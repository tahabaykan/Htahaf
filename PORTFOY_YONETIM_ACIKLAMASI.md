# Portföy Yönetim Süreci - Detaylı Açıklama

## 📋 Genel Bakış

Bu dokümantasyon, preferred stock portföyünüzün nasıl yönetildiğini adım adım açıklamaktadır. Sistem, günlük veri toplama ve analizden başlayarak, skorlama, risk analizi ve trading kararlarına kadar tüm süreci otomatikleştirmiştir.

---

## 🔄 Günlük Veri İşleme Süreci (21 Aşamalı Pipeline)

Her gün, piyasa açılmadan önce ve gün içinde, sistem otomatik olarak şu adımları izler:

### 1. Veri Toplama Aşaması

**nibkrtry.py** - IBKR'den Güncel Veri Çekme
- Interactive Brokers API üzerinden tüm preferred stock'ların güncel fiyat verileri çekilir
- Bid, Ask, Last Price, Volume, Open Interest gibi temel piyasa verileri toplanır
- Her hisse için güncel durum kaydedilir

**ncorrex.py** - Ex-Dividend Tarihleri Düzeltme
- CNBC'den ex-dividend tarihleri çekilir ve doğrulanır
- Dividend ödemeleri için kritik tarihler güncellenir

### 2. Veri Normalizasyonu

**nnormalize_data.py** - Veri Standardizasyonu
- Farklı kaynaklardan gelen veriler standart formata dönüştürülür
- Tutarsızlıklar düzeltilir, eksik veriler işaretlenir
- Her hisse için tutarlı bir veri yapısı oluşturulur

### 3. Temel Hesaplamalar

**nmaster_processor.py** - YEK Dosyaları ve Cally Hesaplamaları
- Her hisse grubu için YEK (Yatırım Eşik Katsayısı) dosyaları oluşturulur
- Cally (Callable) değerleri hesaplanır - hissenin erken çağrılabilme olasılığı
- Treasury yield verileri entegre edilir

**nbefore_common_adv.py** - Ortalama Günlük Hacim (ADV) Hesaplama
- Her hisse için ortalama günlük işlem hacmi hesaplanır
- Likidite analizi için kritik metrik

**ncommon_stocks.py** - Common Stock Grupları
- Her preferred stock'un bağlı olduğu common stock belirlenir
- Grup bazlı analiz için veri hazırlığı

### 4. Skorlama Sistemi

**ncalculate_scores.py** - 6 Farklı Trading Stratejisi için Skorlama

Sistem, her hisse için **6 farklı trading stratejisini** otomatik olarak skorlar:

#### Alım Stratejileri:
1. **Bid Buy**: Bid fiyatına yakın alım stratejisi
   - Skor: Benchmark'e göre ucuzluk/pahalılık
   - Negatif skor = ucuz (iyi alım fırsatı)

2. **Front Buy**: Son işlem fiyatı üzerinden alım
   - Skor: Son fiyatın benchmark'e göre göreceli değeri

3. **Ask Buy**: Ask fiyatı üzerinden agresif alım
   - Skor: Ask fiyatının benchmark'e göre değerlendirmesi

#### Satım Stratejileri:
4. **Ask Sell**: Ask fiyatına yakın satım (maksimum kar)
   - Skor: Benchmark'e göre pahalılık
   - Pozitif skor = pahalı (iyi satım fırsatı)

5. **Front Sell**: Son işlem fiyatından satım
   - Skor: Son fiyatın benchmark'e göre göreceli değeri

6. **Bid Sell**: Bid fiyatından hızlı satım
   - Skor: Bid fiyatının benchmark'e göre değerlendirmesi

**Her skor nasıl hesaplanır?**
```
Ucuzluk/Pahalılık Skoru = (Passive Fiyat - Önceki Kapanış) - Benchmark Değişimi
```

Bu skorlar, her hissenin benchmark'e (PFF, TLT gibi ETF'ler) göre göreceli ucuzluk veya pahalılığını gösterir.

### 5. Risk Analizi

**nfill_missing_solidity_data.py** - Solidity (Sağlamlık) Hesaplamaları
- Her hisse için finansal sağlamlık skoru hesaplanır
- Kredi riski, likidite riski, volatilite faktörleri değerlendirilir
- Düşük solidity skoruna sahip hisseler işaretlenir

