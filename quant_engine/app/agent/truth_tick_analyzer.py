"""
Truth Tick Deep Analyzer — 30-Minute Window Analysis Engine
============================================================

QAGENTT'nin truth tick istatistik modülü.

Her hisse için:
  - Son 5 günlük truth tick serisini Redis'ten çeker
  - 30'ar dakikalık periyodlara böler (9:30-10:00, 10:00-10:30 ...)
  - Her periyotta: tick sayısı, VWAP, hacim, spread, yön analizi
  - DOS grubu bazında karşılaştırma yapar
  - Volume/AVG_ADV oranıyla normalize eder
  - Her DOS grubundaki en ilgi çekici 3 hisseyi seçer

Çıktı: Gemini Flash'a gönderilebilecek yapılandırılmış JSON analiz.
"""

import json
import time
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict

from app.core.logger import logger


# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

# Market hours (ET)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MIN = 0

# 30-minute windows
WINDOW_MINUTES = 30

# Number of TRADING DAYS (iş günü) to look back
LOOKBACK_DAYS = 5  # 5 trading days, not calendar days

# Analysis modes
MODE_BACKTEST = "backtest"  # Historical: no bid/ask, estimate from prints, NO look-ahead
MODE_LIVE = "live"          # Real-time: has bid/ask/last from L1, bias-free

# Top N interesting stocks per group
TOP_N_PER_GROUP = 3

# Minimum truth ticks to consider a stock "active" in a window
MIN_TICKS_PER_WINDOW = 2

# FNRA strict rules (same as TruthTicksEngine)
FNRA_VENUES = {'FNRA', 'ADFN', 'FINRA', 'OTC', 'DARK'}
MIN_LOT_SIZE = 15


# ═══════════════════════════════════════════════════════════════
# Helper: Truth Tick validation (mirrors TruthTicksEngine)
# ═══════════════════════════════════════════════════════════════

def is_truth_tick(tick: Dict[str, Any]) -> bool:
    """Check if a tick qualifies as a Truth Tick."""
    size = tick.get('size', 0)
    venue = str(tick.get('exch', tick.get('venue', 'UNKNOWN'))).upper()

    if size < MIN_LOT_SIZE:
        return False

    if venue in FNRA_VENUES:
        return size == 100 or size == 200

    return True


def _generate_30min_windows() -> List[Dict[str, Any]]:
    """
    Generate 30-minute window definitions for a trading day.

    Returns list of:
        {"label": "09:30-10:00", "start_minutes": 570, "end_minutes": 600}

    Minutes are from midnight (9:30 = 570, 16:00 = 960).
    """
    windows = []
    start = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MIN  # 570
    end = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MIN    # 960

    current = start
    while current < end:
        window_end = min(current + WINDOW_MINUTES, end)
        sh, sm = divmod(current, 60)
        eh, em = divmod(window_end, 60)
        windows.append({
            "label": f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d}",
            "start_minutes": current,
            "end_minutes": window_end,
        })
        current = window_end

    return windows


WINDOWS_30MIN = _generate_30min_windows()
# Pre-compute for quick reference
WINDOW_LABELS = [w["label"] for w in WINDOWS_30MIN]


# ═══════════════════════════════════════════════════════════════
# Core: Fetch truth ticks from Redis
# ═══════════════════════════════════════════════════════════════

def _get_redis_sync():
    """Get sync Redis client."""
    try:
        from app.core.redis_client import get_redis_client
        rc = get_redis_client()
        return rc.sync if rc else None
    except Exception:
        return None


def fetch_truth_ticks_for_symbol(symbol: str, r=None) -> List[Dict[str, Any]]:
    """
    Fetch truth tick data for a symbol from Redis.

    Priority:
        1. tt:ticks:{symbol} — persisted by TruthTicksEngine (12-day TTL, raw ticks)
        2. truth_ticks:inspect:{symbol} — inspector snapshot (path_dataset)

    Returns:
        List of truth tick dicts, sorted by timestamp ascending
    """
    if r is None:
        r = _get_redis_sync()
    if not r:
        return []

    try:
        # === Priority 1: Persisted tick data (from TruthTicksEngine) ===
        persist_key = f"tt:ticks:{symbol}"
        raw_persist = r.get(persist_key)
        if raw_persist:
            try:
                ticks = json.loads(raw_persist)
                if ticks and isinstance(ticks, list):
                    # Already filtered truth ticks — validate and return
                    truth_ticks = []
                    for t in ticks:
                        ts = t.get("ts", 0)
                        price = t.get("price", 0)
                        size = t.get("size", 0)
                        if ts > 0 and price > 0 and size > 0:
                            truth_ticks.append({
                                "ts": float(ts),
                                "price": float(price),
                                "size": float(size),
                                "exch": str(t.get("exch", "UNK")).upper(),
                            })
                    if truth_ticks:
                        truth_ticks.sort(key=lambda x: x["ts"])
                        return truth_ticks
            except (json.JSONDecodeError, TypeError):
                pass

        # === Priority 2: Inspector snapshot (legacy) ===
        key = f"truth_ticks:inspect:{symbol}"
        raw = r.get(key)
        if not raw:
            return []

        data = json.loads(raw)
        if not data.get("success"):
            return []

        inspect = data.get("data", {})

        # path_dataset contains the tick-by-tick data
        ticks_raw = inspect.get("path_dataset", [])

        # Also try raw_history as fallback
        if not ticks_raw:
            ticks_raw = inspect.get("raw_history", [])

        # Also check top_events
        if not ticks_raw:
            ticks_raw = inspect.get("top_events", [])

        if not ticks_raw:
            return []

        # Normalize & filter to truth ticks
        truth_ticks = []
        for t in ticks_raw:
            # Normalize timestamp field
            ts = t.get("ts") or t.get("timestamp") or t.get("time", 0)
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
            ts = float(ts) if ts else 0

            price = t.get("price", 0)
            size = t.get("size", 0)
            venue = t.get("exch") or t.get("venue", "UNKNOWN")

            if ts <= 0 or price <= 0 or size <= 0:
                continue

            tick = {
                "ts": ts,
                "price": float(price),
                "size": float(size),
                "exch": str(venue).upper(),
            }

            if is_truth_tick(tick):
                truth_ticks.append(tick)

        # Sort by timestamp
        truth_ticks.sort(key=lambda x: x["ts"])
        return truth_ticks

    except Exception as e:
        logger.debug(f"[TT-ANALYZER] Error fetching ticks for {symbol}: {e}")
        return []


