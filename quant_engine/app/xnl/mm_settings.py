"""
MM Settings Store

Stores and retrieves MM (Market Making) configuration for XNL Engine.

Settings:
- Est/Cur ratio (for stock count adjustment)
- Enabled flag
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class MMSettings:
    """MM configuration settings"""
    enabled: bool = True
    est_cur_ratio: float = 44.0  # Default Est/Cur ratio (%)
    min_stock_count: int = 5  # Minimum stocks per side
    max_stock_count: int = 100  # Maximum stocks per side
    lot_per_stock: int = 200  # Fixed lot size per stock
    lot_mode: str = 'fixed'  # 'fixed' or 'adv_adjust' (AVG ADV via FreeExposure tiers)


class MMSettingsStore:
    """Persistent storage for MM settings"""
    
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            # Store in quant_engine/config directory
            config_path = Path(__file__).parent.parent / 'config' / 'mm_xnl_settings.json'
        
        self.config_path = config_path
        self.settings = MMSettings()
        
        # Load existing settings
        self._load()
        
        logger.info(f"[MM_SETTINGS] Initialized. Path: {self.config_path}")
    
    def _load(self):
        """Load settings from file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.settings = MMSettings(
                    enabled=data.get('enabled', True),
                    est_cur_ratio=data.get('est_cur_ratio', 44.0),
                    min_stock_count=data.get('min_stock_count', 5),
                    max_stock_count=data.get('max_stock_count', 100),
                    lot_per_stock=data.get('lot_per_stock', 200),
                    lot_mode=data.get('lot_mode', 'fixed')
                )
                logger.info(f"[MM_SETTINGS] Loaded settings: est_cur_ratio={self.settings.est_cur_ratio}%")
            else:
                logger.info("[MM_SETTINGS] No settings file, using defaults")
        except Exception as e:
            logger.error(f"[MM_SETTINGS] Load error: {e}")
    
    def save(self) -> bool:
        """Save settings to file"""
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = asdict(self.settings)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"[MM_SETTINGS] Saved settings: est_cur_ratio={self.settings.est_cur_ratio}%")
            return True
        except Exception as e:
            logger.error(f"[MM_SETTINGS] Save error: {e}")
            return False
    
    def get_settings(self) -> Dict[str, Any]:
        """Get settings as dict"""
        return asdict(self.settings)
    
    def update_settings(self, updates: Dict[str, Any]) -> bool:
        """Update settings from dict"""
        try:
            if 'enabled' in updates:
                self.settings.enabled = updates['enabled']
            if 'est_cur_ratio' in updates:
                self.settings.est_cur_ratio = float(updates['est_cur_ratio'])
            if 'min_stock_count' in updates:
                self.settings.min_stock_count = int(updates['min_stock_count'])
            if 'max_stock_count' in updates:
                self.settings.max_stock_count = int(updates['max_stock_count'])
            if 'lot_per_stock' in updates:
                self.settings.lot_per_stock = int(updates['lot_per_stock'])
            if 'lot_mode' in updates:
                mode = str(updates['lot_mode']).lower()
                if mode in ('fixed', 'adv_adjust'):
                    self.settings.lot_mode = mode
            
            return self.save()
        except Exception as e:
            logger.error(f"[MM_SETTINGS] Update error: {e}")
            return False


# Global instance
_settings_store: Optional[MMSettingsStore] = None


def get_mm_settings_store(config_path: Optional[Path] = None) -> MMSettingsStore:
    """Get global MM settings store instance"""
    global _settings_store
    if _settings_store is None:
        _settings_store = MMSettingsStore(config_path)
    return _settings_store

