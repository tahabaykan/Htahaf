"""app/ibkr/ibkr_client.py

⚠️ DEPRECATED — DO NOT USE FOR NEW CODE ⚠️

This module is the OLD IBKR client (Phase 1). It has been superseded by:
    app.psfalgo.ibkr_connector.IBKRConnector

IBKRConnector provides:
- Account-aware connections (IBKR_GUN / IBKR_PED)
- Proper event loop isolation (thread-safe)
- orderRef tagging for REV order identification
- Redis auto-push for UI visibility

This file is kept only for backward compatibility with legacy modules:
- app/ibkr/__init__.py (re-export)
- app/ibkr/ibkr_order_router.py (unused)
- app/ibkr/ibkr_sync.py (unused)
- app/live/ibkr_execution_adapter.py (unused)
- app/engine/engine_loop.py (unused)

TODO: Migrate remaining references and delete this file.
"""
import asyncio
import warnings

warnings.warn(
    "ibkr_client is DEPRECATED. Use app.psfalgo.ibkr_connector.get_ibkr_connector() instead.",
    DeprecationWarning,
    stacklevel=2
)

# NOTE: The old monkey-patch `asyncio.get_event_loop = asyncio.get_running_loop`
# was REMOVED because it corrupted the entire process's asyncio behavior.
# ibkr_connector handles event loop isolation properly per-thread.

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
        Connect to IBKR TWS/Gateway using nbefore_common_adv.py pattern.
        
        Returns:
            True if connected successfully
        """
        try:
            # Try multiple ports
            ports = [4001, 7496]  # Gateway and TWS ports
            connected = False
            
            for port in ports:
                try:
                    client_id = settings.IBKR_CLIENT_ID
                    logger.info(f"[IBKR] Connecting to {settings.IBKR_HOST}:{port} (ClientID: {client_id})...")
                    
                    self.ib = IB()
                    self.ib.connect(
                        settings.IBKR_HOST,
                        port,
                        clientId=client_id,
                        readonly=True
                    )
                    
                    if self.ib.isConnected():
                        connected = True
                        # Set delayed data mode
                        self.ib.reqMarketDataType(3)
                        logger.info(f"✅ IBKR {port} portu ile bağlantı başarılı!")
                        break
                        
                except Exception as e:
                    logger.warning(f"❌ IBKR {port} bağlantı hatası: {e}")
            
            if not connected:
                logger.error("! Hiçbir porta bağlanılamadı. TWS veya Gateway çalışıyor mu?")
                return False
            
            self.connected = True
            
            # Get accounts
            account_values = self.ib.accountValues()
            self.accounts = list(set([av.account for av in account_values]))
            logger.info(f"Accounts: {self.accounts}")
            
            return True
                
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
