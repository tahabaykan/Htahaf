# Execution Adapter Architecture

## 🎯 Core Principle

**Market Data ≠ Execution (STRICT SEPARATION)**

- **Market Data**: ALWAYS from Hammer (single source of truth)
- **Execution**: Pluggable via ExecutionAdapter (IBKR | HAMMER)
- **Strategy**: Broker-agnostic

## 📐 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Market Data Layer                     │
│              (ALWAYS Hammer - Single Source)              │
│                                                           │
│  Hammer Feed (L1 + L2) → Symbol Normalization            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                    Strategy Layer                        │
│              (Broker-Agnostic Logic)                     │
│                                                           │
│  Strategy.on_tick() → Strategy.on_orderbook()            │
│  Strategy.place_order() → ExecutionAdapter               │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                 Execution Layer                           │
│              (Pluggable Adapters)                         │
│                                                           │
│  ┌──────────────────┐    ┌──────────────────┐           │
│  │ IBKRExecution   │    │ HammerExecution  │           │
│  │    Adapter      │    │    Adapter        │           │
│  └──────────────────┘    └──────────────────┘           │
└─────────────────────────────────────────────────────────┘
```

## 🔌 ExecutionAdapter Interface

All execution adapters implement this interface:

```python
class ExecutionAdapter(ABC):
    def connect() -> bool
    def disconnect()
    def is_connected() -> bool
    def place_order(symbol, side, quantity, price, order_type) -> bool
    def cancel_order(order_id) -> bool
    def get_positions() -> List[Dict]
    def get_open_orders() -> List[Dict]
    def set_execution_callback(callback)
```

## 🏗️ Implementations

### 1. HammerExecutionAdapter

- **Account**: Hammer account key (e.g., `ALARIC:TOPI002240A7`)
- **Symbol Format**: Converts display → Hammer format (`CIM PRB` → `CIM-B`)
- **Features**: Hidden orders, L2-aware execution

### 2. IBKRExecutionAdapter

- **Account**: IBKR account ID (e.g., `DU123456` or `U123456`)
- **Symbol Format**: Uses native IBKR format (`CIM PRB` stays `CIM PRB`)
- **Features**: SMART routing, TWS/Gateway integration

## 🚀 Usage

### Runtime Broker Selection

```bash
# Use Hammer for execution (default)
python main.py live --execution-broker HAMMER --hammer-account ALARIC:TOPI002240A7

# Use IBKR for execution
python main.py live --execution-broker IBKR --ibkr-account DU123456
```

### In Code

```python
from app.live.hammer_feed import HammerFeed
from app.live.hammer_execution_adapter import HammerExecutionAdapter
from app.live.ibkr_execution_adapter import IBKRExecutionAdapter
from app.engine.live_engine import LiveEngine

# Market data: ALWAYS Hammer
hammer_feed = HammerFeed(hammer_client)

# Execution: Choose adapter
if broker == "IBKR":
    execution = IBKRExecutionAdapter(account_id="DU123456")
elif broker == "HAMMER":
    execution = HammerExecutionAdapter(
        account_key="ALARIC:TOPI002240A7",
        hammer_client=hammer_client
    )

# Engine is broker-agnostic
engine = LiveEngine(
    hammer_feed=hammer_feed,
    execution_adapter=execution
)
```

## 🔒 Account Guard

Execution adapters enforce account separation:

```python
# This will raise ValueError if account mismatch
execution._validate_account(expected_account="DU123456")
```

## 📊 Symbol Mapping

Symbol mapping is centralized in `SymbolMapper`:

- **Display Format**: `"CIM PRB"` (used by strategy)
- **Hammer Format**: `"CIM-B"` (used by Hammer execution)
- **IBKR Format**: `"CIM PRB"` (used by IBKR execution)

Strategy always uses display format. Adapters handle conversion.

## ✅ Benefits

1. **Account Separation**: IBKR and Hammer accounts never mix
2. **Strategy Reusability**: Same strategy works with any broker
3. **Runtime Flexibility**: Switch brokers without code changes
4. **Single Source of Truth**: Market data always from Hammer
5. **Testability**: Easy to mock execution adapters

## 🚨 Important Notes

- **Market data is ALWAYS from Hammer** - never from IBKR
- **Strategy code is broker-agnostic** - uses ExecutionAdapter interface
- **Account IDs are validated** - prevents accidental account mixing
- **Symbol formats are handled by adapters** - strategy uses display format

## 🔄 Migration Guide

### Old Code (Hardcoded Hammer)

```python
# OLD - Don't do this
hammer_execution = HammerExecution(hammer_client)
engine = LiveEngine(hammer_feed, hammer_execution)
```

### New Code (Adapter Pattern)

```python
# NEW - Use adapter
execution = HammerExecutionAdapter(
    account_key="ALARIC:TOPI002240A7",
    hammer_client=hammer_client
)
engine = LiveEngine(hammer_feed, execution)
```

## 📝 TODO

- [ ] Add get_open_orders() to HammerExecutionAdapter
- [ ] Add order status tracking
- [ ] Add execution replay for backtesting
- [ ] Add multi-account support (same broker, different accounts)








