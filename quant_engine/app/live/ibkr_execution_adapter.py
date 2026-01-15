"""app/live/ibkr_execution_adapter.py

IBKR Execution Adapter.

Handles order execution via IBKR Gateway/TWS.
Market data is NOT used from IBKR - always from Hammer.
"""

from typing import Dict, Any, List, Optional, Callable
from ib_insync import Stock, MarketOrder, LimitOrder, Trade

from app.live.execution_adapter import ExecutionAdapter, ExecutionBroker
from app.ibkr.ibkr_client import IBKRClient
from app.core.logger import logger


class IBKRExecutionAdapter(ExecutionAdapter):
    """
    IBKR execution adapter.
    
    Responsibilities:
    - Connect to IBKR Gateway/TWS
    - Place orders via IBKR
    - Track executions
    - Normalize execution messages
    - Convert symbols (display → IBKR format)
    """
    
    def __init__(
        self,
        account_id: str,
        ibkr_client: Optional[IBKRClient] = None
    ):
        """
        Initialize IBKR execution adapter.
        
        Args:
            account_id: IBKR account ID (e.g., "DU123456" or "U123456")
            ibkr_client: IBKRClient instance (optional, creates new if not provided)
        """
        super().__init__(ExecutionBroker.IBKR, account_id)
        self.ibkr_client = ibkr_client or IBKRClient()
        self._execution_callbacks: List[Callable] = []
        
        # Track pending orders
        self.pending_orders: Dict[int, Dict[str, Any]] = {}
        
        # Note: Execution callbacks will be set up after connection
    
    def _on_execution_detail(self, trade: Trade, fill):
        """Handle IBKR execution detail"""
        try:
            if not fill:
                return
            
            # Normalize execution
            execution = {
                "symbol": trade.contract.symbol,  # IBKR uses native format
                "side": fill.execution.side.upper(),
                "fill_qty": float(fill.execution.shares),
                "fill_price": float(fill.execution.price),
                "timestamp": fill.execution.time.isoformat() if fill.execution.time else None,
                "order_id": str(trade.order.orderId),
                "exec_id": str(fill.execution.execId)
            }
            
            # Forward to callback
            if self.execution_callback:
                try:
                    self.execution_callback(execution)
                except Exception as e:
                    logger.error(f"Error in execution callback: {e}", exc_info=True)
        
        except Exception as e:
            logger.error(f"Error handling execution detail: {e}", exc_info=True)
    
    def _on_order_status(self, trade: Trade):
        """Handle IBKR order status update"""
        try:
            status = trade.orderStatus.status
            order_id = trade.order.orderId
            
            logger.debug(f"Order {order_id} status: {status}")
            
            # Store order info
            self.pending_orders[order_id] = {
                "order_id": order_id,
                "symbol": trade.contract.symbol,
                "status": status,
                "filled": float(trade.orderStatus.filled),
                "remaining": float(trade.orderStatus.remaining)
            }
        
        except Exception as e:
            logger.error(f"Error handling order status: {e}", exc_info=True)
    
    def connect(self) -> bool:
        """Connect to IBKR"""
        if not self.ibkr_client.is_connected():
            if not self.ibkr_client.connect():
                logger.error("Failed to connect to IBKR")
                return False
        
        # Set up execution callbacks after connection
        if self.ibkr_client.ib:
            try:
                # Hook into ib_insync execution events
                self.ibkr_client.ib.executionDetailsEvent += self._on_execution_detail
                self.ibkr_client.ib.orderStatusEvent += self._on_order_status
            except Exception as e:
                logger.warning(f"Could not set up IBKR callbacks: {e}")
        
        # Verify account
        accounts = self.ibkr_client.accounts
        if accounts and self.account_id not in accounts:
            logger.warning(
                f"Account {self.account_id} not found in IBKR accounts: {accounts}. "
                f"Using first available account."
            )
            if accounts:
                self.account_id = accounts[0]
                logger.info(f"Using account: {self.account_id}")
        
        logger.info(f"✅ IBKR execution adapter connected (account: {self.account_id})")
        return True
    
    def disconnect(self):
        """Disconnect from IBKR"""
        if self.ibkr_client:
            self.ibkr_client.disconnect()
        logger.info("IBKR execution adapter disconnected")
    
    def is_connected(self) -> bool:
        """Check if connected"""
        return self.ibkr_client.is_connected()
    
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_type: str = "LIMIT"
    ) -> bool:
        """
        Place order via IBKR.
        
        Args:
            symbol: Display format symbol (e.g., "CIM PRB")
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Limit price
            order_type: "LIMIT" or "MARKET"
            
        Returns:
            True if order placed successfully
        """
        if not self.is_connected():
            logger.error("IBKR not connected, cannot place order")
            return False
        
        # Account guard
        self._validate_account()
        
        try:
            # IBKR uses native symbol format (no conversion needed for preferred stocks)
            # "CIM PRB" stays as "CIM PRB" for IBKR
            ibkr_symbol = symbol
            
            # Create contract
            contract = Stock(ibkr_symbol, 'SMART', 'USD')
            
            # Create order
            if order_type.upper() == "LIMIT":
                if price <= 0:
                    logger.error(f"Invalid price for LIMIT order: {price}")
                    return False
                order = LimitOrder(side.upper(), quantity, price, tif='DAY')
            elif order_type.upper() == "MARKET":
                order = MarketOrder(side.upper(), quantity)
            else:
                logger.error(f"Unsupported order type: {order_type}")
                return False
            
            # Place order
            trade = self.ibkr_client.ib.placeOrder(contract, order)
            
            logger.info(
                f"✅ IBKR Order placed: {side} {quantity} {symbol} @ ${price:.2f} "
                f"(OrderID: {trade.order.orderId})"
            )
            
            return True
        
        except Exception as e:
            logger.error(f"Error placing IBKR order: {e}", exc_info=True)
            return False
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancellation sent successfully
        """
        if not self.is_connected():
            logger.error("IBKR not connected, cannot cancel order")
            return False
        
        try:
            # Find trade by order ID
            order_id_int = int(order_id)
            
            # Get all open trades
            open_trades = self.ibkr_client.ib.openTrades()
            for trade in open_trades:
                if trade.order.orderId == order_id_int:
                    self.ibkr_client.ib.cancelOrder(trade.order)
                    logger.info(f"✅ IBKR Order cancelled: {order_id}")
                    return True
            
            logger.warning(f"Order {order_id} not found in open orders")
            return False
        
        except Exception as e:
            logger.error(f"Error cancelling IBKR order: {e}", exc_info=True)
            return False
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions from IBKR.
        
        Returns:
            List of position dictionaries
        """
        if not self.is_connected():
            logger.warning("IBKR not connected")
            return []
        
        try:
            positions = self.ibkr_client.get_positions()
            
            # Filter by account if specified
            if self.account_id:
                positions = [p for p in positions if p.get('account') == self.account_id]
            
            # Normalize to standard format
            normalized = []
            for pos in positions:
                normalized.append({
                    "symbol": pos['symbol'],  # IBKR native format
                    "qty": pos['quantity'],
                    "avg_cost": pos['avg_cost']
                })
            
            return normalized
        
        except Exception as e:
            logger.error(f"Error getting IBKR positions: {e}", exc_info=True)
            return []
    
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get open orders from IBKR.
        
        Returns:
            List of open order dictionaries
        """
        if not self.is_connected():
            logger.warning("IBKR not connected")
            return []
        
        try:
            open_trades = self.ibkr_client.ib.openTrades()
            result = []
            
            for trade in open_trades:
                # Filter by account if specified
                if self.account_id and trade.order.account != self.account_id:
                    continue
                
                result.append({
                    "order_id": str(trade.order.orderId),
                    "symbol": trade.contract.symbol,
                    "side": trade.order.action.upper(),
                    "quantity": float(trade.order.totalQuantity),
                    "order_type": trade.order.orderType,
                    "limit_price": float(trade.order.lmtPrice) if trade.order.lmtPrice else None,
                    "status": trade.orderStatus.status,
                    "filled": float(trade.orderStatus.filled),
                    "remaining": float(trade.orderStatus.remaining)
                })
            
            return result
        
        except Exception as e:
            logger.error(f"Error getting IBKR open orders: {e}", exc_info=True)
            return []

