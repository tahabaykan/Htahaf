#!/usr/bin/env python3
"""
Quant Engine - Backend Başlatma Scripti
Kullanım: python baslat_backend.py
"""

import subprocess
import sys
from pathlib import Path

def main():
    print("=" * 50)
    print("Quant Engine - Backend Başlatılıyor...")
    print("=" * 50)
    print()
    
    # Script'in bulunduğu dizin
    script_dir = Path(__file__).parent.absolute()
    
    print(f"Dizin: {script_dir}")
    print()
    print("Backend başlatılıyor (port 8000)...")
    print("Durdurmak için: Ctrl+C")
    print()
    
    # Backend'i başlat
    os.chdir(script_dir)
    subprocess.run([sys.executable, "main.py", "api"])

if __name__ == "__main__":
    import os
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nBackend durdu.")
        sys.exit(0)
    except Exception as e:
        print(f"\nHATA: {e}")
        input("\nDevam etmek için Enter'a basın...")
        sys.exit(1)








