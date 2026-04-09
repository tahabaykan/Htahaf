"""
QeBench Benchmark Price Module

Fetches DOS Group average prices for benchmark calculations.

v2: Uses DataFabric as primary source (already computed by JanallMetricsEngine),
    with Redis fallback for when DataFabric isn't available.
"""
from typing import Optional, Tuple
from loguru import logger


class BenchmarkPriceFetcher:
    """Fetches benchmark (DOS Group average) prices from DataFabric or Redis"""
    
    def __init__(self):
        self._redis_client = None
    
    def _get_redis(self):
        """Lazy Redis client initialization"""
        if self._redis_client is None:
            try:
                from app.config.settings import settings
                import redis
                self._redis_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    decode_responses=True
                )
            except Exception as e:
                logger.warning(f"[Benchmark] Redis init failed: {e}")
        return self._redis_client
    
    def get_current_benchmark_price(self, symbol: str) -> Optional[float]:
        """
        Get current benchmark price (DOS Group average) for a symbol.
        
        Priority:
        1. DataFabric derived data (fastest, already computed every 2s)
        2. Redis fallback (janall:metrics or bench:dos_group keys)
        
        Returns:
            Group average price, or None if unavailable
        """
        # === PRIORITY 1: DataFabric (best source) ===
        try:
            from app.core.data_fabric import get_data_fabric
            fabric = get_data_fabric()
            if fabric:
                derived = fabric.get_derived(symbol)
                if derived:
                    # bench_chg is the group avg daily change (cents)
                    # For QeBench we need "group avg price" not "group avg change"
                    # Check if group_avg_price is stored
                    group_avg_price = derived.get('group_avg_price')
                    if group_avg_price and float(group_avg_price) > 0:
                        return float(group_avg_price)
                    
                    # Fallback: compute from bench_source group stats
                    bench_source = derived.get('bench_source', '')
                    group_key = derived.get('group_key')
                    
                    if group_key:
                        # Try to get group stats from JanallMetricsEngine cache
                        price = self._get_group_avg_from_janall(group_key)
                        if price:
                            return price
        except Exception as e:
            logger.debug(f"[Benchmark] DataFabric lookup failed for {symbol}: {e}")
        
        # === PRIORITY 2: Redis fallback ===
        return self._get_from_redis(symbol)
    
    def get_benchmark_data(self, symbol: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """
        Get full benchmark data for a symbol.
        
        Returns:
            (bench_price, bench_chg, bench_source)
            - bench_price: DOS Group average price
            - bench_chg: DOS Group average daily change (cents)
            - bench_source: Source description (e.g., "Group: heldkuponlu:c525 (n=23)")
        """
        try:
            from app.core.data_fabric import get_data_fabric
            fabric = get_data_fabric()
            if fabric:
                derived = fabric.get_derived(symbol)
                if derived:
                    bench_chg = derived.get('bench_chg')
                    bench_source = derived.get('bench_source')
                    bench_price = self.get_current_benchmark_price(symbol)
                    
                    if bench_chg is not None:
                        bench_chg = float(bench_chg)
                    
                    return bench_price, bench_chg, bench_source
        except Exception as e:
            logger.debug(f"[Benchmark] Full data lookup failed for {symbol}: {e}")
        
        return None, None, None
    
    def _get_group_avg_from_janall(self, group_key: str) -> Optional[float]:
        """Get group average price from JanallMetricsEngine cache"""
        try:
            from app.market_data.janall_metrics_engine import get_janall_metrics_engine
            engine = get_janall_metrics_engine()
            if engine and engine.group_stats_cache:
                stats = engine.group_stats_cache.get(group_key)
                if stats:
                    avg_price = stats.get('group_avg_price')
                    if avg_price and float(avg_price) > 0:
                        return float(avg_price)
        except Exception as e:
            logger.debug(f"[Benchmark] JanallMetrics lookup failed for {group_key}: {e}")
        return None
    
    def _get_from_redis(self, symbol: str) -> Optional[float]:
        """Fallback: Get benchmark from Redis"""
        try:
            redis_client = self._get_redis()
            if not redis_client:
                return None
            
            # Try janall:metrics:{symbol} first
            import json
            metrics_json = redis_client.get(f"janall:metrics:{symbol}")
            if metrics_json:
                metrics = json.loads(metrics_json)
                group_key = metrics.get('group_key')
                
                if group_key:
                    # Try cached group average
                    redis_key = f"bench:dos_group:{group_key}:current_avg"
                    bench_price = redis_client.get(redis_key)
                    if bench_price:
                        return float(bench_price)
            
            return None
            
        except Exception as e:
            logger.debug(f"[Benchmark] Redis fallback failed for {symbol}: {e}")
            return None


# Singleton instance
_fetcher_instance = None

def get_benchmark_fetcher() -> BenchmarkPriceFetcher:
    """Get or create benchmark fetcher instance"""
    global _fetcher_instance
    if _fetcher_instance is None:
        _fetcher_instance = BenchmarkPriceFetcher()
    return _fetcher_instance
