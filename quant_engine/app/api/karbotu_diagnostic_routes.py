"""
KARBOTU Diagnostic API Routes

Exposes detailed diagnostic information about KARBOTU engine execution:
- Why positions are triggered but no intents generated
- Blocking reasons breakdown
- Filter analysis
- Triggered vs eligible breakdown
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from loguru import logger

router = APIRouter()


@router.get("/api/karbotu/diagnostic")
async def get_karbotu_diagnostic() -> Dict[str, Any]:
    """
    Get latest KARBOTU diagnostic data.
    
    Returns detailed breakdown of:
    - Total positions analyzed
    - Eligible vs triggered counts
    - Intent generation stats
    - Blocking reasons with details
    """
    try:
        from app.psfalgo.karbotu_engine import get_karbotu_engine
        
        engine = get_karbotu_engine()
        
        if not hasattr(engine, 'last_diagnostic') or not engine.last_diagnostic:
            return {
                "success": False,
                "message": "No diagnostic data available - run KARBOTU first"
            }
        
        diagnostic = engine.last_diagnostic
        
        return {
            "success": True,
            "diagnostic": {
                "total_positions": diagnostic.get('total_positions', 0),
                "longs_count": diagnostic.get('longs_count', 0),
                "shorts_count": diagnostic.get('shorts_count', 0),
                "positions_analyzed": diagnostic.get('positions_analyzed', 0),
                "eligible_count": diagnostic.get('eligible_count', 0),
                "triggered_count": diagnostic.get('triggered_count', 0),
                "intent_generated": diagnostic.get('intent_generated', 0),
                "blocked_by_gort": diagnostic.get('blocked_by_gort', 0),
                "blocked_by_too_cheap": diagnostic.get('blocked_by_too_cheap', 0),
                "blocked_by_too_expensive": diagnostic.get('blocked_by_too_expensive', 0),
                "no_metrics": diagnostic.get('no_metrics', 0),
                "blocking_details": diagnostic.get('blocking_details', [])
            },
            "analysis": {
                "triggered_but_no_intent": diagnostic.get('triggered_count', 0) - diagnostic.get('intent_generated', 0),
                "eligible_but_not_triggered": diagnostic.get('eligible_count', 0) - diagnostic.get('triggered_count', 0),
                "total_blocked": (
                    diagnostic.get('blocked_by_gort', 0) +
                    diagnostic.get('blocked_by_too_cheap', 0) +
                    diagnostic.get('blocked_by_too_expensive', 0)
                )
            }
        }
    
    except Exception as e:
        logger.error(f"[KARBOTU_API] Error fetching diagnostic: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/karbotu/blocking-summary")
async def get_blocking_summary() -> Dict[str, Any]:
    """
    Get summary of why positions are blocked.
    
    Returns grouped blocking reasons.
    """
    try:
        from app.psfalgo.karbotu_engine import get_karbotu_engine
        
        engine = get_karbotu_engine()
        
        if not hasattr(engine, 'last_diagnostic') or not engine.last_diagnostic:
            return {
                "success": False,
                "message": "No diagnostic data available"
            }
        
        diagnostic = engine.last_diagnostic
        blocking_details = diagnostic.get('blocking_details', [])
        
        # Group by reason
        by_reason = {}
        for detail in blocking_details:
            reason = detail.get('reason', 'UNKNOWN')
            if reason not in by_reason:
                by_reason[reason] = []
            by_reason[reason].append(detail)
        
        # Create summary
        summary = []
        for reason, details in by_reason.items():
            summary.append({
                "reason": reason,
                "count": len(details),
                "symbols": [d['symbol'] for d in details[:10]],  # Top 10
                "sample_threshold": details[0].get('threshold', 'N/A') if details else 'N/A'
            })
        
        return {
            "success": True,
            "summary": summary,
            "total_blocked": len(blocking_details)
        }
    
    except Exception as e:
        logger.error(f"[KARBOTU_API] Error fetching blocking summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
