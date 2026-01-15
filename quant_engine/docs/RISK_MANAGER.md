# Risk Manager Documentation

## Overview

Risk Manager is a critical component that protects the trading system from excessive risk exposure. It enforces limits on position sizes, daily losses, trading frequency, and exposure, and includes circuit breaker functionality.

## Architecture

```
┌─────────────┐
│   Strategy  │
│   Signal    │
└──────┬──────┘
       │
       │ check_before_order()
       ▼
┌─────────────────┐
│  Risk Manager   │
│                 │
│  - RiskLimits   │
│  - RiskState    │
│  - Validation   │
└──────┬──────────┘
       │
       │ allowed/rejected
       ▼
┌─────────────────┐
│  Order Router   │
│  (if allowed)   │
└─────────────────┘
```

## Components

### 1. RiskLimits

Static risk limits configuration:

- Position limits (per symbol, total)
- Loss limits (daily, per trade, drawdown)
- Exposure limits (percentage-based)
- Trading frequency limits
- Circuit breaker thresholds
- Cooldown settings

### 2. RiskState

Dynamic risk state tracking:

- Daily P&L
- Trade counts (minute, hour, day)
- Exposure per symbol
- Circuit breaker state
- Cooldown state
- Price volatility tracking

### 3. RiskManager

Main risk management class:

- Pre-trade validation
- Post-trade state updates
- Circuit breaker management
- Cooldown logic

## Risk Checks

### 1. Position Size Limits

```python
# Check per-symbol position limit
if new_position_size > max_position_per_symbol:
    return False, "Position size exceeds limit"
```

### 2. Daily Loss Limit

```python
# Check daily P&L
if daily_pnl <= -max_daily_loss:
    lock("Daily loss limit reached")
    return False
```

### 3. Exposure Limits

```python
# Check total exposure
exposure_pct = (total_exposure / account_equity) * 100
if exposure_pct > max_exposure_pct:
    return False, "Exposure exceeds limit"
```

### 4. Trading Frequency Limits

```python
# Check trades per minute
if trades_last_minute >= max_trades_per_minute:
    return False, "Trade frequency limit exceeded"
```

### 5. Circuit Breaker

```python
# Check price volatility
volatility = get_recent_volatility(symbol, window=60)
if volatility > circuit_breaker_pct:
    lock("Circuit breaker triggered")
    return False
```

### 6. Cooldown Logic

```python
# Check consecutive losses
if consecutive_losses >= cooldown_after_losses:
    set_cooldown(duration_seconds)
    return False, "In cooldown period"
```

## Usage

### Basic Usage

```python
from app.risk.risk_manager import RiskManager
from app.risk.risk_limits import RiskLimits
from app.risk.risk_state import RiskState

# Create risk manager
limits = RiskLimits(
    max_daily_loss=5000.0,
    max_position_per_symbol=10000.0
)
state = RiskState()
risk_manager = RiskManager(limits=limits, state=state)
risk_manager.set_position_manager(position_manager)

# Check before order
allowed, reason = risk_manager.check_before_order("AAPL", "BUY", 10, 150.0)
if not allowed:
    print(f"Order blocked: {reason}")
```

### With Config File

```python
from app.risk.risk_limits import load_risk_limits

# Load from YAML/JSON
limits = load_risk_limits("config/risk_limits.yaml")
risk_manager = RiskManager(limits=limits)
```

### Strategy Integration

```python
class MyStrategy(StrategyBase):
    def on_market_data(self, symbol, price, tick, position, candle_data, completed_candle):
        # Check risk before generating signal
        if not self.risk_allowed(symbol, "BUY", 10, price):
            return None  # Risk check failed
        
        # Generate signal...
```

## Configuration

### Environment Variables

```bash
RISK_MAX_DAILY_LOSS=5000
RISK_MAX_POSITION_PER_SYMBOL=10000
RISK_MAX_EXPOSURE_PCT=50
RISK_MAX_TRADES_PER_MINUTE=10
RISK_CIRCUIT_BREAKER_PCT=5
```

### Config File (YAML)

```yaml
max_daily_loss: 5000.0
max_position_per_symbol: 10000.0
max_total_position: 100000.0
max_trade_loss: 1000.0
max_exposure_pct: 50.0
max_trades_per_minute: 10
circuit_breaker_pct: 5.0
cooldown_after_losses: 3
cooldown_duration_seconds: 300
```

### Config File (JSON)

```json
{
  "max_daily_loss": 5000.0,
  "max_position_per_symbol": 10000.0,
  "max_exposure_pct": 50.0,
  "max_trades_per_minute": 10
}
```

## Flow Diagram

