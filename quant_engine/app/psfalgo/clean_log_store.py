"""
CleanLog Store - Traceable, Account-Scoped Event Logging.

Persists structured events for "Explainability":
- Decision -> Reject/Intent -> Order -> Fill flows via `correlation_id`
- Negative path logging ("Why not?")
- Strict account isolation
"""

import json
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Literal
from enum import Enum

from app.core.logger import logger

class LogSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

class LogEvent(Enum):
    PROPOSAL = "PROPOSAL"
    REJECT = "REJECT"   # Filtered out (Negative decision)
    SKIP = "SKIP"       # Logic skipped (Negative decision)
    INTENT = "INTENT"
    ORDER = "ORDER"
    FILL = "FILL"
    ERROR = "ERROR"

class CleanLogStore:
    """
    Thread-safe store for structured clean logs.
    Persists to data/cleanlogs/{account_id}_{date}.jsonl
    """
    
    def __init__(self, data_dir: str = "data/cleanlogs"):
        self.data_dir = Path(data_dir)
        self._ensure_dir()
        self._lock = threading.Lock()
        
    def _ensure_dir(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_log_path(self, account_id: str, date_str: str) -> Path:
        """Get path for specific account and date"""
        # Partition by Account and Date for efficient storage/query
        return self.data_dir / f"{account_id}_{date_str}.jsonl"
    
    def log_event(self, 
                  account_id: str,
                  component: str,
                  event: str,
                  symbol: Optional[str],
                  message: str,
                  severity: str = "INFO",
                  correlation_id: Optional[str] = None,
                  details: Optional[Dict[str, Any]] = None):
        """
        Log a structured event.
        
        Args:
            account_id: Account ID (HAMPRO, IBKR_PED, etc)
            component: Component name (DECISION, ORDER_CTRL, etc)
            event: Event type (PROPOSAL, REJECT, SKIP, etc)
            symbol: Symbol (optional)
            message: Human readable summary
            severity: INFO, WARNING, CRITICAL
            correlation_id: Trace ID for full lifecycle
            details: dict with extra context (reason, metrics, etc)
        """
        if not account_id:
            logger.warning("[CLEANLOG] Attempted to log without account_id")
            return

        ts = datetime.now()
        date_str = ts.strftime("%Y%m%d")
        ts_iso = ts.isoformat()
        
        entry = {
            "timestamp": ts_iso,
            "account_id": account_id,
            "correlation_id": correlation_id,
            "component": component,
            "event": event,
            "severity": severity,
            "symbol": symbol,
            "message": message,
            "details": details or {}
        }
        
        def json_serial(obj):
            """JSON serializer for objects not serializable by default json code"""
            if isinstance(obj, datetime):
                return obj.isoformat()
            from enum import Enum
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, 'to_dict'):
                return obj.to_dict()
            raise TypeError (f"Type {type(obj)} not serializable")
        
        # Async write would be better for perf, but threading+append is safe enough for now
        # given the volume (algo ticks)
        try:
            with self._lock:
                path = self._get_log_path(account_id, date_str)
                with open(path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(entry, default=json_serial) + "\n")
        except Exception as e:
            logger.error(f"[CLEANLOG] Failed to write log: {e}", exc_info=True)

    def get_logs(self, 
                 account_id: str, 
                 date_str: Optional[str] = None, 
                 correlation_id: Optional[str] = None,
                 limit: int = 100) -> List[Dict[str, Any]]:
        """
        Query logs.
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y%m%d")
            
        logs = []
        path = self._get_log_path(account_id, date_str)
        
        if not path.exists():
            return []
            
        try:
            # Read last N lines efficiently? For now read all and filter (simple)
            # Todo: Implementation optimization for large files
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if correlation_id and entry.get('correlation_id') != correlation_id:
                            continue
                        logs.append(entry)
                    except:
                        continue
            
            # Sort by timestamp desc locally or rely on file order (asc)
            # Usually UI wants newest first
            logs.reverse()
            return logs[:limit]
            
        except Exception as e:
            logger.error(f"[CLEANLOG] Failed to read logs: {e}")
            return []

# Global Instance
_clean_log_store: Optional[CleanLogStore] = None

def get_clean_log_store() -> Optional[CleanLogStore]:
    return _clean_log_store

def initialize_clean_log_store(data_dir: str = "data/cleanlogs"):
    global _clean_log_store
    _clean_log_store = CleanLogStore(data_dir)
    logger.info(f"CleanLogStore initialized at {data_dir}")
