"""
Data Fabric API Routes
======================

Endpoints for monitoring and managing the in-memory data fabric.

⚠️ IMPORTANT:
- /reload endpoint is for ADMIN use only
- Should NOT be called during normal trading hours
- CSV reads are ONLY allowed at startup or manual reload
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional

from app.core.logger import logger
from app.core.data_fabric import get_data_fabric

router = APIRouter(prefix="/api/data-fabric", tags=["Data Fabric"])


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    """
    Get DataFabric status.
    
    Returns current state of all data layers:
    - static: CSV data (loaded at startup)
    - live: Hammer market data (real-time)
    - derived: Calculated metrics
    - etf: ETF data for benchmarks
    """
    try:
        fabric = get_data_fabric()
        return {
            "status": "ok",
            "data": fabric.get_status(),
            "is_ready": fabric.is_ready()
        }
    except Exception as e:
        logger.error(f"Error getting data fabric status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    """
    Get DataFabric performance statistics.
    
    Returns:
    - Load times
    - Update counts
    - Request counts
    """
    try:
        fabric = get_data_fabric()
        return {
            "status": "ok",
            "stats": fabric.get_stats()
        }
    except Exception as e:
        logger.error(f"Error getting data fabric stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/static/{symbol}")
async def get_static_data(symbol: str) -> Dict[str, Any]:
    """
    Get static data for a symbol.
    
    This reads from RAM (no disk I/O).
    """
    try:
        fabric = get_data_fabric()
        data = fabric.get_static(symbol)
        
        if not data:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found in static data")
        
        return {
            "status": "ok",
            "symbol": symbol,
            "data": data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting static data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/live/{symbol}")
async def get_live_data(symbol: str) -> Dict[str, Any]:
    """
    Get live market data for a symbol.
    
    This reads from RAM (no disk I/O).
    """
    try:
        fabric = get_data_fabric()
        data = fabric.get_live(symbol)
        
        if not data:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found in live data")
        
        return {
            "status": "ok",
            "symbol": symbol,
            "data": data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting live data for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshot/{symbol}")
async def get_snapshot(symbol: str) -> Dict[str, Any]:
    """
    Get combined snapshot for a symbol.
    
    Merges: static + live + derived
    """
    try:
        fabric = get_data_fabric()
        data = fabric.get_snapshot(symbol)
        
        if not data:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        
        return {
            "status": "ok",
            "symbol": symbol,
            "data": data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting snapshot for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols")
async def get_all_symbols() -> Dict[str, Any]:
    """
    Get list of all symbols with static data.
    """
    try:
        fabric = get_data_fabric()
        symbols = fabric.get_all_static_symbols()
        
        return {
            "status": "ok",
            "count": len(symbols),
            "symbols": symbols
        }
    except Exception as e:
        logger.error(f"Error getting symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dirty-symbols")
async def get_dirty_symbols() -> Dict[str, Any]:
    """
    Get symbols that need recalculation.
    """
    try:
        fabric = get_data_fabric()
        dirty = fabric.get_dirty_symbols()
        
        return {
            "status": "ok",
            "count": len(dirty),
            "symbols": list(dirty)[:100]  # Limit to first 100
        }
    except Exception as e:
        logger.error(f"Error getting dirty symbols: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_static_data(csv_path: Optional[str] = None) -> Dict[str, Any]:
    """
    ⚠️ ADMIN ONLY: Manually reload static data from CSV.
    
    This should ONLY be called:
    - After daily CSV update
    - During market close
    - For debugging purposes
    
    DO NOT call during normal trading hours!
    """
    try:
        logger.warning("⚠️ Manual static data reload requested via API")
        
        fabric = get_data_fabric()
        success = fabric.reload_static(csv_path)
        
        if success:
            return {
                "status": "ok",
                "message": "Static data reloaded successfully",
                "stats": fabric.get_stats()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to reload static data")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reloading static data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/etf")
async def get_etf_data() -> Dict[str, Any]:
    """
    Get all ETF data (live + prev_close).
    """
    try:
        fabric = get_data_fabric()
        
        return {
            "status": "ok",
            "live": fabric.get_all_etf_data(),
            "prev_close": fabric.get_all_etf_prev_close()
        }
    except Exception as e:
        logger.error(f"Error getting ETF data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/group-weights")
async def get_group_weights() -> Dict[str, Any]:
    """
    Get all group weights.
    """
    try:
        fabric = get_data_fabric()
        
        return {
            "status": "ok",
            "weights": fabric.get_all_group_weights()
        }
    except Exception as e:
        logger.error(f"Error getting group weights: {e}")
        raise HTTPException(status_code=500, detail=str(e))





