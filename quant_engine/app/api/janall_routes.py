from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio

from app.api.janall_models import BulkOrderRequest, BulkOrderResponse, CancelOrderRequest, GenericResponse
from app.psfalgo.account_mode import get_account_mode_manager, AccountMode
from app.psfalgo.ibkr_connector import get_ibkr_connector
from app.trading.hammer_execution_service import get_hammer_execution_service
from app.algo.janall_bulk_manager import JanallBulkOrderManager
from app.psfalgo.execution_ledger import PSFALGOExecutionLedger
from app.core.logger import logger

router = APIRouter(prefix="/api/janall", tags=["Janall Order Mechanisms"])

# Global references (for IB Native specifically)
_native_client = None # Holds the IBNativeConnector instance
_janall_manager = None

def set_janall_dependencies(manager, client):
    global _janall_manager, _native_client
    _janall_manager = manager
    _native_client = client

def get_active_client():
    """
    Returns the appropriate execution client based on Account Mode.
    Wrapper to unify .place_order interface.
    """
    mode_mgr = get_account_mode_manager()
    if not mode_mgr:
        raise HTTPException(status_code=503, detail="Account Mode Manager not ready")
        
    mode = mode_mgr.get_mode()
    
    # 1. HAMMER PRO MODE
    if mode == AccountMode.HAMMER_PRO.value:
        service = get_hammer_execution_service()
        if not service:
            raise HTTPException(status_code=503, detail="Hammer Execution Service not ready")
        
        # Adapter to match JanallBulkOrderManager expected interface
        class HammerAdapter:
            def __init__(self, svc):
                self.svc = svc
            def place_order(self, symbol, action, quantity, price, order_type="LIMIT", **kwargs):
                # Map arguments
                res = self.svc.place_order(
                    symbol=symbol,
                    side=action,
                    quantity=quantity,
                    price=price,
                    order_style=order_type,
                    hidden=True # Janall defaults to Hidden
                )
                return res.get('success', False)
                
            def cancel_order(self, order_id):
                res = self.svc.cancel_order(order_id)
                return res.get('success', False)

        return HammerAdapter(service)

    # 2. IBKR MODES (GUN/PED)
    else:
        # User requested "IB Native" logic.
        # We should prioritize the _native_client if initialized and connected.
        if _native_client and _native_client.isConnected():
             return _native_client
        
        # Fallback to ib_insync connector if native not available?
        # User insisted on "Native" logic. But if native failed to connect, we must bail or warn.
        if not _native_client:
             raise HTTPException(status_code=503, detail="IB Native Client not initialized")
        if not _native_client.isConnected():
             # Try converting to active IBKR_GUN/PED connector?
             # But those are ib_insync.
             # Taking user request "ayni mantigi" strictly -> Try to reconnect Native?
             raise HTTPException(status_code=503, detail="IB Native Client not connected. Check logs.")
             
        return _native_client

@router.post("/bulk-order", response_model=BulkOrderResponse)
async def place_bulk_order(req: BulkOrderRequest):
    # Get Manager (which holds the logic, but we swap the client)
    if not _janall_manager:
        raise HTTPException(status_code=503, detail="Janall Manager not initialized")
        
    # Dynamically set the client on the manager before execution
    active_client = get_active_client()
    _janall_manager.trading_client = active_client # Hot swap
    
    # Configure splitter
    _janall_manager.toggle_lot_divider(req.smart_split)
    
    # Instantiate Ledger (to record Strategy Tag)
    ledger = PSFALGOExecutionLedger()
    
    # Execute
    try:
        results = await _janall_manager.execute_bulk_orders(
            tickers=req.tickers,
            order_type=req.order_type,
            total_lot=req.total_lot,
            strategy_tag=req.strategy_tag.value,
            ledger=ledger
        )
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Bulk Execution Failed: {str(e)}")
    
    return BulkOrderResponse(
        status="completed", 
        message=f"Processed {len(req.tickers)} tickers",
        results=results
    )

@router.post("/cancel-orders", response_model=GenericResponse)
async def cancel_orders(req: CancelOrderRequest):
    client = get_active_client()
    
    success_count = 0
    fail_count = 0
    
    for oid in req.order_ids:
        try:
            if client.cancel_order(oid):
                success_count += 1
            else:
                fail_count += 1
        except Exception:
            fail_count += 1
            
    return GenericResponse(
        success=True,
        message=f"Sent cancel for {success_count} orders. Failed: {fail_count}"
    )


