"""app/utils/time_utils.py

Time utility functions.
"""

import time
from datetime import datetime
from typing import Optional


def get_timestamp() -> float:
    """Get current timestamp"""
    return time.time()


def get_timestamp_ms() -> int:
    """Get current timestamp in milliseconds"""
    return int(time.time() * 1000)


def format_timestamp(ts: Optional[float] = None, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Format timestamp to string.
    
    Args:
        ts: Timestamp (default: current time)
        format_str: Format string
        
    Returns:
        Formatted timestamp string
    """
    if ts is None:
        ts = time.time()
    return datetime.fromtimestamp(ts).strftime(format_str)








