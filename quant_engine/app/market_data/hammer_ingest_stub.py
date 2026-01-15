"""app/market_data/hammer_ingest_stub.py

Hammer PRO market data ingestion.
Reads ticks from Hammer PRO feed and publishes to Redis.
"""

import json
import threading
import time
from typing import Iterator, Dict, Any, Optional

from app.core.event_bus import EventBus
from app.core.logger import logger


class HammerIngest:
    """
    Hammer PRO market data ingestor.
    
    Reads ticks from Hammer PRO feed and publishes to Redis pub/sub.
    Can work with real Hammer PRO API or fake feed for testing.
    """
    
    def __init__(self, feed_reader: Iterator[Dict[str, Any]]):
        """
        Initialize Hammer ingestor.
        
        Args:
            feed_reader: Generator that yields tick dicts from Hammer PRO.
                        Example:
                            for tick in hammer_api.get_ticks("AAPL"):
                                yield tick
        """
        self.feed_reader = feed_reader
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.tick_count = 0
        self.error_count = 0
    
    def start(self):
        """Start ingestion in background thread"""
        if self.running:
            logger.warning("Hammer ingest already running")
            return
        
        logger.info("🚀 Hammer ingest started")
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """Stop ingestion"""
        logger.info("🛑 Hammer ingest stopping...")
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
        logger.info("✅ Hammer ingest stopped")
    
    def _loop(self):
        """Main ingestion loop (runs in background thread)"""
        logger.info("Hammer ingest loop started")
        
        while self.running:
            try:
                # Get next tick from feed
                tick = next(self.feed_reader, None)
                
                if tick is None:
                    # Feed exhausted or no data
                    time.sleep(0.001)
                    continue
                
                # Normalize Hammer format to standard format
                normalized = self._normalize_tick(tick)
                
                if normalized:
                    # Publish to Redis pub/sub channel "ticks"
                    EventBus.publish("ticks", normalized)
                    self.tick_count += 1
                    
                    # Periodic logging
                    if self.tick_count % 100 == 0:
                        logger.debug(
                            f"Hammer ingest: {self.tick_count} ticks published "
                            f"(errors: {self.error_count})"
                        )
                
            except StopIteration:
                logger.info("Hammer feed exhausted")
                break
            except Exception as e:
                self.error_count += 1
                logger.error(f"Hammer ingest error: {e}", exc_info=True)
                time.sleep(0.1)  # Backoff on error
        
        logger.info(f"Hammer ingest loop ended. Total ticks: {self.tick_count}, Errors: {self.error_count}")
    
    def _normalize_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize Hammer PRO tick format to standard format.
        
        Hammer PRO format may vary, this function converts it to:
        {
            "symbol": str,
            "last": float,      # Last price
            "bid": float,       # Bid price
            "ask": float,       # Ask price
            "volume": int,      # Volume
            "ts": str,          # Timestamp (string for JSON compatibility)
        }
        
        Args:
            tick: Raw tick dict from Hammer PRO
            
        Returns:
            Normalized tick dict or None if invalid
        """
        try:
            # Extract symbol
            symbol = tick.get("symbol") or tick.get("ticker") or tick.get("contract")
            if not symbol:
                logger.warning(f"Tick missing symbol: {tick}")
                return None
            
            # Extract prices
            last = tick.get("last") or tick.get("price") or tick.get("close")
            bid = tick.get("bid") or tick.get("bidPrice")
            ask = tick.get("ask") or tick.get("askPrice")
            
            # Extract volume
            volume = tick.get("volume") or tick.get("vol") or 0
            
            # Extract timestamp
            timestamp = tick.get("timestamp") or tick.get("ts") or tick.get("time")
            if timestamp is None:
                timestamp = int(time.time() * 1000)  # Current time in ms
            elif isinstance(timestamp, float):
                timestamp = int(timestamp * 1000) if timestamp < 1e10 else int(timestamp)
            
            # Validate required fields
            if last is None or last <= 0:
                logger.warning(f"Invalid tick price: {tick}")
                return None
            
            # Build normalized tick
            normalized = {
                "symbol": str(symbol),
                "last": str(float(last)),  # String for JSON compatibility
                "ts": str(timestamp),
            }
            
            # Optional fields
            if bid is not None:
                normalized["bid"] = str(float(bid))
            if ask is not None:
                normalized["ask"] = str(float(ask))
            if volume:
                normalized["volume"] = str(int(volume))
            
            return normalized
            
        except Exception as e:
            logger.error(f"Error normalizing tick: {e}, tick: {tick}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get ingestion statistics"""
        return {
            "running": self.running,
            "tick_count": self.tick_count,
            "error_count": self.error_count
        }
