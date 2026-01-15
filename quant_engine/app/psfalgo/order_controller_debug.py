"""
Order Controller - Janall-Compatible (Controller ON)

Manages order lifecycle: tracking, cancellation, replacement.

Features:
- Order Cancel Loop: Cancel unfilled orders after timeout
- Replace Loop: Replace orders with better prices
- Order tracking and status management
- BEFDAY tracking

Janall Logic:
- Orders are tracked from creation
- Unfilled orders are cancelled after 2 minutes (120 seconds)
- Orders can be replaced with better prices
- All order activity is logged
"""

import asyncio
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum

from app.core.logger import logger


from app.execution.order_types import QuantOrderType, QuantOrderBook # Import Enums

class OrderStatus(Enum):
    """Order status enum"""
    PENDING = "PENDING"           # Order created, not sent
    SENT = "SENT"                 # Order sent to broker
    PARTIAL = "PARTIAL"           # Partially filled
    FILLED = "FILLED"             # Fully filled
    CANCELLED = "CANCELLED"       # Cancelled
    REJECTED = "REJECTED"         # Rejected by broker
    EXPIRED = "EXPIRED"           # Expired (timeout)
    REPLACED = "REPLACED"         # Replaced with new order
    ORPHANED = "ORPHANED"         # Orphaned (Left on old provider during switch)


@dataclass
class TrackedOrder:
    """A tracked order"""
    order_id: str
    symbol: str
    action: str                   # BUY, SELL, SHORT, COVER
    order_type: str              # BID_BUY, ASK_SELL (Legacy string)
    lot_qty: int
    price: Optional[float]
    status: OrderStatus = OrderStatus.PENDING
    filled_qty: int = 0
    remaining_qty: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    broker_order_id: Optional[str] = None
    parent_intent_id: Optional[str] = None
    correlation_id: Optional[str] = None # Phase 9: Traceability
    replace_count: int = 0
    error_message: Optional[str] = None
    
    # Multi-Broker Fields
    provider: str = "HAMPRO"          # HAMPRO, IBKR_PED, IBKR_GUN
    book: str = "LT"                  # LT or MM
    quant_order_type: Optional[QuantOrderType] = None
    orphaned_provider: bool = False   # True if left behind on old provider
    
    def __post_init__(self):
        self.remaining_qty = self.lot_qty - self.filled_qty

    
    @property
    def age_seconds(self) -> float:
        """Get order age in seconds"""
        return (datetime.now() - self.created_at).total_seconds()
    
    @property
    def is_active(self) -> bool:
        """Check if order is still active"""
        return self.status in [OrderStatus.PENDING, OrderStatus.SENT, OrderStatus.PARTIAL]


@dataclass
class OrderControllerConfig:
    """Order Controller configuration"""
    enabled: bool = True
    
    # Order Cancel Loop
    cancel_enabled: bool = True
    cancel_check_interval_seconds: int = 30
    max_order_age_seconds: int = 120          # 2 minutes (Janall default)
    cancel_unfilled_orders: bool = True
    
    # Replace Loop
    replace_enabled: bool = True
    replace_check_interval_seconds: int = 60
    price_improvement_threshold: float = 0.01  # $0.01
    max_replace_count: int = 3
    replace_partial_fills: bool = False
    
    # BEFDAY Tracking
    befday_enabled: bool = True
    befday_csv_file: str = "befham.csv"


