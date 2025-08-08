# Ntahaf Uygulaması Detaylı Dokümantasyonu

## Genel Bakış
Ntahaf, hisse senedi işlemleri için geliştirilmiş kapsamlı bir otomasyon ve analiz uygulamasıdır. Uygulama, IBKR (Interactive Brokers) API'si ve Polygon.io API'si üzerinden veri çekme, emir gönderme ve pozisyon yönetimi işlemlerini gerçekleştirir.

## Veri Kaynakları ve Dosyalar

### CSV Dosyaları
1. `mastermind_histport.csv`
   - Tüm hisse senetlerinin skorlarını içerir
   - Front sell pahalilik skoru
   - Front buy ucuzluk skoru
   - Ask sell pahalilik skoru
   - Bid buy ucuzluk skoru
   - FINAL_THG değerleri
   - AVG_ADV değerleri
   - CMON değerleri

2. `mastermind_extltport.csv`
   - Extended Long Term hisselerinin verileri
   - Tüm skor ve metrikler
   - Benchmark değerleri

3. `exdivkayit/*.csv`
   - Günlük ex-dividend kayıtları
   - Dosya formatı: pDDMMYY.csv (örn: p140625.csv)
   - İçerik: Ticker ve dividend bilgileri

4. `bdata.csv`
   - Benchmark verileri
   - PFF ve TLT ETF verileri
   - Tarihsel performans kayıtları

5. C-pref CSV Dosyaları
   - `nffextlt.csv`: NFF extended hisseleri
   - `ffextlt.csv`: Focus extended hisseleri
   - `flrextlt.csv`: FLR extended hisseleri
   - `maturextlt.csv`: Mature extended hisseleri
   - `duzextlt.csv`: Düz extended hisseleri

### Log Dosyaları
1. `logs/psf_reasoning.log`
   - PsfAlgo işlemlerinin gerekçe kayıtları
   - Her işlem ve atlanan işlem için detaylı açıklamalar

2. `logs/error.log`
   - Sistem hataları
   - API bağlantı hataları
   - Veri okuma hataları

3. `logs/order.log`
   - Emir işlemleri
   - Emir gönderim/iptal/modifikasyon kayıtları

4. `logs/market_data.log`
   - Market data hataları
   - Veri güncelleme sorunları

## Ana Pencere Bileşenleri

### 1. Üst Paneller
- **ETF Panel**: PFF, TLT ve diğer ETF'lerin canlı verilerini gösterir
- **Long/Short Panel**: Mevcut long ve short pozisyonların toplam miktar ve değerini gösterir
- **SMA Panel**: IBKR hesap SMA limit ve kalan miktarını gösterir

### 2. Ana Butonlar

#### Bağlantı ve Veri Butonları
- **IBKR'ye Bağlan**: IBKR API bağlantısını başlatır
- **Canlı Veri Başlat**: Market data stream'ini başlatır
- **Veri Güncelle**: Tüm market verilerini manuel günceller
- **ETF Güncelle**: ETF verilerini manuel günceller

#### PsfAlgo Butonları
- **PsfAlgo ON/OFF**: Algoritma modunu açar/kapatır
- **PsfAlgo Exclude**: Hariç tutulacak hisseleri yönetir
- **PsfAlgo Reasoning**: Algoritma işlem gerekçelerini gösterir

#### Ex-Dividend Butonları
- **Paste Ex-Div List**: Ex-dividend listesi yönetimi
- **Load Ex-Div List**: Kaydedilmiş ex-dividend listesini yükler

### 3. Hisse Grupları Butonları

#### NFF (Narrow Focus) Butonları
- **NFF ExtLT**: Narrow Focus Extended Long Term hisselerini gösterir
- **NFF Top Losers**: En çok düşen NFF hisselerini gösterir
- **NFF Top Gainers**: En çok yükselen NFF hisselerini gösterir

#### ExtLT (Extended Long Term) Butonları
- **ExtLT35**: Extended Long Term 35 hisselerini gösterir
- **ExtLT35 Top Losers/Gainers**: En çok düşen/yükselen ExtLT35 hisselerini gösterir

#### Opt50 (Option 50) Butonları
- **Opt50**: Option 50 hisselerini gösterir
- **Opt50 Top Losers/Gainers**: En çok düşen/yükselen Opt50 hisselerini gösterir

#### Diğer Grup Butonları
- **Maturex**: Mature hisseleri gösterir
- **NFFex**: NFF extended hisseleri gösterir
- **FFex**: Focus extended hisseleri gösterir
- **FLRex**: FLR extended hisseleri gösterir
- **Duzex**: Düz extended hisseleri gösterir

