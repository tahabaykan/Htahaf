"""
Port Adjuster Store

State management for Port Adjuster snapshots.
Supports save/load CSV with user-provided name; "last used CSV" is persisted
and loaded on app startup as default.
"""

from typing import Optional
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

LAST_CSV_JSON = "last_port_adjuster_csv.json"
CSV_DIR_NAME = "port_adjuster_csvs"


def _port_adjuster_config_dir() -> Path:
    """Directory for last-csv and csv saves (project_root/config or port_adjuster parent)."""
    # quant_engine/app/port_adjuster -> parents[2] = quant_engine
    base = Path(__file__).resolve().parents[2]
    return base / "config"


def _last_csv_path_file() -> Path:
    return _port_adjuster_config_dir() / LAST_CSV_JSON


def get_last_port_adjuster_csv_path() -> Optional[str]:
    """Return persisted 'last used CSV' path, or None."""
    try:
        p = _last_csv_path_file()
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("path") or None
    except Exception as e:
        logger.debug(f"[PORT_ADJUSTER_STORE] Read last CSV path: {e}")
    return None


def set_last_port_adjuster_csv_path(path: str) -> None:
    """Persist 'last used CSV' path."""
    try:
        _port_adjuster_config_dir().mkdir(parents=True, exist_ok=True)
        with open(_last_csv_path_file(), "w", encoding="utf-8") as f:
            json.dump({"path": path}, f, indent=0)
    except Exception as e:
        logger.warning(f"[PORT_ADJUSTER_STORE] Write last CSV path: {e}")


