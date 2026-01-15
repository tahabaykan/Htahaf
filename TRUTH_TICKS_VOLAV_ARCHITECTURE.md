# 🎯 Truth Ticks & Volav Architecture - Detaylı Açıklama

## 📋 İçindekiler
1. [Truth Ticks Nedir?](#1-truth-ticks-nedir)
2. [Volav (Volume-Averaged Levels) Nedir?](#2-volav-volume-averaged-levels-nedir)
3. [Timeframe-First Architecture](#3-timeframe-first-architecture)
4. [AVG_ADV'nin Rolü](#4-avg_advnin-rolü)
5. [Volav Hesaplama Süreci](#5-volav-hesaplama-süreci)
6. [Volav1 Start/End ve Displacement](#6-volav1-startend-ve-displacement)
7. [State Classification (10-State Model)](#7-state-classification-10-state-model)
8. [Örnek Senaryo](#8-örnek-senaryo)

---

## 1. Truth Ticks Nedir?

### 🎯 Amaç
**Truth Ticks**, illiquid preferred stock'larda **GERÇEK** fiyat hareketini yakalamak için kullanılan filtreleme sistemidir.

### ✅ Truth Tick Kriterleri

#### 1.1 Minimum Size (Lot)
```
size >= 20 lot
```
- **Neden?** Küçük lot'lar (1-19 lot) genelde noise'dur, gerçek flow'u temsil etmez
- **Örnek:** 5 lot'luk bir print → ❌ Truth Tick değil
- **Örnek:** 25 lot'luk bir print → ✅ Truth Tick

#### 1.2 Exchange (Venue) Filtreleme
```
FNRA (FINRA) Exchange:
  - size == 100 lot → ✅ Truth Tick
  - size == 200 lot → ✅ Truth Tick
  - size == 50 lot → ❌ Truth Tick değil (FNRA'da sadece 100/200 lot geçerli)

Diğer Exchange'ler (NYSE, ARCA, NASDAQ, vb.):
  - size >= 20 lot → ✅ Truth Tick
```

**Neden?** FNRA'da 100/200 lot dışındaki print'ler genelde test/error'dur.

#### 1.3 Örnek Truth Tick Filtreleme
```
Tüm Print'ler:
- $22.25 × 5 lot (NYSE) → ❌ Truth Tick değil (size < 20)
- $22.26 × 25 lot (NYSE) → ✅ Truth Tick
- $22.27 × 50 lot (FNRA) → ❌ Truth Tick değil (FNRA'da 50 lot geçersiz)
- $22.28 × 100 lot (FNRA) → ✅ Truth Tick
- $22.29 × 200 lot (FNRA) → ✅ Truth Tick
- $22.30 × 150 lot (ARCA) → ✅ Truth Tick
```

---

## 2. Volav (Volume-Averaged Levels) Nedir?

### 🎯 Amaç
**Volav**, fiyat seviyelerinde **volume konsantrasyonunu** bulmak için kullanılır. Hangi fiyat seviyelerinde **gerçek işlem hacmi** var?

### 📊 Volav = Volume Weighted Average Price (VWAP) Cluster

**Volav1**: En yüksek volume'lu fiyat seviyesi  
**Volav2**: İkinci en yüksek volume'lu fiyat seviyesi  
**Volav3**: Üçüncü en yüksek volume'lu fiyat seviyesi  
**Volav4**: Dördüncü en yüksek volume'lu fiyat seviyesi

### 🔑 Önemli Konsept
**Volav, tick sayısına değil, VOLUME'a göre sıralanır!**

**Örnek:**
```
Bucket A: 10 tick × 20 lot = 200 lot toplam → VWAP = $22.25
Bucket B: 2 tick × 500 lot = 1,000 lot toplam → VWAP = $22.30

→ Bucket B, Volav1 olur (daha yüksek volume)
→ Bucket A, Volav2 olur (daha düşük volume)
```

---

## 3. Timeframe-First Architecture

### 🎯 Amaç
Tüm semboller **aynı zaman aralığında** analiz edilir. Her sembol için farklı implicit timeframe'ler kullanılmaz.

### ⏰ Timeframe'ler (Trading Hours Bazlı)

#### 3.1 TF_4H (Last 4 Trading Hours)
```
Örnek: Cuma 16:00 ET (Market Close)
- effective_now = Cuma 16:00 ET
- timeframe_start = Cuma 12:00 ET (son 4 trading hours)
- Aralık: Cuma 12:00 - 16:00 ET
```

#### 3.2 TF_1D (Last 1 Trading Day)
```
Örnek: Cuma 16:00 ET (Market Close)
- effective_now = Cuma 16:00 ET
- timeframe_start = Cuma 09:30 ET (market open)
- Aralık: Cuma 09:30 - 16:00 ET (tüm trading day)
```

#### 3.3 TF_3D (Last 3 Trading Days)
```
Örnek: Cuma 16:00 ET
- effective_now = Cuma 16:00 ET
- timeframe_start = Çarşamba 09:30 ET (3 trading day öncesi)
- Aralık: Çarşamba 09:30 - Cuma 16:00 ET
```

#### 3.4 TF_5D (Last 5 Trading Days)
```
Örnek: Cuma 16:00 ET
- effective_now = Cuma 16:00 ET
- timeframe_start = Pazartesi 09:30 ET (5 trading day öncesi)
- Aralık: Pazartesi 09:30 - Cuma 16:00 ET
```

### 🔑 Effective Now Kavramı
```
Market Açık → effective_now = gerçek zaman
Market Kapalı → effective_now = son trading day close time
```

**Örnek (Hafta Sonu):**
```
Şu an: Cumartesi 10:00 ET
- effective_now = Cuma 16:00 ET (son trading day close)
- TF_1D = Cuma 09:30 - 16:00 ET (son trading day)
- TF_4H = Cuma 12:00 - 16:00 ET (son 4 trading hours)
```

---

## 4. AVG_ADV'nin Rolü

### 🎯 Amaç
**AVG_ADV (Average Daily Volume)**, tüm hesaplamaları **normalize eder** ve **dinamik threshold'lar** sağlar.

### 📊 AVG_ADV Bazlı Parametreler

#### 4.1 Bucket Size (Fiyat Gruplama Aralığı)
```
AVG_ADV >= 100,000 → bucket_size = $0.03 (3 cent)
AVG_ADV >= 80,000  → bucket_size = $0.03
AVG_ADV >= 50,000  → bucket_size = $0.05 (5 cent)
AVG_ADV >= 30,000  → bucket_size = $0.05
AVG_ADV >= 20,000  → bucket_size = $0.05
AVG_ADV >= 10,000  → bucket_size = $0.07 (7 cent)
AVG_ADV >= 3,000   → bucket_size = $0.09 (9 cent)
AVG_ADV < 3,000     → bucket_size = $0.09
```

**Neden?** Likit ürünlerde daha küçük bucket (daha hassas), illiquid ürünlerde daha büyük bucket.

#### 4.2 Min Volav Gap (Minimum Volav Mesafesi)
```
AVG_ADV >= 100,000 → min_gap = $0.03
AVG_ADV >= 80,000  → min_gap = $0.04
AVG_ADV >= 50,000  → min_gap = $0.05
AVG_ADV >= 30,000  → min_gap = $0.06
AVG_ADV >= 20,000  → min_gap = $0.07
AVG_ADV >= 10,000  → min_gap = $0.09
AVG_ADV >= 3,000   → min_gap = $0.11
AVG_ADV < 3,000    → min_gap = $0.15
```

**Neden?** İki Volav arasında minimum mesafe olmalı, aksi halde aynı seviye sayılır.

#### 4.3 Merge Threshold (Birleştirme Eşiği)
```
merge_threshold = min_gap * 0.6
```

**Örnek:**
```
AVG_ADV = 15,000:
  - min_gap = $0.09
  - merge_threshold = $0.09 * 0.6 = $0.054

AVG_ADV = 2,500:
  - min_gap = $0.15
  - merge_threshold = $0.15 * 0.6 = $0.09
```

**Neden?** İki Volav birbirine çok yakınsa (gap < merge_threshold), birleştirilir.

#### 4.4 ADV Fraction (Volume Normalizasyonu)
```
adv_fraction = truth_volume / avg_adv
adv_percent = adv_fraction * 100
```

**Örnek:**
```
AVG_ADV = 10,000
truth_volume = 5,000 lot
adv_fraction = 5,000 / 10,000 = 0.5 (50% of avg_adv)
```

**Neden?** Mutlak volume değil, **relative volume pressure** önemli.

---

## 5. Volav Hesaplama Süreci

### 🔄 Adım Adım Süreç

#### Adım 1: Bucket Aggregation (Gruplama)
```
Tüm Truth Ticks → Bucket'lara grupla

Örnek (bucket_size = 0.07):
- $22.20 → bucket_key = round(22.20/0.07)*0.07 = 22.18
- $22.22 → bucket_key = 22.18 (aynı bucket)
- $22.25 → bucket_key = 22.25 (farklı bucket)
- $22.27 → bucket_key = 22.25 (aynı bucket)
- $22.30 → bucket_key = 22.30 (farklı bucket)
```

#### Adım 2: Bucket VWAP Hesaplama
```
Her bucket için:
- bucket_volume = bucket içindeki tüm tick'lerin size toplamı
- bucket_price_sum = sum(price × size)
- bucket_vwap = bucket_price_sum / bucket_volume
```

**Örnek:**
```
Bucket 22.18:
- $22.20 × 50 lot = 1,110
- $22.22 × 30 lot = 666.6
- Toplam: 80 lot, toplam = 1,776.6
- VWAP = 1,776.6 / 80 = $22.208
```

#### Adım 3: Volume Bazlı Sıralama
```
Bucket'ları volume'a göre azalan sırada sırala:
1. Bucket 22.25: 800 lot
2. Bucket 22.30: 500 lot
3. Bucket 22.18: 80 lot
```

#### Adım 4: Volav Range Hesaplama (YENİ!)
```
Her bucket için:
- Volav center = bucket VWAP
- Volav range = center ± bucket_size/2

Örnek (bucket_size = 0.07):
- Volav center = $22.25
- Volav range = $22.25 ± 0.035 = $22.215 - $22.285
```

#### Adım 5: Range İçindeki Tüm Tick'leri Bul
```
Volav range içindeki TÜM tick'leri bul (bucket sınırı yok):
- $22.215 - $22.285 aralığındaki tüm tick'ler → Volav'a dahil
```

**Örnek:**
```
Volav range: $22.215 - $22.285
Tick'ler:
- $22.20 (bucket 22.18) → ✅ Dahil (range içinde)
- $22.22 (bucket 22.18) → ✅ Dahil (range içinde)
- $22.25 (bucket 22.25) → ✅ Dahil (range içinde)
- $22.27 (bucket 22.25) → ✅ Dahil (range içinde)
- $22.30 (bucket 22.30) → ❌ Dahil değil (range dışında)
```

#### Adım 6: Volav VWAP ve Volume Hesaplama
```
Range içindeki tüm tick'lerden:
- range_volume = sum(size)
- range_price_sum = sum(price × size)
- range_vwap = range_price_sum / range_volume
```

**Örnek:**
```
Range: $22.215 - $22.285
Tick'ler:
- $22.20 × 50 lot = 1,110
- $22.22 × 30 lot = 666.6
- $22.25 × 800 lot = 18,000
- $22.27 × 20 lot = 445.4
- Toplam: 900 lot, toplam = 20,222
- VWAP = 20,222 / 900 = $22.469
```

#### Adım 7: Merge Kontrolü (YENİ!)
```
Yeni Volav ile mevcut Volav'lar arasında gap kontrolü:

if gap < merge_threshold:
  → Birleştir (aralıkları birleştir, VWAP yeniden hesapla)
elif gap >= min_gap:
  → Kesinlikle ayrı Volav
else:
  → Ayrı Volav (ara bölge: merge_threshold <= gap < min_gap)
```

**Örnek (AVG_ADV = 15,000, min_gap = 0.09, merge_threshold = 0.054):**
```
Volav1: $22.25 (range: $22.215 - $22.285)
Volav2: $22.30 (range: $22.265 - $22.335)
Gap = |22.30 - 22.25| = 0.05 < 0.054 → Birleştir! ✅

Birleşik aralık: $22.215 - $22.335
Birleşik VWAP: Bu aralıktaki tüm tick'lerden yeniden hesapla
```

---

## 6. Volav1 Start/End ve Displacement

### 🎯 Amaç
**Volav1 Start/End**, timeframe içindeki **fiyat migrasyonunu** ölçer.

### 📊 Hesaplama Süreci

#### Adım 1: Timeframe Ticks'lerini Sırala
```
truth_ticks_timeframe → timestamp'e göre sırala (oldest → newest)
```

#### Adım 2: İlk %20 ve Son %20'yi Ayır
```
first_20_percent_count = max(1, int(truth_tick_count * 0.2))
first_20_percent_ticks = sorted_ticks[:first_20_percent_count]

last_20_percent_count = max(1, int(truth_tick_count * 0.2))
last_20_percent_ticks = sorted_ticks[-last_20_percent_count:]
```

**Örnek (100 tick):**
```
first_20_percent = ilk 20 tick (en eski)
last_20_percent = son 20 tick (en yeni)
```

#### Adım 3: Volav1 Start Hesapla
```
first_20_percent_ticks → compute_volav_levels(top_n=1) → Volav1
volav1_start = Volav1 price
```

#### Adım 4: Volav1 End Hesapla
```
last_20_percent_ticks → compute_volav_levels(top_n=1) → Volav1
volav1_end = Volav1 price
```

#### Adım 5: Displacement Hesapla
```
volav1_displacement = volav1_end - volav1_start
normalized_displacement = volav1_displacement / min_volav_gap
```

**Örnek:**
```
volav1_start = $22.25
volav1_end = $22.30
volav1_displacement = $22.30 - $22.25 = $0.05
min_volav_gap = $0.09
normalized_displacement = $0.05 / $0.09 = 0.556
```

### 🔑 Önemli Konsept
**Volav1 Start/End, timeline window'larından değil, timeframe içindeki ilk/son %20 tick'lerden hesaplanır!**

---

## 7. State Classification (10-State Model)

### 🎯 Amaç
**State**, piyasa mikro-yapısını kategorize eder.

### 📊 10 State

#### 7.1 STRONG_BUYER_DOMINANT
```
normalized_displacement >= 1.5
adv_fraction >= 0.10
truth_tick_count >= 15
```
**Anlam:** Güçlü alıcı baskısı, fiyat yukarı taşınıyor.

#### 7.2 BUYER_DOMINANT
```
0.4 <= normalized_displacement < 1.5
adv_fraction >= 0.10
truth_tick_count >= 15
```
**Anlam:** Alıcı baskısı, fiyat yukarı.

#### 7.3 BUYER_ABSORPTION
```
abs(normalized_displacement) < 0.3
adv_fraction >= 0.60
normalized_displacement >= 0
truth_tick_count >= 15
```
**Anlam:** Yüksek volume, fiyat hafif yukarı/yatay, alıcı emiyor.

#### 7.4 BUYER_VACUUM
```
normalized_displacement > 0
adv_fraction < 0.20
truth_tick_count >= 15
```
**Anlam:** Düşük volume, fiyat yukarı, gerçek alıcı yok (fake strength).

#### 7.5 NEUTRAL
```
Diğer durumlar (yeterli tick, ama belirgin pattern yok)
```
**Anlam:** Tape okunamaz, edge yok.

#### 7.6 SELLER_ABSORPTION
```
abs(normalized_displacement) < 0.3
adv_fraction >= 0.60
normalized_displacement < 0
truth_tick_count >= 15
```
**Anlam:** Yüksek volume, fiyat hafif aşağı/yatay, satıcı emiyor.

#### 7.7 SELLER_DOMINANT
```
-1.5 < normalized_displacement <= -0.4
adv_fraction >= 0.10
truth_tick_count >= 15
```
**Anlam:** Satıcı baskısı, fiyat aşağı.

#### 7.8 STRONG_SELLER_DOMINANT
```
normalized_displacement <= -1.5
adv_fraction >= 0.10
truth_tick_count >= 15
```
**Anlam:** Güçlü satıcı baskısı, fiyat aşağı taşınıyor.

#### 7.9 SELLER_VACUUM
```
normalized_displacement < 0
adv_fraction < 0.20
truth_tick_count >= 15
```
**Anlam:** Düşük volume, fiyat aşağı, gerçek satıcı yok (air pocket).

#### 7.10 INSUFFICIENT_DATA
```
truth_tick_count < 15
```
**Anlam:** Yeterli data yok, ama metrics hala döndürülür (N/A değil).

---

## 8. Örnek Senaryo

### 📊 Senaryo: CIM PRB, TF_1D, AVG_ADV = 12,000

#### Adım 1: Truth Tick Filtreleme
```
Tüm Print'ler (son 1 trading day):
- $22.20 × 5 lot (NYSE) → ❌ Truth Tick değil
- $22.22 × 25 lot (NYSE) → ✅ Truth Tick
- $22.25 × 100 lot (FNRA) → ✅ Truth Tick
- $22.27 × 30 lot (ARCA) → ✅ Truth Tick
- $22.30 × 200 lot (FNRA) → ✅ Truth Tick
- $22.32 × 50 lot (NYSE) → ✅ Truth Tick
- $22.35 × 20 lot (NYSE) → ✅ Truth Tick

Truth Ticks: 7 tick, toplam volume = 425 lot
```

#### Adım 2: AVG_ADV Bazlı Parametreler
```
AVG_ADV = 12,000:
- bucket_size = $0.07
- min_gap = $0.09
- merge_threshold = $0.09 * 0.6 = $0.054
```

#### Adım 3: Bucket Aggregation
```
Bucket 22.18: $22.22 × 25 = 555.5
Bucket 22.25: $22.25 × 100 = 2,225
Bucket 22.25: $22.27 × 30 = 668.1
Bucket 22.30: $22.30 × 200 = 4,460
Bucket 22.30: $22.32 × 50 = 1,116
Bucket 22.35: $22.35 × 20 = 447

Bucket VWAP'ları:
- Bucket 22.18: VWAP = $22.22 (25 lot)
- Bucket 22.25: VWAP = $22.26 (130 lot: 100+30)
- Bucket 22.30: VWAP = $22.31 (250 lot: 200+50)
- Bucket 22.35: VWAP = $22.35 (20 lot)
```

#### Adım 4: Volume Sıralama
```
1. Bucket 22.30: 250 lot → Volav1 adayı
2. Bucket 22.25: 130 lot → Volav2 adayı
3. Bucket 22.18: 25 lot → Volav3 adayı
4. Bucket 22.35: 20 lot → Volav4 adayı
```

#### Adım 5: Volav Range Hesaplama
```
Volav1 (Bucket 22.30):
- Center = $22.31
- Range = $22.31 ± 0.035 = $22.275 - $22.345
- Range içindeki tick'ler: $22.27, $22.30, $22.32
- Range volume = 30 + 200 + 50 = 280 lot
- Range VWAP = (22.27×30 + 22.30×200 + 22.32×50) / 280 = $22.304

Volav2 (Bucket 22.25):
- Center = $22.26
- Range = $22.26 ± 0.035 = $22.225 - $22.295
- Range içindeki tick'ler: $22.22, $22.25, $22.27
- Range volume = 25 + 100 + 30 = 155 lot
- Range VWAP = (22.22×25 + 22.25×100 + 22.27×30) / 155 = $22.247
```

#### Adım 6: Merge Kontrolü
```
Volav1: $22.304 (range: $22.275 - $22.345)
Volav2: $22.247 (range: $22.225 - $22.295)
Gap = |22.304 - 22.247| = 0.057

0.054 (merge_threshold) <= 0.057 < 0.09 (min_gap)
→ Ayrı Volav (ara bölge)
```

#### Adım 7: Volav1 Start/End Hesaplama
```
Truth Ticks (7 tick):
- İlk %20 = ilk 2 tick: $22.22, $22.25
- Son %20 = son 2 tick: $22.32, $22.35

Volav1 Start (ilk 2 tick):
- Bucket 22.18: $22.22 × 25 = 555.5
- Bucket 22.25: $22.25 × 100 = 2,225
- Range: $22.18 ± 0.035 = $22.145 - $22.215
- Range içindeki tick: $22.22 (range dışında, sadece bucket içindeki tick'ler)
- Volav1 Start = $22.235 (25+100 lot'tan VWAP)

Volav1 End (son 2 tick):
- Bucket 22.30: $22.32 × 50 = 1,116
- Bucket 22.35: $22.35 × 20 = 447
- Range: $22.30 ± 0.035 = $22.265 - $22.335
- Range içindeki tick: $22.32 (range dışında)
- Volav1 End = $22.33 (50+20 lot'tan VWAP)

Displacement:
- volav1_displacement = $22.33 - $22.235 = $0.095
- normalized_displacement = $0.095 / $0.09 = 1.056
```

#### Adım 8: State Classification
```
normalized_displacement = 1.056
adv_fraction = 425 / 12,000 = 0.035
truth_tick_count = 7

1.056 >= 0.4 (BUYER_DOMINANT threshold)
0.035 < 0.10 (LOW_VOLUME threshold)
7 < 15 (INSUFFICIENT_DATA threshold)

→ State = INSUFFICIENT_DATA (tick count < 15)
→ Confidence = 7/15 = 0.467 (düşük confidence)
```

---

## 🎯 Özet

### Truth Ticks
- **Amaç:** Gerçek fiyat hareketini yakalamak
- **Filtreleme:** size >= 20, FNRA rules
- **Sonuç:** Noise-free, volume-weighted prints

### Volav
- **Amaç:** Volume konsantrasyonunu bulmak
- **Hesaplama:** Range-based clustering (center ± bucket_size/2)
- **Merging:** merge_threshold = min_gap * 0.6
- **Sonuç:** Volume-dominant fiyat seviyeleri

### Timeframe-First
- **Amaç:** Tüm semboller aynı zaman aralığında analiz
- **Timeframe'ler:** TF_4H, TF_1D, TF_3D, TF_5D (trading hours bazlı)
- **Effective Now:** Market kapalıysa son trading day close

### AVG_ADV
- **Amaç:** Normalizasyon ve dinamik threshold'lar
- **Parametreler:** bucket_size, min_gap, merge_threshold
- **Sonuç:** Likiditeye göre adaptif hesaplama

### Volav1 Start/End
- **Amaç:** Fiyat migrasyonunu ölçmek
- **Hesaplama:** İlk/son %20 tick'lerden Volav1
- **Displacement:** normalized_displacement = displacement / min_gap

### State Classification
- **Amaç:** Piyasa mikro-yapısını kategorize etmek
- **Model:** 10-state (STRONG_BUYER_DOMINANT → INSUFFICIENT_DATA)
- **Kriterler:** normalized_displacement, adv_fraction, truth_tick_count

---

## 🔑 Kritik Noktalar

1. **Truth Ticks = Gerçek Flow:** Noise filtrelenir, sadece anlamlı print'ler kalır
2. **Volav = Volume Konsantrasyonu:** Tick sayısı değil, volume önemli
3. **Range-Based Clustering:** Bucket sınırı yok, range içindeki tüm tick'ler dahil
4. **Merge Threshold:** Çok yakın Volav'lar birleştirilir
5. **Timeframe-First:** Tüm semboller aynı zaman aralığında
6. **AVG_ADV Normalizasyonu:** Mutlak volume değil, relative pressure
7. **Volav1 Start/End:** Timeline değil, ilk/son %20 tick'ler
8. **10-State Model:** Detaylı piyasa mikro-yapısı analizi

---

**Son Güncelleme:** 2025-12-21  
**Versiyon:** TruthTicksEngine v2 (Range-Based Volav + Merge Threshold)



