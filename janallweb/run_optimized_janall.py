#!/usr/bin/env python3
"""
Optimized JanAll Application Launcher
=====================================

Bu script optimize edilmiş JanAll uygulamasını başlatır:
- ETF'ler: 3 saniyede bir snapshot (L1 yok)
- Preferred Stocks: L1 subscription ile gerçek zamanlı bid/ask/last/volume
- Symbol conversion: VNO PRN → VNO-N
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# JanAll modüllerini import et
from janallapp.main_window import MainWindow
from janallapp.hammer_client import HammerClient

def main():
    print("🚀 JanAll - Optimized Stock Tracker")
    print("=" * 40)
    print("💡 Features:")
    print("   • ETF'ler: 3s snapshot interval (bid/ask/volume yok)")
    print("   • Preferred Stocks: Real-time L1 data (bid/ask/last/volume)")
    print("   • Symbol conversion: VNO PRN → VNO-N")
    print("   • Benchmark calculations with ETF changes")
    print("   • Score calculations")
    print()
    
    try:
        # Hammer Pro API şifresi
        api_password = input("🔑 Hammer Pro API şifresi: ").strip()
        if not api_password:
            print("❌ API şifresi gerekli!")
            return
        
        print("\n📱 JanAll uygulaması başlatılıyor...")
        
        # Main window oluştur ve Hammer client'ı configure et
        app = MainWindow()
        
        # Hammer client şifresini ayarla
        app.hammer.password = api_password
        
        print("✅ Uygulama hazır!")
        print("\n💡 Kullanım:")
        print("   1. 'Hammer Pro'ya Bağlan' butonuna tıklayın")
        print("   2. 'Live Data Başlat' butonuna tıklayın")
        print("   3. ETF'ler 3 saniyede bir güncellenecek")
        print("   4. Preferred stocks gerçek zamanlı güncellenecek")
        print()
        
        # Uygulamayı başlat
        app.mainloop()
        
    except KeyboardInterrupt:
        print("\n⏹️ Uygulama kullanıcı tarafından durduruldu")
    except Exception as e:
        print(f"\n❌ Uygulama hatası: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()