"""
StrategyConfigManager - 3-Layer Configuration System
====================================================

This module manages the "Effective Rules" for the execution engines.
It implements the 3-layer hierarchy:

1.  **Defaults**: Static rules from `psfalgo_rules.yaml`.
2.  **User Settings**: Account-scoped overrides persisted in `data/strategy_settings/{account_id}.json`.
3.  **Runtime Overrides**: In-memory ephemeral parameter tweaks (e.g. changing a threshold for the day).

The `get_effective_rules(account_id)` method merges these layers in order.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from copy import deepcopy

from app.core.logger import logger

class StrategyConfigManager:
    """Manages strategy configuration layers."""
    
    def __init__(self, config_dir: Path = None, data_dir: Path = None):
        self.config_dir = config_dir or Path("app/config")
        self.data_dir = data_dir or Path("data")
        self.settings_dir = self.data_dir / "strategy_settings"
        
        # Ensure directories exist
        self.settings_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Load Defaults
        self._defaults = self._load_defaults()
        
        # 3. Runtime Overrides (In-Memory)
        self._runtime_overrides: Dict[str, Dict[str, Any]] = {}
        
    def _load_defaults(self) -> Dict[str, Any]:
        """Load default rules from YAML."""
        yaml_path = self.config_dir / "psfalgo_rules.yaml"
        if not yaml_path.exists():
            logger.error(f"Default rules not found at {yaml_path}")
            return {}
            
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading default rules: {e}")
            return {}

    def _load_user_settings(self, account_id: str) -> Dict[str, Any]:
        """Load user settings from JSON."""
        json_path = self.settings_dir / f"{account_id}.json"
        if not json_path.exists():
            return {}
            
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading user settings for {account_id}: {e}")
            return {}

    def _merge_dicts(self, base: Dict, update: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = deepcopy(base)
        for k, v in update.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._merge_dicts(result[k], v)
            else:
                result[k] = v
        return result

    def get_effective_rules(self, account_id: str) -> Dict[str, Any]:
        """
        Get the final merged configuration for an account.
        Order: Defaults | User Settings | Runtime Overrides
        """
        # 1. Start with Defaults
        rules = deepcopy(self._defaults)
        
        # 2. Merge User Settings
        user_settings = self._load_user_settings(account_id)
        rules = self._merge_dicts(rules, user_settings)
        
        # 3. Merge Runtime Overrides
        overrides = self._runtime_overrides.get(account_id, {})
        rules = self._merge_dicts(rules, overrides)
        
        return rules

    def set_runtime_override(self, account_id: str, path: str, value: Any):
        """
        Set a runtime override for a specific parameter.
        Path examples: "karbotu.step_2.filters.fbtot_lt", "general.cycle.interval_seconds"
        """
        if account_id not in self._runtime_overrides:
            self._runtime_overrides[account_id] = {}
            
        # Helper to set nested dict value
        keys = path.split('.')
        current = self._runtime_overrides[account_id]
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
            if not isinstance(current, dict):
                 # Conflict: trying to nest into a non-dict
                 logger.warning(f"Cannot set override {path}: {key} is not a dict")
                 return
        
        current[keys[-1]] = value
        logger.info(f"Set runtime override for {account_id}: {path} = {value}")

    def save_user_settings(self, account_id: str, settings: Dict[str, Any]):
        """Save persistent user settings."""
        json_path = self.settings_dir / f"{account_id}.json"
        try:
            # Load existing to merge partial updates if needed, 
            # but usually UI sends full section or we handle partials upstream.
            # Here we assume 'settings' contains the updates to be persisted.
            current = self._load_user_settings(account_id)
            updated = self._merge_dicts(current, settings)
            
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(updated, f, indent=2)
            logger.info(f"Saved user settings for {account_id}")
            
        except Exception as e:
            logger.error(f"Error saving user settings for {account_id}: {e}")

# Global Instance
_config_manager = StrategyConfigManager()

def get_strategy_config_manager() -> StrategyConfigManager:
    return _config_manager
