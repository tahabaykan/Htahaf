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
    DATA_INCOMPLETE = "DATA_INCOMPLETE"  # Fbtot/SFStot/GORT/SMA = 0 or None
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
    engine_name: Optional[str] = None  # Engine that created this intent (for UI routing)
    priority: int = 10       # 10=Micro, 20=Macro, 30=Risk, 40=Emergency
    reason: str = ""
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
    pot_total: float  # Total exposure (sum of |qty| * price) - DOLLAR VALUE
    pot_max: float  # Maximum exposure limit
    long_lots: float  # Total long lots (share count)
    short_lots: float  # Total short lots (share count)
    net_exposure: float  # long_lots - short_lots (NET SHARE COUNT)
    # NEW: Dollar-based metrics for UI display
    long_value: float = 0.0  # Total LONG position value in dollars
    short_value: float = 0.0  # Total SHORT position value in dollars
    # Per-account avg_price used for lot-based mode calculation
    # This prevents cross-account leakage through ExposureCalculator singleton
    avg_price: float = 100.0  # Average preferred price for lot conversion
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
    positions: List['PositionSnapshot']  # Position snapshots (PositionSnapshot objects)
    metrics: Dict[str, 'SymbolMetrics']  # Symbol metrics (symbol -> SymbolMetrics object)
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
    strategy_tag: Optional[str] = None # Phase 10: "LT_LONG_INC", etc.
    lot_percentage: Optional[float] = None  # %50, %25, etc.
    calculated_lot: Optional[int] = None  # Calculated lot amount
    price_hint: Optional[float] = None  # Price hint (GRPAN, RWVAP, etc.)
    step_number: Optional[int] = None  # Which step (for KARBOTU/REDUCEMORE)
    current_qty: Optional[float] = None  # Broker Current Qty (Phase 11 UI)
    potential_qty: Optional[float] = None # Broker Current + Open (Phase 11 UI)
    reason: str = ""  # Decision reason
    filtered_out: bool = False  # Was this filtered out?
    filter_reasons: List[str] = field(default_factory=list)  # Why filtered?
    confidence: float = 0.0  # Confidence score (0-1)
    metrics_used: Dict[str, float] = field(default_factory=dict)  # Metrics used
    priority: int = 20  # Execution priority (High=40, Low=10)
    engine_name: Optional[str] = None  # Name of the engine that produced this decision
    
    # Proposal UI: Benchmark chg & Ask sell pahalilik (from symbol_metrics at adapt time)
    bench_chg: Optional[float] = None  # Benchmark daily change (for B: in UI)
    ask_sell_pahalilik: Optional[float] = None  # Ask sell pahalilik score (for Ask ph in UI)
    
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


