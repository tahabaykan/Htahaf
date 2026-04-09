# -*- coding: utf-8 -*-
"""
app/market_data/truth_shift_v2_engine.py

Truth Shift Score v2 Engine — Production
Multi-dimensional buyer/seller pressure analysis using truth ticks.

Score: 0 = Max Bearish | 50 = Neutral | 100 = Max Bullish

4 Dimensions:
  1. Volume Direction  (40%) — Which side has more volume?
  2. Displacement Depth (25%) — How many cents up/down, weighted by volume?
  3. Frequency Pressure (15%) — How often are buys vs sells hitting?
  4. VWAP Momentum     (20%) — Is VWAP drifting up or down over time?

Multiplied by ADV Significance (0.5–1.5x) based on truth_volume / ADV ratio.

Rolling Windows: 5m, 15m, 1h, 4h, FULL_DAY
Update Interval: Every 5 minutes (configurable)
"""

import json
import time
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict
from statistics import median

from app.core.logger import logger


# ════════════════════════════════════════════════════════════════════
# ROLLING WINDOWS (in seconds)
# ════════════════════════════════════════════════════════════════════
ROLLING_WINDOWS = {
    'W_5M':       5 * 60,       # 5 minutes
    'W_15M':      15 * 60,      # 15 minutes
    'W_1H':       60 * 60,      # 1 hour
    'W_4H':       4 * 60 * 60,  # 4 hours
    'W_FULL_DAY': 0,            # Special: all ticks from market open today
}

# Scoring weights
W_VOL_DIR = 0.40
W_DISP    = 0.25
W_FREQ    = 0.15
W_VWAP    = 0.20

# VWAP drift normalization: ±0.3% = fully bull/bear for illiquid preferreds
MAX_VWAP_DRIFT_PCT = 0.30

# ET timezone offset from UTC (EST = -5, EDT = -4)
# March 2026: DST starts March 8 → EDT = UTC-4
ET_OFFSET_HOURS = -4

# Minimum ticks required per window
MIN_TICKS_PER_WINDOW = 3

# ═══ TEMPORAL DECAY ═══
# Recent ticks have MORE influence than older ticks.
# weight = DECAY_FLOOR + (1 - DECAY_FLOOR) × (time_progress ^ DECAY_POWER)
#   time_progress = 0.0 for oldest tick, 1.0 for newest tick
#   DECAY_FLOOR = 0.3 → oldest tick still has 30% influence
#   DECAY_POWER = 1.5 → moderate bias toward recent (not too aggressive)
#
# Example (1h window):
#   Tick at -60min → progress=0.0 → weight=0.30
#   Tick at -30min → progress=0.5 → weight=0.55  
#   Tick at -10min → progress=0.83 → weight=0.83
#   Tick at -1min  → progress=0.98 → weight=0.99
DECAY_FLOOR = 0.30
DECAY_POWER = 1.5

# ════════════════════════════════════════════════════════════════════
# CORE METRIC COMPUTATION
# ════════════════════════════════════════════════════════════════════

def _calc_time_weight(ts: float, window_start: float, window_end: float) -> float:
    """
    Calculate temporal decay weight for a tick.
    
    Recent ticks have MORE influence. Oldest tick in window gets DECAY_FLOOR (0.3),
    newest tick gets ~1.0. Power curve gives moderate recency bias.
    
    Args:
        ts: Tick timestamp
        window_start: Earliest tick timestamp in window
        window_end: Latest tick timestamp in window (≈ now)
    """
    span = window_end - window_start
    if span <= 0:
        return 1.0
    progress = (ts - window_start) / span  # 0.0 = oldest, 1.0 = newest
    progress = max(0.0, min(1.0, progress))
    return DECAY_FLOOR + (1.0 - DECAY_FLOOR) * (progress ** DECAY_POWER)


