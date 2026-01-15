"""
Order Queue
Manages order queuing, throttling, and scheduling (simulation-only, no execution).

Features:
- FIFO queue with priority support
- Rate limiting (max orders per minute)
- Per-symbol cooldown
- Scheduled dispatch time simulation
- NO execution - pure simulation
"""

import time
from typing import Dict, Any, Optional, List, Tuple
from collections import deque, defaultdict
from pathlib import Path
import yaml

from app.core.logger import logger


class QueuedOrder:
    """Represents an order in the queue"""
    
    def __init__(
        self,
        symbol: str,
        order_plan: Dict[str, Any],
        enqueue_time: float,
        scheduled_time: float
    ):
        self.symbol = symbol
        self.order_plan = order_plan
        self.enqueue_time = enqueue_time
        self.scheduled_time = scheduled_time
        self.queue_position = 0


class OrderQueue:
    """
    Manages order queuing and throttling.
    
    This is simulation-only - NO execution, NO order sending.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize with config file.
        
        Args:
            config_path: Path to order_queue_rules.yaml config file
        """
        if config_path is None:
            # Default to config/order_queue_rules.yaml relative to project root
            project_root = Path(__file__).parent.parent.parent
            config_path = project_root / "app" / "config" / "order_queue_rules.yaml"
        
        self.config = self._load_config(config_path)
        self._validate_config()
        
        # Queue state
        self._queue: deque = deque()  # FIFO queue of QueuedOrder objects
        self._symbol_last_order_time: Dict[str, float] = {}  # {symbol: last_order_timestamp}
        self._order_timestamps: List[float] = []  # Track order timestamps for rate limiting
        self._queue_position_counter = 0
        
        # Statistics
        self._total_enqueued = 0
        self._total_skipped = 0
        self._total_dispatched = 0
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load YAML config file"""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"Order queue config file not found: {config_path}, using defaults")
                return self._get_default_config()
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            logger.info(f"Loaded order queue rules config from {config_path}")
            return config
            
        except Exception as e:
            logger.error(f"Error loading order queue config from {config_path}: {e}", exc_info=True)
            logger.warning("Using default order queue config")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default config if file not found"""
        return {
            'queue': {
                'max_orders_per_minute': 60,
                'per_symbol_cooldown_seconds': 5,
                'batch_interval_ms': 500,
                'max_queue_size': 1000,
                'priority': {
                    'urgency_weight': 1.0
                }
            }
        }
    
    def _validate_config(self):
        """Validate config structure"""
        if 'queue' not in self.config:
            raise ValueError("Config missing required key: queue")
    
    def enqueue_order(
        self,
        symbol: str,
        order_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enqueue an order plan.
        
        Args:
            symbol: Symbol identifier
            order_plan: Order plan dict from OrderPlanner
            
        Returns:
            Queue status dict:
            {
                'queued': bool,
                'scheduled_time': float or None,
                'position_in_queue': int or None,
                'queue_status': 'QUEUED' | 'READY' | 'SKIPPED' | 'REJECTED',
                'reason': str
            }
        """
        try:
            # If action is NONE, skip queueing
            if order_plan.get('action') == 'NONE':
                return {
                    'queued': False,
                    'scheduled_time': None,
                    'position_in_queue': None,
                    'queue_status': 'SKIPPED',
                    'reason': 'order_plan_action_none'
                }
            
            # Check queue size limit
            max_size = self.config['queue']['max_queue_size']
            if len(self._queue) >= max_size:
                self._total_skipped += 1
                return {
                    'queued': False,
                    'scheduled_time': None,
                    'position_in_queue': None,
                    'queue_status': 'REJECTED',
                    'reason': f'queue_full_max_size_{max_size}'
                }
            
            # Check per-symbol cooldown
            cooldown_seconds = self.config['queue']['per_symbol_cooldown_seconds']
            current_time = time.time()
            last_order_time = self._symbol_last_order_time.get(symbol, 0)
            time_since_last = current_time - last_order_time
            
            if time_since_last < cooldown_seconds:
                self._total_skipped += 1
                return {
                    'queued': False,
                    'scheduled_time': None,
                    'position_in_queue': None,
                    'queue_status': 'SKIPPED',
                    'reason': f'cooldown_active_{round(cooldown_seconds - time_since_last, 1)}s_remaining'
                }
            
            # Check rate limit (max orders per minute)
            if not self._can_dispatch_now():
                # Calculate when we can dispatch
                scheduled_time = self._calculate_scheduled_time()
            else:
                scheduled_time = current_time
            
            # Create queued order
            queued_order = QueuedOrder(
                symbol=symbol,
                order_plan=order_plan,
                enqueue_time=current_time,
                scheduled_time=scheduled_time
            )
            
            # Add to queue
            self._queue.append(queued_order)
            queued_order.queue_position = len(self._queue)
            self._total_enqueued += 1
            
            # Update symbol last order time
            self._symbol_last_order_time[symbol] = scheduled_time
            
            return {
                'queued': True,
                'scheduled_time': scheduled_time,
                'position_in_queue': queued_order.queue_position,
                'queue_status': 'QUEUED',
                'reason': 'order_enqueued'
            }
            
        except Exception as e:
            logger.error(f"Error enqueuing order for {symbol}: {e}", exc_info=True)
            return {
                'queued': False,
                'scheduled_time': None,
                'position_in_queue': None,
                'queue_status': 'REJECTED',
                'reason': f'error_{str(e)}'
            }
    
    def _can_dispatch_now(self) -> bool:
        """Check if we can dispatch an order now (rate limit check)"""
        max_per_minute = self.config['queue']['max_orders_per_minute']
        current_time = time.time()
        
        # Remove timestamps older than 1 minute
        one_minute_ago = current_time - 60
        self._order_timestamps = [ts for ts in self._order_timestamps if ts > one_minute_ago]
        
        # Check if we're under the limit
        return len(self._order_timestamps) < max_per_minute
    
    def _calculate_scheduled_time(self) -> float:
        """Calculate when the next order can be dispatched"""
        max_per_minute = self.config['queue']['max_orders_per_minute']
        current_time = time.time()
        
        # Remove old timestamps
        one_minute_ago = current_time - 60
        self._order_timestamps = [ts for ts in self._order_timestamps if ts > one_minute_ago]
        
        if len(self._order_timestamps) < max_per_minute:
            # Can dispatch now
            return current_time
        
        # Need to wait until oldest timestamp is 1 minute old
        if self._order_timestamps:
            oldest_timestamp = min(self._order_timestamps)
            scheduled_time = oldest_timestamp + 60
            # Add some buffer (batch interval)
            batch_interval_seconds = self.config['queue']['batch_interval_ms'] / 1000.0
            scheduled_time += batch_interval_seconds
            return scheduled_time
        
        return current_time
    
    def simulate_dispatch(self) -> List[Dict[str, Any]]:
        """
        Simulate dispatching ready orders (for testing/monitoring).
        
        Returns:
            List of dispatched order info dicts
        """
        current_time = time.time()
        dispatched = []
        
        # Process queue (FIFO)
        while self._queue:
            queued_order = self._queue[0]
            
            # Check if it's time to dispatch
            if queued_order.scheduled_time > current_time:
                break  # Not ready yet
            
            # Check if we can dispatch (rate limit)
            if not self._can_dispatch_now():
                break  # Rate limit reached
            
            # Dispatch this order
            self._queue.popleft()
            self._order_timestamps.append(current_time)
            self._total_dispatched += 1
            
            dispatched.append({
                'symbol': queued_order.symbol,
                'order_plan': queued_order.order_plan,
                'scheduled_time': queued_order.scheduled_time,
                'dispatched_time': current_time,
                'queue_position': queued_order.queue_position
            })
            
            # Update queue positions
            for i, order in enumerate(self._queue):
                order.queue_position = i + 1
        
        return dispatched
    
    def get_queue_status(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get queue status.
        
        Args:
            symbol: Optional symbol to check specific position
            
        Returns:
            Queue status dict
        """
        current_time = time.time()
        
        # Find symbol's position in queue
        symbol_position = None
        symbol_scheduled_time = None
        if symbol:
            for i, queued_order in enumerate(self._queue):
                if queued_order.symbol == symbol:
                    symbol_position = i + 1
                    symbol_scheduled_time = queued_order.scheduled_time
                    break
        
        # Clean old timestamps
        one_minute_ago = current_time - 60
        self._order_timestamps = [ts for ts in self._order_timestamps if ts > one_minute_ago]
        
        return {
            'queue_size': len(self._queue),
            'orders_in_last_minute': len(self._order_timestamps),
            'max_orders_per_minute': self.config['queue']['max_orders_per_minute'],
            'symbol_position': symbol_position,
            'symbol_scheduled_time': symbol_scheduled_time,
            'can_dispatch_now': self._can_dispatch_now(),
            'stats': {
                'total_enqueued': self._total_enqueued,
                'total_dispatched': self._total_dispatched,
                'total_skipped': self._total_skipped
            }
        }
    
    def get_queue_info_for_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Get queue information for a specific symbol.
        
        Returns:
            Queue info dict for the symbol
        """
        queue_status = self.get_queue_status(symbol)
        
        if queue_status['symbol_position'] is not None:
            return {
                'queued': True,
                'scheduled_time': queue_status['symbol_scheduled_time'],
                'position_in_queue': queue_status['symbol_position'],
                'queue_status': 'QUEUED',
                'reason': 'order_in_queue'
            }
        else:
            # Check if symbol is in cooldown
            cooldown_seconds = self.config['queue']['per_symbol_cooldown_seconds']
            last_order_time = self._symbol_last_order_time.get(symbol, 0)
            current_time = time.time()
            time_since_last = current_time - last_order_time
            
            if time_since_last < cooldown_seconds:
                return {
                    'queued': False,
                    'scheduled_time': None,
                    'position_in_queue': None,
                    'queue_status': 'SKIPPED',
                    'reason': f'cooldown_{round(cooldown_seconds - time_since_last, 1)}s_remaining'
                }
            else:
                return {
                    'queued': False,
                    'scheduled_time': None,
                    'position_in_queue': None,
                    'queue_status': 'READY',
                    'reason': 'not_queued_can_enqueue'
                }