def fetch_in_memory_ticks(symbol: str) -> List[Dict[str, Any]]:
    """
    Fetch truth ticks directly from TruthTicksEngine's in-memory store.
    This has more data than Redis snapshots.
    """
    try:
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        engine = get_truth_ticks_engine()
        if not engine:
            return []

        with engine._tick_lock:
            if symbol not in engine.tick_store:
                return []
            all_ticks = list(engine.tick_store[symbol])

        # Filter to truth ticks using engine logic
        truth_ticks = [t for t in all_ticks if engine.is_truth_tick(t)]
        truth_ticks.sort(key=lambda x: x.get("ts", 0))
        return truth_ticks

    except Exception as e:
        logger.debug(f"[TT-ANALYZER] In-memory fetch error for {symbol}: {e}")
        return []


def fetch_ticks_from_hammer(symbol: str, last_few: int = 500) -> List[Dict[str, Any]]:
    """
    Fetch historical ticks directly from Hammer Pro API (getTicks command).
    This is the BEST source — works anytime Hammer is connected, even weekends.
    Returns raw trade prints that need truth tick filtering.
    """
    try:
        from app.live.hammer_client import get_hammer_client
        client = get_hammer_client()
        if not client or not client.is_connected():
            return []

        tick_data = client.get_ticks(
            symbol,
            lastFew=last_few,
            tradesOnly=True,
            regHoursOnly=False,
            timeout=3.0,
        )

        if not tick_data or "data" not in tick_data:
            return []

        raw_ticks = tick_data.get("data", [])
        if not raw_ticks:
            return []

        # Convert Hammer tick format to our format and filter truth ticks
        truth_ticks = []
        for t in raw_ticks:
            size = t.get("s", 0)
            venue = str(t.get("e", "UNK")).upper()
            price = t.get("p", 0)
            ts = t.get("t", 0)

            if not price or not size or not ts:
                continue

            # Parse timestamp
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    continue
            ts = float(ts)

            # Truth tick filtering (same rules as GRPAN fetcher)
            is_dark = "FNRA" in venue or "ADFN" in venue or "TRF" in venue or venue == "D"
            if is_dark:
                if size not in (100, 200):
                    continue
            else:
                if size < 15:
                    continue

            truth_ticks.append({
                "ts": ts,
                "price": float(price),
                "size": float(size),
                "exch": venue,
            })

        truth_ticks.sort(key=lambda x: x["ts"])
        return truth_ticks

    except Exception as e:
        logger.debug(f"[TT-ANALYZER] Hammer fetch error for {symbol}: {e}")
        return []


def fetch_all_ticks_for_symbol(symbol: str, r=None) -> List[Dict[str, Any]]:
    """
    Fetch truth ticks from ALL available sources, with priority:
    1. Hammer API (freshest, historical getTicks) — with circuit breaker
    2. In-memory TruthTicksEngine
    3. Redis persisted data (tt:ticks:* or truth_ticks:inspect:*)

    Returns combined, deduplicated, sorted truth ticks.
    """
    all_ticks = []

    # Source 1: Hammer API (with circuit breaker)
    if not hasattr(fetch_all_ticks_for_symbol, '_hammer_fails'):
        fetch_all_ticks_for_symbol._hammer_fails = 0
        fetch_all_ticks_for_symbol._hammer_disabled = False

    if not fetch_all_ticks_for_symbol._hammer_disabled:
        hammer_ticks = fetch_ticks_from_hammer(symbol, last_few=500)
        if hammer_ticks:
            all_ticks.extend(hammer_ticks)
            fetch_all_ticks_for_symbol._hammer_fails = 0  # reset on success
            logger.debug(f"[TT-ANALYZER] {symbol}: {len(hammer_ticks)} ticks from Hammer API")
        else:
            fetch_all_ticks_for_symbol._hammer_fails += 1
            if fetch_all_ticks_for_symbol._hammer_fails >= 10:
                fetch_all_ticks_for_symbol._hammer_disabled = True
                logger.warning(
                    "[TT-ANALYZER] Hammer circuit breaker: 10 consecutive failures, "
                    "switching to Redis/memory only"
                )

    # Source 2: In-memory engine
    mem_ticks = fetch_in_memory_ticks(symbol)
    if mem_ticks:
        all_ticks.extend(mem_ticks)
        logger.debug(f"[TT-ANALYZER] {symbol}: {len(mem_ticks)} ticks from in-memory")

    # Source 3: Redis (persisted or inspect)
    if not all_ticks:
        redis_ticks = fetch_truth_ticks_for_symbol(symbol, r=r)
        if redis_ticks:
            all_ticks.extend(redis_ticks)
            logger.debug(f"[TT-ANALYZER] {symbol}: {len(redis_ticks)} ticks from Redis")

    if not all_ticks:
        return []

    # Deduplicate by (ts, price, size)
    seen = set()
    unique_ticks = []
    for t in all_ticks:
        key = (round(t["ts"], 3), t["price"], t["size"])
        if key not in seen:
            seen.add(key)
            unique_ticks.append(t)

    unique_ticks.sort(key=lambda x: x["ts"])
    return unique_ticks



def _load_gort_from_csv() -> Dict[str, Dict[str, float]]:
    """
    Load GORT and GORT_NORM directly from janalldata.csv.
    These fields are not in StaticDataStore's REQUIRED_FIELDS.
    
    Returns:
        {symbol: {"gort": 0.0, "gort_norm": 50.0}}
    """
    import pandas as pd
    from pathlib import Path
    import os

    possible_paths = [
        Path(r"C:\StockTracker") / 'janalldata.csv',
        Path(os.getcwd()) / 'janalldata.csv',
        Path(r"C:\StockTracker\janall") / 'janalldata.csv',
        Path(os.getcwd()) / 'janall' / 'janalldata.csv',
    ]

    filepath = None
    for p in possible_paths:
        if p.exists():
            filepath = p
            break

    if not filepath:
        logger.debug("[TT-ANALYZER] janalldata.csv not found for GORT loading")
        return {}

    try:
        try:
            df = pd.read_csv(filepath, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, encoding='latin-1')

        result = {}
        for _, row in df.iterrows():
            symbol = str(row.get('PREF IBKR', '')).strip()
            if not symbol or symbol == 'nan':
                continue

            gort = row.get('GORT', None)
            gort_norm = row.get('GORT_NORM', None)

            result[symbol] = {
                "gort": float(gort) if pd.notna(gort) else None,
                "gort_norm": float(gort_norm) if pd.notna(gort_norm) else None,
            }

        logger.info(f"[TT-ANALYZER] Loaded GORT data for {len(result)} symbols")
        return result
    except Exception as e:
        logger.warning(f"[TT-ANALYZER] GORT CSV load error: {e}")
        return {}


