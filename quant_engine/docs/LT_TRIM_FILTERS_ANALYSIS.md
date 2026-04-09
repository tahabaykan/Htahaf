# LT_TRIM Engine - Tüm Filtreler Analizi

## 🔴 SORUN: LT_TRIM Önerileri Çıkmıyor

### LT_TRIM Engine'deki TÜM FİLTRELER (13 Adet)

#### 1. **Global Enable Check** (Satır 129)
```python
if not controls.lt_trim_enabled:
    return [], diagnostic  # ❌ TAMAMEN KAPALI
```
**Etkisi**: Engine tamamen devre dışı kalır.

---

#### 2. **Dust Filter** (Satır 139)
```python
if abs(qty) < 1:
    continue  # ❌ 1 lot'tan küçük position'lar skip
```
**Etkisi**: Çok küçük position'lar işlenmez (normal).

---

#### 3. **Strategy Type Filter** (Satır 144)
```python
if getattr(position, 'strategy_type', 'LT') != 'LT':
    continue  # ❌ Sadece LT position'ları işlenir
```
**Etkisi**: MM position'ları skip edilir (normal).

---

#### 4. **✅ ORIGIN TYPE FİLTRESİ - MANTIKLI!** (Satır 148)
```python
if getattr(position, 'origin_type', 'INT') != 'OV':
    continue  # ✅ Sadece OV (Overnight) position'ları işlenir
```
**MANTIK**: Bu filtre mantıklı!
- **OV (Overnight)**: Befday'de olan position'lar (dün akşam kalan) → LT_TRIM ile trim edilmeli
- **INT (Intraday)**: Bugün açılan position'lar → REV order mekanizması zaten çalışmış olmalı
- **Sonuç**: INT position'lar REV order ile yönetiliyor, LT_TRIM'e gerek yok

**KARBOTU vs LT_TRIM Farkı**:
- **KARBOTU**: Tüm position'ları işler (signal üretir)
- **LT_TRIM**: Sadece OV position'ları işler (execution engine, REV order'dan önce)

---

#### 5. **MM Position Tag Filter** (Satır 154)
```python
if 'MM' in pos_tag.upper():
    continue  # ❌ MM tag'li position'lar skip
```
**Etkisi**: MM position'ları skip edilir (normal, zaten strategy_type'da da var).

---

#### 6. **Side Enable Filter** (Satır 159-164)
```python
if is_long and not controls.lt_trim_long_enabled:
    continue  # ❌ LONG side kapalıysa skip
if not is_long and not controls.lt_trim_short_enabled:
    continue  # ❌ SHORT side kapalıysa skip
```
**Etkisi**: Long/Short side'lar ayrı ayrı enable/disable edilebilir.

---

#### 7. **Metrics Check** (Satır 168)
```python
metric = request.metrics.get(symbol)
if not metric:
    continue  # ❌ Metrics yoksa skip
```
**Etkisi**: Symbol için metrics yoksa işlenmez (normal).

---

#### 8. **Score Check** (Satır 243)
```python
if score is None:
    return [], [], debug_info  # ❌ Score yoksa skip
```
**Etkisi**: Score hesaplanamazsa intent üretilmez.

---

#### 9. **Safety Floor Filter** (Satır 248)
```python
SAFE_FLOOR = -0.08
if is_long and score < SAFE_FLOOR:
    return [], [f"SCORE_TOO_LOW"], debug_info  # ❌ Score çok düşükse skip
```
**Etkisi**: LONG için score < -0.08 ise skip (güvenlik filtresi).

---

#### 10. **L1 Data Check** (Satır 268)
```python
if bid <= 0 or ask <= 0:
    return [], ["BAD_L1_DATA"], debug_info  # ❌ Bid/Ask yoksa skip
```
**Etkisi**: Market data yoksa işlenmez (normal).

---

#### 11. **Stage Triggers Check** (Satır 347)
```python
if flags_triggered == 0:
    return [], ["NO_STAGES_MET"], debug_info  # ❌ Hiç stage trigger olmamışsa skip
```
**Etkisi**: 
- **Small Position (< 400)**: Stage 2 veya Stage 3 trigger olmalı
- **Standard Position (>= 400)**: Stage 1, 2, 3 veya 4'ten en az biri trigger olmalı