**nmarket_risk_analyzer.py** - Piyasa Risk Analizi
- Genel piyasa koşulları analiz edilir
- Sektörel risk faktörleri değerlendirilir
- Risk uyarıları üretilir

### 6. FINAL THG Hesaplaması

**ncalculate_thebest.py** - FINAL THG (Final Total Holding Grade) Skoru

FINAL THG, sistemin en önemli skorudur ve şu faktörleri birleştirir:
- **Fiyat Skorları**: 6 trading stratejisinden gelen skorlar
- **Likidite**: ADV (Average Daily Volume) bazlı likidite skoru
- **Risk**: Solidity ve market risk skorları
- **Benchmark Performansı**: PFF ve TLT gibi ETF'lerle karşılaştırma

**FINAL THG Yüksek = İyi Alım Fırsatı (Long)**
**FINAL THG Düşük = İyi Satım Fırsatı (Short)**

### 7. Portföy Optimizasyonu

**noptimize_shorts.py** - Short Pozisyon Optimizasyonu
- EKHELD dosyalarından en düşük SHORT_FINAL skoruna sahip hisseler belirlenir
- Short için en uygun fırsatlar seçilir

**ntumcsvport.py** - Long/Short Hisse Seçimi
- SSFINEK dosyalarından FINAL THG skorlarına göre:
  - **LONG**: En yüksek FINAL THG skoruna sahip hisseler
  - **SHORT**: En düşük FINAL THG skoruna sahip hisseler

**npreviousadd.py** - Önceki Kapanış Fiyatı Ekleme
- Her hisse için önceki günün kapanış fiyatı eklenir
- Fiyat değişimi hesaplamaları için gerekli

**merge_csvs.py** - Veri Birleştirme
- Tüm grup dosyaları birleştirilir
- `janalldata.csv` ana veri dosyası oluşturulur
- Her hisse için tüm skorlar ve metrikler tek dosyada toplanır

**gorter.py** - Grup Bazlı Analiz
- Her CGRUP (Common Stock Group) için:
  - En yüksek 3 GORT değerine sahip hisseler (Long için)
  - En düşük 3 GORT değerine sahip hisseler (Short için)

---

## 📊 Skorlama Sistemi Detayları

### Benchmark Karşılaştırması

Sistem, her hisseyi şu benchmark'larla karşılaştırır:
- **PFF**: Preferred Stock ETF (Preferred stock piyasası genel performansı)
- **TLT**: Treasury ETF (Risk-free rate referansı)

**Neden Benchmark Karşılaştırması?**
- Bir hisse tek başına ucuz görünebilir, ama benchmark'e göre pahalı olabilir
- Göreceli değerleme, mutlak fiyat karşılaştırmasından daha doğru sonuçlar verir
- Piyasa genel hareketlerinden bağımsız değerlendirme yapılır

### Skor Yorumlama

**Bid Buy Ucuzluk Skoru:**
- **Negatif (-0.25 ve altı)**: Benchmark'e göre çok ucuz → İyi alım fırsatı
- **Pozitif**: Benchmark'e göre pahalı → Alım için uygun değil

**Ask Sell Pahalılık Skoru:**
- **Pozitif (+0.25 ve üstü)**: Benchmark'e göre çok pahalı → İyi satım fırsatı
- **Negatif**: Benchmark'e göre ucuz → Satım için uygun değil

---

## 🎯 Trading Kararları Nasıl Alınıyor?

### Günlük Analiz Sonuçları

Günlük pipeline çalıştıktan sonra:

1. **janalldata.csv** dosyası oluşturulur
   - Tüm hisseler için FINAL THG skorları
   - 6 farklı trading stratejisi skorları
   - Risk metrikleri
   - Grup bilgileri

2. **Portföy Ağırlıklandırma (Port Adjuster)**
   - Her hisse grubu için ağırlık belirlenir
   - Örnek: HELDFF grubu %40, HELDKUPONLU grubu %30, vb.
   - Toplam exposure ve long/short oranı ayarlanır

3. **FINAL THG Bazlı Lot Dağılımı**
   - Her grupta FINAL THG skoruna göre TOP 5 hisse seçilir
   - Portföy ağırlıklarına göre lot dağılımı yapılır
   - MAXALW (Maksimum Alım Limiti) kontrolü uygulanır

### Gerçek Zamanlı Trading Süreci

