"""
PSFALGO Decision Models

Data models for decision engines and RUNALL orchestration.
All models are dataclasses for easy serialization and immutability.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List


# ============================================================================
# STATE ENUMS
# ============================================================================

class RunallState(str, Enum):
    """RUNALL global state"""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    WAITING = "WAITING"  # Waiting for decision engine
    BLOCKED = "BLOCKED"  # Blocked (exposure limit, etc.)
    CANCELLING = "CANCELLING"
    ERROR = "ERROR"


class CycleState(str, Enum):
    """RUNALL cycle sub-state"""
    INIT = "INIT"
    EXPOSURE_CHECK = "EXPOSURE_CHECK"
    KARBOTU_RUNNING = "KARBOTU_RUNNING"
    REDUCEMORE_RUNNING = "REDUCEMORE_RUNNING"
    ADDNEWPOS_CHECK = "ADDNEWPOS_CHECK"
    ADDNEWPOS_RUNNING = "ADDNEWPOS_RUNNING"
    STRATEGY_ORCHESTRATOR_RUNNING = "STRATEGY_ORCHESTRATOR_RUNNING"
    ORDER_SENDING = "ORDER_SENDING"
    WAITING_FOR_FILLS = "WAITING_FOR_FILLS"
    CANCELLING_ORDERS = "CANCELLING_ORDERS"
    METRICS_COLLECT = "METRICS_COLLECT"
    WAITING_NEXT = "WAITING_NEXT"


class RejectReason(str, Enum):
    """
    Standardized rejection reasons for visibility.
    """
    CRITICAL_METRIC_MISSING = "CRITICAL_METRIC_MISSING"
    INVALID_FAST_SCORE = "INVALID_FAST_SCORE"
    SPREAD_TOO_HIGH = "SPREAD_TOO_HIGH"
    AVG_ADV_TOO_LOW = "AVG_ADV_TOO_LOW"
    GROUP_LIMIT_REACHED = "GROUP_LIMIT_REACHED"
    EXISTING_POSITION_LIMIT = "EXISTING_POSITION_LIMIT"
    ISSUER_LIMIT_REACHED = "ISSUER_LIMIT_REACHED"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"
    VALUATION_TOO_POOR = "VALUATION_TOO_POOR"
    NOT_CHEAP_ENOUGH = "NOT_CHEAP_ENOUGH"
    NOT_EXPENSIVE_ENOUGH = "NOT_EXPENSIVE_ENOUGH"
    UNKNOWN = "UNKNOWN"


# ============================================================================
# PHASE 11: INTENT & SIGNAL MODELS
# ============================================================================

@dataclass
class Intent:
    """
    Standardized Action Intent (Phase 11).
    Replaces raw Decision objects for Execution routing.
    """
    symbol: str
    action: str              # SELL, COVER, BUY
    qty: int
    intent_category: str     # LT_TRIM_MICRO, KARBOTU_MACRO, REDUCEMORE_EMERGENCY
    priority: int            # 10=Micro, 20=Macro, 30=Risk, 40=Emergency
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata for execution
    id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class AnalysisSignal:
    """
    Generic Signal from Analyzers (Karbotu).
    """
    symbol: str
    eligibility: bool           # Can execution engine proceed?
    bias: float                 # -1.0 to 1.0 (Directional pressure)
    quality_bucket: str         # GOOD_LONG, BAD, etc.
    reason_codes: List[str]
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RiskMultiplier:
    """
    Risk Scaling Factor (Reducemore).
    """
    symbol: str
    value: float                # 1.0 (Normal) to N.0 (Aggressive)
    regime: str                 # NORMAL, DEFENSIVE, AGGRESSIVE
    reason: str


# ============================================================================
# EXPOSURE SNAPSHOT
# ============================================================================

@dataclass
class ExposureSnapshot:
    """
    Exposure snapshot - minimal but sufficient.
    
    Used for:
    - Mode determination (OFANSIF/DEFANSIF)
    - ADDNEWPOS eligibility check
    - Risk monitoring
    """
    pot_total: float  # Total exposure (sum of |qty| * price)
    pot_max: float  # Maximum exposure limit
    long_lots: float  # Total long lots
    short_lots: float  # Total short lots
    net_exposure: float  # long_lots - short_lots
    mode: str = 'OFANSIF'  # Exposure mode: OFANSIF (offensive) or DEFANSIF (defensive)
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def exposure_ratio(self) -> float:
        """Exposure ratio (pot_total / pot_max)"""
        if self.pot_max == 0:
            return 0.0
        return self.pot_total / self.pot_max
    
    @property
    def is_over_limit(self) -> bool:
        """Is exposure over limit?"""
        return self.pot_total >= self.pot_max
    
    @property
    def long_short_ratio(self) -> float:
        """Long/Short ratio"""
        if self.short_lots == 0:
            return float('inf') if self.long_lots > 0 else 0.0
        return self.long_lots / self.short_lots


# ============================================================================
# CYCLE METRICS
# ============================================================================

@dataclass
class CycleMetrics:
    """
    Cycle health metrics - minimal but sufficient.
    
    Used for:
    - Performance monitoring
    - Overrun detection
    - Error tracking
    """
    loop_count: int
    cycle_start_time: datetime
    cycle_duration_seconds: float
    exposure_snapshot: Optional[ExposureSnapshot] = None
    karbotu_decisions: int = 0
    reducemore_decisions: int = 0
    addnewpos_decisions: int = 0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def total_decisions(self) -> int:
        """Total decisions made in this cycle"""
        return self.karbotu_decisions + self.reducemore_decisions + self.addnewpos_decisions
    
    @property
    def is_overrun(self) -> bool:
        """Did cycle overrun? (duration > expected interval)"""
        # This is checked in runall_engine, but stored here for metrics
        return False  # Will be set by runall_engine


# ============================================================================
# DECISION REQUEST / RESPONSE
# ============================================================================

@dataclass
class DecisionRequest:
    """
    Decision request - input to decision engines.
    
    Decision engines are STATELESS - they only need this input.
    """
    positions: List[PositionSnapshot]  # Position snapshots (PositionSnapshot objects)
    metrics: Dict[str, SymbolMetrics]  # Symbol metrics (symbol -> SymbolMetrics object)
    exposure: Optional[ExposureSnapshot] = None
    cycle_count: int = 0
    available_symbols: Optional[List[str]] = None  # For ADDNEWPOS only
    l1_data: Dict[str, Any] = field(default_factory=dict) # L1 Data (Ladder, etc.)
    snapshot_ts: Optional[datetime] = None  # Snapshot timestamp (for consistency)
    correlation_id: Optional[str] = None  # Trace ID for CleanLogs


@dataclass
class Decision:
    """
    Single decision - output from decision engines.
    """
    symbol: str
    action: str  # "SELL", "BUY", "REDUCE", "ADD", "HOLD", "FILTERED"
    order_type: Optional[str] = None  # "ASK_SELL", "BID_BUY", etc.
    lot_percentage: Optional[float] = None  # %50, %25, etc.
    calculated_lot: Optional[int] = None  # Calculated lot amount
    price_hint: Optional[float] = None  # Price hint (GRPAN, RWVAP, etc.)
    step_number: Optional[int] = None  # Which step (for KARBOTU/REDUCEMORE)
    reason: str = ""  # Decision reason
    filtered_out: bool = False  # Was this filtered out?
    filter_reasons: List[str] = field(default_factory=list)  # Why filtered?
    confidence: float = 0.0  # Confidence score (0-1)
    metrics_used: Dict[str, float] = field(default_factory=dict)  # Metrics used
    
    # Shadow Visibility
    reject_reason_code: Optional[str] = None  # Enum value from RejectReason
    reject_reason_details: Dict[str, Any] = field(default_factory=dict)  # Detailed context (e.g. {value: 0.5, limit: 0.1})
    
    # CleanLogs Traceability
    correlation_id: Optional[str] = None  # Inherited from Request
    
    last_decision_ts: Optional[datetime] = None  # Last decision timestamp (for cooldown)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DecisionResponse:
    """
    Decision response - output from decision engines.
    
    Contains:
    - Decisions made
    - Filtered out positions
    - Explanation for each
    - Error message (if any)
    """
    decisions: List[Decision] = field(default_factory=list)
    filtered_out: List[Decision] = field(default_factory=list)
    step_summary: Dict[int, Dict[str, Any]] = field(default_factory=dict)  # Step-by-step summary
    total_decisions: int = 0
    total_filtered: int = 0
    execution_time_ms: float = 0.0
    error: Optional[str] = None  # Error message if decision engine failed
    correlation_id: Optional[str] = None  # Trace ID from request
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Calculate totals after initialization"""
        self.total_decisions = len(self.decisions)
        self.total_filtered = len(self.filtered_out)


