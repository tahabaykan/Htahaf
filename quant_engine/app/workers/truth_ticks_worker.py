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
    
    def initialize_services(self):
        """Initialize worker's own services"""
        try:
            logger.info(f"🔧 [{self.worker_name}] Initializing worker services...")
            
            # Log assigned symbols (User Request)
            if self.assigned_symbols:
                preview = list(self.assigned_symbols)[:5]
                count = len(self.assigned_symbols)
                logger.info(f"📌 [{self.worker_name}] Managing {count} symbols: {preview}...")
            
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
            
            # ════════════════════════════════════════════════════════════════
            # SAFETY NET: If NO symbols were assigned, auto-load ALL symbols
            # from static store. This prevents the critical bug where workers
            # 2-6 are not started and 334/466 symbols have no truth tick data.
            # ════════════════════════════════════════════════════════════════
            if not self.assigned_symbols and self.static_store and self.static_store.is_loaded():
                all_syms = self.static_store.get_all_symbols()
                if all_syms:
                    self.assigned_symbols = set(all_syms)
                    self.symbols_to_collect.update(all_syms)
                    logger.warning(
                        f"🔴 [{self.worker_name}] AUTO-LOADED ALL {len(all_syms)} symbols from static store! "
                        f"No --symbols/--config was provided. Worker will collect ALL symbols."
                    )
            
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
            
            # 5. Snapshot Scheduler Imports
            from app.market_data.snapshot_scheduler import SnapshotScheduler
            
            logger.info(f"⚙️ [{self.worker_name}] Initializing services...")
            
            # 1. Hammer Client
            self.hammer_client = HammerClient(
                host=settings.HAMMER_HOST,
                port=settings.HAMMER_PORT,
                password=settings.HAMMER_PASSWORD
            )
            # Add self as observer for connection status logging
            # self.hammer_client.add_observer(self._on_hammer_message)
            
            # Connect with retry — Hammer Pro often fails auth on first attempt
            # when many workers start simultaneously (backend + L1 + 6 workers)
            max_retries = 5
            connected = False
            for attempt in range(1, max_retries + 1):
                if self.hammer_client.connect():
                    connected = True
                    break
                wait = attempt * 10  # 10s, 20s, 30s, 40s, 50s
                logger.warning(f"⚠️ [{self.worker_name}] Hammer connect attempt {attempt}/{max_retries} failed, retrying in {wait}s...")
                time.sleep(wait)
            
            if not connected:
                logger.error(f"❌ [{self.worker_name}] Failed to connect to Hammer Pro after {max_retries} attempts")
                return False
            
            # 5. Tick Fetcher (Bootstrap & Active Polling)
            self.grpan_tick_fetcher = GRPANTickFetcher(
                hammer_client=self.hammer_client,
                trade_print_router=self.trade_print_router,
                grpan_engine=self.grpan_engine,
                last_few_ticks=150,   # ✅ FIXED: Was 2500 — caused 22min bootstrap (20s × 66 syms)
                                      # 150 ticks is enough for initial state, polling fills the rest
                polling_mode=True,    # ✅ CONTINUOUS POLLING ENABLED
                polling_interval=60.0 # ✅ Poll every 60 seconds
            )
            self.grpan_tick_fetcher.start()
            
            # Register assigned symbols with fetcher to start data collection
            if self.assigned_symbols:
                logger.info(f"📋 [{self.worker_name}] Registering {len(self.assigned_symbols)} symbols with Tick Fetcher")
                self.grpan_tick_fetcher.add_symbols(list(self.assigned_symbols))
            
            # 6. Snapshot Scheduler (For 1-min market data - L1 feed)
            if self.assigned_symbols:
                self.snapshot_scheduler = SnapshotScheduler(
                    worker_name=self.worker_name,
                    hammer_client=self.hammer_client,
                    redis_client=self.redis_client,
                    symbols=list(self.assigned_symbols),
                    interval_minutes=1  # Changed from 5 to 1 for faster L1 updates
                )
                self.snapshot_scheduler.start()
            
            # 6b. L1 Feed Loop (Continuous L1 updates to Redis - 30s interval)
            # This ensures market:l1:{symbol} is always fresh for RevnBookCheck and other terminals
            if self.assigned_symbols:
                self.start_l1_feed_loop()

            # 7. Analysis Scheduler (For continuous calculations)
            # This ensures 1H/4H/1D columns are populated even without external jobs
            self.start_analysis_scheduler()

            logger.info(f"✅ [{self.worker_name}] Services initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Failed to initialize services: {e}", exc_info=True)
            return False

    def start_l1_feed_loop(self):
        """Starts a background thread to continuously fetch L1 data and write to Redis"""
        def l1_feed_loop():
            logger.info(f"📊 [{self.worker_name}] L1 Feed Loop started (Interval: 30s, {len(self.assigned_symbols)} symbols)")
            interval = 30  # 30 seconds
            
            while self.running:
                try:
                    if not self.hammer_client or not self.hammer_client.is_connected():
                        logger.warning(f"⚠️ [{self.worker_name}] Hammer not connected, skipping L1 feed cycle")
                        time.sleep(10)
                        continue
                    
                    cycle_start = time.time()
                    updated = 0
                    errors = 0
                    pipeline = self.redis_client.pipeline()
                    
                    for symbol in self.assigned_symbols:
                        if not self.running:
                            break
                        
                        try:
                            # Fetch snapshot from Hammer (lightweight, just bid/ask/last)
                            snapshot = self.hammer_client.get_symbol_snapshot(symbol, use_cache=False)
                            
                            if snapshot:
                                bid = snapshot.get('bid', 0.0) or 0.0
                                ask = snapshot.get('ask', 0.0) or 0.0
                                last = snapshot.get('last', 0.0) or 0.0
                                
                                # Calculate spread
                                spread = 0.0
                                if bid > 0 and ask > 0 and ask > bid:
                                    spread = round(ask - bid, 4)
                                
                                l1_data = {
                                    'bid': bid,
                                    'ask': ask,
                                    'spread': spread,
                                    'last': last,
                                    'ts': time.time()
                                }
                                
                                l1_json = json.dumps(l1_data)
                                
                                # 🔑 TICKER CONVENTION: Write BOTH Hammer and PREF_IBKR keys
                                # so ALL consumers can find L1 data regardless of format.
                                # Hammer format (WBS-F) is the canonical key for market data.
                                from app.live.symbol_mapper import SymbolMapper
                                hammer_sym = SymbolMapper.to_hammer_symbol(symbol)
                                
                                # Primary key: Hammer format (canonical for market data)
                                pipeline.setex(f"market:l1:{hammer_sym}", 120, l1_json)
                                
                                # Secondary key: PREF_IBKR format (for backward compat)
                                if hammer_sym != symbol:
                                    pipeline.setex(f"market:l1:{symbol}", 120, l1_json)
                                
                                updated += 1
                                
                                # Small delay to avoid overwhelming Hammer
                                time.sleep(0.01)
                                
                        except Exception as e:
                            errors += 1
                            if errors <= 5:  # Only log first 5 errors
                                logger.debug(f"[{self.worker_name}] L1 feed error for {symbol}: {e}")
                    
                    # Execute pipeline
                    try:
                        pipeline.execute()
                        cycle_time = time.time() - cycle_start
                        logger.debug(
                            f"📊 [{self.worker_name}] L1 Feed Cycle: "
                            f"Updated {updated}/{len(self.assigned_symbols)} symbols in {cycle_time:.1f}s"
                        )
                    except Exception as e:
                        logger.error(f"❌ [{self.worker_name}] Redis pipeline error: {e}")
                    
                    # Wait for next cycle
                    elapsed = time.time() - cycle_start
                    sleep_time = max(1, interval - elapsed)
                    time.sleep(sleep_time)
                    
                except Exception as e:
                    logger.error(f"❌ [{self.worker_name}] L1 feed loop error: {e}", exc_info=True)
                    time.sleep(10)
        
        t = threading.Thread(target=l1_feed_loop, daemon=True, name=f"{self.worker_name}_l1_feed")
        t.start()
    
    def start_analysis_scheduler(self):
        """Starts a background thread to run analysis periodically"""
        def analysis_loop():
            logger.info(f"🔄 [{self.worker_name}] Analysis Scheduler started (Interval: 1m)")
            cycle_count = 0
            while self.running:
                try:
                    cycle_count += 1
                    
                    # Run analysis for all assigned symbols
                    # Passing None as job_data triggers 'process all assigned' logic
                    job_data = {"job_id": "auto_analysis", "symbols": None}
                    result = self.process_job(job_data)
                    
                    # CRITICAL: Save this result to Redis so Analysis Panels can find it
                    if result and result.get('success'):
                        # Save as 'truth_ticks:auto_analysis' (fixed key for UI)
                        self.redis_client.setex(
                            "truth_ticks:auto_analysis",
                            300, # 5 min TTL
                            json.dumps(result)
                        )
                        # Heartbeat log every 5 cycles (5 min)
                        if cycle_count % 5 == 0:
                            logger.info(
                                f"💓 [{self.worker_name}] Heartbeat: cycle={cycle_count}, "
                                f"processed={result.get('processed_count')}/{result.get('total_count')} symbols, "
                                f"tick_store={len(self.truth_ticks_engine.tick_store) if self.truth_ticks_engine else 0}"
                            )
                    
                    time.sleep(60) # Run every minute
                except Exception as e:
                    logger.error(f"❌ [{self.worker_name}] Error in analysis loop (will retry): {e}", exc_info=True)
                    time.sleep(10)

        t = threading.Thread(target=analysis_loop, daemon=True)
        t.start()
            
    def cleanup(self):
        """Cleanup resources"""
        try:
            self.running = False
            
            if hasattr(self, 'snapshot_scheduler') and self.snapshot_scheduler:
                self.snapshot_scheduler.stop()
                
            if self.grpan_tick_fetcher:
                self.grpan_tick_fetcher.stop()
                logger.info(f"✅ [{self.worker_name}] GRPANTickFetcher stopped")
            
            if self.hammer_client:
                self.hammer_client.disconnect()
                logger.info(f"✅ [{self.worker_name}] Hammer client disconnected")
            
            logger.info(f"✅ [{self.worker_name}] Worker cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error during cleanup: {e}", exc_info=True)

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
        requested_symbols = job_data.get("symbols")  # None = all symbols
        
        # logger.info(f"🔄 [{self.worker_name}] Processing job {job_id}") # Log less to avoid spam
        
        try:
            # Determine universe of symbols this worker is responsible for
            if self.assigned_symbols:
                my_universe = list(self.assigned_symbols)
                # logger.debug(f"🔍 [{self.worker_name}] Worker restricted to {len(my_universe)} assigned symbols")
            elif self.static_store and self.static_store.is_loaded():
                my_universe = self.static_store.get_all_symbols()
            else:
                my_universe = self.truth_ticks_engine.get_all_symbols()
            
            # Intersect requested symbols with my universe
            if requested_symbols is None:
                # User asked for ALL, so I do ALL of MINE
                symbols_to_process = my_universe
                # logger.info(f"📊 [{self.worker_name}] Processing ALL assigned symbols: {len(symbols_to_process)}")
            else:
                # User asked for specific list, I only do ones that are MINE
                symbols_to_process = [s for s in requested_symbols if s in my_universe]
                # logger.info(f"📊 [{self.worker_name}] Processing {len(symbols_to_process)} symbols")
            
            if not symbols_to_process:
                return { "success": True, "count": 0 }
            
            # Add symbols to GRPANTickFetcher (bootstrap if needed)
            # Only if we are running the fetcher (which we are)
            new_symbols = []
            with self._symbols_lock:
                new_symbols = [s for s in symbols_to_process if s not in self.symbols_to_collect]
                if new_symbols:
                    self.grpan_tick_fetcher.add_symbols(new_symbols, bootstrap=True)
                    self.symbols_to_collect.update(new_symbols)
                    logger.info(f"📊 [{self.worker_name}] Added {len(new_symbols)} new symbols to tick fetcher")
            
            # Fixed timeframes (explicit in code as per requirements)
            TIMEFRAMES = {
                '1h': 60 * 60,
                '4h': 4 * 60 * 60,
                '1d': 24 * 60 * 60,
                '2d': 2 * 24 * 60 * 60
            }
            # Note: TruthTicksEngine uses minutes internally usually, verifying engine code...
            # Actually TruthTicksEngine expecting 'TF_1H' format or minutes?
            # Let's check TruthTicksEngine usage in original file.
            # Original code had: TIMEFRAMES = {'TF_4H': ...}
            # GemEngine expects: '1h', '4h'.
            # I should align them. Let's use the keys GemEngine expects.
            
            results = {}
            processed_count = 0
            
            for symbol in symbols_to_process:
                try:
                    # Get AVG_ADV
                    avg_adv = 0.0
                    if self.static_store:
                        record = self.static_store.get_static_data(symbol)
                        if record:
                            avg_adv = float(record.get('AVG_ADV', 0) or 0)
                    
                    if avg_adv <= 0:
                        continue
                    
                    symbol_timeframes = {}
                    has_any_timeframe = False
                    
                    # GemEngine keys: 1h, 4h, 1d, 2d. TruthTicksEngine keys: TF_1H, TF_4H...
                    # We need to map or check what engine supports.
                    # Assuming engine supports generic seconds/minutes/names.
                    
                    # Using Gem friendly keys
                    target_tfs = ['1h', '4h', '1d', '2d']
                    
                    # Get ALL data from engine in one go if possible, or loop
                    # TruthTicksEngine.compute_metrics_for_timeframe(symbol, avg_adv, tf_name)
                    # We will use 'TF_' prefix for Engine compatibility if needed, but save as '1h' etc.
                    
                    for tf in target_tfs:
                        # Map to Engine TF name if necessary
                        engine_tf = f"TF_{tf.upper()}" 
                        
                        try:
                            metrics = self.truth_ticks_engine.compute_metrics_for_timeframe(
                                symbol, avg_adv, engine_tf
                            )
                            if metrics:
                                # Clean metrics for Gem consumption
                                symbol_timeframes[tf] = metrics
                                # ALSO save with TF_ prefix for legacy API compatibility
                                symbol_timeframes[engine_tf] = metrics
                                has_any_timeframe = True
                        except Exception:
                            continue
                    
                    if has_any_timeframe:
                        results[symbol] = symbol_timeframes
                        processed_count += 1
                        
                        # Cache inspect data for Gem Engine
                        inspect_data = self.truth_ticks_engine.get_inspect_data(symbol, avg_adv)
                        if inspect_data:
                            # DO NOT overwrite temporal_analysis with symbol_timeframes
                            # The engine's get_inspect_data now calculates this correctly (in cents)
                            # inspect_data['temporal_analysis'] = symbol_timeframes
                            
                            inspect_key = f"truth_ticks:inspect:{symbol}"
                            self.redis_client.setex(
                                inspect_key,
                                3600,
                                json.dumps({"success": True, "symbol": symbol, "data": inspect_data})
                            )
                            # Write latest truth tick for RevnBookCheck/Frontlama (truthtick:latest:{symbol})
                            path_dataset = inspect_data.get("path_dataset") or []
                            if path_dataset:
                                last_tick = path_dataset[-1]
                                latest_payload = {
                                    "price": last_tick.get("price"),
                                    "ts": last_tick.get("timestamp"),       # Market tick time (can be old for illiquid stocks)
                                    "updated_at": time.time(),              # When worker last refreshed (use THIS for staleness)
                                    "size": last_tick.get("size"),
                                    "venue": last_tick.get("venue", ""),
                                    "exch": last_tick.get("venue", ""),
                                }
                                self.redis_client.setex(
                                    f"truthtick:latest:{symbol}",
                                    600,  # 10 min TTL (analysis runs every 60s, so this is safe)
                                    json.dumps(latest_payload),
                                )
                            
                except Exception as e:
                    logger.error(f"❌ [{self.worker_name}] Error processing {symbol}: {e}", exc_info=True)
                    continue
            
            if processed_count > 0:
                logger.info(f"✅ [{self.worker_name}] Analyzed {processed_count}/{len(symbols_to_process)} symbols")
            
            return {
                "success": True,
                "job_id": job_id,
                "processed_count": processed_count,
                "total_count": len(symbols_to_process),
                "data": results,
                "updated_at": datetime.now().isoformat(),
                "worker": self.worker_name
            }
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error processing job {job_id}: {e}", exc_info=True)
            return {
                "success": False,
                "job_id": job_id,
                "error": str(e),
                "data": {}
            }

    def __init__(self, worker_name: str = None, assigned_symbols: List[str] = None):
        self.worker_name = worker_name or WORKER_NAME
        self.assigned_symbols = set(assigned_symbols) if assigned_symbols else set()
        
        self.redis_client = None
        self.running = False
        self.processed_jobs = 0
        self.failed_jobs = 0
        self.start_time = None
        
        # Services
        self.hammer_client: Optional[HammerClient] = None
        self.truth_ticks_engine = None
        self.grpan_engine = None
        self.trade_print_router = None
        self.grpan_tick_fetcher = None
        self.static_store = None
        self.snapshot_scheduler = None
        
        self.symbols_to_collect: Set[str] = set()
        if self.assigned_symbols:
            logger.info(f"📌 [{self.worker_name}] Initialized with SHARD: {len(self.assigned_symbols)} symbols assigned")
            # Pre-populate symbols to collect
            self.symbols_to_collect.update(self.assigned_symbols)
        else:
            logger.warning(f"⚠️ [{self.worker_name}] No symbols assigned! Will auto-load ALL symbols from static store after initialization.")
            
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
            
            logger.info(f"✅ [{self.worker_name}] Connected to Redis")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            return False
            
    def run(self):
        """Run the worker loop"""
        self.running = True
        self.start_time = datetime.now()
        
        logger.info(f"🚀 [{self.worker_name}] Starting Truth Ticks Worker...")
        
        # 1. Connect to Redis (required for job queue)
        if not self.connect_redis():
            logger.error("❌ Failed to connect to Redis. Exiting.")
            return

        # 2. Initialize Logic Services (Hammer, Engines, etc.)
        # IMPORTANT: Pass redis_client IS NOW AVAILABLE
        if not self.initialize_services():
            logger.error("❌ Failed to initialize services. Exiting.")
            return

        logger.info(f"✅ [{self.worker_name}] Ready to process jobs from stream: {STREAM_NAME}")
        
        # Create consumer group if not exists
        try:
            self.redis_client.xgroup_create(STREAM_NAME, "truth_ticks_workers", id="$", mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"Error creating generic consumer group: {e}")

        # Main Loop
        while self.running:
            try:
                # Use Consumer Group to read jobs
                # > means "messages never delivered to other consumers"
                entries = self.redis_client.xreadgroup(
                    "truth_ticks_workers",
                    self.worker_name,
                    {STREAM_NAME: ">"},
                    count=1,
                    block=POLL_TIMEOUT * 1000
                )
                
                if entries:
                    for stream, messages in entries:
                        for message_id, job_data in messages:
                            # Acknowledge immediately (at-most-once for simplicity, or process then ack)
                            self.redis_client.xack(STREAM_NAME, "truth_ticks_workers", message_id)
                            
                            logger.info(f"📥 [{self.worker_name}] Received job {message_id}")
                            
                            # Parse job data
                            try:
                                # Stream data comes as {b'data': b'{...}'} or {'data': '{...}'}
                                raw_data = job_data.get('data') or job_data.get(b'data')
                                if not raw_data:
                                    logger.warning(f"⚠️ [{self.worker_name}] Received empty job data in message {message_id}")
                                    continue
                                    
                                if isinstance(raw_data, bytes):
                                    raw_data = raw_data.decode('utf-8')
                                
                                parsed_job = json.loads(raw_data)
                                
                                # Process
                                result = self.process_job(parsed_job)
                            except Exception as e:
                                logger.error(f"❌ [{self.worker_name}] Error parsing job {message_id}: {e}")
                                continue
                            
                            # Store result
                            result_key = f"{JOB_RESULT_PREFIX}{result['job_id']}"
                            self.redis_client.setex(result_key, 3600, json.dumps(result))
                            
                            self.processed_jobs += 1
                
                # Maintenance / Heartbit could go here
                
            except Exception as e:
                logger.error(f"❌ [{self.worker_name}] Error in main loop: {e}", exc_info=True)
                self.failed_jobs += 1
                time.sleep(1)
        
        self.cleanup()

def main():
    """Main entry point"""
    import argparse
    import signal
    
    parser = argparse.ArgumentParser(description="Truth Ticks Worker")
    parser.add_argument("--name", type=str, help="Worker name", default=None)
    parser.add_argument("--symbols", type=str, help="Comma-separated list of symbols to assign to this worker")
    parser.add_argument("--config", type=str, help="Path to JSON config file containing 'symbols' list")
    
    args = parser.parse_args()
    
    assigned_symbols = []
    
    if args.symbols:
        assigned_symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
    elif args.config and os.path.exists(args.config):
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
                if isinstance(config, list):
                    assigned_symbols = config
                elif isinstance(config, dict) and 'symbols' in config:
                    assigned_symbols = config['symbols']
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            sys.exit(1)
            
    worker_name = args.name or f"worker_{os.getpid()}"
    
    # Initialize worker
    worker = TruthTicksWorker(worker_name=worker_name, assigned_symbols=assigned_symbols)
    
    # Handle SIGINT (Ctrl+C)
    def signal_handler(sig, frame):
        logger.info(f"🛑 [{worker.worker_name}] Received SIGINT, shutting down...")
        worker.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run worker
    worker.run()


if __name__ == "__main__":
    main()

