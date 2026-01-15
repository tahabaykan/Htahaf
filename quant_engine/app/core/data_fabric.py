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
            Path(r"C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janalldata.csv"),
            Path(r"C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janall\janalldata.csv"),
            Path(os.getcwd()) / 'janalldata.csv',
            Path(os.getcwd()) / 'janall' / 'janalldata.csv',
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
        Get live market data for symbol (from RAM).
        
        Args:
            symbol: PREF_IBKR symbol
            
        Returns:
            Live data dict or None
        """
        return self._live_data.get(symbol)
    
    def get_live_symbols_count(self) -> int:
        """Get count of symbols with live data"""
        return len(self._live_data)

    def get_all_live_symbols(self) -> List[str]:
        """Get all symbols with live data"""
        return list(self._live_data.keys())
    
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
                    Path(r"C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\groupweights.csv"),
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
                logger.info(
                    f"🔑 [FAST_SNAPSHOT_DEBUG] {symbol}: "
                    f"static_exists={bool(static)} | "
                    f"live_exists={bool(live)} | "
                    f"derived_exists={bool(derived)} | "
                    f"live.bid={live.get('bid')} | "
                    f"live.ask={live.get('ask')} | "
                    f"live.last={live.get('last')} | "
                    f"live_keys={list(live.keys()) if live else []}"
                )
            
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
    
    logger.info("🏗️ DataFabric fully initialized")
    return fabric

