"""
Decision Cooldown Manager - Production-Grade

Manages decision cooldowns per symbol to prevent rapid-fire decisions.
Tracks last decision timestamp and enforces minimum time between decisions.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional
from dataclasses import dataclass, field

from app.core.logger import logger


@dataclass
class DecisionCooldownManager:
    """
    Decision Cooldown Manager - prevents rapid-fire decisions.
    
    Responsibilities:
    - Track last decision timestamp per symbol
    - Enforce minimum cooldown period
    - Calculate time since last decision
    """
    
    def __init__(self, cooldown_minutes: float = 5.0):
        """
        Initialize Decision Cooldown Manager.
        
        Args:
            cooldown_minutes: Minimum minutes between decisions (default: 5.0)
        """
        self.cooldown_minutes = cooldown_minutes
        self.last_decision_ts: Dict[str, datetime] = {}  # symbol -> last_decision_ts
    
    def can_make_decision(self, symbol: str, current_ts: Optional[datetime] = None) -> bool:
        """
        Check if decision can be made for symbol (cooldown expired).
        
        Args:
            symbol: Symbol (PREF_IBKR)
            current_ts: Current timestamp (default: now)
            
        Returns:
            True if cooldown expired, False otherwise
        """
        if current_ts is None:
            current_ts = datetime.now()
        
        last_ts = self.last_decision_ts.get(symbol)
        if last_ts is None:
            return True  # No previous decision, allow
        
        # Calculate time since last decision
        time_since_last = (current_ts - last_ts).total_seconds() / 60.0  # minutes
        
        return time_since_last >= self.cooldown_minutes
    
    def get_time_since_last_decision(self, symbol: str, current_ts: Optional[datetime] = None) -> float:
        """
        Get time since last decision (in minutes).
        
        Args:
            symbol: Symbol (PREF_IBKR)
            current_ts: Current timestamp (default: now)
            
        Returns:
            Time since last decision in minutes (0.0 if no previous decision)
        """
        if current_ts is None:
            current_ts = datetime.now()
        
        last_ts = self.last_decision_ts.get(symbol)
        if last_ts is None:
            return 0.0
        
        return (current_ts - last_ts).total_seconds() / 60.0
    
    def record_decision(self, symbol: str, decision_ts: Optional[datetime] = None):
        """
        Record decision timestamp for symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            decision_ts: Decision timestamp (default: now)
        """
        if decision_ts is None:
            decision_ts = datetime.now()
        
        self.last_decision_ts[symbol] = decision_ts
        logger.debug(f"Decision recorded for {symbol} at {decision_ts.isoformat()}")
    
    def set_decision_ts(self, symbol: str, decision_ts: datetime):
        """
        Set decision timestamp for symbol (for testing).
        
        Args:
            symbol: Symbol (PREF_IBKR)
            decision_ts: Decision timestamp
        """
        self.last_decision_ts[symbol] = decision_ts
        logger.debug(f"Decision timestamp set for {symbol} at {decision_ts.isoformat()}")
    
    def clear_cooldown(self, symbol: str):
        """Clear cooldown for symbol (for testing or manual override)"""
        if symbol in self.last_decision_ts:
            del self.last_decision_ts[symbol]
            logger.debug(f"Cooldown cleared for {symbol}")
    
    def clear_all_cooldowns(self):
        """Clear all cooldowns (for testing or reset)"""
        self.last_decision_ts.clear()
        logger.debug("All cooldowns cleared")


# Global instance
_decision_cooldown_manager: Optional[DecisionCooldownManager] = None


def get_decision_cooldown_manager() -> Optional[DecisionCooldownManager]:
    """Get global DecisionCooldownManager instance"""
    return _decision_cooldown_manager


def initialize_decision_cooldown_manager(cooldown_minutes: float = 5.0):
    """Initialize global DecisionCooldownManager instance"""
    global _decision_cooldown_manager
    _decision_cooldown_manager = DecisionCooldownManager(cooldown_minutes=cooldown_minutes)
    logger.info(f"DecisionCooldownManager initialized (cooldown={cooldown_minutes} minutes)")

