"""
Hammer Orders Service
READ-ONLY service to fetch open orders from Hammer Pro trading account.
"""

import time
from typing import List, Dict, Any, Optional
from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper


class HammerOrdersService:
    """
    Service to fetch and normalize open orders from Hammer Pro.
    
    READ-ONLY: No order placement, no cancel, no modifications.
    """
    
    def __init__(self, hammer_client=None):
        """
        Initialize orders service.
        
        Args:
            hammer_client: HammerClient instance (optional, can be set later)
        """
        self.hammer_client = hammer_client
        self.account_key: Optional[str] = None
        # Stale-cache: serve last good result when getTransactions times out during order bursts
        self._last_good_orders: List[Dict[str, Any]] = []
        self._last_good_filled: List[Dict[str, Any]] = []
        self._last_good_ts: float = 0.0
        self._STALE_CACHE_MAX_AGE = 300  # 5 min — must survive order bursts (112 fire-and-forget → WS saturated)
    
    def set_hammer_client(self, hammer_client, account_key: str):
        """
        Set Hammer client and account key.
        
        Args:
            hammer_client: HammerClient instance
            account_key: Trading account key (e.g., "ALARIC:TOPI002240A7")
        """
        self.hammer_client = hammer_client
        self.account_key = account_key
        logger.info(f"HammerOrdersService initialized with account: {account_key}")
    
    def _fetch_transactions(self, force_refresh: bool = False) -> list:
        """
        Fetch raw transactions from Hammer Pro.
        Returns list of raw transaction dicts, or None on failure/timeout.
        
        Includes a single retry on timeout — after an order burst (100+ fire-and-forget),
        the WebSocket response queue is clogged with tradeCommandNew confirmations.
        A brief pause + retry often succeeds once the queue drains.
        """
        if not self.hammer_client or not self.account_key or not self.hammer_client.is_connected():
            return None  # Not connected → same as timeout for callers
        
        cmd = {
            "cmd": "getTransactions",
            "accountKey": self.account_key,
            "changesOnly": False
        }
        if force_refresh:
            cmd["forceRefresh"] = True
        
        # First attempt
        response = self.hammer_client.send_command_and_wait(
            cmd, wait_for_response=True, timeout=3.0
        )
        
        # If timeout, retry ONCE after brief pause (let WS drain order responses)
        if response is None:
            import time as _t
            _t.sleep(0.3)  # 300ms breathing room
            cmd2 = dict(cmd)  # fresh copy (new reqID will be assigned)
            response = self.hammer_client.send_command_and_wait(
                cmd2, wait_for_response=True, timeout=3.0
            )
        
        if not response or response.get('success') != 'OK':
            return None  # Signal failure (caller decides cache)
        
        result = response.get('result', {})
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            return result.get('transactions', [])
        return []

    def get_orders(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch open orders from Hammer Pro.
        Returns only OPEN orders (status == Open, IsOpen == True).
        """
        try:
            transactions_data = self._fetch_transactions(force_refresh)
            
            if transactions_data is None:
                # Timeout — serve stale cache
                age = time.time() - self._last_good_ts
                if self._last_good_orders and age < self._STALE_CACHE_MAX_AGE:
                    logger.warning(f"Failed to get transactions (timeout), serving {len(self._last_good_orders)} cached open orders ({age:.0f}s old)")
                    return self._last_good_orders
                logger.warning("Failed to get transactions, no cache")
                return []
            
            open_orders = [txn for txn in transactions_data if self._is_open_order(txn)]
            
            normalized = []
            for order in open_orders:
                n = self._normalize_order(order)
                if n:
                    normalized.append(n)
            
            logger.info(f"Fetched {len(normalized)} open orders from Hammer")
            self._last_good_orders = normalized
            self._last_good_ts = time.time()
            return normalized
            
        except Exception as e:
            logger.error(f"Error fetching orders from Hammer: {e}", exc_info=True)
            age = time.time() - self._last_good_ts
            if self._last_good_orders and age < self._STALE_CACHE_MAX_AGE:
                logger.warning(f"Serving {len(self._last_good_orders)} cached orders ({age:.0f}s old) after error")
                return self._last_good_orders
            return []

    def get_all_orders(self, force_refresh: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch ALL orders (open + filled + cancelled) from Hammer Pro.
        Returns dict with 'open_orders' and 'filled_orders'.
        This is the method the UI should use to show both tabs.
        """
        try:
            transactions_data = self._fetch_transactions(force_refresh)
            
            if transactions_data is None:
                age = time.time() - self._last_good_ts
                if self._last_good_orders and age < self._STALE_CACHE_MAX_AGE:
                    logger.warning(f"Timeout, serving cached open={len(self._last_good_orders)}, filled={len(self._last_good_filled)}")
                    return {
                        'open_orders': self._last_good_orders,
                        'filled_orders': self._last_good_filled
                    }
                return {'open_orders': [], 'filled_orders': []}
            
            open_orders = []
            filled_orders = []
            
            for txn in transactions_data:
                status = (
                    txn.get('StatusID') or txn.get('statusID') or
                    txn.get('Status') or txn.get('status') or ''
                ).upper()
                is_open = txn.get('IsOpen') or txn.get('isOpen', False)
                
                normalized = self._normalize_order(txn)
                if not normalized:
                    continue
                
                if status == 'OPEN' or is_open:
                    open_orders.append(normalized)
                elif status == 'FILLED':
                    filled_orders.append(normalized)
                # CANCELED, REJECTED etc. are silently skipped
            
            logger.info(f"Fetched {len(open_orders)} open + {len(filled_orders)} filled orders from Hammer")
            
            # Cache
            self._last_good_orders = open_orders
            self._last_good_filled = filled_orders
            self._last_good_ts = time.time()
            
            return {'open_orders': open_orders, 'filled_orders': filled_orders}
            
        except Exception as e:
            logger.error(f"Error fetching all orders from Hammer: {e}", exc_info=True)
            age = time.time() - self._last_good_ts
            if self._last_good_orders and age < self._STALE_CACHE_MAX_AGE:
                return {
                    'open_orders': self._last_good_orders,
                    'filled_orders': getattr(self, '_last_good_filled', [])
                }
            return {'open_orders': [], 'filled_orders': []}

    def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Alias for get_orders() for compatibility with XNL engine and janall/orders.
        Returns same open-order list (order_id, action, symbol, etc.).
        """
        return self.get_orders()

    def get_filled_orders(self) -> List[Dict[str, Any]]:
        """
        Fetch filled orders from Hammer Pro.
        Uses get_all_orders() to avoid a duplicate getTransactions call.
        """
        return self.get_all_orders().get('filled_orders', [])
    
    def _is_open_order(self, txn: Dict[str, Any]) -> bool:
        """
        Check if transaction is an open order.
        
        Args:
            txn: Transaction data from Hammer
            
        Returns:
            True if order is open
        """
        # Check status
        status = (
            txn.get('StatusID') or
            txn.get('statusID') or
            txn.get('Status') or
            txn.get('status') or
            ''
        ).upper()
        
        # Check IsOpen flag if available
        is_open = txn.get('IsOpen') or txn.get('isOpen', False)
        
        # Open orders have status "Open" or IsOpen=True
        return status == 'OPEN' or is_open
    
    def _normalize_order(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize Hammer order to internal schema.
        
        Args:
            order: Raw order data from Hammer
            
        Returns:
            Normalized order dict or None if invalid
        """
        try:
            # Extract symbol
            symbol = (
                order.get('Symbol') or
                order.get('symbol') or
                order.get('Sym') or
                order.get('sym')
            )
            
            if not symbol:
                return None
            
            # Normalize symbol from Hammer format to display format
            display_symbol = SymbolMapper.to_display_symbol(symbol)
            
            # Extract side (BUY or SELL)
            action = (
                order.get('Action') or
                order.get('action') or
                ''
            ).upper()
            
            if action in ['BUY', 'BUY_TO_COVER', 'COVER']:
                side = 'BUY'
            elif action in ['SELL', 'SELL_SHORT', 'SHORT']:
                side = 'SELL'
            else:
                # Default to BUY if unclear
                side = 'BUY'
            
            # Extract quantity
            quantity = (
                order.get('QTY') or
                order.get('qty') or
                order.get('Quantity') or
                order.get('quantity') or
                order.get('RemainingQTY') or
                order.get('remainingQTY') or
                0.0
            )
            quantity = float(quantity) if quantity else 0.0
            
            # Extract order type
            order_type = (
                order.get('OrderType') or
                order.get('orderType') or
                order.get('Type') or
                order.get('type') or
                'MARKET'
            ).upper()
            
            # Extract price (limit price for limit orders)
            price = (
                order.get('LimitPrice') or
                order.get('limitPrice') or
                order.get('Price') or
                order.get('price') or
                None
            )
            price = float(price) if price else None
            
            # Extract status
            status = (
                order.get('StatusID') or
                order.get('statusID') or
                order.get('Status') or
                order.get('status') or
                'UNKNOWN'
            ).upper()
            
            # Extract order ID
            order_id = (
                order.get('OrderID') or
                order.get('orderID') or
                order.get('OrderId') or
                order.get('orderId') or
                str(order.get('OrderID', ''))
            )
            
            # Extract timestamp
            timestamp = 0.0
            time_str = (
                order.get('TransactTime') or
                order.get('transactTime') or
                order.get('CreationTime') or
                order.get('creationTime') or
                ''
            )
            if time_str:
                try:
                    # Attempt to parse common formats
                    from datetime import datetime
                    if 'T' in time_str:
                        # ISO format
                        dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                        timestamp = dt.timestamp()
                    else:
                        # "YYYY-MM-DD HH:MM:SS"
                        dt = datetime.strptime(time_str[:19], '%Y-%m-%d %H:%M:%S')
                        timestamp = dt.timestamp()
                except:
                    pass
            # ── Resolve tag from Redis ──
            order_id_str = str(order_id) if order_id else ''
            tag = self._get_order_tag_from_redis(order_id_str) if order_id_str else None

            # Extract filled quantity — Hammer Pro API uses 'FilledQTY' per docs
            filled_qty = float(
                order.get('FilledQTY') or
                order.get('filledQTY') or
                order.get('FilledQuantity') or
                order.get('CumulativeQTY') or
                order.get('filled_qty') or
                0
            )
            
            # Extract remaining quantity
            remaining_qty = float(
                order.get('RemainingQTY') or
                order.get('remainingQTY') or
                order.get('remaining_qty') or
                0
            )
            # If remaining not provided, calculate from total - filled
            if remaining_qty == 0 and quantity > 0 and filled_qty > 0:
                remaining_qty = max(0, quantity - filled_qty)
            elif remaining_qty == 0 and status == 'OPEN':
                remaining_qty = quantity  # No fills yet
            
            # Extract fill price if available
            filled_price = float(
                order.get('FilledPrice') or
                order.get('filledPrice') or
                order.get('AvgFillPrice') or
                0
            )
            
            # Extract exact fill timestamp (FilledDT from Hammer Pro)
            filled_dt = (
                order.get('FilledDT') or
                order.get('filledDT') or
                ''
            )
            
            # Extract individual fill breakdown (Hammer Pro provides Fills array)
            # Each fill: {"FillID": "...", "QTY": 250.0, "Price": 1.4399, "FillDT": "..."}
            individual_fills = []
            raw_fills = order.get('Fills') or order.get('fills') or []
            for rf in raw_fills:
                try:
                    individual_fills.append({
                        'fill_id': rf.get('FillID', rf.get('fillID', '')),
                        'qty': float(rf.get('QTY', rf.get('qty', 0))),
                        'price': float(rf.get('Price', rf.get('price', 0))),
                        'fill_dt': rf.get('FillDT', rf.get('fillDT', '')),
                    })
                except (ValueError, TypeError):
                    continue
            
            # Determine proper display status
            if status == 'FILLED':
                display_status = 'FILLED'
            elif status == 'CANCELED':
                display_status = 'CANCELED'
            elif status == 'REJECTED':
                display_status = 'REJECTED'
            elif filled_qty > 0 and filled_qty >= quantity and quantity > 0:
                display_status = 'FILLED'  # Fully filled even if StatusID not yet updated
            elif filled_qty > 0:
                display_status = 'PARTIAL'  # Partially filled
            elif status == 'OPEN' or order.get('IsOpen') or order.get('isOpen', False):
                display_status = 'PENDING'
            else:
                display_status = status

            return {
                'symbol': display_symbol,  # Use normalized display symbol
                'side': side,
                'action': side,            # Alias
                'quantity': quantity,
                'qty': quantity,          # Alias
                'price': price,
                'limit_price': price,     # Alias
                'order_type': order_type,
                'status': display_status,
                'order_id': order_id_str,
                'tag': tag,               # Strategy tag (e.g., KARBOTU, MM, LT_TRIM)
                'timestamp': timestamp,
                'source': 'HAMMER',
                'filled_qty': filled_qty,
                'filled_price': filled_price,
                'filled_dt': filled_dt,            # Exact fill timestamp from broker
                'individual_fills': individual_fills,  # Per-partial-fill breakdown
                'remaining_qty': remaining_qty
            }
            
        except Exception as e:
            logger.error(f"Error normalizing order: {e}", exc_info=True)
            return None

    def _get_order_tag_from_redis(self, order_id: str) -> Optional[str]:
        """Read strategy tag for an order from Redis."""
        try:
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if redis and order_id:
                key = f"hammer:order_tag:{order_id}"
                tag = redis.get(key)
                if tag:
                    return tag if isinstance(tag, str) else tag.decode('utf-8')
        except Exception:
            pass
        return None

# ============================================================================
# Global Instance Management
# ============================================================================

_hammer_orders_service: Optional[HammerOrdersService] = None

def get_hammer_orders_service() -> Optional[HammerOrdersService]:
    """Get global Hammer orders service instance"""
    return _hammer_orders_service

def set_hammer_orders_service(hammer_client, account_key: str):
    """
    Set Hammer client for orders service.
    
    Args:
        hammer_client: HammerClient instance
        account_key: Trading account key
    """
    global _hammer_orders_service
    if not _hammer_orders_service:
        _hammer_orders_service = HammerOrdersService()
    _hammer_orders_service.set_hammer_client(hammer_client, account_key)
    logger.info(f"Hammer orders service initialized for account: {account_key}")