```
Order Request
    ↓
RiskManager.check_before_order()
    ↓
┌─────────────────────────┐
│ 1. Check if locked      │ → Locked? → REJECT
│ 2. Check cooldown        │ → Cooldown? → REJECT
│ 3. Validate order size   │ → Invalid? → REJECT
│ 4. Check position limit  │ → Exceeded? → REJECT
│ 5. Check exposure limit   │ → Exceeded? → REJECT
│ 6. Check trade frequency │ → Exceeded? → REJECT
│ 7. Check circuit breaker │ → Triggered? → LOCK + REJECT
│ 8. Check daily loss      │ → Exceeded? → LOCK + REJECT
│ 9. Check drawdown        │ → Exceeded? → LOCK + REJECT
└─────────────────────────┘
    ↓
ALL CHECKS PASSED
    ↓
ALLOW ORDER
    ↓
Order Executed
    ↓
RiskManager.update_after_execution()
    ↓
Update RiskState
```

## State Updates

### After Execution

```python
risk_manager.update_after_execution(
    symbol="AAPL",
    side="BUY",
    qty=10.0,
    price=150.0,
    pnl=0.0  # Will be calculated
)
```

Updates:
- Trade count
- Daily P&L
- Exposure
- Trade timestamps
- Consecutive losses

### Auto-Lock Conditions

Risk Manager automatically locks if:
- Daily loss limit reached
- Max drawdown exceeded
- Circuit breaker triggered

## Circuit Breaker

Circuit breaker triggers when price moves exceed threshold in short time:

```python
# Track price changes
risk_state.track_price_change("AAPL", price_change_pct=6.0)

# Check volatility
volatility = risk_state.get_recent_price_volatility("AAPL", window_seconds=60)
if volatility > 5.0:  # 5% move in 60 seconds
    risk_manager.lock("Circuit breaker: high volatility")
```

## Cooldown Logic

After consecutive losses, system enters cooldown:

```python
# After 3 consecutive losses
if consecutive_losses >= 3:
    set_cooldown(300)  # 5 minutes
    # All orders blocked during cooldown
```

## Manual Control

### Lock/Unlock

```python
# Manually lock
risk_manager.lock("Manual lock for maintenance")

# Unlock
risk_manager.unlock()
```

### Reset Daily

```python
# Reset at start of trading day
risk_manager.reset_daily()
```

## Integration Examples

### Engine Integration

```python
# engine_loop.py
risk_manager = RiskManager(limits=risk_limits)
risk_manager.set_position_manager(position_manager)

# Before order
allowed, reason = risk_manager.check_before_order(symbol, side, qty, price)
if not allowed:
    logger.warning(f"Order blocked: {reason}")
    return
```

### Execution Handler Integration

```python
# execution_handler.py
def _process_execution(self, exec_data):
    # Update position
    position_manager.update_position(...)
    
    # Update risk state
    risk_manager.update_after_execution(...)
```

## Monitoring

### Get Risk State

```python
state = risk_manager.get_state()
# Returns:
# {
#     'daily_pnl': -500.0,
#     'trade_count': 25,
#     'trades_last_minute': 2,
#     'total_exposure': 50000.0,
#     'locked': False,
#     'consecutive_losses': 1
# }
```

### Check Status

```python
# Check if locked
if risk_manager.is_locked():
    print(f"Locked: {risk_manager.state.lock_reason}")

# Check cooldown
if risk_manager.state.is_in_cooldown():
    print("In cooldown")
```

## Best Practices

1. **Always check before order** - Never skip risk checks
2. **Update after execution** - Keep state synchronized
3. **Monitor risk state** - Log and alert on limits
4. **Set appropriate limits** - Based on account size and risk tolerance
5. **Test circuit breaker** - Ensure it triggers correctly
6. **Review daily** - Reset and review metrics

## Troubleshooting

### Problem: All orders blocked

**Solutions:**
1. Check if locked: `risk_manager.is_locked()`
2. Check cooldown: `risk_manager.state.is_in_cooldown()`
3. Check daily P&L: `risk_manager.state.daily_pnl`
4. Review risk limits

### Problem: Orders passing but should be blocked

**Solutions:**
1. Verify risk manager is initialized
2. Check limits are set correctly
3. Verify position manager is attached
4. Check logs for risk check results

### Problem: Circuit breaker not triggering

**Solutions:**
1. Verify price change tracking
2. Check circuit breaker threshold
3. Verify time window
4. Test with manual price change

## Related Documentation

- [Execution Pipeline](./EXECUTION_PIPELINE.md) - Execution flow
- [Position Manager](./POSITION_MANAGER.md) - Position tracking
- [Strategy Engine](./STRATEGY_ENGINE.md) - Strategy integration








