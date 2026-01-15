"""
Intraday Position Tracker

Tracks intraday positions opened today and calculates realized PnL
only when intraday-opened inventory is closed within the same day.
"""

from datetime import date
from typing import Dict, Any, Optional, Tuple
from collections import defaultdict
from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.event_driven.state.store import StateStore
from app.event_driven.state.store import StateStore


class IntradayTracker:
    """Tracks intraday positions and calculates realized PnL"""
    
    def __init__(self):
        redis_client = get_redis_client().sync
        if not redis_client:
            raise RuntimeError("Redis client not available")
        
        self.state_store = StateStore(redis_client=redis_client)
        self.tracker_key_prefix = "intraday:positions"
    
    def get_tracker_key(self, account_id: str, symbol: str, target_date: Optional[date] = None) -> str:
        """Get Redis key for intraday position tracker"""
        if target_date is None:
            target_date = date.today()
        date_str = target_date.isoformat()
        return f"{self.tracker_key_prefix}:{date_str}:{account_id}:{symbol}"
    
    def get_intraday_position(self, account_id: str, symbol: str, target_date: Optional[date] = None) -> Dict[str, Any]:
        """Get current intraday position state"""
        key = self.get_tracker_key(account_id, symbol, target_date)
        position = self.state_store.get_state(key)
        
        if not position:
            return {
                "intraday_qty": 0,  # Net intraday quantity (can be positive or negative)
                "intraday_avg_fill_price": 0.0,  # Weighted average of today's fills
                "intraday_long_qty": 0,  # Long positions opened today
                "intraday_long_avg_price": 0.0,
                "intraday_short_qty": 0,  # Short positions opened today
                "intraday_short_avg_price": 0.0,
                "realized_pnl": 0.0,  # Cumulative realized PnL from closing intraday positions
            }
        
        return position
    
    def update_intraday_position(
        self,
        account_id: str,
        symbol: str,
        fill_qty: int,
        fill_price: float,
        action: str,  # "BUY" or "SELL"
        target_date: Optional[date] = None
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Update intraday position and calculate realized PnL
        
        Returns:
            (realized_pnl, updated_position_state)
        """
        key = self.get_tracker_key(account_id, symbol, target_date)
        position = self.get_intraday_position(account_id, symbol, target_date)
        
        realized_pnl = 0.0
        
        if action == "BUY":
            # Buying: increase long or close short
            if position["intraday_short_qty"] > 0:
                # Closing intraday short: recognize realized PnL
                close_qty = min(position["intraday_short_qty"], fill_qty)
                realized_pnl = (position["intraday_short_avg_price"] - fill_price) * close_qty
                
                # Update short position
                position["intraday_short_qty"] -= close_qty
                if position["intraday_short_qty"] == 0:
                    position["intraday_short_avg_price"] = 0.0
                
                # Remaining qty opens new long
                remaining_qty = fill_qty - close_qty
                if remaining_qty > 0:
                    # Opening new long position
                    if position["intraday_long_qty"] == 0:
                        position["intraday_long_qty"] = remaining_qty
                        position["intraday_long_avg_price"] = fill_price
                    else:
                        # Add to existing long (weighted average)
                        total_cost = (position["intraday_long_qty"] * position["intraday_long_avg_price"] +
                                    remaining_qty * fill_price)
                        position["intraday_long_qty"] += remaining_qty
                        position["intraday_long_avg_price"] = total_cost / position["intraday_long_qty"]
            else:
                # Opening new long or adding to existing long
                if position["intraday_long_qty"] == 0:
                    position["intraday_long_qty"] = fill_qty
                    position["intraday_long_avg_price"] = fill_price
                else:
                    # Add to existing long (weighted average)
                    total_cost = (position["intraday_long_qty"] * position["intraday_long_avg_price"] +
                                fill_qty * fill_price)
                    position["intraday_long_qty"] += fill_qty
                    position["intraday_long_avg_price"] = total_cost / position["intraday_long_qty"]
            
            position["intraday_qty"] += fill_qty
        
        else:  # SELL
            # Selling: increase short or close long
            if position["intraday_long_qty"] > 0:
                # Closing intraday long: recognize realized PnL
                close_qty = min(position["intraday_long_qty"], fill_qty)
                realized_pnl = (fill_price - position["intraday_long_avg_price"]) * close_qty
                
                # Update long position
                position["intraday_long_qty"] -= close_qty
                if position["intraday_long_qty"] == 0:
                    position["intraday_long_avg_price"] = 0.0
                
                # Remaining qty opens new short
                remaining_qty = fill_qty - close_qty
                if remaining_qty > 0:
                    # Opening new short position
                    if position["intraday_short_qty"] == 0:
                        position["intraday_short_qty"] = remaining_qty
                        position["intraday_short_avg_price"] = fill_price
                    else:
                        # Add to existing short (weighted average)
                        total_cost = (position["intraday_short_qty"] * position["intraday_short_avg_price"] +
                                    remaining_qty * fill_price)
                        position["intraday_short_qty"] += remaining_qty
                        position["intraday_short_avg_price"] = total_cost / position["intraday_short_qty"]
            else:
                # Opening new short or adding to existing short
                if position["intraday_short_qty"] == 0:
                    position["intraday_short_qty"] = fill_qty
                    position["intraday_short_avg_price"] = fill_price
                else:
                    # Add to existing short (weighted average)
                    total_cost = (position["intraday_short_qty"] * position["intraday_short_avg_price"] +
                                fill_qty * fill_price)
                    position["intraday_short_qty"] += fill_qty
                    position["intraday_short_avg_price"] = total_cost / position["intraday_short_qty"]
            
            position["intraday_qty"] -= fill_qty
        
        # Calculate overall intraday_avg_fill_price (weighted average of all fills)
        total_notional = 0.0
        total_qty = 0
        
        if position["intraday_long_qty"] > 0:
            total_notional += position["intraday_long_qty"] * position["intraday_long_avg_price"]
            total_qty += position["intraday_long_qty"]
        
        if position["intraday_short_qty"] > 0:
            total_notional += position["intraday_short_qty"] * position["intraday_short_avg_price"]
            total_qty += position["intraday_short_qty"]
        
        if total_qty > 0:
            position["intraday_avg_fill_price"] = total_notional / total_qty
        else:
            position["intraday_avg_fill_price"] = 0.0
        
        # Update cumulative realized PnL
        position["realized_pnl"] += realized_pnl
        
        # Persist to Redis
        self.state_store.set_state(key, position)
        
        return realized_pnl, position

