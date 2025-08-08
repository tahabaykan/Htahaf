#!/usr/bin/env python3
"""
Debug PrevClose - Hammer Pro'dan gelen prevClose değerlerini detaylı kontrol et
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'janallapp'))

from hammer_client import HammerClient
import time
import json

def debug_prevclose():
    print("🔍 PREVCLOSE DEBUG")
    print("=" * 50)
    
    # Hammer client oluştur
    hammer = HammerClient(
        host='127.0.0.1',
        port=16400,
        password='Nl201090.'
    )
    
    # Bağlan
    print("🔗 Hammer Pro'ya bağlanılıyor...")
    if not hammer.connect():
        print("❌ Bağlantı başarısız!")
        return
    
    # Test ETF'leri
    test_etfs = ['SPY', 'TLT', 'IEF', 'PFF']
    
    print("\n📸 Snapshot verilerini çekiliyor...")
    
    # Her ETF için snapshot iste
    for etf in test_etfs:
        print(f"📸 {etf} snapshot isteniyor...")
        hammer.get_symbol_snapshot(etf)
        time.sleep(1)  # Daha uzun bekle
    
    print("\n⏱️ Veriler gelsin diye 5 saniye bekleniyor...")
    time.sleep(5)
    
    print("\n🔍 HAMMER PRO MARKET DATA DEBUG:")
    print("-" * 80)
    
    # Her ETF için detaylı market data kontrol et
    for etf in test_etfs:
        print(f"\n📊 {etf} MARKET DATA:")
        print("-" * 40)
        
        market_data = hammer.get_market_data(etf)
        if market_data:
            print(f"Raw market_data: {json.dumps(market_data, indent=2)}")
            
            last = market_data.get('last', 0)
            prev_close = market_data.get('prevClose', 0)
            change = market_data.get('change', 0)
            
            print(f"Last: {last}")
            print(f"PrevClose: {prev_close}")
            print(f"API Change: {change}")
            
            if last > 0 and prev_close > 0:
                calc_change = last - prev_close
                calc_change_pct = (calc_change / prev_close) * 100
                print(f"Calculated Change: {calc_change}")
                print(f"Calculated Change %: {calc_change_pct:.2f}%")
            else:
                print("❌ Last veya PrevClose eksik!")
        else:
            print("❌ Market data yok!")
    
    print("\n🎯 PROBLEM ANALİZİ:")
    print("-" * 80)
    print("1. PrevClose değerleri 0 ise: Hammer Pro API'dan gelmiyor")
    print("2. Last değerleri 0 ise: Market data alınamıyor")
    print("3. Change değerleri 0 ise: Hesaplama yanlış")
    print("4. API'dan gelen change değeri varsa onu kullan")

if __name__ == "__main__":
    debug_prevclose()
