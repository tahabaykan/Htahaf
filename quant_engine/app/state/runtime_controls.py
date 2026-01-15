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


class RuntimeControlsManager:
    """Singleton manager for all account controls."""
    
    def __init__(self):
        self._controls: Dict[str, AccountRuntimeControls] = {}
    
    def get_controls(self, account_id: str) -> AccountRuntimeControls:
        """Get controls for an account (creates default if missing)."""
        if account_id not in self._controls:
            self._controls[account_id] = AccountRuntimeControls()
            logger.info(f"[RuntimeControls] Initialized default controls for {account_id}")
        return self._controls[account_id]
    
    def update_controls(self, account_id: str, updates: Dict[str, Any]) -> AccountRuntimeControls:
        """Update controls for an account."""
        ctrl = self.get_controls(account_id)
        ctrl.update(**updates)
        return ctrl
        
    def reset_controls(self, account_id: str):
        """Reset account to defaults."""
        self._controls[account_id] = AccountRuntimeControls()
        logger.info(f"[RuntimeControls] Reset controls for {account_id}")

# Global Instance
_runtime_controls_manager = RuntimeControlsManager()

def get_runtime_controls_manager() -> RuntimeControlsManager:
    return _runtime_controls_manager
