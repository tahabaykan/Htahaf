"""
Greatest MM Quant Engine
========================

Market Making quantitative scoring engine with 4-scenario analysis.

Formulas:
- Final MM Long = 200×b + 4×(b/a) - 50×Ucuzluk
- Final MM Short = 200×a + 4×(a/b) + 50×Pahalılık

Where:
- b(Long) = Son5Tick - Entry_Long
- a(Long) = Ask - Son5Tick  
- a(Short) = Entry_Short - Son5Tick
- b(Short) = Son5Tick - Bid
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from collections import deque
import threading

from app.core.logger import logger
from app.mm.greatest_mm_models import (
    MMScenarioType, MMScenario, MMAnalysis, MMWatchlistItem, GreatestMMResponse
)


# Threshold for valid entry
MM_THRESHOLD = 30.0


class GreatestMMEngine:
    """
    Greatest MM Quant Engine
    
    Computes 4-scenario MM Long/Short scores for optimal entry points.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        
        # Watchlist: symbols being tracked
        self.watchlist: Dict[str, MMWatchlistItem] = {}
        
        # Recent prints per symbol: {symbol: deque of recent prints}
        self.recent_prints: Dict[str, deque] = {}
        
        logger.info("[GREATEST_MM] Engine initialized")
    
    def compute_mm_scenario(
        self,
        scenario_type: MMScenarioType,
        bid: float,
        ask: float,
        spread: float,
        prev_close: float,
        benchmark_chg: float,
        entry_long: float,
        entry_short: float,
        son5_tick: float
    ) -> MMScenario:
        """
        Compute MM scores for a single scenario.
        
        Args:
            scenario_type: Type of scenario
            bid, ask, spread: Market data
            prev_close, benchmark_chg: For ucuzluk/pahalilik
            entry_long, entry_short: Entry points
            son5_tick: Reference Son5Tick price
            
        Returns:
            MMScenario with computed scores
        """
        # Calculate distances
        # For Long: b = Son5Tick - Entry_Long, a = Ask - Son5Tick
        b_long_raw = son5_tick - entry_long
        a_long_raw = ask - son5_tick
        
        # For Short: a = Entry_Short - Son5Tick, b = Son5Tick - Bid
        a_short_raw = entry_short - son5_tick
        b_short_raw = son5_tick - bid
        
        # Check for edge cases - if raw distance is <= 0, scenario is invalid for that direction
        long_edge_case = b_long_raw <= 0 or a_long_raw <= 0
        short_edge_case = a_short_raw <= 0 or b_short_raw <= 0
        
        # Apply minimum 0.01 for zero/negative values (for calculation only)
        b_long = max(0.01, b_long_raw) if b_long_raw <= 0 else b_long_raw
        a_long = max(0.01, a_long_raw) if a_long_raw <= 0 else a_long_raw
        a_short = max(0.01, a_short_raw) if a_short_raw <= 0 else a_short_raw
        b_short = max(0.01, b_short_raw) if b_short_raw <= 0 else b_short_raw
        
        # Calculate ucuzluk/pahalilik
        ucuzluk = (entry_long - prev_close) - benchmark_chg
        pahalilik = (entry_short - prev_close) - benchmark_chg
        
        # Calculate MM scores
        # MM Long = 200×b + 4×(b/a) - 50×Ucuzluk
        mm_long = 200 * b_long + 4 * (b_long / a_long) - 50 * ucuzluk
        
        # MM Short = 200×a + 4×(a/b) + 50×Pahalılık
        mm_short = 200 * a_short + 4 * (a_short / b_short) + 50 * pahalilik
        
        # Cap scores at reasonable limits (prevents edge case inflation)
        # REMOVED CAP: User wants to see real scores to debug "500" nonsense.
        # mm_long = min(mm_long, 500.0)
        # mm_short = min(mm_short, 500.0)
        
        # Mark as invalid if edge case (distance was 0 or negative)
        long_valid = mm_long >= MM_THRESHOLD and not long_edge_case
        short_valid = mm_short >= MM_THRESHOLD and not short_edge_case
        
        return MMScenario(
            scenario_type=scenario_type,
            entry_long=round(entry_long, 4),
            entry_short=round(entry_short, 4),
            son5_tick=round(son5_tick, 4),
            b_long=round(b_long, 4),
            a_long=round(a_long, 4),
            a_short=round(a_short, 4),
            b_short=round(b_short, 4),
            ucuzluk=round(ucuzluk, 4),
            pahalilik=round(pahalilik, 4),
            mm_long=round(mm_long, 2),
            mm_short=round(mm_short, 2),
            long_valid=long_valid,
            short_valid=short_valid
        )
    
    def analyze_symbol(
        self,
        symbol: str,
        bid: float,
        ask: float,
        prev_close: float,
        benchmark_chg: float,
        son5_tick: float,
        new_print: Optional[float] = None
    ) -> MMAnalysis:
        """
        Analyze a symbol with 4-scenario MM scoring.
        
        If no new_print, only Scenario 1 is computed.
        Otherwise, all 4 scenarios are computed.
        
        Args:
            symbol: Stock symbol
            bid, ask: Current bid/ask
            prev_close: Previous close
            benchmark_chg: Benchmark change (from pricing overlay)
            son5_tick: Current Son5Tick value
            new_print: Optional new print (100-200 lot)
            
        Returns:
            MMAnalysis with all scenarios
        """
        try:
            spread = ask - bid
            
            analysis = MMAnalysis(
                symbol=symbol,
                bid=bid,
                ask=ask,
                spread=round(spread, 4),
                prev_close=prev_close,
                benchmark_chg=benchmark_chg,
                son5_tick=son5_tick,
                new_print=new_print,
                has_new_print=new_print is not None
            )
            
            scenarios = []
            
            # Scenario 1: ORIGINAL
            # Entry = Bid + spread×0.15 (long), Ask - spread×0.15 (short)
            entry_long_1 = bid + spread * 0.15
            entry_short_1 = ask - spread * 0.15
            scenario_1 = self.compute_mm_scenario(
                MMScenarioType.ORIGINAL,
                bid, ask, spread, prev_close, benchmark_chg,
                entry_long_1, entry_short_1, son5_tick
            )
            scenarios.append(scenario_1)
            
            if new_print is not None:
                # Skip edge cases:
                # For Long: if new_print >= ask, a_long would be 0 (meaningless)
                # For Short: if new_print <= bid, b_short would be 0 (meaningless)
                # Also skip if new_print is essentially same as son5_tick (no new info)
                new_print_valid = (
                    new_print < ask and   # Must be below ask for meaningful a_long
                    new_print > bid and   # Must be above bid for meaningful b_short
                    abs(new_print - son5_tick) > 0.005  # Must be different from son5_tick
                )
                
                if new_print_valid:
                    # Scenario 2: NEW_SON5
                    # Same entry, Son5Tick = new_print
                    scenario_2 = self.compute_mm_scenario(
                        MMScenarioType.NEW_SON5,
                        bid, ask, spread, prev_close, benchmark_chg,
                        entry_long_1, entry_short_1, new_print
                    )
                    scenarios.append(scenario_2)
                    
                    # Scenario 3: NEW_ENTRY
                    # Entry = new_print ± 0.01, Son5Tick = old
                    entry_long_3 = new_print + 0.01
                    entry_short_3 = new_print - 0.01
                    scenario_3 = self.compute_mm_scenario(
                        MMScenarioType.NEW_ENTRY,
                        bid, ask, spread, prev_close, benchmark_chg,
                        entry_long_3, entry_short_3, son5_tick
                    )
                    scenarios.append(scenario_3)
                    
                    # Scenario 4: BOTH_NEW
                    # Entry = old_son5 ± 0.01, Son5Tick = new_print
                    entry_long_4 = son5_tick + 0.01
                    entry_short_4 = son5_tick - 0.01
                    scenario_4 = self.compute_mm_scenario(
                        MMScenarioType.BOTH_NEW,
                        bid, ask, spread, prev_close, benchmark_chg,
                        entry_long_4, entry_short_4, new_print
                    )
                    scenarios.append(scenario_4)
            
            analysis.scenarios = scenarios
            
            # Find best entries (closest to 30 but >= 30)
            valid_long_scenarios = [(s, s.mm_long) for s in scenarios if s.long_valid]
            valid_short_scenarios = [(s, s.mm_short) for s in scenarios if s.short_valid]
            
            if valid_long_scenarios:
                # Sort by score (closest to 30)
                best_long = min(valid_long_scenarios, key=lambda x: x[1])
                analysis.best_long_entry = best_long[0].entry_long
                analysis.best_long_scenario = best_long[0].scenario_type
                analysis.best_long_score = best_long[1]
                analysis.long_actionable = True
            
            if valid_short_scenarios:
                best_short = min(valid_short_scenarios, key=lambda x: x[1])
                analysis.best_short_entry = best_short[0].entry_short
                analysis.best_short_scenario = best_short[0].scenario_type
                analysis.best_short_score = best_short[1]
                analysis.short_actionable = True
            
            return analysis
            
        except Exception as e:
            logger.error(f"[GREATEST_MM] Error analyzing {symbol}: {e}", exc_info=True)
            return MMAnalysis(symbol=symbol, error=str(e))
    
    def add_to_watchlist(self, symbol: str, son5_tick: float) -> bool:
        """Add symbol to watchlist"""
        with self._lock:
            if symbol not in self.watchlist:
                self.watchlist[symbol] = MMWatchlistItem(
                    symbol=symbol,
                    son5_tick=son5_tick
                )
                logger.info(f"[GREATEST_MM] Added {symbol} to watchlist")
                return True
            return False
    
    def remove_from_watchlist(self, symbol: str) -> bool:
        """Remove symbol from watchlist"""
        with self._lock:
            if symbol in self.watchlist:
                del self.watchlist[symbol]
                logger.info(f"[GREATEST_MM] Removed {symbol} from watchlist")
                return True
            return False
    
    def update_new_print(self, symbol: str, price: float, size: int):
        """
        Update new print for a symbol.
        
        If prints accumulate near new_print area, update son5_tick.
        """
        with self._lock:
            if symbol not in self.recent_prints:
                self.recent_prints[symbol] = deque(maxlen=10)
            
            self.recent_prints[symbol].append({
                'price': price,
                'size': size,
                'ts': datetime.now().timestamp()
            })
            
            # If symbol in watchlist, update new_print
            if symbol in self.watchlist:
                item = self.watchlist[symbol]
                item.new_print = price
                item.last_updated = datetime.now()
                
                # Check if prints are clustering near new area
                # (if 3+ prints within 0.03 of new_print, update son5_tick)
                recent = list(self.recent_prints[symbol])
                if len(recent) >= 3:
                    cluster_prices = [p['price'] for p in recent[-3:]]
                    avg_price = sum(cluster_prices) / len(cluster_prices)
                    max_diff = max(abs(p - avg_price) for p in cluster_prices)
                    
                    if max_diff <= 0.03:
                        # Prints are clustering, update son5_tick
                        item.son5_tick = avg_price
                        logger.debug(f"[GREATEST_MM] {symbol} Son5Tick updated to {avg_price:.2f}")
    
    def get_watchlist(self) -> List[MMWatchlistItem]:
        """Get current watchlist"""
        with self._lock:
            return list(self.watchlist.values())


# Global instance
_greatest_mm_engine: Optional[GreatestMMEngine] = None


def get_greatest_mm_engine() -> GreatestMMEngine:
    """Get global GreatestMMEngine instance"""
    global _greatest_mm_engine
    if _greatest_mm_engine is None:
        _greatest_mm_engine = GreatestMMEngine()
    return _greatest_mm_engine


def initialize_greatest_mm_engine() -> GreatestMMEngine:
    """Initialize global GreatestMMEngine instance"""
    global _greatest_mm_engine
    _greatest_mm_engine = GreatestMMEngine()
    return _greatest_mm_engine
