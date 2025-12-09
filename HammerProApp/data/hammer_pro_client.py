import websocket
import json
import threading
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Callable

class HammerProClient:
    """
    WebSocket client for Hammer Pro API integration
    """
    
    def __init__(self, host='127.0.0.1', port=8080, password=''):
        self.host = host
        self.port = port
        self.password = password
        self.ws = None
        self.connected = False
        self.authenticated = False
        self.req_id_counter = 0
        self.callbacks = {}
        self.subscriptions = {}
        self.market_data = {}
        self.positions = {}
        self.orders = {}
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Event callbacks
        self.on_connect = None
        self.on_disconnect = None
        self.on_market_data = None
        self.on_position_update = None
        self.on_order_update = None
        
    def connect(self):
        """Connect to Hammer Pro WebSocket API"""
        try:
            url = f"ws://{self.host}:{self.port}"
            self.logger.info(f"Connecting to Hammer Pro at {url}")
            
            self.ws = websocket.WebSocketApp(
                url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # Start WebSocket connection in a separate thread
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            # Wait for connection
            timeout = 10
            start_time = time.time()
            while not self.connected and time.time() - start_time < timeout:
                time.sleep(0.1)
                
            if not self.connected:
                raise Exception("Failed to connect to Hammer Pro")
                
            # Authenticate
            self._authenticate()
            
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            raise
    
    def _authenticate(self):
        """Authenticate with Hammer Pro using password"""
        auth_msg = {
            "cmd": "connect",
            "pwd": self.password,
            "reqID": self._get_next_req_id()
        }
        
        self._send_message(auth_msg)
        
        # Wait for authentication response
        timeout = 10
        start_time = time.time()
        while not self.authenticated and time.time() - start_time < timeout:
            time.sleep(0.1)
            
        if not self.authenticated:
            raise Exception("Authentication failed")
    
    def _get_next_req_id(self):
        """Get next request ID"""
        self.req_id_counter += 1
        return str(self.req_id_counter)
    
    def _send_message(self, message):
        """Send message to Hammer Pro"""
        if self.ws and self.connected:
            try:
                self.ws.send(json.dumps(message))
                self.logger.debug(f"Sent: {message}")
            except Exception as e:
                self.logger.error(f"Failed to send message: {e}")
    
    def _on_open(self, ws):
        """WebSocket connection opened"""
        self.connected = True
        self.logger.info("Connected to Hammer Pro WebSocket")
        if self.on_connect:
            self.on_connect()
    
    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            self.logger.debug(f"Received: {data}")
            
            cmd = data.get('cmd', '')
            
            if cmd == 'connect':
                self._handle_connect_response(data)
            elif cmd == 'L1Update':
                self._handle_l1_update(data)
            elif cmd == 'L2Update':
                self._handle_l2_update(data)
            elif cmd == 'balancesUpdate':
                self._handle_balances_update(data)
            elif cmd == 'positionsUpdate':
                self._handle_positions_update(data)
            elif cmd == 'transactionsUpdate':
                self._handle_transactions_update(data)
            elif cmd == 'closing':
                self._handle_closing(data)
            else:
                # Handle other responses
                req_id = data.get('reqID')
                if req_id and req_id in self.callbacks:
                    callback = self.callbacks.pop(req_id)
                    callback(data)
                    
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
    
    def _handle_connect_response(self, data):
        """Handle authentication response"""
        if data.get('success') == 'OK':
            self.authenticated = True
            self.logger.info("Successfully authenticated with Hammer Pro")
        else:
            self.logger.error(f"Authentication failed: {data.get('result', 'Unknown error')}")
    
    def _handle_l1_update(self, data):
        """Handle Level 1 market data updates"""
        result = data.get('result', {})
        symbol = result.get('sym', '')
        
        if symbol:
            self.market_data[symbol] = {
                'price': result.get('price', 0),
                'bid': result.get('bid', 0),
                'ask': result.get('ask', 0),
                'size': result.get('size', 0),
                'volume': result.get('volume', 0),
                'timestamp': result.get('timeStamp', '')
            }
            
            if self.on_market_data:
                self.on_market_data(symbol, self.market_data[symbol])
    
    def _handle_l2_update(self, data):
        """Handle Level 2 market data updates"""
        result = data.get('result', {})
        symbol = result.get('sym', '')
        
        if symbol:
            # Store L2 data
            if symbol not in self.market_data:
                self.market_data[symbol] = {}
            
            self.market_data[symbol].update({
                'bids': result.get('bids', []),
                'asks': result.get('asks', []),
                'type': data.get('type', ''),
                'timestamp': result.get('timeStamp', '')
            })
    
    def _handle_balances_update(self, data):
        """Handle account balances updates"""
        result = data.get('result', {})
        account_key = result.get('accountKey', '')
        
        if account_key:
            # Store balances data
            self.balances = result
            self.logger.info(f"Balances updated for account: {account_key}")
    
    def _handle_positions_update(self, data):
        """Handle positions updates"""
        result = data.get('result', {})
        account_key = result.get('accountKey', '')
        
        if account_key:
            positions = result.get('positions', [])
            self.positions[account_key] = positions
            
            if self.on_position_update:
                self.on_position_update(account_key, positions)
    
    def _handle_transactions_update(self, data):
        """Handle transactions/orders updates"""
        result = data.get('result', {})
        account_key = result.get('accountKey', '')
        
        if account_key:
            transactions = result.get('transactions', [])
            self.orders[account_key] = transactions
            
            if self.on_order_update:
                self.on_order_update(account_key, transactions)
    
    def _handle_closing(self, data):
        """Handle application closing notification"""
        self.logger.info("Hammer Pro is closing")
        self.connected = False
        self.authenticated = False
    
    def _on_error(self, ws, error):
        """WebSocket error handler"""
        self.logger.error(f"WebSocket error: {error}")
        self.connected = False
        self.authenticated = False
    
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket connection closed"""
        self.logger.info("Disconnected from Hammer Pro")
        self.connected = False
        self.authenticated = False
        if self.on_disconnect:
            self.on_disconnect()
    
    def disconnect(self):
        """Disconnect from Hammer Pro"""
        if self.ws:
            self.ws.close()
        self.connected = False
        self.authenticated = False
    
    # Market Data Methods
    def enum_data_streamers(self, callback=None):
        """Get available data streamers"""
        msg = {
            "cmd": "enumDataStreamers",
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def start_data_streamer(self, streamer_id, refresh=None, callback=None):
        """Start a data streamer"""
        msg = {
            "cmd": "startDataStreamer",
            "streamerID": streamer_id,
            "reqID": self._get_next_req_id()
        }
        
        if refresh is not None:
            msg["refresh"] = refresh
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def subscribe_l1(self, streamer_id, symbols, transient=False, callback=None):
        """Subscribe to Level 1 market data"""
        msg = {
            "cmd": "subscribe",
            "streamerID": streamer_id,
            "sub": "L1",
            "sym": symbols if isinstance(symbols, list) else [symbols],
            "transient": transient,
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def subscribe_l2(self, streamer_id, symbols, changes=True, max_rows=None, callback=None):
        """Subscribe to Level 2 market data"""
        msg = {
            "cmd": "subscribe",
            "streamerID": streamer_id,
            "sub": "L2",
            "sym": symbols if isinstance(symbols, list) else [symbols],
            "changes": changes,
            "reqID": self._get_next_req_id()
        }
        
        if max_rows is not None:
            msg["maxRows"] = max_rows
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def unsubscribe(self, streamer_id, sub_type, symbols="*", callback=None):
        """Unsubscribe from market data"""
        msg = {
            "cmd": "unsubscribe",
            "streamerID": streamer_id,
            "sub": sub_type,
            "sym": symbols,
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    # Trading Account Methods
    def enum_trading_accounts(self, callback=None):
        """Get available trading accounts"""
        msg = {
            "cmd": "enumTradingAccounts",
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def start_trading_account(self, account_key, callback=None):
        """Start a trading account"""
        msg = {
            "cmd": "startTradingAccount",
            "accountKey": account_key,
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def get_balances(self, account_key, callback=None):
        """Get account balances"""
        msg = {
            "cmd": "getBalances",
            "accountKey": account_key,
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def get_positions(self, account_key, force_refresh=False, callback=None):
        """Get account positions"""
        msg = {
            "cmd": "getPositions",
            "accountKey": account_key,
            "forceRefresh": force_refresh,
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def get_transactions(self, account_key, force_refresh=False, changes_only=False, callback=None):
        """Get account transactions/orders"""
        msg = {
            "cmd": "getTransactions",
            "accountKey": account_key,
            "forceRefresh": force_refresh,
            "changesOnly": changes_only,
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    # Portfolio Methods
    def enum_ports(self, callback=None):
        """Get available portfolios"""
        msg = {
            "cmd": "enumPorts",
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def enum_port_symbols(self, port_id, detailed=False, callback=None):
        """Get symbols in a portfolio"""
        msg = {
            "cmd": "enumPortSymbols",
            "portID": port_id,
            "detailed": detailed,
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def add_to_port(self, port_id, symbols, new=False, name=None, callback=None):
        """Add symbols to portfolio"""
        msg = {
            "cmd": "addToPort",
            "portID": port_id,
            "new": new,
            "reqID": self._get_next_req_id()
        }
        
        if name:
            msg["name"] = name
        
        if isinstance(symbols, list):
            msg["items"] = [{"sym": sym} for sym in symbols]
        else:
            msg["sym"] = symbols
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    # Historical Data Methods
    def backfill(self, streamer_id, symbol, data_type, backfill_type="incremental", callback=None):
        """Backfill historical data"""
        msg = {
            "cmd": "backfill",
            "streamerID": streamer_id,
            "sym": symbol,
            "type": data_type,
            "backfillType": backfill_type,
            "reqID": self._get_next_req_id()
        }
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def get_candles(self, symbol, candle_size, start_date=None, end_date=None, 
                   reg_hours_only=False, adjust_for_dividends=False, last_few=None, callback=None):
        """Get historical candle data"""
        msg = {
            "cmd": "getCandles",
            "sym": symbol,
            "candleSize": candle_size,
            "reqID": self._get_next_req_id()
        }
        
        if start_date:
            msg["startDate"] = start_date
        if end_date:
            msg["endDate"] = end_date
        if reg_hours_only:
            msg["regHoursOnly"] = reg_hours_only
        if adjust_for_dividends:
            msg["adjustForDividends"] = adjust_for_dividends
        if last_few:
            msg["lastFew"] = last_few
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    def get_ticks(self, symbol, start_date=None, end_date=None, trades_only=False, 
                 reg_hours_only=False, last_few=None, callback=None):
        """Get historical tick data"""
        msg = {
            "cmd": "getTicks",
            "sym": symbol,
            "reqID": self._get_next_req_id()
        }
        
        if start_date:
            msg["startDate"] = start_date
        if end_date:
            msg["endDate"] = end_date
        if trades_only:
            msg["tradesOnly"] = trades_only
        if reg_hours_only:
            msg["regHoursOnly"] = reg_hours_only
        if last_few:
            msg["lastFew"] = last_few
        
        if callback:
            self.callbacks[msg["reqID"]] = callback
        
        self._send_message(msg)
    
    # Utility Methods
    def get_market_data(self, symbol):
        """Get current market data for a symbol"""
        return self.market_data.get(symbol, {})
    
    def get_all_market_data(self):
        """Get all current market data"""
        return self.market_data.copy()
    
    def get_positions_data(self, account_key=None):
        """Get positions data"""
        if account_key:
            return self.positions.get(account_key, [])
        return self.positions.copy()
    
    def get_orders_data(self, account_key=None):
        """Get orders/transactions data"""
        if account_key:
            return self.orders.get(account_key, [])
        return self.orders.copy()
    
    def is_connected(self):
        """Check if connected and authenticated"""
        return self.connected and self.authenticated 

    def send_message(self, message_type, data=None, callback=None):
        """Send a message to Hammer Pro"""
        if not self.connected:
            self.logger.error("Not connected to Hammer Pro")
            return False
        
        try:
            # Create message
            message = {
                'cmd': message_type,
                'reqID': str(self._get_next_req_id())
            }
            
            # Add data if provided
            if data:
                message.update(data)
            
            # Store callback for response
            if callback:
                self.callbacks[message['reqID']] = callback
            
            # Convert to JSON
            json_message = json.dumps(message)
            
            # Send message
            self.ws.send(json_message)
            self.logger.debug(f"Sent message: {message_type}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}")
            return False 