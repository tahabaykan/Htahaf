"""
Signal Interpreter
Interprets Janall metrics to generate explainable trading signals.

Input: merged record (static + live + janall_metrics + benchmark)
Output: signal and signal_reason (explainable)
"""

from typing import Dict, Any, Optional
import yaml
import os
from pathlib import Path

from app.core.logger import logger


class SignalInterpreter:
    """
    Interprets Janall metrics to generate trading signals.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Signal Interpreter with config file.
        
        Args:
            config_path: Path to signal_rules.yaml config file
        """
        if config_path is None:
            # Default path: app/config/signal_rules.yaml
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "app" / "config" / "signal_rules.yaml"
        
        self.config_path = config_path
        self.config = self._load_config()
        logger.info(f"Signal Interpreter initialized with config: {config_path}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load signal rules from YAML config file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    if config:
                        return config
            logger.warning(f"Signal rules config not found at {self.config_path}, using defaults")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading signal rules config: {e}", exc_info=True)
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default config if file not found"""
        return {
            'long_entry': {
                'strong_fbtot_min': 1.8,
                'medium_fbtot_min': 1.4,
                'weak_fbtot_min': 1.2
            },
            'long_exit': {
                'strong_fbtot_max': 1.1,
                'medium_fbtot_max': 1.3,
                'weak_fbtot_max': 1.5
            },
            'short_entry': {
                'strong_sfstot_max': 1.1,
                'medium_sfstot_max': 1.3,
                'weak_sfstot_max': 1.5
            },
            'short_cover': {
                'strong_sfstot_min': 1.7,
                'medium_sfstot_min': 1.5,
                'weak_sfstot_min': 1.3
            },
            'confidence': {
                'gort_weight': 0.35,
                'liquidity_weight': 0.25,
                'rank_weight': 0.40,
                'min_avg_adv': 5000
            }
        }
    
    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float"""
        if value is None or value == 'N/A' or value == '':
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def interpret_signal(
        self,
        merged_record: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Interpret Janall metrics to generate trading signal.
        
        Args:
            merged_record: Merged record containing static, live, and Janall metrics
            
        Returns:
            Dict with 'signal' and 'signal_reason'
        """
        try:
            # Extract inputs
            fbtot = self._safe_float(merged_record.get('Fbtot') or merged_record.get('fbtot'))
            sfstot = self._safe_float(merged_record.get('SFStot') or merged_record.get('sfstot'))
            gort = self._safe_float(merged_record.get('GORT') or merged_record.get('gort'))
            final_fb = self._safe_float(merged_record.get('FinalFB') or merged_record.get('final_fb'))
            final_sfs = self._safe_float(merged_record.get('FinalSFS') or merged_record.get('final_sfs'))
            avg_adv = self._safe_float(merged_record.get('AVG_ADV'))
            benchmark_chg = self._safe_float(merged_record.get('benchmark_chg'))
            
            # Extract config thresholds
            long_entry_rules = self.config.get('long_entry', {})
            long_exit_rules = self.config.get('long_exit', {})
            short_entry_rules = self.config.get('short_entry', {})
            short_cover_rules = self.config.get('short_cover', {})
            confidence_rules = self.config.get('confidence', {})
            gort_gating = self.config.get('gort_gating', {})
            
            # Initialize signal
            signal = {
                'long_entry': 'NONE',
                'long_exit': 'NONE',
                'short_entry': 'NONE',
                'short_cover': 'NONE',
                'confidence': 0.0
            }
            
            # Initialize reason
            signal_reason = {
                'inputs': {
                    'Fbtot': fbtot,
                    'SFStot': sfstot,
                    'GORT': gort,
                    'FinalFB': final_fb,
                    'FinalSFS': final_sfs,
                    'benchmark_chg': benchmark_chg,
                    'AVG_ADV': avg_adv
                },
                'rules': [],
                'computed': {}
            }
            
            # Check liquidity gate
            min_avg_adv = confidence_rules.get('min_avg_adv', 5000)
            liquidity_passed = avg_adv >= min_avg_adv
            
            # Long Entry Signal (based on Fbtot and FinalFB)
            if liquidity_passed and fbtot > 0 and final_fb is not None:
                strong_threshold = long_entry_rules.get('strong_fbtot_min', 1.8)
                medium_threshold = long_entry_rules.get('medium_fbtot_min', 1.4)
                weak_threshold = long_entry_rules.get('weak_fbtot_min', 1.2)
                
                strong_finalfb = long_entry_rules.get('strong_finalfb_min', 1.5)
                medium_finalfb = long_entry_rules.get('medium_finalfb_min', 1.0)
                weak_finalfb = long_entry_rules.get('weak_finalfb_min', 0.5)
                
                # Check GORT gate for long
                min_gort = gort_gating.get('min_gort_for_long', -0.5)
                gort_passed = gort is None or gort >= min_gort
                
                if gort_passed:
                    if fbtot >= strong_threshold and final_fb >= strong_finalfb:
                        signal['long_entry'] = 'STRONG'
                        signal_reason['rules'].append(f"Fbtot {fbtot:.2f} >= {strong_threshold} (STRONG) AND FinalFB {final_fb:.2f} >= {strong_finalfb}")
                    elif fbtot >= medium_threshold and final_fb >= medium_finalfb:
                        signal['long_entry'] = 'MEDIUM'
                        signal_reason['rules'].append(f"Fbtot {fbtot:.2f} >= {medium_threshold} (MEDIUM) AND FinalFB {final_fb:.2f} >= {medium_finalfb}")
                    elif fbtot >= weak_threshold and final_fb >= weak_finalfb:
                        signal['long_entry'] = 'WEAK'
                        signal_reason['rules'].append(f"Fbtot {fbtot:.2f} >= {weak_threshold} (WEAK) AND FinalFB {final_fb:.2f} >= {weak_finalfb}")
                else:
                    signal_reason['rules'].append(f"GORT {gort:.2f} < {min_gort} (long entry blocked)")
            
            # Long Exit Signal (based on Fbtot and FinalFB decreasing)
            if liquidity_passed and fbtot > 0 and final_fb is not None:
                strong_threshold = long_exit_rules.get('strong_fbtot_max', 1.1)
                medium_threshold = long_exit_rules.get('medium_fbtot_max', 1.3)
                weak_threshold = long_exit_rules.get('weak_fbtot_max', 1.5)
                
                strong_finalfb = long_exit_rules.get('strong_finalfb_max', 0.5)
                medium_finalfb = long_exit_rules.get('medium_finalfb_max', 0.8)
                weak_finalfb = long_exit_rules.get('weak_finalfb_max', 1.0)
                
                if fbtot <= strong_threshold and final_fb <= strong_finalfb:
                    signal['long_exit'] = 'STRONG'
                    signal_reason['rules'].append(f"Fbtot {fbtot:.2f} <= {strong_threshold} (STRONG EXIT) AND FinalFB {final_fb:.2f} <= {strong_finalfb}")
                elif fbtot <= medium_threshold and final_fb <= medium_finalfb:
                    signal['long_exit'] = 'MEDIUM'
                    signal_reason['rules'].append(f"Fbtot {fbtot:.2f} <= {medium_threshold} (MEDIUM EXIT) AND FinalFB {final_fb:.2f} <= {medium_finalfb}")
                elif fbtot <= weak_threshold and final_fb <= weak_finalfb:
                    signal['long_exit'] = 'WEAK'
                    signal_reason['rules'].append(f"Fbtot {fbtot:.2f} <= {weak_threshold} (WEAK EXIT) AND FinalFB {final_fb:.2f} <= {weak_finalfb}")
            
            # Short Entry Signal (based on SFStot and FinalSFS)
            if liquidity_passed and sfstot > 0 and final_sfs is not None:
                strong_threshold = short_entry_rules.get('strong_sfstot_max', 1.1)
                medium_threshold = short_entry_rules.get('medium_sfstot_max', 1.3)
                weak_threshold = short_entry_rules.get('weak_sfstot_max', 1.5)
                
                strong_finalsfs = short_entry_rules.get('strong_finalsfs_max', 0.5)
                medium_finalsfs = short_entry_rules.get('medium_finalsfs_max', 0.8)
                weak_finalsfs = short_entry_rules.get('weak_finalsfs_max', 1.0)
                
                # Check GORT gate for short
                max_gort = gort_gating.get('max_gort_for_short', 0.5)
                gort_passed = gort is None or gort <= max_gort
                
                if gort_passed:
                    if sfstot <= strong_threshold and final_sfs <= strong_finalsfs:
                        signal['short_entry'] = 'STRONG'
                        signal_reason['rules'].append(f"SFStot {sfstot:.2f} <= {strong_threshold} (STRONG) AND FinalSFS {final_sfs:.2f} <= {strong_finalsfs}")
                    elif sfstot <= medium_threshold and final_sfs <= medium_finalsfs:
                        signal['short_entry'] = 'MEDIUM'
                        signal_reason['rules'].append(f"SFStot {sfstot:.2f} <= {medium_threshold} (MEDIUM) AND FinalSFS {final_sfs:.2f} <= {medium_finalsfs}")
                    elif sfstot <= weak_threshold and final_sfs <= weak_finalsfs:
                        signal['short_entry'] = 'WEAK'
                        signal_reason['rules'].append(f"SFStot {sfstot:.2f} <= {weak_threshold} (WEAK) AND FinalSFS {final_sfs:.2f} <= {weak_finalsfs}")
                else:
                    signal_reason['rules'].append(f"GORT {gort:.2f} > {max_gort} (short entry blocked)")
            
            # Short Cover Signal (based on SFStot and FinalSFS increasing)
            if liquidity_passed and sfstot > 0 and final_sfs is not None:
                strong_threshold = short_cover_rules.get('strong_sfstot_min', 1.7)
                medium_threshold = short_cover_rules.get('medium_sfstot_min', 1.5)
                weak_threshold = short_cover_rules.get('weak_sfstot_min', 1.3)
                
                strong_finalsfs = short_cover_rules.get('strong_finalsfs_min', 1.5)
                medium_finalsfs = short_cover_rules.get('medium_finalsfs_min', 1.0)
                weak_finalsfs = short_cover_rules.get('weak_finalsfs_min', 0.5)
                
                if sfstot >= strong_threshold and final_sfs >= strong_finalsfs:
                    signal['short_cover'] = 'STRONG'
                    signal_reason['rules'].append(f"SFStot {sfstot:.2f} >= {strong_threshold} (STRONG COVER) AND FinalSFS {final_sfs:.2f} >= {strong_finalsfs}")
                elif sfstot >= medium_threshold and final_sfs >= medium_finalsfs:
                    signal['short_cover'] = 'MEDIUM'
                    signal_reason['rules'].append(f"SFStot {sfstot:.2f} >= {medium_threshold} (MEDIUM COVER) AND FinalSFS {final_sfs:.2f} >= {medium_finalsfs}")
                elif sfstot >= weak_threshold and final_sfs >= weak_finalsfs:
                    signal['short_cover'] = 'WEAK'
                    signal_reason['rules'].append(f"SFStot {sfstot:.2f} >= {weak_threshold} (WEAK COVER) AND FinalSFS {final_sfs:.2f} >= {weak_finalsfs}")
            
            # Compute Confidence Score
            confidence = self._compute_confidence(
                merged_record, fbtot, sfstot, gort, avg_adv, benchmark_chg, confidence_rules
            )
            signal['confidence'] = round(confidence, 2)
            
            signal_reason['computed'] = {
                'confidence_components': self._compute_confidence_components(
                    merged_record, fbtot, sfstot, gort, avg_adv, benchmark_chg, confidence_rules
                ),
                'liquidity_passed': liquidity_passed,
                'min_avg_adv_required': min_avg_adv
            }
            
            return {
                'signal': signal,
                'signal_reason': signal_reason
            }
            
        except Exception as e:
            logger.error(f"Error interpreting signal: {e}", exc_info=True)
            return {
                'signal': {
                    'long_entry': 'NONE',
                    'long_exit': 'NONE',
                    'short_entry': 'NONE',
                    'short_cover': 'NONE',
                    'confidence': 0.0
                },
                'signal_reason': {
                    'error': str(e),
                    'inputs': {},
                    'rules': [],
                    'computed': {}
                }
            }
    
    def _compute_confidence(
        self,
        merged_record: Dict[str, Any],
        fbtot: float,
        sfstot: float,
        gort: float,
        avg_adv: float,
        benchmark_chg: float,
        confidence_rules: Dict[str, Any]
    ) -> float:
        """Compute overall confidence score (0.0 to 1.0)"""
        try:
            gort_weight = confidence_rules.get('gort_weight', 0.35)
            liquidity_weight = confidence_rules.get('liquidity_weight', 0.25)
            rank_weight = confidence_rules.get('rank_weight', 0.40)
            
            min_avg_adv = confidence_rules.get('min_avg_adv', 5000)
            gort_positive_bonus = confidence_rules.get('gort_positive_bonus', 0.1)
            gort_negative_penalty = confidence_rules.get('gort_negative_penalty', -0.1)
            
            # Liquidity component (0.0 to 1.0)
            liquidity_score = min(1.0, avg_adv / min_avg_adv) if avg_adv > 0 else 0.0
            
            # Rank component (use normalized rank if available, otherwise fallback to value-based)
            rank_score = 0.0
            fbtot_rank_norm = merged_record.get('fbtot_rank_norm') if merged_record else None
            sfstot_rank_norm = merged_record.get('sfstot_rank_norm') if merged_record else None
            
            if fbtot_rank_norm is not None:
                # Use normalized rank (0..1, where 1.0 is best)
                rank_score = fbtot_rank_norm
            elif sfstot_rank_norm is not None:
                # For shorts, use normalized rank (0..1, where 1.0 is best)
                rank_score = sfstot_rank_norm
            elif fbtot > 0:
                # Fallback: Normalize Fbtot (assuming range 0-5, adjust as needed)
                rank_score = min(1.0, fbtot / 3.0)
            elif sfstot > 0:
                # Fallback: For shorts, lower SFStot is better, so invert
                rank_score = min(1.0, (3.0 - sfstot) / 3.0) if sfstot < 3.0 else 0.0
            
            # GORT component (normalized to 0-1, with bonus/penalty)
            gort_score = 0.5  # Neutral
            if gort is not None:
                # Normalize GORT (assuming range -2 to +2)
                gort_normalized = (gort + 2.0) / 4.0  # Maps -2..+2 to 0..1
                gort_score = max(0.0, min(1.0, gort_normalized))
                
                # Apply bonus/penalty
                if gort > 0:
                    gort_score = min(1.0, gort_score + gort_positive_bonus)
                elif gort < 0:
                    gort_score = max(0.0, gort_score + gort_negative_penalty)
            
            # Weighted average
            confidence = (
                gort_weight * gort_score +
                liquidity_weight * liquidity_score +
                rank_weight * rank_score
            )
            
            return max(0.0, min(1.0, confidence))
            
        except Exception as e:
            logger.warning(f"Error computing confidence: {e}")
            return 0.0
    
    def _compute_confidence_components(
        self,
        merged_record: Dict[str, Any],
        fbtot: float,
        sfstot: float,
        gort: float,
        avg_adv: float,
        benchmark_chg: float,
        confidence_rules: Dict[str, Any]
    ) -> Dict[str, float]:
        """Compute individual confidence components for explainability"""
        try:
            min_avg_adv = confidence_rules.get('min_avg_adv', 5000)
            
            liquidity_score = min(1.0, avg_adv / min_avg_adv) if avg_adv > 0 else 0.0
            
            # Rank component (use normalized rank if available, otherwise fallback to value-based)
            rank_score = 0.0
            if merged_record:
                fbtot_rank_norm = merged_record.get('fbtot_rank_norm')
                sfstot_rank_norm = merged_record.get('sfstot_rank_norm')
                
                if fbtot_rank_norm is not None:
                    rank_score = fbtot_rank_norm
                elif sfstot_rank_norm is not None:
                    rank_score = sfstot_rank_norm
                elif fbtot > 0:
                    rank_score = min(1.0, fbtot / 3.0)
                elif sfstot > 0:
                    rank_score = min(1.0, (3.0 - sfstot) / 3.0) if sfstot < 3.0 else 0.0
            else:
                if fbtot > 0:
                    rank_score = min(1.0, fbtot / 3.0)
                elif sfstot > 0:
                    rank_score = min(1.0, (3.0 - sfstot) / 3.0) if sfstot < 3.0 else 0.0
            
            gort_score = 0.5
            if gort is not None:
                gort_normalized = (gort + 2.0) / 4.0
                gort_score = max(0.0, min(1.0, gort_normalized))
            
            return {
                'trend': round(gort_score, 3),
                'rank': round(rank_score, 3),
                'liquidity': round(liquidity_score, 3)
            }
        except Exception as e:
            logger.warning(f"Error computing confidence components: {e}")
            return {
                'trend': 0.0,
                'rank': 0.0,
                'liquidity': 0.0
            }

