"""
RUNALL State API - Observability & Control Layer

Provides read-only access to RUNALL state and manual controls.
No decision/execution logic changes.

Key Principles:
- Read-only state access
- Manual controls (start/stop/toggle)
- No feedback to decision/execution layers
- Human-readable audit trail
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict

from app.core.logger import logger
from app.psfalgo.runall_engine import RunallEngine
from app.psfalgo.decision_models import DecisionResponse
from app.psfalgo.execution_models import ExecutionPlan


@dataclass
class RunallStateSnapshot:
    """
    RUNALL state snapshot - for observability.
    """
    global_state: str  # IDLE, RUNNING, BLOCKED, ERROR
    cycle_state: str  # INIT, EXPOSURE_CHECK, KARBOTU_RUNNING, etc.
    cycle_id: int
    loop_running: bool
    dry_run_mode: bool
    cycle_start_time: Optional[str] = None  # ISO format
    next_cycle_time: Optional[str] = None  # ISO format
    last_error: Optional[str] = None
    last_error_time: Optional[str] = None
    exposure: Optional[Dict[str, Any]] = None
    timestamp: str = ""  # ISO format
    
    def __post_init__(self):
        """Set timestamp if not provided"""
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class ExecutionObservability:
    """
    Execution observability - last N execution plans.
    """
    cycle_id: int
    source: str  # "KARBOTU", "REDUCEMORE", "ADDNEWPOS"
    execution_timestamp: str  # ISO format
    total_intents: int
    executed_count: int
    skipped_count: int
    error_count: int
    dry_run: bool
    intents: List[Dict[str, Any]] = None  # ExecutionIntent details
    
    def __post_init__(self):
        """Initialize intents list"""
        if self.intents is None:
            self.intents = []


@dataclass
class DecisionObservability:
    """
    Decision observability - last cycle DecisionResponse snapshot (READ-ONLY).
    """
    cycle_id: int
    source: str  # "KARBOTU", "REDUCEMORE", "ADDNEWPOS"
    decision_timestamp: str  # ISO format
    total_decisions: int
    total_filtered: int
    execution_time_ms: float
    decisions: List[Dict[str, Any]] = None  # Decision details
    filtered_out: List[Dict[str, Any]] = None  # Filtered decision details
    step_summary: Dict[str, Any] = None
    
    def __post_init__(self):
        """Initialize lists"""
        if self.decisions is None:
            self.decisions = []
        if self.filtered_out is None:
            self.filtered_out = []
        if self.step_summary is None:
            self.step_summary = {}


class RunallStateAPI:
    """
    RUNALL State API - provides observability and manual controls.
    
    Responsibilities:
    - Read-only state access
    - Manual controls (start/stop/toggle)
    - Execution observability
    - Decision observability (read-only)
    - Audit trail
    
    Does NOT:
    - Modify decision engines
    - Modify execution engine logic
    - Make trading decisions
    """
    
    def __init__(self, runall_engine: Optional[RunallEngine] = None):
        """
        Initialize State API.
        
        Args:
            runall_engine: RunallEngine instance (optional, can be set later)
        """
        self.runall_engine = runall_engine
        
        # Execution observability (last N cycles)
        self._execution_history: List[ExecutionObservability] = []
        self._max_execution_history = 50  # Keep last 50 execution plans
        
        # Decision observability (last cycle)
        self._last_decision_snapshots: Dict[str, DecisionObservability] = {}  # source -> snapshot
        
        # Audit trail (last N cycles)
        self._audit_trail: List[Dict[str, Any]] = []
        self._max_audit_trail = 100  # Keep last 100 audit entries
        
        logger.info("RunallStateAPI initialized")
    
    def set_runall_engine(self, runall_engine: RunallEngine):
        """Set RunallEngine instance"""
        self.runall_engine = runall_engine
        logger.info("RunallStateAPI connected to RunallEngine")
    
    def get_state_snapshot(self) -> Optional[RunallStateSnapshot]:
        """
        Get current RUNALL state snapshot.
        
        Returns:
            RunallStateSnapshot or None if engine not available
        """
        if not self.runall_engine:
            return None
        
        state_dict = self.runall_engine.get_state()
        
        snapshot = RunallStateSnapshot(
            global_state=state_dict.get('global_state', 'IDLE'),
            cycle_state=state_dict.get('cycle_state', 'INIT'),
            cycle_id=state_dict.get('loop_count', 0),
            loop_running=state_dict.get('loop_running', False),
            dry_run_mode=state_dict.get('dry_run_mode', True),
            cycle_start_time=self.runall_engine.cycle_start_time.isoformat() if self.runall_engine.cycle_start_time else None,
            next_cycle_time=self.runall_engine.next_cycle_time.isoformat() if self.runall_engine.next_cycle_time else None,
            last_error=state_dict.get('last_error'),
            last_error_time=self.runall_engine.last_error_time.isoformat() if self.runall_engine.last_error_time else None,
            exposure=asdict(self.runall_engine.current_exposure) if self.runall_engine.current_exposure else None
        )
        
        return snapshot
    
    def get_execution_history(self, last_n: int = 10) -> List[ExecutionObservability]:
        """
        Get last N execution plans.
        
        Args:
            last_n: Number of recent execution plans to return
            
        Returns:
            List of ExecutionObservability objects
        """
        return self._execution_history[-last_n:]
    
    def record_execution_plan(
        self,
        plan: ExecutionPlan,
        source: str
    ):
        """
        Record execution plan for observability.
        
        Args:
            plan: ExecutionPlan to record
            source: "KARBOTU", "REDUCEMORE", or "ADDNEWPOS"
        """
        executed_count = sum(1 for i in plan.intents if i.status.value == "EXECUTED")
        skipped_count = sum(1 for i in plan.intents if i.status.value == "SKIPPED")
        error_count = sum(1 for i in plan.intents if i.status.value == "ERROR")
        
        observability = ExecutionObservability(
            cycle_id=plan.cycle_id,
            source=source,
            execution_timestamp=plan.cycle_timestamp.isoformat(),
            total_intents=plan.total_intents,
            executed_count=executed_count,
            skipped_count=skipped_count,
            error_count=error_count,
            dry_run=plan.dry_run,
            intents=[asdict(intent) for intent in plan.intents]
        )
        
        self._execution_history.append(observability)
        
        # Keep only last N
        if len(self._execution_history) > self._max_execution_history:
            self._execution_history.pop(0)
        
        logger.debug(f"[STATE_API] Recorded execution plan: {source} cycle={plan.cycle_id}, {executed_count} executed")
    
    def get_decision_snapshot(self, source: str) -> Optional[DecisionObservability]:
        """
        Get last cycle DecisionResponse snapshot (READ-ONLY).
        
        Args:
            source: "KARBOTU", "REDUCEMORE", or "ADDNEWPOS"
            
        Returns:
            DecisionObservability or None if not available
        """
        return self._last_decision_snapshots.get(source)
    
    def record_decision_response(
        self,
        response: DecisionResponse,
        cycle_id: int,
        source: str,
        decision_timestamp: datetime
    ):
        """
        Record DecisionResponse snapshot for observability (READ-ONLY).
        
        Args:
            response: DecisionResponse to record
            cycle_id: RUNALL cycle count
            source: "KARBOTU", "REDUCEMORE", or "ADDNEWPOS"
            decision_timestamp: Timestamp of decision
        """
        observability = DecisionObservability(
            cycle_id=cycle_id,
            source=source,
            decision_timestamp=decision_timestamp.isoformat(),
            total_decisions=len(response.decisions),
            total_filtered=len(response.filtered_out),
            execution_time_ms=response.execution_time_ms,
            decisions=[asdict(d) for d in response.decisions],
            filtered_out=[asdict(d) for d in response.filtered_out],
            step_summary=response.step_summary
        )
        
        self._last_decision_snapshots[source] = observability
        
        logger.debug(
            f"[STATE_API] Recorded decision snapshot: {source} cycle={cycle_id}, "
            f"{len(response.decisions)} decisions, {len(response.filtered_out)} filtered"
        )
    
    def add_audit_entry(
        self,
        event: str,
        details: Dict[str, Any],
        cycle_id: Optional[int] = None
    ):
        """
        Add audit trail entry.
        
        Args:
            event: Event name (e.g., "RUNALL_STARTED", "EXECUTION_COMPLETE")
            details: Event details
            cycle_id: Optional cycle ID
        """
        entry = {
            'timestamp': datetime.now().isoformat(),
            'event': event,
            'cycle_id': cycle_id,
            'details': details
        }
        
        self._audit_trail.append(entry)
        
        # Keep only last N
        if len(self._audit_trail) > self._max_audit_trail:
            self._audit_trail.pop(0)
        
        logger.info(f"[AUDIT] {event} (cycle={cycle_id}): {details}")
    
    def get_audit_trail(self, last_n: int = 50) -> List[Dict[str, Any]]:
        """
        Get last N audit trail entries.
        
        Args:
            last_n: Number of recent entries to return
            
        Returns:
            List of audit trail entries
        """
        return self._audit_trail[-last_n:]
    
    # Manual Controls
    
    async def start_runall(self) -> Dict[str, Any]:
        """
        Start RUNALL engine (manual control).
        
        Returns:
            Result dict with status
        """
        if not self.runall_engine:
            return {'success': False, 'error': 'RunallEngine not available'}
        
        try:
            # Trigger FAST score computation before starting (ensure readiness)
            try:
                from app.core.fast_score_calculator import compute_all_fast_scores
                logger.info("[STATE_API] Pre-flight: Computing FAST scores (L1+Group)...")
                compute_all_fast_scores(include_group_metrics=True)
            except Exception as e:
                logger.warning(f"[STATE_API] Pre-flight computation warning: {e}")
                
            await self.runall_engine.start()
            self.add_audit_entry('RUNALL_STARTED', {'manual': True})
            return {'success': True, 'message': 'RUNALL started'}
        except Exception as e:
            logger.error(f"[STATE_API] Error starting RUNALL: {e}", exc_info=True)
            self.add_audit_entry('RUNALL_START_ERROR', {'error': str(e)})
            return {'success': False, 'error': str(e)}
    
    async def stop_runall(self) -> Dict[str, Any]:
        """
        Stop RUNALL engine (manual control).
        
        Returns:
            Result dict with status
        """
        if not self.runall_engine:
            return {'success': False, 'error': 'RunallEngine not available'}
        
        try:
            await self.runall_engine.stop()
            self.add_audit_entry('RUNALL_STOPPED', {'manual': True})
            return {'success': True, 'message': 'RUNALL stopped'}
        except Exception as e:
            logger.error(f"[STATE_API] Error stopping RUNALL: {e}", exc_info=True)
            self.add_audit_entry('RUNALL_STOP_ERROR', {'error': str(e)})
            return {'success': False, 'error': str(e)}
    
    def toggle_dry_run(self) -> Dict[str, Any]:
        """
        Toggle dry-run mode (manual control).
        
        Returns:
            Result dict with new dry_run status
        """
        if not self.runall_engine:
            return {'success': False, 'error': 'RunallEngine not available'}
        
        old_dry_run = self.runall_engine.dry_run_mode
        new_dry_run = not old_dry_run
        
        self.runall_engine.dry_run_mode = new_dry_run
        
        # Update execution engine dry_run mode
        from app.psfalgo.execution_engine import get_execution_engine
        execution_engine = get_execution_engine()
        if execution_engine:
            execution_engine.dry_run = new_dry_run
        
        self.add_audit_entry(
            'DRY_RUN_TOGGLED',
            {'old': old_dry_run, 'new': new_dry_run, 'manual': True}
        )
        
        logger.info(f"[STATE_API] Dry-run mode toggled: {old_dry_run} → {new_dry_run}")
        
        return {
            'success': True,
            'dry_run': new_dry_run,
            'message': f'Dry-run mode: {new_dry_run}'
        }
    
    async def emergency_stop(self) -> Dict[str, Any]:
        """
        Emergency stop - immediately stops RUNALL and execution.
        
        Returns:
            Result dict with status
        """
        if not self.runall_engine:
            return {'success': False, 'error': 'RunallEngine not available'}
        
        try:
            # Stop RUNALL
            await self.runall_engine.stop()
            
            # Mark as emergency stop
            from app.psfalgo.decision_models import RunallState
            self.runall_engine.global_state = RunallState.BLOCKED
            
            self.add_audit_entry('EMERGENCY_STOP', {'manual': True, 'emergency': True})
            
            logger.warning("[STATE_API] EMERGENCY STOP activated")
            
            return {'success': True, 'message': 'Emergency stop activated'}
        except Exception as e:
            logger.error(f"[STATE_API] Error in emergency stop: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}


# Global instance
_runall_state_api: Optional[RunallStateAPI] = None


def get_runall_state_api() -> Optional[RunallStateAPI]:
    """Get global RunallStateAPI instance"""
    return _runall_state_api


def initialize_runall_state_api(runall_engine: Optional[RunallEngine] = None):
    """Initialize global RunallStateAPI instance"""
    global _runall_state_api
    _runall_state_api = RunallStateAPI(runall_engine=runall_engine)
    logger.info("RunallStateAPI initialized")

