
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
        Delegates to HammerExecutionService.place_buy_order (Currently BUY only supported).
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
        if action != 'BUY':
             return {
                "success": False, 
                "message": f"HammerProvider currently supports BUY only (requested {action})"
            }

        return self._service.place_buy_order(
            symbol=order_request['symbol'],
            quantity=order_request['quantity'],
            price=order_request['price'],
            order_style=order_request.get('style', 'LIMIT')
        )
        
    def cancel_order(self, account_id: str, order_id: str) -> bool:
        if account_id != 'HAMPRO':
            return False
        # TODO: Implement cancel via HammerClient
        logger.warning(f"[HammerProvider] Cancel not implemented for {order_id}")
        return False
        
    def replace_order(self, account_id: str, order_id: str, new_price: float, new_qty: Optional[float] = None) -> bool:
        if account_id != 'HAMPRO':
            return False
        # TODO: Implement replace
        return False


class IBKRExecutionProvider(ExecutionProvider):
    """
    Execution Provider for IBKR (Gateway).
    Used for both PED (Paper) and GUN (Live) modes.
    Strictly scoped to ONE account mode per instance.
    """
    
    def __init__(self, mode_name: str):
        """
        Args:
            mode_name: 'IBKR_PED' or 'IBKR_GUN'
        """
        self.mode_name = mode_name
        self._status = ExecutionProviderStatus.DISCONNECTED
        self.is_paper = (mode_name == 'IBKR_PED')
        logger.info(f"IBKRExecutionProvider initialized for {mode_name} (Paper={self.is_paper})")
        
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
            
        # TODO: Send reqIds / placeOrder
        logger.info(f"[{self.mode_name}] WOULD PLACE ORDER: {order_request}")
        return {
            "success": True, 
            "order_id": f"IBKR_STUB_{int(datetime.now().timestamp())}",
            "message": "IBKR Stub Order"
        }
        
    def cancel_order(self, account_id: str, order_id: str) -> bool:
        if account_id != self.mode_name:
            return False
            
        logger.info(f"[{self.mode_name}] WOULD CANCEL ORDER: {order_id}")
        return True
        
    def replace_order(self, account_id: str, order_id: str, new_price: float, new_qty: Optional[float] = None) -> bool:
        if account_id != self.mode_name:
            return False
            
        logger.info(f"[{self.mode_name}] WOULD REPLACE ORDER: {order_id} -> {new_price}")
        return True
