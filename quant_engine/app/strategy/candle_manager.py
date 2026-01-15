"""app/strategy/candle_manager.py

Candle/OHLCV data manager - converts ticks to candles.
Provides candle data for strategy use.
"""

import time
from typing import Dict, List, Optional, Any
from collections import defaultdict
from datetime import datetime, timedelta

from app.core.logger import logger


class Candle:
    """OHLCV candle data"""
    
    def __init__(self, symbol: str, timestamp: float, open: float, high: float, low: float, close: float, volume: float = 0.0):
        self.symbol = symbol
        self.timestamp = timestamp
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }


class CandleManager:
    """Manages candle data for symbols"""
    
    def __init__(self, interval_seconds: int = 60):
        """
        Initialize candle manager.
        
        Args:
            interval_seconds: Candle interval in seconds (default: 60 = 1 minute)
        """
        self.interval_seconds = interval_seconds
        self.candles: Dict[str, List[Candle]] = defaultdict(list)  # symbol -> candles
        self.current_candles: Dict[str, Dict] = {}  # symbol -> current candle data
        self.max_candles = 1000  # Maximum candles to keep per symbol
    
    def add_tick(self, tick: Dict[str, Any]) -> Optional[Candle]:
        """
        Add tick and update/create candle.
        
        Args:
            tick: Tick data dict with keys: symbol, last, volume, ts
            
        Returns:
            Completed candle if interval closed, None otherwise
        """
        try:
            symbol = tick.get('symbol')
            price = float(tick.get('last', 0))
            volume = float(tick.get('volume', 0))
            timestamp = float(tick.get('ts', time.time() * 1000)) / 1000.0  # Convert ms to seconds
            
            if not symbol or price <= 0:
                return None
            
            # Get current candle for symbol
            current = self.current_candles.get(symbol)
            
            # Calculate candle start time
            candle_start = int(timestamp / self.interval_seconds) * self.interval_seconds
            
            # Check if new candle needed
            if current is None or current['candle_start'] != candle_start:
                # Close previous candle if exists
                completed_candle = None
                if current is not None:
                    completed_candle = Candle(
                        symbol=symbol,
                        timestamp=current['candle_start'],
                        open=current['open'],
                        high=current['high'],
                        low=current['low'],
                        close=current['close'],
                        volume=current['volume']
                    )
                    self._add_candle(symbol, completed_candle)
                
                # Start new candle
                self.current_candles[symbol] = {
                    'candle_start': candle_start,
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                    'volume': volume
                }
                
                return completed_candle
            else:
                # Update current candle
                current['high'] = max(current['high'], price)
                current['low'] = min(current['low'], price)
                current['close'] = price
                current['volume'] += volume
                
                return None
        
        except Exception as e:
            logger.error(f"Error adding tick to candle: {e}", exc_info=True)
            return None
    
    def _add_candle(self, symbol: str, candle: Candle):
        """Add completed candle to history"""
        self.candles[symbol].append(candle)
        
        # Limit history size
        if len(self.candles[symbol]) > self.max_candles:
            self.candles[symbol] = self.candles[symbol][-self.max_candles:]
    
    def get_candles(self, symbol: str, count: Optional[int] = None) -> List[Candle]:
        """
        Get candle history for symbol.
        
        Args:
            symbol: Stock symbol
            count: Number of candles to return (None = all)
            
        Returns:
            List of candles (oldest first)
        """
        candles = self.candles.get(symbol, [])
        if count:
            return candles[-count:]
        return candles
    
    def get_last_candle(self, symbol: str) -> Optional[Candle]:
        """Get last completed candle for symbol"""
        candles = self.candles.get(symbol, [])
        return candles[-1] if candles else None
    
    def get_current_candle(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current (incomplete) candle for symbol"""
        current = self.current_candles.get(symbol)
        if current:
            return {
                'symbol': symbol,
                'timestamp': current['candle_start'],
                'open': current['open'],
                'high': current['high'],
                'low': current['low'],
                'close': current['close'],
                'volume': current['volume']
            }
        return None
    
    def get_candle_data(self, symbol: str, count: int = 100) -> Dict[str, List[float]]:
        """
        Get candle data in format suitable for indicators.
        
        Args:
            symbol: Stock symbol
            count: Number of candles
            
        Returns:
            Dict with 'open', 'high', 'low', 'close', 'volume' lists
        """
        candles = self.get_candles(symbol, count)
        
        return {
            'open': [c.open for c in candles],
            'high': [c.high for c in candles],
            'low': [c.low for c in candles],
            'close': [c.close for c in candles],
            'volume': [c.volume for c in candles]
        }








