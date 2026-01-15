# Price Displacement - Detaylı Açıklama

## 🎯 Price Displacement Nedir?

**Price Displacement**, belirli bir zaman penceresi içinde fiyatın **ne kadar değiştiğini** ölçer.

**Basit Formül:**
```
Displacement = Son Fiyat - İlk Fiyat
```

**Anlamı:**
- **Pozitif (+)** → Fiyat yukarı gitmiş (satın alma baskısı)
- **Negatif (-)** → Fiyat aşağı gitmiş (satış baskısı)
- **Sıfır (0)** → Fiyat değişmemiş (dengeli)

---

## 📊 ADIM ADIM HESAPLAMA

### ADIM 1: Zaman Penceresi Belirleme

**Örnek: 15 dakika penceresi**

```
Şu anki zaman: 14:30:00
Window: 15 dakika (900 saniye)
Window başlangıcı: 14:15:00
Window sonu: 14:30:00
```

**Kod:**
```python
# En son trade'in zamanını bul
last_print_time = tick_times_parsed[-1][0]  # Örnek: 14:30:00

# Window'u hesapla
window_end_time = last_print_time      # 14:30:00
window_start_time = window_end_time - 900  # 14:15:00
```

**Sonuç:** 14:15:00 - 14:30:00 arasındaki tüm trade'ler

---

### ADIM 2: Gerçek Trade'leri Filtrele

**Sadece gerçek trade'ler kullanılır:**

✅ **Dahil edilen:**
- `bf=false` (pseudo-tick değil)
- `price > 0` (geçerli fiyat)
- `size > 0` (gerçek trade - bid/ask update değil)
- `size <= avg_adv` (FINRA/ADFN print değil)

❌ **Hariç tutulan:**
- Bid/ask update'leri (`size=0`)
- Pseudo-ticks (`bf=true`)
- Aşırı büyük trade'ler (`size > avg_adv`)

**Örnek Tick'ler:**
```
Tick 1: 14:15:10, price=21.70, size=100, bf=false  ✅ KULLANILIR
Tick 2: 14:15:20, price=0, size=0, bf=false        ❌ HARIÇ (bid/ask update)
Tick 3: 14:16:05, price=21.65, size=50, bf=true   ❌ HARIÇ (pseudo-tick)
Tick 4: 14:20:30, price=21.60, size=200, bf=false  ✅ KULLANILIR
Tick 5: 14:25:15, price=21.55, size=75, bf=false   ✅ KULLANILIR
Tick 6: 14:30:00, price=21.50, size=150, bf=false  ✅ KULLANILIR
```

**Filtreleme sonrası:**
```
Window içindeki gerçek trade'ler:
- 14:15:10 → 21.70
- 14:20:30 → 21.60
- 14:25:15 → 21.55
- 14:30:00 → 21.50
```

---

### ADIM 3: Timestamp'e Göre Sıralama

**ÖNEMLİ:** Tick'ler **timestamp'e göre** sıralanır (eklenme sırasına göre değil!)

**Kod:**
```python
# Timestamp'e göre sırala (ascending: en eski → en yeni)
window_ticks_with_time.sort(key=lambda x: x[0])
```

**Sonuç:**
```
Sıralı tick'ler (zaman sırasına göre):
1. 14:15:10 → 21.70  (EN ESKİ)
2. 14:20:30 → 21.60
3. 14:25:15 → 21.55
4. 14:30:00 → 21.50  (EN YENİ)
```

---

### ADIM 4: First Price ve Last Price Bulma

**FIRST_PRICE (İlk Fiyat):**
- Sıralı listedeki **İLK** tick'in fiyatı
- Timestamp'e göre **EN ESKİ** olan tick
- Window'un **BAŞLANGICI**

**LAST_PRICE (Son Fiyat):**
- Sıralı listedeki **SON** tick'in fiyatı
- Timestamp'e göre **EN YENİ** olan tick
- Window'un **SONU**

**Kod:**
```python
# İlk tick = En eski (timestamp en küçük)
first_price = float(window_ticks[0].get('p', 0))  # 21.70
first_tick_time = window_ticks[0].get('t')        # 14:15:10

# Son tick = En yeni (timestamp en büyük)
last_price = float(window_ticks[-1].get('p', 0))   # 21.50
last_tick_time = window_ticks[-1].get('t')        # 14:30:00
```

**Örnek:**
```
first_price = 21.70  (14:15:10 - EN ESKİ)
last_price = 21.50   (14:30:00 - EN YENİ)
```

---

### ADIM 5: Displacement Hesaplama

**Formül:**
```python
price_displacement = last_price - first_price
```

**Örnek:**
```
price_displacement = 21.50 - 21.70 = -0.20
```

**Yorum:**
- **Negatif (-0.20)** → Fiyat **aşağı** gitmiş
- 15 dakika içinde **20 cent** düşmüş
- **Satış baskısı** var

---

## 🔍 GERÇEK ÖRNEKLER

### Örnek 1: Yukarı Trend (Pozitif Displacement)

**Window: 15 dakika (14:15:00 - 14:30:00)**

```
Trade'ler:
14:15:10 → 21.50  (EN ESKİ)
14:18:20 → 21.55
14:22:05 → 21.60
14:27:30 → 21.65
14:30:00 → 21.70  (EN YENİ)
```

**Hesaplama:**
```
first_price = 21.50  (14:15:10)
last_price = 21.70   (14:30:00)
displacement = 21.70 - 21.50 = +0.20
```

