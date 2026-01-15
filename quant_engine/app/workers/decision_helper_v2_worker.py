"""
DecisionHelperV2 Worker - Processes DecisionHelperV2 jobs independently.

This worker:
- Consumes jobs from Redis stream: tasks:decision_helper_v2
- Collects tick-by-tick data from Hammer Pro
- Computes modal price flow metrics
- Writes results to Redis
"""

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional

from app.core.redis_client import get_redis_client
from app.config.settings import settings
from app.live.hammer_client import HammerClient
from app.market_data.decision_helper_v2_engine import get_decision_helper_v2_engine
from app.market_data.static_data_store import get_static_store, initialize_static_store
from app.live.symbol_mapper import SymbolMapper

logger = logging.getLogger(__name__)

# Redis stream and key prefixes
STREAM_NAME = "tasks:decision_helper_v2"
JOB_RESULT_PREFIX = "decision_v2:"


class DecisionHelperV2Worker:
    """Worker for DecisionHelperV2 processing"""
    
    def __init__(self, worker_name: str = "decision_helper_v2_worker1"):
        self.worker_name = worker_name
        self.redis_client = None
        self.hammer_client = None
        self.decision_engine = None
        self.static_store = None
        self.running = False
        self.bootstrap_progress = {'total': 0, 'completed': 0, 'tick_count': 0}
    
    def connect_redis(self):
        """Connect to Redis"""
        try:
            redis_client = get_redis_client()
            self.redis_client = redis_client.sync
            
            if not self.redis_client:
                # Try direct connection
                import redis
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
    
    def initialize_services(self) -> bool:
        """Initialize all services"""
        try:
            logger.info(f"🔧 [{self.worker_name}] Initializing worker services...")
            
            # Initialize DecisionHelperV2Engine
            self.decision_engine = get_decision_helper_v2_engine()
            logger.info(f"✅ [{self.worker_name}] DecisionHelperV2Engine initialized")
            
            # Initialize Static Store
            try:
                import os
                self.static_store = get_static_store()
                
                # If not available, create new instance
                if not self.static_store:
                    logger.info(f"📊 [{self.worker_name}] Creating new StaticDataStore instance...")
                    # Calculate CSV path: go up 4 levels from worker file to project root
                    # worker_file = quant_engine/app/workers/decision_helper_v2_worker.py
                    # 1 up: quant_engine/app/workers/
                    # 2 up: quant_engine/app/
                    # 3 up: quant_engine/
                    # 4 up: project root
                    worker_file = os.path.abspath(__file__)
                    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(worker_file))))
                    csv_path = os.path.join(project_root, "janall", "janalldata.csv")
                    logger.info(f"📊 [{self.worker_name}] CSV path: {csv_path}")
                    initialize_static_store(csv_path=csv_path)
                    self.static_store = get_static_store()
                
                # Load CSV if not already loaded
                if self.static_store and not self.static_store.is_loaded():
                    try:
                        # Calculate CSV path: go up 4 levels from worker file to project root
                        worker_file = os.path.abspath(__file__)
                        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(worker_file))))
                        csv_path = os.path.join(project_root, "janall", "janalldata.csv")
                        
                        logger.info(f"📊 [{self.worker_name}] Attempting to load CSV from: {csv_path}")
                        logger.info(f"📊 [{self.worker_name}] CSV exists: {os.path.exists(csv_path)}")
                        
                        if os.path.exists(csv_path):
                            self.static_store.load_csv(csv_path)
                            symbol_count = len(self.static_store.get_all_symbols())
                            logger.info(f"✅ [{self.worker_name}] Static store loaded from {csv_path}: {symbol_count} symbols")
                        else:
                            logger.warning(f"⚠️ [{self.worker_name}] CSV file not found at {csv_path}")
                    except Exception as e:
                        logger.error(f"❌ [{self.worker_name}] Failed to load static store: {e}", exc_info=True)
                elif self.static_store and self.static_store.is_loaded():
                    symbol_count = len(self.static_store.get_all_symbols())
                    logger.info(f"✅ [{self.worker_name}] Static store already loaded: {symbol_count} symbols")
                else:
                    logger.warning(f"⚠️ [{self.worker_name}] Static store not available")
            except Exception as e:
                logger.error(f"❌ [{self.worker_name}] Static store initialization failed: {e}", exc_info=True)
            
            # Connect to Hammer Pro
            self.hammer_client = HammerClient(
                host=settings.HAMMER_HOST,
                port=settings.HAMMER_PORT,
                password=settings.HAMMER_PASSWORD,
                account_key=settings.HAMMER_ACCOUNT_KEY
            )
            
            if self.hammer_client.connect():
                logger.info(f"✅ [{self.worker_name}] Connected to Hammer Pro")
                
                # Set up message callback for L2Updates (trade prints)
                self.hammer_client.on_message_callback = self._handle_l2_update
                
                # Bootstrap ticks in background thread (non-blocking)
                import threading
                bootstrap_thread = threading.Thread(
                    target=self._bootstrap_ticks,
                    daemon=True,
                    name=f"{self.worker_name}_bootstrap"
                )
                bootstrap_thread.start()
                logger.info(f"🚀 [{self.worker_name}] Bootstrap thread started")
            else:
                logger.error(f"❌ [{self.worker_name}] Failed to connect to Hammer Pro")
                return False
            
            logger.info(f"✅ [{self.worker_name}] All services initialized successfully")
            return True
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Failed to initialize services: {e}", exc_info=True)
            return False
    
    def _bootstrap_ticks(self):
        """Bootstrap tick data using getTicks for all symbols (runs in background thread)"""
        try:
            logger.info(f"🔍 [{self.worker_name}] Bootstrap thread started")
            
            if not self.static_store or not self.static_store.is_loaded():
                logger.warning(f"⚠️ [{self.worker_name}] Static store not loaded, skipping bootstrap")
                return
            
            symbols = self.static_store.get_all_symbols()
            logger.info(f"📊 [{self.worker_name}] Bootstrapping ticks for {len(symbols)} symbols...")
            
            self.bootstrap_progress = {'total': len(symbols), 'completed': 0, 'tick_count': 0}
            
            for symbol in symbols:
                try:
                    # Get last 2000 ticks using getTicks (more ticks for longer windows like pan_1d)
                    # CRITICAL: tradesOnly=True ensures we only get REAL TRADES
                    # We need more ticks for pan_1d (1440 minutes = 24 hours)
                    # 2000 ticks should cover at least 1 day of trading data
                    tick_data = self.hammer_client.get_ticks(
                        symbol,
                        lastFew=2000,  # Increased from 100 to 2000 for longer windows
                        tradesOnly=True,  # ONLY real trades
                        regHoursOnly=True
                    )
                    
                    symbol_tick_count = 0
                    if tick_data and tick_data.get('data'):
                        ticks = tick_data.get('data', [])
                        
                        for tick in ticks:
                            # Add tick to decision engine
                            self.decision_engine.add_tick(symbol, tick)
                            symbol_tick_count += 1
                            self.bootstrap_progress['tick_count'] += 1
                    
                    self.bootstrap_progress['completed'] += 1
                    
                    if self.bootstrap_progress['completed'] % 50 == 0:
                        logger.info(
                            f"📊 [{self.worker_name}] Bootstrap progress: "
                            f"{self.bootstrap_progress['completed']}/{self.bootstrap_progress['total']} symbols, "
                            f"{self.bootstrap_progress['tick_count']} ticks"
                        )
                
                except Exception as e:
                    logger.debug(f"Error bootstrapping {symbol}: {e}")
                    self.bootstrap_progress['completed'] += 1
                    continue
            
            logger.info(
                f"✅ [{self.worker_name}] Bootstrap completed: "
                f"{self.bootstrap_progress['completed']}/{self.bootstrap_progress['total']} symbols, "
                f"{self.bootstrap_progress['tick_count']} total ticks"
            )
            
            # Log tick_store status after bootstrap
            with self.decision_engine._tick_lock:
                symbols_with_ticks = [s for s in self.decision_engine.tick_store.keys() if len(self.decision_engine.tick_store[s]) > 0]
                logger.info(f"📊 [{self.worker_name}] Tick store status: {len(symbols_with_ticks)} symbols with ticks")
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Bootstrap error: {e}", exc_info=True)
    
    def _handle_l2_update(self, message: Dict[str, Any]):
        """Handle L2Update (trade prints) from Hammer Pro"""
        try:
            if message.get('cmd') != 'L2Update':
                return
            
            result = message.get('result', {})
            hammer_sym = result.get('sym', '')
            
            if not hammer_sym:
                return
            
            # Map Hammer symbol to display symbol
            display_sym = SymbolMapper.from_hammer_symbol(hammer_sym)
            
            # Extract trade print data
            bids = result.get('bids', [])
            asks = result.get('asks', [])
            
            # Process bids and asks as trade prints
            for level in bids + asks:
                if level.get('act') == 'a':  # Add/modify
                    price = float(level.get('price', 0))
                    size = float(level.get('size', 0))
                    timestamp = level.get('timeStamp', '')
                    
                    if price > 0 and size > 0:
                        tick = {
                            't': timestamp,
                            'p': price,
                            's': size,
                            'b': float(result.get('bids', [{}])[0].get('price', 0)) if result.get('bids') else 0,
                            'a': float(result.get('asks', [{}])[0].get('price', 0)) if result.get('asks') else 0,
                            'bf': False
                        }
                        self.decision_engine.add_tick(display_sym, tick)
        
        except Exception as e:
            logger.debug(f"Error handling L2Update: {e}")
    
    def get_avg_adv(self, symbol: str) -> float:
        """Get AVG_ADV for symbol"""
        try:
            if not self.static_store:
                return 10000.0  # Default
            
            # Use get_static_data method (same as other workers)
            data = self.static_store.get_static_data(symbol)
            if data:
                return float(data.get('AVG_ADV', 10000.0))
            return 10000.0
        except Exception as e:
            logger.debug(f"Error getting AVG_ADV for {symbol}: {e}")
            return 10000.0
    
    def process_job(self, job_id: str, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a DecisionHelperV2 job"""
        try:
            logger.info(f"🔄 [{self.worker_name}] Processing job {job_id}")
            
            # Get symbols to process
            symbols_to_process = job_data.get('symbols', [])
            if not symbols_to_process:
                # If no symbols specified, process all symbols with ticks
                with self.decision_engine._tick_lock:
                    symbols_to_process = list(self.decision_engine.tick_store.keys())
            
            # Get windows from job data, default to all supported windows
            windows = job_data.get('windows', None)
            if not windows or len(windows) == 0:
                # Default to all supported windows
                windows = ['pan_10m', 'pan_30m', 'pan_1h', 'pan_3h', 'pan_1d']
            
            # Log received job data for debugging
            logger.info(f"📋 [{self.worker_name}] Job data received - windows: {windows}, symbols: {len(symbols_to_process) if symbols_to_process else 'all'}")
            logger.info(f"📊 [{self.worker_name}] Processing {len(symbols_to_process)} symbols for windows: {windows}")
            
            # Wait for bootstrap if needed
            if self.bootstrap_progress['total'] == 0:
                logger.warning(f"⚠️ [{self.worker_name}] Bootstrap not started yet (total=0). Waiting...")
                max_wait = 30  # 30 seconds
                start_time = time.time()
                while (time.time() - start_time) < max_wait:
                    if self.bootstrap_progress['total'] > 0:
                        break
                    time.sleep(1)
            
            if self.bootstrap_progress['completed'] < self.bootstrap_progress['total']:
                logger.info(f"⏳ [{self.worker_name}] Waiting for bootstrap to complete ({self.bootstrap_progress['completed']}/{self.bootstrap_progress['total']})...")
                max_wait = 120  # 120 seconds (bootstrap can take time)
                start_time = time.time()
                while (time.time() - start_time) < max_wait:
                    if self.bootstrap_progress['completed'] >= self.bootstrap_progress['total']:
                        break
                    time.sleep(2)
                    if int(time.time() - start_time) % 10 == 0:
                        logger.info(f"⏳ [{self.worker_name}] Still waiting... ({self.bootstrap_progress['completed']}/{self.bootstrap_progress['total']})")
            
            # Check symbols with ticks
            with self.decision_engine._tick_lock:
                symbols_with_ticks = [
                    s for s in symbols_to_process
                    if s in self.decision_engine.tick_store and len(self.decision_engine.tick_store[s]) > 0
                ]
            
            logger.info(f"📊 [{self.worker_name}] Found {len(symbols_with_ticks)} symbols with ticks")
            
            # Process each symbol
            results = {}
            processed_count = 0
            
            for symbol in symbols_with_ticks:
                try:
                    avg_adv = self.get_avg_adv(symbol)
                    
                    symbol_results = {}
                    
                    # Compute metrics for each window
                    for window_name in windows:
                        metrics = self.decision_engine.compute_metrics(
                            symbol=symbol,
                            window_name=window_name,
                            avg_adv=avg_adv
                        )
                        
                        if metrics:
                            symbol_results[window_name] = metrics
                            
                            # Write to Redis
                            redis_key = f"{JOB_RESULT_PREFIX}{symbol}:{window_name}"
                            
                            # Store result in Redis (1 hour TTL)
                            self.redis_client.setex(
                                redis_key,
                                3600,
                                json.dumps(metrics)
                            )
                        else:
                            logger.debug(f"⚠️ [{self.worker_name}] No metrics for {symbol} ({window_name})")
                    
                    if symbol_results:
                        results[symbol] = {
                            'symbol': symbol,
                            'windows': symbol_results,
                            'timestamp': datetime.now().isoformat()
                        }
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
                "timestamp": datetime.now().isoformat()
            }
    
    def run(self):
        """Main worker loop"""
        try:
            logger.info(f"🚀 Worker {self.worker_name} starting...")
            
            if not self.connect_redis():
                logger.error("❌ Cannot start worker: Redis connection failed")
                return
            
            if not self.initialize_services():
                logger.error("❌ Cannot start worker: Service initialization failed")
                return
            
            logger.info(f"✅ [{self.worker_name}] Worker started successfully")
            logger.info(f"📊 [{self.worker_name}] Polling Redis stream: {STREAM_NAME}")
            
            self.running = True
            last_id = '0'  # Start from beginning
            
            while self.running:
                try:
                    # Read from Redis stream
                    messages = self.redis_client.xread({STREAM_NAME: last_id}, count=1, block=5000)
                    
                    if not messages:
                        continue
                    
                    for stream, stream_messages in messages:
                        for msg_id, msg_data in stream_messages:
                            try:
                                # Update last_id for next read
                                last_id = msg_id.decode('utf-8') if isinstance(msg_id, bytes) else msg_id
                                
                                # Parse job data
                                job_data_str = msg_data.get(b'data', b'{}')
                                if isinstance(job_data_str, bytes):
                                    job_data_str = job_data_str.decode('utf-8')
                                job_data = json.loads(job_data_str)
                                job_id = job_data.get('job_id', last_id)
                                
                                # Debug: Log raw job data
                                logger.debug(f"📋 [{self.worker_name}] Raw job data: {job_data_str[:200]}...")
                                logger.debug(f"📋 [{self.worker_name}] Parsed job data - windows: {job_data.get('windows')}")
                                
                                # Process job
                                result = self.process_job(job_id, job_data)
                                
                                logger.info(f"✅ Job {job_id} completed: {result.get('processed_count', 0)} symbols")
                            
                            except Exception as e:
                                logger.error(f"❌ Error processing message: {e}", exc_info=True)
                
                except Exception as e:
                    if self.running:
                        logger.error(f"❌ Error in worker loop: {e}", exc_info=True)
                        time.sleep(5)
        
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
            logger.info(f"✅ [{self.worker_name}] Worker cleanup completed")
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")


def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    worker = DecisionHelperV2Worker()
    
    def signal_handler(sig, frame):
        logger.info("🛑 Received interrupt signal")
        worker.running = False
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    worker.run()


if __name__ == "__main__":
    main()


