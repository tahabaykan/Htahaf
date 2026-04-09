"""
Decision Logger - Central logging for all engine decisions

Logs to:
1. Console (via Loguru)
2. Redis (structured data with audit trail)
3. UI notifications (via Redis Pub/Sub)

Provides full transparency on:
- Why orders were sent
- Why orders were blocked
- Which limits were hit
- Filter pass/fail details
"""
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field, asdict

from loguru import logger


class DecisionType(Enum):
    """Type of decision"""
    ORDER_SENT = "ORDER_SENT"           # Emir gönderildi
    ORDER_BLOCKED = "ORDER_BLOCKED"     # Emir bloke edildi
    ORDER_ADJUSTED = "ORDER_ADJUSTED"   # Miktar ayarlandı
    FILTER_FAILED = "FILTER_FAILED"     # Filter geçilmedi
    LIMIT_HIT = "LIMIT_HIT"             # Limit'e takıldı
    ENGINE_SKIPPED = "ENGINE_SKIPPED"   # Engine skip edildi
    VETO = "VETO"                       # Engine veto etti


class BlockReason(Enum):
    """Blocking reasons"""
    MAXALW_EXCEEDED = "MAXALW_EXCEEDED"
    BEFDAY_LIMIT = "BEFDAY_LIMIT"
    PORTFOLIO_PCT = "PORTFOLIO_PCT"
    DAILY_LIMIT = "DAILY_LIMIT"
    GORT_FILTER = "GORT_FILTER"
    FBTOT_FILTER = "FBTOT_FILTER"
    SFSTOT_FILTER = "SFSTOT_FILTER"
    SMA63CHG_FILTER = "SMA63CHG_FILTER"
    PAHALILIK_FILTER = "PAHALILIK_FILTER"
    UCUZLUK_FILTER = "UCUZLUK_FILTER"
    EXPOSURE_HIGH = "EXPOSURE_HIGH"
    NO_METRICS = "NO_METRICS"
    KARBOTU_VETO = "KARBOTU_VETO"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    POTENTIAL_MAXALW = "POTENTIAL_MAXALW"
    POTENTIAL_EXPOSURE = "POTENTIAL_EXPOSURE"


@dataclass
class DecisionLog:
    """Single decision log entry"""
    # Identity
    cycle_id: str
    timestamp: str
    symbol: str
    engine: str  # LT_TRIM, KARBOTU_V2, ADDNEWPOS, etc.
    
    # Decision
    decision_type: str  # ORDER_SENT, ORDER_BLOCKED, etc.
    action: Optional[str] = None  # BUY, SELL
    qty: Optional[int] = None
    price: Optional[float] = None
    tag: Optional[str] = None
    
    # Blocking/Filter info
    block_reason: Optional[str] = None
    block_details: Dict[str, Any] = field(default_factory=dict)
    
    # Context (BEFDAY, MAXALW, etc.)
    context: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata (config, filters, etc.)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dict for JSON serialization"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), default=str)


