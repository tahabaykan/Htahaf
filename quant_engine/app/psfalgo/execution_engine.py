"""
Execution Engine - Production-Grade

Execution Engine maps DecisionResponse → ExecutionIntent → Order Plan.
Read-only from decision layer (no feedback).

Key Principles:
- Idempotent: Same decision → same order set
- Deduplication: decision_timestamp + cycle_id + symbol + side
- Dry-run support: dry_run=True → only log, no broker calls
- Mock broker adapter: No real orders (Phase 4)
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from app.core.logger import logger
from app.psfalgo.decision_models import DecisionResponse, Decision
from app.psfalgo.execution_models import (
    ExecutionIntent,
    ExecutionPlan,
    ExecutionStatus,
    OrderSide,
    OrderType,
    OrderDeduplicationRecord
)


class ExecutionEngine:
    """
    Execution Engine - maps DecisionResponse to ExecutionIntent.
    
    Responsibilities:
    - Map Decision → ExecutionIntent
    - Deduplication (prevent duplicate orders)
    - Dry-run mode support
    - Mock broker adapter (Phase 4)
    
    Does NOT:
    - Modify decision engines
    - Send feedback to decision layer
    - Make trading decisions
    """
    
    def __init__(self, dry_run: bool = True):
        """
        Initialize Execution Engine.
        
        Args:
            dry_run: If True, only log intents (no broker calls)
        """
        self.dry_run = dry_run
        
        # Deduplication store (in-memory, cleared periodically)
        # Key: dedup_key (decision_timestamp + cycle_id + symbol + side)
        self._dedup_store: Dict[str, OrderDeduplicationRecord] = {}
        
        # Deduplication window (keep records for 1 hour)
        self._dedup_window_hours = 1.0
        
        logger.info(f"ExecutionEngine initialized (dry_run={dry_run})")
    
    def map_decision_to_intent(
        self,
        decision: Decision,
        cycle_id: int,
        decision_source: str,
        decision_timestamp: datetime
    ) -> Optional[ExecutionIntent]:
        """
        Map a Decision to ExecutionIntent.
        
        Args:
            decision: Decision object from decision engine
            cycle_id: RUNALL cycle count
            decision_source: "KARBOTU", "REDUCEMORE", or "ADDNEWPOS"
            decision_timestamp: Timestamp of decision (for deduplication)
            
        Returns:
            ExecutionIntent or None if decision is FILTERED
        """
        # Skip filtered decisions
        if decision.action == "FILTERED" or decision.filtered_out:
            return None
        
        # Map action to side
        side = None
        if decision.action in ["SELL", "REDUCE"]:
            side = OrderSide.SELL
        elif decision.action in ["BUY", "ADD"]:
            side = OrderSide.BUY
        else:
            logger.warning(f"[EXECUTION] Unknown action: {decision.action}")
            return None
        
        # Get quantity
        quantity = decision.calculated_lot
        if quantity is None or quantity <= 0:
            logger.warning(f"[EXECUTION] Invalid quantity for {decision.symbol}: {quantity}")
            return None
        
        # Map order_type from decision
        order_type = OrderType.LIMIT  # Default to LIMIT
        if decision.order_type:
            order_type_str = decision.order_type.upper()
            if "MARKET" in order_type_str:
                order_type = OrderType.MARKET
            elif "LIMIT" in order_type_str:
                order_type = OrderType.LIMIT
        
        # Get price hint (for LIMIT orders)
        price = decision.price_hint
        
        # Create execution intent
        intent = ExecutionIntent(
            symbol=decision.symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            price_hint=decision.price_hint,
            decision_timestamp=decision_timestamp,
            cycle_id=cycle_id,
            decision_source=decision_source,
            decision_reason=decision.reason,
            decision_confidence=decision.confidence or 0.0,
            status=ExecutionStatus.PENDING
        )
        
        logger.debug(
            f"[EXECUTION] Mapped decision to intent: "
            f"{decision.symbol} {side.value} {quantity} @ {price} "
            f"(source={decision_source}, cycle={cycle_id})"
        )
        
        return intent
    
    def check_duplicate(self, intent: ExecutionIntent) -> bool:
        """
        Check if intent is duplicate (already executed).
        
        Args:
            intent: ExecutionIntent to check
            
        Returns:
            True if duplicate, False otherwise
        """
        dedup_key = intent.dedup_key
        
        # Check deduplication store
        if dedup_key in self._dedup_store:
            record = self._dedup_store[dedup_key]
            logger.debug(
                f"[EXECUTION] Duplicate detected: {intent.symbol} {intent.side.value} "
                f"(executed at {record.execution_timestamp.isoformat()})"
            )
            return True
        
        return False
    
    def record_execution(self, intent: ExecutionIntent, order_id: Optional[str] = None):
        """
        Record execution (for deduplication).
        
        Args:
            intent: ExecutionIntent that was executed
            order_id: Broker order ID (if executed)
        """
        record = OrderDeduplicationRecord(
            dedup_key=intent.dedup_key,
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            cycle_id=intent.cycle_id,
            decision_timestamp=intent.decision_timestamp,
            execution_timestamp=datetime.now(),
            order_id=order_id
        )
        
        self._dedup_store[intent.dedup_key] = record
        
        logger.debug(
            f"[EXECUTION] Recorded execution: {intent.symbol} {intent.side.value} "
            f"{intent.quantity} (order_id={order_id})"
        )
        
        # Cleanup old records (keep dedup store small)
        self._cleanup_dedup_store()
    
    def _cleanup_dedup_store(self):
        """Remove old deduplication records (older than window)"""
        cutoff_time = datetime.now() - timedelta(hours=self._dedup_window_hours)
        
        keys_to_remove = [
            key for key, record in self._dedup_store.items()
            if record.execution_timestamp < cutoff_time
        ]
        
        for key in keys_to_remove:
            del self._dedup_store[key]
        
        if keys_to_remove:
            logger.debug(f"[EXECUTION] Cleaned up {len(keys_to_remove)} old dedup records")
    
    async def process_decision_response(
        self,
        response: DecisionResponse,
        cycle_id: int,
        decision_source: str,
        decision_timestamp: datetime
    ) -> ExecutionPlan:
        """
        Process DecisionResponse and create ExecutionPlan.
        
        Args:
            response: DecisionResponse from decision engine
            cycle_id: RUNALL cycle count
            decision_source: "KARBOTU", "REDUCEMORE", or "ADDNEWPOS"
            decision_timestamp: Timestamp of decision (for deduplication)
            
        Returns:
            ExecutionPlan with ExecutionIntents
        """
        intents: List[ExecutionIntent] = []
        
        # Map each decision to intent
        for decision in response.decisions:
            intent = self.map_decision_to_intent(
                decision=decision,
                cycle_id=cycle_id,
                decision_source=decision_source,
                decision_timestamp=decision_timestamp
            )
            
            if intent is None:
                continue
            
            # Check for duplicates
            if self.check_duplicate(intent):
                intent.status = ExecutionStatus.SKIPPED
                intent.error = "Duplicate order (already executed)"
                logger.info(
                    f"[EXECUTION] Skipping duplicate: {intent.symbol} {intent.side.value} "
                    f"{intent.quantity} (cycle={cycle_id})"
                )
            
            intents.append(intent)
        
        # Create execution plan
        plan = ExecutionPlan(
            cycle_id=cycle_id,
            cycle_timestamp=decision_timestamp,
            intents=intents,
            dry_run=self.dry_run
        )
        
        logger.info(
            f"[EXECUTION] Execution plan created: {len(intents)} intents "
            f"(source={decision_source}, cycle={cycle_id}, dry_run={self.dry_run})"
        )
        
        return plan
    
    async def execute_plan(self, plan: ExecutionPlan) -> Dict[str, Any]:
        """
        Execute execution plan (dry-run or real).
        
        Args:
            plan: ExecutionPlan to execute
            
        Returns:
            Execution result summary
        """
        if self.dry_run:
            return await self._execute_plan_dry_run(plan)
        else:
            return await self._execute_plan_real(plan)
    
    async def _execute_plan_dry_run(self, plan: ExecutionPlan) -> Dict[str, Any]:
        """
        Execute plan in dry-run mode (only log, no broker calls).
        
        Args:
            plan: ExecutionPlan to execute
            
        Returns:
            Execution result summary
        """
        executed_count = 0
        skipped_count = 0
        error_count = 0
        
        for intent in plan.intents:
            if intent.status == ExecutionStatus.SKIPPED:
                skipped_count += 1
                continue
            
            if intent.status == ExecutionStatus.ERROR:
                error_count += 1
                continue
            
            # Dry-run: Just log the intent
            logger.info(
                f"[EXECUTION] [DRY-RUN] Would execute: "
                f"{intent.symbol} {intent.side.value} {intent.quantity} "
                f"@ {intent.price} ({intent.order_type.value}) "
                f"(source={intent.decision_source}, reason={intent.decision_reason})"
            )
            
            # Mark as executed (for deduplication)
            intent.status = ExecutionStatus.EXECUTED
            intent.execution_timestamp = datetime.now()
            intent.order_id = f"DRY_RUN_{intent.symbol}_{intent.cycle_id}_{datetime.now().timestamp()}"
            
            # Record execution (for deduplication)
            self.record_execution(intent, order_id=intent.order_id)
            
            executed_count += 1
        
        result = {
            'executed': executed_count,
            'skipped': skipped_count,
            'errors': error_count,
            'total': len(plan.intents),
            'dry_run': True
        }
        
        logger.info(
            f"[EXECUTION] [DRY-RUN] Execution complete: "
            f"{executed_count} executed, {skipped_count} skipped, {error_count} errors"
        )
        
        return result
    
    async def execute_plan_from_intent(self, order_plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute order from approved intent.
        
        Args:
            order_plan: Order plan from intent (dict with action, symbol, qty, price, order_type, intent_id)
            
        Returns:
            Execution result
        """
        try:
            if self.dry_run:
                logger.info(
                    f"[EXECUTION] [DRY-RUN] Would execute from intent: "
                    f"{order_plan.get('symbol')} {order_plan.get('action')} {order_plan.get('qty')} "
                    f"@ {order_plan.get('price')} ({order_plan.get('order_type')})"
                )
                return {
                    'executed': True,
                    'dry_run': True,
                    'order_id': f"DRY_RUN_{order_plan.get('intent_id')}",
                    'message': 'Order simulated (dry-run mode)'
                }
            else:
                # TODO: Real execution (Phase 4)
                logger.warning("[EXECUTION] Real execution not yet implemented")
                return {
                    'executed': False,
                    'dry_run': False,
                    'error': 'Real execution not yet implemented'
                }
        except Exception as e:
            logger.error(f"[EXECUTION] Error executing from intent: {e}", exc_info=True)
            return {
                'executed': False,
                'error': str(e)
            }
    
    async def _execute_plan_real(self, plan: ExecutionPlan) -> Dict[str, Any]:
        """
        Execute plan in real mode (call mock broker adapter).
        
        Args:
            plan: ExecutionPlan to execute
            
        Returns:
            Execution result summary
        """
        # Phase 4: Mock broker adapter (no real orders)
        logger.warning("[EXECUTION] Real execution mode not implemented (Phase 4: Mock only)")
        
        # For now, treat as dry-run
        return await self._execute_plan_dry_run(plan)


# Global instance
_execution_engine: Optional[ExecutionEngine] = None


def get_execution_engine() -> Optional[ExecutionEngine]:
    """Get global ExecutionEngine instance"""
    return _execution_engine


def initialize_execution_engine(dry_run: bool = True):
    """Initialize global ExecutionEngine instance"""
    global _execution_engine
    _execution_engine = ExecutionEngine(dry_run=dry_run)
    logger.info(f"ExecutionEngine initialized (dry_run={dry_run})")


