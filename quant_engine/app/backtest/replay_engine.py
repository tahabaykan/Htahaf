"""app/backtest/replay_engine.py

Replay engine - replays historical data tick-by-tick or candle-by-candle.
Supports speed control, deterministic event ordering, and multi-symbol replay.
"""

import time
import heapq
from typing import Iterator, Dict, Any, Optional, Callable, List, Tuple
from enum import Enum

from app.core.logger import logger


class ReplayMode(Enum):
    """Replay mode"""
    TICK = "tick"  # Tick-by-tick replay
    CANDLE = "candle"  # Candle-by-candle replay


class ReplaySpeed(Enum):
    """Replay speed"""
    INSTANT = "instant"  # No delay, as fast as possible
    REALTIME = "realtime"  # Real-time speed (1x)
    SLOW = "slow"  # 0.1x speed
    FAST = "fast"  # 10x speed


class ReplayEngine:
    """
    Replay engine - replays historical data.
    
    Features:
    - Tick-by-tick or candle-by-candle replay
    - Speed control (instant, real-time, slow, fast)
    - Deterministic event order
    - Strategy callback support
    """
    
    def __init__(
        self,
        mode: ReplayMode = ReplayMode.TICK,
        speed: ReplaySpeed = ReplaySpeed.INSTANT
    ):
        """
        Initialize replay engine.
        
        Args:
            mode: Replay mode (TICK or CANDLE)
            speed: Replay speed (INSTANT, REALTIME, SLOW, FAST)
        """
        self.mode = mode
        self.speed = speed
        self.running = False
        self.tick_count = 0
        self.candle_count = 0
        self.start_time: Optional[float] = None
        self.last_timestamp: Optional[float] = None
    
    def replay_ticks(
        self,
        ticks: Iterator[Dict[str, Any]],
        on_tick: Callable[[Dict[str, Any]], None]
    ):
        """
        Replay ticks.
        
        Args:
            ticks: Iterator of tick dicts
            on_tick: Callback function called for each tick
        """
        self.running = True
        self.start_time = time.time()
        self.last_timestamp = None
        
        logger.info(f"Starting tick replay (speed: {self.speed.value})")
        
        try:
            for tick in ticks:
                if not self.running:
                    break
                
                # Get tick timestamp
                tick_ts = float(tick.get('ts', 0)) / 1000.0  # Convert ms to seconds
                
                # Handle speed control
                if self.speed != ReplaySpeed.INSTANT and self.last_timestamp is not None:
                    time_diff = tick_ts - self.last_timestamp
                    
                    # Adjust for speed
                    if self.speed == ReplaySpeed.REALTIME:
                        delay = time_diff
                    elif self.speed == ReplaySpeed.SLOW:
                        delay = time_diff * 10  # 0.1x speed
                    elif self.speed == ReplaySpeed.FAST:
                        delay = time_diff / 10  # 10x speed
                    else:
                        delay = 0
                    
                    if delay > 0:
                        time.sleep(delay)
                
                # Call callback
                on_tick(tick)
                
                self.tick_count += 1
                self.last_timestamp = tick_ts
                
                # Progress update
                if self.tick_count % 1000 == 0:
                    elapsed = time.time() - self.start_time
                    rate = self.tick_count / elapsed if elapsed > 0 else 0
                    logger.info(f"Replayed {self.tick_count:,} ticks ({rate:.0f} ticks/sec)")
        
        except Exception as e:
            logger.error(f"Error in tick replay: {e}", exc_info=True)
        finally:
            self.running = False
            elapsed = time.time() - self.start_time if self.start_time else 0
            logger.info(f"Tick replay completed: {self.tick_count:,} ticks in {elapsed:.2f}s")
    
    def replay_candles(
        self,
        candles: Iterator[Dict[str, Any]],
        on_candle: Callable[[Dict[str, Any]], None]
    ):
        """
        Replay candles.
        
        Args:
            candles: Iterator of candle dicts
            on_candle: Callback function called for each candle
        """
        self.running = True
        self.start_time = time.time()
        self.last_timestamp = None
        
        logger.info(f"Starting candle replay (speed: {self.speed.value})")
        
        try:
            for candle in candles:
                if not self.running:
                    break
                
                # Get candle timestamp
                candle_ts = float(candle.get('timestamp', 0))
                
                # Handle speed control
                if self.speed != ReplaySpeed.INSTANT and self.last_timestamp is not None:
                    time_diff = candle_ts - self.last_timestamp
                    
                    # Adjust for speed
                    if self.speed == ReplaySpeed.REALTIME:
                        delay = time_diff
                    elif self.speed == ReplaySpeed.SLOW:
                        delay = time_diff * 10
                    elif self.speed == ReplaySpeed.FAST:
                        delay = time_diff / 10
                    else:
                        delay = 0
                    
                    if delay > 0:
                        time.sleep(delay)
                
                # Call callback
                on_candle(candle)
                
                self.candle_count += 1
                self.last_timestamp = candle_ts
                
                # Progress update
                if self.candle_count % 100 == 0:
                    elapsed = time.time() - self.start_time
                    rate = self.candle_count / elapsed if elapsed > 0 else 0
                    logger.info(f"Replayed {self.candle_count:,} candles ({rate:.0f} candles/sec)")
        
        except Exception as e:
            logger.error(f"Error in candle replay: {e}", exc_info=True)
        finally:
            self.running = False
            elapsed = time.time() - self.start_time if self.start_time else 0
            logger.info(f"Candle replay completed: {self.candle_count:,} candles in {elapsed:.2f}s")
    
    def stop(self):
        """Stop replay"""
        self.running = False
        logger.info("Replay stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get replay statistics"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        return {
            'mode': self.mode.value,
            'speed': self.speed.value,
            'tick_count': self.tick_count,
            'candle_count': self.candle_count,
            'elapsed_time': elapsed,
            'tick_rate': self.tick_count / elapsed if elapsed > 0 else 0,
            'candle_rate': self.candle_count / elapsed if elapsed > 0 else 0
        }

