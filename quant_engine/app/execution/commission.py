"""app/execution/commission.py

Commission models for execution simulation.
Supports IBKR, percentage, and maker/taker fee models.
"""

from enum import Enum
from typing import Optional
from app.core.logger import logger


class CommissionType(Enum):
    """Commission model types"""
    IBKR_STOCK = "ibkr_stock"
    PERCENTAGE = "percentage"
    MAKER_TAKER = "maker_taker"
    FIXED = "fixed"


class CommissionModel:
    """
    Commission calculation model.
    
    Supports multiple commission structures:
    - IBKR stock commission
    - Percentage commission
    - Maker/Taker fees (crypto)
    - Fixed commission
    """
    
    def __init__(
        self,
        commission_type: CommissionType = CommissionType.IBKR_STOCK,
        percentage: float = 0.0,
        per_share: float = 0.0,
        min_commission: float = 0.0,
        max_commission_pct: float = 0.0,
        maker_fee: float = 0.0,
        taker_fee: float = 0.0,
        fixed_commission: float = 0.0
    ):
        """
        Initialize commission model.
        
        Args:
            commission_type: Type of commission model
            percentage: Percentage commission (e.g., 0.0002 for 0.02%)
            per_share: Per-share commission (e.g., 0.0035)
            min_commission: Minimum commission per trade
            max_commission_pct: Maximum commission as % of trade value
            maker_fee: Maker fee (negative for rebate)
            taker_fee: Taker fee
            fixed_commission: Fixed commission per trade
        """
        self.commission_type = commission_type
        self.percentage = percentage
        self.per_share = per_share
        self.min_commission = min_commission
        self.max_commission_pct = max_commission_pct
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.fixed_commission = fixed_commission
    
    @classmethod
    def ibkr_stock(cls):
        """Create IBKR stock commission model"""
        return cls(
            commission_type=CommissionType.IBKR_STOCK,
            per_share=0.0035,
            min_commission=1.0,
            max_commission_pct=0.01  # 1% max
        )
    
    @classmethod
    def percentage(cls, pct: float, min_commission: float = 0.0):
        """Create percentage commission model"""
        return cls(
            commission_type=CommissionType.PERCENTAGE,
            percentage=pct,
            min_commission=min_commission
        )
    
    @classmethod
    def maker_taker(cls, maker_fee: float, taker_fee: float):
        """Create maker/taker commission model (crypto)"""
        return cls(
            commission_type=CommissionType.MAKER_TAKER,
            maker_fee=maker_fee,
            taker_fee=taker_fee
        )
    
    @classmethod
    def fixed(cls, amount: float):
        """Create fixed commission model"""
        return cls(
            commission_type=CommissionType.FIXED,
            fixed_commission=amount
        )
    
    def calculate(
        self,
        symbol: str,
        qty: float,
        price: float,
        side: str = "BUY",
        order_type: str = "MARKET"
    ) -> float:
        """
        Calculate commission for a trade.
        
        Args:
            symbol: Stock symbol
            qty: Quantity traded
            price: Fill price
            side: BUY or SELL
            order_type: MARKET or LIMIT (for maker/taker)
            
        Returns:
            Commission amount
        """
        trade_value = abs(qty * price)
        
        if self.commission_type == CommissionType.IBKR_STOCK:
            # IBKR: $0.0035 per share, min $1, max 1% of trade value
            commission = abs(qty) * self.per_share
            commission = max(commission, self.min_commission)
            if self.max_commission_pct > 0:
                commission = min(commission, trade_value * self.max_commission_pct)
            return commission
        
        elif self.commission_type == CommissionType.PERCENTAGE:
            # Percentage of trade value
            commission = trade_value * self.percentage
            if self.min_commission > 0:
                commission = max(commission, self.min_commission)
            return commission
        
        elif self.commission_type == CommissionType.MAKER_TAKER:
            # Maker/Taker fees (crypto)
            fee_rate = self.maker_fee if order_type == "LIMIT" else self.taker_fee
            commission = trade_value * abs(fee_rate)
            # Maker rebate is negative, so we add it (reduces cost)
            if fee_rate < 0:
                commission = -commission
            return commission
        
        elif self.commission_type == CommissionType.FIXED:
            # Fixed commission per trade
            return self.fixed_commission
        
        else:
            logger.warning(f"Unknown commission type: {self.commission_type}")
            return 0.0








