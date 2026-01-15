"""
PnL Attribution

Attributes intraday PnL to MM vs LT buckets and classifications.
"""

from datetime import date
from typing import Dict, Any, Optional
from collections import defaultdict
from app.core.logger import logger
from app.event_driven.reporting.daily_ledger import DailyLedger


class PnLAttribution:
    """Attributes PnL to MM vs LT and classifications"""
    
    def __init__(self):
        self.daily_ledger = DailyLedger()
    
    def get_pnl_by_bucket(
        self,
        target_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Get PnL breakdown by bucket (LT vs MM)
        
        Returns:
            Dict with LT and MM PnL breakdowns
        """
        try:
            summary = self.daily_ledger.get_daily_summary(target_date)
            
            # Classify by bucket based on classification prefix
            lt_pnl = 0.0
            mm_pnl = 0.0
            unknown_pnl = 0.0
            
            lt_notional = 0.0
            mm_notional = 0.0
            unknown_notional = 0.0
            
            lt_fills = 0
            mm_fills = 0
            unknown_fills = 0
            
            for classification, cls_data in summary.get("by_classification", {}).items():
                pnl = cls_data.get("realized_pnl", 0.0)
                notional = cls_data.get("filled_notional", 0.0)
                fills = cls_data.get("count_fills", 0)
                
                if classification.startswith("LT_"):
                    lt_pnl += pnl
                    lt_notional += notional
                    lt_fills += fills
                elif classification.startswith("MM_"):
                    mm_pnl += pnl
                    mm_notional += notional
                    mm_fills += fills
                else:
                    unknown_pnl += pnl
                    unknown_notional += notional
                    unknown_fills += fills
            
            total_pnl = lt_pnl + mm_pnl + unknown_pnl
            total_notional = lt_notional + mm_notional + unknown_notional
            
            return {
                "date": target_date.isoformat() if target_date else date.today().isoformat(),
                "lt": {
                    "realized_pnl": lt_pnl,
                    "filled_notional": lt_notional,
                    "count_fills": lt_fills,
                    "pnl_pct": (lt_pnl / total_pnl * 100.0) if total_pnl != 0 else 0.0,
                },
                "mm": {
                    "realized_pnl": mm_pnl,
                    "filled_notional": mm_notional,
                    "count_fills": mm_fills,
                    "pnl_pct": (mm_pnl / total_pnl * 100.0) if total_pnl != 0 else 0.0,
                },
                "unknown": {
                    "realized_pnl": unknown_pnl,
                    "filled_notional": unknown_notional,
                    "count_fills": unknown_fills,
                    "pnl_pct": (unknown_pnl / total_pnl * 100.0) if total_pnl != 0 else 0.0,
                },
                "total": {
                    "realized_pnl": total_pnl,
                    "filled_notional": total_notional,
                }
            }
        
        except Exception as e:
            logger.error(f"❌ [PnLAttribution] Error getting PnL by bucket: {e}", exc_info=True)
            return {}
    
    def get_pnl_by_classification(
        self,
        target_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Get PnL breakdown by classification
        
        Returns:
            Dict with PnL for each classification
        """
        try:
            summary = self.daily_ledger.get_daily_summary(target_date)
            
            pnl_by_class = {}
            for classification, cls_data in summary.get("by_classification", {}).items():
                pnl_by_class[classification] = {
                    "realized_pnl": cls_data.get("realized_pnl", 0.0),
                    "filled_notional": cls_data.get("filled_notional", 0.0),
                    "count_fills": cls_data.get("count_fills", 0),
                    "filled_qty": cls_data.get("filled_qty", 0),
                }
            
            return {
                "date": target_date.isoformat() if target_date else date.today().isoformat(),
                "by_classification": pnl_by_class,
            }
        
        except Exception as e:
            logger.error(f"❌ [PnLAttribution] Error getting PnL by classification: {e}", exc_info=True)
            return {}
    
    def get_pnl_by_effect(
        self,
        target_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Get PnL breakdown by effect (INCREASE vs DECREASE)
        
        Returns:
            Dict with PnL for risk-increasing vs risk-reducing trades
        """
        try:
            summary = self.daily_ledger.get_daily_summary(target_date)
            
            increase_pnl = 0.0
            decrease_pnl = 0.0
            increase_notional = 0.0
            decrease_notional = 0.0
            increase_fills = 0
            decrease_fills = 0
            
            for classification, cls_data in summary.get("by_classification", {}).items():
                pnl = cls_data.get("realized_pnl", 0.0)
                notional = cls_data.get("filled_notional", 0.0)
                fills = cls_data.get("count_fills", 0)
                
                # Determine effect from classification
                if "_INCREASE" in classification:
                    increase_pnl += pnl
                    increase_notional += notional
                    increase_fills += fills
                elif "_DECREASE" in classification:
                    decrease_pnl += pnl
                    decrease_notional += notional
                    decrease_fills += fills
            
            total_pnl = increase_pnl + decrease_pnl
            
            return {
                "date": target_date.isoformat() if target_date else date.today().isoformat(),
                "increase": {
                    "realized_pnl": increase_pnl,
                    "filled_notional": increase_notional,
                    "count_fills": increase_fills,
                    "pnl_pct": (increase_pnl / total_pnl * 100.0) if total_pnl != 0 else 0.0,
                },
                "decrease": {
                    "realized_pnl": decrease_pnl,
                    "filled_notional": decrease_notional,
                    "count_fills": decrease_fills,
                    "pnl_pct": (decrease_pnl / total_pnl * 100.0) if total_pnl != 0 else 0.0,
                },
                "total": {
                    "realized_pnl": total_pnl,
                }
            }
        
        except Exception as e:
            logger.error(f"❌ [PnLAttribution] Error getting PnL by effect: {e}", exc_info=True)
            return {}



