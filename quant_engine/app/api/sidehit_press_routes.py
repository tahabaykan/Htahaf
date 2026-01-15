"""
Sidehit Press API Routes
========================

API endpoints for Sidehit Press Engine.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional
from datetime import datetime

from app.core.logger import logger
from app.mm.sidehit_press_engine import get_sidehit_press_engine, SidehitPressEngine
from app.mm.sidehit_press_models import (
    EngineMode, SidehitPressMode, SignalType, GroupStatus,
    SymbolAnalysis, GroupSummary, SidehitPressResponse, TimeframeDrift
)

router = APIRouter(prefix="/api/sidehit", tags=["SidehitPress"])


@router.get("/analysis")
async def get_sidehit_analysis(
    symbols: Optional[str] = Query(None, description="Comma-separated symbols (empty=all)"),
    group: Optional[str] = Query(None, description="Filter by DOS group"),
    limit: int = Query(0, description="Max symbols to return (0=unlimited)")
):
    """
    Get Sidehit Press analysis in ANALYSIS_ONLY mode.
    
    This works even when market is closed (no L1 required).
    Returns VOLAV, DRIFT, and GROUP-RELATIVE analysis.
    """
    try:
        engine = get_sidehit_press_engine()
        
        # Get truth ticks from GLOBAL engine (not new instance!)
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        
        if not static_store or not static_store.loaded:
            return {
                'success': False,
                'error': 'Static data not loaded',
                'mode': EngineMode.ANALYSIS_ONLY.value
            }
        
        # Get symbols to analyze
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(',')]
        else:
            all_symbols = static_store.get_all_symbols()
            symbol_list = all_symbols if limit == 0 else all_symbols[:limit]
        
        # Filter by group if specified
        if group:
            symbol_list = [
                s for s in symbol_list
                if static_store.get_static_data(s).get('DOS_GRUP') == group or
                   static_store.get_static_data(s).get('GROUP') == group
            ]
        
        # Group symbols by DOS_GRUP for group analysis
        groups_data: dict = {}
        for symbol in symbol_list:
            static_data = static_store.get_static_data(symbol) or {}
            group_id = engine.resolve_group(symbol, static_data)
            
            if group_id not in groups_data:
                groups_data[group_id] = []
            groups_data[group_id].append(symbol)
        
        # =========================================================================
        # LOAD TRUTH TICKS FROM REDIS (same as Aura MM)
        # This enables weekend analysis with cached data from last trading day
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
                        result_keys = [k for k in result_keys if not k.endswith(':inspect:') and ':inspect:' not in k]
                        
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
                            logger.info(f"[SIDEHIT] ✅ Loaded {len(all_redis_metrics)} symbols from Redis cache (last update: {latest_timestamp})")
                except Exception as e:
                    logger.warning(f"[SIDEHIT] Redis error: {e}")
        except Exception as e:
            logger.warning(f"[SIDEHIT] Redis client error: {e}")
        
        # First pass: compute drifts for all symbols
        symbol_drifts = {}
        symbol_static = {}
        symbol_ticks = {}
        symbols_with_data = 0
        symbols_no_data = 0
        
        for symbol in symbol_list:
            static_data = static_store.get_static_data(symbol) or {}
            symbol_static[symbol] = static_data
            avg_adv = static_data.get('AVG_ADV', 0)
            
            # Try to get truth ticks from Redis first (cached data)
            ticks = []
            
            # 1) Try Redis cache (for weekend/market closed)
            if symbol in all_redis_metrics:
                redis_data = all_redis_metrics[symbol]
                
                # Check if redis_data is a list of ticks directly
                if isinstance(redis_data, list):
                    ticks = redis_data
                # Check if redis_data is a dict with timeframe structure
                elif isinstance(redis_data, dict):
                    # Try to get truth_ticks from timeframe data
                    for tf_name in ['TF_4H', 'TF_1D', 'TF_2D']:
                        if tf_name in redis_data and redis_data[tf_name]:
                            tf_data = redis_data[tf_name]
                            # Try different possible field names
                            if isinstance(tf_data, dict):
                                tf_ticks = tf_data.get('truth_ticks', tf_data.get('ticks', []))
                                if tf_ticks:
                                    ticks.extend(tf_ticks)
                                    break
                            elif isinstance(tf_data, list):
                                ticks.extend(tf_data)
                                break
                    
                    # Also check for 'ticks' or 'truth_ticks' at root level
                    if not ticks:
                        ticks = redis_data.get('truth_ticks', redis_data.get('ticks', []))
            
            # 2) Fallback: try tick_store (live data)
            if not ticks and hasattr(truth_engine, 'tick_store'):
                with truth_engine._tick_lock:
                    if symbol in truth_engine.tick_store:
                        ticks = list(truth_engine.tick_store[symbol])
            
            symbol_ticks[symbol] = ticks
            
            # Compute VOLAV for drift calculation
            if ticks:
                symbols_with_data += 1
                anchor_ts = max(t.get('ts', 0) for t in ticks)
                
                volav_15m = engine.compute_volav(ticks, 900, anchor_ts, avg_adv)
                volav_1h = engine.compute_volav(ticks, 3600, anchor_ts, avg_adv)
                volav_4h = engine.compute_volav(ticks, 14400, anchor_ts, avg_adv)
                volav_1d = engine.compute_volav(ticks, 86400, anchor_ts, avg_adv)
                
                drift = engine.compute_drift(volav_15m, volav_1h, volav_4h, volav_1d)
                symbol_drifts[symbol] = drift
            else:
                symbols_no_data += 1
                symbol_drifts[symbol] = TimeframeDrift()
        
        logger.info(f"[SIDEHIT] Data summary: {symbols_with_data} symbols with ticks, {symbols_no_data} without")
        
        # Group drifts
        group_drifts = {}
        for group_id, group_symbols in groups_data.items():
            group_drifts[group_id] = [
                symbol_drifts[s] for s in group_symbols
                if s in symbol_drifts
            ]

        
        # Second pass: full analysis with group context
        analyses = []
        for symbol in symbol_list:
            static_data = symbol_static.get(symbol, {})
            ticks = symbol_ticks.get(symbol, [])
            group_id = engine.resolve_group(symbol, static_data)
            
            analysis = engine.analyze_symbol(
                symbol=symbol,
                ticks=ticks,
                static_data=static_data,
                mode=EngineMode.ANALYSIS_ONLY,
                group_symbols_drifts=group_drifts.get(group_id, [])
            )
            analyses.append(analysis)
        
        # Build group summaries
        group_summaries = []
        for group_id, group_symbols in groups_data.items():
            summary = GroupSummary(
                group_id=group_id,
                symbol_count=len(group_symbols)
            )
            
            # Compute median drifts
            group_drift_list = group_drifts.get(group_id, [])
            drifts_15_60 = [d.drift_15_60 for d in group_drift_list if d.drift_15_60 is not None]
            drifts_60_240 = [d.drift_60_240 for d in group_drift_list if d.drift_60_240 is not None]
            drifts_240_1d = [d.drift_240_1d for d in group_drift_list if d.drift_240_1d is not None]
            
            if drifts_15_60:
                import statistics
                summary.median_drift_15_60 = round(statistics.median(drifts_15_60), 4)
            if drifts_60_240:
                import statistics
                summary.median_drift_60_240 = round(statistics.median(drifts_60_240), 4)
            if drifts_240_1d:
                import statistics
                summary.median_drift_240_1d = round(statistics.median(drifts_240_1d), 4)
            
            # Collect group analyses for averaging
            group_analyses = [a for a in analyses if a.group and a.group.group_id == group_id]
            
            # Compute average VOLAVs
            volav_15m_list = [a.volav_15m.volav_price for a in group_analyses if a.volav_15m and a.volav_15m.volav_price]
            volav_1h_list = [a.volav_1h.volav_price for a in group_analyses if a.volav_1h and a.volav_1h.volav_price]
            volav_4h_list = [a.volav_4h.volav_price for a in group_analyses if a.volav_4h and a.volav_4h.volav_price]
            volav_1d_list = [a.volav_1d.volav_price for a in group_analyses if a.volav_1d and a.volav_1d.volav_price]
            
            if volav_15m_list:
                summary.avg_volav_15m = round(sum(volav_15m_list) / len(volav_15m_list), 4)
            if volav_1h_list:
                summary.avg_volav_1h = round(sum(volav_1h_list) / len(volav_1h_list), 4)
            if volav_4h_list:
                summary.avg_volav_4h = round(sum(volav_4h_list) / len(volav_4h_list), 4)
            if volav_1d_list:
                summary.avg_volav_1d = round(sum(volav_1d_list) / len(volav_1d_list), 4)
            
            # Compute average last5 tick values
            last5_tick_list = [a.last5_tick_avg for a in group_analyses if a.last5_tick_avg is not None]
            last5_vs_15m_list = [a.last5_vs_15m for a in group_analyses if a.last5_vs_15m is not None]
            last5_vs_1h_list = [a.last5_vs_1h for a in group_analyses if a.last5_vs_1h is not None]
            
            if last5_tick_list:
                summary.avg_last5_tick = round(sum(last5_tick_list) / len(last5_tick_list), 4)
            if last5_vs_15m_list:
                summary.avg_last5_vs_15m = round(sum(last5_vs_15m_list) / len(last5_vs_15m_list), 4)
            if last5_vs_1h_list:
                summary.avg_last5_vs_1h = round(sum(last5_vs_1h_list) / len(last5_vs_1h_list), 4)
            
            # Categorize symbols
            for analysis in group_analyses:
                if analysis.group.status_15_60 == GroupStatus.OVERPERFORM_GROUP:
                    summary.overperform_symbols.append(analysis.symbol)
                elif analysis.group.status_15_60 == GroupStatus.UNDERPERFORM_GROUP:
                    summary.underperform_symbols.append(analysis.symbol)
                else:
                    summary.inline_symbols.append(analysis.symbol)
            
            group_summaries.append(summary)
        
        # Sort analyses by strongest deviation
        def sort_key(a):
            if a.group and a.group.rel_drift_15_60 is not None:
                return abs(a.group.rel_drift_15_60)
            return 0
        
        analyses.sort(key=sort_key, reverse=True)
        
        logger.info(f"[SIDEHIT] Analysis complete: {len(analyses)} symbols, {len(group_summaries)} groups")
        
        return {
            'success': True,
            'mode': EngineMode.ANALYSIS_ONLY.value,
            'timestamp': datetime.now().isoformat(),
            'symbol_count': len(analyses),
            'group_count': len(group_summaries),
            'symbols': [a.model_dump() for a in analyses],
            'groups': [g.model_dump() for g in group_summaries]
        }
        
    except Exception as e:
        logger.error(f"[SIDEHIT] Analysis error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scores")
async def get_sidehit_scores(
    symbols: Optional[str] = Query(None, description="Comma-separated symbols"),
    sidehit_mode: str = Query("PASSIVE", description="PASSIVE or ACTIVE"),
    limit: int = Query(50, description="Max symbols to return")
):
    """
    Get Sidehit Press scores in EXECUTION mode.
    
    Requires market to be open (L1 data needed).
    Returns MM_SCORE and BUY_FADE/SELL_FADE signals.
    """
    try:
        engine = get_sidehit_press_engine()
        
        # Parse sidehit mode
        if sidehit_mode.upper() == "ACTIVE":
            sh_mode = SidehitPressMode.ACTIVE
        else:
            sh_mode = SidehitPressMode.PASSIVE
        
        # Get data sources
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        from app.core.data_fabric import get_data_fabric
        
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        data_fabric = get_data_fabric()
        
        if not static_store or not static_store.loaded:
            return {
                'success': False,
                'error': 'Static data not loaded',
                'mode': EngineMode.EXECUTION.value
            }
        
        # Get symbols
        if symbols:
            symbol_list = [s.strip() for s in symbols.split(',')]
        else:
            symbol_list = static_store.get_all_symbols()[:limit]
        
        # Analyze each symbol
        analyses = []
        skipped_no_l1 = 0
        
        for symbol in symbol_list[:limit]:
            static_data = static_store.get_static_data(symbol) or {}
            
            # Get truth ticks
            ticks = []
            if hasattr(truth_engine, 'tick_store'):
                with truth_engine._tick_lock:
                    if symbol in truth_engine.tick_store:
                        ticks = list(truth_engine.tick_store[symbol])
            
            # Get L1 data
            bid, ask = None, None
            if data_fabric:
                live_data = data_fabric.get_live(symbol)
                if live_data:
                    bid = live_data.get('bid')
                    ask = live_data.get('ask')
            
            if bid is None or ask is None:
                skipped_no_l1 += 1
                continue
            
            # Get Fbtot/SFStot if ACTIVE mode
            fbtot, sfstot = None, None
            if sh_mode == SidehitPressMode.ACTIVE and data_fabric:
                derived = data_fabric.get_derived(symbol)
                if derived:
                    fbtot = derived.get('Fbtot')
                    sfstot = derived.get('SFStot')
            
            analysis = engine.analyze_symbol(
                symbol=symbol,
                ticks=ticks,
                static_data=static_data,
                mode=EngineMode.EXECUTION,
                bid=bid,
                ask=ask,
                fbtot=fbtot,
                sfstot=sfstot,
                sidehit_mode=sh_mode
            )
            analyses.append(analysis)
        
        # Sort by MM score (highest first)
        analyses.sort(key=lambda a: a.mm_score or 0, reverse=True)
        
        # Count signals
        buy_fade_count = sum(1 for a in analyses if a.signal_type == SignalType.BUY_FADE)
        sell_fade_count = sum(1 for a in analyses if a.signal_type == SignalType.SELL_FADE)
        watch_count = sum(1 for a in analyses if a.signal_type == SignalType.WATCH)
        
        logger.info(
            f"[SIDEHIT] Scores complete: {len(analyses)} analyzed, "
            f"{skipped_no_l1} skipped (no L1), "
            f"BUY_FADE={buy_fade_count}, SELL_FADE={sell_fade_count}, WATCH={watch_count}"
        )
        
        return {
            'success': True,
            'mode': EngineMode.EXECUTION.value,
            'sidehit_mode': sh_mode.value,
            'timestamp': datetime.now().isoformat(),
            'symbol_count': len(analyses),
            'skipped_no_l1': skipped_no_l1,
            'signal_summary': {
                'buy_fade': buy_fade_count,
                'sell_fade': sell_fade_count,
                'watch': watch_count
            },
            'symbols': [a.model_dump() for a in analyses]
        }
        
    except Exception as e:
        logger.error(f"[SIDEHIT] Scores error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/groups")
async def get_sidehit_groups():
    """
    Get group-level summary for Sidehit Press.
    
    Shows median drifts and over/underperform counts per group.
    """
    try:
        from app.market_data.static_data_store import get_static_store
        
        static_store = get_static_store()
        if not static_store or not static_store.loaded:
            return {
                'success': False,
                'error': 'Static data not loaded'
            }
        
        engine = get_sidehit_press_engine()
        
        # Group all symbols
        groups = {}
        for symbol in static_store.get_all_symbols():
            static_data = static_store.get_static_data(symbol) or {}
            group_id = engine.resolve_group(symbol, static_data)
            
            if group_id not in groups:
                groups[group_id] = []
            groups[group_id].append(symbol)
        
        # Build summaries
        summaries = []
        for group_id, symbols in groups.items():
            summaries.append({
                'group_id': group_id,
                'symbol_count': len(symbols),
                'symbols': symbols[:10],  # Preview only
                'has_more': len(symbols) > 10
            })
        
        # Sort by symbol count
        summaries.sort(key=lambda x: x['symbol_count'], reverse=True)
        
        return {
            'success': True,
            'group_count': len(summaries),
            'groups': summaries
        }
        
    except Exception as e:
        logger.error(f"[SIDEHIT] Groups error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbol/{symbol}")
async def get_sidehit_symbol_detail(
    symbol: str,
    mode: str = Query("ANALYSIS_ONLY", description="ANALYSIS_ONLY or EXECUTION")
):
    """
    Get detailed Sidehit Press analysis for a single symbol.
    """
    try:
        engine = get_sidehit_press_engine()
        
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        from app.core.data_fabric import get_data_fabric
        
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        data_fabric = get_data_fabric()
        
        static_data = static_store.get_static_data(symbol) if static_store else {}
        
        # Get truth ticks
        ticks = []
        if hasattr(truth_engine, 'tick_store'):
            with truth_engine._tick_lock:
                if symbol in truth_engine.tick_store:
                    ticks = list(truth_engine.tick_store[symbol])
        
        # Determine mode
        engine_mode = EngineMode.EXECUTION if mode.upper() == "EXECUTION" else EngineMode.ANALYSIS_ONLY
        
        # Get L1 if execution mode
        bid, ask = None, None
        if engine_mode == EngineMode.EXECUTION and data_fabric:
            live_data = data_fabric.get_live(symbol)
            if live_data:
                bid = live_data.get('bid')
                ask = live_data.get('ask')
        
        analysis = engine.analyze_symbol(
            symbol=symbol,
            ticks=ticks,
            static_data=static_data,
            mode=engine_mode,
            bid=bid,
            ask=ask
        )
        
        return {
            'success': True,
            'symbol': symbol,
            'analysis': analysis.model_dump()
        }
        
    except Exception as e:
        logger.error(f"[SIDEHIT] Symbol detail error for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best-odds")
async def get_best_odds(
    group: Optional[str] = Query(None, description="Filter by group (empty=all)"),
):
    """
    Get Best Odds From Side analysis.
    
    Calculates odd_bid_distance and odd_ask_distance for each symbol:
    - odd_bid_distance = last5_tick_avg - bid (positive = Son5Tick above bid)
    - odd_ask_distance = ask - last5_tick_avg (positive = ask above Son5Tick)
    
    Requires L1 data (bid/ask) from data fabric.
    """
    try:
        engine = get_sidehit_press_engine()
        
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        from app.market_data.static_data_store import get_static_store
        from app.core.data_fabric import get_data_fabric
        
        truth_engine = get_truth_ticks_engine()
        static_store = get_static_store()
        data_fabric = get_data_fabric()
        
        if not static_store or not static_store.loaded:
            return {
                'success': False,
                'error': 'Static data not loaded',
                'mode': 'BEST_ODDS'
            }
        
        # Get all symbols or filter by group
        if group:
            all_symbols = static_store.get_all_symbols()
            symbol_list = []
            for s in all_symbols:
                sd = static_store.get_static_data(s)
                if sd:
                    resolved_group = engine.resolve_group(s, sd)
                    if resolved_group == group:
                        symbol_list.append(s)
        else:
            symbol_list = static_store.get_all_symbols()
        
        # =========================================================================
        # LOAD TRUTH TICKS FROM REDIS (for weekend/market closed)
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
                        result_keys = [k for k in result_keys if not k.endswith(':inspect:') and ':inspect:' not in k]
                        
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
        
        # Build group mapping for group summaries
        groups_data = {}
        for symbol in symbol_list:
            static_data = static_store.get_static_data(symbol) or {}
            group_id = engine.resolve_group(symbol, static_data)
            if group_id not in groups_data:
                groups_data[group_id] = []
            groups_data[group_id].append(symbol)
        
        # Process each symbol
        results = []
        symbols_with_l1 = 0
        symbols_without_l1 = 0
        
        for symbol in symbol_list:
            static_data = static_store.get_static_data(symbol) or {}
            avg_adv = static_data.get('AVG_ADV', 0)
            group_id = engine.resolve_group(symbol, static_data)
            
            # Get ticks
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
            
            # Get L1 data
            bid, ask = None, None
            if data_fabric:
                live_data = data_fabric.get_live(symbol)
                if live_data:
                    bid = live_data.get('bid')
                    ask = live_data.get('ask')
            
            if bid and ask:
                symbols_with_l1 += 1
            else:
                symbols_without_l1 += 1
            
            # Compute VOLAV
            if ticks:
                anchor_ts = max(t.get('ts', t.get('timestamp', 0)) for t in ticks)
                volav_15m = engine.compute_volav(ticks, 900, anchor_ts, avg_adv)
                volav_1h = engine.compute_volav(ticks, 3600, anchor_ts, avg_adv)
            else:
                volav_15m = None
                volav_1h = None
            
            # Compute Last 5 Tick
            last5_data = engine.compute_last5_tick(ticks, volav_15m, volav_1h)
            last5_avg = last5_data.get('last5_avg')
            
            # Calculate odd distances
            odd_bid_distance = None
            odd_ask_distance = None
            
            if last5_avg is not None:
                if bid is not None:
                    odd_bid_distance = round(last5_avg - bid, 4)
                if ask is not None:
                    odd_ask_distance = round(ask - last5_avg, 4)
            
            results.append({
                'symbol': symbol,
                'group_id': group_id,
                'bid': bid,
                'ask': ask,
                'last5_tick_avg': last5_avg,
                'odd_bid_distance': odd_bid_distance,
                'odd_ask_distance': odd_ask_distance,
                'volav_15m': volav_15m.volav_price if volav_15m else None,
                'volav_1h': volav_1h.volav_price if volav_1h else None,
                'last5_vs_15m': last5_data.get('last5_vs_15m'),
                'last5_vs_1h': last5_data.get('last5_vs_1h'),
                'tick_count': len(ticks)
            })
        
        # Sort by odd_ask_distance descending (best buying opportunities first)
        results.sort(key=lambda x: x.get('odd_ask_distance') or -999, reverse=True)
        
        logger.info(f"[SIDEHIT] Best Odds: {len(results)} symbols, {symbols_with_l1} with L1, {symbols_without_l1} without L1")
        
        return {
            'success': True,
            'mode': 'BEST_ODDS',
            'timestamp': datetime.now().isoformat(),
            'symbol_count': len(results),
            'symbols_with_l1': symbols_with_l1,
            'symbols_without_l1': symbols_without_l1,
            'groups': list(groups_data.keys()),
            'results': results
        }
        
    except Exception as e:
        logger.error(f"[SIDEHIT] Best Odds error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
