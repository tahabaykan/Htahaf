"""
DecisionHelperV2 API Routes

Endpoints for submitting jobs and retrieving results.
"""

import json
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.redis_client import get_redis_client
from app.core.logger import logger
import time

router = APIRouter(prefix="/api/decision-helper-v2", tags=["DecisionHelperV2"])

# Redis keys
STREAM_NAME = "tasks:decision_helper_v2"
JOB_RESULT_PREFIX = "decision_v2:"


class DecisionHelperV2JobRequest(BaseModel):
    """Request model for DecisionHelperV2 job"""
    symbols: Optional[List[str]] = None  # If None, process all symbols with ticks
    windows: Optional[List[str]] = None  # Default: ['pan_10m', 'pan_30m', 'pan_1h']


class DecisionHelperV2JobResponse(BaseModel):
    """Response model for job submission"""
    job_id: str
    status: str
    message: str


@router.post("/submit-job", response_model=DecisionHelperV2JobResponse)
async def submit_job(request: DecisionHelperV2JobRequest):
    """
    Submit a DecisionHelperV2 job to Redis stream.
    
    The worker will process this job asynchronously.
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            raise HTTPException(
                status_code=503,
                detail="Redis not available. DecisionHelperV2 worker is not running."
            )
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Default windows - use all supported windows if not specified
        valid_windows = ['pan_10m', 'pan_30m', 'pan_1h', 'pan_3h', 'pan_1d']
        if request.windows and len(request.windows) > 0:
            windows = request.windows
            # Validate windows
            invalid_windows = [w for w in windows if w not in valid_windows]
            if invalid_windows:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid windows: {invalid_windows}. Valid windows: {valid_windows}"
                )
        else:
            # Default to all supported windows
            windows = valid_windows
        
        # Create job data
        job_data = {
            'job_id': job_id,
            'symbols': request.symbols,
            'windows': windows,
            'timestamp': str(uuid.uuid4())
        }
        
        # Add to Redis stream
        redis.xadd(STREAM_NAME, {
            'data': json.dumps(job_data)
        })
        
        logger.info(f"✅ DecisionHelperV2 job submitted: {job_id} with windows: {windows}")
        
        return DecisionHelperV2JobResponse(
            job_id=job_id,
            status="submitted",
            message=f"Job {job_id} submitted successfully"
        )
    
    except Exception as e:
        logger.error(f"❌ Error submitting DecisionHelperV2 job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/result/{symbol}/{window}")
async def get_result(symbol: str, window: str):
    """
    Get DecisionHelperV2 result for a symbol and window.
    
    Results are cached in Redis with 1 hour TTL.
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            raise HTTPException(
                status_code=503,
                detail="Redis not available"
            )
        
        redis_key = f"{JOB_RESULT_PREFIX}{symbol}:{window}"
        result_str = redis.get(redis_key)
        
        if not result_str:
            raise HTTPException(
                status_code=404,
                detail=f"No result found for {symbol} ({window})"
            )
        
        result = json.loads(result_str)
        
        # 🛡️ SHADOW MODE: Enrich with V2 Snapshot if available
        v2_key = f"state:snapshot_cache_v2:{symbol}"
        v2_data = redis.hgetall(v2_key)
        if v2_data:
            try:
                # Convert from byte strings and handle types
                v2_final = {}
                for k, v in v2_data.items():
                    k_str = k.decode('utf-8') if isinstance(k, bytes) else k
                    v_str = v.decode('utf-8') if isinstance(v, bytes) else v
                    try:
                        if k_str in ['bid', 'ask', 'timestamp']:
                            v2_final[k_str] = float(v_str)
                        else:
                            v2_final[k_str] = v_str
                    except:
                        v2_final[k_str] = v_str
                
                # Calculate age
                if 'timestamp' in v2_final:
                    v2_final['age'] = round(time.time() - v2_final['timestamp'], 1)
                result['v2_snapshot'] = v2_final
            except Exception as e:
                logger.debug(f"Error enriching V2 snapshot: {e}")
                
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving DecisionHelperV2 result: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/{symbol}")
async def get_symbol_results(symbol: str):
    """
    Get all DecisionHelperV2 results for a symbol across all windows.
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            raise HTTPException(
                status_code=503,
                detail="Redis not available"
            )
        
        # Search for all keys matching pattern
        pattern = f"{JOB_RESULT_PREFIX}{symbol}:*"
        keys = redis.keys(pattern)
        
        results = {}
        for key in keys:
            window = key.split(':')[-1]  # Extract window name
            result_str = redis.get(key)
            if result_str:
                res_obj = json.loads(result_str)
                # 🛡️ SHADOW MODE: Enrich with V2 Snapshot if available
                v2_key = f"state:snapshot_cache_v2:{symbol}"
                v2_data = redis.hgetall(v2_key)
                if v2_data:
                    try:
                        v2_final = {}
                        for k, v in v2_data.items():
                            k_str = k.decode('utf-8') if isinstance(k, bytes) else k
                            v_str = v.decode('utf-8') if isinstance(v, bytes) else v
                            try:
                                if k_str in ['bid', 'ask', 'timestamp']:
                                    v2_final[k_str] = float(v_str)
                                else:
                                    v2_final[k_str] = v_str
                            except:
                                v2_final[k_str] = v_str
                        
                        if 'timestamp' in v2_final:
                            v2_final['age'] = round(time.time() - v2_final['timestamp'], 1)
                        res_obj['v2_snapshot'] = v2_final
                    except:
                        pass
                results[window] = res_obj
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No results found for {symbol}"
            )
        
        return {
            'symbol': symbol,
            'windows': results,
            'timestamp': str(uuid.uuid4())
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error retrieving DecisionHelperV2 results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


