"""
ADDNEWPOS Settings Store - ACCOUNT-AWARE VERSION

Stores and retrieves ADDNEWPOS configuration per trading account.

ACCOUNT-SPECIFIC SETTINGS:
- HAMPRO has its own ADDNEWPOS settings
- IBKR_PED has its own ADDNEWPOS settings  
- IBKR_GUN has its own ADDNEWPOS settings

Each account stores:
- Global settings (enabled, mode, long/short ratio)
- Per-tab settings (BB, FB, SAS, SFS with JFIN%, filters, etc.)

BACKWARD COMPATIBILITY:
- Old single-account JSON → Migrated to all accounts
- CSV save/load → Per-account CSV files

CSV Format: config/addnewpos_csvs/{account_id}_addnewpos.csv
JSON Format: config/addnewpos_settings_v2.json
"""

import csv
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from loguru import logger

# File paths
SETTINGS_JSON_V2 = "addnewpos_settings_v2.json"  # New account-aware format
SETTINGS_JSON_V1 = "addnewpos_xnl_settings.json"  # Old single-account format
LAST_CSV_JSON = "last_addnewpos_csv.json"
CSV_DIR_NAME = "addnewpos_csvs"


@dataclass
class TabSettings:
    """Settings specific to each tab (BB, FB, SAS, SFS)"""
    jfin_pct: int = 50  # 0, 25, 50, 75, 100 (0 = skip this tab, no orders sent)
    
    # GORT range filter
    gort_min: Optional[float] = None
    gort_max: Optional[float] = None
    
    # FBtot filter (for BB/FB) or SFStot filter (for SAS/SFS)
    tot_threshold: Optional[float] = None
    tot_direction: str = "above"  # above or below
    
    # SMA63chg filter
    sma63chg_threshold: Optional[float] = None
    sma63chg_direction: str = "below"  # above or below


@dataclass
class AddnewposSettings:
    """ADDNEWPOS configuration settings with per-tab support"""
    # Global settings (shared across all tabs)
    enabled: bool = True
    mode: str = "both"  # both, addlong_only, addshort_only
    long_ratio: float = 50.0
    short_ratio: float = 50.0
    
    # Currently active tab for UI
    active_tab: str = "BB"  # BB, FB, SAS, SFS
    
    # Per-tab settings
    tab_bb: TabSettings = field(default_factory=TabSettings)
    tab_fb: TabSettings = field(default_factory=TabSettings)
    tab_sas: TabSettings = field(default_factory=TabSettings)
    tab_sfs: TabSettings = field(default_factory=TabSettings)


def tab_settings_to_dict(ts: TabSettings) -> Dict[str, Any]:
    """Convert TabSettings to dict"""
    return {
        'jfin_pct': ts.jfin_pct,
        'gort_min': ts.gort_min,
        'gort_max': ts.gort_max,
        'tot_threshold': ts.tot_threshold,
        'tot_direction': ts.tot_direction,
        'sma63chg_threshold': ts.sma63chg_threshold,
        'sma63chg_direction': ts.sma63chg_direction
    }


def dict_to_tab_settings(data: Dict[str, Any]) -> TabSettings:
    """Convert dict to TabSettings"""
    return TabSettings(
        jfin_pct=data.get('jfin_pct', 50),
        gort_min=data.get('gort_min'),
        gort_max=data.get('gort_max'),
        tot_threshold=data.get('tot_threshold'),
        tot_direction=data.get('tot_direction', 'above'),
        sma63chg_threshold=data.get('sma63chg_threshold'),
        sma63chg_direction=data.get('sma63chg_direction', 'below')
    )


def _config_dir() -> Path:
    """quant_engine/config"""
    return Path(__file__).resolve().parent.parent / "config"


def _settings_path_v2() -> Path:
    """Path to new account-aware settings file"""
    return _config_dir() / SETTINGS_JSON_V2


def _settings_path_v1() -> Path:
    """Path to old single-account settings file (for migration)"""
    return _config_dir() / SETTINGS_JSON_V1


