"""
Order Proposal Models - Human-in-the-Loop

Data models for order proposals (before execution).
DecisionResponse → OrderProposal mapping.

Key Principles:
- ExecutionIntent'tan ÖNCE
- Broker'dan TAMAMEN bağımsız
- Human-readable
- Decision logic'e dokunmaz
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum


class ProposalStatus(Enum):
    """Order proposal status"""
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"  # Human accepted (for tracking)
    REJECTED = "REJECTED"  # Human rejected (for tracking)
    EXPIRED = "EXPIRED"  # Proposal expired (not executed)


class PositionBook(Enum):
    """Position Book Type (POS TAG) - How position entered portfolio"""
    LT = "LT"   # Long Term (opened via PATADD, ADDNEWPOS)
    MM = "MM"   # Market Making (opened via Greatest MM)


class EngineTag(Enum):
    """
    Order Engine Tag (ORDER TAG) - Which engine generated the order.
    6 possible values.
    """
    MM = "MM"       # Greatest MM engine (INC & DEC)
    NEWC = "NEWC"   # NEWCLMM engine — truth tick spread capture (INC & DEC)
    PA = "PA"       # PATADD engine (INC only)
    AN = "AN"       # ADDNEWPOS engine (INC only)
    KB = "KB"       # KARBOTU engine (DEC only)
    TRIM = "TRIM"   # LT_TRIM engine (DEC only) — renamed from LT to avoid confusion
    
    
class OrderSubtype(Enum):
    """
    Detailed Order Subtype — Dual Tag Format v4
    
    Format: {POS}_{ENGINE}_{DIRECTION}_{ACTION}
    POS:       MM or LT
    ENGINE:    MM, PA, AN, KB, TRIM
    DIRECTION: LONG or SHORT
    ACTION:    INC or DEC
    """
    # ═══ POS INCREASE (new position / position growth) ═══
    # MM pos, MM engine increase
    MM_MM_LONG_INC = "MM_MM_LONG_INC"
    MM_MM_SHORT_INC = "MM_MM_SHORT_INC"
    # MM pos, NEWCLMM engine increase (truth tick spread capture)
    MM_NEWC_LONG_INC = "MM_NEWC_LONG_INC"
    MM_NEWC_SHORT_INC = "MM_NEWC_SHORT_INC"
    # LT pos, PATADD engine increase
    LT_PA_LONG_INC = "LT_PA_LONG_INC"
    LT_PA_SHORT_INC = "LT_PA_SHORT_INC"
    # LT pos, ADDNEWPOS engine increase
    LT_AN_LONG_INC = "LT_AN_LONG_INC"
    LT_AN_SHORT_INC = "LT_AN_SHORT_INC"
    
    # ═══ POS DECREASE (trim / take profit / close) ═══
    # MM pos, KARBOTU engine decrease
    MM_KB_LONG_DEC = "MM_KB_LONG_DEC"
    MM_KB_SHORT_DEC = "MM_KB_SHORT_DEC"
    # MM pos, TRIM engine decrease
    MM_TRIM_LONG_DEC = "MM_TRIM_LONG_DEC"
    MM_TRIM_SHORT_DEC = "MM_TRIM_SHORT_DEC"
    # MM pos, MM engine decrease
    MM_MM_LONG_DEC = "MM_MM_LONG_DEC"
    MM_MM_SHORT_DEC = "MM_MM_SHORT_DEC"
    # MM pos, NEWCLMM engine decrease (profit take / exit)
    MM_NEWC_LONG_DEC = "MM_NEWC_LONG_DEC"
    MM_NEWC_SHORT_DEC = "MM_NEWC_SHORT_DEC"
    # LT pos, KARBOTU engine decrease
    LT_KB_LONG_DEC = "LT_KB_LONG_DEC"
    LT_KB_SHORT_DEC = "LT_KB_SHORT_DEC"
    # LT pos, TRIM engine decrease
    LT_TRIM_LONG_DEC = "LT_TRIM_LONG_DEC"
    LT_TRIM_SHORT_DEC = "LT_TRIM_SHORT_DEC"
    
    # ═══ Legacy compatibility ═══
    LT_LONG_INC = "LT_LONG_INC"
    LT_SHORT_INC = "LT_SHORT_INC"
    LT_LONG_DEC = "LT_LONG_DEC"
    LT_SHORT_DEC = "LT_SHORT_DEC"
    LT_LONG_TRIM = "LT_LONG_TRIM"
    LT_SHORT_TRIM = "LT_SHORT_TRIM"
    LT_LONG_KARBOTU = "LT_LONG_KARBOTU"
    LT_SHORT_KARBOTU = "LT_SHORT_KARBOTU"
    LT_LONG_REDUCE = "LT_LONG_REDUCE"
    LT_SHORT_REDUCE = "LT_SHORT_REDUCE"
    MM_LONG_INC = "MM_LONG_INC"
    MM_SHORT_INC = "MM_SHORT_INC"
    MM_LONG_DEC = "MM_LONG_DEC"
    MM_SHORT_DEC = "MM_SHORT_DEC"
    
    # UNKNOWN/OTHER
    UNKNOWN = "UNKNOWN"


@dataclass
class OrderProposal:
    """
    Order Proposal - human-readable order suggestion.
    
    This is generated from DecisionResponse BEFORE ExecutionIntent.
    Human evaluates and decides whether to execute manually.
    """
    # Order details (required fields first)
    symbol: str
    side: str  # "BUY", "SELL", "ADD"
    qty: int  # Lot amount (always positive)
    order_type: str  # "LIMIT", "MARKET"
    
    # Decision context (required fields)
    engine: str  # "KARBOTU", "REDUCEMORE", "ADDNEWPOS"
    reason: str  # Human-readable decision reason
    
    # Position Context (Phase 11 UI)
    current_qty: Optional[float] = None
    potential_qty: Optional[float] = None
    
    # Optional fields (with defaults)
    proposed_price: Optional[float] = None  # Limit price (if LIMIT order)
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    spread: Optional[float] = None
    spread_percent: Optional[float] = None
    
    # Extended market context (Janall-style)
    prev_close: Optional[float] = None
    daily_chg: Optional[float] = None  # Daily change %
    bench_chg: Optional[float] = None  # Benchmark change %
    pahalilik_score: Optional[float] = None  # Ask Sell Pahalilik Score
    ucuzluk_score: Optional[float] = None  # Bid Buy Ucuzluk Score
    
    # Decision thresholds (why this proposal was made)
    decision_thresholds: Dict[str, Any] = field(default_factory=dict)
    # Example: {"score": 0.25, "threshold": 0.10, "spread_pct": 0.05, "ladder_step": 0.1}
    
    confidence: float = 0.0  # Confidence score (0-1)
    metrics_used: Dict[str, float] = field(default_factory=dict)  # Metrics used for decision
    
    # Cycle tracking
    cycle_id: int = 0
    decision_ts: datetime = field(default_factory=datetime.now)
    proposal_ts: datetime = field(default_factory=datetime.now)
    
    # Lifecycle
    status: str = ProposalStatus.PROPOSED.value
    human_action: Optional[str] = None  # "ACCEPTED", "REJECTED", None
    human_action_ts: Optional[datetime] = None
    
    # Additional context
    step_number: Optional[int] = None  # Which step (for KARBOTU/REDUCEMORE)
    lot_percentage: Optional[float] = None  # % of position (if applicable)
    price_hint: Optional[float] = None  # Price hint from decision (GRPAN, RWVAP, etc.)
    
    # PHASE 9: Strict Tagging — Dual Tag System v4
    book: str = "MM"  # POS TAG: MM or LT (default MM for migration)
    order_subtype: str = "UNKNOWN"  # Full tag e.g. MM_MM_LONG_INC, LT_PA_LONG_INC
    pos_tag: str = "MM"  # POS TAG shortcut (MM or LT)
    engine_tag: str = "MM"  # ORDER TAG shortcut (MM, PA, AN, KB, TRIM)
    
    @property
    def strategy_tag(self) -> str:
        """Generate full combined strategy tag: {POS}_{ENGINE}_{DIR}_{ACTION}"""
        return self.order_subtype if self.order_subtype != "UNKNOWN" else f"{self.pos_tag}_{self.engine_tag}_UNKNOWN"
    
    # PHASE 8: Warnings (for enrichment validation)
    warnings: List[str] = field(default_factory=list)  # e.g., "MARKET_CONTEXT_INCOMPLETE"
    
    # Account tagging (CRITICAL: for per-account proposal filtering)
    account_id: Optional[str] = None  # e.g. "HAMPRO", "IBKR_PED", "IBKR_GUN"
    
    # ID (Unique Identifier) - Populated on save/load
    id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization"""
        # Generate unique ID for UI if not present
        if not self.id:
            self.id = f"{self.cycle_id}_{self.symbol}_{self.side}_{self.proposal_ts.timestamp()}"
        
        return {
            'id': self.id,  # Unique ID for UI
            'symbol': self.symbol,
            'side': self.side,
            'qty': self.qty,
            'current_qty': self.current_qty,
            'potential_qty': self.potential_qty,
            'order_type': self.order_type,
            'price': self.proposed_price,  # UI expects 'price', not 'proposed_price'
            'proposed_price': self.proposed_price,  # Keep for backwards compatibility
            'bid': self.bid,
            'ask': self.ask,
            'last': self.last,
            'spread': self.spread,
            'spread_percent': self.spread_percent,
            # Extended market context
            'prev_close': self.prev_close,
            'daily_chg': self.daily_chg,
            'bench_chg': self.bench_chg,
            'pahalilik_score': self.pahalilik_score,
            'ucuzluk_score': self.ucuzluk_score,
            'decision_thresholds': self.decision_thresholds,
            # Decision context
            'engine': self.engine,
            'reason': self.reason,
            'confidence': self.confidence,
            'metrics_used': self.metrics_used,
            'cycle_id': self.cycle_id,
            'decision_ts': self.decision_ts.isoformat(),
            'proposal_ts': self.proposal_ts.isoformat(),
            'status': self.status,
            'human_action': self.human_action,
            'human_action_ts': self.human_action_ts.isoformat() if self.human_action_ts else None,
            'step_number': self.step_number,
            'lot_percentage': self.lot_percentage,
            'price_hint': self.price_hint,
            'warnings': self.warnings,
            'book': self.book,
            'order_subtype': self.order_subtype,
            'pos_tag': self.pos_tag,
            'engine_tag': self.engine_tag,
            'strategy_tag': self.strategy_tag,
            'account_id': self.account_id
        }
    
    def to_human_readable(self) -> str:
        """Convert to human-readable string for console/log"""
        lines = [
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"ORDER PROPOSAL - {self.engine} ({self.id or 'NO_ID'})",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"Symbol: {self.symbol}",
            f"Action: {self.side} {self.qty} @ {self.proposed_price or 'MARKET'} ({self.order_type})",
            f"",
            f"Market Context:",
            f"  Bid: ${self.bid:.2f}" if self.bid else "  Bid: N/A",
            f"  Ask: ${self.ask:.2f}" if self.ask else "  Ask: N/A",
            f"  Last: ${self.last:.2f}" if self.last else "  Last: N/A",
            f"  Spread: ${self.spread:.4f} ({self.spread_percent:.2f}%)" if self.spread and self.spread_percent else "  Spread: N/A",
            f"",
            f"Decision Context:",
            f"  Engine: {self.engine}",
            f"  Reason: {self.reason}",
            f"  Confidence: {self.confidence:.2%}",
            f"  Step: {self.step_number}" if self.step_number else "",
            f"  Lot %: {self.lot_percentage:.1f}%" if self.lot_percentage else "",
            f"  Price Hint: ${self.price_hint:.2f}" if self.price_hint else "",
            f"",
            f"Cycle: {self.cycle_id} | Decision: {self.decision_ts.strftime('%H:%M:%S')} | Proposal: {self.proposal_ts.strftime('%H:%M:%S')}",
            f"Status: {self.status}",
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        ]
        return "\n".join(filter(None, lines))  # Remove empty lines

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrderProposal':
        """Create OrderProposal from dict (deserialization)"""
        # Parse datetimes
        decision_ts = datetime.fromisoformat(data['decision_ts']) if isinstance(data.get('decision_ts'), str) else data.get('decision_ts', datetime.now())
        proposal_ts = datetime.fromisoformat(data['proposal_ts']) if isinstance(data.get('proposal_ts'), str) else data.get('proposal_ts', datetime.now())
        
        human_action_ts = None
        if data.get('human_action_ts'):
            if isinstance(data['human_action_ts'], str):
                human_action_ts = datetime.fromisoformat(data['human_action_ts'])
            else:
                human_action_ts = data['human_action_ts']

        # Extract fields known to constructor
        # (This avoids TypeError if new fields are added to dict but not yet in constructor, 
        # though we should match them. For safety, we can filter or just pass explicit args)
        
        return cls(
            symbol=data['symbol'],
            side=data['side'],
            qty=data['qty'],
            order_type=data['order_type'],
            engine=data['engine'],
            reason=data['reason'],
            
            # Position Context
            current_qty=data.get('current_qty'),
            potential_qty=data.get('potential_qty'),
            
            # Optional
            proposed_price=data.get('proposed_price') or data.get('price'), # Handle alias
            bid=data.get('bid'),
            ask=data.get('ask'),
            last=data.get('last'),
            spread=data.get('spread'),
            spread_percent=data.get('spread_percent'),
            
            # Extended
            prev_close=data.get('prev_close'),
            daily_chg=data.get('daily_chg'),
            bench_chg=data.get('bench_chg'),
            pahalilik_score=data.get('pahalilik_score'),
            ucuzluk_score=data.get('ucuzluk_score'),
            
            decision_thresholds=data.get('decision_thresholds', {}),
            confidence=data.get('confidence', 0.0),
            metrics_used=data.get('metrics_used', {}),
            
            cycle_id=data.get('cycle_id', 0),
            decision_ts=decision_ts,
            proposal_ts=proposal_ts,
            
            status=data.get('status', ProposalStatus.PROPOSED.value),
            human_action=data.get('human_action'),
            human_action_ts=human_action_ts,
            
            step_number=data.get('step_number'),
            lot_percentage=data.get('lot_percentage'),
            price_hint=data.get('price_hint'),
            
            
            book=data.get('book', 'MM'),
            order_subtype=data.get('order_subtype', 'UNKNOWN'),
            pos_tag=data.get('pos_tag', data.get('book', 'MM')),
            engine_tag=data.get('engine_tag', 'MM'),
            warnings=data.get('warnings', []),
            account_id=data.get('account_id'),
            
            id=data.get('id')
        )

