"""app/engine/engine_loop.py

Main trading engine loop.
Consumes ticks from Redis, processes through strategy, generates signals.
"""

import time
import asyncio
from typing import Optional

from app.core.logger import logger
from app.core.event_bus import EventBus
from app.strategy.strategy_base import StrategyBase
from app.strategy.candle_manager import CandleManager
from app.engine.position_manager import PositionManager
from app.engine.execution_handler import ExecutionHandler

# Use new RiskManager from risk module
try:
    from app.risk.risk_manager import RiskManager
except ImportError:
    # Fallback to old risk_manager if new one not available
    from app.engine.risk_manager import RiskManager


class TradingEngine:
    """Main trading engine"""
    
    def __init__(self, strategy: StrategyBase, sync_on_start: bool = True):
        """
        Initialize trading engine.
        
        Args:
            strategy: Strategy instance to use
            sync_on_start: Whether to sync positions from IBKR on startup
        """
        self.strategy = strategy
        self.position_manager = PositionManager()
        
        # Initialize RiskManager with limits
        from app.risk.risk_limits import load_risk_limits
        risk_limits = load_risk_limits()
        self.risk_manager = RiskManager(limits=risk_limits)
        self.risk_manager.set_position_manager(self.position_manager)
        
        self.execution_handler: Optional[ExecutionHandler] = None
        self.running = False
        self.tick_count = 0
        self.signal_count = 0
        self.sync_on_start = sync_on_start
    
    def run(self):
        """
        Run engine (synchronous version - uses Redis pub/sub).
        """
        logger.info("🚀 Trading engine started")
        
        # Create candle manager
        candle_manager = CandleManager(interval_seconds=60)  # 1-minute candles
        
        # Initialize strategy with dependencies
        self.strategy.initialize(
            candle_manager=candle_manager,
            position_manager=self.position_manager,
            risk_manager=self.risk_manager,
            symbols=self.strategy.symbols if hasattr(self.strategy, 'symbols') else None
        )
        
        # Subscribe to ticks channel
        sub = EventBus.subscribe("ticks")
        
        self.running = True
        
        try:
            while self.running:
                message = sub.get_message(ignore_subscribe_messages=True)
                
                if message and message["type"] == "message":
                    try:
                        import json
                        # Parse message data (may be JSON string or already dict)
                        data = message["data"]
                        if isinstance(data, str):
                            tick = json.loads(data)
                        else:
                            tick = data
                        self.tick_count += 1
                        
                        # Process tick through strategy (new interface)
                        signal = self.strategy.on_tick(tick)
                        
                        if signal:
                            self.signal_count += 1
                            logger.info(f"Signal generated: {signal}")
                            
                            # Risk check
                            if self.risk_manager.check_signal(signal):
                                # Publish signal
                                EventBus.publish("signals", signal)
                                logger.info(f"Signal approved by risk manager: {signal}")
                            else:
                                logger.warning(f"Signal rejected by risk manager: {signal}")
                        
                        # Periodic stats
                        if self.tick_count % 100 == 0:
                            logger.info(
                                f"Engine stats: Ticks={self.tick_count}, "
                                f"Signals={self.signal_count}"
                            )
                    
                    except Exception as e:
                        logger.error(f"Error processing tick: {e}", exc_info=True)
                
                time.sleep(0.001)  # Small sleep to prevent CPU spinning
        
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()
    
    async def run_async(self):
        """
        Run engine (asynchronous version - uses Redis streams).
        """
        logger.info("🚀 Trading engine started (async mode)")
        
        # Sync positions from IBKR on startup
        if self.sync_on_start:
            await self._sync_positions_on_start()
        
        # Create candle manager
        candle_manager = CandleManager(interval_seconds=60)  # 1-minute candles
        
        # Initialize strategy with dependencies
        self.strategy.initialize(
            candle_manager=candle_manager,
            position_manager=self.position_manager,
            risk_manager=self.risk_manager,
            symbols=self.strategy.symbols if hasattr(self.strategy, 'symbols') else None
        )
        
        # Start execution handler (with risk manager)
        self.execution_handler = ExecutionHandler(self.position_manager, risk_manager=self.risk_manager)
        self.execution_handler.start()
        
        self.running = True
        last_id = '0-0'
        
        try:
            while self.running:
                # Read from ticks stream
                messages = EventBus.xread({'ticks': last_id}, count=10, block=1000)
                
                if messages:
                    for stream, items in messages:
                        for msg_id, data in items:
                            last_id = msg_id
                            self.tick_count += 1
                            
                            # Process tick through strategy
                            signal = self.strategy.on_tick(data)
                            
                            if signal:
                                self.signal_count += 1
                                logger.info(f"Signal generated: {signal}")
                                
                                # Risk check
                                if self.risk_manager.check_signal(signal):
                                    # Publish signal
                                    await EventBus.publish_async("signals", signal)
                                    logger.info(f"Signal approved by risk manager: {signal}")
                                else:
                                    logger.warning(f"Signal rejected by risk manager: {signal}")
                    
                    # Periodic stats
                    if self.tick_count % 100 == 0:
                        logger.info(
                            f"Engine stats: Ticks={self.tick_count}, "
                            f"Signals={self.signal_count}"
                        )
                else:
                    await asyncio.sleep(0.1)
        
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            await self.stop_async()
    
    def stop(self):
        """Stop engine (synchronous)"""
        logger.info("Stopping trading engine...")
        self.running = False
        self.strategy.cleanup()
        logger.info(f"Engine stopped. Final stats: Ticks={self.tick_count}, Signals={self.signal_count}")
    
    async def stop_async(self):
        """Stop engine (asynchronous)"""
        logger.info("Stopping trading engine (async)...")
        self.running = False
        
        # Stop execution handler
        if self.execution_handler:
            self.execution_handler.stop()
        
        self.strategy.cleanup()
        logger.info(f"Engine stopped. Final stats: Ticks={self.tick_count}, Signals={self.signal_count}")
    
    async def _sync_positions_on_start(self):
        """Sync positions from IBKR on startup"""
        try:
            from app.ibkr.ibkr_client import ibkr_client
            from app.ibkr.ibkr_sync import ibkr_sync
            
            # Connect to IBKR if not connected
            if not ibkr_client.is_connected():
                logger.info("Connecting to IBKR for position sync...")
                if not ibkr_client.connect():
                    logger.warning("Could not connect to IBKR, skipping position sync")
                    return
            
            # Sync positions
            logger.info("Syncing positions from IBKR...")
            ibkr_sync.sync_positions_to_manager(self.position_manager)
            
            # Log synced positions
            positions = self.position_manager.get_positions_summary()
            if positions:
                logger.info(f"Synced {len(positions)} positions from IBKR:")
                for pos in positions:
                    logger.info(f"  {pos['symbol']}: {pos['qty']:+.0f} @ ${pos['avg_price']:.2f}")
            else:
                logger.info("No positions to sync")
        
        except Exception as e:
            logger.error(f"Error syncing positions on startup: {e}", exc_info=True)

