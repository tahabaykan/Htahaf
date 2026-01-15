"""
Port Adjuster API Routes

API endpoints for Port Adjuster configuration and snapshot access.
"""

from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pathlib import Path
from app.core.logger import logger
from app.port_adjuster.port_adjuster_store import get_port_adjuster_store
from app.port_adjuster.port_adjuster_models import PortAdjusterConfig, PortAdjusterSnapshot
from app.port_adjuster.port_adjuster_csv import load_config_from_csv, save_config_to_csv

router = APIRouter(prefix="/api/psfalgo/port-adjuster", tags=["Port Adjuster"])


@router.get("/snapshot", response_model=PortAdjusterSnapshot)
async def get_snapshot() -> PortAdjusterSnapshot:
    """
    Get current Port Adjuster snapshot.
    
    Returns:
        Current PortAdjusterSnapshot with all allocations
    """
    try:
        store = get_port_adjuster_store()
        snapshot = store.get_snapshot()
        
        if snapshot is None:
            raise HTTPException(
                status_code=404,
                detail="Port Adjuster snapshot not available. Please configure first."
            )
        
        return snapshot
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_API] Error getting snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def update_config(config: PortAdjusterConfig) -> Dict[str, Any]:
    """
    Update Port Adjuster configuration and recalculate snapshot.
    
    Args:
        config: New Port Adjuster configuration
        
    Returns:
        Success status and new snapshot
    """
    try:
        store = get_port_adjuster_store()
        store.config_source = "api:config"
        snapshot = store.update_config(config)
        
        return {
            "success": True,
            "message": "Configuration updated successfully",
            "snapshot": snapshot
        }
        
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_API] Error updating config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recalculate")
async def recalculate() -> Dict[str, Any]:
    """
    Recalculate snapshot from current configuration.
    
    Returns:
        Success status and updated snapshot
    """
    try:
        store = get_port_adjuster_store()
        snapshot = store.recalculate()
        
        if snapshot is None:
            raise HTTPException(
                status_code=400,
                detail="No configuration available. Please configure first."
            )
        
        return {
            "success": True,
            "message": "Snapshot recalculated successfully",
            "snapshot": snapshot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_API] Error recalculating: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export-csv")
async def export_csv(
    file_path: Optional[str] = Query(
        None,
        description="Optional file path (default: exposureadjuster.csv in project root)"
    )
) -> FileResponse:
    """Export current configuration to CSV file (download)."""
    try:
        store = get_port_adjuster_store()
        config = store.get_config()
        
        if config is None:
            raise HTTPException(
                status_code=400,
                detail="No configuration available. Please configure first."
            )
        
        # Default path: project root / exposureadjuster.csv
        if file_path is None:
            # Get project root (quant_engine parent)
            project_root = Path(__file__).parent.parent.parent.parent
            file_path = str(project_root / "exposureadjuster.csv")
        
        success = save_config_to_csv(config, file_path)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to save CSV file"
            )
        
        return FileResponse(
            path=file_path,
            media_type="text/csv",
            filename=Path(file_path).name
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_API] Error exporting CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-csv")
async def import_csv(
    file_path: Optional[str] = Query(None, description="Path to CSV file to import"),
    upload_file: UploadFile = File(None)
) -> Dict[str, Any]:
    """
    Import configuration from CSV file.
    
    """
    try:
        # Support both file upload and path-based import
        temp_file = None
        import_path = file_path
        
        if upload_file is not None:
            temp_dir = Path(__file__).parent.parent.parent / "tmp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file = temp_dir / upload_file.filename
            with open(temp_file, "wb") as f:
                f.write(upload_file.file.read())
            import_path = str(temp_file)
        
        if import_path is None:
            raise HTTPException(status_code=400, detail="file_path or upload_file is required")
        
        config = load_config_from_csv(import_path)
        
        if config is None:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to load configuration from CSV: {import_path}"
            )
        
        # Update store with loaded config
        store = get_port_adjuster_store()
        store.config_source = f"csv:{Path(import_path).name}"
        snapshot = store.update_config(config)
        
        if temp_file and temp_file.exists():
            temp_file.unlink(missing_ok=True)
        
        return {
            "success": True,
            "message": "Configuration imported from CSV",
            "config": config,
            "snapshot": snapshot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_API] Error importing CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_config() -> PortAdjusterConfig:
    """
    Get current Port Adjuster configuration.
    
    Returns:
        Current PortAdjusterConfig
    """
    try:
        store = get_port_adjuster_store()
        config = store.get_config()
        
        if config is None:
            raise HTTPException(
                status_code=404,
                detail="Port Adjuster configuration not available"
            )
        
        return config
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_API] Error getting config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
# Preset management
# -------------------------------------------------------------------

@router.post("/presets/save")
async def save_preset(name: str, config: PortAdjusterConfig) -> Dict[str, Any]:
    """Save a preset."""
    try:
        store = get_port_adjuster_store()
        success = store.save_preset(name, config)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save preset")
        return {"success": True, "message": f"Preset '{name}' saved"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_API] Error saving preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presets/list")
async def list_presets() -> Dict[str, Any]:
    """List available presets."""
    try:
        store = get_port_adjuster_store()
        presets = store.list_presets()
        return {"success": True, "presets": presets}
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_API] Error listing presets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/presets/load")
async def load_preset(name: str) -> Dict[str, Any]:
    """Load preset by name."""
    try:
        store = get_port_adjuster_store()
        snapshot = store.load_preset(name)
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
        return {
            "success": True,
            "message": f"Preset '{name}' loaded",
            "snapshot": snapshot
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PORT_ADJUSTER_API] Error loading preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

