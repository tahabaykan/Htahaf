"""
Guardrails - Janall-Compatible Safety Checks

Implements safety checks before order execution:
- MAXALW: Company exposure limits
- Daily Limits: Max daily lot change, order count
- Position Limits: Max position per symbol, total positions
- Duplicate Prevention: Prevent duplicate orders

Janall Logic:
- Check MAXALW before each order
- Track daily lot changes per symbol
- Prevent duplicate orders within cooldown window
"""

import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

from app.core.logger import logger


@dataclass
class GuardrailsConfig:
    """Guardrails configuration"""
    # MAXALW
    maxalw_enabled: bool = True
    max_company_exposure_percent: float = 100.0
    
    # BEFDAY + MAXALW Multiplier (JANALL)
    # max_change_limit = maxalw * multiplier
    # Daily change from befday position must not exceed max_change_limit
    befday_maxalw_enabled: bool = True
    maxalw_multiplier: float = 0.75  # Default 75% of MAXALW
    
    # Daily Limits
    daily_limits_enabled: bool = True
    max_daily_lot_change: int = 10000
    max_daily_lot_change_per_symbol: int = 2000
    max_daily_orders: int = 500
    reset_time: str = "09:30:00"
    
    # Order Limits
    max_open_orders: int = 100
    max_open_orders_per_symbol: int = 5
    max_order_value: float = 100000.0
    
    # Duplicate Prevention
    duplicate_prevention_enabled: bool = True
    duplicate_window_seconds: int = 60
    same_symbol_cooldown_seconds: int = 300
    
    # Position Limits
    position_limits_enabled: bool = True
    max_position_per_symbol: int = 2000
    max_total_positions: int = 200
    max_sector_exposure_percent: float = 30.0


@dataclass
class GuardrailCheck:
    """Result of a guardrail check"""
    passed: bool
    check_name: str
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


