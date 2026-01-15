"""
Daily Ledger / Report Module

Aggregates fills by (date, symbol, classification) and provides end-of-day reports.
"""

import json
import time
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from collections import defaultdict
from datetime import date
from typing import Dict, Any, List, Optional
import time
import json

from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.event_driven.state.event_log import EventLog
from app.event_driven.state.store import StateStore
from app.event_driven.contracts.events import OrderEvent, OrderClassification
from app.event_driven.baseline.befday_snapshot import BefDaySnapshot
from app.event_driven.reporting.intraday_tracker import IntradayTracker


class DailyLedger:
    """Daily ledger for tracking fills by classification"""
    
    def __init__(self):
        redis_client = get_redis_client().sync
        if not redis_client:
            raise RuntimeError("Redis client not available")
        
        self.event_log = EventLog(redis_client=redis_client)
        self.state_store = StateStore(redis_client=redis_client)
        self.ledger_key_prefix = "ledger:daily"
        self.befday_snapshot = BefDaySnapshot()
        self.intraday_tracker = IntradayTracker()
    
    def record_fill(self, order_event: OrderEvent):
        """Record a fill in the daily ledger"""
        try:
            if order_event.data.get("action") not in ["FILLED", "PARTIAL_FILL"]:
                return  # Only record fills
            
            fill_data = order_event.data
            symbol = fill_data.get("symbol", "UNKNOWN")
            classification = fill_data.get("classification", "")
            filled_quantity = fill_data.get("filled_quantity", 0)
            avg_fill_price = fill_data.get("avg_fill_price", 0.0)
            timestamp = order_event.timestamp
            order_id = fill_data.get("order_id", "")
            
            # Get date from timestamp
            fill_date = datetime.fromtimestamp(timestamp / 1e9).date()
            date_str = fill_date.isoformat()
            
            # Calculate notional
            notional = abs(filled_quantity * avg_fill_price)
            
            # Get account ID and date
            account_id = fill_data.get("account_id", "HAMMER")
            fill_date = datetime.fromtimestamp(timestamp / 1e9).date() if timestamp else date.today()
            
            # Get order_action (BUY or SELL) from order data
            # This is the trading action, not the order status (ACCEPTED, FILLED, etc.)
            action = fill_data.get("order_action", "")
            if action not in ["BUY", "SELL"]:
                # Fallback: determine from classification
                classification = fill_data.get("classification", "")
                dir_str = fill_data.get("dir", "")
                effect_str = fill_data.get("effect", "")
                
                # Determine action from classification
                if (dir_str == "LONG" and effect_str == "INCREASE") or (dir_str == "SHORT" and effect_str == "DECREASE"):
                    action = "BUY"
                else:
                    action = "SELL"
            
            # Update intraday tracker and get realized PnL
            # Realized PnL is only recognized when closing intraday-opened positions
            realized_pnl, intraday_position = self.intraday_tracker.update_intraday_position(
                account_id=account_id,
                symbol=symbol,
                fill_qty=filled_quantity,
                fill_price=avg_fill_price,
                action=action,
                target_date=fill_date
            )
            
            # Calculate net position change
            if fill_data.get("action") == "BUY":
                net_qty_change = filled_quantity
            else:  # SELL
                net_qty_change = -filled_quantity
            
            # Store in ledger (by date, symbol, classification)
            ledger_key = f"{self.ledger_key_prefix}:{date_str}:{symbol}:{classification}"
            
            # Get existing entry or create new
            existing = self.state_store.get_state(ledger_key)
            if existing:
                filled_qty = existing.get("filled_qty", 0) + filled_quantity
                filled_notional = existing.get("filled_notional", 0.0) + notional
                realized_pnl_total = existing.get("realized_pnl", 0.0) + realized_pnl
                count_fills = existing.get("count_fills", 0) + 1
                net_qty_change_total = existing.get("net_qty_change", 0) + net_qty_change
            else:
                filled_qty = filled_quantity
                filled_notional = notional
                realized_pnl_total = realized_pnl
                count_fills = 1
                net_qty_change_total = net_qty_change
            
            # Update ledger entry
            ledger_entry = {
                "date": date_str,
                "symbol": symbol,
                "classification": classification,
                "filled_qty": filled_qty,
                "filled_notional": filled_notional,
                "realized_pnl": realized_pnl_total,
                "count_fills": count_fills,
                "net_qty_change": net_qty_change_total,
                "last_updated": datetime.utcnow().isoformat(),
            }
            
            self.state_store.set_state(ledger_key, ledger_entry)
            
            logger.debug(
                f"📝 Recorded fill: {symbol} {filled_quantity} @ {avg_fill_price} "
                f"[{classification}] PnL: ${realized_pnl:.2f}"
            )
        
        except Exception as e:
            logger.error(f"❌ Error recording fill: {e}", exc_info=True)
    
    def get_daily_summary(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """Get daily summary for a specific date"""
        if target_date is None:
            target_date = date.today()
        
        date_str = target_date.isoformat()
        
        # Get all ledger entries for this date
        pattern = f"{self.ledger_key_prefix}:{date_str}:*"
        keys = self.state_store.redis.keys(pattern)
        
        summary = {
            "date": date_str,
            "by_classification": defaultdict(lambda: {
                "filled_qty": 0,
                "filled_notional": 0.0,
                "realized_pnl": 0.0,
                "count_fills": 0,
                "net_qty_change": 0,
                "symbols": set()
            }),
            "by_symbol": defaultdict(lambda: {
                "filled_qty": 0,
                "filled_notional": 0.0,
                "realized_pnl": 0.0,
                "count_fills": 0,
                "net_qty_change": 0,
                "classifications": set()
            }),
            "totals": {
                "total_filled_qty": 0,
                "total_filled_notional": 0.0,
                "total_realized_pnl": 0.0,
                "total_count_fills": 0,
                "total_net_qty_change": 0,
            }
        }
        
        for key in keys:
            try:
                # Extract ledger key (remove prefix)
                key_parts = key.split(":")
                if len(key_parts) < 4:
                    continue
                ledger_key = ":".join(key_parts[1:])  # Remove "ledger" prefix
                entry = self.state_store.get_state(ledger_key)
                if not entry:
                    continue
                
                classification = entry.get("classification", "")
                symbol = entry.get("symbol", "")
                filled_qty = entry.get("filled_qty", 0)
                filled_notional = entry.get("filled_notional", 0.0)
                realized_pnl = entry.get("realized_pnl", 0.0)
                count_fills = entry.get("count_fills", 0)
                net_qty_change = entry.get("net_qty_change", 0)
                
                # Aggregate by classification
                summary["by_classification"][classification]["filled_qty"] += filled_qty
                summary["by_classification"][classification]["filled_notional"] += filled_notional
                summary["by_classification"][classification]["realized_pnl"] += realized_pnl
                summary["by_classification"][classification]["count_fills"] += count_fills
                summary["by_classification"][classification]["net_qty_change"] += net_qty_change
                summary["by_classification"][classification]["symbols"].add(symbol)
                
                # Aggregate by symbol
                summary["by_symbol"][symbol]["filled_qty"] += filled_qty
                summary["by_symbol"][symbol]["filled_notional"] += filled_notional
                summary["by_symbol"][symbol]["realized_pnl"] += realized_pnl
                summary["by_symbol"][symbol]["count_fills"] += count_fills
                summary["by_symbol"][symbol]["net_qty_change"] += net_qty_change
                summary["by_symbol"][symbol]["classifications"].add(classification)
                
                # Totals
                summary["totals"]["total_filled_qty"] += filled_qty
                summary["totals"]["total_filled_notional"] += filled_notional
                summary["totals"]["total_realized_pnl"] += realized_pnl
                summary["totals"]["total_count_fills"] += count_fills
                summary["totals"]["total_net_qty_change"] += net_qty_change
            
            except Exception as e:
                logger.warning(f"⚠️ Error processing ledger entry {key}: {e}")
                continue
        
        # Convert sets to lists for JSON serialization
        for cls_data in summary["by_classification"].values():
            cls_data["symbols"] = list(cls_data["symbols"])
        
        for sym_data in summary["by_symbol"].values():
            sym_data["classifications"] = list(sym_data["classifications"])
        
        return summary
    
    def generate_end_of_day_report(self, target_date: Optional[date] = None) -> str:
        """Generate end-of-day report as formatted string"""
        summary = self.get_daily_summary(target_date)
        
        report_lines = [
            "=" * 80,
            f"END OF DAY REPORT - {summary['date']}",
            "=" * 80,
            "",
            "TOTALS:",
            f"  Total Filled Qty: {summary['totals']['total_filled_qty']:,}",
            f"  Total Filled Notional: ${summary['totals']['total_filled_notional']:,.2f}",
            f"  Total Realized P&L: ${summary['totals']['total_realized_pnl']:,.2f}",
            f"  Total Fill Count: {summary['totals']['total_count_fills']:,}",
            f"  Total Net Qty Change: {summary['totals']['total_net_qty_change']:,}",
            "",
            "BY CLASSIFICATION:",
        ]
        
        for classification in sorted(summary["by_classification"].keys()):
            cls_data = summary["by_classification"][classification]
            report_lines.extend([
                f"  {classification}:",
                f"    Filled Qty: {cls_data['filled_qty']:,}",
                f"    Filled Notional: ${cls_data['filled_notional']:,.2f}",
                f"    Realized P&L: ${cls_data['realized_pnl']:,.2f}",
                f"    Fill Count: {cls_data['count_fills']:,}",
                f"    Net Qty Change: {cls_data['net_qty_change']:,}",
                f"    Symbols: {', '.join(sorted(cls_data['symbols']))}",
                ""
            ])
        
        report_lines.extend([
            "BY SYMBOL:",
        ])
        
        for symbol in sorted(summary["by_symbol"].keys()):
            sym_data = summary["by_symbol"][symbol]
            report_lines.extend([
                f"  {symbol}:",
                f"    Filled Qty: {sym_data['filled_qty']:,}",
                f"    Filled Notional: ${sym_data['filled_notional']:,.2f}",
                f"    Realized P&L: ${sym_data['realized_pnl']:,.2f}",
                f"    Fill Count: {sym_data['count_fills']:,}",
                f"    Net Qty Change: {sym_data['net_qty_change']:,}",
                f"    Classifications: {', '.join(sorted(sym_data['classifications']))}",
                ""
            ])
        
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    def export_json(self, target_date: Optional[date] = None, output_path: Optional[str] = None) -> str:
        """Export daily summary as JSON"""
        summary = self.get_daily_summary(target_date)
        
        # Convert sets to lists for JSON serialization
        for cls_data in summary["by_classification"].values():
            if isinstance(cls_data.get("symbols"), set):
                cls_data["symbols"] = list(cls_data["symbols"])
        
        for sym_data in summary["by_symbol"].values():
            if isinstance(sym_data.get("classifications"), set):
                sym_data["classifications"] = list(sym_data["classifications"])
        
        json_str = json.dumps(summary, indent=2, default=str)
        
        if output_path:
            with open(output_path, "w") as f:
                f.write(json_str)
            logger.info(f"✅ Exported JSON report to {output_path}")
        
        return json_str
    
    def export_csv(self, target_date: Optional[date] = None, output_path: Optional[str] = None) -> str:
        """Export daily summary as CSV"""
        import csv
        from io import StringIO
        
        summary = self.get_daily_summary(target_date)
        
        # Create CSV with detailed entries
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "Date", "Symbol", "Classification", "Filled_Qty", "Filled_Notional",
            "Realized_PnL", "Count_Fills", "Net_Qty_Change"
        ])
        
        # Get all ledger entries for this date
        date_str = target_date.isoformat() if target_date else date.today().isoformat()
        pattern = f"{self.ledger_key_prefix}:{date_str}:*"
        keys = self.state_store.redis.keys(pattern)
        
        for key in keys:
            try:
                key_parts = key.split(":")
                if len(key_parts) < 4:
                    continue
                ledger_key = ":".join(key_parts[1:])
                entry = self.state_store.get_state(ledger_key)
                if entry:
                    writer.writerow([
                        entry.get("date", ""),
                        entry.get("symbol", ""),
                        entry.get("classification", ""),
                        entry.get("filled_qty", 0),
                        entry.get("filled_notional", 0.0),
                        entry.get("realized_pnl", 0.0),
                        entry.get("count_fills", 0),
                        entry.get("net_qty_change", 0),
                    ])
            except Exception as e:
                logger.warning(f"⚠️ Error processing ledger entry {key}: {e}")
                continue
        
        csv_str = output.getvalue()
        output.close()
        
        if output_path:
            with open(output_path, "w", newline="") as f:
                f.write(csv_str)
            logger.info(f"✅ Exported CSV report to {output_path}")
        
        return csv_str