**PISDoNGU Sistemi** (Her 3 Dakikada Bir Çalışan Döngü):

1. **Gün Başı Pozisyonları Yükleme**
   - BEFDAY dosyasından mevcut pozisyonlar yüklenir
   - Her hisse için pozisyon limitleri kontrol edilir (±600 lot)

2. **Veri Güncelleme**
   - ETF panelinden PFF, TLT güncel fiyatları
   - Tüm takip edilen hisseler için güncel market data

3. **Emir İptali**
   - Bekleyen normal emirler iptal edilir
   - Reverse order'lar (kar garantili emirler) korunur

4. **6 Aşamalı Chain Sistemi**

   **Aşama 1: T-TOP LOSERS (Long Alımlar)**
   - Bid buy ucuzluk skoru ≤ -0.25 olan hisseler seçilir
   - LONG emirleri gönderilir (Bid + Spread × 0.15 fiyatından)

   **Aşama 2: T-TOP GAINERS (Short Satışlar)**
   - Ask sell pahalılık skoru ≥ 0.25 olan top 30 hisse seçilir
   - SHORT emirleri gönderilir (Ask - Spread × 0.15 fiyatından)

   **Aşama 3: LONG TP ASK SELL (Long Kar Realizasyonu)**
   - Mevcut long pozisyonlarda ask sell pahalılık > 0.20
   - Long pozisyonlar ask fiyatından satılır (kar realizasyonu)

   **Aşama 4: LONG TP FRONT SELL (Agresif Long Kar Realizasyonu)**
   - Long pozisyonlarda front sell pahalılık > 0.10 (top 3)
   - Front running ile agresif kar realizasyonu

   **Aşama 5: SHORT TP BID BUY (Short Kar Realizasyonu)**
   - Mevcut short pozisyonlarda bid buy ucuzluk < -0.20
   - Short pozisyonlar bid fiyatından kapatılır (kar realizasyonu)

   **Aşama 6: SHORT TP FRONT BUY (Agresif Short Kar Realizasyonu)**
   - Short pozisyonlarda front buy ucuzluk < -0.10 (top 3)
   - Front running ile agresif kar realizasyonu

5. **3 Dakika Bekleme ve Yeni Döngü**

---

## 🛡️ Risk Yönetimi

### Pozisyon Limitleri

**Günlük Pozisyon Limiti:**
- Her hisse için maksimum ±600 lot pozisyon limiti
- Bu limit, aşırı konsantrasyon riskini önler

**MAXALW (Maksimum Alım Limiti):**
- Her hisse için MAXALW değeri hesaplanır
- Lot dağılımı yapılırken MAXALW × 2 limiti uygulanır
- Bu, likidite riskini kontrol altında tutar

### Solidity Kontrolü

- Düşük solidity skoruna sahip hisseler işaretlenir
- Bu hisseler için daha düşük pozisyon limitleri uygulanabilir
- Kredi riski yüksek hisseler otomatik olarak filtrelenir

### Company Limit Kontrolü

- Aynı şirkete ait farklı preferred stock'lar için toplam limit kontrolü
- Şirket bazlı konsantrasyon riski önlenir

### Reverse Order Sistemi (Kar Garantisi)

- Her alım emrinden sonra otomatik olarak kar garantili satım emri yerleştirilir
- Her satım emrinden sonra otomatik olarak kar garantili alım emri yerleştirilir
- Bu sistem, zarar durumunda otomatik kar realizasyonu sağlar

---

## 📈 Portföy Optimizasyonu

### Grup Bazlı Ağırlıklandırma

Portföy, hisse gruplarına göre ağırlıklandırılır:

**Örnek Grup Dağılımı:**
- HELDFF (Fixed-to-Float): %40
- HELDKUPONLU (Kuponlu): %30
- HELDSOLIDBIG (Büyük ve Sağlam): %20
- Diğer gruplar: %10

### FINAL THG Bazlı Seçim

Her grupta:
- **Long için**: En yüksek FINAL THG skoruna sahip TOP 5 hisse seçilir
- **Short için**: En düşük FINAL THG skoruna sahip TOP 5 hisse seçilir

### Lot Dağılımı Algoritması

