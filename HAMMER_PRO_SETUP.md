# Hammer Pro API ile SSFINEK Dosyalarına Prev Close Ekleme

Bu script, SSFINEK dosyalarındaki PREF IBKR kolonundaki hisseler için Hammer Pro API'den previous close değerlerini çeker ve CSV dosyalarına ekler.

## Kurulum

### 1. Gerekli Kütüphaneleri Yükleyin
```bash
pip install -r requirements_hammer_pro.txt
```

### 2. Hammer Pro Ayarları
1. Hammer Pro'yu açın
2. Settings > API bölümüne gidin
3. API'yi aktif edin ve port numarasını not edin (varsayılan: 16400)
4. API şifrenizi not edin (varsayılan: Nl201090)

### 3. Script Ayarları
`npreviousadd.py` dosyasında şu değerleri güncelleyin (zaten güncellenmiş):
```python
password = "Nl201090"  # Hammer Pro şifresi
```

## Kullanım

### 1. Hammer Pro'yu Başlatın
- Hammer Pro'nun çalıştığından emin olun
- API'nin aktif olduğunu kontrol edin

### 2. Scripti Çalıştırın
```bash
python npreviousadd.py
```

## Nasıl Çalışır

1. **Dosya Tarama**: Script, `*ssfinek*.csv` pattern'ine uyan tüm dosyaları bulur
2. **Hisse Dönüşümü**: PREF IBKR kolonundaki hisselerde " PR" -> "-" dönüşümü yapar
   - Örnek: "AHL PR" -> "AHL-F"
3. **API Çağrısı**: Her hisse için Hammer Pro API'den `getSymbolSnapshot` komutu ile veri çeker
4. **Veri Kaydetme**: Prev close değerlerini `prev_close` kolonuna kaydeder
5. **Dosya Oluşturma**: İşlenen dosyaları `janek_` prefix'i ile kaydeder

## Örnek Çıktı

```
🚀 npreviousadd.py başlatılıyor...
⏰ Başlangıç zamanı: 2024-01-15 10:30:00
🔗 Hammer Pro API'ye bağlanılıyor... 127.0.0.1:16400
🔌 WebSocket bağlantısı açıldı, authenticate ediliyor...
✅ Hammer Pro API bağlantısı başarılı
🧪 Test: AAPL için prev_close çekiliyor...
[Hammer Pro] 📊 AAPL için snapshot çekiliyor...
[Hammer Pro] ✅ AAPL: prev_close = 185.92
🧪 Test sonucu: 185.92
✅ Test başarılı, SSFINEK dosyaları işleniyor...
📁 1 SSFINEK dosyası bulundu

📋 İşleniyor: ssfinekheldkuponlu.csv
🔄 25 hisse için prev_close çekiliyor...
[Hammer Pro] 📊 AHL-F için snapshot çekiliyor...
[Hammer Pro] ✅ AHL-F: prev_close = 15.45
📊 Progress: 10/25 hisse işlendi
...
✅ Kaydedildi: janek_ssfinekheldkuponlu.csv
✅ Orijinal dosya güncellendi: ssfinekheldkuponlu.csv
✅ Tamamlandı: 2024-01-15 10:35:00
```

## Hata Durumları

### Bağlantı Hatası
- Hammer Pro'nun çalıştığından emin olun
- API'nin aktif olduğunu kontrol edin
- Port numarasının doğru olduğunu kontrol edin

### Şifre Hatası
- Hammer Pro'daki API şifresinin doğru olduğunu kontrol edin

### Dosya Bulunamadı
- SSFINEK dosyalarının script ile aynı dizinde olduğunu kontrol edin

## Notlar

- Script, her hisse için 1 saniye bekleme süresi koyar (rate limiting)
- " PR" -> "-" dönüşümü otomatik olarak yapılır
- Hem orijinal dosya hem de `janek_` prefix'li dosya güncellenir
- Test için önce AAPL hissesi denenir