class PortAdjusterStore:
    """
    Port Adjuster Store - Manages Port Adjuster state.
    
    Responsibilities:
    - Store current snapshot
    - Store current config
    - Provide read-only access to downstream engines
    """
    
    def __init__(self):
        """Initialize Port Adjuster Store"""
        self.engine: PortAdjusterEngine = get_port_adjuster_engine()
        self.current_config: Optional[PortAdjusterConfig] = None
        self.current_snapshot: Optional[PortAdjusterSnapshot] = None
        self.last_saved_at: Optional[datetime] = None
        self.config_source: Optional[str] = None
        self.config_path_default = self._get_project_root() / "port_adjuster_config.json"
        self.preset_dir = self._get_project_root() / "reports" / "port_adjuster" / "presets"
        
        # Initialize with default config
        self._initialize_persisted()
        
        logger.info("[PORT_ADJUSTER_STORE] Store initialized")
    
    def _get_project_root(self) -> Path:
        # quant_engine/app/port_adjuster/... -> go up 3 levels to project root
        return Path(__file__).resolve().parents[3]
    
    def _initialize_persisted(self):
        """Initialize config: last-used CSV if exists, else exposureadjuster.csv, else JSON, else default."""
        try:
            project_root = self._get_project_root()
            
            # 0) Last-used CSV (saved path)
            last_path = get_last_port_adjuster_csv_path()
            if last_path and Path(last_path).exists():
                cfg = load_config_from_csv(last_path)
                if cfg:
                    self.last_saved_at = datetime.now()
                    self.config_source = f"csv:{Path(last_path).name}"
                    self._apply_config(cfg, persist=False)
                    logger.info(f"[PORT_ADJUSTER_STORE] Loaded from last CSV: {last_path}")
                    return
            
            # 1) exposureadjuster.csv in project root
            csv_path = project_root / "exposureadjuster.csv"
            if csv_path.exists():
                cfg = load_config_from_csv(str(csv_path))
                if cfg:
                    self.last_saved_at = datetime.now()
                    self.config_source = f"csv:{csv_path.name}"
                    self._apply_config(cfg, persist=False)
                    set_last_port_adjuster_csv_path(str(csv_path.resolve()))
                    logger.info(f"[PORT_ADJUSTER_STORE] Loaded config from CSV: {csv_path}")
                    return
            
            # 2) port_adjuster_config.json
            if self.config_path_default.exists():
                cfg = self._load_from_json(self.config_path_default)
                if cfg:
                    self.last_saved_at = datetime.now()
                    self.config_source = f"json:{self.config_path_default.name}"
                    self._apply_config(cfg, persist=False)
                    logger.info(f"[PORT_ADJUSTER_STORE] Loaded config from JSON: {self.config_path_default}")
                    return
            
            # 3) default config
            default_config = PortAdjusterConfig()
            self.last_saved_at = datetime.now()
            self.config_source = "default"
            self._apply_config(default_config, persist=False)
            logger.info("[PORT_ADJUSTER_STORE] Default configuration applied")
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER_STORE] Error initializing config: {e}", exc_info=True)
    
    def update_config(self, config: PortAdjusterConfig) -> PortAdjusterSnapshot:
        """
        Update configuration and recalculate snapshot.
        
        Args:
            config: New Port Adjuster configuration
            
        Returns:
            New PortAdjusterSnapshot
        """
        try:
            self.last_saved_at = datetime.now()
            self.config_source = self.config_source or "manual"
            self._apply_config(config, persist=True)
            
            logger.info(
                f"[PORT_ADJUSTER_STORE] Config updated: "
                f"exposure=${config.total_exposure_usd:,.0f}, "
                f"long={config.long_ratio_pct}%, short={config.short_ratio_pct}%"
            )
            
            return self.current_snapshot
            
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER_STORE] Error updating config: {e}", exc_info=True)
            raise
    
    def _apply_config(self, config: PortAdjusterConfig, persist: bool = False) -> None:
        """Apply config, recalc snapshot, optionally persist."""
        self.current_config = config
        snapshot = self.engine.calculate_snapshot(config)
        snapshot.last_saved_at = self.last_saved_at
        snapshot.config_source = self.config_source
        self.current_snapshot = snapshot
        
        if persist:
            self._persist_to_json(config)
    
    def _persist_to_json(self, config: PortAdjusterConfig) -> None:
        """Persist config to default JSON path."""
        try:
            self.config_path_default.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path_default, "w", encoding="utf-8") as f:
                json.dump(config.dict(), f, indent=2)
            logger.info(f"[PORT_ADJUSTER_STORE] Config persisted to {self.config_path_default}")
        except Exception as e:
            logger.warning(f"[PORT_ADJUSTER_STORE] Failed to persist config: {e}")
    
    def _load_from_json(self, path: Path) -> Optional[PortAdjusterConfig]:
        """Load config from JSON file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PortAdjusterConfig(**data)
        except Exception as e:
            logger.warning(f"[PORT_ADJUSTER_STORE] Failed to load JSON config {path}: {e}")
            return None
    
    def recalculate(self) -> Optional[PortAdjusterSnapshot]:
        """
        Recalculate snapshot from current config.
        
        Returns:
            Updated PortAdjusterSnapshot, or None if no config exists
        """
        try:
            if self.current_config is None:
                logger.warning("[PORT_ADJUSTER_STORE] No config available for recalculation")
                return None
            
            snapshot = self.engine.calculate_snapshot(self.current_config)
            snapshot.last_saved_at = self.last_saved_at
            snapshot.config_source = self.config_source
            self.current_snapshot = snapshot
            
            logger.info("[PORT_ADJUSTER_STORE] Snapshot recalculated")
            return self.current_snapshot
            
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER_STORE] Error recalculating: {e}", exc_info=True)
            return None
    
    def get_snapshot(self) -> Optional[PortAdjusterSnapshot]:
        """
        Get current snapshot (read-only).
        
        Returns:
            Current PortAdjusterSnapshot, or None if not initialized
        """
        return self.current_snapshot
    
    def get_config(self) -> Optional[PortAdjusterConfig]:
        """
        Get current configuration (read-only).
        
        Returns:
            Current PortAdjusterConfig, or None if not initialized
        """
        return self.current_config
    
    def get_group_max_lot(self, group: str, side: str = "LONG") -> Optional[float]:
        """
        Get maximum lot for a group (convenience method).
        
        Args:
            group: Group name
            side: 'LONG' or 'SHORT'
            
        Returns:
            Maximum lot, or None if not found
        """
        if self.current_snapshot is None:
            return None
        
        return self.engine.get_group_max_lot(self.current_snapshot, group, side)
    
    def get_group_max_value_usd(self, group: str, side: str = "LONG") -> Optional[float]:
        """
        Get maximum value (USD) for a group (convenience method).
        
        Args:
            group: Group name
            side: 'LONG' or 'SHORT'
            
        Returns:
            Maximum value in USD, or None if not found
        """
        if self.current_snapshot is None:
            return None
        
        return self.engine.get_group_max_value_usd(self.current_snapshot, group, side)
    
    # CSV save/load with name; last-used as default ---------------------------------
    def save_to_named_csv(self, filename: str) -> Optional[str]:
        """Save current config to a named CSV under project_root/port_adjuster_csvs/; set as last-used. Returns path or None."""
        cfg = self.get_config()
        if not cfg:
            return None
        base = self._get_project_root()
        csv_dir = base / CSV_DIR_NAME
        csv_dir.mkdir(parents=True, exist_ok=True)
        name = (filename or "exposureadjuster").strip().replace("..", "").replace("/", "").replace("\\", "")
        if not name:
            name = "exposureadjuster"
        if not name.endswith(".csv"):
            name += ".csv"
        path = str(csv_dir / name)
        if not save_config_to_csv(cfg, path):
            return None
        set_last_port_adjuster_csv_path(path)
        logger.info(f"[PORT_ADJUSTER_STORE] Saved to named CSV: {path}")
        return path
    
    def load_from_last_csv(self) -> Optional[PortAdjusterSnapshot]:
        """Load config from last-used CSV path; return new snapshot or None."""
        path = get_last_port_adjuster_csv_path()
        if not path or not Path(path).exists():
            return None
        cfg = load_config_from_csv(path)
        if not cfg:
            return None
        self.last_saved_at = datetime.now()
        self.config_source = f"csv:{Path(path).name}"
        self._apply_config(cfg, persist=False)
        return self.current_snapshot
    
    # Preset management -------------------------------------------------
    def save_preset(self, name: str, config: PortAdjusterConfig) -> bool:
        try:
            self.preset_dir.mkdir(parents=True, exist_ok=True)
            path = self.preset_dir / f"{name}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config.dict(), f, indent=2)
            logger.info(f"[PORT_ADJUSTER_STORE] Preset saved: {path}")
            return True
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER_STORE] Failed to save preset {name}: {e}", exc_info=True)
            return False
    
    def list_presets(self) -> list:
        try:
            # Create preset directory if it doesn't exist
            if not self.preset_dir.exists():
                self.preset_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"[PORT_ADJUSTER_STORE] Created preset directory: {self.preset_dir}")
                return []
            presets = [p.stem for p in self.preset_dir.glob("*.json")]
            if presets:
                logger.debug(f"[PORT_ADJUSTER_STORE] Found {len(presets)} presets: {presets}")
            return presets
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER_STORE] Failed to list presets: {e}", exc_info=True)
            return []
    
    def load_preset(self, name: str) -> Optional[PortAdjusterSnapshot]:
        try:
            # Ensure preset directory exists
            self.preset_dir.mkdir(parents=True, exist_ok=True)
            
            path = self.preset_dir / f"{name}.json"
            if not path.exists():
                logger.warning(f"[PORT_ADJUSTER_STORE] Preset not found: {name} (path: {path})")
                return None
            cfg = self._load_from_json(path)
            if not cfg:
                return None
            self.last_saved_at = datetime.now()
            self.config_source = f"preset:{name}"
            self._apply_config(cfg, persist=False)
            return self.current_snapshot
        except Exception as e:
            logger.error(f"[PORT_ADJUSTER_STORE] Failed to load preset {name}: {e}", exc_info=True)
            return None


# Singleton instance
_port_adjuster_store: Optional[PortAdjusterStore] = None


def get_port_adjuster_store() -> PortAdjusterStore:
    """Get singleton Port Adjuster Store instance"""
    global _port_adjuster_store
    if _port_adjuster_store is None:
        _port_adjuster_store = PortAdjusterStore()
    return _port_adjuster_store

