# Advanced Hyperparameter Optimization

Advanced hyperparameter optimization using Optuna with Bayesian TPE, parallel execution, and pruning.

## Overview

Traditional grid search is slow and inefficient. Advanced optimization uses:

- **Bayesian TPE (Tree-structured Parzen Estimator)**: Intelligently explores parameter space
- **Parallel Execution**: Uses all CPU cores simultaneously
- **Early Stopping (Pruning)**: Stops unpromising trials early
- **Visualization**: Generates plots to understand parameter relationships

## Key Features

### Bayesian Optimization

TPE algorithm learns from previous trials and focuses on promising regions:

- **Grid Search**: 1000 trials needed
- **TPE**: 80-100 trials often sufficient

### Parallel Execution

- Uses `n_jobs` CPU cores simultaneously
- 8 cores = 8x speedup
- Automatic load balancing

### Pruning

- **MedianPruner**: Stops trials performing worse than median
- Saves computation time
- Configurable warmup period

## Usage

### Command Line

```bash
python main.py optimize \
    --strategy SMAStrategy \
    --symbols AAPL \
    --param-space config/param_space.yaml \
    --trials 100 \
    --jobs 4 \
    --scoring sharpe \
    --start-date 2020-01-01 \
    --end-date 2023-12-31
```

### Parameter Space File (YAML)

```yaml
# config/param_space.yaml
sma_short: [5, 10, 15, 20, 25, 30]
sma_long: [50, 75, 100, 125, 150, 175, 200]
stop_loss: [0.01, 0.02, 0.03, 0.04, 0.05]
take_profit: [0.05, 0.10, 0.15, 0.20]
position_size: [0.1, 0.2, 0.3, 0.4, 0.5]
```

### Programmatic

```python
from app.optimization.advanced_optimizer import AdvancedOptimizer

optimizer = AdvancedOptimizer(
    strategy_cls=MyStrategy,
    param_space={
        'sma_short': list(range(5, 31)),
        'sma_long': list(range(50, 201))
    },
    symbols=['AAPL'],
    start_date='2020-01-01',
    end_date='2023-12-31',
    scoring='sharpe'
)

result = optimizer.optimize(
    num_trials=100,
    n_jobs=4
)

print(f"Best parameters: {result.best_params}")
print(f"Best score: {result.best_value}")
```

## Scoring Metrics

### Available Metrics

- **sharpe**: Sharpe ratio (default)
- **sortino**: Sortino ratio
- **pnl**: Total profit/loss
- **winrate**: Win rate percentage
- **profit_factor**: Gross profit / Gross loss
- **drawdown_adjusted_return**: P&L / Max drawdown

### Custom Scorer

```python
def custom_scorer(metrics):
    sharpe = metrics.get('sharpe', 0)
    pnl = metrics.get('total_pnl', 0) / 1000.0
    return 0.7 * sharpe + 0.3 * pnl

optimizer = AdvancedOptimizer(
    ...,
    custom_scorer=custom_scorer
)
```

## Output Files

### optimization_results/

```
optimization_results/
├── study.db                              # Optuna SQLite database
├── best_params.json                      # Best parameters found
├── optimization_summary.json             # Summary statistics
├── optimization_history.csv             # All trial results
├── optimization_plot_param_importance.png
├── optimization_plot_parallel_coords.png
└── optimization_plot_slice.png
```

### Understanding Plots

#### Parameter Importance

Shows which parameters most affect performance:
- Higher = more important
- Use to focus optimization on key parameters

#### Parallel Coordinate

Shows parameter relationships:
- Each line = one trial
- Color = performance (green = good, red = bad)
- Identify parameter combinations that work well

#### Slice Plot

Shows parameter value vs performance:
- X-axis = parameter value
- Y-axis = score
- Identify optimal ranges for each parameter

## Best Practices

### 1. Parameter Space Design

**Good:**
```yaml
sma_short: [5, 10, 15, 20, 25, 30]  # Reasonable range
sma_long: [50, 100, 150, 200]       # Not too many values
```

**Bad:**
```yaml
sma_short: [1, 2, 3, ..., 100]       # Too many values
sma_long: [50, 51, 52, ..., 200]    # Grid search territory
```

### 2. Number of Trials

- **Small space (< 50 combinations)**: 50-100 trials
- **Medium space (50-500)**: 100-200 trials
- **Large space (> 500)**: 200-500 trials

### 3. Parallel Jobs

- Set `n_jobs` to number of CPU cores
- More jobs = faster, but more memory
- Recommended: 4-8 jobs

### 4. Pruning

- Default: 5 startup trials, 10 warmup steps
- Adjust if trials are too short/long
- Disable for very fast backtests

### 5. Scoring Metric

- **Sharpe**: Best for risk-adjusted returns
- **PNL**: Best for absolute returns
- **Drawdown-adjusted**: Best for risk management

## Integration with Walk-Forward

Optimize parameters for each WFO window:

```python
from app.optimization.walk_forward_engine import WalkForwardEngine
from app.optimization.advanced_optimizer import AdvancedOptimizer

# In WalkForwardEngine, replace ParameterOptimizer with AdvancedOptimizer
optimizer = AdvancedOptimizer(
    strategy_cls=strategy_class,
    param_space=param_space,
    symbols=symbols,
    start_date=train_start,
    end_date=train_end,
    scoring='sharpe'
)

result = optimizer.optimize(num_trials=50, n_jobs=4)
best_params = result.best_params
```

## Performance Tips

1. **Use fewer trials initially**: Test with 20-30 trials first
2. **Reduce date range**: Test on shorter periods first
3. **Limit symbols**: Start with single symbol
4. **Cache data**: Ensure data is pre-loaded
5. **Monitor progress**: Check `study.db` periodically

## Troubleshooting

### Problem: Optimization too slow

**Solutions:**
- Reduce `num_trials`
- Reduce date range
- Use fewer symbols
- Increase `n_jobs` (if CPU available)

### Problem: No improvement

**Solutions:**
- Expand parameter space
- Check if strategy is working at all
- Try different scoring metric
- Increase `num_trials`

### Problem: Memory issues

**Solutions:**
- Reduce `n_jobs`
- Use shorter date ranges
- Clear study database periodically

## Related Documentation

- [Walk-Forward Optimization](./WALK_FORWARD_OPTIMIZATION.md) - WFO process
- [Backtest Report](./BACKTEST_REPORT.md) - Backtest reporting
- [Strategy Engine](./STRATEGY_ENGINE.md) - Strategy framework