class PositionTag(str, Enum):
    """
    8-Type Position Taxonomy Tags (Phase 10).
    Format: {STRATEGY}_{SIDE}_{ORIGIN}
    """
    LT_LONG_OV = "LT_LONG_OV"
    LT_LONG_INT = "LT_LONG_INT"
    LT_SHORT_OV = "LT_SHORT_OV"
    LT_SHORT_INT = "LT_SHORT_INT"
    
    MM_LONG_OV = "MM_LONG_OV"
    MM_LONG_INT = "MM_LONG_INT"
    MM_SHORT_OV = "MM_SHORT_OV"
    MM_SHORT_INT = "MM_SHORT_INT"


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
    potential_qty: float = 0.0  # Current Qty + Net Open Orders (Phase 11 UI)
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
    
    # Phase 9: 8-Type Taxonomy (Strict Classification)
    strategy_type: str = "LT"      # LT or MM
    origin_type: str = "INT"       # OV (Overnight) or INT (Intraday)
    full_taxonomy: str = "LT INT"  # e.g. "LT OV Long", "MM INT Short"
    befday_qty: float = 0.0        # Value from Befday CSV (if OV)
    
    # Intraday P&L (New Request)
    prev_close: float = 0.0
    intraday_cost: float = 0.0
    intraday_pnl: float = 0.0
    
    # Phase 10: Position Tags (OV/INT Breakdown)
    position_tags: Dict[str, float] = field(default_factory=dict)
    
    # Truth Shift (TSS/RTS — directional flow scores)
    tss_5m: Optional[float] = None    # TSS over 5 min window
    tss_15m: Optional[float] = None   # TSS over 15 min window
    tss_1h: Optional[float] = None    # TSS over 1 hour window
    rts_15m: Optional[float] = None   # RTS (relative to group) 15 min
    truth_shift_group: Optional[str] = None  # Group key used for RTS
    
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
    
    # Generic grouping
    dos_grup: Optional[str] = None
    
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
    bench_chg: Optional[float] = None  # NEW: Benchmark daily change
    
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
    
    # Truth Ticks & VOLAV (intraday volume-weighted levels)
    last_truth_tick: Optional[float] = None   # Last real trade tick price
    volav_1h: Optional[float] = None          # Volume-averaged price (1 hour)
    volav_4h: Optional[float] = None          # Volume-averaged price (4 hours)
    son5_tick: Optional[float] = None         # Average of last 5 truth ticks
    
    timestamp: datetime = field(default_factory=datetime.now)


# ============================================================================
# DATA COMPLETENESS CHECK
# ============================================================================

def is_data_complete(metric: SymbolMetrics, side: str = 'LONG') -> bool:
    """
    Check if critical metrics are available and not exactly 0.00.
    
    Returns False if ANY critical metric is None or exactly 0.00.
    Exactly 0.00 indicates missing data, not a valid calculated value.
    Valid values like 0.01 or -0.01 are considered complete.
    
    Args:
        metric: SymbolMetrics object
        side: 'LONG' or 'SHORT' - determines which metrics are critical
        
    Returns:
        True if all critical metrics are present and valid
    """
    if metric is None:
        return False
    
    # Helper to check if value is valid (not None)
    # Note: Exactly 0.0 is considered invalid for GORT/FBtot/SFStot as it usually indicates missing price data
    # But for SMA_CHG, 0.0 is a perfectly valid market condition.
    def is_valid(value, name=None):
        if value is None:
            return False
            
        if isinstance(value, (int, float)) and value == 0.0:
            # Gort/FBtot/SFStot cannot be exactly zero if data is healthy
            if name in ['gort', 'fbtot', 'sfstot']:
                return False
            # SMA Change can be exactly 0.0
            return True
            
        return True
    
    # Common metrics required for both LONG and SHORT
    if not is_valid(metric.gort, 'gort'):
        return False
    if not is_valid(metric.sma63_chg, 'sma63_chg'):
        return False
    if not is_valid(metric.sma246_chg, 'sma246_chg'):
        return False
    
    # Side-specific metrics
    if side == 'LONG':
        if not is_valid(metric.fbtot, 'fbtot'):
            return False
    elif side == 'SHORT':
        if not is_valid(metric.sfstot, 'sfstot'):
            return False
    
    return True


def get_missing_metrics(metric: SymbolMetrics, side: str = 'LONG') -> list:
    """
    Get list of missing/invalid critical metrics.
    
    Args:
        metric: SymbolMetrics object
        side: 'LONG' or 'SHORT'
        
    Returns:
        List of metric names that are missing or invalid
    """
    if metric is None:
        return ['ALL_METRICS']
    
    missing = []
    
    def check(value, name):
        if value is None or (isinstance(value, (int, float)) and value == 0.0):
            missing.append(name)
    
    check(metric.gort, 'gort')
    check(metric.sma63_chg, 'sma63_chg')
    check(metric.sma246_chg, 'sma246_chg')
    
    if side == 'LONG':
        check(metric.fbtot, 'fbtot')
    elif side == 'SHORT':
        check(metric.sfstot, 'sfstot')
    
    return missing


