"""app/live/execution_adapter.py

Execution Adapter Pattern - Broker-agnostic execution interface.

This module provides the abstraction layer that allows switching between
different execution brokers (IBKR, Hammer Pro) at runtime without
changing strategy code.

Key Principles:
- Market data ALWAYS from Hammer (single source of truth)
- Execution is pluggable (IBKR | HAMMER)
- Strategy is broker-agnostic
- Account separation is enforced
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from enum import Enum

from app.core.logger import logger


class ExecutionBroker(Enum):
    """Execution broker types"""
    IBKR = "IBKR"
    HAMMER = "HAMMER"


class ExecutionAdapter(ABC):
    """
    Abstract base class for execution adapters.
    
    All execution adapters must implement this interface.
    Strategy code uses this interface, never broker-specific code.
    """
    
    def __init__(self, broker: ExecutionBroker, account_id: str):
        """
        Initialize execution adapter.
        
        Args:
            broker: Broker type (IBKR or HAMMER)
            account_id: Account identifier (for guard checks)
        """
        self.broker = broker
        self.account_id = account_id
        self.execution_callback: Optional[Callable] = None
        logger.info(f"Initialized {broker.value} execution adapter (account: {account_id})")
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to broker.
        
        Returns:
            True if connected successfully
        """
        pass
    
    @abstractmethod
    def disconnect(self):
        """Disconnect from broker"""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if connected and ready for orders.
        
        Returns:
            True if connected
        """
        pass
    
    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_type: str = "LIMIT"
    ) -> bool:
        """
        Place order.
        
        Args:
            symbol: Display format symbol (e.g., "CIM PRB")
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Limit price (required for LIMIT orders)
            order_type: "LIMIT" or "MARKET"
            
        Returns:
            True if order placed successfully
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancellation sent successfully
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions.
        
        Returns:
            List of position dictionaries with keys:
            - symbol: Display format symbol
            - qty: Position quantity (positive = long, negative = short)
            - avg_cost: Average cost basis
        """
        pass
    
    @abstractmethod
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get open orders.
        
        Returns:
            List of open order dictionaries
        """
        pass
    
    def set_execution_callback(self, callback: Callable):
        """
        Set callback for execution events (fills).
        
        Args:
            callback: Function that receives execution dict
        """
        self.execution_callback = callback
    
    def _normalize_execution(self, execution: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize execution message to standard format.
        
        All adapters should normalize their execution messages to this format:
        {
            "symbol": "CIM PRB",  # Display format
            "side": "BUY" or "SELL",
            "fill_qty": 100.0,
            "fill_price": 25.50,
            "timestamp": "2024-01-01T12:00:00",
            "order_id": "12345",
            "exec_id": "67890"
        }
        
        Args:
            execution: Raw execution from broker
            
        Returns:
            Normalized execution dict
        """
        return execution
    
    def _validate_account(self, expected_account: Optional[str] = None):
        """
        Account guard - prevent account mixing.
        
        Args:
            expected_account: Expected account ID (if provided)
            
        Raises:
            ValueError: If account mismatch detected
        """
        if expected_account and self.account_id != expected_account:
            raise ValueError(
                f"Account mismatch! Expected {expected_account}, "
                f"but adapter is configured for {self.account_id}"
            )








