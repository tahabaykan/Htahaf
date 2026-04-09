"""
Dual Connection Manager - Phase 11
===================================

Manages persistent connections to IBKR and HAMMER PRO simultaneously.
Connections are established once on startup and maintained throughout the application lifecycle.

IMPORTANT CONNECTION RULES:
- HAMMER_PRO + IBKR_PED = OK ✅
- HAMMER_PRO + IBKR_GUN = OK ✅
- IBKR_PED + IBKR_GUN = NOT POSSIBLE ❌ (same Gateway account)

Key Principles:
- HAMMER_PRO + ONE IBKR account (PED or GUN) can connect together
- Connections remain PERSISTENT (never disconnected during mode switch)
- Active mode determines which data source is used for positions/orders/fills
- Market data ALWAYS comes from HAMMER PRO (unchanged)
"""

from typing import Optional, Dict, Any
from enum import Enum
import asyncio
from app.core.logger import logger


class ConnectionStatus(Enum):
    """Connection status enum"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class DualConnectionManager:
    """
    Manages persistent connections to IBKR and HAMMER PRO.
    
    IMPORTANT CONNECTION RULES:
    - HAMMER_PRO + IBKR_PED = OK ✅
    - HAMMER_PRO + IBKR_GUN = OK ✅
    - IBKR_PED + IBKR_GUN = NOT POSSIBLE ❌ (same Gateway account)
    
    Responsibilities:
    - Initialize and maintain HAMMER_PRO connection (always)
    - Initialize and maintain ONE IBKR connection (PED or GUN, not both)
    - Track connection status for each account
    - Handle switching between IBKR accounts (disconnect one, connect other)
    """
    
    def __init__(self):
        """Initialize Dual Connection Manager"""
        # Connection status tracking
        self._ibkr_ped_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
        self._ibkr_gun_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
        self._hammer_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
        
        # Track which IBKR account is currently connected
        self._active_ibkr_type: Optional[str] = None  # "IBKR_PED" or "IBKR_GUN"
        
        # Connection error tracking
        self._ibkr_ped_error: Optional[str] = None
        self._ibkr_gun_error: Optional[str] = None
        self._hammer_error: Optional[str] = None
        
        logger.info("[DUAL_CONN] DualConnectionManager initialized")
    
    async def connect_startup(self, default_ibkr: str = "IBKR_PED") -> Dict[str, Any]:
        """
        Connect to HAMMER_PRO + ONE IBKR account on startup.
        
        IMPORTANT: IBKR_PED and IBKR_GUN share the same Gateway, 
        so only ONE can be connected at a time.
        
        Args:
            default_ibkr: Which IBKR account to connect ("IBKR_PED" or "IBKR_GUN")
        
        Returns:
            Dict with connection results
        """
        logger.info(f"[DUAL_CONN] 🚀 Starting dual connection (HAMMER_PRO + {default_ibkr})...")
        
        results = {
            'ibkr': {'success': False, 'connected': False, 'account': default_ibkr},
            'hammer_pro': {'success': False, 'connected': False}
        }
        
        # Connect HAMMER_PRO and ONE IBKR account in parallel
        if default_ibkr == "IBKR_GUN":
            ibkr_task = self._connect_ibkr_gun()
        else:
            ibkr_task = self._connect_ibkr_ped()
        
        hammer_task = self._connect_hammer_pro()
        
        connection_results = await asyncio.gather(ibkr_task, hammer_task, return_exceptions=True)
        
        # Process results
        results['ibkr'] = connection_results[0] if not isinstance(connection_results[0], Exception) else {'success': False, 'error': str(connection_results[0])}
        results['hammer_pro'] = connection_results[1] if not isinstance(connection_results[1], Exception) else {'success': False, 'error': str(connection_results[1])}
        
        # Track which IBKR is connected
        if results['ibkr'].get('connected'):
            self._active_ibkr_type = default_ibkr
        
        # Log summary
        ibkr_ok = results['ibkr'].get('connected', False)
        hammer_ok = results['hammer_pro'].get('connected', False)
        
        logger.info(f"[DUAL_CONN] ✅ Connection Summary: {default_ibkr}={ibkr_ok}, HAMMER_PRO={hammer_ok}")
        
        return results
    
    async def switch_ibkr_account(self, new_ibkr: str) -> Dict[str, Any]:
        """
        Switch from one IBKR account to another.
        
        IMPORTANT: This will DISCONNECT the current IBKR account before connecting the new one.
        Only ONE IBKR account can be connected at a time (same Gateway).
        
        Args:
            new_ibkr: New IBKR account to connect ("IBKR_PED" or "IBKR_GUN")
        
        Returns:
            Dict with switch result
        """
        if new_ibkr not in ["IBKR_PED", "IBKR_GUN"]:
            return {'success': False, 'error': f'Invalid IBKR account: {new_ibkr}'}
        
        # If already connected to this account, just return success
        if self._active_ibkr_type == new_ibkr:
            if new_ibkr == "IBKR_PED" and self._ibkr_ped_status == ConnectionStatus.CONNECTED:
                return {'success': True, 'connected': True, 'already_connected': True}
            if new_ibkr == "IBKR_GUN" and self._ibkr_gun_status == ConnectionStatus.CONNECTED:
                return {'success': True, 'connected': True, 'already_connected': True}
        
        logger.info(f"[DUAL_CONN] 🔄 Switching IBKR from {self._active_ibkr_type} to {new_ibkr}...")
        
        # Disconnect current IBKR account
        await self._disconnect_current_ibkr()
        
        # Connect new IBKR account
        if new_ibkr == "IBKR_GUN":
            result = await self._connect_ibkr_gun()
        else:
            result = await self._connect_ibkr_ped()
        
        if result.get('connected'):
            self._active_ibkr_type = new_ibkr
            logger.info(f"[DUAL_CONN] ✅ Switched to {new_ibkr}")
        else:
            logger.warning(f"[DUAL_CONN] ⚠️ Failed to switch to {new_ibkr}: {result.get('error')}")
        
        return result
    
    async def _disconnect_current_ibkr(self):
        """Disconnect the currently connected IBKR account"""
        try:
            from app.psfalgo.ibkr_connector import get_ibkr_connector
            
            if self._active_ibkr_type == "IBKR_PED":
                connector = get_ibkr_connector("IBKR_PED", create_if_missing=False)
                if connector and connector.is_connected():
                    await connector.disconnect()
                    logger.info("[DUAL_CONN] Disconnected IBKR_PED")
                self._ibkr_ped_status = ConnectionStatus.DISCONNECTED
                
            elif self._active_ibkr_type == "IBKR_GUN":
                connector = get_ibkr_connector("IBKR_GUN", create_if_missing=False)
                if connector and connector.is_connected():
                    await connector.disconnect()
                    logger.info("[DUAL_CONN] Disconnected IBKR_GUN")
                self._ibkr_gun_status = ConnectionStatus.DISCONNECTED
            
            self._active_ibkr_type = None
            
        except Exception as e:
            logger.error(f"[DUAL_CONN] Error disconnecting IBKR: {e}")
    
    async def _connect_ibkr_ped(self) -> Dict[str, Any]:
        """Connect to IBKR PED account"""
        try:
            self._ibkr_ped_status = ConnectionStatus.CONNECTING
            logger.info("[DUAL_CONN] Connecting to IBKR_PED...")
            
            from app.psfalgo.ibkr_connector import connect_isolated_sync
            
            # Use isolated sync connection in executor
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: connect_isolated_sync(
                    account_type='IBKR_PED',
                    host='127.0.0.1',
                    port=None,  # Auto-detect (4001, 7497, etc.)
                    client_id=21  # Unique client ID for PED
                )
            )
            
            if result and result.get('success'):
                self._ibkr_ped_status = ConnectionStatus.CONNECTED
                self._ibkr_ped_error = None
                self._active_ibkr_type = "IBKR_PED"
                logger.info("[DUAL_CONN] ✅ IBKR_PED connected successfully")
                return {'success': True, 'connected': True, 'account': 'IBKR_PED'}
            else:
                error_msg = result.get('error', 'Unknown error') if result else 'No result returned'
                self._ibkr_ped_status = ConnectionStatus.ERROR
                self._ibkr_ped_error = error_msg
                logger.warning(f"[DUAL_CONN] ⚠️ IBKR_PED connection failed: {error_msg}")
                return {'success': False, 'connected': False, 'error': error_msg}
                
        except Exception as e:
            self._ibkr_ped_status = ConnectionStatus.ERROR
            self._ibkr_ped_error = str(e)
            logger.error(f"[DUAL_CONN] ❌ IBKR_PED connection error: {e}", exc_info=True)
            return {'success': False, 'connected': False, 'error': str(e)}
    
    async def _connect_ibkr_gun(self) -> Dict[str, Any]:
        """Connect to IBKR GUN account"""
        try:
            self._ibkr_gun_status = ConnectionStatus.CONNECTING
            logger.info("[DUAL_CONN] Connecting to IBKR_GUN...")
            
            from app.psfalgo.ibkr_connector import connect_isolated_sync
            
            # Use isolated sync connection in executor
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: connect_isolated_sync(
                    account_type='IBKR_GUN',
                    host='127.0.0.1',
                    port=None,  # Auto-detect (4001, 7497, etc.)
                    client_id=19  # Unique client ID for GUN
                )
            )
            
            if result and result.get('success'):
                self._ibkr_gun_status = ConnectionStatus.CONNECTED
                self._ibkr_gun_error = None
                self._active_ibkr_type = "IBKR_GUN"
                logger.info("[DUAL_CONN] ✅ IBKR_GUN connected successfully")
                return {'success': True, 'connected': True, 'account': 'IBKR_GUN'}
            else:
                error_msg = result.get('error', 'Unknown error') if result else 'No result returned'
                self._ibkr_gun_status = ConnectionStatus.ERROR
                self._ibkr_gun_error = error_msg
                logger.warning(f"[DUAL_CONN] ⚠️ IBKR_GUN connection failed: {error_msg}")
                return {'success': False, 'connected': False, 'error': error_msg}
                
        except Exception as e:
            self._ibkr_gun_status = ConnectionStatus.ERROR
            self._ibkr_gun_error = str(e)
            logger.error(f"[DUAL_CONN] ❌ IBKR_GUN connection error: {e}", exc_info=True)
            return {'success': False, 'connected': False, 'error': str(e)}
    
    async def _connect_hammer_pro(self) -> Dict[str, Any]:
        """Connect to HAMMER PRO account"""
        try:
            self._hammer_status = ConnectionStatus.CONNECTING
            logger.info("[DUAL_CONN] Connecting to HAMMER_PRO...")
            
            from app.api.market_data_routes import get_hammer_client
            
            hammer_client = get_hammer_client()
            if not hammer_client:
                error_msg = "Hammer client not initialized"
                self._hammer_status = ConnectionStatus.ERROR
                self._hammer_error = error_msg
                logger.warning(f"[DUAL_CONN] ⚠️ HAMMER_PRO: {error_msg}")
                return {'success': False, 'connected': False, 'error': error_msg}
            
            # Check if already connected (from startup)
            if hammer_client.is_connected() and hammer_client.is_authenticated():
                self._hammer_status = ConnectionStatus.CONNECTED
                self._hammer_error = None
                logger.info("[DUAL_CONN] ✅ HAMMER_PRO already connected")
                return {'success': True, 'connected': True, 'account': 'HAMMER_PRO', 'already_connected': True}
            
            # Connect if not already connected
            loop = asyncio.get_running_loop()
            connected = await loop.run_in_executor(None, hammer_client.connect)
            
            if connected:
                # Wait for authentication
                await asyncio.sleep(2)
                
                if hammer_client.is_authenticated():
                    self._hammer_status = ConnectionStatus.CONNECTED
                    self._hammer_error = None
                    logger.info("[DUAL_CONN] ✅ HAMMER_PRO connected successfully")
                    return {'success': True, 'connected': True, 'account': 'HAMMER_PRO'}
                else:
                    error_msg = "Authentication failed"
                    self._hammer_status = ConnectionStatus.ERROR
                    self._hammer_error = error_msg
                    logger.warning(f"[DUAL_CONN] ⚠️ HAMMER_PRO: {error_msg}")
                    return {'success': False, 'connected': False, 'error': error_msg}
            else:
                error_msg = "Connection failed"
                self._hammer_status = ConnectionStatus.ERROR
                self._hammer_error = error_msg
                logger.warning(f"[DUAL_CONN] ⚠️ HAMMER_PRO: {error_msg}")
                return {'success': False, 'connected': False, 'error': error_msg}
                
        except Exception as e:
            self._hammer_status = ConnectionStatus.ERROR
            self._hammer_error = str(e)
            logger.error(f"[DUAL_CONN] ❌ HAMMER_PRO connection error: {e}", exc_info=True)
            return {'success': False, 'connected': False, 'error': str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get connection status for all accounts.
        
        Returns:
            Dict with status for each account
        """
        return {
            'active_ibkr': self._active_ibkr_type,
            'ibkr_ped': {
                'status': self._ibkr_ped_status.value,
                'connected': self._ibkr_ped_status == ConnectionStatus.CONNECTED,
                'error': self._ibkr_ped_error
            },
            'ibkr_gun': {
                'status': self._ibkr_gun_status.value,
                'connected': self._ibkr_gun_status == ConnectionStatus.CONNECTED,
                'error': self._ibkr_gun_error
            },
            'hammer_pro': {
                'status': self._hammer_status.value,
                'connected': self._hammer_status == ConnectionStatus.CONNECTED,
                'error': self._hammer_error
            }
        }
    
    def is_account_connected(self, account: str) -> bool:
        """
        Check if specific account is connected.
        
        Args:
            account: Account name (IBKR_PED, IBKR_GUN, HAMMER_PRO)
        
        Returns:
            True if connected, False otherwise
        """
        if account == 'IBKR_PED':
            return self._ibkr_ped_status == ConnectionStatus.CONNECTED
        elif account == 'IBKR_GUN':
            return self._ibkr_gun_status == ConnectionStatus.CONNECTED
        elif account in ['HAMMER_PRO', 'HAMPRO']:
            return self._hammer_status == ConnectionStatus.CONNECTED
        return False
    
    def get_active_ibkr(self) -> Optional[str]:
        """Get currently connected IBKR account type"""
        return self._active_ibkr_type


# Global instance
_dual_connection_manager: Optional[DualConnectionManager] = None


def get_dual_connection_manager() -> Optional[DualConnectionManager]:
    """Get global DualConnectionManager instance"""
    return _dual_connection_manager


def initialize_dual_connection_manager():
    """Initialize global DualConnectionManager instance"""
    global _dual_connection_manager
    _dual_connection_manager = DualConnectionManager()
    logger.info("[DUAL_CONN] DualConnectionManager initialized")
    return _dual_connection_manager
