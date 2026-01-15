# Risk Timeline & PM Autopsy

## Overview

Production-grade risk timeline tracking and PM-style daily autopsy reporting system. Tracks intraday risk metrics, regime transitions, intent arbitration decisions, CAP_RECOVERY episodes, and PnL attribution throughout the trading day.

## Components

### 1. RiskTimelineTracker
**Location**: `app/event_driven/reporting/risk_timeline_tracker.py`

Tracks intraday risk snapshots over time:
- Gross exposure (current, potential)
- LT/MM bucket breakdown
- Regime (time-based: OPEN, EARLY, MID, LATE, CLOSE)
- Decision mode (NORMAL, SOFT_DERISK, HARD_DERISK, etc.)
- Timestamps for time-series analysis

**Storage**: Redis Sorted Set (timestamp_ns as score)
**Key Pattern**: `risk:timeline:{date}`

**Usage**:
```python
from app.event_driven.reporting.risk_timeline_tracker import RiskTimelineTracker

tracker = RiskTimelineTracker()
tracker.record_snapshot(exposure_data, session_data, decision_data)
snapshots = tracker.get_timeline(target_date=date.today())
summary = tracker.get_summary_stats(target_date=date.today())
```

### 2. RegimeTransitionLogger
**Location**: `app/event_driven/reporting/regime_transition_logger.py`

Logs regime and decision mode transitions:
- Regime transitions (OPEN → EARLY → MID → LATE → CLOSE)
- Mode transitions (NORMAL → SOFT_DERISK → HARD_DERISK)
- Timestamps and reasons
- Exposure context at transition time

**Storage**: Redis Sorted Set
**Key Pattern**: `risk:transitions:{date}`

**Usage**:
```python
from app.event_driven.reporting.regime_transition_logger import RegimeTransitionLogger

logger = RegimeTransitionLogger()
logger.log_regime_transition("OPEN", "EARLY", "Time-based", exposure_data)
logger.log_mode_transition("NORMAL", "SOFT_DERISK", "Exposure > 120%", exposure_data)
transitions = logger.get_transitions(target_date=date.today())
```

### 3. CapRecoveryTracker
**Location**: `app/event_driven/reporting/cap_recovery_tracker.py`

Tracks CAP_RECOVERY episodes:
- Start/end timestamps
- Duration (seconds)
- Exposure change (before/after)
- Status (active/completed)

**Storage**: Redis Sorted Set + Active episode key
**Key Patterns**: 
- `risk:cap_recovery:episodes:{date}` (all episodes)
- `risk:cap_recovery:active` (currently active episode)

**Usage**:
```python
from app.event_driven.reporting.cap_recovery_tracker import CapRecoveryTracker

tracker = CapRecoveryTracker()
episode_id = tracker.start_episode(gross_exposure_pct=130.5, exposure_data=exposure_data)
tracker.end_episode(gross_exposure_pct=122.0, exposure_data=exposure_data)
episodes = tracker.get_episodes(target_date=date.today())
summary = tracker.get_summary(target_date=date.today())
```

### 4. IntentArbitrationTracker
**Location**: `app/event_driven/reporting/intent_arbitration_tracker.py`

Tracks intent arbitration decisions:
- Input vs output intent counts
- Suppressed intent breakdown
- Intent type distribution
- Classification distribution
- Suppression reasons

**Storage**: Redis Sorted Set
**Key Pattern**: `risk:intent_arbitration:{date}`

**Usage**:
```python
from app.event_driven.reporting.intent_arbitration_tracker import IntentArbitrationTracker

tracker = IntentArbitrationTracker()
tracker.log_arbitration(
    input_intents=input_intents,
    output_intents=output_intents,
    current_gross_exposure_pct=125.0,
    current_mode="SOFT_DERISK",
    suppression_reasons={"AAPL_MM_CHURN": "MM churn suppressed"}
)
summary = tracker.get_summary(target_date=date.today())
```

### 5. PnLAttribution
**Location**: `app/event_driven/reporting/pnl_attribution.py`

Attributes intraday PnL to:
- MM vs LT buckets
- Classifications (LT_LONG_INCREASE, MM_SHORT_DECREASE, etc.)
- Effect (INCREASE vs DECREASE)

