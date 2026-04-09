"""
Truth Shift Engine

Analyzes directional flow of truth ticks for each symbol and group.
Produces TSS (Truth Shift Score) and RTS (Relative Truth Shift) metrics
across multiple time windows.

TSS Formula (Displacement-Weighted):
    weight = size × |price_change|
    UP_IMPACT  = Σ weight for ticks where price went UP
    DOWN_IMPACT = Σ weight for ticks where price went DOWN
    TSS = (UP_IMPACT - DOWN_IMPACT) / (UP_IMPACT + DOWN_IMPACT) × 100
    
    Range: -100 (all displacement-volume printing down)
       to  +100 (all displacement-volume printing up)
    
    Why displacement-weighted?
    A 100-lot tick moving $0.25 counts 25x more than a 100-lot tick
    moving $0.01. Real price migration matters more than micro-noise.

Time Windows:
    TSS_5M:    Last 5 minutes   — instant momentum
    TSS_15M:   Last 15 minutes  — short-term trend
    TSS_30M:   Last 30 minutes  — medium-term trend
    TSS_1H:    Last 1 hour      — hourly bias
    TSS_TODAY:  Since market open — daily direction

Group Analysis:
    GROUP_TSS = volume-weighted average of member symbol TSS scores
    RTS (Relative Truth Shift) = symbol_TSS - group_TSS

Redis Keys:
    ts:shift:{symbol}   — per-symbol TSS across all windows
    ts:group:{group_key} — per-group TSS with ranked symbols
"""

import json
import time
import asyncio
import threading
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

from loguru import logger


# ═══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

# Time windows in seconds
WINDOWS = {
    'TSS_5M':    5 * 60,
    'TSS_15M':  15 * 60,
    'TSS_30M':  30 * 60,
    'TSS_1H':   60 * 60,
    'TSS_TODAY': 0,  # Special: from market open
}

# Compute interval (seconds)
COMPUTE_INTERVAL = 60

# Redis TTL for shift data (4 hours — intraday only)
SHIFT_TTL = 4 * 3600

# Minimum ticks needed for a valid score
MIN_TICKS_FOR_SCORE = 3

# Market open time (EST) — 9:30 AM
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 30


