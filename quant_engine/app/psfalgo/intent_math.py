
"""
Quant Engine - Intent & Lot Logic (Shared Math)
Mental Model v1
"""
import math
from typing import Dict, Any, Tuple, Optional

def compute_intents(exposure_pct: float, config: Dict[str, Any]) -> Tuple[float, float, str]:
    """
    Compute AddIntent and ReduceIntent based on exposure and config.
    Implements Piecewise Model C.

    Args:
        exposure_pct: Current global gross exposure % (e.g., 50.0, 95.0, 125.0)
        config: Dict containing 'hard_threshold_pct', 'soft_ratio_num', 'soft_ratio_den', 
                'Amax', 'Asoft', 'pn', 'q', 'ps'

    Returns:
        (AddIntent, ReduceIntent, Regime)
        AddIntent: 0.0 - 100.0
        ReduceIntent: 0.0 - 100.0
        Regime: "NORMAL" | "SOFT" | "HARD"
    """
    # 1. Parse Config & Thresholds
    H = float(config.get('hard_threshold_pct', 130.0))
    soft_num = float(config.get('soft_ratio_num', 12))
    soft_den = float(config.get('soft_ratio_den', 13))
    S = H * (soft_num / soft_den)

    # Shape params
    Amax = float(config.get('Amax', 100.0))
    Asoft = float(config.get('Asoft', 20.0))
    pn = float(config.get('pn', 1.25))
    q = float(config.get('q', 2.14))
    ps = float(config.get('ps', 1.50))

    # 2. Determine Regime & Compute AddIntent
    regime = "NORMAL"
    add_intent = 0.0

    if exposure_pct <= S:
        # NORMAL ZONE
        regime = "NORMAL"
        # Avoid division by zero
        if S <= 0:
            x = 0
        else:
            x = (exposure_pct / S) ** q
        
        # Clamp x to [0, 1] essentially
        if x > 1: x = 1 
        if x < 0: x = 0

        # Formula: AddIntent = Asoft + (Amax - Asoft) * (1 - x)^pn
        add_intent = Asoft + (Amax - Asoft) * (1 - x) ** pn

    elif S < exposure_pct < H:
        # SOFT DERISK ZONE
        regime = "SOFT"
        # t = (E - S) / (H - S)
        denom = (H - S)
        if denom <= 0:
            t = 1.0
        else:
            t = (exposure_pct - S) / denom
        
        if t > 1: t = 1
        if t < 0: t = 0
        
        # Formula: AddIntent = Asoft * (1 - t)^ps
        add_intent = Asoft * (1 - t) ** ps

    else:
        # HARD DERISK ZONE (E >= H)
        regime = "HARD"
        add_intent = 0.0

    # 3. Compute ReduceIntent
    # Ensure add_intent is in [0, 100] just in case
    add_intent = max(0.0, min(100.0, add_intent))
    reduce_intent = 100.0 - add_intent

    return add_intent, reduce_intent, regime


def compute_desire(intent: float, goodness: float, alpha: float = 1.0, beta: float = 2.0) -> float:
    """
    Compute Desire score [0, 1.0]

    Args:
        intent: AddIntent or ReduceIntent [0, 100]
        goodness: Normalized goodness score [0, 100]
        alpha: Intent sensitivity exponent (default 1.0)
        beta: Goodness sensitivity exponent (default 2.0)
    
    Returns:
        Desire coefficient 0.0 to 1.0
    """
    i_norm = intent / 100.0
    g_norm = goodness / 100.0
    
    i_norm = max(0.0, min(1.0, i_norm))
    g_norm = max(0.0, min(1.0, g_norm))

    return (i_norm ** alpha) * (g_norm ** beta)


def calculate_rounded_lot(raw_lot: float, policy: Optional[Dict[str, Any]] = None) -> int:
    """
    Apply strict rounding policy (Janall DNA).
    
    Rules:
    - raw < 100 => 0
    - 100 <= raw < 150 => 0 (Prohibited Zone 100-199, rounds down)
    - 150 <= raw < 250 => 200 (Prohibited Zone 100-199, rounds up)
    - raw >= 250 => Round to nearest 100 (300, 400, ...)
    
    Result is ALWAYS either 0 or >= 200. NEVER 100.

    Args:
        raw_lot: calculated raw lot size
        policy: dict containing 'rounding' rules (optional, uses defaults if None)
    
    Returns:
        Rounded integer lot size
    """
    if policy is None:
        policy = {}
    
    # These might be configurable, but the prompt rules are strict
    # min_trade_lot = 200
    
    if raw_lot < 100:
        return 0
    
    # Standard rounding to nearest 100
    # Using arithmetic rounding (Half Up) to avoid Banker's Rounding (2.5->2)
    # 250 -> 2.5 -> 3.0 -> 300
    rounded = int((raw_lot / 100.0) + 0.5) * 100
    
    # Enforce "Never 100" rule
    if rounded == 100:
        return 0  # 100-149 range -> 0
        
    # If rounded resulted in 200 (from 150-249 range), it's valid.
    # If rounded is 0 (from <50), it's valid.
    
    return rounded


