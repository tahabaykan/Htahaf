# Position Manager Documentation

## Overview

PositionManager tracks trading positions, calculates P&L, and manages position state. It uses FIFO (First In, First Out) methodology for average price calculation and realized P&L tracking.

## Architecture

```
┌─────────────────┐
│ Execution       │
│ Message         │
└────────┬────────┘
         │
         │ apply_execution()
         ▼
┌─────────────────┐
│ Position Manager│
│                 │
│  - update_position() │
│  - FIFO queue   │
│  - P&L calc     │
└────────┬────────┘
         │
         │ get_position()
         ▼
┌─────────────────┐
│ Strategy/Engine │
│ Position State  │
└─────────────────┘
```

## Position Data Structure

### Position Object

```python
{
    'qty': 10.0,              # Position quantity (positive = long, negative = short)
    'avg_price': 150.25,      # Average entry price
    'realized_pnl': 0.0,      # Realized P&L
    'unrealized_pnl': 0.0,    # Unrealized P&L
    'last_update_time': 1700000000.0  # Last update timestamp
}
```

## FIFO Price Calculation

### Adding to Position

When adding to an existing position (same direction):

```python
# Example: Buy 10 @ $150, then buy 5 @ $152
# Old: qty=10, avg=$150
# New: qty=15, avg=(10*150 + 5*152) / 15 = $150.67
```

### Reducing Position

When reducing position (partial close):

```python
# Example: Buy 10 @ $150, then sell 3 @ $155
# Old: qty=10, avg=$150
# New: qty=7, avg=$150 (keeps old average)
```

### Position Flip

When position flips direction:

```python
# Example: Buy 10 @ $150, then sell 15 @ $155
# Old: qty=10, avg=$150
# New: qty=-5, avg=$155 (new direction, new average)
```

## Edge Cases

### 1. Partial Fills

```python
# Order: Buy 10 @ $150
# Fill 1: 3 @ $150.10
# Fill 2: 7 @ $149.90

# After fill 1: qty=3, avg=$150.10
# After fill 2: qty=10, avg=(3*150.10 + 7*149.90)/10 = $149.96
```

### 2. Average Price Reset

Average price resets when:
- Position completely closes (qty → 0)
- Position flips direction (+10 → -5)

### 3. Position Flip

```python
# Long 10 @ $150
# Sell 15 @ $155
# Result: Short 5 @ $155 (flipped, new avg)
```

## P&L Calculation

### Realized P&L

Calculated when closing positions using FIFO:

```python
# Buy 10 @ $150
# Sell 10 @ $155
# Realized P&L = (155 - 150) * 10 = $50
```

### Unrealized P&L

Calculated using mark-to-market:

```python
# Position: qty=10, avg=$150
# Market price: $155
# Unrealized P&L = (155 - 150) * 10 = $50
```

### Usage

```python
from app.engine.position_manager import PositionManager

pm = PositionManager()

# Update position
pm.update_position("AAPL", 10, 150.0)  # Buy 10 @ $150

# Calculate unrealized P&L
market_prices = {"AAPL": 155.0}
unrealized = pm.calculate_unrealized_pnl(market_prices=market_prices)
# Returns: 50.0

# Get position
position = pm.get_position("AAPL")
# Returns: {'qty': 10.0, 'avg_price': 150.0, ...}
```

## State Snapshot Examples

### Example 1: Simple Long Position

```python
# Buy 10 @ $150
pm.update_position("AAPL", 10, 150.0)

# State:
{
    'qty': 10.0,
    'avg_price': 150.0,
    'realized_pnl': 0.0,
    'unrealized_pnl': 0.0
}
```

### Example 2: Adding to Position

```python
# Buy 10 @ $150
pm.update_position("AAPL", 10, 150.0)

# Buy 5 @ $152
pm.update_position("AAPL", 5, 152.0)

# State:
{
    'qty': 15.0,
    'avg_price': 150.67,  # (10*150 + 5*152) / 15
    'realized_pnl': 0.0,
    'unrealized_pnl': 0.0
}
```

### Example 3: Partial Close

```python
# Buy 10 @ $150
pm.update_position("AAPL", 10, 150.0)

# Sell 3 @ $155
pm.update_position("AAPL", -3, 155.0)

# State:
{
    'qty': 7.0,
    'avg_price': 150.0,  # Keeps old average
    'realized_pnl': 15.0,  # (155 - 150) * 3
    'unrealized_pnl': 0.0
}
```

### Example 4: Position Flip

```python
# Long 10 @ $150
pm.update_position("AAPL", 10, 150.0)

# Sell 15 @ $155
pm.update_position("AAPL", -15, 155.0)

# State:
{
    'qty': -5.0,  # Flipped to short
    'avg_price': 155.0,  # New average
    'realized_pnl': 50.0,  # (155 - 150) * 10
    'unrealized_pnl': 0.0
}
```

## Strategy Engine Integration

### Using Position Manager in Strategy

```python
from app.engine.position_manager import PositionManager

class MyStrategy(StrategyBase):
    def __init__(self, position_manager: PositionManager):
        self.position_manager = position_manager
    
    def on_tick(self, tick):
        symbol = tick['symbol']
        price = float(tick['last'])
        
        # Get current position
        position = self.position_manager.get_position(symbol)
        current_qty = position['qty'] if position else 0
        
        # Strategy logic
        if should_buy and current_qty == 0:
            # Place order (will update position via execution handler)
            OrderPublisher.publish_market_order(symbol, "BUY", 10)
```

### Engine Integration

```python
# engine_loop.py
engine = TradingEngine(strategy)
engine.position_manager  # Access position manager

# Get all positions
positions = engine.position_manager.get_all_positions()
```

## Methods Reference

### `update_position(symbol, quantity, price)`

Update position from execution.

**Parameters:**
- `symbol`: Stock symbol
- `quantity`: Position change (positive = buy, negative = sell)
- `price`: Execution price

**Returns:** None

### `apply_execution(exec_msg)`

Apply execution message to position.

**Parameters:**
- `exec_msg`: Execution message dict

**Returns:** None

### `get_position(symbol)`

Get position for a symbol.

**Parameters:**
- `symbol`: Stock symbol

**Returns:** Position dict or None

### `get_all_positions()`

Get all positions.

**Returns:** Dict of {symbol: position_dict}

### `calculate_unrealized_pnl(symbol, market_prices)`

Calculate unrealized P&L.

**Parameters:**
- `symbol`: Symbol (None = all)
- `market_prices`: Dict of {symbol: market_price}

**Returns:** Total unrealized P&L

## Best Practices

1. **Always validate execution data** before updating position
2. **Use FIFO for realized P&L** - Ensures accurate calculation
3. **Update market prices regularly** - For unrealized P&L
4. **Handle edge cases** - Position flips, partial fills
5. **Log position changes** - For audit trail

## Related Documentation

- [Execution Pipeline](./EXECUTION_PIPELINE.md) - Execution flow
- [IBKR Sync](./IBKR_SYNC.md) - Position synchronization








