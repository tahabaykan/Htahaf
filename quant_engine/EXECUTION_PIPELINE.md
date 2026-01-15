# Execution Pipeline Documentation

Bu dokümantasyon execution → position sync pipeline'ının nasıl çalıştığını açıklar.

## 📋 İçindekiler

1. [Genel Bakış](#genel-bakış)
2. [Execution Flow](#execution-flow)
3. [Position Management](#position-management)
4. [IBKR Synchronization](#ibkr-synchronization)
5. [Kullanım](#kullanım)

---

## 🎯 Genel Bakış

Execution pipeline şu bileşenlerden oluşur:

- **OrderRouter Callbacks**: IBKR execution'larını yakalar
- **ExecutionHandler**: Execution'ları işler ve position manager'a gönderir
- **PositionManager**: Pozisyonları günceller, P&L hesaplar
- **IBKRSync**: Startup'ta IBKR'den pozisyonları çeker

### Veri Akışı

```
IBKR Execution
    ↓
OrderRouter._on_execution()
    ↓
Redis Stream ("executions")
    ↓
ExecutionHandler._loop()
    ↓
PositionManager.update_position()
    ↓
Position Updated ✅
```

---

## 📊 Execution Flow

### 1. IBKR Execution

IBKR order execute edildiğinde callback tetiklenir:

```python
# order_router.py
def _on_execution(self, trade, fill):
    exec_msg = {
        "symbol": symbol,
        "qty": exec_qty,
        "price": exec_price,
        "side": "BUY" or "SELL",
        "timestamp": timestamp,
        "order_id": order_id,
        "exec_id": exec_id,
        "remaining": remaining,
        "avg_fill_price": avg_fill_price
    }
    
    # Publish to Redis stream
    EventBus.stream_add("executions", exec_msg)
```

### 2. Execution Handler

ExecutionHandler stream'den okur ve işler:

```python
# execution_handler.py
def _process_execution(self, exec_data):
    # Convert side to quantity
    if side == "BUY":
        quantity = qty
    else:
        quantity = -qty
    
    # Update position
    position_manager.update_position(symbol, quantity, price)
```

### 3. Position Update

PositionManager pozisyonu günceller:

```python
# position_manager.py
def update_position(self, symbol, quantity, price):
    # Calculate new average price
    # Update FIFO queue
    # Update position data
```

---

## 💼 Position Management

### Position Data Structure

Her symbol için:

```python
{
    'qty': float,              # Position quantity (positive = long, negative = short)
    'avg_price': float,        # Average entry price
    'realized_pnl': float,     # Realized P&L
    'unrealized_pnl': float,   # Unrealized P&L
    'last_update_time': float  # Last update timestamp
}
```

### Average Price Calculation

- **New Position**: Execution price
- **Adding to Position**: Weighted average
- **Reducing Position**: Keep old average (FIFO)

### P&L Calculation

- **Realized P&L**: Calculated when closing positions (FIFO-based)
- **Unrealized P&L**: (Market Price - Avg Price) × Quantity

---

## 🔄 IBKR Synchronization

### Startup Sync

Engine başlarken IBKR'den pozisyonlar çekilir:

```python
# engine_loop.py
async def _sync_positions_on_start(self):
    ibkr_sync.sync_positions_to_manager(self.position_manager)
```

### Manual Sync

```bash
# IBKR sync komutu
python main.py sync
```

Çıktı:
- Open positions
- Open orders
- Account summary (Net Liquidation, Buying Power, etc.)

### Sync Methods

```python
from app.ibkr.ibkr_sync import ibkr_sync

# Fetch positions
positions = ibkr_sync.fetch_open_positions()

# Fetch orders
orders = ibkr_sync.fetch_open_orders()

# Fetch account summary
summary = ibkr_sync.fetch_account_summary()
```

---

## 🚀 Kullanım

### Tam Akış Testi

```bash
# Terminal 1: Redis
docker compose up -d redis

# Terminal 2: Hammer ingest
python main.py hammer --symbol AAPL

# Terminal 3: Engine (with position sync)
python main.py engine-async

# Terminal 4: Order Router
python main.py router
```

### Position Sync

```bash
# IBKR'den pozisyonları çek ve göster
python main.py sync
```

### Position Monitoring

```python
from app.engine.position_manager import PositionManager

pm = PositionManager()

# Get all positions
positions = pm.get_all_positions()

# Get single position
position = pm.get_position("AAPL")

# Get positions summary
summary = pm.get_positions_summary()

# Calculate P&L
unrealized_pnl = pm.calculate_unrealized_pnl(market_prices={"AAPL": 150.0})
```

---

## 📝 Execution Message Format

### Normalized Execution Message

```python
{
    "symbol": "AAPL",
    "qty": 10.0,
    "price": 150.25,
    "side": "BUY",
    "timestamp": 1700000000000,
    "order_id": 12345,
    "exec_id": "abc123",
    "remaining": 0.0,
    "avg_fill_price": 150.25
}
```

---

## ⚠️ Error Handling

### Execution Processing Errors

ExecutionHandler hataları loglar ve devam eder:

```
[ERROR] Error processing execution: ...
```

### Position Update Errors

PositionManager hataları loglar:

```
[ERROR] Error updating position: ...
```

### IBKR Sync Errors

IBKR sync hataları loglar ama engine başlamaya devam eder:

```
[WARNING] Could not connect to IBKR, skipping position sync
```

---

## 🔧 Configuration

### Disable Startup Sync

```python
# engine_loop.py
engine = TradingEngine(strategy, sync_on_start=False)
```

### Manual Position Sync

```python
from app.ibkr.ibkr_sync import ibkr_sync
from app.engine.position_manager import PositionManager

pm = PositionManager()
ibkr_sync.sync_positions_to_manager(pm)
```

---

## 📈 Monitoring

### Execution Statistics

ExecutionHandler çalışırken:

```
Execution handler: Processed 50 executions (errors: 0)
```

### Position Updates

PositionManager logları:

```
Position updated: AAPL = 10 @ 150.25 (change: +10)
```

### Redis Stream Monitoring

```bash
# Execution stream uzunluğu
redis-cli XLEN executions

# Execution stream içeriği
redis-cli XREAD STREAMS executions 0-0
```

---

## 🎯 Best Practices

1. **Startup Sync**: Her zaman startup'ta IBKR'den sync yapın
2. **Position Tracking**: Her execution'dan sonra position güncellenir
3. **P&L Calculation**: Market prices ile unrealized P&L hesaplayın
4. **Error Handling**: Execution hatalarını loglayın ama devam edin
5. **FIFO Tracking**: Realized P&L için FIFO queue kullanın

---

## 🚀 Sonraki Adımlar

1. ✅ Execution pipeline (tamamlandı)
2. ✅ Position sync (tamamlandı)
3. ⏳ Real-time P&L updates
4. ⏳ Position exposure limits
5. ⏳ WebSocket UI integration

---

## 📊 Example Output

### Position Sync Output

```
=== Open Positions ===
  AAPL: +10 @ $150.25 (P&L: $2.50)
  MSFT: -5 @ $350.00 (P&L: -$1.25)

=== Open Orders ===
  AAPL BUY 10 (LMT) - Status: Submitted (Filled: 0, Remaining: 10)

=== Account Summary ===
  Account: DU123456
    NetLiquidation: 100000.00
    TotalCashValue: 50000.00
    BuyingPower: 200000.00
```

---

## 🔍 Troubleshooting

### Problem: Positions not syncing

**Çözüm:**
1. IBKR bağlantısını kontrol edin
2. `python main.py sync` ile manuel sync deneyin
3. Log'larda hata mesajlarını kontrol edin

### Problem: Execution not processed

**Çözüm:**
1. ExecutionHandler çalışıyor mu?
2. Redis stream'de execution var mı? `redis-cli XLEN executions`
3. ExecutionHandler log'larını kontrol edin

### Problem: Position calculation wrong

**Çözüm:**
1. FIFO queue'yu kontrol edin
2. Average price calculation'ı doğrulayın
3. Market prices'ı güncel tutun








