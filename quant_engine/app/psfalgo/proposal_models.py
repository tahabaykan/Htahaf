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
    
    # Optional fields (with defaults)
    proposed_price: Optional[float] = None  # Limit price (if LIMIT order)
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    spread: Optional[float] = None
    spread_percent: Optional[float] = None
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
    
    # PHASE 8: Warnings (for enrichment validation)
    warnings: List[str] = field(default_factory=list)  # e.g., "MARKET_CONTEXT_INCOMPLETE"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization"""
        # Generate unique ID for UI
        proposal_id = f"{self.cycle_id}_{self.symbol}_{self.side}_{self.proposal_ts.timestamp()}"
        
        return {
            'id': proposal_id,  # Unique ID for UI
            'symbol': self.symbol,
            'side': self.side,
            'qty': self.qty,
            'order_type': self.order_type,
            'price': self.proposed_price,  # UI expects 'price', not 'proposed_price'
            'proposed_price': self.proposed_price,  # Keep for backwards compatibility
            'bid': self.bid,
            'ask': self.ask,
            'last': self.last,
            'spread': self.spread,
            'spread_percent': self.spread_percent,
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
            'warnings': self.warnings
        }
    
    def to_human_readable(self) -> str:
        """Convert to human-readable string for console/log"""
        lines = [
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"ORDER PROPOSAL - {self.engine}",
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

