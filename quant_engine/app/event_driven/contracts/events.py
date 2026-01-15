"""
Event Contract Definitions

All events in the system follow a common structure with:
- event_id: Unique identifier
- event_type: Type of event
- timestamp: Unix epoch nanoseconds
- idempotency_key: For deduplication
- data: Event-specific payload
"""

import time
import uuid
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime


class OrderClassification(str, Enum):
    """Order/Intent classification - 8 semantic classes"""
    MM_LONG_INCREASE = "MM_LONG_INCREASE"
    MM_LONG_DECREASE = "MM_LONG_DECREASE"
    MM_SHORT_INCREASE = "MM_SHORT_INCREASE"
    MM_SHORT_DECREASE = "MM_SHORT_DECREASE"
    LT_LONG_INCREASE = "LT_LONG_INCREASE"
    LT_LONG_DECREASE = "LT_LONG_DECREASE"
    LT_SHORT_INCREASE = "LT_SHORT_INCREASE"
    LT_SHORT_DECREASE = "LT_SHORT_DECREASE"
    
    @classmethod
    def from_components(cls, bucket: str, direction: str, effect: str) -> "OrderClassification":
        """Create classification from components"""
        bucket_upper = bucket.upper()
        dir_upper = direction.upper()
        effect_upper = effect.upper()
        name = f"{bucket_upper}_{dir_upper}_{effect_upper}"
        return cls[name]
    
    @property
    def bucket(self) -> str:
        """Extract bucket (LT or MM)"""
        return self.value.split("_")[0]
    
    @property
    def direction(self) -> str:
        """Extract direction (LONG or SHORT)"""
        return self.value.split("_")[1]
    
    @property
    def effect(self) -> str:
        """Extract effect (INCREASE or DECREASE)"""
        return self.value.split("_")[2]
    
    @property
    def is_risk_increasing(self) -> bool:
        """Check if this classification is risk-increasing"""
        return self.effect == "INCREASE"


class EventType(str, Enum):
    """Event type enumeration"""
    L1 = "l1"
    PRINT = "print"
    FEATURE = "feature"
    ALERT = "alert"
    POSITION = "position"
    EXPOSURE = "exposure"
    SESSION = "session"
    ORDER = "order"
    INTENT = "intent"


@dataclass
class BaseEvent:
    """Base event structure"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    timestamp: int = field(default_factory=lambda: int(time.time_ns()))
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis Stream"""
        return asdict(self)
    
    def to_redis_stream(self) -> Dict[str, str]:
        """Convert to Redis Stream format (all values as strings)"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": str(self.timestamp),
            "idempotency_key": self.idempotency_key,
            "data": self._serialize_data(self.data)
        }
    
    @staticmethod
    def _serialize_data(data: Dict[str, Any]) -> str:
        """Serialize data dict to JSON string"""
        import json
        return json.dumps(data)
    
    @classmethod
    def from_redis_stream(cls, stream_data: Dict[str, str]) -> "BaseEvent":
        """Create event from Redis Stream data"""
        import json
        data_str = stream_data.get("data", "{}")
        try:
            data = json.loads(data_str) if isinstance(data_str, str) else data_str
        except (json.JSONDecodeError, TypeError):
            data = {}
        return cls(
            event_id=stream_data.get("event_id", ""),
            event_type=stream_data.get("event_type", ""),
            timestamp=int(stream_data.get("timestamp", 0)),
            idempotency_key=stream_data.get("idempotency_key", ""),
            data=data
        )


@dataclass
class L1Event(BaseEvent):
    """Level 1 market data event"""
    event_type: str = EventType.L1
    
    @staticmethod
    def create(symbol: str, bid: float, ask: float, bid_size: int, ask_size: int,
               last_price: Optional[float] = None, last_size: Optional[int] = None,
               timestamp: Optional[int] = None) -> "L1Event":
        """Create L1 event"""
        return L1Event(
            timestamp=timestamp or int(time.time_ns()),
            data={
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "bid_size": bid_size,
                "ask_size": ask_size,
                "last_price": last_price,
                "last_size": last_size,
            }
        )


@dataclass
class PrintEvent(BaseEvent):
    """Trade print event"""
    event_type: str = EventType.PRINT
    
    @staticmethod
    def create(symbol: str, price: float, size: int, venue: str,
               timestamp: Optional[int] = None) -> "PrintEvent":
        """Create print event"""
        return PrintEvent(
            timestamp=timestamp or int(time.time_ns()),
            data={
                "symbol": symbol,
                "price": price,
                "size": size,
                "venue": venue,
            }
        )


@dataclass
class FeatureEvent(BaseEvent):
    """GRPAN/dominant price feature event"""
    event_type: str = EventType.FEATURE
    
    @staticmethod
    def create(symbol: str, dominant_price: float, volume_weighted_price: float,
               print_count: int, timestamp: Optional[int] = None) -> "FeatureEvent":
        """Create feature event"""
        return FeatureEvent(
            timestamp=timestamp or int(time.time_ns()),
            data={
                "symbol": symbol,
                "dominant_price": dominant_price,
                "volume_weighted_price": volume_weighted_price,
                "print_count": print_count,
            }
        )


@dataclass
class AlertEvent(BaseEvent):
    """Alert/notification event"""
    event_type: str = EventType.ALERT
    
    @staticmethod
    def create(alert_type: str, message: str, symbol: Optional[str] = None,
               severity: str = "info", timestamp: Optional[int] = None) -> "AlertEvent":
        """Create alert event"""
        return AlertEvent(
            timestamp=timestamp or int(time.time_ns()),
            data={
                "alert_type": alert_type,
                "message": message,
                "symbol": symbol,
                "severity": severity,  # info, warning, error, critical
            }
        )


@dataclass
class PositionEvent(BaseEvent):
    """Position update event"""
    event_type: str = EventType.POSITION
    
    @staticmethod
    def create(
        symbol: str,
        quantity: int,
        avg_price: float,
        notional: float,
        befday_qty: Optional[int] = None,
        befday_cost: Optional[float] = None,
        intraday_qty_delta: Optional[int] = None,
        intraday_avg_fill_price: Optional[float] = None,
        account_id: Optional[str] = None,
        timestamp: Optional[int] = None
    ) -> "PositionEvent":
        """Create position event with BefDay baseline data"""
        return PositionEvent(
            timestamp=timestamp or int(time.time_ns()),
            data={
                "symbol": symbol,
                "quantity": quantity,  # Positive = long, negative = short
                "avg_price": avg_price,
                "notional": notional,  # abs(quantity * avg_price)
                "befday_qty": befday_qty,  # Baseline quantity at market open
                "befday_cost": befday_cost,  # Baseline cost (prev_close)
                "intraday_qty_delta": intraday_qty_delta or (quantity - (befday_qty or 0)),  # Change since open
                "intraday_avg_fill_price": intraday_avg_fill_price,  # Avg fill price for today's fills
                "account_id": account_id,  # Account ID (HAMMER, IBKR_GUN, IBKR_PED)
            }
        )


@dataclass
class ExposureEvent(BaseEvent):
    """Exposure snapshot event (published every 15s)"""
    event_type: str = EventType.EXPOSURE
    
    @staticmethod
    def create(
        equity: float,
        long_notional: float,
        short_notional: float,
        gross_exposure_pct: float,
        net_exposure_pct: float,
        long_gross_pct: float,  # long_notional / equity * 100
        short_gross_pct: float,  # short_notional / equity * 100
        buckets: Dict[str, Dict[str, float]],  # {bucket_name: {current, potential, target, max, current_pct, potential_pct}}
        group_exposure: Dict[str, float],  # {group_name: exposure_pct} for 22 groups
        positions: List[Dict[str, Any]],  # List of position summaries
        open_orders_potential: Optional[float] = None,  # Potential exposure from open orders
        timestamp: Optional[int] = None
    ) -> "ExposureEvent":
        """Create exposure event"""
        return ExposureEvent(
            timestamp=timestamp or int(time.time_ns()),
            data={
                "equity": equity,
                "long_notional": long_notional,
                "short_notional": short_notional,
                "gross_exposure_pct": gross_exposure_pct,
                "net_exposure_pct": net_exposure_pct,
                "long_gross_pct": long_gross_pct,
                "short_gross_pct": short_gross_pct,
                "buckets": buckets,
                "group_exposure": group_exposure,
                "positions": positions,
                "open_orders_potential": open_orders_potential or 0.0,
            }
        )


@dataclass
class SessionEvent(BaseEvent):
    """Session clock event (published every 1s)"""
    event_type: str = EventType.SESSION
    
    @staticmethod
    def create(
        regime: str,  # OPEN, EARLY, MID, LATE, CLOSE
        market_open: bool,
        minutes_to_close: Optional[int] = None,
        current_time: Optional[str] = None,
        timestamp: Optional[int] = None
    ) -> "SessionEvent":
        """Create session event"""
        return SessionEvent(
            timestamp=timestamp or int(time.time_ns()),
            data={
                "regime": regime,
                "market_open": market_open,
                "minutes_to_close": minutes_to_close,
                "current_time": current_time or datetime.utcnow().isoformat(),
            }
        )


@dataclass
class OrderEvent(BaseEvent):
    """Order update event (from Execution Service)"""
    event_type: str = EventType.ORDER
    
    @staticmethod
    def create(
        order_id: str,
        symbol: str,
        action: str,  # ACCEPTED, WORKING, PARTIAL_FILL, FILLED, CANCELED, REJECTED
        quantity: int,
        order_type: str,  # MARKET, LIMIT, etc.
        classification: str,  # OrderClassification enum value (preserved from intent)
        bucket: str,  # LT or MM
        effect: str,  # INCREASE or DECREASE
        dir: str,  # LONG or SHORT
        risk_delta_notional: float,  # Estimated worst-case change if filled
        risk_delta_gross_pct: float,  # Estimated worst-case gross exposure change
        position_context_at_intent: Dict[str, Any],  # Snapshot from intent
        limit_price: Optional[float] = None,
        filled_quantity: Optional[int] = None,
        avg_fill_price: Optional[float] = None,
        status: Optional[str] = None,
        intent_id: Optional[str] = None,  # Link back to intent
        order_action: Optional[str] = None,  # BUY or SELL (for PnL calculation)
        account_id: Optional[str] = None,  # Account ID (HAMMER, IBKR_GUN, IBKR_PED)
        metadata: Optional[Dict[str, Any]] = None,  # Additional metadata (fill_id, event_id, etc.)
        timestamp: Optional[int] = None
    ) -> "OrderEvent":
        """Create order event with classification"""
        return OrderEvent(
            timestamp=timestamp or int(time.time_ns()),
            data={
                "order_id": order_id,
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "order_type": order_type,
                "classification": classification,
                "bucket": bucket,
                "effect": effect,
                "dir": dir,
                "risk_delta_notional": risk_delta_notional,
                "risk_delta_gross_pct": risk_delta_gross_pct,
                "position_context_at_intent": position_context_at_intent,
                "limit_price": limit_price,
                "filled_quantity": filled_quantity,
                "avg_fill_price": avg_fill_price,
                "status": status,
                "intent_id": intent_id,
                "order_action": order_action,  # BUY or SELL
                "account_id": account_id,  # Account ID
                "metadata": metadata or {},
            }
        )


@dataclass
class IntentEvent(BaseEvent):
    """Trading intent from Decision Engine"""
    event_type: str = EventType.INTENT
    
    @staticmethod
    def create(
        intent_type: str,  # DERISK_SOFT, DERISK_HARD, REDUCE, INCREASE, HOLD
        symbol: str,
        action: str,  # BUY, SELL
        quantity: int,
        reason: str,
        classification: str,  # OrderClassification enum value
        bucket: str,  # LT or MM
        effect: str,  # INCREASE or DECREASE
        dir: str,  # LONG or SHORT
        risk_delta_notional: float,  # Estimated worst-case change if filled
        risk_delta_gross_pct: float,  # Estimated worst-case gross exposure change
        position_context_at_intent: Dict[str, Any],  # {current_qty, avg_fill_price}
        priority: int = 0,  # Higher = more urgent
        limit_price: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[int] = None
    ) -> "IntentEvent":
        """Create intent event with classification"""
        return IntentEvent(
            timestamp=timestamp or int(time.time_ns()),
            data={
                "intent_type": intent_type,
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "reason": reason,
                "classification": classification,
                "bucket": bucket,
                "effect": effect,
                "dir": dir,
                "risk_delta_notional": risk_delta_notional,
                "risk_delta_gross_pct": risk_delta_gross_pct,
                "position_context_at_intent": position_context_at_intent,
                "priority": priority,
                "limit_price": limit_price,
                "metadata": metadata or {},
            }
        )