### 4. Pozisyon ve Emir Yönetimi Butonları
- **Pozisyonlarım**: Mevcut pozisyonları gösterir
- **Emirlerim**: Bekleyen ve gerçekleşen emirleri gösterir
- **Orderbook**: Seçili hissenin orderbook'unu gösterir

## Maltopla Penceresi Özellikleri

### 1. Tablo Özellikleri
- **Kolonlar**:
  - Ticker, Last price, Daily change, Benchmark change
  - FINAL_THG, Previous close
  - Bid, Ask, Spread, Volume
  - Tüm skor kolonları (Bid buy, Front buy, Ask buy, vb.)
  - Benchmark type, CMON, AVG_ADV, Final_Shares
  - PF (Polygon) verileri

### 2. Emir Butonları
- **Lot**: Manuel lot girişi
- **Avgadv lot**: AVG_ADV'ye göre otomatik lot hesaplama
- **%20, %50, %100**: Pozisyon yüzdesine göre lot hesaplama
- **Bid buy, Front buy, Ask buy**: Alış emirleri
- **Ask sell, Front sell, Bid sell**: Satış emirleri

### 3. Emir Özellikleri
- **Hidden Emirler**: Gizli emir gönderme
- **Fiyat Hesaplama**:
  - Bid buy: Bid - 0.15 * spread
  - Front buy: Last - 0.01
  - Ask buy: Ask - 0.15 * spread
  - Ask sell: Ask + 0.15 * spread
  - Front sell: Last + 0.01
  - Bid sell: Bid + 0.15 * spread

## Veri Güncelleme Mekanizmaları

### Market Data Güncelleme
- **Sıklık**: 45 saniyede bir
- **Veri Kaynakları**:
  - IBKR: Canlı market data
  - Polygon.io: Tarihsel veriler
- **Güncellenen Veriler**:
  - Last price
  - Bid/Ask fiyatları
  - Volume
  - Spread hesaplamaları

### ETF Güncelleme
- **Sıklık**: 45 saniyede bir
- **Veri Kaynakları**:
  - IBKR: Canlı ETF verileri
  - Polygon.io: Tarihsel ETF verileri
- **Güncellenen ETF'ler**:
  - PFF
  - TLT
  - Diğer takip edilen ETF'ler

## PsfAlgo İşlem Detayları

### T-top Losers İşlemleri
- **Filtreler**:
  - `bid buy ucuzluk` skoru <= -0.25
  - İlk 30 hisse (skora göre sıralı)
- **Emir Mantığı**:
  - Short pozisyon varsa: 200 lot hidden BUY
  - Pozisyon yoksa/long ise ve FINAL_THG >= 330: 200 lot hidden BUY
  - FINAL_THG < 330 ise: İşlem atlanır

### T-top Gainers İşlemleri
- **Filtreler**:
  - `ask sell pahalilik` skoru >= 0.25
  - İlk 30 hisse (skora göre sıralı)
- **Emir Mantığı**:
  - Long pozisyon varsa: 200 lot hidden SELL
  - Pozisyon yoksa/short ise ve FINAL_THG <= 410: 200 lot hidden SELL
  - FINAL_THG > 410 ise: İşlem atlanır

### Long Take Profit İşlemleri
- **Koşullar**:
  - Ask sell pahalilik skoru > 0.05
  - Spread > 0.04
- **Emir Mantığı**:
  - Pozisyonun %20'si (min 200, max 800 lot)
  - Hidden sell emri (ask - 0.15 * spread)

### Short Take Profit İşlemleri
- **Koşullar**:
  - Bid buy ucuzluk skoru < -0.05
  - Spread > 0.04
- **Emir Mantığı**:
  - Pozisyonun %20'si (min 200, max 800 lot)
  - Hidden buy emri (bid + 0.15 * spread)

### Front Run İşlemleri

#### Long Front Run
- **Koşullar**:
  - Front sell pahalilik skoru > 0.10
  - En yüksek skorlu 3 hisse
- **Emir Mantığı**:
  - Pozisyonun %20'si (min 200, max 800 lot)
  - Hidden sell emri (last - 0.01)

#### Short Front Run
- **Koşullar**:
  - Front buy ucuzluk skoru < -0.10
  - En düşük skorlu 3 hisse