def determine_order_tag(order: Dict[str, Any], position_map: Dict[str, Dict]) -> str:
    """
    Determine order tag based on position and order source.
    
    Returns one of 8 tags:
    - LT_LONG_INC, LT_SHORT_INC, LT_LONG_DEC, LT_SHORT_DEC
    - MM_LONG_INC, MM_SHORT_INC, MM_LONG_DEC, MM_SHORT_DEC
    
    Uses position tags (from PositionTagManager) to determine LT vs MM.
    """
    symbol = order.get('symbol', '')
    action = order.get('action', '')  # BUY or SELL
    source = order.get('source', order.get('order_ref', 'UNKNOWN'))
    
    # Find existing position
    position = position_map.get(symbol)
    
    # NEW POSITION (opening)
    if not position or abs(position.get('qty', 0)) < 0.01:
        # Check source for LT vs MM
        source_upper = str(source).upper()
        
        if 'MM' in source_upper or 'GREATEST' in source_upper:
            # MM new position
            return 'MM_LONG_INC' if action == 'BUY' else 'MM_SHORT_INC'
        else:
            # LT new position (JFIN, ADDNEWPOS, etc.)
            return 'LT_LONG_INC' if action == 'BUY' else 'LT_SHORT_INC'
    
    # EXISTING POSITION - use position tag
    pos_qty = position.get('qty', 0)
    pos_tag = position.get('tag', 'LT ov long')  # Default to LT if no tag
    
    # Determine if LT or MM from position tag
    is_mm = 'MM' in pos_tag
    base = 'MM' if is_mm else 'LT'
    
    # Determine direction (LONG/SHORT)
    is_long = pos_qty > 0
    direction = 'LONG' if is_long else 'SHORT'
    
    # Determine INC/DEC
    if is_long:
        # LONG position: BUY = increase, SELL = decrease
        action_type = 'INC' if action == 'BUY' else 'DEC'
    else:
        # SHORT position: SELL = increase, BUY = decrease (cover)
        action_type = 'INC' if action == 'SELL' else 'DEC'
    
    return f"{base}_{direction}_{action_type}"


