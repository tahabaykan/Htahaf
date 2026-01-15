# Execution Chaos Testing

## Overview

Execution Chaos Testing simulates adversarial broker behavior to harden the system against real-world edge cases. The system must remain deterministic, consistent, and risk-safe under all conditions.

## Chaos Scenarios

### 1. Out-of-Order Events

**Scenario**: Events arrive in unexpected order.

**Examples**:
- Fill event arrives BEFORE order ACCEPTED event
- Cancel ACK arrives AFTER a fill
- Replace ACK arrives before Cancel ACK

**Expected Behavior**:
- System handles out-of-order events gracefully
- No negative position drift (no ghost inventory)
- IntradayTracker remains consistent
- Daily Ledger totals remain correct

**Implementation**:
- Events are queued and processed in correct order
- State machine handles late ACKs
- Idempotency prevents duplicate processing

### 2. Partial Fills + Replace

**Scenario**: Order partially fills, then replace intent is sent.

**Examples**:
- Order partially fills (e.g., 30%)
- Replace intent is sent
- Remaining 70% might:
  - Fill at old price
  - Be canceled late
  - Be double-reported (duplicate fill)

**Expected Behavior**:
- Partial fills update remaining qty correctly
- Replace logic handles partial fills
- No double counting of fills
- Remaining quantity tracked accurately

**Implementation**:
- `remaining_quantity` tracked in order data
- Fill events include `fill_id` for idempotency
- Replace logic checks partial fill status

### 3. Cancel Rejection

**Scenario**: Cancel intent sent, but broker rejects it.

**Examples**:
- Cancel intent sent
- Broker responds: CANCEL_REJECTED (order already filled / too late)
- System must not:
  - Reopen risk
  - Double count fills
  - Panic-cancel other orders

**Expected Behavior**:
- CANCEL_REJECTED event published
- System accepts rejection gracefully
- No risk recalculation errors
- Other orders unaffected

**Implementation**:
- `cancel_rejection_probability` configurable
- CANCEL_REJECTED event type added
- State machine handles rejection

### 4. Latency Simulation

**Scenario**: Random delays on broker events.

**Examples**:
- Random delays (1–5 seconds) on:
  - Order ACK
  - Cancel ACK
  - Fill events
- Events may arrive batched or delayed

**Expected Behavior**:
- System handles delayed events
- No timeout errors
- State remains consistent
- Risk calculations correct despite delays

**Implementation**:
- Configurable latency range (`latency_min_seconds`, `latency_max_seconds`)
- Events delayed before publishing
- State machine handles late arrivals

### 5. Duplicate Events

**Scenario**: Same event delivered twice.

**Examples**:
- Same fill event ID delivered twice
- Same order status update delivered twice
- Idempotency must protect ledger and state

**Expected Behavior**:
- Duplicate events ignored
- No double counting
- Ledger remains correct
- Position tracking accurate

**Implementation**:
- `fill_id` tracking for fills
- `order_id:status:event_id` tracking for order updates
- Idempotency checks before processing

### 6. Mixed Chaos

**Scenario**: Combine multiple chaos conditions.

**Examples**:
- Partial fills + delayed cancel + duplicate fill
- Out-of-order + latency + duplicate
- Multiple chaos conditions simultaneously

**Expected Behavior**:
- System handles all conditions
- Intraday PnL correct
- Exposure correct
- No phantom positions
- System converges to stable state

**Implementation**:
- All chaos modes can be enabled simultaneously
- Statistics track each chaos type
- Final state verification

## System Invariants (MUST HOLD)

### 1. No Negative Position Drift

**Invariant**: System must never create ghost inventory.

**Verification**:
```python
position = intraday_tracker.get_intraday_position(account_id, symbol)
assert position["intraday_qty"] >= -max_reasonable_position
```

### 2. IntradayTracker Consistency

**Invariant**: IntradayTracker must remain consistent under all conditions.

**Verification**:
- Long and short quantities tracked separately
- Average prices calculated correctly
- Realized PnL accurate