def compute_window_metrics(ticks: List[Dict]) -> Optional[Dict[str, Any]]:
    """
    Compute all v2 raw metrics for a list of ticks in a window.
    ALL metrics are time-decay weighted: recent ticks have more influence.
    
    Each tick: {'ts': float, 'price': float, 'size': float, 'exch': str}
    
    Returns dict with volume, displacement, frequency, vwap metrics or None.
    """
    if len(ticks) < MIN_TICKS_PER_WINDOW:
        return None
    
    # Time window boundaries
    window_start = ticks[0]['ts']
    window_end = ticks[-1]['ts']
    
    # ═══ RAW (unweighted) counters — for reporting ═══
    up_vol = 0; down_vol = 0; flat_vol = 0
    up_count = 0; down_count = 0; flat_count = 0
    total_up_cents = 0.0; total_down_cents = 0.0
    max_up_cents = 0.0; max_down_cents = 0.0
    
    # ═══ TIME-WEIGHTED counters — for scoring ═══
    tw_up_vol = 0.0; tw_down_vol = 0.0; tw_flat_vol = 0.0
    tw_up_disp = 0.0; tw_down_disp = 0.0
    tw_up_count = 0.0; tw_down_count = 0.0
    
    # First tick is reference — count as flat
    w0 = _calc_time_weight(ticks[0]['ts'], window_start, window_end)
    flat_vol += int(ticks[0]['size'])
    flat_count += 1
    tw_flat_vol += int(ticks[0]['size']) * w0
    
    for i in range(1, len(ticks)):
        prev_p = ticks[i-1]['price']
        curr_p = ticks[i]['price']
        size = int(ticks[i]['size'])
        delta = curr_p - prev_p
        disp = abs(delta)
        tw = _calc_time_weight(ticks[i]['ts'], window_start, window_end)
        
        if delta > 0.0001:  # UP
            up_vol += size
            up_count += 1
            total_up_cents += disp
            max_up_cents = max(max_up_cents, disp)
            tw_up_vol += size * tw
            tw_up_disp += size * disp * tw
            tw_up_count += tw
        elif delta < -0.0001:  # DOWN
            down_vol += size
            down_count += 1
            total_down_cents += disp
            max_down_cents = max(max_down_cents, disp)
            tw_down_vol += size * tw
            tw_down_disp += size * disp * tw
            tw_down_count += tw
        else:  # FLAT
            flat_vol += size
            flat_count += 1
            tw_flat_vol += size * tw
    
    total_vol = up_vol + down_vol + flat_vol
    
    # Time span
    span_sec = max(window_end - window_start, 1)
    span_min = span_sec / 60
    
    # ═══ TIME-WEIGHTED frequency (recent ticks count more per minute) ═══
    tw_up_freq = tw_up_count / max(span_min, 1)
    tw_down_freq = tw_down_count / max(span_min, 1)
    
    # ═══ VWAP drift (first quartile vs last quartile) — inherently time-aware ═══
    n = len(ticks)
    q = max(n // 4, 1)
    first_q = ticks[:q]
    last_q = ticks[-q:]
    
    vwap_first = (sum(t['price'] * t['size'] for t in first_q) /
                  max(sum(t['size'] for t in first_q), 1))
    vwap_last = (sum(t['price'] * t['size'] for t in last_q) /
                 max(sum(t['size'] for t in last_q), 1))
    vwap_drift_pct = (vwap_last - vwap_first) / max(vwap_first, 0.01) * 100
    
    # ═══ RECENCY: how fresh is this symbol's data? ═══
    # Seconds since last tick — for cross-symbol comparison
    now = time.time()
    seconds_since_last_tick = now - window_end
    
    return {
        # Raw (for display)
        'up_vol': up_vol, 'down_vol': down_vol, 'flat_vol': flat_vol,
        'total_vol': total_vol,
        'up_count': up_count, 'down_count': down_count, 'flat_count': flat_count,
        'total_ticks': len(ticks),
        'total_up_cents': round(total_up_cents, 4),
        'total_down_cents': round(total_down_cents, 4),
        'avg_up_cents': round(total_up_cents / max(up_count, 1), 4),
        'avg_down_cents': round(total_down_cents / max(down_count, 1), 4),
        'max_up_cents': round(max_up_cents, 4),
        'max_down_cents': round(max_down_cents, 4),
        # Time-weighted (for scoring)
        'tw_up_vol': tw_up_vol, 'tw_down_vol': tw_down_vol, 'tw_flat_vol': tw_flat_vol,
        'tw_up_disp': tw_up_disp, 'tw_down_disp': tw_down_disp,
        'tw_up_freq': round(tw_up_freq, 3), 'tw_down_freq': round(tw_down_freq, 3),
        # Frequency (raw, for display)
        'up_freq': round(up_count / max(span_min, 1), 3),
        'down_freq': round(down_count / max(span_min, 1), 3),
        'span_min': round(span_min, 1),
        # VWAP
        'vwap_first': round(vwap_first, 4),
        'vwap_last': round(vwap_last, 4),
        'vwap_drift_pct': round(vwap_drift_pct, 4),
        # Price range
        'price_start': ticks[0]['price'],
        'price_end': ticks[-1]['price'],
        'price_high': max(t['price'] for t in ticks),
        'price_low': min(t['price'] for t in ticks),
        # Recency
        'seconds_since_last_tick': round(seconds_since_last_tick, 0),
        'last_tick_ts': window_end,
    }


def calc_tss_v2(m: Dict, adv: float) -> Optional[Dict[str, Any]]:
    """
    Calculate TSS v2 score (0-100 scale).
    50 = neutral, 100 = max bullish, 0 = max bearish.
    
    Uses TIME-WEIGHTED metrics so recent prints have more influence.
    Also applies a recency penalty: if last tick was >30min ago,
    the score gets dampened toward neutral (stale data is unreliable).
    
    Returns dict with tss, component scores, and adv info.
    """
    if m is None:
        return None
    
    # ── Dim 1: Volume Direction (-1 to +1) — TIME-WEIGHTED ──
    ABSORPTION = 0.5
    tw_eff_total = m['tw_up_vol'] + m['tw_down_vol'] + m['tw_flat_vol'] * ABSORPTION
    vol_dir = (m['tw_up_vol'] - m['tw_down_vol']) / tw_eff_total if tw_eff_total > 0 else 0
    
    # ── Dim 2: Displacement Depth (-1 to +1) — TIME-WEIGHTED ──
    tw_total_disp = m['tw_up_disp'] + m['tw_down_disp']
    disp_depth = (m['tw_up_disp'] - m['tw_down_disp']) / tw_total_disp if tw_total_disp > 0 else 0
    
    # ── Dim 3: Frequency Pressure (-1 to +1) — TIME-WEIGHTED ──
    tw_total_freq = m['tw_up_freq'] + m['tw_down_freq']
    freq_press = (m['tw_up_freq'] - m['tw_down_freq']) / tw_total_freq if tw_total_freq > 0 else 0
    
    # ── Dim 4: VWAP Momentum (-1 to +1) — inherently time-aware ──
    vwap_mom = max(-1, min(1, m['vwap_drift_pct'] / MAX_VWAP_DRIFT_PCT))
    
    # ── ADV Significance (0.5 to 1.5) ──
    if adv and adv > 0:
        ratio = m['total_vol'] / adv * 100
        if ratio < 0.5:
            adv_sig = 0.5
        elif ratio < 2:
            adv_sig = 0.75
        elif ratio < 5:
            adv_sig = 1.0
        elif ratio < 10:
            adv_sig = 1.2
        else:
            adv_sig = 1.5
    else:
        adv_sig = 0.75  # unknown ADV = conservative
    
    # ── RECENCY PENALTY ──
    # If last truth tick is stale (>30min ago), dampen score toward 50 (neutral).
    # This prevents a stock that printed bearish 1.5h ago from still showing
    # strong bearish while other stocks have fresh prints.
    #   <5min  → 1.0  (full signal)
    #   5-15min → 0.9
    #   15-30min → 0.75
    #   30-60min → 0.5
    #   >60min → 0.3  (heavy dampening)
    stale_sec = m.get('seconds_since_last_tick', 0)
    if stale_sec < 300:          # <5 min
        recency_factor = 1.0
    elif stale_sec < 900:        # 5-15 min
        recency_factor = 0.9
    elif stale_sec < 1800:       # 15-30 min
        recency_factor = 0.75
    elif stale_sec < 3600:       # 30-60 min
        recency_factor = 0.5
    else:                         # >60 min
        recency_factor = 0.3
    
    # ── Composite (-1 to +1 range, then scale to 0-100) ──
    raw = (vol_dir * W_VOL_DIR + disp_depth * W_DISP +
           freq_press * W_FREQ + vwap_mom * W_VWAP)
    
    # Apply ADV significance (amplifies or dampens)
    raw_scaled = raw * adv_sig
    
    # Apply recency penalty (pulls toward 0 = neutral on -1 to +1 scale)
    raw_recency = raw_scaled * recency_factor
    
    raw_clamped = max(-1.0, min(1.0, raw_recency))
    score = round((raw_clamped + 1) * 50, 1)
    
    return {
        'tss': score,
        'vol_dir': round((vol_dir + 1) * 50, 1),
        'disp_depth': round((disp_depth + 1) * 50, 1),
        'freq_press': round((freq_press + 1) * 50, 1),
        'vwap_mom': round((vwap_mom + 1) * 50, 1),
        'adv_sig': round(adv_sig, 2),
        'adv_pct': round(m['total_vol'] / max(adv, 1) * 100, 2) if adv else 0,
        'recency_factor': round(recency_factor, 2),
        'stale_seconds': round(stale_sec, 0),
        'total_vol': m['total_vol'],
        'total_ticks': m['total_ticks'],
        'span_min': m['span_min'],
    }


# ════════════════════════════════════════════════════════════════════
# TRUTH SHIFT v2 ENGINE
# ════════════════════════════════════════════════════════════════════

class TruthShiftV2Engine:
    """
    Production Truth Shift Score v2 Engine.
    
    Reads truth ticks from Redis (tt:ticks:{symbol}), computes multi-dimensional
    TSS v2 scores for each symbol in rolling windows, normalizes within groups,
    and publishes results back to Redis.
    
    Update interval: every 5 minutes.
    """
    
    def __init__(self, redis_client, static_store=None, compute_interval: float = 300.0):
        """
        Args:
            redis_client: Redis sync client
            static_store: StaticDataStore instance (for ADV, group data)
            compute_interval: Seconds between compute cycles (default: 300 = 5min)
        """
        self.redis = redis_client
        self.static_store = static_store
        self.compute_interval = compute_interval
        
        # Caches
        self._adv_cache: Dict[str, float] = {}         # symbol -> ADV
        self._group_cache: Dict[str, str] = {}          # symbol -> group name
        self._group_members: Dict[str, List[str]] = {}  # group -> [symbols]
        
        # Results
        self._symbol_scores: Dict[str, Dict] = {}       # symbol -> {window -> scores}
        self._group_scores: Dict[str, Dict] = {}        # group -> {window -> scores}
        self._market_scores: Dict[str, Dict] = {}       # window -> market scores
        
        # Threading
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Metrics
        self._last_compute_time = 0
        self._compute_count = 0
        self._last_symbol_count = 0
        
        logger.info("[TSS-V2] Engine initialized")
    
    def start(self):
        """Start the compute loop thread."""
        if self._running:
            return
        
        self._load_static_data()
        self._running = True
        self._thread = threading.Thread(target=self._compute_loop, daemon=True, name="tss_v2_engine")
        self._thread.start()
        logger.info(f"[TSS-V2] 🚀 Engine started (interval: {self.compute_interval}s, "
                    f"{len(self._adv_cache)} symbols, {len(self._group_members)} groups)")
    
    def stop(self):
        """Stop the compute loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("[TSS-V2] Engine stopped")
    
    def _load_static_data(self):
        """Load ADV and group mappings from static store."""
        try:
            if not self.static_store:
                from app.market_data.static_data_store import get_static_store
                self.static_store = get_static_store()
            
            if not self.static_store or not self.static_store.is_loaded():
                logger.warning("[TSS-V2] Static store not loaded")
                return
            
            # Load ADV
            for sym, data in self.static_store.data.items():
                sym = sym.strip()
                adv = data.get('AVG_ADV', 0)
                try:
                    self._adv_cache[sym] = float(adv) if adv else 0
                except (ValueError, TypeError):
                    self._adv_cache[sym] = 0
            
            # Load groups
            try:
                from app.market_data.grouping import get_all_group_keys
                groups = get_all_group_keys(self.static_store)
                self._group_members = {}
                self._group_cache = {}
                for grp, members in groups.items():
                    self._group_members[grp] = list(members)
                    for sym in members:
                        self._group_cache[sym] = grp
            except Exception as e:
                logger.warning(f"[TSS-V2] Group loading failed: {e}")
            
            logger.info(f"[TSS-V2] Loaded {len(self._adv_cache)} ADV values, "
                        f"{len(self._group_members)} groups")
        except Exception as e:
            logger.error(f"[TSS-V2] Static data load error: {e}", exc_info=True)
    
    def _compute_loop(self):
        """Main compute loop — runs every compute_interval seconds."""
        # Initial delay to let truth tick workers start collecting
        time.sleep(30)
        
        while self._running:
            try:
                t0 = time.time()
                self._run_compute_cycle()
                elapsed = time.time() - t0
                
                self._compute_count += 1
                self._last_compute_time = time.time()
                
                # Log TSS dashboard EVERY cycle (5 min)
                self._log_dashboard(elapsed)
                
                # Sleep remaining time
                sleep_time = max(1, self.compute_interval - elapsed)
                time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"[TSS-V2] Compute loop error: {e}", exc_info=True)
                time.sleep(30)
    
    def _run_compute_cycle(self):
        """Single compute cycle: read ticks → compute scores → write to Redis."""
        # Step 1: Load today's ticks from Redis
        symbol_ticks = self._load_today_ticks()
        if not symbol_ticks:
            return
        
        self._last_symbol_count = len(symbol_ticks)
        
        # Step 2: Compute per-symbol scores for each window
        symbol_scores = {}
        now = time.time()
        
        for sym, ticks in symbol_ticks.items():
            adv = self._adv_cache.get(sym, 0)
            sym_result = {}
            
            for wname, window_sec in ROLLING_WINDOWS.items():
                if window_sec > 0:
                    # Rolling window: last N seconds
                    cutoff = now - window_sec
                    w_ticks = [t for t in ticks if t['ts'] >= cutoff]
                else:
                    # FULL_DAY: all today's ticks
                    w_ticks = ticks
                
                if len(w_ticks) < MIN_TICKS_PER_WINDOW:
                    continue
                
                metrics = compute_window_metrics(w_ticks)
                scores = calc_tss_v2(metrics, adv)
                if scores:
                    scores['metrics'] = metrics
                    sym_result[wname] = scores
            
            if sym_result:
                symbol_scores[sym] = sym_result
        
        # Step 3: Compute group scores
        group_scores = {}
        for grp, members in self._group_members.items():
            grp_result = {}
            
            for wname in ROLLING_WINDOWS:
                window_tss = []
                for sym in members:
                    if sym in symbol_scores and wname in symbol_scores[sym]:
                        window_tss.append((sym, symbol_scores[sym][wname]['tss']))
                
                if not window_tss:
                    continue
                
                scores_only = [s for _, s in window_tss]
                grp_tss = round(median(scores_only), 1)
                
                # RTS: each member vs group median
                ranked = sorted(window_tss, key=lambda x: -x[1])
                members_rts = []
                for sym, tss in ranked:
                    rts = round(tss - grp_tss, 1)
                    members_rts.append({'sym': sym, 'tss': tss, 'rts': rts})
                
                grp_result[wname] = {
                    'tss': grp_tss,
                    'member_count': len(window_tss),
                    'total_members': len(members),
                    'ranked': members_rts,
                    'top_3': members_rts[:3],
                    'bottom_3': members_rts[-3:] if len(members_rts) > 3 else members_rts,
                }
            
            if grp_result:
                group_scores[grp] = grp_result
        
        # Step 4: Compute market-wide score
        market_scores = {}
        for wname in ROLLING_WINDOWS:
            all_sym_tss = []
            all_grp_tss = []
            
            for sym, sdata in symbol_scores.items():
                if wname in sdata:
                    all_sym_tss.append(sdata[wname]['tss'])
            
            for grp, gdata in group_scores.items():
                if wname in gdata:
                    all_grp_tss.append((grp, gdata[wname]['tss']))
            
            if all_sym_tss:
                grp_sorted = sorted(all_grp_tss, key=lambda x: -x[1])
                market_scores[wname] = {
                    'tss': round(median(all_sym_tss), 1),
                    'mean': round(sum(all_sym_tss) / len(all_sym_tss), 1),
                    'symbol_count': len(all_sym_tss),
                    'group_count': len(all_grp_tss),
                    'top_group': {'name': grp_sorted[0][0], 'tss': grp_sorted[0][1]} if grp_sorted else None,
                    'bottom_group': {'name': grp_sorted[-1][0], 'tss': grp_sorted[-1][1]} if grp_sorted else None,
                    'groups_ranked': [{'name': g, 'tss': t} for g, t in grp_sorted],
                }
        
        # Step 5: Store results
        with self._lock:
            self._symbol_scores = symbol_scores
            self._group_scores = group_scores
            self._market_scores = market_scores
        
        # Step 6: Persist to Redis
        self._persist_to_redis(symbol_scores, group_scores, market_scores)
    
    def _tss_emoji(self, score):
        if score >= 70: return "🟢🟢"
        if score >= 55: return "🟢"
        if score >= 45: return "↔️"
        if score >= 30: return "🔴"
        return "🔴🔴"
    
    def _tss_label(self, score):
        if score >= 75: return "STRONG BUY"
        if score >= 60: return "Bullish"
        if score >= 55: return "Slight Bull"
        if score >= 45: return "Neutral"
        if score >= 40: return "Slight Bear"
        if score >= 25: return "Bearish"
        return "STRONG SELL"
    
    def _log_dashboard(self, elapsed: float):
        """Log formatted TSS v2 dashboard every compute cycle."""
        try:
            with self._lock:
                ss = self._symbol_scores
                gs = self._group_scores
                ms = self._market_scores
            
            if not ms:
                logger.info(f"[TSS-V2] Cycle #{self._compute_count}: No data yet ({elapsed:.1f}s)")
                return
            
            # Use W_15M as primary window, fallback to W_1H, then W_FULL_DAY
            wname = 'W_15M'
            if wname not in ms:
                wname = 'W_1H' if 'W_1H' in ms else 'W_FULL_DAY'
            if wname not in ms:
                wname = list(ms.keys())[0] if ms else None
            if not wname:
                return
            
            mkt = ms[wname]
            mkt_tss = mkt['tss']
            
            lines = []
            lines.append("")
            lines.append("═" * 100)
            lines.append(f"  📊 TSS v2 Dashboard │ Cycle #{self._compute_count} │ "
                         f"Window={wname} │ {self._last_symbol_count} symbols │ {elapsed:.1f}s")
            lines.append("═" * 100)
            
            # ─── Market Overview ───
            lines.append(f"  🌐 PREF MARKET: {self._tss_emoji(mkt_tss)} {mkt_tss:.1f} {self._tss_label(mkt_tss)}")
            
            # Show all windows in one line
            win_parts = []
            for w in ['W_5M', 'W_15M', 'W_1H', 'W_4H', 'W_FULL_DAY']:
                if w in ms:
                    win_parts.append(f"{w.replace('W_','')}: {ms[w]['tss']:.0f}")
            lines.append(f"  Windows: {' │ '.join(win_parts)}")
            
            top = mkt.get('top_group', {})
            bot = mkt.get('bottom_group', {})
            if top and bot:
                lines.append(f"  ▲ Most Bullish Group: {top.get('name','?'):>28s} = {top.get('tss',50):.1f}")
                lines.append(f"  ▼ Most Bearish Group: {bot.get('name','?'):>28s} = {bot.get('tss',50):.1f}")
            
            # ─── Group Rankings ───
            lines.append(f"  {'─' * 96}")
            lines.append(f"  {'#':>3}  {'Group':>30}  {'TSS':>5}  {'Signal':>12}  "
                         f"{'#Sym':>4}  Top 2 Bullish{'':>20}  Top 2 Bearish")
            lines.append(f"  {'─'*3}  {'─'*30}  {'─'*5}  {'─'*12}  {'─'*4}  {'─'*40}  {'─'*40}")
            
            grp_ranked = mkt.get('groups_ranked', [])
            for rank, ginfo in enumerate(grp_ranked, 1):
                gname = ginfo.get('name', '?')
                gtss = ginfo.get('tss', 50)
                gdata = gs.get(gname, {}).get(wname, {})
                n_sym = gdata.get('member_count', 0)
                
                # Get top 2 and bottom 2
                top_3 = gdata.get('top_3', [])
                bot_3 = gdata.get('bottom_3', [])
                
                top_str = ", ".join(
                    f"{m['sym']}={m['tss']:.0f}(+{m['rts']:.0f})" 
                    for m in top_3[:2]
                ) if top_3 else "-"
                
                bot_str = ", ".join(
                    f"{m['sym']}={m['tss']:.0f}({m['rts']:.0f})" 
                    for m in bot_3[-2:]
                ) if bot_3 else "-"
                
                lines.append(
                    f"  {rank:3d}  {gname:>30s}  {gtss:5.1f}  "
                    f"{self._tss_emoji(gtss)} {self._tss_label(gtss):>10s}  "
                    f"{n_sym:4d}  {top_str:<40s}  {bot_str}"
                )
            
            # ─── Top 5% and Bottom 5% symbols market-wide ───
            all_syms = []
            for sym, sdata in ss.items():
                if wname in sdata:
                    all_syms.append({
                        'sym': sym,
                        'tss': sdata[wname]['tss'],
                        'grp': self._group_cache.get(sym, '?'),
                        'rec': sdata[wname].get('recency_factor', 1.0),
                    })
            all_syms.sort(key=lambda x: -x['tss'])
            
            n_5pct = max(3, len(all_syms) * 5 // 100)  # At least 3
            
            if all_syms:
                lines.append(f"  {'─' * 96}")
                lines.append(f"  ▲ TOP {n_5pct} ({n_5pct}/{len(all_syms)} = top 5%):")
                for s in all_syms[:n_5pct]:
                    lines.append(f"      {s['sym']:>12s} {self._tss_emoji(s['tss'])} {s['tss']:5.1f}  "
                                 f"grp={s['grp']:<25s} rec={s['rec']:.1f}")
                
                lines.append(f"  ▼ BOTTOM {n_5pct}:")
                for s in all_syms[-n_5pct:]:
                    lines.append(f"      {s['sym']:>12s} {self._tss_emoji(s['tss'])} {s['tss']:5.1f}  "
                                 f"grp={s['grp']:<25s} rec={s['rec']:.1f}")
            
            lines.append("═" * 100)
            
            logger.info("\n".join(lines))
            
        except Exception as e:
            logger.warning(f"[TSS-V2] Dashboard log error: {e}")
    
    def _load_today_ticks(self) -> Dict[str, List[Dict]]:
        """Load today's truth ticks from Redis for all symbols."""
        result = {}
        
        try:
            # We will scan Redis for tt:ticks:* keys and find "today" based on the latest tick
            keys = []
            cursor = 0
            while True:
                cursor, batch = self.redis.scan(cursor, match="tt:ticks:*", count=500)
                keys.extend(batch)
                if cursor == 0:
                    break
            
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode()
                sym = key.replace("tt:ticks:", "")
                
                raw = self.redis.get(key)
                if not raw:
                    continue
                
                try:
                    ticks = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                    
                if not ticks:
                    continue
                    
                # Determine "today" based on the latest tick available for this symbol
                latest_ts = 0
                for t in ticks:
                    try:
                        ts = float(t.get('ts', 0))
                        if ts > 1e12: ts /= 1000.0
                        latest_ts = max(latest_ts, ts)
                    except:
                        pass
                
                if latest_ts == 0:
                    continue
                    
                # Calculate market open (09:30 ET) for that "latest" day
                et_tz = timezone(timedelta(hours=ET_OFFSET_HOURS))
                latest_et = datetime.fromtimestamp(latest_ts, timezone.utc).astimezone(et_tz)
                market_open_et = datetime(latest_et.year, latest_et.month, latest_et.day,
                                          9, 30, tzinfo=et_tz)
                market_open_ts = market_open_et.timestamp()
                
                # Filter to today's ticks (since market open)
                today_ticks = []
                for t in ticks:
                    try:
                        price = float(t.get('price', 0))
                        size = float(t.get('size', 0))
                        ts = float(t.get('ts', 0))
                        
                        if price <= 0 or size <= 0:
                            continue
                        
                        # Convert ms to seconds
                        if ts > 1e12:
                            ts = ts / 1000.0
                        
                        # Only today's market hours (since market_open_ts of that specific day)
                        if ts >= market_open_ts:
                            today_ticks.append({
                                'price': price,
                                'size': size,
                                'ts': ts,
                                'exch': str(t.get('exch', 'UNK')),
                            })
                    except (ValueError, TypeError):
                        continue
                
                if len(today_ticks) >= MIN_TICKS_PER_WINDOW:
                    today_ticks.sort(key=lambda x: x['ts'])
                    result[sym] = today_ticks
            
        except Exception as e:
            logger.error(f"[TSS-V2] Error loading ticks: {e}", exc_info=True)
        
        return result
    
    def _persist_to_redis(self, symbol_scores, group_scores, market_scores):
        """Write computed scores to Redis."""
        try:
            pipe = self.redis.pipeline()
            ts_now = time.time()
            
            # Per-symbol scores
            for sym, windows in symbol_scores.items():
                # Strip metrics from persisted data (too large for Redis)
                clean = {}
                for wname, wdata in windows.items():
                    clean[wname] = {k: v for k, v in wdata.items() if k != 'metrics'}
                
                payload = {
                    'symbol': sym,
                    'group': self._group_cache.get(sym, 'unknown'),
                    'adv': self._adv_cache.get(sym, 0),
                    'windows': clean,
                    'updated_at': ts_now,
                }
                pipe.setex(f"tss:v2:{sym}", 600, json.dumps(payload))
            
            # Group scores
            for grp, windows in group_scores.items():
                payload = {
                    'group': grp,
                    'windows': windows,
                    'updated_at': ts_now,
                }
                pipe.setex(f"tss:v2:group:{grp}", 600, json.dumps(payload))
            
            # Market scores
            if market_scores:
                payload = {
                    'windows': market_scores,
                    'updated_at': ts_now,
                }
                pipe.setex("tss:v2:market", 600, json.dumps(payload))
            
            # Summary for dashboard
            summary = self._build_summary(symbol_scores, group_scores, market_scores)
            if summary:
                pipe.setex("tss:v2:summary", 600, json.dumps(summary))
            
            pipe.execute()
            
        except Exception as e:
            logger.error(f"[TSS-V2] Redis persist error: {e}", exc_info=True)
    
    def _build_summary(self, symbol_scores, group_scores, market_scores) -> Dict:
        """Build a compact summary for dashboard display."""
        summary = {
            'updated_at': time.time(),
            'symbol_count': len(symbol_scores),
            'group_count': len(group_scores),
            'windows': {},
        }
        
        for wname in ROLLING_WINDOWS:
            ms = market_scores.get(wname)
            if not ms:
                continue
            
            # Top 10 bullish + bottom 10 bearish
            all_syms = []
            for sym, sdata in symbol_scores.items():
                if wname in sdata:
                    all_syms.append({
                        'sym': sym,
                        'tss': sdata[wname]['tss'],
                        'grp': self._group_cache.get(sym, '?'),
                    })
            all_syms.sort(key=lambda x: -x['tss'])
            
            summary['windows'][wname] = {
                'market_tss': ms['tss'],
                'symbol_count': ms['symbol_count'],
                'top_group': ms.get('top_group'),
                'bottom_group': ms.get('bottom_group'),
                'top_10': all_syms[:10],
                'bottom_10': all_syms[-10:] if len(all_syms) > 10 else [],
                'groups': ms.get('groups_ranked', []),
            }
        
        return summary
    
    # ════════════════════════════════════════════════════════════════
    # PUBLIC API — for other engines to read
    # ════════════════════════════════════════════════════════════════
    
    def get_symbol_tss(self, symbol: str, window: str = 'W_15M') -> Optional[Dict]:
        """Get TSS v2 score for a symbol in a specific window."""
        with self._lock:
            sym_data = self._symbol_scores.get(symbol)
            if sym_data and window in sym_data:
                return sym_data[window]
        return None
    
    def get_group_tss(self, group: str, window: str = 'W_15M') -> Optional[Dict]:
        """Get TSS v2 for a group."""
        with self._lock:
            grp_data = self._group_scores.get(group)
            if grp_data and window in grp_data:
                return grp_data[window]
        return None
    
    def get_market_tss(self, window: str = 'W_15M') -> Optional[Dict]:
        """Get market-wide TSS v2."""
        with self._lock:
            return self._market_scores.get(window)
    
    def get_all_scores(self) -> Dict[str, Any]:
        """Get complete snapshot of all scores."""
        with self._lock:
            return {
                'symbol_scores': dict(self._symbol_scores),
                'group_scores': dict(self._group_scores),
                'market_scores': dict(self._market_scores),
                'compute_count': self._compute_count,
                'last_compute': self._last_compute_time,
            }


# ════════════════════════════════════════════════════════════════════
# SINGLETON
# ════════════════════════════════════════════════════════════════════

_engine: Optional[TruthShiftV2Engine] = None


def get_truth_shift_v2_engine() -> Optional[TruthShiftV2Engine]:
    """Get global TruthShiftV2Engine instance."""
    return _engine


def initialize_truth_shift_v2_engine(redis_client=None, static_store=None,
                                      compute_interval: float = 300.0) -> TruthShiftV2Engine:
    """Initialize and start the global TruthShiftV2Engine."""
    global _engine
    
    if _engine is not None:
        return _engine
    
    if redis_client is None:
        from app.core.redis_client import get_redis_client
        rc = get_redis_client()
        redis_client = rc.sync if rc else None
    
    if redis_client is None:
        logger.error("[TSS-V2] Cannot initialize — Redis not available")
        return None
    
    _engine = TruthShiftV2Engine(
        redis_client=redis_client,
        static_store=static_store,
        compute_interval=compute_interval,
    )
    _engine.start()
    return _engine
