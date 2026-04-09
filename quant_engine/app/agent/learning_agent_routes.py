"""
Learning Agent API Routes
==========================

REST endpoints for controlling the Learning Agent:
- Start/Stop agent
- Add directives (Taha's instructions)
- Get status, insights, learned patterns
- Record trade outcomes for feedback
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from app.core.logger import logger

router = APIRouter(prefix="/api/learning-agent", tags=["Learning Agent"])


# ═══════════════════════════════════════════════════════════════
# Request/Response Models
# ═══════════════════════════════════════════════════════════════

class StartRequest(BaseModel):
    api_key: Optional[str] = None
    quick_interval: int = 300        # 5 min
    trend_interval: int = 1800       # 30 min
    deep_interval: int = 7200        # 2 hours


class DirectiveRequest(BaseModel):
    directive: str


class TradeOutcomeRequest(BaseModel):
    symbol: str
    action: str          # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    pnl: float
    notes: str = ""


class TruthTickAnalysisRequest(BaseModel):
    lookback_days: int = 5    # 5 İŞ GÜNÜ (trading days) geriye bakış
    top_n: int = 3            # Her DOS grubundan top N hisse
    mode: str = "backtest"    # "backtest" veya "live"


# ═══════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════

@router.post("/start")
async def start_agent(req: StartRequest):
    """Start the learning agent."""
    from app.agent.learning_agent import start_learning_agent

    try:
        agent = await start_learning_agent(
            api_key=req.api_key,
            quick_interval=req.quick_interval,
            trend_interval=req.trend_interval,
            deep_interval=req.deep_interval,
        )
        return {
            "status": "started",
            "message": "🧠 QAGENTT başlatıldı — izle, öğren, raporla!",
            "config": {
                "quick_interval": req.quick_interval,
                "trend_interval": req.trend_interval,
                "deep_interval": req.deep_interval,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Start failed: {e}")


@router.post("/stop")
async def stop_agent():
    """Stop the learning agent."""
    from app.agent.learning_agent import stop_learning_agent

    await stop_learning_agent()
    return {"status": "stopped", "message": "🛑 QAGENTT durduruldu"}


@router.get("/status")
async def get_status():
    """Get comprehensive agent status."""
    from app.agent.learning_agent import get_learning_agent

    agent = get_learning_agent()
    if not agent:
        return {
            "running": False,
            "message": "QAGENTT henüz başlatılmadı. POST /api/learning-agent/start ile başlat."
        }
    return agent.status


@router.get("/latest-insight")
async def get_latest_insight():
    """Get the most recent analysis insight."""
    from app.agent.learning_agent import get_learning_agent

    agent = get_learning_agent()
    if not agent or not agent.latest_insight:
        return {"insight": None, "message": "Henüz analiz yapılmadı"}
    return agent.latest_insight


@router.get("/insights-history")
async def get_insights_history(limit: int = 20):
    """Get insight history (most recent last)."""
    from app.agent.learning_agent import get_learning_agent

    agent = get_learning_agent()
    if not agent:
        return {"insights": [], "count": 0}

    history = agent.insights_history[-limit:]
    return {"insights": history, "count": len(history)}


@router.get("/learned-patterns")
async def get_learned_patterns():
    """Get all patterns the agent has learned."""
    from app.agent.learning_agent import get_learning_agent

    agent = get_learning_agent()
    if not agent:
        return {"patterns": [], "count": 0}

    return {
        "patterns": agent.learned_patterns,
        "count": len(agent.learned_patterns),
    }


@router.get("/directives")
async def get_directives():
    """Get active directives."""
    from app.agent.learning_agent import get_learning_agent

    agent = get_learning_agent()
    if not agent:
        return {"directives": [], "count": 0}

    return {
        "directives": agent.active_directives,
        "count": len(agent.active_directives),
    }


@router.post("/directive")
async def add_directive(req: DirectiveRequest):
    """
    Add a directive (instruction) for the agent.

    Examples:
        "Bugün NLY-PD'ye dikkat et, ex-div yaklaşıyor"
        "CONY short kesinlikle gitme, likidite sıfır"
        "Exposure %85'i geçmesin bugün"
    """
    from app.agent.learning_agent import get_learning_agent

    agent = get_learning_agent()
    if not agent:
        raise HTTPException(status_code=400, detail="Agent başlatılmadı")

    await agent.add_directive(req.directive)
    return {
        "status": "added",
        "directive": req.directive,
        "total_directives": len(agent.active_directives),
    }


@router.delete("/directives")
async def clear_directives():
    """Clear all active directives."""
    from app.agent.learning_agent import get_learning_agent

    agent = get_learning_agent()
    if not agent:
        raise HTTPException(status_code=400, detail="Agent başlatılmadı")

    await agent.clear_directives()
    return {"status": "cleared", "message": "Tüm direktifler temizlendi"}


@router.post("/trade-outcome")
async def record_trade_outcome(req: TradeOutcomeRequest):
    """
    Record a trade outcome for the agent to learn from.

    This helps the agent understand which setups work and which don't.
    """
    from app.agent.learning_agent import get_learning_agent

    agent = get_learning_agent()
    if not agent:
        raise HTTPException(status_code=400, detail="Agent başlatılmadı")

    await agent.record_trade_outcome(
        symbol=req.symbol,
        action=req.action,
        entry_price=req.entry_price,
        exit_price=req.exit_price,
        pnl=req.pnl,
        notes=req.notes,
    )

    return {
        "status": "recorded",
        "symbol": req.symbol,
        "action": req.action,
        "pnl": req.pnl,
    }


@router.get("/gemini-stats")
async def get_gemini_stats():
    """Get Gemini API usage statistics."""
    from app.agent.learning_agent import get_learning_agent

    agent = get_learning_agent()
    if not agent:
        return {"message": "Agent başlatılmadı"}

    stats = agent.status.get("gemini_stats", {})
    return {
        "daily_calls": stats.get("daily_calls", 0),
        "daily_limit": 1500,
        "usage_pct": stats.get("daily_usage_pct", 0),
        "message": f"Bugün {stats.get('daily_calls', 0)}/1500 call kullanıldı "
                   f"({stats.get('daily_usage_pct', 0)}%) — ÜCRETSİZ tier"
    }


# ═══════════════════════════════════════════════════════════════
# Truth Tick Analysis Endpoints
# ═══════════════════════════════════════════════════════════════

@router.post("/truth-tick-analysis")
async def trigger_truth_tick_analysis(req: TruthTickAnalysisRequest):
    """
    Trigger on-demand truth tick 30-minute window analysis.

    Analyzes all DOS groups, picks top-N stocks per group,
    and sends to Gemini for portfolio/MM model insights.
    """
    from app.agent.learning_agent import get_learning_agent

    agent = get_learning_agent()
    if not agent:
        # Run standalone analysis without agent
        from app.agent.truth_tick_analyzer import run_truth_tick_deep_analysis

        result = await run_truth_tick_deep_analysis(
            lookback_days=req.lookback_days,
            top_n=req.top_n,
            mode=req.mode,
        )
        return {
            "status": "completed",
            "mode": req.mode,
            "message": f"Truth tick analysis tamamlandı (standalone, {req.mode} mode)",
            "result": result,
        }

    result = await agent.run_truth_tick_analysis_manual(
        lookback_days=req.lookback_days,
        top_n=req.top_n,
    )
    return {
        "status": "completed",
        "mode": req.mode,
        "message": f"Truth tick analysis tamamlandı ({req.mode} mode)",
        "result": result,
    }


@router.get("/truth-tick-analysis")
async def get_last_truth_tick_analysis():
    """Get the last truth tick analysis result (including Gemini interpretation)."""
    from app.agent.learning_agent import get_learning_agent
    import json

    agent = get_learning_agent()

    # Check agent's in-memory result first
    if agent and agent.last_tt_analysis:
        return {
            "source": "agent_memory",
            "result": agent.last_tt_analysis,
        }

    # Fallback: Check Redis
    try:
        from app.core.redis_client import get_redis_sync
        r = get_redis_sync()
        if r:
            raw = r.get("qagentt:truth_tick_analysis")
            if raw:
                return {
                    "source": "redis_cache",
                    "result": json.loads(raw),
                }
    except Exception:
        pass

    return {"result": None, "message": "Henüz truth tick analizi yapılmadı. POST /api/learning-agent/truth-tick-analysis ile tetikle."}


@router.get("/truth-tick-raw-stats")
async def get_truth_tick_raw_stats(lookback_days: int = 5, top_n: int = 3):
    """
    Get raw truth tick statistics WITHOUT Gemini interpretation.

    Faster — purely computational, no API calls.
    Useful for dashboards and data exploration.
    """
    from app.agent.truth_tick_analyzer import analyze_dos_groups

    result = analyze_dos_groups(
        lookback_days=lookback_days,
        top_n=top_n,
    )
    return {
        "status": "completed",
        "result": result,
    }
