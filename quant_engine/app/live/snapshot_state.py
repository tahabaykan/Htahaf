"""
Snapshot State Manager
Tracks snapshot fetch state per symbol to prevent duplicate requests.

CRITICAL: Snapshot is BOOTSTRAP-ONLY, not real-time.
- Snapshot is fetched once per symbol (on first discovery or startup)
- State is tracked: attempted, success, failed, last_attempt
- Once attempted, symbol is never enqueued again (unless manual retry)
"""

import time
import logging
from typing import Dict, Optional
from threading import Lock

logger = logging.getLogger(__name__)

# Snapshot state per symbol
_snapshot_state: Dict[str, Dict[str, any]] = {}  # symbol -> {attempted, success, failed, last_attempt}
_state_lock = Lock()

# Retry configuration
MAX_RETRY_COUNT = 3
RETRY_INTERVAL = 600  # 10 minutes


def get_snapshot_state(symbol: str) -> Dict[str, any]:
    """Get snapshot state for a symbol"""
    with _state_lock:
        return _snapshot_state.get(symbol, {
            "attempted": False,
            "success": False,
            "failed": False,
            "last_attempt": 0,
            "retry_count": 0
        })


def mark_snapshot_attempted(symbol: str):
    """Mark snapshot as attempted"""
    with _state_lock:
        if symbol not in _snapshot_state:
            _snapshot_state[symbol] = {
                "attempted": True,
                "success": False,
                "failed": False,
                "last_attempt": time.time(),
                "retry_count": 0
            }
        else:
            _snapshot_state[symbol]["attempted"] = True
            _snapshot_state[symbol]["last_attempt"] = time.time()
            _snapshot_state[symbol]["retry_count"] += 1


def mark_snapshot_success(symbol: str):
    """Mark snapshot as successful"""
    with _state_lock:
        if symbol not in _snapshot_state:
            _snapshot_state[symbol] = {
                "attempted": True,
                "success": True,
                "failed": False,
                "last_attempt": time.time(),
                "retry_count": 0
            }
        else:
            _snapshot_state[symbol]["success"] = True
            _snapshot_state[symbol]["failed"] = False
            _snapshot_state[symbol]["last_attempt"] = time.time()


def mark_snapshot_failed(symbol: str):
    """Mark snapshot as failed"""
    with _state_lock:
        if symbol not in _snapshot_state:
            _snapshot_state[symbol] = {
                "attempted": True,
                "success": False,
                "failed": True,
                "last_attempt": time.time(),
                "retry_count": 1
            }
        else:
            _snapshot_state[symbol]["success"] = False
            _snapshot_state[symbol]["failed"] = True
            _snapshot_state[symbol]["last_attempt"] = time.time()
            _snapshot_state[symbol]["retry_count"] = _snapshot_state[symbol].get("retry_count", 0) + 1


def should_attempt_snapshot(symbol: str) -> bool:
    """
    Check if snapshot should be attempted for a symbol.
    
    Returns True if:
    - Never attempted before, OR
    - Failed and retry conditions are met (retry_count < MAX_RETRY_COUNT, last_attempt > RETRY_INTERVAL)
    
    Returns False if:
    - Already succeeded, OR
    - Already attempted and retry conditions not met
    """
    state = get_snapshot_state(symbol)
    
    # Never attempted - should attempt
    if not state["attempted"]:
        return True
    
    # Already succeeded - no need to retry
    if state["success"]:
        return False
    
    # Failed - check retry conditions
    if state["failed"]:
        retry_count = state.get("retry_count", 0)
        last_attempt = state.get("last_attempt", 0)
        age = time.time() - last_attempt
        
        # Can retry if: retry_count < MAX_RETRY_COUNT AND age > RETRY_INTERVAL
        if retry_count < MAX_RETRY_COUNT and age > RETRY_INTERVAL:
            return True
    
    # Otherwise, don't attempt
    return False


def reset_snapshot_state(symbol: str):
    """Reset snapshot state for a symbol (for manual retry)"""
    with _state_lock:
        if symbol in _snapshot_state:
            del _snapshot_state[symbol]
        logger.debug(f"📊 Reset snapshot state for {symbol}")


def get_all_snapshot_states() -> Dict[str, Dict[str, any]]:
    """Get all snapshot states (for debugging)"""
    with _state_lock:
        return _snapshot_state.copy()





