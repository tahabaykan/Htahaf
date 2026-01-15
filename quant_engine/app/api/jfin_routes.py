"""
JFIN API Routes - Deterministic Transformer for ADDNEWPOS

⚠️ CRITICAL DESIGN PRINCIPLES:
1. JFIN output is INTENTIONS, NOT orders
2. Orders are NEVER sent directly - only previewed for approval
3. BB/FB/SAS/SFS pools are STRICTLY SEPARATE
4. All parameters are adjustable via Rules Window
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.jfin_engine import (
    JFINEngine, JFINConfig, JFINResult,
    get_jfin_engine, initialize_jfin_engine
)
from app.psfalgo.rules_store import get_rules_store

router = APIRouter(prefix="/jfin", tags=["JFIN"])


# ============================================================================
# Request/Response Models
# ============================================================================

class JFINConfigUpdate(BaseModel):
    """JFIN Config update from UI"""
    # TUMCSV Selection
    selection_percent: Optional[float] = Field(None, ge=0.01, le=1.0, description="Selection percent (0.10 = 10%)")
    min_selection: Optional[int] = Field(None, ge=1, le=20, description="Minimum stocks per group")
    heldkuponlu_pair_count: Optional[int] = Field(None, ge=1, le=20, description="HELDKUPONLU pair count")
    
    # Lot Distribution
    alpha: Optional[float] = Field(None, ge=0.5, le=10.0, description="Alpha coefficient")
    total_long_rights: Optional[int] = Field(None, ge=0, description="Total long lot rights")
    total_short_rights: Optional[int] = Field(None, ge=0, description="Total short lot rights")
    
    # JFIN Percentage
    jfin_percentage: Optional[int] = Field(None, description="JFIN percentage (25, 50, 75, 100)")
    
    # Exposure
    exposure_percent: Optional[float] = Field(None, ge=0, le=100, description="Exposure percent")
    
    # Lot Controls
    min_lot_per_order: Optional[int] = Field(None, ge=100, description="Minimum lot per order")


class JFINTransformRequest(BaseModel):
    """Request for JFIN transform"""
    candidates: List[Dict[str, Any]] = Field(..., description="ADDNEWPOS candidates")
    market_data: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Market data")
    positions: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Current positions")
    befday_positions: Dict[str, int] = Field(default_factory=dict, description="BEFDAY positions")
    max_addable_total: Optional[int] = Field(None, description="Max addable lot (Pot Max - Pot Total)")
    
    # Override config for this request (optional)
    jfin_percentage: Optional[int] = Field(None, description="Override JFIN percentage")
    pool_filter: Optional[str] = Field(None, description="Filter to specific pool (BB, FB, SAS, SFS)")


class JFINPreviewRequest(BaseModel):
    """Request for JFIN preview (dry-run)"""
    pool: str = Field(..., description="Pool to preview (BB, FB, SAS, SFS)")
    jfin_percentage: int = Field(50, description="JFIN percentage")


class GroupWeightsUpdate(BaseModel):
    """Group weights update"""
    long_weights: Dict[str, float] = Field(default_factory=dict, description="Long group weights")
    short_weights: Dict[str, float] = Field(default_factory=dict, description="Short group weights")


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/config")
async def get_jfin_config():
    """
    Get current JFIN configuration
    
    Returns all adjustable parameters for the Rules Window
    """
    try:
        engine = get_jfin_engine()
        if not engine:
            # Return default config
            default_config = JFINConfig()
            return {
                "success": True,
                "config": default_config.to_dict(),
                "initialized": False
            }
        
        return {
            "success": True,
            "config": engine.config.to_dict(),
            "initialized": True
        }
    except Exception as e:
        logger.error(f"[JFIN API] Error getting config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_jfin_config(update: JFINConfigUpdate):
    """
    Update JFIN configuration from Rules Window
    
    All parameters are adjustable:
    - selection_percent: 0.10, 0.12, 0.15 (TUMCSV version)
    - jfin_percentage: 25, 50, 75, 100
    - exposure_percent: 0-100
    - alpha: 1-5
    """
    try:
        engine = get_jfin_engine()
        if not engine:
            engine = initialize_jfin_engine()
        
        # Update config
        update_dict = {k: v for k, v in update.dict().items() if v is not None}
        engine.update_config(update_dict)
        
        # Also update rules store if available
        rules_store = get_rules_store()
        if rules_store:
            rules_store.update_jfin_config(update_dict)
        
        return {
            "success": True,
            "config": engine.config.to_dict(),
            "message": f"Updated {len(update_dict)} parameters"
        }
    except Exception as e:
        logger.error(f"[JFIN API] Error updating config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/preset/{preset_name}")
async def apply_jfin_preset(preset_name: str):
    """
    Apply a TUMCSV preset (v10, v15, v20)
    
    Presets:
    - v10: 10% selection, min 2, heldkuponlu 8
    - v15: 12% selection, min 2, heldkuponlu 10
    - v20: 15% selection, min 3, heldkuponlu 12
    """
    try:
        presets = {
            "v10": {"selection_percent": 0.10, "min_selection": 2, "heldkuponlu_pair_count": 8},
            "v15": {"selection_percent": 0.12, "min_selection": 2, "heldkuponlu_pair_count": 10},
            "v20": {"selection_percent": 0.15, "min_selection": 3, "heldkuponlu_pair_count": 12},
        }
        
        if preset_name not in presets:
            raise HTTPException(status_code=400, detail=f"Unknown preset: {preset_name}. Available: {list(presets.keys())}")
        
        engine = get_jfin_engine()
        if not engine:
            engine = initialize_jfin_engine()
        
        engine.update_config(presets[preset_name])
        
        return {
            "success": True,
            "preset": preset_name,
            "config": engine.config.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[JFIN API] Error applying preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/group-weights")
async def update_group_weights(weights: GroupWeightsUpdate):
    """
    Update group weights (from groupweights.csv or UI)
    """
    try:
        engine = get_jfin_engine()
        if not engine:
            engine = initialize_jfin_engine()
        
        engine.set_group_weights(weights.long_weights, weights.short_weights)
        
        return {
            "success": True,
            "long_groups": len(weights.long_weights),
            "short_groups": len(weights.short_weights)
        }
    except Exception as e:
        logger.error(f"[JFIN API] Error updating group weights: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transform")
async def transform_addnewpos_to_intents(request: JFINTransformRequest):
    """
    Transform ADDNEWPOS candidates into JFIN Intentions
    
    ⚠️ THIS DOES NOT SEND ORDERS!
    Output is a list of INTENTIONS for user approval.
    
    The transform follows this order:
    1. TUMCSV Selection (select stocks for each pool)
    2. Lot Distribution (alpha-weighted)
    3. Addable Lot Calculation (MAXALW, position, daily limit)
    4. Apply Percentage and Exposure Adjustment
    5. Calculate Prices
    6. Generate Intentions (NOT orders!)
    """
    try:
        engine = get_jfin_engine()
        if not engine:
            engine = initialize_jfin_engine()
        
        # Override percentage if specified
        if request.jfin_percentage:
            engine.config.jfin_percentage = request.jfin_percentage
        
        # Run transform
        result = await engine.transform(
            addnewpos_candidates=request.candidates,
            market_data=request.market_data,
            positions=request.positions,
            befday_positions=request.befday_positions,
            max_addable_total=request.max_addable_total
        )
        
        # Filter to specific pool if requested
        if request.pool_filter:
            pool_filter = request.pool_filter.upper()
            filtered_result = {
                "bb_long_intents": result.bb_long_intents if pool_filter == "BB" else [],
                "fb_long_intents": result.fb_long_intents if pool_filter == "FB" else [],
                "sas_short_intents": result.sas_short_intents if pool_filter == "SAS" else [],
                "sfs_short_intents": result.sfs_short_intents if pool_filter == "SFS" else [],
            }
            return {
                "success": True,
                "pool_filter": pool_filter,
                "result": filtered_result,
                "total_intents": len(filtered_result.get(f"{pool_filter.lower()}_{'long' if pool_filter in ['BB', 'FB'] else 'short'}_intents", [])),
                "execution_time_ms": result.execution_time_ms
            }
        
        return {
            "success": True,
            "result": result.to_dict(),
            "summary": {
                "total_intents": result.total_intents,
                "total_long_lots": result.total_long_lots,
                "total_short_lots": result.total_short_lots,
                "bb_long": len(result.bb_long_intents),
                "fb_long": len(result.fb_long_intents),
                "sas_short": len(result.sas_short_intents),
                "sfs_short": len(result.sfs_short_intents)
            },
            "execution_time_ms": result.execution_time_ms
        }
    except Exception as e:
        logger.error(f"[JFIN API] Error in transform: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preview/{pool}")
async def preview_jfin_pool(pool: str, percentage: int = 50):
    """
    Preview JFIN intentions for a specific pool
    
    This is a DRY-RUN that shows what would be generated
    without actually creating intents.
    
    Args:
        pool: BB, FB, SAS, or SFS
        percentage: 25, 50, 75, or 100
    """
    try:
        pool = pool.upper()
        if pool not in ["BB", "FB", "SAS", "SFS"]:
            raise HTTPException(status_code=400, detail=f"Invalid pool: {pool}. Must be BB, FB, SAS, or SFS")
        
        if percentage not in [25, 50, 75, 100]:
            raise HTTPException(status_code=400, detail=f"Invalid percentage: {percentage}. Must be 25, 50, 75, or 100")
        
        engine = get_jfin_engine()
        if not engine:
            return {
                "success": False,
                "error": "JFIN engine not initialized. Run transform first.",
                "pool": pool,
                "percentage": percentage
            }
        
        # Get current config
        config = engine.config.to_dict()
        
        return {
            "success": True,
            "pool": pool,
            "percentage": percentage,
            "config": config,
            "message": "Use POST /transform to generate actual intents"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[JFIN API] Error in preview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pools")
async def get_jfin_pools():
    """
    Get information about JFIN pools
    
    Returns:
    - Pool configuration
    - Score columns used
    - Order types
    """
    return {
        "success": True,
        "pools": {
            "BB_LONG": {
                "name": "Bid Buy Long",
                "score_column": "Final_BB_skor",
                "order_type": "BID_BUY",
                "price_formula": "bid + (spread * 0.15)",
                "direction": "LONG",
                "selection": "Highest score"
            },
            "FB_LONG": {
                "name": "Front Buy Long",
                "score_column": "Final_FB_skor",
                "order_type": "FRONT_BUY",
                "price_formula": "last + 0.01",
                "direction": "LONG",
                "selection": "Highest score"
            },
            "SAS_SHORT": {
                "name": "Ask Sell Short",
                "score_column": "Final_SAS_skor",
                "order_type": "ASK_SELL",
                "price_formula": "ask - (spread * 0.15)",
                "direction": "SHORT",
                "selection": "Lowest score"
            },
            "SFS_SHORT": {
                "name": "Soft Front Sell Short",
                "score_column": "Final_SFS_skor",
                "order_type": "FRONT_SELL",
                "price_formula": "last - 0.01",
                "direction": "SHORT",
                "selection": "Lowest score"
            }
        },
        "note": "⚠️ Pools are STRICTLY SEPARATE - same stock can appear in multiple pools"
    }


@router.get("/status")
async def get_jfin_status():
    """
    Get JFIN engine status
    """
    try:
        engine = get_jfin_engine()
        
        return {
            "success": True,
            "initialized": engine is not None,
            "config": engine.config.to_dict() if engine else None,
            "group_weights_loaded": bool(engine and engine._group_weights.get('long')),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"[JFIN API] Error getting status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))





