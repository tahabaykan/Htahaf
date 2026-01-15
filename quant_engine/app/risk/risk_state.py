"""app/risk/risk_state.py

Risk state tracking - tracks dynamic risk metrics.
Updated after each execution and used for risk checks.
"""

import time
from typing import Dict, Optional
from collections import deque

from app.core.logger import logger


class RiskState:
    """
    Tracks dynamic risk state.
    
    This class maintains real-time risk metrics that are updated
    after each trade execution.
    """
    
    def __init__(self):
        # P&L tracking
        self.daily_pnl: float = 0.0
        self.unrealized_pnl: float = 0.0
        self.realized_pnl: float = 0.0
        self.starting_equity: float = 0.0
        self.current_equity: float = 0.0
        
        # Trade counting
        self.trade_count: int = 0
        self.trades_last_minute: deque = deque(maxlen=100)  # Timestamps
        self.trades_last_hour: deque = deque(maxlen=1000)
        self.trades_today: deque = deque(maxlen=10000)
        
        # Exposure tracking
        self.exposure_per_symbol: Dict[str, float] = {}
        self.total_exposure: float = 0.0
        
        # Circuit breaker state
        self.locked: bool = False
        self.lock_reason: Optional[str] = None
        self.lock_timestamp: Optional[float] = None
        
        # Cooldown state
        self.consecutive_losses: int = 0
        self.cooldown_until: Optional[float] = None
        
        # Price volatility tracking (for circuit breaker)
        self.price_changes: Dict[str, deque] = {}  # symbol -> deque of (timestamp, price_change_pct)
        
        # Timestamps
        self.last_reset_timestamp: float = time.time()
        self.last_update_timestamp: float = time.time()
    
    def update_after_execution(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        pnl: Optional[float] = None
    ):
        """
        Update state after execution.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            qty: Execution quantity
            price: Execution price
            pnl: P&L from this execution (if available)
        """
        try:
            now = time.time()
            
            # Update trade count
            self.trade_count += 1
            self.trades_last_minute.append(now)
            self.trades_last_hour.append(now)
            self.trades_today.append(now)
            
            # Update P&L
            if pnl is not None:
                self.realized_pnl += pnl
                self.daily_pnl += pnl
                
                # Track consecutive losses
                if pnl < 0:
                    self.consecutive_losses += 1
                else:
                    self.consecutive_losses = 0
            
            # Update exposure
            exposure_change = qty * price
            if side.upper() == "BUY":
                self.exposure_per_symbol[symbol] = self.exposure_per_symbol.get(symbol, 0) + exposure_change
            else:
                self.exposure_per_symbol[symbol] = self.exposure_per_symbol.get(symbol, 0) - exposure_change
            
            # Update total exposure
            self.total_exposure = sum(abs(v) for v in self.exposure_per_symbol.values())
            
            # Update timestamp
            self.last_update_timestamp = now
            
            # Check minute rollover
            self.check_minute_rollover()
            
        except Exception as e:
            logger.error(f"Error updating risk state: {e}", exc_info=True)
    
    def update_exposure(self, symbol: str, exposure: float):
        """
        Update exposure for a symbol.
        
        Args:
            symbol: Stock symbol
            exposure: Exposure amount (positive = long, negative = short)
        """
        self.exposure_per_symbol[symbol] = exposure
        self.total_exposure = sum(abs(v) for v in self.exposure_per_symbol.values())
    
    def update_pnl(self, unrealized_pnl: float, realized_pnl: Optional[float] = None):
        """
        Update P&L metrics.
        
        Args:
            unrealized_pnl: Unrealized P&L
            realized_pnl: Realized P&L (optional, will be added to existing)
        """
        self.unrealized_pnl = unrealized_pnl
        if realized_pnl is not None:
            self.realized_pnl = realized_pnl
            self.daily_pnl = self.realized_pnl + self.unrealized_pnl
    
    def update_equity(self, current_equity: float):
        """Update current equity"""
        if self.starting_equity == 0:
            self.starting_equity = current_equity
        self.current_equity = current_equity
    
    def check_minute_rollover(self):
        """Remove old trades from minute/hour tracking"""
        now = time.time()
        
        # Remove trades older than 1 minute
        while self.trades_last_minute and now - self.trades_last_minute[0] > 60:
            self.trades_last_minute.popleft()
        
        # Remove trades older than 1 hour
        while self.trades_last_hour and now - self.trades_last_hour[0] > 3600:
            self.trades_last_hour.popleft()
    
    def get_trades_last_minute(self) -> int:
        """Get number of trades in last minute"""
        self.check_minute_rollover()
        return len(self.trades_last_minute)
    
    def get_trades_last_hour(self) -> int:
        """Get number of trades in last hour"""
        self.check_minute_rollover()
        return len(self.trades_last_hour)
    
    def get_trades_today(self) -> int:
        """Get number of trades today"""
        return len(self.trades_today)
    
    def reset_daily(self):
        """Reset daily metrics (called at start of trading day)"""
        self.daily_pnl = 0.0
        self.trade_count = 0
        self.trades_today.clear()
        self.consecutive_losses = 0
        self.cooldown_until = None
        self.last_reset_timestamp = time.time()
        logger.info("Risk state reset for new trading day")
    
    def lock(self, reason: str):
        """
        Lock trading (circuit breaker).
        
        Args:
            reason: Lock reason
        """
        self.locked = True
        self.lock_reason = reason
        self.lock_timestamp = time.time()
        logger.warning(f"Risk Manager LOCKED: {reason}")
    
    def unlock(self):
        """Unlock trading"""
        self.locked = False
        self.lock_reason = None
        self.lock_timestamp = None
        logger.info("Risk Manager UNLOCKED")
    
    def set_cooldown(self, duration_seconds: int):
        """Set cooldown period"""
        self.cooldown_until = time.time() + duration_seconds
        logger.info(f"Cooldown set for {duration_seconds} seconds")
    
    def is_in_cooldown(self) -> bool:
        """Check if in cooldown period"""
        if self.cooldown_until is None:
            return False
        if time.time() >= self.cooldown_until:
            self.cooldown_until = None
            return False
        return True
    
    def track_price_change(self, symbol: str, price_change_pct: float):
        """
        Track price change for circuit breaker.
        
        Args:
            symbol: Stock symbol
            price_change_pct: Price change percentage
        """
        if symbol not in self.price_changes:
            self.price_changes[symbol] = deque(maxlen=100)
        
        now = time.time()
        self.price_changes[symbol].append((now, price_change_pct))
    
    def get_recent_price_volatility(self, symbol: str, window_seconds: int = 60) -> Optional[float]:
        """
        Get recent price volatility for circuit breaker.
        
        Args:
            symbol: Stock symbol
            window_seconds: Time window
            
        Returns:
            Maximum price change percentage in window, or None
        """
        if symbol not in self.price_changes:
            return None
        
        now = time.time()
        changes = [
            pct for ts, pct in self.price_changes[symbol]
            if now - ts <= window_seconds
        ]
        
        if not changes:
            return None
        
        return max(abs(c) for c in changes)
    
    def get_state_summary(self) -> Dict:
        """Get risk state summary"""
        return {
            'daily_pnl': self.daily_pnl,
            'unrealized_pnl': self.unrealized_pnl,
            'realized_pnl': self.realized_pnl,
            'trade_count': self.trade_count,
            'trades_last_minute': self.get_trades_last_minute(),
            'trades_last_hour': self.get_trades_last_hour(),
            'total_exposure': self.total_exposure,
            'locked': self.locked,
            'lock_reason': self.lock_reason,
            'in_cooldown': self.is_in_cooldown(),
            'consecutive_losses': self.consecutive_losses
        }








