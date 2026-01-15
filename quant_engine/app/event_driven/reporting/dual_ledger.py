"""
Dual-Ledger Reporting

Ledger A: Overnight/BefDay baseline snapshot
Ledger B: Intraday fills (today's trading activity)
Combined: Baseline carry + intraday performance + net end position
"""

from datetime import date, datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict
from app.core.logger import logger
from app.event_driven.reporting.daily_ledger import DailyLedger
from app.event_driven.baseline.befday_snapshot import BefDaySnapshot
from app.event_driven.reporting.intraday_tracker import IntradayTracker


class DualLedgerReport:
    """Dual-ledger reporting: Baseline + Intraday"""
    
    def __init__(self, account_id: str = "HAMMER"):
        self.account_id = account_id
        self.daily_ledger = DailyLedger()
        self.befday_snapshot = BefDaySnapshot()
        self.intraday_tracker = IntradayTracker()
    
    def get_baseline_report(self, snapshot_date: Optional[date] = None) -> Dict[str, Any]:
        """Get Ledger A: Overnight/BefDay baseline snapshot report"""
        if snapshot_date is None:
            snapshot_date = date.today()
        
        snapshot = self.befday_snapshot.load_snapshot(self.account_id, snapshot_date)
        if not snapshot:
            logger.warning(f"⚠️ No BefDay snapshot found for {self.account_id} on {snapshot_date}")
            return {
                "account_id": self.account_id,
                "snapshot_date": snapshot_date.isoformat(),
                "entries": [],
                "totals": {
                    "total_symbols": 0,
                    "total_notional": 0.0,
                    "total_long_notional": 0.0,
                    "total_short_notional": 0.0,
                }
            }
        
        entries = snapshot.get("entries", [])
        
        # Aggregate by symbol
        by_symbol = {}
        total_long_notional = 0.0
        total_short_notional = 0.0
        
        for entry in entries:
            symbol = entry.get("symbol", "")
            befday_qty = entry.get("befday_qty", 0)
            befday_cost = entry.get("befday_cost", 0.0)
            notional = entry.get("notional", 0.0)
            
            if symbol not in by_symbol:
                by_symbol[symbol] = {
                    "symbol": symbol,
                    "befday_qty": 0,
                    "befday_cost": 0.0,
                    "notional": 0.0,
                }
            
            by_symbol[symbol]["befday_qty"] += befday_qty
            by_symbol[symbol]["befday_cost"] = befday_cost  # Use latest
            by_symbol[symbol]["notional"] += notional
            
            if befday_qty > 0:
                total_long_notional += notional
            else:
                total_short_notional += notional
        
        return {
            "account_id": self.account_id,
            "snapshot_date": snapshot_date.isoformat(),
            "entries": list(by_symbol.values()),
            "totals": {
                "total_symbols": len(by_symbol),
                "total_notional": total_long_notional + total_short_notional,
                "total_long_notional": total_long_notional,
                "total_short_notional": total_short_notional,
            }
        }
    
    def get_intraday_report(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """Get Ledger B: Intraday fills (today's trading activity)"""
        return self.daily_ledger.get_daily_summary(target_date)
    
    def get_intraday_pnl(self, symbol: str, target_date: Optional[date] = None) -> float:
        """
        Get intraday realized PnL for a symbol from IntradayTracker
        
        Args:
            symbol: Symbol
            target_date: Date (default: today)
        
        Returns:
            Realized PnL (only from closing intraday-opened positions)
        """
        if target_date is None:
            target_date = date.today()
        
        position = self.intraday_tracker.get_intraday_position(
            self.account_id, symbol, target_date
        )
        return position.get("realized_pnl", 0.0)
    
    def generate_combined_report(self, target_date: Optional[date] = None) -> str:
        """Generate combined end-of-day report: Baseline + Intraday + Net"""
        if target_date is None:
            target_date = date.today()
        
        # Get baseline (Ledger A)
        baseline = self.get_baseline_report(target_date)
        
        # Get intraday (Ledger B)
        intraday = self.get_intraday_report(target_date)
        
        # Combine
        report_lines = [
            "=" * 80,
            f"DUAL-LEDGER END OF DAY REPORT - {target_date.isoformat()}",
            f"Account: {self.account_id}",
            "=" * 80,
            "",
            "LEDGER A: OVERNIGHT BASELINE (BefDay Snapshot)",
            "-" * 80,
            f"Snapshot Date: {baseline.get('snapshot_date', 'N/A')}",
            f"Total Symbols: {baseline['totals']['total_symbols']}",
            f"Total Baseline Notional: ${baseline['totals']['total_notional']:,.2f}",
            f"  Long: ${baseline['totals']['total_long_notional']:,.2f}",
            f"  Short: ${baseline['totals']['total_short_notional']:,.2f}",
            "",
        ]
        
        # Baseline entries
        for entry in sorted(baseline.get("entries", []), key=lambda x: x["symbol"]):
            report_lines.append(
                f"  {entry['symbol']}: "
                f"qty={entry['befday_qty']:,}, "
                f"cost=${entry['befday_cost']:.2f}, "
                f"notional=${entry['notional']:,.2f}"
            )
        
        report_lines.extend([
            "",
            "LEDGER B: INTRADAY FILLS (Today's Trading)",
            "-" * 80,
            f"Total Filled Qty: {intraday['totals']['total_filled_qty']:,}",
            f"Total Filled Notional: ${intraday['totals']['total_filled_notional']:,.2f}",
            f"Total Realized P&L: ${intraday['totals']['total_realized_pnl']:,.2f}",
            f"Total Fill Count: {intraday['totals']['total_count_fills']:,}",
            f"Total Net Qty Change: {intraday['totals']['total_net_qty_change']:,}",
            "",
        ])
        
        # Intraday by classification
        for classification in sorted(intraday.get("by_classification", {}).keys()):
            cls_data = intraday["by_classification"][classification]
            report_lines.append(
                f"  {classification}: "
                f"qty={cls_data['filled_qty']:,}, "
                f"notional=${cls_data['filled_notional']:,.2f}, "
                f"PnL=${cls_data['realized_pnl']:,.2f}, "
                f"fills={cls_data['count_fills']}"
            )
        
        report_lines.extend([
            "",
            "COMBINED: BASELINE CARRY + INTRADAY PERFORMANCE",
            "-" * 80,
        ])
        
        # Calculate net positions per symbol
        baseline_by_symbol = {e["symbol"]: e for e in baseline.get("entries", [])}
        intraday_by_symbol = intraday.get("by_symbol", {})
        
        all_symbols = set(baseline_by_symbol.keys()) | set(intraday_by_symbol.keys())
        
        total_baseline_notional = baseline["totals"]["total_notional"]
        total_intraday_notional = intraday["totals"]["total_filled_notional"]
        total_realized_pnl = intraday["totals"]["total_realized_pnl"]
        
        # Estimate end position notional (baseline + intraday changes)
        # This is simplified - in real system, use actual current positions
        estimated_end_notional = total_baseline_notional + (
            intraday["totals"]["total_net_qty_change"] * 100.0  # Stub: assume $100 avg price
        )
        
        report_lines.extend([
            f"Baseline Carry (Overnight): ${total_baseline_notional:,.2f}",
            f"Intraday Trading Notional: ${total_intraday_notional:,.2f}",
            f"Intraday Realized P&L: ${total_realized_pnl:,.2f}",
            f"Estimated End Position Notional: ${estimated_end_notional:,.2f}",
            "",
            "NET POSITIONS BY SYMBOL:",
        ])
        
        for symbol in sorted(all_symbols):
            baseline_entry = baseline_by_symbol.get(symbol, {})
            intraday_entry = intraday_by_symbol.get(symbol, {})
            
            befday_qty = baseline_entry.get("befday_qty", 0)
            befday_cost = baseline_entry.get("befday_cost", 0.0)
            intraday_delta = intraday_entry.get("net_qty_change", 0)
            end_qty = befday_qty + intraday_delta
            intraday_pnl = intraday_entry.get("realized_pnl", 0.0)
            
            report_lines.append(
                f"  {symbol}: "
                f"baseline={befday_qty:,} @ ${befday_cost:.2f}, "
                f"intraday_delta={intraday_delta:+,}, "
                f"end_qty={end_qty:,}, "
                f"intraday_PnL=${intraday_pnl:,.2f}"
            )
        
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    def export_combined_json(self, target_date: Optional[date] = None, output_path: Optional[str] = None) -> str:
        """Export combined report as JSON"""
        if target_date is None:
            target_date = date.today()
        
        baseline = self.get_baseline_report(target_date)
        intraday = self.get_intraday_report(target_date)
        
        combined = {
            "account_id": self.account_id,
            "report_date": target_date.isoformat(),
            "ledger_a_baseline": baseline,
            "ledger_b_intraday": intraday,
            "summary": {
                "baseline_notional": baseline["totals"]["total_notional"],
                "intraday_notional": intraday["totals"]["total_filled_notional"],
                "intraday_realized_pnl": intraday["totals"]["total_realized_pnl"],
                "intraday_fill_count": intraday["totals"]["total_count_fills"],
            }
        }
        
        import json
        json_str = json.dumps(combined, indent=2, default=str)
        
        if output_path:
            with open(output_path, "w") as f:
                f.write(json_str)
            logger.info(f"✅ Exported combined JSON report to {output_path}")
        
        return json_str

