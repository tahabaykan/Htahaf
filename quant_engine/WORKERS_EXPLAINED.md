# Worker'ların Detaylı Açıklaması

Bu dokümantasyon, sistemdeki üç ana worker'ın (Decision Helper, Decision Helper V2, ve Deeper Analysis) ne yaptığını, hangi metrikleri hesapladığını ve nasıl çalıştığını detaylı olarak açıklar.

---

## 📊 1. DECISION HELPER WORKER

### 🎯 Genel Amaç
Decision Helper Worker, piyasadaki **kısa vadeli fiyat hareketlerini** analiz ederek, bir hisse senedinin belirli bir zaman diliminde **alıcı mı yoksa satıcı mı baskın** olduğunu belirler. Bu bilgi, **ne zaman alım/satım yapılacağına** karar vermek için kullanılır.

### ⏱️ Zaman Pencereleri (Time Windows)
Worker, üç farklı zaman diliminde analiz yapar:
- **5 dakika (5m)**: Çok kısa vadeli hareketler
- **15 dakika (15m)**: Kısa vadeli trendler
- **30 dakika (30m)**: Orta vadeli hareketler

### 📈 Hesaplanan Metrikler

#### 1. **Price Displacement (Fiyat Yer Değiştirmesi)**
**Ne demek?**
- Belirli bir zaman penceresinde (örneğin son 15 dakika) ilk işlem fiyatı ile son işlem fiyatı arasındaki fark.
- **Örnek**: Bir hisse 15 dakika önce $20.50'den işlem görmüşse ve şimdi $20.65'ten işlem görüyorsa, displacement = $0.15 (yukarı yönlü).

**Neden önemli?**
- Pozitif değer = Fiyat yükselmiş (alıcılar baskın)
- Negatif değer = Fiyat düşmüş (satıcılar baskın)
- Sıfıra yakın = Fiyat sabit (dengeli piyasa)

#### 2. **ADV Fraction (Günlük Ortalama Hacim Oranı)**
**Ne demek?**
- ADV = Average Daily Volume (Günlük Ortalama Hacim)
- Belirli bir zaman penceresinde işlem gören toplam hacmin, o hissenin günlük ortalama hacmine oranı.
- **Örnek**: Bir hissenin günlük ortalaması 100,000 lot ise ve son 15 dakikada 5,000 lot işlem görmüşse, ADV Fraction = 5,000 / 100,000 = 0.05 (yani %5).

**Neden önemli?**
- Yüksek ADV Fraction = O zaman diliminde normalden fazla işlem var (yoğun aktivite)
- Düşük ADV Fraction = O zaman diliminde normalden az işlem var (sessiz piyasa)
- Bu, piyasanın **ne kadar aktif** olduğunu gösterir.

#### 3. **Aggressor Proxy (Saldırganlık Ölçüsü)**
**Ne demek?**
- Her işlemde, alıcı mı yoksa satıcı mı daha "saldırgan" olduğunu ölçer.
- **Alıcı saldırgan**: İşlem fiyatı, ask (satış) fiyatına eşit veya yüksekse → Alıcı, satıcının fiyatını kabul etmiş (saldırgan alım)
- **Satıcı saldırgan**: İşlem fiyatı, bid (alış) fiyatına eşit veya düşükse → Satıcı, alıcının fiyatını kabul etmiş (saldırgan satım)
- **Net Pressure**: Tüm işlemlerdeki saldırganlık toplamı / toplam hacim

**Neden önemli?**
- Pozitif Net Pressure = Alıcılar daha saldırgan (fiyat yükselme eğilimi)
- Negatif Net Pressure = Satıcılar daha saldırgan (fiyat düşme eğilimi)
- Bu, piyasadaki **güç dengesini** gösterir.

#### 4. **Efficiency (Verimlilik)**
**Ne demek?**
- Fiyatın ne kadar "verimli" hareket ettiğini ölçer.
- Formül: `|Price Displacement| / ADV Fraction`
- **Örnek**: Fiyat $0.15 yükselmiş ve ADV Fraction 0.05 ise, Efficiency = 0.15 / 0.05 = 3.0

