# Hammer Pro Stock Tracker

Bu uygulama, Hammer Pro'nun WebSocket API'sini kullanarak hisse senedi verilerini takip etmek için geliştirilmiştir. Ptahaf uygulamasının Hammer Pro versiyonudur.

## Özellikler

- **Hammer Pro WebSocket API Entegrasyonu**: Gerçek zamanlı market verisi
- **CSV Veri Yönetimi**: Historical, Extended, Mastermind ve Befday verilerini destekler
- **Çoklu Tab Desteği**: 4 farklı veri kaynağı için ayrı tablar
- **Canlı Veri Güncellemeleri**: Gerçek zamanlı fiyat ve hacim verileri
- **Pozisyon Takibi**: Long/Short pozisyon bilgileri
- **SMA Hesaplamaları**: Basit hareketli ortalama göstergeleri

## Kurulum

### Gereksinimler

1. **Hammer Pro**: [Hammer Pro](http://www.alaricsecurities.com) kurulu ve çalışır durumda olmalı
2. **Python 3.8+**: Python 3.8 veya üzeri
3. **WebSocket API Etkin**: Hammer Pro'da API etkinleştirilmiş olmalı

### Adımlar

1. **Bağımlılıkları yükleyin**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Hammer Pro'yu yapılandırın**:
   - Hammer Pro'yu açın
   - Settings > API bölümüne gidin
   - WebSocket API'yi etkinleştirin
   - Port numarasını not edin (varsayılan: 8080)
   - Şifrenizi belirleyin

3. **CSV dosyalarını yerleştirin**:
   - `historical_data.csv`
   - `extlthistorical.csv`
   - `mastermind_extltport.csv`
   - `befday.csv`

## Kullanım

### Uygulamayı Başlatma

```bash
python main.py
```

### Bağlantı Kurma

1. **Connect** butonuna tıklayın
2. Hammer Pro'nun çalıştığından emin olun
3. Bağlantı durumu "Connected" olarak değişecektir

### Veri Görüntüleme

- **Historical Tab**: Tarihsel veri
- **Extended Tab**: Genişletilmiş veri
- **Mastermind Tab**: Mastermind veri
- **Befday Tab**: Befday veri

### Canlı Veri

- **Toggle Live Data** butonuna tıklayarak canlı veri güncellemelerini açın/kapatın
- Canlı veri açıkken tablolar otomatik olarak güncellenir

## Hammer Pro API Konfigürasyonu

### WebSocket Bağlantısı

Uygulama varsayılan olarak şu ayarları kullanır:
- **Host**: 127.0.0.1
- **Port**: 8080 (Hammer Pro'da ayarladığınız port)
- **Password**: (Hammer Pro'da belirlediğiniz şifre)

### Market Data Streamer

Varsayılan olarak "AMTD" streamer kullanılır. Farklı bir streamer kullanmak için:

```python
# Market data manager'da streamer ID'sini değiştirin
self.market_data.start_data_streamer('YOUR_STREAMER_ID')
```

## Dosya Yapısı

```
HammerProApp/
├── main.py                 # Ana uygulama girişi
├── requirements.txt        # Python bağımlılıkları
├── README.md              # Bu dosya
├── data/
│   ├── __init__.py
│   ├── hammer_pro_client.py  # Hammer Pro WebSocket client
│   └── market_data.py        # Market data manager
├── gui/
│   ├── __init__.py
│   └── main_window.py        # Ana GUI penceresi
└── *.csv                   # Veri dosyaları
```

## API Komutları

Uygulama aşağıdaki Hammer Pro API komutlarını kullanır:

### Bağlantı
- `connect`: Kimlik doğrulama
- `enumDataStreamers`: Mevcut streamer'ları listele
- `startDataStreamer`: Streamer başlat

### Market Data
- `subscribe`: L1/L2 market data aboneliği
- `unsubscribe`: Market data aboneliğini iptal et
- `L1Update`: Level 1 veri güncellemeleri
- `L2Update`: Level 2 veri güncellemeleri

### Trading
- `enumTradingAccounts`: Trading hesaplarını listele
- `getPositions`: Pozisyon bilgilerini al
- `getBalances`: Bakiye bilgilerini al

### Portfolio
- `enumPorts`: Portföyleri listele
- `enumPortSymbols`: Portföy sembollerini listele

## Sorun Giderme

### Bağlantı Sorunları

1. **Hammer Pro çalışıyor mu?**
   - Hammer Pro'nun açık olduğundan emin olun

2. **API etkin mi?**
   - Settings > API bölümünde WebSocket API'nin etkin olduğunu kontrol edin

3. **Port doğru mu?**
   - Hammer Pro'da ayarladığınız port numarasını kontrol edin

4. **Şifre doğru mu?**
   - Hammer Pro'da belirlediğiniz şifreyi kontrol edin

### Veri Sorunları

1. **CSV dosyaları mevcut mu?**
   - Gerekli CSV dosyalarının uygulama klasöründe olduğunu kontrol edin

2. **Streamer çalışıyor mu?**
   - Hammer Pro'da data streamer'ın başlatıldığını kontrol edin

## Geliştirme

### Yeni Özellik Ekleme

1. **Market Data Manager**'a yeni metodlar ekleyin
2. **GUI**'ye yeni bileşenler ekleyin
3. **Hammer Pro Client**'a yeni API komutları ekleyin

### Hata Ayıklama

Log seviyesini DEBUG'a ayarlayın:

```python
logging.basicConfig(level=logging.DEBUG)
```

## Lisans

Bu proje eğitim amaçlı geliştirilmiştir.

## İletişim

Sorularınız için: support@alaricsecurities.com 