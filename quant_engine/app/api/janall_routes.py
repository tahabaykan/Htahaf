from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import asyncio
import time

from app.api.janall_models import BulkOrderRequest, BulkOrderResponse, CancelOrderRequest, GenericResponse
from app.psfalgo.account_mode import get_account_mode_manager, AccountMode
from app.psfalgo.ibkr_connector import get_ibkr_connector
from app.trading.hammer_execution_service import get_hammer_execution_service
from app.algo.janall_bulk_manager import JanallBulkOrderManager
from app.psfalgo.execution_ledger import PSFALGOExecutionLedger
from app.psfalgo.order_manager import get_order_controller
from app.core.logger import logger

router = APIRouter(prefix="/api/janall", tags=["Janall Order Mechanisms"])

# Global references (for IB Native specifically)
_native_client = None # Holds the IBNativeConnector instance
_janall_manager = None

# Short-TTL cache for get_orders() to avoid repeated IBKR/Hammer calls when UI polls every 2s
_orders_response_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_ORDERS_CACHE_TTL = 3

def _invalidate_orders_cache():
    """Clear get_orders cache for current mode so next poll returns fresh data after place/cancel."""
    mode_mgr = get_account_mode_manager()
    if mode_mgr:
        mode = mode_mgr.get_mode()
        if mode and str(mode) in _orders_response_cache:
            del _orders_response_cache[str(mode)]

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
        if not _native_client:
             raise HTTPException(status_code=503, detail="IB Native Client not initialized")
        if not _native_client.isConnected():
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
    _invalidate_orders_cache()
    return BulkOrderResponse(
        status="completed", 
        message=f"Processed {len(req.tickers)} tickers",
        results=results
    )

