# Phase 10.1: Real IBKR Connection (Normal Bağlantı, Execution Yok)

## 📋 Genel Bakış

Phase 10.1, IBKR Gateway / TWS üzerinden gerçek hesap pozisyonlarını PSFALGO'ya bağlar. Execution yok, order gönderimi yok. SADECE positions / open orders / account summary.

**ÖNEMLİ**: 
- Normal bağlantı (READ-ONLY değil, ama execution yok)
- Live account (paper account değil)
- Market data HER ZAMAN HAMMER
- IBKR sadece pozisyon & emir bilgisi
- Execution ASLA yapılmayacak

---

## 🎯 Hedefler

1. **ib_insync entegrasyonu**: Real IBKR connection
2. **IBKRConnector implementasyonu**: connect, disconnect, get_positions, get_open_orders, get_account_summary
3. **PositionSnapshot mapping**: IBKR Position → PositionSnapshot
4. **PositionSnapshotAPI update**: Account mode'a göre IBKR veya HAMMER
5. **API endpoints aktif**: Connect, positions, orders, summary
6. **Güvenlik**: order.place() ASLA yok, trade() ASLA yok
7. **Test**: IBKR live account ile test

---

## 📁 Dosya Yapısı

```
quant_engine/
├── requirements.txt          # ib-insync eklendi
├── app/psfalgo/
│   └── ibkr_connector.py    # Real IBKR connection implementation
└── app/api/
    └── psfalgo_routes.py    # Updated connect endpoint
```

---

## 🔧 Bileşenler

### 1. ib_insync Entegrasyonu

**requirements.txt:**
```
ib-insync>=0.9.86
```

**Install:**
```bash
pip install ib-insync
```

### 2. IBKRConnector Implementation

**Connection:**
- `connect(host, port, client_id)`: Connect to IBKR Gateway / TWS
- Default ports:
  - GUN: port 4001 (Gateway) / 7497 (TWS)
  - PED: port 4002 (Gateway) / 7496 (TWS)
- Live account (not paper)

**Methods:**
- `get_positions()`: Get positions from IBKR
- `get_open_orders()`: Get open orders from IBKR
- `get_account_summary()`: Get account summary from IBKR

**Position Mapping:**
```python
{
    'symbol': contract.symbol,
    'qty': pos.position,  # Positive = Long, Negative = Short
    'avg_price': pos.averageCost / pos.position if pos.position != 0 else 0,
    'account': pos.account
}
```

### 3. PositionSnapshot Mapping

**IBKR Position → PositionSnapshot:**
- `symbol`: From contract.symbol
- `qty`: From position.position
- `avg_price`: From position.averageCost / position.position
- `account_type`: IBKR_GUN or IBKR_PED
- `current_price`: From HAMMER market data (ALWAYS)
- `timestamp`: Current time

### 4. PositionSnapshotAPI Update

**Logic:**
- AccountModeManager'a bak
- Eğer mode = IBKR_GUN veya IBKR_PED:
  → IBKRConnector.get_positions() kullan
- Eğer mode = HAMMER_PRO:
  → Mevcut Hammer logic

**Market Data:**
- current_price ALWAYS from HAMMER
- IBKR sadece pozisyon bilgisi

---

## 🔌 API Endpoints

### Connect to IBKR

**POST /api/psfalgo/account/ibkr/connect**

**Parameters:**
- `account_type`: IBKR_GUN or IBKR_PED
- `host`: IBKR Gateway / TWS host (default: 127.0.0.1)
- `port`: Port number (default: based on account_type)
- `client_id`: Client ID (default: 1)

**Example:**
```bash
POST /api/psfalgo/account/ibkr/connect?account_type=IBKR_GUN&host=127.0.0.1&port=4001&client_id=1
```

**Response:**
```json
{
  "success": true,
  "account_type": "IBKR_GUN",
  "host": "127.0.0.1",
  "port": 4001,
  "client_id": 1,
  "connected": true
}
```

### Get Positions

**GET /api/psfalgo/account/ibkr/positions**

**Response:**
```json
{
  "success": true,
  "account_type": "IBKR_GUN",
  "count": 5,
  "positions": [
    {
      "symbol": "MS PRK",
      "qty": 400.0,
      "avg_price": 27.00,
      "account": "DU123456"
    }
  ]
}
```

### Get Open Orders

**GET /api/psfalgo/account/ibkr/orders**

**Response:**
```json
{
  "success": true,
  "account_type": "IBKR_GUN",
  "count": 2,
  "orders": [
    {
      "order_id": 12345,
      "symbol": "MS PRK",
      "side": "SELL",
      "qty": 300,
      "order_type": "LMT",
      "limit_price": 27.32,
      "status": "Submitted",
      "filled": 0,
      "remaining": 300
    }
  ]
}
```

### Get Account Summary

**GET /api/psfalgo/account/ibkr/summary**

**Response:**
```json
{
  "success": true,
  "account_type": "IBKR_GUN",
  "summary": {
    "account": "IBKR_GUN",
    "connected": true,
    "net_liquidation": 100000.0,
    "buying_power": 50000.0,
    "total_cash": 75000.0,
    "gross_position_value": 25000.0,
    "available_funds": 50000.0
  }
}
```

