#!/usr/bin/env python3
"""
Quant Engine - Backend ve Frontend Başlatma Scripti
Kullanım: python baslat.py
"""

import subprocess
import sys
import os
import time
from pathlib import Path

def main():
    print("=" * 50)
    print("Quant Engine - Her İkisini Başlatıyor")
    print("=" * 50)
    print()
    
    # Script'in bulunduğu dizin
    script_dir = Path(__file__).parent.absolute()
    frontend_dir = script_dir / "frontend"
    
    print(f"Backend dizini: {script_dir}")
    print(f"Frontend dizini: {frontend_dir}")
    print()
    
    # Backend'i başlat (yeni pencere)
    print("Backend başlatılıyor (yeni pencere)...")
    
    if sys.platform == "win32":
        # Windows için - os.system ile çalıştır (daha güvenilir)
        script_dir_str = str(script_dir)
        # start komutu ile yeni cmd penceresi aç
        # Windows'ta yol tırnak içine alınmalı
        # Windows'ta iç tırnakları çift tırnak yap
        backend_cmd = f'start "Quant Engine - Backend" cmd /k "cd /d ""{script_dir_str}"" && python main.py api"'
        os.system(backend_cmd)
    else:
        # Linux/Mac için
        subprocess.Popen(
            ["gnome-terminal", "--", "bash", "-c", f"cd '{script_dir}' && python main.py api; exec bash"],
            start_new_session=True
        )
    
    # 2 saniye bekle
    time.sleep(2)
    
    # Frontend'i başlat (yeni pencere)
    print("Frontend başlatılıyor (yeni pencere)...")
    
    if sys.platform == "win32":
        # Windows için - os.system ile çalıştır (daha güvenilir)
        frontend_dir_str = str(frontend_dir)
        # start komutu ile yeni cmd penceresi aç
        # Windows'ta yol tırnak içine alınmalı
        # Windows'ta iç tırnakları çift tırnak yap
        frontend_cmd = f'start "Quant Engine - Frontend" cmd /k "cd /d ""{frontend_dir_str}"" && npm run dev"'
        os.system(frontend_cmd)
    else:
        # Linux/Mac için
        subprocess.Popen(
            ["gnome-terminal", "--", "bash", "-c", f"cd '{frontend_dir}' && npm run dev; exec bash"],
            start_new_session=True
        )
    
    print()
    print("=" * 50)
    print("Her iki servis de başlatıldı!")
    print("Backend: http://localhost:8000")
    print("Frontend: http://localhost:3000")
    print("=" * 50)
    print()
    print("Bu pencereyi kapatabilirsiniz.")
    print("Servisleri durdurmak için ilgili pencerelerde Ctrl+C yapın.")
    print()
    
    # 3 saniye bekle ve çık
    time.sleep(3)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nİptal edildi.")
        sys.exit(0)
    except Exception as e:
        print(f"\nHATA: {e}")
        input("\nDevam etmek için Enter'a basın...")
        sys.exit(1)

