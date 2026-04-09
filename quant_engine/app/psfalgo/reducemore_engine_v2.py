"""
REDUCEMORE Engine V2 - JanallApp Compatible

Correct exposure thresholds:
- Offensive: < 92.7%
- Transition (GEÇIŞ): 92.7% - 95.5%
- Defensive: > 95.5%

3-mode system: OFANSIF / GEÇIŞ / DEFANSIVE
"""
import pandas as pd
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.decision_models import DecisionRequest


class ReducemoreEngineV2:
    """
    REDUCEMORE Engine V2 - JanallApp Compatible
    
    Key Changes from V1:
    - Correct thresholds: 92.7% (offensive), 95.5% (defensive)
    - 3-mode system instead of 2-mode
    - Total lots based (not ratio based)
    """
    
    def __init__(self, config_path: str = "config/exposure_thresholds.csv"):
        self.config_path = Path(config_path)
        self.load_thresholds()
        logger.info(
            f"[REDUCEMORE_V2] Initialized with thresholds: "
            f"Offensive={self.offensive_threshold:.0f} lots ({self.offensive_pct:.1%}), "
            f"Defensive={self.defensive_threshold:.0f} lots ({self.defensive_pct:.1%})"
        )
    
    def load_thresholds(self):
        """Load exposure thresholds from CSV"""
        try:
            if not self.config_path.exists():
                logger.warning(f"[REDUCEMORE_V2] Config not found: {self.config_path}")
                self._create_default_config()
            
            df = pd.read_csv(self.config_path)
            config = {row['setting']: float(row['value']) for _, row in df.iterrows()}
            
            self.exposure_limit = config.get('exposure_limit', 5_000_000)
            self.avg_price = config.get('avg_price', 100)
            self.pot_expo_limit = config.get('pot_expo_limit', 6_363_600)
            self.defensive_pct = config.get('defensive_pct', 0.955)
            self.offensive_pct = config.get('offensive_pct', 0.927)
            
            # Calculate thresholds
            self.max_lot = self.exposure_limit / self.avg_price
            self.defensive_threshold = self.max_lot * self.defensive_pct  # 95.5%
            self.offensive_threshold = self.max_lot * self.offensive_pct  # 92.7%
            
            logger.info(f"[REDUCEMORE_V2] Thresholds loaded from {self.config_path}")
        
        except Exception as e:
            logger.error(f"[REDUCEMORE_V2] Error loading thresholds: {e}", exc_info=True)
            self._set_defaults()
    
    def _create_default_config(self):
        """Create default config file"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'setting': ['exposure_limit', 'avg_price', 'pot_expo_limit', 'defensive_pct', 'offensive_pct'],
            'value': [5_000_000, 100, 6_363_600, 0.955, 0.927],
            'description': [
                'Maximum exposure in dollars',
                'Average stock price for lot calculation',
                'Portfolio exposure limit',
                'Defensive threshold percentage (95.5%)',
                'Offensive threshold percentage (92.7%)'
            ]
        }
        
        df = pd.DataFrame(data)
        df.to_csv(self.config_path, index=False)
        logger.info(f"[REDUCEMORE_V2] Created default config at {self.config_path}")
        
        self._set_defaults()
    
    def _set_defaults(self):
        """Set default values"""
        self.exposure_limit = 5_000_000
        self.avg_price = 100
        self.pot_expo_limit = 6_363_600
        self.defensive_pct = 0.955
        self.offensive_pct = 0.927
        self.max_lot = 50_000
        self.defensive_threshold = 47_750  # 95.5% of 50,000
        self.offensive_threshold = 46_350  # 92.7% of 50,000
    
    def determine_exposure_mode(self, total_lots: float, pot_max_override: float = None, avg_price_override: float = None) -> str:
        """
        Determine exposure mode based on total lots
        
        Args:
            total_lots: Total lot count across all positions
            pot_max_override: If provided, recalculate thresholds using this 
                              pot_max (from ExposureSnapshot / Port Adjuster V2)
                              instead of the static CSV exposure_limit.
            avg_price_override: Account-specific avg price from Port Adjuster V2
        
        Returns:
            One of: "OFANSIF", "GEÇIŞ", "DEFANSIVE"
        """
        # Use dynamic pot_max if provided (account-specific from Port Adjuster V2)
        if pot_max_override and pot_max_override > 0:
            avg_price = avg_price_override if (avg_price_override and avg_price_override > 0) else (self.avg_price if self.avg_price > 0 else 100)
            dynamic_max_lot = pot_max_override / avg_price
            defensive_threshold = dynamic_max_lot * self.defensive_pct
            offensive_threshold = dynamic_max_lot * self.offensive_pct
            logger.debug(
                f"[REDUCEMORE_V2] Using dynamic pot_max=${pot_max_override:,.0f} → "
                f"max_lot={dynamic_max_lot:.0f}, off={offensive_threshold:.0f}, def={defensive_threshold:.0f}"
            )
        else:
            defensive_threshold = self.defensive_threshold
            offensive_threshold = self.offensive_threshold
            dynamic_max_lot = self.max_lot
        
        if total_lots > defensive_threshold:
            mode = "DEFANSIVE"  # > 95.5%
            logger.warning(
                f"[REDUCEMORE_V2] DEFANSIVE mode: {total_lots:.0f} lots > "
                f"{defensive_threshold:.0f} ({self.defensive_pct:.1%})"
            )
        elif total_lots < offensive_threshold:
            mode = "OFANSIF"  # < 92.7%
            logger.info(
                f"[REDUCEMORE_V2] OFANSIF mode: {total_lots:.0f} lots < "
                f"{offensive_threshold:.0f} ({self.offensive_pct:.1%})"
            )
        else:
            mode = "GEÇIŞ"  # 92.7% - 95.5%
            logger.info(
                f"[REDUCEMORE_V2] GEÇIŞ mode: {total_lots:.0f} lots between "
                f"{offensive_threshold:.0f} and {defensive_threshold:.0f}"
            )
        
        return mode
    
    def calculate_total_lots(self, positions: list) -> float:
        """Calculate total lots from positions"""
        total = sum(abs(p.qty) for p in positions)
        return total
    
    async def run(self, request: DecisionRequest) -> Dict[str, Any]:
        """
        Main execution - determine exposure mode
        
        Uses pot_max from request.exposure (Port Adjuster V2, account-specific)
        if available, otherwise falls back to static CSV config.
        
        Returns dict with mode and diagnostic info
        """
        try:
            total_lots = self.calculate_total_lots(request.positions)
            
            # Use account-specific pot_max from ExposureSnapshot if available
            pot_max_override = None
            if request.exposure and request.exposure.pot_max > 0:
                pot_max_override = request.exposure.pot_max
            
            # CRITICAL FIX: Use account-specific avg_pref_price from Port Adjuster V2
            # instead of hardcoded $100. Preferred stocks average ~$20, not $100.
            # Without this fix, max_lot is 5x too small → permanent DEFANSIVE mode.
            account_avg_price = self.avg_price  # fallback to config
            try:
                from app.trading.trading_account_context import get_trading_context
                from app.port_adjuster.port_adjuster_store_v2 import get_port_adjuster_store_v2
                ctx = get_trading_context()
                account_id = ctx.trading_mode.value
                pa_store = get_port_adjuster_store_v2()
                pa_config = pa_store.get_config(account_id)
                if pa_config and pa_config.avg_pref_price > 0:
                    account_avg_price = pa_config.avg_pref_price
                    logger.info(
                        f"[REDUCEMORE_V2] Using account avg_price=${account_avg_price:.0f} "
                        f"from Port Adjuster V2 ({account_id})"
                    )
            except Exception as e:
                logger.debug(f"[REDUCEMORE_V2] Could not get account avg_price: {e}")
            
            mode = self.determine_exposure_mode(
                total_lots, pot_max_override=pot_max_override, avg_price_override=account_avg_price
            )
            
            # Calculate ratio using the effective max_lot
            effective_max_lot = self.max_lot
            if pot_max_override and pot_max_override > 0:
                effective_max_lot = pot_max_override / account_avg_price
            
            ratio = total_lots / effective_max_lot if effective_max_lot > 0 else 0
            
            diagnostic = {
                'total_lots': total_lots,
                'max_lot': effective_max_lot,
                'pot_max_source': 'PORT_ADJUSTER_V2' if pot_max_override else 'STATIC_CSV',
                'pot_max_value': pot_max_override or (self.max_lot * self.avg_price),
                'ratio': ratio,
                'ratio_pct': ratio * 100,
                'mode': mode,
                'defensive_threshold': effective_max_lot * self.defensive_pct,
                'offensive_threshold': effective_max_lot * self.offensive_pct,
                'timestamp': datetime.now().isoformat()
            }
            
            # Log summary
            logger.info("=" * 80)
            logger.info("[REDUCEMORE_V2 DIAGNOSTIC] Exposure Summary:")
            logger.info(f"  Total Lots: {total_lots:.0f}")
            logger.info(f"  Max Lot: {effective_max_lot:.0f} (source: {diagnostic['pot_max_source']})")
            logger.info(f"  Ratio: {ratio:.1%}")
            logger.info(f"  Mode: {mode}")
            logger.info(f"  Thresholds: Offensive={diagnostic['offensive_threshold']:.0f} ({self.offensive_pct:.1%}), Defensive={diagnostic['defensive_threshold']:.0f} ({self.defensive_pct:.1%})")
            logger.info("=" * 80)
            
            return {
                'mode': mode,
                'diagnostic': diagnostic
            }
        
        except Exception as e:
            logger.error(f"[REDUCEMORE_V2] Error in run: {e}", exc_info=True)
            return {
                'mode': 'UNKNOWN',
                'diagnostic': {'error': str(e)}
            }


# Global instance
_reducemore_engine_v2 = None

def get_reducemore_engine_v2() -> ReducemoreEngineV2:
    """Get global REDUCEMORE V2 engine instance"""
    global _reducemore_engine_v2
    if _reducemore_engine_v2 is None:
        _reducemore_engine_v2 = ReducemoreEngineV2()
    return _reducemore_engine_v2
