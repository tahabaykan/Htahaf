"""
Intent Arbitration Layer

Resolves conflicts between multiple intents from Decision Engine.
Determines which intents are allowed, merged, suppressed, or delayed.
"""

from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from app.core.logger import logger
from app.event_driven.reporting.intent_arbitration_tracker import IntentArbitrationTracker


class IntentPriority:
    """Priority levels for intents (higher number = higher priority)"""
    CAP_RECOVERY = 100
    HARD_DERISK = 80
    SOFT_DERISK = 60
    RISK_REDUCING = 40  # Any *_DECREASE
    LT_BAND_DRIFT = 20
    MM_CHURN = 10  # Lowest priority


class IntentArbiter:
    """Arbitrates between multiple intents"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize IntentArbiter with configuration
        
        Args:
            config: Full risk_rules.yaml configuration (includes intent_arbitration section)
        """
        self.full_config = config  # Store full config for nested access
        self.config = config.get("intent_arbitration", {})
        self.cap_recovery_target = self.config.get("cap_recovery_target_gross", 123.0)
        self.mm_overnight_max_pct = self.config.get("mm_overnight_max_pct", 15.0)
        self.soft_suppress_threshold = self.config.get("soft_suppress_threshold", 120.0)
        
        # Initialize tracker (optional, for reporting)
        try:
            self.tracker = IntentArbitrationTracker()
        except Exception as e:
            logger.warning(f"⚠️ [IntentArbiter] Failed to initialize tracker: {e}")
            self.tracker = None
    
    def get_intent_priority(self, intent_data: Dict[str, Any]) -> int:
        """
        Get priority score for an intent
        
        Returns:
            Priority score (higher = more important)
        """
        intent_type = intent_data.get("intent_type", "")
        classification = intent_data.get("classification", "")
        effect = intent_data.get("effect", "")
        
        # CAP_RECOVERY (highest)
        if intent_type == "CAP_RECOVERY":
            return IntentPriority.CAP_RECOVERY
        
        # HARD_DERISK
        if intent_type == "HARD_DERISK":
            return IntentPriority.HARD_DERISK
        
        # SOFT_DERISK
        if intent_type == "SOFT_DERISK":
            return IntentPriority.SOFT_DERISK
        
        # Risk-reducing (any *_DECREASE)
        if effect == "DECREASE":
            return IntentPriority.RISK_REDUCING
        
        # LT Band Drift corrective
        if intent_type == "LT_BAND_CORRECTIVE":
            return IntentPriority.LT_BAND_DRIFT
        
        # MM churn (lowest)
        if intent_type in ["MM_CHURN", "ALPHA"] or classification.startswith("MM_"):
            return IntentPriority.MM_CHURN
        
        # Default: use explicit priority if provided
        return intent_data.get("priority", IntentPriority.MM_CHURN)
    
    def is_risk_increasing(self, intent_data: Dict[str, Any]) -> bool:
        """Check if intent is risk-increasing"""
        effect = intent_data.get("effect", "")
        return effect == "INCREASE"
    
    def is_cap_recovery_active(self, current_gross_exposure_pct: float) -> bool:
        """Check if CAP_RECOVERY should be active"""
        # Get max exposure from full config (nested under exposure section)
        exposure_config = self.full_config.get("exposure", {})
        max_exposure = exposure_config.get("max_gross_exposure_pct", 130.0)
        return current_gross_exposure_pct >= max_exposure
    
    def should_suppress_mm_churn(
        self,
        current_gross_exposure_pct: float,
        active_intent_types: List[str]
    ) -> bool:
        """Determine if MM churn should be suppressed"""
        # Suppress during CAP_RECOVERY
        if "CAP_RECOVERY" in active_intent_types:
            return True
        
        # Suppress during HARD_DERISK
        if "HARD_DERISK" in active_intent_types:
            return True
        
        # Suppress if gross exposure > soft threshold
        if current_gross_exposure_pct > self.soft_suppress_threshold:
            return True
        
        return False
    
    def should_suppress_lt_drift(
        self,
        active_intent_types: List[str]
    ) -> bool:
        """Determine if LT drift corrective should be suppressed"""
        # Suppress during HARD_DERISK
        if "HARD_DERISK" in active_intent_types:
            return True
        
        return False
    
    def merge_intents_same_symbol(
        self,
        intents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge intents on the same symbol with same direction & effect
        
        Args:
            intents: List of intents for the same symbol
        
        Returns:
            Merged intents
        """
        if len(intents) <= 1:
            return intents
        
        # Group by (direction, effect)
        groups = defaultdict(list)
        for intent in intents:
            key = (intent.get("dir", ""), intent.get("effect", ""))
            groups[key].append(intent)
        
        merged = []
        for (direction, effect), group_intents in groups.items():
            if len(group_intents) == 1:
                merged.append(group_intents[0])
            else:
                # Merge: sum quantities, use highest priority metadata
                merged_intent = group_intents[0].copy()
                total_qty = sum(i.get("quantity", 0) for i in group_intents)
                merged_intent["quantity"] = total_qty
                
                # Use highest priority intent's metadata
                highest_priority = max(group_intents, key=lambda x: self.get_intent_priority(x))
                merged_intent["intent_type"] = highest_priority.get("intent_type", "")
                merged_intent["priority"] = self.get_intent_priority(highest_priority)
                merged_intent["reason"] = f"Merged {len(group_intents)} intents: {highest_priority.get('reason', '')}"
                
                # Sum risk deltas
                merged_intent["risk_delta_notional"] = sum(i.get("risk_delta_notional", 0.0) for i in group_intents)
                merged_intent["risk_delta_gross_pct"] = sum(i.get("risk_delta_gross_pct", 0.0) for i in group_intents)
                
                merged.append(merged_intent)
        
        return merged
    
    def resolve_symbol_conflicts(
        self,
        intents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Resolve conflicts for intents on the same symbol
        
        Args:
            intents: List of intents for the same symbol
        
        Returns:
            Resolved intents (conflicts resolved, higher priority wins)
        """
        if len(intents) <= 1:
            return intents
        
        # Sort by priority (highest first)
        sorted_intents = sorted(intents, key=lambda x: self.get_intent_priority(x), reverse=True)
        
        # Check for conflicts (same direction, opposite effect)
        resolved = []
        seen_directions = set()
        
        for intent in sorted_intents:
            direction = intent.get("dir", "")
            effect = intent.get("effect", "")
            key = direction
            
            # If we already have an intent for this direction, check conflict
            if key in seen_directions:
                # Conflict: same direction, different effect
                # Higher priority already added, skip this one
                logger.debug(
                    f"🔀 [IntentArbiter] Suppressed conflicting intent: "
                    f"{intent.get('symbol')} {intent.get('intent_type')} "
                    f"[{intent.get('classification')}] (lower priority)"
                )
                continue
            
            # If both are risk-reducing, choose one with lower expected cost
            if effect == "DECREASE" and len(resolved) > 0:
                existing = resolved[0]
                if existing.get("effect") == "DECREASE":
                    # Compare costs (if available in metadata)
                    existing_cost = existing.get("metadata", {}).get("estimated_cost", float('inf'))
                    intent_cost = intent.get("metadata", {}).get("estimated_cost", float('inf'))
                    
                    if intent_cost < existing_cost:
                        # Replace with cheaper option
                        resolved[0] = intent
                        logger.debug(
                            f"💰 [IntentArbiter] Chose cheaper derisk: "
                            f"{intent.get('symbol')} (cost: ${intent_cost:.2f} vs ${existing_cost:.2f})"
                        )
                    continue
            
            resolved.append(intent)
            seen_directions.add(key)
        
        return resolved
    
    def arbitrate(
        self,
        intents: List[Dict[str, Any]],
        current_gross_exposure_pct: float,
        current_mode: str = "NORMAL"
    ) -> List[Dict[str, Any]]:
        """
        Main arbitration function
        
        Args:
            intents: List of raw intents from Decision Engine
            current_gross_exposure_pct: Current gross exposure percentage
            current_mode: Current policy mode (NORMAL, THROTTLE, etc.)
        
        Returns:
            Filtered and merged list of intents to execute
        """
        if not intents:
            return []
        
        # Step 1: Check for CAP_RECOVERY
        cap_recovery_active = self.is_cap_recovery_active(current_gross_exposure_pct)
        active_intent_types = [i.get("intent_type", "") for i in intents]
        
        if cap_recovery_active or "CAP_RECOVERY" in active_intent_types:
            logger.info(
                f"🚨 [IntentArbiter] CAP_RECOVERY active (gross={current_gross_exposure_pct:.2f}%)"
            )
            # Suppress ALL risk-increasing intents (except CAP_RECOVERY itself)
            filtered = [
                i for i in intents
                if not self.is_risk_increasing(i) or i.get("intent_type") == "CAP_RECOVERY"
            ]
            intents = filtered
        
        # Step 2: Suppress MM churn if needed
        if self.should_suppress_mm_churn(current_gross_exposure_pct, active_intent_types):
            filtered = [
                i for i in intents
                if not (i.get("intent_type") in ["MM_CHURN", "ALPHA"] or
                       i.get("classification", "").startswith("MM_"))
            ]
            intents = filtered
            logger.debug(f"🚫 [IntentArbiter] Suppressed MM churn intents")
        
        # Step 3: Suppress LT drift if HARD_DERISK active
        if self.should_suppress_lt_drift(active_intent_types):
            filtered = [
                i for i in intents
                if i.get("intent_type") != "LT_BAND_CORRECTIVE"
            ]
            intents = filtered
            logger.debug(f"🚫 [IntentArbiter] Suppressed LT drift intents (HARD_DERISK active)")
        
        # Step 4: Group by symbol and resolve conflicts
        by_symbol = defaultdict(list)
        for intent in intents:
            symbol = intent.get("symbol", "UNKNOWN")
            by_symbol[symbol].append(intent)
        
        arbitrated = []
        for symbol, symbol_intents in by_symbol.items():
            # Merge intents with same direction & effect
            merged = self.merge_intents_same_symbol(symbol_intents)
            
            # Resolve conflicts (opposite effects)
            resolved = self.resolve_symbol_conflicts(merged)
            
            arbitrated.extend(resolved)
        
        # Step 5: Final priority sort
        arbitrated.sort(key=lambda x: self.get_intent_priority(x), reverse=True)
        
        # Track arbitration decision
        if self.tracker:
            # Build suppression reasons dict
            suppressed_intents = [i for i in intents if i not in arbitrated]
            suppression_reasons = {}
            for intent in suppressed_intents:
                intent_id = f"{intent.get('symbol', 'UNKNOWN')}_{intent.get('intent_type', 'UNKNOWN')}"
                if cap_recovery_active and self.is_risk_increasing(intent):
                    suppression_reasons[intent_id] = "CAP_RECOVERY: risk-increasing suppressed"
                elif self.should_suppress_mm_churn(current_gross_exposure_pct, active_intent_types):
                    if intent.get("intent_type") in ["MM_CHURN", "ALPHA"] or intent.get("classification", "").startswith("MM_"):
                        suppression_reasons[intent_id] = "MM churn suppressed"
                elif self.should_suppress_lt_drift(active_intent_types):
                    if intent.get("intent_type") == "LT_BAND_CORRECTIVE":
                        suppression_reasons[intent_id] = "LT drift suppressed (HARD_DERISK active)"
            
            self.tracker.log_arbitration(
                input_intents=intents,
                output_intents=arbitrated,
                current_gross_exposure_pct=current_gross_exposure_pct,
                current_mode=current_mode,
                suppression_reasons=suppression_reasons
            )
        
        logger.info(
            f"✅ [IntentArbiter] Arbitrated {len(intents)} → {len(arbitrated)} intents "
            f"(suppressed {len(intents) - len(arbitrated)})"
        )
        
        return arbitrated

