"""
JanAllSec Kullanım Örnekleri

Bu dosya JanAllSec'in nasıl kullanılacağını gösterir.
"""

# ============================================================================
# 1. CONFIG YÖNETİMİ
# ============================================================================

from config import get_config

# Config'i yükle
config = get_config()

# Config değerlerini al
hammer_host = config.get('hammer.host', '127.0.0.1')
hammer_port = config.get('hammer.port', 16400)
hammer_password = config.get('hammer.password', '')

print(f"Hammer Host: {hammer_host}:{hammer_port}")
print(f"Password set: {'Evet' if hammer_password else 'Hayır'}")

# Config değerini değiştir
config.set('hammer.port', 16401)
config.save()  # Değişiklikleri kaydet

# ============================================================================
# 2. LOGGING
# ============================================================================

from utils.logger import get_logger

# Logger'ı al
logger = get_logger()

# Farklı seviyelerde log yaz
logger.debug("Debug mesajı - detaylı bilgi")
logger.info("Bilgi mesajı - normal işlemler")
logger.warning("Uyarı mesajı - dikkat edilmesi gereken durumlar")
logger.error("Hata mesajı - hatalar")
logger.critical("Kritik mesaj - sistem çökmesi riski")

# Exception bilgisiyle log yaz
try:
    result = 1 / 0
except Exception:
    logger.exception("Bölme hatası oluştu")

# ============================================================================
# 3. VALIDATION
# ============================================================================

from utils.validators import (
    validate_symbol,
    validate_price,
    validate_lot,
    validate_csv_data,
    ValidationError
)
import pandas as pd

# Sembol doğrula
try:
    validate_symbol("VNO PRN")  # ✅ Geçerli
    validate_symbol("VNO-N")    # ✅ Geçerli
    validate_symbol("SPY")      # ✅ Geçerli
    validate_symbol("")         # ❌ Hata: Sembol boş olamaz
except ValidationError as e:
    print(f"Validation hatası: {e}")

# Fiyat doğrula
try:
    validate_price(25.50)                    # ✅ Geçerli
    validate_price(0.01)                     # ✅ Geçerli (minimum)
    validate_price(10000.0)                  # ✅ Geçerli (maksimum)
    validate_price(-5.0)                     # ❌ Hata: Pozitif olmalı
    validate_price(50000.0)                  # ❌ Hata: Maksimum değeri aşıyor
except ValidationError as e:
    print(f"Fiyat validation hatası: {e}")

# Lot doğrula
try:
    validate_lot(200)                        # ✅ Geçerli
    validate_lot(1)                         # ✅ Geçerli (minimum)
    validate_lot(100000)                     # ✅ Geçerli (maksimum)
    validate_lot(0)                          # ❌ Hata: Minimum değerin altında
    validate_lot(200000)                     # ❌ Hata: Maksimum değeri aşıyor
except ValidationError as e:
    print(f"Lot validation hatası: {e}")

# CSV verilerini doğrula
df = pd.DataFrame({
    'PREF IBKR': ['VNO PRN', 'AHL PRE', 'SPY'],
    'Bid': [17.76, 25.50, 450.0],
    'Ask': [17.78, 25.52, 450.5]
})

validation_result = validate_csv_data(df, required_columns=['PREF IBKR', 'Bid', 'Ask'])
print(f"Validation sonucu: {validation_result['valid']}")
if validation_result['errors']:
    print(f"Hatalar: {validation_result['errors']}")
if validation_result['warnings']:
    print(f"Uyarılar: {validation_result['warnings']}")

# ============================================================================
# 4. ATOMIC CSV YAZMA VE YEDEKLEME
# ============================================================================

from utils.file_utils import save_csv_atomic, auto_backup_csv
import pandas as pd

# DataFrame oluştur
df = pd.DataFrame({
    'Symbol': ['VNO PRN', 'AHL PRE'],
    'Price': [17.77, 25.51]
})

# Atomic olarak kaydet (otomatik yedekleme ile)
try:
    save_csv_atomic('test_data.csv', df, backup=True)
    print("✅ CSV başarıyla kaydedildi")
except Exception as e:
    print(f"❌ CSV kaydetme hatası: {e}")

# Manuel yedekleme
try:
    backup_path = auto_backup_csv('test_data.csv', backup_dir='backups', max_backups=30)
    print(f"✅ Yedekleme yapıldı: {backup_path}")
except Exception as e:
    print(f"❌ Yedekleme hatası: {e}")

# ============================================================================
# 5. HEALTH CHECK
# ============================================================================

from utils.health_check import get_health_status
from config import get_config

# Config'i yükle
config = get_config()

# Health check yap
health_status = get_health_status(config.config)

# Sonuçları göster
print(f"\n{'='*60}")
print("SİSTEM SAĞLIK DURUMU")
print(f"{'='*60}")
print(f"Genel Durum: {health_status['overall_status'].upper()}")
print(f"Zaman: {health_status['timestamp']}")

for check_name, check_result in health_status['checks'].items():
    status_icon = "✅" if check_result['status'] == 'healthy' else "⚠️"
    print(f"\n{status_icon} {check_name.upper()}: {check_result['status']}")
    
    for key, value in check_result.get('details', {}).items():
        print(f"  - {key}: {value}")

# ============================================================================
# 6. GERÇEK DÜNYA ÖRNEĞİ: CSV OKUMA VE İŞLEME
# ============================================================================

from utils.file_utils import save_csv_atomic
from utils.validators import validate_csv_data, ValidationError
from utils.logger import get_logger
import pandas as pd

logger = get_logger()

def process_csv_file(file_path: str):
    """
    CSV dosyasını güvenli şekilde oku, doğrula ve işle
    
    Args:
        file_path: CSV dosya yolu
    """
    try:
        # CSV'yi oku
        logger.info(f"CSV okunuyor: {file_path}")
        df = pd.read_csv(file_path)
        
        # Veriyi doğrula
        logger.info("Veri doğrulanıyor...")
        validation_result = validate_csv_data(df)
        
        if not validation_result['valid']:
            logger.error(f"Validation hatası: {validation_result['errors']}")
            return False
        
        if validation_result['warnings']:
            logger.warning(f"Validation uyarıları: {validation_result['warnings']}")
        
        # Veriyi işle (örnek: sembolleri doğrula)
        if 'PREF IBKR' in df.columns:
            invalid_symbols = []
            for idx, symbol in df['PREF IBKR'].items():
                try:
                    validate_symbol(str(symbol))
                except ValidationError as e:
                    invalid_symbols.append(f"Satır {idx}: {symbol} - {e}")
            
            if invalid_symbols:
                logger.warning(f"Geçersiz semboller bulundu: {invalid_symbols[:5]}")
        
        # İşlenmiş veriyi kaydet
        logger.info("İşlenmiş veri kaydediliyor...")
        save_csv_atomic(file_path.replace('.csv', '_processed.csv'), df, backup=True)
        
        logger.info("✅ CSV işleme tamamlandı")
        return True
        
    except Exception as e:
        logger.exception(f"CSV işleme hatası: {e}")
        return False

# Kullanım örneği
# process_csv_file('janalldata.csv')

# ============================================================================
# 7. CONFIG İLE LOGGER AYARLAMA
# ============================================================================

from config import get_config
from utils.logger import setup_logger_from_config

# Config'i yükle
config = get_config()

# Config'den logger ayarlarını yükle
logger = setup_logger_from_config(config.config)

# Artık logger kullanılabilir
logger.info("Config'den ayarlanan logger kullanılıyor")

print("\n✅ Tüm örnekler tamamlandı!")


