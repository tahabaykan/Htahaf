# Decision Helper - Timeframe ve Displacement Açıklaması

## 🕐 TIMEFRAME (Zaman Penceresi) Nasıl Çalışıyor?

### Rolling Window Mantığı

Decision Helper, **rolling window** (kayan pencere) kullanır:

**Örnek: 15 dakika penceresi**
- Şu an saat: **14:13:20**
- Window: **15 dakika** (900 saniye)
- Bakılan zaman aralığı: **13:58:20 - 14:13:20** (son 15 dakika)

**Nasıl Hesaplanıyor:**
```python
current_time = time.time()  # Şu anki zaman (Unix timestamp)
window_seconds = 15 * 60    # 900 saniye
window_start_time = current_time - window_seconds  # 13:58:20

# Tick'ler filtrelenir:
if window_start_time <= tick_time <= current_time:
    # Bu tick window içinde, kullanılır
```

**Pencereler:**
- **5m**: Son 5 dakika
- **15m**: Son 15 dakika  
- **30m**: Son 30 dakika

---

## 📊 FIRST_PRICE ve LAST_PRICE Nedir?

### ⚠️ ÖNEMLİ: "First" ve "Last" = ZAMAN'a göre, eklenme sırasına göre DEĞİL!

**FIRST_PRICE (İlk Fiyat):**
- Window içindeki **EN ESKİ** tick'in fiyatı
- Timestamp'e göre **en küçük** olan tick
- Örnek: 13:58:20'deki tick (window'un başlangıcı)

**LAST_PRICE (Son Fiyat):**
- Window içindeki **EN YENİ** tick'in fiyatı
- Timestamp'e göre **en büyük** olan tick
- Örnek: 14:13:20'deki tick (window'un sonu)

### Kod Mantığı:

```python
# 1. Tick'ler timestamp'e göre SIRALANIR (ascending: en eski → en yeni)
sorted_pairs = sorted(zip(tick_times, window_ticks), key=lambda x: x[0])
window_ticks = [tick for _, tick in sorted_pairs]

# 2. İlk tick = En eski (timestamp en küçük)
first_price = window_ticks[0].get('p')  # En eski tick'in fiyatı

# 3. Son tick = En yeni (timestamp en büyük)
last_price = window_ticks[-1].get('p')  # En yeni tick'in fiyatı

# 4. Displacement = En yeni - En eski
displacement = last_price - first_price
```

---

## 🔍 ÖRNEK: WRB-E Senaryosu

**Diyelim ki:**
- Window: 15 dakika (13:58:20 - 14:13:20)
- Tick'ler:
  - 13:58:20 → Fiyat: **21.70** (en eski)
  - 14:00:00 → Fiyat: **21.65**
  - 14:05:00 → Fiyat: **21.60**
  - 14:10:00 → Fiyat: **21.55**
  - 14:13:20 → Fiyat: **21.50** (en yeni)

**Hesaplama:**
- `first_price = 21.70` (13:58:20'deki tick - EN ESKİ)
- `last_price = 21.50` (14:13:20'deki tick - EN YENİ)
- `displacement = 21.50 - 21.70 = -0.20` (NEGATİF - aşağı düşmüş)

**✅ Bu DOĞRU!** Fiyat 21.70'ten 21.50'ye düşmüş, displacement negatif olmalı.

---

## ❌ YANLIŞ ANLAMA: "First" = İlk Eklenen Değil!

**YANLIŞ DÜŞÜNCE:**
- "First" = Tick store'a ilk eklenen tick
- "Last" = Tick store'a son eklenen tick

**DOĞRU:**
- "First" = Window içindeki **EN ESKİ** tick (timestamp'e göre)
- "Last" = Window içindeki **EN YENİ** tick (timestamp'e göre)

**Neden?**
- Tick'ler farklı zamanlarda eklenebilir
- İlk eklenen tick, en eski tick olmayabilir!
- Bu yüzden **timestamp'e göre** sıralama yapılır

---

## 🐛 OLASI SORUNLAR

### 1. Timestamp Parsing Hatası

Eğer timestamp'ler yanlış parse edilirse:
- Tick'ler ters sıralanabilir
- "First" aslında "Last" olabilir
- Displacement işareti ters olur

**Kontrol:**
```python
# Log'da şunları kontrol et:
first_tick_time = window_ticks[0].get('t')  # Timestamp string
last_tick_time = window_ticks[-1].get('t')  # Timestamp string
first_tick_ts = tick_times[0]  # Parsed timestamp (float)
last_tick_ts = tick_times[-1]  # Parsed timestamp (float)

# last_tick_ts > first_tick_ts olmalı!
```

### 2. Symbol Mapping Karışması

Eğer farklı symbol'lerin tick'leri karışırsa:
- WRB-E'nin tick'leri WRB-PRH ile karışabilir
- "First" başka symbol'den, "Last" başka symbol'den olabilir

**Kontrol:**
- Symbol mapping log'larını kontrol et
- Her tick'in doğru symbol'e ait olduğundan emin ol

### 3. Window Filtreleme Hatası

Eğer window filtresi yanlış çalışırsa:
- Eski tick'ler window'a dahil olabilir
- Yeni tick'ler window'dan çıkarılabilir

**Kontrol:**
- Window start/end zamanlarını log'la
- Tick'lerin window içinde olduğundan emin ol

---

## 🔧 DEBUG İÇİN LOG FORMATI

Şu log'ları ekledik:

```
🔍 [DISPLACEMENT] WRB PRE (15m): 
  first=21.7000@2025-12-19T13:58:20 (ts=1734611900.0), 
  last=21.5000@2025-12-19T14:13:20 (ts=1734612800.0), 
  time_diff=900.0s, 
  disp(last-first)=-0.2000, 
  disp(first-last)=+0.2000, 
  ticks=150, 
  ✅ RESULT=-0.2000
```

**Kontrol Edilecekler:**
1. `time_diff` pozitif mi? (last_ts > first_ts olmalı)
2. `first` timestamp'i `last` timestamp'inden önce mi?
3. `disp(last-first)` işareti doğru mu?
4. Symbol doğru mu? (WRB-E için WRB-E tick'leri mi?)

---

## 📝 ÖZET

**FIRST_PRICE:**
- Window içindeki **EN ESKİ** tick'in fiyatı
- Timestamp'e göre **en küçük** olan

**LAST_PRICE:**
- Window içindeki **EN YENİ** tick'in fiyatı
- Timestamp'e göre **en büyük** olan

**DISPLACEMENT:**
- `last_price - first_price`
- Pozitif = Fiyat yukarı gitmiş
- Negatif = Fiyat aşağı gitmiş

**TIMEFRAME:**
- Rolling window: Son N dakika
- Her hesaplamada güncel zaman kullanılır
- Window sürekli "kayar" (rolling)
