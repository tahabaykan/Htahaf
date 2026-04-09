"""
Operations Dashboard API Routes

Aggregates data from all accounts for a unified operations dashboard.
Combines: Positions, Open Orders, Filled Orders, REV Orders, Exposure, Cycle Reports.
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import json
from datetime import datetime

from app.core.logger import logger

router = APIRouter(prefix="/api/ops-dashboard", tags=["Operations Dashboard"])

ACCOUNTS = ["HAMPRO", "IBKR_PED"]


def _get_redis():
    try:
        from app.core.redis_client import get_redis_client
        return get_redis_client()
    except Exception:
        return None


def _safe_json(raw) -> Any:
    """Safely parse JSON from Redis bytes/str."""
    if raw is None:
        return None
    try:
        s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
        return json.loads(s)
    except Exception:
        return None


def _get_positions(r, account_id: str) -> List[Dict]:
    """Get positions from Redis for an account."""
    try:
        data = _safe_json(r.get(f"psfalgo:positions:{account_id}"))
        if not data or not isinstance(data, dict):
            return []
        result = []
        for sym, pos in data.items():
            if sym == '_meta':  # Skip internal metadata
                continue
            if isinstance(pos, dict):
                pos['symbol'] = pos.get('symbol', sym)
                pos['account'] = account_id
                result.append(pos)
        return result
    except Exception as e:
        logger.debug(f"[OpsDash] positions error {account_id}: {e}")
        return []


def _get_open_orders(r, account_id: str) -> List[Dict]:
    """Get open orders from Redis."""
    try:
        data = _safe_json(r.get(f"psfalgo:open_orders:{account_id}"))
        if not data:
            return []
        # Handle wrapped format vs legacy list
        if isinstance(data, dict) and 'orders' in data:
            orders = data['orders']
        elif isinstance(data, list):
            orders = data
        else:
            return []
        for o in orders:
            o['account'] = account_id
        return orders
    except Exception as e:
        logger.debug(f"[OpsDash] orders error {account_id}: {e}")
        return []


def _get_exposure(r, account_id: str) -> Dict:
    """Get exposure data from Redis."""
    try:
        data = _safe_json(r.get(f"psfalgo:exposure:{account_id}"))
        if data and isinstance(data, dict):
            data['account'] = account_id
            return data
        return {"account": account_id, "pot_total": 0, "pot_max": 0, "pct": 0}
    except Exception:
        return {"account": account_id, "pot_total": 0, "pot_max": 0, "pct": 0}


def _get_befday(r, account_id: str) -> Dict:
    """Get BEFDAY snapshot from Redis."""
    try:
        data = _safe_json(r.get(f"psfalgo:befday:positions:{account_id}"))
        if data:
            return {"account": account_id, "data": data, "available": True}
        return {"account": account_id, "data": None, "available": False}
    except Exception:
        return {"account": account_id, "data": None, "available": False}


def _get_rev_orders(r, account_id: str) -> List[Dict]:
    """Get active REV orders."""
    try:
        orders = _get_open_orders(r, account_id)
        rev_orders = []
        for o in orders:
            tag = (o.get('tag', '') or o.get('strategy_tag', '') or '').upper()
            if 'REV_' in tag:
                o['rev_type'] = 'TP' if '_TP' in tag else ('RELOAD' if '_RELOAD' in tag else 'OTHER')
                o['direction'] = 'LONG' if '_LONG_' in tag else ('SHORT' if '_SHORT_' in tag else '?')
                rev_orders.append(o)
        return rev_orders
    except Exception:
        return []


def _get_filled_today(r, account_id: str) -> List[Dict]:
    """Get today's fills from Redis stream or fill log."""
    fills = []
    try:
        # Check fill log key
        fill_key = f"psfalgo:fills:today:{account_id}"
        data = _safe_json(r.get(fill_key))
        if data and isinstance(data, list):
            for f in data:
                f['account'] = account_id
            return data
        
        # Fallback: check stream
        stream_key = f"psfalgo:stream:fills:{account_id}"
        try:
            entries = r.xrevrange(stream_key, count=200)
            if entries:
                for entry_id, fields in entries:
                    fill = {}
                    for k, v in fields.items():
                        key = k.decode() if isinstance(k, bytes) else k
                        val = v.decode() if isinstance(v, bytes) else v
                        fill[key] = val
                    fill['account'] = account_id
                    fill['stream_id'] = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                    fills.append(fill)
        except Exception:
            pass
        
        return fills
    except Exception as e:
        logger.debug(f"[OpsDash] fills error {account_id}: {e}")
        return fills


def _get_pending_queue(r) -> List[Dict]:
    """Get pending orders in Redis queue."""
    try:
        items = r.lrange("psfalgo:orders:pending", 0, -1)
        if not items:
            return []
        result = []
        for item in items:
            data = _safe_json(item)
            if data:
                result.append(data)
        return result
    except Exception:
        return []