**Neden önemli?**
- Yüksek Efficiency = Az hacimle çok fiyat hareketi (verimli hareket, güçlü trend)
- Düşük Efficiency = Çok hacimle az fiyat hareketi (verimsiz, direnç var)
- Bu, piyasanın **ne kadar "kolay" hareket ettiğini** gösterir.

#### 5. **Trade Frequency (İşlem Sıklığı)**
**Ne demek?**
- Belirli bir zaman diliminde dakika başına düşen işlem sayısı.
- **Örnek**: Son 15 dakikada 30 işlem olmuşsa, Trade Frequency = 30 / 15 = 2 işlem/dakika

**Neden önemli?**
- Yüksek Trade Frequency = Sık işlem (aktif piyasa)
- Düşük Trade Frequency = Seyrek işlem (sessiz piyasa)
- Bu, piyasanın **ne kadar "canlı"** olduğunu gösterir.

### 🎭 Piyasa Durumu Sınıflandırması (Market State Classification)

Worker, hesaplanan metrikleri kullanarak piyasayı 5 farklı duruma sınıflandırır:

1. **BUYER_DOMINANT (Alıcı Baskın)**
   - Fiyat yükseliyor, alıcılar saldırgan, yüksek verimlilik
   - **Anlamı**: Güçlü alım baskısı var, fiyat yükselme eğiliminde

2. **SELLER_DOMINANT (Satıcı Baskın)**
   - Fiyat düşüyor, satıcılar saldırgan, yüksek verimlilik
   - **Anlamı**: Güçlü satım baskısı var, fiyat düşme eğiliminde

3. **SELLER_VACUUM (Satıcı Boşluğu)**
   - Fiyat yükseliyor ama çok az hacim var
   - **Anlamı**: Satıcı yok, alıcılar kolayca fiyatı yukarı itiyor

4. **ABSORPTION (Emilim)**
   - Fiyat sabit kalıyor ama yüksek hacim var
   - **Anlamı**: Alıcı ve satıcı dengeli, fiyat hareket etmiyor (konsolidasyon)

5. **NEUTRAL (Nötr)**
   - Belirgin bir yön yok
   - **Anlamı**: Piyasa kararsız, net bir trend yok

### 🔄 Nasıl Çalışır?

1. **Veri Toplama**: Worker, Hammer Pro'dan gerçek zamanlı işlem verilerini (ticks) toplar
2. **Filtreleme**: Sadece gerçek işlemleri kullanır (bid/ask güncellemeleri değil, sadece gerçek alım/satım işlemleri)
3. **Zaman Penceresi Analizi**: Her zaman penceresi için (5m, 15m, 30m) metrikleri hesaplar
4. **Sınıflandırma**: Hesaplanan metrikleri kullanarak piyasa durumunu belirler
5. **Sonuçları Kaydetme**: Sonuçları Redis'e kaydeder, böylece frontend ve diğer sistemler kullanabilir

---

## 📊 2. DECISION HELPER V2 WORKER

### 🎯 Genel Amaç
Decision Helper V2 Worker, **daha az likit (illiquid) hisse senetleri** için özel olarak tasarlanmış bir analiz motorudur. V1'den farklı olarak, **modal price flow (en sık görülen fiyat akışı)** kullanır ve **tek seferlik anormal işlemleri (outliers) görmezden gelir**.

### ⏱️ Zaman Pencereleri (Time Windows)
Worker, beş farklı zaman diliminde analiz yapar:
- **10 dakika (pan_10m)**: Çok kısa vadeli
- **30 dakika (pan_30m)**: Kısa vadeli
- **1 saat (pan_1h)**: Orta vadeli
- **3 saat (pan_3h)**: Uzun vadeli
- **1 gün (pan_1d)**: Günlük trend

### 📈 Hesaplanan Metrikler

