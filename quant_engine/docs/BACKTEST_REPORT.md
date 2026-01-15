# Backtest Reporting Module

This module generates all backtest outputs:

- `trade_log.csv` - Detailed trade log
- `equity_curve.csv` - Equity curve over time
- `metrics.json` - Performance metrics (Sharpe, Sortino, Drawdown, PF, Win-rate)

## Usage

### Inside BacktestEngine

```python
from app.backtest.backtest_report import BacktestReport

# Initialize
report = BacktestReport()

# Add equity point on each tick
report.add_equity_point(timestamp, equity)

# Add trade when position closes
report.add_trade(
    symbol=symbol,
    side=side,
    qty=qty,
    entry_price=entry_price,
    exit_price=exit_price,
    pnl=pnl,
    entry_time=entry_ts,
    exit_time=exit_ts,
    duration_s=exit_ts - entry_ts,
)

# Save all reports at end
report.save_all("backtests/run_001/")
```

## Output Files

### trade_log.csv

Columns:
- `symbol` - Stock symbol
- `side` - BUY or SELL
- `qty` - Trade quantity
- `entry_price` - Entry price
- `exit_price` - Exit price
- `pnl` - Profit/Loss
- `entry_time` - Entry timestamp
- `exit_time` - Exit timestamp
- `duration_s` - Trade duration in seconds

### equity_curve.csv

Columns:
- `timestamp` - Timestamp
- `equity` - Equity value at this point

### metrics.json

Contains:
- `equity_metrics`:
  - `CAGR` - Compound Annual Growth Rate
  - `volatility` - Annualized volatility
  - `sharpe` - Sharpe ratio
  - `sortino` - Sortino ratio
  - `max_drawdown` - Maximum drawdown
- `trade_metrics`:
  - `num_trades` - Total number of trades
  - `win_rate` - Win rate (0-1)
  - `avg_win` - Average winning trade
  - `avg_loss` - Average losing trade
  - `profit_factor` - Profit factor
  - `max_win` - Largest winning trade
  - `max_loss` - Largest losing trade
  - `gross_profit` - Total profit
  - `gross_loss` - Total loss
  - `total_pnl` - Net P&L
  - `avg_duration_s` - Average trade duration

## Integration with BacktestEngine

The `BacktestEngine` automatically uses `BacktestReport` to:
1. Track equity curve on each tick
2. Log trades when positions close
3. Generate all reports at the end

## Example Output

```json
{
  "equity_metrics": {
    "CAGR": 0.15,
    "volatility": 0.12,
    "sharpe": 1.25,
    "sortino": 1.85,
    "max_drawdown": -0.08
  },
  "trade_metrics": {
    "num_trades": 150,
    "win_rate": 0.55,
    "avg_win": 250.0,
    "avg_loss": -150.0,
    "profit_factor": 1.83,
    "total_pnl": 15000.0
  }
}
```








