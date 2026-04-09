"""
RUNALL Engine V2 - Sequential Execution with LotCoordinator

⚠️ DEPRECATED — NOT IMPORTED BY ANY MODULE ⚠️

This was an incomplete prototype. The active version is:
    app.psfalgo.runall_engine.RunallEngine (v1)

NOTE: _prepare_request() is a stub, ADDNEWPOS phase is a TODO.
This file is NOT used in production. Kept for reference only.
TODO: Delete this file.

Major Changes (planned but never completed):
1. Sequential Execution: LT_TRIM → KARBOTU/REDUCEMORE → ADDNEWPOS
2. LotCoordinator Integration: Smart lot sizing and deduplication
3. CycleReporter Integration: Full transparency on all decisions
4. Enhanced Tagging: Detailed tags with stage/step info
"""
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid

from app.core.logger import logger
from app.core.lot_coordinator import get_lot_coordinator, reset_lot_coordinator
from app.core.cycle_reporter import get_cycle_reporter, SymbolStatus
from app.psfalgo.decision_models import (
    DecisionRequest,
    Decision,
    DecisionResponse
)
from app.psfalgo.intent_models import Intent
from app.config.strategy_config_manager import get_strategy_config_manager
from app.state.runtime_controls import get_runtime_controls_manager

# Engines
from app.psfalgo.karbotu_engine_v2 import get_karbotu_engine_v2
from app.psfalgo.reducemore_engine_v2 import get_reducemore_engine_v2
from app.psfalgo.addnewpos_engine import get_addnewpos_engine
from app.event_driven.decision_engine.lt_trim_engine import get_lt_trim_engine

# Proposal & Intent Storage
from app.psfalgo.proposal_engine import get_proposal_engine
from app.psfalgo.proposal_store import get_proposal_store
from app.psfalgo.intent_store import get_intent_store

# Data APIs
from app.psfalgo.position_snapshot_api import get_position_snapshot_api
from app.psfalgo.metrics_snapshot_api import get_metrics_snapshot_api
from app.psfalgo.exposure_calculator import get_exposure_calculator

# Execution
from app.psfalgo.execution_engine import get_execution_engine
from app.trading.trading_account_context import get_trading_context