#### 1. **GRPAN1 ve GRPAN2 (Modal Price - En Sık Görülen Fiyatlar)**
**Ne demek?**
- GRPAN = Grouped Real Print Analyzer (Gruplandırılmış Gerçek İşlem Analizörü)
- **GRPAN1**: Belirli bir zaman penceresinde en sık işlem gören fiyat (birincil konsantrasyon noktası)
- **GRPAN2**: GRPAN1'den en az $0.06 uzakta olan ikinci en sık işlem gören fiyat (ikincil konsantrasyon noktası)

**Nasıl Hesaplanır?**
- Her işlem, lot büyüklüğüne göre ağırlıklandırılır:
  - **100, 200, 300 lot işlemler**: Ağırlık = 1.0 (tam ağırlık)
  - **Diğer işlemler**: Ağırlık = 0.25 (çeyrek ağırlık)
- Tüm işlemler fiyatlarına göre gruplandırılır
- En yüksek ağırlığa sahip fiyat = GRPAN1
- GRPAN1'den $0.06+ uzakta, en yüksek ağırlığa sahip fiyat = GRPAN2

**Neden önemli?**
- Likit olmayan hisselerde, tek bir anormal işlem fiyatı çarpıtabilir
- GRPAN, **en sık görülen fiyatı** bulur, bu daha güvenilir bir referans noktasıdır
- GRPAN1 ve GRPAN2 arasındaki fark, **spread kalitesini** gösterir

#### 2. **Modal Displacement (Modal Yer Değiştirmesi)**
**Ne demek?**
- Zaman penceresinin başındaki GRPAN1 ile sonundaki GRPAN1 arasındaki fark
- **Örnek**: Son 1 saatte başlangıçtaki GRPAN1 = $20.50, şimdiki GRPAN1 = $20.65 ise, Modal Displacement = $0.15

**Neden önemli?**
- V1'deki "Price Displacement" gibi, ama **modal fiyat** kullanır (daha güvenilir)
- Likit olmayan hisselerde, tek bir anormal işlem displacement'i çarpıtabilir
- Modal displacement, **gerçek trendi** daha iyi yansıtır

#### 3. **RWVAP (Robust Volume-Weighted Average Price - Sağlam Hacim Ağırlıklı Ortalama Fiyat)**
**Ne demek?**
- VWAP (Volume-Weighted Average Price) benzeri, ama **aşırı hacimli işlemler hariç tutulur**
- **Aşırı hacimli işlem**: İşlem hacmi, günlük ortalama hacimden (AVG_ADV) büyükse
- **Örnek**: Bir hissenin günlük ortalaması 100,000 lot ise, 150,000 lotluk bir işlem "aşırı" sayılır ve RWVAP hesaplamasından çıkarılır

**Neden önemli?**
- FINRA prints (büyük blok transferler) ve diğer anormal işlemler VWAP'ı çarpıtabilir
- RWVAP, **normal piyasa aktivitesini** daha iyi yansıtır
- Bu, daha güvenilir bir "ortalama fiyat" verir

#### 4. **RWVAP Diff (RWVAP Farkı)**
**Ne demek?**
- Zaman penceresinin başındaki RWVAP ile sonundaki RWVAP arasındaki fark
- **Örnek**: Son 1 saatte başlangıçtaki RWVAP = $20.50, şimdiki RWVAP = $20.60 ise, RWVAP Diff = $0.10

**Neden önemli?**
- Modal Displacement'e benzer, ama **hacim ağırlıklı ortalama** kullanır
- Bu, **hacim etkisini** de hesaba katar

#### 5. **ADV Fraction (Günlük Ortalama Hacim Oranı)**
**Ne demek?**
- V1'deki gibi, belirli bir zaman penceresinde işlem gören toplam hacmin, günlük ortalama hacme oranı

