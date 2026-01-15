"""
LiquidityGuard - Pre-Trade Sizing Constraints

Applies liquidity-based sizing constraints before sending orders.
Prevents order spam and respects market liquidity.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from app.core.logger import logger


class LiquidityGuard:
    """Pre-trade sizing constraints based on liquidity"""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize LiquidityGuard with configuration"""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "liquidity_limits.yaml"
        
        self.config = self._load_config(config_path)
        self.min_lot = self.config.get("global", {}).get("min_lot", 200)
        self.scale_factor = self.config.get("global", {}).get("scale_factor", 1000)
        self.residual_policy = self.config.get("global", {}).get("residual_close_policy", "defer")
        
        # Residual handling
        residual_config = self.config.get("residual", {})
        self.allow_near_close = residual_config.get("allow_near_close", True)
        self.allow_hard_derisk = residual_config.get("allow_hard_derisk", True)
        self.allow_soft_derisk = residual_config.get("allow_soft_derisk", False)
        self.near_close_threshold = residual_config.get("near_close_threshold", 2)
        
        # Logging
        logging_config = self.config.get("logging", {})
        self.log_adjustments = logging_config.get("log_adjustments", True)
        self.log_deferred = logging_config.get("log_deferred", True)
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
            return config or {}
        except Exception as e:
            logger.warning(f"⚠️ Failed to load liquidity_limits.yaml: {e}, using defaults")
            return {}
    
    def calculate_base_max(self, avg_adv: float) -> int:
        """
        Calculate base maximum order size from average daily volume
        
        Args:
            avg_adv: Average daily volume (shares)
        
        Returns:
            Base maximum order size (shares)
        """
        base_max = max(round(avg_adv / self.scale_factor), self.min_lot)
        return int(base_max)
    
    def get_bucket_max(self, bucket: str) -> Optional[int]:
        """
        Get maximum cap for bucket
        
        Args:
            bucket: Bucket name (LT, MM, MM_PURE)
        
        Returns:
            Maximum cap (None = no cap)
        """
        bucket_config = self.config.get("buckets", {}).get(bucket, {})
        if not bucket_config.get("enabled", True):
            return 0  # Disabled
        
        max_cap = bucket_config.get("max_cap")
        return int(max_cap) if max_cap is not None else None
    
    def should_allow_residual(
        self,
        residual_qty: int,
        minutes_to_close: Optional[int] = None,
        intent_type: Optional[str] = None
    ) -> bool:
        """
        Determine if residual order (< min_lot) should be allowed
        
        Args:
            residual_qty: Remaining quantity (< min_lot)
            minutes_to_close: Minutes until market close
            intent_type: Intent type (HARD_DERISK, SOFT_DERISK, etc.)
        
        Returns:
            True if residual should be allowed
        """
        if residual_qty >= self.min_lot:
            return True  # Not a residual
        
        # Check if near close
        if minutes_to_close is not None and minutes_to_close <= self.near_close_threshold:
            if self.allow_near_close:
                return True
        
        # Check if hard derisk
        if intent_type == "HARD_DERISK":
            if self.allow_hard_derisk:
                return True
        
        # Check if soft derisk
        if intent_type == "SOFT_DERISK":
            if self.allow_soft_derisk:
                return True
        
        # Default: defer
        return False
    
    def clamp_quantity(
        self,
        desired_qty: int,
        symbol: str,
        classification: str,
        avg_adv: float,
        bucket: str,
        minutes_to_close: Optional[int] = None,
        intent_type: Optional[str] = None
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Clamp order quantity based on liquidity constraints
        
        Args:
            desired_qty: Desired order quantity
            symbol: Symbol
            classification: Order classification (e.g., LT_LONG_INCREASE)
            avg_adv: Average daily volume
            bucket: Bucket (LT, MM, MM_PURE)
            minutes_to_close: Minutes until market close
            intent_type: Intent type (HARD_DERISK, SOFT_DERISK, etc.)
        
        Returns:
            (clamped_qty, adjustment_info)
        """
        adjustment_info = {
            "original_qty": desired_qty,
            "adjusted_qty": desired_qty,
            "reason": None,
            "deferred": False,
        }
        
        # Calculate base_max
        base_max = self.calculate_base_max(avg_adv)
        
        # Get bucket-specific max
        bucket_max = self.get_bucket_max(bucket)
        
        # Determine max_qty
        if bucket_max is not None:
            # MM bucket: cap at bucket_max
            max_qty = min(base_max, bucket_max)
        else:
            # LT bucket: no cap (only base_max)
            max_qty = base_max
        
        # Clamp to [min_lot, max_qty]
        if desired_qty >= self.min_lot:
            # Normal case: clamp to max
            clamped_qty = min(desired_qty, max_qty)
            if clamped_qty < desired_qty:
                adjustment_info["reason"] = f"Capped at {max_qty} (base_max={base_max}, bucket_max={bucket_max})"
                adjustment_info["adjusted_qty"] = clamped_qty
        else:
            # Residual case (< min_lot)
            if self.should_allow_residual(desired_qty, minutes_to_close, intent_type):
                # Allow residual
                clamped_qty = desired_qty
                adjustment_info["reason"] = f"Residual allowed (near_close={minutes_to_close}, intent={intent_type})"
            else:
                # Defer residual
                clamped_qty = 0
                adjustment_info["deferred"] = True
                adjustment_info["reason"] = f"Residual deferred (< min_lot={self.min_lot})"
                adjustment_info["adjusted_qty"] = 0
        
        # Log adjustment if needed
        if self.log_adjustments and (clamped_qty != desired_qty or adjustment_info["deferred"]):
            if adjustment_info["deferred"]:
                if self.log_deferred:
                    logger.info(
                        f"🛑 [LiquidityGuard] Deferred {symbol}: "
                        f"qty={desired_qty} < min_lot={self.min_lot} "
                        f"[{classification}]"
                    )
            else:
                logger.info(
                    f"✂️ [LiquidityGuard] Adjusted {symbol}: "
                    f"{desired_qty} → {clamped_qty} "
                    f"(base_max={base_max}, bucket_max={bucket_max}) "
                    f"[{classification}]"
                )
        
        adjustment_info["adjusted_qty"] = clamped_qty
        return clamped_qty, adjustment_info
    
    def validate_order(
        self,
        symbol: str,
        classification: str,
        desired_qty: int,
        avg_adv: float,
        bucket: str,
        minutes_to_close: Optional[int] = None,
        intent_type: Optional[str] = None
    ) -> Tuple[bool, Optional[int], Dict[str, Any]]:
        """
        Validate and adjust order quantity
        
        Args:
            symbol: Symbol
            classification: Order classification
            desired_qty: Desired quantity
            avg_adv: Average daily volume
            bucket: Bucket (LT, MM, MM_PURE)
            minutes_to_close: Minutes until market close
            intent_type: Intent type
        
        Returns:
            (is_valid, adjusted_qty, adjustment_info)
        """
        clamped_qty, adjustment_info = self.clamp_quantity(
            desired_qty=desired_qty,
            symbol=symbol,
            classification=classification,
            avg_adv=avg_adv,
            bucket=bucket,
            minutes_to_close=minutes_to_close,
            intent_type=intent_type
        )
        
        is_valid = clamped_qty > 0
        return is_valid, clamped_qty if is_valid else None, adjustment_info



