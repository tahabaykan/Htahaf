"""
Async Snapshot Queue Worker
Handles getSymbolSnapshot requests in a controlled, rate-limited manner.

CRITICAL RULES:
- Snapshot fetch NEVER happens in L1Update path (real-time blocking)
- Snapshot fetch ONLY happens in:
  - Startup preload (ETF + symbol list)
  - Explicit preload task
  - Manual admin/debug call
- Failed snapshots are cached (5 min TTL) to prevent retry spam
- Rate-limited: max 2 snapshots per second
- Symbol deduplication: same symbol can only be in queue once
- Priority queue: ETFs get priority 0, core benchmarks priority 1, others priority 5
"""

import asyncio
import time
import logging
from typing import Dict, Optional, Set, Tuple
from collections import deque
from threading import Lock
import heapq

logger = logging.getLogger(__name__)

# ETF tickers (priority 0)
ETF_TICKERS = {'TLT', 'IEF', 'IEI', 'PFF', 'PGF', 'KRE', 'IWM', 'SPY'}

# Core benchmarks (priority 1)
CORE_BENCHMARKS = {'SPY', 'IWM', 'QQQ', 'TLT', 'IEF'}

# Global snapshot queue (priority queue: (priority, timestamp, symbol, callback))
_snapshot_queue: asyncio.PriorityQueue = None
_snapshot_worker_task: asyncio.Task = None
_pending_snapshots: Set[str] = set()  # Symbols currently in queue or being processed
_pending_lock = Lock()  # Lock for pending_snapshots set
_failed_snapshot_cache: Dict[str, float] = {}  # symbol -> last_fail_ts
_failed_cache_lock = Lock()
FAIL_TTL = 300  # 5 minutes

# Rate limiting
_last_snapshot_times: deque = deque(maxlen=2)  # Track last 2 snapshot times
MIN_SNAPSHOT_INTERVAL = 0.5  # 0.5 seconds = max 2 per second

# Stats
_snapshot_stats = {
    "queued": 0,
    "processed": 0,
    "success": 0,
    "failed": 0,
    "skipped": 0,
}
_stats_lock = Lock()
_last_stats_log = 0.0
STATS_LOG_INTERVAL = 10.0  # Log stats every 10 seconds


def _get_priority(symbol: str) -> int:
    """Get priority for a symbol (lower = higher priority)"""
    if symbol in ETF_TICKERS:
        return 0  # ETFs highest priority
    elif symbol in CORE_BENCHMARKS:
        return 1  # Core benchmarks second priority
    else:
        return 5  # Others lowest priority


def get_snapshot_queue() -> Optional[asyncio.PriorityQueue]:
    """Get or create the global snapshot priority queue"""
    global _snapshot_queue
    if _snapshot_queue is None:
        _snapshot_queue = asyncio.PriorityQueue(maxsize=1000)  # Max 1000 pending snapshots
    return _snapshot_queue


def is_snapshot_failed_recently(symbol: str) -> bool:
    """Check if snapshot failed recently (within FAIL_TTL)"""
    with _failed_cache_lock:
        fail_time = _failed_snapshot_cache.get(symbol, 0)
        if fail_time > 0:
            age = time.time() - fail_time
            return age < FAIL_TTL
    return False


def mark_snapshot_failed(symbol: str):
    """Mark snapshot as failed (will prevent retry for FAIL_TTL seconds)"""
    with _failed_cache_lock:
        _failed_snapshot_cache[symbol] = time.time()
        logger.debug(f"📊 Snapshot failed for {symbol}, will retry after {FAIL_TTL}s")


def clear_snapshot_failed(symbol: str):
    """Clear failed status (snapshot succeeded)"""
    with _failed_cache_lock:
        if symbol in _failed_snapshot_cache:
            del _failed_snapshot_cache[symbol]


def _remove_from_pending(symbol: str):
    """Remove symbol from pending set (called after snapshot success/fail)"""
    with _pending_lock:
        _pending_snapshots.discard(symbol)


def is_pending(symbol: str) -> bool:
    """Check if symbol is already pending (public API for deduplication check)"""
    with _pending_lock:
        return symbol in _pending_snapshots


def _add_to_pending(symbol: str) -> bool:
    """Add symbol to pending set (returns True if added, False if already pending)"""
    with _pending_lock:
        if symbol in _pending_snapshots:
            return False
        _pending_snapshots.add(symbol)
        return True


def _is_pending(symbol: str) -> bool:
    """Check if symbol is already pending (internal alias for is_pending)"""
    return is_pending(symbol)


