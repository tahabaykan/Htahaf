"""
ACTMAN Scoring Engine V8 — 3-Tier Execution

Hedger Scoring (V7): 30/30/20 + 20 = 100 (group-relative)
Panic Scoring (V8):  20/25/15/20/15/5 = 100 (SFS/FB + ADV size)

3-Tier Execution Gate:
  K1: Always available (pasif limit)
  K2: spread ≤ $0.20 + truth ≤ $0.15 (frontlama)
  K3: spread ≤ $0.12 + truth ≤ $0.08 (aktif vuruş)

Tier Fallback: K3 unavailable → K2, K2 unavailable → K1
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger

from app.actman.actman_config import (
    CGRUP_MAX_STEPS, AVG_ADV_MAX_RATIO, MIN_AVG_ADV, MAX_SPREAD_PCT,
    TIER_K2_MAX_SPREAD, TIER_K2_MAX_TRUTH_DIST,
    TIER_K3_MAX_SPREAD, TIER_K3_MAX_TRUTH_DIST,
    TRUTH_PROX_MAX_DIST,
    K1_SPREAD_FRACTION, K2_TRUTH_OFFSET, K3_ACTIVE_OFFSET,
    KUPONLU_GROUPS, ACTMAN_ELIGIBLE_HELD_GROUPS,
    PANIC_ADV_SIZE_BREAKPOINTS, PANIC_MAX_SPREAD_PCT,
    is_actman_eligible,
    cgrup_distance,
)


@dataclass
class ActmanCandidate:
    """A scored candidate for ACTMAN action."""
    symbol: str
    dos_grup: str
    cgrup: str
    avg_adv: float
    # Scoring inputs
    final_score: float    # FTHG (raw value, will be group-normalized)
    spread: float         # ask - bid (dollars)
    spread_pct: float     # spread / ask * 100
    maxalw: float         # Maximum allowed lots
    current_qty: float    # Current position qty (absolute)
    maxalw_util: float    # current_qty / maxalw (0.0 = empty, 1.0 = full)
    truth_distance: float # |truth_avg - bid| (SELL) or |ask - truth_avg| (BUY)
    # Market data
    bid: float
    ask: float
    last_price: float
    son5_tick: Optional[float]  # Average of last 5 truth ticks
    # Panic-specific inputs
    sfs_score: float = 0.0      # Short Front Sell score (lower = better for short)
    fb_score: float = 0.0       # Front Buy score (higher = better for long)
    # Scoring output
    score: float = 0.0
    score_breakdown: Dict[str, float] = None
    # Execution gate
    available_tiers: List[str] = None  # ['K1', 'K2', 'K3']
    best_tier: str = "K1"
    can_active_hit: bool = False
    hit_fail_reason: str = ""
    # Order details
    action: str = ""        # BUY or SELL
    order_price: float = 0.0
    order_qty: int = 0
    order_tier: str = ""    # K1, K2, or K3

    def __post_init__(self):
        if self.score_breakdown is None:
            self.score_breakdown = {}
        if self.available_tiers is None:
            self.available_tiers = ['K1']


# ═══════════════════════════════════════════════
# GROUP FTHG RANGE CACHE
# ═══════════════════════════════════════════════

_group_fthg_range: Dict[str, Dict[str, float]] = {}


def set_group_fthg_range(ranges: Dict[str, Dict[str, float]]):
    """Set FTHG min/max per DOS_GRUP. Called during engine initialization."""
    global _group_fthg_range
    _group_fthg_range = ranges
    logger.info(f"[ACTMAN_SCORING] FTHG ranges set for {len(ranges)} groups")


def get_group_fthg_range() -> Dict[str, Dict[str, float]]:
    return _group_fthg_range


# ═══════════════════════════════════════════════
# HARD FILTERS
# ═══════════════════════════════════════════════

def hard_filter(
    candidate_dos_grup: str,
    target_dos_grup: str,
    candidate_cgrup: str,
    reference_cgrup: str,
    candidate_avg_adv: float,
    reference_avg_adv: float,
    spread_pct: float,
    avg_adv: float,
    is_kuponlu: bool = False,
) -> Tuple[bool, str]:
    """
    Hedger hard filter for candidates (both SELL and BUY).
    Returns (passed, reason_if_failed).
    """
    if not is_actman_eligible(candidate_dos_grup):
        return False, f"not_eligible:{candidate_dos_grup}"

    if candidate_dos_grup != target_dos_grup:
        return False, f"dos_grup_mismatch:{candidate_dos_grup}!={target_dos_grup}"

    # CGRUP distance — ONLY for kuponlu groups
    if is_kuponlu:
        cdist = cgrup_distance(candidate_cgrup, reference_cgrup)
        if cdist > CGRUP_MAX_STEPS:
            return False, f"cgrup_too_far:{cdist}_steps"

    # AVG_ADV ratio
    if reference_avg_adv > 0 and candidate_avg_adv > 0:
        ratio = max(candidate_avg_adv, reference_avg_adv) / min(candidate_avg_adv, reference_avg_adv)
        if ratio > AVG_ADV_MAX_RATIO:
            return False, f"adv_ratio_too_high:{ratio:.1f}x"
    elif candidate_avg_adv <= 0:
        return False, "adv_zero"

    if avg_adv < MIN_AVG_ADV:
        return False, f"adv_too_low:{avg_adv}"

    if spread_pct > MAX_SPREAD_PCT:
        return False, f"spread_too_wide:{spread_pct:.1f}%"

    return True, "ok"


hard_filter_sell = hard_filter
hard_filter_buy = hard_filter


def panic_hard_filter(
    candidate_dos_grup: str,
    spread_pct: float,
) -> Tuple[bool, str]:
    """
    Panic hard filter — much simpler than Hedger.
    No CGRUP filter, no ADV ratio filter, no group match required.
    Only: eligible group + spread limit.
    """
    if not is_actman_eligible(candidate_dos_grup):
        return False, f"not_eligible:{candidate_dos_grup}"

    if spread_pct > PANIC_MAX_SPREAD_PCT:
        return False, f"spread_too_wide:{spread_pct:.1f}%"

    return True, "ok"


# ═══════════════════════════════════════════════
# HEDGER V7 SCORING — 30/30/20 + 20
# ═══════════════════════════════════════════════

def score_sell_candidate(
    final_score: float,      # sfstot (FINAL_BS): lower in group = better short
    dos_grup: str,
    spread_pct: float,
    truth_distance: float,   # |truth_avg - bid|
    maxalw_util: float,
    adv_ratio: float,
    cgrup_steps: int,
    is_kuponlu: bool = True,
) -> Tuple[float, Dict[str, float]]:
    """V7 Scoring for SELL direction (Hedger)."""
    rng = _group_fthg_range.get(dos_grup)
    bs_min = rng.get('bs_min', rng.get('min', 0)) if rng else 0
    bs_max = rng.get('bs_max', rng.get('max', 0)) if rng else 0
    if bs_max > bs_min:
        pos_in_group = (final_score - bs_min) / (bs_max - bs_min)
        s_fthg = max(0.0, 1.0 - pos_in_group)
    else:
        s_fthg = 0.5

    s_spread = max(0.0, 1.0 - spread_pct / MAX_SPREAD_PCT)
    s_truth = max(0.0, 1.0 - truth_distance / TRUTH_PROX_MAX_DIST)
    s_maxalw = max(0.0, 1.0 - maxalw_util)
    s_adv = max(0.0, 1.0 - (adv_ratio - 1.0) / (AVG_ADV_MAX_RATIO - 1.0))

    if is_kuponlu:
        s_cgrup = max(0.0, 1.0 - cgrup_steps / max(CGRUP_MAX_STEPS, 1))
        total = s_fthg*30 + s_spread*30 + s_truth*20 + s_maxalw*8 + s_adv*7 + s_cgrup*5
    else:
        s_cgrup = 0.0
        total = s_fthg*30 + s_spread*30 + s_truth*20 + s_maxalw*10 + s_adv*10

    breakdown = {
        'bs_score': round(s_fthg * 30, 2),
        'spread': round(s_spread * 30, 2),
        'truth_prox': round(s_truth * 20, 2),
        'maxalw': round(s_maxalw * (8 if is_kuponlu else 10), 2),
        'avg_adv': round(s_adv * (7 if is_kuponlu else 10), 2),
    }
    if is_kuponlu:
        breakdown['cgrup'] = round(s_cgrup * 5, 2)

    return round(total, 1), breakdown


def score_buy_candidate(
    final_score: float,      # fbtot (FINAL_AB): higher in group = better long
    dos_grup: str,
    spread_pct: float,
    truth_distance: float,   # |ask - truth_avg|
    maxalw_util: float,
    adv_ratio: float,
    cgrup_steps: int,
    is_kuponlu: bool = True,
) -> Tuple[float, Dict[str, float]]:
    """V7 Scoring for BUY direction (Hedger)."""
    rng = _group_fthg_range.get(dos_grup)
    ab_min = rng.get('ab_min', rng.get('min', 0)) if rng else 0
    ab_max = rng.get('ab_max', rng.get('max', 0)) if rng else 0
    if ab_max > ab_min:
        pos_in_group = (final_score - ab_min) / (ab_max - ab_min)
        s_fthg = max(0.0, pos_in_group)
    else:
        s_fthg = 0.5

    s_spread = max(0.0, 1.0 - spread_pct / MAX_SPREAD_PCT)
    s_truth = max(0.0, 1.0 - truth_distance / TRUTH_PROX_MAX_DIST)
    s_maxalw = max(0.0, 1.0 - maxalw_util)
    s_adv = max(0.0, 1.0 - (adv_ratio - 1.0) / (AVG_ADV_MAX_RATIO - 1.0))

    if is_kuponlu:
        s_cgrup = max(0.0, 1.0 - cgrup_steps / max(CGRUP_MAX_STEPS, 1))
        total = s_fthg*30 + s_spread*30 + s_truth*20 + s_maxalw*8 + s_adv*7 + s_cgrup*5
    else:
        s_cgrup = 0.0
        total = s_fthg*30 + s_spread*30 + s_truth*20 + s_maxalw*10 + s_adv*10

    breakdown = {
        'ab_score': round(s_fthg * 30, 2),
        'spread': round(s_spread * 30, 2),
        'truth_prox': round(s_truth * 20, 2),
        'maxalw': round(s_maxalw * (8 if is_kuponlu else 10), 2),
        'avg_adv': round(s_adv * (7 if is_kuponlu else 10), 2),
    }
    if is_kuponlu:
        breakdown['cgrup'] = round(s_cgrup * 5, 2)

    return round(total, 1), breakdown


# ═══════════════════════════════════════════════
# PANIC SCORING — 20/25/15/20/15/5
# ═══════════════════════════════════════════════

def _adv_size_score(avg_adv: float) -> float:
    """Score based on absolute ADV size (no hard filter — pure scoring)."""
    for threshold, points in PANIC_ADV_SIZE_BREAKPOINTS:
        if avg_adv >= threshold:
            return points
    return 0.0


def score_panic_sell(
    final_bs: float,          # FINAL_BS (group-relative)
    dos_grup: str,
    spread_pct: float,
    truth_distance: float,    # |truth_avg - bid|
    maxalw_util: float,
    sfs_score: float,         # Short Front Sell score (lower = cheaper to front sell)
    avg_adv: float,           # Absolute AVG_ADV
) -> Tuple[float, Dict[str, float]]:
    """
    Panic SELL scoring — 100 puan.
    BS(20) + Spread(25) + Truth(15) + SFS(20) + ADV_size(15) + MAXALW(5)
    """
    # 1. BS grup-içi (20 puan) — düşük = iyi short
    rng = _group_fthg_range.get(dos_grup)
    bs_min = rng.get('bs_min', rng.get('min', 0)) if rng else 0
    bs_max = rng.get('bs_max', rng.get('max', 0)) if rng else 0
    if bs_max > bs_min:
        pos = (final_bs - bs_min) / (bs_max - bs_min)
        s_bs = max(0.0, 1.0 - pos)
    else:
        s_bs = 0.5

    # 2. Spread (25 puan)
    s_spread = max(0.0, 1.0 - spread_pct / PANIC_MAX_SPREAD_PCT)

    # 3. Truth proximity (15 puan)
    s_truth = max(0.0, 1.0 - truth_distance / TRUTH_PROX_MAX_DIST)

    # 4. SFS score (20 puan) — düşük SFS = front sell ucuz = iyi
    # SFS range is typically -2000 to +2000
    # Normalize: SFS < 0 is best (score = 1.0), SFS > 1000 is worst (score = 0.0)
    if sfs_score <= 0:
        s_sfs = 1.0
    elif sfs_score >= 1000:
        s_sfs = 0.0
    else:
        s_sfs = max(0.0, 1.0 - sfs_score / 1000.0)

    # 5. ADV büyüklüğü (15 puan) — yüksek ADV = iyi
    s_adv_size = _adv_size_score(avg_adv)

    # 6. MAXALW (5 puan)
    s_maxalw = max(0.0, 1.0 - maxalw_util)

    total = s_bs * 20 + s_spread * 25 + s_truth * 15 + s_sfs * 20 + s_adv_size + s_maxalw * 5

    breakdown = {
        'bs_score': round(s_bs * 20, 2),
        'spread': round(s_spread * 25, 2),
        'truth_prox': round(s_truth * 15, 2),
        'sfs': round(s_sfs * 20, 2),
        'adv_size': round(s_adv_size, 2),
        'maxalw': round(s_maxalw * 5, 2),
    }

    return round(total, 1), breakdown


def score_panic_buy(
    final_ab: float,          # FINAL_AB (group-relative)
    dos_grup: str,
    spread_pct: float,
    truth_distance: float,    # |ask - truth_avg|
    maxalw_util: float,
    fb_score: float,          # Front Buy score (higher = better for long)
    avg_adv: float,
) -> Tuple[float, Dict[str, float]]:
    """
    Panic BUY scoring — 100 puan.
    AB(20) + Spread(25) + Truth(15) + FB(20) + ADV_size(15) + MAXALW(5)
    """
    rng = _group_fthg_range.get(dos_grup)
    ab_min = rng.get('ab_min', rng.get('min', 0)) if rng else 0
    ab_max = rng.get('ab_max', rng.get('max', 0)) if rng else 0
    if ab_max > ab_min:
        pos = (final_ab - ab_min) / (ab_max - ab_min)
        s_ab = max(0.0, pos)
    else:
        s_ab = 0.5

    s_spread = max(0.0, 1.0 - spread_pct / PANIC_MAX_SPREAD_PCT)
    s_truth = max(0.0, 1.0 - truth_distance / TRUTH_PROX_MAX_DIST)

    # FB score: higher = better. Range: -2000 to +2000
    if fb_score >= 1000:
        s_fb = 1.0
    elif fb_score <= 0:
        s_fb = 0.0
    else:
        s_fb = min(1.0, fb_score / 1000.0)

    s_adv_size = _adv_size_score(avg_adv)
    s_maxalw = max(0.0, 1.0 - maxalw_util)

    total = s_ab * 20 + s_spread * 25 + s_truth * 15 + s_fb * 20 + s_adv_size + s_maxalw * 5

    breakdown = {
        'ab_score': round(s_ab * 20, 2),
        'spread': round(s_spread * 25, 2),
        'truth_prox': round(s_truth * 15, 2),
        'fb': round(s_fb * 20, 2),
        'adv_size': round(s_adv_size, 2),
        'maxalw': round(s_maxalw * 5, 2),
    }

    return round(total, 1), breakdown


# ═══════════════════════════════════════════════
# 3-TIER EXECUTION GATE
# ═══════════════════════════════════════════════

def check_available_tiers(
    spread: float,
    truth_distance: float,
    son5_tick: Optional[float],
) -> List[str]:
    """
    Determine which execution tiers are available for a candidate.

    K1: Always available (pasif limit)
    K2: truth data exists + spread ≤ $0.20 + truth_distance ≤ $0.15
    K3: spread ≤ $0.12 + truth_distance ≤ $0.08

    Returns: list of available tiers, e.g. ['K1', 'K2', 'K3']
    """
    tiers = ['K1']  # K1 always available

    has_truth = son5_tick is not None and son5_tick > 0

    # K2: FRONT
    if has_truth and spread <= TIER_K2_MAX_SPREAD and truth_distance <= TIER_K2_MAX_TRUTH_DIST:
        tiers.append('K2')

    # K3: AKTIF
    if has_truth and spread <= TIER_K3_MAX_SPREAD and truth_distance <= TIER_K3_MAX_TRUTH_DIST:
        tiers.append('K3')

    return tiers


def calculate_order_price(
    tier: str,
    direction: str,      # "SELL" or "BUY"
    bid: float,
    ask: float,
    spread: float,
    son5_tick: Optional[float],
) -> float:
    """
    Calculate order price based on tier and direction.

    SELL:
      K1: ask - spread * 0.15
      K2: truth - $0.01
      K3: bid - $0.01

    BUY:
      K1: bid + spread * 0.15
      K2: truth + $0.01
      K3: ask + $0.01
    """
    truth = son5_tick if son5_tick and son5_tick > 0 else None

    if direction == "SELL":
        if tier == 'K3':
            return round(bid - K3_ACTIVE_OFFSET, 2)
        elif tier == 'K2' and truth:
            return round(truth - K2_TRUTH_OFFSET, 2)
        else:  # K1
            return round(ask - spread * K1_SPREAD_FRACTION, 2)
    else:  # BUY
        if tier == 'K3':
            return round(ask + K3_ACTIVE_OFFSET, 2)
        elif tier == 'K2' and truth:
            return round(truth + K2_TRUTH_OFFSET, 2)
        else:  # K1
            return round(bid + spread * K1_SPREAD_FRACTION, 2)


def select_best_tier(available_tiers: List[str], requested_tier: str) -> str:
    """
    Select the best available tier, with fallback.
    K3 requested but unavailable → K2, K2 unavailable → K1.
    """
    tier_priority = ['K3', 'K2', 'K1']
    start_idx = tier_priority.index(requested_tier) if requested_tier in tier_priority else 0

    for tier in tier_priority[start_idx:]:
        if tier in available_tiers:
            return tier

    return 'K1'  # ultimate fallback


# Legacy compatibility aliases
def check_execution_gate(
    spread: float,
    target_price: float,
    son5_tick: Optional[float],
    direction: str,
) -> Tuple[bool, str]:
    """Legacy 2-tier gate — returns K3 availability."""
    if son5_tick is None or son5_tick <= 0:
        return False, "no_truth_tick_data"

    distance = abs(target_price - son5_tick)
    tiers = check_available_tiers(spread, distance, son5_tick)

    can_k3 = 'K3' in tiers
    if can_k3:
        return True, "ok"

    reasons = []
    if spread > TIER_K3_MAX_SPREAD:
        reasons.append(f"spread_{spread:.3f}_gt_{TIER_K3_MAX_SPREAD}")
    if distance > TIER_K3_MAX_TRUTH_DIST:
        reasons.append(f"truth_dist_{distance:.3f}_gt_{TIER_K3_MAX_TRUTH_DIST}")
    return False, "|".join(reasons) if reasons else "ok"


# ═══════════════════════════════════════════════════════════════════
# DECREASE SCORING — Find worst positions to reduce
# ═══════════════════════════════════════════════════════════════════

def score_long_decrease(
    grup_pct: float,
    spread: float,
    spread_pct: float,
    truth_bid_dist: float,
    maxalw_util: float,
    final_bs: float = 0.0,
) -> Tuple[float, str]:
    """
    Score a LONG position for DECREASE (selling).
    Higher score = should be sold first (worst long).

    Uses GROUP-RELATIVE percentile (grup_pct) instead of absolute FTHG.
    grup_pct = (FTHG - group_min) / (group_max - group_min)
      - 0% = worst in group (lowest FTHG) → SELL FIRST
      - 100% = best in group → KEEP

    Logic:
      - Low grup_pct = bad long in its group → high dec score
      - Narrow spread = easy to execute → high dec score
      - Truth close to bid = can hit bid easily → high dec score
      - High MAXALW util = too concentrated → slight boost
    """
    from app.actman.actman_config import (
        DEC_WEIGHT_SCORE, DEC_WEIGHT_SPREAD, DEC_WEIGHT_TRUTH, DEC_WEIGHT_MAXALW,
    )

    # 1. Group-relative percentile: low = bad long = high DEC score
    # grup_pct is 0.0 to 1.0 (0 = worst in group)
    gp = max(0.0, min(1.0, grup_pct))
    score_norm = 1.0 - gp  # Inverse: worst in group → highest score
    score_pts = score_norm * DEC_WEIGHT_SCORE

    # 2. Spread: narrow = good execution = high score
    spr_norm = max(0.0, min(1.0, 1.0 - (spread_pct / 2.0)))  # 2% → 0, 0% → 1
    spr_pts = spr_norm * DEC_WEIGHT_SPREAD

    # 3. Truth-Bid proximity: close = bid pressure = high score
    truth_norm = max(0.0, min(1.0, 1.0 - (truth_bid_dist / 0.15)))  # $0.15 → 0, $0 → 1
    truth_pts = truth_norm * DEC_WEIGHT_TRUTH

    # 4. MAXALW utilization: high = concentrated = slight boost
    maxalw_pts = min(1.0, maxalw_util) * DEC_WEIGHT_MAXALW

    total = score_pts + spr_pts + truth_pts + maxalw_pts

    breakdown = (
        f"DEC_LONG: grup%={gp:.0%}→{score_pts:.1f} "
        f"spr={spread_pct:.2f}%→{spr_pts:.1f} "
        f"truth_bid=${truth_bid_dist:.3f}→{truth_pts:.1f} "
        f"maxalw={maxalw_util:.0%}→{maxalw_pts:.1f} "
        f"[bs={final_bs:.0f}]"
    )

    return total, breakdown


def score_short_decrease(
    grup_pct: float,
    spread: float,
    spread_pct: float,
    truth_ask_dist: float,
    maxalw_util: float,
    final_ab: float = 0.0,
) -> Tuple[float, str]:
    """
    Score a SHORT position for DECREASE (covering/buying).
    Higher score = should be covered first (worst short).

    Uses GROUP-RELATIVE percentile (grup_pct) for FTHG.
    grup_pct = (FTHG - group_min) / (group_max - group_min)
      - 100% = best stock in group → BAD short → COVER FIRST
      - 0% = worst stock in group → GOOD short → KEEP

    Logic:
      - High grup_pct = good stock being shorted = bad short → high dec score
      - Narrow spread = easy to cover → high dec score
      - Truth close to ask = can hit ask easily → high dec score
      - High MAXALW util = too concentrated → slight boost
    """
    from app.actman.actman_config import (
        DEC_WEIGHT_SCORE, DEC_WEIGHT_SPREAD, DEC_WEIGHT_TRUTH, DEC_WEIGHT_MAXALW,
    )

    # 1. Group-relative percentile: HIGH = good stock = bad short = high DEC score
    gp = max(0.0, min(1.0, grup_pct))
    score_norm = gp  # Direct: best in group → worst short → highest score
    score_pts = score_norm * DEC_WEIGHT_SCORE

    # 2. Spread: narrow = good execution = high score
    spr_norm = max(0.0, min(1.0, 1.0 - (spread_pct / 2.0)))
    spr_pts = spr_norm * DEC_WEIGHT_SPREAD

    # 3. Truth-Ask proximity: close = buy pressure = high score
    truth_norm = max(0.0, min(1.0, 1.0 - (truth_ask_dist / 0.15)))
    truth_pts = truth_norm * DEC_WEIGHT_TRUTH

    # 4. MAXALW utilization
    maxalw_pts = min(1.0, maxalw_util) * DEC_WEIGHT_MAXALW

    total = score_pts + spr_pts + truth_pts + maxalw_pts

    breakdown = (
        f"DEC_SHORT: grup%={gp:.0%}→{score_pts:.1f} "
        f"spr={spread_pct:.2f}%→{spr_pts:.1f} "
        f"truth_ask=${truth_ask_dist:.3f}→{truth_pts:.1f} "
        f"maxalw={maxalw_util:.0%}→{maxalw_pts:.1f} "
        f"[ab={final_ab:.0f}]"
    )

    return total, breakdown


def calculate_decrease_lot(
    current_qty: int,
    proposed_lot: int,
    min_lot: int = 125,
    full_close_threshold: int = 400,
    dust_threshold: int = 70,
    round_to: int = 100,
) -> Tuple[int, str]:
    """
    Calculate decrease lot with LT_TRIM/KARBOTU rules.

    Rules:
      1. current_qty < min_lot → skip (dust, too small to decrease)
      2. proposed_lot → round to 100
      3. remaining = current_qty - proposed_lot
         - remaining < dust_threshold → full close (komple kapat)
         - remaining < full_close_threshold → full close (komple kapat)
      4. proposed_lot > current_qty → clamp to current_qty (no flip!)
      5. proposed_lot < min_lot → skip

    Returns:
        (adjusted_lot, reason)
    """
    current_qty = abs(current_qty)

    if current_qty < min_lot:
        return 0, f"position_too_small:{current_qty}<{min_lot}"

    # Clamp to current (no flip)
    lot = min(proposed_lot, current_qty)

    # Round
    lot = (lot // round_to) * round_to

    if lot < min_lot:
        return 0, f"lot_below_min:{lot}<{min_lot}"

    # Post-trade remaining check
    remaining = current_qty - lot

    if 0 < remaining < full_close_threshold:
        # Remaining too small → full close
        lot = current_qty
        return lot, f"full_close:remaining={remaining}<{full_close_threshold}"

    return lot, "ok"
