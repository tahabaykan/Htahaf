"""
Position Tag Store — Manages POS TAG (MM/LT) per symbol PER ACCOUNT in Redis.

Dual Tag System v4:
- Every position has a POS TAG: MM (Market Making) or LT (Long Term)
- POS TAG is set when position is first opened:
  - MM engine fills → MM
  - PATADD/ADDNEWPOS fills → LT
- POS TAG persists until position is closed and reopened
- CRITICAL: Each account (HAMPRO, IBKR_PED) has SEPARATE POS TAGs

Storage: Redis key "psfalgo:pos_tags:{account_id}" → {symbol: "MM" or "LT"}
Fallback: Redis key "psfalgo:pos_tags" (legacy global, migration only)

Migration: All existing positions default to "MM".
"""

import json
from typing import Dict, Optional
from app.core.logger import logger


class PositionTagStore:
    """
    Manages POS TAG (MM/LT) per symbol, PER ACCOUNT.
    
    Redis key: psfalgo:pos_tags:{account_id} → {symbol: "MM" or "LT"}
    """
    
    REDIS_KEY_PREFIX = "psfalgo:pos_tags"
    VALID_TAGS = {"MM", "LT"}
    # Known account IDs
    KNOWN_ACCOUNTS = {"HAMPRO", "IBKR_PED"}
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        # Per-account caches: {account_id: {symbol: tag}}
        self._caches: Dict[str, Dict[str, str]] = {}
        self._load_all_from_redis()
    
    def _redis_key(self, account_id: str) -> str:
        """Redis key for a specific account."""
        return f"{self.REDIS_KEY_PREFIX}:{account_id}"
    
    def _load_all_from_redis(self):
        """Load pos_tags from Redis for all known accounts."""
        try:
            if not self.redis_client:
                return
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            
            # Load per-account keys
            for acct in self.KNOWN_ACCOUNTS:
                raw = redis_sync.get(self._redis_key(acct))
                if raw:
                    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    self._caches[acct] = {k: v for k, v in data.items() if v in self.VALID_TAGS}
                else:
                    self._caches[acct] = {}
            
            # Migration: if per-account keys are empty but legacy global key exists, migrate
            legacy_raw = redis_sync.get(self.REDIS_KEY_PREFIX)
            if legacy_raw:
                legacy_data = json.loads(legacy_raw.decode() if isinstance(legacy_raw, bytes) else legacy_raw)
                legacy_tags = {k: v for k, v in legacy_data.items() if v in self.VALID_TAGS}
                if legacy_tags:
                    migrated = False
                    for acct in self.KNOWN_ACCOUNTS:
                        if not self._caches.get(acct):
                            self._caches[acct] = dict(legacy_tags)
                            self._save_to_redis(acct)
                            migrated = True
                    if migrated:
                        logger.info(
                            f"[PositionTagStore] Migrated {len(legacy_tags)} legacy global tags "
                            f"to per-account keys"
                        )
            
            total = sum(len(c) for c in self._caches.values())
            logger.info(
                f"[PositionTagStore] Loaded {total} pos_tags "
                f"({', '.join(f'{k}={len(v)}' for k, v in self._caches.items())})"
            )
        except Exception as e:
            logger.debug(f"[PositionTagStore] Redis load error: {e}")
    
    def _save_to_redis(self, account_id: str):
        """Save pos_tags cache for a specific account to Redis."""
        try:
            if not self.redis_client:
                return
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            cache = self._caches.get(account_id, {})
            redis_sync.set(self._redis_key(account_id), json.dumps(cache))
        except Exception as e:
            logger.warning(f"[PositionTagStore] Redis save error for {account_id}: {e}")
    
    def _resolve_account(self, account_id: Optional[str] = None) -> str:
        """
        Resolve account_id, with fallback to active dual process account.
        """
        if account_id and account_id.upper() in self.KNOWN_ACCOUNTS:
            return account_id.upper()
        
        # Try to get active account from Redis (dual process state)
        try:
            if self.redis_client:
                redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
                # Priority 1: xnl running account (dual process runner writes this)
                active = redis_sync.get("psfalgo:xnl:running_account")
                if active:
                    active_str = active.decode() if isinstance(active, bytes) else active
                    if active_str in self.KNOWN_ACCOUNTS:
                        return active_str
                # Priority 2: trading account mode
                active = redis_sync.get("psfalgo:trading:account_mode")
                if active:
                    active_str = active.decode() if isinstance(active, bytes) else active
                    if active_str in self.KNOWN_ACCOUNTS:
                        return active_str
        except Exception:
            pass
        
        # Fallback: HAMPRO (primary account)
        return "HAMPRO"
    
    def get_tag(self, symbol: str, account_id: Optional[str] = None) -> str:
        """
        Get POS TAG for a symbol in a specific account.
        Returns 'MM' if not found (migration default).
        """
        acct = self._resolve_account(account_id)
        cache = self._caches.get(acct, {})
        return cache.get(symbol, "MM")
    
    def set_tag(self, symbol: str, tag: str, account_id: Optional[str] = None):
        """Set POS TAG for a symbol in a specific account. Only accepts 'MM' or 'LT'."""
        if tag not in self.VALID_TAGS:
            logger.warning(f"[PositionTagStore] Invalid tag '{tag}' for {symbol}, ignoring")
            return
        
        acct = self._resolve_account(account_id)
        if acct not in self._caches:
            self._caches[acct] = {}
        
        old_tag = self._caches[acct].get(symbol)
        if old_tag != tag:
            self._caches[acct][symbol] = tag
            self._save_to_redis(acct)
            logger.info(f"[PositionTagStore] {acct}/{symbol}: {old_tag or 'NEW'} → {tag}")
    
    def update_on_fill(self, symbol: str, engine_tag: str, account_id: Optional[str] = None):
        """
        Update POS TAG on fill based on ENGINE TAG.
        
        Only INC engines set POS TAG:
        - MM engine → POS TAG = MM
        - PA (PATADD) → POS TAG = LT
        - AN (ADDNEWPOS) → POS TAG = LT
        
        DEC engines (KB, TRIM) don't change POS TAG.
        """
        if engine_tag in ("PA", "AN"):
            self.set_tag(symbol, "LT", account_id)
        elif engine_tag == "MM":
            # Only set MM if not already LT (don't overwrite LT with MM)
            if self.get_tag(symbol, account_id) != "LT":
                self.set_tag(symbol, "MM", account_id)
    
    def remove_tag(self, symbol: str, account_id: Optional[str] = None):
        """Remove POS TAG when position is fully closed."""
        acct = self._resolve_account(account_id)
        cache = self._caches.get(acct, {})
        if symbol in cache:
            del cache[symbol]
            self._save_to_redis(acct)
            logger.info(f"[PositionTagStore] {acct}/{symbol}: REMOVED (position closed)")
    
    def get_all_tags(self, account_id: Optional[str] = None) -> Dict[str, str]:
        """Get all POS TAGs for a specific account."""
        acct = self._resolve_account(account_id)
        return dict(self._caches.get(acct, {}))
    
    def initialize_from_befday(self, positions: list, account_id: Optional[str] = None):
        """
        Initialize pos_tags from BEFDAY CSV data for a specific account.
        Migration: All positions get 'MM' unless already tagged.
        
        Args:
            positions: List of dicts with 'symbol' and optionally 'pos_tag' or 'book'
            account_id: Account to initialize for
        """
        acct = self._resolve_account(account_id)
        if acct not in self._caches:
            self._caches[acct] = {}
        
        count = 0
        for pos in positions:
            symbol = pos.get('symbol', pos.get('Symbol', ''))
            if not symbol:
                continue
            tag = pos.get('pos_tag', pos.get('book', 'MM'))
            if tag not in self.VALID_TAGS:
                tag = 'MM'
            if symbol not in self._caches[acct]:
                self._caches[acct][symbol] = tag
                count += 1
        
        if count > 0:
            self._save_to_redis(acct)
            logger.info(f"[PositionTagStore] Initialized {count} new pos_tags from BEFDAY for {acct}")


# Global instance
_store: Optional[PositionTagStore] = None


def get_position_tag_store() -> Optional[PositionTagStore]:
    """Get global PositionTagStore instance."""
    return _store


def initialize_position_tag_store(redis_client=None) -> PositionTagStore:
    """Initialize global PositionTagStore instance."""
    global _store
    if redis_client is None:
        try:
            from app.core.redis_client import get_redis_client
            redis_client = get_redis_client()
        except Exception:
            pass
    _store = PositionTagStore(redis_client)
    logger.info("[PositionTagStore] Initialized (per-account mode)")
    return _store
