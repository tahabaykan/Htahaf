# Test Scripts Documentation

## Overview

This document provides test scripts and validation procedures for the execution → position pipeline.

## Full Pipeline Test

### Prerequisites

- Redis running: `docker compose up -d redis`
- IBKR TWS/Gateway running (optional for full test)

### Test Steps

```bash
# Terminal 1: Start Redis
docker compose up -d redis

# Terminal 2: Start Hammer ingest (fake data)
python main.py hammer --symbol AAPL

# Terminal 3: Start Engine
python main.py engine-async

# Terminal 4: Start Order Router (if IBKR available)
python main.py router

# Terminal 5: Monitor Redis streams
redis-cli XREAD STREAMS ticks 0-0 COUNT 10
redis-cli XREAD STREAMS executions 0-0 COUNT 10
```

### Expected Flow

1. **Hammer ingest** publishes ticks to Redis `ticks` stream
2. **Engine** reads ticks, processes through strategy
3. **Strategy** generates signals (if conditions met)
4. **OrderPublisher** publishes orders to `orders` stream
5. **OrderRouter** reads orders, sends to IBKR
6. **IBKR** executes orders, triggers callbacks
7. **OrderRouter** publishes executions to `executions` stream
8. **ExecutionHandler** processes executions
9. **PositionManager** updates positions

### Validation

```bash
# Check ticks stream
redis-cli XLEN ticks

# Check orders stream
redis-cli XLEN orders

# Check executions stream
redis-cli XLEN executions

# Check position manager (via engine logs)
# Look for "Position updated" messages
```

## Execution Injection Test

### Manual Mock Execution

Test execution handler without IBKR:

```python
# test_execution_injection.py
import time
from app.core.event_bus import EventBus
from app.engine.position_manager import PositionManager
from app.engine.execution_handler import ExecutionHandler

# Create position manager and handler
pm = PositionManager()
handler = ExecutionHandler(pm)
handler.start()

# Inject test execution
exec_msg = {
    "symbol": "AAPL",
    "side": "BUY",
    "fill_qty": 10.0,
    "fill_price": 150.25,
    "order_id": 99999,
    "exec_id": "test_123",
    "timestamp": int(time.time() * 1000)
}

EventBus.stream_add("executions", exec_msg)

# Wait for processing
time.sleep(1)

# Check position
position = pm.get_position("AAPL")
print(f"Position: {position}")

# Expected: qty=10.0, avg_price=150.25
```

### Run Test

```bash
python test_execution_injection.py
```

## Position Flip Test

### Test Scenario

Test position flip from long to short:

```python
# test_position_flip.py
from app.engine.position_manager import PositionManager

pm = PositionManager()

# Step 1: Buy 10 @ $150
pm.update_position("AAPL", 10, 150.0)
pos1 = pm.get_position("AAPL")
print(f"After buy: {pos1}")
# Expected: qty=10.0, avg_price=150.0

# Step 2: Sell 15 @ $155 (flip to short)
pm.update_position("AAPL", -15, 155.0)
pos2 = pm.get_position("AAPL")
print(f"After sell: {pos2}")
# Expected: qty=-5.0, avg_price=155.0 (flipped)

# Step 3: Buy 5 @ $160 (close short)
pm.update_position("AAPL", 5, 160.0)
pos3 = pm.get_position("AAPL")
print(f"After buy: {pos3}")
# Expected: qty=0.0 (closed)
```

### Run Test

```bash
python test_position_flip.py
```

## IBKR Sync Test

### Test Steps

```bash
# 1. Ensure IBKR TWS/Gateway is running
# 2. Run sync command
python main.py sync
```

### Expected Output

```
=== Open Positions ===
  AAPL: +10 @ $150.25 (P&L: $2.50)
  MSFT: -5 @ $350.00 (P&L: -$1.25)

=== Open Orders ===
  AAPL BUY 10 (LMT) - Status: Submitted

=== Account Summary ===
  Account: DU123456
    NetLiquidation: 100000.00
    BuyingPower: 200000.00
```

### Validation

1. Positions match IBKR TWS
2. Orders match IBKR TWS
3. Account values are reasonable
4. No errors in logs

## CLI Usage Examples

### Engine Async Mode

```bash
# Start engine with position sync
python main.py engine-async

# Expected output:
# Syncing positions from IBKR...
# Synced position: AAPL = 10 @ 150.25
# 🚀 Trading engine started (async mode)
```

