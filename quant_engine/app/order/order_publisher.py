"""app/order/order_publisher.py

Order publisher - publishes orders to Redis stream.
Used by strategies to submit orders.
"""

import time
import json
from typing import Optional

from app.core.event_bus import EventBus
from app.core.logger import logger
from app.order.order_message import OrderMessage


class OrderPublisher:
    """Publishes orders to Redis stream"""
    
    STREAM = "orders"
    
    @staticmethod
    def publish(
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "MKT",
        limit_price: Optional[float] = None
    ) -> str:
        """
        Publish order to Redis stream.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            qty: Order quantity
            order_type: MKT or LMT
            limit_price: Limit price (required for LMT)
            
        Returns:
            Message ID
        """
        msg = {
            "symbol": symbol,
            "side": side.upper(),
            "qty": float(qty),
            "order_type": order_type.upper(),
            "limit_price": limit_price,
            "timestamp": int(time.time() * 1000),
        }
        
        # Validate message
        try:
            order_msg = OrderMessage(**msg)
            order_msg.validate()
        except Exception as e:
            logger.error(f"Invalid order message: {e}")
            raise
        
        # Publish to stream
        try:
            msg_id = EventBus.stream_add(OrderPublisher.STREAM, msg)
            logger.info(
                f"Order published: {symbol} {side} {qty} {order_type} "
                f"(limit: {limit_price}, id: {msg_id})"
            )
            return msg_id
        except Exception as e:
            logger.error(f"Error publishing order: {e}")
            raise
    
    @staticmethod
    def publish_market_order(symbol: str, side: str, qty: float) -> str:
        """Convenience method for market orders"""
        return OrderPublisher.publish(symbol, side, qty, order_type="MKT")
    
    @staticmethod
    def publish_limit_order(symbol: str, side: str, qty: float, limit_price: float) -> str:
        """Convenience method for limit orders"""
        return OrderPublisher.publish(symbol, side, qty, order_type="LMT", limit_price=limit_price)








