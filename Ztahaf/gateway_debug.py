#!/usr/bin/env python3
"""
Gateway Debug Scripti
Gateway bağlantı sorununu detaylı analiz eder
"""

import socket
import subprocess
import time
from ib_insync import *

def check_port_status():
    print("🔍 Port 4001 Durum Analizi:")
    print("=" * 40)
    
    try:
        # TCP bağlantısı test et
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('127.0.0.1', 4001))
        sock.close()
        
        if result == 0:
            print("✅ Port 4001 açık ve erişilebilir")
            return True
        else:
            print(f"❌ Port 4001 kapalı (hata kodu: {result})")
            return False
            
    except Exception as e:
        print(f"⚠️ Port kontrol hatası: {e}")
        return False

def check_netstat():
    print("\n📊 Netstat Analizi:")
    print("=" * 40)
    
    try:
        result = subprocess.run(['netstat', '-an'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        
        # Port 4001 bağlantılarını bul
        port_4001_lines = [line for line in lines if ':4001' in line]
        
        print(f"📈 Port 4001 bağlantı sayısı: {len(port_4001_lines)}")
        
        for line in port_4001_lines:
            print(f"   {line.strip()}")
            
        # ESTABLISHED bağlantıları say
        established = [line for line in port_4001_lines if 'ESTABLISHED' in line]
        print(f"🔗 Aktif bağlantı sayısı: {len(established)}")
        
        return len(established)
        
    except Exception as e:
        print(f"⚠️ Netstat hatası: {e}")
        return 0

def test_simple_connection():
    print("\n🔌 Basit Bağlantı Testi:")
    print("=" * 40)
    
    try:
        # En basit bağlantı testi
        ib = IB()
        print("📡 Basit bağlantı deneniyor...")
        
        # Çok kısa timeout ile test
        ib.connect('127.0.0.1', 4001, clientId=12345, timeout=5)
        
        if ib.isConnected():
            print("✅ Basit bağlantı başarılı!")
            ib.disconnect()
            return True
        else:
            print("❌ Basit bağlantı başarısız")
            ib.disconnect()
            return False
            
    except Exception as e:
        print(f"❌ Basit bağlantı hatası: {e}")
        return False

def check_gateway_process():
    print("\n🔍 Gateway Process Kontrolü:")
    print("=" * 40)
    
    try:
        result = subprocess.run(['tasklist'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        
        gateway_processes = [line for line in lines if 'ibgateway' in line.lower()]
        
        if gateway_processes:
            print("✅ IB Gateway çalışıyor:")
            for process in gateway_processes:
                print(f"   {process.strip()}")
        else:
            print("❌ IB Gateway çalışmıyor!")
            
    except Exception as e:
        print(f"⚠️ Process kontrol hatası: {e}")

def main():
    print("🚀 Gateway Debug Scripti")
    print("=" * 50)
    
    # 1. Port durumu
    port_ok = check_port_status()
    
    # 2. Netstat analizi
    active_connections = check_netstat()
    
    # 3. Gateway process kontrolü
    check_gateway_process()
    
    # 4. Basit bağlantı testi
    if port_ok:
        connection_ok = test_simple_connection()
    else:
        connection_ok = False
    
    # Sonuç analizi
    print("\n📋 Sonuç Analizi:")
    print("=" * 40)
    
    if port_ok and connection_ok:
        print("✅ Gateway normal çalışıyor")
        print("💡 Sorun başka bir yerde olabilir")
    elif port_ok and not connection_ok:
        print("⚠️ Port açık ama bağlantı başarısız")
        print("🔧 Gateway API ayarlarını kontrol edin")
    elif not port_ok:
        print("❌ Port kapalı")
        print("🔧 Gateway'i başlatın")
    
    if active_connections > 0:
        print(f"⚠️ {active_connections} aktif bağlantı var")
        print("💡 Başka bir uygulama Gateway'i kullanıyor olabilir")

if __name__ == "__main__":
    main() 