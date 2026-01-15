"""
Policy Decision Table

Deterministic decision logic based on:
- Session regime
- Current exposure (gross, buckets)
- Potential exposure (open orders)
- Risk rules configuration

Outputs: NORMAL, THROTTLE_NEW_ORDERS, SOFT_DERISK, HARD_DERISK
"""

from typing import Dict, Any, Optional, Tuple
from enum import Enum
from app.core.logger import logger


class PolicyMode(str, Enum):
    """Policy decision modes"""
    NORMAL = "NORMAL"
    THROTTLE_NEW_ORDERS = "THROTTLE_NEW_ORDERS"
    SOFT_DERISK = "SOFT_DERISK"
    HARD_DERISK = "HARD_DERISK"


class PolicyDecisionTable:
    """Policy decision table - deterministic decision logic"""
    
    def __init__(self, risk_rules: Dict[str, Any]):
        self.risk_rules = risk_rules
        self.exposure_rules = risk_rules.get("exposure", {})
        self.bucket_rules = risk_rules.get("buckets", {})
        self.regime_rules = risk_rules.get("time_regimes", {})
        self.derisk_rules = risk_rules.get("derisk", {})
    
    def decide(
        self,
        regime: str,
        gross_exposure_pct: float,
        potential_exposure_pct: Optional[float] = None,
        lt_current_pct: Optional[float] = None,
        lt_potential_pct: Optional[float] = None,
        mm_current_pct: Optional[float] = None,
        mm_potential_pct: Optional[float] = None,
        minutes_to_close: Optional[int] = None
    ) -> Tuple[PolicyMode, str]:
        """
        Decide policy mode based on current state
        
        Returns:
            (mode, reason)
        """
        # Get regime-specific rules
        regime_config = self.regime_rules.get(regime, {})
        regime_tolerance = regime_config.get("gross_exposure_tolerance_pct", 120.0)
        allow_derisk = regime_config.get("allow_derisk", True)
        
        # Hard cap check (always enforced, regardless of regime)
        max_exposure = self.exposure_rules.get("max_gross_exposure_pct", 130.0)
        if gross_exposure_pct > max_exposure:
            return (
                PolicyMode.HARD_DERISK,
                f"HARD CAP exceeded: {gross_exposure_pct:.2f}% > {max_exposure}%"
            )
        
        # Use potential exposure if available, otherwise current
        effective_exposure = potential_exposure_pct if potential_exposure_pct is not None else gross_exposure_pct
        
        # Check if potential exposure exceeds hard cap
        if effective_exposure > max_exposure:
            return (
                PolicyMode.THROTTLE_NEW_ORDERS,
                f"Potential exposure {effective_exposure:.2f}% would exceed hard cap {max_exposure}%"
            )
        
        # Hard derisk check (16:28, 2 minutes to close)
        if regime == "CLOSE" and minutes_to_close is not None and minutes_to_close <= 2:
            if gross_exposure_pct > 100.0:
                return (
                    PolicyMode.HARD_DERISK,
                    f"Hard derisk: {minutes_to_close} min to close, exposure {gross_exposure_pct:.2f}% > 100%"
                )
        
        # Soft derisk check (after 16:15, LATE regime)
        if regime == "LATE" and allow_derisk:
            soft_limit = self.exposure_rules.get("soft_limit_pct", 120.0)
            if gross_exposure_pct > soft_limit:
                return (
                    PolicyMode.SOFT_DERISK,
                    f"Soft derisk: LATE regime, exposure {gross_exposure_pct:.2f}% > {soft_limit}%"
                )
        
        # Check regime-specific tolerance
        if effective_exposure > regime_tolerance:
            if allow_derisk:
                return (
                    PolicyMode.SOFT_DERISK,
                    f"Regime tolerance exceeded: {effective_exposure:.2f}% > {regime_tolerance}% in {regime}"
                )
            else:
                # In OPEN/EARLY, throttle but don't derisk
                return (
                    PolicyMode.THROTTLE_NEW_ORDERS,
                    f"Regime tolerance exceeded: {effective_exposure:.2f}% > {regime_tolerance}% in {regime} (throttle only)"
                )
        
        # Bucket overflow checks
        if lt_potential_pct is not None:
            lt_max = self.bucket_rules.get("LT", {}).get("max_pct", 90.0)
            if lt_potential_pct > lt_max:
                return (
                    PolicyMode.THROTTLE_NEW_ORDERS,
                    f"LT bucket potential overflow: {lt_potential_pct:.2f}% > {lt_max}%"
                )
        
        if mm_potential_pct is not None:
            mm_max = self.bucket_rules.get("MM_PURE", {}).get("max_pct", 30.0)
            if mm_potential_pct > mm_max:
                return (
                    PolicyMode.THROTTLE_NEW_ORDERS,
                    f"MM_PURE bucket potential overflow: {mm_potential_pct:.2f}% > {mm_max}%"
                )
        
        # Current bucket overflow (less urgent, but still throttle)
        if lt_current_pct is not None:
            lt_max = self.bucket_rules.get("LT", {}).get("max_pct", 90.0)
            if lt_current_pct > lt_max:
                return (
                    PolicyMode.THROTTLE_NEW_ORDERS,
                    f"LT bucket current overflow: {lt_current_pct:.2f}% > {lt_max}%"
                )
        
        if mm_current_pct is not None:
            mm_max = self.bucket_rules.get("MM_PURE", {}).get("max_pct", 30.0)
            if mm_current_pct > mm_max:
                return (
                    PolicyMode.THROTTLE_NEW_ORDERS,
                    f"MM_PURE bucket current overflow: {mm_current_pct:.2f}% > {mm_max}%"
                )
        
        # All checks passed - NORMAL mode
        return (PolicyMode.NORMAL, "All limits within tolerance")



