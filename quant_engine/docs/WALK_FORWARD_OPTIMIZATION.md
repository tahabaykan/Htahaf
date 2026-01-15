# Walk-Forward Optimization (WFO)

Walk-Forward Optimization is a robust method for parameter tuning that avoids overfitting by testing parameters on out-of-sample data.

## What is WFO?

Traditional backtesting optimizes parameters on the entire dataset, which can lead to overfitting. WFO divides data into windows:

1. **Training Window**: Used to find optimal parameters
2. **Testing Window**: Used to validate parameters on unseen data

This process repeats for multiple windows, ensuring parameters work across different market conditions.

## Window Generation

### Sliding Windows

Fixed-size training windows that slide forward:

```
Window 1: [Train: Jan-Dec] → [Test: Jan-Mar]
Window 2: [Train: Apr-Mar] → [Test: Apr-Jun]
Window 3: [Train: Jul-Jun] → [Test: Jul-Sep]
```

### Expanding Windows

Training window grows, test window slides:

```
Window 1: [Train: Jan-Dec] → [Test: Jan-Mar]
Window 2: [Train: Jan-Mar] → [Test: Apr-Jun]
Window 3: [Train: Jan-Jun] → [Test: Jul-Sep]
```

## Parameter Search

### Grid Search

Exhaustive search over all parameter combinations:

```python
param_space = {
    'sma_short': [10, 20, 30],
    'sma_long': [50, 100, 200]
}
# Evaluates 3 × 3 = 9 combinations
```

### Random Search

Samples random combinations (faster for large spaces):

```python
# Samples 50 random combinations from large space
```

## Scoring Metrics

- **PNL**: Total profit/loss
- **Sharpe**: Sharpe ratio
- **Sortino**: Sortino ratio
- **Drawdown**: Maximum drawdown (minimized)
- **Win Rate**: Percentage of winning trades
- **Profit Factor**: Gross profit / Gross loss
- **Weighted**: Combination of metrics (default)

## Usage

### Command Line

```bash
python main.py walkforward \
    --strategy SMAStrategy \
    --symbols AAPL,MSFT \
    --start-date 2020-01-01 \
    --end-date 2023-12-31 \
    --training-period 12M \
    --testing-period 3M \
    --wfo-mode sliding \
    --param-space config/param_space.yaml
```

### Parameter Space File (YAML)

```yaml
# config/param_space.yaml
sma_short: [10, 20, 30]
sma_long: [50, 100, 200]
stop_loss: [0.02, 0.03, 0.05]
take_profit: [0.05, 0.10, 0.15]
```

## Output Files

### chosen_parameters.json

Parameters chosen for each window:

```json
[
  {
    "window": 1,
    "params": {
      "sma_short": 20,
      "sma_long": 100
    },
    "test_period": "2021-01-01 to 2021-03-31"
  }
]
```

### window_results.json

Detailed results for each window:

```json
[
  {
    "window": 1,
    "train_start": "2020-01-01",
    "train_end": "2020-12-31",
    "test_start": "2021-01-01",
    "test_end": "2021-03-31",
    "chosen_params": {...},
    "training_score": 1.25,
    "training_metrics": {...},
    "oos_metrics": {...}
  }
]
```

### oos_equity_curve.csv

Out-of-sample equity curve:

```csv
window,pnl,cumulative_pnl,sharpe,max_drawdown
1,1500.0,1500.0,1.25,-0.05
2,-200.0,1300.0,0.95,-0.08
3,800.0,2100.0,1.15,-0.03
```

### walkforward_summary.json

Summary statistics:

```json
{
  "num_windows": 10,
  "total_pnl": 15000.0,
  "avg_pnl_per_window": 1500.0,
  "avg_sharpe": 1.20,
  "consistency": 0.70,
  "profitable_windows": 7
}
```

### walkforward_summary.md

Human-readable summary report.

## Best Practices

1. **Window Size**: 
   - Training: 12-24 months
   - Testing: 3-6 months

2. **Parameter Space**: 
   - Start with coarse grid
   - Refine based on results

3. **Consistency**: 
   - Look for consistent OOS performance
   - Avoid windows with extreme results

4. **Validation**: 
   - Use expanding windows for more data
   - Use sliding windows for recency

## Example

```python
from app.optimization.walk_forward_engine import WalkForwardEngine
from app.optimization.window_generator import WindowMode
from app.optimization.parameter_optimizer import SearchMethod

param_space = {
    'sma_short': [10, 20, 30],
    'sma_long': [50, 100, 200]
}

wfo = WalkForwardEngine(
    strategy_class=MyStrategy,
    param_space=param_space,
    symbols=['AAPL', 'MSFT'],
    start_date='2020-01-01',
    end_date='2023-12-31',
    training_period='12M',
    testing_period='3M',
    mode=WindowMode.SLIDING
)

wfo.run()
```

## Related Documentation

- [Backtest Report](./BACKTEST_REPORT.md) - Backtest reporting
- [Strategy Engine](./STRATEGY_ENGINE.md) - Strategy framework
- [Multi-Asset Backtest](./MULTI_ASSET_BACKTEST.md) - Multi-symbol backtesting








