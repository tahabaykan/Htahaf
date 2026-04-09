"""
Direct Hammer OrderBook Verification
==================================

Uses the newly refactored OrderBookFetcher and HammerClient.
"""
import sys
import os
import json
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.terminals.orderbook_fetcher import OrderBookFetcher
from app.live.hammer_client import HammerClient
from app.config.settings import settings
from loguru import logger

def main():
    # Show more logs
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    print("🚀 Initializing End-to-End OrderBook Verification...")
    
    # 1. Setup Client
    client = HammerClient(
        host=settings.HAMMER_HOST,
        port=settings.HAMMER_PORT,
        password=settings.HAMMER_PASSWORD,
        account_key=settings.HAMMER_ACCOUNT_KEY
    )
    
    if not client.connect():
        print("❌ Failed to connect to Hammer")
        return

    # 2. Setup Fetcher with Client
    fetcher = OrderBookFetcher(client=client)
    
    symbol = "SPY"
    print(f"📡 Fetching OrderBook for {symbol}...")
    
    # Try multiple times as streamer might take a second to warm up
    bids, asks = [], []
    for i in range(5):
        bids, asks = fetcher.fetch_orderbook(symbol, max_levels=10)
        if bids or asks:
            break
        print(f"  Attempt {i+1} empty, retrying...")
        time.sleep(1)

    if bids or asks:
        print(f"\n📊 {symbol} ORDERBOOK RESULTS:")
        print("-" * 30)
        print("📉 BIDS:")
        for p, q in bids:
            print(f"  ${p:6.2f} x {q:4d}")
        print("\n📈 ASKS:")
        for p, q in asks:
            print(f"  ${p:6.2f} x {q:4d}")
            
        # Test selection logic
        mid = (bids[0][0] + asks[0][0]) / 2 if bids and asks else 0
        if mid:
            target_bid = mid - 0.05
            target_ask = mid + 0.05
            print(f"\n🎯 Selection Test (Mid: ${mid:.2f}):")
            
            s_bid = fetcher.find_suitable_bid(symbol, target_bid)
            s_ask = fetcher.find_suitable_ask(symbol, target_ask)
            
            print(f"  Find Bid <= ${target_bid:.2f}: {s_bid}")
            print(f"  Find Ask >= ${target_ask:.2f}: {s_ask}")
    else:
        print(f"❌ Failed to fetch OrderBook for {symbol} after multiple attempts.")

    client.disconnect()
    print("\n👋 Done")

if __name__ == "__main__":
    main()
