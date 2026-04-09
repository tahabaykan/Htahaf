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
from app.mm.greatest_mm_decision_engine import get_greatest_mm_decision_engine # NEW: Greatest MM Integration
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
from app.psfalgo.free_exposure_engine import get_free_exposure_engine  # FREE EXPOSURE: Dynamic MM lot sizing
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
        self.last_run_diagnostic = {} # New: Stores comprehensive diagnostic for UI report
        
        # API Dependencies (Lazy Loaded)
        self.position_snapshot_api = None
        self.metrics_snapshot_api = None
        self.exposure_calculator = None
        
        # Active Engines (Default from User Request: LT, KARBOTU, MM, ADDNEWPOS)
        self._default_engines = ['LT_TRIM', 'KARBOTU', 'PATADD_ENGINE', 'ADDNEWPOS_ENGINE', 'MM_ENGINE']
        self.active_engines = self._load_active_engines()

    def _load_active_engines(self) -> List[str]:
        """Load active engines from Redis. Falls back to defaults if no saved state."""
        try:
            from app.core.redis_client import get_redis
            import json
            redis = get_redis()
            if redis:
                raw = redis.get('psfalgo:active_engines')
                if raw:
                    engines = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    if isinstance(engines, list) and len(engines) > 0:
                        logger.info(f"[RUNALL] Loaded active_engines from Redis: {engines}")
                        return engines
        except Exception as e:
            logger.warning(f"[RUNALL] Failed to load active_engines from Redis: {e}")
        logger.info(f"[RUNALL] Using default active_engines: {self._default_engines}")
        return list(self._default_engines)

    def _save_active_engines(self):
        """Save active engines to Redis for persistence across restarts."""
        try:
            from app.core.redis_client import get_redis
            import json
            redis = get_redis()
            if redis:
                redis.set('psfalgo:active_engines', json.dumps(self.active_engines))
                logger.debug(f"[RUNALL] Saved active_engines to Redis: {self.active_engines}")
        except Exception as e:
            logger.warning(f"[RUNALL] Failed to save active_engines to Redis: {e}")

    def set_active_engines(self, engines: List[str]):
        """Set the list of active engines (controlled by UI checkboxes). Persisted to Redis."""
        logger.info(f"[RUNALL] Setting active engines: {engines}")
        self.active_engines = engines
        self._save_active_engines()

    def reset_active_engines_to_default(self):
        """Reset active engines to default and persist."""
        self.active_engines = list(self._default_engines)
        self._save_active_engines()
        logger.info(f"[RUNALL] Reset active_engines to defaults: {self._default_engines}")
        return self.active_engines

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
            await asyncio.sleep(self.config.get('cycle_interval_seconds', 65))

    async def run_single_cycle(self):
        """Run a single execution cycle (Refactored for Testability)"""
        self.loop_count += 1
        correlation_id = str(uuid.uuid4())
        
        try:
            # 0. Check if account has been selected
            from app.core.redis_client import get_redis
            redis = get_redis()
            account_selected = False
            if redis:
                try:
                    account_selected = redis.get("psfalgo:account_selected") is not None
                    
                    # FALLBACK: If hammer connected but account_selected was never set
                    # (e.g. Redis TTL expired mid-day), auto-set it
                    if not account_selected:
                        hammer_ready = redis.get("psfalgo:hammer_ready")
                        if hammer_ready:
                            redis.set("psfalgo:account_selected", "true", ex=86400)
                            account_selected = True
                            logger.info(f"[RUNALL] Auto-set account_selected (hammer_ready was set, account_selected expired)")
                except Exception:
                    pass
            
            if not account_selected:
                if self.loop_count <= 3:  # Only log first few to avoid spam
                    logger.info(f"[RUNALL] Cycle {self.loop_count} SKIPPED (No account selected yet)")
                return
            
            # 1. Context & Config
            ctx = get_trading_context()
            account_id = ctx.trading_mode.value
            
            # Explicitly log active account for user visibility
            logger.info(f"[RUNALL] Cycle {self.loop_count} processing for Account: {account_id}")
            
            cfg_mgr = get_strategy_config_manager()
            effective_rules = cfg_mgr.get_effective_rules(account_id)
            
            ctrl_mgr = get_runtime_controls_manager()
            controls = ctrl_mgr.get_controls(account_id)
            
            # Log runtime controls status
            logger.info(f"[RUNALL] 🔧 Runtime Controls: system_enabled={controls.system_enabled}, lt_trim_enabled={controls.lt_trim_enabled}, karbotu_enabled={controls.karbotu_enabled}")

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
                logger.warning(f"[RUNALL] ⚠️ Request preparation failed - no request object")
                return
            
            logger.info(f"[RUNALL] 📊 Request prepared: {len(request.positions)} positions, {len(request.metrics)} metrics")

            # 2.5. Score Calculation (BATCH - at cycle start)
            # Computes all scores and updates SecurityContexts
            try:
                from app.core.fast_score_calculator import get_fast_score_calculator
                score_calculator = get_fast_score_calculator()
                score_stats = score_calculator.update_security_contexts()
                logger.debug(f"[RUNALL] Scores updated: {score_stats.get('updated', 0)} symbols")
            except Exception as e:
                logger.warning(f"[RUNALL] Score calculation error: {e}")

            # 2.7. Free Exposure Pre-Calculation (for MM dynamic lot sizing)
            try:
                free_exp_engine = get_free_exposure_engine()
                free_exp_snapshot = await free_exp_engine.calculate_free_exposure(account_id)
                if free_exp_snapshot.get('blocked'):
                    logger.warning(
                        f"[RUNALL] ⚠️ FREE EXPOSURE BLOCKED for {account_id} — "
                        f"MM/ADDNEWPOS INCREASE disabled (free={free_exp_snapshot['effective_free_pct']:.1f}%)"
                    )
                else:
                    logger.info(
                        f"[RUNALL] 📊 Free Exposure: {account_id} → "
                        f"free_cur={free_exp_snapshot['free_cur_pct']:.1f}% "
                        f"free_pot={free_exp_snapshot['free_pot_pct']:.1f}% "
                        f"effective={free_exp_snapshot['effective_free_pct']:.1f}% "
                        f"→ {free_exp_snapshot['tier_label']}"
                    )
            except Exception as e:
                logger.warning(f"[RUNALL] Free exposure calc error: {e}")

            # 3. Parallel Engine Execution (Analyzers)
            # Define dummy/empty result class
            class EmptyResult:
                def __init__(self):
                    self.signals = {}
                    self.multipliers = {}
                    self.intents = []

            async def _run_or_skip(engine_name, task_factory):
                if engine_name in self.active_engines:
                    # Additional runtime control check for KARBOTU (similar to LT_TRIM)
                    if engine_name == 'KARBOTU' and not controls.karbotu_enabled:
                        logger.warning(f"[RUNALL] ⚠️ KARBOTU skipped: runtime control disabled (karbotu_enabled={controls.karbotu_enabled})")
                        return EmptyResult()
                    return await task_factory()
                return EmptyResult()

            # Log before running engines
            logger.info(f"[RUNALL] 🚀 Starting parallel engines: KARBOTU={'KARBOTU' in self.active_engines} (enabled={controls.karbotu_enabled}), REDUCEMORE={'REDUCEMORE' in self.active_engines}, PATADD={'PATADD_ENGINE' in self.active_engines}, ADDNEWPOS={'ADDNEWPOS_ENGINE' in self.active_engines}, MM={'MM_ENGINE' in self.active_engines}")
            
            karbotu_task = _run_or_skip('KARBOTU', lambda: get_karbotu_engine().run(request, effective_rules))
            reducemore_task = _run_or_skip('REDUCEMORE', lambda: get_reducemore_engine().run(request, effective_rules))
            
            # Safe AddNewPos Call - MUST initialize if not yet done
            from app.psfalgo.addnewpos_engine import get_addnewpos_engine, initialize_addnewpos_engine
            addnewpos_engine = get_addnewpos_engine()
            if not addnewpos_engine:
                logger.info("[RUNALL] 🔧 AddnewposEngine not initialized - initializing now...")
                addnewpos_engine = initialize_addnewpos_engine()
            if addnewpos_engine:
                addnewpos_task = _run_or_skip('ADDNEWPOS_ENGINE', lambda: addnewpos_engine.addnewpos_decision_engine(request))
            else:
                logger.error("[RUNALL] ❌ AddnewposEngine failed to initialize!")
                async def _empty_task(): return EmptyResult()
                addnewpos_task = _empty_task()
            
            # PATADD Engine Task (Pattern-based position increase)
            from app.psfalgo.patadd_engine import get_patadd_engine
            patadd_engine = get_patadd_engine()
            if patadd_engine:
                patadd_task = _run_or_skip('PATADD_ENGINE', lambda: patadd_engine.run(request, account_id=account_id))
            else:
                async def _empty_patadd(): return None
                patadd_task = _empty_patadd()
            
            # Greatest MM Task (mapped to MM_ENGINE label)
            mm_engine_task = _run_or_skip('MM_ENGINE', lambda: get_greatest_mm_decision_engine().run(request))
            
            karbotu_out, reducemore_out, addnewpos_out, patadd_out, mm_out = await asyncio.gather(
                karbotu_task, 
                reducemore_task, 
                addnewpos_task,
                patadd_task,
                mm_engine_task,
                return_exceptions=True # Prevent one crash from killing all
            )
            
            # Helper to handle Exception results from return_exceptions=True
            if isinstance(karbotu_out, Exception):
                logger.error(f"[RUNALL] Karbotu crashed: {karbotu_out}", exc_info=True)
                karbotu_out = EmptyResult()
            else:
                logger.info(f"[RUNALL] ✅ KARBOTU completed: {len(karbotu_out.intents) if hasattr(karbotu_out, 'intents') else 0} intents")
            if isinstance(reducemore_out, Exception):
                logger.error(f"[RUNALL] Reducemore crashed: {reducemore_out}")
                reducemore_out = EmptyResult()
            if isinstance(addnewpos_out, Exception):
                logger.error(f"[RUNALL] AddNewPos crashed: {addnewpos_out}")
                addnewpos_out = EmptyResult()
            else:
                # Log ADDNEWPOS results
                anp_decisions = getattr(addnewpos_out, 'decisions', []) if addnewpos_out else []
                anp_filtered = getattr(addnewpos_out, 'filtered_out', []) if addnewpos_out else []
                anp_summary = getattr(addnewpos_out, 'step_summary', {}) if addnewpos_out else {}
                logger.info(f"[RUNALL] ✅ ADDNEWPOS completed: {len(anp_decisions)} decisions, {len(anp_filtered)} filtered, summary={anp_summary}")
            if isinstance(patadd_out, Exception):
                logger.error(f"[RUNALL] PATADD crashed: {patadd_out}")
                patadd_out = None
            else:
                if patadd_out and hasattr(patadd_out, 'total_orders'):
                    logger.info(f"[RUNALL] ✅ PATADD completed: {patadd_out.total_orders} orders (LPAT={len(patadd_out.lpat_orders)}, SPAT={len(patadd_out.spat_orders)})")
                elif patadd_out is None or (hasattr(patadd_out, 'intents') and not patadd_out.intents):
                    logger.info("[RUNALL] ✅ PATADD completed: 0 orders (no active signals or skipped)")
            if isinstance(mm_out, Exception):
                logger.error(f"[RUNALL] Greatest MM crashed: {mm_out}")
                mm_out = [] # Returns list of Decisions
            
            # Phase 11 Recommendation Bridge (Intents -> Proposals)
            # -----------------------------------------------------
            start_time = datetime.now()
            
            # Prepare Position Map for Adapter
            positions_map = {p.symbol: p for p in request.positions}
            
            # CRITICAL: Compute MinMax Area ONCE per cycle for all symbols
            # This pre-validates all potential orders before they become proposals
            try:
                from app.psfalgo.minmax_area_service import get_minmax_area_service
                minmax_svc = get_minmax_area_service()
                all_symbols = list(positions_map.keys())
                if all_symbols:
                    minmax_svc.compute_for_account(account_id, symbols=all_symbols)
                    logger.info(f"[RUNALL] MinMax Area computed for {len(all_symbols)} symbols (account={account_id})")
            except Exception as e:
                logger.warning(f"[RUNALL] MinMax Area computation failed: {e}")
            
            
            # 1. Adapt Karbotu Intents
            if karbotu_out and karbotu_out.intents:
                karbotu_decisions = self._adapt_intents_to_decisions(karbotu_out.intents, positions_map, request.metrics, account_id=account_id)
                
                # Generate & Store Proposals
                proposal_engine = get_proposal_engine()
                proposal_store = get_proposal_store()
                if proposal_engine and proposal_store and karbotu_decisions:
                    proposals = await proposal_engine.process_decision_response(
                        response=DecisionResponse(decisions=karbotu_decisions),
                        cycle_id=self.loop_count,
                        decision_source="KARBOTU",
                        decision_timestamp=start_time,
                        account_id=account_id
                    )
                    for p in proposals:
                        proposal_store.add_proposal(p)

            # 2. Adapt Reducemore Intents
            if reducemore_out and reducemore_out.intents:
                reducemore_decisions = self._adapt_intents_to_decisions(reducemore_out.intents, positions_map, request.metrics, account_id=account_id)
                
                # Generate & Store Proposals
                proposal_engine = get_proposal_engine()
                proposal_store = get_proposal_store()
                if proposal_engine and proposal_store and reducemore_decisions:
                    proposals = await proposal_engine.process_decision_response(
                        response=DecisionResponse(decisions=reducemore_decisions),
                        cycle_id=self.loop_count,
                        decision_source="REDUCEMORE",
                        decision_timestamp=start_time,
                        account_id=account_id
                    )
                    for p in proposals:
                        proposal_store.add_proposal(p)

            # 3. Adapt AddNewPos Decisions (ADDNEWPOS returns DecisionResponse, not intents)
            if addnewpos_out and hasattr(addnewpos_out, 'decisions') and addnewpos_out.decisions:
                # ADDNEWPOS already returns DecisionResponse with decisions, no need to adapt
                addnewpos_decisions = addnewpos_out.decisions
                
                # Generate & Store Proposals
                proposal_engine = get_proposal_engine()
                proposal_store = get_proposal_store()
                if proposal_engine and proposal_store and addnewpos_decisions:
                    proposals = await proposal_engine.process_decision_response(
                        response=addnewpos_out,  # Use the DecisionResponse directly
                        cycle_id=self.loop_count,
                        decision_source="ADDNEWPOS_ENGINE", # Matches UI tabs
                        decision_timestamp=start_time,
                        account_id=account_id
                    )
                    for p in proposals:
                        proposal_store.add_proposal(p)

            # 4. Adapt Greatest MM Decisions (NEW)
            if mm_out and isinstance(mm_out, list):
                # Generate & Store Proposals
                proposal_engine = get_proposal_engine()
                proposal_store = get_proposal_store()
                if proposal_engine and proposal_store:
                    proposals = await proposal_engine.process_decision_response(
                        response=DecisionResponse(decisions=mm_out),
                        cycle_id=self.loop_count,
                        decision_source="GREATEST_MM", # Maps to MM book
                        decision_timestamp=start_time,
                        account_id=account_id
                    )
                    for p in proposals:
                        proposal_store.add_proposal(p)

            # 5. Adapt PATADD Decisions (Pattern-based position increase)
            if patadd_out and hasattr(patadd_out, 'lpat_orders'):
                patadd_decisions = patadd_out.lpat_orders + patadd_out.spat_orders
                if patadd_decisions:
                    proposal_engine = get_proposal_engine()
                    proposal_store = get_proposal_store()
                    if proposal_engine and proposal_store:
                        proposals = await proposal_engine.process_decision_response(
                            response=DecisionResponse(decisions=patadd_decisions),
                            cycle_id=self.loop_count,
                            decision_source="PATADD_ENGINE",
                            decision_timestamp=start_time,
                            account_id=account_id
                        )
                        for p in proposals:
                            proposal_store.add_proposal(p)
                        logger.info(f"[RUNALL] ✅ PATADD generated {len(proposals)} proposals from {len(patadd_decisions)} decisions")

            # 3. Executive Engine Execution (LT Trim)
            lt_intents = []
            lt_diagnostic = {}
            if 'LT_TRIM' in self.active_engines:
                logger.info(f"[RUNALL] 🔍 LT_TRIM engine starting... (positions={len(request.positions)}, lt_trim_enabled={controls.lt_trim_enabled})")
                lt_intents, lt_diagnostic = await get_lt_trim_engine().run(
                    request,
                    (karbotu_out.signals if hasattr(karbotu_out, 'signals') else {}),
                    (reducemore_out.multipliers if hasattr(reducemore_out, 'multipliers') else {}),
                    effective_rules,
                    controls,
                    account_id=account_id # Explicitly pass account_id for Befday loading
                )
                logger.info(f"[RUNALL] LT_TRIM generated {len(lt_intents)} intents (diagnostic: {lt_diagnostic.get('generated_count', 0)} generated, {lt_diagnostic.get('analyzed_count', 0)} analyzed, global_status={lt_diagnostic.get('global_status', 'N/A')})")
                if lt_diagnostic.get('analyzed_count', 0) > 0:
                    # Log filter breakdown
                    details = lt_diagnostic.get('details', [])
                    filter_counts = {}
                    for detail in details:
                        status = detail.get('status', 'UNKNOWN')
                        filter_counts[status] = filter_counts.get(status, 0) + 1
                    logger.info(f"[RUNALL] LT_TRIM filter breakdown: {filter_counts}")
                if lt_intents:
                    logger.info(f"[RUNALL] LT_TRIM sample intents: {[(i.symbol, i.action, i.qty, getattr(i, 'priority', 'N/A')) for i in lt_intents[:5]]}")
            else:
                logger.warning(f"[RUNALL] ⚠️ LT_TRIM not in active_engines: {self.active_engines}")
            
            # Store Last Run Diagnostic (Universal)
            self.last_run_diagnostic = {
                'timestamp': datetime.now().isoformat(),
                'karbotu': karbotu_out.diagnostic if hasattr(karbotu_out, 'diagnostic') else {},
                'lt_trim': lt_diagnostic,
                'addnewpos': getattr(addnewpos_out, 'diagnostic', {}), # Assuming AddNewPos will have one
                'reducemore': getattr(reducemore_out, 'diagnostic', {}),
                'greatest_mm': len(mm_out) if mm_out and isinstance(mm_out, list) else 0
            }
            
            # Persist to Redis for API visibility (Cross-Process Support)
            try:
                from app.core.redis_client import get_redis
                import json
                redis = get_redis()
                if redis:
                    # Use a serializer helper if needed for datetimes, but isoformat() above handles timestamp
                    # Ensure all other fields are JSON serializable
                    redis.set("runall:last_diagnostic", json.dumps(self.last_run_diagnostic))
            except Exception as e:
                logger.warning(f"[RUNALL] Failed to save diagnostic to Redis: {e}")

            # 4. Conflict Resolution & Collection
            # CRITICAL FIX: ADDNEWPOS and GREATEST_MM already have their own dedicated proposal paths
            # (ADDNEWPOS at lines 296-312, GREATEST_MM at lines 314-327).
            # They generate proposals with decision_source="ADDNEWPOS_ENGINE" and "GREATEST_MM" respectively.
            # Including them in all_intents would DOUBLE the proposals (once via dedicated path, once via RUNALL).
            # Only LT_TRIM, KARBOTU, and REDUCEMORE go through the RUNALL conflict resolution path.
            all_intents = karbotu_out.intents + reducemore_out.intents + lt_intents
            logger.info(f"[RUNALL] Before conflict resolution: KARBOTU={len(karbotu_out.intents)}, REDUCEMORE={len(reducemore_out.intents)}, LT_TRIM={len(lt_intents)}, ADDNEWPOS_EXCLUDED(separate_path), MM_EXCLUDED(separate_path), TOTAL={len(all_intents)}")
            unique_intents = self._resolve_conflicts(all_intents)
            logger.info(f"[RUNALL] After conflict resolution: {len(unique_intents)} unique intents")
            # Count LT_TRIM intents after resolution
            lt_trim_after = [i for i in unique_intents if getattr(i, 'engine_name', '') == 'LT_TRIM' or 'LT_TRIM' in getattr(i, 'intent_category', '')]
            logger.info(f"[RUNALL] LT_TRIM intents after conflict resolution: {len(lt_trim_after)}")
            
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
                        decisions = self._adapt_intents_to_decisions(unique_intents, positions_map, request.metrics, account_id=account_id)
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
                                decision_timestamp=datetime.now(),
                                account_id=account_id
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
            
            # ── ORDER LIFECYCLE TRACKER: run monitoring cycle ──
            try:
                from app.monitoring.order_lifecycle_tracker import get_order_lifecycle_tracker
                get_order_lifecycle_tracker().check_cycle()
            except Exception as e:
                logger.debug(f"[RUNALL] OrderLifecycleTracker check_cycle error: {e}")
            
            return unique_intents if unique_intents else []

        except Exception as e:
            logger.error(f"[RUNALL] Cycle Error: {e}", exc_info=True)
            return []

    def _adapt_intents_to_decisions(
        self,
        intents: List[Any],
        positions_map: Dict[str, Any] = None,
        metrics: Optional[Dict[str, Any]] = None,
        account_id: Optional[str] = None
    ) -> List[Decision]:
        """
        Adapt Phase 11 Intents to Phase 10 Decisions for Proposal Engine compatibility.
        Handles both old-style dict/dataclass intents and new pydantic Intent models.
        If metrics is provided, sets decision.bench_chg and decision.ask_sell_pahalilik from symbol metrics (for Ask ph / B: in UI).
        
        MinMax Validation: If account_id is provided, validates each intent against MinMax Area constraints.
        Orders that exceed limits are trimmed or rejected BEFORE becoming proposals.
        """
        decisions: List[Decision] = []
        positions_map = positions_map or {}
        metrics = metrics or {}
        
        # Get MinMax service if account_id provided
        minmax_svc = None
        if account_id:
            try:
                from app.psfalgo.minmax_area_service import get_minmax_area_service, pre_validate_order_for_runall
                minmax_svc = get_minmax_area_service()
            except Exception as e:
                logger.debug(f"[ADAPT] MinMax service not available: {e}")
        
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
                
                # MINMAX PRE-VALIDATION: Validate and trim qty BEFORE creating Decision
                if account_id and minmax_svc and qty > 0:
                    from app.psfalgo.minmax_area_service import pre_validate_order_for_runall
                    allowed, adjusted_qty, minmax_reason = pre_validate_order_for_runall(
                        account_id=account_id,
                        symbol=intent.symbol,
                        action=action,
                        qty=int(qty)
                    )
                    
                    if not allowed:
                        logger.info(f"[RUNALL] MinMax BLOCKED: {intent.symbol} {action} {qty} - {minmax_reason}")
                        continue  # Skip this intent entirely
                    
                    if adjusted_qty != qty:
                        logger.info(f"[RUNALL] MinMax TRIMMED: {intent.symbol} {action} {qty} → {adjusted_qty} ({minmax_reason})")
                        qty = adjusted_qty
                
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
                    
                    # ═══════════════════════════════════════════════════════════
                    # CRITICAL: 0-SNAP RULE (Prevent tiny position remnants)
                    # ═══════════════════════════════════════════════════════════
                    # KURAL: DECREASE emirlerinde potential_qty -400 ile +400 
                    # arasında kalacaksa, pozisyon TAMAMEN kapatılmalı (0'a 
                    # getirilmeli). İncik cincik 50 lot, -50 lot gibi küçük 
                    # pozisyonlar kalmamalı.
                    #
                    # Örnek:
                    # - Current: +250, Proposed: -200 → Potential: +50 (incik!)
                    # - Adjusted: -250 → Potential: 0 ✅
                    # ═══════════════════════════════════════════════════════════
                    from app.psfalgo.zero_snap_validator import (
                        apply_zero_snap_rule,
                        is_decrease_order
                    )
                    
                    intent_category = getattr(intent, 'intent_category', '')
                    is_decrease = is_decrease_order(intent_category)
                    
                    if is_decrease and qty > 0:
                        # Calculate proposed change
                        decision_impact = qty if action == 'BUY' else -qty
                        
                        # Apply 0-SNAP rule
                        # CRITICAL: Use base_potential (includes open orders) not current_qty
                        # This prevents duplicate snap orders when open orders already cover
                        adjusted_impact, potential_qty = apply_zero_snap_rule(
                            symbol=intent.symbol,
                            current_qty=base_potential,  # Open orders factored in!
                            proposed_qty=decision_impact,
                            order_tag=intent_category,
                            is_decrease=True
                        )
                        
                        # Update qty to adjusted value
                        qty = abs(adjusted_impact)
                        
                        logger.debug(
                            f"[ADAPT] {intent.symbol}: "
                            f"action={action}, adjusted_qty={qty}, "
                            f"potential_qty={potential_qty}"
                        )
                    else:
                        # INCREASE orders: normal flow
                        decision_impact = qty if action == 'BUY' else -qty
                        potential_qty = base_potential + decision_impact
                
                # Create Decision
                sm = metrics.get(intent.symbol) if metrics else None
                decision = Decision(
                    symbol=intent.symbol,
                    action=action,
                    order_type="LIMIT",
                    calculated_lot=qty,
                    reason=reason,
                    confidence=0.8,
                    metrics_used=metadata,
                    current_qty=current_qty,
                    potential_qty=potential_qty,
                    bench_chg=getattr(sm, 'bench_chg', getattr(sm, 'benchmark_chg', None)) if sm else None,
                    ask_sell_pahalilik=getattr(sm, 'ask_sell_pahalilik', None) if sm else None,
                )
                
                # PHASE 11.5: Preserving Engine Name (for UI Tab Routing)
                # Priority: Use intent.engine_name if available, else map from intent_category
                engine_name_from_intent = getattr(intent, 'engine_name', None)
                
                if engine_name_from_intent:
                    # Direct engine_name set by engine (e.g. LT_TRIM, KARBOTU)
                    decision.engine_name = engine_name_from_intent
                else:
                    # Fallback: Map intent_category to engine name
                    category = getattr(intent, 'intent_category', 'UNKNOWN')
                    if 'LT_TRIM' in category:
                        decision.engine_name = 'LT_TRIM'
                    elif 'KARBOTU' in category:
                        decision.engine_name = 'KARBOTU'
                    elif 'REDUCEMORE' in category:
                        decision.engine_name = 'REDUCEMORE'
                    elif 'ADDNEWPOS' in category:
                        decision.engine_name = 'ADDNEWPOS_ENGINE'
                    elif 'MM_GREATEST' in category:
                        decision.engine_name = 'GREATEST_MM'
                    else:
                        decision.engine_name = category
                
                # Preserve step info if available
                if isinstance(metadata, dict) and "step" in metadata:
                    decision.step_number = metadata["step"]
                
                decisions.append(decision)
                logger.debug(f"[ADAPT] Intent {intent.symbol} {action} qty={qty}: engine_name={engine_name_from_intent} category={getattr(intent, 'intent_category', 'N/A')} -> Decision.engine_name={decision.engine_name}")
                
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
            
            # PHASE 11.5 FIX: Residual Quantity Logic (Not Winner-Takes-All)
            # Example: Karbotu (1000) vs LT (400) -> LT gets 400, Karbotu gets 600
            total_covered_qty = 0
            
            for candidate in candidates:
                needed = abs(candidate.qty)
                # How much of this specific intent is NOT covered by higher priority intents?
                remainder = max(0, needed - total_covered_qty)
                
                if remainder > 0:
                    # Update intent quantity to remainder
                    if remainder < needed:
                        logger.info(f"[CONFLICT] Partial fill for {candidate.intent_category}: {needed} -> {remainder} (Covered by higher priority: {total_covered_qty})")
                        candidate.qty = remainder # Update quantity in place
                        
                    resolved.append(candidate)
                    # Update total covered quantity for lower priority items
                    # Logic: We consider the "largest desired quantity" as the coverage ceiling so far
                    # If LT=400, covered=400.
                    # Next is Karbotu=1000. Remainder=600.
                    # New covered is NOT 400+600=1000 (additive). It is max(400, 1000) = 1000.
                    # Because we are talking about "Position Reduction Target".
                    # If I want to reduce by 1000 total, and someone else reduced 400, I only need 600 more.
                    total_covered_qty = max(total_covered_qty, needed)
                else:
                    logger.debug(f"[CONFLICT] Dropped {candidate.intent_category}({needed}) - fully covered by {total_covered_qty}")
            
        return resolved

    def _adapt_decisions_to_intents(self, decisions: List[Decision], correlation_id: str) -> List[Any]:
        """
        Adapt Greatest MM Decisions to Intent objects for Resolution context.
        """
        from app.psfalgo.intent_models import Intent, IntentAction
        import uuid
        
        intents = []
        for d in decisions:
            try:
                action = IntentAction.BUY if d.action == "BUY" else IntentAction.SELL
                
                intent = Intent(
                    id=f"mm_{uuid.uuid4().hex[:8]}",
                    symbol=d.symbol,
                    action=action,
                    qty=d.calculated_lot,
                    price=d.price_hint,
                    priority=d.priority or 10,
                    intent_category="MM_GREATEST",
                    reason_code="MM_GREATEST_SCORE",
                    reason_text=d.reason,
                    trigger_rule="greatest_mm_v1",
                    metric_values=d.metrics_used,
                    cycle_number=self.loop_count,
                    engine_name="GREATEST_MM"
                )
                intents.append(intent)
            except Exception as e:
                logger.error(f"[RUNALL] Error adapting MM decision to intent: {e}")
                
        return intents

    async def prepare_cycle_request(self, account_id: str, correlation_id: Optional[str] = None):
        """
        Public entry point for preparing a full cycle request (used by XNL and others).
        Returns the same DecisionRequest (positions, metrics, exposure, l1_data, etc.)
        that RUNALL uses. Call this before running LT_TRIM/KARBOTU/ADDNEWPOS/MM.
        """
        cid = correlation_id or str(uuid.uuid4())
        return await self._prepare_request(account_id, cid)

    async def _prepare_request(self, account_id, correlation_id):
        """
        Prepare DecisionRequest by fetching real data from APIs.
        """
        try:
            # 🔍 DIAGNOSTIC: Check Hammer connection and L1Update status
            try:
                from app.api.market_data_routes import get_hammer_feed, get_hammer_client
                
                hammer_feed = get_hammer_feed()
                hammer_client = get_hammer_client() if hasattr(get_hammer_client, '__call__') else None
                
                if hammer_client:
                    hammer_connected = hammer_client.is_connected() if hasattr(hammer_client, 'is_connected') else False
                    hammer_authenticated = getattr(hammer_client, 'authenticated', False)
                    l1_msg_count = getattr(hammer_client, '_l1_msg_count', 0)
                    logger.info(f"[RUNALL] 🔍 Hammer Diagnostic: connected={hammer_connected}, authenticated={hammer_authenticated}, L1Update_count={l1_msg_count}")
                elif hammer_feed and hasattr(hammer_feed, 'hammer_client'):
                    hammer_client = hammer_feed.hammer_client
                    hammer_connected = hammer_client.is_connected() if hasattr(hammer_client, 'is_connected') else False
                    hammer_authenticated = getattr(hammer_client, 'authenticated', False)
                    l1_msg_count = getattr(hammer_client, '_l1_msg_count', 0)
                    l1update_count = getattr(hammer_feed, '_l1update_count', 0)
                    logger.info(f"[RUNALL] 🔍 Hammer Diagnostic: connected={hammer_connected}, authenticated={hammer_authenticated}, L1Update_count={l1_msg_count}, Feed_L1Update_count={l1update_count}")
                else:
                    logger.warning(f"[RUNALL] ⚠️ Hammer Feed/Client not available - L1 data may not be updating")
            except Exception as e:
                logger.warning(f"[RUNALL] ⚠️ Error checking Hammer status: {e}")
            
            # 🔍 DIAGNOSTIC: Check DataFabric L1 data availability
            try:
                from app.core.data_fabric import get_data_fabric
                fabric = get_data_fabric()
                if fabric:
                    live_symbols_count = len(fabric._live_data) if hasattr(fabric, '_live_data') else 0
                    lifeless_mode = fabric.is_lifeless_mode() if hasattr(fabric, 'is_lifeless_mode') else False
                    mode_str = "💀 LIFELESS" if lifeless_mode else "🟢 LIVE"
                    logger.info(f"[RUNALL] 🔍 DataFabric Diagnostic: {mode_str} mode, live_symbols={live_symbols_count}")
                    
                    # Sample first 3 symbols to check L1 data
                    if hasattr(fabric, '_live_data') and fabric._live_data:
                        sample_symbols = list(fabric._live_data.keys())[:3]
                        for sym in sample_symbols:
                            live_data = fabric._live_data.get(sym, {})
                            bid = live_data.get('bid')
                            ask = live_data.get('ask')
                            last = live_data.get('last')
                            logger.info(f"[RUNALL] 🔍 DataFabric Sample: {sym} bid={bid} ask={ask} last={last}")
            except Exception as e:
                logger.warning(f"[RUNALL] ⚠️ Error checking DataFabric status: {e}")
            
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
            
            # 🔥 CRITICAL: Compute Janall Metrics BEFORE fetching snapshot
            # This ensures GORT/FBtot/SFStot are calculated in BOTH live and lifeless modes
            # In lifeless mode, market_data_cache contains fake bid/ask/last from DataFabric
            from app.api.market_data_routes import get_janall_metrics_engine as get_janall_from_api
            janall_engine = get_janall_from_api()
            if janall_engine and static_store:
                try:
                    # Get market_data_cache (contains fake data in lifeless mode)
                    from app.api.market_data_routes import market_data_cache
                    from app.api.market_data_routes import get_etf_market_data
                    
                    # Populate market_data_cache from DataFabric (RAM)
                    # MERGE with existing cache so we don't overwrite last/bid/ask with None
                    # (DataFabric may have no L1 for some symbols; cache may have Hammer L1)
                    # bench_chg = group avg daily_chg needs last + prev_close for each symbol
                    try:
                        from app.core.data_fabric import get_data_fabric
                        fabric = get_data_fabric()
                        if fabric:
                            mode_str = "💀 LIFELESS" if fabric.is_lifeless_mode() else "🟢 LIVE"
                            logger.info(f"[RUNALL] {mode_str} MODE: Syncing market_data_cache for {len(all_symbols)} symbols")
                            for symbol in all_symbols:
                                fast_snap = fabric.get_fast_snapshot(symbol)
                                existing = market_data_cache.get(symbol, {})
                                if fast_snap:
                                    # Merge: prefer non-None last/bid/ask from either source so daily_chg can be computed
                                    last = fast_snap.get('last') if fast_snap.get('last') is not None else existing.get('last')
                                    bid = fast_snap.get('bid') if fast_snap.get('bid') is not None else existing.get('bid')
                                    ask = fast_snap.get('ask') if fast_snap.get('ask') is not None else existing.get('ask')
                                    prev_close = fast_snap.get('prev_close') or existing.get('prev_close')
                                    market_data_cache[symbol] = {
                                        'bid': bid,
                                        'ask': ask,
                                        'last': last,
                                        'volume': fast_snap.get('volume') or existing.get('volume'),
                                        'timestamp': fast_snap.get('timestamp') or existing.get('timestamp'),
                                        'spread': None,
                                        'prev_close': prev_close,
                                        'price': last  # Alias
                                    }
                                elif existing:
                                    market_data_cache[symbol] = dict(existing)
                            
                            populated = len([s for s in all_symbols if s in market_data_cache])
                            with_last = len([s for s in all_symbols if (market_data_cache.get(s) or {}).get('last') is not None])
                            with_prev = len([s for s in all_symbols if (market_data_cache.get(s) or {}).get('prev_close') is not None])
                            logger.info(f"[RUNALL] Market cache synced: {populated}/{len(all_symbols)} symbols (with last: {with_last}, with prev_close: {with_prev})")
                    except Exception as e:
                        logger.error(f"[RUNALL] Error syncing market_data_cache: {e}")
                    
                    etf_data = get_etf_market_data()
                    
                    # Compute batch metrics - this calculates GORT/FBtot/SFStot from bid/ask/last
                    janall_engine.compute_batch_metrics(
                        all_symbols, static_store, market_data_cache, etf_data
                    )
                    logger.info(f"[RUNALL] Computed Janall metrics for {len(all_symbols)} symbols")
                    
                    # Update MarketSnapshotStore with computed metrics
                    # This ensures MetricsSnapshotAPI can read GORT/FBtot from MarketSnapshot
                    try:
                        from app.psfalgo.metric_compute_engine import get_metric_compute_engine
                        from app.psfalgo.market_snapshot_store import get_market_snapshot_store
                        
                        metric_engine = get_metric_compute_engine()
                        snapshot_store = get_market_snapshot_store()
                        
                        if metric_engine and snapshot_store:
                            updated_count = 0
                            for symbol in all_symbols:
                                try:
                                    static_data = static_store.get_static_data(symbol)
                                    if not static_data:
                                        continue
                                    
                                    market_data = market_data_cache.get(symbol, {})
                                    
                                    # 💀 LIFELESS MODE: Use fake data from DataFabric
                                    try:
                                        from app.core.data_fabric import get_data_fabric
                                        fabric = get_data_fabric()
                                        if fabric and fabric.is_lifeless_mode():
                                            fast_snap = fabric.get_fast_snapshot(symbol)
                                            if fast_snap:
                                                market_data = {
                                                    'bid': fast_snap.get('bid'),
                                                    'ask': fast_snap.get('ask'),
                                                    'last': fast_snap.get('last'),
                                                    'volume': fast_snap.get('volume'),
                                                    'timestamp': fast_snap.get('timestamp'),
                                                    'spread': None,
                                                    'prev_close': fast_snap.get('prev_close')
                                                }
                                    except Exception:
                                        pass
                                    
                                    if not market_data:
                                        continue
                                    
                                    # Get Janall metrics from cache
                                    janall_metrics = None
                                    if hasattr(janall_engine, 'symbol_metrics_cache'):
                                        janall_metrics = janall_engine.symbol_metrics_cache.get(symbol, {})
                                    
                                    # Compute and update MarketSnapshot
                                    snapshot = metric_engine.compute_metrics(
                                        symbol=symbol,
                                        market_data=market_data,
                                        position_data=None,
                                        static_data=static_data,
                                        janall_metrics=janall_metrics
                                    )
                                    
                                    await snapshot_store.update_current_snapshot(symbol, snapshot, account_type=account_id)
                                    updated_count += 1
                                except Exception as e:
                                    logger.debug(f"[RUNALL] Failed to update MarketSnapshot for {symbol}: {e}")
                            
                            if updated_count > 0:
                                logger.info(f"[RUNALL] Updated {updated_count} MarketSnapshots with GORT/FBtot/SFStot")
                    except Exception as e:
                        logger.warning(f"[RUNALL] Error updating MarketSnapshotStore: {e}")
                except Exception as e:
                    logger.warning(f"[RUNALL] Error computing Janall metrics: {e}")
            
            metrics = await self.metrics_snapshot_api.get_metrics_snapshot(all_symbols) # Fetch for ALL
            
            # 🔥 ENRICH metrics with GORT/FBtot from JanallMetricsEngine cache
            # This ensures KARBOTU/LT_TRIM get GORT/FBtot even if MarketSnapshot update failed
            # Scanner uses this same approach - reading directly from Janall cache
            try:
                if janall_engine and hasattr(janall_engine, 'symbol_metrics_cache'):
                    enriched_count = 0
                    created_count = 0
                    for symbol, symbol_metrics in metrics.items():
                        janall_data = janall_engine.symbol_metrics_cache.get(symbol, {})
                        if janall_data:
                            # Enrich with Janall metrics
                            symbol_metrics.gort = janall_data.get('gort')
                            symbol_metrics.fbtot = janall_data.get('fbtot')
                            symbol_metrics.sfstot = janall_data.get('sfstot')
                            symbol_metrics.sma63_chg = janall_data.get('sma63_chg')
                            symbol_metrics.sma246_chg = janall_data.get('sma246_chg')
                            symbol_metrics.bench_chg = janall_data.get('bench_chg')
                            # Enrich Pahalilik/Ucuzluk if available (Missing Link)
                            symbol_metrics.ask_sell_pahalilik = janall_data.get('ask_sell_pahalilik')
                            symbol_metrics.bid_buy_ucuzluk = janall_data.get('bid_buy_ucuzluk')
                            # 🔥 CRITICAL FIX: Enrich bid/ask/last/prev_close/spread
                            # These were MISSING — causing bid=None ask=None last=None in ALL engine logs
                            _bd = janall_data.get('_breakdown', {})
                            _inputs = _bd.get('inputs', {}) if _bd else {}
                            if symbol_metrics.bid is None and _inputs.get('bid') is not None:
                                symbol_metrics.bid = _inputs['bid']
                            if symbol_metrics.ask is None and _inputs.get('ask') is not None:
                                symbol_metrics.ask = _inputs['ask']
                            if symbol_metrics.last is None and _inputs.get('last') is not None:
                                symbol_metrics.last = _inputs['last']
                            if symbol_metrics.prev_close is None and _inputs.get('prev_close') is not None:
                                symbol_metrics.prev_close = _inputs['prev_close']
                            if symbol_metrics.spread is None and janall_data.get('spread') is not None:
                                symbol_metrics.spread = janall_data['spread']
                            enriched_count += 1
                    
                    # 🔥 ENRICH: Truth Ticks (son5_tick, last_truth_tick) + VOLAV (1h, 4h)
                    try:
                        from app.core.redis_client import get_redis
                        import json as _json
                        _redis = get_redis()
                        if _redis:
                            _tt_enriched = 0
                            for symbol, symbol_metrics in metrics.items():
                                try:
                                    # Truth tick data from Redis
                                    _tt_raw = _redis.get(f"truth_ticks:inspect:{symbol}")
                                    if _tt_raw:
                                        _tt = _json.loads(_tt_raw) if isinstance(_tt_raw, (str, bytes)) else _tt_raw
                                        # last_truth_tick = most recent trade price
                                        if isinstance(_tt, dict):
                                            symbol_metrics.last_truth_tick = _tt.get('price')
                                            symbol_metrics.son5_tick = _tt.get('son5_tick') or _tt.get('son5')
                                except Exception:
                                    pass
                                
                                try:
                                    # VOLAV from auto_analysis result
                                    _aa_raw = _redis.get("truth_ticks:auto_analysis")
                                    if _aa_raw:
                                        _aa = _json.loads(_aa_raw) if isinstance(_aa_raw, (str, bytes)) else _aa_raw
                                        if isinstance(_aa, dict):
                                            _sym_data = _aa.get('symbols', {}).get(symbol, {})
                                            if _sym_data:
                                                _v1h = _sym_data.get('volav_1h')
                                                _v4h = _sym_data.get('volav_4h')
                                                if _v1h and isinstance(_v1h, dict):
                                                    symbol_metrics.volav_1h = _v1h.get('volav_price')
                                                elif isinstance(_v1h, (int, float)):
                                                    symbol_metrics.volav_1h = _v1h
                                                if _v4h and isinstance(_v4h, dict):
                                                    symbol_metrics.volav_4h = _v4h.get('volav_price')
                                                elif isinstance(_v4h, (int, float)):
                                                    symbol_metrics.volav_4h = _v4h
                                                _tt_enriched += 1
                                except Exception:
                                    pass
                            if _tt_enriched > 0:
                                logger.info(f"[RUNALL] ✅ Enriched {_tt_enriched} metrics with truth_tick/volav data")
                    except Exception as _tt_err:
                        logger.debug(f"[RUNALL] Truth tick enrichment skipped: {_tt_err}")
                    
                    # 🔥 CRITICAL: Create SymbolMetrics for symbols in Janall cache but NOT in metrics
                    # This happens for ADDNEWPOS candidates that have no MarketSnapshot/market_data_cache
                    # but DO have Janall-computed metrics (bid/ask/last/fbtot/ucuzluk from live data)
                    from app.psfalgo.decision_models import SymbolMetrics as _SM
                    for symbol in all_symbols:
                        if symbol in metrics:
                            continue  # Already has metrics
                        janall_data = janall_engine.symbol_metrics_cache.get(symbol, {})
                        if not janall_data:
                            continue  # No Janall data either
                        
                        # Get static data for final_thg, short_final
                        s_data = static_store.get_static_data(symbol) if static_store else None
                        breakdown = janall_data.get('_breakdown', {})
                        inputs = breakdown.get('inputs', {})
                        
                        metrics[symbol] = _SM(
                            symbol=symbol,
                            timestamp=datetime.now(),
                            bid=inputs.get('bid'),
                            ask=inputs.get('ask'),
                            last=inputs.get('last'),
                            prev_close=inputs.get('prev_close'),
                            spread=janall_data.get('spread'),
                            fbtot=janall_data.get('fbtot'),
                            sfstot=janall_data.get('sfstot'),
                            gort=janall_data.get('gort'),
                            sma63_chg=janall_data.get('sma63_chg'),
                            sma246_chg=janall_data.get('sma246_chg'),
                            bench_chg=janall_data.get('bench_chg'),
                            bid_buy_ucuzluk=janall_data.get('bid_buy_ucuzluk'),
                            ask_sell_pahalilik=janall_data.get('ask_sell_pahalilik'),
                            final_thg=float(s_data.get('FINAL_THG', 0) or 0) if s_data else None,
                            short_final=float(s_data.get('SHORT_FINAL', 0) or 0) if s_data else None,
                            avg_adv=float(s_data.get('AVG_ADV', 0) or 0) if s_data else None,
                        )
                        created_count += 1
                    
                    if enriched_count > 0:
                        logger.info(f"[RUNALL] ✅ Enriched {enriched_count} metrics with GORT/FBtot from JanallMetrics cache")
                    if created_count > 0:
                        logger.info(f"[RUNALL] ✅ Created {created_count} NEW metrics from JanallMetrics cache (ADDNEWPOS candidates)")
            except Exception as e:
                logger.warning(f"[RUNALL] Error enriching metrics with Janall cache: {e}")
            
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
            # CRITICAL FIX: Pass account-specific pot_max from Port Adjuster V2
            # Without this, calculate_exposure() uses default pot_max_lot=63636
            # causing DEFANSIVE mode and 2713% Hard Risk for $1.2M portfolios!
            account_pot_max = None
            account_avg_price = None
            try:
                from app.port_adjuster.port_adjuster_store_v2 import get_port_adjuster_store_v2
                pa_store = get_port_adjuster_store_v2()
                pa_config = pa_store.get_config(account_id)
                if pa_config:
                    if pa_config.total_exposure_usd > 0:
                        account_pot_max = pa_config.total_exposure_usd
                    if pa_config.avg_pref_price > 0:
                        account_avg_price = pa_config.avg_pref_price
                    logger.info(
                        f"[RUNALL] Exposure config from Port Adjuster V2 ({account_id}): "
                        f"pot_max=${account_pot_max:,.0f}, avg_price=${account_avg_price}"
                    )
            except Exception as e:
                logger.warning(f"[RUNALL] Could not get Port Adjuster V2 config: {e}")
            
            # CRITICAL FIX: Pass avg_price as parameter instead of mutating singleton
            # This prevents cross-account contamination when multiple accounts are processed
            exposure = self.exposure_calculator.calculate_exposure(
                positions, pot_max=account_pot_max, avg_price=account_avg_price
            )
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