class RunallEngineV2:
    """
    RUNALL Engine V2 - Sequential execution with smart lot coordination
    """
    
    def __init__(self, config=None):
        self.config = config or {}
        self.loop_running = False
        self.loop_count = 0
        
        # State
        self.global_state = "IDLE"
        self.cycle_state = "INIT"
        self.dry_run_mode = True
        self.cycle_start_time = None
        self.next_cycle_time = None
        self.last_error = None
        
        # Active Engines
        self.active_engines = ['LT_TRIM', 'KARBOTU_V2', 'ADDNEWPOS']
        
        logger.info("[RUNALL_V2] Initialized with sequential execution")
    
    def get_state(self) -> Dict[str, Any]:
        """Get current engine state"""
        return {
            "global_state": self.global_state,
            "cycle_state": self.cycle_state,
            "loop_count": self.loop_count,
            "loop_running": self.loop_running,
            "active_engines": self.active_engines,
            "dry_run_mode": self.dry_run_mode,
            "last_error": self.last_error
        }
    
    async def run_single_cycle_v2(self):
        """
        Run a single cycle with sequential execution
        
        Flow:
            1. Check simulation mode
            2. Initialize coordinators
            3. LT_TRIM (FIRST!)
            4. KARBOTU/REDUCEMORE (SECOND)
            5. ADDNEWPOS (LAST)
            6. Generate summary
        """
        self.loop_count += 1
        cycle_id = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{self.loop_count}"
        
        logger.info("=" * 80)
        logger.info(f"[RUNALL_V2] CYCLE {self.loop_count} START: {cycle_id}")
        
        # Check simulation mode
        from app.core.simulation_controller import get_simulation_controller
        sim_controller = get_simulation_controller()
        is_simulation = sim_controller.is_simulation_mode()
        
        if is_simulation:
            logger.warning("=" * 80)
            logger.warning("[RUNALL_V2] 🎭 SIMULATION MODE - Orders will be FAKE")
            logger.warning("=" * 80)
        else:
            logger.info("[RUNALL_V2] 💰 REAL MODE - Orders will be REAL")
        
        logger.info("=" * 80)
        
        try:
            # 1. Initialize coordination services
            lot_coordinator = reset_lot_coordinator()
            cycle_reporter = get_cycle_reporter()
            cycle_reporter.start_cycle(cycle_id)
            
            # 2. Get context
            ctx = get_trading_context()
            account_id = ctx.trading_mode.value
            
            logger.info(f"[RUNALL_V2] Account: {account_id}")
            
            # 3. Cancel stale orders
            from app.psfalgo.order_manager import get_order_controller
            oc = get_order_controller()
            if oc:
                cancelled = await oc.cancel_open_orders(account_id, book="LT")
                if cancelled > 0:
                    logger.info(f"[RUNALL_V2] Cancelled {cancelled} stale LT orders")
            
            # 4. Prepare request
            request = await self._prepare_request(account_id, cycle_id)
            if not request:
                logger.warning("[RUNALL_V2] Failed to prepare request")
                return
            
            # 5. Create position map for easy lookup
            position_map = {pos.symbol: pos for pos in request.positions}
            
            # ================================================================
            # PHASE 1: LT_TRIM (FIRST!)
            # ================================================================
            logger.info("[RUNALL_V2] >>> PHASE 1: LT_TRIM")
            
            lt_decisions = []
            if 'LT_TRIM' in self.active_engines:
                lt_engine = get_lt_trim_engine()
                lt_intents = await lt_engine.run(request, {}, {}, {}, {}, account_id=account_id)
                
                # Convert intents to decisions
                for intent in lt_intents:
                    pos = position_map.get(intent.symbol)
                    if not pos:
                        continue
                    
                    # Process through LotCoordinator
                    final_qty, lot_rule, adjusted_reason = lot_coordinator.calculate_lot_size(
                        symbol=intent.symbol,
                        action=intent.side,
                        requested_qty=intent.quantity,
                        current_position=pos.qty,
                        engine='LT_TRIM',
                        tag=intent.classification or 'LT_TRIM',
                        reason=intent.reason or 'LT_TRIM decision'
                    )
                    
                    if final_qty > 0:
                        decision = Decision(
                            symbol=intent.symbol,
                            action=intent.side,
                            calculated_lot=final_qty,
                            tag=intent.classification,
                            metadata={'lot_rule': lot_rule, 'original_qty': intent.quantity}
                        )
                        lt_decisions.append(decision)
                        
                        # Record to CycleReporter
                        cycle_reporter.record_symbol_status(
                            symbol=intent.symbol,
                            status=SymbolStatus.SENT,
                            engine='LT_TRIM',
                            action=intent.side,
                            qty=final_qty,
                            tag=intent.classification,
                            reason=adjusted_reason,
                            current_qty=pos.qty,
                            befday_qty=getattr(pos, 'befday_qty', None)
                        )
                    else:
                        # Blocked by lot rules
                        cycle_reporter.record_symbol_status(
                            symbol=intent.symbol,
                            status=SymbolStatus.BLOCKED,
                            engine='LT_TRIM',
                            block_reason=lot_rule,
                            reason=adjusted_reason,
                            current_qty=pos.qty
                        )
            
            logger.info(f"[RUNALL_V2] LT_TRIM: {len(lt_decisions)} decisions")
            
            # ================================================================
            # PHASE 2: KARBOTU V2 or REDUCEMORE V2 (SECOND!)
            # ================================================================
            logger.info("[RUNALL_V2] >>> PHASE 2: KARBOTU/REDUCEMORE")
            
            karbotu_decisions = []
            if 'KARBOTU_V2' in self.active_engines:
                # Determine exposure mode
                reducemore_v2 = get_reducemore_engine_v2()
                mode_result = await reducemore_v2.run(request)
                exposure_mode = mode_result.get('mode', 'Unknown')
                
                logger.info(f"[RUNALL_V2] Exposure Mode: {exposure_mode}")
                
                if exposure_mode == 'OFANSIF':
                    # Run KARBOTU_V2
                    karbotu_v2 = get_karbotu_engine_v2()
                    karbotu_output = await karbotu_v2.run(request)
                    
                    # Process each decision through LotCoordinator
                    for dec in karbotu_output.decisions:
                        pos = position_map.get(dec.symbol)
                        if not pos:
                            continue
                        
                        final_qty, lot_rule, adjusted_reason = lot_coordinator.calculate_lot_size(
                            symbol=dec.symbol,
                            action=dec.action,
                            requested_qty=dec.qty,
                            current_position=pos.qty,
                            engine='KARBOTU_V2',
                            tag=dec.tag,
                            reason=dec.reason
                        )
                        
                        if final_qty > 0:
                            dec.qty = final_qty
                            karbotu_decisions.append(dec)
                            
                            # Record to CycleReporter
                            cycle_reporter.record_symbol_status(
                                symbol=dec.symbol,
                                status=SymbolStatus.SENT,
                                engine='KARBOTU_V2',
                                action=dec.action,
                                qty=final_qty,
                                tag=dec.tag,
                                reason=adjusted_reason,
                                current_qty=pos.qty,
                                befday_qty=getattr(pos, 'befday_qty', None),
                                **dec.metadata
                            )
                        else:
                            # Blocked
                            cycle_reporter.record_symbol_status(
                                symbol=dec.symbol,
                                status=SymbolStatus.BLOCKED,
                                engine='KARBOTU_V2',
                                block_reason=lot_rule,
                                reason=adjusted_reason,
                                current_qty=pos.qty
                            )
                else:
                    logger.info(f"[RUNALL_V2] KARBOTU skipped (mode: {exposure_mode})")
            
            logger.info(f"[RUNALL_V2] KARBOTU: {len(karbotu_decisions)} decisions")
            
            # ================================================================
            # PHASE 3: ADDNEWPOS (LAST!)
            # ================================================================
            logger.info("[RUNALL_V2] >>> PHASE 3: ADDNEWPOS")
            
            addnewpos_decisions = []
            # TODO: Implement ADDNEWPOS integration
            # Similar pattern to above
            
            # ================================================================
            # PHASE 4: Generate Cycle Summary
            # ================================================================
            summary = cycle_reporter.end_cycle()
            
            logger.info("=" * 80)
            logger.info(f"[RUNALL_V2] CYCLE {self.loop_count} END")
            logger.info("=" * 80)
            
            return{
                'cycle_id': cycle_id,
                'lt_decisions': len(lt_decisions),
                'karbotu_decisions': len(karbotu_decisions),
                'addnewpos_decisions': len(addnewpos_decisions),
                'summary': summary
            }
        
        except Exception as e:
            logger.error(f"[RUNALL_V2] Cycle error: {e}", exc_info=True)
            self.last_error = str(e)
            return None
    
    async def _prepare_request(self, account_id: str, correlation_id: str):
        """Prepare decision request (placeholder)"""
        # TODO: Implement full request preparation
        # This should load positions, metrics, exposure, etc.
        logger.debug(f"[RUNALL_V2] Preparing request for {account_id}")
        return DecisionRequest(
            cycle_id=correlation_id,
            account_id=account_id,
            positions=[],
            metrics={},
            exposure=None
        )


# Global instance
_runall_engine_v2: Optional[RunallEngineV2] = None


def get_runall_engine_v2() -> RunallEngineV2:
    """Get global RUNALL V2 engine"""
    global _runall_engine_v2
    if _runall_engine_v2 is None:
        _runall_engine_v2 = RunallEngineV2()
    return _runall_engine_v2
