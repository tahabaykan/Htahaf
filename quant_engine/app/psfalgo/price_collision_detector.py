"""
Price Collision Detector

Detects and prevents price collisions between opposite-direction orders
on the same symbol within a configurable threshold ($0.04 default).

Rules:
1. Same direction (BUY+BUY or SELL+SELL): OK, will aggregate
2. Opposite direction (BUY vs SELL): Must have ≥$0.04 spread
   - SELL price - BUY price ≥ $0.04
3. Priority: LT_TRIM > KARBOTU/REDUCEMORE > ADDNEWPOS
   - Lower priority intents are blocked if they violate spread rule
"""

from typing import Dict, List, Tuple, Optional, Any
from app.core.logger import logger
from app.psfalgo.decision_models import Intent


class PriceCollisionDetector:
    """
    Detects price collisions between opposite-direction intents.
    
    Prevents situations like:
    - LT_TRIM: X SELL $20.00
    - ADDNEWPOS: X BUY $19.97 → BLOCKED (spread $0.03 < $0.04)
    """
    
    def __init__(self, collision_threshold: float = 0.04):
        """
        Initialize detector.
        
        Args:
            collision_threshold: Minimum spread required for opposite orders ($)
        """
        self.collision_threshold = collision_threshold
        logger.info(
            f"[PRICE_COLLISION] Initialized with threshold ${collision_threshold}"
        )
    
    def check_collision(
        self,
        intent: Intent,
        existing_intents: List[Intent],
        l1_data: Dict[str, Any],
        priority_order: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """
        Check if intent collides with existing intents.
        
        Args:
            intent: New intent to check
            existing_intents: List of already-registered intents
            l1_data: L1 market data (bid/ask/last)
            priority_order: Optional priority order (default: LT_TRIM > KARBOTU/REDUCEMORE > ADDNEWPOS)
            
        Returns:
            (is_allowed, reason) tuple
        """
        if priority_order is None:
            priority_order = ["LT_TRIM", "KARBOTU", "REDUCEMORE", "ADDNEWPOS"]
        
        # Filter existing intents for same symbol
        symbol_intents = [
            ei for ei in existing_intents 
            if ei.symbol == intent.symbol
        ]
        
        if not symbol_intents:
            return True, "OK - No existing intents for symbol"
        
        # Check each existing intent
        for existing in symbol_intents:
            # Same direction → OK (will aggregate)
            if existing.action == intent.action:
                continue
            
            # Opposite direction → check spread
            collision_detected, reason = self._check_spread(
                intent,
                existing,
                l1_data,
                priority_order
            )
            
            if collision_detected:
                return False, reason
        
        return True, "OK - No collisions detected"
    
    def _check_spread(
        self,
        intent: Intent,
        existing: Intent,
        l1_data: Dict[str, Any],
        priority_order: List[str]
    ) -> Tuple[bool, str]:
        """
        Check spread between opposite-direction intents.
        
        Returns:
            (collision_detected, reason) tuple
        """
        # Get prices
        intent_price = self._get_intent_price(intent, l1_data)
        existing_price = self._get_intent_price(existing, l1_data)
        
        if intent_price is None or existing_price is None:
            logger.warning(
                f"[PRICE_COLLISION] Could not determine prices for {intent.symbol} "
                f"(intent={intent_price}, existing={existing_price})"
            )
            return False, "OK - Price unavailable, allowing"
        
        # Calculate spread based on direction
        if existing.action == "SELL" and intent.action == "BUY":
            # Existing is SELL, new is BUY
            # Spread = SELL price - BUY price
            spread = existing_price - intent_price
            
            if spread < self.collision_threshold:
                # Check priority
                existing_priority = self._get_priority(existing.intent_category, priority_order)
                intent_priority = self._get_priority(intent.intent_category, priority_order)
                
                if intent_priority > existing_priority:
                    # New intent has lower priority, block it
                    return True, (
                        f"COLLISION BLOCKED: BUY ${intent_price:.2f} too close to existing "
                        f"SELL ${existing_price:.2f} (spread ${spread:.2f} < ${self.collision_threshold}). "
                        f"Existing {existing.intent_category} has higher priority."
                    )
        
        elif existing.action == "BUY" and intent.action == "SELL":
            # Existing is BUY, new is SELL
            # Spread = SELL price - BUY price
            spread = intent_price - existing_price
            
            if spread < self.collision_threshold:
                existing_priority = self._get_priority(existing.intent_category, priority_order)
                intent_priority = self._get_priority(intent.intent_category, priority_order)
                
                if intent_priority > existing_priority:
                    return True, (
                        f"COLLISION BLOCKED: SELL ${intent_price:.2f} too close to existing "
                        f"BUY ${existing_price:.2f} (spread ${spread:.2f} < ${self.collision_threshold}). "
                        f"Existing {existing.intent_category} has higher priority."
                    )
        
        return False, "OK"
    
    def _get_intent_price(
        self,
        intent: Intent,
        l1_data: Dict[str, Any]
    ) -> Optional[float]:
        """
        Get price for an intent.
        
        Uses intent.target_price if available, otherwise bid/ask from L1 data.
        """
        # Check if intent has target_price
        if hasattr(intent, 'target_price') and intent.target_price:
            return float(intent.target_price)
        
        # Fallback to L1 data
        l1 = l1_data.get(intent.symbol, {})
        
        if intent.action == "BUY":
            # BUY uses ASK price
            price = l1.get('ask')
        else:
            # SELL uses BID price
            price = l1.get('bid')
        
        if price is None or price <= 0:
            # Last fallback: use 'last' price
            price = l1.get('last')
        
        return float(price) if price and price > 0 else None
    
    def _get_priority(
        self,
        engine: str,
        priority_order: List[str]
    ) -> int:
        """
        Get priority index for an engine.
        
        Lower index = higher priority.
        
        Args:
            engine: Engine name
            priority_order: List of engines in priority order
            
        Returns:
            Priority index (0 = highest priority)
        """
        try:
            return priority_order.index(engine)
        except ValueError:
            # Unknown engine, lowest priority
            return len(priority_order)
    
    def filter_collisions(
        self,
        intents: List[Intent],
        existing_intents: List[Intent],
        l1_data: Dict[str, Any],
        priority_order: Optional[List[str]] = None
    ) -> Tuple[List[Intent], List[Tuple[Intent, str]]]:
        """
        Filter out intents that collide with existing intents.
        
        Args:
            intents: List of new intents to check
            existing_intents: List of already-registered intents
            l1_data: L1 market data
            priority_order: Optional priority order
            
        Returns:
            (allowed_intents, blocked_intents) tuple
            blocked_intents is list of (intent, reason) tuples
        """
        allowed = []
        blocked = []
        
        for intent in intents:
            is_allowed, reason = self.check_collision(
                intent,
                existing_intents,
                l1_data,
                priority_order
            )
            
            if is_allowed:
                allowed.append(intent)
            else:
                blocked.append((intent, reason))
                logger.warning(
                    f"[PRICE_COLLISION] Blocked {intent.intent_category} intent: "
                    f"{intent.symbol} {intent.action} {intent.qty} - {reason}"
                )
        
        if blocked:
            logger.info(
                f"[PRICE_COLLISION] Filtered {len(intents)} intents: "
                f"{len(allowed)} allowed, {len(blocked)} blocked"
            )
        
        return allowed, blocked
    
    def set_collision_threshold(self, threshold: float):
        """
        Update collision threshold.
        
        Args:
            threshold: New threshold in dollars
        """
        old_threshold = self.collision_threshold
        self.collision_threshold = threshold
        logger.info(
            f"[PRICE_COLLISION] Threshold updated: ${old_threshold} → ${threshold}"
        )


# Global instance
_price_collision_detector: Optional[PriceCollisionDetector] = None


def get_price_collision_detector() -> PriceCollisionDetector:
    """Get or create global PriceCollisionDetector instance"""
    global _price_collision_detector
    if _price_collision_detector is None:
        _price_collision_detector = PriceCollisionDetector()
    return _price_collision_detector


def initialize_price_collision_detector(collision_threshold: float = 0.04):
    """Initialize global PriceCollisionDetector instance"""
    global _price_collision_detector
    _price_collision_detector = PriceCollisionDetector(collision_threshold=collision_threshold)
    logger.info("[PRICE_COLLISION] Detector initialized")
