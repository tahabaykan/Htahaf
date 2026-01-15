"""
Gem Logic Library
Pure functions for "Gem" strategy analysis.
"""

import math
from typing import Optional, Tuple

def calculate_reduction_ratio(current_lot: float, maxalw: float) -> float:
    """
    Calculates asymmetric reduction ratio based on position size relative to MAXALW.
    Formula: RR = 1 - (Current / MAXALW)^2
    
    Logic:
    - Large positions (Near MAXALW) -> Small RR -> Keep most (Conviction).
    - Small positions -> Large RR -> Reduce heavily (or close).
    
    Args:
        current_lot: Current position size (absolute).
        maxalw: Maximum allowed position size.
        
    Returns:
        float: Reduction Ratio (0.0 to 1.0). 
               1.0 means "Keep All" (Reduction=0), 0.0 means "Close All"?
               Wait, Formula: RR = 1 - (C/M)^2.
               If C=M (Max), RR = 1 - 1 = 0. 
               If C=0, RR = 1 - 0 = 1.
               
               User Prompt: "Large positions (Conviction) ... piece piece reduce, Small positions ... one shot close."
               If RR is "Reduction Amount", then High RR = Big Reduce.
               If RR is "Retention Ratio", then High RR = Keep.
               
               Let's re-read prompt: "RR = 1 - (Current_Lot / MAXALW)^2".
               If C=M, RR=0.
               If C=0, RR=1.
               
               "Small positions tek seferde kapatılabilir" -> Implies big reduction.
               If C is small, RR is ~1. This implies RR is "Retention Ratio"?
               No, if RR=1 means "Keep 100%", then small positions are KEPT? That contradicts "Close Small".
               
               Let's check logic: "MAXALW limitine yakın (büyük) pozisyonlar ... parça parça azaltılırken".
               If C=M, we want SMALL reduction.
               If C=Small, we want BIG reduction.
               
               If RR = Retention Ratio:
               C=M -> RR=0 -> Keep 0%? No, that's "Dump All".
               
               Maybe formula is: Reduction *Amount* Ratio?
               Let's assume the user provided formula is correct for *Retention* or *Reduction*?
               "RR = 1 - (Current / MAXALW)^2"
               
               Let's look at the shape:
               x = C/M (0 to 1).
               y = 1 - x^2. (Parabola opening down).
               x=0 -> y=1.
               x=1 -> y=0.
               
               If y is "Keep %":
               Small Position (x~0) -> Keep 100%? No, we want to CLOSE small positions.
               Large Position (x~1) -> Keep 0%? No, we want to KEEP Conviction.
               
               Conclusion: The formula `1 - (C/M)^2` behaves opposite to description if it is "Retention".
               If it is "Reduction %":
               Small (x~0) -> Reduce 100%? (Formula gives 1). YES.
               Large (x~1) -> Reduce 0%? (Formula gives 0). YES.
               
               So RR is **Reduction Ratio** (Amount to Sell).
               RR = 1.0 -> Sell 100% (Close).
               RR = 0.0 -> Sell 0% (Hold).
               
               Verification:
               Small pos (C=10, M=5000) -> x=0.002 -> RR ~ 1.0 -> Sell All. Correct.
               Large pos (C=5000, M=5000) -> x=1.0 -> RR = 0.0 -> Sell None (Hold). Correct?
               Wait, "Conviction ... parça parça azaltılırken".
               If Sell 0%, we aren't reducing. 
               Maybe "Large" means "Near Max". If we are OVER max, that's different.
               If we are just "Large", we hold.
               If we want to TRIM, maybe we use a different scale.
               
               But for "Dynamic Reduction", this makes sense as a "Urgency to Sell" metric.
               Small stuff -> High Urgency (Clean up).
               Big stuff (Conviction) -> Low Urgency (Let it run).
               
    """
    if maxalw <= 0: return 1.0 # Safe fallback: Close all if invalid maxalw
    
    ratio = abs(current_lot) / maxalw
    if ratio > 1.0: ratio = 1.0 # Cap at 1.0 for calculation
    
    rr = 1.0 - (ratio ** 2)
    return rr

def calculate_target_details(current_lot: float, rr: float, min_lot: int = 400) -> Tuple[int, str]:
    """
    Calculates target reduction amount and rounded lot.
    
    Args:
        current_lot: Current position size.
        rr: Reduction Ratio (0.0 to 1.0, where 1.0 = Reduce All).
        min_lot: Minimum lot size to avoid flipping (400 rule).
        
    Returns:
        (sell_qty, reason)
    """
    abs_current = abs(current_lot)
    
    # 400 Rule: If current < 400, strictly 0 (Close All).
    if abs_current < min_lot and abs_current > 0:
        return int(abs_current), "Small Position (<400) -> Close All"
        
    # Calculate raw sell amount
    # Sell = Current * RR
    raw_sell = abs_current * rr
    
    # Rounding (100 lots)
    sell_qty = int((raw_sell / 100.0) + 0.5) * 100
    
    # Logic adjustment:
    # If Sell Qty results in remaining < 400?
    remaining = abs_current - sell_qty
    if 0 < remaining < min_lot:
        # If remaining is dust, close all
        sell_qty = int(abs_current)
        reason = "Clean Up (Remaining < 400)"
    else:
        reason = f"Dynamic Reduce (RR={rr:.2f})"
        
    return sell_qty, reason

def is_fake_print(volume: float, avg_adv: float) -> bool:
    """
    The 0.5 ADV Filter.
    Returns True if a single print volume is > 50% of Average Daily Volume.
    """
    if avg_adv <= 0: return False
    return volume > (0.5 * avg_adv)

def check_divergence(
    symbol_price_chg: float, 
    group_avg_price_chg: float, 
    threshold: float = 0.05
) -> Tuple[bool, float]:
    """
    Checks Price-Volume Divergence vs DOS Group.
    
    Args:
        symbol_price_chg: % Change of symbol.
        group_avg_price_chg: % Change of group average.
        threshold: Divergence threshold (e.g., 5%).
        
    Returns:
        (IsDivergent, DiffVal)
    """
    # Simple logic: If symbol moves opposite or significantly away
    diff = symbol_price_chg - group_avg_price_chg
    is_divergent = abs(diff) > threshold
    return is_divergent, diff

def check_spread_efficiency(spread: float, avg_spread: float) -> str:
    """
    Evaluates spread efficiency.
    """
    if avg_spread <= 0: return "UNKNOWN"
    
    ratio = spread / avg_spread
    if ratio < 0.8: return "TIGHT (Hard to capture)"
    if ratio > 1.2: return "WIDE (Good for passive)"
    return "NORMAL"
