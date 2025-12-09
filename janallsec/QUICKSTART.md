# JanAllSec Hızlı Başlangıç Kılavuzu

## 🚀 5 Dakikada Başlayın

### Adım 1: Klasöre Geçin
```bash
cd janallsec
```

### Adım 2: Gereksinimleri Yükleyin
```bash
pip install -r requirements.txt
```

### Adım 3: .env Dosyası Oluşturun
```bash
# Windows PowerShell
echo "HAMMER_PASSWORD=your_password_here" > .env

# Linux/Mac
echo "HAMMER_PASSWORD=your_password_here" > .env
```

**ÖNEMLİ:** `your_password_here` yerine gerçek şifrenizi yazın!

### Adım 4: Config Dosyasını Kontrol Edin
`config/config.json` dosyasını açın ve gerekirse düzenleyin.

### Adım 5: Uygulamayı Başlatın
```bash
python main.py
```

## ✅ Başarılı Kurulum Kontrolü

Uygulama başladığında şunları görmelisiniz:

```
============================================================
JanAllSec - Geliştirilmiş JanAll Uygulaması
============================================================
[CONFIG] ✅ Config dosyası yüklendi: ...
[MAIN] ✅ Config yüklendi
[MAIN] 🔍 Sistem sağlık kontrolü yapılıyor...

[HEALTH CHECK] Genel Durum: HEALTHY
  ✅ connections: healthy
  ✅ filesystem: healthy
  ✅ data: healthy
  ✅ performance: healthy

[MAIN] 🔄 Orijinal janall uygulaması başlatılıyor...
[MAIN] ✅ JanAllSec hazır!
```

## 🔧 Sorun Giderme

### Problem: "Config dosyası bulunamadı"
**Çözüm:** `config/config.json` dosyasının var olduğundan emin olun.

### Problem: "HAMMER_PASSWORD environment variable bulunamadı"
**Çözüm:** `.env` dosyasını oluşturun ve şifrenizi ekleyin.

### Problem: "Orijinal janall uygulaması bulunamadı"
**Çözüm:** `janall` klasörünün `janallsec` ile aynı seviyede olduğundan emin olun:
```
StockTracker/
├── janall/
└── janallsec/
```

### Problem: "Import hatası"
**Çözüm:** Gereksinimleri yüklediğinizden emin olun:
```bash
pip install -r requirements.txt
```

## 📚 Sonraki Adımlar

1. **Örnekleri İnceleyin:** `examples/usage_examples.py`
2. **Dokümantasyonu Okuyun:** `README.md`
3. **Log Dosyalarını Kontrol Edin:** `logs/` dizini
4. **Health Check Yapın:** Uygulama başlatıldığında otomatik yapılır

## 💡 İpuçları

- Log dosyaları `logs/` dizininde saklanır
- Yedekler `backups/` dizininde saklanır
- Config değişiklikleri `config/config.json` dosyasında yapılır
- `.env` dosyasını `.gitignore`'a eklemeyi unutmayın!

## 🆘 Yardım

Sorun yaşıyorsanız:
1. Log dosyalarını kontrol edin: `logs/janallsec_errors_*.log`
2. Health check sonuçlarını inceleyin
3. Config dosyasını kontrol edin


