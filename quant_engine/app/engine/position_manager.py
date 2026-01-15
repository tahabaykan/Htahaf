"""app/engine/position_manager.py

Position manager - tracks current positions, P&L, and exposure.
"""

import time
from typing import Dict, List, Optional, Any
from collections import defaultdict

from app.core.logger import logger


class PositionManager:
    """Manages trading positions"""
    
    def __init__(self):
        # Position data: symbol -> position info
        self.positions: Dict[str, Dict] = {}
        
        # FIFO tracking (for realized P&L)
        self.fifo_queue: Dict[str, List[Dict]] = defaultdict(list)
    
    def update_position(self, symbol: str, quantity: float, price: float, book: str = "LT"):
        """
        Update position from execution, respecting LT/MM buckets.
        
        Args:
            symbol: Stock symbol
            quantity: Position change (positive = long, negative = short)
            price: Execution price
            book: 'LT' or 'MM' (default 'LT')
        """
        try:
            # 1. Get current position state
            current = self.positions.get(symbol, {
                'qty': 0.0,
                'avg_price': 0.0,
                # Buckets
                'lt_qty': 0.0,
                'lt_avg_price': 0.0,
                'mm_qty': 0.0,
                'mm_avg_price': 0.0,
                # P&L
                'realized_pnl': 0.0,
                'unrealized_pnl': 0.0,
                'last_update_time': time.time()
            })
            
            # 2. Update Specific Bucket
            bucket_prefix = book.lower() # 'lt' or 'mm'
            old_bucket_qty = current.get(f'{bucket_prefix}_qty', 0.0)
            old_bucket_avg = current.get(f'{bucket_prefix}_avg_price', 0.0)
            
            new_bucket_qty = old_bucket_qty + quantity
            
            # Calculate new bucket average
            if old_bucket_qty == 0:
                new_bucket_avg = price
            elif (old_bucket_qty > 0 and quantity > 0) or (old_bucket_qty < 0 and quantity < 0):
                # Adding
                total_cost = (old_bucket_qty * old_bucket_avg) + (quantity * price)
                new_bucket_avg = total_cost / new_bucket_qty if new_bucket_qty != 0 else price
            else:
                # Reducing - simplified FIFO (bucket level)
                # For basic P&L, assumes reducing keeps same avg price for remaining
                new_bucket_avg = old_bucket_avg
            
            # Update bucket values in state
            current[f'{bucket_prefix}_qty'] = new_bucket_qty
            current[f'{bucket_prefix}_avg_price'] = new_bucket_avg
            
            # 3. Aggregation (Net Position)
            current['lt_qty'] = current.get('lt_qty', 0.0)
            current['mm_qty'] = current.get('mm_qty', 0.0)
            current['qty'] = current['lt_qty'] + current['mm_qty']
            
            # Aggregate Average (Weighted)
            total_cost = (current['lt_qty'] * current.get('lt_avg_price', 0)) + \
                         (current['mm_qty'] * current.get('mm_avg_price', 0))
                         
            current['avg_price'] = total_cost / current['qty'] if current['qty'] != 0 else 0.0
            
            # 4. FIFO & Realized P&L (Per Bucket Logic Simplified)
            # Use bucket-specific FIFO key
            self._update_fifo_queue(f"{symbol}_{book}", quantity, price)
            
            # Calculate realized P&L (Bucket specific contribution)
            # Note: This uses logic similar to before but scoped to bucket queue
            bucket_pnl = self._calculate_realized_pnl_from_fifo(f"{symbol}_{book}", quantity, price, old_bucket_qty)
            
            current['realized_pnl'] += bucket_pnl
            current['last_update_time'] = time.time()
            
            # Save back
            self.positions[symbol] = current
            
            # Debug log
            logger.debug(
                f"Position updated ({book})",
                extra={
                    "symbol": symbol,
                    "book": book,
                    "qty_change": quantity,
                    "price": price,
                    "new_net_qty": current['qty'],
                    "new_lt_qty": current['lt_qty'],
                    "new_mm_qty": current['mm_qty']
                }
            )
            
        except Exception as e:
            logger.error(f"Error updating position: {e}", exc_info=True)

    def _calculate_fifo_avg(self, symbol: str, quantity: float, price: float, old_qty: float, old_avg: float) -> float:
        # Kept for compatibility if used elsewhere, but logic moved inline for buckets
        if abs(old_qty) <= abs(quantity):
             return price
        if (old_qty > 0 and quantity < 0 and old_qty + quantity < 0) or \
           (old_qty < 0 and quantity > 0 and old_qty + quantity > 0):
             return price
        return old_avg
    
    def _update_fifo_queue(self, queue_key: str, quantity: float, price: float):
        """Update FIFO queue (queue_key includes bucket suffix)."""
        queue = self.fifo_queue[queue_key]
        if quantity > 0:
            queue.append({'qty': quantity, 'price': price})
        else:
            remaining = abs(quantity)
            while remaining > 0 and queue:
                oldest = queue[0]
                if oldest['qty'] <= remaining:
                    remaining -= oldest['qty']
                    queue.pop(0)
                else:
                    oldest['qty'] -= remaining
                    remaining = 0
    
    def _calculate_realized_pnl_from_fifo(self, queue_key: str, quantity: float, price: float, old_qty: float) -> float:
        """Calculate realized P&L from FIFO queue."""
        if quantity >= 0: return 0.0
        # Simplified placeholder for P&L calc logic (requires full matched trade tracking)
        # Using old_qty isn't enough for exact P&L without matching against queue prices.
        # For now return 0 to match previous behavior, can be enhanced later.
        return 0.0

    def apply_execution(self, exec_msg: Dict[str, Any]):
        """
        Apply execution message to position.
        """
        try:
            symbol = exec_msg.get("symbol")
            qty = float(exec_msg.get("qty", 0))
            price = float(exec_msg.get("price", 0))
            side = exec_msg.get("side", "BUY").upper()
            
            # Extract book if present (default LT)
            book = exec_msg.get("book", "LT")
            
            if side == "BUY":
                quantity = qty
            elif side == "SELL":
                quantity = -qty
            else:
                return
            
            self.update_position(symbol, quantity, price, book=book)
            
        except Exception as e:
            logger.error(f"Error applying execution: {e}", exc_info=True)

    
    def calculate_realized_pnl(self, symbol: Optional[str] = None) -> float:
        """
        Calculate realized P&L.
        
        Args:
            symbol: Symbol to calculate for (None = all symbols)
            
        Returns:
            Total realized P&L
        """
        # For now, return 0 (FIFO-based calculation would go here)
        # In production, this would track closed positions and calculate P&L
        return 0.0
    
    def calculate_unrealized_pnl(self, symbol: Optional[str] = None, market_prices: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate unrealized P&L.
        
        Args:
            symbol: Symbol to calculate for (None = all symbols)
            market_prices: Dict of {symbol: market_price}
            
        Returns:
            Total unrealized P&L
        """
        if market_prices is None:
            market_prices = {}
        
        total_pnl = 0.0
        
        if symbol:
            # Calculate for single symbol
            pos = self.positions.get(symbol)
            if pos and pos['qty'] != 0:
                market_price = market_prices.get(symbol, pos['avg_price'])
                pnl = (market_price - pos['avg_price']) * pos['qty']
                self.positions[symbol]['unrealized_pnl'] = pnl
                total_pnl = pnl
        else:
            # Calculate for all symbols
            for sym, pos in self.positions.items():
                if pos['qty'] != 0:
                    market_price = market_prices.get(sym, pos['avg_price'])
                    pnl = (market_price - pos['avg_price']) * pos['qty']
                    self.positions[sym]['unrealized_pnl'] = pnl
                    total_pnl += pnl
        
        return total_pnl
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """
        Get position for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Position dict or None
        """
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, Dict]:
        """
        Get all positions.
        
        Returns:
            Dict of {symbol: position_dict}
        """
        return dict(self.positions)
    
    def get_positions_summary(self) -> List[Dict]:
        """
        Get positions summary list.
        
        Returns:
            List of position dicts
        """
        return [
            {
                'symbol': symbol,
                **position
            }
            for symbol, position in self.positions.items()
            if position['qty'] != 0
        ]
