"""
Intent Tracker - Cumulative Intent Management

Tracks intents from multiple engines (LT_TRIM, KARBOTU, REDUCEMORE, ADDNEWPOS)
and provides cumulative quantity tracking for same symbol+action pairs.

Used in sequential RUNALL execution to enable cumulative intent aggregation.
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.decision_models import Intent


@dataclass
class IntentSummary:
    """Summary of intents for a (symbol, action) pair"""
    symbol: str
    action: str  # BUY or SELL
    total_qty: float
    intents: List[Intent] = field(default_factory=list)
    engines: List[str] = field(default_factory=list)


class IntentTracker:
    """
    Tracks intents across multiple engines in sequential RUNALL execution.
    
    Enables cumulative intent tracking:
    - LT_TRIM: X SELL 450
    - KARBOTU: X SELL 550 (additional)
    - Total: X SELL 1000
    """
    
    def __init__(self):
        self.intents_by_engine: Dict[str, List[Intent]] = {}
        self.intent_map: Dict[Tuple[str, str], List[Intent]] = {}
        self.execution_order: List[str] = []
        self.timestamp = datetime.now()
    
    def register_intents(self, engine: str, intents: List[Intent]):
        """
        Register intents from an engine.
        
        Args:
            engine: Engine name (LT_TRIM, KARBOTU, REDUCEMORE, ADDNEWPOS)
            intents: List of Intent objects
        """
        self.intents_by_engine[engine] = intents
        self.execution_order.append(engine)
        
        for intent in intents:
            key = (intent.symbol, intent.action)
            if key not in self.intent_map:
                self.intent_map[key] = []
            self.intent_map[key].append(intent)
        
        logger.info(
            f"[INTENT_TRACKER] Registered {len(intents)} intents from {engine}. "
            f"Total tracked: {len(self.get_all_intents())}"
        )
    
    def get_cumulative_qty(self, symbol: str, action: str) -> float:
        """
        Get cumulative quantity for a (symbol, action) pair.
        
        Args:
            symbol: Stock symbol
            action: BUY or SELL
            
        Returns:
            Total quantity from all engines for this (symbol, action)
        """
        key = (symbol, action)
        if key not in self.intent_map:
            return 0.0
        
        total = sum(intent.qty for intent in self.intent_map[key])
        return total
    
    def get_intents_for_symbol_action(
        self, 
        symbol: str, 
        action: str
    ) -> List[Intent]:
        """
        Get all intents for a (symbol, action) pair.
        
        Returns list of intents in execution order.
        """
        key = (symbol, action)
        return self.intent_map.get(key, [])
    
    def get_intents_by_engine(self, engine: str) -> List[Intent]:
        """Get all intents from a specific engine"""
        return self.intents_by_engine.get(engine, [])
    
    def get_all_intents(self) -> List[Intent]:
        """Get all intents from all engines in execution order"""
        all_intents = []
        for engine in self.execution_order:
            all_intents.extend(self.intents_by_engine.get(engine, []))
        return all_intents
    
    def get_intent_summary(self, symbol: str, action: str) -> Optional[IntentSummary]:
        """
        Get summary of intents for a (symbol, action) pair.
        
        Returns:
            IntentSummary with aggregated info, or None if no intents
        """
        key = (symbol, action)
        if key not in self.intent_map:
            return None
        
        intents = self.intent_map[key]
        engines = [intent.intent_category for intent in intents]
        total_qty = sum(intent.qty for intent in intents)
        
        return IntentSummary(
            symbol=symbol,
            action=action,
            total_qty=total_qty,
            intents=intents,
            engines=engines
        )
    
    def get_all_symbols(self) -> List[str]:
        """Get list of all unique symbols with intents"""
        return list(set(key[0] for key in self.intent_map.keys()))
    
    def get_intent_count_by_engine(self) -> Dict[str, int]:
        """Get intent count breakdown by engine"""
        return {
            engine: len(intents) 
            for engine, intents in self.intents_by_engine.items()
        }
    
    def has_intent_for_symbol(self, symbol: str) -> bool:
        """Check if any intent exists for a symbol"""
        return any(key[0] == symbol for key in self.intent_map.keys())
    
    def has_opposite_direction_intent(
        self, 
        symbol: str, 
        action: str
    ) -> bool:
        """
        Check if there's an intent in the opposite direction for this symbol.
        
        Used for price collision detection.
        
        Args:
            symbol: Stock symbol
            action: BUY or SELL
            
        Returns:
            True if opposite direction intent exists
        """
        opposite_action = "SELL" if action == "BUY" else "BUY"
        key = (symbol, opposite_action)
        return key in self.intent_map and len(self.intent_map[key]) > 0
    
    def get_price_range_for_symbol(
        self, 
        symbol: str, 
        l1_data: Dict[str, Any]
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Get min/max price range for all intents on a symbol.
        
        Used for price collision detection.
        
        Args:
            symbol: Stock symbol
            l1_data: L1 market data (bid/ask)
            
        Returns:
            (min_price, max_price) tuple, or (None, None) if no intents
        """
        symbol_intents = [
            intent for intent in self.get_all_intents() 
            if intent.symbol == symbol
        ]
        
        if not symbol_intents:
            return None, None
        
        prices = []
        for intent in symbol_intents:
            # Get price from intent or L1 data
            if hasattr(intent, 'target_price') and intent.target_price:
                prices.append(intent.target_price)
            else:
                # Use bid/ask from L1
                l1 = l1_data.get(symbol, {})
                if intent.action == "BUY":
                    price = l1.get('ask', 0.0)
                else:
                    price = l1.get('bid', 0.0)
                if price > 0:
                    prices.append(price)
        
        if not prices:
            return None, None
        
        return min(prices), max(prices)
    
    def log_summary(self):
        """Log comprehensive summary of all tracked intents"""
        logger.info("=" * 80)
        logger.info("[INTENT_TRACKER] SUMMARY")
        logger.info(f"  Execution Order: {' → '.join(self.execution_order)}")
        logger.info(f"  Total Intents: {len(self.get_all_intents())}")
        
        intent_counts = self.get_intent_count_by_engine()
        for engine, count in intent_counts.items():
            logger.info(f"    {engine}: {count}")
        
        logger.info(f"  Unique Symbols: {len(self.get_all_symbols())}")
        
        # Log cumulative summary per symbol
        logger.info("  Cumulative Summary:")
        for symbol in sorted(self.get_all_symbols()):
            for action in ["BUY", "SELL"]:
                summary = self.get_intent_summary(symbol, action)
                if summary and summary.total_qty > 0:
                    engines_str = " + ".join([
                        f"{intent.intent_category}({intent.qty})" 
                        for intent in summary.intents
                    ])
                    logger.info(
                        f"    {symbol} {action}: {summary.total_qty:.0f} "
                        f"({engines_str})"
                    )
        logger.info("=" * 80)
    
    def clear(self):
        """Clear all tracked intents (for new cycle)"""
        self.intents_by_engine.clear()
        self.intent_map.clear()
        self.execution_order.clear()
        self.timestamp = datetime.now()


# Global instance
_intent_tracker: Optional[IntentTracker] = None


def get_intent_tracker() -> IntentTracker:
    """Get or create global IntentTracker instance"""
    global _intent_tracker
    if _intent_tracker is None:
        _intent_tracker = IntentTracker()
    return _intent_tracker


def reset_intent_tracker():
    """Reset global IntentTracker for new cycle"""
    global _intent_tracker
    if _intent_tracker:
        _intent_tracker.clear()
    else:
        _intent_tracker = IntentTracker()
