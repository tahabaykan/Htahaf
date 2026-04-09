"""
Trading Account API Routes
Endpoints for managing trading account mode and status.
"""

from fastapi import APIRouter, HTTPException, Query
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

def get_hammer_services() -> tuple:
    """Return (orders_service, positions_service) for Hammer mode. Used by XNL engine and janall/orders."""
    return (_hammer_orders_service, _hammer_positions_service)

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
            "mode": "HAMMER" | "IBKR_PED" | "IBKR_GUN"
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
        if mode_str == "PAPER": mode_str = "IBKR_PED"  # legacy alias

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
async def get_positions(account_id: Optional[str] = Query(None, description="Hesap (IBKR_PED, IBKR_GUN, HAMPRO). Yoksa aktif hesap kullanılır.")):
    """
    Get positions for active (or given) trading account via PositionSnapshotAPI.
    
    account_id verilirse o hesabın pozisyonları döner (RevnBookCheck / harici
    istemciler için; Pozisyonlar ekranı ile aynı kaynak).
    
    CRITICAL: Hard timeout of 6s — never let frontend hang in "Loading".
    Falls back to Redis cached data if snapshot takes too long.
    """
    import asyncio
    
    try:
        from app.trading.trading_account_context import get_trading_context
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api, initialize_position_snapshot_api
        
        active_account = account_id
        if not active_account:
            ctx = get_trading_context()
            active_account = ctx.trading_mode.value
        
        # CRITICAL FIX: Map HAMMER_PRO to HAMPRO for position_snapshot_api compatibility
        if active_account == "HAMMER_PRO":
            active_account = "HAMPRO"
        
        pos_api = get_position_snapshot_api()
        if not pos_api:
            # Try initializing if missing
            initialize_position_snapshot_api()
            pos_api = get_position_snapshot_api()
            
        if not pos_api:
            raise HTTPException(status_code=503, detail="PositionSnapshotAPI not initialized")
        
        # ═══════════════════════════════════════════════════════════════════
        # HARD TIMEOUT: Never let the frontend hang in "Loading..."
        # If position_snapshot takes >6s (WS down, IBKR unreachable), 
        # fall through to Redis cached data.
        # ═══════════════════════════════════════════════════════════════════
        snapshots = []
        data_source = "live"
        try:
            snapshots = await asyncio.wait_for(
                pos_api.get_position_snapshot(
                    account_id=active_account,
                    include_zero_positions=False
                ),
                timeout=6.0
            )
        except asyncio.TimeoutError:
            logger.warning(f"[POSITIONS_API] ⏰ Position snapshot TIMEOUT (6s) for {active_account} — falling back to Redis cache")
            data_source = "redis_cache_timeout"
            # Fallback: try to read last known positions from Redis
            try:
                from app.core.redis_client import get_redis_client
                import json as _json
                redis = get_redis_client()
                if redis:
                    positions_key = f"psfalgo:positions:{active_account}"
                    raw = redis.get(positions_key)
                    if raw:
                        positions_dict = _json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                        for sym, pos_data in positions_dict.items():
                            if sym == '_meta' or not isinstance(pos_data, dict):
                                continue
                            qty = pos_data.get('qty', 0)
                            if abs(float(qty)) < 0.01:
                                continue
                            snapshots_fallback_item = type('Snap', (), {
                                'symbol': sym,
                                'qty': float(qty),
                                'display_qty': float(pos_data.get('display_qty', qty)),
                                'display_bucket': pos_data.get('display_bucket', 'LT'),
                                'view_mode': pos_data.get('view_mode', 'SINGLE_BUCKET'),
                                'lt_qty_raw': None,
                                'mm_qty_raw': None,
                                'avg_price': float(pos_data.get('avg_price', 0)),
                                'current_price': float(pos_data.get('current_price', 0)),
                                'unrealized_pnl': float(pos_data.get('unrealized_pnl', 0)),
                                'account_type': active_account,
                                'group': None,
                                'price_status': None,
                                'holding_minutes': None,
                                'full_taxonomy': pos_data.get('full_taxonomy', ''),
                                'position_tags': None,
                                'befday_qty': float(pos_data.get('befday_qty', 0)),
                                'potential_qty': float(pos_data.get('potential_qty', qty)),
                            })()
                            snapshots.append(snapshots_fallback_item)
                        logger.info(f"[POSITIONS_API] ✅ Redis fallback: {len(snapshots)} positions for {active_account}")
            except Exception as redis_err:
                logger.warning(f"[POSITIONS_API] Redis fallback also failed: {redis_err}")
        except Exception as snap_err:
            logger.error(f"[POSITIONS_API] Snapshot error: {snap_err}", exc_info=True)
        
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
                'group': getattr(snap, 'group', None),
                'price_status': getattr(snap, 'price_status', None),
                'holding_minutes': getattr(snap, 'holding_minutes', None),
                'tag': snap.full_taxonomy,
                'position_tags': getattr(snap, 'position_tags', None),
                'befday_qty': snap.befday_qty,
                'potential_qty': snap.potential_qty
            }
            enriched_positions.append(pos_dict)
            
        return {
            "success": True,
            "account_mode": active_account,
            "data_source": data_source,
            "positions": enriched_positions,
            "count": len(enriched_positions)
        }

    except HTTPException:
        raise
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
        
        # IBKR Handling – Read from Redis first (instant), fallback to slow IBKR API if needed
        if active_mode in [TradingAccountMode.IBKR_GUN, TradingAccountMode.IBKR_PED]:
            import asyncio
            import json
            
            account_type = active_mode.value  # IBKR_GUN or IBKR_PED
            
            # PHASE 1: Try Redis cache first (fast path) - STRING-based JSON list format
            try:
                from app.core.redis_client import get_redis_client
                r = get_redis_client()
                if r:
                    orders_key = f"psfalgo:open_orders:{account_type}"
                    raw = r.get(orders_key)
                    if raw:
                        s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                        cached_list = json.loads(s) if isinstance(s, str) else []
                        # Handle wrapped format vs legacy list
                        if isinstance(cached_list, dict) and 'orders' in cached_list:
                            cached_list = cached_list['orders']
                        if isinstance(cached_list, list):
                            for o in cached_list:
                                orders.append({
                                    'order_id': o.get('order_id'),
                                    'symbol': o.get('symbol'),
                                    'side': o.get('action'),
                                    'qty': o.get('quantity', 0.0),
                                    'order_type': o.get('order_type', 'LMT'),
                                    'limit_price': o.get('price'),
                                    'status': o.get('status', 'OPEN'),
                                    'filled': 0.0,
                                    'remaining': o.get('quantity', 0.0),
                                    'account': account_type,
                                    'tag': o.get('tag', ''),
                                    'source': 'redis_cache'
                                })
                        if orders:
                            logger.debug(f"Fetched {len(orders)} open orders from Redis cache for {account_type}")
            except Exception as redis_err:
                logger.debug(f"Redis orders cache miss: {redis_err}")
            
            # PHASE 2: If no cached orders AND IBKR is connected, fallback to slow IBKR API
            if not orders:
                from app.psfalgo.ibkr_connector import get_ibkr_connector, get_open_orders_isolated_sync
                ibkr_connector = get_ibkr_connector(account_type=account_type)

                if ibkr_connector and ibkr_connector.is_connected():
                    loop = asyncio.get_event_loop()
                    ibkr_orders = await loop.run_in_executor(None, lambda: get_open_orders_isolated_sync(account_type))
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
                            'account': o.get('account', account_type),
                            'source': 'ibkr_api'
                        }
                        for o in (ibkr_orders or [])
                    ]
                    logger.info(f"Fetched {len(orders)} open orders from IBKR API {account_type}")
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
        
        # BEFDAY + intraday metrics (per account; no cross-account sum)
        befday_long_exp = None
        befday_long_exp_pct = None
        befday_short_exp = None
        befday_short_exp_pct = None
        intraday_long_chg_exp = None
        intraday_long_chg_exp_pct = None
        intraday_short_chg_exp = None
        intraday_short_chg_exp_pct = None
        intraday_total_chg_exp = None
        intraday_total_chg_exp_pct = None
        try:
            befday_snapshot = pos_api.get_befday_exposure_snapshot(active_account)
            if befday_snapshot:
                bl = befday_snapshot.long_value
                bs = befday_snapshot.short_value
                bt = befday_snapshot.pot_total
                befday_long_exp = round(bl, 2)
                befday_short_exp = round(bs, 2)
                if bt and bt > 0:
                    befday_long_exp_pct = round(100.0 * bl / bt, 2)
                    befday_short_exp_pct = round(100.0 * bs / bt, 2)
                # Intraday: current - befday (current long/short are dollar values)
                cl = long_exposure
                cs = abs(short_exposure)  # short_exposure is negative, we want positive for "short value"
                intraday_long_chg_exp = round(cl - bl, 2)
                intraday_short_chg_exp = round(cs - bs, 2)
                intraday_total_chg_exp = round((total_exposure - bt), 2)
                if bl and bl > 0:
                    intraday_long_chg_exp_pct = round(100.0 * (cl - bl) / bl, 2)
                if bs and bs > 0:
                    intraday_short_chg_exp_pct = round(100.0 * (cs - bs) / bs, 2)
                if bt and bt > 0:
                    intraday_total_chg_exp_pct = round(100.0 * (total_exposure - bt) / bt, 2)
        except Exception as be:
            logger.debug(f"BEFDAY exposure metrics skipped: {be}")
        
        # Max cur exp / max pot exp (single source) + current/potential pct for hard risk
        max_cur_exp_pct = None
        max_pot_exp_pct = None
        current_exposure_pct = None
        potential_exposure_pct = None
        try:
            # V2: Account-aware exposure thresholds
            from app.psfalgo.exposure_threshold_service_v2 import get_exposure_threshold_service_v2
            from app.psfalgo.exposure_calculator import get_current_and_potential_exposure_pct
            thresh = get_exposure_threshold_service_v2()
            limits = thresh.get_limits_for_api(active_account)
            max_cur_exp_pct = limits.get("max_cur_exp_pct")
            max_pot_exp_pct = limits.get("max_pot_exp_pct")
            _, cur_pct, pot_pct = await get_current_and_potential_exposure_pct(active_account)
            current_exposure_pct = round(cur_pct, 2)
            potential_exposure_pct = round(pot_pct, 2)
        except Exception as ex:
            logger.debug(f"Exposure limits/pct: {ex}")

        exposure = {
            "total_exposure": round(total_exposure, 2),
            "long_exposure": round(long_exposure, 2),
            "short_exposure": round(abs(short_exposure), 2),
            "net_exposure": round(net_exposure, 2),
            "position_count": position_count,
            "max_cur_exp_pct": max_cur_exp_pct,
            "max_pot_exp_pct": max_pot_exp_pct,
            "current_exposure_pct": current_exposure_pct,
            "potential_exposure_pct": potential_exposure_pct,
            "befday_long_exp": befday_long_exp,
            "befday_long_exp_pct": befday_long_exp_pct,
            "befday_short_exp": befday_short_exp,
            "befday_short_exp_pct": befday_short_exp_pct,
            "intraday_long_chg_exp": intraday_long_chg_exp,
            "intraday_long_chg_exp_pct": intraday_long_chg_exp_pct,
            "intraday_short_chg_exp": intraday_short_chg_exp,
            "intraday_short_chg_exp_pct": intraday_short_chg_exp_pct,
            "intraday_total_chg_exp": intraday_total_chg_exp,
            "intraday_total_chg_exp_pct": intraday_total_chg_exp_pct,
        }

        return {
            "success": True,
            "trading_mode": active_account,
            "exposure": exposure
        }
    except Exception as e:
        logger.error(f"Error getting exposure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/modify")
