"""
Dual Process Runner - XNL cycle alternating between two accounts.

Flow (per account phase):
1. Switch context → Cancel ALL orders (including REV — REV re-evaluates fresh each cycle)
2. Recompute MinMax Area (fresh BEFDAY + positions from Redis)
3. Start XNL → Wait longest front cycle (LT_INCREASE 3.5 min)
4. Stop XNL (orders left in market)
5. REV health check (reacts to fills from step 3)
6. Send REV orders (queued by health check, with fresh prices)

En uzun süren cycle (LT_INCREASE = 3.5 dk) baz alınır; diğer tag'li cycle'lar bu sürede 3–4 veya MM 6–7 kez dönebilir.
"""

from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Tuple

from loguru import logger

from app.xnl.xnl_engine import (
    get_xnl_engine,
    CYCLE_TIMINGS,
    OrderTagCategory,
)


class DualProcessState(Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"


# Longest front cycle = LT_INCREASE (3.5 minutes). Other cycles can run 3–4 or 6–7 times in this window.
LONGEST_FRONT_CYCLE_SECONDS = CYCLE_TIMINGS[OrderTagCategory.LT_INCREASE].front_cycle_seconds  # 210.0

# Check stop flag every N seconds during the 3.5 min wait so Stop is responsive
STOP_CHECK_INTERVAL_SECONDS = 5.0

VALID_ACCOUNT_IDS = {"HAMPRO", "IBKR_PED", "IBKR_GUN"}


@dataclass
class DualProcessRunnerState:
    state: DualProcessState = DualProcessState.STOPPED
    account_a: str = ""
    account_b: str = ""
    current_account: Optional[str] = None
    loop_count: int = 0
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_error: Optional[str] = None


class DualProcessRunner:
    """
    Runs XNL alternately on two accounts. For each account:
    - Cancel All (tum) → Start XNL → Wait longest front cycle (3.5 min) → Stop XNL (orders left as-is).
    """

    def __init__(self):
        self._state = DualProcessRunnerState()
        self._stop_requested = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def get_state(self) -> dict:
        return {
            "state": self._state.state.value,
            "account_a": self._state.account_a,
            "account_b": self._state.account_b,
            "current_account": self._state.current_account,
            "loop_count": self._state.loop_count,
            "started_at": self._state.started_at.isoformat() if self._state.started_at else None,
            "stopped_at": self._state.stopped_at.isoformat() if self._state.stopped_at else None,
            "last_error": self._state.last_error,
            "longest_front_cycle_seconds": LONGEST_FRONT_CYCLE_SECONDS,
        }

    def _validate_accounts(self, account_a: str, account_b: str) -> List[str]:
        a = (account_a or "").strip().upper()
        b = (account_b or "").strip().upper()
        errs = []
        if a not in VALID_ACCOUNT_IDS:
            errs.append(f"account_a must be one of {sorted(VALID_ACCOUNT_IDS)}, got {account_a!r}")
        if b not in VALID_ACCOUNT_IDS:
            errs.append(f"account_b must be one of {sorted(VALID_ACCOUNT_IDS)}, got {account_b!r}")
        if a == b:
            errs.append("account_a and account_b must be different")
        return errs

    async def start(self, account_a: str, account_b: str) -> Tuple[bool, Optional[str]]:
        """
        Start dual process loop in background. Returns (success, error_message).
        """
        async with self._lock:
            if self._state.state == DualProcessState.RUNNING:
                return False, "Dual Process already running"
            
            # CRITICAL: Block start while old loop is still winding down
            # Without this, stop() → start() race creates TWO concurrent loops
            if self._state.state == DualProcessState.STOPPING:
                logger.info("[DUAL_PROCESS] Still stopping previous loop, waiting...")
                # Release lock while waiting so _run_loop's finally block can update state
                old_task = self._task
            else:
                old_task = None
        
        # Wait for old task outside lock (so finally block in _run_loop can acquire lock-free state update)
        if old_task and not old_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(old_task), timeout=15.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                logger.warning("[DUAL_PROCESS] Old task did not finish in 15s, force proceeding")
            except Exception:
                pass
        
        async with self._lock:
            # Re-check after waiting
            if self._state.state == DualProcessState.RUNNING:
                return False, "Dual Process already running (started by another caller)"
            
            errs = self._validate_accounts(account_a, account_b)
            if errs:
                return False, "; ".join(errs)

            self._state.account_a = (account_a or "").strip().upper()
            self._state.account_b = (account_b or "").strip().upper()
            self._state.state = DualProcessState.RUNNING
            self._state.started_at = datetime.now()
            self._state.stopped_at = None
            self._state.last_error = None
            self._state.loop_count = 0
            self._state.current_account = None
            self._stop_requested = False

            # Publish state to Redis (for RevnBookCheck terminal in separate process)
            self._publish_state_to_redis()

            # Start ETF Guard Terminal (circuit breaker for market-wide moves)
            try:
                from app.terminals.etf_guard_terminal import get_etf_guard
                guard = get_etf_guard()
                await guard.start()
                logger.info("[DUAL_PROCESS] 🛡️ ETF Guard Terminal auto-started")
            except Exception as e:
                logger.warning(f"[DUAL_PROCESS] ETF Guard start failed (non-fatal): {e}")

            self._task = asyncio.create_task(
                self._run_loop(),
                name="dual_process_loop"
            )
            logger.info(
                f"[DUAL_PROCESS] Started: account_a={self._state.account_a}, "
                f"account_b={self._state.account_b}, wait={LONGEST_FRONT_CYCLE_SECONDS}s per account"
            )
            return True, None
    
    def _publish_state_to_redis(self):
        """
        Publish Dual Process state to Redis.
        
        CRITICAL: Updates ALL Redis keys that various consumers read:
        - psfalgo:dual_process:state     → RevnBookCheck._is_dual_process_running()
        - psfalgo:recovery:account_open  → RevRecoveryService._run_recovery_check()
        - psfalgo:account_mode           → RevnBookCheck._get_active_account_from_redis() (priority 3)
        - psfalgo:trading:account_mode   → TradingAccountContext.trading_mode (cross-process sync)
        - psfalgo:xnl:running_account    → RevnBookCheck._xnl_running_account() (priority 2)
        - psfalgo:xnl:running            → RevnBookCheck._is_xnl_running()
        
        This ensures UI, Backend, and RevnBookCheck all see the same active account
        when Dual Process switches between accounts.
        """
        try:
            from app.core.redis_client import get_redis_client
            import json
            
            redis_client = get_redis_client()
            redis_sync = getattr(redis_client, 'sync', redis_client)
            
            # 1. Dual Process state (for RevnBookCheck dual mode detection)
            state_data = {
                "state": self._state.state.value,
                "accounts": [self._state.account_a, self._state.account_b],
                "current_account": self._state.current_account,
                "loop_count": self._state.loop_count,
                "started_at": self._state.started_at.isoformat() if self._state.started_at else None,
            }
            
            redis_sync.set("psfalgo:dual_process:state", json.dumps(state_data))
            redis_sync.expire("psfalgo:dual_process:state", 3600)
            
            # 2. XNL running status (RevnBookCheck._is_xnl_running checks this)
            is_running = self._state.state == DualProcessState.RUNNING
            redis_sync.set("psfalgo:xnl:running", "1" if is_running else "0")
            
            # 3. Sync active account to ALL consumer keys (only when we have a current account)
            current = self._state.current_account
            if current:
                # RevRecoveryService reads this key
                redis_sync.set("psfalgo:recovery:account_open", current)
                
                # UI reads this key (JSON format)
                redis_sync.set("psfalgo:account_mode", json.dumps({"mode": current}))
                
                # TradingAccountContext reads this key (plain value)
                redis_sync.set("psfalgo:trading:account_mode", current)
                
                # RevnBookCheck._xnl_running_account() reads this (priority 2)
                redis_sync.set("psfalgo:xnl:running_account", current)
                
                logger.info(f"[DUAL_PROCESS] 🔄 Published active account to all Redis keys: {current}")
            
            logger.debug(f"[DUAL_PROCESS] Published state to Redis: {state_data['state']}")
        except Exception as e:
            logger.warning(f"[DUAL_PROCESS] Failed to publish state to Redis: {e}")

    async def stop(self) -> bool:
        """Request stop; runner will exit after current wait/step."""
        async with self._lock:
            if self._state.state != DualProcessState.RUNNING:
                return False
            self._state.state = DualProcessState.STOPPING
            self._stop_requested = True
            logger.info("[DUAL_PROCESS] Stop requested; will halt after current step")
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        return True

    async def _run_account_phase(self, account_id: str, engine, ctx, rev_service, to_mode):
        """
        Run a single account phase in the Dual Process loop.
        
        Correct order of operations:
        ═══════════════════════════════════════════════════════════════
        1. Switch to account → Cancel ALL orders (including REV)
        2. Recompute MinMax Area (fresh BEFDAY + positions)
        3. Start XNL → Wait 3.5 min (fills happen here)
        4. Stop XNL (orders left in market)
        5. REV health check (reacts to fills from step 3)
        6. Send REV orders (queued by health check, fresh prices)
        ═══════════════════════════════════════════════════════════════
        
        REV comes AFTER XNL because REV orders are responses to fills
        that occur during the XNL cycle. Checking REV before XNL runs
        would miss all fills from the current cycle.
        
        REV orders are NOT preserved during cancel because:
        - They've been in market for ~4 min (full other-account phase)
        - If unfilled, prices are likely stale
        - REV health check at step 5 will re-evaluate with fresh prices
        - Eliminates fragile cancel-all + re-send-REV pattern
        """
        from app.trading.trading_account_context import get_account_context_lock
        
        # ─── STEP 0: ETF Guard freeze check ──────────────────────────────
        # If ETF Guard triggered (bearish/bullish), wait until freeze expires
        try:
            from app.terminals.etf_guard_terminal import get_etf_guard
            guard = get_etf_guard()
            if guard.is_frozen():
                import time as _time
                remaining = max(0, guard._freeze_until - _time.time())
                logger.warning(f"[DUAL_PROCESS] ❄️ ETF Guard FROZEN — waiting {remaining:.0f}s "
                             f"before {account_id} phase")
                while guard.is_frozen() and not self._stop_requested:
                    await asyncio.sleep(2)
                logger.info(f"[DUAL_PROCESS] ❄️→🟢 ETF Guard unfreeze — proceeding with {account_id}")
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"[DUAL_PROCESS] ETF Guard check error (non-fatal): {e}")
        
        if self._stop_requested:
            return False
        
        # ─── STEP 1: Switch context + Cancel ALL orders ─────────────────
        async with get_account_context_lock():
            self._state.current_account = account_id
            ctx.set_trading_mode(to_mode(account_id))
            self._publish_state_to_redis()
            logger.info(f"[DUAL_PROCESS] ──── {account_id} PHASE START ────")
            
            # ❌ Cancel ALL orders (including REV — REV re-evaluates fresh each cycle)
            try:
                await engine.cancel_by_filter(account_id, "tum", False)
            except Exception as e:
                logger.warning(f"[DUAL_PROCESS] Cancel all on {account_id} error: {e}")
            
            # ─── STEP 2: Recompute MinMax Area (fresh BEFDAY + positions) ───
            try:
                from app.psfalgo.minmax_area_service import get_minmax_area_service
                minmax_svc = get_minmax_area_service()
                minmax_svc.compute_for_account(account_id)
                # CRITICAL: Refresh current_qty from Redis AFTER compute.
                # compute_for_account sets current_qty = befday_qty (stale!).
                # Redis has REAL positions from fills — refresh immediately
                # so XNL engines see actual headroom, not befday-based.
                engine._refresh_minmax_current_qty(minmax_svc, account_id)
                logger.info(f"[DUAL_PROCESS] ✅ MinMax recomputed + current_qty refreshed for {account_id}")
            except Exception as e:
                logger.warning(f"[DUAL_PROCESS] MinMax recompute error for {account_id}: {e}")
            
            if self._stop_requested:
                return False
            
            # ─── STEP 3: Start XNL Engine ───────────────────────────────────
            await engine.start()
        
        # ─── STEP 3 (cont.): Wait for XNL cycles (fills happen here) ──
        await self._sleep_longest_front_cycle()
        
        # ─── STEP 4: Stop XNL (orders stay in market) ──────────────────
        await engine.stop()
        
        if self._stop_requested:
            return False
        
        # ─── STEP 5: REV health check (reacts to fills from XNL) ───────
        try:
            logger.info(f"[DUAL_PROCESS] 🔍 REV health check for {account_id} (post-XNL)...")
            rev_orders = await rev_service.check_account_health(account_id)
            if rev_orders:
                queued = rev_service.queue_rev_orders(account_id, rev_orders)
                logger.info(f"[DUAL_PROCESS] Queued {queued} REV orders for {account_id}")
        except Exception as e:
            logger.warning(f"[DUAL_PROCESS] REV check error for {account_id}: {e}")
        
        # ─── STEP 6: Send REV orders (queued by health check) ──────────
        await self._send_pending_rev_orders(account_id)
        
        # ─── STEP 7: OrderLifecycleTracker check_cycle ──────────────────
        # Checks ALL accounts (both HAMPRO and IBKR_PED).
        # Data isolation is per-account in AccountState — fills from one
        # account never contaminate the other's state/analysis.
        # Returns 'EOD' at 15:58 ET → triggers position OV tagging.
        try:
            from app.monitoring.order_lifecycle_tracker import get_order_lifecycle_tracker
            eod_signal = get_order_lifecycle_tracker().check_cycle()
            if eod_signal == 'EOD':
                logger.warning(f"[DUAL_PROCESS] ⏰ EOD signal received — will stop after this cycle")
        except Exception as e:
            logger.debug(f"[DUAL_PROCESS] OrderLifecycleTracker error: {e}")
        
        logger.info(f"[DUAL_PROCESS] ──── {account_id} PHASE END ────")
        return True

    async def _run_loop(self):
        """
        Main loop: alternate between account_a and account_b.
        
        Flow per account:
          Cancel stale → Start XNL → Wait 3.5min → Stop XNL → REV check → Send REV
        """
        from app.trading.trading_account_context import get_trading_context, TradingAccountMode
        from app.terminals.dual_account_rev_service import get_dual_account_rev_service

        ctx = get_trading_context()
        engine = get_xnl_engine()
        account_a = self._state.account_a
        account_b = self._state.account_b
        rev_service = get_dual_account_rev_service()

        def to_mode(s: str) -> TradingAccountMode:
            return TradingAccountMode(s)

        # ─── DAILY RESET: Flush stale REV queues from previous day ────
        # Orders are strictly 1-day. BEFDAY refreshes daily, so stale
        # REV orders from yesterday would have wrong gap calculations.
        # This MUST run before the first account phase.
        try:
            rev_service.flush_stale_queues()
        except Exception as e:
            logger.warning(f"[DUAL_PROCESS] flush_stale_queues error (non-fatal): {e}")

        try:
            while not self._stop_requested:
                # ── 15:59 ET AUTO-STOP ──
                try:
                    from zoneinfo import ZoneInfo
                    from datetime import datetime
                    et_now = datetime.now(ZoneInfo('America/New_York'))
                    et_time = et_now.hour * 100 + et_now.minute
                    if et_time >= 1559:
                        logger.warning(
                            f"[DUAL_PROCESS] 🛑 AUTO-STOP: Market close "
                            f"({et_now.strftime('%H:%M ET')}). No more trading."
                        )
                        break
                except Exception:
                    pass

                # --- Account A Phase ---
                if self._stop_requested:
                    break
                ok = await self._run_account_phase(account_a, engine, ctx, rev_service, to_mode)
                if not ok:
                    break

                # --- Account B Phase ---
                if self._stop_requested:
                    break
                ok = await self._run_account_phase(account_b, engine, ctx, rev_service, to_mode)
                if not ok:
                    break

                self._state.loop_count += 1
                self._publish_state_to_redis()  # BUG-RUN-03 fix: keep Redis state fresh
                logger.info(f"[DUAL_PROCESS] ✅ Loop #{self._state.loop_count} complete")

        except asyncio.CancelledError:
            logger.info("[DUAL_PROCESS] Task cancelled")
        except Exception as e:
            logger.error(f"[DUAL_PROCESS] Loop error: {e}", exc_info=True)
            self._state.last_error = str(e)
        finally:
            self._state.state = DualProcessState.STOPPED
            self._state.stopped_at = datetime.now()
            self._state.current_account = None
            self._task = None
            # Stop ETF Guard Terminal
            try:
                from app.terminals.etf_guard_terminal import get_etf_guard
                guard = get_etf_guard()
                await guard.stop()
                logger.info("[DUAL_PROCESS] 🛡️ ETF Guard Terminal auto-stopped")
            except Exception:
                pass
            # Publish stopped state to Redis
            self._publish_state_to_redis()
            logger.info("[DUAL_PROCESS] Stopped")

    async def _send_pending_rev_orders(self, account_id: str):
        """
        Pop REV orders from Redis queue, CANCEL stale REV for same symbol,
        apply FRONTLAMA with 5-tick multi-evaluation, THEN send fresh order.
        
        REV REFRESH PATTERN (Cancel → Clear → Send):
        ═══════════════════════════════════════════════════════════════
        1. For each new REV order:
           a. Clear stale pending state (Redis open_orders + intra-cycle)
           b. Cancel old broker order for this symbol (Hammer/IBKR)
           c. Apply frontlama sacrifice limits
           d. Send fresh REV at current price
           e. Track broker order ID for next cycle's cancel
        ═══════════════════════════════════════════════════════════════
        
        This ensures REV orders ALWAYS reflect current bid/ask,
        not stale prices from minutes/hours ago.
        
        Frontlama Tag Mapping for REV:
        ═══════════════════════════════════════════════════════════════
        REV_TP + MM pos → MM_*_DEC limits ($0.60, 50%) — kar alma, agresif
        REV_TP + LT pos → LT_*_DEC limits ($0.35, 25%) — kar alma
        REV_RL + MM pos → MM_*_INC limits ($0.07, 7%)  — reload, en kısıtlı
        REV_RL + LT pos → LT_*_INC limits ($0.10, 10%) — reload, kısıtlı
        ═══════════════════════════════════════════════════════════════
        """
        try:
            from app.terminals.dual_account_rev_service import get_dual_account_rev_service
            from app.terminals.frontlama_engine import get_frontlama_engine
            from app.psfalgo.reverse_guard import clear_pending_rev_for_symbol
            
            rev_service = get_dual_account_rev_service()
            orders = rev_service.pop_rev_orders(account_id)
            if not orders:
                return
            
            logger.info(f"[DUAL_PROCESS] 📤 Sending {len(orders)} pending REV orders for {account_id} (cancel-refresh pattern)")
            
            frontlama = get_frontlama_engine()
            
            # Get exposure for frontlama evaluation
            try:
                from app.psfalgo.exposure_calculator import calculate_exposure_for_account
                exposure = await calculate_exposure_for_account(account_id)
                exposure_pct = (exposure.pot_total / exposure.pot_max * 100) if exposure and exposure.pot_max > 0 else 50.0
            except Exception:
                exposure_pct = 50.0
            
            for order in orders:
                try:
                    symbol = order.get('symbol', '')
                    rev_tag = (order.get('tag') or '').upper()
                    rev_action = (order.get('action') or '').upper()
                    rev_price = float(order.get('price', 0))
                    
                    # 🛡️ HARD RISK GUARD: Block reload (INC) in hard risk mode
                    # TP (take profit) always allowed, RL (reload) blocked
                    is_reload = '_RL_' in rev_tag or rev_tag.endswith('_INC')
                    if is_reload:
                        try:
                            from app.terminals.revnbookcheck import RevnBookCheck
                            # Quick hard risk check via Redis (same as revnbookcheck)
                            import json as _json
                            from app.core.redis_client import get_redis_client
                            _r = get_redis_client()
                            if _r:
                                _hr = _r.get(f"psfalgo:hard_risk:{account_id}")
                                if _hr and _json.loads(_hr.decode() if isinstance(_hr, bytes) else _hr).get('active', False):
                                    logger.info(
                                        f"[DUAL_PROCESS] ⛔ HARD RISK: RELOAD skipped: "
                                        f"{symbol} {rev_tag} (Account={account_id})"
                                    )
                                    continue
                        except Exception:
                            pass  # Fail open — allow order if check fails
                    
                    # ── Get L1 data ──
                    l1_data = await rev_service._get_l1_data(symbol)
                    bid = l1_data.get('bid', 0)
                    ask = l1_data.get('ask', 0)
                    spread = l1_data.get('spread', 0.02)
                    
                    # 🛡️ L1 GUARD: NEVER send order without valid L1 data
                    if bid <= 0 or ask <= 0:
                        logger.warning(
                            f"[DUAL_PROCESS] ⛔ REV SKIPPED: {symbol} {rev_action} "
                            f"— No valid L1 data (bid={bid}, ask={ask}). "
                            f"Order will NOT be sent."
                        )
                        continue
                    
                    # ── Get truth ticks (5 most recent) ──
                    truth_ticks = await self._fetch_truth_ticks(symbol)
                    
                    # ── Map REV tag to frontlama tag ──
                    frontlama_tag = self._rev_tag_to_frontlama_tag(
                        rev_tag, rev_action
                    )
                    
                    # ── Build order dict for frontlama ──
                    order_dict = {
                        'symbol': symbol,
                        'action': rev_action,
                        'price': rev_price,
                        'tag': frontlama_tag
                    }
                    l1_dict = {
                        'bid': bid,
                        'ask': ask,
                        'spread': spread
                    }
                    
                    # ── Evaluate frontlama with 5 truth ticks ──
                    decision = frontlama.evaluate_with_multi_ticks(
                        order=order_dict,
                        l1_data=l1_dict,
                        truth_ticks=truth_ticks,
                        exposure_pct=exposure_pct
                    )
                    
                    # Use fronted price if approved
                    final_price = rev_price
                    if decision.allowed and decision.front_price:
                        fronted_price = round(decision.front_price, 2)
                        
                        # ═══════════════════════════════════════════════════════════════
                        # 🛡️ PROFIT-vs-COST GUARD for REV TP orders
                        # ═══════════════════════════════════════════════════════════════
                        is_tp = '_TP_' in rev_tag
                        fill_cost = float(order.get('_fill_price', 0) or 0)
                        min_tp_profit = 0.05  # Must be at least $0.05 profit vs fill cost
                        
                        if is_tp and fill_cost > 0:
                            if rev_action == 'BUY':
                                profit = fill_cost - fronted_price
                            else:
                                profit = fronted_price - fill_cost
                            
                            if profit < min_tp_profit:
                                logger.warning(
                                    f"[DUAL_PROCESS] ⛔ REV FRONT REJECTED: {symbol} {rev_action} "
                                    f"front=${fronted_price:.2f} vs fill_cost=${fill_cost:.2f} "
                                    f"→ profit=${profit:.2f} < min ${min_tp_profit:.2f}. "
                                    f"Keeping REV price ${rev_price:.2f}."
                                )
                                final_price = rev_price  # Keep original REV price
                            else:
                                final_price = fronted_price
                                logger.info(
                                    f"[DUAL_PROCESS] 🔥 REV FRONTED: {symbol} {rev_action} "
                                    f"${rev_price:.2f} → ${final_price:.2f} "
                                    f"(sacrifice={decision.sacrificed_cents:.2f}¢, "
                                    f"ratio={decision.sacrifice_ratio:.1%}, "
                                    f"profit_vs_fill=${profit:.2f}) "
                                    f"[{decision.tag.value}] rev_tag={rev_tag}"
                                )
                        else:
                            final_price = fronted_price
                            logger.info(
                                f"[DUAL_PROCESS] 🔥 REV FRONTED: {symbol} {rev_action} "
                                f"${rev_price:.2f} → ${final_price:.2f} "
                                f"(sacrifice={decision.sacrificed_cents:.2f}¢, "
                                f"ratio={decision.sacrifice_ratio:.1%}) "
                                f"[{decision.tag.value}] rev_tag={rev_tag}"
                            )
                        
                        order = {**order, 'price': final_price}
                    else:
                        logger.debug(
                            f"[DUAL_PROCESS] REV no-front: {symbol} {rev_action} "
                            f"@ ${rev_price:.2f} — {decision.reason}"
                        )
                    
                    # ══════════════════════════════════════════════════════════════
                    # 🔄 CANCEL-REFRESH: Clear stale REV before REVERSE GUARD
                    # ══════════════════════════════════════════════════════════════
                    # 1. Clear stale pending from Redis + intra-cycle tracking
                    cleared = clear_pending_rev_for_symbol(symbol, account_id)
                    
                    # 2. Cancel old broker order for this symbol
                    old_cancelled = await self._cancel_old_rev_broker_order(symbol, rev_action, account_id)
                    
                    if cleared > 0 or old_cancelled:
                        logger.info(
                            f"[DUAL_PROCESS] 🔄 REV REFRESH: {symbol} — "
                            f"cleared={cleared} redis entries, "
                            f"broker_cancel={'✅' if old_cancelled else '⚠️ none found'} — "
                            f"sending fresh REV {rev_action} @ ${final_price:.2f}"
                        )
                    
                    # ── REVERSE GUARD: Check before sending REV order ──
                    from app.psfalgo.reverse_guard import check_reverse_guard
                    rg_ok, rg_qty, rg_rsn = check_reverse_guard(
                        symbol=order.get('symbol', ''),
                        action=order.get('action', ''),
                        quantity=float(order.get('qty', 0)),
                        tag=order.get('tag', ''),
                        account_id=account_id,
                    )
                    if not rg_ok:
                        logger.warning(
                            f"[DUAL_PROCESS] 🛡️ REVERSE GUARD BLOCKED REV: "
                            f"{order.get('symbol')} {order.get('action')} "
                            f"{order.get('qty')} | {rg_rsn}"
                        )
                        continue
                    if rg_qty != float(order.get('qty', 0)):
                        logger.warning(
                            f"[DUAL_PROCESS] 🛡️ REVERSE GUARD TRIMMED REV: "
                            f"{order.get('symbol')} {order.get('action')} "
                            f"{order.get('qty')} → {rg_qty} | {rg_rsn}"
                        )
                        order = {**order, 'qty': rg_qty}
                    
                    # ── Send order via appropriate execution service ──
                    if 'HAMPRO' in account_id:
                        from app.trading.hammer_execution_service import get_hammer_execution_service
                        exec_svc = get_hammer_execution_service()
                        result = await self._send_order_hammer(exec_svc, order)
                    else:
                        result = await self._send_order_ibkr(order)
                    
                    # ══════════════════════════════════════════════════════════════
                    # 📝 TRACK: Save REV order identity for future cancel-refresh
                    # ══════════════════════════════════════════════════════════════
                    self._track_rev_order_sent(
                        symbol=symbol,
                        action=rev_action,
                        price=final_price,
                        qty=float(order.get('qty', 0)),
                        tag=rev_tag,
                        fill_price=float(order.get('_fill_price', 0) or 0),
                        account_id=account_id,
                        result=result,
                    )
                        
                except Exception as e:
                    logger.error(f"[DUAL_PROCESS] REV order send error for {order.get('symbol')}: {e}")
                    
        except Exception as e:
            logger.warning(f"[DUAL_PROCESS] _send_pending_rev_orders error: {e}")
    
    async def _cancel_old_rev_broker_order(self, symbol: str, action: str, account_id: str) -> bool:
        """
        Cancel existing REV broker order for a symbol before sending fresh one.
        
        Reads psfalgo:rev_tracker:{account}:{symbol} for the old broker order info,
        then cancels via Hammer/IBKR cancel API.
        
        Returns True if a cancel was issued (or no old order existed).
        """
        try:
            import json
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if not redis:
                return False
            
            tracker_key = f"psfalgo:rev_tracker:{account_id}:{symbol}"
            raw = redis.get(tracker_key)
            if not raw:
                return False  # No tracked REV order — nothing to cancel
            
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            old_broker_id = data.get('broker_order_id')
            old_price = data.get('price', 0)
            old_action = data.get('action', '')
            
            if not old_broker_id:
                # No broker ID — order was fire-and-forget, can't cancel individually
                # But we can still try to cancel via cancel_by_filter for this symbol
                logger.debug(
                    f"[DUAL_PROCESS] REV tracker has no broker_order_id for {symbol}, "
                    f"relying on phase-start cancel_all"
                )
                # Delete stale tracker entry 
                redis.delete(tracker_key)
                return False
            
            logger.info(
                f"[DUAL_PROCESS] 🔄 Cancelling old REV: {symbol} {old_action} "
                f"@ ${old_price:.2f} broker_id={old_broker_id} Account={account_id}"
            )
            
            # Cancel via broker
            cancelled = False
            if 'HAMPRO' in account_id.upper():
                try:
                    from app.trading.hammer_execution_service import get_hammer_execution_service
                    svc = get_hammer_execution_service()
                    if svc:
                        result = svc.cancel_order(str(old_broker_id))
                        cancelled = result.get('success', False) if isinstance(result, dict) else False
                except Exception as e:
                    logger.warning(f"[DUAL_PROCESS] Hammer cancel old REV error: {e}")
            else:
                try:
                    from app.psfalgo.ibkr_connector import cancel_orders_isolated_sync
                    import asyncio
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None, lambda: cancel_orders_isolated_sync(account_id, [int(old_broker_id)])
                    )
                    cancelled = bool(result)
                except Exception as e:
                    logger.warning(f"[DUAL_PROCESS] IBKR cancel old REV error: {e}")
            
            # Clear tracker regardless of cancel success (will be replaced by new order)
            redis.delete(tracker_key)
            
            if cancelled:
                logger.info(f"[DUAL_PROCESS] ✅ Old REV cancelled: {symbol} broker_id={old_broker_id}")
            else:
                logger.warning(
                    f"[DUAL_PROCESS] ⚠️ Old REV cancel may have failed: {symbol} "
                    f"broker_id={old_broker_id} — proceeding with fresh REV anyway"
                )
            
            return cancelled
            
        except Exception as e:
            logger.warning(f"[DUAL_PROCESS] _cancel_old_rev_broker_order error for {symbol}: {e}")
            return False
    
    def _track_rev_order_sent(
        self,
        symbol: str,
        action: str,
        price: float,
        qty: float,
        tag: str,
        fill_price: float,
        account_id: str,
        result: Optional[dict] = None,
    ):
        """
        Track a REV order that was sent to the broker.
        
        Saves to Redis psfalgo:rev_tracker:{account}:{symbol} so the NEXT cycle
        can find and cancel this order before sending a fresh one at updated price.
        
        Tracked info:
        - broker_order_id: for cancel API
        - price: to detect if price changed
        - fill_price: the original fill this REV is responding to
        - tag: REV type (TP/RL, engine, position type)
        """
        try:
            import json
            import time as _time
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if not redis:
                return
            
            # Extract broker order ID from result
            broker_order_id = None
            if isinstance(result, dict):
                broker_order_id = (
                    result.get('order_id') 
                    or result.get('OrderID') 
                    or result.get('orderId')
                    or result.get('broker_order_id')
                )
                # For Hammer, order_id might be in nested result
                if not broker_order_id and result.get('success'):
                    broker_order_id = result.get('response', {}).get('OrderID') if isinstance(result.get('response'), dict) else None
            
            tracker_key = f"psfalgo:rev_tracker:{account_id}:{symbol}"
            tracker_data = {
                'symbol': symbol,
                'action': action,
                'price': price,
                'qty': qty,
                'tag': tag,
                'fill_price': fill_price,
                'broker_order_id': str(broker_order_id) if broker_order_id else None,
                'account_id': account_id,
                'sent_at': _time.time(),
            }
            
            redis.set(tracker_key, json.dumps(tracker_data), ex=86400)  # 24h TTL
            
            logger.info(
                f"[DUAL_PROCESS] 📝 REV tracked: {symbol} {action} {qty:.0f} "
                f"@ ${price:.2f} (fill=${fill_price:.2f}) "
                f"broker_id={broker_order_id or 'N/A'} tag={tag} "
                f"Account={account_id}"
            )
            
        except Exception as e:
            logger.debug(f"[DUAL_PROCESS] _track_rev_order_sent error: {e}")
    
    def _rev_tag_to_frontlama_tag(self, rev_tag: str, rev_action: str) -> str:
        """
        Map REV order tag to frontlama-compatible tag for correct sacrifice limits.
        
        TP (Take Profit) → DECREASE behavior (we WANT fill → aggressive limits)
        RL (Reload)       → INCREASE behavior (cautious re-entry → strict limits)
        
        Examples:
          REV_TP_MM_MM_SELL → MM_MM_LONG_DEC  (sell to take profit on MM long = DEC)
          REV_TP_LT_PA_SELL → LT_PA_LONG_DEC  (sell to take profit on LT long = DEC)
          REV_RL_MM_KB_BUY  → MM_KB_LONG_INC  (buy to reload MM long = INC)
          REV_RL_LT_TRIM_BUY → LT_TRIM_LONG_INC (buy to reload LT long = INC)
        """
        tag = rev_tag.upper()
        
        # Determine TP vs RL
        is_tp = '_TP_' in tag
        
        # Determine POS tag (MM or LT) — first part after REV_TP_ or REV_RL_
        pos = 'MM'  # default
        parts = tag.split('_')
        # REV_TP_MM_MM_SELL → parts = [REV, TP, MM, MM, SELL]
        # REV_RL_LT_TRIM_BUY → parts = [REV, RL, LT, TRIM, BUY]
        if len(parts) >= 3:
            if parts[2] in ('MM', 'LT'):
                pos = parts[2]
        
        # Engine tag for clarity
        engine = parts[3] if len(parts) >= 4 else 'MM'
        
        # Direction inference from action
        # REV SELL on long pos = taking profit (LONG_DEC)
        # REV BUY on long pos = reloading (LONG_INC)
        # REV BUY on short pos = taking profit (SHORT_DEC)
        # REV SELL on short pos = reloading (SHORT_INC)
        action = rev_action.upper()
        
        if is_tp:
            # Take Profit → DEC
            if action == 'SELL':
                return f"{pos}_{engine}_LONG_DEC"
            else:
                return f"{pos}_{engine}_SHORT_DEC"
        else:
            # Reload → INC
            if action == 'BUY':
                return f"{pos}_{engine}_LONG_INC"
            else:
                return f"{pos}_{engine}_SHORT_INC"
    
    async def _fetch_truth_ticks(self, symbol: str, count: int = 5) -> list:
        """
        Fetch last N truth ticks from Redis for a symbol.
        Standalone version (no XNL Engine dependency).
        
        🔑 TICKER CONVENTION: Tries both Hammer (WBS-F) and PREF_IBKR (WBS PRF)
        format keys to ensure truth ticks are found regardless of caller format.
        
        Returns: List of dicts newest-first: [{price, venue, size, ts}, ...]
        """
        try:
            import json
            import time
            from app.core.redis_client import get_redis_client
            from app.live.symbol_mapper import SymbolMapper
            
            redis_client = get_redis_client()
            if not redis_client:
                return []
            
            redis_sync = getattr(redis_client, 'sync', redis_client)
            
            # Build format variants to try
            hammer_sym = SymbolMapper.to_hammer_symbol(symbol)
            display_sym = SymbolMapper.to_display_symbol(symbol)
            formats_to_try = list(dict.fromkeys([symbol, hammer_sym, display_sym]))
            
            # PRIMARY: tt:ticks:{symbol}
            for sym in formats_to_try:
                data = redis_sync.get(f"tt:ticks:{sym}")
                if data:
                    raw = data.decode() if isinstance(data, bytes) else data
                    ticks = json.loads(raw)
                    
                    if ticks and isinstance(ticks, list):
                        now = time.time()
                        valid = []
                        for tick in reversed(ticks):  # newest first
                            ts = tick.get('ts', 0)
                            if ts > 0 and (now - ts) > 86400:
                                continue
                            price = float(tick.get('price', 0))
                            size = float(tick.get('size', 0))
                            venue = str(tick.get('exch', tick.get('venue', '')))
                            if price > 0 and size > 0:
                                valid.append({'price': price, 'venue': venue, 'size': size, 'ts': ts})
                            if len(valid) >= count:
                                break
                        if valid:
                            return valid
            
            # FALLBACK: truthtick:latest:{symbol}
            for sym in formats_to_try:
                legacy = redis_sync.get(f"truthtick:latest:{sym}")
                if legacy:
                    raw = legacy.decode() if isinstance(legacy, bytes) else legacy
                    tick = json.loads(raw)
                    price = float(tick.get('price', 0))
                    size = float(tick.get('size', 0))
                    venue = str(tick.get('venue', tick.get('exch', '')))
                    tick_ts = float(tick.get('ts', 0))
                    # ⚠️ STALENESS CHECK: same 24h limit as primary source
                    if price > 0 and size > 0:
                        if tick_ts > 0 and (time.time() - tick_ts) > 86400:
                            continue  # STALE — try next format
                        return [{'price': price, 'venue': venue, 'size': size, 'ts': tick_ts}]
            
            return []
        except Exception as e:
            logger.debug(f"[DUAL_PROCESS] Truth ticks fetch for {symbol}: {e}")
            return []
    
    async def _send_order_hammer(self, exec_svc, order: dict):
        """Send REV order via Hammer — NOT fire_and_forget, we need broker order ID for cancel-refresh."""
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: exec_svc.place_order(
                symbol=order['symbol'],
                side=order['action'],
                quantity=int(order['qty']),
                price=float(order['price']),
                order_style='LIMIT',
                hidden=True,
                strategy_tag=order.get('tag', 'REV_RECOVERY'),
                fire_and_forget=False  # Need order ID for cancel-refresh pattern
            )
        )
        success = result.get('success', False) if isinstance(result, dict) else False
        if success:
            # Log in standard ORDER_SENT format for analysis scripts
            try:
                from app.core.order_context_logger import format_order_sent_log, get_order_context
                _ctx = get_order_context(order['symbol'])
                logger.info(format_order_sent_log(
                    order['symbol'], order['action'], int(order['qty']),
                    float(order['price']), order.get('tag', 'REV'), 'HAMPRO',
                    engine_source='REV', ctx=_ctx
                ))
            except Exception:
                logger.info(f"[DUAL_PROCESS] ✅ REV sent via Hammer: {order['action']} {order['qty']} {order['symbol']} @ ${order['price']:.2f}")
        else:
            msg = result.get('message', 'unknown') if isinstance(result, dict) else str(result)
            logger.warning(f"[DUAL_PROCESS] ⚠️ REV Hammer send failed for {order['symbol']}: {msg}")
        return result
    
    async def _send_order_ibkr(self, order: dict):
        """
        Send REV order via IBKR using place_order_isolated_sync (same safe pattern as XNL Engine).
        
        CRITICAL: Uses place_order_isolated_sync which:
        - Runs placeOrder on the IB event loop thread (not generic executor)
        - Shares the same IB connection session
        - Pushes order to Redis (psfalgo:open_orders:{account}) for UI visibility
        - Sets orderRef for REV tag identification by cancel_by_filter
        """
        try:
            from app.psfalgo.ibkr_connector import get_ibkr_connector, place_order_isolated_sync
            
            # Determine account type from the order or current state
            account_id = order.get('account_id') or self._state.current_account or 'IBKR_GUN'
            
            conn = get_ibkr_connector(account_type=account_id, create_if_missing=False)
            if not conn or not conn.connected:
                logger.warning(f"[DUAL_PROCESS] IBKR not connected for {account_id}, cannot send REV order for {order['symbol']}")
                return None
            
            # Build contract and order details
            symbol = order['symbol']
            rev_tag = order.get('tag') or order.get('strategy_tag') or 'REV_RECOVERY'
            
            contract_details = {
                'symbol': symbol,
                'secType': 'STK',
                'exchange': 'SMART',
                'currency': 'USD'
            }
            # IBKR action normalization (same as xnl_engine._place_order)
            raw_action = order['action'].upper()
            if raw_action in ('SHORT', 'ADD_SHORT', 'SELL_SHORT', 'SSHORT'):
                ibkr_action = 'SELL'
            elif raw_action in ('COVER', 'BUY_TO_COVER', 'ADD'):
                ibkr_action = 'BUY'
            elif raw_action in ('BUY', 'SELL'):
                ibkr_action = raw_action
            else:
                ibkr_action = 'SELL'
            
            order_details = {
                'action': ibkr_action,
                'totalQuantity': int(order['qty']),
                'lmtPrice': float(order['price']),
                'strategy_tag': rev_tag
            }
            
            # Use place_order_isolated_sync (runs on IB thread)
            import asyncio
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: place_order_isolated_sync(account_id, contract_details, order_details)
            )
            success = result.get('success', False) if result else False
            
            if success:
                # Log in standard ORDER_SENT format for analysis scripts
                try:
                    from app.core.order_context_logger import format_order_sent_log, get_order_context
                    _ctx = get_order_context(order['symbol'])
                    logger.info(format_order_sent_log(
                        order['symbol'], order['action'], int(order['qty']),
                        float(order['price']), order.get('tag', 'REV'), account_id,
                        engine_source='REV', ctx=_ctx
                    ))
                except Exception:
                    logger.info(f"[DUAL_PROCESS] ✅ REV sent via IBKR: {order['action']} {order['qty']} {order['symbol']} @ ${order['price']:.2f}")
            else:
                msg = result.get('message', 'unknown') if result else 'no result'
                logger.warning(f"[DUAL_PROCESS] ⚠️ REV IBKR send failed for {order['symbol']}: {msg}")
            
            return result
            
        except Exception as e:
            logger.error(f"[DUAL_PROCESS] IBKR order error for {order['symbol']}: {e}")
            return None

    async def _sleep_longest_front_cycle(self):
        """Sleep for LONGEST_FRONT_CYCLE_SECONDS, checking _stop_requested every STOP_CHECK_INTERVAL_SECONDS."""
        remaining = LONGEST_FRONT_CYCLE_SECONDS
        while remaining > 0 and not self._stop_requested:
            chunk = min(STOP_CHECK_INTERVAL_SECONDS, remaining)
            await asyncio.sleep(chunk)
            remaining -= chunk


_runner: Optional[DualProcessRunner] = None


def get_dual_process_runner() -> DualProcessRunner:
    global _runner
    if _runner is None:
        _runner = DualProcessRunner()
    return _runner
