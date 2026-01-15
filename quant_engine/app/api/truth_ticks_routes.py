"""
Truth Ticks API Routes

Endpoints for submitting truth ticks analysis jobs and retrieving results.
"""

import json
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.redis_client import get_redis_client
from app.core.logger import logger

router = APIRouter(prefix="/api/truth-ticks", tags=["TruthTicks"])

# Redis keys
STREAM_NAME = "tasks:truth_ticks"
JOB_RESULT_PREFIX = "truth_ticks:"


class TruthTicksJobRequest(BaseModel):
    """Request model for Truth Ticks job"""
    symbols: Optional[List[str]] = None  # If None, process all symbols with ticks


class TruthTicksJobResponse(BaseModel):
    """Response model for job submission"""
    job_id: str
    status: str
    message: str


@router.post("/submit-job", response_model=TruthTicksJobResponse)
async def submit_job(request: TruthTicksJobRequest):
    """
    Submit a Truth Ticks analysis job to Redis stream.
    
    The worker will process this job asynchronously.
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            raise HTTPException(
                status_code=503,
                detail="Redis not available. Truth Ticks worker is not running."
            )
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Create job data
        job_data = {
            'job_id': job_id,
            'symbols': request.symbols,
            'timestamp': str(uuid.uuid4())
        }
        
        # Add to Redis stream
        redis.xadd(STREAM_NAME, {
            'data': json.dumps(job_data)
        })
        
        logger.info(f"✅ Truth Ticks job submitted: {job_id} for {len(request.symbols) if request.symbols else 'all'} symbols")
        
        return TruthTicksJobResponse(
            job_id=job_id,
            status="submitted",
            message=f"Job {job_id} submitted successfully"
        )
    
    except Exception as e:
        logger.error(f"Error submitting Truth Ticks job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/result/all")
async def get_all_results():
    """
    Get Truth Ticks analysis results for all symbols.
    
    First tries to get from latest job result in Redis (worker stores results there),
    then falls back to TruthTicksEngine (if worker has populated it).
    
    Returns:
        Dict of {symbol: metrics} for all symbols with data
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            logger.warning("⚠️ Redis client not available, falling back to TruthTicksEngine")
        else:
            # Test Redis connection
            try:
                redis.ping()
            except Exception as e:
                logger.error(f"❌ Redis connection test failed: {e}")
                redis = None
        
        # Try to get from latest job result in Redis first
        if redis:
            try:
                # Get all job result keys
                pattern = f"{JOB_RESULT_PREFIX}*"
                logger.debug(f"🔍 Searching Redis for keys matching pattern: {pattern}")
                result_keys = redis.keys(pattern)
                
                # Decode byte strings if needed
                if result_keys:
                    result_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in result_keys]
                    logger.info(f"📦 Found {len(result_keys)} job result keys in Redis: {result_keys[:5]}...")  # Log first 5
                
                if result_keys:
                    # Get the most recent job result by checking updated_at timestamps
                    latest_result = None
                    latest_key = None
                    latest_timestamp = None
                    
                    for key in result_keys:
                        try:
                            result_json = redis.get(key)
                            if result_json:
                                # Decode if bytes
                                if isinstance(result_json, bytes):
                                    result_json = result_json.decode('utf-8')
                                
                                result = json.loads(result_json)
                                # Check if it has data and is successful
                                if result.get('success') and result.get('data') and len(result.get('data', {})) > 0:
                                    updated_at = result.get('updated_at', '')
                                    # Compare timestamps to find latest (ISO format strings are comparable)
                                    if not latest_result or (updated_at and updated_at > (latest_timestamp or '')):
                                        latest_result = result
                                        latest_key = key
                                        latest_timestamp = updated_at or ''
                        except Exception as e:
                            logger.warning(f"⚠️ Error parsing Redis result {key}: {e}", exc_info=True)
                            continue
                    
                    if latest_result and latest_result.get('data') and len(latest_result.get('data', {})) > 0:
                        logger.info(f"✅ Got results from Redis cache: {latest_key}, {len(latest_result.get('data', {}))} symbols, updated_at: {latest_result.get('updated_at', 'N/A')}")
                        return {
                            "success": True,
                            "count": latest_result.get('processed_count', len(latest_result.get('data', {}))),
                            "data": latest_result.get('data', {}),
                            "job_id": latest_result.get('job_id'),
                            "updated_at": latest_result.get('updated_at'),
                            "message": "Results from latest job cache"
                        }
                    else:
                        logger.warning(f"⚠️ Found {len(result_keys)} Redis keys but no valid results with data")
                else:
                    logger.debug(f"🔍 No Redis keys found matching pattern: {pattern}")
            except Exception as e:
                logger.error(f"❌ Error reading from Redis cache: {e}", exc_info=True)
        
        # Fallback: Try to get from TruthTicksEngine (if worker has populated it)
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        
        # Get all symbols
        symbols = truth_engine.get_all_symbols()
        
        if not symbols:
            return {
                "success": True,
                "count": 0,
                "data": {},
                "message": "No symbols with Truth Ticks data available. Worker may still be processing."
            }
        
        # Get metrics for each symbol
        results = {}
        for symbol in symbols:
            try:
                # Get AVG_ADV
                avg_adv = 0.0
                if static_store:
                    record = static_store.get_static_data(symbol)
                    if record:
                        avg_adv = float(record.get('AVG_ADV', 0) or 0)
                
                # Get metrics
                metrics = truth_engine.get_metrics(symbol, avg_adv)
                if metrics:
                    results[symbol] = metrics
            except Exception as e:
                logger.debug(f"Error getting metrics for {symbol}: {e}")
                continue
        
        return {
            "success": True,
            "count": len(results),
            "data": results
        }
    
    except Exception as e:
        logger.error(f"Error getting all Truth Ticks results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/result/{job_id}")
