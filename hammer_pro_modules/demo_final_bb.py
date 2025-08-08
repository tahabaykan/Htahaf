"""
FINAL BB Score Calculation Demo
Örnek market data ile FINAL BB skor hesaplama gösterimi
"""

import pandas as pd
from market_data_manager import HammerProMarketDataManager
from connection import HammerProConnection
from config import HammerProConfig

def demo_final_bb_calculation():
    """FINAL BB skor hesaplama demo"""
    
    print("🎯 FINAL BB Skor Hesaplama Demo")
    print("=" * 50)
    
    # Örnek market data
    example_market_data = {
        "AAPL": {
            "bid": 150.25,
            "ask": 150.35,
            "last": 150.30,
            "prevClose": 149.80,
            "volume": 2500000
        },
        "MSFT": {
            "bid": 320.10,
            "ask": 320.25,
            "last": 320.15,
            "prevClose": 319.50,
            "volume": 1800000
        },
        "GOOGL": {
            "bid": 2750.00,
            "ask": 2750.50,
            "last": 2750.25,
            "prevClose": 2745.00,
            "volume": 950000
        }
    }
    
    # Örnek CSV data
    example_csv_data = pd.DataFrame({
        "PREF IBKR": ["AAPL", "MSFT", "GOOGL"],
        "FINAL_THG": [85.5, 92.3, 78.9],
        "Company": ["Apple Inc", "Microsoft Corp", "Alphabet Inc"]
    })
    
    # Market data manager oluştur (bağlantı olmadan)
    class MockConnection:
        def __init__(self):
            pass
        
        async def send_message(self, msg):
            pass
        
        async def _wait_for_response(self, req_id):
            return {"success": "OK", "result": {}}
    
    connection = MockConnection()
    market_manager = HammerProMarketDataManager(connection)
    
    # Market data'yı manuel olarak set et
    market_manager.symbol_data = example_market_data
    
    print("\n📊 Örnek Market Data:")
    print("-" * 30)
    for symbol, data in example_market_data.items():
        print(f"{symbol}:")
        print(f"  Bid: ${data['bid']:.2f}")
        print(f"  Ask: ${data['ask']:.2f}")
        print(f"  Last: ${data['last']:.2f}")
        print(f"  Prev Close: ${data['prevClose']:.2f}")
        print(f"  Volume: {data['volume']:,}")
        spread = data['ask'] - data['bid']
        print(f"  Spread: ${spread:.2f}")
        print()
    
    print("\n🔢 FINAL BB Hesaplama Adımları:")
    print("-" * 40)
    
    for symbol in example_market_data.keys():
        print(f"\n📈 {symbol} için hesaplama:")
        
        # CSV'den FINAL_THG al
        final_thg = example_csv_data[
            example_csv_data["PREF IBKR"] == symbol
        ]["FINAL_THG"].iloc[0]
        
        print(f"FINAL_THG: {final_thg}")
        
        # Market data al
        market_data = example_market_data[symbol]
        bid = market_data["bid"]
        ask = market_data["ask"]
        last = market_data["last"]
        prev_close = market_data["prevClose"]
        spread = ask - bid
        
        print(f"Bid: ${bid:.2f}")
        print(f"Ask: ${ask:.2f}")
        print(f"Last: ${last:.2f}")
        print(f"Prev Close: ${prev_close:.2f}")
        print(f"Spread: ${spread:.2f}")
        
        # Benchmark hesapla
        benchmark = market_manager.calculate_benchmark('T')
        print(f"Benchmark (T): {benchmark}")
        
        # Bid Buy Ucuzluk hesapla
        pf_bid_buy = bid + spread * 0.15
        pf_bid_buy_chg = pf_bid_buy - prev_close
        bid_buy_ucuzluk = pf_bid_buy_chg - benchmark
        
        print(f"\nBid Buy Ucuzluk hesaplama:")
        print(f"  pf_bid_buy = {bid:.2f} + {spread:.2f} × 0.15 = {pf_bid_buy:.2f}")
        print(f"  pf_bid_buy_chg = {pf_bid_buy:.2f} - {prev_close:.2f} = {pf_bid_buy_chg:.2f}")
        print(f"  bid_buy_ucuzluk = {pf_bid_buy_chg:.2f} - {benchmark} = {bid_buy_ucuzluk:.2f}")
        
        # FINAL BB hesapla
        final_bb = final_thg - 400 * bid_buy_ucuzluk
        print(f"  FINAL_BB = {final_thg} - 400 × {bid_buy_ucuzluk:.2f} = {final_bb:.2f}")
        
        # Diğer skorları da hesapla
        pf_front_buy = last + 0.01
        pf_front_buy_chg = pf_front_buy - prev_close
        front_buy_ucuzluk = pf_front_buy_chg - benchmark
        final_fb = final_thg - 400 * front_buy_ucuzluk
        
        pf_ask_buy = ask + 0.01
        pf_ask_buy_chg = pf_ask_buy - prev_close
        ask_buy_ucuzluk = pf_ask_buy_chg - benchmark
        final_ab = final_thg - 400 * ask_buy_ucuzluk
        
        pf_ask_sell = ask - spread * 0.15
        pf_ask_sell_chg = pf_ask_sell - prev_close
        ask_sell_pahali = pf_ask_sell_chg - benchmark
        final_as = final_thg - 400 * ask_sell_pahali
        
        pf_front_sell = last - 0.01
        pf_front_sell_chg = pf_front_sell - prev_close
        front_sell_pahali = pf_front_sell_chg - benchmark
        final_fs = final_thg - 400 * front_sell_pahali
        
        pf_bid_sell = bid - 0.01
        pf_bid_sell_chg = pf_bid_sell - prev_close
        bid_sell_pahali = pf_bid_sell_chg - benchmark
        final_bs = final_thg - 400 * bid_sell_pahali
        
        print(f"\n📊 {symbol} FINAL Skorları:")
        print(f"  FINAL_BB: {final_bb:.2f}")
        print(f"  FINAL_FB: {final_fb:.2f}")
        print(f"  FINAL_AB: {final_ab:.2f}")
        print(f"  FINAL_AS: {final_as:.2f}")
        print(f"  FINAL_FS: {final_fs:.2f}")
        print(f"  FINAL_BS: {final_bs:.2f}")
        
        print("-" * 50)
    
    # Batch hesaplama demo
    print("\n🔄 Batch Hesaplama Demo:")
    print("-" * 30)
    
    scores = market_manager.calculate_final_bb_scores_batch(example_csv_data)
    
    print("Toplu hesaplama sonuçları:")
    for symbol, score_data in scores.items():
        print(f"{symbol}:")
        print(f"  BB: {score_data['final_bb']:.2f}")
        print(f"  FB: {score_data['final_fb']:.2f}")
        print(f"  AB: {score_data['final_ab']:.2f}")
        print(f"  AS: {score_data['final_as']:.2f}")
        print(f"  FS: {score_data['final_fs']:.2f}")
        print(f"  BS: {score_data['final_bs']:.2f}")
        print(f"  Market Data: {'✓' if score_data['market_data_available'] else '✗'}")
        print()
    
    print("\n✅ Demo tamamlandı!")
    print("\n💡 Önemli Notlar:")
    print("- Market data mevcut olduğunda gerçek zamanlı veriler kullanılır")
    print("- Spread hesaplaması: ask - bid")
    print("- Benchmark değeri (T): 0.5")
    print("- FINAL BB formülü: FINAL_THG - 400 × bid_buy_ucuzluk")
    print("- Tüm FINAL skorlar aynı formülle hesaplanır")

if __name__ == "__main__":
    demo_final_bb_calculation() 