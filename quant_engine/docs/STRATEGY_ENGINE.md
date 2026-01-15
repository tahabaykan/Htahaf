# Strategy Engine Documentation

## Overview

Strategy Engine is the brain of the trading system. It processes market data, calculates indicators, generates trading signals, and executes orders. This document describes the strategy framework, indicators, candle management, and how to create custom strategies.

## Architecture

```
┌─────────────┐
│ Market Data │
│   (Ticks)   │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  Candle Manager │
│  (Tick → OHLCV) │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│   Indicators    │
│  (SMA, EMA, RSI)│
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│    Strategy     │
│  (Your Logic)   │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│     Signal      │
│  (BUY/SELL)     │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐
│ Order Publisher │
└─────────────────┘
```

## Components

### 1. StrategyBase

Base class for all strategies. Provides:

- Indicator calculations
- Candle/OHLCV data access
- Position tracking
- Risk management integration
- Event-driven architecture

### 2. CandleManager

Converts ticks to OHLCV candles:

- Configurable interval (default: 60 seconds)
- Automatic candle creation/updating
- Candle history management
- Multi-symbol support

### 3. Indicators

Technical indicators:

- **SMA**: Simple Moving Average
- **EMA**: Exponential Moving Average
- **RSI**: Relative Strength Index
- **MACD**: Moving Average Convergence Divergence
- **Bollinger Bands**: Volatility bands

### 4. StrategyLoader

Dynamic strategy loading and hot-reload:

- Load strategies at runtime
- Hot-reload without engine restart
- Strategy management

## Creating a Strategy

### Basic Strategy Template

```python
from app.strategy.strategy_base import StrategyBase
from app.order.order_publisher import OrderPublisher

class MyStrategy(StrategyBase):
    def __init__(self):
        super().__init__(name="MyStrategy")
        self.sma_period = 20
    
    def on_initialize(self):
        """Called when strategy is initialized"""
        logger.info("MyStrategy initialized")
    
    def on_market_data(
        self,
        symbol: str,
        price: float,
        tick: Dict[str, Any],
        position: Optional[Dict],
        candle_data: Optional[Dict[str, List[float]]],
        completed_candle: Optional[Any]
    ) -> Optional[Dict[str, Any]]:
        """Main strategy logic"""
        
        # Get current position
        current_qty = position.get('qty', 0) if position else 0
        
        # Calculate indicator
        sma = self.get_indicator(symbol, 'sma', period=self.sma_period)
        if sma is None:
            return None  # Not enough data
        
        # Strategy logic
        if price > sma and current_qty <= 0:
            # Buy signal
            OrderPublisher.publish_market_order(symbol, "BUY", 10)
            return {
                'symbol': symbol,
                'signal': 'BUY',
                'price': price,
                'quantity': 10,
                'reason': 'Price above SMA'
            }
        
        return None
```

### Using Indicators

```python
# SMA
sma_20 = self.get_indicator(symbol, 'sma', period=20)

# EMA
ema_12 = self.get_indicator(symbol, 'ema', period=12)

# RSI
rsi = self.get_indicator(symbol, 'rsi', period=14)
```

### Using Candle Data

```python
# Get candle history
candles = self.get_candles(symbol, count=100)

# Get last candle
last_candle = candles[-1] if candles else None

# Access OHLCV
if last_candle:
    open_price = last_candle['open']
    high_price = last_candle['high']
    low_price = last_candle['low']
    close_price = last_candle['close']
    volume = last_candle['volume']
```

### Using Position Data

```python
# Get current position
position = self.get_position(symbol)

if position:
    qty = position['qty']
    avg_price = position['avg_price']
    unrealized_pnl = position['unrealized_pnl']
```

## Example Strategies

### 1. Simple Moving Average Crossover

```python
class SMACrossoverStrategy(StrategyBase):
    def on_market_data(self, symbol, price, tick, position, candle_data, completed_candle):
        sma_fast = self.get_indicator(symbol, 'sma', period=10)
        sma_slow = self.get_indicator(symbol, 'sma', period=20)
        
        if sma_fast and sma_slow:
            if sma_fast > sma_slow:
                # Bullish crossover
                return {'signal': 'BUY', ...}
            elif sma_fast < sma_slow:
                # Bearish crossover
                return {'signal': 'SELL', ...}
```

### 2. RSI Strategy

```python
class RSIStrategy(StrategyBase):
    def on_market_data(self, symbol, price, tick, position, candle_data, completed_candle):
        rsi = self.get_indicator(symbol, 'rsi', period=14)
        
        if rsi:
            if rsi < 30:  # Oversold
                return {'signal': 'BUY', ...}
            elif rsi > 70:  # Overbought
                return {'signal': 'SELL', ...}
```

## Multi-Symbol Strategy

```python
class MultiSymbolStrategy(StrategyBase):
    def __init__(self):
        super().__init__(name="MultiSymbol")
        self.symbols = ["AAPL", "MSFT", "GOOGL"]
    
    def on_market_data(self, symbol, price, tick, position, candle_data, completed_candle):
        # Process each symbol independently
        if symbol in self.symbols:
            # Strategy logic for this symbol
            ...
```

## Hot Reload

Strategies can be hot-reloaded without restarting the engine:

```python
from app.strategy.strategy_loader import strategy_loader

# Reload strategy
new_strategy = strategy_loader.reload_strategy("MyStrategy")
```

## Risk Guards

Strategies automatically use risk manager:

```python
# In strategy_base.py
if self.risk_manager and not self.risk_manager.check_signal(signal):
    logger.warning(f"Signal rejected by risk manager")
    return None
```

## Best Practices

1. **Always check for sufficient data** before calculating indicators
2. **Use candle data** for more reliable signals than raw ticks
3. **Check position** before generating signals
4. **Use risk manager** to validate signals
5. **Log strategy decisions** for debugging
6. **Handle edge cases** (no data, invalid prices, etc.)

## Performance Tips

1. **Cache indicator values** - Use indicator_cache
2. **Limit candle history** - Don't keep too many candles
3. **Batch processing** - Process multiple symbols efficiently
4. **Avoid blocking operations** - Keep strategy logic fast

## Related Documentation

- [Execution Pipeline](./EXECUTION_PIPELINE.md) - How signals become orders
- [Position Manager](./POSITION_MANAGER.md) - Position tracking
- [Order Pipeline](../ORDER_PIPELINE.md) - Order flow








