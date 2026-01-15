"""
Position Tagging System

Manages position tags with intraday/overnight tracking.
Implements 1200+ lot auto-upgrade rule and majority-based tagging.

Tag Format: [LT/MM] [int/ov] [long/short]
Examples: 'LT int long', 'MM ov short'

Rules:
1. Total qty >= 1200 → auto 'ov' (overnight)
2. Total qty < 1200 → majority wins (int vs ov)
3. Daily reset: all int_qty → ov_qty
"""
from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from loguru import logger


@dataclass
class PositionTag:
    """Individual position tag state"""
    symbol: str
    total_qty: float = 0.0
    ov_qty: float = 0.0  # Overnight quantity (from BEFDAY or previous day)
    int_qty: float = 0.0  # Intraday quantity (filled today)
    is_mm: bool = False  # MM position vs LT position
    
    def calculate_tag(self) -> str:
        """
        Calculate position tag based on current state.
        
        Returns:
            Tag string: '[LT/MM] [int/ov] [long/short]'
        """
        if self.total_qty == 0:
            return ''
        
        # Determine suffix (int/ov)
        if abs(self.total_qty) >= 1200:
            # Rule 1: 1200+ auto-upgrade to ov
            suffix = 'ov'
        else:
            # Rule 2: Majority wins
            suffix = 'int' if self.int_qty > self.ov_qty else 'ov'
        
        # Determine base (LT/MM)
        base = 'MM' if self.is_mm else 'LT'
        
        # Determine direction (long/short)
        direction = 'long' if self.total_qty > 0 else 'short'
        
        return f"{base} {suffix} {direction}"


class PositionTagManager:
    """
    Singleton managing all position tags.
    
    Tracks int/ov quantities for each position and calculates tags
    according to the rules.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._tags: Dict[str, PositionTag] = {}
        self._initialized = True
        logger.info("[PositionTagManager] Initialized")
    
    def get_or_create_tag(self, symbol: str, is_mm: bool = False) -> PositionTag:
        """Get existing tag or create new one"""
        if symbol not in self._tags:
            self._tags[symbol] = PositionTag(symbol=symbol, is_mm=is_mm)
        return self._tags[symbol]
    
    def update_on_befday_load(self, symbol: str, qty: float, is_mm: bool = False):
        """
        Load position from BEFDAY (overnight position).
        
        All BEFDAY quantities are overnight.
        """
        tag = self.get_or_create_tag(symbol, is_mm)
        tag.ov_qty = qty
        tag.int_qty = 0.0
        tag.total_qty = qty
        
        logger.debug(f"[PositionTag] BEFDAY {symbol}: ov={qty}, tag={tag.calculate_tag()}")
    
    def update_on_fill(self, symbol: str, fill_qty: float, is_new_position: bool = False, is_mm: bool = False):
        """
        Update position on fill (intraday increase).
        
        Args:
            symbol: Stock symbol
            fill_qty: Filled quantity (positive for long, negative for short)
            is_new_position: True if opening new position
            is_mm: True if MM position
        """
        tag = self.get_or_create_tag(symbol, is_mm)
        
        # Add to intraday
        tag.int_qty += fill_qty
        tag.total_qty += fill_qty
        
        logger.info(f"[PositionTag] FILL {symbol}: +{fill_qty} → total={tag.total_qty} "
                   f"(ov={tag.ov_qty}, int={tag.int_qty}) tag={tag.calculate_tag()}")
    
    def update_on_reduce(self, symbol: str, reduce_qty: float):
        """
        Reduce position (decrease).
        
        Priority: Reduce from int_qty first, then ov_qty.
        
        Args:
            symbol: Stock symbol
            reduce_qty: Amount to reduce (positive number)
        """
        tag = self.get_or_create_tag(symbol)
        
        remaining = abs(reduce_qty)
        
        # Reduce from int first
        if tag.int_qty > 0 and remaining > 0:
            int_reduce = min(tag.int_qty, remaining)
            tag.int_qty -= int_reduce
            remaining -= int_reduce
        
        # Then reduce from ov
        if remaining > 0:
            tag.ov_qty -= remaining
        
        # Update total
        tag.total_qty -= abs(reduce_qty)
        
        # If position closed, remove tag
        if abs(tag.total_qty) < 0.01:
            logger.info(f"[PositionTag] CLOSED {symbol}")
            del self._tags[symbol]
        else:
            logger.info(f"[PositionTag] REDUCE {symbol}: -{reduce_qty} → total={tag.total_qty} "
                       f"(ov={tag.ov_qty}, int={tag.int_qty}) tag={tag.calculate_tag()}")
    
    def reset_daily(self):
        """
        Daily reset: Convert all int → ov.
        
        Called at market open / day start.
        All intraday positions become overnight.
        """
        for symbol, tag in self._tags.items():
            tag.ov_qty = tag.total_qty
            tag.int_qty = 0.0
            logger.info(f"[PositionTag] DAILY_RESET {symbol}: all → ov, tag={tag.calculate_tag()}")
        
        logger.info(f"[PositionTagManager] Daily reset completed for {len(self._tags)} positions")
    
    def get_tag(self, symbol: str) -> str:
        """
        Get current tag for symbol.
        
        Returns:
            Tag string or empty if no position
        """
        if symbol not in self._tags:
            return ''
        
        return self._tags[symbol].calculate_tag()
    
    def get_tag_details(self, symbol: str) -> Optional[Dict]:
        """
        Get detailed tag info for symbol.
        
        Returns:
            Dict with total_qty, ov_qty, int_qty, tag
        """
        if symbol not in self._tags:
            return None
        
        tag = self._tags[symbol]
        return {
            'symbol': symbol,
            'total_qty': tag.total_qty,
            'ov_qty': tag.ov_qty,
            'int_qty': tag.int_qty,
            'tag': tag.calculate_tag()
        }
    
    def get_all_tags(self) -> Dict[str, str]:
        """Get all position tags"""
        return {symbol: tag.calculate_tag() for symbol, tag in self._tags.items()}


# Singleton accessor
_tag_manager_instance = None

def get_position_tag_manager() -> PositionTagManager:
    """Get singleton PositionTagManager instance"""
    global _tag_manager_instance
    if _tag_manager_instance is None:
        _tag_manager_instance = PositionTagManager()
    return _tag_manager_instance
