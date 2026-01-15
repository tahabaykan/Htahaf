"""app/risk/risk_manager.py

Main Risk Manager - enforces risk limits and protects the trading system.
"""

import time
from typing import Dict, Any, Optional, Tuple
from app.risk.risk_limits import RiskLimits
from app.risk.risk_state import RiskState
from app.core.logger import logger
from app.engine.position_manager import PositionManager


class RiskManager:
    """
    Risk Manager - enforces risk limits and protects trading system.
    
    Responsibilities:
    - Pre-trade validation (check_before_order)
    - Post-trade state updates (update_after_execution)
    - Circuit breaker management
    - Cooldown logic
    - Exposure tracking
    """
    
    def __init__(
        self,
        limits: Optional[RiskLimits] = None,
        state: Optional[RiskState] = None,
        position_manager: Optional[PositionManager] = None
    ):
        """
        Initialize Risk Manager.
        
        Args:
            limits: RiskLimits instance (default: creates new)
            state: RiskState instance (default: creates new)
            position_manager: PositionManager instance (optional, injected later)
        """
        self.limits = limits or RiskLimits()
        self.state = state or RiskState()
        self.position_manager = position_manager
        
        logger.info(f"Risk Manager initialized with limits: max_daily_loss=${self.limits.max_daily_loss}")
    
    def set_position_manager(self, position_manager: PositionManager):
        """Set position manager (dependency injection)"""
        self.position_manager = position_manager
    
    def check_before_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if order is allowed before execution.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            qty: Order quantity
            price: Order price
            
        Returns:
            Tuple of (allowed: bool, reason: str or None)
        """
        try:
            # Check if locked
            if self.state.locked:
                return False, f"Risk Manager locked: {self.state.lock_reason}"
            
            # Check cooldown
            if self.state.is_in_cooldown():
                remaining = int(self.state.cooldown_until - time.time())
                return False, f"In cooldown period: {remaining}s remaining"
            
            # 1. Order size validation
            if qty < self.limits.min_order_size:
                return False, f"Order size {qty} below minimum {self.limits.min_order_size}"
            
            if qty > self.limits.max_order_size:
                return False, f"Order size {qty} exceeds maximum {self.limits.max_order_size}"
            
            # 2. Position size limit
            if self.position_manager:
                current_position = self.position_manager.get_position(symbol)
                current_qty = abs(current_position.get('qty', 0)) if current_position else 0
                
                # Calculate new position size
                if side.upper() == "BUY":
                    new_qty = current_qty + qty
                else:
                    new_qty = abs(current_qty - qty) if current_qty > 0 else qty
                
                if new_qty > self.limits.max_position_per_symbol:
                    return False, f"Position size {new_qty} exceeds limit {self.limits.max_position_per_symbol}"
            
            # 3. Total exposure limit
            order_value = qty * price
            estimated_new_exposure = self.state.total_exposure + order_value
            
            if self.state.current_equity > 0:
                exposure_pct = (estimated_new_exposure / self.state.current_equity) * 100
                if exposure_pct > self.limits.max_exposure_pct:
                    return False, f"Exposure {exposure_pct:.1f}% exceeds limit {self.limits.max_exposure_pct}%"
            
            # Per-symbol exposure limit
            current_symbol_exposure = abs(self.state.exposure_per_symbol.get(symbol, 0))
            new_symbol_exposure = current_symbol_exposure + order_value
            
            if self.state.current_equity > 0:
                symbol_exposure_pct = (new_symbol_exposure / self.state.current_equity) * 100
                if symbol_exposure_pct > self.limits.max_exposure_per_symbol_pct:
                    return False, f"Symbol exposure {symbol_exposure_pct:.1f}% exceeds limit {self.limits.max_exposure_per_symbol_pct}%"
            
            # 4. Trade frequency limits
            trades_last_minute = self.state.get_trades_last_minute()
            if trades_last_minute >= self.limits.max_trades_per_minute:
                return False, f"Trade frequency limit: {trades_last_minute} trades in last minute"
            
            trades_last_hour = self.state.get_trades_last_hour()
            if trades_last_hour >= self.limits.max_trades_per_hour:
                return False, f"Trade frequency limit: {trades_last_hour} trades in last hour"
            
            trades_today = self.state.get_trades_today()
            if trades_today >= self.limits.max_trades_per_day:
                return False, f"Trade frequency limit: {trades_today} trades today"
            
            # 5. Per-trade loss limit (estimate)
            if self.position_manager:
                position = self.position_manager.get_position(symbol)
                if position and position.get('qty', 0) != 0:
                    # Estimate loss if closing position
                    avg_price = position.get('avg_price', price)
                    if side.upper() == "SELL" and position.get('qty', 0) > 0:
                        estimated_loss = (avg_price - price) * min(qty, position.get('qty', 0))
                        if estimated_loss > self.limits.max_trade_loss:
                            return False, f"Estimated trade loss ${estimated_loss:.2f} exceeds limit ${self.limits.max_trade_loss}"
            
            # 6. Circuit breaker check (price volatility)
            volatility = self.state.get_recent_price_volatility(symbol, self.limits.circuit_breaker_window_seconds)
            if volatility and volatility > self.limits.circuit_breaker_pct:
                self.state.lock(f"Circuit breaker: {symbol} volatility {volatility:.1f}%")
                return False, f"Circuit breaker triggered: volatility {volatility:.1f}%"
            
            # 7. Daily loss limit check
            if self.state.daily_pnl <= -self.limits.max_daily_loss:
                self.state.lock(f"Daily loss limit reached: ${self.state.daily_pnl:.2f}")
                return False, f"Daily loss limit reached: ${self.state.daily_pnl:.2f}"
            
            # 8. Drawdown check
            if self.state.starting_equity > 0:
                drawdown_pct = ((self.state.starting_equity - self.state.current_equity) / self.state.starting_equity) * 100
                if drawdown_pct > self.limits.max_drawdown_pct:
                    self.state.lock(f"Max drawdown exceeded: {drawdown_pct:.1f}%")
                    return False, f"Max drawdown {drawdown_pct:.1f}% exceeds limit {self.limits.max_drawdown_pct}%"
            
            # All checks passed
            return True, None
        
        except Exception as e:
            logger.error(f"Error in risk check: {e}", exc_info=True)
            return False, f"Risk check error: {e}"
    
    def check_signal(self, signal: Dict[str, Any]) -> bool:
        """
        Check if signal passes risk management (legacy method for compatibility).
        
        Args:
            signal: Signal dict with keys: symbol, signal, quantity, price
            
        Returns:
            True if signal passes risk checks
        """
        try:
            symbol = signal.get('symbol')
            side = signal.get('signal', 'BUY')  # signal field contains BUY/SELL
            qty = float(signal.get('quantity', signal.get('qty', 0)))
            price = float(signal.get('price', 0))
            
            allowed, reason = self.check_before_order(symbol, side, qty, price)
            
            if not allowed:
                logger.warning(f"Signal rejected by Risk Manager: {reason}")
            
            return allowed
        
        except Exception as e:
            logger.error(f"Error checking signal: {e}", exc_info=True)
            return False
    
    def update_after_execution(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        pnl: Optional[float] = None
    ):
        """
        Update risk state after execution.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            qty: Execution quantity
            price: Execution price
            pnl: P&L from execution (optional)
        """
        try:
            # Update state
            self.state.update_after_execution(symbol, side, qty, price, pnl)
            
            # Check for auto-lock conditions
            if self.state.daily_pnl <= -self.limits.max_daily_loss:
                self.state.lock(f"Daily loss limit reached: ${self.state.daily_pnl:.2f}")
            
            # Check for cooldown trigger
            if self.state.consecutive_losses >= self.limits.cooldown_after_losses:
                self.state.set_cooldown(self.limits.cooldown_duration_seconds)
                logger.warning(
                    f"Cooldown triggered: {self.state.consecutive_losses} consecutive losses"
                )
            
            # Update equity if position manager available
            if self.position_manager:
                positions = self.position_manager.get_all_positions()
                # Calculate total equity (simplified)
                # In production, get from account summary
                pass
        
        except Exception as e:
            logger.error(f"Error updating risk state after execution: {e}", exc_info=True)
    
    def is_locked(self) -> bool:
        """Check if risk manager is locked"""
        return self.state.locked
    
    def lock(self, reason: str):
        """Manually lock risk manager"""
        self.state.lock(reason)
    
    def unlock(self):
        """Manually unlock risk manager"""
        self.state.unlock()
    
    def get_state(self) -> Dict[str, Any]:
        """Get current risk state summary"""
        return self.state.get_state_summary()
    
    def reset_daily(self):
        """Reset daily metrics (call at start of trading day)"""
        self.state.reset_daily()

