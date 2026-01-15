"""
Event Log - Redis Streams for Event Logging

Publishes events to Redis Streams with consumer groups.
"""

from typing import Dict, Any, Optional, List
from app.core.redis_client import get_redis_client
from app.core.logger import logger
from app.event_driven.contracts.events import BaseEvent


class EventLog:
    """Event log using Redis Streams"""
    
    def __init__(self, redis_client=None):
        self.redis = redis_client or get_redis_client().sync
        if not self.redis:
            raise RuntimeError("Redis client not available")
    
    def publish(self, stream_name: str, event: BaseEvent) -> Optional[str]:
        """
        Publish event to Redis Stream
        
        Returns:
            Message ID if successful, None otherwise
        """
        try:
            stream_key = f"ev.{stream_name}"
            event_data = event.to_redis_stream()
            
            # XADD to stream
            msg_id = self.redis.xadd(stream_key, event_data)
            
            logger.debug(f"Event published to {stream_key}: {event.event_id} (msg_id={msg_id})")
            return msg_id
        except Exception as e:
            logger.error(f"Error publishing event to {stream_name}: {e}", exc_info=True)
            return None
    
    def create_consumer_group(self, stream_name: str, group_name: str, start_id: str = "0"):
        """Create consumer group for stream"""
        try:
            stream_key = f"ev.{stream_name}"
            try:
                self.redis.xgroup_create(
                    name=stream_key,
                    groupname=group_name,
                    id=start_id,
                    mkstream=True  # Create stream if it doesn't exist
                )
                logger.info(f"Consumer group created: {group_name} for {stream_key}")
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    logger.debug(f"Consumer group {group_name} already exists for {stream_key}")
                else:
                    raise
        except Exception as e:
            logger.error(f"Error creating consumer group {group_name} for {stream_name}: {e}", exc_info=True)
            raise
    
    def read(self, stream_name: str, group_name: str, consumer_name: str,
             count: int = 1, block: int = 1000) -> List[Dict[str, Any]]:
        """
        Read events from stream using consumer group
        
        Returns:
            List of (message_id, event_data) tuples
        """
        try:
            stream_key = f"ev.{stream_name}"
            
            # XREADGROUP
            messages = self.redis.xreadgroup(
                groupname=group_name,
                consumername=consumer_name,
                streams={stream_key: ">"},  # Read pending messages first, then new
                count=count,
                block=block
            )
            
            if not messages:
                return []
            
            result = []
            for stream, stream_messages in messages:
                for msg_id, msg_data in stream_messages:
                    result.append({
                        "message_id": msg_id,
                        "data": msg_data
                    })
            
            return result
        except Exception as e:
            logger.error(f"Error reading from stream {stream_name}: {e}", exc_info=True)
            return []
    
    def ack(self, stream_name: str, group_name: str, message_id: str):
        """Acknowledge message processing"""
        try:
            stream_key = f"ev.{stream_name}"
            self.redis.xack(stream_key, group_name, message_id)
            logger.debug(f"Message acknowledged: {message_id} in {stream_key}")
        except Exception as e:
            logger.error(f"Error acknowledging message {message_id}: {e}", exc_info=True)



