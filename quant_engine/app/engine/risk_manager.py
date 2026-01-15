"""app/engine/risk_manager.py

Risk manager - validates signals before execution.
"""

from typing import Dict, Any
from app.core.logger import logger


class RiskManager:
    """Risk management - validates trading signals"""
    
    def __init__(self):
        self.max_position_size = 10000  # Max position size per symbol
        self.max_daily_loss = 10000  # Max daily loss limit
        self.daily_pnl = 0.0
    
    def check_signal(self, signal: Dict[str, Any]) -> bool:
        """
        Check if signal passes risk management rules.
        
        Args:
            signal: Signal dict
            
        Returns:
            True if signal passes risk checks
        """
        try:
            symbol = signal.get('symbol')
            signal_type = signal.get('signal', 'BUY')
            quantity = signal.get('quantity', 0)
            price = float(signal.get('price', 0))
            
            # Basic validation
            if not symbol or quantity <= 0 or price <= 0:
                logger.warning(f"Invalid signal: {signal}")
                return False
            
            # Position size check
            if quantity > self.max_position_size:
                logger.warning(f"Signal rejected: quantity {quantity} exceeds max {self.max_position_size}")
                return False
            
            # Daily loss limit check (simplified)
            # In production, this would check actual P&L
            if self.daily_pnl <= -self.max_daily_loss:
                logger.warning(f"Signal rejected: daily loss limit reached ({self.daily_pnl})")
                return False
            
            # All checks passed
            return True
            
        except Exception as e:
            logger.error(f"Error in risk check: {e}")
            return False
    
    def update_daily_pnl(self, pnl: float):
        """Update daily P&L"""
        self.daily_pnl += pnl
        logger.debug(f"Daily P&L updated: {self.daily_pnl}")








