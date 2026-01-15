# PSFALGO Intentions - Kriter Raporu

## 📋 ÖZET

Bu doküman, PSFALGO Intentions sisteminin **hangi kriterlere baktığını** ve **nasıl intent yarattığını** detaylı olarak açıklar.

---

## 🔍 INTENT YARATMA SÜRECİ

Intent yaratma 3 aşamalıdır:

1. **Decision Engine Kararları** (KARBOTU, REDUCEMORE, ADDNEWPOS)
2. **Risk Check'ler** (MAXALW, Daily Lot Limit, Exposure, Duplicate)
3. **Intent Oluşturma** (Status: PENDING veya REJECTED)

---

## 1️⃣ DECISION ENGINE KRİTERLERİ

### KARBOTU Engine

**Amaç**: Mevcut LONG pozisyonlardan kar almak

**Kriterler**:
- ✅ **GORT Filtresi**: `GORT > 0` (pozisyon GORT'a dahil olmalı)
- ✅ **Fbtot Eşiği**: `Fbtot < 1.10` (kar alma sinyali)
- ✅ **Lot Yüzdesi**: `lot_percentage` (config'den, genelde %20-50)
- ✅ **Cooldown**: Aynı sembol için son karar üzerinden belirli süre geçmeli
- ✅ **Confidence**: Confidence skoru yeterli olmalı

**Intent Yaratma**:
- Decision engine `DecisionResponse` döndürür
- `ExecutionEngine.process_decision_response()` → `ExecutionPlan` oluşturur
- Her `ExecutionIntent` için `Intent` yaratılır

**Intent Alanları**:
- `symbol`: Pozisyon sembolü
- `action`: `SELL` veya `ASK_SELL`
- `qty`: `position.qty * lot_percentage`
- `price`: `ask` veya `GRPAN` bazlı
- `reason_code`: `KARBOTU_TAKE_PROFIT`
- `metric_values`: `{fbtot, sfstot, gort, final_thg, short_final}`

---

### REDUCEMORE Engine

**Amaç**: Daha agresif kar alma (exposure yüksekken)

**Eligibility Kriterleri**:
- ✅ **Exposure Ratio**: `exposure_ratio >= threshold` (genelde 0.7-0.8)
- ✅ **Pot Total**: `pot_total >= threshold` (genelde 500K+)
- ✅ **Exposure Mode**: `DEFANSIF` (yüksek exposure)

**Karar Kriterleri**:
- ✅ **GORT Filtresi**: `GORT > 0` (KARBOTU ile aynı)
- ✅ **Fbtot Eşiği**: `Fbtot < 1.10` (KARBOTU ile aynı)
- ✅ **Lot Yüzdesi**: Daha agresif (genelde %30-60)
- ✅ **Cooldown**: Aynı sembol için son karar üzerinden belirli süre geçmeli
- ✅ **Confidence**: Confidence skoru yeterli olmalı

**Intent Yaratma**:
- Decision engine `DecisionResponse` döndürür
- `ExecutionEngine.process_decision_response()` → `ExecutionPlan` oluşturur
- Her `ExecutionIntent` için `Intent` yaratılır

**Intent Alanları**:
- `symbol`: Pozisyon sembolü
- `action`: `SELL` veya `ASK_SELL`
- `qty`: `position.qty * lot_percentage` (daha yüksek)
- `price`: `ask` veya `GRPAN` bazlı
- `reason_code`: `REDUCEMORE_TAKE_PROFIT`
- `metric_values`: `{fbtot, sfstot, gort, final_thg, short_final}`

---

### ADDNEWPOS Engine

**Amaç**: Yeni LONG pozisyon eklemek

**Eligibility Kriterleri**:
- ✅ **Exposure Ratio**: `exposure_ratio < threshold` (genelde 0.8)
- ✅ **Pot Total**: `pot_total < pot_max` (hala yer var)
- ✅ **Exposure Mode**: `OFANSIF` (düşük exposure)

**Filtreleme Kriterleri**:
- ✅ **Bid Buy Ucuzluk**: `bid_buy_ucuzluk > threshold` (genelde 0.5+)
- ✅ **Fbtot**: `Fbtot > threshold` (genelde 1.0+)
- ✅ **Spread**: `spread_pct < threshold` (genelde 0.5%+)
- ✅ **AVG_ADV**: `avg_adv > threshold` (genelde 10K+)
- ✅ **Port Adjuster Group Cap**: `current_position + proposed_lot <= group_max_lot`
- ✅ **Cooldown**: Aynı sembol için son karar üzerinden belirli süre geçmeli
- ✅ **Confidence**: Confidence skoru yeterli olmalı

**Intent Yaratma**:
- Decision engine `DecisionResponse` döndürür
- `ExecutionEngine.process_decision_response()` → `ExecutionPlan` oluşturur
- Her `ExecutionIntent` için `Intent` yaratılır

**Intent Alanları**:
- `symbol`: Yeni pozisyon sembolü
- `action`: `BUY` veya `ADD`
- `qty`: `calculated_lot` (Port Adjuster group cap'a göre)
- `price`: `bid` veya `GRPAN` bazlı
- `reason_code`: `ADDNEWPOS_BUY`
- `metric_values`: `{fbtot, sfstot, gort, final_thg, short_final}`

---

## 2️⃣ RISK CHECK KRİTERLERİ

Her intent yaratıldığında **4 risk check** çalışır:

### 1. MAXALW (Company-Based Order Limit)

**Formül**: `min(3, max(1, round(total_stocks_for_company / 3)))`

**Kontrol**:
- Aynı şirketten (örn: "INN PRE", "INN PRF" → "INN") kaç aktif intent var?
- `active_company_intents < max_allowed` olmalı

**Örnek**:
- INN şirketinden 5 hisse var → `max_allowed = min(3, max(1, round(5/3))) = 2`
- Eğer zaten 2 aktif intent varsa → **FAIL**

**Risk FAIL Sonucu**:
- Intent yaratılır ama `status = REJECTED`
- `rejected_reason`: "Company limit exceeded: 2/2 active intents for INN"

---

### 2. Daily Lot Limit

**Limit**: `±600 lot` per symbol per day

**Kontrol**:
- Bugün bu sembol için toplam kaç lot emir verildi?
- `abs(current_total + new_qty) <= 600` olmalı

**Örnek**:
- Bugün "INN PRE" için 500 lot BUY verildi
- Yeni intent: 150 lot BUY
- `500 + 150 = 650 > 600` → **FAIL**

**Risk FAIL Sonucu**:
- Intent yaratılır ama `status = REJECTED`
- `rejected_reason`: "Daily lot limit exceeded: 650 > 600 for INN PRE (BUY)"

**NOT**: Şu an `daily_limits` tracking henüz tam implement edilmedi (TODO)

---

### 3. Exposure Limit

**Kontrol**:
- Mevcut exposure: `pot_total`
- Max exposure: `pot_max`
- Yeni intent'in exposure'ı: `qty * price`
- `new_pot_total <= pot_max` olmalı

**Örnek**:
- `pot_total = 400,000`
- `pot_max = 500,000`
- Yeni intent: 100 lot × $20 = $2,000
- `400,000 + 2,000 = 402,000 <= 500,000` → **PASS**

**Risk FAIL Sonucu**:
- Intent yaratılır ama `status = REJECTED`
- `rejected_reason`: "Exposure limit exceeded: 502,000 > 500,000"

---

### 4. Duplicate Intent Check

**Kontrol**:
- Aynı `symbol` + `action` kombinasyonu
- Status: `PENDING` veya `APPROVED`
- TTL içinde (90 saniye)

**Örnek**:
- 30 saniye önce "INN PRE BUY" intent yaratıldı (PENDING)
- Yeni intent: "INN PRE BUY" → **FAIL** (duplicate)

**Risk FAIL Sonucu**:
- Intent yaratılır ama `status = REJECTED`
- `rejected_reason`: "Duplicate intent found: abc-123 (created 2025-12-16 01:42:00)"

**NOT**: EXPIRED intent'ler duplicate sayılmaz (TTL dışında)

---

## 3️⃣ INTENT OLUŞTURMA

### Risk Check Sonuçları

**Tüm Risk Check'ler PASS**:
- `status = PENDING`
- `risk_passed = True`
- Intent UI'da görünür, approve edilebilir

**Herhangi Bir Risk Check FAIL**:
- `status = REJECTED`
- `risk_passed = False`
- `rejected_reason`: Tüm FAIL eden check'lerin reason'ları birleştirilir
- Intent UI'da görünür ama approve edilemez (kırmızı)

---

## 📊 METRIC VALUES

Her intent'te şu metric'ler saklanır:

```python
metric_values = {
    'fbtot': float,        # Final Buy Total (ucuzluk skoru)
    'sfstot': float,       # Short Final Total (pahalılık skoru)
    'gort': float,         # Group Ortalama (benchmark)
    'final_thg': float,    # Final THG (long sinyali)
    'short_final': float   # Short Final (short sinyali)
}
```

Bu değerler intent yaratıldığı andaki market snapshot'tan alınır.

---

## ⏱️ TTL (Time To Live)

**TTL**: 90 saniye

**Başlangıç**: Intent yaratıldığı anda (`timestamp`)

**Expiration**:
- TTL dolunca → `status = EXPIRED`
- EXPIRED intent'ler execute edilmez
- UI'da gri renkte görünür

**Background Task**:
- Her 10 saniyede bir `check_and_expire_intents()` çalışır
- EXPIRED intent'ler otomatik işaretlenir

---

## 🎯 SONUÇ

**Intent Yaratma Akışı**:

```
Decision Engine (KARBOTU/REDUCEMORE/ADDNEWPOS)
    ↓
ExecutionEngine.process_decision_response()
    ↓
ExecutionPlan.intents
    ↓
Her ExecutionIntent için:
    ↓
Intent oluştur (status = PENDING)
    ↓
Risk Check'ler çalıştır:
    - MAXALW
    - Daily Lot Limit
    - Exposure Limit
    - Duplicate Check
    ↓
Risk Check Sonuçları:
    - Tüm PASS → status = PENDING ✅
    - Herhangi biri FAIL → status = REJECTED ❌
    ↓
IntentStore.add_intent()
    ↓
UI'da görünür (PENDING = sarı, REJECTED = kırmızı)
```

---

## 📝 NOTLAR

1. **Daily Limits Tracking**: Şu an `daily_limits` dict'i track edilmiyor (TODO)
2. **Auto-approve**: FULL_AUTO modunda bile şimdilik manuel onay gerekiyor
3. **WebSocket Broadcast**: Intent status değişiklikleri WebSocket üzerinden broadcast edilmeli (TODO)
4. **ExecutionRouter**: Sadece APPROVED intent'ler ExecutionRouter'a gidiyor

---

## 🔍 DEBUGGING

**Intent yaratılmıyorsa kontrol et**:
1. Decision engine çalışıyor mu? (KARBOTU/REDUCEMORE/ADDNEWPOS eligibility)
2. Decision engine karar üretiyor mu? (`DecisionResponse.decisions` boş mu?)
3. ExecutionEngine plan oluşturuyor mu? (`ExecutionPlan.intents` boş mu?)
4. Risk check'ler tüm intent'leri REJECT mi ediyor?

**Log'larda bakılacak yerler**:
- `[RUNALL] KARBOTU intents created: X intents (pending: Y, rejected: Z)`
- `[RUNALL] REDUCEMORE intents created: X intents (pending: Y, rejected: Z)`
- `[RUNALL] ADDNEWPOS intents created: X intents (pending: Y, rejected: Z)`
- `[RUNALL] ... intent REJECTED (risk check failed): ...`