@router.post("/cancel-orders")
async def cancel_orders(request: CancelOrderRequest):
    """
    Cancel selected orders. Uses the same client as order visibility:
    - HAMMER_PRO → Hammer execution service
    - IBKR (GUN/PED) → Native first (historically working path), then IB_INSYNC for any remaining.
    """
    logger.info(f"[CANCEL_DEBUG] Received cancel request for IDs: {request.order_ids}")
    global _native_client

    mode_mgr = get_account_mode_manager()
    if not mode_mgr:
        raise HTTPException(status_code=500, detail="Account mode manager not available")

    mode = mode_mgr.get_mode()
    cancelled = []
    failed = []

    # --- HAMMER MODE: use Hammer service (same as /orders) ---
    if mode == AccountMode.HAMMER_PRO.value:
        try:
            hammer_svc = get_hammer_execution_service()
            if hammer_svc:
                # CANCEL ALL: empty order_ids → cancel_all_orders() cancels every open order
                if not request.order_ids:
                    logger.info("[CANCEL] HAMMER CANCEL ALL: Empty order_ids → calling cancel_all_orders()")
                    result = hammer_svc.cancel_all_orders(side=None)
                    if result.get("success", False):
                        cancelled = result.get("cancelled", [])
                        logger.info(f"[CANCEL] HAMMER CANCEL ALL: Cancelled {len(cancelled)} orders")
                    else:
                        failed.append({"order_id": "ALL", "error": result.get("message", "Cancel all failed")})
                        logger.warning(f"[CANCEL] HAMMER CANCEL ALL failed: {result.get('message')}")
                else:
                    # CANCEL SELECTED: batch cancel using array (Hammer API supports orderID as array)
                    # Per Hammer Pro API docs: "orderID": ["id1", "id2", ...] is valid
                    order_ids_str = [str(oid) for oid in request.order_ids]
                    logger.info(f"[CANCEL] HAMMER BATCH CANCEL: {len(order_ids_str)} orders: {order_ids_str[:5]}...")
                    try:
                        cancel_cmd = {
                            "cmd": "tradeCommandCancel",
                            "accountKey": hammer_svc.account_key,
                            "orderID": order_ids_str  # Array - single API call for all!
                        }
                        response = hammer_svc.hammer_client.send_command_and_wait(
                            cancel_cmd, wait_for_response=True, timeout=5.0
                        )
                        if response and isinstance(response, dict) and response.get('success') == 'OK':
                            cancelled = order_ids_str
                            logger.info(f"[CANCEL] HAMMER BATCH CANCEL SUCCESS: {len(cancelled)} orders")
                        else:
                            error_msg = response.get('result') if isinstance(response, dict) else str(response) if response else "No response"
                            # Batch failed - try individual as fallback
                            logger.warning(f"[CANCEL] Batch cancel failed ({error_msg}), trying individual...")
                            for oid in order_ids_str:
                                try:
                                    res = hammer_svc.cancel_order(oid)
                                    if res.get("success", False):
                                        cancelled.append(oid)
                                    else:
                                        failed.append({"order_id": oid, "error": res.get("message", "Cancel failed")})
                                except Exception as e2:
                                    failed.append({"order_id": oid, "error": str(e2)})
                    except Exception as e:
                        logger.error(f"[CANCEL] Hammer batch cancel error: {e}")
                        for oid in order_ids_str:
                            failed.append({"order_id": oid, "error": str(e)})
            else:
                if not request.order_ids:
                    failed.append({"order_id": "ALL", "error": "Hammer service not available"})
                else:
                    for oid in request.order_ids:
                        failed.append({"order_id": oid, "error": "Hammer service not available"})
        except Exception as e:
            logger.error(f"[CANCEL] Hammer path error: {e}")
            if not request.order_ids:
                failed.append({"order_id": "ALL", "error": str(e)})
            else:
                for oid in request.order_ids:
                    failed.append({"order_id": oid, "error": str(e)})
        _invalidate_orders_cache()
        return {
            "success": len(cancelled) > 0 or (not failed),
            "cancelled": cancelled,
            "failed": failed,
            "message": f"Cancelled {len(cancelled)} orders" + (f", {len(failed)} failed" if failed else ""),
        }

    # --- IBKR MODE: use ONLY ib_insync bridge (native path disabled for Python 3.14) ---
    target_account = "IBKR_GUN"
    if mode in ["IBKR_PAPER", "IBKR_PED", AccountMode.IBKR_PED.value]:
        target_account = "IBKR_PED"

    try:
        from app.psfalgo.ibkr_connector import (
            get_open_orders_isolated_sync,
            get_open_orders_all_isolated_sync,
            cancel_orders_isolated_sync,
            global_cancel_isolated_sync,
        )
        loop = asyncio.get_event_loop()

        # CANCEL ALL: empty order_ids → reqGlobalCancel() cancels every open order on the account (any clientId)
        if not request.order_ids:
            all_open = await loop.run_in_executor(None, lambda: get_open_orders_all_isolated_sync(target_account))
            all_ids = [int(o.get("order_id") or o.get("orderId")) for o in (all_open or []) if (o.get("order_id") or o.get("orderId")) is not None]
            if not all_ids:
                logger.warning("[CANCEL] No open orders on account - nothing to cancel")
            else:
                ok = await loop.run_in_executor(None, lambda: global_cancel_isolated_sync(target_account))
                if ok:
                    await asyncio.sleep(1.0)
                    open_after = await loop.run_in_executor(None, lambda: get_open_orders_all_isolated_sync(target_account))
                    still_open = set((o.get("order_id") or o.get("orderId") for o in (open_after or []) if (o.get("order_id") or o.get("orderId")) is not None))
                    for oid in all_ids:
                        if int(oid) not in still_open:
                            cancelled.append(int(oid))
                            logger.info(f"[CANCEL] Cancelled order {oid} via reqGlobalCancel")
                        else:
                            failed.append({"order_id": oid, "error": "Still open after reqGlobalCancel"})
                else:
                    for oid in all_ids:
                        failed.append({"order_id": oid, "error": "reqGlobalCancel failed"})
        else:
            # CANCEL SELECTED: try cancelOrder() for every selected ID; only our session's orders will actually cancel (IB 10147 for others)
            requested = [int(x) for x in request.order_ids]
            if not requested:
                pass
            else:
                await loop.run_in_executor(
                    None, lambda: cancel_orders_isolated_sync(target_account, requested)
                )
                await asyncio.sleep(0.5)
                open_after = await loop.run_in_executor(None, lambda: get_open_orders_all_isolated_sync(target_account))
                still_open = set()
                for o in (open_after or []):
                    oid = o.get("order_id") or o.get("orderId")
                    if oid is not None:
                        still_open.add(int(oid))
                for oid in requested:
                    if oid not in still_open:
                        cancelled.append(oid)
                        logger.info(f"[CANCEL] Cancelled order {oid} via IB_INSYNC")
                    else:
                        failed.append({"order_id": oid, "error": "Başka oturumdan (10147); Tümünü iptal kullanın"})
        # Update Redis open-orders: remove confirmed cancelled IDs; if any failed (10147/stale), clear key so UI refetches from IB
        try:
            from app.core.redis_client import get_redis_client
            import json
            r = get_redis_client()
            if r and hasattr(r, "get") and hasattr(r, "set"):
                key = f"psfalgo:open_orders:{target_account}"
                if failed:
                    # Stale/10147: clear cache so UI shows only what IB has (reqOpenOrders)
                    try:
                        r.delete(key)
                    except Exception:
                        r.set(key, json.dumps([]), ex=60)
                    logger.info(f"[CANCEL] Cleared Redis {key} after {len(failed)} failed (stale/10147) so UI refetches from IB")
                elif cancelled:
                    raw = r.get(key)
                    if raw:
                        s = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                        parsed = json.loads(s) if isinstance(s, str) else s
                        # Handle wrapped format vs legacy list
                        if isinstance(parsed, dict) and 'orders' in parsed:
                            redis_list = parsed['orders']
                        elif isinstance(parsed, list):
                            redis_list = parsed
                        else:
                            redis_list = []
                        if isinstance(redis_list, list):
                            cancelled_ids = {int(x) for x in cancelled} | {str(x) for x in cancelled}
                            new_list = [o for o in redis_list if o.get("order_id") not in cancelled_ids]
                            import time as _time
                            payload = {'orders': new_list, '_meta': {'updated_at': _time.time()}}
                            r.set(key, json.dumps(payload), ex=600)
                            logger.info(f"[CANCEL] Removed {len(cancelled)} order IDs from Redis {key} (now {len(new_list)} open)")
        except Exception as redis_err:
            logger.debug(f"[CANCEL] Redis cleanup: {redis_err}")
    except Exception as e:
        logger.warning(f"[CANCEL] IBKR ib_insync error: {e}", exc_info=True)
        for oid in request.order_ids:
            failed.append({"order_id": oid, "error": str(e)})

    _invalidate_orders_cache()
    return {
        "success": len(cancelled) > 0,
        "cancelled": cancelled,
        "failed": failed,
        "message": f"Cancelled {len(cancelled)} orders" + (f", {len(failed)} failed" if failed else ""),
    }

