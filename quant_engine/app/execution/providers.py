
"""
Concrete Execution Provider Implementations.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.core.logger import logger
from app.execution.execution_provider import (
    ExecutionProvider, 
    ExecutionProviderStatus,
    ProviderPosition,
    ProviderOrder
)
from app.trading.hammer_execution_service import HammerExecutionService, get_hammer_execution_service
from app.live.symbol_mapper import SymbolMapper

class HammerExecutionProvider(ExecutionProvider):
    """
    Execution Provider for Hammer Pro (HAMPRO).
    Wraps existing HammerExecutionService.
    """
    
    def __init__(self):
        self._service: Optional[HammerExecutionService] = None
        self._status = ExecutionProviderStatus.DISCONNECTED
        
    def connect(self) -> bool:
        # Service is usually initialized globally via `runall_orchestrator` setup
        self._service = get_hammer_execution_service()
        if self._service and self._service.hammer_client and self._service.hammer_client.is_connected():
            self._status = ExecutionProviderStatus.CONNECTED
            return True
        return False
        
    def disconnect(self):
        # We don't control the global service lifecycle here, just our view of it
        self._status = ExecutionProviderStatus.DISCONNECTED
        
    def get_status(self) -> ExecutionProviderStatus:
        if self._service and self._service.hammer_client and self._service.hammer_client.is_connected():
            return ExecutionProviderStatus.CONNECTED
        return ExecutionProviderStatus.DISCONNECTED
        
    def get_positions(self, account_id: str) -> List[ProviderPosition]:
        """Get open positions for 'HAMPRO'."""
        if account_id != 'HAMPRO':
             logger.warning(f"[HammerProvider] get_positions called for mismatch account {account_id}, expected HAMPRO")
             return []
             
        # Hammer position fetch logic would go here.
        # For now, fetching via existing client or `account_monitor` (not part of exec service)
        # TODO: Link to AccountMonitor to get real positions
        return [] 
        
    def get_open_orders(self, account_id: str) -> List[ProviderOrder]:
        """Get open orders for 'HAMPRO'."""
        if account_id != 'HAMPRO':
             return []
             
        # Hammer order fetch
        # TODO: Implement optional fetch via HammerClient `tradeCommand("orders")`
        return []
        
    def place_order(self, account_id: str, order_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Delegates to HammerExecutionService.place_order.
        Supports BUY, SELL, SHORT actions with HIDDEN orders by default.
        """
        if account_id != 'HAMPRO':
            return {
                "success": False,
                "message": f"HammerProvider cannot place order for {account_id}"
            }

        if not self._service:
            # Try to re-bind
            self.connect()
            
        if not self._service:
            return {"success": False, "message": "Service not bound"}
            
        action = order_request.get('action', 'BUY').upper()
        
        # ═══════════════════════════════════════════════════════════════════
        # HAMMER PRO - ALL ORDERS HIDDEN BY DEFAULT
        # Per Hammer API: SpInstructions="Hidden", DisplaySize=0
        # ═══════════════════════════════════════════════════════════════════
        return self._service.place_order(
            symbol=order_request['symbol'],
            side=action,  # BUY, SELL, or SHORT
            quantity=order_request['quantity'],
            price=order_request['price'],
            order_style=order_request.get('style', 'LIMIT'),
            hidden=True,  # QUANT_ENGINE CORE RULE: ALL ORDERS HIDDEN
            strategy_tag=order_request.get('strategy_tag', order_request.get('psfalgo_action', 'PROVIDER'))
        )
        
    def cancel_order(self, account_id: str, order_id: str) -> bool:
        if account_id != 'HAMPRO':
            return False
        
        if not self._service:
            self.connect()
        
        if not self._service:
            logger.error("[HammerProvider] Service not available for cancel")
            return False
        
        try:
            result = self._service.cancel_order(str(order_id))
            success = result.get('success', False)
            if success:
                logger.info(f"[HammerProvider] ✅ Cancelled order {order_id}")
            else:
                logger.warning(f"[HammerProvider] Cancel failed: {result.get('message', 'Unknown')}")
            return success
        except Exception as e:
            logger.error(f"[HammerProvider] Cancel error: {e}", exc_info=True)
            return False
        
    def replace_order(self, account_id: str, order_id: str, new_price: float, new_qty: Optional[float] = None) -> bool:
        """
        ATOMIC order modify for Hammer Pro using tradeCommandModify.
        Single API call — same OrderID preserved, no cancel gap.
        """
        if account_id != 'HAMPRO':
            return False
        
        if not self._service:
            self.connect()
        
        if not self._service:
            logger.error("[HammerProvider] Service not available for replace/modify")
            return False
        
        try:
            result = self._service.modify_order(str(order_id), float(new_price))
            success = result.get('success', False)
            if success:
                logger.info(f"[HammerProvider] ✅ MODIFIED order {order_id} → ${new_price:.4f} (atomic)")
            else:
                logger.warning(f"[HammerProvider] Modify failed: {result.get('message', 'Unknown')}")
            return success
        except Exception as e:
            logger.error(f"[HammerProvider] Modify error: {e}", exc_info=True)
            return False


