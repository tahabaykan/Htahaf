"""
Intent Models
Data models for PSFALGO Intentions system.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class IntentStatus(str, Enum):
    """Intent status enum"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class IntentAction(str, Enum):
    """Intent action type"""
    BUY = "BUY"
    SELL = "SELL"
    BUY_TO_COVER = "BUY_TO_COVER"
    SELL_SHORT = "SELL_SHORT"
    REPLACE = "REPLACE"
    CANCEL = "CANCEL"


class OrderType(str, Enum):
    """Order type"""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class RiskCheckResult(BaseModel):
    """Risk check result"""
    passed: bool = Field(..., description="Whether risk check passed")
    reason: str = Field(..., description="Reason for pass/fail")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional details")


class Intent(BaseModel):
    """Intent model - represents a planned order before execution"""
    
    # Identity
    id: str = Field(..., description="Unique intent ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="Intent creation timestamp")
    
    # Order details
    symbol: str = Field(..., description="Symbol (PREF_IBKR)")
    action: IntentAction = Field(..., description="Order action")
    qty: int = Field(..., description="Quantity (lots)")
    price: Optional[float] = Field(None, description="Limit price (if limit order)")
    order_type: OrderType = Field(OrderType.LIMIT, description="Order type")
    
    # Reasoning
    reason_code: str = Field(..., description="Reason code (e.g., 'KARBOTU_TAKE_PROFIT', 'ADDNEWPOS_BUY')")
    reason_text: str = Field(..., description="Human-readable reason")
    trigger_rule: str = Field(..., description="Which rule triggered this intent")
    metric_values: Dict[str, Any] = Field(default_factory=dict, description="Metric values at trigger time")
    
    # Risk checks
    risk_checks: List[RiskCheckResult] = Field(default_factory=list, description="Risk check results")
    risk_passed: bool = Field(True, description="Overall risk check status")
    
    # Status
    status: IntentStatus = Field(IntentStatus.PENDING, description="Current intent status")
    approved_at: Optional[datetime] = Field(None, description="Approval timestamp")
    rejected_at: Optional[datetime] = Field(None, description="Rejection timestamp")
    rejected_reason: Optional[str] = Field(None, description="Rejection reason")
    sent_at: Optional[datetime] = Field(None, description="Execution timestamp")
    execution_result: Optional[Dict[str, Any]] = Field(None, description="Execution result")
    
    # Metadata
    cycle_number: Optional[int] = Field(None, description="RUNALL cycle number")
    engine_name: str = Field(..., description="Engine that created this intent (e.g., 'KARBOTU', 'ADDNEWPOS')")
    
    class Config:
        use_enum_values = True





