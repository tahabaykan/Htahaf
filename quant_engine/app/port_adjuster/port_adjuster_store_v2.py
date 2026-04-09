"""
Port Adjuster Store V2 - Account-Aware Configuration Management

This store manages separate Port Adjuster configurations per trading account:
- IBKR_PED
- HAMPRO
- IBKR_GUN

All configurations are stored in a single JSON file for easy management.
"""

from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import json
from app.core.logger import logger
from app.port_adjuster.port_adjuster_engine import PortAdjusterEngine, get_port_adjuster_engine
from app.port_adjuster.port_adjuster_models import (
    PortAdjusterConfig,
    PortAdjusterSnapshot
)
from app.port_adjuster.port_adjuster_csv import load_config_from_csv, save_config_to_csv


# Default configuration for each account
DEFAULT_ACCOUNT_CONFIGS = {
    "IBKR_PED": {
        "total_exposure_usd": 1_200_000,
        "avg_pref_price": 20.0,
        "long_ratio_pct": 60.0,
        "short_ratio_pct": 40.0,
        "lt_ratio_pct": 70.0,
        "mm_ratio_pct": 30.0,
        "lt_potential_multiplier": 1.5,
        "mm_potential_multiplier": 2.0,
        "long_groups": {},
        "short_groups": {}
    },
    "HAMPRO": {
        "total_exposure_usd": 800_000,
        "avg_pref_price": 18.0,
        "long_ratio_pct": 55.0,
        "short_ratio_pct": 45.0,
        "lt_ratio_pct": 65.0,
        "mm_ratio_pct": 35.0,
        "lt_potential_multiplier": 1.3,
        "mm_potential_multiplier": 1.8,
        "long_groups": {},
        "short_groups": {}
    },
    "IBKR_GUN": {
        "total_exposure_usd": 1_500_000,
        "avg_pref_price": 22.0,
        "long_ratio_pct": 65.0,
        "short_ratio_pct": 35.0,
        "lt_ratio_pct": 75.0,
        "mm_ratio_pct": 25.0,
        "lt_potential_multiplier": 1.6,
        "mm_potential_multiplier": 2.2,
        "long_groups": {},
        "short_groups": {}
    }
}


def _get_config_dir() -> Path:
    """Get config directory path."""
    base = Path(__file__).resolve().parents[2]
    return base / "config"


def _get_v2_config_path() -> Path:
    """Get V2 config file path."""
    return _get_config_dir() / "port_adjuster_v2.json"


