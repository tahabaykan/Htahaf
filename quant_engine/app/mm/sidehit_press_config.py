"""
Sidehit Press Configuration
===========================

Thresholds and constants for Sidehit Press Engine.
"""

from typing import Dict, Any
from dataclasses import dataclass, field


@dataclass
class SidehitPressConfig:
    """Configuration for Sidehit Press Engine"""
    
    # =========================================================================
    # TIMEFRAMES (seconds)
    # =========================================================================
    TIMEFRAMES: Dict[str, int] = field(default_factory=lambda: {
        'TF_15M': 15 * 60,      # 900 seconds
        'TF_1H': 60 * 60,       # 3600 seconds
        'TF_4H': 4 * 60 * 60,   # 14400 seconds
        'TF_1D': 24 * 60 * 60   # 86400 seconds
    })
    
    # =========================================================================
    # VOLAV CALCULATION
    # =========================================================================
    # Bucket size for VOLAV grouping (in dollars)
    BUCKET_SIZE_DEFAULT: float = 0.01
    BUCKET_SIZE_ILLIQUID: float = 0.02  # For AVG_ADV < 5000
    BUCKET_SIZE_VERY_ILLIQUID: float = 0.05  # For AVG_ADV < 1000
    
    # Minimum tick size to consider (lots)
    MIN_TICK_SIZE: int = 20
    
    # Weighted volume: FNRA lot weights
    WEIGHT_LOT_100_200: float = 1.0
    WEIGHT_LOT_300_1000: float = 0.4
    WEIGHT_LOT_IRREGULAR: float = 0.2
    WEIGHT_NON_FNRA: float = 1.0
    
    # Band coverage: percentage of weighted volume for band calculation
    BAND_COVERAGE_PCT: float = 0.60  # 60% of volume defines band
    
    # =========================================================================
    # DRIFT THRESHOLDS
    # =========================================================================
    # Minimum drift to consider significant
    DRIFT_THRESHOLD_SIGNIFICANT: float = 0.03  # 3 cents
    
    # Strong drift threshold
    DRIFT_THRESHOLD_STRONG: float = 0.06  # 6 cents
    
    # =========================================================================
    # GROUP RELATIVE ANALYSIS
    # =========================================================================
    # Thresholds for OVERPERFORM / UNDERPERFORM classification
    GROUP_DEVIATION_THRESHOLD: float = 0.03  # 3 cents deviation from group median
    GROUP_DEVIATION_STRONG: float = 0.05  # 5 cents for strong deviation
    
    # Minimum group size for group analysis
    MIN_GROUP_SIZE: int = 3
    
    # =========================================================================
    # ZONE DISTANCE (EXECUTION MODE)
    # =========================================================================
    # Minimum spread floor for normalization
    MIN_SPREAD_FLOOR: float = 0.04  # 4 cents
    
    # Zone distance thresholds
    ZONE_DISTANCE_THRESHOLD: float = 1.5  # 1.5x spread = significant deviation
    ZONE_DISTANCE_STRONG: float = 2.5     # 2.5x spread = strong deviation
    
    # =========================================================================
    # MM SCORE WEIGHTS (EXECUTION MODE)
    # =========================================================================
    WEIGHT_INEFFICIENCY: float = 0.55
    WEIGHT_FLOW_ALIGNMENT: float = 0.25
    WEIGHT_GROUP_CONTEXT: float = 0.20
    
    # =========================================================================
    # SIDEHIT INFLUENCE (EXECUTION MODE, ACTIVE)
    # =========================================================================
    # Sidehit factor calculation: 1 - abs(Fbtot - SFStot) * k
    SIDEHIT_K_FACTOR: float = 0.01
    SIDEHIT_MIN_FACTOR: float = 0.70
    SIDEHIT_MAX_FACTOR: float = 1.10
    
    # =========================================================================
    # GUARDRAILS
    # =========================================================================
    # Minimum ticks per timeframe for valid analysis
    MIN_TICKS_PER_TIMEFRAME: int = 5
    
    # Maximum spread for MM consideration
    MAX_SPREAD_MM: float = 0.20  # 20 cents
    
    # Minimum dispersion for MM consideration
    MIN_DISPERSION_MM: float = 0.04  # 4 cents
    
    # =========================================================================
    # HELDKUPONLU SPECIAL HANDLING
    # =========================================================================
    # HELDKUPONLU symbols are normalized by CGRUP, not DOS_GRUP
    HELDKUPONLU_GROUP_NAME: str = "HELDKUPONLU"


# Global config instance
_config: SidehitPressConfig = None


def get_sidehit_config() -> SidehitPressConfig:
    """Get global Sidehit Press config"""
    global _config
    if _config is None:
        _config = SidehitPressConfig()
    return _config


def set_sidehit_config(config: SidehitPressConfig):
    """Set global Sidehit Press config"""
    global _config
    _config = config
