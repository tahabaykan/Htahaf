"""
Port Adjuster Engine

Core calculation logic for portfolio exposure and group allocation.
Matches Janall Port Adjuster mathematics exactly.
"""

from typing import Dict, Optional
from datetime import datetime
from app.core.logger import logger
from app.port_adjuster.port_adjuster_models import (
    PortAdjusterConfig,
    GroupAllocation,
    PortAdjusterSnapshot
)


class PortAdjusterEngine:
    """
    Port Adjuster Engine - Pre-sizing allocation calculator.
    
    Responsibilities:
    - Calculate total_lot, long_lot, short_lot from config
    - Distribute lots across groups based on weights
    - Generate snapshot with per-group caps
    
    NOT a decision engine. Does not:
    - Make trading decisions
    - Generate signals
    - Execute orders
    """
    
    def __init__(self):
        """Initialize Port Adjuster Engine"""
        logger.info("[PORT_ADJUSTER] Engine initialized")
    
    def calculate_snapshot(self, config: PortAdjusterConfig) -> PortAdjusterSnapshot:
        """
        Calculate Port Adjuster snapshot from configuration.
        
        Args:
            config: Port Adjuster configuration
            
        Returns:
            PortAdjusterSnapshot with calculated allocations
        """
        try:
            # Step 1: Core calculations (birebir Janall)
            total_lot = config.total_exposure_usd / config.avg_pref_price
            long_lot = total_lot * (config.long_ratio_pct / 100.0)
            short_lot = total_lot * (config.short_ratio_pct / 100.0)
            
            logger.debug(
                f"[PORT_ADJUSTER] Core calculations: "
                f"total_lot={total_lot:.0f}, long_lot={long_lot:.0f}, short_lot={short_lot:.0f}"
            )
            
            # Step 2: Long group allocations
            long_allocations: Dict[str, GroupAllocation] = {}
            long_total_pct = sum(config.long_groups.values())
            
            for group, weight_pct in config.long_groups.items():
                if weight_pct > 0:
                    group_lot = long_lot * (weight_pct / 100.0)
                    group_value = group_lot * config.avg_pref_price
                    
                    long_allocations[group] = GroupAllocation(
                        group=group,
                        weight_pct=weight_pct,
                        max_lot=group_lot,
                        max_value_usd=group_value
                    )
            
            # Step 3: Short group allocations
            short_allocations: Dict[str, GroupAllocation] = {}
            short_total_pct = sum(config.short_groups.values())
            
            for group, weight_pct in config.short_groups.items():
                if weight_pct > 0:
                    group_lot = short_lot * (weight_pct / 100.0)
                    group_value = group_lot * config.avg_pref_price
                    
                    short_allocations[group] = GroupAllocation(
                        group=group,
                        weight_pct=weight_pct,
                        max_lot=group_lot,
                        max_value_usd=group_value
                    )
            
            # Step 4: Validation
            # Allow slight deviation (99-101%) for practical use
            is_valid = (
                99.0 <= long_total_pct <= 101.0 and
                99.0 <= short_total_pct <= 101.0
            )
            
            if not is_valid:
                logger.warning(
                    f"[PORT_ADJUSTER] Allocation validation failed: "
                    f"long_total_pct={long_total_pct:.1f}%, short_total_pct={short_total_pct:.1f}%"
                )
            
            # Step 5: Create snapshot
            snapshot = PortAdjusterSnapshot(
                timestamp=datetime.now(),
                total_lot=total_lot,
                long_lot=long_lot,
                short_lot=short_lot,
                long_allocations=long_allocations,
                short_allocations=short_allocations,
                config=config,
                long_total_pct=long_total_pct,
                short_total_pct=short_total_pct,
                is_valid=is_valid
            )
            
            logger.info(
                f"[PORT_ADJUSTER] Snapshot calculated: "
                f"total_lot={total_lot:.0f}, long_groups={len(long_allocations)}, "
                f"short_groups={len(short_allocations)}, valid={is_valid}"
            )
            
            return snapshot
            
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER] Error calculating snapshot: {e}", exc_info=True)
            raise
    
    def get_group_max_lot(
        self,
        snapshot: PortAdjusterSnapshot,
        group: str,
        side: str = "LONG"
    ) -> Optional[float]:
        """
        Get maximum lot allocation for a specific group.
        
        Args:
            snapshot: Port Adjuster snapshot
            group: Group name (e.g., 'heldff', 'heldkuponlu')
            side: 'LONG' or 'SHORT'
            
        Returns:
            Maximum lot for the group, or None if group not found
        """
        try:
            if side.upper() == "LONG":
                allocation = snapshot.long_allocations.get(group)
            elif side.upper() == "SHORT":
                allocation = snapshot.short_allocations.get(group)
            else:
                logger.warning(f"[PORT_ADJUSTER] Invalid side: {side}")
                return None
            
            if allocation:
                return allocation.max_lot
            else:
                logger.debug(f"[PORT_ADJUSTER] Group '{group}' not found in {side} allocations")
                return None
                
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER] Error getting group max lot: {e}", exc_info=True)
            return None
    
    def get_group_max_value_usd(
        self,
        snapshot: PortAdjusterSnapshot,
        group: str,
        side: str = "LONG"
    ) -> Optional[float]:
        """
        Get maximum value (USD) allocation for a specific group.
        
        Args:
            snapshot: Port Adjuster snapshot
            group: Group name
            side: 'LONG' or 'SHORT'
            
        Returns:
            Maximum value in USD for the group, or None if group not found
        """
        try:
            if side.upper() == "LONG":
                allocation = snapshot.long_allocations.get(group)
            elif side.upper() == "SHORT":
                allocation = snapshot.short_allocations.get(group)
            else:
                return None
            
            if allocation:
                return allocation.max_value_usd
            else:
                return None
                
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER] Error getting group max value: {e}", exc_info=True)
            return None


# Singleton instance
_port_adjuster_engine: Optional[PortAdjusterEngine] = None


def get_port_adjuster_engine() -> PortAdjusterEngine:
    """Get singleton Port Adjuster Engine instance"""
    global _port_adjuster_engine
    if _port_adjuster_engine is None:
        _port_adjuster_engine = PortAdjusterEngine()
    return _port_adjuster_engine





