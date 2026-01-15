"""
GRPAN Engine
Grouped Real Print Analyzer - analyzes weighted price frequency from trade prints.

JANALL-Compatible Implementation:
- Event-driven: Only computes when trade print arrives
- Fixed-size ring buffer: deque(maxlen=15) - O(1) operations
- Lot-based weighting: 100/200/300 lot = 1.0, others = 0.25
- Auto-cache: GRPAN computed immediately on add_trade_print
- Batch loop only reads: No computation in API/cycle loops

Rules:
- Last 15 trade prints (ring buffer) - latest_pan
- Rolling windows: pan_10m, pan_30m, pan_1h, pan_3h, pan_1d, pan_3d
- Size < 10 lot ignore
- Weight: 100/200/300 lot = 1.0, others = 0.25
- Calculate: weighted price frequency, dominant price (grpan_price), 
  ±0.04 concentration %, real_lot_count, deviation_vs_last, deviation_vs_prev_window
"""

from typing import Dict, Any, Optional, List, Set, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta
import yaml
from pathlib import Path
import os
import threading
import time
import re

from app.core.logger import logger
from app.market_data.trading_calendar import get_trading_calendar


class GRPANWindowState:
    """State for a single rolling time window"""
    
    def __init__(self, window_name: str, window_seconds: int):
        self.window_name = window_name
        self.window_seconds = window_seconds
        self.prints: deque = deque()  # List of (timestamp, print_data) tuples
        self.last_computed: Optional[Dict[str, Any]] = None
    
    def add_print(self, print_data: Dict[str, Any], current_time: float):
        """Add print if within window"""
        print_time = self._parse_timestamp(print_data.get('time'), current_time)
        if print_time is None:
            return False
        
        window_start = current_time - self.window_seconds
        
        # Debug: Log if print is outside window
        if print_time < window_start:
            time_diff_sec = current_time - print_time
            time_diff_min = time_diff_sec / 60.0
            logger.debug(
                f"GRPAN {self.window_name}: Print outside window "
                f"(print_time={print_time:.0f}, window_start={window_start:.0f}, "
                f"diff={time_diff_min:.1f}min, window={self.window_seconds/60:.0f}min)"
            )
            return False
        
        self.prints.append((print_time, print_data))
        return True
    
    def clean_old_prints(self, current_time: float):
        """Remove prints outside window"""
        window_start = current_time - self.window_seconds
        while self.prints and self.prints[0][0] < window_start:
            self.prints.popleft()
    
    def _parse_timestamp(self, time_str: Optional[str], fallback_time: float) -> Optional[float]:
        """Parse timestamp string to unix timestamp"""
        if time_str is None:
            return fallback_time
        
        try:
            # Try ISO format first
            if 'T' in time_str:
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                return dt.timestamp()
            
            # Try unix timestamp
            if time_str.replace('.', '').isdigit():
                return float(time_str)
            
            # Try other formats
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                try:
                    dt = datetime.strptime(time_str, fmt)
                    return dt.timestamp()
                except:
                    continue
            
            return fallback_time
        except:
            return fallback_time


