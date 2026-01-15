"""
PSFALGO Rules Store
Manages PSFALGO decision rules configuration with thread-safe access.
Supports runtime updates, validation, and preset save/load.
"""

import yaml
import json
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from app.core.logger import logger


class RulesStore:
    """
    Thread-safe store for PSFALGO rules configuration.
    
    Features:
    - Load default rules from YAML
    - Runtime updates (thread-safe)
    - Validation
    - Preset save/load
    - Version tracking
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize RulesStore.
        
        Args:
            config_path: Path to psfalgo_rules.yaml (default: app/config/psfalgo_rules.yaml)
        """
        if config_path is None:
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "app" / "config" / "psfalgo_rules.yaml"
        
        self.config_path = Path(config_path)
        self.rules_lock = threading.RLock()
        self.rules: Dict[str, Any] = {}
        self.version: str = "1.0.0"
        self.last_updated: Optional[datetime] = None
        
        # Load default rules
        self._load_rules()
        
        logger.info(f"RulesStore initialized with {len(self.rules)} rule categories")
    
    @classmethod
    def get_instance(cls, config_path: Optional[str] = None) -> 'RulesStore':
        """Get singleton instance of RulesStore"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config_path)
        return cls._instance
    
    def _load_rules(self) -> None:
        """Load rules from YAML config file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    rules = yaml.safe_load(f)
                    if rules:
                        with self.rules_lock:
                            self.rules = rules
                            self.last_updated = datetime.now()
                        logger.info(f"Rules loaded from {self.config_path}")
                        return
            
            logger.warning(f"Rules config not found at {self.config_path}, using defaults")
            with self.rules_lock:
                self.rules = self._get_default_rules()
                self.last_updated = datetime.now()
        except Exception as e:
            logger.error(f"Error loading rules: {e}", exc_info=True)
            with self.rules_lock:
                self.rules = self._get_default_rules()
                self.last_updated = datetime.now()
    
    def _get_default_rules(self) -> Dict[str, Any]:
        """Return default rules (Janall-based defaults)"""
        return {
            'version': '1.0.0',
            'general': {
                'cycle': {
                    'interval_seconds': 240,  # 4 minutes (Janall: ~3-4 min)
                    'order_wait_seconds': 120,  # 2 minutes (Janall: after(120000))
                    'auto_cancel_after_seconds': 120,  # Cancel orders after 2 min
                },
                'intent': {
                    'ttl_seconds': 90,  # Intent TTL (90 seconds)
                    'max_intents_per_cycle': 50,
                    'auto_expire_enabled': True,
                },
            },
            'exposure': {
                'defensive_threshold_percent': 95.5,  # Janall: defensive_threshold = max_lot * 0.955
                'offensive_threshold_percent': 92.7,  # Janall: offensive_threshold = max_lot * 0.927
                'transition_mode': 'REDUCEMORE',  # GEÇIŞ mode uses REDUCEMORE
            },
            'karbotu': {
                'step_1': {
                    'name': 'GORT Filter',
                    'description': 'Filter positions with Gort > -1 and Ask Sell Pahalılık > -0.05',
                    'enabled': True,
                    'filters': {
                        'gort_gt': -1.0,
                        'ask_sell_pahalilik_gt': -0.05,
                    },
                    'action': 'FILTER',
                },
                'step_2': {
                    'name': 'Fbtot < 1.10',
                    'description': 'Sell 50% lot for positions with Fbtot < 1.10 and Ask Sell Pahalılık > -0.10',
                    'enabled': True,
                    'filters': {
                        'fbtot_lt': 1.10,
                        'ask_sell_pahalilik_gt': -0.10,
                        'qty_ge': 100,
                    },
                    'action': 'SELL',
                    'lot_percentage': 50.0,
                    'order_type': 'ASK_SELL',
                },
                'settings': {
                    'min_lot_size': 100,
                    'cooldown_minutes': 5.0,
                },
            },
            'reducemore': {
                'eligibility': {
                    'exposure_ratio_threshold': 0.8,  # Run if exposure_ratio >= 80%
                    'pot_total_multiplier': 0.9,  # Run if pot_total > 90% of pot_max
                },
                'step_1': {
                    'name': 'GORT Filter',
                    'description': 'Filter positions with Gort > -1 and Ask Sell Pahalılık > -0.05',
                    'enabled': True,
                    'filters': {
                        'gort_gt': -1.0,
                        'ask_sell_pahalilik_gt': -0.05,
                    },
                    'action': 'FILTER',
                },
                'step_2': {
                    'name': 'Fbtot < 1.10 (Aggressive)',
                    'description': 'Sell 75% lot for positions with Fbtot < 1.10 and Ask Sell Pahalılık > -0.10',
                    'enabled': True,
                    'filters': {
                        'fbtot_lt': 1.10,
                        'ask_sell_pahalilik_gt': -0.10,
                        'qty_ge': 100,
                    },
                    'action': 'SELL',
                    'lot_percentage': 75.0,  # More aggressive than KARBOTU (50%)
                    'order_type': 'ASK_SELL',
                },
                'settings': {
                    'min_lot_size': 100,
                    'cooldown_minutes': 5.0,
                    'spread_tolerance_percent': 0.20,
                },
            },
            'addnewpos': {
                'eligibility': {
                    'exposure_ratio_threshold': 0.8,  # Run if exposure_ratio < 80%
                    'exposure_mode': 'OFANSIF',  # Only run in OFANSIF mode
                },
                'filters': {
                    'bid_buy_ucuzluk_gt': 0.06,
                    'fbtot_gt': 1.10,
                    'spread_lt': 0.05,
                    'avg_adv_gt': 1000.0,
                },
                'rules': {
                    # Portfolio percentage thresholds (Janall: addnewpos_rules)
                    'thresholds': [
                        {'max_portfolio_percent': 1.0, 'maxalw_multiplier': 0.50, 'portfolio_percent': 5.0},
                        {'max_portfolio_percent': 3.0, 'maxalw_multiplier': 0.40, 'portfolio_percent': 4.0},
                        {'max_portfolio_percent': 5.0, 'maxalw_multiplier': 0.30, 'portfolio_percent': 3.0},
                        {'max_portfolio_percent': 7.0, 'maxalw_multiplier': 0.20, 'portfolio_percent': 2.0},
                        {'max_portfolio_percent': 10.0, 'maxalw_multiplier': 0.10, 'portfolio_percent': 1.5},
                        {'max_portfolio_percent': 100.0, 'maxalw_multiplier': 0.05, 'portfolio_percent': 1.0},
                    ],
                    'exposure_usage_percent': 60.0,  # Use 60% of remaining exposure
                },
                'settings': {
                    'max_lot_per_symbol': 200,
                    'default_lot': 200,
                    'min_lot_size': 100,
                    'cooldown_minutes': 5.0,
                    'min_avg_adv_divisor': 10,  # RULE_AVG_ADV_DIVISOR
                },
            },
            'guardrails': {
                'maxalw': {
                    'company_limit_enabled': True,
                    'max_company_exposure_percent': 100.0,  # MAXALW per company
                },
                'daily_limits': {
                    'max_daily_lot_change': 10000,  # Max daily lot change
                    'max_daily_lot_change_per_symbol': 2000,  # Max daily lot change per symbol
                },
                'order_limits': {
                    'max_open_orders': 100,
                    'max_open_orders_per_symbol': 5,
                },
                'duplicate_prevention': {
                    'duplicate_intent_window_seconds': 60,  # Prevent duplicate intents within 60 seconds
                    'same_symbol_cooldown_seconds': 300,  # 5 minutes cooldown per symbol
                },
            },
        }
    
    def get_rules(self) -> Dict[str, Any]:
        """Get current rules (thread-safe)"""
        with self.rules_lock:
            return self.rules.copy()
    
    def get_rule_category(self, category: str) -> Optional[Dict[str, Any]]:
        """Get specific rule category"""
        with self.rules_lock:
            return self.rules.get(category, {}).copy()
    
    def update_rules(self, updates: Dict[str, Any], validate: bool = True) -> Dict[str, Any]:
        """
        Update rules (thread-safe).
        
        Args:
            updates: Partial rules dict to merge
            validate: Whether to validate before applying
        
        Returns:
            Result dict with success/error
        """
        try:
            if validate:
                validation_result = self.validate_rules(updates)
                if not validation_result.get('valid', False):
                    return {
                        'success': False,
                        'error': 'Validation failed',
                        'validation_errors': validation_result.get('errors', [])
                    }
            
            with self.rules_lock:
                # Deep merge updates
                self._deep_merge(self.rules, updates)
                self.last_updated = datetime.now()
                self.version = updates.get('version', self.version)
            
            # Save to file
            self._save_rules()
            
            logger.info(f"Rules updated successfully")
            return {
                'success': True,
                'message': 'Rules updated successfully',
                'last_updated': self.last_updated.isoformat()
            }
        except Exception as e:
            logger.error(f"Error updating rules: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _deep_merge(self, base: Dict[str, Any], updates: Dict[str, Any]) -> None:
        """Deep merge updates into base dict"""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def validate_rules(self, rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validate rules structure and values.
        
        Args:
            rules: Rules to validate (if None, validates current rules)
        
        Returns:
            Validation result with valid flag and errors list
        """
        errors = []
        
        if rules is None:
            rules = self.rules
        
        # Validate required categories
        required_categories = ['general', 'exposure', 'karbotu', 'reducemore', 'addnewpos', 'guardrails']
        for category in required_categories:
            if category not in rules:
                errors.append(f"Missing required category: {category}")
        
        # Validate general.cycle
        if 'general' in rules and 'cycle' in rules['general']:
            cycle = rules['general']['cycle']
            if cycle.get('interval_seconds', 0) <= 0:
                errors.append("general.cycle.interval_seconds must be > 0")
            if cycle.get('order_wait_seconds', 0) < 0:
                errors.append("general.cycle.order_wait_seconds must be >= 0")
        
        # Validate exposure thresholds
        if 'exposure' in rules:
            exp = rules['exposure']
            if exp.get('defensive_threshold_percent', 0) <= exp.get('offensive_threshold_percent', 0):
                errors.append("exposure.defensive_threshold_percent must be > offensive_threshold_percent")
        
        # Validate lot percentages (0-100)
        for category in ['karbotu', 'reducemore']:
            if category in rules:
                for step_key, step in rules[category].items():
                    if isinstance(step, dict) and 'lot_percentage' in step:
                        lot_pct = step['lot_percentage']
                        if not (0 < lot_pct <= 100):
                            errors.append(f"{category}.{step_key}.lot_percentage must be between 0 and 100")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def _save_rules(self) -> None:
        """Save rules to YAML file"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.rules, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info(f"Rules saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving rules: {e}", exc_info=True)
            raise
    
    def reset_to_defaults(self) -> Dict[str, Any]:
        """Reset rules to default values"""
        try:
            with self.rules_lock:
                self.rules = self._get_default_rules()
                self.last_updated = datetime.now()
            
            self._save_rules()
            
            logger.info("Rules reset to defaults")
            return {
                'success': True,
                'message': 'Rules reset to defaults',
                'last_updated': self.last_updated.isoformat()
            }
        except Exception as e:
            logger.error(f"Error resetting rules: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def save_preset(self, preset_name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """
        Save current rules as a preset.
        
        Args:
            preset_name: Name of preset
            description: Optional description
        
        Returns:
            Result dict
        """
        try:
            presets_dir = self.config_path.parent / 'presets'
            presets_dir.mkdir(exist_ok=True)
            
            preset_path = presets_dir / f"{preset_name}.yaml"
            
            preset_data = {
                'name': preset_name,
                'description': description or f"Preset saved at {datetime.now().isoformat()}",
                'saved_at': datetime.now().isoformat(),
                'version': self.version,
                'rules': self.rules
            }
            
            with open(preset_path, 'w', encoding='utf-8') as f:
                yaml.dump(preset_data, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"Preset saved: {preset_name}")
            return {
                'success': True,
                'message': f'Preset "{preset_name}" saved',
                'preset_path': str(preset_path)
            }
        except Exception as e:
            logger.error(f"Error saving preset: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def load_preset(self, preset_name: str) -> Dict[str, Any]:
        """
        Load rules from a preset.
        
        Args:
            preset_name: Name of preset to load
        
        Returns:
            Result dict
        """
        try:
            presets_dir = self.config_path.parent / 'presets'
            preset_path = presets_dir / f"{preset_name}.yaml"
            
            if not preset_path.exists():
                return {
                    'success': False,
                    'error': f'Preset "{preset_name}" not found'
                }
            
            with open(preset_path, 'r', encoding='utf-8') as f:
                preset_data = yaml.safe_load(f)
            
            if 'rules' not in preset_data:
                return {
                    'success': False,
                    'error': 'Invalid preset format: missing rules'
                }
            
            # Validate before loading
            validation_result = self.validate_rules(preset_data['rules'])
            if not validation_result.get('valid', False):
                return {
                    'success': False,
                    'error': 'Preset validation failed',
                    'validation_errors': validation_result.get('errors', [])
                }
            
            # Load rules
            with self.rules_lock:
                self.rules = preset_data['rules']
                self.version = preset_data.get('version', '1.0.0')
                self.last_updated = datetime.now()
            
            self._save_rules()
            
            logger.info(f"Preset loaded: {preset_name}")
            return {
                'success': True,
                'message': f'Preset "{preset_name}" loaded',
                'preset_info': {
                    'name': preset_data.get('name'),
                    'description': preset_data.get('description'),
                    'saved_at': preset_data.get('saved_at')
                }
            }
        except Exception as e:
            logger.error(f"Error loading preset: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }
    
    def list_presets(self) -> List[Dict[str, Any]]:
        """List all available presets"""
        try:
            presets_dir = self.config_path.parent / 'presets'
            if not presets_dir.exists():
                return []
            
            presets = []
            for preset_file in presets_dir.glob('*.yaml'):
                try:
                    with open(preset_file, 'r', encoding='utf-8') as f:
                        preset_data = yaml.safe_load(f)
                    
                    presets.append({
                        'name': preset_data.get('name', preset_file.stem),
                        'description': preset_data.get('description', ''),
                        'saved_at': preset_data.get('saved_at', ''),
                        'version': preset_data.get('version', '1.0.0')
                    })
                except Exception:
                    continue
            
            return presets
        except Exception as e:
            logger.error(f"Error listing presets: {e}", exc_info=True)
            return []


# Singleton accessor
_rules_store_instance: Optional[RulesStore] = None
_rules_store_lock = threading.Lock()


def get_rules_store(config_path: Optional[str] = None) -> RulesStore:
    """Get singleton RulesStore instance"""
    global _rules_store_instance
    if _rules_store_instance is None:
        with _rules_store_lock:
            if _rules_store_instance is None:
                _rules_store_instance = RulesStore.get_instance(config_path)
    return _rules_store_instance


def initialize_rules_store(config_path: Optional[str] = None) -> RulesStore:
    """Initialize RulesStore (called at startup)"""
    return get_rules_store(config_path)





