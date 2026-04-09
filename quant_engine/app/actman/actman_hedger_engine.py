"""
ACTMAN Hedger Engine V8.3 — Gap-Driven Rebalancing

Strategy:
  1. Detect L/S drift from config (e.g. actual 68.1% vs config 55% = 13.1%)
  2. Determine tier preference based on drift severity
  3. For each eligible DOS_GRUP, calculate gap and allocate proportionally
  4. Pick correct number of candidates per group (alloc / MIN_LOT)
  5. Score-weighted distribution: high scorers get more lots (max 40% per sym)
  6. Each candidate gets ONE order at best available tier
  7. MinMax/MAXALW block → lot devolves to next best candidate

Tier Selection (per candidate, based on spread/truth availability):
  K1 PASİF: ask - spread*0.15 (SELL) / bid + spread*0.15 (BUY)
  K2 FRONT: truth - $0.01 (SELL) / truth + $0.01 (BUY)
  K3 AKTİF: bid - $0.01 (SELL) / ask + $0.01 (BUY)

K3 ONLY at drift >= 15%!
  <%2   → no action
  %2-5  → prefer K1 (pasif)
  %5-15 → prefer K2 (front) — K3 KAPALI!
  %15+  → prefer K3 (aktif bid vuruş)
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger

from app.actman.actman_config import (
    TAG_HEDGER_LONG_INC, TAG_HEDGER_SHORT_INC,
    TAG_HEDGER_LONG_DEC, TAG_HEDGER_SHORT_DEC,
    HEDGER_MIN_DRIFT_PCT, HEDGER_MAX_PCT_SINGLE_IN_GROUP,
    LOT_ROUND_TO, MIN_LOT_SIZE, MAXALW_SAFETY_MARGIN,
    KUPONLU_GROUPS, ACTMAN_ELIGIBLE_HELD_GROUPS,
    is_actman_eligible,
    cgrup_distance,
    hedger_tier_split,
    DEC_MIN_POSITION_LOT, DEC_MIN_LOT, DEC_FULL_CLOSE_THRESHOLD,
    DEC_DUST_THRESHOLD, DEC_ROUND_TO,
    DEC_INC_RATIO_HIGH_EXP, DEC_INC_RATIO_MID_EXP,
    DEC_INC_RATIO_LOW_EXP, DEC_INC_RATIO_VERY_LOW,
)
from app.actman.actman_scoring import (
    hard_filter_sell, hard_filter_buy,
    score_sell_candidate, score_buy_candidate,
    score_long_decrease, score_short_decrease,
    calculate_decrease_lot,
    check_available_tiers, calculate_order_price, select_best_tier,
    check_execution_gate,
    set_group_fthg_range, get_group_fthg_range,
    ActmanCandidate,
)


# ═══════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════

@dataclass
class GapAllocation:
    """A DOS_GRUP gap with its hedge lot allocation."""
    dos_grup: str
    long_lots: int
    short_lots: int
    gap: int               # positive = needs SELL (too much long), negative = needs BUY
    gap_share_pct: float   # % of total gap from eligible groups
    allocated_lots: int    # lots assigned for hedging
    reference_cgrup: str
    reference_avg_adv: float
    is_kuponlu: bool


@dataclass
class HedgerResult:
    """Result from a hedger run."""
    account_id: str
    trigger_reason: str
    gap_allocations: List[GapAllocation]
    orders: List[Dict[str, Any]]
    skipped_reasons: List[str]
    drift_before: float
    drift_after: float
    timestamp: float = field(default_factory=time.time)


# ═══════════════════════════════════════════════
# HEDGER ENGINE
# ═══════════════════════════════════════════════

class ActmanHedgerEngine:
    """
    ACTMAN Hedger V7 — Gap-Driven Drift Correction.

    Called during XNL Engine cycle.
    Analyzes portfolio L/S balance per DOS_GRUP and issues corrective orders.
    """

    def __init__(self):
        self._last_run_ts: Dict[str, float] = {}
        self._fthg_ranges_initialized = False

    def _ensure_score_ranges(self, metrics: Dict[str, Any]):
        """
        Initialize per-direction score ranges per DOS_GRUP.

        SELL uses final_bs (= FINAL_THG - 1000 * bid_sell_pahalilik)
          → Lower final_bs in group = better short candidate
          Runtime: sm.final_bs, fallback sm.sfstot
        BUY uses final_ab (= FINAL_THG - 1000 * ask_buy_ucuzluk)
          → Higher final_ab in group = better long candidate
          Runtime: sm.final_ab, fallback sm.fbtot
        """
        if self._fthg_ranges_initialized:
            return

        # Build separate ranges for SELL (final_bs) and BUY (final_ab)
        group_bs_scores = defaultdict(list)  # final_bs values per group
        group_ab_scores = defaultdict(list)  # final_ab values per group

        for sym, sm in metrics.items():
            if sm is None:
                continue
            grp = self._get_dosgrup_from_metrics(sym, sm)
            if not grp:
                continue

            # SELL score: final_bs, fallback sfstot
            bs_val = float(getattr(sm, 'final_bs', 0) or getattr(sm, 'sfstot', 0) or 0)
            if bs_val > 0:
                group_bs_scores[grp].append(bs_val)

            # BUY score: final_ab, fallback fbtot
            ab_val = float(getattr(sm, 'final_ab', 0) or getattr(sm, 'fbtot', 0) or 0)
            if ab_val > 0:
                group_ab_scores[grp].append(ab_val)

        # Build combined ranges dict:
        # Each group has {bs_min, bs_max, ab_min, ab_max}
        ranges = {}
        all_groups = set(list(group_bs_scores.keys()) + list(group_ab_scores.keys()))
        for grp in all_groups:
            r = {}
            if grp in group_bs_scores:
                bs = group_bs_scores[grp]
                r['bs_min'] = min(bs)
                r['bs_max'] = max(bs)
            if grp in group_ab_scores:
                ab = group_ab_scores[grp]
                r['ab_min'] = min(ab)
                r['ab_max'] = max(ab)
            # Backward compat
            r['min'] = r.get('ab_min', r.get('bs_min', 0))
            r['max'] = r.get('ab_max', r.get('bs_max', 0))
            ranges[grp] = r

        set_group_fthg_range(ranges)
        self._fthg_ranges_initialized = True

        logger.info(
            f"[ACTMAN_HEDGER] Score ranges: {len(group_bs_scores)} groups with BS (final_bs), "
            f"{len(group_ab_scores)} groups with AB (final_ab)"
        )

    # ═══════════════════════════════════════════════
    # EXPOSURE-BASED DEC/INC RATIO
    # ═══════════════════════════════════════════════

    def _calculate_dec_inc_ratio(self, exposure) -> Tuple[int, int, str]:
        """
        Determine DEC/INC percentage split based on current exposure usage.
        Higher exposure → more DEC (reduce positions), less INC (new positions).
        Returns: (dec_pct, inc_pct, label)
        """
        if exposure is None:
            return DEC_INC_RATIO_MID_EXP[0], DEC_INC_RATIO_MID_EXP[1], "NO_EXPOSURE(default 50/50)"

        pot_total = getattr(exposure, 'pot_total', 0) or 0
        pot_max = getattr(exposure, 'pot_max', 0) or 0

        if pot_max <= 0:
            return DEC_INC_RATIO_MID_EXP[0], DEC_INC_RATIO_MID_EXP[1], "NO_MAX(default 50/50)"

        usage_pct = (pot_total / pot_max) * 100.0

        if usage_pct >= 80:
            return DEC_INC_RATIO_HIGH_EXP[0], DEC_INC_RATIO_HIGH_EXP[1], f"HIGH_EXP({usage_pct:.0f}%)"
        elif usage_pct >= 60:
            return DEC_INC_RATIO_MID_EXP[0], DEC_INC_RATIO_MID_EXP[1], f"MID_EXP({usage_pct:.0f}%)"
        elif usage_pct >= 40:
            return DEC_INC_RATIO_LOW_EXP[0], DEC_INC_RATIO_LOW_EXP[1], f"LOW_EXP({usage_pct:.0f}%)"
        else:
            return DEC_INC_RATIO_VERY_LOW[0], DEC_INC_RATIO_VERY_LOW[1], f"VERY_LOW({usage_pct:.0f}%)"

    # ═══════════════════════════════════════════════
    # MAIN ENTRY POINT — DEC-FIRST ARCHITECTURE
    # ═══════════════════════════════════════════════

    async def run(
        self,
        account_id: str,
        positions: List[Any],       # List of PositionSnapshot
        metrics: Dict[str, Any],    # {symbol: SymbolMetrics}
        exposure: Any = None,       # ExposureSnapshot (for DEC/INC ratio)
        config_long_pct: float = 55.0,
        befday_positions: Optional[List[Any]] = None,
    ) -> HedgerResult:
        """
        Main entry point — DEC-FIRST architecture.

        Flow:
          1. Calculate drift and total rebalance lots
          2. Determine DEC/INC ratio from exposure
          3. STEP 1 — DEC: Score worst existing positions → decrease orders
          4. STEP 2 — INC: Remaining lots → new position orders (existing logic)
          5. DEC fill → REV reload YAZILMAZ
          6. INC fill → REV TP YAZILIR
        """
        logger.info(f"[ACTMAN_HEDGER] ═══ START for {account_id} (DEC-FIRST) ═══")

        # Initialize per-direction score ranges
        self._ensure_score_ranges(metrics)

        # 1. Build portfolio breakdown
        lgr, sgr, lt, st = self._build_group_breakdown(positions, metrics)
        total = lt + st

        if total == 0:
            logger.info("[ACTMAN_HEDGER] No positions, skipping")
            return HedgerResult(account_id, "no_positions", [], [], [], 0, 0)

        actual_long_pct = lt / total * 100
        drift = actual_long_pct - config_long_pct

        logger.info(
            f"[ACTMAN_HEDGER] L={lt:,}({actual_long_pct:.1f}%) S={st:,}({100-actual_long_pct:.1f}%) "
            f"Target: L={config_long_pct:.0f}% Drift={drift:+.1f}%"
        )

        # Check if drift is significant enough
        if abs(drift) < HEDGER_MIN_DRIFT_PCT:
            logger.info(f"[ACTMAN_HEDGER] Drift {drift:+.1f}% < {HEDGER_MIN_DRIFT_PCT}% threshold, no action")
            return HedgerResult(account_id, "balanced", [], [], [], drift, drift)

        # Determine tier preference based on drift severity
        tier_split = hedger_tier_split(drift)
        tier_pref = 'K1'
        if abs(drift) >= 15.0:
            tier_pref = 'K3'
        elif abs(drift) >= 5.0:
            tier_pref = 'K2'

        logger.info(
            f"[ACTMAN_HEDGER] Drift {abs(drift):.1f}% -> prefer {tier_pref} | "
            f"K1={tier_split['k1']}% K2={tier_split['k2']}% K3={tier_split['k3']}%"
            f"{' !!! K3 AKTIF !!!' if tier_pref == 'K3' else ' (K3 KAPALI)'}"
        )

        # 2. Determine direction and total lots needed
        target_short_pct = 100 - config_long_pct
        if drift > 0:
            overall_dir = "SELL"  # Fazla long → long azalt + short aç
            total_needed = max(0, int(total * target_short_pct / 100 - st))
        else:
            overall_dir = "BUY"   # Fazla short → short azalt + long aç
            total_needed = max(0, int(total * config_long_pct / 100 - lt))

        logger.info(f"[ACTMAN_HEDGER] Need {total_needed:,} lots {overall_dir} to reach target")

        if total_needed < MIN_LOT_SIZE:
            return HedgerResult(account_id, "drift_too_small", [], [], [], drift, drift)

        # 3. DEC/INC RATIO from exposure
        dec_pct, inc_pct, ratio_label = self._calculate_dec_inc_ratio(exposure)
        dec_lots = int(total_needed * dec_pct / 100)
        inc_lots = total_needed - dec_lots

        logger.info(
            f"[ACTMAN_HEDGER] DEC/INC Ratio: {dec_pct}%/{inc_pct}% [{ratio_label}] | "
            f"DEC={dec_lots:,} + INC={inc_lots:,} = {total_needed:,}"
        )

        all_orders = []
        skipped_reasons = []
        pos_map = self._build_position_map(positions)

        # ═══════════════════════════════════════════════
        # STEP 1: DECREASE — Score worst existing positions
        # ═══════════════════════════════════════════════
        dec_filled = 0
        if dec_lots >= DEC_MIN_LOT:
            logger.info(
                f"[ACTMAN_HEDGER] >>> STEP 1: DECREASE {dec_lots:,} lots "
                f"({'LONG DEC' if drift > 0 else 'SHORT DEC'})"
            )
            dec_orders = self._run_decrease_phase(
                positions=positions,
                metrics=metrics,
                pos_map=pos_map,
                dec_lots=dec_lots,
                is_over_long=(drift > 0),
                account_id=account_id,
                tier_pref=tier_pref,
            )
            if dec_orders:
                dec_filled = sum(o['quantity'] for o in dec_orders)
                all_orders.extend(dec_orders)
                logger.info(
                    f"[ACTMAN_HEDGER] DEC result: {len(dec_orders)} orders, {dec_filled:,} lots"
                )
            else:
                logger.info("[ACTMAN_HEDGER] DEC: no viable decrease candidates")

            # Unfilled DEC lots transfer to INC
            unfilled_dec = dec_lots - dec_filled
            if unfilled_dec > 0:
                inc_lots += unfilled_dec
                logger.info(
                    f"[ACTMAN_HEDGER] DEC unfilled {unfilled_dec:,} lots → transferred to INC "
                    f"(new INC target: {inc_lots:,})"
                )
        else:
            logger.info(f"[ACTMAN_HEDGER] DEC skipped: {dec_lots} < {DEC_MIN_LOT} min")
            inc_lots = total_needed  # All to INC

        # ═══════════════════════════════════════════════
        # STEP 2: INCREASE — New positions (existing logic)
        # ═══════════════════════════════════════════════
        if inc_lots >= MIN_LOT_SIZE:
            logger.info(
                f"[ACTMAN_HEDGER] >>> STEP 2: INCREASE {inc_lots:,} lots "
                f"({'SHORT INC' if drift > 0 else 'LONG INC'})"
            )

            gap_allocs = self._calculate_gap_allocations(
                lgr, sgr, lt, st, drift, inc_lots, positions, metrics
            )

            if gap_allocs:
                remaining = inc_lots
                for ga in gap_allocs:
                    if remaining < MIN_LOT_SIZE:
                        break
                    alloc = min(ga.allocated_lots, remaining)
                    if alloc < MIN_LOT_SIZE:
                        continue

                    logger.info(
                        f"[ACTMAN_HEDGER] === {ga.dos_grup} === "
                        f"gap={ga.gap:+,} share={ga.gap_share_pct:.1f}% alloc={alloc} {overall_dir}"
                    )

                    if overall_dir == "SELL":
                        orders = self._find_and_allocate_sell(
                            ga, alloc, metrics, pos_map, account_id, tier_pref
                        )
                    else:
                        orders = self._find_and_allocate_buy(
                            ga, alloc, metrics, pos_map, account_id, tier_pref
                        )

                    if orders:
                        filled = sum(o['quantity'] for o in orders)
                        all_orders.extend(orders)
                        remaining -= filled
                    else:
                        skipped_reasons.append(f"{ga.dos_grup}: no viable INC candidates")
            else:
                logger.info("[ACTMAN_HEDGER] INC: no eligible gaps found")
        else:
            logger.info(f"[ACTMAN_HEDGER] INC skipped: {inc_lots} < {MIN_LOT_SIZE} min")

        # Calculate post-hedge drift
        total_buy = sum(o['quantity'] for o in all_orders if o['action'] == 'BUY')
        total_sell = sum(o['quantity'] for o in all_orders if o['action'] == 'SELL')
        new_lt = lt + total_buy
        new_st = st + total_sell
        new_total = new_lt + new_st
        drift_after = (new_lt / new_total * 100 - config_long_pct) if new_total > 0 else 0

        dec_count = sum(1 for o in all_orders if 'DEC' in (o.get('tag') or ''))
        inc_count = len(all_orders) - dec_count
        logger.info(
            f"[ACTMAN_HEDGER] ═══ DONE {account_id}: {len(all_orders)} orders "
            f"({dec_count} DEC + {inc_count} INC), {total_buy+total_sell:,} lots | "
            f"drift {drift:+.1f}pp → {drift_after:+.1f}pp ═══"
        )

        self._last_run_ts[account_id] = time.time()
        return HedgerResult(
            account_id=account_id,
            trigger_reason=f"ls_drift({drift:+.1f}pp)_dec_first",
            gap_allocations=[],
            orders=all_orders,
            skipped_reasons=skipped_reasons,
            drift_before=drift,
            drift_after=drift_after,
        )

    # ═══════════════════════════════════════════════
    # DECREASE PHASE — Score worst positions to reduce
    # ═══════════════════════════════════════════════

    def _run_decrease_phase(
        self,
        positions: List[Any],
        metrics: Dict[str, Any],
        pos_map: Dict,
        dec_lots: int,
        is_over_long: bool,
        account_id: str,
        tier_pref: str,
    ) -> List[Dict[str, Any]]:
        """
        Score existing positions and generate DECREASE orders.

        is_over_long=True  → too much long  → sell worst longs  (LT_ACTHEDGE_LONG_DEC)
        is_over_long=False → too much short → cover worst shorts (LT_ACTHEDGE_SHORT_DEC)

        Scoring uses grup-içi yüzdelik (group-relative percentile).
        Lot rules: min 125 position, min 200 order, <400 remaining → full close.
        REV: DEC fill → NO RELOAD (kesinlikle).
        """
        from app.trading.order_guard import is_excluded

        fthg_ranges = get_group_fthg_range()
        candidates = []

        for pos in positions:
            sym = getattr(pos, 'symbol', '')
            qty = getattr(pos, 'qty', 0)
            grp = getattr(pos, 'group', '') or ''

            if not sym or not grp:
                continue

            # Direction filter
            if is_over_long and qty <= 0:
                continue  # We want LONGs to decrease
            if not is_over_long and qty >= 0:
                continue  # We want SHORTs to decrease

            aq = abs(qty)

            # Min position lot filter
            if aq < DEC_MIN_POSITION_LOT:
                continue

            # Eligible group filter
            if not is_actman_eligible(grp):
                continue

            # Excluded ticker filter
            try:
                if is_excluded(sym):
                    continue
            except Exception:
                pass

            # Get metrics for scoring
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
            maxalw = float(getattr(sm, 'maxalw', 0) or 0)
            maxalw_util = aq / maxalw if maxalw > 0 else 0

            # Calculate group-relative percentile
            rng = fthg_ranges.get(grp, {})

            if is_over_long:
                # Long decrease: use BS (final_bs / sfstot)
                final_bs = float(getattr(sm, 'final_bs', 0) or getattr(sm, 'sfstot', 0) or 0)
                bs_min = rng.get('bs_min', rng.get('min', 0))
                bs_max = rng.get('bs_max', rng.get('max', 0))
                if bs_max > bs_min and final_bs > 0:
                    grup_pct = (final_bs - bs_min) / (bs_max - bs_min)
                else:
                    grup_pct = 0.5

                truth_dist = abs(son5 - bid) if bid > 0 else 0.15

                score, breakdown = score_long_decrease(
                    grup_pct=grup_pct,
                    spread=spread,
                    spread_pct=spread_pct,
                    truth_bid_dist=truth_dist,
                    maxalw_util=maxalw_util,
                    final_bs=final_bs,
                )
                tag = TAG_HEDGER_LONG_DEC
                action = 'SELL'
            else:
                # Short decrease: use AB (final_ab / fbtot)
                final_ab = float(getattr(sm, 'final_ab', 0) or getattr(sm, 'fbtot', 0) or 0)
                ab_min = rng.get('ab_min', rng.get('min', 0))
                ab_max = rng.get('ab_max', rng.get('max', 0))
                if ab_max > ab_min and final_ab > 0:
                    grup_pct = (final_ab - ab_min) / (ab_max - ab_min)
                else:
                    grup_pct = 0.5

                truth_dist = abs(ask - son5) if ask > 0 else 0.15

                score, breakdown = score_short_decrease(
                    grup_pct=grup_pct,
                    spread=spread,
                    spread_pct=spread_pct,
                    truth_ask_dist=truth_dist,
                    maxalw_util=maxalw_util,
                    final_ab=final_ab,
                )
                tag = TAG_HEDGER_SHORT_DEC
                action = 'BUY'  # Cover

            candidates.append({
                'symbol': sym, 'qty': aq, 'group': grp,
                'score': score, 'breakdown': breakdown,
                'tag': tag, 'action': action,
                'spread': spread, 'spread_pct': spread_pct,
                'bid': bid, 'ask': ask, 'son5': son5,
                'truth_dist': truth_dist, 'grup_pct': grup_pct,
            })

        if not candidates:
            logger.info("[ACTMAN_HEDGER] DEC: no eligible positions to decrease")
            return []

        # Sort by score descending (highest = worst position = decrease first)
        candidates.sort(key=lambda c: c['score'], reverse=True)

        # Log top candidates
        for i, c in enumerate(candidates[:10], 1):
            logger.info(
                f"[ACTMAN_HEDGER] DEC #{i}: {c['symbol']:<12s} skor={c['score']:.1f} "
                f"qty={c['qty']} grp%={c['grup_pct']:.0%} spr={c['spread_pct']:.2f}% "
                f"t_dist=${c['truth_dist']:.3f} [{c['group']}]"
            )

        # Generate orders
        orders = []
        remaining = dec_lots

        for c in candidates:
            if remaining < DEC_MIN_LOT:
                break

            proposed = min(remaining, c['qty'])
            lot, reason = calculate_decrease_lot(
                current_qty=c['qty'],
                proposed_lot=proposed,
                min_lot=DEC_MIN_LOT,
                full_close_threshold=DEC_FULL_CLOSE_THRESHOLD,
                dust_threshold=DEC_DUST_THRESHOLD,
                round_to=DEC_ROUND_TO,
            )

            if lot <= 0:
                logger.debug(f"[ACTMAN_HEDGER] DEC skip {c['symbol']}: {reason}")
                continue

            # Determine execution tier & price
            spread = c['spread']
            truth_dist = c['truth_dist']

            if spread <= 0.12 and truth_dist <= 0.08:
                exec_tier = 'K3'
            elif spread <= 0.20 and truth_dist <= 0.15:
                exec_tier = 'K2'
            else:
                exec_tier = 'K1'

            # Price calculation
            if c['action'] == 'SELL':  # Long decrease
                if exec_tier == 'K3':
                    price = c['bid'] - 0.01
                elif exec_tier == 'K2':
                    price = c['son5'] - 0.01
                else:
                    price = c['ask'] - spread * 0.15
            else:  # Short decrease (BUY/COVER)
                if exec_tier == 'K3':
                    price = c['ask'] + 0.01
                elif exec_tier == 'K2':
                    price = c['son5'] + 0.01
                else:
                    price = c['bid'] + spread * 0.15

            price = round(price, 2)
            remaining -= lot
            post_qty = c['qty'] - lot

            order = {
                'symbol': c['symbol'],
                'action': c['action'],
                'quantity': lot,
                'price': price,
                'tag': c['tag'],
                'strategy_tag': c['tag'],
                'hidden': True,
                'source': 'ACTMAN_HEDGER_DEC',
                'engine_name': 'ACTMAN_HEDGER',
                'actman_exec_tier': exec_tier,
                'actman_score': round(c['score'], 1),
                'actman_is_decrease': True,      # Flag for REV: NO reload
                'actman_no_rev_reload': True,     # Explicit: DEC = no reload
                'account_id': account_id,
            }
            orders.append(order)

            logger.info(
                f"[ACTMAN_HEDGER] DEC ORDER: {c['action']} {lot} {c['symbol']} "
                f"@ ${price:.2f} [{exec_tier}] skor={c['score']:.1f} | "
                f"{reason} | {c['qty']}→{post_qty} | tag={c['tag']} | REV: NO RELOAD"
            )

        return orders

    # ═══════════════════════════════════════════════
    # GAP ANALYSIS
    # ═══════════════════════════════════════════════

    def _calculate_gap_allocations(
        self, lgr, sgr, lt, st, drift, total_needed, positions, metrics
    ) -> List[GapAllocation]:
        """Calculate per-group gap and proportional lot allocation."""
        all_groups = sorted(set(list(lgr.keys()) + list(sgr.keys())))
        gaps = []

        for g in all_groups:
            if not is_actman_eligible(g):
                continue
            l, s = lgr.get(g, 0), sgr.get(g, 0)
            gap = (l - s) if drift > 0 else (s - l)
            if gap <= 0:
                continue

            is_kup = g in KUPONLU_GROUPS
            ref_cgrup, ref_adv = self._get_group_reference(g, positions, metrics,
                                                            'LONG' if drift > 0 else 'SHORT')

            gaps.append(GapAllocation(
                dos_grup=g, long_lots=l, short_lots=s, gap=gap,
                gap_share_pct=0, allocated_lots=0,
                reference_cgrup=ref_cgrup, reference_avg_adv=ref_adv,
                is_kuponlu=is_kup,
            ))

        total_gap = sum(g.gap for g in gaps)
        if total_gap <= 0:
            return []

        # Allocate proportionally, round to LOT_ROUND_TO
        for g in gaps:
            g.gap_share_pct = g.gap / total_gap * 100
            raw_alloc = total_needed * g.gap / total_gap
            g.allocated_lots = int(round(raw_alloc / LOT_ROUND_TO) * LOT_ROUND_TO)

        # Sort by gap descending
        gaps.sort(key=lambda g: g.gap, reverse=True)

        # Log gap table
        for g in gaps:
            tag = "AKTIF" if g.gap_share_pct > 2 else "kucuk"
            logger.info(
                f"[ACTMAN_HEDGER] {g.dos_grup:<28} L={g.long_lots:>6,} S={g.short_lots:>6,} "
                f"gap={g.gap:>+6,} share={g.gap_share_pct:>5.1f}% -> {g.allocated_lots} lots [{tag}]"
            )

        return gaps

    def _get_group_reference(
        self, dos_grup: str, positions: List[Any], metrics: Dict[str, Any], heavy_side: str
    ) -> Tuple[str, float]:
        """Get reference CGRUP (most common) and AVG_ADV (average) for a group."""
        cgrup_lots = defaultdict(int)
        advs = []

        for pos in positions:
            grp = getattr(pos, 'group', '') or ''
            if grp != dos_grup:
                continue
            sym = getattr(pos, 'symbol', '')
            qty = getattr(pos, 'qty', 0)

            # Get ADV from metrics
            sm = metrics.get(sym)
            if sm:
                adv = float(getattr(sm, 'avg_adv', 0) or 0)
                if adv > 0:
                    advs.append(adv)

            # CGRUP from heavy side
            if (heavy_side == 'LONG' and qty > 0) or (heavy_side == 'SHORT' and qty < 0):
                cg = getattr(pos, 'cgrup', '') or ''
                if not cg and sm:
                    cg = str(getattr(sm, 'cgrup', '') or '')
                if cg:
                    cgrup_lots[cg] += abs(qty)

        ref_cgrup = max(cgrup_lots, key=cgrup_lots.get) if cgrup_lots else ''
        ref_adv = sum(advs) / len(advs) if advs else 15000

        return ref_cgrup, ref_adv

    # ═══════════════════════════════════════════════
    # CANDIDATE FINDING + ORDER GENERATION
    # ═══════════════════════════════════════════════

    def _find_and_allocate_sell(
        self, ga: GapAllocation, alloc: int,
        metrics: Dict[str, Any], pos_map: Dict, account_id: str,
        tier_pref: str = 'K2',
    ) -> List[Dict]:
        """Find sell candidates for a group and allocate lots."""
        candidates = self._score_candidates(ga, "SELL", metrics, pos_map)
        return self._allocate_orders(candidates, alloc, "SELL", account_id, tier_pref)

    def _find_and_allocate_buy(
        self, ga: GapAllocation, alloc: int,
        metrics: Dict[str, Any], pos_map: Dict, account_id: str,
        tier_pref: str = 'K2',
    ) -> List[Dict]:
        """Find buy candidates for a group and allocate lots."""
        candidates = self._score_candidates(ga, "BUY", metrics, pos_map)
        return self._allocate_orders(candidates, alloc, "BUY", account_id, tier_pref)

    def _score_candidates(
        self, ga: GapAllocation, direction: str,
        metrics: Dict[str, Any], pos_map: Dict
    ) -> List[ActmanCandidate]:
        """Score all candidates in a group for a direction."""
        candidates = []

        for sym, sm in metrics.items():
            if sm is None:
                continue

            # ── EXCLUDED TICKER CHECK ──
            # qe_excluded.csv → FGSN, ATH PRD, AGM PRF etc.
            try:
                from app.trading.order_guard import is_excluded
                if is_excluded(sym):
                    continue
            except ImportError:
                pass

            sym_group = self._get_dosgrup_from_metrics(sym, sm)
            sym_cgrup = str(getattr(sm, 'cgrup', '') or '')
            sym_adv = float(getattr(sm, 'avg_adv', 0) or 0)
            spread = float(getattr(sm, 'spread', 0) or 0)
            bid = float(getattr(sm, 'bid', 0) or 0)
            ask = float(getattr(sm, 'ask', 0) or 0)
            last_price = float(getattr(sm, 'last', 0) or getattr(sm, 'last_price', 0) or 0)
            spread_pct = (spread / ask * 100) if ask > 0 else 99

            # Hard filter
            passed, reason = hard_filter_sell(
                candidate_dos_grup=sym_group, target_dos_grup=ga.dos_grup,
                candidate_cgrup=sym_cgrup, reference_cgrup=ga.reference_cgrup,
                candidate_avg_adv=sym_adv,
                reference_avg_adv=ga.reference_avg_adv if ga.reference_avg_adv > 0 else sym_adv,
                spread_pct=spread_pct, avg_adv=sym_adv, is_kuponlu=ga.is_kuponlu,
            )
            if not passed:
                continue

            # ── Score Selection ──
            # SELL (short açma, bid'e vuruyor):
            #   final_bs = FINAL_THG - 1000 × bid_sell_pahalilik
            #   Düşük final_bs = iyi short adayı
            #   Runtime: sm.final_bs veya fallback sm.sfstot
            # BUY (long açma, ask'a vuruyor):
            #   final_ab = FINAL_THG - 1000 × ask_buy_ucuzluk
            #   Yüksek final_ab = iyi long adayı
            #   Runtime: sm.final_ab veya fallback sm.fbtot
            if direction == "SELL":
                dir_score = float(getattr(sm, 'final_sbs', 0) or getattr(sm, 'sfstot', 0) or 0)
            else:
                dir_score = float(getattr(sm, 'final_ab', 0) or getattr(sm, 'fbtot', 0) or 0)

            # Position + MAXALW
            maxalw = float(getattr(sm, 'maxalw', 0) or 0)
            if maxalw <= 0:
                maxalw = sym_adv / 10.0 if sym_adv > 0 else 500

            side_key = 'short' if direction == 'SELL' else 'long'
            cur_qty = abs(pos_map.get(sym, {}).get(side_key, 0))
            mu = cur_qty / maxalw if maxalw > 0 else 1.0

            # Room check — skip if no room
            room = max(0, maxalw - cur_qty)
            if room < MIN_LOT_SIZE:
                continue

            # ADV ratio
            safe_ref = ga.reference_avg_adv if ga.reference_avg_adv > 0 else sym_adv
            ar = max(sym_adv, safe_ref) / min(sym_adv, safe_ref) if sym_adv > 0 and safe_ref > 0 else 1.0

            # CGRUP steps
            cs = cgrup_distance(sym_cgrup, ga.reference_cgrup) if ga.is_kuponlu else 0

            # Truth tick
            son5 = getattr(sm, 'son5_tick', None) or getattr(sm, 'son5', None)
            if son5 is not None:
                son5 = float(son5)
            else:
                son5 = last_price  # Fallback to last price

            # Truth distance
            if direction == "SELL":
                truth_dist = abs(son5 - bid) if son5 and bid else 0.3
                tp = bid
            else:
                truth_dist = abs(ask - son5) if son5 and ask else 0.3
                tp = ask

            # Score using direction-appropriate score
            if direction == "SELL":
                score, breakdown = score_sell_candidate(
                    final_score=dir_score, dos_grup=ga.dos_grup,
                    spread_pct=spread_pct, truth_distance=truth_dist,
                    maxalw_util=mu, adv_ratio=ar, cgrup_steps=cs, is_kuponlu=ga.is_kuponlu,
                )
            else:
                score, breakdown = score_buy_candidate(
                    final_score=dir_score, dos_grup=ga.dos_grup,
                    spread_pct=spread_pct, truth_distance=truth_dist,
                    maxalw_util=mu, adv_ratio=ar, cgrup_steps=cs, is_kuponlu=ga.is_kuponlu,
                )

            # Execution gate
            can_hit, hit_reason = check_execution_gate(
                spread=spread, target_price=tp, son5_tick=son5, direction=direction,
            )

            candidates.append(ActmanCandidate(
                symbol=sym, dos_grup=sym_group, cgrup=sym_cgrup, avg_adv=sym_adv,
                final_score=dir_score, spread=spread, spread_pct=spread_pct,
                maxalw=maxalw, current_qty=cur_qty, maxalw_util=mu,
                truth_distance=truth_dist, bid=bid, ask=ask, last_price=last_price,
                son5_tick=son5, score=score, score_breakdown=breakdown,
                can_active_hit=can_hit, hit_fail_reason=hit_reason if not can_hit else "",
                action=direction,
            ))

        candidates.sort(key=lambda c: c.score, reverse=True)

        # Log top candidates
        for i, c in enumerate(candidates[:5]):
            hit_tag = "HIT" if c.can_active_hit else "PAS"
            logger.info(
                f"[ACTMAN_HEDGER] {direction} #{i+1}: {c.symbol} "
                f"score={c.score:.1f} FTHG={c.final_score:.0f} "
                f"spr=${c.spread:.2f} truth=${c.truth_distance:.3f} "
                f"[{hit_tag}] | {c.score_breakdown}"
            )

        return candidates

    def _allocate_orders(
        self, candidates: List[ActmanCandidate], needed: int,
        direction: str, account_id: str,
        tier_pref: str = 'K2',
    ) -> List[Dict]:
        """
        V8.3: One order per candidate at best available tier.

        Key rules:
          - Candidate count = needed / MIN_LOT_SIZE (max candidates that fit)
          - Score-weighted: high scorers get more lots
          - Max per symbol = HEDGER_MAX_PCT_SINGLE_IN_GROUP% of needed
          - Min per order = MIN_LOT_SIZE (200)
          - Tier: best available, influenced by tier_pref (K3 only at %15+)
          - MAXALW block → lot devolves to next candidate
        """
        if not candidates:
            return []

        orders = []
        remaining = needed

        tag = TAG_HEDGER_SHORT_INC if direction == "SELL" else TAG_HEDGER_LONG_INC
        side = "SHORT" if direction == "SELL" else "LONG"

        # How many candidates can we pick?
        max_cands = max(1, needed // MIN_LOT_SIZE)
        max_per_sym = max(MIN_LOT_SIZE, int(needed * HEDGER_MAX_PCT_SINGLE_IN_GROUP / 100))

        # Filter candidates that have room
        viable = []
        for c in candidates:
            room = max(0, c.maxalw - c.current_qty)
            safe_room = int(room * MAXALW_SAFETY_MARGIN / LOT_ROUND_TO) * LOT_ROUND_TO
            if safe_room >= MIN_LOT_SIZE:
                viable.append((c, safe_room))

        selected = viable[:max_cands]
        if not selected:
            return []

        # Score-weighted allocation
        total_score = sum(c.score for c, _ in selected)

        logger.info(
            f"[ACTMAN_HEDGER] {direction}: {len(selected)} candidates from "
            f"{len(viable)} viable | max/sym={max_per_sym} | tier_pref={tier_pref}"
        )

        for c, safe_room in selected:
            if remaining < MIN_LOT_SIZE:
                break

            # Score-weighted share
            share = c.score / total_score if total_score > 0 else 1.0 / len(selected)
            raw = int(needed * share)
            raw = min(raw, max_per_sym, safe_room, remaining)
            raw = (raw // LOT_ROUND_TO) * LOT_ROUND_TO
            if raw < MIN_LOT_SIZE:
                continue

            # Best available tier for this candidate
            avail_tiers = check_available_tiers(c.spread, c.truth_distance, c.son5_tick)
            actual_tier = select_best_tier(avail_tiers, tier_pref)
            price = calculate_order_price(
                actual_tier, direction,
                c.bid, c.ask, c.spread, c.son5_tick,
            )

            otype_map = {
                'K3': 'BID_HIT' if direction == 'SELL' else 'ASK_HIT',
                'K2': 'FRONT_SELL' if direction == 'SELL' else 'FRONT_BUY',
                'K1': 'ASK_PASSIVE' if direction == 'SELL' else 'BID_PASSIVE',
            }

            fallback = f" ({tier_pref}->{actual_tier})" if actual_tier != tier_pref else ""

            order = {
                'symbol': c.symbol,
                'action': direction,
                'side': side,
                'quantity': raw,
                'price': price,
                'hidden': True,
                'tag': tag,
                'strategy_tag': tag,
                'engine_name': 'ACTMAN_HEDGER',
                'order_type': otype_map.get(actual_tier, 'PASSIVE'),
                'actman_score': c.score,
                'actman_breakdown': c.score_breakdown,
                'actman_exec_tier': actual_tier,
                'actman_tier_pref': tier_pref,
                'account_id': account_id,
            }
            orders.append(order)

            logger.info(
                f"[ACTMAN_HEDGER] ORDER: {direction} {raw} {c.symbol} "
                f"@ ${price:.2f} [{actual_tier}]{fallback} score={c.score:.1f} "
                f"({raw/needed*100:.0f}% of alloc) spr=${c.spread:.2f}"
            )

            remaining -= raw

        return orders

    # ═══════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════

    def _build_group_breakdown(self, positions, metrics=None):
        lgr, sgr = defaultdict(int), defaultdict(int)
        lt = st = 0
        metrics = metrics or {}
        for pos in positions:
            grp = getattr(pos, 'group', '') or ''
            sym = getattr(pos, 'symbol', '')
            qty = getattr(pos, 'qty', 0)
            
            # CRITICAL FIX: Fallback to metrics if dos_grup/group is missing in PositionSnapshot
            if not grp and sym:
                sm = metrics.get(sym)
                if sm:
                    grp = self._get_dosgrup_from_metrics(sym, sm)
                    
            if not grp:
                logger.debug(f"[ACTMAN_HEDGER] Excluded {sym} from breakdown: missing dos_grup")
                continue
                
            aq = abs(qty)
            if qty > 0:
                lgr[grp] += aq; lt += aq
            elif qty < 0:
                sgr[grp] += aq; st += aq
        return lgr, sgr, lt, st

    def _build_position_map(self, positions):
        pm = defaultdict(lambda: {'long': 0, 'short': 0})
        for pos in positions:
            sym = getattr(pos, 'symbol', '')
            qty = getattr(pos, 'qty', 0)
            if qty > 0:
                pm[sym]['long'] += qty
            elif qty < 0:
                pm[sym]['short'] += abs(qty)
        return pm

    def _get_dosgrup_from_metrics(self, symbol: str, sm) -> str:
        """Get DOS_GRUP from metrics or static data."""
        grp = str(getattr(sm, 'dos_grup', '') or getattr(sm, 'group', '') or '')
        if grp and grp != 'nan':
            return grp
        try:
            from app.market_data.static_data_store import get_static_store
            store = get_static_store()
            if store and store.is_loaded():
                data = store.get_static_data(symbol)
                if data:
                    return data.get('group', '') or ''
        except Exception:
            pass
        return ''

    @staticmethod
    def _round_lots(lots: int) -> int:
        if lots < MIN_LOT_SIZE:
            return 0
        return round(lots / LOT_ROUND_TO) * LOT_ROUND_TO


# ═══════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════

_hedger_instance: Optional[ActmanHedgerEngine] = None


def get_actman_hedger() -> ActmanHedgerEngine:
    global _hedger_instance
    if _hedger_instance is None:
        _hedger_instance = ActmanHedgerEngine()
    return _hedger_instance
