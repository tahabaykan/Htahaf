"""
PSFALGO Position Guard Engine
Implements hard risk guards: MAXALW, daily limits, 3h limits, cross-blocking.
"""

from typing import Dict, Any, Optional, List, Tuple
import yaml
import os
from pathlib import Path
from app.core.logger import logger
from app.psfalgo.state_store import PSFALGOStateStore


class PositionGuardEngine:
    """
    Implements position risk guards for PSFALGO.
    
    Guards:
    - MAXALW absolute limit
    - Daily net increase limit (MAXALW * multiplier from config)
    - 3H net change limit (MAXALW * multiplier from config)
    - No long->short crossing intraday
    """
    
    def __init__(self, state_store: Optional[PSFALGOStateStore] = None, config_path: Optional[str] = None):
        """
        Initialize position guard engine.
        
        Args:
            state_store: PSFALGOStateStore instance. If None, creates new one.
            config_path: Path to psfalgo_rules.yaml config file
        """
        self.state_store = state_store or PSFALGOStateStore()
        
        if config_path is None:
            # Default path: app/config/psfalgo_rules.yaml
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "app" / "config" / "psfalgo_rules.yaml"
        
        self.config_path = config_path
        self.config = self._load_config()
        
        # Extract config values
        self.maxalw_adv_divisor = self.config.get('maxalw', {}).get('adv_divisor', 10)
        self.daily_add_limit_multiplier = self.config.get('daily_add', {}).get('limit_multiplier', 0.75)
        self.change_3h_limit_multiplier = self.config.get('change_3h', {}).get('limit_multiplier', 0.50)
        
        logger.info(f"Position Guard Engine initialized with config: {config_path}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load PSFALGO rules from YAML config file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config:
                        return config
            logger.warning(f"PSFALGO rules config not found at {self.config_path}, using defaults")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading PSFALGO rules config: {e}", exc_info=True)
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default config if file not found"""
        return {
            'maxalw': {'adv_divisor': 10},
            'daily_add': {'limit_multiplier': 0.75},
            'change_3h': {'limit_multiplier': 0.50}
        }
    
    def evaluate_guards(
        self,
        symbol: str,
        snapshot: Dict[str, Any],
        static_data: Dict[str, Any],
        order_plan: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate all position guards for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            snapshot: Position snapshot from PositionSnapshotEngine
            static_data: Static data (AVG_ADV for MAXALW calculation)
            order_plan: Order plan (for checking potential actions)
            
        Returns:
            Guard evaluation dict with allowed_actions, block_reasons, thresholds, etc.
        """
        try:
            befday_qty = snapshot.get('befday_qty', 0.0)
            current_qty = snapshot.get('current_qty', 0.0)
            potential_qty = snapshot.get('potential_qty', 0.0)
            
            # Calculate MAXALW
            maxalw = self._calculate_maxalw(static_data)
            
            # Check MAXALW limits
            maxalw_exceeded_current = False
            maxalw_exceeded_potential = False
            if maxalw is not None:
                if abs(current_qty) > maxalw:
                    maxalw_exceeded_current = True
                if abs(potential_qty) > maxalw:
                    maxalw_exceeded_potential = True
            
            # Get daily tracker
            daily_tracker = self.state_store.get_daily_tracker(symbol)
            daily_add_used = daily_tracker['daily_add_used']
            # Daily limit from config
            daily_add_limit = maxalw * self.daily_add_limit_multiplier if maxalw is not None else None
            daily_add_remaining = (daily_add_limit - daily_add_used) if daily_add_limit is not None else None
            
            # Get 3h net change
            change_3h_net = self.state_store.get_3h_net_change(symbol)
            # 3h limit from config
            change_3h_limit = maxalw * self.change_3h_limit_multiplier if maxalw is not None else None
            change_3h_remaining = (change_3h_limit - abs(change_3h_net)) if change_3h_limit is not None else None
            
            # Check cross-blocking
            cross_blocked, cross_block_reason = self._check_cross_blocking(
                befday_qty, current_qty, potential_qty
            )
            
            # Determine allowed actions
            allowed_actions = self._determine_allowed_actions(
                befday_qty,
                current_qty,
                potential_qty,
                maxalw,
                maxalw_exceeded_current,
                maxalw_exceeded_potential,
                daily_add_used,
                daily_add_limit,
                change_3h_net,
                change_3h_limit,
                cross_blocked
            )
            
            # Determine guard status
            guard_status = self._determine_guard_status(
                maxalw_exceeded_current,
                maxalw_exceeded_potential,
                daily_add_used,
                daily_add_limit,
                change_3h_net,
                change_3h_limit,
                cross_blocked
            )
            
            # Build guard reason (explainable)
            guard_reason = self._build_guard_reason(
                maxalw,
                maxalw_exceeded_current,
                maxalw_exceeded_potential,
                daily_add_used,
                daily_add_limit,
                change_3h_net,
                change_3h_limit,
                cross_blocked,
                cross_block_reason
            )
            
            return {
                'maxalw': round(maxalw, 2) if maxalw is not None else None,
                'maxalw_exceeded_current': maxalw_exceeded_current,
                'maxalw_exceeded_potential': maxalw_exceeded_potential,
                'daily_add_used': round(daily_add_used, 2),
                'daily_add_limit': round(daily_add_limit, 2) if daily_add_limit is not None else None,
                'daily_add_remaining': round(daily_add_remaining, 2) if daily_add_remaining is not None else None,
                'change_3h_net': round(change_3h_net, 2),
                'change_3h_limit': round(change_3h_limit, 2) if change_3h_limit is not None else None,
                'change_3h_remaining': round(change_3h_remaining, 2) if change_3h_remaining is not None else None,
                'cross_blocked': cross_blocked,
                'cross_block_reason': cross_block_reason,
                'guard_status': guard_status,
                'guard_reason': guard_reason,
                'allowed_actions': allowed_actions
            }
            
        except Exception as e:
            logger.error(f"Error evaluating guards for {symbol}: {e}", exc_info=True)
            return {
                'maxalw': None,
                'maxalw_exceeded_current': False,
                'maxalw_exceeded_potential': False,
                'daily_add_used': 0.0,
                'daily_add_limit': None,
                'daily_add_remaining': None,
                'change_3h_net': 0.0,
                'change_3h_limit': None,
                'change_3h_remaining': None,
                'cross_blocked': False,
                'cross_block_reason': None,
                'guard_status': ['OK'],
                'guard_reason': {'error': str(e)},
                'allowed_actions': []
            }
    
    def _calculate_maxalw(self, static_data: Dict[str, Any]) -> Optional[float]:
        """
        Calculate MAXALW (maximum allowed) per symbol.
        
        Rules:
        - Use MAXALW field from static data if available
        - Otherwise: AVG_ADV / 10
        
        Args:
            static_data: Static data dict
            
        Returns:
            MAXALW value or None
        """
        # Try MAXALW field first
        for col_name in ['MAXALW', 'maxalw', 'MaxAlw', 'MAX_ALW']:
            if col_name in static_data:
                maxalw = self._safe_float(static_data.get(col_name))
                if maxalw is not None and maxalw > 0:
                    return maxalw
        
        # Fallback to AVG_ADV / adv_divisor (from config)
        avg_adv = self._safe_float(static_data.get('AVG_ADV'))
        if avg_adv is not None and avg_adv > 0:
            return avg_adv / float(self.maxalw_adv_divisor)
        
        return None
    
    def _check_cross_blocking(
        self,
        befday_qty: float,
        current_qty: float,
        potential_qty: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if cross-blocking applies (no long->short crossing intraday).
        
        Rules:
        - If befday_qty > 0, cannot cross to potential_qty < 0 (can reduce to 0)
        - If befday_qty < 0, cannot cross to potential_qty > 0 (can reduce to 0)
        
        Args:
            befday_qty: Before-day quantity
            current_qty: Current quantity
            potential_qty: Potential quantity
            
        Returns:
            Tuple of (cross_blocked: bool, reason: str | None)
        """
        threshold = 0.001
        
        if befday_qty > threshold:
            # Started long
            if potential_qty < -threshold:
                return True, f"Cannot cross from long (befday={befday_qty:.2f}) to short (potential={potential_qty:.2f})"
        elif befday_qty < -threshold:
            # Started short
            if potential_qty > threshold:
                return True, f"Cannot cross from short (befday={befday_qty:.2f}) to long (potential={potential_qty:.2f})"
        
        return False, None
    
    def _determine_allowed_actions(
        self,
        befday_qty: float,
        current_qty: float,
        potential_qty: float,
        maxalw: Optional[float],
        maxalw_exceeded_current: bool,
        maxalw_exceeded_potential: bool,
        daily_add_used: float,
        daily_add_limit: Optional[float],
        change_3h_net: float,
        change_3h_limit: Optional[float],
        cross_blocked: bool
    ) -> List[str]:
        """
        Determine allowed actions based on guards.
        
        Returns:
            List of allowed actions: ['ADD_LONG', 'ADD_SHORT', 'REDUCE_LONG', 'REDUCE_SHORT', 'FLAT']
        """
        allowed = []
        threshold = 0.001
        
        # Check if can add long
        can_add_long = True
        if befday_qty < -threshold:
            can_add_long = False  # Started short, cannot add long
        if maxalw is not None and abs(potential_qty) >= maxalw and potential_qty > current_qty:
            can_add_long = False  # Would exceed MAXALW
        if daily_add_limit is not None and daily_add_used >= daily_add_limit:
            can_add_long = False  # Daily limit reached
        if cross_blocked and potential_qty > threshold:
            can_add_long = False
        
        # Check if can add short
        can_add_short = True
        if befday_qty > threshold:
            can_add_short = False  # Started long, cannot add short
        if maxalw is not None and abs(potential_qty) >= maxalw and potential_qty < current_qty:
            can_add_short = False  # Would exceed MAXALW
        if daily_add_limit is not None and daily_add_used >= daily_add_limit:
            can_add_short = False  # Daily limit reached
        if cross_blocked and potential_qty < -threshold:
            can_add_short = False
        
        # Check if can reduce
        can_reduce_long = current_qty > threshold
        can_reduce_short = current_qty < -threshold
        
        # Always allow going flat
        allowed.append('FLAT')
        
        if can_add_long:
            allowed.append('ADD_LONG')
        if can_add_short:
            allowed.append('ADD_SHORT')
        if can_reduce_long:
            allowed.append('REDUCE_LONG')
        if can_reduce_short:
            allowed.append('REDUCE_SHORT')
        
        return allowed
    
    def _determine_guard_status(
        self,
        maxalw_exceeded_current: bool,
        maxalw_exceeded_potential: bool,
        daily_add_used: float,
        daily_add_limit: Optional[float],
        change_3h_net: float,
        change_3h_limit: Optional[float],
        cross_blocked: bool
    ) -> List[str]:
        """
        Determine guard status flags.
        
        Returns:
            List of status flags: ['OK', 'BLOCK_ADD', 'BLOCK_CROSS', 'BLOCK_DAILY', 'BLOCK_3H']
        """
        status = []
        
        if maxalw_exceeded_current or maxalw_exceeded_potential:
            status.append('BLOCK_ADD')
        
        if cross_blocked:
            status.append('BLOCK_CROSS')
        
        if daily_add_limit is not None and daily_add_used >= daily_add_limit:
            status.append('BLOCK_DAILY')
        
        if change_3h_limit is not None and abs(change_3h_net) >= change_3h_limit:
            status.append('BLOCK_3H')
        
        if not status:
            status.append('OK')
        
        return status
    
    def _build_guard_reason(
        self,
        maxalw: Optional[float],
        maxalw_exceeded_current: bool,
        maxalw_exceeded_potential: bool,
        daily_add_used: float,
        daily_add_limit: Optional[float],
        change_3h_net: float,
        change_3h_limit: Optional[float],
        cross_blocked: bool,
        cross_block_reason: Optional[str]
    ) -> Dict[str, Any]:
        """
        Build explainable guard reason with inputs and thresholds.
        
        Returns:
            Dict with explanation, inputs, and thresholds
        """
        reason = {
            'explanation': [],
            'inputs': {},
            'thresholds': {}
        }
        
        if maxalw is not None:
            reason['thresholds']['maxalw'] = maxalw
            reason['inputs']['current_qty'] = None  # Will be filled by caller if needed
            reason['inputs']['potential_qty'] = None  # Will be filled by caller if needed
            
            if maxalw_exceeded_current:
                reason['explanation'].append(f"Current qty exceeds MAXALW ({maxalw:.2f})")
            if maxalw_exceeded_potential:
                reason['explanation'].append(f"Potential qty exceeds MAXALW ({maxalw:.2f})")
        
        if daily_add_limit is not None:
            reason['thresholds']['daily_add_limit'] = daily_add_limit
            reason['inputs']['daily_add_used'] = daily_add_used
            if daily_add_used >= daily_add_limit:
                reason['explanation'].append(f"Daily add limit reached ({daily_add_used:.2f} >= {daily_add_limit:.2f})")
        
        if change_3h_limit is not None:
            reason['thresholds']['change_3h_limit'] = change_3h_limit
            reason['inputs']['change_3h_net'] = change_3h_net
            if abs(change_3h_net) >= change_3h_limit:
                reason['explanation'].append(f"3H change limit reached ({change_3h_net:.2f} >= {change_3h_limit:.2f})")
        
        if cross_blocked:
            reason['explanation'].append(f"Cross-blocked: {cross_block_reason}")
        
        if not reason['explanation']:
            reason['explanation'].append("All guards OK")
        
        return reason
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None or value == 'N/A' or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

