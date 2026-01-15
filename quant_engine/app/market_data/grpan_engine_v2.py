"""
GRPAN Engine V2 - Rolling Windows Architecture
Grouped Real Print Analyzer with time-based rolling windows.

Features:
- Rolling windows: 10m, 30m, 3h, 1d, 3d
- Deviation analysis: vs LAST, vs previous window
- Event-driven architecture
- Group-level aggregation support
"""

from typing import Dict, Any, Optional, List, Set, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta
import threading
import time
import re

from app.core.logger import logger


class GRPANWindowState:
    """State for a single time window"""
    
    def __init__(self, window_name: str, window_seconds: int):
        self.window_name = window_name
        self.window_seconds = window_seconds
        self.prints: deque = deque()  # Will filter by timestamp
        self.last_computed: Optional[Dict[str, Any]] = None
        self.last_compute_time: Optional[float] = None
    
    def add_print(self, print_data: Dict[str, Any], current_time: float):
        """Add print if within window"""
        print_time = self._parse_timestamp(print_data.get('time'), current_time)
        if print_time is None:
            return False
        
        window_start = current_time - self.window_seconds
        if print_time >= window_start:
            self.prints.append((print_time, print_data))
            return True
        return False
    
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
            if time_str.isdigit() or '.' in time_str:
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


