"""
ADDNEWPOS Settings Store

Stores and retrieves ADDNEWPOS configuration for XNL Engine.

Global Settings (shared across all tabs):
- Mode (both/addlong_only/addshort_only)
- Long/Short ratio
- Enabled flag

Per-Tab Settings (BB, FB, SAS, SFS each have their own):
- JFIN percentage
- GORT range (min/max)
- FBtot threshold (for BB/FB) or SFStot threshold (for SAS/SFS)
- SMA63chg threshold

CSV Save/Load: settings can be saved to a named CSV and loaded from it.
"Last used CSV" path is persisted; on app startup that file is loaded if it exists.
"""

import csv
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from loguru import logger

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


def get_last_addnewpos_csv_path_resolved() -> Optional[str]:
    """Return last-used CSV path that actually exists (try stored path, then config/addnewpos_csvs/<name>)."""
    raw = get_last_addnewpos_csv_path()
    if not raw or not raw.strip():
        return None
    path = Path(raw)
    if path.exists():
        return str(path.resolve())
    # Stored path may be from another machine or relative; try config/addnewpos_csvs/<filename>
    base = path.name
    if not base:
        return None
    fallback = _config_dir() / CSV_DIR_NAME / base
    if fallback.exists():
        return str(fallback.resolve())
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
    """Persistent storage for ADDNEWPOS settings"""
    
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'addnewpos_xnl_settings.json'
        
        self.config_path = config_path
        self.settings = AddnewposSettings()
        self._csv_dir = _config_dir() / CSV_DIR_NAME
        
        # Load: prefer last-used CSV if it exists, else JSON, else defaults
        self._load()
        
        logger.info(f"[ADDNEWPOS_SETTINGS] Initialized. Path: {self.config_path}")
    
    def _load(self):
        """Load settings: last-used CSV if exists, else JSON, else defaults."""
        try:
            last_csv = get_last_addnewpos_csv_path_resolved()
            if last_csv:
                self._load_from_csv_into_settings(Path(last_csv))
                logger.info(f"[ADDNEWPOS_SETTINGS] Loaded from last CSV: {Path(last_csv).name}")
                return
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.settings = AddnewposSettings(
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
                logger.info(f"[ADDNEWPOS_SETTINGS] Loaded from JSON: mode={self.settings.mode}")
            else:
                logger.info("[ADDNEWPOS_SETTINGS] No settings file, using defaults")
        except Exception as e:
            logger.error(f"[ADDNEWPOS_SETTINGS] Load error: {e}")
    
    def _load_from_csv_into_settings(self, path: Path) -> None:
        """Parse CSV and set self.settings. CSV format: section,key,value."""
        data: Dict[str, Dict[str, Any]] = {"global": {}, "tab_bb": {}, "tab_fb": {}, "tab_sas": {}, "tab_sfs": {}}
        with open(path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                sec = (row.get("section") or "global").strip().lower()
                key = (row.get("key") or "").strip()
                val = row.get("value", "")
                if sec not in data:
                    data[sec] = {}
                if key:
                    if val in ("true", "yes", "1"): data[sec][key] = True
                    elif val in ("false", "no", "0"): data[sec][key] = False
                    elif val in ("", "null", "None"): data[sec][key] = None
                    else:
                        try:
                            data[sec][key] = float(val) if "." in val or "e" in val.lower() else int(val)
                        except ValueError:
                            data[sec][key] = val
        g = data.get("global", {})
        self.settings = AddnewposSettings(
            enabled=g.get("enabled", True),
            mode=g.get("mode", "both"),
            long_ratio=float(g.get("long_ratio", 50.0)),
            short_ratio=float(g.get("short_ratio", 50.0)),
            active_tab=g.get("active_tab") or "BB",
            tab_bb=dict_to_tab_settings(data.get("tab_bb", {})),
            tab_fb=dict_to_tab_settings(data.get("tab_fb", {})),
            tab_sas=dict_to_tab_settings(data.get("tab_sas", {})),
            tab_sfs=dict_to_tab_settings(data.get("tab_sfs", {}))
        )
    
    def save_to_csv(self, file_path: str) -> bool:
        """Save current settings to CSV; persist as last-used. Returns True on success."""
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            rows = [
                ("section", "key", "value"),
                ("global", "enabled", str(self.settings.enabled)),
                ("global", "mode", self.settings.mode),
                ("global", "long_ratio", str(self.settings.long_ratio)),
                ("global", "short_ratio", str(self.settings.short_ratio)),
                ("global", "active_tab", self.settings.active_tab),
            ]
            for tab_name, ts in [("tab_bb", self.settings.tab_bb), ("tab_fb", self.settings.tab_fb),
                                 ("tab_sas", self.settings.tab_sas), ("tab_sfs", self.settings.tab_sfs)]:
                d = tab_settings_to_dict(ts)
                for k, v in d.items():
                    rows.append((tab_name, k, "" if v is None else str(v)))
            with open(path, "w", encoding="utf-8", newline="") as f:
                csv.writer(f).writerows(rows)
            set_last_addnewpos_csv_path(str(path.resolve()))
            logger.info(f"[ADDNEWPOS_SETTINGS] Saved to CSV: {path}")
            return True
        except Exception as e:
            logger.error(f"[ADDNEWPOS_SETTINGS] Save CSV error: {e}")
            return False
    
    def load_from_csv(self, file_path: str) -> bool:
        """Load settings from CSV and set as last-used. Returns True on success."""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"[ADDNEWPOS_SETTINGS] CSV not found: {path}")
                return False
            self._load_from_csv_into_settings(path)
            set_last_addnewpos_csv_path(str(path.resolve()))
            self.save()  # sync to default JSON so other in-memory state stays consistent
            logger.info(f"[ADDNEWPOS_SETTINGS] Loaded from CSV: {path}")
            return True
        except Exception as e:
            logger.error(f"[ADDNEWPOS_SETTINGS] Load CSV error: {e}")
            return False
    
    def save(self) -> bool:
        """Save settings to file"""
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'enabled': self.settings.enabled,
                'mode': self.settings.mode,
                'long_ratio': self.settings.long_ratio,
                'short_ratio': self.settings.short_ratio,
                'active_tab': self.settings.active_tab,
                'tab_bb': tab_settings_to_dict(self.settings.tab_bb),
                'tab_fb': tab_settings_to_dict(self.settings.tab_fb),
                'tab_sas': tab_settings_to_dict(self.settings.tab_sas),
                'tab_sfs': tab_settings_to_dict(self.settings.tab_sfs)
            }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"[ADDNEWPOS_SETTINGS] Saved settings: mode={self.settings.mode}")
            return True
        except Exception as e:
            logger.error(f"[ADDNEWPOS_SETTINGS] Save error: {e}")
            return False
    
    def get_settings(self) -> Dict[str, Any]:
        """Get settings as dict"""
        return {
            'enabled': self.settings.enabled,
            'mode': self.settings.mode,
            'long_ratio': self.settings.long_ratio,
            'short_ratio': self.settings.short_ratio,
            'active_tab': self.settings.active_tab,
            'tab_bb': tab_settings_to_dict(self.settings.tab_bb),
            'tab_fb': tab_settings_to_dict(self.settings.tab_fb),
            'tab_sas': tab_settings_to_dict(self.settings.tab_sas),
            'tab_sfs': tab_settings_to_dict(self.settings.tab_sfs)
        }
    
    def get_tab_settings(self, tab: str) -> Dict[str, Any]:
        """Get settings for a specific tab"""
        tab_map = {
            'BB': self.settings.tab_bb,
            'FB': self.settings.tab_fb,
            'SAS': self.settings.tab_sas,
            'SFS': self.settings.tab_sfs
        }
        ts = tab_map.get(tab.upper(), self.settings.tab_bb)
        return tab_settings_to_dict(ts)
    
    def update_settings(self, updates: Dict[str, Any]) -> bool:
        """Update settings from dict"""
        try:
            # Update global settings
            if 'enabled' in updates:
                self.settings.enabled = updates['enabled']
            if 'mode' in updates:
                self.settings.mode = updates['mode']
            if 'long_ratio' in updates:
                self.settings.long_ratio = updates['long_ratio']
            if 'short_ratio' in updates:
                self.settings.short_ratio = updates['short_ratio']
            if 'active_tab' in updates:
                self.settings.active_tab = updates['active_tab']
            
            # Update per-tab settings
            if 'tab_bb' in updates:
                self.settings.tab_bb = dict_to_tab_settings(updates['tab_bb'])
            if 'tab_fb' in updates:
                self.settings.tab_fb = dict_to_tab_settings(updates['tab_fb'])
            if 'tab_sas' in updates:
                self.settings.tab_sas = dict_to_tab_settings(updates['tab_sas'])
            if 'tab_sfs' in updates:
                self.settings.tab_sfs = dict_to_tab_settings(updates['tab_sfs'])
            
            return self.save()
        except Exception as e:
            logger.error(f"[ADDNEWPOS_SETTINGS] Update error: {e}")
            return False


# Global instance
_settings_store: Optional[AddnewposSettingsStore] = None


def get_addnewpos_settings_store() -> AddnewposSettingsStore:
    """Get global settings store instance"""
    global _settings_store
    if _settings_store is None:
        _settings_store = AddnewposSettingsStore()
    return _settings_store
