"""app/backtest/execution_simulator.py

Historical Execution Simulator - realistic order fill model for backtesting.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, List, Dict


@dataclass
class PendingOrder:
    """Pending order in the queue"""
    order_id: str
    symbol: str
    side: str
    qty: float
    price: Optional[float]  # None for market orders
    remaining: float
    timestamp: float
    type: str  # "MARKET" or "LIMIT"
    status: str = "OPEN"
    fills: List[dict] = field(default_factory=list)


class ExecutionSimulator:
    """
    Execution simulator for backtesting.
    
    Features:
    - Market order immediate fill
    - Limit order touch-and-fill
    - Partial fills
    - Slippage simulation
    - Spread-aware pricing
    - Commission calculation
    - Order/fill latency simulation
    - Pending order queue
    """
    
    def __init__(
        self,
        slippage: float = 0.0,
        commission_per_share: float = 0.0,
        commission_min: float = 0.0,
        order_latency_ms: int = 0,
        fill_latency_ms: int = 0,
    ):
        """
        Initialize execution simulator.
        
        Args:
            slippage: Slippage in price units (e.g., 0.01 = $0.01 per share)
            commission_per_share: Commission per share
            commission_min: Minimum commission
            order_latency_ms: Order processing latency in milliseconds
            fill_latency_ms: Fill processing latency in milliseconds
        """
        self.slippage = slippage
        self.commission_per_share = commission_per_share
        self.commission_min = commission_min
        self.order_latency_ms = order_latency_ms
        self.fill_latency_ms = fill_latency_ms
        
        self.pending_orders: Dict[str, List[PendingOrder]] = {}
    
    # ------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------
    def process_new_order(self, order: dict) -> str:
        """
        Process new order from strategy.
        
        Args:
            order: Order dict with keys: symbol, side, qty, limit_price (optional)
            
        Returns:
            Order ID
        """
        order_id = str(uuid.uuid4())
        pend = PendingOrder(
            order_id=order_id,
            symbol=order["symbol"],
            side=order["side"].upper(),
            qty=order["qty"],
            remaining=order["qty"],
            price=order.get("limit_price"),
            timestamp=time.time(),
            type="LIMIT" if order.get("limit_price") else "MARKET",
        )
        
        if pend.symbol not in self.pending_orders:
            self.pending_orders[pend.symbol] = []
        
        self.pending_orders[pend.symbol].append(pend)
        
        # Order latency
        if self.order_latency_ms > 0:
            time.sleep(self.order_latency_ms / 1000.0)
        
        return pend.order_id
    
    # ------------------------------------------------------------
    # Called on every tick: try to fill eligible orders
    # ------------------------------------------------------------
    def process_tick(self, tick: dict) -> List[dict]:
        """
        Process tick and try to fill eligible orders.
        
        Args:
            tick: Tick dict with keys: symbol, last, bid, ask, volume, timestamp
            
        Returns:
            List of execution (fill) dicts
        """
        symbol = tick["symbol"]
        if symbol not in self.pending_orders:
            return []
        
        fills = []
        
        # Make a copy to avoid modification during iteration
        for pend in list(self.pending_orders[symbol]):
            if pend.status != "OPEN":
                continue
            
            if pend.type == "MARKET":
                execs = self._fill_market_order(pend, tick)
            else:
                execs = self._fill_limit_order(pend, tick)
            
            for e in execs:
                fills.append(e)
                pend.fills.append(e)
                pend.remaining -= e["fill_qty"]
            
            # If fully filled
            if pend.remaining <= 0:
                pend.status = "FILLED"
                self.pending_orders[symbol].remove(pend)
        
        return fills
    
    # ------------------------------------------------------------
    # MARKET ORDER
    # ------------------------------------------------------------
    def _fill_market_order(self, pend: PendingOrder, tick: dict) -> List[dict]:
        """Fill market order immediately"""
        fill_price = (
            float(tick["ask"]) + self.slippage if pend.side == "BUY" else float(tick["bid"]) - self.slippage
        )
        
        fill_qty = pend.remaining
        
        commission = self.apply_commission(fill_qty)
        
        # Fill latency
        if self.fill_latency_ms > 0:
            time.sleep(self.fill_latency_ms / 1000.0)
        
        return [
            {
                "order_id": pend.order_id,
                "exec_id": str(uuid.uuid4()),
                "symbol": pend.symbol,
                "side": pend.side,
                "fill_qty": fill_qty,
                "fill_price": fill_price,
                "commission": commission,
                "timestamp": tick.get("ts", tick.get("timestamp", int(time.time() * 1000))),
                "slippage": self.slippage,
                "remaining": 0,
            }
        ]
    
    # ------------------------------------------------------------
    # LIMIT ORDER
    # ------------------------------------------------------------
    def _fill_limit_order(self, pend: PendingOrder, tick: dict) -> List[dict]:
        """Fill limit order if price touches limit"""
        last = float(tick["last"])
        bid = float(tick.get("bid", last))
        ask = float(tick.get("ask", last))
        vol = float(tick.get("volume", pend.remaining))
        
        # BUY LIMIT → price must be >= last or ask
        if pend.side == "BUY":
            can_fill = (pend.price >= last) or (pend.price >= ask)
        else:
            # SELL LIMIT → price must be <= last or <= bid
            can_fill = (pend.price <= last) or (pend.price <= bid)
        
        if not can_fill:
            return []
        
        # Partial fill (limited by volume)
        fill_qty = min(vol, pend.remaining)
        
        if fill_qty <= 0:
            return []
        
        # Fill price (touch-and-fill)
        if pend.side == "BUY":
            fill_price = min(pend.price, ask) + self.slippage
        else:
            fill_price = max(pend.price, bid) - self.slippage
        
        commission = self.apply_commission(fill_qty)
        
        if self.fill_latency_ms > 0:
            time.sleep(self.fill_latency_ms / 1000.0)
        
        return [
            {
                "order_id": pend.order_id,
                "exec_id": str(uuid.uuid4()),
                "symbol": pend.symbol,
                "side": pend.side,
                "fill_qty": fill_qty,
                "fill_price": fill_price,
                "commission": commission,
                "timestamp": tick.get("ts", tick.get("timestamp", int(time.time() * 1000))),
                "slippage": self.slippage,
                "remaining": pend.remaining - fill_qty,
            }
        ]
    
    # ------------------------------------------------------------
    # Commission Model
    # ------------------------------------------------------------
    def apply_commission(self, qty: float) -> float:
        """Calculate commission"""
        c = qty * self.commission_per_share
        return max(c, self.commission_min)
    
    def get_pending_orders(self, symbol: Optional[str] = None) -> List[PendingOrder]:
        """Get pending orders (all symbols or specific symbol)"""
        if symbol:
            return self.pending_orders.get(symbol, [])
        else:
            all_orders = []
            for orders in self.pending_orders.values():
                all_orders.extend(orders)
            return all_orders
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order"""
        for symbol, orders in self.pending_orders.items():
            for order in orders:
                if order.order_id == order_id:
                    order.status = "CANCELLED"
                    self.pending_orders[symbol].remove(order)
                    return True
        return False








