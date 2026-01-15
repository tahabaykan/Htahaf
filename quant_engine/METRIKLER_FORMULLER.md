# Metrikler ve Formüller - Detaylı Açıklama

## 1. GRPAN (Grouped Real Print Analyzer)

### Ne Yapar?
GRPAN, trade print'lerden (gerçek işlemlerden) ağırlıklı fiyat yoğunluğu analizi yapar. Son işlemlerdeki dominant fiyatı ve konsantrasyon yüzdesini hesaplar.

### Formül:

```
1. Trade Print Filtreleme:
   - Size < 10 lot olan print'ler IGNORE edilir
   - Sadece size >= 10 lot olan print'ler kullanılır

2. Ağırlık Hesaplama (Weight):
   - 100/200/300 lot = 1.0 ağırlık
   - Diğer lotlar (10-99, 101-199, 201-299, 301+) = 0.25 ağırlık

3. Ağırlıklı Fiyat Yoğunluğu:
   price_frequency[price] += weight
   
4. Dominant Fiyat (GRPAN Price):
   grpan_price = max(price_frequency)  # En yüksek ağırlıklı frekansa sahip fiyat

5. Konsantrasyon Yüzdesi:
   concentration_count = print'ler içinde |price - grpan_price| <= 0.04 olanlar
   concentration_percent = (concentration_count / total_prints) * 100
```

### Rolling Windows:
- `latest_pan`: Son 15 print (ring buffer)
- `pan_10m`: Son 10 dakika
- `pan_30m`: Son 30 dakika
- `pan_1h`: Son 1 saat
- `pan_3h`: Son 3 saat
- `pan_1d`: Son 1 işlem günü
- `pan_3d`: Son 3 işlem günü

### Çıktılar:
- `grpan_price`: Dominant fiyat (en yüksek ağırlıklı frekans)
- `concentration_percent`: ±0.04 aralığındaki yoğunluk yüzdesi
- `real_lot_count`: 100/200/300 lot sayısı
- `print_count`: Toplam print sayısı
- `deviation_vs_last`: `last_price - grpan_price`

---

## 2. GOD (GRPAN ORT DEV) - Group Outlier Detection

### Ne Yapar?
GOD, son fiyatın tüm GRPAN window'larının ortalamasından sapmasını ölçer. Yüksek GOD değerleri, hissenin GRPAN ortalamasından ne kadar saptığını gösterir.

### Formül:

```
1. GRPAN Ortalama (GRPAN ORT):
   grpan_prices = [pan_10m.grpan_price, pan_30m.grpan_price, pan_1h.grpan_price, 
                   pan_3h.grpan_price, pan_1d.grpan_price, pan_3d.grpan_price]
   
   # Geçersiz değerler çıkarılır (NaN, Inf, None)
   valid_grpan_prices = [p for p in grpan_prices if p is valid]
   
   grpan_ort = sum(valid_grpan_prices) / len(valid_grpan_prices)

2. GOD Hesaplama:
   GOD = last_price - grpan_ort
```

### Anlamı:
- **GOD > 0**: Son fiyat, GRPAN ortalamasının üzerinde (pahalı)
- **GOD < 0**: Son fiyat, GRPAN ortalamasının altında (ucuz)
- **GOD = 0**: Son fiyat, GRPAN ortalamasına eşit

### Kullanım:
- En yüksek GOD değerleri = en çok sapma gösteren hisseler (outlier detection)
- Trading stratejilerinde: Yüksek GOD = potansiyel mean reversion fırsatı

---

## 3. RWVAP (Robust VWAP)

### Ne Yapar?
RWVAP, extreme volume print'lerini (FINRA, block transfers) hariç tutarak VWAP hesaplar. İlliquid preferred stock'lar için daha güvenilir bir ortalama fiyat sağlar.

### Formül:

```
1. Extreme Volume Filtresi:
   extreme_threshold = AVG_ADV * extreme_multiplier  # Default: AVG_ADV * 1.0
   
   # Size > extreme_threshold olan print'ler EXCLUDE edilir
   if print.size > extreme_threshold:
       exclude print

2. VWAP Hesaplama (Filtered Prints):
   total_volume = sum(print.size for print in filtered_prints)
   weighted_price_sum = sum(print.price * print.size for print in filtered_prints)
   
   rwvap = weighted_price_sum / total_volume
```

### Rolling Windows:
- `rwvap_1d`: Son 1 işlem günü
- `rwvap_3d`: Son 3 işlem günü
- `rwvap_5d`: Son 5 işlem günü

### Özellikler:
- **Extreme Volume Filter**: `size > (AVG_ADV * 1.0)` olan print'ler exclude edilir
- **Shared Buffer**: GRPAN'in 150-tick buffer'ını kullanır (veri tekrarı yok)
- **Trading-Time Aware**: Sadece işlem saatleri içindeki print'ler kullanılır

### Çıktılar:
- `rwvap`: Robust VWAP fiyatı
- `effective_print_count`: Hesaplamaya dahil edilen print sayısı
- `excluded_print_count`: Hariç tutulan print sayısı
- `excluded_volume_ratio`: Hariç tutulan volume oranı
- `deviation_vs_last`: `last_price - rwvap`

