# RUN_ANYWHERE_N.PY İÇİNDEKİ HER SCRIPT'İN DETAYLI AÇIKLAMASI

Bu dokümantasyon, `run_anywhere_n.py` dosyasındaki her bir Python script'inin ne yaptığını ve oluşturduğu CSV dosyalarındaki kolonların ne anlama geldiğini DETAYLI olarak açıklar.

---

## 1. NIBKRTRY.PY - IBKR'den Fiyat ve Teknik Veri Çekme

### Ne Yapar?
Bu script, Interactive Brokers (IBKR) API'sine bağlanarak hisse senetleri için gerçek zamanlı fiyat verileri ve teknik göstergeler çeker.

### İşlem Adımları:

1. **IBKR Bağlantısı**: 
   - TWS (Trader Workstation) veya Gateway'e bağlanır
   - Port: 4001 (Gateway) veya 7496 (TWS)
   - Client ID: 2982

2. **CSV Dosyalarını Yükler**:
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

3. **Her Hisse İçin Yapılan İşlemler**:
   - **Contract Qualification**: IBKR'den doğru exchange ve kontrat bilgilerini alır
   - **Historical Data Çekme**: 2 yıllık günlük fiyat verilerini çeker
   - **Last Price**: Son kapanış fiyatını alır
   - **SMA Hesaplamaları**: 
     - SMA20: 20 günlük basit hareketli ortalama
     - SMA63: 63 günlük basit hareketli ortalama
     - SMA246: 246 günlük basit hareketli ortalama
   - **SMA Değişim Yüzdeleri**: Div adj.price ile SMA'lar arasındaki % farkı hesaplar
   - **High/Low Değerleri**:
     - 3M High/Low: Son 3 ayın en yüksek/düşük fiyatı
     - 6M High/Low: Son 6 ayın en yüksek/düşük fiyatı
     - 1Y High/Low: Son 1 yılın en yüksek/düşük fiyatı
   - **Tarihsel Fiyat Farkları**:
     - Aug2022_diff: Mevcut fiyat - Ağustos 2022 fiyatı
     - Oct19_diff: Mevcut fiyat - Ekim 2019 fiyatı

4. **Temettü Metrikleri**:
   - **TIME TO DIV**: Bir sonraki temettü ödemesine kalan gün sayısı (90 günlük mod sistemi ile normalize edilir)
   - **Div adj.price**: Temettü düzeltmeli fiyat = Last Price - (((90-Time to Div)/90)*DIV AMOUNT)

5. **Çıktı Dosyaları**: Her giriş dosyasının başına 's' harfi eklenerek kaydedilir
   - Örnek: `ekheldbesmaturlu.csv` → `sekheldbesmaturlu.csv`

### Oluşturulan CSV Kolonları ve Anlamları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **PREF IBKR** | IBKR'de kullanılan ticker sembolü | String |
| **Last Price** | Son kapanış fiyatı | Float (2 ondalık) |
| **SMA20** | 20 günlük basit hareketli ortalama | Float (2 ondalık) |
| **SMA63** | 63 günlük basit hareketli ortalama | Float (2 ondalık) |
| **SMA246** | 246 günlük basit hareketli ortalama | Float (2 ondalık) |
| **SMA20 chg** | Div adj.price'ın SMA20'den % sapması | Float (2 ondalık, %) |
| **SMA63 chg** | Div adj.price'ın SMA63'ten % sapması | Float (2 ondalık, %) |
| **SMA246 chg** | Div adj.price'ın SMA246'dan % sapması | Float (2 ondalık, %) |
| **3M High** | Son 3 ayın en yüksek fiyatı | Float (2 ondalık) |
| **3M Low** | Son 3 ayın en düşük fiyatı | Float (2 ondalık) |
| **6M High** | Son 6 ayın en yüksek fiyatı | Float (2 ondalık) |
| **6M Low** | Son 6 ayın en düşük fiyatı | Float (2 ondalık) |
| **1Y High** | Son 1 yılın en yüksek fiyatı | Float (2 ondalık) |
| **1Y Low** | Son 1 yılın en düşük fiyatı | Float (2 ondalık) |
| **Aug2022_diff** | Mevcut fiyat - Ağustos 2022 fiyatı | Float (2 ondalık) |
| **Oct19_diff** | Mevcut fiyat - Ekim 2019 fiyatı | Float (2 ondalık) |
| **TIME TO DIV** | Bir sonraki temettüye kalan gün (90 mod) | Integer (1-90) |
| **Div adj.price** | Temettü düzeltmeli fiyat | Float (2 ondalık) |
| **EX-DIV DATE** | Ex-dividend tarihi | Date (MM/DD/YYYY) |
| **DIV AMOUNT** | Çeyreklik temettü miktarı | Float |

### Önemli Notlar:
- TIME TO DIV değeri 90 günlük mod sistemi ile normalize edilir (0 yerine 90 yazılır)
- Div adj.price hesaplamasında temettü ödemesine yakınlık dikkate alınır
- Her hisse sonrası 2 saniye beklenir (API rate limiting)

---

## 2. NCORREX.PY - Ex-Dividend Date Düzeltici (CNBC)

### Ne Yapar?
Bu script, CSV dosyalarındaki TIME TO DIV değerlerini kontrol eder ve CNBC'den ex-dividend date bilgilerini çekerek düzeltir.

### İşlem Adımları:

1. **TIME TO DIV Senkronizasyonu**:
   - `janalldata.csv` dosyasından TIME TO DIV ve DIV AMOUNT değerlerini alır
   - Tüm SSFINEK ve SEK dosyalarındaki bu değerleri senkronize eder

2. **Kontrol Edilecek TIME TO DIV Değerleri**:
   - [0, 1, 2, 3, 4, 5, 6, 84, 85, 86, 87, 88, 89]
   - Bu değerlere sahip hisseler CNBC'den kontrol edilir

3. **CNBC Scraping**:
   - Selenium WebDriver kullanarak CNBC'den ex-dividend date bilgilerini çeker
   - Anti-detection teknikleri kullanır (user-agent rotasyonu, JavaScript injection)

4. **TIME TO DIV Yeniden Hesaplama**:
   - Yeni ex-dividend date'den TIME TO DIV'i yeniden hesaplar
   - 90 günlük mod sistemi kullanılır

5. **Div adj.price Yeniden Hesaplama**:
   - Yeni TIME TO DIV ile Div adj.price'i yeniden hesaplar
   - Formül: Last Price - (((90-Time to Div)/90)*DIV AMOUNT)

6. **Teknik Göstergeleri Güncelleme**:
   - SMA20 chg, SMA63 chg, SMA246 chg değerlerini yeni Div adj.price ile yeniden hesaplar
   - 3M/6M/1Y High/Low değerlerini günceller

### İşlenen Dosyalar:
- `sekheld*.csv` dosyaları (20 adet)
- `ekheld*.csv` dosyaları (20 adet)

### Oluşturulan/Güncellenen CSV Kolonları:

