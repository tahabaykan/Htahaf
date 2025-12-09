import websocket
import json
import logging
import time
import threading
from datetime import datetime

class HammerProDirectClient:
    def __init__(self, host='127.0.0.1', port=16400, password=''):
        # WebSocket URL
        self.url = f"ws://{host}:{port}"
        self.password = password
        
        # Logging setup
        self.logger = logging.getLogger('hammer_pro_direct')
        self.logger.setLevel(logging.DEBUG)
        
        # Data containers
        self.market_data = {}  # {symbol: {price, bid, ask, etc.}}
        self.orderbooks = {}   # {symbol: {bids: [], asks: []}}
        self.last_prints = {}  # {symbol: [{price, size, timestamp}, ...]}
        
        # Connection state
        self.ws = None
        self.connected = False
        self.authenticated = False
        self.req_id_counter = 0
        
        # Callbacks
        self.on_market_data = None
        
    def _get_next_req_id(self):
        """Get next request ID"""
        self.req_id_counter += 1
        return str(self.req_id_counter)
        
    def _send_command(self, command, req_id=None):
        """Send a command to WebSocket"""
        if req_id:
            command["reqID"] = req_id
        try:
            self.ws.send(json.dumps(command))
            self.logger.debug(f"Sent command: {command}")
            return True
        except Exception as e:
            self.logger.error(f"Error sending command: {e}")
            return False
            
    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            # Handle CONNECTED message
            if message.strip() == "CONNECTED":
                self.logger.info("WebSocket CONNECTED")
                return
                
            # Parse JSON message
            data = json.loads(message)
            cmd = data.get("cmd", "")
            success = data.get("success", "")
            result = data.get("result", {})
            req_id = data.get("reqID", "")
            
            self.logger.debug(f"Received message: {data}")
            
            # Handle different message types
            if cmd == "connect":
                if success == "OK":
                    self.authenticated = True
                    self.logger.info("Authenticated with Hammer Pro")
                    # Start data streamer
                    self._send_command({
                        "cmd": "startDataStreamer",
                        "streamerID": "ALARICQ"
                    })
                else:
                    self.logger.error(f"Authentication failed: {result}")
                    
            elif cmd == "startDataStreamer":
                if success == "OK":
                    self.logger.info("Data streamer started")
                else:
                    self.logger.error(f"Failed to start data streamer: {result}")
                    
            elif cmd == "subscribe":
                if success == "OK":
                    self.logger.info("Subscription successful")
                else:
                    self.logger.error(f"Subscription failed: {result}")
                    
            elif cmd == "marketDataUpdate":
                symbol = result.get("sym", "")
                if not symbol:
                    return
                    
                try:
                    # Parse market data
                    price = float(result.get("price", 0))
                    bid = float(result.get("bid", 0))
                    ask = float(result.get("ask", 0))
                    last = float(result.get("last", price))
                    volume = float(result.get("volume", 0))
                    prev_close = float(result.get("prevClose", 0))
                    
                    # Update market data
                    self.market_data[symbol] = {
                        "price": price,
                        "bid": bid,
                        "ask": ask,
                        "last": last,
                        "volume": volume,
                        "prev_close": prev_close,
                        "timestamp": datetime.now().isoformat(),
                        "is_live": True
                    }
                    
                    # Handle orderbook if available
                    if "book" in result:
                        book = result["book"]
                        bids = [(float(p), float(s)) for p, s in book.get("bids", [])]
                        asks = [(float(p), float(s)) for p, s in book.get("asks", [])]
                        
                        # Sort and keep top 7 levels
                        bids.sort(reverse=True)
                        asks.sort()
                        
                        self.orderbooks[symbol] = {
                            "bids": bids[:7],
                            "asks": asks[:7]
                        }
                        
                    # Handle trades if available
                    if "trades" in result:
                        trades = result["trades"]
                        if trades and isinstance(trades, list):
                            for trade in trades[:10]:  # Keep last 10 trades
                                trade_data = {
                                    "price": float(trade.get("price", 0)),
                                    "size": float(trade.get("size", 0)),
                                    "timestamp": trade.get("timeStamp", datetime.now().isoformat())
                                }
                                
                                if symbol not in self.last_prints:
                                    self.last_prints[symbol] = []
                                    
                                self.last_prints[symbol].insert(0, trade_data)
                                self.last_prints[symbol] = self.last_prints[symbol][:10]
                                
                    # Notify callback if set
                    if self.on_market_data:
                        self.on_market_data(symbol, self.market_data[symbol])
                        
                except Exception as e:
                    self.logger.error(f"Error processing market data for {symbol}: {e}")
                    
        except json.JSONDecodeError:
            pass
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
            
    def _on_error(self, ws, error):
        """Handle WebSocket errors"""
        self.logger.error(f"WebSocket error: {error}")
        self.connected = False
        self.authenticated = False
        
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        self.logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.connected = False
        self.authenticated = False
        
    def _on_open(self, ws):
        """Handle WebSocket open"""
        self.connected = True
        self.logger.info("WebSocket opened")
        
        # Send authentication
        auth_cmd = {
            "cmd": "connect",
            "pwd": self.password
        }
        self._send_command(auth_cmd)
        
    def connect(self):
        """Connect to Hammer Pro"""
        try:
            self.ws = websocket.WebSocketApp(
                self.url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )
            
            # Start WebSocket in a thread
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            # Wait for connection
            timeout = 10
            start_time = time.time()
            while not self.connected and time.time() - start_time < timeout:
                time.sleep(0.1)
                
            return self.connected
            
        except Exception as e:
            self.logger.error(f"Error connecting: {e}")
            return False
            
    def disconnect(self):
        """Disconnect from Hammer Pro"""
        if self.ws:
            self.ws.close()
            
    def subscribe_symbol(self, symbol):
        """Subscribe to market data for a symbol"""
        if not self.connected or not self.authenticated:
            self.logger.error("Not connected/authenticated")
            return False
            
        # Format symbol for request
        if " PR" in symbol:
            base, suffix = symbol.split(" PR")
            formatted_symbol = f"{base}-{suffix}"
        else:
            formatted_symbol = symbol
            
        # Subscribe command
        cmd = {
            "cmd": "subscribe",
            "sub": "marketData",
            "streamerID": "ALARICQ",
            "sym": [formatted_symbol]
        }
        
        return self._send_command(cmd)
        
    def get_market_data(self, symbol):
        """Get current market data for a symbol"""
        return self.market_data.get(symbol, {})
        
    def get_orderbook(self, symbol):
        """Get current orderbook for a symbol"""
        return self.orderbooks.get(symbol, {"bids": [], "asks": []})
        
    def get_last_prints(self, symbol):
        """Get last trades for a symbol"""
        return self.last_prints.get(symbol, [])