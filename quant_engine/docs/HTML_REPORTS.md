# HTML Report Generator

The HTML Report Generator creates professional, hedge-fund quality reports for backtest results, walk-forward optimization, and parameter tuning.

## Features

### Charts

- **Equity Curve**: Portfolio equity over time
- **Drawdown Chart**: Underwater plot showing drawdowns
- **Monthly Returns Heatmap**: Visual representation of monthly performance
- **Trade Distribution**: P&L and holding time distributions

### Tables

- **Performance Summary**: Key metrics at a glance
- **Equity Metrics**: CAGR, Sharpe, Sortino, volatility, drawdown
- **Trade Metrics**: Win rate, profit factor, average win/loss, total P&L

### Files Generated

- `report.html` - Main dashboard
- `equity_curve.png` - Equity curve chart
- `drawdown.png` - Drawdown chart
- `monthly_returns.png` - Monthly returns heatmap
- `trade_distribution.png` - Trade P&L and holding time distributions
- `trade_list.csv` - Complete trade log
- `summary.json` - Summary statistics

## Usage

### Command Line

Generate HTML report after backtest:

```bash
python main.py backtest \
    --strategy SMAStrategy \
    --symbols AAPL,MSFT \
    --start-date 2021-01-01 \
    --end-date 2023-01-01 \
    --report
```

### Programmatic

```python
from app.report.html_reporter import HTMLReportGenerator
from app.backtest.backtest_engine import BacktestEngine

# Run backtest
engine = BacktestEngine(strategy=my_strategy)
result = engine.run(symbols=['AAPL'], start_date='2021-01-01', end_date='2023-01-01')

# Generate report
reporter = HTMLReportGenerator()
reporter.generate(
    backtest_result=result,
    strategy_name='MyStrategy',
    symbols=['AAPL']
)
```

## Report Structure

### Header

- Strategy name
- Symbols tested
- Generation timestamp

### Performance Metrics Cards

- Total P&L
- Sharpe Ratio
- Max Drawdown
- Win Rate

### Charts Section

Four main charts:
1. Equity Curve
2. Drawdown Chart
3. Monthly Returns Heatmap
4. Trade Distribution

### Detailed Metrics Tables

- Equity Metrics: CAGR, volatility, Sharpe, Sortino, max drawdown
- Trade Metrics: Total trades, win rate, avg win/loss, profit factor, total P&L

## Customization

### Template

The HTML template is embedded in `HTMLReportGenerator._get_html_template()`. To customize:

1. Modify the template string in `html_reporter.py`
2. Or create a separate template file and load it:

```python
from jinja2 import FileSystemLoader, Environment

loader = FileSystemLoader('templates')
env = Environment(loader=loader)
template = env.get_template('report_template.html')
```

### Charts

Charts are generated using matplotlib and seaborn. To customize:

1. Modify chart generation methods in `HTMLReportGenerator`
2. Adjust colors, styles, or add new charts

### Styling

The template uses Bootstrap 5. You can:
- Modify CSS in the `<style>` section
- Add custom Bootstrap classes
- Include additional CSS files

## Best Practices

1. **Review Reports Regularly**: Generate reports for all backtests to track strategy evolution

2. **Compare Reports**: Use timestamps to compare different strategy versions

3. **Share Reports**: HTML reports are self-contained and can be shared easily

4. **Archive Reports**: Keep historical reports for analysis

5. **Customize for Your Needs**: Modify templates to include strategy-specific metrics

## Example Output

```
reports/
└── 20240115_143022/
    ├── report.html
    ├── equity_curve.png
    ├── drawdown.png
    ├── monthly_returns.png
    ├── trade_distribution.png
    ├── trade_list.csv
    └── summary.json
```

## PDF Export

To convert HTML to PDF:

```bash
# Using wkhtmltopdf
wkhtmltopdf report.html report.pdf

# Using Chrome headless
chrome --headless --disable-gpu --print-to-pdf=report.pdf report.html
```

## Integration with Walk-Forward Optimization

HTML reports can be generated for each window in walk-forward optimization:

```python
# In WalkForwardEngine
for window_result in window_results:
    reporter = HTMLReportGenerator(output_dir=f"wfo_reports/window_{window_result['window']}")
    reporter.generate(window_result, strategy_name, symbols)
```

## Related Documentation

- [Backtest Report](./BACKTEST_REPORT.md) - CSV/JSON reports
- [Walk-Forward Optimization](./WALK_FORWARD_OPTIMIZATION.md) - WFO process
- [Multi-Asset Backtest](./MULTI_ASSET_BACKTEST.md) - Portfolio backtesting








