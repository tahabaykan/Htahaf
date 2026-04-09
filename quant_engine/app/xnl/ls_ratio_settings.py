"""
Long/Short Ratio Settings Store — Per-engine L/S allocation control.

Each increase engine (MM, PATADD, ADDNEWPOS) has independent L/S ratio.
Default: 50/50.  User can adjust e.g. 30L/70S → long lots × 0.6, short lots × 1.4.

Redis key: psfalgo:ls_ratio_settings
Persisted as JSON, survives restarts.
"""

import json
from typing import Dict, Any, Optional
from app.core.logger import logger

REDIS_KEY = 'psfalgo:ls_ratio_settings'

# Defaults: 50/50 for each engine
_DEFAULTS = {
    'MM_ENGINE': {'long_pct': 50, 'short_pct': 50},
    'PATADD_ENGINE': {'long_pct': 50, 'short_pct': 50},
    'ADDNEWPOS_ENGINE': {'long_pct': 50, 'short_pct': 50},
}


class LSRatioSettingsStore:
    """
    Persists L/S ratio per increase engine to Redis.
    Singleton.
    """
    _instance: Optional['LSRatioSettingsStore'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._cache: Dict[str, Dict[str, int]] = {}
        self._load()
        logger.info("[LS_RATIO] Store initialized")

    def _load(self):
        """Load from Redis, fallback to defaults."""
        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            if r:
                raw = r.get(REDIS_KEY)
                if raw:
                    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    self._cache = data
                    logger.info(f"[LS_RATIO] Loaded from Redis: {data}")
                    return
        except Exception as e:
            logger.warning(f"[LS_RATIO] Redis load failed: {e}")
        self._cache = {k: dict(v) for k, v in _DEFAULTS.items()}

    def _save(self):
        """Save to Redis."""
        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            if r:
                r.set(REDIS_KEY, json.dumps(self._cache))
        except Exception as e:
            logger.warning(f"[LS_RATIO] Redis save failed: {e}")

    def get_ratio(self, engine_name: str) -> Dict[str, int]:
        """Get L/S ratio for an engine. Returns {'long_pct': int, 'short_pct': int}."""
        defaults = _DEFAULTS.get(engine_name, {'long_pct': 50, 'short_pct': 50})
        return self._cache.get(engine_name, dict(defaults))

    def get_all(self) -> Dict[str, Dict[str, int]]:
        """Get all engine ratios."""
        result = {}
        for eng in _DEFAULTS:
            result[eng] = self.get_ratio(eng)
        return result

    def set_ratio(self, engine_name: str, long_pct: int) -> Dict[str, int]:
        """
        Set L/S ratio for an engine. short_pct = 100 - long_pct.
        long_pct clamped to [0, 100].
        """
        long_pct = max(0, min(100, int(long_pct)))
        short_pct = 100 - long_pct
        self._cache[engine_name] = {'long_pct': long_pct, 'short_pct': short_pct}
        self._save()
        logger.info(f"[LS_RATIO] {engine_name}: L={long_pct}% S={short_pct}%")
        return self._cache[engine_name]

    def get_lot_multiplier(self, engine_name: str, direction: str) -> float:
        """
        Get lot multiplier for a direction.
        50/50 → 1.0 for both.
        30/70 → LONG=0.6, SHORT=1.4
        0/100 → LONG=0.0, SHORT=2.0
        
        Formula: multiplier = pct / 50.0
        """
        ratio = self.get_ratio(engine_name)
        if direction.upper() in ('LONG', 'BUY', 'ADD'):
            return ratio['long_pct'] / 50.0
        else:  # SHORT, SELL, ADD_SHORT
            return ratio['short_pct'] / 50.0

    def apply_ratio_to_lot(self, engine_name: str, direction: str, base_lot: int,
                           min_lot: int = 200, round_to: int = 100) -> int:
        """
        Apply L/S ratio to a base lot amount.
        
        1. Multiply base_lot by the direction multiplier
        2. Round DOWN to nearest round_to (100)
        3. Enforce min_lot (200)
        4. If multiplier is 0 → return 0 (skip this side entirely)
        
        Returns: adjusted lot (int)
        """
        mult = self.get_lot_multiplier(engine_name, direction)
        
        # If ratio is 0% for this side, skip entirely
        if mult <= 0.001:
            return 0
        
        raw = base_lot * mult
        # Round DOWN to nearest round_to
        adjusted = int(raw // round_to) * round_to
        
        # Enforce minimum
        if adjusted < min_lot:
            adjusted = min_lot
        
        return adjusted


def get_ls_ratio_store() -> LSRatioSettingsStore:
    """Get the singleton LSRatioSettingsStore."""
    return LSRatioSettingsStore()
