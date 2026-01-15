"""
Deeper Analysis Worker

Processes deeper analysis jobs from Redis queue.
Computes GOD, ROD, GRPAN metrics for all symbols using tick-by-tick data.

🔵 CRITICAL: This worker runs in a SEPARATE process/terminal to avoid blocking the main application.
Worker has its own Hammer Pro connection and trade print collection - backend is NOT blocked.

Multiple worker instances can run simultaneously for load distribution.
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

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

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
from app.core.data_fabric import get_data_fabric
from app.core.redis_client import get_redis_client
from app.config.settings import settings
from app.market_data.grpan_engine import get_grpan_engine
from app.market_data.rwvap_engine import get_rwvap_engine
from app.market_data.trade_print_router import TradePrintRouter
from app.market_data.grpan_tick_fetcher import GRPANTickFetcher
from app.market_data.static_data_store import get_static_store
from app.live.hammer_client import HammerClient


# Redis keys (must match deeper_analysis_routes.py)
JOB_QUEUE_KEY = "deeper_analysis:jobs"
JOB_STATUS_PREFIX = "deeper_analysis:status:"
JOB_RESULT_PREFIX = "deeper_analysis:result:"

# Worker configuration
WORKER_NAME = os.getenv("WORKER_NAME", f"worker_{os.getpid()}")
POLL_TIMEOUT = int(os.getenv("POLL_TIMEOUT", "5"))  # seconds
MAX_JOB_TIME = int(os.getenv("MAX_JOB_TIME", "300"))  # 5 minutes max per job


class DeeperAnalysisWorker:
    """
    Worker that processes deeper analysis jobs from Redis queue.
    
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
        self.grpan_engine = None
        self.rwvap_engine = None
        self.trade_print_router = None
        self.grpan_tick_fetcher = None
        self.static_store = None
        self.fabric = None
        
        # Track symbols we're collecting data for
        self.symbols_to_collect: Set[str] = set()
        self._symbols_lock = threading.Lock()
    
    def calculate_srpan(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Calculate SRPAN (Spread Real Print Analyzer) for a symbol.
        
        Finds two price concentration points (G1 and G2) from last 30 ticks
        and calculates spread quality score.
        
        SRPAN Rules:
        ============
        1. Data Collection:
           - Use last 30 filtered ticks (size > 9 lots)
           - Minimum 8 ticks required for calculation
        
        2. Weighting:
           - 100/200/300 lot = 1.00 weight
           - Other sizes = 0.25 weight
        
        3. GRPAN1 (Primary Concentration):
           - Highest weighted price
           - Concentration = ±0.03¢ range weight / total weight
        
        4. GRPAN2 (Secondary Concentration):
           - Must be at least 0.06¢ away from GRPAN1
           - Highest weighted price in excluded set
           - Concentration = ±0.03¢ range weight / total weight
        
        5. Spread Score Calculation:
           - Minimum spread: 0.06¢ (score = 0)
           - Optimal spread: ≥0.30¢ (score = 100)
           - Linear interpolation between 0.06¢ and 0.30¢
        
        6. SRPAN Score (0-100):
           - Balance Score (60%): Minimize G1-G2 concentration difference
           - Total Score (15%): Maximize G1+G2 total concentration
           - Spread Score (25%): Evaluate spread width (0.06¢ min, 0.30¢ optimal)
        
        Returns:
            Dict with srpan_score, grpan1, grpan1_conf, grpan2, grpan2_conf, spread, etc.
        """
        try:
            # Get last 30 ticks from extended_prints_store
            if not hasattr(self.grpan_engine, 'extended_prints_store'):
                logger.debug(f"🔍 [SRPAN] {symbol}: extended_prints_store not available")
                return None
            
            symbol_prints = self.grpan_engine.extended_prints_store.get(symbol)
            if not symbol_prints:
                logger.debug(f"🔍 [SRPAN] {symbol}: No prints in extended_prints_store")
                return None
            
            if len(symbol_prints) < 8:
                logger.debug(f"🔍 [SRPAN] {symbol}: Only {len(symbol_prints)} prints (need at least 8)")
                return None
            
            # Convert to list and filter (9 lot altı ignore)
            all_prints = list(symbol_prints)
            filtered_prints = [p for p in all_prints if p.get('size', 0) > 9]
            
            # Get last 30 ticks
            last_30_prints = filtered_prints[-30:] if len(filtered_prints) >= 30 else filtered_prints
            
            if len(last_30_prints) < 8:
                logger.debug(f"🔍 [SRPAN] {symbol}: Only {len(last_30_prints)} filtered prints (need at least 8)")
                return None
            
            # Calculate weighted price frequency
            price_weights = defaultdict(float)
            
            for print_data in last_30_prints:
                price = print_data.get('price', 0)
                size = print_data.get('size', 0)
                
                if price > 0:
                    price = round(float(price), 2)
                    
                    # Weight: 100/200/300 lot = 1.00, others = 0.25
                    if size in [100, 200, 300]:
                        weight = 1.00
                    else:
                        weight = 0.25
                    
                    price_weights[price] += weight
            
            if len(price_weights) < 2:
                return None
            
            # Total weight
            total_weight = sum(price_weights.values())
            
            # 1. Find GRPAN1 (primary concentration)
            grpan1 = max(price_weights.keys(), key=lambda p: price_weights[p])
            
            # GRPAN1 ±0.03 range weight (changed from ±0.04)
            grpan1_range_min = grpan1 - 0.03
            grpan1_range_max = grpan1 + 0.03
            grpan1_range_weight = sum(
                w for p, w in price_weights.items() 
                if grpan1_range_min <= p <= grpan1_range_max
            )
            grpan1_conf = (grpan1_range_weight / total_weight) * 100 if total_weight > 0 else 0
            
            # 2. Find GRPAN2 (secondary concentration, at least 0.06¢ away, changed from 0.08¢)
            excluded_prices = {
                p: w for p, w in price_weights.items() 
                if abs(p - grpan1) >= 0.06
            }
            
            if not excluded_prices:
                # No secondary concentration found
                return {
                    'grpan1': grpan1,
                    'grpan1_conf': grpan1_conf,
                    'grpan2': None,
                    'grpan2_conf': 0,
                    'spread': 0,
                    'direction': 'N/A',
                    'balance_score': 0,
                    'total_score': 0,
                    'spread_score': 0,
                    'srpan_score': 0
                }
            
            # GRPAN2 = highest weighted price in excluded set
            grpan2 = max(excluded_prices.keys(), key=lambda p: excluded_prices[p])
            
            # GRPAN2 ±0.03 range weight (changed from ±0.04)
            grpan2_range_min = grpan2 - 0.03
            grpan2_range_max = grpan2 + 0.03
            grpan2_range_weight = sum(
                w for p, w in price_weights.items() 
                if grpan2_range_min <= p <= grpan2_range_max 
                and abs(p - grpan1) >= 0.06  # Changed from 0.08
            )
            grpan2_conf = (grpan2_range_weight / total_weight) * 100 if total_weight > 0 else 0
            
            # Calculate spread
            spread = abs(grpan2 - grpan1)
            direction = 'UP' if grpan2 > grpan1 else 'DOWN'
            
            # ============ SRPAN SCORE CALCULATION ============
            # 1. Balance Score (60% weight): G1-G2 difference should be minimal
            conf_diff = abs(grpan1_conf - grpan2_conf)
            balance_score = max(0, 100 - conf_diff)
            
            # 2. Total Score (15% weight): G1+G2 should be close to 100
            total_conf = grpan1_conf + grpan2_conf
            total_score = min(100, total_conf)
            
            # 3. Spread Score (25% weight): Spread should be wide enough
            # Minimum spread changed from 0.08¢ to 0.06¢
            if spread >= 0.30:
                spread_score = 100
            elif spread <= 0.06:  # Changed from 0.08
                spread_score = 0
            else:
                # Linear interpolation: 0.06 → 0, 0.30 → 100 (changed from 0.08 → 0)
                spread_score = ((spread - 0.06) / (0.30 - 0.06)) * 100
            
            # Composite SRPAN score
            srpan_score = (0.60 * balance_score) + (0.15 * total_score) + (0.25 * spread_score)
            
            return {
                'grpan1': grpan1,
                'grpan1_conf': grpan1_conf,
                'grpan2': grpan2,
                'grpan2_conf': grpan2_conf,
                'spread': spread,
                'direction': direction,
                'balance_score': balance_score,
                'total_score': total_score,
                'spread_score': spread_score,
                'srpan_score': srpan_score
            }
            
        except Exception as e:
            logger.error(f"❌ Error calculating SRPAN for {symbol}: {e}", exc_info=True)
            return None
        
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
        """Initialize worker's own services (Hammer, GRPAN, RWVAP, etc.)"""
        try:
            logger.info(f"🔧 [{self.worker_name}] Initializing worker services...")
            
            # Get DataFabric
            self.fabric = get_data_fabric()
            if not self.fabric:
                raise Exception("DataFabric not available")
            
            # Enable tick-by-tick collection in worker
            if not self.fabric.is_tick_by_tick_enabled():
                logger.info(f"🔵 [{self.worker_name}] Enabling tick-by-tick collection")
                self.fabric.enable_tick_by_tick(True)
            
            # Get static store (for AVG_ADV, etc.)
            self.static_store = get_static_store()
            if not self.static_store:
                logger.warning(f"⚠️ [{self.worker_name}] Static store not available - RWVAP extreme volume filter may not work")
            elif not self.static_store.is_loaded():
                # Try to load static store
                try:
                    csv_path = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                        "janall", "janalldata.csv"
                    )
                    if os.path.exists(csv_path):
                        self.static_store.load_csv(csv_path)
                        logger.info(f"✅ [{self.worker_name}] Static store loaded from {csv_path}")
                    else:
                        logger.warning(f"⚠️ [{self.worker_name}] CSV file not found at {csv_path}")
                except Exception as e:
                    logger.warning(f"⚠️ [{self.worker_name}] Failed to load static store: {e}")
            
            # Initialize GRPAN engine (worker creates its own instance)
            from app.market_data.grpan_engine import initialize_grpan_engine
            self.grpan_engine = initialize_grpan_engine()
            if not self.grpan_engine:
                raise Exception("GRPANEngine not available")
            
            # Start GRPAN compute loop
            self.grpan_engine.start_compute_loop()
            logger.info(f"✅ [{self.worker_name}] GRPANEngine initialized and compute loop started")
            
            # Initialize RWVAP engine (worker creates its own instance)
            from app.market_data.rwvap_engine import initialize_rwvap_engine
            self.rwvap_engine = initialize_rwvap_engine(
                extended_prints_store=self.grpan_engine.extended_prints_store,
                static_store=self.static_store,
                extreme_multiplier=1.0  # AVG_ADV * 1.0 threshold
            )
            if not self.rwvap_engine:
                raise Exception("RWVAPEngine not available")
            
            # Set RWVAP engine's last_price_cache (from GRPAN)
            self.rwvap_engine.set_last_price_cache(self.grpan_engine.last_price_cache)
            logger.info(f"✅ [{self.worker_name}] RWVAPEngine initialized")
            
            # Set RWVAP engine's extended_prints_store (shared with GRPAN)
            if hasattr(self.grpan_engine, 'extended_prints_store'):
                self.rwvap_engine.set_extended_prints_store(self.grpan_engine.extended_prints_store)
            
            # Set RWVAP engine's static store (for AVG_ADV)
            if self.static_store:
                self.rwvap_engine.set_static_store(self.static_store)
            
            # Set RWVAP engine's last_price_cache (from GRPAN)
            if hasattr(self.grpan_engine, 'last_price_cache'):
                self.rwvap_engine.set_last_price_cache(self.grpan_engine.last_price_cache)
            
            # Initialize TradePrintRouter
            self.trade_print_router = TradePrintRouter(self.grpan_engine)
            
            # Initialize Hammer Client (worker's own connection)
            self.hammer_client = HammerClient(
                host=settings.HAMMER_HOST,
                port=settings.HAMMER_PORT,
                password=settings.HAMMER_PASSWORD
            )
            
            # Connect to Hammer Pro
            if not self.hammer_client.connect():
                logger.error(f"❌ [{self.worker_name}] Failed to connect to Hammer Pro")
                logger.error(f"   Host: {settings.HAMMER_HOST}:{settings.HAMMER_PORT}")
                logger.error(f"   Password: {'SET' if settings.HAMMER_PASSWORD else 'NOT SET'}")
                raise Exception("Hammer Pro connection failed")
            
            logger.info(f"✅ [{self.worker_name}] Connected to Hammer Pro: {settings.HAMMER_HOST}:{settings.HAMMER_PORT}")
            
            # Initialize GRPANTickFetcher (bootstrap/recovery mode)
            self.grpan_tick_fetcher = GRPANTickFetcher(
                hammer_client=self.hammer_client,
                trade_print_router=self.trade_print_router,
                grpan_engine=self.grpan_engine,
                last_few_ticks=150,  # Extended buffer for rolling windows
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
    
    def get_all_symbols(self) -> List[str]:
        """Get all symbols from static store"""
        if self.static_store and self.static_store.is_loaded():
            return self.static_store.get_all_symbols()
        
        # Fallback: try to get from main app API
        if REQUESTS_AVAILABLE:
            try:
                api_url = "http://localhost:8000/api/market-data/merged"
                response = requests.get(api_url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("data"):
                        symbols = [record.get('PREF_IBKR') for record in data.get("data", [])]
                        symbols = [s for s in symbols if s]  # Filter None
                        return symbols
            except Exception as e:
                logger.warning(f"⚠️ Failed to get symbols from main app API: {e}")
        
        return []
    
    def process_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a deeper analysis job.
        
        Worker collects its own trade prints from Hammer Pro and computes GOD, ROD, GRPAN.
        Backend is NOT involved - all work happens in worker process.
        """
        job_id = job_data.get("job_id")
        symbols = job_data.get("symbols")  # None = all symbols
        
        logger.info(f"🔄 [{self.worker_name}] Processing job {job_id}")
        
        try:
            # Get symbols to process
            if symbols is None:
                # Process all symbols
                symbols_to_process = self.get_all_symbols()
                logger.info(f"📊 [{self.worker_name}] Processing all {len(symbols_to_process)} symbols")
            else:
                # Process only specified symbols
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
            
            # Now compute GOD, ROD, GRPAN for each symbol
            results = {}
            processed_count = 0
            
            for symbol in symbols_to_process:
                try:
                    # Get GRPAN windows
                    grpan_all_windows = self.grpan_engine.get_all_windows_for_symbol(symbol) or {}
                    
                    # Get RWVAP windows
                    rwvap_all_windows = self.rwvap_engine.get_all_rwvap_for_symbol(symbol) or {}
                    
                    # Calculate GOD (GRPAN ORT DEV)
                    god = None
                    grpan_price = None
                    window_names = ['pan_10m', 'pan_30m', 'pan_1h', 'pan_3h', 'pan_1d', 'pan_3d']
                    valid_grpan_prices = []
                    for window_name in window_names:
                        window_data = grpan_all_windows.get(window_name, {})
                        grpan_price_val = window_data.get('grpan_price')
                        if grpan_price_val is not None and isinstance(grpan_price_val, (int, float)):
                            if not (grpan_price_val != grpan_price_val or grpan_price_val == float('inf') or grpan_price_val == float('-inf')):
                                valid_grpan_prices.append(float(grpan_price_val))
                    
                    # Get last price from GRPAN engine's cache
                    last_price = self.grpan_engine.last_price_cache.get(symbol)
                    
                    if valid_grpan_prices and last_price:
                        grpan_ort = sum(valid_grpan_prices) / len(valid_grpan_prices)
                        god = float(last_price) - grpan_ort
                    
                    # Get latest GRPAN price
                    latest_pan = grpan_all_windows.get('latest_pan', {})
                    grpan_price = latest_pan.get('grpan_price')
                    
                    # Calculate ROD (RWVAP ORT DEV)
                    rod = None
                    rwvap_window_names = ['rwvap_1d', 'rwvap_3d', 'rwvap_5d']
                    valid_rwvap_prices = []
                    for window_name in rwvap_window_names:
                        window_data = rwvap_all_windows.get(window_name, {})
                        rwvap_price = window_data.get('rwvap') or window_data.get('rwvap_price')
                        if rwvap_price is not None and isinstance(rwvap_price, (int, float)):
                            if not (rwvap_price != rwvap_price or rwvap_price == float('inf') or rwvap_price == float('-inf')):
                                valid_rwvap_prices.append(float(rwvap_price))
                    
                    if valid_rwvap_prices and last_price:
                        rwvap_ort = sum(valid_rwvap_prices) / len(valid_rwvap_prices)
                        rod = float(last_price) - rwvap_ort
                    
                    # Get tick count from extended_prints_store
                    tick_count = 0
                    if hasattr(self.grpan_engine, 'extended_prints_store'):
                        symbol_prints = self.grpan_engine.extended_prints_store.get(symbol)
                        if symbol_prints:
                            tick_count = len(symbol_prints)
                    
                    # Calculate SRPAN (Spread Real Print Analyzer)
                    srpan_data = None
                    try:
                        srpan_data = self.calculate_srpan(symbol)
                    except Exception as e:
                        logger.warning(f"⚠️ [{self.worker_name}] Failed to calculate SRPAN for {symbol}: {e}")
                        srpan_data = None
                    
                    # Debug: Log first few symbols
                    if processed_count < 3:
                        logger.info(f"🔍 [DEBUG] Symbol {symbol}: god={god}, rod={rod}, grpan={grpan_price}, tick_count={tick_count}")
                        if srpan_data and srpan_data.get('srpan_score') is not None:
                            logger.info(f"🔍 [DEBUG] Symbol {symbol}: SRPAN={srpan_data.get('srpan_score', 0):.1f}, G1={srpan_data.get('grpan1')}, G2={srpan_data.get('grpan2')}, Spread={srpan_data.get('spread', 0):.2f}")
                        else:
                            logger.info(f"🔍 [DEBUG] Symbol {symbol}: SRPAN calculation returned None or no data")
                    
                    # Build result
                    result = {
                        'symbol': symbol,
                        'god': god,
                        'rod': rod,
                        'grpan': {
                            'value': grpan_price,
                            'all_windows': grpan_all_windows
                        },
                        'rwvap': rwvap_all_windows,
                        'tick_count': tick_count,
                        'last_price': last_price,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # Add SRPAN data if available
                    if srpan_data:
                        result['srpan'] = srpan_data
                    else:
                        result['srpan'] = {
                            'srpan_score': 0,
                            'grpan1': None,
                            'grpan1_conf': 0,
                            'grpan2': None,
                            'grpan2_conf': 0,
                            'spread': 0,
                            'direction': 'N/A'
                        }
                    
                    results[symbol] = result
                    
                    processed_count += 1
                    
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
    
    def update_status(self, job_id: str, status: str, message: str = None, error: str = None):
        """Update job status in Redis"""
        if not self.redis_client:
            return
        
        try:
            status_data = {
                "status": status,
                "message": message or f"Job {status}",
                "worker": self.worker_name,
                "timestamp": datetime.now().isoformat()
            }
            
            if error:
                status_data["error"] = error
            
            self.redis_client.setex(
                f"{JOB_STATUS_PREFIX}{job_id}",
                3600,  # 1 hour TTL
                json.dumps(status_data)
            )
        except Exception as e:
            logger.error(f"Failed to update status for job {job_id}: {e}")
    
    def save_result(self, job_id: str, result: Dict[str, Any]):
        """Save job result to Redis"""
        if not self.redis_client:
            return
        
        try:
            self.redis_client.setex(
                f"{JOB_RESULT_PREFIX}{job_id}",
                7200,  # 2 hours TTL
                json.dumps(result)
            )
        except Exception as e:
            logger.error(f"Failed to save result for job {job_id}: {e}")
    
    def cleanup(self):
        """Cleanup worker resources"""
        try:
            if self.grpan_tick_fetcher:
                self.grpan_tick_fetcher.stop()
                logger.info(f"🛑 [{self.worker_name}] GRPANTickFetcher stopped")
            
            if self.hammer_client:
                self.hammer_client.disconnect()
                logger.info(f"🛑 [{self.worker_name}] Hammer Pro disconnected")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def run(self):
        """Main worker loop - processes jobs from Redis queue"""
        if not self.connect_redis():
            logger.error("❌ Cannot start worker: Redis connection failed")
            return
        
        # Initialize worker services (Hammer, GRPAN, RWVAP, etc.)
        if not self.initialize_services():
            logger.error("❌ Cannot start worker: Service initialization failed")
            return
        
        self.running = True
        self.start_time = time.time()
        
        logger.info(f"🚀 Worker {self.worker_name} started")
        logger.info(f"   Queue: {JOB_QUEUE_KEY}")
        logger.info(f"   Poll timeout: {POLL_TIMEOUT}s")
        logger.info(f"   🔵 Worker has its own Hammer Pro connection - backend is NOT blocked")
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            while self.running:
                try:
                    # Blocking pop from queue (BRPOP)
                    result = self.redis_client.brpop(JOB_QUEUE_KEY, timeout=POLL_TIMEOUT)
                    
                    if result is None:
                        # Timeout - continue loop
                        continue
                    
                    queue_name, job_json = result
                    job_data = json.loads(job_json)
                    job_id = job_data.get("job_id")
                    
                    if not job_id:
                        logger.warning("⚠️ Received job without job_id, skipping")
                        continue
                    
                    # Update status to processing
                    self.update_status(job_id, "processing", f"Processing by {self.worker_name}")
                    
                    # Process job
                    start_time = time.time()
                    result = self.process_job(job_data)
                    processing_time = time.time() - start_time
                    
                    if result.get("success"):
                        # Save result
                        self.save_result(job_id, result)
                        # Update status to completed
                        self.update_status(
                            job_id,
                            "completed",
                            f"Completed in {processing_time:.2f}s by {self.worker_name}"
                        )
                        self.processed_jobs += 1
                        logger.info(f"✅ Job {job_id} completed in {processing_time:.2f}s")
                    else:
                        # Update status to failed
                        error_msg = result.get("error", "Unknown error")
                        self.update_status(job_id, "failed", error=error_msg)
                        self.failed_jobs += 1
                        logger.error(f"❌ Job {job_id} failed: {error_msg}")
                    
                except KeyboardInterrupt:
                    logger.info("🛑 Received interrupt signal, shutting down...")
                    self.running = False
                    break
                except Exception as e:
                    logger.error(f"❌ Error in worker loop: {e}", exc_info=True)
                    time.sleep(1)  # Brief pause before retry
        
        finally:
            # Cleanup
            self.cleanup()
        
        # Shutdown
        runtime = time.time() - self.start_time if self.start_time else 0
        logger.info(
            f"🛑 Worker {self.worker_name} stopped | "
            f"Processed: {self.processed_jobs} | "
            f"Failed: {self.failed_jobs} | "
            f"Runtime: {runtime:.1f}s"
        )
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"📡 Received signal {signum}, shutting down gracefully...")
        self.running = False


def main():
    """Entry point for worker process"""
    worker_name = os.getenv("WORKER_NAME", f"worker_{os.getpid()}")
    worker = DeeperAnalysisWorker(worker_name=worker_name)
    worker.run()


if __name__ == "__main__":
    main()


