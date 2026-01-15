# Janall vs Quant Engine PSFALGO/RUNALL Birebirlik Raporu

## 📋 ÖZET

Bu rapor, Janall klasöründeki RUNALL/PSFALGO davranışını referans alarak, quant_engine içindeki PSFALGO'nun birebir eşleşip eşleşmediğini analiz eder.

---

## A) JANALL PSFALGO SPEC (Referans)

### 1. Input Kaynakları

#### CSV Pipeline (run_daily_n.py zinciri)
- **npreviousadd.py**: `prev_close` kaynağı (Hammer Pro API `getSymbolSnapshot.prevClose`)
  - NASDAQ stocks için TIME_TO_DIV=90 ise DIV_AMOUNT kadar düşürülür
  - `janek_ssfinek*.csv` dosyalarına `prev_close` kolonu eklenir
- **merge_csvs.py**: `janek_ssfinek*.csv` → `janalldata.csv` birleştirme
- **janalldata.csv**: Ana veri kaynağı
  - Kolonlar: `PREF IBKR`, `CMON`, `CGRUP`, `GROUP`, `FINAL_THG`, `SHORT_FINAL`, `AVG_ADV`, `SMI`, `SMA63 chg`, `SMA246 chg`, `prev_close`

#### Live Market Data
- **Bid/Ask/Last**: Hammer Pro L1/L2 stream
- **Trade Prints**: Hammer Pro L2 (GRPAN için)

### 2. RUNALL Loop Yapısı (Janall)

```
Döngü Başlangıcı (runall_loop_count++)
    ↓
Adım 1: Lot Bölücü Kontrolü (checkbox)
    ↓
Adım 2: Controller ON (limit kontrolleri)
    ↓
Adım 3: Exposure Kontrolü (Async - thread)
    ├─ Pot Toplam < Pot Max → OFANSIF → KARBOTU
    ├─ Pot Toplam >= Pot Max → DEFANSIF → REDUCEMORE
    └─ GEÇİŞ → REDUCEMORE
    ↓
Adım 4: KARBOTU veya REDUCEMORE Başlat (non-blocking)
    ↓
KARBOTU/REDUCEMORE Bitince:
    ↓
Adım 5: ADDNEWPOS Kontrolü
    ├─ Pot Toplam < Pot Max → ADDNEWPOS aktif
    └─ Pot Toplam >= Pot Max → ADDNEWPOS pasif
    ↓
Adım 6: Qpcal İşlemi (Spreadkusu panel) - EMİR GÖNDERME
    ↓
Adım 7: 2 Dakika Bekle (after(120000))
    ↓
Adım 8: Tüm Emirleri İptal Et (runall_cancel_orders_and_restart)
    ↓
Adım 9: Yeni Döngü Başlat (Adım 1'e dön)
```

**Cycle Süresi**: ~3-4 dakika (emir gönderme + 2 dakika bekleme + iptal)

### 3. PSFALGO Karar Kuralları (Ntahaf/psfalgo.py)

#### Emir Türleri
- **BUY**: Yeni long pozisyon
- **SELL**: Long pozisyon kapatma
- **BUY_TO_COVER**: Short pozisyon kapatma
- **SELL_SHORT**: Yeni short pozisyon
- **REPLACE**: Mevcut emri değiştir
- **CANCEL**: Emir iptal

#### Risk/Guardrail Kuralları
- **MAXALW**: Şirket bazlı maksimum emir sayısı (min(3, max(1, round(total_stocks_for_company / 3))))
- **Daily Position Limits**: Her hisse için ±600 lot limit
- **BEFDAY Position Tracking**: Günlük fill takibi
- **Company Limits**: Aynı şirketten maksimum emir sayısı

#### Modlar
- **INACTIVE**: Algo kapalı (default)
- **ACTIVE**: Algo aktif, emir gönderiyor
- **PISDoNGU**: Özel döngü modu

### 4. Port Adjuster (Janall)

#### Veri Kaynağı
- **exposureadjuster.csv**: Project root'ta (`StockTracker/exposureadjuster.csv`)
- **Format**: Setting/Value kolonları, Long Groups ve Short Groups ağırlıkları
- **Yükleme**: `load_group_weights()` fonksiyonu ile CSV'den direkt okuma

