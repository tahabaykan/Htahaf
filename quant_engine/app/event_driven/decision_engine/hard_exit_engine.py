"""
Hard Exit Engine

Deterministic preference engine for ranking and selecting positions to reduce
during HARD_DERISK and CLOSE regimes.

Logic:
    - MM Bucket First (unless 1.8x Cost Exception)
    - Deterministic Ranking (Profit > Loss > Exec > Truth > Spread > Liquidity)
    - Low Confidence -> No churn sizing limits, but full exits allowed.
"""

import logging
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import math
from app.core.logger import logger

class HardExitEngine:
    """
    Engine to strictly rank positions for reduction in time-critical regimes.
    """
    
    def __init__(self, risk_config: Dict[str, Any] = None):
        self.risk_config = risk_config or {}
        # Default cost multiplier for MM vs LT override
        self.mm_cost_penalty_threshold = 1.8 
        # Min lot size for churn orders (LiquidityGuard default)
        self.min_lot_size = 200
        # Clip Sizing
        self.clip_size_default = 2000
        self.clip_size_close = 4000


    def plan_hard_derisk(
        self,
        reduction_notional: float,
        positions: List[Dict[str, Any]],
        l1_data: Dict[str, Any],
        truth_data: Dict[str, Any],
        regime: str,
        mode: str,
        confidence_scores: Dict[str, float],
        rules: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Main entry point for Hard Derisk planning.
        Matches required signature: plan_hard_derisk(reduction_notional, positions, l1, truth, regime, mode, confidence, rules)
        """
        # Merge data sources for internal usage
        market_data_snapshot = self._merge_market_data(l1_data, truth_data, confidence_scores)
        
        # Call internal logic
        return self.plan_reduction(
            positions=positions,
            market_data_snapshot=market_data_snapshot,
            target_reduction_notional=reduction_notional,
            time_regime=regime
        )

    def _merge_market_data(self, l1: Dict[str, Any], truth: Dict[str, Any], conf: Dict[str, float]) -> Dict[str, Any]:
        """Helper to merge L1, Truth, and Confidence into a single snapshot"""
        snapshot = {}
        all_symbols = set(l1.keys()) | set(truth.keys())
        
        for sym in all_symbols:
            l1_info = l1.get(sym, {})
            truth_info = truth.get(sym, {})
            
            # Truth Price Fallback Chain: Dominant(GRPAN1) > Last > Mid
            # GRPAN data usually in truth_info['grpan']... let's assume truth_info has keys 'dominant_price', 'last_price'
            dominant = truth_info.get('dominant_price') or truth_info.get('truth_price')
            last = truth_info.get('last_price') or l1_info.get('lastPrice')
            bid = l1_info.get('bid', 0)
            ask = l1_info.get('ask', 0)
            mid = (bid + ask) / 2 if (bid and ask) else 0
            
            truth_price = dominant if dominant else (last if last else mid)
            
            snapshot[sym] = {
                'bid': bid,
                'ask': ask,
                'adv': truth_info.get('adv') or l1_info.get('adv', 1000000),
                'truth_price': truth_price,
                'confidence': conf.get(sym, 100)
            }
        return snapshot

    def plan_reduction(
        self,
        positions: List[Dict[str, Any]],
        market_data_snapshot: Dict[str, Any],
        target_reduction_notional: float,
        time_regime: str = 'LATE'
    ) -> List[Dict[str, Any]]:
        """
        Generate a list of Intent dictionaries to reduce exposure.
        """
        intents = []
        remaining_reduction = target_reduction_notional
        
        # 1. Separate Buckets
        mm_positions = []
        lt_positions = []
        
        for pos in positions:
            # Skip negligible dust
            if abs(pos.get('size', 0)) * pos.get('mark_price', 0) < 100:
                continue
                
            bucket = pos.get('bucket', 'MM')
            if bucket == 'MM':
                mm_positions.append(pos)
            else:
                lt_positions.append(pos)
                
        # 2. Rank Candidates Deterministically
        ranked_mm = self.rank_positions(mm_positions, market_data_snapshot)
        ranked_lt = self.rank_positions(lt_positions, market_data_snapshot)
        
        mm_idx = 0
        lt_idx = 0
        
        while remaining_reduction > 100: # Threshold for "done"
            candidate_mm = ranked_mm[mm_idx] if mm_idx < len(ranked_mm) else None
            candidate_lt = ranked_lt[lt_idx] if lt_idx < len(ranked_lt) else None
            
            if not candidate_mm and not candidate_lt:
                break
            
            selected_pos = None
            use_source = 'MM'
            
            if candidate_mm:
                if candidate_lt:
                    # Cost Check: MM > 1.8 * LT ?
                    slip_mm = self._calculate_unit_slippage(candidate_mm, market_data_snapshot)
                    slip_lt = self._calculate_unit_slippage(candidate_lt, market_data_snapshot)
                    
                    if slip_mm > (self.mm_cost_penalty_threshold * slip_lt):
                        selected_pos = candidate_lt
                        use_source = 'LT'
                    else:
                        selected_pos = candidate_mm
                        use_source = 'MM'
                else:
                    selected_pos = candidate_mm
                    use_source = 'MM'
            else:
                selected_pos = candidate_lt
                use_source = 'LT'
                
                
            # Sizing
            price = selected_pos.get('mark_price', 1.0)
            if price <= 0: price = 1.0
            
            # Clip size based on Regime
            # CLOSE = Aggressive = Larger Clips (4000 lots)
            # LATE = Standard = 2000 lots
            target_clip_lots = self.clip_size_close if time_regime == 'CLOSE' else self.clip_size_default
            clip_value_usd = target_clip_lots * price 
            
            chunk_notional = min(remaining_reduction, clip_value_usd)
            
            qty_needed = int(chunk_notional / price)
            current_size = abs(selected_pos.get('size', 0))
            qty_to_reduce = min(qty_needed, current_size)
            
            # LiquidityGuard Min Lot
            # NOTE: Confidence is IGNORED for HARD_DERISK and CLOSE. 
            # We attempt full exit regardless of confidence scores.
            qty_to_reduce = max(qty_to_reduce, self.min_lot_size)
            qty_to_reduce = min(qty_to_reduce, current_size)
            
            if qty_to_reduce <= 0:
                # Should not happen if dust filter works, but safety break
                if use_source == 'MM': mm_idx += 1
                else: lt_idx += 1
                continue

            # Create Intent
            intent = self._create_reduction_intent(selected_pos, qty_to_reduce, time_regime)
            
            reduced_notional = qty_to_reduce * price
            remaining_reduction_after = remaining_reduction - reduced_notional
            
            # Decision Trace (PM-Grade)
            trace = self._create_decision_trace(
                ranked_mm, ranked_lt, selected_pos, use_source, 
                candidate_mm, candidate_lt, reduction_value=remaining_reduction_after
            )
            intent['_debug_trace'] = trace
            
            # CLOSE Regime: market_limit flag?
            if time_regime == 'CLOSE':
                intent['execution_style'] = 'MARKETABLE_LIMIT'
            
            intents.append(intent)
            
            remaining_reduction = remaining_reduction_after
            
            # Move to next candidate (Simulate full consumption of candidate for this pass)
            if use_source == 'MM':
                mm_idx += 1
            else:
                lt_idx += 1
                
        return intents


    def rank_positions(self, positions: List[Dict[str, Any]], market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Sort positions using deterministic lexicographic keys.
        """
        def sort_key(pos):
            symbol = pos['symbol']
            md = market_data.get(symbol, {})
            
            # Data
            is_long = pos['size'] > 0
            avg_cost = pos.get('avg_cost', 0)
            bid, ask = md.get('bid', 0), md.get('ask', 0)
            mark_price = pos.get('mark_price', md.get('truth_price', (bid+ask)/2))
            
            # 1. Profitability (Profit > Smallest Loss)
            # Exec Price: Bid for Long, Ask for Short (Conservative view)
            exec_price = bid if is_long else ask
            if exec_price <= 0: exec_price = mark_price # Fallback
            
            pnl_per_share = (exec_price - avg_cost) if is_long else (avg_cost - exec_price)
            total_pnl = pnl_per_share * abs(pos['size'])
            
            # Key 1: IsLoss (0=Profit, 1=Loss)
            is_loss = 1 if total_pnl < 0 else 0
            
            # Key 2: Profit Amount (Descending) -> -Profit
            profit_val = total_pnl if total_pnl > 0 else 0
            
            # Key 3: Loss Amount (Ascending - Smallest First) -> Loss
            loss_val = abs(total_pnl) if total_pnl < 0 else 0
            
            # 2. Exec Proximity (Closer is Better -> Ascending Dist)
            dist_to_exec = abs(exec_price - avg_cost)
            
            # 3. Truth Context (Closer is Better -> Ascending Dist)
            truth_price = md.get('truth_price', exec_price)
            dist_to_truth = abs(exec_price - truth_price)
            
            # 4. Spread (Narrow is Better -> Ascending Spread)
            spread = abs(ask - bid)
            
            # 5. Liquidity (Illiquid is Better -> Ascending ADV)
            adv = md.get('adv', 10000000)
            
            return (
                is_loss,          # 0 before 1
                -profit_val,      # Large profit before small
                loss_val,         # Small loss before large
                dist_to_exec,     # Small dist before large
                dist_to_truth,    # Small dist before large
                spread,           # Narrow before wide
                adv               # Low ADV before High
            )
            
        return sorted(positions, key=sort_key)

    def _create_decision_trace(
        self, 
        ranked_mm: List[Dict], 
        ranked_lt: List[Dict], 
        chosen: Dict, 
        chosen_bucket: str,
        cand_mm: Optional[Dict], 
        cand_lt: Optional[Dict],
        reduction_value: float
    ) -> Dict[str, Any]:
        """Generate a PM-grade decision trace for audit."""
        trace = {
            'timestamp': str(datetime.now()),
            'chosen_symbol': chosen['symbol'],
            'chosen_bucket': chosen_bucket,
            'reduction_remaining': reduction_value,
            'switch_triggered': False,
            'switch_reason': None,
            'ranked_mm_top5': [p['symbol'] for p in ranked_mm[:5]],
            'ranked_lt_top5': [p['symbol'] for p in ranked_lt[:5]],
            'skipped_candidates': []
        }
        
        # Explain Switch
        if cand_mm and cand_lt:
            if chosen_bucket == 'LT' and cand_mm['symbol'] != cand_lt['symbol']:
                 # We chose LT over MM? Maybe same symbol? 
                 # If cand_mm exists but we chose LT, it implies switch (or MM empty, but cand_mm checked)
                 trace['switch_triggered'] = True
                 trace['switch_reason'] = f"MM Cost > 1.8x LT Cost (Skipped {cand_mm['symbol']})"
                 trace['skipped_candidates'].append({
                     'symbol': cand_mm['symbol'], 
                     'reason': 'Cost Override (High Slippage)'
                 })
        
        return trace

    def _calculate_unit_slippage(self, pos: Dict[str, Any], market_data: Dict[str, Any]) -> float:
        """Calculate slippage per share cost."""
        symbol = pos['symbol']
        md = market_data.get(symbol, {})
        
        is_long = pos['size'] > 0
        best_bid = md.get('bid', 0)
        best_ask = md.get('ask', 0)
        # Conservative Exec Price
        exec_price = best_bid if is_long else best_ask
        if exec_price <= 0: exec_price = md.get('truth_price', 0)
        
        truth_price = md.get('truth_price', exec_price)
        
        return abs(exec_price - truth_price)

    def _create_reduction_intent(self, selected_pos: Dict[str, Any], qty: float, regime: str) -> Dict[str, Any]:
        """Create standard intent dictionary."""
        bucket = selected_pos.get('bucket', 'MM')
        side = 'LONG' if selected_pos['size'] > 0 else 'SHORT'
        
        intent_type = f"{bucket}_{side}_DECREASE"
        
        return {
            'type': intent_type,
            'symbol': selected_pos['symbol'],
            'qty': qty,
            'regime': regime,
            'reason': 'HARD_DERISK_PREFERENCE'
        }
