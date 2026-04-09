"""
RuntimeControls - Ephemeral Account-Scoped Toggles
==================================================

This module manages the "Runtime Controls" for the execution engines.
Unlike Strategy Rules (which define *how* to trade), these controls define 
*whether* to trade and *how aggressively* to behave in the moment.

Design Principles:
1.  **Ephemeral**: These settings are NOT persisted to disk (by default). They reset on restart.
2.  **Account-Scoped**: Controls are strictly isolated per account (HAMPRO vs IBKR_PED).
3.  **Command-Oriented**: Used for manual overrides, panic buttons, and day-specific tweaks.

Fields:
-   Enabled Flags (Global & Per-Engine)
-   Intensity Multipliers (e.g. 0.5x, 2.0x)
-   Overrides (Force Trim, Allow Veto)
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Any
from app.core.logger import logger

@dataclass
class AccountRuntimeControls:
    """Controls for a single account."""
    
    # --- Master Switch ---
    system_enabled: bool = True
    
    # --- Execution Mode ---
    # PREVIEW: Orders are logged but not sent to broker
    # LIVE: Orders are actually sent to broker
    execution_mode: str = "PREVIEW"
    
    # --- LT TRIM (Execution Engine) ---
    lt_trim_enabled: bool = True
    lt_trim_long_enabled: bool = True   # Enable selling longs
    lt_trim_short_enabled: bool = True  # Enable covering shorts
    
    # Intensity (0.0 - 2.0): Scales the trim size
    # 1.0 = Normal (20% rule)
    # 0.5 = Half size
    # 0.0 = Dry run (effectively)
    lt_trim_intensity: float = 1.0
    
    # --- KARBOTU (Signal Engine) ---
    karbotu_enabled: bool = True
    
    # Veto Power: If True, Karbotu can block LT Trim via eligibility signal.
    # Set to False to ignore Karbotu's opinion.
    allow_karbotu_veto: bool = True
    
    # --- REDUCEMORE (Risk Engine) ---
    reducemore_enabled: bool = True
    
    # Scale Power: If True, Reducemore can increase LT Trim size via multiplier.
    allow_reducemore_scale: bool = True
    
    # --- MM (Placeholder) ---
    mm_enabled: bool = False
    
    # --- HEAVY MODE (Aggressive Reduction) ---
    # When enabled, bypasses FBTOT/SFSTOT/GORT/Spread filters
    # Only uses pahalilik/ucuzluk score for decisions
    heavy_long_dec: bool = False   # HEAVYLONGDEC - Aggressively reduce LONG positions
    heavy_short_dec: bool = False  # HEAVYSHORTDEC - Aggressively reduce SHORT positions
    
    # HEAVY Mode Configurable Parameters (persisted to Redis)
    heavy_lot_pct: int = 30              # Lot percentage for HEAVY mode (default: 30%)
    heavy_long_threshold: float = 0.02   # Min pahalilik score for LONG reduction (default: 0.02)
    heavy_short_threshold: float = -0.02 # Max ucuzluk score for SHORT reduction (default: -0.02)
    
    # --- Emergency / Overrides ---
    # FORCE TRIM: If True, bypasses ALL vetoes/checks (except hard risk limits).
    # Use with CAUTION.
    force_trim: bool = False
    
    def update(self, **kwargs):
        """Update fields with validation."""
        for k, v in kwargs.items():
            if hasattr(self, k):
                # Simple type validation/casting could go here
                setattr(self, k, v)
                logger.info(f"[RuntimeControls] Updated {k} = {v}")
            else:
                logger.warning(f"[RuntimeControls] Unknown control field: {k}")


# Redis key for persisting HEAVY settings
HEAVY_SETTINGS_REDIS_KEY = "psfalgo:heavy_settings"


class RuntimeControlsManager:
    """Singleton manager for all account controls."""
    
    def __init__(self):
        self._controls: Dict[str, AccountRuntimeControls] = {}
        self._heavy_settings_loaded = False
    
    def _load_heavy_settings_from_redis(self) -> Dict[str, Any]:
        """Load persisted HEAVY settings from Redis."""
        try:
            from app.core.redis_client import get_redis
            import json
            
            redis = get_redis()
            if redis:
                raw = redis.get(HEAVY_SETTINGS_REDIS_KEY)
                if raw:
                    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    logger.info(f"[RuntimeControls] Loaded HEAVY settings from Redis: {data}")
                    return data
        except Exception as e:
            logger.warning(f"[RuntimeControls] Failed to load HEAVY settings from Redis: {e}")
        return {}
    
    def _save_heavy_settings_to_redis(self, settings: Dict[str, Any]):
        """Persist HEAVY settings to Redis."""
        try:
            from app.core.redis_client import get_redis
            import json
            
            redis = get_redis()
            if redis:
                redis.set(HEAVY_SETTINGS_REDIS_KEY, json.dumps(settings))
                logger.info(f"[RuntimeControls] Saved HEAVY settings to Redis: {settings}")
        except Exception as e:
            logger.warning(f"[RuntimeControls] Failed to save HEAVY settings to Redis: {e}")
    
    def get_controls(self, account_id: str) -> AccountRuntimeControls:
        """Get controls for an account (creates default if missing, loads persisted HEAVY settings)."""
        if account_id not in self._controls:
            ctrl = AccountRuntimeControls()
            
            # Load persisted HEAVY settings (once per session or if not loaded yet)
            if not self._heavy_settings_loaded:
                persisted = self._load_heavy_settings_from_redis()
                if persisted:
                    if 'heavy_lot_pct' in persisted:
                        ctrl.heavy_lot_pct = int(persisted['heavy_lot_pct'])
                    if 'heavy_long_threshold' in persisted:
                        ctrl.heavy_long_threshold = float(persisted['heavy_long_threshold'])
                    if 'heavy_short_threshold' in persisted:
                        ctrl.heavy_short_threshold = float(persisted['heavy_short_threshold'])
                self._heavy_settings_loaded = True
            
            self._controls[account_id] = ctrl
            logger.info(f"[RuntimeControls] Initialized controls for {account_id} (HEAVY: lot={ctrl.heavy_lot_pct}%, long_th={ctrl.heavy_long_threshold}, short_th={ctrl.heavy_short_threshold})")
        return self._controls[account_id]
    
    def update_controls(self, account_id: str, updates: Dict[str, Any]) -> AccountRuntimeControls:
        """Update controls for an account. Persists HEAVY settings to Redis."""
        ctrl = self.get_controls(account_id)
        ctrl.update(**updates)
        
        # Persist HEAVY settings if any were updated
        heavy_keys = ['heavy_lot_pct', 'heavy_long_threshold', 'heavy_short_threshold']
        if any(k in updates for k in heavy_keys):
            self._save_heavy_settings_to_redis({
                'heavy_lot_pct': ctrl.heavy_lot_pct,
                'heavy_long_threshold': ctrl.heavy_long_threshold,
                'heavy_short_threshold': ctrl.heavy_short_threshold
            })
        
        return ctrl
        
    def reset_controls(self, account_id: str):
        """Reset account to defaults."""
        self._controls[account_id] = AccountRuntimeControls()
        logger.info(f"[RuntimeControls] Reset controls for {account_id}")

# Global Instance
_runtime_controls_manager = RuntimeControlsManager()

def get_runtime_controls_manager() -> RuntimeControlsManager:
    return _runtime_controls_manager

