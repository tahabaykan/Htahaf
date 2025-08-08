# 🔨 Hammer Pro Watchlist Oluşturucu

Bu uygulama, mevcut CSV dosyalarınızdan (özellikle `ssfinekheldkuponlu.csv`) Hammer Pro platformunda watchlist oluşturmanızı sağlar.

## 🚀 Hızlı Başlangıç

### 1. Uygulamayı Çalıştırın
```bash
cd hammerib
python main.py
```

### 2. "Simple Watchlist Creator" Seçin
Uygulama seçici penceresinde "Simple Watchlist Creator" seçeneğini seçin.

### 3. Hammer Pro Bağlantısı
- **Host**: `127.0.0.1` (varsayılan)
- **Port**: Hammer Pro API portunuz (varsayılan: `8080`)
- **Şifre**: Hammer Pro şifreniz

### 4. CSV Dosyasını Yükleyin
- `ssfinekheldkuponlu.csv` dosyanızı seçin
- "CSV'yi Yükle" butonuna tıklayın

### 5. Watchlist Oluşturun
- **Watchlist Adı**: Örn. `SSFI_HELD_KUPONLU`
- **Watchlist Türü**: 
  - Tüm Semboller
  - En Yüksek FINAL_THG
  - En Düşük FINAL_THG
- **Maksimum Sembol Sayısı**: Örn. `50`

## 📋 Özellikler

### ✅ Mevcut Özellikler
- **Hammer Pro WebSocket Bağlantısı**: Gerçek zamanlı bağlantı
- **CSV Dosya Yükleme**: `ssfinekheldkuponlu.csv` desteği
- **Farklı Watchlist Türleri**: 
  - Tüm semboller
  - FINAL_THG'ye göre sıralama
- **Görsel Arayüz**: Kolay kullanım için GUI
- **Gerçek Zamanlı Durum**: Bağlantı durumu göstergesi

### 🔄 Watchlist Türleri

#### 1. Tüm Semboller
CSV'deki tüm benzersiz sembolleri watchlist'e ekler.

#### 2. En Yüksek FINAL_THG
FINAL_THG değeri en yüksek olan sembolleri seçer.

#### 3. En Düşük FINAL_THG
FINAL_THG değeri en düşük olan sembolleri seçer.

## 🛠️ Kurulum

### Gereksinimler
```bash
pip install websockets pandas tkinter
```

### Hammer Pro Ayarları
1. Hammer Pro'yu açın
2. Settings > API bölümüne gidin
3. Streaming API'yi etkinleştirin
4. Port numarasını not edin (varsayılan: 8080)

## 📊 Kullanım Örnekleri

### Örnek 1: Tüm SSFI Sembolleri
```
Watchlist Adı: SSFI_ALL_SYMBOLS
Watchlist Türü: Tüm Semboller
Maksimum Sembol: 100
```

### Örnek 2: En İyi FINAL_THG
```
Watchlist Adı: SSFI_TOP_FINAL_THG
Watchlist Türü: En Yüksek FINAL_THG
Maksimum Sembol: 25
```

### Örnek 3: En Düşük FINAL_THG
```
Watchlist Adı: SSFI_BOTTOM_FINAL_THG
Watchlist Türü: En Düşük FINAL_THG
Maksimum Sembol: 25
```

## 🔧 Sorun Giderme

### Bağlantı Sorunları
1. **Hammer Pro çalışıyor mu?**
2. **API etkin mi?**
3. **Port doğru mu?**
4. **Şifre doğru mu?**

### CSV Sorunları
1. **Dosya yolu doğru mu?**
2. **CSV formatı uygun mu?**
3. **PREF IBKR sütunu var mı?**

### Watchlist Sorunları
1. **Hammer Pro'da watchlist görünüyor mu?**
2. **Sembol sayısı çok fazla mı?**
3. **Sembol isimleri doğru mu?**

## 📝 Log Dosyaları

Uygulama aşağıdaki log dosyalarını oluşturur:
- `hammer_watchlist.log`: Ana log dosyası
- `hammer_integration.log`: Entegrasyon logları

## 🔄 Geliştirme

### Yeni Özellikler Ekleme
1. `simple_hammer_watchlist.py` dosyasını düzenleyin
2. Yeni watchlist türleri ekleyin
3. Farklı CSV formatları için destek ekleyin

### Örnek: Yeni Watchlist Türü
```python
elif watchlist_type == "custom_filter":
    # Özel filtreleme mantığı
    filtered_data = self.csv_data[self.csv_data['CUSTOM_COLUMN'] > threshold]
    symbols = filtered_data['PREF IBKR'].dropna().unique().tolist()[:max_symbols]
```

## 📞 Destek

Sorunlarınız için:
1. Log dosyalarını kontrol edin
2. Hammer Pro ayarlarını kontrol edin
3. CSV dosya formatını kontrol edin

## 🎯 Gelecek Özellikler

- [ ] Otomatik watchlist güncelleme
- [ ] Çoklu CSV dosya desteği
- [ ] Gelişmiş filtreleme seçenekleri
- [ ] Watchlist performans takibi
- [ ] Otomatik trading sinyalleri 