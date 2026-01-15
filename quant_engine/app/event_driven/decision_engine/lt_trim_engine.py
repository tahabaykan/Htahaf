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
    LONG_SPREAD_THRESHOLDS = [
        (0.06, 0.08), (0.10, 0.05), (0.15, 0.02),
        (0.25, -0.02), (0.45, -0.05), (999.0, -0.08)
    ]
    SHORT_SPREAD_THRESHOLDS = [
        (0.06, -0.08), (0.10, -0.05), (0.15, -0.02),
        (0.25, 0.02), (0.45, 0.05), (999.0, 0.08)
    ]
    LADDER_TARGETS = [0.10, 0.20, 0.40]

    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        # Track daily stats
        self.symbol_stats: Dict[str, Dict[str, Any]] = {}
        self.max_daily_trim_pct = 80.0

    async def run(
        self,
        request, # DecisionRequest
        karbotu_signals: Dict[str, Any],
        reducemore_multipliers: Dict[str, Any],
        rules: Dict[str, Any],
        controls: Any # RuntimeControls object
    ) -> List[Intent]:
        """
        Main Execution Cycle.
        """
        import sys
        print("I AM HERE - LT TRIM ENGINE RUNNING (START)", flush=True)
        intents = []
        
        # 1. Global Enable Check
        if not controls.lt_trim_enabled:
            return []

        for position in request.positions:
            symbol = position.symbol
            qty = position.qty
            if qty == 0: continue
            
            # Direction Checks
            is_long = qty > 0
            if is_long and not controls.lt_trim_long_enabled: continue
            if not is_long and not controls.lt_trim_short_enabled: continue

            # 2. Veto Logic (Karbotu)
            signal = karbotu_signals.get(symbol)
            is_eligible = True
            veto_reason = ""
            
            if controls.allow_karbotu_veto and not controls.force_trim:
                if signal and not signal.eligibility:
                    is_eligible = False
                    veto_reason = f"Karbotu Veto: {signal.reason_codes}"
            
            if not is_eligible:
                sys.stderr.write(f"[DEBUG LT_TRIM] Skipped {symbol}: {veto_reason}\n")
                continue

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

            sys.stderr.write(f"[DEBUG LT_TRIM] Eval {symbol}: Qty={qty}, Score={metric.ask_sell_pahalilik if is_long else metric.bid_buy_ucuzluk}, Intensity={intensity}\n")

            symbol_intents = self._evaluate_trim(
                symbol, qty, metric, l1, intensity, rules
            )
            sys.stderr.write(f"[DEBUG LT_TRIM] Generated {len(symbol_intents)} intents for {symbol}\n")
            intents.extend(symbol_intents)

        return intents

    def _evaluate_trim(self, symbol, qty, metric, l1, intensity, rules):
        """Evaluate single symbol trim logic."""
        # ... (Core Logic - Ladder/Spread) ...
        # Simplified port of previous logic, applying 'intensity' to sizing.
        
        intents = []
        is_long = qty > 0
        abs_qty = abs(qty)
        
        # Stats Check
        stats = self._get_stats(symbol, qty)
        if stats['trimmed_today_pct'] >= self.max_daily_trim_pct:
            sys.stderr.write(f"[DEBUG LT_TRIM] Bailing: Max Trim Reached ({stats['trimmed_today_pct']})\n")
            return []
        
        remaining_cap_pct = self.max_daily_trim_pct - stats['trimmed_today_pct']
        sys.stderr.write(f"[DEBUG LT_TRIM] Remaining Cap: {remaining_cap_pct}\n")
        
        # Score & Spread
        score = metric.ask_sell_pahalilik if is_long else metric.bid_buy_ucuzluk
        # L1 Fallback if needed
        bid = metric.bid or l1.get('bid', 0)
        ask = metric.ask or l1.get('ask', 0)
        if bid <= 0 or ask <= 0:
            sys.stderr.write(f"[DEBUG LT_TRIM] Bailing: Bid/Ask invalid ({bid}/{ask})\n")
            return []
        spread = ask - bid
        sys.stderr.write(f"[DEBUG LT_TRIM] Spread={spread:.4f}, Score={score:.4f}\n")
        
        # 1. Aggressive Illiquid Trim
        # If huge spread and good score -> Big Trim
        # Apply intensity to the "60%" base
        if spread >= 0.25 and abs(score) >= 0.25: # Simplified cond
             sys.stderr.write(f"[DEBUG LT_TRIM] Aggressive Trim Triggered\n")
             base_pct = 60.0 * intensity
             target_pct = min(base_pct, remaining_cap_pct)
             trim_qty = self._calculate_trim_qty(qty, target_pct)
             if trim_qty > 0:
                 price = self._calculate_hidden_price(bid, ask, is_long)
                 intents.append(self._create_intent(symbol, trim_qty, price, "LT_AGGRESSIVE", is_long))
                 self._update_stats(symbol, trim_qty, stats['max_observed_qty'])
                 return intents # Aggressive takes precedence

        # 2. Ladder Logic
        # Iterate targets. If target met -> Trim 20% * Intensity
        current_remaining = abs_qty
        accumulated_pct = 0.0
        
        # Start looking from lowest target
        # Problem: Triggering multiple ladder steps in one go? 
        # Usually we check highest triggered level? Or stack them?
        # Original logic: "Each step = 20%". Iterate targets.
        
        for target in self.LADDER_TARGETS:
             # Check logic (is_long: score >= target)
             triggered = (score >= target) if is_long else (score <= -target)
             
             if triggered:
                 sys.stderr.write(f"[DEBUG LT_TRIM] Ladder {target} Triggered\n")
                 sys.stderr.flush()
                 # Calculate Step Size
                 step_base = 20.0 * intensity
                 
                 # Cap check
                 if accumulated_pct + step_base > remaining_cap_pct:
                     sys.stderr.write(f"[DEBUG LT_TRIM] Cap Reached: Acc={accumulated_pct}, Step={step_base}, Rem={remaining_cap_pct}\n")
                     sys.stderr.flush()
                     break
                 
                 step_qty = self._calculate_trim_qty(current_remaining, step_base)
                 sys.stderr.write(f"[DEBUG LT_TRIM] Step Qty={step_qty} (CurRem={current_remaining})\n")
                 sys.stderr.flush()
                 if step_qty > 0:
                     price = self._calculate_hidden_price(bid, ask, is_long) # Fallback for now check L1 ladder later
                     
                     intents.append(self._create_intent(symbol, step_qty, price, f"LT_LADDER_{target}", is_long))
                     current_remaining -= step_qty
                     accumulated_pct += step_base
                     # REMOVED STATE MUTATION: self._update_stats(symbol, step_qty, stats['max_observed_qty'])
        
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

    def _calculate_trim_qty(self, current_qty, pct):
        """Standard 100-lot rounding logic."""
        abs_qty = abs(current_qty)
        if abs_qty < 200: return abs_qty # Clean sweep small pos
        raw = abs_qty * (pct / 100.0)
        # Min 200, Round 100
        val = max(raw, 200)
        return int(round(val / 100.0) * 100)

    def _calculate_hidden_price(self, bid, ask, is_long):
        spread = ask - bid
        if is_long: return round(ask - (spread * 0.15), 2)
        return round(bid + (spread * 0.15), 2)

    def _get_stats(self, symbol, qty):
        if symbol not in self.symbol_stats:
            self.symbol_stats[symbol] = {'trimmed_today_pct': 0.0, 'max_observed_qty': abs(qty)}
        return self.symbol_stats[symbol]

    def _update_stats(self, symbol, qty, max_qty):
        pct = (qty / max_qty) * 100.0 if max_qty > 0 else 0
        self.symbol_stats[symbol]['trimmed_today_pct'] += pct

    def reset_stats(self):
        """Reset daily stats (for testing/new day)."""
        self.symbol_stats.clear()
        
# Global Instance
_lt_trim_engine = LTTrimEngine()
def get_lt_trim_engine(): return _lt_trim_engine
