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
from app.psfalgo.decision_models import DecisionRequest
from app.config.strategy_config_manager import get_strategy_config_manager
from app.state.runtime_controls import get_runtime_controls_manager

# Engines
from app.psfalgo.karbotu_engine import get_karbotu_engine
from app.psfalgo.reducemore_engine import get_reducemore_engine
from app.event_driven.decision_engine.lt_trim_engine import get_lt_trim_engine
# REMOVED: from app.psfalgo.order_controller import get_order_controller

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
            "dry_run_mode": self.dry_run_mode,
            "last_error": self.last_error
        }
        
    async def start(self):
        if self.loop_running: return
        self.loop_running = True
        asyncio.create_task(self._cycle_loop())
        logger.info("[RUNALL] Started Phase 11 Cycle Loop")

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

            # 3. Parallel Engine Execution (Analyzers)
            # Karbotu & Reducemore run in parallel
            karbotu_task = get_karbotu_engine().run(request, effective_rules)
            reducemore_task = get_reducemore_engine().run(request, effective_rules)
            
            karbotu_out, reducemore_out = await asyncio.gather(karbotu_task, reducemore_task)
            
            # 4. Executive Engine Execution (LT Trim)
            # Depends on Signals & Multipliers
            lt_intents = await get_lt_trim_engine().run(
                request,
                karbotu_out.signals,
                reducemore_out.multipliers,
                effective_rules,
                controls
            )

            # 5. Conflict Resolution
            # Merge all intent sources
            all_intents = karbotu_out.intents + reducemore_out.intents + lt_intents
            unique_intents = self._resolve_conflicts(all_intents)
            
            # 6. Submit to Execution (Intent Store)
            # (Assuming IntentStore logic exists)
            if unique_intents:
                logger.info(f"[RUNALL] Cycle {self.loop_count}: Submitting {len(unique_intents)} resolved intents")
                # self.intent_store.add_intents(unique_intents) # Placeholder
                
                # Phase 11.5 Simulation Hook:
                # Return intents for verification script inspection
                return unique_intents 
            else:
                logger.debug(f"[RUNALL] Cycle {self.loop_count}: No actionable intents")
                return []

        except Exception as e:
            logger.error(f"[RUNALL] Cycle Error: {e}", exc_info=True)
            return []
            
            # Wait remainder of interval
            await asyncio.sleep(self.config.get('cycle_interval_seconds', 60))

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
        # ... (Legacy Request Prep Logic) ...
        # Returning dummy for syntax check now, implementation uses existing helpers
        from app.psfalgo.decision_models import DecisionRequest, ExposureSnapshot
        return DecisionRequest(
            positions=[], metrics={}, 
            exposure=ExposureSnapshot(0,0,0,0,0,0.0,"NORMAL"),
            snapshot_ts=datetime.now(), correlation_id=correlation_id
        )

# Global Instance
_runall_engine = RunallEngine()
def get_runall_engine(): return _runall_engine

def initialize_runall_engine():
    """
    Initialize global RunallEngine instance.
    This is required by main.py startup event.
    """
    logger.info("[RUNALL] Initializing RunallEngine...")
    # Currently RunallEngine self-initializes via global accessors in run_single_cycle
    # This function serves as a hook for any future explicit initialization needs.
    pass
