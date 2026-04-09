"""
Port Adjuster V2 API Routes - Account-Aware

API endpoints for Port Adjuster with account-specific configurations.
Each account (IBKR_PED, HAMPRO, IBKR_GUN) has its own configuration.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel
from app.core.logger import logger
from app.port_adjuster.port_adjuster_store_v2 import (
    get_port_adjuster_store_v2,
)
from app.port_adjuster.port_adjuster_models import PortAdjusterConfig, PortAdjusterSnapshot


router = APIRouter(prefix="/api/psfalgo/port-adjuster-v2", tags=["Port Adjuster V2"])


class PortAdjusterConfigRequest(BaseModel):
    """Request body for updating Port Adjuster config."""
    account_id: Optional[str] = None  # If None, uses trading context
    total_exposure_usd: Optional[float] = None
    avg_pref_price: Optional[float] = None
    long_ratio_pct: Optional[float] = None
    short_ratio_pct: Optional[float] = None
    lt_ratio_pct: Optional[float] = None
    mm_ratio_pct: Optional[float] = None
    lt_potential_multiplier: Optional[float] = None
    mm_potential_multiplier: Optional[float] = None
    long_groups: Optional[Dict[str, float]] = None
    short_groups: Optional[Dict[str, float]] = None


class SaveCsvRequest(BaseModel):
    """Request body for saving to CSV."""
    account_id: Optional[str] = None
    filename: str


def _get_account_id(provided: Optional[str] = None) -> str:
    """Get account ID from parameter or trading context."""
    if provided:
        acc = provided.upper().strip()
        if acc == "HAMMER_PRO":
            acc = "HAMPRO"
        return acc
    
    # Get from trading context
    try:
        from app.trading.trading_account_context import get_trading_context
        ctx = get_trading_context()
        return ctx.trading_mode.value
    except Exception:
        return "IBKR_PED"  # Default


@router.get("/config")
async def get_config(account_id: Optional[str] = Query(None, description="Account ID")) -> Dict[str, Any]:
    """
    Get Port Adjuster configuration for specified or current account.
    
    Query params:
        account_id: Optional - IBKR_PED, HAMPRO, IBKR_GUN
    """
    try:
        acc = _get_account_id(account_id)
        store = get_port_adjuster_store_v2()
        config = store.get_config(acc)
        
        if config is None:
            raise HTTPException(status_code=404, detail=f"No config for account {acc}")
        
        return {
            "success": True,
            "account_id": acc,
            "config": config.dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_V2_API] Error getting config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshot")
async def get_snapshot(account_id: Optional[str] = Query(None, description="Account ID")) -> Dict[str, Any]:
    """
    Get Port Adjuster snapshot for specified or current account.
    
    Query params:
        account_id: Optional - IBKR_PED, HAMPRO, IBKR_GUN
    """
    try:
        acc = _get_account_id(account_id)
        store = get_port_adjuster_store_v2()
        snapshot = store.get_snapshot(acc)
        
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"No snapshot for account {acc}")
        
        return {
            "success": True,
            "account_id": acc,
            "snapshot": snapshot.dict() if hasattr(snapshot, 'dict') else snapshot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_V2_API] Error getting snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_config(config: PortAdjusterConfig, account_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """
    Update Port Adjuster configuration for specified or current account.
    
    Query params:
        account_id: Optional - IBKR_PED, HAMPRO, IBKR_GUN
    Body:
        Full PortAdjusterConfig object
    """
    try:
        acc = _get_account_id(account_id)
        store = get_port_adjuster_store_v2()
        snapshot = store.update_config(acc, config)
        
        return {
            "success": True,
            "message": f"Configuration updated for {acc}",
            "account_id": acc,
            "snapshot": snapshot.dict() if hasattr(snapshot, 'dict') else snapshot
        }
        
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_V2_API] Error updating config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recalculate")
async def recalculate(account_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """
    Recalculate snapshot for specified or current account.
    
    Query params:
        account_id: Optional - IBKR_PED, HAMPRO, IBKR_GUN
    """
    try:
        acc = _get_account_id(account_id)
        store = get_port_adjuster_store_v2()
        snapshot = store.recalculate(acc)
        
        if snapshot is None:
            raise HTTPException(status_code=400, detail=f"No config for account {acc}")
        
        return {
            "success": True,
            "message": f"Snapshot recalculated for {acc}",
            "account_id": acc,
            "snapshot": snapshot.dict() if hasattr(snapshot, 'dict') else snapshot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_V2_API] Error recalculating: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all-configs")
async def get_all_configs() -> Dict[str, Any]:
    """
    Get configurations for all accounts.
    
    Returns:
        Dictionary with configs for all 3 accounts
    """
    try:
        store = get_port_adjuster_store_v2()
        all_configs = store.get_all_configs()
        
        result = {}
        for acc, cfg in all_configs.items():
            result[acc] = cfg.dict()
        
        return {
            "success": True,
            "configs": result
        }
        
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_V2_API] Error getting all configs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save-csv")
async def save_csv(request: SaveCsvRequest) -> Dict[str, Any]:
    """
    Save account config to CSV file.
    
    Body:
        account_id: Optional - defaults to current account
        filename: CSV filename (without .csv extension)
    """
    try:
        acc = _get_account_id(request.account_id)
        store = get_port_adjuster_store_v2()
        
        path = store.save_account_to_csv(acc, request.filename)
        if path is None:
            raise HTTPException(status_code=500, detail="Failed to save CSV")
        
        return {
            "success": True,
            "message": f"Config saved for {acc}",
            "account_id": acc,
            "path": path,
            "filename": Path(path).name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_V2_API] Error saving CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load-csv")
async def load_csv(
    account_id: Optional[str] = Query(None),
    upload_file: UploadFile = File(...)
) -> Dict[str, Any]:
    """
    Load config from CSV file for specified account.
    
    Query params:
        account_id: Optional - defaults to current account
    Body:
        upload_file: CSV file to upload
    """
    try:
        acc = _get_account_id(account_id)
        
        # Save uploaded file temporarily
        temp_dir = Path(__file__).parent.parent.parent / "tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / upload_file.filename
        
        with open(temp_path, "wb") as f:
            f.write(upload_file.file.read())
        
        store = get_port_adjuster_store_v2()
        snapshot = store.load_account_from_csv(acc, str(temp_path))
        
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        
        if snapshot is None:
            raise HTTPException(status_code=400, detail="Failed to load CSV")
        
        return {
            "success": True,
            "message": f"Config loaded for {acc}",
            "account_id": acc,
            "config": store.get_config(acc).dict(),
            "snapshot": snapshot.dict() if hasattr(snapshot, 'dict') else snapshot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_V2_API] Error loading CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
