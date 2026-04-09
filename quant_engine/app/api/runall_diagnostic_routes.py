from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional

from app.psfalgo.runall_engine import get_runall_engine

router = APIRouter(prefix="/api/runall/diagnostic", tags=["runall-diagnostic"])

@router.get("/universal")
async def get_universal_diagnostic() -> Dict[str, Any]:
    """
    Get the UNIVERSAL diagnostic report from the last Runall Cycle.
    Aggregates data from LT Trim, Karbotu, Reducemore, etc.
    """
    try:
        # Try to get from Redis (Source of Truth for Multi-Process)
        from app.core.redis_client import get_redis
        import json
        redis = get_redis()
        if redis:
            cached = redis.get("runall:last_diagnostic")
            if cached:
                cached_data = json.loads(cached)
                return {
                    "status": "ok",
                    "timestamp": cached_data.get('timestamp'),
                    "report": cached_data
                }
    except Exception as e:
        pass # Fallback to local memory

    engine = get_runall_engine()
    if not engine:
        return {"status": "error", "message": "RunallEngine not initialized"}
        
    return {
        "status": "ok",
        "timestamp": engine.last_run_diagnostic.get('timestamp'),
        "report": engine.last_run_diagnostic
    }

@router.get("/last-cursor")
async def get_last_run_cursor() -> Dict[str, Any]:
    """Get just the timestamp to check if update needed"""
    engine = get_runall_engine()
    ts = engine.last_run_diagnostic.get('timestamp', None) if engine else None
    return {"timestamp": ts}