class TruthShiftEngine:
    """
    Computes directional truth tick flow scores (TSS) per symbol and group.
    
    Data source: tt:ticks:{symbol} in Redis (written by TruthTicksEngine).
    No new data collection needed — pure analysis layer.
    """
    
    def __init__(self):
        self._redis = None
        self._running = False
        self._task = None
        self._group_map: Dict[str, str] = {}    # symbol → group_key
        self._group_members: Dict[str, List[str]] = {}  # group_key → [symbols]
        self._last_compute_ts = 0
        self._cached_results: Dict[str, Dict] = {}  # symbol → TSS data
        self._cached_groups: Dict[str, Dict] = {}    # group → TSS data
        logger.info("[TruthShift] Engine initialized")
    
    # ═══════════════════════════════════════════════════════════════════
    # LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════
    
    async def start(self):
        """Start periodic computation loop."""
        if self._running:
            logger.warning("[TruthShift] Already running")
            return
        
        self._running = True
        self._load_group_mappings()
        self._task = asyncio.create_task(self._compute_loop(), name="truth_shift_loop")
        logger.info("[TruthShift] Started — computing every {COMPUTE_INTERVAL}s")
    
    async def stop(self):
        """Stop computation loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("[TruthShift] Stopped")
    
    # ═══════════════════════════════════════════════════════════════════
    # REDIS
    # ═══════════════════════════════════════════════════════════════════
    
    def _get_redis(self):
        """Get sync Redis client."""
        if self._redis is None:
            try:
                from app.core.redis_client import get_redis_client
                client = get_redis_client()
                self._redis = getattr(client, 'sync', client)
            except Exception as e:
                logger.warning(f"[TruthShift] Redis init error: {e}")
        return self._redis
    
    # ═══════════════════════════════════════════════════════════════════
    # GROUP MAPPINGS
    # ═══════════════════════════════════════════════════════════════════
    
    # Groups that should be split by CGRUP
    KUPONLU_GROUPS = {'heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta'}
    
    def _load_group_mappings(self):
        """
        Load symbol → group mappings from grouping.py's CSV files.
        
        For kuponlu groups (heldkuponlu, heldkuponlukreciliz, heldkuponlukreorta),
        splits into CGRUP sub-groups: e.g. 'heldkuponlu::c450', 'heldkuponlu::c500'
        so that symbols within c450 compare against their c450 peers only.
        
        Symbols also keep a '_primary_group' entry for the original full group.
        """
        try:
            from app.market_data.grouping import _load_group_files
            
            group_symbols = _load_group_files()
            
            self._group_map = {}        # symbol → effective group (may include ::cgrup)
            self._primary_group = {}    # symbol → original group (without ::cgrup)
            self._group_members = defaultdict(list)
            
            # Load CGRUP from static store first, then fallback to CSV
            cgrup_map = {}  # symbol → cgrup
            try:
                from app.market_data.static_data_store import get_static_store
                static_store = get_static_store()
                if static_store and static_store.is_loaded():
                    for sym, data in static_store.data.items():
                        cgrup = data.get('CGRUP')
                        if cgrup:
                            cgrup_str = str(cgrup).strip().lower()
                            if cgrup_str and cgrup_str not in ('n/a', 'nan', ''):
                                cgrup_map[sym] = cgrup_str
                    logger.debug(f"[TruthShift] Loaded {len(cgrup_map)} CGRUP mappings from static store")
            except Exception as e:
                logger.debug(f"[TruthShift] Could not load CGRUP from static store: {e}")
            
            # Fallback: read CGRUP from janall CSV files directly
            if not cgrup_map:
                try:
                    import os
                    import pandas as pd
                    KUPONLU_FILES = {
                        'heldkuponlu': 'ssfinekheldkuponlu.csv',
                        'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
                        'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
                    }
                    janall_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                              '..', '..', '..', '..', 'janall')
                    # Try common janall locations
                    for try_dir in [janall_dir, r'C:\StockTracker\janall']:
                        if not os.path.isdir(try_dir):
                            continue
                        for grp_name, fname in KUPONLU_FILES.items():
                            fpath = os.path.join(try_dir, fname)
                            if not os.path.exists(fpath):
                                continue
                            df = pd.read_csv(fpath)
                            sym_col = 'PREF IBKR' if 'PREF IBKR' in df.columns else 'PREF_IBKR'
                            if 'CGRUP' in df.columns and sym_col in df.columns:
                                for _, row in df.iterrows():
                                    sym = str(row[sym_col]).strip()
                                    cg = str(row.get('CGRUP', '')).strip().lower()
                                    if cg and cg not in ('nan', 'n/a', ''):
                                        cgrup_map[sym] = cg
                        if cgrup_map:
                            break
                    if cgrup_map:
                        logger.info(f"[TruthShift] Loaded {len(cgrup_map)} CGRUP mappings from janall CSVs")
                except Exception as e:
                    logger.debug(f"[TruthShift] Could not load CGRUP from CSVs: {e}")
            
            for group_name, symbols in group_symbols.items():
                for sym in symbols:
                    self._primary_group[sym] = group_name
                    
                    # For kuponlu groups, split by CGRUP
                    if group_name in self.KUPONLU_GROUPS and sym in cgrup_map:
                        effective_group = f"{group_name}::{cgrup_map[sym]}"
                    else:
                        effective_group = group_name
                    
                    self._group_map[sym] = effective_group
                    self._group_members[effective_group].append(sym)
            
            logger.info(
                f"[TruthShift] Loaded {len(self._group_map)} symbols across "
                f"{len(self._group_members)} groups (incl. CGRUP sub-groups)"
            )
        except Exception as e:
            logger.warning(f"[TruthShift] Group mapping load error: {e}")
    
    # ═══════════════════════════════════════════════════════════════════
    # CORE: TSS COMPUTATION
    # ═══════════════════════════════════════════════════════════════════
    
    def compute_symbol_tss(self, symbol: str, ticks: List[Dict]) -> Dict[str, Any]:
        """
        Compute TSS for a single symbol across all time windows.
        
        Args:
            symbol: Stock symbol
            ticks: List of truth ticks (chronological), each with {price, size, ts}
            
        Returns:
            Dict with TSS data per window
        """
        now = time.time()
        market_open_ts = self._get_market_open_ts(now)
        
        result = {
            'symbol': symbol,
            'group': self._group_map.get(symbol, 'unknown'),
            'updated_at': now,
            'windows': {}
        }
        
        for window_name, window_seconds in WINDOWS.items():
            if window_name == 'TSS_TODAY':
                cutoff = market_open_ts
            else:
                cutoff = now - window_seconds
            
            # Filter ticks within this window
            window_ticks = [t for t in ticks if t.get('ts', 0) >= cutoff]
            
            # Compute TSS for this window
            tss_data = self._compute_tss_for_ticks(window_ticks)
            tss_data['window'] = window_name
            result['windows'][window_name] = tss_data
        
        return result
    
    def _compute_tss_for_ticks(self, ticks: List[Dict]) -> Dict[str, Any]:
        """
        Compute TSS (Truth Shift Score) for a list of ordered ticks.
        
        DISPLACEMENT-WEIGHTED scoring:
            weight = size × |price_change|
            
        This means a 100-lot tick moving $0.25 counts 25x more than
        a 100-lot tick moving $0.01. Real price migration matters more
        than micro-noise.
        
        Also tracks raw (unweighted) volume for reference.
        """
        if len(ticks) < MIN_TICKS_FOR_SCORE:
            return {
                'score': 0,
                'up_impact': 0,
                'down_impact': 0,
                'up_vol': 0,
                'down_vol': 0,
                'flat_vol': 0,
                'tick_count': len(ticks),
                'up_ticks': 0,
                'down_ticks': 0,
                'flat_ticks': 0,
                'price_start': ticks[0]['price'] if ticks else 0,
                'price_end': ticks[-1]['price'] if ticks else 0,
                'price_change_pct': 0,
                'intensity': 0,
                'valid': False
            }
        
        # Displacement-weighted accumulators
        up_impact = 0.0    # Σ (size × |price_change|) for UP moves
        down_impact = 0.0  # Σ (size × |price_change|) for DOWN moves
        
        # Raw volume (unweighted, for reference)
        up_vol = 0
        down_vol = 0
        flat_vol = 0
        up_count = 0
        down_count = 0
        flat_count = 0
        
        for i in range(1, len(ticks)):
            prev_price = ticks[i - 1].get('price', 0)
            curr_price = ticks[i].get('price', 0)
            curr_size = ticks[i].get('size', 0)
            displacement = abs(curr_price - prev_price)
            
            if curr_price > prev_price:
                up_impact += curr_size * displacement
                up_vol += curr_size
                up_count += 1
            elif curr_price < prev_price:
                down_impact += curr_size * displacement
                down_vol += curr_size
                down_count += 1
            else:
                flat_vol += curr_size
                flat_count += 1
        
        # TSS from displacement-weighted impact
        total_impact = up_impact + down_impact
        if total_impact > 0:
            score = round((up_impact - down_impact) / total_impact * 100, 1)
        else:
            score = 0
        
        price_start = ticks[0]['price']
        price_end = ticks[-1]['price']
        price_change_pct = round(
            (price_end - price_start) / price_start * 100, 3
        ) if price_start > 0 else 0
        
        # Time span for intensity calculation
        ts_start = ticks[0].get('ts', 0)
        ts_end = ticks[-1].get('ts', 0)
        span_minutes = max((ts_end - ts_start) / 60, 1)
        intensity = round(len(ticks) / span_minutes, 2)
        
        return {
            'score': score,
            'up_impact': round(up_impact, 2),
            'down_impact': round(down_impact, 2),
            'up_vol': up_vol,
            'down_vol': down_vol,
            'flat_vol': flat_vol,
            'tick_count': len(ticks),
            'up_ticks': up_count,
            'down_ticks': down_count,
            'flat_ticks': flat_count,
            'price_start': round(price_start, 4),
            'price_end': round(price_end, 4),
            'price_change_pct': price_change_pct,
            'intensity': intensity,
            'valid': True
        }
    
    # ═══════════════════════════════════════════════════════════════════
    # GROUP TSS
    # ═══════════════════════════════════════════════════════════════════
    
    def compute_group_tss(
        self,
        group_key: str,
        symbol_results: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """
        Compute group-level TSS (volume-weighted average of member symbols).
        Also computes RTS (Relative Truth Shift) for each member.
        """
        members = self._group_members.get(group_key, [])
        active_members = [s for s in members if s in symbol_results]
        
        if not active_members:
            return {
                'group': group_key,
                'symbol_count': 0,
                'updated_at': time.time(),
                'windows': {},
                'symbols': {}
            }
        
        result = {
            'group': group_key,
            'symbol_count': len(active_members),
            'updated_at': time.time(),
            'windows': {},
            'symbols': {}
        }
        
        for window_name in WINDOWS:
            # Collect all valid scores with their displacement-weighted impact
            scores_vols = []
            for sym in active_members:
                w = symbol_results[sym].get('windows', {}).get(window_name, {})
                if not w.get('valid', False):
                    continue
                # Use displacement-weighted impact for group weighting
                total_impact = w.get('up_impact', 0) + w.get('down_impact', 0)
                if total_impact > 0:
                    scores_vols.append((w['score'], total_impact, sym))
            
            if not scores_vols:
                result['windows'][window_name] = {
                    'score': 0, 'member_count': 0, 'avg_intensity': 0, 'valid': False
                }
                continue
            
            # Volume-weighted average
            total_weight = sum(v for _, v, _ in scores_vols)
            group_score = round(
                sum(s * v for s, v, _ in scores_vols) / total_weight, 1
            ) if total_weight > 0 else 0
            
            # Average intensity
            intensities = []
            for sym in active_members:
                w = symbol_results[sym].get('windows', {}).get(window_name, {})
                if w.get('valid'):
                    intensities.append(w.get('intensity', 0))
            avg_intensity = round(sum(intensities) / len(intensities), 2) if intensities else 0
            
            result['windows'][window_name] = {
                'score': group_score,
                'member_count': len(scores_vols),
                'avg_intensity': avg_intensity,
                'valid': True
            }
            
            # RTS for each symbol in this window
            for sym in active_members:
                if sym not in result['symbols']:
                    result['symbols'][sym] = {}
                
                w = symbol_results[sym].get('windows', {}).get(window_name, {})
                sym_score = w.get('score', 0) if w.get('valid') else None
                rts = round(sym_score - group_score, 1) if sym_score is not None else None
                
                result['symbols'][sym][window_name] = {
                    'tss': sym_score,
                    'rts': rts,
                    'group_tss': group_score
                }
        
        return result
    
    # ═══════════════════════════════════════════════════════════════════
    # FULL COMPUTE (ALL SYMBOLS + ALL GROUPS)
    # ═══════════════════════════════════════════════════════════════════
    
    def compute_all(self) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
        """
        Compute TSS for ALL symbols, then ALL groups.
        Stores results in Redis and in-memory cache.
        
        Returns:
            (symbol_results, group_results)
        """
        redis = self._get_redis()
        if not redis:
            return {}, {}
        
        # ── Step 1: Discover all symbols with truth ticks ──
        all_symbols = self._discover_symbols(redis)
        if not all_symbols:
            logger.debug("[TruthShift] No symbols found in tt:ticks:*")
            return {}, {}
        
        # ── Step 2: Compute TSS per symbol ──
        symbol_results = {}
        for symbol in all_symbols:
            ticks = self._read_ticks(redis, symbol)
            if not ticks:
                continue
            
            result = self.compute_symbol_tss(symbol, ticks)
            symbol_results[symbol] = result
            
            # Write to Redis
            try:
                key = f"ts:shift:{symbol}"
                redis.set(key, json.dumps(result, default=str))
                redis.expire(key, SHIFT_TTL)
            except Exception:
                pass
        
        # ── Step 3: Compute group TSS ──
        group_results = {}
        groups_with_data = set()
        for sym in symbol_results:
            g = self._group_map.get(sym)
            if g:
                groups_with_data.add(g)
        
        for group_key in groups_with_data:
            g_result = self.compute_group_tss(group_key, symbol_results)
            group_results[group_key] = g_result
            
            # Write to Redis
            try:
                key = f"ts:group:{group_key}"
                redis.set(key, json.dumps(g_result, default=str))
                redis.expire(key, SHIFT_TTL)
            except Exception:
                pass
        
        # ── Step 4: Inject RTS into symbol results ──
        for sym, s_result in symbol_results.items():
            group_key = self._group_map.get(sym)
            if group_key and group_key in group_results:
                g_data = group_results[group_key]
                sym_in_group = g_data.get('symbols', {}).get(sym, {})
                s_result['rts'] = {}
                for window_name in WINDOWS:
                    rts_data = sym_in_group.get(window_name, {})
                    s_result['rts'][window_name] = rts_data.get('rts', None)
        
        # Cache
        self._cached_results = symbol_results
        self._cached_groups = group_results
        self._last_compute_ts = time.time()
        
        logger.info(
            f"[TruthShift] Computed: {len(symbol_results)} symbols, "
            f"{len(group_results)} groups"
        )
        
        return symbol_results, group_results
    
    # ═══════════════════════════════════════════════════════════════════
    # DATA READING
    # ═══════════════════════════════════════════════════════════════════
    
    def _discover_symbols(self, redis) -> List[str]:
        """Discover all symbols that have truth tick data in Redis."""
        try:
            keys = redis.keys("tt:ticks:*")
            symbols = []
            for k in keys:
                k_str = k.decode() if isinstance(k, bytes) else k
                sym = k_str.replace("tt:ticks:", "")
                if sym:
                    symbols.append(sym)
            return sorted(symbols)
        except Exception as e:
            logger.warning(f"[TruthShift] Symbol discovery error: {e}")
            return []
    
    def _read_ticks(self, redis, symbol: str) -> List[Dict]:
        """Read truth ticks from Redis for a symbol (chronological order)."""
        try:
            data = redis.get(f"tt:ticks:{symbol}")
            if not data:
                return []
            
            raw = data.decode() if isinstance(data, bytes) else data
            ticks = json.loads(raw)
            
            if not isinstance(ticks, list):
                return []
            
            # Filter valid ticks and ensure chronological order
            valid = []
            now = time.time()
            for t in ticks:
                ts = t.get('ts', 0)
                price = float(t.get('price', 0))
                size = float(t.get('size', 0))
                
                # Skip stale (>24h) or invalid
                if price <= 0 or size <= 0:
                    continue
                if ts > 0 and (now - ts) > 86400:
                    continue
                
                valid.append({
                    'price': price,
                    'size': size,
                    'venue': str(t.get('exch', t.get('venue', ''))),
                    'ts': ts
                })
            
            # Sort by timestamp (chronological)
            valid.sort(key=lambda x: x['ts'])
            return valid
            
        except Exception as e:
            logger.debug(f"[TruthShift] Read ticks error for {symbol}: {e}")
            return []
    
    # ═══════════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════════
    
    def _get_market_open_ts(self, now: float) -> float:
        """Get today's market open timestamp (9:30 AM EST)."""
        try:
            from datetime import timezone
            import pytz
            est = pytz.timezone('US/Eastern')
            now_est = datetime.fromtimestamp(now, tz=est)
            market_open = now_est.replace(
                hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0, microsecond=0
            )
            return market_open.timestamp()
        except Exception:
            # Fallback: approximate (UTC-5)
            from datetime import timezone as tz
            utc_now = datetime.utcfromtimestamp(now)
            est_now = utc_now - timedelta(hours=5)
            market_open = est_now.replace(
                hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN, second=0, microsecond=0
            )
            return market_open.timestamp() + 5 * 3600  # back to UTC
    
    # ═══════════════════════════════════════════════════════════════════
    # COMPUTE LOOP
    # ═══════════════════════════════════════════════════════════════════
    
    async def _compute_loop(self):
        """Periodic computation loop."""
        logger.info("[TruthShift] Compute loop started")
        try:
            while self._running:
                try:
                    # Run compute in executor (Redis calls are sync)
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, self.compute_all)
                except Exception as e:
                    logger.warning(f"[TruthShift] Compute error: {e}")
                
                # Wait for next cycle
                await asyncio.sleep(COMPUTE_INTERVAL)
        except asyncio.CancelledError:
            pass
        logger.info("[TruthShift] Compute loop stopped")
    
    # ═══════════════════════════════════════════════════════════════════
    # PUBLIC API (for routes / dashboard)
    # ═══════════════════════════════════════════════════════════════════
    
    def get_symbol_tss(self, symbol: str) -> Optional[Dict]:
        """Get cached TSS for a symbol."""
        return self._cached_results.get(symbol)
    
    def get_group_tss(self, group_key: str) -> Optional[Dict]:
        """Get cached TSS for a group."""
        return self._cached_groups.get(group_key)
    
    def get_all_symbols_summary(self, window: str = 'TSS_15M') -> List[Dict]:
        """
        Get summary for ALL symbols sorted by TSS score.
        Returns a flat list: [{symbol, group, tss, rts, ticks, intensity}, ...]
        """
        rows = []
        for sym, data in self._cached_results.items():
            w = data.get('windows', {}).get(window, {})
            if not w.get('valid'):
                continue
            
            rts_val = data.get('rts', {}).get(window)
            
            rows.append({
                'symbol': sym,
                'group': data.get('group', 'unknown'),
                'tss': w.get('score', 0),
                'rts': rts_val,
                'up_vol': w.get('up_vol', 0),
                'down_vol': w.get('down_vol', 0),
                'ticks': w.get('tick_count', 0),
                'up_ticks': w.get('up_ticks', 0),
                'down_ticks': w.get('down_ticks', 0),
                'price_start': w.get('price_start', 0),
                'price_end': w.get('price_end', 0),
                'price_change_pct': w.get('price_change_pct', 0),
                'intensity': w.get('intensity', 0),
            })
        
        # Sort by absolute TSS (strongest flow first)
        rows.sort(key=lambda r: abs(r['tss']), reverse=True)
        return rows
    
    def get_all_groups_summary(self, window: str = 'TSS_15M') -> List[Dict]:
        """
        Get summary for ALL groups sorted by group TSS score.
        Includes hit frequency, avg lot sizes, total up/down volume, tick counts.
        Returns: [{group, tss, member_count, total_up_vol, total_dn_vol, ...}, ...]
        """
        rows = []
        for group_key, data in self._cached_groups.items():
            w = data.get('windows', {}).get(window, {})
            if not w.get('valid'):
                continue
            
            # Aggregate per-group stats from member symbols
            total_up_vol = 0
            total_dn_vol = 0
            total_up_ticks = 0
            total_dn_ticks = 0
            total_flat_ticks = 0
            total_ticks = 0
            total_up_impact = 0.0
            total_dn_impact = 0.0
            intensities = []
            
            for sym in data.get('symbols', {}):
                if sym not in self._cached_results:
                    continue
                sw = self._cached_results[sym].get('windows', {}).get(window, {})
                if not sw.get('valid'):
                    continue
                total_up_vol += sw.get('up_vol', 0)
                total_dn_vol += sw.get('down_vol', 0)
                total_up_ticks += sw.get('up_ticks', 0)
                total_dn_ticks += sw.get('down_ticks', 0)
                total_flat_ticks += sw.get('flat_ticks', 0)
                total_ticks += sw.get('tick_count', 0)
                total_up_impact += sw.get('up_impact', 0)
                total_dn_impact += sw.get('down_impact', 0)
                intensities.append(sw.get('intensity', 0))
            
            active = total_up_ticks + total_dn_ticks
            avg_up_lot = round(total_up_vol / total_up_ticks, 0) if total_up_ticks > 0 else 0
            avg_dn_lot = round(total_dn_vol / total_dn_ticks, 0) if total_dn_ticks > 0 else 0
            hit_ratio = round(total_up_ticks / active * 100, 1) if active > 0 else 50.0
            avg_intensity = round(sum(intensities) / len(intensities), 2) if intensities else 0
            
            rows.append({
                'group': group_key,
                'tss': w.get('score', 0),
                'member_count': w.get('member_count', 0),
                'symbol_count': data.get('symbol_count', 0),
                # Hit stats
                'total_up_vol': total_up_vol,
                'total_dn_vol': total_dn_vol,
                'total_up_ticks': total_up_ticks,
                'total_dn_ticks': total_dn_ticks,
                'total_flat_ticks': total_flat_ticks,
                'total_ticks': total_ticks,
                'avg_up_lot': avg_up_lot,
                'avg_dn_lot': avg_dn_lot,
                'hit_ratio_up_pct': hit_ratio,  # % of directional ticks that are UP
                'avg_intensity': avg_intensity,
                'total_up_impact': round(total_up_impact, 1),
                'total_dn_impact': round(total_dn_impact, 1),
            })
        
        rows.sort(key=lambda r: r['tss'], reverse=True)
        return rows
    
    def get_dashboard_data(self, window: str = 'TSS_15M') -> Dict[str, Any]:
        """
        Full dashboard payload: symbols + groups + metadata.
        """
        return {
            'window': window,
            'available_windows': list(WINDOWS.keys()),
            'last_compute': self._last_compute_ts,
            'age_seconds': round(time.time() - self._last_compute_ts, 1) if self._last_compute_ts else None,
            'symbols': self.get_all_symbols_summary(window),
            'groups': self.get_all_groups_summary(window),
            'total_symbols': len(self._cached_results),
            'total_groups': len(self._cached_groups),
        }


# ═══════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════

_truth_shift_engine: Optional[TruthShiftEngine] = None


def get_truth_shift_engine() -> TruthShiftEngine:
    """Get or create singleton TruthShiftEngine instance."""
    global _truth_shift_engine
    if _truth_shift_engine is None:
        _truth_shift_engine = TruthShiftEngine()
    return _truth_shift_engine