**Usage**:
```python
from app.event_driven.reporting.pnl_attribution import PnLAttribution

attribution = PnLAttribution()
pnl_by_bucket = attribution.get_pnl_by_bucket(target_date=date.today())
pnl_by_class = attribution.get_pnl_by_classification(target_date=date.today())
pnl_by_effect = attribution.get_pnl_by_effect(target_date=date.today())
```

### 6. PMAutopsyReport
**Location**: `app/event_driven/reporting/pm_autopsy_report.py`

Generates comprehensive PM-style daily reports combining all tracking data.

**Usage**:
```python
from app.event_driven.reporting.pm_autopsy_report import PMAutopsyReport

report_gen = PMAutopsyReport()
report = report_gen.generate_report(target_date=date.today())
formatted_report = report_gen.generate_formatted_report(target_date=date.today())
print(formatted_report)
```

## Integration

### Decision Engine
- **Mode transitions**: Automatically logged via `RegimeTransitionLogger`
- **CAP_RECOVERY**: Automatically tracked via `CapRecoveryTracker`
  - Starts when gross exposure ≥ 130%
  - Ends when gross exposure < cap_recovery_target (default: 123%)

### IntentArbiter
- **Arbitration decisions**: Automatically logged via `IntentArbitrationTracker`
- Tracks input/output intents, suppression reasons

### Exposure Worker
- **Risk timeline snapshots**: Automatically recorded every 15 seconds
- Includes exposure data, session data, decision data

### Session Worker
- **Regime transitions**: Automatically logged when regime changes
- Tracks OPEN → EARLY → MID → LATE → CLOSE transitions

## Report Example

```
================================================================================
PM AUTopsy REPORT - 2024-01-15
Generated: 2024-01-15T16:30:00
================================================================================

RISK TIMELINE:
  Snapshots: 1440
  Gross Exposure:
    Min: 95.23%
    Max: 128.45%
    Avg: 112.34%

REGIME TRANSITIONS:
  Count: 4
  2024-01-15T09:30:00: CLOSED → OPEN
  2024-01-15T10:00:00: OPEN → EARLY
  2024-01-15T12:00:00: EARLY → MID
  2024-01-15T15:00:00: MID → LATE

MODE TRANSITIONS:
  Count: 3
  2024-01-15T14:30:00: NORMAL → SOFT_DERISK (Exposure > 120%)
  2024-01-15T15:45:00: SOFT_DERISK → HARD_DERISK (Exposure > 125%)
  2024-01-15T16:00:00: HARD_DERISK → NORMAL (Exposure < 120%)

CAP_RECOVERY:
  Episodes: 1
  Total Duration: 180.5s
  Avg Duration: 180.5s
  Total Exposure Reduction: 7.50%
  Avg Exposure Reduction: 7.50%

INTENT ARBITRATION:
  Arbitration Cycles: 45
  Total Input Intents: 120
  Total Output Intents: 85
  Total Suppressed: 35
  Suppression Rate: 29.17%

PNL ATTRIBUTION:
  Total Realized PnL: $1,234.56
  LT PnL: $890.12 (72.1%)
  MM PnL: $344.44 (27.9%)

================================================================================
```

## Data Retention

- **Risk Timeline**: Max 10,000 snapshots per day (oldest removed)
- **Transitions**: Stored indefinitely (can be cleaned up manually)
- **CAP_RECOVERY Episodes**: Stored indefinitely
- **Intent Arbitration**: Stored indefinitely

## API Endpoints (Future)

Future API endpoints for accessing reports:
- `GET /api/reports/pm-autopsy/{date}` - Get PM autopsy report
- `GET /api/reports/risk-timeline/{date}` - Get risk timeline
- `GET /api/reports/cap-recovery/{date}` - Get CAP_RECOVERY summary
- `GET /api/reports/intent-arbitration/{date}` - Get intent arbitration summary

## Testing

All components are designed to be testable:
- Mock Redis client for unit tests
- Deterministic timestamps
- Idempotent operations

## Performance

- **Risk Timeline**: ~1ms per snapshot (Redis Sorted Set)
- **Transitions**: ~0.5ms per transition
- **CAP_RECOVERY**: ~1ms per episode start/end
- **Intent Arbitration**: ~2ms per arbitration cycle
- **Report Generation**: ~50-100ms for full day report

## Next Steps

1. Add API endpoints for report access
2. Add visualization (charts/graphs) for risk timeline
3. Add alerting based on CAP_RECOVERY frequency/duration
4. Add historical analysis (compare across days)
5. Add export to CSV/JSON for external analysis