class Guardrails:
    """
    Guardrails - safety checks before order execution.
    
    Features:
    - MAXALW check (company exposure)
    - Daily limits (lot change, order count)
    - Position limits
    - Duplicate prevention
    - Thread-safe operations
    """
    
    def __init__(self, config: Optional[GuardrailsConfig] = None):
        """
        Initialize Guardrails.
        
        Args:
            config: GuardrailsConfig object
        """
        self.config = config or GuardrailsConfig()
        
        # Tracking data
        self._lock = threading.RLock()
        
        # Daily tracking
        self._daily_lot_changes: Dict[str, int] = {}  # symbol -> lot change
        self._daily_order_count: int = 0
        self._daily_reset_date: Optional[datetime] = None
        
        # Recent orders (for duplicate prevention)
        self._recent_orders: List[Dict[str, Any]] = []
        
        # Open orders
        self._open_orders: Dict[str, int] = {}  # symbol -> count
        self._total_open_orders: int = 0
        
        # Position tracking
        self._positions: Dict[str, float] = {}  # symbol -> qty
        
        # BEFDAY tracking (gün başı pozisyonları)
        self._befday_positions: Dict[str, float] = {}  # symbol -> befday_qty
        
        logger.info(
            f"Guardrails initialized: maxalw={self.config.maxalw_enabled}, "
            f"befday_maxalw={self.config.befday_maxalw_enabled}, "
            f"daily_limits={self.config.daily_limits_enabled}, "
            f"duplicate_prevention={self.config.duplicate_prevention_enabled}"
        )
    
    def check_all(
        self,
        symbol: str,
        action: str,
        lot_qty: int,
        price: Optional[float] = None,
        maxalw: Optional[float] = None,
        current_position: Optional[float] = None,
        befday_position: Optional[float] = None,
        sector: Optional[str] = None
    ) -> Tuple[bool, List[GuardrailCheck]]:
        """
        Run all guardrail checks.
        
        Args:
            symbol: Symbol string
            action: BUY, SELL, SHORT, COVER
            lot_qty: Order lot quantity
            price: Order price (optional)
            maxalw: MAXALW value (optional)
            current_position: Current position qty (optional)
            befday_position: Position at start of day (optional, for BEFDAY check)
            sector: Sector (optional)
            
        Returns:
            (all_passed, list of GuardrailCheck results)
        """
        checks = []
        
        # Check daily reset
        self._check_daily_reset()
        
        # MAXALW Check
        if self.config.maxalw_enabled and maxalw is not None:
            check = self._check_maxalw(symbol, action, lot_qty, maxalw, current_position)
            checks.append(check)
        
        # BEFDAY + MAXALW Multiplier Check (JANALL)
        if self.config.befday_maxalw_enabled and maxalw is not None:
            # Use provided befday_position or lookup from stored values
            bef_pos = befday_position if befday_position is not None else self._befday_positions.get(symbol, 0)
            check = self._check_befday_maxalw(symbol, action, lot_qty, maxalw, current_position, bef_pos)
            checks.append(check)
        
        # Daily Limits Check
        if self.config.daily_limits_enabled:
            check = self._check_daily_limits(symbol, lot_qty)
            checks.append(check)
        
        # Order Limits Check
        check = self._check_order_limits(symbol)
        checks.append(check)
        
        # Duplicate Prevention Check
        if self.config.duplicate_prevention_enabled:
            check = self._check_duplicate(symbol, action, lot_qty)
            checks.append(check)
        
        # Position Limits Check
        if self.config.position_limits_enabled:
            check = self._check_position_limits(symbol, action, lot_qty, current_position)
            checks.append(check)
        
        # Order Value Check
        if price is not None:
            check = self._check_order_value(symbol, lot_qty, price)
            checks.append(check)
        
        # Determine overall result
        all_passed = all(c.passed for c in checks)
        
        if not all_passed:
            failed_checks = [c for c in checks if not c.passed]
            logger.warning(
                f"[GUARDRAILS] {symbol} {action} {lot_qty}: BLOCKED - "
                f"{', '.join(c.check_name for c in failed_checks)}"
            )
        
        return all_passed, checks
    
    def _check_daily_reset(self):
        """Check if daily tracking should be reset"""
        now = datetime.now()
        
        # Parse reset time
        try:
            reset_hour, reset_minute, reset_second = map(int, self.config.reset_time.split(':'))
            reset_time_today = now.replace(hour=reset_hour, minute=reset_minute, second=reset_second, microsecond=0)
        except:
            reset_time_today = now.replace(hour=9, minute=30, second=0, microsecond=0)
        
        with self._lock:
            # Reset if:
            # 1. Never reset before
            # 2. Last reset was before today's reset time and now is after
            should_reset = False
            
            if self._daily_reset_date is None:
                should_reset = True
            elif self._daily_reset_date.date() < now.date():
                should_reset = True
            elif self._daily_reset_date < reset_time_today and now >= reset_time_today:
                should_reset = True
            
            if should_reset:
                self._daily_lot_changes.clear()
                self._daily_order_count = 0
                self._daily_reset_date = now
                logger.info("[GUARDRAILS] Daily tracking reset")
    
    def _check_maxalw(
        self,
        symbol: str,
        action: str,
        lot_qty: int,
        maxalw: float,
        current_position: Optional[float]
    ) -> GuardrailCheck:
        """
        Check MAXALW (company exposure limit).
        
        Janall logic:
        - Position should not exceed MAXALW
        """
        current = current_position or 0
        
        # Calculate new position
        if action in ['BUY', 'ADD']:
            new_position = current + lot_qty
        elif action in ['SELL']:
            new_position = current - lot_qty
        elif action in ['SHORT', 'ADD_SHORT']:
            new_position = current - lot_qty
        elif action in ['COVER']:
            new_position = current + lot_qty
        else:
            new_position = current
        
        # Check against MAXALW
        max_allowed = maxalw * (self.config.max_company_exposure_percent / 100.0)
        
        if abs(new_position) > max_allowed:
            return GuardrailCheck(
                passed=False,
                check_name="MAXALW",
                reason=f"Position {abs(new_position):.0f} would exceed MAXALW {max_allowed:.0f}",
                details={
                    'current_position': current,
                    'lot_qty': lot_qty,
                    'new_position': new_position,
                    'maxalw': maxalw,
                    'max_allowed': max_allowed
                }
            )
        
        return GuardrailCheck(
            passed=True,
            check_name="MAXALW",
            details={'new_position': new_position, 'max_allowed': max_allowed}
        )
    
    def _check_befday_maxalw(
        self,
        symbol: str,
        action: str,
        lot_qty: int,
        maxalw: float,
        current_position: Optional[float],
        befday_position: float
    ) -> GuardrailCheck:
        """
        Check BEFDAY + MAXALW multiplier limit (JANALL logic).
        
        Janall logic:
        - max_change_limit = maxalw * multiplier (default 0.75)
        - befday_qty = gün başı pozisyon
        - potential_daily_change = abs(new_potential - befday_qty)
        - if potential_daily_change > max_change_limit: BLOCK
        
        This prevents excessive daily position changes relative to MAXALW.
        """
        current = current_position or 0
        
        # Calculate new position after this order
        if action in ['BUY', 'ADD']:
            new_position = current + lot_qty
        elif action in ['SELL']:
            new_position = current - lot_qty
        elif action in ['SHORT', 'ADD_SHORT']:
            new_position = current - lot_qty
        elif action in ['COVER']:
            new_position = current + lot_qty
        else:
            new_position = current
        
        # Calculate max daily change limit
        max_change_limit = maxalw * self.config.maxalw_multiplier
        
        # Calculate potential daily change from befday position
        potential_daily_change = abs(new_position - befday_position)
        
        if potential_daily_change > max_change_limit:
            return GuardrailCheck(
                passed=False,
                check_name="BEFDAY_MAXALW",
                reason=f"Daily change {potential_daily_change:.0f} would exceed MAXALW*{self.config.maxalw_multiplier} limit {max_change_limit:.0f}",
                details={
                    'befday_position': befday_position,
                    'current_position': current,
                    'new_position': new_position,
                    'potential_daily_change': potential_daily_change,
                    'maxalw': maxalw,
                    'multiplier': self.config.maxalw_multiplier,
                    'max_change_limit': max_change_limit
                }
            )
        
        return GuardrailCheck(
            passed=True,
            check_name="BEFDAY_MAXALW",
            details={
                'befday_position': befday_position,
                'new_position': new_position,
                'potential_daily_change': potential_daily_change,
                'max_change_limit': max_change_limit
            }
        )
    
    def _check_daily_limits(self, symbol: str, lot_qty: int) -> GuardrailCheck:
        """
        Check daily limits.
        
        Janall logic:
        - Max daily lot change per symbol
        - Max daily lot change total
        - Max daily order count
        """
        with self._lock:
            # Check symbol daily limit
            current_symbol_change = self._daily_lot_changes.get(symbol, 0)
            new_symbol_change = current_symbol_change + lot_qty
            
            if abs(new_symbol_change) > self.config.max_daily_lot_change_per_symbol:
                return GuardrailCheck(
                    passed=False,
                    check_name="DAILY_SYMBOL_LIMIT",
                    reason=f"Symbol daily change {abs(new_symbol_change)} would exceed limit {self.config.max_daily_lot_change_per_symbol}",
                    details={
                        'current_change': current_symbol_change,
                        'lot_qty': lot_qty,
                        'limit': self.config.max_daily_lot_change_per_symbol
                    }
                )
            
            # Check total daily limit
            total_change = sum(self._daily_lot_changes.values()) + lot_qty
            if abs(total_change) > self.config.max_daily_lot_change:
                return GuardrailCheck(
                    passed=False,
                    check_name="DAILY_TOTAL_LIMIT",
                    reason=f"Total daily change {abs(total_change)} would exceed limit {self.config.max_daily_lot_change}",
                    details={
                        'current_total': sum(self._daily_lot_changes.values()),
                        'lot_qty': lot_qty,
                        'limit': self.config.max_daily_lot_change
                    }
                )
            
            # Check order count
            if self._daily_order_count >= self.config.max_daily_orders:
                return GuardrailCheck(
                    passed=False,
                    check_name="DAILY_ORDER_COUNT",
                    reason=f"Daily order count {self._daily_order_count} at limit {self.config.max_daily_orders}",
                    details={
                        'current_count': self._daily_order_count,
                        'limit': self.config.max_daily_orders
                    }
                )
        
        return GuardrailCheck(
            passed=True,
            check_name="DAILY_LIMITS"
        )
    
    def _check_order_limits(self, symbol: str) -> GuardrailCheck:
        """Check open order limits"""
        with self._lock:
            # Check total open orders
            if self._total_open_orders >= self.config.max_open_orders:
                return GuardrailCheck(
                    passed=False,
                    check_name="MAX_OPEN_ORDERS",
                    reason=f"Total open orders {self._total_open_orders} at limit {self.config.max_open_orders}",
                    details={
                        'current': self._total_open_orders,
                        'limit': self.config.max_open_orders
                    }
                )
            
            # Check per-symbol open orders
            symbol_orders = self._open_orders.get(symbol, 0)
            if symbol_orders >= self.config.max_open_orders_per_symbol:
                return GuardrailCheck(
                    passed=False,
                    check_name="MAX_SYMBOL_ORDERS",
                    reason=f"Symbol open orders {symbol_orders} at limit {self.config.max_open_orders_per_symbol}",
                    details={
                        'symbol': symbol,
                        'current': symbol_orders,
                        'limit': self.config.max_open_orders_per_symbol
                    }
                )
        
        return GuardrailCheck(
            passed=True,
            check_name="ORDER_LIMITS"
        )
    
    def _check_duplicate(self, symbol: str, action: str, lot_qty: int) -> GuardrailCheck:
        """
        Check for duplicate orders.
        
        Janall logic:
        - Prevent same order within duplicate_window_seconds
        - Prevent any order for same symbol within cooldown_seconds
        """
        now = datetime.now()
        
        with self._lock:
            # Clean old entries
            cutoff = now - timedelta(seconds=max(
                self.config.duplicate_window_seconds,
                self.config.same_symbol_cooldown_seconds
            ))
            self._recent_orders = [
                o for o in self._recent_orders
                if o['timestamp'] > cutoff
            ]
            
            # Check for exact duplicate
            duplicate_cutoff = now - timedelta(seconds=self.config.duplicate_window_seconds)
            for order in self._recent_orders:
                if order['timestamp'] > duplicate_cutoff:
                    if (order['symbol'] == symbol and 
                        order['action'] == action and 
                        order['lot_qty'] == lot_qty):
                        return GuardrailCheck(
                            passed=False,
                            check_name="DUPLICATE_ORDER",
                            reason=f"Duplicate order within {self.config.duplicate_window_seconds}s",
                            details={
                                'previous_timestamp': order['timestamp'].isoformat(),
                                'window_seconds': self.config.duplicate_window_seconds
                            }
                        )
            
            # Check for same symbol cooldown
            cooldown_cutoff = now - timedelta(seconds=self.config.same_symbol_cooldown_seconds)
            for order in self._recent_orders:
                if order['timestamp'] > cooldown_cutoff:
                    if order['symbol'] == symbol:
                        time_since = (now - order['timestamp']).total_seconds()
                        time_remaining = self.config.same_symbol_cooldown_seconds - time_since
                        return GuardrailCheck(
                            passed=False,
                            check_name="SYMBOL_COOLDOWN",
                            reason=f"Symbol cooldown active ({time_remaining:.0f}s remaining)",
                            details={
                                'previous_timestamp': order['timestamp'].isoformat(),
                                'cooldown_seconds': self.config.same_symbol_cooldown_seconds,
                                'time_remaining': time_remaining
                            }
                        )
        
        return GuardrailCheck(
            passed=True,
            check_name="DUPLICATE_PREVENTION"
        )
    
    def _check_position_limits(
        self,
        symbol: str,
        action: str,
        lot_qty: int,
        current_position: Optional[float]
    ) -> GuardrailCheck:
        """Check position limits"""
        current = current_position or 0
        
        # Calculate new position
        if action in ['BUY', 'ADD']:
            new_position = current + lot_qty
        elif action in ['SELL']:
            new_position = current - lot_qty
        elif action in ['SHORT', 'ADD_SHORT']:
            new_position = current - lot_qty
        elif action in ['COVER']:
            new_position = current + lot_qty
        else:
            new_position = current
        
        # Check max position per symbol
        if abs(new_position) > self.config.max_position_per_symbol:
            return GuardrailCheck(
                passed=False,
                check_name="MAX_POSITION",
                reason=f"Position {abs(new_position):.0f} would exceed limit {self.config.max_position_per_symbol}",
                details={
                    'current': current,
                    'new_position': new_position,
                    'limit': self.config.max_position_per_symbol
                }
            )
        
        return GuardrailCheck(
            passed=True,
            check_name="POSITION_LIMITS"
        )
    
    def _check_order_value(self, symbol: str, lot_qty: int, price: float) -> GuardrailCheck:
        """Check order value limit"""
        order_value = lot_qty * price
        
        if order_value > self.config.max_order_value:
            return GuardrailCheck(
                passed=False,
                check_name="MAX_ORDER_VALUE",
                reason=f"Order value ${order_value:,.2f} exceeds limit ${self.config.max_order_value:,.2f}",
                details={
                    'lot_qty': lot_qty,
                    'price': price,
                    'order_value': order_value,
                    'limit': self.config.max_order_value
                }
            )
        
        return GuardrailCheck(
            passed=True,
            check_name="ORDER_VALUE"
        )
    
    # ========== Tracking Updates ==========
    
    def record_order(self, symbol: str, action: str, lot_qty: int):
        """Record an order for tracking"""
        with self._lock:
            # Update daily tracking
            lot_change = lot_qty if action in ['BUY', 'ADD', 'COVER'] else -lot_qty
            self._daily_lot_changes[symbol] = self._daily_lot_changes.get(symbol, 0) + lot_change
            self._daily_order_count += 1
            
            # Add to recent orders
            self._recent_orders.append({
                'symbol': symbol,
                'action': action,
                'lot_qty': lot_qty,
                'timestamp': datetime.now()
            })
            
            # Update open orders
            self._open_orders[symbol] = self._open_orders.get(symbol, 0) + 1
            self._total_open_orders += 1
    
    def record_order_complete(self, symbol: str):
        """Record order completion"""
        with self._lock:
            if symbol in self._open_orders:
                self._open_orders[symbol] = max(0, self._open_orders[symbol] - 1)
            self._total_open_orders = max(0, self._total_open_orders - 1)
    
    def update_position(self, symbol: str, qty: float):
        """Update position tracking"""
        with self._lock:
            self._positions[symbol] = qty
    
    def set_befday_position(self, symbol: str, qty: float):
        """
        Set BEFDAY (start of day) position for a symbol.
        
        Called when loading befday CSV or at market open.
        """
        with self._lock:
            self._befday_positions[symbol] = qty
    
    def set_befday_positions(self, positions: Dict[str, float]):
        """
        Set multiple BEFDAY positions at once.
        
        Args:
            positions: Dict mapping symbol -> befday quantity
        """
        with self._lock:
            self._befday_positions.update(positions)
            logger.info(f"[GUARDRAILS] Loaded {len(positions)} BEFDAY positions")
    
    def get_befday_position(self, symbol: str) -> float:
        """Get BEFDAY position for a symbol"""
        with self._lock:
            return self._befday_positions.get(symbol, 0)
    
    def clear_befday_positions(self):
        """Clear all BEFDAY positions (called at daily reset)"""
        with self._lock:
            self._befday_positions.clear()
            logger.info("[GUARDRAILS] BEFDAY positions cleared")
    
    def get_status(self) -> Dict[str, Any]:
        """Get guardrails status"""
        with self._lock:
            return {
                'daily_order_count': self._daily_order_count,
                'daily_lot_changes': dict(self._daily_lot_changes),
                'total_open_orders': self._total_open_orders,
                'open_orders_by_symbol': dict(self._open_orders),
                'recent_orders_count': len(self._recent_orders),
                'befday_positions_count': len(self._befday_positions),
                'config': {
                    'maxalw_enabled': self.config.maxalw_enabled,
                    'befday_maxalw_enabled': self.config.befday_maxalw_enabled,
                    'maxalw_multiplier': self.config.maxalw_multiplier,
                    'daily_limits_enabled': self.config.daily_limits_enabled,
                    'duplicate_prevention_enabled': self.config.duplicate_prevention_enabled,
                    'max_daily_lot_change': self.config.max_daily_lot_change,
                    'max_daily_orders': self.config.max_daily_orders
                }
            }


