# Sample End-of-Day Report

## Human-Readable Format

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

  LT_LONG_INCREASE:
    Filled Qty: 300
    Filled Notional: $45,000.00
    Realized P&L: $0.00
    Fill Count: 8
    Net Qty Change: 300
    Symbols: TSLA, NVDA

  LT_SHORT_DECREASE:
    Filled Qty: 200
    Filled Notional: $30,000.00
    Realized P&L: $890.50
    Fill Count: 10
    Net Qty Change: 200
    Symbols: SPY, QQQ

  MM_LONG_INCREASE:
    Filled Qty: 150
    Filled Notional: $22,500.00
    Realized P&L: $0.00
    Fill Count: 9
    Net Qty Change: 150
    Symbols: AAPL, MSFT

  MM_SHORT_DECREASE:
    Filled Qty: 100
    Filled Notional: $15,000.00
    Realized P&L: $200.00
    Fill Count: 6
    Net Qty Change: 100
    Symbols: GOOGL

BY SYMBOL:
  AAPL:
    Filled Qty: 350
    Filled Notional: $52,500.00
    Realized P&L: $450.00
    Fill Count: 15
    Net Qty Change: -200
    Classifications: LT_LONG_DECREASE, MM_LONG_INCREASE

  GOOGL:
    Filled Qty: 250
    Filled Notional: $37,500.00
    Realized P&L: $300.00
    Fill Count: 10
    Net Qty Change: -150
    Classifications: LT_LONG_DECREASE, MM_SHORT_DECREASE

  MSFT:
    Filled Qty: 200
    Filled Notional: $30,000.00
    Realized P&L: $500.00
    Fill Count: 8
    Net Qty Change: -100
    Classifications: LT_LONG_DECREASE, MM_LONG_INCREASE

  NVDA:
    Filled Qty: 150
    Filled Notional: $22,500.00
    Realized P&L: $0.00
    Fill Count: 5
    Net Qty Change: 150
    Classifications: LT_LONG_INCREASE

  QQQ:
    Filled Qty: 100
    Filled Notional: $15,000.00
    Realized P&L: $390.50
    Fill Count: 4
    Net Qty Change: 100
    Classifications: LT_SHORT_DECREASE

  SPY:
    Filled Qty: 100
    Filled Notional: $15,000.00
    Realized P&L: $500.00
    Fill Count: 3
    Net Qty Change: 100
    Classifications: LT_SHORT_DECREASE

  TSLA:
    Filled Qty: 100
    Filled Notional: $15,000.00
    Realized P&L: $0.00
    Fill Count: 3
    Net Qty Change: 100
    Classifications: LT_LONG_INCREASE

================================================================================
```

## JSON Format

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
      "symbols": ["AAPL", "GOOGL", "MSFT"]
    },
    "LT_LONG_INCREASE": {
      "filled_qty": 300,
      "filled_notional": 45000.00,
      "realized_pnl": 0.00,
      "count_fills": 8,
      "net_qty_change": 300,
      "symbols": ["NVDA", "TSLA"]
    },
    "LT_SHORT_DECREASE": {
      "filled_qty": 200,
      "filled_notional": 30000.00,
      "realized_pnl": 890.50,
      "count_fills": 10,
      "net_qty_change": 200,
      "symbols": ["QQQ", "SPY"]
    },
    "MM_LONG_INCREASE": {
      "filled_qty": 150,
      "filled_notional": 22500.00,
      "realized_pnl": 0.00,
      "count_fills": 9,
      "net_qty_change": 150,
      "symbols": ["AAPL", "MSFT"]
    },
    "MM_SHORT_DECREASE": {
      "filled_qty": 100,
      "filled_notional": 15000.00,
      "realized_pnl": 200.00,
      "count_fills": 6,
      "net_qty_change": 100,
      "symbols": ["GOOGL"]
    }
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
    "GOOGL": {
      "filled_qty": 250,
      "filled_notional": 37500.00,
      "realized_pnl": 300.00,
      "count_fills": 10,
      "net_qty_change": -150,
      "classifications": ["LT_LONG_DECREASE", "MM_SHORT_DECREASE"]
    },
    "MSFT": {
      "filled_qty": 200,
      "filled_notional": 30000.00,
      "realized_pnl": 500.00,
      "count_fills": 8,
      "net_qty_change": -100,
      "classifications": ["LT_LONG_DECREASE", "MM_LONG_INCREASE"]
    },
    "NVDA": {
      "filled_qty": 150,
      "filled_notional": 22500.00,
      "realized_pnl": 0.00,
      "count_fills": 5,
      "net_qty_change": 150,
      "classifications": ["LT_LONG_INCREASE"]
    },
    "QQQ": {
      "filled_qty": 100,
      "filled_notional": 15000.00,
      "realized_pnl": 390.50,
      "count_fills": 4,
      "net_qty_change": 100,
      "classifications": ["LT_SHORT_DECREASE"]
    },
    "SPY": {
      "filled_qty": 100,
      "filled_notional": 15000.00,
      "realized_pnl": 500.00,
      "count_fills": 3,
      "net_qty_change": 100,
      "classifications": ["LT_SHORT_DECREASE"]
    },
    "TSLA": {
      "filled_qty": 100,
      "filled_notional": 15000.00,
      "realized_pnl": 0.00,
      "count_fills": 3,
      "net_qty_change": 100,
      "classifications": ["LT_LONG_INCREASE"]
    }
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

## CSV Format

```csv
Date,Symbol,Classification,Filled_Qty,Filled_Notional,Realized_PnL,Count_Fills,Net_Qty_Change
2024-01-15,AAPL,LT_LONG_DECREASE,300,45000.00,300.00,8,-300
2024-01-15,AAPL,MM_LONG_INCREASE,50,7500.00,0.00,7,50
2024-01-15,GOOGL,LT_LONG_DECREASE,200,30000.00,200.00,7,-200
2024-01-15,GOOGL,MM_SHORT_DECREASE,50,7500.00,100.00,3,50
2024-01-15,MSFT,LT_LONG_DECREASE,150,22500.00,400.00,6,-150
2024-01-15,MSFT,MM_LONG_INCREASE,50,7500.00,100.00,2,50
2024-01-15,NVDA,LT_LONG_INCREASE,150,22500.00,0.00,5,150
2024-01-15,QQQ,LT_SHORT_DECREASE,100,15000.00,390.50,4,100
2024-01-15,SPY,LT_SHORT_DECREASE,100,15000.00,500.00,3,100
2024-01-15,TSLA,LT_LONG_INCREASE,100,15000.00,0.00,3,100
```

## Usage

### Generate Report

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

### Run Report Generator

```bash
python workers/run_report_generator.py
```

## Notes

- **Filled Qty**: Total quantity filled (sum of all fills)
- **Filled Notional**: Total notional value of fills
- **Realized P&L**: Realized profit/loss from closing positions
- **Count Fills**: Number of fill events
- **Net Qty Change**: Net position change (positive = increased, negative = decreased)

Realized P&L is calculated when closing positions:
- Closing long: (sell_price - avg_buy_price) × qty_sold
- Closing short: (avg_sell_price - buy_price) × qty_bought



