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
        self.last_diagnostic = None  # Store last cycle diagnostic for API access
        
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
        
        # Diagnostic tracking
        diagnostic = {
            'exposure_ratio': 0.0,
            'exposure_pot_total': 0.0,
            'exposure_pot_max': 0.0,
            'regime': 'UNKNOWN',
            'base_multiplier': 1.0,
            'positions_analyzed': 0,
            'intent_generated': 0,
            'mode': request.exposure.mode if request.exposure else 'N/A',
            'threshold': rules.get('reducemore', {}).get('eligibility', {}).get('exposure_ratio_threshold', 0.8),
            'triggered': False,
            'trigger_reason': []
        }
        
        try:
            # 1. Exposure Check -> Global Regime & Multiplier Base
            exposure = request.exposure
            base_multiplier = 1.0
            regime = "NORMAL"
            
            if exposure:
                # Basic Logic: If exposure > 80%, defensive.
                ratio = exposure.pot_total / exposure.pot_max if exposure.pot_max > 0 else 0
                
                diagnostic['exposure_ratio'] = ratio
                diagnostic['exposure_pot_total'] = exposure.pot_total
                diagnostic['exposure_pot_max'] = exposure.pot_max
                
                # Load thresholds from rules
                eligibility = rules.get('reducemore', {}).get('eligibility', {})
                threshold = eligibility.get('exposure_ratio_threshold', 0.8)
                diagnostic['threshold'] = threshold
                
                if ratio >= threshold:
                    regime = "DEFENSIVE"
                    base_multiplier = 1.5  # Start scaling up
                    diagnostic['triggered'] = True
                    diagnostic['trigger_reason'].append(f"Exposure ratio {ratio:.2%} >= threshold {threshold:.2%}")
                
                # Check Mode (GECIS / DEFANSIF)
                if exposure.mode in ['DEFANSIF', 'GECIS']:
                    regime = "AGGRESSIVE"  # Or "DEFENSIVE" depending on definition
                    base_multiplier = max(base_multiplier, 1.5)
                    diagnostic['triggered'] = True
                    diagnostic['trigger_reason'].append(f"Mode is {exposure.mode}")
                
                diagnostic['regime'] = regime
                diagnostic['base_multiplier'] = base_multiplier

            # 2. Per-Symbol Analysis
            for pos in request.positions:
                # MM Position Filter - LT engines should NOT process MM positions
                pos_tag = getattr(pos, 'tag', '') or ''
                if 'MM' in pos_tag.upper():
                    logger.debug(f"[REDUCEMORE] Skipping MM position: {pos.symbol} (tag={pos_tag})")
                    continue
                    
                diagnostic['positions_analyzed'] += 1
                
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

            diagnostic['intent_generated'] = len(output.intents)
            output.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log comprehensive diagnostic summary
            logger.info("=" * 80)
            logger.info("[REDUCEMORE DIAGNOSTIC] Cycle Summary:")
            logger.info(f"  Exposure: {diagnostic['exposure_ratio']:.2%} ({diagnostic['exposure_pot_total']:.0f}/{diagnostic['exposure_pot_max']:.0f})")
            logger.info(f"  Threshold: {diagnostic['threshold']:.2%}")
            logger.info(f"  Regime: {diagnostic['regime']}, Multiplier: {diagnostic['base_multiplier']}")
            logger.info(f"  Mode: {diagnostic['mode']}")
            logger.info(f"  Triggered: {diagnostic['triggered']}")
            if diagnostic['trigger_reason']:
                for reason in diagnostic['trigger_reason']:
                    logger.info(f"    - {reason}")
            logger.info(f"  Positions Analyzed: {diagnostic['positions_analyzed']}")
            logger.info(f"  Intents Generated: {diagnostic['intent_generated']}")
            
            if diagnostic['intent_generated'] == 0:
                if not diagnostic['triggered']:
                    logger.warning(f"[REDUCEMORE] ⚠️ NO INTENTS - Exposure below threshold ({diagnostic['exposure_ratio']:.2%} < {diagnostic['threshold']:.2%})")
                else:
                    logger.warning(f"[REDUCEMORE] ⚠️ NO INTENTS - Regime {diagnostic['regime']} but no emergency conditions met")
            else:
                logger.info(f"[REDUCEMORE] ✅ Generated {diagnostic['intent_generated']} intents")
            logger.info("=" * 80)
            
            # Store diagnostic for API access
            output.diagnostic = diagnostic
            self.last_diagnostic = diagnostic
            
            return output

        except Exception as e:
            logger.error(f"[REDUCEMORE] Error in run: {e}", exc_info=True)
            return output

# Global Instance
_reducemore_engine = ReducemoreEngine()
def get_reducemore_engine(): return _reducemore_engine
