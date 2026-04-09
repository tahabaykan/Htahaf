"""
Admin Panel API Routes

System health monitoring endpoints for:
- Redis data freshness (truth ticks, L1, TSS, positions, orders)
- Worker/Terminal heartbeats
- Account data freshness (HAMPRO, IBKR_PED)
- Pipeline health checks

CRITICAL: Redis keys must match actual system keys:
  - psfalgo:befday:positions:{account_id}  (BEFDAY capture)
  - psfalgo:positions:{account_id}         (current positions)
  - psfalgo:minmax:daily:{account_id}      (MinMax bands)
  - psfalgo:open_orders:{account_id}       (active orders)
  - psfalgo:dual_process:state             (dual process state)
  - psfalgo:rev_queue:{account_id}         (REV order queue)
"""

import time
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from fastapi import APIRouter

from app.core.logger import logger

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def _get_redis():
    """Get sync Redis client."""
    try:
        from app.core.redis_client import get_redis_client
        rc = get_redis_client()
        if rc and rc.sync:
            return rc.sync
        return None
    except Exception:
        try:
            import redis
            return redis.Redis(host='localhost', port=6379, db=0, decode_responses=True, socket_timeout=2)
        except Exception:
            return None


def _safe_json_parse(raw):
    """Safe JSON parse."""
    if raw is None:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        return json.loads(raw)
    except Exception:
        return None


def _age_str(seconds: float) -> str:
    """Convert seconds to human-readable age string."""
    if seconds < 0:
        return "future?"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f}m"
    if seconds < 86400:
        return f"{seconds/3600:.1f}h"
    return f"{seconds/86400:.1f}d"


def _freshness_status(age_sec: float, fresh_limit: float = 120, warn_limit: float = 600) -> str:
    """Return freshness status: fresh/stale/dead."""
    if age_sec <= fresh_limit:
        return "fresh"
    if age_sec <= warn_limit:
        return "stale"
    return "dead"