---

## 4. ROD (RWVAP ORT DEV) - Relative Outlier Detection

### Ne Yapar?
ROD, son fiyatın tüm RWVAP window'larının ortalamasından sapmasını ölçer. Yüksek ROD değerleri, hissenin RWVAP ortalamasından ne kadar saptığını gösterir.

### Formül:

```
1. RWVAP Ortalama (RWVAP ORT):
   rwvap_prices = [rwvap_1d.rwvap, rwvap_3d.rwvap, rwvap_5d.rwvap]
   
   # Geçersiz değerler çıkarılır (NaN, Inf, None)
   valid_rwvap_prices = [p for p in rwvap_prices if p is valid]
   
   rwvap_ort = sum(valid_rwvap_prices) / len(valid_rwvap_prices)

2. ROD Hesaplama:
   ROD = last_price - rwvap_ort
```

### Anlamı:
- **ROD > 0**: Son fiyat, RWVAP ortalamasının üzerinde (pahalı)
- **ROD < 0**: Son fiyat, RWVAP ortalamasının altında (ucuz)
- **ROD = 0**: Son fiyat, RWVAP ortalamasına eşit

### Kullanım:
- En yüksek ROD değerleri = en çok sapma gösteren hisseler (relative outlier detection)
- Trading stratejilerinde: Yüksek ROD = potansiyel mean reversion fırsatı

---

## GOD vs ROD - Fark Nedir?

### GOD (GRPAN ORT DEV):
- **Kaynak**: GRPAN window'ları (pan_10m, pan_30m, pan_1h, pan_3h, pan_1d, pan_3d)
- **Zaman Aralığı**: Kısa-orta vadeli (10 dakika - 3 gün)
- **Hesaplama**: Ağırlıklı fiyat yoğunluğu (lot-based weighting)
- **Kullanım**: Kısa vadeli sapma tespiti, momentum analizi

### ROD (RWVAP ORT DEV):
- **Kaynak**: RWVAP window'ları (rwvap_1d, rwvap_3d, rwvap_5d)
- **Zaman Aralığı**: Orta-uzun vadeli (1-5 işlem günü)
- **Hesaplama**: Volume-weighted average price (extreme volume filtered)
- **Kullanım**: Orta-uzun vadeli sapma tespiti, trend analizi

### Özet:
- **GOD**: Kısa vadeli, ağırlıklı fiyat yoğunluğu bazlı sapma
- **ROD**: Orta-uzun vadeli, volume-weighted average bazlı sapma
- **İkisi birlikte**: Farklı zaman dilimlerinde sapma tespiti yapılır

---

## Örnek Hesaplama:

### GRPAN Örneği:
```
Trade Prints:
- Print 1: price=20.00, size=100 (weight=1.0)
- Print 2: price=20.01, size=50 (weight=0.25)
- Print 3: price=20.00, size=200 (weight=1.0)
- Print 4: price=20.02, size=30 (weight=0.25)

Price Frequency:
- 20.00: 1.0 + 1.0 = 2.0
- 20.01: 0.25
- 20.02: 0.25

GRPAN Price = 20.00 (en yüksek frekans: 2.0)
Concentration % = 3/4 = 75% (20.00, 20.01, 20.02 hepsi ±0.04 içinde)
```

### GOD Örneği:
```
GRPAN Windows:
- pan_10m: grpan_price = 20.00
- pan_30m: grpan_price = 19.95
- pan_1h: grpan_price = 20.05
- pan_3h: grpan_price = 19.98
- pan_1d: grpan_price = 20.02
- pan_3d: grpan_price = 19.99

GRPAN ORT = (20.00 + 19.95 + 20.05 + 19.98 + 20.02 + 19.99) / 6 = 20.00
Last Price = 20.10

GOD = 20.10 - 20.00 = +0.10
```

### RWVAP Örneği:
```
Filtered Prints (extreme volume excluded):
- Print 1: price=20.00, size=100
- Print 2: price=20.01, size=80
- Print 3: price=19.99, size=120

Total Volume = 300
Weighted Price Sum = (20.00 * 100) + (20.01 * 80) + (19.99 * 120) = 6000.80

RWVAP = 6000.80 / 300 = 20.0027
```

### ROD Örneği:
```
RWVAP Windows:
- rwvap_1d: rwvap = 20.00
- rwvap_3d: rwvap = 19.95
- rwvap_5d: rwvap = 20.05

RWVAP ORT = (20.00 + 19.95 + 20.05) / 3 = 20.00
Last Price = 20.10

ROD = 20.10 - 20.00 = +0.10
```

---

## 5. SRPAN (Spread Real Print Analyzer)

### Ne Yapar?
SRPAN, son 30 tick'ten iki farklı fiyat konsantrasyon noktası (G1 ve G2) bulur ve spread kalitesini skorlar. Dual-sided liquidity analizi yapar.

### Formül:

