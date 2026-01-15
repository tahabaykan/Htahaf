# RUN_WEEKLY_N - Haftalık Veri İşleme Pipeline Detaylı Özet

## 📋 GENEL BAKIŞ

`run_weekly_n.py` script'i, ABD preferred stock piyasası için haftalık veri işleme pipeline'ını çalıştırır. Bu pipeline, ham verilerden başlayarak trading için kullanılacak `janalldata.csv` dosyasını oluşturur. Her adım, bir önceki adımın çıktısını alır ve bir sonraki adıma girdi olarak verir.

---

## 🔄 VERİ AKIŞI DİYAGRAMI

```
ek*.csv (Ham Veriler)
    ↓
[nibkrtry.py] → sek*.csv (IBKR'den güncel fiyatlar)
    ↓
[ncorrex.py] → sek*.csv (Ex-dividend date düzeltmeleri)
    ↓
[nnormalize_data.py] → nek*.csv (Normalize edilmiş veriler)
    ↓
[nmaster_processor.py] → yek*.csv (Cally hesaplamaları, Treasury benchmarks)
    ↓
[nbefore_common_adv.py] → advek*.csv (ADV verileri eklendi)
    ↓
[ncommon_stocks.py] → comek*.csv (Common stock verileri eklendi)
    ↓
[ncalculate_scores.py] → allcomek.csv (Skor hesaplamaları)
    ↓
[nfill_missing_solidity_data.py] → allcomek_sld.csv (Solidity verileri dolduruldu)
    ↓
[nmarket_risk_analyzer.py] → Market risk analizi
    ↓
[ncalculate_thebest.py] → finek*.csv (FINAL_THG hesaplamaları)
    ↓
[nget_short_fee_rates.py] → nsmiall.csv (Short fee rates)
    ↓
[noptimize_shorts.py] → ssfinek*.csv (SHORT_FINAL hesaplamaları, LONG/SHORT seçimi)
    ↓
[ntumcsvport.py] → ssfinek*.csv (Portfolio seçimi)
    ↓
[npreviousadd.py] → janek_ssfinek*.csv (prev_close eklendi)
    ↓
[merge_csvs.py] → janalldata.csv (Tüm dosyalar birleştirildi)
    ↓
[gorter.py] → gort_analysis.csv (GORT analizi)
```

---

## 📝 SCRIPT DETAYLARI

### 1. **nibkrtry.py** - IBKR'den Güncel Fiyat Verileri Çekme

#### Ne Yapar?
IBKR TWS/Gateway API üzerinden preferred stock'lar için güncel fiyat verilerini çeker ve CSV dosyalarını günceller.

#### Girdi CSV'leri:
- `ekheldbesmaturlu.csv`
- `ekheldcilizyeniyedi.csv`
- `ekheldcommonsuz.csv`
- `ekhelddeznff.csv`
- `ekheldff.csv`
- `ekheldflr.csv`
- `ekheldgarabetaltiyedi.csv`
- `ekheldkuponlu.csv`
- `ekheldkuponlukreciliz.csv`
- `ekheldkuponlukreorta.csv`
- `ekheldnff.csv`
- `ekheldotelremorta.csv`
- `ekheldsolidbig.csv`
- `ekheldtitrekhc.csv`
- `ekhighmatur.csv`
- `eknotbesmaturlu.csv`
- `eknotcefilliquid.csv`
- `eknottitrekhc.csv`
- `ekrumoreddanger.csv`
- `eksalakilliquid.csv`
- `ekshitremhc.csv`

#### Çıktı CSV'leri:
- `sekheldbesmaturlu.csv` (ek → sek prefix değişimi)
- `sekheldcilizyeniyedi.csv`
- ... (tüm ek* dosyaları sek* olarak kaydedilir)

#### Değişiklikler:
- **Last Price**: IBKR'den güncel son fiyat
- **Oct19_diff**: 19 Ekim 2022'ye göre fiyat değişimi
- **Aug2022_diff**: Ağustos 2022'ye göre fiyat değişimi
- **SMA20, SMA63, SMA246**: Simple Moving Average değerleri
- **SMA20 chg, SMA63 chg, SMA246 chg**: SMA değişim yüzdeleri
- **3M Low, 3M High, 6M Low, 6M High, 1Y Low, 1Y High**: Zaman aralığına göre en düşük/en yüksek fiyatlar
- **TIME TO DIV**: Normalize edilmiş (90 günlük mod sistemi, 0 yerine 90 yazılır)

