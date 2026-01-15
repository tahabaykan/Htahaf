"""app/execution/liquidity.py

Liquidity models for execution simulation.
Handles volume-based fills and impact slippage.
"""

from enum import Enum
from typing import Dict, Optional
from collections import defaultdict
from app.core.logger import logger


class LiquidityModelType(Enum):
    """Liquidity model types"""
    VOLUME_BASED = "volume_based"
    IMPACT_BASED = "impact_based"
    HYBRID = "hybrid"


class LiquidityModel:
    """
    Liquidity model for execution simulation.
    
    Determines:
    - Maximum fill quantity based on available liquidity
    - Impact slippage based on order size vs market depth
    """
    
    def __init__(
        self,
        model_type: LiquidityModelType = LiquidityModelType.HYBRID,
        volume_fraction: float = 0.1,
        impact_coefficient: float = 0.1,
        avg_daily_volumes: Optional[Dict[str, float]] = None
    ):
        """
        Initialize liquidity model.
        
        Args:
            model_type: Type of liquidity model
            volume_fraction: Fraction of volume that can be filled (0.1 = 10%)
            impact_coefficient: Impact coefficient for slippage calculation
            avg_daily_volumes: Average daily volumes per symbol (for impact calculation)
        """
        self.model_type = model_type
        self.volume_fraction = volume_fraction
        self.impact_coefficient = impact_coefficient
        self.avg_daily_volumes = avg_daily_volumes or {}
        
        # Track volume history for dynamic avg calculation
        self.volume_history: Dict[str, list] = defaultdict(list)
    
    def update_volume(self, symbol: str, volume: float):
        """Update volume history for symbol"""
        self.volume_history[symbol].append(volume)
        # Keep last 100 volumes
        if len(self.volume_history[symbol]) > 100:
            self.volume_history[symbol].pop(0)
    
    def get_avg_daily_volume(self, symbol: str) -> float:
        """Get average daily volume for symbol"""
        if symbol in self.avg_daily_volumes:
            return self.avg_daily_volumes[symbol]
        
        # Calculate from history
        if symbol in self.volume_history and len(self.volume_history[symbol]) > 0:
            volumes = self.volume_history[symbol]
            return sum(volumes) / len(volumes)
        
        # Default: assume 1M shares/day
        return 1_000_000.0
    
    def get_max_fill_qty(self, symbol: str, tick: Dict) -> float:
        """
        Get maximum fill quantity based on available liquidity.
        
        Args:
            symbol: Stock symbol
            tick: Current tick data with volume
            
        Returns:
            Maximum fillable quantity
        """
        volume = float(tick.get('volume', 0))
        
        if self.model_type == LiquidityModelType.VOLUME_BASED:
            # Volume-based: can fill up to volume_fraction of current volume
            max_fill = volume * self.volume_fraction
            return max(0, max_fill)
        
        elif self.model_type == LiquidityModelType.IMPACT_BASED:
            # Impact-based: use average daily volume
            avg_volume = self.get_avg_daily_volume(symbol)
            # Can fill up to a fraction of average daily volume
            max_fill = avg_volume * self.volume_fraction
            return max(0, max_fill)
        
        elif self.model_type == LiquidityModelType.HYBRID:
            # Hybrid: use both current volume and average volume
            current_max = volume * self.volume_fraction
            avg_max = self.get_avg_daily_volume(symbol) * self.volume_fraction
            # Use the minimum (more conservative)
            max_fill = min(current_max, avg_max)
            return max(0, max_fill)
        
        else:
            # Default: no limit
            return float('inf')
    
    def compute_impact_slippage(self, symbol: str, qty: float) -> float:
        """
        Compute impact slippage based on order size.
        
        Formula: impact = k * (qty / avg_daily_volume)
        
        Args:
            symbol: Stock symbol
            qty: Order quantity
            
        Returns:
            Impact slippage as fraction (e.g., 0.001 = 0.1%)
        """
        avg_volume = self.get_avg_daily_volume(symbol)
        
        if avg_volume <= 0:
            return 0.0
        
        # Impact = coefficient * (order_size / avg_daily_volume)
        impact = self.impact_coefficient * (abs(qty) / avg_volume)
        
        # Cap impact at 5% (very large orders)
        impact = min(impact, 0.05)
        
        return impact
    
    def compute_spread_slippage(self, tick: Dict) -> float:
        """
        Compute spread-based slippage.
        
        Args:
            tick: Current tick data with bid/ask
            
        Returns:
            Spread slippage as fraction
        """
        bid = float(tick.get('bid', 0))
        ask = float(tick.get('ask', 0))
        last = float(tick.get('last', 0))
        
        if bid <= 0 or ask <= 0:
            return 0.0
        
        # Spread = (ask - bid) / mid
        mid = (bid + ask) / 2.0
        if mid <= 0:
            return 0.0
        
        spread = (ask - bid) / mid
        
        # Spread slippage = half of spread (we pay half on average)
        return spread / 2.0








