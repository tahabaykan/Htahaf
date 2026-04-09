"""
ACTMAN Panic Engine V8.3 — ETF-Driven Emergency Hedge

Reads ETF Guard's 2min/5min bar changes and opens protective positions.
Works DURING freeze (unique privilege — other engines stop during freeze).

Key features:
  - Kademeli eskalasyon (no cooldown — every micro-trigger = new round)
  - Group-balanced lot allocation (groups get lots proportional to size)
  - Score-weighted within group (high scorers get more)
  - Max 25% single symbol, min 200 lot
  - Config shift (max config + 5%, severity-based)
  - Only acts when market move HURTS us (opposite direction of our bias)
  - Sliding window fallback (MinMax/MAXALW block → next candidate)
  - Panic scoring: BS(20) + Spread(25) + Truth(15) + SFS(20) + ADV(15) + MAXALW(5)
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from loguru import logger

from app.actman.actman_config import (
    PANIC_ENABLED,
    PANIC_ETF_TIERS, PANIC_REVERSE_ETFS,
    PANIC_MAX_CONFIG_SHIFT, PANIC_SEVERITY_SHIFT,
    PANIC_MAX_PCT_SINGLE_SYMBOL, PANIC_MIN_SYMBOLS, PANIC_MIN_LOT_SIZE,
    MAXALW_SAFETY_MARGIN, LOT_ROUND_TO,
    TAG_PANIC_LONG_INC, TAG_PANIC_SHORT_INC,
    TAG_PANIC_LONG_DEC, TAG_PANIC_SHORT_DEC,
    ACTMAN_ELIGIBLE_HELD_GROUPS,
    is_actman_eligible,
    panic_tier_split,
    DEC_MIN_POSITION_LOT, DEC_MIN_LOT, DEC_FULL_CLOSE_THRESHOLD,
    DEC_DUST_THRESHOLD, DEC_ROUND_TO,
)
from app.actman.actman_scoring import (
    ActmanCandidate,
    score_panic_sell, score_panic_buy,
    score_long_decrease, score_short_decrease,
    calculate_decrease_lot,
    panic_hard_filter,
    check_available_tiers, calculate_order_price, select_best_tier,
    get_group_fthg_range,
)


@dataclass
class PanicOrder:
    """A single panic order to be sent."""
    symbol: str
    action: str          # "BUY" or "SELL"
    qty: int
    price: float
    tier: str            # "K1", "K2", or "K3"
    tag: str             # Dual v4 tag
    score: float         # ACTMAN panic score
    account_id: str


@dataclass
class PanicResult:
    """Result from a panic evaluation."""
    triggered: bool
    direction: str = ""        # "SELL" (market down) or "BUY" (market up)
    severity: str = ""         # "hafif", "orta", "sert"
    best_tier: str = ""        # "K1", "K2", "K3"
    config_shift: float = 0.0  # How much L/S target shifted
    panic_target_long_pct: float = 0.0  # Shifted L target
    allowed_lots: int = 0      # Max lots allowed by config shift
    orders: List[PanicOrder] = field(default_factory=list)
    reason: str = ""
    etf_triggers: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


class ActmanPanicEngine:
    """
    ACTMAN Panic — Emergency hedge response to ETF movements.

    Reads ETF Guard's ring buffer for 2min/5min bar changes.
    Opens positions to protect portfolio when market moves against us.

    SPECIAL PRIVILEGE: Works DURING ETF Guard freeze.
    Other engines stop → Panic starts.
    """

    def __init__(self):
        self._event_count: int = 0

    # ─────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────

    async def evaluate(
        self,
        account_id: str,
        config_long_pct: float,       # Target L% (e.g. 55.0)
        actual_long_pct: float,       # Current L% (e.g. 68.1)
        total_lots: int,              # Total portfolio lots
        etf_changes: Dict[str, Dict[str, Optional[float]]],  # ETF 2min/5min changes
        all_symbols_data: List[Dict[str, Any]],  # All eligible symbols with market data
        minmax_service: Any = None,   # MinMax validation service
        positions: List[Any] = None,  # Current positions for DEC
        metrics: Dict[str, Any] = None,  # Symbol metrics for DEC scoring
    ) -> PanicResult:
        """
        Main panic evaluation — called during freeze or normal cycle.

        etf_changes format:
          {
            'SPY': {'chg_2min': -0.35, 'chg_5min': -0.50, 'price': 543.00},
            'PFF': {'chg_2min': -0.06, 'chg_5min': -0.08, 'price': 31.14},
            ...
          }

        all_symbols_data: list of dicts with keys:
          symbol, dos_grup, cgrup, avg_adv, final_bs, final_ab,
          sfs_score, fb_score, spread, spread_pct, bid, ask,
          son5_tick, maxalw, current_qty, last_price
        """
        if not PANIC_ENABLED:
            return PanicResult(triggered=False, reason="panic_disabled")

        # ── STEP 1: Determine panic direction and severity ──
        direction, severity, triggers = self._evaluate_etf_triggers(etf_changes)

        if not direction:
            return PanicResult(triggered=False, reason="no_etf_trigger")

        # ── STEP 2: Check if market move HURTS us ──
        # If move is in our favor, skip
        needs_action, skip_reason = self._check_if_action_needed(
            direction, actual_long_pct, config_long_pct
        )
        if not needs_action:
            logger.info(
                f"[ACTMAN_PANIC] {account_id} | {direction} detected but {skip_reason} — skipping"
            )
            return PanicResult(
                triggered=False, reason=skip_reason,
                direction=direction, severity=severity,
                etf_triggers=triggers,
            )

        # ── STEP 3: Calculate config shift and allowed lots ──
        shift_pct = self._calculate_config_shift(severity)
        panic_target_long_pct = self._calculate_panic_target(
            direction, config_long_pct, shift_pct
        )
        allowed_lots = self._calculate_allowed_lots(
            direction, actual_long_pct, panic_target_long_pct, total_lots
        )

        if allowed_lots < PANIC_MIN_LOT_SIZE:
            return PanicResult(
                triggered=False,
                reason=f"allowed_lots_too_small:{allowed_lots}",
                direction=direction, severity=severity,
                config_shift=shift_pct,
                panic_target_long_pct=panic_target_long_pct,
                etf_triggers=triggers,
            )

        # ── STEP 4: Determine best execution tier ──
        best_tier_name = self._severity_to_tier(severity)
        tier_split = panic_tier_split(best_tier_name)

        # ── STEP 5: Score and rank candidates ──
        candidates = self._score_candidates(direction, all_symbols_data)

        if not candidates:
            return PanicResult(
                triggered=True, reason="no_eligible_candidates",
                direction=direction, severity=severity,
                best_tier=best_tier_name,
                config_shift=shift_pct,
                panic_target_long_pct=panic_target_long_pct,
                allowed_lots=allowed_lots,
                etf_triggers=triggers,
            )

        # ── STEP 6: DEC-FIRST — Decrease worst positions, then INC ──
        # Panic'te DEC/INC 50/50 default (acil müdahale)
        dec_lots = allowed_lots // 2
        inc_lots = allowed_lots - dec_lots

        all_orders = []

        # STEP 6a: DEC — score worst existing positions
        if dec_lots >= DEC_MIN_LOT and positions and metrics:
            logger.info(
                f"[ACTMAN_PANIC] >>> PANIC DEC: {dec_lots:,} lots "
                f"({'LONG DEC' if direction == 'SELL' else 'SHORT DEC'})"
            )
            dec_orders = self._run_panic_decrease(
                positions=positions,
                metrics=metrics,
                dec_lots=dec_lots,
                is_selloff=(direction == 'SELL'),
                account_id=account_id,
                tier_split=tier_split,
                best_tier_name=best_tier_name,
            )
            if dec_orders:
                dec_filled = sum(o.qty for o in dec_orders)
                all_orders.extend(dec_orders)
                inc_lots += (dec_lots - dec_filled)  # Unfilled → INC
                logger.info(
                    f"[ACTMAN_PANIC] DEC result: {len(dec_orders)} orders, {dec_filled:,} lots"
                )
            else:
                inc_lots = allowed_lots  # All to INC
                logger.info("[ACTMAN_PANIC] DEC: no viable decrease candidates")
        else:
            inc_lots = allowed_lots  # All to INC

        # STEP 6b: INC — open new protective positions (existing logic)
        if inc_lots >= PANIC_MIN_LOT_SIZE:
            inc_orders = self._distribute_lots(
                candidates, inc_lots, tier_split,
                direction, account_id, minmax_service
            )
            all_orders.extend(inc_orders)

        self._event_count += 1

        result = PanicResult(
            triggered=True,
            direction=direction,
            severity=severity,
            best_tier=best_tier_name,
            config_shift=shift_pct,
            panic_target_long_pct=panic_target_long_pct,
            allowed_lots=allowed_lots,
            orders=all_orders,
            reason=f"panic_{direction.lower()}_{severity}",
            etf_triggers=triggers,
        )

        self._log_result(account_id, result)
        return result

    # ─────────────────────────────────────────────
    # PANIC DECREASE PHASE
    # ─────────────────────────────────────────────

    def _run_panic_decrease(
        self,
        positions: List[Any],
        metrics: Dict[str, Any],
        dec_lots: int,
        is_selloff: bool,
        account_id: str,
        tier_split: Dict[str, int],
        best_tier_name: str,
    ) -> List[PanicOrder]:
        """
        Score existing positions and generate PANIC DEC orders.

        is_selloff=True  → market düşüyor → sell worst longs  (LT_ACTPANIC_LONG_DEC)
        is_selloff=False → market yükseliyor → cover worst shorts (LT_ACTPANIC_SHORT_DEC)

        REV: DEC fill → NO RELOAD (kesinlikle).
        """
        from app.trading.order_guard import is_excluded

        fthg_ranges = get_group_fthg_range()
        candidates = []

        for pos in positions:
            sym = getattr(pos, 'symbol', '') if not isinstance(pos, dict) else pos.get('symbol', '')
            qty = getattr(pos, 'qty', 0) if not isinstance(pos, dict) else pos.get('qty', pos.get('quantity', 0))
            grp = getattr(pos, 'group', '') if not isinstance(pos, dict) else pos.get('dos_grup', pos.get('group', ''))

            # CRITICAL FIX: Fallback to metrics if dos_grup/group is missing
            if not grp and sym and metrics:
                sm = metrics.get(sym)
                if sm:
                    grp = str(getattr(sm, 'dos_grup', '') or getattr(sm, 'group', '') or '')
                    if grp == 'nan': grp = ''

            if not sym or not grp:
                continue

            # Direction filter
            if is_selloff and (qty if isinstance(qty, (int, float)) else 0) <= 0:
                continue  # Want LONGs to decrease in selloff
            if not is_selloff and (qty if isinstance(qty, (int, float)) else 0) >= 0:
                continue  # Want SHORTs to decrease in rally

            aq = abs(int(qty))
            if aq < DEC_MIN_POSITION_LOT:
                continue
            if not is_actman_eligible(grp):
                continue
            try:
                if is_excluded(sym):
                    continue
            except Exception:
                pass

            sm = metrics.get(sym)
            if sm is None:
                continue

            spread = float(getattr(sm, 'spread', 0) or 0)
            spread_pct = float(getattr(sm, 'spread_pct', 0) or 0)
            bid = float(getattr(sm, 'bid', 0) or 0)
            ask = float(getattr(sm, 'ask', 0) or 0)
            son5 = getattr(sm, 'son5_tick', None)
            if son5 is None:
                son5 = float(getattr(sm, 'last', getattr(sm, 'last_price', 0)) or 0)
            else:
                son5 = float(son5)

            rng = fthg_ranges.get(grp, {})

            if is_selloff:
                final_bs = float(getattr(sm, 'final_bs', 0) or getattr(sm, 'sfstot', 0) or 0)
                bs_min = rng.get('bs_min', rng.get('min', 0))
                bs_max = rng.get('bs_max', rng.get('max', 0))
                grup_pct = (final_bs - bs_min) / (bs_max - bs_min) if bs_max > bs_min and final_bs > 0 else 0.5
                truth_dist = abs(son5 - bid) if bid > 0 else 0.15
                maxalw = float(getattr(sm, 'maxalw', 0) or 0)
                maxalw_util = aq / maxalw if maxalw > 0 else 0

                score, breakdown = score_long_decrease(
                    grup_pct=grup_pct, spread=spread, spread_pct=spread_pct,
                    truth_bid_dist=truth_dist, maxalw_util=maxalw_util,
                    final_bs=final_bs,
                )
                tag = TAG_PANIC_LONG_DEC
                action = 'SELL'
            else:
                final_ab = float(getattr(sm, 'final_ab', 0) or getattr(sm, 'fbtot', 0) or 0)
                ab_min = rng.get('ab_min', rng.get('min', 0))
                ab_max = rng.get('ab_max', rng.get('max', 0))
                grup_pct = (final_ab - ab_min) / (ab_max - ab_min) if ab_max > ab_min and final_ab > 0 else 0.5
                truth_dist = abs(ask - son5) if ask > 0 else 0.15
                maxalw = float(getattr(sm, 'maxalw', 0) or 0)
                maxalw_util = aq / maxalw if maxalw > 0 else 0

                score, breakdown = score_short_decrease(
                    grup_pct=grup_pct, spread=spread, spread_pct=spread_pct,
                    truth_ask_dist=truth_dist, maxalw_util=maxalw_util,
                    final_ab=final_ab,
                )
                tag = TAG_PANIC_SHORT_DEC
                action = 'BUY'

            candidates.append({
                'symbol': sym, 'qty': aq, 'group': grp,
                'score': score, 'tag': tag, 'action': action,
                'spread': spread, 'bid': bid, 'ask': ask, 'son5': son5,
                'truth_dist': truth_dist,
            })

        if not candidates:
            return []

        candidates.sort(key=lambda c: c['score'], reverse=True)

        for i, c in enumerate(candidates[:5], 1):
            logger.info(
                f"[ACTMAN_PANIC] DEC #{i}: {c['symbol']:<12s} skor={c['score']:.1f} "
                f"qty={c['qty']} [{c['group']}]"
            )

        orders = []
        remaining = dec_lots

        for c in candidates:
            if remaining < DEC_MIN_LOT:
                break

            proposed = min(remaining, c['qty'])
            lot, reason = calculate_decrease_lot(
                current_qty=c['qty'], proposed_lot=proposed,
                min_lot=DEC_MIN_LOT, full_close_threshold=DEC_FULL_CLOSE_THRESHOLD,
                dust_threshold=DEC_DUST_THRESHOLD, round_to=DEC_ROUND_TO,
            )
            if lot <= 0:
                continue

            # Panic DEC → aggressif fiyat (K3 ağırlıklı)
            if c['action'] == 'SELL':
                price = round(c['bid'] - 0.01, 2)
            else:
                price = round(c['ask'] + 0.01, 2)

            remaining -= lot

            orders.append(PanicOrder(
                symbol=c['symbol'], action=c['action'],
                qty=lot, price=price, tier=best_tier_name,
                tag=c['tag'], score=round(c['score'], 1),
                account_id=account_id,
            ))

            logger.info(
                f"[ACTMAN_PANIC] DEC ORDER: {c['action']} {lot} {c['symbol']} "
                f"@ ${price:.2f} [{best_tier_name}] tag={c['tag']} | REV: NO RELOAD"
            )

        return orders

    # ─────────────────────────────────────────────
    # ETF TRIGGER EVALUATION
    # ─────────────────────────────────────────────

    def _evaluate_etf_triggers(
        self, etf_changes: Dict[str, Dict[str, Optional[float]]]
    ) -> Tuple[str, str, List[str]]:
        """
        Evaluate ETF 2min/5min changes against PANIC_ETF_TIERS.
        Returns (direction, severity, trigger_descriptions).

        direction: 'SELL' (market down → short more) or 'BUY' (market up → long more)
        severity: 'hafif' / 'orta' / 'sert'
        """
        best_tier_level = 0  # 0=none, 1=K1, 2=K2, 3=K3
        best_direction = ""
        triggers = []

        for etf, thresholds in PANIC_ETF_TIERS.items():
            changes = etf_changes.get(etf)
            if not changes:
                continue

            chg_2min = changes.get('chg_2min')
            chg_5min = changes.get('chg_5min')
            etf_type = thresholds.get('type', 'pct')
            is_reverse = etf in PANIC_REVERSE_ETFS  # TLT, IEF: up = bearish

            # Check bearish signals (market dropping → need to short)
            for label, chg_val, window in [('2min', chg_2min, '2min'), ('5min', chg_5min, '5min')]:
                if chg_val is None:
                    continue

                drop_val = -chg_val if not is_reverse else chg_val  # Normalize: positive = bearish move
                unit = '$' if etf_type == 'abs' else '%'

                # Check each tier threshold
                for tier_name, tier_level in [('k3', 3), ('k2', 2), ('k1', 1)]:
                    key = f"{window}_{tier_name}"
                    threshold = thresholds.get(key)
                    if threshold is None:
                        continue

                    if drop_val >= threshold:
                        if tier_level > best_tier_level:
                            best_tier_level = tier_level
                            best_direction = "SELL"
                        triggers.append(
                            f"{etf} {window} {chg_val:+.2f}{unit} → K{tier_level} SELL"
                        )
                        break  # Don't double-count same ETF/window

                # Check bullish signals (market rallying → need to long)
                rally_val = chg_val if not is_reverse else -chg_val  # Positive = bullish

                for tier_name, tier_level in [('k3', 3), ('k2', 2), ('k1', 1)]:
                    key = f"{window}_{tier_name}"
                    threshold = thresholds.get(key)
                    if threshold is None:
                        continue

                    if rally_val >= threshold:
                        if tier_level > best_tier_level:
                            best_tier_level = tier_level
                            best_direction = "BUY"
                        triggers.append(
                            f"{etf} {window} {chg_val:+.2f}{unit} → K{tier_level} BUY"
                        )
                        break

        if best_tier_level == 0:
            return "", "", []

        severity = {1: 'hafif', 2: 'orta', 3: 'sert'}.get(best_tier_level, 'hafif')
        return best_direction, severity, triggers

    def _severity_to_tier(self, severity: str) -> str:
        """Map severity to tier name."""
        return {'hafif': 'K1', 'orta': 'K2', 'sert': 'K3'}.get(severity, 'K1')

    # ─────────────────────────────────────────────
    # ACTION NEEDED CHECK
    # ─────────────────────────────────────────────

    def _check_if_action_needed(
        self, direction: str, actual_long_pct: float, config_long_pct: float
    ) -> Tuple[bool, str]:
        """
        Check if the market move HURTS our position.
        If it's in our favor → no action needed.

        SELL direction (market down): Hurts us if we're long-heavy
        BUY direction (market up): Hurts us if we're short-heavy
        """
        config_short_pct = 100.0 - config_long_pct
        actual_short_pct = 100.0 - actual_long_pct
        panic_limit = config_long_pct - PANIC_MAX_CONFIG_SHIFT

        if direction == "SELL":
            # Market dropping — hurts if we're long-heavy
            # Only act if actual_long% > (config_long% - max_shift)
            if actual_long_pct <= panic_limit:
                return False, f"already_short_enough:L={actual_long_pct:.1f}%_limit={panic_limit:.1f}%"
            return True, ""

        elif direction == "BUY":
            # Market rallying — hurts if we're short-heavy
            panic_limit_buy = config_long_pct + PANIC_MAX_CONFIG_SHIFT
            if actual_long_pct >= panic_limit_buy:
                return False, f"already_long_enough:L={actual_long_pct:.1f}%_limit={panic_limit_buy:.1f}%"
            return True, ""

        return False, "unknown_direction"

    # ─────────────────────────────────────────────
    # CONFIG SHIFT
    # ─────────────────────────────────────────────

    def _calculate_config_shift(self, severity: str) -> float:
        """Calculate how much to shift L/S target based on ETF severity."""
        multiplier = PANIC_SEVERITY_SHIFT.get(severity, 0.0)
        return multiplier * PANIC_MAX_CONFIG_SHIFT

    def _calculate_panic_target(
        self, direction: str, config_long_pct: float, shift_pct: float
    ) -> float:
        """Calculate shifted panic target L%."""
        if direction == "SELL":
            # Shifting toward short: lower L target
            return config_long_pct - shift_pct
        else:  # BUY
            # Shifting toward long: higher L target
            return config_long_pct + shift_pct

    def _calculate_allowed_lots(
        self, direction: str, actual_long_pct: float,
        panic_target_long_pct: float, total_lots: int
    ) -> int:
        """Calculate how many lots Panic is allowed to open."""
        if direction == "SELL":
            # Need to reduce long% to target → open shorts
            pct_gap = actual_long_pct - panic_target_long_pct
        else:  # BUY
            # Need to increase long% to target → open longs
            pct_gap = panic_target_long_pct - actual_long_pct

        if pct_gap <= 0:
            return 0

        lots = int(pct_gap / 100.0 * total_lots)
        lots = (lots // LOT_ROUND_TO) * LOT_ROUND_TO
        return max(0, lots)

    # ─────────────────────────────────────────────
    # CANDIDATE SCORING
    # ─────────────────────────────────────────────

    def _score_candidates(
        self, direction: str, all_symbols_data: List[Dict[str, Any]]
    ) -> List[ActmanCandidate]:
        """Score all eligible candidates for panic action."""
        candidates = []

        for sm in all_symbols_data:
            sym = sm.get('symbol', '')
            dos_grup = sm.get('dos_grup', '')

            # ── EXCLUDED TICKER CHECK ──
            try:
                from app.trading.order_guard import is_excluded
                if is_excluded(sym):
                    continue
            except ImportError:
                pass

            # Panic hard filter (simple: eligible group + spread)
            spread_pct = sm.get('spread_pct', 99.0)
            passed, reason = panic_hard_filter(dos_grup, spread_pct)
            if not passed:
                continue

            maxalw = sm.get('maxalw', 0)
            current_qty = abs(sm.get('current_qty', 0))
            if maxalw <= 0:
                continue

            maxalw_util = current_qty / maxalw if maxalw > 0 else 1.0
            room = (maxalw - current_qty) * MAXALW_SAFETY_MARGIN
            if room < PANIC_MIN_LOT_SIZE:
                continue

            spread = sm.get('spread', 99.0)
            bid = sm.get('bid', 0)
            ask = sm.get('ask', 0)
            son5_tick = sm.get('son5_tick')
            avg_adv = sm.get('avg_adv', 0)

            truth_distance = 0.0
            if son5_tick and son5_tick > 0:
                if direction == "SELL":
                    truth_distance = abs(son5_tick - bid) if bid > 0 else 99.0
                else:
                    truth_distance = abs(ask - son5_tick) if ask > 0 else 99.0

            # Score based on direction
            if direction == "SELL":
                final_sbs = sm.get('final_sbs', sm.get('final_score', 0))
                sfs_score = sm.get('sfs_score', sm.get('final_sfs', 0))
                score, breakdown = score_panic_sell(
                    final_bs=final_sbs, dos_grup=dos_grup,
                    spread_pct=spread_pct, truth_distance=truth_distance,
                    maxalw_util=maxalw_util, sfs_score=sfs_score,
                    avg_adv=avg_adv,
                )
            else:  # BUY
                final_ab = sm.get('final_ab', sm.get('final_score', 0))
                fb_score = sm.get('fb_score', sm.get('fbtot', 0))
                score, breakdown = score_panic_buy(
                    final_ab=final_ab, dos_grup=dos_grup,
                    spread_pct=spread_pct, truth_distance=truth_distance,
                    maxalw_util=maxalw_util, fb_score=fb_score,
                    avg_adv=avg_adv,
                )

            # Check available tiers
            available_tiers = check_available_tiers(spread, truth_distance, son5_tick)

            candidate = ActmanCandidate(
                symbol=sm.get('symbol', ''),
                dos_grup=dos_grup,
                cgrup=sm.get('cgrup', ''),
                avg_adv=avg_adv,
                final_score=sm.get('final_score', 0),
                spread=spread,
                spread_pct=spread_pct,
                maxalw=maxalw,
                current_qty=current_qty,
                maxalw_util=maxalw_util,
                truth_distance=truth_distance,
                bid=bid, ask=ask,
                last_price=sm.get('last_price', 0),
                son5_tick=son5_tick,
                sfs_score=sm.get('sfs_score', sm.get('final_sfs', 0)),
                fb_score=sm.get('fb_score', sm.get('fbtot', 0)),
                score=score,
                score_breakdown=breakdown,
                available_tiers=available_tiers,
                action=direction,
            )
            candidates.append(candidate)

        # Sort by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)

        return candidates

    # ─────────────────────────────────────────────
    # LOT DISTRIBUTION (diversified + fallback)
    # ─────────────────────────────────────────────

    def _distribute_lots(
        self,
        candidates: List[ActmanCandidate],
        total_lots: int,
        tier_split: Dict[str, int],
        direction: str,
        account_id: str,
        minmax_service: Any = None,
    ) -> List[PanicOrder]:
        """
        V8.3: Group-balanced + score-weighted distribution.

        Step 1: Distribute total_lots across groups proportional to group size
        Step 2: Within each group, pick candidates by score (alloc/MIN_LOT)
        Step 3: Score-weighted lot alloc, one order per candidate at best tier
        """
        orders = []
        max_per_symbol = int(total_lots * PANIC_MAX_PCT_SINGLE_SYMBOL / 100)
        tag = TAG_PANIC_SHORT_INC if direction == "SELL" else TAG_PANIC_LONG_INC

        # Determine best tier preference from tier_split
        tier_pref = 'K3' if tier_split.get('k3', 0) > 0 else ('K2' if tier_split.get('k2', 0) > 0 else 'K1')

        # Group candidates by dos_grup
        from collections import defaultdict
        group_cands = defaultdict(list)
        group_sizes = defaultdict(int)  # total lots in group (from candidate data)
        for c in candidates:
            group_cands[c.dos_grup].append(c)
            # Approximate group size from MAXALW as proxy
            group_sizes[c.dos_grup] += int(c.maxalw)

        # Calculate group budgets proportional to size
        total_size = sum(group_sizes.values())
        if total_size <= 0:
            return []

        group_budgets = {}
        for grp, size in group_sizes.items():
            share = size / total_size
            budget = int(total_lots * share)
            budget = (budget // LOT_ROUND_TO) * LOT_ROUND_TO
            group_budgets[grp] = budget

        logger.info(
            f"[ACTMAN_PANIC] Distributing {total_lots:,} lots across {len(group_budgets)} groups | "
            f"tier_pref={tier_pref} max/sym={max_per_symbol}"
        )

        # Within each group: score-weighted allocation
        for grp, budget in sorted(group_budgets.items(), key=lambda x: x[1], reverse=True):
            if budget < PANIC_MIN_LOT_SIZE:
                continue

            cands = group_cands.get(grp, [])
            if not cands:
                continue

            max_cands = max(1, budget // PANIC_MIN_LOT_SIZE)
            selected = cands[:max_cands]
            total_score = sum(c.score for c in selected)
            grp_remaining = budget

            logger.info(
                f"[ACTMAN_PANIC] [{grp}] budget={budget} | {len(selected)} candidates"
            )

            for c in selected:
                if grp_remaining < PANIC_MIN_LOT_SIZE:
                    break

                # Score-weighted share
                share = c.score / total_score if total_score > 0 else 1.0 / len(selected)
                raw = int(budget * share)

                # Apply limits
                room = int((c.maxalw - c.current_qty) * MAXALW_SAFETY_MARGIN)
                room = (room // LOT_ROUND_TO) * LOT_ROUND_TO
                raw = min(raw, room, max_per_symbol, grp_remaining)
                raw = (raw // LOT_ROUND_TO) * LOT_ROUND_TO
                if raw < PANIC_MIN_LOT_SIZE:
                    continue

                # MinMax check
                if minmax_service:
                    try:
                        mma_ok, mma_qty, mma_reason = self._check_minmax(
                            minmax_service, account_id, c.symbol, direction, raw
                        )
                        if not mma_ok:
                            logger.info(f"[ACTMAN_PANIC] {c.symbol} MinMax BLOCK: {mma_reason}")
                            continue
                        raw = min(raw, mma_qty)
                        raw = (raw // LOT_ROUND_TO) * LOT_ROUND_TO
                        if raw < PANIC_MIN_LOT_SIZE:
                            continue
                    except Exception as e:
                        logger.warning(f"[ACTMAN_PANIC] MinMax check error for {c.symbol}: {e}")

                # Best available tier
                actual_tier = select_best_tier(c.available_tiers, tier_pref)
                price = calculate_order_price(
                    actual_tier, direction,
                    c.bid, c.ask, c.spread, c.son5_tick,
                )

                orders.append(PanicOrder(
                    symbol=c.symbol,
                    action=direction,
                    qty=raw,
                    price=price,
                    tier=actual_tier,
                    tag=tag,
                    score=c.score,
                    account_id=account_id,
                ))

                logger.info(
                    f"[ACTMAN_PANIC] ORDER: {direction} {raw} {c.symbol} @ ${price:.2f} "
                    f"[{actual_tier}] score={c.score:.1f} [{grp}] tag={tag}"
                )

                grp_remaining -= raw

        return orders

    def _check_minmax(
        self, minmax_service, account_id: str, symbol: str,
        direction: str, qty: int
    ) -> Tuple[bool, int, str]:
        """Check MinMax validation. Returns (allowed, adjusted_qty, reason)."""
        try:
            action = "SELL" if direction == "SELL" else "BUY"
            result = minmax_service.validate(
                account_id=account_id,
                symbol=symbol,
                action=action,
                qty=qty,
            )
            if isinstance(result, tuple) and len(result) >= 2:
                return result[0], result[1] if len(result) > 1 else qty, result[2] if len(result) > 2 else ""
            return True, qty, "ok"
        except Exception as e:
            # If MinMax fails, allow the order (fail-open)
            return True, qty, f"minmax_error:{e}"

    # ─────────────────────────────────────────────
    # LOGGING
    # ─────────────────────────────────────────────

    def _log_result(self, account_id: str, result: PanicResult):
        """Log panic result."""
        if result.orders:
            order_summary = ", ".join(
                f"{o.action} {o.qty} {o.symbol} @{o.price:.2f} [{o.tier}]"
                for o in result.orders
            )
            logger.warning(
                f"[ACTMAN_PANIC] ⚡ #{self._event_count} {account_id} | "
                f"{result.direction} {result.severity} | "
                f"shift={result.config_shift:.1f}% target_L={result.panic_target_long_pct:.1f}% | "
                f"allowed={result.allowed_lots} | "
                f"Orders: {order_summary} | "
                f"Triggers: {result.etf_triggers}"
            )
        else:
            logger.info(
                f"[ACTMAN_PANIC] {account_id} | "
                f"{result.direction} {result.severity} triggered but no orders generated: "
                f"{result.reason}"
            )


# ═══════════════════════════════════════════════════════════════
# ETF CHANGES READER — reads from ETF Guard ring buffer
# ═══════════════════════════════════════════════════════════════

def read_etf_changes() -> Dict[str, Dict[str, Optional[float]]]:
    """
    Read current ETF 2min/5min changes from ETF Guard terminal.

    Returns:
      {
        'SPY': {'chg_2min': -0.35, 'chg_5min': -0.50, 'price': 543.00},
        'PFF': {'chg_2min': -0.06, 'chg_5min': -0.08, 'price': 31.14},
        ...
      }
    """
    try:
        from app.terminals.etf_guard_terminal import get_etf_guard

        guard = get_etf_guard()
        status = guard.get_status()

        if not status or 'etfs' not in status:
            return {}

        changes = {}
        for etf, etf_data in status['etfs'].items():
            changes[etf] = {
                'chg_2min': etf_data.get('chg_2min'),
                'chg_5min': etf_data.get('chg_5min'),
                'price': etf_data.get('price', 0),
            }

        return changes

    except Exception as e:
        logger.error(f"[ACTMAN_PANIC] ETF changes read error: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════

_panic_instance: Optional[ActmanPanicEngine] = None


def get_actman_panic() -> ActmanPanicEngine:
    global _panic_instance
    if _panic_instance is None:
        _panic_instance = ActmanPanicEngine()
    return _panic_instance
