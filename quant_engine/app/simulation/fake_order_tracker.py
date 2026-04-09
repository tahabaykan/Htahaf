"""
Fake Order Tracker - Track simulated orders without real execution

Features:
- Track fake orders in memory
- Generate simulation order IDs
- State management (PENDING, FILLED, CANCELLED)
- Query interface

This component replaces real order execution in simulation mode.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from loguru import logger


class OrderStatus(Enum):
    """Fake order status"""
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class FakeOrder:
    """
    Fake order for simulation.
    
    Mimics real order structure but exists only in memory.
    """
    order_id: str
    symbol: str
    side: str  # BUY, SELL
    qty: int
    price: float
    tag: str
    status: str  # PENDING, FILLED, CANCELLED
    timestamp: datetime
    
    # Fill info (populated when filled)
    filled_at: Optional[datetime] = None
    fill_price: Optional[float] = None
    fill_qty: Optional[int] = None
    
    # Metadata
    cycle_id: Optional[str] = None
    engine: Optional[str] = None
    reason: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dict for JSON serialization"""
        data = asdict(self)
        # Convert datetime to ISO string
        data['timestamp'] = self.timestamp.isoformat()
        if self.filled_at:
            data['filled_at'] = self.filled_at.isoformat()
        return data


class FakeOrderTracker:
    """
    Tracks fake orders in simulation mode.
    
    Provides:
    - Order submission (fake)
    - Status queries
    - Fill simulation support
    
    Usage:
        tracker = get_fake_order_tracker()
        order_id = tracker.submit_order(
            symbol='SOJD',
            side='SELL',
            qty=500,
            price=20.50,
            tag='KARBOTU_LONG_DECREASE_STEP_2'
        )
    """
    
    def __init__(self):
        self.orders: Dict[str, FakeOrder] = {}
        self.order_counter = 0
        logger.info("[FakeOrderTracker] Initialized")
    
    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        tag: str,
        cycle_id: Optional[str] = None,
        engine: Optional[str] = None,
        reason: Optional[str] = None
    ) -> str:
        """
        Submit a fake order.
        
        Returns:
            Fake order ID (SIM_000001, etc.)
        """
        self.order_counter += 1
        order_id = f"SIM_{self.order_counter:06d}"
        
        order = FakeOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            tag=tag,
            status=OrderStatus.PENDING.value,
            timestamp=datetime.now(),
            cycle_id=cycle_id,
            engine=engine,
            reason=reason
        )
        
        self.orders[order_id] = order
        
        logger.info(
            f"[FakeOrderTracker] 🎭 FAKE ORDER: "
            f"{order_id} | {symbol} {side} {qty} @ ${price:.2f} "
            f"({tag})"
        )
        
        return order_id
    
    def get_order(self, order_id: str) -> Optional[FakeOrder]:
        """Get order by ID"""
        return self.orders.get(order_id)
    
    def get_pending_orders(self) -> List[FakeOrder]:
        """Get all pending orders"""
        return [
            o for o in self.orders.values()
            if o.status == OrderStatus.PENDING.value
        ]
    
    def get_filled_orders(self) -> List[FakeOrder]:
        """Get all filled orders"""
        return [
            o for o in self.orders.values()
            if o.status == OrderStatus.FILLED.value
        ]
    
    def get_orders_by_symbol(self, symbol: str) -> List[FakeOrder]:
        """Get all orders for a symbol"""
        return [
            o for o in self.orders.values()
            if o.symbol == symbol
        ]
    
    def get_orders_by_tag(self, tag: str) -> List[FakeOrder]:
        """Get all orders with specific tag"""
        return [
            o for o in self.orders.values()
            if o.tag == tag
        ]
    
    def fill_order(
        self,
        order_id: str,
        fill_price: float,
        fill_qty: Optional[int] = None
    ) -> bool:
        """
        Mark an order as filled.
        
        Args:
            order_id: Order to fill
            fill_price: Fill price
            fill_qty: Fill quantity (defaults to order qty)
        
        Returns:
            True if filled, False if not found or not pending
        """
        order = self.orders.get(order_id)
        
        if not order:
            logger.warning(f"[FakeOrderTracker] Order {order_id} not found")
            return False
        
        if order.status != OrderStatus.PENDING.value:
            logger.warning(
                f"[FakeOrderTracker] Order {order_id} "
                f"not pending (status: {order.status})"
            )
            return False
        
        order.status = OrderStatus.FILLED.value
        order.filled_at = datetime.now()
        order.fill_price = fill_price
        order.fill_qty = fill_qty or order.qty
        
        logger.info(
            f"[FakeOrderTracker] 📈 FILLED: "
            f"{order_id} | {order.symbol} {order.side} "
            f"{order.fill_qty} @ ${fill_price:.2f}"
        )
        
        return True
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        order = self.orders.get(order_id)
        
        if not order:
            return False
        
        if order.status != OrderStatus.PENDING.value:
            return False
        
        order.status = OrderStatus.CANCELLED.value
        logger.info(f"[FakeOrderTracker] Cancelled: {order_id}")
        
        return True
    
    def auto_fill_eligible_orders(self, market_data_cache: Dict[str, Dict]) -> List[str]:
        """
        Automatically fill pending orders that meet fill criteria.
        
        FILL LOGIC (EXACT copy from real broker):
        - LIMIT BUY: market ask <= limit price (can buy at ask)
        - LIMIT SELL: market bid >= limit price (can sell at bid)
        - MARKET BUY orders: fill immediately at current ask
        - MARKET SELL orders: fill immediately at current bid
        
        Args:
            market_data_cache: Market data cache with bid/ask for each symbol
            
        Returns:
            List of filled order IDs
        """
        filled_ids = []
        pending = self.get_pending_orders()
        
        if not pending:
            return filled_ids
        
        for order in pending:
            # Get market data for this symbol
            market_data = market_data_cache.get(order.symbol, {})
            if not market_data:
                continue
            
            bid = market_data.get('bid')
            ask = market_data.get('ask')
            
            if bid is None or ask is None or bid <= 0 or ask <= 0:
                continue
            
            fill_price = None
            should_fill = False
            
            # MARKET ORDERS: Fill immediately
            if order.price == 0 or order.price is None:
                should_fill = True
                if order.side == 'BUY':
                    fill_price = ask  # Buy at ask
                elif order.side == 'SELL':
                    fill_price = bid  # Sell at bid
                else:
                    continue
            
            # LIMIT ORDERS: Check if price crossed
            else:
                if order.side == 'BUY':
                    # Can buy if ask <= limit price
                    if ask <= order.price:
                        should_fill = True
                        fill_price = ask
                elif order.side == 'SELL':
                    # Can sell if bid >= limit price
                    if bid >= order.price:
                        should_fill = True
                        fill_price = bid
            
            # Fill the order
            if should_fill and fill_price:
                success = self.fill_order(order.order_id, fill_price, order.qty)
                if success:
                    filled_ids.append(order.order_id)
                    logger.info(
                        f"[AUTO_FILL] ✅ {order.order_id} | {order.symbol} {order.side} "
                        f"{order.qty} @ ${fill_price:.2f} "
                        f"(bid={bid:.2f}, ask={ask:.2f}, limit={order.price:.2f if order.price else 'MARKET'})"
                    )
        
        if filled_ids:
            logger.info(f"[AUTO_FILL] Filled {len(filled_ids)} orders: {filled_ids}")
        
        return filled_ids
    
    def get_stats(self) -> Dict:
        """Get order statistics"""
        return {
            'total_orders': len(self.orders),
            'pending': len(self.get_pending_orders()),
            'filled': len(self.get_filled_orders()),
            'cancelled': len([
                o for o in self.orders.values()
                if o.status == OrderStatus.CANCELLED.value
            ])
        }
    
    def reset(self):
        """Reset all orders (for new simulation)"""
        self.orders.clear()
        self.order_counter = 0
        logger.info("[FakeOrderTracker] Reset - all orders cleared")


# Global instance
_fake_order_tracker: Optional[FakeOrderTracker] = None


def get_fake_order_tracker() -> FakeOrderTracker:
    """Get global fake order tracker"""
    global _fake_order_tracker
    if _fake_order_tracker is None:
        _fake_order_tracker = FakeOrderTracker()
    return _fake_order_tracker


def reset_fake_order_tracker():
    """Reset tracker (for new simulation)"""
    tracker = get_fake_order_tracker()
    tracker.reset()
    return tracker
