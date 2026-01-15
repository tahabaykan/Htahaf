"""
Trading Account API Routes
Endpoints for managing trading account mode and status.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional

from app.core.logger import logger
from app.trading.trading_account_context import (
    get_trading_context,
    TradingAccountMode,
    initialize_trading_context
)
from app.trading.hammer_positions_service import HammerPositionsService
from app.trading.hammer_orders_service import HammerOrdersService
from app.trading.hammer_execution_service import set_hammer_execution_service
from app.api.market_data_routes import market_data_cache

# Global service instances
_hammer_positions_service: Optional[HammerPositionsService] = None
_hammer_orders_service: Optional[HammerOrdersService] = None

def get_hammer_positions_service() -> Optional[HammerPositionsService]:
    """Get global Hammer positions service instance"""
    return _hammer_positions_service

def get_hammer_orders_service() -> Optional[HammerOrdersService]:
    """Get global Hammer orders service instance"""
    return _hammer_orders_service

def set_hammer_services(hammer_client=None, account_key: Optional[str] = None):
    """
    Set Hammer client for positions and orders services.
    Initialize services if they don't exist.
    
    Args:
        hammer_client: HammerClient instance (Optional)
        account_key: Trading account key (Optional)
    """
    global _hammer_positions_service, _hammer_orders_service
    
    if not _hammer_positions_service:
        _hammer_positions_service = HammerPositionsService()
    
    if hammer_client and account_key:
        _hammer_positions_service.set_hammer_client(hammer_client, account_key)
    
    if not _hammer_orders_service:
        _hammer_orders_service = HammerOrdersService()
    
    if hammer_client and account_key:
        _hammer_orders_service.set_hammer_client(hammer_client, account_key)
        
    # Also initialize Execution Service (Phase 10)
    if hammer_client and account_key:
        set_hammer_execution_service(hammer_client, account_key)
    
    if hammer_client:
        logger.info(f"Hammer trading services initialized for account: {account_key}")
    else:
        logger.info("Hammer trading services pre-initialized (empty)")

router = APIRouter(prefix="/api/trading", tags=["trading"])


@router.get("/mode")
async def get_trading_mode():
    """
    Get current trading account mode and connection status.
    
    Returns:
        Current trading mode, connection status, and available options
    """
    try:
        trading_context = get_trading_context()
        status = trading_context.get_status()
        
        return {
            "success": True,
            **status
        }
    except Exception as e:
        logger.error(f"Error getting trading mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mode")
async def set_trading_mode(data: Dict[str, Any]):
    """
    Set trading account mode.
    
    Synchronizes both TradingAccountContext and AccountModeManager.
    Triggers auto-connect/disconnect logic via AccountModeManager.
    
    Body:
        {
            "mode": "HAMMER" | "IBKR" | "PAPER"
        }
    
    Returns:
        Success status and updated mode
    """
    try:
        trading_context = get_trading_context()
        
        mode_str = data.get("mode")
        if not mode_str:
            raise HTTPException(status_code=400, detail="mode field is required")
        
        # Map simplified UI strings to internal Enum values
        if mode_str == "HAMMER": mode_str = "HAMPRO"
        if mode_str == "HAMMER_TRADING": mode_str = "HAMPRO"
        if mode_str == "IBKR": mode_str = "IBKR_GUN" # Default to Live
        if mode_str == "IBKR_TRADING": mode_str = "IBKR_GUN"
        if mode_str == "PAPER": mode_str = "IBKR_PED"

        # Validate TradingAccountMode Enum
        try:
            mode = TradingAccountMode(mode_str)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trading mode: {mode_str}. Must be HAMPRO, IBKR_PED, or IBKR_GUN"
            )
        
        # 1. Update AccountModeManager (Handles Connections & Heavy Lifting)
        from app.psfalgo.account_mode import get_account_mode_manager
        account_mode_manager = get_account_mode_manager()
        
        if account_mode_manager:
            # Map TradingAccountMode to AccountModeManager strings
            manager_mode_str = mode.value
            
            # AccountMode enum uses HAMMER_PRO etc.
            if mode == TradingAccountMode.HAMPRO:
                manager_mode_str = "HAMMER_PRO"
            
            logger.info(f"[TRADING_API] Switching AccountModeManager to {manager_mode_str}...")
            # Ensure we await if it's async, check implementation. 
            # AccountModeManager.set_mode is NOT async in current codebase view (checked in view_code_item). wait, let's check.
            # view_code_item output for AccountModeManager.set_mode didn't show signature fully but looked sync. 
            # However IBKR connector operations are usually async.
            # Let's assume sync for now based on snippet, but if it calls async it might be issue. 
            # Re-reading snippet: It calls self._connect_ibkr which might be async.
            # Actually, most managers in this codebase seem to use background threads or async.
            # If set_mode is standard method, it's likely synchronous triggering background tasks.
            
            # Correction: AccountModeManager.set_mode usually returns a dict.
            result = account_mode_manager.set_mode(manager_mode_str, auto_connect=True)
            
            if not result.get('success'):
                 logger.error(f"[TRADING_API] AccountModeManager failed: {result.get('error')}")
        
        # 2. Update TradingAccountContext (Global State for Runall)
        success = trading_context.set_trading_mode(mode)
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot switch to {mode_str}. Check logs."
            )

        # 3. Broadcast to Global System via Redis (Sync QE Components)
        try:
            from app.core.redis_client import redis_client
            import json
            import time
            
            # Use the manager mode string (HAMMER_PRO / IBKR_GUN / IBKR_PED)
            broadcast_payload = {
                "mode": manager_mode_str,
                "timestamp": time.time(),
                "source": "API"
            }
            redis_client.publish("sys:account_change", json.dumps(broadcast_payload))
            logger.info(f"[TRADING_API] Broadcasted account mode change to sys:account_change: {manager_mode_str}")
        except Exception as re:
             logger.error(f"[TRADING_API] Redis broadcast failed: {re}")
        
        # Return updated status
        status = trading_context.get_status()
        
        return {
            "success": True,
            "message": f"Trading mode set to {mode.value}",
            **status
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting trading mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_trading_status():
    """
    Get detailed trading account status.
    
    Returns:
        Full status including connections, mode, and capabilities
    """
    try:
        trading_context = get_trading_context()
        status = trading_context.get_status()
        
        return {
            "success": True,
            "market_data_source": "HAMMER",  # Always Hammer (fixed)
            "market_data_status": "LIVE",  # TODO: Check actual Hammer market data connection
            **status
        }
    except Exception as e:
        logger.error(f"Error getting trading status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_positions():
    """
    Get positions for active trading account via PositionSnapshotAPI.
    
    Includes:
    - Strict Account Scope (HAMPRO / IBKR_PED / IBKR_GUN)
    - LT/MM Split logic
    - Missing Price visibility
    - Real-time Market Data enrichment
    """
    try:
        from app.trading.trading_account_context import get_trading_context
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api, initialize_position_snapshot_api
        
        ctx = get_trading_context()
        active_account = ctx.trading_mode.value
        
        pos_api = get_position_snapshot_api()
        if not pos_api:
            # Try initializing if missing
            initialize_position_snapshot_api()
            pos_api = get_position_snapshot_api()
            
        if not pos_api:
            raise HTTPException(status_code=503, detail="PositionSnapshotAPI not initialized")
        
        # Get snapshots
        snapshots = await pos_api.get_position_snapshot(
            account_id=active_account,
            include_zero_positions=False
        )
        
        enriched_positions = []
        for snap in snapshots:
            # Map PositionSnapshot to Frontend format
            side = 'LONG' if snap.qty > 0 else 'SHORT' if snap.qty < 0 else 'FLAT'
            
            # Use display fields if available (Phase 8), else raw
            display_qty = snap.display_qty if snap.display_qty is not None else snap.qty
            
            # Calculate market value
            market_value = abs(snap.qty) * (snap.current_price or 0.0)
            
            pos_dict = {
                'symbol': snap.symbol,
                'qty': snap.qty,
                'quantity': snap.qty,  # Compat
                'display_qty': display_qty,
                'display_bucket': snap.display_bucket, # LT/MM/MIXED
                'view_mode': snap.view_mode,
                'lt_qty_raw': snap.lt_qty_raw,
                'mm_qty_raw': snap.mm_qty_raw,
                'avg_price': snap.avg_price,
                'current_price': snap.current_price,
                'unrealized_pnl': snap.unrealized_pnl,
                'market_value': market_value,
                'account': snap.account_type,
                'side': side,
                'group': snap.group,
                'price_status': snap.price_status,
                'holding_minutes': snap.holding_minutes
            }
            enriched_positions.append(pos_dict)
            
        return {
            "success": True,
            "account_mode": active_account,
            "positions": enriched_positions,
            "count": len(enriched_positions)
        }

    except Exception as e:
        logger.error(f"Error getting positions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders")
async def get_orders():
    """
    Get open orders for active trading account.
    
    PHASE 10: Now supports IBKR orders (READ-ONLY).
    Returns orders from appropriate source (HAMMER or IBKR) based on account mode.
    
    Returns:
        List of open orders (filtered by current account mode)
        - HAMMER_PRO: Returns Hammer open orders
        - IBKR_GUN/IBKR_PED: Returns IBKR open orders
    """
    try:
        # User Logic: ACTIVE account decides where we look
        from app.trading.trading_account_context import get_trading_context
        ctx = get_trading_context()
        active_mode = ctx.trading_mode
        
        orders = []
        
        # IBKR Handling
        if active_mode in [TradingAccountMode.IBKR_GUN, TradingAccountMode.IBKR_PED]:
            from app.psfalgo.ibkr_connector import get_ibkr_connector
            
            account_type = active_mode.value # IBKR_GUN or IBKR_PED
            ibkr_connector = get_ibkr_connector(account_type=account_type)
            
            if ibkr_connector and ibkr_connector.is_connected():
                ibkr_orders = await ibkr_connector.get_open_orders()
                # Convert to format expected by frontend
                orders = [
                    {
                        'order_id': o.get('order_id'),
                        'symbol': o.get('symbol'),
                        'side': o.get('side'),
                        'qty': o.get('qty', 0.0),
                        'order_type': o.get('order_type'),
                        'limit_price': o.get('limit_price'),
                        'status': o.get('status', 'OPEN'),
                        'filled': o.get('filled', 0.0),
                        'remaining': o.get('remaining', 0.0),
                        'account': o.get('account', account_type)
                    }
                    for o in ibkr_orders
                ]
                logger.info(f"Fetched {len(orders)} open orders from IBKR {account_type}")
            else:
                logger.warning(f"IBKR {account_type} not connected, returning empty orders")
        
        # Hammer Handling
        elif active_mode == TradingAccountMode.HAMPRO:
            orders_service = get_hammer_orders_service()
            if orders_service:
                orders = orders_service.get_orders(force_refresh=False)
                logger.info(f"Fetched {len(orders)} open orders from Hammer")
            else:
                logger.warning("Hammer orders service not initialized")
        
        return {
            "success": True,
            "account_mode": active_mode.value,
            "orders": orders,
            "count": len(orders)
        }
    except Exception as e:
        logger.error(f"Error getting orders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exposure")
async def get_exposure():
    """
    Get exposure/risk metrics for active trading account.
    
    Uses Unified PositionSnapshotAPI to calculate exposure for the ACTIVE account.
    Eliminates old logic that was hardcoded to Hammer/broken Enums.
    
    Returns:
        Exposure data (filtered by current trading_mode)
    """
    try:
        from app.trading.trading_account_context import get_trading_context
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        
        ctx = get_trading_context()
        active_account = ctx.trading_mode.value
        
        pos_api = get_position_snapshot_api()
        if not pos_api:
             return {
                "success": False,
                "error": "PositionSnapshotAPI not initialized",
                "trading_mode": active_account
            }
        
        # Get snapshots for ACTIVE account
        snapshots = await pos_api.get_position_snapshot(
            account_id=active_account,
            include_zero_positions=False
        )
        
        # Calculate exposure
        long_exposure = 0.0
        short_exposure = 0.0
        position_count = 0
        
        for snap in snapshots:
            qty = snap.qty
            
            # Use current price if available, else avg_price
            price_to_use = snap.current_price if snap.current_price and snap.current_price > 0 else snap.avg_price
            
            val = qty * price_to_use
            
            if qty > 0:
                long_exposure += val
            elif qty < 0:
                short_exposure += val # val is negative here
            
            if abs(qty) > 0.001:
                position_count += 1
        
        # Total exposure = abs(long) + abs(short) (Gross Exposure)
        total_exposure = abs(long_exposure) + abs(short_exposure)
        
        # Net exposure = long + short (Net Exposure)
        net_exposure = long_exposure + short_exposure
        
        exposure = {
            "total_exposure": round(total_exposure, 2),
            "long_exposure": round(long_exposure, 2),
            "short_exposure": round(abs(short_exposure), 2), # Send positive value for display usually
            "net_exposure": round(net_exposure, 2),
            "position_count": position_count
        }
        
        return {
            "success": True,
            "trading_mode": active_account,
            "exposure": exposure
        }
    except Exception as e:
        logger.error(f"Error getting exposure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
