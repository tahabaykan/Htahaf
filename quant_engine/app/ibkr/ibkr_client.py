"""app/ibkr/ibkr_client.py

IBKR client wrapper using ib_insync.
Handles connection, account info, positions, and order management.
"""

from typing import Optional, List, Dict, Any
from ib_insync import IB, Stock, MarketOrder, LimitOrder

from app.core.logger import logger
from app.config.settings import settings


class IBKRClient:
    """IBKR client wrapper"""
    
    def __init__(self):
        self.ib: Optional[IB] = None
        self.connected = False
        self.accounts: List[str] = []
    
    def connect(self) -> bool:
        """
        Connect to IBKR TWS/Gateway.
        
        Returns:
            True if connected successfully
        """
        try:
            logger.info(f"Connecting to IBKR: {settings.IBKR_HOST}:{settings.IBKR_PORT} (Client ID: {settings.IBKR_CLIENT_ID})")
            
            self.ib = IB()
            self.ib.connect(
                settings.IBKR_HOST,
                settings.IBKR_PORT,
                clientId=settings.IBKR_CLIENT_ID,
                timeout=15
            )
            
            if self.ib.isConnected():
                self.connected = True
                logger.info("✅ Connected to IBKR successfully")
                
                # Get accounts
                account_values = self.ib.accountValues()
                self.accounts = list(set([av.account for av in account_values]))
                logger.info(f"Accounts: {self.accounts}")
                
                return True
            else:
                logger.error("❌ IBKR connection failed")
                return False
                
        except Exception as e:
            logger.error(f"IBKR connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from IBKR"""
        try:
            if self.connected and self.ib:
                self.ib.disconnect()
                self.connected = False
                logger.info("Disconnected from IBKR")
        except Exception as e:
            logger.error(f"Error disconnecting from IBKR: {e}")
    
    def is_connected(self) -> bool:
        """Check connection status"""
        if self.ib:
            return self.ib.isConnected()
        return False
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions"""
        if not self.is_connected():
            logger.warning("IBKR not connected")
            return []
        
        try:
            positions = self.ib.positions()
            result = []
            
            for pos in positions:
                result.append({
                    'symbol': pos.contract.symbol,
                    'quantity': float(pos.position),
                    'avg_cost': float(getattr(pos, 'averageCost', 0)),
                    'account': pos.account,
                    'market_value': float(getattr(pos, 'marketValue', 0))
                })
            
            return result
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def place_order(self, symbol: str, action: str, quantity: float, price: Optional[float] = None, order_type: str = "LIMIT") -> bool:
        """
        Place order to IBKR.
        
        Args:
            symbol: Stock symbol
            action: BUY or SELL
            quantity: Order quantity
            price: Limit price (required for LIMIT orders)
            order_type: LIMIT or MARKET
            
        Returns:
            True if order placed successfully
        """
        if not self.is_connected():
            logger.error("IBKR not connected, cannot place order")
            return False
        
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            
            if order_type.upper() == "LIMIT":
                if price is None:
                    logger.error("Price required for LIMIT order")
                    return False
                order = LimitOrder(action.upper(), quantity, price, tif='DAY')
            elif order_type.upper() == "MARKET":
                order = MarketOrder(action.upper(), quantity)
            else:
                logger.error(f"Unsupported order type: {order_type}")
                return False
            
            trade = self.ib.placeOrder(contract, order)
            logger.info(f"✅ Order placed: {symbol} {action} {quantity} @ {price} (OrderID: {trade.order.orderId})")
            return True
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return False


# Global IBKR client instance
ibkr_client = IBKRClient()








