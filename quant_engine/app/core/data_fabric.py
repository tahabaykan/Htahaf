"""
SINGLE IN-MEMORY DATA FABRIC
============================

Central data layer for trading-grade performance.

🎯 TWO-PATH ARCHITECTURE (CRITICAL!)
====================================

🟢 FAST PATH (L1 Data) - For UI + Algo
--------------------------------------
- bid, ask, last, size, timestamp (from Hammer L1)
- prev_close, AVG_ADV (from CSV - loaded once at startup)
- FAST scores: Final_BB, Final_FB, Final_SAS, Final_SFS, Fbtot, SFStot, GORT
- benchmark_chg (ETF last / prev_close)
- daily_change (last - prev_close)

⚠️ FAST PATH NEVER WAITS FOR:
- GOD (Group Outlier Detection)
- ROD (Relative Outlier Detection)  
- GRPAN (Group Analysis)
- Any tick-by-tick calculations

🔵 SLOW PATH (Tick-by-Tick) - For Deeper Analysis ONLY
------------------------------------------------------
- GOD, ROD, GRPAN
- Rolling window calculations
- Tick aggregations

⚠️ SLOW PATH IS:
- Lazy loaded (only when Deeper Analysis tab is opened)
- Async computed (never blocks UI or Algo)
- Optional (Algo NEVER requires these)

DESIGN PRINCIPLES:
1. CSV'ler sadece STARTUP'ta okunur - runtime'da asla disk I/O yok
2. Tüm data RAM'de tutulur - singleton pattern
3. UI ve Algo aynı cache'i okur - Single Source of Truth
4. L1 = televizyon yayını gibi sürekli akmalı
5. Tick-by-tick = isteyene derin analiz
6. Algo, tick-by-tick yüzünden ASLA beklememeli

LAYERS:
1. StaticStore: CSV'lerden yüklenen statik data (günde 1 kez)
2. L1Cache: Hammer L1 data (bid/ask/last) - FAST PATH
3. FastScores: L1 + CSV'den hesaplanan skorlar - FAST PATH
4. TickByTickStore: GOD/ROD/GRPAN - SLOW PATH (lazy)
"""

import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from app.core.logger import logger


class DataStatus(Enum):
    """Data status enum"""
    NOT_LOADED = "NOT_LOADED"
    LOADING = "LOADING"
    READY = "READY"
    ERROR = "ERROR"
    STALE = "STALE"


@dataclass
class DataFabricStats:
    """Statistics for monitoring"""
    static_symbols: int = 0
    live_symbols: int = 0
    derived_symbols: int = 0
    snapshot_symbols: int = 0
    static_load_time_ms: float = 0.0
    last_static_load: Optional[datetime] = None
    live_updates_count: int = 0
    derived_computes_count: int = 0
    snapshot_requests_count: int = 0


