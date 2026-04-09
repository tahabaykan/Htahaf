"""
ETF Guard Terminal v2 — Market-wide circuit breaker for the Quant Engine.

Tiered Hard Stop + Micro-Trigger Architecture:

  ╔══════════════════════════════════════════════════════════╗
  ║ LAYER 1: HARD STOPS (Day-Change vs prev_close)          ║
  ║   PFF: HS1=-$0.15, HS2=-$0.18, HS3+=-$0.22 each step   ║
  ║   Each HS fires ONCE → cancel all + 60s freeze          ║
  ║   Rally: same but +$0.15, +$0.18, +$0.22 → cancel sells ║
  ╠══════════════════════════════════════════════════════════╣
  ║ LAYER 2: MICRO-TRIGGER (5-min bar window)               ║
  ║   PFF: every -$0.04 in 5m bar → cancel buys + 30s freeze║
  ║   After HS breached: micro freeze → 60s                 ║
  ║   Rally: +$0.04 → cancel sells + 30s/60s                ║
  ╚══════════════════════════════════════════════════════════╝

ETFs tracked: SPY, IWM, KRE, TLT, IEF, PFF

Integration points:
  - XNL Engine: reads `etf_guard_frozen` flag before starting cycles
  - Dual Process Runner: checks guard before each account phase
  - API: /api/etf-guard/status
"""

from __future__ import annotations
import asyncio
import csv
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from loguru import logger


# ──────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────

# ETFs to monitor — order matters for display
GUARD_ETFS = ["SPY", "IWM", "KRE", "TLT", "IEF", "PFF"]

# Check interval (seconds)
CHECK_INTERVAL_SEC = 15

# ── FREEZE DURATIONS ──
MICRO_FREEZE_SEC = 30       # Micro-trigger: 30s (before hard stop)
MICRO_FREEZE_POST_HS = 60   # Micro-trigger: 60s (after any hard stop breached)
HARD_STOP_FREEZE_SEC = 60   # Hard stop: always 60s

# Legacy alias for backward compatibility
FREEZE_DURATION_SEC = HARD_STOP_FREEZE_SEC

# Price history ring buffer size (keep 5 min = 20 snapshots at 15s interval)
HISTORY_SIZE = 20

# STATUS LOG interval: log a summary line every N seconds so guard activity is visible
STATUS_LOG_INTERVAL_SEC = 60

# ── TIERED HARD STOP THRESHOLDS (Day-Change vs prev_close) ──
# Format: {ETF: {type, hs1_drop, hs2_drop, hs3_step_drop, hs1_rally, hs2_rally, hs3_step_rally}}
# hs1: first hard stop, fires once
# hs2: second hard stop, fires once
# hs3_step: repeating step after hs2 (cumulative from prev_close)
#
# Example PFF bearish: HS1=-0.15, HS2=-0.18, then every -0.22 from hs2
#   Triggers at: -0.15, -0.18, -0.40, -0.62, -0.84 ...
HARD_STOP_TIERS: Dict[str, Dict] = {
    "SPY":  {"type": "pct", "hs1_drop": 1.50, "hs2_drop": 1.80, "hs3_step_drop": 0.50,
                            "hs1_rally": 1.50, "hs2_rally": 1.80, "hs3_step_rally": 0.50},
    "IWM":  {"type": "pct", "hs1_drop": 2.00, "hs2_drop": 2.50, "hs3_step_drop": 0.80,
                            "hs1_rally": 2.00, "hs2_rally": 2.50, "hs3_step_rally": 0.80},
    "KRE":  {"type": "pct", "hs1_drop": 2.50, "hs2_drop": 3.00, "hs3_step_drop": 1.00,
                            "hs1_rally": 2.50, "hs2_rally": 3.00, "hs3_step_rally": 1.00},
    "TLT":  {"type": "abs", "hs1_drop": 0.50, "hs2_drop": 0.70, "hs3_step_drop": 0.40,
                            "hs1_rally": 0.50, "hs2_rally": 0.70, "hs3_step_rally": 0.40},
    "IEF":  {"type": "abs", "hs1_drop": 0.20, "hs2_drop": 0.30, "hs3_step_drop": 0.15,
                            "hs1_rally": 0.20, "hs2_rally": 0.30, "hs3_step_rally": 0.15},
    "PFF":  {"type": "abs", "hs1_drop": 0.15, "hs2_drop": 0.18, "hs3_step_drop": 0.04,
                            "hs1_rally": 0.15, "hs2_rally": 0.18, "hs3_step_rally": 0.04},
}

# ── MICRO-TRIGGER (5-min bar intra-bar movement) ──
# Every N units of movement within a 5-min window → trigger
# PFF: every $0.04 drop in 5m → cancel buys; every $0.04 rally → cancel sells
MICRO_TRIGGER_STEP: Dict[str, Dict] = {
    "SPY":  {"type": "pct", "drop_step": 0.25, "rally_step": 0.25},
    "IWM":  {"type": "pct", "drop_step": 0.35, "rally_step": 0.35},
    "KRE":  {"type": "pct", "drop_step": 0.45, "rally_step": 0.45},
    "TLT":  {"type": "abs", "drop_step": 0.25, "rally_step": 0.25},
    "IEF":  {"type": "abs", "drop_step": 0.15, "rally_step": 0.15},
    "PFF":  {"type": "abs", "drop_step": 0.04, "rally_step": 0.04},
}

# 5-min bar window for micro-trigger
MICRO_BAR_WINDOW_SEC = 300  # 5 minutes

# Ring buffer thresholds (2min/5min window checks — secondary to hard stops)
DEFAULT_THRESHOLDS: Dict[str, Dict] = {
    "SPY":  {"type": "pct", "drop_2min": 0.40, "drop_5min": 0.60, "rally_2min": 0.40, "rally_5min": 0.60},
    "IWM":  {"type": "pct", "drop_2min": 0.50, "drop_5min": 0.75, "rally_2min": 0.50, "rally_5min": 0.75},
    "KRE":  {"type": "pct", "drop_2min": 0.40, "drop_5min": 0.60, "rally_2min": 0.40, "rally_5min": 0.60},
    "TLT":  {"type": "abs", "drop_2min": 0.40, "drop_5min": 0.60, "rally_2min": 0.40, "rally_5min": 0.60},
    "IEF":  {"type": "abs", "drop_2min": 0.20, "drop_5min": 0.30, "rally_2min": 0.20, "rally_5min": 0.30},
    "PFF":  {"type": "abs", "drop_2min": 0.04, "drop_5min": 0.06, "rally_2min": 0.04, "rally_5min": 0.06},
}


class GuardAction(Enum):
    NONE = "NONE"
    CANCEL_BUYS = "CANCEL_BUYS"        # Bearish → cancel buy orders
    CANCEL_SELLS = "CANCEL_SELLS"      # Bullish → cancel sell orders


@dataclass
class PriceSnapshot:
    """Single point-in-time price snapshot for all tracked ETFs."""
    timestamp: float  # time.time()
    time_str: str     # HH:MM:SS
    prices: Dict[str, float] = field(default_factory=dict)


@dataclass
class TriggerEvent:
    """Record of a guard trigger — for log and audit."""
    timestamp: str       # HH:MM:SS
    action: GuardAction
    triggers: List[str]  # Human-readable trigger descriptions
    cancelled_buys: int = 0
    cancelled_sells: int = 0
    freeze_until: Optional[str] = None


