"""
SecurityRegistry - Central Registry for SecurityContext Objects

Single registry managing all SecurityContext instances.
Provides get_or_create pattern and snapshot generation.

Key Features:
- get_or_create(pref_ibkr) -> SecurityContext
- resolve_and_get(raw_symbol) -> SecurityContext (uses SymbolResolver)
- Snapshot generation for UI with filtering
- Cycle debug summary generation
"""

from typing import Dict, Optional, List, Set, Any
from datetime import datetime
from collections import Counter

from app.core.logger import logger
from app.core.security_context import SecurityContext, MissingReasonCode
from app.core.symbol_resolver import get_symbol_resolver


class SecurityRegistry:
    """
    Central registry for all SecurityContext objects.
    
    Each preferred stock (identified by PREF_IBKR) has exactly ONE
    SecurityContext in this registry.
    """
    
    def __init__(self):
        self._contexts: Dict[str, SecurityContext] = {}
        self._created_at = datetime.now()
    
    # =========================================================================
    # Core Access Methods
    # =========================================================================
    
    def get_or_create(self, pref_ibkr: str) -> Optional[SecurityContext]:
        """
        Get existing or create new SecurityContext for a PREF_IBKR symbol.
        
        Args:
            pref_ibkr: Canonical PREF_IBKR symbol
            
        Returns:
            SecurityContext or None if invalid symbol
        """
        if not pref_ibkr:
            return None
        
        normalized = pref_ibkr.strip().upper()
        
        if normalized not in self._contexts:
            self._contexts[normalized] = SecurityContext(pref_ibkr=normalized)
        
        return self._contexts[normalized]
    
    def get(self, pref_ibkr: str) -> Optional[SecurityContext]:
        """
        Get existing SecurityContext (without creating).
        
        Args:
            pref_ibkr: Canonical PREF_IBKR symbol
            
        Returns:
            SecurityContext or None if not exists
        """
        if not pref_ibkr:
            return None
        return self._contexts.get(pref_ibkr.strip().upper())
    
    def resolve_and_get(self, raw_symbol: str) -> Optional[SecurityContext]:
        """
        Resolve symbol through SymbolResolver and get/create context.
        
        Args:
            raw_symbol: Raw symbol from any source
            
        Returns:
            SecurityContext or None if symbol unknown
        """
        resolver = get_symbol_resolver()
        pref = resolver.resolve_to_pref(raw_symbol)
        
        if not pref:
            return None
        
        return self.get_or_create(pref)
    
    def exists(self, pref_ibkr: str) -> bool:
        """Check if a context exists for this symbol."""
        if not pref_ibkr:
            return False
        return pref_ibkr.strip().upper() in self._contexts
    
    # =========================================================================
    # Bulk Access
    # =========================================================================
    
    def get_all(self) -> Dict[str, SecurityContext]:
        """Get all contexts. Use with caution for large universes."""
        return self._contexts
    
    def get_symbols(self) -> Set[str]:
        """Get all registered PREF_IBKR symbols."""
        return set(self._contexts.keys())
    
    def get_count(self) -> int:
        """Get count of registered securities."""
        return len(self._contexts)
    
    def get_contexts_with_positions(self) -> List[SecurityContext]:
        """Get all contexts that have open positions."""
        return [
            ctx for ctx in self._contexts.values()
            if ctx.position.has_position()
        ]
    
    def get_contexts_by_group(self, group: str) -> List[SecurityContext]:
        """Get all contexts in a specific group."""
        return [
            ctx for ctx in self._contexts.values()
            if ctx.static.group == group
        ]
    
    # =========================================================================
    # Snapshot Generation
    # =========================================================================
    
    def get_snapshot(
        self,
        symbols: Optional[List[str]] = None,
        groups: Optional[List[str]] = None,
        only_with_positions: bool = False,
        only_tradeable: bool = False,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get lightweight snapshot for UI.
        
        Args:
            symbols: Filter to specific symbols
            groups: Filter to specific groups
            only_with_positions: Only include securities with positions
            only_tradeable: Only include tradeable securities
            limit: Maximum number of results
            
        Returns:
            List of snapshot dicts
        """
        result = []
        
        contexts = self._contexts.values()
        
        # Apply filters
        if symbols:
            symbol_set = {s.strip().upper() for s in symbols}
            contexts = [c for c in contexts if c.pref_ibkr in symbol_set]
        
        if groups:
            group_set = set(groups)
            contexts = [c for c in contexts if c.static.group in group_set]
        
        if only_with_positions:
            contexts = [c for c in contexts if c.position.has_position()]
        
        if only_tradeable:
            contexts = [c for c in contexts if c.is_tradeable()]
        
        # Convert to snapshot
        for ctx in contexts:
            result.append(ctx.to_snapshot())
            if limit and len(result) >= limit:
                break
        
        return result
    
    def get_full_snapshot(self, pref_ibkr: str) -> Optional[Dict[str, Any]]:
        """Get full context data for debugging."""
        ctx = self.get(pref_ibkr)
        if ctx:
            return ctx.to_dict(include_heavy=True)
        return None
    
    # =========================================================================
    # Observability / Debug
    # =========================================================================
    
    def get_cycle_debug_summary(self) -> Dict[str, Any]:
        """
        Generate cycle debug summary - THE key observability output.
        
        Returns dict with:
        - securities: total count
        - l1_fresh: count with fresh L1
        - unknown_symbol: count from resolver
        - benchmark_ok: from BenchmarkStore (caller should add)
        - eligible: count of tradeable
        - top_missing: most common missing reason
        """
        contexts = list(self._contexts.values())
        
        # Count L1 freshness
        l1_fresh_count = sum(1 for c in contexts if c.l1.is_valid() and c.l1.is_fresh())
        
        # Count tradeable
        eligible_count = sum(1 for c in contexts if c.is_tradeable(for_engine=True))
        
        # Count missing reasons
        reason_counter = Counter()
        for ctx in contexts:
            reason = ctx.get_missing_reason(for_engine=True)
            if reason != MissingReasonCode.OK:
                reason_counter[reason.value] += 1
        
        # Get resolver stats
        resolver = get_symbol_resolver()
        unknown_count = resolver.get_unknown_count()
        
        # Top missing reason
        top_missing = reason_counter.most_common(1)
        top_missing_str = f"{top_missing[0][0]}({top_missing[0][1]})" if top_missing else "NONE"
        
        return {
            "securities": len(contexts),
            "l1_fresh": l1_fresh_count,
            "unknown_symbol": unknown_count,
            "eligible": eligible_count,
            "top_missing": top_missing_str,
            "missing_breakdown": dict(reason_counter.most_common(5))
        }
    
    def log_cycle_summary(
        self,
        cycle_id: int,
        intents_count: int = 0,
        proposals_count: int = 0,
        benchmark_ok: bool = True
    ) -> None:
        """
        Log single-line cycle debug summary.
        
        This is THE log line that answers "why no proposals?".
        """
        summary = self.get_cycle_debug_summary()
        
        logger.info(
            f"[CYCLE {cycle_id}] "
            f"securities={summary['securities']} "
            f"l1_fresh={summary['l1_fresh']} "
            f"unknown={summary['unknown_symbol']} "
            f"benchmark={'OK' if benchmark_ok else 'MISSING'} "
            f"eligible={summary['eligible']} "
            f"intents={intents_count} "
            f"proposals={proposals_count} "
            f"top_missing={summary['top_missing']}"
        )
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get detailed health report for debugging."""
        contexts = list(self._contexts.values())
        
        l1_valid = sum(1 for c in contexts if c.l1.is_valid())
        l1_fresh = sum(1 for c in contexts if c.l1.is_valid() and c.l1.is_fresh())
        static_loaded = sum(1 for c in contexts if c.static.is_loaded())
        has_scores = sum(1 for c in contexts if c.scores.has_scores())
        has_positions = sum(1 for c in contexts if c.position.has_position())
        tradeable = sum(1 for c in contexts if c.is_tradeable())
        
        # Group breakdown
        groups = Counter(c.static.group for c in contexts if c.static.group)
        
        return {
            "total_securities": len(contexts),
            "l1_valid": l1_valid,
            "l1_fresh": l1_fresh,
            "static_loaded": static_loaded,
            "has_scores": has_scores,
            "has_positions": has_positions,
            "tradeable": tradeable,
            "groups": dict(groups.most_common(10)),
            "created_at": self._created_at.isoformat()
        }
    
    # =========================================================================
    # Cleanup
    # =========================================================================
    
    def clear(self) -> None:
        """Clear all contexts. Use with caution."""
        self._contexts.clear()
        logger.warning("[SECURITY_REGISTRY] All contexts cleared")


# =============================================================================
# Global Singleton
# =============================================================================

_security_registry: Optional[SecurityRegistry] = None


def get_security_registry() -> SecurityRegistry:
    """Get global SecurityRegistry instance."""
    global _security_registry
    if _security_registry is None:
        _security_registry = SecurityRegistry()
    return _security_registry


def initialize_security_registry() -> SecurityRegistry:
    """Initialize global SecurityRegistry instance."""
    global _security_registry
    _security_registry = SecurityRegistry()
    logger.info("[SECURITY_REGISTRY] Initialized")
    return _security_registry