def enqueue_snapshot(symbol: str, callback=None) -> bool:
    """
    Enqueue a snapshot request (non-blocking) with state-based deduplication.
    
    CRITICAL: Snapshot is BOOTSTRAP-ONLY, not real-time.
    - State is checked: if already attempted and succeeded, skip
    - If failed, only retry if retry conditions are met
    
    Args:
        symbol: Symbol to fetch snapshot for
        callback: Optional callback function(snapshot_dict) called when snapshot is ready
        
    Returns:
        True if enqueued, False if already attempted/succeeded, failed recently, or queue full
    """
    from app.live.snapshot_state import should_attempt_snapshot, mark_snapshot_attempted
    
    # Check if snapshot should be attempted (state-based)
    if not should_attempt_snapshot(symbol):
        logger.debug(f"📊 Skipping snapshot for {symbol} (already attempted/succeeded or retry conditions not met)")
        with _stats_lock:
            _snapshot_stats["skipped"] += 1
        return False
    
    # Check if snapshot failed recently (additional check)
    if is_snapshot_failed_recently(symbol):
        logger.debug(f"📊 Skipping snapshot for {symbol} (failed recently)")
        with _stats_lock:
            _snapshot_stats["skipped"] += 1
        return False
    
    # Check if already pending (deduplication)
    if _is_pending(symbol):
        logger.debug(f"📊 Skipping snapshot for {symbol} (already pending)")
        with _stats_lock:
            _snapshot_stats["skipped"] += 1
        return False
    
    queue = get_snapshot_queue()
    if queue is None:
        return False
    
    # Mark as attempted (state-based)
    mark_snapshot_attempted(symbol)
    
    # Add to pending set
    if not _add_to_pending(symbol):
        return False
    
    # Get priority
    priority = _get_priority(symbol)
    timestamp = time.time()
    
    try:
        # Priority queue: (priority, timestamp, symbol, callback)
        # Lower priority number = higher priority
        queue.put_nowait((priority, timestamp, symbol, callback))
        
        with _stats_lock:
            _snapshot_stats["queued"] += 1
        
        logger.info(f"📊 Enqueued snapshot for {symbol} (priority={priority}, pending={len(_pending_snapshots)})")
        return True
    except asyncio.QueueFull:
        # Queue full → remove from pending and skip (don't drop)
        _remove_from_pending(symbol)
        logger.debug(f"📊 Snapshot queue full, skipping {symbol} (will retry on next L1Update)")
        with _stats_lock:
            _snapshot_stats["skipped"] += 1
        return False


def _log_stats():
    """Log snapshot stats periodically"""
    global _last_stats_log
    
    current_time = time.time()
    if current_time - _last_stats_log < STATS_LOG_INTERVAL:
        return
    
    with _stats_lock:
        pending_count = len(_pending_snapshots)
        stats = {
            "queued": _snapshot_stats["queued"],
            "processed": _snapshot_stats["processed"],
            "success": _snapshot_stats["success"],
            "failed": _snapshot_stats["failed"],
            "skipped": _snapshot_stats["skipped"],
            "pending": pending_count,
        }
    
    logger.info(f"📊 Snapshot stats: queued={stats['queued']} processed={stats['processed']} "
                f"success={stats['success']} failed={stats['failed']} skipped={stats['skipped']} pending={stats['pending']}")
    
    _last_stats_log = current_time