### Order Router

```bash
# Start order router
python main.py router

# Expected output:
# Connecting to IBKR (127.0.0.1:7497, Client ID: 1)
# ✅ Connected to IBKR successfully
# 🚀 Order Router started
```

### IBKR Sync

```bash
# Manual sync
python main.py sync

# Expected output:
# === Open Positions ===
# === Open Orders ===
# === Account Summary ===
```

## Integration Test Script

### Complete Integration Test

```python
# test_integration.py
import time
import asyncio
from app.engine.position_manager import PositionManager
from app.engine.execution_handler import ExecutionHandler
from app.core.event_bus import EventBus

async def test_integration():
    # Setup
    pm = PositionManager()
    handler = ExecutionHandler(pm)
    handler.start()
    
    # Test execution 1: Buy
    exec1 = {
        "symbol": "AAPL",
        "side": "BUY",
        "fill_qty": 10.0,
        "fill_price": 150.0,
        "order_id": 1,
        "exec_id": "exec1",
        "timestamp": int(time.time() * 1000)
    }
    EventBus.stream_add("executions", exec1)
    
    await asyncio.sleep(0.5)
    
    # Test execution 2: Sell (partial)
    exec2 = {
        "symbol": "AAPL",
        "side": "SELL",
        "fill_qty": 3.0,
        "fill_price": 155.0,
        "order_id": 2,
        "exec_id": "exec2",
        "timestamp": int(time.time() * 1000)
    }
    EventBus.stream_add("executions", exec2)
    
    await asyncio.sleep(0.5)
    
    # Check final position
    position = pm.get_position("AAPL")
    print(f"Final position: {position}")
    # Expected: qty=7.0, avg_price=150.0
    
    # Cleanup
    handler.stop()

if __name__ == "__main__":
    asyncio.run(test_integration())
```

## Performance Test

### Load Test

```python
# test_load.py
import time
from app.core.event_bus import EventBus
from app.engine.position_manager import PositionManager
from app.engine.execution_handler import ExecutionHandler

pm = PositionManager()
handler = ExecutionHandler(pm)
handler.start()

# Inject 1000 executions
start = time.time()
for i in range(1000):
    exec_msg = {
        "symbol": "AAPL",
        "side": "BUY" if i % 2 == 0 else "SELL",
        "fill_qty": 1.0,
        "fill_price": 150.0 + (i % 10),
        "order_id": i,
        "exec_id": f"exec_{i}",
        "timestamp": int(time.time() * 1000)
    }
    EventBus.stream_add("executions", exec_msg)

# Wait for processing
time.sleep(5)

elapsed = time.time() - start
print(f"Processed 1000 executions in {elapsed:.2f}s")
print(f"Rate: {1000/elapsed:.2f} executions/s")

handler.stop()
```

## Validation Checklist

### Execution Pipeline

- [ ] Executions published to Redis stream
- [ ] ExecutionHandler processes executions
- [ ] PositionManager updates positions
- [ ] FIFO queue maintained correctly
- [ ] P&L calculated correctly

### Position Manager

- [ ] Average price calculated correctly
- [ ] Position flip handled correctly
- [ ] Partial fills handled correctly
- [ ] Realized P&L calculated correctly
- [ ] Unrealized P&L calculated correctly

### IBKR Sync

- [ ] Positions fetched from IBKR
- [ ] Orders fetched from IBKR
- [ ] Account summary fetched
- [ ] Positions synced to manager
- [ ] Startup sync works

## Troubleshooting Tests

### Test Redis Connection

```python
from app.core.redis_client import redis_client

redis = redis_client.sync
result = redis.ping()
print(f"Redis connected: {result}")
```

### Test IBKR Connection

```python
from app.ibkr.ibkr_client import ibkr_client

if ibkr_client.connect():
    print("IBKR connected")
    positions = ibkr_client.get_positions()
    print(f"Positions: {positions}")
else:
    print("IBKR connection failed")
```

### Test Event Bus

```python
from app.core.event_bus import EventBus

# Test publish
EventBus.publish("test", {"message": "test"})

# Test stream add
msg_id = EventBus.stream_add("test_stream", {"data": "test"})
print(f"Message ID: {msg_id}")

# Test stream read
msg = EventBus.stream_read("test_stream", block=1000)
print(f"Message: {msg}")
```








