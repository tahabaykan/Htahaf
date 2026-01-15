# Phase 10: Account Connector & Mode Switch (READ-ONLY)

## 📋 Genel Bakış

Phase 10, IBKR ve HAMMER pozisyonlarını algoya bağlar. Market data HER ZAMAN Hammer'dan gelmeye devam eder, execution ASLA yapılmaz (HUMAN_ONLY).

**ÖNEMLİ**: 
- Market data ALWAYS from HAMMER
- IBKR is READ-ONLY (positions, orders, account summary)
- Execution ASLA yapılmayacak (HUMAN_ONLY)
- PositionSnapshot standardize edilir (account_type)

---

## 🎯 Hedefler

1. **Account Mode Selector**: HAMMER_PRO, IBKR_GUN, IBKR_PED
2. **IBKR Gateway Connector (READ-ONLY)**: Positions, open orders, account summary
3. **Unified PositionSnapshot**: account_type ile standardize
4. **Market Data Separation**: L1/L2/prints/GRPAN/RWVAP = SADECE HAMMER
5. **Safety**: HUMAN_ONLY mode sabit, execution yok

---

## 📁 Dosya Yapısı

```
quant_engine/app/psfalgo/
├── account_mode.py           # Account mode manager
├── ibkr_connector.py        # IBKR Gateway connector (READ-ONLY)
└── position_snapshot_api.py  # Updated with account_type support
```

---

## 🔧 Bileşenler

### 1. AccountModeManager (`account_mode.py`)

**Sorumluluklar:**
- Manage account mode selection
- Provide account mode info
- Validate account mode

**Account Modes:**
- `HAMMER_PRO`: Hammer Pro account (default)
- `IBKR_GUN`: IBKR GUN account
- `IBKR_PED`: IBKR PED account

**Özellikler:**
- `set_mode()`: Set account mode
- `get_mode()`: Get current account mode
- `is_hammer()`, `is_ibkr_gun()`, `is_ibkr_ped()`, `is_ibkr()`: Check mode
- `get_account_type()`: Get account type for PositionSnapshot

### 2. IBKRConnector (`ibkr_connector.py`)

**Sorumluluklar:**
- Connect to IBKR Gateway / TWS (READ-ONLY)
- Get positions (READ-ONLY)
- Get open orders (READ-ONLY)
- Get account summary (READ-ONLY)
- Account selector (GUN / PED)

**Özellikler:**
- `connect()`: Connect to IBKR Gateway / TWS
- `disconnect()`: Disconnect from IBKR
- `get_positions()`: Get positions (READ-ONLY)
- `get_open_orders()`: Get open orders (READ-ONLY)
- `get_account_summary()`: Get account summary (READ-ONLY)
- `is_connected()`: Check connection status

**NOT**: Actual IBKR Gateway / TWS connection implementation is placeholder. To be implemented with `ib_insync` or similar library.

### 3. Unified PositionSnapshot (`decision_models.py`)

**Updated Fields:**
- `account_type`: HAMMER_PRO, IBKR_GUN, IBKR_PED (PHASE 10)

**PositionSnapshot API (`position_snapshot_api.py`):**
- `get_position_snapshot()`: Now gets positions from appropriate source (HAMMER or IBKR)
- `get_all_positions()`: Now gets all positions from appropriate source
- Market data ALWAYS from HAMMER (regardless of account mode)

---

## 📊 Market Data Separation (KRİTİK)

**Market Data (ALWAYS from HAMMER):**
- L1 updates (bid/ask/last)
- L2 updates (order book)
- Trade prints
- GRPAN calculations
- RWVAP calculations
- All market data metrics

**IBKR (READ-ONLY):**
- Positions
- Open orders
- Account summary
- NO market data
- NO order submission

---

## 🔌 API Endpoints

### Account Mode

**Get Account Mode:**
```bash
GET /api/psfalgo/account/mode
```

**Response:**
```json
{
  "success": true,
  "mode": "HAMMER_PRO",
  "is_hammer": true,
  "is_ibkr_gun": false,
  "is_ibkr_ped": false,
  "is_ibkr": false
}
```

**Set Account Mode:**
```bash
POST /api/psfalgo/account/mode
{
  "mode": "IBKR_GUN"
}
```

### IBKR Connection

**Connect to IBKR:**
```bash
POST /api/psfalgo/account/ibkr/connect?account_type=IBKR_GUN
```

**Disconnect from IBKR:**
```bash
POST /api/psfalgo/account/ibkr/disconnect?account_type=IBKR_GUN
```

