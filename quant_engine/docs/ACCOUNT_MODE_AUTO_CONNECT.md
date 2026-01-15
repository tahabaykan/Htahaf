# Account Mode Auto-Connect (Phase 10.1 Update)

## 📋 Genel Bakış

Account mode seçildiğinde otomatik olarak IBKR'ye bağlanır veya bağlantıyı kapatır.

**3 Seçenek:**
- **HAM PRO**: Default, otomatik bağlanır (Hammer Pro)
- **IBKR GUN**: Seçildiğinde otomatik IBKR GUN'a bağlanır (port 4001, client_id 19)
- **IBKR PED**: Seçildiğinde otomatik IBKR PED'e bağlanır (port 4002, client_id 21)

---

## 🎯 Davranış

### HAM PRO (Default)

- Açılışta otomatik seçilir
- IBKR bağlantısı yok
- Pozisyonlar Hammer Pro'dan alınır
- Market data Hammer Pro'dan

### IBKR GUN

- Seçildiğinde:
  1. IBKR Gateway'e bağlanır (127.0.0.1:4001, client_id 19)
  2. Pozisyonlar IBKR GUN'dan alınır
  3. Market data yine Hammer Pro'dan (ALWAYS)

### IBKR PED

- Seçildiğinde:
  1. IBKR Gateway'e bağlanır (127.0.0.1:4002, client_id 21)
  2. Pozisyonlar IBKR PED'den alınır
  3. Market data yine Hammer Pro'dan (ALWAYS)

### Mode Değişimi

- **HAM PRO → IBKR GUN/PED**: 
  - IBKR'ye otomatik bağlanır
  - Pozisyonlar IBKR'den alınır

- **IBKR GUN/PED → HAM PRO**: 
  - IBKR bağlantısı kapatılır
  - Pozisyonlar Hammer Pro'dan alınır

- **IBKR GUN → IBKR PED** (veya tersi):
  - Eski IBKR bağlantısı kapatılır
  - Yeni IBKR'ye bağlanır

---

## 🔌 API Endpoints

### Set Account Mode (Auto-Connect)

**POST /api/psfalgo/account/mode**

**Parameters:**
- `mode`: HAMMER_PRO, IBKR_GUN, or IBKR_PED
- `auto_connect`: true (default) - otomatik bağlan

**Example:**
```bash
POST /api/psfalgo/account/mode?mode=IBKR_GUN&auto_connect=true
```

**Response:**
```json
{
  "success": true,
  "old_mode": "HAMMER_PRO",
  "new_mode": "IBKR_GUN",
  "connected": true,
  "connection_info": {
    "success": true,
    "account_type": "IBKR_GUN",
    "host": "127.0.0.1",
    "port": 4001,
    "client_id": 19,
    "connected": true
  }
}
```

### Get Account Mode (with Connection Status)

**GET /api/psfalgo/account/mode**

**Response:**
```json
{
  "success": true,
  "mode": "IBKR_GUN",
  "is_hammer": false,
  "is_ibkr_gun": true,
  "is_ibkr_ped": false,
  "is_ibkr": true,
  "ibkr_gun_connected": true,
  "ibkr_ped_connected": false
}
```

---

## 🚀 Kullanım

### 1. Default (HAM PRO)

Açılışta otomatik:
- Mode: HAMMER_PRO
- Pozisyonlar: Hammer Pro
- IBKR bağlantısı: Yok

### 2. IBKR GUN'a Geçiş

```bash
POST /api/psfalgo/account/mode?mode=IBKR_GUN
```

**Yapılanlar:**
1. Mode → IBKR_GUN
2. IBKR Gateway'e bağlanır (127.0.0.1:4001, client_id 19)
3. Pozisyonlar IBKR GUN'dan alınır
4. Market data Hammer Pro'dan (ALWAYS)

### 3. IBKR PED'e Geçiş

```bash
POST /api/psfalgo/account/mode?mode=IBKR_PED
```

**Yapılanlar:**
1. Mode → IBKR_PED
2. IBKR Gateway'e bağlanır (127.0.0.1:4002, client_id 21)
3. Pozisyonlar IBKR PED'den alınır
4. Market data Hammer Pro'dan (ALWAYS)

