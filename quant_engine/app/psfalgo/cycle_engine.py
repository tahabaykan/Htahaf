"""
PSFALGO Cycle Engine (RUNALL)
SHADOW MODE ONLY - Simulates full PSFALGO cycle without broker execution.

Cycle steps:
1. Read ExposureMode for all symbols
2. Run PSFALGOActionPlanner
3. Filter HOLD/BLOCKED actions
4. Produce cycle_action_list
5. Wait for approval (manual)
6. On approve: write all actions to ExecutionLedger
7. ShadowPositionStore updates automatically
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio
import threading
from app.core.logger import logger
from app.psfalgo.action_planner import PSFALGOActionPlanner
from app.psfalgo.execution_ledger import PSFALGOExecutionLedger
from app.psfalgo.shadow_position_store import ShadowPositionStore


class PSFALGOCycleEngine:
    """
    PSFALGO Cycle Engine - RUNALL in SHADOW MODE.
    
    Simulates full PSFALGO decision cycle:
    - Reads ExposureMode
    - Runs ActionPlanner
    - Produces action list
    - Waits for approval
    - Writes to ledger on approval
    """
    
    def __init__(
        self,
        action_planner: Optional[PSFALGOActionPlanner] = None,
        ledger: Optional[PSFALGOExecutionLedger] = None,
        shadow_store: Optional[ShadowPositionStore] = None
    ):
        """
        Initialize cycle engine.
        
        Args:
            action_planner: PSFALGOActionPlanner instance
            ledger: PSFALGOExecutionLedger instance
            shadow_store: ShadowPositionStore instance
        """
        self.action_planner = action_planner or PSFALGOActionPlanner()
        self.ledger = ledger or PSFALGOExecutionLedger()
        self.shadow_store = shadow_store or ShadowPositionStore(self.ledger)
        
        # Current cycle state
        self.current_cycle: Optional[Dict[str, Any]] = None
        self.cycle_history: List[Dict[str, Any]] = []
        
        # Execution tracking per cycle
        self.cycle_execution_stats: Dict[str, Dict[str, Any]] = {}  # {cycle_id: {simulated_count, executed_count, blocked_count}}
        
        # AutoCycle state
        self._autocycle_running = False
        self._autocycle_thread: Optional[threading.Thread] = None
        self._autocycle_interval = 120  # Default: 120 seconds
        self._autocycle_last_run: Optional[datetime] = None
        self._autocycle_lock = threading.Lock()
        self._autocycle_blocked_reason: Optional[str] = None  # Why AutoCycle is waiting
    
    def run_cycle(
        self,
        symbols: List[str],
        merged_data: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Run a PSFALGO cycle (RUNALL).
        
        Args:
            symbols: List of symbols to process
            merged_data: Dict of {symbol: merged_data_dict} containing:
                - exposure_mode
                - psfalgo_action_plan
                - position_analytics
                - psfalgo_snapshot
                - psfalgo_guards
                - market_data
                - static_data
                - signal_data
                - grpan_metrics
                
        Returns:
            Cycle result dict with:
                - cycle_id: str
                - cycle_timestamp: str
                - status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED'
                - action_count: int
                - actions: List[action_dicts]
                - exposure_before: Dict
                - exposure_after: Dict (if approved)
        """
        try:
            cycle_id = f"cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            cycle_timestamp = datetime.now().isoformat()
            
            # Get exposure before
            exposure_before = self.shadow_store.get_exposure_summary()
            
            # Step 1-3: Run ActionPlanner and filter actions
            cycle_actions = []
            
            for symbol in symbols:
                symbol_data = merged_data.get(symbol, {})
                
                # Skip if no merged data
                if not symbol_data:
                    continue
                
                # Get exposure mode
                exposure_mode = symbol_data.get('exposure_mode', {})
                exposure_mode_value = exposure_mode.get('mode', 'DEFENSIVE')
                
                # Get existing action plan (already computed)
                action_plan = symbol_data.get('psfalgo_action_plan', {})
                action = action_plan.get('action')
                
                # Filter: Skip HOLD and BLOCKED
                if action in ['HOLD', 'BLOCKED']:
                    continue
                
                # TEMPORARY: Disable SHORT execution paths (phase 1 rollout)
                # ActionPlanner still computes them, but Cycle Engine marks them as HOLD
                if action in ['ADD_SHORT', 'REDUCE_SHORT']:
                    logger.debug(f"PSFALGO Cycle: {symbol} - {action} disabled (SHORT execution disabled - phase 1 rollout)")
                    continue  # Skip SHORT actions (treat as HOLD)
                
                # Prepare action for cycle
                cycle_action = {
                    'symbol': symbol,
                    'psfalgo_action': action,
                    'size_percent': action_plan.get('size_percent', 0.0),
                    'size_lot_estimate': action_plan.get('size_lot_estimate', 0),
                    'exposure_mode': exposure_mode,
                    'guard_status': symbol_data.get('guard_status'),
                    'action_reason': action_plan.get('reason'),
                    'position_snapshot': {
                        'befday_qty': symbol_data.get('befday_qty'),
                        'current_qty': symbol_data.get('current_qty'),
                        'potential_qty': symbol_data.get('potential_qty')
                    }
                }
                
                cycle_actions.append(cycle_action)
            
            # Compute cycle summary
            cycle_summary = self._compute_cycle_summary(cycle_actions, exposure_before, None)
            
            # Create cycle record
            cycle = {
                'cycle_id': cycle_id,
                'cycle_timestamp': cycle_timestamp,
                'status': 'PENDING_APPROVAL',
                'action_count': len(cycle_actions),
                'actions': cycle_actions,
                'exposure_before': exposure_before,
                'exposure_after': None,
                'cycle_summary': cycle_summary
            }
            
            # Store as current cycle
            self.current_cycle = cycle
            
            logger.info(f"PSFALGO Cycle {cycle_id}: Generated {len(cycle_actions)} actions (PENDING_APPROVAL)")
            
            return cycle
            
        except Exception as e:
            logger.error(f"Error running PSFALGO cycle: {e}", exc_info=True)
            return {
                'cycle_id': None,
                'cycle_timestamp': datetime.now().isoformat(),
                'status': 'ERROR',
                'action_count': 0,
                'actions': [],
                'exposure_before': None,
                'exposure_after': None,
                'error': str(e)
            }
    
    def approve_cycle(self, cycle_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Approve current cycle and write actions to ledger.
        
        Args:
            cycle_id: Optional cycle ID. If None, uses current_cycle.
            
        Returns:
            Approval result dict
        """
        try:
            # Get cycle to approve
            cycle = None
            if cycle_id:
                # Find in history
                for c in self.cycle_history:
                    if c['cycle_id'] == cycle_id:
                        cycle = c
                        break
            else:
                cycle = self.current_cycle
            
            if not cycle:
                return {
                    'success': False,
                    'error': 'No cycle found to approve'
                }
            
            if cycle['status'] != 'PENDING_APPROVAL':
                return {
                    'success': False,
                    'error': f"Cycle {cycle['cycle_id']} is not in PENDING_APPROVAL status"
                }
            
            # Write all actions to ledger
            approved_count = 0
            for action in cycle['actions']:
                success = self.ledger.add_entry(
                    symbol=action['symbol'],
                    psfalgo_action=action['psfalgo_action'],
                    size_percent=action['size_percent'],
                    size_lot_estimate=action['size_lot_estimate'],
                    exposure_mode=action.get('exposure_mode'),
                    guard_status=action.get('guard_status'),
                    action_reason=action.get('action_reason'),
                    position_snapshot=action.get('position_snapshot'),
                    cycle_id=cycle['cycle_id'],
                    cycle_timestamp=cycle['cycle_timestamp']
                )
                
                if success:
                    approved_count += 1
            
            # Invalidate shadow store cache to force recomputation
            self.shadow_store.invalidate_cache()
            
            # Get exposure after
            exposure_after = self.shadow_store.get_exposure_summary()
            
            # Check execution mode before routing to execution pipeline
            execution_results = {}
            try:
                from app.execution.execution_router import ExecutionRouter, ExecutionMode
                from app.trading.trading_account_context import get_trading_context, TradingAccountMode
                from app.api.market_data_routes import get_execution_router
                
                execution_router = get_execution_router()
                if execution_router:
                    execution_mode = execution_router.get_mode()
                    trading_context = get_trading_context()
                    trading_mode = trading_context.trading_mode
                    
                    # Only route to execution pipeline in SEMI_AUTO + HAMMER_TRADING
                    if execution_mode == ExecutionMode.SEMI_AUTO and trading_mode == TradingAccountMode.HAMMER_TRADING:
                        # Mark AutoCycle as execution in progress
                        with self._autocycle_lock:
                            if self._autocycle_running:
                                self._autocycle_blocked_reason = 'EXECUTION_IN_PROGRESS'
                        
                        # Generate execution candidates and route through execution pipeline
                        execution_results = self._route_cycle_to_execution(cycle)
                        
                        # Clear execution in progress after routing completes
                        with self._autocycle_lock:
                            if self._autocycle_blocked_reason == 'EXECUTION_IN_PROGRESS':
                                self._autocycle_blocked_reason = None
                    else:
                        # PREVIEW mode or other modes: skip execution routing
                        execution_results = {
                            'simulated_count': 0,
                            'executed_count': 0,
                            'blocked_count': 0,
                            'skipped_count': len(cycle['actions']),
                            'reason': f'Preview mode or non-Hammer mode - execution routing skipped (execution_mode={execution_mode.value if execution_mode else "N/A"}, trading_mode={trading_mode.value if trading_mode else "N/A"})'
                        }
                else:
                    # No execution router available
                    execution_results = {
                        'simulated_count': 0,
                        'executed_count': 0,
                        'blocked_count': 0,
                        'skipped_count': len(cycle['actions']),
                        'reason': 'ExecutionRouter not available - execution routing skipped'
                    }
            except Exception as e:
                logger.warning(f"Error checking execution mode in approve_cycle: {e}")
                execution_results = {
                    'simulated_count': 0,
                    'executed_count': 0,
                    'blocked_count': 0,
                    'skipped_count': len(cycle['actions']),
                    'reason': f'Error checking execution mode: {str(e)}'
                }
            
            # Update cycle status
            cycle['status'] = 'APPROVED'
            cycle['exposure_after'] = exposure_after
            cycle['approved_count'] = approved_count
            cycle['approved_timestamp'] = datetime.now().isoformat()
            cycle['execution_results'] = execution_results
            
            # Update cycle summary with exposure_after
            cycle['cycle_summary'] = self._compute_cycle_summary(
                cycle['actions'],
                cycle['exposure_before'],
                exposure_after
            )
            
            # Track execution stats
            self.cycle_execution_stats[cycle['cycle_id']] = {
                'simulated_count': execution_results.get('simulated_count', 0),
                'executed_count': execution_results.get('executed_count', 0),
                'blocked_count': execution_results.get('blocked_count', 0),
                'skipped_count': execution_results.get('skipped_count', 0)
            }
            
            # Move to history
            self.cycle_history.append(cycle)
            self.current_cycle = None
            
            logger.info(f"PSFALGO Cycle {cycle['cycle_id']}: Approved {approved_count} actions, Execution: {execution_results.get('simulated_count', 0)} simulated, {execution_results.get('executed_count', 0)} executed")
            
            return {
                'success': True,
                'cycle_id': cycle['cycle_id'],
                'approved_count': approved_count,
                'exposure_before': cycle['exposure_before'],
                'exposure_after': exposure_after,
                'execution_results': execution_results
            }
            
        except Exception as e:
            logger.error(f"Error approving PSFALGO cycle: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def reject_cycle(self, cycle_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Reject current cycle (no ledger write).
        
        Args:
            cycle_id: Optional cycle ID. If None, uses current_cycle.
            
        Returns:
            Rejection result dict
        """
        try:
            cycle = None
            if cycle_id:
                for c in self.cycle_history:
                    if c['cycle_id'] == cycle_id:
                        cycle = c
                        break
            else:
                cycle = self.current_cycle
            
            if not cycle:
                return {
                    'success': False,
                    'error': 'No cycle found to reject'
                }
            
            if cycle['status'] != 'PENDING_APPROVAL':
                return {
                    'success': False,
                    'error': f"Cycle {cycle['cycle_id']} is not in PENDING_APPROVAL status"
                }
            
            # Update cycle status
            cycle['status'] = 'REJECTED'
            cycle['rejected_timestamp'] = datetime.now().isoformat()
            
            # Move to history
            self.cycle_history.append(cycle)
            self.current_cycle = None
            
            # Clear AutoCycle blocked_reason after rejection
            with self._autocycle_lock:
                if self._autocycle_blocked_reason == 'PENDING_APPROVAL':
                    self._autocycle_blocked_reason = None
            
            logger.info(f"PSFALGO Cycle {cycle['cycle_id']}: Rejected")
            
            return {
                'success': True,
                'cycle_id': cycle['cycle_id']
            }
            
        except Exception as e:
            logger.error(f"Error rejecting PSFALGO cycle: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_cycle_status(self) -> Dict[str, Any]:
        """
        Get current cycle status.
        
        Returns:
            Status dict with current cycle and last cycle info
        """
        last_cycle = self.cycle_history[-1] if self.cycle_history else None
        
        return {
            'current_cycle': self.current_cycle,
            'last_cycle': last_cycle,
            'cycle_count': len(self.cycle_history)
        }
    
    def start_autocycle(self, interval_seconds: int = 120) -> Dict[str, Any]:
        """
        Start AutoCycle loop (SHADOW MODE ONLY).
        
        Args:
            interval_seconds: Interval between cycles in seconds (default: 120)
            
        Returns:
            Status dict
        """
        with self._autocycle_lock:
            if self._autocycle_running:
                return {
                    'success': False,
                    'error': 'AutoCycle is already running'
                }
            
            self._autocycle_interval = interval_seconds
            self._autocycle_running = True
            self._autocycle_blocked_reason = None  # Clear blocked reason on start
            
            # Start background thread
            self._autocycle_thread = threading.Thread(
                target=self._autocycle_loop,
                daemon=True,
                name="PSFALGO-AutoCycle"
            )
            self._autocycle_thread.start()
            
            logger.info(f"PSFALGO AutoCycle started with interval: {interval_seconds}s")
            
            return {
                'success': True,
                'interval_seconds': interval_seconds,
                'status': 'RUNNING'
            }
    
    def stop_autocycle(self) -> Dict[str, Any]:
        """
        Stop AutoCycle loop.
        
        Returns:
            Status dict
        """
        with self._autocycle_lock:
            if not self._autocycle_running:
                return {
                    'success': False,
                    'error': 'AutoCycle is not running'
                }
            
            self._autocycle_running = False
            self._autocycle_blocked_reason = 'MANUAL_STOP'  # User manually stopped
            
            logger.info("PSFALGO AutoCycle stopped")
            
            return {
                'success': True,
                'status': 'STOPPED'
            }
    
    def get_autocycle_status(self) -> Dict[str, Any]:
        """
        Get AutoCycle status.
        
        Returns:
            Status dict with running state, interval, last run time, and blocked_reason
        """
        with self._autocycle_lock:
            # Determine blocked_reason if running but not executing
            blocked_reason = None
            if self._autocycle_running:
                # Check why AutoCycle might be waiting
                if self.current_cycle and self.current_cycle.get('status') == 'PENDING_APPROVAL':
                    blocked_reason = 'PENDING_APPROVAL'
                elif self._autocycle_blocked_reason:
                    blocked_reason = self._autocycle_blocked_reason
                # Note: EXECUTION_IN_PROGRESS would be set during execution routing
                # For now, we track it via blocked_reason state
            
            return {
                'running': self._autocycle_running,
                'interval_seconds': self._autocycle_interval,
                'last_run': self._autocycle_last_run.isoformat() if self._autocycle_last_run else None,
                'blocked_reason': blocked_reason
            }
    
    def _autocycle_loop(self):
        """
        Background thread loop for AutoCycle.
        Runs cycles at specified interval.
        """
        logger.info(f"PSFALGO AutoCycle loop started (interval: {self._autocycle_interval}s)")
        
        while self._autocycle_running:
            try:
                # Check if we should skip (pending approval)
                with self._autocycle_lock:
                    if self.current_cycle and self.current_cycle.get('status') == 'PENDING_APPROVAL':
                        self._autocycle_blocked_reason = 'PENDING_APPROVAL'
                        logger.debug("PSFALGO AutoCycle: Skipping - cycle pending approval")
                    else:
                        # Clear blocked reason when running
                        self._autocycle_blocked_reason = None
                        # Run cycle
                        logger.info("PSFALGO AutoCycle: Running cycle...")
                        self._autocycle_last_run = datetime.now()
                        
                        # Get merged data and run cycle
                        try:
                            # Import here to avoid circular dependencies
                            from app.api.market_data_routes import static_store, market_data_cache
                            from app.api.market_data_routes import (
                                janall_metrics_engine, grpan_engine, position_analytics_engine,
                                exposure_mode_engine, position_snapshot_engine, position_guard_engine,
                                psfalgo_action_planner, signal_interpreter
                            )
                            
                            # Get symbols from static store
                            if not static_store or not static_store.is_loaded():
                                logger.warning("PSFALGO AutoCycle: Static store not loaded, skipping cycle")
                                continue
                            
                            symbols = static_store.get_all_symbols()
                            if not symbols:
                                logger.warning("PSFALGO AutoCycle: No symbols available, skipping cycle")
                                continue
                            
                            # Batch fetch positions and orders ONCE (O(1) API calls per cycle)
                            positions_cache = []
                            orders_cache = []
                            if position_snapshot_engine:
                                try:
                                    from app.api.trading_routes import get_hammer_positions_service, get_hammer_orders_service
                                    from app.trading.trading_account_context import get_trading_context, TradingAccountMode
                                    
                                    trading_context = get_trading_context()
                                    trading_mode = trading_context.trading_mode
                                    
                                    if trading_mode == TradingAccountMode.HAMMER_TRADING:
                                        positions_service = get_hammer_positions_service()
                                        if positions_service:
                                            positions_cache = positions_service.get_positions(force_refresh=False)
                                        
                                        orders_service = get_hammer_orders_service()
                                        if orders_service:
                                            all_orders = orders_service.get_orders(force_refresh=False)
                                            # Filter for OPEN orders only
                                            orders_cache = [o for o in all_orders if o.get('status', '').upper() == 'OPEN']
                                except Exception as e:
                                    logger.debug(f"PSFALGO AutoCycle: Error fetching positions/orders for batch: {e}")
                            
                            # Build merged data dict (simplified - use cached data)
                            merged_data = {}
                            for symbol in symbols:
                                static_data = static_store.get_static_data(symbol)
                                if not static_data:
                                    continue
                                
                                market_data = market_data_cache.get(symbol, {})
                                
                                # Get Janall metrics
                                janall_metrics = {}
                                if janall_metrics_engine and hasattr(janall_metrics_engine, 'symbol_metrics_cache'):
                                    janall_metrics = janall_metrics_engine.symbol_metrics_cache.get(symbol, {})
                                
                                # Get GRPAN metrics
                                grpan_metrics = {}
                                if grpan_engine:
                                    grpan_metrics = grpan_engine.get_grpan_for_symbol(symbol)
                                
                                # Get position analytics
                                position_analytics = {}
                                if position_analytics_engine:
                                    # Create a dummy order_plan for position analytics
                                    order_plan = {}
                                    position_analytics = position_analytics_engine.compute_position_analytics(
                                        symbol, static_data, market_data, order_plan
                                    )
                                
                                # Get exposure mode
                                exposure_mode = {}
                                if exposure_mode_engine:
                                    # Get signal data (simplified)
                                    signal_data = {}
                                    if signal_interpreter:
                                        # Would need full merged record for signal - skip for now
                                        pass
                                    exposure_mode = exposure_mode_engine.compute_exposure_mode(
                                        symbol, market_data, static_data, signal_data, grpan_metrics, position_analytics
                                    )
                                
                                # Get PSFALGO snapshot
                                # Use batch-fetched positions and orders cache (O(1) API calls per cycle)
                                psfalgo_snapshot = {}
                                if position_snapshot_engine:
                                    psfalgo_snapshot = position_snapshot_engine.compute_snapshot(
                                        symbol, static_data, market_data,
                                        positions_cache=positions_cache,
                                        orders_cache=orders_cache
                                    )
                                
                                # Get PSFALGO guards
                                psfalgo_guards = {}
                                if position_guard_engine and psfalgo_snapshot:
                                    order_plan = {}
                                    psfalgo_guards = position_guard_engine.evaluate_guards(
                                        symbol, psfalgo_snapshot, static_data, order_plan
                                    )
                                
                                # Get PSFALGO action plan
                                psfalgo_action_plan = {}
                                if psfalgo_action_planner and psfalgo_snapshot and psfalgo_guards:
                                    psfalgo_action_plan = psfalgo_action_planner.plan_action(
                                        symbol, psfalgo_snapshot, psfalgo_guards, janall_metrics, exposure_mode
                                    )
                                
                                # Build merged record
                                merged_data[symbol] = {
                                    'PREF_IBKR': symbol,
                                    'exposure_mode': exposure_mode,
                                    'psfalgo_action_plan': psfalgo_action_plan,
                                    'position_analytics': position_analytics,
                                    'psfalgo_snapshot': psfalgo_snapshot,
                                    'psfalgo_guards': psfalgo_guards,
                                    'market_data': market_data,
                                    'static_data': static_data,
                                    'signal_data': {},
                                    'grpan_metrics': grpan_metrics,
                                    'befday_qty': psfalgo_snapshot.get('befday_qty'),
                                    'current_qty': psfalgo_snapshot.get('current_qty'),
                                    'potential_qty': psfalgo_snapshot.get('potential_qty'),
                                    'guard_status': psfalgo_guards.get('guard_status'),
                                }
                            
                            # Run cycle
                            cycle_result = self.run_cycle(symbols, merged_data)
                            logger.info(f"PSFALGO AutoCycle: Cycle {cycle_result.get('cycle_id')} generated ({cycle_result.get('action_count')} actions)")
                            
                            # Update blocked_reason based on cycle result
                            with self._autocycle_lock:
                                if cycle_result.get('status') == 'PENDING_APPROVAL':
                                    self._autocycle_blocked_reason = 'PENDING_APPROVAL'
                                else:
                                    self._autocycle_blocked_reason = None
                            
                        except Exception as e:
                            logger.error(f"PSFALGO AutoCycle: Error running cycle: {e}", exc_info=True)
                            with self._autocycle_lock:
                                self._autocycle_blocked_reason = None  # Clear on error
                
                # Wait for interval
                for _ in range(self._autocycle_interval):
                    if not self._autocycle_running:
                        break
                    threading.Event().wait(1)  # Wait 1 second at a time, check running flag
                    
            except Exception as e:
                logger.error(f"PSFALGO AutoCycle loop error: {e}", exc_info=True)
                # Wait a bit before retrying
                threading.Event().wait(5)
        
        logger.info("PSFALGO AutoCycle loop stopped")
    
    def _route_cycle_to_execution(self, cycle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route approved cycle actions through execution pipeline.
        
        Args:
            cycle: Approved cycle dict with actions
            
        Returns:
            Execution results dict with counts and details
        """
        try:
            # Import here to avoid circular dependencies
            from app.execution.execution_router import ExecutionRouter, ExecutionMode
            from app.trading.trading_account_context import get_trading_context, TradingAccountMode
            from app.api.market_data_routes import (
                static_store, market_data_cache, order_queue, order_gate, execution_router
            )
            
            trading_context = get_trading_context()
            trading_mode = trading_context.trading_mode
            
            if not execution_router:
                logger.warning("ExecutionRouter not available, skipping execution routing")
                return {
                    'simulated_count': 0,
                    'executed_count': 0,
                    'blocked_count': 0,
                    'skipped_count': len(cycle['actions']),
                    'error': 'ExecutionRouter not available'
                }
            
            execution_mode = execution_router.get_mode()
            
            # Safety checks
            if execution_mode != ExecutionMode.SEMI_AUTO:
                logger.info(f"PSFALGO Cycle execution: Mode is {execution_mode.value}, not SEMI_AUTO. Skipping execution.")
                return {
                    'simulated_count': 0,
                    'executed_count': 0,
                    'blocked_count': 0,
                    'skipped_count': len(cycle['actions']),
                    'reason': f'Execution mode is {execution_mode.value}, not SEMI_AUTO'
                }
            
            if trading_mode != TradingAccountMode.HAMMER_TRADING:
                logger.info(f"PSFALGO Cycle execution: Trading mode is {trading_mode.value}, not HAMMER_TRADING. Skipping execution.")
                return {
                    'simulated_count': 0,
                    'executed_count': 0,
                    'blocked_count': 0,
                    'skipped_count': len(cycle['actions']),
                    'reason': f'Trading mode is {trading_mode.value}, not HAMMER_TRADING'
                }
            
            simulated_count = 0
            executed_count = 0
            blocked_count = 0
            skipped_count = 0
            execution_details = []
            
            for action in cycle['actions']:
                symbol = action['symbol']
                psfalgo_action = action['psfalgo_action']
                guard_status = action.get('guard_status', [])
                
                # Check if guard allows action
                if isinstance(guard_status, list) and ('BLOCKED' in guard_status or 'BLOCK_ADD' in guard_status):
                    blocked_count += 1
                    execution_details.append({
                        'symbol': symbol,
                        'psfalgo_action': psfalgo_action,
                        'status': 'BLOCKED',
                        'reason': 'Guard status blocks action'
                    })
                    continue
                
                # TEMPORARY: Block SHORT execution paths (phase 1 rollout)
                if psfalgo_action in ['ADD_SHORT', 'REDUCE_SHORT']:
                    skipped_count += 1
                    execution_details.append({
                        'symbol': symbol,
                        'psfalgo_action': psfalgo_action,
                        'status': 'SKIPPED',
                        'reason': 'SHORT execution disabled (phase 1 rollout)'
                    })
                    continue
                
                # Map PSFALGO action to order plan
                order_plan = self._create_order_plan_from_psfalgo_action(action, symbol)
                
                if not order_plan or order_plan.get('action') == 'NONE':
                    skipped_count += 1
                    execution_details.append({
                        'symbol': symbol,
                        'psfalgo_action': psfalgo_action,
                        'status': 'SKIPPED',
                        'reason': 'Cannot create order plan'
                    })
                    continue
                
                # Get static and market data
                static_data = static_store.get_static_data(symbol) if static_store else {}
                market_data = market_data_cache.get(symbol, {})
                
                if not static_data or not market_data:
                    skipped_count += 1
                    execution_details.append({
                        'symbol': symbol,
                        'psfalgo_action': psfalgo_action,
                        'status': 'SKIPPED',
                        'reason': 'Missing static or market data'
                    })
                    continue
                
                # Queue order
                queue_status = {}
                if order_queue:
                    queue_status = order_queue.enqueue_order(symbol, order_plan)
                
                # Evaluate gate
                gate_status = {}
                if order_gate:
                    gate_status = order_gate.evaluate_gate(order_plan, queue_status, market_data, static_data)
                
                # Route through execution router
                # Execution routing REMOVED - all orders must go through Intent system
                # ExecutionRouter now only handles APPROVED intents (via /api/psfalgo/intents/{id}/approve)
                execution_result = {
                    'execution_status': 'SKIPPED_NO_INTENT',
                    'execution_reason': 'Direct execution disabled - use Intent system',
                    'execution_mode': 'PREVIEW'
                }
                
                execution_status = execution_result.get('execution_status')
                
                if execution_status == 'SIMULATED':
                    simulated_count += 1
                elif execution_status == 'EXECUTED':
                    executed_count += 1
                elif execution_status in ['BLOCKED_BY_GATE', 'SKIPPED_USER_ACTION']:
                    blocked_count += 1
                else:
                    skipped_count += 1
                
                execution_details.append({
                    'symbol': symbol,
                    'psfalgo_action': psfalgo_action,
                    'status': execution_status,
                    'reason': execution_result.get('execution_reason', 'Unknown'),
                    'order_plan': order_plan
                })
            
            return {
                'simulated_count': simulated_count,
                'executed_count': executed_count,
                'blocked_count': blocked_count,
                'skipped_count': skipped_count,
                'details': execution_details
            }
            
        except Exception as e:
            logger.error(f"Error routing cycle to execution: {e}", exc_info=True)
            return {
                'simulated_count': 0,
                'executed_count': 0,
                'blocked_count': 0,
                'skipped_count': len(cycle.get('actions', [])),
                'error': str(e)
            }
    
    def _create_order_plan_from_psfalgo_action(
        self,
        action: Dict[str, Any],
        symbol: str
    ) -> Optional[Dict[str, Any]]:
        """
        Create order plan from PSFALGO action.
        
        Args:
            action: PSFALGO action dict
            symbol: Symbol (PREF_IBKR)
            
        Returns:
            Order plan dict or None if not supported
        """
        try:
            psfalgo_action = action['psfalgo_action']
            size_lot = action.get('size_lot_estimate', 0)
            
            # Import here to avoid circular dependencies
            from app.api.market_data_routes import static_store, market_data_cache
            
            static_data = static_store.get_static_data(symbol) if static_store else {}
            market_data = market_data_cache.get(symbol, {})
            
            if not static_data or not market_data:
                return None
            
            bid = self._safe_float(market_data.get('bid'))
            ask = self._safe_float(market_data.get('ask'))
            spread_percent = self._safe_float(market_data.get('spread_percent'))
            
            if not bid or not ask:
                return None
            
            # Map PSFALGO actions to order plans
            if psfalgo_action == 'ADD_LONG':
                # BUY order
                # Determine style based on spread
                if spread_percent and spread_percent <= 0.2:
                    style = 'BID'
                    price = bid
                elif spread_percent and spread_percent <= 0.5:
                    style = 'FRONT'
                    price = (bid + ask) / 2
                else:
                    style = 'SOFT_FRONT'
                    price = (bid + ask) / 2
                
                return {
                    'action': 'BUY',
                    'style': style,
                    'price': price,
                    'size': size_lot,
                    'urgency': 'MEDIUM',
                    'symbol': symbol,
                    'plan_reason': {
                        'reason': 'psfalgo_add_long',
                        'psfalgo_action': psfalgo_action,
                        'size_lot': size_lot,
                        'message': f'PSFALGO ADD_LONG: {size_lot} lots @ {price:.4f} ({style})'
                    },
                    'psfalgo_source': True,
                    'psfalgo_action': psfalgo_action
                }
            
            elif psfalgo_action == 'REDUCE_LONG':
                # SELL order (stub - may not be fully implemented)
                # Determine style based on spread
                if spread_percent and spread_percent <= 0.2:
                    style = 'ASK'
                    price = ask
                elif spread_percent and spread_percent <= 0.5:
                    style = 'FRONT'
                    price = (bid + ask) / 2
                else:
                    style = 'SOFT_FRONT'
                    price = (bid + ask) / 2
                
                return {
                    'action': 'SELL',
                    'style': style,
                    'price': price,
                    'size': size_lot,
                    'urgency': 'MEDIUM',
                    'symbol': symbol,
                    'plan_reason': {
                        'reason': 'psfalgo_reduce_long',
                        'psfalgo_action': psfalgo_action,
                        'size_lot': size_lot,
                        'message': f'PSFALGO REDUCE_LONG: {size_lot} lots @ {price:.4f} ({style})'
                    },
                    'psfalgo_source': True,
                    'psfalgo_action': psfalgo_action
                }
            
            elif psfalgo_action in ['ADD_SHORT', 'REDUCE_SHORT']:
                # TEMPORARY: SHORT execution disabled (phase 1 rollout)
                logger.debug(f"PSFALGO action {psfalgo_action} disabled - SHORT execution disabled (phase 1 rollout)")
                return None
            
            return None
            
        except Exception as e:
            logger.error(f"Error creating order plan from PSFALGO action: {e}", exc_info=True)
            return None
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None or value == 'N/A' or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    
    def get_cycle_execution_stats(self, cycle_id: str) -> Optional[Dict[str, Any]]:
        """
        Get execution statistics for a cycle.
        
        Args:
            cycle_id: Cycle ID
            
        Returns:
            Execution stats dict or None
        """
        return self.cycle_execution_stats.get(cycle_id)

