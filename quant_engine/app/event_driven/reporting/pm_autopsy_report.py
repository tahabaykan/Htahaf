"""
PM Autopsy Report Generator

Generates PM-style daily reports combining:
- Risk timeline
- Regime transitions
- Intent arbitration breakdown
- CAP_RECOVERY episodes
- PnL attribution (MM vs LT)
"""

from datetime import date, datetime
from typing import Dict, Any, Optional
from app.core.logger import logger
from app.event_driven.reporting.risk_timeline_tracker import RiskTimelineTracker
from app.event_driven.reporting.regime_transition_logger import RegimeTransitionLogger
from app.event_driven.reporting.cap_recovery_tracker import CapRecoveryTracker
from app.event_driven.reporting.intent_arbitration_tracker import IntentArbitrationTracker
from app.event_driven.reporting.pnl_attribution import PnLAttribution
from app.event_driven.reporting.daily_ledger import DailyLedger


class PMAutopsyReport:
    """PM-style daily autopsy report"""
    
    def __init__(self):
        self.risk_timeline = RiskTimelineTracker()
        self.regime_logger = RegimeTransitionLogger()
        self.cap_recovery = CapRecoveryTracker()
        self.intent_arbitration = IntentArbitrationTracker()
        self.pnl_attribution = PnLAttribution()
        self.daily_ledger = DailyLedger()
    
    def generate_report(
        self,
        target_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive PM autopsy report
        
        Args:
            target_date: Date for report (default: today)
        
        Returns:
            Complete PM autopsy report dict
        """
        try:
            if target_date is None:
                target_date = date.today()
            
            # Gather all data
            timeline_summary = self.risk_timeline.get_summary_stats(target_date)
            regime_transitions = self.regime_logger.get_transitions(target_date)
            mode_transitions = self.regime_logger.get_transitions(target_date, transition_type="mode_transition")
            cap_recovery_summary = self.cap_recovery.get_summary(target_date)
            cap_recovery_episodes = self.cap_recovery.get_episodes(target_date)
            intent_arbitration_summary = self.intent_arbitration.get_summary(target_date)
            pnl_by_bucket = self.pnl_attribution.get_pnl_by_bucket(target_date)
            pnl_by_classification = self.pnl_attribution.get_pnl_by_classification(target_date)
            pnl_by_effect = self.pnl_attribution.get_pnl_by_effect(target_date)
            daily_summary = self.daily_ledger.get_daily_summary(target_date)
            
            # Build report
            report = {
                "date": target_date.isoformat(),
                "generated_at": datetime.now().isoformat(),
                
                # Risk Timeline
                "risk_timeline": {
                    "summary": timeline_summary,
                    "snapshot_count": timeline_summary.get("snapshot_count", 0),
                },
                
                # Regime Transitions
                "regime_transitions": {
                    "count": len(regime_transitions),
                    "transitions": regime_transitions,
                },
                
                # Mode Transitions
                "mode_transitions": {
                    "count": len(mode_transitions),
                    "transitions": mode_transitions,
                },
                
                # CAP_RECOVERY
                "cap_recovery": {
                    "summary": cap_recovery_summary,
                    "episodes": cap_recovery_episodes,
                },
                
                # Intent Arbitration
                "intent_arbitration": {
                    "summary": intent_arbitration_summary,
                },
                
                # PnL Attribution
                "pnl_attribution": {
                    "by_bucket": pnl_by_bucket,
                    "by_classification": pnl_by_classification,
                    "by_effect": pnl_by_effect,
                },
                
                # Daily Summary
                "daily_summary": {
                    "totals": daily_summary.get("totals", {}),
                    "by_classification_count": len(daily_summary.get("by_classification", {})),
                    "by_symbol_count": len(daily_summary.get("by_symbol", {})),
                },
            }
            
            return report
        
        except Exception as e:
            logger.error(f"❌ [PMAutopsy] Error generating report: {e}", exc_info=True)
            return {}
    
    def generate_formatted_report(
        self,
        target_date: Optional[date] = None
    ) -> str:
        """
        Generate formatted text report
        
        Args:
            target_date: Date for report (default: today)
        
        Returns:
            Formatted report string
        """
        try:
            report = self.generate_report(target_date)
            
            if not report:
                return "Error generating report"
            
            lines = [
                "=" * 80,
                f"PM AUTopsy REPORT - {report['date']}",
                f"Generated: {report['generated_at']}",
                "=" * 80,
                "",
                
                # Risk Timeline
                "RISK TIMELINE:",
                f"  Snapshots: {report['risk_timeline']['snapshot_count']}",
            ]
            
            timeline_summary = report['risk_timeline']['summary']
            if timeline_summary.get("gross_exposure"):
                gross = timeline_summary["gross_exposure"]
                lines.extend([
                    f"  Gross Exposure:",
                    f"    Min: {gross.get('min', 0):.2f}%",
                    f"    Max: {gross.get('max', 0):.2f}%",
                    f"    Avg: {gross.get('avg', 0):.2f}%",
                ])
            
            lines.extend([
                "",
                # Regime Transitions
                "REGIME TRANSITIONS:",
                f"  Count: {report['regime_transitions']['count']}",
            ])
            
            for transition in report['regime_transitions']['transitions'][:10]:  # First 10
                lines.append(
                    f"  {transition.get('datetime', '')}: "
                    f"{transition.get('from_regime', '')} → {transition.get('to_regime', '')}"
                )
            
            lines.extend([
                "",
                # Mode Transitions
                "MODE TRANSITIONS:",
                f"  Count: {report['mode_transitions']['count']}",
            ])
            
            for transition in report['mode_transitions']['transitions'][:10]:  # First 10
                lines.append(
                    f"  {transition.get('datetime', '')}: "
                    f"{transition.get('from_mode', '')} → {transition.get('to_mode', '')} "
                    f"({transition.get('reason', '')})"
                )
            
            lines.extend([
                "",
                # CAP_RECOVERY
                "CAP_RECOVERY:",
            ])
            
            cap_summary = report['cap_recovery']['summary']
            if cap_summary.get("episode_count", 0) > 0:
                lines.extend([
                    f"  Episodes: {cap_summary.get('episode_count', 0)}",
                    f"  Total Duration: {cap_summary.get('total_duration_seconds', 0):.1f}s",
                    f"  Avg Duration: {cap_summary.get('avg_duration_seconds', 0):.1f}s",
                    f"  Total Exposure Reduction: {cap_summary.get('total_exposure_reduction_pct', 0):.2f}%",
                    f"  Avg Exposure Reduction: {cap_summary.get('avg_exposure_reduction_pct', 0):.2f}%",
                ])
            else:
                lines.append("  No CAP_RECOVERY episodes")
            
            lines.extend([
                "",
                # Intent Arbitration
                "INTENT ARBITRATION:",
            ])
            
            arb_summary = report['intent_arbitration']['summary']
            if arb_summary.get("arbitration_count", 0) > 0:
                lines.extend([
                    f"  Arbitration Cycles: {arb_summary.get('arbitration_count', 0)}",
                    f"  Total Input Intents: {arb_summary.get('total_input_intents', 0)}",
                    f"  Total Output Intents: {arb_summary.get('total_output_intents', 0)}",
                    f"  Total Suppressed: {arb_summary.get('total_suppressed_intents', 0)}",
                    f"  Suppression Rate: {arb_summary.get('suppression_rate', 0):.2f}%",
                ])
            
            lines.extend([
                "",
                # PnL Attribution
                "PNL ATTRIBUTION:",
            ])
            
            pnl_bucket = report['pnl_attribution']['by_bucket']
            if pnl_bucket.get("total", {}).get("realized_pnl", 0) != 0:
                lines.extend([
                    f"  Total Realized PnL: ${pnl_bucket.get('total', {}).get('realized_pnl', 0):,.2f}",
                    f"  LT PnL: ${pnl_bucket.get('lt', {}).get('realized_pnl', 0):,.2f} "
                    f"({pnl_bucket.get('lt', {}).get('pnl_pct', 0):.1f}%)",
                    f"  MM PnL: ${pnl_bucket.get('mm', {}).get('realized_pnl', 0):,.2f} "
                    f"({pnl_bucket.get('mm', {}).get('pnl_pct', 0):.1f}%)",
                ])
            
            lines.extend([
                "",
                "=" * 80,
            ])
            
            return "\n".join(lines)
        
        except Exception as e:
            logger.error(f"❌ [PMAutopsy] Error generating formatted report: {e}", exc_info=True)
            return f"Error generating formatted report: {e}"



