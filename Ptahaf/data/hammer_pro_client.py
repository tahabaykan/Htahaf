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
        # Setup logging first
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
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
        
        # ETF sembolleri
        self.etf_symbols = ['SPY', 'TLT', 'IWM', 'PFF', 'KRE']
        
        # Orderbook ve print verilerini tut
        self.orderbooks = {}  # {symbol: {'bids': [], 'asks': []}}
        self.last_prints = {}  # {symbol: [{'price': float, 'size': int, 'timestamp': str}]}
        
    def _format_symbol_for_request(self, symbol):
        """Format symbol for Hammer Pro request"""
        # ETF'ler için direkt sembolü kullan
        if symbol in self.etf_symbols:
            return symbol
            
        # Orijinal sembolü sakla
        orig_symbol = symbol
        
        # "PR" formatını kontrol et
        if " PR" in orig_symbol:
            # "AHL PRF" -> ["AHL", "F"]
            parts = orig_symbol.split(" PR")
            if len(parts) == 2:
                base = parts[0]  # "AHL"
                suffix = parts[1]  # "F"
                formatted = f"{base}-{suffix}"
                self.logger.info(f"Converting {orig_symbol} to {formatted}")
                return formatted
            
        # Eğer özel format bulunamazsa, orijinal sembolü döndür
        # Boşlukları temizle
        return orig_symbol.replace(" ", "")
        
        # Event handlers
        self.on_connect = None
        self.on_disconnect = None
        self.on_market_data = None
        self.on_position_update = None
        self.on_order_update = None
        
    def _get_next_req_id(self):
        """Get next request ID"""
        self.req_id_counter += 1
        return self.req_id_counter
        
    def connect(self):
        """Connect to Hammer Pro WebSocket"""
        try:
            url = f"ws://{self.host}:{self.port}"
            self.logger.info(f"Connecting to Hammer Pro at {url}")
            
            # Create WebSocket connection
            self.ws = websocket.WebSocketApp(
                url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            # Start WebSocket in a separate thread
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            # Wait for connection
            timeout = 10
            start_time = time.time()
            while not self.connected and time.time() - start_time < timeout:
                time.sleep(0.1)
            
            if self.connected:
                self.logger.info("Connected to Hammer Pro WebSocket")
                
                # Get available streamers
                message = {
                    'cmd': 'enumDataStreamers',
                    'reqID': str(self._get_next_req_id())
                }
                self._send_message(message)
                
                return True
            else:
                self.logger.error("Failed to connect to Hammer Pro")
                return False
                
        except Exception as e:
            self.logger.error(f"Error connecting to Hammer Pro: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Hammer Pro"""
        try:
            if self.ws:
                self.ws.close()
            self.connected = False
            self.authenticated = False
            self.logger.info("Disconnected from Hammer Pro")
        except Exception as e:
            self.logger.error(f"Error disconnecting: {e}")
    
    def is_connected(self):
        """Check if connected to Hammer Pro"""
        return self.connected and self.authenticated
    
    def _on_open(self, ws):
        """WebSocket connection opened"""
        self.connected = True
        self.logger.info("WebSocket connected")
        
        # Send authentication
        self._authenticate()
    
    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            self.logger.debug(f"Received message: {data}")
            
            # Handle different message types
            cmd = data.get('cmd', '')
            
            if cmd == 'connect':
                self._handle_connect_response(data)
            elif cmd == 'enumDataStreamers':
                self._handle_enum_data_streamers_response(data)
            elif cmd == 'startDataStreamer':
                self._handle_streamer_response(data)
            elif cmd == 'subscribe':
                self._handle_subscribe_response(data)
            elif cmd == 'L1Update':
                self._handle_market_data_update(data)
            elif cmd == 'balancesUpdate':
                self._handle_balance_update(data)
            elif cmd == 'positionsUpdate':
                self._handle_position_update(data)
            elif cmd == 'ordersUpdate':
                self._handle_order_update(data)
            else:
                self.logger.debug(f"Unhandled message type: {cmd}")
                
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON message: {e}")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
    
    def _on_error(self, ws, error):
        """Handle WebSocket errors"""
        self.logger.error(f"WebSocket error: {error}")
        self.connected = False
        self.authenticated = False
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection close"""
        self.logger.info("WebSocket connection closed")
        self.connected = False
        self.authenticated = False
        if self.on_disconnect:
            self.on_disconnect()
    
    def _authenticate(self):
        """Send authentication to Hammer Pro"""
        try:
            message = {
                'cmd': 'connect',
                'password': self.password
            }
            self._send_message(message)
            self.logger.info("Authentication sent to Hammer Pro")
        except Exception as e:
            self.logger.error(f"Error sending authentication: {e}")
    
    def _handle_connect_response(self, data):
        """Handle authentication response"""
        success = data.get('success', 'fail')
        if success == 'OK':
            self.authenticated = True
            self.logger.info("Successfully authenticated with Hammer Pro")
            
            # Streamer'ı başlat
            message = {
                'cmd': 'startDataStreamer',
                'streamerID': 'ALARICQ'
            }
            self._send_message(message)
            
            if self.on_connect:
                self.on_connect()
                
            # Get available streamers
            message = {
                'cmd': 'enumDataStreamers',
                'reqID': str(self._get_next_req_id())
            }
            self._send_message(message)
        else:
            self.logger.error(f"Authentication failed: {data.get('result', 'Unknown error')}")
            
    def _handle_enum_data_streamers_response(self, data):
        """Handle enumDataStreamers response"""
        try:
            if data.get('success') == 'OK':
                result = data.get('result', [])
                if isinstance(result, list):
                    self.logger.info("Available data streamers:")
                    for streamer in result:
                        if isinstance(streamer, dict):
                            streamer_id = streamer.get('streamerID', '')
                            name = streamer.get('name', '')
                            is_set = streamer.get('isSet', False)
                            self.logger.info(f"- {streamer_id}: {name} {'(Ready)' if is_set else ''}")
                            
                            # Store available streamers
                            if not hasattr(self, 'available_streamers'):
                                self.available_streamers = {}
                            self.available_streamers[streamer_id] = {
                                'name': name,
                                'is_set': is_set
                            }
                else:
                    self.logger.error("Invalid response format from enumDataStreamers")
            else:
                self.logger.error(f"Failed to get data streamers: {data.get('result', 'Unknown error')}")
        except Exception as e:
            self.logger.error(f"Error handling enumDataStreamers response: {e}")
    
    def _handle_streamer_response(self, data):
        """Handle data streamer response"""
        success = data.get('success', 'fail')
        if success == 'OK':
            self.logger.info("Data streamer started successfully")
            
            # Get available streamers again to confirm status
            message = {
                'cmd': 'enumDataStreamers',
                'reqID': str(self._get_next_req_id())
            }
            self._send_message(message)
        else:
            error = data.get('result', 'Unknown error')
            self.logger.error(f"Failed to start data streamer: {error}")
            
            if "does not exist" in str(error):
                # Try to get available streamers
                message = {
                    'cmd': 'enumDataStreamers',
                    'reqID': str(self._get_next_req_id())
                }
                self._send_message(message)
    
    def _handle_subscribe_response(self, data):
        """Handle subscription response"""
        success = data.get('success', 'fail')
        if success == 'OK':
            self.logger.info("Symbol subscription successful")
        else:
            self.logger.error(f"Symbol subscription failed: {data.get('result', 'Unknown error')}")
    
    def _handle_market_data_update(self, data):
        """Handle market data updates"""
        try:
            cmd = data.get('cmd', '')
            result = data.get('result', {})
            formatted_symbol = result.get('sym', '')
            
            if not formatted_symbol:
                return
                
            # Find original symbol from subscriptions
            orig_symbol = None
            for sym, sub_info in self.subscriptions.items():
                if sub_info.get('formatted') == formatted_symbol:
                    orig_symbol = sym
                    break
            
            if not orig_symbol:
                orig_symbol = formatted_symbol  # Fallback to formatted symbol
            
            # Debug için gelen mesajı logla
            self.logger.debug(f"Received market data: {json.dumps(data)}")
            
            # Quote Update
            if cmd in ['quoteUpdate', 'quotesUpdate', 'marketDataUpdate']:
                # Basic market data
                self._handle_l1_update(orig_symbol, formatted_symbol, result)
                
            # Debug için gelen veriyi logla
            elif cmd == 'error':
                self.logger.error(f"Received error from Hammer Pro: {result}")
            else:
                self.logger.debug(f"Received command: {cmd} with data: {json.dumps(data)}")
                    
        except Exception as e:
            self.logger.error(f"Error handling market data update: {e}")
            
    def _handle_l1_update(self, orig_symbol, formatted_symbol, result):
        """Handle L1 market data updates"""
        try:
            # Convert string values to float
            try:
                price = float(result.get('price', 0))
                bid = float(result.get('bid', 0))
                ask = float(result.get('ask', 0))
                size = float(result.get('size', 0))
                volume = float(result.get('volume', 0))
            except (ValueError, TypeError):
                return
            
            # Update market data
            self.market_data[orig_symbol] = {
                'price': price,
                'bid': bid,
                'ask': ask,
                'size': size,
                'volume': volume,
                'timestamp': result.get('timeStamp', datetime.now().isoformat()),
                'is_live': True,
                'last': price,
                'prev_close': result.get('prevClose', 0)
            }
            
            self.logger.debug(f"Updated L1 data for {orig_symbol}: Price={price}, Bid={bid}, Ask={ask}")
            
            if self.on_market_data:
                self.on_market_data(orig_symbol, self.market_data[orig_symbol])
                
        except Exception as e:
            self.logger.error(f"Error handling L1 update: {e}")
            
    def _handle_depth_update(self, formatted_symbol, result):
        """Handle depth (L2) updates"""
        try:
            # Get bid/ask arrays
            bids = result.get('bids', [])  # [[price, size], ...]
            asks = result.get('asks', [])
            
            # Convert to float and sort
            try:
                bids = [(float(p), float(s)) for p, s in bids]
                asks = [(float(p), float(s)) for p, s in asks]
            except (ValueError, TypeError):
                return
                
            # Sort bids descending (highest first)
            bids.sort(reverse=True)
            # Sort asks ascending (lowest first)
            asks.sort()
            
            # Keep only top 7 levels
            self.orderbooks[formatted_symbol] = {
                'bids': bids[:7],
                'asks': asks[:7]
            }
            
            self.logger.debug(f"Updated depth data for {formatted_symbol}")
            
        except Exception as e:
            self.logger.error(f"Error handling depth update: {e}")
            
    def _handle_trade_update(self, formatted_symbol, result):
        """Handle trade (print) updates"""
        try:
            # Get trade data
            try:
                price = float(result.get('price', 0))
                size = float(result.get('size', 0))
            except (ValueError, TypeError):
                return
                
            if price <= 0 or size <= 0:
                return
                
            timestamp = result.get('timeStamp', datetime.now().isoformat())
            
            # Add to prints list
            print_data = {
                'price': price,
                'size': size,
                'timestamp': timestamp
            }
            
            if formatted_symbol not in self.last_prints:
                self.last_prints[formatted_symbol] = []
                
            # Add to front of list and keep only last 10
            self.last_prints[formatted_symbol].insert(0, print_data)
            self.last_prints[formatted_symbol] = self.last_prints[formatted_symbol][:10]
            
            self.logger.debug(f"Added trade for {formatted_symbol}: {size} @ {price}")
            
        except Exception as e:
            self.logger.error(f"Error handling trade update: {e}")
    
    def _handle_balance_update(self, data):
        """Handle balance updates"""
        try:
            # Process balance updates
            pass
        except Exception as e:
            self.logger.error(f"Error handling balance update: {e}")
    
    def _handle_position_update(self, data):
        """Handle position updates"""
        try:
            # Process position updates
            if self.on_position_update:
                self.on_position_update(data)
        except Exception as e:
            self.logger.error(f"Error handling position update: {e}")
    
    def _handle_order_update(self, data):
        """Handle order updates"""
        try:
            # Process order updates
            if self.on_order_update:
                self.on_order_update(data)
        except Exception as e:
            self.logger.error(f"Error handling order update: {e}")
    
    def _send_message(self, message):
        """Send message to Hammer Pro"""
        if self.ws and self.connected:
            try:
                # Add reqID if not present
                if 'reqID' not in message:
                    message['reqID'] = str(self._get_next_req_id())
                
                json_message = json.dumps(message)
                self.ws.send(json_message)
                self.logger.debug(f"Sent message: {message}")
                return True
            except Exception as e:
                self.logger.error(f"Error sending message: {e}")
                return False
        return False
    
    def start_data_streamer(self, streamer_id='ALARICQ'):
        """Start data streamer"""
        try:
            # Check if streamer exists and is ready
            if hasattr(self, 'available_streamers'):
                streamer = self.available_streamers.get(streamer_id)
                if not streamer:
                    available = list(self.available_streamers.keys())
                    self.logger.error(f"Streamer {streamer_id} not found. Available streamers: {available}")
                    if available:
                        streamer_id = available[0]
                        self.logger.info(f"Using first available streamer: {streamer_id}")
                    else:
                        self.logger.error("No streamers available")
                        return False
            
            # Start the streamer
            message = {
                'cmd': 'startDataStreamer',
                'streamerID': streamer_id
            }
            success = self._send_message(message)
            
            if success:
                # Subscribe to ETF symbols
                self.logger.info("Subscribing to ETF symbols...")
                for symbol in self.etf_symbols:
                    self.subscribe_symbol(symbol)
                    
            return success
            
        except Exception as e:
            self.logger.error(f"Error starting data streamer: {e}")
            return False
    
    def subscribe_symbol(self, symbol, streamer_id='ALARICQ'):
        """Subscribe to symbol for market data"""
        try:
            # Format symbol for subscription
            orig_symbol = symbol.strip().upper()
            formatted_symbol = self._format_symbol_for_request(orig_symbol)
            
            # Sembol dönüşümünü kontrol et
            if formatted_symbol == orig_symbol and 'PR' in orig_symbol:
                # Eğer dönüşüm yapılmadıysa ve PR içeriyorsa tekrar dene
                parts = orig_symbol.split(" ")
                if len(parts) >= 2:
                    for i in range(1, len(parts)):
                        if parts[i].startswith("PR"):
                            base = parts[0]
                            suffix = parts[i][2:]  # PR'den sonraki kısım
                            formatted_symbol = f"{base}-{suffix}"
                            break
            
            # Market data için subscribe
            message = {
                'cmd': 'subscribe',
                'sub': 'quotes',  # Market data subscription
                'streamerID': streamer_id,
                'sym': [formatted_symbol],  # Array içinde gönder
                'type': 'all',  # Tüm veri tiplerini iste
                'fields': ['bid', 'ask', 'last', 'volume', 'prevClose']  # İstenen alanlar
            }
            
            # Debug için mesajı logla
            self.logger.debug(f"Sending subscription message: {json.dumps(message)}")
            
            self.logger.info(f"Subscribing to symbol: {orig_symbol} as {formatted_symbol}")
            
            # Mesajı gönder
            success = self._send_message(message)
            
            if success:
                # Store original symbol in subscriptions
                self.subscriptions[orig_symbol] = {
                    'formatted': formatted_symbol,
                    'active': True
                }
                
                # Initialize orderbook and prints containers
                self.orderbooks[formatted_symbol] = {
                    'bids': [],  # [(price, size), ...]
                    'asks': []   # [(price, size), ...]
                }
                self.last_prints[formatted_symbol] = []  # son 10 print
                
                return True
            return False
            
        except Exception as e:
            self.logger.error(f"Error subscribing to symbol {symbol}: {e}")
            return False
    
    def unsubscribe_symbol(self, symbol, streamer_id='ALARICQ'):
        """Unsubscribe from symbol"""
        try:
            message = {
                'cmd': 'unsubscribe',
                'sub': 'L1',
                'streamerID': streamer_id,
                'sym': symbol
            }
            self._send_message(message)
            if symbol in self.subscriptions:
                del self.subscriptions[symbol]
            return True
        except Exception as e:
            self.logger.error(f"Error unsubscribing from symbol {symbol}: {e}")
            return False
    
    def get_market_data(self, symbols):
        """Get market data for one or more symbols"""
        if isinstance(symbols, (str, bytes)):
            # Single symbol
            data = self.market_data.get(symbols, {})
            if not data:
                return {
                    symbols: {
                        'price': 0,
                        'bid': 0,
                        'ask': 0,
                        'size': 0,
                        'volume': 0,
                        'timestamp': datetime.now().isoformat(),
                        'is_live': False,
                        'last': 0
                    }
                }
            return {symbols: data}
        else:
            # List of symbols
            result = {}
            for symbol in symbols:
                data = self.market_data.get(symbol, {})
                if not data:
                    result[symbol] = {
                        'price': 0,
                        'bid': 0,
                        'ask': 0,
                        'size': 0,
                        'volume': 0,
                        'timestamp': datetime.now().isoformat(),
                        'is_live': False,
                        'last': 0
                    }
                else:
                    result[symbol] = data
            return result
    
    def get_subscriptions(self):
        """Get list of subscribed symbols"""
        return list(self.subscriptions.keys())
        
    def get_orderbook(self, symbol):
        """Get orderbook for a symbol"""
        formatted_symbol = self._format_symbol_for_request(symbol.strip().upper())
        return self.orderbooks.get(formatted_symbol, {'bids': [], 'asks': []})
        
    def get_last_prints(self, symbol):
        """Get last 10 prints for a symbol"""
        formatted_symbol = self._format_symbol_for_request(symbol.strip().upper())
        return self.last_prints.get(formatted_symbol, []) 