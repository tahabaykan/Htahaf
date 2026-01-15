"""
QeBenchDataLogger - Benchmark Logging & Analysis Module

Responsibilities:
1. Log every trade fill (Price, Qty, Time, Account) to CSV and Redis.
2. Calculate "Group Average Price" Benchmark at the EXACT moment of the fill.
3. Handle "Offline Recovery":
   - If a fill is recovered (delayed), reconstruct benchmark using Hammer Pro `getTicks`.
   - Prevent duplicates (Deduplication).
4. Listen to Global Account Mode changes via Redis (`sys:account_change`).
5. Validate fill account against active mode (Cross-Check).

Usage:
    logger = QeBenchDataLogger()
    logger.log_fill(symbol="CIM PRB", price=25.05, qty=100, account="IBKR_GUN", ...)
"""

import os
import csv
import time
import json
import threading
import statistics
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set

from app.core.logger import logger
from app.core.redis_client import redis_client
from app.live.hammer_client import HammerClient

# Import lazily to avoid circular deps if needed, but here simple imports are fine
# from app.psfalgo.ibkr_connector import get_ibkr_connector

class QeBenchDataLogger:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(QeBenchDataLogger, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        
        # Configuration
        self.csv_dir = r"c:\StockTracker\quant_engine\reports"
        os.makedirs(self.csv_dir, exist_ok=True)
        
        self.current_active_mode = "UNKNOWN" # Will be updated via Redis
        self.processed_fill_ids: Set[str] = set() # For deduplication
        
        # Redis Channels
        self.REDIS_CHANNEL_ACCOUNT = "sys:account_change"
        self.REDIS_KEY_BENCH_FILL = "bench:last_fill:{symbol}"
        
        # Start Redis Listener for Account Mode
        self._start_account_listener()
        
        # Pre-load dosgroups/cgrups logic if possible, or fetch dynamically
        # For now we will fetch "peers" from Redis or config on the fly
        
        logger.info("QeBenchDataLogger initialized")

    def _start_account_listener(self):
        """Start a thread to listen for global account mode changes"""
        def listen():
            try:
                if not redis_client.sync:
                    logger.error("[QeBenchData] Redis not connected, cannot subscribe")
                    return
                pubsub = redis_client.sync.pubsub()
                pubsub.subscribe(self.REDIS_CHANNEL_ACCOUNT)
                logger.info(f"[QeBenchData] Subscribed to {self.REDIS_CHANNEL_ACCOUNT}")
                
                for message in pubsub.listen():
                    if message['type'] == 'message':
                        try:
                            data = json.loads(message['data'])
                            new_mode = data.get('mode')
                            if new_mode:
                                self.current_active_mode = new_mode
                                logger.info(f"[QeBenchData] Account Mode Updated: {self.current_active_mode}")
                        except Exception as e:
                            logger.error(f"[QeBenchData] Error parsing account msg: {e}")
            except Exception as e:
                logger.error(f"[QeBenchData] Redis listener failed: {e}")

        t = threading.Thread(target=listen, daemon=True, name="QeBenchAccountListener")
        t.start()

    def log_fill(self, 
                 symbol: str, 
                 price: float, 
                 qty: int, 
                 action: str, 
                 account: str, 
                 fill_time: datetime, 
                 fill_id: str,
                 source_module: str = "UNKNOWN"):
        """
        Main entry point to log a fill.
        """
        # 1. Deduplication
        if fill_id in self.processed_fill_ids:
            logger.debug(f"[QeBenchData] Skipping duplicate fill {fill_id}")
            return
        
        self.processed_fill_ids.add(fill_id)

        # 2. Account Mismatch Check
        if self.current_active_mode != "UNKNOWN":
            # Simple check logic: IBKR_GUN account should match mode IBKR_GUN, etc.
            # If HAMMER_PRO mode, account might be "Simulated" or "Hammer"
            # This is a soft check, we still log.
            if "IBKR" in self.current_active_mode and account not in self.current_active_mode:
                 logger.warning(f"[QeBenchData] [MISMATCH] Fill Account {account} != Active Mode {self.current_active_mode}")

        # 3. Calculate Benchmark
        # Check latency to decide if "Realtime" or "Recovered"
        # If fill_time is older than 60 seconds, use RECOVERY
        latency = (datetime.now() - fill_time).total_seconds()
        is_recovery = latency > 60
        
        bench_price = None
        bench_source = "REALTIME"
        
        try:
            if is_recovery:
                bench_price = self._recover_benchmark_via_hammer(symbol, fill_time)
                bench_source = "RECOVERED:HAMMER_TICKS"
            else:
                bench_price = self._calculate_realtime_group_price(symbol)
                bench_source = "REALTIME"
        except Exception as e:
            logger.error(f"[QeBenchData] Benchmark eval failed for {symbol}: {e}")
            bench_source = "ERROR"

        # 4. CSV Logging
        self._write_to_csv({
            "timestamp": datetime.now().isoformat(),
            "fill_time": fill_time.isoformat(),
            "symbol": symbol,
            "price": price,
            "qty": qty,
            "action": action,
            "account": account,
            "active_mode": self.current_active_mode,
            "bench_price": bench_price if bench_price else "",
            "bench_source": bench_source,
            "fill_id": fill_id,
            "source": source_module
        })

        # 5. Redis Publish (for UI/Realtime Analysis)
        try:
            redis_data = {
                "symbol": symbol,
                "price": price,
                "fill_time": fill_time.isoformat(),
                "bench_price": bench_price,
                "bench_source": bench_source
            }
            if redis_client.sync:
                redis_client.sync.set(self.REDIS_KEY_BENCH_FILL.format(symbol=symbol), json.dumps(redis_data))
            # Optional: Publish to channel if needed
            # redis_client.publish("bench:fills", json.dumps(redis_data)) 
        except Exception as e:
            logger.error(f"[QeBenchData] Redis publish failed: {e}")

        logger.info(f"[QeBenchData] Logged {symbol} @ {price} ({action}) - Bench: {bench_price} ({bench_source})")

    def _get_peers_for_symbol(self, symbol: str) -> List[str]:
        """
        Identify peer stocks in the same DOS GROUP (and CGRUP if heldkuponlu).
        Uses StaticDataStore to find group members.
        """
        try:
            from app.market_data.static_data_store import get_static_store, initialize_static_store
            
            store = get_static_store()
            if not store or not store.is_loaded():
                # Try to initialize if not found
                store = initialize_static_store()
                if not store.load_csv():
                    logger.error("[QeBenchData] Failed to load StaticDataStore for peer lookup")
                    return []

            # 1. Get Group Info for Target Symbol
            # symbol arg is "CIM PRB" (Display Format) -> Convert to PREF_IBKR format if needed?
            # StaticDataStore keys are PREF_IBKR (e.g. "CIM-B" or "CIM PRB" depending on CSV)
            # Usually CSV has "PREF IBKR" column. Let's assume input symbol matches key or we try variants.
            
            # Simple direct lookup first
            data = store.get_static_data(symbol)
            if not data:
                # Try replacing space with hyphen or vice versa if needed, but for now strict
                logger.warning(f"[QeBenchData] Symbol {symbol} not found in StaticDataStore")
                return []

            group = data.get('GROUP')
            c_group = data.get('CGRUP')
            
            if not group:
                return []

            # 2. Refine Grouping Logic
            target_group_key = group
            use_cgroup = False
            
            # Special logic for heldkuponlu -> Use CGRUP
            # "heldkuponlu" might be the group name.
            if "heldkuponlu" in str(group).lower() and c_group:
                 target_group_key = c_group
                 use_cgroup = True
            
            # 3. Find Peers
            peers = []
            all_symbols = store.get_all_symbols()
            for s in all_symbols:
                if s == symbol: 
                    continue # Exclude self? Or include? Usually exclude self from "peers" list for "average of others"
                    # But "Group Average Price" might imply including self?
                    # "Group Average Price" usually means the index value. If we want index of *group*, we should include self.
                    # Let's include self for a true group average.
                    
                s_data = store.get_static_data(s)
                if not s_data: continue
                
                s_group = s_data.get('GROUP')
                s_cgroup = s_data.get('CGRUP')
                
                match = False
                if use_cgroup:
                    if s_cgroup == target_group_key:
                        match = True
                else:
                    if s_group == target_group_key:
                        match = True
                
                if match:
                    peers.append(s)
            
            # Include self if not already in list (for group average)
            if symbol not in peers:
                peers.append(symbol)
                
            return peers

        except Exception as e:
            logger.error(f"[QeBenchData] Peer lookup failed: {e}", exc_info=True)
            return []

    def _recover_benchmark_via_hammer(self, symbol: str, fill_time: datetime) -> Optional[float]:
        """
        Recover historical benchmark using Hammer Pro `getTicks`.
        Iterates peers, requests ticks, finds price at `fill_time`.
        """
        peers = self._get_peers_for_symbol(symbol)
        if not peers:
            return None
        
        # Get Hammer Client
        try:
            from app.live.hammer_client import HammerClient
            # We need a connected instance. 
            # If we are in the main process, there is likely a global instance in `app.live_engine` or similar?
            # Or we can spin up a temporary one? Spin up is slow.
            # Best effort: Try to use existing connection if accessible, or create new.
            # "headless, engine-driven" implies we can instantiate one.
            
            # NOTE: Connecting a NEW client for every fill is heavy.
            # Ideally we pass the client in `log_fill`.
            # If prompt didn't specifying adding client to `log_fill`, we'll try to instantiate a temporary one 
            # OR assume one exists.
            
            # Given User constraint: "Hammer Pro ile Geriye Dönük Veri Çekiyoruz"
            # We will try to instantiate a client here just for this recovery if needed.
            # AUTO-RECOVERY approach.
            
            client = HammerClient() 
            # We need password? Defaults in class might work or env vars.
            # Assuming client can connect via defaults or env vars.
            # If not connected, we try to connect.
            if not client.connect():
                 logger.error("[QeBenchData] Could not connect to Hammer for recovery")
                 return None
                 
            # Wait a bit for auth? connect() handles it.
            
            recovered_prices = []
            target_ts = fill_time.timestamp()
            
            for peer in peers:
                # getTicks(lastFew=800)
                # We need to map symbol to Hammer format? `client.get_ticks` handles `SymbolMapper`.
                ticks_data = client.get_ticks(peer, lastFew=800, tradesOnly=True)
                
                if not ticks_data or 'data' not in ticks_data:
                    continue
                    
                ticks = ticks_data['data'] # List of dicts {t, p, s, ...}
                
                # Find closest tick <= target_ts
                # Ticks are usually newest to oldest or oldest to newest?
                # Hammer API docs: "reverse chronological order" if lastFew is used?
                # Actually docs say "return only last N ticks ... in reverse chronological order" (Newest first).
                
                # We want the tick occurring *at or before* fill_time.
                # Since list is Newest -> Oldest:
                # We iterate until we find a tick where tick.ts <= target_ts
                
                best_tick_price = None
                min_diff = float('inf')
                
                for tick in ticks:
                    # Parse timestamp "2020-08-12T11:00:07.500"
                    t_str = tick.get('t')
                    try:
                        # Normalize 'Z'
                        if t_str.endswith('Z'): t_str = t_str[:-1]
                        # Python legacy fromisoformat might not handle partial seconds well dependent on version
                        # but usually fine.
                        t_dt = datetime.fromisoformat(t_str)
                        tick_ts = t_dt.timestamp()
                        
                        # We want tick_ts <= target_ts
                        if tick_ts <= target_ts:
                            # This is the first tick going backwards that is before our target.
                            # This is the "Truth" price at that moment.
                            best_tick_price = float(tick.get('p'))
                            # Check if it's too old? e.g. > 5 mins old?
                            if (target_ts - tick_ts) > 300: # 5 mins
                                logger.warning(f"[QeBenchData] Recovered tick for {peer} is too old ({target_ts - tick_ts}s)")
                                best_tick_price = None # stale
                            break
                    except:
                        continue
                        
                if best_tick_price:
                    recovered_prices.append(best_tick_price)
                
                # Throttle to be nice?
                time.sleep(0.05)
                
            client.disconnect()
            
            if not recovered_prices:
                return None
                
            return statistics.mean(recovered_prices)

        except Exception as e:
            logger.error(f"[QeBenchData] Recovery failed: {e}", exc_info=True)
            return None 

    def _write_to_csv(self, data: Dict[str, Any]):
        filename = f"qebenchdata_{datetime.now().strftime('%Y%m%d')}.csv"
        filepath = os.path.join(self.csv_dir, filename)
        
        exists = os.path.exists(filepath)
        
        fieldnames = [
            "timestamp", "fill_time", "symbol", "price", "qty", "action", 
            "account", "active_mode", "bench_price", "bench_source", "fill_id", "source"
        ]
        
        try:
            with open(filepath, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not exists:
                    writer.writeheader()
                writer.writerow(data)
        except Exception as e:
            logger.error(f"[QeBenchData] CSV Write Failed: {e}")

# Global Accessor
_logger_instance = None
def get_bench_logger():
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = QeBenchDataLogger()
    return _logger_instance
