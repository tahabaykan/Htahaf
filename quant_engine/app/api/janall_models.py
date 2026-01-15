from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum

class StrategyTag(str, Enum):
    LT_LONG_INCREASE = "LT_LONG_INCREASE"
    LT_SHORT_INCREASE = "LT_SHORT_INCREASE"
    LT_LONG_DECREASE = "LT_LONG_DECREASE"
    LT_SHORT_DECREASE = "LT_SHORT_DECREASE"
    MM_LONG_INCREASE = "MM_LONG_INCREASE"
    MM_SHORT_INCREASE = "MM_SHORT_INCREASE"
    MM_LONG_DECREASE = "MM_LONG_DECREASE"
    MM_SHORT_DECREASE = "MM_SHORT_DECREASE"

class PositionTag(str, Enum):
    # LT (Liquidity Taking / Long Term)
    LT_LONG_OV = "LT_LONG_OV"
    LT_LONG_INT = "LT_LONG_INT"
    LT_SHORT_OV = "LT_SHORT_OV"
    LT_SHORT_INT = "LT_SHORT_INT"
    
    # MM (Market Making / Short Term)
    MM_LONG_OV = "MM_LONG_OV"
    MM_LONG_INT = "MM_LONG_INT"
    MM_SHORT_OV = "MM_SHORT_OV"
    MM_SHORT_INT = "MM_SHORT_INT"

class PositionBreakdown(BaseModel):
    tags: Dict[PositionTag, float] = Field(default_factory=dict)
    account_mode: str
    symbol: str

class BulkOrderRequest(BaseModel):
    tickers: List[str] = Field(..., description="List of tickers (e.g., BFS-E)")
    order_type: str = Field(..., description="Tactical type: bid_buy, front_sell, etc.")
    total_lot: int = Field(..., gt=0, description="Total lot size per ticker")
    strategy_tag: StrategyTag = Field(..., description="Strategic intent tag")
    smart_split: bool = Field(True, description="Enable smart lot splitting (>399)")

class BulkOrderResponse(BaseModel):
    status: str
    message: str
    results: List[dict]

class CancelOrderRequest(BaseModel):
    order_ids: List[str]

class GenericResponse(BaseModel):
    success: bool
    message: str
