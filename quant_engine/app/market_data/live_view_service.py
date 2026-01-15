"""
Live View Service - UI-Only Data Layer

⚠️ CRITICAL DESIGN PRINCIPLES:
1. This is ONLY for UI display - NOT for algo decisions
2. Reads directly from market_data_cache (fastest path)
3. Does NOT affect RUNALL, ADDNEWPOS, KARBOTU, or any algo logic
4. No extra polling - just a consumer of existing cache
5. Provides live_data and algo_ready flags for UI

Architecture:
    Hammer Pro → market_data_cache → LiveViewService → UI (fast, display only)
                                   ↘
    Hammer Pro → MarketSnapshotStore → DataReadinessChecker → RUNALL (safe, gated)

This separation ensures:
- UI is always responsive with latest prices
- Algo only runs when data is validated and ready
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.logger import logger


class LiveViewService:
    """
    Live View Service - provides fast, UI-only market data.
    
    ⚠️ THIS IS NOT FOR ALGO DECISIONS!
    Use MarketSnapshotStore + DataReadinessChecker for algo.
    
    Responsibilities:
    - Read from market_data_cache (fast)
    - Provide live_data flag
    - Provide algo_ready flag
    - Merge with static data for UI display
    
    Does NOT:
    - Make trading decisions
    - Gate algo execution
    - Modify any data
    """
    
    def __init__(self):
        """Initialize Live View Service"""
        self._last_update = None
        logger.info("[LIVE_VIEW] Service initialized")
    
    def get_live_prices(self, symbol: str) -> Dict[str, Any]:
        """
        Get live prices for a symbol (UI-only, fast path).
        
        Args:
            symbol: Symbol to get prices for
            
        Returns:
            Dict with bid, ask, last, spread, live_data flag
        """
        try:
            from app.api.market_data_routes import market_data_cache
            
            if not market_data_cache:
                return self._empty_prices(symbol, live_data=False)
            
            data = market_data_cache.get(symbol, {})
            
            if not data:
                return self._empty_prices(symbol, live_data=False)
            
            bid = data.get('bid')
            ask = data.get('ask')
            last = data.get('last') or data.get('price')
            
            # Calculate spread
            spread = None
            spread_percent = None
            if bid and ask and bid > 0 and ask > 0:
                spread = ask - bid
                mid = (bid + ask) / 2
                if mid > 0:
                    spread_percent = (spread / mid) * 100
            
            # Determine if we have live data
            has_live_data = bid is not None and ask is not None and last is not None
            
            return {
                'symbol': symbol,
                'bid': bid,
                'ask': ask,
                'last': last,
                'spread': spread,
                'spread_percent': spread_percent,
                'prev_close': data.get('prev_close'),
                'volume': data.get('volume'),
                'timestamp': data.get('timestamp'),
                'live_data': has_live_data,
                'source': 'market_data_cache'
            }
            
        except Exception as e:
            logger.debug(f"[LIVE_VIEW] Error getting prices for {symbol}: {e}")
            return self._empty_prices(symbol, live_data=False)
    
    def get_all_live_prices(self) -> Dict[str, Dict[str, Any]]:
        """
        Get live prices for all symbols in cache (UI-only).
        
        Returns:
            Dict of {symbol: price_data}
        """
        try:
            from app.api.market_data_routes import market_data_cache
            
            if not market_data_cache:
                return {}
            
            result = {}
            for symbol, data in market_data_cache.items():
                result[symbol] = self.get_live_prices(symbol)
            
            return result
            
        except Exception as e:
            logger.debug(f"[LIVE_VIEW] Error getting all prices: {e}")
            return {}
    
    def get_live_view_stats(self) -> Dict[str, Any]:
        """
        Get live view statistics for UI status display.
        
        Returns:
            Dict with counts and flags
        """
        try:
            from app.api.market_data_routes import market_data_cache, static_store
            from app.psfalgo.data_readiness_checker import get_data_readiness_checker
            
            # Count symbols with live data
            symbols_with_live = 0
            symbols_with_bid = 0
            symbols_with_ask = 0
            symbols_with_last = 0
            total_in_cache = 0
            
            if market_data_cache:
                total_in_cache = len(market_data_cache)
                for symbol, data in market_data_cache.items():
                    if data.get('bid') is not None:
                        symbols_with_bid += 1
                    if data.get('ask') is not None:
                        symbols_with_ask += 1
                    if data.get('last') is not None or data.get('price') is not None:
                        symbols_with_last += 1
                    if (data.get('bid') is not None and 
                        data.get('ask') is not None and 
                        (data.get('last') is not None or data.get('price') is not None)):
                        symbols_with_live += 1
            
            # Get total symbols from static store
            total_symbols = 0
            if static_store:
                total_symbols = len(static_store.get_all_symbols())
            
            # Check algo readiness
            algo_ready = False
            algo_reason = None
            checker = get_data_readiness_checker()
            if checker:
                algo_ready, algo_reason = checker.is_ready_for_runall()
            
            return {
                'total_symbols': total_symbols,
                'total_in_cache': total_in_cache,
                'symbols_with_live': symbols_with_live,
                'symbols_with_bid': symbols_with_bid,
                'symbols_with_ask': symbols_with_ask,
                'symbols_with_last': symbols_with_last,
                'live_data_percent': (symbols_with_live / total_symbols * 100) if total_symbols > 0 else 0,
                'algo_ready': algo_ready,
                'algo_reason': algo_reason,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.debug(f"[LIVE_VIEW] Error getting stats: {e}")
            return {
                'total_symbols': 0,
                'symbols_with_live': 0,
                'live_data_percent': 0,
                'algo_ready': False,
                'algo_reason': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def _empty_prices(self, symbol: str, live_data: bool = False) -> Dict[str, Any]:
        """Return empty price structure"""
        return {
            'symbol': symbol,
            'bid': None,
            'ask': None,
            'last': None,
            'spread': None,
            'spread_percent': None,
            'prev_close': None,
            'volume': None,
            'timestamp': None,
            'live_data': live_data,
            'source': 'empty'
        }


# Global instance
_live_view_service: Optional[LiveViewService] = None


def get_live_view_service() -> Optional[LiveViewService]:
    """Get global LiveViewService instance"""
    global _live_view_service
    if _live_view_service is None:
        _live_view_service = LiveViewService()
    return _live_view_service


def initialize_live_view_service() -> LiveViewService:
    """Initialize global LiveViewService instance"""
    global _live_view_service
    _live_view_service = LiveViewService()
    logger.info("[LIVE_VIEW] Service initialized globally")
    return _live_view_service





