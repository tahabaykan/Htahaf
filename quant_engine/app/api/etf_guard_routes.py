"""
API routes for ETF Guard Terminal.

Endpoints:
  GET  /api/etf-guard/status      — Current guard status + ETF prices
  POST /api/etf-guard/start       — Start the guard
  POST /api/etf-guard/stop        — Stop the guard
  POST /api/etf-guard/thresholds  — Update threshold settings
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/etf-guard", tags=["ETF Guard"])


class ThresholdUpdate(BaseModel):
    """Partial threshold update payload."""
    etf: str
    drop_2min: Optional[float] = None
    drop_5min: Optional[float] = None
    rally_2min: Optional[float] = None
    rally_5min: Optional[float] = None


@router.get("/status")
async def get_guard_status() -> Dict[str, Any]:
    """Get ETF Guard status, current ETF prices, and recent events."""
    from app.terminals.etf_guard_terminal import get_etf_guard
    guard = get_etf_guard()
    return guard.get_status()


@router.post("/start")
async def start_guard() -> Dict[str, Any]:
    """Start the ETF Guard Terminal."""
    from app.terminals.etf_guard_terminal import get_etf_guard
    guard = get_etf_guard()
    await guard.start()
    return {"success": True, "message": "ETF Guard started"}


@router.post("/stop")
async def stop_guard() -> Dict[str, Any]:
    """Stop the ETF Guard Terminal."""
    from app.terminals.etf_guard_terminal import get_etf_guard
    guard = get_etf_guard()
    await guard.stop()
    return {"success": True, "message": "ETF Guard stopped"}


@router.post("/thresholds")
async def update_thresholds(updates: list[ThresholdUpdate]) -> Dict[str, Any]:
    """Update threshold settings for one or more ETFs."""
    from app.terminals.etf_guard_terminal import get_etf_guard
    guard = get_etf_guard()
    
    new_th = {}
    for u in updates:
        settings = {}
        if u.drop_2min is not None:
            settings["drop_2min"] = u.drop_2min
        if u.drop_5min is not None:
            settings["drop_5min"] = u.drop_5min
        if u.rally_2min is not None:
            settings["rally_2min"] = u.rally_2min
        if u.rally_5min is not None:
            settings["rally_5min"] = u.rally_5min
        if settings:
            new_th[u.etf] = settings
    
    success = guard.update_thresholds(new_th)
    if success:
        return {"success": True, "message": f"Updated thresholds for {list(new_th.keys())}"}
    raise HTTPException(status_code=500, detail="Failed to update thresholds")