#### 6. **Flow Efficiency (Akış Verimliliği)**
**Ne demek?**
- Modal Displacement'in, ADV Fraction'a oranı
- Formül: `|Modal Displacement| / ADV Fraction`
- **Örnek**: Modal Displacement = $0.15, ADV Fraction = 0.05 ise, Flow Efficiency = 3.0

**Neden önemli?**
- V1'deki "Efficiency" gibi, ama **modal fiyat** kullanır
- Yüksek Flow Efficiency = Az hacimle çok fiyat hareketi (güçlü trend)

#### 7. **SRPAN Score (Spread Real Print Analyzer Score - Spread Kalite Skoru)**
**Ne demek?**
- GRPAN1 ve GRPAN2 arasındaki spread'in (fark) kalitesini ölçer
- Skor 0-100 arası:
  - **0**: Spread çok dar ($0.06 veya daha az) - kötü kalite
  - **100**: Spread optimal ($0.30 veya daha fazla) - mükemmel kalite
  - **Aralarında**: Doğrusal interpolasyon

**Nasıl Hesaplanır?**
- **Balance Score (%60)**: GRPAN1 ve GRPAN2 konsantrasyonlarının dengeli olması
- **Total Score (%15)**: GRPAN1 + GRPAN2 toplam konsantrasyonunun yüksek olması
- **Spread Score (%25)**: Spread genişliğinin optimal olması ($0.06 min, $0.30 optimal)

**Neden önemli?**
- Likit olmayan hisselerde, spread kalitesi çok önemlidir
- Yüksek SRPAN Score = İyi spread kalitesi, işlem yapmak daha kolay
- Düşük SRPAN Score = Kötü spread kalitesi, işlem yapmak riskli

#### 8. **Outlier Ratio (Anormal İşlem Oranı)**
**Ne demek?**
- Zaman penceresindeki toplam işlem sayısının, GRPAN1 ve GRPAN2 konsantrasyonlarına dahil olmayan işlem sayısına oranı
- **Örnek**: 100 işlem var, 80'i GRPAN1/GRPAN2 konsantrasyonunda, 20'si dışında ise, Outlier Ratio = 20/100 = 0.20 (%20)

**Neden önemli?**
- Yüksek Outlier Ratio = Çok fazla anormal işlem var (güvenilirlik düşük)
- Düşük Outlier Ratio = İşlemler konsantre (güvenilirlik yüksek)

#### 9. **RFS (Real Flow Score - Gerçek Akış Skoru)**
**Ne demek?**
- Tüm metrikleri birleştiren **tek bir skor** (-1.0 ile +1.0 arası)
- Pozitif = Alıcı akışı (yükseliş eğilimi)
- Negatif = Satıcı akışı (düşüş eğilimi)
- Sıfıra yakın = Nötr

**Nasıl Hesaplanır?**
- **%30**: Modal Displacement (normalize edilmiş)
- **%20**: RWVAP Diff (normalize edilmiş)
- **%20**: SRPAN Score (yönlü: yükselişte pozitif, düşüşte negatif)
- **%15**: Flow Efficiency (yönlü)
- **%15**: Net Pressure (aggressor-based)

**Neden önemli?**
- Tüm metrikleri tek bir skorda birleştirir
- Karar vermeyi kolaylaştırır: RFS > 0.40 = Alım, RFS < -0.40 = Satım

### 🎭 Piyasa Durumu Sınıflandırması

1. **BUYER_DOMINANT (Alıcı Baskın)**
   - RFS > 0.40
   - Modal fiyat yükseliyor, alıcı akışı güçlü

2. **SELLER_DOMINANT (Satıcı Baskın)**
   - RFS < -0.40
   - Modal fiyat düşüyor, satıcı akışı güçlü

3. **ABSORPTION (Emilim)**
   - Modal Displacement çok küçük (< $0.03) ama ADV Fraction yüksek (> 0.10)
   - Yüksek hacim var ama fiyat hareket etmiyor

4. **VACUUM (Boşluk)**
   - Modal Displacement büyük (> $0.10) ama ADV Fraction düşük (< 0.05)
   - Fiyat hareket ediyor ama çok az hacim var

