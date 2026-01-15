"""
app/api/genobs_routes.py

API Endpoints for Genobs (General Observation) Module.
"""
from fastapi import APIRouter, HTTPException
from app.analysis.genobs_service import get_genobs_service
from app.core.logger import logger

router = APIRouter(prefix="/api/genobs", tags=["genobs"])

@router.get("/data")
async def get_genobs_data():
    """
    Get aggregated data for Genobs table.
    Includes: Prices, Metrics, OFI, Scores.
    """
    try:
        service = get_genobs_service()
        data = service.get_genobs_data()
        return {
            "success": True,
            "count": len(data),
            "data": data
        }
    except Exception as e:
        logger.error(f"Error in get_genobs_data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
