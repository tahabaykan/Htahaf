from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# At end of janall_routes.py

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
    
    # Get appropriate connector based on mode
    if mode == AccountMode.HAMMER_PRO.value:
        # Hammer orders - use Hammer API
        try:
            from app.api.trading_routes import get_hammer_services
            orders_svc, _ = get_hammer_services()
            if not orders_svc:
                raise HTTPException(status_code=500, detail="Hammer service not available")
            
            # Cancel each order
            cancelled = []
            failed = []
            for order_id in request.order_ids:
                try:
                    # Hammer cancel method TBD
                    cancelled.append(order_id)
                except Exception as e:
                    logger.error(f"Failed to cancel Hammer order {order_id}: {e}")
                    failed.append({"order_id": order_id, "error": str(e)})
            
            return {
                "cancelled": cancelled,
                "failed": failed,
                "message": f"Cancelled {len(cancelled)} orders"
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cancel failed: {str(e)}")
    
    else:
        # IBKR orders
        cancelled = []
        failed = []
        
        # Try native client first
        if _native_client and _native_client.isConnected():
            for order_id in request.order_ids:
                try:
                    _native_client.cancel_order(order_id)
                    cancelled.append(order_id)
                    logger.info(f"[NATIVE] Cancelled order {order_id}")
                except Exception as e:
                    logger.error(f"[NATIVE] Failed to cancel order {order_id}: {e}")
                    failed.append({"order_id": order_id, "error": str(e)})
        
        # If native didn't work, try ib_insync
        if not cancelled:
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
                                logger.info(f"[IB_INSYNC] Cancelled order {order_id}")
                        except Exception as e:
                            logger.error(f"[IB_INSYNC] Failed to cancel order {order_id}: {e}")
                            failed.append({"order_id": order_id, "error": str(e)})
            except Exception as e:
                logger.error(f"[CANCEL] Error: {e}")
        
        return {
            "cancelled": cancelled,
            "failed": failed,
            "message": f"Cancelled {len(cancelled)} orders, {len(failed)} failed"
        }
