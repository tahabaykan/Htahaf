"""
Deeper Analysis API Routes

Handles job submission, status checking, and result retrieval for deeper analysis
(GOD, ROD, GRPAN) using Redis-based worker architecture.
"""

import uuid
import json
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.logger import logger
from app.core.redis_client import get_redis_client

router = APIRouter(prefix="/api/deeper-analysis", tags=["deeper-analysis"])

# Redis keys
JOB_QUEUE_KEY = "deeper_analysis:jobs"
JOB_STATUS_PREFIX = "deeper_analysis:status:"
JOB_RESULT_PREFIX = "deeper_analysis:result:"


@router.post("/compute")
async def start_deeper_analysis():
    """
    Start a deeper analysis job (GOD, ROD, GRPAN).
    
    Returns:
        - job_id: Unique job identifier
        - status: Initial status (queued)
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            # Fallback: return error but suggest using fallback endpoint
            logger.warning("Redis not available, deeper analysis worker unavailable")
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": "Redis not available. Deeper analysis worker is not running.",
                    "message": "Please ensure Redis is running and the worker process is started."
                }
            )
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Create job payload
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "created_at": str(uuid.uuid1().time),
            "symbols": None  # None = all symbols
        }
        
        # Add to Redis queue (LPUSH)
        redis.lpush(JOB_QUEUE_KEY, json.dumps(job_data))
        
        # Set initial status
        redis.setex(
            f"{JOB_STATUS_PREFIX}{job_id}",
            3600,  # 1 hour TTL
            json.dumps({"status": "queued", "message": "Job queued for processing"})
        )
        
        logger.info(f"📊 Deeper analysis job queued: {job_id}")
        
        return {
            "success": True,
            "job_id": job_id,
            "status": "queued",
            "message": "Job queued successfully"
        }
        
    except Exception as e:
        logger.error(f"Error starting deeper analysis job: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "message": "Failed to start deeper analysis job"
            }
        )


@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Get the status of a deeper analysis job.
    
    Returns:
        - status: queued, processing, completed, or failed
        - message: Status message
        - error: Error message (if failed)
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
        
        # Get status from Redis
        status_key = f"{JOB_STATUS_PREFIX}{job_id}"
        status_data = redis.get(status_key)
        
        if not status_data:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "Job not found",
                    "status": "not_found"
                }
            )
        
        status_info = json.loads(status_data)
        
        return {
            "success": True,
            "job_id": job_id,
            **status_info
        }
        
    except Exception as e:
        logger.error(f"Error getting job status: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "status": "error"
            }
        )


@router.get("/result/{job_id}")
async def get_job_result(job_id: str):
    """
    Get the result of a completed deeper analysis job.
    
    Returns:
        - success: Whether the request was successful
        - data: Analysis results (if completed)
        - error: Error message (if failed)
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
        
        # Check status first
        status_key = f"{JOB_STATUS_PREFIX}{job_id}"
        status_data = redis.get(status_key)
        
        if not status_data:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "Job not found"
                }
            )
        
        status_info = json.loads(status_data)
        
        if status_info.get("status") != "completed":
            return {
                "success": False,
                "error": f"Job not completed yet. Status: {status_info.get('status')}",
                "status": status_info.get("status")
            }
        
        # Get result from Redis
        result_key = f"{JOB_RESULT_PREFIX}{job_id}"
        result_data = redis.get(result_key)
        
        if not result_data:
            return JSONResponse(
                status_code=404,
                content={
                    "success": False,
                    "error": "Result not found (may have expired)"
                }
            )
        
        result = json.loads(result_data)
        
        # Worker result format: {success: True, job_id: ..., data: {symbol: {...}}, ...}
        # Return the entire result as-is (worker already formatted it correctly)
        return result
        
    except Exception as e:
        logger.error(f"Error getting job result: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )


