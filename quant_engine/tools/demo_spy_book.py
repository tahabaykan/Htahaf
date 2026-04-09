"""
Demo SPY OrderBook - Mock Data for Market-Off Hours
==================================================
This script demonstrates the OrderBook format and the selection logic
using mock data, since the US market is currently closed.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.terminals.orderbook_fetcher import OrderBookFetcher
from unittest.mock import MagicMock

def main():
    print("🚀 Running SPY OrderBook Mock Demonstration (Market Closed)")
    
    # 1. Create a fetcher
    fetcher = OrderBookFetcher()
    
    # 2. Mock the client and its response to simulate Hammer Pro L2 Snapshot
    mock_client = MagicMock()
    mock_snapshot = {
        'symbol': 'SPY',
        'bids': [
            {'price': 480.50, 'size': 1500},
            {'price': 480.45, 'size': 2000},
            {'price': 480.40, 'size': 800},
            {'price': 480.35, 'size': 500},
            {'price': 480.30, 'size': 1200},
        ],
        'asks': [
            {'price': 480.55, 'size': 1200},
            {'price': 480.60, 'size': 800},
            {'price': 480.65, 'size': 2500},
            {'price': 480.70, 'size': 1000},
            {'price': 480.75, 'size': 3000},
        ]
    }
    mock_client.get_l2_snapshot.return_value = mock_snapshot
    fetcher._client = mock_client
    
    symbol = "SPY"
    print(f"\n📡 Simulating OrderBook Fetch for {symbol}...")
    
    bids, asks = fetcher.fetch_orderbook(symbol)
    
    if bids or asks:
        print(f"\n📊 {symbol} ORDERBOOK (MOCK DATA):")
        print("=" * 40)
        print(f"{'BIDS (BUY)':<20} | {'ASKS (SELL)':<20}")
        print("-" * 40)
        
        for i in range(max(len(bids), len(asks))):
            bid_str = f"${bids[i][0]:.2f} x {bids[i][1]}" if i < len(bids) else ""
            ask_str = f"${asks[i][0]:.2f} x {asks[i][1]}" if i < len(asks) else ""
            print(f"{bid_str:<20} | {ask_str:<20}")
            
        # 3. Test selection logic for REV Orders
        # Scenario: Fill price was 480.52 (BUY). 
        # Profit target $0.04 -> Min Sell boundary = 480.56
        fill_price = 480.52
        min_sell = fill_price + 0.04
        
        print(f"\n🎯 REV Order Logic Test:")
        print(f"  Fill Price: ${fill_price:.2f}")
        print(f"  Profit Target: +$0.04")
        print(f"  Min Sell Price: >= ${min_sell:.2f}")
        
        suitable_ask = fetcher.find_suitable_ask(bids, min_sell) # Note: find_suitable_ask expects list or sym
        # Re-fetching to test the find_suitable_ask internal logic
        fetcher.fetch_orderbook = MagicMock(return_value=(bids, asks))
        
        result_ask = fetcher.find_suitable_ask(symbol, min_sell)
        
        print(f"\n🔍 Result:")
        if result_ask:
            print(f"  ✅ Found Level: ${result_ask:.2f}")
            print(f"  🚀 Final REV Order Price (Fronting -0.01): ${result_ask - 0.01:.2f}")
        else:
            print(f"  ❌ No suitable level found above ${min_sell:.2f}")
    else:
        print("❌ Error: Mock data failed to parse.")

if __name__ == "__main__":
    main()
