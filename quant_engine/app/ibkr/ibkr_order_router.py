"""app/ibkr/ibkr_order_router.py

IBKR order router - routes orders from event bus to IBKR.
"""

from typing import Dict, Any
from ib_insync import Stock, MarketOrder, LimitOrder

from app.ibkr.ibkr_client import ibkr_client
from app.core.logger import logger
from app.core.event_bus import EventBus


class IBKROrderRouter:
    """IBKR order router"""
    
    def __init__(self):
        self.ibkr_client = ibkr_client
        self.orders_stream = 'orders'
        self.execs_stream = 'execs'
    
    def submit_order(self, contract, order) -> bool:
        """
        Submit order to IBKR.
        
        Args:
            contract: IB contract object
            order: IB order object
            
        Returns:
            True if order submitted successfully
        """
        try:
            logger.info("Submitting order to IBKR...")
            trade = self.ibkr_client.ib.placeOrder(contract, order)
            logger.info(f"✅ Order submitted: OrderID={trade.order.orderId}")
            
            # Publish execution event
            EventBus.publish('order_submitted', {
                'order_id': trade.order.orderId,
                'symbol': contract.symbol,
                'action': order.action,
                'quantity': order.totalQuantity,
                'status': 'Submitted'
            })
            
            return True
        except Exception as e:
            logger.error(f"Error submitting order: {e}")
            return False
    
    def route_order(self, order_data: Dict[str, Any]) -> bool:
        """
        Route order from event bus to IBKR.
        
        Args:
            order_data: Order dict with keys: symbol, action, quantity, price, order_type
            
        Returns:
            True if order routed successfully
        """
        try:
            symbol = order_data.get('symbol')
            action = order_data.get('action', 'BUY')
            quantity = float(order_data.get('quantity', 0))
            price = order_data.get('price')
            order_type = order_data.get('order_type', 'LIMIT')
            
            if not symbol or quantity <= 0:
                logger.error(f"Invalid order data: {order_data}")
                return False
            
            # Create contract
            contract = Stock(symbol, 'SMART', 'USD')
            
            # Create order
            if order_type.upper() == 'LIMIT':
                if not price:
                    logger.error("Price required for LIMIT order")
                    return False
                order = LimitOrder(action.upper(), quantity, float(price), tif='DAY')
            elif order_type.upper() == 'MARKET':
                order = MarketOrder(action.upper(), quantity)
            else:
                logger.error(f"Unsupported order type: {order_type}")
                return False
            
            # Submit order
            return self.submit_order(contract, order)
            
        except Exception as e:
            logger.error(f"Error routing order: {e}")
            return False








