"""
Aura MM Engine v4 - Ping-Pong Value-First Model

Market Making Screener & Scoring Engine for preferred stocks.
Rank symbols by TIME-ORDERED PING-PONG behavior and MM_VALUE (net_gap × cycles).

Core Philosophy:
- A symbol is MM-tradeable ONLY if it repeatedly alternates between two price anchors (A↔B↔A↔B)
- Volume in two zones alone is NOT sufficient
- Alternation frequency and cycle count dominate all other factors
- MM_VALUE = net_gap × expected_cycles (parasal edge expectation)
- Value-first scoring: 0.70*value_score + 0.15*balance + 0.10*recency + 0.05*liq_score
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import time
import math

from app.core.logger import logger
from app.market_data.trading_calendar import get_trading_calendar


class AuraMMEngine:
    """
    Aura MM Engine v4 - Ping-Pong Value-First Model.
    
    Goal: Rank symbols by time-ordered ping-pong behavior and MM_VALUE (net_gap × cycles).
    """
    
    # MM-Anchor minimum gap (critical for tradeability)
    MM_ANCHOR_MIN_GAP = 0.06  # $0.06 minimum gap between anchors
    
    # Net gap calculation (after commission + buffer)
    COMMISSION_BUFFER = 0.04  # $0.04 commission + buffer per round trip
    
    # Speed constraints for ping-pong cycles
    MAX_LEG_MINUTES = 30  # Maximum time for one leg (A→B or B→A) to count as "fast"
    MAX_CYCLE_MINUTES = 60  # Maximum time for full cycle (A→B→A or B→A→B)
    TARGET_CYCLES_4H = 3  # Target cycles for 4H timeframe
    TARGET_CYCLES_5D = 10  # Target cycles for 5D timeframe (per day: 2)
    
    # Value score normalization
    VALUE_SCORE_K = 0.20  # Normalization constant: value_score = 1 - exp(-mm_value / K)
    
    # Net edge minimum (after commission)
    MIN_NET_EDGE = 0.04  # $0.04 minimum net edge per share
    
    # Commission per share (round trip = 2x)
    # $0.04 per round trip for 100 shares = $0.0004 per share per round trip
    # But we calculate: commission = COMMISSION_PER_SHARE * size * 2 (buy + sell)
    COMMISSION_PER_SHARE = 0.0002  # $0.0002 per share (round trip: $0.04 for 100 shares, $0.08 for 200 shares)
    
    # Progressive benchmark-shock quoting model
    PFF_STEP = 0.04  # $0.04 per shock level
    BASE_QUOTE_FRAC = 0.15  # Base spread fraction
    MAX_QUOTE_FRAC = 0.30  # Maximum spread fraction
    SHOCK_FRAC_INCREMENT = 0.03  # Per shock level increment
    FRONT_RUN_BOOSTER = 0.02  # Per front-run step increment
    
    # Tradeable MM constraints
    MIN_MARKET_SPREAD = 0.06  # Minimum market spread required
    MIN_ORDER_GAP = 0.04  # Minimum gap between buy_quote and sell_quote
    
    # Timeframe weights for recency scoring
    TIMEFRAME_WEIGHTS = {
        'TF_4H': 0.45,
        'TF_1D': 0.30,
        'TF_3D': 0.15,
        'TF_5D': 0.10
    }
    
    def __init__(self):
        """Initialize Aura MM Engine v4"""
        self.trading_calendar = get_trading_calendar()
        logger.info("AuraMMEngine v4 (Ping-Pong Value-First) initialized")
    
    def compute_mm_score(
        self,
        symbol: str,
        timeframe_metrics: Dict[str, Dict[str, Any]],
        avg_adv: float,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        spread: Optional[float] = None,
        mode: str = 'MARKET_CLOSED',
        pff_change_now: Optional[float] = None,
        pff_delta_5m: Optional[float] = None,
        prev_close: Optional[float] = None,
        last_truth_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Compute MM_SCORE (0-100) for a symbol using MM-Anchor based model.
        
        Args:
            symbol: Symbol name
            timeframe_metrics: Dict of {timeframe_name: metrics_dict}
                - Each metrics_dict should have:
                  - volav_levels: List of Volav levels (already merged with 0.06$ spacing)
                  - truth_tick_count: Number of truth ticks
                  - truth_volume: Total truth volume
            avg_adv: Average Daily Volume
            bid: Current bid price (for MARKET_LIVE mode)
            ask: Current ask price (for MARKET_LIVE mode)
            spread: Current spread (for MARKET_LIVE mode)
            mode: 'MARKET_CLOSED' or 'MARKET_LIVE'
            
        Returns:
            Dict with MM_SCORE and all component scores
        """
        try:
            # Compute per-timeframe ping-pong analysis
            timeframe_pingpong = {}
            
            # Select primary timeframe based on mode
            if mode == 'MARKET_LIVE':
                primary_timeframes = ['TF_4H', 'TF_1D']  # Execution readiness
            else:
                primary_timeframes = ['TF_1D', 'TF_3D', 'TF_5D']  # Character/bias
            
            for timeframe_name in ['TF_4H', 'TF_1D', 'TF_3D', 'TF_5D']:
                if timeframe_name not in timeframe_metrics:
                    continue
                
                metrics = timeframe_metrics[timeframe_name]
                truth_ticks = metrics.get('truth_ticks', [])
                
                if not truth_ticks:
                    continue
                
                # Compute ping-pong analysis
                pingpong_result = self._compute_pingpong_analysis(
                    symbol,
                    timeframe_name,
                    metrics,
                    truth_ticks,
                    avg_adv
                )
                
                timeframe_pingpong[timeframe_name] = pingpong_result
            
            if not timeframe_pingpong:
                return {
                    'symbol': symbol,
                    'mm_score': 0.0,
                    'mode': mode,
                    'error': 'No timeframe metrics with truth ticks available'
                }
            
            # Select primary timeframe for final scoring
            primary_tf = None
            for tf in primary_timeframes:
                if tf in timeframe_pingpong:
                    primary_tf = tf
                    break
            
            if not primary_tf:
                primary_tf = list(timeframe_pingpong.keys())[0]
            
            primary_data = timeframe_pingpong[primary_tf]
            
            # Check tradeability gate: gap >= 0.06
            gap = primary_data.get('gap', 0.0)
            if gap < self.MM_ANCHOR_MIN_GAP:
                return {
                    'symbol': symbol,
                    'mm_score': 0.0,
                    'mode': mode,
                    'gap': round(gap, 3),
                    'error': f'Gap {gap:.3f} < {self.MM_ANCHOR_MIN_GAP} (not tradeable)',
                    'pingpong_data': primary_data
                }
            
            # Calculate net_gap (after commission buffer)
            net_gap = max(0.0, gap - self.COMMISSION_BUFFER)
            
            if net_gap <= 0:
                return {
                    'symbol': symbol,
                    'mm_score': 0.0,
                    'mode': mode,
                    'gap': round(gap, 3),
                    'net_gap': round(net_gap, 3),
                    'error': f'Net gap {net_gap:.3f} <= 0 (no edge after commissions)',
                    'pingpong_data': primary_data
                }
            
            # Calculate expected_cycles based on mode
            if mode == 'MARKET_LIVE':
                # Use TF_4H cycles directly
                expected_cycles = primary_data.get('fast_cycles', 0)
            else:
                # MARKET_CLOSED: Use TF_5D to project next session
                tf_5d_data = timeframe_pingpong.get('TF_5D', primary_data)
                fast_cycles_5d = tf_5d_data.get('fast_cycles', 0)
                # Project: avg cycles per day * 1 trading day
                expected_cycles = (fast_cycles_5d / 5.0) * 1.0
            
            # Calculate MM_VALUE (parasal edge expectation)
            mm_value = net_gap * expected_cycles
            
            # Value score (normalized)
            value_score = 1.0 - math.exp(-mm_value / self.VALUE_SCORE_K)
            value_score = max(0.0, min(1.0, value_score))
            
            # Supporting scores
            balance = primary_data.get('balance', 0.0)  # 1 - abs(vol_A - vol_B)/(vol_A + vol_B)
            
            # Recency: minutes since last fast alternation
            last_alt_time = primary_data.get('last_fast_alt_time', None)
            if last_alt_time:
                minutes_since = (time.time() - last_alt_time) / 60.0
                recency = math.exp(-minutes_since / 120.0)  # Half-life: 120 minutes
            else:
                recency = 0.0
            
            # Liquidity sanity (soft check, don't penalize illiquid ping-pong)
            if avg_adv > 0:
                total_volume = primary_data.get('vol_A', 0) + primary_data.get('vol_B', 0)
                volume_fraction = total_volume / avg_adv
                liq_score = min(1.0, volume_fraction / 0.20)  # Normalize to 0.20
            else:
                liq_score = 0.5  # Neutral if no AVG_ADV
            
            # Final MM_SCORE (value-first)
            mm_score = 100.0 * (
                0.70 * value_score +
                0.15 * balance +
                0.10 * recency +
                0.05 * liq_score
            )
            mm_score = max(0.0, min(100.0, mm_score))
            
            # Generate recommendations
            recommendations = self._generate_recommendations_v4(
                symbol,
                primary_data,
                avg_adv,
                bid,
                ask,
                spread,
                mode,
                pff_change_now,
                pff_delta_5m,
                prev_close,
                last_truth_price
            )
            
            # Evaluate MM reasoning
            mm_reasoning = self._evaluate_mm_reasoning_v4(
                symbol,
                mode,
                primary_data,
                timeframe_pingpong,
                gap,
                net_gap,
                mm_value,
                expected_cycles,
                recommendations,
                avg_adv
            )
            
            return {
                'symbol': symbol,
                'mm_score': round(mm_score, 2),
                'mode': mode,
                'gap': round(gap, 3),
                'net_gap': round(net_gap, 3),
                'expected_cycles': round(expected_cycles, 2),
                'mm_value': round(mm_value, 3),
                'value_score': round(value_score, 3),
                'balance': round(balance, 3),
                'recency': round(recency, 3),
                'liq_score': round(liq_score, 3),
                'fast_cycles': primary_data.get('fast_cycles', 0),
                'fast_alternations': primary_data.get('fast_alternations', 0),
                'avg_cycle_time': primary_data.get('avg_cycle_time', None),
                'last_fast_alt_time': last_alt_time,
                'a_low': primary_data.get('a_low'),
                'b_high': primary_data.get('b_high'),
                'vol_A': primary_data.get('vol_A', 0),
                'vol_B': primary_data.get('vol_B', 0),
                'vol_A_pct': primary_data.get('vol_A_pct', 0),
                'vol_B_pct': primary_data.get('vol_B_pct', 0),
                'timeframe_pingpong': {
                    tf: {
                        'fast_cycles': data.get('fast_cycles', 0),
                        'fast_alternations': data.get('fast_alternations', 0),
                        'gap': data.get('gap', 0.0),
                        'balance': data.get('balance', 0.0)
                    }
                    for tf, data in timeframe_pingpong.items()
                },
                'recommendations': recommendations,
                'mm_reasoning': mm_reasoning,
                'avg_adv': avg_adv
            }
            
        except Exception as e:
            logger.error(f"Error computing MM_SCORE for {symbol}: {e}", exc_info=True)
            return {
                'symbol': symbol,
                'mm_score': 0.0,
                'error': str(e)
            }
    
    def _compute_timeframe_anchors(
        self,
        symbol: str,
        timeframe_name: str,
        metrics: Dict[str, Any],
        avg_adv: float
    ) -> Dict[str, Any]:
        """
        Compute MM-Anchors from Volav levels for a single timeframe.
        
        Returns:
            Dict with a1, a2, anchor_gap, two_sided_score
        """
        volav_levels = metrics.get('volav_levels', [])
        
        if len(volav_levels) < 2:
            # Less than 2 anchors - single-sided, weak for MM
            return {
                'a1': None,
                'a2': None,
                'anchor_gap': 0.0,
                'two_sided_score': 0.0,
                'anchors': []
            }
        
        # Select top-2 anchors by volume
        # A1 = highest volume anchor
        # A2 = anchor furthest from A1 with meaningful volume
        
        sorted_volavs = sorted(volav_levels, key=lambda x: x.get('volume', 0), reverse=True)
        a1 = sorted_volavs[0]
        
        # Find A2: furthest from A1 with meaningful volume (at least 10% of total)
        total_volume = sum(v.get('volume', 0) for v in volav_levels)
        min_volume_threshold = total_volume * 0.10
        
        a2_candidates = [
            v for v in sorted_volavs[1:]
            if v.get('volume', 0) >= min_volume_threshold
        ]
        
        if not a2_candidates:
            # No meaningful A2 - single-sided
            return {
                'a1': a1,
                'a2': None,
                'anchor_gap': 0.0,
                'two_sided_score': 0.0,
                'anchors': [a1]
            }
        
        # Select A2 as the one furthest from A1
        a1_price = a1.get('price', 0)
        a2 = max(a2_candidates, key=lambda v: abs(v.get('price', 0) - a1_price))
        
        # Calculate anchor gap
        anchor_gap = abs(a2.get('price', 0) - a1_price)
        
        # Two-sided homogeneity scoring
        a1_volume = a1.get('volume', 0)
        a2_volume = a2.get('volume', 0)
        total_anchor_volume = a1_volume + a2_volume
        
        if total_anchor_volume == 0:
            two_sided_score = 0.0
        else:
            p1 = a1_volume / total_anchor_volume
            p2 = a2_volume / total_anchor_volume
            # two_sided_score = 1 - abs(p1 - p2)
            # 50/50 → 1.0, 80/20 → 0.6, 95/5 → 0.1
            two_sided_score = 1.0 - abs(p1 - p2)
            
            # Penalize extreme one-sidedness (share > 0.95)
            if max(p1, p2) > 0.95:
                two_sided_score *= 0.5  # Heavy penalty
        
        # Confidence as continuous function (not hard kill)
        truth_tick_count = metrics.get('truth_tick_count', 0)
        truth_volume = metrics.get('truth_volume', 0.0)
        confidence = self._compute_confidence(truth_tick_count, truth_volume, avg_adv)
        
        # Check if anchors are tradeable (gap >= 0.06)
        anchors_untradeable = anchor_gap < self.MM_ANCHOR_MIN_GAP
        
        return {
            'a1': a1,
            'a2': a2,
            'anchor_gap': anchor_gap,
            'two_sided_score': two_sided_score,
            'anchors': [a1, a2],
            'anchors_untradeable': anchors_untradeable,
            'confidence': confidence
        }
    
    def _aggregate_anchors(
        self,
        timeframe_anchors: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Aggregate anchors across timeframes (weighted by recency).
        """
        # Use TF_4H as primary (most recent)
        primary_tf = 'TF_4H'
        if primary_tf not in timeframe_anchors:
            # Fallback to TF_1D
            primary_tf = 'TF_1D'
            if primary_tf not in timeframe_anchors:
                # Fallback to first available
                primary_tf = list(timeframe_anchors.keys())[0] if timeframe_anchors else None
        
        if not primary_tf:
            return {
                'anchors': [],
                'anchor_gap': 0.0,
                'two_sided_score': 0.0
            }
        
        primary_anchors = timeframe_anchors[primary_tf]
        
        # Weighted average of two_sided_score across timeframes
        weighted_two_sided = 0.0
        total_weight = 0.0
        
        for tf, weight in self.TIMEFRAME_WEIGHTS.items():
            if tf in timeframe_anchors:
                tf_score = timeframe_anchors[tf].get('two_sided_score', 0.0)
                weighted_two_sided += tf_score * weight
                total_weight += weight
        
        avg_two_sided = weighted_two_sided / total_weight if total_weight > 0 else 0.0
        
        return {
            'anchors': primary_anchors.get('anchors', []),
            'anchor_gap': primary_anchors.get('anchor_gap', 0.0),
            'two_sided_score': avg_two_sided,
            'a1': primary_anchors.get('a1'),
            'a2': primary_anchors.get('a2')
        }
    
    def _compute_recency_score(
        self,
        timeframe_anchors: Dict[str, Dict[str, Any]]
    ) -> float:
        """
        Compute recency score based on timeframe weights.
        More recent timeframes (TF_4H, TF_1D) should have higher scores.
        """
        score = 0.0
        total_weight = 0.0
        
        for tf, weight in self.TIMEFRAME_WEIGHTS.items():
            if tf in timeframe_anchors:
                tf_data = timeframe_anchors[tf]
                # Score based on anchor_gap and two_sided_score
                gap_score = min(1.0, tf_data.get('anchor_gap', 0.0) / 0.15)  # Normalize to 0.15 max
                two_sided = tf_data.get('two_sided_score', 0.0)
                tf_score = (gap_score + two_sided) / 2.0
                
                score += tf_score * weight
                total_weight += weight
        
        return score / total_weight if total_weight > 0 else 0.0
    
    def _compute_volume_score(
        self,
        timeframe_anchors: Dict[str, Dict[str, Any]],
        avg_adv: float
    ) -> float:
        """
        Compute volume score (normalized by AVG_ADV).
        """
        # Use TF_4H volume as primary
        primary_tf = 'TF_4H'
        if primary_tf not in timeframe_anchors:
            primary_tf = 'TF_1D'
        
        if primary_tf not in timeframe_anchors:
            return 0.0
        
        # Get total volume from anchors
        anchors = timeframe_anchors[primary_tf].get('anchors', [])
        total_volume = sum(a.get('volume', 0) for a in anchors)
        
        if avg_adv <= 0:
            return 0.0
        
        # Normalize: volume / avg_adv
        volume_fraction = total_volume / avg_adv
        
        # Score: 1 - exp(-volume_fraction / 0.15)
        volume_score = 1.0 - math.exp(-volume_fraction / 0.15)
        
        return max(0.0, min(1.0, volume_score))
    
    def _generate_recommendations(
        self,
        symbol: str,
        final_anchors: Dict[str, Any],
        avg_adv: float,
        bid: Optional[float],
        ask: Optional[float],
        spread: Optional[float],
        mode: str,
        pff_change_now: Optional[float] = None,
        pff_delta_5m: Optional[float] = None,
        prev_close: Optional[float] = None,
        last_truth_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generate MM recommendations: buy/sell zones, sizes, profit estimates.
        """
        recommendations = {
            'suggested_size': None,
            'buy_zone': None,
            'sell_zone': None,
            'buy_price': None,
            'sell_price': None,
            'expected_profit': {},
            'confidence': 0.0,
            'anchor_details': {}
        }
        
        anchors = final_anchors.get('anchors', [])
        anchor_gap = final_anchors.get('anchor_gap', 0.0)
        two_sided_score = final_anchors.get('two_sided_score', 0.0)
        
        if len(anchors) < 2:
            return recommendations
        
        # Confidence = two_sided_score
        recommendations['confidence'] = round(two_sided_score, 3)
        
        # Get A1 and A2 (sorted by price: low = buy, high = sell)
        a1 = final_anchors.get('a1')
        a2 = final_anchors.get('a2')
        
        if not a1 or not a2:
            return recommendations
        
        # Ensure A_low < A_high
        if a1.get('price', 0) > a2.get('price', 0):
            a_low, a_high = a2, a1
        else:
            a_low, a_high = a1, a2
        
        # Anchor details for UI
        recommendations['anchor_details'] = {
            'buy_anchor': {
                'price': round(a_low.get('price', 0), 2),
                'volume': int(a_low.get('volume', 0)),
                'tick_count': a_low.get('tick_count', 0),
                'pct_share': round(a_low.get('pct_of_truth_volume', 0), 1)
            },
            'sell_anchor': {
                'price': round(a_high.get('price', 0), 2),
                'volume': int(a_high.get('volume', 0)),
                'tick_count': a_high.get('tick_count', 0),
                'pct_share': round(a_high.get('pct_of_truth_volume', 0), 1)
            }
        }
        
        # Size suggestion
        if avg_adv < 5000:
            base_size = 300
        elif avg_adv < 15000:
            base_size = 500
        elif avg_adv < 30000:
            base_size = 1000
        else:
            base_size = 2000
        
        size_mult = 0.6 + 0.8 * two_sided_score
        suggested_size = int(base_size * size_mult)
        suggested_size = round(suggested_size / 100) * 100
        suggested_size = max(100, min(2000, suggested_size))
        recommendations['suggested_size'] = suggested_size
        
        # Market Closed Mode: Proxy trade zones
        if mode == 'MARKET_CLOSED':
            buy_proxy = a_low.get('price', 0) + 0.01
            sell_proxy = a_high.get('price', 0) - 0.01
            
            recommendations['buy_zone'] = round(buy_proxy, 2)
            recommendations['sell_zone'] = round(sell_proxy, 2)
            
            proxy_edge = sell_proxy - buy_proxy
            
            if proxy_edge < self.MIN_NET_EDGE:
                # MM-Not-Tradeable
                recommendations['expected_profit'] = {'status': 'NOT_TRADEABLE', 'reason': f'Proxy edge {proxy_edge:.3f} < {self.MIN_NET_EDGE}'}
            else:
                # Estimate profit for different sizes
                for size in [300, 500, 1000, 2000]:
                    gross_profit = proxy_edge * size
                    net_profit = gross_profit - (self.COMMISSION_PER_SHARE * size * 2)
                    recommendations['expected_profit'][f'size_{size}'] = {
                        'gross': round(gross_profit, 2),
                        'net': round(net_profit, 2)
                    }
        
        # Market Live Mode: Progressive benchmark-shock quoting + adaptive aggressiveness
        elif mode == 'MARKET_LIVE':
            if bid is None or ask is None or spread is None:
                recommendations['expected_profit'] = {'status': 'NO_L1_DATA'}
                recommendations['tradeable_mm'] = False
                recommendations['tradeable_reason'] = 'No L1 market data'
                return recommendations
            
            # Hard constraint: minimum market spread
            if spread < self.MIN_MARKET_SPREAD:
                recommendations['buy_price'] = None
                recommendations['sell_price'] = None
                recommendations['expected_profit'] = {'status': 'SPREAD_TOO_TIGHT', 'reason': f'Spread {spread:.3f} < {self.MIN_MARKET_SPREAD}'}
                recommendations['tradeable_mm'] = False
                recommendations['tradeable_reason'] = f'Market spread {spread:.3f} < {self.MIN_MARKET_SPREAD}'
                return recommendations
            
            # Progressive benchmark-shock quoting model
            effective_frac = self._compute_effective_quote_fraction(
                pff_change_now,
                pff_delta_5m,
                front_run_steps=0  # TODO: Track front-run steps from order history
            )
            
            # Compute suggested MM quotes
            buy_quote = bid + spread * effective_frac
            sell_quote = ask - spread * effective_frac
            
            # Hard constraint: minimum order gap
            order_gap = sell_quote - buy_quote
            if order_gap < self.MIN_ORDER_GAP:
                recommendations['buy_price'] = None
                recommendations['sell_price'] = None
                recommendations['expected_profit'] = {'status': 'ORDER_GAP_TOO_SMALL', 'reason': f'Order gap {order_gap:.3f} < {self.MIN_ORDER_GAP}'}
                recommendations['tradeable_mm'] = False
                recommendations['tradeable_reason'] = f'Order gap {order_gap:.3f} < {self.MIN_ORDER_GAP}'
                return recommendations
            
            recommendations['buy_price'] = round(buy_quote, 2)
            recommendations['sell_price'] = round(sell_quote, 2)
            recommendations['tradeable_mm'] = True
            recommendations['tradeable_reason'] = 'OK'
            
            # Net edge
            net_edge = sell_quote - buy_quote
            
            if net_edge < self.MIN_NET_EDGE:
                recommendations['expected_profit'] = {'status': 'EDGE_TOO_SMALL', 'reason': f'Net edge {net_edge:.3f} < {self.MIN_NET_EDGE}'}
            else:
                # Estimate profit for different sizes
                for size in [300, 500, 1000, 2000]:
                    gross_profit = net_edge * size
                    net_profit = gross_profit - (self.COMMISSION_PER_SHARE * size * 2)
                    recommendations['expected_profit'][f'size_{size}'] = {
                        'gross': round(gross_profit, 2),
                        'net': round(net_profit, 2)
                    }
            
            # Relative value bias metrics
            if prev_close is not None and last_truth_price is not None and pff_change_now is not None:
                symbol_change = last_truth_price - prev_close
                bench_change = pff_change_now
                buy_cheap = bench_change - symbol_change
                sell_rich = symbol_change - bench_change
                
                recommendations['relative_value'] = {
                    'buy_cheap': round(buy_cheap, 3),
                    'sell_rich': round(sell_rich, 3),
                    'symbol_change': round(symbol_change, 3),
                    'bench_change': round(bench_change, 3)
                }
                
                # Skew sizing based on relative value
                if buy_cheap > 0.05:  # Symbol is cheap relative to benchmark
                    recommendations['buy_size_mult'] = 1.2  # Increase buy size
                if sell_rich > 0.05:  # Symbol is rich relative to benchmark
                    recommendations['sell_size_mult'] = 1.2  # Increase sell size
        
        return recommendations
    
    def _compute_pingpong_analysis(
        self,
        symbol: str,
        timeframe_name: str,
        metrics: Dict[str, Any],
        truth_ticks: List[Dict[str, Any]],
        avg_adv: float
    ) -> Dict[str, Any]:
        """
        Compute ping-pong analysis: time-ordered alternation between two anchor zones.
        
        Returns:
            Dict with ping-pong metrics
        """
        volav_levels = metrics.get('volav_levels', [])
        
        if len(volav_levels) < 2:
            return {
                'a_low': None, 'b_high': None, 'gap': 0.0,
                'vol_A': 0, 'vol_B': 0, 'vol_A_pct': 0.0, 'vol_B_pct': 0.0,
                'balance': 0.0, 'fast_cycles': 0, 'fast_alternations': 0,
                'avg_cycle_time': None, 'last_fast_alt_time': None
            }
        
        bucket_size = metrics.get('min_volav_gap_used', 0.05)
        band = max(bucket_size / 2.0, 0.01)
        
        sorted_volavs = sorted(volav_levels, key=lambda x: x.get('volume', 0), reverse=True)
        
        if len(sorted_volavs) >= 2:
            a1_price = sorted_volavs[0].get('price', 0)
            a2_price = sorted_volavs[1].get('price', 0)
            gap_raw = abs(a2_price - a1_price)
            
            if gap_raw < self.MM_ANCHOR_MIN_GAP:
                a1_vol = sorted_volavs[0].get('volume', 0)
                a2_vol = sorted_volavs[1].get('volume', 0)
                total_vol = a1_vol + a2_vol
                if total_vol > 0:
                    merged_price = (a1_price * a1_vol + a2_price * a2_vol) / total_vol
                    a_low = merged_price
                    b_high = merged_price
                    gap = 0.0
                else:
                    a_low = a1_price
                    b_high = a2_price
                    gap = gap_raw
            else:
                a_low = min(a1_price, a2_price)
                b_high = max(a1_price, a2_price)
                gap = abs(b_high - a_low)
        else:
            a_low = sorted_volavs[0].get('price', 0)
            b_high = a_low
            gap = 0.0
        
        zone_sequence = []
        vol_A = 0
        vol_B = 0
        
        sorted_ticks = sorted(truth_ticks, key=lambda t: t.get('ts', 0))
        
        for tick in sorted_ticks:
            price = tick.get('price', 0)
            size = tick.get('size', 0)
            ts = tick.get('ts', 0)
            
            dist_to_A = abs(price - a_low)
            dist_to_B = abs(price - b_high)
            
            if gap > 0 and dist_to_A <= band and dist_to_A < dist_to_B:
                vol_A += size
                zone_sequence.append((ts, 'A', tick))
            elif gap > 0 and dist_to_B <= band and dist_to_B < dist_to_A:
                vol_B += size
                zone_sequence.append((ts, 'B', tick))
        
        if len(zone_sequence) < 2:
            total_vol = vol_A + vol_B
            vol_A_pct = (vol_A / total_vol * 100) if total_vol > 0 else 0.0
            vol_B_pct = (vol_B / total_vol * 100) if total_vol > 0 else 0.0
            balance = 1.0 - abs(vol_A - vol_B) / total_vol if total_vol > 0 else 0.0
            return {
                'a_low': a_low, 'b_high': b_high, 'gap': gap,
                'vol_A': vol_A, 'vol_B': vol_B, 'vol_A_pct': vol_A_pct, 'vol_B_pct': vol_B_pct,
                'balance': balance, 'fast_cycles': 0, 'fast_alternations': 0,
                'avg_cycle_time': None, 'last_fast_alt_time': None
            }
        
        # Run-compress consecutive duplicates
        compressed = []
        prev_zone = None
        for ts, zone, tick in zone_sequence:
            if zone != prev_zone:
                compressed.append((ts, zone, tick))
                prev_zone = zone
        
        if len(compressed) < 2:
            total_vol = vol_A + vol_B
            vol_A_pct = (vol_A / total_vol * 100) if total_vol > 0 else 0.0
            vol_B_pct = (vol_B / total_vol * 100) if total_vol > 0 else 0.0
            balance = 1.0 - abs(vol_A - vol_B) / total_vol if total_vol > 0 else 0.0
            return {
                'a_low': a_low, 'b_high': b_high, 'gap': gap,
                'vol_A': vol_A, 'vol_B': vol_B, 'vol_A_pct': vol_A_pct, 'vol_B_pct': vol_B_pct,
                'balance': balance, 'fast_cycles': 0, 'fast_alternations': 0,
                'avg_cycle_time': None, 'last_fast_alt_time': None
            }
        
        # Count fast cycles and alternations
        fast_alternations = 0
        fast_cycles = 0
        cycle_times = []
        last_fast_alt_time = None
        
        for i in range(1, len(compressed)):
            prev_ts, prev_zone, _ = compressed[i-1]
            curr_ts, curr_zone, _ = compressed[i]
            
            if prev_zone != curr_zone:
                dt_minutes = (curr_ts - prev_ts) / 60.0
                
                if dt_minutes <= self.MAX_LEG_MINUTES:
                    fast_alternations += 1
                    last_fast_alt_time = curr_ts
                
                if i >= 2:
                    prev2_ts, prev2_zone, _ = compressed[i-2]
                    if prev2_zone == curr_zone and prev_zone != curr_zone:
                        leg1_time = (prev_ts - prev2_ts) / 60.0
                        leg2_time = (curr_ts - prev_ts) / 60.0
                        cycle_time = leg1_time + leg2_time
                        
                        if (leg1_time <= self.MAX_LEG_MINUTES and 
                            leg2_time <= self.MAX_LEG_MINUTES and 
                            cycle_time <= self.MAX_CYCLE_MINUTES):
                            fast_cycles += 1
                            cycle_times.append(cycle_time)
        
        total_vol = vol_A + vol_B
        vol_A_pct = (vol_A / total_vol * 100) if total_vol > 0 else 0.0
        vol_B_pct = (vol_B / total_vol * 100) if total_vol > 0 else 0.0
        balance = 1.0 - abs(vol_A - vol_B) / total_vol if total_vol > 0 else 0.0
        avg_cycle_time = sum(cycle_times) / len(cycle_times) if cycle_times else None
        
        return {
            'a_low': a_low, 'b_high': b_high, 'gap': gap,
            'vol_A': vol_A, 'vol_B': vol_B, 'vol_A_pct': vol_A_pct, 'vol_B_pct': vol_B_pct,
            'balance': balance, 'fast_cycles': fast_cycles, 'fast_alternations': fast_alternations,
            'avg_cycle_time': avg_cycle_time, 'last_fast_alt_time': last_fast_alt_time
        }
    
    def _generate_recommendations_v4(
        self,
        symbol: str,
        pingpong_data: Dict[str, Any],
        avg_adv: float,
        bid: Optional[float],
        ask: Optional[float],
        spread: Optional[float],
        mode: str,
        pff_change_now: Optional[float] = None,
        pff_delta_5m: Optional[float] = None,
        prev_close: Optional[float] = None,
        last_truth_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Generate MM recommendations using ping-pong data.
        """
        recommendations = {
            'suggested_size': None,
            'buy_zone': None,
            'sell_zone': None,
            'buy_price': None,
            'sell_price': None,
            'expected_profit': {},
            'confidence': 0.0,
            'tradeable_mm': False,
            'tradeable_reason': 'Not analyzed'
        }
        
        a_low = pingpong_data.get('a_low')
        b_high = pingpong_data.get('b_high')
        gap = pingpong_data.get('gap', 0.0)
        fast_cycles = pingpong_data.get('fast_cycles', 0)
        
        if a_low is None or b_high is None or gap < self.MM_ANCHOR_MIN_GAP:
            recommendations['tradeable_reason'] = f'Gap {gap:.3f} < {self.MM_ANCHOR_MIN_GAP} or missing anchors'
            return recommendations
        
        # Confidence based on fast cycles
        recommendations['confidence'] = min(1.0, fast_cycles / 3.0)
        
        # Size suggestion
        if avg_adv < 5000:
            base_size = 300
        elif avg_adv < 15000:
            base_size = 500
        elif avg_adv < 30000:
            base_size = 1000
        else:
            base_size = 2000
        
        size_mult = 0.6 + 0.4 * recommendations['confidence']
        suggested_size = int(base_size * size_mult)
        suggested_size = round(suggested_size / 100) * 100
        suggested_size = max(100, min(2000, suggested_size))
        recommendations['suggested_size'] = suggested_size
        
        if mode == 'MARKET_CLOSED':
            # Proxy zones
            buy_proxy = a_low + 0.01
            sell_proxy = b_high - 0.01
            recommendations['buy_zone'] = round(buy_proxy, 2)
            recommendations['sell_zone'] = round(sell_proxy, 2)
            recommendations['tradeable_mm'] = True
            recommendations['tradeable_reason'] = 'OK'
            
            proxy_edge = sell_proxy - buy_proxy
            net_edge = max(0.0, proxy_edge - self.COMMISSION_BUFFER)
            
            if net_edge > 0:
                for size in [300, 500, 1000, 2000]:
                    gross_profit = net_edge * size
                    net_profit = gross_profit - (self.COMMISSION_PER_SHARE * size * 2)
                    recommendations['expected_profit'][f'size_{size}'] = {
                        'gross': round(gross_profit, 2),
                        'net': round(net_profit, 2)
                    }
        
        elif mode == 'MARKET_LIVE':
            if bid is None or ask is None or spread is None:
                recommendations['tradeable_reason'] = 'No L1 market data'
                return recommendations
            
            if spread < self.MIN_MARKET_SPREAD:
                recommendations['tradeable_reason'] = f'Spread {spread:.3f} < {self.MIN_MARKET_SPREAD}'
                return recommendations
            
            # Progressive benchmark-shock quoting
            effective_frac = self._compute_effective_quote_fraction(
                pff_change_now,
                pff_delta_5m,
                front_run_steps=0
            )
            
            buy_quote = bid + spread * effective_frac
            sell_quote = ask - spread * effective_frac
            order_gap = sell_quote - buy_quote
            
            if order_gap < self.MIN_ORDER_GAP:
                recommendations['tradeable_reason'] = f'Order gap {order_gap:.3f} < {self.MIN_ORDER_GAP}'
                return recommendations
            
            recommendations['buy_price'] = round(buy_quote, 2)
            recommendations['sell_price'] = round(sell_quote, 2)
            recommendations['tradeable_mm'] = True
            recommendations['tradeable_reason'] = 'OK'
            
            net_edge = order_gap
            if net_edge > 0:
                for size in [300, 500, 1000, 2000]:
                    gross_profit = net_edge * size
                    net_profit = gross_profit - (self.COMMISSION_PER_SHARE * size * 2)
                    recommendations['expected_profit'][f'size_{size}'] = {
                        'gross': round(gross_profit, 2),
                        'net': round(net_profit, 2)
                    }
        
        return recommendations
    
    def _evaluate_mm_reasoning_v4(
        self,
        symbol: str,
        mode: str,
        primary_data: Dict[str, Any],
        timeframe_pingpong: Dict[str, Dict[str, Any]],
        gap: float,
        net_gap: float,
        mm_value: float,
        expected_cycles: float,
        recommendations: Dict[str, Any],
        avg_adv: float
    ) -> Dict[str, Any]:
        """
        Evaluate MM reasoning for v4 ping-pong model.
        """
        reasoning = {
            'included': False,
            'mode': 'TRADEABLE_MM' if mode in ['MARKET_CLOSED', 'MARKET_LIVE'] else 'BIAS_MM',
            'exclusion_reasons': [],
            'inclusion_reasons': [],
            'metrics_snapshot': {
                'gap': round(gap, 3),
                'net_gap': round(net_gap, 3),
                'mm_value': round(mm_value, 3),
                'expected_cycles': round(expected_cycles, 2),
                'fast_cycles': primary_data.get('fast_cycles', 0),
                'balance': round(primary_data.get('balance', 0.0), 3),
                'avg_adv': avg_adv
            }
        }
        
        is_tradeable_mode = mode in ['MARKET_CLOSED', 'MARKET_LIVE']
        is_bias_mode = mode == 'MARKET_CLOSED_BIAS'
        
        if is_tradeable_mode:
            reasoning['mode'] = 'TRADEABLE_MM'
            
            # Check 1: Gap >= 0.06
            if gap < self.MM_ANCHOR_MIN_GAP:
                reasoning['exclusion_reasons'].append('GAP_TOO_NARROW')
                return reasoning
            
            # Check 2: Net gap > 0
            if net_gap <= 0:
                reasoning['exclusion_reasons'].append('NO_NET_EDGE')
                return reasoning
            
            # Check 3: Fast cycles > 0
            fast_cycles = primary_data.get('fast_cycles', 0)
            if fast_cycles == 0:
                reasoning['exclusion_reasons'].append('NO_PINGPONG_CYCLES')
                return reasoning
            
            # Check 4: MM_VALUE > 0
            if mm_value <= 0:
                reasoning['exclusion_reasons'].append('NO_MM_VALUE')
                return reasoning
            
            # All checks passed
            reasoning['included'] = True
            reasoning['inclusion_reasons'].append('PINGPONG_CYCLES')
            if mm_value >= 0.20:
                reasoning['inclusion_reasons'].append('HIGH_MM_VALUE')
            if fast_cycles >= 3:
                reasoning['inclusion_reasons'].append('MULTIPLE_CYCLES')
        
        elif is_bias_mode:
            reasoning['mode'] = 'BIAS_MM'
            
            # Relaxed criteria for watchlist
            fast_cycles = primary_data.get('fast_cycles', 0)
            balance = primary_data.get('balance', 0.0)
            
            inclusion_criteria_met = False
            
            # Any fast cycles
            if fast_cycles > 0:
                reasoning['inclusion_reasons'].append('HAS_PINGPONG_CYCLES')
                inclusion_criteria_met = True
            
            # Good balance even without cycles
            if balance >= 0.50:
                reasoning['inclusion_reasons'].append('BALANCED_FLOW')
                inclusion_criteria_met = True
            
            # Large gap potential
            if gap >= 0.08:
                reasoning['inclusion_reasons'].append('LARGE_GAP')
                inclusion_criteria_met = True
            
            if inclusion_criteria_met:
                reasoning['included'] = True
            else:
                reasoning['exclusion_reasons'].append('NO_BIAS_CRITERIA_MET')
        
        return reasoning
    
    def _evaluate_mm_reasoning(
        self,
        symbol: str,
        mode: str,
        final_anchors: Dict[str, Any],
        timeframe_anchors: Dict[str, Dict[str, Any]],
        two_sided_score: float,
        anchor_gap: float,
        recommendations: Dict[str, Any],
        avg_adv: float
    ) -> Dict[str, Any]:
        """
        Evaluate MM reasoning for inclusion/exclusion in Tradeable MM or Bias MM modes.
        
        Returns:
            Dict with:
            - included: bool
            - mode: "TRADEABLE_MM" | "BIAS_MM"
            - exclusion_reasons: List[str]
            - inclusion_reasons: List[str]
            - metrics_snapshot: Dict
        """
        reasoning = {
            'included': False,
            'mode': 'TRADEABLE_MM' if mode in ['MARKET_CLOSED', 'MARKET_LIVE'] else 'BIAS_MM',
            'exclusion_reasons': [],
            'inclusion_reasons': [],
            'metrics_snapshot': {
                'anchor_gap': round(anchor_gap, 3),
                'two_sided_score': round(two_sided_score, 3),
                'volav_count': len(final_anchors.get('anchors', [])),
                'net_edge': 0.0,
                'avg_adv': avg_adv
            }
        }
        
        # Get net edge from recommendations
        if recommendations.get('expected_profit'):
            if isinstance(recommendations['expected_profit'], dict):
                if 'size_500' in recommendations['expected_profit']:
                    net_edge = recommendations['expected_profit']['size_500'].get('net', 0) / 500
                    reasoning['metrics_snapshot']['net_edge'] = round(net_edge, 3)
        
        # Determine evaluation mode
        is_tradeable_mode = mode in ['MARKET_CLOSED', 'MARKET_LIVE']
        is_bias_mode = mode == 'MARKET_CLOSED_BIAS'
        
        if is_tradeable_mode:
            # TRADEABLE MM: Strict filters
            reasoning['mode'] = 'TRADEABLE_MM'
            
            # Check 1: At least 2 anchors
            if len(final_anchors.get('anchors', [])) < 2:
                reasoning['exclusion_reasons'].append('NO_TRADEABLE_ANCHOR')
                return reasoning
            
            # Check 2: Anchor gap >= 0.06
            if anchor_gap < self.MM_ANCHOR_MIN_GAP:
                reasoning['exclusion_reasons'].append('GAP_TOO_NARROW')
                return reasoning
            
            # Check 3: Two-sided score >= 0.65
            if two_sided_score < 0.65:
                reasoning['exclusion_reasons'].append('ONE_SIDED_FLOW')
                return reasoning
            
            # Check 4: Net edge > 0 (after fees)
            net_edge = reasoning['metrics_snapshot']['net_edge']
            if net_edge <= 0:
                reasoning['exclusion_reasons'].append('INSUFFICIENT_EDGE')
                return reasoning
            
            # Check 5: Not stale (has recent data)
            has_recent_data = 'TF_4H' in timeframe_anchors or 'TF_1D' in timeframe_anchors
            if not has_recent_data:
                reasoning['exclusion_reasons'].append('STALE_PRINTS')
                return reasoning
            
            # All checks passed - included
            reasoning['included'] = True
            reasoning['inclusion_reasons'].append('TWO_SIDED_FLOW')
            if anchor_gap >= 0.10:
                reasoning['inclusion_reasons'].append('LARGE_ANCHOR_GAP')
            if net_edge >= self.MIN_NET_EDGE:
                reasoning['inclusion_reasons'].append('NET_EDGE_OK')
            
        elif is_bias_mode:
            # BIAS MM: Relaxed filters for watchlist
            reasoning['mode'] = 'BIAS_MM'
            
            # Check if we have ANY timeframe data
            if not timeframe_anchors:
                reasoning['exclusion_reasons'].append('NO_TIMEFRAME_DATA')
                return reasoning
            
            # Inclusion criteria (ANY of the following):
            inclusion_criteria_met = False
            
            # 1) anchor_gap >= 0.08 at least once
            max_gap = max([
                tf_data.get('anchor_gap', 0.0)
                for tf_data in timeframe_anchors.values()
            ], default=0.0)
            if max_gap >= 0.08:
                reasoning['inclusion_reasons'].append('LARGE_ANCHOR_GAP')
                inclusion_criteria_met = True
            
            # 2) two_sided_score >= 0.50
            if two_sided_score >= 0.50:
                reasoning['inclusion_reasons'].append('TWO_SIDED_FLOW')
                inclusion_criteria_met = True
            
            # 3) Clear two-sided truth ticks but gap < 0.06
            if two_sided_score >= 0.45 and anchor_gap < 0.06:
                reasoning['inclusion_reasons'].append('TWO_SIDED_BUT_NARROW_GAP')
                inclusion_criteria_met = True
            
            # 4) Illiquid but symmetric behavior
            if avg_adv < 30000 and two_sided_score >= 0.30:
                reasoning['inclusion_reasons'].append('ILLIQUID_BUT_SYMMETRIC')
                inclusion_criteria_met = True
            
            # 5) Historical MM-friendly pattern (check 3D/5D)
            for tf in ['TF_3D', 'TF_5D']:
                if tf in timeframe_anchors:
                    tf_data = timeframe_anchors[tf]
                    tf_gap = tf_data.get('anchor_gap', 0.0)
                    tf_two_sided = tf_data.get('two_sided_score', 0.0)
                    if tf_gap >= 0.06 and tf_two_sided >= 0.40:
                        reasoning['inclusion_reasons'].append('HISTORICAL_MM_PATTERN')
                        inclusion_criteria_met = True
                        break
            
            # 6) Any timeframe with at least 2 anchors
            has_two_anchors = any(
                len(tf_data.get('anchors', [])) >= 2
                for tf_data in timeframe_anchors.values()
            )
            if has_two_anchors and not inclusion_criteria_met:
                reasoning['inclusion_reasons'].append('HAS_TWO_ANCHORS')
                inclusion_criteria_met = True
            
            if inclusion_criteria_met:
                reasoning['included'] = True
            else:
                reasoning['exclusion_reasons'].append('NO_BIAS_CRITERIA_MET')
        
        return reasoning
    
    def _compute_confidence(
        self,
        truth_tick_count: int,
        truth_volume: float,
        avg_adv: float
    ) -> float:
        """
        Compute confidence as continuous function (not hard kill).
        
        Confidence depends on:
        - truth_tick_count (more ticks = higher confidence)
        - truth_volume / avg_adv (more volume = higher confidence)
        """
        # Tick count component (soft threshold, not hard kill)
        tick_score = 1.0 - math.exp(-truth_tick_count / 12.0)
        
        # Volume component
        if avg_adv > 0:
            volume_fraction = truth_volume / avg_adv
            volume_score = 1.0 - math.exp(-volume_fraction / 0.15)
        else:
            volume_score = 0.0
        
        # Combined confidence
        confidence = (tick_score + volume_score) / 2.0
        
        return max(0.0, min(1.0, confidence))
    
    def _compute_effective_quote_fraction(
        self,
        pff_change_now: Optional[float],
        pff_delta_5m: Optional[float],
        front_run_steps: int = 0
    ) -> float:
        """
        Compute effective quote fraction using progressive benchmark-shock model.
        
        Args:
            pff_change_now: Current PFF change from prev_close
            pff_delta_5m: PFF change over last 5 minutes
            front_run_steps: Number of front-run steps (decay over time)
            
        Returns:
            Effective quote fraction (0.15 to 0.30)
        """
        # Base fraction
        base_frac = self.BASE_QUOTE_FRAC
        
        # Progressive benchmark-shock levels
        shock_level = 0
        shock_impulse = 0
        
        if pff_change_now is not None:
            shock_level = int(abs(pff_change_now) / self.PFF_STEP)
        
        if pff_delta_5m is not None:
            shock_impulse = int(abs(pff_delta_5m) / self.PFF_STEP)
        
        effective_shock = max(shock_level, shock_impulse)
        
        # Shock-based fraction increment
        shock_frac = min(
            self.MAX_QUOTE_FRAC,
            base_frac + self.SHOCK_FRAC_INCREMENT * effective_shock
        )
        
        # Front-run booster
        effective_frac = min(
            self.MAX_QUOTE_FRAC,
            shock_frac + self.FRONT_RUN_BOOSTER * front_run_steps
        )
        
        return effective_frac