@router.get("/orders")
async def get_orders():
    """
    Fetch orders based on active mode.
    """
    global _native_client
    
    mode_mgr = get_account_mode_manager()
    if not mode_mgr:
        return {"open_orders": [], "filled_orders": []}

    mode = mode_mgr.get_mode()
    
    logger.info(f"[JANALL_ORDERS_DEBUG] Mode: {mode}, Type: {type(mode)}")
    logger.info(f"[JANALL_ORDERS_DEBUG] HAMMER_PRO value: {AccountMode.HAMMER_PRO.value}")
    logger.info(f"[JANALL_ORDERS_DEBUG] Comparison: {mode == AccountMode.HAMMER_PRO.value}")
    
    # HAMMER MODE
    if mode == AccountMode.HAMMER_PRO.value:
        try:
            # Lazy import to avoid circular dependency
            from app.api.trading_routes import get_hammer_services
            
            orders_svc, _ = get_hammer_services()
            if not orders_svc:
                return {"open_orders": [], "filled_orders": []}
            
            # Hammer service .get_open_orders() returns list of dicts
            open_orders = orders_svc.get_open_orders()
            # Fills not perfectly tracked in service yet, maybe empty
            return {
                "open_orders": open_orders,
                "filled_orders": [] # Not implemented in HammerService yet
            }
        except Exception:
             return {"open_orders": [], "filled_orders": []}

    # IBKR MODE
    # IBKR MODE
    # IBKR MODE
    # IBKR MODE
    else:
        all_orders = {}
        all_fills = []
        native_fills = []
        
        # logger.info("🔍 [JANALL] Fetching IBKR Orders (Merged Mode)...")

        # 1. Fetch from Native Client (Active Fetch)
        if _native_client:
             if not _native_client.isConnected():
                 logger.warning("[JANALL] IB Native Client disconnected. Attempting reconnect...")
                 try:
                     _native_client.connect_client()
                 except Exception as e:
                     logger.error(f"[JANALL] Native reconnect failed: {e}")

             if _native_client.isConnected():
                 try:
                     native_orders = _native_client.get_open_orders()
                     logger.info(f"   [NATIVE] Connected. Found {len(native_orders)} orders.")
                     for o in native_orders:
                         all_orders[o['order_id']] = o
                     
                     # Native fills
                     native_fills = _native_client.get_todays_filled_orders()
                 except Exception as e:
                     logger.error(f"   [NATIVE] Error: {e}")
             else:
                 logger.warning("   [NATIVE] Still disconnected after retry.")

        else:
             # Native client not initialized - try to initialize it now
             logger.warning("   [NATIVE] Not initialized. Attempting lazy initialization...")
             try:
                  from app.ibkr.ib_native_connector import IBNativeConnector
                  from app.config.settings import settings
                  
                  _native_client = IBNativeConnector(host=settings.IBKR_HOST, port=settings.IBKR_PORT, client_id=1)
                  
                  if _native_client.connect_client():
                       logger.info(f"✅ [NATIVE] Lazy connect successful!")
                       # Now fetch orders
                       try:
                            native_orders = _native_client.get_open_orders()
                            logger.info(f"   [NATIVE] Found {len(native_orders)} orders after lazy connect.")
                            for o in native_orders:
                                 all_orders[o['order_id']] = o
                            native_fills = _native_client.get_todays_filled_orders()
                       except Exception as e:
                            logger.error(f"   [NATIVE] Error after lazy connect: {e}")
                  else:
                       logger.warning("   [NATIVE] Lazy connect failed.")
             except Exception as e:
                  logger.error(f"   [NATIVE] Lazy initialization error: {e}")
        
        # 2. Fetch from IBKRConnector (ib_insync) - Cached/Event-driven
        try:
             # Determine Account Type from Mode
             # AccountMode values: HAMMER_PRO, IBKR_GUN, IBKR_PED
             logger.info(f"[JANALL] Current mode: {mode}")
             
             target_account = "IBKR_GUN"
             if mode == AccountMode.IBKR_PED.value:
                 target_account = "IBKR_PED"
             elif mode == AccountMode.IBKR_GUN.value:
                target_account = "IBKR_GUN"
             
             conn = get_ibkr_connector(account_type=target_account)
             
             if conn:
                  if not conn.is_connected():
                       logger.info(f"[JANALL] {target_account} disconnected. Connecting...")
                       await conn.connect()
                  
                  if conn.is_connected():
                       # force reqAllOpenOrders to see Client 1 / Manual orders
                       if hasattr(conn, '_ibkr_client') and conn._ibkr_client:
                            # ib_insync reqAllOpenOrders requests updates. 
                            conn._ibkr_client.reqAllOpenOrders()
                            
                            # Increase wait time to ensure TWS sends data
                            await asyncio.sleep(0.5) 
                            
                            # Fetch from cache after update
                            ib_insync_orders = await conn.get_open_orders()
                            logger.info(f"   [IB_INSYNC] Connected to {target_account}. Found {len(ib_insync_orders)} orders.")
                            
                            for o in ib_insync_orders:
                                # Merge: Native is authority, but assume ib_insync sees same orders plus maybe more
                                if o['order_id'] not in all_orders:
                                     all_orders[o['order_id']] = o
                  else:
                       logger.warning(f"   [IB_INSYNC] Failed to connect to {target_account}.")
             else:
                  logger.warning("   [IB_INSYNC] Connector retrieval failed.")
        except Exception as e:
             logger.error(f"   [IB_INSYNC] Error: {e}")

        # Add tags to all orders before returning
        try:
            # For now, all positions are LT (as user confirmed)
            # Fetch current positions to determine tags
            from app.api.trading_routes import get_positions_snapshot
            positions = []
            try:
                pos_response = await get_positions_snapshot()
                if isinstance(pos_response, dict) and 'positions' in pos_response:
                    positions = pos_response['positions']
            except:
                pass
            
            # Create position lookup
            position_map = {p['symbol']: p for p in positions}
            
            for order in all_orders.values():
                tag = determine_order_tag(order, position_map)
                order['tag'] = tag
                
        except Exception as e:
            logger.error(f"   [TAG] Error adding tags: {e}")
            # Continue without tags

        logger.info(f"   [MERGED] Total Unique Orders: {len(all_orders)}")
        return {
            "open_orders": list(all_orders.values()),
            "filled_orders": native_fills
        }


class CancelOrdersRequest(BaseModel):
    order_ids: List[int]


@router.post("/cancel-orders")
async def cancel_orders(request: CancelOrdersRequest):
    """
    Cancel selected orders.
    """
    global _native_client
    
    mode_mgr = get_account_mode_manager()
    if not mode_mgr:
        raise HTTPException(status_code=500, detail="Account mode manager not available")
    
    mode = mode_mgr.get_mode()
    
    # IBKR orders
    cancelled = []
    failed = []
    
    # Try ib_insync connector
    try:
        target_account = "IBKR_GUN"
        if mode in ["IBKR_PAPER", "IBKR_PED", AccountMode.IBKR_PED.value]:
            target_account = "IBKR_PED"
        
        conn = get_ibkr_connector(account_type=target_account)
        if conn and conn.is_connected():
            for order_id in request.order_ids:
                try:
                    # Cancel via ib_insync
                    if hasattr(conn, '_ibkr_client') and conn._ibkr_client:
                        conn._ibkr_client.cancelOrder(order_id)
                        cancelled.append(order_id)
                        logger.info(f"[CANCEL] Cancelled order {order_id}")
                except Exception as e:
                    logger.error(f"[CANCEL] Failed to cancel order {order_id}: {e}")
                    failed.append({"order_id": order_id, "error": str(e)})
        else:
            logger.warning(f"[CANCEL] IBKR connector not connected")
    except Exception as e:
        logger.error(f"[CANCEL] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Cancel failed: {str(e)}")
    
    return {
        "success": len(cancelled) > 0,
        "cancelled": cancelled,
        "failed": failed,
        "message": f"Cancelled {len(cancelled)} orders" + (f", {len(failed)} failed" if failed else "")
    }



