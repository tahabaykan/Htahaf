"""
Intent Arbitration Tracker

Tracks intent arbitration decisions:
- Accepted vs suppressed intents
- Reasons for suppression
- Intent type breakdown
"""

import time
from datetime import date, datetime
from typing import Dict, Any, Optional, List
from collections import defaultdict
from app.core.logger import logger
from app.core.redis_client import get_redis_client


class IntentArbitrationTracker:
    """Tracks intent arbitration decisions"""
    
    def __init__(self):
        redis_client = get_redis_client().sync
        if not redis_client:
            raise RuntimeError("Redis client not available")
        
        self.redis = redis_client
        self.arbitration_key_prefix = "risk:intent_arbitration"
    
    def get_arbitration_key(self, target_date: Optional[date] = None) -> str:
        """Get Redis key for intent arbitration logs"""
        if target_date is None:
            target_date = date.today()
        date_str = target_date.isoformat()
        return f"{self.arbitration_key_prefix}:{date_str}"
    
    def log_arbitration(
        self,
        input_intents: List[Dict[str, Any]],
        output_intents: List[Dict[str, Any]],
        current_gross_exposure_pct: float,
        current_mode: str,
        suppression_reasons: Optional[Dict[str, str]] = None,
        target_date: Optional[date] = None
    ):
        """
        Log an intent arbitration decision
        
        Args:
            input_intents: Original intents before arbitration
            output_intents: Intents after arbitration (accepted)
            current_gross_exposure_pct: Current gross exposure
            current_mode: Current decision mode
            suppression_reasons: Dict mapping intent_id -> reason for suppression
            target_date: Date for log entry (default: today)
        """
        try:
            timestamp_ns = time.time_ns()
            timestamp = timestamp_ns / 1e9
            
            # Calculate statistics
            input_count = len(input_intents)
            output_count = len(output_intents)
            suppressed_count = input_count - output_count
            
            # Group by intent type
            input_by_type = defaultdict(int)
            output_by_type = defaultdict(int)
            
            for intent in input_intents:
                intent_type = intent.get("intent_type", "UNKNOWN")
                input_by_type[intent_type] += 1
            
            for intent in output_intents:
                intent_type = intent.get("intent_type", "UNKNOWN")
                output_by_type[intent_type] += 1
            
            # Group by classification
            input_by_class = defaultdict(int)
            output_by_class = defaultdict(int)
            
            for intent in input_intents:
                classification = intent.get("classification", "UNKNOWN")
                input_by_class[classification] += 1
            
            for intent in output_intents:
                classification = intent.get("classification", "UNKNOWN")
                output_by_class[classification] += 1
            
            # Create log entry
            log_entry = {
                "timestamp": timestamp,
                "timestamp_ns": timestamp_ns,
                "datetime": datetime.fromtimestamp(timestamp).isoformat(),
                "input_count": input_count,
                "output_count": output_count,
                "suppressed_count": suppressed_count,
                "current_gross_exposure_pct": current_gross_exposure_pct,
                "current_mode": current_mode,
                "input_by_type": dict(input_by_type),
                "output_by_type": dict(output_by_type),
                "input_by_classification": dict(input_by_class),
                "output_by_classification": dict(output_by_class),
                "suppression_reasons": suppression_reasons or {},
            }
            
            # Store in Redis Sorted Set
            arbitration_key = self.get_arbitration_key(target_date)
            import json
            log_json = json.dumps(log_entry)
            self.redis.zadd(arbitration_key, {log_json: timestamp_ns})
            
            logger.debug(
                f"📊 [IntentArbitration] {input_count} → {output_count} intents "
                f"(suppressed: {suppressed_count})"
            )
        
        except Exception as e:
            logger.error(f"❌ [IntentArbitration] Error logging arbitration: {e}", exc_info=True)
    
    def get_arbitration_logs(
        self,
        target_date: Optional[date] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Get intent arbitration logs
        
        Args:
            target_date: Date to query (default: today)
            start_time: Start timestamp (Unix seconds) - optional
            end_time: End timestamp (Unix seconds) - optional
        
        Returns:
            List of arbitration log dicts, sorted by timestamp
        """
        try:
            arbitration_key = self.get_arbitration_key(target_date)
            
            # Convert to nanoseconds
            start_ns = int(start_time * 1e9) if start_time else None
            end_ns = int(end_time * 1e9) if end_time else None
            
            # Query sorted set
            if start_ns and end_ns:
                members = self.redis.zrangebyscore(
                    arbitration_key, start_ns, end_ns,
                    withscores=False
                )
            else:
                members = self.redis.zrange(arbitration_key, 0, -1)
            
            # Parse JSON
            import json
            logs = []
            for member in members:
                try:
                    log = json.loads(member)
                    logs.append(log)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ [IntentArbitration] Error parsing log: {e}")
                    continue
            
            return logs
        
        except Exception as e:
            logger.error(f"❌ [IntentArbitration] Error getting logs: {e}", exc_info=True)
            return []
    
    def get_summary(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Get summary statistics for intent arbitration
        
        Returns:
            Dict with total input/output/suppressed counts, breakdowns, etc.
        """
        try:
            logs = self.get_arbitration_logs(target_date)
            
            if not logs:
                return {
                    "date": target_date.isoformat() if target_date else date.today().isoformat(),
                    "arbitration_count": 0,
                }
            
            # Aggregate statistics
            total_input = sum(log.get("input_count", 0) for log in logs)
            total_output = sum(log.get("output_count", 0) for log in logs)
            total_suppressed = sum(log.get("suppressed_count", 0) for log in logs)
            
            # Aggregate by type
            input_by_type = defaultdict(int)
            output_by_type = defaultdict(int)
            
            for log in logs:
                for intent_type, count in log.get("input_by_type", {}).items():
                    input_by_type[intent_type] += count
                for intent_type, count in log.get("output_by_type", {}).items():
                    output_by_type[intent_type] += count
            
            # Aggregate by classification
            input_by_class = defaultdict(int)
            output_by_class = defaultdict(int)
            
            for log in logs:
                for classification, count in log.get("input_by_classification", {}).items():
                    input_by_class[classification] += count
                for classification, count in log.get("output_by_classification", {}).items():
                    output_by_class[classification] += count
            
            return {
                "date": target_date.isoformat() if target_date else date.today().isoformat(),
                "arbitration_count": len(logs),
                "total_input_intents": total_input,
                "total_output_intents": total_output,
                "total_suppressed_intents": total_suppressed,
                "suppression_rate": (total_suppressed / total_input * 100.0) if total_input > 0 else 0.0,
                "input_by_type": dict(input_by_type),
                "output_by_type": dict(output_by_type),
                "input_by_classification": dict(input_by_class),
                "output_by_classification": dict(output_by_class),
            }
        
        except Exception as e:
            logger.error(f"❌ [IntentArbitration] Error getting summary: {e}", exc_info=True)
            return {}



