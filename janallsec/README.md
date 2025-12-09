# JanAllSec - Geliştirilmiş JanAll Uygulaması

## 📋 Genel Bakış

JanAllSec, orijinal JanAll uygulamasının geliştirilmiş ve güvenli versiyonudur. Tüm iyileştirmeler burada yapılmaktadır, **orijinal janall uygulamasına dokunulmaz**.

## ✨ Yeni Özellikler

### 1. 🔐 Güvenli Config Yönetimi
- API şifreleri artık kod dışında
- `.env` dosyası desteği
- Environment variable desteği
- Config dosyası: `config/config.json`

### 2. 📝 Merkezi Logging Sistemi
- Tüm loglar merkezi bir sistemde
- Günlük log dosyaları
- Hata logları ayrı dosyada
- Rotating file handler (otomatik temizleme)
- Log dizini: `logs/`

### 3. ✅ Veri Validation
- Sembol formatı kontrolü
- Fiyat değeri kontrolü
- Lot miktarı kontrolü
- CSV veri doğrulama

### 4. 💾 Atomic CSV Yazma
- Veri kaybını önler
- Geçici dosya kullanımı
- Hata durumunda otomatik temizleme

### 5. 🔄 Otomatik Yedekleme
- CSV dosyaları otomatik yedeklenir
- Yedekleme dizini: `backups/`
- Eski yedekler otomatik temizlenir
- Maksimum yedek sayısı: 30

### 6. 🏥 Health Check ve Monitoring
- Sistem sağlık kontrolü
- Bağlantı durumu kontrolü
- Dosya sistemi kontrolü
- Disk alanı kontrolü

## 🚀 Kurulum

### 1. Gereksinimleri Yükleyin

```bash
cd janallsec
pip install -r requirements.txt
```

### 2. Config Dosyasını Ayarlayın

`config/config.json` dosyasını düzenleyin:

```json
{
  "hammer": {
    "host": "127.0.0.1",
    "port": 16400,
    "password": "ENV_HAMMER_PASSWORD"
  }
}
```

### 3. Environment Variables (Opsiyonel ama Önerilen)

`.env` dosyası oluşturun:

```bash
# .env dosyası
HAMMER_PASSWORD=your_actual_password_here
```

**ÖNEMLİ:** `.env` dosyasını `.gitignore`'a ekleyin!

### 4. Uygulamayı Başlatın

```bash
python main.py
```

## 📁 Klasör Yapısı

```
janallsec/
├── config/
│   ├── __init__.py          # Config manager
│   └── config.json          # Yapılandırma dosyası
├── utils/
│   ├── __init__.py
│   ├── logger.py            # Logging sistemi
│   ├── validators.py        # Veri validation
│   ├── file_utils.py        # Dosya işlemleri
│   └── health_check.py      # Health check
├── backups/                 # Otomatik yedekler
├── logs/                    # Log dosyaları
├── main.py                  # Ana dosya
├── requirements.txt         # Gereksinimler
└── README.md                # Bu dosya
```

## 🔧 Kullanım

### Config Yönetimi

```python
from config import get_config

config = get_config()

# Config değerini al
hammer_host = config.get('hammer.host')
hammer_password = config.get('hammer.password')

# Config değerini ayarla
config.set('hammer.port', 16401)
config.save()
```

### Logging

```python
from utils.logger import get_logger

logger = get_logger()

logger.info("Bilgi mesajı")
logger.warning("Uyarı mesajı")
logger.error("Hata mesajı")
logger.exception("Exception bilgisiyle hata")
```

### Validation

```python
from utils.validators import validate_symbol, validate_price, validate_lot

# Sembol doğrula
try:
    validate_symbol("VNO PRN")
except ValidationError as e:
    print(f"Hata: {e}")

# Fiyat doğrula
validate_price(25.50, min_price=0.01, max_price=10000.0)

# Lot doğrula
validate_lot(200, min_lot=1, max_lot=100000)
```

### Atomic CSV Yazma

```python
from utils.file_utils import save_csv_atomic
import pandas as pd

df = pd.DataFrame({'col1': [1, 2, 3]})
save_csv_atomic('data.csv', df, backup=True)
```

### Health Check

```python
from utils.health_check import get_health_status
from config import get_config

config = get_config()
health = get_health_status(config.config)

print(f"Genel Durum: {health['overall_status']}")
for check_name, check_result in health['checks'].items():
    print(f"{check_name}: {check_result['status']}")
```

## 🔒 Güvenlik

### Şifre Yönetimi

**❌ YANLIŞ (Eski Yöntem):**
```python
password = 'Nl201090.'  # Kod içinde hardcoded!
```

**✅ DOĞRU (Yeni Yöntem):**
```python
# .env dosyasında
HAMMER_PASSWORD=your_password_here

# Kodda
password = os.environ.get('HAMMER_PASSWORD')
```

### .gitignore

`.env` dosyasını mutlaka `.gitignore`'a ekleyin:

```
.env
*.log
backups/
__pycache__/
```

## 📊 Log Dosyaları

Log dosyaları `logs/` dizininde saklanır:

- `janallsec_YYYYMMDD.log` - Tüm loglar
- `janallsec_errors_YYYYMMDD.log` - Sadece hatalar

Log dosyaları otomatik olarak rotate edilir (10MB maksimum, 5 backup).

## 🔄 Yedekleme

CSV dosyaları otomatik olarak yedeklenir:

- Yedekleme dizini: `backups/`
- Format: `dosya_adi_backup_YYYYMMDD_HHMMSS.csv`
- Maksimum yedek sayısı: 30 (config'de ayarlanabilir)

## 🏥 Health Check

Uygulama başlatıldığında otomatik health check yapılır:

- ✅ Bağlantı durumu
- ✅ Dosya sistemi
- ✅ Veri dosyaları
- ✅ Disk alanı
- ✅ Performans metrikleri

## 🐛 Hata Ayıklama

### Log Seviyesini Değiştirme

`config/config.json` dosyasında:

```json
{
  "logging": {
    "level": "DEBUG"  // DEBUG, INFO, WARNING, ERROR, CRITICAL
  }
}
```

### Manuel Health Check

```python
from utils.health_check import get_health_status
from config import get_config

config = get_config()
health = get_health_status(config.config)
print(health)
```

## 📝 Notlar

- **Orijinal janall uygulamasına dokunulmaz** - Tüm değişiklikler janallsec'te
- CSV dosyaları hala `StockTracker/` dizininde kalır
- Yedekler `janallsec/backups/` dizininde
- Loglar `janallsec/logs/` dizininde

## 🔮 Gelecek Geliştirmeler

- [ ] Unit testler
- [ ] Integration testler
- [ ] Performance monitoring dashboard
- [ ] Alerting sistemi (email/SMS)
- [ ] Veri tutarlılık kontrolü
- [ ] Rate limiting
- [ ] Audit trail (işlem logları)

## 🤝 Katkıda Bulunma

1. Yeni özellik eklerken önce test edin
2. Logging kullanın (print yerine)
3. Validation ekleyin
4. Dokümantasyon güncelleyin

## 📞 Destek

Sorunlar için:
1. Log dosyalarını kontrol edin (`logs/`)
2. Health check sonuçlarını inceleyin
3. Config dosyasını kontrol edin

## 📄 Lisans

Orijinal janall ile aynı lisans.