class DataFabric:
    """
    Central In-Memory Data Fabric
    
    Single Source of Truth for all trading data.
    """
    
    _instance: Optional['DataFabric'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern - only one instance allowed"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize data fabric (only once)"""
        if self._initialized:
            return
        
        # Data stores (in-memory)
        self._static_data: Dict[str, Dict[str, Any]] = {}  # CSV data
        self._live_data: Dict[str, Dict[str, Any]] = {}    # Hammer data
        self._derived_data: Dict[str, Dict[str, Any]] = {} # Calculated metrics
        self._snapshot_data: Dict[str, Dict[str, Any]] = {} # Combined snapshots
        
        # ETF data (separate for benchmark calculations)
        self._etf_live: Dict[str, Dict[str, Any]] = {}
        self._etf_prev_close: Dict[str, float] = {}
        
        # Group weights (from CSV or config)
        self._group_weights: Dict[str, float] = {}
        
        # Status tracking
        self._static_status = DataStatus.NOT_LOADED
        self._live_status = DataStatus.NOT_LOADED
        
        # Lifeless Mode Protocol (Cansız Veri)
        self._lifeless_mode: bool = False
        self._simulation_offsets: Dict[str, float] = {}
        
        # Statistics
        self._stats = DataFabricStats()
        
        # Dirty tracking (symbols that need recalculation)
        self._dirty_symbols: Set[str] = set()
        
        # Thread safety
        self._data_lock = threading.RLock()
        
        # Timestamps
        self._static_load_time: Optional[datetime] = None
        self._last_live_update: Optional[datetime] = None
        
        self._initialized = True
        logger.info("🏗️ DataFabric initialized (singleton)")

    # =========================================================================
    # LIFELESS MODE (Cansız Veri - Snapshot Playback)
    # =========================================================================
    
    def set_lifeless_mode(self, enabled: bool) -> bool:
        """
        Toggle Lifeless Data Mode (Cansız Veri).
        
        TRUE: 
        - Block all incoming live updates (Hammer).
        - Load latest 'last', 'bid', 'ask' from Redis Snapshots.
        - System behaves as if market is frozen at snapshot time.
        
        FALSE:
        - Resume live updates.
        """
        import json
        from app.core.redis_client import get_redis_client
        
        with self._data_lock:
            self._lifeless_mode = enabled
            logger.warning(f"💀 LIFELESS MODE set to: {enabled}")
            
            if enabled:
                # LOAD SNAPSHOTS FROM REDIS
                try:
                    client = get_redis_client().sync
                    # Pattern: market_data:history:{symbol}
                    # We need to iterate known symbols
                    symbols = self.get_all_static_symbols()
                    loaded_count = 0
                    
                    from datetime import datetime
                    
                    for symbol in symbols:
                        key = f"market_data:history:{symbol}"
                        # Get last 100 snapshots to find the best market close candidate
                        history = client.lrange(key, 0, 99)
                        
                        best_snap = None
                        
                        if history:
                            # Strategy: Find snapshot closest to 16:00 ET (21:00 UTC)
                            # Assuming server runs in UTC or we can deduce from timestamp
                            # We want the LATEST snapshot that is <= 16:00 ET (Market Close)
                            # This avoids showing 18:00 after hours garbage.
                            
                            # UTC 21:00 is approx 16:00 ET
                            # We can also just avoid very late timestamps if we know today's date.
                            # Simpler heuristic: Look for valid volume/price profile? No.
                            # Time-based: Scan history.
                            
                            candidates = []
                            for h in history:
                                try:
                                    s = json.loads(h)
                                    ts = s.get('timestamp', 0)
                                    dt = datetime.fromtimestamp(ts)
                                    
                                    # 🕒 TIME FILTER (Local TR Time)
                                    # US Market Open: 17:30 TR (09:30 ET)
                                    # US Market Close: 24:00 TR (16:00 ET) -> 00:00 Next Day
                                    # After Hours: 00:00 - 04:00 TR (16:00 - 20:00 ET)
                                    
                                    # User Request: "Delete 23.59 sonrası" (Reject after 23:59)
                                    # This means reject 00:00, 01:00, ... onwards.
                                    # Valid hours: 13, 14, 15, ... 23.
                                    # Invalid hours: 00, 01, 02 ... 12.
                                    
                                    if 0 <= dt.hour <= 12:
                                        # This excludes 00:00 (16:00 ET) and 01:00 (17:00 ET) etc.
                                        # Strictly <= 23:59.
                                        continue
                                        
                                    candidates.append(s)
                                except:
                                    pass
                                    
                            if candidates:
                                # Sort by timestamp descending (newest first)
                                candidates.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
                                
                                # Take the newest VALID snapshot (which should be 23:59 or 00:00 or 16:00 ET)
                                best_snap = candidates[0] 
                                
                            if best_snap:
                                # Extract L1 basics
                                l1_update = {
                                    'bid': best_snap.get('bid'),
                                    'ask': best_snap.get('ask'),
                                    'last': best_snap.get('last'),
                                    'volume': best_snap.get('volume'),
                                    'timestamp': best_snap.get('timestamp')
                                }
                                # Force update
                                if symbol not in self._live_data:
                                    self._live_data[symbol] = {}
                                self._live_data[symbol].update(l1_update)
                                self._dirty_symbols.add(symbol)
                                loaded_count += 1

                    # 🛡️ VALIDATION & FALLBACK (New Logic)
                    # Check if loaded snapshots are "bad" (e.g. After Hours noise with huge spreads).
                    # Heuristic: If > 50 items have spread > 0.90, assume ALL are bad.
                    
                    bad_spread_count = 0
                    total_checked = 0
                    
                    for sym, data in self._live_data.items():
                        bid = float(data.get('bid', 0) or 0)
                        ask = float(data.get('ask', 0) or 0)
                        if bid > 0 and ask > 0:
                            spread = ask - bid
                            if spread > 0.90:
                                bad_spread_count += 1
                        total_checked += 1
                        
                    logger.info(f"💀 Snapshot Validation: {bad_spread_count}/{total_checked} symbols have spread > 0.90")
                    
                    # TRIGGER CONDITION:
                    # 1. Too many bad spreads (>50) - Data exists but is garbage/after-hours.
                    # 2. Too few loaded symbols (<50) - Data is missing/wiped (Fresh start case).
                    force_synthetic = False
                    if bad_spread_count > 50:
                        logger.warning(f"⚠️ DETECTED BAD SNAPSHOT DATA ({bad_spread_count} symbols with >0.90 spread).")
                        force_synthetic = True
                    elif loaded_count < 50:
                        logger.warning(f"⚠️ INSUFFICIENT SNAPSHOT DATA (Only {loaded_count} symbols loaded).")
                        force_synthetic = True
                    
                    if force_synthetic:
                        logger.warning("🔄 Switching to SYNTHETIC mode (PrevClose +/- 0.15).")
                        
                        # Generate SYNTHETIC data for ALL symbols based on Prev Close
                        import random
                        import time
                        
                        syn_count = 0
                        for sym in symbols:
                            # ensuring we have static data (prev close)
                            static = self._static_data.get(sym, {})
                            prev_close = float(static.get('prev_close', 0) or 0)
                            
                            if prev_close > 0:
                                # Generate fake tight market within +/- 0.15 of prev_close
                                # User rule: "prev.close a yakin -+0.15 cent icerisinde"
                                
                                # Random shift from prev_close (-0.10 to +0.10)
                                center = prev_close + random.uniform(-0.10, 0.10)
                                
                                # Create mock spread (0.01 to 0.05)
                                half_spread = random.uniform(0.01, 0.05)
                                
                                new_bid = round(center - half_spread, 2)
                                new_ask = round(center + half_spread, 2)
                                new_last = round(center, 2) # Last is center
                                
                                # Update L1
                                if sym not in self._live_data:
                                    self._live_data[sym] = {}
                                    
                                self._live_data[sym].update({
                                    'bid': new_bid,
                                    'ask': new_ask,
                                    'last': new_last,
                                    'volume': 0, # Synthetic start
                                    'timestamp': time.time() # Synthetic: use NOW to pass freshness checks
                                })
                                self._dirty_symbols.add(sym)
                                syn_count += 1
                                
                        logger.info(f"🧪 Generated SYNTHETIC start data for {syn_count} symbols (Base: PrevClose)")
                            
                    logger.info(f"💀 Loaded snapshots for {loaded_count} symbols from Redis")
                    return True
                    
                except Exception as e:
                    logger.error(f"❌ Error loading snapshots for Lifeless Mode: {e}")
                    # Revert if failed? No, keep flag but warn.
                    return False
            else:
                self._simulation_offsets.clear() # Clear offsets on disable
                logger.info("🟢 Resuming Live Data Feed")
                return True

    def is_lifeless_mode(self) -> bool:
        return self._lifeless_mode
        
    def shuffle_lifeless_data(self) -> int:
        """
        Simulate market movement by shuffling Prices (Bid/Ask/Last).
        
        Range: +/- 0.05 to 0.15 (random direction)
        Constraint: Bid <= Last <= Ask
        
        Returns:
            Number of symbols shuffled
        """
        import random
        
        if not self._lifeless_mode:
            logger.warning("⚠️ Cannot shuffle: Lifeless Mode not active")
            return 0
            
        count = 0
        with self._data_lock:
            # Clear previous offsets to avoid cumulative drift (or maybe we want cumulative? User said "shuffle derse... oynuyor")
            # Let's start fresh from the *snapshot* base? 
            # No, if we modify _live_data directly, we lose the original snapshot.
            # Ideally we should store the *original* snapshot separately.
            # But efficiently... let's assume we just perturb the *current* state.
            # User Key Requirement: "bid,ask,last ve truth,volav... 0.05-0.15 bandinda oynuyor"
            
            # Calculate realistic shuffle
            for symbol, data in self._live_data.items():
                if not data: continue
                
                try:
                    # 1. New Offset (Small jitter)
                    current_offset = self._simulation_offsets.get(symbol, 0.0)
                    jitter = random.uniform(-0.02, 0.02)
                    new_offset = round(current_offset + jitter, 2)
                    # Limit overall drift
                    if new_offset > 0.50: new_offset = 0.50
                    if new_offset < -0.50: new_offset = -0.50
                    
                    self._simulation_offsets[symbol] = new_offset
                    
                    # 2. Applying to prices (Base + Offset)
                    # Get base price (from prev_close or existing last if reasonable)
                    static = self._static_data.get(symbol, {})
                    base_price = float(static.get('prev_close', 0))
                    if base_price <= 0:
                         base_price = float(data.get('last', 0))
                    
                    if base_price > 0:
                        # 3. Simulate Realistic Spread
                        # User Request: "Mostly 0.03-0.05, but some 0.35+"
                        # Distribution: 70% Small, 20% Medium, 10% Large
                        rand_spread = random.random()
                        if rand_spread < 0.70:
                            # Tight: 0.02 - 0.06
                            spread = round(random.uniform(0.02, 0.06), 2)
                        elif rand_spread < 0.90:
                            # Medium: 0.07 - 0.15
                            spread = round(random.uniform(0.07, 0.15), 2)
                        else:
                            # Wide: 0.20 - 0.45
                            spread = round(random.uniform(0.20, 0.45), 2)
                        
                        # Apply offset to base to get "Center Price"
                        center_price = base_price + new_offset
                        
                        # Construct Bid/Ask around center
                        # (Bid is center - half spread, Ask is center + half spread)
                        # Jitter the center slightly so it's not always perfect mid
                        micro_move = random.uniform(-0.02, 0.02)
                        center_price += micro_move
                        
                        new_bid = round(center_price - (spread / 2), 2)
                        new_ask = round(center_price + (spread / 2), 2)
                        
                        # Ensure spread is maintained and prices > 0
                        if new_ask <= new_bid: new_ask = new_bid + 0.01
                        
                        # 4. Realistic Last Price (Stickiness to Bid/Ask)
                        # User Request: "80-90% close to one side"
                        # 45% Hit Bid, 45% Take Ask, 10% Random Inside
                        decision = random.random()
                        if decision < 0.45:
                            new_last = new_bid # Sell side pressure
                        elif decision < 0.90:
                            new_last = new_ask # Buy side pressure
                        else:
                            new_last = round(random.uniform(new_bid, new_ask), 2)
                            
                        # Update Live Data (In-Place)
                        data['bid'] = new_bid
                        data['ask'] = new_ask
                        data['last'] = new_last
                        # Force update timestamp
                        import time
                        data['timestamp'] = time.time() 
                        
                    self._dirty_symbols.add(symbol)
                    count += 1
                except Exception as e:
                    # logger.warning(f"Error shuffling {symbol}: {e}")
                    pass
                    
        logger.info(f"🎲 Shuffled {count} symbols (Realistic Spread 0.05-0.45) in Lifeless Mode")
        return count

    def get_simulation_offset(self, symbol: str) -> float:
        """Get the current simulation price offset for a symbol"""
        return self._simulation_offsets.get(symbol, 0.0)

    # =========================================================================
    # STATIC DATA (CSV - loaded once at startup)
    # =========================================================================
    
    def load_static_data(self, csv_path: Optional[str] = None) -> bool:
        """
        Load static data from CSV (ONLY at startup).
        
        ⚠️ This should ONLY be called at application startup.
        Runtime CSV reads are FORBIDDEN for trading-grade performance.
        
        Args:
            csv_path: Path to janalldata.csv
            
        Returns:
            True if loaded successfully
        """
        import pandas as pd
        
        start_time = time.time()
        
        with self._data_lock:
            self._static_status = DataStatus.LOADING
            
            try:
                # Find CSV file
                if csv_path:
                    filepath = Path(csv_path)
                else:
                    filepath = self._find_csv_file()
                
                if not filepath or not filepath.exists():
                    logger.error(f"❌ CSV file not found: {csv_path or 'janalldata.csv'}")
                    self._static_status = DataStatus.ERROR
                    return False
                
                logger.info(f"📂 Loading static data from: {filepath}")
                
                # Read CSV (try different encodings)
                try:
                    df = pd.read_csv(filepath, encoding='utf-8')
                except UnicodeDecodeError:
                    df = pd.read_csv(filepath, encoding='latin-1')
                
                # Clear existing data
                self._static_data.clear()
                
                # Load data keyed by PREF_IBKR
                pref_col = 'PREF IBKR'
                if pref_col not in df.columns:
                    logger.error(f"❌ Primary key column '{pref_col}' not found")
                    self._static_status = DataStatus.ERROR
                    return False
                
                for _, row in df.iterrows():
                    symbol = str(row[pref_col]).strip()
                    if not symbol or symbol == 'nan':
                        continue
                    
                    # Store all columns as dict
                    self._static_data[symbol] = row.to_dict()
                
                # 🚫 Apply excluded list filtering (qe_excluded.csv)
                try:
                    import os
                    import csv as csv_module
                    excluded_symbols = set()
                    excluded_path = Path(os.getcwd()) / 'qe_excluded.csv'
                    if excluded_path.exists():
                        with open(excluded_path, 'r', encoding='utf-8') as f:
                            reader = csv_module.reader(f)
                            for row in reader:
                                if row:
                                    excluded_symbols.update([s.strip().upper() for s in row if s.strip()])
                    
                    if excluded_symbols:
                        # Remove excluded symbols from static data
                        removed_count = 0
                        keys_to_remove = [sym for sym in self._static_data.keys() if sym.upper() in excluded_symbols]
                        for sym in keys_to_remove:
                            del self._static_data[sym]
                            removed_count += 1
                        
                        if removed_count > 0:
                            logger.info(f"🚫 Excluded {removed_count} symbols from DataFabric (qe_excluded.csv)")
                except Exception as e:
                    logger.warning(f"⚠️ Could not apply excluded list: {e}")
                
                # 🔧 Load GROUP info from group files (ssfinek*.csv)
                # This is critical for GroupSelector UI component
                try:
                    from app.market_data.grouping import resolve_primary_group
                    group_count = 0
                    for symbol, data in self._static_data.items():
                        if not data.get('GROUP'):
                            group = resolve_primary_group(data, symbol)
                            if group:
                                data['GROUP'] = group
                                group_count += 1
                    logger.info(f"📁 Resolved GROUP for {group_count} symbols from group files")
                except Exception as e:
                    logger.warning(f"⚠️ Could not load group files: {e}")
                
                # Update status
                self._static_status = DataStatus.READY
                self._static_load_time = datetime.now()
                
                # Update stats
                load_time_ms = (time.time() - start_time) * 1000
                self._stats.static_symbols = len(self._static_data)
                self._stats.static_load_time_ms = load_time_ms
                self._stats.last_static_load = self._static_load_time
                
                logger.info(
                    f"✅ Static data loaded: {len(self._static_data)} symbols "
                    f"in {load_time_ms:.1f}ms"
                )
                return True
                
            except Exception as e:
                logger.error(f"❌ Error loading static data: {e}", exc_info=True)
                self._static_status = DataStatus.ERROR
                return False
    
    def _find_csv_file(self) -> Optional[Path]:
        """Find janalldata.csv file"""
        import os
        
        possible_paths = [
            # PRIORITY 1: Ana dizin (merge_csvs.py buraya yazar)
            Path(r"C:\StockTracker\janalldata.csv"),
            Path(r"C:\StockTracker\janall\janalldata.csv"),
            
            # PRIORITY 2: CWD
            Path(os.getcwd()) / 'janalldata.csv',
            Path(os.getcwd()) / 'janall' / 'janalldata.csv',
            
            # Fallbacks
            Path(r"C:\StockTracker\janall\janallapp\janalldata.csv"),
            Path(os.getcwd()).parent / 'janalldata.csv',
            Path(__file__).parent.parent.parent.parent / 'janalldata.csv',
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        return None
    
    def get_static(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get static data for symbol (from RAM - no disk I/O).
        
        Args:
            symbol: PREF_IBKR symbol
            
        Returns:
            Static data dict or None
        """
        return self._static_data.get(symbol)
    
    def get_all_static_symbols(self) -> List[str]:
        """Get all symbols with static data"""
        return list(self._static_data.keys())
    
    # =========================================================================
    # LIVE DATA (Hammer - real-time updates)
    # =========================================================================
    
    def update_live(self, symbol: str, data: Dict[str, Any]) -> None:
        """
        Update live market data for symbol.
        
        Called by Hammer feed handler.
        
        🔑 CRITICAL: symbol MUST be in PREF_IBKR format (e.g., "RLJ PRA")
        This ensures key consistency across all DataFabric layers.
        
        Args:
            symbol: PREF_IBKR symbol (display format, e.g., "RLJ PRA")
            data: Live market data {bid, ask, last, volume, timestamp}
        """
        with self._data_lock:
            # 💀 LIFELESS MODE CHECK
            if self._lifeless_mode:
                # Block live updates!
                return

            # 🔑 KEY CONSISTENCY: Ensure symbol is in PREF_IBKR format
            # SymbolMapper already converts Hammer format → PREF_IBKR format
            # But we double-check here for safety
            symbol = str(symbol).strip()
            
            # Merge with existing data (don't overwrite completely)
            if symbol not in self._live_data:
                self._live_data[symbol] = {}
            
            # Update only provided fields
            self._live_data[symbol].update(data)
            self._live_data[symbol]['_last_update'] = datetime.now()
            
            # Mark as dirty (needs derived recalculation)
            self._dirty_symbols.add(symbol)
            
            # 🔍 DEBUG: Log key consistency (first few updates only)
            if self._stats.live_updates_count < 5:
                logger.debug(
                    f"🔑 [KEY_DEBUG] update_live: symbol='{symbol}' | "
                    f"static_exists={symbol in self._static_data} | "
                    f"bid={data.get('bid')}"
                )
            
            # Update stats
            self._stats.live_updates_count += 1
            self._stats.live_symbols = len(self._live_data)
            
            self._last_live_update = datetime.now()
    
    def update_live_batch(self, updates: Dict[str, Dict[str, Any]]) -> None:
        """
        Batch update live data (more efficient).
        
        Args:
            updates: {symbol: {bid, ask, last, ...}}
        """
        with self._data_lock:
            # 💀 LIFELESS MODE CHECK
            if self._lifeless_mode:
                return

            now = datetime.now()
            for symbol, data in updates.items():
                if symbol not in self._live_data:
                    self._live_data[symbol] = {}
                self._live_data[symbol].update(data)
                self._live_data[symbol]['_last_update'] = now
                self._dirty_symbols.add(symbol)
            
            self._stats.live_updates_count += len(updates)
            self._stats.live_symbols = len(self._live_data)
            self._last_live_update = now
    
    def get_live(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get live market data for symbol (from RAM, with Redis fallback).
        
        🔄 FALLBACK LOGIC:
        1. First check in-memory _live_data (fastest)
        2. If missing, try Redis live:{symbol} (recent data)
        3. If still missing, try Redis market_data:snapshot:{symbol} (last snapshot)
        
        Args:
            symbol: PREF_IBKR symbol
            
        Returns:
            Live data dict or None
        """
        # 1. Check in-memory first (fastest)
        live = self._live_data.get(symbol)
        if live and live.get('bid') is not None and live.get('ask') is not None:
            return live
        
        # 2. FALLBACK: Try Redis if in-memory is missing or incomplete
        # This helps when Hammer feed hasn't updated yet or symbol wasn't subscribed
        try:
            from app.core.redis_client import get_redis_client
            import json
            
            redis_client = get_redis_client()
            if redis_client and redis_client.sync:
                # Try live:{symbol} first (most recent)
                live_key = f"live:{symbol}"
                live_json = redis_client.sync.get(live_key)
                
                if live_json:
                    try:
                        redis_live = json.loads(live_json)
                        # Validate it has bid/ask
                        if redis_live.get('bid') is not None and redis_live.get('ask') is not None:
                            # Update in-memory cache for next time
                            with self._data_lock:
                                if symbol not in self._live_data:
                                    self._live_data[symbol] = {}
                                self._live_data[symbol].update(redis_live)
                                self._live_data[symbol]['_last_update'] = datetime.now()
                            logger.debug(f"🔄 [REDIS_FALLBACK] Loaded {symbol} from Redis live:{symbol}")
                            return self._live_data[symbol]
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(f"Failed to parse Redis live:{symbol}: {e}")
                
                # Try market:l1:{symbol} (L1Feed Terminal streaming data — 2s refresh, 120s TTL)
                l1_key = f"market:l1:{symbol}"
                l1_json = redis_client.sync.get(l1_key)
                
                if l1_json:
                    try:
                        l1_data = json.loads(l1_json)
                        bid = l1_data.get('bid')
                        ask = l1_data.get('ask')
                        if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0:
                            redis_live = {
                                'bid': float(bid),
                                'ask': float(ask),
                                'last': float(l1_data.get('last', 0)),
                                'timestamp': l1_data.get('ts'),
                            }
                            with self._data_lock:
                                if symbol not in self._live_data:
                                    self._live_data[symbol] = {}
                                self._live_data[symbol].update(redis_live)
                                self._live_data[symbol]['_last_update'] = datetime.now()
                            logger.debug(f"🔄 [REDIS_FALLBACK] Loaded {symbol} from Redis market:l1:{symbol}")
                            return self._live_data[symbol]
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(f"Failed to parse Redis market:l1:{symbol}: {e}")
                
                # Try market_data:snapshot:{symbol} as third fallback
                snapshot_key = f"market_data:snapshot:{symbol}"
                snapshot_json = redis_client.sync.get(snapshot_key)
                
                if snapshot_json:
                    try:
                        snapshot = json.loads(snapshot_json)
                        # Extract L1 data
                        redis_live = {
                            'bid': snapshot.get('bid'),
                            'ask': snapshot.get('ask'),
                            'last': snapshot.get('last'),
                            'volume': snapshot.get('volume'),
                            'prev_close': snapshot.get('prev_close'),
                            'timestamp': snapshot.get('timestamp')
                        }
                        # Validate it has bid/ask
                        if redis_live.get('bid') is not None and redis_live.get('ask') is not None:
                            # Update in-memory cache
                            with self._data_lock:
                                if symbol not in self._live_data:
                                    self._live_data[symbol] = {}
                                self._live_data[symbol].update(redis_live)
                                self._live_data[symbol]['_last_update'] = datetime.now()
                            logger.debug(f"🔄 [REDIS_FALLBACK] Loaded {symbol} from Redis snapshot")
                            return self._live_data[symbol]
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(f"Failed to parse Redis snapshot:{symbol}: {e}")
        except Exception as e:
            # Non-critical - Redis fallback failed, continue with None
            logger.debug(f"Redis fallback failed for {symbol}: {e}")
        
        # Return None if nothing found
        return self._live_data.get(symbol) if symbol in self._live_data else None
    
    def get_live_symbols_count(self) -> int:
        """Get count of symbols with live data"""
        return len(self._live_data)

    def get_all_live_symbols(self) -> List[str]:
        """Get all symbols with live data"""
        return list(self._live_data.keys())
    
    def load_live_from_redis(self) -> int:
        """
        Load live market data from Redis (fallback when Hammer feed hasn't started).
        
        Tries two Redis keys:
        1. live:{symbol} - Most recent live data
        2. market_data:snapshot:{symbol} - Last snapshot
        
        Returns:
            Number of symbols loaded
        """
        try:
            from app.core.redis_client import get_redis_client
            import json
            
            redis_client = get_redis_client()
            if not redis_client or not redis_client.sync:
                logger.debug("Redis not available for live data fallback")
                return 0
            
            symbols = self.get_all_static_symbols()
            loaded_count = 0
            
            for symbol in symbols:
                # Skip if already in memory with valid data
                existing = self._live_data.get(symbol, {})
                if existing.get('bid') is not None and existing.get('ask') is not None:
                    continue
                
                # Try live:{symbol} first
                live_key = f"live:{symbol}"
                live_json = redis_client.sync.get(live_key)
                
                if live_json:
                    try:
                        redis_live = json.loads(live_json)
                        if redis_live.get('bid') is not None and redis_live.get('ask') is not None:
                            with self._data_lock:
                                if symbol not in self._live_data:
                                    self._live_data[symbol] = {}
                                self._live_data[symbol].update(redis_live)
                                self._live_data[symbol]['_last_update'] = datetime.now()
                            loaded_count += 1
                            continue
                    except (json.JSONDecodeError, Exception):
                        pass
                
                # Try market_data:snapshot:{symbol} as fallback
                snapshot_key = f"market_data:snapshot:{symbol}"
                snapshot_json = redis_client.sync.get(snapshot_key)
                
                if snapshot_json:
                    try:
                        snapshot = json.loads(snapshot_json)
                        redis_live = {
                            'bid': snapshot.get('bid'),
                            'ask': snapshot.get('ask'),
                            'last': snapshot.get('last'),
                            'volume': snapshot.get('volume'),
                            'prev_close': snapshot.get('prev_close'),
                            'timestamp': snapshot.get('timestamp')
                        }
                        if redis_live.get('bid') is not None and redis_live.get('ask') is not None:
                            with self._data_lock:
                                if symbol not in self._live_data:
                                    self._live_data[symbol] = {}
                                self._live_data[symbol].update(redis_live)
                                self._live_data[symbol]['_last_update'] = datetime.now()
                            loaded_count += 1
                    except (json.JSONDecodeError, Exception):
                        pass
            
            if loaded_count > 0:
                logger.info(f"🔄 [REDIS_FALLBACK] Loaded {loaded_count} symbols from Redis (live data fallback)")
                self._stats.live_symbols = len(self._live_data)
            
            return loaded_count
            
        except Exception as e:
            logger.warning(f"Failed to load live data from Redis: {e}")
            return 0
    
    # =========================================================================
    # ETF DATA (for benchmark calculations)
    # =========================================================================
    
    def update_etf_live(self, etf_symbol: str, data: Dict[str, Any]) -> None:
        """Update live ETF data"""
        with self._data_lock:
            self._etf_live[etf_symbol] = data
            self._etf_live[etf_symbol]['_last_update'] = datetime.now()
            
            # Mark all symbols as dirty (benchmark changed)
            self._dirty_symbols.update(self._static_data.keys())
    
    def set_etf_prev_close(self, etf_symbol: str, prev_close: float) -> None:
        """Set ETF previous close"""
        with self._data_lock:
            self._etf_prev_close[etf_symbol] = prev_close
    
    def get_etf_live(self, etf_symbol: str) -> Optional[Dict[str, Any]]:
        """Get live ETF data"""
        return self._etf_live.get(etf_symbol)
    
    def get_etf_prev_close(self, etf_symbol: str) -> Optional[float]:
        """Get ETF previous close"""
        return self._etf_prev_close.get(etf_symbol)
    
    def get_all_etf_data(self) -> Dict[str, Dict[str, Any]]:
        """Get all ETF live data"""
        return dict(self._etf_live)
    
    def get_all_etf_prev_close(self) -> Dict[str, float]:
        """Get all ETF previous close"""
        return dict(self._etf_prev_close)
    
    # =========================================================================
    # DERIVED DATA (calculated metrics)
    # =========================================================================
    
    def update_derived(self, symbol: str, metrics: Dict[str, Any]) -> None:
        """
        Update derived metrics for symbol.
        
        Called after calculation (Fbtot, GORT, Final_BB, etc.)
        
        🔑 CRITICAL: symbol MUST be in PREF_IBKR format (e.g., "RLJ PRA")
        This ensures key consistency across all DataFabric layers.
        
        Args:
            symbol: PREF_IBKR symbol (display format, e.g., "RLJ PRA")
            metrics: Calculated metrics
        """
        with self._data_lock:
            # 🔑 KEY CONSISTENCY: Ensure symbol is in PREF_IBKR format
            symbol = str(symbol).strip()
            
            if symbol not in self._derived_data:
                self._derived_data[symbol] = {}
            
            self._derived_data[symbol].update(metrics)
            self._derived_data[symbol]['_last_compute'] = datetime.now()
            
            # ⚠️ DO NOT remove from dirty set here!
            # Dirty symbols must remain dirty until WebSocket broadcast sends them
            # WebSocket broadcast will clear dirty symbols after sending
            
            # Update stats
            self._stats.derived_computes_count += 1
            self._stats.derived_symbols = len(self._derived_data)
    
    def get_derived(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get derived metrics for symbol"""
        return self._derived_data.get(symbol)
    
    def get_dirty_symbols(self) -> Set[str]:
        """Get symbols that need recalculation"""
        return self._dirty_symbols.copy()
    
    def clear_dirty(self, symbol: str) -> None:
        """Clear dirty flag for symbol"""
        self._dirty_symbols.discard(symbol)
    
    # =========================================================================
    # SNAPSHOT (combined view for algo)
    # =========================================================================
    
    def get_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get combined snapshot for symbol.
        
        Merges: static + live + derived
        
        Args:
            symbol: PREF_IBKR symbol
            
        Returns:
            Combined snapshot dict
        """
        with self._data_lock:
            static = self._static_data.get(symbol, {})
            live = self._live_data.get(symbol, {})
            derived = self._derived_data.get(symbol, {})
            
            if not static and not live:
                return None
            
            # Merge (derived > live > static priority)
            snapshot = {}
            snapshot.update(static)
            snapshot.update(live)
            snapshot.update(derived)
            
            # Add metadata
            snapshot['_symbol'] = symbol
            snapshot['_has_static'] = bool(static)
            snapshot['_has_live'] = bool(live)
            snapshot['_has_derived'] = bool(derived)
            
            self._stats.snapshot_requests_count += 1
            
            return snapshot
    
    def get_all_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """Get snapshots for all symbols with data"""
        with self._data_lock:
            all_symbols = set(self._static_data.keys()) | set(self._live_data.keys())
            return {
                symbol: self.get_snapshot(symbol)
                for symbol in all_symbols
                if self.get_snapshot(symbol)
            }
    
    # =========================================================================
    # GROUP WEIGHTS
    # =========================================================================
    
    def load_group_weights(self, csv_path: Optional[str] = None) -> bool:
        """Load group weights from CSV"""
        import pandas as pd
        
        try:
            if csv_path:
                filepath = Path(csv_path)
            else:
                # Search for groupweights.csv
                possible_paths = [
                    Path(r"C:\StockTracker\janall\groupweights.csv"),
                    Path.cwd() / 'janall' / 'groupweights.csv',
                    Path.cwd() / 'groupweights.csv',
                ]
                filepath = None
                for p in possible_paths:
                    if p.exists():
                        filepath = p
                        break
            
            if not filepath or not filepath.exists():
                logger.warning("groupweights.csv not found, using defaults")
                return False
            
            df = pd.read_csv(filepath)
            
            with self._data_lock:
                self._group_weights.clear()
                for _, row in df.iterrows():
                    group = str(row.get('GROUP', row.get('group', ''))).strip()
                    weight = float(row.get('WEIGHT', row.get('weight', 0)))
                    if group:
                        self._group_weights[group] = weight
            
            logger.info(f"✅ Loaded {len(self._group_weights)} group weights")
            return True
            
        except Exception as e:
            logger.warning(f"Error loading group weights: {e}")
            return False
    
    def get_group_weight(self, group: str) -> float:
        """Get weight for group"""
        return self._group_weights.get(group, 0.0)
    
    def get_all_group_weights(self) -> Dict[str, float]:
        """Get all group weights"""
        return dict(self._group_weights)
    
    # =========================================================================
    # STATUS & STATS
    # =========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get data fabric status"""
        return {
            'static_status': self._static_status.value,
            'live_status': self._live_status.value,
            'static_symbols': len(self._static_data),
            'live_symbols': len(self._live_data),
            'derived_symbols': len(self._derived_data),
            'etf_symbols': len(self._etf_live),
            'dirty_symbols': len(self._dirty_symbols),
            'static_load_time': self._static_load_time.isoformat() if self._static_load_time else None,
            'last_live_update': self._last_live_update.isoformat() if self._last_live_update else None,
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        return {
            'static_symbols': self._stats.static_symbols,
            'live_symbols': self._stats.live_symbols,
            'derived_symbols': self._stats.derived_symbols,
            'static_load_time_ms': self._stats.static_load_time_ms,
            'last_static_load': self._stats.last_static_load.isoformat() if self._stats.last_static_load else None,
            'live_updates_count': self._stats.live_updates_count,
            'derived_computes_count': self._stats.derived_computes_count,
            'snapshot_requests_count': self._stats.snapshot_requests_count,
        }
    
    def is_ready(self) -> bool:
        """Check if data fabric is ready for trading"""
        return (
            self._static_status == DataStatus.READY and
            len(self._live_data) > 0
        )
    
    # =========================================================================
    # 🟢 FAST PATH - L1 Data + FAST Scores (for UI + Algo)
    # =========================================================================
    
    def _calculate_maxalw(self, avg_adv: Optional[float]) -> Optional[int]:
        """
        Calculate MAXALW = AVG_ADV / 10 (static data).
        
        Args:
            avg_adv: AVG_ADV value from static data
            
        Returns:
            MAXALW value (int) or None if AVG_ADV is invalid
        """
        if avg_adv is not None:
            try:
                avg_adv_float = float(avg_adv)
                if avg_adv_float > 0:
                    return int(avg_adv_float / 10)
            except (ValueError, TypeError):
                pass
        return None
    
    def get_fast_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get FAST PATH snapshot for symbol.
        
        🔑 CRITICAL: symbol MUST be in PREF_IBKR format (e.g., "RLJ PRA")
        This is the SINGLE SOURCE OF TRUTH for UI and Algo.
        
        🟢 FAST PATH includes:
        - L1 data: bid, ask, last, volume, timestamp
        - Static data: prev_close, AVG_ADV, FINAL_THG, GROUP, CGRUP
        - FAST scores: Final_BB, Final_FB, Final_SAS, Final_SFS, Fbtot, SFStot, GORT
        - daily_change, benchmark_chg
        
        ⚠️ FAST PATH NEVER includes:
        - GOD, ROD, GRPAN (tick-by-tick calculations)
        
        This is what UI and Algo should use for instant display.
        Janall-style simplicity: one call, all data.
        """
        with self._data_lock:
            # 🔑 KEY CONSISTENCY: Ensure symbol is in PREF_IBKR format
            symbol = str(symbol).strip()
            
            static = self._static_data.get(symbol, {})
            live = self._live_data.get(symbol, {})
            derived = self._derived_data.get(symbol, {})
            
            # 🔍 DEBUG: Log key consistency and bid/ask/last values (first few reads only)
            if not hasattr(self, '_fast_snapshot_debug_count'):
                self._fast_snapshot_debug_count = {}
            if symbol not in self._fast_snapshot_debug_count:
                self._fast_snapshot_debug_count[symbol] = 0
            if self._fast_snapshot_debug_count[symbol] < 3:
                self._fast_snapshot_debug_count[symbol] += 1
                logger.debug(
                    f"🔑 [FAST_SNAPSHOT_DEBUG] {symbol}: "
                    f"static_exists={bool(static)} | "
                    f"live_exists={bool(live)} | "
                    f"derived_exists={bool(derived)} | "
                    f"live.bid={live.get('bid')} | "
                    f"live.ask={live.get('ask')} | "
                    f"live.last={live.get('last')} | "
                    f"live_keys={list(live.keys()) if live else []}"
                )

            # 🛠️ APPLY SIMULATION OFFSETS (Lifeless Mode)
            # REMOVED: Offsets are now baked directly into _live_data by shuffle_lifeless_data.
            # This prevents double-application and ensures get_live() consumers also see the shuffled data.
            # if self._lifeless_mode:
            #    pass
            
            if not static and not live:
                return None
            
            # Build FAST snapshot (only fast fields)
            # Convert datetime to ISO string for JSON serialization
            last_update = live.get('_last_update')
            if last_update and hasattr(last_update, 'isoformat'):
                last_update = last_update.isoformat()
            
            timestamp = live.get('timestamp')
            if timestamp and hasattr(timestamp, 'isoformat'):
                timestamp = timestamp.isoformat()
            
            fast_snapshot = {
                # Identity
                '_symbol': symbol,
                
                # L1 Market Data (FAST - from Hammer)
                'bid': live.get('bid'),
                'ask': live.get('ask'),
                'last': live.get('last'),
                'volume': live.get('volume'),
                'timestamp': timestamp,
                '_last_update': last_update,
                
                # Static Data (from CSV - loaded once)
                'prev_close': static.get('prev_close'),
                'AVG_ADV': static.get('AVG_ADV'),
                'FINAL_THG': static.get('FINAL_THG'),
                'SHORT_FINAL': static.get('SHORT_FINAL'),
                'GROUP': static.get('GROUP'),
                'CMON': static.get('CMON') or static.get('cmon'),  # Company name
                'CGRUP': static.get('CGRUP') or static.get('cgrup'),
                # Calculate MAXALW = AVG_ADV / 10 (static data)
                'MAXALW': self._calculate_maxalw(static.get('AVG_ADV')),
                'SMA63 chg': static.get('SMA63 chg'),
                'SMA246 chg': static.get('SMA246 chg'),
                # Frontend compatibility aliases
                'SMA63chg': static.get('SMA63 chg'),  # Frontend expects SMA63chg
                'SMA246chg': static.get('SMA246 chg'),  # Frontend expects SMA246chg
                # Frontend compatibility aliases
                'SMA63chg': static.get('SMA63 chg'),  # Frontend expects SMA63chg
                'SMA246chg': static.get('SMA246 chg'),  # Frontend expects SMA246chg
                
                # FAST Derived Scores (calculated from L1 + CSV - Janall format)
                # Final Scores (800 katsayısı ile)
                'Final_BB_skor': derived.get('Final_BB_skor'),
                'Final_FB_skor': derived.get('Final_FB_skor'),
                'Final_AB_skor': derived.get('Final_AB_skor'),
                'Final_AS_skor': derived.get('Final_AS_skor'),
                'Final_FS_skor': derived.get('Final_FS_skor'),
                'Final_BS_skor': derived.get('Final_BS_skor'),
                'Final_SAS_skor': derived.get('Final_SAS_skor'),
                'Final_SFS_skor': derived.get('Final_SFS_skor'),
                'Final_SBS_skor': derived.get('Final_SBS_skor'),
                
                # Group-based metrics
                'Fbtot': derived.get('Fbtot'),
                'SFStot': derived.get('SFStot'),
                'GORT': derived.get('GORT'),
                
                # Ucuzluk/Pahalılık scores (Janall format)
                'Bid_buy_ucuzluk_skoru': derived.get('Bid_buy_ucuzluk_skoru'),
                'Front_buy_ucuzluk_skoru': derived.get('Front_buy_ucuzluk_skoru'),
                'Ask_buy_ucuzluk_skoru': derived.get('Ask_buy_ucuzluk_skoru'),
                'Ask_sell_pahalilik_skoru': derived.get('Ask_sell_pahalilik_skoru'),
                'Front_sell_pahalilik_skoru': derived.get('Front_sell_pahalilik_skoru'),
                'Bid_sell_pahalilik_skoru': derived.get('Bid_sell_pahalilik_skoru'),
                
                # Legacy aliases
                'bid_buy_ucuzluk': derived.get('bid_buy_ucuzluk'),
                'front_buy_ucuzluk': derived.get('front_buy_ucuzluk'),
                'ask_buy_ucuzluk': derived.get('ask_buy_ucuzluk'),
                'ask_sell_pahalilik': derived.get('ask_sell_pahalilik'),
                'front_sell_pahalilik': derived.get('front_sell_pahalilik'),
                'bid_sell_pahalilik': derived.get('bid_sell_pahalilik'),
                
                # Benchmark
                'Benchmark_Type': derived.get('Benchmark_Type') or derived.get('benchmark_type'),
                'Benchmark_Chg': derived.get('Benchmark_Chg') or derived.get('benchmark_chg'),
                'benchmark_type': derived.get('benchmark_type'),
                'benchmark_chg': derived.get('benchmark_chg'),
                # NEW: Group-based benchmark
                'bench_chg': derived.get('bench_chg'),  # Group average daily change
                'bench_source': derived.get('bench_source'),  # Source description
                'daily_chg': derived.get('daily_chg'),  # Stock's own daily change (cents)
                
                # Other metrics
                'daily_change': derived.get('daily_change'),
                'Spread': derived.get('Spread') or derived.get('spread'),
                'spread': derived.get('spread'),
                
                # Status flags
                '_has_static': bool(static),
                '_has_live': bool(live),
                '_has_derived': bool(derived),
            }
            
            return fast_snapshot
    
    def get_all_fast_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """
        Get FAST snapshots for all symbols.
        
        🟢 This is what UI tables should use - instant, no tick-by-tick.
        
        ⚠️ IMPORTANT: Only returns symbols from _static_data (janalldata.csv).
        ETFs are NOT included here - they have their own ETF Strip panel.
        """
        with self._data_lock:
            # Only return symbols from static data (preferred stocks from CSV)
            # DO NOT include live-only symbols (like ETFs) - they have separate UI
            result = {}
            for symbol in self._static_data.keys():
                snap = self.get_fast_snapshot(symbol)
                if snap:
                    result[symbol] = snap
            return result
    
    # =========================================================================
    # 🔵 SLOW PATH - Tick-by-Tick Data (for Deeper Analysis ONLY)
    # =========================================================================
    
    def _init_tick_stores(self):
        """Initialize tick-by-tick stores (called lazily)"""
        if not hasattr(self, '_tick_data'):
            self._tick_data: Dict[str, Dict[str, Any]] = {}
        if not hasattr(self, '_god_data'):
            self._god_data: Dict[str, Dict[str, Any]] = {}
        if not hasattr(self, '_rod_data'):
            self._rod_data: Dict[str, Dict[str, Any]] = {}
        if not hasattr(self, '_grpan_data'):
            self._grpan_data: Dict[str, Dict[str, Any]] = {}
        if not hasattr(self, '_tick_enabled'):
            self._tick_enabled: bool = False
    
    def enable_tick_by_tick(self, enabled: bool = True) -> None:
        """
        Enable/disable tick-by-tick data collection.
        
        🔵 SLOW PATH - Only enable when Deeper Analysis tab is opened.
        """
        self._init_tick_stores()
        self._tick_enabled = enabled
        logger.info(f"{'🔵 Tick-by-tick ENABLED' if enabled else '⚫ Tick-by-tick DISABLED'}")
    
    def is_tick_by_tick_enabled(self) -> bool:
        """Check if tick-by-tick is enabled"""
        self._init_tick_stores()
        return self._tick_enabled
    
    def update_tick_data(self, symbol: str, tick: Dict[str, Any]) -> None:
        """
        Update tick-by-tick data for symbol.
        
        🔵 SLOW PATH - Only called when tick-by-tick is enabled.
        """
        self._init_tick_stores()
        if not self._tick_enabled:
            return  # Skip if not enabled
        
        with self._data_lock:
            if symbol not in self._tick_data:
                self._tick_data[symbol] = {'ticks': [], 'last_tick': None}
            
            # Store tick (keep last N ticks for rolling calculations)
            max_ticks = 1000  # Configurable
            self._tick_data[symbol]['ticks'].append(tick)
            self._tick_data[symbol]['ticks'] = self._tick_data[symbol]['ticks'][-max_ticks:]
            self._tick_data[symbol]['last_tick'] = tick
    
    def update_god(self, symbol: str, god_value: float) -> None:
        """Update GOD (Group Outlier Detection) for symbol"""
        self._init_tick_stores()
        if not self._tick_enabled:
            return
        with self._data_lock:
            self._god_data[symbol] = {'value': god_value, 'timestamp': datetime.now()}
    
    def update_rod(self, symbol: str, rod_value: float) -> None:
        """Update ROD (Relative Outlier Detection) for symbol"""
        self._init_tick_stores()
        if not self._tick_enabled:
            return
        with self._data_lock:
            self._rod_data[symbol] = {'value': rod_value, 'timestamp': datetime.now()}
    
    def update_grpan(self, symbol: str, grpan_data: Dict[str, Any]) -> None:
        """Update GRPAN (Group Analysis) for symbol"""
        self._init_tick_stores()
        if not self._tick_enabled:
            return
        with self._data_lock:
            self._grpan_data[symbol] = {**grpan_data, 'timestamp': datetime.now()}
    
    def get_deep_analysis(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get SLOW PATH deep analysis data for symbol.
        
        🔵 SLOW PATH includes:
        - GOD, ROD, GRPAN
        - Tick history
        
        ⚠️ Only available when tick-by-tick is enabled.
        """
        self._init_tick_stores()
        if not self._tick_enabled:
            return None
        
        with self._data_lock:
            return {
                'symbol': symbol,
                'god': self._god_data.get(symbol, {}).get('value'),
                'rod': self._rod_data.get(symbol, {}).get('value'),
                'grpan': self._grpan_data.get(symbol, {}),
                'tick_count': len(self._tick_data.get(symbol, {}).get('ticks', [])),
                'last_tick': self._tick_data.get(symbol, {}).get('last_tick'),
            }
    
    def get_all_deep_analysis(self) -> Dict[str, Dict[str, Any]]:
        """
        Get SLOW PATH deep analysis for all symbols.
        
        🔵 Only available when tick-by-tick is enabled.
        """
        self._init_tick_stores()
        if not self._tick_enabled:
            return {}
        
        with self._data_lock:
            all_symbols = set(self._tick_data.keys()) | set(self._god_data.keys()) | set(self._rod_data.keys())
            return {
                symbol: self.get_deep_analysis(symbol)
                for symbol in all_symbols
            }
    
    # =========================================================================
    # MANUAL RELOAD (for admin use only)
    # =========================================================================
    
    def reload_static(self, csv_path: Optional[str] = None) -> bool:
        """
        Manually reload static data.
        
        ⚠️ This is for ADMIN use only (e.g., after daily CSV update).
        Should NOT be called during normal runtime.
        """
        logger.warning("⚠️ Manual static data reload requested")
        return self.load_static_data(csv_path)


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_data_fabric: Optional[DataFabric] = None


def get_data_fabric() -> DataFabric:
    """Get global DataFabric instance (singleton)"""
    global _data_fabric
    if _data_fabric is None:
        _data_fabric = DataFabric()
    return _data_fabric


def initialize_data_fabric(csv_path: Optional[str] = None) -> DataFabric:
    """
    Initialize DataFabric and load static data.
    
    Should be called ONCE at application startup.
    """
    fabric = get_data_fabric()
    
    # Load static data from CSV
    fabric.load_static_data(csv_path)
    
    # Load group weights
    fabric.load_group_weights()
    
    # 🆕 Load live data from Redis (fallback if Hammer feed hasn't started yet)
    try:
        fabric.load_live_from_redis()
    except Exception as e:
        logger.warning(f"Failed to load live data from Redis at startup: {e}")
    
    logger.info("🏗️ DataFabric fully initialized")
    return fabric