class GRPANEngine:
    """
    Computes GRPAN (Grouped Real Print Analyzer) metrics from trade prints.
    
    Event-driven architecture:
    - add_trade_print() triggers immediate GRPAN computation
    - compute_grpan() reads from cache (O(1))
    - Ring buffer ensures O(1) memory and operations
    
    Rolling windows:
    - latest_pan: Last 15 prints (backward compatible)
    - pan_10m, pan_30m, pan_1h, pan_3h, pan_1d, pan_3d: Time-based windows
    """
    
    # Rolling window definitions (name: seconds)
    ROLLING_WINDOWS = {
        'pan_10m': 10 * 60,           # 10 minutes
        'pan_30m': 30 * 60,           # 30 minutes
        'pan_1h': 60 * 60,            # 1 hour
        'pan_3h': 3 * 60 * 60,        # 3 hours
        'pan_1d': 24 * 60 * 60,       # 1 day
        'pan_3d': 3 * 24 * 60 * 60    # 3 days
    }
    
    def __init__(self, compute_interval_ms: float = 300.0):
        """
        Initialize GRPAN Engine.
        
        Args:
            compute_interval_ms: Batch compute loop interval in milliseconds (default: 300ms)
        """
        # Trade print store: {symbol: deque(maxlen=15)} - RING BUFFER (latest_pan)
        # Each print: {'time': str, 'price': float, 'size': float, 'venue': str}
        self.trade_prints_store: Dict[str, deque] = {}
        
        # Extended print store: {symbol: deque(maxlen=150)} - RING BUFFER (for rolling windows)
        # Stores last 150 ticks for rolling window calculations
        self.extended_prints_store: Dict[str, deque] = {}
        
        # Rolling window states: {symbol: {window_name: GRPANWindowState}}
        self.rolling_window_states: Dict[str, Dict[str, GRPANWindowState]] = {}
        
        # Bootstrap state: {symbol: bool} - tracks if symbol has been bootstrapped
        self.bootstrap_state: Dict[str, bool] = {}
        
        # GRPAN metrics cache: {symbol: {window_name: metrics}}
        # window_name can be 'latest_pan' or any rolling window name
        self.grpan_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
        
        # Last price cache (for deviation calculation): {symbol: last_price}
        self.last_price_cache: Dict[str, float] = {}
        
        # Dirty symbols set: symbols that need GRPAN recomputation
        self.dirty_symbols: Set[str] = set()
        self._dirty_lock = threading.Lock()
        
        # Configuration
        self.config = self._load_config()
        self.max_prints = 15  # Last 15 prints (ring buffer size for latest_pan)
        self.min_lot_size = self.config.get('print_realism', {}).get('min_lot_ignore', 20)
        self.concentration_range = 0.04  # ±0.04 for concentration calculation
        
        # Weighted Print Realism (for breakdown logging)
        weights = self.config.get('print_realism', {}).get('weights', {})
        self.high_weight_100_200 = weights.get('lot_100_200', 1.0)
        self.mid_weight_round = weights.get('round_large', 0.4)
        self.low_weight_irregular = weights.get('irregular', 0.2)
        
        # Batch compute loop
        self.compute_interval_ms = compute_interval_ms
        self._compute_thread: Optional[threading.Thread] = None
        self._compute_running = False
        
        # Metrics
        self.metrics = {
            'trades_per_sec': 0.0,
            'dirty_len': 0,
            'recomputed_count': 0,
            'grpan_compute_ms': 0.0,
            'last_compute_time': None
        }
        
        # 🔵 SLOW PATH: DO NOT auto-start compute loop
        # GRPAN is tick-by-tick analysis - only start when Deeper Analysis is enabled
        # self.start_compute_loop()  # DISABLED - call manually when needed
    
    def _get_rolling_window_states_for_symbol(self, symbol: str) -> Dict[str, GRPANWindowState]:
        """Get or create rolling window states for a symbol"""
        if symbol not in self.rolling_window_states:
            self.rolling_window_states[symbol] = {
                window_name: GRPANWindowState(window_name, window_seconds)
                for window_name, window_seconds in self.ROLLING_WINDOWS.items()
            }
        return self.rolling_window_states[symbol]
    
    def add_trade_print(self, symbol: str, print_data: Dict[str, Any]):
        """
        Add a trade print to the store (EVENT-DRIVEN, LAZY COMPUTE).
        
        This method:
        1. Adds print to latest_pan ring buffer (O(1))
        2. Adds print to all rolling windows (O(1) per window)
        3. Updates last price cache
        4. Marks symbol as dirty (O(1))
        5. Compute loop will batch-process dirty symbols
        
        Args:
            symbol: Symbol (PREF_IBKR)
            print_data: Dict with 'time', 'price', 'size', 'venue'
        """
        try:
            # Filter: size < min_lot_size ignore
            size = float(print_data.get('size', 0))
            if size < self.min_lot_size:
                return  # Ignore tiny prints
            
            current_time = time.time()
            price = float(print_data.get('price', 0))
            
            # Update last price cache (for deviation calculation)
            if price > 0:
                self.last_price_cache[symbol] = price
            
            # Add to latest_pan (backward compatible ring buffer - last 15 prints)
            if symbol not in self.trade_prints_store:
                self.trade_prints_store[symbol] = deque(maxlen=self.max_prints)
            self.trade_prints_store[symbol].append(print_data)
            
            # Add to extended_prints_store (last 150 ticks for rolling windows)
            if symbol not in self.extended_prints_store:
                self.extended_prints_store[symbol] = deque(maxlen=150)
            self.extended_prints_store[symbol].append(print_data)
            
            # Add to all rolling windows (timestamp-based, but only from extended_prints_store)
            rolling_states = self._get_rolling_window_states_for_symbol(symbol)
            added_to_windows = []
            for window_name, window_state in rolling_states.items():
                if window_state.add_print(print_data, current_time):
                    added_to_windows.append(window_name)
            
            # Debug: Log which windows received the print
            if len(added_to_windows) < len(rolling_states):
                skipped_windows = [w for w in rolling_states.keys() if w not in added_to_windows]
                logger.debug(
                    f"GRPAN {symbol}: Print added to {len(added_to_windows)}/{len(rolling_states)} windows. "
                    f"Skipped: {skipped_windows} (likely outside time window)"
                )
            
            # Mark symbol as dirty (O(1))
            with self._dirty_lock:
                self.dirty_symbols.add(symbol)
            
            # Log first few prints per symbol for debugging
            if not hasattr(self, '_print_log_count'):
                self._print_log_count = {}
            if symbol not in self._print_log_count:
                self._print_log_count[symbol] = 0
            self._print_log_count[symbol] += 1
            
            if self._print_log_count[symbol] <= 3:
                logger.info(
                    f"📊 GRPAN: Trade print #{self._print_log_count[symbol]} for {symbol}: "
                    f"price={price}, size={size}, "
                    f"latest_pan_size={len(self.trade_prints_store[symbol])}"
                )
        except Exception as e:
            logger.error(f"Error adding trade print for {symbol}: {e}", exc_info=True)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from microstructure_rules.yaml"""
        try:
            config_path = Path(__file__).parents[2] / 'config' / 'microstructure_rules.yaml'
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return yaml.safe_load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def _get_weight(self, lot_size: float, venue: str = 'UNKNOWN') -> float:
        """
        Get weight for a lot size based on Venue Policy:
        - Non-FNRA venues (EDGX, ARCA, etc.) -> 1.0
        - FNRA + 100/200 lot -> 1.0
        - FNRA + 300-1000 lot -> 0.4
        - FNRA + irregular -> 0.2
        - < 20 lot -> 0.0 (ignore)
        
        Args:
            lot_size: Lot size
            venue: Venue (e.g., 'FNRA', 'EDGX', 'NSDQ')
            
        Returns:
            Weight (1.0, 0.4, or 0.2)
        """
        if lot_size < 20:
            return 0.0

        venue_upper = str(venue).upper()
        
        # FNRA dışındaki TÜM print’ler GERÇEKTİR (1.0)
        if venue_upper != 'FNRA' and venue_upper != 'UNKNOWN' and venue_upper != '':
            return 1.0

        # FNRA veya UNKNOWN durumunda lot size kuralları geçerli
        weights = self.config.get('print_realism', {}).get('weights', {
            'lot_100_200': 1.0,
            'round_large': 0.4,
            'irregular': 0.2
        })
        
        # Exact 100 or 200
        if lot_size == 100 or lot_size == 200:
            return weights.get('lot_100_200', 1.0)
            
        # Round large multiples of 100 (>= 300)
        if lot_size >= 300 and lot_size % 100 == 0:
             return weights.get('round_large', 0.4)
             
        # All others
        return weights.get('irregular', 0.2)
    
    def _compute_grpan_for_prints(
        self, 
        prints: List[Dict[str, Any]],
        last_price: Optional[float] = None,
        prev_grpan_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Compute GRPAN for a list of prints (shared logic for latest_pan and rolling windows).
        
        Args:
            prints: List of print dicts
            last_price: Last price for deviation calculation
            prev_grpan_price: Previous GRPAN price for deviation calculation
            
        Returns:
            GRPAN metrics dict
        """
        # Filter: size >= min_lot_size
        filtered_prints = [
            p for p in prints 
            if p.get('size', 0) >= self.min_lot_size
        ]
        
        if not filtered_prints:
            return self._empty_grpan_result(f'No prints with size >= {self.min_lot_size}')
        
        # Calculate weighted price frequency
        price_frequency: Dict[float, float] = defaultdict(float)
        total_lots = 0
        
        for print_data in filtered_prints:
            price = float(print_data.get('price', 0))
            size = float(print_data.get('size', 0))
            venue = print_data.get('venue', 'UNKNOWN')
            weight = self._get_weight(size, venue)
            
            # Add weighted frequency
            price_frequency[price] += weight
            total_lots += size
        
        # Find dominant price (highest weighted frequency)
        if not price_frequency:
            return self._empty_grpan_result('No valid price frequency calculated')
        
        # Sort by weighted frequency (descending)
        sorted_prices = sorted(
            price_frequency.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        grpan_price = sorted_prices[0][0]  # Dominant price
        
        # Calculate concentration % (±0.04 range)
        concentration_count = 0
        total_prints = len(filtered_prints)
        
        for print_data in filtered_prints:
            price = float(print_data.get('price', 0))
            if abs(price - grpan_price) <= self.concentration_range:
                concentration_count += 1
        
        concentration_percent = (concentration_count / total_prints * 100) if total_prints > 0 else 0.0
        
        # Calculate deviations
        deviation_vs_last = None
        if last_price is not None and last_price > 0:
            # Deviation = last_price - grpan_price (how much last price deviates from GRPAN)
            deviation_vs_last = last_price - grpan_price
        
        deviation_vs_prev_window = None
        if prev_grpan_price is not None:
            deviation_vs_prev_window = grpan_price - prev_grpan_price
        
        # Build result
        result = {
            'grpan_price': round(grpan_price, 4),
            'weighted_price_frequency': {
                round(price, 4): round(freq, 4) 
                for price, freq in sorted_prices[:10]  # Top 10 prices
            },
            'concentration_percent': round(concentration_percent, 2),
            'real_lot_count': round(total_lots, 2),
            'print_count': len(filtered_prints),
            'deviation_vs_last': round(deviation_vs_last, 4) if deviation_vs_last is not None else None,
            'deviation_vs_prev_window': round(deviation_vs_prev_window, 4) if deviation_vs_prev_window is not None else None,
            'breakdown': {
                'total_prints': len(prints),
                'filtered_prints': len(filtered_prints),
                'min_lot_size': self.min_lot_size,
                'concentration_range': self.concentration_range,
                'weights': {
                    'institutional': self.high_weight_100_200,
                    'round': self.mid_weight_round,
                    'irregular': self.low_weight_irregular
                },
                'top_prices': [
                    {'price': round(price, 4), 'weighted_freq': round(freq, 4)}
                    for price, freq in sorted_prices[:5]
                ]
            }
        }
        
        return result
    
    def _compute_grpan_internal(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """
        Internal GRPAN computation for all windows (latest_pan + rolling windows).
        
        Args:
            symbol: Symbol (PREF_IBKR)
            
        Returns:
            Dict mapping window_name -> GRPAN metrics
        """
        try:
            current_time = time.time()
            last_price = self.last_price_cache.get(symbol)
            
            results: Dict[str, Dict[str, Any]] = {}
            
            # Compute latest_pan (backward compatible)
            prints_deque = self.trade_prints_store.get(symbol)
            if prints_deque:
                prints = list(prints_deque)
                latest_result = self._compute_grpan_for_prints(prints, last_price=last_price)
                results['latest_pan'] = latest_result
            else:
                results['latest_pan'] = self._empty_grpan_result('No trade prints available')
            
            # Compute rolling windows from extended_prints_store (last 150 ticks)
            # Use TRADING-TIME aware filtering (not wall-clock time)
            extended_prints = list(self.extended_prints_store.get(symbol, deque()))
            
            if len(extended_prints) == 0:
                # No extended prints yet - mark as loading
                for window_name in ['pan_10m', 'pan_30m', 'pan_1h', 'pan_3h', 'pan_1d', 'pan_3d']:
                    results[window_name] = self._empty_grpan_result('Loading... (bootstrap in progress)')
            else:
                # Get trading-time aware "now"
                trading_calendar = get_trading_calendar()
                
                # Get last trade timestamp from extended_prints (most recent)
                last_trade_ts = None
                if extended_prints:
                    last_print = extended_prints[-1]
                    # Use GRPANWindowState's _parse_timestamp method (same logic)
                    window_state_temp = GRPANWindowState('temp', 60)
                    last_trade_ts = window_state_temp._parse_timestamp(last_print.get('time'), current_time)
                    if last_trade_ts is None:
                        last_trade_ts = current_time
                
                # Get trading-time "now" (market closed = last trade time, market open = real time)
                trading_time_now = trading_calendar.get_trading_time_now(last_trade_ts)
                
                # Compute rolling windows from extended prints (trading-time based filtering)
                prev_window_grpan = results.get('latest_pan', {}).get('grpan_price')
                window_order = ['pan_10m', 'pan_30m', 'pan_1h', 'pan_3h', 'pan_1d', 'pan_3d']
                
                for window_name in window_order:
                    window_seconds = self.ROLLING_WINDOWS[window_name]
                    
                    # Calculate window start in trading-time
                    if window_name in ['pan_1d', 'pan_3d']:
                        # For day-based windows, use trading day boundaries
                        if window_name == 'pan_1d':
                            # Last trading day
                            last_trading_day_end = trading_calendar.get_trading_day_end()
                            window_start = last_trading_day_end.timestamp()
                        else:  # pan_3d
                            # Last 3 trading days
                            trading_days = trading_calendar.get_trading_days_back(3)
                            if trading_days:
                                window_start = trading_days[-1].timestamp()  # Oldest of 3 days
                            else:
                                window_start = trading_time_now - window_seconds
                    else:
                        # For time-based windows (10m, 30m, 1h, 3h), use trading-time
                        # If market closed, window is relative to last trade time
                        window_start = trading_time_now - window_seconds
                    
                    # Filter prints within window from extended_prints_store
                    window_prints = []
                    # Use GRPANWindowState's _parse_timestamp method (same logic)
                    window_state_temp = GRPANWindowState('temp', 60)
                    for print_data in extended_prints:
                        print_time = window_state_temp._parse_timestamp(print_data.get('time'), trading_time_now)
                        if print_time is not None and print_time >= window_start:
                            window_prints.append(print_data)
                    
                    # Debug: Log window state
                    if len(window_prints) == 0:
                        logger.debug(
                            f"GRPAN {symbol} {window_name}: No prints in window "
                            f"(window_size={window_seconds/60:.0f}min, extended_prints={len(extended_prints)}, "
                            f"trading_time_now={trading_time_now:.0f}, window_start={window_start:.0f})"
                        )
                    
                    # Compute GRPAN for this window
                    window_result = self._compute_grpan_for_prints(
                        window_prints,
                        last_price=last_price,
                        prev_grpan_price=prev_window_grpan
                    )
                    
                    # If no data but we have extended prints, try to use cached value (stable during market closed)
                    if window_result.get('grpan_price') is None and len(extended_prints) > 0:
                        # Check if we have cached value from previous computation
                        cached_result = self.grpan_cache.get(symbol, {}).get(window_name)
                        if cached_result and cached_result.get('grpan_price') is not None:
                            # Use cached value (stable during market closed)
                            window_result = cached_result.copy()
                            window_result['message'] = 'Market closed - showing last available data'
                        else:
                            # No cached value - show empty result
                            window_result = self._empty_grpan_result('Market closed - no data available')
                    
                    results[window_name] = window_result
                    
                    # Use this window's GRPAN as previous for next window
                    if window_result.get('grpan_price') is not None:
                        prev_window_grpan = window_result['grpan_price']
            
            # Log successful computation
            successful_windows = [w for w, r in results.items() if r.get('grpan_price') is not None]
            if successful_windows:
                logger.debug(
                    f"✅ GRPAN computed for {symbol}: {len(successful_windows)} windows "
                    f"({', '.join(successful_windows)})"
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Error computing GRPAN for {symbol}: {e}", exc_info=True)
            return {'latest_pan': self._empty_grpan_result(str(e))}
    
    def _empty_grpan_result(self, error_msg: str) -> Dict[str, Any]:
        """
        Return empty GRPAN result with error message.
        
        Args:
            error_msg: Error message
            
        Returns:
            Empty GRPAN metrics dict
        """
        return {
            'grpan_price': None,
            'weighted_price_frequency': {},
            'concentration_percent': None,
            'real_lot_count': 0,
            'print_count': 0,
            'deviation_vs_last': None,
            'deviation_vs_prev_window': None,
            'breakdown': {
                'error': error_msg
            }
        }
    
    def compute_grpan(self, symbol: str, window: Optional[str] = None) -> Dict[str, Any]:
        """
        Get GRPAN metrics for a symbol (READ-ONLY from cache).
        
        This method is called by batch loops / API / PSFALGO.
        It does NOT compute, only reads from cache.
        
        If cache is empty, computes once (lazy initialization).
        
        Args:
            symbol: Symbol (PREF_IBKR)
            window: Optional window name ('latest_pan', 'pan_10m', 'pan_30m', etc.)
                   If None, returns latest_pan (backward compatible)
            
        Returns:
            If window specified: Single window metrics
            If window None: latest_pan metrics (backward compatible)
        """
        # Read from cache (O(1))
        if symbol in self.grpan_cache:
            symbol_cache = self.grpan_cache[symbol]
            if window:
                return symbol_cache.get(window, self._empty_grpan_result(f'Window {window} not found'))
            # Backward compatible: return latest_pan
            return symbol_cache.get('latest_pan', self._empty_grpan_result('No GRPAN data available'))
        
        # Lazy initialization: if cache is empty but prints exist, compute once
        if symbol in self.trade_prints_store and len(self.trade_prints_store[symbol]) > 0:
            all_results = self._compute_grpan_internal(symbol)
            self.grpan_cache[symbol] = all_results
            if window:
                return all_results.get(window, self._empty_grpan_result(f'Window {window} not found'))
            # Backward compatible: return latest_pan
            return all_results.get('latest_pan', self._empty_grpan_result('No GRPAN data available'))
        
        # No data available
        return self._empty_grpan_result('No trade prints available')
    
    def compute_batch_grpan(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get GRPAN metrics for all symbols in batch (READ-ONLY from cache).
        
        This method is called by batch loops / API.
        It does NOT compute, only reads from cache.
        
        Args:
            symbols: List of symbols to get GRPAN for
            
        Returns:
            Dict mapping symbol -> GRPAN metrics
        """
        results = {}
        for symbol in symbols:
            # Read from cache (O(1) per symbol)
            results[symbol] = self.compute_grpan(symbol)
        
        logger.debug(f"Retrieved GRPAN for {len(results)} symbols from cache")
        return results
    
    def get_grpan_for_symbol(self, symbol: str, window: Optional[str] = None) -> Dict[str, Any]:
        """
        Get cached GRPAN metrics for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            window: Optional window name ('latest_pan', 'pan_10m', 'pan_30m', etc.)
                   If None, returns latest_pan (backward compatible)
            
        Returns:
            If window specified: Single window metrics
            If window None: latest_pan metrics (backward compatible)
            If all windows needed: Use get_all_windows_for_symbol()
        """
        if symbol not in self.grpan_cache:
            return self._empty_grpan_result('No GRPAN data available')
        
        symbol_cache = self.grpan_cache[symbol]
        if window:
            return symbol_cache.get(window, self._empty_grpan_result(f'Window {window} not found'))
        
        # Backward compatible: return latest_pan
        return symbol_cache.get('latest_pan', self._empty_grpan_result('No GRPAN data available'))
    
    def get_all_windows_for_symbol(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all GRPAN windows for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            
        Returns:
            Dict mapping window_name -> GRPAN metrics
        """
        return self.grpan_cache.get(symbol, {})
    
    def start_compute_loop(self):
        """Start the batch compute loop thread."""
        if self._compute_running:
            return
        
        self._compute_running = True
        self._compute_thread = threading.Thread(target=self._compute_loop, daemon=True)
        self._compute_thread.start()
        logger.info(f"GRPAN compute loop started (interval: {self.compute_interval_ms}ms)")
    
    def stop_compute_loop(self):
        """Stop the batch compute loop thread."""
        self._compute_running = False
        if self._compute_thread:
            self._compute_thread.join(timeout=1.0)
        logger.info("GRPAN compute loop stopped")
    
    def _compute_loop(self):
        """Batch compute loop: processes dirty_symbols at fixed interval."""
        interval_sec = self.compute_interval_ms / 1000.0
        last_trade_count = 0
        last_time = time.time()
        
        while self._compute_running:
            try:
                loop_start = time.time()
                
                # Snapshot dirty symbols
                with self._dirty_lock:
                    dirty_snapshot = set(self.dirty_symbols)
                    self.dirty_symbols.clear()
                
                # Update metrics
                current_time = time.time()
                time_delta = current_time - last_time
                if time_delta > 0:
                    trades_delta = self.metrics.get('recomputed_count', 0) - last_trade_count
                    self.metrics['trades_per_sec'] = trades_delta / time_delta
                    last_trade_count = self.metrics.get('recomputed_count', 0)
                    last_time = current_time
                
                self.metrics['dirty_len'] = len(dirty_snapshot)
                
                # Batch compute for dirty symbols
                if dirty_snapshot:
                    compute_start = time.time()
                    recomputed = 0
                    
                    for symbol in dirty_snapshot:
                        try:
                            # Check print count before computing
                            prints_deque = self.trade_prints_store.get(symbol)
                            if prints_deque:
                                print_count = len(prints_deque)
                                filtered_count = sum(1 for p in prints_deque if p.get('size', 0) >= self.min_lot_size)
                                logger.debug(f"GRPAN compute for {symbol}: {print_count} total prints, {filtered_count} >= {self.min_lot_size} lot")
                            
                            all_results = self._compute_grpan_internal(symbol)
                            self.grpan_cache[symbol] = all_results
                            
                            # Log if any window was successfully computed
                            successful_windows = [w for w, r in all_results.items() if r.get('grpan_price') is not None]
                            if successful_windows:
                                recomputed += 1
                                latest_pan = all_results.get('latest_pan', {})
                                logger.debug(
                                    f"GRPAN computed for {symbol}: {len(successful_windows)} windows, "
                                    f"latest_pan=${latest_pan.get('grpan_price', 'N/A')}"
                                )
                        except Exception as e:
                            logger.error(f"Error computing GRPAN for {symbol}: {e}", exc_info=True)
                    
                    compute_time_ms = (time.time() - compute_start) * 1000.0
                    self.metrics['grpan_compute_ms'] = compute_time_ms
                    self.metrics['recomputed_count'] = recomputed
                    self.metrics['last_compute_time'] = time.time()
                    
                    if recomputed > 0:
                        logger.info(
                            f"📊 GRPAN batch compute: {recomputed} symbols in {compute_time_ms:.2f}ms"
                        )
                    elif dirty_snapshot:
                        # Log when symbols are dirty but no GRPAN computed (likely insufficient prints)
                        logger.debug(f"GRPAN compute loop: {len(dirty_snapshot)} dirty symbols but no GRPAN computed (likely insufficient prints)")
                
                # Sleep until next interval
                elapsed = time.time() - loop_start
                sleep_time = max(0, interval_sec - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Error in GRPAN compute loop: {e}", exc_info=True)
                time.sleep(interval_sec)
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get GRPAN engine metrics.
        
        Returns:
            Metrics dict with trades_per_sec, dirty_len, recomputed_count, etc.
        """
        return self.metrics.copy()


# Global instance
_grpan_engine: Optional[GRPANEngine] = None


def get_grpan_engine() -> Optional[GRPANEngine]:
    """Get global GRPANEngine instance"""
    global _grpan_engine
    if _grpan_engine is None:
        # Try to get from market_data_routes
        try:
            from app.api.market_data_routes import grpan_engine as routes_engine
            if routes_engine:
                _grpan_engine = routes_engine
        except Exception:
            pass
    return _grpan_engine


def initialize_grpan_engine() -> GRPANEngine:
    """Initialize global GRPANEngine instance"""
    global _grpan_engine
    # If already initialized in market_data_routes, use that instance
    try:
        from app.api.market_data_routes import grpan_engine as routes_engine
        if routes_engine:
            _grpan_engine = routes_engine
            logger.info("GRPANEngine global instance synced from market_data_routes")
            return _grpan_engine
    except Exception:
        pass
    # Otherwise create new instance
    _grpan_engine = GRPANEngine()
    logger.info("GRPANEngine global instance initialized")
    return _grpan_engine