**Get IBKR Status:**
```bash
GET /api/psfalgo/account/ibkr/status
```

**Response:**
```json
{
  "success": true,
  "IBKR_GUN": {
    "connected": true,
    "error": null
  },
  "IBKR_PED": {
    "connected": false,
    "error": "Not connected"
  }
}
```

### IBKR Data (READ-ONLY)

**Get Positions:**
```bash
GET /api/psfalgo/account/ibkr/positions?account_type=IBKR_GUN
```

**Get Open Orders:**
```bash
GET /api/psfalgo/account/ibkr/orders?account_type=IBKR_GUN
```

**Get Account Summary:**
```bash
GET /api/psfalgo/account/ibkr/summary?account_type=IBKR_GUN
```

---

## 🚀 Kullanım

### 1. Set Account Mode

```python
from app.psfalgo.account_mode import get_account_mode_manager

manager = get_account_mode_manager()
manager.set_mode("IBKR_GUN")
```

### 2. Connect to IBKR

```python
from app.psfalgo.ibkr_connector import get_ibkr_connector

connector = get_ibkr_connector("IBKR_GUN")
result = await connector.connect()
```

### 3. Get Positions

```python
from app.psfalgo.position_snapshot_api import get_position_snapshot_api

api = get_position_snapshot_api()
positions = await api.get_all_positions()

# Positions now include account_type
for pos in positions:
    print(f"{pos.symbol}: {pos.qty} @ {pos.avg_price} ({pos.account_type})")
```

---

## ⚠️ Önemli Notlar

1. **Market Data ALWAYS from HAMMER**:
   - L1/L2/prints/GRPAN/RWVAP = SADECE HAMMER
   - IBKR sadece pozisyon & emir bilgisi
   - PositionSnapshot'da current_price ALWAYS from HAMMER

2. **IBKR is READ-ONLY**:
   - Positions: READ-ONLY
   - Open orders: READ-ONLY
   - Account summary: READ-ONLY
   - NO order submission
   - NO market data

3. **Execution ASLA yapılmayacak**:
   - HUMAN_ONLY mode sabit
   - Execution layer'a dokunma
   - Broker order API çağrısı YOK

4. **PositionSnapshot Standardize**:
   - account_type field eklendi
   - Algo, pozisyonun kaynağını umursamaz
   - Decision engines account_type'a göre filtreleme yapabilir

5. **IBKR Gateway Connection**:
   - Actual connection implementation is placeholder
   - To be implemented with `ib_insync` or similar
   - Connection logic in `ibkr_connector.py` is ready for implementation

---

## 🔧 Implementation Notes

### IBKR Gateway Connection (TODO)

Current implementation is a placeholder. To implement actual IBKR Gateway / TWS connection:

1. Install `ib_insync`:
   ```bash
   pip install ib_insync
   ```

2. Update `ibkr_connector.py`:
   ```python
   from ib_insync import IB
   
   async def connect(self):
       self._ibkr_client = IB()
       await self._ibkr_client.connect('127.0.0.1', 7497, clientId=1)
       # ...
   ```

3. Implement position retrieval:
   ```python
   async def get_positions(self):
       positions = self._ibkr_client.positions()
       return [
           {
               'symbol': pos.contract.symbol,
               'qty': pos.position,
               'avg_price': pos.averageCost / pos.position if pos.position != 0 else 0,
               'account': pos.account
           }
           for pos in positions
           if pos.account == self.account_type
       ]
   ```

---

## 📈 Sonraki Adımlar

1. ✅ AccountModeManager oluşturuldu
2. ✅ IBKRConnector oluşturuldu (placeholder)
3. ✅ PositionSnapshot account_type field eklendi
4. ✅ PositionSnapshot API güncellendi
5. ✅ API endpoints eklendi
6. ⏳ IBKR Gateway connection implementation (TODO)
7. ⏳ UI integration (frontend)

---

## 🎯 Phase 10 Durumu

**TAMAMLANDI** ✅

- AccountModeManager: ✅
- IBKRConnector (placeholder): ✅
- Unified PositionSnapshot: ✅
- PositionSnapshot API updates: ✅
- API endpoints: ✅
- Documentation: ✅

**IBKR Gateway Connection Implementation**: ⏳ TODO (placeholder ready)

**Sistem artık IBKR ve HAMMER pozisyonlarını algoya bağlayabilir!** 🔌

Trader kendi IBKR hesabında manuel trade ederken, algoritmanın hangi pozisyonlara yöneldiğini kendi gerçek hesabı üzerinden görebilir.




