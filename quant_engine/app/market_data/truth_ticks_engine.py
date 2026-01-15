"""
Truth Ticks Engine

Designed for illiquid preferred stocks.
Identifies REAL price migration using volume-weighted truth prints,
NOT last/first trade prices.

Key Features:
- TruthTick filtering (size >= 20, FNRA rules)
- Volume-Averaged Levels (Volav) - volume concentration
- Volav1_start/end displacement - real price migration
- Top truth volume events
"""

from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta
import threading
import time
import math

from app.core.logger import logger
from app.market_data.trading_calendar import get_trading_calendar


import yaml
from pathlib import Path

class TruthTicksEngine:
    """
    Truth Ticks Engine for illiquid preferred stocks.
    
    Analyzes REAL price migration using volume-weighted truth prints.
    Uses Weighted Print Realism model instead of venue-based filtering.
    """
    
    # Configuration defaults (overridden by yaml)
    BUCKET_SIZE = 0.01
    MIN_SIZE = 19
    
    # Timeframe constants
    TIMEFRAMES = {
        'TF_4H': 4 * 60 * 60,
        'TF_1D': 24 * 60 * 60,
        'TF_3D': 3 * 24 * 60 * 60,
        'TF_5D': 5 * 24 * 60 * 60
    }
    
    def __init__(self):
        """Initialize Truth Ticks Engine"""
        # Tick store: {symbol: deque(maxlen=200)}
        self.tick_store: Dict[str, deque] = {}
        self._tick_lock = threading.Lock()
        
        # Results cache
        self.results_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()
        
        # Load configuration
        self.config = self._load_config()
        self.MIN_SIZE = self.config.get('print_realism', {}).get('min_lot_ignore', 20)
        
        # Saliency & Thresholds
        self.MIN_TICKS_FOR_SUFFICIENT_DATA = 15
        self.REQUIRED_TRUTH_TICKS = 100
        self.MIN_TRUTH_TICKS = 15
        self.FNRA_ALLOWED_SIZES = {50, 100, 200, 300, 400, 500, 1000, 2000, 5000}
        self.VOLAV_MOVE_THRESHOLD = 0.06
        self.HIGH_VOLUME_THRESHOLD = 0.8
        self.LOW_VOLUME_THRESHOLD = 0.2
        self.DISPLACEMENT_THRESHOLD = 0.4
        self.FINRA_DOMINANT_THRESHOLD = 0.5
        self.FLAT_EPSILON = 1e-6
        
        logger.info("TruthTicksEngine initialized (Weighted Print Realism)")
        
    def _load_config(self) -> Dict[str, Any]:
        """Load microstructure rules from yaml"""
        try:
            # Path: quant_engine/app/config/microstructure_rules.yaml
            # current file: quant_engine/app/market_data/truth_ticks_engine.py
            config_path = Path(__file__).parent.parent / "config" / "microstructure_rules.yaml"
            if config_path.exists():
                with open(config_path, "r") as f:
                    return yaml.safe_load(f)
            else:
                logger.warning(f"Config not found at {config_path}, using defaults")
                return {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def add_tick(self, symbol: str, tick: Dict[str, Any]):
        """
        Add a trade print to the engine.
        
        Args:
            symbol: Symbol name (display format, e.g., "CIM PRB")
            tick: Trade print dict with fields:
                - timestamp (ts or timeStamp)
                - price (float)
                - size (int or float, lots)
                - exch (string: FNRA, NYSE, ARCA, etc.)
        """
        try:
            with self._tick_lock:
                if symbol not in self.tick_store:
                    self.tick_store[symbol] = deque(maxlen=200)
                
                # Normalize tick data
                normalized_tick = self._normalize_tick(tick)
                if normalized_tick:
                    self.tick_store[symbol].append(normalized_tick)
                    
        except Exception as e:
            logger.error(f"Error adding tick for {symbol}: {e}", exc_info=True)
    
    def _normalize_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize tick data to standard format.
        
        Returns:
            Normalized tick dict or None if invalid
        """
        try:
            # Extract timestamp
            timestamp = tick.get('ts') or tick.get('timeStamp') or tick.get('time')
            if timestamp is None:
                return None
            
            # Parse timestamp to float (unix timestamp)
            if isinstance(timestamp, str):
                # Try to parse ISO format or other formats
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp = dt.timestamp()
                except:
                    # Fallback: use current time
                    timestamp = time.time()
            elif isinstance(timestamp, (int, float)):
                timestamp = float(timestamp)
            else:
                return None
            
            # Extract price
            price = tick.get('price')
            if price is None:
                return None
            try:
                price = float(price)
                if price <= 0:
                    return None
            except (ValueError, TypeError):
                return None
            
            # Extract size
            size = tick.get('size')
            if size is None:
                return None
            try:
                size = float(size)
                if size <= 0:
                    return None
            except (ValueError, TypeError):
                return None
            
            # Extract exchange
            exch = tick.get('exch') or tick.get('exchange') or tick.get('venue', '')
            if not exch:
                exch = 'UNKNOWN'
            
            return {
                'ts': timestamp,
                'price': price,
                'size': size,
                'exch': str(exch).upper()
            }
            
        except Exception as e:
            logger.debug(f"Error normalizing tick: {e}")
            return None
    
    def calculate_print_weight(self, size: float, venue: str = 'UNKNOWN') -> float:
        """
        Calculate realism weight based on Venue Policy:
        - Non-FNRA venues (EDGX, ARCA, etc.) -> 1.0
        - FNRA + 100/200 lot -> 1.0
        - FNRA + 300-1000 lot -> 0.4
        - FNRA + irregular -> 0.2
        - < 20 lot -> 0.0 (ignore)
        """
        if size < 20:
            return 0.0

        venue_upper = str(venue).upper()
        
        # FNRA dışındaki TÜM print’ler GERÇEKTİR (1.0)
        # Hammer historical 'getTicks''te borsa gelmezse 'UNKNOWN' olur. 
        # Eğer venue biliniyorsa ve FNRA değilse tam ağırlık veriyoruz.
        if venue_upper != 'FNRA' and venue_upper != 'UNKNOWN' and venue_upper != '':
            return 1.0

        # FNRA veya UNKNOWN durumunda lot size kuralları geçerli
        weights = self.config.get('print_realism', {}).get('weights', {
            'lot_100_200': 1.0,
            'round_large': 0.4,
            'irregular': 0.2
        })
        
        # Exact 100 or 200
        if size == 100 or size == 200:
            return weights.get('lot_100_200', 1.0)
            
        # Round large multiples of 100 (>= 300)
        if size >= 300 and size % 100 == 0:
             return weights.get('round_large', 0.4)
             
        # All others
        return weights.get('irregular', 0.2)

    def is_truth_tick(self, tick: Dict[str, Any]) -> bool:
        """
        Check if a tick is valid for analysis (size >= MIN_SIZE).
        Venue-based filtering is REMOVED in favor of weighted realism.
        """
        try:
            size = tick.get('size', 0)
            return size >= self.MIN_SIZE
        except Exception:
            return False
    
    def filter_truth_ticks(self, ticks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter ticks to get only valid ticks (size >= 20).
        """
        truth_ticks = [tick for tick in ticks if self.is_truth_tick(tick)]
        truth_ticks.sort(key=lambda x: x.get('ts', 0))
        return truth_ticks
    
    def bucket_size(self, avg_adv: float) -> float:
        """
        Calculate bucket size based on avg_adv.
        Bucket size determines how close prices can be to be grouped together.
        
        Args:
            avg_adv: Average Daily Volume
            
        Returns:
            Bucket size in USD
        """
        if avg_adv >= 100000:
            return 0.03
        elif avg_adv >= 80000:
            return 0.03
        elif avg_adv >= 50000:
            return 0.05
        elif avg_adv >= 30000:
            return 0.05
        elif avg_adv >= 20000:
            return 0.05
        elif avg_adv >= 10000:
            return 0.07
        elif avg_adv >= 3000:
            return 0.09
        else:
            return 0.09
    
    def min_volav_gap(self, avg_adv: float) -> float:
        """
        Calculate minimum Volav gap based on avg_adv.
        
        Args:
            avg_adv: Average Daily Volume
            
        Returns:
            Minimum gap in USD
        """
        if avg_adv >= 100000:
            return 0.03
        elif avg_adv >= 80000:
            return 0.04
        elif avg_adv >= 50000:
            return 0.05
        elif avg_adv >= 30000:
            return 0.06
        elif avg_adv >= 20000:
            return 0.07
        elif avg_adv >= 10000:
            return 0.09
        elif avg_adv >= 3000:
            return 0.11
        else:
            return 0.15
    
    def compute_volav_levels(
        self,
        truth_ticks: List[Dict[str, Any]],
        top_n: int = 4,
        avg_adv: float = 0.0,
        return_all_buckets: bool = False
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Compute Volume-Averaged Levels (Volav) using WEIGHTED volume.
        """
        if not truth_ticks:
            return [], []
        
        # Get dynamic bucket size and min gap based on avg_adv
        dynamic_bucket_size = self.bucket_size(avg_adv)
        min_gap = self.min_volav_gap(avg_adv) if avg_adv > 0 else 0.05
        merge_threshold = min_gap * 0.9
        
        # MM-Anchor minimum gap
        MM_ANCHOR_MIN_GAP = 0.06
        
        # Step 1: Bucket aggregation
        bucket_volume: Dict[float, float] = defaultdict(float)
        bucket_price_sum: Dict[float, float] = defaultdict(float)
        bucket_tick_count: Dict[float, int] = defaultdict(int)
        
        for tick in truth_ticks:
            price = tick.get('price', 0)
            size = tick.get('size', 0)
            
            if price <= 0 or size <= 0:
                continue
            
            # Weighted volume
            weight = self.calculate_print_weight(size)
            weighted_size = size * weight
            
            if weighted_size <= 0:
                continue
            
            # Bucket key: round to dynamic bucket_size
            bucket_key = round(price / dynamic_bucket_size) * dynamic_bucket_size
            
            # Aggregate by WEIGHTED volume
            bucket_volume[bucket_key] += weighted_size
            bucket_price_sum[bucket_key] += price * weighted_size
            bucket_tick_count[bucket_key] += 1
        
        if not bucket_volume:
            return [], []
        
        # Calculate bucket VWAP for each bucket
        bucket_vwap: Dict[float, float] = {}
        total_volume = sum(bucket_volume.values())
        
        for bucket_key, volume in bucket_volume.items():
            price_sum = bucket_price_sum[bucket_key]
            bucket_vwap[bucket_key] = price_sum / volume if volume > 0 else bucket_key
        
        # Build all buckets list (for debugging)
        all_buckets = []
        for bucket_key, volume in bucket_volume.items():
            all_buckets.append({
                'bucket_key': bucket_key,
                'price': bucket_vwap[bucket_key],
                'volume': volume,
                'tick_count': bucket_tick_count[bucket_key],
                'pct_of_truth_volume': (volume / total_volume * 100) if total_volume > 0 else 0
            })
        
        # Sort all buckets by volume descending
        all_buckets.sort(key=lambda x: x['volume'], reverse=True)
        
        # Step 2: Build Volav levels with range-based clustering and merging
        volav_levels = []
        half_bucket = dynamic_bucket_size / 2.0
        
        for bucket in all_buckets:
            if len(volav_levels) >= top_n:
                break
            
            bucket_center = bucket['price']
            bucket_range_min = bucket_center - half_bucket
            bucket_range_max = bucket_center + half_bucket
            
            # Find all ticks within this Volav range (center ± bucket_size/2)
            range_ticks = [
                tick for tick in truth_ticks
                if bucket_range_min <= tick.get('price', 0) <= bucket_range_max
            ]
            
            if not range_ticks:
                continue
            
            # Calculate VWAP and volume for this range (WEIGHTED)
            range_volume = 0.0
            range_price_sum = 0.0
            range_ticks_filtered = []
            
            for tick in range_ticks:
                size = tick.get('size', 0)
                price = tick.get('price', 0)
                weight = self.calculate_print_weight(size)
                weighted_size = size * weight
                
                if weighted_size > 0:
                     range_volume += weighted_size
                     range_price_sum += price * weighted_size
                     range_ticks_filtered.append(tick)
            
            range_vwap = range_price_sum / range_volume if range_volume > 0 else bucket_center
            range_tick_count = len(range_ticks_filtered)
            range_last_ts = max([tick.get('ts', 0) for tick in range_ticks_filtered]) if range_ticks_filtered else 0
            
            # Check if this Volav should be merged with existing Volavs
            merged = False
            merge_target_idx = None
            
            for idx, existing_volav in enumerate(volav_levels):
                existing_center = existing_volav['price']
                gap = abs(range_vwap - existing_center)
                
                if gap < merge_threshold:
                    # Merge: Combine ranges and recalculate VWAP
                    existing_range_min = existing_volav.get('range_min', existing_center - half_bucket)
                    existing_range_max = existing_volav.get('range_max', existing_center + half_bucket)
                    
                    # Combined range
                    combined_range_min = min(existing_range_min, bucket_range_min)
                    combined_range_max = max(existing_range_max, bucket_range_max)
                    
                    # Find all ticks in combined range
                    combined_ticks = [
                        tick for tick in truth_ticks
                        if combined_range_min <= tick.get('price', 0) <= combined_range_max
                    ]
                    
                    if combined_ticks:
                        combined_volume = 0.0
                        combined_price_sum = 0.0
                        combined_filtered_ticks = []
                        
                        for tick in combined_ticks:
                            size = tick.get('size', 0)
                            price = tick.get('price', 0)
                            weight = self.calculate_print_weight(size)
                            weighted_size = size * weight
                            
                            if weighted_size > 0:
                                combined_volume += weighted_size
                                combined_price_sum += price * weighted_size
                                combined_filtered_ticks.append(tick)
                            
                        combined_vwap = combined_price_sum / combined_volume if combined_volume > 0 else existing_center
                        combined_tick_count = len(combined_filtered_ticks)
                        combined_pct = (combined_volume / total_volume * 100) if total_volume > 0 else 0
                        combined_last_ts = max([tick.get('ts', 0) for tick in combined_ticks]) if combined_ticks else max(existing_volav.get('last_print_ts', 0), range_last_ts)
                        
                        # Update existing Volav with merged data
                        existing_volav['price'] = combined_vwap
                        existing_volav['volume'] = combined_volume
                        existing_volav['tick_count'] = combined_tick_count
                        existing_volav['pct_of_truth_volume'] = combined_pct
                        existing_volav['range_min'] = combined_range_min
                        existing_volav['range_max'] = combined_range_max
                        existing_volav['last_print_ts'] = combined_last_ts
                        existing_volav['merged'] = True
                        # Keep bucket_key if it exists, otherwise add from current bucket
                        if 'bucket_key' not in existing_volav:
                            existing_volav['bucket_key'] = bucket['bucket_key']
                        
                        # After merging, check if merged Volav should merge with other Volavs
                        # (because the range expanded)
                        merge_target_idx = idx
                    
                    merged = True
                    break
                elif gap >= min_gap:
                    # Definitely separate Volav (gap >= min_gap)
                    # Continue to next existing Volav
                    continue
                # else: merge_threshold <= gap < min_gap → Separate Volav (intermediate zone)
            
            # If merged, check for cascading merges (merged Volav might now be close to others)
            if merged and merge_target_idx is not None:
                merged_volav = volav_levels[merge_target_idx]
                merged_center = merged_volav['price']
                
                # Check other Volavs (except the one we just merged into)
                for other_idx, other_volav in enumerate(volav_levels):
                    if other_idx == merge_target_idx:
                        continue
                    
                    other_center = other_volav['price']
                    gap = abs(merged_center - other_center)
                    
                    if gap < merge_threshold:
                        # Cascade merge: Merge the other Volav into the merged one
                        other_range_min = other_volav.get('range_min', other_center - half_bucket)
                        other_range_max = other_volav.get('range_max', other_center + half_bucket)
                        
                        # Combined range
                        final_range_min = min(merged_volav['range_min'], other_range_min)
                        final_range_max = max(merged_volav['range_max'], other_range_max)
                        
                        # Find all ticks in final combined range
                        final_ticks = [
                            tick for tick in truth_ticks
                            if final_range_min <= tick.get('price', 0) <= final_range_max
                        ]
                        
                        if final_ticks:
                            final_volume = 0.0
                            final_price_sum = 0.0
                            final_filtered_ticks = []
                            
                            for tick in final_ticks:
                                size = tick.get('size', 0)
                                price = tick.get('price', 0)
                                weight = self.calculate_print_weight(size)
                                weighted_size = size * weight
                                
                                if weighted_size > 0:
                                    final_volume += weighted_size
                                    final_price_sum += price * weighted_size
                                    final_filtered_ticks.append(tick)
                            
                            final_vwap = final_price_sum / final_volume if final_volume > 0 else merged_center
                            final_tick_count = len(final_filtered_ticks)
                            final_pct = (final_volume / total_volume * 100) if total_volume > 0 else 0
                            final_last_ts = max([tick.get('ts', 0) for tick in final_filtered_ticks]) if final_filtered_ticks else max(merged_volav.get('last_print_ts', 0), other_volav.get('last_print_ts', 0))
                            
                            # Update merged Volav
                            merged_volav['price'] = final_vwap
                            merged_volav['volume'] = final_volume
                            merged_volav['tick_count'] = final_tick_count
                            merged_volav['pct_of_truth_volume'] = final_pct
                            merged_volav['range_min'] = final_range_min
                            merged_volav['range_max'] = final_range_max
                            merged_volav['last_print_ts'] = final_last_ts
                            # Keep bucket_key if it exists
                            if 'bucket_key' not in merged_volav:
                                # Find closest bucket by price
                                closest_bucket = None
                                min_price_diff = float('inf')
                                for b in all_buckets:
                                    price_diff = abs(b['price'] - final_vwap)
                                    if price_diff < min_price_diff:
                                        min_price_diff = price_diff
                                        closest_bucket = b
                                if closest_bucket:
                                    merged_volav['bucket_key'] = closest_bucket['bucket_key']
                            
                            # Remove the other Volav (it's been merged)
                            volav_levels.pop(other_idx)
                            
                            # Re-rank remaining Volavs
                            for i, volav in enumerate(volav_levels):
                                volav['rank'] = i + 1
                            
                            break  # Only merge one at a time, will be checked in next iteration
            
            if not merged:
                # Add as new Volav (either gap >= min_gap or intermediate zone)
                # Ensure we used the weighted values from the start of the loop
                volav_levels.append({
                    'rank': len(volav_levels) + 1,
                    'price': range_vwap,
                    'volume': range_volume,
                    'tick_count': range_tick_count,
                    'pct_of_truth_volume': (range_volume / total_volume * 100) if total_volume > 0 else 0,
                    'range_min': bucket_range_min,
                    'range_max': bucket_range_max,
                    'last_print_ts': range_last_ts,
                    'merged': False,
                    'bucket_key': bucket['bucket_key']  # Add bucket_key for backward compatibility
                })
        
        # Add bucket_key to all volav_levels for backward compatibility (if missing)
        for volav in volav_levels:
            if 'bucket_key' not in volav:
                # Find closest bucket by price
                closest_bucket = None
                min_price_diff = float('inf')
                for bucket in all_buckets:
                    price_diff = abs(bucket['price'] - volav['price'])
                    if price_diff < min_price_diff:
                        min_price_diff = price_diff
                        closest_bucket = bucket
                if closest_bucket:
                    volav['bucket_key'] = closest_bucket['bucket_key']
        
        # MM-Anchor spacing constraint: Ensure minimum 0.06$ gap between Volavs
        # This is critical for MM tradeability - two anchor zones must be at least 0.06$ apart
        # Iterative algorithm: merge closest Volavs until all gaps >= 0.06
        MM_ANCHOR_MIN_GAP = 0.06
        volav_levels = self._apply_mm_anchor_spacing_constraint(
            volav_levels,
            truth_ticks,
            total_volume,
            MM_ANCHOR_MIN_GAP,
            half_bucket
        )
        
        return volav_levels, all_buckets
    
    def _apply_mm_anchor_spacing_constraint(
        self,
        volav_levels: List[Dict[str, Any]],
        truth_ticks: List[Dict[str, Any]],
        total_volume: float,
        min_gap: float = 0.06,
        half_bucket: float = 0.005
    ) -> List[Dict[str, Any]]:
        """
        Apply MM-Anchor spacing constraint: ensure minimum gap between all Volavs.
        
        Iterative algorithm:
        1. Sort Volavs by price
        2. Find closest pair
        3. If gap < min_gap, merge them
        4. Repeat until all gaps >= min_gap
        
        Args:
            volav_levels: List of Volav levels (already merged with merge_threshold)
            truth_ticks: All truth ticks (for recalculating merged Volavs)
            total_volume: Total truth volume
            min_gap: Minimum gap between anchors (default: 0.06)
            half_bucket: Half of bucket size (for range calculation)
            
        Returns:
            List of Volav levels with minimum gap constraint applied
        """
        if len(volav_levels) <= 1:
            return volav_levels
        
        # Sort by price (ascending)
        sorted_volavs = sorted(volav_levels, key=lambda v: v.get('price', 0))
        
        # Iterative merging until all gaps >= min_gap
        max_iterations = 100  # Safety limit
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            # Find closest pair
            min_gap_found = float('inf')
            closest_pair_idx = None
            
            for i in range(len(sorted_volavs) - 1):
                gap = abs(sorted_volavs[i+1]['price'] - sorted_volavs[i]['price'])
                if gap < min_gap_found:
                    min_gap_found = gap
                    closest_pair_idx = i
            
            # If all gaps >= min_gap, we're done
            if min_gap_found >= min_gap:
                break
            
            # Merge closest pair
            if closest_pair_idx is not None:
                v1 = sorted_volavs[closest_pair_idx]
                v2 = sorted_volavs[closest_pair_idx + 1]
                
                # Combined range
                v1_range_min = v1.get('range_min', v1['price'] - half_bucket)
                v1_range_max = v1.get('range_max', v1['price'] + half_bucket)
                v2_range_min = v2.get('range_min', v2['price'] - half_bucket)
                v2_range_max = v2.get('range_max', v2['price'] + half_bucket)
                
                combined_range_min = min(v1_range_min, v2_range_min)
                combined_range_max = max(v1_range_max, v2_range_max)
                
                # Find all ticks in combined range
                combined_ticks = [
                    tick for tick in truth_ticks
                    if combined_range_min <= tick.get('price', 0) <= combined_range_max
                ]
                
                if combined_ticks:
                    # Weighted volume integration
                    combined_volume = 0.0
                    combined_price_sum = 0.0
                    combined_filtered_ticks = []
                    
                    for tick in combined_ticks:
                        size = tick.get('size', 0)
                        price = tick.get('price', 0)
                        weight = self.calculate_print_weight(size)
                        weighted_size = size * weight
                        
                        if weighted_size > 0:
                             combined_volume += weighted_size
                             combined_price_sum += price * weighted_size
                             combined_filtered_ticks.append(tick)

                    combined_vwap = combined_price_sum / combined_volume if combined_volume > 0 else (v1['price'] + v2['price']) / 2
                    combined_tick_count = len(combined_filtered_ticks)
                    combined_pct = (combined_volume / total_volume * 100) if total_volume > 0 else 0
                    combined_last_ts = max([tick.get('ts', 0) for tick in combined_filtered_ticks]) if combined_filtered_ticks else max(v1.get('last_print_ts', 0), v2.get('last_print_ts', 0))
                    
                    # Create merged Volav
                    merged_volav = {
                        'rank': v1.get('rank', 1),
                        'price': combined_vwap,
                        'volume': combined_volume,
                        'tick_count': combined_tick_count,
                        'pct_of_truth_volume': combined_pct,
                        'range_min': combined_range_min,
                        'range_max': combined_range_max,
                        'last_print_ts': combined_last_ts,
                        'merged': True,
                        'bucket_key': v1.get('bucket_key')  # Keep first bucket_key
                    }
                    
                    # Replace v1 with merged, remove v2
                    sorted_volavs[closest_pair_idx] = merged_volav
                    sorted_volavs.pop(closest_pair_idx + 1)
        
        # Re-sort by volume (descending) for final ranking
        sorted_volavs.sort(key=lambda x: x.get('volume', 0), reverse=True)
        for i, volav in enumerate(sorted_volavs):
            volav['rank'] = i + 1
        
        return sorted_volavs
    
    def compute_volav_timeline(
        self,
        truth_ticks: List[Dict[str, Any]],
        num_windows: int = 5,
        avg_adv: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Compute Volav timeline - how Volav levels evolve over time.
        
        Splits truth_ticks into time windows and computes Volav1..4 for each window.
        This shows how volume-dominant price regions shift over time.
        
        Args:
            truth_ticks: List of TruthTicks (should be truth_ticks_100)
            num_windows: Number of time windows to split into (default: 5)
            avg_adv: Average Daily Volume (for min_volav_gap calculation)
            
        Returns:
            List of window data, each containing:
            - window_index: 0..num_windows-1
            - start_timestamp: First tick timestamp in window
            - end_timestamp: Last tick timestamp in window
            - tick_count: Number of ticks in window
            - volume: Total volume in window
            - volav1..volav4: Volav prices (None if not found)
            - volav_levels: Full volav data for this window
        """
        # CRITICAL: Don't hard exit if we have fewer ticks than windows
        # Preferred stocks are illiquid - adapt to available data
        if not truth_ticks:
            return []
        
        # If we have fewer ticks than requested windows, reduce window count
        if len(truth_ticks) < num_windows:
            # Use all ticks in a single window if we have very few ticks
            if len(truth_ticks) < 2:
                return []
            # Otherwise, use fewer windows
            num_windows = max(1, len(truth_ticks) // 2)  # At least 2 ticks per window
        
        timeline = []
        ticks_per_window = len(truth_ticks) // num_windows
        
        for window_idx in range(num_windows):
            start_idx = window_idx * ticks_per_window
            # Last window gets remaining ticks
            if window_idx == num_windows - 1:
                end_idx = len(truth_ticks)
            else:
                end_idx = (window_idx + 1) * ticks_per_window
            
            window_ticks = truth_ticks[start_idx:end_idx]
            
            if not window_ticks:
                continue
            
            # Compute Volav levels for this window
            volav_levels, _ = self.compute_volav_levels(window_ticks, top_n=4, avg_adv=avg_adv)
            
            # Extract Volav prices
            volav1 = volav_levels[0]['price'] if len(volav_levels) > 0 else None
            volav2 = volav_levels[1]['price'] if len(volav_levels) > 1 else None
            volav3 = volav_levels[2]['price'] if len(volav_levels) > 2 else None
            volav4 = volav_levels[3]['price'] if len(volav_levels) > 3 else None
            
            # Calculate weighted volume
            weighted_vol = 0.0
            for t in window_ticks:
                w = self.calculate_print_weight(t.get('size', 0))
                weighted_vol += t.get('size', 0) * w

            window_data = {
                'window_index': window_idx,
                'start_timestamp': window_ticks[0].get('ts'),
                'end_timestamp': window_ticks[-1].get('ts'),
                'tick_count': len(window_ticks),
                'volume': weighted_vol, # WEIGHTED volume
                'volav1': volav1,
                'volav2': volav2,
                'volav3': volav3,
                'volav4': volav4,
                'volav_levels': volav_levels  # Full data for detailed view
            }
            
            timeline.append(window_data)
        
        return timeline
    
    def compute_metrics(
        self,
        symbol: str,
        avg_adv: float
    ) -> Optional[Dict[str, Any]]:
        """
        Compute Truth Ticks metrics for a symbol.
        
        Args:
            symbol: Symbol name
            avg_adv: Average Daily Volume (for ADV fraction calculation)
            
        Returns:
            Metrics dict or None if insufficient data
        """
        try:
            with self._tick_lock:
                if symbol not in self.tick_store:
                    return None
                
                # Get last 200 ticks
                all_ticks = list(self.tick_store[symbol])
            
            if not all_ticks:
                return None
            
            # Filter to TruthTicks
            truth_ticks_200 = self.filter_truth_ticks(all_ticks)
            
            if not truth_ticks_200:
                return None
            
            # Apply 10-day limit: Only use ticks from last 10 days
            current_time = time.time()
            ten_days_ago = current_time - (10 * 24 * 60 * 60)  # 10 days in seconds
            
            # Filter truth_ticks_200 to only include ticks from last 10 days
            truth_ticks_200_filtered = [
                tick for tick in truth_ticks_200
                if tick.get('ts', 0) >= ten_days_ago
            ]
            
            # Check tick count in last 10 days for insufficient data flag
            ticks_in_last_10_days = len(truth_ticks_200_filtered)
            insufficient_data_flag = ticks_in_last_10_days < 30
            
            # Get most recent 100 TruthTicks for VWAP calculation (from filtered set)
            if len(truth_ticks_200_filtered) >= self.REQUIRED_TRUTH_TICKS:
                truth_ticks_100 = truth_ticks_200_filtered[-self.REQUIRED_TRUTH_TICKS:]
            else:
                truth_ticks_100 = truth_ticks_200_filtered
            
            # Check if we have minimum TruthTicks
            insufficient_truth_ticks = len(truth_ticks_100) < self.MIN_TRUTH_TICKS
            
            # Basic metrics (truth_ticks_100)
            truth_tick_count_100 = len(truth_ticks_100)
            
            # VWAP: Sum(Price * Size) / Sum(Size) -> CRITICAL: Use Weighted Volume
            truth_volume_100 = 0.0
            truth_value_100 = 0.0
            
            for tick in truth_ticks_100:
                size = tick.get('size', 0)
                price = tick.get('price', 0)
                weight = self.calculate_print_weight(size)
                weighted_size = size * weight
                
                truth_volume_100 += weighted_size
                truth_value_100 += price * weighted_size
            
            # Truth VWAP (Volume Weighted Average Price)
            truth_vwap_100 = truth_value_100 / truth_volume_100 if truth_volume_100 > 0 else 0
            
            # ADV fraction
            adv_fraction_truth = truth_volume_100 / avg_adv if avg_adv > 0 else 0
            
            # Venue volume mix
            volume_by_exch: Dict[str, float] = defaultdict(float)
            for tick in truth_ticks_100:
                exch = tick.get('exch', 'UNKNOWN')
                size = tick.get('size', 0)
                weight = self.calculate_print_weight(size)
                volume_by_exch[exch] += size * weight
            
            venue_mix_pct: Dict[str, float] = {}
            if truth_volume_100 > 0:
                for exch, volume in volume_by_exch.items():
                    venue_mix_pct[exch] = (volume / truth_volume_100) * 100
            
            # Volav levels (from truth_ticks_100) - Volume Weighted Average Price clusters
            # Each Volav is a VWAP of a volume-dominant price region
            volav_levels, _ = self.compute_volav_levels(truth_ticks_100, top_n=4, avg_adv=avg_adv)
            min_volav_gap_used = self.min_volav_gap(avg_adv) if avg_adv > 0 else 0.05
            
            # Volav Timeline - How Volav levels evolve over time (5 windows)
            volav_timeline = self.compute_volav_timeline(truth_ticks_100, num_windows=5, avg_adv=avg_adv)
            
            # Volav1_start and Volav1_end (CORE LOGIC) - from first and last windows
            volav1_start = None
            volav1_end = None
            volav1_displacement = None
            volav_shift_abs = None
            volav_shift_dir = None
            
            if len(volav_timeline) >= 2:
                # Use first and last windows from timeline
                first_window = volav_timeline[0]
                last_window = volav_timeline[-1]
                
                volav1_start = first_window.get('volav1')
                volav1_end = last_window.get('volav1')
                
                # Compute displacement
                if volav1_start is not None and volav1_end is not None:
                    volav1_displacement = volav1_end - volav1_start
                    volav_shift_abs = abs(volav1_displacement)
                    
                    # Determine direction
                    if volav_shift_abs < self.FLAT_EPSILON:
                        volav_shift_dir = 'FLAT'
                    elif volav1_displacement > 0:
                        volav_shift_dir = 'UP'
                    else:
                        volav_shift_dir = 'DOWN'
            elif len(truth_ticks_100) >= 2:
                # Fallback: Split into two equal halves by time
                mid_point = len(truth_ticks_100) // 2
                first_half = truth_ticks_100[:mid_point]
                second_half = truth_ticks_100[mid_point:]
                
                # Compute Volav1 for each half
                first_half_volav, _ = self.compute_volav_levels(first_half, top_n=1, avg_adv=avg_adv)
                second_half_volav, _ = self.compute_volav_levels(second_half, top_n=1, avg_adv=avg_adv)
                
                if first_half_volav:
                    volav1_start = first_half_volav[0]['price']
                
                if second_half_volav:
                    volav1_end = second_half_volav[0]['price']
                
                # Compute displacement
                if volav1_start is not None and volav1_end is not None:
                    volav1_displacement = volav1_end - volav1_start
                    volav_shift_abs = abs(volav1_displacement)
                    
                    # Determine direction
                    if volav_shift_abs < self.FLAT_EPSILON:
                        volav_shift_dir = 'FLAT'
                    elif volav1_displacement > 0:
                        volav_shift_dir = 'UP'
                    else:
                        volav_shift_dir = 'DOWN'
            
            # Real Pressure (net_pressure_truth) - optional, requires bid/ask
            # For now, we'll skip if bid/ask not available per tick
            net_pressure_truth = None
            # TODO: Implement when bid/ask data is available per tick
            
            # State Classification
            state_name, state_confidence = self.classify_state(
                volav1_displacement=volav1_displacement,
                volav_shift_abs=volav_shift_abs,
                volav_shift_dir=volav_shift_dir,
                adv_fraction_truth=adv_fraction_truth,
                truth_tick_count_100=truth_tick_count_100,
                volav_levels=volav_levels,
                net_pressure_truth=net_pressure_truth,
                min_ticks_required=None,  # Legacy method uses default threshold
                min_volav_gap_used=min_volav_gap_used
            )
            
            # Top truth volume events (from truth_ticks_200_filtered)
            top_truth_events_200 = []
            if truth_ticks_200_filtered:
                # Sort by size descending
                sorted_by_size = sorted(
                    truth_ticks_200_filtered,
                    key=lambda x: x.get('size', 0),
                    reverse=True
                )[:10]  # Top 10
                
                for tick in sorted_by_size:
                    top_truth_events_200.append({
                        'ts': tick.get('ts'),
                        'price': tick.get('price'),
                        'size': tick.get('size'),
                        'exch': tick.get('exch')
                    })
            
            # Calculate timeframe for 100 Truth Ticks
            timeframe_str = None
            timeframe_seconds = None
            if truth_ticks_100 and len(truth_ticks_100) >= 2:
                first_tick_time = truth_ticks_100[0].get('ts', 0)
                last_tick_time = truth_ticks_100[-1].get('ts', 0)
                timeframe_seconds = last_tick_time - first_tick_time
                
                # Format as "XdXhXm" (days, hours, minutes)
                days = int(timeframe_seconds // 86400)
                hours = int((timeframe_seconds % 86400) // 3600)
                minutes = int((timeframe_seconds % 3600) // 60)
                
                parts = []
                if days > 0:
                    parts.append(f"{days}d")
                if hours > 0:
                    parts.append(f"{hours}h")
                if minutes > 0:
                    parts.append(f"{minutes}m")
                
                timeframe_str = "".join(parts) if parts else "0m"
            
            # Flags
            finra_dominant = False
            if truth_volume_100 > 0:
                finra_volume = volume_by_exch.get('FNRA', 0)
                finra_dominant = (finra_volume / truth_volume_100) > self.FINRA_DOMINANT_THRESHOLD
            
            flags = {
                'insufficient_truth_ticks': insufficient_truth_ticks,
                'insufficient_data': insufficient_data_flag,  # Less than 30 ticks in last 10 days
                'finra_dominant': finra_dominant
            }
            
            # Build result
            result = {
                'symbol': symbol,
                'avg_adv': avg_adv,
                'min_volav_gap_used': min_volav_gap_used,
                'truth_tick_count_100': truth_tick_count_100,
                'truth_tick_count_200': len(truth_ticks_200_filtered),  # Use filtered count
                'truth_volume_100': truth_volume_100,
                'truth_volume_200': sum(tick.get('size', 0) for tick in truth_ticks_200_filtered),
                'truth_vwap_100': truth_vwap_100,
                'adv_fraction_truth': adv_fraction_truth,
                'venue_mix_pct': venue_mix_pct,
                'volav_levels': volav_levels,
                'volav_timeline': volav_timeline,  # Time evolution of Volav levels
                'volav1_start': volav1_start,
                'volav1_end': volav1_end,
                'volav1_displacement': volav1_displacement,
                'volav_shift_abs': volav_shift_abs,
                'volav_shift_dir': volav_shift_dir,
                'net_pressure_truth': net_pressure_truth,
                'state': state_name,
                'state_confidence': state_confidence,
                'top_truth_events_200': top_truth_events_200,
                'flags': flags,
                'timeframe': timeframe_str,  # Format: "4d3h30m"
                'timeframe_seconds': timeframe_seconds,  # For sorting
                'updated_at': datetime.now().isoformat()
            }
            
            # Cache result
            with self._cache_lock:
                self.results_cache[symbol] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Error computing Truth Ticks metrics for {symbol}: {e}", exc_info=True)
            return None
    
    def get_metrics(self, symbol: str, avg_adv: float) -> Optional[Dict[str, Any]]:
        """
        Get Truth Ticks metrics for a symbol.
        
        Args:
            symbol: Symbol name
            avg_adv: Average Daily Volume
            
        Returns:
            Metrics dict or None
        """
        # Check cache first
        with self._cache_lock:
            cached = self.results_cache.get(symbol)
            if cached:
                # Check if cache is recent (within last 5 seconds)
                updated_at = cached.get('updated_at')
                if updated_at:
                    try:
                        cache_time = datetime.fromisoformat(updated_at).timestamp()
                        if time.time() - cache_time < 5.0:
                            return cached
                    except:
                        pass
        
        # Compute fresh metrics
        return self.compute_metrics(symbol, avg_adv)
    
    def classify_state(
        self,
        volav1_displacement: Optional[float],
        volav_shift_abs: Optional[float],
        volav_shift_dir: Optional[str],
        adv_fraction_truth: float,
        truth_tick_count_100: int,
        volav_levels: List[Dict[str, Any]],
        net_pressure_truth: Optional[float],
        min_ticks_required: Optional[int] = None,
        min_volav_gap_used: Optional[float] = None
    ) -> Tuple[str, float]:
        """
        Classify market state based on Volav displacement and volume.
        
        7-State Model (Symmetric & Market-Structure Aligned):
        1. BUYER_DOMINANT: High volume + significant upward displacement
        2. SELLER_DOMINANT: High volume + significant downward displacement
        3. BUYER_ABSORPTION: High volume + flat/slight down (buyers absorbing sells)
        4. SELLER_ABSORPTION: High volume + flat/slight up (sellers absorbing buys)
        5. BUYER_VACUUM: Low volume + upward drift (fake strength, no real buyers)
        6. SELLER_VACUUM: Low volume + downward drift (air pocket, no real sellers)
        7. NEUTRAL: Everything else
        
        Returns:
            Tuple of (state_name, confidence_score)
        """
        # CRITICAL: Don't hard exit on insufficient ticks - compute anyway with reduced confidence
        # If min_ticks_required is provided, use it; otherwise use default MIN_TRUTH_TICKS
        threshold = min_ticks_required if min_ticks_required is not None else self.MIN_TRUTH_TICKS
        
        # Guard against invalid inputs
        if volav_shift_abs is None or volav1_displacement is None:
            return ('NEUTRAL', 0.2)
        
        # Calculate normalized displacement for threshold comparison
        # Use min_volav_gap_used if provided, otherwise use default
        min_gap = min_volav_gap_used if min_volav_gap_used and min_volav_gap_used > 0 else self.VOLAV_MOVE_THRESHOLD
        normalized_displacement = volav1_displacement / min_gap if min_gap > 0 else 0.0
        
        # Guard against NaN
        if not isinstance(normalized_displacement, (int, float)) or normalized_displacement != normalized_displacement:
            normalized_displacement = 0.0
        if not isinstance(adv_fraction_truth, (int, float)) or adv_fraction_truth != adv_fraction_truth:
            adv_fraction_truth = 0.0
        
        # Determine volume category
        HIGH_VOLUME = adv_fraction_truth >= self.HIGH_VOLUME_THRESHOLD
        LOW_VOLUME = adv_fraction_truth <= self.LOW_VOLUME_THRESHOLD
        
        # Determine displacement direction (using normalized threshold)
        UP = normalized_displacement > self.DISPLACEMENT_THRESHOLD
        DOWN = normalized_displacement < -self.DISPLACEMENT_THRESHOLD
        FLAT = not UP and not DOWN  # abs(normalized_displacement) <= DISPLACEMENT_THRESHOLD
        
        # State Resolution Tree (Volume → Displacement → Direction)
        
        # 1. HIGH_VOLUME + UP → BUYER_DOMINANT
        if HIGH_VOLUME and UP:
            confidence = min(0.95, 0.6 + (adv_fraction_truth * 0.3) + (abs(normalized_displacement) * 0.1))
            if net_pressure_truth and net_pressure_truth >= 0.10:
                confidence = min(0.98, confidence + 0.05)
            return ('BUYER_DOMINANT', confidence)
        
        # 2. HIGH_VOLUME + DOWN → SELLER_DOMINANT
        elif HIGH_VOLUME and DOWN:
            confidence = min(0.95, 0.6 + (adv_fraction_truth * 0.3) + (abs(normalized_displacement) * 0.1))
            if net_pressure_truth and net_pressure_truth <= -0.10:
                confidence = min(0.98, confidence + 0.05)
            return ('SELLER_DOMINANT', confidence)
        
        # 3. HIGH_VOLUME + FLAT → BUYER_ABSORPTION or SELLER_ABSORPTION
        elif HIGH_VOLUME and FLAT:
            # Check subtle trend: if volav1_displacement is slightly positive → buyer absorption
            # If slightly negative → seller absorption
            if volav1_displacement is not None and abs(volav1_displacement) > 0:
                if volav1_displacement > 0:
                    # Slight upward bias → buyers absorbing sells (bullish)
                    confidence = min(0.85, 0.5 + (adv_fraction_truth * 0.3))
                    return ('BUYER_ABSORPTION', confidence)
                else:
                    # Slight downward bias → sellers absorbing buys (bearish)
                    confidence = min(0.85, 0.5 + (adv_fraction_truth * 0.3))
                    return ('SELLER_ABSORPTION', confidence)
            else:
                # Truly flat → default to BUYER_ABSORPTION (accumulation is more common)
                confidence = min(0.80, 0.45 + (adv_fraction_truth * 0.3))
                return ('BUYER_ABSORPTION', confidence)
        
        # 4. LOW_VOLUME + UP → BUYER_VACUUM
        elif LOW_VOLUME and UP:
            confidence = min(0.70, 0.4 + (abs(normalized_displacement) * 0.2))
            return ('BUYER_VACUUM', confidence)
        
        # 5. LOW_VOLUME + DOWN → SELLER_VACUUM
        elif LOW_VOLUME and DOWN:
            confidence = min(0.70, 0.4 + (abs(normalized_displacement) * 0.2))
            return ('SELLER_VACUUM', confidence)
        
        # 6. Everything else → NEUTRAL
        else:
            # Medium volume + small displacement, or insufficient data
            confidence = min(0.60, 0.3 + (adv_fraction_truth * 0.2))
            return ('NEUTRAL', confidence)
    
    def classify_state_v2(
        self,
        normalized_displacement: float,
        adv_fraction: float,
        truth_tick_count: int,
        volav1_displacement: Optional[float],
        min_volav_gap_used: float
    ) -> Tuple[str, float]:
        """
        TIMEFRAME-FIRST: 10-State Classification Model
        
        States:
        1. STRONG_BUYER_DOMINANT
        2. BUYER_DOMINANT
        3. BUYER_ABSORPTION (high volume, price barely up)
        4. BUYER_VACUUM (low volume, price up)
        5. NEUTRAL
        6. SELLER_ABSORPTION (high volume, price barely down)
        7. SELLER_DOMINANT
        8. STRONG_SELLER_DOMINANT
        9. SELLER_VACUUM (low volume, price down)
        10. INSUFFICIENT_DATA
        
        Args:
            normalized_displacement: (volav1_end - volav1_start) / min_volav_gap
            adv_fraction: truth_volume / avg_adv
            truth_tick_count: Number of truth ticks in timeframe
            volav1_displacement: Raw displacement (volav1_end - volav1_start)
            min_volav_gap_used: Minimum volav gap used for normalization
            
        Returns:
            Tuple of (state_name, confidence_score)
        """
        # Guard against invalid inputs
        if not isinstance(normalized_displacement, (int, float)) or normalized_displacement != normalized_displacement:
            normalized_displacement = 0.0
        if not isinstance(adv_fraction, (int, float)) or adv_fraction != adv_fraction:
            adv_fraction = 0.0
        
        D = normalized_displacement
        V = adv_fraction
        T = truth_tick_count
        
        # Rule 1: INSUFFICIENT_DATA if tick count < 15
        if T < self.MIN_TICKS_FOR_SUFFICIENT_DATA:
            return ('INSUFFICIENT_DATA', 0.1)
        
        # Rule 2: ABSORPTION states (high volume, small displacement)
        if V > 0.8 and abs(D) < 0.3:
            if D >= 0:
                confidence = min(0.85, 0.5 + (V * 0.3))
                return ('BUYER_ABSORPTION', confidence)
            else:
                confidence = min(0.85, 0.5 + (V * 0.3))
                return ('SELLER_ABSORPTION', confidence)
        
        # Rule 3: VACUUM states (low volume)
        if V < 0.2:
            if D > 0:
                confidence = min(0.70, 0.4 + (abs(D) * 0.2))
                return ('BUYER_VACUUM', confidence)
            elif D < 0:
                confidence = min(0.70, 0.4 + (abs(D) * 0.2))
                return ('SELLER_VACUUM', confidence)
            else:
                confidence = min(0.60, 0.3 + (V * 0.2))
                return ('NEUTRAL', confidence)
        
        # Rule 4: STRONG_BUYER_DOMINANT
        if D >= 1.5:
            confidence = min(0.95, 0.7 + (V * 0.2) + (abs(D) * 0.05))
            return ('STRONG_BUYER_DOMINANT', confidence)
        
        # Rule 5: BUYER_DOMINANT
        if D >= 0.4:
            confidence = min(0.90, 0.6 + (V * 0.2) + (abs(D) * 0.1))
            return ('BUYER_DOMINANT', confidence)
        
        # Rule 6: STRONG_SELLER_DOMINANT
        if D <= -1.5:
            confidence = min(0.95, 0.7 + (V * 0.2) + (abs(D) * 0.05))
            return ('STRONG_SELLER_DOMINANT', confidence)
        
        # Rule 7: SELLER_DOMINANT
        if D <= -0.4:
            confidence = min(0.90, 0.6 + (V * 0.2) + (abs(D) * 0.1))
            return ('SELLER_DOMINANT', confidence)
        
        # Rule 8: NEUTRAL (everything else)
        confidence = min(0.70, 0.4 + (V * 0.2))
        return ('NEUTRAL', confidence)
    
    def get_inspect_data(self, symbol: str, avg_adv: float) -> Optional[Dict[str, Any]]:
        """
        Get detailed inspection data for a symbol (for Inspector view).
        
        Returns:
            Detailed dict with filtering report, Volav details, time segmentation, etc.
        """
        try:
            with self._tick_lock:
                if symbol not in self.tick_store:
                    return None
                
                # Get last 150 ticks
                all_ticks = list(self.tick_store[symbol])
            
            if not all_ticks:
                return None
            
            # Filtering report
            excluded_small_size = 0
            excluded_fnra_non_100_200 = 0
            included_non_fnra = 0
            included_fnra_100_200 = 0
            
            for tick in all_ticks:
                size = tick.get('size', 0)
                exch = tick.get('exch', '')
                
                if size < self.MIN_SIZE:
                    excluded_small_size += 1
                elif exch == 'FNRA':
                    if size in self.FNRA_ALLOWED_SIZES:
                        included_fnra_100_200 += 1
                    else:
                        excluded_fnra_non_100_200 += 1
                else:
                    included_non_fnra += 1
            
            # Filter to TruthTicks
            truth_ticks_200 = self.filter_truth_ticks(all_ticks)
            
            # Apply 10-day limit: Only use ticks from last 10 days
            current_time = time.time()
            ten_days_ago = current_time - (10 * 24 * 60 * 60)  # 10 days in seconds
            
            # Filter truth_ticks_200 to only include ticks from last 10 days
            truth_ticks_200_filtered = [
                tick for tick in truth_ticks_200
                if tick.get('ts', 0) >= ten_days_ago
            ]
            
            # Get most recent 100 TruthTicks for VWAP calculation (from filtered set)
            if len(truth_ticks_200_filtered) >= self.REQUIRED_TRUTH_TICKS:
                truth_ticks_100 = truth_ticks_200_filtered[-self.REQUIRED_TRUTH_TICKS:]
            else:
                truth_ticks_100 = truth_ticks_200_filtered
            
            # Compute Volav with all buckets (Volume Weighted Average Price clusters)
            volav_levels, all_buckets = self.compute_volav_levels(truth_ticks_100, top_n=4, avg_adv=avg_adv)
            min_volav_gap_used = self.min_volav_gap(avg_adv) if avg_adv > 0 else 0.05
            
            # Volav Timeline - How Volav levels evolve over time (5 windows)
            volav_timeline = self.compute_volav_timeline(truth_ticks_100, num_windows=5, avg_adv=avg_adv)
            
            # Find skipped buckets (buckets in top 10 that weren't selected)
            # NOTE: New Volav structure doesn't have 'bucket_key', so we match by price proximity
            top_10_buckets = all_buckets[:10]
            selected_volav_prices = {v['price'] for v in volav_levels}
            skipped_buckets = []
            
            # A bucket is "skipped" if its price is not close to any selected Volav price
            # Use min_gap as the proximity threshold
            for bucket in top_10_buckets:
                bucket_price = bucket['price']
                is_selected = False
                
                # Check if bucket price is within min_gap of any selected Volav
                for volav_price in selected_volav_prices:
                    if abs(bucket_price - volav_price) < min_volav_gap_used:
                        is_selected = True
                        break
                
                if not is_selected:
                    skipped_buckets.append(bucket)
            
            # Time segmentation (for backward compatibility)
            first_half = None
            second_half = None
            
            if len(volav_timeline) >= 2:
                # Use first and last windows from timeline
                first_window = volav_timeline[0]
                last_window = volav_timeline[-1]
                
                first_half = {
                    'tick_count': first_window.get('tick_count', 0),
                    'volume': first_window.get('volume', 0),
                    'volav1': {'price': first_window.get('volav1')} if first_window.get('volav1') else None,
                    'start_timestamp': first_window.get('start_timestamp'),
                    'end_timestamp': first_window.get('end_timestamp')
                }
                
                second_half = {
                    'tick_count': last_window.get('tick_count', 0),
                    'volume': last_window.get('volume', 0),
                    'volav1': {'price': last_window.get('volav1')} if last_window.get('volav1') else None,
                    'start_timestamp': last_window.get('start_timestamp'),
                    'end_timestamp': last_window.get('end_timestamp')
                }
            elif len(truth_ticks_100) >= 2:
                # Fallback: Split into two equal halves by time
                mid_point = len(truth_ticks_100) // 2
                first_half_ticks = truth_ticks_100[:mid_point]
                second_half_ticks = truth_ticks_100[mid_point:]
                
                first_half_volav, _ = self.compute_volav_levels(first_half_ticks, top_n=1, avg_adv=avg_adv)
                second_half_volav, _ = self.compute_volav_levels(second_half_ticks, top_n=1, avg_adv=avg_adv)
                
                first_half = {
                    'tick_count': len(first_half_ticks),
                    'volume': sum(t.get('size', 0) for t in first_half_ticks),
                    'volav1': first_half_volav[0] if first_half_volav else None
                }
                
                second_half = {
                    'tick_count': len(second_half_ticks),
                    'volume': sum(t.get('size', 0) for t in second_half_ticks),
                    'volav1': second_half_volav[0] if second_half_volav else None
                }
            
            # Price-time-volume path dataset
            path_dataset = []
            for tick in truth_ticks_100:
                path_dataset.append({
                    'timestamp': tick.get('ts'),
                    'price': tick.get('price'),
                    'size': tick.get('size'),
                    'venue': tick.get('exch'),
                    'is_truth': True
                })
            
            # Overlay bands (Volav levels - VWAP clusters)
            overlay_bands = []
            for volav in volav_levels:
                overlay_bands.append({
                    'level': f'Volav{volav["rank"]}',
                    'price': volav['price'],
                    'volume': volav['volume'],
                    'pct': volav['pct_of_truth_volume']
                })
            
            # Volav1_start and Volav1_end markers
            markers = []
            if first_half and first_half.get('volav1'):
                markers.append({
                    'type': 'volav1_start',
                    'price': first_half['volav1']['price'],
                    'timestamp': truth_ticks_100[0].get('ts') if truth_ticks_100 else None
                })
            if second_half and second_half.get('volav1'):
                markers.append({
                    'type': 'volav1_end',
                    'price': second_half['volav1']['price'],
                    'timestamp': truth_ticks_100[-1].get('ts') if truth_ticks_100 else None
                })
            
            # Get summary metrics
            metrics = self.compute_metrics(symbol, avg_adv)
            
            # Check tick count in last 10 days for insufficient data flag
            ticks_in_last_10_days = len(truth_ticks_200_filtered)
            insufficient_data_flag = ticks_in_last_10_days < 30
            
            return {
                'summary': {
                    'symbol': symbol,
                    'avg_adv': avg_adv,
                    'min_volav_gap_used': min_volav_gap_used,
                    'timeframe': metrics.get('timeframe') if metrics else None,
                    'timeframe_seconds': metrics.get('timeframe_seconds') if metrics else None,
                    'truth_tick_count_200': len(truth_ticks_200_filtered),
                    'truth_tick_count_100': len(truth_ticks_100),
                    'truth_volume_200': sum(t.get('size', 0) for t in truth_ticks_200_filtered),
                    'truth_volume_100': sum(t.get('size', 0) for t in truth_ticks_100),
                    'truth_adv_fraction_100': metrics.get('adv_fraction_truth', 0) if metrics else 0,
                    'state': metrics.get('state', 'UNKNOWN') if metrics else 'UNKNOWN',
                    'state_confidence': metrics.get('state_confidence', 0) if metrics else 0,
                    'volav1_start_price': metrics.get('volav1_start') if metrics else None,
                    'volav1_end_price': metrics.get('volav1_end') if metrics else None,
                    'volav_shift': metrics.get('volav1_displacement') if metrics else None,
                    'insufficient_data_flag': insufficient_data_flag
                },
                'filtering_report': {
                    'last_200_raw_ticks_count': len(all_ticks),
                    'excluded_small_size_count': excluded_small_size,
                    'excluded_fnra_non_100_200_count': excluded_fnra_non_100_200,
                    'included_non_fnra_count': included_non_fnra,
                    'included_fnra_100_200_count': included_fnra_100_200,
                    'total_truth_ticks_200': len(truth_ticks_200_filtered),
                    'ticks_in_last_10_days': len(truth_ticks_200_filtered),
                    'insufficient_data_flag': len(truth_ticks_200_filtered) < 30
                },
                'volav_details': {
                    'volavs': volav_levels,
                    'top_buckets': all_buckets[:10],  # Top 10 by volume
                    'skipped_buckets': skipped_buckets
                },
                'volav_timeline': volav_timeline,  # Time evolution: Volav levels across 5 windows
                'time_segmentation': {
                    'first_half': first_half,
                    'second_half': second_half
                },
                'path_dataset': path_dataset,
                'overlay_bands': overlay_bands,
                'markers': markers
            }
            
        except KeyError as e:
            # Specifically handle KeyError for 'bucket_key' - this happens when old code tries to access bucket_key from new Volav structure
            if 'bucket_key' in str(e):
                logger.error(f"Error getting inspect data for {symbol}: {e}. This is likely due to accessing 'bucket_key' from new Volav structure. Volav levels: {volav_levels[:2] if 'volav_levels' in locals() else 'N/A'}", exc_info=True)
            else:
                logger.error(f"Error getting inspect data for {symbol}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Error getting inspect data for {symbol}: {e}", exc_info=True)
            return None
    
    def calculate_bad_slip(self, avg_adv: float, spread: float = 0.0) -> float:
        """
        Calculate bad slippage threshold based on ADV and Spread.
        
        Args:
            avg_adv: Average Daily Volume
            spread: Current spread in cents (optional, default 0.0)
            
        Returns:
            Bad slippage threshold in USD
        """
        # Default bad slip base
        adv_thresholds = self.config.get('slippage', {}).get('adv_thresholds', [])
        default_bad_slip = self.config.get('slippage', {}).get('adv_default_bad_slip', 0.12)
        
        base_bad_slip = default_bad_slip
        
        # Check ADV thresholds (first match wins)
        if adv_thresholds:
            for rule in adv_thresholds:
                if avg_adv >= rule.get('adv', 0):
                    base_bad_slip = rule.get('bad_slip', default_bad_slip)
                    break
        else:
            # Fallback hardcoded values if config missing
            if avg_adv >= 100000: base_bad_slip = 0.03
            elif avg_adv >= 40000: base_bad_slip = 0.05
            elif avg_adv >= 10000: base_bad_slip = 0.07
            elif avg_adv >= 2000: base_bad_slip = 0.10
            else: base_bad_slip = 0.12
        
        # Spread Floor
        multiplier = self.config.get('slippage', {}).get('spread_floor_multiplier', 0.25)
        spread_floor = spread * multiplier
        
        return max(base_bad_slip, spread_floor)

    def get_all_symbols(self) -> List[str]:
        """Get list of all symbols with tick data"""
        with self._tick_lock:
            return list(self.tick_store.keys())
    
    def get_effective_now(self) -> datetime:
        """
        Get "effective now" - trading-time aware current time.
        
        CRITICAL: If market is open, use real time.
        If market is closed, use last market close time.
        
        This ensures timeframes work correctly on weekends/holidays.
        
        Returns:
            Effective now datetime (NYSE timezone)
        """
        trading_calendar = get_trading_calendar()
        now_nyse = datetime.now(trading_calendar.NYSE_TZ)
        
        if trading_calendar.is_market_open(now_nyse):
            # Market is open - use real time
            return now_nyse
        else:
            # Market is closed - use last trading day close
            return trading_calendar.get_last_trading_day(now_nyse)
    
    def get_timeframe_start_trading_hours(self, timeframe_name: str) -> float:
        """
        Get timeframe start timestamp based on TRADING HOURS (not calendar time).
        
        CRITICAL: Timeframes are based on trading days/hours, not calendar time.
        - TF_4H = last 4 trading hours
        - TF_1D = last 1 trading day (market open to close)
        - TF_3D = last 3 trading days
        - TF_5D = last 5 trading days
        
        Uses "effective_now" - if market is closed, uses last market close.
        
        Args:
            timeframe_name: One of 'TF_4H', 'TF_1D', 'TF_3D', 'TF_5D'
            
        Returns:
            Unix timestamp for timeframe start (trading hours aware)
        """
        trading_calendar = get_trading_calendar()
        effective_now = self.get_effective_now()  # Trading-time aware "now"
        
        if timeframe_name == 'TF_4H':
            # Last 4 trading hours from effective_now
            # effective_now is already last trading day close if market is closed
            timeframe_start_dt = effective_now - timedelta(hours=4)
            
            # Don't go before market open of the trading day
            trading_day_start = trading_calendar.get_trading_day_start(effective_now)
            if timeframe_start_dt < trading_day_start:
                timeframe_start_dt = trading_day_start
            
            return timeframe_start_dt.timestamp()
        
        elif timeframe_name == 'TF_1D':
            # Last 1 trading day (market open to close)
            # effective_now is already last trading day close if market is closed
            trading_day_start = trading_calendar.get_trading_day_start(effective_now)
            return trading_day_start.timestamp()
        
        elif timeframe_name == 'TF_3D':
            # Last 3 trading days - get the first day's market open
            trading_days = trading_calendar.get_trading_days_back(3, effective_now)
            if trading_days:
                # Get market open for the oldest trading day
                oldest_day = trading_days[-1]  # Last in list = oldest
                trading_day_start = trading_calendar.get_trading_day_start(oldest_day)
                return trading_day_start.timestamp()
            else:
                # Fallback: 3 calendar days ago
                fallback = effective_now - timedelta(days=3)
                return fallback.timestamp()
        
        elif timeframe_name == 'TF_5D':
            # Last 5 trading days - get the first day's market open
            trading_days = trading_calendar.get_trading_days_back(5, effective_now)
            if trading_days:
                # Get market open for the oldest trading day
                oldest_day = trading_days[-1]  # Last in list = oldest
                trading_day_start = trading_calendar.get_trading_day_start(oldest_day)
                return trading_day_start.timestamp()
            else:
                # Fallback: 5 calendar days ago
                fallback = effective_now - timedelta(days=5)
                return fallback.timestamp()
        
        else:
            # Invalid timeframe - fallback to calendar time
            logger.warning(f"Invalid timeframe for trading hours: {timeframe_name}, using calendar time")
            timeframe_seconds = self.TIMEFRAMES.get(timeframe_name, 86400)
            return time.time() - timeframe_seconds
    
    def compute_metrics_for_timeframe(
        self,
        symbol: str,
        avg_adv: float,
        timeframe_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Compute Truth Ticks metrics for a symbol over a SPECIFIC TIMEFRAME.
        
        This is the NEW timeframe-based approach. All symbols are evaluated
        over the SAME time windows (4H, 1D, 3D, 5D).
        
        Args:
            symbol: Symbol name
            avg_adv: Average Daily Volume
            timeframe_name: One of 'TF_4H', 'TF_1D', 'TF_3D', 'TF_5D'
            
        Returns:
            Metrics dict or None if insufficient data
        """
        try:
            if timeframe_name not in self.TIMEFRAMES:
                logger.warning(f"Invalid timeframe: {timeframe_name}")
                return None
            
            timeframe_seconds = self.TIMEFRAMES[timeframe_name]
            
            with self._tick_lock:
                if symbol not in self.tick_store:
                    return None
                
                # Get all ticks
                all_ticks = list(self.tick_store[symbol])
            
            if not all_ticks:
                return None
            
            # Filter to TruthTicks
            truth_ticks_all = self.filter_truth_ticks(all_ticks)
            
            if not truth_ticks_all:
                return None
            
            # CRITICAL: Anchor-based timeframe calculation
            # Use LAST PRINT TIMESTAMP as anchor, not calendar time
            # This ensures timeframes work correctly even when market hasn't opened yet
            # or when there are gaps in trading activity
            
            # Get anchor timestamp (last print)
            anchor_timestamp = max([tick.get('ts', 0) for tick in truth_ticks_all])
            
            if anchor_timestamp <= 0:
                return None
            
            # Calculate timeframe window: anchor_time - timeframe_seconds to anchor_time
            timeframe_start = anchor_timestamp - timeframe_seconds
            current_time = anchor_timestamp  # Use anchor as "now" for filtering
            
            # Enhanced logging for debugging (first symbol only)
            if symbol == list(self.tick_store.keys())[0] if self.tick_store else False:
                anchor_dt = datetime.fromtimestamp(anchor_timestamp)
                timeframe_start_dt = datetime.fromtimestamp(timeframe_start)
                oldest_tick_ts = min([t.get('ts', 0) for t in truth_ticks_all]) if truth_ticks_all else 0
                newest_tick_ts = max([t.get('ts', 0) for t in truth_ticks_all]) if truth_ticks_all else 0
                oldest_tick_dt = datetime.fromtimestamp(oldest_tick_ts) if oldest_tick_ts > 0 else None
                newest_tick_dt = datetime.fromtimestamp(newest_tick_ts) if newest_tick_ts > 0 else None
                
                logger.info(f"🔍 [{symbol}][{timeframe_name}] Anchor-based timeframe:")
                logger.info(f"   anchor_timestamp (last print)={anchor_dt.isoformat()}")
                logger.info(f"   timeframe_start (anchor - {timeframe_seconds}s)={timeframe_start_dt.isoformat()}")
                logger.info(f"   total_truth_ticks={len(truth_ticks_all)}")
                logger.info(f"   oldest_tick={oldest_tick_dt.isoformat() if oldest_tick_dt else 'N/A'}, newest_tick={newest_tick_dt.isoformat() if newest_tick_dt else 'N/A'}")
            
            # Filter truth ticks to timeframe (ts >= timeframe_start and ts <= anchor_timestamp)
            # CRITICAL: Anchor-based filtering - window is [anchor_time - timeframe_seconds, anchor_time]
            truth_ticks_timeframe = [
                tick for tick in truth_ticks_all
                if timeframe_start <= tick.get('ts', 0) <= anchor_timestamp
            ]
            
            # Enhanced logging for filtered results (first symbol only)
            if symbol == list(self.tick_store.keys())[0] if self.tick_store else False:
                if truth_ticks_timeframe:
                    filtered_oldest = min([t.get('ts', 0) for t in truth_ticks_timeframe])
                    filtered_newest = max([t.get('ts', 0) for t in truth_ticks_timeframe])
                    filtered_oldest_dt = datetime.fromtimestamp(filtered_oldest)
                    filtered_newest_dt = datetime.fromtimestamp(filtered_newest)
                    logger.info(f"   filtered_ticks={len(truth_ticks_timeframe)}, filtered_oldest={filtered_oldest_dt.isoformat()}, filtered_newest={filtered_newest_dt.isoformat()}")
                else:
                    logger.warning(f"   ⚠️ No ticks after filtering! timeframe_start={datetime.fromtimestamp(timeframe_start).isoformat()}, anchor={datetime.fromtimestamp(anchor_timestamp).isoformat()}")
            
            # TIMEFRAME-FIRST: Use universal minimum threshold (15 ticks)
            # CRITICAL: If tick_count < 15, state = INSUFFICIENT_DATA but still return metrics
            truth_tick_count = len(truth_ticks_timeframe)
            
            # If no ticks at all, return None (can't compute anything)
            if truth_tick_count == 0:
                logger.debug(f"⚠️ [{symbol}][{timeframe_name}] No ticks in timeframe (timeframe_start={datetime.fromtimestamp(timeframe_start).isoformat() if timeframe_start else 'N/A'}, anchor={datetime.fromtimestamp(anchor_timestamp).isoformat() if anchor_timestamp else 'N/A'})")
                return None
            
            # Check if we have sufficient data (15 ticks minimum)
            # CRITICAL: Never return N/A if ticks exist - return INSUFFICIENT_DATA state instead
            insufficient_data = truth_tick_count < self.MIN_TICKS_FOR_SUFFICIENT_DATA
            
            # Log for debugging (first symbol only)
            if symbol == list(self.tick_store.keys())[0] if self.tick_store else False:
                logger.info(f"🔍 [{symbol}][{timeframe_name}] truth_ticks={truth_tick_count} required={self.MIN_TICKS_FOR_SUFFICIENT_DATA}, insufficient={insufficient_data}, timeframe_start={datetime.fromtimestamp(timeframe_start).isoformat() if timeframe_start else 'N/A'}")
            
            # If insufficient data, still compute but will set state = INSUFFICIENT_DATA
            if insufficient_data:
                logger.debug(f"⚠️ [{symbol}][{timeframe_name}] Insufficient ticks: {truth_tick_count} < {self.MIN_TICKS_FOR_SUFFICIENT_DATA} (will compute with INSUFFICIENT_DATA state)")
            
            # Basic metrics - WEIGHTED
            truth_volume = 0.0
            price_volume_sum = 0.0
            
            for tick in truth_ticks_timeframe:
                 size = tick.get('size', 0)
                 price = tick.get('price', 0)
                 weight = self.calculate_print_weight(size)
                 weighted_size = size * weight
                 
                 truth_volume += weighted_size
                 price_volume_sum += price * weighted_size
            
            # Truth VWAP
            truth_vwap = None
            if truth_volume > 0:
                truth_vwap = price_volume_sum / truth_volume
            
            # ADV fraction (RELATIVE weighted volume pressure)
            adv_fraction_truth = truth_volume / avg_adv if avg_adv > 0 else 0.0
            # Guard against NaN
            if not isinstance(adv_fraction_truth, (int, float)) or adv_fraction_truth != adv_fraction_truth:
                adv_fraction_truth = 0.0
            
            # Venue volume mix
            volume_by_exch: Dict[str, float] = defaultdict(float)
            for tick in truth_ticks_timeframe:
                exch = tick.get('exch', 'UNKNOWN')
                size = tick.get('size', 0)
                weight = self.calculate_print_weight(size, exch)
                volume_by_exch[exch] += size * weight
            
            venue_mix_pct: Dict[str, float] = {}
            if truth_volume > 0:
                for exch, volume in volume_by_exch.items():
                    venue_mix_pct[exch] = (volume / truth_volume) * 100
            
            # Volav levels
            volav_levels, _ = self.compute_volav_levels(truth_ticks_timeframe, top_n=4, avg_adv=avg_adv)
            min_volav_gap_used = self.min_volav_gap(avg_adv) if avg_adv > 0 else 0.05
            
            # Volav Timeline - DYNAMIC window count based on available ticks
            # CRITICAL: Don't force 5 windows if we don't have enough ticks
            # Preferred stocks are illiquid - adapt to available data
            if truth_tick_count >= 50:
                num_windows = 5  # Full 5 windows if we have enough ticks
            elif truth_tick_count >= 30:
                num_windows = 4  # 4 windows for medium data
            elif truth_tick_count >= 20:
                num_windows = 3  # 3 windows for limited data
            elif truth_tick_count >= 10:
                num_windows = 2  # 2 windows for very limited data
            else:
                num_windows = 1  # Single window for minimal data (still compute!)
            
            volav_timeline = self.compute_volav_timeline(truth_ticks_timeframe, num_windows=num_windows, avg_adv=avg_adv)
            
            # Filter out empty windows (robustness: ignore empty windows, but don't fail)
            if volav_timeline:
                volav_timeline = [w for w in volav_timeline if w.get('volav1') is not None]
            
            # Log window count for debugging
            if symbol == list(self.tick_store.keys())[0] if self.tick_store else False:
                logger.info(f"   [{symbol}][{timeframe_name}] windows={len(volav_timeline)} (requested={num_windows}, ticks={truth_tick_count})")
            
            # TIMEFRAME-FIRST: Volav1 Start/End from first/last 20% of ticks (not timeline windows)
            volav1_start = None
            volav1_end = None
            volav1_displacement = None
            volav_shift_abs = None
            volav_shift_dir = None
            normalized_displacement = None
            
            if truth_tick_count >= 2:
                # Sort ticks by timestamp (should already be sorted, but ensure)
                sorted_ticks = sorted(truth_ticks_timeframe, key=lambda t: t.get('ts', 0))
                
                # First 20% of ticks for Volav1_start
                first_20_percent_count = max(1, int(truth_tick_count * 0.2))
                first_20_percent_ticks = sorted_ticks[:first_20_percent_count]
                
                # Last 20% of ticks for Volav1_end
                last_20_percent_count = max(1, int(truth_tick_count * 0.2))
                last_20_percent_ticks = sorted_ticks[-last_20_percent_count:]
                
                # Compute Volav1 for first 20%
                if first_20_percent_ticks:
                    first_volav_levels, _ = self.compute_volav_levels(first_20_percent_ticks, top_n=1, avg_adv=avg_adv)
                    if first_volav_levels:
                        volav1_start = first_volav_levels[0]['price']
                
                # Compute Volav1 for last 20%
                if last_20_percent_ticks:
                    last_volav_levels, _ = self.compute_volav_levels(last_20_percent_ticks, top_n=1, avg_adv=avg_adv)
                    if last_volav_levels:
                        volav1_end = last_volav_levels[0]['price']
                
                # Guard against NaN
                if volav1_start is not None and (not isinstance(volav1_start, (int, float)) or (isinstance(volav1_start, float) and volav1_start != volav1_start)):
                    volav1_start = None
                if volav1_end is not None and (not isinstance(volav1_end, (int, float)) or (isinstance(volav1_end, float) and volav1_end != volav1_end)):
                    volav1_end = None
                
                # Compute displacement and normalized displacement
                if volav1_start is not None and volav1_end is not None:
                    volav1_displacement = volav1_end - volav1_start
                    # Guard against NaN
                    if isinstance(volav1_displacement, (int, float)) and volav1_displacement == volav1_displacement:
                        volav_shift_abs = abs(volav1_displacement)
                        
                        # Normalized displacement = displacement / min_volav_gap
                        if min_volav_gap_used > 0:
                            normalized_displacement = volav1_displacement / min_volav_gap_used
                        else:
                            normalized_displacement = 0.0
                        
                        # Guard against NaN in normalized_displacement
                        if not isinstance(normalized_displacement, (int, float)) or normalized_displacement != normalized_displacement:
                            normalized_displacement = 0.0
                        
                        if volav_shift_abs < self.FLAT_EPSILON:
                            volav_shift_dir = 'FLAT'
                        elif volav1_displacement > 0:
                            volav_shift_dir = 'UP'
                        else:
                            volav_shift_dir = 'DOWN'
                    else:
                        volav1_displacement = None
                        volav_shift_abs = None
                        volav_shift_dir = 'FLAT'
                        normalized_displacement = 0.0
            
            # TIMEFRAME-FIRST: State Classification with 10-state model
            # CRITICAL: Never return N/A if ticks exist - return INSUFFICIENT_DATA state instead
            state_name, state_confidence = self.classify_state_v2(
                normalized_displacement=normalized_displacement if normalized_displacement is not None else 0.0,
                adv_fraction=adv_fraction_truth,
                truth_tick_count=truth_tick_count,
                volav1_displacement=volav1_displacement,
                min_volav_gap_used=min_volav_gap_used
            )
            
            # Adjust confidence based on insufficient data (NO HARD EXIT)
            if insufficient_data and truth_tick_count > 0:
                # Reduce confidence proportionally: confidence *= (actual_ticks / required_ticks)
                confidence_multiplier = min(1.0, truth_tick_count / self.MIN_TICKS_FOR_SUFFICIENT_DATA)
                state_confidence = state_confidence * confidence_multiplier if state_confidence else 0.0
                logger.debug(f"   [{symbol}][{timeframe_name}] Confidence adjusted: {state_confidence:.3f} (multiplier={confidence_multiplier:.2f})")
            
            # Flags
            finra_dominant = False
            if truth_volume > 0:
                finra_volume = volume_by_exch.get('FNRA', 0)
                if finra_volume > 0:
                    finra_ratio = finra_volume / truth_volume
                    # Guard against NaN
                    if isinstance(finra_ratio, (int, float)) and finra_ratio == finra_ratio:
                        finra_dominant = finra_ratio > self.FINRA_DOMINANT_THRESHOLD
            
            flags = {
                'insufficient_data': insufficient_data,
                'insufficient_truth_ticks': insufficient_data,
                'finra_dominant': finra_dominant
            }
            
            # Calculate actual timeframe duration (with NaN guards)
            if truth_ticks_timeframe:
                first_tick_time = truth_ticks_timeframe[0].get('ts', 0)
                last_tick_time = truth_ticks_timeframe[-1].get('ts', 0)
                
                # Guard against invalid timestamps
                if isinstance(first_tick_time, (int, float)) and isinstance(last_tick_time, (int, float)):
                    actual_timeframe_seconds = last_tick_time - first_tick_time
                    # Guard against NaN
                    if not isinstance(actual_timeframe_seconds, (int, float)) or actual_timeframe_seconds != actual_timeframe_seconds:
                        actual_timeframe_seconds = timeframe_seconds  # Use requested timeframe
                    
                    # Format as "XdXhXm"
                    days = int(actual_timeframe_seconds // 86400)
                    hours = int((actual_timeframe_seconds % 86400) // 3600)
                    minutes = int((actual_timeframe_seconds % 3600) // 60)
                    
                    parts = []
                    if days > 0:
                        parts.append(f"{days}d")
                    if hours > 0:
                        parts.append(f"{hours}h")
                    if minutes > 0:
                        parts.append(f"{minutes}m")
                    
                    timeframe_str = "".join(parts) if parts else "0m"
                else:
                    actual_timeframe_seconds = timeframe_seconds
                    timeframe_str = timeframe_name.replace('TF_', '')
            else:
                actual_timeframe_seconds = timeframe_seconds
                timeframe_str = timeframe_name.replace('TF_', '')
            
            # Build result
            result = {
                'symbol': symbol,
                'timeframe_name': timeframe_name,
                'timeframe_seconds': timeframe_seconds,  # Requested timeframe
                'actual_timeframe_seconds': actual_timeframe_seconds,  # Actual data span
                'timeframe': timeframe_str,  # Formatted duration
                'anchor_timestamp': anchor_timestamp,  # CRITICAL: Last print timestamp (anchor)
                'timeframe_start': timeframe_start,  # Timeframe window start (anchor - timeframe_seconds)
                'avg_adv': avg_adv,
                'min_volav_gap_used': min_volav_gap_used,
                'truth_tick_count': truth_tick_count,
                'truth_volume': truth_volume,
                'truth_vwap': truth_vwap,
                'adv_fraction_truth': adv_fraction_truth,
                'venue_mix_pct': venue_mix_pct,
                'volav_levels': volav_levels,
                'volav_timeline': volav_timeline,
                'volav1_start': volav1_start,
                'volav1_end': volav1_end,
                'volav1_displacement': volav1_displacement,
                'volav_shift_abs': volav_shift_abs,
                'volav_shift_dir': volav_shift_dir,
                'normalized_displacement': normalized_displacement if normalized_displacement is not None else 0.0,
                'net_pressure_truth': None,
                'state': state_name,
                'state_confidence': state_confidence,
                'flags': flags,
                'truth_ticks': truth_ticks_timeframe,  # CRITICAL: Add truth_ticks list for MM engine
                'updated_at': datetime.now().isoformat()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error computing timeframe metrics for {symbol} ({timeframe_name}): {e}", exc_info=True)
            return None


# Singleton instance
_truth_ticks_engine_instance: Optional[TruthTicksEngine] = None


def get_truth_ticks_engine() -> TruthTicksEngine:
    """Get singleton TruthTicksEngine instance"""
    global _truth_ticks_engine_instance
    if _truth_ticks_engine_instance is None:
        _truth_ticks_engine_instance = TruthTicksEngine()
    return _truth_ticks_engine_instance

