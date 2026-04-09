"""
Daily Fills Store
-----------------
Manages the recording and retrieval of daily filled orders.
This explicitly follows the user requirement to persist fills to:
`data/logs/orders/ib{account}filledorders{YYMMDD}.csv`

And allows querying these fills to reconstruct "Intraday Strategy Breakdown" (LT vs MM).

Benchmark Tracking (v2):
- Each fill records the DOS Group Average Daily Change (cents) at fill time
- bench_chg = group average (last - prev_close) across all stocks in the symbol's DOS group
- bench_source = the DOS group key used for the benchmark
- This enables post-trade attribution: was the fill cheap/expensive relative to peers?
"""

import os
import csv
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from app.core.logger import logger

class DailyFillsStore:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DailyFillsStore, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.log_dir = r"data/logs/daily_fills"
        os.makedirs(self.log_dir, exist_ok=True)
        self.lock = threading.Lock()
        
    def _get_filename(self, account_type: str) -> str:
        """
        Generate filename: ib{account}filledorders{YYMMDD}.csv
        Example: ibibkr_gunfilledorders260114.csv (per user example format)
        User said: ibpedfilledorders140126.csv
        So format is: ib{ped/gun}filledorders{YYMMDD}.csv
        """
        # User defined format: 
        # - ibpedfilledordersYYMMDD.csv
        # - ibgunfilledordersYYMMDD.csv
        # - hamfilledordersYYMMDD.csv
        
        date_str = datetime.now().strftime("%y%m%d")
        acc_lower = account_type.lower()
        
        if "hammer" in acc_lower:
            return f"hamfilledorders{date_str}.csv"
        elif "ped" in acc_lower:
            return f"ibpedfilledorders{date_str}.csv"
        elif "gun" in acc_lower:
            return f"ibgunfilledorders{date_str}.csv"
        else:
             # Fallback
             return f"unknown_filledorders{date_str}.csv"
        
    def _fetch_bid_ask_at_fill(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Fetch current bid/ask from market data at fill time.
        Returns (bid, ask) or (None, None) if unavailable.
        
        Resolution layers (in priority order):
        1. In-memory market data getter (fastest)
        2. In-memory market_data_cache dict (direct access)
        3. Redis market:l1:{symbol} (L1Feed Terminal streaming data)
        4. Redis live:{symbol} hash (legacy)
        5. DataFabric (aggregated data source)
        
        IMPORTANT: Fills from Hammer arrive with Hammer symbol format (e.g. PSA-N)
        but market_data_cache uses display format (e.g. PSA PRN). We try BOTH.
        """
        # Build list of symbol variants to try
        symbols_to_try = [symbol]
        try:
            from app.live.symbol_mapper import SymbolMapper
            display = SymbolMapper.to_display_symbol(symbol)
            if display != symbol:
                symbols_to_try.append(display)
            hammer = SymbolMapper.to_hammer_symbol(symbol)
            if hammer != symbol and hammer not in symbols_to_try:
                symbols_to_try.append(hammer)
        except Exception:
            pass
        
        for sym in symbols_to_try:
            # Layer 1: Thread-safe market data getter
            try:
                from app.api.market_data_routes import get_market_data
                data = get_market_data(sym)
                if data:
                    bid = data.get('bid')
                    ask = data.get('ask')
                    if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0:
                        return float(bid), float(ask)
            except ImportError:
                pass
            except Exception as e:
                logger.debug(f"[FILL_LOG] Could not fetch bid/ask via getter for {sym}: {e}")
            
            # Layer 2: Direct cache access
            try:
                from app.api.market_data_routes import market_data_cache
                if market_data_cache and sym in market_data_cache:
                    cached = market_data_cache[sym]
                    bid = cached.get('bid')
                    ask = cached.get('ask')
                    if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0:
                        return float(bid), float(ask)
            except Exception:
                pass
        
        # Layer 3: Redis market:l1:{symbol} (L1Feed Terminal streaming data — has TTL)
        for sym in symbols_to_try:
            try:
                from app.core.redis_client import get_redis_client
                import json as _json
                redis = get_redis_client()
                if redis:
                    r = redis.sync if hasattr(redis, 'sync') else redis
                    val = r.get(f"market:l1:{sym}")
                    if val:
                        l1_data = _json.loads(val if isinstance(val, str) else val.decode('utf-8'))
                        bid = l1_data.get('bid')
                        ask = l1_data.get('ask')
                        if bid and ask and float(bid) > 0 and float(ask) > 0:
                            return float(bid), float(ask)
            except Exception:
                pass
        
        # Layer 4: Redis live:{symbol} hash (legacy Hammer L1 feed)
        for sym in symbols_to_try:
            try:
                from app.core.redis_client import get_redis_client
                redis = get_redis_client()
                if redis:
                    r = redis.sync if hasattr(redis, 'sync') else redis
                    bid_raw = r.hget(f"live:{sym}", "bid")
                    ask_raw = r.hget(f"live:{sym}", "ask")
                    if bid_raw and ask_raw:
                        bid = float(bid_raw if isinstance(bid_raw, str) else bid_raw.decode('utf-8'))
                        ask = float(ask_raw if isinstance(ask_raw, str) else ask_raw.decode('utf-8'))
                        if bid > 0 and ask > 0:
                            return bid, ask
            except Exception:
                pass
        
        # Layer 5: DataFabric (aggregated source)
        for sym in symbols_to_try:
            try:
                from app.core.data_fabric import get_data_fabric
                fabric = get_data_fabric()
                if fabric:
                    md = fabric.get_market_data(sym)
                    if md:
                        bid = md.get('bid')
                        ask = md.get('ask')
                        if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0:
                            return float(bid), float(ask)
            except Exception:
                pass
        
        # All 5 layers failed — log a warning so we can diagnose
        logger.warning(
            f"[FILL_LOG] ⚠️ Bid/Ask NOT FOUND for {symbol} "
            f"(tried variants: {symbols_to_try}). "
            f"Fill will have Bid=N/A Ask=N/A."
        )
        return None, None

    def log_fill(self, 
                 account_type: str, 
                 symbol: str, 
                 action: str, 
                 qty: float, 
                 price: float, 
                 strategy_tag: str,
                 bench_chg: Optional[float] = None,
                 bench_source: Optional[str] = None,
                 bid: Optional[float] = None,
                 ask: Optional[float] = None,
                 fill_id: Optional[str] = None,
                 bench_price: Optional[float] = None,
                 fill_time: Optional[str] = None):
        """
        Append a fill to the daily CSV with deduplication.
        Args:
            strategy_tag: The orderRef (e.g. "LT_TRIM", "MM_ENGINE", "JFIN")
            bench_chg: DOS Group average daily change in CENTS at fill time
            bench_source: DOS group key used for benchmark
            bid: Bid price at fill time (auto-fetched if None)
            ask: Ask price at fill time (auto-fetched if None)
            fill_id: Optional unique fill ID for deduplication
            bench_price: DOS Group average PRICE at fill time (auto-fetched if None)
            fill_time: Actual fill timestamp from broker (ISO 8601 or HH:MM:SS).
                        If None, uses current time (datetime.now()).
        """
        # === Deduplication: check if this exact fill already exists ===
        dedup_key = f"{symbol}|{action}|{qty}|{price}|{fill_id or ''}"
        
        if not hasattr(self, '_existing_keys'):
            self._existing_keys = {}  # account -> set of keys
        
        filename = self._get_filename(account_type)
        filepath = os.path.join(self.log_dir, filename)
        
        # Load existing keys from CSV on first call for this account
        if account_type not in self._existing_keys:
            self._existing_keys[account_type] = set()
            if os.path.isfile(filepath):
                try:
                    with open(filepath, 'r') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            k = f"{row.get('Symbol','')}|{row.get('Action','')}|{row.get('Quantity','')}|{row.get('Price','')}|{row.get('FillID','')}"
                            self._existing_keys[account_type].add(k)
                except Exception:
                    pass
        
        if dedup_key in self._existing_keys[account_type]:
            return  # Already logged, skip
        
        self._existing_keys[account_type].add(dedup_key)
        
        # Auto-fetch benchmark if not provided
        if bench_chg is None:
            bench_chg, bench_source = self._fetch_benchmark_for_symbol(symbol)
        
        # Resolve fill time FIRST (needed for historical PFF lookup)
        resolved_time = self._resolve_fill_time(fill_time)
        
        # Auto-fetch PFF benchmark price at fill time (if not provided)
        # PFF ETF is our universal benchmark — simpler & more reliable than group avg
        if bench_price is None:
            bench_price = self._fetch_pff_price(fill_time=resolved_time)
        
        # Auto-fetch bid/ask if not provided
        if bid is None or ask is None:
            fetched_bid, fetched_ask = self._fetch_bid_ask_at_fill(symbol)
            if bid is None:
                bid = fetched_bid
            if ask is None:
                ask = fetched_ask
        
        # Calculate spread and fill quality
        spread = round(ask - bid, 4) if (bid is not None and ask is not None and ask > 0 and bid > 0) else None
        
        row = {
            "Time": resolved_time,
            "Symbol": symbol,
            "Action": action,
            "Quantity": qty,
            "Price": price,
            "Bid": round(bid, 2) if bid is not None else "",
            "Ask": round(ask, 2) if ask is not None else "",
            "Spread": round(spread, 2) if spread is not None else "",
            "Strategy": strategy_tag,
            "Source": "AUTO",
            "Bench_Chg": round(bench_chg, 2) if bench_chg is not None else "",
            "Bench_Price": round(bench_price, 2) if bench_price is not None else "",
            "Bench_Source": bench_source or "",
            "FillID": fill_id or "",
        }
        
        fieldnames = ["Time", "Symbol", "Action", "Quantity", "Price", "Bid", "Ask", "Spread", "Strategy", "Source", "Bench_Chg", "Bench_Price", "Bench_Source", "FillID"]
        
        with self.lock:
            file_exists = os.path.isfile(filepath)
            try:
                with open(filepath, 'a', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                    if not file_exists:
                        writer.writeheader()
                    writer.writerow(row)
                bench_str = f", bench={bench_chg:+.2f}\u00a2 [{bench_source}]" if bench_chg is not None else ""
                bp_str = f", PFF=${bench_price:.2f}" if bench_price is not None else " [!NO_PFF]"
                ba_str = f", bid={bid:.2f} ask={ask:.2f}" if (bid and ask) else " [!NO_BID_ASK]"
                # Enhanced fill log with FBtot/SFStot/GORT
                try:
                    from app.core.order_context_logger import format_fill_log, get_order_context
                    _fctx = get_order_context(symbol, fill_time=fill_time)
                    logger.info(format_fill_log(
                        symbol=symbol, action=action, qty=qty, price=price,
                        tag=strategy_tag, bid=bid, ask=ask,
                        pff_price=bench_price, bench_source=bench_source,
                        ctx=_fctx, fill_time=fill_time
                    ))
                except Exception:
                    logger.info(f"[FILL_LOG] Logged fill to {filename}: {symbol} {action} {qty} @ {price} ({strategy_tag}){ba_str}{bench_str}{bp_str}")
            except Exception as e:
                logger.error(f"[FILL_LOG] Failed to log fill: {e}")
        
        # === QeBench Position Tracking (auto-sync) ===
        self._update_qebench(account_type, symbol, action, qty, price)
    
    def _resolve_fill_time(self, fill_time: Optional[str]) -> str:
        """
        Parse broker fill timestamp into HH:MM:SS format.
        
        Handles multiple formats from brokers:
        - Hammer Pro: "2020-09-17T14:39:19.000" (ISO 8601)
        - IBKR:       "20200917 14:39:19" or "14:39:19"
        - Already HH:MM:SS
        - None → datetime.now()
        
        Returns:
            Time string in HH:MM:SS format
        """
        if not fill_time or not str(fill_time).strip():
            return datetime.now().strftime("%H:%M:%S")
        
        ft = str(fill_time).strip()
        
        # Already HH:MM:SS
        if len(ft) == 8 and ft[2] == ':' and ft[5] == ':':
            return ft
        
        # ISO 8601: "2020-09-17T14:39:19.000" or "2020-09-17T14:39:19"
        if 'T' in ft:
            try:
                time_part = ft.split('T')[1]
                # Remove milliseconds and timezone
                time_part = time_part.split('.')[0].split('Z')[0].split('+')[0].split('-')[0]
                parts = time_part.split(':')
                if len(parts) >= 3:
                    return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
                elif len(parts) == 2:
                    return f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
            except Exception:
                pass
        
        # IBKR format: "20200917 14:39:19"
        if ' ' in ft and len(ft) > 10:
            try:
                time_part = ft.split(' ')[-1]
                parts = time_part.split(':')
                if len(parts) >= 3:
                    return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
            except Exception:
                pass
        
        # HH:MM only
        if len(ft) == 5 and ft[2] == ':':
            return f"{ft}:00"
        
        # Fallback to now
        return datetime.now().strftime("%H:%M:%S")
    
    def _fetch_pff_price(self, fill_time: Optional[str] = None) -> Optional[float]:
        """
        Fetch PFF ETF price — at fill time or current.
        
        PFF is our universal execution benchmark:
        "When I bought MS-A at $20.50, PFF was at $31.40"
        
        For LIVE fills (fill_time is None or very recent):
            Uses etf_market_data cache → market_data_cache → Redis
        
        For BACKFILL fills (fill_time is hours ago):
            Uses Hammer Pro getTicks to fetch PFF's recent trade ticks,
            then finds the tick closest to fill_time.
        
        Args:
            fill_time: HH:MM:SS string of when the fill occurred.
                       None means "right now" (live fill).
        
        Returns:
            PFF price (float) or None
        """
        PFF = "PFF"
        
        # Determine if we need historical lookup
        need_historical = False
        if fill_time and fill_time.strip():
            try:
                now = datetime.now()
                parts = fill_time.strip().split(":")
                fill_hour, fill_min = int(parts[0]), int(parts[1])
                fill_sec = int(parts[2]) if len(parts) > 2 else 0
                diff_secs = abs(
                    (now.hour * 3600 + now.minute * 60 + now.second) -
                    (fill_hour * 3600 + fill_min * 60 + fill_sec)
                )
                # If fill was more than 2 minutes ago, use historical lookup
                need_historical = diff_secs > 120
            except Exception:
                pass
        
        # ─── HISTORICAL: Use Hammer getTicks ───
        if need_historical and fill_time:
            historical_price = self._fetch_pff_price_at_time(fill_time)
            if historical_price:
                return historical_price
            # Fall through to live price as fallback
        
        # ─── LIVE: Use in-memory caches ───
        
        # LAYER 1: ETF market data cache (primary — Hammer L1 feed writes here)
        try:
            from app.api.market_data_routes import get_etf_market_data
            etf_data = get_etf_market_data()
            if etf_data and PFF in etf_data:
                pff = etf_data[PFF]
                last = pff.get('last') or pff.get('price')
                if last and float(last) > 0:
                    return round(float(last), 2)
        except Exception:
            pass
        
        # LAYER 2: General market data cache
        try:
            from app.api.market_data_routes import get_market_data
            pff_data = get_market_data(PFF)
            if pff_data:
                last = pff_data.get('last') or pff_data.get('price')
                if last and float(last) > 0:
                    return round(float(last), 2)
        except Exception:
            pass
        
        # LAYER 3: Redis (written by Hammer feed)
        try:
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if redis and getattr(redis, 'sync', None):
                val = redis.sync.hget(f"live:{PFF}", "last")
                if val:
                    price = float(val if isinstance(val, str) else val.decode('utf-8'))
                    if price > 0:
                        return round(price, 2)
        except Exception:
            pass
        
        return None
    
    def _fetch_pff_price_at_time(self, fill_time_str: str) -> Optional[float]:
        """
        Fetch PFF price at a specific historical time using Hammer Pro getTicks.
        
        Uses a 5-minute bucket cache:
        - Fill at 10:32 → bucket "10:30", Fill at 10:37 → bucket "10:35"
        - All fills in same 5-min bucket share the same PFF price
        - getTicks is called only ONCE per backfill session (results cached)
        
        Args:
            fill_time_str: "HH:MM:SS" of when the fill occurred
            
        Returns:
            PFF price at that time, or None
        """
        # ── 5-minute bucket key ──
        try:
            parts = fill_time_str.strip().split(":")
            hour, minute = int(parts[0]), int(parts[1])
            bucket_min = (minute // 5) * 5  # Round down to 5-min boundary
            bucket_key = f"{hour:02d}:{bucket_min:02d}"
        except Exception:
            return None
        
        # Check bucket cache first
        if not hasattr(self, '_pff_bucket_cache'):
            self._pff_bucket_cache: Dict[str, float] = {}
        
        if bucket_key in self._pff_bucket_cache:
            return self._pff_bucket_cache[bucket_key]
        
        # ── Build tick lookup table (once) ──
        if not hasattr(self, '_pff_tick_table') or not self._pff_tick_table:
            self._pff_tick_table = self._build_pff_tick_table()
        
        if not self._pff_tick_table:
            return None
        
        # Parse target time to seconds
        target_secs = hour * 3600 + bucket_min * 60 + 150  # Middle of 5-min bucket
        
        # Find tick closest to target
        best_tick = None
        best_diff = float('inf')
        
        for tick_secs, tick_price in self._pff_tick_table:
            diff = abs(tick_secs - target_secs)
            if diff < best_diff:
                best_diff = diff
                best_tick = tick_price
        
        if best_tick:
            price = round(float(best_tick), 2)
            self._pff_bucket_cache[bucket_key] = price
            logger.info(f"[PFF_HIST] PFF @ {bucket_key} ≈ ${price:.2f} (closest tick {best_diff:.0f}s away)")
            return price
        
        return None
    
    def _build_pff_tick_table(self) -> list:
        """
        Fetch PFF trade ticks from Hammer and build a (seconds, price) lookup table.
        Called ONCE per backfill session — results cached in self._pff_tick_table.
        
        Returns:
            List of (seconds_since_midnight, price) tuples, sorted by time
        """
        try:
            from app.live.hammer_client import get_hammer_client
            client = get_hammer_client()
            if not client or not client.is_connected():
                logger.debug("[PFF_HIST] Hammer client not connected, can't fetch historical PFF")
                return []
            
            # Fetch last 200 trade ticks for PFF (covers ~2-3 hours for liquid ETF)
            result = client.get_ticks("PFF", lastFew=200, tradesOnly=True, regHoursOnly=True, timeout=8.0)
            if not result or 'data' not in result:
                logger.debug("[PFF_HIST] getTicks returned no data for PFF")
                return []
            
            ticks = result['data']
            if not ticks:
                return []
            
            # Build (seconds, price) tuples
            table = []
            for tick in ticks:
                tick_time = tick.get('Time') or tick.get('time') or tick.get('DT') or ''
                tick_price = tick.get('Price') or tick.get('price') or tick.get('Last') or tick.get('last')
                
                if not tick_price or not tick_time:
                    continue
                
                tick_secs = self._timestamp_to_seconds(tick_time)
                if tick_secs is not None:
                    table.append((tick_secs, float(tick_price)))
            
            table.sort(key=lambda x: x[0])
            logger.info(f"[PFF_HIST] Built PFF tick table: {len(table)} ticks covering "
                       f"{self._secs_to_time(table[0][0])} → {self._secs_to_time(table[-1][0])}" if table else "")
            return table
            
        except Exception as e:
            logger.debug(f"[PFF_HIST] Error building PFF tick table: {e}")
            return []
    
    def _secs_to_time(self, secs: float) -> str:
        """Convert seconds since midnight to HH:MM."""
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        return f"{h:02d}:{m:02d}"
    
    def _timestamp_to_seconds(self, ts: str) -> Optional[float]:
        """Convert various timestamp formats to seconds since midnight."""
        if not ts:
            return None
        try:
            ts = str(ts).strip()
            # ISO 8601: "2026-03-01T13:22:15.000"
            if 'T' in ts:
                time_part = ts.split('T')[1].split('.')[0].split('Z')[0].split('+')[0]
                parts = time_part.split(':')
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + (int(parts[2]) if len(parts) > 2 else 0)
            # HH:MM:SS
            if ':' in ts:
                parts = ts.split(':')
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + (int(parts[2]) if len(parts) > 2 else 0)
        except Exception:
            pass
        return None
    
    def _fetch_benchmark_for_symbol(self, symbol: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Fetch DOS group benchmark (average daily change in cents) for a symbol at fill time.
        
        Returns:
            (bench_chg_cents, bench_source_group_key)
        """
        try:
            from app.core.data_fabric import get_data_fabric
            fabric = get_data_fabric()
            if not fabric:
                return None, None
            
            # Get derived scores which contain bench_chg from the last score calculation
            derived = fabric.get_derived(symbol)
            if derived:
                bench_chg = derived.get('bench_chg') or derived.get('benchmark_chg')
                bench_source = derived.get('bench_source')
                if bench_chg is not None:
                    return float(bench_chg), bench_source
            
            return None, None
        except Exception as e:
            logger.debug(f"[FILL_LOG] Could not fetch benchmark for {symbol}: {e}")
            return None, None
    
    @staticmethod
    def _map_account_to_qebench(account_type: str) -> str:
        """
        Map account_type strings to QeBench account keys.
        Ensures 3 separate CSV sets: hampro, ibped, ibgun.
        """
        acc = account_type.upper()
        if "HAMMER" in acc or "HAMPRO" in acc:
            return "HAMMER_PRO"
        elif "GUN" in acc:
            return "IBKR_GUN"
        elif "PED" in acc:
            return "IBKR_PED"
        else:
            return "IBKR_PED"  # safe default
    
    def _update_qebench(self, account_type: str, symbol: str, action: str, qty: float, price: float):
        """
        Auto-update QeBench position-level tracking when a fill is logged.
        
        v3 — PFF BENCHMARK + TIME TRACKING:
        1. PFF ETF price at fill → market-relative performance
        2. Time@Fill → weighted average fill age in days (how "old" is the position?)
        
        Each account has its own QeBench files:
        - hamproqebench.csv + hamproqebench_fills.csv
        - ibpedqebench.csv + ibpedqebench_fills.csv
        - ibgunqebench.csv + ibgunqebench_fills.csv
        """
        try:
            from app.qebench import get_qebench_csv
            
            qb_account = self._map_account_to_qebench(account_type)
            csv_mgr = get_qebench_csv(account=qb_account)
            
            # ── BENCHMARK: PFF ETF price ──
            pff_price = self._fetch_pff_price() or 0.0
            
            # ── TIME: Days since this fill (0 = today) ──
            fill_days_ago = 0.0  # New fill = 0 days ago
            
            # Get existing position (if any)
            existing = csv_mgr.get_position(symbol)
            
            is_buy = action.upper() == "BUY"
            fill_qty = abs(qty)
            
            if existing:
                old_qty = existing['total_qty']
                old_avg_cost = existing['weighted_avg_cost']
                old_pff_fill = existing.get('weighted_pff_fill', 0.0)
                old_time_fill = existing.get('weighted_time_fill', 0.0)
                
                if is_buy and old_qty >= 0:
                    # Adding to long: weighted average update
                    new_qty = old_qty + fill_qty
                    if new_qty > 0:
                        new_avg_cost = (old_qty * old_avg_cost + fill_qty * price) / new_qty
                        new_pff_fill = (old_qty * old_pff_fill + fill_qty * pff_price) / new_qty
                        # Time: old fills aged by 0 days more (we recalc on read), new fill is 0 days
                        new_time_fill = (old_qty * old_time_fill + fill_qty * fill_days_ago) / new_qty
                    else:
                        new_avg_cost = price
                        new_pff_fill = pff_price
                        new_time_fill = fill_days_ago
                elif not is_buy and old_qty <= 0:
                    # Adding to short: weighted average update
                    new_qty = old_qty - fill_qty
                    abs_old = abs(old_qty)
                    abs_new = abs(new_qty)
                    if abs_new > 0:
                        new_avg_cost = (abs_old * old_avg_cost + fill_qty * price) / abs_new
                        new_pff_fill = (abs_old * old_pff_fill + fill_qty * pff_price) / abs_new
                        new_time_fill = (abs_old * old_time_fill + fill_qty * fill_days_ago) / abs_new
                    else:
                        new_avg_cost = price
                        new_pff_fill = pff_price
                        new_time_fill = fill_days_ago
                else:
                    # Reducing position: keep existing weighted averages
                    if is_buy:
                        new_qty = old_qty + fill_qty  # covering short
                    else:
                        new_qty = old_qty - fill_qty  # trimming long
                    new_avg_cost = old_avg_cost
                    new_pff_fill = old_pff_fill
                    new_time_fill = old_time_fill
                
                csv_mgr.update_position(
                    symbol=symbol,
                    total_qty=new_qty,
                    weighted_avg_cost=round(new_avg_cost, 4),
                    weighted_pff_fill=round(new_pff_fill, 4),
                    weighted_time_fill=round(new_time_fill, 2),
                )
            else:
                # New position
                signed_qty = fill_qty if is_buy else -fill_qty
                csv_mgr.update_position(
                    symbol=symbol,
                    total_qty=signed_qty,
                    weighted_avg_cost=round(price, 4),
                    weighted_pff_fill=round(pff_price, 4),
                    weighted_time_fill=round(fill_days_ago, 2),
                )
            
            # Record fill in QeBench fills CSV
            csv_mgr.add_fill(
                symbol=symbol,
                qty=fill_qty,
                fill_price=price,
                pff_price=pff_price,
                source="AUTO"
            )
            
            logger.info(
                f"[QeBench] {qb_account}: {symbol} {action} {qty}@{price:.2f} "
                f"pff@{pff_price:.2f}"
            )
            
        except Exception as e:
            logger.error(f"[QeBench] Auto-update failed for {symbol}: {e}")

    def get_all_fills(self, account_type: str) -> List[Dict]:
        """
        Get all fills for today as a list of dicts (UI-compatible format).
        Used as fallback when IBKR API is unavailable.
        
        Returns:
            List of fill dicts with: order_id, symbol, action, qty, price, status, timestamp, tag
        """
        filename = self._get_filename(account_type)
        filepath = os.path.join(self.log_dir, filename)
        
        fills = []
        if not os.path.exists(filepath):
            return fills
        
        try:
            with open(filepath, 'r') as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader):
                    time_str = row.get("Time", "")
                    # Convert HH:MM:SS to timestamp
                    ts = 0
                    try:
                        today = datetime.now().strftime("%Y-%m-%d")
                        dt = datetime.strptime(f"{today} {time_str}", "%Y-%m-%d %H:%M:%S")
                        ts = dt.timestamp()
                    except Exception:
                        ts = 0
                    
                    # Parse bench_chg (may be empty string in old CSVs)
                    bench_chg_raw = row.get("Bench_Chg", "")
                    bench_chg = None
                    try:
                        if bench_chg_raw and bench_chg_raw.strip():
                            bench_chg = float(bench_chg_raw)
                    except (ValueError, TypeError):
                        bench_chg = None
                    
                    # Parse bid/ask (may be empty in old CSVs without these columns)
                    bid_raw = row.get("Bid", "")
                    ask_raw = row.get("Ask", "")
                    spread_raw = row.get("Spread", "")
                    bid_val = None
                    ask_val = None
                    spread_val = None
                    try:
                        if bid_raw and str(bid_raw).strip():
                            bid_val = float(bid_raw)
                    except (ValueError, TypeError):
                        pass
                    try:
                        if ask_raw and str(ask_raw).strip():
                            ask_val = float(ask_raw)
                    except (ValueError, TypeError):
                        pass
                    try:
                        if spread_raw and str(spread_raw).strip():
                            spread_val = float(spread_raw)
                    except (ValueError, TypeError):
                        pass
                    
                    # Parse bench_price
                    bench_price_raw = row.get("Bench_Price", "")
                    bench_price_val = None
                    try:
                        if bench_price_raw and str(bench_price_raw).strip():
                            bench_price_val = float(bench_price_raw)
                    except (ValueError, TypeError):
                        pass
                    
                    fills.append({
                        "order_id": f"csv_fill_{idx}",
                        "symbol": row.get("Symbol", ""),
                        "action": row.get("Action", ""),
                        "qty": float(row.get("Quantity", 0)),
                        "filled_qty": float(row.get("Quantity", 0)),
                        "remaining_qty": 0,
                        "price": float(row.get("Price", 0)),
                        "bid": bid_val,
                        "ask": ask_val,
                        "spread": spread_val,
                        "status": "Filled",
                        "source": row.get("Source", "CSV_FALLBACK"),
                        "tag": row.get("Strategy", ""),
                        "timestamp": ts,
                        "time": time_str,
                        "bench_chg": bench_chg,
                        "bench_price": bench_price_val,
                        "bench_source": row.get("Bench_Source", ""),
                    })
            
            # Sort by timestamp descending (newest first)
            fills.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return fills
            
        except Exception as e:
            logger.error(f"[FILL_LOG] Failed to read all fills: {e}")
            return []

    def get_intraday_breakdown(self, account_type: str, symbol: str) -> Dict[str, float]:
        """
        Read today's CSV and aggregate Net Quantity per Strategy Tag for a specific symbol.
        Returns:
            Dict: {'LT': 100.0, 'MM': 50.0} (Aggregated by inferred bucket)
        """
        filename = self._get_filename(account_type)
        filepath = os.path.join(self.log_dir, filename)
        
        breakdown = defaultdict(float)
        
        if not os.path.exists(filepath):
            return dict(breakdown)
            
        try:
            with open(filepath, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Symbol") == symbol:
                        qty = float(row.get("Quantity", 0))
                        action = row.get("Action", "").upper()
                        strategy = row.get("Strategy", "UNKNOWN").upper()
                        
                        # Sign correction (Sell is negative impact on holdings)
                        signed_qty = qty if action == "BUY" else -qty
                        
                        # Map specific strategies to buckets (LT/MM)
                        # "JFIN", "LT_TRIM", "REDUCEMORE" -> LT
                        # "GREATEST_MM", "SIDEHIT", "MM_ENGINE" -> MM
                        bucket = "LT" # Default fallback as per user request
                        
                        if any(x in strategy for x in ["MM", "SIDEHIT"]):
                            bucket = "MM"
                        elif any(x in strategy for x in ["LT", "JFIN", "REDUCEMORE", "KARBOTU"]):
                            bucket = "LT"
                        
                        breakdown[bucket] += signed_qty
                        
            return dict(breakdown)
            
        except Exception as e:
            logger.error(f"[FILL_LOG] Failed to read breakdown: {e}")
            return {}

    def get_fills_for_symbol(self, symbol: str) -> List[Dict]:
        """
        Get all today's fills for a specific symbol across all accounts.
        Used by tag inference to determine what book (LT/MM) was used most recently.
        
        Returns:
            List of fill dicts with: symbol, action, tag, time
        """
        fills = []
        for account_type in ["HAMMER_PRO", "IBKR_PED"]:
            try:
                filename = self._get_filename(account_type)
                filepath = os.path.join(self.log_dir, filename)
                if not os.path.exists(filepath):
                    continue
                with open(filepath, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get("Symbol") == symbol:
                            fills.append({
                                "symbol": symbol,
                                "action": row.get("Action", ""),
                                "tag": row.get("Strategy", ""),
                                "time": row.get("Time", ""),
                                "qty": float(row.get("Quantity", 0)),
                                "price": float(row.get("Price", 0)),
                            })
            except Exception:
                continue
        return fills

_daily_fills_store = None
def get_daily_fills_store():
    global _daily_fills_store
    if _daily_fills_store is None:
        _daily_fills_store = DailyFillsStore()
    return _daily_fills_store
