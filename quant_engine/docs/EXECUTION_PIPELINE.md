# Execution Pipeline Documentation

## Overview

The execution pipeline handles the complete flow from IBKR order execution to position updates in the trading engine. This document describes the architecture, data flow, message formats, and usage.

## Architecture

```
┌─────────────┐
│   IBKR      │
│  Execution  │
└──────┬──────┘
       │
       │ execution callback
       ▼
┌─────────────────┐
│  Order Router   │
│  _on_execution()│
└──────┬──────────┘
       │
       │ normalized message
       ▼
┌─────────────────┐
│  Redis Stream   │
│  "executions"   │
└──────┬──────────┘
       │
       │ stream_read()
       ▼
┌──────────────────┐
│Execution Handler │
│   _process()     │
└──────┬───────────┘
       │
       │ update_position()
       ▼
┌──────────────────┐
│ Position Manager │
│  Position State  │
└──────────────────┘
```

## Data Flow

### 1. IBKR Execution

When IBKR executes an order, the `_on_execution()` callback is triggered:

```python
# order_router.py
def _on_execution(self, trade, fill):
    exec_msg = {
        "symbol": "AAPL",
        "side": "BUY",
        "fill_qty": 10.0,
        "fill_price": 150.25,
        "order_id": 12345,
        "exec_id": "abc123",
        "timestamp": 1700000000000
    }
    
    EventBus.stream_add("executions", exec_msg)
```

### 2. Redis Stream

Execution messages are stored in Redis stream `executions` for durability:

```bash
# Check stream length
redis-cli XLEN executions

# Read from stream
redis-cli XREAD STREAMS executions 0-0
```

### 3. Execution Handler

ExecutionHandler reads from stream and processes:

```python
# execution_handler.py
def _process_execution(self, exec_data):
    symbol = exec_data["symbol"]
    qty = exec_data["fill_qty"]
    price = exec_data["fill_price"]
    side = exec_data["side"]
    
    # Convert to position quantity
    quantity = qty if side == "BUY" else -qty
    
    # Update position
    position_manager.update_position(symbol, quantity, price)
```

### 4. Position Update

PositionManager updates position state:

```python
# position_manager.py
def update_position(self, symbol, quantity, price):
    # Calculate new average price
    # Update FIFO queue
    # Calculate realized P&L
    # Update position data
```

## Message Format

### Normalized Execution Message

```json
{
    "symbol": "AAPL",
    "side": "BUY",
    "fill_qty": 10.0,
    "fill_price": 150.25,
    "order_id": 12345,
    "exec_id": "abc123",
    "timestamp": 1700000000000,
    "remaining": 0.0,
    "avg_fill_price": 150.25
}
```

### Field Descriptions

- `symbol`: Stock symbol (string)
- `side`: "BUY" or "SELL" (string)
- `fill_qty`: Execution quantity (float)
- `fill_price`: Execution price (float)
- `order_id`: IBKR order ID (int)
- `exec_id`: IBKR execution ID (string)
- `timestamp`: Unix timestamp in milliseconds (int)
- `remaining`: Remaining order quantity (float)
- `avg_fill_price`: Average fill price (float)

## Error Handling

### Execution Processing Errors

ExecutionHandler uses exponential backoff on errors:

```python
# Exponential backoff
time.sleep(min(0.1 * (2 ** min(error_count, 5)), 5.0))
```

### Redis Connection Errors

If Redis is unavailable, ExecutionHandler logs error and retries:

```python
try:
    msg = EventBus.stream_read(...)
except Exception as e:
    logger.error(f"Redis error: {e}")
    time.sleep(backoff_time)
```

### Position Update Errors

PositionManager validates data before updating:

```python
if not symbol or qty <= 0 or price <= 0:
    logger.warning(f"Invalid execution data: {exec_data}")
    return
```

## Usage Examples

### Full Pipeline Test

```bash
# Terminal 1: Redis
docker compose up -d redis

# Terminal 2: Engine
python main.py engine-async

# Terminal 3: Order Router
python main.py router

# Terminal 4: Monitor executions
redis-cli XREAD STREAMS executions 0-0 COUNT 10
```

### Manual Execution Injection

```python
from app.core.event_bus import EventBus

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
```

## Troubleshooting

### Problem: Executions not processed

**Symptoms:**
- ExecutionHandler not receiving messages
- Redis stream growing

**Solutions:**
1. Check ExecutionHandler is running: `ps aux | grep execution_handler`
2. Check Redis stream: `redis-cli XLEN executions`
3. Check logs for errors
4. Verify Redis connection

### Problem: Position not updating

**Symptoms:**
- Executions processed but positions unchanged

**Solutions:**
1. Check PositionManager logs
2. Verify execution message format
3. Check for validation errors
4. Verify position manager is receiving updates

### Problem: High error rate

**Symptoms:**
- Many errors in ExecutionHandler logs

**Solutions:**
1. Check execution message format
2. Verify Redis connection stability
3. Check for malformed messages
4. Review error logs for patterns

## Monitoring

### Execution Statistics

ExecutionHandler logs statistics:

```
Execution handler: Processed 50 executions (errors: 0)
```

### Redis Stream Monitoring

```bash
# Stream length
redis-cli XLEN executions

# Stream info
redis-cli XINFO STREAM executions
```

### Position Updates

PositionManager logs updates:

```
Position updated: AAPL = 10 @ 150.25 (change: +10)
```

## Best Practices

1. **Always use normalized message format** - Ensures compatibility
2. **Handle errors gracefully** - Use exponential backoff
3. **Monitor stream length** - Prevent memory issues
4. **Validate execution data** - Before processing
5. **Log structured data** - For debugging and monitoring

## Related Documentation

- [Position Manager](./POSITION_MANAGER.md) - Position tracking details
- [IBKR Sync](./IBKR_SYNC.md) - IBKR synchronization
- [Order Pipeline](../ORDER_PIPELINE.md) - Order flow








