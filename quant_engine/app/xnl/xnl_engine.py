"""
XNL Engine - Automated Trading Cycle Manager

XNL Engine manages automated trading cycles with:
- Front Control Cycles (frontlama kontrolü)
- Refresh cycle KALDIRILDI: toptan iptal Dual Process veya manuel Cancel All ile yapılıyor.

Cycle Timing (by tag):
═══════════════════════════════════════════════════════════════════
FRONT CONTROL CYCLE:
    LT_*_INC (ADDNEWPOS)              : 3.5 minutes
    LT_*_DEC (LT_TRIM/KARBOTU/REDUCEMORE): 2 minutes
    MM_*_INC                          : 2 minutes (inactive)
    MM_*_DEC                          : 30 seconds (REV frontlama)

REFRESH CYCLE:
    LT_*_INC (ADDNEWPOS)              : 8 minutes
    LT_*_DEC (LT_TRIM/KARBOTU/REDUCEMORE): 5 minutes
    MM_*_INC                          : 3 minutes (inactive)
    MM_*_DEC                          : 1 minute (REV frontlama)
═══════════════════════════════════════════════════════════════════
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import time

from loguru import logger


class XNLState(Enum):
    """XNL Engine states"""
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"


class OrderTagCategory(Enum):
    """Order tag categories for cycle timing"""
    LT_INCREASE = "LT_INCREASE"  # ADDNEWPOS orders
    LT_DECREASE = "LT_DECREASE"  # LT_TRIM, KARBOTU, REDUCEMORE orders
    MM_INCREASE = "MM_INCREASE"  # MM new positions (inactive)
    MM_DECREASE = "MM_DECREASE"  # MM profit taking (inactive)


@dataclass
class CycleTiming:
    """Cycle timing configuration"""
    front_cycle_seconds: float
    refresh_cycle_seconds: float
    active: bool = True  # MM cycles are inactive by default


# Rate limit between order sends (seconds). ~15 orders/sec for both IBKR and Hammer.
ORDER_SEND_DELAY_SEC = 0.067  # ~15 orders/sec (1/15 ≈ 0.067)

# Cycle timing configuration
CYCLE_TIMINGS: Dict[OrderTagCategory, CycleTiming] = {
    OrderTagCategory.LT_INCREASE: CycleTiming(
        front_cycle_seconds=3.5 * 60,  # 3.5 minutes
        refresh_cycle_seconds=8 * 60,  # 8 minutes
        active=True
    ),
    OrderTagCategory.LT_DECREASE: CycleTiming(
        front_cycle_seconds=2 * 60,    # 2 minutes
        refresh_cycle_seconds=5 * 60,  # 5 minutes
        active=True
    ),
    OrderTagCategory.MM_INCREASE: CycleTiming(
        front_cycle_seconds=2 * 60,    # 2 minutes
        refresh_cycle_seconds=3 * 60,  # 3 minutes
        active=True  # MM active (controlled by settings)
    ),
    OrderTagCategory.MM_DECREASE: CycleTiming(
        front_cycle_seconds=30,        # 30 seconds
        refresh_cycle_seconds=60,      # 1 minute
        active=True  # MM DECREASE active — REV orders MUST be fronted after fills
    ),
}


@dataclass
class CycleState:
    """State for a single cycle type"""
    category: OrderTagCategory
    last_front_cycle: Optional[datetime] = None
    last_refresh_cycle: Optional[datetime] = None
    front_cycle_count: int = 0
    refresh_cycle_count: int = 0


@dataclass
class XNLEngineState:
    """Complete XNL Engine state"""
    state: XNLState = XNLState.STOPPED
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    cycle_states: Dict[OrderTagCategory, CycleState] = field(default_factory=dict)
    total_orders_sent: int = 0
    total_orders_cancelled: int = 0
    total_front_cycles: int = 0
    total_refresh_cycles: int = 0
    last_error: Optional[str] = None


class XNLEngine:
    """
    XNL Engine - Automated Trading Cycle Manager
    
    Flow:
    1. START: Run all engines (LT_TRIM → KARBOTU → PATADD → ADDNEWPOS → ACTMAN → MM)
    2. Send orders WITH frontlama check (before sending)
    3. Start cycle timers
    4. FRONT CYCLE: Check frontlama opportunities
    5. REFRESH CYCLE: Cancel + recalculate + resend orders
    """
    
    def __init__(self):
        self.state = XNLEngineState()
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        self._start_lock = asyncio.Lock()  # 🔒 Prevent concurrent start() calls
        self._active_account_id: Optional[str] = None  # 🔒 Pinned at start(), used by ALL cycles
        
        # Initialize cycle states
        for category in OrderTagCategory:
            self.state.cycle_states[category] = CycleState(category=category)
        
        logger.info("[XNL_ENGINE] Initialized")
    
    def _is_engine_active(self, engine_name: str) -> bool:
        """Check if an engine is in the active_engines list (Redis persisted)."""
        try:
            from app.core.redis_client import get_redis
            import json as _json
            redis = get_redis()
            if redis:
                raw = redis.get('psfalgo:active_engines')
                if raw:
                    engines = _json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    return engine_name in engines
            # Default: all engines active
            return True
        except Exception:
            return True
    
    def get_state(self) -> Dict[str, Any]:
        """Get current engine state as dict"""
        return {
            "state": self.state.state.value,
            "active_account_id": self._active_account_id,  # 🔒 Pinned at start()
            "started_at": self.state.started_at.isoformat() if self.state.started_at else None,
            "stopped_at": self.state.stopped_at.isoformat() if self.state.stopped_at else None,
            "total_orders_sent": self.state.total_orders_sent,
            "total_orders_cancelled": self.state.total_orders_cancelled,
            "total_front_cycles": self.state.total_front_cycles,
            "total_refresh_cycles": self.state.total_refresh_cycles,
            "last_error": self.state.last_error,
            "cycle_states": {
                cat.value: {
                    "last_front_cycle": cs.last_front_cycle.isoformat() if cs.last_front_cycle else None,
                    "last_refresh_cycle": cs.last_refresh_cycle.isoformat() if cs.last_refresh_cycle else None,
                    "front_cycle_count": cs.front_cycle_count,
                    "refresh_cycle_count": cs.refresh_cycle_count,
                    "timing": {
                        "front_seconds": CYCLE_TIMINGS[cat].front_cycle_seconds,
                        "refresh_seconds": CYCLE_TIMINGS[cat].refresh_cycle_seconds,
                        "active": CYCLE_TIMINGS[cat].active
                    }
                }
                for cat, cs in self.state.cycle_states.items()
            }
        }
    
    async def start(self) -> bool:
        """Start XNL Engine"""
        # 🔒 THREAD-SAFE: Prevent concurrent start() calls AND race with stop()
        # All critical state mutations MUST be inside the lock
        async with self._start_lock:
            if self.state.state in [XNLState.RUNNING, XNLState.STARTING]:
                logger.warning(f"[XNL_ENGINE] Already {self.state.state.value}")
                return False
            
            logger.info("=" * 80)
            logger.info("[XNL_ENGINE] 🚀 STARTING XNL ENGINE")
            logger.info("=" * 80)
            
            self.state.state = XNLState.STARTING
            self.state.started_at = datetime.now()
            self.state.stopped_at = None
            self._stop_event.clear()
            self._running = True
        
        try:
            # Set RUNNING immediately so UI can show Stop button and API returns quickly
            self.state.state = XNLState.RUNNING

            # 🔒 PIN ACCOUNT ID: Capture the active account AT START TIME.
            # All cycles (initial, front, refresh) use this pinned value.
            # This prevents cross-account contamination during dual process switching.
            from app.trading.trading_account_context import get_trading_context
            ctx = get_trading_context()
            self._active_account_id = ctx.trading_mode.value
            logger.info(f"[XNL_ENGINE] 🔒 Account pinned: {self._active_account_id}")

            # REV order sadece XNL run edildiğinde ve bu hesap için çalışsın: terminaller running + running_account'a bakacak
            try:
                from app.core.redis_client import get_redis_client
                r = get_redis_client()
                if r:
                    r.set("psfalgo:xnl:running", "1")
                    r.set("psfalgo:xnl:running_account", self._active_account_id)
                    logger.info(f"[XNL_ENGINE] Redis psfalgo:xnl:running=1, running_account={self._active_account_id} (REV terminals may place for this account only)")
            except Exception as e:
                logger.debug(f"[XNL_ENGINE] Redis xnl running flag: {e}")

            # Create cycle loop tasks first (they run on timers)
            for category, timing in CYCLE_TIMINGS.items():
                # Check MM settings if MM category
                if category == OrderTagCategory.MM_INCREASE:
                    from app.xnl.mm_settings import get_mm_settings_store
                    mm_settings = get_mm_settings_store().get_settings()
                    if not mm_settings.get('enabled', True):
                        logger.info("[XNL_ENGINE] MM cycles disabled in settings")
                        continue
                
                if timing.active:
                    # Front cycle task only. Refresh cycle KALDIRILDI: toptan cancel (Dual Process
                    # veya manuel Cancel All) kullanılıyor; kategori bazlı refresh yapılmıyor.
                    front_task = asyncio.create_task(
                        self._front_cycle_loop(category),
                        name=f"front_{category.value}"
                    )
                    self._tasks.append(front_task)
            
            logger.info(f"[XNL_ENGINE] Started {len(self._tasks)} cycle tasks (front only; no refresh cycle)")
            
            # Run initial cycle in background so POST /start returns immediately
            async def _run_initial_then_log():
                try:
                    await self._run_initial_cycle()
                except Exception as e:
                    logger.error(f"[XNL_ENGINE] Initial cycle failed: {e}", exc_info=True)
                    if self._running:
                        self.state.last_error = str(e)
            
            asyncio.create_task(_run_initial_then_log(), name="xnl_initial_cycle")
            return True
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] Start failed: {e}", exc_info=True)
            self.state.state = XNLState.STOPPED
            self.state.last_error = str(e)
            return False
    
    async def stop(self) -> bool:
        """Stop XNL Engine"""
        if self.state.state == XNLState.STOPPED:
            logger.warning("[XNL_ENGINE] Already stopped")
            return False
        
        logger.info("=" * 80)
        logger.info("[XNL_ENGINE] 🛑 STOPPING XNL ENGINE")
        logger.info("=" * 80)
        
        self.state.state = XNLState.STOPPING
        self._running = False
        self._stop_event.set()
        
        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
        
        self._tasks.clear()
        self.state.state = XNLState.STOPPED
        self.state.stopped_at = datetime.now()
        self._active_account_id = None  # 🔒 Clear pinned account

        # REV order: XNL durduğunda terminaller REV atmasın; hangi hesap bilgisi de temizlensin
        try:
            from app.core.redis_client import get_redis_client
            r = get_redis_client()
            if r:
                r.set("psfalgo:xnl:running", "0")
                r.set("psfalgo:xnl:running_account", "")
                logger.info("[XNL_ENGINE] Redis psfalgo:xnl:running=0, running_account cleared (REV terminals will not place)")
        except Exception as e:
            logger.debug(f"[XNL_ENGINE] Redis xnl running flag clear: {e}")

        # Stop RUNALL so no further cycles run (same "automated flow" as XNL)
        try:
            from app.psfalgo.runall_engine import get_runall_engine
            runall = get_runall_engine()
            await runall.stop()
            logger.info("[XNL_ENGINE] RUNALL loop also stopped")
        except Exception as e:
            logger.warning(f"[XNL_ENGINE] Could not stop RUNALL: {e}")
        
        logger.info("[XNL_ENGINE] Stopped successfully")
        return True
    
    async def _run_initial_cycle(self):
        """
        Run initial cycle using RUNALL's shared data layer (metrics, exposure, Janall).
        1. Prepare request via RunallEngine.prepare_cycle_request (same as RUNALL).
        2. LT_TRIM → KARBOTU/REDUCEMORE → ADDNEWPOS → MM, all use this request.
        3. Send orders WITH frontlama check (before sending).
        """
        logger.info("[XNL_ENGINE] Running initial cycle...")
        
        from app.psfalgo.runall_engine import get_runall_engine

        # 🔒 Use pinned account_id from start() — NOT get_trading_context()
        account_id = self._active_account_id
        if not account_id:
            from app.trading.trading_account_context import get_trading_context
            account_id = get_trading_context().trading_mode.value
            logger.warning(f"[XNL_ENGINE] _active_account_id was None, falling back to trading_context: {account_id}")
        logger.info(f"[XNL_ENGINE] Account: {account_id}")

        # Shared request = RUNALL's _prepare_request (positions, metrics, exposure, l1_data)
        correlation_id = f"xnl_cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        request = await get_runall_engine().prepare_cycle_request(account_id, correlation_id=correlation_id)
        if request is None:
            logger.warning("[XNL_ENGINE] Cycle request preparation failed (RUNALL preparer returned None), skipping initial cycle")
            return

        logger.info("[XNL_ENGINE] Using shared cycle request (metrics, exposure, Janall from RUNALL layer)")

        # Hard risk: cur >= max_cur_exp OR pot >= max_pot_exp → skip position increase (ADDNEWPOS, MM INC, REV saved)
        # V2: Account-aware thresholds (each account can have different max_cur_exp/max_pot_exp)
        #
        # IMPORTANT: During initial cycle (right after reqGlobalCancel), open orders
        # are still being cancelled by broker (~1-2s lag). Using get_current_and_potential_exposure_pct()
        # would include those stale orders and inflate potential exposure to 200-300%.
        # Instead, use request.exposure (from RUNALL preparer) which is position-based only.
        from app.psfalgo.exposure_threshold_service_v2 import get_exposure_threshold_service_v2
        thresh_svc = get_exposure_threshold_service_v2()
        
        if request.exposure and request.exposure.pot_max > 0:
            cur_pct = (request.exposure.pot_total / request.exposure.pot_max) * 100.0
            pot_pct = cur_pct  # No open orders in initial cycle (just cancelled)
        else:
            cur_pct = 0.0
            pot_pct = 0.0
        
        hard_risk = thresh_svc.is_hard_risk_mode(account_id, cur_pct, pot_pct)
        if hard_risk:
            logger.warning(
                f"[XNL_ENGINE] Hard risk mode: cur={cur_pct:.1f}% pot={pot_pct:.1f}% → "
                "skipping ADDNEWPOS, MM INC, REV saved; only decrease orders"
            )
        else:
            logger.info(
                f"[XNL_ENGINE] Exposure OK: cur={cur_pct:.1f}% pot={pot_pct:.1f}% "
                f"(pot_total=${request.exposure.pot_total:,.0f}/{request.exposure.pot_max:,.0f})"
            )

        # ═══════════════════════════════════════════════════════════════
        # CRITICAL: Refresh MinMax current_qty from REAL Redis positions
        # BEFORE any engine runs. Without this, engine-phase validations
        # use stale befday-initialized current_qty (e.g. current=0) while
        # SAFETY NET later reads fresh Redis (e.g. current=300 from fills).
        # This caused PATADD to approve BUY 500 with headroom=514,
        # then SAFETY NET to block it with headroom=14 (real current=500).
        # ═══════════════════════════════════════════════════════════════
        from app.psfalgo.minmax_area_service import get_minmax_area_service
        minmax_svc = get_minmax_area_service()
        minmax_svc.get_all_rows(account_id)  # Ensure daily bands are loaded
        self._refresh_minmax_current_qty(minmax_svc, account_id)
        logger.info(f"[XNL_ENGINE] MinMax current_qty refreshed from Redis for {account_id} (pre-engine)")

        # Reset REVERSE GUARD intra-cycle tracking (fresh start each cycle)
        from app.psfalgo.reverse_guard import reset_guard_tracking
        reset_guard_tracking()

        # Phase 1: LT_TRIM
        logger.info("[XNL_ENGINE] >>> Phase 1: LT_TRIM")
        lt_trim_orders = await self._run_lt_trim(account_id, request)

        # Phase 2: KARBOTU/REDUCEMORE
        logger.info("[XNL_ENGINE] >>> Phase 2: KARBOTU/REDUCEMORE")
        karbotu_orders = await self._run_karbotu(account_id, request)

        # Phase 2.5: PATADD — Pattern-based position increase (priority 17)
        # Runs BEFORE ADDNEWPOS; its symbols are excluded from ADDNEWPOS & MM.
        # Respects active_engines toggle from RUNALL checkbox UI.
        patadd_enabled_in_runall = self._is_engine_active('PATADD_ENGINE')
        if hard_risk:
            patadd_orders = []
            logger.info("[XNL_ENGINE] >>> Phase 2.5: PATADD skipped (hard risk)")
        elif not patadd_enabled_in_runall:
            patadd_orders = []
            logger.info("[XNL_ENGINE] >>> Phase 2.5: PATADD skipped (disabled in active_engines)")
        else:
            logger.info("[XNL_ENGINE] >>> Phase 2.5: PATADD")
            patadd_orders = await self._run_patadd(account_id, request)

        # Phase 3: ADDNEWPOS (es geçilir if hard risk OR disabled in active_engines)
        addnewpos_enabled_in_runall = self._is_engine_active('ADDNEWPOS_ENGINE')
        if hard_risk:
            addnewpos_orders = []
            logger.info("[XNL_ENGINE] >>> Phase 3: ADDNEWPOS skipped (hard risk)")
        elif not addnewpos_enabled_in_runall:
            addnewpos_orders = []
            logger.info("[XNL_ENGINE] >>> Phase 3: ADDNEWPOS skipped (disabled in active_engines)")
        else:
            logger.info("[XNL_ENGINE] >>> Phase 3: ADDNEWPOS")
            addnewpos_orders = await self._run_addnewpos(account_id, request)

        # ═══════════════════════════════════════════════════════════════
        # Phase 3.5: ACTMAN (Hedger + Panic)
        #
        # ACTMAN runs AFTER ADDNEWPOS but BEFORE MM.
        # Hedger: L/S drift correction (pasif/front, K3 at %15+ drift)
        # Panic:  ETF-driven emergency hedge (K3 aktif, freeze'de çalışır)
        #
        # ÖNCELİK: LT_TRIM > KARBOTU > PATADD > ADDNEWPOS > ACTMAN > MM
        # ACTMAN tag'ları: LT_ACTHEDGE_*_INC, LT_ACTPANIC_*_INC
        # ACTMAN claimed symbols → MM cannot INC on those symbols
        # ═══════════════════════════════════════════════════════════════
        actman_enabled_in_runall = self._is_engine_active('ACTMAN_ENGINE')
        actman_orders = []

        if hard_risk:
            logger.info("[XNL_ENGINE] >>> Phase 3.5: ACTMAN skipped (hard risk)")
        elif not actman_enabled_in_runall:
            logger.info("[XNL_ENGINE] >>> Phase 3.5: ACTMAN skipped (disabled in active_engines)")
        else:
            logger.info("[XNL_ENGINE] >>> Phase 3.5: ACTMAN (Hedger + Panic)")
            actman_orders = await self._run_actman(account_id, request)

        # ═══════════════════════════════════════════════════════════════
        # SYMBOL EXCLUSION: Bir hisse SADECE BIR motora ait olabilir.
        # Oncelik: LT_TRIM > KARBOTU > PATADD > ADDNEWPOS > ACTMAN > MM
        #
        # LT/KARBOTU/PATADD/ADDNEWPOS/ACTMAN emirleri once toplanir, bu
        # sembollerin listesi MM'e gonderilir. MM bu sembolleri ATLAR
        # ve top N secimini geri kalan havuzdan yapar.
        # ═══════════════════════════════════════════════════════════════
        
        # Collect symbols claimed by higher-priority engines
        lt_claimed: Set[str] = set()
        for batch in [lt_trim_orders, karbotu_orders, patadd_orders, addnewpos_orders, actman_orders]:
            for o in (batch or []):
                sym = str(o.get('symbol', '')).strip().upper()
                if (o.get('quantity') or 0) > 0:
                    lt_claimed.add(sym)
        
        if lt_claimed:
            logger.info(
                f"[XNL_ENGINE] SYMBOL EXCLUSION: {len(lt_claimed)} symbols claimed by "
                f"LT/KARBOTU/PATADD/ADDNEWPOS/ACTMAN — MM will skip these"
            )

        # ═══════════════════════════════════════════════════════════════
        # EXPOSURE DEDUCTION: PATADD/ADDNEWPOS INCREASE emirleri
        # exposure'dan düşülür → MM sadece KALAN exposure'ı kullanır.
        # Öncelik: PATADD > ADDNEWPOS > MM
        # ═══════════════════════════════════════════════════════════════
        patadd_addnewpos_inc_lots = 0
        patadd_addnewpos_inc_value = 0.0
        avg_price_for_deduction = 18.0  # fallback
        if request and request.exposure and request.exposure.pot_max > 0:
            try:
                from app.psfalgo.exposure_calculator import get_exposure_calculator
                exp_calc = get_exposure_calculator()
                if exp_calc and exp_calc.avg_price > 0:
                    avg_price_for_deduction = exp_calc.avg_price
            except:
                pass
            
            for batch_name, batch in [('PATADD', patadd_orders), ('ADDNEWPOS', addnewpos_orders), ('ACTMAN', actman_orders)]:
                for o in (batch or []):
                    qty = o.get('quantity') or 0
                    if qty <= 0:
                        continue
                    tag = str(o.get('tag', '') or '').upper()
                    action = str(o.get('action', '')).upper()
                    # Only count INCREASE orders (BUY/ADD/SHORT/ADD_SHORT with INC tag)
                    is_increase = 'INC' in tag or action in ('BUY', 'ADD', 'SHORT', 'ADD_SHORT')
                    if is_increase:
                        price = o.get('price') or avg_price_for_deduction
                        patadd_addnewpos_inc_lots += qty
                        patadd_addnewpos_inc_value += qty * price
            
            if patadd_addnewpos_inc_value > 0:
                old_pot = request.exposure.pot_total
                request.exposure.pot_total += patadd_addnewpos_inc_value
                # Recalculate mode
                try:
                    exp_calc = get_exposure_calculator()
                    if exp_calc:
                        request.exposure.mode = exp_calc.determine_exposure_mode(request.exposure)
                except:
                    pass
                logger.info(
                    f"[XNL_ENGINE] 💰 EXPOSURE DEDUCTION: PATADD+ADDNEWPOS committed "
                    f"{patadd_addnewpos_inc_lots} lots (${patadd_addnewpos_inc_value:,.0f}) → "
                    f"pot_total ${old_pot:,.0f} → ${request.exposure.pot_total:,.0f} "
                    f"(MM sees reduced free exposure)"
                )
                
                # Also patch FreeExposureEngine cache so MM's get_cached_snapshot() 
                # sees the reduced free capacity
                try:
                    from app.psfalgo.free_exposure_engine import get_free_exposure_engine
                    fee = get_free_exposure_engine()
                    cached = fee.get_cached_snapshot(account_id)
                    if cached and not cached.get('blocked'):
                        # Reduce BOTH current and potential, recalculate free values
                        # Current also increases because these orders will be placed immediately
                        cached['current'] = cached.get('current', 0) + patadd_addnewpos_inc_value
                        cached['potential'] = cached.get('potential', 0) + patadd_addnewpos_inc_value
                        max_cur = cached.get('max_cur', 1)
                        max_pot = cached.get('max_pot', 1)
                        cached['free_cur'] = max(0, max_cur - cached['current'])
                        cached['free_pot'] = max(0, max_pot - cached['potential'])
                        cached['free_cur_pct'] = round((cached['free_cur'] / max_cur * 100.0) if max_cur > 0 else 0.0, 1)
                        cached['free_pot_pct'] = round((cached['free_pot'] / max_pot * 100.0) if max_pot > 0 else 0.0, 1)
                        cached['effective_free_pct'] = round(min(cached['free_cur_pct'], cached['free_pot_pct']), 1)
                        # Re-determine tier
                        from app.psfalgo.free_exposure_engine import _tier_for_pct
                        divisor, tier_label = _tier_for_pct(cached['effective_free_pct'])
                        cached['divisor'] = divisor
                        cached['adv_divisor'] = divisor
                        cached['tier_label'] = tier_label
                        cached['blocked'] = divisor is None
                        logger.info(
                            f"[XNL_ENGINE] 📉 FreeExposure cache patched for {account_id}: "
                            f"cur_free={cached['free_cur_pct']:.1f}% pot_free={cached['free_pot_pct']:.1f}% "
                            f"effective={cached['effective_free_pct']:.1f}% "
                            f"blocked={cached['blocked']} tier={tier_label}"
                        )
                except Exception as fe_err:
                    logger.warning(f"[XNL_ENGINE] FreeExposure cache patch error: {fe_err}")

        # Phase 4: MM — runs with exclusion set so it backfills to target count
        # MM now sees REDUCED exposure after PATADD/ADDNEWPOS commitments
        #
        # ═══ PRIORITY GUARD ═══
        # Re-check exposure AFTER PATADD/ADDNEWPOS deduction.
        # If higher-priority engines consumed the budget, MM INC must be blocked.
        mm_blocked_by_priority = False
        if not hard_risk and request.exposure and request.exposure.pot_max > 0:
            updated_pct = (request.exposure.pot_total / request.exposure.pot_max) * 100.0
            mm_hard_risk = thresh_svc.is_hard_risk_mode(account_id, updated_pct, updated_pct)
            if mm_hard_risk:
                hard_risk = True  # Upgrade to hard_risk
                mm_blocked_by_priority = True
                logger.warning(
                    f"[XNL_ENGINE] ⚡ PRIORITY GUARD: PATADD/ADDNEWPOS consumed budget → "
                    f"exposure now {updated_pct:.1f}% → MM INC BLOCKED"
                )
        
        logger.info("[XNL_ENGINE] >>> Phase 4: MM")
        mm_orders = await self._run_mm(account_id, request, exclude_symbols=lt_claimed or None)
        if hard_risk and mm_orders:
            before = len(mm_orders)
            mm_orders = [o for o in mm_orders if o.get("category") == OrderTagCategory.MM_DECREASE]
            if before != len(mm_orders):
                logger.info(f"[XNL_ENGINE] MM INC orders dropped (hard risk{' — priority guard' if mm_blocked_by_priority else ''})")
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 3: LOT COORDINATION (LT engines) + SYMBOL EXCLUSION (MM)
        #
        # LT motorlari (LT_TRIM, KARBOTU, PATADD, ADDNEWPOS) ayni
        # hissede AYNI YONDE emir girerse → lot koordinasyonu:
        #   - Sonraki motor, onceki motorun lot'unu duser
        # FARKLI YONDE ayni hisseye emir girerse → bloklanir
        #
        # MM zaten exclude_symbols ile cagrildi, bu asamada sadece 
        # LT motorlari arasi koordinasyon yapiliyor.
        # ═══════════════════════════════════════════════════════════════
        
        # ── L/S RATIO LOT ADJUSTMENT (increase engines only) ──────────────
        # Adjust lots based on per-engine long/short allocation ratio.
        # Decrease engines (LT_TRIM, KARBOTU) are NOT affected.
        try:
            from app.xnl.ls_ratio_settings import get_ls_ratio_store
            ls_store = get_ls_ratio_store()
            
            for orders_list, engine_key in [
                (patadd_orders, 'PATADD_ENGINE'),
                (addnewpos_orders, 'ADDNEWPOS_ENGINE'),
            ]:
                if not orders_list:
                    continue
                for o in orders_list:
                    action = str(o.get('action', '')).upper()
                    # Determine direction from action
                    if action in ('BUY', 'ADD', 'COVER'):
                        direction = 'LONG'
                    elif action in ('SELL', 'SHORT', 'ADD_SHORT'):
                        direction = 'SHORT'
                    else:
                        continue
                    
                    orig_qty = o.get('quantity') or 0
                    if orig_qty <= 0:
                        continue
                    
                    adjusted = ls_store.apply_ratio_to_lot(
                        engine_key, direction, orig_qty,
                        min_lot=200, round_to=100
                    )
                    if adjusted != orig_qty:
                        ratio = ls_store.get_ratio(engine_key)
                        logger.info(
                            f"[XNL_ENGINE] LS_RATIO {engine_key}: {o.get('symbol')} "
                            f"{direction} {orig_qty}→{adjusted} "
                            f"(L={ratio['long_pct']}%/S={ratio['short_pct']}%)"
                        )
                        o['quantity'] = adjusted
        except Exception as e:
            logger.warning(f"[XNL_ENGINE] L/S ratio adjustment error (continuing without): {e}")

        # Track claims per symbol: {SYMBOL: {action: str, total_qty: int, engine: str}}
        symbol_claims: Dict[str, Dict[str, Any]] = {}
        all_orders: List[Dict[str, Any]] = []
        
        lt_batches = [
            (lt_trim_orders, "LT_TRIM"),
            (karbotu_orders, "KARBOTU"),
            (patadd_orders, "PATADD"),
            (addnewpos_orders, "ADDNEWPOS"),
            (actman_orders, "ACTMAN"),
        ]
        
        def _normalize_action(raw_action: str) -> str:
            """Normalize action: BUY/ADD/COVER → BUY, SELL/SHORT/ADD_SHORT → SELL"""
            a = raw_action.upper()
            if a in ('BUY', 'ADD', 'COVER'):
                return 'BUY'
            if a in ('SELL', 'SHORT', 'ADD_SHORT'):
                return 'SELL'
            return a
        
        for batch, engine_name in lt_batches:
            if not batch:
                continue
            for o in batch:
                sym = str(o.get('symbol', '')).strip().upper()
                qty = o.get('quantity') or 0
                action = _normalize_action(str(o.get('action', '')))
                if qty <= 0:
                    continue
                
                if sym in symbol_claims:
                    existing = symbol_claims[sym]
                    if existing['action'] == action:
                        # AYNI YON: Lot koordinasyonu — kalan lot'u yaz
                        remaining = qty - existing['total_qty']
                        if remaining > 0:
                            adjusted_order = dict(o)
                            adjusted_order['quantity'] = remaining
                            all_orders.append(adjusted_order)
                            symbol_claims[sym]['total_qty'] += remaining
                            logger.info(
                                f"[XNL_ENGINE] LOT COORD: {sym} {action} "
                                f"from {engine_name}: {qty}→{remaining} "
                                f"(already {existing['total_qty']-remaining} by {existing['engine']})"
                            )
                        else:
                            logger.info(
                                f"[XNL_ENGINE] LOT COORD: {sym} {action} "
                                f"from {engine_name}: {qty} lot SKIPPED — "
                                f"already {existing['total_qty']} by {existing['engine']}"
                            )
                    else:
                        # FARKLI YÖN: Spread-based conflict resolution
                        # ─────────────────────────────────────────────
                        # MM always loses to any other engine (lowest priority)
                        # Between non-MM engines (LT_TRIM, KARBOTU, PATADD, ADDNEWPOS):
                        #   Allow both BUY+SELL if the price gap >= $0.08
                        #   This enables simultaneous increase+decrease on wide-spread symbols
                        is_mm_new = 'MM' in engine_name.upper()
                        is_mm_existing = 'MM' in existing['engine'].upper()
                        
                        if is_mm_new:
                            # MM always blocked by any other engine
                            logger.info(
                                f"[XNL_ENGINE] DIRECTION CONFLICT: {sym} "
                                f"MM wants {action} but {existing['engine']} "
                                f"already has {existing['action']} — MM BLOCKED (lowest priority)"
                            )
                        elif is_mm_existing:
                            # New non-MM engine overrides MM
                            logger.info(
                                f"[XNL_ENGINE] DIRECTION OVERRIDE: {sym} "
                                f"{engine_name} wants {action} — replacing MM's {existing['action']}"
                            )
                            # Remove MM order, add new one
                            all_orders[:] = [
                                x for x in all_orders
                                if str(x.get('symbol', '')).strip().upper() != sym
                            ]
                            symbol_claims[sym] = {
                                'action': action,
                                'total_qty': qty,
                                'engine': engine_name,
                            }
                            all_orders.append(o)
                        else:
                            # Both are non-MM engines — check spread
                            new_price = float(o.get('price') or o.get('limit_price') or 0)
                            existing_price = existing.get('price', 0)
                            price_gap = abs(new_price - existing_price) if new_price > 0 and existing_price > 0 else 0
                            
                            if price_gap >= 0.08:
                                # Wide enough spread — allow both directions
                                all_orders.append(o)
                                logger.info(
                                    f"[XNL_ENGINE] DUAL DIRECTION ALLOWED: {sym} "
                                    f"{engine_name} {action}@${new_price:.2f} + "
                                    f"{existing['engine']} {existing['action']}@${existing_price:.2f} "
                                    f"| gap=${price_gap:.2f} >= $0.08 — BOTH KEPT"
                                )
                            else:
                                # Spread too narrow — higher priority engine wins
                                logger.warning(
                                    f"[XNL_ENGINE] DIRECTION CONFLICT: {sym} "
                                    f"{engine_name} wants {action}@${new_price:.2f} but "
                                    f"{existing['engine']} already has {existing['action']}@${existing_price:.2f} "
                                    f"| gap=${price_gap:.2f} < $0.08 — BLOCKED"
                                )
                else:
                    # Ilk kez bu sembole emir giriyor
                    symbol_claims[sym] = {
                        'action': action,
                        'total_qty': qty,
                        'engine': engine_name,
                        'price': float(o.get('price') or o.get('limit_price') or 0),
                    }
                    all_orders.append(o)
        
        # ── L/S RATIO for MM orders (only INC, not DEC/REV) ──────────
        try:
            from app.xnl.ls_ratio_settings import get_ls_ratio_store as _get_ls_mm
            ls_store_mm = _get_ls_mm()
            for o in (mm_orders or []):
                tag = str(o.get('tag', '') or o.get('strategy_tag', '') or '').upper()
                # Only adjust INC orders, skip DEC/REV
                if 'INC' not in tag:
                    continue
                action = str(o.get('action', '')).upper()
                if action in ('BUY', 'ADD', 'COVER'):
                    direction = 'LONG'
                elif action in ('SELL', 'SHORT', 'ADD_SHORT'):
                    direction = 'SHORT'
                else:
                    continue
                orig_qty = o.get('quantity') or 0
                if orig_qty <= 0:
                    continue
                adjusted = ls_store_mm.apply_ratio_to_lot(
                    'MM_ENGINE', direction, orig_qty,
                    min_lot=200, round_to=100
                )
                if adjusted != orig_qty:
                    ratio = ls_store_mm.get_ratio('MM_ENGINE')
                    logger.info(
                        f"[XNL_ENGINE] LS_RATIO MM: {o.get('symbol')} "
                        f"{direction} {orig_qty}→{adjusted} "
                        f"(L={ratio['long_pct']}%/S={ratio['short_pct']}%)"
                    )
                    o['quantity'] = adjusted
        except Exception as e:
            logger.warning(f"[XNL_ENGINE] MM L/S ratio error (continuing): {e}")

        # ── MM SIGNAL DIRECTION GUARD ──────────────────────────────────
        # KURAL: ADDNEWPOS/PATADD LONG sinyali varsa → MM SHORT açamaz
        #        ADDNEWPOS/PATADD SHORT sinyali varsa → MM LONG açamaz
        # Bu kural MM'in stratejik pozisyon engine'lerimize ters düşmesini engeller
        lt_signal_directions: Dict[str, str] = {}  # {SYMBOL: 'BUY' or 'SELL'}
        for batch, eng_name in [(patadd_orders, 'PATADD'), (addnewpos_orders, 'ADDNEWPOS')]:
            if not batch:
                continue
            for o in batch:
                sym = str(o.get('symbol', '')).strip().upper()
                act = _normalize_action(str(o.get('action', '')))
                tag = str(o.get('tag', '') or o.get('strategy_tag', '') or '').upper()
                # Only track INC (position increase) signals, not DEC
                if 'INC' in tag or act in ('BUY', 'SELL', 'SHORT', 'ADD', 'ADD_SHORT'):
                    if sym and act in ('BUY', 'SELL'):
                        lt_signal_directions[sym] = act
        
        if lt_signal_directions:
            logger.info(
                f"[XNL_ENGINE] MM SIGNAL GUARD: {len(lt_signal_directions)} symbols with "
                f"ADDNEWPOS/PATADD signals → {lt_signal_directions}"
            )
        
        # MM orders — already filtered by exclude_symbols, now also check signal guard
        for o in (mm_orders or []):
            sym = str(o.get('symbol', '')).strip().upper()
            qty = o.get('quantity') or 0
            if qty <= 0:
                continue
            if sym in symbol_claims:
                # This shouldn't happen since MM was called with exclude_symbols,
                # but guard against edge cases
                logger.warning(
                    f"[XNL_ENGINE] MM SAFETY BLOCK: {sym} — "
                    f"already claimed by {symbol_claims[sym]['engine']}"
                )
                continue
            
            # ── SIGNAL DIRECTION GUARD ──
            mm_action = _normalize_action(str(o.get('action', '')))
            mm_tag = str(o.get('tag', '') or o.get('strategy_tag', '') or '').upper()
            is_mm_inc = 'INC' in mm_tag  # Only block INC orders, not DEC
            
            if is_mm_inc and sym in lt_signal_directions:
                lt_dir = lt_signal_directions[sym]
                if lt_dir == 'BUY' and mm_action == 'SELL':
                    # ADDNEWPOS/PATADD says LONG → MM cannot SHORT
                    logger.warning(
                        f"[XNL_ENGINE] MM SIGNAL GUARD BLOCK: {sym} — "
                        f"ADDNEWPOS/PATADD has LONG signal, MM SHORT BLOCKED"
                    )
                    continue
                elif lt_dir == 'SELL' and mm_action == 'BUY':
                    # ADDNEWPOS/PATADD says SHORT → MM cannot LONG
                    logger.warning(
                        f"[XNL_ENGINE] MM SIGNAL GUARD BLOCK: {sym} — "
                        f"ADDNEWPOS/PATADD has SHORT signal, MM LONG BLOCKED"
                    )
                    continue
            
            symbol_claims[sym] = {
                'action': mm_action,
                'total_qty': qty,
                'engine': 'MM',
            }
            all_orders.append(o)
        
        logger.info(
            f"[XNL_ENGINE] Total orders: {len(all_orders)} "
            f"({len(symbol_claims)} unique symbols, "
            f"priority: LT_TRIM>KARBOTU>PATADD>ADDNEWPOS>ACTMAN>MM)"
        )
        
        # ═══════════════════════════════════════════════════════════════
        # Phase 5: NEWCLMM — Truth Tick Spread Capture (PAPER by default)
        # Runs AFTER all other engines. In PAPER mode: only logs.
        # In LIVE mode: creates real orders with MinMax validation.
        # ═══════════════════════════════════════════════════════════════
        logger.info("[XNL_ENGINE] >>> Phase 5: NEWCLMM")
        newclmm_orders = await self._run_newclmm(account_id, request, exclude_symbols=set(symbol_claims.keys()))
        if newclmm_orders:
            # Only add to all_orders if engine is ENABLED (live mode)
            for o in newclmm_orders:
                sym = str(o.get('symbol', '')).strip().upper()
                if sym not in symbol_claims:
                    symbol_claims[sym] = {
                        'action': str(o.get('action', '')).upper(),
                        'total_qty': o.get('quantity', 0),
                        'engine': 'NEWCLMM',
                    }
                    all_orders.append(o)
                else:
                    logger.info(
                        f"[XNL_ENGINE] NEWCLMM {sym} BLOCKED — "
                        f"already claimed by {symbol_claims[sym]['engine']}"
                    )
        
        await self._write_proposals_to_store(lt_trim_orders, karbotu_orders, patadd_orders, addnewpos_orders, mm_orders)
        
        if all_orders:
            await self._send_orders_with_frontlama(all_orders, account_id)
        
        # Initialize cycle timestamps
        now = datetime.now()
        for category in OrderTagCategory:
            self.state.cycle_states[category].last_front_cycle = now
            self.state.cycle_states[category].last_refresh_cycle = now
        
        logger.info("[XNL_ENGINE] Initial cycle complete")
    
    async def _run_lt_trim(self, account_id: str, request) -> List[Dict[str, Any]]:
        """Run LT_TRIM engine using shared cycle request (metrics, exposure from RUNALL layer)."""
        orders = []
        try:
            from app.event_driven.decision_engine.lt_trim_engine import get_lt_trim_engine
            from app.state.runtime_controls import get_runtime_controls_manager
            
            if not request or not getattr(request, 'positions', None):
                logger.info("[XNL_ENGINE] No positions for LT_TRIM")
                return orders
            
            lt_engine = get_lt_trim_engine()
            controls_manager = get_runtime_controls_manager()
            controls = controls_manager.get_controls(account_id)
            
            intents, diagnostic = await lt_engine.run(
                request=request,
                karbotu_signals={},
                reducemore_multipliers={},
                rules={},
                controls=controls,
                account_id=account_id
            )
            
            for intent in intents:
                # Check L1 data before creating order (same logic as MM)
                l1_data = await self._get_l1_data(intent.symbol)
                if not l1_data:
                    logger.warning(f"[XNL_ENGINE] No L1 data for {intent.symbol}, skipping")
                    continue
                
                action = getattr(intent, 'action', getattr(intent, 'side', 'SELL'))
                qty = getattr(intent, 'qty', getattr(intent, 'quantity', 0))
                qty = int(qty) if qty else 0
                price = getattr(intent, 'price', None) or (getattr(intent, 'metadata', {}) or {}).get('price')
                tag = getattr(intent, 'classification', None)
                if not tag:
                    _pos_tag = 'LT'
                    try:
                        from app.psfalgo.position_tag_store import get_position_tag_store
                        _store = get_position_tag_store()
                        if _store:
                            _pos_tag = _store.get_tag(intent.symbol, account_id)
                    except Exception:
                        pass
                    # Extract stage number from reason (e.g. "LT_STAGE_2" → "S2")
                    _stage_suffix = ""
                    _reason = getattr(intent, 'reason', '') or ''
                    if 'STAGE_4' in _reason or 'STAGE4' in _reason:
                        _stage_suffix = "_S4"
                    elif 'STAGE_3' in _reason or 'STAGE3' in _reason:
                        _stage_suffix = "_S3"
                    elif 'STAGE_2' in _reason or 'STAGE2' in _reason:
                        _stage_suffix = "_S2"
                    elif 'STAGE_1' in _reason or 'STAGE1' in _reason:
                        _stage_suffix = "_S1"
                    tag = f"{_pos_tag}_TRIM_{'LONG' if action == 'SELL' else 'SHORT'}_DEC{_stage_suffix}"
                
                # MinMax Validation — LT_TRIM must also respect daily limits
                if qty > 0:
                    from app.psfalgo.minmax_area_service import (
                        get_minmax_area_service,
                        validate_order_against_minmax,
                        update_minmax_cache_after_order,
                    )
                    minmax_svc = get_minmax_area_service()
                    minmax_row = minmax_svc.get_row(account_id, intent.symbol)
                    current_qty = minmax_row.current_qty if minmax_row else 0.0
                    mma_allowed, mma_qty, mma_reason = validate_order_against_minmax(
                        account_id, intent.symbol, action, qty,
                        current_qty, minmax_row=minmax_row, minmax_service=minmax_svc,
                    )
                    if not mma_allowed:
                        logger.info(
                            f"[XNL_ENGINE] LT_TRIM {intent.symbol} {action} {qty} "
                            f"blocked by MinMax: {mma_reason}"
                        )
                        continue
                    if mma_qty != qty:
                        logger.info(
                            f"[XNL_ENGINE] LT_TRIM {intent.symbol} trimmed by MinMax: "
                            f"{qty} -> {mma_qty} ({mma_reason})"
                        )
                        qty = mma_qty
                    # Update MinMax cache for intra-cycle consistency
                    update_minmax_cache_after_order(minmax_svc, intent.symbol, action, qty)
                
                orders.append({
                    'symbol': intent.symbol,
                    'action': action,
                    'quantity': qty,
                    'price': float(price) if price is not None else None,
                    'tag': tag,
                    'source': 'LT_TRIM',
                    'category': OrderTagCategory.LT_DECREASE
                })
            
            for o in orders:
                _sym = o['symbol']
                _m = request.metrics.get(_sym) if hasattr(request, 'metrics') and request.metrics else None
                _ms = ""
                if _m:
                    _ms = (
                        f" | fbtot={_m.fbtot} sfstot={_m.sfstot} gort={_m.gort} "
                        f"ucuz={_m.bid_buy_ucuzluk} pah={_m.ask_sell_pahalilik} "
                        f"bid={_m.bid} ask={_m.ask} last={_m.last} "
                        f"son5={_m.son5_tick} v1h={_m.volav_1h} v4h={_m.volav_4h}"
                    )
                logger.info(
                    f"[XNL_ENGINE] LT_TRIM ORDER: {_sym} {o['action']} "
                    f"{o['quantity']} @ ${o.get('price', 0) or 0:.2f} "
                    f"tag={o['tag']}{_ms}"
                )
            logger.info(f"[XNL_ENGINE] LT_TRIM generated {len(orders)} orders")
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] LT_TRIM error: {e}", exc_info=True)
        
        return orders
    
    async def _run_karbotu(self, account_id: str, request) -> List[Dict[str, Any]]:
        """Run KARBOTU engine using shared cycle request (metrics, exposure from RUNALL layer)."""
        orders = []
        try:
            from app.psfalgo.karbotu_engine_v2 import get_karbotu_engine_v2
            from app.psfalgo.reducemore_engine_v2 import get_reducemore_engine_v2
            from app.xnl.heavy_settings_store import get_heavy_settings_store
            
            if not request or not getattr(request, 'positions', None):
                logger.info("[XNL_ENGINE] No positions for KARBOTU")
                return orders
            
            # Get HEAVY mode settings for this specific account
            heavy_store = get_heavy_settings_store()
            heavy_settings = heavy_store.get_settings(account_id)
            
            reducemore_v2 = get_reducemore_engine_v2()
            mode_result = await reducemore_v2.run(request)
            exposure_mode = mode_result.get('mode', 'Unknown')
            
            logger.info(f"[XNL_ENGINE] Exposure mode: {exposure_mode}, HEAVY: long={heavy_settings.heavy_long_dec}, short={heavy_settings.heavy_short_dec}")
            
            # KARBOTU is a DECREASE-only engine (position reduction) and must run in ALL modes.
            # In OFANSIF: selective selling based on step/signal analysis
            # In GEÇIŞ: both KARBOTU (selective) and REDUCEMORE (aggressive) contribute
            # In DEFANSIVE: KARBOTU continues to actively reduce positions (critical for risk reduction)
            # Only INCREASE engines (MM INC, PATADD, ADDNEWPOS) are blocked in DEFANSIVE mode.
            if exposure_mode in ('OFANSIF', 'GEÇIŞ', 'DEFANSIVE') or heavy_settings.heavy_long_dec or heavy_settings.heavy_short_dec:
                karbotu_v2 = get_karbotu_engine_v2()
                output = await karbotu_v2.run(request, controls=heavy_settings, account_id=account_id)  # Pass heavy_settings as controls
                
                # MinMax pre-validation
                from app.psfalgo.minmax_area_service import (
                    get_minmax_area_service,
                    validate_order_against_minmax,
                    update_minmax_cache_after_order,
                )
                minmax_svc = get_minmax_area_service()
                minmax_svc.get_all_rows(account_id)
                
                for dec in output.decisions:
                    # Check L1 data before creating order (same logic as MM)
                    l1_data = await self._get_l1_data(dec.symbol)
                    if not l1_data:
                        logger.warning(f"[XNL_ENGINE] No L1 data for {dec.symbol}, skipping")
                        continue
                    
                    qty = dec.qty
                    action = dec.action
                    
                    # MinMax Validation
                    if qty > 0:
                        minmax_row = minmax_svc.get_row(account_id, dec.symbol)
                        current_qty = minmax_row.current_qty if minmax_row else 0.0
                        mma_allowed, mma_qty, mma_reason = validate_order_against_minmax(
                            account_id, dec.symbol, action, qty,
                            current_qty, minmax_row=minmax_row, minmax_service=minmax_svc,
                        )
                        if not mma_allowed:
                            logger.info(
                                f"[XNL_ENGINE] KARBOTU {dec.symbol} {action} {qty} "
                                f"blocked by MinMax: {mma_reason}"
                            )
                            continue
                        if mma_qty != qty:
                            logger.info(
                                f"[XNL_ENGINE] KARBOTU {dec.symbol} trimmed by MinMax: "
                                f"{qty} -> {mma_qty} ({mma_reason})"
                            )
                            qty = mma_qty
                        # Update MinMax cache for intra-cycle consistency
                        update_minmax_cache_after_order(minmax_svc, dec.symbol, action, qty)
                    
                    orders.append({
                        'symbol': dec.symbol,
                        'action': action,
                        'quantity': qty,
                        'price': None,  # Will be calculated
                        'tag': dec.tag,
                        'source': 'KARBOTU',
                        'category': OrderTagCategory.LT_DECREASE
                    })
            
            for o in orders:
                _sym = o['symbol']
                _m = request.metrics.get(_sym) if hasattr(request, 'metrics') and request.metrics else None
                _ms = ""
                if _m:
                    _ms = (
                        f" | fbtot={_m.fbtot} sfstot={_m.sfstot} gort={_m.gort} "
                        f"ucuz={_m.bid_buy_ucuzluk} pah={_m.ask_sell_pahalilik} "
                        f"bid={_m.bid} ask={_m.ask} last={_m.last} "
                        f"son5={_m.son5_tick} v1h={_m.volav_1h} v4h={_m.volav_4h}"
                    )
                logger.info(
                    f"[XNL_ENGINE] KARBOTU ORDER: {_sym} {o['action']} "
                    f"{o['quantity']} tag={o['tag']}{_ms}"
                )
            logger.info(f"[XNL_ENGINE] KARBOTU generated {len(orders)} orders")
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] KARBOTU error: {e}", exc_info=True)
        
        return orders
    
    async def _run_addnewpos(self, account_id: str, request) -> List[Dict[str, Any]]:
        """Run ADDNEWPOS engine using shared cycle request (metrics, exposure, available_symbols from RUNALL layer)."""
        orders = []
        try:
            from app.xnl.addnewpos_settings_v2 import get_addnewpos_settings_store
            from app.psfalgo.addnewpos_engine import get_addnewpos_engine, initialize_addnewpos_engine
            
            settings_store = get_addnewpos_settings_store()
            settings = settings_store.get_settings(account_id)  # Account-specific!
            
            if not settings.get('enabled', True):
                logger.info("[XNL_ENGINE] ADDNEWPOS disabled in settings")
                return orders
            
            if not request:
                logger.info("[XNL_ENGINE] No cycle request for ADDNEWPOS")
                return orders
            
            # Run ADDNEWPOS (request already has positions, metrics, exposure, available_symbols)
            addnewpos_engine = get_addnewpos_engine()
            if addnewpos_engine is None:
                logger.warning("[XNL_ENGINE] ADDNEWPOS engine not initialized, initializing now...")
                addnewpos_engine = initialize_addnewpos_engine()
            
            if addnewpos_engine is None:
                logger.error("[XNL_ENGINE] Failed to initialize ADDNEWPOS engine")
                return orders
            
            # AddnewposEngine uses addnewpos_decision_engine method, not run
            response = await addnewpos_engine.addnewpos_decision_engine(request)
            
            # Get per-tab settings
            tab_settings = {
                'BB': settings.get('tab_bb', {}),
                'FB': settings.get('tab_fb', {}),
                'SAS': settings.get('tab_sas', {}),
                'SFS': settings.get('tab_sfs', {})
            }
            
            # Apply settings filters and JFIN percentage
            for dec in response.decisions:
                if dec.filtered_out:
                    continue
                
                # Check mode (both/addlong_only/addshort_only)
                mode = settings.get('mode', 'both')
                if mode == 'addlong_only' and dec.action not in ('BUY', 'ADD'):
                    continue
                if mode == 'addshort_only' and dec.action not in ('SELL', 'SHORT', 'ADD_SHORT'):
                    continue
                
                # Determine pool (BB/FB/SAS/SFS) from order_type
                pool = None
                order_type = getattr(dec, 'order_type', '')
                if order_type == 'BID_BUY':
                    pool = 'BB'
                elif order_type == 'FRONT_BUY':
                    pool = 'FB'
                elif order_type == 'ASK_SELL':
                    pool = 'SAS'
                elif order_type == 'FRONT_SELL':
                    pool = 'SFS'
                else:
                    # Fallback: infer from action
                    if dec.action in ('BUY', 'ADD'):
                        pool = 'BB'  # Default to BB for BUY/ADD
                    elif dec.action in ('SELL', 'SHORT', 'ADD_SHORT'):
                        pool = 'SAS'  # Default to SAS for SELL/SHORT/ADD_SHORT
                
                if not pool:
                    logger.warning(f"[XNL_ENGINE] Cannot determine pool for {dec.symbol}, skipping")
                    continue
                
                # Get JFIN percentage for this pool
                pool_settings = tab_settings.get(pool, {})
                jfin_pct = pool_settings.get('jfin_pct', 50)
                
                # Skip if JFIN is 0% (this pool disabled)
                if jfin_pct == 0:
                    logger.debug(f"[XNL_ENGINE] {pool} pool disabled (JFIN=0%), skipping {dec.symbol}")
                    continue
                
                # Apply JFIN percentage AND MAXALW/4 per-order cap
                # Formula: final_lot = min(RECSIZE × JFIN%, MAXALW/4), min 200
                original_lot = dec.calculated_lot or 0
                jfin_lot = int(original_lot * (jfin_pct / 100.0))
                
                # MAXALW/4 cap: tek emirde en fazla MAXALW'un 1/4'ü
                maxalw = getattr(
                    request.metrics.get(dec.symbol) if hasattr(request, 'metrics') and request.metrics else None,
                    'maxalw', None
                )
                if maxalw and maxalw > 0:
                    per_order_cap = int(maxalw / 4)
                    if per_order_cap > 0:
                        final_lot = min(jfin_lot, per_order_cap)
                    else:
                        final_lot = jfin_lot
                else:
                    final_lot = jfin_lot
                
                # Ensure min 200 lot
                if final_lot > 0 and final_lot < 200:
                    final_lot = 200
                
                if final_lot <= 0:
                    logger.debug(f"[XNL_ENGINE] {dec.symbol} lot becomes 0 after JFIN {jfin_pct}%, skipping")
                    continue
                
                # Check L1 data before creating order (same logic as MM)
                l1_data = await self._get_l1_data(dec.symbol)
                if not l1_data:
                    logger.warning(f"[XNL_ENGINE] No L1 data for {dec.symbol}, skipping")
                    continue
                
                # MinMax Validation
                from app.psfalgo.minmax_area_service import (
                    get_minmax_area_service,
                    validate_order_against_minmax,
                    update_minmax_cache_after_order,
                )
                minmax_svc = get_minmax_area_service()
                minmax_row = minmax_svc.get_row(account_id, dec.symbol)
                current_qty = minmax_row.current_qty if minmax_row else 0.0
                # Normalize action for MinMax: SHORT/ADD_SHORT → SELL
                minmax_action = 'SELL' if dec.action in ('SHORT', 'ADD_SHORT') else dec.action
                mma_allowed, mma_qty, mma_reason = validate_order_against_minmax(
                    account_id, dec.symbol, minmax_action, final_lot,
                    current_qty, minmax_row=minmax_row, minmax_service=minmax_svc,
                )
                if not mma_allowed:
                    logger.info(
                        f"[XNL_ENGINE] ADDNEWPOS {dec.symbol} {dec.action} {final_lot} "
                        f"blocked by MinMax: {mma_reason}"
                    )
                    continue
                if mma_qty != final_lot:
                    logger.info(
                        f"[XNL_ENGINE] ADDNEWPOS {dec.symbol} trimmed by MinMax: "
                        f"{final_lot} -> {mma_qty} ({mma_reason})"
                    )
                    final_lot = mma_qty
                # Update MinMax cache for intra-cycle consistency
                update_minmax_cache_after_order(minmax_svc, dec.symbol, minmax_action, final_lot)
                
                logger.debug(
                    f"[XNL_ENGINE] {dec.symbol} ({pool}): "
                    f"RECSIZE={original_lot} × JFIN{jfin_pct}%={jfin_lot} "
                    f"MAXALW/4={'N/A' if not maxalw else int(maxalw/4)} "
                    f"→ final={final_lot}"
                )
                
                # v4 tag: ALWAYS LT_AN_{DIR}_INC — AN/PA always convert position to LT
                # (same dir: MM→LT transition | opposite dir: OZEL closes first, then clean LT)
                _an_dir = 'LONG' if dec.action in ('BUY', 'ADD') else 'SHORT'
                orders.append({
                    'symbol': dec.symbol,
                    'action': dec.action,
                    'quantity': final_lot,
                    'price': dec.price_hint,
                    'tag': f"LT_AN_{_an_dir}_INC",
                    'source': 'ADDNEWPOS',
                    'category': OrderTagCategory.LT_INCREASE,
                    'pool': pool,
                    'jfin_pct': jfin_pct
                })
            long_orders = [o for o in orders if o['action'] in ('BUY', 'ADD')]
            short_orders = [o for o in orders if o['action'] not in ('BUY', 'ADD')]
            logger.info(
                f"[XNL_ENGINE] ADDNEWPOS generated {len(orders)} orders "
                f"(LONG={len(long_orders)}, SHORT={len(short_orders)}) after JFIN filtering"
            )
            for o in orders:
                # Get metrics for this symbol from request
                _sym = o['symbol']
                _m = request.metrics.get(_sym) if hasattr(request, 'metrics') and request.metrics else None
                _metrics_str = ""
                if _m:
                    _metrics_str = (
                        f" | fbtot={_m.fbtot} sfstot={_m.sfstot} gort={_m.gort} "
                        f"ucuz={_m.bid_buy_ucuzluk} pah={_m.ask_sell_pahalilik} "
                        f"bid={_m.bid} ask={_m.ask} last={_m.last} "
                        f"son5={_m.son5_tick} v1h={_m.volav_1h} v4h={_m.volav_4h}"
                    )
                logger.info(
                    f"[XNL_ENGINE] ADDNEWPOS ORDER: {_sym} {o['action']} "
                    f"{o['quantity']} @ ${o.get('price', 0) or 0:.2f} "
                    f"tag={o['tag']} pool={o.get('pool', '?')}{_metrics_str}"
                )
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] ADDNEWPOS error: {e}", exc_info=True)
        
        return orders

    async def _run_actman(self, account_id: str, request) -> List[Dict[str, Any]]:
        """
        Run ACTMAN engine — Active Manager for L/S hedge and panic response.

        Phase 3.5: After ADDNEWPOS, before MM.
        Priority: LT_TRIM > KARBOTU > PATADD > ADDNEWPOS > ACTMAN > MM

        Two sub-engines:
          1. HEDGER: Gap-driven L/S rebalancing (K1 pasif / K2 front / K3 at %15+)
          2. PANIC:  ETF-driven emergency hedge (K3 aktif, works during freeze)

        Tag format: LT_ACTHEDGE_SHORT_INC, LT_ACTPANIC_LONG_INC etc.
        All tags start with LT_ → REV v3 compatible → automatic TP/RL

        Position data comes from request.positions (same as other engines).
        Config comes from actman_config.py + Redis settings if available.
        """
        orders: List[Dict[str, Any]] = []
        try:
            from app.actman.actman_hedger_engine import ActmanHedgerEngine
            from app.actman.actman_panic_engine import ActmanPanicEngine
            from app.actman.actman_config import (
                HEDGER_ENABLED, PANIC_ENABLED,
                HEDGER_CONFIG_LONG_PCT,
            )

            if not request or not getattr(request, 'positions', None):
                logger.info("[XNL_ENGINE] ACTMAN: No positions available")
                return orders

            # ── Build L/S portfolio state from positions ──
            positions = request.positions if isinstance(request.positions, list) else []
            total_long = 0
            total_short = 0
            long_by_group = {}
            short_by_group = {}

            for pos in positions:
                # PositionSnapshot is a DATACLASS — use attribute access, NOT .get()
                sym = getattr(pos, 'symbol', '')
                raw_qty = getattr(pos, 'qty', 0) or 0
                qty = abs(raw_qty)
                # Side determined by qty sign: positive = LONG, negative = SHORT
                if raw_qty > 0:
                    side = 'LONG'
                elif raw_qty < 0:
                    side = 'SHORT'
                else:
                    continue  # qty=0 → skip
                dos_grup = getattr(pos, 'group', '') or ''

                if qty <= 0:
                    continue

                if side == 'LONG':
                    total_long += qty
                    long_by_group[dos_grup] = long_by_group.get(dos_grup, 0) + qty
                elif side == 'SHORT':
                    total_short += qty
                    short_by_group[dos_grup] = short_by_group.get(dos_grup, 0) + qty

            total = total_long + total_short
            if total <= 0:
                logger.info("[XNL_ENGINE] ACTMAN: Portfolio empty, skipping")
                return orders

            actual_long_pct = total_long / total * 100.0

            # Get config L% — from Redis settings or config file
            config_long_pct = HEDGER_CONFIG_LONG_PCT
            try:
                from app.psfalgo.redis_client import get_redis_client
                redis = get_redis_client()
                raw = redis.get(f'psfalgo:actman:config_long_pct:{account_id}')
                if raw:
                    config_long_pct = float(raw.decode() if isinstance(raw, bytes) else raw)
            except Exception:
                pass

            logger.info(
                f"[XNL_ENGINE] ACTMAN: {account_id} | L={total_long:,}({actual_long_pct:.1f}%) "
                f"S={total_short:,}({100-actual_long_pct:.1f}%) | Config L={config_long_pct:.0f}% "
                f"Drift={actual_long_pct - config_long_pct:+.1f}%"
            )

            # ── Build symbol data from metrics ──
            all_symbols_data = []
            if hasattr(request, 'metrics') and request.metrics:
                for sym, m in request.metrics.items():
                    all_symbols_data.append({
                        'symbol': sym,
                        'dos_grup': getattr(m, 'dos_grup', getattr(m, 'dosGrup', '')),
                        'cgrup': getattr(m, 'cgrup', ''),
                        'avg_adv': getattr(m, 'avg_adv', getattr(m, 'adv', 0)),
                        'final_bs': getattr(m, 'final_bs', getattr(m, 'bid_sell', 0)),
                        'final_sbs': getattr(m, 'final_sbs', getattr(m, 'short_bid_sell', 0)),
                        'final_ab': getattr(m, 'final_ab', getattr(m, 'ask_buy', 0)),
                        'sfs_score': getattr(m, 'sfs_score', getattr(m, 'final_sfs', 0)),
                        'fb_score': getattr(m, 'fbtot', getattr(m, 'fb_score', 0)),
                        'spread': getattr(m, 'spread', 0),
                        'spread_pct': getattr(m, 'spread_pct', 0),
                        'bid': getattr(m, 'bid', 0),
                        'ask': getattr(m, 'ask', 0),
                        'son5_tick': getattr(m, 'son5_tick', None),
                        'maxalw': getattr(m, 'maxalw', 0),
                        'current_qty': getattr(m, 'current_qty', 0),
                        'last_price': getattr(m, 'last', getattr(m, 'last_price', 0)),
                    })

            # ── HEDGER: L/S drift correction ──
            hedger_orders = []
            if HEDGER_ENABLED:
                try:
                    hedger = ActmanHedgerEngine()
                    hedger_result = await hedger.run(
                        account_id=account_id,
                        positions=positions,
                        metrics=request.metrics if hasattr(request, 'metrics') else {},
                        exposure=request.exposure if hasattr(request, 'exposure') else None,
                        config_long_pct=config_long_pct,
                    )
                    if hedger_result and hedger_result.orders:
                        hedger_orders = hedger_result.orders
                        logger.info(
                            f"[XNL_ENGINE] ACTMAN HEDGER: {len(hedger_orders)} orders | "
                            f"drift {hedger_result.drift_before:+.1f}% → {hedger_result.drift_after:+.1f}%"
                        )
                except Exception as he:
                    logger.error(f"[XNL_ENGINE] ACTMAN HEDGER error: {he}", exc_info=True)

            # ── PANIC: ETF-driven emergency ──
            panic_orders_raw = []
            if PANIC_ENABLED:
                try:
                    # Get ETF changes from ETF Guard service
                    etf_changes = {}
                    try:
                        from app.psfalgo.etf_guard_service import get_etf_guard_service
                        etf_svc = get_etf_guard_service()
                        if etf_svc:
                            etf_changes = etf_svc.get_recent_changes() or {}
                    except Exception as etf_err:
                        logger.debug(f"[XNL_ENGINE] ETF Guard service not available: {etf_err}")

                    if etf_changes:
                        from app.psfalgo.minmax_area_service import get_minmax_area_service
                        minmax_svc = get_minmax_area_service()

                        panic = ActmanPanicEngine()
                        panic_result = await panic.evaluate(
                            account_id=account_id,
                            config_long_pct=config_long_pct,
                            actual_long_pct=actual_long_pct,
                            total_lots=total,
                            etf_changes=etf_changes,
                            all_symbols_data=all_symbols_data,
                            minmax_service=minmax_svc,
                            positions=positions,
                            metrics=request.metrics if hasattr(request, 'metrics') else {},
                        )

                        if panic_result and panic_result.triggered and panic_result.orders:
                            panic_orders_raw = panic_result.orders
                            logger.info(
                                f"[XNL_ENGINE] ACTMAN PANIC: {panic_result.severity.upper()} | "
                                f"{len(panic_orders_raw)} orders | shift={panic_result.config_shift:.1f}% | "
                                f"triggers={panic_result.etf_triggers}"
                            )
                        elif panic_result and not panic_result.triggered:
                            logger.info(
                                f"[XNL_ENGINE] ACTMAN PANIC: not triggered ({panic_result.reason})"
                            )
                    else:
                        logger.debug("[XNL_ENGINE] ACTMAN PANIC: No ETF changes available")

                except Exception as pe:
                    logger.error(f"[XNL_ENGINE] ACTMAN PANIC error: {pe}", exc_info=True)

            # ── Convert to XNL order format ──
            # DEC orders → LT_DECREASE category (REV reload YAZILMAZ)
            # INC orders → LT_INCREASE category (REV TP YAZILIR)
            for ho in hedger_orders:
                is_dec = ho.get('actman_is_decrease', False) or 'DEC' in (ho.get('tag') or '')
                ho['source'] = 'ACTMAN_HEDGER_DEC' if is_dec else 'ACTMAN_HEDGER'
                ho['category'] = OrderTagCategory.LT_DECREASE if is_dec else OrderTagCategory.LT_INCREASE
                orders.append(ho)

            for po in panic_orders_raw:
                is_dec = 'DEC' in (getattr(po, 'tag', '') or '')
                orders.append({
                    'symbol': po.symbol,
                    'action': po.action,
                    'quantity': po.qty,
                    'price': po.price,
                    'tag': po.tag,
                    'strategy_tag': po.tag,
                    'hidden': True,
                    'source': 'ACTMAN_PANIC_DEC' if is_dec else 'ACTMAN_PANIC',
                    'engine_name': 'ACTMAN_PANIC',
                    'category': OrderTagCategory.LT_DECREASE if is_dec else OrderTagCategory.LT_INCREASE,
                    'actman_exec_tier': po.tier,
                    'actman_score': po.score,
                    'actman_is_decrease': is_dec,
                    'actman_no_rev_reload': is_dec,  # DEC → NO reload
                    'account_id': account_id,
                })

            # ── Log summary ──
            hedger_count = len(hedger_orders)
            panic_count = len(panic_orders_raw)
            total_lots = sum(o.get('quantity', 0) for o in orders)
            logger.info(
                f"[XNL_ENGINE] ACTMAN TOTAL: {len(orders)} orders ({hedger_count} hedger + {panic_count} panic) | "
                f"{total_lots:,} lots | account={account_id}"
            )

            for o in orders:
                logger.info(
                    f"[XNL_ENGINE] ACTMAN ORDER: {o.get('symbol')} {o.get('action')} "
                    f"{o.get('quantity')} @ ${o.get('price', 0) or 0:.2f} "
                    f"tag={o.get('tag')} tier={o.get('actman_exec_tier', '?')} "
                    f"source={o.get('source')}"
                )

        except Exception as e:
            logger.error(f"[XNL_ENGINE] ACTMAN error: {e}", exc_info=True)

        return orders
    
    async def _run_patadd(self, account_id: str, request) -> List[Dict[str, Any]]:
        """
        Run PATADD engine — pattern-based position increase.

        Uses Pattern Suggestions (BUY_NOW / SHORT_NOW) combined with QE metrics
        (Fbtot / SFStot) to produce LPAT / SPAT scored orders.

        Priority 17 — runs AFTER KARBOTU (20), BEFORE ADDNEWPOS (15).
        """
        orders: List[Dict[str, Any]] = []
        try:
            from app.psfalgo.patadd_engine import get_patadd_engine
            from app.xnl.patadd_settings import get_patadd_settings_store

            settings_store = get_patadd_settings_store()
            settings = settings_store.get_settings(account_id)

            if not settings.get('enabled', True):
                logger.info("[XNL_ENGINE] PATADD disabled in settings")
                return orders

            engine = get_patadd_engine()
            result = await engine.run(
                request=request,
                account_id=account_id,
                settings=settings,
            )

            if result.errors:
                for err in result.errors:
                    logger.warning(f"[XNL_ENGINE] PATADD error: {err}")

            # Convert Decision objects → order dicts for XNL pipeline
            all_decisions = result.lpat_orders + result.spat_orders
            for dec in all_decisions:
                # Map Decision action to XNL action
                if dec.action in ('BUY', 'ADD'):
                    xnl_action = 'BUY'
                    tag_prefix = 'LPAT'
                elif dec.action in ('SHORT', 'SELL', 'ADD_SHORT'):
                    xnl_action = 'SELL'
                    tag_prefix = 'SPAT'
                else:
                    continue

                final_lot = dec.calculated_lot or 0
                if final_lot <= 0:
                    continue

                # MinMax Validation
                try:
                    from app.psfalgo.minmax_area_service import (
                        get_minmax_area_service,
                        validate_order_against_minmax,
                        update_minmax_cache_after_order,
                    )
                    minmax_svc = get_minmax_area_service()
                    minmax_row = minmax_svc.get_row(account_id, dec.symbol)
                    current_qty = minmax_row.current_qty if minmax_row else 0.0
                    mma_allowed, mma_qty, mma_reason = validate_order_against_minmax(
                        account_id, dec.symbol, xnl_action, final_lot,
                        current_qty, minmax_row=minmax_row, minmax_service=minmax_svc,
                    )
                    if not mma_allowed:
                        logger.info(
                            f"[XNL_ENGINE] PATADD {dec.symbol} {xnl_action} {final_lot} "
                            f"blocked by MinMax: {mma_reason}"
                        )
                        continue
                    if mma_qty != final_lot:
                        logger.info(
                            f"[XNL_ENGINE] PATADD {dec.symbol} trimmed by MinMax: "
                            f"{final_lot} -> {mma_qty} ({mma_reason})"
                        )
                        final_lot = mma_qty
                    # Update MinMax cache for intra-cycle consistency
                    update_minmax_cache_after_order(minmax_svc, dec.symbol, xnl_action, final_lot)
                except Exception as minmax_err:
                    logger.warning(f"[XNL_ENGINE] PATADD MinMax check failed for {dec.symbol}: {minmax_err}")

                pat_score = dec.metrics_used.get('pat_score', 0) if dec.metrics_used else 0
                strategy = dec.metrics_used.get('strategy', '') if dec.metrics_used else ''

                # v4 tag: ALWAYS LT_PA_{DIR}_INC — PA always results in LT position
                _pa_dir = 'LONG' if tag_prefix == 'LPAT' else 'SHORT'
                orders.append({
                    'symbol': dec.symbol,
                    'action': xnl_action,
                    'quantity': final_lot,
                    'price': dec.price_hint,
                    'tag': f"LT_PA_{_pa_dir}_INC",
                    'source': f'PATADD_{tag_prefix}',
                    'category': OrderTagCategory.LT_INCREASE,
                    'pat_score': pat_score,
                    'strategy': strategy,
                })

            for o in orders:
                _sym = o['symbol']
                _m = request.metrics.get(_sym) if hasattr(request, 'metrics') and request.metrics else None
                _ms = ""
                if _m:
                    _ms = (
                        f" | fbtot={_m.fbtot} sfstot={_m.sfstot} gort={_m.gort} "
                        f"ucuz={_m.bid_buy_ucuzluk} pah={_m.ask_sell_pahalilik} "
                        f"bid={_m.bid} ask={_m.ask} last={_m.last} "
                        f"son5={_m.son5_tick} v1h={_m.volav_1h} v4h={_m.volav_4h}"
                    )
                logger.info(
                    f"[XNL_ENGINE] PATADD ORDER: {_sym} {o['action']} "
                    f"{o['quantity']} @ ${o.get('price', 0) or 0:.2f} "
                    f"tag={o['tag']} pat={o.get('pat_score',0):.0f} {o.get('strategy','')}{_ms}"
                )
            logger.info(
                f"[XNL_ENGINE] PATADD generated {len(orders)} orders "
                f"(LPAT={len(result.lpat_orders)}, SPAT={len(result.spat_orders)})"
            )

        except Exception as e:
            logger.error(f"[XNL_ENGINE] PATADD error: {e}", exc_info=True)

        return orders
    
    async def _run_mm(self, account_id: str, request, exclude_symbols: Set[str] = None) -> List[Dict[str, Any]]:
        """
        Run MM engine using shared cycle request.
        
        Args:
            exclude_symbols: Symbols already claimed by higher-priority engines
                            (LT_TRIM, KARBOTU, PATADD, ADDNEWPOS). MM will SKIP these
                            and pick the next-best candidates to fill its quota.
        """
        orders = []
        try:
            from app.xnl.mm_settings import get_mm_settings_store
            from app.mm.greatest_mm_decision_engine import get_greatest_mm_decision_engine
            
            mm_settings_store = get_mm_settings_store()
            mm_settings = mm_settings_store.get_settings()
            
            if not mm_settings.get('enabled', True):
                logger.info("[XNL_ENGINE] MM disabled in settings")
                return orders
            
            if not request:
                logger.info("[XNL_ENGINE] No cycle request for MM")
                return orders
            
            est_cur_ratio = mm_settings.get('est_cur_ratio', 44.0)
            min_stock_count = mm_settings.get('min_stock_count', 5)
            max_stock_count = mm_settings.get('max_stock_count', 100)
            lot_per_stock = mm_settings.get('lot_per_stock', 200)
            lot_mode = mm_settings.get('lot_mode', 'fixed')  # 'fixed' or 'adv_adjust'
            
            logger.info(f"[XNL_ENGINE] MM settings: est_cur_ratio={est_cur_ratio}%, lot={lot_per_stock}, lot_mode={lot_mode}")
            logger.info(f"[XNL_ENGINE] MM: Using shared request (positions={len(getattr(request, 'positions', []) or [])}, l1={len(getattr(request, 'l1_data', {}) or {})} symbols)")
            
            # Run Greatest MM Decision Engine (request from RUNALL preparer has positions, metrics, l1_data, exposure, available_symbols)
            mm_engine = get_greatest_mm_decision_engine()
            mm_decisions = await mm_engine.run(request)
            
            if not mm_decisions:
                logger.info("[XNL_ENGINE] No MM decisions generated")
                return orders
            
            # Separate LONG (BUY) and SHORT (SELL) decisions
            long_decisions = []
            short_decisions = []
            excluded_count = 0
            
            for dec in mm_decisions:
                # SYMBOL EXCLUSION: Skip symbols claimed by LT engines
                if exclude_symbols and dec.symbol.upper() in exclude_symbols:
                    excluded_count += 1
                    continue
                # POS TAG CHECK: MM engine CANNOT operate on LT positions
                # (even if no LT engine claimed this symbol this cycle)
                try:
                    from app.psfalgo.position_tag_store import get_position_tag_store
                    _mm_store = get_position_tag_store()
                    if _mm_store:
                        _mm_pos_tag = _mm_store.get_tag(dec.symbol, account_id)
                        # Check if there's actually a position (not just default MM)
                        pos = next((p for p in request.positions if p.symbol == dec.symbol), None)
                        if pos and abs(pos.qty) > 0 and _mm_pos_tag == "LT":
                            excluded_count += 1
                            logger.info(
                                f"[XNL_ENGINE] MM {dec.symbol} BLOCKED: "
                                f"POS TAG=LT (MM cannot operate on LT positions)"
                            )
                            continue
                except Exception:
                    pass
                if dec.action == 'BUY':
                    long_decisions.append(dec)
                elif dec.action == 'SELL':
                    short_decisions.append(dec)
            
            if excluded_count > 0:
                logger.info(
                    f"[XNL_ENGINE] MM: {excluded_count} symbols excluded "
                    f"(claimed by LT/KARBOTU/ADDNEWPOS)"
                )
            
            # Sort by score (descending) - MM engine already provides score in metrics_used
            long_decisions.sort(
                key=lambda d: d.metrics_used.get('mm_score', 0) if d.metrics_used else 0,
                reverse=True
            )
            short_decisions.sort(
                key=lambda d: d.metrics_used.get('mm_score', 0) if d.metrics_used else 0,
                reverse=True
            )
            
            # Apply Est/Cur ratio to determine stock count
            # Default: 50 long + 50 short = 100 total
            default_count = 50
            ratio_multiplier = est_cur_ratio / 44.0  # Default is 44%
            adjusted_count = max(min_stock_count, min(max_stock_count, int(default_count * ratio_multiplier)))
            
            logger.info(
                f"[XNL_ENGINE] MM stock selection: "
                f"default={default_count}, est_cur={est_cur_ratio}%, "
                f"adjusted={adjusted_count} per side, "
                f"available: {len(long_decisions)}L/{len(short_decisions)}S "
                f"(after {excluded_count} exclusions)"
            )
            
            # Take top N stocks for each side (from FILTERED pool)
            final_longs = long_decisions[:adjusted_count]
            final_shorts = short_decisions[:adjusted_count]
            # MinMax pre-validation: load service once
            from app.psfalgo.minmax_area_service import (
                get_minmax_area_service,
                validate_order_against_minmax,
                update_minmax_cache_after_order,
            )
            minmax_svc = get_minmax_area_service()
            minmax_svc.get_all_rows(account_id)
            
            # Convert to orders
            mm_blocked = 0
            mm_trimmed = 0
            for dec in final_longs:
                # Get price from proposal (bid + spread * 0.15)
                # If price_hint exists, use it; otherwise calculate
                if dec.price_hint:
                    order_price = dec.price_hint
                else:
                    # Get L1 data for price calculation
                    l1_data = await self._get_l1_data(dec.symbol)
                    if l1_data:
                        bid = l1_data.get('bid', 0)
                        ask = l1_data.get('ask', 0)
                        spread = ask - bid if ask > bid else 0.01
                        order_price = bid + (spread * 0.15)
                    else:
                        logger.warning(f"[XNL_ENGINE] No L1 data for {dec.symbol}, skipping")
                        continue
                
                qty = dec.calculated_lot if lot_mode == 'adv_adjust' and dec.calculated_lot else lot_per_stock
                
                # MinMax Validation
                minmax_row = minmax_svc.get_row(account_id, dec.symbol)
                current_qty = minmax_row.current_qty if minmax_row else 0.0
                mma_allowed, mma_qty, mma_reason = validate_order_against_minmax(
                    account_id, dec.symbol, 'BUY', qty,
                    current_qty, minmax_row=minmax_row, minmax_service=minmax_svc,
                )
                if not mma_allowed:
                    logger.debug(f"[XNL_ENGINE] MM {dec.symbol} BUY {qty} blocked by MinMax: {mma_reason}")
                    mm_blocked += 1
                    continue
                if mma_qty != qty:
                    logger.debug(f"[XNL_ENGINE] MM {dec.symbol} BUY trimmed: {qty} -> {mma_qty}")
                    qty = mma_qty
                    mm_trimmed += 1
                # Update MinMax cache for intra-cycle consistency
                update_minmax_cache_after_order(minmax_svc, dec.symbol, 'BUY', qty)
                
                _mm_meta = dec.metrics_used or {}
                orders.append({
                    'symbol': dec.symbol,
                    'action': 'BUY',
                    'quantity': qty,
                    'price': round(order_price, 2),
                    'tag': 'MM_MM_LONG_INC',
                    'source': 'MM',
                    'category': OrderTagCategory.MM_INCREASE,
                    'mm_score': _mm_meta.get('mm_score', 0),
                    'mm_scenario': _mm_meta.get('scenario', '?'),
                    'mm_son5': _mm_meta.get('son5_tick', 0),
                    'mm_volav1': _mm_meta.get('volav1', 0),
                    'mm_volav_window': _mm_meta.get('volav_window', 'none'),
                    'mm_free_exp_pct': _mm_meta.get('free_exp_pct', 0),
                })
                # Log detailed MM order info
                _m = dec.metrics_used or {}
                _rm = request.metrics.get(dec.symbol) if hasattr(request, 'metrics') and request.metrics else None
                _val = ""
                if _rm:
                    _val = f" fbtot={_rm.fbtot} sfstot={_rm.sfstot} gort={_rm.gort} ucuz={_rm.bid_buy_ucuzluk} pah={_rm.ask_sell_pahalilik} son5={_rm.son5_tick} v1h={_rm.volav_1h} v4h={_rm.volav_4h}"
                logger.info(
                    f"[MM_ORDER] BUY {dec.symbol} {qty}lot @${order_price:.2f} | "
                    f"Score={_m.get('mm_score', 0):.1f} Sc={_m.get('scenario', '?')} "
                    f"Bid=${_m.get('bid', 0):.2f} Ask=${_m.get('ask', 0):.2f} "
                    f"Son5={_m.get('son5_tick', 0):.2f} "
                    f"{('Volav_'+_m.get('volav_window','?')+'=$'+str(round(_m.get('volav1',0),2))) if _m.get('volav1') else 'NoVolav'}"
                    f"{_val}"
                )
            
            for dec in final_shorts:
                # Get price from proposal (ask - spread * 0.15)
                if dec.price_hint:
                    order_price = dec.price_hint
                else:
                    # Get L1 data for price calculation
                    l1_data = await self._get_l1_data(dec.symbol)
                    if l1_data:
                        bid = l1_data.get('bid', 0)
                        ask = l1_data.get('ask', 0)
                        spread = ask - bid if ask > bid else 0.01
                        order_price = ask - (spread * 0.15)
                    else:
                        logger.warning(f"[XNL_ENGINE] No L1 data for {dec.symbol}, skipping")
                        continue
                
                qty = dec.calculated_lot if lot_mode == 'adv_adjust' and dec.calculated_lot else lot_per_stock
                
                # MinMax Validation
                minmax_row = minmax_svc.get_row(account_id, dec.symbol)
                current_qty = minmax_row.current_qty if minmax_row else 0.0
                mma_allowed, mma_qty, mma_reason = validate_order_against_minmax(
                    account_id, dec.symbol, 'SELL', qty,
                    current_qty, minmax_row=minmax_row, minmax_service=minmax_svc,
                )
                if not mma_allowed:
                    logger.debug(f"[XNL_ENGINE] MM {dec.symbol} SELL {qty} blocked by MinMax: {mma_reason}")
                    mm_blocked += 1
                    continue
                if mma_qty != qty:
                    logger.debug(f"[XNL_ENGINE] MM {dec.symbol} SELL trimmed: {qty} -> {mma_qty}")
                    qty = mma_qty
                    mm_trimmed += 1
                # Update MinMax cache for intra-cycle consistency
                update_minmax_cache_after_order(minmax_svc, dec.symbol, 'SELL', qty)
                
                _mm_meta = dec.metrics_used or {}
                orders.append({
                    'symbol': dec.symbol,
                    'action': 'SELL',
                    'quantity': qty,
                    'price': round(order_price, 2),
                    'tag': 'MM_MM_SHORT_INC',
                    'source': 'MM',
                    'category': OrderTagCategory.MM_INCREASE,
                    'mm_score': _mm_meta.get('mm_score', 0),
                    'mm_scenario': _mm_meta.get('scenario', '?'),
                    'mm_son5': _mm_meta.get('son5_tick', 0),
                    'mm_volav1': _mm_meta.get('volav1', 0),
                    'mm_volav_window': _mm_meta.get('volav_window', 'none'),
                    'mm_free_exp_pct': _mm_meta.get('free_exp_pct', 0),
                })
                # Log detailed MM order info
                _m = dec.metrics_used or {}
                _rm = request.metrics.get(dec.symbol) if hasattr(request, 'metrics') and request.metrics else None
                _val = ""
                if _rm:
                    _val = f" fbtot={_rm.fbtot} sfstot={_rm.sfstot} gort={_rm.gort} ucuz={_rm.bid_buy_ucuzluk} pah={_rm.ask_sell_pahalilik} son5={_rm.son5_tick} v1h={_rm.volav_1h} v4h={_rm.volav_4h}"
                logger.info(
                    f"[MM_ORDER] SELL {dec.symbol} {qty}lot @${order_price:.2f} | "
                    f"Score={_m.get('mm_score', 0):.1f} Sc={_m.get('scenario', '?')} "
                    f"Bid=${_m.get('bid', 0):.2f} Ask=${_m.get('ask', 0):.2f} "
                    f"Son5={_m.get('son5_tick', 0):.2f} "
                    f"{('Volav_'+_m.get('volav_window','?')+'=$'+str(round(_m.get('volav1',0),2))) if _m.get('volav1') else 'NoVolav'}"
                    f"{_val}"
                )
            
            if mm_blocked > 0 or mm_trimmed > 0:
                logger.info(f"[XNL_ENGINE] MM MinMax: {mm_blocked} blocked, {mm_trimmed} trimmed")
            
            logger.info(
                f"[XNL_ENGINE] MM generated {len(orders)} orders "
                f"({len(final_longs)} LONG, {len(final_shorts)} SHORT)"
            )
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] MM error: {e}", exc_info=True)
        
        return orders
    
    async def _run_newclmm(self, account_id: str, request, exclude_symbols: Set[str] = None) -> List[Dict[str, Any]]:
        """
        Run NEWCLMM engine — truth tick spread capture.
        
        PAPER MODE (default): Engine runs, logs paper signals, returns empty list.
        LIVE MODE (enabled): Returns real order dicts with MinMax validation.
        
        Tag format: MM_NEWC_{LONG|SHORT}_{INC|DEC}
        """
        orders = []
        try:
            from app.mm.newclmm_engine import get_newclmm_engine
            
            newclmm = get_newclmm_engine()
            
            # Run engine (handles paper mode internally — logs but returns empty if disabled)
            newclmm_decisions = await newclmm.run(request)
            
            if not newclmm_decisions:
                is_paper = not newclmm.enabled
                if is_paper:
                    logger.info("[XNL_ENGINE] NEWCLMM running in PAPER mode (signals logged above)")
                else:
                    logger.debug("[XNL_ENGINE] NEWCLMM: no decisions")
                return orders
            
            # LIVE MODE — convert decisions to XNL order dicts
            logger.info(f"[XNL_ENGINE] NEWCLMM LIVE: {len(newclmm_decisions)} decisions to process")
            
            # MinMax setup
            from app.psfalgo.minmax_area_service import (
                get_minmax_area_service,
                validate_order_against_minmax,
                update_minmax_cache_after_order,
            )
            minmax_svc = get_minmax_area_service()
            
            for dec in newclmm_decisions:
                sym = dec.symbol
                if exclude_symbols and sym.upper() in exclude_symbols:
                    logger.debug(f"[XNL_ENGINE] NEWCLMM {sym} excluded (claimed by higher-priority engine)")
                    continue
                
                action = dec.action  # 'BUY' or 'SELL'
                qty = dec.calculated_lot or 200
                tag = dec.strategy_tag or f"MM_NEWC_{'LONG' if action == 'BUY' else 'SHORT'}_INC"
                
                # MinMax validation
                try:
                    minmax_row = minmax_svc.get_row(account_id, sym)
                    current_qty = minmax_row.current_qty if minmax_row else 0.0
                    mma_allowed, mma_qty, mma_reason = validate_order_against_minmax(
                        account_id, sym, action, qty,
                        current_qty, minmax_row=minmax_row, minmax_service=minmax_svc,
                    )
                    if not mma_allowed:
                        logger.info(
                            f"[XNL_ENGINE] NEWCLMM {sym} {action} {qty} "
                            f"blocked by MinMax: {mma_reason}"
                        )
                        continue
                    if mma_qty != qty:
                        logger.info(
                            f"[XNL_ENGINE] NEWCLMM {sym} trimmed by MinMax: "
                            f"{qty} -> {mma_qty} ({mma_reason})"
                        )
                        qty = mma_qty
                    update_minmax_cache_after_order(minmax_svc, sym, action, qty)
                except Exception as mme:
                    logger.warning(f"[XNL_ENGINE] NEWCLMM MinMax check failed for {sym}: {mme}")
                
                price = dec.price_hint or 0
                _meta = dec.metrics_used or {}
                
                orders.append({
                    'symbol': sym,
                    'action': action,
                    'quantity': qty,
                    'price': round(price, 2) if price else None,
                    'tag': tag,
                    'source': 'NEWCLMM',
                    'category': OrderTagCategory.MM_INCREASE if 'INC' in tag else OrderTagCategory.MM_DECREASE,
                    'hidden': _meta.get('hidden', True),
                })
                
                logger.info(
                    f"[XNL_ENGINE] NEWCLMM ORDER: {action} {sym} {qty}lot "
                    f"@${price:.2f} HIDDEN tag={tag} | {dec.reason}"
                )
            
            logger.info(f"[XNL_ENGINE] NEWCLMM generated {len(orders)} orders")
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] NEWCLMM error: {e}", exc_info=True)
        
        return orders

    async def _write_proposals_to_store(
        self,
        lt_trim_orders: List[Dict[str, Any]],
        karbotu_orders: List[Dict[str, Any]],
        patadd_orders: List[Dict[str, Any]],
        addnewpos_orders: List[Dict[str, Any]],
        mm_orders: List[Dict[str, Any]],
    ) -> None:
        """
        Write XNL outputs to proposal_store so PSFALGO tabs show them.
        Uses cycle_id=-1 for XNL; clears previous XNL batch first so the same
        orders do not repeat. RUNALL uses positive cycle_id and is unaffected.
        """
        try:
            from app.psfalgo.proposal_store import get_proposal_store
            from app.psfalgo.proposal_engine import get_proposal_engine
            from app.psfalgo.decision_models import Decision, DecisionResponse

            proposal_store = get_proposal_store()
            proposal_engine = get_proposal_engine()
            if not proposal_store or not proposal_engine:
                logger.debug("[XNL_ENGINE] Proposal store/engine not available, skipping proposal write")
                return

            # Replace previous XNL batch only (cycle_id=-1); RUNALL proposals stay
            cleared = proposal_store.clear_pending_proposals_with_cycle_id(-1)
            if cleared > 0:
                logger.info(f"[XNL_ENGINE] Cleared {cleared} previous XNL proposals before writing new batch")

            now = datetime.now()
            xnl_cycle_id = -1
            batches = [
                (lt_trim_orders, "LT_TRIM"),
                (karbotu_orders, "KARBOTU"),
                (patadd_orders, "PATADD"),
                (addnewpos_orders, "ADDNEWPOS_ENGINE"),
                (mm_orders, "GREATEST_MM"),
            ]
            for orders, decision_source in batches:
                if not orders:
                    continue
                decisions = []
                for o in orders:
                    action = (o.get("action") or "BUY").upper()
                    if action not in ("BUY", "SELL"):
                        continue
                    qty = o.get("quantity") or 0
                    if qty <= 0:
                        continue
                    decisions.append(
                        Decision(
                            symbol=o.get("symbol", ""),
                            action=action,
                            calculated_lot=int(qty),
                            price_hint=o.get("price"),
                            reason=f"XNL {o.get('source', decision_source)}",
                            engine_name=decision_source,
                        )
                    )
                if not decisions:
                    continue
                proposals = await proposal_engine.process_decision_response(
                    response=DecisionResponse(decisions=decisions),
                    cycle_id=xnl_cycle_id,
                    decision_source=decision_source,
                    decision_timestamp=now,
                )
                for p in proposals:
                    proposal_store.add_proposal(p)
                logger.info(f"[XNL_ENGINE] Wrote {len(proposals)} proposals to store (source={decision_source})")
        except Exception as e:
            logger.warning(f"[XNL_ENGINE] Proposal write failed: {e}", exc_info=True)
    
    async def _send_orders_with_frontlama(
        self,
        orders: List[Dict[str, Any]],
        account_id: str
    ):
        """Send orders with frontlama check BEFORE sending"""
        logger.info(f"[XNL_ENGINE] Sending {len(orders)} orders with frontlama...")
        
        try:
            from app.terminals.frontlama_engine import get_frontlama_engine
            from app.psfalgo.exposure_calculator import get_exposure_calculator
            
            frontlama = get_frontlama_engine()
            
            # Get current exposure using async wrapper
            from app.psfalgo.exposure_calculator import calculate_exposure_for_account
            exposure = await calculate_exposure_for_account(account_id)
            exposure_pct = (exposure.pot_total / exposure.pot_max * 100) if exposure and exposure.pot_max > 0 else 50.0
            
            # MinMax SAFETY NET: Refresh current_qty from REAL Redis positions.
            # ═══════════════════════════════════════════════════════════════
            # Engine phase (_run_lt_trim, _run_karbotu, etc.) already updated
            # the MinMax cache with VIRTUAL positions via update_minmax_cache_after_order()
            # to prevent inter-engine double-spending (e.g., PATADD + ADDNEWPOS).
            #
            # But SAFETY NET must validate against REAL positions, because NO
            # orders have been sent/filled yet at this point. Without this,
            # orders get blocked by their own phantom headroom consumption.
            #
            # We refresh ONLY current_qty (from Redis) — bands stay FIXED (daily).
            # ═══════════════════════════════════════════════════════════════
            from app.psfalgo.minmax_area_service import get_minmax_area_service
            minmax_svc = get_minmax_area_service()
            # Ensure daily bands exist (once-per-day, cached after first call)
            minmax_svc.get_all_rows(account_id)
            # Refresh current_qty from real Redis positions
            self._refresh_minmax_current_qty(minmax_svc, account_id)
            
            sent_count = 0
            
            for order in orders:
                if not self._running:
                    logger.info("[XNL_ENGINE] Stop requested, aborting order send")
                    break
                try:
                    # Get L1 data for this symbol
                    l1_data = await self._get_l1_data(order['symbol'])
                    
                    if not l1_data:
                        logger.warning(f"[XNL_ENGINE] No L1 data for {order['symbol']}, skipping")
                        continue
                    
                    # Calculate base price
                    bid = l1_data.get('bid', 0)
                    ask = l1_data.get('ask', 0)
                    spread = ask - bid if ask > bid else 0.01
                    
                    # Base price calculation
                    if order['action'] in ['BUY', 'ADD']:
                        base_price = bid + (spread * 0.15)
                    else:  # SELL
                        base_price = ask - (spread * 0.15)
                    
                    # Get last 5 truth ticks from Redis for multi-tick evaluation
                    truth_ticks = await self._get_truth_ticks_list(order['symbol'])
                    
                    # Evaluate frontlama with multi-tick (newest passing tick wins)
                    order_dict = {
                        'symbol': order['symbol'],
                        'action': order['action'],
                        'price': base_price,
                        'tag': order.get('tag', '')
                    }
                    l1_dict = {
                        'bid': bid,
                        'ask': ask,
                        'spread': ask - bid if ask > bid else 0.01
                    }
                    decision = frontlama.evaluate_with_multi_ticks(
                        order=order_dict,
                        l1_data=l1_dict,
                        truth_ticks=truth_ticks,
                        exposure_pct=exposure_pct
                    )
                    
                    # Use fronted price if allowed
                    final_price = decision.front_price if decision.allowed and decision.front_price else base_price
                    final_price = round(final_price, 2)
                    
                    # FR_ PREFIX: Tag update when initially fronted
                    send_tag = order['tag']
                    if decision.allowed and decision.front_price:
                        if not send_tag.upper().startswith('FR_'):
                            send_tag = f"FR_{send_tag}"
                        from app.core.order_context_logger import format_fronted_log, get_order_context
                        _fr_ctx2 = get_order_context(order['symbol'])
                        logger.info(format_fronted_log(
                            symbol=order['symbol'],
                            action=order.get('action', ''),
                            quantity=order.get('quantity', 0),
                            base_price=base_price,
                            final_price=final_price,
                            sacrifice=decision.sacrificed_cents,
                            tag=send_tag,
                            bid=bid, ask=ask,
                            ctx=_fr_ctx2
                        ))
                    
                    if not self._running:
                        logger.info("[XNL_ENGINE] Stop requested, aborting before place_order")
                        break
                    
                    # ═══════════════════════════════════════════════════════════
                    # REVERSE GUARD: Prevent position reversals & duplicate orders
                    # Checks open orders + current position + befday BEFORE sending
                    # ═══════════════════════════════════════════════════════════
                    from app.psfalgo.reverse_guard import check_reverse_guard
                    rg_allowed, rg_adj_qty, rg_reason = check_reverse_guard(
                        symbol=order['symbol'],
                        action=order['action'],
                        quantity=order['quantity'],
                        tag=send_tag,
                        account_id=account_id,
                    )
                    if not rg_allowed:
                        logger.warning(
                            f"[XNL_ENGINE] 🛡️ REVERSE GUARD BLOCKED: {order['symbol']} "
                            f"{order['action']} {order['quantity']} | {rg_reason}"
                        )
                        continue
                    if rg_adj_qty != order['quantity']:
                        logger.warning(
                            f"[XNL_ENGINE] 🛡️ REVERSE GUARD TRIMMED: {order['symbol']} "
                            f"{order['action']} {order['quantity']} → {rg_adj_qty} | {rg_reason}"
                        )
                        order = {**order, 'quantity': rg_adj_qty}
                    
                    # MinMax Safety Net: Orders should already be validated by RunAll.
                    # This check is a safety net only - it should rarely block/trim.
                    from app.psfalgo.minmax_area_service import validate_order_against_minmax, update_minmax_cache_after_order
                    minmax_row = minmax_svc.get_row(account_id, order['symbol'])
                    current_qty = minmax_row.current_qty if minmax_row else 0.0
                    allowed, adj_qty, minmax_reason = validate_order_against_minmax(
                        account_id, order['symbol'], order['action'], order['quantity'],
                        current_qty, minmax_row=minmax_row, minmax_service=minmax_svc,
                    )
                    if not allowed:
                        # This should be rare if RunAll is working correctly
                        logger.warning(
                            f"[XNL_ENGINE] SAFETY NET: {order['symbol']} {order['action']} {order['quantity']} "
                            f"blocked by MinMax (should have been caught by RunAll): {minmax_reason}"
                        )
                        continue
                    if adj_qty != order['quantity']:
                        # Log at debug level since RunAll should have already trimmed
                        logger.debug(
                            f"[XNL_ENGINE] Safety trim: {order['symbol']} {order['quantity']} -> {adj_qty}"
                        )
                        order = {**order, 'quantity': adj_qty}
                    # Update MinMax cache for intra-cycle consistency
                    update_minmax_cache_after_order(minmax_svc, order['symbol'], order['action'], order['quantity'])
                    # Send order
                    success = await self._place_order(
                        symbol=order['symbol'],
                        action=order['action'],
                        quantity=order['quantity'],
                        price=final_price,
                        tag=send_tag,
                        account_id=account_id
                    )
                    
                    if success:
                        sent_count += 1
                        self.state.total_orders_sent += 1
                        # MM-specific send log: show score, scenario, volav
                        if order.get('source') == 'MM':
                            _ms = order.get('mm_score', 0)
                            _msc = order.get('mm_scenario', '?')
                            _ms5 = order.get('mm_son5', 0)
                            _mv1 = order.get('mm_volav1', 0)
                            _mvw = order.get('mm_volav_window', 'none')
                            _mfep = order.get('mm_free_exp_pct', 0)
                            _volav_str = f"Volav_{_mvw}=${_mv1:.2f}" if _mv1 else "NoVolav"
                            logger.info(
                                f"[MM_SEND] ✅ {order['action']} {order['symbol']} "
                                f"{order['quantity']}lot @${final_price:.2f} | "
                                f"MMScore={_ms:.1f} Scenario={_msc} "
                                f"Son5=${_ms5:.2f} {_volav_str} "
                                f"FreeExp={_mfep:.1f}% tag={send_tag}"
                            )
                    
                    # Rate limiting (tune ORDER_SEND_DELAY_SEC at top of file)
                    await asyncio.sleep(ORDER_SEND_DELAY_SEC)
                    
                except Exception as e:
                    logger.error(f"[XNL_ENGINE] Order send error for {order['symbol']}: {e}")
            
            if not self._running and sent_count < len(orders):
                logger.info(f"[XNL_ENGINE] Sent {sent_count}/{len(orders)} orders (aborted: stop requested)")
            else:
                logger.info(f"[XNL_ENGINE] Sent {sent_count}/{len(orders)} orders")
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] Send orders error: {e}", exc_info=True)
    
    async def _front_cycle_loop(self, category: OrderTagCategory):
        """Front control cycle loop for a category"""
        timing = CYCLE_TIMINGS[category]
        cycle_state = self.state.cycle_states[category]
        
        logger.info(f"[XNL_ENGINE] Starting FRONT cycle for {category.value} (every {timing.front_cycle_seconds}s)")
        
        while self._running and not self._stop_event.is_set():
            try:
                # Wait for next cycle
                await asyncio.sleep(timing.front_cycle_seconds)
                
                if not self._running:
                    break
                
                # Run front cycle
                logger.info(f"[XNL_ENGINE] 🔄 FRONT CYCLE: {category.value}")
                await self._execute_front_cycle(category)
                
                # Update state
                cycle_state.last_front_cycle = datetime.now()
                cycle_state.front_cycle_count += 1
                self.state.total_front_cycles += 1
                
            except asyncio.CancelledError:
                logger.info(f"[XNL_ENGINE] Front cycle {category.value} cancelled")
                break
            except Exception as e:
                logger.error(f"[XNL_ENGINE] Front cycle {category.value} error: {e}", exc_info=True)
                await asyncio.sleep(5)  # Brief pause on error
    
    async def _refresh_cycle_loop(self, category: OrderTagCategory):
        """Refresh cycle loop for a category"""
        timing = CYCLE_TIMINGS[category]
        cycle_state = self.state.cycle_states[category]
        
        logger.info(f"[XNL_ENGINE] Starting REFRESH cycle for {category.value} (every {timing.refresh_cycle_seconds}s)")
        
        while self._running and not self._stop_event.is_set():
            try:
                # Wait for next cycle
                await asyncio.sleep(timing.refresh_cycle_seconds)
                
                if not self._running:
                    break
                
                # Run refresh cycle
                logger.info(f"[XNL_ENGINE] 🔄 REFRESH CYCLE: {category.value}")
                await self._execute_refresh_cycle(category)
                
                # Update state
                cycle_state.last_refresh_cycle = datetime.now()
                cycle_state.refresh_cycle_count += 1
                self.state.total_refresh_cycles += 1
                
            except asyncio.CancelledError:
                logger.info(f"[XNL_ENGINE] Refresh cycle {category.value} cancelled")
                break
            except Exception as e:
                logger.error(f"[XNL_ENGINE] Refresh cycle {category.value} error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def _execute_front_cycle(self, category: OrderTagCategory):
        """Execute front control cycle for open orders of this category"""
        try:
            from app.terminals.frontlama_engine import get_frontlama_engine
            from app.psfalgo.exposure_calculator import get_exposure_calculator
            
            # 🔒 Use pinned account_id from start() — NOT get_trading_context()
            # This prevents cross-account contamination during dual process switching
            account_id = self._active_account_id
            if not account_id:
                logger.warning("[XNL_ENGINE] Front cycle: no pinned account_id, skipping")
                return
            
            # Get open orders for this category
            open_orders = await self._get_open_orders_by_category(category, account_id)
            
            if not open_orders:
                logger.debug(f"[XNL_ENGINE] No open orders for {category.value}")
                return
            
            logger.info(f"[XNL_ENGINE] Checking {len(open_orders)} orders for frontlama")
            
            frontlama = get_frontlama_engine()
            
            # Get current exposure using async wrapper
            from app.psfalgo.exposure_calculator import calculate_exposure_for_account
            exposure = await calculate_exposure_for_account(account_id)
            exposure_pct = (exposure.pot_total / exposure.pot_max * 100) if exposure and exposure.pot_max > 0 else 50.0
            
            modified_count = 0
            
            for order in open_orders:
                try:
                    l1_data = await self._get_l1_data(order['symbol'])
                    if not l1_data:
                        continue
                    
                    bid = l1_data.get('bid', 0)
                    ask = l1_data.get('ask', 0)
                    
                    # Get last 5 truth ticks for multi-tick evaluation
                    truth_ticks = await self._get_truth_ticks_list(order['symbol'])
                    
                    # Evaluate frontlama with multi-tick (newest passing tick wins)
                    order_dict = {
                        'symbol': order['symbol'],
                        'action': order['action'],
                        'price': order['price'],
                        'tag': order.get('tag', '')
                    }
                    l1_dict = {
                        'bid': bid,
                        'ask': ask,
                        'spread': ask - bid if ask > bid else 0.01
                    }
                    decision = frontlama.evaluate_with_multi_ticks(
                        order=order_dict,
                        l1_data=l1_dict,
                        truth_ticks=truth_ticks,
                        exposure_pct=exposure_pct
                    )
                    
                    if decision.allowed and decision.front_price:
                        # Need to modify order
                        price_diff = abs(decision.front_price - order['price'])
                        if price_diff >= 0.01:  # At least 1 cent difference
                            # FR_ PREFIX: Add when frontlama modifies order
                            fr_tag = order.get('tag', '')
                            if not fr_tag.upper().startswith('FR_'):
                                fr_tag = f"FR_{fr_tag}"
                            
                            from app.core.order_context_logger import format_fronted_log, get_order_context
                            _fr_ctx = get_order_context(order['symbol'])
                            logger.info(format_fronted_log(
                                symbol=order['symbol'],
                                action=order.get('action', ''),
                                quantity=order.get('quantity', 0),
                                base_price=order['price'],
                                final_price=decision.front_price,
                                sacrifice=abs(decision.front_price - order['price']),
                                tag=fr_tag,
                                bid=bid, ask=ask,
                                ctx=_fr_ctx
                            ))
                            
                            # Try atomic modify first (Hammer Pro tradeCommandModify)
                            modified = await self._modify_order_price(
                                order['order_id'], decision.front_price, account_id
                            )
                            
                            if not modified:
                                # Fallback: cancel and replace (IBKR path)
                                # Use FR_ tag on the new order
                                await self._cancel_order(order['order_id'], account_id)
                                await asyncio.sleep(0.1)
                                await self._place_order(
                                    symbol=order['symbol'],
                                    action=order['action'],
                                    quantity=order['quantity'],
                                    price=decision.front_price,
                                    tag=fr_tag,
                                    account_id=account_id
                                )
                            
                            modified_count += 1
                    
                    await asyncio.sleep(ORDER_SEND_DELAY_SEC)
                    
                except Exception as e:
                    logger.error(f"[XNL_ENGINE] Front check error for {order['symbol']}: {e}")
            
            logger.info(f"[XNL_ENGINE] Front cycle complete: {modified_count} orders modified")
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] Front cycle error: {e}", exc_info=True)
    
    async def _execute_refresh_cycle(self, category: OrderTagCategory):
        """Execute refresh cycle: cancel all orders of this category and resend.
        Uses same shared cycle request (prepare_cycle_request) as initial cycle so
        engines get positions, metrics, exposure, Janall from RUNALL layer."""
        try:
            from app.psfalgo.runall_engine import get_runall_engine
            
            # 🔒 Use pinned account_id from start() — NOT get_trading_context()
            account_id = self._active_account_id
            if not account_id:
                logger.warning("[XNL_ENGINE] Refresh cycle: no pinned account_id, skipping")
                return
            
            # Get open orders for this category
            open_orders = await self._get_open_orders_by_category(category, account_id)
            
            if not open_orders:
                logger.debug(f"[XNL_ENGINE] No open orders for {category.value} refresh")
                return
            
            logger.info(f"[XNL_ENGINE] Refreshing {len(open_orders)} orders")
            
            # Cancel all orders of this category
            cancelled_count = 0
            for order in open_orders:
                try:
                    success = await self._cancel_order(order['order_id'], account_id)
                    if success:
                        cancelled_count += 1
                        self.state.total_orders_cancelled += 1
                    await asyncio.sleep(ORDER_SEND_DELAY_SEC)
                except Exception as e:
                    logger.error(f"[XNL_ENGINE] Cancel error: {e}")
            
            logger.info(f"[XNL_ENGINE] Cancelled {cancelled_count} orders")
            
            # Wait for cancellations to process
            await asyncio.sleep(0.5)
            
            # Prepare shared cycle request (same as initial cycle and RUNALL)
            correlation_id = f"xnl_refresh_{category.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            request = await get_runall_engine().prepare_cycle_request(account_id, correlation_id=correlation_id)
            if request is None:
                logger.warning("[XNL_ENGINE] Refresh cycle: prepare_cycle_request returned None, skipping resend")
                return
            
            # Refresh MinMax current_qty from Redis before engines run
            from app.psfalgo.minmax_area_service import get_minmax_area_service
            minmax_svc = get_minmax_area_service()
            minmax_svc.get_all_rows(account_id)
            self._refresh_minmax_current_qty(minmax_svc, account_id)
            
            # Reset REVERSE GUARD intra-cycle tracking (fresh start each refresh cycle)
            from app.psfalgo.reverse_guard import reset_guard_tracking
            reset_guard_tracking()
            
            # Recalculate and resend orders for this category
            if category == OrderTagCategory.LT_INCREASE:
                # Check hard_risk to skip increase if needed
                from app.psfalgo.exposure_calculator import get_current_and_potential_exposure_pct
                from app.psfalgo.exposure_threshold_service_v2 import get_exposure_threshold_service_v2
                _, cur_pct, pot_pct = await get_current_and_potential_exposure_pct(account_id)
                thresh_svc = get_exposure_threshold_service_v2()
                hard_risk = thresh_svc.is_hard_risk_mode(account_id, cur_pct, pot_pct)
                
                new_orders = []
                if not hard_risk:
                    # PATADD — same conditions as initial cycle
                    if self._is_engine_active('PATADD_ENGINE'):
                        patadd_refresh = await self._run_patadd(account_id, request)
                        new_orders.extend(patadd_refresh)
                    # ADDNEWPOS — same conditions as initial cycle
                    if self._is_engine_active('ADDNEWPOS_ENGINE'):
                        addnewpos_refresh = await self._run_addnewpos(account_id, request)
                        new_orders.extend(addnewpos_refresh)
                else:
                    logger.info("[XNL_ENGINE] Refresh: LT_INCREASE skipped (hard risk)")
            elif category == OrderTagCategory.LT_DECREASE:
                new_orders = await self._run_lt_trim(account_id, request)
                new_orders += await self._run_karbotu(account_id, request)
            elif category == OrderTagCategory.MM_INCREASE:
                new_orders = await self._run_mm(account_id, request)
            else:
                new_orders = []  # MM_DECREASE inactive
            
            if new_orders:
                await self._send_orders_with_frontlama(new_orders, account_id)
            
            logger.info(f"[XNL_ENGINE] Refresh cycle complete: sent {len(new_orders)} new orders")
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] Refresh cycle error: {e}", exc_info=True)
    
    async def _get_open_orders_by_category(
        self,
        category: OrderTagCategory,
        account_id: str
    ) -> List[Dict[str, Any]]:
        """Get open orders filtered by category.
        
        UNIFIED TAG FILTER — Works with all tag formats:
        ═══════════════════════════════════════════════════════════════════
        Dual v4:   MM_MM_LONG_INC, LT_PA_LONG_INC, MM_TRIM_SHORT_DEC
        REV v4:    REV_TP_MM_MM_SELL, REV_RL_LT_TRIM_BUY
        Frontlama: FR_MM_MM_LONG_INC, FR_LT_PA_LONG_INC
        Legacy:    MM_LONG_INC, LT_SHORT_DEC (backward compat)
        
        All tags use substring matching ('MM' in tag, 'DEC' in tag),
        so FR_ prefix, REV_ prefix, and extra POS tag don't break filtering.
        
        REV v4 tag mapping:
        - REV_TP_MM_MM_SELL → contains 'MM' (POS) → MM category
        - REV_RL_LT_TRIM_BUY → contains 'LT' (POS) → LT category
        """
        try:
            from app.psfalgo.order_manager import get_order_controller
            
            controller = get_order_controller()
            if not controller:
                return []
            
            all_orders = controller.get_active_orders(account_id=account_id)
            
            # Filter by category using substring matching
            # Works with: MM_MM_LONG_INC, LT_PA_LONG_INC, REV_TP_MM_MM_SELL,
            #             FR_MM_MM_LONG_INC, LT_KB_SHORT_DEC, etc.
            filtered = []
            for order in all_orders:
                tag = order.tag or ''
                tag_upper = tag.upper()
                
                matches = False
                
                # ═══════════════════════════════════════════════════════════
                # UNIFIED FILTER: substring match for POS + ACTION type
                # Catches: MM_MM_LONG_INC, REV_TP_MM_MM_SELL, FR_MM_MM_LONG_INC
                #          LT_PA_LONG_INC, LT_KB_SHORT_DEC, etc.
                # ═══════════════════════════════════════════════════════════
                if category == OrderTagCategory.LT_INCREASE:
                    matches = ('LT' in tag_upper or 'PAT' in tag_upper) and 'INC' in tag_upper
                elif category == OrderTagCategory.LT_DECREASE:
                    matches = ('LT' in tag_upper or 'KARBOTU' in tag_upper or 'HEAVY' in tag_upper) and 'DEC' in tag_upper
                elif category == OrderTagCategory.MM_INCREASE:
                    matches = 'MM' in tag_upper and 'INC' in tag_upper
                elif category == OrderTagCategory.MM_DECREASE:
                    matches = 'MM' in tag_upper and 'DEC' in tag_upper
                
                # ═══════════════════════════════════════════════════════════
                # LEGACY REV FALLBACK: Old tags like REV_IBKRPED_LONG_TP
                # These lack MM/LT and INC/DEC, so won't match above.
                # Route to MM_DECREASE (default, most common REV scenario).
                # ═══════════════════════════════════════════════════════════
                if not matches and 'REV' in tag_upper:
                    has_source = 'MM' in tag_upper or 'LT' in tag_upper
                    has_action = 'INC' in tag_upper or 'DEC' in tag_upper
                    
                    if not has_source or not has_action:
                        # Legacy REV tag — route TP→DECREASE, RELOAD→INCREASE
                        if '_TP' in tag_upper and category == OrderTagCategory.MM_DECREASE:
                            matches = True
                        elif 'RELOAD' in tag_upper and category == OrderTagCategory.MM_INCREASE:
                            matches = True
                
                if matches:
                    filtered.append({
                        'order_id': order.broker_order_id or order.order_id,
                        'symbol': order.symbol,
                        'action': order.action,
                        'quantity': order.lot_qty,
                        'price': order.price,
                        'tag': order.tag
                    })
            
            return filtered
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] Get orders error: {e}")
            return []
    
    async def _get_l1_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get L1 market data for a symbol with freshness guarantee.
        
        Priority:
        1. DataFabric in-memory (if fresh — updated within 120s)
        2. Redis market:l1:{symbol} (L1Feed Terminal streaming — 2s refresh)
        3. market_data_cache (Hammer L1Update handler)
        4. DataFabric in-memory (stale — as last resort)
        """
        stale_data = None  # Hold stale data as last resort
        
        try:
            from app.core.data_fabric import get_data_fabric
            
            fabric = get_data_fabric()
            if fabric:
                live = fabric._live_data.get(symbol, {})
                if live and live.get('bid') is not None and live.get('ask') is not None:
                    bid = live.get('bid', 0)
                    ask = live.get('ask', 0)
                    if bid > 0 and ask > 0:
                        # Check freshness
                        last_update = live.get('_last_update')
                        is_fresh = False
                        if last_update:
                            from datetime import datetime
                            age = (datetime.now() - last_update).total_seconds() if hasattr(last_update, 'total_seconds') is False else 0
                            try:
                                age = (datetime.now() - last_update).total_seconds()
                                is_fresh = age < 120  # 2 minutes
                            except Exception:
                                is_fresh = True  # Assume fresh if can't check
                        else:
                            is_fresh = True  # No timestamp = assume fresh
                        
                        data = {'bid': bid, 'ask': ask, 'last': live.get('last', 0)}
                        if is_fresh:
                            return data
                        else:
                            stale_data = data  # Save as fallback
        except Exception as e:
            logger.debug(f"[XNL_ENGINE] DataFabric L1 error for {symbol}: {e}")
        
        # Layer 2: Redis market:l1:{symbol} (L1Feed Terminal streaming data)
        try:
            import json as _json
            from app.core.redis_client import get_redis_client
            from app.live.symbol_mapper import SymbolMapper
            redis_client = get_redis_client()
            if redis_client:
                r = redis_client.sync if hasattr(redis_client, 'sync') else redis_client
                # 🔑 TICKER CONVENTION: Try both Hammer and PREF_IBKR formats
                _h_sym = SymbolMapper.to_hammer_symbol(symbol)
                _d_sym = SymbolMapper.to_display_symbol(symbol)
                for _try_sym in dict.fromkeys([symbol, _h_sym, _d_sym]):
                    val = r.get(f"market:l1:{_try_sym}")
                    if val:
                        l1 = _json.loads(val if isinstance(val, str) else val.decode('utf-8'))
                        bid = l1.get('bid')
                        ask = l1.get('ask')
                        if bid and ask and float(bid) > 0 and float(ask) > 0:
                            return {'bid': float(bid), 'ask': float(ask), 'last': float(l1.get('last', 0))}
        except Exception as e:
            logger.debug(f"[XNL_ENGINE] Redis L1 error for {symbol}: {e}")
        
        # Layer 3: market_data_cache (Hammer L1Update handler in main app)
        try:
            from app.api.market_data_routes import market_data_cache
            if market_data_cache and symbol in market_data_cache:
                cached = market_data_cache[symbol]
                bid = cached.get('bid')
                ask = cached.get('ask')
                if bid is not None and ask is not None and float(bid) > 0 and float(ask) > 0:
                    return {'bid': float(bid), 'ask': float(ask), 'last': float(cached.get('last', 0))}
        except Exception:
            pass
        
        # Layer 4: Return stale data as last resort (better than nothing)
        if stale_data:
            logger.debug(f"[XNL_ENGINE] Using STALE L1 data for {symbol} (no fresh source available)")
            return stale_data
        
        return None
    
    async def _get_truth_tick_data(self, symbol: str) -> tuple:
        """
        BACKWARD COMPAT WRAPPER: returns single (price, venue, size) tuple.
        Delegates to _get_truth_ticks_list and returns the most recent valid tick.
        """
        ticks = await self._get_truth_ticks_list(symbol)
        if ticks:
            t = ticks[0]  # newest first
            return (t['price'], t['venue'], t['size'])
        return None, None, None
    
    async def _get_truth_ticks_list(self, symbol: str, count: int = 5) -> list:
        """
        Get the last N REAL truth ticks from Redis for a symbol.
        
        PRIMARY: tt:ticks:{symbol} (TruthTicksEngine, 12-day TTL, always available)
        FALLBACK: truthtick:latest:{symbol} (worker, 10-min TTL, may expire)
        
        Returns:
            List of dicts, newest first: [{'price', 'venue', 'size', 'ts'}, ...]
            Empty list if no valid ticks found.
        """
        try:
            import json
            import time
            from app.core.redis_client import get_redis_client
            
            redis_client = get_redis_client()
            if not redis_client:
                return []
            
            redis_sync = getattr(redis_client, 'sync', redis_client)
            
            # PRIMARY: tt:ticks:{symbol} — canonical source (12-day TTL)
            key = f"tt:ticks:{symbol}"
            data = redis_sync.get(key)
            
            if data:
                raw = data.decode() if isinstance(data, bytes) else data
                ticks = json.loads(raw)
                
                if ticks and isinstance(ticks, list):
                    now = time.time()
                    valid_ticks = []
                    
                    # Iterate from newest to oldest (list is chronological)
                    for tick in reversed(ticks):
                        tick_ts = tick.get('ts', 0)
                        
                        # Allow up to 24 hours (illiquid stocks + overnight)
                        if tick_ts > 0:
                            age = now - tick_ts
                            if age > 86400:
                                continue
                        
                        price = float(tick.get('price', 0))
                        size = float(tick.get('size', 0))
                        venue = str(tick.get('exch', tick.get('venue', '')))
                        
                        if price > 0 and size > 0:
                            valid_ticks.append({
                                'price': price,
                                'venue': venue,
                                'size': size,
                                'ts': tick_ts
                            })
                        
                        if len(valid_ticks) >= count:
                            break
                    
                    if valid_ticks:
                        return valid_ticks  # Already newest-first (from reversed)
            
            # FALLBACK: truthtick:latest:{symbol} (legacy, short TTL)
            legacy_key = f"truthtick:latest:{symbol}"
            legacy_data = redis_sync.get(legacy_key)
            
            if legacy_data:
                raw = legacy_data.decode() if isinstance(legacy_data, bytes) else legacy_data
                tick = json.loads(raw)
                price = float(tick.get('price', 0))
                size = float(tick.get('size', 0))
                venue = str(tick.get('venue', tick.get('exch', '')))
                tick_ts = float(tick.get('ts', 0))
                # ⚠️ STALENESS CHECK: same 24h limit as primary source
                if price > 0 and size > 0:
                    if tick_ts > 0 and (time.time() - tick_ts) > 86400:
                        return []  # STALE — reject
                    return [{'price': price, 'venue': venue, 'size': size, 'ts': tick_ts}]
            
            return []
            
        except Exception as e:
            logger.debug(f"[XNL_ENGINE] Truth ticks fetch error for {symbol}: {e}")
            return []
    
    def _refresh_minmax_current_qty(self, minmax_svc, account_id: str):
        """Refresh MinMax cache current_qty from REAL Redis positions.
        
        Only updates current_qty — daily bands (todays_max/min) stay FIXED.
        This is much cheaper than compute_for_account(force=True).
        """
        try:
            import json as _json
            from app.core.redis_client import get_redis_client
            r = get_redis_client()
            if not r:
                return
            
            pos_key = f"psfalgo:positions:{account_id}"
            raw = r.get(pos_key)
            if not raw:
                return
            
            positions = _json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            acct_cache = minmax_svc._cache_by_account.get(account_id, {})
            
            updated = 0
            for sym, row in acct_cache.items():
                pos_data = positions.get(sym)
                if pos_data and isinstance(pos_data, dict):
                    real_qty = float(pos_data.get('qty', 0) or 0)
                    if row.current_qty != real_qty:
                        row.current_qty = real_qty
                        updated += 1
            
            if updated > 0:
                logger.debug(
                    f"[XNL_ENGINE] MinMax current_qty refreshed: {updated} symbols "
                    f"updated from Redis (bands unchanged)"
                )
        except Exception as e:
            logger.debug(f"[XNL_ENGINE] MinMax refresh error: {e}")
    
    async def _place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        price: float,
        tag: str,
        account_id: str
    ) -> bool:
        """Place an order and register it with OrderController for frontlama tracking."""
        try:
            # ═══════════════════════════════════════════════════════════════
            # MARKET HOURS GUARD — Block ALL orders outside regular hours
            # After-hours fills are catastrophic due to wide spreads.
            # WRB-F 2026-03-11: SELL @$18.15 when TT ~$20 (after-hours)
            # ═══════════════════════════════════════════════════════════════
            from app.trading.hammer_execution_service import _is_us_market_open
            if not _is_us_market_open():
                logger.warning(
                    f"🚫 [MARKET_CLOSED] Order BLOCKED — market is closed! "
                    f"{symbol} {action} {quantity} @ ${price:.4f} (Tag: {tag}, Account: {account_id})"
                )
                return False
            
            from app.psfalgo.account_mode import AccountMode
            
            broker_order_id = None
            success = False
            
            if 'HAMPRO' in account_id.upper():
                from app.trading.hammer_execution_service import get_hammer_execution_service
                service = get_hammer_execution_service()
                if service:
                    # Hammer API is async: order confirmation comes via transactionsUpdate
                    # No need to wait for response - fire_and_forget speeds up order flow significantly
                    result = service.place_order_venue_routed(
                        symbol=symbol,
                        side=action,
                        quantity=quantity,
                        price=price,
                        order_style='LIMIT',
                        hidden=True,
                        strategy_tag=tag,
                        fire_and_forget=True  # Hammer is async - confirmation via transactionsUpdate
                    )
                    success = result.get('success', False)
                    broker_order_id = str(result.get('order_id') or result.get('OrderID') or '') if success else None
            else:
                # Use place_order_isolated_sync (runs on IB thread, not generic executor)
                # Same safe pattern as get_positions_isolated_sync, cancel_orders_isolated_sync etc.
                from app.psfalgo.ibkr_connector import get_ibkr_connector, place_order_isolated_sync
                conn = get_ibkr_connector(account_type=account_id, create_if_missing=False)
                
                conn_exists = conn is not None
                is_conn = conn.connected if conn else False
                logger.info(f"[XNL_ENGINE] IBKR _place_order debug: account={account_id}, conn_exists={conn_exists}, is_connected={is_conn}")
                
                if conn and conn.connected:
                    # ═══════════════════════════════════════════════════════════
                    # IBKR action normalization
                    # IBKR TWS API only accepts 'BUY' and 'SELL'.
                    # ═══════════════════════════════════════════════════════════
                    ibkr_action = action.upper()
                    if ibkr_action in ('SHORT', 'ADD_SHORT', 'SELL_SHORT', 'SSHORT'):
                        ibkr_action = 'SELL'
                    elif ibkr_action in ('COVER', 'BUY_TO_COVER', 'ADD'):
                        ibkr_action = 'BUY'
                    elif ibkr_action not in ('BUY', 'SELL'):
                        logger.warning(f"[XNL_ENGINE] Unknown action '{action}' for IBKR, defaulting to SELL")
                        ibkr_action = 'SELL'
                    
                    # ── Venue routing with chunk splitting ──
                    from app.trading.venue_router import get_venue_router
                    vr = get_venue_router()
                    chunks = vr.route_order(symbol, int(quantity))
                    
                    from app.core.order_context_logger import format_order_sent_log, get_order_context
                    _ctx = get_order_context(symbol)
                    
                    if len(chunks) == 1:
                        # Single order (< 400 lots) — standard path
                        ibkr_exchange = chunks[0].routing_ibkr
                        contract_details = {
                            'symbol': symbol, 'secType': 'STK',
                            'exchange': ibkr_exchange, 'currency': 'USD'
                        }
                        order_details = {
                            'action': ibkr_action,
                            'totalQuantity': quantity,
                            'orderType': 'LMT',
                            'lmtPrice': price,
                            'strategy_tag': tag if tag else 'XNL'
                        }
                        logger.info(format_order_sent_log(symbol, action, quantity, price, tag, account_id, ctx=_ctx))
                        import asyncio
                        loop = asyncio.get_running_loop()
                        result = await loop.run_in_executor(
                            None,
                            lambda: place_order_isolated_sync(account_id, contract_details, order_details)
                        )
                        success = result.get('success', False) if result else False
                        broker_order_id = str(result.get('order_id') or result.get('orderId') or '') if success else None
                        logger.info(f"[XNL_ENGINE] IBKR order result: {symbol} → success={success}")
                    else:
                        # Multiple chunks (>= 400 lots) — venue-routed split
                        logger.info(
                            f"[XNL_ENGINE] IBKR VENUE SPLIT: {symbol} {ibkr_action} {quantity} "
                            f"→ {len(chunks)} chunks"
                        )
                        import asyncio
                        loop = asyncio.get_running_loop()
                        all_success = True
                        last_order_id = None
                        
                        for chunk in chunks:
                            route_label = chunk.routing_ibkr
                            # Each chunk gets unique tag suffix (_CH0, _CH1) to prevent
                            # duplicate detection from blocking sibling chunks
                            chunk_tag = f"{tag}_CH{chunk.chunk_index}" if tag else f"XNL_CH{chunk.chunk_index}"
                            contract_details = {
                                'symbol': symbol, 'secType': 'STK',
                                'exchange': route_label, 'currency': 'USD'
                            }
                            order_details = {
                                'action': ibkr_action,
                                'totalQuantity': chunk.qty,
                                'orderType': 'LMT',
                                'lmtPrice': price,
                                'strategy_tag': chunk_tag
                            }
                            logger.info(
                                f"  📦 IBKR Chunk {chunk.chunk_index}: "
                                f"{ibkr_action} {chunk.qty} @ ${price:.4f} → {route_label}"
                            )
                            logger.info(format_order_sent_log(
                                symbol, action, chunk.qty, price,
                                f"{chunk_tag}|{route_label}", account_id, ctx=_ctx
                            ))
                            # Capture chunk values for lambda
                            _cd = dict(contract_details)
                            _od = dict(order_details)
                            result = await loop.run_in_executor(
                                None,
                                lambda cd=_cd, od=_od: place_order_isolated_sync(account_id, cd, od)
                            )
                            chunk_ok = result.get('success', False) if result else False
                            if chunk_ok:
                                last_order_id = str(result.get('order_id') or result.get('orderId') or '')
                            else:
                                all_success = False
                                logger.warning(f"  ❌ IBKR Chunk {chunk.chunk_index} FAILED: {symbol} {route_label}")
                        
                        success = all_success
                        broker_order_id = last_order_id
                        logger.info(f"[XNL_ENGINE] IBKR venue split result: {symbol} → all_success={all_success}")
                else:
                    logger.warning(f"[XNL_ENGINE] ❌ IBKR not connected! Cannot place order for {symbol}. conn={conn_exists}, connected={is_conn}")
            
            # ═══════════════════════════════════════════════════════════
            # CRITICAL: Register with OrderController so frontlama can
            # find and modify these orders via _get_open_orders_by_category.
            # Without this, front cycle sees ZERO orders → frontlama is dead.
            # ═══════════════════════════════════════════════════════════
            if success:
                try:
                    from app.psfalgo.order_manager import get_order_controller, TrackedOrder, OrderStatus
                    controller = get_order_controller()
                    if controller:
                        import uuid
                        intent_id = str(uuid.uuid4())[:12]
                        tracked = TrackedOrder(
                            order_id=intent_id,
                            symbol=symbol,
                            action=action,
                            order_type='LIMIT',
                            lot_qty=quantity,
                            price=price,
                            status=OrderStatus.SENT,
                            remaining_qty=quantity,
                            provider=account_id,
                            broker_order_id=broker_order_id or intent_id,
                            tag=tag,
                        )
                        controller.track_order(tracked)
                        logger.debug(f"[XNL_ENGINE] Tracked order: {symbol} {action} {quantity} @ {price} tag={tag}")
                except Exception as track_err:
                    # Non-fatal: order was sent, just tracking failed
                    logger.debug(f"[XNL_ENGINE] Order tracking failed (non-fatal): {track_err}")
            
            return success
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] Place order error: {e}")
            return False
    
    async def _cancel_order(self, order_id: str, account_id: str) -> bool:
        """Cancel an order. Uses isolated sync for IBKR to avoid event loop issues."""
        try:
            if 'HAMPRO' in (account_id or '').upper():
                from app.trading.hammer_execution_service import get_hammer_execution_service
                service = get_hammer_execution_service()
                if service:
                    result = service.cancel_order(order_id)
                    return result.get('success', False)
            else:
                from app.psfalgo.ibkr_connector import cancel_orders_isolated_sync
                loop = asyncio.get_event_loop()
                cancelled_list = await loop.run_in_executor(
                    None, lambda: cancel_orders_isolated_sync(account_id, [int(order_id)])
                )
                return str(order_id) in (cancelled_list or [])

            return False

        except Exception as e:
            logger.error(f"[XNL_ENGINE] Cancel order error: {e}")
            return False
    
    async def _modify_order_price(self, order_id: str, new_price: float, account_id: str) -> bool:
        """
        ATOMIC order modify — same order ID preserved, no cancel gap.
        
        Hammer Pro: Uses tradeCommandModify (single API call, same OrderID).
        IBKR: Uses placeOrder with existing orderId (native IBKR modify).
        """
        try:
            if 'HAMPRO' in (account_id or '').upper():
                from app.trading.hammer_execution_service import get_hammer_execution_service
                service = get_hammer_execution_service()
                if service:
                    result = service.modify_order(order_id, new_price)
                    return result.get('success', False)
            else:
                # IBKR: Atomic modify via placeOrder with same orderId
                from app.psfalgo.ibkr_connector import modify_order_isolated_sync
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: modify_order_isolated_sync(
                        account_type=account_id,
                        order_id=int(order_id),
                        new_price=float(new_price)
                    )
                )
                success = result.get('success', False) if result else False
                if success:
                    logger.info(f"[XNL_ENGINE] ✅ IBKR ATOMIC modify order {order_id} → ${new_price:.4f}")
                return success

            return False

        except ImportError:
            logger.warning(f"[XNL_ENGINE] modify_order_isolated_sync not available for IBKR, returning False")
            return False  # Let caller handle cancel+replace fallback
        except Exception as e:
            logger.error(f"[XNL_ENGINE] Modify order error: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # CANCEL METHODS (for UI buttons)
    # ═══════════════════════════════════════════════════════════════════════
    
    async def _get_broker_open_orders(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Fetch open orders from the broker (IBKR or Hammer), not from order_controller.
        Same source as janall/orders so cancel sees the same orders as the UI.
        Returns list of dicts with order_id, action, strategy_tag, order_ref, tag, etc.
        """
        if 'HAMPRO' in (account_id or '').upper():
            try:
                from app.api.trading_routes import get_hammer_services
                orders_svc, _ = get_hammer_services()
                if orders_svc:
                    raw = orders_svc.get_open_orders()
                    return list(raw) if isinstance(raw, list) else []
            except Exception as e:
                logger.warning(f"[XNL_ENGINE] Hammer get_open_orders: {e}")
            return []
        # IBKR_PED / IBKR_GUN
        try:
            import json
            from app.psfalgo.ibkr_connector import get_open_orders_isolated_sync
            from app.core.redis_client import get_redis_client
            loop = asyncio.get_event_loop()
            ib_list = await loop.run_in_executor(None, lambda: get_open_orders_isolated_sync(account_id))
            all_orders = {o.get('order_id'): o for o in (ib_list or []) if o.get('order_id') is not None}
            r = get_redis_client()
            if r and hasattr(r, 'get'):
                key = f"psfalgo:open_orders:{account_id}"
                raw = r.get(key)
                if raw:
                    s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                    parsed = json.loads(s) if isinstance(s, str) else s
                    # Handle wrapped format vs legacy list
                    if isinstance(parsed, dict) and 'orders' in parsed:
                        redis_list = parsed['orders']
                    elif isinstance(parsed, list):
                        redis_list = parsed
                    else:
                        redis_list = []
                    if isinstance(redis_list, list):
                        for o in redis_list:
                            oid = o.get('order_id')
                            if oid is not None and oid not in all_orders:
                                all_orders[oid] = o
            return list(all_orders.values())
        except Exception as e:
            logger.warning(f"[XNL_ENGINE] Broker open orders fetch: {e}")
        return []

    async def cancel_by_filter(
        self,
        account_id: str,
        filter_type: str,
        rev_excluded: bool
    ) -> Dict[str, int]:
        """
        Cancel orders by filter: incr, decr, sells, buys, lt, mm, tum.
        rev_excluded: when True, exclude orders whose tag contains REV.
        Uses open orders from BROKER (IBKR/Hammer), not order_controller, so all
        visible open orders can be cancelled by tag/side.
        """
        try:
            all_orders = await self._get_broker_open_orders(account_id)
            if not all_orders:
                logger.info(f"[XNL_ENGINE] Cancel by filter {filter_type!r}: no open orders from broker")
                return {'cancelled': 0, 'failed': 0}

            def order_tag(o: Dict[str, Any]) -> str:
                return (o.get('strategy_tag') or o.get('order_ref') or o.get('tag') or '').upper()

            def order_side(o: Dict[str, Any]) -> str:
                a = (o.get('action') or o.get('side') or '').upper()
                if a in ('SELL', 'SHORT'):
                    return 'SELL'
                if a in ('BUY', 'COVER'):
                    return 'BUY'
                return a

            def matches_filter(o: Dict[str, Any], ft: str) -> bool:
                tag = order_tag(o)
                book = (o.get('book') or '').upper()
                ft = (ft or '').lower()
                if ft == 'tum':
                    return True
                if ft == 'incr':
                    # Tag formats: MM_LONG_INCREASE, LT_LONG_INC, LT_SHORT_INC
                    return 'INC' in tag  # Matches both _INC and _INCREASE
                if ft == 'decr':
                    # Tag formats: LT_LONG_DECREASE, LT_LONG_DEC, HEAVYLONGDEC, HEAVYSHORTDEC
                    return 'DEC' in tag  # Matches _DEC, _DECREASE, HEAVYLONGDEC
                if ft == 'sells':
                    return order_side(o) == 'SELL'
                if ft == 'buys':
                    return order_side(o) == 'BUY'
                if ft == 'lt':
                    return 'LT' in tag or book == 'LT'
                if ft == 'mm':
                    return 'MM' in tag or book == 'MM'
                return False

            def is_rev(o: Dict[str, Any]) -> bool:
                return 'REV' in order_tag(o)

            orders_to_cancel = [
                o for o in all_orders
                if matches_filter(o, filter_type) and (not rev_excluded or not is_rev(o))
            ]

            cancelled = 0
            failed = 0
            cancelled_ids: List[Any] = []
            
            # OPTIMIZATION: Use batch cancel for Hammer when cancelling all (tum)
            # Even when rev_excluded=True, batch cancel is MUCH faster than one-by-one.
            # Strategy: batch cancel ALL → then re-send REV orders that were unintentionally cancelled.
            if filter_type.lower() == 'tum' and 'HAMPRO' in (account_id or '').upper():
                from app.trading.hammer_execution_service import get_hammer_execution_service
                service = get_hammer_execution_service()
                if service:
                    # Collect REV orders BEFORE batch cancel (so we can re-send them)
                    rev_orders_to_preserve = []
                    if rev_excluded:
                        rev_orders_to_preserve = [o for o in all_orders if is_rev(o)]
                        if rev_orders_to_preserve:
                            logger.info(
                                f"[XNL_ENGINE] Hammer batch cancel: preserving {len(rev_orders_to_preserve)} REV orders"
                            )
                    
                    # Batch cancel ALL orders (fast — single API call)
                    result = service.cancel_all_orders(side=None)
                    cancelled = result.get('cancelled_count', len(result.get('cancelled', [])))
                    cancelled_ids = result.get('cancelled', [])
                    self.state.total_orders_cancelled += cancelled
                    logger.info(f"[XNL_ENGINE] Hammer batch cancel: {cancelled} orders")
                    
                    # Notify exposure calculator: pending orders are stale for 15s
                    from app.psfalgo.exposure_calculator import notify_global_cancel_issued
                    notify_global_cancel_issued()
                    
                    # ═══════════════════════════════════════════════════════════
                    # CRITICAL: Clear Redis open orders IMMEDIATELY after cancel.
                    # Without this, potential_qty = qty + net_open_orders uses
                    # stale cancelled orders for ~5s until PositionRedisWorker
                    # refreshes, causing engines to see wrong effective_qty.
                    # IBKR already does this (line ~3110); Hammer was missing it.
                    # ═══════════════════════════════════════════════════════════
                    try:
                        from app.core.redis_client import get_redis_client
                        import json as _json
                        import time as _time
                        _r = get_redis_client()
                        if _r:
                            _orders_key = f"psfalgo:open_orders:{account_id}"
                            _empty_payload = {'orders': [], '_meta': {'updated_at': _time.time(), 'cleared_by': 'cancel_all'}}
                            _r.set(_orders_key, _json.dumps(_empty_payload), ex=600)
                            logger.info(f"[XNL_ENGINE] ✅ Redis open orders cleared for {account_id} (post-cancel)")
                    except Exception as _rc_err:
                        logger.warning(f"[XNL_ENGINE] Redis open orders clear failed: {_rc_err}")
                    
                    # Re-send preserved REV orders (they were cancelled by batch)
                    resent_rev = 0
                    for rev_o in rev_orders_to_preserve:
                        try:
                            sym = rev_o.get('symbol', '')
                            action = (rev_o.get('action') or rev_o.get('side') or 'BUY').upper()
                            qty = int(rev_o.get('quantity') or rev_o.get('qty') or 0)
                            price = float(rev_o.get('price') or 0)
                            tag = (rev_o.get('strategy_tag') or rev_o.get('order_ref') or rev_o.get('tag') or 'REV')
                            if qty > 0 and price > 0:
                                place_result = service.place_order(
                                    symbol=sym, side=action, quantity=qty,
                                    price=price, order_style='LIMIT',
                                    hidden=True, strategy_tag=tag, fire_and_forget=True
                                )
                                if place_result.get('success', False):
                                    resent_rev += 1
                                await asyncio.sleep(ORDER_SEND_DELAY_SEC)
                        except Exception as rev_err:
                            logger.warning(f"[XNL_ENGINE] REV re-send error for {rev_o.get('symbol')}: {rev_err}")
                    
                    if resent_rev > 0:
                        logger.info(f"[XNL_ENGINE] ✅ Re-sent {resent_rev}/{len(rev_orders_to_preserve)} REV orders after batch cancel")
                    
                    actual_cancelled = cancelled - resent_rev
                    return {'cancelled': max(actual_cancelled, 0), 'failed': 0}
            
            # ═══════════════════════════════════════════════════════════════
            # OPTIMIZATION: IBKR batch cancel using reqGlobalCancel when "tum"
            # Same strategy as Hammer: batch cancel ALL → re-send REV orders
            #
            # CRITICAL FIX (VLYPO-3017): reqGlobalCancel is ASYNC — IBKR
            # queues cancels but doesn't complete them instantly. We MUST:
            #   1. Call reqGlobalCancel
            #   2. WAIT for broker to process (2.5s)
            #   3. VERIFY remaining orders via openTrades()
            #   4. Retry if orders remain
            #   5. ONLY clear Redis AFTER broker confirmation
            # ═══════════════════════════════════════════════════════════════
            if filter_type.lower() == 'tum' and 'IBKR' in (account_id or '').upper():
                try:
                    from app.psfalgo.ibkr_connector import (
                        global_cancel_isolated_sync,
                        get_open_orders_isolated_sync,
                        _clear_redis_open_orders_for_account,
                    )
                    
                    # Collect REV orders BEFORE batch cancel
                    rev_orders_to_preserve = []
                    if rev_excluded:
                        rev_orders_to_preserve = [o for o in all_orders if is_rev(o)]
                        if rev_orders_to_preserve:
                            logger.info(
                                f"[XNL_ENGINE] IBKR batch cancel: preserving {len(rev_orders_to_preserve)} REV orders"
                            )
                    
                    # Step 1: Batch cancel ALL (reqGlobalCancel — fire-and-forget)
                    ok = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: global_cancel_isolated_sync(account_id)
                    )
                    if ok:
                        cancelled = len(all_orders)
                        self.state.total_orders_cancelled += cancelled
                        logger.info(f"[XNL_ENGINE] IBKR reqGlobalCancel issued: ~{cancelled} orders")
                        
                        # Step 2: WAIT for IBKR broker to process cancellations
                        # reqGlobalCancel is ASYNC — broker queues cancels but does NOT
                        # complete them instantly. Without this wait, new orders sent in
                        # the initial cycle will PILE UP with old unfilled orders.
                        IBKR_CANCEL_WAIT_SECONDS = 2.5
                        logger.info(
                            f"[XNL_ENGINE] ⏳ Waiting {IBKR_CANCEL_WAIT_SECONDS}s for IBKR "
                            f"broker to process reqGlobalCancel..."
                        )
                        await asyncio.sleep(IBKR_CANCEL_WAIT_SECONDS)
                        
                        # Step 3: VERIFY — check remaining orders via openTrades()
                        remaining_orders = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: get_open_orders_isolated_sync(account_id)
                        )
                        remaining_count = len(remaining_orders) if remaining_orders else 0
                        
                        # Exclude REV orders from remaining count (they'll be re-sent)
                        if rev_excluded and remaining_orders:
                            non_rev_remaining = [o for o in remaining_orders if not is_rev(o)]
                            remaining_count = len(non_rev_remaining)
                        
                        if remaining_count > 0:
                            # Step 3b: Retry — some orders survived reqGlobalCancel
                            logger.warning(
                                f"[XNL_ENGINE] ⚠️ IBKR reqGlobalCancel incomplete: "
                                f"{remaining_count} non-REV orders still open! Retrying..."
                            )
                            # Second reqGlobalCancel attempt
                            await asyncio.get_event_loop().run_in_executor(
                                None, lambda: global_cancel_isolated_sync(account_id)
                            )
                            await asyncio.sleep(2.0)  # Wait for retry
                            
                            # Final verification
                            remaining2 = await asyncio.get_event_loop().run_in_executor(
                                None, lambda: get_open_orders_isolated_sync(account_id)
                            )
                            remaining2_count = len(remaining2) if remaining2 else 0
                            if remaining2_count > 0:
                                logger.error(
                                    f"[XNL_ENGINE] 🔴 IBKR cancel FAILED: still {remaining2_count} "
                                    f"orders after 2 reqGlobalCancel attempts!"
                                )
                            else:
                                logger.info("[XNL_ENGINE] ✅ IBKR cancel verified on retry — all orders cleared")
                        else:
                            logger.info("[XNL_ENGINE] ✅ IBKR cancel verified — 0 remaining orders")
                        
                        # Notify exposure calculator: pending orders are stale for 15s
                        from app.psfalgo.exposure_calculator import notify_global_cancel_issued
                        notify_global_cancel_issued()
                        
                        # Step 4: NOW clear Redis (ONLY after broker confirmation)
                        try:
                            _clear_redis_open_orders_for_account(account_id)
                        except Exception:
                            pass
                        
                        # Re-send preserved REV orders
                        resent_rev = 0
                        for rev_o in rev_orders_to_preserve:
                            try:
                                from app.psfalgo.ibkr_connector import get_ibkr_connector, place_order_isolated_sync
                                conn = get_ibkr_connector(account_type=account_id, create_if_missing=False)
                                if conn and conn.connected:
                                    cd = {'symbol': rev_o.get('symbol', ''), 'secType': 'STK', 'exchange': 'SMART', 'currency': 'USD'}
                                    od = {
                                        'action': (rev_o.get('action') or rev_o.get('side') or 'BUY').upper(),
                                        'totalQuantity': int(rev_o.get('quantity') or rev_o.get('qty') or 0),
                                        'lmtPrice': float(rev_o.get('price') or 0),
                                        'strategy_tag': rev_o.get('strategy_tag') or rev_o.get('order_ref') or 'REV',
                                    }
                                    if od['totalQuantity'] > 0 and od['lmtPrice'] > 0:
                                        # FIX: Bind loop variables via default args to avoid closure-over-loop-variable bug
                                        place_result = await asyncio.get_event_loop().run_in_executor(
                                            None, lambda _aid=account_id, _cd=cd, _od=od: place_order_isolated_sync(_aid, _cd, _od)
                                        )
                                        if place_result and place_result.get('success', False):
                                            resent_rev += 1
                                        await asyncio.sleep(ORDER_SEND_DELAY_SEC)
                            except Exception as rev_err:
                                logger.warning(f"[XNL_ENGINE] IBKR REV re-send error for {rev_o.get('symbol')}: {rev_err}")
                        
                        if resent_rev > 0:
                            logger.info(f"[XNL_ENGINE] ✅ Re-sent {resent_rev}/{len(rev_orders_to_preserve)} REV orders after IBKR batch cancel")
                        
                        actual_cancelled = cancelled - resent_rev
                        return {'cancelled': max(actual_cancelled, 0), 'failed': 0}
                    else:
                        logger.warning("[XNL_ENGINE] IBKR reqGlobalCancel returned False, falling back to one-by-one")
                except Exception as ibkr_batch_err:
                    logger.warning(f"[XNL_ENGINE] IBKR batch cancel error, falling back: {ibkr_batch_err}")
            
            # Standard one-by-one cancel (for filtered cancels or batch-cancel fallback)
            for o in orders_to_cancel:
                try:
                    order_id = o.get('order_id')
                    if order_id is None:
                        failed += 1
                        continue
                    success = await self._cancel_order(str(order_id), account_id)
                    if success:
                        cancelled += 1
                        cancelled_ids.append(order_id)
                        self.state.total_orders_cancelled += 1
                    else:
                        failed += 1
                    await asyncio.sleep(ORDER_SEND_DELAY_SEC)
                except Exception as e:
                    logger.error(f"[XNL_ENGINE] Cancel error: {e}")
                    failed += 1

            # Remove cancelled order IDs from Redis so UI refetch shows correct list
            if cancelled_ids and 'HAMPRO' not in (account_id or '').upper():
                try:
                    import json
                    from app.core.redis_client import get_redis_client
                    r = get_redis_client()
                    if r and hasattr(r, 'get') and hasattr(r, 'set'):
                        key = f"psfalgo:open_orders:{account_id}"
                        raw = r.get(key)
                        if raw:
                            s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                            parsed = json.loads(s) if isinstance(s, str) else s
                            # Handle wrapped format vs legacy list
                            if isinstance(parsed, dict) and 'orders' in parsed:
                                redis_list = parsed['orders']
                            elif isinstance(parsed, list):
                                redis_list = parsed
                            else:
                                redis_list = []
                            if isinstance(redis_list, list):
                                ids_set = {int(x) for x in cancelled_ids} | {str(x) for x in cancelled_ids}
                                new_list = [o for o in redis_list if o.get('order_id') not in ids_set]
                                import time as _time
                                payload = {'orders': new_list, '_meta': {'updated_at': _time.time()}}
                                r.set(key, json.dumps(payload), ex=600)
                                logger.info(f"[XNL_ENGINE] Removed {len(cancelled_ids)} order IDs from Redis {key}")
                except Exception as redis_err:
                    logger.debug(f"[XNL_ENGINE] Redis cleanup after cancel: {redis_err}")

            logger.info(f"[XNL_ENGINE] Cancel by filter {filter_type!r} (rev_excluded={rev_excluded}): {cancelled} cancelled, {failed} failed (broker orders={len(all_orders)})")
            return {'cancelled': cancelled, 'failed': failed}

        except Exception as e:
            logger.error(f"[XNL_ENGINE] Cancel by filter error: {e}", exc_info=True)
            return {'cancelled': 0, 'failed': 0}
    
    async def _cancel_orders_by_side(
        self,
        account_id: str,
        side: Optional[str]
    ) -> Dict[str, int]:
        """Cancel orders filtered by side.
        
        Uses BROKER open orders (same source as cancel_by_filter) so we cancel
        ALL visible orders, not just internally-tracked ones.
        
        Called by: ETF Guard Terminal for emergency cancel (CANCEL_BUYS / CANCEL_SELLS)
        
        OPTIMIZATION (v2): Uses batch cancel for speed:
        - HAMPRO: cancel_all_orders(side=...) — single API call (~1s vs ~97s)
        - IBKR: batch cancel_orders_isolated_sync — all IDs in one call
        """
        try:
            # Use BROKER open orders — same as cancel_by_filter
            all_orders = await self._get_broker_open_orders(account_id)
            if not all_orders:
                return {'cancelled': 0, 'failed': 0}
            
            # Filter by side to count matching orders
            if side:
                side_upper = side.upper()
                orders_to_cancel = []
                for o in all_orders:
                    a = (o.get('action') or o.get('side') or '').upper()
                    if side_upper == 'BUY' and a in ('BUY', 'COVER'):
                        orders_to_cancel.append(o)
                    elif side_upper == 'SELL' and a in ('SELL', 'SHORT'):
                        orders_to_cancel.append(o)
            else:
                orders_to_cancel = all_orders
            
            if not orders_to_cancel:
                logger.info(f"[XNL_ENGINE] Cancel by side ({side}): no matching orders")
                return {'cancelled': 0, 'failed': 0}
            
            cancelled = 0
            failed = 0
            
            # ═══════════════════════════════════════════════════════════════
            # HAMPRO BATCH CANCEL — single API call via cancel_all_orders
            # ~1 second vs ~97 seconds (one-by-one with 3-5s timeout each)
            # ═══════════════════════════════════════════════════════════════
            if 'HAMPRO' in (account_id or '').upper():
                try:
                    from app.trading.hammer_execution_service import get_hammer_execution_service
                    service = get_hammer_execution_service()
                    if service:
                        result = service.cancel_all_orders(side=side)
                        if result.get('success'):
                            cancelled = len(result.get('cancelled', []))
                            if cancelled == 0:
                                # cancel_all_orders returns cancelled as list of IDs
                                # Some versions return count in 'message'
                                cancelled = len(orders_to_cancel)
                            self.state.total_orders_cancelled += cancelled
                            logger.info(f"[XNL_ENGINE] Cancel by side ({side}): BATCH {cancelled} cancelled on {account_id}")
                            return {'cancelled': cancelled, 'failed': 0}
                        else:
                            logger.warning(f"[XNL_ENGINE] Hammer batch cancel failed: {result.get('message')}, falling back to one-by-one")
                except Exception as batch_err:
                    logger.warning(f"[XNL_ENGINE] Hammer batch cancel error, falling back: {batch_err}")
            
            # ═══════════════════════════════════════════════════════════════
            # IBKR BATCH CANCEL — send all order IDs in one call
            # ═══════════════════════════════════════════════════════════════
            if 'IBKR' in (account_id or '').upper():
                try:
                    from app.psfalgo.ibkr_connector import cancel_orders_isolated_sync
                    order_ids = []
                    for o in orders_to_cancel:
                        oid = o.get('order_id') or o.get('OrderID') or o.get('id')
                        if oid is not None:
                            try:
                                order_ids.append(int(oid))
                            except (ValueError, TypeError):
                                pass
                    
                    if order_ids:
                        loop = asyncio.get_event_loop()
                        cancelled_list = await loop.run_in_executor(
                            None, lambda: cancel_orders_isolated_sync(account_id, order_ids)
                        )
                        cancelled = len(cancelled_list) if cancelled_list else 0
                        failed = len(order_ids) - cancelled
                        self.state.total_orders_cancelled += cancelled
                        logger.info(f"[XNL_ENGINE] Cancel by side ({side}): BATCH {cancelled} cancelled, {failed} failed on {account_id}")
                        return {'cancelled': cancelled, 'failed': failed}
                except Exception as ibkr_batch_err:
                    logger.warning(f"[XNL_ENGINE] IBKR batch cancel error, falling back: {ibkr_batch_err}")
            
            # ═══════════════════════════════════════════════════════════════
            # FALLBACK: One-by-one cancel (if batch fails)
            # ═══════════════════════════════════════════════════════════════
            for order in orders_to_cancel:
                try:
                    order_id = order.get('order_id') or order.get('OrderID') or order.get('id')
                    if not order_id:
                        failed += 1
                        continue
                    success = await self._cancel_order(str(order_id), account_id)
                    if success:
                        cancelled += 1
                        self.state.total_orders_cancelled += 1
                    else:
                        failed += 1
                    await asyncio.sleep(ORDER_SEND_DELAY_SEC)
                except Exception as e:
                    logger.error(f"[XNL_ENGINE] Cancel error: {e}")
                    failed += 1
            
            logger.info(f"[XNL_ENGINE] Cancel by side ({side}): {cancelled} cancelled, {failed} failed")
            return {'cancelled': cancelled, 'failed': failed}
            
        except Exception as e:
            logger.error(f"[XNL_ENGINE] Cancel by side error: {e}", exc_info=True)
            return {'cancelled': 0, 'failed': 0}


# Global instance
_xnl_engine: Optional[XNLEngine] = None


def get_xnl_engine() -> XNLEngine:
    """Get global XNL Engine instance"""
    global _xnl_engine
    if _xnl_engine is None:
        _xnl_engine = XNLEngine()
    return _xnl_engine

