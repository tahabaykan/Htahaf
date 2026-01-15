"""
Order Lifecycle Policy - TTL, Selective Cancel, Replace Policy

Implements:
- TTL per intent_category
- Replace policy (>= 1 tick change OR reason change)
- Stale detection (data age > 90s)
- Selective cancel engine (KEEP/REPLACE/CANCEL per order)
"""

import time
from typing import Dict, Any, List, Tuple, Optional
from enum import Enum
from dataclasses import dataclass
from app.core.logger import logger


class OrderAction(Enum):
    KEEP = "KEEP"
    REPLACE = "REPLACE"
    CANCEL = "CANCEL"


@dataclass
class OrderDecision:
    """Decision for a single order."""
    order_id: str
    symbol: str
    action: OrderAction
    reason: str
    new_price: Optional[float] = None
    new_qty: Optional[int] = None


class OrderLifecyclePolicy:
    """
    Manages order TTL, replacement, and selective cancellation.
    
    NO mass cancel by default. Only cancel:
    a) TTL expired
    b) Order stale/invalid relative to latest truth
    c) Risk regime forces (HARD_DERISK / close-time)
    d) Symbol disabled / excluded
    """
    
    # Default TTLs by intent category (seconds)
    DEFAULT_TTLS = {
        'LT_TRIM': 120,       # 2 minutes
        'MM_CHURN': 60,       # 1 minute
        'ADDNEWPOS': 180,     # 3 minutes
        'HARD_DERISK': 30,    # 30 seconds (urgent)
        'CLOSE_EXIT': 15,     # 15 seconds (very urgent)
        'DEFAULT': 90,        # Default fallback
    }
    
    # Minimum time between replaces (seconds)
    MIN_REPLACE_INTERVAL = 2.5
    
    # Price change threshold for replace (cents)
    PRICE_CHANGE_THRESHOLD = 0.01  # 1 tick
    
    # Data age threshold for stale (seconds)
    STALE_DATA_THRESHOLD = 90.0
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.ttls = self.config.get('ORDER_TTL_BY_CATEGORY', self.DEFAULT_TTLS)
        self.selective_cancel_enabled = self.config.get('SELECTIVE_CANCEL_ENABLED', True)
    
    def get_ttl(self, intent_category: str) -> float:
        """Get TTL for an intent category."""
        return self.ttls.get(intent_category, self.ttls.get('DEFAULT', 90))
    
    def should_replace(
        self,
        old_price: float,
        new_price: float,
        old_reason: str,
        new_reason: str,
        last_replace_ts: float
    ) -> Tuple[bool, str]:
        """
        Determine if an order should be replaced.
        
        Returns (should_replace, reason)
        """
        now = time.time()
        
        # Check min replace interval
        if last_replace_ts > 0 and (now - last_replace_ts) < self.MIN_REPLACE_INTERVAL:
            return False, "MIN_REPLACE_INTERVAL_NOT_MET"
        
        # Price change >= 1 tick
        price_diff = abs(new_price - old_price)
        if price_diff >= self.PRICE_CHANGE_THRESHOLD:
            return True, f"PRICE_CHANGED_{price_diff:.2f}c"
        
        # Reason changed materially
        if old_reason != new_reason:
            # Only replace if reason is truly different category
            old_base = old_reason.split('_')[0] if old_reason else ""
            new_base = new_reason.split('_')[0] if new_reason else ""
            if old_base != new_base:
                return True, f"REASON_CHANGED_{old_reason}_TO_{new_reason}"
        
        return False, "NO_CHANGE"
    
    def is_order_valid(
        self,
        order_side: str,
        order_price: float,
        position_qty: int,
        bid: float,
        ask: float,
        regime: str
    ) -> Tuple[bool, str]:
        """
        Check if an order is still valid given current state.
        
        Returns (is_valid, reason_if_invalid)
        """
        # Regime-based invalidation
        if regime == "HARD_DERISK":
            # During HARD_DERISK, only reduction orders are valid
            is_reduction = (order_side == "SELL" and position_qty > 0) or \
                          (order_side == "BUY" and position_qty < 0)
            if not is_reduction:
                return False, "HARD_DERISK_NO_NEW_POSITIONS"
        
        if regime == "CLOSE":
            # During CLOSE, only exit orders valid
            is_exit = (order_side == "SELL" and position_qty > 0) or \
                     (order_side == "BUY" and position_qty < 0)
            if not is_exit:
                return False, "CLOSE_ONLY_EXIT_ALLOWED"
        
        # Price validity (order price should be within reasonable range)
        if bid > 0 and ask > 0:
            spread = ask - bid
            mid = (bid + ask) / 2
            
            # SELL order should be near/above mid
            if order_side == "SELL":
                if order_price < bid - spread:  # Way below even bid
                    return False, "SELL_PRICE_TOO_LOW"
            
            # BUY order should be near/below mid
            if order_side == "BUY":
                if order_price > ask + spread:  # Way above even ask
                    return False, "BUY_PRICE_TOO_HIGH"
        
        return True, ""
    
    def evaluate_orders(
        self,
        active_orders: List[Dict[str, Any]],
        symbol_states: Dict[str, Dict[str, Any]],
        regime: str,
        excluded_symbols: set
    ) -> List[OrderDecision]:
        """
        Evaluate all active orders and decide KEEP/REPLACE/CANCEL for each.
        
        This is the selective cancel engine - NO mass cancel.
        """
        decisions = []
        
        for order in active_orders:
            order_id = order.get('order_id')
            symbol = order.get('symbol')
            side = order.get('side')
            price = order.get('price', 0)
            qty = order.get('qty', 0)
            intent_category = order.get('intent_category', 'DEFAULT')
            created_ts = order.get('created_ts', 0)
            last_replace_ts = order.get('last_replace_ts', 0)
            
            state = symbol_states.get(symbol, {})
            position_qty = state.get('position_qty', 0)
            bid = state.get('bid', 0)
            ask = state.get('ask', 0)
            truth_age = state.get('truth_age', 999)
            is_excluded = symbol in excluded_symbols
            
            # ==== DECISION LOGIC ====
            
            # 1. Excluded symbol => CANCEL
            if is_excluded:
                decisions.append(OrderDecision(
                    order_id=order_id,
                    symbol=symbol,
                    action=OrderAction.CANCEL,
                    reason="SYMBOL_EXCLUDED"
                ))
                continue
            
            # 2. TTL expired => CANCEL
            ttl = self.get_ttl(intent_category)
            if created_ts > 0 and (time.time() - created_ts) > ttl:
                decisions.append(OrderDecision(
                    order_id=order_id,
                    symbol=symbol,
                    action=OrderAction.CANCEL,
                    reason=f"TTL_EXPIRED_{int(ttl)}s"
                ))
                continue
            
            # 3. Data stale => FREEZE (cancel if invalid, else keep)
            if truth_age > self.STALE_DATA_THRESHOLD:
                is_valid, invalid_reason = self.is_order_valid(
                    side, price, position_qty, bid, ask, regime
                )
                if not is_valid:
                    decisions.append(OrderDecision(
                        order_id=order_id,
                        symbol=symbol,
                        action=OrderAction.CANCEL,
                        reason=f"STALE_DATA_AND_INVALID:{invalid_reason}"
                    ))
                else:
                    # Data stale but order still valid => KEEP (frozen)
                    decisions.append(OrderDecision(
                        order_id=order_id,
                        symbol=symbol,
                        action=OrderAction.KEEP,
                        reason="STALE_DATA_BUT_VALID_FROZEN"
                    ))
                continue
            
            # 4. Regime-based validation
            is_valid, invalid_reason = self.is_order_valid(
                side, price, position_qty, bid, ask, regime
            )
            if not is_valid:
                decisions.append(OrderDecision(
                    order_id=order_id,
                    symbol=symbol,
                    action=OrderAction.CANCEL,
                    reason=invalid_reason
                ))
                continue
            
            # 5. All checks passed => KEEP
            decisions.append(OrderDecision(
                order_id=order_id,
                symbol=symbol,
                action=OrderAction.KEEP,
                reason="VALID"
            ))
        
        return decisions
    
    def compute_selective_cancels(
        self,
        decisions: List[OrderDecision]
    ) -> Tuple[List[str], List[str], Dict[str, str]]:
        """
        Extract cancel/keep lists from decisions.
        
        Returns (cancel_ids, keep_ids, reasons)
        """
        cancel_ids = []
        keep_ids = []
        reasons = {}
        
        for d in decisions:
            reasons[d.order_id] = d.reason
            if d.action == OrderAction.CANCEL:
                cancel_ids.append(d.order_id)
            else:
                keep_ids.append(d.order_id)
        
        return cancel_ids, keep_ids, reasons


# Singleton-ish config loader
_policy_instance: Optional[OrderLifecyclePolicy] = None

def get_order_lifecycle_policy(config: Dict[str, Any] = None) -> OrderLifecyclePolicy:
    """Get or create order lifecycle policy instance."""
    global _policy_instance
    if _policy_instance is None:
        _policy_instance = OrderLifecyclePolicy(config)
    return _policy_instance
