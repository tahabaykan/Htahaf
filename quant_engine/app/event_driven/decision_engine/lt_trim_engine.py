"""
LT Trim Engine - Executive Phase 11 Refactor
============================================

Role: "Executive Execution Engine"
-   Consumes SIGNALs from Karbotu (Veto/Bias).
-   Consumes MULTIPLIERs from Reducemore (Sizing Intensity).
-   Consumes RUNTIME CONTROLS (Force Trim, Enable/Disable).
-   Executes the "Ladder" and "Spread Gating" logic.

Input:
    Signals, Multipliers, Rules, Controls, Market Data
Output:
    Intents (Standardized)
"""

import math
import time
import sys
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.decision_models import Intent # Phase 11 Intent Model

class LTTrimEngine:
    """
    LT Trim Engine (Phase 11 Executive)
    """
    
    # Spread Tables (Same as before)
    # Spread Tables (Stricter - Phase 12)
    # Format: (SpreadLimit, ScoreLimit)
    # Logic: If Spread >= SpreadLimit, we accept Score >= ScoreLimit.
    # Removed deep negative tolerances to prevent "Low Score" trims.
    LONG_SPREAD_THRESHOLDS = [
        (0.06, 0.08),   # Normal Spread -> Need 0.08
        (0.10, 0.05),   # Wide Spread -> Need 0.05
        (0.15, 0.02),   # Very Wide -> Need 0.02
        (0.25, 0.00),   # Huge Spread -> Accept 0.00 (Neutral)
        (0.45, -0.02),  # Massive Spread -> Tolerate slight negative
        (10.0, -0.08)   # Extreme -> Tolerate -0.08 max (User Request)
    ]
    SHORT_SPREAD_THRESHOLDS = [
        (0.06, -0.08),
        (0.10, -0.05),
        (0.15, -0.02),
        (0.25, 0.00),
        (0.45, 0.02),
        (10.0, 0.08)
    ]
    LADDER_TARGETS = [0.10, 0.20, 0.40]

    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        # Track daily stats
        self.symbol_stats: Dict[str, Dict[str, Any]] = {}
        self.max_daily_trim_pct = 80.0
        self._last_stats_date: Optional[str] = None  # Track which day stats belong to

    async def run(
        self,
        request, # DecisionRequest
        karbotu_signals: Dict[str, Any],
        reducemore_multipliers: Dict[str, Any],
        rules: Dict[str, Any],
        controls: Any, # RuntimeControls object
        account_id: str = "UNKNOWN"
    ) -> List[Intent]:
        """
        Main Execution Cycle.
        """
        import sys
        # print("I AM HERE - LT TRIM ENGINE RUNNING (START)", flush=True)
        intents = []
        
        # 1. Global Enable Check
        if not controls.lt_trim_enabled:
            return []

        for position in request.positions:
            symbol = position.symbol
            qty = position.qty
            if abs(qty) < 1: continue # Ignore dust
            
            # Taxonomy Check (New)
            # 1. Strategy Check: Only LT
            if getattr(position, 'strategy_type', 'LT') != 'LT':
                sys.stderr.write(f"[DEBUG LT_TRIM] Skipped {symbol}: Not LT ({getattr(position, 'strategy_type', 'N/A')})\n")
                continue
            
            # 2. Origin Check: Only Overnight (OV)
            # "gun ici 0 dan acilmis pozlar icin farkli bir mekanizma calisacak bu LT trim calismayacak"
            if getattr(position, 'origin_type', 'INT') != 'OV':
                sys.stderr.write(f"[DEBUG LT_TRIM] Skipped {symbol}: Intraday Position\n")
                continue
            
            # Direction Checks
            is_long = qty > 0
            if is_long and not controls.lt_trim_long_enabled: continue
            if not is_long and not controls.lt_trim_short_enabled: continue

            # 2. Veto Logic (Karbotu) - REMOVED BY USER REQUEST
            # "bu lt trim mekanizmasi ozgurdur"
            # signal = karbotu_signals.get(symbol)
            # ... (Logic removed)

            # Retrieve Metrics
            metric = request.metrics.get(symbol)
            if not metric:
                sys.stderr.write(f"[DEBUG LT_TRIM] Skipped {symbol}: No Metrics\n")
                continue
            
            l1 = request.l1_data.get(symbol) if isinstance(request.l1_data, dict) else request.l1_data     
            if not l1: l1 = metric # Fallback to using metric as l1 source if needed

            # 3. Intensity Scaling
            intensity = controls.lt_trim_intensity 
            rm_mult = reducemore_multipliers.get(symbol)
            if rm_mult and controls.allow_reducemore_scale:
                intensity *= rm_mult.value

            # sys.stderr.write(f"[DEBUG LT_TRIM] Eval {symbol}: Qty={qty}, Score={metric.ask_sell_pahalilik if is_long else metric.bid_buy_ucuzluk}, Intensity={intensity}\n")

            symbol_intents = self._evaluate_trim(
                position, metric, l1, intensity, rules
            )
            # Only log if intent generated
            if symbol_intents:
                sys.stderr.write(f"[DEBUG LT_TRIM] Generated {len(symbol_intents)} intents for {symbol}\n")
            intents.extend(symbol_intents)

        return intents

    def _evaluate_trim(self, position, metric, l1, intensity, rules):
        """Evaluate single symbol trim logic using 4-Stage Befday Model."""
        intents = []
        symbol = position.symbol
        qty = position.qty
        is_long = qty > 0
        abs_qty = abs(qty)
        
        # Befday Qty from Position (Enriched in Snapshot)
        befday_qty = getattr(position, 'befday_qty', 0.0)
        abs_befday = abs(befday_qty)
        if abs_befday < 1: 
             sys.stderr.write(f"[DEBUG LT_TRIM] Warn: {symbol} OV but befday 0? Using current.\n")
             abs_befday = abs_qty
             
        # Score & Spread
        from app.core.data_fabric import get_data_fabric
        data_fabric = get_data_fabric()
        
        score = None
        if data_fabric:
            fast_snapshot = data_fabric.get_fast_snapshot(symbol)
            if fast_snapshot and fast_snapshot.get('_has_derived'):
                if is_long:
                    score = fast_snapshot.get('ask_sell_pahalilik') or fast_snapshot.get('Ask_sell_pahalilik_skoru')
                else:
                    score = fast_snapshot.get('bid_buy_ucuzluk') or fast_snapshot.get('Bid_buy_ucuzluk_skoru')
        
        if score is None:
            score = metric.ask_sell_pahalilik if is_long else metric.bid_buy_ucuzluk
        
        if score is None: return []

        # --- SAFETY FLOOR (User Request) ---
        # "Score -0.08 centten yukarı olmak zorunda"
        SAFE_FLOOR = -0.08
        if is_long and score < SAFE_FLOOR:
            # sys.stderr.write(f"[DEBUG LT_TRIM] {symbol} Rejected: Score {score} < Safety Floor {SAFE_FLOOR}\n")
            return []
        
        # Symmetrical for Shorts? (Assuming mirror logic, but sticking to request)
        if not is_long and score > abs(SAFE_FLOOR): # For Short, "Ucuzluk" > 0.08? Or symmetric?
             # Short logic usually mirror: score <= 0.08
             # But let's check thresholds. Short threshold allows +0.08 max.
             # So if score > 0.08, reject.
             pass


        # L1 Data
        def _safe_get(obj, key, default=0):
            if obj is None: return default
            if hasattr(obj, 'get'): return obj.get(key, default)
            return getattr(obj, key, default)

        bid = metric.bid if metric.bid is not None else _safe_get(l1, 'bid', 0)
        ask = metric.ask if metric.ask is not None else _safe_get(l1, 'ask', 0)
        bid, ask = (bid or 0), (ask or 0)
        if bid <= 0 or ask <= 0: return []
        spread = ask - bid
        
        # --- LOGIC BRANCHING ---
        # Branch A: Small Position (< 400)
        # Branch B: Standard Position (>= 400)
        
        needed_sell_qty = 0
        flags_triggered = 0
        triggered_reasons = []
        
        if abs_befday < 400:
            # Special Small Pos Logic
            # Stage 1 (Spread) -> Skipped
            # Stage 2 (Score 0.10) -> Sell 200
            # Stage 3 (Score 0.20) -> Sell Rest (Close)
            
            # Check Stage 2
            limit2 = 0.10
            stage2_met = (is_long and score >= limit2) or (not is_long and score <= -limit2)
            
            # Check Stage 3
            limit3 = 0.20
            stage3_met = (is_long and score >= limit3) or (not is_long and score <= -limit3)
            
            target_sell_total = 0
            
            if stage3_met:
                target_sell_total = abs_befday # Sell All
                triggered_reasons.append(f"SMALL_STAGE3_CLOSE({limit3})")
            elif stage2_met:
                target_sell_total = 200
                triggered_reasons.append(f"SMALL_STAGE2_200({limit2})")
            
            # Cap at actual max (abs_befday)
            target_sell_total = min(target_sell_total, abs_befday)
            
            # Calculate needed
            # Target Qty = Abs Befday - Target Sell
            target_qty_abs = abs_befday - target_sell_total
            needed_sell_qty = abs_qty - target_qty_abs
            
            # For small logic, min 200 doesn't strictly apply if we are closing (sell rest).
            # If Stage 2 (200) triggered, we sell 200.
            
        else:
            # Standard 4-Stage Logic
            
            # Stage 1: Spread Gating ("Loose Trim")
            thresholds = self.LONG_SPREAD_THRESHOLDS if is_long else self.SHORT_SPREAD_THRESHOLDS
            stage1_met = False
            for (spr_limit, score_limit) in thresholds:
                spread_ok = (spread >= spr_limit)
                score_ok = (score >= score_limit) if is_long else (score <= score_limit)
                if spread_ok and score_ok:
                    stage1_met = True
                    triggered_reasons.append(f"STAGE1_SPREAD(S={spread:.2f})")
                    break
            if stage1_met: flags_triggered += 1
            
            # Stage 2: Ladder 1 (Score 0.10)
            limit2 = 0.10
            if (is_long and score >= limit2) or (not is_long and score <= -limit2):
                flags_triggered += 1
                triggered_reasons.append(f"STAGE2_SCORE({limit2})")

            # Stage 3: Ladder 2 (Score 0.20)
            limit3 = 0.20
            if (is_long and score >= limit3) or (not is_long and score <= -limit3):
                flags_triggered += 1
                triggered_reasons.append(f"STAGE3_SCORE({limit3})")

            # Stage 4: Ladder 3 (Score 0.40)
            limit4 = 0.40
            if (is_long and score >= limit4) or (not is_long and score <= -limit4):
                flags_triggered += 1
                triggered_reasons.append(f"STAGE4_SCORE({limit4})")
                
            if flags_triggered == 0: return []
            
            # Calculate Target
            step_size_pct = 20.0 * intensity
            total_sell_pct = flags_triggered * step_size_pct
            total_sell_pct = min(total_sell_pct, self.max_daily_trim_pct)
            
            target_retention_pct = 100.0 - total_sell_pct
            target_qty_abs = abs_befday * (target_retention_pct / 100.0)
            
            needed_sell_qty = abs_qty - target_qty_abs

        # Common Execution Logic
        sys.stderr.write(f"[DEBUG LT_TRIM] {symbol} NeedsSell={needed_sell_qty} (Reasons={','.join(triggered_reasons)})\n")

        final_trim_qty = 0
        
        if needed_sell_qty > 0:
            # Check rounding/min rule (Standard Rule)
            if needed_sell_qty < 200:
                # Force min 200
                final_trim_qty = 200
            else:
                final_trim_qty = int(round(needed_sell_qty / 100.0) * 100)
                if final_trim_qty < 200: final_trim_qty = 200
            
            # CRITICAL: Do not flip position
            if final_trim_qty > abs_qty:
                final_trim_qty = abs_qty 
            
            if final_trim_qty > 0:
                price = self._calculate_hidden_price(bid, ask, is_long)
                reason_code = f"LT_STAGE_{flags_triggered if abs_befday >= 400 else 'SMALL'}"
                intents.append(self._create_intent(symbol, final_trim_qty, price, reason_code, is_long))
        
        return intents

    def _create_intent(self, symbol, qty, price, reason, is_long):
        return Intent(
            symbol=symbol,
            action='SELL' if is_long else 'BUY', # Actually Cover? standardized to BUY/SELL for IBKR
            qty=qty, # Intent qty usually absolute? Or signed? Provider expects signed? 
            # Intent model said qty: int. Usually absolute.
            intent_category='LT_TRIM_MICRO',
            priority=10,
            reason=reason,
            metadata={'price': price, 'hidden': True}
        )

    def _calculate_hidden_price(self, bid, ask, is_long):
        spread = ask - bid
        if is_long: return round(ask - (spread * 0.15), 2)
        return round(bid + (spread * 0.15), 2)

    def _get_stats(self, symbol, qty):
        # Legacy stats for reporting, less critical for logic now driven by Befday
        today = datetime.now().strftime('%Y-%m-%d')
        if self._last_stats_date != today:
            self.symbol_stats.clear()
            self._last_stats_date = today
        if symbol not in self.symbol_stats:
            self.symbol_stats[symbol] = {'trimmed_today_pct': 0.0, 'max_observed_qty': abs(qty)}
        return self.symbol_stats[symbol]

    def _update_stats(self, symbol, qty, max_qty):
        pass # Stats now implicitly handled by Befday comparison

    def reset_stats(self):
        self.symbol_stats.clear()
        self._last_stats_date = None
        
# Global Instance
_lt_trim_engine = LTTrimEngine()
def get_lt_trim_engine(): return _lt_trim_engine

