"""
Exposure Worker

Publishes exposure snapshots every 15 seconds.
Currently uses mock position data (Sprint 1).
"""

import time
import signal
from typing import Dict, Any, Optional
from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.event_driven.state.event_log import EventLog
from app.event_driven.contracts.events import ExposureEvent
from app.event_driven.baseline.befday_snapshot import BefDaySnapshot
from app.event_driven.reporting.risk_timeline_tracker import RiskTimelineTracker
from datetime import date


class ExposureWorker:
    """Worker that publishes exposure snapshots"""
    
    def __init__(self, worker_name: str = "exposure_worker"):
        self.worker_name = worker_name
        self.running = False
        self.event_log: Optional[EventLog] = None
        self.publish_interval = 15.0  # 15 seconds
        self.befday_snapshot: Optional[BefDaySnapshot] = None
        self.risk_timeline: Optional[RiskTimelineTracker] = None
        
        # Account ID (default: HAMMER)
        self.account_id = "HAMMER"
        
        # Mock data for testing
        self.mock_equity = 1000000.0  # $1M equity
        # Mock positions with group assignments (22 groups)
        self.mock_positions = [
            {"symbol": "AAPL", "quantity": 100, "avg_price": 150.0, "notional": 15000.0, "group": "group_1", "bucket": "LT"},
            {"symbol": "MSFT", "quantity": -50, "avg_price": 300.0, "notional": 15000.0, "group": "group_2", "bucket": "LT"},
            {"symbol": "GOOGL", "quantity": 200, "avg_price": 100.0, "notional": 20000.0, "group": "group_3", "bucket": "MM_PURE"},
        ]
        
        # Mock group mapping (22 groups)
        self.group_names = [f"group_{i}" for i in range(1, 23)]
    
    def connect(self):
        """Connect to Redis"""
        try:
            redis_client = get_redis_client().sync
            if not redis_client:
                raise RuntimeError("Redis client not available")
            
            self.event_log = EventLog(redis_client=redis_client)
            self.befday_snapshot = BefDaySnapshot()
            self.risk_timeline = RiskTimelineTracker()
            logger.info(f"✅ [{self.worker_name}] Connected to Redis")
            return True
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Failed to connect: {e}", exc_info=True)
            return False
    
    def _enrich_positions_with_befday(self, positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich positions with BefDay baseline data"""
        enriched = []
        snapshot_date = date.today()
        
        for pos in positions:
            symbol = pos.get("symbol", "UNKNOWN")
            current_qty = pos.get("quantity", 0)
            
            # Get BefDay entry
            befday_entry = self.befday_snapshot.get_befday_entry(
                self.account_id, symbol, snapshot_date
            )
            
            if befday_entry:
                befday_qty = befday_entry.get("befday_qty", 0)
                befday_cost = befday_entry.get("befday_cost", 0.0)
            else:
                # No BefDay entry (position opened today or snapshot not taken)
                befday_qty = 0
                befday_cost = pos.get("avg_price", 0.0)  # Use current avg_price as fallback
            
            # Calculate intraday delta
            intraday_qty_delta = current_qty - befday_qty
            
            # For intraday avg fill price, we'd need to track today's fills
            # For now, use current avg_price if there's intraday activity
            intraday_avg_fill_price = None
            if intraday_qty_delta != 0:
                intraday_avg_fill_price = pos.get("avg_price", 0.0)  # Stub: use current avg
            
            # Enrich position
            enriched_pos = pos.copy()
            enriched_pos.update({
                "befday_qty": befday_qty,
                "befday_cost": befday_cost,
                "intraday_qty_delta": intraday_qty_delta,
                "intraday_avg_fill_price": intraday_avg_fill_price,
                "account_id": self.account_id,
            })
            enriched.append(enriched_pos)
        
        return enriched
    
    def _calculate_exposure(self) -> Dict[str, Any]:
        """Calculate full exposure breakdown from positions"""
        # Enrich positions with BefDay data
        enriched_positions = self._enrich_positions_with_befday(self.mock_positions)
        
        # Calculate current exposure
        long_notional = sum(p["notional"] for p in enriched_positions if p["quantity"] > 0)
        short_notional = abs(sum(p["notional"] for p in enriched_positions if p["quantity"] < 0))
        
        gross_exposure = long_notional + short_notional
        net_exposure = long_notional - short_notional
        
        gross_exposure_pct = (gross_exposure / self.mock_equity) * 100.0
        net_exposure_pct = (net_exposure / self.mock_equity) * 100.0
        long_gross_pct = (long_notional / self.mock_equity) * 100.0
        short_gross_pct = (short_notional / self.mock_equity) * 100.0
        
        # Calculate bucket exposure (current and potential)
        lt_positions = [p for p in self.mock_positions if p.get("bucket") == "LT"]
        mm_positions = [p for p in self.mock_positions if p.get("bucket") == "MM_PURE"]
        
        lt_current = sum(abs(p["notional"]) for p in lt_positions)
        mm_current = sum(abs(p["notional"]) for p in mm_positions)
        
        # Potential exposure (current + open orders - stub for now)
        # In real system, this would include pending orders
        open_orders_potential = 0.0  # Will be updated when Execution Service tracks orders
        
        lt_potential = lt_current + (open_orders_potential * 0.8)  # Assume 80% of orders go to LT
        mm_potential = mm_current + (open_orders_potential * 0.2)  # 20% to MM
        
        buckets = {
            "LT": {
                "current": lt_current,
                "current_pct": (lt_current / self.mock_equity) * 100.0,
                "potential": lt_potential,
                "potential_pct": (lt_potential / self.mock_equity) * 100.0,
                "target": self.mock_equity * 0.8,
                "target_pct": 80.0,
                "max": self.mock_equity * 0.9,
                "max_pct": 90.0,
            },
            "MM_PURE": {
                "current": mm_current,
                "current_pct": (mm_current / self.mock_equity) * 100.0,
                "potential": mm_potential,
                "potential_pct": (mm_potential / self.mock_equity) * 100.0,
                "target": self.mock_equity * 0.2,
                "target_pct": 20.0,
                "max": self.mock_equity * 0.3,
                "max_pct": 30.0,
            }
        }
        
        # Calculate per-group exposure (22 groups)
        group_exposure = {}
        for group_name in self.group_names:
            group_positions = [p for p in self.mock_positions if p.get("group") == group_name]
            group_notional = sum(abs(p["notional"]) for p in group_positions)
            group_exposure[group_name] = (group_notional / self.mock_equity) * 100.0
        
        return {
            "equity": self.mock_equity,
            "long_notional": long_notional,
            "short_notional": short_notional,
            "gross_exposure_pct": gross_exposure_pct,
            "net_exposure_pct": net_exposure_pct,
            "long_gross_pct": long_gross_pct,
            "short_gross_pct": short_gross_pct,
            "buckets": buckets,
            "group_exposure": group_exposure,
            "positions": enriched_positions,  # Use enriched positions with BefDay data
            "open_orders_potential": open_orders_potential,
        }
    
    def publish_exposure(self):
        """Publish exposure snapshot"""
        try:
            exposure_data = self._calculate_exposure()
            
            event = ExposureEvent.create(
                equity=exposure_data["equity"],
                long_notional=exposure_data["long_notional"],
                short_notional=exposure_data["short_notional"],
                gross_exposure_pct=exposure_data["gross_exposure_pct"],
                net_exposure_pct=exposure_data["net_exposure_pct"],
                long_gross_pct=exposure_data["long_gross_pct"],
                short_gross_pct=exposure_data["short_gross_pct"],
                buckets=exposure_data["buckets"],
                group_exposure=exposure_data["group_exposure"],
                positions=exposure_data["positions"],
                open_orders_potential=exposure_data["open_orders_potential"],
            )
            
            msg_id = self.event_log.publish("exposure", event)
            if msg_id:
                logger.info(
                    f"📊 [{self.worker_name}] Published exposure: "
                    f"gross={exposure_data['gross_exposure_pct']:.2f}%, "
                    f"LT={exposure_data['buckets']['LT']['current_pct']:.2f}%, "
                    f"MM={exposure_data['buckets']['MM_PURE']['current_pct']:.2f}%"
                )
                
                # Record risk timeline snapshot
                if self.risk_timeline:
                    try:
                        # Get session and decision state (if available)
                        from app.event_driven.state.store import StateStore
                        state_store = StateStore(redis_client=get_redis_client().sync)
                        session_data = state_store.get_state("session")
                        decision_data = state_store.get_state("decision")
                        
                        self.risk_timeline.record_snapshot(
                            exposure_data=exposure_data,
                            session_data=session_data,
                            decision_data=decision_data
                        )
                    except Exception as e:
                        logger.warning(f"⚠️ [{self.worker_name}] Failed to record risk timeline: {e}")
            else:
                logger.warning(f"⚠️ [{self.worker_name}] Failed to publish exposure")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error publishing exposure: {e}", exc_info=True)
    
    def run(self):
        """Main worker loop"""
        try:
            logger.info(f"🚀 [{self.worker_name}] Starting...")
            
            if not self.connect():
                logger.error(f"❌ [{self.worker_name}] Cannot start: connection failed")
                return
            
            self.running = True
            logger.info(f"✅ [{self.worker_name}] Started (publish interval: {self.publish_interval}s)")
            
            # Publish immediately on start
            self.publish_exposure()
            
            # Main loop
            while self.running:
                time.sleep(self.publish_interval)
                if self.running:
                    self.publish_exposure()
        
        except KeyboardInterrupt:
            logger.info(f"🛑 [{self.worker_name}] Stopped by user")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error: {e}", exc_info=True)
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        self.running = False
        logger.info(f"✅ [{self.worker_name}] Cleanup completed")


def main():
    """Main entry point"""
    worker = ExposureWorker()
    
    def signal_handler(sig, frame):
        logger.info(f"🛑 [{worker.worker_name}] Received SIGINT, shutting down...")
        worker.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    worker.run()


if __name__ == "__main__":
    main()

