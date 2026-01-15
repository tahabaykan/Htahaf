# IBKR Entegrasyonu - HAMPRO MOD ve IBKR MOD

Bu entegrasyon ile uygulamanızda iki farklı mod kullanabilirsiniz:

## 🔄 Modlar

### HAMPRO MOD (Varsayılan)
- **Pozisyonlar**: Hammer Pro hesabınızdan
- **Emirler**: Hammer Pro hesabınızdan  
- **Market Data**: Hammer Pro'dan (her zaman)

### IBKR MOD
- **Pozisyonlar**: IBKR hesabınızdan
- **Emirler**: IBKR hesabınızdan
- **Market Data**: Hammer Pro'dan (her zaman)

## 🚀 Kurulum

### 1. IBKR TWS/Gateway Kurulumu

1. **IBKR TWS veya Gateway'i indirin**
   - IBKR hesabınıza giriş yapın
   - Account Management > Downloads
   - "Trader Workstation (TWS)" veya "IB Gateway" indirin

2. **TWS/Gateway'i çalıştırın**
   - TWS: Tam özellikli trading platform
   - Gateway: Sadece API bağlantıları için hafif versiyon

3. **API Ayarlarını Yapın**
   - TWS/Gateway'de: Edit > Global Configuration > API > Settings
   - "Enable ActiveX and Socket Clients" işaretleyin
   - Socket port: 4001 (live hesap) veya 4002 (paper hesap)
   - "Read-Only API" işaretini kaldırın (emir göndermek için)

4. **Python ibapi paketini kurun**
   ```bash
   pip install ibapi
   ```

## 🎯 Kullanım

### Mod Değiştirme
1. Uygulamayı başlatın
2. Üst panelde **HAMPRO MOD** ve **IBKR MOD** butonlarını görün
3. İstediğiniz moda tıklayın
4. Aktif mod vurgulanır (Accent.TButton stili)

### Pozisyonları Görüntüleme
1. **Pozisyonlarım** butonuna tıklayın
2. Seçili moda göre:
   - **HAMPRO MOD**: Hammer Pro pozisyonları gösterilir
   - **IBKR MOD**: IBKR pozisyonları gösterilir

### Market Data
- Market data **her zaman** Hammer Pro'dan alınır
- Mod değişikliği market data'yı etkilemez
- L1 ve L2 veriler Hammer Pro'dan gelmeye devam eder

## 🔧 Teknik Detaylar

### Dosya Yapısı
```
janall/janallapp/
├── ibkr_client.py          # IBKR Client Portal API client
├── mode_manager.py          # Mod yönetimi
├── ibkr_positions.py        # IBKR pozisyon görüntüleme
├── main_window.py           # Ana pencere (mod butonları eklendi)
└── __init__.py              # Import'lar güncellendi
```

### API Metodları
- **Pozisyonlar**: `reqPositions()` - Tüm pozisyonları al
- **Emirler**: `reqAllOpenOrders()` - Açık emirleri al
- **Hesaplar**: `reqManagedAccts()` - Hesapları al
- **Bağlantı**: `connect()` - TWS/Gateway'e bağlan

### Port Ayarları
- **IBKR TWS/Gateway**: Port 4001 (live hesap) veya 4002 (paper hesap)
- **Hammer Pro**: Port 16400 (değişmedi)

## ⚠️ Önemli Notlar

### Güvenlik
- IBKR TWS/Gateway sadece yerel makinenizde çalışır
- Socket bağlantısı güvenlidir
- API izinleri TWS/Gateway ayarlarından kontrol edilir

### Sınırlamalar
- TWS/Gateway API tüm hesap türleri için desteklenir
- Demo hesapları da API erişimi için uygundur
- TWS/Gateway'in çalışır durumda olması gerekir

### Sorun Giderme

#### IBKR TWS/Gateway Bağlantı Hatası
```
❌ IBKR TWS/Gateway'e bağlanılamıyor
💡 Kontrol edilecekler:
   1. IBKR TWS/Gateway çalışıyor mu?
   2. Port 4001 (live) veya 4002 (paper) açık mı?
   3. API izinleri aktif mi?
   4. Client ID çakışması var mı?
```

**Çözümler:**
1. TWS/Gateway'in çalıştığını kontrol edin: `netstat -an | findstr 4001`
2. TWS/Gateway'de API ayarlarını kontrol edin
3. "Enable ActiveX and Socket Clients" işaretli mi?
4. Socket port doğru mu? (4001 veya 4002)
5. "Read-Only API" işareti kaldırıldı mı?
6. Client ID çakışması var mı? (farklı bir ID deneyin)

#### Pozisyon Bulunamadı
```
⚠️ Pozisyon bulunamadı
💡 Kontrol edilecekler:
   1. IBKR TWS/Gateway çalışıyor mu?
   2. Bağlantı kuruldu mu?
   3. Pozisyon var mı?
```

**Çözümler:**
1. IBKR hesabınızda pozisyon olduğunu kontrol edin
2. TWS/Gateway'in çalışır durumda olduğunu kontrol edin
3. API izinlerinin aktif olduğunu kontrol edin
4. Bağlantı durumunu kontrol edin

## 📊 Özellikler

### Pozisyon Görüntüleme
- Symbol, Qty, Avg Cost, Current Price
- PnL hesaplama
- AVG_ADV ve MAXALW değerleri
- SMI, Final FB, Final SFS skorları
- Sıralama (kolon başlıklarına tıklayarak)

### Mod Yönetimi
- Otomatik mod değiştirme
- Bağlantı durumu kontrolü
- Hata durumunda otomatik geri dönüş
- Callback sistemi

### Uyumluluk
- Mevcut Hammer Pro entegrasyonu korundu
- Market data akışı değişmedi
- Tüm mevcut özellikler çalışmaya devam eder

## 🔄 Güncellemeler

Bu entegrasyon mevcut sisteminizi bozmaz:
- Hammer Pro bağlantısı aynen çalışır
- Market data akışı değişmez
- Tüm mevcut butonlar ve özellikler korunur
- Sadece pozisyon ve emir kaynakları moda göre değişir

---

**Not**: Bu entegrasyon sadece pozisyon ve emir verilerini moda göre değiştirir. Market data her zaman Hammer Pro'dan alınır ve bu kısımda hiçbir değişiklik yapılmamıştır.
