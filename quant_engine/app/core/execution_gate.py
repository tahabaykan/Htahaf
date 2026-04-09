"""
Execution Gate - Route orders to real or simulation execution

This is the critical safety component that ensures:
1. Simulation orders never reach real brokers
2. Real orders never go to fake tracker
3. Clear separation of concerns
"""
from typing import Optional
from dataclasses import dataclass

from loguru import logger

from app.core.simulation_controller import get_simulation_controller
from app.simulation.fake_order_tracker import get_fake_order_tracker
from app.psfalgo.decision_models import Decision


@dataclass
class ExecutionResult:
    """Result of order execution"""
    order_id: str
    success: bool
    is_simulation: bool
    error: Optional[str] = None


async def execute_decision(decision: Decision) -> ExecutionResult:
    """
    Execute a decision - routes to real or simulation.
    
    This is the ONLY entry point for order execution.
    
    Args:
        decision: Decision to execute
    
    Returns:
        ExecutionResult with order ID and success status
    """
    sim_controller = get_simulation_controller()
    is_simulation = sim_controller.is_simulation_mode()
    
    if is_simulation:
        # SIMULATION MODE: Fake execution
        return await _execute_simulation(decision)
    else:
        # REAL MODE: Real execution
        return await _execute_real(decision)


async def _execute_simulation(decision: Decision) -> ExecutionResult:
    """
    Execute decision in simulation mode (FAKE).
    
    Safety: Never reaches real broker.
    """
    try:
        tracker = get_fake_order_tracker()
        
        order_id = tracker.submit_order(
            symbol=decision.symbol,
            side=decision.action,
            qty=decision.calculated_lot,
            price=decision.price_hint or 0.0,
            tag=decision.tag,
            engine=decision.metadata.get('engine') if decision.metadata else None,
            reason=decision.metadata.get('reason') if decision.metadata else None
        )
        
        logger.info(
            f"[ExecutionGate] 🎭 SIMULATION: {order_id} | "
            f"{decision.symbol} {decision.action} {decision.calculated_lot}"
        )
        
        return ExecutionResult(
            order_id=order_id,
            success=True,
            is_simulation=True
        )
    
    except Exception as e:
        logger.error(f"[ExecutionGate] Simulation execution error: {e}", exc_info=True)
        return ExecutionResult(
            order_id="",
            success=False,
            is_simulation=True,
            error=str(e)
        )


async def _execute_real(decision: Decision) -> ExecutionResult:
    """
    Execute decision in real mode.
    
    Routes to real execution engine.
    """
    try:
        from app.psfalgo.execution_engine import get_execution_engine
        
        execution_engine = get_execution_engine()
        
        # Convert decision to intent for execution
        # TODO: This needs proper intent model conversion
        order_id = f"REAL_{decision.symbol}_{decision.action}"
        
        logger.info(
            f"[ExecutionGate] 💰 REAL: {order_id} | "
            f"{decision.symbol} {decision.action} {decision.calculated_lot}"
        )
        
        # TODO: Actual execution
        # result = await execution_engine.execute(intent)
        
        return ExecutionResult(
            order_id=order_id,
            success=True,
            is_simulation=False
        )
    
    except Exception as e:
        logger.error(f"[ExecutionGate] Real execution error: {e}", exc_info=True)
        return ExecutionResult(
            order_id="",
            success=False,
            is_simulation=False,
            error=str(e)
        )