class OrderController:
    """
    Order Controller - manages order lifecycle.
    
    Features:
    - Track all orders
    - Order Cancel Loop (cancel unfilled orders after timeout)
    - Replace Loop (replace orders with better prices)
    - BEFDAY tracking
    - Thread-safe operations
    """
    

    def __init__(self, config: Optional[OrderControllerConfig] = None):
        """
        Initialize Order Controller.
        
        Args:
            config: OrderControllerConfig object
        """
        self.config = config or OrderControllerConfig()
        
        # Order tracking - Partitioned by account_id (provider)
        # Structure: { account_id: { order_id: TrackedOrder } }
        self._orders: Dict[str, Dict[str, TrackedOrder]] = {}
        self._orders_lock = threading.RLock()
        
        # Background tasks
        self._cancel_task: Optional[asyncio.Task] = None
        self._replace_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Callbacks
        self._on_order_cancelled: Optional[Callable] = None
        self._on_order_replaced: Optional[Callable] = None
        self._cancel_order_func: Optional[Callable] = None
        self._replace_order_func: Optional[Callable] = None
        self._get_current_price_func: Optional[Callable] = None
        
        # Daily tracking (BEFDAY)
        self._daily_lot_changes: Dict[str, int] = {}  # symbol -> lot change
        self._daily_order_count: int = 0
        self._daily_reset_time: Optional[datetime] = None
        
        logger.info(
            f"OrderController initialized: cancel_timeout={self.config.max_order_age_seconds}s, "
            f"replace_threshold=${self.config.price_improvement_threshold}"
        )
    
    def set_callbacks(
        self,
        cancel_order_func: Optional[Callable] = None,
        replace_order_func: Optional[Callable] = None,
        get_current_price_func: Optional[Callable] = None,
        on_order_cancelled: Optional[Callable] = None,
        on_order_replaced: Optional[Callable] = None
    ):
        """
        Set callback functions.
        """
        self._cancel_order_func = cancel_order_func
        self._replace_order_func = replace_order_func
        self._get_current_price_func = get_current_price_func
        self._on_order_cancelled = on_order_cancelled
        self._on_order_replaced = on_order_replaced
    
    # ========== Order Tracking ==========
    
    def track_order(self, order: TrackedOrder) -> None:
        """
        Start tracking an order.
        Orders are partitioned by order.provider (account_id).
        """
        with self._orders_lock:
            # Ensure partition exists
            if order.provider not in self._orders:
                self._orders[order.provider] = {}
                
            self._orders[order.provider][order.order_id] = order
            self._daily_order_count += 1
            
            # Track daily lot change
            symbol = order.symbol
            lot_change = order.lot_qty if order.action in ['BUY', 'ADD'] else -order.lot_qty
            self._daily_lot_changes[symbol] = self._daily_lot_changes.get(symbol, 0) + lot_change
        
        logger.debug(f"[ORDER_CONTROLLER] Tracking order: {order.order_id} ({order.symbol} {order.action} {order.lot_qty}) in {order.provider}")
    
    def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        account_id: str,
        filled_qty: Optional[int] = None,
        broker_order_id: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> Optional[TrackedOrder]:
        """
        Update order status.
        REQUIRES account_id to locate order in partition.
        
        Args:
            order_id: Order ID
            status: New status
            account_id: Account ID (Provider) *CRITICAL*
            filled_qty: Filled quantity (optional)
            broker_order_id: Broker order ID (optional)
            error_message: Error message (optional)
            
        Returns:
            Updated TrackedOrder or None if not found (Unmatched)
        """
        with self._orders_lock:
            partition = self._orders.get(account_id)
            if not partition:
                # Account not found in registry at all
                if status == OrderStatus.FILLED or status == OrderStatus.PARTIAL:
                    self._handle_unmatched_fill(account_id, order_id, filled_qty, broker_order_id)
                return None
                
            order = partition.get(order_id)
            if not order:
                # Order not found in account partition
                if status == OrderStatus.FILLED or status == OrderStatus.PARTIAL:
                    self._handle_unmatched_fill(account_id, order_id, filled_qty, broker_order_id)
                return None
            
            order.status = status
            
            if filled_qty is not None:
                # Calculate fill delta for Ledger updates
                fill_delta = filled_qty - order.filled_qty
                
                if fill_delta > 0 and order.book == "LT":
                    # Determine signed delta based on action
                    signed_delta = fill_delta
                    if order.action in ["SELL", "SHORT"]:
                        signed_delta = -fill_delta
                        
                    # Update Internal Ledger (LT Logic)
                    try:
                            ledger.add_lt_trade(account_id, order.symbol, signed_delta)
                    except Exception as e:
                        logger.error(f"[ORDER_CONTROLLER] Failed to update ledger for {order.symbol}: {e}")

                # Phase 9: CleanLogs (FILL)
                try:
                    from app.psfalgo.clean_log_store import get_clean_log_store, LogSeverity, LogEvent, asdict
                    clean_log = get_clean_log_store()
                    if clean_log:
                        clean_log.log_event(
                            account_id=account_id,
                            component="ORDER_CONTROLLER",
                            event=LogEvent.FILL.value,
                            symbol=order.symbol,
                            message=f"Filled {fill_delta} lots @ {order.price} (Total: {filled_qty}/{order.lot_qty})",
                            severity=LogSeverity.INFO.value,
                            correlation_id=order.correlation_id,
                            details={
                                'order_id': order.order_id,
                                'fill_qty': fill_delta,
                                'price': order.price,
                                'remaining': order.remaining_qty
                            }
                        )
                except Exception as log_err:
                     logger.warning(f"[ORDER_CONTROLLER] Failed to log fill: {log_err}")
                
                order.filled_qty = filled_qty
                order.remaining_qty = order.lot_qty - filled_qty
            
            if broker_order_id:
                order.broker_order_id = broker_order_id
            
            if error_message:
                order.error_message = error_message
            
            # Update timestamps
            if status == OrderStatus.SENT:
                order.sent_at = datetime.now()
            elif status == OrderStatus.FILLED:
                order.filled_at = datetime.now()
            elif status == OrderStatus.CANCELLED:
                order.cancelled_at = datetime.now()
                
                # Phase 9: CleanLogs (CANCEL)
                try:
                    from app.psfalgo.clean_log_store import get_clean_log_store, LogSeverity, LogEvent
                    clean_log = get_clean_log_store()
                    if clean_log:
                        clean_log.log_event(
                            account_id=account_id,
                            component="ORDER_CONTROLLER",
                            event=LogEvent.CANCEL.value,
                            symbol=order.symbol,
                            message=f"Order cancelled: {order.order_id}",
                            severity=LogSeverity.WARNING.value, # Warning for cancels usually
                            correlation_id=order.correlation_id,
                            details={'reason': order.error_message or "Cancelled"}
                        )
                except Exception:
                    pass
            
            return order

    def _handle_unmatched_fill(self, account_id: str, order_id: str, qty: Optional[int], broker_id: Optional[str]):
        """CRITICAL: Log unmatched fill and alert"""
        logger.critical(
            f"[UNMATCHED_FILL] Account: {account_id}, OrderID: {order_id}, Qty: {qty}, BrokerID: {broker_id}. "
            f"Action: Logged for review. (Policy: HOLD_UNCLASSIFIED)"
        )
        # TODO: Persist to 'UnmatchedFills' store if exists or send UI alert

    
    def get_order(self, account_id: str, order_id: str) -> Optional[TrackedOrder]:
        """Get order by ID and Account"""
        with self._orders_lock:
            return self._orders.get(account_id, {}).get(order_id)
    
    def get_active_orders(self, account_id: Optional[str] = None) -> List[TrackedOrder]:
        """
        Get all active orders. 
        If account_id provided, scoped to that account.
        Else returns ALL (useful for admin views, but beware of mixing).
        """
        active_list = []
        with self._orders_lock:
            if account_id:
                partition = self._orders.get(account_id, {})
                active_list.extend([o for o in partition.values() if o.is_active])
            else:
                for partition in self._orders.values():
                    active_list.extend([o for o in partition.values() if o.is_active])
        return active_list
    
    def get_orders_by_symbol(self, account_id: str, symbol: str) -> List[TrackedOrder]:
        """Get all orders for a symbol in specific account."""
        with self._orders_lock:
            partition = self._orders.get(account_id, {})
            return [o for o in partition.values() if o.symbol == symbol]

    def mark_provider_orders_orphaned(self, provider: str) -> int:
        """
        Mark active orders for provider as ORPHANED.
        Optimized O(1) partition access.
        """
        count = 0
        with self._orders_lock:
            partition = self._orders.get(provider, {})
            for order in partition.values():
                if order.is_active:
                    order.orphaned_provider = True
                    order.status = OrderStatus.ORPHANED
                    order.error_message = f"Orphaned from provider {provider}"
                    count += 1
                    logger.info(f"[ORDER_CONTROLLER] Orphaned order {order.order_id} ({order.symbol}) in {provider}")
        
        logger.info(f"[ORDER_CONTROLLER] Orphaned {count} orders in partition {provider}")
        return count
    
    # ========== Order Cancel Loop ==========
    
    async def _cancel_loop(self):
        """Background task: Cancel unfilled orders."""
        logger.info("[ORDER_CONTROLLER] Cancel loop started")
        
        while self._running:
            try:
                await self._check_and_cancel_expired_orders()
                await asyncio.sleep(self.config.cancel_check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ORDER_CONTROLLER] Cancel loop error: {e}", exc_info=True)
                await asyncio.sleep(5)
        
        logger.info("[ORDER_CONTROLLER] Cancel loop stopped")
    
    async def _check_and_cancel_expired_orders(self):
        """Check and cancel expired orders across ALL accounts."""
        if not self.config.cancel_enabled:
            return
        
        orders_to_cancel = []
        
        with self._orders_lock:
            for account_id, partition in self._orders.items():
                for order in partition.values():
                    if not order.is_active:
                        continue
                    
                    if order.age_seconds > self.config.max_order_age_seconds:
                        if order.filled_qty == 0 or (self.config.cancel_unfilled_orders and order.filled_qty < order.lot_qty):
                            orders_to_cancel.append(order)
        
        for order in orders_to_cancel:
            await self._cancel_order(order, reason="Timeout")
    
    async def _cancel_order(self, order: TrackedOrder, reason: str = ""):
        """Cancel a single order"""
        try:
            logger.info(
                f"[ORDER_CONTROLLER] Cancelling order: {order.order_id} ({order.symbol}) - {reason}"
            )
            
            if self._cancel_order_func:
                # Pass account_id (order.provider) to cancel function
                await self._cancel_order_func(order, account_id=order.provider)
            
            self.update_order_status(order.order_id, OrderStatus.CANCELLED, account_id=order.provider)
            
            if self._on_order_cancelled:
                self._on_order_cancelled(order, reason)
            
        except Exception as e:
            logger.error(f"[ORDER_CONTROLLER] Failed to cancel order {order.order_id}: {e}")
            
    async def cancel_all_unfilled_orders(self) -> int:
        """Cancel all unfilled orders across ALL accounts."""
        orders_to_cancel = []
        
        with self._orders_lock:
            for account_id, partition in self._orders.items():
                for order in partition.values():
                    if not order.is_active:
                        continue
                    if order.filled_qty == 0 or order.filled_qty < order.lot_qty:
                        orders_to_cancel.append(order)
        
        cancelled_count = 0
        for order in orders_to_cancel:
            try:
                await self._cancel_order(order, reason="Cycle end cleanup")
                cancelled_count += 1
            except Exception as e:
                logger.error(f"[ORDER_CONTROLLER] Failed to cancel order {order.order_id}: {e}")
        
        return cancelled_count

    async def cancel_open_orders(self, account_id: str, book: Optional[str] = None) -> int:
        """
        Cancel open orders for a specific account, optionally filtered by book.
        
        Args:
            account_id: Account ID (Provider)
            book: Optional book filter ('LT' or 'MM')
            
        Returns:
            Count of cancelled orders
        """
        orders_to_cancel = []
        
        with self._orders_lock:
            partition = self._orders.get(account_id)
            if not partition:
                return 0
            
            for order in partition.values():
                if not order.is_active: continue
                
                # Filter by book if specified
                if book and order.book != book: continue
                
                orders_to_cancel.append(order)
        
        if not orders_to_cancel: return 0
        
        logger.info(f"[ORDER_CONTROLLER] Cancelling {len(orders_to_cancel)} open orders for {account_id} (Book: {book or 'ALL'})")
        
        cancelled_count = 0
        for order in orders_to_cancel:
            try:
                await self._cancel_order(order, reason=f"Cycle Cancel-All ({book or 'ALL'})")
                cancelled_count += 1
            except Exception as e:
                logger.error(f"[ORDER_CONTROLLER] Failed to cancel order {order.order_id}: {e}")
        
        return cancelled_count
    
    # ========== Replace Loop ==========
    
    async def _replace_loop(self):
        logger.info("[ORDER_CONTROLLER] Replace loop started")
        while self._running:
            try:
                await self._check_and_replace_orders()
                await asyncio.sleep(self.config.replace_check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ORDER_CONTROLLER] Replace loop error: {e}", exc_info=True)
                await asyncio.sleep(5)
        logger.info("[ORDER_CONTROLLER] Replace loop stopped")
    
    async def _check_and_replace_orders(self):
        if not self.config.replace_enabled or not self._get_current_price_func:
            return
        
        orders_to_replace = []
        
        with self._orders_lock:
            for account_id, partition in self._orders.items():
                for order in partition.values():
                    if not order.is_active: continue
                    if order.replace_count >= self.config.max_replace_count: continue
                    if order.filled_qty > 0 and not self.config.replace_partial_fills: continue
                    
                    try:
                        current_price = self._get_current_price_func(order.symbol, order.order_type)
                        if current_price is None or order.price is None: continue
                        
                        price_diff = abs(current_price - order.price)
                        if price_diff >= self.config.price_improvement_threshold:
                            orders_to_replace.append((order, current_price))
                    except Exception as e:
                        logger.debug(f"[ORDER_CONTROLLER] Price check failed: {e}")
        
        for order, new_price in orders_to_replace:
            await self._replace_order(order, new_price)
    
    async def _replace_order(self, order: TrackedOrder, new_price: float):
        try:
            logger.info(f"[ORDER_CONTROLLER] Replacing order: {order.order_id} -> {new_price}")
            
            if self._replace_order_func:
                new_order_id = await self._replace_order_func(order, new_price, account_id=order.provider)
                
                self.update_order_status(order.order_id, OrderStatus.REPLACED, account_id=order.provider)
                
                new_order = TrackedOrder(
                    order_id=new_order_id or f"{order.order_id}_r{order.replace_count + 1}",
                    symbol=order.symbol,
                    action=order.action,
                    order_type=order.order_type,
                    lot_qty=order.remaining_qty,
                    price=new_price,
                    parent_intent_id=order.parent_intent_id,
                    replace_count=order.replace_count + 1,
                    provider=order.provider,         # Inherit provider
                    book=order.book,                 # Inherit book
                    quant_order_type=order.quant_order_type,
                    correlation_id=order.correlation_id # Propagate TraceID
                )
                self.track_order(new_order)
            
            if self._on_order_replaced:
                self._on_order_replaced(order, new_price)
            
        except Exception as e:
            logger.error(f"[ORDER_CONTROLLER] Failed to replace order {order.order_id}: {e}")

    
    # ========== Daily Tracking (BEFDAY) ==========
    
    def get_daily_lot_change(self, symbol: str) -> int:
        """Get daily lot change for a symbol"""
        return self._daily_lot_changes.get(symbol, 0)
    
    def get_total_daily_lot_change(self) -> int:
        """Get total daily lot change"""
        return sum(self._daily_lot_changes.values())
    
    def get_daily_order_count(self) -> int:
        """Get daily order count"""
        return self._daily_order_count
    
    def reset_daily_tracking(self):
        """Reset daily tracking (called at market open)"""
        with self._orders_lock:
            self._daily_lot_changes.clear()
            self._daily_order_count = 0
            self._daily_reset_time = datetime.now()
        
        logger.info("[ORDER_CONTROLLER] Daily tracking reset")
    
    # ========== Lifecycle ==========
    
    async def start(self):
        """Start background tasks"""
        if self._running:
            return
        
        self._running = True
        
        if self.config.cancel_enabled:
            self._cancel_task = asyncio.create_task(self._cancel_loop())
        
        if self.config.replace_enabled:
            self._replace_task = asyncio.create_task(self._replace_loop())
        
        logger.info("[ORDER_CONTROLLER] Started")
    
    async def stop(self):
        """Stop background tasks"""
        self._running = False
        
        if self._cancel_task:
            self._cancel_task.cancel()
            try:
                await self._cancel_task
            except asyncio.CancelledError:
                pass
        
        if self._replace_task:
            self._replace_task.cancel()
            try:
                await self._replace_task
            except asyncio.CancelledError:
                pass
        
        logger.info("[ORDER_CONTROLLER] Stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get controller status"""
        with self._orders_lock:
            active_orders = [o for o in self._orders.values() if o.is_active]
            
            return {
                'running': self._running,
                'total_orders': len(self._orders),
                'active_orders': len(active_orders),
                'daily_order_count': self._daily_order_count,
                'daily_lot_change': self.get_total_daily_lot_change(),
                'config': {
                    'cancel_enabled': self.config.cancel_enabled,
                    'cancel_timeout_seconds': self.config.max_order_age_seconds,
                    'replace_enabled': self.config.replace_enabled,
                    'replace_threshold': self.config.price_improvement_threshold
                }
            }


# ============================================================================
# Global Instance Management
# ============================================================================

_order_controller: Optional[OrderController] = None


def get_order_controller() -> Optional[OrderController]:
    """Get global OrderController instance"""
    return _order_controller


def initialize_order_controller(config: Optional[Dict[str, Any]] = None) -> OrderController:
    """Initialize global OrderController instance"""
    global _order_controller
    
    if config:
        ctrl_config = OrderControllerConfig(
            enabled=config.get('enabled', True),
            cancel_enabled=config.get('order_cancel', {}).get('enabled', True),
            cancel_check_interval_seconds=config.get('order_cancel', {}).get('check_interval_seconds', 30),
            max_order_age_seconds=config.get('order_cancel', {}).get('max_order_age_seconds', 120),
            cancel_unfilled_orders=config.get('order_cancel', {}).get('cancel_unfilled_orders', True),
            replace_enabled=config.get('order_replace', {}).get('enabled', True),
            replace_check_interval_seconds=config.get('order_replace', {}).get('check_interval_seconds', 60),
            price_improvement_threshold=config.get('order_replace', {}).get('price_improvement_threshold', 0.01),
            max_replace_count=config.get('order_replace', {}).get('max_replace_count', 3),
            replace_partial_fills=config.get('order_replace', {}).get('replace_partial_fills', False)
        )
    else:
        ctrl_config = OrderControllerConfig()
    
    _order_controller = OrderController(config=ctrl_config)
    logger.info("OrderController initialized (Janall-compatible)")
    return _order_controller

