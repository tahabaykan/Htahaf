"""
Scanner Filter Presets API
Save and load filter presets for the main scanner page.
Similar to Port Adjuster preset system.
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
import json
import os
from pathlib import Path
from app.core.logger import logger

router = APIRouter(prefix="/api/scanner-filters", tags=["scanner-filters"])

# Preset storage directory
PRESETS_DIR = Path("data/scanner_filter_presets")
PRESETS_DIR.mkdir(parents=True, exist_ok=True)


def _get_preset_path(name: str) -> Path:
    """Get file path for a preset"""
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    return PRESETS_DIR / f"{safe_name}.json"


@router.get("/presets/list")
async def list_presets() -> Dict[str, Any]:
    """List all available filter presets"""
    try:
        presets = []
        if PRESETS_DIR.exists():
            for file in PRESETS_DIR.glob("*.json"):
                presets.append(file.stem)
        presets.sort()
        return {"success": True, "presets": presets}
    except Exception as e:
        logger.error(f"Error listing presets: {e}", exc_info=True)
        # Return empty list instead of raising exception
        return {"success": True, "presets": []}


@router.post("/presets/save")
async def save_preset(
    name: str = Query(..., description="Preset name"),
    filter_state: Dict[str, Any] = Body(..., description="Filter state to save")
) -> Dict[str, Any]:
    """Save current filter state as a preset"""
    try:
        if not name or not name.strip():
            raise HTTPException(status_code=400, detail="Preset name is required")
        
        preset_path = _get_preset_path(name)
        
        # Save preset
        with open(preset_path, 'w', encoding='utf-8') as f:
            json.dump(filter_state, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved scanner filter preset: {name}")
        return {
            "success": True,
            "message": f"Preset '{name}' saved successfully"
        }
    except Exception as e:
        logger.error(f"Error saving preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/presets/load")
async def load_preset(
    name: str = Query(..., description="Preset name")
) -> Dict[str, Any]:
    """Load a filter preset"""
    try:
        if not name or not name.strip():
            raise HTTPException(status_code=400, detail="Preset name is required")
        
        preset_path = _get_preset_path(name)
        
        if not preset_path.exists():
            raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
        
        # Load preset
        with open(preset_path, 'r', encoding='utf-8') as f:
            filter_state = json.load(f)
        
        logger.info(f"Loaded scanner filter preset: {name}")
        return {
            "success": True,
            "filterState": filter_state,
            "message": f"Preset '{name}' loaded successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/presets/delete")
async def delete_preset(
    name: str = Query(..., description="Preset name")
) -> Dict[str, Any]:
    """Delete a filter preset"""
    try:
        if not name or not name.strip():
            raise HTTPException(status_code=400, detail="Preset name is required")
        
        preset_path = _get_preset_path(name)
        
        if not preset_path.exists():
            raise HTTPException(status_code=404, detail=f"Preset '{name}' not found")
        
        preset_path.unlink()
        
        logger.info(f"Deleted scanner filter preset: {name}")
        return {
            "success": True,
            "message": f"Preset '{name}' deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

