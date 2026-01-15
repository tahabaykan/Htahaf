"""
RUNALL Orchestrator - Stateful, Selective Cancel, Phase-Based

Replaces Janall's 2-minute cancel-all loop with modern orchestration:
- State machine with phases (OPEN, LT_TRIM, MM, ADD, MIDDAY, CLOSE)
- Phase tick every N seconds (default 30s) triggers re-evaluation WITHOUT mass-cancel
- Per-symbol memory tracking (CACHE ONLY - order_controller is truth)
- TTL-based + selective cancel per order
- Event-driven, no blocking loops

NEVER "cancel all orders" by default. Only cancel:
a) TTL expired
b) Order stale/invalid
c) Risk regime forces (HARD_DERISK / close-time)
d) Symbol disabled / excluded

=== SINGLE SCHEDULER RULE ===
At runtime, EXACTLY ONE scheduler must be active.
When orchestrator mode = FULL, legacy loops MUST NOT run.

=== PHASE 1: OBSERVE_ONLY ===
In OBSERVE_ONLY mode, NO side effects occur:
- No cancel, no replace, no submit
- Only logs what WOULD happen (would_cancel, would_replace, would_submit)
- symbol_memory write guards raise RuntimeError if violated
"""

import time
import asyncio
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from app.core.logger import logger
from app.state.symbol_memory import (
    SymbolMemoryStore, SymbolMemory, OrderRecord, DecisionRecord,
    set_observe_only_mode, is_observe_only_mode
)
from app.execution.order_lifecycle import OrderLifecyclePolicy, get_order_lifecycle_policy, OrderAction


class OrchestratorMode(Enum):
    """Orchestrator operating modes."""
    OBSERVE_ONLY = "OBSERVE_ONLY"       # Logs what would happen, doesn't act
    SELECTIVE_ONLY = "SELECTIVE_ONLY"   # TTL cancels only, legacy makes decisions
    FULL = "FULL"                       # Sole scheduler (legacy disabled)


class Phase(Enum):
    """Trading day phases."""
    PRE_MARKET = "PRE_MARKET"
    OPEN = "OPEN"           # First 30 min
    LT_TRIM = "LT_TRIM"     # LT mean-reversion phase
    MM = "MM"               # Market making / churn
    ADD = "ADD"             # Add new positions
    MIDDAY = "MIDDAY"       # Midday consolidation
    CLOSE = "CLOSE"         # End of day
    AFTER_HOURS = "AFTER_HOURS"


@dataclass
class PhaseConfig:
    """Configuration for a trading phase."""
    start_time: str  # "HH:MM"
    end_time: str    # "HH:MM"
    engines_enabled: List[str]  # Which engines run in this phase
    allow_new_positions: bool = True
    allow_lt_trim: bool = True
    allow_mm_churn: bool = True


