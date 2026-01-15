
import threading
import time
import json
import csv
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from app.core.logger import logger
from app.live.hammer_client import HammerClient

class SnapshotScheduler:
    """
    Background scheduler for fetching 5-minute market snapshots.
    
    Features:
    - Periodic execution (default 5 minutes)
    - Distributes load (sleeps between requests)
    - Live Update: Stores latest snapshot in Redis (market_data:snapshot:{symbol})
    - History Log: Appends to daily CSV (market_data/snapshots/YYYYMMDD_worker_{id}.csv)
    """
    
    def __init__(
        self,
        worker_name: str,
        hammer_client: HammerClient,
        redis_client,
        symbols: List[str],
        interval_minutes: int = 5,
        requests_per_second: float = 5.0
    ):
        self.worker_name = worker_name
        self.hammer_client = hammer_client
        self.redis_client = redis_client
        self.symbols = symbols
        self.interval_seconds = interval_minutes * 60
        self.sleep_between_reqs = 1.0 / requests_per_second
        
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Ensure log directory exists
        self.log_dir = Path("data/market_snapshots")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def start(self):
        """Start the scheduler thread"""
        if self.running:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, name=f"{self.worker_name}_snapshot", daemon=True)
        self.thread.start()
        logger.info(f"📸 [{self.worker_name}] SnapshotScheduler started ({len(self.symbols)} symbols, {self.interval_seconds/60:.0f}m interval)")

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info(f"📸 [{self.worker_name}] SnapshotScheduler stopped")

    def _run_loop(self):
        """Main loop"""
        # Initial delay to allow connections to settle
        time.sleep(10)
        
        while self.running:
            start_time = time.time()
            
            try:
                self._run_cycle()
            except Exception as e:
                logger.error(f"❌ [{self.worker_name}] Error in snapshot cycle: {e}", exc_info=True)
            
            # Calculate next run time
            elapsed = time.time() - start_time
            sleep_time = max(1.0, self.interval_seconds - elapsed)
            
            # Sleep in small chunks to check running flag
            chunks = int(sleep_time)
            for _ in range(chunks):
                if not self.running:
                    return
                time.sleep(1)
            
            # Sleep remainder
            time.sleep(sleep_time - chunks)

    def _run_cycle(self):
        """Execute one full snapshot cycle"""
        if not self.hammer_client.is_connected():
            logger.warning(f"⚠️ [{self.worker_name}] Hammer not connected, skipping snapshot cycle")
            return

        cycle_ts = datetime.now()
        date_str = cycle_ts.strftime("%Y%m%d")
        ts_str = cycle_ts.strftime("%H:%M:%S")
        
        # Prepare CSV file for this cycle
        # User requested fixed filename that overwrites daily
        csv_filename = f"daily_snapshots_{self.worker_name}.csv"
        csv_path = self.log_dir / csv_filename
        
        # Check if file exists to write header (initial check, refined later)
        file_exists = csv_path.exists()
        
        csv_buffer = []
        redis_pipeline = self.redis_client.pipeline()
        
        # 🕒 TIME CHECK (TR Time)
        # Only run snapshot logic between 17:30 and 23:59 TRT.
        # This protects 16:00 ET close data from being overwritten by morning noise.
        now_hour = cycle_ts.hour
        now_min = cycle_ts.minute
        
        # Target: 17:30 <= TRT <= 23:59
        is_trading_hours = False
        if 17 <= now_hour <= 23:
            if now_hour == 17:
                if now_min >= 30:
                    is_trading_hours = True
            else:
                is_trading_hours = True
                
        if not is_trading_hours:
            logger.info(f"💤 [{self.worker_name}] Outside Trading Hours (17:30-23:59 TRT). Skipping snapshot cycle to preserve Close Data.")
            return

        # Check for New Day Reset (Cluster safe: Per-Worker)
        date_key = f"market_data:last_snapshot_date:{self.worker_name}"
        stored_date = None
        try:
            stored_date_bytes = self.redis_client.get(date_key)
            if stored_date_bytes:
                stored_date = stored_date_bytes.decode('utf-8')
        except Exception:
            pass
            
        is_new_day = (stored_date != date_str)
        
        # CRITICAL: Only clear history if it is a new day AND we are strictly in trading hours.
        # This prevents clearing yesterday's closing data when restarting the system in the morning (e.g. 10:00 AM).
        if is_new_day and is_trading_hours:
            # New day detected (or first run): Clear history for assigned symbols
            logger.info(f"📅 [{self.worker_name}] New Trading Day detected ({stored_date} -> {date_str}). Clearing history for new session...")
            with self.redis_client.pipeline() as pipe:
                for sym in self.symbols:
                    pipe.delete(f"market_data:history:{sym}")
                pipe.set(date_key, date_str)
                pipe.execute()
            logger.info(f"✅ [{self.worker_name}] History cleared for new session.")
        elif is_new_day and not is_trading_hours:
            # This case is caught by the return above, but just for safety logic:
            # We do NOT touch the date_key, so it remains "yesterday".
            # The next time we run at 17:30, is_new_day will still be True, and we will clear then.
            pass

        logger.info(f"📸 [{self.worker_name}] Starting snapshot cycle for {len(self.symbols)} symbols")
        
        count = 0
        for symbol in self.symbols:
            if not self.running:
                break
                
            try:
                # Fetch Snapshot
                # use_cache=False to force fresh data from Hammer
                snapshot = self.hammer_client.get_symbol_snapshot(symbol, use_cache=False)
                
                if snapshot:
                    # Enhance snapshot with metadata
                    snapshot['symbol'] = symbol
                    snapshot['timestamp'] = ts_str # Human readable
                    snapshot['ts_epoch'] = time.time()
                    
                    # 1. Redis Update (Live)
                    redis_key = f"market_data:snapshot:{symbol}"
                    snapshot_json = json.dumps(snapshot)
                    redis_pipeline.set(redis_key, snapshot_json)
                    
                    # 2. Redis History (Full Day History)
                    # Use a List: LPUSH (prepend)
                    # Removed LTRIM to support full day history (approx 100-150 items)
                    history_key = f"market_data:history:{symbol}"
                    redis_pipeline.lpush(history_key, snapshot_json)
                    
                    # 3. CSV Buffer (History)
                    # Flatten for CSV
                    row = {
                        'timestamp': ts_str,
                        'symbol': symbol,
                        'bid': snapshot.get('bid'),
                        'ask': snapshot.get('ask'),
                        'last': snapshot.get('last'),
                        'volume': snapshot.get('volume'),
                        'prevClose': snapshot.get('prevClose'),
                        'change': snapshot.get('change'),
                        'high': snapshot.get('high'),
                        'low': snapshot.get('low')
                    }
                    csv_buffer.append(row)
                    
                    count += 1
                
                # Rate limit
                time.sleep(self.sleep_between_reqs)
                
                # Batch execute Redis every 50 items
                if count % 50 == 0:
                    redis_pipeline.execute()
                    redis_pipeline = self.redis_client.pipeline()
                    
            except Exception as e:
                logger.debug(f"Error fetching snapshot for {symbol}: {e}")
                
        # Final Redis execute
        if count % 50 != 0:
            redis_pipeline.execute()
            
        # Write CSV
        if csv_buffer:
            try:
                keys = ['timestamp', 'symbol', 'bid', 'ask', 'last', 'volume', 'prevClose', 'change', 'high', 'low']
                
                # If new day, overwrite ('w'). Else append ('a').
                mode = 'w' if is_new_day else 'a'
                should_write_header = is_new_day or not csv_path.exists()
                
                with open(csv_path, mode, newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=keys)
                    if should_write_header:
                        writer.writeheader()
                    writer.writerows(csv_buffer)
                    
                logger.info(f"💾 [{self.worker_name}] {'Overwrote' if is_new_day else 'Appended'} {len(csv_buffer)} rows to {csv_filename}")
            except Exception as e:
                logger.error(f"❌ [{self.worker_name}] Error writing CSV: {e}")

        logger.info(f"✅ [{self.worker_name}] Snapshot cycle completed. Fetched {count}/{len(self.symbols)}")
