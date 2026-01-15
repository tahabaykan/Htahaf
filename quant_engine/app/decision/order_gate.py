"""
Order Gate
Pre-execution decision layer - human-in-the-loop safety.

Gate Status:
- AUTO_APPROVED: Order can proceed automatically
- MANUAL_REVIEW: Requires human review before execution
- BLOCKED: Order is blocked and cannot proceed

This is a safety layer before actual execution.
"""

import yaml
from typing import Dict, Any, Optional
from pathlib import Path

from app.core.logger import logger


class OrderGate:
    """
    Pre-execution gate for order safety checks.
    
    This is a human-in-the-loop safety layer - NO execution.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize with config file.
        
        Args:
            config_path: Path to order_gate_rules.yaml config file
        """
        if config_path is None:
            # Default to config/order_gate_rules.yaml relative to project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "app" / "config" / "order_gate_rules.yaml"
        
        self.config = self._load_config(config_path)
        self._validate_config()
        
        # Runtime flags (can be set via API or UI)
        self.user_global_block = False  # Global block flag
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load YAML config file"""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"Order gate config file not found: {config_path}, using defaults")
                return self._get_default_config()
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"Loaded order gate rules config from {config_path}")
            return config
            
        except Exception as e:
            logger.error(f"Error loading order gate config from {config_path}: {e}", exc_info=True)
            logger.warning("Using default order gate config")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default config if file not found"""
        return {
            'gate': {
                'auto_approved': {
                    'min_urgency': 'HIGH',
                    'max_spread_percent': 0.3
                },
                'manual_review': {
                    'urgency': 'MEDIUM'
                },
                'blocked': {
                    'max_spread_percent': 1.5,
                    'min_final_thg': 0.0
                }
            }
        }
    
    def _validate_config(self):
        """Validate config structure"""
        if 'gate' not in self.config:
            raise ValueError("Config missing required key: gate")
    
    def evaluate_gate(
        self,
        order_plan: Dict[str, Any],
        queue_status: Dict[str, Any],
        market_data: Dict[str, Any],
        static_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate order gate status.
        
        Args:
            order_plan: Order plan dict from OrderPlanner
            queue_status: Queue status dict from OrderQueue
            market_data: Live market data
            static_data: Static CSV data
            
        Returns:
            Gate status dict:
            {
                'gate_status': 'AUTO_APPROVED' | 'MANUAL_REVIEW' | 'BLOCKED',
                'gate_reason': dict with explanation
            }
        """
        try:
            # If order plan action is NONE, no gate evaluation needed
            if order_plan.get('action') == 'NONE':
                return {
                    'gate_status': 'BLOCKED',
                    'gate_reason': {
                        'reason': 'no_order_plan',
                        'message': 'No order plan to evaluate'
                    }
                }
            
            # Extract metrics
            urgency = order_plan.get('urgency', 'LOW')
            intent = order_plan.get('intent', 'WAIT')  # Get intent from order_plan
            spread_percent = self._safe_float(market_data.get('spread_percent'))
            final_thg = self._safe_float(static_data.get('FINAL_THG'))
            
            # Get GRPAN metrics from market_data (if available)
            # GRPAN metrics are added to market_data in the API layer
            grpan_concentration = self._safe_float(market_data.get('grpan_concentration_percent'))
            grpan_print_count = market_data.get('grpan_print_count', 0)
            grpan_real_lot_count = self._safe_float(market_data.get('grpan_real_lot_count'))
            grpan_price = self._safe_float(market_data.get('grpan_price'))
            
            # Check BLOCKED conditions first (highest priority)
            blocked_reason = self._check_blocked(spread_percent, final_thg)
            if blocked_reason:
                return {
                    'gate_status': 'BLOCKED',
                    'gate_reason': blocked_reason
                }
            
            # Check GRPAN filter: If intent is WANT_BUY or WANT_SELL and concentration < 50%, require MANUAL_REVIEW
            # With false positive reduction: ringlen<8 skip, real_lot_count>=2 allow MEDIUM
            grpan_review_reason = self._check_grpan_filter(
                intent, 
                grpan_concentration,
                grpan_print_count,
                grpan_real_lot_count,
                grpan_price
            )
            if grpan_review_reason:
                return {
                    'gate_status': 'MANUAL_REVIEW',
                    'gate_reason': grpan_review_reason
                }
            
            # Check AUTO_APPROVED conditions
            auto_approved_reason = self._check_auto_approved(urgency, spread_percent)
            if auto_approved_reason:
                return {
                    'gate_status': 'AUTO_APPROVED',
                    'gate_reason': auto_approved_reason
                }
            
            # Check MANUAL_REVIEW conditions
            manual_review_reason = self._check_manual_review(urgency)
            if manual_review_reason:
                return {
                    'gate_status': 'MANUAL_REVIEW',
                    'gate_reason': manual_review_reason
                }
            
            # Default to MANUAL_REVIEW if no conditions met
            return {
                'gate_status': 'MANUAL_REVIEW',
                'gate_reason': {
                    'reason': 'default_manual_review',
                    'urgency': urgency,
                    'spread_percent': spread_percent,
                    'message': 'Defaulting to manual review - conditions not met for auto-approval'
                }
            }
            
        except Exception as e:
            logger.error(f"Error evaluating order gate: {e}", exc_info=True)
            return {
                'gate_status': 'BLOCKED',
                'gate_reason': {
                    'reason': 'error',
                    'error': str(e)
                }
            }
    
    def _check_blocked(
        self,
        spread_percent: Optional[float],
        final_thg: Optional[float]
    ) -> Optional[Dict[str, Any]]:
        """Check if order should be BLOCKED"""
        cfg = self.config['gate']['blocked']
        reasons = []
        
        # Check global block flag
        if self.user_global_block:
            return {
                'reason': 'global_block_active',
                'user_global_block': True,
                'message': 'Global block is active - all orders blocked'
            }
        
        # Check spread
        if spread_percent is not None and spread_percent > cfg['max_spread_percent']:
            reasons.append(f'spread {spread_percent:.2f}% > {cfg["max_spread_percent"]}%')
        
        # Check FINAL_THG
        if final_thg is not None and final_thg < cfg['min_final_thg']:
            reasons.append(f'FINAL_THG {final_thg:.2f} < {cfg["min_final_thg"]}')
        
        if reasons:
            return {
                'reason': 'blocked_conditions_met',
                'blocking_reasons': reasons,
                'spread_percent': spread_percent,
                'spread_threshold': cfg['max_spread_percent'],
                'final_thg': final_thg,
                'final_thg_threshold': cfg['min_final_thg'],
                'message': f'Order blocked: {", ".join(reasons)}'
            }
        
        return None
    
    def _check_auto_approved(
        self,
        urgency: str,
        spread_percent: Optional[float]
    ) -> Optional[Dict[str, Any]]:
        """Check if order should be AUTO_APPROVED"""
        cfg = self.config['gate']['auto_approved']
        
        # Check urgency
        urgency_levels = {'LOW': 1, 'MEDIUM': 2, 'HIGH': 3}
        required_urgency = urgency_levels.get(cfg['min_urgency'], 3)
        current_urgency = urgency_levels.get(urgency, 1)
        
        if current_urgency < required_urgency:
            return None
        
        # Check spread
        if spread_percent is not None and spread_percent <= cfg['max_spread_percent']:
            return {
                'reason': 'auto_approved_conditions_met',
                'urgency': urgency,
                'urgency_required': cfg['min_urgency'],
                'spread_percent': spread_percent,
                'spread_threshold': cfg['max_spread_percent'],
                'message': f'Auto-approved: urgency {urgency} and spread {spread_percent:.2f}% <= {cfg["max_spread_percent"]}%'
            }
        
        return None
    
    def _check_grpan_filter(
        self,
        intent: str,
        grpan_concentration: Optional[float],
        grpan_print_count: int = 0,
        grpan_real_lot_count: Optional[float] = None,
        grpan_price: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Check GRPAN concentration filter with false positive reduction.
        
        Rules:
        - If intent is WANT_BUY or WANT_SELL and grpan_concentration < 50%, require MANUAL_REVIEW
        - FALSE POSITIVE REDUCTION:
          1. ringlen < 8: Skip check (not enough data)
          2. real_lot_count >= 2: Allow MEDIUM confidence even if concentration < 50%
          3. (Future: staleness > 10s: LOW confidence)
        """
        # Only check if intent is WANT_BUY or WANT_SELL
        if intent not in ['WANT_BUY', 'WANT_SELL']:
            return None
        
        # If GRPAN concentration is not available, skip this check
        if grpan_concentration is None:
            return None
        
        # FALSE POSITIVE REDUCTION 1: ringlen < 8 -> Skip check
        if grpan_print_count < 8:
            return None  # Not enough data, don't block
        
        # FALSE POSITIVE REDUCTION 2: real_lot_count >= 2 -> Allow MEDIUM even if concentration < 50%
        if grpan_real_lot_count is not None and grpan_real_lot_count >= 2.0:
            # If we have at least 2 real lots, allow MEDIUM confidence even with lower concentration
            if grpan_concentration >= 30.0:  # Lower threshold for real_lot_count >= 2
                return None  # Allow through
        
        # Check if concentration is below threshold (50%)
        if grpan_concentration < 50.0:
            return {
                'reason': 'weak_real_lot_concentration',
                'intent': intent,
                'grpan_concentration_percent': grpan_concentration,
                'grpan_print_count': grpan_print_count,
                'grpan_real_lot_count': grpan_real_lot_count,
                'threshold': 50.0,
                'message': f'Weak real lot concentration: {grpan_concentration:.2f}% < 50% (intent: {intent}, prints: {grpan_print_count}, lots: {grpan_real_lot_count})'
            }
        
        return None
    
    def _check_manual_review(self, urgency: str) -> Optional[Dict[str, Any]]:
        """Check if order should be MANUAL_REVIEW"""
        cfg = self.config['gate']['manual_review']
        
        if urgency == cfg['urgency']:
            return {
                'reason': 'manual_review_urgency',
                'urgency': urgency,
                'message': f'Manual review required: urgency is {urgency}'
            }
        
        return None
    
    def set_global_block(self, blocked: bool):
        """Set global block flag (can be called via API)"""
        self.user_global_block = blocked
        logger.info(f"Global block set to: {blocked}")
    
    def get_global_block(self) -> bool:
        """Get global block flag status"""
        return self.user_global_block
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

