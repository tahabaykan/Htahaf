"""app/core/event_bus.py

Event bus implementation using Redis pub/sub and streams.
Supports both synchronous and asynchronous operations.
"""

from typing import Dict, Any, Optional, Callable
import json

from app.core.redis_client import redis_client
from app.core.logger import logger


class EventBus:
    """Event bus for pub/sub and stream operations"""
    
    @staticmethod
    def publish(channel: str, message: Dict[str, Any]) -> int:
        """
        Publish message to Redis channel (pub/sub).
        
        Args:
            channel: Channel name
            message: Message dict (will be JSON serialized)
            
        Returns:
            Number of subscribers that received the message
        """
        try:
            redis = redis_client.sync
            # If message is already a dict, serialize it
            if isinstance(message, dict):
                message_str = json.dumps(message)
            else:
                message_str = str(message)
            subscribers = redis.publish(channel, message_str)
            logger.debug(f"Published to {channel}: {subscribers} subscribers")
            return subscribers
        except Exception as e:
            logger.error(f"Error publishing to {channel}: {e}")
            return 0
    
    @staticmethod
    def subscribe(channel: str):
        """
        Subscribe to Redis channel (pub/sub).
        
        Args:
            channel: Channel name
            
        Returns:
            Redis pubsub object
        """
        try:
            redis = redis_client.sync
            pubsub = redis.pubsub()
            pubsub.subscribe(channel)
            logger.info(f"Subscribed to channel: {channel}")
            return pubsub
        except Exception as e:
            logger.error(f"Error subscribing to {channel}: {e}")
            raise
    
    @staticmethod
    def xadd(stream: str, data: Dict[str, Any]) -> str:
        """
        Add message to Redis stream.
        
        Args:
            stream: Stream name
            data: Message data dict
            
        Returns:
            Message ID
        """
        try:
            redis = redis_client.sync
            msg_id = redis.xadd(stream, data)
            logger.debug(f"Added to stream {stream}: {msg_id}")
            return msg_id
        except Exception as e:
            logger.error(f"Error adding to stream {stream}: {e}")
            raise
    
    @staticmethod
    def xread(streams: Dict[str, str], count: int = 10, block: int = 0):
        """
        Read from Redis streams.
        
        Args:
            streams: Dict of {stream_name: last_id}
            count: Maximum number of messages per stream
            block: Block time in milliseconds (0 = non-blocking)
            
        Returns:
            List of (stream, messages) tuples
        """
        try:
            redis = redis_client.sync
            messages = redis.xread(streams, count=count, block=block)
            return messages
        except Exception as e:
            logger.error(f"Error reading streams: {e}")
            return []
    
    @staticmethod
    async def publish_async(channel: str, message: Dict[str, Any]) -> int:
        """Async version of publish"""
        try:
            redis = await redis_client.async_client()
            message_str = json.dumps(message)
            subscribers = await redis.publish(channel, message_str)
            logger.debug(f"Published (async) to {channel}: {subscribers} subscribers")
            return subscribers
        except Exception as e:
            logger.error(f"Error publishing (async) to {channel}: {e}")
            return 0
    
    @staticmethod
    async def xadd_async(stream: str, data: Dict[str, Any]) -> str:
        """Async version of xadd"""
        try:
            redis = await redis_client.async_client()
            msg_id = await redis.xadd(stream, data)
            logger.debug(f"Added (async) to stream {stream}: {msg_id}")
            return msg_id
        except Exception as e:
            logger.error(f"Error adding (async) to stream {stream}: {e}")
            raise
    
    @staticmethod
    def stream_add(stream: str, data: Dict[str, Any]) -> str:
        """
        Add message to Redis stream (alias for xadd).
        
        Args:
            stream: Stream name
            data: Message data dict
            
        Returns:
            Message ID
        """
        return EventBus.xadd(stream, data)
    
    @staticmethod
    def stream_read(stream: str, last_id: str = "0-0", block: int = 1000, count: int = 1) -> Optional[Dict[str, Any]]:
        """
        Read from Redis stream (single message).
        
        Args:
            stream: Stream name
            last_id: Last message ID (default: "0-0" = from beginning)
            block: Block time in milliseconds (0 = non-blocking)
            count: Maximum number of messages
            
        Returns:
            Message dict with 'id' and 'data' keys, or None if no message
        """
        try:
            messages = EventBus.xread({stream: last_id}, count=count, block=block)
            if messages:
                for stream_name, items in messages:
                    for msg_id, data in items:
                        return {
                            'id': msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                            'data': data
                        }
            return None
        except Exception as e:
            logger.error(f"Error reading stream {stream}: {e}")
            return None
    
    @staticmethod
    def stream_ack(stream: str, group: str, message_id: str):
        """
        Acknowledge message in consumer group.
        
        Args:
            stream: Stream name
            group: Consumer group name
            message_id: Message ID to acknowledge
        """
        try:
            redis = redis_client.sync
            redis.xack(stream, group, message_id)
            logger.debug(f"Acknowledged message {message_id} in {stream}/{group}")
        except Exception as e:
            logger.error(f"Error acknowledging message: {e}")

