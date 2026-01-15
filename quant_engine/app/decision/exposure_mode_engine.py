"""
Exposure Mode Engine
Computes exposure mode (DEFENSIVE / TRANSITION / OFFENSIVE) based on market conditions.

This engine provides exposure mode for monitoring and display purposes only.
It does NOT make trading decisions.
"""

from typing import Dict, Any, Optional
from app.core.logger import logger


class ExposureModeEngine:
    """
    Computes exposure mode for symbols.
    
    Outputs:
    - mode: DEFENSIVE | TRANSITION | OFFENSIVE
    - confidence: HIGH | MEDIUM | LOW
    - factors: Dict of contributing factors
    - explanation: Human-readable explanation
    """
    
    def __init__(self):
        # Default thresholds (can be made configurable)
        self.defensive_thresholds = {
            'spread_percent_max': 1.0,  # High spread = defensive
            'volatility_high': True,  # High volatility = defensive
            'signal_weak': True  # Weak signals = defensive
        }
        
        self.offensive_thresholds = {
            'spread_percent_max': 0.3,  # Low spread = offensive
            'signal_strong': True,  # Strong signals = offensive
            'grpan_high': True  # High GRPAN concentration = offensive
        }
    
    def compute_exposure_mode(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        static_data: Dict[str, Any],
        signal_data: Optional[Dict[str, Any]] = None,
        grpan_metrics: Optional[Dict[str, Any]] = None,
        position_analytics: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Compute exposure mode for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            market_data: Market data (spread_percent, etc.)
            static_data: Static data (FINAL_THG, etc.)
            signal_data: Signal data (for signal strength)
            grpan_metrics: GRPAN metrics (for concentration)
            position_analytics: Position analytics (for position status)
            
        Returns:
            Exposure mode dict:
            {
                'mode': 'DEFENSIVE' | 'TRANSITION' | 'OFFENSIVE',
                'confidence': 'HIGH' | 'MEDIUM' | 'LOW',
                'factors': {
                    'spread_factor': float,
                    'signal_factor': float,
                    'grpan_factor': float,
                    'position_factor': float
                },
                'explanation': str
            }
        """
        try:
            # Extract inputs
            spread_percent = self._safe_float(market_data.get('spread_percent'))
            final_thg = self._safe_float(static_data.get('FINAL_THG'))
            
            # Signal strength (0.0 to 1.0)
            signal_strength = 0.5  # Default neutral
            if signal_data:
                confidence = signal_data.get('confidence', {})
                if isinstance(confidence, dict):
                    signal_strength = self._safe_float(confidence.get('total', 0.5)) or 0.5
                elif isinstance(confidence, (int, float)):
                    signal_strength = float(confidence)
            
            # GRPAN concentration (0.0 to 100.0)
            grpan_concentration = None
            if grpan_metrics:
                grpan_concentration = self._safe_float(grpan_metrics.get('concentration_percent'))
            
            # Position status
            has_position = False
            if position_analytics:
                has_position = position_analytics.get('status_flags', {}).get('position_exists', False)
            
            # Calculate factors (0.0 to 1.0, higher = more offensive)
            factors = {}
            
            # Spread factor: lower spread = more offensive
            spread_factor = 0.5  # Default neutral
            if spread_percent is not None:
                if spread_percent <= 0.3:
                    spread_factor = 1.0  # Very offensive
                elif spread_percent <= 0.5:
                    spread_factor = 0.75  # Offensive
                elif spread_percent <= 1.0:
                    spread_factor = 0.5  # Neutral
                elif spread_percent <= 2.0:
                    spread_factor = 0.25  # Defensive
                else:
                    spread_factor = 0.0  # Very defensive
            
            factors['spread_factor'] = spread_factor
            
            # Signal factor: stronger signal = more offensive
            signal_factor = signal_strength
            factors['signal_factor'] = signal_factor
            
            # GRPAN factor: higher concentration = more offensive
            grpan_factor = 0.5  # Default neutral
            if grpan_concentration is not None:
                if grpan_concentration >= 70.0:
                    grpan_factor = 1.0  # Very offensive
                elif grpan_concentration >= 50.0:
                    grpan_factor = 0.75  # Offensive
                elif grpan_concentration >= 30.0:
                    grpan_factor = 0.5  # Neutral
                else:
                    grpan_factor = 0.25  # Defensive
            factors['grpan_factor'] = grpan_factor
            
            # Position factor: having position = slightly more defensive (risk management)
            position_factor = 0.4 if has_position else 0.5
            factors['position_factor'] = position_factor
            
            # Calculate weighted average
            weights = {
                'spread_factor': 0.3,
                'signal_factor': 0.3,
                'grpan_factor': 0.2,
                'position_factor': 0.2
            }
            
            weighted_score = (
                factors['spread_factor'] * weights['spread_factor'] +
                factors['signal_factor'] * weights['signal_factor'] +
                factors['grpan_factor'] * weights['grpan_factor'] +
                factors['position_factor'] * weights['position_factor']
            )
            
            # Determine mode based on weighted score
            if weighted_score >= 0.7:
                mode = 'OFFENSIVE'
                confidence = 'HIGH' if weighted_score >= 0.85 else 'MEDIUM'
            elif weighted_score >= 0.4:
                mode = 'TRANSITION'
                confidence = 'MEDIUM'
            else:
                mode = 'DEFENSIVE'
                confidence = 'HIGH' if weighted_score <= 0.2 else 'MEDIUM'
            
            # Build explanation
            explanation_parts = []
            explanation_parts.append(f"Mode: {mode} (score: {weighted_score:.2f})")
            explanation_parts.append(f"Spread: {spread_percent:.2f}%" if spread_percent is not None else "Spread: N/A")
            explanation_parts.append(f"Signal: {signal_strength:.2f}")
            if grpan_concentration is not None:
                explanation_parts.append(f"GRPAN: {grpan_concentration:.1f}%")
            if has_position:
                explanation_parts.append("Has position")
            
            explanation = " | ".join(explanation_parts)
            
            return {
                'mode': mode,
                'confidence': confidence,
                'weighted_score': round(weighted_score, 3),
                'factors': {
                    'spread_factor': round(factors['spread_factor'], 2),
                    'signal_factor': round(factors['signal_factor'], 2),
                    'grpan_factor': round(factors['grpan_factor'], 2),
                    'position_factor': round(factors['position_factor'], 2)
                },
                'weights': weights,
                'explanation': explanation
            }
            
        except Exception as e:
            logger.error(f"Error computing exposure mode for {symbol}: {e}", exc_info=True)
            return {
                'mode': 'TRANSITION',
                'confidence': 'LOW',
                'weighted_score': 0.5,
                'factors': {
                    'spread_factor': 0.5,
                    'signal_factor': 0.5,
                    'grpan_factor': 0.5,
                    'position_factor': 0.5
                },
                'weights': {},
                'explanation': f'Error: {str(e)}'
            }
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None or value == 'N/A' or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None