def determine_order_tag(order: Dict[str, Any], position_map: Dict[str, Dict], account_id: str = None) -> str:
    """
    Determine order tag for display with account info.
    LT_TRIM / KARBOTU / REDUCEMORE → always DECREASE (SELL=long reduce, BUY=short reduce).
    Placement strategy_tag/order_ref is preferred: if it already contains DEC/INC, use it.
    Tag Format: {ACCOUNT}_{LT/MM}_{LONG/SHORT}_{INC/DEC}
    Example: IBKR_PED_LT_LONG_DEC, HAMPRO_MM_SHORT_INC
    
    KEY FIX: For DECREASE orders:
    - SELL action on a LONG position = LT_LONG_DEC (selling to reduce long)
    - BUY action on a SHORT position = LT_SHORT_DEC (buying to cover short)
    """
    symbol = order.get('symbol', '')
    action = order.get('action', '')
    qty = abs(order.get('qty', order.get('total_qty', 0)))
    
    # Check if order already has a well-formed tag 
    existing_tag = order.get('tag', '') or order.get('strategy_tag', '')
    if existing_tag:
        existing_upper = existing_tag.upper()
        # If tag already contains full format (e.g. LT_LONG_DEC, MM_SHORT_INC), preserve it
        if ('_LONG_' in existing_upper or '_SHORT_' in existing_upper) and ('_INC' in existing_upper or '_DEC' in existing_upper):
            # Just add account prefix if needed
            if account_id and not existing_upper.startswith(account_id.upper()):
                return f"{account_id}_{existing_tag}"
            return existing_tag
    
    source = order.get('strategy_tag') or order.get('source') or order.get('order_ref', 'UNKNOWN')
    source_upper = str(source).upper()
    
    position = position_map.get(symbol)
    current_qty = position.get('qty', 0) if position else 0
    if action == 'BUY':
        potential_qty = current_qty + qty
    else:
        potential_qty = current_qty - qty
    
    # Base: LT vs MM
    if 'LT_TRIM' in source_upper or 'KARBOTU' in source_upper or 'REDUCEMORE' in source_upper or source_upper.startswith('LT_'):
        base = 'LT'
    elif 'MM' in source_upper or 'GREATEST' in source_upper or (position and (position.get('tag') or '').upper().find('MM') >= 0):
        base = 'MM'
    else:
        base = 'LT'
    
    # INC vs DEC: Prefer placement tag. LT_TRIM/KARBOTU/REDUCEMORE are always DECREASE.
    if 'DEC' in source_upper or 'DECREASE' in source_upper or 'TRIM' in source_upper or 'KARBOTU' in source_upper or 'REDUCE' in source_upper:
        action_type = 'DEC'
    elif 'INC' in source_upper or 'INCREASE' in source_upper:
        action_type = 'INC'
    else:
        is_increasing = abs(potential_qty) > abs(current_qty)
        action_type = 'INC' if is_increasing else 'DEC'
    
    # Direction: LONG or SHORT  
    # KEY FIX: For DECREASE orders, the direction is what we're decreasing FROM (existing position)
    # - SELL on long = LONG_DEC (reducing long position)
    # - BUY on short = SHORT_DEC (covering short position)
    # For INCREASE orders, direction is what we're building TO
    # - BUY = LONG_INC (adding long)
    # - SELL = SHORT_INC (adding short)
    if action_type == 'DEC':
        # DECREASE: Look at current position to determine what we're trimming
        if abs(current_qty) > 0.01:
            direction = 'LONG' if current_qty > 0 else 'SHORT'
        else:
            # No current position - infer from action: 
            # SELL = was long, BUY = was short  
            direction = 'LONG' if action == 'SELL' else 'SHORT'
    else:
        # INCREASE: Direction is where we're going
        if abs(potential_qty) > abs(current_qty) and abs(potential_qty) > 0.01:
            direction = 'LONG' if potential_qty > 0 else 'SHORT'
        elif abs(current_qty) > 0.01:
            direction = 'LONG' if current_qty > 0 else 'SHORT'
        else:
            # Building new position
            direction = 'LONG' if action == 'BUY' else 'SHORT'
    
    # Include account_id if provided
    base_tag = f"{base}_{direction}_{action_type}"
    if account_id:
        return f"{account_id}_{base_tag}"
    return base_tag

