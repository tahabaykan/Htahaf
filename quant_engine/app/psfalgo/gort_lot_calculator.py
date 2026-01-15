"""
GORT Lot Calculator - Janall-Compatible

Special lot calculation for GORT filter step.

Janall Logic:
- GORT filter uses a special lot calculation method
- The lot is calculated based on GORT value and position size
- Different from standard percentage-based calculation

Methods:
1. PROPORTIONAL: Base lot * GORT multiplier
2. TIERED: Different percentages for different GORT ranges
3. FIXED: Fixed lot amount
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from app.core.logger import logger


@dataclass
class GortLotConfig:
    """GORT Lot Calculator configuration"""
    enabled: bool = True
    method: str = "PROPORTIONAL"  # PROPORTIONAL, TIERED, FIXED
    
    # Proportional method
    base_lot: int = 100
    gort_multiplier: float = 0.5
    max_lot: int = 500
    
    # Fixed method
    fixed_lot: int = 200
    
    # Tiered method (list of {gort_range: [min, max], lot_percentage: float})
    tiers: list = None
    
    def __post_init__(self):
        if self.tiers is None:
            self.tiers = [
                {'gort_range': [-1.0, 0.0], 'lot_percentage': 25.0},
                {'gort_range': [0.0, 1.0], 'lot_percentage': 50.0},
                {'gort_range': [1.0, 2.0], 'lot_percentage': 75.0}
            ]


class GortLotCalculator:
    """
    GORT Lot Calculator - special lot calculation for GORT filter.
    
    Janall uses a special calculation for GORT-filtered positions.
    This calculator implements the same logic.
    
    Methods:
    1. PROPORTIONAL: lot = base_lot * (1 + gort * multiplier)
    2. TIERED: Different lot percentages for different GORT ranges
    3. FIXED: Fixed lot amount
    """
    
    def __init__(self, config: Optional[GortLotConfig] = None, config_path: Optional[Path] = None):
        """
        Initialize GORT Lot Calculator.
        
        Args:
            config: GortLotConfig object
            config_path: Path to psfalgo_rules.yaml (to load config)
        """
        if config:
            self.config = config
        elif config_path:
            self.config = self._load_config(config_path)
        else:
            self.config = GortLotConfig()
        
        logger.info(f"GortLotCalculator initialized: method={self.config.method}")
    
    def _load_config(self, config_path: Path) -> GortLotConfig:
        """Load config from psfalgo_rules.yaml"""
        try:
            if not config_path.exists():
                return GortLotConfig()
            
            with open(config_path, 'r', encoding='utf-8') as f:
                rules = yaml.safe_load(f)
            
            gort_config = rules.get('gort_lot_calculation', {})
            
            return GortLotConfig(
                enabled=gort_config.get('enabled', True),
                method=gort_config.get('method', 'PROPORTIONAL'),
                base_lot=gort_config.get('proportional', {}).get('base_lot', 100),
                gort_multiplier=gort_config.get('proportional', {}).get('gort_multiplier', 0.5),
                max_lot=gort_config.get('proportional', {}).get('max_lot', 500),
                fixed_lot=gort_config.get('fixed', {}).get('lot', 200),
                tiers=gort_config.get('tiered', [])
            )
        except Exception as e:
            logger.error(f"Error loading GORT lot config: {e}")
            return GortLotConfig()
    
    def calculate_lot(
        self,
        position_qty: float,
        gort_value: float,
        is_shorts: bool = False,
        confidence: float = 1.0
    ) -> Tuple[int, str]:
        """
        Calculate lot for GORT filter.
        
        Venue Policy Adjustment:
        - Düşük confidence (< 0.5) durumunda trade iptal edilmez.
        - Sadece min lot (200) ile işlem yapılır.
        
        Args:
            position_qty: Current position quantity
            gort_value: GORT value
            is_shorts: True if processing shorts
            confidence: Decision confidence (0.0-1.0)
            
        Returns:
            (calculated_lot, reason)
        """
        # Venue Policy: Low confidence -> Min lot (200)
        if confidence < 0.5:
            min_lot = 200
            # Clamp to position size
            lot = min(min_lot, abs(position_qty))
            lot = self._round_lot(lot)
            return lot, f"LOW_CONFIDENCE: Force min lot (200), confidence={confidence:.2f}"

        if not self.config.enabled:
            # Fall back to standard 50% calculation
            return self._standard_lot_calculation(position_qty, 50.0), "GORT calculation disabled"
        
        method = self.config.method.upper()
        
        if method == "PROPORTIONAL":
            return self._proportional_calculation(position_qty, gort_value, is_shorts)
        elif method == "TIERED":
            return self._tiered_calculation(position_qty, gort_value, is_shorts)
        elif method == "FIXED":
            return self._fixed_calculation(position_qty)
        else:
            logger.warning(f"Unknown GORT lot method: {method}, using PROPORTIONAL")
            return self._proportional_calculation(position_qty, gort_value, is_shorts)
    
    def _proportional_calculation(
        self,
        position_qty: float,
        gort_value: float,
        is_shorts: bool
    ) -> Tuple[int, str]:
        """
        Proportional calculation: lot = base_lot * (1 + gort * multiplier)
        
        For LONGS: Higher GORT = more to sell
        For SHORTS: Lower GORT = more to cover
        """
        base_lot = self.config.base_lot
        multiplier = self.config.gort_multiplier
        max_lot = self.config.max_lot
        
        # Adjust GORT for shorts (invert)
        effective_gort = -gort_value if is_shorts else gort_value
        
        # Calculate lot
        lot = base_lot * (1 + effective_gort * multiplier)
        
        # Clamp to max_lot
        lot = min(lot, max_lot)
        
        # Clamp to position size
        lot = min(lot, abs(position_qty))
        
        # Round to nearest 100
        lot = self._round_lot(lot)
        
        reason = f"PROPORTIONAL: base={base_lot}, gort={gort_value:.2f}, multiplier={multiplier}"
        
        return lot, reason
    
    def _tiered_calculation(
        self,
        position_qty: float,
        gort_value: float,
        is_shorts: bool
    ) -> Tuple[int, str]:
        """
        Tiered calculation: Different percentages for different GORT ranges.
        
        Example tiers:
        - GORT -1 to 0: 25%
        - GORT 0 to 1: 50%
        - GORT 1 to 2: 75%
        """
        # Adjust GORT for shorts (invert)
        effective_gort = -gort_value if is_shorts else gort_value
        
        # Find applicable tier
        lot_percentage = 50.0  # Default
        matched_tier = None
        
        for tier in self.config.tiers:
            gort_range = tier.get('gort_range', [-999, 999])
            if gort_range[0] <= effective_gort < gort_range[1]:
                lot_percentage = tier.get('lot_percentage', 50.0)
                matched_tier = tier
                break
        
        # Calculate lot
        lot = abs(position_qty) * (lot_percentage / 100.0)
        
        # Round to nearest 100
        lot = self._round_lot(lot)
        
        reason = f"TIERED: gort={gort_value:.2f}, tier={matched_tier}, percentage={lot_percentage}%"
        
        return lot, reason
    
    def _fixed_calculation(self, position_qty: float) -> Tuple[int, str]:
        """Fixed calculation: Always use fixed lot amount"""
        lot = min(self.config.fixed_lot, abs(position_qty))
        lot = self._round_lot(lot)
        
        reason = f"FIXED: lot={self.config.fixed_lot}"
        
        return lot, reason
    
    def _standard_lot_calculation(self, position_qty: float, percentage: float) -> int:
        """Standard percentage-based lot calculation"""
        lot = abs(position_qty) * (percentage / 100.0)
        return self._round_lot(lot)
    
    def _round_lot(self, lot: float) -> int:
        """
        Round lot using Janall's logic.
        
        Janall logic:
        - <= 100: 100
        - <= 200: 200
        - ...
        - > 1000: round to nearest 100
        """
        if lot <= 0:
            return 0
        elif lot <= 100:
            return 100
        elif lot <= 200:
            return 200
        elif lot <= 300:
            return 300
        elif lot <= 400:
            return 400
        elif lot <= 500:
            return 500
        elif lot <= 600:
            return 600
        elif lot <= 700:
            return 700
        elif lot <= 800:
            return 800
        elif lot <= 900:
            return 900
        elif lot <= 1000:
            return 1000
        else:
            return int((lot + 50) // 100) * 100


# ============================================================================
# Global Instance Management
# ============================================================================

_gort_lot_calculator: Optional[GortLotCalculator] = None


def get_gort_lot_calculator() -> Optional[GortLotCalculator]:
    """Get global GortLotCalculator instance"""
    return _gort_lot_calculator


def initialize_gort_lot_calculator(config: Optional[Dict[str, Any]] = None) -> GortLotCalculator:
    """Initialize global GortLotCalculator instance"""
    global _gort_lot_calculator
    
    if config:
        gort_config = GortLotConfig(
            enabled=config.get('enabled', True),
            method=config.get('method', 'PROPORTIONAL'),
            base_lot=config.get('proportional', {}).get('base_lot', 100),
            gort_multiplier=config.get('proportional', {}).get('gort_multiplier', 0.5),
            max_lot=config.get('proportional', {}).get('max_lot', 500),
            fixed_lot=config.get('fixed', {}).get('lot', 200),
            tiers=config.get('tiered', [])
        )
        _gort_lot_calculator = GortLotCalculator(config=gort_config)
    else:
        config_path = Path(__file__).parent.parent / 'config' / 'psfalgo_rules.yaml'
        _gort_lot_calculator = GortLotCalculator(config_path=config_path)
    
    logger.info("GortLotCalculator initialized (Janall-compatible)")
    return _gort_lot_calculator





