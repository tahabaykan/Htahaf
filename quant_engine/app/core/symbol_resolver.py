"""
Symbol Resolver - Canonical Key Normalization

Normalizes all symbol formats to PREF_IBKR (e.g., "WFC PRZ").
This is the SINGLE source of truth for symbol resolution.

Key Features:
- Bi-directional mapping (raw_to_pref AND pref_to_raws)
- Alias dictionary for manual mappings
- Multiple source resolution (cache → alias → CSV → transform)
- Rate-limited unknown symbol logging
- NEVER crash on unknown symbols
"""

from typing import Optional, Dict, Set, List, Any
from datetime import datetime, timedelta
from collections import Counter
from app.core.logger import logger


class SymbolResolver:
    """
    Symbol Resolver - normalizes symbols to PREF_IBKR format.
    
    Resolution order:
    1. Cache (O(1))
    2. Alias dictionary (manual mappings)
    3. Known PREFs (direct match)
    4. Transformations (pattern matching)
    5. Unknown → log (rate-limited)
    """
    
    # Rate limit for unknown symbol logging
    UNKNOWN_LOG_INTERVAL = timedelta(minutes=5)
    
    def __init__(self):
        # Primary mapping: raw_symbol -> pref_ibkr
        self._raw_to_pref: Dict[str, str] = {}
        
        # Reverse mapping: pref_ibkr -> set of raw formats (for debug)
        self._pref_to_raws: Dict[str, Set[str]] = {}
        
        # Known PREF_IBKR symbols (universe)
        self._known_prefs: Set[str] = set()
        
        # Manual alias mappings (e.g., "AHL-E" -> "AHL PRE")
        self._alias_dict: Dict[str, str] = {}
        
        # Unknown symbol tracking (for observability)
        self._unknown_counter: Counter = Counter()
        self._unknown_last_logged: Dict[str, datetime] = {}
    
    # =========================================================================
    # Registration Methods
    # =========================================================================
    
    def register_pref(self, pref_ibkr: str) -> None:
        """
        Register a known PREF_IBKR symbol.
        Called during static data loading from CSV.
        """
        if not pref_ibkr:
            return
        
        normalized = pref_ibkr.strip().upper()
        self._known_prefs.add(normalized)
        self._raw_to_pref[normalized] = normalized
        
        # Initialize reverse mapping
        if normalized not in self._pref_to_raws:
            self._pref_to_raws[normalized] = set()
        self._pref_to_raws[normalized].add(normalized)
    
    def register_alias(self, alias: str, pref_ibkr: str) -> None:
        """
        Register an alias mapping.
        Use for manual mappings like "AHL-E" -> "AHL PRE".
        """
        if not alias or not pref_ibkr:
            return
        
        alias_norm = alias.strip().upper()
        pref_norm = pref_ibkr.strip().upper()
        
        self._alias_dict[alias_norm] = pref_norm
        self._raw_to_pref[alias_norm] = pref_norm
        
        # Update reverse mapping
        if pref_norm not in self._pref_to_raws:
            self._pref_to_raws[pref_norm] = set()
        self._pref_to_raws[pref_norm].add(alias_norm)
    
    def register_aliases_bulk(self, alias_map: Dict[str, str]) -> None:
        """
        Register multiple aliases at once.
        Format: {alias: pref_ibkr, ...}
        """
        for alias, pref in alias_map.items():
            self.register_alias(alias, pref)
    
    def register_from_csv_row(
        self,
        pref_ibkr: str,
        hammer_symbol: Optional[str] = None,
        ibkr_symbol: Optional[str] = None,
        display_symbol: Optional[str] = None
    ) -> None:
        """
        Register all symbol variants from a CSV row.
        
        Args:
            pref_ibkr: Canonical PREF_IBKR
            hammer_symbol: Hammer format (optional)
            ibkr_symbol: IBKR format (optional)
            display_symbol: Display format (optional)
        """
        if not pref_ibkr:
            return
        
        self.register_pref(pref_ibkr)
        
        if hammer_symbol:
            self.register_alias(hammer_symbol, pref_ibkr)
        if ibkr_symbol:
            self.register_alias(ibkr_symbol, pref_ibkr)
        if display_symbol:
            self.register_alias(display_symbol, pref_ibkr)
    
    # =========================================================================
    # Resolution Methods
    # =========================================================================
    
    def resolve_to_pref(self, raw_symbol: str) -> Optional[str]:
        """
        Resolve any symbol format to canonical PREF_IBKR.
        
        Resolution order:
        1. Cache lookup (O(1))
        2. Alias dictionary
        3. Known PREFs (direct match)
        4. Pattern transformations
        5. Unknown → track & return None
        
        NEVER throws exception. Returns None for unknown symbols.
        """
        if not raw_symbol:
            return None
        
        try:
            normalized = raw_symbol.strip().upper()
            
            # 1. Cache hit
            if normalized in self._raw_to_pref:
                return self._raw_to_pref[normalized]
            
            # 2. Alias dictionary
            if normalized in self._alias_dict:
                pref = self._alias_dict[normalized]
                self._cache_mapping(normalized, pref)
                return pref
            
            # 3. Already a known PREF
            if normalized in self._known_prefs:
                self._cache_mapping(normalized, normalized)
                return normalized
            
            # 4. Try transformations
            pref = self._try_transformations(normalized)
            if pref:
                self._cache_mapping(normalized, pref)
                return pref
            
            # 5. Unknown symbol
            self._track_unknown(normalized)
            return None
            
        except Exception as e:
            logger.error(f"[SYMBOL_RESOLVER] Error resolving '{raw_symbol}': {e}")
            return None
    
    def _cache_mapping(self, raw: str, pref: str) -> None:
        """Cache a resolved mapping."""
        self._raw_to_pref[raw] = pref
        if pref not in self._pref_to_raws:
            self._pref_to_raws[pref] = set()
        self._pref_to_raws[pref].add(raw)
    
    def _try_transformations(self, symbol: str) -> Optional[str]:
        """
        Try common symbol format transformations.
        
        Known patterns:
        - "WFC-Z" -> "WFC PRZ"
        - "WFC.PRZ" -> "WFC PRZ"
        - "WFCPRZ" -> "WFC PRZ"
        """
        # Pattern 1: WFC-Z -> WFC PRZ
        if '-' in symbol:
            parts = symbol.split('-')
            if len(parts) == 2 and len(parts[1]) == 1:
                candidate = f"{parts[0]} PR{parts[1]}"
                if candidate in self._known_prefs:
                    return candidate
        
        # Pattern 2: WFC.PRZ -> WFC PRZ
        if '.' in symbol:
            candidate = symbol.replace('.', ' ')
            if candidate in self._known_prefs:
                return candidate
        
        # Pattern 3: WFCPRZ (no space) -> WFC PRZ
        for known in self._known_prefs:
            if ' ' in known:
                no_space = known.replace(' ', '')
                if symbol == no_space:
                    return known
        
        return None
    
    def _track_unknown(self, symbol: str) -> None:
        """Track unknown symbol with rate-limited logging."""
        self._unknown_counter[symbol] += 1
        
        now = datetime.now()
        last_logged = self._unknown_last_logged.get(symbol)
        
        # Rate limit logging
        if last_logged is None or (now - last_logged) > self.UNKNOWN_LOG_INTERVAL:
            count = self._unknown_counter[symbol]
            logger.warning(f"[SYMBOL_RESOLVER] Unknown symbol: {symbol} (count={count})")
            self._unknown_last_logged[symbol] = now
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def is_valid_pref(self, symbol: str) -> bool:
        """Check if symbol is a valid known PREF_IBKR."""
        if not symbol:
            return False
        return symbol.strip().upper() in self._known_prefs
    
    def get_raw_formats(self, pref_ibkr: str) -> Set[str]:
        """Get all known raw formats for a PREF_IBKR (for debugging)."""
        if not pref_ibkr:
            return set()
        return self._pref_to_raws.get(pref_ibkr.strip().upper(), set())
    
    def get_known_count(self) -> int:
        """Get count of known PREF_IBKR symbols."""
        return len(self._known_prefs)
    
    def get_all_prefs(self) -> Set[str]:
        """Get all known PREF_IBKR symbols."""
        return self._known_prefs.copy()
    
    # =========================================================================
    # Observability
    # =========================================================================
    
    def get_unknown_stats(self) -> Dict[str, int]:
        """Get unknown symbol statistics for debugging."""
        return dict(self._unknown_counter.most_common(20))
    
    def get_unknown_count(self) -> int:
        """Get total count of unique unknown symbols."""
        return len(self._unknown_counter)
    
    def get_resolution_stats(self) -> Dict[str, Any]:
        """Get resolver statistics."""
        return {
            "known_prefs": len(self._known_prefs),
            "cached_mappings": len(self._raw_to_pref),
            "aliases": len(self._alias_dict),
            "unknown_unique": len(self._unknown_counter),
            "unknown_top": self._unknown_counter.most_common(5)
        }
    
    def clear_unknown_stats(self) -> None:
        """Clear unknown symbol tracking (for testing/new day)."""
        self._unknown_counter.clear()
        self._unknown_last_logged.clear()


# =============================================================================
# Global Singleton
# =============================================================================

_symbol_resolver: Optional[SymbolResolver] = None


def get_symbol_resolver() -> SymbolResolver:
    """Get global SymbolResolver instance."""
    global _symbol_resolver
    if _symbol_resolver is None:
        _symbol_resolver = SymbolResolver()
    return _symbol_resolver


def initialize_symbol_resolver() -> SymbolResolver:
    """Initialize global SymbolResolver instance."""
    global _symbol_resolver
    _symbol_resolver = SymbolResolver()
    logger.info("[SYMBOL_RESOLVER] Initialized")
    return _symbol_resolver
