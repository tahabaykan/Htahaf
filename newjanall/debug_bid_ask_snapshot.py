#!/usr/bin/env python3
"""
Bid/Ask N/A sorunu - Snapshot ile çözüm
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'janallapp'))

from hammer_client import HammerClient
import time

def debug_bid_ask_snapshot():
    """Snapshot ile Bid/Ask data çek"""
    print("=== Bid/Ask Snapshot Debug ===")
    
    # Hammer client oluştur
    hammer = HammerClient(password="123456")
    
    # Bağlan
    if not hammer.connect():
        print("❌ Hammer Pro bağlantısı başarısız!")
        return
    
    print("✅ Hammer Pro bağlandı")
    
    # Test sembolleri
    test_symbols = ["NRUC", "AIZN", "WFC PRY", "PSA PRH"]
    
    for symbol in test_symbols:
        print(f"\n--- {symbol} ---")
        
        # Önce snapshot çek
        print(f"📸 {symbol} snapshot isteniyor...")
        hammer.get_symbol_snapshot(symbol)
        
        # 1 saniye bekle
        time.sleep(1)
        
        # Market data al
        market_data = hammer.get_market_data(symbol)
        if market_data:
            print(f"📊 {symbol} Market Data (Snapshot):")
            print(f"  Raw data: {market_data}")
            print(f"  Bid: {market_data.get('bid', 'N/A')}")
            print(f"  Ask: {market_data.get('ask', 'N/A')}")
            print(f"  Last: {market_data.get('last', 'N/A')}")
            print(f"  Volume: {market_data.get('volume', 'N/A')}")
            print(f"  PrevClose: {market_data.get('prevClose', 'N/A')}")
        else:
            print(f"❌ {symbol} için market data yok!")
        
        # Sonra subscribe ol
        hammer.subscribe_symbol(symbol)
        print(f"✅ {symbol} subscribe edildi")
        
        # 2 saniye bekle
        time.sleep(2)
        
        # Tekrar market data al
        market_data = hammer.get_market_data(symbol)
        if market_data:
            print(f"📊 {symbol} Market Data (Streaming):")
            print(f"  Raw data: {market_data}")
            print(f"  Bid: {market_data.get('bid', 'N/A')}")
            print(f"  Ask: {market_data.get('ask', 'N/A')}")
            print(f"  Last: {market_data.get('last', 'N/A')}")
            print(f"  Volume: {market_data.get('volume', 'N/A')}")
        else:
            print(f"❌ {symbol} için streaming data yok!")
    
    hammer.disconnect()

if __name__ == "__main__":
    debug_bid_ask_snapshot()
