"""
Agent API Routes — Start/stop observer and view insights.

Dual-provider: Gemini Flash (free) → Claude Haiku (fallback, ~$1/month).

Endpoints:
    POST /api/observer/start         — Start the trading observer
    POST /api/observer/stop          — Stop the trading observer
    GET  /api/observer/status        — Get observer status
    GET  /api/observer/insights      — Get latest insights
    GET  /api/observer/history       — Get insight history
    POST /api/observer/set-claude-key — Set Claude API key (persisted in Redis)
"""

from fastapi import APIRouter, Query
from typing import Optional

from app.core.logger import logger


router = APIRouter(prefix="/api/observer", tags=["Trading Observer Agent"])


@router.post("/start")
async def start_observer(
    api_key: Optional[str] = None,
    claude_api_key: Optional[str] = None,
    interval_minutes: int = Query(default=10, ge=1, le=60),
):
    """
    Start the Trading Observer Agent with dual-provider support.
    
    Provider chain: Gemini Flash (free) → Claude Haiku ($0.05/day fallback).
    
    Args:
        api_key: Gemini API key (optional — will use Redis/env if not provided)
        claude_api_key: Claude API key (optional — will use Redis/env if not provided)
        interval_minutes: Analysis interval in minutes (default 10)
    """
    try:
        from app.agent.trading_observer import start_trading_observer
        
        observer = await start_trading_observer(
            api_key=api_key,
            claude_api_key=claude_api_key,
            interval_seconds=interval_minutes * 60,
        )
        
        return {
            "success": True,
            "message": f"Observer started! Analyzing every {interval_minutes} minutes.",
            "status": observer.status,
        }
    except ValueError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        logger.error(f"[OBSERVER API] Start error: {e}", exc_info=True)
        return {"success": False, "message": f"Failed to start: {e}"}


@router.post("/stop")
async def stop_observer():
    """Stop the Trading Observer Agent."""
    try:
        from app.agent.trading_observer import stop_trading_observer, get_trading_observer
        
        observer = get_trading_observer()
        if not observer or not observer.is_running:
            return {"success": False, "message": "Observer is not running"}
        
        await stop_trading_observer()
        return {"success": True, "message": "Observer stopped"}
    except Exception as e:
        return {"success": False, "message": f"Failed to stop: {e}"}


@router.get("/status")
async def observer_status():
    """Get current observer status including active AI provider."""
    from app.agent.trading_observer import get_trading_observer
    
    observer = get_trading_observer()
    if not observer:
        return {
            "running": False,
            "message": "Observer has not been started yet",
        }
    
    return observer.status


@router.get("/insights")
async def get_latest_insight():
    """
    Get the latest analysis insight.
    
    Returns the most recent AI analysis with:
    - durum (status): NORMAL / DİKKAT / UYARI / KRİTİK
    - skor (score): 0-100
    - gözlemler (observations)
    - anomaliler (anomalies)
    - öneriler (recommendations)
    - provider: gemini / claude (which AI produced this insight)
    """
    from app.agent.trading_observer import get_trading_observer
    
    observer = get_trading_observer()
    if not observer:
        return {"available": False, "message": "Observer not started"}
    
    insight = observer.latest_insight
    if not insight:
        return {"available": False, "message": "No analysis completed yet"}
    
    return {"available": True, "insight": insight}


@router.get("/history")
async def get_insight_history(
    limit: int = Query(default=10, ge=1, le=50),
):
    """Get insight history (most recent first)."""
    from app.agent.trading_observer import get_trading_observer
    
    observer = get_trading_observer()
    if not observer:
        return {"available": False, "insights": []}
    
    history = observer.insights_history
    return {
        "available": True,
        "total": len(history),
        "insights": list(history)[:limit],
    }


@router.get("/snapshot")
async def get_current_snapshot():
    """
    Get the raw metrics snapshot (without LLM analysis).
    Useful for debugging what data the observer is collecting.
    """
    try:
        from app.agent.metrics_collector import MetricsCollector
        collector = MetricsCollector()
        snapshot = collector.collect_snapshot()
        return {"success": True, "snapshot": snapshot}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/set-claude-key")
async def set_claude_api_key(claude_api_key: str):
    """
    Set/update the Claude API key (persisted in Redis for 30 days).
    
    This allows injecting a Claude key without restarting the observer.
    The observer will automatically use it as a fallback when Gemini quota runs out.
    """
    try:
        from app.core.redis_client import get_redis_client
        from app.agent.trading_observer import REDIS_CLAUDE_API_KEY_KEY
        
        client = get_redis_client()
        redis_sync = getattr(client, "sync", client)
        redis_sync.set(REDIS_CLAUDE_API_KEY_KEY, claude_api_key, ex=86400 * 30)
        
        logger.info("[OBSERVER API] ✅ Claude API key stored in Redis")
        
        # If observer is running, update its Claude client
        from app.agent.trading_observer import get_trading_observer
        observer = get_trading_observer()
        if observer:
            try:
                from app.agent.claude_client import ClaudeClient, MODEL_HAIKU
                observer.claude = ClaudeClient(api_key=claude_api_key, model=MODEL_HAIKU)
                logger.info("[OBSERVER API] ✅ Live observer updated with Claude Haiku client")
            except Exception as e:
                logger.warning(f"[OBSERVER API] Claude client update failed: {e}")
        
        return {
            "success": True,
            "message": "Claude API key stored. Observer will use it as Gemini fallback.",
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to store key: {e}"}