### 3. Daily Ledger Totals Correct

**Invariant**: Daily Ledger must sum correctly.

**Verification**:
- Total fills match sum of individual fills
- No duplicate counting
- PnL calculations correct

### 4. CAP_RECOVERY / HARD_DERISK Logic Not Retriggered

**Invariant**: Risk logic must not be incorrectly retriggered.

**Verification**:
- No false positives on exposure calculations
- Risk events only triggered on actual changes
- State transitions correct

### 5. LiquidityGuard Does Not Allow New Risk

**Invariant**: LiquidityGuard must not allow new risk due to bad ordering.

**Verification**:
- Order sizes respect limits
- Risk calculations account for pending orders
- No orders slip through that violate limits

### 6. System Converges to Stable State

**Invariant**: System must converge without manual intervention.

**Verification**:
- All events eventually processed
- State consistent after all events
- No hanging orders or stuck states

## Configuration

**File**: Passed to `ChaosExecutionSimulator` constructor

```python
chaos_config = {
    "enabled": True,  # Enable chaos mode
    "out_of_order": True,  # Enable out-of-order events
    "latency": True,  # Enable latency simulation
    "latency_min_seconds": 1.0,
    "latency_max_seconds": 5.0,
    "duplicate": True,  # Enable duplicate events
    "duplicate_probability": 0.1,  # 10% chance
    "partial_fill": True,  # Enable partial fills
    "partial_fill_probability": 0.3,  # 30% chance
    "partial_fill_min_pct": 0.1,  # 10% minimum
    "partial_fill_max_pct": 0.7,  # 70% maximum
    "cancel_rejection": True,  # Enable cancel rejection
    "cancel_rejection_probability": 0.2,  # 20% chance
}
```

## Running Tests

### Run All Tests

```bash
python quant_engine/workers/run_execution_chaos_tests.py
```

### Run Individual Test

```python
from app.event_driven.testing.execution_chaos_tests import ChaosTestRunner

runner = ChaosTestRunner()
runner.test_out_of_order_events()
```

## Test Scenarios

### Test 1: Out-of-Order Events

**Purpose**: Verify system handles events arriving in wrong order.

**Steps**:
1. Create intent
2. Process intent (generates ACCEPTED, WORKING, FILL)
3. Verify events arrive in correct order (or handled correctly if out-of-order)
4. Verify no negative position drift

**Expected Result**: System handles out-of-order events, no position drift.

### Test 2: Partial Fill + Replace

**Purpose**: Verify partial fills handled correctly.

**Steps**:
1. Create intent with partial fill enabled
2. Process intent (should partial fill ~30%)
3. Verify fill events have correct quantities
4. Verify no duplicate fill IDs

**Expected Result**: Partial fills tracked correctly, no duplicates.

### Test 3: Cancel Rejection

**Purpose**: Verify cancel rejection handled gracefully.

**Steps**:
1. Create and fill order
2. Attempt to cancel (should be rejected)
3. Verify CANCEL_REJECTED event published
4. Verify no double counting of fills

**Expected Result**: Cancel rejection handled, no double counting.

### Test 4: Duplicate Events

**Purpose**: Verify idempotency prevents duplicate processing.

**Steps**:
1. Create intent with duplicate enabled
2. Process intent (should generate duplicate fill)
3. Verify duplicate fill ignored
4. Verify position correct (not doubled)

**Expected Result**: Duplicates ignored, position correct.

### Test 5: Mixed Chaos

**Purpose**: Verify system handles multiple chaos conditions.

**Steps**:
1. Create multiple intents with all chaos modes enabled
2. Process all intents
3. Verify:
   - No negative position drift
   - No duplicate counting
   - System converged to stable state

**Expected Result**: All chaos conditions handled, system stable.

### Test 6: Idempotency

**Purpose**: Verify same intent processed only once.

**Steps**:
1. Create intent
2. Process intent twice (same intent_id)
3. Verify only one ACCEPTED event

