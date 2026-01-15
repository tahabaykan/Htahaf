"""app/core/log_capture.py

Log Capture and Analysis System
================================

Captures all terminal logs (ERROR, WARNING, FAILED, etc.) and provides:
- Real-time log streaming
- Log filtering and search
- Log reporting (CSV/JSON export)
- Statistics and summaries
"""

import re
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import deque
import json

from app.core.logger import logger as app_logger


class LogLevel(Enum):
    """Log level enum"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogEntry:
    """Single log entry"""
    timestamp: datetime
    level: str
    module: str
    function: str
    line: int
    message: str
    raw_message: str  # Original log line
    
    # Extracted keywords
    keywords: List[str] = field(default_factory=list)
    
    # Error details (if applicable)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class LogCapture:
    """
    Log Capture System
    
    Intercepts all log messages and stores them for analysis and reporting.
    """
    
    _instance: Optional['LogCapture'] = None
    _lock = threading.Lock()
    
    # Keywords to detect important log types
    ERROR_KEYWORDS = ['error', 'failed', 'exception', 'traceback', 'critical', 'fatal']
    WARNING_KEYWORDS = ['warning', 'warn', 'deprecated', 'deprecation']
    FAILED_KEYWORDS = ['failed', 'failure', 'unsuccessful', 'aborted', 'timeout']
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize log capture"""
        if self._initialized:
            return
        
        # In-memory log storage (circular buffer - keeps last N logs)
        self._max_logs = 10000  # Keep last 10k logs
        self._logs: deque = deque(maxlen=self._max_logs)
        
        # Statistics
        self._stats = {
            'total': 0,
            'by_level': {level.value: 0 for level in LogLevel},
            'by_keyword': {},
            'errors': 0,
            'warnings': 0,
            'failed': 0,
            'start_time': datetime.now()
        }
        
        # Thread safety
        self._log_lock = threading.RLock()
        
        # WebSocket subscribers (for real-time streaming)
        self._subscribers: List[Any] = []  # Will store WebSocket connections
        
        self._initialized = True
        app_logger.info("📊 Log Capture System initialized")
    
    def capture_log(
        self,
        level: str,
        message: str,
        module: str = "",
        function: str = "",
        line: int = 0
    ) -> None:
        """
        Capture a log entry
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: Log message
            module: Module name
            function: Function name
            line: Line number
        """
        try:
            # Parse log message for keywords
            keywords = self._extract_keywords(message)
            
            # Detect error type
            error_type = None
            error_message = None
            if level.upper() in ['ERROR', 'CRITICAL']:
                error_type, error_message = self._extract_error_details(message)
            
            # Create log entry
            entry = LogEntry(
                timestamp=datetime.now(),
                level=level.upper(),
                module=module or "unknown",
                function=function or "unknown",
                line=line or 0,
                message=message,
                raw_message=message,
                keywords=keywords,
                error_type=error_type,
                error_message=error_message
            )
            
            # Store log
            with self._log_lock:
                self._logs.append(entry)
                
                # Update statistics
                self._stats['total'] += 1
                self._stats['by_level'][level.upper()] = self._stats['by_level'].get(level.upper(), 0) + 1
                
                # Count errors/warnings/failed
                if level.upper() in ['ERROR', 'CRITICAL']:
                    self._stats['errors'] += 1
                elif level.upper() == 'WARNING':
                    self._stats['warnings'] += 1
                
                # Check for "failed" keywords
                if any(kw in message.lower() for kw in self.FAILED_KEYWORDS):
                    self._stats['failed'] += 1
                
                # Update keyword stats
                for keyword in keywords:
                    self._stats['by_keyword'][keyword] = self._stats['by_keyword'].get(keyword, 0) + 1
            
            # Broadcast to WebSocket subscribers (real-time streaming)
            self._broadcast_to_subscribers(entry)
            
        except Exception as e:
            # Don't log errors in log capture to avoid infinite loop
            pass
    
    def _extract_keywords(self, message: str) -> List[str]:
        """Extract keywords from log message"""
        keywords = []
        message_lower = message.lower()
        
        # Check for error keywords
        for kw in self.ERROR_KEYWORDS:
            if kw in message_lower:
                keywords.append(kw)
        
        # Check for warning keywords
        for kw in self.WARNING_KEYWORDS:
            if kw in message_lower:
                keywords.append(kw)
        
        # Check for failed keywords
        for kw in self.FAILED_KEYWORDS:
            if kw in message_lower:
                keywords.append(kw)
        
        # Extract common patterns
        # Module names (e.g., "app.api.main")
        module_pattern = r'([a-z_]+\.[a-z_]+\.[a-z_]+)'
        modules = re.findall(module_pattern, message)
        keywords.extend(modules[:3])  # Max 3 modules
        
        return list(set(keywords))  # Remove duplicates
    
    def _extract_error_details(self, message: str) -> tuple[Optional[str], Optional[str]]:
        """Extract error type and message from log"""
        # Try to find error type (e.g., "ValueError", "ConnectionError")
        error_type_pattern = r'([A-Z][a-zA-Z]*Error|Exception)'
        error_match = re.search(error_type_pattern, message)
        error_type = error_match.group(1) if error_match else None
        
        # Try to extract error message (after colon)
        if ':' in message:
            parts = message.split(':', 1)
            if len(parts) > 1:
                error_message = parts[1].strip()[:200]  # Limit length
            else:
                error_message = None
        else:
            error_message = message[:200] if len(message) > 200 else message
        
        return error_type, error_message
    
    def _broadcast_to_subscribers(self, entry: LogEntry) -> None:
        """Broadcast log entry to WebSocket subscribers"""
        if not self._subscribers:
            return
        
        try:
            entry_dict = entry.to_dict()
            # Remove closed connections
            active_subscribers = []
            for subscriber in self._subscribers:
                try:
                    subscriber.send_json(entry_dict)
                    active_subscribers.append(subscriber)
                except Exception:
                    pass  # Connection closed
            
            self._subscribers = active_subscribers
        except Exception:
            pass  # Don't fail on broadcast errors
    
    def get_logs(
        self,
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get filtered logs
        
        Args:
            level: Filter by log level
            keyword: Filter by keyword
            module: Filter by module
            limit: Maximum number of logs to return
            offset: Offset for pagination
            
        Returns:
            List of log entries as dictionaries
        """
        with self._log_lock:
            logs = list(self._logs)
        
        # Apply filters
        filtered_logs = logs
        
        if level:
            filtered_logs = [log for log in filtered_logs if log.level == level.upper()]
        
        if keyword:
            keyword_lower = keyword.lower()
            filtered_logs = [
                log for log in filtered_logs
                if keyword_lower in log.message.lower() or
                   keyword_lower in ' '.join(log.keywords).lower() or
                   (log.error_type and keyword_lower in log.error_type.lower())
            ]
        
        if module:
            module_lower = module.lower()
            filtered_logs = [
                log for log in filtered_logs
                if module_lower in log.module.lower()
            ]
        
        # Sort by timestamp (newest first)
        filtered_logs.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Apply pagination
        paginated_logs = filtered_logs[offset:offset + limit]
        
        return [log.to_dict() for log in paginated_logs]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get log statistics"""
        with self._log_lock:
            uptime = (datetime.now() - self._stats['start_time']).total_seconds()
            
            return {
                'total_logs': self._stats['total'],
                'by_level': self._stats['by_level'].copy(),
                'errors': self._stats['errors'],
                'warnings': self._stats['warnings'],
                'failed': self._stats['failed'],
                'by_keyword': dict(sorted(
                    self._stats['by_keyword'].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:20]),  # Top 20 keywords
                'uptime_seconds': uptime,
                'logs_per_second': self._stats['total'] / uptime if uptime > 0 else 0,
                'start_time': self._stats['start_time'].isoformat()
            }
    
    def export_logs(
        self,
        format: str = 'json',
        level: Optional[str] = None,
        keyword: Optional[str] = None,
        module: Optional[str] = None
    ) -> str:
        """
        Export logs to CSV or JSON
        
        Args:
            format: 'json' or 'csv'
            level: Filter by level
            keyword: Filter by keyword
            module: Filter by module
            
        Returns:
            Exported logs as string
        """
        logs = self.get_logs(level=level, keyword=keyword, module=module, limit=10000)
        
        if format.lower() == 'json':
            return json.dumps(logs, indent=2, default=str)
        
        elif format.lower() == 'csv':
            import csv
            from io import StringIO
            
            output = StringIO()
            if logs:
                writer = csv.DictWriter(output, fieldnames=[
                    'timestamp', 'level', 'module', 'function', 'line',
                    'message', 'keywords', 'error_type', 'error_message'
                ])
                writer.writeheader()
                
                for log in logs:
                    # Flatten keywords list
                    log_copy = log.copy()
                    log_copy['keywords'] = ', '.join(log.get('keywords', []))
                    writer.writerow(log_copy)
            
            return output.getvalue()
        
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def clear_logs(self) -> None:
        """Clear all logs"""
        with self._log_lock:
            self._logs.clear()
            self._stats = {
                'total': 0,
                'by_level': {level.value: 0 for level in LogLevel},
                'by_keyword': {},
                'errors': 0,
                'warnings': 0,
                'failed': 0,
                'start_time': datetime.now()
            }
    
    def add_subscriber(self, websocket_connection: Any) -> None:
        """Add WebSocket subscriber for real-time log streaming"""
        with self._log_lock:
            if websocket_connection not in self._subscribers:
                self._subscribers.append(websocket_connection)
    
    def remove_subscriber(self, websocket_connection: Any) -> None:
        """Remove WebSocket subscriber"""
        with self._log_lock:
            if websocket_connection in self._subscribers:
                self._subscribers.remove(websocket_connection)


# Global instance
_log_capture: Optional[LogCapture] = None


def get_log_capture() -> LogCapture:
    """Get global log capture instance"""
    global _log_capture
    if _log_capture is None:
        _log_capture = LogCapture()
    return _log_capture


def setup_log_capture() -> None:
    """Setup log capture by intercepting loguru logger"""
    try:
        from loguru import logger as loguru_logger
        
        log_capture = get_log_capture()
        
        def log_sink(message):
            """Custom sink to capture all logs"""
            try:
                record = message.record
                log_capture.capture_log(
                    level=record["level"].name,
                    message=record["message"],
                    module=record["name"],
                    function=record["function"],
                    line=record["line"]
                )
            except Exception:
                pass  # Don't fail on capture errors
        
        # Add custom sink (level="DEBUG" to capture all logs)
        loguru_logger.add(log_sink, level="DEBUG", format="{message}")
        app_logger.info("✅ Log capture sink added to loguru - all terminal logs will be captured")
        
    except ImportError:
        app_logger.warning("⚠️ Loguru not available - log capture may be limited")
    except Exception as e:
        app_logger.error(f"❌ Failed to setup log capture: {e}", exc_info=True)

