
"""
Execution Provider Interface
Standardizes interaction with different broker backends.

Supported Providers:
- HAMPRO (Hammer Pro)
- IBKR_PED (IBKR Paper)
- IBKR_GUN (IBKR Live)
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

class ExecutionProviderStatus(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"

@dataclass
class ProviderPosition:
    symbol: str
    qty: float
    avg_price: float
    unrealized_pnl: float = 0.0
    currency: str = "USD"
    account: str = ""

@dataclass
class ProviderOrder:
    order_id: str
    symbol: str
    action: str  # BUY/SELL
    total_qty: float
    filled_qty: float
    price: float
    status: str  # PENDING, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED
    type: str = "LIMIT"
    tif: str = "DAY"
    
class ExecutionProvider(ABC):
    """
    Abstract Base Class for Execution Providers.
    """
    
    @abstractmethod
    def connect(self) -> bool:
        """Connect to the provider."""
        pass
        
    @abstractmethod
    def disconnect(self):
        """Disconnect from the provider."""
        pass
        
    @abstractmethod
    def get_status(self) -> ExecutionProviderStatus:
        """Get connection status."""
        pass
        
    @abstractmethod
    def get_positions(self, account_id: str) -> List[ProviderPosition]:
        """
        Get all open positions for specific account.
        Strictly isolated by account_id.
        """
        pass
        
    @abstractmethod
    def get_open_orders(self, account_id: str) -> List[ProviderOrder]:
        """
        Get all open orders for specific account.
        Strictly isolated by account_id.
        """
        pass
        
    @abstractmethod
    def place_order(self, account_id: str, order_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Place a new order for specific account.
        
        Args:
            account_id: Target account ID (HAMPRO/IBKR_PED/IBKR_GUN)
            order_request: Dict containing details (symbol, action, qty, price, etc.)
            
        Returns:
            Dict containing 'order_id' (broker ID) and 'success' boolean.
        """
        pass
        
    @abstractmethod
    def cancel_order(self, account_id: str, order_id: str) -> bool:
        """Cancel an existing order for specific account."""
        pass
        
    @abstractmethod
    def replace_order(self, account_id: str, order_id: str, new_price: float, new_qty: Optional[float] = None) -> bool:
        """Replace/Modify an existing order for specific account."""
        pass
        
    # --- Event Hooks (Strictly Account-Scoped) ---
    def on_order_status(self, account_id: str, order_status: Dict[str, Any]):
        """
        Callback for order status updates.
        MUST include account_id to route correctly.
        """
        pass
        
    def on_fill(self, account_id: str, fill_details: Dict[str, Any]):
        """
        Callback for fill events.
        MUST include account_id to route correctly.
        """
        pass

