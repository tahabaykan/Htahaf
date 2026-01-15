"""
Decision Helper Engine

Computes market state classification metrics from tick-by-tick data.
Analyzes price displacement, ADV fraction, aggressor proxy, efficiency, and trade frequency.

🔵 ISOLATED MODULE - Does NOT modify trading, order, risk, or PSFALGO logic.
"""

from typing import Dict, Any, Optional, List, Tuple
from collections import deque
from datetime import datetime, timedelta, timezone
import threading
import time

from app.core.logger import logger


class DecisionHelperEngine:
    """
    Computes decision metrics and classifies market state.
    
    Metrics:
    1. Price Displacement: last_price - first_price
    2. ADV Fraction: window_volume / AVG_ADV
    3. Aggressor Proxy: net_pressure = sum(aggressor * trade_size) / window_volume
    4. Efficiency: abs(price_displacement) / (window_volume / AVG_ADV)
    5. Trade Frequency: trade_count / window_minutes
    
    States:
    - BUYER_DOMINANT
    - SELLER_DOMINANT
    - SELLER_VACUUM
    - ABSORPTION
    - NEUTRAL
    """
    
    # Rolling window definitions (in minutes)
    WINDOWS = {
        '5m': 5,
        '15m': 15,
        '30m': 30
    }
    
    def __init__(self):
        """Initialize Decision Helper Engine"""
        # Tick store: {symbol: deque(maxlen=1000)} - stores last 1000 ticks
        # Each tick: {'t': timestamp, 'p': price, 's': size, 'b': bid, 'a': ask, 'bf': backfilled}
        self.tick_store: Dict[str, deque] = {}
        self._tick_lock = threading.Lock()
        
        # Results cache: {symbol: {window: result}}
        self.results_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._cache_lock = threading.Lock()
        
        logger.info("DecisionHelperEngine initialized")
    
    def add_tick(self, symbol: str, tick: Dict[str, Any]):
        """
        Add a tick to the store.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            tick: Tick data with keys: t (timestamp), p (price), s (size), b (bid), a (ask), bf (backfilled)
        """
        try:
            # Ignore backfilled ticks
            if tick.get('bf', False):
                return
            
            with self._tick_lock:
                if symbol not in self.tick_store:
                    self.tick_store[symbol] = deque(maxlen=1000)
                
                # Ensure required fields
                if 't' in tick and 'p' in tick and 's' in tick:
                    self.tick_store[symbol].append(tick)
        
        except Exception as e:
            logger.error(f"Error adding tick for {symbol}: {e}", exc_info=True)
    
    def compute_metrics(
        self,
        symbol: str,
        window_name: str,
        avg_adv: float,
        group_peers: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Compute decision metrics for a symbol over a rolling window.
        
        Args:
            symbol: Symbol to analyze
            window_name: Window name ('5m', '15m', '30m')
            avg_adv: Average daily volume for the symbol
            group_peers: List of peer symbols in the same group (for normalization)
        
        Returns:
            Dict with metrics and state classification
        """
        try:
            if window_name not in self.WINDOWS:
                logger.warning(f"Invalid window name: {window_name}")
                return None
            
            window_minutes = self.WINDOWS[window_name]
            window_seconds = window_minutes * 60
            
            with self._tick_lock:
                if symbol not in self.tick_store or len(self.tick_store[symbol]) == 0:
                    return None
                
                ticks = list(self.tick_store[symbol])
            
            if not ticks:
                return None
            
            # Parse all tick timestamps first
            tick_times_parsed = []
            for tick in ticks:
                ts = self._parse_timestamp(tick.get('t'))
                if ts:
                    tick_times_parsed.append((ts, tick))
            
            if not tick_times_parsed:
                logger.debug(f"No valid timestamps for {symbol}")
                return None
            
            # Sort by timestamp to find the most recent tick
            tick_times_parsed.sort(key=lambda x: x[0])
            
            # Use the most recent tick's timestamp as the window end time
            # This handles bootstrap data (historical ticks) correctly
            # Instead of using current_time, we use the last print time
            last_print_time = tick_times_parsed[-1][0]
            
            # For rolling window, use the last print time as reference
            # This ensures we analyze the most recent window of data available
            # Example: If last print was at 14:30:00 and window is 15m (900s)
            # We look at ticks from 14:15:00 to 14:30:00 (last 15 minutes from last print)
            window_end_time = last_print_time
            window_start_time = window_end_time - window_seconds
            
            # Filter ticks within window
            # Rolling window: Look at ticks from (window_end_time - window_seconds) to window_end_time
            # Store as (timestamp, tick) tuples for sorting
            window_ticks_with_time = []
            
            for tick_time, tick in tick_times_parsed:
                # Include ticks within the rolling window
                # tick_time should be >= window_start_time and <= window_end_time
                if window_start_time <= tick_time <= window_end_time:
                    # CRITICAL: Only include REAL TRADES
                    # Filter out:
                    # 1. Backfilled ticks (bf=true) - these are pseudo-ticks from OHLC backfills
                    # 2. Bid/ask updates (size=0) - these are not trades
                    # 3. Trades with no price (p=0) - invalid
                    # 4. Trades larger than AVG_ADV (likely FINRA/ADFN prints)
                    
                    if tick.get('bf', False):
                        continue  # Ignore pseudo-ticks from OHLC backfills
                    
                    price = float(tick.get('p', 0))
                    size = float(tick.get('s', 0))
                    
                    # Only include real trades: must have price AND size
                    if price > 0 and size > 0 and size <= avg_adv:
                        window_ticks_with_time.append((tick_time, tick))
            
            # Count real trades (for illiquid detection)
            real_trade_count = len(window_ticks_with_time)
            
            # ILLIQUID DETECTION: If less than 5 real trades, mark as illiquid
            # This prevents false signals from bid/ask updates and pseudo-ticks
            if real_trade_count < 5:
                logger.debug(
                    f"⚠️ [{symbol} ({window_name})] ILLIQUID: Only {real_trade_count} real trades "
                    f"(need ≥5 for signal). Window: {window_start_time:.1f} to {window_end_time:.1f}"
                )
                return {
                    "state": "ILLIQUID_NO_SIGNAL",
                    "confidence": 0.0,
                    "price_displacement": 0.0,
                    "adv_fraction": 0.0,
                    "net_pressure": 0.0,
                    "efficiency": 0.0,
                    "trade_frequency": real_trade_count / window_minutes if window_minutes > 0 else 0.0,
                    "real_trade_count": real_trade_count,
                    "updated_at": datetime.now().isoformat(),
                    "reason": f"Too few real trades ({real_trade_count} < 5) - insufficient data for signal"
                }
            
            if real_trade_count < 2:
                logger.debug(f"Not enough real trades in window for {symbol} ({window_name}): {real_trade_count} trades (need at least 2)")
                return None
            
            # Sort by timestamp (ascending: oldest first, newest last)
            window_ticks_with_time.sort(key=lambda x: x[0])
            tick_times = [ts for ts, _ in window_ticks_with_time]
            window_ticks = [tick for _, tick in window_ticks_with_time]
            
            # 1. Price Displacement
            # Use the chronologically FIRST tick (oldest) and LAST tick (newest)
            first_price = float(window_ticks[0].get('p', 0))
            last_price = float(window_ticks[-1].get('p', 0))
            first_tick_time = window_ticks[0].get('t', 'N/A')
            last_tick_time = window_ticks[-1].get('t', 'N/A')
            first_tick_ts = tick_times[0]
            last_tick_ts = tick_times[-1]
            
            # Calculate displacement: NEWEST price - OLDEST price
            # Positive = price went UP over time
            # Negative = price went DOWN over time
            price_displacement = last_price - first_price
            
            # DEBUG: Log displacement calculation details
            disp_last_minus_first = last_price - first_price
            disp_first_minus_last = first_price - last_price
            time_diff_seconds = last_tick_ts - first_tick_ts if last_tick_ts > first_tick_ts else 0
            
            # Log at INFO level so it's visible
            logger.info(
                f"🔍 [DISPLACEMENT] {symbol} ({window_name}): "
                f"first={first_price:.4f}@{first_tick_time[:19] if len(str(first_tick_time)) > 19 else first_tick_time} "
                f"(ts={first_tick_ts:.1f}), "
                f"last={last_price:.4f}@{last_tick_time[:19] if len(str(last_tick_time)) > 19 else last_tick_time} "
                f"(ts={last_tick_ts:.1f}), "
                f"time_diff={time_diff_seconds:.1f}s, "
                f"disp(last-first)={disp_last_minus_first:.4f}, "
                f"disp(first-last)={disp_first_minus_last:.4f}, "
                f"ticks={len(window_ticks)}, "
                f"✅ RESULT={disp_last_minus_first:.4f}"
            )
            
            # Validate: If time difference is negative or zero, something is wrong
            if time_diff_seconds <= 0:
                logger.warning(
                    f"⚠️ [DISPLACEMENT] {symbol} ({window_name}): "
                    f"Time ordering issue! first_ts={first_tick_ts:.2f}, last_ts={last_tick_ts:.2f}, "
                    f"time_diff={time_diff_seconds:.1f}s. "
                    f"First tick time string: {first_tick_time}, Last tick time string: {last_tick_time}. "
                    f"This means all ticks have the same timestamp - timestamp parsing may have failed!"
                )
                
                # If timestamps are the same, we can't calculate displacement correctly
                # Use price-based sorting as fallback (not ideal, but better than wrong displacement)
                if time_diff_seconds == 0 and len(window_ticks) > 1:
                    logger.warning(
                        f"⚠️ [DISPLACEMENT] {symbol} ({window_name}): "
                        f"All ticks have same timestamp! Using price-based fallback (NOT RECOMMENDED). "
                        f"Tick count: {len(window_ticks)}"
                    )
                    # Sort by price as fallback (ascending)
                    window_ticks_sorted = sorted(window_ticks, key=lambda t: float(t.get('p', 0)))
                    first_price = float(window_ticks_sorted[0].get('p', 0))
                    last_price = float(window_ticks_sorted[-1].get('p', 0))
                    price_displacement = last_price - first_price
                    logger.warning(
                        f"⚠️ [DISPLACEMENT FALLBACK] {symbol} ({window_name}): "
                        f"Using price-based: first={first_price:.4f}, last={last_price:.4f}, "
                        f"disp={price_displacement:.4f} (THIS IS NOT TIME-BASED!)"
                    )
            
            # 2. ADV Fraction
            # Only count volume from REAL TRADES (already filtered above)
            window_volume = sum(float(t.get('s', 0)) for t in window_ticks)
            adv_fraction = window_volume / avg_adv if avg_adv > 0 else 0
            
            # 3. Aggressor Proxy
            aggressor_sum = 0.0
            for tick in window_ticks:
                price = float(tick.get('p', 0))
                bid = float(tick.get('b', 0))
                ask = float(tick.get('a', 0))
                size = float(tick.get('s', 0))
                
                if price > 0 and bid > 0 and ask > 0:
                    if price >= ask:
                        aggressor = 1  # Buyer aggressor
                    elif price <= bid:
                        aggressor = -1  # Seller aggressor
                    else:
                        aggressor = 0  # Mid-spread
                    
                    aggressor_sum += aggressor * size
            
            net_pressure = aggressor_sum / window_volume if window_volume > 0 else 0
            
            # 4. Efficiency
            efficiency = abs(price_displacement) / adv_fraction if adv_fraction > 0 else 0
            
            # 5. Trade Frequency
            # Count only REAL TRADES (already filtered - no bid/ask updates, no pseudo-ticks)
            trade_count = len(window_ticks)  # This is already real_trade_count
            trade_frequency = trade_count / window_minutes if window_minutes > 0 else 0
            
            # Group-relative normalization (if peers provided)
            normalized_displacement = price_displacement
            normalized_pressure = net_pressure
            
            if group_peers and len(group_peers) > 1:
                # Compute median displacement and pressure for group
                peer_displacements = []
                peer_pressures = []
                
                for peer_symbol in group_peers:
                    if peer_symbol == symbol:
                        continue
                    
                    peer_metrics = self._compute_peer_metrics(peer_symbol, window_name, avg_adv)
                    if peer_metrics:
                        peer_displacements.append(peer_metrics.get('price_displacement', 0))
                        peer_pressures.append(peer_metrics.get('net_pressure', 0))
                
                if peer_displacements:
                    peer_displacements.sort()
                    median_displacement = peer_displacements[len(peer_displacements) // 2]
                    normalized_displacement = price_displacement - median_displacement
                
                if peer_pressures:
                    peer_pressures.sort()
                    median_pressure = peer_pressures[len(peer_pressures) // 2]
                    normalized_pressure = net_pressure - median_pressure
            
            # State Classification
            state, confidence = self._classify_state(
                price_displacement=price_displacement,
                normalized_displacement=normalized_displacement,
                adv_fraction=adv_fraction,
                net_pressure=net_pressure,
                normalized_pressure=normalized_pressure,
                efficiency=efficiency,
                trade_frequency=trade_frequency,
                trade_count=trade_count
            )
            
            result = {
                'state': state,
                'confidence': confidence,
                'price_displacement': price_displacement,
                'normalized_displacement': normalized_displacement,
                'adv_fraction': adv_fraction,
                'net_pressure': net_pressure,
                'normalized_pressure': normalized_pressure,
                'efficiency': efficiency,
                'trade_frequency': trade_frequency,
                'window_volume': window_volume,
                'trade_count': trade_count,
                'real_trade_count': real_trade_count,  # Explicit real trade count
                'updated_at': datetime.now().isoformat()
            }
            
            # Cache result
            with self._cache_lock:
                if symbol not in self.results_cache:
                    self.results_cache[symbol] = {}
                self.results_cache[symbol][window_name] = result
            
            return result
        
        except Exception as e:
            logger.error(f"Error computing metrics for {symbol} ({window_name}): {e}", exc_info=True)
            return None
    
    def _compute_peer_metrics(self, symbol: str, window_name: str, avg_adv: float) -> Optional[Dict[str, Any]]:
        """Compute metrics for a peer symbol (for normalization)"""
        try:
            with self._tick_lock:
                if symbol not in self.tick_store or len(self.tick_store[symbol]) == 0:
                    return None
                
                ticks = list(self.tick_store[symbol])
            
            if not ticks:
                return None
            
            window_minutes = self.WINDOWS[window_name]
            window_seconds = window_minutes * 60
            
            # Parse all tick timestamps first (same as compute_metrics)
            tick_times_parsed = []
            for tick in ticks:
                ts = self._parse_timestamp(tick.get('t'))
                if ts:
                    tick_times_parsed.append((ts, tick))
            
            if not tick_times_parsed:
                return None
            
            # Sort by timestamp to find the most recent tick
            tick_times_parsed.sort(key=lambda x: x[0])
            last_print_time = tick_times_parsed[-1][0]
            window_end_time = last_print_time
            window_start_time = window_end_time - window_seconds
            
            # Filter ticks within window - ONLY REAL TRADES (same as compute_metrics)
            window_ticks_with_time = []
            for tick_time, tick in tick_times_parsed:
                if window_start_time <= tick_time <= window_end_time:
                    # Only include real trades: bf=false, price>0, size>0, size<=avg_adv
                    if tick.get('bf', False):
                        continue
                    price = float(tick.get('p', 0))
                    size = float(tick.get('s', 0))
                    if price > 0 and size > 0 and size <= avg_adv:
                        window_ticks_with_time.append((tick_time, tick))
            
            if len(window_ticks_with_time) < 2:
                return None
            
            # Sort by timestamp
            window_ticks_with_time.sort(key=lambda x: x[0])
            window_ticks = [tick for _, tick in window_ticks_with_time]
            
            # window_ticks already sorted by timestamp
            first_price = float(window_ticks[0].get('p', 0))
            last_price = float(window_ticks[-1].get('p', 0))
            price_displacement = last_price - first_price
            
            window_volume = sum(float(t.get('s', 0)) for t in window_ticks)
            
            aggressor_sum = 0.0
            for tick in window_ticks:
                price = float(tick.get('p', 0))
                bid = float(tick.get('b', 0))
                ask = float(tick.get('a', 0))
                size = float(tick.get('s', 0))
                
                if price > 0 and bid > 0 and ask > 0:
                    if price >= ask:
                        aggressor = 1
                    elif price <= bid:
                        aggressor = -1
                    else:
                        aggressor = 0
                    
                    aggressor_sum += aggressor * size
            
            net_pressure = aggressor_sum / window_volume if window_volume > 0 else 0
            
            return {
                'price_displacement': price_displacement,
                'net_pressure': net_pressure
            }
        
        except Exception as e:
            logger.debug(f"Error computing peer metrics for {symbol}: {e}")
            return None
    
    def _classify_state(
        self,
        price_displacement: float,
        normalized_displacement: float,
        adv_fraction: float,
        net_pressure: float,
        normalized_pressure: float,
        efficiency: float,
        trade_frequency: float,
        trade_count: int
    ) -> Tuple[str, float]:
        """
        Classify market state based on metrics.
        
        ILLIQUID SAFE: Only classifies states if sufficient real trades exist.
        This prevents false signals from bid/ask updates and pseudo-ticks.

        Returns:
            (state, confidence) tuple
        """
        # Thresholds (configurable)
        DISPLACEMENT_THRESHOLD = 0.05  # 5 cents
        PRESSURE_THRESHOLD = 0.1  # 10% net pressure
        ADV_FRACTION_THRESHOLD = 0.05  # 5% of ADV
        EFFICIENCY_THRESHOLD = 1.0
        MIN_TRADES_FOR_SIGNAL = 5  # Minimum real trades for any signal
        MIN_TRADES_FOR_ABSORPTION = 10  # Absorption requires more trades (high volume pattern)

        # Use normalized values if available
        disp = normalized_displacement if abs(normalized_displacement) > 0.01 else price_displacement
        pressure = normalized_pressure if abs(normalized_pressure) > 0.01 else net_pressure

        # ILLIQUID CHECK: If too few trades, return NEUTRAL with low confidence
        # This should already be caught in compute_metrics, but double-check here
        if trade_count < MIN_TRADES_FOR_SIGNAL:
            return ('NEUTRAL', 0.1)  # Very low confidence - insufficient data

        # BUYER_DOMINANT: Positive displacement + buyer pressure + volume
        if (disp > DISPLACEMENT_THRESHOLD and
            pressure > PRESSURE_THRESHOLD and
            adv_fraction > ADV_FRACTION_THRESHOLD):
            confidence = min(1.0, (abs(disp) / DISPLACEMENT_THRESHOLD) * 0.5 +
                            (abs(pressure) / PRESSURE_THRESHOLD) * 0.3 +
                            (adv_fraction / ADV_FRACTION_THRESHOLD) * 0.2)
            return ('BUYER_DOMINANT', confidence)

        # SELLER_DOMINANT: Negative displacement + seller pressure + volume
        if (disp < -DISPLACEMENT_THRESHOLD and
            pressure < -PRESSURE_THRESHOLD and
            adv_fraction > ADV_FRACTION_THRESHOLD):
            confidence = min(1.0, (abs(disp) / DISPLACEMENT_THRESHOLD) * 0.5 +
                            (abs(pressure) / PRESSURE_THRESHOLD) * 0.3 +
                            (adv_fraction / ADV_FRACTION_THRESHOLD) * 0.2)
            return ('SELLER_DOMINANT', confidence)

        # SELLER_VACUUM: Negative displacement but low volume (sellers exhausted)
        if (disp < -DISPLACEMENT_THRESHOLD and
            adv_fraction < ADV_FRACTION_THRESHOLD * 0.5):
            confidence = min(1.0, (abs(disp) / DISPLACEMENT_THRESHOLD) * 0.6 +
                            (1.0 - adv_fraction / (ADV_FRACTION_THRESHOLD * 0.5)) * 0.4)
            return ('SELLER_VACUUM', confidence)

        # ABSORPTION: High volume but low displacement (liquidity absorbing)
        # CRITICAL: Requires minimum trade count (illiquid products can't have absorption)
        if (trade_count >= MIN_TRADES_FOR_ABSORPTION and
            abs(disp) < DISPLACEMENT_THRESHOLD * 0.5 and
            adv_fraction > ADV_FRACTION_THRESHOLD and
            efficiency < EFFICIENCY_THRESHOLD):
            confidence = min(1.0, (adv_fraction / ADV_FRACTION_THRESHOLD) * 0.5 +
                            (1.0 - efficiency / EFFICIENCY_THRESHOLD) * 0.5)
            return ('ABSORPTION', confidence)

        # NEUTRAL: Default state
        confidence = 0.5  # Medium confidence for neutral
        return ('NEUTRAL', confidence)
    
    def _parse_timestamp(self, ts: Any) -> Optional[float]:
        """
        Parse timestamp from various formats.
        
        Hammer Pro getTicks returns ISO 8601 format strings like:
        - "2020-08-12T11:00:07.500"
        - "2020-08-12T19:40:45.686"
        """
        if ts is None:
            return None
        
        try:
            # ISO 8601 string (Hammer Pro format: "2020-08-12T11:00:07.500")
            if isinstance(ts, str):
                # Try ISO format first (most common from Hammer Pro)
                if 'T' in ts:
                    try:
                        # Handle timezone (Z, +00:00, -05:00)
                        if ts.endswith('Z'):
                            # UTC timezone - remove Z and parse
                            ts_no_z = ts[:-1]
                            if '.' in ts_no_z:
                                # Has microseconds
                                base, microsec = ts_no_z.split('.')
                                dt = datetime.strptime(base, '%Y-%m-%dT%H:%M:%S')
                                dt = dt.replace(microsecond=int(microsec[:6].ljust(6, '0')))
                            else:
                                dt = datetime.strptime(ts_no_z, '%Y-%m-%dT%H:%M:%S')
                            # Make timezone-aware (UTC) and return timestamp
                            dt_utc = dt.replace(tzinfo=timezone.utc)
                            return dt_utc.timestamp()
                        elif '+' in ts or (ts.count('-') > 2 and ':' in ts[-6:]):
                            # Has timezone offset (e.g., "+00:00" or "-05:00")
                            dt = datetime.fromisoformat(ts)
                            return dt.timestamp()
                        else:
                            # No timezone - Hammer Pro documentation says "All timestamps will be in UTC"
                            # Parse as UTC (naive datetime, but we know it's UTC)
                            if '.' in ts:
                                # Has microseconds (e.g., "2020-08-12T11:00:07.500")
                                parts = ts.split('.')
                                base = parts[0]
                                microsec_str = parts[1][:6].ljust(6, '0')  # Pad to 6 digits
                                dt = datetime.strptime(base, '%Y-%m-%dT%H:%M:%S')
                                dt = dt.replace(microsecond=int(microsec_str))
                            else:
                                # No microseconds
                                dt = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
                            
                            # Hammer Pro timestamps are UTC per documentation
                            # Make it timezone-aware (UTC) and return timestamp
                            dt_utc = dt.replace(tzinfo=timezone.utc)
                            return dt_utc.timestamp()
                    except (ValueError, AttributeError) as e:
                        # Try fromisoformat as fallback (Python 3.7+)
                        try:
                            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                            return dt.timestamp()
                        except Exception:
                            logger.debug(f"Failed to parse ISO timestamp {ts}: {e}")
                            return None
                
                # Unix timestamp (string) - check if it's a number
                ts_stripped = ts.strip().replace('.', '').replace('-', '')
                if ts_stripped.isdigit() or (ts_stripped[1:].isdigit() if ts_stripped.startswith('-') else False):
                    ts_float = float(ts)
                    # If in milliseconds, convert to seconds
                    if ts_float > 1e10:
                        return ts_float / 1000.0
                    return ts_float
            
            # Unix timestamp (number)
            if isinstance(ts, (int, float)):
                # If in milliseconds, convert to seconds
                if ts > 1e10:
                    return ts / 1000.0
                return float(ts)
            
            return None
        
        except Exception as e:
            logger.debug(f"Error parsing timestamp {ts} (type: {type(ts)}): {e}")
            return None
    
    def get_cached_result(self, symbol: str, window_name: str) -> Optional[Dict[str, Any]]:
        """Get cached result for a symbol and window"""
        with self._cache_lock:
            if symbol in self.results_cache and window_name in self.results_cache[symbol]:
                return self.results_cache[symbol][window_name]
            return None


# Global instance
_decision_helper_engine: Optional[DecisionHelperEngine] = None
_engine_lock = threading.Lock()


def get_decision_helper_engine() -> DecisionHelperEngine:
    """Get global DecisionHelperEngine instance"""
    global _decision_helper_engine
    
    with _engine_lock:
        if _decision_helper_engine is None:
            _decision_helper_engine = DecisionHelperEngine()
        return _decision_helper_engine


