# Historical Data Directory

This directory contains historical market data files for backtesting.

## File Formats

### CSV Format

Expected columns:
- `timestamp` or `ts` - Timestamp (ISO format or milliseconds)
- `symbol` - Stock symbol
- `last` or `close` - Last/close price
- `bid` - Bid price (optional)
- `ask` - Ask price (optional)
- `volume` - Volume

Example:
```csv
timestamp,symbol,last,bid,ask,volume
2024-01-01 09:30:00,AAPL,150.0,149.99,150.01,1000
2024-01-01 09:30:01,AAPL,150.1,150.09,150.11,1200
```

### Parquet Format

Same columns as CSV, but in Parquet format for faster loading.

## File Naming

Files should be named: `{SYMBOL}.csv` or `{SYMBOL}.parquet`

Examples:
- `AAPL.csv`
- `MSFT.parquet`
- `SPY.csv`

## Data Sources

You can download historical data from:
- Yahoo Finance
- Alpha Vantage
- IEX Cloud
- Polygon.io
- Your broker's historical data API

## Example: Download from Yahoo Finance

```python
import yfinance as yf
import pandas as pd

# Download data
ticker = yf.Ticker("AAPL")
df = ticker.history(start="2023-01-01", end="2024-01-01")

# Save to CSV
df.to_csv("data/historical/AAPL.csv")
```