```
1. Her gruptaki TOP 5 hisse için FINAL THG skorları alınır
2. Skorlar normalize edilir (en yüksek = 1.0)
3. Alpha parametresi ile ağırlıklandırma yapılır (varsayılan: 3)
4. Grup ağırlığına göre toplam lot hesaplanır
5. Her hisse için lot dağılımı yapılır
6. MAXALW limiti kontrol edilir ve gerekirse düzeltilir
7. Lotlar 100'lük sayılara yuvarlanır
```

**Alpha Parametresi:**
- Alpha = 2: Daha dengeli dağılım
- Alpha = 3: Varsayılan (orta konsantrasyon)
- Alpha = 4-5: Daha agresif konsantrasyon (en yüksek skorlu hisselere daha fazla ağırlık)

---

## 🔍 Veri Kaynakları ve Entegrasyonlar

### Interactive Brokers (IBKR)
- Gerçek zamanlı piyasa verileri (Bid, Ask, Last, Volume)
- Emir gönderimi ve pozisyon takibi
- Ex-dividend tarihleri ve dividend bilgileri

### Hammer Pro API
- Alternatif veri kaynağı (yedek sistem)
- Emir yönetimi alternatifi

### CNBC Scraper
- Treasury yield verileri
- Ex-dividend tarihleri doğrulama

### Polygon.io
- Ek piyasa verileri
- Tarihsel veri analizi

---

## 📊 Performans Takibi

### Günlük Metrikler

**jdata.csv** - Günlük İşlem Kayıtları
- Her işlemin detayları (tarih, saat, fiyat, lot)
- Benchmark karşılaştırması
- Fill zamanları

**Final jdata Analizi**
- Her unique hisse için ağırlıklı ortalama maliyet
- Ağırlıklı ortalama benchmark maliyeti
- Toplam P&L ve outperformans hesaplaması

### Pozisyon Takibi

- Gerçek zamanlı pozisyon durumu
- Her pozisyon için unrealized P&L
- Benchmark'e göre performans karşılaştırması

---

## ⚙️ Sistem Özellikleri

### Otomasyon Seviyeleri

1. **Tam Otomatik**: PISDoNGU sistemi 7/24 çalışır, otomatik emir gönderir
2. **Yarı Otomatik**: Emirler önerilir, manuel onay gerekir
3. **Manuel**: Analiz sonuçları gösterilir, kararlar manuel alınır

### Veri Güvenliği

- Günlük otomatik yedekleme sistemi
- Her adımda veri doğrulama
- Hata durumunda otomatik geri dönüş mekanizmaları

### Esneklik

- **run_anywhere_n.py**: İstediğiniz aşamadan başlayabilme
- Hata durumunda kaldığınız yerden devam etme
- Manuel müdahale imkanı

---

## 📝 Özet: Portföy Yönetim Süreci

1. **Sabah (Piyasa Öncesi)**: 21 aşamalı veri işleme pipeline'ı çalışır
2. **Veri Analizi**: Tüm hisseler için skorlar hesaplanır
3. **Portföy Planlama**: Grup ağırlıkları ve lot dağılımı belirlenir
4. **Gün İçi Trading**: PISDoNGU sistemi her 3 dakikada bir:
   - Yeni fırsatları tespit eder
   - Kar realizasyonu fırsatlarını değerlendirir
   - Risk limitlerini kontrol eder
   - Otomatik emir gönderir
5. **Risk Yönetimi**: Pozisyon limitleri, solidity kontrolü, company limitleri
6. **Performans Takibi**: Günlük P&L ve benchmark karşılaştırması

---

## 🎯 Sonuç

Bu sistem, preferred stock piyasasında **veri odaklı, sistematik ve risk kontrollü** bir portföy yönetimi sağlar. Tüm kararlar, objektif skorlama ve risk analizi üzerine kuruludur. Sistem, duygusal kararları ortadan kaldırarak, tutarlı ve ölçülebilir sonuçlar hedefler.

**Temel Prensipler:**
- ✅ Veri odaklı karar alma
- ✅ Benchmark'e göre göreceli değerleme
- ✅ Çok katmanlı risk yönetimi
- ✅ Otomatik kar realizasyonu
- ✅ Pozisyon limitleri ve konsantrasyon kontrolü
- ✅ Sürekli performans takibi

---

*Bu dokümantasyon, portföy yönetim sürecinin teknik detaylarını açıklamak amacıyla hazırlanmıştır. Sorularınız için lütfen iletişime geçin.*

