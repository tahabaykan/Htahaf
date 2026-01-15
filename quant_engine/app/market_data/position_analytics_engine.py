"""
Position Analytics Engine
Computes position-related analytics: current/potential qty, MAXALW, 3h change, status flags.

This engine provides position analytics for monitoring and display purposes only.
It does NOT make trading decisions.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.logger import logger


class PositionAnalyticsEngine:
    """
    Computes position analytics for symbols.
    
    Outputs:
    - current_qty: Current position quantity (from position manager or 0)
    - potential_qty: Potential position quantity (from order plan or 0)
    - maxalw: MAXALW from static data (if available)
    - change_3h: 3-hour price change (if available)
    - status_flags: Various status flags (position_exists, has_potential, etc.)
    """
    
    def __init__(self):
        # Position history cache: {symbol: [(timestamp, qty, price), ...]}
        # Used for 3h change calculation
        self.position_history: Dict[str, list] = {}
        
        # Current positions cache: {symbol: qty}
        # This should be updated from position manager or external source
        self.current_positions: Dict[str, float] = {}
    
    def update_current_position(self, symbol: str, qty: float):
        """
        Update current position for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            qty: Current position quantity (positive for long, negative for short)
        """
        self.current_positions[symbol] = qty
        
        # Add to history
        if symbol not in self.position_history:
            self.position_history[symbol] = []
        
        now = datetime.now()
        self.position_history[symbol].append((now, qty, None))  # price not tracked here
        
        # Keep only last 24 hours
        cutoff = now - timedelta(hours=24)
        self.position_history[symbol] = [
            (ts, q, p) for ts, q, p in self.position_history[symbol]
            if ts >= cutoff
        ]
    
    def compute_position_analytics(
        self,
        symbol: str,
        static_data: Dict[str, Any],
        market_data: Dict[str, Any],
        order_plan: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Compute position analytics for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            static_data: Static data (may contain MAXALW)
            market_data: Market data (last, prev_close for 3h change)
            order_plan: Order plan (for potential_qty)
            
        Returns:
            Position analytics dict:
            {
                'current_qty': float,
                'potential_qty': float,
                'maxalw': float | None,
                'change_3h': float | None,
                'change_3h_percent': float | None,
                'status_flags': {
                    'position_exists': bool,
                    'has_potential': bool,
                    'at_maxalw': bool,
                    'has_3h_data': bool
                },
                'explanation': str
            }
        """
        try:
            # Get current position
            current_qty = self.current_positions.get(symbol, 0.0)
            
            # Get potential qty from order plan
            potential_qty = 0.0
            if order_plan and order_plan.get('action') != 'NONE':
                potential_qty = order_plan.get('size', 0)
                # If action is SELL, potential is negative
                if order_plan.get('action') == 'SELL':
                    potential_qty = -potential_qty
            
            # Get MAXALW from static data (try different possible column names)
            maxalw = None
            for col_name in ['MAXALW', 'maxalw', 'MaxAlw', 'MAX_ALW']:
                if col_name in static_data:
                    maxalw = self._safe_float(static_data.get(col_name))
                    if maxalw is not None:
                        break
            
            # Calculate 3h change (price change over last 3 hours)
            change_3h = None
            change_3h_percent = None
            has_3h_data = False
            
            # Try to get 3h price from history or market data
            # For now, we'll use prev_close vs last as a proxy
            # In production, this should use actual 3h price history
            last = self._safe_float(market_data.get('last') or market_data.get('price'))
            prev_close = self._safe_float(market_data.get('prev_close'))
            
            if last is not None and prev_close is not None:
                change_3h = last - prev_close
                if prev_close != 0:
                    change_3h_percent = (change_3h / prev_close) * 100
                has_3h_data = True
            
            # Build status flags
            position_exists = abs(current_qty) > 0.001  # Small threshold for float comparison
            has_potential = abs(potential_qty) > 0.001
            at_maxalw = False
            if maxalw is not None and current_qty is not None:
                at_maxalw = abs(current_qty) >= maxalw
            
            status_flags = {
                'position_exists': position_exists,
                'has_potential': has_potential,
                'at_maxalw': at_maxalw,
                'has_3h_data': has_3h_data
            }
            
            # Build explanation
            explanation_parts = []
            if position_exists:
                explanation_parts.append(f"Current: {current_qty:.0f}")
            if has_potential:
                explanation_parts.append(f"Potential: {potential_qty:.0f}")
            if maxalw is not None:
                explanation_parts.append(f"MAXALW: {maxalw:.0f}")
            if change_3h_percent is not None:
                explanation_parts.append(f"3h: {change_3h_percent:+.2f}%")
            
            explanation = ", ".join(explanation_parts) if explanation_parts else "No position data"
            
            return {
                'current_qty': round(current_qty, 2) if current_qty is not None else 0.0,
                'potential_qty': round(potential_qty, 2) if potential_qty is not None else 0.0,
                'maxalw': round(maxalw, 2) if maxalw is not None else None,
                'change_3h': round(change_3h, 4) if change_3h is not None else None,
                'change_3h_percent': round(change_3h_percent, 2) if change_3h_percent is not None else None,
                'status_flags': status_flags,
                'explanation': explanation
            }
            
        except Exception as e:
            logger.error(f"Error computing position analytics for {symbol}: {e}", exc_info=True)
            return {
                'current_qty': 0.0,
                'potential_qty': 0.0,
                'maxalw': None,
                'change_3h': None,
                'change_3h_percent': None,
                'status_flags': {
                    'position_exists': False,
                    'has_potential': False,
                    'at_maxalw': False,
                    'has_3h_data': False
                },
                'explanation': f'Error: {str(e)}'
            }
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None or value == 'N/A' or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None