def calculate_ucuzluk_score(price: float, prev_close: float, benchmark_chg: float) -> float:
    """
    Calculate raw 'ucuzluk' (cheapness) or 'pahalilik' (expensiveness) score.
    
    Score = (Price - PrevClose) - BenchmarkChg
    
    Args:
        price: Current price (Bid, Ask, Last, etc.)
        prev_close: Previous close price
        benchmark_chg: Benchmark change in currency value (not percentage)
        
    Returns:
        Raw change score (e.g., -0.05 means dropped 0.05 more than benchmark -> cheap)
    """
    if prev_close <= 0:
        return 0.0
    
    price_change = price - prev_close
    return price_change - benchmark_chg


def calculate_final_score(base_score: float, ucuzluk_score: float, multiplier: float = 1000.0) -> float:
    """
    Calculate Final Score using Janall formula.
    
    Final = Base - (Multiplier * Ucuzluk)
    
    Long (Final_BB/FB):
      - Low Ucuzluk (negative) is good -> Score Increases
      - Base Score (FINAL_THG) is higher better
      
    Short (Final_SAS/SFS):
      - High Pahalilik (positive) is good for short?
      - Janall Logic: 
        Final_SAS = SHORT_FINAL - (1000 * ask_sell_pahalilik)
        If Pahalilik is High (e.g. +0.50), Score drops heavily. 
        So for Short, LOWER score is better? 
        WAIT: Janall uses 'select_top_stocks' with 'ascending=True' for Shorts.
        So YES, Lower Score is better for Shorts.
        High Pahalilik (+0.50) -> Score - 500 -> Very Low Score -> Selected Top 1.
        
    Args:
        base_score: FINAL_THG (Long) or SHORT_FINAL (Short)
        ucuzluk_score: Calculated ucuzluk/pahalilik value
        multiplier: Default 1000
        
    Returns:
        Final combined score
    """
    return base_score - (multiplier * ucuzluk_score)



def clamp_no_flip(existing_qty: float, proposed_qty: float, action: str) -> float:
    """
    Ensure a trade doesn't flip the position (Short -> Long or Long -> Short).
    
    Args:
        existing_qty: Current position signed quantity
        proposed_qty: Proposed absolute quantity to trade
        action: "BUY" or "SELL"
    
    Returns:
        Clamped quantity (absolute)
    """
    proposed_qty = abs(proposed_qty)
    
    if action == "SELL" and existing_qty > 0:
        # Long position, selling: Limit to existing
        if proposed_qty > existing_qty:
            return existing_qty
            
    elif action == "BUY" and existing_qty < 0:
        # Short position, buying: Limit to existing (abs)
        if proposed_qty > abs(existing_qty):
            return abs(existing_qty)
            
    # If adding to position (Long -> Buy, Short -> Sell), no flip risk
    # But usually this guard is for exits/reductions.
    # If starting fresh (existing=0), no flip risk.
    
    return proposed_qty


def clamp_post_trade_hold(existing_qty: float, proposed_qty: float, action: str, min_hold: int = 200) -> float:
    """
    Enforce '0 or >= 200' post-trade rule.
    If remaining holding would be in [1, 199], force full close.
    
    Args:
        existing_qty: Current position signed quantity
        proposed_qty: Proposed absolute quantity
        action: "BUY" or "SELL"
        min_hold: Minimum holding preference (default 200)
        
    Returns:
        Adjusted proposed quantity
    """
    proposed_qty = abs(proposed_qty)
    post_qty = 0
    
    if action == "SELL":
        # Check Long side
        if existing_qty > 0:
            post_qty = existing_qty - proposed_qty
    elif action == "BUY":
        # Check Short side
        if existing_qty < 0:
            post_qty = abs(existing_qty) - proposed_qty
            
    # If post_qty is negative, it's a flip/overshoot -> handle via no_flip or allow here?
    # Usually clamp_no_flip should run first or concurrently.
    # Assuming valid reduction (not flip):
    
    if 0 < post_qty < min_hold:
        # Remaining is dust (e.g. 178).
        # Force full close -> existing_qty (abs)
        return abs(existing_qty)
        
    return proposed_qty
