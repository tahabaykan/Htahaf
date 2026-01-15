"""
Intent Engine
Determines trading intent based on state and market conditions.

Intent values:
- WANT_BUY: System wants to buy (conditions met)
- WANT_SELL: System wants to sell (conditions met)
- WAIT: Wait for better conditions
- BLOCKED: Blocked by some rule
"""

import os
import yaml
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from app.core.logger import logger


class IntentEngine:
    """
    Determines trading intent based on state and market conditions.
    
    Intent is a decision layer between STATE and actual trading.
    It answers: "Given the current state, what should we do?"
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize with config file.
        
        Args:
            config_path: Path to intent_rules.yaml config file
        """
        if config_path is None:
            # Default to config/intent_rules.yaml relative to project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "app" / "config" / "intent_rules.yaml"
        
        self.config = self._load_config(config_path)
        self._validate_config()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load YAML config file"""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"Intent config file not found: {config_path}, using defaults")
                return self._get_default_config()
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"Loaded intent rules config from {config_path}")
            return config
            
        except Exception as e:
            logger.error(f"Error loading intent config from {config_path}: {e}", exc_info=True)
            logger.warning("Using default intent config")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default config if file not found"""
        return {
            'intent': {
                'watch': {
                    'max_spread_percent_for_intent': 2.0
                },
                'candidate': {
                    'want_buy': {
                        'max_spread_percent': 0.5,
                        'min_volume': 1000
                    },
                    'want_sell': {
                        'max_spread_percent': 0.5,
                        'min_volume': 1000
                    }
                }
            }
        }
    
    def _validate_config(self):
        """Validate config structure"""
        if 'intent' not in self.config:
            raise ValueError("Config missing required key: intent")
    
    def compute_intent(
        self,
        state: str,
        market_data: Dict[str, Any],
        static_data: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Compute trading intent based on state and conditions.
        
        Args:
            state: Current state ('IDLE', 'WATCH', 'CANDIDATE')
            market_data: Live market data (bid, ask, last, spread_percent, volume)
            static_data: Static CSV data (FINAL_THG, SHORT_FINAL, AVG_ADV, SMI)
            
        Returns:
            Tuple of (intent, intent_reason):
            - intent: 'WANT_BUY', 'WANT_SELL', 'WAIT', or 'BLOCKED'
            - intent_reason: Dict explaining why this intent was assigned
        """
        try:
            # Extract metrics
            spread_percent = self._safe_float(market_data.get('spread_percent'))
            volume = self._safe_float(market_data.get('volume'))
            bid = self._safe_float(market_data.get('bid'))
            ask = self._safe_float(market_data.get('ask'))
            
            # IDLE state -> always WAIT
            if state == 'IDLE':
                intent_reason = {
                    'reason': 'state_idle',
                    'state': state,
                    'message': 'State is IDLE, waiting for conditions to improve'
                }
                return ('WAIT', intent_reason)
            
            # WATCH state
            if state == 'WATCH':
                return self._compute_watch_intent(spread_percent, volume, market_data, static_data)
            
            # CANDIDATE state
            if state == 'CANDIDATE':
                return self._compute_candidate_intent(spread_percent, volume, market_data, static_data)
            
            # Unknown state -> WAIT
            logger.warning(f"Unknown state for intent computation: {state}")
            intent_reason = {
                'reason': 'unknown_state',
                'state': state,
                'message': f'Unknown state: {state}'
            }
            return ('WAIT', intent_reason)
            
        except Exception as e:
            logger.error(f"Error computing intent: {e}", exc_info=True)
            error_reason = {
                'reason': 'error',
                'error': str(e)
            }
            return ('WAIT', error_reason)
    
    def _compute_watch_intent(
        self,
        spread_percent: Optional[float],
        volume: Optional[float],
        market_data: Dict[str, Any],
        static_data: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """Compute intent for WATCH state"""
        cfg = self.config['intent']['watch']
        max_spread = cfg['max_spread_percent_for_intent']
        
        # If spread is too high, wait
        if spread_percent is not None and spread_percent > max_spread:
            intent_reason = {
                'reason': 'spread_too_high',
                'state': 'WATCH',
                'spread_percent': round(spread_percent, 2),
                'max_spread_percent': max_spread,
                'message': f'Spread {spread_percent:.2f}% exceeds maximum {max_spread}% for intent'
            }
            return ('WAIT', intent_reason)
        
        # Otherwise, still watching (wait)
        intent_reason = {
            'reason': 'watching',
            'state': 'WATCH',
            'spread_percent': round(spread_percent, 2) if spread_percent else None,
            'volume': volume,
            'message': 'Watching for better conditions'
        }
        return ('WAIT', intent_reason)
    
    def _compute_candidate_intent(
        self,
        spread_percent: Optional[float],
        volume: Optional[float],
        market_data: Dict[str, Any],
        static_data: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """Compute intent for CANDIDATE state"""
        cfg = self.config['intent']['candidate']['want_buy']
        max_spread = cfg['max_spread_percent']
        min_volume = cfg['min_volume']
        
        # Check if conditions are met for WANT_BUY
        spread_ok = spread_percent is not None and spread_percent <= max_spread
        volume_ok = volume is not None and volume >= min_volume
        
        if spread_ok and volume_ok:
            intent_reason = {
                'reason': 'conditions_met',
                'state': 'CANDIDATE',
                'spread_percent': round(spread_percent, 2),
                'spread_threshold': max_spread,
                'volume': volume,
                'volume_threshold': min_volume,
                'message': 'All conditions met for buy intent'
            }
            return ('WANT_BUY', intent_reason)
        
        # Conditions not met - explain why
        reasons = []
        if not spread_ok:
            reasons.append(f'spread {spread_percent:.2f}% > {max_spread}%' if spread_percent else 'spread missing')
        if not volume_ok:
            reasons.append(f'volume {volume} < {min_volume}' if volume else 'volume missing')
        
        intent_reason = {
            'reason': 'conditions_not_met',
            'state': 'CANDIDATE',
            'spread_percent': round(spread_percent, 2) if spread_percent else None,
            'spread_threshold': max_spread,
            'volume': volume,
            'volume_threshold': min_volume,
            'blocking_reasons': reasons,
            'message': f'Waiting: {", ".join(reasons)}'
        }
        return ('WAIT', intent_reason)
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None