```
1. Veri Toplama:
   - Son 30 filtered tick (size > 9 lot)
   - Minimum 8 tick gerekli

2. Ağırlıklandırma:
   - 100/200/300 lot = 1.00 ağırlık
   - Diğer lotlar = 0.25 ağırlık

3. GRPAN1 (Primary Concentration):
   - En yüksek ağırlıklı fiyat
   - Konsantrasyon = ±0.03¢ aralığındaki ağırlık / toplam ağırlık

4. GRPAN2 (Secondary Concentration):
   - GRPAN1'den en az 0.06¢ uzakta olmalı
   - Excluded set içindeki en yüksek ağırlıklı fiyat
   - Konsantrasyon = ±0.03¢ aralığındaki ağırlık / toplam ağırlık

5. Spread Hesaplama:
   spread = |GRPAN2 - GRPAN1|
   direction = 'UP' if GRPAN2 > GRPAN1 else 'DOWN'

6. SRPAN Skoru (0-100):
   a) Balance Score (60%):
      conf_diff = |G1_conf - G2_conf|
      balance_score = max(0, 100 - conf_diff)
      # G1 ve G2 konsantrasyonları eşit olmalı (50-50 ideal)

   b) Total Score (15%):
      total_conf = G1_conf + G2_conf
      total_score = min(100, total_conf)
      # Toplam konsantrasyon yüksek olmalı

   c) Spread Score (25%):
      if spread >= 0.30: spread_score = 100
      elif spread <= 0.06: spread_score = 0
      else: spread_score = ((spread - 0.06) / (0.30 - 0.06)) * 100
      # Spread geniş olmalı (0.06¢ minimum, 0.30¢ optimal)

   SRPAN Score = (0.60 * balance_score) + (0.15 * total_score) + (0.25 * spread_score)
```

### Kurallar:
- **Minimum Tick Sayısı**: 8 tick (9 lot üstü, filtrelenmiş)
- **GRPAN Aralığı**: ±0.03¢ (değiştirildi: önceden ±0.04¢)
- **Minimum Spread**: 0.06¢ (değiştirildi: önceden 0.08¢)
- **G1-G2 Minimum Mesafe**: 0.06¢ (değiştirildi: önceden 0.08¢)
- **Optimal Spread**: ≥0.30¢ (spread_score = 100)

### Çıktılar:
- `srpan_score`: Composite score (0-100)
- `grpan1`: Primary dominant price
- `grpan1_conf`: G1 konsantrasyon yüzdesi
- `grpan2`: Secondary dominant price
- `grpan2_conf`: G2 konsantrasyon yüzdesi
- `spread`: G1-G2 fiyat farkı
- `direction`: 'UP' veya 'DOWN'
- `balance_score`: G1-G2 denge skoru
- `total_score`: Toplam konsantrasyon skoru
- `spread_score`: Spread genişlik skoru

### Anlamı:
- **SRPAN ≥ 70**: Excellent - İki taraflı likidite, dengeli spread
- **SRPAN ≥ 50**: Good - İyi spread kalitesi
- **SRPAN ≥ 30**: Fair - Orta seviye spread
- **SRPAN < 30**: Low - Düşük spread kalitesi

### Kullanım:
- **Spread Quality**: İki taraflı likidite analizi
- **Order Placement**: Optimal emir yerleştirme fiyatları (G1/G2)
- **Liquidity Detection**: Dual-sided liquidity tespiti
- **Trading Opportunities**: Spread trading fırsatları

### Örnek Hesaplama:
```
Son 30 Tick (filtrelenmiş, 9 lot üstü):
- 20.00: 5 tick (100 lot = 5.0 ağırlık)
- 20.01: 3 tick (50 lot = 0.75 ağırlık)
- 20.05: 4 tick (200 lot = 4.0 ağırlık)
- 20.06: 2 tick (30 lot = 0.5 ağırlık)

Price Weights:
- 20.00: 5.0
- 20.01: 0.75
- 20.05: 4.0
- 20.06: 0.5

GRPAN1 = 20.00 (en yüksek: 5.0)
G1 Range (±0.03): 19.97-20.03
G1 Weight = 5.0 + 0.75 = 5.75
Total Weight = 10.25
G1 Conf = (5.75 / 10.25) * 100 = 56.1%

GRPAN2 (≥0.06¢ from G1):
- 20.05: 4.0 (en yüksek)
- 20.06: 0.5

GRPAN2 = 20.05
G2 Range (±0.03): 20.02-20.08
G2 Weight = 4.0 + 0.5 = 4.5
G2 Conf = (4.5 / 10.25) * 100 = 43.9%

Spread = |20.05 - 20.00| = 0.05¢
Direction = 'UP'

Balance Score = max(0, 100 - |56.1 - 43.9|) = max(0, 100 - 12.2) = 87.8
Total Score = min(100, 56.1 + 43.9) = 100
Spread Score = 0 (spread 0.05 < 0.06 minimum)

SRPAN Score = (0.60 * 87.8) + (0.15 * 100) + (0.25 * 0) = 52.68 + 15 + 0 = 67.68
```


