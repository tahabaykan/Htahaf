"""
HEAVY Mode Settings Store - ACCOUNT-AWARE VERSION

Stores and retrieves HEAVY mode configuration per trading account.

ACCOUNT-SPECIFIC SETTINGS:
- HAMPRO has its own HEAVY mode settings
- IBKR_PED has its own HEAVY mode settings  
- IBKR_MAIN has its own HEAVY mode settings

SETTINGS (per account):
- heavy_long_dec: bool - Enable HEAVYLONGDEC aggressive reduction
- heavy_short_dec: bool - Enable HEAVYSHORTDEC aggressive reduction
- heavy_lot_pct: int - Lot percentage for reduction (1-100)
- heavy_long_threshold: float - Minimum pahalilik score for LONG reduction
- heavy_short_threshold: float - Maximum ucuzluk score for SHORT reduction

PERSISTENCE:
- Redis key: psfalgo:heavy_settings:{account_id}
- Settings are persisted to Redis and loaded on startup
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, Any
import json
from app.core.logger import logger


@dataclass
class HeavyModeSettings:
    """HEAVY mode settings for a single account"""
    heavy_long_dec: bool = False       # Enable HEAVYLONGDEC mode
    heavy_short_dec: bool = False      # Enable HEAVYSHORTDEC mode
    heavy_lot_pct: int = 30            # Lot percentage (1-100)
    heavy_long_threshold: float = 0.02 # Min pahalilik for LONG reduction
    heavy_short_threshold: float = -0.02  # Max ucuzluk for SHORT reduction


def _get_redis_key(account_id: str) -> str:
    """Get Redis key for account-specific HEAVY settings"""
    return f"psfalgo:heavy_settings:{account_id}"


def _default_accounts() -> list:
    """List of known trading accounts"""
    return ["HAMPRO", "IBKR_PED", "IBKR_MAIN"]


class HeavyModeSettingsStore:
    """
    Persistent storage for HEAVY mode settings - ACCOUNT-AWARE
    
    Each account has its own HEAVY settings stored in Redis.
    """
    
    def __init__(self):
        self._settings: Dict[str, HeavyModeSettings] = {}
        self._load_all()
    
    def _load_all(self):
        """Load settings for all known accounts from Redis"""
        for account_id in _default_accounts():
            self._load_account(account_id)
    
    def _load_account(self, account_id: str):
        """Load settings for a specific account from Redis"""
        try:
            from app.core.redis_client import get_redis
            
            redis = get_redis()
            if not redis:
                self._settings[account_id] = HeavyModeSettings()
                return
            
            key = _get_redis_key(account_id)
            raw = redis.get(key)
            
            if raw:
                data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                self._settings[account_id] = HeavyModeSettings(
                    heavy_long_dec=data.get('heavy_long_dec', False),
                    heavy_short_dec=data.get('heavy_short_dec', False),
                    heavy_lot_pct=int(data.get('heavy_lot_pct', 30)),
                    heavy_long_threshold=float(data.get('heavy_long_threshold', 0.02)),
                    heavy_short_threshold=float(data.get('heavy_short_threshold', -0.02))
                )
                logger.info(f"[HEAVY_SETTINGS] Loaded settings for {account_id}: {asdict(self._settings[account_id])}")
            else:
                self._settings[account_id] = HeavyModeSettings()
                logger.info(f"[HEAVY_SETTINGS] No saved settings for {account_id}, using defaults")
                
        except Exception as e:
            logger.warning(f"[HEAVY_SETTINGS] Failed to load settings for {account_id}: {e}")
            self._settings[account_id] = HeavyModeSettings()
    
    def _save_account(self, account_id: str):
        """Save settings for a specific account to Redis"""
        try:
            from app.core.redis_client import get_redis
            
            redis = get_redis()
            if not redis:
                logger.warning("[HEAVY_SETTINGS] Redis not available, cannot save")
                return
            
            settings = self._settings.get(account_id)
            if not settings:
                return
            
            key = _get_redis_key(account_id)
            data = asdict(settings)
            redis.set(key, json.dumps(data))
            logger.info(f"[HEAVY_SETTINGS] Saved settings for {account_id}: {data}")
            
        except Exception as e:
            logger.error(f"[HEAVY_SETTINGS] Failed to save settings for {account_id}: {e}")
    
    def get_settings(self, account_id: str) -> HeavyModeSettings:
        """Get settings for a specific account"""
        if account_id not in self._settings:
            self._load_account(account_id)
        return self._settings.get(account_id) or HeavyModeSettings()
    
    def get_settings_dict(self, account_id: str) -> Dict[str, Any]:
        """Get settings for a specific account as dict"""
        return asdict(self.get_settings(account_id))
    
    def update_settings(self, account_id: str, updates: Dict[str, Any]) -> HeavyModeSettings:
        """Update settings for a specific account"""
        settings = self.get_settings(account_id)
        
        # Apply updates
        if 'heavy_long_dec' in updates:
            settings.heavy_long_dec = bool(updates['heavy_long_dec'])
        if 'heavy_short_dec' in updates:
            settings.heavy_short_dec = bool(updates['heavy_short_dec'])
        if 'heavy_lot_pct' in updates:
            settings.heavy_lot_pct = max(1, min(100, int(updates['heavy_lot_pct'])))
        if 'heavy_long_threshold' in updates:
            settings.heavy_long_threshold = float(updates['heavy_long_threshold'])
        if 'heavy_short_threshold' in updates:
            settings.heavy_short_threshold = float(updates['heavy_short_threshold'])
        
        self._settings[account_id] = settings
        self._save_account(account_id)
        
        return settings
    
    def get_all_accounts_settings(self) -> Dict[str, Dict[str, Any]]:
        """Get settings for all accounts"""
        result = {}
        for account_id in _default_accounts():
            result[account_id] = self.get_settings_dict(account_id)
        return result


# Global instance
_heavy_settings_store: Optional[HeavyModeSettingsStore] = None


def get_heavy_settings_store() -> HeavyModeSettingsStore:
    """Get global HEAVY settings store instance"""
    global _heavy_settings_store
    if _heavy_settings_store is None:
        _heavy_settings_store = HeavyModeSettingsStore()
    return _heavy_settings_store
