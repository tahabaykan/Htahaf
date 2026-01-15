"""app/execution/execution_simulator.py

Execution simulator - realistic order fill simulation with slippage, commission, and liquidity.
"""

import time
import uuid
from typing import Dict, Any, Optional
from dataclasses import dataclass

from app.core.logger import logger
from app.execution.commission import CommissionModel
from app.execution.liquidity import LiquidityModel


@dataclass
class FillReport:
    """Fill report for an order"""
    filled_qty: float
    avg_fill_price: float
    remaining_qty: float
    timestamp: float
    slippage: float = 0.0
    commission: float = 0.0
    liquidity_constrained: bool = False
    effective_price: float = 0.0


class ExecutionSimulator:
    """
    Execution simulator for realistic order fills.
    
    Features:
    - Market order simulation with slippage
    - Limit order simulation with partial fills
    - Spread-based slippage
    - Impact slippage
    - Liquidity constraints
    - Commission calculation
    """
    
    def __init__(
        self,
        commission_model: Optional[CommissionModel] = None,
        liquidity_model: Optional[LiquidityModel] = None,
        volatility_adjustment: bool = True
    ):
        """
        Initialize execution simulator.
        
        Args:
            commission_model: Commission model instance
            liquidity_model: Liquidity model instance
            volatility_adjustment: Whether to apply volatility-based slippage adjustment
        """
        self.commission_model = commission_model or CommissionModel.ibkr_stock()
        self.liquidity_model = liquidity_model or LiquidityModel()
        self.volatility_adjustment = volatility_adjustment
        
        # Track pending limit orders
        self.pending_orders: Dict[str, Dict[str, Any]] = {}
    
    def simulate_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        tick: Dict[str, Any],
        order_id: Optional[str] = None
    ) -> FillReport:
        """
        Simulate market order fill.
        
        Args:
            symbol: Stock symbol
            qty: Order quantity (positive for BUY, negative for SELL)
            side: BUY or SELL
            tick: Current tick data
            order_id: Optional order ID
            
        Returns:
            FillReport with fill details
        """
        order_id = order_id or str(uuid.uuid4())
        timestamp = float(tick.get('ts', time.time() * 1000)) / 1000.0
        
        # Get market prices
        bid = float(tick.get('bid', 0))
        ask = float(tick.get('ask', 0))
        last = float(tick.get('last', 0))
        
        if bid <= 0 or ask <= 0:
            logger.warning(f"Invalid prices for {symbol}: bid={bid}, ask={ask}")
            return FillReport(
                filled_qty=0,
                avg_fill_price=last,
                remaining_qty=abs(qty),
                timestamp=timestamp,
                slippage=0.0,
                commission=0.0
            )
        
        # Calculate mid price
        mid = (bid + ask) / 2.0
        
        # Get liquidity constraint
        max_fill_qty = self.liquidity_model.get_max_fill_qty(symbol, tick)
        requested_qty = abs(qty)
        
        # Determine actual fill quantity (may be partial)
        filled_qty = min(requested_qty, max_fill_qty)
        liquidity_constrained = filled_qty < requested_qty
        
        # Calculate slippage
        spread_slippage = self.liquidity_model.compute_spread_slippage(tick)
        impact_slippage = self.liquidity_model.compute_impact_slippage(symbol, filled_qty)
        
        # Total slippage
        total_slippage = spread_slippage + impact_slippage
        
        # Volatility adjustment (optional)
        if self.volatility_adjustment:
            # Simple volatility estimate from spread
            volatility = spread_slippage * 2  # Rough estimate
            total_slippage += volatility * 0.1  # Add 10% of volatility
        
        # Calculate fill price
        if side.upper() == "BUY":
            # Buy at ask + slippage
            fill_price = ask * (1 + total_slippage)
        else:
            # Sell at bid - slippage
            fill_price = bid * (1 - total_slippage)
        
        # Ensure fill price is reasonable
        fill_price = max(bid, min(ask, fill_price))
        
        # Calculate commission
        commission = self.commission_model.calculate(
            symbol=symbol,
            qty=filled_qty,
            price=fill_price,
            side=side,
            order_type="MARKET"
        )
        
        # Effective price (including slippage and commission per share)
        effective_price = fill_price
        if filled_qty > 0:
            commission_per_share = commission / filled_qty
            effective_price = fill_price + commission_per_share
        
        return FillReport(
            filled_qty=filled_qty,
            avg_fill_price=fill_price,
            remaining_qty=requested_qty - filled_qty,
            timestamp=timestamp,
            slippage=total_slippage,
            commission=commission,
            liquidity_constrained=liquidity_constrained,
            effective_price=effective_price
        )
    
    def simulate_limit_order(
        self,
        symbol: str,
        qty: float,
        limit_price: float,
        side: str,
        tick: Dict[str, Any],
        order_id: Optional[str] = None
    ) -> FillReport:
        """
        Simulate limit order fill.
        
        Args:
            symbol: Stock symbol
            qty: Order quantity
            limit_price: Limit price
            side: BUY or SELL
            tick: Current tick data
            order_id: Optional order ID
            
        Returns:
            FillReport with fill details
        """
        order_id = order_id or str(uuid.uuid4())
        timestamp = float(tick.get('ts', time.time() * 1000)) / 1000.0
        
        # Get market prices
        bid = float(tick.get('bid', 0))
        ask = float(tick.get('ask', 0))
        last = float(tick.get('last', 0))
        
        if bid <= 0 or ask <= 0:
            return FillReport(
                filled_qty=0,
                avg_fill_price=limit_price,
                remaining_qty=abs(qty),
                timestamp=timestamp,
                slippage=0.0,
                commission=0.0
            )
        
        # Check if limit order can be filled
        can_fill = False
        
        if side.upper() == "BUY":
            # BUY limit: price must be >= ask or >= last
            can_fill = limit_price >= ask or limit_price >= last
        else:
            # SELL limit: price must be <= bid or <= last
            can_fill = limit_price <= bid or limit_price <= last
        
        if not can_fill:
            # Order cannot be filled yet - add to pending
            self.pending_orders[order_id] = {
                'symbol': symbol,
                'qty': qty,
                'limit_price': limit_price,
                'side': side,
                'timestamp': timestamp
            }
            return FillReport(
                filled_qty=0,
                avg_fill_price=limit_price,
                remaining_qty=abs(qty),
                timestamp=timestamp,
                slippage=0.0,
                commission=0.0
            )
        
        # Order can be filled - calculate fill
        requested_qty = abs(qty)
        
        # Get liquidity constraint
        max_fill_qty = self.liquidity_model.get_max_fill_qty(symbol, tick)
        filled_qty = min(requested_qty, max_fill_qty)
        liquidity_constrained = filled_qty < requested_qty
        
        # Fill price: touch-and-fill (limit price or better)
        if side.upper() == "BUY":
            fill_price = min(limit_price, ask)
        else:
            fill_price = max(limit_price, bid)
        
        # Limit orders may have slight slippage (queue position)
        spread_slippage = self.liquidity_model.compute_spread_slippage(tick)
        # Limit orders get 50% of spread slippage (better than market)
        slippage = spread_slippage * 0.5
        
        # Apply slippage
        if side.upper() == "BUY":
            fill_price = fill_price * (1 + slippage)
        else:
            fill_price = fill_price * (1 - slippage)
        
        # Ensure fill price respects limit
        if side.upper() == "BUY":
            fill_price = min(fill_price, limit_price)
        else:
            fill_price = max(fill_price, limit_price)
        
        # Calculate commission
        commission = self.commission_model.calculate(
            symbol=symbol,
            qty=filled_qty,
            price=fill_price,
            side=side,
            order_type="LIMIT"
        )
        
        # Effective price
        effective_price = fill_price
        if filled_qty > 0:
            commission_per_share = commission / filled_qty
            effective_price = fill_price + commission_per_share
        
        # Remove from pending if fully filled
        if filled_qty >= requested_qty and order_id in self.pending_orders:
            del self.pending_orders[order_id]
        
        return FillReport(
            filled_qty=filled_qty,
            avg_fill_price=fill_price,
            remaining_qty=requested_qty - filled_qty,
            timestamp=timestamp,
            slippage=slippage,
            commission=commission,
            liquidity_constrained=liquidity_constrained,
            effective_price=effective_price
        )
    
    def process_tick(self, tick: Dict[str, Any]) -> list:
        """
        Process tick and try to fill pending limit orders.
        
        Args:
            tick: Current tick data
            
        Returns:
            List of FillReport for filled orders
        """
        symbol = tick.get('symbol')
        if not symbol:
            return []
        
        fills = []
        
        # Check pending orders for this symbol
        for order_id, order in list(self.pending_orders.items()):
            if order['symbol'] != symbol:
                continue
            
            # Try to fill limit order
            fill = self.simulate_limit_order(
                symbol=order['symbol'],
                qty=order['qty'],
                limit_price=order['limit_price'],
                side=order['side'],
                tick=tick,
                order_id=order_id
            )
            
            if fill.filled_qty > 0:
                fills.append(fill)
        
        return fills
    
    def get_pending_orders(self) -> Dict[str, Dict[str, Any]]:
        """Get all pending orders"""
        return self.pending_orders.copy()








