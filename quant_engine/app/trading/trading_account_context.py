"""
Trading Account Context
Manages trading account mode and connection state.

IMPORTANT:
- Market data source is ALWAYS Hammer (fixed, non-switchable)
- Trading account is switchable: HAMPRO, IBKR_PED, IBKR_GUN

BAĞLANTI KURALLARI:
- IBKR PED ve IBKR GUN aynı anda ÇALIŞAMAZ; sadece biri açık olur. PED↔GUN geçişinde diğer IBKR disconnect edilir.
- IBKR PED + Hammer Pro (veya IBKR GUN + Hammer Pro) BİRLİKTE çalışır; mod değişince HİÇBİRİ kapatılmaz.
- set_trading_mode() SADECE hangi hesabın verisi/emri kullanılacağını seçer (Redis + in-memory).
- HAMPRO'ya geçerken IBKR (PED veya GUN) KAPATILMAZ. IBKR_PED/GUN'a geçerken Hammer KAPATILMAZ.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, TYPE_CHECKING
import asyncio  # 🔒 For account context lock
from app.core.logger import logger
from app.core.redis_client import get_redis

if TYPE_CHECKING:
    # Import Execution Providers (Interface only) - Lazy to avoid circular dependency
    from app.execution.execution_provider import ExecutionProvider

class TradingAccountMode(Enum):
    """Trading account mode enum"""
    HAMPRO = "HAMPRO"         # Hammer Pro Trading
    IBKR_PED = "IBKR_PED"     # IBKR PED (port 4001)
    IBKR_GUN = "IBKR_GUN"     # IBKR GUN (port 4001)


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
        
        self._hammer_connected: bool = False
        self._ibkr_ped_connected: bool = False
        self._ibkr_live_connected: bool = False
        
        # Redis Key for global account mode sync
        self._REDIS_MODE_KEY = "psfalgo:trading:account_mode"
        
        logger.info(f"TradingAccountContext initialized")
    
    @property
    def trading_mode(self) -> TradingAccountMode:
        """Get current trading account mode (reads from Redis for cross-process sync)"""
        redis = get_redis()
        if redis:
            try:
                mode_val = redis.get(self._REDIS_MODE_KEY)
                if mode_val:
                    return TradingAccountMode(mode_val)
            except Exception as e:
                logger.debug(f"Error reading trading mode from Redis: {e}")
        
        return self._trading_mode
    
    # --- Connection Properties ---
    @property
    def hammer_connected(self) -> bool:
        return self._hammer_connected
        
    @property
    def ibkr_ped_connected(self) -> bool:
        return self._ibkr_ped_connected
        
    @property
    def ibkr_live_connected(self) -> bool:
        return self._ibkr_live_connected
    
    # --- Connection Setters ---
    def set_hammer_connected(self, connected: bool):
        self._hammer_connected = connected
        
    def set_ibkr_ped_connected(self, connected: bool):
        self._ibkr_ped_connected = connected
        
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
        if mode == TradingAccountMode.IBKR_PED and not self._ibkr_ped_connected:
             logger.warning(f"Note: Switching to IBKR_PED but IBKR PED not connected yet.")

        if mode == TradingAccountMode.IBKR_GUN and not self._ibkr_live_connected:
             logger.warning(f"Note: Switching to IBKR_GUN but IBKR Live not connected yet.")
        
        old_mode = self.trading_mode
        self._trading_mode = mode
        
        # Persist to Redis for cross-process sync
        redis = get_redis()
        if redis:
            try:
                redis.set(self._REDIS_MODE_KEY, mode.value)
            except Exception as e:
                logger.error(f"Error persisting trading mode to Redis: {e}")
        
        if old_mode != mode:
            logger.info(f"Trading account mode changed: {old_mode.value} → {mode.value} (Global Sync)")
        
        return True
    
    def get_status(self) -> dict:
        """Get current context status"""
        return {
            "trading_mode": self._trading_mode.value,
            "hammer_connected": self._hammer_connected,
            "ibkr_ped_connected": self._ibkr_ped_connected,
            "ibkr_live_connected": self._ibkr_live_connected
        }


# Global instance
_trading_context: Optional[TradingAccountContext] = None

# 🔒 THREAD-SAFE ACCOUNT CONTEXT LOCK
# Prevents concurrent account switches from Dual Process Runner and manual XNL starts
_account_context_lock: Optional[asyncio.Lock] = None


def get_account_context_lock() -> asyncio.Lock:
    """Get global account context lock for coordinating account switches"""
    global _account_context_lock
    if _account_context_lock is None:
        _account_context_lock = asyncio.Lock()
    return _account_context_lock


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
