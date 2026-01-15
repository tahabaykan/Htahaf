"""
Security API Routes - SecurityContext Architecture Endpoints

Provides REST API access to SecurityRegistry and BenchmarkStore.
UI should use these endpoints instead of directly accessing DataFabric.
"""

from fastapi import APIRouter, Query
from typing import List, Optional, Dict, Any

from app.core.logger import logger

router = APIRouter(prefix="/api/securities", tags=["securities"])


@router.get("/snapshot")
async def get_securities_snapshot(
    symbols: Optional[str] = Query(None, description="Comma-separated symbols to filter"),
    groups: Optional[str] = Query(None, description="Comma-separated groups to filter"),
    only_positions: bool = Query(False, description="Only include securities with positions"),
    only_tradeable: bool = Query(False, description="Only include tradeable securities"),
    limit: int = Query(500, description="Maximum number of results")
) -> Dict[str, Any]:
    """
    Get lightweight snapshot of securities for UI grid.
    
    This is the primary endpoint for UI to display security data.
    Returns shallow data optimized for rendering.
    """
    try:
        from app.core.security_registry import get_security_registry
        
        registry = get_security_registry()
        if not registry:
            return {"securities": [], "error": "Registry not initialized"}
        
        # Parse filters
        symbol_list = [s.strip() for s in symbols.split(",")] if symbols else None
        group_list = [g.strip() for g in groups.split(",")] if groups else None
        
        # Get snapshot
        snapshot = registry.get_snapshot(
            symbols=symbol_list,
            groups=group_list,
            only_with_positions=only_positions,
            only_tradeable=only_tradeable,
            limit=limit
        )
        
        # Get summary stats
        summary = registry.get_cycle_debug_summary()
        
        return {
            "securities": snapshot,
            "count": len(snapshot),
            "total_registered": registry.get_count(),
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error getting securities snapshot: {e}", exc_info=True)
        return {"securities": [], "error": str(e)}


@router.get("/detail/{pref_ibkr}")
async def get_security_detail(pref_ibkr: str) -> Dict[str, Any]:
    """
    Get full SecurityContext data for a specific symbol.
    
    This is the debug endpoint - includes all data including heavy fields.
    """
    try:
        from app.core.security_registry import get_security_registry
        
        registry = get_security_registry()
        if not registry:
            return {"error": "Registry not initialized"}
        
        ctx = registry.get(pref_ibkr)
        if not ctx:
            return {"error": f"Symbol not found: {pref_ibkr}"}
        
        return ctx.to_dict(include_heavy=True)
        
    except Exception as e:
        logger.error(f"Error getting security detail: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/health")
async def get_registry_health() -> Dict[str, Any]:
    """
    Get health report of the SecurityRegistry.
    
    Useful for monitoring and debugging data flow.
    """
    try:
        from app.core.security_registry import get_security_registry
        from app.core.symbol_resolver import get_symbol_resolver
        
        registry = get_security_registry()
        resolver = get_symbol_resolver()
        
        health = {}
        
        if registry:
            health["registry"] = registry.get_health_report()
        else:
            health["registry"] = {"error": "Not initialized"}
        
        if resolver:
            health["resolver"] = resolver.get_resolution_stats()
        else:
            health["resolver"] = {"error": "Not initialized"}
        
        return health
        
    except Exception as e:
        logger.error(f"Error getting registry health: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/benchmarks")
async def get_benchmarks() -> Dict[str, Any]:
    """
    Get ETF benchmark data from BenchmarkStore.
    """
    try:
        from app.core.benchmark_store import get_benchmark_store
        
        store = get_benchmark_store()
        if not store:
            return {"error": "BenchmarkStore not initialized"}
        
        return store.to_dict()
        
    except Exception as e:
        logger.error(f"Error getting benchmarks: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/positions")
async def get_securities_with_positions() -> Dict[str, Any]:
    """
    Get all securities that have open positions.
    """
    try:
        from app.core.security_registry import get_security_registry
        
        registry = get_security_registry()
        if not registry:
            return {"securities": [], "error": "Registry not initialized"}
        
        contexts = registry.get_contexts_with_positions()
        
        return {
            "securities": [ctx.to_snapshot() for ctx in contexts],
            "count": len(contexts)
        }
        
    except Exception as e:
        logger.error(f"Error getting positions: {e}", exc_info=True)
        return {"securities": [], "error": str(e)}


@router.get("/unknown-symbols")
async def get_unknown_symbols() -> Dict[str, Any]:
    """
    Get list of unknown symbols encountered by the resolver.
    
    Useful for debugging symbol mapping issues.
    """
    try:
        from app.core.symbol_resolver import get_symbol_resolver
        
        resolver = get_symbol_resolver()
        if not resolver:
            return {"error": "Resolver not initialized"}
        
        return {
            "unknown_symbols": resolver.get_unknown_stats(),
            "unknown_count": resolver.get_unknown_count(),
            "known_count": resolver.get_known_count()
        }
        
    except Exception as e:
        logger.error(f"Error getting unknown symbols: {e}", exc_info=True)
        return {"error": str(e)}
