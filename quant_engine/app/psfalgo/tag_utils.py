"""
PSFALGO Tag Utils
Logic for resolving Janall Strategy Tags and Position Tags.
"""

from app.api.janall_models import StrategyTag

def resolve_strategy_tag(
    action: str,
    current_qty: float,
    intended_book: str = "LT"  # "LT" or "MM" (Derived from Engine Source)
) -> str:
    """
    Resolve high-level Strategy Tag (Order Tag) based on context.
    
    Args:
        action: 'BUY' or 'SELL' or 'ADD_LONG' etc.
        current_qty: Current position quantity (Net)
        intended_book: 'LT' (default) or 'MM'. Derived from which engine originating the order.
        
    Returns:
        StrategyTag enum value (e.g. 'LT_LONG_INCREASE')
    """
    # 1. Determine Prefix (LT vs MM) from Intended Book
    book = intended_book.upper()
    if book not in ["LT", "MM"]:
        book = "LT" # Default fallback
    
    # 2. Determine Position Side (Long/Short)
    # If currently flat, Action determines Side
    if abs(current_qty) < 0.001:
        # Flat start
        if "BUY" in action.upper() or "ADD_LONG" in action.upper():
            side = "LONG"
        else: # SELL or ADD_SHORT
            side = "SHORT"
    else:
        # Existing position determines Side
        side = "LONG" if current_qty > 0 else "SHORT"
        
    # 3. Determine Direction (Increase/Decrease)
    # Map input action to simple BUY/SELL
    is_buy = "BUY" in action.upper() or "ADD_LONG" in action.upper() or "REDUCE_SHORT" in action.upper()
    is_sell = "SELL" in action.upper() or "ADD_SHORT" in action.upper() or "REDUCE_LONG" in action.upper()
    # Note: REDUCE_SHORT is a BUY order. REDUCE_LONG is a SELL order.
    
    direction = "INCREASE"
    
    if side == "LONG":
        if is_buy:
             direction = "INCREASE" # Buying more Long
        elif is_sell:
             direction = "DECREASE" # Selling Long
             
    elif side == "SHORT":
        if is_sell:
             direction = "INCREASE" # Selling more Short
        elif is_buy:
             direction = "DECREASE" # Buying back Short (Cover)
             
    # 4. Construct Tag
    tag_str = f"{book}_{side}_{direction}"
    
    # Validation (Optional)
    # try:
    #     return StrategyTag(tag_str).value
    # except ValueError:
    #     return tag_str
        
    return tag_str
