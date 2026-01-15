"""
Hammer Orders Service
READ-ONLY service to fetch open orders from Hammer Pro trading account.
"""

from typing import List, Dict, Any, Optional
from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper


class HammerOrdersService:
    """
    Service to fetch and normalize open orders from Hammer Pro.
    
    READ-ONLY: No order placement, no cancel, no modifications.
    """
    
    def __init__(self, hammer_client=None):
        """
        Initialize orders service.
        
        Args:
            hammer_client: HammerClient instance (optional, can be set later)
        """
        self.hammer_client = hammer_client
        self.account_key: Optional[str] = None
    
    def set_hammer_client(self, hammer_client, account_key: str):
        """
        Set Hammer client and account key.
        
        Args:
            hammer_client: HammerClient instance
            account_key: Trading account key (e.g., "ALARIC:TOPI002240A7")
        """
        self.hammer_client = hammer_client
        self.account_key = account_key
        logger.info(f"HammerOrdersService initialized with account: {account_key}")
    
    def get_orders(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch open orders from Hammer Pro.
        
        Args:
            force_refresh: If True, force refresh from broker instead of cached data
            
        Returns:
            List of normalized order records:
            [
                {
                    'symbol': str,
                    'side': str,  # 'BUY' or 'SELL'
                    'quantity': float,
                    'price': float,  # limit price if limit order
                    'order_type': str,  # 'LIMIT', 'MARKET', 'STOP', etc.
                    'status': str,  # 'OPEN', 'FILLED', 'CANCELED', etc.
                    'order_id': str,
                }
            ]
        """
        if not self.hammer_client:
            logger.warning("Hammer client not set in HammerOrdersService")
            return []
        
        if not self.account_key:
            logger.warning("Account key not set in HammerOrdersService")
            return []
        
        if not self.hammer_client.is_connected():
            logger.warning("Hammer client not connected")
            return []
        
        try:
            # Send getTransactions command
            cmd = {
                "cmd": "getTransactions",
                "accountKey": self.account_key,
                "changesOnly": False  # Get all transactions
            }
            
            if force_refresh:
                cmd["forceRefresh"] = True
            
            logger.debug(f"Fetching orders from Hammer: {self.account_key}")
            response = self.hammer_client.send_command_and_wait(
                cmd,
                wait_for_response=True,
                timeout=10.0
            )
            
            if not response or response.get('success') != 'OK':
                logger.warning(f"Failed to get transactions: {response}")
                return []
            
            # Parse transactions from response
            result = response.get('result', {})
            
            # Handle different response formats
            transactions_data = []
            
            # Format 1: Direct transactions array
            if isinstance(result, list):
                transactions_data = result
            # Format 2: Nested in result object
            elif isinstance(result, dict):
                if 'transactions' in result:
                    transactions_data = result['transactions']
                elif 'accountKey' in result:
                    # This might be a transactionsUpdate format
                    transactions_data = result.get('transactions', [])
            
            # Filter for open orders only
            open_orders = [
                txn for txn in transactions_data
                if self._is_open_order(txn)
            ]
            
            # Normalize orders
            normalized_orders = []
            for order in open_orders:
                normalized = self._normalize_order(order)
                if normalized:
                    normalized_orders.append(normalized)
            
            logger.info(f"Fetched {len(normalized_orders)} open orders from Hammer")
            return normalized_orders
            
        except Exception as e:
            logger.error(f"Error fetching orders from Hammer: {e}", exc_info=True)
            return []
    
    def _is_open_order(self, txn: Dict[str, Any]) -> bool:
        """
        Check if transaction is an open order.
        
        Args:
            txn: Transaction data from Hammer
            
        Returns:
            True if order is open
        """
        # Check status
        status = (
            txn.get('StatusID') or
            txn.get('statusID') or
            txn.get('Status') or
            txn.get('status') or
            ''
        ).upper()
        
        # Check IsOpen flag if available
        is_open = txn.get('IsOpen') or txn.get('isOpen', False)
        
        # Open orders have status "Open" or IsOpen=True
        return status == 'OPEN' or is_open
    
    def _normalize_order(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize Hammer order to internal schema.
        
        Args:
            order: Raw order data from Hammer
            
        Returns:
            Normalized order dict or None if invalid
        """
        try:
            # Extract symbol
            symbol = (
                order.get('Symbol') or
                order.get('symbol') or
                order.get('Sym') or
                order.get('sym')
            )
            
            if not symbol:
                return None
            
            # Normalize symbol from Hammer format to display format
            display_symbol = SymbolMapper.to_display_symbol(symbol)
            
            # Extract side (BUY or SELL)
            action = (
                order.get('Action') or
                order.get('action') or
                ''
            ).upper()
            
            if action in ['BUY', 'BUY_TO_COVER', 'COVER']:
                side = 'BUY'
            elif action in ['SELL', 'SELL_SHORT', 'SHORT']:
                side = 'SELL'
            else:
                # Default to BUY if unclear
                side = 'BUY'
            
            # Extract quantity
            quantity = (
                order.get('QTY') or
                order.get('qty') or
                order.get('Quantity') or
                order.get('quantity') or
                order.get('RemainingQTY') or
                order.get('remainingQTY') or
                0.0
            )
            quantity = float(quantity) if quantity else 0.0
            
            # Extract order type
            order_type = (
                order.get('OrderType') or
                order.get('orderType') or
                order.get('Type') or
                order.get('type') or
                'MARKET'
            ).upper()
            
            # Extract price (limit price for limit orders)
            price = (
                order.get('LimitPrice') or
                order.get('limitPrice') or
                order.get('Price') or
                order.get('price') or
                None
            )
            price = float(price) if price else None
            
            # Extract status
            status = (
                order.get('StatusID') or
                order.get('statusID') or
                order.get('Status') or
                order.get('status') or
                'UNKNOWN'
            ).upper()
            
            # Extract order ID
            order_id = (
                order.get('OrderID') or
                order.get('orderID') or
                order.get('OrderId') or
                order.get('orderId') or
                str(order.get('OrderID', ''))
            )
            
            return {
                'symbol': display_symbol,  # Use normalized display symbol
                'side': side,
                'quantity': quantity,
                'price': price,
                'order_type': order_type,
                'status': status,
                'order_id': str(order_id)
            }
            
        except Exception as e:
            logger.error(f"Error normalizing order: {e}", exc_info=True)
            return None