# ============================================================================
# POSITION SNAPSHOT
# ============================================================================

class PositionPriceStatus(str, Enum):
    """Status of the market price used for valuation"""
    OK = "OK"                 # Valid price from market data
    NO_PRICE = "NO_PRICE"     # No price available (using 0.0 or last known)
    STALE = "STALE"           # Price is old (e.g. > 10 mins)


@dataclass
class PositionSnapshot:
    """
    Position snapshot - minimal but sufficient.
    
    Used by decision engines to make decisions.
    """
    symbol: str
    qty: float  # Broker Net Quantity (Positive=Long, Negative=Short)
    avg_price: float  # Average entry price
    current_price: float  # Current market price
    unrealized_pnl: float  # Unrealized P&L
    group: Optional[str] = None  # PRIMARY GROUP
    cgrup: Optional[str] = None  # SECONDARY GROUP (CGRUP)
    account_type: Optional[str] = None  # PHASE 10: HAMPRO, IBKR_GUN, IBKR_PED
    
    # Metadata & Metrics
    position_open_ts: Optional[datetime] = None  # When position was opened
    holding_minutes: float = 0.0  # How long position has been held (minutes)
    
    # Phase 7: Price Status
    price_status: str = PositionPriceStatus.OK  # OK, NO_PRICE, STALE
    
    # Phase 8: LT/MM Split & Netting (Optional until Phase 8 fully live)
    lt_qty_raw: float = 0.0       # Raw LT ledger quantity
    mm_qty_raw: float = 0.0       # Raw MM ledger quantity
    display_qty: Optional[float] = None    # Quantity to display (after netting)
    display_bucket: Optional[str] = None   # LT, MM, or MIXED
    view_mode: Optional[str] = None        # SINGLE_BUCKET, SPLIT_SAME_DIR, NETTED_OPPOSITE
    
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def is_long(self) -> bool:
        """Is this a long position?"""
        return self.qty > 0
    
    @property
    def is_short(self) -> bool:
        """Is this a short position?"""
        return self.qty < 0
    
    @property
    def pnl_percent(self) -> float:
        """P&L percentage"""
        if self.avg_price == 0:
            return 0.0
        return (self.current_price - self.avg_price) / self.avg_price * 100
    
    @property
    def holding_hours(self) -> float:
        """Holding time in hours"""
        return self.holding_minutes / 60.0
    
    @property
    def holding_days(self) -> float:
        """Holding time in days"""
        return self.holding_minutes / (60.0 * 24.0)


