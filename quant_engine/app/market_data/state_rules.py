"""
State Transition Rules
Centralized logic for state transitions: IDLE -> WATCH -> CANDIDATE

Production-grade with:
- Externalized config (YAML)
- Anti-flapping / stability guards
- Explainable transitions
"""

import os
import yaml
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from app.core.logger import logger


class StateTransitionRules:
    """
    Defines rules for state transitions with stability guards.
    
    States:
    - IDLE: Default state, no action
    - WATCH: Symbol is being watched (meets some criteria)
    - CANDIDATE: Symbol is a candidate for trading (meets stronger criteria)
    
    Features:
    - All thresholds loaded from config file
    - Anti-flapping: requires N consecutive confirmations or T seconds
    - Explainable: transition reasons include stability guard info
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize with config file.
        
        Args:
            config_path: Path to state_rules.yaml config file
        """
        if config_path is None:
            # Default to config/state_rules.yaml relative to project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "app" / "config" / "state_rules.yaml"
        
        self.config = self._load_config(config_path)
        self._validate_config()
        
        # Stability tracking per symbol
        self._stability_tracking: Dict[str, Dict[str, Any]] = {}
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load YAML config file"""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"Config file not found: {config_path}, using defaults")
                return self._get_default_config()
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"Loaded state rules config from {config_path}")
            return config
            
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}", exc_info=True)
            logger.warning("Using default config")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default config if file not found"""
        return {
            'stability': {
                'required_confirmations': 3,
                'min_time_seconds': 5.0
            },
            'transitions': {
                'idle_to_watch': {
                    'max_spread_percent': 1.0,
                    'min_volume': 0
                },
                'watch_to_candidate': {
                    'max_spread_percent': 0.5,
                    'min_volume': 1000,
                    'min_final_thg': 0,
                    'min_smi': 0
                },
                'idle_to_watch_static': {
                    'min_spread_percent': 5.0,
                    'min_final_thg': 1.2,
                    'min_avg_adv': 5000
                }
            }
        }
    
    def _validate_config(self):
        """Validate config structure"""
        required_keys = ['stability', 'transitions']
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"Config missing required key: {key}")
        
        stability = self.config['stability']
        if 'required_confirmations' not in stability:
            raise ValueError("Config missing stability.required_confirmations")
        if 'min_time_seconds' not in stability:
            raise ValueError("Config missing stability.min_time_seconds")
    
    def evaluate_transition(
        self,
        symbol: str,
        current_state: str,
        static_data: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """
        Evaluate state transition with stability guards.
        
        Args:
            symbol: Symbol identifier
            current_state: Current state ('IDLE', 'WATCH', 'CANDIDATE')
            static_data: Static CSV data
            market_data: Live Hammer market data
            
        Returns:
            Tuple of (new_state, state_reason, transition_reason):
            - new_state: Target state (may be same as current if blocked by stability)
            - state_reason: Why this state was assigned
            - transition_reason: Why transition occurred (or why blocked)
        """
        try:
            # Extract metrics
            metrics = self._extract_metrics(static_data, market_data)
            
            if not metrics['has_market_data']:
                # No market data - always IDLE
                state_reason = {
                    'live_data_missing': True,
                    'bid': metrics['bid'],
                    'ask': metrics['ask'],
                    'last': metrics['last']
                }
                transition_reason = self._get_transition_reason(
                    current_state, 'IDLE', state_reason
                )
                # Reset stability tracking for IDLE (no market data)
                self._reset_stability_tracking(symbol)
                return ('IDLE', state_reason, transition_reason)
            
            # Evaluate desired state (without stability check)
            desired_state, state_reason, raw_transition_reason = self._evaluate_desired_state(
                current_state, metrics
            )
            
            # Apply stability guard
            actual_state, transition_reason = self._apply_stability_guard(
                symbol,
                current_state,
                desired_state,
                state_reason,
                raw_transition_reason
            )
            
            return (actual_state, state_reason, transition_reason)
                
        except Exception as e:
            logger.error(f"Error evaluating state transition for {symbol}: {e}", exc_info=True)
            error_reason = {'error': str(e)}
            return ('IDLE', error_reason, {'error': str(e)})
    
    def _evaluate_desired_state(
        self,
        current_state: str,
        metrics: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """Evaluate desired state without stability guards"""
        if current_state == 'IDLE':
            return self._evaluate_from_idle(metrics)
        elif current_state == 'WATCH':
            return self._evaluate_from_watch(metrics)
        elif current_state == 'CANDIDATE':
            return self._evaluate_from_candidate(metrics)
        else:
            logger.warning(f"Unknown state: {current_state}, defaulting to IDLE")
            return self._evaluate_from_idle(metrics)
    
    def _evaluate_from_idle(self, metrics: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """Evaluate transition from IDLE state"""
        # Check for CANDIDATE first (highest priority)
        candidate_result = self._check_candidate_criteria(metrics)
        if candidate_result:
            state_reason, transition_reason = candidate_result
            return ('CANDIDATE', state_reason, transition_reason)
        
        # Check for WATCH
        watch_result = self._check_watch_criteria(metrics)
        if watch_result:
            state_reason, transition_reason = watch_result
            return ('WATCH', state_reason, transition_reason)
        
        # Stay in IDLE
        state_reason = {
            'spread_percent': round(metrics['spread_percent'], 2) if metrics['spread_percent'] else None,
            'volume': metrics['volume'],
            'FINAL_THG': round(metrics['final_thg'], 2) if metrics['final_thg'] else None,
            'AVG_ADV': round(metrics['avg_adv'], 2) if metrics['avg_adv'] else None
        }
        transition_reason = {}  # No transition
        return ('IDLE', state_reason, transition_reason)
    
    def _evaluate_from_watch(self, metrics: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """Evaluate transition from WATCH state"""
        # Check for CANDIDATE (upgrade)
        candidate_result = self._check_candidate_criteria(metrics)
        if candidate_result:
            state_reason, transition_reason = candidate_result
            transition_reason['from'] = 'WATCH'
            transition_reason['to'] = 'CANDIDATE'
            return ('CANDIDATE', state_reason, transition_reason)
        
        # Check if still WATCH
        watch_result = self._check_watch_criteria(metrics)
        if watch_result:
            state_reason, _ = watch_result
            transition_reason = {}  # No transition
            return ('WATCH', state_reason, transition_reason)
        
        # Downgrade to IDLE
        state_reason = {
            'spread_percent': round(metrics['spread_percent'], 2) if metrics['spread_percent'] else None,
            'volume': metrics['volume'],
            'FINAL_THG': round(metrics['final_thg'], 2) if metrics['final_thg'] else None,
            'AVG_ADV': round(metrics['avg_adv'], 2) if metrics['avg_adv'] else None
        }
        transition_reason = {
            'from': 'WATCH',
            'to': 'IDLE',
            'reason': 'Watch criteria no longer met'
        }
        return ('IDLE', state_reason, transition_reason)
    
    def _evaluate_from_candidate(self, metrics: Dict[str, Any]) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """Evaluate transition from CANDIDATE state"""
        # Check if still CANDIDATE
        candidate_result = self._check_candidate_criteria(metrics)
        if candidate_result:
            state_reason, _ = candidate_result
            transition_reason = {}  # No transition
            return ('CANDIDATE', state_reason, transition_reason)
        
        # Check for WATCH (downgrade)
        watch_result = self._check_watch_criteria(metrics)
        if watch_result:
            state_reason, _ = watch_result
            transition_reason = {
                'from': 'CANDIDATE',
                'to': 'WATCH',
                'reason': 'Candidate criteria no longer met, but watch criteria still valid'
            }
            return ('WATCH', state_reason, transition_reason)
        
        # Downgrade to IDLE
        state_reason = {
            'spread_percent': round(metrics['spread_percent'], 2) if metrics['spread_percent'] else None,
            'volume': metrics['volume'],
            'FINAL_THG': round(metrics['final_thg'], 2) if metrics['final_thg'] else None,
            'AVG_ADV': round(metrics['avg_adv'], 2) if metrics['avg_adv'] else None
        }
        transition_reason = {
            'from': 'CANDIDATE',
            'to': 'IDLE',
            'reason': 'Candidate criteria no longer met'
        }
        return ('IDLE', state_reason, transition_reason)
    
    def _check_candidate_criteria(self, metrics: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Check if CANDIDATE criteria are met (using config thresholds)"""
        cfg = self.config['transitions']['watch_to_candidate']
        
        if (metrics['spread_percent'] is not None and metrics['spread_percent'] < cfg['max_spread_percent'] and
            metrics['volume'] is not None and metrics['volume'] > cfg['min_volume'] and
            metrics['final_thg'] is not None and metrics['final_thg'] > cfg['min_final_thg'] and
            metrics['smi'] is not None and metrics['smi'] > cfg['min_smi']):
            
            state_reason = {
                'spread_percent': round(metrics['spread_percent'], 2),
                'spread_percent_threshold': cfg['max_spread_percent'],
                'volume': metrics['volume'],
                'volume_threshold': cfg['min_volume'],
                'FINAL_THG': round(metrics['final_thg'], 2),
                'FINAL_THG_threshold': cfg['min_final_thg'],
                'SMI': round(metrics['smi'], 2),
                'SMI_threshold': cfg['min_smi']
            }
            
            transition_reason = {
                'triggered_by': 'candidate_criteria',
                'spread_percent': round(metrics['spread_percent'], 2),
                'volume': metrics['volume'],
                'FINAL_THG': round(metrics['final_thg'], 2),
                'SMI': round(metrics['smi'], 2)
            }
            
            return (state_reason, transition_reason)
        
        return None
    
    def _check_watch_criteria(self, metrics: Dict[str, Any]) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """Check if WATCH criteria are met (using config thresholds)"""
        cfg_spread = self.config['transitions']['idle_to_watch']
        cfg_static = self.config['transitions']['idle_to_watch_static']
        
        # WATCH: If spread is reasonable and has volume
        if (metrics['spread_percent'] is not None and metrics['spread_percent'] < cfg_spread['max_spread_percent'] and
            metrics['volume'] is not None and metrics['volume'] > cfg_spread['min_volume']):
            
            state_reason = {
                'spread_percent': round(metrics['spread_percent'], 2),
                'spread_percent_threshold': cfg_spread['max_spread_percent'],
                'volume': metrics['volume'],
                'volume_threshold': cfg_spread['min_volume']
            }
            
            transition_reason = {
                'triggered_by': 'watch_criteria_spread',
                'spread_percent': round(metrics['spread_percent'], 2),
                'volume': metrics['volume']
            }
            
            return (state_reason, transition_reason)
        
        # WATCH: High spread but good static metrics
        if (metrics['spread_percent'] is not None and metrics['spread_percent'] >= cfg_static['min_spread_percent'] and
            metrics['final_thg'] is not None and metrics['final_thg'] > cfg_static['min_final_thg'] and
            metrics['avg_adv'] is not None and metrics['avg_adv'] > cfg_static['min_avg_adv']):
            
            state_reason = {
                'spread_percent': round(metrics['spread_percent'], 2),
                'spread_percent_threshold': cfg_static['min_spread_percent'],
                'FINAL_THG': round(metrics['final_thg'], 2),
                'FINAL_THG_threshold': cfg_static['min_final_thg'],
                'AVG_ADV': round(metrics['avg_adv'], 2),
                'AVG_ADV_threshold': cfg_static['min_avg_adv']
            }
            
            transition_reason = {
                'triggered_by': 'watch_criteria_static',
                'spread_percent': round(metrics['spread_percent'], 2),
                'FINAL_THG': round(metrics['final_thg'], 2),
                'AVG_ADV': round(metrics['avg_adv'], 2)
            }
            
            return (state_reason, transition_reason)
        
        return None
    
    def _apply_stability_guard(
        self,
        symbol: str,
        current_state: str,
        desired_state: str,
        state_reason: Dict[str, Any],
        raw_transition_reason: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Apply stability guard to prevent state flapping.
        
        Returns:
            Tuple of (actual_state, transition_reason):
            - actual_state: State after stability check (may be current_state if blocked)
            - transition_reason: Updated with stability guard info if blocked
        """
        # No transition needed
        if desired_state == current_state:
            # Reset tracking if staying in same state
            self._reset_stability_tracking(symbol)
            return (current_state, {})
        
        # Initialize tracking if not exists
        if symbol not in self._stability_tracking:
            self._stability_tracking[symbol] = {
                'pending_state': None,
                'pending_state_reason': None,
                'consecutive_confirmations': 0,
                'first_confirmation_time': None
            }
        
        tracking = self._stability_tracking[symbol]
        stability_cfg = self.config['stability']
        required_confirmations = stability_cfg['required_confirmations']
        min_time_seconds = stability_cfg['min_time_seconds']
        
        # Check if this is a new pending state
        if tracking['pending_state'] != desired_state:
            # New pending transition
            tracking['pending_state'] = desired_state
            tracking['pending_state_reason'] = raw_transition_reason
            tracking['consecutive_confirmations'] = 1
            tracking['first_confirmation_time'] = datetime.now()
            
            # Block transition, return stability guard reason
            transition_reason = {
                'reason': 'stability_guard',
                'pending_state': desired_state,
                'confirmations': f"{tracking['consecutive_confirmations']}/{required_confirmations}",
                'time_elapsed_seconds': 0.0,
                'required_time_seconds': min_time_seconds
            }
            transition_reason.update(raw_transition_reason)
            return (current_state, transition_reason)
        
        # Same pending state - increment confirmation
        tracking['consecutive_confirmations'] += 1
        time_elapsed = (datetime.now() - tracking['first_confirmation_time']).total_seconds()
        
        # Check if stability requirements met
        confirmations_met = tracking['consecutive_confirmations'] >= required_confirmations
        time_met = time_elapsed >= min_time_seconds
        
        if confirmations_met or time_met:
            # Stability requirements met - allow transition
            transition_reason = tracking['pending_state_reason'].copy()
            transition_reason['stability_confirmations'] = tracking['consecutive_confirmations']
            transition_reason['stability_time_seconds'] = round(time_elapsed, 2)
            
            # Reset tracking
            self._reset_stability_tracking(symbol)
            
            return (desired_state, transition_reason)
        else:
            # Still waiting for stability
            transition_reason = {
                'reason': 'stability_guard',
                'pending_state': desired_state,
                'confirmations': f"{tracking['consecutive_confirmations']}/{required_confirmations}",
                'time_elapsed_seconds': round(time_elapsed, 2),
                'required_time_seconds': min_time_seconds
            }
            transition_reason.update(raw_transition_reason)
            return (current_state, transition_reason)
    
    def _reset_stability_tracking(self, symbol: str):
        """Reset stability tracking for a symbol"""
        if symbol in self._stability_tracking:
            del self._stability_tracking[symbol]
    
    def _extract_metrics(self, static_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and calculate all metrics"""
        bid = self._safe_float(market_data.get('bid'))
        ask = self._safe_float(market_data.get('ask'))
        last = self._safe_float(market_data.get('last') or market_data.get('price'))
        
        has_market_data = bool(bid and ask and last)
        
        spread_percent = None
        if bid and ask and bid > 0 and ask > 0:
            spread = ask - bid
            mid_price = (bid + ask) / 2
            if mid_price > 0:
                spread_percent = (spread / mid_price) * 100
        
        return {
            'has_market_data': has_market_data,
            'bid': bid,
            'ask': ask,
            'last': last,
            'spread_percent': spread_percent,
            'volume': self._safe_float(market_data.get('volume')),
            'final_thg': self._safe_float(static_data.get('FINAL_THG')),
            'smi': self._safe_float(static_data.get('SMI')),
            'avg_adv': self._safe_float(static_data.get('AVG_ADV'))
        }
    
    def _get_transition_reason(
        self,
        from_state: str,
        to_state: str,
        state_reason: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate transition reason"""
        if from_state == to_state:
            return {}  # No transition
        
        return {
            'from': from_state,
            'to': to_state,
            'reason': f'Transitioned from {from_state} to {to_state}',
            'triggered_by': state_reason
        }
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