#### Neden Yapılıyor?
- Güncel piyasa fiyatlarını almak için
- Teknik analiz için SMA ve fiyat aralıkları hesaplamak için
- TIME TO DIV değerlerini normalize etmek için (90 günlük mod sistemi)

---

### 2. **ncorrex.py** - Ex-Dividend Date Düzeltme

#### Ne Yapar?
CNBC web scraping ile ex-dividend date bilgilerini çeker ve TIME TO DIV değerlerini düzeltir. Ayrıca kaynak ek* dosyalarına da güncel EX-DIV DATE bilgilerini yazar.

#### Girdi CSV'leri:
- `sek*.csv` dosyaları (nibkrtry.py'den gelen)

#### Çıktı CSV'leri:
- `sek*.csv` (güncellenmiş, TIME TO DIV düzeltilmiş)
- Kaynak `ek*.csv` dosyaları (EX-DIV DATE güncellenmiş)

#### Değişiklikler:
- **TIME TO DIV**: CNBC'den çekilen ex-dividend date'e göre düzeltilir
- **EX-DIV DATE**: Kaynak ek* dosyalarına yazılır

#### Neden Yapılıyor?
- TIME TO DIV değerlerinin doğruluğunu sağlamak için
- Ex-dividend date bilgilerini güncellemek için
- Dividend timing analizi için kritik veri

---

### 3. **nnormalize_data.py** - Veri Normalizasyonu

#### Ne Yapar?
CSV dosyalarındaki değerleri normalize eder, boş değerleri ortalama ile doldurur, Excel formüllerini taklit eder.

#### Girdi CSV'leri:
- `sek*.csv` dosyaları

#### Çıktı CSV'leri:
- `nek*.csv` dosyaları (normalize edilmiş)

#### Değişiklikler:
- **Normalize Edilen Kolonlar**:
  - SMA değişimleri (-15 ile 15 arası değerler için normalize)
  - 6 aylık değişimler (-8 ile 15 arası değerler için normalize)
  - Boş değerler ortalama ile doldurulur
- **Normalizasyon Formülü**: 
  - En negatif değer = 90 puan
  - En pozitif değer = 10 puan
  - Arasındaki değerler lineer interpolasyon

#### Neden Yapılıyor?
- Farklı ölçeklerdeki verileri karşılaştırılabilir hale getirmek için
- Skorlama sistemine hazırlık için
- Eksik verileri doldurmak için

---

### 4. **nmaster_processor.py** - Cally Hesaplamaları ve Treasury Benchmarks

#### Ne Yapar?
Treasury yield'larını günceller, Cally (Call Yield) değerlerini hesaplar, Treasury benchmark'larını ve Adj Risk Premium'u hesaplar.

#### Alt Script'ler:
1. `create_yek_files.py`: nek*.csv → yek*.csv (boş Cally kolonları eklenir)
2. `ntreyield.py`: Treasury yield'ları güncelle (US15Y dahil)
3. `nyield_calculator.py`: Cally değerleri hesaplanır (15Y dahil)
4. `update_normal_treasury_benchmark.py`: Normal Treasury benchmark'ları
5. `update_adjusted_treasury_benchmark.py`: Adjusted Treasury benchmark'ları (US15Y dahil)
6. `add_adj_risk_premium.py`: Adj Risk Premium (US15Y dahil)

#### Girdi CSV'leri:
- `nek*.csv` dosyaları
- `treyield.csv` (Treasury yield verileri)

#### Çıktı CSV'leri:
- `yek*.csv` dosyaları (Cally hesaplamaları ile)

#### Değişiklikler:
- **Cally Kolonları**: Call yield değerleri hesaplanır
- **Treasury Benchmarks**: Normal ve adjusted Treasury benchmark'ları
- **Adj Risk Premium**: Adjusted risk premium hesaplanır
- **US15Y**: 15 yıllık Treasury yield dahil edilir

#### Neden Yapılıyor?
- Preferred stock'ların call risk'ini hesaplamak için
- Treasury benchmark'ları ile karşılaştırma yapmak için
- Risk premium hesaplamak için

---

### 5. **nbefore_common_adv.py** - ADV (Average Daily Volume) Verileri

#### Ne Yapar?
IBKR Gateway üzerinden her hisse için ortalama günlük hacim (ADV) verilerini çeker ve CSV dosyalarına ekler.

#### Girdi CSV'leri:
- `yek*.csv` dosyaları

#### Çıktı CSV'leri:
- `advek*.csv` dosyaları (ADV verileri ile)

#### Değişiklikler:
- **ADV_6M**: Son 6 aylık ortalama günlük hacim
- **ADV_3M**: Son 3 aylık ortalama günlük hacim
- **ADV_15D**: Son 15 günlük ortalama günlük hacim
- **AVG_ADV**: Ortalama ADV (6M, 3M, 15D ortalaması)

#### Neden Yapılıyor?
- Likidite analizi için
- Lot hesaplamaları için (AVG_ADV bazlı)
- RWVAP extreme volume filter için (AVG_ADV * multiplier)

---

### 6. **ncommon_stocks.py** - Common Stock Verileri

#### Ne Yapar?
IBKR'den common stock fiyat verilerini çeker ve preferred stock verilerine ekler. Common stock performans metriklerini hesaplar.

#### Girdi CSV'leri:
- `advek*.csv` dosyaları

#### Çıktı CSV'leri:
- `comek*.csv` dosyaları (common stock verileri ile)

#### Değişiklikler:
- **COM_LAST_PRICE**: Common stock son fiyatı
- **COM_3M_PRICE**: 3 ay önceki common stock fiyatı
- **COM_6M_PRICE**: 6 ay önceki common stock fiyatı
- **COM_52W_HIGH**: 52 hafta en yüksek fiyat
- **COM_5Y_HIGH**: 5 yıl en yüksek fiyat
- **3M_PERF, 6M_PERF**: 3/6 aylık performans
- **RECENT_TOTAL**: Son performans toplamı

#### Neden Yapılıyor?
- Preferred stock'ların common stock ile korelasyonunu analiz etmek için
- Common stock performansını preferred stock skorlamasına dahil etmek için
- Relative value analizi için

---

### 7. **ncalculate_scores.py** - Skor Hesaplamaları

#### Ne Yapar?
Tüm comek*.csv dosyalarını birleştirir, skor hesaplamaları yapar, normalize eder, eksik değerleri doldurur.

#### Girdi CSV'leri:
- `comek*.csv` dosyaları
- `ek*.csv` dosyaları (CRDT_SCORE için)

#### Çıktı CSV'leri:
- `allcomek.csv` (birleştirilmiş, skorlanmış)

#### Değişiklikler:
- **CRDT_SCORE**: Credit score (eksik değerler 8 ile doldurulur)
- **CRDT_NORM**: Normalize edilmiş credit score (1-100 arası)
- **COM_* Kolonları**: Eksik değerler ortalama ile doldurulur
- **3M_PERF, 6M_PERF, RECENT_TOTAL**: Yeniden hesaplanır
- **52W_HIGH_SKOR, 5Y_HIGH_SKOR**: Fiyat/High oranına göre skor (10-90 arası)
- **Tüm numerik kolonlar**: 2 ondalık basamağa yuvarlanır

#### Neden Yapılıyor?
- Tüm verileri tek bir dosyada toplamak için
- Skorlama sistemine hazırlık için
- Eksik verileri doldurmak için

---

### 8. **nfill_missing_solidity_data.py** - Solidity Verilerini Doldurma

#### Ne Yapar?
Solidity (güvenilirlik) skorlarını hesaplar ve eksik değerleri doldurur.

#### Girdi CSV'leri:
- `allcomek.csv` (ncalculate_scores.py'den)
- `sldek*.csv` dosyaları (solidity verileri)

#### Çıktı CSV'leri:
- `allcomek_sld.csv` (solidity verileri ile)

#### Değişiklikler:
- **SOLIDITY_SCORE**: Solidity skoru hesaplanır veya doldurulur
- **SOLIDITY_NORM**: Normalize edilmiş solidity skoru

#### Neden Yapılıyor?
- Preferred stock'ların güvenilirlik skorunu hesaplamak için
- FINAL_THG hesaplamasında kullanılmak üzere

---

### 9. **nmarket_risk_analyzer.py** - Market Risk Analizi

#### Ne Yapar?
ETF'ler (SPY, IWM, HYG, KRE, TLT, VXX) ve endeksler üzerinden piyasa risk analizi yapar.

#### Girdi CSV'leri:
- Mevcut CSV dosyaları (risk analizi için)

#### Çıktı CSV'leri:
- Risk analizi raporu (CSV veya log)

#### Değişiklikler:
- **RISK_ON/RISK_OFF**: Risk iştahı göstergeleri
- **SMA Diffs**: ETF'lerin SMA farkları
- **Price Changes**: 2, 5, 15 günlük fiyat değişimleri

#### Neden Yapılıyor?
- Piyasa koşullarını anlamak için
- Risk yönetimi için
- Market timing için

---

### 10. **ncalculate_thebest.py** - FINAL_THG Hesaplama

#### Ne Yapar?
Preferred stock'lar için FINAL_THG (Final Front Buy) skorunu hesaplar. Bu skor, solidity, yield, ADV, adj risk premium, solcall score, credit score gibi faktörlerin ağırlıklı toplamıdır.

#### Girdi CSV'leri:
- `advek*.csv` dosyaları
- `allcomek_sld.csv` (solidity verileri)
- `sek*.csv` dosyaları (Adj Risk Premium için)
- `yek*.csv` dosyaları (Cally, Treasury benchmarks için)
- `market_weights.csv` (piyasa ağırlıkları)

#### Çıktı CSV'leri:
- `finek*.csv` dosyaları (FINAL_THG ile)

#### Değişiklikler:
- **FINAL_THG**: Final Front Buy skoru hesaplanır
  - Formül: `solidity_weight * SOLIDITY_SCORE + yield_weight * YIELD + adv_weight * AVG_ADV + adj_risk_premium_weight * ADJ_RISK_PREMIUM + solcall_score_weight * SOLCALL_SCORE + credit_score_norm_weight * CRDT_NORM + ...`
- **Piyasa Ağırlıkları**: `market_weights.csv`'den dinamik olarak yüklenir

#### Neden Yapılıyor?
- Preferred stock'ları skorlamak için
- Trading kararları için
- LONG pozisyon seçimi için

---

### 11. **nget_short_fee_rates.py** - Short Fee Rate (SMI) Verileri

#### Ne Yapar?
IBKR'den her hisse için short fee rate (SMI - Short Market Interest) verilerini çeker.

#### Girdi CSV'leri:
- `ek*.csv` dosyaları (hisse listesi için)

#### Çıktı CSV'leri:
- `nsmiall.csv` (tüm hisseler için SMI değerleri)

#### Değişiklikler:
- **SMI**: Short fee rate değeri (IBKR'den çekilir)
- **FEE_RATE**: Alternatif fee rate değeri

#### Neden Yapılıyor?
- SHORT_FINAL hesaplaması için (FINAL_THG + SMI*1000)
- Short pozisyon maliyetlerini hesaplamak için

---

### 12. **noptimize_shorts.py** - SHORT_FINAL Hesaplama ve Optimizasyon

#### Ne Yapar?
FINEK dosyalarından SHORT_FINAL skorunu hesaplar (FINAL_THG + SMI*1000), en düşük SHORT_FINAL değerine sahip hisseleri bulur.

#### Girdi CSV'leri:
- `finek*.csv` dosyaları
- `nsmiall.csv` (SMI verileri)

#### Çıktı CSV'leri:
- `ssfinek*.csv` dosyaları (SHORT_FINAL ile)

#### Değişiklikler:
- **SHORT_FINAL**: `FINAL_THG + (SMI * 1000)` formülü ile hesaplanır
- **SMI**: Eksik değerler ortalama ile doldurulur

#### Neden Yapılıyor?
- SHORT pozisyon seçimi için
- Short maliyetlerini FINAL_THG'ye eklemek için
- En düşük SHORT_FINAL = en iyi short fırsatı

---

### 13. **ntumcsvport.py** - Portfolio Seçimi (LONG/SHORT)

#### Ne Yapar?
SSFINEK dosyalarından her dosya için özel kurallara göre LONG ve SHORT hisseleri seçer.

#### Girdi CSV'leri:
- `ssfinek*.csv` dosyaları

#### Çıktı CSV'leri:
- `ssfinek*.csv` (güncellenmiş, LONG/SHORT işaretli)

#### Değişiklikler:
- **LONG/SHORT Seçimi**: Her dosya için özel kurallar:
  - `long_percent`: En yüksek FINAL_THG'ye sahip %X hisse (LONG)
  - `long_multiplier`: FINAL_THG çarpanı
  - `short_percent`: En düşük SHORT_FINAL'ye sahip %X hisse (SHORT)
  - `short_multiplier`: SHORT_FINAL çarpanı
  - `max_short`: Maksimum short sayısı
- **Örnek Kurallar**:
  - `ssfinekheldsolidbig.csv`: Top 15% LONG (1.7x), Top 10% SHORT (0.35x), max 2 short
  - `ssfinekheldkuponlu.csv`: Top 35% LONG (1.3x), Top 35% SHORT (0.75x), sınırsız short

#### Neden Yapılıyor?
- Trading portfolio'su oluşturmak için
- LONG ve SHORT pozisyonları belirlemek için
- Risk yönetimi için (max_short limiti)

---

### 14. **npreviousadd.py** - Previous Close Ekleme

#### Ne Yapar?
Hammer Pro API'den previous close (önceki gün kapanış) fiyatlarını çeker ve SSFINEK dosyalarına ekler. NASDAQ exchange'de olan ve TIME TO DIV=90 olan hisselerde previous close'u DIV AMOUNT kadar düşürür.

#### Girdi CSV'leri:
- `ssfinek*.csv` dosyaları

#### Çıktı CSV'leri:
- `janek_ssfinek*.csv` dosyaları (prev_close ile)

#### Değişiklikler:
- **prev_close**: Hammer Pro API'den çekilen previous close fiyatı
- **NASDAQ Hisseleri**: TIME TO DIV=90 ise `prev_close = prev_close - DIV_AMOUNT`

#### Neden Yapılıyor?
- Spread hesaplamaları için
- Fiyat değişim analizi için
- NASDAQ ex-dividend adjustment için

---

### 15. **merge_csvs.py** - CSV Birleştirme

#### Ne Yapar?
Tüm `janek_ssfinek*.csv` dosyalarını birleştirir ve `janalldata.csv` oluşturur.

#### Girdi CSV'leri:
- `janek_ssfinekheldcilizyeniyedi.csv`
- `janek_ssfinekheldcommonsuz.csv`
- `janek_ssfinekhelddeznff.csv`
- `janek_ssfinekheldff.csv`
- `janek_ssfinekheldflr.csv`
- `janek_ssfinekheldgarabetaltiyedi.csv`
- `janek_ssfinekheldkuponlu.csv`
- `janek_ssfinekheldkuponlukreciliz.csv`
- `janek_ssfinekheldkuponlukreorta.csv`
- `janek_ssfinekheldnff.csv`
- `janek_ssfinekheldotelremorta.csv`
- `janek_ssfinekheldsolidbig.csv`
- `janek_ssfinekheldtitrekhc.csv`
- `janek_ssfinekhighmatur.csv`
- `janek_ssfineknotbesmaturlu.csv`
- `janek_ssfineknotcefilliquid.csv`
- `janek_ssfineknottitrekhc.csv`
- `janek_ssfinekrumoreddanger.csv`
- `janek_ssfineksalakilliquid.csv`
- `janek_ssfinekshitremhc.csv`

#### Çıktı CSV'leri:
- `janalldata.csv` (tüm dosyalar birleştirilmiş, duplicate'ler çıkarılmış)

#### Değişiklikler:
- **Duplicate Removal**: `PREF IBKR` kolonuna göre duplicate satırlar çıkarılır (ilk kayıt tutulur)
- **Column Merge**: Tüm kolonlar birleştirilir

#### Neden Yapılıyor?
- Tüm verileri tek bir dosyada toplamak için
- Quant Engine ve Janall uygulaması için master data dosyası oluşturmak için
- Trading scanner için hazır veri seti

---

### 16. **gorter.py** - GORT Analizi

#### Ne Yapar?
`janalldata.csv` dosyasındaki hisseleri CGRUP'a göre gruplayıp, her grup için en yüksek ve en düşük 3 GORT (Group Relative Trend) değerine sahip hisseleri bulur.

#### Girdi CSV'leri:
- `janalldata.csv`
- `ssfinek*.csv` dosyaları (grup bilgisi için)

#### Çıktı CSV'leri:
- `gort_analysis.csv` (GORT analiz sonuçları)

#### GORT Hesaplama:
```
GORT = (0.25 * (SMA63_chg - group_avg_sma63)) + (0.75 * (SMA246_chg - group_avg_sma246))
```

#### Değişiklikler:
- **GORT**: Her hisse için grup ortalamasına göre relative trend hesaplanır
- **GROUP**: Her hisse için grup bilgisi eklenir
- **Kuponlu Hisseler**: CGRUP'a göre gruplanır (c425, c450, c475, vb.)
- **Diğer Hisseler**: Grup adına göre gruplanır (heldff, helddeznff, vb.)

#### Neden Yapılıyor?
- Grup içinde relative trend analizi için
- En yüksek/en düşük GORT = grup içinde en iyi/en kötü performans
- Trading kararları için (grup içinde outlier'ları bulmak)

---

## 🎯 GENEL AMAÇ

Bu pipeline'ın genel amacı:

1. **Veri Toplama**: IBKR, Hammer Pro, CNBC gibi kaynaklardan güncel verileri çekmek
2. **Veri Temizleme**: Eksik değerleri doldurmak, normalize etmek, düzeltmek
3. **Skorlama**: FINAL_THG ve SHORT_FINAL skorlarını hesaplamak
4. **Portfolio Seçimi**: LONG ve SHORT pozisyonları belirlemek
5. **Master Data**: `janalldata.csv` dosyasını oluşturmak (97+ kolon)
6. **Analiz**: GORT analizi ile grup içi relative trend bulmak

---

## 📊 ÇIKTI DOSYALARI

### Ana Çıktı:
- **janalldata.csv**: Tüm preferred stock'lar için master data dosyası (97+ kolon)
  - PREF_IBKR, CMON, CGRUP
  - FINAL_THG, SHORT_FINAL
  - AVG_ADV, SMI
  - SMA63 chg, SMA246 chg
  - prev_close, bid, ask, last
  - GRPAN, RWVAP (runtime'da hesaplanır)
  - ... ve daha fazlası

### Analiz Çıktıları:
- **gort_analysis.csv**: Grup bazında GORT analizi
- **nsmiall.csv**: Tüm hisseler için SMI değerleri

---

## ⚙️ TEKNİK DETAYLAR

### Veri Kaynakları:
- **IBKR TWS/Gateway**: Fiyat, hacim, SMA, fee rate verileri
- **Hammer Pro API**: Previous close, real-time market data
- **CNBC Web Scraping**: Ex-dividend date bilgileri
- **Treasury Data**: Yield curve, benchmark rates

### İşlem Sırası:
1. Her script bir önceki script'in çıktısını alır
2. Her script çalıştıktan sonra CSV dosyaları `janall/` klasörüne kopyalanır
3. Hata durumunda pipeline durur
4. Son adım: `janalldata.csv` oluşturulur

### Performans:
- IBKR API rate limiting: Her istek arasında 1 saniye bekleme
- Web scraping: CNBC'den ex-dividend date çekme (Selenium)
- Batch processing: Tüm dosyalar sırayla işlenir

---

## 🔍 ÖNEMLİ NOTLAR

1. **TIME TO DIV Normalizasyonu**: 90 günlük mod sistemi (0 yerine 90 yazılır)
2. **NASDAQ Ex-Dividend Adjustment**: TIME TO DIV=90 ise prev_close düşürülür
3. **Duplicate Removal**: merge_csvs.py'de PREF_IBKR'ye göre duplicate'ler çıkarılır
4. **Missing Data Handling**: Eksik değerler ortalama ile doldurulur
5. **Group-Based Analysis**: GORT analizi grup bazında yapılır (CGRUP veya GROUP)

---

*Son Güncelleme: 2025-01-XX*