class IBKRExecutionProvider(ExecutionProvider):
    """
    Execution Provider for IBKR (Gateway).
    Used for both PED and GUN (both port 4001).
    Strictly scoped to ONE account mode per instance.
    """
    
    def __init__(self, mode_name: str):
        """
        Args:
            mode_name: 'IBKR_PED' or 'IBKR_GUN'
        """
        self.mode_name = mode_name
        self._status = ExecutionProviderStatus.DISCONNECTED
        self.is_ped = (mode_name == 'IBKR_PED')
        logger.info(f"IBKRExecutionProvider initialized for {mode_name}")
        
    def connect(self) -> bool:
        # TODO: Connect to IBKR TWS/Gateway socket
        self._status = ExecutionProviderStatus.CONNECTED
        return True
        
    def disconnect(self):
        # TODO: Disconnect
        self._status = ExecutionProviderStatus.DISCONNECTED
        
    def get_status(self) -> ExecutionProviderStatus:
        return self._status
        
    def get_positions(self, account_id: str) -> List[ProviderPosition]:
        if account_id != self.mode_name:
            logger.warning(f"[{self.mode_name}] get_positions mismatch for {account_id}")
            return []
        # TODO: Fetch from IBKR EWrapper
        return []
        
    def get_open_orders(self, account_id: str) -> List[ProviderOrder]:
        if account_id != self.mode_name:
            return []
        # TODO: Fetch from IBKR EWrapper
        return []
        
    def place_order(self, account_id: str, order_request: Dict[str, Any]) -> Dict[str, Any]:
        if account_id != self.mode_name:
             return {
                "success": False,
                "message": f"IBKR Provider {self.mode_name} cannot place order for {account_id}"
            }
            
        # Connect to Real Connector
        from app.psfalgo.ibkr_connector import get_ibkr_connector
        connector = get_ibkr_connector(account_type=self.mode_name)
        
        if not connector:
             return {
                "success": False,
                "message": f"IBKR Connector for {self.mode_name} not found"
            }
            
        # Map Request to IBKR Format
        symbol = order_request.get('symbol')
        action = order_request.get('action') # 'BUY'/'SELL'
        quantity = order_request.get('quantity')
        price = order_request.get('price')
        style = order_request.get('style', 'LIMIT') # 'LIMIT'/'MARKET'
        
        ibkr_order_type = 'LMT' if style == 'LIMIT' else 'MKT'
        
        # Contract Details (Default to SMART/USD/STK)
        contract_details = {
            'symbol': symbol,
            'secType': 'STK',
            'exchange': 'SMART',
            'currency': 'USD'
        }
        
        # Order Details
        order_details = {
            'action': action,
            'totalQuantity': quantity,
            'orderType': ibkr_order_type,
            'lmtPrice': price,
            'strategy_tag': order_request.get('strategy_tag', order_request.get('psfalgo_action', 'PROVIDER'))  # 8-tag system
        }
        
        logger.info(f"[{self.mode_name}] Placing Real Order: {action} {quantity} {symbol} @ {price}")
        
        # CRITICAL: Check if connector is connected
        if not connector or not connector.connected:
            error_msg = f"IBKR connector not connected"
            if connector and connector.connection_error:
                error_msg += f" (last error: {connector.connection_error})"
            logger.error(f"[{self.mode_name}] {error_msg}")
            return {"success": False, "message": error_msg}
        
        # CRITICAL FIX: Use isolated sync to place order (same pattern as connect_isolated_sync)
        # This avoids event loop conflicts between FastAPI thread and IBKR thread
        from app.psfalgo.ibkr_connector import place_order_isolated_sync
        try:
            result = place_order_isolated_sync(
                account_type=self.mode_name,
                contract_details=contract_details,
                order_details=order_details
            )
            if result.get("success"):
                return {
                    "success": True,
                    "order_id": str(result.get("order_id", "")),
                    "message": result.get("message", "Order placed (Hidden)")
                }
            return {
                "success": False,
                "message": result.get("message", "IBKR place_order failed")
            }
        except Exception as e:
            logger.error(f"[{self.mode_name}] place_order error: {e}", exc_info=True)
            return {"success": False, "message": str(e)}
        
    def cancel_order(self, account_id: str, order_id: str) -> bool:
        if account_id != self.mode_name:
            return False
        
        try:
            from app.psfalgo.ibkr_connector import cancel_orders_isolated_sync
            
            # Convert order_id to int (IBKR uses int order IDs)
            try:
                order_id_int = int(order_id)
            except ValueError:
                logger.error(f"[{self.mode_name}] Invalid order_id format: {order_id}")
                return False
            
            # Cancel via isolated sync
            cancelled_ids = cancel_orders_isolated_sync(self.mode_name, [order_id_int])
            
            success = str(order_id_int) in [str(x) for x in cancelled_ids]
            if success:
                logger.info(f"[{self.mode_name}] ✅ Cancelled order {order_id}")
            else:
                logger.warning(f"[{self.mode_name}] Cancel failed for order {order_id}")
            
            return success
        except Exception as e:
            logger.error(f"[{self.mode_name}] Cancel error: {e}", exc_info=True)
            return False
        
    def replace_order(self, account_id: str, order_id: str, new_price: float, new_qty: Optional[float] = None) -> bool:
        """
        ATOMIC order modify for IBKR using ib_insync's placeOrder with existing orderId.
        
        In IBKR/TWS, calling placeOrder with an existing orderId automatically
        modifies the order (no cancel needed). This is the native IBKR modify mechanism.
        """
        if account_id != self.mode_name:
            return False
        
        try:
            from app.psfalgo.ibkr_connector import modify_order_isolated_sync
            
            result = modify_order_isolated_sync(
                account_type=self.mode_name,
                order_id=int(order_id),
                new_price=float(new_price),
                new_qty=float(new_qty) if new_qty is not None else None
            )
            
            success = result.get('success', False)
            if success:
                logger.info(f"[{self.mode_name}] ✅ MODIFIED order {order_id} → ${new_price:.4f} (atomic, same ID)")
            else:
                logger.warning(f"[{self.mode_name}] Modify failed: {result.get('message', 'Unknown')}")
            return success
            
        except ImportError:
            logger.warning(f"[{self.mode_name}] modify_order_isolated_sync not available, falling back to cancel+replace")
            return False
        except Exception as e:
            logger.error(f"[{self.mode_name}] Replace order error: {e}", exc_info=True)
            return False
