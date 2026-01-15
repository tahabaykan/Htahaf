# BefDay Snapshot & Dual-Ledger System

## Overview

The BefDay (Before Day) Snapshot system separates overnight baseline positions from intraday trading decisions. This enables accurate intraday P&L calculation based only on today's fills, using prev_close as the baseline cost reference.

## Accounts

Three accounts are supported:
- **HAMMER**: `befham.csv`
- **IBKR_GUN**: `befibgun.csv`
- **IBKR_PED**: `befibped.csv`

## BefDay Snapshot

### Purpose

Captures baseline positions at market open for each account, providing:
- `befday_qty`: Position quantity at market open
- `befday_cost`: Baseline cost (prev_close price)
- Reference point for intraday P&L calculation

### How It Works

1. **Trigger**: On first activation of an account each market-open day
2. **Fetch**: Current positions from broker (mocked for now)
3. **Store**: For each symbol:
   - `befday_qty`: Current quantity
   - `befday_cost`: Previous close price (or provided baseline price)
4. **Persist**:
   - **CSV**: `data/befham.csv`, `data/befibgun.csv`, `data/befibped.csv`
   - **Redis**: `befday:YYYY-MM-DD:<account_id>`

### Idempotency

- Snapshot runs only once per day per account
- If snapshot exists, subsequent calls are skipped
- Use `--force` flag to recreate

### CSV Format

```csv
date,symbol,befday_qty,befday_cost,prev_close,notional
2024-01-15,AAPL,100,150.0,150.0,15000.0
2024-01-15,MSFT,-50,300.0,300.0,15000.0
```

### Usage

```bash
# Create snapshot for HAMMER account
python workers/run_befday_snapshot.py HAMMER

# Create snapshot for IBKR_GUN account
python workers/run_befday_snapshot.py IBKR_GUN

# Force recreate (even if exists)
python workers/run_befday_snapshot.py HAMMER --force
```

## Position State

### Updated Fields

Position events and state now include:

- `befday_qty`: Baseline quantity at market open
- `befday_cost`: Baseline cost (prev_close)
- `intraday_qty_delta`: Change since open (current_qty - befday_qty)
- `intraday_avg_fill_price`: Average fill price for today's fills only
- `account_id`: Account identifier

### Exposure Calculations

- **Current Exposure**: Uses current positions (includes intraday changes)
- **Baseline Exposure**: Uses befday_qty × befday_cost
- **Intraday Exposure**: Uses intraday_qty_delta × intraday_avg_fill_price

## Dual-Ledger Reporting

### Ledger A: Overnight Baseline

Shows positions carried from previous day:
- Symbol, befday_qty, befday_cost, notional
- Total baseline notional (long + short)
- Per-symbol baseline positions

### Ledger B: Intraday Fills

Shows today's trading activity:
- Fills aggregated by (date, symbol, classification)
- `filled_qty`, `filled_notional`, `realized_pnl`, `count_fills`
- Realized P&L calculated using befday_cost as baseline

### Combined Report

End-of-day report showing:
1. **Baseline Carry**: Overnight positions (Ledger A)
2. **Intraday Performance**: Today's trading (Ledger B)
3. **Net End Position**: Baseline + intraday changes

### Realized P&L Calculation

Intraday realized P&L is calculated as:

- **Closing Long**: `(fill_price - befday_cost) × qty_closed`
- **Closing Short**: `(befday_cost - fill_price) × qty_closed`

Only fills that close baseline positions contribute to realized P&L. Intraday-only positions (opened and closed today) use their own avg_fill_price.

## Usage Examples

### Create BefDay Snapshot

```python
from app.event_driven.baseline.befday_snapshot import BefDaySnapshot

snapshot = BefDaySnapshot()
snapshot_data = snapshot.create_snapshot("HAMMER")
```

### Generate Dual-Ledger Report

```python
from app.event_driven.reporting.dual_ledger import DualLedgerReport

dual_ledger = DualLedgerReport(account_id="HAMMER")
report = dual_ledger.generate_combined_report()
print(report)

# Export JSON
dual_ledger.export_combined_json(output_path="eod_combined_2024-01-15.json")
```

### Command Line

```bash
# Create snapshot
python workers/run_befday_snapshot.py HAMMER

# Generate dual-ledger report
python workers/run_report_generator.py --dual HAMMER
```

## Sample Combined Report

```
================================================================================
DUAL-LEDGER END OF DAY REPORT - 2024-01-15
Account: HAMMER
================================================================================

LEDGER A: OVERNIGHT BASELINE (BefDay Snapshot)
--------------------------------------------------------------------------------
Snapshot Date: 2024-01-15
Total Symbols: 2
Total Baseline Notional: $30,000.00
  Long: $15,000.00
  Short: $15,000.00

  AAPL: qty=100, cost=$150.00, notional=$15,000.00
  MSFT: qty=-50, cost=$300.00, notional=$15,000.00

LEDGER B: INTRADAY FILLS (Today's Trading)
--------------------------------------------------------------------------------
Total Filled Qty: 50
Total Filled Notional: $7,500.00
Total Realized P&L: $250.00
Total Fill Count: 2
Total Net Qty Change: -50

  LT_LONG_DECREASE: qty=50, notional=$7,500.00, PnL=$250.00, fills=2

COMBINED: BASELINE CARRY + INTRADAY PERFORMANCE
--------------------------------------------------------------------------------
Baseline Carry (Overnight): $30,000.00
Intraday Trading Notional: $7,500.00
Intraday Realized P&L: $250.00
Estimated End Position Notional: $22,500.00

NET POSITIONS BY SYMBOL:
  AAPL: baseline=100 @ $150.00, intraday_delta=-50, end_qty=50, intraday_PnL=$250.00
  MSFT: baseline=-50 @ $300.00, intraday_delta=0, end_qty=-50, intraday_PnL=$0.00

================================================================================
```

## Files

### Core Implementation
- `app/event_driven/baseline/befday_snapshot.py`: Snapshot system
- `app/event_driven/reporting/dual_ledger.py`: Dual-ledger reporting
- `workers/run_befday_snapshot.py`: Snapshot worker

### Data Files
- `data/befham.csv`: HAMMER account snapshots
- `data/befibgun.csv`: IBKR_GUN account snapshots
- `data/befibped.csv`: IBKR_PED account snapshots

### Redis Keys
- `befday:YYYY-MM-DD:HAMMER`: Snapshot data
- `befday:YYYY-MM-DD:IBKR_GUN`: Snapshot data
- `befday:YYYY-MM-DD:IBKR_PED`: Snapshot data

## Integration

### Exposure Worker

The Exposure Worker automatically enriches positions with BefDay data:
- Loads BefDay snapshot for current date
- Adds `befday_qty`, `befday_cost`, `intraday_qty_delta` to positions
- Publishes enriched positions in ExposureEvent

### Daily Ledger

The Daily Ledger uses BefDay data for P&L calculation:
- Retrieves `befday_cost` for each symbol
- Calculates realized P&L using baseline cost
- Separates baseline carry from intraday performance

## Next Steps

1. **Real Broker Integration**: Replace mock `fetch_positions()` with actual broker API
2. **Market Data Integration**: Fetch real prev_close prices
3. **Multi-Account Aggregation**: Combine reports across all accounts
4. **Historical Analysis**: Compare baseline vs end-of-day across multiple days
5. **Unrealized P&L**: Calculate mark-to-market P&L on baseline positions