# ============================================================================
# Global Instance Management
# ============================================================================

_guardrails: Optional[Guardrails] = None


def get_guardrails() -> Optional[Guardrails]:
    """Get global Guardrails instance"""
    return _guardrails


def initialize_guardrails(config: Optional[Dict[str, Any]] = None) -> Guardrails:
    """Initialize global Guardrails instance"""
    global _guardrails
    
    if config:
        gr_config = GuardrailsConfig(
            maxalw_enabled=config.get('maxalw', {}).get('company_limit_enabled', True),
            max_company_exposure_percent=config.get('maxalw', {}).get('max_company_exposure_percent', 100.0),
            # BEFDAY + MAXALW Multiplier (JANALL)
            befday_maxalw_enabled=config.get('befday', {}).get('maxalw_limit_enabled', True),
            maxalw_multiplier=config.get('befday', {}).get('maxalw_multiplier', 0.75),
            daily_limits_enabled=config.get('daily_limits', {}).get('enabled', True),
            max_daily_lot_change=config.get('daily_limits', {}).get('max_daily_lot_change', 10000),
            max_daily_lot_change_per_symbol=config.get('daily_limits', {}).get('max_daily_lot_change_per_symbol', 2000),
            max_daily_orders=config.get('daily_limits', {}).get('max_daily_orders', 500),
            reset_time=config.get('daily_limits', {}).get('reset_time', '09:30:00'),
            max_open_orders=config.get('order_limits', {}).get('max_open_orders', 100),
            max_open_orders_per_symbol=config.get('order_limits', {}).get('max_open_orders_per_symbol', 5),
            max_order_value=config.get('order_limits', {}).get('max_order_value', 100000),
            duplicate_prevention_enabled=config.get('duplicate_prevention', {}).get('enabled', True),
            duplicate_window_seconds=config.get('duplicate_prevention', {}).get('duplicate_intent_window_seconds', 60),
            same_symbol_cooldown_seconds=config.get('duplicate_prevention', {}).get('same_symbol_cooldown_seconds', 300),
            position_limits_enabled=config.get('position_limits', {}).get('enabled', True),
            max_position_per_symbol=config.get('position_limits', {}).get('max_position_per_symbol', 2000),
            max_total_positions=config.get('position_limits', {}).get('max_total_positions', 200)
        )
    else:
        gr_config = GuardrailsConfig()
    
    _guardrails = Guardrails(config=gr_config)
    logger.info("Guardrails initialized (Janall-compatible with BEFDAY+MAXALW)")
    return _guardrails

