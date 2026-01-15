# LT Band Drift Controller & Daily Ledger Features

## Summary

Two new features have been added to the event-driven trading system:

1. **LT Band Drift Controller**: Monitors and corrects LT long/short band violations
2. **Daily Ledger/Reporting**: Aggregates fills and generates end-of-day reports

## 1. LT Band Drift Controller

### Overview

Monitors LT long/short gross band ranges and generates gentle corrective intents when bands drift outside configured ranges.

### Configuration

In `app/config/risk_rules.yaml`:

```yaml
buckets:
  LT:
    band_drift:
      long_pct_range: [60.0, 70.0]  # LT long should be 60-70% of LT bucket
      short_pct_range: [30.0, 40.0]  # LT short should be 30-40% of LT bucket
      tolerance_days: 2  # Band can be violated for up to 2 days
      corrective_intent_size_pct: 0.02  # 2% of position for gentle correction
      use_limit_orders: true  # Use limit orders near truth tick
      prefer_positive_pnl: true  # Prefer actions with positive/acceptable PnL
```

### How It Works

1. **Monitoring**: Decision Engine checks LT bands in NORMAL mode
2. **Detection**: Compares LT long/short % against configured ranges
3. **Correction**: Generates low-priority corrective intents (priority=1)
4. **Gentle**: Small sizes (2%), limit orders, PnL-aware

### Corrective Actions

| Violation | Preferred Classifications |
|-----------|---------------------------|
| LT Short Too High (>40%) | LT_SHORT_DECREASE, LT_LONG_INCREASE |
| LT Short Too Low (<30%) | LT_SHORT_INCREASE, LT_LONG_DECREASE |
| LT Long Too High (>70%) | LT_LONG_DECREASE, LT_SHORT_INCREASE |
| LT Long Too Low (<60%) | LT_LONG_INCREASE, LT_SHORT_DECREASE |

### Features

- **Tolerance**: Bands can be violated for 1-2 days (no aggressive action)
- **Gentle**: 2% of position size, limit orders near truth tick
- **Hard Cap Safe**: Never violates global 130% hard cap
- **Low Priority**: Priority=1 (vs 5-10 for derisk)
- **PnL-Aware**: Prefers positions with positive/acceptable PnL

## 2. Daily Ledger/Reporting

### Overview

Aggregates filled OrderEvents by (date, symbol, classification) and provides end-of-day reports.

### Aggregation

Each fill is recorded with:
- `filled_qty`: Total quantity filled
- `filled_notional`: Total notional value
- `realized_pnl`: Realized profit/loss (calculated when closing positions)
- `count_fills`: Number of fill events
- `net_qty_change`: Net position change

### Report Formats

#### Human-Readable

```
================================================================================
END OF DAY REPORT - 2024-01-15
================================================================================

TOTALS:
  Total Filled Qty: 1,250
  Total Filled Notional: $187,500.00
  Total Realized P&L: $2,340.50
  Total Fill Count: 45
  Total Net Qty Change: 150

BY CLASSIFICATION:
  LT_LONG_DECREASE:
    Filled Qty: 500
    Filled Notional: $75,000.00
    Realized P&L: $1,250.00
    Fill Count: 12
    Net Qty Change: -500
    Symbols: AAPL, MSFT, GOOGL
  ...
```

#### JSON Export

```json
{
  "date": "2024-01-15",
  "by_classification": {
    "LT_LONG_DECREASE": {
      "filled_qty": 500,
      "filled_notional": 75000.00,
      "realized_pnl": 1250.00,
      "count_fills": 12,
      "net_qty_change": -500,
      "symbols": ["AAPL", "MSFT", "GOOGL"]
    },
    ...
  },
  "by_symbol": {
    "AAPL": {
      "filled_qty": 350,
      "filled_notional": 52500.00,
      "realized_pnl": 450.00,
      "count_fills": 15,
      "net_qty_change": -200,
      "classifications": ["LT_LONG_DECREASE", "MM_LONG_INCREASE"]
    },
    ...
  },
  "totals": {
    "total_filled_qty": 1250,
    "total_filled_notional": 187500.00,
    "total_realized_pnl": 2340.50,
    "total_count_fills": 45,
    "total_net_qty_change": 150
  }
}
```

#### CSV Export

```csv
Date,Symbol,Classification,Filled_Qty,Filled_Notional,Realized_PnL,Count_Fills,Net_Qty_Change
2024-01-15,AAPL,LT_LONG_DECREASE,300,45000.00,300.00,8,-300
2024-01-15,AAPL,MM_LONG_INCREASE,50,7500.00,0.00,7,50
...
```

### Usage

```python
from app.event_driven.reporting.daily_ledger import DailyLedger
from datetime import date

ledger = DailyLedger()

# Human-readable report
report = ledger.generate_end_of_day_report()
print(report)

# Export JSON
ledger.export_json(output_path="eod_report_2024-01-15.json")

# Export CSV
ledger.export_csv(output_path="eod_report_2024-01-15.csv")
```

### Ledger Consumer

The `LedgerConsumer` automatically records fills from order events:

```python
from app.event_driven.reporting.daily_ledger import LedgerConsumer

consumer = LedgerConsumer()
consumer.run()  # Runs in background, consumes ev.orders
```

## Integration

### LT Band Controller

- Integrated into Decision Engine
- Runs in NORMAL mode (after risk checks)
- Operates independently of derisk logic
- Can run concurrently with other intents

### Daily Ledger

- `LedgerConsumer` runs as separate worker
- Consumes `ev.orders` stream
- Records fills automatically
- Reports generated on-demand

## Files

### LT Band Controller
- `app/event_driven/decision_engine/lt_band_controller.py`: Controller logic
- `app/event_driven/decision_engine/engine.py`: Integration
- `app/config/risk_rules.yaml`: Configuration

### Daily Ledger
- `app/event_driven/reporting/daily_ledger.py`: Ledger and reporting
- `app/event_driven/reporting/report_generator.py`: Report generator
- `workers/run_report_generator.py`: Entry point

## Testing

### LT Band Controller

Test by:
1. Setting up exposure with LT long/short outside bands
2. Running Decision Engine
3. Verifying corrective intents are generated (low priority)

### Daily Ledger

Test by:
1. Running Execution Service (generates fills)
2. Running LedgerConsumer (records fills)
3. Generating report: `python workers/run_report_generator.py`

## Next Steps

1. **Real PnL Calculation**: Integrate actual position PnL for `prefer_positive_pnl`
2. **Truth Tick Integration**: Use real truth tick prices for limit orders
3. **Tolerance Tracking**: Track violation duration (1-2 days tolerance)
4. **Report Scheduling**: Auto-generate reports at end of day
5. **Historical Reports**: Generate reports for past dates



