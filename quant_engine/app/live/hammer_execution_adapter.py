"""app/live/hammer_execution_adapter.py

Hammer Execution Adapter.

Wraps existing HammerExecution to implement ExecutionAdapter interface.
"""

from typing import Dict, Any, List, Optional, Callable

from app.live.execution_adapter import ExecutionAdapter, ExecutionBroker
from app.live.hammer_execution import HammerExecution
from app.live.hammer_client import HammerClient
from app.core.logger import logger


class HammerExecutionAdapter(ExecutionAdapter):
    """
    Hammer Pro execution adapter.
    
    Wraps existing HammerExecution to provide ExecutionAdapter interface.
    """
    
    def __init__(
        self,
        account_key: str,
        hammer_client: HammerClient
    ):
        """
        Initialize Hammer execution adapter.
        
        Args:
            account_key: Hammer account key (e.g., "ALARIC:TOPI002240A7")
            hammer_client: HammerClient instance
        """
        super().__init__(ExecutionBroker.HAMMER, account_key)
        self.hammer_client = hammer_client
        
        # Wrap existing HammerExecution
        self._hammer_execution = HammerExecution(
            hammer_client=hammer_client,
            account_key=account_key,
            execution_callback=self._on_execution_internal
        )
    
    def _on_execution_internal(self, execution: Dict[str, Any]):
        """Internal execution handler - forwards to adapter callback"""
        if self.execution_callback:
            try:
                self.execution_callback(execution)
            except Exception as e:
                logger.error(f"Error in execution callback: {e}", exc_info=True)
    
    def connect(self) -> bool:
        """Connect to Hammer Pro"""
        if not self.hammer_client.is_connected():
            if not self.hammer_client.connect():
                logger.error("Failed to connect to Hammer Pro")
                return False
        
        # Account guard
        self._validate_account(self.account_id)
        
        logger.info(f"✅ Hammer execution adapter connected (account: {self.account_id})")
        return True
    
    def disconnect(self):
        """Disconnect from Hammer Pro"""
        if self.hammer_client:
            self.hammer_client.disconnect()
        logger.info("Hammer execution adapter disconnected")
    
    def is_connected(self) -> bool:
        """Check if connected"""
        return self.hammer_client.is_connected()
    
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_type: str = "LIMIT"
    ) -> bool:
        """
        Place order via Hammer Pro.
        
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
            logger.error("Hammer not connected, cannot place order")
            return False
        
        # Account guard
        self._validate_account(self.account_id)
        
        # Delegate to wrapped HammerExecution
        return self._hammer_execution.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type
        )
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancellation sent successfully
        """
        if not self.is_connected():
            logger.error("Hammer not connected, cannot cancel order")
            return False
        
        # Delegate to wrapped HammerExecution
        return self._hammer_execution.cancel_order(order_id)
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions from Hammer Pro.
        
        Returns:
            List of position dictionaries
        """
        if not self.is_connected():
            logger.warning("Hammer not connected")
            return []
        
        # Delegate to wrapped HammerExecution
        return self._hammer_execution.get_positions()
    
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get open orders from Hammer Pro.
        
        Note: HammerExecution doesn't have get_open_orders yet.
        This is a placeholder for future implementation.
        
        Returns:
            List of open order dictionaries
        """
        if not self.is_connected():
            logger.warning("Hammer not connected")
            return []
        
        # TODO: Implement get_open_orders in HammerExecution
        logger.warning("get_open_orders not yet implemented for Hammer")
        return []








