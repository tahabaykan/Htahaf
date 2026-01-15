"""
Intent API Routes
API endpoints for PSFALGO Intentions system.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid

from app.core.logger import logger
from app.psfalgo.intent_store import get_intent_store
from app.psfalgo.intent_models import Intent, IntentStatus, IntentAction
from app.psfalgo.execution_engine import get_execution_engine

router = APIRouter(prefix="/api/psfalgo/intents", tags=["Intentions"])


@router.get("", response_model=List[Dict[str, Any]])
async def get_intents(
    status: Optional[str] = Query(None, description="Filter by status (PENDING, APPROVED, REJECTED, SENT, EXPIRED)"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(200, description="Maximum number of intents to return")
) -> List[Dict[str, Any]]:
    """
    Get intents with optional filters.
    
    Returns:
        List of intents (as dictionaries)
    """
    try:
        store = get_intent_store()
        
        # Parse status filter
        status_filter = None
        if status:
            try:
                status_filter = IntentStatus(status.upper())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
        
        # Get intents
        intents = store.get_intents(status=status_filter, symbol=symbol, limit=limit)
        
        # Convert to dict
        return [intent.dict() for intent in intents]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INTENT_API] Error getting intents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{intent_id}", response_model=Dict[str, Any])
async def get_intent(intent_id: str) -> Dict[str, Any]:
    """Get single intent by ID"""
    try:
        store = get_intent_store()
        intent = store.get_intent(intent_id)
        
        if not intent:
            raise HTTPException(status_code=404, detail=f"Intent {intent_id} not found")
        
        return intent.dict()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INTENT_API] Error getting intent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{intent_id}/approve")
async def approve_intent(intent_id: str) -> Dict[str, Any]:
    """
    Approve intent and send to execution.
    
    Returns:
        Execution result
    """
    try:
        store = get_intent_store()
        intent = store.get_intent(intent_id)
        
        if not intent:
            raise HTTPException(status_code=404, detail=f"Intent {intent_id} not found")
        
        if intent.status != IntentStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Intent {intent_id} is not PENDING (current status: {intent.status.value})"
            )
        
        # Update status to APPROVED
        store.update_intent_status(intent_id, IntentStatus.APPROVED)
        
        # Send to ExecutionRouter (ONLY APPROVED intents can reach here)
        execution_result = {}
        from app.execution.execution_router import get_execution_router
        execution_router = get_execution_router()
        
        if execution_router:
            try:
                # Convert intent to order_plan format for ExecutionRouter
                order_plan = {
                    'action': intent.action.value,
                    'symbol': intent.symbol,
                    'qty': intent.qty,
                    'price': intent.price,
                    'order_type': intent.order_type.value,
                    'intent_id': intent_id
                }
                
                # ExecutionRouter will handle based on mode (PREVIEW/SEMI_AUTO/FULL_AUTO)
                # Since we're here, user already approved, so treat as APPROVED
                execution_result = execution_router.handle(
                    order_plan=order_plan,
                    gate_status={'gate_status': 'APPROVED'},  # Intent approval = gate approved
                    user_action='APPROVE',
                    symbol=intent.symbol
                )
                
                # If execution was successful, update intent status to SENT
                if execution_result.get('execution_status') in ['EXECUTED', 'SIMULATED']:
                    store.update_intent_status(
                        intent_id,
                        IntentStatus.SENT,
                        execution_result=execution_result
                    )
                    logger.info(f"[INTENT_API] Intent {intent_id} approved and executed: {execution_result}")
                else:
                    # Execution failed or skipped
                    store.update_intent_status(
                        intent_id,
                        IntentStatus.FAILED,
                        reason=execution_result.get('execution_reason', 'Execution failed')
                    )
                    logger.warning(f"[INTENT_API] Intent {intent_id} approved but execution failed: {execution_result}")
                
            except Exception as e:
                logger.error(f"[INTENT_API] Error executing intent {intent_id}: {e}", exc_info=True)
                store.update_intent_status(intent_id, IntentStatus.FAILED, reason=str(e))
                execution_result = {'error': str(e)}
        else:
            # Fallback to execution_engine if ExecutionRouter not available
            execution_engine = get_execution_engine()
            if execution_engine:
                try:
                    order_plan = {
                        'action': intent.action.value,
                        'symbol': intent.symbol,
                        'qty': intent.qty,
                        'price': intent.price,
                        'order_type': intent.order_type.value,
                        'intent_id': intent_id
                    }
                    result = await execution_engine.execute_plan_from_intent(order_plan)
                    execution_result = result
                    store.update_intent_status(
                        intent_id,
                        IntentStatus.SENT,
                        execution_result=execution_result
                    )
                    logger.info(f"[INTENT_API] Intent {intent_id} approved and executed (via execution_engine): {execution_result}")
                except Exception as e:
                    logger.error(f"[INTENT_API] Error executing intent {intent_id}: {e}", exc_info=True)
                    store.update_intent_status(intent_id, IntentStatus.FAILED, reason=str(e))
                    execution_result = {'error': str(e)}
            else:
                logger.warning(f"[INTENT_API] ExecutionRouter and ExecutionEngine not available, intent {intent_id} approved but not executed")
                execution_result = {'warning': 'ExecutionRouter and ExecutionEngine not available'}
        
        return {
            'success': True,
            'intent_id': intent_id,
            'status': 'APPROVED',
            'execution_result': execution_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INTENT_API] Error approving intent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{intent_id}/reject")
async def reject_intent(intent_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """Reject intent"""
    try:
        store = get_intent_store()
        intent = store.get_intent(intent_id)
        
        if not intent:
            raise HTTPException(status_code=404, detail=f"Intent {intent_id} not found")
        
        if intent.status != IntentStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Intent {intent_id} is not PENDING (current status: {intent.status.value})"
            )
        
        # Update status to REJECTED
        store.update_intent_status(intent_id, IntentStatus.REJECTED, reason=reason or "Rejected by user")
        
        logger.info(f"[INTENT_API] Intent {intent_id} rejected: {reason}")
        
        return {
            'success': True,
            'intent_id': intent_id,
            'status': 'REJECTED'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[INTENT_API] Error rejecting intent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk-approve")
async def bulk_approve_intents(intent_ids: List[str]) -> Dict[str, Any]:
    """Approve multiple intents"""
    try:
        results = []
        for intent_id in intent_ids:
            try:
                result = await approve_intent(intent_id)
                results.append(result)
            except Exception as e:
                results.append({
                    'intent_id': intent_id,
                    'success': False,
                    'error': str(e)
                })
        
        return {
            'success': True,
            'approved': len([r for r in results if r.get('success')]),
            'failed': len([r for r in results if not r.get('success')]),
            'results': results
        }
        
    except Exception as e:
        logger.error(f"[INTENT_API] Error bulk approving intents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear")
async def clear_intents() -> Dict[str, Any]:
    """Clear all intents"""
    try:
        store = get_intent_store()
        count = store.clear_all()
        
        return {
            'success': True,
            'cleared': count
        }
        
    except Exception as e:
        logger.error(f"[INTENT_API] Error clearing intents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/summary")
async def get_intent_stats() -> Dict[str, Any]:
    """Get intent store statistics"""
    try:
        store = get_intent_store()
        stats = store.get_stats()
        
        return {
            'success': True,
            'stats': stats
        }
        
    except Exception as e:
        logger.error(f"[INTENT_API] Error getting stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

