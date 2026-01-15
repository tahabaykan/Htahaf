"""app/strategy/indicators.py

Technical indicators for strategy use.
Provides common indicators like SMA, EMA, RSI, MACD, etc.
"""

from typing import List, Dict, Optional
from collections import deque
import math


class IndicatorCache:
    """Cache for indicator values per symbol"""
    
    def __init__(self, max_size: int = 1000):
        """
        Initialize indicator cache.
        
        Args:
            max_size: Maximum number of values to cache per indicator
        """
        self.cache: Dict[str, Dict[str, deque]] = {}  # {symbol: {indicator_name: deque}}
        self.max_size = max_size
    
    def add_value(self, symbol: str, indicator_name: str, value: float):
        """Add indicator value to cache"""
        if symbol not in self.cache:
            self.cache[symbol] = {}
        if indicator_name not in self.cache[symbol]:
            self.cache[symbol][indicator_name] = deque(maxlen=self.max_size)
        
        self.cache[symbol][indicator_name].append(value)
    
    def get_values(self, symbol: str, indicator_name: str, period: Optional[int] = None) -> List[float]:
        """Get indicator values (last N values if period specified)"""
        if symbol not in self.cache or indicator_name not in self.cache[symbol]:
            return []
        
        values = list(self.cache[symbol][indicator_name])
        if period:
            return values[-period:]
        return values
    
    def get_last(self, symbol: str, indicator_name: str) -> Optional[float]:
        """Get last indicator value"""
        values = self.get_values(symbol, indicator_name, period=1)
        return values[0] if values else None
    
    def clear(self, symbol: Optional[str] = None):
        """Clear cache (all symbols or specific symbol)"""
        if symbol:
            if symbol in self.cache:
                del self.cache[symbol]
        else:
            self.cache.clear()


class Indicators:
    """Technical indicators calculator"""
    
    @staticmethod
    def sma(prices: List[float], period: int) -> Optional[float]:
        """
        Simple Moving Average.
        
        Args:
            prices: List of prices
            period: Period length
            
        Returns:
            SMA value or None if insufficient data
        """
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period
    
    @staticmethod
    def ema(prices: List[float], period: int, previous_ema: Optional[float] = None) -> Optional[float]:
        """
        Exponential Moving Average.
        
        Args:
            prices: List of prices
            period: Period length
            previous_ema: Previous EMA value (for incremental calculation)
            
        Returns:
            EMA value or None if insufficient data
        """
        if not prices:
            return None
        
        multiplier = 2.0 / (period + 1)
        
        if previous_ema is not None:
            # Incremental calculation
            return (prices[-1] - previous_ema) * multiplier + previous_ema
        else:
            # Initial calculation
            if len(prices) < period:
                return None
            # Start with SMA
            sma_value = sum(prices[:period]) / period
            # Calculate EMA from there
            ema_value = sma_value
            for price in prices[period:]:
                ema_value = (price - ema_value) * multiplier + ema_value
            return ema_value
    
    @staticmethod
    def rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """
        Relative Strength Index.
        
        Args:
            prices: List of prices
            period: Period length (default: 14)
            
        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if len(prices) < period + 1:
            return None
        
        gains = []
        losses = []
        
        for i in range(len(prices) - period, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    @staticmethod
    def macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Dict[str, float]]:
        """
        MACD (Moving Average Convergence Divergence).
        
        Args:
            prices: List of prices
            fast: Fast EMA period
            slow: Slow EMA period
            signal: Signal line EMA period
            
        Returns:
            Dict with 'macd', 'signal', 'histogram' or None
        """
        if len(prices) < slow:
            return None
        
        # Calculate EMAs
        fast_ema = Indicators.ema(prices, fast)
        slow_ema = Indicators.ema(prices, slow)
        
        if fast_ema is None or slow_ema is None:
            return None
        
        macd_line = fast_ema - slow_ema
        
        # Calculate signal line (EMA of MACD)
        # For simplicity, use MACD value as signal (in production, maintain MACD history)
        signal_line = macd_line  # Simplified
        
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    @staticmethod
    def bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2.0) -> Optional[Dict[str, float]]:
        """
        Bollinger Bands.
        
        Args:
            prices: List of prices
            period: Period length
            std_dev: Standard deviation multiplier
            
        Returns:
            Dict with 'upper', 'middle', 'lower' or None
        """
        if len(prices) < period:
            return None
        
        sma = Indicators.sma(prices, period)
        if sma is None:
            return None
        
        # Calculate standard deviation
        variance = sum((p - sma) ** 2 for p in prices[-period:]) / period
        std = math.sqrt(variance)
        
        return {
            'upper': sma + (std_dev * std),
            'middle': sma,
            'lower': sma - (std_dev * std)
        }


# Global indicator cache instance
indicator_cache = IndicatorCache()








