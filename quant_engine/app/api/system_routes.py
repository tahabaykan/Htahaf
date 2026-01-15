
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

from app.core.logger import logger
from app.core.data_fabric import get_data_fabric

router = APIRouter(prefix="/api/system", tags=["System"])

class LifelessModeRequest(BaseModel):
    enabled: bool

@router.post("/mode/lifeless")
async def set_lifeless_mode(request: LifelessModeRequest):
    """
    Toggle Lifeless Data Mode (Cansız Veri).
    
    WHEN ENABLED:
    - Blocks Hammer live updates.
    - Loads latest snapshots from Redis into DataFabric.
    - System runs on frozen data.
    """
    try:
        fabric = get_data_fabric()
        if not fabric:
            raise HTTPException(status_code=503, detail="DataFabric not initialized")
            
        success = fabric.set_lifeless_mode(request.enabled)
        
        if success:
            state = "ENABLED" if request.enabled else "DISABLED"
            return {"status": "success", "mode": state, "message": f"Lifeless Mode {state}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to toggle Lifeless Mode")
            
    except Exception as e:
        logger.error(f"Error toggling Lifeless Mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mode/lifeless/shuffle")
async def shuffle_lifeless_data():
    """
    Simulate market movement (Shuffle).
    
    Only works if Lifeless Mode is active.
    Randomly shifts Bid/Ask/Last/Truth/Volav by +/- 0.05-0.15.
    """
    try:
        fabric = get_data_fabric()
        if not fabric:
            raise HTTPException(status_code=503, detail="DataFabric not initialized")
            
        if not fabric.is_lifeless_mode():
            raise HTTPException(status_code=400, detail="Lifeless Mode is NOT active")
            
        count = fabric.shuffle_lifeless_data()
        
        return {
            "status": "success", 
            "message": f"Shuffled {count} symbols",
            "shuffled_count": count
        }
    except Exception as e:
        logger.error(f"Error shuffling data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def get_system_status():
    """Get system status including Lifeless Mode state"""
    try:
        fabric = get_data_fabric()
        lifeless_mode = False
        if fabric:
            lifeless_mode = fabric.is_lifeless_mode()
            
        return {
            "lifeless_mode": lifeless_mode,
            "status": "ok"
        }
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return {"status": "error", "detail": str(e)}
