"""
Exposure Threshold Service V2 - ACCOUNT-AWARE

Manages exposure threshold configuration per trading account.
Each account (HAMPRO, IBKR_PED, IBKR_GUN) has its own:
- current_threshold (max current exposure %)
- potential_threshold (max potential exposure %)
- pot_max (maximum exposure limit $)

Determines which risk engine (KARBOTU or REDUCEMORE) should be active
based on account-specific thresholds.

MIGRATION:
- V1 (single CSV) → V2 (account-specific JSON)
- Backward compatible
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field

from app.core.logger import logger
from app.psfalgo.decision_models import ExposureSnapshot, PositionSnapshot


@dataclass
class AccountExposureThresholds:
    """Exposure thresholds for a single trading account"""
    current_threshold: float = 92.0   # Max current exposure %
    potential_threshold: float = 100.0  # Max potential exposure %
    pot_max: float = 1400000.0  # Maximum exposure limit ($)


def _config_dir() -> Path:
    """quant_engine/config"""
    return Path(__file__).resolve().parent.parent / "config"


class ExposureThresholdServiceV2:
    """
    Manages ACCOUNT-SPECIFIC exposure thresholds.
    
    Features:
    - Per-account threshold configuration
    - Calculate potential exposure (with pending orders)
    - Determine KARBOTU vs REDUCEMORE activation (per account)
    - V1 → V2 migration
    """
    
    def __init__(self):
        self.config_path_v2 = _config_dir() / "exposure_thresholds_v2.json"
        self.config_path_v1 = _config_dir() / "exposure_thresholds.csv"  # For migration
        
        # Account-specific thresholds: {account_id: AccountExposureThresholds}
        self.accounts_thresholds: Dict[str, AccountExposureThresholds] = {}
        
        # Load thresholds (v2 → v1 → defaults)
        self._load()
        
        logger.info(
            f"[EXPOSURE_THRESHOLD_V2] Initialized (Account-Aware). "
            f"Accounts: {list(self.accounts_thresholds.keys())}"
        )
    
    def _load(self):
        """Load thresholds: v2 JSON → migrate v1 → defaults."""
        try:
            # Try v2 (account-aware) first
            if self.config_path_v2.exists():
                with open(self.config_path_v2, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                accounts_data = data.get('accounts', {})
                for account_id, acc_data in accounts_data.items():
                    self.accounts_thresholds[account_id] = AccountExposureThresholds(
                        current_threshold=acc_data.get('current_threshold', 92.0),
                        potential_threshold=acc_data.get('potential_threshold', 100.0),
                        pot_max=acc_data.get('pot_max', 1400000.0)
                    )
                
                logger.info(
                    f"[EXPOSURE_THRESHOLD_V2] Loaded v2 (account-aware): "
                    f"{list(self.accounts_thresholds.keys())}"
                )
                return
            
            # Migrate from v1 (CSV) if exists
            if self.config_path_v1.exists():
                import pandas as pd
                df = pd.read_csv(self.config_path_v1)
                v1_thresholds = {}
                for _, row in df.iterrows():
                    v1_thresholds[row['setting']] = float(row['value'])
                
                # Support legacy 'current threshold' typo
                if 'current_threshold' not in v1_thresholds and 'current threshold' in v1_thresholds:
                    v1_thresholds['current_threshold'] = v1_thresholds['current threshold']
                
                # Create default thresholds from v1
                default_thresholds = AccountExposureThresholds(
                    current_threshold=v1_thresholds.get('current_threshold', 92.0),
                    potential_threshold=v1_thresholds.get('potential_threshold', 100.0),
                    pot_max=v1_thresholds.get('pot_max', 1400000.0)
                )
                
                # Apply to all known accounts
                for account in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
                    self.accounts_thresholds[account] = default_thresholds
                
                logger.info("[EXPOSURE_THRESHOLD_V2] Migrated from v1 (applied to all accounts)")
                self.save()  # Save as v2
                return
            
            # No config file, use defaults for all accounts
            for account in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
                self.accounts_thresholds[account] = AccountExposureThresholds()
            logger.info("[EXPOSURE_THRESHOLD_V2] No config file, using defaults for all accounts")
            
        except Exception as e:
            logger.error(f"[EXPOSURE_THRESHOLD_V2] Load error: {e}", exc_info=True)
            # Fallback: defaults for all accounts
            for account in ["HAMPRO", "IBKR_PED", "IBKR_GUN"]:
                self.accounts_thresholds[account] = AccountExposureThresholds()
    
    def save(self) -> bool:
        """Save all account thresholds to v2 JSON file"""
        try:
            self.config_path_v2.parent.mkdir(parents=True, exist_ok=True)
            
            accounts_data = {}
            for account_id, thresholds in self.accounts_thresholds.items():
                accounts_data[account_id] = {
                    'current_threshold': thresholds.current_threshold,
                    'potential_threshold': thresholds.potential_threshold,
                    'pot_max': thresholds.pot_max
                }
            
            data = {
                'version': 2,
                'accounts': accounts_data
            }
            
            with open(self.config_path_v2, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            logger.info(
                f"[EXPOSURE_THRESHOLD_V2] Saved v2 (accounts: {list(self.accounts_thresholds.keys())})"
            )
            return True
        except Exception as e:
            logger.error(f"[EXPOSURE_THRESHOLD_V2] Save error: {e}", exc_info=True)
            return False
    
    def get_thresholds(self, account_id: str) -> Dict[str, float]:
        """Get thresholds for specific account as dict"""
        if account_id not in self.accounts_thresholds:
            self.accounts_thresholds[account_id] = AccountExposureThresholds()
        
        thresholds = self.accounts_thresholds[account_id]
        return {
            'current_threshold': thresholds.current_threshold,
            'potential_threshold': thresholds.potential_threshold,
            'pot_max': thresholds.pot_max
        }
    
    def save_thresholds(
        self,
        account_id: str,
        current: float,
        potential: float,
        pot_max: Optional[float] = None
    ) -> bool:
        """
        Save exposure thresholds for specific account.
        
        Args:
            account_id: Account ID (HAMPRO, IBKR_PED, IBKR_GUN)
            current: Current exposure threshold (%)
            potential: Potential exposure threshold (%)
            pot_max: Maximum exposure limit ($), optional
        """
        try:
            if account_id not in self.accounts_thresholds:
                self.accounts_thresholds[account_id] = AccountExposureThresholds()
            
            thresholds = self.accounts_thresholds[account_id]
            thresholds.current_threshold = current
            thresholds.potential_threshold = potential
            if pot_max is not None:
                thresholds.pot_max = pot_max
            
            success = self.save()
            
            if success:
                logger.info(
                    f"[EXPOSURE_THRESHOLD_V2] Saved thresholds for {account_id}: "
                    f"Current={current}%, Potential={potential}%, Pot Max=${thresholds.pot_max:,.0f}"
                )
            
            return success
        except Exception as e:
            logger.error(f"[EXPOSURE_THRESHOLD_V2] Error saving thresholds for {account_id}: {e}", exc_info=True)
            return False
    
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
                f"[EXPOSURE_THRESHOLD_V2] Potential exposure: {potential_exposure_pct:.2f}% "
                f"(Current: {current_exposure.pot_total:,.0f} → Potential: {potential_pot_total:,.0f}, "
                f"Delta: {debug_info['delta']:,.0f}, Pending: {len(pending_orders)})"
            )
            
            return potential_exposure_pct, debug_info
        
        except Exception as e:
            logger.error(f"[EXPOSURE_THRESHOLD_V2] Error calculating potential exposure: {e}", exc_info=True)
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
        
        CRITICAL: Both INCREASE and DECREASE orders are simulated, but with
        different rules:
        
        - INCREASE orders (LONG_INC, SHORT_INC, MM_*_INC):
          Freely add to positions → exposure INCREASES
          
        - DECREASE orders (LONG_DEC, SHORT_DEC, KARBOTU_*_DEC, LT_*_DEC):
          Reduce positions toward zero → exposure DECREASES
          BUT qty is CLAMPED at zero — a DECREASE order CANNOT flip a
          position's direction (e.g., LONG→SHORT). Without this clamp,
          abs(negative_qty)*price would ADD to exposure instead of reducing it.
        
        Returns:
            List of simulated PositionSnapshot objects
        """
        # Create a position map (deep copy qty to avoid mutating originals)
        position_map = {}
        for pos in positions:
            position_map[pos.symbol] = PositionSnapshot(
                symbol=pos.symbol,
                qty=pos.qty,
                befday_qty=getattr(pos, 'befday_qty', 0),
                current_price=pos.current_price,
                avg_price=pos.avg_price,
                unrealized_pnl=getattr(pos, 'unrealized_pnl', 0.0)
            )
        
        increase_count = 0
        decrease_count = 0
        
        for order in pending_orders:
            symbol = order.symbol
            side = order.side  # BUY or SELL
            qty = order.qty
            
            # Get strategy tag if available
            strategy_tag = getattr(order, 'strategy_tag', None) or getattr(order, 'order_subtype', None)
            
            # Determine if this is INCREASE or DECREASE
            is_increase = self._is_increase_order(strategy_tag, side, position_map.get(symbol))
            
            if is_increase:
                # ═══ INCREASE: freely add to position ═══
                increase_count += 1
                
                if symbol not in position_map:
                    position_map[symbol] = PositionSnapshot(
                        symbol=symbol,
                        qty=0,
                        befday_qty=0,
                        current_price=l1_data.get(symbol, {}).get('last', 0.0),
                        avg_price=l1_data.get(symbol, {}).get('last', 0.0),
                        unrealized_pnl=0.0
                    )
                
                pos = position_map[symbol]
                if side == 'BUY':
                    pos.qty += qty
                else:  # SELL (SHORT_INC)
                    pos.qty -= qty
            else:
                # ═══ DECREASE: reduce toward zero, CLAMP at zero ═══
                # Discount factor: only count 50% of DECREASE effect
                # (conservative — not all decreases will fill)
                # A $100K DECREASE order reduces pot by $50K, not $100K.
                decrease_count += 1
                decrease_discount = 0.5  # Conservative: 50% fill assumption
                effective_qty = int(qty * decrease_discount)
                
                if symbol not in position_map:
                    # DECREASE for a symbol we don't hold — ignore
                    continue
                
                pos = position_map[symbol]
                if side == 'SELL':
                    # Selling to decrease a LONG position
                    if pos.qty > 0:
                        pos.qty = max(0, pos.qty - effective_qty)  # Clamp at 0
                    # If pos is already SHORT or zero, SELL DEC is a no-op
                elif side == 'BUY':
                    # Buying to decrease a SHORT position
                    if pos.qty < 0:
                        pos.qty = min(0, pos.qty + effective_qty)  # Clamp at 0
                    # If pos is already LONG or zero, BUY DEC is a no-op
        
        logger.debug(
            f"[EXPOSURE_SIM] Pending simulation: "
            f"{increase_count} INCREASE applied, "
            f"{decrease_count} DECREASE applied (clamped)"
        )
        
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
        account_id: str,
        current_exposure_pct: float,
        potential_exposure_pct: float
    ) -> str:
        """
        Determine which risk engine should be active for specific account.
        
        Logic:
        - If Current ≥ threshold OR Potential ≥ threshold → REDUCEMORE
        - Else → KARBOTU
        
        Args:
            account_id: Account ID
            current_exposure_pct: Current exposure percentage
            potential_exposure_pct: Potential exposure percentage
            
        Returns:
            "KARBOTU" or "REDUCEMORE"
        """
        thresholds = self.get_thresholds(account_id)
        current_threshold = thresholds['current_threshold']
        potential_threshold = thresholds['potential_threshold']
        
        if current_exposure_pct >= current_threshold:
            reason = f"Current exposure {current_exposure_pct:.2f}% >= threshold {current_threshold}%"
            logger.warning(f"[EXPOSURE_SWITCH] {account_id} REDUCEMORE activated: {reason}")
            return "REDUCEMORE"
        
        if potential_exposure_pct >= potential_threshold:
            reason = f"Potential exposure {potential_exposure_pct:.2f}% >= threshold {potential_threshold}%"
            logger.warning(f"[EXPOSURE_SWITCH] {account_id} REDUCEMORE activated: {reason}")
            return "REDUCEMORE"
        
        logger.info(
            f"[EXPOSURE_SWITCH] {account_id} KARBOTU active "
            f"(Current: {current_exposure_pct:.2f}% < {current_threshold}%, "
            f"Potential: {potential_exposure_pct:.2f}% < {potential_threshold}%)"
        )
        return "KARBOTU"
    
    def get_exposure_status(
        self,
        account_id: str,
        current_exposure: ExposureSnapshot,
        positions: List[PositionSnapshot],
        pending_orders: List[Any],
        l1_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get comprehensive exposure status for specific account.
        
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
        
        # Active engine (account-specific)
        active_engine = self.determine_active_engine(account_id, current_pct, potential_pct)
        
        return {
            'account_id': account_id,
            'current_exposure_pct': current_pct,
            'potential_exposure_pct': potential_pct,
            'current_pot_total': current_exposure.pot_total,
            'potential_pot_total': debug_info.get('potential_pot_total', current_exposure.pot_total),
            'pot_max': current_exposure.pot_max,
            'active_engine': active_engine,
            'thresholds': self.get_thresholds(account_id),
            'pending_orders_count': len(pending_orders),
            'timestamp': datetime.now().isoformat()
        }

    def is_hard_risk_mode(
        self,
        account_id: str,
        current_exposure_pct: float,
        potential_exposure_pct: float
    ) -> bool:
        """
        True if current >= max_cur_exp OR potential >= max_pot_exp (position increase must be skipped).
        """
        thresholds = self.get_thresholds(account_id)
        cur_lim = thresholds['current_threshold']
        pot_lim = thresholds['potential_threshold']
        return current_exposure_pct >= cur_lim or potential_exposure_pct >= pot_lim

    def get_limits_for_api(self, account_id: str) -> Dict[str, float]:
        """Return max_cur_exp_pct and max_pot_exp_pct for API/UI (single source)."""
        thresholds = self.get_thresholds(account_id)
        return {
            'max_cur_exp_pct': thresholds['current_threshold'],
            'max_pot_exp_pct': thresholds['potential_threshold'],
            'pot_max': thresholds['pot_max']
        }


# Global instance
_exposure_threshold_service_v2: Optional[ExposureThresholdServiceV2] = None


def get_exposure_threshold_service_v2() -> ExposureThresholdServiceV2:
    """Get or create global ExposureThresholdServiceV2 instance"""
    global _exposure_threshold_service_v2
    if _exposure_threshold_service_v2 is None:
        _exposure_threshold_service_v2 = ExposureThresholdServiceV2()
    return _exposure_threshold_service_v2


def initialize_exposure_threshold_service_v2():
    """Initialize global ExposureThresholdServiceV2 instance"""
    global _exposure_threshold_service_v2
    _exposure_threshold_service_v2 = ExposureThresholdServiceV2()
    logger.info("[EXPOSURE_THRESHOLD_V2] Service initialized (account-aware)")
