#!/usr/bin/env python3
"""
Debug ETF N/A - ETF panelindeki N/A problemini detaylı debug et
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'janallresapp'))

from hammer_client import HammerClient
import time
import json

def debug_etf_na():
    print("🔍 ETF N/A DEBUG")
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
        time.sleep(1)
    
    print("\n⏱️ Veriler gelsin diye 5 saniye bekleniyor...")
    time.sleep(5)
    
    print("\n🔍 ETF PANEL DEBUG:")
    print("-" * 80)
    
    # Her ETF için detaylı kontrol
    for etf in test_etfs:
        print(f"\n📊 {etf} DETAYLI KONTROL:")
        print("-" * 40)
        
        market_data = hammer.get_market_data(etf)
        if market_data:
            print(f"Raw market_data: {json.dumps(market_data, indent=2)}")
            
            last = market_data.get('last', 0)
            prev_close = market_data.get('prevClose', 0)
            api_change = market_data.get('change', None)
            
            print(f"Last: {last}")
            print(f"PrevClose: {prev_close}")
            print(f"API Change: {api_change}")
            
            # ETF Panel hesaplamasını simüle et
            change = 0
            change_pct = 0
            
            if api_change is not None:
                print("✅ API'dan gelen change kullanılıyor")
                change = api_change
                if prev_close > 0:
                    change_pct = (change / prev_close) * 100
            elif last > 0 and prev_close > 0:
                print("✅ Manuel hesaplama yapılıyor")
                change = last - prev_close
                change_pct = (change / prev_close) * 100
            else:
                print("❌ Hesaplama yapılamıyor!")
                if last == 0:
                    print("  - Last = 0")
                if prev_close == 0:
                    print("  - PrevClose = 0")
                if api_change is None:
                    print("  - API Change = None")
            
            print(f"Final Change: {change}")
            print(f"Final Change %: {change_pct:.2f}%")
            
            # Format kontrolü
            change_str = f"{change:+.2f}" if change != 0 else "N/A"
            change_pct_str = f"{change_pct:+.2f}%" if change_pct != 0 else "N/A"
            
            print(f"Change String: '{change_str}'")
            print(f"Change % String: '{change_pct_str}'")
            
        else:
            print("❌ Market data yok!")
    
    print("\n🎯 PROBLEM ANALİZİ:")
    print("-" * 80)
    print("1. PrevClose = 0 ise: Snapshot çekilmedi")
    print("2. Last = 0 ise: Market data alınamadı")
    print("3. API Change = None ise: API'dan gelmiyor")
    print("4. Change = 0 ise: Hesaplama yanlış")
    print("5. Format = N/A ise: 0 değeri N/A'ya çevriliyor")

if __name__ == "__main__":
    debug_etf_na()
