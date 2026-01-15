"""
State Store - Redis Hashes for Latest State

Maintains latest state in Redis Hashes for fast access.
"""

from typing import Dict, Any, Optional
import json
from app.core.redis_client import get_redis_client
from app.core.logger import logger


class StateStore:
    """State store using Redis Hashes"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client().sync
        if not self.redis:
            raise RuntimeError("Redis client not available")
    
    def set_state(self, key: str, state: Dict[str, Any], ttl: Optional[int] = None):
        """Set state in Redis Hash"""
        try:
            # Convert dict values to strings for Redis Hash
            hash_data = {}
            for k, v in state.items():
                if isinstance(v, (dict, list)):
                    hash_data[k] = json.dumps(v)
                else:
                    hash_data[k] = str(v)
            
            state_key = f"state:{key}"
            self.redis.hset(state_key, mapping=hash_data)
            
            if ttl:
                self.redis.expire(state_key, ttl)
            
            logger.debug(f"State updated: {state_key}")
        except Exception as e:
            logger.error(f"Error setting state {key}: {e}", exc_info=True)
            raise
    
    def get_state(self, key: str) -> Optional[Dict[str, Any]]:
        """Get state from Redis Hash"""
        try:
            state_key = f"state:{key}"
            data = self.redis.hgetall(state_key)
            
            if not data:
                return None
            
            # Parse JSON values
            result = {}
            for k, v in data.items():
                try:
                    result[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    result[k] = v
            
            return result
        except Exception as e:
            logger.error(f"Error getting state {key}: {e}", exc_info=True)
            return None
    
    def update_state(self, key: str, updates: Dict[str, Any]):
        """Update state (partial update)"""
        try:
            state_key = f"state:{key}"
            hash_data = {}
            for k, v in updates.items():
                if isinstance(v, (dict, list)):
                    hash_data[k] = json.dumps(v)
                else:
                    hash_data[k] = str(v)
            
            self.redis.hset(state_key, mapping=hash_data)
            logger.debug(f"State updated (partial): {state_key}")
        except Exception as e:
            logger.error(f"Error updating state {key}: {e}", exc_info=True)
            raise
    
    def delete_state(self, key: str):
        """Delete state"""
        try:
            state_key = f"state:{key}"
            self.redis.delete(state_key)
            logger.debug(f"State deleted: {state_key}")
        except Exception as e:
            logger.error(f"Error deleting state {key}: {e}", exc_info=True)



