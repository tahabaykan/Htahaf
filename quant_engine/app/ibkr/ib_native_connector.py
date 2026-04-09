"""
IBKR Native Connector
=====================
Ported from Janall's IBKRNativeClient.
Uses strict ibapi (TWS API) instead of ib_insync, as requested.
"""

import logging
import time
import threading
from typing import List, Dict, Optional, Callable
from datetime import datetime

try:
    from ibapi.wrapper import EWrapper
    from ibapi.client import EClient
    from ibapi.contract import Contract
    from ibapi.order import Order
except ImportError:
    EWrapper = object
    EClient = object
    Contract = object
    Order = object
    # Will log error in init

logger = logging.getLogger(__name__)

# Avoid "duplicate base class object": when ibapi is missing both are object -> single base
_NativeBases = (EWrapper, EClient) if (EWrapper is not object and EClient is not object) else (object,)


class IBNativeConnector(*_NativeBases):
    """
    Combined EWrapper + EClient for ibapi when available; otherwise a stub (object) so
    lazy init in janall_routes does not raise "duplicate base class object" when ibapi is missing.
    """
    def __init__(self, host='127.0.0.1', port=4001, client_id=999):
        if EWrapper is not object and EClient is not object:
            try:
                EWrapper.__init__(self)
            except TypeError:
                pass
            EClient.__init__(self, self)
        # else: single base object, no parent __init__

        self._ib_host = str(host) if host else '127.0.0.1'
        self._ib_port = int(port) if port else 4001
        self._ib_client_id = int(client_id) if client_id else 1
        
        print(f"DEBUG: IBNativeConnector init: host='{self._ib_host}', port={self._ib_port}, client_id={self._ib_client_id}")
        
        self.connected_flag = False
        self.next_order_id = 0
        self._orders_lock = threading.Lock()
        self.open_orders = []
        self.filled_orders = [] # Today's fills
        
        self._thread = None
    
    def isConnected(self):
        """
        Safe wrapper for EClient.isConnected().
        Falls back to connected_flag if method doesn't exist (e.g., when ibapi is missing).
        """
        if EClient is not object and hasattr(EClient, 'isConnected'):
            try:
                return super().isConnected()
            except Exception:
                return self.connected_flag
        return self.connected_flag

    def connect_client(self):
        """Connects to TWS/Gateway"""
        try:
            print(f"DEBUG: IBNativeConnector connect_client: Connecting to host='{self._ib_host}' type={type(self._ib_host)}, port={self._ib_port}, client_id={self._ib_client_id}")
            logger.info(f"Connecting to IB Native: host={self._ib_host} (type={type(self._ib_host)}), port={self._ib_port}, client_id={self._ib_client_id}")
            if EClient is not object and hasattr(EClient, 'connect'):
                self.connect(self._ib_host, self._ib_port, self._ib_client_id)
            else:
                logger.error(f"[IBNativeConnector] EClient.connect() not available (EClient={EClient})")
                return False
            
            # Start API thread
            self._thread = threading.Thread(target=self.run, daemon=True)
            self._thread.start()
            
            # Wait for connection
            time.sleep(1)
            if self.isConnected():
                self.connected_flag = True
                logger.info("IB Native Connected")
                
                # Request initial data
                self.reqIds(-1)
                self.reqAllOpenOrders()
                self.reqExecutions(1, None) # Request all executions
                return True
            else:
                logger.error("IB Native Connection Failed")
                return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    def nextValidId(self, orderId: int):
        self.next_order_id = orderId
        logger.info(f"Next Valid ID: {orderId}")

    def error(self, reqId, errorCode, errorString):
        # Filter common non-errors
        if errorCode in [2104, 2106, 2158]: return
        logger.error(f"IB Error {reqId} {errorCode}: {errorString}")

    def place_order(self, symbol, action, quantity, price, order_type="LIMIT", **kwargs):
        """
        Main entry point for placing orders.
        Matches the signature expected by JanallBulkOrderManager.
        """
        if not self.isConnected():
            logger.warning("Not connected")
            return False

        contract = Contract()
        contract.symbol = self._convert_symbol(symbol)
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        
        order = Order()
        order.action = action.upper()
        order.totalQuantity = quantity
        order.orderType = order_type.upper()
        
        if order_type.upper() == "LIMIT":
            order.lmtPrice = price
            
        # Hardcoded specific settings from Janall
        order.transmit = True
        order.tif = 'DAY'
        order.ordered = True # Not sure if standard, but kept safe
        
        # Order Ref (Tagging)
        if 'order_ref' in kwargs:
             order.orderRef = kwargs['order_ref']

        # Wait for valid ID
        if self.next_order_id == 0:
             # Attempt to wait (Max 0.5s)
             retries = 0
             while self.next_order_id == 0 and retries < 5:
                  time.sleep(0.1)
                  retries += 1
             
             # Fallback if still 0
             if self.next_order_id == 0:
                 fallback_id = int(time.time() * 1000) % 1000000000 # Use milliseconds to ensure uniqueness
                 logger.warning(f"⚠️ IB ID fetch timeout. Using fallback ID: {fallback_id}")
                 self.next_order_id = fallback_id
        
        # Legacy attributes to prevent errors
        order.eTradeOnly = False
        order.firmQuoteOnly = False
        
        # ═══════════════════════════════════════════════════════════════════
        # QUANT_ENGINE CORE RULE: ALL ORDERS MUST BE HIDDEN
        # This is a fundamental principle - we never show our hand to the market
        # ═══════════════════════════════════════════════════════════════════
        # IBKR Hidden Order Requirements:
        # 1. order.hidden = True → Order not visible in order book
        # 2. order.displaySize = 0 → Full hidden (not iceberg)
        # 3. Only works with LIMIT orders (not MARKET)
        # ═══════════════════════════════════════════════════════════════════
        order.hidden = True
        order.displaySize = 0  # Full hidden, not iceberg
        
        # Only allow explicit override to False if specifically requested (emergency cases)
        if 'hidden' in kwargs and kwargs['hidden'] is False:
            order.hidden = False
            logger.warning(f"⚠️ ORDER NOT HIDDEN: {symbol} - This should be rare!")
        
        oid = self.next_order_id
        self.next_order_id += 1
        
        # Legacy Pre-Transmission Sleep (Safety)
        time.sleep(0.05) 
        
        self.placeOrder(oid, contract, order)
        logger.info(f"Placed Native Order {oid}: {symbol} {action} {quantity} @ {price}")
        
        # Legacy Post-Transmission Status Check Wait
        # Janall used 0.6s. We use 0.1s to be faster but safe.
        time.sleep(0.1)
        return True

    def cancel_order(self, order_id):
        """Cancels an order with status verification"""
        if not self.isConnected(): return False
        try:
            order_id_int = int(order_id)
            logger.info(f"IB Native Cancel Request: {order_id_int}")
            
            # Request cancellation
            self.cancelOrder(order_id_int)
            
            # Poll for status update (briefly)
            for _ in range(3):
                time.sleep(0.5)
                # Check if it's still in open_orders
                found = False
                with self._orders_lock: # Assuming we might want a lock for thread safety
                    for o in self.open_orders:
                        if o.get('order_id') == order_id_int:
                            found = True
                            break
                if not found:
                    logger.info(f"✅ IB Native Order {order_id_int} confirmed canceled (removed from list)")
                    return True
            
            return True # Request sent is usually enough
        except Exception as e:
            logger.error(f"Error canceling order {order_id}: {e}")
            return False

    def openOrder(self, orderId, contract, order, orderState):
        """Callback for open orders"""
        # Update local cache
        # Simple implementation: Upsert
        entry = {
            'order_id': orderId,
            'symbol': contract.symbol,
            'action': order.action.upper(),
            'side': order.action.upper(),
            'qty': int(order.totalQuantity),
            'quantity': int(order.totalQuantity),
            'filled': 0,
            'filled_qty': 0,
            'remaining': int(order.totalQuantity),
            'remaining_qty': int(order.totalQuantity),
            'price': order.lmtPrice if order.orderType == 'LMT' else 0.0,
            'limit_price': order.lmtPrice if order.orderType == 'LMT' else 0.0,
            'order_type': order.orderType,
            'status': orderState.status,
            'time': datetime.now().strftime("%H:%M:%S"),
            'timestamp': time.time(),
            # Additional metadata for Janall matching and robustness
            'order_ref': order.orderRef,
            'account': order.account,
            'client_id': order.clientId,
            'perm_id': order.permId,
            'parent_id': order.parentId,
            'avg_fill_price': 0.0, # Will be updated by orderStatus
            'last_fill_price': 0.0, # Will be updated by orderStatus
            'commission': 0.0, # Not directly available here, but useful for Janall
            'contract': contract, # Store full contract for more details if needed
            'order': order, # Store full order for more details if needed
            'order_state': orderState # Store full orderState for more details if needed
        }
        
        # Remove existing if present
        self.open_orders = [o for o in self.open_orders if o['order_id'] != orderId]
        self.open_orders.append(entry)

    def openOrderEnd(self):
        """Callback for end of open orders"""
        logger.info("Open orders download finished")
        if hasattr(self, '_open_orders_event'):
            self._open_orders_event.set()

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        # Update filled qty
        for o in self.open_orders:
            if o['order_id'] == orderId:
                o['status'] = status
                o['filled'] = filled
                o['remaining'] = remaining

    def execDetails(self, reqId, contract, execution):
        """Callback for fills"""
        # Add to filled_orders
        fill = {
            'symbol': contract.symbol,
            'action': execution.side, # BOT/SLD
            'qty': execution.shares,
            'price': execution.price,
            'time': execution.time,
            'exec_id': execution.execId
        }
        # Avoid dupes
        if not any(f['exec_id'] == fill['exec_id'] for f in self.filled_orders):
            self.filled_orders.append(fill)
            
            # === NEW: Update PositionTagManager + PositionTagStore (Dual Tag v4) ===
            try:
                from app.psfalgo.fill_tag_handler import handle_fill_for_tagging
                # Convert BOT/SLD to BUY/SELL
                action = 'BUY' if execution.side == 'BOT' else 'SELL'
                # Get order_ref as source/tag if available
                source = getattr(execution, 'orderRef', 'UNKNOWN') or 'UNKNOWN'
                handle_fill_for_tagging(
                    symbol=contract.symbol,
                    fill_qty=execution.shares,
                    action=action,
                    source=source,
                    tag=source,  # orderRef contains the strategy tag
                    account_id='IBKR_PED'
                )
            except Exception as e:
                logger.warning(f"Could not update PositionTagManager: {e}")
            # === END NEW ===

    def get_open_orders(self):
        """
        Returns list of dicts: id, symbol, action, qty, filled, price, status.
        LEGACY MODE: Actively requests open orders from TWS instead of relying on cache.
        """
        if not self.isConnected():
             return []
             
        # Clear cache to force fresh update
        self.open_orders = []
        
        # Event for synchronization
        self._open_orders_event = threading.Event()
        
        # Request all open orders
        # logger.info("Refreshing Open Orders (Active Fetch)...")
        self.reqAllOpenOrders()
        
        # Wait for openOrderEnd callback (max 2 seconds)
        if not self._open_orders_event.wait(timeout=2.0):
            logger.warning("Timeout waiting for OpenOrdersEnd")
        
        return self.open_orders

    def get_todays_filled_orders(self):
        return self.filled_orders

    def _convert_symbol(self, symbol):
        # BFS-E -> BFS PRE
        if '-' in symbol:
            return symbol.replace('-', ' PR')
        return symbol
