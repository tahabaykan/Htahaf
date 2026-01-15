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
        Set account mode and optionally auto-connect/disconnect.
        
        PHASE 10.1: Auto-connect IBKR when mode is IBKR_GUN or IBKR_PED.
        Auto-disconnect IBKR when mode is HAMMER_PRO.
        
        Args:
            mode: Account mode (HAMMER_PRO, IBKR_GUN, IBKR_PED)
            auto_connect: Auto-connect IBKR if mode is IBKR (default: True)
            
        Returns:
            Result dict with connection status
        """
        try:
            new_mode = AccountMode(mode)
            old_mode = self.current_mode
            self.current_mode = new_mode
            
            logger.info(f"[ACCOUNT_MODE] Changed from {old_mode.value} to {new_mode.value}")
            
            result = {
                'success': True,
                'old_mode': old_mode.value,
                'new_mode': new_mode.value
            }
            
            # PHASE 10.1: Auto-connect/disconnect
            if auto_connect:
                if new_mode == AccountMode.HAMMER_PRO:
                    # Disconnect IBKR if switching to HAMMER
                    if old_mode in [AccountMode.IBKR_GUN, AccountMode.IBKR_PED]:
                        from app.psfalgo.ibkr_connector import get_ibkr_connector
                        old_connector = get_ibkr_connector(account_type=old_mode.value)
                        if old_connector and old_connector.is_connected():
                            await old_connector.disconnect()
                            logger.info(f"[ACCOUNT_MODE] Disconnected from {old_mode.value}")
                            result['disconnected'] = old_mode.value
                
                elif new_mode in [AccountMode.IBKR_GUN, AccountMode.IBKR_PED]:
                    # Auto-connect to IBKR
                    from app.psfalgo.ibkr_connector import get_ibkr_connector
                    
                    connector = get_ibkr_connector(account_type=new_mode.value)
                    if connector and not connector.is_connected():
                        # PHASE 10.1: Same port for both GUN and PED (like Janall)
                        # Default: 4001 (Gateway) or 7497 (TWS)
                        # Account distinction is done via account field, not port
                        port = 4001  # Default Gateway port (same for both)
                        # Different client_id per account type to avoid conflicts
                        client_id = 19 if new_mode == AccountMode.IBKR_GUN else 21
                        
                        connect_result = await connector.connect(
                            host='127.0.0.1',
                            port=port,
                            client_id=client_id
                        )
                        
                        if connect_result.get('success'):
                            logger.info(f"[ACCOUNT_MODE] Auto-connected to {new_mode.value}")
                            result['connected'] = True
                            result['connection_info'] = connect_result
                            
                            # Auto-track BEFDAY positions when account mode changes to IBKR (günde 1 kere)
                            async def auto_track_befday_on_mode_change():
                                """Auto-track BEFDAY positions when switching to IBKR mode (once per day)"""
                                try:
                                    await asyncio.sleep(2)  # Wait for connection to stabilize
                                    
                                    from app.psfalgo.befday_tracker import get_befday_tracker, track_befday_positions
                                    
                                    tracker = get_befday_tracker()
                                    if not tracker:
                                        logger.warning("[BEFDAY] Tracker not initialized, skipping auto-track")
                                        return
                                    
                                    # Determine mode based on account_type
                                    mode = 'ibkr_gun' if new_mode == AccountMode.IBKR_GUN else 'ibkr_ped'
                                    
                                    # Check if should track
                                    should_track, reason = tracker.should_track(mode=mode)
                                    if not should_track:
                                        logger.info(f"[BEFDAY] Skipping auto-track for {new_mode.value}: {reason}")
                                        return
                                    
                                    # Get positions from IBKR
                                    positions = await connector.get_positions()
                                    if positions:
                                        success = await track_befday_positions(
                                            positions=positions,
                                            mode=mode,
                                            account=new_mode.value
                                        )
                                        if success:
                                            logger.info(f"[BEFDAY] ✅ Auto-tracked {len(positions)} {new_mode.value} positions (befibgun.csv or befibped.csv)")
                                        else:
                                            logger.warning(f"[BEFDAY] Auto-track failed for {new_mode.value}")
                                    else:
                                        logger.info(f"[BEFDAY] No positions to track for {new_mode.value}")
                                except Exception as e:
                                    logger.error(f"[BEFDAY] Error in auto-track for {new_mode.value}: {e}", exc_info=True)
                            
                            # Schedule auto-track after a delay
                            try:
                                loop = asyncio.get_event_loop()
                                loop.create_task(auto_track_befday_on_mode_change())
                            except RuntimeError:
                                # No event loop, create one
                                asyncio.run(auto_track_befday_on_mode_change())
                        else:
                            logger.warning(f"[ACCOUNT_MODE] Auto-connect failed: {connect_result.get('error')}")
                            result['connected'] = False
                            result['connection_error'] = connect_result.get('error')
                    elif connector and connector.is_connected():
                        result['connected'] = True
                        result['already_connected'] = True
                        
                        # Even if already connected, check if we should track BEFDAY (günde 1 kere)
                        async def auto_track_befday_if_needed():
                            """Auto-track BEFDAY positions if already connected (once per day)"""
                            try:
                                from app.psfalgo.befday_tracker import get_befday_tracker, track_befday_positions
                                
                                tracker = get_befday_tracker()
                                if not tracker:
                                    return
                                
                                # Determine mode based on account_type
                                mode = 'ibkr_gun' if new_mode == AccountMode.IBKR_GUN else 'ibkr_ped'
                                
                                # Check if should track
                                should_track, reason = tracker.should_track(mode=mode)
                                if not should_track:
                                    logger.debug(f"[BEFDAY] Skipping auto-track for {new_mode.value}: {reason}")
                                    return
                                
                                # Get positions from IBKR
                                positions = await connector.get_positions()
                                if positions:
                                    success = await track_befday_positions(
                                        positions=positions,
                                        mode=mode,
                                        account=new_mode.value
                                    )
                                    if success:
                                        logger.info(f"[BEFDAY] ✅ Auto-tracked {len(positions)} {new_mode.value} positions (already connected)")
                            except Exception as e:
                                logger.debug(f"[BEFDAY] Error in auto-track for {new_mode.value}: {e}")
                        
                        # Schedule auto-track
                        try:
                            loop = asyncio.get_event_loop()
                            loop.create_task(auto_track_befday_if_needed())
                        except RuntimeError:
                            pass
            
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
        
        Returns:
            Account type string (HAMMER_PRO, IBKR_GUN, IBKR_PED)
        """
        return self.current_mode.value


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

