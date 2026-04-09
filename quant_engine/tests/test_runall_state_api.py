"""
RunallStateAPI Test

Tests observability and control layer.
"""

import asyncio
from datetime import datetime
from app.core.logger import logger
from app.psfalgo.runall_state_api import (
    RunallStateAPI,
    initialize_runall_state_api,
    get_runall_state_api
)
from app.psfalgo.runall_engine import RunallEngine
from app.psfalgo.decision_models import DecisionResponse, Decision
from app.psfalgo.execution_models import ExecutionPlan, ExecutionIntent, ExecutionStatus, OrderSide, OrderType


async def test_runall_state_api():
    """Test RunallStateAPI observability and controls"""
    
    # Initialize State API
    initialize_runall_state_api()
    state_api = get_runall_state_api()
    
    if not state_api:
        print("ERROR: State API not initialized")
        return
    
    print("\n=== RunallStateAPI Test ===\n")
    
    # Test 1: State Snapshot (without engine)
    print("1. Testing state snapshot (no engine):")
    snapshot = state_api.get_state_snapshot()
    if snapshot:
        print(f"   State: {snapshot.global_state}")
        print(f"   Cycle ID: {snapshot.cycle_id}")
    else:
        print("   No engine available (expected)")
    
    # Test 2: Record Decision Response
    print("\n2. Testing decision response recording:")
    decision = Decision(
        symbol="MS PRK",
        action="SELL",
        order_type="ASK_SELL",
        calculated_lot=300,
        price_hint=27.32,
        reason="Fbtot < 1.10",
        confidence=0.62,
        timestamp=datetime.now()
    )
    response = DecisionResponse(
        decisions=[decision],
        filtered_out=[],
        step_summary={},
        execution_time_ms=0.1,
        timestamp=datetime.now()
    )
    
    state_api.record_decision_response(
        response=response,
        cycle_id=1,
        source='KARBOTU',
        decision_timestamp=datetime.now()
    )
    
    snapshot = state_api.get_decision_snapshot('KARBOTU')
    if snapshot:
        print(f"   Recorded: {snapshot.total_decisions} decisions, {snapshot.total_filtered} filtered")
        print(f"   Source: {snapshot.source}, Cycle: {snapshot.cycle_id}")
    else:
        print("   ERROR: Snapshot not found")
    
    # Test 3: Record Execution Plan
    print("\n3. Testing execution plan recording:")
    intent = ExecutionIntent(
        symbol="MS PRK",
        side=OrderSide.SELL,
        quantity=300,
        order_type=OrderType.LIMIT,
        price=27.32,
        decision_timestamp=datetime.now(),
        cycle_id=1,
        decision_source='KARBOTU',
        decision_reason="Fbtot < 1.10",
        status=ExecutionStatus.EXECUTED
    )
    
    plan = ExecutionPlan(
        cycle_id=1,
        cycle_timestamp=datetime.now(),
        intents=[intent],
        dry_run=True
    )
    
    state_api.record_execution_plan(plan=plan, source='KARBOTU')
    
    history = state_api.get_execution_history(last_n=5)
    print(f"   Recorded: {len(history)} execution plans in history")
    if history:
        last = history[-1]
        print(f"   Last: {last.source} cycle={last.cycle_id}, {last.executed_count} executed, {last.skipped_count} skipped")
    
    # Test 4: Audit Trail
    print("\n4. Testing audit trail:")
    state_api.add_audit_entry('TEST_EVENT', {'test': True}, cycle_id=1)
    trail = state_api.get_audit_trail(last_n=5)
    print(f"   Recorded: {len(trail)} audit entries")
    if trail:
        last = trail[-1]
        print(f"   Last: {last['event']} at {last['timestamp']}")
    
    # Test 5: Manual Controls (without engine - will fail gracefully)
    print("\n5. Testing manual controls (no engine):")
    result = await state_api.start_runall()
    print(f"   Start result: {result.get('success')} - {result.get('error', result.get('message'))}")
    
    result = state_api.toggle_dry_run()
    print(f"   Toggle dry-run result: {result.get('success')} - {result.get('error', result.get('message'))}")
    
    print("\n[OK] RunallStateAPI test complete")


if __name__ == "__main__":
    asyncio.run(test_runall_state_api())