class PortAdjusterStoreV2:
    """
    Port Adjuster Store V2 - Account-Aware Configuration Management.
    
    Manages separate configurations for each trading account:
    - IBKR_PED
    - HAMPRO  
    - IBKR_GUN
    
    All configs stored in config/port_adjuster_v2.json
    """
    
    VALID_ACCOUNTS = ["IBKR_PED", "HAMPRO", "IBKR_GUN"]
    
    def __init__(self):
        """Initialize V2 Store with account-aware configs."""
        self.engine: PortAdjusterEngine = get_port_adjuster_engine()
        
        # Account-specific configs and snapshots
        self._configs: Dict[str, PortAdjusterConfig] = {}
        self._snapshots: Dict[str, PortAdjusterSnapshot] = {}
        self._last_saved_at: Dict[str, Optional[datetime]] = {}
        
        # Load from JSON
        self._load_from_json()
        
        logger.info("[PORT_ADJUSTER_V2] Store initialized with account-aware configs")
    
    def _normalize_account_id(self, account_id: str) -> str:
        """Normalize account ID to standard format."""
        acc = account_id.upper().strip()
        # Map common aliases
        if acc == "HAMMER_PRO":
            acc = "HAMPRO"
        if acc not in self.VALID_ACCOUNTS:
            logger.warning(f"[PORT_ADJUSTER_V2] Unknown account '{acc}', defaulting to IBKR_PED")
            acc = "IBKR_PED"
        return acc
    
    def _load_from_json(self) -> None:
        """Load configurations from JSON file."""
        config_path = _get_v2_config_path()
        
        try:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                for account_id in self.VALID_ACCOUNTS:
                    if account_id in data:
                        cfg_data = data[account_id]
                        cfg = PortAdjusterConfig(**cfg_data)
                        self._configs[account_id] = cfg
                        self._snapshots[account_id] = self.engine.calculate_snapshot(cfg)
                        self._last_saved_at[account_id] = datetime.now()
                        logger.info(f"[PORT_ADJUSTER_V2] Loaded config for {account_id}")
                    else:
                        # Use default
                        self._apply_default_config(account_id)
            else:
                # First run - create with defaults
                self._create_default_configs()
                self._save_to_json()
                
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER_V2] Error loading configs: {e}", exc_info=True)
            self._create_default_configs()
    
    def _create_default_configs(self) -> None:
        """Create default configs for all accounts."""
        for account_id in self.VALID_ACCOUNTS:
            self._apply_default_config(account_id)
    
    def _apply_default_config(self, account_id: str) -> None:
        """Apply default config for an account."""
        default_data = DEFAULT_ACCOUNT_CONFIGS.get(account_id, DEFAULT_ACCOUNT_CONFIGS["IBKR_PED"])
        cfg = PortAdjusterConfig(**default_data)
        self._configs[account_id] = cfg
        self._snapshots[account_id] = self.engine.calculate_snapshot(cfg)
        self._last_saved_at[account_id] = datetime.now()
        logger.info(f"[PORT_ADJUSTER_V2] Applied default config for {account_id}")
    
    def _save_to_json(self) -> None:
        """Save all configurations to JSON file."""
        try:
            config_path = _get_v2_config_path()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {}
            for account_id, cfg in self._configs.items():
                data[account_id] = cfg.dict()
            
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"[PORT_ADJUSTER_V2] Saved configs to {config_path}")
            
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER_V2] Error saving configs: {e}", exc_info=True)
    
    def get_config(self, account_id: str) -> Optional[PortAdjusterConfig]:
        """Get configuration for a specific account."""
        acc = self._normalize_account_id(account_id)
        return self._configs.get(acc)
    
    def get_snapshot(self, account_id: str) -> Optional[PortAdjusterSnapshot]:
        """Get snapshot for a specific account."""
        acc = self._normalize_account_id(account_id)
        return self._snapshots.get(acc)
    
    def update_config(self, account_id: str, config: PortAdjusterConfig) -> PortAdjusterSnapshot:
        """
        Update configuration for a specific account.
        
        Args:
            account_id: Account identifier (IBKR_PED, HAMPRO, IBKR_GUN)
            config: New configuration
            
        Returns:
            New calculated snapshot
        """
        acc = self._normalize_account_id(account_id)
        
        try:
            self._configs[acc] = config
            snapshot = self.engine.calculate_snapshot(config)
            snapshot.last_saved_at = datetime.now()
            snapshot.config_source = f"api:{acc}"
            self._snapshots[acc] = snapshot
            self._last_saved_at[acc] = datetime.now()
            
            # Persist to JSON
            self._save_to_json()
            
            logger.info(
                f"[PORT_ADJUSTER_V2] Config updated for {acc}: "
                f"exposure=${config.total_exposure_usd:,.0f}"
            )
            
            return snapshot
            
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER_V2] Error updating config for {acc}: {e}", exc_info=True)
            raise
    
    def recalculate(self, account_id: str) -> Optional[PortAdjusterSnapshot]:
        """Recalculate snapshot for an account."""
        acc = self._normalize_account_id(account_id)
        cfg = self._configs.get(acc)
        
        if cfg is None:
            return None
        
        snapshot = self.engine.calculate_snapshot(cfg)
        snapshot.last_saved_at = self._last_saved_at.get(acc)
        self._snapshots[acc] = snapshot
        
        return snapshot
    
    def get_all_configs(self) -> Dict[str, PortAdjusterConfig]:
        """Get all account configurations."""
        return dict(self._configs)
    
    def get_group_max_lot(self, account_id: str, group: str, side: str = "LONG") -> Optional[float]:
        """Get maximum lot for a group in a specific account."""
        acc = self._normalize_account_id(account_id)
        snapshot = self._snapshots.get(acc)
        if snapshot is None:
            return None
        return self.engine.get_group_max_lot(snapshot, group, side)
    
    def get_group_max_value_usd(self, account_id: str, group: str, side: str = "LONG") -> Optional[float]:
        """Get maximum value (USD) for a group in a specific account."""
        acc = self._normalize_account_id(account_id)
        snapshot = self._snapshots.get(acc)
        if snapshot is None:
            return None
        return self.engine.get_group_max_value_usd(snapshot, group, side)
    
    # CSV Import/Export for account-specific configs
    def save_account_to_csv(self, account_id: str, filename: str) -> Optional[str]:
        """Save account config to CSV file."""
        acc = self._normalize_account_id(account_id)
        cfg = self._configs.get(acc)
        if cfg is None:
            return None
        
        # Build path
        base = Path(__file__).resolve().parents[3]
        csv_dir = base / "port_adjuster_csvs"
        csv_dir.mkdir(parents=True, exist_ok=True)
        
        # Include account in filename
        name = (filename or f"portadj_{acc.lower()}").strip()
        if not name.endswith(".csv"):
            name += ".csv"
        
        path = str(csv_dir / name)
        
        if save_config_to_csv(cfg, path):
            logger.info(f"[PORT_ADJUSTER_V2] Saved {acc} config to CSV: {path}")
            return path
        return None
    
    def load_account_from_csv(self, account_id: str, filepath: str) -> Optional[PortAdjusterSnapshot]:
        """Load account config from CSV file."""
        acc = self._normalize_account_id(account_id)
        
        cfg = load_config_from_csv(filepath)
        if cfg is None:
            return None
        
        return self.update_config(acc, cfg)


# Singleton instance
_port_adjuster_store_v2: Optional[PortAdjusterStoreV2] = None


def get_port_adjuster_store_v2() -> PortAdjusterStoreV2:
    """Get singleton V2 Port Adjuster Store instance."""
    global _port_adjuster_store_v2
    if _port_adjuster_store_v2 is None:
        _port_adjuster_store_v2 = PortAdjusterStoreV2()
    return _port_adjuster_store_v2