---

## 🚀 Kullanım

### 1. Install ib_insync

```bash
pip install ib-insync
```

### 2. Start IBKR Gateway / TWS

- Start IBKR Gateway or TWS
- Ensure API is enabled
- Note the port (default: 4001 for Gateway, 7497 for TWS)

### 3. Connect to IBKR

```python
from app.psfalgo.ibkr_connector import get_ibkr_connector

connector = get_ibkr_connector("IBKR_GUN")
result = await connector.connect(host='127.0.0.1', port=4001, client_id=1)
```

### 4. Get Positions

```python
positions = await connector.get_positions()
for pos in positions:
    print(f"{pos['symbol']}: {pos['qty']} @ {pos['avg_price']}")
```

### 5. Set Account Mode

```python
from app.psfalgo.account_mode import get_account_mode_manager

manager = get_account_mode_manager()
manager.set_mode("IBKR_GUN")
```

### 6. Get Position Snapshots

```python
from app.psfalgo.position_snapshot_api import get_position_snapshot_api

api = get_position_snapshot_api()
snapshots = await api.get_position_snapshot()

# Snapshots now include IBKR positions
for snap in snapshots:
    print(f"{snap.symbol}: {snap.qty} @ {snap.avg_price} ({snap.account_type})")
    print(f"  Current price (from HAMMER): {snap.current_price}")
```

---

## ⚠️ Önemli Notlar

1. **Normal Bağlantı (Execution Yok)**:
   - Normal IBKR connection (not READ-ONLY)
   - But execution ASLA yapılmayacak
   - order.place() ASLA yok
   - trade() ASLA yok

2. **Live Account**:
   - Paper account değil
   - Live account'a bağlanır
   - Janall'daki gibi normal bağlantı

3. **Market Data ALWAYS from HAMMER**:
   - L1/L2/prints/GRPAN/RWVAP = SADECE HAMMER
   - IBKR sadece pozisyon & emir bilgisi
   - PositionSnapshot'da current_price ALWAYS from HAMMER

4. **Port Configuration**:
   - GUN: port 4001 (Gateway) / 7497 (TWS)
   - PED: port 4002 (Gateway) / 7496 (TWS)
   - Default: Gateway ports

5. **Account Filtering**:
   - Positions filtered by account field
   - Account field format: "DU123456" or similar
   - Can be extended to filter by account prefix

6. **Error Handling**:
   - Graceful degradation if ib_insync not available
   - Connection errors logged
   - Returns empty lists on error

---

## 🔒 Güvenlik

**YASAKLAR:**
- `order.place()` ASLA yok
- `trade()` ASLA yok
- Execution engine ile bağlantı YOK
- Broker order API çağrısı YOK

**SADECE:**
- `positions()` - Get positions
- `openOrders()` - Get open orders
- `accountValues()` - Get account summary

---

## 🧪 Test

### 1. IBKR Connection Test

```bash
# Connect to IBKR_GUN
POST /api/psfalgo/account/ibkr/connect?account_type=IBKR_GUN&port=4001

# Check status
GET /api/psfalgo/account/ibkr/status
```

### 2. Positions Test

```bash
# Get positions
GET /api/psfalgo/account/ibkr/positions?account_type=IBKR_GUN

# Should return at least 1 long + 1 short position
```

### 3. PositionSnapshot Test

```bash
# Set account mode
POST /api/psfalgo/account/mode
{
  "mode": "IBKR_GUN"
}

# Get position snapshots
GET /api/psfalgo/position/snapshot

# Should return IBKR positions with:
# - account_type = IBKR_GUN
# - current_price from HAMMER
# - qty, avg_price from IBKR
```

### 4. UI Inspector Test

- UI inspector'da pozisyonlar görünmeli
- account_type gösterilmeli
- current_price HAMMER'dan gelmeli

### 5. Proposal Engine Test

- Proposal engine bu pozisyonları input olarak kullanmalı
- Decision engines IBKR positions üzerinde çalışmalı

---

## 📈 Sonraki Adımlar

1. ✅ ib_insync entegrasyonu
2. ✅ IBKRConnector implementasyonu
3. ✅ PositionSnapshot mapping
4. ✅ PositionSnapshotAPI update
5. ✅ API endpoints aktif
6. ✅ Güvenlik (execution yok)
7. ⏳ Test (IBKR live account)

---

## 🎯 Phase 10.1 Durumu

**TAMAMLANDI** ✅

- ib_insync entegrasyonu: ✅
- IBKRConnector implementasyonu: ✅
- PositionSnapshot mapping: ✅
- PositionSnapshotAPI update: ✅
- API endpoints aktif: ✅
- Güvenlik: ✅
- Documentation: ✅

**Test**: ⏳ TODO (IBKR live account ile test)

**Sistem artık gerçek IBKR hesabına bağlanabilir!** 🔌

Trader kendi IBKR hesabında manuel trade ederken, algoritmanın hangi pozisyonlara yöneldiğini kendi gerçek hesabı üzerinden görebilir.






