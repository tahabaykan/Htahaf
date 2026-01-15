"""tests/utils/fake_execution_factory.py

Factory for creating fake test data: ticks, orders, executions, positions.
"""

import time
import random
from typing import Dict, Any, List, Optional


class FakeExecutionFactory:
    """Factory for creating fake test data"""
    
    @staticmethod
    def create_tick(
        symbol: str = "AAPL",
        price: Optional[float] = None,
        volume: Optional[int] = None,
        timestamp: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Create fake tick data.
        
        Args:
            symbol: Stock symbol
            price: Price (default: random 100-200)
            volume: Volume (default: random 1000-10000)
            timestamp: Timestamp in ms (default: current time)
            
        Returns:
            Tick dict
        """
        if price is None:
            price = round(100 + random.random() * 100, 2)
        
        if volume is None:
            volume = random.randint(1000, 10000)
        
        if timestamp is None:
            timestamp = int(time.time() * 1000)
        
        return {
            "symbol": symbol,
            "last": str(price),
            "bid": str(round(price - 0.01, 2)),
            "ask": str(round(price + 0.01, 2)),
            "volume": volume,
            "ts": timestamp
        }
    
    @staticmethod
    def create_ticks(
        symbol: str,
        count: int,
        start_price: float = 100.0,
        price_variance: float = 5.0,
        delay_ms: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Create multiple ticks with price progression.
        
        Args:
            symbol: Stock symbol
            count: Number of ticks
            start_price: Starting price
            price_variance: Max price change per tick
            delay_ms: Delay between ticks (ms)
            
        Returns:
            List of tick dicts
        """
        ticks = []
        current_price = start_price
        base_time = int(time.time() * 1000)
        
        for i in range(count):
            # Random walk price
            change = (random.random() - 0.5) * 2 * price_variance
            current_price = max(1.0, current_price + change)
            
            tick = FakeExecutionFactory.create_tick(
                symbol=symbol,
                price=round(current_price, 2),
                timestamp=base_time + (i * delay_ms)
            )
            ticks.append(tick)
        
        return ticks
    
    @staticmethod
    def create_order(
        symbol: str = "AAPL",
        side: str = "BUY",
        qty: float = 10.0,
        order_type: str = "MKT",
        limit_price: Optional[float] = None,
        timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create fake order message.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            qty: Quantity
            order_type: MKT or LMT
            limit_price: Limit price (for LMT orders)
            timestamp: Timestamp in ms
            
        Returns:
            Order dict
        """
        if timestamp is None:
            timestamp = int(time.time() * 1000)
        
        order = {
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "order_type": order_type,
            "timestamp": timestamp
        }
        
        if order_type == "LMT" and limit_price:
            order["limit_price"] = str(limit_price)
        
        return order
    
    @staticmethod
    def create_execution(
        symbol: str = "AAPL",
        side: str = "BUY",
        qty: float = 10.0,
        price: float = 150.0,
        order_id: Optional[int] = None,
        exec_id: Optional[str] = None,
        timestamp: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create fake execution message.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            qty: Execution quantity
            price: Execution price
            order_id: Order ID
            exec_id: Execution ID
            timestamp: Timestamp in ms
            
        Returns:
            Execution dict
        """
        if timestamp is None:
            timestamp = int(time.time() * 1000)
        
        if order_id is None:
            order_id = random.randint(1000, 9999)
        
        if exec_id is None:
            exec_id = f"EXEC_{order_id}_{timestamp}"
        
        return {
            "symbol": symbol,
            "side": side,
            "fill_qty": str(qty),
            "fill_price": str(price),
            "order_id": str(order_id),
            "exec_id": exec_id,
            "timestamp": timestamp,
            # Legacy fields
            "qty": str(qty),
            "price": str(price)
        }
    
    @staticmethod
    def create_position(
        symbol: str = "AAPL",
        qty: float = 10.0,
        avg_price: float = 150.0,
        realized_pnl: float = 0.0,
        unrealized_pnl: float = 0.0
    ) -> Dict[str, Any]:
        """
        Create fake position data.
        
        Args:
            symbol: Stock symbol
            qty: Position quantity
            avg_price: Average price
            realized_pnl: Realized P&L
            unrealized_pnl: Unrealized P&L
            
        Returns:
            Position dict
        """
        return {
            "symbol": symbol,
            "qty": qty,
            "avg_price": avg_price,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "last_update_time": time.time()
        }
    
    @staticmethod
    def create_signal(
        symbol: str = "AAPL",
        signal: str = "BUY",
        price: float = 150.0,
        quantity: float = 10.0,
        order_type: str = "MKT",
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create fake strategy signal.
        
        Args:
            symbol: Stock symbol
            signal: BUY or SELL
            price: Signal price
            quantity: Order quantity
            order_type: MKT or LMT
            reason: Signal reason
            
        Returns:
            Signal dict
        """
        signal_dict = {
            "symbol": symbol,
            "signal": signal,
            "price": price,
            "quantity": quantity,
            "order_type": order_type
        }
        
        if reason:
            signal_dict["reason"] = reason
        
        return signal_dict








