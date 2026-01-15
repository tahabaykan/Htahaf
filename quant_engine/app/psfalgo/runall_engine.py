"""
RUNALL Cycle Engine - Phase 11 Orchestrator
===========================================

Role: "Central Conductor"
1.  Loads State: Config, Inputs, Runtime Controls.
2.  Runs Analyzers: Karbotu (Signals), Reducemore (Multipliers).
3.  Runs Executive: LT Trim (consumes Signals + Multipliers).
4.  Resolves Conflicts: Priority-based selection (Emergency > Macro > Micro).
5.  Submits Final Intents to Execution.
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from app.core.logger import logger
from app.psfalgo.decision_models import (
    DecisionRequest,
    Decision, 
    DecisionResponse
)
from app.psfalgo.intent_models import Intent
from app.config.strategy_config_manager import get_strategy_config_manager
from app.state.runtime_controls import get_runtime_controls_manager

# Engines
from app.psfalgo.karbotu_engine import get_karbotu_engine
from app.psfalgo.reducemore_engine import get_reducemore_engine
from app.psfalgo.addnewpos_engine import get_addnewpos_engine # NEW: AddNewPos Integration
from app.event_driven.decision_engine.lt_trim_engine import get_lt_trim_engine

# Proposal & Intent Storage
from app.psfalgo.proposal_engine import get_proposal_engine
from app.psfalgo.proposal_store import get_proposal_store
from app.psfalgo.intent_store import get_intent_store
from app.psfalgo.market_snapshot_store import get_market_snapshot_store

# Data APIs (New)
from app.psfalgo.position_snapshot_api import get_position_snapshot_api
from app.psfalgo.metrics_snapshot_api import get_metrics_snapshot_api
from app.psfalgo.exposure_calculator import get_exposure_calculator
from app.market_data.static_data_store import get_static_store # NEW: JFIN Data

# Execution
# Execution
from app.psfalgo.execution_engine import get_execution_engine
from app.trading.trading_account_context import get_trading_context

class RunallEngine:
    
    
    def __init__(self, config=None):
        self.config = config or {}
        self.loop_running = False
        self.loop_count = 0
        
        # State Attributes (added for API compatibility)
        self.global_state = "IDLE" 
        self.cycle_state = "INIT"
        self.dry_run_mode = True
        self.cycle_start_time = None
        self.next_cycle_time = None
        self.last_error = None
        self.last_error_time = None
        self.current_exposure = None
        
        # API Dependencies (Lazy Loaded)
        self.position_snapshot_api = None
        self.metrics_snapshot_api = None
        self.exposure_calculator = None
        
        # Active Engines (Default from User Request: LT, KARBOTU, MM, ADDNEWPOS)
        self.active_engines = ['LT_TRIM', 'KARBOTU', 'MM_ENGINE', 'ADDNEWPOS_ENGINE'] 

    def set_active_engines(self, engines: List[str]):
        """Set the list of active engines (controlled by UI checkboxes)"""
        logger.info(f"[RUNALL] Setting active engines: {engines}")
        self.active_engines = engines

    def get_state(self) -> Dict[str, Any]:
        """
        Get current engine state.
        Required by RunallStateAPI.
        """
        return {
            "global_state": self.global_state,
            "cycle_state": self.cycle_state,
            "loop_count": self.loop_count,
            "loop_running": self.loop_running,
            "active_engines": self.active_engines, # Expose active engines
            "dry_run_mode": self.dry_run_mode,
            "last_error": self.last_error
        }
        
    async def start(self):
        if self.loop_running: return
        self.loop_running = True
        asyncio.create_task(self._cycle_loop())
        logger.info(f"[RUNALL] Started Phase 11 Cycle Loop (Engines: {self.active_engines})")

    async def stop(self):
        self.loop_running = False
        logger.info("[RUNALL] Stopping Cycle Loop")

    async def _cycle_loop(self):
        while self.loop_running:
            await self.run_single_cycle()
            # Wait remainder of interval
            await asyncio.sleep(self.config.get('cycle_interval_seconds', 60))

    async def run_single_cycle(self):
        """Run a single execution cycle (Refactored for Testability)"""
        self.loop_count += 1
        correlation_id = str(uuid.uuid4())
        
        try:
            # 1. Context & Config
            ctx = get_trading_context()
            account_id = ctx.trading_mode.value
            
            # Explicitly log active account for user visibility
            logger.info(f"[RUNALL] Cycle {self.loop_count} processing for Account: {account_id}")
            
            cfg_mgr = get_strategy_config_manager()
            effective_rules = cfg_mgr.get_effective_rules(account_id)
            
            ctrl_mgr = get_runtime_controls_manager()
            controls = ctrl_mgr.get_controls(account_id)

            if not controls.system_enabled:
                logger.info(f"[RUNALL] Cycle {self.loop_count} SKIPPED (System Disabled)")
                return
            
            # 1.5. Cancel-All Protocol (Phase 11)
            # Ensure stateless execution by cancelling all pending LT orders
            # Lazy Import to avoid circular dependency
            from app.psfalgo.order_manager import get_order_controller
            oc = get_order_controller()
            if oc:
                cancelled = await oc.cancel_open_orders(account_id, book="LT")
                if cancelled > 0:
                    logger.info(f"[RUNALL] Cancelled {cancelled} stale LT orders for {account_id}")

            # 2. Data Snapshot (Metrics, Exposure)
            # (Assuming helper methods exist and work, simplified for brevity)
            request = await self._prepare_request(account_id, correlation_id)
            if not request:
                return

            # 2.5. Score Calculation (BATCH - at cycle start)
            # Computes all scores and updates SecurityContexts
            try:
                from app.core.fast_score_calculator import get_fast_score_calculator
                score_calculator = get_fast_score_calculator()
                score_stats = score_calculator.update_security_contexts()
                logger.debug(f"[RUNALL] Scores updated: {score_stats.get('updated', 0)} symbols")
            except Exception as e:
                logger.warning(f"[RUNALL] Score calculation error: {e}")

            # 3. Parallel Engine Execution (Analyzers)
            # Define dummy/empty result class
            class EmptyResult:
                def __init__(self):
                    self.signals = {}
                    self.multipliers = {}
                    self.intents = []

            async def _run_or_skip(engine_name, task_factory):
                if engine_name in self.active_engines:
                    return await task_factory()
                return EmptyResult()

            karbotu_task = _run_or_skip('KARBOTU', lambda: get_karbotu_engine().run(request, effective_rules))
            reducemore_task = _run_or_skip('REDUCEMORE', lambda: get_reducemore_engine().run(request, effective_rules))
            
            # Safe AddNewPos Call (MM Engine)
            addnewpos_engine = get_addnewpos_engine()
            if addnewpos_engine:
                 # MM_ENGINE maps to AddNewPos logic for now
                addnewpos_task = _run_or_skip('MM_ENGINE', lambda: addnewpos_engine.addnewpos_decision_engine(request))
            else:
                async def _empty_task(): return EmptyResult()
                addnewpos_task = _empty_task()
            
            karbotu_out, reducemore_out, addnewpos_out = await asyncio.gather(
                karbotu_task, 
                reducemore_task, 
                addnewpos_task,
                return_exceptions=True # Prevent one crash from killing all
            )
            
            # Helper to handle Exception results from return_exceptions=True
            if isinstance(karbotu_out, Exception):
                logger.error(f"[RUNALL] Karbotu crashed: {karbotu_out}")
                karbotu_out = EmptyResult()
            if isinstance(reducemore_out, Exception):
                logger.error(f"[RUNALL] Reducemore crashed: {reducemore_out}")
                reducemore_out = EmptyResult()
            if isinstance(addnewpos_out, Exception):
                logger.error(f"[RUNALL] AddNewPos crashed: {addnewpos_out}")
                addnewpos_out = EmptyResult()
            
            # Phase 11 Recommendation Bridge (Intents -> Proposals)
            # -----------------------------------------------------
            start_time = datetime.now()
            
            # Prepare Position Map for Adapter
            positions_map = {p.symbol: p for p in request.positions}
            
            # 1. Adapt Karbotu Intents
            if karbotu_out and karbotu_out.intents:
                karbotu_decisions = self._adapt_intents_to_decisions(karbotu_out.intents, positions_map)
                
                # Generate & Store Proposals
                proposal_engine = get_proposal_engine()
                proposal_store = get_proposal_store()
                if proposal_engine and proposal_store and karbotu_decisions:
                    proposals = await proposal_engine.process_decision_response(
                        response=DecisionResponse(decisions=karbotu_decisions),
                        cycle_id=self.loop_count,
                        decision_source="KARBOTU",
                        decision_timestamp=start_time
                    )
                    for p in proposals:
                        proposal_store.add_proposal(p)

            # 2. Adapt Reducemore Intents
            if reducemore_out and reducemore_out.intents:
                reducemore_decisions = self._adapt_intents_to_decisions(reducemore_out.intents, positions_map)
                
                # Generate & Store Proposals
                proposal_engine = get_proposal_engine()
                proposal_store = get_proposal_store()
                if proposal_engine and proposal_store and reducemore_decisions:
                    proposals = await proposal_engine.process_decision_response(
                        response=DecisionResponse(decisions=reducemore_decisions),
                        cycle_id=self.loop_count,
                        decision_source="REDUCEMORE",
                        decision_timestamp=start_time
                    )
                    for p in proposals:
                        proposal_store.add_proposal(p)

            # 3. Adapt AddNewPos Intents (NEW)
            if addnewpos_out and addnewpos_out.intents:
                addnewpos_decisions = self._adapt_intents_to_decisions(addnewpos_out.intents, positions_map)
                
                # Generate & Store Proposals
                proposal_engine = get_proposal_engine()
                proposal_store = get_proposal_store()
                if proposal_engine and proposal_store and addnewpos_decisions:
                    proposals = await proposal_engine.process_decision_response(
                        response=DecisionResponse(decisions=addnewpos_decisions),
                        cycle_id=self.loop_count,
                        decision_source="ADDNEWPOS_ENGINE", # Matches UI tabs
                        decision_timestamp=start_time
                    )
                    for p in proposals:
                        proposal_store.add_proposal(p)

            # 3. Executive Engine Execution (LT Trim)
            lt_intents = []
            if 'LT_TRIM' in self.active_engines:
                lt_intents = await get_lt_trim_engine().run(
                    request,
                    (karbotu_out.signals if hasattr(karbotu_out, 'signals') else {}),
                    (reducemore_out.multipliers if hasattr(reducemore_out, 'multipliers') else {}),
                    effective_rules,
                    controls,
                    account_id=account_id # Explicitly pass account_id for Befday loading
                )

            # 4. Conflict Resolution & Collection
            addnewpos_intents = addnewpos_out.intents if (addnewpos_out and addnewpos_out.intents) else []
            all_intents = karbotu_out.intents + reducemore_out.intents + lt_intents + addnewpos_intents # NEW: Add JFIN intents
            unique_intents = self._resolve_conflicts(all_intents)
            
            # 5. Persist Intents
            intent_store = get_intent_store()
            proposals_created = 0
            
            if unique_intents:
                if intent_store:
                    for intent in unique_intents:
                        intent_store.add_intent(intent)
                
                # 6. Convert Intents to Proposals (Human-in-the-Loop)
                try:
                    # get_proposal_engine and get_proposal_store already imported at module level
                    proposal_engine = get_proposal_engine()
                    proposal_store = get_proposal_store()
                    
                    logger.info(f"[RUNALL] Proposal Engine: {proposal_engine is not None}, Proposal Store: {proposal_store is not None}")
                    
                    if proposal_engine and proposal_store:
                        # Convert intents to decisions for proposal engine
                        decisions = self._adapt_intents_to_decisions(unique_intents, positions_map)
                        logger.info(f"[RUNALL] Adapted {len(decisions)} decisions from {len(unique_intents)} intents")
                        
                        if decisions:
                            # Create DecisionResponse wrapper (already imported at module level)
                            response = DecisionResponse(
                                decisions=decisions,
                                timestamp=datetime.now()
                            )
                            
                            # Generate proposals
                            proposals = await proposal_engine.process_decision_response(
                                response=response,
                                cycle_id=self.loop_count,
                                decision_source="RUNALL",
                                decision_timestamp=datetime.now()
                            )
                            
                            logger.info(f"[RUNALL] Generated {len(proposals) if proposals else 0} raw proposals")
                            
                            # 5. Deduplicate Proposals (Prevent Spam)
                            unique_proposals = []
                            seen_proposals = set()
                            
                            if proposals:
                                for p in proposals:
                                    # OrderProposal is an OBJECT, not dict - use attribute access
                                    try:
                                        sym = p.symbol if hasattr(p, 'symbol') else p.get('symbol', 'UNK')
                                        side = p.side if hasattr(p, 'side') else p.get('side', 'UNK')
                                        price = p.proposed_price if hasattr(p, 'proposed_price') else p.get('price', 0)
                                        intent_type = p.order_subtype if hasattr(p, 'order_subtype') else 'UNKNOWN'
                                        
                                        key = (sym, side, intent_type, round(price or 0, 2))
                                        
                                        if key not in seen_proposals:
                                            seen_proposals.add(key)
                                            unique_proposals.append(p)
                                        else:
                                            logger.debug(f"[RUNALL] Dropped duplicate: {sym} {side} @ {price}")
                                    except Exception as de:
                                        # If dedup fails, keep the proposal anyway
                                        unique_proposals.append(p)
                                        logger.warning(f"[RUNALL] Dedup error: {de}")
                            
                            final_proposals = unique_proposals

                            # 6. Push to Core State
                            if hasattr(self, 'state_manager'):
                                self.state_manager.update_proposals(final_proposals)

                            # Save proposals
                            for proposal in final_proposals:
                                proposal_store.add_proposal(proposal)
                                proposals_created += 1
                            
                            logger.info(f"[RUNALL] Created {proposals_created} proposals from {len(unique_intents)} intents")
                    else:
                        logger.warning(f"[RUNALL] Proposal engine or store not available: engine={proposal_engine}, store={proposal_store}")
                except Exception as e:
                    logger.error(f"[RUNALL] Error creating proposals: {e}", exc_info=True)
                
                logger.info(f"[RUNALL] Cycle {self.loop_count}: Generated {len(unique_intents)} intents, {proposals_created} proposals")
            else:
                logger.debug(f"[RUNALL] Cycle {self.loop_count}: No actionable intents")
            
            # Count proposals for summary
            proposal_store = get_proposal_store()
            proposals_count = proposal_store.get_pending_count() if proposal_store else 0

            # =========================================================
            # CYCLE DEBUG SUMMARY (Kritik observability çıktısı)
            # Bu log satırı "neden proposal yok?" sorusunu yanıtlar
            # =========================================================
            try:
                from app.core.security_registry import get_security_registry
                from app.core.benchmark_store import get_benchmark_store
                
                registry = get_security_registry()
                benchmark_store = get_benchmark_store()
                
                if registry:
                    registry.log_cycle_summary(
                        cycle_id=self.loop_count,
                        intents_count=len(unique_intents) if unique_intents else 0,
                        proposals_count=proposals_count,
                        benchmark_ok=benchmark_store.is_available() if benchmark_store else False
                    )
            except Exception as e:
                logger.debug(f"[RUNALL] Could not log cycle summary: {e}")
            
            return unique_intents if unique_intents else []

        except Exception as e:
            logger.error(f"[RUNALL] Cycle Error: {e}", exc_info=True)
            return []
            
            # Wait remainder of interval
            await asyncio.sleep(self.config.get('cycle_interval_seconds', 60))

    def _adapt_intents_to_decisions(self, intents: List[Any], positions_map: Dict[str, Any] = None) -> List[Decision]:
        """
        Adapt Phase 11 Intents to Phase 10 Decisions for Proposal Engine compatibility.
        Handles both old-style dict/dataclass intents and new pydantic Intent models.
        """
        decisions: List[Decision] = []
        positions_map = positions_map or {}
        for intent in intents:
            try:
                # Get action - could be enum or string
                intent_action = getattr(intent, 'action', None)
                if hasattr(intent_action, 'value'):
                    action_str = intent_action.value
                else:
                    action_str = str(intent_action) if intent_action else "HOLD"
                
                # Determine standard action
                action = "HOLD"
                if action_str.upper() in ["SELL", "REDUCE", "SELL_SHORT"]:
                    action = "SELL"
                elif action_str.upper() in ["BUY", "ADD", "COVER", "BUY_TO_COVER"]:
                    action = "BUY"
                
                # Get qty - could be 'qty' or 'calculated_lot'
                qty = getattr(intent, 'qty', getattr(intent, 'calculated_lot', 0))
                
                # Get reason - could be 'reason', 'reason_text', or 'reason_code'
                reason = getattr(intent, 'reason_text', 
                         getattr(intent, 'reason', 
                         getattr(intent, 'reason_code', 'LT_TRIM')))
                
                # Get metadata - could be 'metadata' or 'metric_values'
                metadata = getattr(intent, 'metric_values', 
                           getattr(intent, 'metadata', {})) or {}
                
                # Get Position Context
                current_qty = 0.0
                potential_qty = 0.0
                if intent.symbol in positions_map:
                    pos = positions_map[intent.symbol]
                    current_qty = pos.qty
                    base_potential = getattr(pos, 'potential_qty', pos.qty) # Base potential (Current + Open)
                    # Add this decision's impact
                    decision_impact = qty if action == 'BUY' else -qty
                    potential_qty = base_potential + decision_impact
                
                # Create Decision
                decision = Decision(
                    symbol=intent.symbol,
                    action=action,
                    order_type="LIMIT",
                    calculated_lot=qty,
                    reason=reason,
                    confidence=0.8,
                    metrics_used=metadata,
                    current_qty=current_qty,
                    potential_qty=potential_qty
                )
                
                # Preserve step info if available
                if isinstance(metadata, dict) and "step" in metadata:
                    decision.step_number = metadata["step"]
                
                decisions.append(decision)
                logger.debug(f"[ADAPT] Intent {intent.symbol} -> Decision: action={action}, qty={qty}")
                
            except Exception as e:
                logger.warning(f"[RUNALL] Failed to adapt intent for {getattr(intent, 'symbol', 'UNKNOWN')}: {e}")
        
        return decisions

    def _resolve_conflicts(self, intents: List[Any]) -> List[Any]:
        """
        Phase 11 Conflict Resolution Strategy:
        1. Group by Symbol + Side.
        2. Sort by Priority (Emergency > Reducemore > Karbotu > LT).
        3. If Priority Equal: Use MAX Qty (as per user tweak).
        """
        grouped = {}
        for i in intents:
            key = (i.symbol, i.action) # e.g. ("AAPL", "SELL")
            if key not in grouped: grouped[key] = []
            grouped[key].append(i)
        
        resolved = []
        for key, candidates in grouped.items():
            # Sort by Priority (descending) then Qty (descending)
            # Priority: Emergency (40) > Reducemore (30) > Macro (20) > Micro (10)
            candidates.sort(key=lambda x: (x.priority, abs(x.qty)), reverse=True)
            
            winner = candidates[0]
            if len(candidates) > 1:
                # Log usage of prioritization
                losers = [f"{c.intent_category}({c.qty})" for c in candidates[1:]]
                logger.info(f"[CONFLICT] Selected {winner.intent_category}({winner.qty}) for {key}. Dropped: {losers}")
            
            resolved.append(winner)
            
        return resolved

    async def _prepare_request(self, account_id, correlation_id):
        """
        Prepare DecisionRequest by fetching real data from APIs.
        """
        try:
            # 1. Get API Instances (Lazy Load)
            if not self.position_snapshot_api:
                self.position_snapshot_api = get_position_snapshot_api()
            if not self.metrics_snapshot_api:
                self.metrics_snapshot_api = get_metrics_snapshot_api()
            if not self.exposure_calculator:
                self.exposure_calculator = get_exposure_calculator()
            
            if not self.position_snapshot_api or not self.metrics_snapshot_api or not self.exposure_calculator:
                missing = []
                if not self.position_snapshot_api: missing.append("PositionSnapshotAPI")
                if not self.metrics_snapshot_api: missing.append("MetricsSnapshotAPI")
                if not self.exposure_calculator: missing.append("ExposureCalculator")
                logger.error(f"[RUNALL] Critical APIs not initialized: {', '.join(missing)}")
                return None
            
            # 2. Fetch Data (Parallel where possible, but dependent here)
            # A. Positions
            positions = await self.position_snapshot_api.get_position_snapshot(
                account_id=account_id,
                include_zero_positions=False 
            )
            
            # B. Metrics (for symbols in positions AND JFIN candidates)
            # Strategy: We also need to scan potential new entries (candidates).
            # Load JFIN candidates from StaticDataStore
            static_store = get_static_store()
            if not static_store:
                static_store = initialize_static_store()
            
            # Ensure loaded
            if not static_store.is_loaded():
                static_store.load_csv()

            jfin_candidates = static_store.get_all_symbols() if static_store else []
            
            pos_symbols = [p.symbol for p in positions]
            # Merge and deduplicate symbols for metrics fetching
            all_symbols = list(set(pos_symbols + jfin_candidates))
            
            metrics = await self.metrics_snapshot_api.get_metrics_snapshot(all_symbols) # Fetch for ALL
            
            # Update request available_symbols for AddNewPosEngine
            available_symbols = jfin_candidates
            
            # D. L1 Data (Bid/Ask/Last) from DataFabric
            from app.core.data_fabric import get_data_fabric
            l1_data = {}
            data_fabric = get_data_fabric()
            if data_fabric:
                for symbol in all_symbols:
                    live_data = data_fabric.get_live(symbol)
                    if live_data:
                        l1_data[symbol] = {
                            'bid': live_data.get('bid', 0) or 0,
                            'ask': live_data.get('ask', 0) or 0,
                            'last': live_data.get('last', 0) or 0,
                        }
            
            # C. Exposure
            exposure = self.exposure_calculator.calculate_exposure(positions)
            self.current_exposure = exposure # Update state
            
            # 3. Create Request
            return DecisionRequest(
                positions=positions,
                metrics=metrics,
                l1_data=l1_data,
                exposure=exposure,
                snapshot_ts=datetime.now(),
                correlation_id=correlation_id,
                available_symbols=available_symbols # NEW: Pass JFIN candidates
            )
            
        except Exception as e:
            logger.error(f"[RUNALL] Data fetch error: {e}", exc_info=True)
            return None

# Global Instance
_runall_engine = RunallEngine()
def get_runall_engine(): return _runall_engine

def initialize_runall_engine():
    """
    Initialize global RunallEngine instance.
    This is required by main.py startup event.
    """
    logger.info("[RUNALL] Initializing RunallEngine...")
    # Return the global instance
    return _runall_engine
