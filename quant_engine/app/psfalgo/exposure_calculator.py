"""
Exposure Calculator - Production-Grade

Calculates ExposureSnapshot from position snapshots.
Used by RUNALL to determine exposure mode (OFANSIF/DEFANSIF).
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from app.core.logger import logger
from app.psfalgo.decision_models import ExposureSnapshot, PositionSnapshot


class ExposureCalculator:
    """
    Exposure Calculator - calculates exposure from position snapshots.
    
    Responsibilities:
    - Calculate pot_total (total exposure)
    - Calculate long_lots / short_lots
    - Calculate net_exposure
    - Determine exposure_mode (OFANSIF/DEFANSIF)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Exposure Calculator.
        
        Args:
            config: Configuration dict with:
                - pot_max_lot: Maximum exposure limit (default: 63636)
                - avg_price: Average price for lot calculation (default: 100)
        """
        self.config = config or {}
        self.pot_max_lot = self.config.get('pot_max_lot', 63636)
        self.avg_price = self.config.get('avg_price', 100.0)  # Default $100 for lot calculation
    
    def calculate_exposure(
        self,
        positions: List[PositionSnapshot],
        pot_max: Optional[float] = None
    ) -> ExposureSnapshot:
        """
        Calculate exposure snapshot from position snapshots.
        
        Args:
            positions: List of PositionSnapshot objects
            pot_max: Override pot_max from config (optional)
            
        Returns:
            ExposureSnapshot object
        """
        if pot_max is None:
            pot_max = self.pot_max_lot
        
        pot_total = 0.0
        long_lots = 0.0
        short_lots = 0.0
        
        for pos in positions:
            # DEBUG LOG requested by user to diagnose why positions are discarded
            accepted_flag = "OK"
            if pos.current_price is None or pos.current_price <= 0:
                accepted_flag = "REJECTED_NO_PRICE"
            elif pos.qty == 0:
                accepted_flag = "REJECTED_ZERO_QTY"
                
            logger.info(
                f"[EXPOSURE_DEBUG] sym={pos.symbol} "
                f"qty={pos.qty} price={pos.current_price} "
                f"value={abs(pos.qty) * (pos.current_price or 0)} "
                f"accepted={accepted_flag}"
            )

            # Calculate position value (absolute)
            position_value = abs(pos.qty) * (pos.current_price or 0.0)
            pot_total += position_value
            
            # Accumulate lots
            if pos.qty > 0:
                long_lots += pos.qty
            elif pos.qty < 0:
                short_lots += abs(pos.qty)
        
        # Calculate net exposure
        net_exposure = long_lots - short_lots
        
        # Determine mode using Janall logic (lot-based thresholds)
        # Will be recalculated properly in determine_exposure_mode()
        # For now, use simple fallback
        mode = 'OFANSIF' if pot_total < pot_max else 'DEFANSIF'
        
        exposure = ExposureSnapshot(
            pot_total=pot_total,
            pot_max=pot_max,
            long_lots=long_lots,
            short_lots=short_lots,
            net_exposure=net_exposure,
            mode=mode,  # Will be recalculated by determine_exposure_mode()
            timestamp=datetime.now()
        )
        
        # Recalculate mode using proper Janall logic
        exposure.mode = self.determine_exposure_mode(exposure)
        
        logger.debug(
            f"Exposure calculated: "
            f"Pot Total={pot_total:,.0f}, "
            f"Pot Max={pot_max:,.0f}, "
            f"Long={long_lots:,.0f}, "
            f"Short={short_lots:,.0f}, "
            f"Net={net_exposure:,.0f}, "
            f"Mode={exposure.mode}"
        )
        
        return exposure
    
    def determine_exposure_mode(self, exposure: ExposureSnapshot, config: Optional[Dict[str, Any]] = None) -> str:
        """
        Determine exposure mode from exposure snapshot (Janall-compatible).
        
        Janall Logic:
        - defensive_threshold = max_lot * 0.955 (%95.5)
        - offensive_threshold = max_lot * 0.927 (%92.7)
        - total_lots > defensive_threshold → DEFANSIF (only REDUCEMORE)
        - total_lots < offensive_threshold → OFANSIF (KARBOTU + ADDNEWPOS)
        - between → GECIS (REDUCEMORE)
        
        Args:
            exposure: ExposureSnapshot object
            config: Optional config with thresholds (defaults from rules)
            
        Returns:
            'OFANSIF', 'DEFANSIF', or 'GECIS'
        """
        if config is None:
            # Load defaults from rules
            from app.psfalgo.rules_store import get_rules_store
            rules_store = get_rules_store()
            if rules_store:
                exposure_rules = rules_store.get_rules().get('exposure', {})
                defensive_threshold_percent = exposure_rules.get('defensive_threshold_percent', 95.5)
                offensive_threshold_percent = exposure_rules.get('offensive_threshold_percent', 92.7)
            else:
                defensive_threshold_percent = 95.5
                offensive_threshold_percent = 92.7
        else:
            defensive_threshold_percent = config.get('defensive_threshold_percent', 95.5)
            offensive_threshold_percent = config.get('offensive_threshold_percent', 92.7)
        
        # Calculate max_lot from pot_max
        # Janall uses lot-based thresholds, not dollar-based
        # We'll use total_lots (long_lots + short_lots) as total_lots
        total_lots = exposure.long_lots + exposure.short_lots
        
        # Calculate thresholds (as percentages of pot_max in lots)
        # pot_max is in dollars, convert to lots using avg_price
        avg_price = self.avg_price
        max_lot = exposure.pot_max / avg_price if avg_price > 0 else 63636
        
        defensive_threshold = max_lot * (defensive_threshold_percent / 100.0)
        offensive_threshold = max_lot * (offensive_threshold_percent / 100.0)
        
        # Janall logic
        if total_lots > defensive_threshold:
            return 'DEFANSIF'  # Only REDUCEMORE
        elif total_lots < offensive_threshold:
            return 'OFANSIF'  # KARBOTU + ADDNEWPOS
        else:
            return 'GECIS'  # Transition mode - REDUCEMORE


# Global instance
_exposure_calculator: Optional[ExposureCalculator] = None


def get_exposure_calculator() -> Optional[ExposureCalculator]:
    """Get global ExposureCalculator instance"""
    return _exposure_calculator


def initialize_exposure_calculator(config: Optional[Dict[str, Any]] = None):
    """Initialize global ExposureCalculator instance"""
    global _exposure_calculator
    _exposure_calculator = ExposureCalculator(config=config)
    logger.info("ExposureCalculator initialized")


