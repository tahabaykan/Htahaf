"""
Decision Helper Worker

Processes decision helper jobs from Redis queue.
Computes market state classification metrics from tick-by-tick data.

🔵 CRITICAL: This worker runs in a SEPARATE process/terminal to avoid blocking the main application.
Worker has its own Hammer Pro connection and tick collection - backend is NOT blocked.
"""

import os
import sys
import json
import time
import signal
import threading
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from collections import defaultdict

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
from app.market_data.decision_helper_engine import get_decision_helper_engine
from app.market_data.static_data_store import get_static_store, initialize_static_store
from app.live.hammer_client import HammerClient
from app.live.symbol_mapper import SymbolMapper


# Redis keys
JOB_QUEUE_KEY = "tasks:decision_helper"  # Redis stream for jobs
JOB_RESULT_PREFIX = "decision:"  # decision:{group}:{symbol}:{window}

# Worker configuration
WORKER_NAME = os.getenv("WORKER_NAME", f"decision_helper_worker_{os.getpid()}")
POLL_TIMEOUT = int(os.getenv("POLL_TIMEOUT", "5"))  # seconds


class DecisionHelperWorker:
    """
    Worker that processes decision helper jobs from Redis queue.
    
    🔵 CRITICAL: Worker has its own Hammer Pro connection and tick collection.
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
        self.decision_engine = None
        self.static_store = None
        
        # Track symbols we're collecting data for
        self.symbols_to_collect: Set[str] = set()
        self._symbols_lock = threading.Lock()
        
        # Bootstrap progress tracking
        self.bootstrap_progress = {'total': 0, 'completed': 0, 'tick_count': 0}
        
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
            
            # Initialize decision helper engine
            self.decision_engine = get_decision_helper_engine()
            logger.info(f"✅ [{self.worker_name}] DecisionHelperEngine initialized")
            
            # Load static store
            # Try to get existing instance first
            self.static_store = get_static_store()
            
            # If not available, create new instance
            if not self.static_store:
                logger.info(f"📊 [{self.worker_name}] Creating new StaticDataStore instance...")
                # Calculate CSV path: go up 4 levels from worker file to project root
                worker_file = os.path.abspath(__file__)
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(worker_file))))
                csv_path = os.path.join(project_root, "janall", "janalldata.csv")
                logger.info(f"📊 [{self.worker_name}] CSV path: {csv_path}")
                self.static_store = initialize_static_store(csv_path=csv_path)
            
            # Load CSV if not already loaded
            if self.static_store and not self.static_store.is_loaded():
                try:
                    # Calculate CSV path
                    worker_file = os.path.abspath(__file__)
                    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(worker_file))))
                    csv_path = os.path.join(project_root, "janall", "janalldata.csv")
                    
                    logger.info(f"📊 [{self.worker_name}] Attempting to load CSV from: {csv_path}")
                    logger.info(f"📊 [{self.worker_name}] CSV exists: {os.path.exists(csv_path)}")
                    
                    if os.path.exists(csv_path):
                        self.static_store.load_csv(csv_path)
                        logger.info(f"✅ [{self.worker_name}] Static store loaded from {csv_path}: {len(self.static_store.get_all_symbols())} symbols")
                    else:
                        logger.warning(f"⚠️ [{self.worker_name}] CSV file not found at {csv_path}")
                except Exception as e:
                    logger.error(f"❌ [{self.worker_name}] Failed to load static store: {e}", exc_info=True)
            elif self.static_store and self.static_store.is_loaded():
                logger.info(f"✅ [{self.worker_name}] Static store already loaded: {len(self.static_store.get_all_symbols())} symbols")
            else:
                logger.warning(f"⚠️ [{self.worker_name}] Static store not available")
            
            # Initialize Hammer client
            self.hammer_client = HammerClient(
                host=settings.HAMMER_HOST,
                port=settings.HAMMER_PORT,
                password=settings.HAMMER_PASSWORD,
                account_key=settings.HAMMER_ACCOUNT_KEY
            )
            
            # Set up message callback for L1Updates and L2Updates
            self.hammer_client.on_message_callback = self._handle_hammer_message
            
            # Connect to Hammer Pro
            if self.hammer_client.connect():
                logger.info(f"✅ [{self.worker_name}] Connected to Hammer Pro")
                
                # Bootstrap: Fetch initial ticks for all symbols using getTicks
                self._bootstrap_ticks()
            else:
                logger.error(f"❌ [{self.worker_name}] Failed to connect to Hammer Pro")
                return False
            
            logger.info(f"✅ [{self.worker_name}] All services initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Failed to initialize services: {e}", exc_info=True)
            return False
    
    def _bootstrap_ticks(self):
        """Bootstrap tick data using getTicks for all symbols"""
        try:
            if not self.static_store or not self.static_store.is_loaded():
                logger.warning(f"⚠️ [{self.worker_name}] Static store not loaded, skipping bootstrap")
                return
            
            symbols = self.static_store.get_all_symbols()
            logger.info(f"📊 [{self.worker_name}] Bootstrapping ticks for {len(symbols)} symbols...")
            
            # Bootstrap progress tracking
            self.bootstrap_progress = {'total': len(symbols), 'completed': 0, 'tick_count': 0}
            
            # Bootstrap in background (non-blocking)
            import threading
            def bootstrap_thread():
                for idx, symbol in enumerate(symbols):
                    try:
                        # Get last 100 ticks using getTicks
                        # CRITICAL: tradesOnly=True ensures we only get REAL TRADES
                        # This filters out bid/ask updates (size=0) and pseudo-ticks
                        hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
                        tick_data = self.hammer_client.get_ticks(
                            symbol,
                            lastFew=100,
                            tradesOnly=True,  # ONLY real trades - no bid/ask updates
                            regHoursOnly=True
                        )
                        
                        symbol_tick_count = 0
                        # get_ticks returns {'data': [...]}, not {'ticks': [...]}
                        if tick_data and tick_data.get('data'):
                            ticks = tick_data.get('data', [])
                            
                            # DEBUG: Log first tick format to understand Hammer Pro response
                            if len(ticks) > 0 and symbol_tick_count == 0:
                                first_tick_sample = ticks[0]
                                logger.info(
                                    f"🔍 [TICK FORMAT] {symbol}: First tick sample keys: {list(first_tick_sample.keys())}, "
                                    f"sample: {first_tick_sample}"
                                )
                            
                            # Add ticks to decision engine
                            for idx, tick in enumerate(ticks):
                                # Convert Hammer tick format to decision engine format
                                # Hammer Pro getTicks returns: {'t': timestamp (ISO 8601), 'p': price, 's': size, 'b': bid, 'a': ask, 'bf': backfilled}
                                # According to documentation: t = "the tick timestamp ISO 8601 format" (string)
                                
                                # Get timestamp - Hammer Pro uses 't' field (ISO 8601 string)
                                raw_timestamp = tick.get('t')
                                
                                # If no timestamp, log and skip this tick (we can't use it for displacement calculation)
                                if raw_timestamp is None:
                                    if idx < 3:  # Log first few missing timestamps
                                        logger.warning(
                                            f"⚠️ [{self.worker_name}] Tick {idx} for {symbol} has no 't' timestamp! "
                                            f"Tick keys: {list(tick.keys())}, Tick sample: {tick}"
                                        )
                                    continue
                                
                                # Hammer Pro returns ISO 8601 format string (e.g., "2020-08-12T11:00:07.500")
                                # Use it directly - no conversion needed
                                timestamp_iso = str(raw_timestamp)
                                
                                decision_tick = {
                                    't': timestamp_iso,  # ISO 8601 format string
                                    'p': float(tick.get('p', 0)),  # Hammer Pro uses 'p' for price
                                    's': float(tick.get('s', 0)),  # Hammer Pro uses 's' for size
                                    'b': float(tick.get('b', 0)),  # Hammer Pro uses 'b' for bid
                                    'a': float(tick.get('a', 0)),  # Hammer Pro uses 'a' for ask
                                    'bf': tick.get('bf', False)  # Hammer Pro uses 'bf' for backfilled
                                }
                                
                                if decision_tick['p'] > 0 and decision_tick['s'] > 0:
                                    self.decision_engine.add_tick(symbol, decision_tick)
                                    symbol_tick_count += 1
                                    
                                    # Log first few ticks to debug timestamp format
                                    if symbol_tick_count <= 3:
                                        logger.info(
                                            f"🔍 [TICK] {symbol} tick {symbol_tick_count}: "
                                            f"raw_ts={raw_timestamp} (type={type(raw_timestamp).__name__}), "
                                            f"iso_ts={timestamp_iso}, "
                                            f"price={decision_tick['p']}, size={decision_tick['s']}, "
                                            f"bid={decision_tick['b']}, ask={decision_tick['a']}"
                                        )
                            
                            if symbol_tick_count > 0:
                                logger.debug(f"📊 [{self.worker_name}] Added {symbol_tick_count} ticks for {symbol}")
                            
                            self.bootstrap_progress['tick_count'] += symbol_tick_count
                        else:
                            # Log when no ticks found
                            if tick_data:
                                logger.debug(f"⚠️ [{self.worker_name}] No 'data' field in tick_data for {symbol}: {list(tick_data.keys())}")
                            else:
                                logger.debug(f"⚠️ [{self.worker_name}] No tick_data returned for {symbol}")
                        
                        self.bootstrap_progress['completed'] = idx + 1
                        
                        # Log progress every 50 symbols
                        if (idx + 1) % 50 == 0:
                            logger.info(f"📊 [{self.worker_name}] Bootstrap progress: {idx + 1}/{len(symbols)} symbols, {self.bootstrap_progress['tick_count']} total ticks")
                        
                        # Small delay to avoid hammering Hammer Pro
                        time.sleep(0.05)  # Reduced from 0.1 to speed up
                    
                    except Exception as e:
                        logger.debug(f"Error bootstrapping {symbol}: {e}")
                
                logger.info(f"✅ [{self.worker_name}] Bootstrap completed: {self.bootstrap_progress['completed']}/{self.bootstrap_progress['total']} symbols, {self.bootstrap_progress['tick_count']} total ticks")
            
            thread = threading.Thread(target=bootstrap_thread, daemon=True)
            thread.start()
            logger.info(f"✅ [{self.worker_name}] Bootstrap thread started")
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error in bootstrap: {e}", exc_info=True)
    
    def _handle_hammer_message(self, data: Dict[str, Any]):
        """Handle incoming Hammer Pro messages"""
        try:
            cmd = data.get("cmd", "")
            
            if cmd == "l2Update":
                # L2Update contains trade prints
                result = data.get("result", {})
                self._handle_l2_update(result)
            elif cmd == "l1Update":
                # L1Update for bid/ask updates (may contain last price)
                result = data.get("result", {})
                self._handle_l1_update(result)
                
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error handling Hammer message: {e}", exc_info=True)
    
    def _handle_l2_update(self, result: Dict[str, Any]):
        """Handle L2Update (trade prints) from Hammer Pro"""
        try:
            symbol_hammer = result.get("sym", "")
            if not symbol_hammer:
                return
            
            symbol = SymbolMapper.to_display_symbol(symbol_hammer)
            
            # Extract trade print data
            # Hammer Pro L2Update format may vary - try multiple field names
            price = result.get("p") or result.get("price") or result.get("last")
            size = result.get("s") or result.get("size") or result.get("volume")
            bid = result.get("b") or result.get("bid")
            ask = result.get("a") or result.get("ask")
            timestamp = result.get("t") or result.get("timestamp") or result.get("time") or datetime.now().isoformat()
            
            if not price or not size:
                return
            
            # Create tick data
            tick = {
                't': timestamp,
                'p': float(price),
                's': float(size),
                'b': float(bid) if bid else 0,
                'a': float(ask) if ask else 0,
                'bf': result.get("bf", False) or result.get("backfilled", False)
            }
            
            # DEBUG: Log symbol mapping for first few ticks per symbol
            if symbol not in getattr(self, '_logged_symbols', set()):
                if not hasattr(self, '_logged_symbols'):
                    self._logged_symbols = set()
                self._logged_symbols.add(symbol)
                logger.debug(
                    f"🔍 [SYMBOL MAPPING] hammer_sym={symbol_hammer}, "
                    f"display_sym={symbol}, price={tick['p']}, size={tick['s']}, "
                    f"timestamp={timestamp}"
                )
            
            # Add to decision engine (engine will filter backfilled ticks)
            self.decision_engine.add_tick(symbol, tick)
            
        except Exception as e:
            logger.debug(f"Error handling L2Update: {e}")
    
    def _handle_l1_update(self, result: Dict[str, Any]):
        """Handle L1Update (bid/ask/last updates) from Hammer Pro"""
        try:
            symbol_hammer = result.get("sym", "")
            if not symbol_hammer:
                return
            
            symbol = SymbolMapper.to_display_symbol(symbol_hammer)
            
            # L1Update contains bid/ask/last but not trade size
            # We'll use this for bid/ask context but won't add as a tick
            # (ticks need size for volume calculations)
            # This is just for reference - actual ticks come from L2Updates
            
        except Exception as e:
            logger.debug(f"Error handling L1Update: {e}")
    
    def get_all_symbols(self) -> List[str]:
        """Get all symbols from static store"""
        if self.static_store and self.static_store.is_loaded():
            return self.static_store.get_all_symbols()
        
        return []
    
    def get_group_for_symbol(self, symbol: str) -> Optional[str]:
        """Get GROUP for a symbol"""
        if self.static_store and self.static_store.is_loaded():
            record = self.static_store.get_static_data(symbol)
            if record:
                return record.get('GROUP')
        return None
    
    def get_avg_adv(self, symbol: str) -> float:
        """Get AVG_ADV for a symbol"""
        if self.static_store and self.static_store.is_loaded():
            record = self.static_store.get_static_data(symbol)
            if record:
                avg_adv = record.get('AVG_ADV')
                if avg_adv:
                    try:
                        return float(avg_adv)
                    except (ValueError, TypeError):
                        pass
        return 1000.0  # Default AVG_ADV
    
    def get_group_peers(self, group: str) -> List[str]:
        """Get all symbols in the same group"""
        if not self.static_store or not self.static_store.is_loaded():
            return []
        
        peers = []
        all_symbols = self.static_store.get_all_symbols()
        for symbol in all_symbols:
            record = self.static_store.get_static_data(symbol)
            if record and record.get('GROUP') == group:
                peers.append(symbol)
        
        return peers
    
    def process_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a decision helper job.
        
        Worker collects its own tick data from Hammer Pro and computes decision metrics.
        """
        job_id = job_data.get("job_id")
        symbols = job_data.get("symbols")  # None = all symbols
        windows = job_data.get("windows", ["5m", "15m", "30m"])  # Default windows
        
        logger.info(f"🔄 [{self.worker_name}] Processing job {job_id}")
        
        try:
            # Get symbols to process
            if symbols is None:
                symbols_to_process = self.get_all_symbols()
                logger.info(f"📊 [{self.worker_name}] Processing all {len(symbols_to_process)} symbols")
            else:
                symbols_to_process = symbols
                logger.info(f"📊 [{self.worker_name}] Processing {len(symbols_to_process)} specified symbols")
            
            if not symbols_to_process:
                logger.warning(f"⚠️ [{self.worker_name}] No symbols to process")
                return {
                    "success": False,
                    "job_id": job_id,
                    "error": "No symbols to process",
                    "data": {}
                }
            
            # Wait for bootstrap to collect some ticks
            logger.info(f"⏳ [{self.worker_name}] Waiting for initial tick collection...")
            
            # Wait up to 60 seconds for bootstrap to make progress
            max_wait = 60
            wait_interval = 2
            waited = 0
            
            while waited < max_wait:
                # Check if we have any ticks collected
                with self.decision_engine._tick_lock:
                    symbols_with_ticks = [s for s, ticks in self.decision_engine.tick_store.items() if len(ticks) > 0]
                    total_ticks = sum(len(ticks) for ticks in self.decision_engine.tick_store.values())
                
                if len(symbols_with_ticks) >= 10:  # At least 10 symbols with ticks
                    logger.info(f"📊 [{self.worker_name}] Found {len(symbols_with_ticks)} symbols with ticks ({total_ticks} total ticks)")
                    break
                
                time.sleep(wait_interval)
                waited += wait_interval
                
                if waited % 10 == 0:
                    logger.info(f"⏳ [{self.worker_name}] Still waiting for tick collection... ({waited}s/{max_wait}s)")
            
            # Final check
            with self.decision_engine._tick_lock:
                symbols_with_ticks = [s for s, ticks in self.decision_engine.tick_store.items() if len(ticks) > 0]
                total_ticks = sum(len(ticks) for ticks in self.decision_engine.tick_store.values())
            
            logger.info(f"📊 [{self.worker_name}] Starting processing with {len(symbols_with_ticks)} symbols having ticks ({total_ticks} total ticks)")
            
            # Process each symbol
            results = {}
            processed_count = 0
            
            for symbol in symbols_to_process:
                try:
                    # Check if symbol has tick data
                    with self.decision_engine._tick_lock:
                        has_ticks = symbol in self.decision_engine.tick_store and len(self.decision_engine.tick_store[symbol]) > 0
                        tick_count = len(self.decision_engine.tick_store.get(symbol, []))
                    
                    if not has_ticks:
                        # Skip symbols without tick data (bootstrap may still be running)
                        continue
                    
                    # Get symbol data
                    group = self.get_group_for_symbol(symbol)
                    avg_adv = self.get_avg_adv(symbol)
                    group_peers = self.get_group_peers(group) if group else []
                    
                    symbol_results = {}
                    
                    # Compute metrics for each window
                    for window_name in windows:
                        metrics = self.decision_engine.compute_metrics(
                            symbol=symbol,
                            window_name=window_name,
                            avg_adv=avg_adv,
                            group_peers=group_peers if len(group_peers) > 1 else None
                        )
                        
                        if metrics:
                            symbol_results[window_name] = metrics
                            
                            # Write to Redis
                            if group:
                                redis_key = f"{JOB_RESULT_PREFIX}{group}:{symbol}:{window_name}"
                            else:
                                redis_key = f"{JOB_RESULT_PREFIX}unknown:{symbol}:{window_name}"
                            
                            # Store result in Redis (1 hour TTL)
                            self.redis_client.setex(
                                redis_key,
                                3600,
                                json.dumps(metrics)
                            )
                    
                    if symbol_results:
                        results[symbol] = {
                            'symbol': symbol,
                            'group': group,
                            'windows': symbol_results,
                            'timestamp': datetime.now().isoformat()
                        }
                        processed_count += 1
                    else:
                        # Log why metrics weren't computed
                        logger.debug(f"⚠️ [{self.worker_name}] No metrics for {symbol} (tick_count={tick_count}, avg_adv={avg_adv})")
                
                except Exception as e:
                    logger.error(f"❌ Error processing symbol {symbol}: {e}", exc_info=True)
                    results[symbol] = {
                        'symbol': symbol,
                        'error': str(e)
                    }
            
            logger.info(f"✅ Job {job_id} completed: {processed_count}/{len(symbols_to_process)} symbols processed")
            
            return {
                "success": True,
                "job_id": job_id,
                "processed_count": processed_count,
                "total_symbols": len(symbols_to_process),
                "data": results,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error processing job {job_id}: {e}", exc_info=True)
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
            logger.info(f"📊 [{self.worker_name}] Polling Redis stream: {JOB_QUEUE_KEY}")
            
            # Main loop - poll Redis stream for jobs
            while self.running:
                try:
                    # Read from Redis stream (XREADGROUP)
                    # Note: Using simple LPOP for now (can be upgraded to streams later)
                    job_data_str = self.redis_client.lpop(JOB_QUEUE_KEY)
                    
                    if job_data_str:
                        try:
                            job_data = json.loads(job_data_str)
                            result = self.process_job(job_data)
                            
                            if result.get("success"):
                                self.processed_jobs += 1
                            else:
                                self.failed_jobs += 1
                            
                            logger.info(
                                f"✅ Job {job_data.get('job_id')} completed in "
                                f"{result.get('processed_count', 0)} symbols"
                            )
                        
                        except json.JSONDecodeError as e:
                            logger.error(f"❌ Invalid job data JSON: {e}")
                            self.failed_jobs += 1
                    
                    else:
                        # No job available, wait
                        time.sleep(POLL_TIMEOUT)
                
                except Exception as e:
                    logger.error(f"❌ Error in worker loop: {e}", exc_info=True)
                    time.sleep(POLL_TIMEOUT)
            
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
    worker = DecisionHelperWorker()
    
    # Handle SIGINT (Ctrl+C)
    def signal_handler(sig, frame):
        logger.info(f"🛑 [{worker.worker_name}] Received SIGINT, shutting down...")
        worker.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run worker
    worker.run()


if __name__ == "__main__":
    main()


