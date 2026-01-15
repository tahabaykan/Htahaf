"""
Sidehit Press Engine
====================

MM (Market Making) Flow Scanner with two operating modes:
- ANALYSIS_ONLY: Weekend/market-closed pure flow analysis
- EXECUTION: Live MM signal generation with BUY_FADE/SELL_FADE

Core Philosophy:
1) FLOW NEREYE KAYIYOR? → VOLAV DRIFT (time-based)
2) ŞU ANKİ BID/ASK FLOW'A GÖRE NEREDE? → ZONE DISTANCE
3) HİSSE KENDİ GRUBUNA GÖRE NASIL DAVRANIYOR? → GROUP-RELATIVE ANALYSIS
4) SIDEHIT PRESS VAR MI? → Fbtot/SFStot ile isteğe bağlı filtreleme
"""

from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict
from datetime import datetime
import time
import statistics

from app.core.logger import logger
from app.mm.sidehit_press_models import (
    EngineMode, SidehitPressMode, SignalType, GroupStatus,
    TimeframeVolav, TimeframeDrift, GroupContext, AnalysisSummary,
    ZoneDistance, SidehitFactors, SymbolAnalysis, GroupSummary,
    SidehitPressResponse
)
from app.mm.sidehit_press_config import get_sidehit_config, SidehitPressConfig


