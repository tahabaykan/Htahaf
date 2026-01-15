"""
Symbol State Layer
Computes symbol state (IDLE, WATCH, CANDIDATE) using centralized state rules
"""

from typing import Dict, Any, Optional, Tuple

from app.core.logger import logger
from app.market_data.state_rules import StateTransitionRules


class SymbolStateEngine:
    """
    Computes symbol state based on static and live data.
    Uses centralized StateTransitionRules for state transitions.
    
    States:
    - IDLE: Default state, no action
    - WATCH: Symbol is being watched (meets some criteria)
    - CANDIDATE: Symbol is a candidate for trading (meets stronger criteria)
    """
    
    def __init__(self):
        self.transition_rules = StateTransitionRules()
        # Track current state for each symbol
        self._current_states: Dict[str, str] = {}
        # Track last transition reason for each symbol
        self._last_transitions: Dict[str, Dict[str, Any]] = {}
    
    def compute_state(
        self,
        symbol: str,
        static_data: Dict[str, Any],
        market_data: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        """
        Compute symbol state and reason using centralized transition rules.
        
        Args:
            symbol: PREF_IBKR symbol
            static_data: Static CSV data
            market_data: Live Hammer market data
            
        Returns:
            Tuple of (state, state_reason, transition_reason):
            - state: 'IDLE', 'WATCH', or 'CANDIDATE'
            - state_reason: Dict explaining why this state was assigned
            - transition_reason: Dict explaining why transition occurred (if state changed)
        """
        try:
            # Get current state (default to IDLE if not tracked)
            current_state = self._current_states.get(symbol, 'IDLE')
            
            # Evaluate transition using centralized rules (with stability guards)
            new_state, state_reason, transition_reason = self.transition_rules.evaluate_transition(
                symbol,
                current_state,
                static_data,
                market_data
            )
            
            # Update state tracking if state changed
            if new_state != current_state:
                self._current_states[symbol] = new_state
                # Store transition reason if transition occurred
                if transition_reason:
                    self._last_transitions[symbol] = transition_reason
            
            return (new_state, state_reason, transition_reason)
            
        except Exception as e:
            logger.error(f"Error computing state for {symbol}: {e}", exc_info=True)
            error_reason = {'error': str(e)}
            return ('IDLE', error_reason, error_reason)
    
    def get_last_transition(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get last transition reason for a symbol"""
        return self._last_transitions.get(symbol)
    
    def get_current_state(self, symbol: str) -> str:
        """Get current tracked state for a symbol"""
        return self._current_states.get(symbol, 'IDLE')