**Sonuç:** ✅ **+0.20** (Pozitif) → Fiyat **yukarı** gitmiş, **satın alma baskısı**

---

### Örnek 2: Aşağı Trend (Negatif Displacement)

**Window: 15 dakika (14:15:00 - 14:30:00)**

```
Trade'ler:
14:15:10 → 21.70  (EN ESKİ)
14:20:30 → 21.60
14:25:15 → 21.55
14:30:00 → 21.50  (EN YENİ)
```

**Hesaplama:**
```
first_price = 21.70  (14:15:10)
last_price = 21.50   (14:30:00)
displacement = 21.50 - 21.70 = -0.20
```

**Sonuç:** ❌ **-0.20** (Negatif) → Fiyat **aşağı** gitmiş, **satış baskısı**

---

### Örnek 3: Denge (Sıfır Displacement)

**Window: 15 dakika (14:15:00 - 14:30:00)**

```
Trade'ler:
14:15:10 → 21.60  (EN ESKİ)
14:18:20 → 21.55
14:22:05 → 21.65
14:27:30 → 21.58
14:30:00 → 21.60  (EN YENİ)
```

**Hesaplama:**
```
first_price = 21.60  (14:15:10)
last_price = 21.60   (14:30:00)
displacement = 21.60 - 21.60 = 0.00
```

**Sonuç:** ⚖️ **0.00** (Sıfır) → Fiyat **değişmemiş**, **dengeli**

---

## ⚠️ ÖNEMLİ NOTLAR

### 1. "First" ve "Last" = Zaman'a Göre, Eklenme Sırasına Göre Değil!

**YANLIŞ DÜŞÜNCE:**
```
"First" = Tick store'a ilk eklenen tick
"Last" = Tick store'a son eklenen tick
```

**DOĞRU:**
```
"First" = Window içindeki EN ESKİ tick (timestamp'e göre)
"Last" = Window içindeki EN YENİ tick (timestamp'e göre)
```

**Neden?**
- Tick'ler farklı zamanlarda eklenebilir
- İlk eklenen tick, en eski tick olmayabilir!
- Bu yüzden **timestamp'e göre** sıralama yapılır

---

### 2. Sadece Gerçek Trade'ler Sayılır

**Hariç tutulanlar:**
- ❌ Bid/ask update'leri (`size=0`)
- ❌ Pseudo-ticks (`bf=true`)
- ❌ Aşırı büyük trade'ler (`size > avg_adv`)

**Neden?**
- Bid/ask update'leri gerçek trade değil
- Pseudo-ticks OHLC backfill'den gelir (sahte data)
- Aşırı büyük trade'ler FINRA/ADFN print'leri (institutional)

---

### 3. Window Sürekli "Kayar" (Rolling)

**Rolling Window Mantığı:**

```
Saat 14:30:00 → Window: 14:15:00 - 14:30:00
Saat 14:31:00 → Window: 14:16:00 - 14:31:00  (1 dakika kaydı)
Saat 14:32:00 → Window: 14:17:00 - 14:32:00  (1 dakika kaydı)
```

**Her yeni trade'de:**
- Eski trade'ler window'dan çıkar
- Yeni trade'ler window'a girer
- Displacement yeniden hesaplanır

---

## 🐛 OLASI SORUNLAR

### Sorun 1: Timestamp Parsing Hatası

**Belirti:**
```
time_diff = 0.0s  (Tüm tick'ler aynı timestamp'e sahip)
```

**Neden:**
- Timestamp parse edilemiyor
- Tüm tick'ler `datetime.now()` alıyor
- Sıralama çalışmıyor

**Çözüm:**
- Timestamp parsing'i düzelt (ISO 8601 format)
- UTC timezone kullan

---

### Sorun 2: Symbol Mapping Karışması

**Belirti:**
```
WRB-E için displacement yanlış
Ama WRB-PRH'nin tick'leri WRB-E'ye karışmış
```

**Neden:**
- Symbol mapping hatası
- Farklı symbol'lerin tick'leri karışıyor

**Çözüm:**
- Symbol mapping log'larını kontrol et
- Her tick'in doğru symbol'e ait olduğundan emin ol

---

### Sorun 3: Window Filtreleme Hatası

**Belirti:**
```
Window: 14:15:00 - 14:30:00
Ama 14:10:00'daki tick kullanılıyor
```

**Neden:**
- Window filtresi yanlış çalışıyor
- Eski tick'ler window'a dahil oluyor

**Çözüm:**
- Window start/end zamanlarını kontrol et
- Tick'lerin window içinde olduğundan emin ol

---

## 📝 ÖZET

**Price Displacement:**
1. **Zaman penceresi** belirlenir (örn: son 15 dakika)
2. **Gerçek trade'ler** filtrelenir (bid/ask update'leri hariç)
3. Tick'ler **timestamp'e göre** sıralanır
4. **İlk fiyat** = En eski tick'in fiyatı
5. **Son fiyat** = En yeni tick'in fiyatı
6. **Displacement** = Son fiyat - İlk fiyat

**Yorum:**
- **Pozitif (+)** → Yukarı trend, satın alma baskısı
- **Negatif (-)** → Aşağı trend, satış baskısı
- **Sıfır (0)** → Dengeli, fiyat değişmemiş

**Önemli:**
- Sadece **gerçek trade'ler** kullanılır
- **Timestamp'e göre** sıralama yapılır
- Window **sürekli kayar** (rolling)


