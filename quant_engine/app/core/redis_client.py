"""app/core/redis_client.py

Redis client wrapper - supports both sync and async using redis-py 5.0+.
"""

import os
from typing import Optional

try:
    import redis
    import redis.asyncio as redis_async
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    redis_async = None

from app.config.settings import settings
from app.core.logger import logger


class RedisClient:
    """Redis client wrapper - uses redis-py 5.0+ for both sync and async"""
    
    def __init__(self):
        self._sync_client: Optional[redis.Redis] = None
        self._async_client = None
    
    @property
    def sync(self) -> Optional[redis.Redis]:
        """Synchronous Redis client (returns None if Redis unavailable or not connected)"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis package not installed. Using in-memory cache only.")
            return None
        
        if self._sync_client is None:
            try:
                self._sync_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    decode_responses=True,
                    socket_connect_timeout=2  # Quick timeout
                )
                # Test connection
                self._sync_client.ping()
                logger.info(f"Redis sync client connected: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}. Using in-memory cache only.")
                self._sync_client = None
                return None
        
        return self._sync_client
    
    async def async_client(self):
        """Asynchronous Redis client (using redis-py async)"""
        if not REDIS_AVAILABLE:
            raise ImportError("redis package not installed. Install with: pip install redis")
        
        if self._async_client is None:
            # Use redis-py's async client
            self._async_client = redis_async.from_url(
                settings.REDIS_URL,
                decode_responses=True
            )
            # Test connection
            try:
                await self._async_client.ping()
                logger.info(f"Redis async client connected: {settings.REDIS_URL}")
            except Exception as e:
                logger.error(f"Redis async connection error: {e}")
                raise
        
        return self._async_client
    
    def is_available(self) -> bool:
        """Check if Redis is available and connected"""
        if not REDIS_AVAILABLE:
            return False
        if self._sync_client is None:
            # Try to connect
            try:
                test_client = redis.Redis(
                    host=settings.REDIS_HOST,
                    port=settings.REDIS_PORT,
                    decode_responses=True,
                    socket_connect_timeout=2
                )
                test_client.ping()
                test_client.close()
                return True
            except Exception:
                return False
        return True
    
    def close_sync(self):
        """Close sync client"""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
    
    async def close_async(self):
        """Close async client"""
        if self._async_client:
            await self._async_client.close()
            self._async_client = None


# Global Redis client instance
redis_client = RedisClient()


def get_redis_client() -> RedisClient:
    """Get global Redis client instance"""
    return redis_client


# Backward compatibility: direct access to sync client
if REDIS_AVAILABLE:
    def get_redis():
        """Get Redis client (returns None if not connected)"""
        return redis_client.sync
else:
    def get_redis():
        """Get Redis client (returns None if not available)"""
        logger.warning("Redis package not installed. Using in-memory cache only.")
        return None
