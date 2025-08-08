#!/usr/bin/env python3
"""
IBKR Bağlantı Test Scripti
Bu script IBKR TWS/Gateway bağlantısını test eder
"""

import sys
import time
from ib_insync import *

def test_ibkr_connection():
    """IBKR bağlantısını test et"""
    print("🔍 IBKR Bağlantı Testi Başlatılıyor...")
    print("=" * 50)
    
    # Test edilecek portlar
    ports_to_test = [
        (4001, "TWS Paper Trading"),
        (4002, "TWS Live Trading"), 
        (7496, "Gateway Paper Trading"),
        (7497, "Gateway Live Trading")
    ]
    
    for port, description in ports_to_test:
        print(f"\n🔄 {description} (Port {port}) test ediliyor...")
        
        try:
            # Yeni IB instance oluştur
            ib = IB()
            
            # Bağlantı dene
            print(f"   📡 {port} portuna bağlanılıyor...")
            ib.connect('127.0.0.1', port, clientId=999, timeout=10)
            
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
    print("\n💡 Kontrol Edilecekler:")
    print("   1. TWS veya Gateway açık mı?")
    print("   2. TWS'de File > Global Configuration > API > Settings")
    print("   3. 'Enable ActiveX and Socket Clients' işaretli mi?")
    print("   4. Socket port ayarları doğru mu?")
    print("   5. Windows Firewall IBKR'yi engelliyor mu?")
    print("   6. Başka bir uygulama aynı portu kullanıyor mu?")
    
    return None, None

def check_tws_settings():
    """TWS ayarlarını kontrol et"""
    print("\n📋 TWS Ayarları Kontrol Listesi:")
    print("=" * 50)
    print("1. TWS'yi açın")
    print("2. File > Global Configuration'a gidin")
    print("3. API > Settings sekmesine gidin")
    print("4. Şu ayarları kontrol edin:")
    print("   ✅ Enable ActiveX and Socket Clients")
    print("   ✅ Socket port: 4001 (Paper) veya 4002 (Live)")
    print("   ✅ Allow connections from localhost")
    print("   ✅ Read-Only API: İşaretli değil")
    print("5. Apply > OK")
    print("6. TWS'yi yeniden başlatın")

if __name__ == "__main__":
    print("🚀 IBKR Bağlantı Test Scripti")
    print("=" * 50)
    
    # Bağlantı testi
    working_port, working_desc = test_ibkr_connection()
    
    if working_port:
        print(f"\n🎉 Başarılı! Çalışan port: {working_port} ({working_desc})")
        print(f"💡 Ntahaf uygulamasında bu portu kullanın")
    else:
        print("\n🔧 TWS ayarlarını kontrol edin:")
        check_tws_settings()
    
    print("\n" + "=" * 50)
    print("Test tamamlandı.") 