@router.get("/orders")
async def get_orders(mode: str = None):
    """
    Fetch orders based on active mode with merged Native + IB_INSYNC sources.
    Cached 3s per mode to avoid repeated IBKR/Hammer calls when UI polls.
    
    Args:
        mode: Optional mode override from UI (HAMMER_PRO, IBKR_GUN, IBKR_PED)
              If provided, uses this mode instead of global account mode.
              This is essential for Dual Process where UI follows bot's current account.
    """
    global _native_client
    mode_mgr = get_account_mode_manager()
    if not mode_mgr: return {"open_orders": [], "filled_orders": []}
    
    # Use provided mode parameter if given, otherwise use global mode manager
    if mode:
        mode_upper = mode.upper()
        if mode_upper == 'HAMMER_PRO':
            active_mode = AccountMode.HAMMER_PRO.value
        elif mode_upper == 'IBKR_PED':
            active_mode = AccountMode.IBKR_PED.value
        elif mode_upper == 'IBKR_GUN':
            active_mode = AccountMode.IBKR_GUN.value
        else:
            active_mode = mode_mgr.get_mode()
    else:
        active_mode = mode_mgr.get_mode()
    
    cache_key = str(active_mode) if active_mode else None
    if cache_key:
        now = time.time()
        if cache_key in _orders_response_cache:
            expiry_ts, cached = _orders_response_cache[cache_key]
            if now < expiry_ts:
                return cached
    # 1. HAMMER MODE
    if active_mode == AccountMode.HAMMER_PRO.value:
        try:
            from app.api.trading_routes import get_hammer_services, get_positions
            orders_svc, _ = get_hammer_services()
            if not orders_svc: return {"open_orders": [], "filled_orders": []}
            
            # Use get_all_orders() to get BOTH open and filled in single getTransactions call
            all_data = orders_svc.get_all_orders()
            open_orders = all_data.get('open_orders', [])
            filled_orders = all_data.get('filled_orders', [])
            
            # Enrich tags: Redis tag written at placement time is already in the order dict,
            # but for older/untagged orders, infer from positions
            if open_orders or filled_orders:
                try:
                    pos_resp = await get_positions(account_id='HAMPRO')
                    positions = pos_resp.get('positions', []) if isinstance(pos_resp, dict) else []
                    position_map = {p['symbol']: p for p in positions}
                    for o in open_orders:
                        if not o.get('tag'):
                            o['tag'] = determine_order_tag(o, position_map, account_id='HAMPRO')
                    for o in filled_orders:
                        if not o.get('tag'):
                            o['tag'] = determine_order_tag(o, position_map, account_id='HAMPRO')
                except Exception as tag_err:
                    logger.warning(f"[HAMMER_TAG] Could not enrich tags: {tag_err}")
            
            out = {"open_orders": open_orders, "filled_orders": filled_orders}
            if cache_key:
                _orders_response_cache[cache_key] = (time.time() + _ORDERS_CACHE_TTL, out)
            return out
        except Exception as e:
            logger.error(f"[HAMMER_ORDERS] Error in Hammer orders block: {e}", exc_info=True)
            return {"open_orders": [], "filled_orders": []}

    # 2. IBKR MODE (GUN or PED - Both use Port 4001 via Gateway)
    all_orders = {}
    native_fills = []
    target_account = "IBKR_PED" if active_mode == AccountMode.IBKR_PED.value else "IBKR_GUN"
    
    # Force Gateway Port 4001 as per user requirement
    TARGET_PORT = 4001 
    
    # A. Native Client - DISABLED: We use IB_INSYNC connector instead
    # Native client causes connection issues and is not needed when using IB_INSYNC
    # If you need native client, uncomment and fix the connection logic
    # For now, we rely solely on IB_INSYNC connector (get_open_orders_isolated_sync)

    # B. IB_INSYNC – fetch ALL open orders (reqAllOpenOrders) so UI shows every order on account; cancel uses reqOpenOrders (our session only)
    try:
        import asyncio
        import json
        from app.psfalgo.ibkr_connector import get_open_orders_all_isolated_sync, get_filled_orders_isolated_sync, get_ibkr_connector
        loop = asyncio.get_event_loop()
        ib_orders = await loop.run_in_executor(None, lambda: get_open_orders_all_isolated_sync(target_account))
        
        # Pre-check IBKR connection before calling filled orders (avoid 18s timeout when disconnected)
        ibkr_conn = get_ibkr_connector(account_type=target_account, create_if_missing=False)
        ibkr_connected = ibkr_conn and ibkr_conn.connected if ibkr_conn else False
        
        ib_fills = []
        if ibkr_connected:
            ib_fills = await loop.run_in_executor(None, lambda: get_filled_orders_isolated_sync(target_account)) or []
        
        for o in (ib_orders or []):
            if o.get('order_id') and o['order_id'] not in all_orders:
                all_orders[o['order_id']] = o
        # Merge open orders from Redis (orders pushed after place_order show up before next IBKR fetch)
        try:
            from app.core.redis_client import get_redis_client
            r = get_redis_client()
            if r and hasattr(r, 'get'):
                orders_key = f"psfalgo:open_orders:{target_account}"
                raw = r.get(orders_key)
                if raw:
                    s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                    redis_orders = json.loads(s) if isinstance(s, str) else s
                    # Handle wrapped format vs legacy list
                    if isinstance(redis_orders, dict) and 'orders' in redis_orders:
                        redis_orders = redis_orders['orders']
                    if isinstance(redis_orders, list):
                        for o in redis_orders:
                            oid = o.get('order_id')
                            if oid is not None and oid not in all_orders:
                                all_orders[oid] = o
        except Exception as _:
            pass
        for f in (ib_fills or []):
            if not any(nf.get('order_id') == f.get('order_id') for nf in native_fills):
                native_fills.append(f)
        
        # FALLBACK: If IBKR returned 0 fills, try CSV-based DailyFillsStore
        if not native_fills:
            try:
                from app.trading.daily_fills_store import get_daily_fills_store
                csv_fills = get_daily_fills_store().get_all_fills(target_account)
                if csv_fills:
                    native_fills.extend(csv_fills)
                    logger.info(f"[FILLS_FALLBACK] Loaded {len(csv_fills)} fills from CSV (IBKR returned 0)")
            except Exception as csv_err:
                logger.debug(f"[FILLS_FALLBACK] CSV fallback failed: {csv_err}")
    except Exception as e:
        logger.error(f"[IB_INSYNC] Error: {e}")
        # Even on total IBKR failure, try CSV fallback
        try:
            from app.trading.daily_fills_store import get_daily_fills_store
            csv_fills = get_daily_fills_store().get_all_fills(target_account)
            if csv_fills:
                native_fills.extend(csv_fills)
                logger.info(f"[FILLS_FALLBACK] Loaded {len(csv_fills)} fills from CSV (IBKR error)")
        except Exception:
            pass

    # C. Enrich & Tag (pozisyonlar açık hesaba göre; get_positions(account_id=...) ile Pozisyonlar ekranı ile aynı kaynak)
    try:
        from app.api.trading_routes import get_positions
        pos_resp = await get_positions(account_id=target_account)
        positions = pos_resp.get('positions', []) if isinstance(pos_resp, dict) else []
        position_map = {p['symbol']: p for p in positions}
        
        controller = get_order_controller()
        if controller:
            active_orders = controller.get_active_orders(account_id=target_account)
            internal_map = {o.broker_order_id: o for o in active_orders if o.broker_order_id}
            
            for o in all_orders.values():
                match = internal_map.get(str(o.get('order_id')))
                if match:
                    if not o.get('timestamp'): o['timestamp'] = match.created_at.timestamp()
                    if not o.get('price'): o['price'] = match.price
                    o['internal_tracked'] = True
                    o['parent_intent_id'] = match.parent_intent_id

        _our_client_id = 12 if target_account == 'IBKR_PED' else 11
        for o in all_orders.values():
            o['tag'] = determine_order_tag(o, position_map, account_id=target_account)
            if 'filled_qty' not in o: o['filled_qty'] = o.get('filled', 0)
            if 'remaining_qty' not in o: o['remaining_qty'] = o.get('remaining', o.get('qty', 0))
            if 'price' not in o or not o['price']: o['price'] = o.get('limit_price', 0.0)
            cid = o.get('client_id')
            o['cancelable_by_this_session'] = (cid is not None and int(cid) == _our_client_id)
            o['client_id_label'] = f"clientId {cid}" if cid is not None else "clientId ?"

        for o in native_fills:
            o['tag'] = determine_order_tag(o, position_map)
            if 'filled_qty' not in o: o['filled_qty'] = o.get('qty', 0)
            o['remaining_qty'] = 0

    except Exception as e: logger.error(f"[TAG] Error adding tags: {e}")

    out = {"open_orders": list(all_orders.values()), "filled_orders": native_fills}
    if cache_key:
        _orders_response_cache[cache_key] = (time.time() + _ORDERS_CACHE_TTL, out)
    return out

