
"""
Quant Engine - Selection Engine (Janall DNA Integration)
Handles TumCSV selection logic, Group DNA, and Issuer Constraints.
"""
from typing import List, Dict, Any, Optional
import math
import logging

class SelectionEngine:
    """
    Implements Janall's selection logic:
    1. TumCSV (Top X% by specific score)
    2. Issuer Limits (Divisor 1.6)
    3. Group DNA (Multiplier, etc.)
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.selection_config = config.get('selection', {})
        self.tumcsv_config = self.selection_config.get('tumcsv_modes', {})
        self.issuer_config = self.selection_config.get('issuer_limit', {})
        
        self.logger = logging.getLogger("SelectionEngine")

    def _get_mode_params(self, mode_name: str) -> Dict[str, Any]:
        """Get selection percent and min count for a given mode (v10, v15, v20)."""
        mode_data = self.tumcsv_config.get(mode_name.lower())
        if not mode_data:
            # Fallback based on name parsing or default
            return {'percent': 0.10, 'min_count': 2}
        return mode_data

    def apply_tumcsv_selection(self, 
                               candidates: List[Dict[str, Any]], 
                               mode: str, 
                               direction: str, 
                               score_key: str) -> List[Dict[str, Any]]:
        """
        Select Top X% candidates based on score.
        
        Args:
            candidates: List of stock data dicts. Must contain `score_key` and `CMON`.
            mode: "v10", "v15", "v20" (defines percent selection).
            direction: "LONG" (descending score) or "SHORT" (ascending score).
            score_key: The sorting key (e.g. 'Final_BB_skor', 'Final_SAS_skor').
            
        Returns:
            Filtered list of selected candidates.
        """
        if not candidates:
            return []

        # 1. Get Params
        params = self._get_mode_params(mode)
        percent = params.get('percent', 0.10)
        min_count = params.get('min_count', 2)
        
        total_count = len(candidates)
        target_count = max(min_count, int(round(total_count * percent)))
        
        # 2. Sort Candidates
        # For Long: Higher Score is Better (Reverse=True)
        # For Short: Lower Score is Better (Reverse=False) - Janall Logic for SAS/SFS
        reverse_sort = (direction == "LONG")
        
        # Filter out invalid scores first? Janall usually keeps them but sorts them last?
        # Assuming candidates have valid scores computed.
        # Use a safe float conversion for sorting key
        def sort_key(x):
            try:
                val = x.get(score_key)
                if val is None or val == 'N/A' or math.isnan(float(val)):
                    return -999999.0 if reverse_sort else 999999.0
                return float(val)
            except:
                return -999999.0 if reverse_sort else 999999.0

        sorted_candidates = sorted(candidates, key=sort_key, reverse=reverse_sort)
        
        # 3. Apply Issuer Limits (CMON)
        # PROMPT Rule 7: "issuer_divisor = 1.6"
        # "Default: issuer_divisor = 1.6"
        # "Kural: Aynı issuer'dan seçilen hisseler ... sınırlandırılır"
        
        final_selection = []
        company_counts = {}
        
        divisor = float(self.issuer_config.get('divisor', 1.6))
        if divisor <= 0: divisor = 1.6
        
        # Limit per company based on Total Group Count / Divisor
        # e.g. 10 / 1.6 = 6.25 -> 6
        limit_per_company = max(1, int(round(total_count / divisor)))
        
        # Or explicitly disabled?
        if not self.issuer_config.get('enabled', True):
            limit_per_company = 999999

        for cand in sorted_candidates:
            if len(final_selection) >= target_count:
                break
                
            spouse = cand.get('CMON', 'UNKNOWN')
            current_issuer_count = company_counts.get(spouse, 0)
            
            if current_issuer_count < limit_per_company:
                final_selection.append(cand)
                company_counts[spouse] = current_issuer_count + 1
            else:
                pass 
                # Skipped due to issuer limit (selection phase)
        
        # 4. Return Selection
        # Wait - need to respect "Minimum 2" rule even if issuer limits block?
        # If we blocked stocks and fell below min_count, should we force add?
        # Janall code basically tries its best.
        
        self.logger.info(f"TumCSV Selection ({mode}): {len(final_selection)}/{total_count} selected (Target {target_count})")
        return final_selection

    def get_group_dna(self, group_name: str) -> Dict[str, Any]:
        """
        Retrieve Group DNA (Multiplier, Aggression, etc.)
        """
        group_dna_config = self.config.get('group_dna', {})
        specific = group_dna_config.get(group_name, {})
        default = group_dna_config.get('default', {'multiplier': 1.0, 'aggression': 'NORMAL'})
        
        # Merge specific over default
        dna = default.copy()
        if specific:
            dna.update(specific)
            
        return dna
