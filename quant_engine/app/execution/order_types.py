
"""
Order Types
Standardized Enums for Quant Engine Orders.
"""
from enum import Enum

class QuantOrderBook(Enum):
    """Trading Book Enum"""
    LT = "LT"   # Long Term
    MM = "MM"   # Market Making

class QuantOrderType(Enum):
    """
    Strict Order Types (8 permutations).
    Format: {BOOK}_{DIRECTION}_{ACTION}
    """
    # LT (Long Term)
    LT_LONG_ADD      = "LT_LONG_ADD"
    LT_LONG_REDUCE   = "LT_LONG_REDUCE"
    LT_SHORT_ADD     = "LT_SHORT_ADD"
    LT_SHORT_REDUCE  = "LT_SHORT_REDUCE"
    
    # MM (Market Making)
    MM_LONG_ADD      = "MM_LONG_ADD"
    MM_LONG_REDUCE   = "MM_LONG_REDUCE"
    MM_SHORT_ADD     = "MM_SHORT_ADD"
    MM_SHORT_REDUCE  = "MM_SHORT_REDUCE"
    
    # Validation helper
    @classmethod
    def from_components(cls, book: str, side: str, action: str):
        """
        Construct type from components.
        book: LT/MM
        side: LONG/SHORT
        action: ADD/REDUCE
        """
        key = f"{book}_{side}_{action}".upper()
        if hasattr(cls, key):
            return getattr(cls, key)
        return None
