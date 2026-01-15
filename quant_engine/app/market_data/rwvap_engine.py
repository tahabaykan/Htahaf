"""app/market_data/rwvap_engine.py

RWVAP Engine (Robust VWAP)
Calculates volume-weighted average price excluding extreme volume prints.

Purpose:
- Filter out FINRA prints and extreme block transfers that distort VWAP
- Provide robust VWAP for illiquid/preferred stocks
- Use existing tick buffer (no new data fetching)

Windows:
- RWVAP_1D: Last 1 trading day
- RWVAP_3D: Last 3 trading days
- RWVAP_5D: Last 5 trading days

Extreme Volume Filter:
- Exclude prints where size > (AVG_ADV * extreme_multiplier)
- Default multiplier: 2.0 (configurable)
"""

from typing import Dict, Any, Optional, List
from collections import deque
from datetime import datetime
import time
import threading

from app.core.logger import logger
from app.market_data.trading_calendar import get_trading_calendar


class RWVAPEngine:
    """
    Robust VWAP Engine.
    
    Calculates VWAP excluding extreme volume prints (FINRA, block transfers).
    
    Architecture:
    - Uses existing extended_prints_store (150 tick buffer)
    - Trading-time aware windows
    - Lazy computation (only when requested)
    - O(N) per symbol (N = prints in window)
    """
    
    # Window definitions (name: trading days)
    RWVAP_WINDOWS = {
        'rwvap_1d': 1,   # Last 1 trading day
        'rwvap_3d': 3,   # Last 3 trading days
        'rwvap_5d': 5,   # Last 5 trading days
    }
    
    def __init__(
        self,
        extreme_multiplier: float = 1.0,  # Changed to 1.0 (AVG_ADV * 1.0 = exclude prints >= AVG_ADV)
        min_prints_for_valid: int = 5
    ):
        """
        Initialize RWVAP Engine.
        
        Args:
            extreme_multiplier: Multiplier for AVG_ADV to determine extreme volume (default: 1.0)
                Prints with size > (AVG_ADV * multiplier) will be excluded
            min_prints_for_valid: Minimum prints needed for valid RWVAP (default: 5)
        """
        self.extreme_multiplier = extreme_multiplier
        self.min_prints_for_valid = min_prints_for_valid
        
        # RWVAP cache: {symbol: {window_name: rwvap_metrics}}
        self.rwvap_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
        
        # Reference to extended_prints_store (will be set from GRPANEngine)
        self.extended_prints_store: Optional[Dict[str, deque]] = None
        
        # Reference to last_price_cache (from GRPANEngine) - for consistent "last" price
        self.last_price_cache: Optional[Dict[str, float]] = None
        
        # Static data store reference (for AVG_ADV lookup)
        self.static_store = None
        
        # Cache lock
        self._cache_lock = threading.Lock()
    
    def set_extended_prints_store(self, extended_prints_store: Dict[str, deque]):
        """Set reference to extended_prints_store from GRPANEngine."""
        self.extended_prints_store = extended_prints_store
    
    def set_static_store(self, static_store):
        """Set reference to static data store (for AVG_ADV lookup)."""
        self.static_store = static_store
    
    def set_last_price_cache(self, last_price_cache: Dict[str, float]):
        """Set reference to last_price_cache from GRPANEngine (for consistent 'last' price)."""
        self.last_price_cache = last_price_cache
    
    def compute_rwvap(
        self,
        symbol: str,
        window_name: str = 'rwvap_1d'
    ) -> Dict[str, Any]:
        """
        Compute RWVAP for a symbol and window.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            window_name: Window name ('rwvap_1d', 'rwvap_3d', 'rwvap_5d')
            
        Returns:
            RWVAP metrics dict
        """
        if window_name not in self.RWVAP_WINDOWS:
            return self._empty_rwvap_result(f'Invalid window: {window_name}')
        
        if not self.extended_prints_store:
            return self._empty_rwvap_result('Extended prints store not available')
        
        try:
            # Get extended prints for symbol
            extended_prints = list(self.extended_prints_store.get(symbol, deque()))
            
            if len(extended_prints) == 0:
                return self._empty_rwvap_result('No prints available (bootstrap in progress)')
            
            # Get trading days for window
            trading_days = self.RWVAP_WINDOWS[window_name]
            
            # Get trading-time aware window boundaries
            trading_calendar = get_trading_calendar()
            current_time = time.time()
            
            # Get last trade timestamp
            last_print = extended_prints[-1]
            window_state_temp = self._create_temp_window_state()
            last_trade_ts = window_state_temp._parse_timestamp(last_print.get('time'), current_time)
            if last_trade_ts is None:
                last_trade_ts = current_time
            
            # Get trading-time "now"
            trading_time_now = trading_calendar.get_trading_time_now(last_trade_ts)
            
            # Get trading day boundaries
            trading_days_list = trading_calendar.get_trading_days_back(trading_days, datetime.fromtimestamp(trading_time_now))
            
            if not trading_days_list:
                return self._empty_rwvap_result('No trading days available')
            
            # Window start = oldest trading day start
            window_start = trading_days_list[-1].timestamp()  # Oldest day
            
            # Get AVG_ADV for extreme volume filter
            avg_adv = None
            if self.static_store:
                static_data = self.static_store.get_static_data(symbol)
                if static_data:
                    avg_adv = static_data.get('AVG_ADV')
            
            extreme_threshold = None
            if avg_adv is not None and avg_adv > 0:
                extreme_threshold = avg_adv * self.extreme_multiplier
            
            # Filter prints within window and apply extreme volume filter
            window_prints = []
            excluded_prints = []
            total_volume = 0.0
            excluded_volume = 0.0
            weighted_price_sum = 0.0
            
            for print_data in extended_prints:
                print_time = window_state_temp._parse_timestamp(print_data.get('time'), trading_time_now)
                if print_time is None or print_time < window_start:
                    continue
                
                price = float(print_data.get('price', 0))
                size = float(print_data.get('size', 0))
                
                if price <= 0 or size <= 0:
                    continue
                
                # Check extreme volume filter
                if extreme_threshold and size > extreme_threshold:
                    excluded_prints.append(print_data)
                    excluded_volume += size
                    continue
                
                # Include in RWVAP calculation
                window_prints.append(print_data)
                total_volume += size
                weighted_price_sum += price * size
            
            # Calculate RWVAP
            if len(window_prints) < self.min_prints_for_valid:
                status = 'COLLECTING' if len(window_prints) > 0 else 'INSUFFICIENT_DATA'
                return self._empty_rwvap_result(
                    f'Insufficient prints ({len(window_prints)}/{self.min_prints_for_valid})',
                    status=status,
                    effective_print_count=len(window_prints),
                    excluded_print_count=len(excluded_prints)
                )
            
            rwvap = weighted_price_sum / total_volume if total_volume > 0 else None
            
            if rwvap is None:
                return self._empty_rwvap_result('RWVAP calculation failed')
            
            # Calculate excluded volume ratio
            total_volume_with_excluded = total_volume + excluded_volume
            excluded_volume_ratio = excluded_volume / total_volume_with_excluded if total_volume_with_excluded > 0 else 0.0
            
            # Get last price for deviation calculation (use symbol's actual last trade price, not window-specific)
            last_price = None
            if self.last_price_cache:
                last_price = self.last_price_cache.get(symbol)
            
            # Fallback: use most recent print from extended_prints_store if cache not available
            if last_price is None and extended_prints:
                last_print = extended_prints[-1]
                last_price = float(last_print.get('price', 0))
            
            deviation_vs_last = None
            if last_price and rwvap:
                # Deviation = last_price - rwvap (how much last price deviates from RWVAP)
                deviation_vs_last = last_price - rwvap
            
            result = {
                'rwvap': rwvap,
                'total_volume': total_volume,
                'effective_print_count': len(window_prints),
                'excluded_print_count': len(excluded_prints),
                'excluded_volume': excluded_volume,
                'excluded_volume_ratio': excluded_volume_ratio,
                'deviation_vs_last': deviation_vs_last,
                'last_price': last_price,
                'extreme_threshold': extreme_threshold,
                'avg_adv': avg_adv,
                'status': 'OK',
                'window_name': window_name,
                'trading_days': trading_days,
                'time_span_hours': (trading_time_now - window_start) / 3600.0
            }
            
            # Cache result
            with self._cache_lock:
                if symbol not in self.rwvap_cache:
                    self.rwvap_cache[symbol] = {}
                self.rwvap_cache[symbol][window_name] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Error computing RWVAP for {symbol} ({window_name}): {e}", exc_info=True)
            return self._empty_rwvap_result(f'Error: {str(e)}')
    
    def get_all_rwvap_for_symbol(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all RWVAP windows for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            
        Returns:
            Dict mapping window_name -> RWVAP metrics
        """
        results = {}
        for window_name in self.RWVAP_WINDOWS.keys():
            results[window_name] = self.compute_rwvap(symbol, window_name)
        return results
    
    def _create_temp_window_state(self):
        """Create temporary window state for timestamp parsing."""
        from app.market_data.grpan_engine import GRPANWindowState
        return GRPANWindowState('temp', 60)
    
    def _empty_rwvap_result(
        self,
        message: str,
        status: str = 'INSUFFICIENT_DATA',
        effective_print_count: int = 0,
        excluded_print_count: int = 0
    ) -> Dict[str, Any]:
        """
        Return empty RWVAP result.
        
        Args:
            message: Error/info message
            status: Status ('OK', 'COLLECTING', 'INSUFFICIENT_DATA')
            effective_print_count: Number of effective prints
            excluded_print_count: Number of excluded prints
            
        Returns:
            Empty RWVAP metrics dict
        """
        return {
            'rwvap': None,
            'total_volume': 0.0,
            'effective_print_count': effective_print_count,
            'excluded_print_count': excluded_print_count,
            'excluded_volume': 0.0,
            'excluded_volume_ratio': 0.0,
            'deviation_vs_last': None,
            'last_price': None,
            'extreme_threshold': None,
            'avg_adv': None,
            'status': status,
            'window_name': None,
            'trading_days': None,
            'time_span_hours': None,
            'message': message
        }


# Global instance
_rwvap_engine: Optional[RWVAPEngine] = None


def get_rwvap_engine() -> Optional[RWVAPEngine]:
    """Get global RWVAPEngine instance."""
    return _rwvap_engine


def initialize_rwvap_engine(
    extended_prints_store: Dict[str, deque],
    static_store,
    extreme_multiplier: float = 1.0  # Changed default to 1.0
) -> RWVAPEngine:
    """
    Initialize global RWVAPEngine instance.
    
    Args:
        extended_prints_store: Reference to GRPANEngine's extended_prints_store
        static_store: Static data store (for AVG_ADV lookup)
        extreme_multiplier: Multiplier for AVG_ADV extreme threshold
        
    Returns:
        RWVAPEngine instance
    """
    global _rwvap_engine
    _rwvap_engine = RWVAPEngine(extreme_multiplier=extreme_multiplier)
    _rwvap_engine.set_extended_prints_store(extended_prints_store)
    _rwvap_engine.set_static_store(static_store)
    logger.info(f"RWVAPEngine initialized (extreme_multiplier={extreme_multiplier})")
    return _rwvap_engine

