# Order Pipeline Documentation

Bu dokümantasyon order pipeline'ın nasıl çalıştığını açıklar: Signal → Order Router → IBKR Execution.

## 📋 İçindekiler

1. [Genel Bakış](#genel-bakış)
2. [Kullanım](#kullanım)
3. [Order Flow](#order-flow)
4. [Order Types](#order-types)
5. [Error Handling](#error-handling)

---

## 🎯 Genel Bakış

Order pipeline şu bileşenlerden oluşur:

- **OrderMessage**: Pydantic model (order validation)
- **OrderPublisher**: Strategy'den order yayınlama
- **OrderRouter**: Redis stream'den order okuyup IBKR'ye gönderme

### Veri Akışı

```
Strategy → OrderPublisher.publish() → Redis Stream ("orders") → OrderRouter → IBKR → Execution
```

---

## 🚀 Kullanım

### 1. Strategy'den Order Yayınlama

```python
from app.order.order_publisher import OrderPublisher

# Market order
OrderPublisher.publish_market_order("AAPL", "BUY", 10)

# Limit order
OrderPublisher.publish_limit_order("AAPL", "BUY", 10, limit_price=150.0)

# Full control
OrderPublisher.publish(
    symbol="AAPL",
    side="BUY",
    qty=10.0,
    order_type="LMT",
    limit_price=150.0
)
```

### 2. Order Router Başlatma

```bash
# Terminal 1: Order Router
python main.py router

# Terminal 2: Engine (order üretecek strategy ile)
python main.py engine-async
```

### 3. Tam Akış Testi

```bash
# Terminal 1: Redis
docker compose up -d redis

# Terminal 2: Hammer ingest
python main.py hammer --symbol AAPL

# Terminal 3: Engine
python main.py engine-async

# Terminal 4: Order Router
python main.py router
```

---

## 📊 Order Flow

### 1. Order Creation

Strategy içinde:

```python
from app.order.order_publisher import OrderPublisher

# Signal üretildiğinde order yayınla
if signal_condition:
    OrderPublisher.publish_market_order("AAPL", "BUY", 10)
```

### 2. Redis Stream

Order Redis stream'e yazılır:

```python
{
    "symbol": "AAPL",
    "side": "BUY",
    "qty": 10.0,
    "order_type": "MKT",
    "limit_price": None,
    "timestamp": 1700000000000
}
```

### 3. Order Router

OrderRouter stream'den okur ve IBKR'ye gönderir:

```python
# OrderRouter.start() içinde
msg = EventBus.stream_read("orders", block=1000)
order_msg = OrderMessage(**msg["data"])
trade = router._execute(order_msg)
```

### 4. IBKR Execution

IBKR order'ı execute eder ve callback'ler tetiklenir:

- `_on_order_status()`: Order status güncellemeleri
- `_on_execution()`: Fill bilgileri

### 5. Event Publishing

Execution bilgileri Redis'e yayınlanır:

- `order_status` channel: Status updates
- `executions` channel: Fill details

---

## 📝 Order Types

### Market Order (MKT)

```python
OrderPublisher.publish_market_order("AAPL", "BUY", 10)
```

- Anında execution
- Mevcut market price'dan alır/satar
- Limit price gerekmez

### Limit Order (LMT)

```python
OrderPublisher.publish_limit_order("AAPL", "BUY", 10, limit_price=150.0)
```

- Belirtilen fiyattan veya daha iyi fiyattan execution
- Limit price zorunlu
- Gün sonuna kadar geçerli (DAY)

---

## ⚠️ Error Handling

### Validation Errors

OrderMessage validation hataları:

```python
# Invalid side
OrderPublisher.publish("AAPL", "INVALID", 10)  # ValueError

# Missing limit_price for LMT
OrderPublisher.publish("AAPL", "BUY", 10, order_type="LMT")  # ValueError
```

### IBKR Connection Errors

OrderRouter IBKR'ye bağlanamazsa:

```
❌ IBKR connection failed
```

**Çözüm:**
1. TWS/Gateway çalışıyor mu?
2. Port doğru mu? (7497 paper, 7496 live)
3. API izinleri aktif mi?

### Order Execution Errors

IBKR order execution hataları loglanır:

```
[ERROR] Error executing order: ...
```

---

## 🔧 Configuration

### Environment Variables

`.env` dosyasında:

```bash
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_CLIENT_ID=1
```

### Order Router Settings

```python
router = OrderRouter(
    host="127.0.0.1",
    port=7497,
    client_id=1
)
```

---

## 📈 Monitoring

### Order Statistics

OrderRouter çalışırken:

```
Order Router stopped. Orders: 50, Errors: 2
```

### Redis Stream Monitoring

```bash
# Stream uzunluğu
redis-cli XLEN orders

# Stream içeriği
redis-cli XREAD STREAMS orders 0-0
```

### Order Status Events

OrderRouter order status'ları `order_status` channel'ına yayınlar:

```python
{
    "order_id": 12345,
    "symbol": "AAPL",
    "status": "Filled",
    "filled": 10.0,
    "remaining": 0.0,
    "avg_fill_price": 150.25,
    "timestamp": 1700000000000
}
```

---

## 🎯 Best Practices

1. **Order Validation**: Her zaman OrderMessage.validate() kullanın
2. **Error Handling**: OrderPublisher ve OrderRouter'da try/except kullanın
3. **Rate Limiting**: IBKR rate limit'lerine dikkat edin
4. **Order Tracking**: Order ID'leri kaydedin ve takip edin
5. **Position Sync**: Execution sonrası position manager'ı güncelleyin

---

## 🚀 Sonraki Adımlar

1. ✅ Order pipeline (tamamlandı)
2. ⏳ Execution listener (IBKR → Position Manager)
3. ⏳ Order cancel/replace
4. ⏳ Order history tracking
5. ⏳ WebSocket UI integration






