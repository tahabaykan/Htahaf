"""
PATADD Settings Store — Persistent configuration for the PATADD engine.

Stored per-account in Redis so that HAMPRO / IBKR accounts can have
independent PATADD parameters (same pattern as mm_settings / heavy_settings).
"""

from typing import Dict, Any, Optional
from datetime import datetime

from app.core.logger import logger


# Default settings — ADDNEWPOS-compatible values
_DEFAULTS: Dict[str, Any] = {
    'enabled': True,

    # Filters
    'fbtot_gt': 1.10,              # LONG: Fbtot > 1.10 = grupta ucuz = iyi long
    'sfstot_lt': 1.50,             # SHORT: SFStot < 1.50 = grupta pahalı = iyi short
    'bid_buy_ucuzluk_lt': 0.05,    # PATADD toleranslı: +5¢'e kadar kabul (ADDNEWPOS=-0.06)
    'ask_sell_pahalilik_gt': -0.05, # PATADD toleranslı: -5¢'e kadar kabul (ADDNEWPOS=+0.06)

    # LPAT/SPAT composite score thresholds
    'lpat_threshold': 45.0,        # LONG: LPAT = PatternScore × Fbtot >= 45
    'spat_threshold': 30.0,        # SHORT: SPAT = PatternScore / SFStot >= 30

    # Time filter
    'min_holding_days': 3,         # Pattern exit must be at least 3 days away

    # Lot sizing
    'max_lot_per_symbol': 2000,    # Max lot per symbol (like ADDNEWPOS)
    'min_lot': 200,                # Minimum lot (200 = rounding base)

    # Order limits
    'max_orders_per_side': 20,     # Max 20 LONG + 20 SHORT orders per cycle
}



class PataddSettingsStore:
    """
    Singleton settings store — mirrors the HeavySettingsStore pattern.
    Persists settings to Redis under  psfalgo:patadd_settings:{account_id}
    """

    _instance: Optional['PataddSettingsStore'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache: Dict[str, Dict[str, Any]] = {}
            logger.info("[PATADD_SETTINGS] Store initialized")
        return cls._instance

    # ── read ──────────────────────────────────────────────────────

    def get_settings(self, account_id: str = "HAMPRO") -> Dict[str, Any]:
        """Return merged (defaults + persisted) settings for *account_id*."""
        # Try cache first
        if account_id in self._cache:
            return {**_DEFAULTS, **self._cache[account_id]}

        # Try Redis
        persisted = self._load_from_redis(account_id)
        if persisted:
            self._cache[account_id] = persisted
            return {**_DEFAULTS, **persisted}

        return dict(_DEFAULTS)

    # ── write ─────────────────────────────────────────────────────

    def update_settings(
        self,
        account_id: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge *updates* into persisted settings and return the new merged view.
        Only keys present in _DEFAULTS are accepted.
        """
        current = self._cache.get(account_id, {})
        for key, value in updates.items():
            if key in _DEFAULTS:
                current[key] = value
            else:
                logger.warning(f"[PATADD_SETTINGS] Unknown key ignored: {key}")

        self._cache[account_id] = current
        self._save_to_redis(account_id, current)

        merged = {**_DEFAULTS, **current}
        logger.info(f"[PATADD_SETTINGS] Updated {account_id}: {merged}")
        return merged

    # ── Redis persistence ─────────────────────────────────────────

    def _redis_key(self, account_id: str) -> str:
        return f"psfalgo:patadd_settings:{account_id}"

    def _load_from_redis(self, account_id: str) -> Optional[Dict[str, Any]]:
        try:
            import json
            from app.core.redis_client import get_redis_client
            r = get_redis_client()
            if r is None:
                return None
            raw = r.get(self._redis_key(account_id))
            if raw:
                return json.loads(raw)
        except Exception as exc:
            logger.debug(f"[PATADD_SETTINGS] Redis load failed: {exc}")
        return None

    def _save_to_redis(self, account_id: str, data: Dict[str, Any]):
        try:
            import json
            from app.core.redis_client import get_redis_client
            r = get_redis_client()
            if r is None:
                return
            r.set(self._redis_key(account_id), json.dumps(data))
        except Exception as exc:
            logger.debug(f"[PATADD_SETTINGS] Redis save failed: {exc}")


# ── global accessor ──────────────────────────────────────────────

def get_patadd_settings_store() -> PataddSettingsStore:
    """Get the singleton PataddSettingsStore."""
    return PataddSettingsStore()