async def _snapshot_worker():
    """
    Background worker that processes snapshot requests from the priority queue.
    Rate-limited: max 2 snapshots per second.
    """
    from app.live.hammer_client import get_hammer_client
    
    logger.info("📊 Snapshot queue worker started (priority queue with deduplication)")
    
    while True:
        try:
            queue = get_snapshot_queue()
            if queue is None:
                await asyncio.sleep(1)
                continue
            
            # Log stats periodically
            _log_stats()
            
            # Wait for snapshot request (with timeout to allow graceful shutdown)
            try:
                priority, timestamp, symbol, callback = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            
            # Rate limiting: ensure at least MIN_SNAPSHOT_INTERVAL between snapshots
            if _last_snapshot_times:
                time_since_last = time.time() - _last_snapshot_times[-1]
                if time_since_last < MIN_SNAPSHOT_INTERVAL:
                    wait_time = MIN_SNAPSHOT_INTERVAL - time_since_last
                    await asyncio.sleep(wait_time)
            
            # Fetch snapshot
            hammer_client = get_hammer_client()
            if not hammer_client or not hammer_client.is_connected():
                logger.debug(f"📊 Hammer not connected, skipping snapshot for {symbol}")
                # Remove from pending and re-queue if callback is provided (will retry later)
                _remove_from_pending(symbol)
                if callback:
                    await asyncio.sleep(5)  # Wait 5 seconds before retry
                    # Re-enqueue (will check pending again)
                    enqueue_snapshot(symbol, callback)
                continue
            
            # Check if failed recently (double-check after rate limit wait)
            if is_snapshot_failed_recently(symbol):
                logger.debug(f"📊 Skipping snapshot for {symbol} (failed recently)")
                _remove_from_pending(symbol)
                with _stats_lock:
                    _snapshot_stats["skipped"] += 1
                queue.task_done()
                continue
            
            # Fetch snapshot (blocking call, but in async context)
            try:
                from app.live.snapshot_state import mark_snapshot_success, mark_snapshot_failed
                
                snapshot = hammer_client.get_symbol_snapshot(symbol, use_cache=True)
                
                with _stats_lock:
                    _snapshot_stats["processed"] += 1
                
                if snapshot and snapshot.get('prevClose'):
                    # Success - mark as successful and remove from pending
                    mark_snapshot_success(symbol)
                    clear_snapshot_failed(symbol)
                    _remove_from_pending(symbol)
                    _last_snapshot_times.append(time.time())
                    
                    with _stats_lock:
                        _snapshot_stats["success"] += 1
                    
                    # Call callback if provided
                    if callback:
                        try:
                            # Add symbol to snapshot dict for callback
                            snapshot_with_symbol = snapshot.copy()
                            snapshot_with_symbol['symbol'] = symbol
                            
                            if asyncio.iscoroutinefunction(callback):
                                await callback(snapshot_with_symbol)
                            else:
                                callback(snapshot_with_symbol)
                        except Exception as e:
                            logger.warning(f"Error in snapshot callback for {symbol}: {e}")
                    
                    logger.info(f"✅ Snapshot fetched for {symbol} (prevClose={snapshot.get('prevClose')})")
                else:
                    # Snapshot failed - mark as failed and remove from pending
                    mark_snapshot_failed(symbol)
                    _remove_from_pending(symbol)
                    
                    with _stats_lock:
                        _snapshot_stats["failed"] += 1
                    
                    logger.warning(f"⚠️ Snapshot failed for {symbol} (no prevClose)")
                    
            except Exception as e:
                # Snapshot failed - mark as failed and remove from pending
                from app.live.snapshot_state import mark_snapshot_failed
                mark_snapshot_failed(symbol)
                _remove_from_pending(symbol)
                
                with _stats_lock:
                    _snapshot_stats["failed"] += 1
                
                logger.warning(f"⚠️ Snapshot error for {symbol}: {e}")
            
            # Mark task as done
            queue.task_done()
            
        except Exception as e:
            logger.error(f"Error in snapshot worker: {e}", exc_info=True)
            await asyncio.sleep(1)


def start_snapshot_worker():
    """Start the snapshot queue worker (called on startup)"""
    global _snapshot_worker_task
    
    if _snapshot_worker_task is None or _snapshot_worker_task.done():
        try:
            # Try to get running event loop (FastAPI's loop)
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, schedule the task
                _snapshot_worker_task = loop.create_task(_snapshot_worker())
                logger.info("📊 Snapshot queue worker started (in running event loop)")
            except RuntimeError:
                # No running loop, try to get event loop
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Loop is running, schedule task
                        _snapshot_worker_task = loop.create_task(_snapshot_worker())
                        logger.info("📊 Snapshot queue worker started (in running event loop)")
                    else:
                        # Loop exists but not running, create task and schedule it
                        _snapshot_worker_task = loop.create_task(_snapshot_worker())
                        logger.info("📊 Snapshot queue worker started (task created, will run when loop starts)")
                except RuntimeError:
                    # No event loop at all, create new one in background thread
                    import threading
                    def run_worker():
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        global _snapshot_worker_task
                        _snapshot_worker_task = loop.create_task(_snapshot_worker())
                        loop.run_forever()
                    thread = threading.Thread(target=run_worker, daemon=True)
                    thread.start()
                    logger.info("📊 Snapshot queue worker started (in background thread)")
        except Exception as e:
            logger.error(f"Failed to start snapshot worker: {e}", exc_info=True)
            raise
    else:
        logger.debug("📊 Snapshot queue worker already running")


def stop_snapshot_worker():
    """Stop the snapshot queue worker (called on shutdown)"""
    global _snapshot_worker_task
    
    if _snapshot_worker_task and not _snapshot_worker_task.done():
        _snapshot_worker_task.cancel()
        logger.info("📊 Snapshot queue worker stopped")


def get_snapshot_stats() -> Dict[str, int]:
    """Get current snapshot statistics"""
    with _stats_lock:
        return {
            "queued": _snapshot_stats["queued"],
            "processed": _snapshot_stats["processed"],
            "success": _snapshot_stats["success"],
            "failed": _snapshot_stats["failed"],
            "skipped": _snapshot_stats["skipped"],
            "pending": len(_pending_snapshots),
        }