### 4. HAM PRO'ya Dönüş

```bash
POST /api/psfalgo/account/mode?mode=HAMMER_PRO
```

**Yapılanlar:**
1. Mode → HAMMER_PRO
2. IBKR bağlantısı kapatılır (eğer açıksa)
3. Pozisyonlar Hammer Pro'dan alınır

---

## ⚠️ Önemli Notlar

1. **IBKR Gateway/TWS Açık Olmalı**:
   - Mode seçmeden önce IBKR Gateway veya TWS açık olmalı
   - Login yapılmış olmalı
   - API erişimi açık olmalı

2. **Port Configuration**:
   - GUN: port 4001 (Gateway) / 7497 (TWS)
   - PED: port 4002 (Gateway) / 7496 (TWS)
   - Default: Gateway ports

3. **Client ID**:
   - GUN: client_id 19
   - PED: client_id 21
   - Aynı client_id ile ikinci bağlantı açılamaz

4. **Market Data ALWAYS from HAMMER**:
   - L1/L2/prints/GRPAN/RWVAP = SADECE HAMMER
   - IBKR sadece pozisyon & emir bilgisi
   - PositionSnapshot'da current_price ALWAYS from HAMMER

5. **Auto-Connect Disable**:
   - `auto_connect=false` ile manuel bağlanabilirsin
   - Ama genelde `auto_connect=true` kullanılır

---

## 🎨 Web UI Önerisi

**3 Seçenek Butonu:**

```
┌─────────────────────────────────────┐
│  TRADING ACCOUNT                    │
├─────────────────────────────────────┤
│  [HAM PRO]  [IBKR GUN]  [IBKR PED] │
│    ✓          ○           ○        │
└─────────────────────────────────────┘
```

**Durum Göstergesi:**

- **HAM PRO**: ✓ (aktif, bağlı değil - Hammer Pro otomatik)
- **IBKR GUN**: 
  - ○ (seçili değil)
  - ✓ (seçili, bağlı)
  - ⚠️ (seçili, bağlantı hatası)
- **IBKR PED**: 
  - ○ (seçili değil)
  - ✓ (seçili, bağlı)
  - ⚠️ (seçili, bağlantı hatası)

**Tıklama Davranışı:**

1. **HAM PRO'ya tıkla**:
   - Mode → HAMMER_PRO
   - IBKR bağlantısı kapatılır (varsa)
   - Pozisyonlar Hammer Pro'dan

2. **IBKR GUN'a tıkla**:
   - Mode → IBKR_GUN
   - IBKR Gateway'e bağlanır (otomatik)
   - Pozisyonlar IBKR GUN'dan

3. **IBKR PED'e tıkla**:
   - Mode → IBKR_PED
   - IBKR Gateway'e bağlanır (otomatik)
   - Pozisyonlar IBKR PED'den

---

## 🔧 Implementation

### Backend Changes

1. **AccountModeManager.set_mode()**: 
   - Artık async
   - `auto_connect` parametresi
   - IBKR'ye otomatik bağlanır/kapatır

2. **API Endpoint**:
   - `POST /api/psfalgo/account/mode` → auto_connect parametresi
   - `GET /api/psfalgo/account/mode` → connection status döner

### Frontend Changes (TODO)

1. **Mode Selector Component**:
   - 3 buton: HAM PRO, IBKR GUN, IBKR PED
   - Aktif mode'u göster
   - Connection status göster

2. **API Integration**:
   - Mode değiştiğinde `POST /api/psfalgo/account/mode` çağır
   - Connection status için `GET /api/psfalgo/account/mode` çağır

---

## 📈 Sonraki Adımlar

1. ✅ Backend auto-connect implementasyonu
2. ✅ API endpoints güncellendi
3. ⏳ Frontend mode selector component
4. ⏳ Connection status indicator
5. ⏳ Error handling UI

---

## 🎯 Durum

**TAMAMLANDI** ✅

- Auto-connect logic: ✅
- API endpoints: ✅
- Documentation: ✅

**Frontend**: ⏳ TODO (Web UI mode selector)

**Sistem artık mode seçildiğinde otomatik IBKR'ye bağlanır!** 🔌




