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
from datetime import datetime
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
    
    return {
        'success': True,
        'state': {
            'global_state': snapshot.global_state,
            'cycle_state': snapshot.cycle_state,
            'cycle_id': snapshot.cycle_id,
            'loop_running': snapshot.loop_running,
            'dry_run_mode': snapshot.dry_run_mode,
            'cycle_start_time': snapshot.cycle_start_time,
            'next_cycle_time': snapshot.next_cycle_time,
            'last_error': snapshot.last_error,
            'last_error_time': snapshot.last_error_time,
            'exposure': snapshot.exposure,
            'timestamp': snapshot.timestamp
        }
    }


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

@router.get("/proposals")
async def get_proposals(
    status: Optional[str] = None,
    engine: Optional[str] = None,
    cycle_id: Optional[int] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get order proposals with optional filters.
    
    Args:
        status: Filter by status (PROPOSED, ACCEPTED, REJECTED, EXPIRED)
        engine: Filter by engine (KARBOTU, REDUCEMORE, ADDNEWPOS)
        cycle_id: Filter by cycle ID
        limit: Maximum number of proposals to return (default: 100, max: 500)
    
    Returns:
        List of OrderProposals
    """
    from app.psfalgo.proposal_store import get_proposal_store
    
    proposal_store = get_proposal_store()
    if not proposal_store:
        return {
            'success': True,
            'count': 0,
            'proposals': []
        }
    
    limit = min(limit, 500)  # Cap at 500
    proposals = proposal_store.get_all_proposals(
        status=status,
        engine=engine,
        cycle_id=cycle_id,
        limit=limit
    )
    
    return {
        'success': True,
        'count': len(proposals),
        'proposals': [p.to_dict() for p in proposals]
    }


@router.get("/proposals/latest")
async def get_latest_proposals(limit: int = 10) -> Dict[str, Any]:
    """
    Get latest N order proposals.
    
    Args:
        limit: Number of latest proposals (default: 10, max: 100)
    
    Returns:
        Latest OrderProposals
    """
    from app.psfalgo.proposal_store import get_proposal_store
    
    proposal_store = get_proposal_store()
    if not proposal_store:
        return {
            'success': True,
            'count': 0,
            'proposals': []
        }
    
    limit = min(limit, 100)  # Cap at 100
    proposals = proposal_store.get_latest_proposals(limit=limit)
    
    return {
        'success': True,
        'count': len(proposals),
        'proposals': [p.to_dict() for p in proposals]
    }


@router.post("/proposals/{proposal_id}/accept")
async def accept_proposal(proposal_id: str) -> Dict[str, Any]:
    """
    Mark proposal as ACCEPTED (human action).
    
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
        status='ACCEPTED',
        human_action='ACCEPTED'
    )
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Proposal not found: {proposal_id}")
    
    return {
        'success': True,
        'message': f'Proposal {proposal_id} marked as ACCEPTED'
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
        Current account mode info
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
                'warning': 'AccountModeManager not initialized, using default HAMMER_PRO'
            }
        
        return {
            'success': True,
            'mode': manager.get_mode(),
            'is_hammer': manager.is_hammer(),
            'is_ibkr_gun': manager.is_ibkr_gun(),
            'is_ibkr_ped': manager.is_ibkr_ped(),
            'is_ibkr': manager.is_ibkr()
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
        
        # Check if already connected
        if hammer_client.is_connected():
            return {
                'success': True,
                'connected': True,
                'message': 'Already connected to Hammer Pro',
                'befday_tracked': False
            }
        
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
        
        # Connection successful - now track BEFDAY positions
        logger.info("[HAMMER_API] Connection successful, tracking BEFDAY positions...")
        
        try:
            # Get positions from Hammer
            positions_service = get_hammer_positions_service()
            if positions_service:
                positions = await positions_service.get_positions()
                
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
                    
                    # Track BEFDAY (günde 1 kez)
                    befday_tracked = await track_befday_positions(
                        positions=befday_positions,
                        mode='hampro',
                        account='HAMMER_PRO'
                    )
                    
                    if befday_tracked:
                        logger.info(f"[HAMMER_API] ✅ BEFDAY tracked: {len(befday_positions)} positions saved to befham.csv")
                    else:
                        logger.info(f"[HAMMER_API] ℹ️ BEFDAY already tracked today or outside window")
                    
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
    from app.psfalgo.ibkr_connector import get_ibkr_connector
    
    if account_type not in ["IBKR_GUN", "IBKR_PED"]:
        raise HTTPException(status_code=400, detail="Invalid account_type. Must be IBKR_GUN or IBKR_PED")
    
    connector = get_ibkr_connector(account_type=account_type)
    if not connector:
        raise HTTPException(status_code=503, detail="IBKR connector not initialized")
    
    # PHASE 10.1: Default port if not provided (same for both GUN and PED)
    if port is None:
        port = 4001  # Default Gateway port
    
    result = await connector.connect(host=host, port=port, client_id=client_id)
    
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to connect to IBKR'))
    
    # Connection successful - now track BEFDAY positions (günde 1 kez)
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
    
    return {
        'success': True,
        'account_type': account_type,
        'connected': False
    }


@router.get("/account/ibkr/status")
async def get_ibkr_status() -> Dict[str, Any]:
    """
    Get IBKR connection status for both accounts.
    
    Returns:
        Connection status for IBKR_GUN and IBKR_PED
    """
    from app.psfalgo.ibkr_connector import get_ibkr_connector
    
    gun_connector = get_ibkr_connector("IBKR_GUN")
    ped_connector = get_ibkr_connector("IBKR_PED")
    
    return {
        'success': True,
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
    
    Args:
        account_type: IBKR_GUN or IBKR_PED
    
    Returns:
        List of open orders
    """
    from app.psfalgo.ibkr_connector import get_ibkr_connector
    
    if account_type not in ["IBKR_GUN", "IBKR_PED"]:
        raise HTTPException(status_code=400, detail="Invalid account_type. Must be IBKR_GUN or IBKR_PED")
    
    connector = get_ibkr_connector(account_type=account_type)
    if not connector:
        raise HTTPException(status_code=503, detail="IBKR connector not initialized")
    
    if not connector.is_connected():
        raise HTTPException(status_code=503, detail=f"IBKR {account_type} not connected")
    
    orders = await connector.get_open_orders()
    
    return {
        'success': True,
        'account_type': account_type,
        'count': len(orders),
        'orders': orders
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
        from app.psfalgo.addnewpos_engine import addnewpos_decision_engine
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
                            jfin_config['heldkuponlu_pair_count'] = tumcsv.get('heldkuponlu_pair_count', 8)
                        
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
                csv_path = r"c:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janall\janalldata.csv"
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
                
                # Step 3: Get position snapshot
                position_api = get_position_snapshot_api()
                position_snapshot = await position_api.get_position_snapshot() if position_api else None
                positions = {pos.symbol: {'qty': pos.qty, 'quantity': pos.qty} for pos in (position_snapshot if position_snapshot else [])}
                
                # Step 4: Get metrics snapshot for all symbols
                metrics_api = get_metrics_snapshot_api()
                snapshot_ts = datetime.now()
                metrics = await metrics_api.get_metrics_snapshot(all_symbols, snapshot_ts=snapshot_ts) if metrics_api else {}
                
                # Step 5: Get exposure
                exposure_calc = get_exposure_calculator()
                exposure = None
                if exposure_calc and position_snapshot:
                    # Convert position snapshot to list of PositionSnapshot objects
                    from app.psfalgo.decision_models import PositionSnapshot
                    positions_list = position_snapshot.positions if position_snapshot else []
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
                
                # Step 10: Set group weights from Port Adjuster (automatic TUMCSV)
                # Get group weights from Port Adjuster config
                from app.port_adjuster.port_adjuster_store import get_port_adjuster_store
                port_store = get_port_adjuster_store()
                if port_store:
                    snapshot = port_store.get_snapshot()
                    if snapshot and snapshot.config:
                        # PortAdjusterConfig is a Pydantic model, access attributes directly
                        long_weights = snapshot.config.long_groups if hasattr(snapshot.config, 'long_groups') else {}
                        short_weights = snapshot.config.short_groups if hasattr(snapshot.config, 'short_groups') else {}
                        jfin_engine.set_group_weights(long_weights, short_weights)
                        logger.info(f"[JFIN_API] Group weights loaded from Port Adjuster: {len(long_weights)} long, {len(short_weights)} short")
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
    Get long positions for take profit.
    
    Returns:
        List of long positions
    """
    try:
        from app.psfalgo.take_profit_engine import get_take_profit_engine, initialize_take_profit_engine
        
        engine = get_take_profit_engine()
        if not engine:
            engine = initialize_take_profit_engine()
        
        positions = engine.get_long_positions()
        
        return {
            'success': True,
            'positions': [pos.to_dict() for pos in positions],
            'count': len(positions)
        }
    except Exception as e:
        logger.error(f"Error getting long positions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/take-profit/shorts")
async def get_take_profit_shorts() -> Dict[str, Any]:
    """
    Get short positions for take profit.
    
    Returns:
        List of short positions
    """
    try:
        from app.psfalgo.take_profit_engine import get_take_profit_engine, initialize_take_profit_engine
        
        engine = get_take_profit_engine()
        if not engine:
            engine = initialize_take_profit_engine()
        
        positions = engine.get_short_positions()
        
        return {
            'success': True,
            'positions': [pos.to_dict() for pos in positions],
            'count': len(positions)
        }
    except Exception as e:
        logger.error(f"Error getting short positions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/take-profit/send-order")
async def send_take_profit_order(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send take profit order.
    
    Args:
        request: { symbol, side, qty, price, order_type }
    
    Returns:
        Order result
    """
    try:
        symbol = request.get('symbol')
        side = request.get('side')  # BUY or SELL
        qty = request.get('qty')
        price = request.get('price')
        order_type = request.get('order_type')
        
        if not all([symbol, side, qty, price]):
            raise HTTPException(status_code=400, detail="Missing required fields: symbol, side, qty, price")
        
        # Send order via execution engine
        from app.psfalgo.execution_engine import get_execution_engine
        from app.execution.execution_models import ExecutionIntent, IntentSide, OrderType
        
        execution_engine = get_execution_engine()
        if not execution_engine:
            raise HTTPException(status_code=503, detail="ExecutionEngine not available")
        
        # Create execution intent
        intent_side = IntentSide.BUY if side == 'BUY' else IntentSide.SELL
        intent = ExecutionIntent(
            symbol=symbol,
            side=intent_side,
            quantity=qty,
            price=price,
            order_type=OrderType.LIMIT,
            reason_code="TAKE_PROFIT",
            reason_text=f"Take Profit {order_type}"
        )
        
        # Send order
        result = await execution_engine.send_order(intent)
        
        if result.get('success'):
            logger.info(f"[TAKE_PROFIT] Order sent: {side} {qty} {symbol} @ ${price:.2f}")
            return {
                'success': True,
                'order_id': result.get('order_id'),
                'message': f"Order sent: {side} {qty} {symbol} @ ${price:.2f}"
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', 'Failed to send order'))
            
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
