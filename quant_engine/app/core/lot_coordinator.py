"""
Lot Coordinator - Smart lot sizing and coordination across engines

Responsibilities:
1. Sequential Execution Order: LT_TRIM → KARBOTU/REDUCEMORE → ADDNEWPOS
2. Lot Deduplication: Adjust later engine quantities for earlier decisions
3. Smart Lot Sizing:
   - Min 200 lot rule
   - Sweep logic (if <400 remaining, send all)
   - Percentage rounding (e.g., 80 → 200)
   - Position closing (no reverse position)

Examples:
    # Sweep logic
    Position: 350 lots
    Requested: 200 lots
    Remaining: 150 (< 400)
    → Send ALL 350 lots
    
    # Percentage rounding
    Position: 800 lots
    Percentage: 10%
    Calculated: 80 lots
    → Round UP to 200 lots (min)
    
    # Position closing (no reverse)
    Position: 60 lots LONG
    Requested: 200 lots SELL
    → Send only 60 lots (avoid going SHORT)
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from loguru import logger


class LotSizeRule(Enum):
    """Lot sizing rule applied"""
    MIN_LOT = "MIN_LOT"              # Rounded up to min 200
    SWEEP = "SWEEP"                  # Sent all due to sweep logic
    POSITION_CLOSE = "POSITION_CLOSE"  # Sent remaining to close (no reverse)
    DEDUP_ADJUSTED = "DEDUP_ADJUSTED"  # Adjusted for prior engine
    AS_REQUESTED = "AS_REQUESTED"    # Sent as calculated


@dataclass
class EngineDecision:
    """Decision from an engine"""
    engine: str
    symbol: str
    action: str  # BUY or SELL
    qty: int
    tag: str
    reason: str
    lot_rule: Optional[str] = None
    original_qty: Optional[int] = None  # Before adjustment


@dataclass
class LotCoordinatorState:
    """State for a single symbol"""
    symbol: str
    current_qty: int  # Current position
    decisions: List[EngineDecision] = field(default_factory=list)
    
    def get_total_qty(self, action: str) -> int:
        """Get total qty for an action across all engines"""
        return sum(d.qty for d in self.decisions if d.action == action)


class LotCoordinator:
    """
    Coordinates lot sizing and deduplication across engines.
    
    Features:
    - Sequential execution tracking
    - Lot deduplication (adjust for prior engines)
    - Smart lot sizing (min, sweep, position close)
    - Enhanced tagging
    """
    
    # Constants
    MIN_LOT_SIZE = 200
    MIN_LOT_DECREASE = 125  # Lower min lot for position-decrease orders
    CLEANUP_MIN_LOT = 70   # 70-125 arası pozisyonlar tam kapatma olarak gönderilir
    SWEEP_THRESHOLD = 200  # DEPRECATED: Now using MIN_LOT_SIZE for sweep logic
    
    def __init__(self):
        self.states: Dict[str, LotCoordinatorState] = {}
        logger.info("[LotCoordinator] Initialized (MIN_LOT_INC=200, MIN_LOT_DEC=125, CLEANUP=70, SWEEP<200)")
    
    def calculate_lot_size(
        self,
        symbol: str,
        action: str,
        requested_qty: int,
        current_position: int,
        engine: str,
        tag: str,
        reason: str,
        percentage: Optional[float] = None  # e.g., 0.10 for 10%
    ) -> Tuple[int, str, str]:
        """
        Calculate final lot size with all rules applied.
        
        Args:
            symbol: Stock symbol
            action: BUY or SELL
            requested_qty: Initially requested quantity
            current_position: Current position (positive=LONG, negative=SHORT)
            engine: Engine name
            tag: Order tag
            reason: Decision reason
            percentage: If provided, percentage of position (for debug)
        
        Returns:
            (final_qty, applied_rule, adjusted_reason)
        """
        # Get or create state
        if symbol not in self.states:
            self.states[symbol] = LotCoordinatorState(
                symbol=symbol,
                current_qty=current_position
            )
        
        state = self.states[symbol]
        
        # Step 1: Adjust for prior engine decisions (DEDUPLICATION)
        prior_qty = state.get_total_qty(action)
        if prior_qty > 0:
            adjusted = max(0, requested_qty - prior_qty)
            logger.info(
                f"[LotCoordinator] {symbol} {action}: "
                f"Dedup adjustment {requested_qty} → {adjusted} "
                f"(prior engines: {prior_qty})"
            )
            requested_qty = adjusted
            dedup_adjusted = True
        else:
            dedup_adjusted = False
        
        if requested_qty == 0:
            return 0, LotSizeRule.DEDUP_ADJUSTED.value, f"{reason} (fully covered by prior engines)"
        
        # Step 2: Calculate effective position after prior decisions
        effective_position = current_position
        for dec in state.decisions:
            if dec.action == 'BUY':
                effective_position += dec.qty
            else:  # SELL
                effective_position -= dec.qty
        
        original_qty = requested_qty
        applied_rule = LotSizeRule.AS_REQUESTED
        
        # Step 3: Apply lot sizing rules
        
        # Rule 1: Position Close (prevent reverse position)
        if action == 'SELL' and effective_position > 0:
            # Closing LONG
            if requested_qty >= effective_position:
                # Would go SHORT or zero
                final_qty = effective_position
                if final_qty < requested_qty:
                    applied_rule = LotSizeRule.POSITION_CLOSE
                    reason += f" (position close: sent {final_qty} to avoid SHORT)"
                    logger.info(
                        f"[LotCoordinator] {symbol}: Position close "
                        f"{requested_qty} → {final_qty} (avoid SHORT)"
                    )
                    requested_qty = final_qty
        
        elif action == 'BUY' and effective_position < 0:
            # Covering SHORT
            if requested_qty >= abs(effective_position):
                # Would go LONG or zero
                final_qty = abs(effective_position)
                if final_qty < requested_qty:
                    applied_rule = LotSizeRule.POSITION_CLOSE
                    reason += f" (position close: sent {final_qty} to avoid LONG)"
                    logger.info(
                        f"[LotCoordinator] {symbol}: Position close "
                        f"{requested_qty} → {final_qty} (avoid reverse)"
                    )
                    requested_qty = final_qty
        
        # Rule 2: Min Lot Size (direction-aware: 125 for decrease, 200 for increase)
        # Determine if this is a decrease order (reducing/closing position)
        is_decrease = (
            (action == 'SELL' and effective_position > 0) or
            (action == 'BUY' and effective_position < 0)
        )
        effective_min_lot = self.MIN_LOT_DECREASE if is_decrease else self.MIN_LOT_SIZE
        
        if 0 < requested_qty < effective_min_lot:
            # Check if this would close the position
            is_position_close = (
                (action == 'SELL' and requested_qty >= effective_position) or
                (action == 'BUY' and requested_qty >= abs(effective_position))
            )
            
            if is_position_close:
                # Allow position close even if < MIN_LOT
                final_qty = requested_qty
                applied_rule = LotSizeRule.POSITION_CLOSE
                reason += f" (position close override: {final_qty} < MIN_LOT OK)"
            elif is_decrease and requested_qty >= self.CLEANUP_MIN_LOT:
                # CLEANUP ZONE: 70-125 arası pozisyonları cleanup olarak gönder
                # Ters pozisyona geçmemek şartıyla izin ver
                final_qty = min(requested_qty, abs(effective_position))  # Ters geçmeyi engelle
                if final_qty >= self.CLEANUP_MIN_LOT:
                    applied_rule = LotSizeRule.POSITION_CLOSE
                    reason += f" (cleanup zone: {final_qty} lots, {self.CLEANUP_MIN_LOT}≤qty<{effective_min_lot})"
                    logger.info(
                        f"[LotCoordinator] {symbol}: 🧹 Cleanup zone "
                        f"{requested_qty} → {final_qty} (position close, no flip)"
                    )
                    requested_qty = final_qty
                else:
                    # Cleanup sonrası çok az kalıyor, blokla
                    final_qty = 0
                    applied_rule = LotSizeRule.MIN_LOT
                    reason += f" (cleanup too small after no-flip cap: {final_qty})"
                    requested_qty = 0
            else:
                # Round up to effective MIN_LOT
                final_qty = effective_min_lot
                applied_rule = LotSizeRule.MIN_LOT
                reason += f" (min lot: {requested_qty} → {final_qty})"
                logger.info(
                    f"[LotCoordinator] {symbol}: Min lot applied "
                    f"{requested_qty} → {final_qty} ({'decrease' if is_decrease else 'increase'})"
                )
                requested_qty = final_qty
        
        # Rule 3: Sweep Logic (CRITICAL FIX: Use MIN_LOT_SIZE instead of hardcoded 400)
        if action == 'SELL' and effective_position > 0:
            remaining_after = effective_position - requested_qty
            # FIX: If remaining < MIN_LOT_SIZE, sweep all
            if 0 < remaining_after < self.MIN_LOT_SIZE:
                # Sweep all
                final_qty = effective_position
                applied_rule = LotSizeRule.SWEEP
                reason += f" (sweep: would leave {remaining_after} <{self.MIN_LOT_SIZE}, sent all {final_qty})"
                logger.info(
                    f"[LotCoordinator] {symbol}: Sweep logic "
                    f"{requested_qty} → {final_qty} (remaining {remaining_after} <{self.MIN_LOT_SIZE})"
                )
                requested_qty = final_qty
        
        elif action == 'BUY' and effective_position < 0:
            remaining_after = abs(effective_position) - requested_qty
            # FIX: If remaining < MIN_LOT_SIZE, sweep all
            if 0 < remaining_after < self.MIN_LOT_SIZE:
                # Sweep all
                final_qty = abs(effective_position)
                applied_rule = LotSizeRule.SWEEP
                reason += f" (sweep: would leave {remaining_after} <{self.MIN_LOT_SIZE}, sent all {final_qty})"
                logger.info(
                    f"[LotCoordinator] {symbol}: Sweep logic "
                    f"{requested_qty} → {final_qty} (remaining {remaining_after} <{self.MIN_LOT_SIZE})"
                )
                requested_qty = final_qty
        
        # Record decision
        decision = EngineDecision(
            engine=engine,
            symbol=symbol,
            action=action,
            qty=requested_qty,
            tag=tag,
            reason=reason,
            lot_rule=applied_rule.value,
            original_qty=original_qty if dedup_adjusted or applied_rule != LotSizeRule.AS_REQUESTED else None
        )
        
        state.decisions.append(decision)
        
        return requested_qty, applied_rule.value, reason
    
    def get_symbol_decisions(self, symbol: str) -> List[EngineDecision]:
        """Get all decisions for a symbol"""
        if symbol in self.states:
            return self.states[symbol].decisions
        return []
    
    def get_all_decisions(self) -> List[EngineDecision]:
        """Get all decisions across all symbols"""
        all_decisions = []
        for state in self.states.values():
            all_decisions.extend(state.decisions)
        return all_decisions
    
    def reset(self):
        """Reset state for new cycle"""
        self.states.clear()
        logger.debug("[LotCoordinator] State reset")


# Global instance
_lot_coordinator: Optional[LotCoordinator] = None


def get_lot_coordinator() -> LotCoordinator:
    """Get global lot coordinator instance"""
    global _lot_coordinator
    if _lot_coordinator is None:
        _lot_coordinator = LotCoordinator()
    return _lot_coordinator


def reset_lot_coordinator():
    """Reset lot coordinator for new cycle"""
    global _lot_coordinator
    if _lot_coordinator:
        _lot_coordinator.reset()
    else:
        _lot_coordinator = LotCoordinator()
    return _lot_coordinator
