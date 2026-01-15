"""
Safe Access Utilities - NO-EXCEPTION CONTRACT

Provides safe access to nested attributes and values.
All getters return (value, status) or default - NEVER throw exceptions.
"""

from typing import Any, Optional, Tuple
from datetime import datetime
from enum import Enum


class DataStatus(Enum):
    """Status of data retrieval."""
    OK = "OK"
    MISSING = "MISSING"
    STALE = "STALE"
    UNKNOWN_SYMBOL = "UNKNOWN_SYMBOL"
    MISSING_BENCHMARK = "MISSING_BENCHMARK"
    INVALID = "INVALID"


def safe_get(obj: Any, path: str, default: Any = None) -> Any:
    """
    Safe nested attribute/key access. NEVER throws exception.
    
    Examples:
        safe_get(ctx, "l1.bid", 0.0)
        safe_get(data, "scores.fbtot", None)
        safe_get(config, "settings.timeout", 30)
    
    Args:
        obj: Object to access
        path: Dot-separated path (e.g., "l1.bid" or "scores.fbtot")
        default: Default value if path not found
        
    Returns:
        Value at path or default
    """
    if obj is None:
        return default
    
    try:
        parts = path.split('.')
        current = obj
        
        for part in parts:
            if current is None:
                return default
            
            # Try attribute access first
            if hasattr(current, part):
                current = getattr(current, part, None)
            # Then try dict-like access
            elif hasattr(current, 'get'):
                current = current.get(part, None)
            elif hasattr(current, '__getitem__'):
                try:
                    current = current[part]
                except (KeyError, IndexError, TypeError):
                    return default
            else:
                return default
        
        return current if current is not None else default
    except Exception:
        return default


def safe_num(value: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safe numeric conversion. NEVER throws exception.
    
    Args:
        value: Value to convert
        default: Default if conversion fails
        
    Returns:
        Float value or default
    """
    if value is None:
        return default
    
    if isinstance(value, (int, float)):
        return float(value)
    
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """
    Safe integer conversion. NEVER throws exception.
    
    Args:
        value: Value to convert
        default: Default if conversion fails
        
    Returns:
        Int value or default
    """
    if value is None:
        return default
    
    if isinstance(value, int):
        return value
    
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def is_fresh(ts: Optional[datetime], max_age_seconds: float = 60.0) -> bool:
    """
    Check if timestamp is within acceptable age.
    
    Args:
        ts: Timestamp to check
        max_age_seconds: Maximum acceptable age in seconds
        
    Returns:
        True if timestamp is fresh, False if stale or missing
    """
    if ts is None:
        return False
    
    try:
        age = (datetime.now() - ts).total_seconds()
        return age <= max_age_seconds
    except Exception:
        return False


def get_age_seconds(ts: Optional[datetime]) -> Optional[float]:
    """
    Get age of timestamp in seconds.
    
    Args:
        ts: Timestamp to check
        
    Returns:
        Age in seconds or None if timestamp is None
    """
    if ts is None:
        return None
    
    try:
        return (datetime.now() - ts).total_seconds()
    except Exception:
        return None


def safe_divide(numerator: Any, denominator: Any, default: float = 0.0) -> float:
    """
    Safe division. Returns default for zero/None denominators.
    
    Args:
        numerator: Numerator value
        denominator: Denominator value
        default: Default if division fails
        
    Returns:
        Division result or default
    """
    num = safe_num(numerator)
    den = safe_num(denominator)
    
    if num is None or den is None or den == 0:
        return default
    
    return num / den


def safe_percent(value: Any, total: Any, default: float = 0.0) -> float:
    """
    Calculate percentage safely.
    
    Args:
        value: Part value
        total: Total value
        default: Default if calculation fails
        
    Returns:
        Percentage (0-100) or default
    """
    return safe_divide(value, total, default) * 100


def coalesce(*values, default: Any = None) -> Any:
    """
    Return first non-None value.
    
    Args:
        *values: Values to check
        default: Default if all are None
        
    Returns:
        First non-None value or default
    """
    for v in values:
        if v is not None:
            return v
    return default