class SidehitPressEngine:
    """
    Sidehit Press Engine - MM Flow Scanner
    
    Works in two modes:
    - ANALYSIS_ONLY: No L1 required, pure drift/group analysis
    - EXECUTION: L1 required, generates MM signals
    """
    
    def __init__(self, config: Optional[SidehitPressConfig] = None):
        """Initialize Sidehit Press Engine"""
        self.config = config or get_sidehit_config()
        logger.info("SidehitPressEngine initialized")
    
    # =========================================================================
    # VOLAV CALCULATION
    # =========================================================================
    
    def compute_volav(
        self,
        ticks: List[Dict[str, Any]],
        timeframe_seconds: int,
        anchor_timestamp: Optional[float] = None,
        avg_adv: float = 0.0
    ) -> TimeframeVolav:
        """
        Compute VOLAV (Volume-Averaged Level) for a timeframe.
        
        Args:
            ticks: List of truth ticks with 'ts', 'price', 'size', 'exch'
            timeframe_seconds: Timeframe window in seconds
            anchor_timestamp: Anchor time (default: max tick timestamp)
            avg_adv: Average Daily Volume for bucket sizing
            
        Returns:
            TimeframeVolav with volav_price, band_low, band_high
        """
        if not ticks:
            return TimeframeVolav(timeframe=f"TF_{timeframe_seconds//60}M", tick_count=0)
        
        # Determine anchor (latest tick timestamp)
        if anchor_timestamp is None:
            anchor_timestamp = max(t.get('ts', 0) for t in ticks)
        
        # Filter ticks to timeframe window
        window_start = anchor_timestamp - timeframe_seconds
        window_ticks = [
            t for t in ticks
            if window_start <= t.get('ts', 0) <= anchor_timestamp
        ]
        
        if len(window_ticks) < self.config.MIN_TICKS_PER_TIMEFRAME:
            return TimeframeVolav(
                timeframe=f"TF_{timeframe_seconds//60}M",
                tick_count=len(window_ticks)
            )
        
        # Determine bucket size based on liquidity
        bucket_size = self._get_bucket_size(avg_adv)
        
        # Bucket aggregation with weighted volume
        buckets: Dict[float, Dict[str, float]] = defaultdict(
            lambda: {'volume': 0.0, 'price_sum': 0.0}
        )
        
        total_weighted_volume = 0.0
        
        for tick in window_ticks:
            price = tick.get('price', 0)
            size = tick.get('size', 0)
            venue = tick.get('exch', 'UNKNOWN')
            
            if price <= 0 or size < self.config.MIN_TICK_SIZE:
                continue
            
            # Calculate weight
            weight = self._calculate_print_weight(size, venue)
            weighted_size = size * weight
            
            if weighted_size <= 0:
                continue
            
            # Bucket key
            bucket_key = round(price / bucket_size) * bucket_size
            
            buckets[bucket_key]['volume'] += weighted_size
            buckets[bucket_key]['price_sum'] += price * weighted_size
            total_weighted_volume += weighted_size
        
        if not buckets or total_weighted_volume <= 0:
            return TimeframeVolav(
                timeframe=f"TF_{timeframe_seconds//60}M",
                tick_count=len(window_ticks)
            )
        
        # Find VOLAV price (bucket with highest weighted volume)
        sorted_buckets = sorted(
            buckets.items(),
            key=lambda x: x[1]['volume'],
            reverse=True
        )
        
        volav_bucket_key = sorted_buckets[0][0]
        volav_data = sorted_buckets[0][1]
        volav_price = volav_data['price_sum'] / volav_data['volume']
        
        # Calculate band (60% coverage)
        band_low, band_high = self._calculate_band(
            sorted_buckets,
            total_weighted_volume,
            self.config.BAND_COVERAGE_PCT
        )
        
        dispersion = band_high - band_low if band_low and band_high else 0.0
        
        # Determine timeframe name
        if timeframe_seconds <= 900:
            tf_name = "TF_15M"
        elif timeframe_seconds <= 3600:
            tf_name = "TF_1H"
        elif timeframe_seconds <= 14400:
            tf_name = "TF_4H"
        else:
            tf_name = "TF_1D"
        
        return TimeframeVolav(
            timeframe=tf_name,
            volav_price=round(volav_price, 4),
            band_low=round(band_low, 4) if band_low else None,
            band_high=round(band_high, 4) if band_high else None,
            dispersion=round(dispersion, 4),
            tick_count=len(window_ticks),
            weighted_volume=round(total_weighted_volume, 2)
        )
    
    def _get_bucket_size(self, avg_adv: float) -> float:
        """Get bucket size based on liquidity"""
        if avg_adv < 1000:
            return self.config.BUCKET_SIZE_VERY_ILLIQUID
        elif avg_adv < 5000:
            return self.config.BUCKET_SIZE_ILLIQUID
        else:
            return self.config.BUCKET_SIZE_DEFAULT
    
    def _calculate_print_weight(self, size: float, venue: str) -> float:
        """
        Calculate realism weight using CENTRAL TruthTicksEngine logic.
        Delegates to the single source of truth to avoid duplication.
        """
        # Lazy import to avoid circular dependency
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        
        engine = get_truth_ticks_engine()
        return engine.calculate_print_weight(size, venue)
    
    def _calculate_band(
        self,
        sorted_buckets: List[Tuple[float, Dict[str, float]]],
        total_volume: float,
        coverage_pct: float
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculate volume band covering coverage_pct of volume"""
        if not sorted_buckets or total_volume <= 0:
            return None, None
        
        target_volume = total_volume * coverage_pct
        accumulated_volume = 0.0
        prices_in_band = []
        
        for bucket_key, bucket_data in sorted_buckets:
            accumulated_volume += bucket_data['volume']
            vwap = bucket_data['price_sum'] / bucket_data['volume']
            prices_in_band.append(vwap)
            
            if accumulated_volume >= target_volume:
                break
        
        if not prices_in_band:
            return None, None
        
        return min(prices_in_band), max(prices_in_band)
    
    # =========================================================================
    # DRIFT CALCULATION
    # =========================================================================
    
    def compute_drift(
        self,
        volav_15m: Optional[TimeframeVolav],
        volav_1h: Optional[TimeframeVolav],
        volav_4h: Optional[TimeframeVolav],
        volav_1d: Optional[TimeframeVolav]
    ) -> TimeframeDrift:
        """
        Compute drift between timeframes.
        
        Negative drift = flow moving DOWN
        Positive drift = flow moving UP
        """
        drift = TimeframeDrift()
        
        # 15m vs 1h
        if (volav_15m and volav_15m.volav_price is not None and
            volav_1h and volav_1h.volav_price is not None):
            drift.drift_15_60 = round(
                volav_15m.volav_price - volav_1h.volav_price, 4
            )
        
        # 1h vs 4h
        if (volav_1h and volav_1h.volav_price is not None and
            volav_4h and volav_4h.volav_price is not None):
            drift.drift_60_240 = round(
                volav_1h.volav_price - volav_4h.volav_price, 4
            )
        
        # 4h vs 1d
        if (volav_4h and volav_4h.volav_price is not None and
            volav_1d and volav_1d.volav_price is not None):
            drift.drift_240_1d = round(
                volav_4h.volav_price - volav_1d.volav_price, 4
            )
        
        return drift
    
    # =========================================================================
    # LAST 5 TICK ANALYSIS
    # =========================================================================
    
    def compute_last5_tick(
        self,
        ticks: List[Dict[str, Any]],
        volav_15m: Optional[TimeframeVolav],
        volav_1h: Optional[TimeframeVolav]
    ) -> Dict[str, Optional[float]]:
        """
        Compute last 5 truth tick analysis.
        
        Uses MODE (most frequent price) for better accuracy (like GRPAN logic).
        Falls back to average if mode cannot be determined.
        
        Returns:
            Dict with last5_avg, last5_vs_15m, last5_vs_1h
        """
        result = {
            'last5_avg': None,
            'last5_vs_15m': None,
            'last5_vs_1h': None
        }
        
        if not ticks or len(ticks) < 1:
            return result
        
        # Flexible truth tick filtering using CENTRAL logic
        # Lazy import
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        engine = get_truth_ticks_engine()

        truth_ticks = []
        for tick in ticks:
            size = tick.get('size', tick.get('qty', 0))
            # Support various exchange key formats
            exch = tick.get('exch') or tick.get('venue') or tick.get('exchange') or ''
            venue = str(exch).upper()
            price = tick.get('price', 0)
            
            if price <= 0:
                continue
            
            # Construct a temp tick for validation
            candidate = {'size': size, 'exch': venue}
            
            if engine.is_truth_tick(candidate):
                truth_ticks.append(tick)
        
        # If no truth ticks found, use all ticks with valid prices (fallback)
        if len(truth_ticks) < 1:
            truth_ticks = [t for t in ticks if t.get('price', 0) > 0]
        
        if not truth_ticks:
            return result
        
        # Sort by timestamp descending and get last 5
        sorted_ticks = sorted(
            truth_ticks, 
            key=lambda t: t.get('ts', t.get('timestamp', 0)), 
            reverse=True
        )
        last5 = sorted_ticks[:5]
        
        # Calculate prices
        prices = [t.get('price', 0) for t in last5 if t.get('price', 0) > 0]
        
        if not prices:
            return result
        
        # Calculate MODE (most frequent price) - like GRPAN logic
        # Round prices to 2 decimals for grouping
        rounded_prices = [round(p, 2) for p in prices]
        from collections import Counter
        price_counts = Counter(rounded_prices)
        
        if price_counts:
            # Get most common price (mode)
            mode_price = price_counts.most_common(1)[0][0]
            result['last5_avg'] = round(mode_price, 4)
        else:
            # Fallback to average
            result['last5_avg'] = round(sum(prices) / len(prices), 4)
        
        # Compare to VOLAVs
        if result['last5_avg'] and volav_15m and volav_15m.volav_price:
            result['last5_vs_15m'] = round(result['last5_avg'] - volav_15m.volav_price, 4)
        
        if result['last5_avg'] and volav_1h and volav_1h.volav_price:
            result['last5_vs_1h'] = round(result['last5_avg'] - volav_1h.volav_price, 4)
        
        return result
    
    # =========================================================================
    # GROUP ANALYSIS
    # =========================================================================
    
    def resolve_group(self, symbol: str, static_data: Dict[str, Any]) -> str:
        """
        Resolve symbol's group for comparison.
        
        Uses grouping module which:
        - Looks up symbol in ~22 group CSV files
        - HELDKUPONLU/kuponlu groups use CGRUP for sub-grouping (e.g., heldkuponlu:c450)
        """
        try:
            from app.market_data.grouping import resolve_group_key
            
            # Add symbol to static_data if not present
            static_with_symbol = dict(static_data)
            if 'PREF_IBKR' not in static_with_symbol and 'PREF IBKR' not in static_with_symbol:
                static_with_symbol['PREF_IBKR'] = symbol
            
            group_key = resolve_group_key(static_with_symbol)
            if group_key:
                return group_key
        except Exception as e:
            logger.debug(f"Error resolving group for {symbol}: {e}")
        
        return 'OTHER'
    
    def compute_group_drifts(
        self,
        symbol_drifts: Dict[str, TimeframeDrift]
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute median drifts for each group.
        
        Args:
            symbol_drifts: {symbol: TimeframeDrift}
            
        Returns:
            {group_id: {'median_15_60': float, 'median_60_240': float}}
        """
        # Group symbols by group_id (assumes already resolved)
        group_data: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: {'drift_15_60': [], 'drift_60_240': []}
        )
        
        # This would need group info - for now we return empty
        # In practice, this is called by the main analyze method which has group info
        return {}
    
    def compute_group_context(
        self,
        symbol: str,
        symbol_drift: TimeframeDrift,
        group_id: str,
        group_symbols_drifts: List[TimeframeDrift]
    ) -> GroupContext:
        """
        Compute group-relative analysis for a symbol.
        
        Uses MEDIAN (not mean) for robustness against outliers.
        """
        context = GroupContext(group_id=group_id, group_size=len(group_symbols_drifts))
        
        if len(group_symbols_drifts) < self.config.MIN_GROUP_SIZE:
            logger.debug(f"Group {group_id} too small ({len(group_symbols_drifts)} < {self.config.MIN_GROUP_SIZE})")
            return context
        
        # Collect non-None drifts
        drifts_15_60 = [d.drift_15_60 for d in group_symbols_drifts if d.drift_15_60 is not None]
        drifts_60_240 = [d.drift_60_240 for d in group_symbols_drifts if d.drift_60_240 is not None]
        
        # Compute group medians
        if len(drifts_15_60) >= 2:
            context.group_drift_15_60 = round(statistics.median(drifts_15_60), 4)
        
        if len(drifts_60_240) >= 2:
            context.group_drift_60_240 = round(statistics.median(drifts_60_240), 4)
        
        # Compute relative drifts
        if symbol_drift.drift_15_60 is not None and context.group_drift_15_60 is not None:
            context.rel_drift_15_60 = round(
                symbol_drift.drift_15_60 - context.group_drift_15_60, 4
            )
            context.status_15_60 = self._classify_group_status(context.rel_drift_15_60)
        
        if symbol_drift.drift_60_240 is not None and context.group_drift_60_240 is not None:
            context.rel_drift_60_240 = round(
                symbol_drift.drift_60_240 - context.group_drift_60_240, 4
            )
            context.status_60_240 = self._classify_group_status(context.rel_drift_60_240)
        
        # Compute rank within group
        if symbol_drift.drift_15_60 is not None and drifts_15_60:
            rank = sum(1 for d in drifts_15_60 if d < symbol_drift.drift_15_60)
            context.group_relative_rank = round(rank / len(drifts_15_60), 2)
        
        return context
    
    def _classify_group_status(self, rel_drift: float) -> GroupStatus:
        """Classify symbol's status relative to group"""
        if abs(rel_drift) < self.config.GROUP_DEVIATION_THRESHOLD:
            return GroupStatus.IN_LINE_WITH_GROUP
        elif rel_drift > 0:
            return GroupStatus.OVERPERFORM_GROUP
        else:
            return GroupStatus.UNDERPERFORM_GROUP
    
    # =========================================================================
    # ANALYSIS SUMMARY
    # =========================================================================
    
    def compute_analysis_summary(
        self,
        group_context: GroupContext,
        drift: TimeframeDrift
    ) -> AnalysisSummary:
        """Compute summary fields for ANALYSIS_ONLY mode"""
        summary = AnalysisSummary()
        
        # Find strongest over/underperform timeframe
        status_map = {
            '15_60': group_context.status_15_60,
            '60_240': group_context.status_60_240
        }
        
        rel_drift_map = {
            '15_60': group_context.rel_drift_15_60,
            '60_240': group_context.rel_drift_60_240
        }
        
        # Find strongest overperform
        overperform_tfs = [
            (tf, rel_drift_map.get(tf, 0) or 0)
            for tf, status in status_map.items()
            if status == GroupStatus.OVERPERFORM_GROUP
        ]
        if overperform_tfs:
            summary.strongest_overperform_tf = max(overperform_tfs, key=lambda x: x[1])[0]
        
        # Find strongest underperform
        underperform_tfs = [
            (tf, rel_drift_map.get(tf, 0) or 0)
            for tf, status in status_map.items()
            if status == GroupStatus.UNDERPERFORM_GROUP
        ]
        if underperform_tfs:
            summary.strongest_underperform_tf = min(underperform_tfs, key=lambda x: x[1])[0]
        
        # Drift consistency
        directions = []
        for d in [drift.drift_15_60, drift.drift_60_240, drift.drift_240_1d]:
            if d is not None:
                if d > self.config.DRIFT_THRESHOLD_SIGNIFICANT:
                    directions.append('UP')
                elif d < -self.config.DRIFT_THRESHOLD_SIGNIFICANT:
                    directions.append('DOWN')
                else:
                    directions.append('FLAT')
        
        if directions:
            up_count = directions.count('UP')
            down_count = directions.count('DOWN')
            summary.drift_consistency_score = max(up_count, down_count)
            
            if up_count > down_count:
                summary.overall_drift_direction = 'UP'
            elif down_count > up_count:
                summary.overall_drift_direction = 'DOWN'
            else:
                summary.overall_drift_direction = 'MIXED'
        
        return summary
    
    # =========================================================================
    # ZONE DISTANCE (EXECUTION MODE)
    # =========================================================================
    
    def compute_zone_distance(
        self,
        bid: float,
        ask: float,
        volav_15m: Optional[TimeframeVolav],
        volav_1h: Optional[TimeframeVolav]
    ) -> ZoneDistance:
        """Compute normalized zone distances (EXECUTION mode only)"""
        spread = ask - bid
        mid = (bid + ask) / 2
        
        zone = ZoneDistance(
            bid=bid,
            ask=ask,
            spread=round(spread, 4),
            mid=round(mid, 4)
        )
        
        # Normalize by spread (with floor)
        norm_spread = max(spread, self.config.MIN_SPREAD_FLOOR)
        
        if volav_15m and volav_15m.volav_price is not None:
            zone.z_bid_15m = round((bid - volav_15m.volav_price) / norm_spread, 2)
            zone.z_ask_15m = round((ask - volav_15m.volav_price) / norm_spread, 2)
        
        if volav_1h and volav_1h.volav_price is not None:
            zone.z_bid_1h = round((bid - volav_1h.volav_price) / norm_spread, 2)
            zone.z_ask_1h = round((ask - volav_1h.volav_price) / norm_spread, 2)
        
        return zone
    
    # =========================================================================
    # SIDEHIT FACTORS (EXECUTION MODE, ACTIVE)
    # =========================================================================
    
    def compute_sidehit_factors(
        self,
        fbtot: Optional[float],
        sfstot: Optional[float],
        sidehit_mode: SidehitPressMode
    ) -> SidehitFactors:
        """Compute Sidehit influence factors"""
        factors = SidehitFactors(fbtot=fbtot, sfstot=sfstot)
        
        if sidehit_mode == SidehitPressMode.PASSIVE:
            # PASSIVE: No score modification
            factors.sidehit_factor = 1.0
        else:
            # ACTIVE: Apply Fbtot/SFStot influence
            if fbtot is not None and sfstot is not None:
                raw_factor = 1.0 - abs(fbtot - sfstot) * self.config.SIDEHIT_K_FACTOR
                factors.sidehit_factor = max(
                    self.config.SIDEHIT_MIN_FACTOR,
                    min(self.config.SIDEHIT_MAX_FACTOR, raw_factor)
                )
        
        return factors
    
    # =========================================================================
    # MM SCORE & SIGNAL (EXECUTION MODE)
    # =========================================================================
    
    def compute_mm_score(
        self,
        zone_distance: ZoneDistance,
        drift: TimeframeDrift,
        group_context: GroupContext,
        sidehit_factors: SidehitFactors
    ) -> Tuple[float, SignalType, str]:
        """
        Compute MM score and signal type (EXECUTION mode only).
        
        Returns:
            (mm_score, signal_type, rationale)
        """
        # Component scores
        inefficiency_score = self._compute_inefficiency_score(zone_distance, drift)
        flow_alignment_score = self._compute_flow_alignment_score(drift)
        group_context_score = self._compute_group_context_score(group_context)
        
        # Weighted sum
        raw_score = (
            self.config.WEIGHT_INEFFICIENCY * inefficiency_score +
            self.config.WEIGHT_FLOW_ALIGNMENT * flow_alignment_score +
            self.config.WEIGHT_GROUP_CONTEXT * group_context_score
        ) * 100
        
        # Apply sidehit factor
        final_score = raw_score * sidehit_factors.sidehit_factor
        final_score = max(0.0, min(100.0, final_score))
        
        # Determine signal type
        signal_type, rationale = self._determine_signal(
            zone_distance, drift, group_context, final_score
        )
        
        return round(final_score, 2), signal_type, rationale
    
    def _compute_inefficiency_score(
        self,
        zone_distance: ZoneDistance,
        drift: TimeframeDrift
    ) -> float:
        """Score based on price deviation from VOLAV"""
        if zone_distance.z_ask_15m is None and zone_distance.z_bid_15m is None:
            return 0.0
        
        # Higher deviation = higher inefficiency opportunity
        max_z = max(
            abs(zone_distance.z_ask_15m or 0),
            abs(zone_distance.z_bid_15m or 0)
        )
        
        # Normalize to 0-1
        return min(1.0, max_z / self.config.ZONE_DISTANCE_STRONG)
    
    def _compute_flow_alignment_score(self, drift: TimeframeDrift) -> float:
        """Score based on drift alignment"""
        if drift.drift_15_60 is None:
            return 0.0
        
        # Stronger drift = higher confidence
        return min(1.0, abs(drift.drift_15_60) / self.config.DRIFT_THRESHOLD_STRONG)
    
    def _compute_group_context_score(self, group_context: GroupContext) -> float:
        """Score based on group deviation"""
        if group_context.rel_drift_15_60 is None:
            return 0.5  # Neutral
        
        # Higher deviation from group = more opportunity
        return min(1.0, abs(group_context.rel_drift_15_60) / self.config.GROUP_DEVIATION_STRONG)
    
    def _determine_signal(
        self,
        zone_distance: ZoneDistance,
        drift: TimeframeDrift,
        group_context: GroupContext,
        score: float
    ) -> Tuple[SignalType, str]:
        """Determine signal type and rationale"""
        if score < 30:
            return SignalType.NO_TRADE, "Score too low"
        
        if score < 50:
            return SignalType.WATCH, f"Moderate opportunity (score={score:.1f})"
        
        # Determine direction
        drift_down = (drift.drift_15_60 or 0) < -self.config.DRIFT_THRESHOLD_SIGNIFICANT
        drift_up = (drift.drift_15_60 or 0) > self.config.DRIFT_THRESHOLD_SIGNIFICANT
        
        ask_extended = (zone_distance.z_ask_15m or 0) > self.config.ZONE_DISTANCE_THRESHOLD
        bid_extended = (zone_distance.z_bid_15m or 0) < -self.config.ZONE_DISTANCE_THRESHOLD
        
        if drift_down and ask_extended:
            return SignalType.SELL_FADE, f"Flow down, ask extended (z={zone_distance.z_ask_15m:.1f})"
        
        if drift_up and bid_extended:
            return SignalType.BUY_FADE, f"Flow up, bid extended (z={zone_distance.z_bid_15m:.1f})"
        
        return SignalType.WATCH, f"No clear fade setup (score={score:.1f})"
    
    # =========================================================================
    # MAIN ANALYSIS METHOD
    # =========================================================================
    
    def analyze_symbol(
        self,
        symbol: str,
        ticks: List[Dict[str, Any]],
        static_data: Dict[str, Any],
        mode: EngineMode = EngineMode.ANALYSIS_ONLY,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        fbtot: Optional[float] = None,
        sfstot: Optional[float] = None,
        sidehit_mode: SidehitPressMode = SidehitPressMode.PASSIVE,
        group_symbols_drifts: Optional[List[TimeframeDrift]] = None
    ) -> SymbolAnalysis:
        """
        Main analysis method for a single symbol.
        
        Args:
            symbol: Symbol name
            ticks: List of truth ticks
            static_data: Static data with DOS_GRUP, CGRUP, AVG_ADV
            mode: ANALYSIS_ONLY or EXECUTION
            bid, ask: L1 data (required for EXECUTION mode)
            fbtot, sfstot: Valuation scores (for ACTIVE sidehit)
            sidehit_mode: PASSIVE or ACTIVE
            group_symbols_drifts: Drifts from other symbols in same group
            
        Returns:
            SymbolAnalysis
        """
        analysis = SymbolAnalysis(symbol=symbol, mode=mode)
        avg_adv = static_data.get('AVG_ADV', 0)
        
        try:
            # Get anchor timestamp
            if ticks:
                anchor_ts = max(t.get('ts', 0) for t in ticks)
            else:
                anchor_ts = time.time()
            
            # Compute VOLAV for each timeframe
            analysis.volav_15m = self.compute_volav(
                ticks, self.config.TIMEFRAMES['TF_15M'], anchor_ts, avg_adv
            )
            analysis.volav_1h = self.compute_volav(
                ticks, self.config.TIMEFRAMES['TF_1H'], anchor_ts, avg_adv
            )
            analysis.volav_4h = self.compute_volav(
                ticks, self.config.TIMEFRAMES['TF_4H'], anchor_ts, avg_adv
            )
            analysis.volav_1d = self.compute_volav(
                ticks, self.config.TIMEFRAMES['TF_1D'], anchor_ts, avg_adv
            )
            
            # Compute drift
            analysis.drift = self.compute_drift(
                analysis.volav_15m,
                analysis.volav_1h,
                analysis.volav_4h,
                analysis.volav_1d
            )
            
            # Compute group context
            group_id = self.resolve_group(symbol, static_data)
            
            if group_symbols_drifts:
                analysis.group = self.compute_group_context(
                    symbol,
                    analysis.drift,
                    group_id,
                    group_symbols_drifts
                )
            else:
                analysis.group = GroupContext(group_id=group_id)
            
            # Compute last 5 tick analysis
            last5_data = self.compute_last5_tick(
                ticks, analysis.volav_15m, analysis.volav_1h
            )
            analysis.last5_tick_avg = last5_data.get('last5_avg')
            analysis.last5_vs_15m = last5_data.get('last5_vs_15m')
            analysis.last5_vs_1h = last5_data.get('last5_vs_1h')
            
            # ANALYSIS_ONLY mode: compute summary
            if mode == EngineMode.ANALYSIS_ONLY:
                analysis.summary = self.compute_analysis_summary(
                    analysis.group,
                    analysis.drift
                )
                analysis.rationale = self._build_analysis_rationale(analysis)
            
            # EXECUTION mode: compute zone distance, sidehit, score
            elif mode == EngineMode.EXECUTION:
                if bid is None or ask is None:
                    analysis.rationale = "L1 data required for EXECUTION mode"
                    analysis.signal_type = SignalType.NO_TRADE
                else:
                    # Zone distance
                    analysis.zone_distance = self.compute_zone_distance(
                        bid, ask, analysis.volav_15m, analysis.volav_1h
                    )
                    
                    # Sidehit factors
                    analysis.sidehit = self.compute_sidehit_factors(
                        fbtot, sfstot, sidehit_mode
                    )
                    
                    # MM Score
                    mm_score, signal_type, rationale = self.compute_mm_score(
                        analysis.zone_distance,
                        analysis.drift,
                        analysis.group,
                        analysis.sidehit
                    )
                    
                    analysis.mm_score = mm_score
                    analysis.signal_type = signal_type
                    analysis.rationale = rationale
            
            # Debug metrics
            analysis.debug_metrics = {
                'tick_count_15m': analysis.volav_15m.tick_count if analysis.volav_15m else 0,
                'tick_count_1h': analysis.volav_1h.tick_count if analysis.volav_1h else 0,
                'tick_count_4h': analysis.volav_4h.tick_count if analysis.volav_4h else 0,
                'tick_count_1d': analysis.volav_1d.tick_count if analysis.volav_1d else 0,
                'avg_adv': avg_adv,
                'group_id': group_id
            }
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}", exc_info=True)
            analysis.rationale = f"Error: {str(e)}"
        
        return analysis
    
    def _build_analysis_rationale(self, analysis: SymbolAnalysis) -> str:
        """Build human-readable rationale for ANALYSIS_ONLY mode"""
        parts = []
        
        # Drift direction
        if analysis.drift:
            if analysis.drift.drift_15_60 is not None:
                direction = "UP" if analysis.drift.drift_15_60 > 0 else "DOWN"
                parts.append(f"15m→1h: {direction} ({analysis.drift.drift_15_60:+.3f})")
        
        # Group status
        if analysis.group:
            if analysis.group.status_15_60 == GroupStatus.OVERPERFORM_GROUP:
                parts.append(f"OVERPERFORM vs {analysis.group.group_id}")
            elif analysis.group.status_15_60 == GroupStatus.UNDERPERFORM_GROUP:
                parts.append(f"UNDERPERFORM vs {analysis.group.group_id}")
        
        # Summary
        if analysis.summary:
            if analysis.summary.overall_drift_direction:
                parts.append(f"Overall: {analysis.summary.overall_drift_direction}")
        
        return " | ".join(parts) if parts else "Insufficient data"


# Global instance
_engine: Optional[SidehitPressEngine] = None


def get_sidehit_press_engine() -> SidehitPressEngine:
    """Get global Sidehit Press Engine instance"""
    global _engine
    if _engine is None:
        _engine = SidehitPressEngine()
    return _engine


def initialize_sidehit_press_engine(config: Optional[SidehitPressConfig] = None):
    """Initialize global Sidehit Press Engine"""
    global _engine
    _engine = SidehitPressEngine(config)
    logger.info("SidehitPressEngine initialized globally")
    return _engine
