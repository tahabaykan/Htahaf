"""
OrderBook Test Script - Fetch OrderBook for FGSN

Tests the OrderBook fetching from Hammer Pro Market Data API.

Usage:
    python tools/orderbook_tester.py
    python tools/orderbook_tester.py --symbol "USB PRS"
"""

import sys
import os
import json
from typing import Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.logger import logger


def fetch_orderbook_from_hammer(symbol: str, levels: int = 10) -> Optional[dict]:
    """
    Fetch OrderBook directly from Hammer Pro Market Data API.
    
    Args:
        symbol: Symbol in display format (e.g., "FGSN", "USB PRS")
        levels: Number of levels to fetch
        
    Returns:
        OrderBook dict with bids/asks or None if failed
    """
    import requests
    
    # Hammer Pro API endpoint
    HAMMER_API_URL = "http://localhost:5000"
    
    try:
        # Try without symbol mapping first
        endpoint = f"{HAMMER_API_URL}/api/market-data/orderbook"
        params = {
            'symbol': symbol,
            'levels': levels
        }
        
        print(f"\n📊 Fetching OrderBook for: {symbol}")
        print(f"   Endpoint: {endpoint}")
        print(f"   Params: {params}")
        
        response = requests.get(endpoint, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            print(f"   ⚠️ HTTP {response.status_code}: {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"   ❌ Cannot connect to Hammer API at {HAMMER_API_URL}")
        print(f"      Make sure Hammer Pro Market Data is running!")
        return None
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None


def fetch_l1_from_redis(symbol: str) -> Optional[dict]:
    """
    Fetch L1 data from Redis (if available).
    
    Args:
        symbol: Symbol in display format
        
    Returns:
        L1 dict with bid/ask/spread or None
    """
    try:
        from app.core.redis_client import get_redis_client
        
        redis = get_redis_client().sync
        key = f"market:l1:{symbol}"
        
        data = redis.get(key)
        if data:
            return json.loads(data)
        else:
            print(f"   ⚠️ No L1 data in Redis for {symbol}")
            return None
            
    except Exception as e:
        print(f"   ❌ Redis error: {e}")
        return None


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Test OrderBook Fetching")
    parser.add_argument("--symbol", type=str, default="FGSN", help="Symbol to fetch (default: FGSN)")
    parser.add_argument("--levels", type=int, default=10, help="Number of levels (default: 10)")
    
    args = parser.parse_args()
    symbol = args.symbol
    levels = args.levels
    
    print("=" * 70)
    print("OrderBook Test Script")
    print("=" * 70)
    
    # 1. Try to get L1 from Redis
    print("\n📌 Step 1: Check L1 Data in Redis")
    l1_data = fetch_l1_from_redis(symbol)
    if l1_data:
        print(f"   ✅ L1 Data Found:")
        print(f"      Bid: ${l1_data.get('bid', 'N/A')}")
        print(f"      Ask: ${l1_data.get('ask', 'N/A')}")
        print(f"      Spread: ${l1_data.get('spread', 'N/A')}")
        print(f"      Last: ${l1_data.get('last', 'N/A')}")
    else:
        print(f"   ⚠️ No L1 data in Redis. Run Truth Ticks Worker to populate.")
    
    # 2. Fetch OrderBook from Hammer
    print("\n📌 Step 2: Fetch OrderBook from Hammer Pro")
    orderbook = fetch_orderbook_from_hammer(symbol, levels)
    
    if orderbook:
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        print(f"\n   ✅ OrderBook Received!")
        print(f"   Bids: {len(bids)} levels")
        print(f"   Asks: {len(asks)} levels")
        
        if bids:
            print(f"\n   📉 BIDS (Top 5):")
            for i, bid in enumerate(bids[:5]):
                price = bid.get('price', bid[0] if isinstance(bid, (list, tuple)) else 0)
                qty = bid.get('qty', bid[1] if isinstance(bid, (list, tuple)) else 0)
                print(f"      {i+1}. ${price:.2f} x {qty}")
        
        if asks:
            print(f"\n   📈 ASKS (Top 5):")
            for i, ask in enumerate(asks[:5]):
                price = ask.get('price', ask[0] if isinstance(ask, (list, tuple)) else 0)
                qty = ask.get('qty', ask[1] if isinstance(ask, (list, tuple)) else 0)
                print(f"      {i+1}. ${price:.2f} x {qty}")
                
        # Calculate spread from orderbook
        if bids and asks:
            top_bid = bids[0].get('price', bids[0][0] if isinstance(bids[0], (list, tuple)) else 0)
            top_ask = asks[0].get('price', asks[0][0] if isinstance(asks[0], (list, tuple)) else 0)
            spread = top_ask - top_bid
            print(f"\n   📊 OrderBook Summary:")
            print(f"      Best Bid: ${top_bid:.2f}")
            print(f"      Best Ask: ${top_ask:.2f}")
            print(f"      Spread: ${spread:.4f}")
    else:
        print(f"\n   ❌ Failed to fetch OrderBook")
        print(f"      Possible reasons:")
        print(f"      1. Hammer Pro not running")
        print(f"      2. Symbol not found: '{symbol}'")
        print(f"      3. Market closed / no data")
    
    print("\n" + "=" * 70)
    print("Test Complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
