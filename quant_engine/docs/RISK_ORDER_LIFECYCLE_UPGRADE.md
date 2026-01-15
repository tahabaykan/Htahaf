# Risk & Order Lifecycle Test Rig - Upgrade Summary

## Overview

The Sprint 1 skeleton has been upgraded into a realistic "Risk & Order Lifecycle Test Rig" that focuses on correctness, determinism, and lifecycle robustness before adding any trading/MM strategy.

## What Changed

### 1. Extended Exposure Worker

**Before**: Simple exposure calculation with basic buckets

**After**: Full exposure breakdown including:
- `gross_exposure_pct`: (abs(long) + abs(short)) / equity * 100
- `long_gross_pct`, `short_gross_pct`: Individual percentages
- `buckets`: LT and MM_PURE with:
  - `current`, `current_pct`: Current exposure
  - `potential`, `potential_pct`: Worst-case if all orders fill
  - `target`, `target_pct`: Target exposure
  - `max`, `max_pct`: Maximum allowed
- `group_exposure`: Per-group exposure for 22 groups
- `open_orders_potential`: Potential exposure from open orders

### 2. Policy Decision Table

**Before**: Spaghetti if/else logic in `_evaluate_risk()`

**After**: Clean `PolicyDecisionTable` class with deterministic decision logic:

```python
mode, reason = policy_table.decide(
    regime=regime,
    gross_exposure_pct=gross_exposure_pct,
    potential_exposure_pct=potential_exposure_pct,
    lt_current_pct=lt_current_pct,
    lt_potential_pct=lt_potential_pct,
    mm_current_pct=mm_current_pct,
    mm_potential_pct=mm_potential_pct,
    minutes_to_close=minutes_to_close
)
```

**Modes**:
- `NORMAL`: All limits within tolerance
- `THROTTLE_NEW_ORDERS`: Potential exposure would exceed limits (throttle, don't derisk)
- `SOFT_DERISK`: Reduce exposure using limit orders near truth tick
- `HARD_DERISK`: Aggressive reduction (hit bid/ask)

### 3. Upgraded Execution Service

**Before**: Simple stub that logged actions

**After**: Deterministic lifecycle simulator with:
- **Order Registry in Redis**: Tracks orders by `order_id`, `intent_id`, `symbol`, `side`
- **Idempotency**: Same `intent_id` cannot create duplicate orders
- **Order States**: ACCEPTED → WORKING → (PARTIAL_FILL) → FILLED / CANCELED / REJECTED
- **Deterministic Fills**: Probability-based fill simulation:
  - HARD_DERISK: 100% fill probability
  - SOFT_DERISK: 90% fill probability
  - Other: 50% fill probability
- **CANCEL Support**: `cancel_order(order_id, reason)`
- **REPLACE Support**: Cancel old → ack → new (structure ready)

### 4. Scenario Runner

**New**: Testing harness (`app/event_driven/testing/scenario_runner.py`)

**Features**:
- Inject synthetic events (exposure, session)
- Wait for decision processing
- Assert expected modes and intents
- 5 test scenarios included

**Scenarios**:
1. **A**: OPEN/EARLY with 120% → allow activity, no derisk
2. **B**: 16:16 with 115% → SOFT_DERISK intents
3. **C**: 16:28 with 110% → HARD_DERISK intents
4. **D**: 131% at any time → immediate HARD_DERISK
5. **E**: Current 85% / Potential 135% → THROTTLE (no derisk)

### 5. Updated risk_rules.yaml

**Added**:
- Time-regime tolerance table:
  - OPEN/EARLY: `gross_exposure_tolerance_pct: 125.0`, `allow_derisk: false`
  - MID: `gross_exposure_tolerance_pct: 120.0`, `allow_derisk: true`
  - LATE: `gross_exposure_tolerance_pct: 115.0`, `allow_derisk: true`
  - CLOSE: `gross_exposure_tolerance_pct: 100.0`, `allow_derisk: true`

## Key Design Decisions

### 1. Gross Exposure (Not Net)

```python
gross_exposure_pct = (abs(long_notional) + abs(short_notional)) / equity * 100
```

**Hard Cap**: Never exceed 130% gross exposure.

### 2. Current vs Potential Exposure

- **Current**: Actual positions
- **Potential**: Worst-case if all open orders fill
- **Behavior**: Potential can exceed current; triggers throttling, not forced liquidation

### 3. Bucket Management

- **LT**: Target 80%, max 90% (flex 5-10%)
- **MM_PURE**: Target 20%, max 30%
- **Inventory Rotation**: 10-20% of LT inventory for small MM activity

### 4. Time Regimes

- **OPEN/EARLY**: Wider tolerance (125%), allow aggressive MM, no derisk
- **MID**: Normal tolerance (120%), allow soft derisk
- **LATE**: Tighter tolerance (115%), proactive derisk
- **CLOSE**: Very tight (100%), hard derisk if needed

### 5. De-risk Playbook

- **After 16:15 (LATE)**: SOFT_DERISK using limit orders near truth tick (± $0.01)
- **At 16:28 (2 min to close)**: HARD_DERISK if still > 100%
  - Longs: hit bid
  - Shorts: hit ask
  - Chunked reduction (10% per step)

## Testing

### Run Scenario Runner

```bash
# Terminal 1: Start Decision Engine
python workers/run_decision_engine.py

# Terminal 2: Run scenarios
python workers/run_scenario_runner.py
```

### Expected Output

```
🧪 Running scenario: A: OPEN/EARLY 120% -> allow activity
✅ Scenario PASSED: A: OPEN/EARLY 120% -> allow activity

🧪 Running scenario: B: 16:16 115% -> SOFT_DERISK
✅ Scenario PASSED: B: 16:16 115% -> SOFT_DERISK

...

📊 Test Summary: 5/5 passed
```

## Files Changed

### New Files
- `app/event_driven/decision_engine/policy_table.py`
- `app/event_driven/testing/scenario_runner.py`
- `app/event_driven/testing/__init__.py`
- `workers/run_scenario_runner.py`

### Modified Files
- `app/event_driven/contracts/events.py` - Extended ExposureEvent
- `app/event_driven/workers/exposure_worker.py` - Full breakdown
- `app/event_driven/decision_engine/engine.py` - Uses PolicyDecisionTable
- `app/event_driven/execution/service.py` - Deterministic lifecycle
- `app/config/risk_rules.yaml` - Time-regime tolerance table
- `docs/EVENT_DRIVEN_README.md` - Updated documentation

## Next Steps

1. **Real Broker Integration**: Replace Execution Service stub with IBKR adapter
2. **Open Orders Tracking**: Track real open orders from broker
3. **Fill Handling**: Real fill callbacks → ev.orders events
4. **GRPAN Integration**: Truth tick proximity for SOFT_DERISK
5. **Market Data**: L1/prints/features workers

## Summary

The system is now a robust "Risk & Order Lifecycle Test Rig" that:
- ✅ Correctly calculates gross exposure
- ✅ Distinguishes current vs potential exposure
- ✅ Uses deterministic policy decision table
- ✅ Maintains order lifecycle with idempotency
- ✅ Supports testing via Scenario Runner
- ✅ Focuses on correctness before strategy

Ready for real broker integration and trading strategy development!



