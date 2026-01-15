"""app/portfolio/portfolio_manager.py

Portfolio Manager - manages multi-asset portfolio with cash, positions, and P&L.
"""

from typing import Dict, Any, Optional
from collections import defaultdict

from app.core.logger import logger
from app.engine.position_manager import PositionManager


class PortfolioManager:
    """
    Portfolio-level position manager.
    
    Manages:
    - Cash balance
    - Per-symbol positions
    - Realized & unrealized P&L
    - Total portfolio equity
    - Exposure per symbol and total exposure
    """
    
    def __init__(self, initial_cash: float = 100000.0):
        """
        Initialize portfolio manager.
        
        Args:
            initial_cash: Starting cash balance
        """
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.position_managers: Dict[str, PositionManager] = {}  # symbol -> PositionManager
        
        # Track market prices for unrealized P&L
        self.market_prices: Dict[str, float] = {}
    
    def get_position_manager(self, symbol: str) -> PositionManager:
        """Get or create position manager for symbol"""
        if symbol not in self.position_managers:
            self.position_managers[symbol] = PositionManager()
        return self.position_managers[symbol]
    
    def update_on_order_fill(self, symbol: str, side: str, qty: float, price: float, commission: float = 0.0):
        """
        Update portfolio on order fill.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            qty: Fill quantity
            price: Fill price
            commission: Commission paid
        """
        try:
            position_mgr = self.get_position_manager(symbol)
            
            # Calculate cost
            cost = qty * price + commission
            
            if side.upper() == "BUY":
                # Deduct cash for buy
                self.cash -= cost
                # Update position (positive qty)
                position_mgr.update_position(symbol, qty, price)
            else:
                # Add cash for sell
                self.cash += cost
                # Update position (negative qty)
                position_mgr.update_position(symbol, -qty, price)
            
            # Update market price
            self.market_prices[symbol] = price
            
            logger.debug(f"Portfolio updated: {symbol} {side} {qty} @ {price}, Cash: ${self.cash:.2f}")
        
        except Exception as e:
            logger.error(f"Error updating portfolio on fill: {e}", exc_info=True)
    
    def update_market_price(self, symbol: str, price: float):
        """Update market price for symbol (for unrealized P&L calculation)"""
        self.market_prices[symbol] = price
        
        # Update unrealized P&L in position manager
        position_mgr = self.get_position_manager(symbol)
        position_mgr.calculate_unrealized_pnl(symbol, price)
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position for symbol"""
        position_mgr = self.get_position_manager(symbol)
        return position_mgr.get_position(symbol)
    
    def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """Get all positions"""
        all_positions = {}
        for symbol, position_mgr in self.position_managers.items():
            pos = position_mgr.get_position(symbol)
            if pos and pos.get('qty', 0) != 0:
                all_positions[symbol] = pos
        return all_positions
    
    def get_unrealized_pnl(self) -> float:
        """Get total unrealized P&L across all positions"""
        total = 0.0
        for symbol, position_mgr in self.position_managers.items():
            pos = position_mgr.get_position(symbol)
            if pos:
                # Update unrealized P&L if market price available
                if symbol in self.market_prices:
                    position_mgr.calculate_unrealized_pnl(symbol, self.market_prices[symbol])
                total += pos.get('unrealized_pnl', 0)
        return total
    
    def get_realized_pnl(self) -> float:
        """Get total realized P&L across all positions"""
        total = 0.0
        for symbol, position_mgr in self.position_managers.items():
            total += position_mgr.get_total_realized_pnl()
        return total
    
    def get_total_equity(self) -> float:
        """
        Get total portfolio equity.
        
        Equity = Cash + Sum of (Position Value)
        Position Value = qty * market_price
        """
        equity = self.cash
        
        # Add position values
        for symbol, position_mgr in self.position_managers.items():
            pos = position_mgr.get_position(symbol)
            if pos and symbol in self.market_prices:
                qty = pos.get('qty', 0)
                market_price = self.market_prices[symbol]
                position_value = qty * market_price
                equity += position_value
        
        return equity
    
    def get_exposure(self, symbol: str) -> float:
        """
        Get exposure for symbol.
        
        Exposure = abs(qty * market_price)
        """
        position_mgr = self.get_position_manager(symbol)
        pos = position_mgr.get_position(symbol)
        
        if pos and symbol in self.market_prices:
            qty = pos.get('qty', 0)
            market_price = self.market_prices[symbol]
            return abs(qty * market_price)
        
        return 0.0
    
    def get_total_exposure(self) -> float:
        """Get total portfolio exposure"""
        total = 0.0
        for symbol in self.position_managers.keys():
            total += self.get_exposure(symbol)
        return total
    
    def get_leverage(self) -> float:
        """
        Get portfolio leverage.
        
        Leverage = Total Exposure / Equity
        """
        equity = self.get_total_equity()
        if equity > 0:
            return self.get_total_exposure() / equity
        return 0.0
    
    def get_margin_usage(self) -> float:
        """
        Get margin usage (simplified).
        
        Margin Usage = (Total Exposure - Cash) / Equity
        """
        equity = self.get_total_equity()
        if equity > 0:
            exposure = self.get_total_exposure()
            margin_used = max(0, exposure - self.cash)
            return margin_used / equity
        return 0.0
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary"""
        return {
            'cash': self.cash,
            'total_equity': self.get_total_equity(),
            'total_exposure': self.get_total_exposure(),
            'leverage': self.get_leverage(),
            'margin_usage': self.get_margin_usage(),
            'realized_pnl': self.get_realized_pnl(),
            'unrealized_pnl': self.get_unrealized_pnl(),
            'num_positions': len(self.get_all_positions())
        }








