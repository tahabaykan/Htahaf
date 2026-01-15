"""
KARBOTU Decision Engine - Phase 11 Refactor
===========================================

Role: "Macro Decision & Signal Engine"
-   Generates SIGNALS (Eligibility, Bias, Quality) for LT TRIM execution.
-   Generates INTENTS (Macro reduction suggestions) if needed.
-   Does NOT execute trades directly (delegates execution details to LT Trim).

Dual Output Mode:
    1.  Signals: Used by LT Trim engine for Veto/Bias.
    2.  Intents: Optional direct macro decisions (e.g. "Hard Reduce List").
"""

import asyncio
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.logger import logger
from app.psfalgo.decision_models import (
    PositionSnapshot,
    SymbolMetrics,
    Decision, # Legacy model, mapped to Intent
    DecisionRequest
)
# New Phase 11 Models (will be moved to a shared models file later preferably)
from dataclasses import dataclass

@dataclass
class KarbotuSignal:
    """Signal for Execution Engines."""
    symbol: str
    eligibility: bool        # Can LT Trim act on this? (Veto power)
    bias: float              # -1.0 (Strong Buy) to +1.0 (Strong Sell)
    quality_bucket: str      # GOOD, BAD, OK
    reason_codes: List[str]
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Intent:
    """Standardized Action Intent."""
    symbol: str
    action: str              # SELL, COVER, BUY
    qty: int
    intent_category: str     # KARBOTU_MACRO, LT_TRIM_MICRO, etc.
    priority: int            # 10=Micro, 20=Macro, 30=Risk, 40=Emergency
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class KarbotuOutput:
    """Output payload from Karbotu Engine."""
    signals: Dict[str, KarbotuSignal] = field(default_factory=dict)
    intents: List[Intent] = field(default_factory=list)
    execution_time_ms: float = 0.0

