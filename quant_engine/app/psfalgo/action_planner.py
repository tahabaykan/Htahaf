"""
PSFALGO Action Planner
DRY-RUN ONLY - Produces action proposals without execution.

This planner respects PositionGuardEngine constraints and implements:
- KARBOTU logic (reduce based on Fbtot/SFStot bands)
- ADDNEWPOS logic (add when OFFENSIVE mode)
- REDUCEMORE logic (reduce when DEFENSIVE/TRANSITION mode)
"""

from typing import Dict, Any, Optional
import yaml
import os
from pathlib import Path
from app.core.logger import logger


class PSFALGOActionPlanner:
    """
    Plans PSFALGO actions based on metrics and guard constraints.
    
    DRY-RUN ONLY: No order placement, only action proposals.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize PSFALGO Action Planner with config file.
        
        Args:
            config_path: Path to psfalgo_rules.yaml config file
        """
        if config_path is None:
            # Default path: app/config/psfalgo_rules.yaml
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "app" / "config" / "psfalgo_rules.yaml"
        
        self.config_path = config_path
        self.config = self._load_config()
        
        # Extract config values
        self.min_lot = self.config.get('min_lot', 400)
        self.reduce_size_bands = self.config.get('reduce_size_bands', {
            'strong': {'threshold': 0.7, 'size_percent': 50.0},
            'medium': {'threshold': 0.5, 'size_percent': 40.0},
            'weak': {'threshold': 0.3, 'size_percent': 30.0}
        })
        self.reducemore_size_percent = self.config.get('reducemore', {}).get('size_percent', 25.0)
        self.add_size_bands = self.config.get('add_size_bands', {
            'strong': {'min_fbtot': 0.6, 'min_sfstot': 0.6, 'size_percent': 30.0},
            'default': {'size_percent': 20.0}
        })
        
        logger.info(f"PSFALGO Action Planner initialized with config: {config_path}")
    
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
            'min_lot': 400,
            'reduce_size_bands': {
                'strong': {'threshold': 0.7, 'size_percent': 50.0},
                'medium': {'threshold': 0.5, 'size_percent': 40.0},
                'weak': {'threshold': 0.3, 'size_percent': 30.0}
            },
            'reducemore': {'size_percent': 25.0},
            'add_size_bands': {
                'strong': {'min_fbtot': 0.6, 'min_sfstot': 0.6, 'size_percent': 30.0},
                'default': {'size_percent': 20.0}
            }
        }
    
    def plan_action(
        self,
        symbol: str,
        snapshot: Dict[str, Any],
        guards: Dict[str, Any],
        janall_metrics: Dict[str, Any],
        exposure_mode: Dict[str, Any],
        signal_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Plan PSFALGO action for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            snapshot: Position snapshot from PositionSnapshotEngine
            guards: Guard evaluation from PositionGuardEngine
            janall_metrics: Janall metrics (Fbtot, SFStot, GORT)
            exposure_mode: Exposure mode (DEFENSIVE/TRANSITION/OFFENSIVE)
            signal_data: Signal data (optional)
            
        Returns:
            Action plan dict:
            {
                'action': 'REDUCE_LONG' | 'REDUCE_SHORT' | 'ADD_LONG' | 'ADD_SHORT' | 'HOLD' | 'BLOCKED',
                'size_percent': float (0-100),
                'size_lot_estimate': int,
                'reason': str,
                'blocked': bool,
                'block_reason': str | None
            }
        """
        try:
            # Extract inputs
            current_qty = snapshot.get('current_qty', 0.0)
            position_state = snapshot.get('position_state', 'NO_CHANGE')
            allowed_actions = guards.get('allowed_actions', [])
            guard_status = guards.get('guard_status', [])
            maxalw = guards.get('maxalw')
            
            exposure_mode_value = exposure_mode.get('mode', 'TRANSITION') if exposure_mode else 'TRANSITION'
            
            fbtot = self._safe_float(janall_metrics.get('fbtot'))
            sfstot = self._safe_float(janall_metrics.get('sfstot'))
            gort = self._safe_float(janall_metrics.get('gort'))
            
            # Check if blocked by guards
            if 'BLOCKED' in guard_status or not allowed_actions:
                return {
                    'action': 'BLOCKED',
                    'size_percent': 0.0,
                    'size_lot_estimate': 0,
                    'reason': 'Blocked by position guards',
                    'blocked': True,
                    'block_reason': guards.get('guard_reason', {}).get('explanation', ['Unknown'])[0] if guards.get('guard_reason') else 'Guard constraints not met'
                }
            
            # Determine action based on exposure mode and position state
            action = 'HOLD'
            size_percent = 0.0
            reason_parts = []
            
            # KARBOTU logic: Reduce based on Fbtot/SFStot bands (from config)
            applied_rule_key = None
            if position_state in ['LONG_ADD', 'LONG_REDUCE'] and current_qty > 0:
                # Long position - check Fbtot
                if fbtot is not None:
                    strong_band = self.reduce_size_bands.get('strong', {})
                    medium_band = self.reduce_size_bands.get('medium', {})
                    weak_band = self.reduce_size_bands.get('weak', {})
                    
                    if fbtot >= strong_band.get('threshold', 0.7):
                        if 'REDUCE_LONG' in allowed_actions:
                            action = 'REDUCE_LONG'
                            size_percent = strong_band.get('size_percent', 50.0)
                            applied_rule_key = 'karbotu_strong'
                            reason_parts.append(f"KARBOTU: Fbtot {fbtot:.2f} >= {strong_band.get('threshold', 0.7)} (strong band)")
                    elif fbtot >= medium_band.get('threshold', 0.5):
                        if 'REDUCE_LONG' in allowed_actions:
                            action = 'REDUCE_LONG'
                            size_percent = medium_band.get('size_percent', 40.0)
                            applied_rule_key = 'karbotu_medium'
                            reason_parts.append(f"KARBOTU: Fbtot {fbtot:.2f} >= {medium_band.get('threshold', 0.5)} (medium band)")
                    elif fbtot >= weak_band.get('threshold', 0.3):
                        if 'REDUCE_LONG' in allowed_actions:
                            action = 'REDUCE_LONG'
                            size_percent = weak_band.get('size_percent', 30.0)
                            applied_rule_key = 'karbotu_weak'
                            reason_parts.append(f"KARBOTU: Fbtot {fbtot:.2f} >= {weak_band.get('threshold', 0.3)} (weak band)")
            
            elif position_state in ['SHORT_ADD', 'SHORT_REDUCE'] and current_qty < 0:
                # Short position - check SFStot
                if sfstot is not None:
                    strong_band = self.reduce_size_bands.get('strong', {})
                    medium_band = self.reduce_size_bands.get('medium', {})
                    weak_band = self.reduce_size_bands.get('weak', {})
                    
                    if sfstot >= strong_band.get('threshold', 0.7):
                        if 'REDUCE_SHORT' in allowed_actions:
                            action = 'REDUCE_SHORT'
                            size_percent = strong_band.get('size_percent', 50.0)
                            applied_rule_key = 'karbotu_strong'
                            reason_parts.append(f"KARBOTU: SFStot {sfstot:.2f} >= {strong_band.get('threshold', 0.7)} (strong band)")
                    elif sfstot >= medium_band.get('threshold', 0.5):
                        if 'REDUCE_SHORT' in allowed_actions:
                            action = 'REDUCE_SHORT'
                            size_percent = medium_band.get('size_percent', 40.0)
                            applied_rule_key = 'karbotu_medium'
                            reason_parts.append(f"KARBOTU: SFStot {sfstot:.2f} >= {medium_band.get('threshold', 0.5)} (medium band)")
                    elif sfstot >= weak_band.get('threshold', 0.3):
                        if 'REDUCE_SHORT' in allowed_actions:
                            action = 'REDUCE_SHORT'
                            size_percent = weak_band.get('size_percent', 30.0)
                            applied_rule_key = 'karbotu_weak'
                            reason_parts.append(f"KARBOTU: SFStot {sfstot:.2f} >= {weak_band.get('threshold', 0.3)} (weak band)")
            
            # REDUCEMORE logic: Reduce when DEFENSIVE or TRANSITION (from config)
            if action == 'HOLD' and exposure_mode_value in ['DEFENSIVE', 'TRANSITION']:
                if current_qty > 0 and 'REDUCE_LONG' in allowed_actions:
                    action = 'REDUCE_LONG'
                    size_percent = self.reducemore_size_percent
                    applied_rule_key = 'reducemore'
                    reason_parts.append(f"REDUCEMORE: ExposureMode {exposure_mode_value}")
                elif current_qty < 0 and 'REDUCE_SHORT' in allowed_actions:
                    action = 'REDUCE_SHORT'
                    size_percent = self.reducemore_size_percent
                    applied_rule_key = 'reducemore'
                    reason_parts.append(f"REDUCEMORE: ExposureMode {exposure_mode_value}")
            
            # ADDNEWPOS logic: Add when OFFENSIVE mode (from config)
            if action == 'HOLD' and exposure_mode_value == 'OFFENSIVE':
                strong_band = self.add_size_bands.get('strong', {})
                default_band = self.add_size_bands.get('default', {})
                min_fbtot = strong_band.get('min_fbtot', 0.6)
                min_sfstot = strong_band.get('min_sfstot', 0.6)
                
                # Check if we can add long
                if fbtot is not None and fbtot >= min_fbtot:
                    if 'ADD_LONG' in allowed_actions:
                        action = 'ADD_LONG'
                        applied_rule_key = 'addnewpos_strong'
                        # Size based on available capacity
                        if maxalw is not None:
                            current_abs = abs(current_qty)
                            available = max(0, maxalw - current_abs)
                            if available > 0:
                                # Suggest size_percent of available capacity
                                size_percent = min(strong_band.get('size_percent', 30.0), (available / maxalw) * 100)
                            else:
                                size_percent = 0.0
                        else:
                            size_percent = default_band.get('size_percent', 20.0)
                            applied_rule_key = 'addnewpos_default'
                        reason_parts.append(f"ADDNEWPOS: ExposureMode OFFENSIVE, Fbtot {fbtot:.2f} >= {min_fbtot}")
                
                # Check if we can add short
                elif sfstot is not None and sfstot >= min_sfstot:
                    if 'ADD_SHORT' in allowed_actions:
                        action = 'ADD_SHORT'
                        applied_rule_key = 'addnewpos_strong'
                        # Size based on available capacity
                        if maxalw is not None:
                            current_abs = abs(current_qty)
                            available = max(0, maxalw - current_abs)
                            if available > 0:
                                # Suggest size_percent of available capacity
                                size_percent = min(strong_band.get('size_percent', 30.0), (available / maxalw) * 100)
                            else:
                                size_percent = 0.0
                        else:
                            size_percent = default_band.get('size_percent', 20.0)
                            applied_rule_key = 'addnewpos_default'
                        reason_parts.append(f"ADDNEWPOS: ExposureMode OFFENSIVE, SFStot {sfstot:.2f} >= {min_sfstot}")
            
            # Calculate size_lot_estimate (with min_lot constraint)
            size_lot_estimate = 0
            size_lot_capped_reason = None
            if action in ['ADD_LONG', 'ADD_SHORT', 'REDUCE_LONG', 'REDUCE_SHORT']:
                if maxalw is not None:
                    # Estimate based on MAXALW
                    size_lot_estimate = int((maxalw * size_percent) / 100.0)
                elif abs(current_qty) > 0:
                    # Estimate based on current position
                    size_lot_estimate = int((abs(current_qty) * size_percent) / 100.0)
                else:
                    # Default estimate (small position)
                    size_lot_estimate = int(size_percent)  # Assume 1% = 1 lot for small positions
                
                # Apply min_lot constraint
                if size_lot_estimate > 0 and size_lot_estimate < self.min_lot:
                    size_lot_capped_reason = f"Size {size_lot_estimate} < min_lot {self.min_lot}, capped to {self.min_lot}"
                    size_lot_estimate = self.min_lot
            
            # Build reason string
            reason = "; ".join(reason_parts) if reason_parts else "No action required"
            
            # Check if action is actually blocked
            blocked = False
            block_reason = None
            if action != 'HOLD' and action != 'BLOCKED':
                # Verify action is in allowed_actions
                if action not in allowed_actions:
                    blocked = True
                    block_reason = f"Action {action} not in allowed_actions: {allowed_actions}"
                    action = 'BLOCKED'
                    size_percent = 0.0
                    size_lot_estimate = 0
            
            return {
                'action': action,
                'size_percent': round(size_percent, 2),
                'size_lot_estimate': size_lot_estimate,
                'size_lot_capped_reason': size_lot_capped_reason,
                'applied_rule_key': applied_rule_key,
                'reason': reason,
                'blocked': blocked,
                'block_reason': block_reason
            }
            
        except Exception as e:
            logger.error(f"Error planning PSFALGO action for {symbol}: {e}", exc_info=True)
            return {
                'action': 'BLOCKED',
                'size_percent': 0.0,
                'size_lot_estimate': 0,
                'reason': f'Error: {str(e)}',
                'blocked': True,
                'block_reason': str(e)
            }
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None or value == 'N/A' or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