# ============================================================================
# SYMBOL METRICS
# ============================================================================

@dataclass
class SymbolMetrics:
    """
    Symbol metrics - all metrics needed for decision making.
    
    This is a snapshot at decision time.
    """
    symbol: str
    # Pricing
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    prev_close: Optional[float] = None
    spread: Optional[float] = None
    spread_percent: Optional[float] = None
    
    # GRPAN
    grpan_price: Optional[float] = None
    grpan_concentration_percent: Optional[float] = None
    grpan_ort_dev: Optional[float] = None  # GOD
    
    # RWVAP
    rwvap_1d: Optional[float] = None
    rwvap_ort_dev: Optional[float] = None  # ROD
    
    # Janall Metrics
    fbtot: Optional[float] = None
    sfstot: Optional[float] = None
    gort: Optional[float] = None
    sma63_chg: Optional[float] = None
    sma246_chg: Optional[float] = None
    
    # Pricing Overlay
    bid_buy_ucuzluk: Optional[float] = None
    ask_sell_pahalilik: Optional[float] = None
    front_buy_ucuzluk: Optional[float] = None
    front_sell_pahalilik: Optional[float] = None
    
    # Static
    avg_adv: Optional[float] = None
    final_thg: Optional[float] = None
    short_final: Optional[float] = None
    maxalw: Optional[int] = None  # Max allowed lot
    
    # JFIN Scores (for TUMCSV selection)
    final_bb_skor: Optional[float] = None   # Final Bid Buy score (for BB_LONG)
    final_fb_skor: Optional[float] = None   # Final Front Buy score (for FB_LONG)
    final_sas_skor: Optional[float] = None  # Final Ask Sell score (for SAS_SHORT)
    final_sfs_skor: Optional[float] = None  # Final Soft Front Sell score (for SFS_SHORT)
    
    timestamp: datetime = field(default_factory=datetime.now)