class KarbotuEngine:
    """
    KARBOTU Decision Engine (Phase 11)
    
    Now purely analytical + macro intent generator.
    Standard execution logic (steps 2-13) determines SIGNALS for LT Trim.
    """
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        # Fallback rules can be loaded here if config_manager not provided
     
    async def run(
        self, 
        request: DecisionRequest, 
        rules: Dict[str, Any]
    ) -> KarbotuOutput:
        """
        Main entry point.
        Args:
            request: Market data & positions
            rules: Effective strategy rules for this account
        """
        start_time = datetime.now()
        output = KarbotuOutput()
        
        try:
            # Separate positions
            longs = [p for p in request.positions if p.qty > 0]
            shorts = [p for p in request.positions if p.qty < 0]
            
            # --- PROCESS LONGS ---
            for pos in longs:
                signal, intent = self._analyze_long(pos, request.metrics.get(pos.symbol), rules)
                output.signals[pos.symbol] = signal
                if intent:
                    output.intents.append(intent)

            # --- PROCESS SHORTS ---
            for pos in shorts:
                signal, intent = self._analyze_short(pos, request.metrics.get(pos.symbol), rules)
                output.signals[pos.symbol] = signal
                if intent:
                    output.intents.append(intent)

            output.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            return output

        except Exception as e:
            logger.error(f"[KARBOTU] Error in run: {e}", exc_info=True)
            return output

    def _analyze_long(self, pos: PositionSnapshot, metric: SymbolMetrics, rules: Dict) -> Tuple[KarbotuSignal, Optional[Intent]]:
        """Analyze a LONG position."""
        if not metric:
             return KarbotuSignal(pos.symbol, False, 0.0, "UNKNOWN", ["No Metrics"]), None
        
        symbol = pos.symbol
        reasons = []
        eligible = False
        bias = 0.0 # Neutral
        bucket = "OK"
        
        # 1. GORT Filter (Veto)
        gort_conf = rules.get('karbotu', {}).get('gort_filter_longs', {})
        if gort_conf.get('enabled', True):
            filters = gort_conf.get('filters', {})
            # Gort must be > threshold
            if metric.gort is not None and metric.gort <= filters.get('gort_gt', -1.0):
                reasons.append("GORT_TOO_LOW")
                bucket = "BAD"
            # Ask Sell Pahalilik must be > threshold (not too cheap)
            elif metric.ask_sell_pahalilik is not None and metric.ask_sell_pahalilik <= filters.get('ask_sell_pahalilik_gt', -0.05):
                reasons.append("TOO_CHEAP_TO_SELL")
                bucket = "BAD"
            else:
                eligible = True # Passes basic checks
                bucket = "GOOD_LONG"
        else:
            eligible = True # Filter disabled

        # 2. Step Logic (Determines Intensity/Bias)
        # We iterate steps to find if any 'sell' condition is met. 
        # If met, it increases sell pressure (Bias).
        
        # Simplified loop for steps 2-7
        triggered_step = None
        for step_num in range(2, 8):
            step_key = f'step_{step_num}'
            step_conf = rules.get('karbotu', {}).get(step_key, {})
            if not step_conf.get('enabled', False) or step_conf.get('side') != 'LONGS':
                continue
                
            # Check filters
            # Note: Logic reused from original _check_step_filters ideally
            if self._passes_step_filters(step_conf.get('filters', {}), metric, is_shorts=False):
                triggered_step = step_num
                bias = 1.0 # Strong Selling Bias
                reasons.append(f"TRIGGER_STEP_{step_num}")
                break
        
        signal = KarbotuSignal(
            symbol=symbol, 
            eligibility=(eligible and (triggered_step is not None)), # Only eligible if triggered? Or Gort passed?
            # CORRECTION: LT Trim usually governs the trigger. Karbotu just provides the "OK".
            # If GORT passed, it is "Eligible for consideration".
            # But if a Step passed, it is "Recommended to Sell".
            # Let's say: Eligible = GORT Passed. Bias = 1.0 if Step Triggered.
            bias=bias, 
            quality_bucket=bucket, 
            reason_codes=reasons
        )
        
        # Macro Intent? (Only if configured to generate direct intents)
        intent = None
        # Future: if bias > 0.9 and macro_enabled -> create intent
        
        return signal, intent

    def _analyze_short(self, pos: PositionSnapshot, metric: SymbolMetrics, rules: Dict) -> Tuple[KarbotuSignal, Optional[Intent]]:
        """Analyze a SHORT position."""
        if not metric:
             return KarbotuSignal(pos.symbol, False, 0.0, "UNKNOWN", ["No Metrics"]), None

        symbol = pos.symbol
        reasons = []
        eligible = False
        bias = 0.0
        bucket = "OK"

        # 1. GORT Filter
        gort_conf = rules.get('karbotu', {}).get('gort_filter_shorts', {})
        if gort_conf.get('enabled', True):
            filters = gort_conf.get('filters', {})
            if metric.gort is not None and metric.gort >= filters.get('gort_lt', 1.0):
                reasons.append("GORT_TOO_HIGH")
                bucket = "BAD"
            elif metric.bid_buy_ucuzluk is not None and metric.bid_buy_ucuzluk >= filters.get('bid_buy_ucuzluk_lt', 0.05):
                reasons.append("TOO_EXPENSIVE_TO_COVER")
                bucket = "BAD"
            else:
                eligible = True
                bucket = "GOOD_SHORT"
        else:
            eligible = True

        # 2. Step Logic (9-13)
        triggered_step = None
        for step_num in range(9, 14):
            step_key = f'step_{step_num}'
            step_conf = rules.get('karbotu', {}).get(step_key, {})
            if not step_conf.get('enabled', False) or step_conf.get('side') != 'SHORTS':
                continue
            
            if self._passes_step_filters(step_conf.get('filters', {}), metric, is_shorts=True):
                triggered_step = step_num
                bias = 1.0 # Strong Buying (Covering) Bias? 
                # Note: Bias convention: +1 = Sell/Short, -1 = Buy/Cover? 
                # Plan said: "bias: float (-1.0 to 1.0, where >0 is Sell/Short pressure)"
                # Wait, usually positive bias = Bullish? No, context is "Karbotu Decision".
                # If Karbotu is "Reduce Position", then:
                # For Longs: Reduce = Sell (>0 pressure?)
                # For Shorts: Reduce = Cover (Buy) (<0 pressure?)
                # Let's standardize: Bias = "Desire to Reduce". 
                # If 1.0 -> Strongly want to reduce (Sell Long or Cover Short).
                bias = 1.0 
                reasons.append(f"TRIGGER_STEP_{step_num}")
                break

        signal = KarbotuSignal(
            symbol=symbol,
            eligibility=eligible, # Gort passed
            bias=bias,            # Step triggered
            quality_bucket=bucket,
            reason_codes=reasons
        )
        return signal, None

    def _passes_step_filters(self, filters, metric, is_shorts):
        """Helper to check filters (simplified rewrite of original logic)."""
        if is_shorts:
            # SFStot & BidBuy
            v_sfstot = metric.sfstot if metric.sfstot is not None else 0
            v_bb = metric.bid_buy_ucuzluk if metric.bid_buy_ucuzluk is not None else 0
            
            if 'sfstot_gt' in filters and not (v_sfstot > filters['sfstot_gt']): return False
            if 'sfstot_gte' in filters and not (v_sfstot >= filters['sfstot_gte']): return False
            if 'sfstot_lte' in filters and not (v_sfstot <= filters['sfstot_lte']): return False
            if 'bid_buy_ucuzluk_lt' in filters and not (v_bb < filters['bid_buy_ucuzluk_lt']): return False
            if 'bid_buy_ucuzluk_gte' in filters and not (v_bb >= filters['bid_buy_ucuzluk_gte']): return False
            if 'bid_buy_ucuzluk_lte' in filters and not (v_bb <= filters['bid_buy_ucuzluk_lte']): return False
            return True
        else:
            # FBtot & AskSell
            v_fbtot = metric.fbtot if metric.fbtot is not None else 0
            v_as = metric.ask_sell_pahalilik if metric.ask_sell_pahalilik is not None else 0
            
            if 'fbtot_lt' in filters and not (v_fbtot < filters['fbtot_lt']): return False
            if 'fbtot_gte' in filters and not (v_fbtot >= filters['fbtot_gte']): return False
            if 'fbtot_lte' in filters and not (v_fbtot <= filters['fbtot_lte']): return False
            if 'ask_sell_pahalilik_gt' in filters and not (v_as > filters['ask_sell_pahalilik_gt']): return False
            if 'ask_sell_pahalilik_gte' in filters and not (v_as >= filters['ask_sell_pahalilik_gte']): return False
            if 'ask_sell_pahalilik_lte' in filters and not (v_as <= filters['ask_sell_pahalilik_lte']): return False
            return True

# Global Instance
_karbotu_engine = KarbotuEngine()
def get_karbotu_engine(): return _karbotu_engine