async def get_result(job_id: str):
    """
    Get Truth Ticks analysis result for a job.
    
    Args:
        job_id: Job ID from submit-job response
        
    Returns:
        Result dict with metrics for each symbol
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            raise HTTPException(
                status_code=503,
                detail="Redis not available"
            )
        
        # Get result from Redis
        result_key = f"{JOB_RESULT_PREFIX}{job_id}"
        logger.debug(f"🔍 Looking for job result in Redis: {result_key}")
        result_json = redis.get(result_key)
        
        if not result_json:
            # Check if any results exist at all
            all_keys = redis.keys(f"{JOB_RESULT_PREFIX}*")
            if all_keys:
                all_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in all_keys]
                logger.debug(f"⚠️ Job {job_id} not found, but found {len(all_keys)} other job results: {all_keys[:3]}...")
            else:
                logger.debug(f"⚠️ Job {job_id} not found, and no job results exist in Redis")
            raise HTTPException(
                status_code=404,
                detail=f"Result not found for job {job_id}. Job may still be processing or has expired."
            )
        
        # Decode if bytes
        if isinstance(result_json, bytes):
            result_json = result_json.decode('utf-8')
        
        result = json.loads(result_json)
        
        return {
            "success": True,
            "job_id": job_id,
            "result": result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Truth Ticks result: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/result/symbol/{symbol}")
async def get_symbol_result(symbol: str):
    """
    Get Truth Ticks analysis result for a specific symbol (from cache).
    
    Args:
        symbol: Symbol name (e.g., "CIM PRB")
        
    Returns:
        Metrics dict for the symbol
    """
    try:
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        
        # Get AVG_ADV
        avg_adv = 0.0
        if static_store:
            record = static_store.get_static_data(symbol)
            if record:
                avg_adv = float(record.get('AVG_ADV', 0) or 0)
        
        # Get metrics
        metrics = truth_engine.get_metrics(symbol, avg_adv)
        
        if not metrics:
            raise HTTPException(
                status_code=404,
                detail=f"No Truth Ticks data available for {symbol}. Ensure worker is running and collecting ticks."
            )
        
        return {
            "success": True,
            "symbol": symbol,
            "data": metrics
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Truth Ticks result for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_summary():
    """
    Get Truth Ticks summary for all symbols (optimized for table display).
    
    Returns:
        Dict of {symbol: summary_metrics} for all symbols with data
    """
    try:
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        
        # Get all symbols
        symbols = truth_engine.get_all_symbols()
        
        if not symbols:
            return {
                "success": True,
                "count": 0,
                "data": {},
                "message": "No symbols with Truth Ticks data available"
            }
        
        # Get metrics for each symbol
        results = {}
        for symbol in symbols:
            try:
                # Get AVG_ADV
                avg_adv = 0.0
                if static_store:
                    record = static_store.get_static_data(symbol)
                    if record:
                        avg_adv = float(record.get('AVG_ADV', 0) or 0)
                
                # Get metrics
                metrics = truth_engine.get_metrics(symbol, avg_adv)
                if metrics:
                    # Return only essential fields for table
                    results[symbol] = {
                        'symbol': symbol,
                        'timeframe': metrics.get('timeframe'),  # Format: "4d3h30m"
                        'timeframe_seconds': metrics.get('timeframe_seconds'),  # For sorting
                        'truth_tick_count_100': metrics.get('truth_tick_count_100', 0),
                        'truth_volume_100': metrics.get('truth_volume_100', 0),
                        'truth_vwap_100': metrics.get('truth_vwap_100'),
                        'truth_adv_fraction_100': metrics.get('adv_fraction_truth', 0),
                        'volav1_start': metrics.get('volav1_start'),
                        'volav1_end': metrics.get('volav1_end'),
                        'volav1_displacement': metrics.get('volav1_displacement'),
                        'volav_shift': metrics.get('volav1_displacement'),
                        'volav_levels': metrics.get('volav_levels', []),
                        'volav_timeline': metrics.get('volav_timeline', []),  # Required for dominance score
                        'volav1': metrics.get('volav_levels', [{}])[0].get('price') if metrics.get('volav_levels') else None,
                        'volav2': metrics.get('volav_levels', [{}])[1].get('price') if len(metrics.get('volav_levels', [])) > 1 else None,
                        'volav3': metrics.get('volav_levels', [{}])[2].get('price') if len(metrics.get('volav_levels', [])) > 2 else None,
                        'volav4': metrics.get('volav_levels', [{}])[3].get('price') if len(metrics.get('volav_levels', [])) > 3 else None,
                        'state': metrics.get('state', 'UNKNOWN'),
                        'state_confidence': metrics.get('state_confidence', 0),
                        'flags': metrics.get('flags', {})
                    }
            except Exception as e:
                logger.debug(f"Error getting metrics for {symbol}: {e}")
                continue
        
        return {
            "success": True,
            "count": len(results),
            "data": results
        }
    
    except Exception as e:
        logger.error(f"Error getting Truth Ticks summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inspect")
async def inspect_symbol(symbol: str = Query(..., description="Symbol to inspect")):
    """
    Get detailed inspection data for a symbol (full explainability).
    
    First tries to get from Redis cache (worker stores it there),
    then tries TruthTicksEngine (if worker has populated it).
    
    Returns:
        Detailed dict with filtering report, Volav details, time segmentation, path dataset
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        # First, try to get from Redis cache (worker stores inspect data there)
        if redis:
            inspect_key = f"truth_ticks:inspect:{symbol}"
            cached_data = redis.get(inspect_key)
            if cached_data:
                try:
                    result = json.loads(cached_data)
                    if result.get('success') and result.get('data'):
                        logger.debug(f"✅ Got inspect data for {symbol} from Redis cache")
                        return result
                except Exception as e:
                    logger.debug(f"Error parsing cached inspect data: {e}")
        
        # Fallback: Try to get from TruthTicksEngine (worker may have populated it)
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        
        # Get AVG_ADV
        avg_adv = 0.0
        if static_store:
            record = static_store.get_static_data(symbol)
            if record:
                avg_adv = float(record.get('AVG_ADV', 0) or 0)
        
        # Try to get inspect data from engine
        inspect_data = truth_engine.get_inspect_data(symbol, avg_adv)
        
        if not inspect_data:
            raise HTTPException(
                status_code=404,
                detail=f"No Truth Ticks data available for {symbol}. Worker may still be collecting ticks. Try again in a few seconds after running analysis."
            )
        
        return {
            "success": True,
            "symbol": symbol,
            "data": inspect_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting inspect data for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dominance-scores")
async def get_dominance_scores(timeframe: Optional[str] = Query(None, description="Timeframe: TF_4H, TF_1D, TF_3D, TF_5D")):
    """
    Get Buyer-Seller Dominance scores for all symbols with Truth Ticks data.
    
    NEW: Timeframe-based analysis. If timeframe is provided, uses fixed time windows.
    If not provided, falls back to legacy tick-count-based method.
    
    Args:
        timeframe: Optional timeframe name (TF_4H, TF_1D, TF_3D, TF_5D)
    
    Returns:
        Dict with dominance scores and sub-scores for each symbol
        Structure: {symbol: {timeframe_name: score_data}} if timeframe provided
        Or: {symbol: score_data} if legacy mode
    """
    try:
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.buyer_seller_dominance_engine import get_buyer_seller_dominance_engine
        from app.market_data.static_data_store import get_static_store
        
        truth_engine = get_truth_ticks_engine()
        dominance_engine = get_buyer_seller_dominance_engine()
        static_store = get_static_store()
        
        if not truth_engine or not dominance_engine:
            raise HTTPException(
                status_code=503,
                detail="Engines not available"
            )
        
        # Log the timeframe parameter for debugging
        logger.info(f"🔍 Dominance scores request - timeframe parameter: {timeframe} (type: {type(timeframe)})")
        
        # NEW: Timeframe-based analysis
        if timeframe and timeframe in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']:
            logger.info(f"✅ Using timeframe-based analysis: {timeframe}")
            result = await _get_dominance_scores_timeframe_based(
                truth_engine, dominance_engine, static_store, timeframe
            )
            logger.info(f"📊 Timeframe-based result: {result.get('count', 0)} symbols, timeframe={result.get('timeframe')}")
            return result
        
        # If timeframe is provided but invalid, log warning
        if timeframe:
            logger.warning(f"⚠️ Invalid timeframe '{timeframe}', falling back to legacy method")
        else:
            logger.warning(f"⚠️ No timeframe parameter provided, falling back to legacy method")
        
        # LEGACY: Tick-count-based (backward compatibility)
        # First, try to get from Redis (same as /result/all)
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        truth_metrics_dict = {}
        
        if redis:
            try:
                pattern = f"{JOB_RESULT_PREFIX}*"
                result_keys = redis.keys(pattern)
                
                if result_keys:
                    result_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in result_keys]
                    
                    # Get the most recent job result
                    latest_result = None
                    latest_timestamp = None
                    
                    for key in result_keys:
                        try:
                            result_json = redis.get(key)
                            if result_json:
                                if isinstance(result_json, bytes):
                                    result_json = result_json.decode('utf-8')
                                
                                result = json.loads(result_json)
                                if result.get('success') and result.get('data') and len(result.get('data', {})) > 0:
                                    updated_at = result.get('updated_at', '')
                                    if not latest_result or (updated_at and updated_at > (latest_timestamp or '')):
                                        latest_result = result
                                        latest_timestamp = updated_at or ''
                        except Exception as e:
                            logger.warning(f"Error parsing Redis result {key}: {e}")
                            continue
                    
                    if latest_result and latest_result.get('data'):
                        # Use metrics from Redis cache
                        truth_metrics_dict = latest_result.get('data', {})
                        logger.info(f"Using {len(truth_metrics_dict)} symbols from Redis cache for dominance scores")
            except Exception as e:
                logger.warning(f"Error reading from Redis: {e}")
        
        # Fallback: Get from TruthTicksEngine
        if not truth_metrics_dict:
            symbols = truth_engine.get_all_symbols()
            if not symbols:
                return {
                    "success": True,
                    "count": 0,
                    "data": {}
                }
            
            for symbol in symbols:
                try:
                    avg_adv = 0.0
                    if static_store:
                        record = static_store.get_static_data(symbol)
                        if record:
                            avg_adv = float(record.get('AVG_ADV', 0) or 0)
                    
                    metrics = truth_engine.get_metrics(symbol, avg_adv)
                    if metrics:
                        truth_metrics_dict[symbol] = metrics
                except Exception as e:
                    logger.debug(f"Error getting metrics for {symbol}: {e}")
                    continue
        
        if not truth_metrics_dict:
            return {
                "success": True,
                "count": 0,
                "data": {}
            }
        
        # Compute dominance scores for all symbols
        # Handle both multi-timeframe structure and legacy single-timeframe structure
        results = {}
        
        for symbol, symbol_data in truth_metrics_dict.items():
            try:
                # Check if it's multi-timeframe structure
                if isinstance(symbol_data, dict) and any(tf in symbol_data for tf in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']):
                    # Multi-timeframe structure - use TF_1D as default for legacy path
                    if 'TF_1D' in symbol_data:
                        timeframe_metrics = symbol_data['TF_1D']
                        if isinstance(timeframe_metrics, dict):
                            truth_metrics = timeframe_metrics.copy()
                        else:
                            logger.warning(f"⚠️ TF_1D metrics for {symbol} is not a dict: {type(timeframe_metrics)}")
                            continue
                    elif 'TF_4H' in symbol_data:
                        timeframe_metrics = symbol_data['TF_4H']
                        if isinstance(timeframe_metrics, dict):
                            truth_metrics = timeframe_metrics.copy()
                        else:
                            logger.warning(f"⚠️ TF_4H metrics for {symbol} is not a dict: {type(timeframe_metrics)}")
                            continue
                    else:
                        # Use first available timeframe
                        first_tf = next(iter([tf for tf in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D'] if tf in symbol_data]), None)
                        if first_tf:
                            timeframe_metrics = symbol_data[first_tf]
                            if isinstance(timeframe_metrics, dict):
                                truth_metrics = timeframe_metrics.copy()
                            else:
                                logger.warning(f"⚠️ {first_tf} metrics for {symbol} is not a dict: {type(timeframe_metrics)}")
                                continue
                        else:
                            logger.debug(f"No timeframe data for {symbol} in legacy path")
                            continue
                    
                    # CRITICAL: Ensure symbol is ALWAYS set
                    truth_metrics['symbol'] = symbol
                else:
                    # Legacy single-timeframe structure
                    if isinstance(symbol_data, dict):
                        truth_metrics = symbol_data.copy()
                    else:
                        logger.warning(f"⚠️ Symbol data for {symbol} is not a dict: {type(symbol_data)}")
                        continue
                    
                    # CRITICAL: Ensure symbol is ALWAYS set
                    truth_metrics['symbol'] = symbol
                
                # TODO: Get PFF return if available (for relative strength)
                # For now, pass None
                pff_return = None
                
                # Compute dominance score
                dominance_result = dominance_engine.compute_dominance_score(
                    truth_metrics,
                    pff_return=pff_return
                )
                
                if dominance_result:
                    results[symbol] = dominance_result
                else:
                    logger.debug(f"Could not compute dominance score for {symbol} (insufficient data)")
                    
            except Exception as e:
                logger.warning(f"Error computing dominance score for {symbol}: {e}", exc_info=True)
                continue
        
        logger.info(f"Computed dominance scores for {len(results)} out of {len(truth_metrics_dict)} symbols")
        
        return {
            "success": True,
            "count": len(results),
            "data": results
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dominance scores: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _get_dominance_scores_timeframe_based(
    truth_engine,
    dominance_engine,
    static_store,
    timeframe: str
) -> Dict[str, Any]:
    """
    Helper function to compute dominance scores for a specific timeframe.
    
    NOTE: Backend TruthTicksEngine doesn't have tick data (worker has it).
    So we get symbols from Redis cache (worker's results) and use legacy metrics
    but label them with the requested timeframe.
    
    TODO: In the future, worker should compute timeframe-based metrics and store in Redis.
    
    Returns:
        Dict with structure: {symbol: score_data}
    """
    # Get symbols from Redis cache (worker's results)
    redis_client = get_redis_client()
    redis = redis_client.sync
    
    symbols = []
    truth_metrics_dict = {}
    
    if redis:
        try:
            # Get latest job result from Redis
            pattern = f"{JOB_RESULT_PREFIX}*"
            result_keys = redis.keys(pattern)
            
            if result_keys:
                result_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in result_keys]
                
                # Get the most recent job result
                latest_result = None
                latest_timestamp = None
                
                for key in result_keys:
                    try:
                        result_json = redis.get(key)
                        if result_json:
                            if isinstance(result_json, bytes):
                                result_json = result_json.decode('utf-8')
                            
                            result = json.loads(result_json)
                            if result.get('success') and result.get('data') and len(result.get('data', {})) > 0:
                                updated_at = result.get('updated_at', '')
                                if not latest_result or (updated_at and updated_at > (latest_timestamp or '')):
                                    latest_result = result
                                    latest_timestamp = updated_at or ''
                    except Exception as e:
                        logger.warning(f"Error parsing Redis result {key}: {e}")
                        continue
                
                if latest_result and latest_result.get('data'):
                    truth_metrics_dict = latest_result.get('data', {})
                    # Worker now returns multi-timeframe: {symbol: {TF_4H: metrics, ...}}
                    # Extract symbols from top level
                    symbols = list(truth_metrics_dict.keys())
                    logger.info(f"📦 Got {len(symbols)} symbols from Redis cache for timeframe-based analysis (multi-timeframe structure)")
        except Exception as e:
            logger.warning(f"Error reading from Redis: {e}")
    
    # Fallback: Try to get from TruthTicksEngine (may be empty)
    if not symbols:
        symbols = truth_engine.get_all_symbols()
        logger.warning(f"⚠️ No symbols from Redis, using TruthTicksEngine: {len(symbols)} symbols")
    
    if not symbols:
        return {
            "success": True,
            "count": 0,
            "data": {},
            "timeframe": timeframe
        }
    
    results = {}
    skipped_no_avg_adv = 0
    skipped_no_timeframe = 0
    skipped_no_metrics = 0
    processed_count = 0
    
    for symbol in symbols:
        try:
            # Get AVG_ADV
            avg_adv = 0.0
            if static_store:
                record = static_store.get_static_data(symbol)
                if record:
                    avg_adv = float(record.get('AVG_ADV', 0) or 0)
            
            if avg_adv <= 0:
                skipped_no_avg_adv += 1
                continue
            
            # Worker now returns multi-timeframe structure: {symbol: {TF_4H: metrics, TF_1D: metrics, ...}}
            # Check if we have multi-timeframe data
            if symbol in truth_metrics_dict:
                symbol_data = truth_metrics_dict[symbol]
                
                # Debug: Log first symbol's structure
                if processed_count == 0 and skipped_no_avg_adv == 0 and skipped_no_timeframe == 0:
                    logger.info(f"🔍 Sample symbol_data structure for {symbol}: type={type(symbol_data)}, keys={list(symbol_data.keys())[:10] if isinstance(symbol_data, dict) else 'not a dict'}")
                
                # Check if it's multi-timeframe structure
                if isinstance(symbol_data, dict) and any(tf in symbol_data for tf in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']):
                    # Multi-timeframe structure - get the requested timeframe
                    if timeframe in symbol_data:
                        timeframe_metrics = symbol_data[timeframe]
                        if isinstance(timeframe_metrics, dict):
                            truth_metrics = timeframe_metrics.copy()
                            
                            # Debug: Log first successful extraction
                            if processed_count == 0:
                                logger.info(f"✅ Successfully extracted {timeframe} metrics for {symbol}: keys={list(truth_metrics.keys())[:10]}")
                        else:
                            skipped_no_metrics += 1
                            if skipped_no_metrics <= 5:
                                logger.warning(f"⚠️ Timeframe metrics for {symbol} ({timeframe}) is not a dict: {type(timeframe_metrics)}")
                            continue
                        
                        # CRITICAL: Ensure symbol is ALWAYS set (may be missing in timeframe-specific metrics)
                        truth_metrics['symbol'] = symbol
                        # Ensure timeframe_name is set correctly (never UNKNOWN)
                        truth_metrics['timeframe_name'] = timeframe
                    else:
                        skipped_no_timeframe += 1
                        if skipped_no_timeframe <= 5:  # Log first 5 only
                            available_tfs = [tf for tf in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D'] if tf in symbol_data]
                            logger.debug(f"No {timeframe} data for {symbol}, available timeframes: {available_tfs}")
                        continue
                else:
                    # Legacy single-timeframe structure - override timeframe_name
                    if isinstance(symbol_data, dict):
                        truth_metrics = symbol_data.copy()
                    else:
                        logger.warning(f"⚠️ Symbol data for {symbol} is not a dict: {type(symbol_data)}")
                        continue
                    
                    # CRITICAL: Ensure symbol is ALWAYS set
                    truth_metrics['symbol'] = symbol
                    truth_metrics['timeframe_name'] = timeframe
            else:
                # Fallback: Try to compute from backend (may fail if no tick data)
                truth_metrics = truth_engine.compute_metrics_for_timeframe(
                    symbol, avg_adv, timeframe
                )
                if not truth_metrics:
                    skipped_no_metrics += 1
                    if skipped_no_metrics <= 5:  # Log first 5 only
                        logger.debug(f"No metrics computed for {symbol} ({timeframe}) from backend")
                    continue
                # CRITICAL: Ensure symbol is ALWAYS set
                if not isinstance(truth_metrics, dict):
                    skipped_no_metrics += 1
                    logger.warning(f"⚠️ compute_metrics_for_timeframe returned non-dict for {symbol}: {type(truth_metrics)}")
                    continue
                truth_metrics['symbol'] = symbol
                truth_metrics['timeframe_name'] = timeframe
            
            # TODO: Get PFF return if available
            pff_return = None
            
            # Validate truth_metrics before computing dominance
            if not truth_metrics or not isinstance(truth_metrics, dict):
                skipped_no_metrics += 1
                if skipped_no_metrics <= 5:  # Log first 5 only
                    logger.warning(f"⚠️ Invalid truth_metrics for {symbol}: {type(truth_metrics)}")
                continue
            
            # Ensure symbol is in truth_metrics (double-check)
            if 'symbol' not in truth_metrics or not truth_metrics.get('symbol'):
                truth_metrics['symbol'] = symbol
                if processed_count < 3:  # Log first 3 only
                    logger.debug(f"🔧 Fixed missing symbol field for {symbol}")
            
            # Compute dominance score for this timeframe
            try:
                dominance_result = dominance_engine.compute_dominance_score_for_timeframe(
                    truth_metrics,
                    pff_return=pff_return
                )
                
                if dominance_result:
                    results[symbol] = dominance_result
                    processed_count += 1
                else:
                    skipped_no_metrics += 1
                    if skipped_no_metrics <= 5:  # Log first 5 only
                        logger.debug(f"Could not compute dominance score for {symbol} ({timeframe}) - dominance_result is None")
                        
            except Exception as e:
                logger.warning(f"Error computing dominance score for {symbol} ({timeframe}): {e}", exc_info=True)
                continue
                
        except Exception as e:
            logger.warning(f"Error processing {symbol} ({timeframe}): {e}", exc_info=True)
            continue
    
    logger.info(f"✅ Computed {timeframe} dominance scores for {len(results)} out of {len(symbols)} symbols")
    logger.info(f"   📊 Stats: processed={processed_count}, skipped_no_avg_adv={skipped_no_avg_adv}, skipped_no_timeframe={skipped_no_timeframe}, skipped_no_metrics={skipped_no_metrics}")
    
    # Log sample result to verify timeframe_name
    if results:
        sample_symbol = list(results.keys())[0]
        sample_result = results[sample_symbol]
        logger.info(f"📊 Sample result for {sample_symbol}: timeframe_name={sample_result.get('timeframe_name')}, score={sample_result.get('buyer_seller_score')}")
    
    return {
        "success": True,
        "count": len(results),
        "data": results,
        "timeframe": timeframe
    }


@router.get("/dominance-scores/{symbol}")
async def get_symbol_dominance_score(symbol: str):
    """
    Get Buyer-Seller Dominance score for a specific symbol.
    
    Args:
        symbol: Symbol name (e.g., "CIM PRB")
        
    Returns:
        Dominance score and sub-scores for the symbol
    """
    try:
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.buyer_seller_dominance_engine import get_buyer_seller_dominance_engine
        from app.market_data.static_data_store import get_static_store
        
        truth_engine = get_truth_ticks_engine()
        dominance_engine = get_buyer_seller_dominance_engine()
        static_store = get_static_store()
        
        if not truth_engine or not dominance_engine:
            raise HTTPException(
                status_code=503,
                detail="Engines not available"
            )
        
        # Get AVG_ADV
        avg_adv = 0.0
        if static_store:
            record = static_store.get_static_data(symbol)
            if record:
                avg_adv = float(record.get('AVG_ADV', 0) or 0)
        
        # Get Truth Ticks metrics
        truth_metrics = truth_engine.get_metrics(symbol, avg_adv)
        
        if not truth_metrics:
            raise HTTPException(
                status_code=404,
                detail=f"No Truth Ticks data available for {symbol}. Ensure worker is running and collecting ticks."
            )
        
        # TODO: Get PFF return if available
        pff_return = None
        
        # Compute dominance score
        dominance_result = dominance_engine.compute_dominance_score(
            truth_metrics,
            pff_return=pff_return
        )
        
        if not dominance_result:
            raise HTTPException(
                status_code=404,
                detail=f"Could not compute dominance score for {symbol}. Insufficient data."
            )
        
        return {
            "success": True,
            "symbol": symbol,
            "data": dominance_result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dominance score for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/result/all")
async def get_all_results():
    """
    Get Truth Ticks analysis results for all symbols.
    
    First tries to get from latest job result in Redis (worker stores results there),
    then falls back to TruthTicksEngine (if worker has populated it).
    
    Returns:
        Dict of {symbol: metrics} for all symbols with data
    """
    try:
        redis_client = get_redis_client()
        redis = redis_client.sync
        
        if not redis:
            logger.warning("⚠️ Redis client not available, falling back to TruthTicksEngine")
        else:
            # Test Redis connection
            try:
                redis.ping()
            except Exception as e:
                logger.error(f"❌ Redis connection test failed: {e}")
                redis = None
        
        # Try to get from latest job result in Redis first
        if redis:
            try:
                # Get all job result keys
                pattern = f"{JOB_RESULT_PREFIX}*"
                logger.debug(f"🔍 Searching Redis for keys matching pattern: {pattern}")
                result_keys = redis.keys(pattern)
                
                # Decode byte strings if needed
                if result_keys:
                    result_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in result_keys]
                    logger.info(f"📦 Found {len(result_keys)} job result keys in Redis: {result_keys[:5]}...")  # Log first 5
                
                if result_keys:
                    # Get the most recent job result by checking updated_at timestamps
                    latest_result = None
                    latest_key = None
                    latest_timestamp = None
                    
                    for key in result_keys:
                        try:
                            result_json = redis.get(key)
                            if result_json:
                                # Decode if bytes
                                if isinstance(result_json, bytes):
                                    result_json = result_json.decode('utf-8')
                                
                                result = json.loads(result_json)
                                # Check if it has data and is successful
                                if result.get('success') and result.get('data') and len(result.get('data', {})) > 0:
                                    updated_at = result.get('updated_at', '')
                                    # Compare timestamps to find latest (ISO format strings are comparable)
                                    if not latest_result or (updated_at and updated_at > (latest_timestamp or '')):
                                        latest_result = result
                                        latest_key = key
                                        latest_timestamp = updated_at or ''
                        except Exception as e:
                            logger.warning(f"⚠️ Error parsing Redis result {key}: {e}", exc_info=True)
                            continue
                    
                    if latest_result and latest_result.get('data') and len(latest_result.get('data', {})) > 0:
                        logger.info(f"✅ Got results from Redis cache: {latest_key}, {len(latest_result.get('data', {}))} symbols, updated_at: {latest_result.get('updated_at', 'N/A')}")
                        return {
                            "success": True,
                            "count": latest_result.get('processed_count', len(latest_result.get('data', {}))),
                            "data": latest_result.get('data', {}),
                            "job_id": latest_result.get('job_id'),
                            "updated_at": latest_result.get('updated_at'),
                            "message": "Results from latest job cache"
                        }
                    else:
                        logger.warning(f"⚠️ Found {len(result_keys)} Redis keys but no valid results with data")
                else:
                    logger.debug(f"🔍 No Redis keys found matching pattern: {pattern}")
            except Exception as e:
                logger.error(f"❌ Error reading from Redis cache: {e}", exc_info=True)
        
        # Fallback: Try to get from TruthTicksEngine (if worker has populated it)
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        
        # Get all symbols
        symbols = truth_engine.get_all_symbols()
        
        if not symbols:
            return {
                "success": True,
                "count": 0,
                "data": {},
                "message": "No symbols with Truth Ticks data available. Worker may still be processing."
            }
        
        # Get metrics for each symbol
        results = {}
        for symbol in symbols:
            try:
                # Get AVG_ADV
                avg_adv = 0.0
                if static_store:
                    record = static_store.get_static_data(symbol)
                    if record:
                        avg_adv = float(record.get('AVG_ADV', 0) or 0)
                
                # Get metrics
                metrics = truth_engine.get_metrics(symbol, avg_adv)
                if metrics:
                    results[symbol] = metrics
            except Exception as e:
                logger.debug(f"Error getting metrics for {symbol}: {e}")
                continue
        
        return {
            "success": True,
            "count": len(results),
            "data": results
        }
    
    except Exception as e:
        logger.error(f"Error getting all Truth Ticks results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


