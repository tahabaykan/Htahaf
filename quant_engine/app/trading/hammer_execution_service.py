"""Hammer Execution Service
Places BUY orders via Hammer Pro API (SEMI_AUTO mode only).
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper
from app.event_driven.decision_engine.shadow_observer import shadow_observer
from app.trading.hammer_fills_listener import get_hammer_fills_listener


# ═══════════════════════════════════════════════════════════════════
# MARKET HOURS GUARD
# US Regular Trading Hours: 9:30 AM - 4:00 PM ET
# After-hours fills are CATASTROPHIC — wide spreads cause massive
# losses (e.g. WRB-F SELL @$18.15 when TT was ~$20, 2026-03-11).
# ═══════════════════════════════════════════════════════════════════
def _is_us_market_open() -> bool:
    """Check if US stock market is currently in regular trading hours.
    
    Returns True if current time is between 9:30 AM and 4:00 PM Eastern Time.
    Uses zoneinfo for proper EST/EDT daylight saving handling.
    """
    try:
        from zoneinfo import ZoneInfo
        et_now = datetime.now(ZoneInfo('America/New_York'))
        # Regular hours: 9:30 AM - 4:00 PM ET
        time_val = et_now.hour * 100 + et_now.minute  # e.g. 930, 1600
        return 930 <= time_val < 1600
    except Exception:
        # If timezone handling fails, allow trading (fail-open for safety)
        logger.warning("[MARKET_HOURS] Could not determine market hours, allowing order")
        return True


class HammerExecutionService:
    """
    Service to place orders via Hammer Pro.
    
    READ-ONLY for positions/orders, WRITE for order placement.
    Safety: One order per symbol per cycle.
    """
    
    def __init__(self, hammer_client=None, account_key: Optional[str] = None):
        """
        Initialize execution service.
        
        Args:
            hammer_client: HammerClient instance (optional, can be set later)
            account_key: Trading account key (optional, can be set later)
        """
        self.hammer_client = hammer_client
        self.account_key = account_key
        
        # Track orders per symbol per cycle (prevent duplicates)
        # self._recent_orders: Dict[str, datetime] = {}  # Removed as per user request
        # self._order_cooldown_seconds = 5  # Removed as per user request
        
        # Shadow Mode: ONLY active when Lifeless Mode is enabled
        # Default: LIVE MODE (real order execution)
        # User can enable Lifeless Mode via UI toggle for simulation
        logger.info("HammerExecutionService initialized (Default: LIVE MODE)")

        # Register listener if client provided
        if self.hammer_client:
            self._register_fills_listener()

    
    def _register_fills_listener(self):
        """Register the fills listener as an observer"""
        try:
            listener = get_hammer_fills_listener()
            self.hammer_client.add_observer(listener.on_message)
            logger.info("HammerFillsListener registered as observer")

            # After listener registration, trigger a one-shot transactions snapshot for recovery.
            # This uses Hammer API getTransactions so that even if the app / network was down,
            # we can re-log today's fills from Hammer's local history (similar to IBKR fill recovery).
            try:
                if self.account_key and self.hammer_client.is_connected():
                    from app.core.logger import logger as _logger
                    _logger.info("[HammerExecutionService] Requesting transactions snapshot for fill recovery...")
                    # changesOnly=False → full set; HammerFillsListener will dedupe by FillID.
                    self.hammer_client.send_command(
                        {
                            "cmd": "getTransactions",
                            "accountKey": self.account_key,
                            "changesOnly": False,
                        },
                        wait_for_response=False,
                    )
            except Exception as rec_err:
                logger.warning(f"Hammer fill recovery request failed (non-fatal): {rec_err}")
        except Exception as e:
            logger.error(f"Failed to register HammerFillsListener: {e}")

    def set_hammer_client(self, hammer_client, account_key: str):
        """
        Set Hammer client and account key.
        
        Args:
            hammer_client: HammerClient instance
            account_key: Trading account key (e.g., "ALARIC:TOPI002240A7")
        """
        self.hammer_client = hammer_client
        self.account_key = account_key
        self._register_fills_listener()
        logger.info(f"HammerExecutionService configured for account: {account_key}")
    
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_style: str = "LIMIT",
        hidden: bool = True,
        strategy_tag: str = "UNKNOWN",
        fire_and_forget: bool = False,  # If True, don't wait for response - faster but no confirmation
        routing: str = "",  # Venue routing: "" = SMART/Auto, "NSDQ", "ARCA", "NYSE", etc.
    ) -> Dict[str, Any]:
        """
        Place a BUY/SELL order via Hammer Pro.
        Mirrors Janall logic (Hidden by default).
        
        Args:
            symbol: Symbol (display format)
            side: 'BUY' or 'SELL' (or 'SHORT')
            quantity: Order quantity
            price: Limit price
            order_style: Order style (LIMIT, MARKET, etc.)
            hidden: Whether to hide the order (SpInstruction: Hidden)
            strategy_tag: Strategy identifier (e.g., LT, MM, JFIN) for logging
            
        Returns:
            Execution result dict
        """
        if not self.hammer_client:
            return {'success': False, 'message': 'Hammer client not set'}
        
        if not self.account_key:
            return {'success': False, 'message': 'Account key not set'}
        
        if not self.hammer_client.is_connected():
            return {'success': False, 'message': 'Hammer client not connected'}
        
        # ═══════════════════════════════════════════════════════════════
        # MARKET HOURS GUARD — Block ALL orders outside regular hours
        # After-hours fills are catastrophic due to wide spreads.
        # WRB-F 2026-03-11: SELL @$18.15 when TT ~$20 (after-hours)
        # ═══════════════════════════════════════════════════════════════
        if not _is_us_market_open():
            logger.warning(
                f"🚫 [MARKET_CLOSED] Order BLOCKED — market is closed! "
                f"{symbol} {side} {int(quantity)} @ ${price:.4f} (Tag: {strategy_tag})"
            )
            return {
                'success': False,
                'message': 'Market is closed — order blocked to prevent after-hours fill at bad price'
            }
        
        # ═══════════════════════════════════════════════════════════════
        # ORDER GUARD — EXCLUDED LIST CHECK (LAST BARRIER)
        # This catches ANY excluded symbol regardless of which engine
        # generated the order. qe_excluded.csv is the single source of truth.
        # ═══════════════════════════════════════════════════════════════
        try:
            from app.trading.order_guard import is_order_allowed
            allowed, guard_reason = is_order_allowed(
                symbol=symbol, side=side, quantity=quantity,
                tag=strategy_tag, account_id='HAMPRO'
            )
            if not allowed:
                logger.error(
                    f"🚫 [ORDER_GUARD] HAMMER BLOCKED: {symbol} {side} {int(quantity)} "
                    f"@ ${price:.4f} (Tag: {strategy_tag}) — {guard_reason}"
                )
                return {'success': False, 'message': f'ORDER_GUARD BLOCKED: {guard_reason}'}
        except Exception as guard_err:
            logger.warning(f"[ORDER_GUARD] Guard check failed (allowing order): {guard_err}")
        
        # Safety: Cooldown Removed as per user request (IBKR has none)
        now = datetime.now()
        
        # Normalize Side — map engine actions to Hammer Pro API values
        # Our engines produce: BUY, ADD, SELL, SHORT, ADD_SHORT
        # Hammer Pro API accepts: Buy, Sell, Short
        side_upper = side.upper()
        ACTION_MAP = {
            'BUY': 'Buy',
            'ADD': 'Buy',            # ADD = mevcut LONG'a ekle → Buy
            'SELL': 'Sell',
            'SHORT': 'Short',
            'ADD_SHORT': 'Short',    # ADD_SHORT = mevcut SHORT'a ekle → Short
        }
        action = ACTION_MAP.get(side_upper)
        if action is None:
            logger.error(f"[HAMMER] ❌ REJECTED: Unknown action '{side}' for {symbol} — order NOT sent")
            return {'success': False, 'message': f'Unknown action: {side}'}

        # LIFELESS MODE GUARD - Only simulate when user activates lifeless mode
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        is_simulation = fabric.is_lifeless_mode() if fabric else False
        
        if is_simulation:
            logger.info(
                f"🛡️ [SIMULATION - LIFELESS MODE] Would place {action.upper()} order: "
                f"{symbol} {quantity} @ ${price:.4f} {order_style} (Tag: {strategy_tag})"
            )
            # self._recent_orders[symbol] = now # Removed
            shadow_observer.record_churn_event(symbol, 'INTENT')
            return {
                'success': True,
                'order_id': f"SIM_{int(now.timestamp()*1000)}",
                'message': f'[SIMULATION] Order would be placed: {action} {quantity} @ ${price:.4f}',
                'error': None
            }
        
        try:
            # Convert symbol
            hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
            
            # ═══════════════════════════════════════════════════════════════════
            # HAMMER PRO API - HIDDEN ORDER CONFIGURATION
            # ═══════════════════════════════════════════════════════════════════
            # Per Hammer Pro API Documentation:
            # - SpInstructions: "Hidden" → Order not visible in order book
            # - DisplaySize: 0 → Full hidden (not iceberg)
            # - Routing: "" → Empty string for default routing (per Janall)
            # - OrderType: "Limit" → Hidden only works with limit orders
            # ═══════════════════════════════════════════════════════════════════
            sp_instructions = "Hidden" if hidden else "None"
            
            # OrderCmd
            order_cmd = {
                "cmd": "tradeCommandNew",
                "accountKey": self.account_key,
                "order": {
                    "ConditionalType": "None",
                    "Legs": [{
                        "Symbol": hammer_symbol,
                        "Action": action,
                        "Quantity": int(quantity),
                        "OrderType": order_style.capitalize() if 'limit' in order_style.lower() else "Limit",
                        "LimitPrice": float(price),
                        "LimitPriceType": "None",
                        "StopPrice": 0,
                        "StopPriceType": "None",
                        "Routing": routing or "",  # "" = SMART/Auto, or specific venue like "NSDQ", "ARCA"
                        "DisplaySize": 0,  # 0 = Full hidden (not iceberg)
                        "TIF": "Day",
                        "TIFDate": datetime.now().strftime("%Y-%m-%d"),
                        "SpInstructions": sp_instructions,  # "Hidden" or "None"
                        "CostMultiplier": 1
                    }]
                }
            }
            
            if order_style.lower() == 'market':
                 order_cmd['order']['Legs'][0]['OrderType'] = 'Market'
                 order_cmd['order']['Legs'][0]['LimitPrice'] = 0

            # Log execution attempt — comprehensive format
            try:
                from app.core.order_context_logger import format_order_sent_log, get_order_context
                _ctx = get_order_context(symbol)
                logger.info(format_order_sent_log(
                    symbol=symbol, action=action.upper(), quantity=int(quantity),
                    price=price, tag=strategy_tag, account_id='HAMPRO',
                    ctx=_ctx
                ))
            except Exception:
                logger.info(
                    f"[EXECUTING HAMMER] Placing {action.upper()} order: "
                    f"{symbol} ({hammer_symbol}) {int(quantity)} @ ${price:.4f} (Hidden={hidden}, Tag={strategy_tag})"
                )
            
            # Fire-and-forget mode: Don't wait for response - faster but no confirmation
            if fire_and_forget:
                sent = self.hammer_client._send_command(order_cmd)
                if sent:
                    logger.info(f"[EXECUTION SENT] Order sent (fire-and-forget): {action} {quantity} @ {price}")
                    # Write pending tag to Redis (will be matched when transactionsUpdate arrives with OrderID)
                    self._write_pending_tag_to_redis(symbol, action, int(quantity), strategy_tag)
                    # ── OrderLifecycleTracker ──
                    try:
                        from app.monitoring.order_lifecycle_tracker import get_order_lifecycle_tracker
                        get_order_lifecycle_tracker().on_order_sent(
                            symbol=symbol, action=action.upper(), price=price,
                            lot=int(quantity), tag=strategy_tag, account_id='HAMPRO',
                        )
                    except Exception:
                        pass
                    return {
                        'success': True,
                        'order_id': None,  # Unknown until confirmed
                        'message': f'Order Sent (fire-and-forget): {action} {quantity} @ {price}'
                    }
                else:
                    return {'success': False, 'message': 'Failed to send command'}
            
            # Normal mode: Wait for response
            response = self.hammer_client.send_command_and_wait(
                order_cmd,
                wait_for_response=True,
                timeout=3.0
            )
            
            if not response or response.get('success') != 'OK':
                error_msg = response.get('result', 'Timeout or Unknown Error') if response else 'No Response'
                
                # RETRY ONCE on 'No Response' (transient disconnect)
                if error_msg == 'No Response':
                    import time as _time
                    logger.warning(f"[EXECUTION] Hammer No Response for {symbol} — retrying in 2s...")
                    _time.sleep(2.0)
                    
                    # Check connection is still alive
                    if self.hammer_client.is_connected():
                        response2 = self.hammer_client.send_command_and_wait(
                            order_cmd,
                            wait_for_response=True,
                            timeout=5.0  # Longer timeout on retry
                        )
                        if response2 and response2.get('success') == 'OK':
                            logger.info(f"[EXECUTION] Retry SUCCESS for {symbol}")
                            response = response2
                        else:
                            retry_err = response2.get('result', 'No Response') if response2 else 'No Response'
                            logger.error(f"[EXECUTION FAILED] Hammer retry also failed: {retry_err}")
                            return {'success': False, 'message': f'Hammer Error (after retry): {retry_err}'}
                    else:
                        logger.error(f"[EXECUTION FAILED] Hammer disconnected, cannot retry")
                        return {'success': False, 'message': 'Hammer disconnected during retry'}
                else:
                    logger.error(f"[EXECUTION FAILED] Hammer: {error_msg}")
                    return {'success': False, 'message': f'Hammer Error: {error_msg}'}

            # Success
            # self._recent_orders[symbol] = now # Removed
            
            # Extract ID
            order_id = None
            result = response.get('result', {})
            if isinstance(result, dict):
                 order_data = result.get('order', {})
                 if isinstance(order_data, dict):
                     order_id = order_data.get('OrderID')
            
            # Register Tag (in-memory for fills listener + Redis for UI)
            if order_id:
                 get_hammer_fills_listener().register_order(str(order_id), strategy_tag)
                 self._write_order_tag_to_redis(str(order_id), strategy_tag)

            logger.info(f"[EXECUTION SUCCESS] Order Placed: {order_id} (Tag={strategy_tag})")
            
            # ── OrderLifecycleTracker: record order sent ──
            try:
                from app.monitoring.order_lifecycle_tracker import get_order_lifecycle_tracker
                get_order_lifecycle_tracker().on_order_sent(
                    symbol=symbol, action=action.upper(), price=price,
                    lot=int(quantity), tag=strategy_tag, account_id='HAMPRO',
                    order_id=str(order_id) if order_id else '',
                )
            except Exception:
                pass

            return {
                'success': True,
                'order_id': order_id,
                'message': f'Order Placed {action} {quantity} @ {price}'
            }
            
        except Exception as e:
            logger.error(f"[EXECUTION ERROR] {e}", exc_info=True)
            return {'success': False, 'message': str(e)}

    def _write_order_tag_to_redis(self, order_id: str, tag: str):
        """Write order_id -> tag mapping to Redis for UI display."""
        try:
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if redis and order_id and tag:
                key = f"hammer:order_tag:{order_id}"
                redis.set(key, tag, ex=86400)  # 24 hour TTL
                logger.debug(f"[ORDER_TAG] Written {order_id} -> {tag}")
        except Exception as e:
            logger.warning(f"[ORDER_TAG] Redis write failed: {e}")

    def _write_pending_tag_to_redis(self, symbol: str, action: str, qty: int, tag: str):
        """Write pending tag for fire-and-forget orders (matched by symbol+action+qty when OrderID arrives).
        
        CRITICAL FIX: Also writes a symbol+action-only key (without qty) as fallback
        for partial fills where the fill qty doesn't match the order qty.
        """
        try:
            import json
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if redis and tag:
                # Primary: exact match by symbol+action+qty
                key = f"hammer:pending_tag:{symbol}:{action}:{qty}"
                redis.set(key, tag, ex=300)  # 5 min TTL (order should arrive quickly)
                
                # FALLBACK: symbol+action only (for partial fills with different qty)
                # Strip venue suffix (__V0_NYSE etc) to store the clean base tag
                base_tag = tag.split('__V')[0] if '__V' in tag else tag
                fallback_key = f"hammer:pending_tag:{symbol}:{action}:ANY"
                redis.set(fallback_key, base_tag, ex=300)
                
                logger.debug(f"[ORDER_TAG] Pending tag: {symbol} {action} {qty} -> {tag} (+ ANY fallback: {base_tag})")
        except Exception as e:
            logger.warning(f"[ORDER_TAG] Redis pending write failed: {e}")

    def isConnected(self) -> bool:
        """Native interface shim for Hammer"""
        return self.hammer_client and self.hammer_client.is_connected()

    def place_order_venue_routed(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_style: str = "LIMIT",
        hidden: bool = True,
        strategy_tag: str = "UNKNOWN",
        fire_and_forget: bool = False,
    ) -> Dict[str, Any]:
        """
        Place order with venue-based routing using truth tick analysis.
        
        ≤ 200 lot → single SMART order (same as place_order)
        > 200 lot → split into 200-lot chunks, route to dominant venue
        
        Returns result of first chunk (or single order for ≤200 lot).
        All chunks are logged individually.
        """
        from app.trading.venue_router import get_venue_router
        
        router = get_venue_router()
        chunks = router.route_order(symbol, int(quantity))
        
        if len(chunks) == 1:
            # Single order — just use place_order with default routing
            return self.place_order(
                symbol=symbol, side=side, quantity=quantity,
                price=price, order_style=order_style, hidden=hidden,
                strategy_tag=strategy_tag, fire_and_forget=fire_and_forget,
                routing=chunks[0].routing_hammer,
            )
        
        # Multiple chunks — send each with venue routing
        first_result = None
        for chunk in chunks:
            route_label = chunk.routing_hammer or "SMART"
            chunk_tag = f"{strategy_tag}__V{chunk.chunk_index}_{route_label}"
            
            logger.info(
                f"[VENUE_ROUTE] {symbol} {side} chunk {chunk.chunk_index+1}/{len(chunks)}: "
                f"{chunk.qty} lot @ ${price:.2f} → route={route_label}"
            )
            
            result = self.place_order(
                symbol=symbol, side=side, quantity=chunk.qty,
                price=price, order_style=order_style, hidden=hidden,
                strategy_tag=chunk_tag, fire_and_forget=fire_and_forget,
                routing=chunk.routing_hammer,
            )
            
            if first_result is None:
                first_result = result
            
            # If first chunk fails, don't send remaining
            if not result.get('success', False) and chunk.chunk_index == 0:
                logger.warning(
                    f"[VENUE_ROUTE] {symbol}: First chunk failed, skipping remaining {len(chunks)-1} chunks"
                )
                break
        
        return first_result or {'success': False, 'message': 'No chunks sent'}

    def get_todays_filled_orders(self) -> List[Dict[str, Any]]:
        """
        Get today's filled orders.
        Native interface shim for Hammer.
        """
        from app.trading.hammer_orders_service import get_hammer_orders_service
        service = get_hammer_orders_service()
        if service:
             return service.get_filled_orders()
        return []

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an order via Hammer Pro.
        
        Args:
            order_id: The ID of the order to cancel
            
        Returns:
            Result dict
        """
        if not self.hammer_client:
            return {'success': False, 'message': 'Hammer client not set'}
            
        # LIFELESS MODE GUARD
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        is_simulation = fabric.is_lifeless_mode() if fabric else False
        
        if is_simulation:
            logger.info(f"🛡️ [SIMULATION - LIFELESS MODE] Would cancel order {order_id}")
            return {'success': True, 'message': '[SIMULATION] Order Cancelled'}
            
        try:
            cmd = {
                "cmd": "tradeCommandCancel",
                "accountKey": self.account_key,
                "orderID": order_id
            }
            
            logger.info(f"[HAMMER CANCEL] Cancelling order {order_id}")
            response = self.hammer_client.send_command_and_wait(cmd, timeout=5.0)
            
            if response and response.get('success') == 'OK':
                logger.info(f"[HAMMER CANCEL] Success: {order_id}")
                return {'success': True, 'message': 'Order Cancelled'}
            else:
                msg = response.get('result') if response else "No response"
                logger.error(f"[HAMMER CANCEL] Failed: {msg}")
                return {'success': False, 'message': f"Cancel Failed: {msg}"}
                
        except Exception as e:
            logger.error(f"[HAMMER CANCEL] Error: {e}")
            return {'success': False, 'message': str(e)}
    
    def modify_order(self, order_id: str, new_price: float) -> Dict[str, Any]:
        """
        Modify an existing order's price using Hammer Pro's tradeCommandModify.
        
        This is an ATOMIC operation (single API call) — no risk of cancel succeeding
        but place failing. The order keeps the same OrderID.
        
        Per Hammer Pro API docs:
        "NOTE: you specify only the changed parameters for the modified order."
        
        Args:
            order_id: The ID of the order to modify
            new_price: New limit price
            
        Returns:
            Result dict with success status
        """
        if not self.hammer_client:
            return {'success': False, 'message': 'Hammer client not set'}
        
        if not self.hammer_client.is_connected():
            return {'success': False, 'message': 'Hammer client not connected'}
        
        # LIFELESS MODE GUARD
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        is_simulation = fabric.is_lifeless_mode() if fabric else False
        
        if is_simulation:
            logger.info(f"🛡️ [SIMULATION - LIFELESS MODE] Would modify order {order_id} → ${new_price:.4f}")
            return {'success': True, 'message': '[SIMULATION] Order Modified'}
        
        try:
            cmd = {
                "cmd": "tradeCommandModify",
                "accountKey": self.account_key,
                "order": {
                    "OrderID": str(order_id),
                    "Legs": [{
                        "LimitPrice": float(new_price)
                    }]
                }
            }
            
            logger.info(f"[HAMMER MODIFY] Modifying order {order_id} → ${new_price:.4f}")
            response = self.hammer_client.send_command_and_wait(cmd, timeout=5.0)
            
            if response and isinstance(response, dict) and response.get('success') == 'OK':
                logger.info(f"[HAMMER MODIFY] Success: {order_id} → ${new_price:.4f}")
                return {'success': True, 'message': f'Order Modified: ${new_price:.4f}'}
            else:
                msg = response.get('result') if isinstance(response, dict) else str(response) if response else "No response"
                logger.error(f"[HAMMER MODIFY] Failed: {msg}")
                return {'success': False, 'message': f"Modify Failed: {msg}"}
                
        except Exception as e:
            logger.error(f"[HAMMER MODIFY] Error: {e}")
            return {'success': False, 'message': str(e)}
    
    def cancel_all_orders(self, side: Optional[str] = None) -> Dict[str, Any]:
        """
        Cancel all open orders in Hammer Pro.
        
        Uses hammer_orders_service.get_orders() to fetch open orders (already working),
        then cancels them in batch using tradeCommandCancel.
        
        Args:
            side: Optional filter - 'BUY', 'SELL', or None for all
            
        Returns:
            Dict with success status and cancelled order IDs
        """
        try:
            if not self.hammer_client or not self.hammer_client.is_connected():
                return {'success': False, 'message': 'Hammer not connected', 'cancelled': []}
            
            if not self.account_key:
                return {'success': False, 'message': 'No account key', 'cancelled': []}
            
            # Step 1: Get open orders using global hammer_orders_service (preserves stale-cache)
            from app.trading.hammer_orders_service import get_hammer_orders_service
            orders_service = get_hammer_orders_service()
            if not orders_service:
                # Fallback: create disposable instance
                from app.trading.hammer_orders_service import HammerOrdersService
                orders_service = HammerOrdersService(self.hammer_client)
                orders_service.account_key = self.account_key
            open_orders = orders_service.get_orders()
            
            logger.info(f"[HAMMER CANCEL ALL] Found {len(open_orders)} open orders via orders_service")
            
            if not open_orders:
                logger.info(f"[HAMMER CANCEL ALL] No open orders to cancel")
                return {'success': True, 'message': 'No open orders', 'cancelled': []}
            
            # Filter by side if specified
            if side:
                side_upper = side.upper()
                filtered_orders = []
                for order in open_orders:
                    action = (order.get('action') or order.get('Action') or '').upper()
                    if side_upper == 'BUY' and action in ['BUY', 'COVER', 'BUY_TO_COVER']:
                        filtered_orders.append(order)
                    elif side_upper == 'SELL' and action in ['SELL', 'SHORT', 'SELL_SHORT']:
                        filtered_orders.append(order)
                open_orders = filtered_orders
                logger.info(f"[HAMMER CANCEL ALL] After side filter ({side}): {len(open_orders)} orders")
            
            if not open_orders:
                return {'success': True, 'message': f'No {side} orders to cancel', 'cancelled': []}
            
            # Extract order IDs
            open_order_ids = []
            for order in open_orders:
                order_id = order.get('order_id') or order.get('OrderID') or order.get('orderId')
                if order_id:
                    open_order_ids.append(str(order_id))
            
            if not open_order_ids:
                logger.info(f"[HAMMER CANCEL ALL] No order IDs extracted")
                return {'success': True, 'message': 'No order IDs found', 'cancelled': []}
            
            # Step 2: Cancel all in batch using tradeCommandCancel
            cancel_cmd = {
                "cmd": "tradeCommandCancel",
                "accountKey": self.account_key,
                "orderID": open_order_ids  # API accepts array!
            }
            
            logger.info(f"[HAMMER CANCEL ALL] Cancelling {len(open_order_ids)} orders: {open_order_ids[:5]}...")
            
            cancel_response = self.hammer_client.send_command_and_wait(cancel_cmd, timeout=5.0)
            
            # Handle case where response is not a dict
            if cancel_response and isinstance(cancel_response, dict) and cancel_response.get('success') == 'OK':
                logger.info(f"[HAMMER CANCEL ALL] Success: {len(open_order_ids)} orders cancelled")
                return {
                    'success': True, 
                    'message': f'Cancelled {len(open_order_ids)} orders',
                    'cancelled': open_order_ids
                }
            else:
                msg = cancel_response.get('result') if isinstance(cancel_response, dict) else str(cancel_response) if cancel_response else "No response"
                logger.error(f"[HAMMER CANCEL ALL] Failed: {msg}")
                return {'success': False, 'message': f'Cancel failed: {msg}', 'cancelled': []}
                
        except Exception as e:
            logger.error(f"[HAMMER CANCEL ALL] Error: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'cancelled': []}
    
    def clear_cooldown(self, symbol: Optional[str] = None):
        """
        Clear cooldown for a symbol (or all symbols).
        NOTE: Cooldown system was removed per user request. This is now a no-op.
        
        Args:
            symbol: Symbol to clear, or None to clear all
        """
        # _recent_orders dict was removed — cooldown system disabled
        logger.debug(f"clear_cooldown called (no-op: cooldown system removed)")


# ============================================================================
# Global Instance Management
# ============================================================================

_hammer_execution_service: Optional[HammerExecutionService] = None

def get_hammer_execution_service() -> Optional[HammerExecutionService]:
    """Get global Hammer execution service instance"""
    return _hammer_execution_service

def set_hammer_execution_service(hammer_client, account_key: str):
    """
    Set Hammer client for execution service.
    
    Args:
        hammer_client: HammerClient instance
        account_key: Trading account key
    """
    global _hammer_execution_service
    if not _hammer_execution_service:
        _hammer_execution_service = HammerExecutionService()
    _hammer_execution_service.set_hammer_client(hammer_client, account_key)
    logger.info(f"Hammer execution service initialized for account: {account_key}")