@router.get("/orders/pending")
async def get_pending_orders():
    """Get pending orders (remaining > 0)."""
    try:
        resp = await get_orders()
        open_orders = resp.get('open_orders', [])
        pending = []
        for o in open_orders:
            remaining = o.get('remaining_qty', o.get('remaining', o.get('qty', 0)))
            if remaining > 0:
                o['total_qty'] = o.get('filled_qty', 0) + remaining
                # Add human readable time if missing
                if not o.get('time') and o.get('timestamp'):
                    o['time'] = datetime.fromtimestamp(o['timestamp']).strftime('%H:%M:%S')
                pending.append(o)
        return {'success': True, 'orders': pending}
    except Exception as e:
        logger.error(f"[Pending Orders] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orders/filled")
async def get_filled_orders():
    """Get filled orders (today)."""
    try:
        resp = await get_orders()
        open_orders = resp.get('open_orders', [])
        filled_raw = resp.get('filled_orders', [])
        filled = []
        for o in open_orders:
            if o.get('remaining_qty', 1) == 0 and o.get('filled_qty', 0) > 0:
                if not o.get('time') and o.get('timestamp'):
                    o['time'] = datetime.fromtimestamp(o['timestamp']).strftime('%H:%M:%S')
                filled.append(o)
        for o in filled_raw:
            if not o.get('time') and o.get('timestamp'):
                o['time'] = datetime.fromtimestamp(o['timestamp']).strftime('%H:%M:%S')
            filled.append(o)
        filled.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return {'success': True, 'orders': filled}
    except Exception as e:
        logger.error(f"[Filled Orders] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