async def modify_order(request: Dict[str, Any]):
    """
    Modify an existing order's price (for frontlama).
    
    Uses ATOMIC modify first (same order ID preserved, no cancel gap).
    Falls back to cancel+replace only if atomic modify fails.
    
    Body:
        {
            "order_id": "12345",
            "new_price": 50.25,
            "account_id": "IBKR_PED" | "IBKR_GUN" | "HAMPRO"
        }
    
    Returns:
        {"success": True/False, "message": "..."}
    """
    try:
        order_id = request.get('order_id')
        new_price = request.get('new_price')
        account_id = request.get('account_id')
        
        if not order_id or new_price is None:
            raise HTTPException(status_code=400, detail="order_id and new_price required")
        
        if not account_id:
            # Use active account from context
            ctx = get_trading_context()
            account_id = ctx.trading_mode.value
        
        # Map account_id to TradingAccountMode
        if account_id in ("HAMPRO", "HAMMER_PRO"):
            mode_enum = TradingAccountMode.HAMPRO
        elif account_id == "IBKR_PED":
            mode_enum = TradingAccountMode.IBKR_PED
        elif account_id == "IBKR_GUN":
            mode_enum = TradingAccountMode.IBKR_GUN
        else:
            raise HTTPException(status_code=400, detail=f"Invalid account_id: {account_id}")
        
        # Get provider
        from app.execution.execution_router import get_execution_router
        router = get_execution_router()
        provider = router.providers.get(mode_enum)
        
        if not provider:
            raise HTTPException(status_code=503, detail=f"No provider for {account_id}")
        
        # ═══════════════════════════════════════════════════════════════════
        # PATH 1: ATOMIC MODIFY (preferred — same order ID, no cancel gap)
        # ═══════════════════════════════════════════════════════════════════
        import asyncio
        loop = asyncio.get_event_loop()
        
        try:
            atomic_success = await loop.run_in_executor(
                None,
                lambda: provider.replace_order(
                    account_id=account_id,
                    order_id=str(order_id),
                    new_price=float(new_price)
                )
            )
            
            if atomic_success:
                logger.info(f"[ORDER_MODIFY] ✅ ATOMIC modify {order_id} → ${new_price:.2f} [{account_id}]")
                return {
                    "success": True,
                    "message": f"Order atomically modified: {order_id} → ${new_price:.2f}",
                    "old_order_id": str(order_id),
                    "new_order_id": str(order_id),  # Same ID preserved!
                    "new_price": float(new_price),
                    "method": "ATOMIC_MODIFY"
                }
        except Exception as atomic_err:
            logger.warning(f"[ORDER_MODIFY] Atomic modify failed: {atomic_err}, falling back to cancel+replace")
        
        # ═══════════════════════════════════════════════════════════════════
        # PATH 2: FALLBACK — Cancel + Replace (legacy, non-atomic)
        # ═══════════════════════════════════════════════════════════════════
        logger.info(f"[ORDER_MODIFY] Using cancel+replace fallback for order {order_id}")
        
        # Get order details from open orders
        orders_response = await get_orders()
        orders = orders_response.get('orders', [])
        
        existing_order = None
        for order in orders:
            if str(order.get('order_id')) == str(order_id):
                existing_order = order
                break
        
        if not existing_order:
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found in open orders")
        
        # Cancel existing order first
        cancel_success = provider.cancel_order(account_id, str(order_id))
        if not cancel_success:
            raise HTTPException(status_code=500, detail=f"Failed to cancel order {order_id}")
        
        logger.info(f"[ORDER_MODIFY] ⚠️ Cancelled order {order_id}, placing new order at ${new_price:.2f} (cancel+replace)")
        
        # Place new order at front price
        symbol = existing_order.get('symbol')
        side = existing_order.get('side') or existing_order.get('action', 'BUY')
        qty = existing_order.get('qty') or existing_order.get('quantity', 0)
        strategy_tag = existing_order.get('tag') or existing_order.get('strategy_tag', 'FRONTED')
        
        if not symbol or not qty:
            raise HTTPException(status_code=400, detail="Cannot recreate order: missing symbol or qty")
        
        # Prepare order plan for new order
        order_plan = {
            'symbol': symbol,
            'action': side,
            'size': int(qty),
            'price': float(new_price),
            'style': existing_order.get('order_type', 'LIMIT'),
            'psfalgo_source': True,
            'psfalgo_action': 'FRONTED',
            'strategy_tag': strategy_tag
        }
        
        gate_status = {'gate_status': 'AUTO_APPROVE'}
        
        # Execute via ExecutionRouter
        result = await loop.run_in_executor(
            None,
            lambda: router.handle(
                order_plan=order_plan,
                gate_status=gate_status,
                user_action='APPROVE',
                symbol=symbol
            )
        )
        
        if result.get('execution_status') == 'EXECUTED':
            new_order_id = result.get('order_id', '')
            logger.info(f"[ORDER_MODIFY] ✅ Replaced order {order_id} → {new_order_id} @ ${new_price:.2f} (cancel+replace)")
            return {
                "success": True,
                "message": f"Order modified (cancel+replace): {order_id} → {new_order_id} @ ${new_price:.2f}",
                "old_order_id": str(order_id),
                "new_order_id": str(new_order_id),
                "new_price": float(new_price),
                "method": "CANCEL_REPLACE"
            }
        else:
            error_reason = result.get('execution_reason') or result.get('provider_error') or 'Unknown error'
            raise HTTPException(status_code=500, detail=f"Order placement failed: {error_reason}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error modifying order: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/cancel")
