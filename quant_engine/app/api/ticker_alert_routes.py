"""app/api/ticker_alert_routes.py

API routes for ticker alert functionality (session high/low tracking).
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime

from app.core.logger import logger
from app.market_data.ticker_alert_engine import get_ticker_alert_engine, TickerAlert

router = APIRouter(prefix="/api/ticker-alerts", tags=["ticker-alerts"])


@router.get("/recent")
def get_recent_alerts(
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of alerts to return"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type: NEW_HIGH or NEW_LOW"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol")
) -> dict:
    """
    Get recent ticker alert events.
    
    Returns:
        {
            "success": bool,
            "alerts": List[TickerAlert],
            "count": int
        }
    """
    try:
        engine = get_ticker_alert_engine()
        
        # Validate event_type
        if event_type and event_type not in ["NEW_HIGH", "NEW_LOW"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event_type: {event_type}. Must be 'NEW_HIGH' or 'NEW_LOW'"
            )
        
        alerts = engine.get_recent_alerts(limit=limit, event_type=event_type, symbol=symbol)
        
        return {
            "success": True,
            "alerts": [alert.to_dict() for alert in alerts],
            "count": len(alerts)
        }
    except Exception as e:
        logger.error(f"Error getting recent alerts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/session/create")
def create_tab_session(
    session_id: Optional[str] = Query(None, description="Optional session ID")
) -> dict:
    """
    Create a new tab-based session for ticker alert tracking.
    
    Args:
        session_id: Optional session ID (if not provided, uses timestamp)
    
    Returns:
        {
            "success": bool,
            "session_id": str
        }
    """
    try:
        engine = get_ticker_alert_engine()
        
        if not session_id:
            session_id = f"tab_{int(datetime.now().timestamp() * 1000)}"
        
        if engine:
            engine.create_tab_session(session_id)
        else:
            logger.warning("TickerAlertEngine not available, creating session ID only")
        
        return {
            "success": True,
            "session_id": session_id
        }
    except Exception as e:
        logger.error(f"Error creating tab session: {e}", exc_info=True)
        # Return success with session_id even if engine fails
        if not session_id:
            session_id = f"tab_{int(datetime.now().timestamp() * 1000)}"
        return {
            "success": True,
            "session_id": session_id,
            "warning": "TickerAlertEngine not available"
        }


@router.post("/session/reset")
def reset_session(
    session_id: Optional[str] = None
) -> dict:
    """
    Reset ticker alert session (clear high/low state).
    
    Args:
        session_id: Optional session ID to reset (None = reset global session)
    
    Returns:
        {
            "success": bool,
            "message": str
        }
    """
    try:
        engine = get_ticker_alert_engine()
        engine.reset_session(session_id=session_id)
        
        return {
            "success": True,
            "message": f"Session reset: {session_id or 'global'}"
        }
    except Exception as e:
        logger.error(f"Error resetting session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-cache")
def get_daily_cache(
    symbol: Optional[str] = Query(default=None, description="Get daily cache for specific symbol (None = all symbols"),
    session_id: Optional[str] = Query(default=None, description="Tab session ID (None = global cache")
) -> dict:
    """
    Get daily high/low cache for symbol(s) (for debugging, not shown in UI).
    
    Returns:
        {
            "success": bool,
            "daily_cache": Dict[symbol, {high, low}]
        }
    """
    try:
        engine = get_ticker_alert_engine()
        
        if symbol:
            cache = engine.get_daily_cache(symbol, session_id=session_id)
            return {
                "success": True,
                "daily_cache": {symbol: cache}
            }
        else:
            # Get all caches (would need to iterate through all symbols)
            # For now, return empty (cache is internal, not exposed)
            return {
                "success": True,
                "daily_cache": {},
                "message": "Daily cache data is internal. Use /recent to see alerts."
            }
    except Exception as e:
        logger.error(f"Error getting daily cache: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