class LedgerConsumer:
    """Consumer that listens to order events and updates ledger"""
    
    def __init__(self, worker_name: str = "ledger_consumer"):
        self.worker_name = worker_name
        self.ledger = DailyLedger()
        self.consumer_group = "ledger_consumer"
        self.consumer_name = f"{worker_name}_{int(time.time())}"
        self.running = False
    
    def connect(self):
        """Connect and create consumer group"""
        try:
            self.ledger.event_log.create_consumer_group("orders", self.consumer_group)
            logger.info(f"✅ [{self.worker_name}] Connected")
            return True
        except Exception as e:
            logger.warning(f"⚠️ [{self.worker_name}] Consumer group warning: {e}")
            return True  # Group may already exist
    
    def process_order_event(self, event_data: Dict[str, str]):
        """Process order event and record fills"""
        try:
            from app.event_driven.contracts.events import OrderEvent
            # event_data is already a dict from Redis Stream
            event = OrderEvent.from_redis_stream(event_data)
            
            # Only record fills
            if event.data.get("action") in ["FILLED", "PARTIAL_FILL"]:
                self.ledger.record_fill(event)
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error processing order event: {e}", exc_info=True)
    
    def run(self):
        """Main loop - consume order events"""
        import time
        
        try:
            if not self.connect():
                return
            
            self.running = True
            logger.info(f"✅ [{self.worker_name}] Started")
            
            while self.running:
                try:
                    messages = self.ledger.event_log.read(
                        "orders", self.consumer_group, self.consumer_name,
                        count=10, block=1000
                    )
                    
                    for msg in messages:
                        self.process_order_event(msg["data"])
                        self.ledger.event_log.ack("orders", self.consumer_group, msg["message_id"])
                
                except Exception as e:
                    logger.error(f"❌ [{self.worker_name}] Error: {e}", exc_info=True)
                    time.sleep(1)
        
        except KeyboardInterrupt:
            logger.info(f"🛑 [{self.worker_name}] Stopped")
        finally:
            self.running = False