class GRPANEngineV2:
    """
    GRPAN Engine with rolling windows architecture.
    
    Each symbol maintains 5 time windows:
    - 10m: Last 10 minutes
    - 30m: Last 30 minutes
    - 3h: Last 3 hours
    - 1d: Last 1 day
    - 3d: Last 3 days
    
    Each window computes:
    - grpan_price (weighted mode)
    - concentration_percent
    - deviation_vs_last
    - deviation_vs_prev_window
    """
    
    # Window definitions (name: seconds)
    WINDOWS = {
        '10m': 10 * 60,      # 10 minutes
        '30m': 30 * 60,      # 30 minutes
        '3h': 3 * 60 * 60,   # 3 hours
        '1d': 24 * 60 * 60,  # 1 day
        '3d': 3 * 24 * 60 * 60  # 3 days
    }
    
    def __init__(self, compute_interval_ms: float = 300.0):
        """
        Initialize GRPAN Engine V2.
        
        Args:
            compute_interval_ms: Batch compute loop interval in milliseconds
        """
        # Per-symbol window states: {symbol: {window_name: GRPANWindowState}}
        self.window_states: Dict[str, Dict[str, GRPANWindowState]] = {}
        
        # GRPAN cache: {symbol: {window_name: metrics}}
        self.grpan_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
        
        # Last price cache (for deviation calculation): {symbol: last_price}
        self.last_price_cache: Dict[str, float] = {}
        
        # Dirty symbols: symbols that need recomputation
        self.dirty_symbols: Set[str] = set()
        self._dirty_lock = threading.Lock()
        
        # Configuration
        self.min_lot_size = 10
        self.high_weight_lots = [100, 200, 300]
        self.standard_weight = 0.25
        self.concentration_range = 0.04
        
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
        
        # Initialize window states for each window
        self._init_window_states()
        
        # Start compute loop
        self.start_compute_loop()
    
    def _init_window_states(self):
        """Initialize window state structures"""
        # This will be populated per-symbol as needed
        pass
    
    def _get_window_states_for_symbol(self, symbol: str) -> Dict[str, GRPANWindowState]:
        """Get or create window states for a symbol"""
        if symbol not in self.window_states:
            self.window_states[symbol] = {
                window_name: GRPANWindowState(window_name, window_seconds)
                for window_name, window_seconds in self.WINDOWS.items()
            }
        return self.window_states[symbol]
    
    def add_trade_print(self, symbol: str, print_data: Dict[str, Any]):
        """
        Add a trade print to all windows (EVENT-DRIVEN).
        
        Args:
            symbol: Symbol (PREF_IBKR)
            print_data: Dict with 'time', 'price', 'size', 'venue'
        """
        try:
            # Filter: size < min_lot_size ignore
            size = float(print_data.get('size', 0))
            if size < self.min_lot_size:
                return
            
            current_time = time.time()
            
            # Update last price cache
            price = float(print_data.get('price', 0))
            if price > 0:
                self.last_price_cache[symbol] = price
            
            # Add to all windows
            window_states = self._get_window_states_for_symbol(symbol)
            for window_state in window_states.values():
                window_state.add_print(print_data, current_time)
            
            # Mark symbol as dirty
            with self._dirty_lock:
                self.dirty_symbols.add(symbol)
            
            logger.debug(f"GRPAN V2: Trade print added for {symbol}: price={price}, size={size}")
            
        except Exception as e:
            logger.error(f"Error adding trade print for {symbol}: {e}", exc_info=True)
    
    def _get_weight(self, lot_size: float) -> float:
        """Get weight for a lot size"""
        if lot_size in self.high_weight_lots:
            return 1.0
        return self.standard_weight
    
    def _compute_grpan_for_window(
        self, 
        window_state: GRPANWindowState, 
        current_time: float,
        last_price: Optional[float] = None,
        prev_window_grpan: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Compute GRPAN for a single window.
        
        Args:
            window_state: Window state to compute
            current_time: Current unix timestamp
            last_price: Last price for deviation calculation
            prev_window_grpan: Previous window GRPAN for deviation calculation
            
        Returns:
            GRPAN metrics dict for this window
        """
        # Clean old prints
        window_state.clean_old_prints(current_time)
        
        # Get filtered prints (size >= min_lot_size)
        filtered_prints = [
            print_data for _, print_data in window_state.prints
            if print_data.get('size', 0) >= self.min_lot_size
        ]
        
        if not filtered_prints:
            return self._empty_window_result('No prints in window')
        
        # Calculate weighted price frequency
        price_frequency: Dict[float, float] = defaultdict(float)
        total_lots = 0
        
        for print_data in filtered_prints:
            price = float(print_data.get('price', 0))
            size = float(print_data.get('size', 0))
            weight = self._get_weight(size)
            
            price_frequency[price] += weight
            total_lots += size
        
        if not price_frequency:
            return self._empty_window_result('No valid price frequency')
        
        # Find dominant price
        sorted_prices = sorted(
            price_frequency.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        grpan_price = sorted_prices[0][0]
        
        # Calculate concentration
        concentration_count = sum(
            1 for print_data in filtered_prints
            if abs(float(print_data.get('price', 0)) - grpan_price) <= self.concentration_range
        )
        concentration_percent = (concentration_count / len(filtered_prints) * 100) if filtered_prints else 0.0
        
        # Calculate deviations
        deviation_vs_last = None
        if last_price is not None and last_price > 0:
            deviation_vs_last = grpan_price - last_price
        
        deviation_vs_prev_window = None
        if prev_window_grpan is not None:
            deviation_vs_prev_window = grpan_price - prev_window_grpan
        
        result = {
            'grpan_price': round(grpan_price, 4),
            'concentration_percent': round(concentration_percent, 2),
            'print_count': len(filtered_prints),
            'real_lot_count': round(total_lots, 2),
            'deviation_vs_last': round(deviation_vs_last, 4) if deviation_vs_last is not None else None,
            'deviation_vs_prev_window': round(deviation_vs_prev_window, 4) if deviation_vs_prev_window is not None else None,
            'weighted_price_frequency': {
                round(price, 4): round(freq, 4)
                for price, freq in sorted_prices[:10]
            }
        }
        
        return result
    
    def _empty_window_result(self, error_msg: str) -> Dict[str, Any]:
        """Return empty window result"""
        return {
            'grpan_price': None,
            'concentration_percent': None,
            'print_count': 0,
            'real_lot_count': 0,
            'deviation_vs_last': None,
            'deviation_vs_prev_window': None,
            'weighted_price_frequency': {},
            'error': error_msg
        }
    
    def _compute_all_windows_for_symbol(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """
        Compute GRPAN for all windows for a symbol.
        
        Args:
            symbol: Symbol to compute
            
        Returns:
            Dict mapping window_name -> GRPAN metrics
        """
        current_time = time.time()
        window_states = self._get_window_states_for_symbol(symbol)
        last_price = self.last_price_cache.get(symbol)
        
        results = {}
        prev_window_grpan = None
        
        # Compute in order: 10m, 30m, 3h, 1d, 3d
        window_order = ['10m', '30m', '3h', '1d', '3d']
        
        for window_name in window_order:
            window_state = window_states[window_name]
            window_result = self._compute_grpan_for_window(
                window_state,
                current_time,
                last_price=last_price,
                prev_window_grpan=prev_window_grpan
            )
            results[window_name] = window_result
            
            # Use this window's GRPAN as previous for next window
            if window_result.get('grpan_price') is not None:
                prev_window_grpan = window_result['grpan_price']
        
        return results
    
    def get_grpan_for_symbol(self, symbol: str, window: Optional[str] = None) -> Dict[str, Any]:
        """
        Get GRPAN metrics for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            window: Optional window name ('10m', '30m', '3h', '1d', '3d')
                   If None, returns all windows
            
        Returns:
            If window specified: Single window metrics
            If window None: Dict mapping window_name -> metrics
        """
        if symbol not in self.grpan_cache:
            return self._empty_window_result('No GRPAN data available') if window else {}
        
        symbol_cache = self.grpan_cache[symbol]
        
        if window:
            return symbol_cache.get(window, self._empty_window_result(f'Window {window} not found'))
        
        return symbol_cache.copy()
    
    def start_compute_loop(self):
        """Start the batch compute loop thread"""
        if self._compute_running:
            return
        
        self._compute_running = True
        self._compute_thread = threading.Thread(target=self._compute_loop, daemon=True)
        self._compute_thread.start()
        logger.info(f"GRPAN V2 compute loop started (interval: {self.compute_interval_ms}ms)")
    
    def stop_compute_loop(self):
        """Stop the batch compute loop thread"""
        self._compute_running = False
        if self._compute_thread:
            self._compute_thread.join(timeout=1.0)
        logger.info("GRPAN V2 compute loop stopped")
    
    def _compute_loop(self):
        """Batch compute loop: processes dirty_symbols at fixed interval"""
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
                            window_results = self._compute_all_windows_for_symbol(symbol)
                            self.grpan_cache[symbol] = window_results
                            
                            # Count successful computations
                            if any(r.get('grpan_price') is not None for r in window_results.values()):
                                recomputed += 1
                                
                        except Exception as e:
                            logger.error(f"Error computing GRPAN V2 for {symbol}: {e}", exc_info=True)
                    
                    compute_time_ms = (time.time() - compute_start) * 1000.0
                    self.metrics['grpan_compute_ms'] = compute_time_ms
                    self.metrics['recomputed_count'] = recomputed
                    self.metrics['last_compute_time'] = time.time()
                    
                    if recomputed > 0:
                        logger.info(
                            f"📊 GRPAN V2 batch compute: {recomputed} symbols in {compute_time_ms:.2f}ms"
                        )
                
                # Sleep until next interval
                elapsed = time.time() - loop_start
                sleep_time = max(0, interval_sec - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Error in GRPAN V2 compute loop: {e}", exc_info=True)
                time.sleep(interval_sec)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get GRPAN engine metrics"""
        return self.metrics.copy()






