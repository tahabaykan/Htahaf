# PSFAlgo Sistemi - Kapsamlı Dokümantasyon

## 🎯 Genel Bakış
PSFAlgo, Htahaf uygulamasının kalbidir ve otomatik trading sistemidir. 7/24 çalışabilen, risk kontrollü, kar garantili bir otomatik trading sistemi olarak tasarlanmıştır.

## 📋 Sistem Mimarisi

### Ana Bileşenler:
- **PSFAlgo Sınıfı**: Ana otomasyon motoru
- **PISDoNGU Sistemi**: 3 dakikalık döngüsel işlem zinciri
- **Fill Listener**: Gerçek zamanlı fill tespit sistemi (optimized)
- **Reverse Order Sistemi**: Otomatik kar garantisi emirleri
- **Position Control**: Pozisyon yönetimi ve limit kontrolü

## 🔄 PISDoNGU Sistemi (Ana Döngü)

### Döngü Yapısı (Her 3 Dakikada Bir):
```
Döngü Başlangıcı
    ↓
1. BEFDAY Yükleme (Gün başı pozisyonları)
    ↓
2. Veri Güncelleme (ETF + Market Data)
    ↓
3. Emir İptali (Sadece normal emirler, reverse korunur)
    ↓
4. 6 Aşamalı Chain Başlatma
    ↓
Chain Tamamlandıktan Sonra → 3 Dakika Bekle → Yeni Döngü
```

### 6 Aşamalı Chain Sistemi:

#### 1. T-TOP LOSERS
- **Filtre**: Bid buy ucuzluk ≤ -0.25 olanları seç
- **Emir**: LONG emirleri (BUY)
- **Mantık**: Düşen hisseleri ucuzdan al

#### 2. T-TOP GAINERS  
- **Filtre**: Ask sell pahalilik ≥ 0.25 olanları seç (top 30)
- **Emir**: SHORT emirleri (SELL)
- **Mantık**: Yükselen hisseleri pahalıdan sat

