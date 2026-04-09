"""
MinMax Area Service — BEFDAY-Based Fixed Daily Bands
=====================================================

Per-symbol today's min/max qty bounds. Computed ONCE per day per account
(exactly like BEFDAY), then FIXED for the entire trading day.

Concept:
    todays_max_qty = befday_qty + increase_limit   (capped by MAXALW)
    todays_min_qty = befday_qty - decrease_limit   (capped by -MAXALW)

    These values DO NOT CHANGE during the day.
    Every order must keep potential_qty = current_qty ± order_qty
    within [todays_min_qty, todays_max_qty].

Design:
    - increase_limit is based on portfolio % rules from DailyLimitService
    - decrease_limit is based on BEFDAY % rules from DailyLimitService
    - MAXALW is the absolute position cap from static data
    - Sign reversal cap: long→short only allowed up to increase_limit
    - Computed & persisted to Redis + CSV once per day
    - current_qty is NOT used in band computation (only for validation)
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
import os
import csv
import json
import time

from loguru import logger

MIN_LOT_INCREASE = 200  # Minimum lot for any position-increase order
MIN_LOT_DECREASE = 125  # Minimum lot for any position-decrease order (LT_TRIM, KARBOTU)
MIN_LOT_DECREASE_CLEANUP = 70  # 70-125 arası pozisyonlar tamamen kapatılabilir (ters pozisyona geçmemek şartıyla)
LOT_ROUND = 100  # Emir miktarı trim edildiğinde 100'lük yuvarlanır (limit aşılmasın)

# Hesap bazlı MinMax CSV: her hesap ayrı dosyaya yazılır
MINMAX_CSV_BY_ACCOUNT = {
    "IBKR_PED": "minmaxarea_ped.csv",
    "IBKR_GUN": "minmaxarea_gun.csv",
    "HAMPRO": "minmaxarea_ham.csv",
}

# Redis key for persisted MinMax (computed once per day, like BEFDAY)
MINMAX_REDIS_KEY_PREFIX = "psfalgo:minmax:daily"  # psfalgo:minmax:daily:{account_id}


def get_minmax_csv_path_for_account(account_id: str, root: Optional[Path] = None) -> Path:
    """Aktif hesaba göre MinMax CSV dosya yolu (minmaxarea_ped/gun/ham.csv)."""
    if root is None:
        root = Path(os.getcwd())
        if "quant_engine" in str(root):
            root = root.parent
    filename = MINMAX_CSV_BY_ACCOUNT.get((account_id or "").strip().upper(), "minmaxarea.csv")
    return root / filename


@dataclass
class MinMaxRow:
    """One row of minmax area for a symbol — FIXED for the entire day."""
    symbol: str
    befday_qty: float           # BEFDAY quantity (day-start, sacred)
    maxalw: float               # Absolute position cap from static data
    increase_limit_qty: float   # Max lots we can ADD in increase direction (from BEFDAY)
    decrease_limit_qty: float   # Max lots we can REDUCE in decrease direction (from BEFDAY)
    todays_max_qty: float       # Ceiling — FIXED all day (toward +∞)
    todays_min_qty: float       # Floor   — FIXED all day (toward -∞)
    current_qty: float = 0.0    # Latest current qty (for display/logging only, NOT used in band calc)
    binding_max: Optional[str] = None
    binding_min: Optional[str] = None


def compute_minmax_row(
    symbol: str,
    befday_qty: float,
    maxalw: float,
    increase_limit_qty: float,
    decrease_limit_qty: float,
) -> MinMaxRow:
    """
    Compute todays_max_qty and todays_min_qty for one symbol.
    
    BEFDAY-BASED: Uses befday_qty (not current_qty!) to set fixed daily bands.
    
    Band calculation:
        todays_max_qty = befday_qty + capacity_toward_plus_inf
        todays_min_qty = befday_qty - capacity_toward_minus_inf
    
    Direction logic (from BEFDAY position):
        Long BEFDAY (befday >= 0):
            - Capacity toward +∞ = increase_limit (can add more long)
            - Capacity toward -∞ = decrease_limit (can sell down)
        Short BEFDAY (befday < 0):
            - Capacity toward +∞ = decrease_limit (can cover shorts)
            - Capacity toward -∞ = increase_limit (can add more short)
    
    MAXALW cap: Position cannot exceed maxalw in absolute value.
    Sign reversal cap: If befday is long, short side capped at increase_limit.
    """
    # Direction-aware capacities
    if befday_qty >= 0:
        # Long/flat: toward +∞ is increase, toward -∞ is decrease
        cap_right = increase_limit_qty
        cap_left = decrease_limit_qty
    else:
        # Short: toward +∞ is decrease (cover), toward -∞ is increase (add short)
        cap_right = decrease_limit_qty
        cap_left = increase_limit_qty

    raw_max = befday_qty + cap_right
    raw_min = befday_qty - cap_left

    # MAXALW cap: position cannot exceed ±maxalw
    todays_max_qty = min(raw_max, maxalw) if maxalw > 0 else raw_max
    todays_min_qty = max(raw_min, -maxalw) if maxalw > 0 else raw_min

    # Sign reversal cap:
    # Long befday → shorting capped at increase_limit from zero
    # Short befday → going long capped at increase_limit from zero
    if befday_qty > 0:
        todays_min_qty = max(todays_min_qty, -increase_limit_qty)
    elif befday_qty < 0:
        todays_max_qty = min(todays_max_qty, increase_limit_qty)

    return MinMaxRow(
        symbol=symbol,
        befday_qty=befday_qty,
        maxalw=maxalw,
        increase_limit_qty=increase_limit_qty,
        decrease_limit_qty=decrease_limit_qty,
        todays_max_qty=todays_max_qty,
        todays_min_qty=todays_min_qty,
        current_qty=befday_qty,  # Initialize to befday (will be updated on validation)
    )


class MinMaxAreaService:
    """
    Compute and persist per-symbol min/max qty for the day.
    
    ONCE-PER-DAY computation (like BEFDAY):
    - compute_for_account() calculates bands using BEFDAY quantities
    - Bands are FIXED for the entire day
    - Persisted to Redis and CSV
    - validate_order_against_minmax() checks LIVE current_qty against fixed bands
    """

    def __init__(self):
        # Per-account cache: {account_id: {symbol: MinMaxRow}}
        self._cache_by_account: Dict[str, Dict[str, MinMaxRow]] = {}
        # Track when each account was computed (to enforce once-per-day)
        self._computed_date_by_account: Dict[str, str] = {}

    def is_computed_today(self, account_id: str) -> bool:
        """Check if MinMax has already been computed today for this account."""
        from datetime import date
        today_str = date.today().isoformat()
        return self._computed_date_by_account.get(account_id) == today_str

    def compute_for_account(
        self,
        account_id: str,
        symbols: Optional[List[str]] = None,
        befday_override: Optional[Dict[str, float]] = None,
        force: bool = False,
    ) -> List[MinMaxRow]:
        """
        Compute minmax area for all PREF symbols (or given list).
        
        ONCE-PER-DAY: If already computed today, returns cached data unless force=True.
        Uses BEFDAY quantities as the basis (NOT current positions).
        """
        from datetime import date
        from app.psfalgo.daily_limit_service import get_daily_limit_service
        from app.psfalgo.position_snapshot_api import PositionSnapshotAPI
        from app.market_data.static_data_store import get_static_store
        from app.core.data_fabric import get_data_fabric
        from app.core.redis_client import get_redis_client

        today_str = date.today().isoformat()

        # ── ONCE-PER-DAY CHECK ──
        if not force and self._computed_date_by_account.get(account_id) == today_str:
            cached = self._cache_by_account.get(account_id, {})
            # CRITICAL: Only return cached if it has REAL befday data
            # (not all zeros from a failed befday load)
            if cached:
                has_real_befday = any(r.befday_qty != 0 for r in cached.values())
                if has_real_befday:
                    logger.debug(
                        f"[MinMaxArea] Already computed today for {account_id} "
                        f"({len(cached)} symbols) — returning cached"
                    )
                    return list(cached.values())
                else:
                    logger.warning(
                        f"[MinMaxArea] ⚠️ Cached MinMax for {account_id} has ALL befday=0 — "
                        f"re-computing (BEFDAY was probably not loaded when first computed)"
                    )
                    # Fall through to recompute

        # Try loading from Redis (persisted from earlier today)
        if not force:
            loaded = self._load_from_redis(account_id)
            if loaded:
                # Validate: Redis data must have real befday entries (not all zeros)
                has_real_befday = any(r.befday_qty != 0 for r in loaded.values())
                if has_real_befday:
                    logger.info(
                        f"[MinMaxArea] ✅ Loaded {len(loaded)} MinMax rows from Redis "
                        f"for {account_id} (computed earlier today)"
                    )
                    self._cache_by_account[account_id] = loaded
                    self._computed_date_by_account[account_id] = today_str
                    return list(loaded.values())
                else:
                    logger.warning(
                        f"[MinMaxArea] ⚠️ Redis MinMax for {account_id} has ALL befday=0 — "
                        f"ignoring stale data, will recompute fresh"
                    )

        limit_svc = get_daily_limit_service()
        pos_api = PositionSnapshotAPI()
        static_store = get_static_store()
        fabric = get_data_fabric()

        if symbols is None:
            symbols = static_store.get_all_symbols() if (static_store and static_store.is_loaded()) else []
        if not symbols:
            logger.warning("[MinMaxArea] No symbols to compute")
            return []

        # ── BEFDAY quantities (source of truth for band computation) ──
        befday_map: Dict[str, float] = {}
        if befday_override is not None:
            befday_map = dict(befday_override)
        
        if not befday_map:
            # Load from BEFDAY Redis key (sacred, captured once at day start)
            try:
                r = get_redis_client()
                if r:
                    befday_key = f"psfalgo:befday:positions:{account_id}"
                    date_key = f"psfalgo:befday:date:{account_id}"
                    
                    # CRITICAL: Verify date matches TODAY before using Redis BEFDAY
                    # The Redis key has a 24h TTL, but data from yesterday (e.g. written
                    # at 20:18) could still be alive at 09:00 today — that's STALE!
                    stored_date = r.get(date_key)
                    if stored_date:
                        stored_date_str = stored_date.decode() if isinstance(stored_date, bytes) else stored_date
                        from datetime import date as _date_check
                        today_yyyymmdd = _date_check.today().strftime("%Y%m%d")
                        if stored_date_str != today_yyyymmdd:
                            logger.warning(
                                f"[MinMaxArea] 🗑️ Redis BEFDAY STALE for {account_id}: "
                                f"stored={stored_date_str}, today={today_yyyymmdd} — deleting and falling back to CSV"
                            )
                            r.delete(befday_key)
                            r.delete(date_key)
                        else:
                            # Date matches — load the data
                            raw_bef = r.get(befday_key)
                            if raw_bef:
                                bef_data = json.loads(raw_bef.decode() if isinstance(raw_bef, bytes) else raw_bef)
                                if isinstance(bef_data, list):
                                    for entry in bef_data:
                                        sym = entry.get('symbol', '')
                                        bef_qty = float(entry.get('qty', entry.get('quantity', 0)))
                                        if sym:
                                            befday_map[sym] = bef_qty
                                elif isinstance(bef_data, dict):
                                    for sym, info in bef_data.items():
                                        if sym == '_meta':
                                            continue
                                        if isinstance(info, dict):
                                            befday_map[sym] = float(info.get('qty', info.get('quantity', 0)) or 0)
                                        else:
                                            befday_map[sym] = float(info or 0)
                                logger.info(f"[MinMaxArea] Loaded {len(befday_map)} BEFDAY entries for {account_id}")
                    else:
                        # No date key — try loading data anyway (backward compatibility)
                        # but verify it's reasonable
                        raw_bef = r.get(befday_key)
                        if raw_bef:
                            bef_data = json.loads(raw_bef.decode() if isinstance(raw_bef, bytes) else raw_bef)
                            if isinstance(bef_data, list):
                                for entry in bef_data:
                                    sym = entry.get('symbol', '')
                                    bef_qty = float(entry.get('qty', entry.get('quantity', 0)))
                                    if sym:
                                        befday_map[sym] = bef_qty
                            elif isinstance(bef_data, dict):
                                for sym, info in bef_data.items():
                                    if sym == '_meta':
                                        continue
                                    if isinstance(info, dict):
                                        befday_map[sym] = float(info.get('qty', info.get('quantity', 0)) or 0)
                                    else:
                                        befday_map[sym] = float(info or 0)
                            if befday_map:
                                logger.info(f"[MinMaxArea] Loaded {len(befday_map)} BEFDAY entries for {account_id} (no date key — legacy)")
            except Exception as e:
                logger.debug(f"[MinMaxArea] BEFDAY Redis read error: {e}")

        if not befday_map:
            # Fallback: load from befday CSV
            if hasattr(pos_api, "_load_befday_map"):
                raw_bef = pos_api._load_befday_map(account_id)
                befday_map = {sym: float(info.get("quantity", 0) or 0) for sym, info in raw_bef.items()}
                logger.info(f"[MinMaxArea] Loaded {len(befday_map)} BEFDAY entries from CSV for {account_id}")

        if not befday_map:
            logger.warning(f"[MinMaxArea] ⚠️ No BEFDAY data for {account_id}! MinMax will use 0 as befday.")

        # Portfolio total from BEFDAY (not current — bands are based on day-start)
        portfolio_total_qty = sum(abs(q) for q in befday_map.values()) or 1.0

        rows: List[MinMaxRow] = []
        for symbol in symbols:
            befday_qty = befday_map.get(symbol, 0.0)

            # MAXALW from static/fabric
            maxalw = 5000.0
            if fabric:
                snap = fabric.get_fast_snapshot(symbol)
                if snap and snap.get("MAXALW") is not None:
                    maxalw = float(snap["MAXALW"])
            if maxalw <= 0 and static_store and static_store.is_loaded():
                sd = static_store.get_static_data(symbol)
                if sd and sd.get("AVG_ADV"):
                    try:
                        maxalw = max(100, int(float(sd["AVG_ADV"]) / 10))
                    except (ValueError, TypeError):
                        pass
            if maxalw <= 0:
                maxalw = 5000.0

            # Get daily limits using BEFDAY values (not current!)
            # daily_net_change = 0 because we compute at day start (befday IS current at that point)
            limits = limit_svc.calculate_limits(
                symbol=symbol,
                befday_qty=befday_qty,
                current_qty=befday_qty,  # At day start, current = befday
                maxalw=maxalw,
                portfolio_total_qty=portfolio_total_qty,
                daily_net_change=0.0,  # At day start, no change yet
            )

            inc_qty = limits["increase"]["limit_qty"]  # FULL limit (not remaining — no trades yet)
            dec_info = limits["decrease"]
            dec_qty = dec_info["limit_qty"]
            if dec_qty == float("inf"):
                dec_qty = maxalw * 2

            row = compute_minmax_row(
                symbol=symbol,
                befday_qty=befday_qty,
                maxalw=maxalw,
                increase_limit_qty=float(inc_qty),
                decrease_limit_qty=float(dec_qty),
            )
            rows.append(row)

        # Persist
        if rows:
            cache = {r.symbol: r for r in rows}
            self._cache_by_account[account_id] = cache
            
            # CRITICAL: Only mark as "computed today" if we had REAL befday data.
            # If befday_map was empty (0 entries), we do NOT mark as computed —
            # this allows the next cycle to retry after BEFDAY becomes available.
            has_real_befday = len(befday_map) > 0
            if has_real_befday:
                self._computed_date_by_account[account_id] = today_str
                # Save to Redis (persists for today, expires at midnight + buffer)
                self._save_to_redis(account_id, cache)
                # Save to CSV
                self.save_to_csv(account_id, rows)
                logger.info(
                    f"[MinMaxArea] ✅ Computed DAILY MinMax for {account_id}: "
                    f"{len(rows)} symbols (BEFDAY-based, FIXED for today)"
                )
            else:
                logger.warning(
                    f"[MinMaxArea] ⚠️ Computed MinMax for {account_id} WITH EMPTY BEFDAY! "
                    f"NOT marking as done — will retry on next cycle when BEFDAY is available. "
                    f"{len(rows)} symbols computed with befday=0 (temporary fallback)."
                )
        else:
            self._cache_by_account[account_id] = {}

        return rows

    def get_row(self, account_id: str, symbol: str) -> Optional[MinMaxRow]:
        """Get cached minmax row for symbol; compute daily if not done today.
        
        IMPORTANT: If already computed today but symbol is missing from cache,
        we create a DEFAULT row (befday=0, generous limits) and add it to cache.
        We do NOT force-recompute — that was causing per-order CSV overwrites
        and log spam ("Saved 1 rows to minmaxarea_ham.csv" for every order).
        """
        acct_cache = self._cache_by_account.get(account_id, {})
        if symbol not in acct_cache:
            if not self.is_computed_today(account_id):
                # First time today — compute all symbols
                self.compute_for_account(account_id)
                acct_cache = self._cache_by_account.get(account_id, {})
            
            if symbol not in acct_cache:
                # Symbol not in universe (not in BEFDAY or static data)
                # Create a default permissive row so orders aren't blocked
                # but don't recompute / rewrite CSV for a single symbol
                from app.market_data.static_data_store import get_static_store
                from app.core.data_fabric import get_data_fabric
                
                maxalw = 5000.0
                try:
                    fabric = get_data_fabric()
                    if fabric:
                        snap = fabric.get_fast_snapshot(symbol)
                        if snap and snap.get("MAXALW") is not None:
                            maxalw = float(snap["MAXALW"])
                    if maxalw <= 0:
                        static_store = get_static_store()
                        if static_store and static_store.is_loaded():
                            sd = static_store.get_static_data(symbol)
                            if sd and sd.get("AVG_ADV"):
                                maxalw = max(100, int(float(sd["AVG_ADV"]) / 10))
                except Exception:
                    pass
                if maxalw <= 0:
                    maxalw = 5000.0
                
                default_row = compute_minmax_row(
                    symbol=symbol,
                    befday_qty=0.0,
                    maxalw=maxalw,
                    increase_limit_qty=maxalw,
                    decrease_limit_qty=maxalw,
                )
                # Add to cache (no Redis/CSV save — this is a transient addition)
                if account_id not in self._cache_by_account:
                    self._cache_by_account[account_id] = {}
                self._cache_by_account[account_id][symbol] = default_row
                logger.debug(
                    f"[MinMaxArea] Created default row for {symbol} "
                    f"(not in daily compute, maxalw={maxalw:.0f})"
                )
                return default_row
        
        return acct_cache.get(symbol)

    def get_all_rows(self, account_id: str) -> Dict[str, MinMaxRow]:
        """Get full cache; compute if needed."""
        acct_cache = self._cache_by_account.get(account_id)
        if not acct_cache:
            self.compute_for_account(account_id)
            acct_cache = self._cache_by_account.get(account_id, {})
        return dict(acct_cache)

    # ═══════════════════════════════════════════════════════════════
    # Redis Persistence (load/save daily bands)
    # ═══════════════════════════════════════════════════════════════

    def _save_to_redis(self, account_id: str, cache: Dict[str, MinMaxRow]):
        """Persist MinMax bands to Redis (expires end of day + 2h buffer)."""
        try:
            from app.core.redis_client import get_redis_client
            from datetime import date
            r = get_redis_client()
            if not r:
                return
            key = f"{MINMAX_REDIS_KEY_PREFIX}:{account_id}"
            data = {
                '_meta': {
                    'computed_at': time.time(),
                    'date': date.today().isoformat(),
                    'account_id': account_id,
                    'count': len(cache),
                },
            }
            for sym, row in cache.items():
                data[sym] = {
                    'symbol': row.symbol,
                    'befday_qty': row.befday_qty,
                    'maxalw': row.maxalw,
                    'increase_limit_qty': row.increase_limit_qty,
                    'decrease_limit_qty': row.decrease_limit_qty,
                    'todays_max_qty': row.todays_max_qty,
                    'todays_min_qty': row.todays_min_qty,
                }
            r.set(key, json.dumps(data), ex=86400)  # 24h TTL
            logger.debug(f"[MinMaxArea] Saved {len(cache)} rows to Redis for {account_id}")
        except Exception as e:
            logger.warning(f"[MinMaxArea] Redis save error: {e}")

    def _load_from_redis(self, account_id: str) -> Optional[Dict[str, MinMaxRow]]:
        """Load persisted MinMax bands from Redis (if computed today)."""
        try:
            from app.core.redis_client import get_redis_client
            from datetime import date
            r = get_redis_client()
            if not r:
                return None
            key = f"{MINMAX_REDIS_KEY_PREFIX}:{account_id}"
            raw = r.get(key)
            if not raw:
                return None
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            meta = data.get('_meta', {})
            stored_date = meta.get('date', '')
            if stored_date != date.today().isoformat():
                logger.debug(f"[MinMaxArea] Redis data is from {stored_date}, not today — recomputing")
                return None
            
            result = {}
            for sym, info in data.items():
                if sym == '_meta':
                    continue
                if isinstance(info, dict):
                    result[sym] = MinMaxRow(
                        symbol=info.get('symbol', sym),
                        befday_qty=float(info.get('befday_qty', 0)),
                        maxalw=float(info.get('maxalw', 5000)),
                        increase_limit_qty=float(info.get('increase_limit_qty', 0)),
                        decrease_limit_qty=float(info.get('decrease_limit_qty', 0)),
                        todays_max_qty=float(info.get('todays_max_qty', 0)),
                        todays_min_qty=float(info.get('todays_min_qty', 0)),
                    )
            return result if result else None
        except Exception as e:
            logger.debug(f"[MinMaxArea] Redis load error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # CSV Persistence
    # ═══════════════════════════════════════════════════════════════

    def save_to_csv(self, account_id: str, rows: Optional[List[MinMaxRow]] = None):
        """Write minmax rows to CSV (one file per account)."""
        if rows is None:
            rows = list(self._cache_by_account.get(account_id, {}).values())
        if not rows:
            return
        filepath = get_minmax_csv_path_for_account(account_id)
        try:
            with open(filepath, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "symbol", "befday_qty", "maxalw",
                    "increase_limit_qty", "decrease_limit_qty",
                    "todays_max_qty", "todays_min_qty",
                ])
                w.writeheader()
                for r in rows:
                    w.writerow({
                        "symbol": r.symbol,
                        "befday_qty": r.befday_qty,
                        "maxalw": r.maxalw,
                        "increase_limit_qty": r.increase_limit_qty,
                        "decrease_limit_qty": r.decrease_limit_qty,
                        "todays_max_qty": r.todays_max_qty,
                        "todays_min_qty": r.todays_min_qty,
                    })
            logger.info(f"[MinMaxArea] 📄 Saved {len(rows)} rows to {filepath.name}")
        except Exception as ex:
            logger.warning(f"[MinMaxArea] CSV write error: {ex}")

    def load_from_csv(self, account_id: str) -> Dict[str, MinMaxRow]:
        """Load minmax rows from CSV."""
        filepath = get_minmax_csv_path_for_account(account_id)
        if not filepath.exists():
            return {}
        out = {}
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    sym = row.get("symbol", "").strip()
                    if not sym:
                        continue
                    out[sym] = MinMaxRow(
                        symbol=sym,
                        befday_qty=float(row.get("befday_qty", 0) or 0),
                        maxalw=float(row.get("maxalw", 0) or 0),
                        increase_limit_qty=float(row.get("increase_limit_qty", 0) or 0),
                        decrease_limit_qty=float(row.get("decrease_limit_qty", 0) or 0),
                        todays_max_qty=float(row.get("todays_max_qty", 0) or 0),
                        todays_min_qty=float(row.get("todays_min_qty", 0) or 0),
                    )
                except (ValueError, TypeError) as e:
                    logger.debug(f"[MinMaxArea] Skip row {row}: {e}")
        if account_id:
            self._cache_by_account[account_id] = out
        return out


# ═══════════════════════════════════════════════════════════════
# Validation Functions (use LIVE current_qty against FIXED bands)
# ═══════════════════════════════════════════════════════════════

def validate_order_against_minmax(
    account_id: str,
    symbol: str,
    action: str,
    qty: int,
    current_qty: float,
    minmax_row: Optional[MinMaxRow] = None,
    minmax_service: Optional[MinMaxAreaService] = None,
) -> Tuple[bool, int, str]:
    """
    Ensure order keeps potential_qty within FIXED [todays_min_qty, todays_max_qty].

    The bands are computed ONCE per day (from BEFDAY) and NEVER change.
    current_qty is the LIVE position (from Redis, updated by worker + fill events).

    Core math:
      BUY  qty → potential = current + qty  → must be ≤ todays_max (FIXED)
      SELL qty → potential = current - qty  → must be ≥ todays_min (FIXED)

    If potential exceeds band, qty is trimmed DOWN (never up).
    Returns: (allowed, adjusted_qty, reason).
    """
    if minmax_row is None:
        svc = minmax_service or MinMaxAreaService()
        minmax_row = svc.get_row(account_id, symbol)
    if minmax_row is None:
        return True, qty, "No minmax data"

    def _round_down_to_lot(x: float) -> int:
        """Round down to nearest LOT_ROUND (100). Always >= 0."""
        if x <= 0:
            return 0
        return int(x // LOT_ROUND) * LOT_ROUND

    is_buy = action.upper() in ("BUY", "ADD", "COVER")

    # ═══════════════════════════════════════════════════════════════
    # CORE LOGIC: Check LIVE current against FIXED daily bands
    #
    #   BUY:  headroom = todays_max (FIXED) - current_qty (LIVE)
    #   SELL: headroom = current_qty (LIVE) - todays_min (FIXED)
    # ═══════════════════════════════════════════════════════════════
    if is_buy:
        headroom = minmax_row.todays_max_qty - current_qty
        limit_label = f"max={minmax_row.todays_max_qty:.0f}"
        potential = current_qty + qty
    else:
        headroom = current_qty - minmax_row.todays_min_qty
        limit_label = f"min={minmax_row.todays_min_qty:.0f}"
        potential = current_qty - qty

    if headroom <= 0:
        return False, 0, (
            f"{'BUY' if is_buy else 'SELL'} {qty} blocked: "
            f"current={current_qty:.0f} already at/beyond {limit_label} — no room"
        )

    # Round headroom DOWN to nearest 100 (never exceed the limit)
    max_allowed = _round_down_to_lot(headroom)

    if max_allowed <= 0:
        return False, 0, (
            f"{'BUY' if is_buy else 'SELL'} {qty} blocked: "
            f"headroom={headroom:.0f} rounds to 0 (current={current_qty:.0f}, {limit_label})"
        )

    # Trim: adjusted = min(requested, headroom) — NEVER inflate!
    adjusted_qty = min(qty, max_allowed)

    # Determine if this is a position-INCREASE or position-DECREASE
    is_increase = (
        (current_qty >= 0 and is_buy) or       # Long position + BUY = adding long
        (current_qty <= 0 and not is_buy)       # Short position + SELL = adding short
    )

    # Enforce minimum lot sizes
    if is_increase and adjusted_qty < MIN_LOT_INCREASE:
        return False, 0, (
            f"{'BUY' if is_buy else 'SELL'} trimmed to {adjusted_qty} "
            f"< min increase lot {MIN_LOT_INCREASE}"
        )
    if not is_increase and adjusted_qty < MIN_LOT_DECREASE:
        # ═══════════════════════════════════════════════════════════════
        # CLEANUP ZONE: 70-125 lot arası pozisyonları tamamen kapatmaya izin ver
        # Kural: adjusted_qty >= 70 VE bu qty pozisyonu tam kapatacaksa (ters pozisyona
        # geçmeyecekse), emre izin ver. Bu "ölü pozisyon" sorununu çözer.
        # Örnek: 100 lot long pozisyon → 100 lot SELL emri gönderilir (tam kapanış)
        #        69 lot pozisyon → bloklanır (eski davranış)
        # ═══════════════════════════════════════════════════════════════
        if adjusted_qty >= MIN_LOT_DECREASE_CLEANUP:
            # Tam pozisyon kapatma kontrolü: emir pozisyonu sıfıra getirmeli,
            # ters tarafa geçirmemeli
            abs_current = abs(current_qty)
            is_exact_close = abs(adjusted_qty - abs_current) < 1  # qty == abs(current_qty)
            is_partial_no_flip = adjusted_qty <= abs_current  # pozisyonu azaltır ama ters geçmez
            
            if is_partial_no_flip:
                logger.info(
                    f"[MinMax] 🧹 CLEANUP ZONE: {symbol} {'BUY' if is_buy else 'SELL'} {adjusted_qty} "
                    f"(current={current_qty:.0f}, {MIN_LOT_DECREASE_CLEANUP}≤qty<{MIN_LOT_DECREASE}) — "
                    f"{'exact close' if is_exact_close else 'partial cleanup, no flip'}"
                )
                # İzin ver — aşağıdaki normal akışa devam et
            else:
                # Ters pozisyona geçecek — blokla
                return False, 0, (
                    f"{'BUY' if is_buy else 'SELL'} trimmed to {adjusted_qty} "
                    f"< min decrease lot {MIN_LOT_DECREASE} (cleanup zone rejected: would flip position)"
                )
        else:
            return False, 0, (
                f"{'BUY' if is_buy else 'SELL'} trimmed to {adjusted_qty} "
                f"< min decrease lot {MIN_LOT_DECREASE_CLEANUP}"
            )

    # Build reason
    if adjusted_qty < qty:
        reason = (
            f"Trimmed {qty}→{adjusted_qty} "
            f"(headroom={max_allowed}, {limit_label}, current={current_qty:.0f})"
        )
    else:
        reason = "OK"

    return True, adjusted_qty, reason


def update_minmax_cache_after_order(
    minmax_service: 'MinMaxAreaService',
    symbol: str,
    action: str,
    approved_qty: int,
) -> None:
    """
    Update MinMax cache current_qty after an order is approved.

    CRITICAL for intra-cycle consistency: If PATADD sends BUY 400 for VLYPO,
    then ADDNEWPOS also checks VLYPO, it must see current_qty += 400.
    
    NOTE: todays_max_qty and todays_min_qty are NEVER modified (fixed daily bands).
    Only current_qty is updated for headroom calculation accuracy.
    """
    if not minmax_service or not symbol or approved_qty <= 0:
        return
    # Find row in any account cache
    row = None
    for acct_cache in minmax_service._cache_by_account.values():
        if symbol in acct_cache:
            row = acct_cache[symbol]
            break
    if row is None:
        return

    is_buy = action.upper() in ("BUY", "ADD", "COVER")
    old_qty = row.current_qty
    if is_buy:
        row.current_qty += approved_qty
    else:
        row.current_qty -= approved_qty

    logger.debug(
        f"[MinMax] Cache current_qty updated {symbol}: {old_qty:.0f} → {row.current_qty:.0f} "
        f"after {action} {approved_qty} (bands unchanged: "
        f"[{row.todays_min_qty:.0f}, {row.todays_max_qty:.0f}])"
    )


def is_position_increase(action: str, current_qty: float) -> bool:
    """True if order adds long (BUY when qty>=0) or adds short (SELL when qty<=0)."""
    a = action.upper()
    if a in ("BUY", "ADD", "COVER"):
        return current_qty >= 0  # BUY when long/flat = increase
    if a in ("SELL",):
        return current_qty <= 0  # SELL when short/flat = increase (add short)
    return False


# Singleton
_minmax_area_service: Optional[MinMaxAreaService] = None


def get_minmax_area_service() -> MinMaxAreaService:
    global _minmax_area_service
    if _minmax_area_service is None:
        _minmax_area_service = MinMaxAreaService()
    return _minmax_area_service


def get_max_buy_qty(minmax_row: MinMaxRow, current_qty: float) -> int:
    """
    Calculate maximum BUY quantity allowed within fixed daily bands.
    Uses LIVE current_qty against FIXED todays_max_qty.
    """
    if minmax_row is None:
        return 0
    max_buy = minmax_row.todays_max_qty - current_qty
    return int(max(0, max_buy) // LOT_ROUND) * LOT_ROUND


def get_max_sell_qty(minmax_row: MinMaxRow, current_qty: float) -> int:
    """
    Calculate maximum SELL quantity allowed within fixed daily bands.
    Uses LIVE current_qty against FIXED todays_min_qty.
    """
    if minmax_row is None:
        return 0
    max_sell = current_qty - minmax_row.todays_min_qty
    return int(max(0, max_sell) // LOT_ROUND) * LOT_ROUND


def pre_validate_order_for_runall(
    account_id: str,
    symbol: str,
    action: str,
    qty: int,
) -> tuple[bool, int, str]:
    """
    Pre-validate an order against MinMax constraints BEFORE proposal generation.
    
    Uses LIVE current_qty from Redis against FIXED daily bands.
    """
    svc = get_minmax_area_service()
    row = svc.get_row(account_id, symbol)

    if row is None:
        return True, qty, "No minmax data available"

    # Get LIVE current_qty from Redis (not the cached befday_qty!)
    current_qty = row.current_qty  # This gets updated by update_minmax_cache_after_order
    try:
        from app.core.redis_client import get_redis_client
        r = get_redis_client()
        if r:
            pos_key = f"psfalgo:positions:{account_id}"
            raw = r.get(pos_key)
            if raw:
                data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                if isinstance(data, dict) and symbol in data:
                    info = data[symbol]
                    if isinstance(info, dict):
                        current_qty = float(info.get("qty", 0) or 0)
    except Exception:
        pass

    return validate_order_against_minmax(
        account_id=account_id,
        symbol=symbol,
        action=action,
        qty=qty,
        current_qty=current_qty,
        minmax_row=row,
        minmax_service=svc
    )
