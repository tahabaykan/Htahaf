"""
REDUCEMORE Decision Engine - Phase 11 Refactor
==============================================

Role: "Risk & Multiplier Engine"
-   Generates MULTIPLIERS (Scaling Factor, Regime) for LT TRIM.
-   Generates INTENTS (Emergency Reductions) if risk is critical.

Dual Output Mode:
    1.  Multipliers: Scales the intensity of LT Trim execution.
        -   e.g. 1.0 (Normal), 1.5 (High Risk), 2.0 (Critical)
    2.  Intents: Direct emergency actions if risk safeguards passed.
"""

import asyncio
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from app.core.logger import logger
from app.psfalgo.decision_models import (
    PositionSnapshot,
    SymbolMetrics,
    ExposureSnapshot,
    DecisionRequest
)

# Shared Models (Phase 11) - Ideally import from models.py, defining here for now
@dataclass
class Intent:
    symbol: str
    action: str
    qty: int
    intent_category: str
    priority: int
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RiskMultiplier:
    symbol: str
    value: float             # 1.0 to 3.0+
    regime: str              # NORMAL, DEFENSIVE, AGGRESSIVE
    reason: str

@dataclass
class ReducemoreOutput:
    multipliers: Dict[str, RiskMultiplier] = field(default_factory=dict)
    intents: List[Intent] = field(default_factory=list)
    execution_time_ms: float = 0.0

class ReducemoreEngine:
    """
    REDUCEMORE Engine (Phase 11)
    
    1. Checks Exposure -> Determines Regime.
    2. Suggests Multipliers for LT Trim.
    3. If Critical -> Generates Emergency Intents.
    """
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        
    async def run(
        self, 
        request: DecisionRequest, 
        rules: Dict[str, Any]
    ) -> ReducemoreOutput:
        """
        Main entry point.
        """
        start_time = datetime.now()
        output = ReducemoreOutput()
        
        try:
            # 1. Exposure Check -> Global Regime & Multiplier Base
            exposure = request.exposure
            base_multiplier = 1.0
            regime = "NORMAL"
            
            if exposure:
                # Basic Logic: If exposure > 80%, defensive.
                ratio = exposure.pot_total / exposure.pot_max if exposure.pot_max > 0 else 0
                
                # Load thresholds from rules
                eligibility = rules.get('reducemore', {}).get('eligibility', {})
                threshold = eligibility.get('exposure_ratio_threshold', 0.8)
                
                if ratio >= threshold:
                    regime = "DEFENSIVE"
                    base_multiplier = 1.5 # Start scaling up
                
                # Check Mode (GECIS / DEFANSIF)
                if exposure.mode in ['DEFANSIF', 'GECIS']:
                    regime = "AGGRESSIVE" # Or "DEFENSIVE" depending on definition
                    base_multiplier = max(base_multiplier, 1.5)

            # 2. Per-Symbol Analysis
            for pos in request.positions:
                # Generate Multiplier
                # We can refine multiplier based on symbol metrics too (e.g. illiquid gets higher multiplier)
                mult_val = base_multiplier
                metric = request.metrics.get(pos.symbol)
                
                # Example: If spread is huge, maybe reduce aggression? Or increase purely on price?
                # For now, let's stick to Exposure-Based multiplier.
                
                output.multipliers[pos.symbol] = RiskMultiplier(
                    symbol=pos.symbol,
                    value=mult_val,
                    regime=regime,
                    reason=f"Regime: {regime}"
                )
                
                # 3. Emergency Intent Check
                # If regime is AGGRESSIVE and specific "panic" conditions met
                # Create direct intent (Priority: EMERGENCY_REDUCE)
                if regime == "AGGRESSIVE" and mult_val >= 2.0:
                    # Logic to determine if we should FORCE dump
                    # Placeholder for Phase 11 basic impl
                    pass 

            output.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            return output

        except Exception as e:
            logger.error(f"[REDUCEMORE] Error in run: {e}", exc_info=True)
            return output

# Global Instance
_reducemore_engine = ReducemoreEngine()
def get_reducemore_engine(): return _reducemore_engine
