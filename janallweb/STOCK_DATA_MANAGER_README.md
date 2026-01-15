# Stock Data Manager - Hisse Veri Yönetim Sistemi

## 🎯 Amaç

Ana sayfada görünen her hisse için bid, ask, last, prev_close gibi kolonlardaki verileri hisse sembolüne mapleyip, uygulama içinde herhangi bir yerden bu verilere erişim sağlamak.

## 🏗️ Sistem Mimarisi

### 1. StockDataManager Sınıfı
- **Dosya**: `janallapp/stock_data_manager.py`
- **Görev**: Tüm hisse verilerini merkezi olarak yönetmek
- **Özellikler**:
  - Her hisse sembolü için tüm kolon verilerini saklar
  - Veri geçerlilik süresi kontrolü (30 saniye)
  - Ana tablo ve CSV verilerini birleştirir
  - Hızlı veri erişim metodları

### 2. Ana Pencere Entegrasyonu
- **Dosya**: `janallapp/main_window.py`
- **Entegrasyon**: 
  - Ana tablo güncellendiğinde veri yönetici güncellenir
  - CSV dosyaları yüklendiğinde veri yönetici güncellenir
  - "Stock Data Status" butonu ile durum kontrolü

### 3. Port Adjuster Entegrasyonu
- **Dosya**: `janallapp/port_adjuster.py`
- **Özellikler**:
  - "Hisse Veri Çek" butonu ile tüm hisseleri listele
  - Hisse arama kutusu ile belirli hisse verilerini görüntüle
  - Final_FB_skor, Final_SFS_skor gibi skor verilerine erişim

## 🚀 Kullanım

### 1. Ana Pencere
```python
# Stock Data Manager otomatik olarak başlatılır
# Ana tablo güncellendiğinde veriler otomatik kaydedilir
# CSV dosyaları yüklendiğinde veriler otomatik kaydedilir

# Durum kontrolü için "Stock Data Status" butonuna tıklayın
```

### 2. Port Adjuster
```python
# Port Adjuster'ı açın
# "Hisse Veri Çek" butonuna tıklayarak tüm hisseleri listeleyin
# Hisse arama kutusuna sembol girin (örn: CFG PRE)
# "Ara" butonuna tıklayarak hisse verilerini görüntüleyin
```

### 3. Programatik Kullanım
```python
from janallapp.stock_data_manager import StockDataManager

# Manager'ı oluştur
manager = StockDataManager()

# Belirli bir hisse için veri al
stock_data = manager.get_stock_data('CFG PRE')
price_data = manager.get_stock_price_data('CFG PRE')
score_data = manager.get_stock_scores('CFG PRE')

# Belirli bir kolon için tüm hisselerin verilerini al
fb_scores = manager.get_stock_column_data('Final_FB_skor')
sfs_scores = manager.get_stock_column_data('Final_SFS_skor')

# Hisse arama
cfg_stocks = manager.search_stocks('CFG')
```

## 📊 Veri Yapısı

### Ana Veriler
- **PREF IBKR**: Hisse sembolü (örn: CFG PRE)
- **prev_close**: Önceki kapanış fiyatı
- **Bid**: Alış teklifi
- **Ask**: Satış teklifi  
- **Last**: Son işlem fiyatı
- **Volume**: İşlem hacmi

### Skor Verileri
- **Final_BB_skor**: Final Bid Buy skoru
- **Final_FB_skor**: Final Front Buy skoru
- **Final_AB_skor**: Final Ask Buy skoru
- **Final_AS_skor**: Final Ask Sell skoru
- **Final_FS_skor**: Final Front Sell skoru
- **Final_BS_skor**: Final Bid Sell skoru
- **Final_SAS_skor**: Final Short Ask Sell skoru
- **Final_SFS_skor**: Final Short Front Sell skoru
- **Final_SBS_skor**: Final Short Bid Sell skoru

### Diğer Veriler
- **CMON**: CMON değeri
- **CGRUP**: CGRUP kategorisi
- **FINAL_THG**: FINAL THG değeri
- **AVG_ADV**: Ortalama ADV değeri
- **SMI**: SMI değeri
- **SHORT_FINAL**: Short final değeri
- **Benchmark_Type**: Benchmark tipi
- **Benchmark_Chg**: Benchmark değişimi

## 🔧 Test

### Test Scripti Çalıştırma
```bash
cd janall
python test_stock_data_manager.py
```

### Test Senaryoları
1. ✅ Ana tablo verilerini güncelleme
2. ✅ CSV verilerini ekleme
3. ✅ Hisse verilerini alma
4. ✅ Fiyat verilerini alma
5. ✅ Skor verilerini alma
6. ✅ Kolon verilerini alma
7. ✅ Hisse arama
8. ✅ Durum özeti alma

## 📈 Performans

### Veri Geçerlilik Süresi
- **Varsayılan**: 30 saniye
- **Ayarlanabilir**: `data_validity_duration` parametresi

### Cache Sistemi
- **Otomatik Temizlik**: Süresi dolmuş veriler otomatik temizlenir
- **Bellek Optimizasyonu**: Sadece geçerli veriler saklanır

### Hızlı Erişim
- **Dictionary Tabanlı**: O(1) erişim süresi
- **Lazy Loading**: Veriler sadece gerektiğinde yüklenir

## 🐛 Hata Ayıklama

### Log Mesajları
```
[STOCK_DATA_MANAGER] ✅ Stock Data Manager başlatıldı
[STOCK_DATA_MANAGER] 🔄 Ana tablo verileri güncelleniyor... 150 hisse
[STOCK_DATA_MANAGER] ✅ 150 hisse için veriler güncellendi
[STOCK_DATA_MANAGER] ⚠️ CFG PRE için veri bulunamadı
```

### Hata Kontrolü
- **Veri Bulunamadı**: `None` döndürülür
- **Süresi Dolmuş Veri**: Otomatik temizlenir
- **CSV Okuma Hatası**: Hata loglanır, işlem devam eder

## 🔮 Gelecek Geliştirmeler

### Planlanan Özellikler
1. **Real-time Updates**: WebSocket ile gerçek zamanlı güncelleme
2. **Data Export**: JSON, Excel formatlarında export
3. **Advanced Search**: Filtreleme ve sıralama özellikleri
4. **Performance Monitoring**: Veri erişim istatistikleri
5. **Backup System**: Veri yedekleme ve geri yükleme

### API Genişletmeleri
1. **Batch Operations**: Toplu veri işlemleri
2. **Event System**: Veri değişiklik olayları
3. **Plugin System**: Üçüncü parti eklenti desteği

## 📝 Notlar

### Önemli Noktalar
- Stock Data Manager otomatik olarak başlatılır
- Veriler ana tablo güncellendiğinde otomatik kaydedilir
- CSV verileri yüklendiğinde otomatik birleştirilir
- Veri geçerlilik süresi 30 saniye (ayarlanabilir)

### Sınırlamalar
- Veriler sadece uygulama çalıştığı sürece saklanır
- Disk üzerinde kalıcı depolama yok
- Çok büyük veri setleri için bellek optimizasyonu gerekebilir

### Güvenlik
- Veriler sadece yerel olarak saklanır
- Dış bağlantı yok
- API anahtarı gerektirmez

## 🤝 Destek

### Sorun Giderme
1. **Veri Bulunamadı**: "Stock Data Status" butonuna tıklayın
2. **Güncel Veri Yok**: Ana tabloyu yenileyin
3. **CSV Hatası**: CSV dosyasını kontrol edin

### İletişim
- Hata raporları için log mesajlarını kontrol edin
- Performans sorunları için veri geçerlilik süresini ayarlayın





















