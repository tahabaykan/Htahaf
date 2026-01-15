"""
LT Band Drift Controller

Monitors LT long/short gross band ranges and generates gentle corrective intents.
"""

from typing import Dict, Any, Optional, List, Tuple
from app.core.logger import logger
from app.event_driven.contracts.events import OrderClassification


class LTBandController:
    """Controller for LT band drift correction"""
    
    def __init__(self, risk_rules: Dict[str, Any]):
        self.risk_rules = risk_rules
        self.lt_config = risk_rules.get("buckets", {}).get("LT", {})
        self.band_drift_config = self.lt_config.get("band_drift", {})
        
        self.long_range = self.band_drift_config.get("long_pct_range", [60.0, 70.0])
        self.short_range = self.band_drift_config.get("short_pct_range", [30.0, 40.0])
        self.tolerance_days = self.band_drift_config.get("tolerance_days", 2)
        self.corrective_size_pct = self.band_drift_config.get("corrective_intent_size_pct", 0.02)
        self.use_limit_orders = self.band_drift_config.get("use_limit_orders", True)
        self.prefer_positive_pnl = self.band_drift_config.get("prefer_positive_pnl", True)
    
    def check_band_drift(
        self,
        lt_long_pct: float,
        lt_short_pct: float,
        gross_exposure_pct: float,
        positions: List[Dict[str, Any]],
        equity: float
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Check if LT bands are violated and return corrective action
        
        Args:
            lt_long_pct: LT long as % of equity
            lt_short_pct: LT short as % of equity
            gross_exposure_pct: Current gross exposure %
            positions: List of positions
            equity: Account equity
        
        Returns:
            (action_type, action_params) or (None, None) if no action needed
        """
        # Band ranges are specified as % within LT bucket (e.g., 60-70% of LT bucket)
        # We need to compare LT long/short as % of equity
        # Calculate LT bucket size as % of equity
        lt_bucket_notional = sum(
            abs(p.get("notional", 0)) for p in positions 
            if p.get("bucket") == "LT"
        )
        lt_bucket_pct = (lt_bucket_notional / equity) * 100.0 if equity > 0 else 0.0
        
        if lt_bucket_pct == 0:
            return (None, None)  # No LT bucket
        
        # Convert band ranges from % of LT bucket to % of equity
        long_min = (self.long_range[0] / 100.0) * lt_bucket_pct
        long_max = (self.long_range[1] / 100.0) * lt_bucket_pct
        short_min = (self.short_range[0] / 100.0) * lt_bucket_pct
        short_max = (self.short_range[1] / 100.0) * lt_bucket_pct
        
        # Check if bands are violated
        long_violation = lt_long_pct < long_min or lt_long_pct > long_max
        short_violation = lt_short_pct < short_min or lt_short_pct > short_max
        
        if not (long_violation or short_violation):
            return (None, None)  # Bands are within range
        
        # Determine corrective action
        action_type = None
        action_params = {}
        
        if lt_short_pct > short_max:
            # LT short too high: prefer LT_SHORT_DECREASE and/or LT_LONG_INCREASE
            action_type = "LT_SHORT_TOO_HIGH"
            action_params = {
                "prefer_classifications": [
                    OrderClassification.LT_SHORT_DECREASE.value,
                    OrderClassification.LT_LONG_INCREASE.value
                ],
                "avoid_classifications": [
                    OrderClassification.LT_SHORT_INCREASE.value,
                    OrderClassification.LT_LONG_DECREASE.value
                ]
            }
        elif lt_short_pct < short_min:
            # LT short too low: prefer LT_SHORT_INCREASE and/or LT_LONG_DECREASE
            action_type = "LT_SHORT_TOO_LOW"
            action_params = {
                "prefer_classifications": [
                    OrderClassification.LT_SHORT_INCREASE.value,
                    OrderClassification.LT_LONG_DECREASE.value
                ],
                "avoid_classifications": [
                    OrderClassification.LT_SHORT_DECREASE.value,
                    OrderClassification.LT_LONG_INCREASE.value
                ]
            }
        elif lt_long_pct > long_max:
            # LT long too high: prefer LT_LONG_DECREASE and/or LT_SHORT_INCREASE
            action_type = "LT_LONG_TOO_HIGH"
            action_params = {
                "prefer_classifications": [
                    OrderClassification.LT_LONG_DECREASE.value,
                    OrderClassification.LT_SHORT_INCREASE.value
                ],
                "avoid_classifications": [
                    OrderClassification.LT_LONG_INCREASE.value,
                    OrderClassification.LT_SHORT_DECREASE.value
                ]
            }
        elif lt_long_pct < long_min:
            # LT long too low: prefer LT_LONG_INCREASE and/or LT_SHORT_DECREASE
            action_type = "LT_LONG_TOO_LOW"
            action_params = {
                "prefer_classifications": [
                    OrderClassification.LT_LONG_INCREASE.value,
                    OrderClassification.LT_SHORT_DECREASE.value
                ],
                "avoid_classifications": [
                    OrderClassification.LT_LONG_DECREASE.value,
                    OrderClassification.LT_SHORT_INCREASE.value
                ]
            }
        
        # Check if action would violate global hard cap
        # This will be checked when generating the intent
        action_params["gross_exposure_pct"] = gross_exposure_pct
        action_params["max_gross_exposure_pct"] = 130.0
        
        return (action_type, action_params)
    
    def select_corrective_position(
        self,
        positions: List[Dict[str, Any]],
        prefer_classifications: List[str],
        avoid_classifications: List[str],
        equity: float
    ) -> Optional[Dict[str, Any]]:
        """
        Select position for corrective action
        
        Prefers:
        - Positions matching preferred classifications
        - Positions with positive/acceptable PnL (if prefer_positive_pnl)
        - Small sizes (gentle correction)
        """
        if not positions:
            return None
        
        # Filter positions by bucket (only LT)
        lt_positions = [p for p in positions if p.get("bucket", "LT") == "LT"]
        if not lt_positions:
            return None
        
        # Score positions
        scored_positions = []
        for pos in lt_positions:
            score = 0.0
            symbol = pos.get("symbol", "")
            quantity = pos.get("quantity", 0)
            avg_price = pos.get("avg_price", 0.0)
            notional = abs(pos.get("notional", 0.0))
            
            # Determine classification
            bucket = "LT"
            direction = "LONG" if quantity > 0 else "SHORT"
            # For correction, we want to change position, so effect depends on action
            # This will be determined when generating intent
            
            # Prefer smaller positions (gentle correction)
            position_size_pct = (notional / equity) * 100.0
            score += 1.0 / (1.0 + position_size_pct)  # Smaller = higher score
            
            # Prefer positions with positive PnL (if enabled)
            if self.prefer_positive_pnl:
                # Stub: assume positive PnL if position is profitable
                # In real system, calculate actual PnL
                score += 0.5  # Placeholder
            
            scored_positions.append((score, pos))
        
        # Sort by score (highest first)
        scored_positions.sort(key=lambda x: x[0], reverse=True)
        
        if scored_positions:
            return scored_positions[0][1]  # Return highest-scored position
        
        return None
    
    def calculate_corrective_quantity(
        self,
        position: Dict[str, Any],
        classification: OrderClassification,
        equity: float,
        gross_exposure_pct: float
    ) -> int:
        """Calculate gentle corrective quantity"""
        position_notional = abs(position.get("notional", 0.0))
        avg_price = position.get("avg_price", 1.0)
        
        # Use small percentage of position for gentle correction
        corrective_notional = position_notional * self.corrective_size_pct
        
        # Ensure we don't violate hard cap
        if classification.is_risk_increasing:
            max_allowed_notional = (130.0 - gross_exposure_pct) / 100.0 * equity
            corrective_notional = min(corrective_notional, max_allowed_notional)
        
        # Convert to shares
        quantity = int(corrective_notional / avg_price) if avg_price > 0 else 0
        
        # Ensure minimum 1 share
        if quantity == 0:
            quantity = 1
        
        return quantity