---

#### 12. **Needed Sell Qty Check** (Satır 364)
```python
if needed_sell_qty > 0:
    # ... intent oluştur
```
**Etkisi**: Trim gereksinimi yoksa (needed_sell_qty <= 0) intent üretilmez.

---

#### 13. **Final Trim Qty Check** (Satır 377)
```python
if final_trim_qty > 0:
    intents.append(...)  # ❌ Final qty 0 ise intent eklenmez
```
**Etkisi**: Final hesaplanan qty 0 ise intent üretilmez.

---

## 🔴 KARBOTU vs LT_TRIM Filtre Karşılaştırması

### KARBOTU Engine Filtreleri:
1. ✅ **Global Enable**: `controls.karbotu_enabled`
2. ✅ **Dust Filter**: `abs(qty) < 1`
3. ✅ **Strategy Type**: `strategy_type == 'LT'` (muhtemelen)
4. ❌ **Origin Type**: **YOK!** (Tüm position'ları işler)
5. ✅ **Metrics Check**: Metrics yoksa skip
6. ✅ **Step Filters**: FBTOT, GORT, SMA63Chg, pahalilik (configurable)

### LT_TRIM Engine Filtreleri:
1. ✅ **Global Enable**: `controls.lt_trim_enabled`
2. ✅ **Dust Filter**: `abs(qty) < 1`
3. ✅ **Strategy Type**: `strategy_type == 'LT'`
4. 🔴 **Origin Type**: `origin_type == 'OV'` **← ÇOK KISITLAYICI!**
5. ✅ **MM Tag Filter**: `'MM' in pos_tag`
6. ✅ **Side Enable**: `lt_trim_long_enabled` / `lt_trim_short_enabled`
7. ✅ **Metrics Check**: Metrics yoksa skip
8. ✅ **Score Check**: Score yoksa skip
9. ✅ **Safety Floor**: Score < -0.08 ise skip
10. ✅ **L1 Data Check**: Bid/Ask yoksa skip
11. ✅ **Stage Triggers**: En az 1 stage trigger olmalı
12. ✅ **Needed Sell Qty**: needed_sell_qty > 0 olmalı
13. ✅ **Final Trim Qty**: final_trim_qty > 0 olmalı

---

## 🎯 ÇÖZÜM ÖNERİLERİ

### 1. **✅ Origin Type Filtresi Mantıklı - Değiştirilmedi**
```python
# MANTIKLI: Sadece OV position'ları işle
if getattr(position, 'origin_type', 'INT') != 'OV':
    continue  # INT position'lar REV order ile yönetiliyor
```
**NEDEN**: 
- INT position'lar için REV order mekanizması zaten çalışmış olmalı
- LT_TRIM sadece dün akşam kalan (OV) position'ları trim etmeli
- Bu filtre doğru, değiştirilmedi

### 2. **Stage Triggers Filtresini Yumuşat**
```python
# ŞU ANKİ: flags_triggered == 0 ise skip
# ÖNERİ: Minimum 1 stage yerine, spread gating'i daha esnek yap
```

### 3. **Safety Floor Filtresini Kontrol Et**
```python
# ŞU ANKİ: score < -0.08 ise skip
# Bu çok kısıtlayıcı olabilir, özellikle spread gating'de
```

---

## 📊 LOG'LARDA GÖRÜLEN DURUM

Log'larda `[DEBUG LT_TRIM]` mesajları var, yani:
- ✅ Engine çalışıyor
- ✅ `_evaluate_trim` çağrılıyor
- ❌ Ama intents üretilmiyor veya conflict resolution'da kayboluyor

**Muhtemel Nedenler**:
1. **Origin Type Filtresi**: Position'ların çoğu `origin_type='INT'` olabilir
2. **Stage Triggers**: Hiç stage trigger olmamış olabilir
3. **Conflict Resolution**: LT_TRIM intents'leri KARBOTU ile conflict olup filtreleniyor olabilir

---

## 🔧 HEMEN YAPILACAKLAR

1. **Origin Type filtresini kaldır** (KARBOTU gibi)
2. **Log ekle**: Kaç intent üretildi, conflict resolution'da ne oldu
3. **Stage trigger logic'i kontrol et**: Neden trigger olmuyor?

