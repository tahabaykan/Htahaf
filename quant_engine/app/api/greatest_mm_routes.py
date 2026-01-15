"""
Greatest MM Quant API Routes
============================

API endpoints for Greatest MM Quant scoring system.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from datetime import datetime

from app.core.logger import logger
from app.mm.greatest_mm_engine import get_greatest_mm_engine, GreatestMMEngine
from app.mm.greatest_mm_models import (
    MMScenarioType, MMScenario, MMAnalysis, MMWatchlistItem, GreatestMMResponse
)


router = APIRouter(prefix="/api/greatest-mm", tags=["GreatestMM"])


@router.get("/analysis")
async def get_greatest_mm_analysis(
    symbols: Optional[str] = Query(None, description="Comma-separated symbols (empty=all)"),
    group: Optional[str] = Query(None, description="Filter by DOS group"),
    threshold: float = Query(30.0, description="MM score threshold")
):
    """
    Get Greatest MM analysis for symbols.
    
    Returns 4-scenario MM Long/Short scores with entry recommendations.
    """
    try:
        engine = get_greatest_mm_engine()
        
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        from app.core.data_fabric import get_data_fabric
        from app.market_data.pricing_overlay_engine import get_pricing_overlay_engine
        
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        data_fabric = get_data_fabric()
        pricing_engine = get_pricing_overlay_engine()
        
        if not static_store or not static_store.loaded:
            return GreatestMMResponse(
                success=False,
                error='Static data not loaded'
            ).model_dump()
        
        # Get symbol list
        if symbols:
            symbol_list = [s.strip().upper() for s in symbols.split(',')]
        elif group:
            all_symbols = static_store.get_all_symbols()
            symbol_list = []
            for s in all_symbols:
                sd = static_store.get_static_data(s)
                if sd and sd.get('GROUP', sd.get('DOS_GRUP', '')) == group:
                    symbol_list.append(s)
        else:
            symbol_list = static_store.get_all_symbols()
        
        # =========================================================================
        # LOAD TRUTH TICKS FROM REDIS
        # =========================================================================
        all_redis_metrics = {}
        try:
            from app.core.redis_client import get_redis_client
            import json
            redis_client = get_redis_client()
            redis = redis_client.sync if redis_client else None
            
            if redis:
                try:
                    redis.ping()
                    JOB_RESULT_PREFIX = "truth_ticks:"
                    pattern = f"{JOB_RESULT_PREFIX}*"
                    result_keys = redis.keys(pattern)
                    
                    if result_keys:
                        result_keys = [k.decode('utf-8') if isinstance(k, bytes) else k for k in result_keys]
                        result_keys = [k for k in result_keys if ':inspect:' not in k]
                        
                        for key in result_keys:
                            try:
                                result_json = redis.get(key)
                                if result_json:
                                    if isinstance(result_json, bytes):
                                        result_json = result_json.decode('utf-8')
                                    result_data = json.loads(result_json)
                                    if result_data.get('data'):
                                        all_redis_metrics = result_data['data']
                                        break
                            except:
                                continue
                except:
                    pass
        except:
            pass
        
        analyses = []
        actionable_count = 0
        
        for symbol in symbol_list:
            static_data = static_store.get_static_data(symbol) or {}
            prev_close = static_data.get('prev_close', 0)
            
            # Get L1 data (bid, ask, last)
            bid, ask, last_price = None, None, None
            if data_fabric:
                live_data = data_fabric.get_live(symbol)
                if live_data:
                    bid = live_data.get('bid')
                    ask = live_data.get('ask')
                    last_price = live_data.get('last')  # Last trade price from Hammer
            
            if not bid or not ask or bid <= 0 or ask <= 0:
                continue
            
            # Get benchmark_chg from pricing overlay
            benchmark_chg = 0.0
            if pricing_engine:
                overlay = pricing_engine.get_overlay_scores(symbol)
                if overlay and overlay.get('benchmark_chg') is not None:
                    benchmark_chg = overlay['benchmark_chg']
            
            # Get ticks for Son5Tick calculation
            ticks = []
            if symbol in all_redis_metrics:
                redis_data = all_redis_metrics[symbol]
                if isinstance(redis_data, list):
                    ticks = redis_data
                elif isinstance(redis_data, dict):
                    for tf_name in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']:
                        if tf_name in redis_data and redis_data[tf_name]:
                            tf_data = redis_data[tf_name]
                            if isinstance(tf_data, dict):
                                tf_ticks = tf_data.get('truth_ticks', tf_data.get('ticks', []))
                                if tf_ticks:
                                    ticks.extend(tf_ticks)
                                    break
                            elif isinstance(tf_data, list):
                                ticks.extend(tf_data)
                                break
                    if not ticks:
                        ticks = redis_data.get('truth_ticks', redis_data.get('ticks', []))
            
            if not ticks and hasattr(truth_engine, 'tick_store'):
                with truth_engine._tick_lock:
                    if symbol in truth_engine.tick_store:
                        ticks = list(truth_engine.tick_store[symbol])
            
            # Calculate Son5Tick (mode of last 5 truth ticks)
            son5_tick = None
            new_print = None
            
            if ticks:
                # Filter truth ticks (100-200 lot from FINRA)
                truth_ticks = []
                for tick in ticks:
                    size = tick.get('size', tick.get('qty', 0))
                    venue = str(tick.get('exch', tick.get('venue', ''))).upper()
                    price = tick.get('price', 0)
                    
                    if price > 0 and size in [100, 200]:
                        truth_ticks.append(tick)
                
                if not truth_ticks:
                    truth_ticks = [t for t in ticks if t.get('price', 0) > 0]
                
                if truth_ticks:
                    # Sort by timestamp
                    sorted_ticks = sorted(
                        truth_ticks,
                        key=lambda t: t.get('ts', t.get('timestamp', 0)),
                        reverse=True
                    )
                    
                    # Son5Tick = mode of last 5
                    last5 = sorted_ticks[:5]
                    prices = [round(t.get('price', 0), 2) for t in last5 if t.get('price', 0) > 0]
                    
                    if prices:
                        from collections import Counter
                        price_counts = Counter(prices)
                        son5_tick = price_counts.most_common(1)[0][0]
                        
                        # New print = most recent
                        if len(sorted_ticks) > 0:
                            latest = sorted_ticks[0].get('price', 0)
                            if latest != son5_tick:
                                new_print = latest
            
            # Fallback: if son5_tick is None or 0, use live last price first
            if son5_tick is None or son5_tick <= 0:
                # Priority 1: Use last trade price from Hammer (most recent market price)
                if last_price and last_price > 0:
                    son5_tick = last_price
                # Priority 2: Use prev_close as fallback
                elif prev_close and prev_close > 0:
                    son5_tick = prev_close
                else:
                    # Last resort: use midpoint of bid/ask
                    son5_tick = (bid + ask) / 2.0
            
            # CRITICAL: Son5Tick must be within bid-ask range for calculations to make sense
            # If Son5Tick < Bid: price moved up, clamp to bid
            # If Son5Tick > Ask: price moved down, clamp to ask
            if son5_tick < bid:
                son5_tick = bid
            elif son5_tick > ask:
                son5_tick = ask
            
            # Analyze symbol
            analysis = engine.analyze_symbol(
                symbol=symbol,
                bid=bid,
                ask=ask,
                prev_close=prev_close if prev_close > 0 else bid,
                benchmark_chg=benchmark_chg,
                son5_tick=son5_tick,
                new_print=new_print
            )
            
            analysis.tick_count = len(ticks)
            analyses.append(analysis)
            
            if analysis.long_actionable or analysis.short_actionable:
                actionable_count += 1
        
        # Sort by actionability and score
        analyses.sort(
            key=lambda a: (
                not (a.long_actionable or a.short_actionable),
                -(a.best_long_score or 0) - (a.best_short_score or 0)
            )
        )
        
        logger.info(f"[GREATEST_MM] Analyzed {len(analyses)} symbols, {actionable_count} actionable")
        
        return GreatestMMResponse(
            success=True,
            symbol_count=len(analyses),
            actionable_count=actionable_count,
            analyses=analyses
        ).model_dump()
        
    except Exception as e:
        logger.error(f"[GREATEST_MM] Analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/watchlist")
async def get_watchlist():
    """Get current Greatest MM watchlist"""
    try:
        engine = get_greatest_mm_engine()
        watchlist = engine.get_watchlist()
        
        return {
            'success': True,
            'count': len(watchlist),
            'items': [item.model_dump() for item in watchlist]
        }
        
    except Exception as e:
        logger.error(f"[GREATEST_MM] Watchlist error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/track/{symbol}")
async def track_symbol(symbol: str):
    """Add symbol to watchlist"""
    try:
        engine = get_greatest_mm_engine()
        
        # Get initial Son5Tick
        from app.market_data.static_data_store import get_static_store
        from app.core.data_fabric import get_data_fabric
        
        static_store = get_static_store()
        data_fabric = get_data_fabric()
        
        if data_fabric:
            live = data_fabric.get_live(symbol)
            if live and live.get('bid'):
                son5_tick = live.get('last', live.get('bid'))
                engine.add_to_watchlist(symbol.upper(), son5_tick)
                return {'success': True, 'message': f'{symbol} added to watchlist'}
        
        return {'success': False, 'error': 'No market data available'}
        
    except Exception as e:
        logger.error(f"[GREATEST_MM] Track error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/track/{symbol}")
async def untrack_symbol(symbol: str):
    """Remove symbol from watchlist"""
    try:
        engine = get_greatest_mm_engine()
        success = engine.remove_from_watchlist(symbol.upper())
        
        return {
            'success': success,
            'message': f'{symbol} removed from watchlist' if success else f'{symbol} not in watchlist'
        }
        
    except Exception as e:
        logger.error(f"[GREATEST_MM] Untrack error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
