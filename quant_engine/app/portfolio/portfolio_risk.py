"""app/portfolio/portfolio_risk.py

Portfolio-level risk manager - enforces risk rules at portfolio level.
"""

from typing import Dict, Any, Optional, Tuple
from app.core.logger import logger
from app.portfolio.portfolio_manager import PortfolioManager


class PortfolioRiskManager:
    """
    Portfolio-level risk manager.
    
    Enforces:
    - Max capital per trade
    - Max exposure per symbol (%)
    - Max portfolio leverage
    - Max total exposure (%)
    """
    
    def __init__(
        self,
        max_capital_per_trade: float = 10000.0,
        max_exposure_per_symbol_pct: float = 20.0,
        max_portfolio_leverage: float = 2.0,
        max_total_exposure_pct: float = 80.0
    ):
        """
        Initialize portfolio risk manager.
        
        Args:
            max_capital_per_trade: Maximum capital per trade
            max_exposure_per_symbol_pct: Maximum exposure per symbol as % of equity
            max_portfolio_leverage: Maximum portfolio leverage
            max_total_exposure_pct: Maximum total exposure as % of equity
        """
        self.max_capital_per_trade = max_capital_per_trade
        self.max_exposure_per_symbol_pct = max_exposure_per_symbol_pct
        self.max_portfolio_leverage = max_portfolio_leverage
        self.max_total_exposure_pct = max_total_exposure_pct
    
    def can_open_position(
        self,
        symbol: str,
        qty: float,
        price: float,
        portfolio: PortfolioManager
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if position can be opened.
        
        Args:
            symbol: Stock symbol
            qty: Order quantity
            price: Order price
            portfolio: PortfolioManager instance
            
        Returns:
            Tuple of (allowed: bool, reason: str or None)
        """
        try:
            # Calculate trade value
            trade_value = abs(qty * price)
            equity = portfolio.get_total_equity()
            
            if equity <= 0:
                return False, "Portfolio equity is zero or negative"
            
            # 1. Max capital per trade
            if trade_value > self.max_capital_per_trade:
                return False, f"Trade value ${trade_value:.2f} exceeds max ${self.max_capital_per_trade:.2f}"
            
            # 2. Max exposure per symbol
            current_exposure = portfolio.get_exposure(symbol)
            new_exposure = current_exposure + trade_value
            exposure_pct = (new_exposure / equity) * 100
            
            if exposure_pct > self.max_exposure_per_symbol_pct:
                return False, f"Symbol exposure {exposure_pct:.1f}% exceeds limit {self.max_exposure_per_symbol_pct}%"
            
            # 3. Max portfolio leverage
            current_leverage = portfolio.get_leverage()
            # Estimate new leverage
            new_total_exposure = portfolio.get_total_exposure() + trade_value
            estimated_leverage = new_total_exposure / equity
            
            if estimated_leverage > self.max_portfolio_leverage:
                return False, f"Estimated leverage {estimated_leverage:.2f} exceeds limit {self.max_portfolio_leverage:.2f}"
            
            # 4. Max total exposure
            total_exposure_pct = (new_total_exposure / equity) * 100
            if total_exposure_pct > self.max_total_exposure_pct:
                return False, f"Total exposure {total_exposure_pct:.1f}% exceeds limit {self.max_total_exposure_pct}%"
            
            # All checks passed
            return True, None
        
        except Exception as e:
            logger.error(f"Error in portfolio risk check: {e}", exc_info=True)
            return False, f"Risk check error: {e}"
    
    def validate_risk(
        self,
        symbol: str,
        qty: float,
        price: float,
        portfolio: PortfolioManager
    ) -> bool:
        """
        Validate risk (returns bool only).
        
        Args:
            symbol: Stock symbol
            qty: Order quantity
            price: Order price
            portfolio: PortfolioManager instance
            
        Returns:
            True if risk check passes
        """
        allowed, reason = self.can_open_position(symbol, qty, price, portfolio)
        if not allowed and reason:
            logger.warning(f"Risk check failed for {symbol}: {reason}")
        return allowed








