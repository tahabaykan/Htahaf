"""
Regime Transition Logger

Logs regime/mode transitions with timestamps for PM autopsy analysis.
"""

import time
from datetime import date, datetime
from typing import Dict, Any, Optional, List
from app.core.logger import logger
from app.core.redis_client import get_redis_client


class RegimeTransitionLogger:
    """Logs regime and decision mode transitions"""
    
    def __init__(self):
        redis_client = get_redis_client().sync
        if not redis_client:
            raise RuntimeError("Redis client not available")
        
        self.redis = redis_client
        self.transition_key_prefix = "risk:transitions"
    
    def get_transition_key(self, target_date: Optional[date] = None) -> str:
        """Get Redis key for regime transitions"""
        if target_date is None:
            target_date = date.today()
        date_str = target_date.isoformat()
        return f"{self.transition_key_prefix}:{date_str}"
    
    def log_regime_transition(
        self,
        from_regime: str,
        to_regime: str,
        reason: str,
        exposure_data: Optional[Dict[str, Any]] = None,
        target_date: Optional[date] = None
    ):
        """
        Log a regime transition
        
        Args:
            from_regime: Previous regime (e.g., "OPEN", "MID", "LATE")
            to_regime: New regime
            reason: Reason for transition
            exposure_data: Optional exposure data at transition time
            target_date: Date for log entry (default: today)
        """
        try:
            timestamp_ns = time.time_ns()
            timestamp = timestamp_ns / 1e9
            
            transition = {
                "timestamp": timestamp,
                "timestamp_ns": timestamp_ns,
                "datetime": datetime.fromtimestamp(timestamp).isoformat(),
                "type": "regime_transition",
                "from_regime": from_regime,
                "to_regime": to_regime,
                "reason": reason,
            }
            
            # Add exposure context if provided
            if exposure_data:
                transition["gross_exposure_pct"] = exposure_data.get("gross_exposure_pct", 0.0)
                transition["lt_current_pct"] = exposure_data.get("buckets", {}).get("LT", {}).get("current_pct", 0.0)
                transition["mm_current_pct"] = exposure_data.get("buckets", {}).get("MM_PURE", {}).get("current_pct", 0.0)
            
            # Store in Redis Sorted Set
            transition_key = self.get_transition_key(target_date)
            import json
            transition_json = json.dumps(transition)
            self.redis.zadd(transition_key, {transition_json: timestamp_ns})
            
            logger.info(
                f"🔄 [RegimeTransition] {from_regime} → {to_regime}: {reason}"
            )
        
        except Exception as e:
            logger.error(f"❌ [RegimeTransition] Error logging transition: {e}", exc_info=True)
    
    def log_mode_transition(
        self,
        from_mode: str,
        to_mode: str,
        reason: str,
        exposure_data: Optional[Dict[str, Any]] = None,
        target_date: Optional[date] = None
    ):
        """
        Log a decision mode transition (NORMAL, SOFT_DERISK, HARD_DERISK, etc.)
        
        Args:
            from_mode: Previous mode
            to_mode: New mode
            reason: Reason for transition
            exposure_data: Optional exposure data at transition time
            target_date: Date for log entry (default: today)
        """
        try:
            timestamp_ns = time.time_ns()
            timestamp = timestamp_ns / 1e9
            
            transition = {
                "timestamp": timestamp,
                "timestamp_ns": timestamp_ns,
                "datetime": datetime.fromtimestamp(timestamp).isoformat(),
                "type": "mode_transition",
                "from_mode": from_mode,
                "to_mode": to_mode,
                "reason": reason,
            }
            
            # Add exposure context if provided
            if exposure_data:
                transition["gross_exposure_pct"] = exposure_data.get("gross_exposure_pct", 0.0)
                transition["lt_current_pct"] = exposure_data.get("buckets", {}).get("LT", {}).get("current_pct", 0.0)
                transition["mm_current_pct"] = exposure_data.get("buckets", {}).get("MM_PURE", {}).get("current_pct", 0.0)
            
            # Store in Redis Sorted Set
            transition_key = self.get_transition_key(target_date)
            import json
            transition_json = json.dumps(transition)
            self.redis.zadd(transition_key, {transition_json: timestamp_ns})
            
            logger.info(
                f"🔄 [ModeTransition] {from_mode} → {to_mode}: {reason}"
            )
        
        except Exception as e:
            logger.error(f"❌ [ModeTransition] Error logging transition: {e}", exc_info=True)
    
    def get_transitions(
        self,
        target_date: Optional[date] = None,
        transition_type: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Get regime/mode transitions
        
        Args:
            target_date: Date to query (default: today)
            transition_type: Filter by type ("regime_transition" or "mode_transition") - optional
            start_time: Start timestamp (Unix seconds) - optional
            end_time: End timestamp (Unix seconds) - optional
        
        Returns:
            List of transition dicts, sorted by timestamp
        """
        try:
            transition_key = self.get_transition_key(target_date)
            
            # Convert to nanoseconds
            start_ns = int(start_time * 1e9) if start_time else None
            end_ns = int(end_time * 1e9) if end_time else None
            
            # Query sorted set
            if start_ns and end_ns:
                members = self.redis.zrangebyscore(
                    transition_key, start_ns, end_ns,
                    withscores=False
                )
            else:
                members = self.redis.zrange(transition_key, 0, -1)
            
            # Parse JSON
            import json
            transitions = []
            for member in members:
                try:
                    transition = json.loads(member)
                    # Filter by type if specified
                    if transition_type and transition.get("type") != transition_type:
                        continue
                    transitions.append(transition)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ [RegimeTransition] Error parsing transition: {e}")
                    continue
            
            return transitions
        
        except Exception as e:
            logger.error(f"❌ [RegimeTransition] Error getting transitions: {e}", exc_info=True)
            return []



