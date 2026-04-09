"""
RevOrder Configuration
Load and manage RevOrder rules from CSV.
"""
import pandas as pd
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from loguru import logger


@dataclass
class RevOrderConfig:
    """RevOrder configuration (from CSV)"""
    inc_min_profit: float = 0.04
    dec_min_save: float = 0.06
    spread_wide_threshold: float = 0.20
    orderbook_max_levels: int = 10
    spread_factor: float = 0.15


def load_revorder_config() -> RevOrderConfig:
    """
    Load RevOrder configuration from CSV.
    
    Returns:
        RevOrderConfig with loaded or default values
    """
    config_path = Path(__file__).parent.parent.parent / "config" / "revorder_rules.csv"
    
    try:
        if config_path.exists():
            df = pd.read_csv(config_path)
            config_dict = dict(zip(df['setting'], df['value']))
            
            config = RevOrderConfig(
                inc_min_profit=float(config_dict.get('inc_min_profit', 0.04)),
                dec_min_save=float(config_dict.get('dec_min_save', 0.06)),
                spread_wide_threshold=float(config_dict.get('spread_wide_threshold', 0.20)),
                orderbook_max_levels=int(config_dict.get('orderbook_max_levels', 10)),
                spread_factor=float(config_dict.get('spread_factor', 0.15))
            )
            
            logger.info(f"[RevOrderConfig] Loaded from {config_path}")
            return config
        else:
            logger.warning(f"[RevOrderConfig] Not found at {config_path}, using defaults")
            return RevOrderConfig()
    
    except Exception as e:
        logger.error(f"[RevOrderConfig] Error loading: {e}", exc_info=True)
        return RevOrderConfig(

)
