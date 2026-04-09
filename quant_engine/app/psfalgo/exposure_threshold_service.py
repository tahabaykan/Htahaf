"""
Exposure Threshold Service

⚠️ DEPRECATED — NOT IMPORTED BY ANY MODULE ⚠️

This is the v1 implementation. The active version is:
    app.psfalgo.exposure_threshold_service_v2.ExposureThresholdServiceV2

Used by: xnl_engine, exposure_calculator, psfalgo_routes, trading_routes.
TODO: Delete this file after confirming no runtime references exist.

Manages exposure threshold configuration and determines which risk engine
(KARBOTU or REDUCEMORE) should be active based on current and potential exposure.

Supports user-configurable thresholds saved to/loaded from CSV.
"""

import os
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.decision_models import ExposureSnapshot, PositionSnapshot


class ExposureThresholdService:
    """
    Manages exposure thresholds and determines active risk engine.
    
    Features:
    - Load/save thresholds from CSV
    - Calculate potential exposure (with pending orders)
    - Determine KARBOTU vs REDUCEMORE activation
    """
    
    def __init__(self, config_path: str = "config/exposure_thresholds.csv"):
        self.config_path = Path(config_path)
        self.thresholds = self.load_thresholds()
        logger.info(
            f"[EXPOSURE_THRESHOLD] Initialized with thresholds: "
            f"Current={self.thresholds['current_threshold']}%, "
            f"Potential={self.thresholds['potential_threshold']}%"
        )
    
    def load_thresholds(self) -> Dict[str, float]:
        """
        Load exposure thresholds from CSV.
        
        Returns:
            Dict with 'current_threshold', 'potential_threshold', and 'pot_max' keys
        """
        try:
            if self.config_path.exists():
                df = pd.read_csv(self.config_path)
                thresholds = {}
                for _, row in df.iterrows():
                    thresholds[row['setting']] = float(row['value'])
                
                # Validate required keys (support legacy 'current threshold' typo)
                if 'current_threshold' not in thresholds and 'current threshold' in thresholds:
                    thresholds['current_threshold'] = thresholds['current threshold']
                if 'current_threshold' not in thresholds:
                    thresholds['current_threshold'] = 92.0
                if 'potential_threshold' not in thresholds:
                    thresholds['potential_threshold'] = 100.0
                if 'pot_max' not in thresholds:
                    thresholds['pot_max'] = 1400000.0  # $1.4M default
                
                logger.info(f"[EXPOSURE_THRESHOLD] Loaded thresholds from {self.config_path}")
                return thresholds
            else:
                logger.warning(
                    f"[EXPOSURE_THRESHOLD] Config not found at {self.config_path}, using defaults"
                )
                return self._get_default_thresholds()
        
        except Exception as e:
            logger.error(f"[EXPOSURE_THRESHOLD] Error loading config: {e}", exc_info=True)
            return self._get_default_thresholds()
    
    def save_thresholds(self, current: float, potential: float, pot_max: Optional[float] = None):
        """
        Save exposure thresholds to CSV.
        
        Args:
            current: Current exposure threshold (%)
            potential: Potential exposure threshold (%)
            pot_max: Maximum exposure limit ($), optional
        """
        try:
            # Create config directory if doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Prepare data
            data = [
                {'setting': 'current_threshold', 'value': current},
                {'setting': 'potential_threshold', 'value': potential}
            ]
            
            if pot_max is not None:
                data.append({'setting': 'pot_max', 'value': pot_max})
            else:
                # Keep existing pot_max
                data.append({'setting': 'pot_max', 'value': self.thresholds.get('pot_max', 1400000.0)})
            
            # Create DataFrame
            df = pd.DataFrame(data)
            
            # Save to CSV
            df.to_csv(self.config_path, index=False)
            
            # Update in-memory
            self.thresholds['current_threshold'] = current
            self.thresholds['potential_threshold'] = potential
            if pot_max is not None:
                self.thresholds['pot_max'] = pot_max
            
            logger.info(
                f"[EXPOSURE_THRESHOLD] Saved thresholds: Current={current}%, "
                f"Potential={potential}%, Pot Max=${self.thresholds.get('pot_max', 1400000):,.0f}"
            )
        
        except Exception as e:
            logger.error(f"[EXPOSURE_THRESHOLD] Error saving config: {e}", exc_info=True)
    
    def _get_default_thresholds(self) -> Dict[str, float]:
        """Get default exposure thresholds (max cur exp %92, max pot exp %100)."""
        return {
            'current_threshold': 92.0,   # max cur exp % - hard risk when current >= this
            'potential_threshold': 100.0, # max pot exp % - hard risk when potential >= this
            'pot_max': 1400000.0
        }
    
    def calculate_potential_exposure(
        self,
        current_exposure: ExposureSnapshot,
        positions: List[PositionSnapshot],
        pending_orders: List[Any],
        l1_data: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate potential exposure including pending orders.
        
        Only includes INCREASE orders (LONG_INC, SHORT_INC) in pending.
        DECREASE orders (LONG_DEC, SHORT_DEC) reduce exposure.
        
        Args:
            current_exposure: Current exposure snapshot
            positions: Current position snapshots
            pending_orders: List of pending (unfilled) orders
            l1_data: L1 market data for pricing
            
        Returns:
            (potential_exposure_pct, debug_info) tuple
        """
        try:
            # Create simulated positions by applying pending orders
            simulated_positions = self._simulate_pending_fills(
                positions, 
                pending_orders, 
                l1_data
            )
            
            # Calculate exposure from simulated positions
            potential_pot_total = 0.0
            for pos in simulated_positions:
                if pos.current_price and pos.current_price > 0:
                    position_value = abs(pos.qty) * pos.current_price
                    potential_pot_total += position_value
            
            # Calculate percentage
            pot_max = current_exposure.pot_max
            potential_exposure_pct = (potential_pot_total / pot_max * 100) if pot_max > 0 else 0.0
            
            debug_info = {
                'current_pot_total': current_exposure.pot_total,
                'potential_pot_total': potential_pot_total,
                'pot_max': pot_max,
                'pending_orders_count': len(pending_orders),
                'delta': potential_pot_total - current_exposure.pot_total
            }
            
            logger.debug(
                f"[EXPOSURE_THRESHOLD] Potential exposure: {potential_exposure_pct:.2f}% "
                f"(Current: {current_exposure.pot_total:,.0f} → Potential: {potential_pot_total:,.0f}, "
                f"Delta: {debug_info['delta']:,.0f}, Pending: {len(pending_orders)})"
            )
            
            return potential_exposure_pct, debug_info
        
        except Exception as e:
            logger.error(f"[EXPOSURE_THRESHOLD] Error calculating potential exposure: {e}", exc_info=True)
            # Fallback: return current exposure
            current_pct = (current_exposure.pot_total / current_exposure.pot_max * 100) if current_exposure.pot_max > 0 else 0.0
            return current_pct, {}
    
    def _simulate_pending_fills(
        self,
        positions: List[PositionSnapshot],
        pending_orders: List[Any],
        l1_data: Dict[str, Any]
    ) -> List[PositionSnapshot]:
        """
        Simulate pending order fills to create potential positions.
        
        Respects 8-tag system:
        - LONG_INC / SHORT_INC: Adds to exposure
        - LONG_DEC / SHORT_DEC: Reduces exposure
        
        Returns:
            List of simulated PositionSnapshot objects
        """
        # Create a position map
        position_map = {pos.symbol: pos for pos in positions}
        
        # Apply pending orders
        for order in pending_orders:
            symbol = order.symbol
            side = order.side  # BUY or SELL
            qty = order.qty
            
            # Get strategy tag if available
            strategy_tag = getattr(order, 'strategy_tag', None) or getattr(order, 'order_subtype', None)
            
            # Determine if this is INCREASE or DECREASE
            is_increase = self._is_increase_order(strategy_tag, side, position_map.get(symbol))
            
            # Get or create position
            if symbol not in position_map:
                # New position from order
                position_map[symbol] = PositionSnapshot(
                    symbol=symbol,
                    qty=0,
                    befday_qty=0,
                    current_price=l1_data.get(symbol, {}).get('last', 0.0),
                    avg_price=l1_data.get(symbol, {}).get('last', 0.0),
                    unrealized_pnl=0.0
                )
            
            # Apply order to position (PositionSnapshot uses qty, not current_qty)
            pos = position_map[symbol]
            if side == 'BUY':
                pos.qty += qty
            else:  # SELL
                pos.qty -= qty
        
        return list(position_map.values())
    
    def _is_increase_order(
        self,
        strategy_tag: Optional[str],
        side: str,
        position: Optional[PositionSnapshot]
    ) -> bool:
        """
        Determine if an order increases exposure (risk-increasing).
        
        Uses 8-tag system:
        - LT_LONG_INC, MM_LONG_INC: TRUE
        - LT_SHORT_INC, MM_SHORT_INC: TRUE
        - LT_LONG_DEC, MM_LONG_DEC: FALSE
        - LT_SHORT_DEC, MM_SHORT_DEC: FALSE
        
        Fallback if no tag: infer from side and current position
        """
        if strategy_tag:
            tag_upper = strategy_tag.upper()
            # INC catches both INC and INCREASE (legacy)
            if 'INC' in tag_upper:
                return True
            if 'DEC' in tag_upper:
                return False
        
        # Fallback: infer from side and position
        if position is None or abs(position.qty) < 0.001:
            # New position → always INCREASE
            return True
        
        current_qty = position.qty
        if side == 'BUY':
            # BUY increases LONG, decreases SHORT
            return current_qty >= 0  # LONG position or flat → increase
        else:  # SELL
            # SELL increases SHORT, decreases LONG
            return current_qty <= 0  # SHORT position or flat → increase
    
    def determine_active_engine(
        self,
        current_exposure_pct: float,
        potential_exposure_pct: float
    ) -> str:
        """
        Determine which risk engine should be active.
        
        Logic:
        - If Current ≥ threshold OR Potential ≥ threshold → REDUCEMORE
        - Else → KARBOTU
        
        Args:
            current_exposure_pct: Current exposure percentage
            potential_exposure_pct: Potential exposure percentage
            
        Returns:
            "KARBOTU" or "REDUCEMORE"
        """
        current_threshold = self.thresholds['current_threshold']
        potential_threshold = self.thresholds['potential_threshold']
        
        if current_exposure_pct >= current_threshold:
            reason = f"Current exposure {current_exposure_pct:.2f}% >= threshold {current_threshold}%"
            logger.warning(f"[EXPOSURE_SWITCH] REDUCEMORE activated: {reason}")
            return "REDUCEMORE"
        
        if potential_exposure_pct >= potential_threshold:
            reason = f"Potential exposure {potential_exposure_pct:.2f}% >= threshold {potential_threshold}%"
            logger.warning(f"[EXPOSURE_SWITCH] REDUCEMORE activated: {reason}")
            return "REDUCEMORE"
        
        logger.info(
            f"[EXPOSURE_SWITCH] KARBOTU active "
            f"(Current: {current_exposure_pct:.2f}% < {current_threshold}%, "
            f"Potential: {potential_exposure_pct:.2f}% < {potential_threshold}%)"
        )
        return "KARBOTU"
    
    def get_exposure_status(
        self,
        current_exposure: ExposureSnapshot,
        positions: List[PositionSnapshot],
        pending_orders: List[Any],
        l1_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get comprehensive exposure status.
        
        Returns:
            Dict with current_pct, potential_pct, active_engine, etc.
        """
        current_pct = (current_exposure.pot_total / current_exposure.pot_max * 100) if current_exposure.pot_max > 0 else 0.0

        # Potential exposure
        potential_pct, debug_info = self.calculate_potential_exposure(
            current_exposure,
            positions,
            pending_orders,
            l1_data
        )
        
        # Active engine
        active_engine = self.determine_active_engine(current_pct, potential_pct)
        
        return {
            'current_exposure_pct': current_pct,
            'potential_exposure_pct': potential_pct,
            'current_pot_total': current_exposure.pot_total,
            'potential_pot_total': debug_info.get('potential_pot_total', current_exposure.pot_total),
            'pot_max': current_exposure.pot_max,
            'active_engine': active_engine,
            'thresholds': self.thresholds,
            'pending_orders_count': len(pending_orders),
            'timestamp': datetime.now().isoformat()
        }

    def is_hard_risk_mode(self, current_exposure_pct: float, potential_exposure_pct: float) -> bool:
        """
        True if current >= max_cur_exp OR potential >= max_pot_exp (position increase must be skipped).
        """
        cur_lim = self.thresholds.get('current_threshold', 92.0)
        pot_lim = self.thresholds.get('potential_threshold', 100.0)
        return current_exposure_pct >= cur_lim or potential_exposure_pct >= pot_lim

    def get_limits_for_api(self) -> Dict[str, float]:
        """Return max_cur_exp_pct and max_pot_exp_pct for API/UI (single source)."""
        return {
            'max_cur_exp_pct': self.thresholds.get('current_threshold', 92.0),
            'max_pot_exp_pct': self.thresholds.get('potential_threshold', 100.0),
        }


# Global instance
_exposure_threshold_service: Optional[ExposureThresholdService] = None


def get_exposure_threshold_service() -> ExposureThresholdService:
    """Get or create global ExposureThresholdService instance"""
    global _exposure_threshold_service
    if _exposure_threshold_service is None:
        _exposure_threshold_service = ExposureThresholdService()
    return _exposure_threshold_service


def initialize_exposure_threshold_service(config_path: Optional[str] = None):
    """Initialize global ExposureThresholdService instance"""
    global _exposure_threshold_service
    _exposure_threshold_service = ExposureThresholdService(config_path=config_path or "config/exposure_thresholds.csv")
    logger.info("[EXPOSURE_THRESHOLD] Service initialized")
