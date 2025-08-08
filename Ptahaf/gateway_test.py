#!/usr/bin/env python3
"""
IB Gateway Bağlantı Test Scripti
Bu script IB Gateway bağlantısını test eder
"""

import sys
import time
from ib_insync import *

def test_gateway_connection():
    """IB Gateway bağlantısını test et"""
    print("🔍 IB Gateway Bağlantı Testi Başlatılıyor...")
    print("=" * 50)
    
    # Gateway için test edilecek portlar
    ports_to_test = [
        (4001, "Gateway Paper Trading"),
        (4002, "Gateway Live Trading")
    ]
    
    for port, description in ports_to_test:
        print(f"\n🔄 {description} (Port {port}) test ediliyor...")
        
        try:
            # Yeni IB instance oluştur
            ib = IB()
            
            # Bağlantı dene
            print(f"   📡 {port} portuna bağlanılıyor...")
            ib.connect('127.0.0.1', port, clientId=999, timeout=15)
            
            if ib.isConnected():
                print(f"   ✅ {description} başarılı!")
                
                # Basit test istekleri
                try:
                    # Account summary test
                    print("   📊 Account summary test ediliyor...")
                    account_info = ib.accountSummary()
                    print(f"   ✅ Account bilgileri alındı: {len(account_info)} öğe")
                    
                    # Positions test
                    print("   📈 Positions test ediliyor...")
                    positions = ib.positions()
                    print(f"   ✅ Pozisyonlar alındı: {len(positions)} pozisyon")
                    
                    # Open orders test
                    print("   📋 Open orders test ediliyor...")
                    open_orders = ib.reqAllOpenOrders()
                    print(f"   ✅ Açık emirler alındı: {len(open_orders)} emir")
                    
                except Exception as e:
                    print(f"   ⚠️ Test istekleri hatası: {e}")
                
                # Bağlantıyı kapat
                ib.disconnect()
                print(f"   🔌 {description} bağlantısı kapatıldı")
                
                return port, description
                
            else:
                print(f"   ❌ {description} başarısız - isConnected() False")
                ib.disconnect()
                
        except Exception as e:
            print(f"   ❌ {description} hatası: {e}")
            try:
                ib.disconnect()
            except:
                pass
    
    print("\n❌ Hiçbir port başarılı değil!")
    print("\n💡 Gateway Kontrol Edilecekler:")
    print("   1. IB Gateway açık mı?")
    print("   2. Gateway'de Configure > Settings > API")
    print("   3. 'Enable ActiveX and Socket Clients' işaretli mi?")
    print("   4. Socket port 4001 mi?")
    print("   5. 'Allow connections from localhost' işaretli mi?")
    print("   6. 'Read-Only API' işaretli değil mi?")
    print("   7. Windows Firewall Gateway'i engelliyor mu?")
    print("   8. Başka bir uygulama aynı portu kullanıyor mu?")
    
    return None, None

def check_gateway_settings():
    """Gateway ayarlarını kontrol et"""
    print("\n📋 Gateway Ayarları Kontrol Listesi:")
    print("=" * 50)
    print("1. IB Gateway'i açın")
    print("2. Configure > Settings'a gidin")
    print("3. API sekmesine gidin")
    print("4. Şu ayarları kontrol edin:")
    print("   ✅ Enable ActiveX and Socket Clients")
    print("   ✅ Socket port: 4001 (Paper) veya 4002 (Live)")
    print("   ✅ Allow connections from localhost")
    print("   ❌ Read-Only API: İşaretli değil")
    print("   ✅ Download open orders on connection")
    print("   ✅ Include FX positions")
    print("5. OK")
    print("6. Gateway'i yeniden başlatın")

def check_gateway_status():
    """Gateway durumunu kontrol et"""
    print("\n🔍 Gateway Durum Kontrolü:")
    print("=" * 50)
    
    # Port 4001'in açık olup olmadığını kontrol et
    import socket
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('127.0.0.1', 4001))
        sock.close()
        
        if result == 0:
            print("✅ Port 4001 açık - Gateway çalışıyor olabilir")
        else:
            print("❌ Port 4001 kapalı - Gateway açık değil")
            
    except Exception as e:
        print(f"⚠️ Port kontrol hatası: {e}")

if __name__ == "__main__":
    print("🚀 IB Gateway Bağlantı Test Scripti")
    print("=" * 50)
    
    # Gateway durumunu kontrol et
    check_gateway_status()
    
    # Bağlantı testi
    working_port, working_desc = test_gateway_connection()
    
    if working_port:
        print(f"\n🎉 Başarılı! Çalışan port: {working_port} ({working_desc})")
        print(f"💡 Ptahaf uygulamasında bu portu kullanın")
    else:
        print("\n🔧 Gateway ayarlarını kontrol edin:")
        check_gateway_settings()
    
    print("\n" + "=" * 50)
    print("Test tamamlandı.") 
