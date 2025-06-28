"""
Utility functions for StockTracker application
"""
import math
import re

def safe_format_float(value, format_str="{:.2f}"):
    """Safely format a potential float value, handling None, NaN, etc."""
    try:
        if value is None:
            return "0.00"
        
        # Convert to float and check if it's NaN
        val = float(value)
        if math.isnan(val):
            return "0.00"
            
        return format_str.format(val)
    except (ValueError, TypeError):
        return "0.00"

def safe_float(value, default=0.0):
    """Convert a value to float safely, returning default if conversion fails."""
    try:
        if value is None:
            return default
        
        val = float(value)
        if math.isnan(val):
            return default
            
        return val
    except (ValueError, TypeError):
        return default

def safe_int(value, default=0):
    """Convert a value to int safely, returning default if conversion fails."""
    try:
        if value is None:
            return default
        
        # First convert to float to handle values like "123.45"
        val = float(value)
        if math.isnan(val):
            return default
            
        return int(val)
    except (ValueError, TypeError):
        return default

def normalize_ticker_column(df):
    """Normalize ticker column in DataFrame for consistency."""
    if df is not None and 'ticker' in df.columns:
        df['ticker'] = df['ticker'].str.strip().str.upper()
    return df 