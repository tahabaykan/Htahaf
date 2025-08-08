#!/usr/bin/env python3
"""
Hızlı Gateway Test Scripti
Gateway ayarlarını değiştirdikten sonra test için
"""

from ib_insync import *

def quick_test():
    print("🚀 Hızlı Gateway Test")
    print("=" * 30)
    
    try:
        ib = IB()
        print("📡 Gateway'e bağlanılıyor...")
        ib.connect('127.0.0.1', 4001, clientId=999, timeout=20)
        
        if ib.isConnected():
            print("✅ Bağlantı başarılı!")
            
            # Hızlı test
            try:
                account = ib.accountSummary()
                print(f"✅ Account bilgileri: {len(account)} öğe")
                
                positions = ib.positions()
                print(f"✅ Pozisyonlar: {len(positions)} pozisyon")
                
                print("🎉 Gateway çalışıyor!")
                return True
                
            except Exception as e:
                print(f"⚠️ Test hatası: {e}")
                return False
                
        else:
            print("❌ Bağlantı başarısız")
            return False
            
    except Exception as e:
        print(f"❌ Bağlantı hatası: {e}")
        return False
    finally:
        try:
            ib.disconnect()
        except:
            pass

if __name__ == "__main__":
    success = quick_test()
    
    if success:
        print("\n🎉 Gateway hazır! Ntahaf uygulamasını çalıştırabilirsiniz.")
    else:
        print("\n🔧 Gateway ayarlarını kontrol edin:")
        print("1. Gateway'de Configure > Settings > API")
        print("2. 'Enable ActiveX and Socket Clients' işaretli mi?")
        print("3. Socket port 4001 mi?")
        print("4. 'Allow connections from localhost' işaretli mi?")
        print("5. Gateway'i yeniden başlatın") 