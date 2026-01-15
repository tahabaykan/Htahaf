"""
Hammer Execution Service
Places BUY orders via Hammer Pro API (SEMI_AUTO mode only).
"""

from typing import Dict, Any, Optional
from datetime import datetime
from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper
from app.event_driven.decision_engine.shadow_observer import shadow_observer


class HammerExecutionService:
    """
    Service to place orders via Hammer Pro.
    
    READ-ONLY for positions/orders, WRITE for order placement.
    Safety: One order per symbol per cycle.
    """
    
    def __init__(self, hammer_client=None, account_key: Optional[str] = None):
        """
        Initialize execution service.
        
        Args:
            hammer_client: HammerClient instance (optional, can be set later)
            account_key: Trading account key (optional, can be set later)
        """
        self.hammer_client = hammer_client
        self.account_key = account_key
        
        # Track orders per symbol per cycle (prevent duplicates)
        self._recent_orders: Dict[str, datetime] = {}  # {symbol: last_order_time}
        self._order_cooldown_seconds = 5  # Minimum seconds between orders for same symbol
        
        # Shadow Mode
        self.shadow_mode = True # Default to True for safety
        
        logger.info("HammerExecutionService initialized (SHADOW_MODE: %s)", self.shadow_mode)
    
    def set_hammer_client(self, hammer_client, account_key: str):
        """
        Set Hammer client and account key.
        
        Args:
            hammer_client: HammerClient instance
            account_key: Trading account key (e.g., "ALARIC:TOPI002240A7")
        """
        self.hammer_client = hammer_client
        self.account_key = account_key
        logger.info(f"HammerExecutionService configured for account: {account_key}")
    
    def place_buy_order(
        self,
        symbol: str,
        quantity: float,
        price: float,
        order_style: str = "LIMIT"
    ) -> Dict[str, Any]:
        """
        Place a BUY order via Hammer Pro.
        
        Args:
            symbol: Symbol to buy (display format, e.g., "CIM PRB")
            quantity: Order quantity
            price: Limit price
            order_style: Order style (LIMIT, MARKET, etc.) - for logging only
            
        Returns:
            Execution result dict:
            {
                'success': bool,
                'order_id': str or None,
                'message': str,
                'error': str or None
            }
        """
        if not self.hammer_client:
            return {
                'success': False,
                'order_id': None,
                'message': 'Hammer client not set',
                'error': 'Hammer client not initialized'
            }
        
        if not self.account_key:
            return {
                'success': False,
                'order_id': None,
                'message': 'Account key not set',
                'error': 'Account key not configured'
            }
        
        if not self.hammer_client.is_connected():
            return {
                'success': False,
                'order_id': None,
                'message': 'Hammer client not connected',
                'error': 'Connection required'
            }
        
        # Safety: Check cooldown (one order per symbol per cycle)
        now = datetime.now()
        if symbol in self._recent_orders:
            last_order_time = self._recent_orders[symbol]
            time_since_last = (now - last_order_time).total_seconds()
            if time_since_last < self._order_cooldown_seconds:
                logger.warning(
                    f"[EXECUTION BLOCKED] Symbol {symbol} has recent order "
                    f"({time_since_last:.1f}s ago, cooldown: {self._order_cooldown_seconds}s)"
                )
                shadow_observer.record_churn_event(symbol, 'THROTTLE')
                return {
                    'success': False,
                    'order_id': None,
                    'message': f'Cooldown active for {symbol}',
                    'error': f'Order placed {time_since_last:.1f}s ago, minimum {self._order_cooldown_seconds}s required'
                }
        
        # SHADOW MODE GUARD
        if self.shadow_mode:
            logger.info(
                f"🛡️ [SHADOW EXECUTION] Would place BUY order: "
                f"{symbol} {quantity} @ ${price:.4f} {order_style}"
            )
            self._recent_orders[symbol] = now
            shadow_observer.record_churn_event(symbol, 'INTENT')
            return {
                'success': True,
                'order_id': f"SHADOW_{int(now.timestamp()*1000)}",
                'message': f'[SHADOW] Order would be placed: {quantity} @ ${price:.4f}',
                'error': None
            }
        
        try:
            # Convert symbol to Hammer format
            hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
            logger.info(f"📊 Symbol mapping for execution: '{symbol}' → '{hammer_symbol}'")
            
            # Determine order type from style
            # order_style can be: BID, FRONT, ASK, SOFT_FRONT, etc.
            # For now, we'll use LIMIT for all (can be enhanced later)
            order_type = "Limit"
            
            # Validate quantity (must be positive integer)
            if quantity <= 0:
                return {
                    'success': False,
                    'order_id': None,
                    'message': f'Invalid quantity: {quantity}',
                    'error': 'Quantity must be positive'
                }
            
            quantity_int = int(quantity)
            if quantity_int <= 0:
                return {
                    'success': False,
                    'order_id': None,
                    'message': f'Invalid quantity: {quantity}',
                    'error': 'Quantity must be positive integer'
                }
            
            # Validate price (must be positive)
            if price <= 0:
                return {
                    'success': False,
                    'order_id': None,
                    'message': f'Invalid price: {price}',
                    'error': 'Price must be positive'
                }
            
            # Build order command
            order_cmd = {
                "cmd": "tradeCommandNew",
                "accountKey": self.account_key,
                "order": {
                    "ConditionalType": "None",
                    "Legs": [{
                        "Symbol": hammer_symbol,
                        "Action": "Buy",  # BUY only per requirements
                        "Quantity": quantity_int,
                        "OrderType": order_type,
                        "LimitPrice": float(price),
                        "LimitPriceType": "None",
                        "StopPrice": 0,
                        "StopPriceType": "None",
                        "Routing": "",  # Auto routing
                        "DisplaySize": 0,
                        "TIF": "Day",  # Time in Force: Day
                        "TIFDate": datetime.now().strftime("%Y-%m-%d"),
                        "SpInstructions": "None",
                        "CostMultiplier": 1
                    }]
                }
            }
            
            # Log execution attempt
            logger.info(
                f"[EXECUTING HAMMER] Placing BUY order: "
                f"{symbol} ({hammer_symbol}) {quantity} @ ${price:.4f} {order_style}"
            )
            
            # Send order command and wait for response
            response = self.hammer_client.send_command_and_wait(
                order_cmd,
                wait_for_response=True,
                timeout=10.0
            )
            
            # Check response
            if not response:
                logger.error(f"[EXECUTION FAILED] No response from Hammer for {symbol}")
                return {
                    'success': False,
                    'order_id': None,
                    'message': 'No response from Hammer',
                    'error': 'Timeout or no response'
                }
            
            if response.get('success') != 'OK':
                error_msg = response.get('result', 'Unknown error')
                logger.error(f"[EXECUTION FAILED] Hammer rejected order for {symbol}: {error_msg}")
                return {
                    'success': False,
                    'order_id': None,
                    'message': f'Hammer rejected: {error_msg}',
                    'error': str(error_msg)
                }
            
            # Success - track order
            self._recent_orders[symbol] = now
            
            # Extract order ID from response if available
            # Note: tradeCommandUpdate will have the order ID, but we may not get it immediately
            order_id = None
            result = response.get('result', {})
            if isinstance(result, dict):
                order = result.get('order', {})
                if isinstance(order, dict) and 'OrderID' in order:
                    order_id = order['OrderID']
            
            logger.info(
                f"[EXECUTION SUCCESS] BUY order placed: "
                f"{symbol} ({hammer_symbol}) {quantity} @ ${price:.4f} "
                f"(OrderID: {order_id or 'pending'})"
            )
            
            return {
                'success': True,
                'order_id': order_id,
                'message': f'Order placed: {quantity} @ ${price:.4f}',
                'error': None
            }
            
        except Exception as e:
            logger.error(f"[EXECUTION ERROR] Failed to place order for {symbol}: {e}", exc_info=True)
            return {
                'success': False,
                'order_id': None,
                'message': f'Execution error: {str(e)}',
                'error': str(e)
            }
    
    def clear_cooldown(self, symbol: Optional[str] = None):
        """
        Clear cooldown for a symbol (or all symbols).
        
        Args:
            symbol: Symbol to clear, or None to clear all
        """
        if symbol:
            self._recent_orders.pop(symbol, None)
            logger.debug(f"Cleared cooldown for {symbol}")
        else:
            self._recent_orders.clear()
            logger.debug("Cleared all cooldowns")


# ============================================================================
# Global Instance Management
# ============================================================================

_hammer_execution_service: Optional[HammerExecutionService] = None

def get_hammer_execution_service() -> Optional[HammerExecutionService]:
    """Get global Hammer execution service instance"""
    return _hammer_execution_service

def set_hammer_execution_service(hammer_client, account_key: str):
    """
    Set Hammer client for execution service.
    
    Args:
        hammer_client: HammerClient instance
        account_key: Trading account key
    """
    global _hammer_execution_service
    if not _hammer_execution_service:
        _hammer_execution_service = HammerExecutionService()
    _hammer_execution_service.set_hammer_client(hammer_client, account_key)
    logger.info(f"Hammer execution service initialized for account: {account_key}")

