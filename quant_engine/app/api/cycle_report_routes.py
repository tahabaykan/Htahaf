"""
Cycle Report API Routes

Endpoints for querying cycle summary reports.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from pathlib import Path

from app.core.cycle_reporter import get_cycle_reporter
from app.core.logger import logger


router = APIRouter(prefix="/api/cycle", tags=["cycle_reports"])


@router.get("/latest")
async def get_latest_cycle():
    """Get latest cycle summary report"""
    try:
        reporter = get_cycle_reporter()
        report = reporter.get_latest_report()
        
        if not report:
            raise HTTPException(status_code=404, detail="No cycle report found")
        
        return report
    
    except Exception as e:
        logger.error(f"[API] Error getting latest cycle: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest/summary")
async def get_latest_cycle_summary():
    """Get summary stats from latest cycle (without symbol details)"""
    try:
        reporter = get_cycle_reporter()
        report = reporter.get_latest_report()
        
        if not report:
            raise HTTPException(status_code=404, detail="No cycle report found")
        
        # Return only summary stats (no per-symbol data)
        return {
            'cycle_id': report.get('cycle_id'),
            'start_time': report.get('start_time'),
            'end_time': report.get('end_time'),
            'duration_seconds': report.get('duration_seconds'),
            'total_symbols': report.get('total_symbols'),
            'sent_count': report.get('sent_count'),
            'blocked_count': report.get('blocked_count'),
            'skipped_count': report.get('skipped_count'),
            'adjusted_count': report.get('adjusted_count'),
            'engine_stats': report.get('engine_stats', {}),
            'block_reasons': report.get('block_reasons', {})
        }
    
    except Exception as e:
        logger.error(f"[API] Error getting cycle summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest/symbol/{symbol}")
async def get_symbol_report(symbol: str):
    """Get report for specific symbol from latest cycle"""
    try:
        reporter = get_cycle_reporter()
        symbol_report = reporter.get_symbol_report(symbol)
        
        if not symbol_report:
            raise HTTPException(
                status_code=404,
                detail=f"No report found for symbol {symbol}"
            )
        
        return symbol_report
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error getting symbol report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest/filtered")
async def get_filtered_symbols(
    status: Optional[str] = Query(None, description="Filter by status: SENT, BLOCKED, etc."),
    engine: Optional[str] = Query(None, description="Filter by engine: KARBOTU_V2, etc."),
    block_reason: Optional[str] = Query(None, description="Filter by block reason")
):
    """Get filtered symbols from latest cycle"""
    try:
        reporter = get_cycle_reporter()
        report = reporter.get_latest_report()
        
        if not report or 'symbols' not in report:
            raise HTTPException(status_code=404, detail="No cycle report found")
        
        symbols = report['symbols']
        filtered = {}
        
        for sym, data in symbols.items():
            # Apply filters
            if status and data.get('status') != status:
                continue
            if engine and data.get('engine') != engine:
                continue
            if block_reason and data.get('block_reason') != block_reason:
                continue
            
            filtered[sym] = data
        
        return {
            'count': len(filtered),
            'symbols': filtered
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error filtering symbols: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest/blocked")
async def get_blocked_symbols():
    """Get all blocked symbols from latest cycle"""
    try:
        reporter = get_cycle_reporter()
        report = reporter.get_latest_report()
        
        if not report or 'symbols' not in report:
            raise HTTPException(status_code=404, detail="No cycle report found")
        
        blocked = {
            sym: data
            for sym, data in report['symbols'].items()
            if data.get('status') == 'BLOCKED'
        }
        
        return {
            'count': len(blocked),
            'symbols': blocked
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error getting blocked symbols: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest/sent")
async def get_sent_symbols():
    """Get all symbols with sent orders from latest cycle"""
    try:
        reporter = get_cycle_reporter()
        report = reporter.get_latest_report()
        
        if not report or 'symbols' not in report:
            raise HTTPException(status_code=404, detail="No cycle report found")
        
        sent = {
            sym: data
            for sym, data in report['symbols'].items()
            if data.get('status') == 'SENT'
        }
        
        return {
            'count': len(sent),
            'symbols': sent
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error getting sent symbols: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
