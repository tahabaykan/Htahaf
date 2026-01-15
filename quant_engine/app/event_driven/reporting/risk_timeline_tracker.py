"""
Risk Timeline Tracker

Tracks intraday risk snapshots over time:
- Gross exposure (current, potential)
- LT/MM bucket breakdown
- Regime (time-based)
- Timestamps for time-series analysis
"""

import time
from datetime import date, datetime
from typing import Dict, Any, Optional, List
from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.event_driven.state.store import StateStore


class RiskTimelineTracker:
    """Tracks risk timeline snapshots throughout the day"""
    
    def __init__(self):
        redis_client = get_redis_client().sync
        if not redis_client:
            raise RuntimeError("Redis client not available")
        
        self.state_store = StateStore(redis_client=redis_client)
        self.timeline_key_prefix = "risk:timeline"
        self.max_snapshots_per_day = 10000  # Limit to prevent memory issues
    
    def get_timeline_key(self, target_date: Optional[date] = None) -> str:
        """Get Redis key for risk timeline"""
        if target_date is None:
            target_date = date.today()
        date_str = target_date.isoformat()
        return f"{self.timeline_key_prefix}:{date_str}"
    
    def record_snapshot(
        self,
        exposure_data: Dict[str, Any],
        session_data: Optional[Dict[str, Any]] = None,
        decision_data: Optional[Dict[str, Any]] = None,
        target_date: Optional[date] = None
    ):
        """
        Record a risk timeline snapshot
        
        Args:
            exposure_data: Exposure event data (from ExposureEvent)
            session_data: Session event data (from SessionEvent) - optional
            decision_data: Decision engine state (mode, reason) - optional
            target_date: Date for snapshot (default: today)
        """
        try:
            timestamp_ns = time.time_ns()
            timestamp = timestamp_ns / 1e9  # Unix timestamp (seconds)
            
            # Extract key metrics
            gross_exposure_pct = exposure_data.get("gross_exposure_pct", 0.0)
            net_exposure_pct = exposure_data.get("net_exposure_pct", 0.0)
            long_gross_pct = exposure_data.get("long_gross_pct", 0.0)
            short_gross_pct = exposure_data.get("short_gross_pct", 0.0)
            
            buckets = exposure_data.get("buckets", {})
            lt_bucket = buckets.get("LT", {})
            mm_bucket = buckets.get("MM_PURE", {})
            
            lt_current_pct = lt_bucket.get("current_pct", 0.0)
            lt_potential_pct = lt_bucket.get("potential_pct", 0.0)
            mm_current_pct = mm_bucket.get("current_pct", 0.0)
            mm_potential_pct = mm_bucket.get("potential_pct", 0.0)
            
            # Get regime from session data
            regime = session_data.get("regime", "UNKNOWN") if session_data else "UNKNOWN"
            minutes_to_close = session_data.get("minutes_to_close") if session_data else None
            
            # Get decision mode
            decision_mode = decision_data.get("mode", "NORMAL") if decision_data else "NORMAL"
            decision_reason = decision_data.get("reason", "") if decision_data else ""
            
            # Create snapshot
            snapshot = {
                "timestamp": timestamp,
                "timestamp_ns": timestamp_ns,
                "datetime": datetime.fromtimestamp(timestamp).isoformat(),
                
                # Gross exposure metrics
                "gross_exposure_pct": gross_exposure_pct,
                "net_exposure_pct": net_exposure_pct,
                "long_gross_pct": long_gross_pct,
                "short_gross_pct": short_gross_pct,
                
                # Bucket breakdown
                "lt_current_pct": lt_current_pct,
                "lt_potential_pct": lt_potential_pct,
                "mm_current_pct": mm_current_pct,
                "mm_potential_pct": mm_potential_pct,
                
                # Regime and decision
                "regime": regime,
                "minutes_to_close": minutes_to_close,
                "decision_mode": decision_mode,
                "decision_reason": decision_reason,
                
                # Additional context
                "equity": exposure_data.get("equity", 0.0),
                "open_orders_potential": exposure_data.get("open_orders_potential", 0.0),
            }
            
            # Store in Redis Sorted Set (timestamp as score for time-series queries)
            timeline_key = self.get_timeline_key(target_date)
            
            # Use Redis Sorted Set for time-series data
            # Score = timestamp_ns (for precise ordering)
            # Member = JSON-encoded snapshot
            import json
            snapshot_json = json.dumps(snapshot)
            
            redis_client = get_redis_client().sync
            redis_client.zadd(timeline_key, {snapshot_json: timestamp_ns})
            
            # Limit size (keep last N snapshots)
            count = redis_client.zcard(timeline_key)
            if count > self.max_snapshots_per_day:
                # Remove oldest snapshots
                redis_client.zremrangebyrank(timeline_key, 0, count - self.max_snapshots_per_day)
            
            logger.debug(
                f"📊 [RiskTimeline] Snapshot recorded: "
                f"gross={gross_exposure_pct:.2f}%, regime={regime}, mode={decision_mode}"
            )
        
        except Exception as e:
            logger.error(f"❌ [RiskTimeline] Error recording snapshot: {e}", exc_info=True)
    
    def get_timeline(
        self,
        target_date: Optional[date] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get risk timeline snapshots
        
        Args:
            target_date: Date to query (default: today)
            start_time: Start timestamp (Unix seconds) - optional
            end_time: End timestamp (Unix seconds) - optional
            limit: Maximum number of snapshots to return - optional
        
        Returns:
            List of snapshot dicts, sorted by timestamp
        """
        try:
            timeline_key = self.get_timeline_key(target_date)
            redis_client = get_redis_client().sync
            
            # Convert to nanoseconds for Redis query
            start_ns = int(start_time * 1e9) if start_time else None
            end_ns = int(end_time * 1e9) if end_time else None
            
            # Query sorted set
            if start_ns and end_ns:
                # Range query
                members = redis_client.zrangebyscore(
                    timeline_key, start_ns, end_ns,
                    withscores=False
                )
            else:
                # Get all (or last N)
                if limit:
                    # Get last N snapshots
                    members = redis_client.zrange(timeline_key, -limit, -1)
                else:
                    members = redis_client.zrange(timeline_key, 0, -1)
            
            # Parse JSON snapshots
            import json
            snapshots = []
            for member in members:
                try:
                    snapshot = json.loads(member)
                    snapshots.append(snapshot)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ [RiskTimeline] Error parsing snapshot: {e}")
                    continue
            
            return snapshots
        
        except Exception as e:
            logger.error(f"❌ [RiskTimeline] Error getting timeline: {e}", exc_info=True)
            return []
    
    def get_summary_stats(
        self,
        target_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Get summary statistics for the day
        
        Returns:
            Dict with min/max/avg gross exposure, regime distribution, etc.
        """
        try:
            snapshots = self.get_timeline(target_date)
            
            if not snapshots:
                return {
                    "date": target_date.isoformat() if target_date else date.today().isoformat(),
                    "snapshot_count": 0,
                }
            
            # Extract metrics
            gross_exposures = [s.get("gross_exposure_pct", 0.0) for s in snapshots]
            lt_currents = [s.get("lt_current_pct", 0.0) for s in snapshots]
            mm_currents = [s.get("mm_current_pct", 0.0) for s in snapshots]
            regimes = [s.get("regime", "UNKNOWN") for s in snapshots]
            modes = [s.get("decision_mode", "NORMAL") for s in snapshots]
            
            # Calculate stats
            from collections import Counter
            
            return {
                "date": target_date.isoformat() if target_date else date.today().isoformat(),
                "snapshot_count": len(snapshots),
                "gross_exposure": {
                    "min": min(gross_exposures) if gross_exposures else 0.0,
                    "max": max(gross_exposures) if gross_exposures else 0.0,
                    "avg": sum(gross_exposures) / len(gross_exposures) if gross_exposures else 0.0,
                },
                "lt_current": {
                    "min": min(lt_currents) if lt_currents else 0.0,
                    "max": max(lt_currents) if lt_currents else 0.0,
                    "avg": sum(lt_currents) / len(lt_currents) if lt_currents else 0.0,
                },
                "mm_current": {
                    "min": min(mm_currents) if mm_currents else 0.0,
                    "max": max(mm_currents) if mm_currents else 0.0,
                    "avg": sum(mm_currents) / len(mm_currents) if mm_currents else 0.0,
                },
                "regime_distribution": dict(Counter(regimes)),
                "mode_distribution": dict(Counter(modes)),
            }
        
        except Exception as e:
            logger.error(f"❌ [RiskTimeline] Error getting summary stats: {e}", exc_info=True)
            return {}