class RunallOrchestrator:
    """
    Main orchestrator for stateful, selective-cancel trading loop.
    
    CRITICAL: symbol_memory is CACHE ONLY for analytics.
    order_controller is the SINGLE SOURCE OF TRUTH for orders.
    
    Coordinates:
    - LTTrimEngine
    - MMChurnEngine
    - AddNewPos logic (future)
    - HardExitEngine (always supreme)
    """
    
    # Default phase schedule (Eastern Time)
    DEFAULT_PHASES = {
        Phase.PRE_MARKET: PhaseConfig("04:00", "09:30", [], False, False, False),
        Phase.OPEN: PhaseConfig("09:30", "10:00", ["LT_TRIM", "MM_CHURN"], True, True, True),
        Phase.LT_TRIM: PhaseConfig("10:00", "11:30", ["LT_TRIM", "MM_CHURN", "ADDNEWPOS"], True, True, True),
        Phase.MM: PhaseConfig("11:30", "14:00", ["MM_CHURN", "ADDNEWPOS"], True, True, True),
        Phase.MIDDAY: PhaseConfig("14:00", "15:00", ["LT_TRIM", "MM_CHURN"], True, True, True),
        Phase.CLOSE: PhaseConfig("15:00", "16:00", ["LT_TRIM", "HARD_EXIT"], False, True, False),
        Phase.AFTER_HOURS: PhaseConfig("16:00", "20:00", [], False, False, False),
    }
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        
        # Parse mode
        mode_str = self.config.get('mode', 'OBSERVE_ONLY')
        try:
            self.mode = OrchestratorMode(mode_str)
        except ValueError:
            self.mode = OrchestratorMode.OBSERVE_ONLY
            logger.warning(f"[RUNALL_ORCH] Invalid mode '{mode_str}', defaulting to OBSERVE_ONLY")
        
        # PHASE 1: Set OBSERVE_ONLY guard flag in symbol_memory
        # This will cause RuntimeError if any code tries to write order state
        if self.mode == OrchestratorMode.OBSERVE_ONLY:
            set_observe_only_mode(True)
            logger.info("[RUNALL_ORCH] OBSERVE_ONLY mode active - symbol_memory order writes will FAIL LOUD")
        else:
            set_observe_only_mode(False)
        
        self.phase_tick_seconds = self.config.get('phase_tick_seconds', 30)
        self.persist_memory = self.config.get('persist_symbol_memory', True)
        self.memory_flush_interval = self.config.get('memory_flush_interval_seconds', 300)
        self.selective_cancel_enabled = self.config.get('selective_cancel_enabled', False)
        
        # State
        # NOTE: memory_store is CACHE ONLY for analytics/history
        # order_controller is the SINGLE SOURCE OF TRUTH for orders
        self.memory_store = SymbolMemoryStore()
        self.lifecycle_policy = get_order_lifecycle_policy(config)
        self.current_phase = Phase.PRE_MARKET
        self.current_regime = "NORMAL"
        self.excluded_symbols: Set[str] = set()
        
        # Tick tracking
        self._last_tick_ts: float = 0.0
        self._tick_count: int = 0
        
        # Engine references (set externally)
        self.lt_trim_engine = None
        self.mm_churn_engine = None
        self.hard_exit_engine = None
        self.decision_engine = None
        
        # Callbacks for execution (MUST query order_controller, not local state)
        self._cancel_order_fn: Optional[Callable] = None
        self._replace_order_fn: Optional[Callable] = None
        self._get_active_orders_fn: Optional[Callable] = None
        
        logger.info(f"[RUNALL_ORCH] Initialized. Mode: {self.mode.value}, Tick: {self.phase_tick_seconds}s")
    

    @staticmethod
    def check_single_scheduler(psfalgo_config: Dict[str, Any], orchestrator_config: Dict[str, Any]):
        """
        STARTUP GUARD: Enforce single scheduler rule.
        
        Raises RuntimeError if FULL mode + legacy enabled.
        """
        orch_mode = orchestrator_config.get('mode', 'OBSERVE_ONLY')
        legacy_runall = psfalgo_config.get('legacy_runall_enabled', True)
        legacy_autocycle = psfalgo_config.get('legacy_autocycle_enabled', True)
        
        if orch_mode == 'FULL':
            if legacy_runall:
                raise RuntimeError(
                    "FATAL: Orchestrator mode=FULL but psfalgo.legacy_runall_enabled=true. "
                    "Set legacy_runall_enabled=false or use mode=SELECTIVE_ONLY."
                )
            if legacy_autocycle:
                raise RuntimeError(
                    "FATAL: Orchestrator mode=FULL but psfalgo.legacy_autocycle_enabled=true. "
                    "Set legacy_autocycle_enabled=false."
                )
        
        logger.info(f"[RUNALL_ORCH] Single scheduler check passed. Mode={orch_mode}, LegacyRunall={legacy_runall}")
    
    def set_execution_callbacks(
        self,
        cancel_fn: Callable,
        replace_fn: Callable,
        get_orders_fn: Callable
    ):
        """
        Set callbacks for order execution.
        
        get_orders_fn MUST return orders from order_controller (single truth).
        """
        self._cancel_order_fn = cancel_fn
        self._replace_order_fn = replace_fn
        self._get_active_orders_fn = get_orders_fn
    
    def set_engines(
        self,
        lt_trim_engine=None,
        mm_churn_engine=None,
        hard_exit_engine=None,
        decision_engine=None
    ):
        """Set engine references."""
        self.lt_trim_engine = lt_trim_engine
        self.mm_churn_engine = mm_churn_engine
        self.hard_exit_engine = hard_exit_engine
        self.decision_engine = decision_engine
    
    def update_regime(self, regime: str):
        """Update current risk regime."""
        if self.current_regime != regime:
            logger.info(f"[RUNALL_ORCH] Regime changed: {self.current_regime} -> {regime}")
            self.memory_store.log_event("REGIME_CHANGE", {
                'old_regime': self.current_regime,
                'new_regime': regime
            })
        self.current_regime = regime
    
    def update_excluded(self, symbols: Set[str]):
        """Update excluded symbol set."""
        self.excluded_symbols = symbols
        self.memory_store.set_excluded(symbols)
    
    def _determine_phase(self) -> Phase:
        """Determine current phase based on time of day."""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        for phase, cfg in self.DEFAULT_PHASES.items():
            if cfg.start_time <= current_time < cfg.end_time:
                return phase
        
        return Phase.AFTER_HOURS
    
    def tick(self) -> Dict[str, Any]:
        """
        Main phase tick - called every PHASE_TICK_SECONDS.
        
        MODE determines behavior:
        - OBSERVE_ONLY: Log what would happen, don't act
        - SELECTIVE_ONLY: TTL cancels only
        - FULL: Full orchestration
        
        Returns summary of actions taken.
        """
        if not self.enabled:
            return {'status': 'DISABLED'}
        
        now = time.time()
        self._tick_count += 1
        
        # Determine phase
        new_phase = self._determine_phase()
        if new_phase != self.current_phase:
            logger.info(f"[RUNALL_ORCH] Phase transition: {self.current_phase.value} -> {new_phase.value}")
            self.memory_store.log_event("PHASE_CHANGE", {
                'old_phase': self.current_phase.value,
                'new_phase': new_phase.value
            })
            self.current_phase = new_phase
        
        # Skip if not in trading phase
        if self.current_phase in (Phase.PRE_MARKET, Phase.AFTER_HOURS):
            return {'status': 'NON_TRADING_PHASE', 'phase': self.current_phase.value}
        
        summary = {
            'tick': self._tick_count,
            'phase': self.current_phase.value,
            'regime': self.current_regime,
            'mode': self.mode.value,
            'actions': []
        }
        
        try:
            # 1. Selective cancel pass (TTL, stale, excluded)
            if self.mode == OrchestratorMode.OBSERVE_ONLY:
                # Log what would happen, don't act
                cancel_summary = self._run_selective_cancel_observe_only()
                summary['selective_cancel'] = cancel_summary
            elif self.selective_cancel_enabled:
                cancel_summary = self._run_selective_cancel()
                summary['selective_cancel'] = cancel_summary
            
            # 2. Run enabled engines based on phase (only in FULL mode)
            if self.mode == OrchestratorMode.FULL:
                phase_cfg = self.DEFAULT_PHASES.get(self.current_phase)
                if phase_cfg:
                    engine_summary = self._run_engines(phase_cfg.engines_enabled)
                    summary['engines'] = engine_summary
            
            # 3. Persist memory if interval elapsed (always - cache)
            self.memory_store.flush_csv_snapshot(
                force=False, 
                interval=self.memory_flush_interval
            )
            
            # 4. Log tick event
            self.memory_store.log_event("TICK", {
                'tick': self._tick_count,
                'phase': self.current_phase.value,
                'regime': self.current_regime,
                'mode': self.mode.value,
                'summary': self.memory_store.get_summary()
            })
            
        except Exception as e:
            logger.error(f"[RUNALL_ORCH] Tick error: {e}", exc_info=True)
            summary['error'] = str(e)
        
        self._last_tick_ts = now
        return summary
    
    def _run_selective_cancel_observe_only(self) -> Dict[str, Any]:
        """
        OBSERVE mode: Log what cancels WOULD happen.
        Does NOT actually cancel, replace, or submit.
        
        Logs each decision with ChatGPT's audit contract:
        - would_cancel, would_replace, would_submit (all actions)
        - ttl_remaining, derisk_state, notes
        """
        if not self._get_active_orders_fn:
            return {'status': 'NO_ORDER_FN'}
        
        # Get active orders from order_controller (single truth)
        active_orders = self._get_active_orders_fn()
        if not active_orders:
            return {'active_orders': 0, 'would_cancel': 0, 'would_replace': 0, 'would_submit': 0}
        
        # Build symbol states from cache
        symbol_states = {}
        for sym, mem in self.memory_store.memories.items():
            symbol_states[sym] = {
                'position_qty': mem.position_qty,
                'bid': mem.last_truth.bid,
                'ask': mem.last_truth.ask,
                'truth_age': mem.truth_age,
            }
        
        # Map derisk_state from regime
        derisk_state = "NONE"
        if self.current_regime == "HARD_DERISK":
            derisk_state = "HARD"
        elif self.current_regime == "SOFT_DERISK":
            derisk_state = "SOFT"
        
        # Evaluate orders
        decisions = self.lifecycle_policy.evaluate_orders(
            active_orders=active_orders,
            symbol_states=symbol_states,
            regime=self.current_regime,
            excluded_symbols=self.excluded_symbols
        )
        
        # Log each decision with structured audit contract
        would_cancel = 0
        would_replace = 0  # Replace detection would go here
        would_submit = 0   # New order detection in HARD_DERISK
        
        for i, d in enumerate(decisions):
            order = active_orders[i] if i < len(active_orders) else {}
            symbol = d.symbol
            order_id = d.order_id
            
            # Calculate TTL remaining
            created_ts = order.get('created_ts', 0)
            ttl = self.lifecycle_policy.get_ttl(order.get('intent_category', 'DEFAULT'))
            ttl_remaining = max(0, (created_ts + ttl) - time.time()) if created_ts > 0 else 0
            
            is_cancel = d.action == OrderAction.CANCEL
            if is_cancel:
                would_cancel += 1
            
            # Check if HARD_DERISK would allow submit (never in OBSERVE)
            would_submit_this = False
            if derisk_state == "HARD" and order.get('side') in ['SELL', 'BUY']:
                # In HARD_DERISK, would_submit should never be true
                would_submit_this = False
            
            # Log structured audit record
            self.memory_store.log_observe_action(
                symbol=symbol,
                engine=order.get('intent_category', 'UNKNOWN'),
                intent_id=order.get('intent_id', ''),
                intent_reason=d.reason,
                order_id=order_id,
                order_state=order.get('status', 'ACTIVE'),
                ttl_remaining=ttl_remaining,
                would_cancel=is_cancel,
                would_replace=False,  # Replace evaluated separately
                would_submit=would_submit_this,
                derisk_state=derisk_state,
                notes=d.reason
            )
        
        if would_cancel > 0:
            logger.info(f"[RUNALL_ORCH] OBSERVE_ONLY: Would cancel {would_cancel}/{len(decisions)} orders")
        
        return {
            'active_orders': len(active_orders),
            'evaluated': len(decisions),
            'would_cancel': would_cancel,
            'would_replace': would_replace,
            'would_submit': would_submit,
            'would_keep': len(decisions) - would_cancel
        }
    

    def _run_selective_cancel(self) -> Dict[str, Any]:
        """
        Run selective cancel evaluation.
        
        Uses OrderLifecyclePolicy to decide KEEP/CANCEL per order.
        Queries order_controller for active orders (single truth).
        """
        if not self._get_active_orders_fn:
            return {'status': 'NO_ORDER_FN'}
        
        # Get active orders from order_controller (SINGLE SOURCE OF TRUTH)
        active_orders = self._get_active_orders_fn()
        if not active_orders:
            return {'active_orders': 0, 'cancelled': 0}
        
        # Build symbol states from cache (for stale detection)
        symbol_states = {}
        for sym, mem in self.memory_store.memories.items():
            symbol_states[sym] = {
                'position_qty': mem.position_qty,
                'bid': mem.last_truth.bid,
                'ask': mem.last_truth.ask,
                'truth_age': mem.truth_age,
            }
        
        # Evaluate orders
        decisions = self.lifecycle_policy.evaluate_orders(
            active_orders=active_orders,
            symbol_states=symbol_states,
            regime=self.current_regime,
            excluded_symbols=self.excluded_symbols
        )
        
        # Execute cancels
        cancelled = 0
        kept = 0
        for d in decisions:
            if d.action == OrderAction.CANCEL:
                if self._cancel_order_fn:
                    try:
                        self._cancel_order_fn(d.order_id, d.reason)
                        cancelled += 1
                        logger.debug(f"[RUNALL_ORCH] Cancelled {d.order_id}: {d.reason}")
                    except Exception as e:
                        logger.warning(f"[RUNALL_ORCH] Cancel failed {d.order_id}: {e}")
            else:
                kept += 1
        
        return {
            'active_orders': len(active_orders),
            'evaluated': len(decisions),
            'cancelled': cancelled,
            'kept': kept
        }
    
    def _run_engines(self, enabled_engines: List[str]) -> Dict[str, Any]:
        """
        Run enabled engines for current phase.
        
        Engines generate intents; orchestrator doesn't mass-cancel.
        """
        results = {}
        
        # HARD_DERISK always takes precedence
        if self.current_regime == "HARD_DERISK":
            if self.hard_exit_engine:
                results['HARD_EXIT'] = {'status': 'ACTIVE_HARD_DERISK'}
            return results
        
        # LT_TRIM
        if "LT_TRIM" in enabled_engines and self.lt_trim_engine:
            # LT Trim is called via DecisionEngine phase, not directly here
            results['LT_TRIM'] = {'status': 'DELEGATED_TO_DECISION_ENGINE'}
        
        # MM_CHURN
        if "MM_CHURN" in enabled_engines and self.mm_churn_engine:
            results['MM_CHURN'] = {'status': 'DELEGATED_TO_DECISION_ENGINE'}
        
        # ADDNEWPOS
        if "ADDNEWPOS" in enabled_engines:
            phase_cfg = self.DEFAULT_PHASES.get(self.current_phase)
            if phase_cfg and phase_cfg.allow_new_positions:
                results['ADDNEWPOS'] = {'status': 'ALLOWED'}
            else:
                results['ADDNEWPOS'] = {'status': 'BLOCKED_BY_PHASE'}
        
        return results
    
    def force_cancel_all(self, reason: str = "MANUAL_EMERGENCY"):
        """
        Emergency cancel-all (MANUAL USE ONLY, NOT DEFAULT PATH).
        
        Behind config flag, for emergency situations only.
        """
        if not self.config.get('allow_emergency_cancel_all', False):
            logger.warning("[RUNALL_ORCH] Emergency cancel-all blocked by config")
            return
        
        logger.warning(f"[RUNALL_ORCH] EMERGENCY CANCEL ALL: {reason}")
        self.memory_store.log_event("EMERGENCY_CANCEL_ALL", {'reason': reason})
        
        if self._get_active_orders_fn and self._cancel_order_fn:
            active_orders = self._get_active_orders_fn()
            for order in active_orders:
                try:
                    self._cancel_order_fn(order['order_id'], f"EMERGENCY:{reason}")
                except Exception as e:
                    logger.error(f"[RUNALL_ORCH] Emergency cancel failed: {e}")
    
    async def start_async_loop(self):
        """
        Start async tick loop (for event-driven operation).
        
        This is the preferred way to run - no blocking.
        """
        logger.info(f"[RUNALL_ORCH] Starting async loop, mode: {self.mode.value}, interval: {self.phase_tick_seconds}s")
        
        while self.enabled:
            try:
                summary = self.tick()
                logger.debug(f"[RUNALL_ORCH] Tick summary: {summary}")
            except Exception as e:
                logger.error(f"[RUNALL_ORCH] Async tick error: {e}")
            
            await asyncio.sleep(self.phase_tick_seconds)
    
    def shutdown(self):
        """Clean shutdown - flush state."""
        logger.info("[RUNALL_ORCH] Shutting down...")
        self.enabled = False
        self.memory_store.flush_csv_snapshot(force=True)
        self.memory_store.log_event("SHUTDOWN", {'tick_count': self._tick_count})


# Singleton
_orchestrator_instance: Optional[RunallOrchestrator] = None

def get_runall_orchestrator(config: Dict[str, Any] = None) -> RunallOrchestrator:
    """Get or create orchestrator instance."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = RunallOrchestrator(config)
    return _orchestrator_instance
