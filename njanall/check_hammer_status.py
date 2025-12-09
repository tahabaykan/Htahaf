#!/usr/bin/env python3
"""
Hammer Pro durum kontrolü
"""

import socket
import time

def check_hammer_status():
    """Hammer Pro'nun çalışıp çalışmadığını kontrol et"""
    print("=== Hammer Pro Durum Kontrolü ===")
    
    # Port kontrolü
    host = "127.0.0.1"
    port = 16400
    
    print(f"🔍 {host}:{port} kontrol ediliyor...")
    
    try:
        # Socket bağlantısı dene
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print("✅ Hammer Pro portu açık!")
            print("💡 Hammer Pro çalışıyor olmalı")
        else:
            print("❌ Hammer Pro portu kapalı!")
            print("💡 Hammer Pro çalışmıyor - başlatman gerekiyor!")
            return False
            
    except Exception as e:
        print(f"❌ Bağlantı hatası: {e}")
        return False
    
    # Şifre kontrolü
    print("\n🔐 Şifre kontrolü:")
    print("💡 Varsayılan şifre: 123456")
    print("💡 Hammer Pro'da şifre ayarlarını kontrol et!")
    
    return True

if __name__ == "__main__":
    check_hammer_status()
