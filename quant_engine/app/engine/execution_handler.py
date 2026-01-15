"""app/engine/execution_handler.py

Execution handler - subscribes to executions stream and updates position manager.

This module handles execution messages from IBKR, processes them, and updates
the position manager. It runs in a background thread to avoid blocking the main engine.
"""

import json
import time
import threading
from typing import Dict, Any, Optional

from app.core.event_bus import EventBus
from app.core.logger import logger
from app.engine.position_manager import PositionManager

# Risk manager (optional, injected later)
try:
    from app.risk.risk_manager import RiskManager
    RISK_MANAGER_AVAILABLE = True
except ImportError:
    RISK_MANAGER_AVAILABLE = False
    RiskManager = None


class ExecutionHandler:
    """Handles execution messages and updates position manager"""
    
    def __init__(self, position_manager: PositionManager, risk_manager: Optional[Any] = None):
        """
        Initialize execution handler.
        
        Args:
            position_manager: PositionManager instance to update
            risk_manager: RiskManager instance (optional)
        """
        self.position_manager = position_manager
        self.risk_manager = risk_manager
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.execution_count = 0
        self.error_count = 0
        self.executions_stream = "executions"
        self.last_id = "0-0"
    
    def start(self):
        """Start execution handler in background thread"""
        if self.running:
            logger.warning("Execution handler already running")
            return
        
        logger.info("🚀 Execution handler started")
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop execution handler"""
        logger.info("Stopping execution handler...")
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
        logger.info(
            f"Execution handler stopped. Processed: {self.execution_count}, Errors: {self.error_count}"
        )
    
    def _loop(self):
        """Main execution processing loop"""
        logger.info("Execution handler loop started")
        
        while self.running:
            try:
                # Read from executions stream
                msg = EventBus.stream_read(
                    self.executions_stream,
                    last_id=self.last_id,
                    block=1000,
                    count=1
                )
                
                if msg is None:
                    continue
                
                # Update last_id
                self.last_id = msg["id"]
                
                # Parse message
                try:
                    data = msg["data"]
                    
                    # Decode bytes if needed
                    if isinstance(data, dict):
                        exec_data = data
                    else:
                        if isinstance(data, bytes):
                            exec_data = json.loads(data.decode())
                        else:
                            exec_data = json.loads(data)
                    
                    # Process execution
                    self._process_execution(exec_data)
                    self.execution_count += 1
                    
                    # Periodic logging
                    if self.execution_count % 10 == 0:
                        logger.info(
                            f"Execution handler: Processed {self.execution_count} executions "
                            f"(errors: {self.error_count})"
                        )
                
                except Exception as e:
                    self.error_count += 1
                    logger.error(f"Error processing execution: {e}", exc_info=True)
                    # Exponential backoff on errors
                    time.sleep(min(0.1 * (2 ** min(self.error_count, 5)), 5.0))
            
            except KeyboardInterrupt:
                logger.info("Execution handler interrupted")
                break
            except Exception as e:
                self.error_count += 1
                logger.error(f"Error in execution handler loop: {e}", exc_info=True)
                # Exponential backoff on critical errors
                time.sleep(min(1.0 * (2 ** min(self.error_count, 5)), 10.0))
    
    def _process_execution(self, exec_data: Dict[str, Any]):
        """
        Process execution message and update position manager.
        
        Args:
            exec_data: Execution message dict
        """
        try:
            symbol = exec_data.get("symbol")
            # Support both formats: fill_qty/fill_price (normalized) and qty/price (legacy)
            qty = float(exec_data.get("fill_qty") or exec_data.get("qty", 0))
            price = float(exec_data.get("fill_price") or exec_data.get("price", 0))
            side = exec_data.get("side", "BUY").upper()
            order_id = exec_data.get("order_id")
            exec_id = exec_data.get("exec_id")
            
            if not symbol or qty <= 0 or price <= 0:
                logger.warning(f"Invalid execution data: {exec_data}")
                return
            
            # Convert side to quantity (BUY = positive, SELL = negative)
            if side == "BUY":
                quantity = qty
            elif side == "SELL":
                quantity = -qty
            else:
                logger.warning(f"Invalid side: {side}")
                return
            
            # Update position
            self.position_manager.update_position(symbol, quantity, price)
            
            # Update risk manager
            if self.risk_manager:
                # Calculate P&L if position closed
                position = self.position_manager.get_position(symbol)
                pnl = None
                if position and position.get('qty', 0) == 0:
                    # Position closed, calculate realized P&L
                    # This is simplified - in production, use FIFO queue
                    pnl = 0.0  # Will be calculated by position manager
                
                self.risk_manager.update_after_execution(symbol, side, qty, price, pnl)
            
            # Structured logging
            logger.info(
                "Execution processed",
                extra={
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "price": price,
                    "order_id": order_id,
                    "exec_id": exec_id
                }
            )
            
        except Exception as e:
            logger.error(f"Error processing execution: {exec_data}: {e}", exc_info=True)
            raise