@router.get("/health")
async def get_system_health():
    """
    Comprehensive system health check.
    Returns data freshness for all major data pipelines.
    """
    r = _get_redis()
    if not r:
        return {"success": False, "error": "Redis not available"}

    now = time.time()
    health = {}

    # ═══════════════════════════════════════════
    # 1. TRUTH TICKS (tt:ticks:*)
    # ═══════════════════════════════════════════
    try:
        tt_keys = list(r.scan_iter("tt:ticks:*", count=1000))
        tt_count = len(tt_keys)
        tt_fresh = 0
        tt_stale = 0
        tt_dead = 0
        tt_total_ticks = 0
        tt_newest_tick_age = float('inf')
        tt_oldest_tick_age = 0
        tt_sample_symbols = []

        for key in tt_keys[:200]:  # Sample first 200
            raw = r.get(key)
            if not raw:
                continue
            data = _safe_json_parse(raw)
            if not data or not isinstance(data, list):
                continue

            sym = key.decode().replace("tt:ticks:", "") if isinstance(key, bytes) else key.replace("tt:ticks:", "")
            tick_count = len(data)
            tt_total_ticks += tick_count

            if data:
                last_ts = max(t.get('ts', 0) for t in data if isinstance(t, dict))
                if last_ts > 0:
                    age = now - last_ts
                    status = _freshness_status(age, fresh_limit=300, warn_limit=3600)
                    if status == "fresh":
                        tt_fresh += 1
                    elif status == "stale":
                        tt_stale += 1
                    else:
                        tt_dead += 1

                    if age < tt_newest_tick_age:
                        tt_newest_tick_age = age
                    if age > tt_oldest_tick_age:
                        tt_oldest_tick_age = age

                    if len(tt_sample_symbols) < 5:
                        tt_sample_symbols.append({
                            "symbol": sym,
                            "ticks": tick_count,
                            "last_tick_age": _age_str(age),
                            "status": status
                        })

        health["truth_ticks"] = {
            "total_symbols": tt_count,
            "fresh": tt_fresh,
            "stale": tt_stale,
            "dead": tt_dead,
            "total_ticks": tt_total_ticks,
            "newest_tick_age": _age_str(tt_newest_tick_age) if tt_newest_tick_age < float('inf') else "N/A",
            "oldest_tick_age": _age_str(tt_oldest_tick_age) if tt_oldest_tick_age > 0 else "N/A",
            "samples": tt_sample_symbols,
            "status": "fresh" if tt_fresh > tt_count * 0.5 else ("stale" if tt_stale > 0 else "dead")
        }
    except Exception as e:
        health["truth_ticks"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 2. L1 MARKET DATA (live:* hashes from Hammer feed)
    # ═══════════════════════════════════════════
    try:
        l1_keys = list(r.scan_iter("live:*", count=1000))
        l1_count = len(l1_keys)
        l1_with_bid = 0
        l1_samples = []

        for key in l1_keys[:200]:
            sym = key.decode().replace("live:", "") if isinstance(key, bytes) else key.replace("live:", "")
            bid_raw = r.hget(key, "bid")
            ask_raw = r.hget(key, "ask")
            bid = float(bid_raw) if bid_raw else None
            ask = float(ask_raw) if ask_raw else None
            if bid and bid > 0 and ask and ask > 0:
                l1_with_bid += 1
            ttl = r.ttl(key)
            status = "fresh" if (ttl and ttl > 1800) else ("stale" if ttl and ttl > 0 else "dead")

            if len(l1_samples) < 5:
                l1_samples.append({
                    "symbol": sym,
                    "bid": bid,
                    "ask": ask,
                    "ttl": ttl,
                    "status": status
                })

        health["l1_market_data"] = {
            "total_symbols": l1_count,
            "with_bid_ask": l1_with_bid,
            "samples": l1_samples,
            "status": "fresh" if l1_with_bid > l1_count * 0.5 else ("stale" if l1_count > 0 else "dead")
        }
    except Exception as e:
        health["l1_market_data"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 3. TSS v2 SCORES (tss:v2:*)
    # ═══════════════════════════════════════════
    try:
        tss_keys = list(r.scan_iter("tss:v2:*", count=1000))
        tss_count = len(tss_keys)
        tss_newest = float('inf')
        tss_samples = []

        for key in tss_keys[:50]:
            raw = r.get(key)
            data = _safe_json_parse(raw)
            if not data:
                continue
            sym = key.decode().replace("tss:v2:", "") if isinstance(key, bytes) else key.replace("tss:v2:", "")
            ts = data.get('updated_at', 0) or data.get('ts', 0)
            age = now - ts if ts > 0 else float('inf')
            if age < tss_newest:
                tss_newest = age

            if len(tss_samples) < 5:
                tss_samples.append({
                    "symbol": sym,
                    "score": data.get('tss_score') or data.get('score'),
                    "recency": data.get('recency_factor'),
                    "age": _age_str(age) if age < float('inf') else "N/A"
                })

        health["tss_v2"] = {
            "total_symbols": tss_count,
            "newest_age": _age_str(tss_newest) if tss_newest < float('inf') else "N/A",
            "samples": tss_samples,
            "status": "fresh" if tss_newest < 600 else ("stale" if tss_count > 0 else "dead")
        }
    except Exception as e:
        health["tss_v2"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 4. BEFDAY DATA (psfalgo:befday:positions:{account})
    # ═══════════════════════════════════════════
    try:
        def _befday_info(account_id, label):
            key = f"psfalgo:befday:positions:{account_id}"
            date_key = f"psfalgo:befday:date:{account_id}"
            raw = r.get(key)
            data = _safe_json_parse(raw)
            stored_date = r.get(date_key)
            if stored_date:
                stored_date = stored_date.decode() if isinstance(stored_date, bytes) else stored_date
            
            if not data:
                return {"label": label, "status": "missing", "position_count": 0, "date": stored_date or "N/A"}
            
            if isinstance(data, list):
                pos_count = len(data)
            elif isinstance(data, dict):
                pos_count = len([k for k in data.keys() if k != '_meta'])
            else:
                pos_count = 0
            
            return {
                "label": label,
                "position_count": pos_count,
                "date": stored_date or "N/A",
                "status": "fresh" if pos_count > 0 else "empty"
            }

        health["befday"] = {
            "hampro": _befday_info("HAMPRO", "HAMPRO"),
            "ibkr_ped": _befday_info("IBKR_PED", "IBKR_PED"),
        }
    except Exception as e:
        health["befday"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 5. CURRENT POSITIONS (psfalgo:positions:{account})
    # ═══════════════════════════════════════════
    try:
        def _positions_info(account_id, label):
            key = f"psfalgo:positions:{account_id}"
            raw = r.get(key)
            data = _safe_json_parse(raw)
            if not data or not isinstance(data, dict):
                return {"label": label, "status": "empty", "count": 0, "age": "N/A"}
            
            meta = data.get('_meta', {})
            updated_at = meta.get('updated_at', 0)
            age = now - updated_at if updated_at else float('inf')
            pos_count = len([k for k in data.keys() if k != '_meta'])
            
            return {
                "label": label,
                "count": pos_count,
                "age": _age_str(age) if age < float('inf') else "N/A",
                "status": _freshness_status(age, fresh_limit=300, warn_limit=900) if updated_at else "missing"
            }

        health["positions"] = {
            "hampro": _positions_info("HAMPRO", "HAMPRO"),
            "ibkr_ped": _positions_info("IBKR_PED", "IBKR_PED"),
        }
    except Exception as e:
        health["positions"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 6. ACTIVE ORDERS (psfalgo:open_orders:{account})
    # ═══════════════════════════════════════════
    try:
        def _orders_info(account_id, label):
            key = f"psfalgo:open_orders:{account_id}"
            raw = r.get(key)
            data = _safe_json_parse(raw)
            if not data:
                return {"label": label, "count": 0, "status": "empty"}
            
            if isinstance(data, list):
                count = len(data)
            elif isinstance(data, dict):
                count = len([k for k in data.keys() if k != '_meta'])
            else:
                count = 0
            
            return {"label": label, "count": count, "status": "ok" if count > 0 else "empty"}

        health["orders"] = {
            "hampro": _orders_info("HAMPRO", "HAMPRO"),
            "ibkr_ped": _orders_info("IBKR_PED", "IBKR_PED"),
        }
    except Exception as e:
        health["orders"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 7. DUAL PROCESS STATE (psfalgo:dual_process:state)
    # ═══════════════════════════════════════════
    try:
        dual_state = _safe_json_parse(r.get("psfalgo:dual_process:state"))
        xnl_running = r.get("psfalgo:xnl:running")
        xnl_running_account = r.get("psfalgo:xnl:running_account")
        
        if xnl_running:
            xnl_running = xnl_running.decode() if isinstance(xnl_running, bytes) else xnl_running
        if xnl_running_account:
            xnl_running_account = xnl_running_account.decode() if isinstance(xnl_running_account, bytes) else xnl_running_account
        
        if dual_state:
            health["dual_process"] = {
                "state": dual_state.get('state', 'unknown'),
                "accounts": dual_state.get('accounts', []),
                "current_account": dual_state.get('current_account', 'N/A'),
                "loop_count": dual_state.get('loop_count', 0),
                "started_at": dual_state.get('started_at', 'N/A'),
                "xnl_running": xnl_running,
                "xnl_running_account": xnl_running_account,
                "status": "running" if dual_state.get('state') == 'running' else dual_state.get('state', 'unknown')
            }
        else:
            health["dual_process"] = {
                "status": "no_data",
                "xnl_running": xnl_running,
                "xnl_running_account": xnl_running_account,
                "message": "No dual process state found in Redis"
            }
    except Exception as e:
        health["dual_process"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 8. REV QUEUE STATUS (psfalgo:rev_queue:{account})
    # ═══════════════════════════════════════════
    try:
        def _rev_queue_info(account_id, label):
            key = f"psfalgo:rev_queue:{account_id}"
            queue_len = r.llen(key)
            preview = []
            if queue_len > 0:
                # Peek at first 3 items (non-destructive)
                raw_items = r.lrange(key, 0, 2)
                for item in raw_items:
                    data = _safe_json_parse(item)
                    if data:
                        preview.append({
                            "symbol": data.get("symbol", "?"),
                            "action": data.get("action", "?"),
                            "qty": data.get("qty", "?"),
                            "created_at": data.get("created_at", "NO_TIMESTAMP"),
                        })
            return {"label": label, "queue_length": queue_len, "preview": preview}

        health["rev_queue"] = {
            "hampro": _rev_queue_info("HAMPRO", "HAMPRO"),
            "ibkr_ped": _rev_queue_info("IBKR_PED", "IBKR_PED"),
        }
    except Exception as e:
        health["rev_queue"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 9. MINMAX DATA (psfalgo:minmax:daily:{account})
    # ═══════════════════════════════════════════
    try:
        def _minmax_info(account_id, label):
            key = f"psfalgo:minmax:daily:{account_id}"
            raw = r.get(key)
            data = _safe_json_parse(raw)
            if not(data and isinstance(data, dict)):
                return {"label": label, "status": "missing", "count": 0}
            meta = data.get('_meta', {})
            computed_at = meta.get('computed_at', 0)
            age = now - computed_at if computed_at else float('inf')
            count = len([k for k in data.keys() if k != '_meta'])
            computed_date = meta.get('date', 'N/A')
            return {
                "label": label,
                "count": count,
                "computed_date": computed_date,
                "age": _age_str(age) if age < float('inf') else "N/A",
                "status": "fresh" if computed_date == datetime.now().strftime('%Y-%m-%d') else "stale"
            }

        health["minmax"] = {
            "hampro": _minmax_info("HAMPRO", "HAMPRO"),
            "ibkr_ped": _minmax_info("IBKR_PED", "IBKR_PED"),
        }
    except Exception as e:
        health["minmax"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 10. HAMMER CONNECTION STATUS
    # ═══════════════════════════════════════════
    try:
        from app.live.hammer_feed import get_hammer_feed
        feed = get_hammer_feed()
        if feed and feed.hammer_client:
            hc = feed.hammer_client
            connected = hc.is_connected()
            l1_count = getattr(feed, '_l1update_count', 0)
            last_l1_time = getattr(hc, '_last_l1_update_time', 0)
            l1_age = now - last_l1_time if last_l1_time > 0 else float('inf')
            
            health["hammer_connection"] = {
                "connected": connected,
                "l1_updates_received": l1_count,
                "last_l1_age": _age_str(l1_age) if l1_age < float('inf') else "N/A",
                "status": "fresh" if connected and l1_age < 120 else ("stale" if connected else "dead")
            }
        else:
            health["hammer_connection"] = {"connected": False, "status": "dead", "message": "HammerFeed not initialized"}
    except Exception as e:
        health["hammer_connection"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 11. REDIS GENERAL INFO
    # ═══════════════════════════════════════════
    try:
        info = r.info("memory")
        db_size = r.dbsize()
        health["redis"] = {
            "connected": True,
            "total_keys": db_size,
            "used_memory_human": info.get('used_memory_human', 'N/A'),
            "status": "ok"
        }
    except Exception as e:
        health["redis"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # 12. EXCLUDED LIST
    # ═══════════════════════════════════════════
    try:
        import os, csv as _csv
        excluded_path = os.path.join(os.getcwd(), 'qe_excluded.csv')
        excluded_symbols = []
        if os.path.exists(excluded_path):
            with open(excluded_path, 'r', encoding='utf-8') as f:
                reader = _csv.reader(f)
                for row in reader:
                    if row:
                        excluded_symbols.extend([s.strip().upper() for s in row if s.strip()])
        health["excluded_list"] = {
            "count": len(excluded_symbols),
            "symbols": sorted(set(excluded_symbols)),
            "status": "ok"
        }
    except Exception as e:
        health["excluded_list"] = {"error": str(e), "status": "error"}

    # ═══════════════════════════════════════════
    # OVERALL STATUS
    # ═══════════════════════════════════════════
    critical_systems = ['truth_ticks', 'l1_market_data', 'hammer_connection', 'redis']
    overall_status = "healthy"
    issues = []
    
    for sys_name in critical_systems:
        sys_data = health.get(sys_name, {})
        if sys_data.get('status') == 'dead' or sys_data.get('status') == 'error':
            overall_status = "critical"
            issues.append(f"{sys_name}: {sys_data.get('status')}")
        elif sys_data.get('status') == 'stale':
            if overall_status == "healthy":
                overall_status = "warning"
            issues.append(f"{sys_name}: stale")

    health["overall"] = {
        "status": overall_status,
        "issues": issues,
        "checked_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "server_time": now
    }

    return {"success": True, "health": health}
