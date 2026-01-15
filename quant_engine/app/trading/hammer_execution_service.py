"""
Hammer Execution Service
Places BUY orders via Hammer Pro API (SEMI_AUTO mode only).
"""

from typing import Dict, Any, Optional
from datetime import datetime
from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper
from app.event_driven.decision_engine.shadow_observer import shadow_observer
from app.trading.hammer_fills_listener import get_hammer_fills_listener


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
        
        # Shadow Mode logic:
        # User Rule: Live Data -> Live Execution, Test Mode -> Shadow Mode
        from app.config.settings import settings
        self.shadow_mode = not settings.LIVE_MODE 
        
        logger.info(f"HammerExecutionService initialized (LIVE_MODE: {settings.LIVE_MODE}, SHADOW_MODE: {self.shadow_mode})")

        # Register listener if client provided
        if self.hammer_client:
            self._register_fills_listener()

    
    def _register_fills_listener(self):
        """Register the fills listener as an observer"""
        try:
             listener = get_hammer_fills_listener()
             self.hammer_client.add_observer(listener.on_message)
             logger.info("HammerFillsListener registered as observer")
        except Exception as e:
             logger.error(f"Failed to register HammerFillsListener: {e}")

    def set_hammer_client(self, hammer_client, account_key: str):
        """
        Set Hammer client and account key.
        
        Args:
            hammer_client: HammerClient instance
            account_key: Trading account key (e.g., "ALARIC:TOPI002240A7")
        """
        self.hammer_client = hammer_client
        self.account_key = account_key
        self._register_fills_listener()
        logger.info(f"HammerExecutionService configured for account: {account_key}")
    
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_style: str = "LIMIT",
        hidden: bool = True,
        strategy_tag: str = "UNKNOWN"
    ) -> Dict[str, Any]:
        """
        Place a BUY/SELL order via Hammer Pro.
        Mirrors Janall logic (Hidden by default).
        
        Args:
            symbol: Symbol (display format)
            side: 'BUY' or 'SELL' (or 'SHORT')
            quantity: Order quantity
            price: Limit price
            order_style: Order style (LIMIT, MARKET, etc.)
            hidden: Whether to hide the order (SpInstruction: Hidden)
            strategy_tag: Strategy identifier (e.g., LT, MM, JFIN) for logging
            
        Returns:
            Execution result dict
        """
        if not self.hammer_client:
            return {'success': False, 'message': 'Hammer client not set'}
        
        if not self.account_key:
            return {'success': False, 'message': 'Account key not set'}
        
        if not self.hammer_client.is_connected():
            return {'success': False, 'message': 'Hammer client not connected'}
        
        # Safety: Check cooldown (one order per symbol per cycle)
        now = datetime.now()
        if symbol in self._recent_orders:
            last_order_time = self._recent_orders[symbol]
            time_since_last = (now - last_order_time).total_seconds()
            if time_since_last < self._order_cooldown_seconds:
                logger.warning(
                    f"[EXECUTION BLOCKED] Symbol {symbol} has recent order "
                    f"({time_since_last:.1f}s ago)"
                )
                shadow_observer.record_churn_event(symbol, 'THROTTLE')
                return {
                    'success': False,
                    'message': f'Cooldown active for {symbol}',
                    'error': 'Throttled'
                }
        
        # Normalize Side
        action = side.capitalize() # Buy / Sell / Short
        if action not in ['Buy', 'Sell', 'Short', 'Cover']:
             # Default map
             if side.upper() == 'BUY': action = 'Buy'
             elif side.upper() == 'SELL': action = 'Sell' # Janall logic: Sell (Short if needed? Hammer distinguishes usually)
             else: action = 'Buy'

        # SHADOW MODE GUARD
        if self.shadow_mode:
            logger.info(
                f"🛡️ [SHADOW EXECUTION] Would place {action.upper()} order: "
                f"{symbol} {quantity} @ ${price:.4f} {order_style} (Tag: {strategy_tag})"
            )
            self._recent_orders[symbol] = now
            shadow_observer.record_churn_event(symbol, 'INTENT')
            return {
                'success': True,
                'order_id': f"SHADOW_{int(now.timestamp()*1000)}",
                'message': f'[SHADOW] Order would be placed: {action} {quantity} @ ${price:.4f}',
                'error': None
            }
        
        try:
            # Convert symbol
            hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
            
            # Janall Logic: SpInstructions="Hidden"
            sp_instructions = "Hidden" if hidden else "None"
            
            # OrderCmd
            order_cmd = {
                "cmd": "tradeCommandNew",
                "accountKey": self.account_key,
                "order": {
                    "ConditionalType": "None",
                    "Legs": [{
                        "Symbol": hammer_symbol,
                        "Action": action,
                        "Quantity": int(quantity),
                        "OrderType": order_style.capitalize() if 'limit' in order_style.lower() else "Limit", # Janall defaults to Limit
                        "LimitPrice": float(price),
                        "LimitPriceType": "None",
                        "StopPrice": 0,
                        "StopPriceType": "None",
                        "Routing": "Smart", # Janall calls it empty "", but Smart is safer fallback? Janall used ""
                        "DisplaySize": 0,
                        "TIF": "Day",
                        "TIFDate": datetime.now().strftime("%Y-%m-%d"),
                        "SpInstructions": sp_instructions,
                        "CostMultiplier": 1
                    }]
                }
            }
            
            if order_style.lower() == 'market':
                 order_cmd['order']['Legs'][0]['OrderType'] = 'Market'
                 order_cmd['order']['Legs'][0]['LimitPrice'] = 0

            # Log execution attempt
            logger.info(
                f"[EXECUTING HAMMER] Placing {action.upper()} order: "
                f"{symbol} ({hammer_symbol}) {int(quantity)} @ ${price:.4f} (Hidden={hidden}, Tag={strategy_tag})"
            )
            
            # Send
            response = self.hammer_client.send_command_and_wait(
                order_cmd,
                wait_for_response=True,
                timeout=10.0
            )
            
            if not response or response.get('success') != 'OK':
                error_msg = response.get('result', 'Timeout or Unknown Error') if response else 'No Response'
                logger.error(f"[EXECUTION FAILED] Hammer: {error_msg}")
                return {'success': False, 'message': f'Hammer Error: {error_msg}'}

            # Success
            self._recent_orders[symbol] = now
            
            # Extract ID
            order_id = None
            result = response.get('result', {})
            if isinstance(result, dict):
                 order_data = result.get('order', {})
                 if isinstance(order_data, dict):
                     order_id = order_data.get('OrderID')
            
            # Register Tag
            if order_id:
                 get_hammer_fills_listener().register_order(str(order_id), strategy_tag)

            logger.info(f"[EXECUTION SUCCESS] Order Placed: {order_id}")
            
            return {
                'success': True,
                'order_id': order_id,
                'message': f'Order Placed {action} {quantity} @ {price}'
            }
            
        except Exception as e:
            logger.error(f"[EXECUTION ERROR] {e}", exc_info=True)
            return {'success': False, 'message': str(e)}

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an order via Hammer Pro.
        
        Args:
            order_id: The ID of the order to cancel
            
        Returns:
            Result dict
        """
        if not self.hammer_client:
            return {'success': False, 'message': 'Hammer client not set'}
            
        if self.shadow_mode:
            logger.info(f"🛡️ [SHADOW] Would cancel order {order_id}")
            return {'success': True, 'message': '[SHADOW] Order Cancelled'}
            
        try:
            cmd = {
                "cmd": "tradeCommandCancel",
                "accountKey": self.account_key,
                "orderID": order_id
            }
            
            logger.info(f"[HAMMER CANCEL] Cancelling order {order_id}")
            response = self.hammer_client.send_command_and_wait(cmd, timeout=5.0)
            
            if response and response.get('success') == 'OK':
                logger.info(f"[HAMMER CANCEL] Success: {order_id}")
                return {'success': True, 'message': 'Order Cancelled'}
            else:
                msg = response.get('result') if response else "No response"
                logger.error(f"[HAMMER CANCEL] Failed: {msg}")
                return {'success': False, 'message': f"Cancel Failed: {msg}"}
                
        except Exception as e:
            logger.error(f"[HAMMER CANCEL] Error: {e}")
            return {'success': False, 'message': str(e)}
    
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

