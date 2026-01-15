"""app/live/hammer_client.py

Hammer Pro WebSocket client - headless, engine-driven.
No GUI, no CSV, no UI callbacks - pure API integration.
"""

import websocket
import json
import threading
import time
import uuid
from typing import Optional, Callable, Dict, Any
from datetime import datetime

from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper


class HammerClient:
    """
    Hammer Pro WebSocket client.
    
    Responsibilities:
    - WebSocket connection management
    - Authentication
    - Command sending/receiving
    - Reconnection logic
    - Request/response handling
    
    NO trading logic, NO CSV, NO UI callbacks.
    """
    
    def __init__(
        self,
        host: str = '127.0.0.1',
        port: int = 16400,
        password: Optional[str] = None,
        account_key: str = "ALARIC:TOPI002240A7"
    ):
        """
        Initialize Hammer client.
        
        Args:
            host: Hammer Pro host
            port: Hammer Pro port
            password: API password
            account_key: Trading account key
        """
        self.host = host
        self.port = port
        self.password = password
        self.account_key = account_key
        self.url = None
        self.ws = None
        self.connected = False
        self.authenticated = False
        
        # Request/response handling
        self._pending_responses: Dict[str, Any] = {}
        self._pending_lock = threading.Lock()
        
        # Message callbacks (set by feed/execution modules)
        self.on_message_callback: Optional[Callable] = None
        
        # Reconnection
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10  # Increased for stability
        self._reconnect_delay = 3.0  # Faster reconnect
        self._should_reconnect = True  # Auto-reconnect enabled by default
        
        # Snapshot cache (for prevClose, change, dividend from getSymbolSnapshot)
        self._snapshot_cache: Dict[str, Dict[str, Any]] = {}
        self._snapshot_cache_lock = threading.Lock()
    
    def connect(self) -> bool:
        """
        Connect to Hammer Pro.
        
        Returns:
            True if connected successfully
        """
        if not self.password:
            logger.error("❌ [HAMMER_CONNECT] Hammer API password not set")
            logger.error("   💡 Set HAMMER_PASSWORD in .env file or environment variable")
            return False
        
        try:
            self.url = f"ws://{self.host}:{self.port}"
            logger.info(f"🔌 [HAMMER_CONNECT] Connecting to Hammer Pro: {self.url}")
            logger.info(f"   Host: {self.host}, Port: {self.port}")
            
            # Reset connection state
            self.connected = False
            self.authenticated = False
            
            self.ws = websocket.WebSocketApp(
                self.url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )
            
            # Start WebSocket in separate thread
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            # Wait for connection
            timeout = 10
            start_time = time.time()
            logger.debug(f"⏳ [HAMMER_CONNECT] Waiting for WebSocket connection (timeout: {timeout}s)...")
            
            while not self.connected and time.time() - start_time < timeout:
                time.sleep(0.1)
            
            elapsed = time.time() - start_time
            
            if self.connected:
                logger.info(f"✅ [HAMMER_CONNECT] WebSocket connection opened (took {elapsed:.2f}s)")
                logger.info("   ⏳ Waiting for authentication...")
                # Wait a bit more for authentication
                auth_timeout = 5
                auth_start = time.time()
                while not self.authenticated and time.time() - auth_start < auth_timeout:
                    time.sleep(0.1)
                
                if self.authenticated:
                    logger.info(f"✅ [HAMMER_CONNECT] Hammer Pro connection established and authenticated (total: {time.time() - start_time:.2f}s)")
                    return True
                else:
                    logger.error(f"❌ [HAMMER_CONNECT] WebSocket connected but authentication failed (timeout: {auth_timeout}s)")
                    logger.error("   💡 Check if password is correct and Hammer Pro is running")
                    return False
            else:
                logger.error(f"❌ [HAMMER_CONNECT] Hammer Pro connection timeout after {elapsed:.2f}s")
                logger.error(f"   💡 Check if Hammer Pro is running on {self.host}:{self.port}")
                logger.error("   💡 Common issues:")
                logger.error("      - Hammer Pro not started")
                logger.error("      - Firewall blocking port 16400")
                logger.error("      - Wrong host/port configuration")
                return False
        
        except Exception as e:
            logger.error(f"❌ [HAMMER_CONNECT] Error connecting to Hammer Pro: {e}", exc_info=True)
            logger.error(f"   Error type: {type(e).__name__}")
            return False
    
    def _on_open(self, ws):
        """WebSocket opened"""
        self.connected = True
        logger.info("WebSocket connection opened")
        
        # Authenticate
        if not self.password:
            logger.error("No password set for authentication!")
            return
        
        # Debug: Log password length and first/last char (for debugging, not full password)
        pwd_len = len(self.password) if self.password else 0
        pwd_preview = f"{self.password[0] if self.password and len(self.password) > 0 else '?'}...{self.password[-1] if self.password and len(self.password) > 1 else '?'}" if self.password else "None"
        logger.debug(f"Authenticating with password (length: {pwd_len}, preview: {pwd_preview})")
        
        auth_cmd = {
            "cmd": "connect",
            "pwd": self.password
        }
        logger.info("Sending authentication...")
        self._send_command(auth_cmd)
    
    def _on_message(self, ws, message):
        """Handle incoming WebSocket messages"""
        try:
            # CONNECTED message
            if message.strip() == "CONNECTED":
                logger.debug("Received CONNECTED message")
                return
            
            # Parse JSON
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.warning(f"Non-JSON message received: {message[:100]}")
                return
            
            cmd = data.get("cmd", "")
            success = data.get("success", "")
            result = data.get("result", {})
            req_id = data.get("reqID")
            
            # Debug: Log all messages (first few)
            if not hasattr(self, '_msg_count'):
                self._msg_count = 0
            self._msg_count += 1
            if self._msg_count <= 5:
                logger.debug(f"📥 Message {self._msg_count}: cmd={cmd}, success={success}")
            
            # Store response if reqID present
            if req_id:
                with self._pending_lock:
                    self._pending_responses[req_id] = data
            
            # Handle authentication
            if cmd == "connect":
                logger.info(f"📥 Authentication response: success={success}, result={result}")
                if success == "OK":
                    self.authenticated = True
                    self._reconnect_attempts = 0  # Reset reconnect counter on successful auth
                    logger.info("✅ Hammer Pro authentication successful")
                    
                    # First, enumerate available streamers (non-blocking, timeout is OK)
                    logger.info("🔍 Enumerating data streamers...")
                    streamer_id = "ALARICQ"  # Default
                    
                    # Try to enumerate, but don't fail if timeout
                    streamer_resp = self.send_command_and_wait({
                        "cmd": "enumDataStreamers"
                    }, wait_for_response=True, timeout=3.0)  # Shorter timeout
                    
                    if streamer_resp and streamer_resp.get('success') == 'OK':
                        streamers = streamer_resp.get('result', [])
                        logger.info(f"📋 Found {len(streamers)} streamer(s)")
                        
                        # Find ALARICQ or use first available
                        for s in streamers:
                            if isinstance(s, dict):
                                sid = s.get('streamerID') or s.get('streamerId') or s.get('id')
                                if sid == "ALARICQ":
                                    streamer_id = "ALARICQ"
                                    break
                                elif not streamer_id or streamer_id == "ALARICQ":
                                    streamer_id = sid
                            elif isinstance(s, str):
                                if s == "ALARICQ":
                                    streamer_id = "ALARICQ"
                                    break
                                elif not streamer_id or streamer_id == "ALARICQ":
                                    streamer_id = s
                        
                        logger.info(f"✅ Using streamerID: {streamer_id}")
                    else:
                        logger.info(f"ℹ️ Using default streamerID: {streamer_id} (enumeration timeout is OK)")
                    
                    # Store streamer ID for later use
                    self.streamer_id = streamer_id
                    
                    # Start data streamer (non-blocking - send command, don't wait for response)
                    # Add small delay to prevent overwhelming Hammer Pro
                    time.sleep(0.1)  # 100ms delay after authentication
                    
                    logger.info(f"🚀 Starting data streamer: {streamer_id}")
                    if not self._send_command({
                        "cmd": "startDataStreamer",
                        "streamerID": streamer_id
                    }):
                        logger.warning("Failed to send startDataStreamer command")
                        return
                    logger.info(f"ℹ️ Data streamer start command sent (response will be handled asynchronously)")
                    
                    # Wait a bit before next command
                    time.sleep(0.2)  # 200ms delay
                    
                    # Start trading account (non-blocking)
                    logger.info(f"🚀 Starting trading account: {self.account_key}")
                    if not self._send_command({
                        "cmd": "startTradingAccount",
                        "accountKey": self.account_key
                    }):
                        logger.warning("Failed to send startTradingAccount command")
                        return
                    logger.info(f"ℹ️ Trading account start command sent (response will be handled asynchronously)")
                    
                    # Wait a bit before subscriptions
                    time.sleep(0.2)  # 200ms delay
                    
                    # Subscribe to transactions and positions
                    if not self._send_command({
                        "cmd": "subscribe",
                        "accountKey": self.account_key,
                        "sub": "transactions",
                        "changes": False
                    }):
                        logger.warning("Failed to send subscribe (transactions) command")
                        return
                    
                    time.sleep(0.1)  # 100ms delay between subscriptions
                    
                    if not self._send_command({
                        "cmd": "subscribe",
                        "accountKey": self.account_key,
                        "sub": "positions",
                        "changes": False
                    }):
                        logger.warning("Failed to send subscribe (positions) command")
                        return
                    
                    # Wait a bit before getting positions
                    time.sleep(0.2)  # 200ms delay
                    
                    # Get initial positions
                    if not self._send_command({
                        "cmd": "getPositions",
                        "accountKey": self.account_key
                    }):
                        logger.warning("Failed to send getPositions command")
                        return
                else:
                    logger.error(f"❌ Authentication failed: {result}")
                    self.authenticated = False
            
            elif cmd == "startDataStreamer":
                if success == "OK":
                    logger.info(f"✅ Data streamer started successfully: {result}")
                else:
                    logger.info(f"ℹ️ Data streamer start response: {result} (this is informational)")
            
            elif cmd == "startTradingAccount":
                if success == "OK":
                    logger.info(f"✅ Trading account started successfully: {result}")
                else:
                    logger.info(f"ℹ️ Trading account start response: {result} (this is informational)")
            
            # Forward message to callback
            if self.on_message_callback:
                try:
                    self.on_message_callback(data)
                except Exception as e:
                    logger.error(f"Error in message callback: {e}", exc_info=True)
        
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
    
    def _on_error(self, ws, error):
        """WebSocket error"""
        error_str = str(error) if error else "Unknown error"
        logger.error(f"❌ [HAMMER_WS_ERROR] WebSocket error: {error_str}")
        logger.error(f"   Error type: {type(error).__name__ if error else 'None'}")
        
        # Common error messages
        if "Connection refused" in error_str or "[WinError 10061]" in error_str:
            logger.error("   💡 Hammer Pro is not running or not listening on port 16400")
        elif "timeout" in error_str.lower():
            logger.error("   💡 Connection timeout - check network/firewall")
        elif "[WinError 10053]" in error_str:
            logger.error("   💡 Connection was reset - Hammer Pro may have closed the connection")
        
        self.connected = False
        self.authenticated = False
    
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket closed"""
        close_msg_str = str(close_msg) if close_msg else "No message"
        logger.warning(f"⚠️ [HAMMER_WS_CLOSE] WebSocket closed: status={close_status_code}, msg={close_msg_str}")
        
        # Common close reasons
        if close_status_code == 1006:
            logger.warning("   💡 Abnormal closure (1006) - Hammer Pro may have crashed or network issue")
        elif close_status_code == 1000:
            logger.warning("   💡 Normal closure (1000) - Hammer Pro closed connection gracefully")
        
        self.connected = False
        self.authenticated = False
        
        # Attempt reconnection if enabled (in separate thread to avoid blocking)
        if self._should_reconnect and self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            logger.info(f"🔄 Attempting reconnection ({self._reconnect_attempts}/{self._max_reconnect_attempts}) in {self._reconnect_delay}s...")
            
            def delayed_reconnect():
                time.sleep(self._reconnect_delay)
                if not self.connected:  # Only reconnect if still disconnected
                    logger.info("🔌 Reconnecting to Hammer Pro...")
                    self.connect()
            
            reconnect_thread = threading.Thread(target=delayed_reconnect, daemon=True)
            reconnect_thread.start()
        elif self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error(f"❌ Max reconnection attempts ({self._max_reconnect_attempts}) reached. Manual restart required.")
    
    def _send_command(self, command: Dict[str, Any]) -> bool:
        """
        Send command to Hammer Pro.
        
        Args:
            command: Command dictionary
            
        Returns:
            True if sent successfully
        """
        try:
            if not self.ws:
                logger.warning("WebSocket not initialized, cannot send command")
                return False
            
            # Check if WebSocket is still connected
            if not self.connected:
                logger.warning("WebSocket marked as disconnected, cannot send command")
                return False
            
            # Check WebSocket state more carefully
            try:
                # websocket-client uses sock to check connection
                if hasattr(self.ws, 'sock') and self.ws.sock:
                    # Socket exists, try to send
                    pass
                else:
                    logger.warning("WebSocket socket not available, cannot send command")
                    self.connected = False
                    return False
            except Exception as check_error:
                logger.debug(f"WebSocket state check error (non-critical): {check_error}")
            
            command_json = json.dumps(command)
            self.ws.send(command_json)
            logger.debug(f"Command sent: {command.get('cmd')}")
            return True
        
        except Exception as e:
            logger.error(f"Error sending command: {e}", exc_info=True)
            # Mark as disconnected if send fails
            self.connected = False
            return False
    
    def send_command(self, command: Dict[str, Any], wait_for_response: bool = False, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        Send command and optionally wait for response.
        
        Args:
            command: Command dictionary
            wait_for_response: If True, wait for response
            timeout: Timeout in seconds
            
        Returns:
            Response dictionary or None
        """
        if wait_for_response:
            req_id = str(uuid.uuid4())
            command['reqID'] = req_id
            
            with self._pending_lock:
                self._pending_responses[req_id] = None
            
            if not self._send_command(command):
                return None
            
            # Wait for response
            start_time = time.time()
            while time.time() - start_time < timeout:
                with self._pending_lock:
                    if req_id in self._pending_responses and self._pending_responses[req_id] is not None:
                        return self._pending_responses.pop(req_id)
                time.sleep(0.05)
            
            # Timeout
            with self._pending_lock:
                self._pending_responses.pop(req_id, None)
            
            logger.warning(f"Command timeout: {command.get('cmd')}")
            return None
        else:
            return self._send_command(command)
    
    def send_command_and_wait(self, command: Dict[str, Any], wait_for_response: bool = True, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        Send command and wait for response (convenience method).
        
        Args:
            command: Command dictionary
            wait_for_response: If True, wait for response (default: True)
            timeout: Timeout in seconds
            
        Returns:
            Response dictionary or None
        """
        return self.send_command(command, wait_for_response=wait_for_response, timeout=timeout)
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self.connected and self.ws is not None
    
    def is_authenticated(self) -> bool:
        """Check if Hammer Pro is authenticated"""
        return self.authenticated
    
    def get_symbol_snapshot(self, symbol: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get symbol snapshot from Hammer API (getSymbolSnapshot command).
        
        This is the ONLY source for prevClose, change, and dividend values.
        L1Update messages do NOT contain prevClose.
        
        Args:
            symbol: Symbol in display format (e.g., "CIM PRB", "SPY", "TLT")
            use_cache: If True, return cached snapshot if available (default: True)
            
        Returns:
            Snapshot dict with:
            - prevClose: Previous close (dividend/split adjusted)
            - change: Daily change
            - dividend: Dividend amount if ex-div
            - last: Last price
            - bid: Bid price
            - ask: Ask price
            - open, high, low, volume: Other OHLCV data
            Or None on error
        """
        if not self.is_connected():
            # Don't log warning - this is normal if Hammer isn't connected yet
            # Snapshot will be fetched when Hammer connects and L1Update arrives
            return None
        
        # Check cache first
        if use_cache:
            with self._snapshot_cache_lock:
                if symbol in self._snapshot_cache:
                    cached = self._snapshot_cache[symbol]
                    # Cache is valid for 5 minutes
                    cache_age = time.time() - cached.get('_cache_time', 0)
                    if cache_age < 300:  # 5 minutes
                        logger.debug(f"📊 Using cached snapshot for {symbol}")
                        return cached
        
        try:
            # Convert symbol to Hammer format
            hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
            
            # Build getSymbolSnapshot command (Hammer Pro API format)
            command = {
                "cmd": "getSymbolSnapshot",
                "sym": hammer_symbol,
                "reqID": str(uuid.uuid4())
            }
            
            logger.debug(f"📊 getSymbolSnapshot: {symbol} ({hammer_symbol})")
            
            # Send command and wait for response (shorter timeout for better responsiveness)
            # Cache mechanism (5 min TTL) reduces need for frequent snapshot calls
            response = self.send_command_and_wait(command, wait_for_response=True, timeout=5.0)
            
            if response and response.get('success') == 'OK':
                result = response.get('result', {})
                
                # Extract snapshot data
                snapshot = {
                    'prevClose': self._safe_float(result.get('prevClose')),
                    'change': self._safe_float(result.get('change')),
                    'dividend': self._safe_float(result.get('dividend')),
                    'last': self._safe_float(result.get('last')),
                    'bid': self._safe_float(result.get('bid')),
                    'ask': self._safe_float(result.get('ask')),
                    'open': self._safe_float(result.get('open')),
                    'high': self._safe_float(result.get('high')),
                    'low': self._safe_float(result.get('low')),
                    'volume': self._safe_float(result.get('volume')),
                    '_cache_time': time.time()  # Cache timestamp
                }
                
                # Cache snapshot
                with self._snapshot_cache_lock:
                    self._snapshot_cache[symbol] = snapshot
                
                logger.debug(f"✅ getSymbolSnapshot successful: {symbol} - prevClose={snapshot.get('prevClose')}, change={snapshot.get('change')}")
                return snapshot
            else:
                # Reduce log level: WARNING -> DEBUG (first time only, repeated failures are logged at debug)
                logger.debug(f"⚠️ getSymbolSnapshot failed for {symbol} ({hammer_symbol}): {response}")
                return None
                
        except Exception as e:
            # Reduce log level: ERROR -> DEBUG (timeout is normal if Hammer is busy)
            logger.debug(f"Error getting symbol snapshot for {symbol}: {e}")
            return None
    
    def _safe_float(self, value, default: float = 0.0) -> float:
        """Safely convert value to float"""
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def get_ticks(self, symbol: str, lastFew: int = 50, tradesOnly: bool = False, regHoursOnly: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get historical tick data for a symbol (getTicks command).
        
        Args:
            symbol: Symbol in Hammer format (e.g., "AAPL" or "CIM-B")
            lastFew: Number of last ticks to retrieve
            tradesOnly: If True, only return trades (filter out bid/ask changes)
            regHoursOnly: If True, only return regular trading hours data
            
        Returns:
            Response dict with 'data' field containing list of ticks, or None on error
        """
        if not self.is_connected():
            logger.error("Hammer client not connected")
            return None
        
        try:
            # Convert symbol to Hammer format if needed
            hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
            
            # Build getTicks command (Hammer Pro API format)
            command = {
                "cmd": "getTicks",
                "reqID": str(uuid.uuid4()),
                "sym": hammer_symbol,
                "lastFew": lastFew,
                "tradesOnly": tradesOnly,
                "regHoursOnly": regHoursOnly
            }
            
            logger.debug(f"🔍 getTicks command: {hammer_symbol}, lastFew={lastFew}, tradesOnly={tradesOnly}")
            
            # Send command and wait for response
            response = self.send_command_and_wait(command, wait_for_response=True, timeout=10.0)
            
            if response and response.get('success') == 'OK':
                result = response.get('result', {})
                tick_count = len(result.get('data', []))
                logger.debug(f"✅ getTicks successful: {hammer_symbol} - {tick_count} ticks retrieved")
                return result
            else:
                logger.warning(f"⚠️ getTicks failed for {hammer_symbol}: {response}")
                return None
                
        except Exception as e:
            logger.error(f"❌ getTicks exception for {symbol}: {e}", exc_info=True)
            return None
    
    def get_l2_snapshot(self, symbol: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        Get Level 2 snapshot (bids/asks/prints) using getQuotes command.
        
        Args:
            symbol: Symbol (display format)
            timeout: Command timeout
            
        Returns:
            Snapshot dict or None
        """
        if not self.is_connected():
            return None
            
        try:
            hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
            command = {
                "cmd": "getQuotes",
                "sym": hammer_symbol
            }
            
            response = self.send_command_and_wait(command, timeout=timeout)
            if response and response.get('success') == 'OK':
                return response.get('result')
            return None
        except Exception as e:
            logger.error(f"Error getting L2 snapshot for {symbol}: {e}")
            return None

    def disconnect(self):
        """Disconnect from Hammer Pro"""
        self._should_reconnect = False
        if self.ws:
            try:
                self.ws.close()
                self.ws = None
                self.connected = False
                self.authenticated = False
                logger.info("Disconnected from Hammer Pro")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")

