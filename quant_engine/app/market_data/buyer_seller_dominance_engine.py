"""
Buyer-Seller Dominance Scoring Engine

Assigns each symbol a dominance score between 1 and 100:
- 1   = Extreme Seller Dominance
- 50  = Neutral / Mixed
- 100 = Extreme Buyer Dominance

CRITICAL PRINCIPLES:
- All volume must be evaluated RELATIVE to the stock's own AVG_ADV
- Absolute volume comparisons across symbols are invalid
- Most recent behavior must carry the highest weight
- A single large print must NEVER dominate the score alone
"""

from typing import Dict, Any, Optional, List
import math
from app.core.logger import logger


class BuyerSellerDominanceEngine:
    """
    Buyer-Seller Dominance Scoring Engine for low-liquidity preferred stocks.
    
    Computes a 1-100 dominance score based on Truth Ticks Engine metrics.
    ALL calculations are normalized by AVG_ADV.
    """
    
    # Time weights for windows (recent activity is more important)
    # DEPRECATED: Use exponential decay with half-life instead
    TIME_WEIGHTS = {
        4: 1.0,   # Most recent window
        3: 0.7,
        2: 0.4,
        1: 0.2,
        0: 0.1   # Oldest window
    }
    
    # Exponential decay half-lives (in hours) based on AVG_ADV
    # Higher ADV = shorter half-life (more reactive)
    HALF_LIFE_HOURS = {
        'high': 2,      # avg_adv > 50k
        'medium': 6,    # avg_adv 10k-50k
        'low': 12       # avg_adv < 10k
    }
    
    def __init__(self):
        """Initialize Buyer-Seller Dominance Engine"""
        logger.info("BuyerSellerDominanceEngine initialized (AVG_ADV normalized)")
    
    def compute_dominance_score_for_timeframe(
        self,
        truth_metrics: Dict[str, Any],
        pff_return: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Compute buyer-seller dominance score for a SPECIFIC TIMEFRAME.
        
        This is the NEW timeframe-based approach. All calculations are normalized by AVG_ADV.
        
        Args:
            truth_metrics: Metrics dict from TruthTicksEngine.compute_metrics_for_timeframe()
            pff_return: Optional PFF ETF return over same timeframe
            
        Returns:
            Dict with dominance score and sub-scores, or None if insufficient data
        """
        return self._compute_dominance_score_internal(truth_metrics, pff_return)
    
    def compute_dominance_score(
        self,
        truth_metrics: Dict[str, Any],
        pff_return: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        DEPRECATED: Use compute_dominance_score_for_timeframe() instead.
        
        Legacy method for backward compatibility.
        """
        return self._compute_dominance_score_internal(truth_metrics, pff_return)
    
    def _compute_dominance_score_internal(
        self,
        truth_metrics: Dict[str, Any],
        pff_return: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Compute buyer-seller dominance score from Truth Ticks metrics.
        
        ALL calculations are normalized by AVG_ADV.
        
        Args:
            truth_metrics: Metrics dict from TruthTicksEngine.compute_metrics()
            pff_return: Optional PFF ETF return over same timeframe (for relative strength)
            
        Returns:
            Dict with dominance score and sub-scores, or None if insufficient data
        """
        try:
            # Extract required data
            symbol = truth_metrics.get('symbol')
            timeframe_name = truth_metrics.get('timeframe_name', 'UNKNOWN')  # TF_4H, TF_1D, etc.
            avg_adv = truth_metrics.get('avg_adv', 0)
            # Support both old (truth_volume_100) and new (truth_volume) field names
            truth_volume = truth_metrics.get('truth_volume', truth_metrics.get('truth_volume_100', 0))
            volav_timeline = truth_metrics.get('volav_timeline', [])
            volav1_start = truth_metrics.get('volav1_start')
            volav1_end = truth_metrics.get('volav1_end')
            volav1_displacement = truth_metrics.get('volav1_displacement')
            timeframe_seconds = truth_metrics.get('timeframe_seconds', truth_metrics.get('actual_timeframe_seconds', 0))
            volav_levels = truth_metrics.get('volav_levels', [])
            min_volav_gap_used = truth_metrics.get('min_volav_gap_used', 0.05)
            
            # Validate required data - symbol is critical
            if not symbol or (isinstance(symbol, str) and not symbol.strip()):
                # Try to extract symbol from truth_metrics keys or log detailed error
                logger.warning(f"No symbol in truth_metrics. Keys: {list(truth_metrics.keys())[:10] if isinstance(truth_metrics, dict) else 'not a dict'}")
                return None
                
            if avg_adv <= 0:
                logger.warning(f"No AVG_ADV for {symbol} (avg_adv={avg_adv})")
                return None
            
            # TIMEFRAME-FIRST: volav1_start and volav1_end are computed from first/last 20% of ticks
            # volav_timeline is optional (used for window consistency and recent bias, but not required)
            if volav1_start is None or volav1_end is None:
                logger.warning(f"Insufficient data for {symbol}: volav1_start={volav1_start}, volav1_end={volav1_end}")
                return None
            
            # volav_timeline is optional - if missing or too short, window consistency and recent bias will be 0
            # This is acceptable for illiquid preferred stocks with few ticks
            if not volav_timeline or len(volav_timeline) < 2:
                logger.debug(f"Limited timeline data for {symbol}: volav_timeline len={len(volav_timeline) if volav_timeline else 0} (will use volav1_start/end only)")
                # Continue anyway - volav1_start and volav1_end are sufficient for basic scoring
            
            # Calculate ADV fraction (RELATIVE volume pressure)
            adv_fraction = truth_volume / avg_adv if avg_adv > 0 else 0
            
            # Calculate normalized displacement (with NaN guard)
            if min_volav_gap_used > 0 and volav1_displacement is not None:
                normalized_displacement = volav1_displacement / min_volav_gap_used
                # Guard against NaN
                if not isinstance(normalized_displacement, (int, float)) or normalized_displacement != normalized_displacement:
                    normalized_displacement = 0.0
            else:
                normalized_displacement = 0.0
            
            # Guard against NaN in adv_fraction
            if not isinstance(adv_fraction, (int, float)) or adv_fraction != adv_fraction:
                adv_fraction = 0.0
            
            # Compute sub-scores (all AVG_ADV normalized) with NaN guards
            relative_volume_pressure = self._compute_relative_volume_pressure(adv_fraction)
            directional_displacement = self._compute_directional_displacement(
                normalized_displacement, adv_fraction
            )
            window_consistency = self._compute_window_consistency(
                volav_timeline, volav1_displacement, min_volav_gap_used
            )
            recent_bias = self._compute_recent_bias(
                volav_timeline, 
                min_volav_gap_used,
                avg_adv=avg_adv,
                timeframe_seconds=timeframe_seconds
            )
            
            # Guard against NaN in sub-scores
            if not isinstance(relative_volume_pressure, (int, float)) or relative_volume_pressure != relative_volume_pressure:
                relative_volume_pressure = 0.0
            if not isinstance(directional_displacement, (int, float)) or directional_displacement != directional_displacement:
                directional_displacement = 0.0
            if not isinstance(window_consistency, (int, float)) or window_consistency != window_consistency:
                window_consistency = 0.0
            if not isinstance(recent_bias, (int, float)) or recent_bias != recent_bias:
                recent_bias = 0.0
            
            # Check for ABSORPTION (pass normalized_displacement for strict rule)
            is_absorption = self._check_absorption(
                adv_fraction, volav1_displacement, min_volav_gap_used, volav_timeline, normalized_displacement
            )
            
            # Start from neutral baseline = 50
            raw_score = 50.0
            
            # Add buyer components or subtract seller components
            if directional_displacement > 0:
                # Buyer side
                raw_score += relative_volume_pressure * (directional_displacement / 30.0)
                raw_score += window_consistency
                raw_score += recent_bias
            elif directional_displacement < 0:
                # Seller side
                raw_score -= relative_volume_pressure * (abs(directional_displacement) / 30.0)
                raw_score -= window_consistency
                raw_score -= recent_bias
            else:
                # Flat - check for absorption
                if is_absorption:
                    raw_score += 10.0  # Slight positive for absorption (buyer accumulation)
                else:
                    raw_score += 0  # True neutral
            
            # Guard against NaN in raw_score
            if not isinstance(raw_score, (int, float)) or raw_score != raw_score:
                raw_score = 50.0  # Default to neutral
            
            # Clamp to 1-100
            buyer_seller_score = max(1, min(100, int(round(raw_score))))
            
            # Get label
            buyer_seller_label = self._get_label(buyer_seller_score, is_absorption)
            
            # Symbol return (with division-by-zero guard)
            if volav1_start and volav1_start > 0 and volav1_end:
                symbol_return = (volav1_end / volav1_start - 1)
                # Guard against NaN
                if not isinstance(symbol_return, (int, float)) or symbol_return != symbol_return:
                    symbol_return = 0.0
            else:
                symbol_return = 0.0
            
            # Compute confidence (with NaN guard)
            confidence = self._compute_confidence(adv_fraction, window_consistency, recent_bias)
            if not isinstance(confidence, (int, float)) or confidence != confidence:
                confidence = 0.0
            
            return {
                'symbol': symbol,
                'timeframe_name': timeframe_name,  # Always set to explicit timeframe (never UNKNOWN)
                'buyer_seller_score': buyer_seller_score,
                'buyer_seller_label': buyer_seller_label,
                'relative_volume_pressure': round(relative_volume_pressure, 2),
                'directional_displacement': round(directional_displacement, 2),
                'window_consistency': round(window_consistency, 2),
                'recent_bias': round(recent_bias, 2),
                'adv_fraction': round(adv_fraction, 4),
                'adv_percent': round(adv_fraction * 100, 2),  # For display
                'volav1_start': volav1_start,
                'volav1_end': volav1_end,
                'volav1_displacement': volav1_displacement,
                'normalized_displacement': round(normalized_displacement, 2),
                'timeframe_seconds': timeframe_seconds,
                'symbol_return': round(symbol_return * 100, 2),  # As percentage
                'pff_return': round(pff_return * 100, 2) if pff_return is not None else None,
                'is_absorption': is_absorption,
                'confidence': round(confidence, 3)
            }
            
        except Exception as e:
            logger.error(f"Error computing dominance score for {truth_metrics.get('symbol')}: {e}", exc_info=True)
            return None
    
    def _compute_relative_volume_pressure(self, adv_fraction: float) -> float:
        """
        Compute Relative Volume Pressure (0-30 pts).

        Measures how meaningful the volume is RELATIVE to AVG_ADV.
        Updated thresholds based on ChatGPT recommendations.

        Args:
            adv_fraction: truth_volume / avg_adv

        Returns:
            Score 0-30
        """
        if adv_fraction < 0.30:
            return 0.0  # Noise / meaningless
        elif adv_fraction < 0.70:
            return 10.0  # Weak
        elif adv_fraction < 1.20:
            return 20.0  # Meaningful
        else:
            return 30.0  # Aggressive
    
    def _compute_directional_displacement(
        self,
        normalized_displacement: float,
        adv_fraction: float
    ) -> float:
        """
        Compute Directional Displacement (0-30 pts).
        
        Positive = buyer, Negative = seller.
        Must be multiplied by adv_fraction to be meaningful.
        
        Args:
            normalized_displacement: (volav1_end - volav1_start) / min_volav_gap
            adv_fraction: truth_volume_100 / avg_adv
            
        Returns:
            Score -30 to +30
        """
        if adv_fraction < 0.10:
            # Volume too low, displacement meaningless
            return 0.0
        
        # Multiply displacement by volume pressure
        weighted_displacement = normalized_displacement * adv_fraction
        
        # Cap at ±30
        return max(-30.0, min(30.0, weighted_displacement))
    
    def _get_half_life_hours(self, avg_adv: float) -> float:
        """
        Get half-life in hours based on AVG_ADV for exponential decay.
        
        Args:
            avg_adv: Average Daily Volume
            
        Returns:
            Half-life in hours
        """
        if avg_adv > 50000:
            return self.HALF_LIFE_HOURS['high']
        elif avg_adv >= 10000:
            return self.HALF_LIFE_HOURS['medium']
        else:
            return self.HALF_LIFE_HOURS['low']
    
    def _compute_window_consistency(
        self,
        volav_timeline: List[Dict[str, Any]],
        volav1_displacement: Optional[float],
        min_volav_gap: float
    ) -> float:
        """
        Compute Window Consistency (0-20 pts).
        
        Measures how many windows agree on direction.
        Recent windows matter more.
        Includes NaN guards and division-by-zero checks.
        
        Args:
            volav_timeline: List of 5 windows
            volav1_displacement: Overall displacement
            min_volav_gap: Minimum gap for significance
            
        Returns:
            Score 0-20
        """
        if not volav_timeline or volav1_displacement is None:
            return 0.0
        
        # Guard against NaN
        if not isinstance(volav1_displacement, (int, float)) or volav1_displacement != volav1_displacement:
            return 0.0
        if not isinstance(min_volav_gap, (int, float)) or min_volav_gap <= 0:
            return 0.0
        
        # Determine overall direction
        overall_direction = 1 if volav1_displacement > min_volav_gap else (-1 if volav1_displacement < -min_volav_gap else 0)
        
        if overall_direction == 0:
            return 5.0  # Flat movement
        
        aligned_weight = 0.0
        total_weight = 0.0
        effective_windows = 0
        
        # Check each window pair for direction alignment
        for i in range(1, len(volav_timeline)):
            prev_volav1 = volav_timeline[i-1].get('volav1')
            curr_volav1 = volav_timeline[i].get('volav1')
            
            if prev_volav1 is None or curr_volav1 is None:
                continue
            
            # Guard against NaN
            if not isinstance(prev_volav1, (int, float)) or prev_volav1 != prev_volav1:
                continue
            if not isinstance(curr_volav1, (int, float)) or curr_volav1 != curr_volav1:
                continue
            
            window_delta = curr_volav1 - prev_volav1
            window_direction = 1 if window_delta > min_volav_gap * 0.5 else (-1 if window_delta < -min_volav_gap * 0.5 else 0)
            
            # Get time weight for current window
            weight = self.TIME_WEIGHTS.get(i, 0.5)
            total_weight += weight
            effective_windows += 1
            
            # Check if window direction aligns with overall direction
            if window_direction == overall_direction:
                aligned_weight += weight
        
        if total_weight == 0 or effective_windows == 0:
            return 0.0
        
        # Score based on alignment ratio (guard against division by zero)
        alignment_ratio = aligned_weight / total_weight if total_weight > 0 else 0.0
        
        # Guard against NaN
        if not isinstance(alignment_ratio, (int, float)) or alignment_ratio != alignment_ratio:
            return 0.0
        
        if alignment_ratio >= 0.8:
            return 20.0  # 4-5 aligned windows
        elif alignment_ratio >= 0.6:
            return 15.0  # 3 aligned windows
        elif alignment_ratio >= 0.4:
            return 10.0  # 2 aligned windows
        else:
            return 5.0  # <2 aligned windows
    
    def _compute_recent_bias(
        self,
        volav_timeline: List[Dict[str, Any]],
        min_volav_gap: float,
        avg_adv: float = 0.0,
        timeframe_seconds: float = 0.0
    ) -> float:
        """
        Compute Recent Bias (0-20 pts) using exponential decay.

        Most recent window direction dominates with exponential time decay.
        Uses half-life based on AVG_ADV for more sophisticated weighting.
        If recent window contradicts older ones, reduce confidence.
        Includes NaN guards.

        Args:
            volav_timeline: List of 5 windows
            min_volav_gap: Minimum gap for significance
            avg_adv: Average Daily Volume (for half-life calculation)
            timeframe_seconds: Total timeframe in seconds (for time decay)

        Returns:
            Score 0-20
        """
        if not volav_timeline or len(volav_timeline) < 2:
            return 0.0

        # Guard against invalid min_volav_gap
        if not isinstance(min_volav_gap, (int, float)) or min_volav_gap <= 0:
            return 0.0

        # Get half-life for exponential decay
        half_life_hours = self._get_half_life_hours(avg_adv) if avg_adv > 0 else 6.0
        half_life_seconds = half_life_hours * 3600
        
        # Calculate window duration (assume equal windows)
        window_duration = timeframe_seconds / len(volav_timeline) if timeframe_seconds > 0 and len(volav_timeline) > 0 else 0
        
        # Get most recent window direction
        last_window = volav_timeline[-1]
        second_last_window = volav_timeline[-2]

        last_volav1 = last_window.get('volav1')
        second_last_volav1 = second_last_window.get('volav1')
        
        if last_volav1 is None or second_last_volav1 is None:
            return 0.0
        
        # Guard against NaN
        if not isinstance(last_volav1, (int, float)) or last_volav1 != last_volav1:
            return 0.0
        if not isinstance(second_last_volav1, (int, float)) or second_last_volav1 != second_last_volav1:
            return 0.0
        
        recent_delta = last_volav1 - second_last_volav1
        recent_direction = 1 if recent_delta > min_volav_gap * 0.5 else (-1 if recent_delta < -min_volav_gap * 0.5 else 0)
        
        if recent_direction == 0:
            return 5.0  # Flat
        
        # Apply exponential decay weighting to windows
        import math
        weighted_score = 0.0
        total_weight = 0.0
        
        # Calculate exponential weights for each window (most recent = highest weight)
        for i, window in enumerate(volav_timeline):
            window_volav1 = window.get('volav1')
            if window_volav1 is None:
                continue
            
            # Guard against NaN
            if not isinstance(window_volav1, (int, float)) or window_volav1 != window_volav1:
                continue
            
            # Calculate time from window to now (assume windows are evenly spaced)
            # Window index: 0 = oldest, len-1 = newest
            window_age_seconds = (len(volav_timeline) - 1 - i) * window_duration if window_duration > 0 else 0
            
            # Exponential decay: weight = exp(-Δt / half_life)
            if half_life_seconds > 0:
                weight = math.exp(-window_age_seconds / half_life_seconds)
            else:
                weight = 1.0 if i == len(volav_timeline) - 1 else 0.0  # Fallback: only most recent
            
            total_weight += weight
            
            # Check window direction (compare with previous window)
            if i > 0:
                prev_window = volav_timeline[i - 1]
                prev_volav1 = prev_window.get('volav1')
                if prev_volav1 is not None and isinstance(prev_volav1, (int, float)) and prev_volav1 == prev_volav1:
                    window_delta = window_volav1 - prev_volav1
                    window_dir = 1 if window_delta > min_volav_gap * 0.5 else (-1 if window_delta < -min_volav_gap * 0.5 else 0)
                    
                    if window_dir == recent_direction:
                        weighted_score += weight * 1.0  # Aligned with recent
                    elif window_dir == 0:
                        weighted_score += weight * 0.5  # Flat
                    else:
                        weighted_score += weight * 0.0  # Contradicts recent
        
        # Normalize and scale to 0-20
        if total_weight > 0:
            alignment_ratio = weighted_score / total_weight
            # Scale to 0-20 range
            base_score = alignment_ratio * 20.0
            
            # Boost if recent direction confirms overall trend
            if len(volav_timeline) >= 3:
                first_volav1 = volav_timeline[0].get('volav1')
                if first_volav1 is not None and isinstance(first_volav1, (int, float)) and first_volav1 == first_volav1:
                    overall_delta = last_volav1 - first_volav1
                    overall_direction = 1 if overall_delta > min_volav_gap else (-1 if overall_delta < -min_volav_gap else 0)
                    
                    if recent_direction == overall_direction:
                        # Recent confirms overall trend - boost score
                        return min(20.0, base_score * 1.2)
                    else:
                        # Recent contradicts overall trend - reduce score
                        return max(0.0, base_score * 0.8)
            
            return min(20.0, max(0.0, base_score))
        
        # Fallback: simple recent direction check
        return 15.0 if recent_direction != 0 else 5.0
    
    def _check_absorption(
        self,
        adv_fraction: float,
        volav1_displacement: float,
        min_volav_gap: float,
        volav_timeline: List[Dict[str, Any]],
        normalized_displacement: float = None
    ) -> bool:
        """
        Check if pattern indicates ABSORPTION.
        
        STRICT RULE: Absorption = High volume, stable price, NO negative displacement.
        If normalized_displacement is negative and magnitude > threshold, it cannot be absorption.
        
        Args:
            adv_fraction: truth_volume / avg_adv
            volav1_displacement: Overall displacement
            min_volav_gap: Minimum gap for significance
            volav_timeline: List of windows
            normalized_displacement: (volav1_end - volav1_start) / min_volav_gap
            
        Returns:
            True if absorption pattern detected
        """
        # Constants for strict absorption rule
        ABSORB_ADV_TH = 0.60  # Minimum ADV fraction for absorption
        ABSORB_DISP_TH = 0.20  # Maximum normalized displacement for absorption
        
        # High volume required
        if adv_fraction < ABSORB_ADV_TH:
            return False
        
        # Compute normalized displacement if not provided
        if normalized_displacement is None:
            if min_volav_gap > 0:
                normalized_displacement = abs(volav1_displacement) / min_volav_gap
            else:
                normalized_displacement = abs(volav1_displacement) if volav1_displacement else 0
        
        # CRITICAL: If displacement is negative and significant, it's NOT absorption
        if volav1_displacement < 0 and abs(normalized_displacement) > ABSORB_DISP_TH:
            return False  # Negative displacement = seller pressure, not absorption
        
        # Price must be stable (normalized displacement <= threshold)
        if abs(normalized_displacement) > ABSORB_DISP_TH:
            return False
        
        # Check stability across windows
        if len(volav_timeline) < 3:
            return False
        
        first_volav1 = volav_timeline[0].get('volav1')
        last_volav1 = volav_timeline[-1].get('volav1')
        
        if first_volav1 is None or last_volav1 is None:
            return False
        
        # Price stable across timeline
        if abs(last_volav1 - first_volav1) < min_volav_gap:
            return True
        
        return False
    
    def _compute_confidence(
        self,
        adv_fraction: float,
        window_consistency: float,
        recent_bias: float
    ) -> float:
        """
        Compute confidence score (0-1).
        
        Higher confidence when:
        - High volume (adv_fraction)
        - Consistent windows
        - Strong recent bias
        
        Returns:
            Confidence 0.0-1.0
        """
        # Guard against NaN
        if not isinstance(adv_fraction, (int, float)) or adv_fraction != adv_fraction:
            adv_fraction = 0.0
        if not isinstance(window_consistency, (int, float)) or window_consistency != window_consistency:
            window_consistency = 0.0
        if not isinstance(recent_bias, (int, float)) or recent_bias != recent_bias:
            recent_bias = 0.0
        
        # Volume component (0-0.4)
        volume_conf = min(0.4, adv_fraction * 0.4) if adv_fraction > 0 else 0.0
        
        # Consistency component (0-0.3) - guard against division by zero
        consistency_conf = (window_consistency / 20.0) * 0.3 if window_consistency > 0 else 0.0
        
        # Recent bias component (0-0.3) - guard against division by zero
        recent_conf = (recent_bias / 20.0) * 0.3 if recent_bias > 0 else 0.0
        
        total_conf = volume_conf + consistency_conf + recent_conf
        # Guard against NaN
        if not isinstance(total_conf, (int, float)) or total_conf != total_conf:
            return 0.0
        
        return min(1.0, total_conf)
    
    def _get_label(self, score: int, is_absorption: bool) -> str:
        """
        Get human-readable label for score.
        Uses consistent underscored format to avoid UI displaying N/A.
        Updated thresholds based on ChatGPT recommendations.
        """
        if is_absorption:
            return "ABSORPTION"
        elif score >= 85:
            return "STRONG_BUYER"
        elif score >= 70:
            return "BUYER"
        elif score >= 55:
            return "ABSORPTION"  # ChatGPT: 55-69 = ABSORPTION
        elif score >= 40:
            return "SELLER"
        else:
            return "STRONG_SELLER"


# Singleton instance
_dominance_engine_instance: Optional[BuyerSellerDominanceEngine] = None


def get_buyer_seller_dominance_engine() -> BuyerSellerDominanceEngine:
    """Get singleton instance of BuyerSellerDominanceEngine"""
    global _dominance_engine_instance
    if _dominance_engine_instance is None:
        _dominance_engine_instance = BuyerSellerDominanceEngine()
    return _dominance_engine_instance



