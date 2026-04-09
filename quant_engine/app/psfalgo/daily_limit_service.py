"""
Daily Limit Service
Implements Janall's "Brake Mechanism" (Fren Mekanizması) for daily limits.
"""

from typing import Dict, Any, Optional, Tuple, List
from math import inf
from app.core.logger import logger
from app.psfalgo.open_order_service import get_open_order_service

class DailyLimitService:
    """
    Calculates and enforces daily trading limits based on:
    1. Increase Rules (Portfolio % Based)
    2. Decrease Rules (BefDay % Based)
    """
    
    def __init__(self):
        # Janall INCREASE Rules (Portfolio %)
        # Format: Threshold % -> (MaxAlw_Mult, Portfolio_Limit_%)
        self.increase_rules = {
            1.0: (0.50, 5.0),
            3.0: (0.40, 4.0),
            5.0: (0.30, 3.0),
            7.0: (0.20, 2.0),
            10.0: (0.10, 1.5),
            100.0: (0.05, 1.0)
        }
        
        # Janall DECREASE Rules (BefDay %)
        # Format: Threshold % -> (MaxAlw_Mult, BefDay_Cap_Mult)
        self.decrease_rules = {
            3.0: (None, None),   # Unlimited
            5.0: (0.75, 0.75),
            7.0: (0.60, 0.60),
            10.0: (0.50, 0.50),
            100.0: (0.40, 0.40)
        }
        
        self.min_lot = 400
        
    def _get_increase_limit_specs(self, portfolio_pct: float) -> Tuple[float, float]:
        """Find applicable increase rule"""
        sorted_keys = sorted(self.increase_rules.keys())
        for thresh in sorted_keys:
            if portfolio_pct < thresh:
                return self.increase_rules[thresh]
        return self.increase_rules[100.0]

    def _get_decrease_limit_specs(self, befday_portfolio_pct: float) -> Tuple[Optional[float], Optional[float]]:
        """Find applicable decrease rule"""
        sorted_keys = sorted(self.decrease_rules.keys())
        for thresh in sorted_keys:
            if befday_portfolio_pct < thresh:
                return self.decrease_rules[thresh]
        return self.decrease_rules[100.0]

    def calculate_limits(self, 
                       symbol: str,
                       befday_qty: float,
                       current_qty: float,
                       maxalw: float,
                       portfolio_total_qty: float,
                       daily_net_change: float) -> Dict[str, Any]:
        """
        Calculate both increase and decrease limits for a stock.
        
        Returns a dict describing the limits and the logic used.
        """
        abs_befday = abs(befday_qty)
        abs_current = abs(current_qty)
        
        # Avoid div/0
        if portfolio_total_qty <= 0:
            portfolio_total_qty = max(abs_current, 1.0)
            
        # 1. INCREASE LIMITS
        # Logic: Based on CURRENT portfolio percentage (or BefDay? Janall uses BefDay usually for consistent categorization)
        # Janall actually uses get_portfolio_ratio(befday_qty...)
        portfolio_pct = (abs_befday / portfolio_total_qty) * 100.0
        
        inc_maxalw_mult, inc_port_pct = self._get_increase_limit_specs(portfolio_pct)
        
        limit1 = maxalw * inc_maxalw_mult
        limit2 = portfolio_total_qty * (inc_port_pct / 100.0)
        
        raw_increase_limit = min(limit1, limit2)
        # Floor validity check
        if raw_increase_limit < self.min_lot:
            raw_increase_limit = self.min_lot
            
        # 2. DECREASE LIMITS
        dec_maxalw_mult, dec_befday_mult = self._get_decrease_limit_specs(portfolio_pct)
        
        if dec_maxalw_mult is None:
            raw_decrease_limit = float('inf') # Unlimited
        else:
            lim1 = maxalw * dec_maxalw_mult
            lim2 = abs_befday * dec_befday_mult
            raw_decrease_limit = min(lim1, lim2)
            
            # Floor check - if unlimited flag is False but calc is small
            # Special Janall rule: If abs_befday < min_lot, can sell all (unlimited)
            if abs_befday < self.min_lot:
                raw_decrease_limit = abs_befday
            elif raw_decrease_limit < self.min_lot:
                raw_decrease_limit = self.min_lot

        # ═══════════════════════════════════════════════════════════════
        # BUG-E FIX: Direction-aware consumed qty for remaining calc
        # ═══════════════════════════════════════════════════════════════
        # daily_net_change = current_qty - befday_qty (signed)
        #
        # LONG (befday >= 0):
        #   +daily_net_change = bought more (increase consumed)
        #   -daily_net_change = sold some   (decrease consumed)
        #
        # SHORT (befday < 0):
        #   -daily_net_change = shorted more (abs position grew = INCREASE consumed)
        #   +daily_net_change = covered some (abs position shrank = DECREASE consumed)
        #
        # General rule: increase moves abs(position) UP, decrease moves it DOWN.
        # ═══════════════════════════════════════════════════════════════
        if befday_qty >= 0:
            # LONG side: positive net change = increase, negative = decrease
            increase_consumed = max(0, daily_net_change)
            decrease_consumed = max(0, -daily_net_change)
        else:
            # SHORT side: negative net change = increase (more short), positive = decrease (cover)
            increase_consumed = max(0, -daily_net_change)
            decrease_consumed = max(0, daily_net_change)

        inc_remaining = max(0, int(raw_increase_limit) - increase_consumed)
        if raw_decrease_limit == float('inf'):
            dec_remaining = float('inf')
        else:
            dec_remaining = max(0, int(raw_decrease_limit) - decrease_consumed)

        return {
            'symbol': symbol,
            'portfolio_pct': portfolio_pct,
            'increase': {
                'limit_qty': int(raw_increase_limit),
                'rule_desc': f"Port% < {portfolio_pct:.1f}: Min(MaxAlw*{inc_maxalw_mult}, Port*{inc_port_pct}%)",
                'remaining': inc_remaining
            },
            'decrease': {
                'limit_qty': raw_decrease_limit if raw_decrease_limit == float('inf') else int(raw_decrease_limit),
                'rule_desc': f"Port% < {portfolio_pct:.1f}: MaxAlw*{dec_maxalw_mult}, BefDay*{dec_befday_mult}" if dec_maxalw_mult else "Unlimited",
                'remaining': dec_remaining
            }
        }

    def check_capacity(self, 
                     account_id: str,
                     symbol: str, 
                     side: str, 
                     qty: float,
                     limits: Dict[str, Any],
                     is_increase: Optional[bool] = None) -> Tuple[bool, float, str]:
        """
        Check if an order fits within limits, accounting for Pending Orders.
        
        Args:
            limits: Result from calculate_limits
            is_increase: Explicit flag for increase vs decrease.
                         If None, falls back to BUY=increase, SELL=decrease
                         (which is wrong for short positions).
                         Callers SHOULD provide this for correctness.
            
        Returns:
            (Allowed: bool, TrimmedQty: float, Reason: str)
        """
        open_order_service = get_open_order_service()
        
        # Get pending usage from Open Orders
        # Side mapping: If we want to BUY, we check pending BUYs
        pending_qty = open_order_service.get_pending_qty(account_id, symbol, side)
        
        # Determine increase vs decrease
        # If caller provides is_increase explicitly, use it (position-aware).
        # Otherwise fall back to legacy BUY=increase assumption.
        if is_increase is not None:
            limit_info = limits['increase'] if is_increase else limits['decrease']
        else:
            # Legacy fallback (only correct for long positions)
            limit_info = limits['increase'] if side == 'BUY' else limits['decrease']
        limit_total = limit_info['limit_qty']
        remaining_base = limit_info['remaining'] # This accounts for executed trades already (calc in calculate_limits)
        
        # Adjust remaining for pending
        if limit_total == float('inf'):
            return True, qty, "Unlimited"
            
        # Re-verify remaining: Limit - (Executed + Pending)
        # Note: 'remaining' from calculate_limits was just Limit - Executed.
        # So Real Remaining = Remaining_Base - Pending
        real_remaining = max(0, remaining_base - pending_qty)
        
        if qty <= real_remaining:
            return True, qty, f"OK. Cap: {int(real_remaining)} (L:{limit_total} - E - P:{int(pending_qty)})"
        else:
            # Need to trim
            trimmed = max(0, real_remaining)
            if trimmed < self.min_lot:
                 # If room is tiny (e.g. 10 lots), just block to avoid noise, unless it's a liquidation?
                 # Janall usually rounds.
                 return False, 0.0, f"Blocked. Req: {qty} > Cap: {int(real_remaining)}. Pending: {int(pending_qty)}"
            
            return False, trimmed, f"Trimmed. Req: {qty} -> {int(trimmed)}. Pending: {int(pending_qty)}"

# Global instance
_daily_limit_service = DailyLimitService()

def get_daily_limit_service() -> DailyLimitService:
    return _daily_limit_service
