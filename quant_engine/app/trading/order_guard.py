"""
ORDER GUARD — Central Pre-Flight Check for ALL Orders
=====================================================

This module provides a single, authoritative check that runs BEFORE
any order is sent to ANY venue (Hammer Pro, IBKR, etc.).

Checks:
  1. EXCLUDED LIST (qe_excluded.csv) — symbols that must NEVER receive orders
  2. (Future: MinMax validation, market hours, etc.)

Usage:
  from app.trading.order_guard import is_order_allowed

  allowed, reason = is_order_allowed(symbol)
  if not allowed:
      logger.warning(f"🚫 [ORDER_GUARD] BLOCKED: {symbol} — {reason}")
      return {'success': False, 'message': reason}

CRITICAL: This guard is the LAST BARRIER before real money is spent.
          It must be called in EVERY order execution path.
"""

import os
import csv
import time
from typing import Tuple, Set, Optional
from pathlib import Path
from app.core.logger import logger


# ═══════════════════════════════════════════════════════════════════
# EXCLUDED LIST CACHE
# Loads qe_excluded.csv once, refreshes every 60 seconds
# ═══════════════════════════════════════════════════════════════════

_excluded_symbols: Set[str] = set()
_excluded_last_loaded: float = 0.0
_EXCLUDED_REFRESH_INTERVAL = 60.0  # Reload every 60 seconds


def _load_excluded_list() -> Set[str]:
    """Load excluded symbols from qe_excluded.csv with caching."""
    global _excluded_symbols, _excluded_last_loaded
    
    now = time.time()
    
    # Return cached if fresh enough
    if _excluded_symbols and (now - _excluded_last_loaded) < _EXCLUDED_REFRESH_INTERVAL:
        return _excluded_symbols
    
    try:
        # Try multiple paths
        possible_paths = [
            Path(os.getcwd()) / 'qe_excluded.csv',
            Path(r'C:\StockTracker\quant_engine\qe_excluded.csv'),
            Path(r'C:\StockTracker\quant_engine') / 'qe_excluded.csv',
        ]
        
        for excluded_path in possible_paths:
            if excluded_path.exists():
                symbols = set()
                with open(excluded_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row:
                            symbols.update([s.strip().upper() for s in row if s.strip()])
                
                if symbols != _excluded_symbols:
                    logger.info(
                        f"🚫 [ORDER_GUARD] Excluded list loaded: {len(symbols)} symbols "
                        f"from {excluded_path} — {sorted(symbols)}"
                    )
                
                _excluded_symbols = symbols
                _excluded_last_loaded = now
                return _excluded_symbols
        
        # No file found
        if not _excluded_symbols:
            logger.warning("[ORDER_GUARD] qe_excluded.csv not found — no excluded symbols")
        _excluded_last_loaded = now
        return _excluded_symbols
        
    except Exception as e:
        logger.error(f"[ORDER_GUARD] Error loading excluded list: {e}")
        _excluded_last_loaded = now
        return _excluded_symbols


def is_excluded(symbol: str) -> bool:
    """Check if symbol is in the excluded list."""
    excluded = _load_excluded_list()
    return symbol.strip().upper() in excluded


# ═══════════════════════════════════════════════════════════════════
# MAIN GUARD FUNCTION
# ═══════════════════════════════════════════════════════════════════

def is_order_allowed(
    symbol: str,
    side: Optional[str] = None,
    quantity: Optional[float] = None,
    tag: Optional[str] = None,
    account_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Central pre-flight check for ALL orders.
    
    Returns:
        (True, "OK") if order is allowed
        (False, "reason") if order must be BLOCKED
    """
    symbol_upper = symbol.strip().upper()
    
    # ─── CHECK 1: EXCLUDED LIST ───
    if is_excluded(symbol_upper):
        reason = (
            f"🚫 EXCLUDED LIST BLOCK: {symbol_upper} is in qe_excluded.csv — "
            f"order REJECTED (side={side}, qty={quantity}, tag={tag}, acct={account_id})"
        )
        logger.error(f"[ORDER_GUARD] {reason}")
        return False, reason
    
    # ─── All checks passed ───
    return True, "OK"


def get_excluded_symbols() -> Set[str]:
    """Get current excluded symbols set (for diagnostics)."""
    return _load_excluded_list().copy()


def force_reload_excluded() -> Set[str]:
    """Force reload excluded list (bypass cache)."""
    global _excluded_last_loaded
    _excluded_last_loaded = 0.0
    return _load_excluded_list()
