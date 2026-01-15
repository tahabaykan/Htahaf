from typing import List, Dict, Optional, Any
from collections import deque
from datetime import datetime
import threading
from app.psfalgo.decision_models import Decision, RejectReason

class RejectReasonStore:
    """
    In-memory store for recent rejection reasons (Shadow/Ghost proposals).
    Used to provide visibility into why candidates were filtered out.
    """
    
    def __init__(self, max_size: int = 2000):
        self._store = deque(maxlen=max_size)
        self._lock = threading.RLock()
        
    def add(self, decision: Decision):
        """Add a rejected decision to the store"""
        if not decision.filtered_out:
            return
            
        with self._lock:
            # Create a lightweight summary
            entry = {
                'symbol': decision.symbol,
                'action': decision.action,
                'code': decision.reject_reason_code or RejectReason.UNKNOWN,
                'details': decision.reject_reason_details,
                'timestamp': decision.timestamp.isoformat(),
                'engine': 'ADDNEWPOS' # Can be parameterized if needed
            }
            self._store.append(entry)
            
    def get_latest(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get latest rejections"""
        with self._lock:
            # Convert to list effectively
            return list(self._store)[-limit:][::-1] # Reverse to show newest first

    def clear(self):
        with self._lock:
            self._store.clear()

# Global Instance
_reject_reason_store: Optional[RejectReasonStore] = None

def get_reject_reason_store() -> RejectReasonStore:
    """Get or create global instance"""
    global _reject_reason_store
    if _reject_reason_store is None:
        _reject_reason_store = RejectReasonStore()
    return _reject_reason_store
