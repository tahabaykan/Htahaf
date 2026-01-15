"""
CAP_RECOVERY Tracker

Tracks CAP_RECOVERY episodes:
- Start/end timestamps
- Duration
- Exposure change (before/after)
- Number of intents generated
"""

import time
from datetime import date, datetime
from typing import Dict, Any, Optional, List
from app.core.logger import logger
from app.core.redis_client import get_redis_client


class CapRecoveryTracker:
    """Tracks CAP_RECOVERY episodes"""
    
    def __init__(self):
        redis_client = get_redis_client().sync
        if not redis_client:
            raise RuntimeError("Redis client not available")
        
        self.redis = redis_client
        self.episode_key_prefix = "risk:cap_recovery:episodes"
        self.active_episode_key = "risk:cap_recovery:active"
    
    def get_episode_key(self, target_date: Optional[date] = None) -> str:
        """Get Redis key for CAP_RECOVERY episodes"""
        if target_date is None:
            target_date = date.today()
        date_str = target_date.isoformat()
        return f"{self.episode_key_prefix}:{date_str}"
    
    def start_episode(
        self,
        gross_exposure_pct: float,
        exposure_data: Optional[Dict[str, Any]] = None,
        target_date: Optional[date] = None
    ) -> Optional[str]:
        """
        Start a new CAP_RECOVERY episode
        
        Args:
            gross_exposure_pct: Gross exposure at start
            exposure_data: Optional full exposure data
            target_date: Date for episode (default: today)
        
        Returns:
            Episode ID if started, None if already active
        """
        try:
            # Check if already active
            active_episode = self.get_active_episode()
            if active_episode:
                logger.debug(f"⚠️ [CapRecovery] Episode already active: {active_episode}")
                return None
            
            timestamp_ns = time.time_ns()
            timestamp = timestamp_ns / 1e9
            episode_id = f"ep_{int(timestamp_ns)}"
            
            episode = {
                "episode_id": episode_id,
                "start_timestamp": timestamp,
                "start_timestamp_ns": timestamp_ns,
                "start_datetime": datetime.fromtimestamp(timestamp).isoformat(),
                "start_gross_exposure_pct": gross_exposure_pct,
                "end_timestamp": None,
                "end_datetime": None,
                "end_gross_exposure_pct": None,
                "duration_seconds": None,
                "exposure_reduction_pct": None,
                "status": "active",
            }
            
            # Add exposure context
            if exposure_data:
                episode["start_lt_pct"] = exposure_data.get("buckets", {}).get("LT", {}).get("current_pct", 0.0)
                episode["start_mm_pct"] = exposure_data.get("buckets", {}).get("MM_PURE", {}).get("current_pct", 0.0)
            
            # Store active episode
            import json
            self.redis.set(
                self.active_episode_key,
                json.dumps(episode),
                ex=86400  # Expire after 24 hours
            )
            
            # Add to episodes list
            episode_key = self.get_episode_key(target_date)
            episode_json = json.dumps(episode)
            self.redis.zadd(episode_key, {episode_json: timestamp_ns})
            
            logger.warning(
                f"🚨 [CapRecovery] Episode STARTED: {episode_id} "
                f"(gross={gross_exposure_pct:.2f}%)"
            )
            
            return episode_id
        
        except Exception as e:
            logger.error(f"❌ [CapRecovery] Error starting episode: {e}", exc_info=True)
            return None
    
    def end_episode(
        self,
        gross_exposure_pct: float,
        exposure_data: Optional[Dict[str, Any]] = None,
        target_date: Optional[date] = None
    ) -> Optional[str]:
        """
        End the active CAP_RECOVERY episode
        
        Args:
            gross_exposure_pct: Gross exposure at end
            exposure_data: Optional full exposure data
            target_date: Date for episode (default: today)
        
        Returns:
            Episode ID if ended, None if no active episode
        """
        try:
            # Get active episode
            active_episode = self.get_active_episode()
            if not active_episode:
                logger.debug("⚠️ [CapRecovery] No active episode to end")
                return None
            
            episode_id = active_episode.get("episode_id")
            start_timestamp = active_episode.get("start_timestamp")
            
            timestamp_ns = time.time_ns()
            timestamp = timestamp_ns / 1e9
            
            # Calculate duration and exposure change
            duration_seconds = timestamp - start_timestamp if start_timestamp else None
            start_gross = active_episode.get("start_gross_exposure_pct", 0.0)
            exposure_reduction_pct = start_gross - gross_exposure_pct
            
            # Update episode
            active_episode["end_timestamp"] = timestamp
            active_episode["end_timestamp_ns"] = timestamp_ns
            active_episode["end_datetime"] = datetime.fromtimestamp(timestamp).isoformat()
            active_episode["end_gross_exposure_pct"] = gross_exposure_pct
            active_episode["duration_seconds"] = duration_seconds
            active_episode["exposure_reduction_pct"] = exposure_reduction_pct
            active_episode["status"] = "completed"
            
            # Add end exposure context
            if exposure_data:
                active_episode["end_lt_pct"] = exposure_data.get("buckets", {}).get("LT", {}).get("current_pct", 0.0)
                active_episode["end_mm_pct"] = exposure_data.get("buckets", {}).get("MM_PURE", {}).get("current_pct", 0.0)
            
            # Update in episodes list
            import json
            episode_key = self.get_episode_key(target_date)
            episode_json = json.dumps(active_episode)
            self.redis.zadd(episode_key, {episode_json: active_episode.get("start_timestamp_ns", timestamp_ns)})
            
            # Remove active episode
            self.redis.delete(self.active_episode_key)
            
            logger.info(
                f"✅ [CapRecovery] Episode ENDED: {episode_id} "
                f"(duration={duration_seconds:.1f}s, reduction={exposure_reduction_pct:.2f}%)"
            )
            
            return episode_id
        
        except Exception as e:
            logger.error(f"❌ [CapRecovery] Error ending episode: {e}", exc_info=True)
            return None
    
    def get_active_episode(self) -> Optional[Dict[str, Any]]:
        """Get currently active CAP_RECOVERY episode"""
        try:
            import json
            active_json = self.redis.get(self.active_episode_key)
            if not active_json:
                return None
            return json.loads(active_json)
        except Exception as e:
            logger.error(f"❌ [CapRecovery] Error getting active episode: {e}", exc_info=True)
            return None
    
    def get_episodes(
        self,
        target_date: Optional[date] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all CAP_RECOVERY episodes for a date
        
        Args:
            target_date: Date to query (default: today)
            status: Filter by status ("active" or "completed") - optional
        
        Returns:
            List of episode dicts, sorted by start timestamp
        """
        try:
            episode_key = self.get_episode_key(target_date)
            members = self.redis.zrange(episode_key, 0, -1)
            
            import json
            episodes = []
            for member in members:
                try:
                    episode = json.loads(member)
                    # Filter by status if specified
                    if status and episode.get("status") != status:
                        continue
                    episodes.append(episode)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ [CapRecovery] Error parsing episode: {e}")
                    continue
            
            return episodes
        
        except Exception as e:
            logger.error(f"❌ [CapRecovery] Error getting episodes: {e}", exc_info=True)
            return []
    
    def get_summary(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """
        Get summary statistics for CAP_RECOVERY episodes
        
        Returns:
            Dict with episode count, total duration, avg reduction, etc.
        """
        try:
            episodes = self.get_episodes(target_date, status="completed")
            
            if not episodes:
                return {
                    "date": target_date.isoformat() if target_date else date.today().isoformat(),
                    "episode_count": 0,
                }
            
            durations = [e.get("duration_seconds", 0.0) for e in episodes if e.get("duration_seconds")]
            reductions = [e.get("exposure_reduction_pct", 0.0) for e in episodes if e.get("exposure_reduction_pct")]
            
            return {
                "date": target_date.isoformat() if target_date else date.today().isoformat(),
                "episode_count": len(episodes),
                "total_duration_seconds": sum(durations) if durations else 0.0,
                "avg_duration_seconds": sum(durations) / len(durations) if durations else 0.0,
                "max_duration_seconds": max(durations) if durations else 0.0,
                "total_exposure_reduction_pct": sum(reductions) if reductions else 0.0,
                "avg_exposure_reduction_pct": sum(reductions) / len(reductions) if reductions else 0.0,
                "max_exposure_reduction_pct": max(reductions) if reductions else 0.0,
            }
        
        except Exception as e:
            logger.error(f"❌ [CapRecovery] Error getting summary: {e}", exc_info=True)
            return {}