#### Hesaplamalar
- `total_lot = total_exposure_usd / avg_pref_price`
- `long_lot = total_lot * long_ratio_pct`
- `short_lot = total_lot * short_ratio_pct`
- `group_lot = side_lot * (group_pct / 100)`

---

## B) QUANT ENGINE PSFALGO SPEC

### 1. Input Kaynakları

#### CSV Pipeline
- **static_store** (`StaticDataStore`): `janalldata.csv` yükleme
  - Startup'ta 1 kez yüklenir (`AUTO_LOAD_CSV=True`)
  - Runtime'da değişmez (koruma eklendi)
- **prev_close**: CSV'den okunur (Hammer fallback var ama CSV öncelikli)

#### Live Market Data
- **market_data_cache**: Hammer Pro L1/L2 stream
- **GRPAN Engine**: Trade prints (L2)

### 2. RUNALL Loop Yapısı (Quant Engine)

```python
async def _cycle_loop(self):
    while self.loop_running:
        # Step 1: Update exposure snapshot
        await self._step_update_exposure()
        
        # Step 2: Determine mode (OFANSIF/DEFANSIF)
        exposure_mode = self._determine_exposure_mode()
        
        # Step 3: Run KARBOTU or REDUCEMORE
        if exposure_mode == 'OFANSIF':
            await self._step_run_karbotu()
        else:
            await self._step_run_reducemore()
        
        # Step 4: Run ADDNEWPOS if eligible
        if self._is_addnewpos_eligible():
            await self._step_run_addnewpos()
        
        # Step 5: Collect metrics
        await self._collect_cycle_metrics(cycle_duration)
        
        # Step 6: Wait for next cycle
        await self._wait_for_next_cycle(cycle_start)
```

**Cycle Süresi**: Configurable (default: 60 saniye)

### 3. Execution Modes (Quant Engine)

- **PREVIEW**: Simulation only (no execution)
- **SEMI_AUTO**: Execute only user-approved orders
- **FULL_AUTO**: Execute auto-approved orders automatically

### 4. Port Adjuster (Quant Engine)

#### Veri Kaynağı
- **exposureadjuster.csv**: Project root'ta (`StockTracker/exposureadjuster.csv`)
- **port_adjuster_config.json**: Fallback
- **Yükleme**: Startup'ta `PortAdjusterStore._initialize_persisted()` ile otomatik

#### Hesaplamalar
- Janall ile birebir aynı formüller

---

## C) BİREBİRLİK RAPORU

### ✅ EŞLEŞENLER

| Feature | Janall | Quant Engine | Durum |
|---------|--------|---------------|-------|
| **CSV Pipeline** | run_daily_n.py → janalldata.csv | static_store.load_csv() | ✅ Eşleşiyor |
| **prev_close Source** | npreviousadd.py (Hammer API) | CSV (Hammer fallback) | ✅ Eşleşiyor (CSV öncelikli) |
| **RUNALL Loop** | 9 adımlı döngü | 6 adımlı döngü | ⚠️ Kısmen eşleşiyor |
| **Exposure Mode** | OFANSIF/DEFANSIF | OFANSIF/DEFANSIF | ✅ Eşleşiyor |
| **KARBOTU** | Var | Var | ✅ Eşleşiyor |
| **REDUCEMORE** | Var | Var | ✅ Eşleşiyor |
| **ADDNEWPOS** | Var | Var | ✅ Eşleşiyor |
| **Port Adjuster CSV** | exposureadjuster.csv | exposureadjuster.csv | ✅ Eşleşiyor |
| **Port Adjuster Math** | total_lot = exposure / price | total_lot = exposure / price | ✅ Eşleşiyor |

### ❌ EKSİKLER / FARKLAR