**Expected Result**: Second processing ignored (idempotency).

## Logging & Diagnostics

### Chaos Statistics

```python
stats = simulator.get_chaos_stats()
# Returns:
# {
#     "out_of_order_events": 0,
#     "duplicate_events_ignored": 5,
#     "late_cancel_acks": 2,
#     "cancel_rejections": 1,
#     "partial_fills": 3,
#     "delayed_events": 10,
# }
```

### Structured Logs

**Duplicate Event Ignored**:
```
🔄 [chaos_execution_service] Duplicate fill ignored: fill_id=FILL_ORD_123_0_1234567890
```

**Cancel Rejection**:
```
❌ [chaos_execution_service] Cancel REJECTED: order_id=ORD_123, reason='Order already filled or too late'
```

**Late ACK**:
```
⏱️ [chaos_execution_service] Latency applied: CANCEL delayed by 2.34s
```

## Implementation Details

### Idempotency Keys

**Fill Events**:
- Key: `fill_id` (format: `FILL_{order_id}_{sequence}_{timestamp}`)
- Stored in: `processed_fill_ids` set
- Checked before processing fill

**Order Status Updates**:
- Key: `{order_id}:{status}:{event_id}`
- Stored in: `processed_order_ids` set
- Checked before processing status update

### Partial Fill Tracking

**Order Data Structure**:
```python
{
    "order_id": "ORD_123",
    "quantity": 100,
    "filled_quantity": 30,
    "remaining_quantity": 70,
    "status": "PARTIAL_FILL",
    ...
}
```

**Fill Event Metadata**:
```python
{
    "fill_id": "FILL_ORD_123_0_1234567890",
    "remaining_quantity": 70,
}
```

### State Machine

**Order States**:
- `ACCEPTED` → `WORKING` → `PARTIAL_FILL` / `FILLED` / `CANCELED`
- `PARTIAL_FILL` → `FILLED` / `CANCELED`
- Late `CANCELED` after `FILLED` → `CANCEL_REJECTED`

**State Transitions**:
- Handled gracefully even if events arrive out of order
- Late ACKs don't cause errors
- Rejections don't break state machine

## Best Practices

1. **Always Enable Idempotency**: Never disable idempotency checks in production
2. **Monitor Chaos Stats**: Track chaos statistics to identify patterns
3. **Test Regularly**: Run chaos tests as part of CI/CD pipeline
4. **Verify Invariants**: Always verify system invariants after chaos tests
5. **Log Everything**: Structured logs help diagnose issues

## Troubleshooting

### Issue: Negative Position Drift

**Symptoms**: Position becomes negative unexpectedly.

**Causes**:
- Duplicate fills not ignored
- Out-of-order events processed incorrectly
- Partial fills double-counted

**Fix**:
- Verify idempotency checks
- Check fill_id tracking
- Review event ordering logic

### Issue: Duplicate Counting

**Symptoms**: Same fill counted multiple times.

**Causes**:
- Fill ID not generated correctly
- Idempotency check failing
- Event processed multiple times

**Fix**:
- Verify fill_id generation
- Check idempotency set
- Review event processing logic

### Issue: System Not Converging

**Symptoms**: System stuck in unstable state.

**Causes**:
- Pending events not processed
- State machine stuck
- Deadlock in event processing

**Fix**:
- Check event queues
- Review state machine transitions
- Verify cleanup logic

## Files

- `app/event_driven/execution/chaos_simulator.py`: Chaos simulator implementation
- `app/event_driven/testing/execution_chaos_tests.py`: Test scenarios
- `workers/run_execution_chaos_tests.py`: Test runner
- `docs/EXECUTION_CHAOS_TESTING.md`: This documentation

## Next Steps

1. **Real Broker Integration**: Test with real broker (with safeguards)
2. **Performance Testing**: Measure system performance under chaos
3. **Extended Scenarios**: Add more edge cases
4. **Automated Monitoring**: Alert on invariant violations
5. **Historical Analysis**: Track chaos patterns over time



