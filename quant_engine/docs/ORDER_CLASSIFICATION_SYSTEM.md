# Order/Intent Classification System

## Overview

Every Intent, Order, and Fill MUST be classified into exactly one of 8 semantic classes. This classification is enforced across the entire system for risk management and reporting.

## Classification Enum

The `OrderClassification` enum defines 8 classes:

1. `MM_LONG_INCREASE` - Market-making, long position increase
2. `MM_LONG_DECREASE` - Market-making, long position decrease
3. `MM_SHORT_INCREASE` - Market-making, short position increase
4. `MM_SHORT_DECREASE` - Market-making, short position decrease
5. `LT_LONG_INCREASE` - Long-term portfolio, long position increase
6. `LT_LONG_DECREASE` - Long-term portfolio, long position decrease
7. `LT_SHORT_INCREASE` - Long-term portfolio, short position increase
8. `LT_SHORT_DECREASE` - Long-term portfolio, short position decrease

### Classification Components

Each classification has three components:
- **Bucket**: `LT` (Long-term portfolio) or `MM` (Market-making)
- **Direction**: `LONG` or `SHORT`
- **Effect**: `INCREASE` or `DECREASE`

### Risk-Increasing Orders

Orders whose classification ends with `_INCREASE` are considered **risk-increasing**:
- `MM_LONG_INCREASE`
- `MM_SHORT_INCREASE`
- `LT_LONG_INCREASE`
- `LT_SHORT_INCREASE`

These orders increase gross exposure when filled.

## Event Contracts

### IntentEvent

All intents MUST include:
- `classification`: OrderClassification enum value
- `bucket`: LT or MM
- `effect`: INCREASE or DECREASE
- `dir`: LONG or SHORT
- `risk_delta_notional`: Estimated worst-case change if filled
- `risk_delta_gross_pct`: Estimated worst-case gross exposure change
- `position_context_at_intent`: Snapshot of position at intent time
  - `current_qty`: Current position quantity
  - `avg_fill_price`: Average fill price
  - `notional`: Position notional

### OrderEvent

All order events preserve classification from intent:
- `classification`: Preserved from intent
- `bucket`, `effect`, `dir`: Preserved from intent
- `risk_delta_notional`, `risk_delta_gross_pct`: Preserved from intent
- `position_context_at_intent`: Preserved from intent
- `intent_id`: Link back to original intent

## Decision Engine

The Decision Engine **always** outputs intents with classification filled:

1. Determines bucket from position metadata (defaults to LT)
2. Determines direction from current position (LONG if qty > 0, SHORT if qty < 0)
3. Sets effect to DECREASE for derisk intents
4. Calculates risk_delta_notional and risk_delta_gross_pct
5. Captures position_context_at_intent snapshot

### Cap Logic

When gross exposure reaches 130%:
1. Decision Engine triggers `HARD_DERISK` mode
2. Execution Service monitors exposure stream
3. Execution Service cancels ALL `*_INCREASE` orders
4. Risk-reducing orders (`*_DECREASE`) continue working

## Execution Service

### Classification Preservation

Execution Service:
1. Extracts classification from intent (MUST be present)
2. Preserves classification in all order events (ACCEPTED, WORKING, FILLED, CANCELED)
3. Maintains order registry with classification metadata
4. Enforces idempotency by `intent_id`

### Cancel Filters

`cancel_risk_increasing_open_orders()`:
- Scans open orders registry
- Identifies orders with status: ACCEPTED, WORKING, PARTIAL_FILL
- Cancels only orders whose classification ends with `_INCREASE`
- Leaves `*_DECREASE` orders working

### Exposure Monitoring

Execution Service monitors `ev.exposure` stream:
- When `gross_exposure_pct >= 130.0`, automatically calls `cancel_risk_increasing_open_orders()`
- This ensures hard cap is never exceeded by open orders

## Daily Ledger

The Daily Ledger aggregates fills by:
- Date
- Symbol
- Classification

### Ledger Entry

Each fill is recorded with:
- `date`: ISO date string
- `symbol`: Symbol
- `classification`: OrderClassification value
- `lots`: Total lots filled
- `notional`: Total notional
- `net_qty_change`: Net position change
- `realized_pnl`: Realized P&L (if available)

### End-of-Day Report

The report provides:
- **Totals**: Total lots, notional, net qty change, realized P&L
- **By Classification**: Aggregated by each of 8 classes
- **By Symbol**: Aggregated by symbol with classifications

## Testing

### Scenario F: Classification and Cancel Logic

Tests:
1. Classification enum properties (bucket, direction, effect, is_risk_increasing)
2. Classification preservation through intent → order → fill
3. Cancel filter logic (only `*_INCREASE` canceled at cap)

## Usage Example

```python
from app.event_driven.contracts.events import OrderClassification

# Create classification
cls = OrderClassification.from_components("LT", "LONG", "DECREASE")
assert cls == OrderClassification.LT_LONG_DECREASE

# Check properties
assert cls.bucket == "LT"
assert cls.direction == "LONG"
assert cls.effect == "DECREASE"
assert cls.is_risk_increasing == False

# Risk-increasing check
cls2 = OrderClassification.MM_SHORT_INCREASE
assert cls2.is_risk_increasing == True
```

## Key Rules

1. **Classification is MANDATORY**: Every intent MUST have classification
2. **No Guessing**: Execution Service preserves classification, never infers it
3. **Hard Cap Enforcement**: At 130%, only `*_INCREASE` orders are canceled
4. **Preservation**: Classification flows through: Intent → Order → Fill
5. **Reporting**: All fills are aggregated by classification for daily reports

## Files

- `app/event_driven/contracts/events.py`: OrderClassification enum, event contracts
- `app/event_driven/decision_engine/engine.py`: Classification assignment
- `app/event_driven/execution/service.py`: Classification preservation, cancel filters
- `app/event_driven/reporting/daily_ledger.py`: Classification-based aggregation
- `app/event_driven/testing/scenario_runner.py`: Classification tests



