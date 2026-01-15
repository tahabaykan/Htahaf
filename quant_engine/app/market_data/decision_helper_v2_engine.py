"""
DecisionHelperV2 - Microstructure-aware decision engine for illiquid preferred/CEF instruments.

Key differences from DecisionHelper:
- Uses MODAL price flow (GRPAN1) instead of first/last trade displacement
- Designed for illiquid instruments with sparse trading
- Ignores single outlier prints
- Uses rolling windows: pan_10m, pan_30m, pan_1h, pan_3h, pan_1d
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from collections import deque, defaultdict
from datetime import datetime, timezone
import threading
import time

logger = logging.getLogger(__name__)


class DecisionHelperV2Engine:
    """
    Microstructure-aware decision engine using modal price flow.
    """
    
    WINDOWS = {
        'pan_10m': 10,   # 10 minutes
        'pan_30m': 30,   # 30 minutes
        'pan_1h': 60,    # 1 hour
        'pan_3h': 180,   # 3 hours
        'pan_1d': 1440,  # 1 day (trading hours)
    }
    
    MIN_TICKS_PER_WINDOW = 8
    MIN_LOT_SIZE = 10
    GRPAN_BIN_RANGE = 0.03  # ±0.03 USD
    GRPAN_MIN_SPREAD = 0.06  # Minimum distance between GRPAN1 and GRPAN2
    GRPAN_OPTIMAL_SPREAD = 0.30  # Optimal spread for SRPAN
    
    def __init__(self):
        """Initialize DecisionHelperV2Engine"""
        self.tick_store: Dict[str, deque] = {}  # symbol -> deque of ticks
        self._tick_lock = threading.Lock()
        self.results_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}  # symbol -> window -> result
        self._cache_lock = threading.Lock()
        
        logger.info("DecisionHelperV2Engine initialized (modal price flow)")
    
    def add_tick(self, symbol: str, tick: Dict[str, Any]):
        """
        Add a tick to the store.
        
        Filters:
        - bf == true → ignore
        - size < 10 lots → ignore
        """
        # Filter: ignore backfilled ticks
        if tick.get('bf', False):
            return
        
        # Filter: ignore small prints (< 10 lots)
        size = float(tick.get('s', 0))
        if size < self.MIN_LOT_SIZE:
            return
        
        # Filter: must have valid price
        price = float(tick.get('p', 0))
        if price <= 0:
            return
        
        with self._tick_lock:
            if symbol not in self.tick_store:
                self.tick_store[symbol] = deque(maxlen=10000)  # Keep last 10k ticks
            
            # Store tick with timestamp
            tick_with_ts = {
                't': tick.get('t'),  # ISO 8601 timestamp
                'p': price,
                's': size,
                'b': float(tick.get('b', 0)),
                'a': float(tick.get('a', 0)),
            }
            self.tick_store[symbol].append(tick_with_ts)
    
    def _parse_timestamp(self, ts: Any) -> Optional[float]:
        """Parse timestamp from ISO 8601 format"""
        if ts is None:
            return None
        
        try:
            if isinstance(ts, str):
                if 'T' in ts:
                    # ISO 8601 format
                    if ts.endswith('Z'):
                        ts_no_z = ts[:-1]
                        if '.' in ts_no_z:
                            base, microsec = ts_no_z.split('.')
                            dt = datetime.strptime(base, '%Y-%m-%dT%H:%M:%S')
                            dt = dt.replace(microsecond=int(microsec[:6].ljust(6, '0')))
                        else:
                            dt = datetime.strptime(ts_no_z, '%Y-%m-%dT%H:%M:%S')
                        dt_utc = dt.replace(tzinfo=timezone.utc)
                        return dt_utc.timestamp()
                    elif '+' in ts or (ts.count('-') > 2 and ':' in ts[-6:]):
                        dt = datetime.fromisoformat(ts)
                        return dt.timestamp()
                    else:
                        # No timezone - assume UTC (Hammer Pro timestamps are UTC)
                        if '.' in ts:
                            parts = ts.split('.')
                            base = parts[0]
                            microsec_str = parts[1][:6].ljust(6, '0')
                            dt = datetime.strptime(base, '%Y-%m-%dT%H:%M:%S')
                            dt = dt.replace(microsecond=int(microsec_str))
                        else:
                            dt = datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
                        dt_utc = dt.replace(tzinfo=timezone.utc)
                        return dt_utc.timestamp()
            
            if isinstance(ts, (int, float)):
                if ts > 1e10:
                    return ts / 1000.0
                return float(ts)
            
            return None
        except Exception as e:
            logger.debug(f"Error parsing timestamp {ts}: {e}")
            return None
    
    def _compute_grpan(self, ticks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Compute GRPAN1 and GRPAN2 for a set of ticks.
        
        Returns:
            {
                'grpan1': price,
                'grpan1_conf': confidence (0-1),
                'grpan2': price or None,
                'grpan2_conf': confidence (0-1) or None,
                'total_weight': float
            }
        """
        if len(ticks) < self.MIN_TICKS_PER_WINDOW:
            return None
        
        # Weighting: size >= 100 lots → 1.0, else 0.25
        price_weights = defaultdict(float)
        total_weight = 0.0
        
        for tick in ticks:
            price = float(tick.get('p', 0))
            size = float(tick.get('s', 0))
            
            if price <= 0 or size < self.MIN_LOT_SIZE:
                continue
            
            # Weight calculation
            weight = 1.0 if size >= 100 else 0.25
            price_weights[price] += weight
            total_weight += weight
        
        if total_weight == 0:
            return None
        
        # GRPAN1: Price with highest weighted density
        if not price_weights:
            return None
        
        grpan1 = max(price_weights.keys(), key=lambda p: price_weights[p])
        
        # GRPAN1 confidence: ±0.03 range
        grpan1_range_weight = sum(
            w for p, w in price_weights.items()
            if abs(p - grpan1) <= self.GRPAN_BIN_RANGE
        )
        grpan1_conf = grpan1_range_weight / total_weight
        
        # GRPAN2: Must be at least 0.06 USD away from GRPAN1
        excluded_prices = {
            p: w for p, w in price_weights.items()
            if abs(p - grpan1) >= self.GRPAN_MIN_SPREAD
        }
        
        grpan2 = None
        grpan2_conf = None
        
        if excluded_prices:
            grpan2 = max(excluded_prices.keys(), key=lambda p: excluded_prices[p])
            grpan2_range_weight = sum(
                w for p, w in price_weights.items()
                if abs(p - grpan2) <= self.GRPAN_BIN_RANGE and abs(p - grpan1) >= self.GRPAN_MIN_SPREAD
            )
            grpan2_conf = grpan2_range_weight / total_weight
        
        return {
            'grpan1': grpan1,
            'grpan1_conf': grpan1_conf,
            'grpan2': grpan2,
            'grpan2_conf': grpan2_conf,
            'total_weight': total_weight
        }
    
    def _compute_rwvap(self, ticks: List[Dict[str, Any]], avg_adv: float) -> Optional[float]:
        """
        Compute Robust VWAP.
        
        Excludes prints where size > AVG_ADV
        """
        if not ticks or avg_adv <= 0:
            return None
        
        total_volume = 0.0
        weighted_price_sum = 0.0
        
        for tick in ticks:
            price = float(tick.get('p', 0))
            size = float(tick.get('s', 0))
            
            if price <= 0 or size <= 0:
                continue
            
            # Exclude extreme prints
            if size > avg_adv:
                continue
            
            total_volume += size
            weighted_price_sum += price * size
        
        if total_volume == 0:
            return None
        
        return weighted_price_sum / total_volume
    
    def compute_metrics(
        self,
        symbol: str,
        window_name: str,
        avg_adv: float
    ) -> Optional[Dict[str, Any]]:
        """
        Compute DecisionHelperV2 metrics for a symbol and window.
        
        Returns:
            Dict with all metrics and state classification
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
            
            # Parse all tick timestamps
            tick_times_parsed = []
            for tick in ticks:
                ts = self._parse_timestamp(tick.get('t'))
                if ts:
                    tick_times_parsed.append((ts, tick))
            
            if not tick_times_parsed:
                return None
            
            # Sort by timestamp
            tick_times_parsed.sort(key=lambda x: x[0])
            
            # Use last print time as window end
            last_print_time = tick_times_parsed[-1][0]
            window_end_time = last_print_time
            window_start_time = window_end_time - window_seconds
            
            # Filter ticks within window
            window_ticks = []
            for tick_time, tick in tick_times_parsed:
                if window_start_time <= tick_time <= window_end_time:
                    window_ticks.append(tick)
            
            if len(window_ticks) < self.MIN_TICKS_PER_WINDOW:
                return {
                    "state": "NO_SIGNAL_ILLIQUID",
                    "reason": f"Insufficient ticks: {len(window_ticks)} < {self.MIN_TICKS_PER_WINDOW}",
                    "tick_count": len(window_ticks),
                    "updated_at": datetime.now().isoformat()
                }
            
            # Split window into start and end halves for modal displacement
            mid_time = window_start_time + (window_end_time - window_start_time) / 2
            start_ticks = [tick for tick_time, tick in tick_times_parsed
                          if window_start_time <= tick_time <= mid_time]
            end_ticks = [tick for tick_time, tick in tick_times_parsed
                        if mid_time < tick_time <= window_end_time]
            
            # Compute GRPAN for start and end
            grpan_start = self._compute_grpan(start_ticks) if len(start_ticks) >= self.MIN_TICKS_PER_WINDOW // 2 else None
            grpan_end = self._compute_grpan(end_ticks) if len(end_ticks) >= self.MIN_TICKS_PER_WINDOW // 2 else None
            grpan_full = self._compute_grpan(window_ticks)
            
            if not grpan_full:
                return {
                    "state": "NO_SIGNAL_ILLIQUID",
                    "reason": "Could not compute GRPAN",
                    "updated_at": datetime.now().isoformat()
                }
            
            # Modal Displacement: GRPAN1_end - GRPAN1_start
            if grpan_start and grpan_end:
                modal_displacement = grpan_end['grpan1'] - grpan_start['grpan1']
                grpan1_start = grpan_start['grpan1']
                grpan1_end = grpan_end['grpan1']
            else:
                # Fallback: use first and last ticks if halves don't have enough data
                modal_displacement = 0.0
                grpan1_start = grpan_full['grpan1']
                grpan1_end = grpan_full['grpan1']
            
            # RWVAP
            rwvap = self._compute_rwvap(window_ticks, avg_adv)
            rwvap_diff = (grpan1_end - rwvap) if rwvap else 0.0
            
            # ADV Fraction
            window_volume = sum(float(t.get('s', 0)) for t in window_ticks)
            adv_fraction = window_volume / avg_adv if avg_adv > 0 else 0.0
            
            # Flow Efficiency
            flow_efficiency = abs(modal_displacement) / max(adv_fraction, 0.01)
            
            # SRPAN Score
            srpan_score = 0.0
            if grpan_full['grpan2'] is not None:
                spread = abs(grpan_full['grpan2'] - grpan_full['grpan1'])
                
                # Balance Score (60%)
                conf_diff = abs(grpan_full['grpan1_conf'] - grpan_full['grpan2_conf'])
                balance_score = max(0, 100 - (conf_diff * 100))
                
                # Total Concentration (15%)
                total_conf = grpan_full['grpan1_conf'] + grpan_full['grpan2_conf']
                total_score = min(100, total_conf * 100)
                
                # Spread Score (25%)
                if spread >= self.GRPAN_OPTIMAL_SPREAD:
                    spread_score = 100
                elif spread <= self.GRPAN_MIN_SPREAD:
                    spread_score = 0
                else:
                    spread_score = ((spread - self.GRPAN_MIN_SPREAD) / 
                                   (self.GRPAN_OPTIMAL_SPREAD - self.GRPAN_MIN_SPREAD)) * 100
                
                srpan_score = (0.60 * balance_score) + (0.15 * total_score) + (0.25 * spread_score)
            
            # Outlier Print Flag
            max_single_print = max((float(t.get('s', 0)) for t in window_ticks), default=0.0)
            outlier_ratio = max_single_print / window_volume if window_volume > 0 else 0.0
            outlier_flag = "SINGLE_PRINT_EVENT" if outlier_ratio > 0.40 else None
            
            # Normalization
            d_norm = max(-1.0, min(1.0, modal_displacement / 0.30))
            r_norm = max(-1.0, min(1.0, rwvap_diff / 0.30))
            v_norm = max(0.0, min(1.0, adv_fraction / 1.0))
            e_norm = max(0.0, min(1.0, flow_efficiency / 3.0))
            s_norm = srpan_score / 100.0
            
            # Net Pressure (simplified - can be enhanced)
            net_pressure = 0.0  # TODO: Implement aggressor-based pressure
            
            # Real Flow Score (RFS)
            rfs = (0.30 * d_norm +
                   0.20 * r_norm +
                   0.20 * s_norm * (1 if d_norm >= 0 else -1) +
                   0.15 * e_norm * (1 if d_norm >= 0 else -1) +
                   0.15 * (1 if net_pressure > 0 else -1 if net_pressure < 0 else 0))
            
            # State Classification
            if rfs > 0.40:
                state = "BUYER_DOMINANT"
            elif rfs < -0.40:
                state = "SELLER_DOMINANT"
            elif abs(modal_displacement) < 0.03 and adv_fraction > 0.10:
                state = "ABSORPTION"
            elif abs(modal_displacement) > 0.10 and adv_fraction < 0.05:
                state = "VACUUM"
            else:
                state = "NEUTRAL"
            
            result = {
                'grpan1_start': grpan1_start,
                'grpan1_end': grpan1_end,
                'modal_displacement': modal_displacement,
                'rwvap': rwvap,
                'rwvap_diff': rwvap_diff,
                'adv_fraction': adv_fraction,
                'flow_efficiency': flow_efficiency,
                'srpan_score': srpan_score,
                'rfs': rfs,
                'state': state,
                'flags': [outlier_flag] if outlier_flag else [],
                'grpan1_conf': grpan_full['grpan1_conf'],
                'grpan2': grpan_full['grpan2'],
                'grpan2_conf': grpan_full['grpan2_conf'],
                'outlier_ratio': outlier_ratio,
                'tick_count': len(window_ticks),
                'window_volume': window_volume,
                'updated_at': datetime.now().isoformat()
            }
            
            # Cache result
            with self._cache_lock:
                if symbol not in self.results_cache:
                    self.results_cache[symbol] = {}
                self.results_cache[symbol][window_name] = result
            
            return result
        
        except Exception as e:
            logger.error(f"Error computing DecisionHelperV2 metrics for {symbol} ({window_name}): {e}", exc_info=True)
            return None


# Singleton instance
_v2_engine_instance: Optional[DecisionHelperV2Engine] = None
_v2_engine_lock = threading.Lock()


def get_decision_helper_v2_engine() -> DecisionHelperV2Engine:
    """Get singleton DecisionHelperV2Engine instance"""
    global _v2_engine_instance
    if _v2_engine_instance is None:
        with _v2_engine_lock:
            if _v2_engine_instance is None:
                _v2_engine_instance = DecisionHelperV2Engine()
    return _v2_engine_instance