| Kolon Adı | Açıklama | Değişiklik |
|-----------|----------|------------|
| **EX-DIV DATE** | Ex-dividend tarihi (CNBC'den güncellenir) | Güncellenir |
| **TIME TO DIV** | Yeniden hesaplanan TIME TO DIV | Güncellenir |
| **Div adj.price** | Yeniden hesaplanan Div adj.price | Güncellenir |
| **SMA20 chg** | Yeni Div adj.price ile yeniden hesaplanır | Güncellenir |
| **SMA63 chg** | Yeni Div adj.price ile yeniden hesaplanır | Güncellenir |
| **SMA246 chg** | Yeni Div adj.price ile yeniden hesaplanır | Güncellenir |
| **3M High** | Gerekirse güncellenir | Güncellenir |
| **3M Low** | Gerekirse güncellenir | Güncellenir |
| **6M High** | Gerekirse güncellenir | Güncellenir |
| **6M Low** | Gerekirse güncellenir | Güncellenir |
| **1Y High** | Gerekirse güncellenir | Güncellenir |
| **1Y Low** | Gerekirse güncellenir | Güncellenir |

### Önemli Notlar:
- TIME TO DIV aramasına giren TÜM hisselerde TIME TO DIV ve Div adj.price yeniden hesaplanır
- CNBC scraping için Selenium kullanılır (headless=False ile tarayıcı görünür)
- Her ticker arası 3-6 saniye rastgele bekleme yapılır

---

## 3. NNORMALIZE_DATA.PY - Veri Normalizasyonu

### Ne Yapar?
Bu script, `sekheld*.csv` dosyalarındaki teknik göstergeleri normalize eder ve fark değerlerini hesaplar.

### İşlem Adımları:

1. **CSV Dosyalarını Okur**:
   - `sekheld*.csv` dosyalarını okur (nibkrtry.py'den çıkan dosyalar)

2. **Fark Değerleri Hesaplar**:
   - **6M_Low_diff**: Div adj.price - 6M Low
   - **6M_High_diff**: Div adj.price - 6M High
   - **3M_Low_diff**: Div adj.price - 3M Low
   - **3M_High_diff**: Div adj.price - 3M High
   - **1Y_High_diff**: Div adj.price - 1Y High
   - **1Y_Low_diff**: Div adj.price - 1Y Low
   - **Aug4_chg**: Div adj.price - Aug2022_Price
   - **Oct19_chg**: Div adj.price - Oct19_Price

3. **Normalizasyon İşlemleri**:
   - **SMA Normalizasyonu**: SMA20 chg, SMA63 chg, SMA246 chg için
     - Aralık: -15 ile 15 arası
     - Formül: 90 - ((değer - min) / (max - min) * 80)
     - En negatif değer en yüksek puanı alır
   - **6M Normalizasyonu**: 6M ve 3M değerleri için
     - Aralık: -8 ile 15 arası
     - Formül: 90 - ((değer - min) / (max - min) * 80)
   - **1Y Normalizasyonu**: 1Y High/Low diff için
     - Aralık: -8 ile 15 arası
   - **Aug4/Oct19 Normalizasyonu**: Tarihsel fiyat farkları için
     - Aralık: -8 ile 15 arası

4. **Eksik Değerleri Doldurma**:
   - Normalize edilmiş kolonlardaki boş değerler ortalama ile doldurulur

5. **TLT Filtreleme**:
   - TLT içeren satırlar çıkarılır

6. **Çıktı Dosyaları**: Her giriş dosyasının başındaki 's' harfi 'n' ile değiştirilir
   - Örnek: `sekheldbesmaturlu.csv` → `nekheldbesmaturlu.csv`

### Oluşturulan CSV Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **6M_Low_diff** | Div adj.price - 6M Low | Float |
| **6M_High_diff** | Div adj.price - 6M High | Float |
| **3M_Low_diff** | Div adj.price - 3M Low | Float |
| **3M_High_diff** | Div adj.price - 3M High | Float |
| **1Y_High_diff** | Div adj.price - 1Y High | Float |
| **1Y_Low_diff** | Div adj.price - 1Y Low | Float |
| **Aug4_chg** | Div adj.price - Aug2022_Price | Float |
| **Oct19_chg** | Div adj.price - Oct19_Price | Float |
| **SMA20_chg_norm** | SMA20 chg normalize edilmiş (1-100 arası) | Float (6 ondalık) |
| **SMA63_chg_norm** | SMA63 chg normalize edilmiş (1-100 arası) | Float (6 ondalık) |
| **SMA246_chg_norm** | SMA246 chg normalize edilmiş (1-100 arası) | Float (6 ondalık) |
| **6M_Low_diff_norm** | 6M_Low_diff normalize edilmiş (1-100 arası) | Float (6 ondalık) |
| **6M_High_diff_norm** | 6M_High_diff normalize edilmiş (1-100 arası) | Float (6 ondalık) |
| **3M_Low_diff_norm** | 3M_Low_diff normalize edilmiş (1-100 arası) | Float (6 ondalık) |
| **3M_High_diff_norm** | 3M_High_diff normalize edilmiş (1-100 arası) | Float (6 ondalık) |
| **Aug4_chg_norm** | Aug4_chg normalize edilmiş (1-100 arası) | Float (6 ondalık) |
| **Oct19_chg_norm** | Oct19_chg normalize edilmiş (1-100 arası) | Float (6 ondalık) |
| **1Y_High_diff_norm** | 1Y_High_diff normalize edilmiş (1-100 arası) | Float (6 ondalık) |
| **1Y_Low_diff_norm** | 1Y_Low_diff normalize edilmiş (1-100 arası) | Float (6 ondalık) |

### Normalizasyon Formülü Detayı:
- **SMA Normalizasyonu**: -15 ile 15 arasındaki değerler normalize edilir
  - En negatif değer → 90 puan
  - En pozitif değer → 10 puan
  - Formül: `90 - ((değer - min) / (max - min) * 80)`

- **6M/1Y Normalizasyonu**: -8 ile 15 arasındaki değerler normalize edilir
  - Aynı formül kullanılır

### Önemli Notlar:
- Tüm normalize değerler 1-100 arasındadır (aslında 10-90 arası)
- Eksik değerler ortalama ile doldurulur
- Tüm değerler 6 ondalık basamakla kaydedilir

---

## 4. NMASTER_PROCESSOR.PY - Master Processor (YEK Dosyaları ve Cally Hesaplama)

### Ne Yapar?
Bu script, diğer script'leri sırayla çalıştırarak YEK dosyalarını oluşturur ve Cally değerlerini hesaplar.

### İşlem Adımları:

1. **create_yek_files.py**:
   - `nek*.csv` dosyalarını `yek*.csv` dosyalarına kopyalar
   - Boş Cally kolonları ekler

2. **ntreyield.py**:
   - Treasury yield'ları günceller (US15Y dahil)
   - IBKR'den treasury yield verilerini çeker

3. **nyield_calculator.py**:
   - Cally değerlerini hesaplar (15Y dahil)
   - Formül: Cally = Treasury Yield + Risk Premium

4. **update_normal_treasury_benchmark.py**:
   - Normal Treasury benchmark'ları günceller
   - Yeni kupon aralıkları ekler

5. **update_adjusted_treasury_benchmark.py**:
   - Adjusted Treasury benchmark'ları günceller (US15Y dahil)

6. **add_adj_risk_premium.py**:
   - Adj Risk Premium değerlerini hesaplar (US15Y dahil)
   - Formül: Adj Risk Premium = Current Yield - Adjusted Treasury Benchmark

### Çıktı Dosyaları:
- `yekheld*.csv` dosyaları (20 adet)
- Her dosyada Cally ve Adj Risk Premium kolonları eklenir

### Oluşturulan CSV Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **Cally** | Hesaplanan Cally değeri (Treasury Yield + Risk Premium) | Float |
| **Adj Risk Premium** | Adjusted Risk Premium (Current Yield - Adjusted Treasury Benchmark) | Float (4 ondalık) |
| **Treasury Benchmark** | Treasury benchmark değeri | Float |
| **Adjusted Treasury Benchmark** | Adjusted treasury benchmark değeri | Float |

### Önemli Notlar:
- Her script 5 saniye arayla çalıştırılır
- Script'lerden biri başarısız olsa bile devam edilir
- Tüm işlemler ana dizinde yapılır

---

## 5. NBEFORE_COMMON_ADV.PY - Ortalama Günlük Hacim (ADV) Verileri

### Ne Yapar?
Bu script, IBKR Gateway üzerinden her hisse için ortalama günlük hacim (ADV) verilerini çeker.

### İşlem Adımları:

1. **IBKR Bağlantısı**:
   - IBKR Gateway'e bağlanır (port 4001 veya 7496)
   - Delayed data kullanır (gerçek hesap yoksa)

2. **Hacim Verilerini Çeker**:
   - Her hisse için 3 farklı dönemde ortalama günlük hacim:
     - **ADV_6M**: Son 6 ayın ortalama günlük hacmi (180 gün)
     - **ADV_3M**: Son 3 ayın ortalama günlük hacmi (90 gün)
     - **ADV_15D**: Son 15 günün ortalama günlük hacmi (15 gün)

3. **AVG_ADV Hesaplar**:
   - Mevcut ADV değerlerinin ortalaması
   - Formül: (ADV_6M + ADV_3M + ADV_15D) / 3

4. **Çıktı Dosyaları**: Her giriş dosyasının başına 'adv' eklenir
   - Örnek: `yekheldbesmaturlu.csv` → `advekheldbesmaturlu.csv`

### İşlenen Dosyalar:
- `yekheld*.csv` dosyaları (20 adet)

### Oluşturulan CSV Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **ADV_6M** | Son 6 ayın ortalama günlük hacmi | Integer |
| **ADV_3M** | Son 3 ayın ortalama günlük hacmi | Integer |
| **ADV_15D** | Son 15 günün ortalama günlük hacmi | Integer |
| **AVG_ADV** | Tüm ADV değerlerinin ortalaması | Integer |

### Önemli Notlar:
- Her hisse sonrası 0.5 saniye beklenir (API rate limiting)
- En az 3 gün veri olması gerekir
- Başarılı sonuçlar için tüm 3 ADV değeri olmalıdır
- Birleştirilmiş veri `final_thg_with_avg_adv.csv` dosyasına kaydedilir

---

## 6. NCALCULATE_SCORES.PY - Solidity Skorları Hesaplama

### Ne Yapar?
Bu script, tüm hisseler için Solidity skorlarını hesaplar. Solidity, bir hissenin finansal sağlamlığını ölçen bir metrikdir.

### İşlem Adımları:

1. **comek Dosyalarını Birleştirir**:
   - `comek*.csv` dosyalarını birleştirir
   - `allcomek.csv` dosyasını oluşturur
   - GOOGL TVE/TVC gibi hisseleri filtreler

2. **EK Dosyalarından CRDT_SCORE Alır**:
   - `ek*.csv` dosyalarından CRDT_SCORE verilerini toplar
   - Eksik CRDT_SCORE değerleri 40 ile doldurulur

3. **Veri Temizleme**:
   - Sayısal verileri temizler (virgül, $, B karakterlerini kaldırır)
   - Market Cap değerlerini normalize eder

4. **Solidity Skorları Hesaplar**:
   - **MKTCAP_NORM**: Market Cap normalize edilmiş (35-95 arası)
   - **CRDT_NORM**: Credit Score normalize edilmiş (1-100 arası)
   - **TOTAL_SCORE_NORM**: Fiyat değişimlerinin normalize edilmiş ortalaması
   - **SOLIDITY_SCORE**: Market Cap bazlı ağırlıklandırılmış solidity skoru
   - **SOLIDITY_SCORE_NORM**: Solidity skorunun normalize edilmiş hali (10-90 arası)

5. **Çıktı Dosyası**: `allcomek_sld.csv`

### Solidity Hesaplama Formülü:

**Market Cap Bazlı Ağırlıklandırma**:
- Market Cap < 1B: TOTAL_SCORE_NORM*0.40 + MKTCAP_NORM*0.50 + CRDT_NORM*0.10
- Market Cap 1-3B: TOTAL_SCORE_NORM*0.40 + MKTCAP_NORM*0.45 + CRDT_NORM*0.15
- Market Cap 3-7B: TOTAL_SCORE_NORM*0.30 + MKTCAP_NORM*0.40 + CRDT_NORM*0.30
- Market Cap 7-12B: TOTAL_SCORE_NORM*0.25 + MKTCAP_NORM*0.35 + CRDT_NORM*0.40
- Market Cap 12-20B: TOTAL_SCORE_NORM*0.20 + MKTCAP_NORM*0.30 + CRDT_NORM*0.50
- Market Cap 20-35B: TOTAL_SCORE_NORM*0.15 + MKTCAP_NORM*0.30 + CRDT_NORM*0.55
- Market Cap 35-75B: TOTAL_SCORE_NORM*0.10 + MKTCAP_NORM*0.30 + CRDT_NORM*0.60
- Market Cap 75-200B: TOTAL_SCORE_NORM*0.05 + MKTCAP_NORM*0.30 + CRDT_NORM*0.65
- Market Cap >= 200B: TOTAL_SCORE_NORM*0.05 + MKTCAP_NORM*0.30 + CRDT_NORM*0.65

**Final Formül**: `sqrt(MKTCAP_NORM) * (ağırlıklandırılmış skorlar)`

**BB Bond Bonus**: BB bond'lar için %2 bonus eklenir

### Oluşturulan CSV Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **COM_LAST_PRICE** | Common stock son fiyatı | Float |
| **COM_52W_LOW** | Common stock 52 hafta düşük | Float |
| **COM_52W_HIGH** | Common stock 52 hafta yüksek | Float |
| **COM_6M_PRICE** | Common stock 6 ay önceki fiyat | Float |
| **COM_3M_PRICE** | Common stock 3 ay önceki fiyat | Float |
| **COM_5Y_LOW** | Common stock 5 yıl düşük | Float |
| **COM_5Y_HIGH** | Common stock 5 yıl yüksek | Float |
| **COM_MKTCAP** | Common stock market cap (milyar $) | Float |
| **COM_FEB2020_PRICE** | Common stock Şubat 2020 fiyatı | Float |
| **COM_MAR2020_PRICE** | Common stock Mart 2020 fiyatı | Float |
| **CRDT_SCORE** | Kredi skoru (ek dosyalarından) | Float |
| **MKTCAP_NORM** | Market Cap normalize edilmiş (35-95) | Float |
| **CRDT_NORM** | Credit Score normalize edilmiş (1-100) | Float |
| **CHANGE_COM_52W_LOW** | COM_LAST_PRICE - COM_52W_LOW % değişim | Float (%) |
| **CHANGE_COM_52W_HIGH** | COM_LAST_PRICE - COM_52W_HIGH % değişim | Float (%) |
| **CHANGE_COM_6M_PRICE** | COM_LAST_PRICE - COM_6M_PRICE % değişim | Float (%) |
| **CHANGE_COM_3M_PRICE** | COM_LAST_PRICE - COM_3M_PRICE % değişim | Float (%) |
| **CHANGE_COM_5Y_LOW** | COM_LAST_PRICE - COM_5Y_LOW % değişim | Float (%) |
| **CHANGE_COM_5Y_HIGH** | COM_LAST_PRICE - COM_5Y_HIGH % değişim | Float (%) |
| **CHANGE_COM_FEB2020_PRICE** | COM_LAST_PRICE - COM_FEB2020_PRICE % değişim | Float (%) |
| **CHANGE_COM_MAR2020_PRICE** | COM_LAST_PRICE - COM_MAR2020_PRICE % değişim | Float (%) |
| **TOTAL_SCORE** | Tüm CHANGE değerlerinin normalize edilmiş ortalaması | Float |
| **TOTAL_SCORE_NORM** | TOTAL_SCORE normalize edilmiş (1-100) | Float |
| **SOLIDITY_SCORE** | Ham solidity skoru | Float |
| **SOLIDITY_SCORE_NORM** | Solidity skoru normalize edilmiş (10-90) | Float (2 ondalık) |

### Önemli Notlar:
- Market Cap normalize fonksiyonu logaritmik bir ölçek kullanır
- BB bond'lar için %2 bonus eklenir
- Solidity skoru karekök formülü ile hesaplanır

---

## 7. NFILL_MISSING_SOLIDITY_DATA.PY - Eksik Solidity Verilerini Doldurma

### Ne Yapar?
Bu script, `sldek*.csv` dosyalarındaki eksik SOLIDITY_SCORE değerlerini doldurur ve yeniden hesaplar.

### İşlem Adımları:

1. **CSV Dosyalarını Okur**:
   - `sldek*.csv` dosyalarını okur (20 adet)

2. **CRDT_SCORE Eksik Değerleri Doldurur**:
   - Eksik CRDT_SCORE değerleri 8 ile doldurulur
   - CRDT_NORM yeniden hesaplanır

3. **COM_ Kolonlarındaki Eksik Değerleri Doldurur**:
   - COM_ ile başlayan tüm kolonlardaki eksik değerler ortalama ile doldurulur
   - Doldurulan hisseler işaretlenir

4. **Performans Değerlerini Yeniden Hesaplar**:
   - **3M_PERF**: (COM_LAST_PRICE / COM_3M_PRICE - 1) * 100
   - **6M_PERF**: (COM_LAST_PRICE / COM_6M_PRICE - 1) * 100
   - **RECENT_TOTAL**: 3M_PERF + 6M_PERF

5. **HIGH Skorlarını Hesaplar**:
   - **52W_HIGH_SKOR**: (COM_LAST_PRICE / COM_52W_HIGH) * 90 (10-90 arası)
   - **5Y_HIGH_SKOR**: (COM_LAST_PRICE / COM_5Y_HIGH) * 90 (10-90 arası)
   - **TOTAL_HIGH_SCORE**: (52W_HIGH_SKOR + 5Y_HIGH_SKOR) / 2

6. **Market Cap Yeniden Normalize Edilir**:
   - MKTCAP_NORM yeniden hesaplanır

7. **SOLIDITY_SCORE Yeniden Hesaplanır**:
   - Performansa göre farklı ağırlıklar kullanılır:
     - RECENT_TOTAL >= 0.8: TOTAL_HIGH_SCORE*0.26 + MKTCAP_NORM*0.49 + CRDT_NORM*0.25
     - RECENT_TOTAL < 0.8: TOTAL_HIGH_SCORE*0.42 + MKTCAP_NORM*0.39 + CRDT_NORM*0.20
   - BB bond kontrolü: BB ise %2 bonus
   - Eksik verileri doldurulan hisselerin skorları 20 puan düşürülür
   - Negatif skorlar 1 ile sınırlanır

8. **Çıktı Dosyaları**: Her giriş dosyasındaki 'sld' 'sldf' ile değiştirilir
   - Örnek: `sldekheldbesmaturlu.csv` → `sldfekheldbesmaturlu.csv`

### Oluşturulan/Güncellenen CSV Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **CRDT_SCORE** | Kredi skoru (eksikler 8 ile doldurulur) | Float |
| **CRDT_NORM** | Credit Score normalize edilmiş (yeniden hesaplanır) | Float |
| **3M_PERF** | 3 aylık performans % | Float (2 ondalık) |
| **6M_PERF** | 6 aylık performans % | Float (2 ondalık) |
| **RECENT_TOTAL** | Son dönem toplam performans | Float (2 ondalık) |
| **52W_HIGH_SKOR** | 52 hafta yüksek skoru (10-90) | Float (2 ondalık) |
| **5Y_HIGH_SKOR** | 5 yıl yüksek skoru (10-90) | Float (2 ondalık) |
| **TOTAL_HIGH_SCORE** | HIGH skorlarının ortalaması | Float (2 ondalık) |
| **MKTCAP_NORM** | Market Cap normalize edilmiş (yeniden hesaplanır) | Float (2 ondalık) |
| **SOLIDITY_SCORE** | Solidity skoru (yeniden hesaplanır, eksik verileri doldurulanlar -20) | Float (2 ondalık) |
| **SOLIDITY_SCORE_NORM** | Solidity skoru normalize edilmiş (10-90) | Float (2 ondalık) |

### Önemli Notlar:
- Eksik verileri doldurulan hisselerin SOLIDITY_SCORE değeri 20 puan düşürülür
- Negatif skorlar 1 ile sınırlanır
- BB bond'lar için %2 bonus eklenir

---

## 8. NMARKET_RISK_ANALYZER.PY - Piyasa Risk Analizi

### Ne Yapar?
Bu script, piyasa koşullarını analiz eder ve dinamik ağırlıklar hesaplar.

### İşlem Adımları:

1. **IBKR Bağlantısı**:
   - IBKR Gateway'e bağlanır
   - Risk göstergeleri için ETF verilerini çeker

2. **Risk Göstergeleri**:
   - **RISK_ON**: SPY, IWM, HYG, KRE (risk iştahı arttığında yükselen)
   - **RISK_OFF**: TLT, VXX (güvenli liman arandığında yükselen)

3. **Fiyat Değişimleri Hesaplar**:
   - 2 günlük, 5 günlük, 15 günlük değişimler
   - Ağırlıklar: 2 gün (%50), 5 gün (%30), 15 gün (%20)

4. **SMA Momentum Analizi**:
   - SPY, IWM, KRE için SMA20, SMA100, SMA200 farkları hesaplanır
   - 90 günlük high/low yakınlığı analiz edilir
   - Market momentum skoru: -20 (crash) ile +20 (ralli) arası

5. **Dinamik Ağırlıklar Hesaplar**:
   - **solidity_weight**: 0.8-4.0 arası (risk-on'da düşük, risk-off'da yüksek)
   - **yield_weight**: 8-40 arası (risk-on'da yüksek, risk-off'da düşük)
   - **adv_weight**: 0.00025 (sabit)
   - **adj_risk_premium_weight**: 500-1700 arası (risk-on'da yüksek)
   - **solcall_score_weight**: 1-7 arası (risk-on'da yüksek)
   - **credit_score_norm_weight**: 0.5-3.5 arası (risk-on'da düşük, risk-off'da yüksek)

6. **Çıktı Dosyası**: `market_weights.csv`

### Oluşturulan CSV Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **date** | Analiz tarihi | Date (YYYY-MM-DD) |
| **solidity_weight** | Solidity ağırlığı (0.8-4.0) | Float (2 ondalık) |
| **yield_weight** | Yield ağırlığı (8-40) | Float (2 ondalık) |
| **adv_weight** | ADV ağırlığı (sabit 0.00025) | Float (8 ondalık) |
| **adj_risk_premium_weight** | Adj Risk Premium ağırlığı (500-1700) | Integer |
| **solcall_score_weight** | SOLCALL Score ağırlığı (1-7) | Float (2 ondalık) |
| **credit_score_norm_weight** | Credit Score Norm ağırlığı (0.5-3.5) | Float (2 ondalık) |
| **risk_balance** | Risk-On - Risk-Off skoru | Float (2 ondalık) |
| **risk_on_score** | Risk-On skoru | Float (2 ondalık) |
| **risk_off_score** | Risk-Off skoru | Float (2 ondalık) |
| **market_momentum** | Market momentum skoru (-20 ile +20 arası) | Float (2 ondalık) |

### Ağırlık Hesaplama Formülleri:

**Market Momentum Normalizasyonu**:
- momentum_normalized = (market_momentum + 20) / 40 (0-1 arası)

**Ağırlıklar**:
- yield_weight = 8 + (40 - 8) * momentum_normalized
- solidity_weight = 4 - (4 - 0.8) * momentum_normalized
- adj_risk_premium_weight = 500 + (1700 - 500) * momentum_normalized
- solcall_score_weight = 1 + (7 - 1) * momentum_normalized
- credit_score_norm_weight = 3.5 - (3.5 - 0.5) * momentum_normalized

### Önemli Notlar:
- Market momentum skoru SMA farkları ve high/low yakınlığından hesaplanır
- Risk durumu: -20/20 (crash) ile +20/20 (ralli) arası
- Ağırlıklar `market_weights.csv` dosyasına kaydedilir ve sonraki script'ler tarafından kullanılır

---

## 9. NCALCULATE_THEBEST.PY - FINAL_THG Skorları Hesaplama

### Ne Yapar?
Bu script, her hisse için FINAL_THG (Final The Best) skorunu hesaplar. Bu, bir hissenin genel performans skorudur.

### İşlem Adımları:

1. **Veri Hazırlama**:
   - ADV dosyalarını (`advek*.csv`) okur
   - Solidity verilerini (`allcomek_sld.csv`) okur
   - SEK/YEK dosyalarını okur
   - Verileri birleştirir

2. **Güncel Fiyat Verilerini Alır**:
   - SEK dosyalarından güncel Last Price ve Div adj.price alır
   - YEK dosyalarından Adj Risk Premium alır
   - NEK dosyalarından SMA normalize değerlerini alır

3. **CUR_YIELD Hesaplar**:
   - Formül: (DIV_AMOUNT * 4) / price * 100
   - QDI=No olan hisseler için %5 düşürülür

4. **Özel Gruplar İçin Hesaplamalar**:
   - **Maturlular** (heldbesmaturlu, heldhighmatur, notbesmatur, highmatur):
     - YTM (Yield to Maturity) hesaplanır
     - Formül: YTM_NORM*4 + SMA63_chg_norm*9 + SOLIDITY_SCORE_NORM*2
   - **YTC Grupları** (helddeznff, heldnff):
     - YTC (Yield to Call) hesaplanır
     - Formül: YTC_NORM*3 + SOLIDITY_SCORE_NORM*2 + SMA63_chg_norm*10
   - **EXP_RETURN Grupları** (heldff, heldflr, heldsolidbig, heldtitrekhc, nottitrekhc):
     - EXP_ANN_RETURN (Expected Annual Return) hesaplanır
     - Formül: 2*SOLIDITY_SCORE_NORM + 13*SMA63_chg_norm

5. **Standart Gruplar İçin GORT Hesaplar**:
   - GORT = 0.25 * (SMA63chg - group_avg_sma63) + 0.75 * (SMA246chg - group_avg_sma246)
   - Kuponlu gruplar: CGRUP'a göre gruplama
   - Diğer gruplar: Grup içindeki tüm hisselerin ortalaması

6. **Skorları Normalize Eder**:
   - EXP_ANN_RETURN, YTM, YTC: 5-95 arası normalize edilir
   - SMA normalize değerleri: 5-95 arası normalize edilir
   - GORT: Tersine çevrilmiş normalize (en yüksek GORT → 5, en düşük GORT → 95)

7. **SOLCALL_SCORE Hesaplar** (Kuponlu gruplar için):
   - Final Adj Risk Premium hesaplanır (kupon oranına göre düşürülür)
   - Formül: (Final Adj Risk Premium * adj_risk_premium_weight) + (SOLIDITY_SCORE_NORM * 0.24)
   - SOLCALL_SCORE_NORM: 5-95 arası normalize edilir

8. **FINAL_THG Hesaplar**:
   - **Standart Formül**:
     - EX_FINAL_THG = (SMA20_chg_norm*0.4 + SMA63_chg_norm*0.9 + SMA246_chg_norm*1.1)*2.4 + (1Y_High_diff_norm + 1Y_Low_diff_norm)*2.2 + Aug4_chg_norm*0.50 + Oct19_chg_norm*0.50 + SOLIDITY_SCORE_NORM*solidity_weight + CUR_YIELD_LIMITED*yield_weight*0.75 + AVG_ADV*adv_weight + SOLCALL_SCORE_NORM*solcall_score_weight*0.85 + CREDIT_SCORE_NORM*credit_score_norm_weight
     - FINAL_THG = EX_FINAL_THG * 0.6 + GORT_NORM * 10
   - **Özel Formüller**: Yukarıda belirtilen özel gruplar için farklı formüller kullanılır

9. **Çıktı Dosyaları**: Her ADV dosyası için `finek*.csv` dosyası oluşturulur
   - Örnek: `advekheldbesmaturlu.csv` → `finekheldbesmaturlu.csv`

### Oluşturulan CSV Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **PREF IBKR** | IBKR ticker sembolü | String |
| **Last Price** | Güncel son fiyat (SEK'den) | Float (2 ondalık) |
| **Div adj.price** | Güncel Div adj.price (SEK'den) | Float (2 ondalık) |
| **SOLIDITY_SCORE_NORM** | Solidity skoru normalize edilmiş (10-90) | Float (2 ondalık) |
| **CUR_YIELD** | Current Yield ((DIV_AMOUNT*4)/price*100) | Float (4 ondalık) |
| **CUR_YIELD_LIMITED** | CUR_YIELD sınırlandırılmış (0-10 arası) | Float (2 ondalık) |
| **AVG_ADV** | Ortalama günlük hacim | Integer |
| **Adj Risk Premium** | Adjusted Risk Premium (YEK'den, 4 ondalık) | Float (4 ondalık) |
| **Final Adj Risk Premium** | Kupon oranına göre düşürülmüş Adj Risk Premium | Float (4 ondalık) |
| **SMA20_chg_norm** | SMA20 chg normalize edilmiş (5-95) | Float (2 ondalık) |
| **SMA63_chg_norm** | SMA63 chg normalize edilmiş (5-95) | Float (2 ondalık) |
| **SMA246_chg_norm** | SMA246 chg normalize edilmiş (5-95) | Float (2 ondalık) |
| **1Y_High_diff_norm** | 1Y High diff normalize edilmiş (5-95) | Float (2 ondalık) |
| **1Y_Low_diff_norm** | 1Y Low diff normalize edilmiş (5-95) | Float (2 ondalık) |
| **Aug4_chg_norm** | Aug4 chg normalize edilmiş (5-95) | Float (2 ondalık) |
| **Oct19_chg_norm** | Oct19 chg normalize edilmiş (5-95) | Float (2 ondalık) |
| **GORT** | Group Relative Technical (ham değer) | Float |
| **GORT_NORM** | GORT normalize edilmiş (tersine çevrilmiş, 5-95) | Float (2 ondalık) |
| **EXP_ANN_RETURN** | Expected Annual Return (özel gruplar için) | Float |
| **EXP_ANN_RETURN_NORM** | EXP_ANN_RETURN normalize edilmiş (5-95) | Float (2 ondalık) |
| **YTM** | Yield to Maturity (maturlular için) | Float |
| **YTM_NORM** | YTM normalize edilmiş (5-95) | Float (2 ondalık) |
| **YTC** | Yield to Call (YTC grupları için) | Float |
| **YTC_NORM** | YTC normalize edilmiş (5-95) | Float (2 ondalık) |
| **SOLCALL_SCORE** | Solidity + Call Score (kuponlu gruplar için) | Float |
| **SOLCALL_SCORE_NORM** | SOLCALL_SCORE normalize edilmiş (5-95) | Float (2 ondalık) |
| **CREDIT_SCORE_NORM** | Credit Score normalize edilmiş | Float (2 ondalık) |
| **EX_FINAL_THG** | Eski FINAL_THG formülü | Float (2 ondalık) |
| **FINAL_THG** | Final The Best skoru (ana skor) | Float (2 ondalık) |
| **SOLIDITY_WEIGHT_USED** | Kullanılan solidity ağırlığı | Float (2 ondalık) |
| **YIELD_WEIGHT_USED** | Kullanılan yield ağırlığı (%25 azaltılmış) | Float (2 ondalık) |
| **ADV_WEIGHT_USED** | Kullanılan ADV ağırlığı | Float (8 ondalık) |
| **SOLCALL_SCORE_WEIGHT_USED** | Kullanılan SOLCALL ağırlığı (%15 azaltılmış) | Float (2 ondalık) |
| **CREDIT_SCORE_NORM_WEIGHT_USED** | Kullanılan Credit Score ağırlığı | Float (2 ondalık) |
| **ADJ_RISK_PREMIUM_WEIGHT_USED** | Kullanılan Adj Risk Premium ağırlığı | Integer |
| **SMA20_WEIGHT_USED** | Kullanılan SMA20 ağırlığı | Float |

### Kupon Oranına Göre Adj Risk Premium Düşürme:

- Kupon < 4.16: Adj Risk Premium -0.0060
- Kupon 4.16-4.54: Adj Risk Premium -0.0045
- Kupon 4.55-4.84: Adj Risk Premium -0.0030
- Kupon 4.86-5.26: Adj Risk Premium -0.0015
- Kupon > 5.26: Düşürme yok

### Önemli Notlar:
- COUPON ve DIV AMOUNT değerleri hiç değiştirilmez
- Last Price eksik olan hisseler filtrelenir (PRS ve PRH hariç)
- Duplicate satırlar temizlenir
- Adj Risk Premium 4 ondalık hane ile kaydedilir

---

## 10. NOPTIMIZE_SHORTS.PY - SHORT_FINAL Skorları Hesaplama

### Ne Yapar?
Bu script, FINEK dosyalarından en düşük SHORT_FINAL skoruna sahip hisseleri bulur.

### İşlem Adımları:

1. **SMI Verilerini Yükler**:
   - `nsmiall.csv` dosyasından SMI (Short Margin Interest) verilerini okur

2. **FINEK Dosyalarını İşler**:
   - Her `finek*.csv` dosyasını okur
   - SMI verilerini merge eder
   - Eksik SMI değerleri ortalama ile doldurulur

3. **SHORT_FINAL Hesaplar**:
   - Formül: SHORT_FINAL = FINAL_THG + (SMI * 1000)
   - En düşük SHORT_FINAL = En iyi short adayı

4. **En Düşük SHORT_FINAL Bulur**:
   - Her dosya için en düşük SHORT_FINAL skoruna sahip hisseyi bulur

5. **Çıktı Dosyaları**:
   - Her FINEK dosyası için `ssfinek*.csv` dosyası oluşturulur
   - `ekheld_lowest_short_final_stocks.csv`: Tüm dosyaların en düşük SHORT_FINAL hisseleri

### Oluşturulan CSV Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **SMI** | Short Margin Interest (nsmiall.csv'den) | Float |
| **SHORT_FINAL** | FINAL_THG + (SMI * 1000) | Float (4 ondalık) |

### ekheld_lowest_short_final_stocks.csv Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **DOSYA** | Kaynak dosya adı | String |
| **PREF_IBKR** | Ticker sembolü | String |
| **SHORT_FINAL** | SHORT_FINAL skoru | Float (4 ondalık) |
| **FINAL_THG** | FINAL_THG skoru | Float |
| **SMI** | SMI değeri | Float |
| **CGRUP** | CGRUP değeri | String |
| **CMON** | CMON değeri | String |

### Önemli Notlar:
- SHORT_FINAL ne kadar düşükse, o kadar iyi short adayıdır
- SMI değeri short yapmanın maliyetini gösterir
- NaN değerleri filtrelenir

---

## 11. NTUMCSVPORT.PY - LONG/SHORT Hisseleri Seçme

### Ne Yapar?
Bu script, SSFINEK dosyalarından LONG ve SHORT hisseleri seçer.

### İşlem Adımları:

1. **SSFINEK Dosyalarını Okur**:
   - `ssfinek*.csv` dosyalarını okur

2. **Final FB ve Final SFS Hesaplar**:
   - **Final FB**: LONG için kullanılan skor (FINAL_THG bazlı)
   - **Final SFS**: SHORT için kullanılan skor (SHORT_FINAL bazlı)

3. **Dosya Bazlı Kurallar**:
   - Her dosya için özel LONG ve SHORT kuralları vardır:
     - **long_percent**: Top %X'i
     - **long_multiplier**: Ortalamanın X katı
     - **short_percent**: Bottom %X'i
     - **short_multiplier**: Ortalamanın X katı
     - **max_short**: Maksimum SHORT sayısı

4. **LONG Hisseleri Seçer**:
   - Final FB >= (ortalama * long_multiplier) VE Top long_percent% içinde olan hisseler
   - CMON sınırlaması: Her şirketin toplam hisse sayısı / 1.6 (normal yuvarlama)
   - CGRUP sınırlaması: Her CGRUP'tan maksimum 3 hisse

5. **SHORT Hisseleri Seçer**:
   - Final SFS <= (ortalama * short_multiplier) VE Bottom short_percent% içinde olan hisseler
   - CMON sınırlaması: Her şirketin toplam hisse sayısı / 1.6 (normal yuvarlama)
   - max_short sınırlaması: Maksimum SHORT sayısı

6. **ssfinekheldkuponlu.csv Özel İşleme**:
   - C600 ve C625 hariç her CGRUP'tan zorunlu olarak en iyi LONG ve en kötü SHORT seçilir
   - CMON sınırlaması: Her şirketin toplam hisse sayısı / 1.6
   - Ek olarak kurallara uyan hisseler de seçilir

7. **KUME_ORT ve KUME_PREM Hesaplar**:
   - **KUME_ORT**: CMON bazında Final FB/Final SFS ortalaması
   - **KUME_PREM**: Hissenin Final FB/Final SFS - KUME_ORT farkı

8. **RECSIZE Hesaplar**:
   - Formül: round((KUME_PREM * 8 + AVG_ADV / 25) / 4 / 100) * 100
   - HELDFF için: round((KUME_PREM * 12 + AVG_ADV / 25) / 4 / 100) * 100
   - AVG_ADV/6 sınırlaması (HELDFF için AVG_ADV/4)

9. **Çıktı Dosyaları**:
   - `tumcsvlong.csv`: Seçilen LONG hisseler
   - `tumcsvshort.csv`: Seçilen SHORT hisseler

### Oluşturulan CSV Kolonları (tumcsvlong.csv ve tumcsvshort.csv):

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **DOSYA** | Kaynak dosya adı | String |
| **PREF_IBKR** | Ticker sembolü | String |
| **Final FB** | Final FB skoru (LONG için) | Float |
| **Final SFS** | Final SFS skoru (SHORT için) | Float |
| **SMI** | Short Margin Interest | Float |
| **CGRUP** | CGRUP değeri | String |
| **CMON** | CMON değeri | String |
| **TİP** | LONG veya SHORT | String |
| **ORTALAMA_FINAL_FB** | Dosya ortalaması Final FB | Float |
| **ORTALAMA_FINAL_SFS** | Dosya ortalaması Final SFS | Float |
| **LONG_KURAL** | LONG seçim kuralı | String |
| **SHORT_KURAL** | SHORT seçim kuralı | String |
| **KUME_ORT** | CMON bazında ortalama | Float |
| **KUME_PREM** | KUME_PREM değeri | Float |
| **AVG_ADV** | Ortalama günlük hacim | Integer |
| **RECSIZE** | Önerilen pozisyon büyüklüğü | Integer |

### Dosya Bazlı Kurallar Örnekleri:

| Dosya | LONG % | LONG Mult | SHORT % | SHORT Mult | Max SHORT |
|-------|--------|-----------|---------|------------|-----------|
| ssfinekheldkuponlu.csv | 35 | 1.3 | 35 | 0.75 | 999 |
| ssfinekheldsolidbig.csv | 15 | 1.7 | 10 | 0.35 | 2 |
| ssfinekheldbesmaturlu.csv | 10 | 1.8 | 5 | 0.25 | 2 |
| ssfinekheldff.csv | 25 | 1.6 | 10 | 0.35 | 2 |

### Önemli Notlar:
- CMON sınırlaması: Her şirketin toplam hisse sayısı / 1.6 (minimum 1)
- CGRUP sınırlaması: Her CGRUP'tan maksimum 3 hisse
- ssfinekheldkuponlu.csv için özel zorunlu seçim kuralları vardır
- RECSIZE, pozisyon büyüklüğü önerisidir

---

## 12. NPREVIOUSADD.PY - Previous Close Kolonu Ekleme

### Ne Yapar?
Bu script, SSFINEK dosyalarına `prev_close` kolonu ekler ve `janek_` prefix'i ile kaydeder.

### İşlem Adımları:

1. **Hammer Pro API Bağlantısı**:
   - Hammer Pro API'ye WebSocket üzerinden bağlanır
   - Port: 16400
   - Password: "Nl201090."

2. **Portfolio'dan Symbol'ları Çeker**:
   - "janalldata" portfolio'sundan symbol'ları çeker
   - İlk 100 symbol için prev_close cache'i oluşturur

3. **SSFINEK Dosyalarını İşler**:
   - Her `ssfinek*.csv` dosyasını okur
   - Her hisse için prev_close değerini çeker:
     - Önce cache'den kontrol eder
     - Cache'de yoksa Hammer Pro API'den çeker
     - Başarılıysa cache'e ekler

4. **NASDAQ Exchange Düzeltmesi**:
   - SADECE NASDAQ_STOCKS listesinde olan ve TIME TO DIV=89 olan hisselerde
   - prev_close değeri DIV AMOUNT kadar düşürülür
   - Bu, temettü ödemesine yakın NASDAQ hisselerinde previous close'un temettü düzeltmeli olması içindir

5. **ETF'leri İşler**:
   - SPY, IWM, TLT, KRE, IEI, IEF, PFF, PGF için prev_close çeker
   - `janeketfs.csv` dosyasına kaydeder

6. **Çıktı Dosyaları**:
   - Her SSFINEK dosyası için `janek_ssfinek*.csv` dosyası oluşturulur
   - `janeketfs.csv`: ETF prev_close değerleri

### Oluşturulan CSV Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **prev_close** | Önceki gün kapanış fiyatı (Hammer Pro'dan) | Float (2 ondalık) |

### NASDAQ_STOCKS Listesi:
NASDAQ exchange'de olan hisseler listesi (90+ hisse):
- BCVpA, ECFpA, GGNpB, ACGLN, ACGLO, AGNCL, AGNCM, AGNCN, AGNCO, AGNCP, vb.

### Önemli Notlar:
- SADECE NASDAQ_STOCKS listesinde olan ve TIME TO DIV=89 olan hisselerde prev_close düşürülür
- Diğer hisselerde (PRH, LNC PRD gibi) ASLA düzeltme yapılmaz
- TIME TO DIV=89 = 89 gün var (temettü ödemesine yakın)
- Cache mekanizması API çağrılarını azaltır
- Her hisse sonrası 1 saniye beklenir (rate limiting)

---

## 13. MERGE_CSVS.PY - CSV Dosyalarını Birleştirme

### Ne Yapar?
Bu script, `janek_ssfinek*.csv` dosyalarını birleştirir ve `janalldata.csv` dosyasını oluşturur.

### İşlem Adımları:

1. **CSV Dosyalarını Okur**:
   - `janek_ssfinek*.csv` dosyalarını okur (20 adet)
   - Sadece ana dizindeki dosyalar kullanılır

2. **Dosyaları Birleştirir**:
   - Tüm DataFrame'leri birleştirir
   - Duplicate satırları çıkarır (PREF IBKR'e göre)
   - İlk kayıt korunur

3. **Çıktı Dosyası**: `janalldata.csv`

### Oluşturulan CSV Kolonları:
Tüm `janek_ssfinek*.csv` dosyalarındaki kolonlar korunur:
- PREF IBKR
- Final FB
- Final SFS
- SHORT_FINAL
- prev_close
- SOLIDITY_SCORE_NORM
- CUR_YIELD
- AVG_ADV
- Adj Risk Premium
- SMA normalize değerleri
- GORT
- FINAL_THG
- Ve diğer tüm kolonlar...

### Önemli Notlar:
- Sadece ana dizindeki dosyalar kullanılır
- Duplicate satırlar PREF IBKR'e göre temizlenir
- Tüm kolonlar korunur

---

## 14. GORTER.PY - GORT Analizi

### Ne Yapar?
Bu script, `janalldata.csv` dosyasındaki hisseleri CGRUP'a göre gruplayıp, her grup için en yüksek ve en düşük 3 GORT değerine sahip hisseleri bulur.

### İşlem Adımları:

1. **janalldata.csv Okur**:
   - Ana veri dosyasını okur

2. **GORT Hesaplar**:
   - Her hisse için GORT değerini runtime'da hesaplar
   - Formül: GORT = 0.25 * (SMA63chg - group_avg_sma63) + 0.75 * (SMA246chg - group_avg_sma246)
   - **Kuponlu gruplar**: CGRUP'a göre gruplama
   - **Diğer gruplar**: Grup içindeki tüm hisselerin ortalaması

3. **Gruplama**:
   - **HELDKUPONLU grubu**: CGRUP'a göre gruplar (c425, c450, c475, vb.)
   - **Diğer gruplar**: Grup adına göre gruplar (heldff, helddeznff, vb.)

4. **En Yüksek ve En Düşük 3 GORT Bulur**:
   - Her grup için en yüksek 3 GORT değerine sahip hisseler
   - Her grup için en düşük 3 GORT değerine sahip hisseler

5. **Çıktı Dosyası**: `gort_analysis.csv`

### Oluşturulan CSV Kolonları:

| Kolon Adı | Açıklama | Format |
|-----------|----------|--------|
| **GROUP** | Grup adı (heldkuponlu, heldff, vb.) | String |
| **CGRUP** | CGRUP değeri (heldkuponlu için) veya N/A | String |
| **Symbol** | PREF IBKR ticker sembolü | String |
| **GORT** | GORT değeri | Float (2 ondalık) |
| **Rank** | TOP veya BOTTOM | String |
| **Position** | Sıralama (1, 2, 3) | Integer |

### Önemli Notlar:
- HELDKUPONLU grubu CGRUP'a göre gruplanır
- Diğer gruplar CGRUP'u görmezden gelir
- GORT değeri runtime'da hesaplanır (CSV'de saklanmaz)
- En yüksek GORT = En kötü performans (tersine çevrilmiş)
- En düşük GORT = En iyi performans

---

## GENEL NOTLAR VE ÖNEMLİ BİLGİLER

### Dosya İsimlendirme Kuralları:
- `ek*.csv`: Orijinal giriş dosyaları
- `sek*.csv`: IBKR'den veri çekilmiş dosyalar (nibkrtry.py çıktısı)
- `nek*.csv`: Normalize edilmiş dosyalar (nnormalize_data.py çıktısı)
- `yek*.csv`: YEK dosyaları (Cally ve Adj Risk Premium eklenmiş)
- `advek*.csv`: ADV verileri eklenmiş dosyalar
- `sldek*.csv`: Solidity skorları eklenmiş dosyalar
- `sldfek*.csv`: Solidity skorları doldurulmuş dosyalar
- `finek*.csv`: FINAL_THG skorları hesaplanmış dosyalar
- `ssfinek*.csv`: SHORT_FINAL skorları eklenmiş dosyalar
- `janek_ssfinek*.csv`: prev_close eklenmiş dosyalar
- `janalldata.csv`: Tüm dosyaların birleştirilmiş hali

### Önemli Formüller:

1. **Div adj.price**: `Last Price - (((90-Time to Div)/90)*DIV AMOUNT)`
2. **CUR_YIELD**: `(DIV_AMOUNT * 4) / price * 100`
3. **SHORT_FINAL**: `FINAL_THG + (SMI * 1000)`
4. **GORT**: `0.25 * (SMA63chg - group_avg_sma63) + 0.75 * (SMA246chg - group_avg_sma246)`
5. **RECSIZE**: `round((KUME_PREM * 8 + AVG_ADV / 25) / 4 / 100) * 100`

### Script Çalışma Sırası:
1. nibkrtry.py → IBKR'den veri çeker
2. ncorrex.py → Ex-dividend date düzeltir
3. nnormalize_data.py → Verileri normalize eder
4. nmaster_processor.py → YEK dosyaları ve Cally hesaplar
5. nbefore_common_adv.py → ADV verileri ekler
6. ncalculate_scores.py → Solidity skorları hesaplar
7. nfill_missing_solidity_data.py → Eksik verileri doldurur
8. nmarket_risk_analyzer.py → Piyasa risk analizi yapar
9. ncalculate_thebest.py → FINAL_THG skorları hesaplar
10. noptimize_shorts.py → SHORT_FINAL skorları hesaplar
11. ntumcsvport.py → LONG/SHORT hisseleri seçer
12. npreviousadd.py → prev_close ekler
13. merge_csvs.py → Dosyaları birleştirir
14. gorter.py → GORT analizi yapar

### Veri Akışı:
```
ek*.csv → sek*.csv → nek*.csv → yek*.csv → advek*.csv → finek*.csv → ssfinek*.csv → janek_ssfinek*.csv → janalldata.csv
```

Bu dokümantasyon, her script'in ne yaptığını ve oluşturduğu CSV kolonlarının ne anlama geldiğini DETAYLI olarak açıklar.



