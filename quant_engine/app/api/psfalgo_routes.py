"""
PSFALGO API Routes - Observability & Control

REST API endpoints for RUNALL state, execution observability, and manual controls.
Read-only for decisions, control endpoints for RUNALL lifecycle.

Key Principles:
- Read-only decision/execution observability
- Manual controls (start/stop/toggle)
- No decision/execution logic changes
- Human-readable responses
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import asdict

from app.core.logger import logger
from app.psfalgo.runall_state_api import (
    get_runall_state_api,
    RunallStateSnapshot,
    ExecutionObservability,
    DecisionObservability
)


router = APIRouter(prefix="/api/psfalgo", tags=["psfalgo"])


# ============================================================================
# RUNALL STATE API
# ============================================================================

@router.get("/state")
async def get_runall_state() -> Dict[str, Any]:
    """
    Get current RUNALL state snapshot.
    
    Returns:
        RunallStateSnapshot as dict
    """
    state_api = get_runall_state_api()
    if not state_api:
        raise HTTPException(status_code=503, detail="RunallStateAPI not initialized")
    
    snapshot = state_api.get_state_snapshot()
    if not snapshot:
        raise HTTPException(status_code=503, detail="RunallEngine not available")
    
    # Build account_state with Port Adjuster max exposure (same as /jfin/state)
    account_state = None
    if snapshot.exposure:
        # Convert ExposureSnapshot to dict if needed
        if hasattr(snapshot.exposure, 'dict'):
            account_state = snapshot.exposure.dict()
        elif hasattr(snapshot.exposure, '__dict__'):
            account_state = snapshot.exposure.__dict__.copy()
        else:
            account_state = {
                'pot_total': getattr(snapshot.exposure, 'pot_total', 0),
                'pot_max': getattr(snapshot.exposure, 'pot_max', 0),
            }
    
    # Convert ExposureSnapshot dataclass to dict for proper serialization
    exposure_dict = None
    if snapshot.exposure:
        from dataclasses import asdict
        try:
            exposure_dict = asdict(snapshot.exposure)
            # Convert datetime to ISO string for JSON serialization
            if exposure_dict.get('timestamp'):
                exposure_dict['timestamp'] = str(exposure_dict['timestamp'])
        except Exception as e:
            logger.debug(f"[PSFALGO STATE] Could not convert exposure to dict: {e}")
            exposure_dict = {
                'pot_total': getattr(snapshot.exposure, 'pot_total', 0),
                'pot_max': getattr(snapshot.exposure, 'pot_max', 0),
                'long_lots': getattr(snapshot.exposure, 'long_lots', 0),
                'short_lots': getattr(snapshot.exposure, 'short_lots', 0),
                'long_value': getattr(snapshot.exposure, 'long_value', 0),
                'short_value': getattr(snapshot.exposure, 'short_value', 0),
                'net_exposure': getattr(snapshot.exposure, 'net_exposure', 0),
                'mode': getattr(snapshot.exposure, 'mode', 'OFANSIF'),
            }
    
    # Get Max Exposure from Port Adjuster V2 (account-aware - single source of truth)
    try:
        from app.port_adjuster.port_adjuster_store_v2 import get_port_adjuster_store_v2
        from app.trading.trading_account_context import get_trading_context
        account_id = get_trading_context().trading_mode.value
        pa_store = get_port_adjuster_store_v2()
        pa_config = pa_store.get_config(account_id)
        if pa_config:
            max_exposure_from_pa = pa_config.total_exposure_usd
            if account_state is None:
                account_state = {}
            account_state['limit_max_exposure'] = max_exposure_from_pa
            account_state['pot_max'] = max_exposure_from_pa  # Override with PA value
            if exposure_dict:
                exposure_dict['pot_max'] = max_exposure_from_pa
            logger.debug(f"[PSFALGO STATE] Max exposure from Port Adjuster V2 ({account_id}): ${max_exposure_from_pa:,.0f}")
    except Exception as e:
        logger.warning(f"[PSFALGO STATE] Could not get Port Adjuster V2 config: {e}")
        # Fallback to V1 store
        try:
            from app.port_adjuster.port_adjuster_store import get_port_adjuster_store
            pa_store = get_port_adjuster_store()
            pa_config = pa_store.get_config()
            if pa_config:
                max_exposure_from_pa = pa_config.total_exposure_usd
                if account_state is None:
                    account_state = {}
                account_state['limit_max_exposure'] = max_exposure_from_pa
                account_state['pot_max'] = max_exposure_from_pa
                if exposure_dict:
                    exposure_dict['pot_max'] = max_exposure_from_pa
        except Exception as e2:
            logger.warning(f"[PSFALGO STATE] Could not get Port Adjuster V1 config: {e2}")
    
    # Max cur exp / max pot exp (single source - Set & Check Rules / Port Adjuster sync)
    # V2: Account-aware exposure thresholds
    try:
        from app.psfalgo.exposure_threshold_service_v2 import get_exposure_threshold_service_v2
        from app.trading.trading_account_context import get_trading_context
        account_id = get_trading_context().trading_mode.value
        thresh = get_exposure_threshold_service_v2()
        limits = thresh.get_limits_for_api(account_id)
        if exposure_dict:
            exposure_dict['max_cur_exp_pct'] = limits['max_cur_exp_pct']
            exposure_dict['max_pot_exp_pct'] = limits['max_pot_exp_pct']
            if exposure_dict.get('pot_max') and exposure_dict.get('pot_max') > 0:
                exposure_dict['current_exposure_pct'] = round(
                    100.0 * (exposure_dict.get('pot_total') or 0) / exposure_dict['pot_max'], 2
                )
        if account_state is not None:
            account_state['max_cur_exp_pct'] = limits['max_cur_exp_pct']
            account_state['max_pot_exp_pct'] = limits['max_pot_exp_pct']
    except Exception as e:
        logger.debug(f"[PSFALGO STATE] Exposure limits: {e}")

    return {
        'success': True,
        'state': {
            'global_state': snapshot.global_state,
            'cycle_state': snapshot.cycle_state,
            'cycle_id': snapshot.cycle_id,
            'loop_running': snapshot.loop_running,
            'dry_run_mode': snapshot.dry_run_mode,
            'active_engines': snapshot.active_engines,
            'cycle_start_time': snapshot.cycle_start_time,
            'next_cycle_time': snapshot.next_cycle_time,
            'last_error': snapshot.last_error,
            'last_error_time': snapshot.last_error_time,
            'exposure': exposure_dict,
            'account_state': account_state,
            'timestamp': snapshot.timestamp
        }
    }


@router.get("/exposure-limits")
async def get_exposure_limits(account_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get exposure limits for account (single source for Set & Check Rules, Port Adjuster, and UI).
    V2: Account-aware - pass account_id or uses current trading context.

    Response includes:
    - max_cur_exp_pct: Current exposure threshold (%)
    - max_pot_exp_pct: Potential exposure threshold (%)
    - pot_max: Maximum exposure limit ($)
    - cur_max_dollars: Derived current limit in dollars (pot_max × max_cur_exp_pct / 100)
    """
    try:
        from app.psfalgo.exposure_threshold_service_v2 import get_exposure_threshold_service_v2
        from app.trading.trading_account_context import get_trading_context
        acc = account_id or get_trading_context().trading_mode.value
        thresh = get_exposure_threshold_service_v2()
        limits = thresh.get_limits_for_api(acc)
        
        # Add derived dollar values
        pot_max = limits.get('pot_max', 1400000.0)
        cur_pct = limits.get('max_cur_exp_pct', 92.0)
        limits['cur_max_dollars'] = round(pot_max * (cur_pct / 100.0), 2)
        limits['derisk_at_dollars'] = round(pot_max * 0.849, 2)
        limits['hard_stop_at_dollars'] = round(pot_max * (cur_pct / 100.0), 2)
        
        return {"success": True, "account_id": acc, **limits}
    except Exception as e:
        logger.error(f"[PSFALGO] get_exposure_limits: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hard-risk-status")
