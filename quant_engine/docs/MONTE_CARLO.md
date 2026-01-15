# Monte Carlo Simulation

Monte Carlo simulation for risk analysis and stress testing of trading strategies.

## Overview

Monte Carlo simulation generates thousands of possible future scenarios based on historical returns to assess:

- **Tail Risk**: Worst-case outcomes
- **Value at Risk (VaR)**: Potential losses at confidence levels
- **Conditional VaR (CVaR)**: Expected loss beyond VaR threshold
- **Drawdown Analysis**: Maximum drawdown distributions
- **Recovery Probability**: Likelihood of recovering from losses

## Simulation Models

### 1. Bootstrap (Default)

**Best for**: Realistic market behavior

- Resamples from historical returns
- Preserves actual return distribution
- Captures fat tails and skewness
- Most reliable for risk assessment

### 2. Geometric Brownian Motion (GBM)

**Best for**: Smooth, mathematical modeling

- Assumes normal distribution
- Smooth, continuous paths
- Good for theoretical analysis
- May underestimate tail risk

### 3. Volatility Regime Switching

**Best for**: Stress testing

- Models high/low volatility regimes
- 15% chance of high volatility (2.5x normal)
- Captures tail events
- More conservative risk estimates

## Usage

### Command Line

```bash
python main.py montecarlo \
    --strategy SMAStrategy \
    --symbols AAPL \
    --start-date 2020-01-01 \
    --end-date 2023-01-01 \
    --model bootstrap \
    --horizon 252 \
    --simulations 5000 \
    --mc-jobs 4
```

### Programmatic

```python
from app.risk.monte_carlo import MonteCarloEngine
import pandas as pd

# Get returns from backtest
returns = pd.Series([0.01, -0.02, 0.03, ...])

# Create Monte Carlo engine
mc_engine = MonteCarloEngine(
    returns=returns,
    simulations=10000,
    horizon=252,  # 1 year
    n_jobs=4
)

# Run simulation
result = mc_engine.run(model='bootstrap')

# Access results
print(f"VaR (95%): {result.var_95}")
print(f"CVaR (95%): {result.cvar_95}")
print(f"Worst 1%: {result.worst_1pct}")
```

## Output Metrics

### Return Statistics

- **Mean Return**: Average ending value
- **Median Return**: Median ending value
- **Worst 1%**: 1st percentile (worst case)

### Risk Metrics

- **VaR (95%)**: Value at Risk at 95% confidence
  - 95% of scenarios will have returns >= VaR
  - 5% of scenarios will have returns < VaR

- **CVaR (95%)**: Conditional VaR (Expected Shortfall)
  - Average return of worst 5% scenarios
  - More conservative than VaR

- **Max Drawdown**: Distribution of maximum drawdowns
  - Average max drawdown
  - Worst max drawdown

## Interpretation

### Example Results

```
Mean return:     1.15
Median return:   1.12
VaR (95%):       0.85
CVaR (95%):      0.78
Worst 1%:        0.65
```

**Interpretation:**
- On average, portfolio grows 15% over horizon
- 95% of scenarios: portfolio >= 85% of initial value
- Worst 5% scenarios: average 78% of initial value
- Worst 1% scenario: 65% of initial value

### Risk Assessment

- **VaR < 0.90**: High risk (potential 10%+ loss)
- **VaR 0.90-0.95**: Moderate risk
- **VaR > 0.95**: Low risk

## Best Practices

### 1. Number of Simulations

- **Minimum**: 1,000 simulations
- **Recommended**: 5,000-10,000 simulations
- **High precision**: 50,000+ simulations

### 2. Time Horizon

- **Short-term**: 63 days (1 quarter)
- **Medium-term**: 252 days (1 year) - default
- **Long-term**: 504 days (2 years)

### 3. Model Selection

- **Bootstrap**: Default, most realistic
- **GBM**: For smooth theoretical analysis
- **Regime**: For conservative stress testing

### 4. Parallel Execution

- Use `--mc-jobs -1` for all CPU cores
- More cores = faster simulation
- Memory usage increases with cores

## Integration with Backtest

Monte Carlo automatically runs after backtest:

```python
# Run backtest
result = engine.run(symbols=['AAPL'], ...)

# Extract returns
equity_df = pd.DataFrame(result['equity_curve'])
returns = equity_df['equity'].pct_change()

# Run Monte Carlo
mc_engine = MonteCarloEngine(returns=returns)
mc_result = mc_engine.run()
```

## Use Cases

### 1. Risk Assessment

Assess tail risk before deploying strategy:

```bash
python main.py montecarlo --strategy MyStrategy --simulations 10000
```

### 2. Position Sizing

Determine safe position sizes based on CVaR:

- If CVaR = 0.85, don't risk more than 15% of capital

### 3. Strategy Comparison

Compare risk profiles of different strategies:

```bash
# Strategy A
python main.py montecarlo --strategy StrategyA

# Strategy B
python main.py montecarlo --strategy StrategyB
```

### 4. Stress Testing

Use regime switching model for worst-case scenarios:

```bash
python main.py montecarlo --model regime --simulations 20000
```

## Limitations

1. **Historical Bias**: Assumes future resembles past
2. **Model Assumptions**: GBM assumes normal distribution
3. **Correlation**: Doesn't model cross-asset correlations
4. **Regime Changes**: May miss structural market changes

## Related Documentation

- [Risk Manager](./RISK_MANAGER.md) - Risk management framework
- [Backtest Report](./BACKTEST_REPORT.md) - Backtest reporting
- [Walk-Forward Optimization](./WALK_FORWARD_OPTIMIZATION.md) - WFO process








