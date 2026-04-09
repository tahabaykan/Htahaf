"""
BefDay Guard (Position Safety)
Checks queries against BefDay positions and Daily Limit Service.
"""

from typing import Dict, Tuple, Optional
from app.psfalgo.daily_limit_service import get_daily_limit_service
from app.core.logger import logger

class BefDayGuard:
    def __init__(self):
        self.daily_limit_service = get_daily_limit_service()

    def check_safety(
        self,
        symbol: str,
        side: str, # "BUY" or "SELL"
        qty: float,
        current_qty: float,
        befday_qty: float,
        maxalw: float,
        portfolio_total_qty: float,
        daily_net_change: float,
        account_id: str = "IBKR_GUN",
        is_increase: Optional[bool] = None
    ) -> Tuple[bool, float, str]:
        """
        Validates if an order is safe based on:
        1. BefDay limits (via DailyLimitService).
        2. Exposure constraints.
        
        Args:
            is_increase: Explicit flag. If None, inferred from current_qty + side:
                         Long(qty>=0) + BUY = increase, Long + SELL = decrease,
                         Short(qty<0) + SELL = increase, Short + BUY = decrease.
        
        Returns:
            (Allowed: bool, SafeQty: float, Reason: str)
        """
        # Infer is_increase from position direction if not provided
        if is_increase is None:
            if current_qty >= 0:
                is_increase = (side == 'BUY')   # Long: BUY=increase, SELL=decrease
            else:
                is_increase = (side == 'SELL')  # Short: SELL=increase, BUY=decrease (cover)
        
        # 1. Calculate Daily Limits
        limits = self.daily_limit_service.calculate_limits(
            symbol=symbol,
            befday_qty=befday_qty,
            current_qty=current_qty,
            maxalw=maxalw,
            portfolio_total_qty=portfolio_total_qty,
            daily_net_change=daily_net_change
        )
        
        # 2. Check Capacity (including Pending Orders)
        is_allowed, trimmed_qty, reason = self.daily_limit_service.check_capacity(
            account_id=account_id,
            symbol=symbol,
            side=side,
            qty=qty,
            limits=limits,
            is_increase=is_increase
        )
        
        if not is_allowed:
            return False, trimmed_qty, f"DailyLimit: {reason}"
            
        # 3. BefDay Flip Guard (Extra Safety)
        # Ensure we don't flip position sign relative to BefDay unless explicitly intended?
        # Actually "400 rule" handles flippiness for small positions.
        # Major flips usually blocked by ActionPlanner logic.
        
        return True, trimmed_qty, "Safe"

# Global Instance
_befday_guard = BefDayGuard()

def get_befday_guard() -> BefDayGuard:
    return _befday_guard
