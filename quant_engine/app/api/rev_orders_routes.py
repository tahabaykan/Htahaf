"""
REV Orders API Routes

Provides endpoints for viewing active REV orders across accounts.
REV orders are auto-generated recovery/take-profit orders from RevnBookCheck terminal.
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import json
from datetime import datetime

from app.core.logger import logger

router = APIRouter(prefix="/api/rev-orders", tags=["REV Orders"])


def _get_redis_client():
    """Get Redis client for reading orders."""
    try:
        from app.core.redis_client import get_redis_client
        return get_redis_client()
    except Exception as e:
        logger.error(f"[REV_API] Redis client error: {e}")
        return None


def _get_open_orders_from_redis(account_id: str) -> List[Dict[str, Any]]:
    """Get open orders from Redis for given account."""
    try:
        r = _get_redis_client()
        if not r:
            return []
        
        orders_key = f"psfalgo:open_orders:{account_id}"
        raw = r.get(orders_key)
        if not raw:
            return []
        
        s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
        parsed = json.loads(s) if isinstance(s, str) else []
        # Handle wrapped format vs legacy list
        if isinstance(parsed, dict) and 'orders' in parsed:
            orders = parsed['orders']
        elif isinstance(parsed, list):
            orders = parsed
        else:
            orders = []
        return orders if isinstance(orders, list) else []
    except Exception as e:
        logger.error(f"[REV_API] Error reading orders for {account_id}: {e}")
        return []


def _filter_rev_orders(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter only REV orders from order list."""
    rev_orders = []
    for order in orders:
        tag = order.get('tag', '') or order.get('strategy_tag', '') or ''
        if 'REV_' in tag.upper():
            # Enrich order with parsed tag info
            enriched = {
                **order,
                'tag': tag,
                'is_rev': True,
            }
            
            # Parse tag to extract type (TP/RELOAD) and direction (LONG/SHORT)
            tag_upper = tag.upper()
            if '_TP' in tag_upper:
                enriched['rev_type'] = 'TP'
                enriched['rev_type_label'] = 'Take Profit (Kar Al)'
            elif '_RELOAD' in tag_upper:
                enriched['rev_type'] = 'RELOAD'
                enriched['rev_type_label'] = 'Reload (Gap Recovery)'
            else:
                enriched['rev_type'] = 'UNKNOWN'
                enriched['rev_type_label'] = 'Unknown'
            
            if '_LONG_' in tag_upper:
                enriched['direction'] = 'LONG'
            elif '_SHORT_' in tag_upper:
                enriched['direction'] = 'SHORT'
            else:
                enriched['direction'] = 'UNKNOWN'
            
            rev_orders.append(enriched)
    
    return rev_orders


@router.get("")
@router.get("/")
async def get_all_rev_orders():
    """
    Get all active REV orders across all accounts.
    
    Returns:
        Dict with orders grouped by account.
    """
    try:
        accounts = ["HAMPRO", "IBKR_PED", "IBKR_GUN"]
        result = {
            "accounts": {},
            "total_rev_orders": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        for account in accounts:
            all_orders = _get_open_orders_from_redis(account)
            rev_orders = _filter_rev_orders(all_orders)
            
            result["accounts"][account] = {
                "orders": rev_orders,
                "count": len(rev_orders),
                "total_orders": len(all_orders)
            }
            result["total_rev_orders"] += len(rev_orders)
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"[REV_API] Error getting REV orders: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.get("/by-account/{account_id}")
async def get_rev_orders_by_account(account_id: str):
    """
    Get active REV orders for a specific account.
    
    Args:
        account_id: Account identifier (HAMPRO, IBKR_PED, IBKR_GUN)
    """
    try:
        all_orders = _get_open_orders_from_redis(account_id)
        rev_orders = _filter_rev_orders(all_orders)
        
        return JSONResponse(content={
            "account": account_id,
            "orders": rev_orders,
            "count": len(rev_orders),
            "total_orders_in_account": len(all_orders),
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"[REV_API] Error getting REV orders for {account_id}: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.get("/summary")
async def get_rev_orders_summary():
    """
    Get summary of REV orders with stats per account.
    """
    try:
        accounts = ["HAMPRO", "IBKR_PED", "IBKR_GUN"]
        result = {
            "summary": [],
            "total_by_type": {
                "TP": 0,
                "RELOAD": 0,
                "UNKNOWN": 0
            },
            "total_by_direction": {
                "LONG": 0,
                "SHORT": 0,
                "UNKNOWN": 0
            },
            "total_rev_orders": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        for account in accounts:
            all_orders = _get_open_orders_from_redis(account)
            rev_orders = _filter_rev_orders(all_orders)
            
            account_summary = {
                "account": account,
                "rev_count": len(rev_orders),
                "total_count": len(all_orders),
                "by_type": {"TP": 0, "RELOAD": 0, "UNKNOWN": 0},
                "by_direction": {"LONG": 0, "SHORT": 0, "UNKNOWN": 0},
                "symbols": []
            }
            
            for order in rev_orders:
                rev_type = order.get('rev_type', 'UNKNOWN')
                direction = order.get('direction', 'UNKNOWN')
                
                account_summary["by_type"][rev_type] = account_summary["by_type"].get(rev_type, 0) + 1
                account_summary["by_direction"][direction] = account_summary["by_direction"].get(direction, 0) + 1
                result["total_by_type"][rev_type] = result["total_by_type"].get(rev_type, 0) + 1
                result["total_by_direction"][direction] = result["total_by_direction"].get(direction, 0) + 1
                
                account_summary["symbols"].append(order.get('symbol', 'UNKNOWN'))
            
            result["summary"].append(account_summary)
            result["total_rev_orders"] += len(rev_orders)
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"[REV_API] Error getting REV summary: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )
