"""
Execution Models - Production-Grade

Data models for execution layer (Phase 4).
Maps DecisionResponse → ExecutionIntent → Order Plan.

Key Principles:
- Read-only from decision layer (no feedback)
- Idempotent (same decision → same order set)
- Deduplication (decision timestamp + cycle_id)
- Dry-run support
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class ExecutionStatus(Enum):
    """Execution status"""
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class OrderSide(Enum):
    """Order side"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order type"""
    LIMIT = "LIMIT"
    MARKET = "MARKET"


@dataclass
class ExecutionIntent:
    """
    Execution Intent - maps Decision to executable order plan.
    
    This is the bridge between decision layer and execution layer.
    One Decision → One ExecutionIntent → One or more Orders.
    """
    symbol: str
    side: OrderSide  # BUY or SELL
    quantity: int  # Lot amount (always positive)
    order_type: OrderType  # LIMIT or MARKET
    price: Optional[float] = None  # Limit price (if LIMIT order)
    price_hint: Optional[float] = None  # Price hint from decision (GRPAN, RWVAP, etc.)
    
    # Decision tracking (for deduplication)
    decision_timestamp: datetime = field(default_factory=datetime.now)
    cycle_id: int = 0  # RUNALL cycle count
    decision_source: str = ""  # "KARBOTU", "REDUCEMORE", "ADDNEWPOS"
    decision_reason: str = ""  # Decision reason (for logging)
    decision_confidence: float = 0.0  # Decision confidence (0-1)
    
    # Execution tracking
    status: ExecutionStatus = ExecutionStatus.PENDING
    execution_timestamp: Optional[datetime] = None
    order_id: Optional[str] = None  # Broker order ID (if executed)
    error: Optional[str] = None
    
    # Deduplication key
    dedup_key: str = field(default="")  # decision_timestamp + cycle_id + symbol + side
    
    def __post_init__(self):
        """Generate deduplication key"""
        if not self.dedup_key:
            self.dedup_key = f"{self.decision_timestamp.isoformat()}_{self.cycle_id}_{self.symbol}_{self.side.value}"


@dataclass
class ExecutionPlan:
    """
    Execution Plan - collection of ExecutionIntents for a cycle.
    
    This is the output of ExecutionEngine for a single cycle.
    """
    cycle_id: int
    cycle_timestamp: datetime
    intents: List[ExecutionIntent] = field(default_factory=list)
    dry_run: bool = True
    total_intents: int = 0
    skipped_intents: int = 0
    error_intents: int = 0
    
    def __post_init__(self):
        """Calculate totals"""
        self.total_intents = len(self.intents)
        self.skipped_intents = sum(1 for i in self.intents if i.status == ExecutionStatus.SKIPPED)
        self.error_intents = sum(1 for i in self.intents if i.status == ExecutionStatus.ERROR)


@dataclass
class OrderDeduplicationRecord:
    """
    Order deduplication record - tracks executed orders to prevent duplicates.
    """
    dedup_key: str
    symbol: str
    side: OrderSide
    quantity: int
    cycle_id: int
    decision_timestamp: datetime
    execution_timestamp: datetime
    order_id: Optional[str] = None