class DecisionLogger:
    """
    Central decision logging service
    
    Features:
    - Log all engine decisions
    - Store to Redis (queryable audit trail)
    - Publish to UI (real-time notifications)
    - Console output (debugging)
    
    Usage:
        decision_logger = get_decision_logger()
        decision_logger.set_cycle_id("2026-01-18T18:45:00")
        
        decision_logger.log_decision(
            symbol='SOJD',
            engine='KARBOTU_V2',
            decision_type=DecisionType.ORDER_SENT,
            action='SELL',
            qty=500,
            tag='LT_LONG_DECREASE',
            context={'fbtot': 1.05, 'step': 2}
        )
    """
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.current_cycle_id = None
        logger.info("[DecisionLogger] Initialized")
    
    def set_cycle_id(self, cycle_id: str):
        """Set current cycle ID for grouping decisions"""
        self.current_cycle_id = cycle_id
        logger.debug(f"[DecisionLogger] Cycle ID set: {cycle_id}")
    
    def log_decision(
        self,
        symbol: str,
        engine: str,
        decision_type: DecisionType,
        action: Optional[str] = None,
        qty: Optional[int] = None,
        price: Optional[float] = None,
        tag: Optional[str] = None,
        block_reason: Optional[BlockReason] = None,
        block_details: Optional[Dict] = None,
        context: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Log a decision
        
        Args:
            symbol: Stock symbol
            engine: Engine name (LT_TRIM, KARBOTU_V2, INTRACON, etc.)
            decision_type: Type of decision
            action: BUY or SELL
            qty: Quantity
            price: Price
            tag: Order tag (LT_LONG_DECREASE, etc.)
            block_reason: Reason for blocking (if blocked)
            block_details: Additional blocking details (limits, thresholds, etc.)
            context: Context data (BEFDAY, MAXALW, current_qty, etc.)
            metadata: Additional metadata (filter config, step info, etc.)
        """
        log_entry = DecisionLog(
            cycle_id=self.current_cycle_id or "UNKNOWN",
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            engine=engine,
            decision_type=decision_type.value,
            action=action,
            qty=qty,
            price=price,
            tag=tag,
            block_reason=block_reason.value if block_reason else None,
            block_details=block_details or {},
            context=context or {},
            metadata=metadata or {}
        )
        
        # 1. Console logging
        self._log_to_console(log_entry)
        
        # 2. Redis storage
        self._log_to_redis(log_entry)
        
        # 3. UI notification
        self._notify_ui(log_entry)
    
    def _log_to_console(self, log: DecisionLog):
        """Log to console with emoji indicators"""
        if log.decision_type == DecisionType.ORDER_SENT.value:
            logger.info(
                f"[{log.engine}] ✅ {log.symbol} {log.action} {log.qty} "
                f"@ ${log.price:.2f} ({log.tag})"
            )
            # Add context if available
            if log.context:
                context_str = ", ".join([f"{k}={v}" for k, v in log.context.items() if k not in ['data_sources']])
                if context_str:
                    logger.debug(f"  Context: {context_str}")
        
        elif log.decision_type == DecisionType.ORDER_BLOCKED.value:
            logger.warning(
                f"[{log.engine}] ❌ {log.symbol} BLOCKED: {log.block_reason}"
            )
            if log.block_details:
                details_str = ", ".join([f"{k}={v}" for k, v in log.block_details.items()])
                logger.warning(f"  Details: {details_str}")
        
        elif log.decision_type == DecisionType.ORDER_ADJUSTED.value:
            logger.info(
                f"[{log.engine}] ⚠️ {log.symbol} ADJUSTED: {log.qty} lots "
                f"(Reason: {log.block_reason})"
            )
            if log.block_details:
                logger.debug(f"  Details: {log.block_details}")
        
        elif log.decision_type == DecisionType.FILTER_FAILED.value:
            logger.debug(
                f"[{log.engine}] 🔍 {log.symbol} FILTER FAILED: {log.block_reason}"
            )
            if log.block_details and logger.level < 20:  # DEBUG level
                logger.debug(f"  Details: {log.block_details}")
        
        elif log.decision_type == DecisionType.VETO.value:
            logger.info(
                f"[{log.engine}] 🛑 {log.symbol} VETO: {log.block_reason}"
            )
    
    def _log_to_redis(self, log: DecisionLog):
        """Log to Redis for persistence and querying"""
        if not self.redis_client:
            return
        
        try:
            # Store in Redis Stream (by cycle)
            stream_key = f"psfalgo:decisions:{log.cycle_id}"
            self.redis_client.sync.xadd(
                stream_key,
                {k: str(v) for k, v in log.to_dict().items()},
                maxlen=1000  # Keep last 1000 decisions per cycle
            )
            
            # Set TTL on stream (7 days)
            self.redis_client.sync.expire(stream_key, 86400 * 7)
            
            # Store in sorted set for per-symbol querying
            zset_key = f"psfalgo:decisions:by_symbol:{log.symbol}"
            score = datetime.fromisoformat(log.timestamp).timestamp()
            self.redis_client.sync.zadd(
                zset_key,
                {log.to_json(): score}
            )
            self.redis_client.sync.expire(zset_key, 86400 * 7)  # 7 days
            
            logger.debug(f"[DecisionLogger] Logged to Redis: {log.symbol} ({log.decision_type})")
        
        except Exception as e:
            logger.error(f"[DecisionLogger] Redis log error: {e}", exc_info=True)
    
    def _notify_ui(self, log: DecisionLog):
        """Publish to Redis Pub/Sub for real-time UI notifications"""
        if not self.redis_client:
            return
        
        try:
            channel = "psfalgo:notifications"
            message = {
                'type': 'decision',
                'symbol': log.symbol,
                'engine': log.engine,
                'decision_type': log.decision_type,
                'action': log.action,
                'qty': log.qty,
                'price': log.price,
                'tag': log.tag,
                'block_reason': log.block_reason,
                'timestamp': log.timestamp,
                'cycle_id': log.cycle_id
            }
            
            self.redis_client.sync.publish(channel, json.dumps(message, default=str))
            logger.debug(f"[DecisionLogger] Published to UI: {log.symbol}")
        
        except Exception as e:
            logger.error(f"[DecisionLogger] UI notification error: {e}", exc_info=True)
    
    def log_cycle_summary(
        self,
        engine: str,
        summary: Dict[str, Any]
    ):
        """Log cycle-level summary"""
        logger.info("=" * 80)
        logger.info(f"[{engine} SUMMARY] Cycle: {self.current_cycle_id}")
        for key, value in summary.items():
            logger.info(f"  {key}: {value}")
        logger.info("=" * 80)
        
        # Store summary to Redis
        if self.redis_client:
            try:
                key = f"psfalgo:cycle_summary:{self.current_cycle_id}:{engine}"
                self.redis_client.sync.setex(
                    key,
                    86400 * 7,  # 7 days
                    json.dumps(summary, default=str)
                )
            except Exception as e:
                logger.error(f"[DecisionLogger] Summary storage error: {e}")


# Global instance
_decision_logger: Optional[DecisionLogger] = None


def get_decision_logger() -> DecisionLogger:
    """Get global decision logger instance"""
    global _decision_logger
    if _decision_logger is None:
        try:
            from app.core.redis_client import get_redis_client
            redis_client = get_redis_client()
        except Exception as e:
            logger.warning(f"[DecisionLogger] Redis client unavailable: {e}")
            redis_client = None
        
        _decision_logger = DecisionLogger(redis_client=redis_client)
    
    return _decision_logger


def initialize_decision_logger(redis_client=None):
    """Initialize global decision logger with Redis client"""
    global _decision_logger
    _decision_logger = DecisionLogger(redis_client=redis_client)
    logger.info("[DecisionLogger] Initialized with Redis client")
    return _decision_logger
