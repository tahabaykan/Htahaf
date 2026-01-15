"""app/market_data/hammer_api_stub.py

Hammer PRO API stub - generates fake market data for testing.

This file provides a fake feed generator when real Hammer PRO API is not available.
Replace this with actual Hammer PRO API integration when ready.

Usage:
    from app.market_data.hammer_api_stub import hammer_fake_feed
    
    for tick in hammer_fake_feed("AAPL"):
        print(tick)
"""

import time
import random
from typing import Iterator, Dict, Any, Optional


def hammer_fake_feed(symbol: str = "AAPL", delay: float = 0.05) -> Iterator[Dict[str, Any]]:
    """
    Generate fake market data feed (for testing).
    
    Args:
        symbol: Stock symbol
        delay: Delay between ticks (seconds)
        
    Yields:
        Tick dict in Hammer PRO format
    """
    base_price = 100.0 + random.random() * 50  # Random base price
    
    while True:
        # Random walk price
        change = (random.random() - 0.5) * 2  # -1 to +1
        base_price = max(1.0, base_price + change)
        
        # Generate tick
        tick = {
            "symbol": symbol,
            "last": round(base_price, 2),
            "bid": round(base_price - 0.01, 2),
            "ask": round(base_price + 0.01, 2),
            "volume": random.randint(1000, 10000),
            "timestamp": int(time.time() * 1000)
        }
        
        yield tick
        time.sleep(delay)


def hammer_fake_feed_multi(symbols: list, delay: float = 0.05) -> Iterator[Dict[str, Any]]:
    """
    Generate fake market data feed for multiple symbols.
    
    Args:
        symbols: List of stock symbols
        delay: Delay between ticks (seconds)
        
    Yields:
        Tick dicts for each symbol in rotation
    """
    base_prices = {sym: 100.0 + random.random() * 50 for sym in symbols}
    
    while True:
        for symbol in symbols:
            # Random walk price
            change = (random.random() - 0.5) * 2
            base_prices[symbol] = max(1.0, base_prices[symbol] + change)
            
            tick = {
                "symbol": symbol,
                "last": round(base_prices[symbol], 2),
                "bid": round(base_prices[symbol] - 0.01, 2),
                "ask": round(base_prices[symbol] + 0.01, 2),
                "volume": random.randint(1000, 10000),
                "timestamp": int(time.time() * 1000)
            }
            
            yield tick
            time.sleep(delay)


# Example: Real Hammer PRO API integration (placeholder)
class HammerProAPI:
    """
    Real Hammer PRO API client (placeholder).
    
    Replace this with actual Hammer PRO API implementation.
    """
    
    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        """
        Initialize Hammer PRO API client.
        
        Args:
            api_key: API key (if required)
            api_url: API endpoint URL
        """
        self.api_key = api_key
        self.api_url = api_url or "https://api.hammerpro.com"
        # TODO: Initialize actual API client
    
    def get_ticks(self, symbol: str) -> Iterator[Dict[str, Any]]:
        """
        Get real-time ticks for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Yields:
            Tick dicts from Hammer PRO
        """
        # TODO: Implement actual Hammer PRO API call
        # Example:
        #   response = self.client.stream_ticks(symbol)
        #   for tick in response:
        #       yield tick
        raise NotImplementedError("Real Hammer PRO API not implemented yet. Use hammer_fake_feed for testing.")








