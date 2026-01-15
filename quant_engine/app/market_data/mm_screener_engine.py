"""
Market Making Screener Engine

Professional micro-market-making (MM) screener and execution assistant
for illiquid and semi-liquid preferred stocks.

Two modes:
1. MODE 1 - MARKET CLOSED (PREPARATION MODE): Screener only, no bid/ask
2. MODE 2 - MARKET LIVE (EXECUTION MODE): Real MM suggestions with orders
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import time
import math

from app.core.logger import logger
from app.market_data.trading_calendar import get_trading_calendar


class MMScreenerEngine:
    """
    Market Making Screener Engine for preferred stocks.
    
    MODE 1: Market Closed - Preparation/Screening mode
    MODE 2: Market Live - Execution mode with order suggestions
    """
    
    # Timeframe weights (recent timeframes dominate)
    TIMEFRAME_WEIGHTS = {
        'TF_4H': 0.40,  # Most important - action potential
        'TF_1D': 0.30,  # Very important - action potential
        'TF_3D': 0.20,  # Context - behavior context
        'TF_5D': 0.10   # Context - behavior context
    }
    
    # Minimum viable spread for MM (commission-aware)
    MIN_VIABLE_SPREAD = 0.04  # $0.04 minimum to cover commissions
    
    # Liquidity fit thresholds (AVG_ADV based)
    TOO_ILLIQUID_THRESHOLD = 2000   # Below this: too illiquid, hard to exit
    TOO_LIQUID_THRESHOLD = 50000    # Above this: spread too tight
    SWEET_SPOT_MIN = 5000           # Sweet spot range
    SWEET_SPOT_MAX = 30000
    
    # Tick freshness thresholds (seconds)
    STALE_THRESHOLD = 24 * 60 * 60      # 24 hours = stale
    VERY_STALE_THRESHOLD = 3 * 24 * 60 * 60  # 3 days = very stale
    DEAD_THRESHOLD = 7 * 24 * 60 * 60   # 7 days = dead
    
    # Volav stability thresholds
    STABLE_DISPLACEMENT_THRESHOLD = 0.3  # normalized_displacement < 0.3 = stable
    UNSTABLE_DISPLACEMENT_THRESHOLD = 1.0  # normalized_displacement > 1.0 = unstable
    
    # Two-sided flow threshold
    TWO_SIDED_RATIO_THRESHOLD = 0.3  # At least 30% of ticks in opposite direction
    
    def __init__(self):
        """Initialize MM Screener Engine"""
        self.trading_calendar = get_trading_calendar()
        logger.info("MMScreenerEngine initialized")
    
    def compute_mm_prep_score(
        self,
        symbol: str,
        timeframe_metrics: Dict[str, Dict[str, Any]],
        avg_adv: float,
        final_bb: Optional[float] = None,
        final_sas: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Compute MM_PREP_SCORE (0-100) for a symbol in MARKET CLOSED mode.
        
        Args:
            symbol: Symbol name
            timeframe_metrics: Dict of {timeframe_name: metrics_dict}
                - Must contain TF_4H, TF_1D, TF_3D, TF_5D
            avg_adv: Average Daily Volume
            final_bb: Final BB (Fbtot) - optional
            final_sas: Final SAS (SFStot) - optional
            
        Returns:
            Dict with MM_PREP_SCORE and all component scores
        """
        try:
            # Get current time and last truth tick time
            current_time = time.time()
            last_tick_time = self._get_last_tick_time(timeframe_metrics)
            
            # 1) Tick Freshness (0-15 points)
            freshness_score, freshness_details = self._compute_tick_freshness(
                last_tick_time, current_time
            )
            
            # 2) Tick Density (0-20 points)
            density_score, density_details = self._compute_tick_density(
                timeframe_metrics
            )
            
            # 3) Volav Centrality (0-15 points)
            centrality_score, centrality_details = self._compute_volav_centrality(
                timeframe_metrics
            )
            
            # 4) Volav Stability (0-15 points)
            stability_score, stability_details = self._compute_volav_stability(
                timeframe_metrics
            )
            
            # 5) Two-Sided Flow (0-15 points)
            two_sided_score, two_sided_details = self._compute_two_sided_flow(
                timeframe_metrics
            )
            
            # 6) Liquidity Fit (0-10 points)
            liquidity_score, liquidity_details = self._compute_liquidity_fit(avg_adv)
            
            # 7) Extremes Filter (0-10 points penalty)
            extremes_penalty, extremes_details = self._compute_extremes_filter(
                final_bb, final_sas
            )
            
            # Total score (0-100)
            mm_prep_score = (
                freshness_score +
                density_score +
                centrality_score +
                stability_score +
                two_sided_score +
                liquidity_score -
                extremes_penalty
            )
            
            # Clamp to 0-100
            mm_prep_score = max(0, min(100, mm_prep_score))
            
            # Determine flags
            flags = self._determine_flags(
                freshness_details,
                two_sided_details,
                extremes_details,
                last_tick_time,
                current_time,
                mm_prep_score
            )
            
            return {
                'symbol': symbol,
                'mm_prep_score': round(mm_prep_score, 2),
                'component_scores': {
                    'tick_freshness': round(freshness_score, 2),
                    'tick_density': round(density_score, 2),
                    'volav_centrality': round(centrality_score, 2),
                    'volav_stability': round(stability_score, 2),
                    'two_sided_flow': round(two_sided_score, 2),
                    'liquidity_fit': round(liquidity_score, 2),
                    'extremes_penalty': round(extremes_penalty, 2)
                },
                'details': {
                    'freshness': freshness_details,
                    'density': density_details,
                    'centrality': centrality_details,
                    'stability': stability_details,
                    'two_sided': two_sided_details,
                    'liquidity': liquidity_details,
                    'extremes': extremes_details
                },
                'flags': flags,
                'last_tick_time': last_tick_time,
                'last_tick_age_seconds': current_time - last_tick_time if last_tick_time else None,
                'avg_adv': avg_adv
            }
            
        except Exception as e:
            logger.error(f"Error computing MM_PREP_SCORE for {symbol}: {e}", exc_info=True)
            return {
                'symbol': symbol,
                'mm_prep_score': 0.0,
                'error': str(e)
            }
    
    def _get_last_tick_time(self, timeframe_metrics: Dict[str, Dict[str, Any]]) -> Optional[float]:
        """Get the most recent truth tick timestamp across all timeframes"""
        last_time = None
        
        # Check each timeframe for the most recent tick
        for timeframe_name in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']:
            if timeframe_name in timeframe_metrics:
                metrics = timeframe_metrics[timeframe_name]
                tick_count = metrics.get('truth_tick_count', 0)
                
                if tick_count > 0:
                    # Try to get last tick timestamp from volav_timeline
                    volav_timeline = metrics.get('volav_timeline', [])
                    if volav_timeline:
                        # Get last window's end timestamp
                        last_window = volav_timeline[-1]
                        end_timestamp = last_window.get('end_timestamp')
                        if end_timestamp:
                            if last_time is None or end_timestamp > last_time:
                                last_time = end_timestamp
        
        return last_time
    
    def _compute_tick_freshness(
        self,
        last_tick_time: Optional[float],
        current_time: float
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute tick freshness score (0-15 points).
        
        Penalize stale symbols heavily.
        """
        if last_tick_time is None:
            return 0.0, {'status': 'NO_TICKS', 'age_seconds': None}
        
        age_seconds = current_time - last_tick_time
        age_hours = age_seconds / 3600
        
        if age_seconds >= self.DEAD_THRESHOLD:
            score = 0.0
            status = 'DEAD'
        elif age_seconds >= self.VERY_STALE_THRESHOLD:
            score = 2.0
            status = 'VERY_STALE'
        elif age_seconds >= self.STALE_THRESHOLD:
            score = 5.0
            status = 'STALE'
        elif age_seconds >= 12 * 3600:  # 12 hours
            score = 10.0
            status = 'AGING'
        elif age_seconds >= 6 * 3600:  # 6 hours
            score = 12.0
            status = 'RECENT'
        else:
            score = 15.0
            status = 'FRESH'
        
        return score, {
            'status': status,
            'age_seconds': age_seconds,
            'age_hours': round(age_hours, 2)
        }
    
    def _compute_tick_density(
        self,
        timeframe_metrics: Dict[str, Dict[str, Any]]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute tick density score (0-20 points).
        
        Reward symbols with consistent activity in TF_4H and TF_1D.
        """
        # Weighted tick count (TF_4H and TF_1D dominate)
        weighted_count = 0.0
        
        tick_counts = {}
        for timeframe_name in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']:
            if timeframe_name in timeframe_metrics:
                metrics = timeframe_metrics[timeframe_name]
                tick_count = metrics.get('truth_tick_count', 0)
                tick_counts[timeframe_name] = tick_count
                weight = self.TIMEFRAME_WEIGHTS.get(timeframe_name, 0.0)
                weighted_count += tick_count * weight
        
        # Score based on weighted count
        # Target: 20+ ticks in TF_4H+TF_1D for full score
        if weighted_count >= 30:
            score = 20.0
        elif weighted_count >= 20:
            score = 15.0
        elif weighted_count >= 10:
            score = 10.0
        elif weighted_count >= 5:
            score = 5.0
        else:
            score = 0.0
        
        return score, {
            'weighted_tick_count': round(weighted_count, 2),
            'tick_counts': tick_counts
        }
    
    def _compute_volav_centrality(
        self,
        timeframe_metrics: Dict[str, Dict[str, Any]]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute Volav centrality score (0-15 points).
        
        Are recent ticks clustering around Volav1/Volav2?
        MM requires mean-reverting behavior.
        """
        # Check TF_4H and TF_1D for Volav centrality
        centrality_scores = []
        
        for timeframe_name in ['TF_4H', 'TF_1D']:
            if timeframe_name not in timeframe_metrics:
                continue
            
            metrics = timeframe_metrics[timeframe_name]
            volav_levels = metrics.get('volav_levels', [])
            
            if not volav_levels:
                continue
            
            volav1 = volav_levels[0].get('price') if volav_levels else None
            volav2 = volav_levels[1].get('price') if len(volav_levels) > 1 else None
            
            if volav1 is None:
                continue
            
            # Get truth VWAP to see if ticks cluster around Volav
            truth_vwap = metrics.get('truth_vwap')
            
            if truth_vwap is None:
                continue
            
            # Check proximity to Volav1
            volav1_distance = abs(truth_vwap - volav1) if volav1 else float('inf')
            
            # Check proximity to Volav2 if available
            volav2_distance = abs(truth_vwap - volav2) if volav2 else float('inf')
            
            # Use min distance
            min_distance = min(volav1_distance, volav2_distance)
            
            # Get min_volav_gap for normalization
            min_volav_gap = metrics.get('min_volav_gap_used', 0.05)
            
            if min_volav_gap > 0:
                normalized_distance = min_distance / min_volav_gap
                
                # Score: closer to Volav = higher score
                if normalized_distance < 0.2:
                    score = 15.0
                elif normalized_distance < 0.5:
                    score = 12.0
                elif normalized_distance < 1.0:
                    score = 8.0
                else:
                    score = 4.0
            else:
                score = 0.0
            
            centrality_scores.append(score)
        
        # Average score across TF_4H and TF_1D
        if centrality_scores:
            avg_score = sum(centrality_scores) / len(centrality_scores)
        else:
            avg_score = 0.0
        
        return avg_score, {
            'centrality_scores': centrality_scores,
            'timeframes_checked': ['TF_4H', 'TF_1D']
        }
    
    def _compute_volav_stability(
        self,
        timeframe_metrics: Dict[str, Dict[str, Any]]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute Volav stability score (0-15 points).
        
        Penalize strong one-directional Volav migration.
        Reward sideways / oscillating Volav.
        """
        stability_scores = []
        
        for timeframe_name in ['TF_4H', 'TF_1D']:
            if timeframe_name not in timeframe_metrics:
                continue
            
            metrics = timeframe_metrics[timeframe_name]
            normalized_displacement = metrics.get('normalized_displacement', 0.0)
            
            if normalized_displacement is None:
                continue
            
            abs_displacement = abs(normalized_displacement)
            
            # Score: stable (low displacement) = higher score
            if abs_displacement < self.STABLE_DISPLACEMENT_THRESHOLD:
                score = 15.0
            elif abs_displacement < 0.5:
                score = 12.0
            elif abs_displacement < 1.0:
                score = 8.0
            elif abs_displacement < self.UNSTABLE_DISPLACEMENT_THRESHOLD:
                score = 4.0
            else:
                score = 0.0  # Strong trend = not good for MM
            
            stability_scores.append(score)
        
        # Average score
        if stability_scores:
            avg_score = sum(stability_scores) / len(stability_scores)
        else:
            avg_score = 0.0
        
        return avg_score, {
            'stability_scores': stability_scores,
            'timeframes_checked': ['TF_4H', 'TF_1D']
        }
    
    def _compute_two_sided_flow(
        self,
        timeframe_metrics: Dict[str, Dict[str, Any]]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute two-sided flow score (0-15 points).
        
        Presence of both up-ticks and down-ticks.
        Penalize one-way tape.
        """
        # This requires access to individual tick directions
        # For now, we'll use a simplified approach based on Volav displacement
        # If displacement is small, assume two-sided flow
        
        two_sided_ratios = []
        
        for timeframe_name in ['TF_4H', 'TF_1D']:
            if timeframe_name not in timeframe_metrics:
                continue
            
            metrics = timeframe_metrics[timeframe_name]
            normalized_displacement = abs(metrics.get('normalized_displacement', 0.0) or 0.0)
            
            # Small displacement suggests two-sided flow
            # Large displacement suggests one-way flow
            if normalized_displacement < 0.3:
                ratio = 1.0  # Fully two-sided
            elif normalized_displacement < 0.6:
                ratio = 0.7  # Mostly two-sided
            elif normalized_displacement < 1.0:
                ratio = 0.4  # Somewhat one-way
            else:
                ratio = 0.1  # Strongly one-way
            
            two_sided_ratios.append(ratio)
        
        # Average ratio
        if two_sided_ratios:
            avg_ratio = sum(two_sided_ratios) / len(two_sided_ratios)
            score = avg_ratio * 15.0  # Scale to 0-15
        else:
            score = 0.0
            avg_ratio = 0.0
        
        return score, {
            'two_sided_ratio': round(avg_ratio, 2),
            'ratios': two_sided_ratios
        }
    
    def _compute_liquidity_fit(self, avg_adv: float) -> tuple[float, Dict[str, Any]]:
        """
        Compute liquidity fit score (0-10 points).
        
        Too illiquid → hard to exit
        Too liquid → spread too tight
        Sweet spot favored.
        """
        if avg_adv <= 0:
            return 0.0, {'status': 'UNKNOWN', 'avg_adv': avg_adv}
        
        if avg_adv < self.TOO_ILLIQUID_THRESHOLD:
            score = 2.0
            status = 'TOO_ILLIQUID'
        elif avg_adv < self.SWEET_SPOT_MIN:
            score = 5.0
            status = 'LOW_LIQUIDITY'
        elif self.SWEET_SPOT_MIN <= avg_adv <= self.SWEET_SPOT_MAX:
            score = 10.0
            status = 'SWEET_SPOT'
        elif avg_adv <= self.TOO_LIQUID_THRESHOLD:
            score = 7.0
            status = 'HIGH_LIQUIDITY'
        else:
            score = 3.0
            status = 'TOO_LIQUID'
        
        return score, {
            'status': status,
            'avg_adv': avg_adv
        }
    
    def _compute_extremes_filter(
        self,
        final_bb: Optional[float],
        final_sas: Optional[float]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute extremes filter penalty (0-10 points penalty).
        
        Penalize symbols with extremely high or extremely low
        Final BB or Final SAS (trend bets are NOT MM).
        """
        penalty = 0.0
        reasons = []
        
        # Define extreme thresholds (these may need adjustment based on your data)
        EXTREME_HIGH = 0.8  # 80%+
        EXTREME_LOW = 0.2   # 20%-
        
        if final_bb is not None:
            if final_bb >= EXTREME_HIGH:
                penalty += 5.0
                reasons.append(f'EXTREME_HIGH_BB({final_bb:.2f})')
            elif final_bb <= EXTREME_LOW:
                penalty += 3.0
                reasons.append(f'EXTREME_LOW_BB({final_bb:.2f})')
        
        if final_sas is not None:
            if final_sas >= EXTREME_HIGH:
                penalty += 5.0
                reasons.append(f'EXTREME_HIGH_SAS({final_sas:.2f})')
            elif final_sas <= EXTREME_LOW:
                penalty += 3.0
                reasons.append(f'EXTREME_LOW_SAS({final_sas:.2f})')
        
        # Cap penalty at 10
        penalty = min(10.0, penalty)
        
        return penalty, {
            'penalty': penalty,
            'reasons': reasons,
            'final_bb': final_bb,
            'final_sas': final_sas
        }
    
    def _determine_flags(
        self,
        freshness_details: Dict[str, Any],
        two_sided_details: Dict[str, Any],
        extremes_details: Dict[str, Any],
        last_tick_time: Optional[float],
        current_time: float,
        mm_prep_score: Optional[float] = None
    ) -> List[str]:
        """Determine flags for the symbol"""
        flags = []
        
        # READY_FOR_MM (if score >= 60)
        if mm_prep_score is not None and mm_prep_score >= 60:
            flags.append('READY_FOR_MM')
        
        # STALE
        if freshness_details.get('status') in ['STALE', 'VERY_STALE', 'DEAD']:
            flags.append('STALE')
        
        # ONE_WAY
        two_sided_ratio = two_sided_details.get('two_sided_ratio', 0.0)
        if two_sided_ratio < self.TWO_SIDED_RATIO_THRESHOLD:
            flags.append('ONE_WAY')
        
        # TREND_RISK
        if extremes_details.get('penalty', 0) > 5.0:
            flags.append('TREND_RISK')
        
        # DEAD
        if freshness_details.get('status') == 'DEAD':
            flags.append('DEAD')
        
        return flags
    
    def compute_mm_live_score(
        self,
        symbol: str,
        bid: Optional[float],
        ask: Optional[float],
        spread: Optional[float],
        timeframe_metrics: Dict[str, Dict[str, Any]],
        avg_adv: float,
        final_bb: Optional[float] = None,
        final_sas: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Compute MM_LIVE_SCORE (0-100) for a symbol in MARKET LIVE mode.
        
        Args:
            symbol: Symbol name
            bid: Current bid price
            ask: Current ask price
            spread: Current spread (ask - bid)
            timeframe_metrics: Dict of {timeframe_name: metrics_dict}
            avg_adv: Average Daily Volume
            final_bb: Final BB (Fbtot) - optional
            final_sas: Final SAS (SFStot) - optional
            
        Returns:
            Dict with MM_LIVE_SCORE, order recommendations, and profit estimates
        """
        try:
            # Validate bid/ask/spread
            if bid is None or ask is None or spread is None:
                return {
                    'symbol': symbol,
                    'mm_live_score': 0.0,
                    'error': 'Missing bid/ask/spread data'
                }
            
            if spread <= 0:
                return {
                    'symbol': symbol,
                    'mm_live_score': 0.0,
                    'error': 'Invalid spread (spread <= 0)'
                }
            
            # 1) Spread Quality (0-25 points)
            spread_score, spread_details = self._compute_spread_quality(spread)
            
            # 2) Exit Probability (0-25 points)
            exit_score, exit_details = self._compute_exit_probability(
                bid, ask, timeframe_metrics, avg_adv
            )
            
            # 3) Volav Anchoring (0-20 points)
            anchoring_score, anchoring_details = self._compute_volav_anchoring(
                bid, ask, timeframe_metrics
            )
            
            # 4) Tape Bias (0-15 points)
            tape_bias_score, tape_bias_details = self._compute_tape_bias(
                timeframe_metrics
            )
            
            # 5) Risk Penalties (0-15 points penalty)
            risk_penalty, risk_details = self._compute_risk_penalties(
                timeframe_metrics, final_bb, final_sas
            )
            
            # Total score (0-100)
            mm_live_score = (
                spread_score +
                exit_score +
                anchoring_score +
                tape_bias_score -
                risk_penalty
            )
            
            # Clamp to 0-100
            mm_live_score = max(0, min(100, mm_live_score))
            
            # Generate order recommendations
            order_recommendations = self._generate_order_recommendations(
                symbol,
                bid,
                ask,
                spread,
                timeframe_metrics,
                avg_adv,
                mm_live_score
            )
            
            # Determine trade style
            trade_style = self._determine_trade_style(order_recommendations)
            
            # Determine risk flags
            risk_flags = self._determine_risk_flags(risk_details, spread_details)
            
            return {
                'symbol': symbol,
                'mm_live_score': round(mm_live_score, 2),
                'component_scores': {
                    'spread_quality': round(spread_score, 2),
                    'exit_probability': round(exit_score, 2),
                    'volav_anchoring': round(anchoring_score, 2),
                    'tape_bias': round(tape_bias_score, 2),
                    'risk_penalty': round(risk_penalty, 2)
                },
                'details': {
                    'spread': spread_details,
                    'exit': exit_details,
                    'anchoring': anchoring_details,
                    'tape_bias': tape_bias_details,
                    'risk': risk_details
                },
                'order_recommendations': order_recommendations,
                'trade_style': trade_style,
                'risk_flags': risk_flags,
                'bid': bid,
                'ask': ask,
                'spread': spread,
                'avg_adv': avg_adv
            }
            
        except Exception as e:
            logger.error(f"Error computing MM_LIVE_SCORE for {symbol}: {e}", exc_info=True)
            return {
                'symbol': symbol,
                'mm_live_score': 0.0,
                'error': str(e)
            }
    
    def _compute_spread_quality(self, spread: float) -> tuple[float, Dict[str, Any]]:
        """
        Compute spread quality score (0-25 points).
        
        Spread must exceed minimum viable profit.
        Commission-aware (minimum ~0.04).
        """
        if spread < self.MIN_VIABLE_SPREAD:
            score = 0.0
            status = 'TOO_TIGHT'
        elif spread < 0.06:
            score = 10.0
            status = 'MINIMAL'
        elif spread < 0.10:
            score = 15.0
            status = 'ADEQUATE'
        elif spread < 0.20:
            score = 20.0
            status = 'GOOD'
        else:
            score = 25.0
            status = 'EXCELLENT'
        
        return score, {
            'status': status,
            'spread': spread,
            'min_viable': self.MIN_VIABLE_SPREAD
        }
    
    def _compute_exit_probability(
        self,
        bid: float,
        ask: float,
        timeframe_metrics: Dict[str, Dict[str, Any]],
        avg_adv: float
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute exit probability score (0-25 points).
        
        Based on tape behavior and Volav proximity.
        "If I get filled, can I exit?"
        """
        # Get TF_4H metrics for recent behavior
        tf_4h_metrics = timeframe_metrics.get('TF_4H', {})
        
        # Check tick density (more ticks = easier exit)
        tick_count = tf_4h_metrics.get('truth_tick_count', 0)
        
        # Check Volav proximity to current bid/ask
        volav_levels = tf_4h_metrics.get('volav_levels', [])
        mid_price = (bid + ask) / 2
        
        volav_proximity_score = 0.0
        if volav_levels:
            volav1 = volav_levels[0].get('price')
            if volav1:
                distance_to_volav1 = abs(mid_price - volav1)
                min_volav_gap = tf_4h_metrics.get('min_volav_gap_used', 0.05)
                
                if min_volav_gap > 0:
                    normalized_distance = distance_to_volav1 / min_volav_gap
                    
                    # Closer to Volav = easier exit
                    if normalized_distance < 0.3:
                        volav_proximity_score = 15.0
                    elif normalized_distance < 0.6:
                        volav_proximity_score = 10.0
                    elif normalized_distance < 1.0:
                        volav_proximity_score = 5.0
        
        # Tick density score
        if tick_count >= 20:
            density_score = 10.0
        elif tick_count >= 10:
            density_score = 7.0
        elif tick_count >= 5:
            density_score = 4.0
        else:
            density_score = 0.0
        
        total_score = volav_proximity_score + density_score
        
        return total_score, {
            'volav_proximity_score': round(volav_proximity_score, 2),
            'density_score': round(density_score, 2),
            'tick_count': tick_count,
            'mid_price': mid_price
        }
    
    def _compute_volav_anchoring(
        self,
        bid: float,
        ask: float,
        timeframe_metrics: Dict[str, Dict[str, Any]]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute Volav anchoring score (0-20 points).
        
        Orders placed relative to Volav zones.
        """
        # Get TF_4H and TF_1D Volav levels
        mid_price = (bid + ask) / 2
        anchoring_scores = []
        
        for timeframe_name in ['TF_4H', 'TF_1D']:
            if timeframe_name not in timeframe_metrics:
                continue
            
            metrics = timeframe_metrics[timeframe_name]
            volav_levels = metrics.get('volav_levels', [])
            
            if not volav_levels:
                continue
            
            volav1 = volav_levels[0].get('price')
            if volav1 is None:
                continue
            
            # Check if mid_price is near Volav1
            distance = abs(mid_price - volav1)
            min_volav_gap = metrics.get('min_volav_gap_used', 0.05)
            
            if min_volav_gap > 0:
                normalized_distance = distance / min_volav_gap
                
                if normalized_distance < 0.2:
                    score = 20.0
                elif normalized_distance < 0.5:
                    score = 15.0
                elif normalized_distance < 1.0:
                    score = 10.0
                else:
                    score = 5.0
                
                anchoring_scores.append(score)
        
        # Average score
        if anchoring_scores:
            avg_score = sum(anchoring_scores) / len(anchoring_scores)
        else:
            avg_score = 0.0
        
        return avg_score, {
            'anchoring_scores': anchoring_scores,
            'mid_price': mid_price
        }
    
    def _compute_tape_bias(
        self,
        timeframe_metrics: Dict[str, Dict[str, Any]]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute tape bias score (0-15 points).
        
        Recent print clustering.
        Buyer vs seller pressure is secondary, NOT dominant.
        """
        # Get TF_4H metrics
        tf_4h_metrics = timeframe_metrics.get('TF_4H', {})
        
        # Use normalized displacement as proxy for tape bias
        # Small displacement = balanced tape = good for MM
        normalized_displacement = abs(tf_4h_metrics.get('normalized_displacement', 0.0) or 0.0)
        
        if normalized_displacement < 0.3:
            score = 15.0
        elif normalized_displacement < 0.6:
            score = 12.0
        elif normalized_displacement < 1.0:
            score = 8.0
        else:
            score = 4.0
        
        return score, {
            'normalized_displacement': normalized_displacement,
            'score': score
        }
    
    def _compute_risk_penalties(
        self,
        timeframe_metrics: Dict[str, Dict[str, Any]],
        final_bb: Optional[float],
        final_sas: Optional[float]
    ) -> tuple[float, Dict[str, Any]]:
        """
        Compute risk penalties (0-15 points penalty).
        
        One-way acceleration
        Sudden liquidity vacuum
        Extreme Final SAS / BB conflicts
        """
        penalty = 0.0
        reasons = []
        
        # Check for one-way acceleration (strong displacement)
        tf_4h_metrics = timeframe_metrics.get('TF_4H', {})
        normalized_displacement = abs(tf_4h_metrics.get('normalized_displacement', 0.0) or 0.0)
        
        if normalized_displacement > 1.5:
            penalty += 5.0
            reasons.append('STRONG_TREND')
        
        # Check for liquidity vacuum (low tick count)
        tick_count = tf_4h_metrics.get('truth_tick_count', 0)
        if tick_count < 5:
            penalty += 3.0
            reasons.append('LOW_LIQUIDITY')
        
        # Check extremes (same as MODE 1)
        if final_bb is not None:
            if final_bb >= 0.8 or final_bb <= 0.2:
                penalty += 3.0
                reasons.append('EXTREME_BB')
        
        if final_sas is not None:
            if final_sas >= 0.8 or final_sas <= 0.2:
                penalty += 3.0
                reasons.append('EXTREME_SAS')
        
        # Cap penalty at 15
        penalty = min(15.0, penalty)
        
        return penalty, {
            'penalty': penalty,
            'reasons': reasons
        }
    
    def _generate_order_recommendations(
        self,
        symbol: str,
        bid: float,
        ask: float,
        spread: float,
        timeframe_metrics: Dict[str, Dict[str, Any]],
        avg_adv: float,
        mm_live_score: float
    ) -> Dict[str, Any]:
        """
        Generate order recommendations with sizing and profit estimates.
        """
        recommendations = {
            'buy_price': None,
            'sell_price': None,
            'size': None,
            'estimated_profit': None,
            'confidence': None
        }
        
        # Only generate recommendations if score is above threshold
        if mm_live_score < 50:
            return recommendations
        
        # Get Volav levels for anchoring
        tf_4h_metrics = timeframe_metrics.get('TF_4H', {})
        volav_levels = tf_4h_metrics.get('volav_levels', [])
        
        volav1 = volav_levels[0].get('price') if volav_levels else None
        
        # Determine sizing based on liquidity
        if avg_adv < 5000:
            size = 200  # Very illiquid
        elif avg_adv < 15000:
            size = 500  # Medium
        elif avg_adv < 30000:
            size = 1000  # More liquid
        else:
            size = 2000  # Liquid
        
        # Adjust size based on confidence (mm_live_score)
        confidence_multiplier = mm_live_score / 100.0
        size = int(size * confidence_multiplier)
        size = max(100, min(2000, size))  # Clamp between 100 and 2000
        
        # Calculate order prices
        # Hidden buy at bid + spread*0.15
        # Hidden sell at ask - spread*0.15
        buy_price = bid + spread * 0.15
        sell_price = ask - spread * 0.15
        
        # If Volav1 is available, adjust prices to be closer to Volav1
        if volav1:
            mid_price = (bid + ask) / 2
            if volav1 < mid_price:
                # Volav1 below mid - favor buy side
                buy_price = max(bid, volav1 + spread * 0.1)
                sell_price = ask - spread * 0.2
            else:
                # Volav1 above mid - favor sell side
                buy_price = bid + spread * 0.2
                sell_price = min(ask, volav1 - spread * 0.1)
        
        # Calculate estimated profit (gross, before commissions)
        # Assume we can exit at mid price
        mid_price = (bid + ask) / 2
        buy_profit = (mid_price - buy_price) * size if buy_price else 0
        sell_profit = (sell_price - mid_price) * size if sell_price else 0
        
        # Two-sided profit
        total_profit = buy_profit + sell_profit
        
        recommendations = {
            'buy_price': round(buy_price, 2) if buy_price else None,
            'sell_price': round(sell_price, 2) if sell_price else None,
            'size': size,
            'estimated_profit': round(total_profit, 2),
            'confidence': round(mm_live_score / 100.0, 2),
            'buy_profit': round(buy_profit, 2) if buy_price else None,
            'sell_profit': round(sell_profit, 2) if sell_price else None
        }
        
        return recommendations
    
    def _determine_trade_style(
        self,
        order_recommendations: Dict[str, Any]
    ) -> str:
        """Determine trade style based on recommendations"""
        buy_price = order_recommendations.get('buy_price')
        sell_price = order_recommendations.get('sell_price')
        
        if buy_price and sell_price:
            return 'TWO_SIDED'
        elif buy_price:
            return 'BID_ONLY'
        elif sell_price:
            return 'ASK_ONLY'
        else:
            return 'AVOID'
    
    def _determine_risk_flags(
        self,
        risk_details: Dict[str, Any],
        spread_details: Dict[str, Any]
    ) -> List[str]:
        """Determine risk flags"""
        flags = []
        
        risk_reasons = risk_details.get('reasons', [])
        if 'STRONG_TREND' in risk_reasons:
            flags.append('TREND_RISK')
        if 'LOW_LIQUIDITY' in risk_reasons:
            flags.append('LIQUIDITY_RISK')
        if 'EXTREME_BB' in risk_reasons or 'EXTREME_SAS' in risk_reasons:
            flags.append('EXTREME_RISK')
        
        spread_status = spread_details.get('status')
        if spread_status == 'TOO_TIGHT':
            flags.append('SPREAD_TOO_TIGHT')
        
        return flags

