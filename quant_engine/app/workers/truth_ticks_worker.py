"""
Truth Ticks Worker

Processes truth ticks analysis jobs from Redis queue.
Computes volume-weighted truth prints analysis for illiquid preferred stocks.

🔵 CRITICAL: This worker runs in a SEPARATE process/terminal to avoid blocking the main application.
Worker has its own Hammer Pro connection and trade print collection - backend is NOT blocked.
"""

import os
import sys
import json
import time
import signal
import threading
from typing import Dict, Any, Optional, List, Set
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
from app.market_data.truth_ticks_engine import get_truth_ticks_engine
from app.market_data.static_data_store import get_static_store
from app.market_data.trade_print_router import TradePrintRouter
from app.market_data.grpan_engine import get_grpan_engine
from app.market_data.grpan_tick_fetcher import GRPANTickFetcher
from app.live.hammer_client import HammerClient
from app.live.symbol_mapper import SymbolMapper


# Redis keys
STREAM_NAME = "tasks:truth_ticks"  # Redis stream for jobs
JOB_RESULT_PREFIX = "truth_ticks:"  # truth_ticks:{job_id}

# Worker configuration
WORKER_NAME = os.getenv("WORKER_NAME", f"truth_ticks_worker_{os.getpid()}")
POLL_TIMEOUT = int(os.getenv("POLL_TIMEOUT", "5"))  # seconds


