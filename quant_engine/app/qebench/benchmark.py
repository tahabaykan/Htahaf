"""
QeBench Benchmark Price Module

Fetches DOS Group average prices for benchmark calculations.
"""
from typing import Optional
from loguru import logger
import redis
from app.config.settings import settings


class BenchmarkPriceFetcher:
    """Fetches benchmark (DOS Group average) prices"""
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            decode_responses=True
        )
    
    def get_current_benchmark_price(self, symbol: str) -> Optional[float]:
        """
        Get current benchmark price for a symbol.
        
        Uses DOS Group average from market_context_worker.
        For heldkuponlu stocks, uses CGRUP-specific average.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Benchmark average price or None
        """
        try:
            # Get symbol DOS Group and CGRUP
            dos_group = self._get_dos_group(symbol)
            cgrup = self._get_cgrup(symbol)
            
            # Build Redis key
            if cgrup and dos_group == 'heldkuponlu':
                redis_key = f"bench:dos_group:heldkuponlu:{cgrup}:current_avg"
            else:
                redis_key = f"bench:dos_group:{dos_group}:current_avg"
            
            # Fetch from Redis
            bench_price = self.redis_client.get(redis_key)
            
            if bench_price:
                return float(bench_price)
            
            # Fallback: calculate from individual prices
            logger.warning(f"[Benchmark] No cached bench for {symbol}, calculating from group")
            return self._calculate_group_average(dos_group, cgrup)
            
        except Exception as e:
            logger.error(f"[Benchmark] Error fetching for {symbol}: {e}")
            return None
    
    def _get_dos_group(self, symbol: str) -> Optional[str]:
        """Get DOS Group for symbol from static data"""
        try:
            group = self.redis_client.hget(f"static:{symbol}", "dos_group")
            return group if group else None
        except:
            return None
    
    def _get_cgrup(self, symbol: str) -> Optional[str]:
        """Get CGRUP for heldkuponlu symbols"""
        try:
            cgrup = self.redis_client.hget(f"static:{symbol}", "cgrup")
            return cgrup if cgrup else None
        except:
            return None
    
    def _calculate_group_average(self, dos_group: str, cgrup: Optional[str] = None) -> Optional[float]:
        """
        Calculate benchmark by averaging all symbols in group.
        
        Fallback method when cached average not available.
        """
        try:
            # Get all symbols in group
            if cgrup and dos_group == 'heldkuponlu':
                # Filter by CGRUP
                symbols = self._get_symbols_by_cgrup(cgrup)
            else:
                symbols = self._get_symbols_by_dos_group(dos_group)
            
            if not symbols:
                return None
            
            # Get current prices
            prices = []
            for sym in symbols:
                price = self.redis_client.hget(f"live:{sym}", "last")
                if price:
                    prices.append(float(price))
            
            if not prices:
                return None
            
            avg_price = sum(prices) / len(prices)
            logger.info(f"[Benchmark] Calculated {dos_group}/{cgrup} avg: {avg_price:.2f} from {len(prices)} symbols")
            
            return avg_price
            
        except Exception as e:
            logger.error(f"[Benchmark] Error calculating group avg: {e}")
            return None
    
    def _get_symbols_by_dos_group(self, dos_group: str) -> list:
        """Get all symbols in a DOS Group"""
        try:
            # Scan all static keys
            symbols = []
            for key in self.redis_client.scan_iter("static:*"):
                sym = key.replace("static:", "")
                group = self.redis_client.hget(key, "dos_group")
                if group == dos_group:
                    symbols.append(sym)
            return symbols
        except:
            return []
    
    def _get_symbols_by_cgrup(self, cgrup: str) -> list:
        """Get all heldkuponlu symbols in a CGRUP"""
        try:
            symbols = []
            for key in self.redis_client.scan_iter("static:*"):
                sym = key.replace("static:", "")
                sym_cgrup = self.redis_client.hget(key, "cgrup")
                if sym_cgrup == cgrup:
                    symbols.append(sym)
            return symbols
        except:
            return []


# Singleton instance
_fetcher_instance = None

def get_benchmark_fetcher() -> BenchmarkPriceFetcher:
    """Get or create benchmark fetcher instance"""
    global _fetcher_instance
    if _fetcher_instance is None:
        _fetcher_instance = BenchmarkPriceFetcher()
    return _fetcher_instance