- **Emir Mantığı**:
  - Pozisyonun %20'si (min 200, max 800 lot)
  - Hidden buy emri (last + 0.01)

## Pozisyon Yönetimi

### Reverse Order Mekanizması
- **Tetikleyici**: Fill emirlerinin toplam büyüklüğü 200'ün katı olduğunda
- **Koşullar**:
  - Pozisyon artışı olmalı
  - Minimum 5 cent kar hedefi
- **Emir Mantığı**:
  - Long pozisyonlar için: Ask + 0.05'ten hidden sell
  - Short pozisyonlar için: Bid - 0.05'ten hidden buy

### Pozisyon Kontrolleri
- Ters pozisyona geçiş engelleme
- Minimum lot kontrolü
- Maksimum lot sınırlaması
- Spread kontrolü

## Güvenlik ve Limitler

### Emir Limitleri
- Minimum lot: 200
- Maksimum lot: 800
- Spread minimum: 0.04
- Kar hedefi minimum: 0.05

### API Limitleri
- IBKR API rate limits
- Polygon.io API rate limits
- Veri çekme sıklığı limitleri

## Notlar ve Öneriler
1. Her işlem öncesi spread kontrolü yapılmalı
2. Pozisyon büyüklüğü kontrolleri dikkatli yapılmalı
3. Reverse order mekanizması düzenli kontrol edilmeli
4. Log dosyaları düzenli incelenmeli
5. CSV dosyalarının güncelliği kontrol edilmeli
6. API bağlantı durumları monitör edilmeli
7. Market data tutarlılığı kontrol edilmeli
8. Emir gönderim onayları dikkatli incelenmeli

## Butonlar ve Pencereler: Veri Kaynakları ve İşlevler

### 1. Üst Ana Butonlar

- **IBKR'ye Bağlan / IBKR'den Ayrıl**
  - IBKR API bağlantısını başlatır veya sonlandırır.
  - Veri Kaynağı: IBKR API (canlı bağlantı).

- **Canlı Veri Başlat**
  - Market data stream'ini başlatır.
  - Veri Kaynağı: IBKR ve Polygon.io API.

- **Veri Güncelle**
  - Tüm market verilerini manuel günceller.
  - Veri Kaynağı: IBKR ve Polygon.io API.

- **ETF Veri Güncelle**
  - ETF verilerini günceller.
  - Veri Kaynağı: IBKR ve Polygon.io API.

### 2. Portföy ve Emir Yönetimi

- **Pozisyonlarım**
  - Mevcut pozisyonları gösterir.
  - Veri Kaynağı: IBKR API'dan pozisyonlar.

- **Emirlerim**
  - Bekleyen, gerçekleşen ve reverse emirleri gösterir.
  - Veri Kaynağı: IBKR API ve OrderManager.

### 3. Opt50 ve Extlt35 Butonları

- **Opt50**
  - Açılan Pencere: Basit tablo penceresi.
  - Okunan CSV: `optimized_50_stocks_portfolio.csv`
  - Gösterilen Veriler: `PREF IBKR`, `Final_Shares`, `FINAL_THG`, `AVG_ADV`
  - Alt Butonlar: Yok.

- **Opt50 Maltopla**
  - Açılan Pencere: MaltoplaWindow
  - Okunan CSV: `optimized_50_stocks_portfolio.csv`
  - Gösterilen Veriler: Tüm skorlar, fiyatlar, hacim, spread, FINAL_THG, AVG_ADV, CMON, grup, benchmark değişimi.
  - Alt Butonlar: Satır seçimi, toplu emir, sıralama, sayfa geçişi.

- **Extlt35**
  - Açılan Pencere: Basit tablo penceresi.
  - Okunan CSV: `optimized_35_extlt.csv`
  - Gösterilen Veriler: `PREF IBKR`, `Final_Shares`, `FINAL_THG`, `AVG_ADV`
  - Alt Butonlar: Yok.

- **Extlt35 Maltopla**
  - Açılan Pencere: MaltoplaWindow
  - Okunan CSV: `optimized_35_extlt.csv`
  - Gösterilen Veriler: Tüm skorlar, fiyatlar, hacim, spread, FINAL_THG, AVG_ADV, CMON, grup, benchmark değişimi.
  - Alt Butonlar: Satır seçimi, toplu emir, sıralama, sayfa geçişi.

### 4. T-pref ve C-pref Sekmeleri Altındaki Butonlar

