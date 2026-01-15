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
    
    Body:
        {
            "mode": "HAMMER_TRADING" | "IBKR_TRADING"
        }
    
    Returns:
        Success status and updated mode
    """
    try:
        trading_context = get_trading_context()
        
        mode_str = data.get("mode")
        if not mode_str:
            raise HTTPException(status_code=400, detail="mode field is required")
        
        # Validate mode string
        try:
            mode = TradingAccountMode(mode_str)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid trading mode: {mode_str}. Must be HAMMER_TRADING or IBKR_TRADING"
            )
        
        # Set mode (validation happens inside)
        success = trading_context.set_trading_mode(mode)
        
        if not success:
            status = trading_context.get_status()
            raise HTTPException(
                status_code=400,
                detail=f"Cannot switch to {mode_str}. Check connection status."
            )
        
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
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        
        ctx = get_trading_context()
        active_account = ctx.trading_mode.value
        
        pos_api = get_position_snapshot_api()
        if not pos_api:
            raise HTTPException(status_code=503, detail="PositionSnapshotAPI not initialized")
        
        # Get snapshots (include zero positions to safe check, or false?)
        # For UI, usually we want non-zero.
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
        # PHASE 10: Check account mode - IBKR or HAMMER
        from app.psfalgo.account_mode import get_account_mode_manager
        
        account_mode_manager = get_account_mode_manager()
        orders = []
        
        if account_mode_manager and account_mode_manager.is_ibkr():
            # IBKR mode: Get orders from IBKR
            from app.psfalgo.ibkr_connector import get_ibkr_connector
            
            account_type = account_mode_manager.get_account_type()
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
        else:
            # HAMMER mode: Get orders from Hammer
            orders_service = get_hammer_orders_service()
            if orders_service:
                orders = orders_service.get_orders(force_refresh=False)
                logger.info(f"Fetched {len(orders)} open orders from Hammer")
            else:
                logger.warning("Hammer orders service not initialized")
        
        # Get account mode for response
        account_type = account_mode_manager.get_account_type() if account_mode_manager else "HAMMER_PRO"
        
        return {
            "success": True,
            "account_mode": account_type,
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
    
    Returns:
        Exposure data (filtered by current trading_mode)
        - long_exposure: sum of (quantity * avg_price) for LONG positions
        - short_exposure: sum of (quantity * avg_price) for SHORT positions
        - total_exposure: abs(long_exposure) + abs(short_exposure)
        - net_exposure: long_exposure + short_exposure
    """
    try:
        trading_context = get_trading_context()
        trading_mode = trading_context.trading_mode
        
        # Fetch positions
        positions = []
        if trading_mode == TradingAccountMode.HAMMER_TRADING:
            positions_service = get_hammer_positions_service()
            if positions_service:
                positions = positions_service.get_positions(force_refresh=False)
            else:
                logger.warning("Hammer positions service not initialized")
        elif trading_mode == TradingAccountMode.IBKR_TRADING:
            # IBKR not implemented yet
            positions = []
        
        # Calculate exposure
        long_exposure = 0.0
        short_exposure = 0.0
        
        for pos in positions:
            side = pos.get('side', '').upper()
            quantity = float(pos.get('quantity', 0) or 0)
            avg_price = float(pos.get('avg_price', 0) or 0)
            
            if side == 'LONG' and quantity > 0 and avg_price > 0:
                long_exposure += quantity * avg_price
            elif side == 'SHORT' and quantity > 0 and avg_price > 0:
                short_exposure += quantity * avg_price
        
        # Total exposure = abs(long) + abs(short)
        total_exposure = abs(long_exposure) + abs(short_exposure)
        
        # Net exposure = long - short (short is negative)
        net_exposure = long_exposure - short_exposure
        
        exposure = {
            "total_exposure": round(total_exposure, 2),
            "long_exposure": round(long_exposure, 2),
            "short_exposure": round(short_exposure, 2),
            "net_exposure": round(net_exposure, 2),
            "position_count": len(positions)
        }
        
        return {
            "success": True,
            "trading_mode": trading_mode.value,
            "exposure": exposure
        }
    except Exception as e:
        logger.error(f"Error getting exposure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

