"""
Account Mode Selector - Phase 10

Manages account mode selection (HAMMER_PRO, IBKR_GUN, IBKR_PED).
Provides unified position snapshot regardless of account source.

Key Principles:
- Market data ALWAYS from HAMMER
- IBKR is READ-ONLY (positions, orders, account summary)
- Execution ASLA yapılmayacak (HUMAN_ONLY)
- PositionSnapshot standardize edilir (account_type)
"""

from typing import Optional, Dict, Any
from enum import Enum
import asyncio

from app.core.logger import logger


class AccountMode(Enum):
    """Account mode"""
    HAMMER_PRO = "HAMMER_PRO"  # Hammer Pro account (default)
    IBKR_GUN = "IBKR_GUN"  # IBKR GUN account
    IBKR_PED = "IBKR_PED"  # IBKR PED account


class AccountModeManager:
    """
    Account Mode Manager - manages account mode selection.
    
    Responsibilities:
    - Manage current account mode
    - Provide account mode info
    - Validate account mode
    
    Does NOT:
    - Execute orders
    - Modify decision engines
    - Change dry_run mode
    """
    
    def __init__(self, initial_mode: str = "HAMMER_PRO"):
        """
        Initialize Account Mode Manager.
        
        Args:
            initial_mode: Initial account mode (default: HAMMER_PRO)
        """
        try:
            self.current_mode = AccountMode(initial_mode)
        except ValueError:
            logger.warning(f"Invalid account mode: {initial_mode}, defaulting to HAMMER_PRO")
            self.current_mode = AccountMode.HAMMER_PRO
        
        logger.info(f"AccountModeManager initialized (mode={self.current_mode.value})")
    
    async def set_mode(self, mode: str, auto_connect: bool = True) -> Dict[str, Any]:
        """
        Set account mode (PHASE 11: Persistent Dual Connections).
        
        IMPORTANT: Connections are PERSISTENT - this method ONLY changes the active account flag.
        NO disconnections occur. All accounts remain connected.
        
        Args:
            mode: Account mode (HAMMER_PRO, IBKR_GUN, IBKR_PED)
            auto_connect: Ignored (kept for API compatibility) - connections are persistent
            
        Returns:
            Result dict with connection status
        """
        try:
            new_mode = AccountMode(mode)
            old_mode = self.current_mode
            
            # Update mode
            self.current_mode = new_mode
            
            logger.info(f"[ACCOUNT_MODE] Switching from {old_mode.value} to {new_mode.value} (persistent connections)")
            
            result = {
                'success': True,
                'old_mode': old_mode.value,
                'new_mode': new_mode.value
            }
            
            # PHASE 11: ONLY update Redis active account flag - NO connection changes
            from app.psfalgo.ibkr_connector import set_active_ibkr_account
            from app.core.redis_client import get_redis_client
            import json
            
            try:
                r = get_redis_client()
                if not r or not getattr(r, 'sync', None):
                    logger.warning("[ACCOUNT_MODE] Redis not available - cannot save mode")
                    return {'success': False, 'error': 'Redis not available'}
                
                if new_mode == AccountMode.HAMMER_PRO:
                    # Switch to HAMMER_PRO (IBKR connections remain active)
                    set_active_ibkr_account(None)  # Clear IBKR active flag
                    r.sync.set("psfalgo:recovery:account_open", "HAMPRO")
                    r.sync.set("psfalgo:account_mode", json.dumps({"mode": "HAMMER_PRO"}))
                    r.sync.set("psfalgo:trading:account_mode", "HAMPRO")
                    logger.info("[ACCOUNT_MODE] ✅ Switched to HAMMER_PRO (IBKR connections remain active)")
                    
                elif new_mode in [AccountMode.IBKR_GUN, AccountMode.IBKR_PED]:
                    # Switch to IBKR account (HAMMER connection remains active)
                    from app.psfalgo.ibkr_connector import get_ibkr_connector
                    connector = get_ibkr_connector(account_type=new_mode.value, create_if_missing=False)
                    
                    # If connector not found or not connected, try auto-connect via DualConnectionManager
                    if not connector or not connector.is_connected():
                        logger.info(f"[ACCOUNT_MODE] {new_mode.value} not connected, attempting auto-connect via DualConnectionManager...")
                        try:
                            from app.psfalgo.dual_connection_manager import get_dual_connection_manager
                            dual_mgr = get_dual_connection_manager()
                            if dual_mgr:
                                switch_result = await dual_mgr.switch_ibkr_account(new_mode.value)
                                if switch_result and switch_result.get('connected'):
                                    logger.info(f"[ACCOUNT_MODE] ✅ Auto-connected {new_mode.value} via DualConnectionManager")
                                    # Re-fetch connector after connection
                                    connector = get_ibkr_connector(account_type=new_mode.value, create_if_missing=False)
                                else:
                                    error_msg = switch_result.get('error', 'Unknown error') if switch_result else 'No result'
                                    logger.error(f"[ACCOUNT_MODE] ❌ Auto-connect failed for {new_mode.value}: {error_msg}")
                                    self.current_mode = old_mode  # Revert mode
                                    return {'success': False, 'error': f'{new_mode.value} bağlantısı kurulamadı: {error_msg}', 'connection_error': error_msg}
                            else:
                                # Fallback: try connect_isolated_sync directly
                                from app.psfalgo.ibkr_connector import connect_isolated_sync
                                loop = asyncio.get_running_loop()
                                sync_result = await loop.run_in_executor(None, lambda: connect_isolated_sync(account_type=new_mode.value))
                                if sync_result and sync_result.get('success'):
                                    connector = get_ibkr_connector(account_type=new_mode.value, create_if_missing=False)
                                else:
                                    error_msg = sync_result.get('error', 'Unknown error') if sync_result else 'No result'
                                    self.current_mode = old_mode  # Revert mode
                                    return {'success': False, 'error': f'{new_mode.value} bağlantısı kurulamadı: {error_msg}', 'connection_error': error_msg}
                        except Exception as auto_conn_err:
                            logger.error(f"[ACCOUNT_MODE] ❌ Auto-connect exception: {auto_conn_err}", exc_info=True)
                            self.current_mode = old_mode  # Revert mode
                            return {'success': False, 'error': f'{new_mode.value} auto-connect failed: {str(auto_conn_err)}', 'connection_error': str(auto_conn_err)}
                    
                    # Final check - connector must be connected now
                    if not connector or not connector.is_connected():
                        logger.error(f"[ACCOUNT_MODE] ❌ {new_mode.value} still not connected after auto-connect attempt")
                        self.current_mode = old_mode  # Revert mode
                        return {'success': False, 'error': f'{new_mode.value} IBKR bağlı değil! IBKR Gateway/TWS çalışıyor mu kontrol edin.'}
                    
                    # IBKR is connected - proceed with mode switch
                    set_active_ibkr_account(new_mode.value)
                    r.sync.set("psfalgo:recovery:account_open", new_mode.value)
                    r.sync.set("psfalgo:account_mode", json.dumps({"mode": new_mode.value}))
                    r.sync.set("psfalgo:trading:account_mode", new_mode.value)
                    logger.info(f"[ACCOUNT_MODE] ✅ Switched to {new_mode.value} (IBKR connected, HAMMER remains active)")
                    result['connected'] = True
                
                # CRITICAL: Immediately fetch and save positions to Redis for terminals
                async def save_positions_to_redis():
                    try:
                        await asyncio.sleep(0.5)  # Short delay
                        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
                        pos_api = get_position_snapshot_api()
                        if pos_api:
                            account_id = "HAMPRO" if new_mode == AccountMode.HAMMER_PRO else new_mode.value
                            snapshots = await pos_api.get_position_snapshot(account_id=account_id)
                            logger.info(f"[ACCOUNT_MODE] ✅ Saved {len(snapshots)} positions to Redis for {account_id}")
                    except Exception as e:
                        logger.warning(f"[ACCOUNT_MODE] Failed to save positions to Redis: {e}")
                
                # Fire and forget - don't wait
                asyncio.create_task(save_positions_to_redis())
                
            except Exception as redis_err:
                logger.error(f"[ACCOUNT_MODE] Failed to update Redis: {redis_err}")
                return {'success': False, 'error': f'Failed to update Redis: {str(redis_err)}'}
            
            return result
            
        except ValueError as e:
            logger.error(f"[ACCOUNT_MODE] Invalid account mode: {mode}", exc_info=True)
            return {
                'success': False,
                'error': f'Invalid account mode: {mode}. Valid modes: HAMMER_PRO, IBKR_GUN, IBKR_PED'
            }
        except Exception as e:
            logger.error(f"[ACCOUNT_MODE] Error setting account mode: {e}", exc_info=True)
            return {
                'success': False,
                'error': f'Failed to set account mode: {str(e)}'
            }
    
    def get_mode(self) -> str:
        """Get current account mode"""
        return self.current_mode.value
    
    def is_hammer(self) -> bool:
        """Check if current mode is HAMMER_PRO"""
        return self.current_mode == AccountMode.HAMMER_PRO
    
    def is_ibkr_gun(self) -> bool:
        """Check if current mode is IBKR_GUN"""
        return self.current_mode == AccountMode.IBKR_GUN
    
    def is_ibkr_ped(self) -> bool:
        """Check if current mode is IBKR_PED"""
        return self.current_mode == AccountMode.IBKR_PED
    
    def is_ibkr(self) -> bool:
        """Check if current mode is any IBKR account"""
        return self.current_mode in [AccountMode.IBKR_GUN, AccountMode.IBKR_PED]
    
    def get_account_type(self) -> str:
        """
        Get account type for PositionSnapshot.
        Syncs with global TradingAccountContext for cross-process consistency.
        
        Returns:
            Account type string (HAMMER_PRO, IBKR_GUN, IBKR_PED)
        """
        from app.trading.trading_account_context import get_trading_context
        context = get_trading_context()
        mode = context.trading_mode.value
        
        # Map HAMPRO to HAMMER_PRO (AccountMode enum uses HAMMER_PRO)
        if mode == "HAMPRO":
            return "HAMMER_PRO"
        return mode


# Global instance
_account_mode_manager: Optional[AccountModeManager] = None


def get_account_mode_manager() -> Optional[AccountModeManager]:
    """Get global AccountModeManager instance"""
    return _account_mode_manager


def initialize_account_mode_manager(initial_mode: str = "HAMMER_PRO"):
    """Initialize global AccountModeManager instance"""
    global _account_mode_manager
    _account_mode_manager = AccountModeManager(initial_mode=initial_mode)
    logger.info(f"AccountModeManager initialized (mode={initial_mode})")

