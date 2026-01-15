# Multi-Asset / Portfolio Backtesting

This document explains how to run backtests with multiple symbols simultaneously, manage portfolio-level positions, and enforce portfolio-level risk rules.

## Overview

The multi-asset backtesting system allows you to:

- Test strategies across multiple symbols simultaneously
- Manage portfolio-level cash, positions, and P&L
- Enforce portfolio-level risk rules
- Generate portfolio equity curves
- Track exposure and leverage

## Architecture

```
┌─────────────┐
│  Symbol 1   │
│  (AAPL)     │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Symbol 2   │
│  (MSFT)     │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  Event Merger   │
│  (by timestamp) │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│  BacktestEngine │
│  (per symbol)   │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│ PortfolioManager│
│  (cash, equity) │
└─────────────────┘
```

## Components

### 1. PortfolioManager

Manages portfolio-level state:

- **Cash balance**: Starting cash and current cash
- **Per-symbol positions**: Uses PositionManager for each symbol
- **Total equity**: Cash + Sum of position values
- **Exposure**: Per-symbol and total exposure
- **Leverage**: Total exposure / Equity
- **P&L**: Realized and unrealized P&L

### 2. PortfolioRiskManager

Enforces portfolio-level risk rules:

- **Max capital per trade**: Maximum trade value
- **Max exposure per symbol**: Maximum exposure as % of equity
- **Max portfolio leverage**: Maximum leverage ratio
- **Max total exposure**: Maximum total exposure as % of equity

### 3. Multi-Symbol Replay

ReplayEngine merges events from multiple symbols:

- Loads data for all symbols
- Creates timestamp-ordered event queue
- Replays events in chronological order
- Calls strategy with per-symbol context

## Usage

### Single Symbol (Backward Compatible)

```bash
python main.py backtest --symbol AAPL --start-date 2023-01-01 --end-date 2023-12-31
```

### Multiple Symbols

```bash
python main.py backtest --symbols AAPL,MSFT,GOOG --start-date 2023-01-01 --end-date 2023-12-31
```

### With Custom Data Directory

```bash
python main.py backtest --symbols AAPL,MSFT --data-dir /path/to/data
```

## Strategy Integration

Your strategy receives per-symbol market data:

```python
class MyStrategy(StrategyBase):
    def on_market_data(self, symbol, price, tick, position, candle_data, completed_candle):
        # symbol: Current symbol being processed
        # position: Position for this symbol
        # candle_data: Candle data for this symbol
        
        # Strategy logic here
        if symbol == "AAPL":
            # AAPL-specific logic
            pass
        elif symbol == "MSFT":
            # MSFT-specific logic
            pass
        
        return signal
```

## Portfolio Manager API

### Get Portfolio State

```python
# Get total equity
equity = portfolio_manager.get_total_equity()

# Get cash
cash = portfolio_manager.cash

# Get exposure
exposure = portfolio_manager.get_total_exposure()

# Get leverage
leverage = portfolio_manager.get_leverage()

# Get portfolio summary
summary = portfolio_manager.get_portfolio_summary()
```

### Get Position

```python
# Get position for symbol
position = portfolio_manager.get_position("AAPL")

# Get all positions
all_positions = portfolio_manager.get_all_positions()
```

## Portfolio Risk Manager

### Risk Checks

```python
# Check if order is allowed
allowed, reason = portfolio_risk_manager.can_open_position(
    symbol="AAPL",
    qty=10.0,
    price=150.0,
    portfolio=portfolio_manager
)

if not allowed:
    print(f"Order rejected: {reason}")
```

### Risk Limits

Default limits:
- Max capital per trade: $10,000
- Max exposure per symbol: 20% of equity
- Max portfolio leverage: 2.0x
- Max total exposure: 80% of equity

## Output Files

### trade_log.csv

Includes symbol column:
```csv
symbol,side,qty,entry_price,exit_price,pnl,entry_time,exit_time,duration_s
AAPL,BUY,10,150.0,155.0,50.0,1234567890,1234568000,110
MSFT,SELL,5,300.0,295.0,25.0,1234567900,1234568100,200
```

### equity_curve.csv

Portfolio equity (not per-symbol):
```csv
timestamp,equity
1234567890,100000.0
1234567900,100050.0
```

### metrics.json

Portfolio-level metrics:
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
    "profit_factor": 1.83
  }
}
```

## Example: Multi-Asset Strategy

```python
class MultiAssetStrategy(StrategyBase):
    def on_market_data(self, symbol, price, tick, position, candle_data, completed_candle):
        # Get portfolio state
        portfolio = self.position_manager  # Access portfolio manager
        
        # Check if we should trade this symbol
        if symbol == "AAPL":
            sma = self.get_indicator(symbol, 'sma', period=20)
            if price > sma:
                return {'signal': 'BUY', 'symbol': symbol, 'quantity': 10, 'price': price}
        
        elif symbol == "MSFT":
            rsi = self.get_indicator(symbol, 'rsi', period=14)
            if rsi < 30:
                return {'signal': 'BUY', 'symbol': symbol, 'quantity': 5, 'price': price}
        
        return None
```

## Best Practices

1. **Symbol Selection**: Choose symbols with different correlations for diversification
2. **Risk Limits**: Set appropriate limits based on account size
3. **Position Sizing**: Use portfolio risk manager to control position sizes
4. **Data Quality**: Ensure all symbols have data for the same date range
5. **Strategy Logic**: Consider cross-symbol signals and correlations

## Troubleshooting

### Problem: No data for some symbols

**Solution**: Check that all symbol data files exist in data directory

### Problem: Events out of order

**Solution**: ReplayEngine automatically merges by timestamp - ensure timestamps are correct

### Problem: Portfolio risk rejects all orders

**Solution**: Check risk limits - may need to adjust max_capital_per_trade or exposure limits

## Related Documentation

- [Backtest Report](./BACKTEST_REPORT.md) - Report generation
- [Strategy Engine](./STRATEGY_ENGINE.md) - Strategy framework
- [Risk Manager](./RISK_MANAGER.md) - Risk management








