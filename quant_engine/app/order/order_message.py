"""app/order/order_message.py

Order message model using Pydantic.
Represents an order request from strategy to order router.
"""

from pydantic import BaseModel, Field
from typing import Optional


class OrderMessage(BaseModel):
    """Order message model"""
    
    symbol: str = Field(..., description="Stock symbol")
    side: str = Field(..., description="Order side: BUY or SELL")
    qty: float = Field(..., gt=0, description="Order quantity")
    order_type: str = Field(default="MKT", description="Order type: MKT or LMT")
    limit_price: Optional[float] = Field(default=None, description="Limit price (required for LMT orders)")
    timestamp: int = Field(..., description="Order timestamp in milliseconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "side": "BUY",
                "qty": 10.0,
                "order_type": "MKT",
                "limit_price": None,
                "timestamp": 1700000000000
            }
        }
    
    def validate(self):
        """Validate order message"""
        if self.side.upper() not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid side: {self.side}. Must be BUY or SELL")
        
        if self.order_type.upper() not in ["MKT", "LMT"]:
            raise ValueError(f"Invalid order_type: {self.order_type}. Must be MKT or LMT")
        
        if self.order_type.upper() == "LMT" and self.limit_price is None:
            raise ValueError("limit_price is required for LMT orders")
        
        if self.order_type.upper() == "LMT" and self.limit_price <= 0:
            raise ValueError("limit_price must be positive")








