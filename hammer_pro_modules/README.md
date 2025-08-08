# Hammer Pro FINAL BB Score Calculator

Bu uygulama, Hammer Pro'nun gerçek zamanlı market data'sını kullanarak FINAL BB skorlarını hesaplar. Orijinal formülü kullanarak `bid`, `ask`, `volume`, `last price` ve `benchmark` verilerini entegre eder.

## 🎯 FINAL BB Skor Formülü

### Ana Formül
```
FINAL_BB = FINAL_THG - 400 × bid_buy_ucuzluk
```

### Detaylı Hesaplamalar

#### 1. Bid Buy Ucuzluk (BB)
```
pf_bid_buy = bid + spread × 0.15
pf_bid_buy_chg = pf_bid_buy - prev_close
bid_buy_ucuzluk = pf_bid_buy_chg - benchmark
```

#### 2. Front Buy Ucuzluk (FB)
```
pf_front_buy = last + 0.01
pf_front_buy_chg = pf_front_buy - prev_close
front_buy_ucuzluk = pf_front_buy_chg - benchmark
```

#### 3. Ask Buy Ucuzluk (AB)
```
pf_ask_buy = ask + 0.01
pf_ask_buy_chg = pf_ask_buy - prev_close
ask_buy_ucuzluk = pf_ask_buy_chg - benchmark
```

#### 4. Ask Sell Pahalilik (AS)
```
pf_ask_sell = ask - spread × 0.15
pf_ask_sell_chg = pf_ask_sell - prev_close
ask_sell_pahali = pf_ask_sell_chg - benchmark
```

#### 5. Front Sell Pahalilik (FS)
```
pf_front_sell = last - 0.01
pf_front_sell_chg = pf_front_sell - prev_close
front_sell_pahali = pf_front_sell_chg - benchmark
```

#### 6. Bid Sell Pahalilik (BS)
```
pf_bid_sell = bid - 0.01
pf_bid_sell_chg = pf_bid_sell - prev_close
bid_sell_pahali = pf_bid_sell_chg - benchmark
```

### Tüm FINAL Skorlar
```
FINAL_BB = FINAL_THG - 400 × bid_buy_ucuzluk
FINAL_FB = FINAL_THG - 400 × front_buy_ucuzluk
FINAL_AB = FINAL_THG - 400 × ask_buy_ucuzluk
FINAL_AS = FINAL_THG - 400 × ask_sell_pahali
FINAL_FS = FINAL_THG - 400 × front_sell_pahali
FINAL_BS = FINAL_THG - 400 × bid_sell_pahali
```

## 🔧 Market Data Kullanımı

### Hammer Pro'dan Alınan Veriler
- **Bid**: Alış fiyatı
- **Ask**: Satış fiyatı
- **Last**: Son işlem fiyatı
- **Prev Close**: Önceki kapanış fiyatı
- **Volume**: İşlem hacmi
- **Spread**: Ask - Bid farkı

### Benchmark Hesaplama
```
Benchmark Type 'T' (Treasury): 0.5
Benchmark Type 'C' (Corporate): 0.3
Default: 0.0
```

## 📊 Uygulama Özellikleri

### 1. Hammer Pro Bağlantısı
- WebSocket bağlantısı ile gerçek zamanlı veri
- Otomatik authentication
- Bağlantı durumu takibi

### 2. CSV Veri Yönetimi
- SSFI CSV dosyalarını yükleme
- FINAL_THG verilerini okuma
- Sembol listesi filtreleme

### 3. Market Data Güncelleme
- Tek sembol snapshot
- Portföy snapshot
- Gerçek zamanlı abonelik

### 4. FINAL BB Hesaplama
- Orijinal formül kullanımı
- Batch hesaplama
- Sonuç tablosu

## 🚀 Kullanım

### 1. Uygulamayı Başlat
```bash
cd hammer_pro_modules
python main.py
```

