"""
Greatest MM Quant Worker
========================

Terminal 9: Market Making quantitative scoring worker.
Processes 4-scenario MM Long/Short analysis every 3 minutes.
Shares results via Redis for inter-terminal communication.

Run with: python -m app.workers.greatest_mm_worker
"""

import os
import sys
import json
import time
import signal
import threading
from typing import Dict, Any, Optional, List, Set
from datetime import datetime, date
from collections import Counter

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
from app.mm.greatest_mm_engine import GreatestMMEngine, get_greatest_mm_engine
from app.mm.greatest_mm_models import MMAnalysis, MMScenario


# Redis keys
STREAM_NAME = "tasks:greatest_mm"       # Job queue stream
RESULT_KEY = "greatest_mm:results"      # Latest results
SIGNAL_KEY = "greatest_mm:signals"      # Trading signals (bid/ask to write)

# Worker configuration
WORKER_NAME = os.getenv("GREATEST_MM_WORKER_NAME", f"greatest_mm_worker_{os.getpid()}")
REFRESH_INTERVAL = int(os.getenv("GREATEST_MM_REFRESH_SEC", "180"))  # 3 minutes default
MM_THRESHOLD = 30.0


class GreatestMMWorker:
    """
    Greatest MM Quant Worker (Terminal 9)
    
    Computes 4-scenario MM Long/Short scores and publishes:
    - Results to Redis for other terminals
    - Trading signals (entry points) for actionable symbols
    """
    
    def __init__(self, worker_name: str = None):
        self.worker_name = worker_name or WORKER_NAME
        self.redis_client = None
        self.running = False
        self.cycle_count = 0
        self.start_time = None
        
        # Engine
        self.mm_engine: Optional[GreatestMMEngine] = None
        
        # Services
        self.static_store = None
        self.data_fabric = None
        self.pricing_engine = None
        self.truth_engine = None
        
        logger.info(f"[{self.worker_name}] Worker initialized")
    
    def connect_redis(self) -> bool:
        """Connect to Redis"""
        try:
            redis_client = get_redis_client()
            self.redis_client = redis_client.sync
            
            if not self.redis_client:
                self.redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    decode_responses=True,
                    socket_connect_timeout=5
                )
                self.redis_client.ping()
            
            logger.info(f"✅ [{self.worker_name}] Connected to Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            return True
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Redis connection failed: {e}")
            return False
    
    def initialize_services(self) -> bool:
        """Initialize required services"""
        try:
            logger.info(f"🔧 [{self.worker_name}] Initializing services...")
            
            # Initialize MM Engine
            self.mm_engine = get_greatest_mm_engine()
            logger.info(f"✅ [{self.worker_name}] GreatestMMEngine initialized")
            
            # Load static store
            from app.market_data.static_data_store import get_static_store, initialize_static_store
            self.static_store = get_static_store()
            if not self.static_store:
                self.static_store = initialize_static_store()
            if self.static_store and not self.static_store.is_loaded():
                self.static_store.load_csv()
            
            symbol_count = len(self.static_store.get_all_symbols()) if self.static_store and self.static_store.is_loaded() else 0
            logger.info(f"✅ [{self.worker_name}] Static store: {symbol_count} symbols")
            
            # Data fabric (for L1)
            from app.core.data_fabric import get_data_fabric
            self.data_fabric = get_data_fabric()
            logger.info(f"✅ [{self.worker_name}] DataFabric ready: {self.data_fabric is not None}")
            
            # Pricing overlay (for benchmark_chg)
            from app.market_data.pricing_overlay_engine import get_pricing_overlay_engine
            self.pricing_engine = get_pricing_overlay_engine()
            logger.info(f"✅ [{self.worker_name}] PricingOverlayEngine ready: {self.pricing_engine is not None}")
            
            # Truth ticks engine (for Son5Tick)
            from app.market_data.truth_ticks_engine import get_truth_ticks_engine
            self.truth_engine = get_truth_ticks_engine()
            logger.info(f"✅ [{self.worker_name}] TruthTicksEngine ready: {self.truth_engine is not None}")
            
            logger.info(f"✅ [{self.worker_name}] All services initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Service initialization failed: {e}", exc_info=True)
            return False
    
    def get_tick_data_from_redis(self) -> Dict[str, List]:
        """Load truth ticks from Redis (shared by truth_ticks_worker)"""
        all_ticks = {}
        try:
            # Targeted lookup of 'inspect' keys which contain the PRE-FILTERED truth ticks
            # This ensures we use the exact same logic as the UI and other components
            symbols = self.static_store.get_all_symbols() if self.static_store else []
            
            if not symbols:
                return all_ticks
                
            # Use pipeline for performance if we have many symbols
            pipe = self.redis_client.pipeline()
            # Split into batches of 200 to avoid blocking Redis for too long
            for i in range(0, len(symbols), 200):
                batch = symbols[i:i+200]
                for symbol in batch:
                    pipe.get(f"truth_ticks:inspect:{symbol}")
                
                results = pipe.execute()
                
                for idx, result_json in enumerate(results):
                    if result_json:
                        try:
                            symbol = batch[idx]
                            if isinstance(result_json, bytes):
                                result_json = result_json.decode('utf-8')
                            result_data = json.loads(result_json)
                            # Extract path_dataset (the latest 100 qualified truth ticks)
                            path_data = result_data.get('data', {}).get('path_dataset', [])
                            if path_data:
                                # Normalize for MM engine
                                normalized_ticks = []
                                for t in path_data:
                                    normalized_ticks.append({
                                        'ts': t.get('timestamp'),
                                        'price': t.get('price'),
                                        'size': t.get('size'),
                                        'exch': t.get('venue')
                                    })
                                all_ticks[symbol] = normalized_ticks
                        except:
                            continue
        except Exception as e:
            logger.warning(f"⚠️ [{self.worker_name}] Could not load ticks from Redis: {e}")
        
        return all_ticks
    
    def compute_son5_tick(self, ticks: List[Dict]) -> Optional[float]:
        """Compute Son5Tick (mode of last 5 truth ticks)"""
        if not ticks or not isinstance(ticks, list):
            return None
        
        # Ticks from 'path_dataset' are ALREADY truth filtered!
        # Just sort by timestamp descending
        sorted_ticks = sorted(
            ticks,
            key=lambda t: t.get('ts', 0),
            reverse=True
        )
        
        # Mode of last 5
        last5 = sorted_ticks[:5]
        prices = [round(t.get('price', 0), 2) for t in last5 if t.get('price', 0) > 0]
        
        if prices:
            price_counts = Counter(prices)
            return price_counts.most_common(1)[0][0]
        
        return None
    
    def get_new_print(self, ticks: List[Dict], son5_tick: float) -> Optional[float]:
        """
        Get 'NewPrint' (Latest Truth Tick).
        """
        if not ticks or not isinstance(ticks, list):
            return None
        
        # Ticks from 'path_dataset' are ALREADY truth filtered!
        # Sort by timestamp descending (Latest first)
        sorted_ticks = sorted(
            ticks,
            key=lambda t: t.get('ts', 0),
            reverse=True
        )
        
        if sorted_ticks and sorted_ticks[0].get('price', 0) > 0:
            return sorted_ticks[0]['price']
        
        return None
    
    def run_analysis_cycle(self) -> Dict[str, Any]:
        """Run one analysis cycle for all symbols"""
        results = []
        actionable_longs = []
        actionable_shorts = []
        
        symbols = self.static_store.get_all_symbols() if self.static_store and self.static_store.is_loaded() else []
        
        if not symbols:
            logger.warning(f"⚠️ [{self.worker_name}] No symbols to process")
            return {'success': False, 'error': 'No symbols'}
        
        # Load ticks from Redis
        all_redis_ticks = self.get_tick_data_from_redis()
        
        processed = 0
        skipped = 0
        
        for symbol in symbols:
            try:
                static_data = self.static_store.get_static_data(symbol) or {}
                # Get L1 data (Prefer get_fast_snapshot which works in Lifeless Mode)
                bid, ask = None, None
                prev_close = 0.0
                
                if self.data_fabric:
                    # In Lifeless Mode, get_fast_snapshot returns SIMULATED data
                    snapshot = self.data_fabric.get_fast_snapshot(symbol)
                    if snapshot:
                        bid = snapshot.get('bid')
                        ask = snapshot.get('ask')
                        # Override static prev_close with snapshot prev_close if available
                        # This ensures consistency if DataFabric handles adjustments
                        if snapshot.get('prev_close'):
                            prev_close = float(snapshot.get('prev_close'))
                    else:
                        live_data = self.data_fabric.get_live(symbol)
                        if live_data:
                            bid = live_data.get('bid')
                            ask = live_data.get('ask')
                            
                    # Fallback for prev_close if not in snapshot
                    if prev_close == 0.0:
                         static_data = self.static_store.get_static_data(symbol) or {}
                         prev_close = float(static_data.get('prev_close', 0) or 0)
                
                if not bid or not ask or bid <= 0 or ask <= 0:
                    skipped += 1
                    continue
                
                # Get benchmark_chg
                benchmark_chg = 0.0
                if self.pricing_engine:
                    overlay = self.pricing_engine.get_overlay_scores(symbol)
                    if overlay and overlay.get('benchmark_chg') is not None:
                        benchmark_chg = overlay['benchmark_chg']
                
                # Get ticks for Son5Tick
                ticks = []
                if symbol in all_redis_ticks:
                    redis_data = all_redis_ticks[symbol]
                    if isinstance(redis_data, list):
                        ticks = redis_data
                    elif isinstance(redis_data, dict):
                        for tf_name in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']:
                            if tf_name in redis_data and redis_data[tf_name]:
                                tf_data = redis_data[tf_name]
                                if isinstance(tf_data, dict):
                                    ticks = tf_data.get('truth_ticks', tf_data.get('ticks', []))
                                    if ticks:
                                        break
                                elif isinstance(tf_data, list):
                                    ticks = tf_data
                                    break
                
                # 💀 SIMULATION: Apply offset to Truth Ticks (for Lifeless Mode)
                if self.data_fabric and self.data_fabric.is_lifeless_mode():
                    offset = self.data_fabric.get_simulation_offset(symbol)
                    if offset != 0.0:
                        # Apply offset to all ticks (affects Son5Tick and NewPrint)
                        # Create shallow copy to avoid mutating cache if shared
                        sim_ticks = []
                        for t in ticks:
                            new_t = t.copy()
                            if 'price' in new_t and new_t['price']:
                                new_t['price'] += offset
                            sim_ticks.append(new_t)
                        ticks = sim_ticks
                
                # Compute Son5Tick and NewPrint
                son5_tick = self.compute_son5_tick(ticks)
                if son5_tick is None:
                    skipped += 1
                    continue
                
                new_print = self.get_new_print(ticks, son5_tick)
                
                # Run MM analysis
                analysis = self.mm_engine.analyze_symbol(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    prev_close=prev_close if prev_close > 0 else bid,
                    benchmark_chg=benchmark_chg,
                    son5_tick=son5_tick,
                    new_print=new_print
                )
                
                if analysis and not analysis.error:
                    results.append(analysis.model_dump())
                    processed += 1
                    
                    # Collect actionable entries
                    if analysis.long_actionable:
                        actionable_longs.append({
                            'symbol': symbol,
                            'entry': analysis.best_long_entry,
                            'score': analysis.best_long_score,
                            'scenario': analysis.best_long_scenario.value if analysis.best_long_scenario else None
                        })
                    
                    if analysis.short_actionable:
                        actionable_shorts.append({
                            'symbol': symbol,
                            'entry': analysis.best_short_entry,
                            'score': analysis.best_short_score,
                            'scenario': analysis.best_short_scenario.value if analysis.best_short_scenario else None
                        })
                
            except Exception as e:
                logger.debug(f"⚠️ [{self.worker_name}] Error processing {symbol}: {e}")
                skipped += 1
                continue
        
        logger.info(f"📊 [{self.worker_name}] Cycle complete: {processed} processed, {skipped} skipped, {len(actionable_longs)} longs, {len(actionable_shorts)} shorts")
        
        return {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'processed': processed,
            'skipped': skipped,
            'actionable_longs': len(actionable_longs),
            'actionable_shorts': len(actionable_shorts),
            'results': results,
            'signals': {
                'longs': actionable_longs,
                'shorts': actionable_shorts
            }
        }
    
    def _json_sanitize(self, obj: Any) -> Any:
        """Recursively convert datetime/date to ISO strings so json.dumps works."""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: self._json_sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._json_sanitize(v) for v in obj]
        return obj

    def publish_to_redis(self, data: Dict[str, Any]):
        """Publish results and signals to Redis"""
        try:
            sanitized = self._json_sanitize(data)
            # Main results
            self.redis_client.setex(
                RESULT_KEY,
                3600,  # 1 hour TTL
                json.dumps(sanitized)
            )
            # Signals (for other terminals)
            if sanitized.get('signals'):
                self.redis_client.setex(
                    SIGNAL_KEY,
                    600,  # 10 minutes TTL
                    json.dumps(sanitized['signals'])
                )
            logger.info(f"✅ [{self.worker_name}] Published to Redis: {RESULT_KEY}")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Redis publish failed: {e}")
    
    def run(self):
        """Main worker loop"""
        try:
            logger.info(f"🚀 [{self.worker_name}] Starting Greatest MM Worker (Terminal 9)...")
            
            if not self.connect_redis():
                logger.error(f"❌ Cannot start: Redis connection failed")
                return
            
            if not self.initialize_services():
                logger.error(f"❌ Cannot start: Service initialization failed")
                return
            
            self.running = True
            self.start_time = time.time()
            
            logger.info(f"✅ [{self.worker_name}] Worker started. Refresh interval: {REFRESH_INTERVAL}s")
            
            while self.running:
                try:
                    self.cycle_count += 1
                    logger.info(f"🔄 [{self.worker_name}] Cycle #{self.cycle_count} starting...")
                    
                    # Run analysis
                    result = self.run_analysis_cycle()
                    
                    # Publish to Redis
                    if result.get('success'):
                        self.publish_to_redis(result)
                    
                    # Wait for next cycle
                    logger.info(f"⏳ [{self.worker_name}] Next cycle in {REFRESH_INTERVAL}s...")
                    time.sleep(REFRESH_INTERVAL)
                    
                except Exception as e:
                    logger.error(f"❌ [{self.worker_name}] Cycle error: {e}", exc_info=True)
                    time.sleep(30)
            
        except KeyboardInterrupt:
            logger.info(f"🛑 [{self.worker_name}] Stopped by user")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Fatal error: {e}", exc_info=True)
        finally:
            self.running = False
            logger.info(f"✅ [{self.worker_name}] Worker stopped")


def main():
    """Entry point"""
    worker = GreatestMMWorker()
    
    def signal_handler(sig, frame):
        logger.info(f"🛑 [{worker.worker_name}] SIGINT received, shutting down...")
        worker.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    
    worker.run()


if __name__ == "__main__":
    main()
