"""
L1 Feed Terminal - Dedicated L1 Data Feed (STREAMING MODE)

Subscribes to L1 (bid/ask/last) updates via Hammer Pro WebSocket.
Writes to Redis: market:l1:{symbol}

ARCHITECTURE NOTE:
  OLD (broken): Polled getSymbolSnapshot for 467 symbols every 30s
                 → 467 serial HTTP-like calls → Hammer overload → timeouts
                 → circuit breaker → disconnect → reconnect fails → L1 dead

  NEW (streaming): Subscribe to L1 updates once → receive push callbacks
                    → write to Redis on each update → Hammer stays healthy
                    → Main App's HammerClient stays unaffected

Usage:
    python workers/l1_feed_worker.py
    
    In baslat.py: Press 'L' to start
"""

import os
import sys
import json
import time
import signal
import threading
from typing import Dict, List, Any, Optional
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.config.settings import settings
from app.live.hammer_client import HammerClient
from app.live.symbol_mapper import SymbolMapper
from app.market_data.static_data_store import get_static_store, initialize_static_store


class L1FeedWorker:
    """
    Dedicated L1 Feed Worker (Streaming Mode)
    
    - Subscribes to L1 updates for all symbols (one-time batch subscribe)
    - Receives pushed L1Update messages via WebSocket callback
    - Updates market:l1:{symbol} in Redis on each update
    - Provides fresh bid/ask/spread for RevnBookCheck and other terminals
    
    CRITICAL: Does NOT poll getSymbolSnapshot! That approach caused
    Hammer Pro overload and killed L1 for both this terminal AND the main app.
    """
    
    def __init__(self, poll_interval: int = 30):
        self.poll_interval = poll_interval  # Used for health check interval
        self.running = False
        self.redis_client = None
        self.hammer_client = None
        self.symbols: List[str] = []
        
        # Stats
        self.l1_updates_received = 0
        self.l1_updates_written = 0
        self.cycles_completed = 0
        self.start_time = None
        self._last_stats_time = 0
        self._stats_interval = 60  # Print stats every 60s
        
        # Redis pipeline batching
        self._pending_updates: Dict[str, Dict] = {}
        self._pending_lock = threading.Lock()
        self._flush_interval = 2.0  # Flush Redis every 2 seconds
        
        # Staleness tracking
        self._last_l1_time: float = 0.0
        self._stale_threshold = 90.0  # seconds
        
        logger.info(f"[L1Feed] Initializing STREAMING mode (health check every {poll_interval}s)")
    
    def connect(self) -> bool:
        """Connect to Redis and Hammer Pro (with retry)"""
        try:
            # Redis
            redis_wrapper = get_redis_client()
            self.redis_client = redis_wrapper.sync
            logger.info("[L1Feed] ✅ Connected to Redis")
            
            # Hammer Pro — retry up to 3 times (startup race condition with other terminals)
            max_retries = 3
            backoff = [3, 5, 10]  # seconds between retries
            
            for attempt in range(1, max_retries + 1):
                self.hammer_client = HammerClient(
                    host=settings.HAMMER_HOST,
                    port=settings.HAMMER_PORT,
                    password=settings.HAMMER_PASSWORD
                )
                
                # Set L1Update callback BEFORE connecting
                self.hammer_client.on_message_callback = self._handle_message
                
                if self.hammer_client.connect():
                    # Wait for auth
                    auth_deadline = time.time() + 15
                    while not self.hammer_client.authenticated and time.time() < auth_deadline:
                        time.sleep(0.1)
                    
                    if self.hammer_client.authenticated:
                        logger.info("[L1Feed] ✅ Connected & authenticated to Hammer Pro")
                        return True
                    else:
                        logger.warning(f"[L1Feed] ⚠️ Connected but auth failed (attempt {attempt})")
                else:
                    logger.warning(f"[L1Feed] ⚠️ Connection failed (attempt {attempt})")
                
                if attempt < max_retries:
                    wait = backoff[attempt - 1]
                    logger.warning(f"[L1Feed] Retrying in {wait}s...")
                    time.sleep(wait)
            
            logger.error(f"[L1Feed] ❌ Failed to connect after {max_retries} attempts")
            return False
            
        except Exception as e:
            logger.error(f"[L1Feed] Connection error: {e}", exc_info=True)
            return False
    
    def load_symbols(self) -> bool:
        """Load symbol universe from static store"""
        try:
            static_store = get_static_store()
            if not static_store:
                static_store = initialize_static_store()
            
            if static_store and not static_store.is_loaded():
                static_store.load_csv()
            
            if static_store:
                self.symbols = static_store.get_all_symbols()
                logger.info(f"[L1Feed] ✅ Loaded {len(self.symbols)} symbols from static store")
                return True
            else:
                logger.warning("[L1Feed] ⚠️ Static store not available, trying Redis")
                keys = self.redis_client.keys("market:l1:*")
                if keys:
                    self.symbols = [k.decode().replace("market:l1:", "") if isinstance(k, bytes) else k.replace("market:l1:", "") for k in keys]
                    logger.info(f"[L1Feed] ✅ Loaded {len(self.symbols)} symbols from Redis keys")
                    return True
                else:
                    logger.error("[L1Feed] ❌ No symbols found")
                    return False
                    
        except Exception as e:
            logger.error(f"[L1Feed] Symbol load error: {e}", exc_info=True)
            return False
    
    def subscribe_all(self) -> int:
        """Subscribe to L1 updates for all symbols via streaming (batch)"""
        if not self.symbols or not self.hammer_client:
            return 0
        
        # Wait for streamer to be ready
        logger.info("[L1Feed] ⏳ Waiting for data streamer to be ready...")
        if not self.hammer_client._streamer_ready_event.wait(timeout=15):
            logger.warning("[L1Feed] ⚠️ Streamer not ready after 15s — proceeding anyway")
        
        # Convert all symbols to Hammer format and subscribe in batches
        batch_size = 50
        subscribed = 0
        
        for i in range(0, len(self.symbols), batch_size):
            batch = self.symbols[i:i + batch_size]
            hammer_symbols = [SymbolMapper.to_hammer_symbol(s) for s in batch]
            
            # Subscribe to L1
            l1_cmd = {
                "cmd": "subscribe",
                "sub": "L1",
                "streamerID": self.hammer_client.streamer_id,
                "sym": hammer_symbols,
                "transient": False
            }
            
            if self.hammer_client.send_command(l1_cmd, wait_for_response=False):
                subscribed += len(batch)
            else:
                logger.warning(f"[L1Feed] ⚠️ Failed to subscribe batch {i//batch_size + 1}")
                if not self.hammer_client.is_connected():
                    logger.error("[L1Feed] ❌ Lost connection during subscribe!")
                    break
            
            # Small delay between batches
            if i + batch_size < len(self.symbols):
                time.sleep(0.3)
        
        logger.info(f"[L1Feed] ✅ Subscribed to {subscribed}/{len(self.symbols)} symbols (L1 streaming)")
        return subscribed
    
    def _handle_message(self, data: Dict[str, Any]):
        """
        Handle incoming L1Update messages from Hammer Pro.
        Called by HammerClient's _on_message for every WebSocket message.
        
        Only processes L1Update messages — ignores all others.
        Batches updates for Redis (flushed every 2 seconds).
        """
        try:
            cmd = data.get("cmd", "")
            
            if cmd != "L1Update":
                return  # Only interested in L1 updates
            
            result = data.get("result", {})
            if not result:
                return
            
            # Get symbol
            hammer_symbol = result.get("sym")
            if not hammer_symbol:
                return
            
            # Convert to display format
            display_symbol = SymbolMapper.to_display_symbol(hammer_symbol)
            
            # Extract fields
            bid = result.get("bid")
            ask = result.get("ask")
            last = result.get("last") or result.get("price") or result.get("trade") or result.get("tradePrice")
            
            if bid is None and ask is None and last is None:
                return
            
            # Track stats
            self.l1_updates_received += 1
            self._last_l1_time = time.time()
            
            # Build L1 data
            bid_f = float(bid) if bid is not None and bid != "" else 0.0
            ask_f = float(ask) if ask is not None and ask != "" else 0.0
            last_f = float(last) if last is not None and last != "" else 0.0
            
            spread = 0.0
            if bid_f > 0 and ask_f > 0 and ask_f > bid_f:
                spread = round(ask_f - bid_f, 4)
            
            l1_data = {
                'bid': bid_f,
                'ask': ask_f,
                'spread': spread,
                'last': last_f,
                'ts': time.time()
            }
            
            # Add to pending batch (thread-safe)
            with self._pending_lock:
                self._pending_updates[display_symbol] = l1_data
            
            # Log first few updates
            if self.l1_updates_received <= 10:
                logger.info(f"[L1Feed] 📊 L1Update #{self.l1_updates_received}: {display_symbol} bid={bid_f} ask={ask_f} last={last_f}")
                
        except Exception as e:
            logger.error(f"[L1Feed] Error handling L1Update: {e}")
    
    def _flush_to_redis(self):
        """Flush pending L1 updates to Redis (called periodically)"""
        with self._pending_lock:
            if not self._pending_updates:
                return
            updates = dict(self._pending_updates)
            self._pending_updates.clear()
        
        try:
            pipeline = self.redis_client.pipeline()
            
            for symbol, l1_data in updates.items():
                key = f"market:l1:{symbol}"
                pipeline.setex(key, 120, json.dumps(l1_data))  # 2 min TTL
            
            pipeline.execute()
            self.l1_updates_written += len(updates)
            
            # Publish batch update for subscribers
            if updates:
                self.redis_client.publish("market:live:updates", json.dumps(updates))
                
        except Exception as e:
            logger.error(f"[L1Feed] Redis flush error: {e}")
    
    def run(self):
        """Main worker loop"""
        logger.info("=" * 70)
        logger.info("[L1Feed] L1 Feed Terminal Starting (STREAMING MODE)")
        logger.info(f"[L1Feed] Health check interval: {self.poll_interval} seconds")
        logger.info("[L1Feed] ⚡ Using L1Update subscriptions (NOT getSymbolSnapshot polling)")
        logger.info("=" * 70)
        
        # Connect
        if not self.connect():
            logger.error("[L1Feed] ❌ Failed to connect. Exiting.")
            return
        
        # Load symbols
        if not self.load_symbols():
            logger.error("[L1Feed] ❌ Failed to load symbols. Exiting.")
            return
        
        # Subscribe to all symbols (streaming L1)
        subscribed = self.subscribe_all()
        if subscribed == 0:
            logger.error("[L1Feed] ❌ Failed to subscribe to any symbols. Exiting.")
            return
        
        logger.info(f"[L1Feed] ✅ Ready — streaming L1 for {subscribed} symbols")
        logger.info("[L1Feed] Press Ctrl+C to stop")
        
        self.running = True
        self.start_time = datetime.now()
        self._last_l1_time = time.time()
        self._last_stats_time = time.time()
        last_flush = time.time()
        
        while self.running:
            try:
                now = time.time()
                
                # Flush pending updates to Redis
                if now - last_flush >= self._flush_interval:
                    self._flush_to_redis()
                    last_flush = now
                
                # Print stats periodically
                if now - self._last_stats_time >= self._stats_interval:
                    self._print_stats()
                    self._last_stats_time = now
                
                # Check L1 staleness (during market hours)
                l1_age = now - self._last_l1_time
                if l1_age > self._stale_threshold:
                    self._handle_stale_l1(l1_age)
                
                # Sleep a short interval
                time.sleep(1.0)
                
            except Exception as e:
                logger.error(f"[L1Feed] Loop error: {e}", exc_info=True)
                time.sleep(5)
        
        # Final flush
        self._flush_to_redis()
        self.cleanup()
    
    def _print_stats(self):
        """Print periodic health stats"""
        l1_age = time.time() - self._last_l1_time
        runtime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        
        logger.info(
            f"[L1Feed] 📊 Stats: "
            f"received={self.l1_updates_received} "
            f"written={self.l1_updates_written} "
            f"last_L1={l1_age:.0f}s ago "
            f"runtime={runtime:.0f}s "
            f"connected={self.hammer_client.is_connected() if self.hammer_client else False}"
        )
    
    def _handle_stale_l1(self, age: float):
        """Handle stale L1 data — resubscribe or reconnect"""
        # Only during market hours (9:25-16:05 ET)
        from datetime import timezone, timedelta
        now_utc = datetime.now(timezone.utc)
        et_offset = timedelta(hours=-4)  # EDT
        now_et = now_utc + et_offset
        market_open = now_et.replace(hour=9, minute=25, second=0)
        market_close = now_et.replace(hour=16, minute=5, second=0)
        
        if not (market_open <= now_et <= market_close):
            return  # Outside market hours
        
        logger.warning(f"[L1Feed] ⚠️ L1 data stale for {age:.0f}s! Checking connection...")
        
        if not self.hammer_client or not self.hammer_client.is_connected():
            logger.warning("[L1Feed] ❌ Hammer disconnected! Attempting reconnect...")
            try:
                if self.hammer_client:
                    self.hammer_client.disconnect()
                time.sleep(3)
                
                self.hammer_client = HammerClient(
                    host=settings.HAMMER_HOST,
                    port=settings.HAMMER_PORT,
                    password=settings.HAMMER_PASSWORD
                )
                self.hammer_client.on_message_callback = self._handle_message
                
                if self.hammer_client.connect():
                    # Wait for auth
                    auth_deadline = time.time() + 15
                    while not self.hammer_client.authenticated and time.time() < auth_deadline:
                        time.sleep(0.1)
                    
                    if self.hammer_client.authenticated:
                        logger.info("[L1Feed] ✅ Reconnected! Re-subscribing...")
                        self.subscribe_all()
                        self._last_l1_time = time.time()
                    else:
                        logger.error("[L1Feed] ❌ Reconnect auth failed")
                else:
                    logger.error("[L1Feed] ❌ Reconnect failed")
            except Exception as e:
                logger.error(f"[L1Feed] Reconnect error: {e}")
        else:
            # Connected but no L1 data — resubscribe
            logger.info("[L1Feed] 🔄 Connected but L1 stale — re-subscribing all symbols...")
            self.subscribe_all()
            self._last_l1_time = time.time()
    
    def cleanup(self):
        """Cleanup on exit"""
        logger.info("[L1Feed] Shutting down...")
        
        if self.hammer_client:
            self.hammer_client.disconnect()
        
        # Print final stats
        if self.start_time:
            runtime = (datetime.now() - self.start_time).total_seconds()
            logger.info(
                f"[L1Feed] Final Stats: "
                f"received={self.l1_updates_received} "
                f"written={self.l1_updates_written} "
                f"runtime={runtime:.0f}s"
            )
        
        logger.info("[L1Feed] ✅ Shutdown complete")
    
    def stop(self):
        """Stop the worker"""
        self.running = False


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="L1 Feed Terminal (Streaming Mode)")
    parser.add_argument("--interval", type=int, default=30, help="Health check interval in seconds (default: 30)")
    
    args = parser.parse_args()
    
    worker = L1FeedWorker(poll_interval=args.interval)
    
    # Handle SIGINT
    def signal_handler(sig, frame):
        logger.info("\n[L1Feed] Received SIGINT, stopping...")
        worker.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run
    worker.run()


if __name__ == "__main__":
    main()