class ETFGuardState(Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    FROZEN = "FROZEN"     # Post-trigger freeze


# ──────────────────────────────────────────────────────────
# SINGLETON
# ──────────────────────────────────────────────────────────

_guard_instance: Optional["ETFGuardTerminal"] = None


def get_etf_guard() -> "ETFGuardTerminal":
    """Get or create the singleton ETF Guard Terminal."""
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = ETFGuardTerminal()
    return _guard_instance


# ──────────────────────────────────────────────────────────
# MAIN CLASS
# ──────────────────────────────────────────────────────────

class ETFGuardTerminal:
    """
    Continuous ETF price monitor with automatic order cancellation.
    
    Architecture:
    ─────────────
    Background task runs every 15s:
      1. Fetch prices for SPY, IWM, KRE, TLT, IEF, PFF
      2. Store in ring buffer (last 5 min)
      3. Compare current vs 2min-ago and 5min-ago
      4. If threshold breached:
         a. Log trigger event
         b. Cancel buys (bearish) or sells (bullish) on ALL accounts
         c. Set frozen flag for 30s
         d. XNL/DualProcess reads this flag and skips new cycles
    """

    def __init__(self):
        self._state = ETFGuardState.STOPPED
        self._task: Optional[asyncio.Task] = None
        self._history: deque = deque(maxlen=HISTORY_SIZE)
        self._thresholds = {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}
        self._events: List[TriggerEvent] = []
        self._last_trigger_time: float = 0
        self._freeze_until: float = 0
        self._started_at: Optional[datetime] = None
        self._check_count: int = 0
        self._last_status_log_time: float = 0
        self._prev_closes: Dict[str, float] = {}  # Loaded on startup for day-change checks
        self._seeded: bool = False  # True once ring buffer has been pre-seeded
        
        # ── TIERED HARD STOP STATE ──
        # Tracks which hard stop level each ETF has reached (0=none, 1=HS1 fired, 2=HS2 fired, 3+=HS3+)
        self._hs_bearish_level: Dict[str, int] = {etf: 0 for etf in GUARD_ETFS}
        self._hs_bullish_level: Dict[str, int] = {etf: 0 for etf in GUARD_ETFS}
        # The next bearish/bullish hard stop threshold value for each ETF
        self._hs_bearish_next: Dict[str, float] = {}  # Calculated on start
        self._hs_bullish_next: Dict[str, float] = {}  # Calculated on start
        
        # ── MICRO-TRIGGER STATE ──
        # 5-min bar window tracking: {ETF: (bar_start_ts, bar_open_price)}
        self._micro_bar: Dict[str, Tuple[float, float]] = {}
        # Last micro-trigger price for each ETF per direction
        self._micro_last_bearish_price: Dict[str, float] = {}  # Last price where bearish micro fired
        self._micro_last_bullish_price: Dict[str, float] = {}  # Last price where bullish micro fired
        
        # ── VIP TICK PROCESSING ──
        self._vip_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        
        # CSV log path
        self._log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
        os.makedirs(self._log_dir, exist_ok=True)

    # ─── PUBLIC API ───────────────────────────────────────

    def is_frozen(self) -> bool:
        """Check if ETF Guard has frozen trading. Called by XNL/DualProcess."""
        if self._freeze_until > 0 and time.time() < self._freeze_until:
            return True
        # Auto-unfreeze
        if self._freeze_until > 0 and time.time() >= self._freeze_until:
            if self._state == ETFGuardState.FROZEN:
                self._state = ETFGuardState.RUNNING
                logger.info("[ETF_GUARD] ❄️→🟢 Freeze ended, trading resumed")
                self._log_csv("UNFREEZE", "Freeze period ended, trading resumed")
            self._freeze_until = 0
        return False

    def process_vip_tick(self, symbol: str, market_data: dict):
        """Called by HammerFeed to inject a VIP tick directly and instantly wake up the evaluation loop."""
        if self._vip_event and self._loop:
            self._loop.call_soon_threadsafe(self._vip_event.set)
            
    def _execute_safeguard_checks(self):
        """Force a manual evaluation of the ring buffer, called on macro volatility."""
        if self._vip_event and self._loop:
            self._loop.call_soon_threadsafe(self._vip_event.set)

    def get_status(self) -> dict:
        """Full status for API endpoint."""
        frozen = self.is_frozen()
        remaining = max(0, self._freeze_until - time.time()) if frozen else 0
        
        # Current ETF prices from last snapshot
        last_snap = self._history[-1] if self._history else None
        current_prices = last_snap.prices if last_snap else {}
        
        # Build ETF status with changes
        etf_status = {}
        for etf in GUARD_ETFS:
            price = current_prices.get(etf, 0)
            chg_2min, chg_5min = self._get_changes(etf, price)
            threshold = self._thresholds.get(etf, {})
            etf_status[etf] = {
                "price": round(price, 2),
                "chg_2min": round(chg_2min, 2) if chg_2min is not None else None,
                "chg_5min": round(chg_5min, 2) if chg_5min is not None else None,
                "threshold_type": threshold.get("type", "pct"),
                "drop_2min_threshold": threshold.get("drop_2min"),
                "drop_5min_threshold": threshold.get("drop_5min"),
            }
        
        return {
            "state": self._state.value,
            "is_frozen": frozen,
            "freeze_remaining_sec": round(remaining, 1),
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "check_count": self._check_count,
            "history_points": len(self._history),
            "data_density_2min": round(self._data_density(120), 2),
            "data_density_5min": round(self._data_density(300), 2),
            "etfs": etf_status,
            "recent_events": [
                {
                    "time": e.timestamp,
                    "action": e.action.value,
                    "triggers": e.triggers,
                    "cancelled_buys": e.cancelled_buys,
                    "cancelled_sells": e.cancelled_sells,
                }
                for e in self._events[-10:]  # Last 10 events
            ],
        }

    async def start(self):
        """Start the ETF Guard background task."""
        if self._state != ETFGuardState.STOPPED:
            logger.warning("[ETF_GUARD] Already running")
            return
        
        self._state = ETFGuardState.RUNNING
        self._started_at = datetime.now()
        self._seeded = False
        
        # Store loop references for VIP threadsafe wakeup
        self._loop = asyncio.get_running_loop()
        self._vip_event = asyncio.Event()
        
        # ── LOAD PREV_CLOSE for day-change checks ──
        self._load_prev_closes()
        
        # ── PRE-SEED ring buffer with live/historical prices ──
        # MUST run BEFORE _init_hard_stop_levels so it can read
        # current prices and skip already-breached thresholds.
        await self._seed_ring_buffer()
        
        # ── INITIALIZE TIERED HARD STOP LEVELS ──
        # Uses ring buffer prices to skip startup cascade
        self._init_hard_stop_levels()
        
        self._task = asyncio.create_task(self._run_loop())
        logger.info("[ETF_GUARD] 🟢 ETF Guard Terminal STARTED — monitoring every 15s")
        self._log_csv("START", f"ETF Guard started — tracking {', '.join(GUARD_ETFS)}")

    def _load_prev_closes(self):
        """Load ETF prev_close values from janeketfs.csv for day-change checks."""
        self._prev_closes = {}
        try:
            import csv as csv_mod
            csv_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "..", "janeketfs.csv"
            )
            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv_mod.DictReader(f)
                    for row in reader:
                        sym = row.get('symbol') or row.get('Symbol') or row.get('sym', '')
                        pc = row.get('prev_close') or row.get('PrevClose') or row.get('close', '')
                        if sym and pc:
                            try:
                                self._prev_closes[sym.upper()] = float(pc)
                            except (ValueError, TypeError):
                                pass
            
            # Also try from ETF market data cache
            if not self._prev_closes:
                try:
                    from app.api.market_data_routes import get_etf_market_data
                    etf_cache = get_etf_market_data() or {}
                    for etf in GUARD_ETFS:
                        if etf in etf_cache:
                            pc = etf_cache[etf].get('prev_close')
                            if pc and float(pc) > 0:
                                self._prev_closes[etf] = float(pc)
                except Exception:
                    pass
            
            if self._prev_closes:
                pc_str = ', '.join(f"{k}=${v:.2f}" for k, v in sorted(self._prev_closes.items()) if k in GUARD_ETFS)
                logger.info(f"[ETF_GUARD] 📊 Loaded prev_close: {pc_str}")
            else:
                logger.warning("[ETF_GUARD] ⚠️ No prev_close data loaded — day-change checks disabled")
        except Exception as e:
            logger.error(f"[ETF_GUARD] prev_close load error: {e}")

    async def _seed_ring_buffer(self):
        """Pre-seed ring buffer with HISTORICAL prices from the last ~5 minutes.
        
        ═══════════════════════════════════════════════════════════════
        DESIGN: When engine starts at 18:43, we need to know what SPY,
        IWM, PFF etc. were at 18:38, 18:39, 18:40... so the FIRST check
        can detect a real move that happened BEFORE engine start.
        
        DATA SOURCES (in priority order):
        1. Hammer getTicks API — last 20 ticks per ETF (has timestamps)
        2. Redis tt:ticks:{ETF} — truth tick cache (has timestamps)
        3. Live L1 fetch — current price only (fallback, flat baseline)
        
        The ring buffer gets filled with 15s-interval snapshots going
        back 5 minutes, using the closest historical tick for each slot.
        ═══════════════════════════════════════════════════════════════
        """
        now = time.time()
        num_slots = HISTORY_SIZE  # 20 slots × 15s = 5 minutes
        
        # Build time slots we need to fill: [now-300s, now-285s, ..., now-15s]
        slot_times = [now - (i * CHECK_INTERVAL_SEC) for i in range(num_slots, 0, -1)]
        
        # ── Collect historical ticks per ETF ──
        etf_ticks: Dict[str, List[dict]] = {}  # {ETF: [{price, ts}, ...]} sorted by ts
        
        for etf in GUARD_ETFS:
            ticks = await self._fetch_historical_ticks_for_etf(etf, lookback_sec=360)
            if ticks:
                etf_ticks[etf] = ticks
        
        # ── Also get current live price as the "now" data point ──
        live_snap = await self._fetch_prices()
        if live_snap:
            for etf, price in live_snap.prices.items():
                if price > 0:
                    if etf not in etf_ticks:
                        etf_ticks[etf] = []
                    etf_ticks[etf].append({'price': price, 'ts': now})
        
        if not etf_ticks:
            # Absolute last resort — seed with current live prices (flat baseline)
            logger.warning("[ETF_GUARD] ⚠️ No historical data found — seeding with flat live baseline")
            await self._seed_flat_baseline()
            return
        
        # ── Build snapshots by interpolating ticks into time slots ──
        has_history = any(len(t) > 1 for t in etf_ticks.values())
        
        for slot_ts in slot_times:
            prices = {}
            for etf in GUARD_ETFS:
                ticks = etf_ticks.get(etf, [])
                if not ticks:
                    continue
                # Find the closest tick AT or BEFORE this slot time
                best_price = None
                best_dist = float('inf')
                for tick in ticks:
                    tick_ts = tick.get('ts', 0)
                    if tick_ts <= 0:
                        continue
                    dist = abs(slot_ts - tick_ts)
                    if dist < best_dist:
                        best_dist = dist
                        best_price = tick['price']
                if best_price and best_price > 0:
                    prices[etf] = round(best_price, 2)
            
            if prices:
                snap = PriceSnapshot(
                    timestamp=slot_ts,
                    time_str=datetime.fromtimestamp(slot_ts).strftime("%H:%M:%S"),
                    prices=prices,
                )
                self._history.append(snap)
        
        self._seeded = True
        
        # ── Log results ──
        hist_etfs = [e for e, t in etf_ticks.items() if len(t) > 1]
        flat_etfs = [e for e in GUARD_ETFS if e not in hist_etfs and e in etf_ticks]
        missing_etfs = [e for e in GUARD_ETFS if e not in etf_ticks]
        
        # Show oldest → newest prices for each ETF  
        summary_parts = []
        for etf in GUARD_ETFS:
            ticks = etf_ticks.get(etf, [])
            if not ticks:
                summary_parts.append(f"{etf}=?")
            elif len(ticks) == 1:
                summary_parts.append(f"{etf}=${ticks[0]['price']:.2f}(live only)")
            else:
                oldest = min(ticks, key=lambda t: t['ts'])
                newest = max(ticks, key=lambda t: t['ts'])
                age_sec = now - oldest['ts']
                chg = newest['price'] - oldest['price']
                summary_parts.append(
                    f"{etf}=${newest['price']:.2f}(Δ{chg:+.2f} over {age_sec:.0f}s)"
                )
        
        logger.info(
            f"[ETF_GUARD] 🌱 Ring buffer seeded with {len(self._history)} historical snapshots: "
            f"{', '.join(summary_parts)} "
            f"| historical={len(hist_etfs)} flat={len(flat_etfs)} missing={len(missing_etfs)}"
        )
        self._log_csv("SEED", f"Ring buffer pre-seeded with HISTORICAL prices ({len(self._history)} snapshots)")
    
    async def _fetch_historical_ticks_for_etf(
        self, etf: str, lookback_sec: int = 360
    ) -> List[dict]:
        """
        Fetch historical tick data for an ETF from last N seconds.
        
        Returns: [{price: float, ts: float}, ...] sorted by ts ascending
        """
        now = time.time()
        cutoff = now - lookback_sec
        ticks = []
        
        # ── SOURCE 1: Redis truth tick cache (tt:ticks:{etf}) ──
        try:
            import json as _json
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if redis:
                redis_sync = getattr(redis, 'sync', redis)
                raw = redis_sync.get(f"tt:ticks:{etf}")
                if raw:
                    data = _json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    if isinstance(data, list):
                        for t in data:
                            ts = float(t.get('ts', 0))
                            price = float(t.get('price', 0))
                            if ts >= cutoff and price > 0:
                                ticks.append({'price': price, 'ts': ts})
        except Exception:
            pass
        
        # ── SOURCE 2: Hammer getTicks API ──
        if len(ticks) < 5:
            try:
                from app.live.hammer_client import get_hammer_client
                import asyncio
                
                client = get_hammer_client()
                if client and client.is_connected():
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None,
                        lambda: client.get_ticks(etf, lastFew=30, tradesOnly=True, timeout=5.0)
                    )
                    if result and isinstance(result, dict):
                        tick_data = result.get('data', [])
                        if isinstance(tick_data, list):
                            for t in tick_data:
                                ts = float(t.get('ts', t.get('time', 0)))
                                price = float(t.get('price', t.get('last', 0)))
                                if ts >= cutoff and price > 0:
                                    if not any(abs(existing['ts'] - ts) < 1 for existing in ticks):
                                        ticks.append({'price': price, 'ts': ts})
            except Exception:
                pass
        
        # ── SOURCE 3: Redis L1 snapshot (current only) ──
        if not ticks:
            try:
                from app.core.redis_client import get_redis_client
                redis = get_redis_client()
                if redis:
                    redis_sync = getattr(redis, 'sync', redis)
                    val = redis_sync.hget(f"live:{etf}", "last")
                    if val:
                        p = float(val if isinstance(val, str) else val.decode('utf-8'))
                        if p > 0:
                            ticks.append({'price': p, 'ts': now})
            except Exception:
                pass
        
        # Sort by timestamp ascending
        ticks.sort(key=lambda t: t['ts'])
        return ticks
    
    async def _seed_flat_baseline(self):
        """Fallback: seed ring buffer with flat current L1 prices."""
        baseline_prices = {}
        live_snap = await self._fetch_prices()
        if live_snap:
            for etf, price in live_snap.prices.items():
                if price > 0:
                    baseline_prices[etf] = price
        
        if not baseline_prices:
            logger.warning("[ETF_GUARD] ⚠️ Cannot seed ring buffer — no prices available at all")
            return
        
        now = time.time()
        num_seeds = 8
        for i in range(num_seeds, 0, -1):
            fake_ts = now - (i * CHECK_INTERVAL_SEC)
            snap = PriceSnapshot(
                timestamp=fake_ts,
                time_str=datetime.fromtimestamp(fake_ts).strftime("%H:%M:%S"),
                prices=dict(baseline_prices),
            )
            self._history.append(snap)
        
        self._seeded = True
        seed_str = ', '.join(f"{k}=${v:.2f}" for k, v in sorted(baseline_prices.items()) if k in GUARD_ETFS)
        logger.info(f"[ETF_GUARD] 🌱 Ring buffer seeded FLAT (no history): {seed_str}")
        self._log_csv("SEED", "Ring buffer seeded flat with live prices (no historical data)")

    async def stop(self):
        """Stop the ETF Guard background task."""
        self._state = ETFGuardState.STOPPED
        self._freeze_until = 0
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("[ETF_GUARD] ⏹️ ETF Guard Terminal STOPPED")
        self._log_csv("STOP", "ETF Guard stopped")

    def update_thresholds(self, new_thresholds: Dict) -> bool:
        """Update threshold settings. Returns True on success."""
        try:
            for etf, settings in new_thresholds.items():
                if etf in self._thresholds:
                    self._thresholds[etf].update(settings)
            logger.info(f"[ETF_GUARD] Thresholds updated: {new_thresholds}")
            return True
        except Exception as e:
            logger.error(f"[ETF_GUARD] Threshold update error: {e}")
            return False

    # ─── MAIN LOOP ────────────────────────────────────────

    async def _run_loop(self):
        """Background loop — runs every 15 seconds."""
        logger.info("[ETF_GUARD] Background loop started")
        
        while self._state in (ETFGuardState.RUNNING, ETFGuardState.FROZEN):
            try:
                # 1. Fetch prices
                snapshot = await self._fetch_prices()
                if snapshot:
                    self._history.append(snapshot)
                    self._check_count += 1
                    
                    # 2. Check thresholds (only if not currently frozen)
                    if not self.is_frozen():
                        await self._check_thresholds(snapshot)
                        # 2b. TIERED hard stop check (day-change vs prev_close)
                        await self._check_day_change(snapshot)
                        # 2c. MICRO-TRIGGER check (5-min bar intra-bar movement)
                        await self._check_micro_trigger(snapshot)
                    else:
                        remaining = max(0, self._freeze_until - time.time())
                        if self._check_count % 4 == 0:  # Log every minute during freeze
                            logger.info(f"[ETF_GUARD] ❄️ Frozen — {remaining:.0f}s remaining")
                    
                    # 3. Periodic status log (every ~60s)
                    self._log_status(snapshot)
                    
                    # 4. Publish state to Redis
                    self._publish_to_redis(snapshot)
                else:
                    # No data — log warning (not silently)
                    if self._check_count % 4 == 0:
                        logger.warning(f"[ETF_GUARD] ⚠️ No ETF price data available (check #{self._check_count})")
                
                # Sleep up to 15 seconds, but wake up INSTANTLY if a VIP tick arrives
                try:
                    await asyncio.wait_for(self._vip_event.wait(), timeout=CHECK_INTERVAL_SEC)
                    self._vip_event.clear()  # reset for next time
                except asyncio.TimeoutError:
                    pass  # Normal 15-second interval
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ETF_GUARD] Loop error: {e}")
                await asyncio.sleep(CHECK_INTERVAL_SEC)

    def _log_status(self, snapshot: PriceSnapshot):
        """Log a periodic status summary so guard activity is visible in logs."""
        now = time.time()
        if now - self._last_status_log_time < STATUS_LOG_INTERVAL_SEC:
            return
        self._last_status_log_time = now
        
        parts = []
        for etf in GUARD_ETFS:
            price = snapshot.prices.get(etf, 0)
            if price <= 0:
                parts.append(f"{etf}=?")
                continue
            
            chg_2min, chg_5min = self._get_changes(etf, price)
            th = self._thresholds.get(etf, {})
            is_pct = th.get("type", "pct") == "pct"
            unit = "%" if is_pct else "$"
            
            # Day change vs prev_close
            day_chg = ""
            pc = self._prev_closes.get(etf)
            if pc and pc > 0:
                dc = (price - pc) / pc * 100
                day_chg = f" day={dc:+.2f}%"
            
            chg2_s = f"{chg_2min:+.2f}{unit}" if chg_2min is not None else "?"
            chg5_s = f"{chg_5min:+.2f}{unit}" if chg_5min is not None else "?"
            parts.append(f"{etf}=${price:.2f}(2m:{chg2_s} 5m:{chg5_s}{day_chg})")
        
        density_2 = self._data_density(120)
        density_5 = self._data_density(300)
        state_emoji = "🟢" if self._state == ETFGuardState.RUNNING else "❄️"
        
        logger.info(f"[ETF_GUARD] {state_emoji} Check #{self._check_count} | "
                    f"density(2m={density_2:.0%} 5m={density_5:.0%}) | "
                    f"{' | '.join(parts)}")
        
        # Also log to CSV for audit
        self._log_csv("STATUS", f"Check #{self._check_count} | {' | '.join(parts)}",
                      snapshot=snapshot)

    # ─── PRICE FETCHING ──────────────────────────────────

    async def _fetch_prices(self) -> Optional[PriceSnapshot]:
        """Fetch current prices for all tracked ETFs."""
        try:
            prices = {}
            
            # Try ETF market data cache first (Hammer L1 feed)
            try:
                from app.api.market_data_routes import get_etf_market_data, get_market_data
                etf_cache = get_etf_market_data() or {}
                
                for etf in GUARD_ETFS:
                    price = 0.0
                    
                    # Layer 1: ETF cache
                    if etf in etf_cache:
                        raw = etf_cache[etf]
                        last = raw.get('last') or raw.get('price')
                        if last and float(last) > 0:
                            price = float(last)
                    
                    # Layer 2: General market data
                    if price <= 0:
                        md = get_market_data(etf)
                        if md:
                            last = md.get('last') or md.get('price')
                            if last and float(last) > 0:
                                price = float(last)
                    
                    if price > 0:
                        prices[etf] = round(price, 2)
                        
            except ImportError:
                pass
            
            # Layer 3: Redis fallback
            if len(prices) < len(GUARD_ETFS):
                try:
                    from app.core.redis_client import get_redis_client
                    redis = get_redis_client()
                    if redis and getattr(redis, 'sync', None):
                        for etf in GUARD_ETFS:
                            if etf not in prices or prices[etf] <= 0:
                                val = redis.sync.hget(f"live:{etf}", "last")
                                if val:
                                    p = float(val if isinstance(val, str) else val.decode('utf-8'))
                                    if p > 0:
                                        prices[etf] = round(p, 2)
                except Exception:
                    pass
            
            if not prices:
                return None
            
            now = time.time()
            snap = PriceSnapshot(
                timestamp=now,
                time_str=datetime.now().strftime("%H:%M:%S"),
                prices=prices,
            )
            return snap
            
        except Exception as e:
            logger.error(f"[ETF_GUARD] Fetch error: {e}")
            return None

    # ─── THRESHOLD CHECKING ──────────────────────────────

    def _get_price_n_seconds_ago(self, etf: str, seconds: int) -> Tuple[Optional[float], Optional[float]]:
        """Get ETF price from N seconds ago using ring buffer.
        Returns (price, snapshot_timestamp) or (None, None)."""
        if not self._history:
            return None, None
        target_time = time.time() - seconds
        
        # Walk backward through history
        for snap in reversed(self._history):
            if snap.timestamp <= target_time:
                return snap.prices.get(etf), snap.timestamp
        return None, None

    def _data_density(self, seconds: int) -> float:
        """Calculate data density for the last N seconds.
        Returns ratio of actual snapshots vs expected (1.0 = perfect, 0.0 = no data).
        Expected = seconds / CHECK_INTERVAL_SEC snapshots."""
        if len(self._history) < 2:
            return 0.0
        now = time.time()
        cutoff = now - seconds
        actual = sum(1 for s in self._history if s.timestamp >= cutoff)
        expected = seconds / CHECK_INTERVAL_SEC
        return min(1.0, actual / max(expected, 1))

    def _get_changes(self, etf: str, current_price: float) -> Tuple[Optional[float], Optional[float]]:
        """Calculate 2-min and 5-min changes for an ETF."""
        if current_price <= 0:
            return None, None
        
        threshold = self._thresholds.get(etf, {})
        is_pct = threshold.get("type", "pct") == "pct"
        
        price_2min, ts_2min = self._get_price_n_seconds_ago(etf, 120)
        price_5min, ts_5min = self._get_price_n_seconds_ago(etf, 300)
        
        chg_2min = None
        chg_5min = None
        
        if price_2min and price_2min > 0:
            if is_pct:
                chg_2min = (current_price - price_2min) / price_2min * 100
            else:
                chg_2min = current_price - price_2min
        
        if price_5min and price_5min > 0:
            if is_pct:
                chg_5min = (current_price - price_5min) / price_5min * 100
            else:
                chg_5min = current_price - price_5min
        
        return chg_2min, chg_5min

    def _init_hard_stop_levels(self):
        """Initialize hard stop levels — SKIP already-breached thresholds.
        
        CRITICAL FIX: On startup, the market may already be -2.30% from
        prev_close. The old code started at level=0 → immediately fired
        HS1 at -2.00%, then HS2 at -2.50% etc. in rapid cascade.
        
        NEW BEHAVIOR: Check current price vs prev_close and advance the
        level to match the CURRENT state. Only genuinely NEW crossings
        (price moves FURTHER from current position) will trigger.
        
        Example: IWM is already -2.30% at startup
          Old: level=0, next=2.00% → fires HS1 immediately! → cascade
          New: level=1, next=2.50% → only fires if IWM drops PAST -2.50%
        """
        # Get current prices from the ring buffer (already seeded) or live
        current_prices = {}
        if self._history:
            last_snap = self._history[-1]
            current_prices = last_snap.prices
        
        for etf in GUARD_ETFS:
            tiers = HARD_STOP_TIERS.get(etf)
            if not tiers:
                continue
            
            pc = self._prev_closes.get(etf, 0)
            current = current_prices.get(etf, 0)
            
            # Calculate current day-change magnitude
            if pc > 0 and current > 0:
                is_pct = tiers["type"] == "pct"
                if is_pct:
                    day_chg = abs((current - pc) / pc * 100)
                else:
                    day_chg = abs(current - pc)
                
                # ── BEARISH: find how many levels are already breached ──
                bear_level = 0
                bear_chg = (pc - current) / pc * 100 if is_pct else (pc - current)  # positive = price dropped
                
                if bear_chg > 0:  # Price is below prev_close
                    # Walk through levels until we pass current position
                    test_level = 0
                    while True:
                        threshold = self._get_next_hs_threshold(etf, "drop", test_level)
                        if bear_chg >= threshold:
                            test_level += 1
                        else:
                            break
                        if test_level > 20:  # Safety cap
                            break
                    bear_level = test_level
                
                # ── BULLISH: same logic ──
                bull_level = 0
                bull_chg = (current - pc) / pc * 100 if is_pct else (current - pc)  # positive = price rallied
                
                if bull_chg > 0:  # Price is above prev_close
                    test_level = 0
                    while True:
                        threshold = self._get_next_hs_threshold(etf, "rally", test_level)
                        if bull_chg >= threshold:
                            test_level += 1
                        else:
                            break
                        if test_level > 20:
                            break
                    bull_level = test_level
                
                self._hs_bearish_level[etf] = bear_level
                self._hs_bullish_level[etf] = bull_level
                self._hs_bearish_next[etf] = self._get_next_hs_threshold(etf, "drop", bear_level)
                self._hs_bullish_next[etf] = self._get_next_hs_threshold(etf, "rally", bull_level)
                
                unit = "%" if is_pct else "$"
                if bear_level > 0 or bull_level > 0:
                    logger.warning(
                        f"[ETF_GUARD] ⏩ {etf} SKIPPED startup cascade: "
                        f"price=${current:.2f} prev=${pc:.2f} | "
                        f"bear_level={bear_level} (next={self._hs_bearish_next[etf]:.2f}{unit}) | "
                        f"bull_level={bull_level} (next={self._hs_bullish_next[etf]:.2f}{unit})"
                    )
            else:
                # No price data — start from level 0 (normal)
                self._hs_bearish_level[etf] = 0
                self._hs_bullish_level[etf] = 0
                self._hs_bearish_next[etf] = tiers["hs1_drop"]
                self._hs_bullish_next[etf] = tiers["hs1_rally"]
        
        logger.info(f"[ETF_GUARD] 🎯 Hard stop levels initialized: "
                    f"{', '.join(f'{e} bear={self._hs_bearish_next.get(e, 0):.2f} bull={self._hs_bullish_next.get(e, 0):.2f}' for e in GUARD_ETFS)}")

    def _get_next_hs_threshold(self, etf: str, direction: str, current_level: int) -> float:
        """Calculate the next hard stop threshold for an ETF.
        direction: 'drop' or 'rally'
        current_level: 0=none fired yet, 1=HS1 fired, 2=HS2 fired, 3+=HS3+ fired
        Returns the absolute day-change value that would trigger the NEXT hard stop.
        """
        tiers = HARD_STOP_TIERS.get(etf, {})
        if not tiers:
            return 999.0
        
        if current_level == 0:
            return tiers[f"hs1_{direction}"]
        elif current_level == 1:
            return tiers[f"hs2_{direction}"]
        else:
            # HS3+: hs2 + (level - 1) * hs3_step
            hs2 = tiers[f"hs2_{direction}"]
            step = tiers[f"hs3_step_{direction}"]
            return hs2 + (current_level - 1) * step

    async def _check_day_change(self, snapshot: PriceSnapshot):
        """TIERED hard stop check — day-change vs prev_close.
        
        v2 Architecture:
        ────────────────
        Each ETF has tiered hard stops: HS1 → HS2 → HS3 (repeating).
        Each level fires ONCE when reached, then the next level becomes active.
        This eliminates the old perpetual freeze-refreeze loop.
        
        Example PFF bearish: HS1=-$0.15, HS2=-$0.18, then every -$0.22 step.
        When PFF day-change hits -$0.15: HS1 fires, cancel buys, 60s freeze.
        Next trigger is at -$0.18 (not -$0.15 again).
        """
        if not self._prev_closes:
            return
        
        bearish_triggers: List[str] = []
        bullish_triggers: List[str] = []
        
        for etf in GUARD_ETFS:
            current = snapshot.prices.get(etf, 0)
            pc = self._prev_closes.get(etf, 0)
            if current <= 0 or pc <= 0:
                continue
            
            tiers = HARD_STOP_TIERS.get(etf)
            if not tiers:
                continue
            
            is_pct = tiers["type"] == "pct"
            if is_pct:
                day_chg = (current - pc) / pc * 100
                unit = "%"
            else:
                day_chg = current - pc
                unit = "$"
            
            # ── BEARISH CHECK ──
            bear_next = self._hs_bearish_next.get(etf, 999)
            bear_level = self._hs_bearish_level.get(etf, 0)
            
            if day_chg <= -bear_next:
                # Hard stop breached! Fire and advance to next level.
                bear_level += 1
                self._hs_bearish_level[etf] = bear_level
                
                # Calculate next threshold
                next_thresh = self._get_next_hs_threshold(etf, "drop", bear_level)
                self._hs_bearish_next[etf] = next_thresh
                
                hs_label = f"HS{bear_level}" if bear_level <= 2 else f"HS3.{bear_level - 2}"
                pct_chg = (current - pc) / pc * 100
                abs_chg = current - pc
                bearish_triggers.append(
                    f"{etf} {hs_label}: ${pc:.2f}\u2192${current:.2f} "
                    f"({abs_chg:+.2f}$, {pct_chg:+.2f}%) "
                    f"[trigger={bear_next:.2f}{unit}, next={next_thresh:.2f}{unit}]"
                )
            
            # ── BULLISH CHECK ──
            bull_next = self._hs_bullish_next.get(etf, 999)
            bull_level = self._hs_bullish_level.get(etf, 0)
            
            if day_chg >= bull_next:
                bull_level += 1
                self._hs_bullish_level[etf] = bull_level
                
                next_thresh = self._get_next_hs_threshold(etf, "rally", bull_level)
                self._hs_bullish_next[etf] = next_thresh
                
                hs_label = f"HS{bull_level}" if bull_level <= 2 else f"HS3.{bull_level - 2}"
                pct_chg = (current - pc) / pc * 100
                abs_chg = current - pc
                bullish_triggers.append(
                    f"{etf} {hs_label}: ${pc:.2f}\u2192${current:.2f} "
                    f"({abs_chg:+.2f}$, {pct_chg:+.2f}%) "
                    f"[trigger={bull_next:.2f}{unit}, next={next_thresh:.2f}{unit}]"
                )
        
        if bearish_triggers:
            logger.warning(f"[ETF_GUARD] 🚨 HARD STOP (bearish): {bearish_triggers}")
            await self._execute_action(GuardAction.CANCEL_BUYS, bearish_triggers,
                                       freeze_sec=HARD_STOP_FREEZE_SEC)
        if bullish_triggers:
            logger.warning(f"[ETF_GUARD] 🚨 HARD STOP (bullish): {bullish_triggers}")
            await self._execute_action(GuardAction.CANCEL_SELLS, bullish_triggers,
                                       freeze_sec=HARD_STOP_FREEZE_SEC)

    def _any_hs_breached(self) -> bool:
        """Check if any ETF has breached at least HS1 in either direction."""
        for etf in GUARD_ETFS:
            if self._hs_bearish_level.get(etf, 0) > 0:
                return True
            if self._hs_bullish_level.get(etf, 0) > 0:
                return True
        return False

    async def _check_micro_trigger(self, snapshot: PriceSnapshot):
        """MICRO-TRIGGER: 5-min bar intra-bar movement check.
        
        For each ETF, we track a rolling 5-minute bar window.
        When the price drops by the ETF's micro-trigger step within that
        window, we fire a cancel-buys trigger (bearish) with 30s freeze.
        If any hard stop has been breached, freeze extends to 60s.
        
        Rally direction: same logic with cancel-sells.
        """
        now = time.time()
        
        bearish_triggers: List[str] = []
        bullish_triggers: List[str] = []
        
        for etf in GUARD_ETFS:
            current = snapshot.prices.get(etf, 0)
            if current <= 0:
                continue
            
            micro_cfg = MICRO_TRIGGER_STEP.get(etf)
            if not micro_cfg:
                continue
            
            is_pct = micro_cfg["type"] == "pct"
            
            # ── Manage 5-min bar window ──
            bar_info = self._micro_bar.get(etf)
            if bar_info is None or (now - bar_info[0]) >= MICRO_BAR_WINDOW_SEC:
                # Start new 5-min bar
                self._micro_bar[etf] = (now, current)
                self._micro_last_bearish_price[etf] = current
                self._micro_last_bullish_price[etf] = current
                continue
            
            bar_start_ts, bar_open = bar_info
            
            # ── Calculate drop/rally from last trigger price ──
            last_bear_price = self._micro_last_bearish_price.get(etf, bar_open)
            last_bull_price = self._micro_last_bullish_price.get(etf, bar_open)
            
            if is_pct:
                drop_from_last = (last_bear_price - current) / last_bear_price * 100 if last_bear_price > 0 else 0
                rally_from_last = (current - last_bull_price) / last_bull_price * 100 if last_bull_price > 0 else 0
                drop_step = micro_cfg["drop_step"]
                rally_step = micro_cfg["rally_step"]
                unit = "%"
            else:
                drop_from_last = last_bear_price - current
                rally_from_last = current - last_bull_price
                drop_step = micro_cfg["drop_step"]
                rally_step = micro_cfg["rally_step"]
                unit = "$"
            
            # ── BEARISH micro-trigger ──
            if drop_from_last >= drop_step:
                # How many steps?
                num_steps = int(drop_from_last / drop_step)
                # Move the last trigger price down by the steps we consumed
                if is_pct:
                    new_ref = last_bear_price * (1 - (num_steps * drop_step / 100))
                else:
                    new_ref = last_bear_price - (num_steps * drop_step)
                self._micro_last_bearish_price[etf] = new_ref
                
                bar_age = now - bar_start_ts
                # Calculate both absolute and percentage change
                abs_drop = last_bear_price - current
                pct_drop = (last_bear_price - current) / last_bear_price * 100 if last_bear_price > 0 else 0
                bearish_triggers.append(
                    f"{etf} MICRO: ${last_bear_price:.2f}\u2192${current:.2f} "
                    f"(-{abs_drop:.2f}$, -{pct_drop:.2f}%) in {bar_age:.0f}s "
                    f"[{num_steps}x {drop_step:.2f}{unit}] \u2192 CANCEL BUYS"
                )
            
            # ── BULLISH micro-trigger ──
            if rally_from_last >= rally_step:
                num_steps = int(rally_from_last / rally_step)
                if is_pct:
                    new_ref = last_bull_price * (1 + (num_steps * rally_step / 100))
                else:
                    new_ref = last_bull_price + (num_steps * rally_step)
                self._micro_last_bullish_price[etf] = new_ref
                
                bar_age = now - bar_start_ts
                abs_rally = current - last_bull_price
                pct_rally = (current - last_bull_price) / last_bull_price * 100 if last_bull_price > 0 else 0
                bullish_triggers.append(
                    f"{etf} MICRO: ${last_bull_price:.2f}\u2192${current:.2f} "
                    f"(+{abs_rally:.2f}$, +{pct_rally:.2f}%) in {bar_age:.0f}s "
                    f"[{num_steps}x {rally_step:.2f}{unit}] \u2192 CANCEL SELLS"
                )
        
        if not bearish_triggers and not bullish_triggers:
            return
        
        # Freeze duration depends on whether any hard stop has been breached
        hs_active = self._any_hs_breached()
        freeze_sec = MICRO_FREEZE_POST_HS if hs_active else MICRO_FREEZE_SEC
        
        if bearish_triggers:
            logger.warning(f"[ETF_GUARD] ⚡ MICRO-TRIGGER (bearish, freeze={freeze_sec}s): {bearish_triggers}")
            await self._execute_action(GuardAction.CANCEL_BUYS, bearish_triggers,
                                       freeze_sec=freeze_sec)
        if bullish_triggers:
            logger.warning(f"[ETF_GUARD] ⚡ MICRO-TRIGGER (bullish, freeze={freeze_sec}s): {bullish_triggers}")
            await self._execute_action(GuardAction.CANCEL_SELLS, bullish_triggers,
                                       freeze_sec=freeze_sec)

    async def _check_thresholds(self, snapshot: PriceSnapshot):
        """Check all ETFs against thresholds — trigger cancel if breached.
        
        Data quality protection:
        - If ring buffer density < 25% → skip check entirely (stale data)
        - If density < 80% → widen thresholds proportionally
        - This prevents false triggers from L1 feed disconnections
        
        NOTE: Even if this check is skipped, _check_day_change() still runs
        as an independent safety net using prev_close comparison.
        """
        # NOTE: No cooldown for ring buffer checks — tiered hard stops handle their own gating
        
        # ── DATA QUALITY GATE ─────────────────────────────────
        # Check ring buffer density for 2min and 5min windows
        density_2min = self._data_density(120)
        density_5min = self._data_density(300)
        
        # Lowered from 0.40 → 0.25: the ring buffer is now pre-seeded on
        # startup, so we have baseline data immediately. The old 0.40 gate
        # was too strict and caused a 5-min blind spot after restart.
        # The day-change check provides a separate safety net regardless.
        MIN_DENSITY = 0.25  # Need at least 25% of expected snapshots
        if density_5min < MIN_DENSITY:
            if self._check_count % 8 == 0:  # Log every ~2 minutes
                logger.info(f"[ETF_GUARD] ⏭️ Skipping ring-buffer check — data too sparse "
                           f"(2min: {density_2min:.0%}, 5min: {density_5min:.0%}) "
                           f"[day-change check still active]")
            return
        
        # Scale thresholds up when data is sparse (more tolerance for gaps)
        # density 1.0 → scale 1.0 (normal), density 0.5 → scale 2.0 (2x wider)
        GOOD_DENSITY = 0.80
        scale_2min = max(1.0, GOOD_DENSITY / max(density_2min, 0.01))
        scale_5min = max(1.0, GOOD_DENSITY / max(density_5min, 0.01))
        
        if scale_2min > 1.05 or scale_5min > 1.05:
            logger.debug(f"[ETF_GUARD] 📊 Data density: 2min={density_2min:.0%} "
                        f"(scale {scale_2min:.1f}x), 5min={density_5min:.0%} "
                        f"(scale {scale_5min:.1f}x)")
        
        bearish_triggers: List[str] = []
        bullish_triggers: List[str] = []
        
        for etf in GUARD_ETFS:
            current = snapshot.prices.get(etf, 0)
            if current <= 0:
                continue
            
            th = self._thresholds.get(etf)
            if not th:
                continue
            
            is_pct = th["type"] == "pct"
            unit = "%" if is_pct else "$"
            
            chg_2min, chg_5min = self._get_changes(etf, current)
            
            # Apply scaled thresholds (wider when data sparse)
            drop_2min = th["drop_2min"] * scale_2min
            rally_2min = th["rally_2min"] * scale_2min
            drop_5min = th["drop_5min"] * scale_5min
            rally_5min = th["rally_5min"] * scale_5min
            
            # 2-min window
            if chg_2min is not None:
                if chg_2min <= -drop_2min:
                    bearish_triggers.append(f"{etf} 2m: {chg_2min:+.2f}{unit} (limit: -{drop_2min:.2f}{unit})")
                elif chg_2min >= rally_2min:
                    bullish_triggers.append(f"{etf} 2m: {chg_2min:+.2f}{unit} (limit: +{rally_2min:.2f}{unit})")
            
            # 5-min window
            if chg_5min is not None:
                if chg_5min <= -drop_5min:
                    bearish_triggers.append(f"{etf} 5m: {chg_5min:+.2f}{unit} (limit: -{drop_5min:.2f}{unit})")
                elif chg_5min >= rally_5min:
                    bullish_triggers.append(f"{etf} 5m: {chg_5min:+.2f}{unit} (limit: +{rally_5min:.2f}{unit})")
        
        # Execute action (both directions independently)
        if bearish_triggers:
            await self._execute_action(GuardAction.CANCEL_BUYS, bearish_triggers)
        if bullish_triggers:
            await self._execute_action(GuardAction.CANCEL_SELLS, bullish_triggers)

    # ─── ACTION EXECUTION ────────────────────────────────

    # ETFs that can trigger PANIC MODE — TLT/IEF are monitored for
    # guard actions (cancel orders) but do NOT escalate to ACTMAN Panic.
    PANIC_ELIGIBLE_ETFS = {"SPY", "KRE", "IWM", "PFF"}

    async def _execute_action(self, action: GuardAction, triggers: List[str],
                              freeze_sec: int = HARD_STOP_FREEZE_SEC):
        """Cancel orders + freeze XNL for the specified duration.
        
        After cancelling and freezing, checks if any PANIC_ELIGIBLE_ETFS
        are among the triggers. If so, fires ACTMAN Panic Engine as a
        background task (fire-and-forget) to open protective positions
        DURING the freeze window.
        """
        import asyncio as _asyncio
        
        now_str = datetime.now().strftime("%H:%M:%S")
        
        logger.warning(f"[ETF_GUARD] {'🔴 BEARISH' if action == GuardAction.CANCEL_BUYS else '🟢 BULLISH'} "
                       f"TRIGGER: {', '.join(triggers)}")
        
        # Record event
        event = TriggerEvent(
            timestamp=now_str,
            action=action,
            triggers=triggers,
        )
        
        # Cancel orders on ALL accounts
        cancelled_buys = 0
        cancelled_sells = 0
        
        try:
            from app.xnl.xnl_engine import get_xnl_engine
            engine = get_xnl_engine()
            
            if engine:
                accounts = ["HAMPRO", "IBKR_PED"]
                
                for account_id in accounts:
                    try:
                        if action == GuardAction.CANCEL_BUYS:
                            result = await engine._cancel_orders_by_side(account_id, "BUY")
                            cancelled_buys += result.get("cancelled", 0)
                            logger.warning(f"[ETF_GUARD] 🔴 Cancelled {result.get('cancelled', 0)} BUY orders "
                                         f"on {account_id}")
                        else:
                            result = await engine._cancel_orders_by_side(account_id, "SELL")
                            cancelled_sells += result.get("cancelled", 0)
                            logger.warning(f"[ETF_GUARD] 🟢 Cancelled {result.get('cancelled', 0)} SELL orders "
                                         f"on {account_id}")
                    except Exception as e:
                        logger.error(f"[ETF_GUARD] Cancel error on {account_id}: {e}")
                        
        except Exception as e:
            logger.error(f"[ETF_GUARD] Engine access error: {e}")
        
        event.cancelled_buys = cancelled_buys
        event.cancelled_sells = cancelled_sells
        
        # Freeze XNL for the specified duration
        self._freeze_until = time.time() + freeze_sec
        self._state = ETFGuardState.FROZEN
        self._last_trigger_time = time.time()
        
        freeze_end = datetime.fromtimestamp(self._freeze_until).strftime("%H:%M:%S")
        event.freeze_until = freeze_end
        self._events.append(event)
        
        logger.warning(f"[ETF_GUARD] ❄️ XNL FROZEN for {freeze_sec}s "
                       f"(until {freeze_end}) — "
                       f"cancelled {cancelled_buys} buys, {cancelled_sells} sells")
        
        # Log to CSV
        action_str = f"{action.value} | triggers: {'; '.join(triggers)}"
        detail = (f"Cancelled buys={cancelled_buys}, sells={cancelled_sells}, "
                  f"frozen until {freeze_end} ({freeze_sec}s)")
        self._log_csv(action.value, f"{action_str} || {detail}")
        
        # Publish alert to Redis
        self._publish_alert_to_redis(event)
        
        # ── PANIC MODE TRIGGER ──────────────────────────────────────────
        # Fire ACTMAN Panic Engine if a PANIC_ELIGIBLE_ETF is among triggers.
        # TLT/IEF are excluded — they still cause cancel+freeze but NO panic.
        # Panic runs as fire-and-forget during the freeze window.
        try:
            # Check if any panic-eligible ETF is in the trigger list
            has_panic_etf = any(
                any(etf in trig for etf in self.PANIC_ELIGIBLE_ETFS)
                for trig in triggers
            )
            
            if has_panic_etf:
                logger.warning(f"[ETF_GUARD] 🚨 PANIC MODE eligible — "
                              f"launching ACTMAN Panic Engine (fire-and-forget)")
                _asyncio.create_task(
                    self._fire_panic_engine(action, triggers),
                    name="etf_guard_panic"
                )
            else:
                # TLT/IEF only — cancel+freeze but no panic
                trigger_etfs = [t.split()[0] for t in triggers if t]
                logger.info(f"[ETF_GUARD] No panic escalation — "
                           f"trigger ETFs {trigger_etfs} not in PANIC_ELIGIBLE list")
        except Exception as pe:
            logger.error(f"[ETF_GUARD] Panic trigger error (non-fatal): {pe}")

    async def _fire_panic_engine(self, action: GuardAction, triggers: List[str]):
        """Fire ACTMAN Panic Engine as a background task during freeze.
        
        Reads current ETF changes, positions, and metrics, then lets
        the Panic Engine evaluate and generate protective orders.
        """
        try:
            from app.actman.actman_panic_engine import get_actman_panic, read_etf_changes
            
            panic = get_actman_panic()
            etf_changes = read_etf_changes()
            
            if not etf_changes:
                logger.warning("[ETF_GUARD→PANIC] No ETF change data available — skipping")
                return
            
            # Run panic for both accounts
            accounts = ["HAMPRO", "IBKR_PED"]
            
            for account_id in accounts:
                try:
                    # Get current positions and config for this account
                    from app.psfalgo.position_snapshot_api import get_position_snapshot_api
                    from app.actman.actman_config import PANIC_ENABLED
                    
                    if not PANIC_ENABLED:
                        logger.info("[ETF_GUARD→PANIC] PANIC_ENABLED=False — skipping")
                        return
                    
                    pos_api = get_position_snapshot_api()
                    if not pos_api:
                        continue
                    
                    snapshots = await pos_api.get_position_snapshot(
                        account_id=account_id,
                        include_zero_positions=False
                    )
                    
                    if not snapshots:
                        logger.info(f"[ETF_GUARD→PANIC] No positions for {account_id} — skipping")
                        continue
                    
                    # Calculate current L/S split
                    total_lots = sum(abs(int(s.qty)) for s in snapshots)
                    long_lots = sum(abs(int(s.qty)) for s in snapshots if s.qty > 0)
                    actual_long_pct = (long_lots / total_lots * 100) if total_lots > 0 else 50.0
                    
                    # Default config L% — Redis override or constant
                    from app.actman.actman_config import HEDGER_CONFIG_LONG_PCT
                    config_long_pct = HEDGER_CONFIG_LONG_PCT  # 60.0 default
                    try:
                        from app.core.redis_client import get_redis_client
                        r = get_redis_client()
                        if r:
                            redis_sync = getattr(r, 'sync', r)
                            val = redis_sync.get(f"psfalgo:actman:config_long_pct:{account_id}")
                            if val:
                                config_long_pct = float(val if isinstance(val, str) else val.decode())
                    except Exception:
                        pass
                    
                    # Build minimal symbol data for panic scoring
                    all_symbols_data = []
                    try:
                        from app.market_data.static_data_store import get_static_data_store
                        store = get_static_data_store()
                        if store:
                            for snap in snapshots:
                                sym_data = store.get_symbol_data(snap.symbol)
                                if sym_data:
                                    all_symbols_data.append({
                                        'symbol': snap.symbol,
                                        'dos_grup': getattr(sym_data, 'dos_grup', getattr(sym_data, 'GROUP', '')),
                                        'cgrup': getattr(sym_data, 'cgrup', getattr(sym_data, 'CGRUP', '')),
                                        'avg_adv': float(getattr(sym_data, 'AVG_ADV', 0) or 0),
                                        'final_bs': float(getattr(sym_data, 'final_bs', 0) or getattr(sym_data, 'SFSTOT', 0) or 0),
                                        'final_ab': float(getattr(sym_data, 'final_ab', 0) or getattr(sym_data, 'FBTOT', 0) or 0),
                                        'sfs_score': float(getattr(sym_data, 'sfstot', 0) or 0),
                                        'fb_score': float(getattr(sym_data, 'fbtot', 0) or 0),
                                        'spread': float(getattr(sym_data, 'spread', 0) or 0),
                                        'spread_pct': float(getattr(sym_data, 'spread_pct', 0) or 0),
                                        'bid': float(getattr(sym_data, 'bid', 0) or 0),
                                        'ask': float(getattr(sym_data, 'ask', 0) or 0),
                                        'son5_tick': float(getattr(sym_data, 'son5_tick', 0) or getattr(sym_data, 'last', 0) or 0),
                                        'maxalw': float(getattr(sym_data, 'maxalw', 0) or getattr(sym_data, 'MAXALW', 0) or 0),
                                        'current_qty': int(snap.qty),
                                        'last_price': float(snap.current_price or 0),
                                    })
                    except Exception as data_err:
                        logger.warning(f"[ETF_GUARD→PANIC] Symbol data build error: {data_err}")
                    
                    result = await panic.evaluate(
                        account_id=account_id,
                        config_long_pct=config_long_pct,
                        actual_long_pct=actual_long_pct,
                        total_lots=total_lots,
                        etf_changes=etf_changes,
                        all_symbols_data=all_symbols_data,
                        positions=snapshots,
                    )
                    
                    if result.triggered and result.orders:
                        logger.warning(
                            f"[ETF_GUARD→PANIC] 🚨 {account_id}: {result.direction} {result.severity} | "
                            f"{len(result.orders)} panic orders generated | "
                            f"shift={result.config_shift:.1f}% target_L={result.panic_target_long_pct:.1f}%"
                        )
                    else:
                        logger.info(
                            f"[ETF_GUARD→PANIC] {account_id}: {result.reason} "
                            f"(direction={result.direction}, severity={result.severity})"
                        )
                        
                except Exception as acct_err:
                    logger.error(f"[ETF_GUARD→PANIC] {account_id} error: {acct_err}", exc_info=True)
        
        except Exception as e:
            logger.error(f"[ETF_GUARD→PANIC] Panic engine error: {e}", exc_info=True)

    # ─── LOGGING ─────────────────────────────────────────

    def _get_log_filepath(self) -> str:
        """Daily CSV log file."""
        date_str = datetime.now().strftime("%Y%m%d")
        return os.path.join(self._log_dir, f"etf_guard_{date_str}.csv")

    def _log_csv(self, event_type: str, detail: str, snapshot: Optional[PriceSnapshot] = None):
        """Append a row to the daily ETF Guard CSV log."""
        try:
            filepath = self._get_log_filepath()
            file_exists = os.path.exists(filepath)
            
            # Current ETF snapshot
            price_str = ""
            snap = snapshot or (self._history[-1] if self._history else None)
            if snap:
                parts = [f"{etf}=${snap.prices.get(etf, 0):.2f}" for etf in GUARD_ETFS]
                price_str = " | ".join(parts)
            
            with open(filepath, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Time", "Event", "Detail", "Prices"])
                writer.writerow([
                    datetime.now().strftime("%H:%M:%S"),
                    event_type,
                    detail,
                    price_str,
                ])
        except Exception as e:
            logger.debug(f"[ETF_GUARD] CSV log error: {e}")

    # ─── REDIS INTEGRATION ───────────────────────────────

    def _publish_to_redis(self, snapshot: PriceSnapshot):
        """Publish current ETF Guard state to Redis for dashboard consumption."""
        try:
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if not redis or not getattr(redis, 'sync', None):
                return
            
            import json
            state_data = {
                "state": self._state.value,
                "is_frozen": self.is_frozen(),
                "freeze_remaining": max(0, self._freeze_until - time.time()),
                "check_count": self._check_count,
                "prices": snapshot.prices,
                "updated_at": snapshot.time_str,
            }
            redis.sync.set("etf_guard:state", json.dumps(state_data), ex=60)
        except Exception:
            pass

    def _publish_alert_to_redis(self, event: TriggerEvent):
        """Publish alert event to Redis for real-time dashboard notifications."""
        try:
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if not redis or not getattr(redis, 'sync', None):
                return
            
            import json
            alert = {
                "time": event.timestamp,
                "action": event.action.value,
                "triggers": event.triggers,
                "cancelled_buys": event.cancelled_buys,
                "cancelled_sells": event.cancelled_sells,
                "freeze_until": event.freeze_until,
            }
            redis.sync.set("etf_guard:last_alert", json.dumps(alert), ex=300)
            # Also publish to channel for real-time subscribers
            redis.sync.publish("etf_guard:alert", json.dumps(alert))
        except Exception:
            pass