async def get_hard_risk_status(account_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Hard risk modu: cur >= max_cur_exp OR pot >= max_pot_exp.
    REV saved/reload (INC) atlanmalı; sadece REV take profit (DEC) çalışır.
    V2: Account-aware thresholds - pass account_id or uses current trading context.
    """
    try:
        from app.trading.trading_account_context import get_trading_context
        from app.psfalgo.exposure_calculator import get_current_and_potential_exposure_pct
        from app.psfalgo.exposure_threshold_service_v2 import get_exposure_threshold_service_v2

        acc = account_id or get_trading_context().trading_mode.value
        _, cur_pct, pot_pct = await get_current_and_potential_exposure_pct(acc)
        thresh = get_exposure_threshold_service_v2()
        hard_risk = thresh.is_hard_risk_mode(acc, cur_pct, pot_pct)
        limits = thresh.get_limits_for_api(acc)
        return {
            "success": True,
            "hard_risk": hard_risk,
            "account_id": acc,
            "current_exposure_pct": round(cur_pct, 2),
            "potential_exposure_pct": round(pot_pct, 2),
            "max_cur_exp_pct": limits['max_cur_exp_pct'],
            "max_pot_exp_pct": limits['max_pot_exp_pct'],
        }
    except Exception as e:
        logger.error(f"[PSFALGO] hard-risk-status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/free-exposure")
async def get_free_exposure(account_id: Optional[str] = None, symbol: Optional[str] = None) -> Dict[str, Any]:
    """
    Free Exposure Status — boş kapasite ve MM lot limitleri.
    
    Döndürür:
    - free_cur_pct: Mevcut boş kapasite (%)
    - free_pot_pct: Potansiyel boş kapasite (%)
    - effective_free_pct: Bağlayıcı minimum (%)
    - divisor: AVG_ADV böleni (None = BLOCKED)
    - tier_label: Kademe açıklaması
    - blocked: True ise tüm INCREASE emirleri yasak
    - mm_lot: (opsiyonel) Belirtilen sembol için hesaplanan MM lot
    """
    try:
        from app.trading.trading_account_context import get_trading_context
        from app.psfalgo.free_exposure_engine import get_free_exposure_engine

        acc = account_id or get_trading_context().trading_mode.value
        engine = get_free_exposure_engine()
        snapshot = await engine.calculate_free_exposure(acc)
        
        result = {"success": True, **snapshot}
        
        # Opsiyonel: belirli bir sembol için lot hesapla
        if symbol:
            mm_lot = await engine.get_mm_lot_for_symbol(acc, symbol, use_cache=True)
            result['mm_lot'] = mm_lot
            result['mm_lot_symbol'] = symbol
        
        return result
    except Exception as e:
        logger.error(f"[PSFALGO] free-exposure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/free-exposure/all-accounts")
async def get_free_exposure_all_accounts() -> Dict[str, Any]:
    """Tüm hesapların free exposure durumunu döndür (cache'den)."""
    try:
        from app.psfalgo.free_exposure_engine import get_free_exposure_engine
        engine = get_free_exposure_engine()
        return {"success": True, "accounts": engine.get_status_summary()}
    except Exception as e:
        logger.error(f"[PSFALGO] free-exposure/all-accounts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exposure-limits")
async def set_exposure_limits(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Set exposure limits per account. V2: Account-aware.

    Body: {
        "account_id": "IBKR_PED",
        "max_cur_exp_pct": 92,
        "max_pot_exp_pct": 100,
        "pot_max": 5000000
    }

    pot_max = maximum exposure limit in dollars ($).
    max_cur_exp_pct = current exposure threshold (%) — when reached, ADDNEWPOS disabled.
    max_pot_exp_pct = potential exposure threshold (%) — when reached, hard risk mode ON.

    Example: pot_max=$5M + max_cur_exp_pct=92% → derisk starts at $4.6M.
    If account_id not provided, uses current trading context.
    """
    try:
        from app.psfalgo.exposure_threshold_service_v2 import get_exposure_threshold_service_v2
        from app.trading.trading_account_context import get_trading_context
        
        account_id = request.get("account_id") or get_trading_context().trading_mode.value
        thresh = get_exposure_threshold_service_v2()
        cur = request.get("max_cur_exp_pct")
        pot = request.get("max_pot_exp_pct")
        pot_max = request.get("pot_max")
        
        if cur is not None:
            cur = float(cur)
        if pot is not None:
            pot = float(pot)
        if pot_max is not None:
            pot_max = float(pot_max)
        
        if cur is None and pot is None and pot_max is None:
            return {"success": False, "error": "Provide at least one of: max_cur_exp_pct, max_pot_exp_pct, pot_max"}
        
        # Get current thresholds for this account
        current_thresholds = thresh.get_thresholds(account_id)
        cur = cur if cur is not None else current_thresholds.get("current_threshold", 92.0)
        pot = pot if pot is not None else current_thresholds.get("potential_threshold", 100.0)
        
        thresh.save_thresholds(account_id, current=cur, potential=pot, pot_max=pot_max)
        
        # Recalculate derived values for response
        saved = thresh.get_thresholds(account_id)
        actual_pot_max = saved['pot_max']
        cur_max_dollars = actual_pot_max * (cur / 100.0)
        
        logger.info(
            f"[PSFALGO] Exposure limits set for {account_id}: "
            f"cur={cur}%, pot={pot}%, pot_max=${actual_pot_max:,.0f}, "
            f"cur_max_dollars=${cur_max_dollars:,.0f}"
        )
        return {
            "success": True,
            "account_id": account_id,
            "max_cur_exp_pct": cur,
            "max_pot_exp_pct": pot,
            "pot_max": actual_pot_max,
            "cur_max_dollars": round(cur_max_dollars, 2),
            "derisk_at_dollars": round(actual_pot_max * 0.849, 2),
            "hard_stop_at_dollars": round(actual_pot_max * (cur / 100.0), 2),
        }
    except Exception as e:
        logger.error(f"[PSFALGO] set_exposure_limits: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start")
async def start_runall() -> Dict[str, Any]:
    """
    Start RUNALL engine (manual control).
    
    Returns:
        Result dict with status
    """
    state_api = get_runall_state_api()
    if not state_api:
        raise HTTPException(status_code=503, detail="RunallStateAPI not initialized")
    
    result = await state_api.start_runall()
    
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to start RUNALL'))
    
    return result


@router.post("/stop")
async def stop_runall() -> Dict[str, Any]:
    """
    Stop RUNALL engine (manual control).
    
    Returns:
        Result dict with status
    """
    state_api = get_runall_state_api()
    if not state_api:
        raise HTTPException(status_code=503, detail="RunallStateAPI not initialized")
    
    result = await state_api.stop_runall()
    
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to stop RUNALL'))
    
    return result


@router.post("/emergency-stop")
async def emergency_stop() -> Dict[str, Any]:
    """
    Emergency stop - immediately stops RUNALL and execution.
    
    Returns:
        Result dict with status
    """
    state_api = get_runall_state_api()
    if not state_api:
        raise HTTPException(status_code=503, detail="RunallStateAPI not initialized")
    
    result = await state_api.emergency_stop()
    
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to emergency stop'))
    
    return result


@router.post("/toggle-dry-run")
async def toggle_dry_run() -> Dict[str, Any]:
    """
    Toggle dry-run mode (manual control).
    
    Returns:
        Result dict with new dry_run status
    """
    state_api = get_runall_state_api()
    if not state_api:
        raise HTTPException(status_code=503, detail="RunallStateAPI not initialized")
    
    result = state_api.toggle_dry_run()
    
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to toggle dry-run'))
    
    return result
    
    
@router.post("/set-active-engines")
async def set_active_engines(engines: List[str]) -> Dict[str, Any]:
    """
    Set active engines for execution loop (LT_TRIM, KARBOTU, REDUCEMORE, MM_ENGINE).
    Controlled by UI checkboxes.
    """
    from app.psfalgo.runall_state_api import get_runall_state_api
    
    # We need to access the engine directly usually, but StateAPI might not expose it.
    # However, RunallStateAPI usually holds the engine instance.
    # Check runall_state_api.py. For now assuming we can get the engine.
    from app.psfalgo.runall_engine import RunallEngine
    # The runall engine is a singleton in runall_state_api?
    # Actually, let's fix this properly. 
    # Usually we get the engine via a get_runall_engine() call.
    # Let's import the getter if it exists.
    
    # Assuming get_runall_state_api returns the API wrapper, we need to add a method there too?
    # Or just grab the global instance if relevant.
    # Let's try to add it to RunallStateAPI first or access engine directly if possible.
    
    # Better approach: Add set_active_engines to RunallStateAPI.
    # But I can't modify that file right now without viewing it.
    # Let's just import the global engine getter if it exists.
    # Wait, runall_engine.py has no getter? 
    # Ah, runall_state_api.py likely has it.
    
    try:
        logger.info(f"[DEBUG_ENGINES] Received request to set engines: {engines}")
        state_api = get_runall_state_api()
        
        if not state_api:
            logger.error("[DEBUG_ENGINES] state_api is None! Call initialize_runall_state_api first.")
            return {'success': False, 'error': 'RunallStateAPI not initialized'}
            
        if not state_api.runall_engine:
            logger.error(f"[DEBUG_ENGINES] state_api found but runall_engine is None! state_api={state_api}")
            return {'success': False, 'error': 'RunallEngine not connected to StateAPI'}
            
        logger.info(f"[DEBUG_ENGINES] Updating active_engines via RunallEngine instance: {id(state_api.runall_engine)}")
        state_api.runall_engine.set_active_engines(engines)
        
        # Verify it persisted immediately
        current = state_api.runall_engine.active_engines
        logger.info(f"[DEBUG_ENGINES] Verified active_engines are now: {current}")
        
        return {'success': True, 'active_engines': current}
    except Exception as e:
        logger.error(f"[DEBUG_ENGINES] Exception in set_active_engines: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


@router.post("/reset-active-engines")
async def reset_active_engines() -> Dict[str, Any]:
    """
    Reset active engines to defaults (LT_TRIM, KARBOTU, MM_ENGINE, ADDNEWPOS_ENGINE).
    Persisted to Redis.
    """
    from app.psfalgo.runall_state_api import get_runall_state_api
    try:
        state_api = get_runall_state_api()
        if not state_api or not state_api.runall_engine:
            return {'success': False, 'error': 'RunallEngine not initialized'}
        
        engines = state_api.runall_engine.reset_active_engines_to_default()
        return {'success': True, 'active_engines': engines}
    except Exception as e:
        logger.error(f"[API] reset_active_engines error: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


# ============================================================================
# L/S RATIO SETTINGS (Per-Engine Long/Short Allocation)
# ============================================================================

@router.get("/ls-ratio")
async def get_ls_ratio() -> Dict[str, Any]:
    """
    Get Long/Short ratio for all increase engines.
    Returns: { MM_ENGINE: {long_pct, short_pct}, PATADD_ENGINE: ..., ADDNEWPOS_ENGINE: ... }
    """
    try:
        from app.xnl.ls_ratio_settings import get_ls_ratio_store
        store = get_ls_ratio_store()
        return {'success': True, 'ratios': store.get_all()}
    except Exception as e:
        logger.error(f"[API] get_ls_ratio error: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


@router.post("/ls-ratio")
async def set_ls_ratio(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Set Long/Short ratio for an increase engine.
    Body: { "engine": "MM_ENGINE", "long_pct": 30 }
    short_pct is automatically computed as 100 - long_pct.
    """
    try:
        from app.xnl.ls_ratio_settings import get_ls_ratio_store
        engine_name = request.get('engine')
        long_pct = request.get('long_pct')
        if not engine_name or long_pct is None:
            return {'success': False, 'error': 'engine and long_pct required'}
        store = get_ls_ratio_store()
        result = store.set_ratio(engine_name, int(long_pct))
        return {'success': True, 'engine': engine_name, **result, 'ratios': store.get_all()}
    except Exception as e:
        logger.error(f"[API] set_ls_ratio error: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


# ============================================================================
# EXECUTION OBSERVABILITY
# ============================================================================

@router.get("/execution/history")
async def get_execution_history(last_n: int = 10) -> Dict[str, Any]:
    """
    Get last N execution plans.
    
    Args:
        last_n: Number of recent execution plans (default: 10, max: 50)
    
    Returns:
        List of ExecutionObservability objects
    """
    state_api = get_runall_state_api()
    if not state_api:
        raise HTTPException(status_code=503, detail="RunallStateAPI not initialized")
    
    last_n = min(last_n, 50)  # Cap at 50
    history = state_api.get_execution_history(last_n=last_n)
    
    return {
        'success': True,
        'count': len(history),
        'history': [asdict(obs) for obs in history]
    }


@router.get("/execution/last")
async def get_last_execution(source: Optional[str] = None) -> Dict[str, Any]:
    """
    Get last execution plan for a source (or all sources).
    
    Args:
        source: "KARBOTU", "REDUCEMORE", "ADDNEWPOS", or None for all
    
    Returns:
        Last execution plan(s)
    """
    state_api = get_runall_state_api()
    if not state_api:
        raise HTTPException(status_code=503, detail="RunallStateAPI not initialized")
    
    history = state_api.get_execution_history(last_n=50)
    
    if source:
        # Filter by source
        filtered = [obs for obs in history if obs.source == source]
        if not filtered:
            return {'success': True, 'source': source, 'execution': None}
        return {'success': True, 'source': source, 'execution': asdict(filtered[-1])}
    else:
        # Return last for each source
        result = {}
        for src in ['KARBOTU', 'REDUCEMORE', 'ADDNEWPOS']:
            filtered = [obs for obs in history if obs.source == src]
            if filtered:
                result[src] = asdict(filtered[-1])
            else:
                result[src] = None
        
        return {'success': True, 'executions': result}


# ============================================================================
# DECISION OBSERVABILITY (READ-ONLY)
# ============================================================================

@router.get("/decision/snapshot")
async def get_decision_snapshot(source: Optional[str] = None) -> Dict[str, Any]:
    """
    Get last cycle DecisionResponse snapshot (READ-ONLY).
    
    Args:
        source: "KARBOTU", "REDUCEMORE", "ADDNEWPOS", or None for all
    
    Returns:
        DecisionObservability snapshot(s)
    """
    state_api = get_runall_state_api()
    if not state_api:
        raise HTTPException(status_code=503, detail="RunallStateAPI not initialized")
    
    if source:
        snapshot = state_api.get_decision_snapshot(source)
        if not snapshot:
            return {'success': True, 'source': source, 'snapshot': None}
        return {'success': True, 'source': source, 'snapshot': asdict(snapshot)}
    else:
        # Return all sources
        result = {}
        for src in ['KARBOTU', 'REDUCEMORE', 'ADDNEWPOS']:
            snapshot = state_api.get_decision_snapshot(src)
            if snapshot:
                result[src] = asdict(snapshot)
            else:
                result[src] = None
        
        return {'success': True, 'snapshots': result}



# ============================================================================
# REJECTED OBSERVABILITY (SHADOW REASONS)
# ============================================================================

@router.get("/rejected")
async def get_rejected_candidates(limit: int = 100) -> Dict[str, Any]:
    """
    Get recent rejected candidates with reasons (Shadow Visibility).
    
    Args:
        limit: Max number of records (default: 100)
    
    Returns:
        List of rejected candidates with structured reasons
    """
    from app.psfalgo.reject_reason_store import get_reject_reason_store
    
    store = get_reject_reason_store()
    rejections = store.get_latest(limit=limit)
    
    return {
        'success': True,
        'count': len(rejections),
        'rejections': rejections
    }


# ============================================================================
# NOT FOUND STOCKS (Zero/Missing Metrics)
# ============================================================================

@router.get("/not-found")
async def get_not_found_stocks() -> Dict[str, Any]:
    """
    Get stocks with missing/zero critical metrics (DATA_INCOMPLETE).
    
    These stocks are excluded from KARBOTU, REDUCEMORE, ADDNEWPOS proposals
    because their Fbtot, SFStot, GORT, or SMA values are None or exactly 0.00.
    
    Returns:
        List of not found stocks with their missing metrics
    """
    from app.core.redis_client import get_redis_client
    import json
    
    try:
        redis = get_redis_client().sync
        
        not_found_list = []
        
        # Get from all engine sources
        for source in ['karbotu', 'addnewpos', 'reducemore']:
            key = f"psfalgo:not_found:{source}"
            data = redis.get(key)
            if data:
                try:
                    items = json.loads(data)
                    for item in items:
                        item['source'] = source.upper()
                        not_found_list.append(item)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in {key}")
        
        # Deduplicate by symbol (keep first occurrence)
        seen = set()
        unique_list = []
        for item in not_found_list:
            if item['symbol'] not in seen:
                seen.add(item['symbol'])
                unique_list.append(item)
        
        return {
            'success': True,
            'count': len(unique_list),
            'not_found': unique_list
        }
        
    except Exception as e:
        logger.error(f"[NOT_FOUND] Error fetching not found stocks: {e}", exc_info=True)
        return {
            'success': False,
            'count': 0,
            'not_found': [],
            'error': str(e)
        }



# ============================================================================
# AUDIT TRAIL
# ============================================================================

@router.get("/audit/trail")
async def get_audit_trail(last_n: int = 50) -> Dict[str, Any]:
    """
    Get last N audit trail entries.
    
    Args:
        last_n: Number of recent entries (default: 50, max: 100)
    
    Returns:
        List of audit trail entries
    """
    state_api = get_runall_state_api()
    if not state_api:
        raise HTTPException(status_code=503, detail="RunallStateAPI not initialized")
    
    last_n = min(last_n, 100)  # Cap at 100
    trail = state_api.get_audit_trail(last_n=last_n)
    
    return {
        'success': True,
        'count': len(trail),
        'trail': trail
    }


# ============================================================================
# SHADOW LIVE (DRY-RUN OPERATIONS)
# ============================================================================

@router.post("/shadow/start")
async def start_shadow_live() -> Dict[str, Any]:
    """
    Start Shadow Live Runner (DRY-RUN operations).
    
    Returns:
        Result dict with status
    """
    from app.psfalgo.shadow_live_runner import get_shadow_live_runner, initialize_shadow_live_runner
    
    runner = get_shadow_live_runner()
    if not runner:
        runner = initialize_shadow_live_runner()
    
    try:
        await runner.start()
        return {'success': True, 'message': 'Shadow Live Runner started'}
    except Exception as e:
        logger.error(f"Error starting Shadow Live Runner: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shadow/stop")
async def stop_shadow_live() -> Dict[str, Any]:
    """
    Stop Shadow Live Runner.
    
    Returns:
        Result dict with status
    """
    from app.psfalgo.shadow_live_runner import get_shadow_live_runner
    
    runner = get_shadow_live_runner()
    if not runner:
        raise HTTPException(status_code=404, detail="Shadow Live Runner not initialized")
    
    try:
        await runner.stop()
        return {'success': True, 'message': 'Shadow Live Runner stopped'}
    except Exception as e:
        logger.error(f"Error stopping Shadow Live Runner: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shadow/status")
async def get_shadow_live_status() -> Dict[str, Any]:
    """
    Get Shadow Live Runner status and current session metrics.
    
    Returns:
        Status and session metrics
    """
    from app.psfalgo.shadow_live_runner import get_shadow_live_runner
    
    runner = get_shadow_live_runner()
    if not runner:
        return {
            'success': True,
            'runner_status': 'NOT_INITIALIZED',
            'session': None
        }
    
    session = runner.get_current_session_metrics()
    
    return {
        'success': True,
        'runner_status': runner.runner_status.value,
        'runner_running': runner.runner_running,
        'session': asdict(session) if session else None
    }


# ============================================================================
# ORDER PROPOSALS (Human-in-the-Loop)
# ============================================================================

def _get_active_account_id() -> Optional[str]:
    """
    Get the currently active account ID from Redis.
    Returns: 'HAMPRO', 'IBKR_PED', 'IBKR_GUN', or None if not set.
    
    CRITICAL: Used for per-account proposal filtering.
    When user switches account mode in the UI, only that account's proposals should be visible.
    """
    try:
        from app.core.redis_client import get_redis_client
        redis = get_redis_client()
        if redis and redis.sync:
            mode = redis.sync.get("psfalgo:trading:account_mode")
            if mode:
                if isinstance(mode, bytes):
                    mode = mode.decode("utf-8")
                return mode.strip()
    except Exception:
        pass
    return None

@router.get("/proposals")
async def get_proposals(
    status: Optional[str] = None,
    engine: Optional[str] = None,
    cycle_id: Optional[int] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get order proposals with optional filters.
    
    CRITICAL: Automatically filters by active account.
    When user is viewing IBKR_PED, only IBKR_PED proposals are shown.
    When user is viewing HAMPRO, only HAMPRO proposals are shown.
    
    Args:
        status: Filter by status (PROPOSED, ACCEPTED, REJECTED, EXPIRED)
        engine: Filter by engine (KARBOTU, REDUCEMORE, ADDNEWPOS)
        cycle_id: Filter by cycle ID
        limit: Maximum number of proposals to return (default: 100, max: 500)
    
    Returns:
        List of OrderProposals for the active account
    """
    from app.psfalgo.proposal_store import get_proposal_store
    
    proposal_store = get_proposal_store()
    if not proposal_store:
        return {
            'success': True,
            'count': 0,
            'proposals': []
        }
    
    # CRITICAL: Filter by active account
    active_account = _get_active_account_id()
    
    limit = min(limit, 500)  # Cap at 500
    proposals = proposal_store.get_all_proposals(
        status=status,
        engine=engine,
        cycle_id=cycle_id,
        account_id=active_account,
        limit=limit
    )
    # Son 60 sn icinde uretilmis proposal'lar; eskiler listede gorunmez
    proposals = _drop_stale_proposals(proposals, max_age_seconds=60)
    # Unique (hisse, yon): ayni hisse+yon icin sadece |lot| buyuk olan; birebir ayni emir tekrar etmesin
    proposals = _unique_proposals_by_symbol_side_max_abs_lot(proposals, proposal_store)
    out = [p.to_dict() for p in proposals]
    out = _enrich_proposals_with_live_l1(out)
    return {
        'success': True,
        'count': len(out),
        'proposals': out,
        'active_account': active_account
    }


def _drop_stale_proposals(plist: List, max_age_seconds: int = 60) -> List:
    """Son max_age_seconds (varsayilan 60 sn) icinde uretilmis proposal'lari tutar; eskileri atmaz."""
    if not plist:
        return plist
    now_ts = datetime.utcnow().timestamp()
    cutoff_ts = now_ts - max_age_seconds
    out = []
    for p in plist:
        pt = getattr(p, "proposal_ts", None)
        if pt is None:
            continue
        ts = pt.timestamp() if hasattr(pt, "timestamp") else (float(pt) if pt else 0)
        if ts >= cutoff_ts:
            out.append(p)
    return out


def _unique_proposals_by_symbol_side_max_abs_lot(plist: List, proposal_store=None) -> List:
    """
    Ayni (hisse, yon) icin tek oneri: mutlak lotu buyuk olan kalir, kucuk olan esgecilir.
    Birebir ayni emir (ayni hisse, ayni lot, ayni yon) zaten tek kayit olur.
    Tie-break: LT_STAGE yuksek, sonra en guncel proposal_ts.
    """
    if not plist:
        return plist
    by_sym_side = {}
    for p in plist:
        sym = (getattr(p, "symbol", None) or "").strip().upper()
        side = (getattr(p, "side", None) or "SELL").upper()
        k = (sym, side)
        qty = int(getattr(p, "qty", 0) or 0)
        abs_qty = abs(qty)
        ts = 0.0
        pt = getattr(p, "proposal_ts", None)
        if pt is not None:
            ts = pt.timestamp() if hasattr(pt, "timestamp") else (float(pt) if pt else 0.0)
        r = proposal_store.get_lt_stage_rank(p) if proposal_store else 0
        if k not in by_sym_side:
            by_sym_side[k] = (p, abs_qty, r, ts)
        else:
            _cur, cur_abs, cur_r, cur_ts = by_sym_side[k]
            if abs_qty > cur_abs or (abs_qty == cur_abs and (r > cur_r or (r == cur_r and ts > cur_ts))):
                by_sym_side[k] = (p, abs_qty, r, ts)
    return [v[0] for v in by_sym_side.values()]


def _enrich_proposals_with_live_l1(proposal_dicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Her proposal icin guncel L1 bid/ask/last DataFabric'ten alinir; Redis'teki eski degerler
    uzerine yazilir. Emir onerisi fiyati her zaman guncel tahtaya gore yeniden hesaplanir:
    SELL = ask - spread*0.15, BUY = bid + spread*0.15. Boylece UI tahta ve son print ile uyumlu gorur.
    """
    if not proposal_dicts:
        return proposal_dicts
    try:
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        if not fabric:
            return proposal_dicts
        SPREAD_FACTOR = 0.15
        for d in proposal_dicts:
            sym = (d.get("symbol") or "").strip()
            if not sym:
                continue
            snap = fabric.get_fast_snapshot(sym)
            if not snap:
                continue
            bid = snap.get("bid")
            ask = snap.get("ask")
            last = snap.get("last")
            try:
                bid_f = float(bid) if bid is not None else None
                ask_f = float(ask) if ask is not None else None
                last_f = float(last) if last is not None else None
            except (TypeError, ValueError):
                bid_f, ask_f, last_f = None, None, None
            if bid_f is not None:
                d["bid"] = bid_f
            if ask_f is not None:
                d["ask"] = ask_f
            if last_f is not None:
                d["last"] = last_f
            # Emir onerisi: SELL = ask - spread*0.15, BUY = bid + spread*0.15 (her zaman guncel L1)
            if bid_f is not None and ask_f is not None and bid_f > 0 and ask_f > 0:
                spread = ask_f - bid_f
                mid = (bid_f + ask_f) / 2
                side = (d.get("side") or "SELL").upper()
                if "SELL" in side:
                    proposed = round(ask_f - spread * SPREAD_FACTOR, 2)
                else:
                    proposed = round(bid_f + spread * SPREAD_FACTOR, 2)
                d["proposed_price"] = proposed
                d["price"] = proposed
                d["spread"] = round(spread, 4)
                if mid > 0:
                    d["spread_percent"] = round((spread / mid) * 100, 4)
    except Exception as e:
        logger.warning(f"[PROPOSALS] Enrich L1 failed: {e}")
    return proposal_dicts


@router.get("/proposals/latest")
async def get_latest_proposals(limit: int = 10) -> Dict[str, Any]:
    """
    Get latest N order proposals from CURRENT CYCLE ONLY.
    Only shows proposals from the most recent cycle to avoid showing stale proposals.
    
    Args:
        limit: Number of latest proposals (default: 10, max: 500)
    
    Returns:
        Latest OrderProposals from current cycle
    """
    from app.psfalgo.proposal_store import get_proposal_store
    
    proposal_store = get_proposal_store()
    if not proposal_store:
        return {
            'success': True,
            'count': 0,
            'proposals': []
        }
    
    limit = min(limit, 500)  # Increased cap to 500 to accommodate all pending
    
    # CRITICAL: Filter by active account
    active_account = _get_active_account_id()
    
    # Get current cycle_id from RUNALL state
    current_cycle_id = None
    try:
        state_api = get_runall_state_api()
        if state_api:
            snapshot = state_api.get_state_snapshot()
            if snapshot:
                current_cycle_id = snapshot.cycle_id
    except Exception as e:
        logger.warning(f"[PROPOSALS] Could not get current cycle_id: {e}")
    
    def _drop_stale(plist, max_age_seconds: int = 60):
        """Sadece son veriler: max_age_seconds (varsayilan 1 dk) dan eski onerileri at; eski Redis verisi donmez."""
        if not plist:
            return plist
        now_ts = datetime.utcnow().timestamp()
        cutoff_ts = now_ts - max_age_seconds
        out = []
        for p in plist:
            ts = getattr(p, "proposal_ts", None)
            if ts is None:
                continue
            pt = ts.timestamp() if hasattr(ts, "timestamp") else (float(ts) if ts else 0)
            if pt >= cutoff_ts:
                out.append(p)
        return out

    # Sadece son 1 dakika: eski Redis verisi (chg 0.09 vs 0.40 gibi) donmesin; tekil ve en guncel
    MAX_AGE_SECONDS = 60  # 1 dk

    # If we have a current cycle_id, filter by it
    if current_cycle_id is not None:
        proposals = proposal_store.get_all_proposals(
            cycle_id=current_cycle_id,
            account_id=active_account,
            limit=limit * 2
        )
        proposals = _drop_stale(proposals, MAX_AGE_SECONDS)
        # Unique (hisse, yon): ayni hisse+yon icin sadece |lot| buyuk olan; birebir ayni emir tek olur
        proposals = _unique_proposals_by_symbol_side_max_abs_lot(proposals, proposal_store)
        proposals.sort(key=lambda x: x.proposal_ts, reverse=True)
        proposals = proposals[:limit]
        out = [p.to_dict() for p in proposals]
        out = _enrich_proposals_with_live_l1(out)
        return {
            'success': True,
            'count': len(out),
            'proposals': out,
            'cycle_id': current_cycle_id
        }

    # Fallback: Get latest proposals (if cycle_id not available)
    pending = proposal_store.get_all_proposals(status='PROPOSED', account_id=active_account, limit=1000)
    history_limit = 50
    history = proposal_store.get_all_proposals(account_id=active_account, limit=history_limit)
    merged_map = {p.id: p for p in pending}
    for p in history:
        if p.id not in merged_map:
            merged_map[p.id] = p
    final_proposals = list(merged_map.values())
    final_proposals = _drop_stale(final_proposals, MAX_AGE_SECONDS)
    # Unique (hisse, yon): ayni hisse+yon icin sadece |lot| buyuk olan; birebir ayni emir tek olur
    final_proposals = _unique_proposals_by_symbol_side_max_abs_lot(final_proposals, proposal_store)
    final_proposals.sort(key=lambda x: x.proposal_ts, reverse=True)
    if len(final_proposals) > limit and len(pending) < limit:
        final_proposals = final_proposals[:limit]

    out = [p.to_dict() for p in final_proposals]
    out = _enrich_proposals_with_live_l1(out)
    return {
        'success': True,
        'count': len(out),
        'proposals': out
    }


@router.post("/proposals/{proposal_id}/accept")
async def accept_proposal(proposal_id: str) -> Dict[str, Any]:
    """
    Mark proposal as ACCEPTED and EXECUTE (human action).
    
    Args:
        proposal_id: Proposal ID
    
    Returns:
        Result dict
    """
    # Use ExecutionService for full flow (Accept -> Execute)
    from app.psfalgo.execution_service import get_execution_service
    
    service = get_execution_service()
    if not service:
         raise HTTPException(status_code=503, detail="ExecutionService not initialized")
    
    # First, mark as ACCEPTED in store (handled by service? No, service assumes it does it or checks)
    # ExecutionService.execute_proposal checks if status is ACCEPTED?
    # Actually, my implementation of ExecutionService checks: "if proposal.status != 'ACCEPTED': return error".
    # So we must update status FIRST.
    
    from app.psfalgo.proposal_store import get_proposal_store
    proposal_store = get_proposal_store()
    
    # Update Status to ACCEPTED
    success = proposal_store.update_proposal_status(
        proposal_id=proposal_id,
        status='ACCEPTED',
        human_action='ACCEPTED'
    )
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
        
    # Now Execute
    result = await service.execute_proposal(proposal_id)
    
    if not result.get('success'):
         # Execution failed, but proposal was Accepted.
         # Warn user but don't fail the request completely?
         # Or return 500?
         logger.error(f"Execution failed for {proposal_id}: {result.get('error')}")
         return {
             'success': False,
             'message': f"Proposal Accepted but Execution Failed: {result.get('error')}",
             'execution_result': result
         }
    
    return {
        'success': True,
        'message': f"Proposal {proposal_id} ACCEPTED and SENT to execution",
        'execution_result': result.get('execution_result')
    }


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str) -> Dict[str, Any]:
    """
    Mark proposal as REJECTED (human action).
    
    Args:
        proposal_id: Proposal ID
    
    Returns:
        Result dict
    """
    from app.psfalgo.proposal_store import get_proposal_store
    
    proposal_store = get_proposal_store()
    if not proposal_store:
        raise HTTPException(status_code=503, detail="ProposalStore not initialized")
    
    success = proposal_store.update_proposal_status(
        proposal_id=proposal_id,
        status='REJECTED',
        human_action='REJECTED'
    )
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    
    return {
        'success': True,
        'message': f'Proposal {proposal_id} marked as REJECTED'
    }


@router.get("/proposals/stats")
async def get_proposal_stats() -> Dict[str, Any]:
    """
    Get proposal store statistics.
    
    Returns:
        Proposal statistics
    """
    from app.psfalgo.proposal_store import get_proposal_store
    
    proposal_store = get_proposal_store()
    if not proposal_store:
        return {
            'success': True,
            'stats': {
                'total_proposals': 0,
                'by_status': {},
                'by_engine': {},
                'by_side': {}
            }
        }
    
    stats = proposal_store.get_stats()
    
    return {
        'success': True,
        'stats': stats
    }


# ============================================================================
# DATA READINESS & HEALTH CHECKS (Phase 8)
# ============================================================================

@router.get("/health/data")
async def get_data_readiness() -> Dict[str, Any]:
    """
    Get data readiness checklist.
    
    Returns:
        Data readiness report with field counts and sample symbols
    """
    from app.psfalgo.data_readiness_checker import get_data_readiness_checker, initialize_data_readiness_checker
    
    checker = get_data_readiness_checker()
    if not checker:
        initialize_data_readiness_checker()
        checker = get_data_readiness_checker()
    
    if not checker:
        return {
            'success': False,
            'error': 'DataReadinessChecker not initialized'
        }
    
    report = checker.check_data_readiness()
    
    return {
        'success': True,
        'report': report
    }


# ============================================================================
# JFIN STATE API (For ADDNEWPOS UI Tab)
# ============================================================================

@router.get("/jf/state")
async def get_jfin_state() -> Dict[str, Any]:
    """
    Get current JFIN state for ADDNEWPOS tab.
    
    Returns JFIN intents from last RUNALL cycle:
    - bb_stocks: BB pool stocks
    - fb_stocks: FB pool stocks  
    - sas_stocks: SAS pool stocks
    - sfs_stocks: SFS pool stocks
    - percentage: Current JFIN percentage
    """
    from app.core.redis_client import get_redis_client
    import json
    
    try:
        redis = get_redis_client().sync
        
        # Get JFIN state from Redis
        state_json = redis.get("psfalgo:jfin:current_state")
        
        if not state_json:
            # Check if RUNALL is running
            state_api = get_runall_state_api()
            runall_running = False
            if state_api:
                snapshot = state_api.get_state_snapshot()
                runall_running = snapshot.loop_running if snapshot else False
            
            return {
                "success": True,
                "is_empty": True,
                "state": None,
                "runall_running": runall_running,
                "message": "JFIN state not populated. Start RUNALL to generate ADDNEWPOS data."
            }
        
        # Parse state
        state = json.loads(state_json)
        
        # ADDED: Enhance state with Account Exposure info (for UI estimation)
        state_api = get_runall_state_api()
        account_state = None
        if state_api:
            snapshot = state_api.get_state_snapshot()
            if snapshot and snapshot.exposure:
                # Convert ExposureSnapshot to dict if needed
                if hasattr(snapshot.exposure, 'dict'):
                    account_state = snapshot.exposure.dict()
                elif hasattr(snapshot.exposure, '__dict__'):
                    account_state = snapshot.exposure.__dict__.copy()
                else:
                    account_state = {
                        'pot_total': getattr(snapshot.exposure, 'pot_total', 0),
                        'pot_max': getattr(snapshot.exposure, 'pot_max', 0),
                    }
        
        # Get Max Exposure from Port Adjuster (single source of truth)
        try:
            from app.port_adjuster.port_adjuster_store import get_port_adjuster_store
            pa_store = get_port_adjuster_store()
            pa_config = pa_store.get_config()
            if pa_config:
                max_exposure_from_pa = pa_config.total_exposure_usd
                if account_state is None:
                    account_state = {}
                account_state['limit_max_exposure'] = max_exposure_from_pa
                account_state['pot_max'] = max_exposure_from_pa  # Override with PA value
                logger.debug(f"[JFIN STATE] Max exposure from Port Adjuster: ${max_exposure_from_pa:,.0f}")
        except Exception as e:
            logger.warning(f"[JFIN STATE] Could not get Port Adjuster config: {e}")
        
        state['account_state'] = account_state
        
        return {
            "success": True,
            "is_empty": False,
            "state": state,
            "percentage": state.get("percentage", 50)
        }
        
    except Exception as e:
        logger.error(f"[JFIN STATE] Error fetching JFIN state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jfin/update-percentage")
async def update_jfin_percentage(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update JFIN percentage and recalculate lots.
    
    Args:
        request: {"percentage": 25|50|75|100}
    
    Returns:
        Updated JFIN state
    """
    from app.core.redis_client import get_redis_client
    from app.psfalgo.jfin_engine import get_jfin_engine
    import json
    
    try:
        percentage = request.get("percentage")
        if percentage not in [25, 50, 75, 100]:
            raise HTTPException(status_code=400, detail="Percentage must be 25, 50, 75, or 100")
        
        redis = get_redis_client().sync
        
        # Get current state
        state_json = redis.get("psfalgo:jfin:current_state")
        if not state_json:
            raise HTTPException(status_code=404, detail="JFIN state not found. Run RUNALL first.")
        
        state = json.loads(state_json)
        
        # Update percentage
        state["percentage"] = percentage
        
        # Recalculate lots for each pool based on new percentage
        engine = get_jfin_engine()
        if engine:
            engine.config.jfin_percentage = percentage
            
            # Recalculate lots (apply percentage scaling)
            for pool_key in ["bb_stocks", "fb_stocks", "sas_stocks", "sfs_stocks"]:
                if pool_key in state and state[pool_key]:
                    for stock in state[pool_key]:
                        if "calculated_lot" in stock:
                            # Scale lot by percentage
                            stock["final_lot"] = int(stock["calculated_lot"] * (percentage / 100))
                            # Round to lot_rounding (default 100)
                            lot_rounding = engine.config.lot_rounding
                            stock["final_lot"] = (stock["final_lot"] // lot_rounding) * lot_rounding
                            # Min lot check
                            if stock["final_lot"] < engine.config.min_lot_per_order:
                                stock["final_lot"] = 0
        
        # Save updated state
        redis.setex("psfalgo:jfin:current_state", 3600, json.dumps(state))
        
        return {
            "success": True,
            "percentage": percentage,
            "state": state
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[JFIN STATE] Error updating percentage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ADDNEWPOS FILTERS (Save/Load)
# ============================================================================

@router.get("/addnewpos/filters")
async def get_addnewpos_filters() -> Dict[str, Any]:
    """
    Get saved ADDNEWPOS filters (Fbtot, SFStot, GORT, SMA min/max).
    
    Returns:
        Saved filter configuration
    """
    from app.core.redis_client import get_redis_client
    import json
    
    try:
        redis = get_redis_client().sync
        
        filters_json = redis.get("psfalgo:addnewpos:filters")
        
        if not filters_json:
            return {
                "success": True,
                "filters": None,
                "message": "No saved filters found"
            }
        
        filters = json.loads(filters_json)
        
        return {
            "success": True,
            "filters": filters
        }
        
    except Exception as e:
        logger.error(f"[ADDNEWPOS FILTERS] Error getting filters: {e}", exc_info=True)
        return {
            "success": False,
            "filters": None,
            "error": str(e)
        }


@router.post("/addnewpos/filters")
async def save_addnewpos_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save ADDNEWPOS filters (Fbtot, SFStot, GORT, SMA min/max).
    
    Args:
        filters: Filter configuration dict with keys like fbtot_min, fbtot_max, etc.
    
    Returns:
        Result dict
    """
    from app.core.redis_client import get_redis_client
    import json
    
    try:
        redis = get_redis_client().sync
        
        # Validate filter keys
        valid_keys = {
            'fbtot_min', 'fbtot_max', 
            'sfstot_min', 'sfstot_max',
            'gort_min', 'gort_max',
            'sma63_min', 'sma63_max',
            'sma246_min', 'sma246_max'
        }
        
        # Filter only valid keys
        clean_filters = {k: v for k, v in filters.items() if k in valid_keys}
        
        # Save to Redis (no expiry - persistent)
        redis.set("psfalgo:addnewpos:filters", json.dumps(clean_filters))
        
        logger.info(f"[ADDNEWPOS FILTERS] Saved filters: {clean_filters}")
        
        return {
            "success": True,
            "message": "Filters saved successfully",
            "filters": clean_filters
        }
        
    except Exception as e:
        logger.error(f"[ADDNEWPOS FILTERS] Error saving filters: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }



# ============================================================================
# DASHBOARD SUMMARY (Phase 8)
# ============================================================================

@router.get("/dashboard/summary")
async def get_dashboard_summary() -> Dict[str, Any]:
    """
    Get dashboard summary (single call for UI).
    
    Returns:
        Summary with state, cycle info, decision counts, proposals, and data readiness
    """
    from app.psfalgo.runall_state_api import get_runall_state_api
    from app.psfalgo.proposal_store import get_proposal_store
    from app.psfalgo.data_readiness_checker import get_data_readiness_checker, initialize_data_readiness_checker
    
    # Get RUNALL state
    state_api = get_runall_state_api()
    state_snapshot = state_api.get_state_snapshot() if state_api else None
    
    # Get last cycle decisions
    last_karbotu = state_api.get_decision_snapshot('KARBOTU') if state_api else None
    last_reducemore = state_api.get_decision_snapshot('REDUCEMORE') if state_api else None
    last_addnewpos = state_api.get_decision_snapshot('ADDNEWPOS') if state_api else None
    
    # Get recent proposals
    proposal_store = get_proposal_store()
    recent_proposals = []
    if proposal_store:
        latest = proposal_store.get_latest_proposals(limit=5)
        for prop in latest:
            recent_proposals.append({
                'symbol': prop.symbol,
                'side': prop.side,
                'qty': prop.qty,
                'proposed_price': prop.proposed_price,
                'bid': prop.bid,
                'ask': prop.ask,
                'last': prop.last,
                'reason': prop.reason[:100] if prop.reason else '',  # First 100 chars
                'confidence': prop.confidence,
                'engine': prop.engine,
                'warnings': prop.warnings if hasattr(prop, 'warnings') else []
            })
    
    # Get data readiness summary
    checker = get_data_readiness_checker()
    if not checker:
        initialize_data_readiness_checker()
        checker = get_data_readiness_checker()
    
    scanner_ready_counts = {}
    if checker:
        readiness_report = checker.check_data_readiness()
        scanner_ready_counts = {
            'total_symbols': readiness_report.get('total_symbols', 0),
            'symbols_with_live_prices': readiness_report.get('symbols_with_live_prices', 0),
            'symbols_with_prev_close': readiness_report.get('symbols_with_prev_close', 0),
            'symbols_with_fbtot': readiness_report.get('symbols_with_fbtot', 0),
            'symbols_with_gort': readiness_report.get('symbols_with_gort', 0),
            'symbols_with_sma63': readiness_report.get('symbols_with_sma63', 0)
        }
    
    return {
        'success': True,
        'state': state_snapshot.global_state if state_snapshot else 'IDLE',
        'last_cycle_id': state_snapshot.cycle_id if state_snapshot else 0,
        'last_decision_counts': {
            'karbotu': last_karbotu.total_decisions if last_karbotu else 0,
            'reducemore': last_reducemore.total_decisions if last_reducemore else 0,
            'addnewpos': last_addnewpos.total_decisions if last_addnewpos else 0
        },
        'last_proposals_count': len(recent_proposals),
        'top5_recent_proposals': recent_proposals,
        'scanner_ready_counts': scanner_ready_counts
    }


# ============================================================================
# TRADER MODE (Human-First UI) - Phase 9
# ============================================================================

@router.get("/trader/proposals")
async def get_trader_proposals(
    sort_by: Optional[str] = None,
    sort_desc: bool = True,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get proposals for trader view (PROPOSED only).
    
    Args:
        sort_by: Sort by field (confidence, spread_percent, engine, decision_ts)
        sort_desc: Sort descending (default: True)
        limit: Maximum number of proposals (default: 100, max: 500)
    
    Returns:
        List of PROPOSED proposals in table format
    """
    from app.psfalgo.proposal_store import get_proposal_store
    from app.psfalgo.proposal_explainer import get_proposal_explainer, initialize_proposal_explainer
    
    proposal_store = get_proposal_store()
    if not proposal_store:
        return {
            'success': True,
            'count': 0,
            'proposals': []
        }
    
    # Get only PROPOSED proposals
    proposals = proposal_store.get_all_proposals(status='PROPOSED', limit=limit)
    
    # Sort
    if sort_by:
        reverse = sort_desc
        try:
            if sort_by == 'confidence':
                proposals.sort(key=lambda p: p.confidence or 0, reverse=reverse)
            elif sort_by == 'spread_percent':
                proposals.sort(key=lambda p: p.spread_percent or 0, reverse=reverse)
            elif sort_by == 'engine':
                proposals.sort(key=lambda p: p.engine, reverse=reverse)
            elif sort_by == 'decision_ts':
                proposals.sort(key=lambda p: p.decision_ts, reverse=reverse)
        except Exception as e:
            logger.warning(f"Error sorting by {sort_by}: {e}")
    
    # Limit
    limit = min(limit, 500)  # Cap at 500
    proposals = proposals[:limit]
    
    # Format for trader view
    trader_proposals = []
    explainer = get_proposal_explainer()
    if not explainer:
        initialize_proposal_explainer()
        explainer = get_proposal_explainer()
    
    for proposal in proposals:
        # Get explanation
        explanation = {}
        if explainer:
            explanation = explainer.explain_proposal(proposal)
        
        # Get proposal ID from store
        proposal_id = proposal_store.get_proposal_id(proposal)
        
        trader_proposals.append({
            'proposal_id': proposal_id,
            'symbol': proposal.symbol,
            'engine': proposal.engine,
            'action': f"{proposal.side} {proposal.qty}",
            'qty': proposal.qty,
            'proposed_price': proposal.proposed_price,
            'order_type': proposal.order_type,
            'bid': proposal.bid,
            'ask': proposal.ask,
            'last': proposal.last,
            'spread': proposal.spread,
            'spread_percent': proposal.spread_percent,
            'fbtot': proposal.metrics_used.get('fbtot'),
            'gort': proposal.metrics_used.get('gort'),
            'sma63_chg': proposal.metrics_used.get('sma63_chg'),
            'reason': proposal.reason,
            'confidence': proposal.confidence,
            'warnings': proposal.warnings if hasattr(proposal, 'warnings') else [],
            'decision_ts': proposal.decision_ts.isoformat(),
            'cycle_id': proposal.cycle_id,
            'explanation': explanation
        })

    trader_proposals = _enrich_proposals_with_live_l1(trader_proposals)
    return {
        'success': True,
        'count': len(trader_proposals),
        'proposals': trader_proposals
    }


@router.get("/trader/proposals/{proposal_id}/explain")
async def explain_proposal(proposal_id: str) -> Dict[str, Any]:
    """
    Get detailed "Why This Trade?" explanation for a proposal.
    
    Args:
        proposal_id: Proposal ID
    
    Returns:
        Detailed explanation
    """
    from app.psfalgo.proposal_store import get_proposal_store
    from app.psfalgo.proposal_explainer import get_proposal_explainer, initialize_proposal_explainer
    
    proposal_store = get_proposal_store()
    if not proposal_store:
        raise HTTPException(status_code=503, detail="ProposalStore not initialized")
    
    proposal = proposal_store.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    
    explainer = get_proposal_explainer()
    if not explainer:
        initialize_proposal_explainer()
        explainer = get_proposal_explainer()
    
    if not explainer:
        raise HTTPException(status_code=503, detail="ProposalExplainer not initialized")
    
    explanation = explainer.explain_proposal(proposal)
    
    return {
        'success': True,
        'proposal_id': proposal_id,
        'symbol': proposal.symbol,
        'explanation': explanation
    }


@router.post("/trader/proposals/{proposal_id}/accept")
async def trader_accept_proposal(
    proposal_id: str,
    trader_note: Optional[str] = None
) -> Dict[str, Any]:
    """
    Accept proposal (HUMAN_ONLY mode - logging only, no execution).
    
    Args:
        proposal_id: Proposal ID
        trader_note: Optional trader note
    
    Returns:
        Result dict
    """
    from app.psfalgo.trader_mode import get_trader_mode_manager, initialize_trader_mode_manager
    
    manager = get_trader_mode_manager()
    if not manager:
        initialize_trader_mode_manager()
        manager = get_trader_mode_manager()
    
    if not manager:
        raise HTTPException(status_code=503, detail="TraderModeManager not initialized")
    
    result = manager.accept_proposal(proposal_id, trader_note=trader_note)
    
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to accept proposal'))
    
    return result


@router.post("/trader/proposals/{proposal_id}/reject")
async def trader_reject_proposal(
    proposal_id: str,
    trader_note: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reject proposal (HUMAN_ONLY mode - logging only).
    
    Args:
        proposal_id: Proposal ID
        trader_note: Optional trader note (why rejected)
    
    Returns:
        Result dict
    """
    from app.psfalgo.trader_mode import get_trader_mode_manager, initialize_trader_mode_manager
    
    manager = get_trader_mode_manager()
    if not manager:
        initialize_trader_mode_manager()
        manager = get_trader_mode_manager()
    
    if not manager:
        raise HTTPException(status_code=503, detail="TraderModeManager not initialized")
    
    result = manager.reject_proposal(proposal_id, trader_note=trader_note)
    
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to reject proposal'))
    
    return result


@router.get("/trader/daily-summary")
async def get_daily_trader_summary(session_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Get daily trader summary.
    
    Args:
        session_date: Date (YYYY-MM-DD), if None uses today
    
    Returns:
        Daily summary report
    """
    from app.psfalgo.trader_mode import get_trader_mode_manager, initialize_trader_mode_manager
    
    manager = get_trader_mode_manager()
    if not manager:
        initialize_trader_mode_manager()
        manager = get_trader_mode_manager()
    
    if not manager:
        raise HTTPException(status_code=503, detail="TraderModeManager not initialized")
    
    result = manager.generate_daily_summary(session_date=session_date)
    
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to generate daily summary'))
    
    return result


@router.post("/trader/expire-old")
async def expire_old_proposals() -> Dict[str, Any]:
    """
    Expire old proposals (older than expiry time).
    
    Returns:
        Result dict with expired count
    """
    from app.psfalgo.trader_mode import get_trader_mode_manager, initialize_trader_mode_manager
    
    manager = get_trader_mode_manager()
    if not manager:
        initialize_trader_mode_manager()
        manager = get_trader_mode_manager()
    
    if not manager:
        raise HTTPException(status_code=503, detail="TraderModeManager not initialized")
    
    expired_count = manager.expire_old_proposals()
    
    return {
        'success': True,
        'expired_count': expired_count
    }


# ============================================================================
# ACCOUNT MODE & CONNECTOR (Phase 10)
# ============================================================================

@router.get("/account/mode")
async def get_account_mode() -> Dict[str, Any]:
    """
    Get current account mode.
    
    Returns:
        Current account mode info including IBKR connection status
    """
    try:
        from app.psfalgo.account_mode import get_account_mode_manager
        
        manager = get_account_mode_manager()
        if not manager:
            # Return default instead of error
            return {
                'success': True,
                'mode': 'HAMMER_PRO',
                'is_hammer': True,
                'is_ibkr_gun': False,
                'is_ibkr_ped': False,
                'is_ibkr': False,
                'ibkr_gun_connected': False,
                'ibkr_ped_connected': False,
                'warning': 'AccountModeManager not initialized, using default HAMMER_PRO'
            }
        
        # Get actual IBKR connection status from DualConnectionManager
        ibkr_gun_connected = False
        ibkr_ped_connected = False
        try:
            from app.psfalgo.dual_connection_manager import get_dual_connection_manager
            dual_mgr = get_dual_connection_manager()
            if dual_mgr:
                ibkr_gun_connected = dual_mgr.is_account_connected('IBKR_GUN')
                ibkr_ped_connected = dual_mgr.is_account_connected('IBKR_PED')
            else:
                # Fallback: check connectors directly
                from app.psfalgo.ibkr_connector import get_ibkr_connector
                gun_conn = get_ibkr_connector(account_type='IBKR_GUN', create_if_missing=False)
                ped_conn = get_ibkr_connector(account_type='IBKR_PED', create_if_missing=False)
                ibkr_gun_connected = gun_conn.is_connected() if gun_conn else False
                ibkr_ped_connected = ped_conn.is_connected() if ped_conn else False
        except Exception as conn_err:
            logger.debug(f"Could not check IBKR connection status: {conn_err}")
        
        return {
            'success': True,
            'mode': manager.get_mode(),
            'is_hammer': manager.is_hammer(),
            'is_ibkr_gun': manager.is_ibkr_gun(),
            'is_ibkr_ped': manager.is_ibkr_ped(),
            'is_ibkr': manager.is_ibkr(),
            'ibkr_gun_connected': ibkr_gun_connected,
            'ibkr_ped_connected': ibkr_ped_connected
        }
    except Exception as e:
        logger.error(f"Error getting account mode: {e}", exc_info=True)
        # Return default instead of raising exception
        return {
            'success': True,
            'mode': 'HAMMER_PRO',
            'is_hammer': True,
            'is_ibkr_gun': False,
            'is_ibkr_ped': False,
            'is_ibkr': False,
            'ibkr_gun_connected': False,
            'ibkr_ped_connected': False,
            'error': str(e)
        }


@router.post("/account/mode")
async def set_account_mode(
    mode: str = Query(..., description="Account mode (HAMMER_PRO, IBKR_GUN, IBKR_PED)"),
    auto_connect: bool = Query(True, description="Auto-connect IBKR if mode is IBKR")
) -> Dict[str, Any]:
    """
    Set account mode and optionally auto-connect/disconnect.
    
    PHASE 10.1: Auto-connects to IBKR when mode is IBKR_GUN or IBKR_PED.
    Auto-disconnects IBKR when mode is HAMMER_PRO.
    
    Args:
        mode: Account mode (HAMMER_PRO, IBKR_GUN, IBKR_PED) - query parameter
        auto_connect: Auto-connect IBKR if mode is IBKR (default: True) - query parameter
    
    Returns:
        Result dict with connection status
    """
    try:
        from app.psfalgo.account_mode import get_account_mode_manager
        
        manager = get_account_mode_manager()
        if not manager:
            return {
                'success': False,
                'error': 'AccountModeManager not initialized'
            }
        
        result = await manager.set_mode(mode, auto_connect=auto_connect)

        # CRITICAL FIX: Also update TradingAccountContext for trading_routes compatibility
        try:
            from app.trading.trading_account_context import get_trading_context, TradingAccountMode
            trading_context = get_trading_context()
            
            # Map string to Enum
            enum_mode = None
            if mode == "HAMMER_PRO":
                enum_mode = TradingAccountMode.HAMPRO
            elif mode == "IBKR_GUN":
                enum_mode = TradingAccountMode.IBKR_GUN
            elif mode == "IBKR_PED":
                enum_mode = TradingAccountMode.IBKR_PED
                
            if enum_mode:
                trading_context.set_trading_mode(enum_mode)
                logger.info(f"[PSFALGO_ROUTES] Synced TradingAccountContext to {enum_mode}")
        except Exception as sync_err:
             logger.error(f"[PSFALGO_ROUTES] Failed to sync TradingAccountContext: {sync_err}")
        
        # Mark that account has been selected by user
        try:
            from app.core.redis_client import get_redis
            redis = get_redis()
            if redis:
                redis.set("psfalgo:account_selected", "true", ex=86400)  # 24 hours expiry
                logger.info(f"[PSFALGO_ROUTES] ✅ Account selection flag set in Redis")
        except Exception as redis_err:
            logger.warning(f"[PSFALGO_ROUTES] Failed to set account selection flag: {redis_err}")
        
        # Start Runall Engine when account is selected (if not already running)
        try:
            from app.psfalgo.runall_engine import get_runall_engine
            runall_engine = get_runall_engine()
            if runall_engine and not runall_engine.loop_running:
                logger.info(f"[PSFALGO_ROUTES] 🚀 Starting Runall Engine (account selected: {mode})")
                await runall_engine.start()
        except Exception as start_err:
            logger.error(f"[PSFALGO_ROUTES] Failed to start Runall Engine: {start_err}")
        
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to set account mode'))
        
        return result
    except Exception as e:
        logger.error(f"Error setting account mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/account/hammer/connect")
async def connect_hammer() -> Dict[str, Any]:
    """
    Connect to Hammer Pro and automatically create befham.csv if successful.
    
    Returns:
        Connection status and BEFDAY tracking result
    """
    try:
        from app.api.market_data_routes import get_hammer_client
        from app.psfalgo.befday_tracker import get_befday_tracker, track_befday_positions
        from app.api.trading_routes import get_hammer_positions_service
        
        hammer_client = get_hammer_client()
        if not hammer_client:
            return {
                'success': True,  # Return success with warning
                'connected': False,
                'message': 'Hammer client not initialized'
            }
        
        # Check if already connected — still proceed to BEFDAY tracking!
        already_connected = hammer_client.is_connected()
        
        if already_connected:
            logger.info("[HAMMER_API] Already connected to Hammer Pro, checking BEFDAY...")
            # Don't return early! Fall through to BEFDAY tracking below.
        
        if not already_connected:
            # Connect to Hammer Pro
            logger.info("[HAMMER_API] Connecting to Hammer Pro...")
            try:
                connected = hammer_client.connect()
            except Exception as connect_err:
                logger.error(f"Error during Hammer connect: {connect_err}", exc_info=True)
                return {
                    'success': True,  # Return success with error message
                    'connected': False,
                    'message': f'Connection error: {str(connect_err)}'
                }
            
            if not connected:
                return {
                    'success': True,  # Return success with error message
                    'connected': False,
                    'message': 'Failed to connect to Hammer Pro. Check if Hammer Pro is running.'
                }
            
            # Wait a bit for authentication
            import asyncio
            await asyncio.sleep(2)
            
            if not hammer_client.is_authenticated():
                return {
                    'success': True,  # Return success with error message
                    'connected': False,
                    'message': 'Connected but authentication failed. Check password.'
                }
            
            # Connection successful - mark account as open for recovery (en az 1 hesap açık bekle)
            from app.core.redis_client import get_redis_client
            try:
                r = get_redis_client()
                if r and r.sync:
                    r.sync.set("psfalgo:recovery:account_open", "HAMPRO")
            except Exception as _:
                pass
        
        logger.info("[HAMMER_API] Proceeding with BEFDAY tracking...")
        
        try:
            # Get positions from Hammer
            positions_service = get_hammer_positions_service()
            if positions_service:
                positions = positions_service.get_positions()
                
                if positions:
                    # Convert to BEFDAY format
                    befday_positions = []
                    for pos in positions:
                        befday_positions.append({
                            'symbol': pos.get('symbol', ''),
                            'qty': pos.get('qty', 0),
                            'quantity': pos.get('qty', 0),
                            'avg_cost': pos.get('avg_cost', pos.get('avg_price', 0)),
                            'market_value': pos.get('market_value', 0),
                            'unrealized_pnl': pos.get('unrealized_pnl', 0),
                            'realized_pnl': pos.get('realized_pnl', 0),
                            'last_price': pos.get('last_price', 0),
                            'exchange': pos.get('exchange', ''),
                            'account': pos.get('account', '')
                        })
                    
                    # BEFDAY — GUNDE 1 KEZ, İLK TIKLAMADA ÇEK, ASLA OVERWRITE ETME!
                    import os
                    from pathlib import Path
                    from datetime import datetime as dt_cls, date as date_cls
                    
                    befham_path = Path("C:/StockTracker/befham.csv")
                    needs_befday = False
                    
                    # CHECK 1: Redis key already exists for TODAY?
                    # ═══════════════════════════════════════════════════════
                    # CRITICAL FIX: Check companion date key to ensure the
                    # Redis data is from TODAY, not yesterday (24h TTL issue)
                    # ═══════════════════════════════════════════════════════
                    redis_befday_exists = False
                    try:
                        from app.core.redis_client import get_redis_client
                        r = get_redis_client()
                        if r and r.sync:
                            existing_redis = r.sync.get("psfalgo:befday:positions:HAMPRO")
                            if existing_redis:
                                # Verify date key matches today
                                stored_date = r.sync.get("psfalgo:befday:date:HAMPRO")
                                stored_date_str = stored_date.decode() if isinstance(stored_date, bytes) else stored_date if stored_date else None
                                today_str = date_cls.today().strftime("%Y%m%d")
                                if stored_date_str == today_str:
                                    redis_befday_exists = True
                                    logger.info("[HAMMER_API] ℹ️ BEFDAY Redis key zaten mevcut (today's date matches) — ASLA üzerine yazılmayacak")
                                else:
                                    # Stale key from yesterday — delete it
                                    r.sync.delete("psfalgo:befday:positions:HAMPRO")
                                    r.sync.delete("psfalgo:befday:date:HAMPRO")
                                    logger.warning(f"[HAMMER_API] 🗑️ Deleted STALE Redis BEFDAY key: stored_date={stored_date_str}, today={today_str}")
                    except Exception:
                        pass
                    
                    # CHECK 2: CSV file exists for today?
                    csv_today_exists = False
                    if befham_path.exists():
                        old_mtime = os.path.getmtime(befham_path)
                        old_date = dt_cls.fromtimestamp(old_mtime).date()
                        if old_date == date_cls.today():
                            csv_today_exists = True
                            logger.info("[HAMMER_API] ℹ️ befham.csv bugün zaten mevcut — BEFDAY atlanıyor")
                        else:
                            # Dünden kalan eski CSV → sil (ama Redis'i SİLME!)
                            logger.info(f"[HAMMER_API] 🗑️ Stale befham.csv siliniyor (from {old_date})")
                            os.remove(befham_path)
                    
                    # KURAL: Eğer Redis VEYA CSV bugün için varsa → BEFDAY YAZILMAZ
                    if redis_befday_exists or csv_today_exists:
                        needs_befday = False
                        logger.info("[HAMMER_API] BEFDAY bugün zaten alınmış — tekrar yazılmayacak (SACRED)")
                    elif not befham_path.exists():
                        needs_befday = True
                        logger.info("[HAMMER_API] BEFDAY ilk kez oluşturulacak (ne CSV ne Redis mevcut)")
                    
                    befday_tracked = False
                    if needs_befday:
                        # Redis stale veriyi temizle (SADECE yeni gün için, ve SADECE kayıt yoksa)
                        try:
                            from app.core.redis_client import get_redis_client
                            r = get_redis_client()
                            if r and r.sync:
                                # Eğer Redis'te eski günün datası varsa temizle
                                existing = r.sync.get("psfalgo:befday:positions:HAMPRO")
                                if not existing:
                                    logger.info("[HAMMER_API] Redis'te BEFDAY yok, yeni yazılacak")
                                else:
                                    # Redis key var ama CSV yoktu → Redis eski günden olabilir
                                    # Ama redis_befday_exists = True olsaydı buraya girmezdik
                                    # Yani burada Redis stale → temizleyebiliriz
                                    r.sync.delete("psfalgo:befday:positions:HAMPRO")
                                    logger.info("[HAMMER_API] Stale Redis BEFDAY temizlendi (yeni gün)")
                        except Exception:
                            pass
                        
                        # Tracker flag'ini resetle
                        tracker = get_befday_tracker()
                        if tracker:
                            tracker._checked_today['hampro'] = False
                        
                        # Şimdi track et — CSV silindi + flag reset = başarılı olacak
                        befday_tracked = await track_befday_positions(
                            positions=befday_positions,
                            mode='hampro',
                            account='HAMPRO'
                        )
                        
                        if befday_tracked:
                            logger.info(f"[HAMMER_API] ✅ BEFDAY tracked: {len(befday_positions)} positions → befham.csv")
                            # ALSO write to Redis psfalgo:befday:positions:HAMPRO (for terminals)
                            try:
                                import json as _json
                                r3 = get_redis_client()
                                if r3 and r3.sync:
                                    befday_redis_list = [{"symbol": bp.get('symbol',''), "qty": float(bp.get('qty',0)),
                                                          "avg_cost": bp.get('avg_cost', 0)} for bp in befday_positions if bp.get('symbol')]
                                    r3.sync.set("psfalgo:befday:positions:HAMPRO", _json.dumps(befday_redis_list), ex=86400)
                                    r3.sync.set("psfalgo:befday:date:HAMPRO", date_cls.today().strftime("%Y%m%d"), ex=86400)
                                    logger.info(f"[HAMMER_API] ✅ BEFDAY Redis written: {len(befday_redis_list)} entries + date key (first & only write of the day)")
                            except Exception as re3:
                                logger.warning(f"[HAMMER_API] Redis BEFDAY write failed: {re3}")
                        else:
                            # FALLBACK: Tracker failed — write befham.csv DIRECTLY
                            logger.warning("[HAMMER_API] ⚠️ Tracker failed, writing befham.csv directly as fallback...")
                            try:
                                import pandas as pd
                                import json as _json
                                rows = []
                                for bp in befday_positions:
                                    sym = bp.get('symbol', '')
                                    qty = float(bp.get('qty', 0))
                                    side = "Short" if qty < 0 else "Long"
                                    ptype = "SHORT" if qty < 0 else "LONG"
                                    rows.append({
                                        'Symbol': sym,
                                        'Quantity': qty,
                                        'Avg_Cost': bp.get('avg_cost', 0),
                                        'Position_Type': ptype,
                                        'Side': side,
                                        'Book': 'LT',
                                        'Strategy': 'LT',
                                        'Origin': 'OV',
                                        'Full_Taxonomy': f"LT OV {side}",
                                        'Account': 'HAMPRO',
                                        'Last_Price': bp.get('last_price', 0),
                                        'Exchange': bp.get('exchange', ''),
                                    })
                                df = pd.DataFrame(rows)
                                df.to_csv(befham_path, index=False, encoding='utf-8-sig')
                                logger.info(f"[HAMMER_API] ✅ FALLBACK befham.csv written: {len(rows)} positions")
                                befday_tracked = True
                                
                                # Also write to Redis BEFDAY cache (ONLY since this is first write)
                                try:
                                    from app.core.redis_client import get_redis_client
                                    r2 = get_redis_client()
                                    if r2:
                                        befday_list = [{"symbol": bp.get('symbol',''), "qty": float(bp.get('qty',0)),
                                                        "avg_cost": bp.get('avg_cost', 0)} for bp in befday_positions if bp.get('symbol')]
                                        r2.set("psfalgo:befday:positions:HAMPRO", _json.dumps(befday_list), ex=86400)
                                        r2.set("psfalgo:befday:date:HAMPRO", date_cls.today().strftime("%Y%m%d"), ex=86400)
                                        logger.info(f"[HAMMER_API] ✅ FALLBACK Redis BEFDAY written: {len(befday_list)} entries + date key")
                                except Exception as re2:
                                    logger.warning(f"[HAMMER_API] Redis fallback write failed: {re2}")
                                    
                            except Exception as fb_err:
                                logger.error(f"[HAMMER_API] ❌ FALLBACK befham.csv write ALSO failed: {fb_err}")
                    else:
                        logger.info("[HAMMER_API] BEFDAY zaten bugün alınmış, tekrar çekilmiyor")
                    
                    # CRITICAL: Trigger position snapshot to write to Redis (for RevnBookCheck terminal)
                    try:
                        from app.psfalgo.position_snapshot_api import get_position_snapshot_api, initialize_position_snapshot_api
                        pos_api = get_position_snapshot_api()
                        if not pos_api:
                            initialize_position_snapshot_api()
                            pos_api = get_position_snapshot_api()
                        if pos_api:
                            await pos_api.get_position_snapshot(account_id="HAMPRO", include_zero_positions=False)
                            logger.info("[HAMMER_API] ✅ Position snapshot written to Redis for RevnBookCheck")
                    except Exception as snap_err:
                        logger.warning(f"[HAMMER_API] Position snapshot to Redis failed: {snap_err}")
                    
                    return {
                        'success': True,
                        'connected': True,
                        'authenticated': True,
                        'befday_tracked': befday_tracked,
                        'positions_count': len(befday_positions),
                        'message': f'Connected to Hammer Pro. BEFDAY: {"tracked" if befday_tracked else "skipped (already tracked today)"}'
                    }
                else:
                    logger.warning("[HAMMER_API] No positions found")
                    return {
                        'success': True,
                        'connected': True,
                        'authenticated': True,
                        'befday_tracked': False,
                        'positions_count': 0,
                        'message': 'Connected to Hammer Pro but no positions found'
                    }
            else:
                logger.warning("[HAMMER_API] Positions service not available")
                return {
                    'success': True,
                    'connected': True,
                    'authenticated': True,
                    'befday_tracked': False,
                    'message': 'Connected to Hammer Pro but positions service not available'
                }
        except Exception as e:
            logger.error(f"[HAMMER_API] Error tracking BEFDAY: {e}", exc_info=True)
            return {
                'success': True,
                'connected': True,
                'authenticated': True,
                'befday_tracked': False,
                'error': f'Connected but BEFDAY tracking failed: {str(e)}'
            }
        
    except Exception as e:
        logger.error(f"[HAMMER_API] Error connecting to Hammer Pro: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


@router.post("/account/hammer/disconnect")
async def disconnect_hammer() -> Dict[str, Any]:
    """
    Disconnect from Hammer Pro.
    
    Returns:
        Disconnection status
    """
    try:
        from app.api.market_data_routes import get_hammer_client
        
        hammer_client = get_hammer_client()
        if not hammer_client:
            return {
                'success': False,
                'error': 'Hammer client not initialized'
            }
        
        if not hammer_client.is_connected():
            return {
                'success': True,
                'disconnected': False,
                'message': 'Not connected to Hammer Pro'
            }
        
        # Disconnect
        hammer_client.disconnect()
        try:
            from app.core.redis_client import get_redis_client
            r = get_redis_client()
            cur = r.sync.get("psfalgo:recovery:account_open")
            if cur and (cur.decode() if isinstance(cur, bytes) else cur) == "HAMPRO":
                r.sync.delete("psfalgo:recovery:account_open")
        except Exception:
            pass
        logger.info("[HAMMER_API] Disconnected from Hammer Pro")
        
        return {
            'success': True,
            'disconnected': True,
            'message': 'Disconnected from Hammer Pro'
        }
        
    except Exception as e:
        logger.error(f"[HAMMER_API] Error disconnecting from Hammer Pro: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


@router.get("/account/hammer/status")
async def get_hammer_status() -> Dict[str, Any]:
    """
    Get Hammer Pro connection status.
    
    Returns:
        Connection status
    """
    try:
        from app.api.market_data_routes import get_hammer_client
        
        hammer_client = get_hammer_client()
        if not hammer_client:
            return {
                'success': True,  # Return success with status
                'connected': False,
                'authenticated': False,
                'message': 'Hammer client not initialized'
            }
        
        return {
            'success': True,
            'connected': hammer_client.is_connected(),
            'authenticated': hammer_client.is_authenticated() if hammer_client.is_connected() else False
        }
        
    except Exception as e:
        logger.error(f"[HAMMER_API] Error getting Hammer status: {e}", exc_info=True)
        return {
            'success': True,  # Return success with error message
            'connected': False,
            'authenticated': False,
            'message': str(e)
        }


@router.post("/account/ibkr/connect")
async def connect_ibkr(
    account_type: str = "IBKR_GUN",
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    client_id: int = 1
) -> Dict[str, Any]:
    """
    Connect to IBKR Gateway / TWS.
    
    PHASE 10.1: Same port for both GUN and PED (like Janall).
    Account distinction is done via account field filtering.
    
    Args:
        account_type: IBKR_GUN or IBKR_PED
        host: IBKR Gateway / TWS host (default: 127.0.0.1)
        port: Port number (default: 4001 for Gateway, 7497 for TWS - same for both)
        client_id: Client ID (default: 1)
    
    Returns:
        Connection result
    """
    from app.psfalgo.ibkr_connector import get_ibkr_connector, connect_isolated_sync
    import asyncio

    if account_type not in ["IBKR_GUN", "IBKR_PED"]:
        raise HTTPException(status_code=400, detail="Invalid account_type. Must be IBKR_GUN or IBKR_PED")

    # PHASE 10.1: Default port if not provided (same for both GUN and PED)
    if port is None:
        port = 4001  # Default Gateway port

    # CRITICAL: Use connect_isolated_sync in a thread to avoid FastAPI event loop conflicts
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: connect_isolated_sync(account_type=account_type, host=host, port=port, client_id=client_id)
    )

    connector = get_ibkr_connector(account_type=account_type)
    
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to connect to IBKR'))
    
    # Connection successful - mark account as open for recovery (en az 1 hesap açık bekle)
    if result.get('connected'):
        try:
            from app.core.redis_client import get_redis_client
            r = get_redis_client()
            if r and r.sync:
                r.sync.set("psfalgo:recovery:account_open", account_type)
        except Exception:
            pass
    
    # Track BEFDAY positions (günde 1 kez)
    if result.get('connected'):
        logger.info(f"[IBKR_API] Connection successful, tracking BEFDAY positions for {account_type}...")
        
        try:
            # Get positions from IBKR
            positions = await connector.get_positions()
            
            if positions:
                # Convert to BEFDAY format
                befday_positions = []
                for pos in positions:
                    befday_positions.append({
                        'symbol': pos.get('symbol', ''),
                        'qty': pos.get('qty', 0),
                        'quantity': pos.get('qty', 0),
                        'avg_cost': pos.get('avg_cost', pos.get('avg_price', 0)),
                        'market_value': pos.get('market_value', 0),
                        'unrealized_pnl': pos.get('unrealized_pnl', 0),
                        'realized_pnl': pos.get('realized_pnl', 0),
                        'last_price': pos.get('last_price', 0),
                        'exchange': pos.get('exchange', ''),
                        'account': pos.get('account', account_type)
                    })
                
                # Track BEFDAY (günde 1 kez)
                from app.psfalgo.befday_tracker import track_befday_positions
                
                mode = 'ibkr_gun' if account_type == 'IBKR_GUN' else 'ibkr_ped'
                befday_tracked = await track_befday_positions(
                    positions=befday_positions,
                    mode=mode,
                    account=account_type
                )
                
                if befday_tracked:
                    logger.info(f"[IBKR_API] ✅ BEFDAY tracked: {len(befday_positions)} positions saved to bef{'ibgun' if account_type == 'IBKR_GUN' else 'ibped'}.csv")
                else:
                    logger.info(f"[IBKR_API] ℹ️ BEFDAY already tracked today or outside window")
                
                result['befday_tracked'] = befday_tracked
                result['positions_count'] = len(befday_positions)
                result['message'] = f'Connected to {account_type}. BEFDAY: {"tracked" if befday_tracked else "skipped (already tracked today)"}'
            else:
                logger.warning(f"[IBKR_API] No positions found for {account_type}")
                result['befday_tracked'] = False
                result['positions_count'] = 0
                result['message'] = f'Connected to {account_type} but no positions found'
        except Exception as e:
            logger.error(f"[IBKR_API] Error tracking BEFDAY: {e}", exc_info=True)
            result['befday_tracked'] = False
            result['error'] = f'Connected but BEFDAY tracking failed: {str(e)}'
    
    # CRITICAL: Trigger position snapshot to write to Redis (for RevnBookCheck terminal)
    if result.get('connected'):
        try:
            from app.psfalgo.position_snapshot_api import get_position_snapshot_api, initialize_position_snapshot_api
            pos_api = get_position_snapshot_api()
            if not pos_api:
                initialize_position_snapshot_api()
                pos_api = get_position_snapshot_api()
            if pos_api:
                await pos_api.get_position_snapshot(account_id=account_type, include_zero_positions=False)
                logger.info(f"[IBKR_API] ✅ Position snapshot written to Redis for RevnBookCheck ({account_type})")
        except Exception as snap_err:
            logger.warning(f"[IBKR_API] Position snapshot to Redis failed: {snap_err}")
    
    return result


@router.post("/account/ibkr/disconnect")
async def disconnect_ibkr(account_type: str = "IBKR_GUN") -> Dict[str, Any]:
    """
    Disconnect from IBKR Gateway / TWS.
    
    Args:
        account_type: IBKR_GUN or IBKR_PED
    
    Returns:
        Disconnect result
    """
    from app.psfalgo.ibkr_connector import get_ibkr_connector
    
    if account_type not in ["IBKR_GUN", "IBKR_PED"]:
        raise HTTPException(status_code=400, detail="Invalid account_type. Must be IBKR_GUN or IBKR_PED")
    
    connector = get_ibkr_connector(account_type=account_type)
    if not connector:
        raise HTTPException(status_code=503, detail="IBKR connector not initialized")
    
    await connector.disconnect()
    try:
        from app.core.redis_client import get_redis_client
        r = get_redis_client()
        if r and r.sync:
            cur = r.sync.get("psfalgo:recovery:account_open")
            if cur and (cur.decode() if isinstance(cur, bytes) else cur) == account_type:
                r.sync.delete("psfalgo:recovery:account_open")
    except Exception:
        pass
    return {
        'success': True,
        'account_type': account_type,
        'connected': False
    }


@router.get("/account/ibkr/status")
async def get_ibkr_status() -> Dict[str, Any]:
    """
    Get IBKR connection status for both accounts (PHASE 11: Dual Connections).
    
    IMPORTANT: Both IBKR_PED and IBKR_GUN can be connected simultaneously.
    Active account determines which one is used for data/orders.
    
    Returns:
        Connection status for IBKR_GUN and IBKR_PED, plus active account info
    """
    from app.psfalgo.ibkr_connector import get_ibkr_connector, get_active_ibkr_account
    from app.psfalgo.dual_connection_manager import get_dual_connection_manager

    # Get dual connection manager status (preferred)
    dual_conn_mgr = get_dual_connection_manager()
    if dual_conn_mgr:
        status = dual_conn_mgr.get_status()
        active_account = get_active_ibkr_account()
        
        return {
            'success': True,
            'active_account': active_account,
            'IBKR_GUN': {
                'connected': status['ibkr_gun']['connected'],
                'status': status['ibkr_gun']['status'],
                'error': status['ibkr_gun']['error']
            },
            'IBKR_PED': {
                'connected': status['ibkr_ped']['connected'],
                'status': status['ibkr_ped']['status'],
                'error': status['ibkr_ped']['error']
            },
            'HAMMER_PRO': {
                'connected': status['hammer_pro']['connected'],
                'status': status['hammer_pro']['status'],
                'error': status['hammer_pro']['error']
            }
        }
    
    # Fallback: Check connectors directly
    gun_connector = get_ibkr_connector("IBKR_GUN", create_if_missing=False)
    ped_connector = get_ibkr_connector("IBKR_PED", create_if_missing=False)
    active_account = get_active_ibkr_account()

    return {
        'success': True,
        'active_account': active_account,
        'IBKR_GUN': {
            'connected': gun_connector.is_connected() if gun_connector else False,
            'error': gun_connector.connection_error if gun_connector else None
        },
        'IBKR_PED': {
            'connected': ped_connector.is_connected() if ped_connector else False,
            'error': ped_connector.connection_error if ped_connector else None
        }
    }



@router.get("/account/ibkr/positions")
async def get_ibkr_positions(account_type: str = "IBKR_GUN") -> Dict[str, Any]:
    """
    Get positions from IBKR (READ-ONLY).
    
    Args:
        account_type: IBKR_GUN or IBKR_PED
    
    Returns:
        List of positions
    """
    from app.psfalgo.ibkr_connector import get_ibkr_connector
    
    if account_type not in ["IBKR_GUN", "IBKR_PED"]:
        raise HTTPException(status_code=400, detail="Invalid account_type. Must be IBKR_GUN or IBKR_PED")
    
    connector = get_ibkr_connector(account_type=account_type)
    if not connector:
        raise HTTPException(status_code=503, detail="IBKR connector not initialized")
    
    if not connector.is_connected():
        raise HTTPException(status_code=503, detail=f"IBKR {account_type} not connected")
    
    positions = await connector.get_positions()
    
    return {
        'success': True,
        'account_type': account_type,
        'count': len(positions),
        'positions': positions
    }


@router.get("/account/ibkr/orders")
async def get_ibkr_orders(account_type: str = "IBKR_GUN") -> Dict[str, Any]:
    """
    Get open orders from IBKR (READ-ONLY).
    Uses isolated executor to avoid "event loop already running" when called from FastAPI.
    
    Args:
        account_type: IBKR_GUN or IBKR_PED
    
    Returns:
        List of open orders
    """
    import asyncio
    from app.psfalgo.ibkr_connector import get_ibkr_connector, get_open_orders_isolated_sync
    
    if account_type not in ["IBKR_GUN", "IBKR_PED"]:
        raise HTTPException(status_code=400, detail="Invalid account_type. Must be IBKR_GUN or IBKR_PED")
    
    connector = get_ibkr_connector(account_type=account_type)
    if not connector:
        raise HTTPException(status_code=503, detail="IBKR connector not initialized")
    
    if not connector.is_connected():
        raise HTTPException(status_code=503, detail=f"IBKR {account_type} not connected")
    
    loop = asyncio.get_event_loop()
    orders = await loop.run_in_executor(None, lambda: get_open_orders_isolated_sync(account_type))
    
    return {
        'success': True,
        'account_type': account_type,
        'count': len(orders or []),
        'orders': orders or []
    }


@router.get("/account/ibkr/summary")
async def get_ibkr_summary(account_type: str = "IBKR_GUN") -> Dict[str, Any]:
    """
    Get account summary from IBKR (READ-ONLY).
    
    Args:
        account_type: IBKR_GUN or IBKR_PED
    
    Returns:
        Account summary
    """
    from app.psfalgo.ibkr_connector import get_ibkr_connector
    
    if account_type not in ["IBKR_GUN", "IBKR_PED"]:
        raise HTTPException(status_code=400, detail="Invalid account_type. Must be IBKR_GUN or IBKR_PED")
    
    connector = get_ibkr_connector(account_type=account_type)
    if not connector:
        raise HTTPException(status_code=503, detail="IBKR connector not initialized")
    
    if not connector.is_connected():
        raise HTTPException(status_code=503, detail=f"IBKR {account_type} not connected")
    
    summary = await connector.get_account_summary()
    
    return {
        'success': True,
        'account_type': account_type,
        'summary': summary
    }


# ============================================================================
# SCANNER API (Market Data & Scanner Layer)
# ============================================================================

@router.get("/scanner")
async def get_scanner(
    account_type: Optional[str] = None,
    fbtot_lt: Optional[float] = None,
    fbtot_gt: Optional[float] = None,
    gort_gt: Optional[float] = None,
    gort_lt: Optional[float] = None,
    sma63_chg_lt: Optional[float] = None,
    sma63_chg_gt: Optional[float] = None,
    sma246_chg_lt: Optional[float] = None,
    sma246_chg_gt: Optional[float] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = True,
    limit: int = 500
) -> Dict[str, Any]:
    """
    Get scanner data (MarketSnapshot) with filters and sorting.
    
    Args:
        account_type: Filter by account type (IBKR_GUN, IBKR_PED)
        fbtot_lt: Filter FBTOT < value
        fbtot_gt: Filter FBTOT > value
        gort_gt: Filter GORT > value
        gort_lt: Filter GORT < value
        sma63_chg_lt: Filter SMA63_CHG < value
        sma63_chg_gt: Filter SMA63_CHG > value
        sma246_chg_lt: Filter SMA246_CHG < value
        sma246_chg_gt: Filter SMA246_CHG > value
        sort_by: Sort by field (fbtot, gort, sma63_chg, etc.)
        sort_desc: Sort descending (default: True)
        limit: Maximum number of results (default: 500, max: 1000)
    
    Returns:
        List of MarketSnapshot rows
    """
    from app.psfalgo.market_snapshot_store import get_market_snapshot_store
    from app.api.market_data_routes import market_data_cache
    from app.market_data.static_data_store import get_static_store
    from app.psfalgo.metric_compute_engine import get_metric_compute_engine
    from app.market_data.janall_metrics_engine import get_janall_metrics_engine
    
    snapshot_store = get_market_snapshot_store()
    static_store = get_static_store()
    metric_engine = get_metric_compute_engine()
    janall_metrics_engine = get_janall_metrics_engine()
    
    if not snapshot_store or not static_store or not metric_engine:
        return {
            'success': True,
            'count': 0,
            'rows': []
        }
    
    # Get all current snapshots from MarketSnapshotStore
    all_snapshots = snapshot_store.get_all_current_snapshots(account_type=account_type)
    
    # CRITICAL: If MarketSnapshotStore is empty or missing data, build snapshots from market_data_cache
    # This ensures UI sees bid/ask/last even if MarketSnapshotStore hasn't been updated yet
    if not all_snapshots or len(all_snapshots) == 0:
        # Build snapshots from market_data_cache
        logger.debug(f"[SCANNER] MarketSnapshotStore empty, building from market_data_cache ({len(market_data_cache)} symbols)")
        all_snapshots = {}
        
        for symbol, market_data in market_data_cache.items():
            try:
                static_data = static_store.get_static_data(symbol)
                if not static_data:
                    continue
                
                # Get Janall metrics from cache
                janall_metrics = None
                if janall_metrics_engine and hasattr(janall_metrics_engine, 'symbol_metrics_cache'):
                    janall_metrics = janall_metrics_engine.symbol_metrics_cache.get(symbol, {})
                
                # Compute metrics
                snapshot = metric_engine.compute_metrics(
                    symbol=symbol,
                    market_data=market_data,
                    position_data=None,
                    static_data=static_data,
                    janall_metrics=janall_metrics
                )
                
                all_snapshots[symbol] = snapshot
            except Exception as e:
                logger.debug(f"[SCANNER] Error building snapshot for {symbol}: {e}")
                continue
    else:
        # MarketSnapshotStore has data, but ensure it's up-to-date with market_data_cache
        # Update snapshots that are missing bid/ask/last but have data in market_data_cache
        for symbol, market_data in market_data_cache.items():
            if symbol not in all_snapshots:
                # New symbol in market_data_cache, build snapshot
                try:
                    static_data = static_store.get_static_data(symbol)
                    if not static_data:
                        continue
                    
                    janall_metrics = None
                    if janall_metrics_engine and hasattr(janall_metrics_engine, 'symbol_metrics_cache'):
                        janall_metrics = janall_metrics_engine.symbol_metrics_cache.get(symbol, {})
                    
                    snapshot = metric_engine.compute_metrics(
                        symbol=symbol,
                        market_data=market_data,
                        position_data=None,
                        static_data=static_data,
                        janall_metrics=janall_metrics
                    )
                    
                    all_snapshots[symbol] = snapshot
                except Exception as e:
                    logger.debug(f"[SCANNER] Error building snapshot for {symbol}: {e}")
                    continue
            else:
                # Snapshot exists, but check if bid/ask/last is missing
                snapshot = all_snapshots[symbol]
                if (snapshot.bid is None and snapshot.ask is None and snapshot.last is None) and market_data:
                    # Snapshot has no market data, but market_data_cache has it - update snapshot
                    try:
                        static_data = static_store.get_static_data(symbol)
                        if not static_data:
                            continue
                        
                        janall_metrics = None
                        if janall_metrics_engine and hasattr(janall_metrics_engine, 'symbol_metrics_cache'):
                            janall_metrics = janall_metrics_engine.symbol_metrics_cache.get(symbol, {})
                        
                        # Recompute snapshot with fresh market data
                        snapshot = metric_engine.compute_metrics(
                            symbol=symbol,
                            market_data=market_data,
                            position_data=None,
                            static_data=static_data,
                            janall_metrics=janall_metrics
                        )
                        
                        all_snapshots[symbol] = snapshot
                    except Exception as e:
                        logger.debug(f"[SCANNER] Error updating snapshot for {symbol}: {e}")
                        continue
    
    # Apply filters
    filtered_snapshots = []
    for symbol, snapshot in all_snapshots.items():
        # FBTOT filters
        if fbtot_lt is not None and (snapshot.fbtot is None or snapshot.fbtot >= fbtot_lt):
            continue
        if fbtot_gt is not None and (snapshot.fbtot is None or snapshot.fbtot <= fbtot_gt):
            continue
        
        # GORT filters
        if gort_gt is not None and (snapshot.gort is None or snapshot.gort <= gort_gt):
            continue
        if gort_lt is not None and (snapshot.gort is None or snapshot.gort >= gort_lt):
            continue
        
        # SMA63_CHG filters
        if sma63_chg_lt is not None and (snapshot.sma63_chg is None or snapshot.sma63_chg >= sma63_chg_lt):
            continue
        if sma63_chg_gt is not None and (snapshot.sma63_chg is None or snapshot.sma63_chg <= sma63_chg_gt):
            continue
        
        # SMA246_CHG filters
        if sma246_chg_lt is not None and (snapshot.sma246_chg is None or snapshot.sma246_chg >= sma246_chg_lt):
            continue
        if sma246_chg_gt is not None and (snapshot.sma246_chg is None or snapshot.sma246_chg <= sma246_chg_gt):
            continue
        
        filtered_snapshots.append(snapshot)
    
    # Sort
    if sort_by:
        reverse = sort_desc
        try:
            filtered_snapshots.sort(
                key=lambda s: getattr(s, sort_by.lower(), None) or 0,
                reverse=reverse
            )
        except Exception as e:
            logger.warning(f"Error sorting by {sort_by}: {e}")
    
    # Limit
    limit = min(limit, 1000)  # Cap at 1000
    filtered_snapshots = filtered_snapshots[:limit]
    
    # Convert to scanner rows
    rows = [snapshot.to_scanner_row() for snapshot in filtered_snapshots]
    
    return {
        'success': True,
        'count': len(rows),
        'rows': rows
    }


# ============================================================================
# PSFALGO RULES CONFIGURATION API
# ============================================================================

@router.get("/rules")
async def get_psfalgo_rules() -> Dict[str, Any]:
    """
    Get current PSFALGO rules configuration.
    
    Returns:
        Current rules configuration
    """
    from app.psfalgo.rules_store import get_rules_store
    
    try:
        rules_store = get_rules_store()
        rules = rules_store.get_rules()
        
        return {
            'success': True,
            'rules': rules,
            'version': rules_store.version,
            'last_updated': rules_store.last_updated.isoformat() if rules_store.last_updated else None
        }
    except Exception as e:
        logger.error(f"Error getting rules: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/rules")
async def update_psfalgo_rules(rules_update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update PSFALGO rules configuration.
    
    Args:
        rules_update: Partial rules dict to merge (will be validated)
    
    Returns:
        Result dict with success/error
    """
    from app.psfalgo.rules_store import get_rules_store
    
    try:
        rules_store = get_rules_store()
        result = rules_store.update_rules(rules_update, validate=True)
        
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to update rules'))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating rules: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/rules/reset")
async def reset_psfalgo_rules() -> Dict[str, Any]:
    """
    Reset PSFALGO rules to default values (Janall defaults).
    
    Returns:
        Result dict
    """
    from app.psfalgo.rules_store import get_rules_store
    
    try:
        rules_store = get_rules_store()
        result = rules_store.reset_to_defaults()
        
        if not result.get('success'):
            raise HTTPException(status_code=500, detail=result.get('error', 'Failed to reset rules'))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting rules: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/rules/presets")
async def list_psfalgo_presets() -> Dict[str, Any]:
    """
    List all available rule presets.
    
    Returns:
        List of presets
    """
    from app.psfalgo.rules_store import get_rules_store
    
    try:
        rules_store = get_rules_store()
        presets = rules_store.list_presets()
        
        return {
            'success': True,
            'count': len(presets),
            'presets': presets
        }
    except Exception as e:
        logger.error(f"Error listing presets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/rules/presets/save")
async def save_psfalgo_preset(
    preset_name: str = Query(..., description="Preset name"),
    description: Optional[str] = Query(None, description="Optional description")
) -> Dict[str, Any]:
    """
    Save current rules as a preset.
    
    Args:
        preset_name: Name of preset
        description: Optional description
    
    Returns:
        Result dict
    """
    from app.psfalgo.rules_store import get_rules_store
    
    try:
        rules_store = get_rules_store()
        result = rules_store.save_preset(preset_name, description)
        
        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error', 'Failed to save preset'))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/rules/presets/load")
async def load_psfalgo_preset(
    preset_name: str = Query(..., description="Preset name to load")
) -> Dict[str, Any]:
    """
    Load rules from a preset.
    
    Args:
        preset_name: Name of preset to load
    
    Returns:
        Result dict
    """
    from app.psfalgo.rules_store import get_rules_store
    
    try:
        rules_store = get_rules_store()
        result = rules_store.load_preset(preset_name)
        
        if not result.get('success'):
            raise HTTPException(status_code=404, detail=result.get('error', 'Preset not found'))
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading preset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/rules/validate")
async def validate_psfalgo_rules(rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Validate PSFALGO rules configuration.
    
    Args:
        rules: Rules to validate (if None, validates current rules)
    
    Returns:
        Validation result
    """
    from app.psfalgo.rules_store import get_rules_store
    
    try:
        rules_store = get_rules_store()
        result = rules_store.validate_rules(rules)
        
        return {
            'success': True,
            'valid': result['valid'],
            'errors': result.get('errors', [])
        }
    except Exception as e:
        logger.error(f"Error validating rules: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ============================================================================
# JFIN API
# ============================================================================

@router.get("/jfin/state")
async def get_jfin_state() -> Dict[str, Any]:
    """
    Get current JFIN state (all 4 tabs: BB, FB, SAS, SFS).
    
    If state is empty, automatically calculate JFIN from current market data (Janall-style).
    This allows users to view JFIN data without running RUNALL.
    
    Returns:
        JFIN state with all tabs
    """
    try:
        from app.psfalgo.jfin_store import get_jfin_store
        from app.psfalgo.jfin_engine import get_jfin_engine, initialize_jfin_engine
        # NOTE: addnewpos_decision_engine is a CLASS METHOD, not a top-level function
        # It was never actually used in this endpoint — removed dead import that caused 500 errors
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        from app.psfalgo.metrics_snapshot_api import get_metrics_snapshot_api
        from app.psfalgo.exposure_calculator import get_exposure_calculator
        from app.psfalgo.befday_tracker import get_befday_tracker
        from app.core.data_fabric import get_data_fabric
        from datetime import datetime
        
        jfin_store = get_jfin_store()
        state = jfin_store.get_state()
        
        # If state is empty, automatically calculate JFIN from current market data
        is_empty = not state.bb_stocks and not state.fb_stocks and not state.sas_stocks and not state.sfs_stocks
        
        if is_empty:
            logger.info("[JFIN_API] State is empty, calculating JFIN from current market data (Janall-style)")
            
            try:
                # Step 1: Get JFIN engine
                jfin_engine = get_jfin_engine()
                if not jfin_engine:
                    # Initialize JFIN engine with default config
                    from app.psfalgo.rules_store import get_rules_store
                    rules_store = get_rules_store()
                    jfin_yaml = rules_store.get_rules().get('jfin', {}) if rules_store else {}
                    
                    # Parse nested YAML structure to flat JFINConfig format
                    jfin_config = {}
                    if jfin_yaml:
                        # TUMCSV parameters
                        tumcsv = jfin_yaml.get('tumcsv', {})
                        if tumcsv:
                            jfin_config['selection_percent'] = tumcsv.get('selection_percent', 0.10)
                            jfin_config['min_selection'] = tumcsv.get('min_selection', 2)
                            jfin_config['heldkuponlu_pair_count'] = tumcsv.get('heldkuponlu_pair_count', 16)
                        
                        # Janall selection criteria (two-step intersection)
                        jfin_config['long_percent'] = tumcsv.get('long_percent', 25.0) if tumcsv else 25.0
                        jfin_config['long_multiplier'] = tumcsv.get('long_multiplier', 1.5) if tumcsv else 1.5
                        jfin_config['short_percent'] = tumcsv.get('short_percent', 25.0) if tumcsv else 25.0
                        jfin_config['short_multiplier'] = tumcsv.get('short_multiplier', 0.7) if tumcsv else 0.7
                        jfin_config['max_short'] = tumcsv.get('max_short', 3) if tumcsv else 3
                        
                        # Company limit (Janall: limit_by_company)
                        jfin_config['company_limit_enabled'] = tumcsv.get('company_limit_enabled', True) if tumcsv else True
                        jfin_config['company_limit_divisor'] = tumcsv.get('company_limit_divisor', 1.6) if tumcsv else 1.6
                        
                        # Lot distribution
                        lot_dist = jfin_yaml.get('lot_distribution', {})
                        if lot_dist:
                            jfin_config['alpha'] = lot_dist.get('alpha', 3.0)
                            jfin_config['total_long_rights'] = lot_dist.get('total_long_rights', 28000)
                            jfin_config['total_short_rights'] = lot_dist.get('total_short_rights', 12000)
                            jfin_config['lot_rounding'] = lot_dist.get('lot_rounding', 100)
                        
                        # Percentage
                        percentage = jfin_yaml.get('percentage', {})
                        if percentage:
                            jfin_config['jfin_percentage'] = percentage.get('default', 50)
                        
                        # Exposure
                        exposure = jfin_yaml.get('exposure', {})
                        if exposure:
                            jfin_config['exposure_percent'] = exposure.get('exposure_percent', 60.0)
                        
                        # Lot controls
                        lot_controls = jfin_yaml.get('lot_controls', {})
                        if lot_controls:
                            jfin_config['min_lot_per_order'] = lot_controls.get('min_lot_per_order', 200)
                        
                        # Pools
                        pools = jfin_yaml.get('pools', {})
                        if pools:
                            jfin_config['separate_pools'] = pools.get('separate_pools', True)
                    
                    jfin_engine = initialize_jfin_engine(jfin_config)
                
                # Step 2: Get all available symbols (from static data)
                # CRITICAL FIX: Explicitly initialize with correct path to avoid data starvation
                from app.market_data.static_data_store import get_static_store, initialize_static_store
                import os
                
                # Define correct path
                # Use local path dynamically
                csv_path = os.path.join(os.getcwd(), 'janalldata.csv')
                if not os.path.exists(csv_path):
                     csv_path = os.path.join(os.getcwd(), 'janall', 'janalldata.csv')
                if os.path.exists(csv_path):
                    initialize_static_store(csv_path)
                    logger.info(f"[JFIN_API] Forced initialization of StaticDataStore with path: {csv_path}")
                
                static_store = get_static_store()
                all_symbols = static_store.get_all_symbols() if static_store else []
                
                if not all_symbols:
                    logger.warning("[JFIN_API] No symbols available for JFIN calculation")
                    return {
                        'success': True,
                        'state': state.to_dict(),
                        'is_empty': True,
                        'message': 'No symbols available. Please ensure static data is loaded.'
                    }
                
                # Step 3: Get position snapshot — 3-account isolation: active account only
                from app.trading.trading_account_context import get_trading_context
                account_id = get_trading_context().trading_mode.value
                position_api = get_position_snapshot_api()
                position_snapshot = await position_api.get_position_snapshot(account_id=account_id) if position_api else None
                positions = {pos.symbol: {'qty': pos.qty, 'quantity': pos.qty} for pos in (position_snapshot if position_snapshot else [])}
                
                # Step 4: Get metrics snapshot for all symbols (market data = single source Hammer, no account)
                metrics_api = get_metrics_snapshot_api()
                snapshot_ts = datetime.now()
                metrics = await metrics_api.get_metrics_snapshot(all_symbols, snapshot_ts=snapshot_ts) if metrics_api else {}
                
                # Step 5: Get exposure
                exposure_calc = get_exposure_calculator()
                exposure = None
                if exposure_calc and position_snapshot:
                    # position_snapshot is already a list of PositionSnapshot objects
                    positions_list = position_snapshot if isinstance(position_snapshot, list) else []
                    exposure = exposure_calc.calculate_exposure(positions_list)
                
                # Step 6: Prepare JFIN candidates (ALL symbols - Janall logic)
                # ⚠️ CRITICAL: JFIN in Janall uses ALL symbols, not just ADDNEWPOS-filtered ones
                # JFIN applies its own group-based selection logic
                candidates = []
                data_fabric = get_data_fabric()
                
                # Ensure fast scores are computed for all symbols
                from app.core.fast_score_calculator import FastScoreCalculator
                fast_calc = FastScoreCalculator()
                logger.info("[JFIN_API] Computing fast scores for all symbols...")
                computed_scores = fast_calc.compute_all_fast_scores(include_group_metrics=True)
                logger.info(f"[JFIN_API] ✅ Fast scores computed for {len(computed_scores)} symbols")
                
                # Debug: Check a few symbols to verify scores are computed
                sample_symbols = list(all_symbols[:5]) if len(all_symbols) >= 5 else all_symbols
                for sample_symbol in sample_symbols:
                    sample_snapshot = data_fabric.get_fast_snapshot(sample_symbol)
                    if sample_snapshot:
                        sample_bb = sample_snapshot.get('Final_BB_skor')
                        sample_fb = sample_snapshot.get('Final_FB_skor')
                        logger.debug(
                            f"[JFIN_API] Sample {sample_symbol}: "
                            f"Final_BB={sample_bb}, Final_FB={sample_fb}, "
                            f"bid={sample_snapshot.get('bid')}, ask={sample_snapshot.get('ask')}, "
                            f"prev_close={sample_snapshot.get('prev_close')}, FINAL_THG={sample_snapshot.get('FINAL_THG')}"
                        )
                
                # Get ALL symbols (no limit - Janall uses all symbols)
                candidates_with_scores = 0
                candidates_without_scores = 0
                for symbol in all_symbols:
                    try:
                        fast_snapshot = data_fabric.get_fast_snapshot(symbol)
                        if not fast_snapshot:
                            continue
                        
                        static_data = static_store.get_static_data(symbol) if static_store else {}
                        
                        # Get scores (handle None properly - don't use "or 0" which converts None to 0)
                        final_bb = fast_snapshot.get('Final_BB_skor')
                        final_fb = fast_snapshot.get('Final_FB_skor')
                        final_sas = fast_snapshot.get('Final_SAS_skor')
                        final_sfs = fast_snapshot.get('Final_SFS_skor')
                        
                        # Debug: Log if scores are None or 0
                        if final_bb is None and final_fb is None and final_sas is None and final_sfs is None:
                            # Try to compute on-the-fly if missing
                            if fast_snapshot.get('bid') and fast_snapshot.get('ask') and fast_snapshot.get('last') and fast_snapshot.get('prev_close'):
                                # Recompute for this symbol
                                on_the_fly_scores = fast_calc.compute_fast_scores(symbol)
                                if on_the_fly_scores:
                                    final_bb = on_the_fly_scores.get('Final_BB_skor')
                                    final_fb = on_the_fly_scores.get('Final_FB_skor')
                                    final_sas = on_the_fly_scores.get('Final_SAS_skor')
                                    final_sfs = on_the_fly_scores.get('Final_SFS_skor')
                                    # Update derived data
                                    data_fabric.update_derived(symbol, on_the_fly_scores)
                                    logger.debug(f"[JFIN_API] Recomputed scores for {symbol}: Final_BB={final_bb}, Final_FB={final_fb}")
                        
                        # Convert None to 0 for comparison, but keep original for candidate
                        final_bb_val = final_bb if final_bb is not None else 0.0
                        final_fb_val = final_fb if final_fb is not None else 0.0
                        final_sas_val = final_sas if final_sas is not None else 0.0
                        final_sfs_val = final_sfs if final_sfs is not None else 0.0
                        
                        if final_bb_val != 0.0 or final_fb_val != 0.0 or final_sas_val != 0.0 or final_sfs_val != 0.0:
                            candidates_with_scores += 1
                        else:
                            candidates_without_scores += 1
                        
                        # Include ALL symbols with static data (Janall logic)
                        # JFIN will apply its own filters in _select_stocks_for_pools
                        # We only exclude symbols that have NO static data
                        if not static_data:
                            continue
                        
                        candidate = {
                            'symbol': symbol,
                            'PREF_IBKR': symbol,
                            'PREF IBKR': symbol,  # Janall format
                            'group': static_data.get('GROUP', static_data.get('group', 'UNKNOWN')),
                            'GROUP': static_data.get('GROUP', static_data.get('group', 'UNKNOWN')),
                            'cgrup': static_data.get('CGRUP', static_data.get('cgrup')),
                            'CGRUP': static_data.get('CGRUP', static_data.get('cgrup')),
                            'cmon': static_data.get('CMON', static_data.get('cmon', 'N/A')),
                            'CMON': static_data.get('CMON', static_data.get('cmon', 'N/A')),  # Company name for limit_by_company
                            # Use actual values (can be None, which is OK - JFIN will handle it)
                            'Final_BB_skor': final_bb_val,
                            'final_bb_skor': final_bb_val,
                            'Final_FB_skor': final_fb_val,
                            'final_fb_skor': final_fb_val,
                            'Final_SAS_skor': final_sas_val,
                            'final_sas_skor': final_sas_val,
                            'Final_SFS_skor': final_sfs_val,
                            'final_sfs_skor': final_sfs_val,
                            # Get metrics (handle None properly)
                            'fbtot': fast_snapshot.get('Fbtot') or 0.0,
                            'Fbtot': fast_snapshot.get('Fbtot') or 0.0,
                            'sfstot': fast_snapshot.get('SFStot') or 0.0,
                            'SFStot': fast_snapshot.get('SFStot') or 0.0,
                            'gort': fast_snapshot.get('GORT') or 0.0,
                            'GORT': fast_snapshot.get('GORT') or 0.0,
                            'sma63_chg': fast_snapshot.get('SMA63chg') or 0.0,
                            'SMA63_CHG': fast_snapshot.get('SMA63chg') or 0.0,
                            # Calculate MAXALW = AVG_ADV / 10 (Janall logic)
                            'maxalw': fast_snapshot.get('MAXALW') or (int(float(static_data.get('AVG_ADV', 0) or 0) / 10) if static_data.get('AVG_ADV') else None) or 0,
                            'MAXALW': fast_snapshot.get('MAXALW') or (int(float(static_data.get('AVG_ADV', 0) or 0) / 10) if static_data.get('AVG_ADV') else None) or 0,
                            'current_position': positions.get(symbol, {}).get('qty', 0) if symbol in positions else 0,
                            'bid': fast_snapshot.get('bid') or 0.0,
                            'ask': fast_snapshot.get('ask') or 0.0,
                            'last': fast_snapshot.get('last') or 0.0,
                        }
                        candidates.append(candidate)
                    except Exception as e:
                        logger.debug(f"[JFIN_API] Error processing symbol {symbol}: {e}")
                        continue
                
                if not candidates:
                    logger.warning("[JFIN_API] No eligible candidates found for JFIN calculation")
                    return {
                        'success': True,
                        'state': state.to_dict(),
                        'is_empty': True,
                        'message': 'No eligible candidates found. Please ensure market data is available.'
                    }
                
                logger.info(
                    f"[JFIN_API] Found {len(candidates)} eligible candidates for JFIN calculation "
                    f"(with scores: {candidates_with_scores}, without scores: {candidates_without_scores})"
                )
                
                # Step 7: Get market data for candidates
                market_data = {}
                for candidate in candidates:
                    symbol = candidate['symbol']
                    fast_snapshot = data_fabric.get_fast_snapshot(symbol)
                    if fast_snapshot:
                        market_data[symbol] = {
                            'bid': fast_snapshot.get('bid', 0) or 0,
                            'ask': fast_snapshot.get('ask', 0) or 0,
                            'last': fast_snapshot.get('last', 0) or 0,
                        }
                
                # Step 8: Get BEFDAY positions
                befday_tracker = get_befday_tracker()
                befday_positions = {}
                if befday_tracker:
                    try:
                        befday_positions = befday_tracker.get_befday_positions()
                    except Exception as e:
                        logger.debug(f"[JFIN_API] Could not load BEFDAY positions: {e}")
                
                # Step 9: Calculate max addable total (from exposure)
                max_addable_total = None
                if exposure:
                    max_addable_total = int(exposure.pot_max - exposure.pot_total)
                    logger.debug(f"[JFIN_API] Max addable total: {max_addable_total} (pot_max={exposure.pot_max}, pot_total={exposure.pot_total})")
                
                # Step 10: Set group weights AND lot ratios from Port Adjuster (automatic TUMCSV)
                # Get group weights from Port Adjuster config
                from app.port_adjuster.port_adjuster_store import get_port_adjuster_store
                port_store = get_port_adjuster_store()
                if port_store:
                    snapshot = port_store.get_snapshot()
                    if snapshot and snapshot.config:
                        # PortAdjusterConfig is a Pydantic model, access attributes directly
                        long_weights = snapshot.config.long_groups if hasattr(snapshot.config, 'long_groups') else {}
                        short_weights = snapshot.config.short_groups if hasattr(snapshot.config, 'short_groups') else {}
                        
                        # 🔍 DEBUG: Log non-zero weights
                        long_nz = {k: v for k, v in long_weights.items() if v > 0}
                        short_nz = {k: v for k, v in short_weights.items() if v > 0}
                        logger.info(f"[JFIN_API] 📊 Port Adjuster long non-zero: {long_nz}")
                        logger.info(f"[JFIN_API] 📊 Port Adjuster short non-zero: {short_nz}")
                        
                        jfin_engine.set_group_weights(long_weights, short_weights)
                        logger.info(f"[JFIN_API] Group weights loaded from Port Adjuster: {len(long_weights)} long, {len(short_weights)} short")
                        
                        # 🎯 NEW: Set total lot rights based on Port Adjuster long/short ratio
                        # Get LT Long/Short ratio from Port Adjuster (e.g., 85% / 15%)
                        long_ratio_pct = getattr(snapshot.config, 'long_ratio_pct', 85.0)
                        short_ratio_pct = getattr(snapshot.config, 'short_ratio_pct', 15.0)
                        
                        # Calculate total lot rights based on ratio (using base of 40000 total lots)
                        # This ensures 85/15 split is respected
                        TOTAL_LOT_RIGHTS = 40000  # Base total
                        total_long_rights = int(TOTAL_LOT_RIGHTS * (long_ratio_pct / 100.0))
                        total_short_rights = int(TOTAL_LOT_RIGHTS * (short_ratio_pct / 100.0))
                        
                        # Update JFIN engine config with calculated values
                        jfin_engine.update_config({
                            'total_long_rights': total_long_rights,
                            'total_short_rights': total_short_rights
                        })
                        logger.info(f"[JFIN_API] 📊 Lot rights from Port Adjuster: long={total_long_rights} ({long_ratio_pct}%), short={total_short_rights} ({short_ratio_pct}%)")
                    else:
                        # Fallback: Use rules store
                        from app.psfalgo.rules_store import get_rules_store
                        rules_store = get_rules_store()
                        if rules_store:
                            rules = rules_store.get_rules()
                            port_config = rules.get('port_adjuster', {})
                            long_weights = port_config.get('long_groups', {}) if isinstance(port_config, dict) else {}
                            short_weights = port_config.get('short_groups', {}) if isinstance(port_config, dict) else {}
                            if long_weights or short_weights:
                                jfin_engine.set_group_weights(long_weights, short_weights)
                                logger.info(f"[JFIN_API] Group weights loaded from rules: {len(long_weights)} long, {len(short_weights)} short")
                
                # Step 11: Run JFIN Transform
                jfin_result = await jfin_engine.transform(
                    addnewpos_candidates=candidates,
                    market_data=market_data,
                    positions=positions,
                    befday_positions=befday_positions,
                    max_addable_total=max_addable_total
                )
                
                # Step 12: Convert JFIN intents to stock dicts and update store
                # We need to get scores from candidates (since JFINIntent only has primary score)
                candidates_dict = {c['symbol']: c for c in candidates}
                
                bb_stocks = [_jfin_intent_to_stock_dict(i, candidates_dict) for i in jfin_result.bb_long_intents]
                fb_stocks = [_jfin_intent_to_stock_dict(i, candidates_dict) for i in jfin_result.fb_long_intents]
                sas_stocks = [_jfin_intent_to_stock_dict(i, candidates_dict) for i in jfin_result.sas_short_intents]
                sfs_stocks = [_jfin_intent_to_stock_dict(i, candidates_dict) for i in jfin_result.sfs_short_intents]
                
                jfin_store.update_state(
                    bb_stocks=bb_stocks,
                    fb_stocks=fb_stocks,
                    sas_stocks=sas_stocks,
                    sfs_stocks=sfs_stocks,
                    percentage=jfin_engine.config.jfin_percentage
                )
                
                state = jfin_store.get_state()
                logger.info(f"[JFIN_API] ✅ JFIN state calculated automatically: BB={len(bb_stocks)}, FB={len(fb_stocks)}, SAS={len(sas_stocks)}, SFS={len(sfs_stocks)}")
                
            except Exception as e:
                logger.error(f"[JFIN_API] Error calculating JFIN state automatically: {e}", exc_info=True)
                return {
                    'success': True,
                    'state': state.to_dict(),
                    'is_empty': True,
                    'message': f'Error calculating JFIN: {str(e)}'
                }
        
        return {
            'success': True,
            'state': state.to_dict(),
            'is_empty': False
        }
    except Exception as e:
        logger.error(f"Error getting JFIN state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


def _jfin_intent_to_stock_dict(jfin_intent, candidates_dict: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Helper: Convert JFINIntent to stock dict for UI display"""
    # Get scores from candidate if available, otherwise use score_type
    final_bb_skor = 0
    final_fb_skor = 0
    final_sas_skor = 0
    final_sfs_skor = 0
    
    if candidates_dict and jfin_intent.symbol in candidates_dict:
        candidate = candidates_dict[jfin_intent.symbol]
        final_bb_skor = candidate.get('Final_BB_skor', candidate.get('final_bb_skor', 0)) or 0
        final_fb_skor = candidate.get('Final_FB_skor', candidate.get('final_fb_skor', 0)) or 0
        final_sas_skor = candidate.get('Final_SAS_skor', candidate.get('final_sas_skor', 0)) or 0
        final_sfs_skor = candidate.get('Final_SFS_skor', candidate.get('final_sfs_skor', 0)) or 0
    else:
        # Fallback: use score based on score_type
        if jfin_intent.score_type == 'BB_LONG':
            final_bb_skor = jfin_intent.score
        elif jfin_intent.score_type == 'FB_LONG':
            final_fb_skor = jfin_intent.score
        elif jfin_intent.score_type == 'SAS_SHORT':
            final_sas_skor = jfin_intent.score
        elif jfin_intent.score_type == 'SFS_SHORT':
            final_sfs_skor = jfin_intent.score
    
    return {
        'symbol': jfin_intent.symbol,
        'group': jfin_intent.group,
        'cgrup': jfin_intent.cgrup,
        'final_bb_skor': final_bb_skor,
        'final_fb_skor': final_fb_skor,
        'final_sas_skor': final_sas_skor,
        'final_sfs_skor': final_sfs_skor,
        'fbtot': jfin_intent.fbtot,
        'sfstot': jfin_intent.sfstot,
        'gort': jfin_intent.gort,
        'calculated_lot': jfin_intent.calculated_lot,
        'addable_lot': jfin_intent.addable_lot,
        'final_lot': jfin_intent.qty,
        'maxalw': jfin_intent.maxalw,
        'current_position': jfin_intent.current_position,
        'befday_qty': jfin_intent.befday_qty,
        'order_price': jfin_intent.price,
        'score_type': jfin_intent.score_type,
        'order_type': jfin_intent.order_type,
        'percentage_applied': jfin_intent.percentage_applied
    }


@router.get("/jfin/tab/{tab_name}")
async def get_jfin_tab(tab_name: str) -> Dict[str, Any]:
    """
    Get stocks for specific JFIN tab.
    
    Args:
        tab_name: 'BB', 'FB', 'SAS', or 'SFS'
    
    Returns:
        Stocks for the specified tab
    """
    try:
        from app.psfalgo.jfin_store import get_jfin_store
        
        jfin_store = get_jfin_store()
        stocks = jfin_store.get_tab_stocks(tab_name)
        
        return {
            'success': True,
            'tab': tab_name.upper(),
            'stocks': stocks,
            'count': len(stocks)
        }
    except Exception as e:
        logger.error(f"Error getting JFIN tab {tab_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/jfin/update-percentage")
async def update_jfin_percentage(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update JFIN percentage and recalculate lots.
    
    Args:
        request: { "percentage": 25|50|75|100 }
    
    Returns:
        Updated JFIN state
    """
    try:
        from app.psfalgo.jfin_store import get_jfin_store
        from app.psfalgo.jfin_engine import get_jfin_engine
        
        percentage = request.get('percentage')
        if percentage not in [25, 50, 75, 100]:
            raise HTTPException(status_code=400, detail="Percentage must be 25, 50, 75, or 100")
        
        jfin_store = get_jfin_store()
        jfin_store.set_percentage(percentage)
        
        # Trigger recalculation if JFIN engine is available
        jfin_engine = get_jfin_engine()
        if jfin_engine:
            jfin_engine.config.jfin_percentage = percentage
            logger.info(f"[JFIN_API] Percentage updated to {percentage}%")
        
        state = jfin_store.get_state()
        
        return {
            'success': True,
            'percentage': percentage,
            'state': state.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating JFIN percentage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/jfin/apply-ntumcsv")
async def apply_jfin_ntumcsv(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply NTUMCSV settings and recalculate JFIN.
    
    Args:
        request: { "csv_data": {...} }
    
    Returns:
        Updated JFIN state
    """
    try:
        from app.psfalgo.jfin_store import get_jfin_store
        from app.psfalgo.jfin_engine import get_jfin_engine
        
        csv_data = request.get('csv_data', {})
        
        jfin_store = get_jfin_store()
        jfin_store.update_state(ntumcsv_settings=csv_data)
        
        # Trigger recalculation if JFIN engine is available
        jfin_engine = get_jfin_engine()
        if jfin_engine:
            # Apply NTUMCSV settings to JFIN engine
            # This will be handled by the engine's update_config method
            logger.info(f"[JFIN_API] NTUMCSV settings applied")
        
        state = jfin_store.get_state()
        
        return {
            'success': True,
            'state': state.to_dict()
        }
    except Exception as e:
        logger.error(f"Error applying NTUMCSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ============================================================================
# TAKE PROFIT API
# ============================================================================

@router.get("/take-profit/longs")
async def get_take_profit_longs() -> Dict[str, Any]:
    """
    Get long positions for take profit — 3-account isolation: active account only.
    Market data (bid/ask/last) = Hammer; positions = account-scoped.
    """
    try:
        from app.psfalgo.take_profit_engine import get_take_profit_engine, initialize_take_profit_engine
        from app.trading.trading_account_context import get_trading_context

        account_id = get_trading_context().trading_mode.value
        engine = get_take_profit_engine()
        if not engine:
            engine = initialize_take_profit_engine()
        positions = await engine.get_long_positions_async(account_id)
        return {
            'success': True,
            'positions': [pos.to_dict() for pos in positions],
            'count': len(positions),
            'account_id': account_id
        }
    except Exception as e:
        logger.error(f"Error getting long positions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/take-profit/shorts")
async def get_take_profit_shorts() -> Dict[str, Any]:
    """
    Get short positions for take profit — 3-account isolation: active account only.
    """
    try:
        from app.psfalgo.take_profit_engine import get_take_profit_engine, initialize_take_profit_engine
        from app.trading.trading_account_context import get_trading_context

        account_id = get_trading_context().trading_mode.value
        engine = get_take_profit_engine()
        if not engine:
            engine = initialize_take_profit_engine()
        positions = await engine.get_short_positions_async(account_id)
        return {
            'success': True,
            'positions': [pos.to_dict() for pos in positions],
            'count': len(positions),
            'account_id': account_id
        }
    except Exception as e:
        logger.error(f"Error getting short positions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/take-profit/send-order")
async def send_take_profit_order(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send take profit (REV) order. Hesap moduna göre yönlendirir:
    - IBKR_PED / IBKR_GUN → Gateway (aynı mantık, port 4001)
    - HAMPRO (HAMMER_PRO) → Hammer Pro emir mantığı
    """
    try:
        symbol = request.get('symbol')
        side = request.get('side')  # BUY or SELL
        qty = request.get('qty')
        price = request.get('price')
        order_type = request.get('order_type', 'LIMIT')
        account_id = request.get('account_id')  # RevnBookCheck gönderir: IBKR_PED, IBKR_GUN, HAMPRO
        
        if not all([symbol, side, qty, price]):
            raise HTTPException(status_code=400, detail="Missing required fields: symbol, side, qty, price")
        
        from app.execution.execution_router import get_execution_router, ExecutionMode
        from app.trading.trading_account_context import get_trading_context, TradingAccountMode
        
        ctx = get_trading_context()
        # account_id request'te varsa context'i ona göre ayarla (RevnBookCheck hangi hesaba REV atacaksa)
        if account_id:
            try:
                mode_enum = TradingAccountMode.HAMPRO if account_id in ("HAMPRO", "HAMMER_PRO") else TradingAccountMode(account_id)
                if ctx.trading_mode != mode_enum:
                    ctx.set_trading_mode(mode_enum)
            except ValueError:
                pass  # Geçersiz account_id ise mevcut context kullanılır
        
        order_plan = {
            'symbol': symbol,
            'action': side,
            'size': int(qty),
            'price': float(price),
            'style': order_type or 'LIMIT',
            'psfalgo_source': True,
            'psfalgo_action': 'TAKE_PROFIT',
            'strategy_tag': 'REV_TP'
        }
        gate_status = {'gate_status': 'MANUAL_APPROVE'}
        router = get_execution_router()
        # Run in executor so IBKR provider can block waiting for real order result without blocking event loop
        import asyncio
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: router.handle(
                    order_plan=order_plan,
                    gate_status=gate_status,
                    user_action='APPROVE',
                    symbol=symbol
                )
            )
        except Exception as exec_err:
            logger.error(f"[TAKE_PROFIT] Execution router error: {exec_err}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Execution router error: {str(exec_err)}")
        
        if result.get('execution_status') == 'EXECUTED':
            logger.info(f"[TAKE_PROFIT] Order sent: {side} {qty} {symbol} @ ${price:.2f} (account: {ctx.trading_mode.value})")
            return {
                'success': True,
                'order_id': result.get('order_id'),
                'message': f"Order sent: {side} {qty} {symbol} @ ${price:.2f}"
            }
        detail = result.get('execution_reason') or result.get('provider_error') or result.get('detail') or 'Failed to send order'
        logger.warning(f"[TAKE_PROFIT] Order not executed: status={result.get('execution_status')!r} reason={detail!r} full_result={result}")
        raise HTTPException(status_code=500, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending take profit order: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")



# ============================================================================
# LEDGER (Internal) - Phase 8
# ============================================================================

@router.post("/ledger/finalize-day")
async def finalize_day(
    account_id: str = Query(..., description="Account ID to finalize"),
    force: bool = Query(False, description="Force finalization even if market is open/mid-day")
) -> Dict[str, Any]:
    """
    Trigger End-of-Day (EOD) normalization for the internal ledger.
    Applies netting rules (Collapse Opposite) and cleanup.
    
    SAFETY GUARD:
    - By default, blocks execution before 16:00 (4:00 PM) to prevent accidental mid-day netting.
    - Use force=true to bypass.
    """
    try:
        from app.psfalgo.internal_ledger_store import get_internal_ledger_store, initialize_internal_ledger_store
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        
        # SAFETY CHECK
        if not force:
            now = datetime.now()
            # Simple check: If before 16:00, require force
            # This assumes server is in market time zone or user is aware.
            if now.hour < 16:
                 raise HTTPException(
                    status_code=400, 
                    detail=f"Market likely open (Current hour: {now.hour}). usage: finalize-day?force=true to override."
                )
        
        store = get_internal_ledger_store()
        if not store:
            initialize_internal_ledger_store()
            store = get_internal_ledger_store()
            
        # We need current broker positions to reconcile
        pos_api = get_position_snapshot_api()
        if not pos_api:
            raise HTTPException(status_code=503, detail="PositionSnapshotAPI not initialized")
        
        # Get snapshot for this account
        snapshots = await pos_api.get_position_snapshot(
            account_id=account_id,
            include_zero_positions=True # Need zeros to clean them up from ledger
        )
        
        # Create simple dict {symbol: qty}
        broker_positions = {s.symbol: s.qty for s in snapshots}
        
        # Run finalize logic
        store.finalize_day(account_id, broker_positions)
        
        return {
            'success': True,
            'message': f"Finalized day for {account_id}",
            'positions_processed': len(broker_positions)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finalizing day: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CLEAN LOGS (Explainability) - Phase 9
# ============================================================================

@router.get("/{account_id}/cleanlogs")
async def get_clean_logs(
    account_id: str,
    correlation_id: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get structured CleanLogs for an account.
    Supports traceability via correlation_id.
    """
    try:
        from app.psfalgo.clean_log_store import get_clean_log_store, initialize_clean_log_store
        
        store = get_clean_log_store()
        if not store:
            initialize_clean_log_store()
            store = get_clean_log_store()
            
        logs = store.get_logs(account_id, correlation_id=correlation_id, limit=limit)
        
        return {
            'success': True,
            'count': len(logs),
            'logs': logs
        }
    except Exception as e:
        logger.error(f"Error getting cleanlogs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
# ============================================================================
# ENGINE DIAGNOSTIC API (Phase 2)
# ============================================================================

@router.get("/engines/diagnostic")
async def get_engines_diagnostic() -> Dict[str, Any]:
    """
    Get diagnostic information for all engines.
    Shows why engines may not be generating proposals.
    
    Returns comprehensive status and diagnostic data for:
    - RUNALL orchestrator
    - KARBOTU engine
    - REDUCEMORE engine
    - ADDNEWPOS engine
    - LT_TRIM engine
    """
    try:
        from app.psfalgo.runall_engine import get_runall_engine
        from app.psfalgo.karbotu_engine import get_karbotu_engine
        from app.psfalgo.reducemore_engine import get_reducemore_engine
        
        runall = get_runall_engine()
        karbotu = get_karbotu_engine()
        reducemore = get_reducemore_engine()
        
        # Build diagnostic response
        diagnostic = {
            'runall': {
                'loop_running': runall.loop_running if hasattr(runall, 'loop_running') else False,
                'loop_count': runall.loop_count if hasattr(runall, 'loop_count') else 0,
                'active_engines': runall.active_engines if hasattr(runall, 'active_engines') else [],
                'last_cycle': runall.loop_count if hasattr(runall, 'loop_count') else 0
            },
            'karbotu': {
                'status': 'ENABLED' if 'KARBOTU' in (runall.active_engines if hasattr(runall, 'active_engines') else []) else 'DISABLED',
                'last_diagnostic': karbotu.last_diagnostic if hasattr(karbotu, 'last_diagnostic') else None
            },
            'reducemore': {
                'status': 'ENABLED' if 'REDUCEMORE' in (runall.active_engines if hasattr(runall, 'active_engines') else []) else 'DISABLED',
                'last_diagnostic': reducemore.last_diagnostic if hasattr(reducemore, 'last_diagnostic') else None
            },
            'addnewpos': {
                'status': 'ENABLED' if 'MM_ENGINE' in (runall.active_engines if hasattr(runall, 'active_engines') else []) else 'DISABLED',
                'last_diagnostic': None  # ADDNEWPOS doesn't have diagnostic yet
            },
            'lt_trim': {
                'status': 'ENABLED' if 'LT_TRIM' in (runall.active_engines if hasattr(runall, 'active_engines') else []) else 'DISABLED',
                'last_diagnostic': None  # LT_TRIM doesn't have diagnostic yet
            }
        }
        
        return {
            'success': True,
            'diagnostic': diagnostic,
            'timestamp': datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"[DIAGNOSTIC API] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Diagnostic error: {str(e)}")


@router.get("/engines/{engine_name}/status")
async def get_engine_status(engine_name: str) -> Dict[str, Any]:
    """
    Get detailed status for a specific engine.
    
    Args:
        engine_name: KARBOTU, REDUCEMORE, LT_TRIM, ADDNEWPOS_ENGINE, MM_ENGINE
        
    Returns:
        Detailed engine status including:
        - Enabled/disabled status
        - Recent proposals count
        - Engine-specific diagnostic data
        - Last cycle metrics
    """
    try:
        from app.psfalgo.runall_engine import get_runall_engine
        from app.psfalgo.karbotu_engine import get_karbotu_engine
        from app.psfalgo.reducemore_engine import get_reducemore_engine
        from app.psfalgo.proposal_store import get_proposal_store
        
        runall = get_runall_engine()
        proposal_store = get_proposal_store()
        
        # Check if enabled
        active_engines = runall.active_engines if hasattr(runall, 'active_engines') else []
        enabled = engine_name in active_engines
        
        # Get recent proposals from this engine
        recent_proposals = []
        if proposal_store:
            # Map engine_name to proposal filter
            engine_filter = engine_name
            if engine_name == 'MM_ENGINE':
                engine_filter = 'ADDNEWPOS_ENGINE'  # MM_ENGINE maps to ADDNEWPOS_ENGINE
            
            try:
                proposals = proposal_store.get_all_proposals(
                    engine=engine_filter,
                    limit=10
                )
                recent_proposals = [
                    {
                        'symbol': p.symbol,
                        'side': p.side,
                        'qty': p.proposed_qty,
                        'status': p.status,
                        'timestamp': p.proposal_ts.isoformat() if hasattr(p.proposal_ts, 'isoformat') else str(p.proposal_ts)
                    } for p in proposals
                ]
            except Exception as e:
                logger.warning(f"[ENGINE STATUS] Could not fetch proposals for {engine_name}: {e}")
        
        # Get engine-specific diagnostic
        engine_diagnostic = None
        if engine_name == 'KARBOTU':
            karbotu = get_karbotu_engine()
            if hasattr(karbotu, 'last_diagnostic'):
                engine_diagnostic = karbotu.last_diagnostic
        elif engine_name == 'REDUCEMORE':
            reducemore = get_reducemore_engine()
            if hasattr(reducemore, 'last_diagnostic'):
                engine_diagnostic = reducemore.last_diagnostic
        
        return {
            'success': True,
            'engine': engine_name,
            'enabled': enabled,
            'recent_proposals_count': len(recent_proposals),
            'recent_proposals': recent_proposals,
            'diagnostic': engine_diagnostic,
            'timestamp': datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"[ENGINE STATUS] Error for {engine_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Engine status error: {str(e)}")


# ============================================================================
# SETTINGS BASELINE (Capture current as default, Reset with diff report)
# ============================================================================

@router.post("/settings/capture-baseline")
async def capture_settings_baseline():
    """
    Snapshot ALL current settings as the 'baseline default'.
    Future reset operations restore to this exact state.
    Call this once when the system is configured as desired.
    """
    try:
        from app.psfalgo.settings_baseline_service import get_settings_baseline_service
        svc = get_settings_baseline_service()
        snapshot = svc.capture_baseline()
        return {
            'success': True,
            'message': f"✅ Baseline captured at {snapshot['captured_at']}",
            'baseline': snapshot
        }
    except Exception as e:
        logger.error(f"[BASELINE API] Capture error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/settings/reset-to-baseline")
async def reset_settings_to_baseline(category: Optional[str] = None):
    """
    Reset ALL (or specific category) settings to the captured baseline.
    Returns a diff report showing every field that was changed.
    
    Query params:
        category: Optional - 'heavy', 'active_engines', 'mm_settings', 
                  'exposure_thresholds', 'addnewpos'. If omitted, resets ALL.
    """
    try:
        from app.psfalgo.settings_baseline_service import get_settings_baseline_service
        svc = get_settings_baseline_service()
        result = svc.reset_to_baseline(category)
        return result
    except Exception as e:
        logger.error(f"[BASELINE API] Reset error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/baseline-diff")
async def get_baseline_diff():
    """
    Compare current settings vs baseline WITHOUT changing anything.
    Shows what has drifted from the captured default.
    """
    try:
        from app.psfalgo.settings_baseline_service import get_settings_baseline_service
        svc = get_settings_baseline_service()
        return svc.get_current_vs_baseline()
    except Exception as e:
        logger.error(f"[BASELINE API] Diff error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EX-DIVIDEND INFO TODAY
# ============================================================================

@router.get("/exdiv-today")
async def get_exdiv_today() -> Dict[str, Any]:
    """
    Get today's ex-dividend stocks and their 0.85 * DIV AMOUNT values.
    Data sourced from exdiv_today.json (generated daily by exdiv_info.py pipeline).
    
    Falls back to scanning ek*.csv files directly if JSON is missing or stale.
    
    Returns:
        { success, date, stocks: [{symbol, div_amount, adjusted_div, source_file}], count }
    """
    import json
    import os
    from datetime import datetime
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # Try JSON file first (fastest path)
    json_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                      '..', 'janall', 'exdiv_today.json'),
        r'C:\StockTracker\janall\exdiv_today.json',
        r'C:\StockTracker\exdiv_today.json',
    ]
    
    for json_path in json_paths:
        try:
            json_path = os.path.abspath(json_path)
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Verify it's today's data
                if data.get('date') == today_str:
                    logger.info(f"[EXDIV] Loaded {data.get('count', 0)} ex-div stocks from {json_path}")
                    return {
                        'success': True,
                        'date': data['date'],
                        'date_display': data.get('date_display', today_str),
                        'stocks': data.get('stocks', []),
                        'count': data.get('count', 0),
                        'source': 'json_cache',
                        'generated_at': data.get('generated_at')
                    }
                else:
                    logger.warning(
                        f"[EXDIV] Stale JSON: file date={data.get('date')} vs today={today_str}"
                    )
        except Exception as e:
            logger.debug(f"[EXDIV] Could not load {json_path}: {e}")
            continue
    
    # Fallback: Live scan from CSV files
    try:
        import glob
        import pandas as pd
        
        today_mm_dd_yyyy = datetime.now().strftime('%m/%d/%Y')
        csv_dir = r'C:\StockTracker'
        
        exdiv_stocks = {}
        csv_patterns = [os.path.join(csv_dir, 'ek*.csv'), os.path.join(csv_dir, 'sek*.csv')]
        all_files = []
        for pattern in csv_patterns:
            all_files.extend(glob.glob(pattern))
        
        for csv_file in set(all_files):
            try:
                df = pd.read_csv(csv_file)
                if not all(c in df.columns for c in ['PREF IBKR', 'EX-DIV DATE', 'DIV AMOUNT']):
                    continue
                
                for _, row in df.iterrows():
                    ex_div_date = str(row.get('EX-DIV DATE', '')).strip()
                    symbol = str(row.get('PREF IBKR', '')).strip()
                    div_amount = row.get('DIV AMOUNT', 0)
                    
                    if not symbol or not ex_div_date:
                        continue
                    
                    if ex_div_date == today_mm_dd_yyyy and symbol not in exdiv_stocks:
                        div_float = float(div_amount) if pd.notna(div_amount) else 0.0
                        exdiv_stocks[symbol] = {
                            'symbol': symbol,
                            'div_amount': div_float,
                            'adjusted_div': round(0.85 * div_float, 4),
                            'ex_div_date': ex_div_date,
                            'source_file': os.path.basename(csv_file)
                        }
            except Exception:
                continue
        
        stocks_list = list(exdiv_stocks.values())
        logger.info(f"[EXDIV] Live scan found {len(stocks_list)} ex-div stocks for {today_str}")
        
        return {
            'success': True,
            'date': today_str,
            'date_display': today_mm_dd_yyyy,
            'stocks': stocks_list,
            'count': len(stocks_list),
            'source': 'live_csv_scan'
        }
    except Exception as e:
        logger.error(f"[EXDIV] Error scanning CSVs: {e}", exc_info=True)
        return {
            'success': False,
            'date': today_str,
            'stocks': [],
            'count': 0,
            'error': str(e)
        }