### 2. Hammer Pro'ya Bağlan
- Host: `127.0.0.1` (varsayılan)
- Port: `8080` (varsayılan)
- Password: Hammer Pro ayarlarınızdan

### 3. CSV Yükle
- SSFI CSV dosyasını seçin
- "CSV Yükle" butonuna tıklayın

### 4. Market Data Güncelle
- "Market Data Güncelle" butonuna tıklayın
- Hammer Pro'dan gerçek zamanlı veriler alınır

### 5. FINAL BB Hesapla
- "FINAL BB Hesapla" butonuna tıklayın
- Tüm skorlar hesaplanır ve tabloda gösterilir

## 📋 Modüller

### `connection.py`
- WebSocket bağlantı yönetimi
- JSON mesaj gönderme/alma
- Authentication

### `market_data_manager.py`
- Gerçek zamanlı market data alma
- FINAL BB skor hesaplama
- Benchmark entegrasyonu

### `csv_handler.py`
- CSV dosya okuma
- Veri doğrulama
- Sembol filtreleme

### `watchlist_manager.py`
- Watchlist oluşturma
- Portföy yönetimi
- Sembol ekleme/çıkarma

### `layout_manager.py`
- Layout oluşturma
- Layout yükleme/kaydetme
- Sembol ekleme

## 🔍 Örnek Kullanım Senaryosu

1. **Hammer Pro'yu açın** ve API'yi etkinleştirin
2. **Uygulamayı başlatın** ve bağlanın
3. **SSFI CSV dosyasını yükleyin** (örn: `ssfinekheldkuponlu.csv`)
4. **Market data'yı güncelleyin** (Hammer Pro'dan gerçek zamanlı veriler)
5. **FINAL BB skorlarını hesaplayın**
6. **Sonuçları inceleyin** - hangi skorların market data ile hesaplandığını görün

## 📈 Sonuç Yorumlama

### Market Data Mevcut (✓)
- Gerçek zamanlı bid/ask verileri kullanıldı
- Spread hesaplaması yapıldı
- Benchmark entegrasyonu aktif

### Market Data Yok (✗)
- Sadece FINAL_THG değeri kullanıldı
- Market data hesaplamaları atlandı
- CSV'deki statik veriler kullanıldı

## 🛠️ Teknik Detaylar

### Güvenli Float Dönüşümü
```python
def safe_float(self, x):
    try: 
        return float(x)
    except: 
        return None
```

### Benchmark Hesaplama
```python
def calculate_benchmark(self, benchmark_type: str = 'T') -> float:
    if benchmark_type == 'T':
        return 0.5  # Treasury benchmark
    elif benchmark_type == 'C':
        return 0.3  # Corporate benchmark
    else:
        return 0.0
```

### FINAL Skor Hesaplama
```python
def final_skor(final_thg, skor):
    try:
        if skor is None:
            return final_thg
        return float(final_thg) - 400 * float(skor)
    except:
        return final_thg
```

## 📝 Log Dosyaları

- `hammer_pro_final_bb.log`: Ana uygulama logları
- `hammer_pro.log`: Hammer Pro bağlantı logları

## 🔗 Bağımlılıklar

- `asyncio`: Asenkron WebSocket bağlantısı
- `websockets`: WebSocket client
- `pandas`: CSV veri işleme
- `tkinter`: GUI
- `threading`: Asenkron işlemler

## 🎯 Sonuç

Bu uygulama, Hammer Pro'nun gerçek zamanlı market data'sını kullanarak FINAL BB skorlarını hesaplar. Orijinal formülü koruyarak, `bid`, `ask`, `volume`, `last price` ve `benchmark` verilerini entegre eder ve daha doğru skorlar üretir.

**Önemli**: Market data mevcut olduğunda, skorlar gerçek zamanlı verilerle hesaplanır. Market data yoksa, sadece CSV'deki FINAL_THG değerleri kullanılır. 