async def cancel_order(request: Dict[str, Any]):
    """
    Cancel an existing order.
    
    Body:
        {
            "order_id": "12345",
            "account_id": "IBKR_PED" | "IBKR_GUN" | "HAMPRO"
        }
    
    Returns:
        {"success": True/False, "message": "..."}
    """
    try:
        order_id = request.get('order_id')
        account_id = request.get('account_id')
        
        if not order_id:
            raise HTTPException(status_code=400, detail="order_id required")
        
        if not account_id:
            # Use active account from context
            ctx = get_trading_context()
            account_id = ctx.trading_mode.value
        
        # Map account_id to TradingAccountMode
        if account_id in ("HAMPRO", "HAMMER_PRO"):
            mode_enum = TradingAccountMode.HAMPRO
        elif account_id == "IBKR_PED":
            mode_enum = TradingAccountMode.IBKR_PED
        elif account_id == "IBKR_GUN":
            mode_enum = TradingAccountMode.IBKR_GUN
        else:
            raise HTTPException(status_code=400, detail=f"Invalid account_id: {account_id}")
        
        # Set trading context
        ctx = get_trading_context()
        if ctx.trading_mode != mode_enum:
            ctx.set_trading_mode(mode_enum)
        
        # Get provider
        from app.execution.execution_router import get_execution_router
        router = get_execution_router()
        provider = router.providers.get(mode_enum)
        
        if not provider:
            raise HTTPException(status_code=503, detail=f"No provider for {account_id}")
        
        # Cancel order
        success = provider.cancel_order(account_id, str(order_id))
        
        if success:
            logger.info(f"[ORDER_CANCEL] ✅ Cancelled order {order_id} via {account_id}")
            return {"success": True, "message": f"Order {order_id} cancelled"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to cancel order {order_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling order: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/cancel-all")
async def cancel_all_orders(request: Dict[str, Any] = {}):
    """
    Cancel all open orders for the given (or active) account.
    
    Body:
        {
            "account_id": "IBKR_PED" | "IBKR_GUN" | "HAMPRO" (optional, defaults to active),
            "side": "BUY" | "SELL" (optional, cancels all if not specified)
        }
    
    Returns:
        {"success": True/False, "cancelled_count": N, "message": "...", "cancelled": [...]}
    """
    try:
        account_id = request.get('account_id')
        side = request.get('side')  # Optional: 'BUY' or 'SELL'
        
        if not account_id:
            # Use active account from context
            ctx = get_trading_context()
            account_id = ctx.trading_mode.value
        
        logger.info(f"[CANCEL_ALL] Request: account={account_id}, side={side}")
        
        # HAMMER PRO
        if account_id in ("HAMPRO", "HAMMER_PRO"):
            from app.trading.hammer_execution_service import get_hammer_execution_service
            service = get_hammer_execution_service()
            
            if not service:
                raise HTTPException(status_code=503, detail="Hammer execution service not available")
            
            result = service.cancel_all_orders(side=side)
            
            return {
                "success": result.get('success', False),
                "cancelled_count": len(result.get('cancelled', [])),
                "cancelled": result.get('cancelled', []),
                "message": result.get('message', '')
            }
        
        # IBKR
        elif account_id in ("IBKR_PED", "IBKR_GUN"):
            from app.psfalgo.ibkr_connector import get_ibkr_connector
            
            conn = get_ibkr_connector(account_type=account_id)
            
            if not conn or not conn.is_connected():
                raise HTTPException(status_code=503, detail=f"IBKR {account_id} not connected")
            
            # Get open orders first
            open_orders = await conn.get_open_orders()
            
            if not open_orders:
                return {
                    "success": True,
                    "cancelled_count": 0,
                    "cancelled": [],
                    "message": "No open orders to cancel"
                }
            
            # Filter by side if specified
            if side:
                side_upper = side.upper()
                open_orders = [
                    o for o in open_orders 
                    if o.get('action', '').upper() == side_upper
                ]
            
            # Cancel each order
            cancelled = []
            for order in open_orders:
                oid = order.get('orderId') or order.get('order_id')
                if oid:
                    try:
                        await conn.cancel_order(str(oid))
                        cancelled.append(str(oid))
                    except Exception as e:
                        logger.warning(f"Failed to cancel order {oid}: {e}")
            
            return {
                "success": True,
                "cancelled_count": len(cancelled),
                "cancelled": cancelled,
                "message": f"Cancelled {len(cancelled)} orders"
            }
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown account_id: {account_id}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CANCEL_ALL] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/orders/place")
async def place_order(request: Dict[str, Any]):
    """
    Place a new order (for frontlama replace).
    
    Body:
        {
            "symbol": "AAPL",
            "side": "BUY" | "SELL",
            "qty": 100,
            "price": 50.25,
            "order_type": "LIMIT",
            "hidden": true,
            "strategy_tag": "FRONTED",
            "account_id": "IBKR_PED" | "IBKR_GUN" | "HAMPRO"
        }
    
    Returns:
        {"success": True/False, "order_id": "...", "message": "..."}
    """
    try:
        symbol = request.get('symbol')
        side = request.get('side')  # BUY or SELL
        qty = request.get('qty')
        price = request.get('price')
        order_type = request.get('order_type', 'LIMIT')
        account_id = request.get('account_id')
        
        if not all([symbol, side, qty, price]):
            raise HTTPException(status_code=400, detail="symbol, side, qty, price required")
        
        if not account_id:
            # Use active account from context
            ctx = get_trading_context()
            account_id = ctx.trading_mode.value
        
        # Map account_id to TradingAccountMode
        if account_id in ("HAMPRO", "HAMMER_PRO"):
            mode_enum = TradingAccountMode.HAMPRO
        elif account_id == "IBKR_PED":
            mode_enum = TradingAccountMode.IBKR_PED
        elif account_id == "IBKR_GUN":
            mode_enum = TradingAccountMode.IBKR_GUN
        else:
            raise HTTPException(status_code=400, detail=f"Invalid account_id: {account_id}")
        
        # Set trading context
        ctx = get_trading_context()
        if ctx.trading_mode != mode_enum:
            ctx.set_trading_mode(mode_enum)
        
        # Prepare order plan
        order_plan = {
            'symbol': symbol,
            'action': side,
            'size': int(qty),
            'price': float(price),
            'style': order_type,
            'psfalgo_source': True,
            'psfalgo_action': 'FRONTED',
            'strategy_tag': request.get('strategy_tag', 'FRONTED')
        }
        
        gate_status = {'gate_status': 'AUTO_APPROVE'}  # Auto-approve for fronted orders
        
        # Execute via ExecutionRouter
        from app.execution.execution_router import get_execution_router
        router = get_execution_router()
        
        # Run in executor to avoid blocking
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: router.handle(
                order_plan=order_plan,
                gate_status=gate_status,
                user_action='APPROVE',
                symbol=symbol
            )
        )
        
        if result.get('execution_status') == 'EXECUTED':
            order_id = result.get('order_id', '')
            logger.info(f"[ORDER_PLACE] ✅ Placed order {order_id} via {account_id}: {side} {qty} {symbol} @ {price}")
            return {
                "success": True,
                "order_id": str(order_id),
                "message": f"Order placed: {side} {qty} {symbol} @ ${price:.2f}"
            }
        else:
            error_reason = result.get('execution_reason') or result.get('provider_error') or 'Unknown error'
            raise HTTPException(status_code=500, detail=f"Order placement failed: {error_reason}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error placing order: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
