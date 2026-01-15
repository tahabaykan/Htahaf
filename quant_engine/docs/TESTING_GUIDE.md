# Testing Guide

## Overview

This guide describes the comprehensive test suite for quant_engine, covering unit tests, integration tests, load tests, and fault tolerance tests.

## Test Structure

```
tests/
├── unit/              # Unit tests (isolated components)
├── integration/       # Integration tests (full pipeline)
├── load/             # Load/stress tests (performance)
├── fault/             # Fault tolerance tests (error handling)
└── utils/            # Test utilities
```

## Running Tests

### Run All Tests

```bash
python tests/test_runner.py --all
```

### Run Specific Test Suite

```bash
# Unit tests only
python tests/test_runner.py --unit

# Integration tests only
python tests/test_runner.py --integration

# Load tests only
python tests/test_runner.py --load

# Fault tolerance tests only
python tests/test_runner.py --fault
```

### Using pytest Directly

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/integration/test_pipeline_full.py -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

## Test Suites

### 1. Unit Tests

**Location:** `tests/unit/`

**Purpose:** Test individual components in isolation.

**Tests:**
- `test_fifo_position_manager.py` - FIFO position logic
- `test_risk_limits_parsing.py` - Risk limits configuration

**Example:**
```python
def test_buy_sell_flip(position_manager):
    # Buy 10 @ 100
    exec1 = create_execution("AAPL", "BUY", 10.0, 100.0)
    position_manager.apply_execution(exec1)
    
    # Sell 15 @ 110 (flip to short)
    exec2 = create_execution("AAPL", "SELL", 15.0, 110.0)
    position_manager.apply_execution(exec2)
    
    # Verify position flipped
    pos = position_manager.get_position("AAPL")
    assert pos['qty'] == -5.0
```

### 2. Integration Tests

**Location:** `tests/integration/`

**Purpose:** Test full pipeline end-to-end.

**Tests:**
- `test_pipeline_full.py` - Full pipeline (500 ticks, 10 BUY + 10 SELL)
- `test_risk_blocks.py` - 10 risk blocking scenarios
- `test_strategy_order_flow.py` - Strategy → Order flow

**Example:**
```python
def test_pipeline_500_ticks(setup):
    # Generate 500 ticks
    ticks = create_ticks("AAPL", count=500)
    
    # Process through strategy
    signals = []
    for tick in ticks:
        signal = strategy.on_tick(tick)
        if signal:
            signals.append(signal)
    
    # Verify
    assert len(signals) > 0
```

### 3. Load Tests

**Location:** `tests/load/`

**Purpose:** Test system performance under high load.

**Tests:**
- `load_ticks_stress_test.py` - 100,000 ticks, measure throughput
- `load_order_pipeline_stress_test.py` - 10,000 signals → orders → executions

**Performance Thresholds:**
- Tick processing: >= 5,000 ticks/sec
- Order publishing: >= 1,000 orders/sec
- Execution processing: >= 1,000 execs/sec

**Example:**
```bash
python tests/load/load_ticks_stress_test.py
```

**Expected Output:**
```
🚀 Starting stress test: 100,000 ticks
Processing ticks...
  Processed 10,000 ticks (5234 ticks/sec)
  ...
Throughput: 5,234 ticks/sec
✅ PASS: Throughput >= 5,000 ticks/sec
```

### 4. Fault Tolerance Tests

**Location:** `tests/fault/`

**Purpose:** Test system behavior under failure conditions.

**Tests:**
- `fault_ibkr_disconnect.py` - IBKR disconnect handling
- `fault_hammer_feed_drop.py` - Feed drop handling

**Example:**
```python
def test_disconnect_during_active_executions():
    # Simulate disconnect
    router.connected = False
    
    # Verify retry logic
    assert retry_count > 0
    assert backoff_exponential
```

## E2E Pipeline Test

### Full Pipeline Flow

```
HAMMER → ENGINE → STRATEGY → RISK → ORDER → IBKR → EXECUTION → POSITION
```

### Test Scenario

1. **Generate 500 ticks** for AAPL
2. **Process through strategy** (SMA crossover)
3. **Risk checks** on each signal
4. **Publish orders** to Redis stream
5. **Simulate executions** (10 BUY + 10 SELL)
6. **Update positions** via execution handler
7. **Verify P&L** calculations

### Expected Results

- ✅ Signals generated
- ✅ Orders published
- ✅ Executions processed
- ✅ Positions updated correctly
- ✅ P&L calculated accurately
- ✅ Risk state updated
- ✅ No deadlocks/stalls

## Risk Blocking Tests

### 10 Risk Scenarios

1. **Max position exceeded** - Block order exceeding position limit
2. **Total exposure exceeded** - Block order exceeding exposure %
3. **Daily loss exceeded** - Lock system when daily loss limit reached
4. **Per-trade loss exceeded** - Block order with estimated large loss
5. **Max trades per minute** - Block when frequency limit exceeded
6. **Circuit breaker volatility** - Lock on high volatility
7. **Drawdown limit** - Lock when drawdown exceeds limit
8. **Consecutive loss cooldown** - Enter cooldown after N losses
9. **Locked state persists** - Block all orders when locked
10. **Manual unlock** - Allow orders after manual unlock

## Performance Expectations

### Tick Processing

- **Throughput:** >= 5,000 ticks/sec
- **Latency:** < 1ms per tick
- **Memory:** < 100MB for 100K ticks

### Order Pipeline

- **Order publishing:** >= 1,000 orders/sec
- **Execution processing:** >= 1,000 execs/sec
- **End-to-end latency:** < 10ms

### Indicator Calculation

- **SMA(20):** < 0.1ms
- **EMA(12):** < 0.1ms
- **RSI(14):** < 0.2ms

## Troubleshooting

### Tests Failing

1. **Check Redis connection:**
   ```bash
   redis-cli ping
   ```

2. **Check dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run with verbose output:**
   ```bash
   pytest tests/ -v -s
   ```

### Performance Issues

1. **Check system resources:**
   ```bash
   # CPU
   top
   
   # Memory
   free -h
   ```

2. **Run load tests individually:**
   ```bash
   python tests/load/load_ticks_stress_test.py
   ```

### Integration Test Failures

1. **Clear Redis streams:**
   ```bash
   redis-cli FLUSHDB
   ```

2. **Check IBKR connection** (if using real IBKR):
   - TWS/Gateway running
   - Correct port (7497 paper, 7496 live)
   - API enabled

## Test Utilities

### FakeExecutionFactory

Factory for creating test data:

```python
from tests.utils.fake_execution_factory import FakeExecutionFactory

# Create tick
tick = FakeExecutionFactory.create_tick("AAPL", price=150.0)

# Create execution
exec = FakeExecutionFactory.create_execution("AAPL", "BUY", 10.0, 150.0)

# Create multiple ticks
ticks = FakeExecutionFactory.create_ticks("AAPL", count=100)
```

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt
      - run: python tests/test_runner.py --all
```

## Best Practices

1. **Isolate tests** - Each test should be independent
2. **Use fixtures** - Reuse setup code
3. **Mock external services** - Don't depend on IBKR/Redis in unit tests
4. **Clean up** - Clear Redis streams between tests
5. **Measure performance** - Track metrics in load tests
6. **Test edge cases** - Cover error conditions

## Related Documentation

- [Execution Pipeline](./EXECUTION_PIPELINE.md)
- [Position Manager](./POSITION_MANAGER.md)
- [Risk Manager](./RISK_MANAGER.md)
- [Strategy Engine](./STRATEGY_ENGINE.md)








