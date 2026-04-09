from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class StrategyTag(str, Enum):
    LT_LONG_INC = "LT_LONG_INC"
    LT_SHORT_INC = "LT_SHORT_INC"
    LT_LONG_DEC = "LT_LONG_DEC"
    LT_SHORT_DEC = "LT_SHORT_DEC"
    MM_LONG_INC = "MM_LONG_INC"
    MM_SHORT_INC = "MM_SHORT_INC"
    MM_LONG_DEC = "MM_LONG_DEC"
    MM_SHORT_DEC = "MM_SHORT_DEC"

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
    order_ids: List[Any]

class GenericResponse(BaseModel):
    success: bool
    message: str