def _get_frontlama_stats(r) -> Dict:
    """Get Frontlama activity stats from Redis."""
    try:
        data = _safe_json(r.get("psfalgo:frontlama:stats"))
        return data or {}
    except Exception:
        return {}


def _get_xnl_status(r) -> Dict:
    """Get XNL engine running status."""
    try:
        running = r.get("psfalgo:xnl:running")
        running_acc = r.get("psfalgo:xnl:running_account")
        
        run_val = (running.decode() if isinstance(running, bytes) else running) if running else "0"
        acc_val = (running_acc.decode() if isinstance(running_acc, bytes) else running_acc) if running_acc else ""
        
        return {
            "running": str(run_val).strip() == "1",
            "account": str(acc_val).strip() if acc_val else None
        }
    except Exception:
        return {"running": False, "account": None}


@router.get("/data")
async def get_dashboard_data():
    """
    Get ALL operational data for the dashboard.
    Single endpoint that aggregates everything needed.
    """
    try:
        r = _get_redis()
        if not r:
            return JSONResponse(status_code=503, content={"error": "Redis unavailable"})
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "xnl_status": _get_xnl_status(r),
            "accounts": {},
            "pending_queue": _get_pending_queue(r),
            "frontlama_stats": _get_frontlama_stats(r),
        }
        
        total_positions = 0
        total_orders = 0
        total_fills = 0
        total_rev = 0
        
        for account in ACCOUNTS:
            positions = _get_positions(r, account)
            open_orders = _get_open_orders(r, account)
            rev_orders = _get_rev_orders(r, account)
            fills = _get_filled_today(r, account)
            exposure = _get_exposure(r, account)
            befday = _get_befday(r, account)
            
            # Calculate account-level stats
            long_positions = [p for p in positions if float(p.get('qty', p.get('quantity', 0)) or 0) > 0]
            short_positions = [p for p in positions if float(p.get('qty', p.get('quantity', 0)) or 0) < 0]
            
            buy_orders = [o for o in open_orders if str(o.get('action', o.get('side', ''))).upper() == 'BUY']
            sell_orders = [o for o in open_orders if str(o.get('action', o.get('side', ''))).upper() == 'SELL']
            
            pot_total = float(exposure.get('pot_total', 0))
            pot_max = float(exposure.get('pot_max', 1))
            exposure_pct = (pot_total / pot_max * 100) if pot_max > 0 else 0
            
            account_data = {
                "positions": positions,
                "open_orders": open_orders,
                "rev_orders": rev_orders,
                "fills": fills,
                "exposure": {
                    "pot_total": pot_total,
                    "pot_max": pot_max,
                    "pct": round(exposure_pct, 2),
                    "raw": exposure,
                },
                "befday": befday,
                "stats": {
                    "position_count": len(positions),
                    "long_count": len(long_positions),
                    "short_count": len(short_positions),
                    "order_count": len(open_orders),
                    "buy_order_count": len(buy_orders),
                    "sell_order_count": len(sell_orders),
                    "rev_order_count": len(rev_orders),
                    "fill_count": len(fills),
                }
            }
            
            result["accounts"][account] = account_data
            total_positions += len(positions)
            total_orders += len(open_orders)
            total_fills += len(fills)
            total_rev += len(rev_orders)
        
        result["totals"] = {
            "positions": total_positions,
            "open_orders": total_orders,
            "fills": total_fills,
            "rev_orders": total_rev,
            "pending_queue": len(result["pending_queue"]),
        }
        
        # Get cycle report summary
        try:
            from app.core.cycle_reporter import get_cycle_reporter
            reporter = get_cycle_reporter()
            report = reporter.get_latest_report()
            if report:
                result["last_cycle"] = {
                    "cycle_id": report.get("cycle_id"),
                    "start_time": report.get("start_time"),
                    "end_time": report.get("end_time"),
                    "duration_seconds": report.get("duration_seconds"),
                    "total_symbols": report.get("total_symbols"),
                    "sent_count": report.get("sent_count"),
                    "blocked_count": report.get("blocked_count"),
                    "engine_stats": report.get("engine_stats", {}),
                }
            else:
                result["last_cycle"] = None
        except Exception:
            result["last_cycle"] = None
        
        return JSONResponse(content=result)
    
    except Exception as e:
        logger.error(f"[OpsDash] Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/fills/{account_id}")
async def get_account_fills(account_id: str, limit: int = 200):
    """Get fills for a specific account."""
    try:
        r = _get_redis()
        if not r:
            return JSONResponse(status_code=503, content={"error": "Redis unavailable"})
        
        fills = _get_filled_today(r, account_id)
        return JSONResponse(content={
            "account": account_id,
            "fills": fills[:limit],
            "count": len(fills),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