class TruthTicksWorker:
    """
    Worker that processes truth ticks analysis jobs from Redis queue.
    
    🔵 CRITICAL: Worker has its own Hammer Pro connection and trade print collection.
    Backend terminal is NOT blocked - all heavy work happens here.
    """
    
    def __init__(self, worker_name: str = None):
        self.worker_name = worker_name or WORKER_NAME
        self.redis_client = None
        self.running = False
        self.processed_jobs = 0
        self.failed_jobs = 0
        self.start_time = None
        
        # Worker's own services (independent from main app)
        self.hammer_client: Optional[HammerClient] = None
        self.truth_ticks_engine = None
        self.grpan_engine = None
        self.trade_print_router = None
        self.grpan_tick_fetcher = None
        self.static_store = None
        
        # Track symbols we're collecting data for
        self.symbols_to_collect: Set[str] = set()
        self._symbols_lock = threading.Lock()
    
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
                    decode_responses=True,
                    socket_connect_timeout=5
                )
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
            
            # Initialize Truth Ticks Engine
            self.truth_ticks_engine = get_truth_ticks_engine()
            logger.info(f"✅ [{self.worker_name}] TruthTicksEngine initialized")
            
            # Load static store (for AVG_ADV)
            from app.market_data.static_data_store import initialize_static_store
            self.static_store = get_static_store()
            if not self.static_store:
                # Initialize static store (creates new instance if not exists)
                try:
                    self.static_store = initialize_static_store()
                    if self.static_store:
                        # Try to load CSV (will auto-find the file)
                        if self.static_store.load_csv():
                            logger.info(f"✅ [{self.worker_name}] Static store initialized and loaded: {len(self.static_store.get_all_symbols())} symbols")
                        else:
                            logger.warning(f"⚠️ [{self.worker_name}] Static store initialized but CSV not found (will use empty store)")
                    else:
                        logger.warning(f"⚠️ [{self.worker_name}] Failed to initialize static store")
                except Exception as e:
                    logger.warning(f"⚠️ [{self.worker_name}] Failed to initialize/load static store: {e}", exc_info=True)
            elif not self.static_store.is_loaded():
                # Try to load static store
                try:
                    if self.static_store.load_csv():
                        logger.info(f"✅ [{self.worker_name}] Static store loaded: {len(self.static_store.get_all_symbols())} symbols")
                    else:
                        logger.warning(f"⚠️ [{self.worker_name}] CSV file not found (will use empty store)")
                except Exception as e:
                    logger.warning(f"⚠️ [{self.worker_name}] Failed to load static store: {e}", exc_info=True)
            else:
                logger.info(f"✅ [{self.worker_name}] Static store already loaded: {len(self.static_store.get_all_symbols())} symbols")
            
            # Initialize GRPAN engine (for trade print routing)
            from app.market_data.grpan_engine import get_grpan_engine, initialize_grpan_engine
            # Try to get existing instance first
            self.grpan_engine = get_grpan_engine()
            if not self.grpan_engine:
                # Create new instance if not available
                self.grpan_engine = initialize_grpan_engine()
            if not self.grpan_engine:
                raise Exception("GRPANEngine not available")
            
            # Start GRPAN compute loop
            self.grpan_engine.start_compute_loop()
            logger.info(f"✅ [{self.worker_name}] GRPANEngine initialized and compute loop started")
            
            # Initialize TradePrintRouter (with custom callback for TruthTicksEngine)
            self.trade_print_router = TradePrintRouter(self.grpan_engine)
            
            # Override route_trade_print to also add to TruthTicksEngine
            original_route = self.trade_print_router.route_trade_print
            
            def enhanced_route_trade_print(raw_print: Dict[str, Any], hammer_symbol: str) -> Optional[Dict[str, Any]]:
                """Enhanced route that also adds to TruthTicksEngine"""
                normalized = original_route(raw_print, hammer_symbol)
                if normalized and self.truth_ticks_engine:
                    # Convert to TruthTicksEngine format
                    # normalized already has display_symbol from TradePrintRouter
                    display_symbol = normalized.get('symbol')
                    if display_symbol:
                        truth_tick = {
                            'ts': normalized.get('time'),
                            'price': normalized.get('price'),
                            'size': normalized.get('size'),
                            'exch': normalized.get('venue', 'UNKNOWN')
                        }
                        self.truth_ticks_engine.add_tick(display_symbol, truth_tick)
                return normalized
            
            self.trade_print_router.route_trade_print = enhanced_route_trade_print
            logger.info(f"✅ [{self.worker_name}] TradePrintRouter initialized with TruthTicksEngine integration")
            
            # Initialize Hammer Client (worker's own connection)
            self.hammer_client = HammerClient(
                host=settings.HAMMER_HOST,
                port=settings.HAMMER_PORT,
                password=settings.HAMMER_PASSWORD,
                account_key=settings.HAMMER_ACCOUNT_KEY
            )
            
            # Connect to Hammer Pro
            if not self.hammer_client.connect():
                logger.error(f"❌ [{self.worker_name}] Failed to connect to Hammer Pro")
                raise Exception("Hammer Pro connection failed")
            
            logger.info(f"✅ [{self.worker_name}] Connected to Hammer Pro: {settings.HAMMER_HOST}:{settings.HAMMER_PORT}")
            
            # Initialize GRPANTickFetcher (for trade print collection)
            self.grpan_tick_fetcher = GRPANTickFetcher(
                hammer_client=self.hammer_client,
                trade_print_router=self.trade_print_router,
                grpan_engine=self.grpan_engine,
                last_few_ticks=150,  # Extended buffer for truth ticks (150 prints)
                min_lot_size=10,
                stale_threshold_sec=600.0  # 10 minutes
            )
            
            # Start GRPANTickFetcher
            self.grpan_tick_fetcher.start()
            logger.info(f"✅ [{self.worker_name}] GRPANTickFetcher started")
            
            logger.info(f"✅ [{self.worker_name}] All services initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Failed to initialize services: {e}", exc_info=True)
            return False
    
    def process_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a truth ticks analysis job.
        
        Args:
            job_data: Job data from Redis queue
                - job_id: Job ID
                - symbols: List of symbols to analyze (None = all symbols)
                
        Returns:
            Result dict with metrics for each symbol
        """
        job_id = job_data.get("job_id")
        symbols = job_data.get("symbols")  # None = all symbols
        
        logger.info(f"🔄 [{self.worker_name}] Processing job {job_id}")
        
        try:
            # Get symbols to process
            if symbols is None:
                # Process all symbols from static store
                if self.static_store and self.static_store.is_loaded():
                    symbols_to_process = self.static_store.get_all_symbols()
                    logger.info(f"📊 [{self.worker_name}] Processing all {len(symbols_to_process)} symbols from static store")
                else:
                    # Fallback: use symbols from TruthTicksEngine (symbols that have received ticks)
                    symbols_to_process = self.truth_ticks_engine.get_all_symbols()
                    if not symbols_to_process:
                        logger.warning(f"⚠️ [{self.worker_name}] No symbols available: static_store not loaded and no ticks collected yet")
                        logger.info(f"💡 [{self.worker_name}] Worker needs time to bootstrap - wait for Hammer connection and tick collection")
                    else:
                        logger.info(f"📊 [{self.worker_name}] Processing all {len(symbols_to_process)} symbols from TruthTicksEngine (symbols with ticks)")
            else:
                # Process only specified symbols
                symbols_to_process = symbols
                logger.info(f"📊 [{self.worker_name}] Processing {len(symbols_to_process)} specified symbols")
            
            if not symbols_to_process:
                logger.warning(f"⚠️ [{self.worker_name}] No symbols to process")
                return {
                    "success": False,
                    "job_id": job_id,
                    "error": "No symbols to process. Worker may need time to bootstrap ticks. Ensure Hammer is connected and static store is loaded.",
                    "data": {},
                    "static_store_loaded": self.static_store.is_loaded() if self.static_store else False,
                    "ticks_collected": len(self.truth_ticks_engine.get_all_symbols()) > 0
                }
            
            # Add symbols to GRPANTickFetcher (bootstrap if needed)
            with self._symbols_lock:
                new_symbols = [s for s in symbols_to_process if s not in self.symbols_to_collect]
                if new_symbols:
                    self.grpan_tick_fetcher.add_symbols(new_symbols, bootstrap=True)
                    self.symbols_to_collect.update(new_symbols)
                    logger.info(f"📊 [{self.worker_name}] Added {len(new_symbols)} new symbols to tick fetcher")
            
            # Wait a bit for initial tick collection (bootstrap)
            logger.info(f"⏳ [{self.worker_name}] Waiting for initial tick collection (bootstrap)...")
            time.sleep(5)  # Give GRPANTickFetcher time to bootstrap
            
            # Fixed timeframes (explicit in code as per requirements)
            TIMEFRAMES = {
                'TF_4H': 4 * 60 * 60,      # 4 hours
                'TF_1D': 24 * 60 * 60,     # 1 day (24 hours)
                'TF_3D': 3 * 24 * 60 * 60, # 3 days
                'TF_5D': 5 * 24 * 60 * 60  # 5 days
            }
            
            # Now compute Truth Ticks metrics for each symbol and each timeframe
            results = {}  # Structure: {symbol: {TF_4H: metrics, TF_1D: metrics, ...}}
            processed_count = 0
            
            for symbol in symbols_to_process:
                try:
                    # Get AVG_ADV from static store
                    avg_adv = 0.0
                    if self.static_store:
                        record = self.static_store.get_static_data(symbol)
                        if record:
                            avg_adv = float(record.get('AVG_ADV', 0) or 0)
                    
                    if avg_adv <= 0:
                        logger.debug(f"⚠️ [{self.worker_name}] No AVG_ADV for {symbol}, skipping")
                        continue
                    
                    # Compute metrics for each timeframe
                    symbol_timeframes = {}
                    has_any_timeframe = False
                    
                    for timeframe_name, timeframe_seconds in TIMEFRAMES.items():
                        try:
                            # Compute timeframe-based metrics
                            metrics = self.truth_ticks_engine.compute_metrics_for_timeframe(
                                symbol, avg_adv, timeframe_name
                            )
                            
                            if metrics:
                                # Ensure timeframe_name is set correctly (never UNKNOWN)
                                metrics['timeframe_name'] = timeframe_name
                                symbol_timeframes[timeframe_name] = metrics
                                has_any_timeframe = True
                                logger.debug(f"✅ [{self.worker_name}] Successfully computed {timeframe_name} for {symbol} (ticks={metrics.get('truth_tick_count', 0)})")
                            else:
                                logger.warning(f"⚠️ [{self.worker_name}] No metrics for {symbol} in {timeframe_name} - check if ticks exist in timeframe window")
                        except Exception as e:
                            logger.warning(f"⚠️ [{self.worker_name}] Error computing {timeframe_name} for {symbol}: {e}")
                            continue
                    
                    if has_any_timeframe:
                        results[symbol] = symbol_timeframes
                        processed_count += 1
                        
                        # Also cache inspect data in Redis for quick access (use TF_1D as default)
                        try:
                            if 'TF_1D' in symbol_timeframes:
                                inspect_data = self.truth_ticks_engine.get_inspect_data(symbol, avg_adv)
                                if inspect_data:
                                    inspect_key = f"truth_ticks:inspect:{symbol}"
                                    self.redis_client.setex(
                                        inspect_key,
                                        3600,  # 1 hour TTL
                                        json.dumps({
                                            "success": True,
                                            "symbol": symbol,
                                            "data": inspect_data
                                        })
                                    )
                        except Exception as e:
                            logger.debug(f"⚠️ [{self.worker_name}] Could not cache inspect data for {symbol}: {e}")
                    else:
                        logger.debug(f"⚠️ [{self.worker_name}] No metrics for {symbol} in any timeframe (insufficient data)")
                        
                except Exception as e:
                    logger.error(f"❌ [{self.worker_name}] Error processing {symbol}: {e}", exc_info=True)
                    continue
            
            logger.info(f"✅ [{self.worker_name}] Processed {processed_count}/{len(symbols_to_process)} symbols (multi-timeframe)")
            
            return {
                "success": True,
                "job_id": job_id,
                "processed_count": processed_count,
                "total_count": len(symbols_to_process),
                "data": results,  # Structure: {symbol: {TF_4H: metrics, TF_1D: metrics, ...}}
                "updated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error processing job {job_id}: {e}", exc_info=True)
            return {
                "success": False,
                "job_id": job_id,
                "error": str(e),
                "data": {}
            }
    
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
            logger.info(f"📊 [{self.worker_name}] Monitoring {len(self.symbols_to_collect)} symbols")
            
            # Track last processed message ID
            last_id = "0"  # Start from beginning of stream
            
            # Main loop - poll Redis stream for jobs
            while self.running:
                try:
                    # Poll Redis stream for jobs
                    # Note: Using XREAD with BLOCK for streaming
                    messages = self.redis_client.xread(
                        {STREAM_NAME: last_id},
                        block=POLL_TIMEOUT * 1000,  # Block in milliseconds
                        count=1
                    )
                    
                    if messages:
                        for stream, stream_messages in messages:
                            for msg_id, msg_data in stream_messages:
                                try:
                                    # Parse job data
                                    job_data = json.loads(msg_data.get('data', '{}'))
                                    # Use job_id from job_data if available, otherwise use msg_id
                                    actual_job_id = job_data.get('job_id') or msg_id
                                    job_data['job_id'] = actual_job_id
                                    
                                    # Process job
                                    result = self.process_job(job_data)
                                    
                                    # Save result to Redis
                                    result_key = f"{JOB_RESULT_PREFIX}{actual_job_id}"
                                    self.redis_client.setex(
                                        result_key,
                                        3600,  # 1 hour TTL
                                        json.dumps(result)
                                    )
                                    
                                    self.processed_jobs += 1
                                    logger.info(f"✅ [{self.worker_name}] Job {actual_job_id} completed and saved to Redis")
                                    
                                    # CRITICAL: Update last_id to avoid reprocessing the same message
                                    last_id = msg_id
                                    
                                except Exception as e:
                                    logger.error(f"❌ [{self.worker_name}] Error processing job message: {e}", exc_info=True)
                                    self.failed_jobs += 1
                                    # Still update last_id to avoid infinite loop on error
                                    last_id = msg_id
                    
                except redis.exceptions.ConnectionError:
                    logger.error(f"❌ [{self.worker_name}] Redis connection lost, reconnecting...")
                    if not self.connect_redis():
                        time.sleep(5)
                        continue
                except Exception as e:
                    logger.error(f"❌ [{self.worker_name}] Error in main loop: {e}", exc_info=True)
                    time.sleep(1)
            
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
            
            if self.grpan_tick_fetcher:
                self.grpan_tick_fetcher.stop()
                logger.info(f"✅ [{self.worker_name}] GRPANTickFetcher stopped")
            
            if self.hammer_client:
                self.hammer_client.disconnect()
                logger.info(f"✅ [{self.worker_name}] Hammer client disconnected")
            
            logger.info(f"✅ [{self.worker_name}] Worker cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error during cleanup: {e}", exc_info=True)


def main():
    """Main entry point"""
    worker = TruthTicksWorker()
    
    # Handle SIGINT (Ctrl+C)
    def signal_handler(sig, frame):
        logger.info(f"🛑 [{worker.worker_name}] Received SIGINT, shutting down...")
        worker.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run worker
    worker.run()


if __name__ == "__main__":
    main()