def _last_csv_path_file() -> Path:
    return _config_dir() / LAST_CSV_JSON


def get_last_addnewpos_csv_path() -> Optional[str]:
    """Return persisted 'last used CSV' path, or None."""
    try:
        p = _last_csv_path_file()
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("path") or None
    except Exception as e:
        logger.debug(f"[ADDNEWPOS_SETTINGS] Read last CSV path: {e}")
    return None


def set_last_addnewpos_csv_path(path: str) -> None:
    """Persist 'last used CSV' path."""
    try:
        _config_dir().mkdir(parents=True, exist_ok=True)
        with open(_last_csv_path_file(), "w", encoding="utf-8") as f:
            json.dump({"path": path}, f, indent=0)
    except Exception as e:
        logger.warning(f"[ADDNEWPOS_SETTINGS] Write last CSV path: {e}")


class AddnewposSettingsStore:
    """Persistent storage for ADDNEWPOS settings - ACCOUNT-AWARE"""
    
    def __init__(self):
        self.config_path_v2 = _settings_path_v2()
        self.config_path_v1 = _settings_path_v1()  # For migration
        self._csv_dir = _config_dir() / CSV_DIR_NAME
        
        # Account-specific settings: {account_id: AddnewposSettings}
        self.accounts_settings: Dict[str, AddnewposSettings] = {}
        
        # Load settings (v2 → v1 → defaults)
        self._load()
        
        logger.info(f"[ADDNEWPOS_SETTINGS] Initialized (Account-Aware). Accounts: {list(self.accounts_settings.keys())}")
    
    def _load(self):
        """Load settings: v2 JSON → migrate v1 → defaults."""
        try:
            # Try v2 (account-aware) first
            if self.config_path_v2.exists():
                with open(self.config_path_v2, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                version = data.get('version', 1)
                accounts_data = data.get('accounts', {})
                
                for account_id, acc_data in accounts_data.items():
                    self.accounts_settings[account_id] = AddnewposSettings(
                        enabled=acc_data.get('enabled', True),
                        mode=acc_data.get('mode', 'both'),
                        long_ratio=acc_data.get('long_ratio', 50.0),
                        short_ratio=acc_data.get('short_ratio', 50.0),
                        active_tab=acc_data.get('active_tab', 'BB'),
                        tab_bb=dict_to_tab_settings(acc_data.get('tab_bb', {})),
                        tab_fb=dict_to_tab_settings(acc_data.get('tab_fb', {})),
                        tab_sas=dict_to_tab_settings(acc_data.get('tab_sas', {})),
                        tab_sfs=dict_to_tab_settings(acc_data.get('tab_sfs', {}))
                    )
                logger.info(f"[ADDNEWPOS_SETTINGS] Loaded v2 (account-aware): {list(self.accounts_settings.keys())}")
                return
            
            # Migrate from v1 (single-account) if exists
            if self.config_path_v1.exists():
                with open(self.config_path_v1, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Apply to all known accounts
                default_settings = AddnewposSettings(
                    enabled=data.get('enabled', True),
                    mode=data.get('mode', 'both'),
                    long_ratio=data.get('long_ratio', 50.0),
                    short_ratio=data.get('short_ratio', 50.0),
                    active_tab=data.get('active_tab', 'BB'),
                    tab_bb=dict_to_tab_settings(data.get('tab_bb', {})),
                    tab_fb=dict_to_tab_settings(data.get('tab_fb', {})),
                    tab_sas=dict_to_tab_settings(data.get('tab_sas', {})),
                    tab_sfs=dict_to_tab_settings(data.get('tab_sfs', {}))
                )
                
                # Create for all known accounts
                for account in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
                    self.accounts_settings[account] = default_settings
                
                logger.info(f"[ADDNEWPOS_SETTINGS] Migrated from v1 to v2 (applied to all accounts)")
                self.save()  # Save as v2
                return
            
            # No settings file, use defaults for all accounts
            for account in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
                self.accounts_settings[account] = AddnewposSettings()
            logger.info("[ADDNEWPOS_SETTINGS] No settings file, using defaults for all accounts")
            
        except Exception as e:
            logger.error(f"[ADDNEWPOS_SETTINGS] Load error: {e}")
            # Fallback: defaults for all accounts
            for account in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
                self.accounts_settings[account] = AddnewposSettings()
    
    def save(self) -> bool:
        """Save all account settings to v2 JSON file"""
        try:
            self.config_path_v2.parent.mkdir(parents=True, exist_ok=True)
            
            accounts_data = {}
            for account_id, settings in self.accounts_settings.items():
                accounts_data[account_id] = {
                    'enabled': settings.enabled,
                    'mode': settings.mode,
                    'long_ratio': settings.long_ratio,
                    'short_ratio': settings.short_ratio,
                    'active_tab': settings.active_tab,
                    'tab_bb': tab_settings_to_dict(settings.tab_bb),
                    'tab_fb': tab_settings_to_dict(settings.tab_fb),
                    'tab_sas': tab_settings_to_dict(settings.tab_sas),
                    'tab_sfs': tab_settings_to_dict(settings.tab_sfs)
                }
            
            data = {
                'version': 2,
                'accounts': accounts_data
            }
            
            with open(self.config_path_v2, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"[ADDNEWPOS_SETTINGS] Saved v2 (accounts: {list(self.accounts_settings.keys())})")
            return True
        except Exception as e:
            logger.error(f"[ADDNEWPOS_SETTINGS] Save error: {e}")
            return False
    
    def get_settings(self, account_id: str) -> Dict[str, Any]:
        """Get settings for specific account as dict"""
        if account_id not in self.accounts_settings:
            self.accounts_settings[account_id] = AddnewposSettings()
        
        settings = self.accounts_settings[account_id]
        return {
            'enabled': settings.enabled,
            'mode': settings.mode,
            'long_ratio': settings.long_ratio,
            'short_ratio': settings.short_ratio,
            'active_tab': settings.active_tab,
            'tab_bb': tab_settings_to_dict(settings.tab_bb),
            'tab_fb': tab_settings_to_dict(settings.tab_fb),
            'tab_sas': tab_settings_to_dict(settings.tab_sas),
            'tab_sfs': tab_settings_to_dict(settings.tab_sfs)
        }
    
    def update_settings(self, account_id: str, updates: Dict[str, Any]) -> bool:
        """Update settings for specific account"""
        try:
            if account_id not in self.accounts_settings:
                self.accounts_settings[account_id] = AddnewposSettings()
            
            settings = self.accounts_settings[account_id]
            
            # Update global settings
            if 'enabled' in updates:
                settings.enabled = updates['enabled']
            if 'mode' in updates:
                settings.mode = updates['mode']
            if 'long_ratio' in updates:
                settings.long_ratio = updates['long_ratio']
            if 'short_ratio' in updates:
                settings.short_ratio = updates['short_ratio']
            if 'active_tab' in updates:
                settings.active_tab = updates['active_tab']
            
            # Update per-tab settings
            if 'tab_bb' in updates:
                settings.tab_bb = dict_to_tab_settings(updates['tab_bb'])
            if 'tab_fb' in updates:
                settings.tab_fb = dict_to_tab_settings(updates['tab_fb'])
            if 'tab_sas' in updates:
                settings.tab_sas = dict_to_tab_settings(updates['tab_sas'])
            if 'tab_sfs' in updates:
                settings.tab_sfs = dict_to_tab_settings(updates['tab_sfs'])
            
            return self.save()
        except Exception as e:
            logger.error(f"[ADDNEWPOS_SETTINGS] Update error for {account_id}: {e}")
            return False


# Global instance
_settings_store: Optional[AddnewposSettingsStore] = None


def get_addnewpos_settings_store() -> AddnewposSettingsStore:
    """Get global settings store instance"""
    global _settings_store
    if _settings_store is None:
        _settings_store = AddnewposSettingsStore()
    return _settings_store
