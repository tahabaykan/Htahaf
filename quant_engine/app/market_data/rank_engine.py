"""
Rank Engine
Normalizes Fbtot and SFStot ranks within groups to remove ambiguity.

Input: group_stats, symbol_metrics
Output: normalized ranks (0..1) for explainability and signal confidence
"""

from typing import Dict, Any, Optional, List
import yaml
import os
from pathlib import Path

from app.core.logger import logger


class RankEngine:
    """
    Computes and normalizes ranks for Fbtot and SFStot within groups.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Rank Engine with config file.
        
        Args:
            config_path: Path to rank_rules.yaml config file
        """
        if config_path is None:
            # Default path: app/config/rank_rules.yaml
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "app" / "config" / "rank_rules.yaml"
        
        self.config_path = config_path
        self.config = self._load_config()
        logger.info(f"Rank Engine initialized with config: {config_path}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load rank rules from YAML config file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config:
                        return config
            logger.warning(f"Rank rules config not found at {self.config_path}, using defaults")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading rank rules config: {e}", exc_info=True)
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default config if file not found"""
        return {
            'rank_direction': {
                'fbtot': 'descending',
                'sfstot': 'ascending'
            },
            'normalization_method': 'minmax'
        }
    
    def compute_ranks(
        self,
        symbol: str,
        symbol_metrics: Dict[str, Any],
        group_stats: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compute raw and normalized ranks for a symbol within its group.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            symbol_metrics: Symbol metrics dict (must contain group_key, fbtot, sfstot)
            group_stats: Group statistics dict {group_key: stats}
            
        Returns:
            Dict with:
                - fbtot_rank_raw: Raw rank (1-based)
                - fbtot_rank_norm: Normalized rank (0..1)
                - sfstot_rank_raw: Raw rank (1-based)
                - sfstot_rank_norm: Normalized rank (0..1)
        """
        try:
            group_key = symbol_metrics.get('group_key')
            if not group_key or group_key not in group_stats:
                return {
                    'fbtot_rank_raw': None,
                    'fbtot_rank_norm': None,
                    'sfstot_rank_raw': None,
                    'sfstot_rank_norm': None
                }
            
            stats = group_stats[group_key]
            fbtot = symbol_metrics.get('fbtot')
            sfstot = symbol_metrics.get('sfstot')
            
            result = {
                'fbtot_rank_raw': None,
                'fbtot_rank_norm': None,
                'sfstot_rank_raw': None,
                'sfstot_rank_norm': None
            }
            
            # Compute Fbtot rank
            if fbtot is not None and 'fbtot_values' in stats:
                fbtot_values = stats['fbtot_values']
                if fbtot_values and len(fbtot_values) > 0:
                    rank_direction = self.config.get('rank_direction', {}).get('fbtot', 'descending')
                    result['fbtot_rank_raw'] = self._compute_raw_rank(
                        fbtot, fbtot_values, rank_direction
                    )
                    result['fbtot_rank_norm'] = self._normalize_rank(
                        result['fbtot_rank_raw'], len(fbtot_values), rank_direction
                    )
            
            # Compute SFStot rank
            if sfstot is not None and 'sfstot_values' in stats:
                sfstot_values = stats['sfstot_values']
                if sfstot_values and len(sfstot_values) > 0:
                    rank_direction = self.config.get('rank_direction', {}).get('sfstot', 'ascending')
                    result['sfstot_rank_raw'] = self._compute_raw_rank(
                        sfstot, sfstot_values, rank_direction
                    )
                    result['sfstot_rank_norm'] = self._normalize_rank(
                        result['sfstot_rank_raw'], len(sfstot_values), rank_direction
                    )
            
            return result
            
        except Exception as e:
            logger.error(f"Error computing ranks for {symbol}: {e}", exc_info=True)
            return {
                'fbtot_rank_raw': None,
                'fbtot_rank_norm': None,
                'sfstot_rank_raw': None,
                'sfstot_rank_norm': None
            }
    
    def _compute_raw_rank(
        self,
        value: float,
        values: List[float],
        direction: str
    ) -> int:
        """
        Compute raw rank (1-based) for a value within a list.
        
        Args:
            value: Value to rank
            values: List of all values in the group
            direction: 'ascending' (lower is better) or 'descending' (higher is better)
            
        Returns:
            Raw rank (1-based, where 1 is best)
        """
        try:
            if direction == 'descending':
                # Higher is better: sort descending, rank 1 = highest value
                sorted_values = sorted(values, reverse=True)
            else:  # ascending
                # Lower is better: sort ascending, rank 1 = lowest value
                sorted_values = sorted(values)
            
            # Find position (1-based)
            try:
                rank = sorted_values.index(value) + 1
            except ValueError:
                # Value not found, assign worst rank
                rank = len(sorted_values) + 1
            
            return rank
            
        except Exception as e:
            logger.warning(f"Error computing raw rank: {e}")
            return len(values) + 1  # Worst rank
    
    def _normalize_rank(
        self,
        raw_rank: int,
        total_count: int,
        direction: str
    ) -> float:
        """
        Normalize rank to 0..1 range using minmax method.
        
        Args:
            raw_rank: Raw rank (1-based)
            total_count: Total number of items in group
            direction: 'ascending' or 'descending'
            
        Returns:
            Normalized rank (0..1, where 1.0 is best)
        """
        try:
            if raw_rank is None or total_count <= 0:
                return 0.0
            
            normalization_method = self.config.get('normalization_method', 'minmax')
            
            if normalization_method == 'minmax':
                # MinMax normalization: best rank (1) -> 1.0, worst rank (N) -> 0.0
                # Formula: norm = 1 - (rank - 1) / (total_count - 1)
                if total_count == 1:
                    return 1.0  # Only one item, it's the best
                
                normalized = 1.0 - (raw_rank - 1) / (total_count - 1)
                return max(0.0, min(1.0, normalized))  # Clamp to [0, 1]
            
            else:
                # Default: simple inverse
                return max(0.0, min(1.0, 1.0 - (raw_rank - 1) / total_count))
                
        except Exception as e:
            logger.warning(f"Error normalizing rank: {e}")
            return 0.0
    
    def compute_batch_ranks(
        self,
        all_symbols_metrics: List[Dict[str, Any]],
        group_stats: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compute ranks for all symbols in batch.
        
        Args:
            all_symbols_metrics: List of symbol metrics dicts
            group_stats: Group statistics dict {group_key: stats}
            
        Returns:
            Dict mapping symbol -> rank results
        """
        result = {}
        
        for symbol_metrics in all_symbols_metrics:
            symbol = symbol_metrics.get('symbol')
            if not symbol:
                continue
            
            ranks = self.compute_ranks(symbol, symbol_metrics, group_stats)
            result[symbol] = ranks
        
        return result








