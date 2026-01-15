#!/usr/bin/env python3
"""
Quant Engine - Frontend Başlatma Scripti
Kullanım: python baslat_frontend.py
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    print("=" * 50)
    print("Quant Engine - Frontend Başlatılıyor...")
    print("=" * 50)
    print()
    
    # Script'in bulunduğu dizin
    script_dir = Path(__file__).parent.absolute()
    frontend_dir = script_dir / "frontend"
    
    print(f"Dizin: {frontend_dir}")
    print()
    
    # Node.js kontrolü
    print("Node.js kontrol ediliyor...")
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("HATA: Node.js bulunamadı!")
            print("Lütfen Node.js'i yükleyin: https://nodejs.org/")
            input("\nDevam etmek için Enter'a basın...")
            sys.exit(1)
        print(f"Node.js: {result.stdout.strip()}")
    except FileNotFoundError:
        print("HATA: Node.js bulunamadı!")
        print("Lütfen Node.js'i yükleyin: https://nodejs.org/")
        input("\nDevam etmek için Enter'a basın...")
        sys.exit(1)
    
    print()
    
    # npm kontrolü
    print("npm kontrol ediliyor...")
    try:
        result = subprocess.run(["npm", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("HATA: npm bulunamadı!")
            input("\nDevam etmek için Enter'a basın...")
            sys.exit(1)
        print(f"npm: {result.stdout.strip()}")
    except FileNotFoundError:
        print("HATA: npm bulunamadı!")
        input("\nDevam etmek için Enter'a basın...")
        sys.exit(1)
    
    print()
    
    # node_modules kontrolü
    if not (frontend_dir / "node_modules").exists():
        print("node_modules bulunamadı. Dependencies yükleniyor...")
        os.chdir(frontend_dir)
        result = subprocess.run(["npm", "install"])
        if result.returncode != 0:
            print("HATA: npm install başarısız!")
            input("\nDevam etmek için Enter'a basın...")
            sys.exit(1)
        print()
    
    # Frontend'i başlat
    print("Frontend başlatılıyor (port 3000)...")
    print("Tarayıcıda açılacak: http://localhost:3000")
    print("Durdurmak için: Ctrl+C")
    print()
    
    os.chdir(frontend_dir)
    subprocess.run(["npm", "run", "dev"])

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nFrontend durdu.")
        sys.exit(0)
    except Exception as e:
        print(f"\nHATA: {e}")
        input("\nDevam etmek için Enter'a basın...")
        sys.exit(1)








