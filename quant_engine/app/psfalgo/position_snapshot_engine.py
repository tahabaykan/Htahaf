"""
PSFALGO Position Snapshot Engine
Computes position snapshots with ex-div adjusted costs and position states.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from app.core.logger import logger
from app.psfalgo.state_store import PSFALGOStateStore


class PositionSnapshotEngine:
    """
    Computes position snapshots for PSFALGO.
    
    Features:
    - Ex-div adjusted befday_cost
    - Position state determination (LONG_ADD, SHORT_ADD, etc.)
    - Potential qty calculation
    - Today's average cost tracking
    - Real trading data integration (Hammer positions + orders)
    """
    
    def __init__(self, state_store: Optional[PSFALGOStateStore] = None):
        """
        Initialize position snapshot engine.
        
        Args:
            state_store: PSFALGOStateStore instance. If None, creates new one.
        """
        self.state_store = state_store or PSFALGOStateStore()
    
    def _extract_trading_data_from_cache(
        self,
        symbol: str,
        positions_cache: Optional[List[Dict[str, Any]]] = None,
        orders_cache: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, float]:
        """
        Extract trading data for a symbol from cached positions and orders.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            positions_cache: Cached list of positions (from batch fetch)
            orders_cache: Cached list of orders (from batch fetch)
            
        Returns:
            Dict with current_qty, open_buy_qty, open_sell_qty
        """
        current_qty = 0.0
        open_buy_qty = 0.0
        open_sell_qty = 0.0
        
        # Extract position from cache
        if positions_cache:
            for pos in positions_cache:
                if pos.get('symbol') == symbol:
                    side = pos.get('side', '').upper()
                    quantity = self._safe_float(pos.get('quantity', 0))
                    if quantity is not None:
                        if side == 'LONG':
                            current_qty = quantity
                        elif side == 'SHORT':
                            current_qty = -quantity
                        break
        
        # Extract open orders from cache
        if orders_cache:
            for order in orders_cache:
                if order.get('symbol') == symbol and order.get('status', '').upper() == 'OPEN':
                    side = order.get('side', '').upper()
                    quantity = self._safe_float(order.get('quantity', 0))
                    if quantity is not None:
                        if side == 'BUY':
                            open_buy_qty += quantity
                        elif side == 'SELL':
                            open_sell_qty += quantity
        
        return {
            'current_qty': current_qty,
            'open_buy_qty': open_buy_qty,
            'open_sell_qty': open_sell_qty
        }
    
    def compute_snapshot(
        self,
        symbol: str,
        static_data: Dict[str, Any],
        market_data: Dict[str, Any],
        current_qty: Optional[float] = None,
        befday_qty: Optional[float] = None,
        open_buy_qty: Optional[float] = None,
        open_sell_qty: Optional[float] = None,
        positions_cache: Optional[List[Dict[str, Any]]] = None,
        orders_cache: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Compute position snapshot for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            static_data: Static data (may contain ex_div_date, dividend_amount)
            market_data: Market data (prev_close from Hammer)
            current_qty: Current position quantity (net). If None, extracted from positions_cache.
            befday_qty: Before-day position quantity (net). If None, fetched from state_store.
            open_buy_qty: Open buy orders quantity. If None, extracted from orders_cache.
            open_sell_qty: Open sell orders quantity. If None, extracted from orders_cache.
            positions_cache: Cached list of all positions (from batch fetch). Used if current_qty is None.
            orders_cache: Cached list of all orders (from batch fetch). Used if open_buy_qty/open_sell_qty is None.
            
        Returns:
            Position snapshot dict with all computed fields
        """
        try:
            # Extract trading data from cache if not provided
            if current_qty is None or open_buy_qty is None or open_sell_qty is None:
                trading_data = self._extract_trading_data_from_cache(symbol, positions_cache, orders_cache)
                if current_qty is None:
                    current_qty = trading_data['current_qty']
                if open_buy_qty is None:
                    open_buy_qty = trading_data['open_buy_qty']
                if open_sell_qty is None:
                    open_sell_qty = trading_data['open_sell_qty']
            
            # Get befday_qty from state_store if not provided
            if befday_qty is None:
                befday_qty = self.state_store.get_befday_qty(symbol)
                # If not found in store, use current_qty as fallback (first run of day)
                if befday_qty == 0.0 and current_qty != 0.0:
                    # Store current_qty as befday_qty for next time
                    self.state_store.set_befday_qty(symbol, current_qty)
                    befday_qty = current_qty
            # Get prev_close from Hammer market data
            prev_close = self._safe_float(market_data.get('prev_close'))
            
            # Calculate ex-div adjusted befday_cost
            befday_cost_raw = prev_close if prev_close is not None else None
            
            # Check if today is ex-div date
            ex_div_date = static_data.get('ex_div_date')
            dividend_amount = self._safe_float(static_data.get('dividend_amount'))
            
            befday_cost_adj = befday_cost_raw
            used_befday_cost = befday_cost_raw
            
            if ex_div_date and dividend_amount is not None and dividend_amount > 0:
                # Check if today is ex-div date
                today_str = datetime.now().strftime("%Y-%m-%d")
                ex_div_str = self._format_date(ex_div_date)
                
                if today_str == ex_div_str:
                    # Today is ex-div: adjust prev_close
                    if befday_cost_raw is not None:
                        befday_cost_adj = befday_cost_raw + dividend_amount
                        used_befday_cost = befday_cost_adj
                    logger.debug(f"Ex-div adjustment for {symbol}: {befday_cost_raw} -> {befday_cost_adj} (+{dividend_amount})")
            
            # Calculate potential qty
            potential_qty = current_qty + open_buy_qty - open_sell_qty
            
            # Determine position state
            position_state = self._determine_position_state(befday_qty, current_qty)
            
            # Get today's average cost
            todays_avg_cost = self.state_store.get_todays_avg_cost(symbol)
            
            return {
                'befday_qty': round(befday_qty, 2),
                'current_qty': round(current_qty, 2),
                'potential_qty': round(potential_qty, 2),
                'open_buy_qty': round(open_buy_qty, 2),
                'open_sell_qty': round(open_sell_qty, 2),
                'befday_cost_raw': round(befday_cost_raw, 4) if befday_cost_raw is not None else None,
                'befday_cost_adj': round(befday_cost_adj, 4) if befday_cost_adj is not None else None,
                'used_befday_cost': round(used_befday_cost, 4) if used_befday_cost is not None else None,
                'position_state': position_state,
                'todays_avg_cost_long': round(todays_avg_cost['long_avg_cost'], 4) if todays_avg_cost['long_avg_cost'] is not None else None,
                'todays_avg_cost_short': round(todays_avg_cost['short_avg_cost'], 4) if todays_avg_cost['short_avg_cost'] is not None else None,
                'ex_div_adjusted': ex_div_date is not None and dividend_amount is not None and dividend_amount > 0
            }
            
        except Exception as e:
            logger.error(f"Error computing position snapshot for {symbol}: {e}", exc_info=True)
            return {
                'befday_qty': round(befday_qty, 2),
                'current_qty': round(current_qty, 2),
                'potential_qty': round(current_qty, 2),
                'befday_cost_raw': None,
                'befday_cost_adj': None,
                'used_befday_cost': None,
                'position_state': 'NO_CHANGE',
                'todays_avg_cost_long': None,
                'todays_avg_cost_short': None,
                'ex_div_adjusted': False
            }
    
    def _determine_position_state(self, befday_qty: float, current_qty: float) -> str:
        """
        Determine position state from befday_qty vs current_qty.
        
        Args:
            befday_qty: Before-day quantity
            current_qty: Current quantity
            
        Returns:
            Position state: LONG_ADD, SHORT_ADD, LONG_REDUCE, SHORT_REDUCE, NO_CHANGE
        """
        # Net change
        net_change = current_qty - befday_qty
        
        # Threshold for "no change"
        threshold = 0.001
        
        if abs(net_change) < threshold:
            return 'NO_CHANGE'
        
        # Determine state based on direction and sign
        if befday_qty > threshold:
            # Started long
            if current_qty > befday_qty:
                return 'LONG_ADD'
            elif current_qty < threshold:
                return 'LONG_REDUCE'  # Reduced to zero or below
            else:
                return 'LONG_REDUCE'  # Reduced but still long
        elif befday_qty < -threshold:
            # Started short
            if current_qty < befday_qty:
                return 'SHORT_ADD'  # More short
            elif current_qty > -threshold:
                return 'SHORT_REDUCE'  # Reduced to zero or above
            else:
                return 'SHORT_REDUCE'  # Reduced but still short
        else:
            # Started flat
            if current_qty > threshold:
                return 'LONG_ADD'
            elif current_qty < -threshold:
                return 'SHORT_ADD'
            else:
                return 'NO_CHANGE'
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None or value == 'N/A' or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def _format_date(self, date_value: Any) -> Optional[str]:
        """Format date value to YYYY-MM-DD string"""
        if date_value is None:
            return None
        
        try:
            # Try parsing as datetime
            if isinstance(date_value, datetime):
                return date_value.strftime("%Y-%m-%d")
            
            # Try parsing as string
            date_str = str(date_value).strip()
            
            # Try common formats
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            
            # If all parsing fails, return as-is (might already be in correct format)
            return date_str
            
        except Exception as e:
            logger.warning(f"Error formatting date {date_value}: {e}")
            return None

