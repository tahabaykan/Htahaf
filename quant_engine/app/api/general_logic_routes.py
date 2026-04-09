"""
API Routes for General Logic Configuration
Allows UI to read, update, and reset formula parameters
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/general-logic", tags=["General Logic"])


class UpdateConfigRequest(BaseModel):
    """Request model for updating config values."""
    updates: Dict[str, Any]


@router.get("")
async def get_general_logic() -> Dict[str, Any]:
    """
    Get all general logic configuration with descriptions.
    Returns all configurable parameters for display in UI.
    """
    try:
        from app.core.general_logic_store import get_general_logic_store
        store = get_general_logic_store()
        
        config_with_desc = store.get_with_descriptions()
        
        # Group by category for better UI organization
        grouped = {}
        for key, data in config_with_desc.items():
            category = key.split('.')[0]
            if category not in grouped:
                grouped[category] = {}
            grouped[category][key] = data
        
        return {
            "success": True,
            "config": config_with_desc,
            "grouped": grouped,
            "categories": list(grouped.keys())
        }
    except Exception as e:
        logger.error(f"Failed to get general logic config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save")
async def save_general_logic(request: UpdateConfigRequest) -> Dict[str, Any]:
    """
    Save updated configuration values.
    Validates and saves to qegenerallogic.csv.
    """
    try:
        from app.core.general_logic_store import get_general_logic_store
        store = get_general_logic_store()
        
        # Update and save
        success = store.update(request.updates)
        
        if success:
            logger.info(f"✅ General logic config saved with {len(request.updates)} updates")
            return {
                "success": True,
                "message": f"Saved {len(request.updates)} configuration values",
                "config": store.get_all()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save general logic config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_general_logic() -> Dict[str, Any]:
    """
    Reset all configuration to default values.
    Overwrites qegenerallogic.csv with defaults.
    """
    try:
        from app.core.general_logic_store import get_general_logic_store
        store = get_general_logic_store()
        
        success = store.reset_to_defaults()
        
        if success:
            logger.info("✅ General logic config reset to defaults")
            return {
                "success": True,
                "message": "Configuration reset to defaults",
                "config": store.get_all()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to reset configuration")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset general logic config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/defaults")
async def get_defaults() -> Dict[str, Any]:
    """
    Get default configuration values (without resetting).
    Useful for comparison in UI.
    """
    try:
        from app.core.general_logic_store import GeneralLogicStore
        
        return {
            "success": True,
            "defaults": GeneralLogicStore.DEFAULT_CONFIG
        }
    except Exception as e:
        logger.error(f"Failed to get defaults: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/value/{key:path}")
async def get_single_value(key: str) -> Dict[str, Any]:
    """
    Get a single configuration value by key.
    """
    try:
        from app.core.general_logic_store import get_general_logic_store
        store = get_general_logic_store()
        
        value = store.get(key)
        if value is None:
            raise HTTPException(status_code=404, detail=f"Key not found: {key}")
        
        return {
            "success": True,
            "key": key,
            "value": value
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get value for {key}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


