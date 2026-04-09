"""
Execution Engine Test

Tests ExecutionEngine mapping and deduplication.
"""

import asyncio
from datetime import datetime
from app.core.logger import logger
from app.psfalgo.decision_models import (
    DecisionRequest,
    DecisionResponse,
    Decision,
    PositionSnapshot,
    SymbolMetrics,
    ExposureSnapshot
)
from app.psfalgo.execution_engine import ExecutionEngine, initialize_execution_engine
from app.psfalgo.execution_models import ExecutionStatus, OrderSide


async def test_execution_engine():
    """Test ExecutionEngine with sample DecisionResponse"""
    
    # Initialize execution engine (dry-run mode)
    engine = ExecutionEngine(dry_run=True)
    
    # Create sample decision response (KARBOTU)
    decisions = [
        Decision(
            symbol="MS PRK",
            action="SELL",
            order_type="ASK_SELL",
            calculated_lot=300,
            price_hint=27.32,
            step_number=2,
            reason="Fbtot < 1.10 and Ask Sell Pahalılık > -0.10",
            confidence=0.62,
            timestamp=datetime.now()
        ),
        Decision(
            symbol="WFC PRY",
            action="SELL",
            order_type="ASK_SELL",
            calculated_lot=200,
            price_hint=24.52,
            step_number=2,
            reason="Fbtot < 1.10 and Ask Sell Pahalılık > -0.10",
            confidence=0.66,
            timestamp=datetime.now()
        )
    ]
    
    response = DecisionResponse(
        decisions=decisions,
        filtered_out=[],
        step_summary={},
        execution_time_ms=0.1,
        timestamp=datetime.now()
    )
    
    # Process decision response
    decision_timestamp = datetime.now()
    plan = await engine.process_decision_response(
        response=response,
        cycle_id=1,
        decision_source='KARBOTU',
        decision_timestamp=decision_timestamp
    )
    
    print(f"\nExecution Plan:")
    print(f"  Cycle ID: {plan.cycle_id}")
    print(f"  Total Intents: {plan.total_intents}")
    print(f"  Dry Run: {plan.dry_run}")
    print(f"\nIntents:")
    for intent in plan.intents:
        print(f"  {intent.symbol}: {intent.side.value} {intent.quantity} @ {intent.price} ({intent.order_type.value})")
        print(f"    Source: {intent.decision_source}, Reason: {intent.decision_reason}")
        print(f"    Dedup Key: {intent.dedup_key}")
    
    # Execute plan
    result = await engine.execute_plan(plan)
    print(f"\nExecution Result:")
    print(f"  Executed: {result['executed']}")
    print(f"  Skipped: {result['skipped']}")
    print(f"  Errors: {result['errors']}")
    print(f"  Dry Run: {result['dry_run']}")
    
    # Test deduplication (same decision again)
    print(f"\n--- Testing Deduplication ---")
    plan2 = await engine.process_decision_response(
        response=response,
        cycle_id=1,
        decision_source='KARBOTU',
        decision_timestamp=decision_timestamp  # Same timestamp = duplicate
    )
    
    result2 = await engine.execute_plan(plan2)
    print(f"Second execution (same decision):")
    print(f"  Executed: {result2['executed']}")
    print(f"  Skipped: {result2['skipped']} (should be 2 - duplicates)")
    print(f"  Errors: {result2['errors']}")
    
    # Test different cycle (not duplicate)
    print(f"\n--- Testing Different Cycle (Not Duplicate) ---")
    plan3 = await engine.process_decision_response(
        response=response,
        cycle_id=2,  # Different cycle = not duplicate
        decision_source='KARBOTU',
        decision_timestamp=datetime.now()  # Different timestamp = not duplicate
    )
    
    result3 = await engine.execute_plan(plan3)
    print(f"Third execution (different cycle):")
    print(f"  Executed: {result3['executed']}")
    print(f"  Skipped: {result3['skipped']}")
    print(f"  Errors: {result3['errors']}")
    
    print("\n[OK] Execution Engine test complete")


if __name__ == "__main__":
    asyncio.run(test_execution_engine())