5. **NEUTRAL (Nötr)**
   - Diğer durumlar

### 🔄 V1'den Farklar

1. **Modal Price Flow**: İlk/son fiyat yerine, en sık görülen fiyat (GRPAN1) kullanılır
2. **Outlier Ignoring**: Tek seferlik anormal işlemler görmezden gelinir
3. **Daha Uzun Pencereler**: 1 güne kadar pencereler (V1'de maksimum 30 dakika)
4. **SRPAN Score**: Spread kalitesi ölçülür
5. **RWVAP**: Aşırı hacimli işlemler hariç tutulur

---

## 📊 3. DEEPER ANALYSIS WORKER

### 🎯 Genel Amaç
Deeper Analysis Worker, **en detaylı ve kapsamlı analizi** yapar. GRPAN, RWVAP, GOD (GRPAN Ortalama Sapma), ve ROD (RWVAP Ortalama Sapma) gibi **gelişmiş metrikleri** hesaplar. Bu worker, **uzun vadeli trend analizi** ve **piyasa mikro yapısı analizi** için kullanılır.

### ⏱️ Zaman Pencereleri (Time Windows)
Worker, altı farklı zaman diliminde analiz yapar:
- **10 dakika (pan_10m)**: Çok kısa vadeli
- **30 dakika (pan_30m)**: Kısa vadeli
- **1 saat (pan_1h)**: Orta vadeli
- **3 saat (pan_3h)**: Uzun vadeli
- **1 gün (pan_1d)**: Günlük trend
- **3 gün (pan_3d)**: Çok uzun vadeli trend

### 📈 Hesaplanan Metrikler

#### 1. **GRPAN (Grouped Real Print Analyzer)**
**Ne demek?**
- Decision Helper V2'deki gibi, **en sık işlem gören fiyat** (modal price)
- Ama Deeper Analysis'te, **her zaman penceresi için ayrı ayrı** hesaplanır

**Nasıl Hesaplanır?**
- Son 15 işlem (latest_pan) veya belirli bir zaman penceresindeki tüm işlemler kullanılır
- Lot büyüklüğüne göre ağırlıklandırma:
  - **100, 200, 300 lot**: Ağırlık = 1.0
  - **Diğerleri**: Ağırlık = 0.25
- En yüksek ağırlığa sahip fiyat = GRPAN Price

**GRPAN Metrikleri:**
- **grpan_price**: En sık işlem gören fiyat
- **concentration_percent**: GRPAN fiyatının ±$0.04 aralığındaki işlemlerin toplam ağırlığının yüzdesi
- **deviation_vs_last**: GRPAN fiyatının, son işlem fiyatından sapması
- **deviation_vs_prev_window**: GRPAN fiyatının, önceki zaman penceresindeki GRPAN fiyatından sapması

**Neden önemli?**
- GRPAN, **gerçek piyasa fiyatını** gösterir (bid/ask değil, gerçek işlem fiyatı)
- Yüksek concentration = İşlemler belirli bir fiyat etrafında toplanmış (güçlü destek/direnç)
- Deviation = GRPAN'ın, mevcut fiyattan ne kadar uzakta olduğunu gösterir

#### 2. **GOD (GRPAN Ortalama Sapma - GRPAN Average Deviation)**
**Ne demek?**
- Belirli bir zaman penceresindeki tüm işlem fiyatlarının, GRPAN fiyatından ortalama sapması
- **Örnek**: GRPAN = $20.50, işlemler $20.48, $20.51, $20.49, $20.52 ise, GOD = ortalama sapma

**Nasıl Hesaplanır?**
- Her işlem fiyatının, GRPAN fiyatından mutlak farkı alınır
- Bu farklar, lot büyüklüğüne göre ağırlıklandırılır
- Ağırlıklı ortalama = GOD

**Neden önemli?**
- Düşük GOD = İşlemler GRPAN etrafında sıkı toplanmış (düşük volatilite, güçlü konsantrasyon)
- Yüksek GOD = İşlemler GRPAN etrafında dağınık (yüksek volatilite, zayıf konsantrasyon)
- Bu, **fiyat istikrarını** gösterir

#### 3. **RWVAP (Robust Volume-Weighted Average Price)**
**Ne demek?**
- Decision Helper V2'deki gibi, **aşırı hacimli işlemler hariç tutularak** hesaplanan hacim ağırlıklı ortalama fiyat

**RWVAP Pencereleri:**
- **rwvap_1d**: Son 1 işlem günü
- **rwvap_3d**: Son 3 işlem günü
- **rwvap_5d**: Son 5 işlem günü

**RWVAP Metrikleri:**
- **rwvap**: Hacim ağırlıklı ortalama fiyat
- **rwvap_volume**: RWVAP hesaplamasına dahil edilen toplam hacim
- **rwvap_print_count**: RWVAP hesaplamasına dahil edilen işlem sayısı

**Neden önemli?**
- RWVAP, **gerçek piyasa ortalamasını** gösterir (anormal işlemler hariç)
- Son fiyattan sapma = Fiyatın ortalamadan ne kadar uzakta olduğunu gösterir

#### 4. **ROD (RWVAP Ortalama Sapma - RWVAP Average Deviation)**
**Ne demek?**
- Belirli bir zaman penceresindeki tüm işlem fiyatlarının, RWVAP'tan ortalama sapması
- GOD'a benzer, ama **RWVAP** referans alınır

**Neden önemli?**
- Düşük ROD = İşlemler RWVAP etrafında sıkı toplanmış (düşük volatilite)
- Yüksek ROD = İşlemler RWVAP etrafında dağınık (yüksek volatilite)
- Bu, **hacim ağırlıklı fiyat istikrarını** gösterir

#### 5. **SRPAN (Spread Real Print Analyzer)**
**Ne demek?**
- Decision Helper V2'deki gibi, **GRPAN1 ve GRPAN2 arasındaki spread kalitesini** ölçer
- Skor 0-100 arası

**Neden önemli?**
- Spread kalitesi, **işlem yapmanın ne kadar kolay/riskli** olduğunu gösterir

### 🎭 Piyasa Durumu Sınıflandırması

Deeper Analysis Worker, GRPAN ve RWVAP metriklerini kullanarak piyasayı analiz eder, ama **doğrudan bir "durum sınıflandırması" yapmaz**. Bunun yerine, **ham metrikleri** sağlar ve kullanıcı/kullanıcı arayüzü bu metrikleri yorumlar.

**Örnek Yorumlar:**
- **Yüksek GRPAN Concentration + Düşük GOD**: Güçlü destek/direnç seviyesi
- **Yüksek RWVAP + Pozitif Deviation**: Fiyat ortalamanın üzerinde (yükseliş eğilimi)
- **Düşük SRPAN Score**: Spread kalitesi kötü (işlem yapmak riskli)

### 🔄 Nasıl Çalışır?

1. **Trade Print Toplama**: Worker, GRPANTickFetcher kullanarak periyodik olarak gerçek işlem verilerini (trade prints) toplar
2. **GRPAN Hesaplama**: Her zaman penceresi için GRPAN hesaplanır
3. **RWVAP Hesaplama**: Her zaman penceresi için RWVAP hesaplanır
4. **GOD/ROD Hesaplama**: Sapma metrikleri hesaplanır
5. **SRPAN Hesaplama**: Spread kalitesi ölçülür
6. **Sonuçları Kaydetme**: Tüm metrikler DataFabric'e kaydedilir, frontend'de "Deeper Analysis" sayfasında gösterilir

### 🔄 Diğer Worker'lardan Farklar

1. **En Detaylı Analiz**: Tüm metrikleri en detaylı şekilde hesaplar
2. **Uzun Vadeli**: 3 güne kadar pencereler (diğerlerinde maksimum 1 gün)
3. **GOD/ROD**: Sapma metrikleri sadece burada hesaplanır
4. **Periyodik Güncelleme**: GRPANTickFetcher ile sürekli veri toplar (diğerleri sadece job geldiğinde çalışır)

---

## 📋 Özet Karşılaştırma

| Özellik | Decision Helper | Decision Helper V2 | Deeper Analysis |
|---------|----------------|-------------------|-----------------|
| **Amaç** | Kısa vadeli piyasa durumu | Likit olmayan hisseler için modal analiz | En detaylı uzun vadeli analiz |
| **Zaman Pencereleri** | 5m, 15m, 30m | 10m, 30m, 1h, 3h, 1d | 10m, 30m, 1h, 3h, 1d, 3d |
| **Ana Metrikler** | Price Displacement, ADV Fraction, Aggressor, Efficiency | GRPAN1/2, Modal Displacement, RWVAP, SRPAN, RFS | GRPAN, GOD, RWVAP, ROD, SRPAN |
| **Fiyat Referansı** | İlk/Son fiyat | Modal fiyat (GRPAN1) | Modal fiyat (GRPAN) |
| **Outlier Handling** | Yok | Var (görmezden gelinir) | Var (filtrelenir) |
| **Durum Sınıflandırması** | 5 durum (BUYER_DOMINANT, SELLER_DOMINANT, vb.) | 5 durum (RFS bazlı) | Yok (ham metrikler) |
| **Kullanım Senaryosu** | Hızlı karar verme | Likit olmayan hisseler | Detaylı analiz ve araştırma |

---

## 🎯 Hangi Worker'ı Ne Zaman Kullanmalı?

### Decision Helper Worker
- ✅ **Kısa vadeli işlemler** için
- ✅ **Hızlı karar verme** gerektiğinde
- ✅ **Likid hisseler** için
- ✅ **5-30 dakika** arası trend analizi

### Decision Helper V2 Worker
- ✅ **Likit olmayan hisseler** için (preferred stocks, CEFs)
- ✅ **Modal fiyat analizi** gerektiğinde
- ✅ **Outlier'ların önemli olduğu** durumlarda
- ✅ **1 güne kadar** trend analizi

### Deeper Analysis Worker
- ✅ **Detaylı araştırma** gerektiğinde
- ✅ **Uzun vadeli trend analizi** (3 güne kadar)
- ✅ **GOD/ROD gibi sapma metrikleri** gerektiğinde
- ✅ **Piyasa mikro yapısı analizi** için

---

## 📚 Terimler Sözlüğü

- **Tick**: Bir işlem (trade) - fiyat, hacim, zaman bilgisi içerir
- **Trade Print**: Gerçekleşmiş bir alım/satım işlemi
- **Bid**: Alıcının teklif ettiği en yüksek fiyat
- **Ask**: Satıcının teklif ettiği en düşük fiyat
- **Spread**: Ask - Bid (fiyat farkı)
- **Lot**: İşlem birimi (genellikle 100 hisse = 1 lot)
- **Volume**: Toplam işlem hacmi (kaç lot işlem görmüş)
- **ADV**: Average Daily Volume (Günlük Ortalama Hacim)
- **VWAP**: Volume-Weighted Average Price (Hacim Ağırlıklı Ortalama Fiyat)
- **Modal Price**: En sık görülen fiyat (istatistiksel mod)
- **Outlier**: Normal dışı, anormal işlem
- **Concentration**: İşlemlerin belirli bir fiyat etrafında toplanması
- **Deviation**: Sapma, fark
- **Volatility**: Fiyat değişkenliği, oynaklık
- **Liquidity**: Likidite - bir hissenin ne kadar kolay alınıp satılabileceği
- **Illiquid**: Likit olmayan - az işlem gören, zor alınıp satılan

---

*Bu dokümantasyon, sistemin mevcut durumunu yansıtmaktadır ve güncellemeler yapıldıkça revize edilecektir.*


