"""
JanAllSec - Geliştirilmiş JanAll Uygulaması Ana Dosyası

Bu uygulama orijinal janall uygulamasının geliştirilmiş versiyonudur.
Tüm iyileştirmeler burada yapılmaktadır, orijinal janall'a dokunulmaz.
"""

import sys
import os
from pathlib import Path

# Proje kök dizinini path'e ekle
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Config ve logger'ı yükle
from config import get_config
from utils.logger import setup_logger_from_config
from utils.health_check import get_health_status

def main():
    """Ana fonksiyon"""
    print("=" * 60)
    print("JanAllSec - Geliştirilmiş JanAll Uygulaması")
    print("=" * 60)
    
    # Config yükle
    config = get_config()
    print(f"[MAIN] ✅ Config yüklendi")
    
    # Logger'ı ayarla
    logger = setup_logger_from_config(config.config)
    logger.info("JanAllSec başlatılıyor...")
    
    # Health check yap
    print("\n[MAIN] 🔍 Sistem sağlık kontrolü yapılıyor...")
    health_status = get_health_status(config.config)
    
    print(f"\n[HEALTH CHECK] Genel Durum: {health_status['overall_status'].upper()}")
    for check_name, check_result in health_status['checks'].items():
        status_icon = "✅" if check_result['status'] == 'healthy' else "⚠️"
        print(f"  {status_icon} {check_name}: {check_result['status']}")
        for key, value in check_result.get('details', {}).items():
            print(f"    - {key}: {value}")
    
    if health_status['overall_status'] != 'healthy':
        logger.warning("Sistem sağlık kontrolünde sorunlar tespit edildi")
    
    # Orijinal janall uygulamasını import et ve başlat
    print("\n[MAIN] 🔄 Orijinal janall uygulaması başlatılıyor...")
    
    try:
        # Orijinal janall'ı import et
        sys.path.insert(0, str(project_root.parent / 'janall'))
        from janallapp import MainWindow
        
        # MainWindow'u config ile başlat
        app = MainWindow()
        
        # Config'i MainWindow'a ekle (opsiyonel)
        if hasattr(app, 'config'):
            app.config = config
        else:
            app.config = config
        
        logger.info("JanAllSec başarıyla başlatıldı")
        print("\n[MAIN] ✅ JanAllSec hazır!")
        print("[MAIN] 💡 Orijinal janall uygulaması çalışıyor")
        print("[MAIN] 💡 Tüm iyileştirmeler aktif")
        
        # Ana döngüyü başlat
        app.mainloop()
        
    except ImportError as e:
        logger.error(f"Orijinal janall import hatası: {e}")
        print(f"\n[MAIN] ❌ Hata: Orijinal janall uygulaması bulunamadı")
        print(f"[MAIN] 💡 Kontrol edin: {project_root.parent / 'janall'}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"Uygulama başlatma hatası: {e}")
        print(f"\n[MAIN] ❌ Hata: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()