#### 3. LONG TP ASK SELL
- **Filtre**: Long pozisyonlarda ask sell pahalilik > 0.20
- **Emir**: Long pozisyonları ask fiyatından sat
- **Mantık**: Kar realizasyonu (ask'a sat)

#### 4. LONG TP FRONT SELL
- **Filtre**: Long pozisyonlarda front sell pahalilik > 0.10 (top 3)
- **Emir**: Long pozisyonları front running ile sat
- **Mantık**: Agresif kar realizasyonu

#### 5. SHORT TP BID BUY
- **Filtre**: Short pozisyonlarda bid buy ucuzluk < -0.20
- **Emir**: Short pozisyonları bid fiyatından kapat
- **Mantık**: Kar realizasyonu (bid'den al)

#### 6. SHORT TP FRONT BUY
- **Filtre**: Short pozisyonlarda front buy ucuzluk < -0.10 (top 3)
- **Emir**: Short pozisyonları front running ile kapat
- **Mantık**: Agresif kar realizasyonu

## 📊 Veri Kaynakları

### 4 Ana Veri Kaynağı:

#### 1. FINAL_THG/AVGADV Data:
- **T-prefs**: `mastermind_histport.csv`
- **C-prefs**: 5 grup CSV'si:
  - `nffextlt.csv` (NFF group)
  - `ffextlt.csv` (FF group)  
  - `flrextlt.csv` (FLR group)
  - `maturextl.csv` (Mature group)
  - `duzextlt.csv` (DUZ group)

#### 2. SMI Values: 
- `Smiall.csv` (Short interest oranları)

#### 3. Position/Order Data: 
- IBKR hesabı (canlı pozisyonlar ve emirler)

#### 4. Market Data: 
- Polygon API (bid/ask/last fiyatlar, ticker dönüşümü ile)

## 🎯 Emir Yönetimi

### Emir Gönderme Süreci:
```
Hisse Seçimi (Skor kriterleri)
    ↓
BEFDAY Limit Kontrolü (±600 lot günlük limit)
    ↓
AVGADV/10 Limit Kontrolü (Pozisyon büyüklük limiti)
    ↓
SMI Kontrolü (Sadece short arttırma için ≤ 0.28)
    ↓
Pozisyon Kontrolü (Tersine geçme önleme)
    ↓
Lot Bölme (200'lük parçalar)
    ↓
IBKR'ye Emir Gönderme
```

### Pozisyon Türleri:
- **LONG_INCREASE**: Long pozisyon arttırma (SMI kontrolü yok)
- **LONG_DECREASE**: Long pozisyon azaltma (pozisyon kapatma)
- **SHORT_INCREASE**: Short pozisyon arttırma (SMI kontrolü var)
- **SHORT_DECREASE**: Short pozisyon azaltma (pozisyon kapatma)

## 🎧 Fill Listener Sistemi (Optimized)

### Çalışma Mantığı:
```
Emirler Gönderilmeden Önce → Position Snapshot Oluştur
    ↓
Her 1 Dakikada Bir → Mevcut Pozisyonları Kontrol Et
    ↓
Snapshot ile Karşılaştır → Fill Tespit Et
    ↓
Fill Varsa → Reverse Order Kontrolü
```

### Performans Optimizasyonu:
- **Eski sistem**: 10 saniyede bir IBKR trades() kontrolü → Uygulama kasıyordu
- **Yeni sistem**: 60 saniyede bir position snapshot karşılaştırması
- **Kazanç**: ~6x daha az API çağrısı, uygulama kasma sorunu çözüldü ✅

## 🔄 Reverse Order Sistemi

### Tetiklenme Koşulları:
- Günlük fill ≥ 200 lot
- **Pozisyon arttırma işlemi** (azaltma değil!)
- Maksimum 600 lot reverse order/ticker/gün

### Pozisyon Arttırma Mantığı:
```
LONG ARTTIRMA:
- Sıfırdan pozitife (0 → +200) ✅
- Pozitiften daha pozitife (+500 → +700) ✅
- Negatiften sıfıra (-200 → 0) ❌ (SHORT AZALTMA)

SHORT ARTTIRMA:
- Sıfırdan negatife (0 → -200) ✅
- Negatiften daha negatife (-500 → -700) ✅
- Pozitiften sıfıra (+200 → 0) ❌ (LONG AZALTMA)
```

### 🧠 Akıllı Orderbook Derinlik Kontrolü:

#### Long Arttırma Fill'i Sonrası (SHORT Reverse):
```
1. IBKR'den orderbook derinliği al (ilk 3 kademe)
2. Her ask seviyesini kontrol et:
   - Ask ≥ fill_price + 0.07 ? → UYGUN
   - Ask < fill_price + 0.07 ? → ATLA
3. İlk uygun ask için ask-spread*0.15 formülünü kullan
4. Hiçbiri uygun değilse → klasik yöntem (fill_price + 0.07)

Örnek: AFGB 20.80 LONG fill (spread: 0.05)
- Ask seviyeleri: 20.83, 20.85, 20.93
- Min kar fiyatı: 20.87
- 20.83 ❌, 20.85 ❌, 20.93 ✅
- Reverse emir: 20.93 - 0.05*0.15 = 20.92
```

#### Short Arttırma Fill'i Sonrası (LONG Reverse):
```
1. IBKR'den orderbook derinliği al (ilk 3 kademe)
2. Her bid seviyesini kontrol et:
   - Bid ≤ fill_price - 0.07 ? → UYGUN
   - Bid > fill_price - 0.07 ? → ATLA
3. İlk uygun bid için bid+spread*0.15 formülünü kullan
4. Hiçbiri uygun değilse → klasik yöntem (fill_price - 0.07)

Örnek: FCNCO 23.50 SHORT fill (spread: 0.04)
- Bid seviyeleri: 23.47, 23.45, 23.20
- Max kar fiyatı: 23.43
- 23.47 ❌, 23.45 ❌, 23.20 ✅
- Reverse emir: 23.20 + 0.04*0.15 = 23.21
```

### Akıllı Sistem Avantajları:
1. **Orderbook derinliği analizi** - Gerçek piyasa durumu
2. **Kar koşulunu sağlamayan seviyeleri atlama** - Daha akıllı fiyatlama
3. **Uygun seviyenin hemen önüne/üstüne pozisyonlanma** - Öncelik kazanma
4. **Agresif alım/satımlarda avantaj** - Daha iyi fill şansı
5. **Minimum 7 cent kar garantisi** - Risk kontrolü

### Reverse Order Tanımlama (Befday Kontrolü):
```
BUY Emri:
- Befday ≥ 0 && Şimdi < 0 → REVERSE (Short kapama)
- Diğer durumlar → NORMAL

SELL Emri:
- Befday ≤ 0 && Şimdi > 0 → REVERSE (Long kapama)
- Diğer durumlar → NORMAL
```

**Önemli**: Bu sistem uygulamanın kapatılıp açılması durumunda da çalışır. Befday.csv kontrolü ile reverse emirler otomatik tanımlanır.

## 🛡️ Limit Kontrol Sistemleri

### BEFDAY Limitleri:
- Her hisse için ±600 lot günlük limit
- `befday.csv`'den gün başı pozisyonları yüklenir
- Gün başı pozisyonundan +600 / -600 aralığı
- Limit aşımında emir reddedilir veya lot azaltılır

### MAXALW Size Limitleri (YENİ MANTIK):
- **Raw MAXALW Size**: AVGADV/10 değeri
- **Effective MAXALW Size**: max(200, raw_maxalw_size) → Minimum 200 lot garantisi
- **Kontrol Tipi**: Mutlak pozisyon değeri |mevcut_pozisyon + yeni_emir| ≤ effective_maxalw_size
- **Kapsam**: Hem long hem short için aynı limit (200 lot veya üzeri)

**Örnekler:**
- MAXALW Size 45 → Effective limit 200 (minimum rule)
- MAXALW Size 3000 → Effective limit 3000 (raw value)
- 130 lot long mevcut, MAXALW 45 → 70 lot daha long alınabilir (200-130=70)
- 2500 lot long mevcut, MAXALW 3000 → 500 lot daha alınabilir (3000-2500=500)

**Manuel vs PSFAlgo:**
- Manuel emirler: Limit kontrolü YOK
- PSFAlgo emirleri: TAM limit kontrolü VAR

### SMI Kontrolü:
- **Sadece short arttırma işlemlerinde**
- SMI rate > 0.28 ise emir reddedilir
- Long işlemler ve pozisyon azaltma için kontrol yok
- `Smiall.csv`'den SMI değerleri okunur

## 🔧 Pozisyon Kontrolü

### Otomatik Pozisyon Koruma:
- **Long pozisyonda**: En pahalı sell emirlerini iptal et (tersine geçme önleme)
- **Short pozisyonda**: En ucuz buy emirlerini iptal et (tersine geçme önleme)
- **AVGADV limiti aşımında**: En riskli emirleri iptal et
- **Pozisyon yok**: Yeni pozisyon açması normal (kontrol etme)

### Emir İptal Stratejisi:
```
Emir iptali sırasında:
1. Position snapshot oluştur
2. Reverse emirleri tanımla (befday kontrolü)
3. Normal emirleri iptal et
4. Reverse emirleri koru (❌ iptal etme)
```

## 📱 GUI Entegrasyonu

### Otomatik Pencere Yönetimi:
- Her chain aşamasında ilgili pencereyi otomatik aç
- Hisse seçimi ve onay pencerelerini otomatik tetikle
- Kullanıcı onayından sonra sonraki aşamaya geç
- Pencere kapama işlemleri otomatik

### Manuel Kontrol:
- **PSFAlgo ON/OFF** butonu
- **PISDoNGU döngü sayacı** görüntüleme
- **Reverse order tanımlama** (Nor/Rev etiketleri)
- **Chain durumu** gösterimi (1/6, 2/6, vb.)

### Emirler Penceresi:
- Reverse emirler **Rev** etiketi ile gösterilir
- Normal emirler **Nor** etiketi ile gösterilir
- Befday kontrolü ile otomatik tanımlama

## 🧪 Test ve Debug Sistemleri

### Test Fonksiyonları:
```python
# Reverse order sistemi testi
psf_algo.test_reverse_order_system(ticker="JAGX", side="long", price=2.89, size=200)

# 🧠 Akıllı reverse order sistemi testi
psf_algo.test_smart_reverse_order_system(ticker="AFGB", fill_price=20.80, fill_size=400)

# 📊 Orderbook derinlik analizi testi
psf_algo.test_orderbook_depth_analysis(["AFGB", "FCNCO", "JAGX"])

# MAXALW Size limit testi
psf_algo.test_maxalw_limits(["AEFC", "INN PRF", "ACP PRA"])

# Fill listener optimizasyon testi
psf_algo.test_fill_listener_optimization()

# Manuel fill simülasyonu
psf_algo.simulate_fill(ticker="AFGB", side="long", price=3.50, size=200)

# Akıllı lot ayarlama testi
psf_algo.test_smart_lot_adjustment(ticker="AEFC")

# Reverse order tanımlama testi
psf_algo.test_reverse_order_identification()
```

### Debug Araçları:
- **Günlük fill takibi**: `debug_daily_fills()`
- **Reverse order cache**: Her order ID için reverse/normal tanımlaması
- **Position snapshot**: Emirler öncesi pozisyon durumu
- **Reasoning log**: `logs/psf_reasoning.log` detaylı işlem geçmişi

## 🎯 Aktivasyon ve Deaktivasyon

### PSFAlgo Aktivasyonu:
```python
psf_algo.activate()
```
- PISDoNGU sistemi başlar
- Fill listener aktif olur
- İlk döngü başlatılır

### PSFAlgo Deaktivasyonu:
```python
psf_algo.deactivate()
```
- PISDoNGU sistemi durur
- Fill listener pasif olur
- Timer'lar iptal edilir

## 📈 Performans ve Optimizasyonlar

### Fill Listener Optimizasyonu:
- **Problem**: 10 saniyede bir IBKR API çağrısı → Uygulama kasıyordu
- **Çözüm**: 1 dakikada bir position snapshot karşılaştırması
- **Sonuç**: ~6x performans artışı, kasma sorunu çözüldü

### Akıllı Lot Ayarlama:
- **Problem**: AVGADV limitinde emir reddediliyordu
- **Çözüm**: Boş kapasiteye göre otomatik lot ayarlama
- **Sonuç**: Daha verimli emir kullanımı

### Reverse Order Tanımlama:
- **Problem**: Uygulama kapanınca reverse emirler tanımlanamıyordu
- **Çözüm**: Befday.csv kontrolü ile otomatik tanımlama
- **Sonuç**: Süreklilik sağlandı

## 🔒 Risk Yönetimi

### Çoklu Güvenlik Katmanları:
1. **BEFDAY Limitleri**: Günlük ±600 lot limit
2. **MAXALW Size Limitleri**: Pozisyon büyüklük kontrolü
3. **SMI Kontrolü**: Short interest risk kontrolü
4. **Pozisyon Tersine Geçme Önleme**: Otomatik emir iptali
5. **Reverse Order Koruması**: Kar garantisi emirlerini koruma

### Otomatik Risk Önlemleri:
- Limit aşımında otomatik lot azaltma
- Riskli emirleri otomatik iptal
- Pozisyon tersine geçmeyi önleme
- SMI yüksek hisselerde short yasağı

## 📝 Özet: PSFAlgo'nun Yaptığı İşlemler

1. **Otomatik Veri Güncelleme** (Her döngüde ETF + Market data)
2. **Akıllı Hisse Seçimi** (Skor bazlı filtreler ile 6 farklı strateji)
3. **Çoklu Limit Kontrolü** (BEFDAY, MAXALW Size, SMI - 3 katmanlı güvenlik)
4. **Otomatik Emir Gönderme** (200'lük parçalar halinde)
5. **Gerçek Zamanlı Fill Takibi** (Position snapshot ile optimize edilmiş)
6. **Otomatik Kar Garantisi** (Reverse order sistemi - 7 cent minimum kar)
7. **Pozisyon Risk Yönetimi** (Tersine geçme önleme, otomatik iptal)
8. **Döngüsel İşlem Zinciri** (6 aşamalı chain, 3 dakika döngü)

## 🎪 Kullanım Senaryoları

### Normal Kullanım:
1. PSFAlgo ON butonuna bas
2. Sistem otomatik olarak çalışmaya başlar
3. Her 3 dakikada döngü tamamlanır
4. Günlük işlemler otomatik takip edilir

### Manuel Müdahale:
- Exclude listesine hisse ekle/çıkar
- PSFAlgo OFF ile durdur
- Test fonksiyonları ile sistem kontrolü
- Reasoning log'ları ile işlem takibi

---

**Bu dokümantasyon, PSFAlgo sisteminin tüm özelliklerini ve işleyişini kapsamaktadır. Sistem, insan müdahalesi olmadan 7/24 çalışabilen, risk kontrollü, kar garantili bir otomatik trading sistemidir.** 
