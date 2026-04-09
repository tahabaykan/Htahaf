"""
Limit Rules Service

Manages all configurable limit rules for RUNALL:
- BEFDAY (daily decrease) rules
- Daily INCREASE rules
- Dust sweep threshold
- Price collision threshold
- Other configurable limits

Supports CSV-based configuration with save/load functionality.
"""

import os
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from app.core.logger import logger


class LimitRulesService:
    """
    Manages configurable limit rules.
    
    Loads rules from CSV files and provides access to:
    - BEFDAY (decrease) limit tiers
    - Daily INCREASE limit tiers
    - Dust sweep threshold
    - Price collision threshold
    - Min lot size
    """
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.befday_rules = self.load_befday_rules()
        self.increase_rules = self.load_increase_rules()
        self.other_limits = self.load_other_limits()
        
        logger.info(
            f"[LIMIT_RULES] Initialized from {config_dir}: "
            f"BEFDAY rules: {len(self.befday_rules)}, "
            f"INCREASE rules: {len(self.increase_rules)}"
        )
    
    def load_befday_rules(self) -> Dict[float, Tuple[Optional[float], Optional[float]]]:
        """
        Load BEFDAY (daily decrease) limit rules from CSV.
        
        Returns:
            Dict mapping portfolio_pct_threshold to (maxalw_mult, befday_mult)
        """
        csv_path = self.config_dir / "befday_rules.csv"
        
        try:
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                rules = {}
                for _, row in df.iterrows():
                    threshold = float(row['portfolio_pct_threshold'])
                    maxalw_mult = None if pd.isna(row['maxalw_multiplier']) else float(row['maxalw_multiplier'])
                    befday_mult = None if pd.isna(row['befday_multiplier']) else float(row['befday_multiplier'])
                    rules[threshold] = (maxalw_mult, befday_mult)
                
                logger.info(f"[LIMIT_RULES] Loaded {len(rules)} BEFDAY rules from {csv_path}")
                return rules
            else:
                logger.warning(f"[LIMIT_RULES] BEFDAY rules not found at {csv_path}, using defaults")
                return self._get_default_befday_rules()
        
        except Exception as e:
            logger.error(f"[LIMIT_RULES] Error loading BEFDAY rules: {e}", exc_info=True)
            return self._get_default_befday_rules()
    
    def load_increase_rules(self) -> Dict[float, Tuple[float, float]]:
        """
        Load daily INCREASE limit rules from CSV.
        
        Returns:
            Dict mapping portfolio_pct_threshold to (maxalw_mult, portfolio_pct_limit)
        """
        csv_path = self.config_dir / "increase_rules.csv"
        
        try:
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                rules = {}
                for _, row in df.iterrows():
                    threshold = float(row['portfolio_pct_threshold'])
                    maxalw_mult = float(row['maxalw_multiplier'])
                    portfolio_pct = float(row['portfolio_pct_limit'])
                    rules[threshold] = (maxalw_mult, portfolio_pct)
                
                logger.info(f"[LIMIT_RULES] Loaded {len(rules)} INCREASE rules from {csv_path}")
                return rules
            else:
                logger.warning(f"[LIMIT_RULES] INCREASE rules not found at {csv_path}, using defaults")
                return self._get_default_increase_rules()
        
        except Exception as e:
            logger.error(f"[LIMIT_RULES] Error loading INCREASE rules: {e}", exc_info=True)
            return self._get_default_increase_rules()
    
    def load_other_limits(self) -> Dict[str, float]:
        """
        Load other configurable limits from CSV.
        
        Returns:
            Dict with keys: dust_threshold, collision_threshold, min_lot
        """
        csv_path = self.config_dir / "other_limits.csv"
        
        try:
            if csv_path.exists():
                df = pd.read_csv(csv_path)
                limits = {}
                for _, row in df.iterrows():
                    limits[row['setting']] = float(row['value'])
                
                logger.info(f"[LIMIT_RULES] Loaded other limits from {csv_path}")
                return limits
            else:
                logger.warning(f"[LIMIT_RULES] Other limits not found at {csv_path}, using defaults")
                return self._get_default_other_limits()
        
        except Exception as e:
            logger.error(f"[LIMIT_RULES] Error loading other limits: {e}", exc_info=True)
            return self._get_default_other_limits()
    
    def save_befday_rules(self, rules: Dict[float, Tuple[Optional[float], Optional[float]]]):
        """
        Save BEFDAY rules to CSV.
        
        Args:
            rules: Dict mapping threshold to (maxalw_mult, befday_mult)
        """
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            csv_path = self.config_dir / "befday_rules.csv"
            
            rows = []
            for threshold, (maxalw_mult, befday_mult) in sorted(rules.items()):
                rows.append({
                    'portfolio_pct_threshold': threshold,
                    'maxalw_multiplier': maxalw_mult if maxalw_mult is not None else '',
                    'befday_multiplier': befday_mult if befday_mult is not None else ''
                })
            
            df = pd.DataFrame(rows)
            df.to_csv(csv_path, index=False)
            
            self.befday_rules = rules
            logger.info(f"[LIMIT_RULES] Saved {len(rules)} BEFDAY rules to {csv_path}")
        
        except Exception as e:
            logger.error(f"[LIMIT_RULES] Error saving BEFDAY rules: {e}", exc_info=True)
    
    def save_increase_rules(self, rules: Dict[float, Tuple[float, float]]):
        """
        Save INCREASE rules to CSV.
        
        Args:
            rules: Dict mapping threshold to (maxalw_mult, portfolio_pct_limit)
        """
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            csv_path = self.config_dir / "increase_rules.csv"
            
            rows = []
            for threshold, (maxalw_mult, portfolio_pct) in sorted(rules.items()):
                rows.append({
                    'portfolio_pct_threshold': threshold,
                    'maxalw_multiplier': maxalw_mult,
                    'portfolio_pct_limit': portfolio_pct
                })
            
            df = pd.DataFrame(rows)
            df.to_csv(csv_path, index=False)
            
            self.increase_rules = rules
            logger.info(f"[LIMIT_RULES] Saved {len(rules)} INCREASE rules to {csv_path}")
        
        except Exception as e:
            logger.error(f"[LIMIT_RULES] Error saving INCREASE rules: {e}", exc_info=True)
    
    def save_other_limits(self, limits: Dict[str, float]):
        """
        Save other limits to CSV.
        
        Args:
            limits: Dict with keys: dust_threshold, collision_threshold, min_lot
        """
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            csv_path = self.config_dir / "other_limits.csv"
            
            rows = []
            for setting, value in limits.items():
                rows.append({'setting': setting, 'value': value})
            
            df = pd.DataFrame(rows)
            df.to_csv(csv_path, index=False)
            
            self.other_limits = limits
            logger.info(f"[LIMIT_RULES] Saved other limits to {csv_path}")
        
        except Exception as e:
            logger.error(f"[LIMIT_RULES] Error saving other limits: {e}", exc_info=True)
    
    def save_all_rules(self, data: Dict[str, Any]):
        """
        Save all rules from a combined data structure.
        
        Args:
            data: Dict with keys: befday_rules, increase_rules, dust_threshold, collision_threshold, min_lot
        """
        if 'befday_rules' in data:
            self.save_befday_rules(data['befday_rules'])
        
        if 'increase_rules' in data:
            self.save_increase_rules(data['increase_rules'])
        
        other_limits = {}
        if 'dust_threshold' in data:
            other_limits['dust_threshold'] = data['dust_threshold']
        if 'collision_threshold' in data:
            other_limits['collision_threshold'] = data['collision_threshold']
        if 'min_lot' in data:
            other_limits['min_lot'] = data['min_lot']
        
        if other_limits:
            self.save_other_limits(other_limits)
    
    def _get_default_befday_rules(self) -> Dict[float, Tuple[Optional[float], Optional[float]]]:
        """Get default BEFDAY rules (matching current daily_limit_service.py)"""
        return {
            3.0: (None, None),        # Unlimited
            5.0: (0.75, 0.75),
            7.0: (0.60, 0.60),
            10.0: (0.50, 0.50),
            100.0: (0.40, 0.40)
        }
    
    def _get_default_increase_rules(self) -> Dict[float, Tuple[float, float]]:
        """Get default INCREASE rules (matching current daily_limit_service.py)"""
        return {
            1.0: (0.50, 5.0),
            3.0: (0.40, 4.0),
            5.0: (0.30, 3.0),
            7.0: (0.20, 2.0),
            10.0: (0.10, 1.5),
            100.0: (0.05, 1.0)
        }
    
    def _get_default_other_limits(self) -> Dict[str, float]:
        """Get default other limits"""
        return {
            'dust_threshold': 200.0,
            'collision_threshold': 0.04,
            'min_lot': 400.0
        }
    
    def get_befday_limit_spec(self, portfolio_pct: float) -> Tuple[Optional[float], Optional[float]]:
        """
        Get BEFDAY limit specification for a given portfolio percentage.
        
        Args:
            portfolio_pct: Portfolio percentage (0-100)
            
        Returns:
            (maxalw_mult, befday_mult) tuple
        """
        sorted_keys = sorted(self.befday_rules.keys())
        for thresh in sorted_keys:
            if portfolio_pct < thresh:
                return self.befday_rules[thresh]
        return self.befday_rules[100.0]
    
    def get_increase_limit_spec(self, portfolio_pct: float) -> Tuple[float, float]:
        """
        Get INCREASE limit specification for a given portfolio percentage.
        
        Args:
            portfolio_pct: Portfolio percentage (0-100)
            
        Returns:
            (maxalw_mult, portfolio_pct_limit) tuple
        """
        sorted_keys = sorted(self.increase_rules.keys())
        for thresh in sorted_keys:
            if portfolio_pct < thresh:
                return self.increase_rules[thresh]
        return self.increase_rules[100.0]
    
    def get_dust_threshold(self) -> float:
        """Get dust sweep threshold (lots)"""
        return self.other_limits.get('dust_threshold', 200.0)
    
    def get_collision_threshold(self) -> float:
        """Get price collision threshold ($)"""
        return self.other_limits.get('collision_threshold', 0.04)
    
    def get_min_lot(self) -> float:
        """Get minimum lot size"""
        return self.other_limits.get('min_lot', 400.0)
    
    def get_all_rules_for_api(self) -> Dict[str, Any]:
        """
        Get all rules in API-friendly format.
        
        Returns:
            Dict with all rules for frontend consumption
        """
        # Convert BEFDAY rules to list format
        befday_list = []
        for threshold, (maxalw_mult, befday_mult) in sorted(self.befday_rules.items()):
            befday_list.append({
                'threshold': threshold,
                'maxalw_mult': maxalw_mult,
                'befday_mult': befday_mult
            })
        
        # Convert INCREASE rules to list format
        increase_list = []
        for threshold, (maxalw_mult, portfolio_pct) in sorted(self.increase_rules.items()):
            increase_list.append({
                'threshold': threshold,
                'maxalw_mult': maxalw_mult,
                'portfolio_pct': portfolio_pct
            })
        
        return {
            'befday_rules': befday_list,
            'increase_rules': increase_list,
            'dust_threshold': self.get_dust_threshold(),
            'collision_threshold': self.get_collision_threshold(),
            'min_lot': self.get_min_lot()
        }


# Global instance
_limit_rules_service: Optional[LimitRulesService] = None


def get_limit_rules_service() -> LimitRulesService:
    """Get or create global LimitRulesService instance"""
    global _limit_rules_service
    if _limit_rules_service is None:
        _limit_rules_service = LimitRulesService()
    return _limit_rules_service


def initialize_limit_rules_service(config_dir: str = "config"):
    """Initialize global LimitRulesService instance"""
    global _limit_rules_service
    _limit_rules_service = LimitRulesService(config_dir=config_dir)
    logger.info("[LIMIT_RULES] Service initialized")
