"""
Truth Shift API Routes

Endpoints for TSS (Truth Shift Score) and RTS (Relative Truth Shift) data.
Shows directional flow of truth ticks per symbol and group.
"""

import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.core.logger import logger


router = APIRouter(prefix="/api/truth-shift", tags=["TruthShift"])


@router.get("/dashboard")
async def get_dashboard(
    window: str = Query("TSS_15M", description="Time window: TSS_5M, TSS_15M, TSS_30M, TSS_1H, TSS_TODAY")
):
    """
    Full dashboard payload: all symbols + groups + metadata.
    
    First triggers a fresh compute if cache is stale (>120s),
    then returns cached results.
    """
    try:
        from app.terminals.truth_shift_engine import get_truth_shift_engine
        engine = get_truth_shift_engine()
        
        # If no cache, trigger compute
        import time
        age = time.time() - engine._last_compute_ts if engine._last_compute_ts else float('inf')
        if age > 120 or not engine._cached_results:
            logger.info("[TruthShift API] Cache stale/empty — computing fresh...")
            engine._load_group_mappings()
            engine.compute_all()
        
        data = engine.get_dashboard_data(window)
        return {"success": True, **data}
    
    except Exception as e:
        logger.error(f"[TruthShift API] Dashboard error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols")
async def get_all_symbols(
    window: str = Query("TSS_15M", description="Time window"),
    sort_by: str = Query("tss_abs", description="Sort: tss_abs, tss, rts, intensity")
):
    """
    All symbols with TSS/RTS data, sorted.
    """
    try:
        from app.terminals.truth_shift_engine import get_truth_shift_engine
        engine = get_truth_shift_engine()
        
        import time
        age = time.time() - engine._last_compute_ts if engine._last_compute_ts else float('inf')
        if age > 120 or not engine._cached_results:
            engine._load_group_mappings()
            engine.compute_all()
        
        rows = engine.get_all_symbols_summary(window)
        
        # Sort options
        if sort_by == 'tss':
            rows.sort(key=lambda r: r['tss'], reverse=True)
        elif sort_by == 'rts':
            rows.sort(key=lambda r: abs(r.get('rts') or 0), reverse=True)
        elif sort_by == 'intensity':
            rows.sort(key=lambda r: r.get('intensity', 0), reverse=True)
        # default: tss_abs (already sorted)
        
        return {
            "success": True,
            "count": len(rows),
            "window": window,
            "data": rows
        }
    
    except Exception as e:
        logger.error(f"[TruthShift API] Symbols error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups")
async def get_all_groups(
    window: str = Query("TSS_15M", description="Time window")
):
    """
    All groups with group TSS data, sorted by score.
    """
    try:
        from app.terminals.truth_shift_engine import get_truth_shift_engine
        engine = get_truth_shift_engine()
        
        import time
        age = time.time() - engine._last_compute_ts if engine._last_compute_ts else float('inf')
        if age > 120 or not engine._cached_results:
            engine._load_group_mappings()
            engine.compute_all()
        
        rows = engine.get_all_groups_summary(window)
        
        return {
            "success": True,
            "count": len(rows),
            "window": window,
            "data": rows
        }
    
    except Exception as e:
        logger.error(f"[TruthShift API] Groups error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbol/{symbol}")
async def get_symbol_detail(symbol: str):
    """
    Detailed TSS for a single symbol across all windows.
    """
    try:
        from app.terminals.truth_shift_engine import get_truth_shift_engine
        engine = get_truth_shift_engine()
        
        import time
        age = time.time() - engine._last_compute_ts if engine._last_compute_ts else float('inf')
        if age > 120 or not engine._cached_results:
            engine._load_group_mappings()
            engine.compute_all()
        
        data = engine.get_symbol_tss(symbol)
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"No TSS data for symbol '{symbol}'. It may not have truth ticks in Redis."
            )
        
        return {"success": True, "data": data}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TruthShift API] Symbol detail error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group/{group_key}")
async def get_group_detail(group_key: str):
    """
    Detailed TSS for a group with all member symbols and their RTS.
    """
    try:
        from app.terminals.truth_shift_engine import get_truth_shift_engine
        engine = get_truth_shift_engine()
        
        import time
        age = time.time() - engine._last_compute_ts if engine._last_compute_ts else float('inf')
        if age > 120 or not engine._cached_results:
            engine._load_group_mappings()
            engine.compute_all()
        
        data = engine.get_group_tss(group_key)
        if not data:
            raise HTTPException(
                status_code=404,
                detail=f"No TSS data for group '{group_key}'."
            )
        
        return {"success": True, "data": data}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TruthShift API] Group detail error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compute")
async def trigger_compute():
    """
    Manually trigger a full TSS/RTS recompute.
    """
    try:
        from app.terminals.truth_shift_engine import get_truth_shift_engine
        engine = get_truth_shift_engine()
        
        engine._load_group_mappings()
        sym_results, grp_results = engine.compute_all()
        
        return {
            "success": True,
            "symbols_computed": len(sym_results),
            "groups_computed": len(grp_results),
            "message": "TSS/RTS recompute complete"
        }
    except Exception as e:
        logger.error(f"[TruthShift API] Compute error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
