"""
Ticker Alert Worker

Monitors price updates from Hammer Pro and generates ticker alerts (NEW_HIGH/NEW_LOW).
Runs in a separate process/terminal to avoid blocking the main application.

🔵 CRITICAL: This worker runs in a SEPARATE process/terminal.
Worker has its own Hammer Pro connection and processes L1Updates independently.
"""

import os
import sys
import json
import time
import signal
import threading
from typing import Dict, Any, Optional, Set
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("ERROR: redis package not installed. Install with: pip install redis")
    sys.exit(1)

from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.config.settings import settings
from app.market_data.ticker_alert_engine import get_ticker_alert_engine, TickerAlert
from app.market_data.static_data_store import get_static_store
from app.live.hammer_client import HammerClient
from app.live.symbol_mapper import SymbolMapper


# Redis keys for alert broadcasting
ALERT_CHANNEL = "ticker_alerts:events"  # Pub/Sub channel for alerts
ALERT_QUEUE = "ticker_alerts:queue"  # Queue for alert processing (if needed)

# Worker configuration
WORKER_NAME = os.getenv("WORKER_NAME", f"ticker_alert_worker_{os.getpid()}")


class TickerAlertWorker:
    """
    Worker that monitors Hammer Pro price updates and generates ticker alerts.
    
    🔵 CRITICAL: Worker has its own Hammer Pro connection.
    Main application terminal is NOT blocked - all monitoring happens here.
    """
    
    def __init__(self, worker_name: str = None):
        self.worker_name = worker_name or WORKER_NAME
        self.redis_client = None
        self.running = False
        self.start_time = None
        
        # Worker's own services (independent from main app)
        self.hammer_client: Optional[HammerClient] = None
        self.ticker_alert_engine = None
        self.static_store = None
        
        # Track subscribed symbols
        self.subscribed_symbols: Set[str] = set()
        self._symbols_lock = threading.Lock()
        
        # Statistics
        self.alerts_generated = 0
        self.price_updates_processed = 0
        
    def connect_redis(self):
        """Connect to Redis"""
        try:
            redis_client = get_redis_client()
            self.redis_client = redis_client.sync
            
            if not self.redis_client:
                # Try direct connection
                self.redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    db=0,  # Default Redis DB
                    decode_responses=True  # Decode for JSON
                )
            
            # Test connection
            self.redis_client.ping()
            logger.info(f"✅ Worker {self.worker_name} connected to Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            return False
    
    def initialize_services(self):
        """Initialize worker's own services"""
        try:
            logger.info(f"🔧 [{self.worker_name}] Initializing worker services...")
            
            # Initialize ticker alert engine
            self.ticker_alert_engine = get_ticker_alert_engine()
            logger.info(f"✅ [{self.worker_name}] TickerAlertEngine initialized")
            
            # Load static store (for symbol mapping)
            self.static_store = get_static_store()
            if not self.static_store:
                logger.warning(f"⚠️ [{self.worker_name}] Static store not available")
            elif not self.static_store.is_loaded():
                # Try to load static store
                try:
                    csv_path = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                        "janall", "janalldata.csv"
                    )
                    if os.path.exists(csv_path):
                        self.static_store.load_csv(csv_path)
                        logger.info(f"✅ [{self.worker_name}] Static store loaded from {csv_path}: {len(self.static_store.get_all_symbols())} symbols")
                    else:
                        logger.warning(f"⚠️ [{self.worker_name}] CSV file not found at {csv_path}")
                except Exception as e:
                    logger.warning(f"⚠️ [{self.worker_name}] Failed to load static store: {e}")
            else:
                logger.info(f"✅ [{self.worker_name}] Static store already loaded: {len(self.static_store.get_all_symbols())} symbols")
            
            # Initialize Hammer client
            self.hammer_client = HammerClient(
                host=settings.HAMMER_HOST,
                port=settings.HAMMER_PORT,
                password=settings.HAMMER_PASSWORD,
                account_key=settings.HAMMER_ACCOUNT_KEY
            )
            
            # Set up message callback for L1Updates (before connecting)
            # This will be called for all L1Update messages from Hammer Pro
            self.hammer_client.on_message_callback = self._handle_hammer_message
            
            # Connect to Hammer Pro
            if self.hammer_client.connect():
                logger.info(f"✅ [{self.worker_name}] Connected to Hammer Pro")
                
                # Preload daily high/low from snapshots
                self._preload_daily_high_low()
                
                # Subscribe to all symbols for L1Updates
                # CRITICAL: Worker must explicitly subscribe to receive L1Updates
                self._subscribe_to_symbols()
            else:
                logger.error(f"❌ [{self.worker_name}] Failed to connect to Hammer Pro")
                return False
            
            logger.info(f"✅ [{self.worker_name}] Services initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Failed to initialize services: {e}", exc_info=True)
            return False
    
    def _subscribe_to_symbols(self):
        """Subscribe to all symbols for L1Updates"""
        try:
            if not self.hammer_client or not self.hammer_client.is_connected():
                logger.warning(f"⚠️ [{self.worker_name}] Hammer client not connected, cannot subscribe")
                return
            
            symbols_to_subscribe = []
            
            # Get preferred symbols from static store
            if self.static_store and self.static_store.is_loaded():
                preferred_symbols = self.static_store.get_all_symbols()
                symbols_to_subscribe.extend(preferred_symbols)
            
            # Add ETFs
            from app.api.market_data_routes import ETF_TICKERS
            symbols_to_subscribe.extend(ETF_TICKERS)
            
            if not symbols_to_subscribe:
                logger.warning(f"⚠️ [{self.worker_name}] No symbols to subscribe")
                return
            
            logger.info(f"📊 [{self.worker_name}] Subscribing to {len(symbols_to_subscribe)} symbols for ticker alerts...")
            
            # Use HammerFeed for batch subscription (same as backend)
            # But preserve worker's callback (HammerFeed will try to override it)
            from app.live.hammer_feed import HammerFeed
            original_callback = self.hammer_client.on_message_callback
            hammer_feed = HammerFeed(self.hammer_client)
            # Restore worker's callback (HammerFeed sets its own, but we need ours)
            self.hammer_client.on_message_callback = original_callback
            
            # Subscribe in batches (L1 only for ticker alerts)
            subscribed_count = hammer_feed.subscribe_symbols_batch(
                symbols_to_subscribe,
                include_l2=False,  # L1 only for ticker alerts
                batch_size=50
            )
            
            # Track subscribed symbols
            with self._symbols_lock:
                self.subscribed_symbols.update(symbols_to_subscribe[:subscribed_count])
            
            logger.info(f"✅ [{self.worker_name}] Subscribed to {subscribed_count}/{len(symbols_to_subscribe)} symbols for ticker alerts")
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error subscribing to symbols: {e}", exc_info=True)
    
    def _preload_daily_high_low(self):
        """Preload daily high/low from Hammer snapshots"""
        try:
            from app.live.snapshot_queue import enqueue_snapshot
            
            symbols_to_preload = []
            
            # Get all symbols
            if self.static_store and self.static_store.is_loaded():
                preferred_symbols = self.static_store.get_all_symbols()
                symbols_to_preload.extend(preferred_symbols)
            
            from app.api.market_data_routes import ETF_TICKERS
            symbols_to_preload.extend(ETF_TICKERS)
            
            logger.info(f"📊 [{self.worker_name}] Preloading daily high/low for {len(symbols_to_preload)} symbols...")
            
            # Enqueue snapshot requests with callback
            def create_snapshot_callback(symbol: str):
                def snapshot_callback(snapshot_dict: Dict[str, Any]):
                    if not snapshot_dict:
                        return
                    
                    daily_high = snapshot_dict.get('high')
                    daily_low = snapshot_dict.get('low')
                    
                    if daily_high and daily_high > 0 and daily_low and daily_low > 0:
                        self.ticker_alert_engine.load_daily_high_low_from_snapshot(symbol, daily_high, daily_low)
                        logger.debug(f"✅ Cached daily high/low for {symbol}: high={daily_high}, low={daily_low}")
                
                return snapshot_callback
            
            enqueued = 0
            for symbol in symbols_to_preload:
                callback = create_snapshot_callback(symbol)
                if enqueue_snapshot(symbol, callback=callback):
                    enqueued += 1
            
            logger.info(f"📊 [{self.worker_name}] Enqueued {enqueued} snapshot requests for daily high/low preload")
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error preloading daily high/low: {e}", exc_info=True)
    
    def _handle_hammer_message(self, data: Dict[str, Any]):
        """Handle incoming Hammer Pro messages"""
        try:
            cmd = data.get("cmd", "")
            
            # Debug: Log first few messages to verify callback is working
            if not hasattr(self, '_msg_count'):
                self._msg_count = 0
            self._msg_count += 1
            if self._msg_count <= 10:
                logger.info(f"📥 [{self.worker_name}] Message #{self._msg_count}: cmd={cmd}")
            
            # Handle both "L1Update" and "l1Update" (case variations)
            if cmd.lower() == "l1update":
                self._handle_l1_update(data.get("result", {}))
            elif cmd.lower() == "symbolsnapshot":
                self._handle_snapshot(data.get("result", {}))
                
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error handling Hammer message: {e}", exc_info=True)
    
    def _handle_l1_update(self, result: Dict[str, Any]):
        """Handle L1Update from Hammer Pro"""
        try:
            symbol_hammer = result.get("sym", "")
            if not symbol_hammer:
                return
            
            # Convert to display symbol
            symbol = SymbolMapper.to_display_symbol(symbol_hammer)
            
            # Debug: Log first few L1Updates
            if not hasattr(self, '_l1update_count'):
                self._l1update_count = 0
            self._l1update_count += 1
            if self._l1update_count <= 10:
                logger.info(f"📊 [{self.worker_name}] L1Update #{self._l1update_count}: {symbol} (hammer={symbol_hammer}), result keys: {list(result.keys())}")
            
            last_price = result.get("last")
            if not last_price or last_price <= 0:
                # Debug: Log why we're skipping
                if self._l1update_count <= 10:
                    logger.debug(f"⚠️ [{self.worker_name}] Skipping {symbol}: last_price={last_price}")
                return
            
            # Get prev_close from static store or snapshot
            prev_close = None
            if self.static_store:
                record = self.static_store.get_symbol_data(symbol)
                if record:
                    prev_close = record.get('prev_close')
            
            # Get timestamp
            timestamp = result.get("timestamp")
            if not timestamp:
                timestamp = datetime.now().isoformat()
            
            # Process price update through ticker alert engine
            alert = self.ticker_alert_engine.process_price_update(
                symbol=symbol,
                last_price=last_price,
                prev_close=prev_close,
                timestamp=timestamp,
                session_id=None  # Global session for now
            )
            
            self.price_updates_processed += 1
            
            # If alert was generated, broadcast it
            if alert:
                self.alerts_generated += 1
                self._broadcast_alert(alert)
                logger.info(
                    f"🔔 [{self.worker_name}] {alert.event_type}: {alert.symbol} @ ${alert.price:.2f} "
                    f"(prev high: ${alert.daily_high:.2f}, prev low: ${alert.daily_low:.2f})"
                )
                
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error handling L1Update: {e}", exc_info=True)
    
    def _handle_snapshot(self, result: Dict[str, Any]):
        """Handle symbol snapshot from Hammer Pro (for daily high/low initialization)"""
        try:
            symbol_hammer = result.get("sym", "")
            if not symbol_hammer:
                return
            
            symbol = SymbolMapper.to_display_symbol(symbol_hammer)
            
            daily_high = result.get("high")
            daily_low = result.get("low")
            
            if daily_high and daily_high > 0 and daily_low and daily_low > 0:
                self.ticker_alert_engine.load_daily_high_low_from_snapshot(symbol, daily_high, daily_low)
                logger.debug(f"✅ [{self.worker_name}] Loaded daily high/low for {symbol}: high={daily_high}, low={daily_low}")
                
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error handling snapshot: {e}", exc_info=True)
    
    def _broadcast_alert(self, alert: TickerAlert):
        """Broadcast alert to Redis pub/sub and main application"""
        try:
            if not self.redis_client:
                return
            
            # Publish to Redis pub/sub channel
            alert_dict = alert.to_dict()
            alert_json = json.dumps(alert_dict)
            self.redis_client.publish(ALERT_CHANNEL, alert_json)
            
            logger.debug(f"📡 [{self.worker_name}] Published alert to Redis: {alert.symbol} {alert.event_type}")
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error broadcasting alert: {e}", exc_info=True)
    
    def run(self):
        """Main worker loop"""
        try:
            logger.info(f"🚀 Worker {self.worker_name} starting...")
            
            # Connect to Redis
            if not self.connect_redis():
                logger.error(f"❌ Cannot start worker: Redis connection failed")
                return
            
            # Initialize services
            if not self.initialize_services():
                logger.error(f"❌ Cannot start worker: Service initialization failed")
                return
            
            self.running = True
            self.start_time = time.time()
            
            logger.info(f"✅ [{self.worker_name}] Worker started successfully")
            logger.info(f"📊 [{self.worker_name}] Monitoring {len(self.subscribed_symbols)} symbols")
            
            # Main loop - keep worker alive
            while self.running:
                time.sleep(1)
                
                # Log statistics every 60 seconds
                if int(time.time()) % 60 == 0:
                    uptime = int(time.time() - self.start_time)
                    logger.info(
                        f"📊 [{self.worker_name}] Stats: "
                        f"uptime={uptime}s, "
                        f"alerts={self.alerts_generated}, "
                        f"updates={self.price_updates_processed}"
                    )
            
        except KeyboardInterrupt:
            logger.info(f"🛑 [{self.worker_name}] Worker stopped by user")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Worker error: {e}", exc_info=True)
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            self.running = False
            
            if self.hammer_client:
                self.hammer_client.disconnect()
                logger.info(f"✅ [{self.worker_name}] Hammer client disconnected")
            
            logger.info(f"✅ [{self.worker_name}] Worker cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error during cleanup: {e}", exc_info=True)


def main():
    """Main entry point"""
    worker = TickerAlertWorker()
    
    # Handle SIGINT (Ctrl+C)
    def signal_handler(sig, frame):
        logger.info(f"🛑 [{worker.worker_name}] Received SIGINT, shutting down...")
        worker.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run worker
    worker.run()


if __name__ == "__main__":
    main()


