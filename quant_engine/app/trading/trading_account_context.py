"""
Trading Account Context
Manages trading account mode and connection state.

IMPORTANT:
- Market data source is ALWAYS Hammer (fixed, non-switchable)
- Trading account is switchable: HAMPRO, IBKR_PED, IBKR_GUN
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, TYPE_CHECKING
from app.core.logger import logger

if TYPE_CHECKING:
    # Import Execution Providers (Interface only) - Lazy to avoid circular dependency
    from app.execution.execution_provider import ExecutionProvider

class TradingAccountMode(Enum):
    """Trading account mode enum"""
    HAMPRO = "HAMPRO"         # Hammer Pro Trading
    IBKR_PED = "IBKR_PED"     # IBKR Paper Trading (PED)
    IBKR_GUN = "IBKR_GUN"     # IBKR Live Trading (GUN)


class TradingAccountContext:
    """
    Global trading account context.
    
    Manages:
    - Current trading account mode
    - Connection state for each account type
    - Validation rules for mode switching
    """
    

    def __init__(self):
        """Initialize with default values"""
        self._trading_mode: TradingAccountMode = TradingAccountMode.HAMPRO
        
        # Connection states
        self._hammer_connected: bool = False
        self._ibkr_paper_connected: bool = False
        self._ibkr_live_connected: bool = False
        
        logger.info(f"TradingAccountContext initialized with default mode: {self._trading_mode.value}")
    
    @property
    def trading_mode(self) -> TradingAccountMode:
        """Get current trading account mode"""
        return self._trading_mode
    
    # --- Connection Properties ---
    @property
    def hammer_connected(self) -> bool:
        return self._hammer_connected
        
    @property
    def ibkr_paper_connected(self) -> bool:
        return self._ibkr_paper_connected
        
    @property
    def ibkr_live_connected(self) -> bool:
        return self._ibkr_live_connected
    
    # --- Connection Setters ---
    def set_hammer_connected(self, connected: bool):
        self._hammer_connected = connected
        
    def set_ibkr_paper_connected(self, connected: bool):
        self._ibkr_paper_connected = connected
        
    def set_ibkr_live_connected(self, connected: bool):
        self._ibkr_live_connected = connected

    # --- Mode Switching ---
    def set_trading_mode(self, mode: TradingAccountMode) -> bool:
        """
        Set trading account mode.
        
        Args:
            mode: Trading account mode to set
            
        Returns:
            True if mode was set successfully, False if validation failed
        """
        # Connection checks
        if mode == TradingAccountMode.IBKR_PED and not self._ibkr_paper_connected:
             logger.warning(f"Note: Switching to IBKR_PED but IBKR Paper not connected yet.")

        if mode == TradingAccountMode.IBKR_GUN and not self._ibkr_live_connected:
             logger.warning(f"Note: Switching to IBKR_GUN but IBKR Live not connected yet.")
        
        old_mode = self._trading_mode
        self._trading_mode = mode
        
        if old_mode != mode:
            logger.info(f"Trading account mode changed: {old_mode.value} → {mode.value}")
        
        return True
    
    def get_status(self) -> dict:
        """Get current context status"""
        return {
            "trading_mode": self._trading_mode.value,
            "hammer_connected": self._hammer_connected,
            "ibkr_paper_connected": self._ibkr_paper_connected,
            "ibkr_live_connected": self._ibkr_live_connected
        }


# Global instance
_trading_context: Optional[TradingAccountContext] = None


def get_trading_context() -> TradingAccountContext:
    """Get global trading account context instance"""
    global _trading_context
    if _trading_context is None:
        _trading_context = TradingAccountContext()
    return _trading_context


def initialize_trading_context():
    """Initialize global trading account context"""
    global _trading_context
    if _trading_context is None:
        _trading_context = TradingAccountContext()
        logger.info("Trading account context initialized")
    return _trading_context








