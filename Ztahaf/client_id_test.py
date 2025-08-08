#!/usr/bin/env python3
"""
Client ID Test Scripti
Farklı Client ID'ler ile Gateway bağlantısını test eder
"""

from ib_insync import *
import time

def test_client_ids():
    print("🔍 Client ID Test Scripti")
    print("=" * 40)
    
    # Test edilecek Client ID'ler
    client_ids = [1, 999, 888, 777, 666, 555, 444, 333, 222, 111]
    
    for client_id in client_ids:
        print(f"\n🔄 Client ID {client_id} test ediliyor...")
        
        try:
            ib = IB()
            print(f"   📡 {client_id} ile bağlanılıyor...")
            ib.connect('127.0.0.1', 4001, clientId=client_id, timeout=10)
            
            if ib.isConnected():
                print(f"   ✅ Client ID {client_id} başarılı!")
                
                # Hızlı test
                try:
                    account = ib.accountSummary()
                    print(f"   📊 Account bilgileri: {len(account)} öğe")
                    print(f"   🎉 Client ID {client_id} çalışıyor!")
                    
                    ib.disconnect()
                    return client_id
                    
                except Exception as e:
                    print(f"   ⚠️ Test hatası: {e}")
                    ib.disconnect()
                    
            else:
                print(f"   ❌ Client ID {client_id} başarısız")
                ib.disconnect()
                
        except Exception as e:
            print(f"   ❌ Client ID {client_id} hatası: {e}")
            try:
                ib.disconnect()
            except:
                pass
    
    print("\n❌ Hiçbir Client ID başarılı değil!")
    return None

def check_gateway_status():
    print("\n🔍 Gateway Durum Analizi:")
    print("=" * 40)
    
    # Port durumu
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(('127.0.0.1', 4001))
        sock.close()
        
        if result == 0:
            print("✅ Port 4001 açık")
        else:
            print("❌ Port 4001 kapalı")
            
    except Exception as e:
        print(f"⚠️ Port kontrol hatası: {e}")
    
    # Bağlantı sayısı
    import subprocess
    try:
        result = subprocess.run(['netstat', '-an'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        connections = [line for line in lines if ':4001' in line and 'ESTABLISHED' in line]
        print(f"📊 Aktif bağlantı sayısı: {len(connections)}")
        
    except Exception as e:
        print(f"⚠️ Bağlantı sayısı kontrol hatası: {e}")

if __name__ == "__main__":
    print("🚀 Client ID Test Scripti")
    print("=" * 40)
    
    # Gateway durumunu kontrol et
    check_gateway_status()
    
    # Client ID testi
    working_client_id = test_client_ids()
    
    if working_client_id:
        print(f"\n🎉 Başarılı! Çalışan Client ID: {working_client_id}")
        print(f"💡 Ntahaf uygulamasında bu Client ID'yi kullanın")
        
        # Ntahaf için öneri
        print(f"\n📝 Ntahaf için öneri:")
        print(f"manager.py dosyasında client_id={working_client_id} kullanın")
        
    else:
        print("\n🔧 Sorun analizi:")
        print("1. Gateway'de API ayarlarını kontrol edin")
        print("2. Gateway'i yeniden başlatın")
        print("3. Başka bir uygulama Gateway'i kullanıyor olabilir")
        print("4. Windows Firewall ayarlarını kontrol edin")
    
    print("\n" + "=" * 40)
    print("Test tamamlandı.") 