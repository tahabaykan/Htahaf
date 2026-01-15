"""
QeBench Historical Backfill

Recovers bench@fill values using historical 5-minute bars
when real-time benchmark data is unavailable.

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
    Recover bench@fill using historical 5-minute bars.
    
    Process:
    1. Get DOS Group for symbol
    2. For each peer in group, fetch 5min bar at fill_time
    3. Calculate average peer close price = bench@fill
    
    Args:
        symbol: Stock symbol
        fill_time: Exact time of fill
        
    Returns:
        Average DOS Group price at fill_time, or None if unavailable
    """
    try:
        # Get DOS Group for symbol
        dos_group = _get_dos_group(symbol)
        if not dos_group:
            logger.warning(f"[QeBench Backfill] No DOS Group for {symbol}")
            return None
        
        # Get group members (peers)
        peers = _get_group_members(dos_group, exclude_symbol=symbol)
        if not peers:
            logger.warning(f"[QeBench Backfill] No peers in group {dos_group}")
            return None
        
        logger.info(f"[QeBench Backfill] {symbol} → Group: {dos_group}, Peers: {len(peers)}")
        
        # Fetch 5min bars for all peers at fill_time
        peer_prices = []
        for peer in peers:
            bar_price = await _fetch_5min_bar_price(peer, fill_time)
            if bar_price is not None:
                peer_prices.append(bar_price)
        
        # Calculate average
        if peer_prices:
            avg_price = sum(peer_prices) / len(peer_prices)
            logger.info(f"[QeBench Backfill] {symbol} bench@fill={avg_price:.2f} "
                       f"(avg of {len(peer_prices)}/{len(peers)} peers)")
            return avg_price
        else:
            logger.warning(f"[QeBench Backfill] No peer prices available for {symbol}")
            return None
            
    except Exception as e:
        logger.error(f"[QeBench Backfill] Error for {symbol}: {e}")
        return None


def _get_dos_group(symbol: str) -> Optional[str]:
    """
    Get DOS Group for symbol.
    
    Uses existing grouping system.
    """
    try:
        from app.market_data.grouping import resolve_primary_group
        
        group = resolve_primary_group(symbol)
        return group
        
    except Exception as e:
        logger.error(f"[QeBench Backfill] Error getting group for {symbol}: {e}")
        return None


def _get_group_members(dos_group: str, exclude_symbol: str = None) -> List[str]:
    """
    Get all members of DOS Group.
    
    Returns list of peer symbols in the same group.
    """
    try:
        from app.market_data.grouping import get_group_members
        
        members = get_group_members(dos_group)
        
        # Exclude the symbol itself
        if exclude_symbol and exclude_symbol in members:
            members.remove(exclude_symbol)
        
        return members
        
    except Exception as e:
        logger.error(f"[QeBench Backfill] Error getting members for {dos_group}: {e}")
        return []


async def _fetch_5min_bar_price(symbol: str, timestamp: datetime) -> Optional[float]:
    """
    Fetch 5-minute bar close price at specific timestamp.
    
    Uses Hammer Pro historical data API.
    
    Args:
        symbol: Stock symbol
        timestamp: Target timestamp
        
    Returns:
        Close price from 5min bar, or None if unavailable
    """
    try:
        # Try Redis cache first (if GRPAN data available)
        cached_price = _try_redis_cache(symbol, timestamp)
        if cached_price is not None:
            return cached_price
        
        # Fallback: Hammer Pro historical bars
        return await _fetch_from_hammer(symbol, timestamp)
        
    except Exception as e:
        logger.error(f"[QeBench Backfill] Error fetching bar for {symbol}: {e}")
        return None


def _try_redis_cache(symbol: str, timestamp: datetime) -> Optional[float]:
    """
    Try to get price from Redis (GRPAN data).
    
    GRPAN stores 5-minute bars in Redis.
    """
    try:
        from app.core.redis_client import get_sync_redis_client
        
        redis_client = get_sync_redis_client()
        
        # Round timestamp to 5-minute interval
        rounded_time = _round_to_5min(timestamp)
        
        # Key format: grpan:5min:{symbol}:{timestamp}
        key = f"grpan:5min:{symbol}:{int(rounded_time.timestamp())}"
        
        data = redis_client.get(key)
        if data:
            import json
            bar = json.loads(data)
            return bar.get('close')
        
        return None
        
    except Exception as e:
        logger.debug(f"[QeBench Backfill] Redis cache miss for {symbol}: {e}")
        return None


async def _fetch_from_hammer(symbol: str, timestamp: datetime) -> Optional[float]:
    """
    Fetch historical 5-minute bar from Hammer Pro.
    
    Uses Hammer's historical data API.
    """
    try:
        from app.live.hammer_client import get_hammer_client
        
        hammer_client = get_hammer_client()
        if not hammer_client or not hammer_client.is_connected():
            logger.warning("[QeBench Backfill] Hammer not connected")
            return None
        
        # Round to 5min interval
        rounded_time = _round_to_5min(timestamp)
        
        # Request historical bar
        # Note: Hammer API format TBD - adjust based on actual API
        # This is placeholder for now
        logger.warning(f"[QeBench Backfill] Hammer historical API not yet implemented for {symbol}")
        return None
        
    except Exception as e:
        logger.error(f"[QeBench Backfill] Hammer fetch error for {symbol}: {e}")
        return None


def _round_to_5min(dt: datetime) -> datetime:
    """Round datetime to nearest 5-minute interval"""
    minute = (dt.minute // 5) * 5
    return dt.replace(minute=minute, second=0, microsecond=0)
