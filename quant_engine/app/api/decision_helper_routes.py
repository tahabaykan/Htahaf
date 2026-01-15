"""
Decision Helper API Routes

Handles job submission and result retrieval for decision helper analysis.
"""

import uuid
import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.logger import logger
from app.core.redis_client import get_redis_client

router = APIRouter(prefix="/api/decision-helper", tags=["decision-helper"])

# Redis keys
JOB_QUEUE_KEY = "tasks:decision_helper"
JOB_RESULT_PREFIX = "decision:"


@router.post("/compute")
async def start_decision_helper():
    """
    Start a decision helper job.
    
    Returns:
        - job_id: Unique job identifier
        - status: Initial status (queued)
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": "Redis not available. Decision helper worker is not running.",
                    "message": "Please ensure Redis is running and the worker process is started."
                }
            )
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Create job payload
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "symbols": None,  # None = all symbols
            "windows": ["5m", "15m", "30m"]  # Default windows
        }
        
        # Add to Redis queue (LPUSH)
        redis.lpush(JOB_QUEUE_KEY, json.dumps(job_data))
        
        logger.info(f"📊 Decision helper job queued: {job_id}")
        
        return {
            "success": True,
            "job_id": job_id,
            "status": "queued",
            "message": "Job queued successfully"
        }
        
    except Exception as e:
        logger.error(f"Error starting decision helper job: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "message": "Failed to start decision helper job"
            }
        )


@router.get("/result/{group}/{symbol}/{window}")
async def get_result(group: str, symbol: str, window: str):
    """
    Get decision helper result for a symbol and window.
    
    Args:
        group: Group name (e.g., "HELDFF")
        symbol: Symbol (e.g., "CIM PRB")
        window: Window name ("5m", "15m", "30m")
    
    Returns:
        Decision metrics and state classification
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": "Redis not available"
                }
            )
        
        # Get result from Redis
        result_key = f"{JOB_RESULT_PREFIX}{group}:{symbol}:{window}"
        result_data = redis.get(result_key)
        
        if not result_data:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "Result not found (may not be computed yet or expired)"
                }
            )
        
        result = json.loads(result_data)
        
        return {
            "success": True,
            "group": group,
            "symbol": symbol,
            "window": window,
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Error getting decision helper result: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


@router.get("/results/{group}")
async def get_group_results(group: str, window: Optional[str] = None):
    """
    Get all decision helper results for a group.
    
    Args:
        group: Group name (e.g., "HELDFF")
        window: Optional window filter ("5m", "15m", "30m")
    
    Returns:
        All results for the group
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": "Redis not available"
                }
            )
        
        # Search for all keys matching pattern
        pattern = f"{JOB_RESULT_PREFIX}{group}:*"
        if window:
            pattern = f"{JOB_RESULT_PREFIX}{group}:*:{window}"
        
        keys = redis.keys(pattern)
        results = {}
        
        for key in keys:
            try:
                # Parse key: decision:{group}:{symbol}:{window}
                parts = key.split(":")
                if len(parts) >= 4:
                    symbol = parts[2]
                    win = parts[3]
                    
                    result_data = redis.get(key)
                    if result_data:
                        result = json.loads(result_data)
                        if symbol not in results:
                            results[symbol] = {}
                        results[symbol][win] = result
            except Exception as e:
                logger.debug(f"Error parsing key {key}: {e}")
        
        return {
            "success": True,
            "group": group,
            "window": window,
            "data": results
        }
        
    except Exception as e:
        logger.error(f"Error getting group results: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


