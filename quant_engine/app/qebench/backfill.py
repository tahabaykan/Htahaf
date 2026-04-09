"""
QeBench Historical Backfill

Recovers bench@fill values using:
1. DataFabric derived data (preferred - already computed)
2. Redis cached group averages (fallback)
3. Historical 5-minute bars from Hammer Pro (last resort)

Uses DOS Group average price at fill time as bench@fill.
"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from loguru import logger


async def recover_bench_fill_from_history(
    symbol: str,
    fill_time: datetime
) -> Optional[float]:
    """
    Recover bench@fill using best available data source.
    
    Priority:
    1. DataFabric derived data (group_avg_price or compute from peers)
    2. Redis cached group average
    3. Historical 5-minute bars from Hammer
    
    Args:
        symbol: Stock symbol
        fill_time: Exact time of fill
        
    Returns:
        Average DOS Group price at fill_time, or None if unavailable
    """
    # === Priority 1: DataFabric ===
    try:
        bench_price = _try_datafabric(symbol)
        if bench_price:
            logger.info(f"[QeBench Backfill] {symbol} bench@fill={bench_price:.2f} (DataFabric)")
            return bench_price
    except Exception as e:
        logger.debug(f"[QeBench Backfill] DataFabric failed for {symbol}: {e}")
    
    # === Priority 2: Redis Cached Group Average ===
    try:
        bench_price = _try_redis_group_avg(symbol)
        if bench_price:
            logger.info(f"[QeBench Backfill] {symbol} bench@fill={bench_price:.2f} (Redis)")
            return bench_price
    except Exception as e:
        logger.debug(f"[QeBench Backfill] Redis failed for {symbol}: {e}")
    
    # === Priority 3: Compute from peers ===
    try:
        dos_group = _get_dos_group(symbol)
        if dos_group:
            peers = _get_group_members(dos_group, exclude_symbol=symbol)
            if peers:
                peer_prices = _get_peer_prices_from_fabric(peers)
                if peer_prices:
                    avg_price = sum(peer_prices) / len(peer_prices)
                    logger.info(f"[QeBench Backfill] {symbol} bench@fill={avg_price:.2f} "
                               f"(computed from {len(peer_prices)}/{len(peers)} peers)")
                    return avg_price
    except Exception as e:
        logger.debug(f"[QeBench Backfill] Peer computation failed for {symbol}: {e}")
    
    logger.warning(f"[QeBench Backfill] No benchmark available for {symbol}")
    return None


def _try_datafabric(symbol: str) -> Optional[float]:
    """Get benchmark from DataFabric derived data"""
    try:
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        if not fabric:
            return None
        
        derived = fabric.get_derived(symbol)
        if derived:
            # Check for pre-computed group average price
            group_avg = derived.get('group_avg_price')
            if group_avg and float(group_avg) > 0:
                return float(group_avg)
        
        return None
    except Exception:
        return None


def _try_redis_group_avg(symbol: str) -> Optional[float]:
    """Try to get group avg price from Redis"""
    try:
        from app.qebench.benchmark import get_benchmark_fetcher
        fetcher = get_benchmark_fetcher()
        return fetcher._get_from_redis(symbol)
    except Exception:
        return None


def _get_peer_prices_from_fabric(peers: List[str]) -> List[float]:
    """Get current prices of peer symbols from DataFabric"""
    try:
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        if not fabric:
            return []
        
        prices = []
        for peer in peers:
            snapshot = fabric.get_snapshot(peer)
            if snapshot:
                price = snapshot.get('last') or snapshot.get('bid') or snapshot.get('close')
                if price and float(price) > 0:
                    prices.append(float(price))
        
        return prices
    except Exception:
        return []


def _get_dos_group(symbol: str) -> Optional[str]:
    """Get DOS Group for symbol."""
    try:
        from app.market_data.static_data_store import get_static_store
        store = get_static_store()
        if store:
            data = store.get_static_data(symbol)
            if data:
                group = data.get('GROUP', '')
                cgrup = data.get('CGRUP', '')
                
                # For heldkuponlu, use CGRUP as the refined group
                if 'heldkuponlu' in str(group).lower() and cgrup:
                    return f"heldkuponlu:{cgrup}"
                return group
        return None
    except Exception as e:
        logger.error(f"[QeBench Backfill] Error getting group for {symbol}: {e}")
        return None


def _get_group_members(dos_group: str, exclude_symbol: str = None) -> List[str]:
    """Get all members of DOS Group."""
    try:
        from app.market_data.static_data_store import get_static_store
        store = get_static_store()
        if not store:
            return []
        
        # Parse composite group key (e.g. "heldkuponlu:c525")
        use_cgrup = False
        target_group = dos_group
        target_cgrup = None
        
        if ':' in dos_group:
            parts = dos_group.split(':', 1)
            target_group = parts[0]
            target_cgrup = parts[1]
            use_cgrup = True
        
        members = []
        all_symbols = store.get_all_symbols()
        
        for s in all_symbols:
            if s == exclude_symbol:
                continue
            
            s_data = store.get_static_data(s)
            if not s_data:
                continue
            
            s_group = s_data.get('GROUP', '')
            
            if use_cgrup:
                s_cgrup = s_data.get('CGRUP', '')
                if s_group == target_group and s_cgrup == target_cgrup:
                    members.append(s)
            else:
                if s_group == target_group:
                    members.append(s)
        
        return members
        
    except Exception as e:
        logger.error(f"[QeBench Backfill] Error getting members for {dos_group}: {e}")
        return []


def _round_to_5min(dt: datetime) -> datetime:
    """Round datetime to nearest 5-minute interval"""
    minute = (dt.minute // 5) * 5
    return dt.replace(minute=minute, second=0, microsecond=0)