def _fetch_l1_data_for_symbol(symbol: str, r=None) -> Optional[Dict[str, Any]]:
    """
    Fetch Level 1 bid/ask/last data from Redis for live mode.
    
    Returns:
        {"bid": 24.50, "ask": 24.55, "last": 24.52, "bid_size": 100, "ask_size": 200}
        or None if unavailable.
    """
    if r is None:
        r = _get_redis_sync()
    if not r:
        return None

    try:
        # Try common Redis keys for L1 data
        for key_pattern in [f"l1:{symbol}", f"market_data:l1:{symbol}", f"hammer:l1:{symbol}"]:
            raw = r.get(key_pattern)
            if raw:
                data = json.loads(raw)
                return {
                    "bid": float(data.get("bid", data.get("bidPrice", 0)) or 0),
                    "ask": float(data.get("ask", data.get("askPrice", 0)) or 0),
                    "last": float(data.get("last", data.get("lastPrice", 0)) or 0),
                    "bid_size": int(data.get("bidSize", data.get("bid_size", 0)) or 0),
                    "ask_size": int(data.get("askSize", data.get("ask_size", 0)) or 0),
                }
    except Exception:
        pass
    return None


def get_all_symbols_with_groups() -> Dict[str, Dict[str, Any]]:
    """
    Get all symbols with DOS group, AVG_ADV, FBtot, SFStot, GORT, and other fields.

    Scoring fields:
        - FBtot (FINAL_THG): Long-term LONG suitability score
        - SFStot (SHORT_FINAL): Long-term SHORT suitability score  
        - GORT: Mean reversion anchor (0 = at mean, positive = above, negative = below)
        - GORT_NORM: Normalized GORT (0-100 scale, 50 = at mean)

    Returns:
        {symbol: {"group": "...", "avg_adv": 12000, "fbtot": 1.5, "sfstot": 1.3, ...}}
    """
    try:
        from app.market_data.static_data_store import get_static_store
        store = get_static_store()
        if not store or not store.is_loaded():
            return {}

        # Load GORT data directly from CSV (not in StaticDataStore)
        gort_data = _load_gort_from_csv()

        result = {}
        for symbol in store.get_all_symbols():
            data = store.get_static_data(symbol)
            if not data:
                continue

            group = data.get("GROUP", "unknown")
            avg_adv = float(data.get("AVG_ADV", 0) or 0)
            if avg_adv <= 0:
                continue  # Skip stocks without volume data

            # Get GORT from CSV supplement
            gort = gort_data.get(symbol, {})

            result[symbol] = {
                "group": group,
                "avg_adv": avg_adv,
                # === SCORING FIELDS (renamed for clarity) ===
                "fbtot": data.get("FINAL_THG"),       # FBtot: LT Long score
                "sfstot": data.get("SHORT_FINAL"),    # SFStot: LT Short score
                "gort": gort.get("gort"),             # GORT: mean reversion position
                "gort_norm": gort.get("gort_norm"),   # GORT_NORM: 0-100 scale
                # === TREND/MOMENTUM ===
                "sma63_chg": data.get("SMA63 chg"),   # 63-day momentum
                "sma246_chg": data.get("SMA246 chg"), # 246-day momentum (LT trend)
                # === METADATA ===
                "cmon": data.get("CMON"),
                "cgrup": data.get("CGRUP"),
                "prev_close": data.get("prev_close"),
                "smi": data.get("SMI"),
            }

        return result

    except Exception as e:
        logger.error(f"[TT-ANALYZER] Error loading static data: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════
# Core: 30-Minute Window Analysis
# ═══════════════════════════════════════════════════════════════

def _ts_to_minute_of_day(ts: float) -> int:
    """Convert unix timestamp to minute-of-day (0-1439)."""
    dt = datetime.fromtimestamp(ts)
    return dt.hour * 60 + dt.minute


def _ts_to_date_str(ts: float) -> str:
    """Convert unix timestamp to date string (YYYY-MM-DD)."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _is_trading_day(dt: datetime) -> bool:
    """Check if a date is a trading day (Mon-Fri)."""
    return dt.weekday() < 5  # 0=Mon, 4=Fri


def _get_trading_day_cutoff(trading_days: int = 5) -> float:
    """
    Calculate the cutoff timestamp for N trading days (iş günü) back.
    
    Skips weekends. For example, if today is Monday and trading_days=5,
    we go back to previous Monday (skipping Sat+Sun).
    
    Args:
        trading_days: Number of TRADING days to look back (default 5)
    
    Returns:
        Unix timestamp of the cutoff (start of the earliest trading day)
    """
    now = datetime.now()
    current = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    days_counted = 0
    while days_counted < trading_days:
        current -= timedelta(days=1)
        if _is_trading_day(current):
            days_counted += 1
    
    # Return the start of that trading day (market open: 9:30 ET)
    cutoff = current.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MIN)
    return cutoff.timestamp()


def analyze_symbol_windows(
    symbol: str,
    truth_ticks: List[Dict[str, Any]],
    avg_adv: float,
    lookback_days: int = LOOKBACK_DAYS,
) -> Dict[str, Any]:
    """
    Analyze a single symbol's truth ticks across 30-minute windows.

    Returns:
        {
            "symbol": "NLY PRD",
            "total_ticks": 145,
            "days_covered": 4,
            "avg_adv": 15000,
            "windows": {
                "09:30-10:00": {
                    "avg_ticks": 5.2,
                    "avg_volume": 1200,
                    "vol_adv_ratio": 0.08,
                    "avg_vwap": 24.55,
                    "price_range_avg": 0.12,
                    "direction": "buyer",  # buyer/seller/neutral
                    "daily_breakdown": { "2026-02-14": {...}, ... }
                },
                ...
            },
            "busiest_window": "09:30-10:00",
            "quietest_window": "14:30-15:00",
            "total_volume": 25000,
            "vol_adv_ratio_total": 1.67,
            "venue_mix": {"NYSE": 0.45, "FNRA": 0.30, "ARCA": 0.25},
            "interest_score": 7.5  # composite score for ranking
        }
    """
    if not truth_ticks:
        return None

    # Use TRADING DAY cutoff (iş günü — Mon-Fri only)
    cutoff_ts = _get_trading_day_cutoff(trading_days=lookback_days)
    relevant_ticks = [t for t in truth_ticks if t["ts"] >= cutoff_ts]
    
    # Further filter: only keep ticks from actual trading days
    relevant_ticks = [
        t for t in relevant_ticks
        if _is_trading_day(datetime.fromtimestamp(t["ts"]))
    ]

    if len(relevant_ticks) < 3:
        return None

    # Organize ticks by date and window
    # {date_str: {window_label: [ticks]}}
    day_window_ticks = defaultdict(lambda: defaultdict(list))
    dates_seen = set()

    for tick in relevant_ticks:
        date_str = _ts_to_date_str(tick["ts"])
        minute = _ts_to_minute_of_day(tick["ts"])
        dates_seen.add(date_str)

        # Find which window this tick belongs to
        for w in WINDOWS_30MIN:
            if w["start_minutes"] <= minute < w["end_minutes"]:
                day_window_ticks[date_str][w["label"]].append(tick)
                break

    num_days = len(dates_seen)
    if num_days == 0:
        return None

    # Analyze each window (averaged across days)
    windows_analysis = {}
    window_total_ticks = {}

    for w in WINDOWS_30MIN:
        label = w["label"]
        all_window_ticks = []
        daily_data = {}

        for date_str in sorted(dates_seen):
            ticks_in_window = day_window_ticks[date_str].get(label, [])
            if not ticks_in_window:
                continue

            all_window_ticks.extend(ticks_in_window)

            # Per-day stats
            prices = [t["price"] for t in ticks_in_window]
            sizes = [t["size"] for t in ticks_in_window]
            total_vol = sum(sizes)
            vwap = sum(p * s for p, s in zip(prices, sizes)) / total_vol if total_vol > 0 else 0

            daily_data[date_str] = {
                "ticks": len(ticks_in_window),
                "volume": total_vol,
                "vwap": round(vwap, 4),
                "high": round(max(prices), 4),
                "low": round(min(prices), 4),
                "range": round(max(prices) - min(prices), 4),
            }

        if not all_window_ticks:
            windows_analysis[label] = {
                "avg_ticks": 0,
                "avg_volume": 0,
                "vol_adv_ratio": 0,
                "avg_vwap": 0,
                "price_range_avg": 0,
                "direction": "inactive",
                "days_active": 0,
            }
            window_total_ticks[label] = 0
            continue

        # Aggregate across days
        days_active = len(daily_data)
        prices = [t["price"] for t in all_window_ticks]
        sizes = [t["size"] for t in all_window_ticks]
        total_vol = sum(sizes)
        vwap = sum(p * s for p, s in zip(prices, sizes)) / total_vol if total_vol > 0 else 0

        # Direction: compare first-half VWAP vs second-half VWAP
        mid_idx = len(all_window_ticks) // 2
        if mid_idx > 0 and len(all_window_ticks) > mid_idx:
            first_half = all_window_ticks[:mid_idx]
            second_half = all_window_ticks[mid_idx:]

            fh_vol = sum(t["size"] for t in first_half)
            sh_vol = sum(t["size"] for t in second_half)

            fh_vwap = sum(t["price"] * t["size"] for t in first_half) / fh_vol if fh_vol > 0 else 0
            sh_vwap = sum(t["price"] * t["size"] for t in second_half) / sh_vol if sh_vol > 0 else 0

            if sh_vwap > fh_vwap * 1.001:
                direction = "buyer"
            elif sh_vwap < fh_vwap * 0.999:
                direction = "seller"
            else:
                direction = "neutral"
        else:
            direction = "neutral"

        # Price range average per day
        ranges = [d["range"] for d in daily_data.values()]
        avg_range = sum(ranges) / len(ranges) if ranges else 0

        # ═══ SPREAD COMPUTATION ═══
        # Tick-to-tick spread: consecutive price differences
        # This is a proxy for effective spread in the 30-min window
        sorted_ticks = sorted(all_window_ticks, key=lambda x: x["ts"])
        tick_spreads = []
        for i in range(1, len(sorted_ticks)):
            spread = abs(sorted_ticks[i]["price"] - sorted_ticks[i-1]["price"])
            tick_spreads.append(spread)

        avg_spread = sum(tick_spreads) / len(tick_spreads) if tick_spreads else 0
        median_spread = sorted(tick_spreads)[len(tick_spreads)//2] if tick_spreads else 0
        # Spread as % of price — normalizes across different price levels
        avg_price = sum(prices) / len(prices) if prices else 1
        spread_bps = round(avg_spread / avg_price * 10000, 1) if avg_price > 0 else 0  # basis points
        # Spread relative to ADV — liquidity proxy
        # Higher ADV → tighter spread expected; this ratio shows if spread is "fair" for liquidity
        spread_adv_ratio = round(avg_spread / (avg_adv / 100000), 4) if avg_adv > 0 else 0

        windows_analysis[label] = {
            "avg_ticks": round(len(all_window_ticks) / num_days, 1),
            "avg_volume": round(total_vol / num_days, 0),
            "vol_adv_ratio": round(total_vol / (avg_adv * num_days) * 100, 2) if avg_adv > 0 else 0,
            "avg_vwap": round(vwap, 4),
            "price_range_avg": round(avg_range, 4),
            "avg_spread": round(avg_spread, 4),
            "median_spread": round(median_spread, 4),
            "spread_bps": spread_bps,
            "spread_adv_ratio": spread_adv_ratio,
            "direction": direction,
            "days_active": days_active,
            "daily_breakdown": daily_data,
        }
        window_total_ticks[label] = len(all_window_ticks)

    # Overall stats
    total_volume = sum(t["size"] for t in relevant_ticks)

    # Venue mix
    venue_counts = defaultdict(int)
    for t in relevant_ticks:
        venue_counts[t["exch"]] += 1
    total_t = len(relevant_ticks)
    venue_mix = {v: round(c / total_t, 3) for v, c in venue_counts.items()} if total_t > 0 else {}

    # Busiest / quietest
    active_windows = {l: c for l, c in window_total_ticks.items() if c > 0}
    busiest = max(active_windows, key=active_windows.get) if active_windows else None
    quietest = min(active_windows, key=active_windows.get) if active_windows else None

    # ═══ OVERALL SPREAD STATS ═══
    all_sorted = sorted(relevant_ticks, key=lambda x: x["ts"])
    overall_spreads = [abs(all_sorted[i]["price"] - all_sorted[i-1]["price"]) for i in range(1, len(all_sorted))]
    overall_avg_spread = sum(overall_spreads) / len(overall_spreads) if overall_spreads else 0
    overall_median_spread = sorted(overall_spreads)[len(overall_spreads)//2] if overall_spreads else 0
    overall_avg_price = sum(t["price"] for t in relevant_ticks) / len(relevant_ticks) if relevant_ticks else 1
    overall_spread_bps = round(overall_avg_spread / overall_avg_price * 10000, 1) if overall_avg_price > 0 else 0

    # ═══ INTEREST SCORE (COMPOSITE) ═══
    # Factors: volume/ADV, spread opportunity, directionality, MM suitability
    score = 0.0
    if active_windows:
        # 1. Volume concentration: high vol/ADV ratio = interesting
        vol_adv_total = total_volume / (avg_adv * num_days) if avg_adv > 0 else 0
        score += min(vol_adv_total * 2, 3.0)  # max 3 points

        # 2. Price movement: large intraday ranges = mean reversion opportunity
        avg_ranges = [
            w.get("price_range_avg", 0) for w in windows_analysis.values() if w.get("price_range_avg", 0) > 0
        ]
        if avg_ranges:
            avg_range = sum(avg_ranges) / len(avg_ranges)
            score += min(avg_range * 10, 2.5)  # max 2.5 points

        # 3. Spread opportunity for MM: wider spread = more room to capture
        # But not TOO wide (illiquid = dangerous)
        if overall_spread_bps > 5 and overall_spread_bps < 200:
            score += min(overall_spread_bps / 30, 2.0)  # max 2 points

        # 4. Window concentration: activity in specific windows = predictable flow
        if len(active_windows) > 0:
            top_window_pct = max(active_windows.values()) / total_t if total_t > 0 else 0
            if top_window_pct > 0.4:
                score += 1.5
            elif top_window_pct > 0.25:
                score += 0.75

        # 5. Directional bias: consistent direction = mean reversion setup when it fades
        directions = [w.get("direction") for w in windows_analysis.values() if w.get("direction") not in ("inactive", "neutral")]
        if directions:
            buyer_pct = directions.count("buyer") / len(directions)
            seller_pct = directions.count("seller") / len(directions)
            directional_strength = max(buyer_pct, seller_pct)
            if directional_strength > 0.6:
                score += 1.5

    # ═══ MM SUITABILITY SCORE ═══
    # Separate score for market making viability
    mm_score = 0.0
    if overall_spread_bps > 10:  # Need at least 1bp spread to capture
        mm_score += min(overall_spread_bps / 50, 2.0)  # spread width
    if total_t > 20:  # Need enough ticks for two-sided flow
        mm_score += min(total_t / 50, 2.0)  # tick density
    # Balanced buyer/seller = ideal for MM
    all_directions = [w.get("direction") for w in windows_analysis.values() if w.get("direction") not in ("inactive",)]
    if all_directions:
        b_count = all_directions.count("buyer")
        s_count = all_directions.count("seller")
        n_count = all_directions.count("neutral")
        total_dir = len(all_directions)
        if total_dir > 0:
            balance = 1.0 - abs(b_count - s_count) / total_dir
            mm_score += balance * 2.0  # max 2 points
    # Venue diversity is good for MM (can work both lit/dark)
    if len(venue_mix) > 1:
        mm_score += 0.5

    return {
        "symbol": symbol,
        "total_ticks": len(relevant_ticks),
        "days_covered": num_days,
        "avg_adv": avg_adv,
        "windows": windows_analysis,
        "busiest_window": busiest,
        "quietest_window": quietest,
        "total_volume": total_volume,
        "vol_adv_ratio_total": round(total_volume / (avg_adv * num_days) * 100, 2) if avg_adv > 0 else 0,
        "overall_avg_spread": round(overall_avg_spread, 4),
        "overall_median_spread": round(overall_median_spread, 4),
        "overall_spread_bps": overall_spread_bps,
        "venue_mix": venue_mix,
        "interest_score": round(score, 2),
        "mm_score": round(mm_score, 2),
    }


# ═══════════════════════════════════════════════════════════════
# Core: DOS Group Comparison
# ═══════════════════════════════════════════════════════════════

def analyze_dos_groups(
    lookback_days: int = LOOKBACK_DAYS,
    top_n: int = TOP_N_PER_GROUP,
    use_in_memory: bool = True,
    mode: str = MODE_BACKTEST,
) -> Dict[str, Any]:
    """
    Run the full DOS group truth tick analysis.

    Modes:
        - MODE_BACKTEST: Historical analysis. No bid/ask data available.
          Estimates spread from consecutive prints. Walk-forward: each
          window only sees data from that window and before (NO look-ahead).
        - MODE_LIVE: Real-time analysis with L1 bid/ask/last data.
          Bias-free: acts as if 5 minutes from now is unknown.

    Steps:
        1. Load all symbols with DOS groups
        2. Fetch truth ticks (from in-memory engine or Redis)
        3. Analyze each symbol's 30-min windows
        4. Group by DOS group
        5. Compare within group (vol/ADV, direction, activity)
        6. Select top-3 most interesting per group

    Args:
        lookback_days: Number of days to look back
        top_n: Number of top stocks per group
        use_in_memory: If True, try TruthTicksEngine first; else Redis only

    Returns:
        Comprehensive analysis dict
    """
    start_time = time.time()
    logger.info(
        f"[TT-ANALYZER] Starting DOS group analysis "
        f"(mode={mode}, lookback={lookback_days} trading days, top_n={top_n})"
    )

    # 1. Load static data
    symbols_data = get_all_symbols_with_groups()
    if not symbols_data:
        return {"error": "Static data not loaded", "groups": {}}

    logger.info(f"[TT-ANALYZER] Loaded {len(symbols_data)} symbols with groups")

    # 2. Fetch and analyze each symbol
    r = _get_redis_sync()
    symbol_analyses = {}
    fetch_count = 0
    no_data_count = 0

    for symbol, static in symbols_data.items():
        # Unified tick fetch: Hammer API > In-memory > Redis
        ticks = fetch_all_ticks_for_symbol(symbol, r=r)
        if not ticks:
            no_data_count += 1
            continue

        fetch_count += 1
        analysis = analyze_symbol_windows(
            symbol=symbol,
            truth_ticks=ticks,
            avg_adv=static["avg_adv"],
            lookback_days=lookback_days,
        )

        if analysis:
            analysis["group"] = static["group"]
            analysis["fbtot"] = static.get("fbtot")
            analysis["sfstot"] = static.get("sfstot")
            analysis["gort"] = static.get("gort")
            analysis["gort_norm"] = static.get("gort_norm")
            analysis["sma63_chg"] = static.get("sma63_chg")
            analysis["prev_close"] = static.get("prev_close")

            # === LIVE MODE: Enrich with L1 bid/ask data ===
            if mode == MODE_LIVE:
                l1 = _fetch_l1_data_for_symbol(symbol, r)
                if l1 and l1["bid"] > 0 and l1["ask"] > 0:
                    live_spread = l1["ask"] - l1["bid"]
                    live_mid = (l1["ask"] + l1["bid"]) / 2
                    analysis["live_l1"] = {
                        "bid": l1["bid"],
                        "ask": l1["ask"],
                        "last": l1["last"],
                        "bid_size": l1["bid_size"],
                        "ask_size": l1["ask_size"],
                        "live_spread": round(live_spread, 4),
                        "live_spread_bps": round(live_spread / live_mid * 10000, 1) if live_mid > 0 else 0,
                    }
            else:
                # BACKTEST MODE: note that spread is estimated from prints
                analysis["spread_note"] = "estimated_from_prints"

            symbol_analyses[symbol] = analysis

    logger.info(
        f"[TT-ANALYZER] Analyzed {len(symbol_analyses)} symbols "
        f"(fetched={fetch_count}, no_data={no_data_count})"
    )

    # 3. Group by DOS group
    groups = defaultdict(list)
    for symbol, analysis in symbol_analyses.items():
        groups[analysis["group"]].append(analysis)

    # 4. Analyze each group and pick top-N
    group_reports = {}

    for group_name, members in sorted(groups.items()):
        if len(members) < 1:
            continue

        # Sort by interest_score descending
        members.sort(key=lambda x: x.get("interest_score", 0), reverse=True)

        # Group-level aggregates
        total_ticks_group = sum(m["total_ticks"] for m in members)
        active_count = len([m for m in members if m["total_ticks"] > 0])

        # Window-level aggregation across group
        group_window_activity = defaultdict(lambda: {"total_ticks": 0, "total_volume": 0, "buyers": 0, "sellers": 0})

        for m in members:
            for label, w_data in m.get("windows", {}).items():
                if w_data.get("avg_ticks", 0) > 0:
                    group_window_activity[label]["total_ticks"] += w_data["avg_ticks"] * m["days_covered"]
                    group_window_activity[label]["total_volume"] += w_data["avg_volume"] * m["days_covered"]
                    if w_data.get("direction") == "buyer":
                        group_window_activity[label]["buyers"] += 1
                    elif w_data.get("direction") == "seller":
                        group_window_activity[label]["sellers"] += 1

        # Find group's busiest window
        group_busiest = None
        max_vol = 0
        for label, gw in group_window_activity.items():
            if gw["total_volume"] > max_vol:
                max_vol = gw["total_volume"]
                group_busiest = label

        # Group dominant direction
        total_buyers = sum(gw["buyers"] for gw in group_window_activity.values())
        total_sellers = sum(gw["sellers"] for gw in group_window_activity.values())
        if total_buyers > total_sellers * 1.3:
            group_direction = "buyer_dominant"
        elif total_sellers > total_buyers * 1.3:
            group_direction = "seller_dominant"
        else:
            group_direction = "balanced"

        # Top-N interesting stocks (for report)
        top_stocks = []
        for m in members[:top_n]:
            # Compact per-stock summary
            compact_windows = {}
            for label, w_data in m.get("windows", {}).items():
                if w_data.get("avg_ticks", 0) > 0:
                    compact_windows[label] = {
                        "ticks": w_data["avg_ticks"],
                        "vol": w_data["avg_volume"],
                        "vol_adv_pct": w_data["vol_adv_ratio"],
                        "vwap": w_data["avg_vwap"],
                        "range": w_data["price_range_avg"],
                        "spread": w_data.get("avg_spread", 0),
                        "spread_bps": w_data.get("spread_bps", 0),
                        "direction": w_data["direction"],
                    }

            top_stocks.append({
                "symbol": m["symbol"],
                "interest_score": m["interest_score"],
                "mm_score": m.get("mm_score", 0),
                "total_ticks": m["total_ticks"],
                "days_covered": m["days_covered"],
                "vol_adv_total_pct": m["vol_adv_ratio_total"],
                "overall_spread_bps": m.get("overall_spread_bps", 0),
                "busiest_window": m["busiest_window"],
                "venue_mix": m["venue_mix"],
                "fbtot": m.get("fbtot"),          # LT Long score
                "sfstot": m.get("sfstot"),        # LT Short score
                "gort": m.get("gort"),            # Mean reversion position
                "gort_norm": m.get("gort_norm"),  # Normalized 0-100
                "sma63_chg": m.get("sma63_chg"),
                "active_windows": compact_windows,
            })

        group_reports[group_name] = {
            "member_count": len(members),
            "active_count": active_count,
            "total_ticks_group": total_ticks_group,
            "group_busiest_window": group_busiest,
            "group_direction": group_direction,
            "buyer_vs_seller": f"{total_buyers}B / {total_sellers}S",
            "window_summary": {
                label: {
                    "ticks": round(gw["total_ticks"]),
                    "volume": round(gw["total_volume"]),
                    "buyers": gw["buyers"],
                    "sellers": gw["sellers"],
                }
                for label, gw in sorted(group_window_activity.items())
                if gw["total_ticks"] > 0
            },
            "top_stocks": top_stocks,
        }

    elapsed = time.time() - start_time

    return {
        "analysis_time": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "mode": mode,
        "lookback_trading_days": lookback_days,
        "total_symbols_analyzed": len(symbol_analyses),
        "total_groups": len(group_reports),
        "groups": group_reports,
    }


# ═══════════════════════════════════════════════════════════════
# Gemini Prompt Builder
# ═══════════════════════════════════════════════════════════════

TRUTH_TICK_ANALYSIS_PROMPT = """
## TRUTH TICK 30-DAKİKALIK WİNDOW ANALİZİ — MEAN REVERSION & MARKET MAKING

Sen QAGENTT'sin — Preferred Stock Learning Agent.
Aşağıda son {lookback_days} **İŞ GÜNÜ** (trading days) truth tick verilerinin 30 dakikalık periyotlara bölünmüş analizi var.

### 🎯 ANALİZ MODU: {mode}
{mode_context}

### 🔑 SKORLAMA SİSTEMİ:
- **FBtot (FINAL_THG)**: Uzun vadeli LONG uygunluk skoru. Yüksek = güçlü long adayı
- **SFStot (SHORT_FINAL)**: Uzun vadeli SHORT uygunluk skoru. Yüksek = güçlü short adayı
- **GORT**: Mean reversion pozisyonu. 0 = ortalamada, + = ortamanın üstü, - = altı
- **GORT_NORM**: Normalize GORT (0-100, 50 = ortalama)

### 🔑 TEMEL FELSEFEMİZ:
Bu hisseler **MEAN REVERSION hisseleri**. Yakın vadede olmasa bile orta-uzun vadede kendi
DOS grubundaki ortalamaya (GORT) geri dönerler. Bu varsayımla:
- **Aşağı düştükçe yavaş yavaş mal ekliyoruz** (LT Portfolio — accumulation)
- **Yukarı geldikçe short açıyoruz** (mean reversion short)
- Her hisse kendi DOS grubu ile mean reversion içerisine girer diye varsayıyoruz
- GORT (SMA246 chg) bu nedenle çok önemli — mean reversion anchor

### 📊 SPREAD ↔ LİKİDİTE İLİŞKİSİ:
- Bir hissede 0.30¢ spread ile işlem görürken, başka bir hissede 0.02¢ spread olabilir
- Bu BÜYÜK OLASLIKLA **AVG_ADV (likidite)** ile ilgili
- Spread'ler AVG_ADV'ye göre normalize edildi (spread_bps ve spread_adv_ratio olarak)
- Düşük ADV → geniş spread → MM fırsatı AMA risk de yüksek
- Yüksek ADV → dar spread → güvenli ama marj düşük

### İKİ STRATEJİ:
1. **LT Portfolio (Long-Term Mean Reversion):**
   - Grup ortalamasının altında kalan hisseleri yavaş yavaş topla
   - GORT'a (SMA246) göre ne kadar uzakta olduğunu ölç
   - Exposure kontrolü — aşırı yüklenmeden, dollar cost averaging mantığı

2. **Mini Market Making (Spread Capture):**
   - Yeterli hacim olan hisselerde bid/ask spread'inden para kazan
   - Likiditeye göre lot büyüklüğü ayarla (avg_adv / 100 gibi)
   - İki yönlü akış olan saatleri hedefle
   - Venue stratejisi: NYSE (lit orders) vs FNRA (dark pool) farkını kullan

### Genel Bilgi:
- Analiz edilen toplam hisse: {total_symbols}
- DOS grup sayısı: {total_groups}
- Analiz zamanı: {analysis_time}

### DOS Grup Verisi:
{group_data}

### GÖREV:
Yukarıdaki verileri inceleyerek şu soruları yanıtla:

1. **Grup Bazında Mean Reversion Durumu**: Her DOS grubunda:
   - Grubun genel yönü ne? (tüm grup alıcı mı satıcı mı?)
   - Hangi hisseler GORT'tan çok uzaklaşmış? (reversion fırsatı)
   - Grup içi korelasyon ne kadar güçlü? (beraber mi hareket ediyorlar?)

2. **Spread & Likidite Analizi**: Her hisse/grup için:
   - Spread kaç bps? Bu AVG_ADV'ye göre makul mü?
   - Spread hangi saatlerde daralıyor (MM fırsatı azalır ama güvenli)
   - Spread hangi saatlerde genişliyor (MM fırsatı var ama risk de var)
   - Volume/ADV oranı spread'i nasıl etkiliyor?

3. **LT Portfolio Önerileri**: Mean reversion mantığıyla:
   - Hangi hisseler aşağı geldikçe toplanmalı? (GORT altı, buyer sinyalleri)
   - Hangi hisseler yukarıdayken short açılmalı? (GORT üstü, seller dominant)
   - Hangi hisselerde pozisyon büyüklüğü ne olmalı? (AVG_ADV'ye göre)
   - Optimal accumulation saatleri? (en ucuz alım saati)

4. **Mini Market Making Modeli**: İstatistiksel olarak:
   - Hangi hisselerde spread capture fırsatı en yüksek? (mm_score'a bak)
   - Her hisse için önerilen lot büyüklüğü? (avg_adv tabanlı)
   - Hangi 30dk periyotlarda iki yönlü akış var? (buyer+seller balanced)
   - Venue stratejisi: FNRA'da mı NYSE'de mi quote etmek daha avantajlı?
   - Risk yönetimi: max exposure per stock, max per group?

5. **İstatistiksel İlişkiler**:
   - Aynı DOS grubundaki hisseler gerçekten beraber mi hareket ediyor?
   - Spread ile ADV arasındaki korelasyon ne kadar güçlü?
   - Hangi gruplarda mean reversion daha hızlı gerçekleşiyor?
   - Saatlik pattern'ler tutarlı mı (her gün aynı saatte mi alıcı geliyor?)

### ÇIKTI FORMATI (JSON):
```json
{{
    "grup_gozlemleri": {{
        "<grup_adi>": {{
            "genel_yorum": "...",
            "mean_reversion_durumu": "fırsat_var/nötr/aşırı_uzaklaşmış",
            "dominant_yön": "buyer/seller/balanced",
            "aktif_saatler": ["09:30-10:00", "15:30-16:00"],
            "ortalama_spread_bps": 0,
            "öne_çıkan_hisseler": ["SYM1", "SYM2", "SYM3"],
            "mm_uygunluk": "yüksek/orta/düşük",
            "grup_korelasyon": "güçlü/orta/zayıf"
        }}
    }},
    "lt_portfolio": {{
        "accumulation_listesi": [
            {{
                "symbol": "...",
                "neden": "GORT altında, buyer geliyor, spread makul",
                "gort_uzaklik_pct": -2.5,
                "önerilen_lot": 100,
                "optimal_alim_saati": "10:00-10:30",
                "güven": 0.0-1.0
            }}
        ],
        "short_listesi": [
            {{
                "symbol": "...",
                "neden": "GORT üstünde, seller dominant, mean revert edecek",
                "gort_uzaklik_pct": 3.1,
                "önerilen_lot": 50,
                "güven": 0.0-1.0
            }}
        ]
    }},
    "mm_model": {{
        "uygun_hisseler": [
            {{
                "symbol": "...",
                "mm_score": 0.0,
                "spread_bps": 0,
                "önerilen_lot": 0,
                "aktif_periyot": "...",
                "iki_yönlü_akış": true,
                "venue_strateji": "NYSE lit preferred / FNRA dark capture",
                "max_exposure": "$X veya Y lot",
                "beklenen_günlük_pnl": "$X (spread * lot * turnover)"
            }}
        ],
        "risk_yönetimi": {{
            "max_per_stock": "...",
            "max_per_group": "...",
            "stop_loss_mantığı": "..."
        }},
        "genel_strateji": "..."
    }},
    "spread_likidite_analizi": {{
        "spread_adv_korelasyon": "güçlü/orta/zayıf",
        "en_dar_spread_grubu": "...",
        "en_geniş_spread_grubu": "...",
        "spread_saatlik_pattern": "sabah geniş→öğlen daralır→kapanış genişler"
    }},
    "istatistiksel_iliskiler": {{
        "grup_ici_korelasyon": "...",
        "mean_reversion_hizi": "...",
        "korelasyon_notları": ["..."]
    }},
    "öğrendiklerim": ["...", "..."],
    "sorularım": ["...", "..."]
}}
```
"""


def build_analysis_prompt(analysis_result: Dict[str, Any]) -> str:
    """
    Build a Gemini-ready prompt from the analysis result.
    Optimized for token efficiency — sends compact group/stock summaries
    without per-window breakdowns (those can be explored separately).
    """
    group_data_lines = []

    for group_name, group in analysis_result.get("groups", {}).items():
        group_data_lines.append(f"\n#### {group_name}")
        group_data_lines.append(
            f"  {group['active_count']}/{group['member_count']} aktif, "
            f"ticks={group['total_ticks_group']}, "
            f"yön={group['group_direction']} ({group['buyer_vs_seller']}), "
            f"yoğun={group['group_busiest_window']}"
        )

        if group.get("top_stocks"):
            for stock in group["top_stocks"]:
                # Compact one-liner per stock
                gort_str = f"GORT={stock.get('gort')}" if stock.get('gort') is not None else "GORT=N/A"
                group_data_lines.append(
                    f"  {stock['symbol']:12s} "
                    f"int={stock['interest_score']:.1f} mm={stock.get('mm_score',0):.1f} "
                    f"ticks={stock['total_ticks']} "
                    f"vol/ADV={stock['vol_adv_total_pct']:.0f}% "
                    f"sprd={stock.get('overall_spread_bps',0):.0f}bps "
                    f"FBtot={stock.get('fbtot','N/A')} "
                    f"SFStot={stock.get('sfstot','N/A')} "
                    f"{gort_str} "
                    f"SMA63={stock.get('sma63_chg','N/A')} "
                    f"peak={stock['busiest_window']}"
                )


    # Determine mode context for prompt
    if analysis_result.get("mode") == MODE_LIVE:
        mode_label = "LIVE (Canlı)"
        mode_context = (
            "Canlı analiz modu. Bid/ask/last verileri mevcut. "
            "\n⚠️ KRİTİK: 5 dakika sonrasının fiyatını BİLMİYORSUN. "
            "Bias-free hareket et. Sadece mevcut verilere dayanarak karar ver."
        )
    else:
        mode_label = "BACKTEST (Geriye Dönük)"
        mode_context = (
            "Geriye dönük analiz modu. Bid/ask verileri YOK — spread, printlerden tahmin ediliyor. "
            "\n🎯 AMAÇ: Pattern'ı öğren, mantığı anla, kendini eğit. "
            "Her 30dk window'ı sadece o ana kadar görülebilir verilerle değerlendir (no look-ahead)."
        )

    group_data = "\n".join(group_data_lines)

    return TRUTH_TICK_ANALYSIS_PROMPT.format(
        lookback_days=analysis_result.get("lookback_trading_days", LOOKBACK_DAYS),
        total_symbols=analysis_result.get("total_symbols_analyzed", 0),
        total_groups=analysis_result.get("total_groups", 0),
        analysis_time=analysis_result.get("analysis_time", ""),
        mode=mode_label,
        mode_context=mode_context,
        group_data=group_data,
    )


# ═══════════════════════════════════════════════════════════════
# Integration: Run full pipeline
# ═══════════════════════════════════════════════════════════════

async def run_truth_tick_deep_analysis(
    lookback_days: int = LOOKBACK_DAYS,
    top_n: int = TOP_N_PER_GROUP,
    mode: str = MODE_BACKTEST,
) -> Dict[str, Any]:
    """
    Run the full truth tick analysis pipeline:
    1. Collect data (respecting TRADING DAYS, not calendar days)
    2. Analyze 30-min windows (bias-free: no look-ahead)
    3. Compare DOS groups with FBtot/SFStot/GORT scoring
    4. Send to Gemini for interpretation
    5. Return structured result

    Modes:
        - backtest: Historical. Estimates spread from prints. Agent trains on patterns.
        - live: Real-time with L1 data. Agent must NOT predict 5 min ahead.

    Returns:
        {"raw_analysis": ..., "gemini_interpretation": ..., "prompt": ..., "mode": ...}
    """
    import os

    logger.info(
        f"[TT-ANALYZER] 🔬 Starting deep truth tick analysis "
        f"(mode={mode}, lookback={lookback_days} trading days)..."
    )

    # Step 1: Run analysis
    raw_analysis = analyze_dos_groups(
        lookback_days=lookback_days,
        top_n=top_n,
        mode=mode,
    )

    if raw_analysis.get("error"):
        return {"error": raw_analysis["error"]}

    # Step 2: Build prompt
    prompt = build_analysis_prompt(raw_analysis)

    # Step 3: Send to AI (Gemini → Claude Haiku fallback)
    ai_response = None
    ai_provider = "none"
    try:
        from app.agent.learning_agent_brain import LEARNING_AGENT_SYSTEM_PROMPT

        # Try Gemini first
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            r = _get_redis_sync()
            if r:
                key = r.get("psfalgo:agent:gemini_api_key")
                if key:
                    api_key = key.decode("utf-8") if isinstance(key, bytes) else key

        if api_key:
            try:
                from app.agent.gemini_client import GeminiFlashClient
                client = GeminiFlashClient(api_key)
                ai_response = await client.analyze(
                    prompt=prompt,
                    system_prompt=LEARNING_AGENT_SYSTEM_PROMPT,
                    temperature=0.35,
                    max_tokens=8192,
                )
                # Check for quota error
                if ai_response and "[GEMINI ERROR]" in ai_response and ("429" in ai_response or "RESOURCE_EXHAUSTED" in ai_response):
                    logger.warning("[TT-ANALYZER] 🔄 Gemini quota exhausted — trying Claude Haiku")
                    ai_response = None  # Fall through to Claude
                else:
                    ai_provider = "gemini"
                    logger.info("[TT-ANALYZER] ✅ Gemini interpretation complete")
            except Exception as e:
                logger.warning(f"[TT-ANALYZER] Gemini error: {e} — trying Claude Haiku")

        # Fallback: Claude Haiku
        if not ai_response or (ai_response and "[GEMINI ERROR]" in ai_response):
            claude_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not claude_key:
                r2 = _get_redis_sync()
                if r2:
                    ck = r2.get("psfalgo:agent:claude_api_key")
                    if ck:
                        claude_key = ck.decode("utf-8") if isinstance(ck, bytes) else ck
            
            if claude_key:
                try:
                    from app.agent.claude_client import ClaudeClient, MODEL_HAIKU
                    claude_client = ClaudeClient(api_key=claude_key, model=MODEL_HAIKU)
                    ai_response = await claude_client.analyze(
                        prompt=prompt,
                        system_prompt=LEARNING_AGENT_SYSTEM_PROMPT,
                        temperature=0.35,
                        max_tokens=8192,
                    )
                    ai_provider = "claude_haiku"
                    logger.info("[TT-ANALYZER] ✅ Claude Haiku interpretation complete")
                except Exception as e:
                    logger.error(f"[TT-ANALYZER] Claude error: {e}")
                    ai_response = f"[ERROR] Claude: {e}"
            else:
                logger.warning("[TT-ANALYZER] No AI API key available — skipping interpretation")

    except Exception as e:
        logger.error(f"[TT-ANALYZER] AI provider error: {e}")
        ai_response = f"[ERROR] {e}"

    # Step 4: Save to Redis
    result = {
        "raw_analysis": raw_analysis,
        "gemini_interpretation": ai_response,  # backward compat key name
        "ai_provider": ai_provider,
        "prompt_length": len(prompt),
        "timestamp": datetime.now().isoformat(),
    }

    try:
        r = _get_redis_sync()
        if r:
            r.setex(
                "qagentt:truth_tick_analysis",
                7200,  # 2 hour TTL
                json.dumps({
                    "raw_stats": {
                        "total_symbols": raw_analysis.get("total_symbols_analyzed"),
                        "total_groups": raw_analysis.get("total_groups"),
                        "elapsed": raw_analysis.get("elapsed_seconds"),
                    },
                    "ai_report": ai_response,
                    "ai_provider": ai_provider,
                    "timestamp": result["timestamp"],
                }, ensure_ascii=False),
            )
    except Exception:
        pass

    return result

