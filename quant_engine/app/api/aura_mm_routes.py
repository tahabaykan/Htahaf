"""
Aura MM API Routes

Endpoints for Market Making Screener & Scoring.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.logger import logger

router = APIRouter(prefix="/api/aura-mm", tags=["AuraMM"])


class AuraMMRequest(BaseModel):
    """Request model for Aura MM scoring"""
    symbols: Optional[List[str]] = None  # If None, process all symbols
    mode: str = "MARKET_CLOSED"  # MARKET_CLOSED or MARKET_LIVE
    bid: Optional[float] = None  # Required for MARKET_LIVE
    ask: Optional[float] = None  # Required for MARKET_LIVE
    spread: Optional[float] = None  # Required for MARKET_LIVE


@router.get("/scores")
async def get_aura_mm_scores(
    mode: str = Query("MARKET_CLOSED", description="MARKET_CLOSED, MARKET_LIVE, or MARKET_CLOSED_BIAS"),
    symbols: Optional[str] = Query(None, description="Comma-separated list of symbols")
):
    """
    Get Aura MM scores for all symbols or specified symbols.
    
    Args:
        mode: MARKET_CLOSED or MARKET_LIVE
        symbols: Comma-separated list of symbols (optional)
        
    Returns:
        Dict of {symbol: mm_score_data}
    """
    try:
        from app.market_data.aura_mm_engine import AuraMMEngine
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        
        mm_engine = AuraMMEngine()
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        
        # Parse symbols
        symbol_list = None
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(",")]
        
        # Get all symbols - try Redis first (where worker stores results), then tick_store, then static_store
        all_symbols = set()
        
        # Try Redis first (same as Truth Ticks API)
        try:
            from app.core.redis_client import get_redis_client
            redis_client = get_redis_client()
            redis = redis_client.sync if redis_client else None
            
            if redis:
                try:
                    redis.ping()
                    # Get latest job result from Redis
                    JOB_RESULT_PREFIX = "truth_ticks:"
                    pattern = f"{JOB_RESULT_PREFIX}*"
                    result_keys = redis.keys(pattern)
                    
                    if result_keys:
                        result_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in result_keys]
                        # Filter out inspect keys
                        result_keys = [k for k in result_keys if not k.endswith(':inspect:') and ':inspect:' not in k]
                        
                        # Get the most recent job result
                        latest_result = None
                        latest_timestamp = None
                        
                        for key in result_keys:
                            try:
                                result_json = redis.get(key)
                                if result_json:
                                    import json
                                    result_data = json.loads(result_json)
                                    if result_data.get('data'):
                                        # Get symbols from result data
                                        all_symbols.update(result_data['data'].keys())
                                        if not latest_result or (result_data.get('updated_at') and 
                                                               (not latest_timestamp or result_data['updated_at'] > latest_timestamp)):
                                            latest_result = result_data
                                            latest_timestamp = result_data.get('updated_at')
                            except Exception as e:
                                logger.debug(f"Error reading Redis key {key}: {e}")
                                continue
                except Exception as e:
                    logger.debug(f"Redis error: {e}")
        except Exception as e:
            logger.debug(f"Redis client error: {e}")
        
        # Fallback to tick_store
        if not all_symbols:
            all_symbols = set(truth_engine.get_all_symbols())
            logger.debug(f"Using tick_store symbols: {len(all_symbols)} symbols")
        
        # Always use static_store as primary source (MM engine needs AVG_ADV anyway)
        # This ensures we have all symbols with AVG_ADV data
        if static_store:
            try:
                all_static_symbols = static_store.get_all_symbols()
                if all_static_symbols:
                    if not all_symbols:
                        all_symbols = set(all_static_symbols)
                        logger.info(f"Using static_store symbols: {len(all_symbols)} symbols")
                    else:
                        # Merge with existing symbols (prioritize Redis/tick_store symbols)
                        all_symbols.update(all_static_symbols)
                        logger.info(f"Merged static_store symbols: {len(all_symbols)} total symbols")
            except Exception as e:
                logger.debug(f"Error getting symbols from static_store: {e}")
        
        # Convert to list
        all_symbols = list(all_symbols)
        
        if symbol_list:
            # Filter to requested symbols
            symbols_to_process = [s for s in symbol_list if s in all_symbols]
        else:
            symbols_to_process = all_symbols
        
        logger.info(f"📊 Found {len(all_symbols)} total symbols, processing {len(symbols_to_process)} symbols")
        
        if not symbols_to_process:
            return {
                "success": True,
                "count": 0,
                "data": {},
                "message": "No symbols to process"
            }
        
        # Get MM scores for each symbol
        results = {}
        processed_count = 0
        skipped_no_avg_adv = 0
        skipped_no_metrics = 0
        skipped_no_ticks = 0
        error_count = 0
        
        logger.info(f"🔄 Starting Aura MM score computation for {len(symbols_to_process)} symbols (mode={mode})")
        
        # OPTIMIZATION: Get all metrics from Redis in one go (not per symbol)
        all_redis_metrics = {}
        try:
            from app.core.redis_client import get_redis_client
            import json
            redis_client = get_redis_client()
            redis = redis_client.sync if redis_client else None
            
            if redis:
                try:
                    redis.ping()
                    # Get latest job result from Redis (ONCE, not per symbol)
                    JOB_RESULT_PREFIX = "truth_ticks:"
                    pattern = f"{JOB_RESULT_PREFIX}*"
                    result_keys = redis.keys(pattern)
                    
                    if result_keys:
                        result_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in result_keys]
                        result_keys = [k for k in result_keys if not k.endswith(':inspect:') and ':inspect:' not in k]
                        
                        # Get the most recent job result
                        latest_result = None
                        latest_timestamp = None
                        
                        for key in result_keys:
                            try:
                                result_json = redis.get(key)
                                if result_json:
                                    if isinstance(result_json, bytes):
                                        result_json = result_json.decode('utf-8')
                                    result_data = json.loads(result_json)
                                    if result_data.get('data'):
                                        if not latest_result or (result_data.get('updated_at') and 
                                                               (not latest_timestamp or result_data['updated_at'] > latest_timestamp)):
                                            latest_result = result_data
                                            latest_timestamp = result_data.get('updated_at')
                            except Exception as e:
                                continue
                        
                        if latest_result and latest_result.get('data'):
                            all_redis_metrics = latest_result['data']
                            logger.info(f"✅ Loaded {len(all_redis_metrics)} symbols from Redis cache")
                except Exception as e:
                    logger.debug(f"Redis error: {e}")
        except Exception as e:
            logger.debug(f"Redis client error: {e}")
        
        # OPTIMIZATION: Only process symbols that have data in Redis
        # This avoids processing 440 symbols when only ~400 have data
        symbols_with_data = []
        if all_redis_metrics:
            symbols_with_data = [s for s in symbols_to_process if s in all_redis_metrics]
            logger.info(f"📊 Filtering: {len(symbols_with_data)} symbols have Redis data out of {len(symbols_to_process)} total")
        else:
            symbols_with_data = symbols_to_process
            logger.warning(f"⚠️ No Redis data found, will try to compute from tick_store (slow)")
        
        # Process symbols with progress tracking
        total_symbols = len(symbols_with_data)
        for idx, symbol in enumerate(symbols_with_data):
            # Progress log every 50 symbols
            if (idx + 1) % 50 == 0:
                logger.info(f"📊 Progress: {idx + 1}/{total_symbols} symbols processed, {processed_count} with valid scores")
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
                
                # Get timeframe metrics - use pre-loaded Redis data (FAST)
                timeframe_metrics = {}
                
                # Get from pre-loaded Redis metrics (already loaded above)
                metrics_from_redis = None
                if symbol in all_redis_metrics:
                    symbol_data = all_redis_metrics[symbol]
                    if isinstance(symbol_data, dict) and 'TF_4H' in symbol_data:
                        metrics_from_redis = symbol_data
                
                # Use Redis metrics if available, otherwise compute from engine
                if metrics_from_redis:
                    # Use metrics from Redis (already computed by worker)
                    for timeframe_name in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']:
                        if timeframe_name in metrics_from_redis:
                            metrics = metrics_from_redis[timeframe_name]
                            # Ensure truth_ticks is present (should already be there from compute_metrics_for_timeframe)
                            if metrics and 'truth_ticks' not in metrics:
                                # Try to get from tick_store as fallback
                                with truth_engine._tick_lock:
                                    if symbol in truth_engine.tick_store:
                                        all_ticks = list(truth_engine.tick_store[symbol])
                                        truth_ticks_all = truth_engine.filter_truth_ticks(all_ticks)
                                        timeframe_start = truth_engine.get_timeframe_start_trading_hours(timeframe_name)
                                        truth_ticks_timeframe = [
                                            tick for tick in truth_ticks_all
                                            if tick.get('ts', 0) >= timeframe_start
                                        ]
                                        metrics['truth_ticks'] = truth_ticks_timeframe
                            
                            if metrics:
                                timeframe_metrics[timeframe_name] = metrics
                else:
                    # Fallback: compute from engine (tick_store)
                    for timeframe_name in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']:
                        metrics = truth_engine.compute_metrics_for_timeframe(
                            symbol=symbol,
                            avg_adv=avg_adv,
                            timeframe_name=timeframe_name
                        )
                        
                        # Get truth ticks for this timeframe (even if metrics is None)
                        truth_ticks_timeframe = []
                        with truth_engine._tick_lock:
                            if symbol in truth_engine.tick_store:
                                all_ticks = list(truth_engine.tick_store[symbol])
                                truth_ticks_all = truth_engine.filter_truth_ticks(all_ticks)
                                
                                # Filter to timeframe
                                timeframe_start = truth_engine.get_timeframe_start_trading_hours(timeframe_name)
                                truth_ticks_timeframe = [
                                    tick for tick in truth_ticks_all
                                    if tick.get('ts', 0) >= timeframe_start
                                ]
                        
                        if metrics:
                            # metrics already contains 'truth_ticks' (added by compute_metrics_for_timeframe)
                            if 'truth_ticks' not in metrics:
                                metrics['truth_ticks'] = truth_ticks_timeframe
                            timeframe_metrics[timeframe_name] = metrics
                        elif truth_ticks_timeframe:
                            # Metrics is None but we have ticks - create minimal metrics dict
                            timeframe_metrics[timeframe_name] = {
                                'truth_ticks': truth_ticks_timeframe,
                                'truth_tick_count': len(truth_ticks_timeframe),
                                'truth_volume': sum(tick.get('size', 0) for tick in truth_ticks_timeframe),
                                'truth_vwap': None,
                                'volav_levels': [],
                                'volav1_start': None,
                                'volav1_end': None,
                                'min_volav_gap_used': truth_engine.min_volav_gap(avg_adv) if avg_adv > 0 else 0.05
                            }
                
                if not timeframe_metrics:
                    skipped_no_metrics += 1
                    if processed_count < 5:  # Log first 5 for debugging
                        logger.debug(f"[{symbol}] No timeframe_metrics available (all timeframes returned None)")
                    continue
                
                # Debug: Check if truth_ticks are present
                has_truth_ticks = any(
                    tf_metrics.get('truth_ticks') and len(tf_metrics.get('truth_ticks', [])) > 0
                    for tf_metrics in timeframe_metrics.values()
                )
                
                # Count ticks per timeframe for debugging
                ticks_per_tf = {
                    tf: len(tf_metrics.get('truth_ticks', []))
                    for tf, tf_metrics in timeframe_metrics.items()
                }
                
                if not has_truth_ticks:
                    skipped_no_ticks += 1
                    if processed_count < 5:  # Log first 5 for debugging
                        logger.debug(f"[{symbol}] No truth_ticks in any timeframe_metrics - ticks_per_tf={ticks_per_tf}")
                    continue
                
                # Log first few successful cases
                if processed_count < 3:
                    logger.info(f"✅ [{symbol}] Computing MM score - ticks_per_tf={ticks_per_tf}, avg_adv={avg_adv:.0f}")
                
                # Compute MM score
                # Get PFF benchmark data for progressive shock quoting
                pff_change_now = None
                pff_delta_5m = None
                prev_close = None
                last_truth_price = None
                
                if mode == 'MARKET_LIVE':
                    # Get PFF data from ETF market data
                    try:
                        from app.api.market_data_routes import etf_market_data
                        pff_data = etf_market_data.get('PFF', {})
                        if pff_data:
                            pff_last = pff_data.get('last')
                            pff_prev_close = pff_data.get('prev_close')
                            if pff_last is not None and pff_prev_close is not None and pff_prev_close > 0:
                                pff_change_now = pff_last - pff_prev_close
                                # TODO: Calculate pff_delta_5m from historical data
                                # For now, use pff_change_now as approximation
                                pff_delta_5m = pff_change_now
                    except Exception as e:
                        logger.debug(f"Could not get PFF data for {symbol}: {e}")
                    
                    # Get symbol's prev_close and last truth price
                    try:
                        from app.api.market_data_routes import market_data_cache
                        symbol_data = market_data_cache.get(symbol, {})
                        prev_close = symbol_data.get('prev_close')
                        
                        # Get last truth price from timeframe metrics
                        if timeframe_metrics:
                            # Use TF_4H for most recent price
                            tf_4h_metrics = timeframe_metrics.get('TF_4H', {})
                            truth_ticks = tf_4h_metrics.get('truth_ticks', [])
                            if truth_ticks:
                                last_truth_price = truth_ticks[-1].get('price') if truth_ticks else None
                    except Exception as e:
                        logger.debug(f"Could not get prev_close/last_truth_price for {symbol}: {e}")
                
                mm_result = mm_engine.compute_mm_score(
                    symbol=symbol,
                    timeframe_metrics=timeframe_metrics,
                    avg_adv=avg_adv,
                    mode=mode,
                    pff_change_now=pff_change_now,
                    pff_delta_5m=pff_delta_5m,
                    prev_close=prev_close,
                    last_truth_price=last_truth_price
                )
                
                if mm_result and 'error' not in mm_result:
                    # Always add to results (filtering happens later)
                    results[symbol] = mm_result
                    
                    # Check reasoning
                    mm_reasoning = mm_result.get('mm_reasoning', {})
                    is_included = mm_reasoning.get('included', False)
                    
                    # Count processed symbols
                    if mode in ['MARKET_CLOSED', 'MARKET_LIVE']:
                        if is_included:
                            processed_count += 1
                    elif mode == 'MARKET_CLOSED_BIAS':
                        # Bias mode: count all (included or not)
                        processed_count += 1
                else:
                    error_count += 1
                    error_msg = mm_result.get('error', 'Unknown error') if mm_result else 'No result'
                    if error_count <= 3:  # Log first 3 errors
                        logger.debug(f"[{symbol}] MM score computation failed: {error_msg}")
                    
            except Exception as e:
                error_count += 1
                if error_count <= 3:  # Log first 3 exceptions
                    logger.warning(f"Error computing MM score for {symbol}: {e}", exc_info=True)
                continue
        
        # Filter results based on mode
        if mode in ['MARKET_CLOSED', 'MARKET_LIVE']:
            # Tradeable MM: Only include symbols with included=True
            filtered_results = {
                symbol: data for symbol, data in results.items()
                if data.get('mm_reasoning', {}).get('included', False)
            }
        else:
            # Bias MM: Include all with reasoning
            filtered_results = results
        
        # Sort by MM score (descending)
        sorted_results = dict(sorted(
            filtered_results.items(),
            key=lambda x: x[1].get('mm_score', 0),
            reverse=True
        ))
        
        # Count included vs excluded
        included_count = sum(1 for d in filtered_results.values() if d.get('mm_reasoning', {}).get('included', False))
        excluded_count = len(results) - included_count
        
        logger.info(f"✅ Aura MM scores computed: {len(sorted_results)} symbols shown ({included_count} included, {excluded_count} excluded)")
        logger.info(f"📊 Stats: processed={processed_count}, skipped_no_avg_adv={skipped_no_avg_adv}, skipped_no_metrics={skipped_no_metrics}, skipped_no_ticks={skipped_no_ticks}, errors={error_count}")
        
        if len(sorted_results) == 0:
            logger.warning(f"⚠️ No MM scores computed. Stats: processed={processed_count}, skipped_no_avg_adv={skipped_no_avg_adv}, skipped_no_metrics={skipped_no_metrics}, skipped_no_ticks={skipped_no_ticks}, errors={error_count}")
        
        return {
            "success": True,
            "count": len(sorted_results),
            "mode": mode,
            "included_count": included_count,
            "excluded_count": excluded_count,
            "data": sorted_results
        }
        
    except Exception as e:
        logger.error(f"Error getting Aura MM scores: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/score/{symbol}")
async def get_symbol_mm_score(
    symbol: str,
    mode: str = Query("MARKET_CLOSED", description="MARKET_CLOSED or MARKET_LIVE"),
    bid: Optional[float] = Query(None),
    ask: Optional[float] = Query(None),
    spread: Optional[float] = Query(None)
):
    """
    Get Aura MM score for a specific symbol.
    
    Args:
        symbol: Symbol name
        mode: MARKET_CLOSED or MARKET_LIVE
        bid: Current bid (for MARKET_LIVE)
        ask: Current ask (for MARKET_LIVE)
        spread: Current spread (for MARKET_LIVE)
        
    Returns:
        MM score data for the symbol
    """
    try:
        from app.market_data.aura_mm_engine import AuraMMEngine
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        
        mm_engine = AuraMMEngine()
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        
        # Get AVG_ADV
        avg_adv = 0.0
        if static_store:
            record = static_store.get_static_data(symbol)
            if record:
                avg_adv = float(record.get('AVG_ADV', 0) or 0)
        
        if avg_adv <= 0:
            raise HTTPException(
                status_code=404,
                detail=f"No AVG_ADV data for {symbol}"
            )
        
        # Get timeframe metrics
        timeframe_metrics = {}
        
        for timeframe_name in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']:
            metrics = truth_engine.compute_metrics_for_timeframe(
                symbol=symbol,
                avg_adv=avg_adv,
                timeframe_name=timeframe_name
            )
            
            if metrics:
                # Get truth ticks for this timeframe
                with truth_engine._tick_lock:
                    if symbol in truth_engine.tick_store:
                        all_ticks = list(truth_engine.tick_store[symbol])
                        truth_ticks_all = truth_engine.filter_truth_ticks(all_ticks)
                        
                        # Filter to timeframe
                        timeframe_start = truth_engine.get_timeframe_start_trading_hours(timeframe_name)
                        truth_ticks_timeframe = [
                            tick for tick in truth_ticks_all
                            if tick.get('ts', 0) >= timeframe_start
                        ]
                        
                        # Add truth_ticks to metrics
                        metrics['truth_ticks'] = truth_ticks_timeframe
                
                timeframe_metrics[timeframe_name] = metrics
        
        if not timeframe_metrics:
            raise HTTPException(
                status_code=404,
                detail=f"No Truth Ticks data available for {symbol}"
            )
        
        # Compute MM score
        mm_result = mm_engine.compute_mm_score(
            symbol=symbol,
            timeframe_metrics=timeframe_metrics,
            avg_adv=avg_adv,
            bid=bid,
            ask=ask,
            spread=spread,
            mode=mode
        )
        
        if not mm_result or 'error' in mm_result:
            raise HTTPException(
                status_code=500,
                detail=mm_result.get('error', 'Unknown error computing MM score')
            )
        
        return {
            "success": True,
            "symbol": symbol,
            "data": mm_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting MM score for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