- **Maturex, NFFex, FFex, FLRex, Duzex**
  - Açılan Pencere: MaltoplaWindow
  - Okunan CSV: 
    - Maturex: `maturextlt.csv`
    - NFFex: `nffextlt.csv`
    - FFex: `ffextlt.csv`
    - FLRex: `flrextlt.csv`
    - Duzex: `duzextlt.csv`
  - Gösterilen Veriler: Ticker, fiyatlar, skorlar, hacim, spread, grup, benchmark değişimi, FINAL_THG, AVG_ADV, CMON.
  - Alt Butonlar: Satır seçimi, toplu emir, sıralama, sayfa geçişi.

- **...-çok düşen / ...-çok yükselen**
  - Açılan Pencere: MaltoplaWindow
  - Okunan CSV: Aynı şekilde ilgili grup CSV'si.
  - Gösterilen Veriler: Yukarıdakiyle aynı.

### 5. T-top Losers / T-top Gainers / Long Take Profit / Short Take Profit

- **T-top Losers / T-top Gainers**
  - Açılan Pencere: MaltoplaWindow
  - Okunan CSV: `mastermind_histport.csv`
  - Gösterilen Veriler: Tüm skorlar, fiyatlar, hacim, spread, FINAL_THG, AVG_ADV, CMON, grup, benchmark değişimi.
  - Alt Butonlar: Satır seçimi, toplu emir, sıralama, sayfa geçişi.

- **Long Take Profit / Short Take Profit**
  - Açılan Pencere: MaltoplaWindow
  - Okunan CSV: `mastermind_histport.csv` (pozisyonlar IBKR API'dan alınır, skorlar CSV'den eşlenir)
  - Gösterilen Veriler: Sadece long veya short pozisyonlar, ilgili skorlar ve fiyatlar.
  - Alt Butonlar: Satır seçimi, toplu emir, sıralama, sayfa geçişi.

### 6. Ex-Div Listesi

- **Paste Ex-Div List**
  - Açılan Pencere: Ex-dividend listesi yapıştırma ve kaydetme penceresi.
  - Okunan/Kaydedilen CSV: `Ntahaf/exdivkayit/pDDMMYY.csv` (günlük dosya)
  - İşlev: Pastedan alınan ex-div listesi parse edilir, tabloya dökülür ve CSV'ye kaydedilir. Uygulama açıldığında bugünün CSV'si otomatik yüklenir.

- **Load Ex-Div List**
  - Açılan Pencere: Ex-div listesi gösterim penceresi.
  - Okunan CSV: `Ntahaf/exdivkayit/pDDMMYY.csv` (günlük dosya)
  - Gösterilen Veriler: Ticker, Dividend.

### 7. BDATA Butonu

- **BDATA**
  - Açılan Pencere: BDATA penceresi.
  - Okunan CSV: `bdata.csv`
  - Gösterilen Veriler: Ticker, Poly, Total Size, Avg Cost, Bench Type, Avg Benchmark, Current Price, Current Benchmark, Avg Outperf, Fills.

### 8. Orderbook

- **Orderbook**
  - Açılan Pencere: OrderBookWindow
  - Veri Kaynağı: IBKR API üzerinden seçili hissenin anlık orderbook verisi.

### 9. PsfAlgo, Exclude fr Psfalgo, Psf Reasoning

- **PsfAlgo**
  - İşlev: Algoritmik işlemleri başlatır/durdurur.
  - Veri Kaynağı: IBKR ve Polygon.io API, mastermind CSV'leri.

- **Exclude fr Psfalgo**
  - Açılan Pencere: Hariç tutulacak hisseleri yönetir.
  - Okunan/Kaydedilen CSV: `excpsfalgo.csv`

- **Psf Reasoning**
  - Açılan Pencere: Algoritmanın işlem gerekçelerini gösterir.
  - Okunan Log: `logs/psf_reasoning.log`

### 10. Dictionary ve Mapping Mekanizması

- **Ticker Mapping:** IBKR tickerları ile Polygon tickerları arasında eşleme yapılır (`polygonize_ticker` fonksiyonu).
- **C-pref Mapping:** C-pref tickerları ile ilgili CSV dosyası arasında mapping (`self.c_ticker_to_csv` ve `self.c_csv_data`).
- **Mastermind Data:** `load_mastermind_data()` fonksiyonu ile `mastermind_histport.csv` ve `mastermind_extltport.csv`'den tüm skorlar ve metrikler bir dictionary'ye yüklenir.
- **Exdiv Data:** Ex-dividend verileri bir dictionary olarak tutulur ve ilgili pencerelerde kullanılır. 
