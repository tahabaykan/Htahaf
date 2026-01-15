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

class IBNativeConnector(EWrapper, EClient):
    def __init__(self, host='127.0.0.1', port=4001, client_id=999):
        EClient.__init__(self, self)
        # EWrapper init is implicit or passed
        
        self.host = host
        self.port = port
        self.client_id = client_id
        
        self.connected_flag = False
        self.next_order_id = 0
        self.open_orders = []
        self.filled_orders = [] # Today's fills
        
        self._thread = None

    def connect_client(self):
        """Connects to TWS/Gateway"""
        try:
            self.connect(self.host, self.port, self.client_id)
            
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
        order.hidden = False # Default to False unless specified? (Legacy defaults to True for Bulk?)
        # Janall legacy defaults hidden=True in some wrappers, but generic place_order defaults False?
        # Let's check **kwargs for 'hidden'
        if 'hidden' in kwargs and kwargs['hidden']:
             order.hidden = True
        
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
        if not self.isConnected(): return False
        try:
            val_id = int(order_id)
            self.cancelOrder(val_id)
            logger.info(f"Cancelled Order {val_id}")
            return True
        except ValueError:
            logger.error(f"Invalid Order ID: {order_id}")
            return False

    def openOrder(self, orderId, contract, order, orderState):
        """Callback for open orders"""
        # Update local cache
        # Simple implementation: Upsert
        entry = {
            'order_id': orderId,
            'symbol': contract.symbol,
            'action': order.action,
            'qty': order.totalQuantity,
            'filled': 0, # orderState doesn't always have filled, Execution does
            'price': order.lmtPrice,
            'status': orderState.status,
            'time': datetime.now().strftime("%H:%M:%S") # Approximate
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
