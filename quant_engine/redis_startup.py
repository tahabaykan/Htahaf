#!/usr/bin/env python3
# Redis Startup Checker ve Başlatıcı
# Bilgisayar açıldığında Redis'in çalışıp çalışmadığını kontrol eder ve gerekirse başlatır.
#
# Kullanım:
#     python redis_startup.py
#
# Windows Task Scheduler'a eklemek için:
#     1. Windows Task Scheduler'ı açın
#     2. "Create Basic Task" seçin
#     3. Trigger: "When the computer starts"
#     4. Action: "Start a program"
#     5. Program: python
#     6. Arguments: C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\quant_engine\redis_startup.py
#     7. Start in: C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\quant_engine

import subprocess
import sys
import os
import time
from pathlib import Path

def check_redis_connection():
    """Redis'in çalışıp çalışmadığını kontrol et"""
    try:
        import redis
        client = redis.Redis(host='localhost', port=6379, socket_connect_timeout=2)
        client.ping()
        return True
    except Exception:
        return False

def start_redis_windows():
    """Windows'ta Redis'i başlat (WSL veya native Redis)"""
    try:
        # WSL'de Redis başlatma
        result = subprocess.run(
            ['wsl', 'sudo', 'service', 'redis-server', 'start'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print("✅ Redis WSL'de başlatıldı")
            return True
    except FileNotFoundError:
        # WSL yok, native Windows Redis dene
        pass
    except subprocess.TimeoutExpired:
        print("⚠️ Redis başlatma zaman aşımına uğradı")
        return False
    except Exception as e:
        print(f"⚠️ WSL Redis başlatma hatası: {e}")
    
    # Native Windows Redis (eğer kuruluysa)
    try:
        # Redis Windows servisini başlat
        result = subprocess.run(
            ['sc', 'start', 'Redis'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print("✅ Redis Windows servisi başlatıldı")
            return True
    except Exception as e:
        print(f"⚠️ Windows Redis servisi başlatılamadı: {e}")
    
    return False

def start_redis_linux():
    """Linux'ta Redis'i başlat"""
    try:
        result = subprocess.run(
            ['sudo', 'service', 'redis-server', 'start'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print("✅ Redis başlatıldı")
            return True
        else:
            print(f"⚠️ Redis başlatma hatası: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("⚠️ Redis başlatma zaman aşımına uğradı")
        return False
    except Exception as e:
        print(f"⚠️ Redis başlatma hatası: {e}")
        return False

def enable_redis_autostart_linux():
    """Linux'ta Redis'in otomatik başlamasını etkinleştir (systemd)"""
    try:
        result = subprocess.run(
            ['sudo', 'systemctl', 'enable', 'redis-server'],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            print("✅ Redis otomatik başlatma etkinleştirildi (systemd)")
            return True
        else:
            print(f"⚠️ Otomatik başlatma etkinleştirilemedi: {result.stderr}")
            return False
    except Exception as e:
        print(f"⚠️ Otomatik başlatma hatası: {e}")
        return False

def main():
    """Ana fonksiyon"""
    print("=" * 60)
    print("Redis Startup Checker")
    print("=" * 60)
    print()
    
    # Redis bağlantısını kontrol et
    print("🔍 Redis bağlantısı kontrol ediliyor...")
    if check_redis_connection():
        print("✅ Redis zaten çalışıyor!")
        print("   Bağlantı: localhost:6379")
        return 0
    
    print("❌ Redis çalışmıyor. Başlatılıyor...")
    print()
    
    # İşletim sistemine göre başlat
    success = False
    if sys.platform == "win32":
        # Windows
        print("🪟 Windows tespit edildi. WSL Redis deneniyor...")
        success = start_redis_windows()
        
        if not success:
            print()
            print("⚠️ Redis otomatik başlatılamadı.")
            print("📝 Manuel başlatma:")
            print("   1. WSL'de: wsl sudo service redis-server start")
            print("   2. Veya Windows Redis servisi: sc start Redis")
    else:
        # Linux/Mac
        print("🐧 Linux/Mac tespit edildi. Redis başlatılıyor...")
        success = start_redis_linux()
        
        if success:
            # Otomatik başlatmayı etkinleştir
            print()
            print("🔧 Redis otomatik başlatma etkinleştiriliyor...")
            enable_redis_autostart_linux()
    
    # Başlatma sonrası kontrol
    if success:
        print()
        print("⏳ Redis'in başlaması bekleniyor (3 saniye)...")
        time.sleep(3)
        
        if check_redis_connection():
            print("✅ Redis başarıyla başlatıldı ve çalışıyor!")
            return 0
        else:
            print("⚠️ Redis başlatıldı ama henüz bağlantı kurulamadı.")
            print("   Birkaç saniye sonra tekrar deneyin.")
            return 1
    else:
        print()
        print("❌ Redis başlatılamadı.")
        print("📝 Lütfen manuel olarak başlatın:")
        if sys.platform == "win32":
            print("   wsl sudo service redis-server start")
        else:
            print("   sudo service redis-server start")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n❌ İptal edildi.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ HATA: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