@router.get("/orders/pending")
async def get_pending_orders():
    """
    Get pending orders (remaining > 0).
    
    Returns orders with partial or no fills.
    Format: {filled}/{total} @ avg_fill_price
    """
    try:
        # Get all orders from main endpoint
        all_orders_response = await get_orders()
        open_orders = all_orders_response.get('open_orders', [])
        
        # Get positions for tag determination
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        pos_api = get_position_snapshot_api()
        
        mode_mgr = get_account_mode_manager()
        account_id = mode_mgr.current_mode.value if mode_mgr else 'HAMPRO'
        
        snapshot = await pos_api.get_position_snapshot(account_id=account_id)
        positions = snapshot.get('positions', [])
        position_map = {p['symbol']: p for p in positions}
        
        # Filter and format pending orders
        pending = []
        for order in open_orders:
            remaining = order.get('remaining', order.get('qty', 0))
            
            # Only include if there's remaining quantity
            if remaining > 0:
                filled = order.get('filled', 0)
                total = filled + remaining
                
                # Determine tag
                tag = determine_order_tag(order, position_map)
                
                pending.append({
                    'symbol': order.get('symbol'),
                    'side': order.get('action'),  # BUY/SELL
                    'total_qty': total,
                    'filled_qty': filled,
                    'remaining_qty': remaining,
                    'avg_fill_price': order.get('avg_fill_price', 0.0),
                    'limit_price': order.get('price', 0.0),
                    'tag': tag,
                    'time': order.get('time', ''),
                    'order_id': order.get('order_id'),
                    'status': order.get('status', 'PENDING')
                })
        
        logger.info(f"[Pending Orders] Returning {len(pending)} pending orders")
        
        return {
            'success': True,
            'orders': pending
        }
        
    except Exception as e:
        logger.error(f"[Pending Orders] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/filled")
async def get_filled_orders():
    """
    Get filled orders (remaining == 0) from today.
    
    Returns completed orders with fill details.
    """
    try:
        # Get all orders
        all_orders_response = await get_orders()
        open_orders = all_orders_response.get('open_orders', [])
        filled_orders_raw = all_orders_response.get('filled_orders', [])
        
        # Get positions for tag determination
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        pos_api = get_position_snapshot_api()
        
        mode_mgr = get_account_mode_manager()
        account_id = mode_mgr.current_mode.value if mode_mgr else 'HAMPRO'
        
        snapshot = await pos_api.get_position_snapshot(account_id=account_id)
        positions = snapshot.get('positions', [])
        position_map = {p['symbol']: p for p in positions}
        
        # Collect filled orders
        filled = []
        
        # 1. From open_orders that are fully filled
        for order in open_orders:
            remaining = order.get('remaining', 1)  # Default to 1 if not specified
            filled_qty = order.get('filled', 0)
            
            if remaining == 0 and filled_qty > 0:
                tag = determine_order_tag(order, position_map)
                
                filled.append({
                    'symbol': order.get('symbol'),
                    'side': order.get('action'),
                    'qty': filled_qty,
                    'fill_price': order.get('avg_fill_price', order.get('price', 0.0)),
                    'tag': tag,
                    'time': order.get('time', ''),
                    'order_id': order.get('order_id')
                })
        
        # 2. From filled_orders list (if available)
        for order in filled_orders_raw:
            tag = determine_order_tag(order, position_map)
            
            filled.append({
                'symbol': order.get('symbol'),
                'side': order.get('action'),
                'qty': order.get('qty', order.get('filled', 0)),
                'fill_price': order.get('fill_price', order.get('avg_fill_price', 0.0)),
                'tag': tag,
                'time': order.get('time', ''),
                'order_id': order.get('order_id')
            })
        
        # Sort by time (most recent first)
        filled.sort(key=lambda x: x.get('time', ''), reverse=True)
        
        logger.info(f"[Filled Orders] Returning {len(filled)} filled orders")
        
        return {
            'success': True,
            'orders': filled
        }
        
    except Exception as e:
        logger.error(f"[Filled Orders] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
