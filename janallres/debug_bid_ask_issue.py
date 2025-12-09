#!/usr/bin/env python3
"""
Bid/Ask Aynı Değer Sorunu Debug Script
=====================================

Bu script bid/ask değerlerinin neden aynı çıktığını debug eder.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from janallresapp.hammer_client import HammerClient
import time

def debug_bid_ask_issue():
    print("🐛 Bid/Ask Aynı Değer Sorunu Debug")
    print("=" * 40)
    
    # Hammer client oluştur
    hammer = HammerClient(
        host='127.0.0.1',
        port=16400,
        password='your_password_here'  # Gerçek şifrenizi buraya yazın
    )
    
    # Bağlan
    print("\n📡 Hammer Pro'ya bağlanılıyor...")
    if not hammer.connect():
        print("❌ Bağlantı başarısız!")
        return
    
    print("✅ Bağlantı başarılı!")
    
    # Test preferred stocks
    test_stocks = ["VNO PRN", "AHL PRE"]
    
    print(f"\n🔄 L1 Streaming başlatılıyor...")
    for stock in test_stocks:
        print(f"[TEST] 🔄 {stock} L1 subscribe...")
        result = hammer.subscribe_symbol(stock)
        if result:
            print(f"[TEST] ✅ {stock} L1 subscription başarılı")
        else:
            print(f"[TEST] ❌ {stock} L1 subscription başarısız")
    
    print(f"\n⏳ 15 saniye L1 verilerini topluyoruz (debug mesajlarını izleyin)...")
    
    # 15 saniye boyunca her 3 saniyede bir kontrol et
    for i in range(5):
        time.sleep(3)
        print(f"\n📊 === {i+1}. Kontrol (3s sonra) ===")
        
        for stock in test_stocks:
            market_data = hammer.get_market_data(stock)
            if market_data:
                bid = market_data.get('bid', 0)
                ask = market_data.get('ask', 0)
                last = market_data.get('last', 0)
                is_live = market_data.get('is_live', False)
                spread = ask - bid if ask > 0 and bid > 0 else 0
                
                print(f"[TEST] 📈 {stock:8s}: Bid=${bid:6.2f}, Ask=${ask:6.2f}, Last=${last:6.2f}, Spread=${spread:.4f}, Live={is_live}")
                
                # PROBLEM TESPİTİ
                if bid > 0 and ask > 0 and abs(spread) < 0.0001:
                    print(f"[TEST] ⚠️  {stock}: BID ve ASK AYNI! (spread ≈ 0)")
                    print(f"[TEST] 🔍 Raw data: {market_data}")
                elif spread > 0:
                    print(f"[TEST] ✅ {stock}: Normal spread")
            else:
                print(f"[TEST] ❌ {stock}: Market data yok")
    
    print(f"\n🎯 Problem Analizi")
    print("-" * 30)
    
    # Final analiz
    for stock in test_stocks:
        market_data = hammer.get_market_data(stock)
        if market_data:
            bid = market_data.get('bid', 0)
            ask = market_data.get('ask', 0)
            
            if bid > 0 and ask > 0:
                if abs(bid - ask) < 0.0001:
                    print(f"[PROBLEM] ❌ {stock}: Bid={bid} Ask={ask} (AYNI DEĞER!)")
                    print(f"[PROBLEM] 🔍 Olası nedenler:")
                    print(f"   1. L1Update'de bid/ask aynı geliyor")
                    print(f"   2. safe_float() parsing hatası")
                    print(f"   3. Hammer Pro API'sinden aynı değer geliyor")
                else:
                    print(f"[OK] ✅ {stock}: Bid={bid} Ask={ask} Spread={ask-bid:.4f}")
            else:
                print(f"[INFO] ℹ️ {stock}: Bid/Ask verisi eksik")
    
    print(f"\n📝 Çözüm Önerileri:")
    print("1. Debug mesajlarında RAW L1Update verilerini kontrol edin")
    print("2. Hammer Pro'da aynı symbollerin bid/ask'ını manuel kontrol edin")
    print("3. API streamer ayarlarını kontrol edin")
    print("4. Symbol conversion'ı kontrol edin (VNO PRN → VNO-N)")
    
    # Bağlantıyı kapat
    hammer.disconnect()

if __name__ == "__main__":
    debug_bid_ask_issue()