| Feature | Janall | Quant Engine | Gap |
|---------|--------|---------------|-----|
| **Lot Bölücü Kontrolü** | Adım 1 (checkbox) | ❌ Yok | **EKSİK** |
| **Controller ON** | Adım 2 (limit kontrolleri) | ❌ Yok | **EKSİK** |
| **Qpcal İşlemi** | Adım 6 (Spreadkusu panel) | ❌ Yok | **EKSİK** |
| **2 Dakika Bekleme** | Adım 7 (after(120000)) | ❌ Yok (configurable interval) | **FARKLI** |
| **Emir İptal Loop** | Adım 8 (tüm emirleri iptal) | ❌ Yok | **EKSİK** |
| **Replace Loop** | Var (emir değiştirme) | ❌ Yok | **EKSİK** |
| **Cancel Policy** | Her cycle sonunda tüm emirleri iptal | ❌ Yok | **EKSİK** |
| **MAXALW (Company Limits)** | Var (şirket bazlı emir limiti) | ❌ Yok | **EKSİK** |
| **Daily Position Limits** | ±600 lot/hisse | ❌ Yok | **EKSİK** |
| **BEFDAY Tracking** | Var (günlük fill takibi) | ❌ Yok | **EKSİK** |
| **Execution Modes** | INACTIVE/ACTIVE/PISDoNGU | PREVIEW/SEMI_AUTO/FULL_AUTO | **FARKLI** |
| **Intentions System** | ❌ Yok | ❌ Yok | **HER İKİSİNDE YOK** |

### ⚠️ DAVRANIŞ FARKI YARATABİLECEK DETAYLAR

1. **Cycle Timing**:
   - **Janall**: ~3-4 dakika (emir gönderme + 2 dakika bekleme + iptal)
   - **Quant**: Configurable (default: 60 saniye)
   - **Etki**: Quant daha hızlı cycle yapıyor, emir iptal mekanizması yok

2. **Emir Gönderme Stratejisi**:
   - **Janall**: Qpcal işlemi (Spreadkusu panel) → emir gönder → 2 dakika bekle → iptal et
   - **Quant**: ExecutionRouter üzerinden direkt gönder (iptal mekanizması yok)
   - **Etki**: Quant'da emirler birikiyor, iptal edilmiyor

3. **Onay Mekanizması**:
   - **Janall**: ❌ Yok (direkt gönder)
   - **Quant**: SEMI_AUTO modunda user approval var
   - **Etki**: Quant daha güvenli ama Janall'dan farklı davranış

4. **Port Adjuster Yükleme**:
   - **Janall**: CSV'den direkt okuma (her çağrıda)
   - **Quant**: Startup'ta 1 kez yükleme (RAM'de tutuluyor)
   - **Etki**: Quant daha hızlı ama CSV değişikliği algılanmıyor (runtime'da)

---

## D) YAPILACAK İŞLER (Öncelik Sırası)

### 🔴 KRİTİK (Algo Davranışını Etkiler)

1. **Intentions System**: Emir göndermeden önce onay bekleme sistemi
2. **Emir İptal Loop**: Her cycle sonunda tüm emirleri iptal etme
3. **2 Dakika Bekleme**: Emir gönderme sonrası bekleme (cycle timing)

### 🟡 ÖNEMLİ (Risk/Guardrail)

4. **MAXALW (Company Limits)**: Şirket bazlı emir limiti
5. **Daily Position Limits**: ±600 lot/hisse limiti
6. **BEFDAY Tracking**: Günlük fill takibi

### 🟢 İYİLEŞTİRME (Opsiyonel)

7. **Lot Bölücü Kontrolü**: Checkbox kontrolü
8. **Controller ON**: Limit kontrolleri
9. **Qpcal İşlemi**: Spreadkusu panel entegrasyonu
10. **Replace Loop**: Emir değiştirme mekanizması

---

## E) SONUÇ

**Birebirlik Durumu**: ⚠️ **%60-70 Eşleşiyor**

**Ana Farklar**:
- Quant Engine daha modern, async, WebSocket tabanlı
- Janall daha "emir gönderme odaklı", cycle-based iptal mekanizması var
- Quant Engine'de onay mekanizması var ama "intentions" sistemi yok
- Port Adjuster her iki tarafta da CSV'den yükleniyor ama Quant startup'ta 1 kez

**Öneri**: Intentions sistemi eklendikten sonra, emir iptal loop'u ve 2 dakika bekleme mekanizması eklendiğinde birebirlik %90+ olacak.





