"""app/live/hammer_client.py

Hammer Pro WebSocket client - headless, engine-driven.
No GUI, no CSV, no UI callbacks - pure API integration.
"""

import websocket
import json
import threading
import time
import uuid
from typing import Optional, Callable, Dict, Any, List
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
        
        # Message callbacks (Legacy Single Callback + Observer Pattern)
        self.on_message_callback: Optional[Callable] = None
        self._observers: List[Callable[[Dict[str, Any]], None]] = []
        self._observers_lock = threading.Lock()
        
        # Reconnection — exponential backoff, effectively unlimited
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 999  # Never give up — Hammer is critical
        self._reconnect_delay_base = 3.0  # Initial delay
        self._reconnect_delay_max = 60.0  # Cap at 60 seconds
        self._should_reconnect = True  # Auto-reconnect enabled by default
        self._reconnecting = False  # Guard: prevent concurrent reconnect threads (death spiral fix)
        
        # Snapshot cache (for prevClose, change, dividend from getSymbolSnapshot)
        self._snapshot_cache: Dict[str, Dict[str, Any]] = {}
        self._snapshot_cache_lock = threading.Lock()
        
        # Streamer ID (auto-discovered on connect)
        self.streamer_id = "ALARICQ" # Default to ALARICQ, updated in post-auth
        self.streamer_ready = False
        self._streamer_ready_event = threading.Event()
        
        # L1 staleness watchdog — tracks last L1Update timestamp
        self._last_l1_update_time: float = 0.0
        self._l1_watchdog_running = False
        self._l1_stale_threshold = 90.0  # seconds before L1 is considered stale
        self._l1_resubscribe_cooldown = 120.0  # minimum seconds between resubscribes
        self._last_resubscribe_time: float = 0.0
    
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
            
            # ═══════════════════════════════════════════════════════════════
            # CRITICAL: Clean up old WebSocket before creating a new one.
            # Without this, each reconnect LEAKS the old ws + thread,
            # creating zombie connections that accumulate over time.
            # This was the root cause of 63 simultaneous connections
            # and the 20:51 death spiral on 3 March.
            # ═══════════════════════════════════════════════════════════════
            old_ws = getattr(self, 'ws', None)
            old_thread = getattr(self, 'ws_thread', None)
            
            if old_ws:
                try:
                    old_ws.close()
                except Exception:
                    pass
                self.ws = None
            
            if old_thread and old_thread.is_alive():
                try:
                    old_thread.join(timeout=2.0)  # Wait max 2s for old thread to die
                except Exception:
                    pass
            
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
            # CRITICAL: ping_interval=30 sends WebSocket ping every 30s
            # ping_timeout=10 waits 10s for pong; if no pong → triggers _on_close
            # Without this, idle connections are silently dropped by NAT/firewall
            # causing L1 data to stop flowing without any error/close notification.
            self.ws_thread = threading.Thread(
                target=lambda: self.ws.run_forever(
                    ping_interval=30,
                    ping_timeout=10
                )
            )
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
                auth_timeout = 10  # Increased from 5s — Hammer can be slow under load
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
            if self._msg_count <= 100:
                logger.info(f"📥 [RAW_MSG] Message {self._msg_count}: cmd={cmd}, success={success}, err={data.get('error')}")
            else:
                logger.debug(f"📥 Message {self._msg_count}: cmd={cmd}")
            
            # Store response if reqID present and signal waiting thread
            if req_id:
                with self._pending_lock:
                    self._pending_responses[req_id] = data
                    # Signal the Event so send_command wakes up immediately
                    if hasattr(self, '_pending_events') and req_id in self._pending_events:
                        self._pending_events[req_id].set()
            
            # Handle authentication
            if cmd == "connect":
                logger.info(f"📥 Authentication response: success={success}, result={result}")
                if success == "OK":
                    self.authenticated = True
                    self._reconnect_attempts = 0  # Reset reconnect counter on successful auth
                    self._reconnecting = False  # Allow future reconnects
                    logger.info("✅ Hammer Pro authentication successful")
                    
                    # Launch startup sequence in separate thread to avoid blocking _on_message
                    # (which would prevent receiving responses to commands sent during startup)
                    startup_thread = threading.Thread(target=self._perform_post_auth_startup, daemon=True)
                    startup_thread.start()
                else:
                    logger.error(f"❌ Authentication failed: {result}")
                    self.authenticated = False
            
            elif cmd == "startDataStreamer":
                if success == "OK":
                    logger.info(f"✅ Data streamer started successfully: {result}")
                    self.streamer_ready = True
                    self._streamer_ready_event.set()
                else:
                    logger.info(f"ℹ️ Data streamer start response: {result} (this is informational)")

            elif cmd == "dataStreamerStateUpdate":
                state = result.get('state', '')
                logger.info(f"📡 Streamer State: {state}")
                if state == "IdleOrStreaming":
                    self.streamer_ready = True
                    self._streamer_ready_event.set()
            
            elif cmd == "startTradingAccount":
                if success == "OK":
                    logger.info(f"✅ Trading account started successfully: {result}")
                else:
                    logger.info(f"ℹ️ Trading account start response: {result} (this is informational)")
            
            # DEBUG: Log L1Update messages specifically
            elif cmd == "L1Update":
                if not hasattr(self, '_l1_msg_count'):
                    self._l1_msg_count = 0
                self._l1_msg_count += 1
                # Track last L1 update time for staleness watchdog
                self._last_l1_update_time = time.time()
                # Log first 50 messages to catch initial burst
                if self._l1_msg_count <= 50:
                    logger.info(f"📥 [HAMMER_CLIENT] L1Update #{self._l1_msg_count}: {result}")
                
            # Forward message to legacy callback
            if self.on_message_callback:
                try:
                    # Log callback invocation for first few messages
                    if self._msg_count <= 10:
                        logger.debug(f"Calling on_message_callback for cmd={cmd}")
                    self.on_message_callback(data)
                except Exception as e:
                    logger.error(f"Error in message callback: {e}", exc_info=True)
            else:
                if self._msg_count <= 10:
                    logger.warning(f"No on_message_callback set for cmd={cmd}")
            
            # Forward to Observers
            with self._observers_lock:
                for observer in self._observers:
                    try:
                        observer(data)
                    except Exception as e:
                        logger.error(f"Error in observer {observer}: {e}", exc_info=True)

            if not self.on_message_callback and not self._observers:
                # DEBUG: Log if NO ONE is listening
                if cmd == "L1Update" and self._l1_msg_count <= 3:
                     logger.warning(f"⚠️ L1Update received but NO listeners set!")
        
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
        logger.warning(f"\u26a0\ufe0f [HAMMER_WS_CLOSE] WebSocket closed: status={close_status_code}, msg={close_msg_str}")
        
        # Common close reasons
        if close_status_code == 1006:
            logger.warning("   \ud83d\udca1 Abnormal closure (1006) - Hammer Pro may have crashed or network issue")
        elif close_status_code == 1000:
            logger.warning("   \ud83d\udca1 Normal closure (1000) - Hammer Pro closed connection gracefully")
        
        self.connected = False
        self.authenticated = False
        
        # Clean up stale WebSocket reference to prevent ghost connections
        try:
            if self.ws and self.ws != ws:
                # A newer ws exists — don't touch it
                pass
            else:
                self.ws = None
        except Exception:
            self.ws = None
        
        # Attempt reconnection with exponential backoff
        # GUARD: Only one reconnect thread at a time (prevents death spiral)
        if self._should_reconnect and not self._reconnecting:
            self._reconnecting = True
            self._reconnect_attempts += 1
            # Exponential backoff: 3 → 6 → 12 → 24 → 48 → 60 (capped)
            delay = min(
                self._reconnect_delay_base * (2 ** min(self._reconnect_attempts - 1, 5)),
                self._reconnect_delay_max
            )
            logger.info(f"\ud83d\udd04 Reconnection ({self._reconnect_attempts}) in {delay:.1f}s...")
            
            def delayed_reconnect():
                try:
                    time.sleep(delay)
                    if not self.connected:
                        logger.info("\ud83d\udd0c Reconnecting to Hammer Pro...")
                        self.connect()
                finally:
                    self._reconnecting = False  # Release guard (allows next reconnect)
            
            reconnect_thread = threading.Thread(target=delayed_reconnect, daemon=True)
            reconnect_thread.start()
        elif self._reconnecting:
            logger.debug("Reconnect already in progress — skipping duplicate")
    
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
                # Throttle: log at most once per 30s
                now = time.time()
                if not hasattr(self, '_last_notconn_warn') or now - self._last_notconn_warn > 30:
                    logger.warning("WebSocket not initialized, cannot send command")
                    self._last_notconn_warn = now
                return False
            
            # Check if WebSocket is still connected
            if not self.connected:
                now = time.time()
                if not hasattr(self, '_last_notconn_warn') or now - self._last_notconn_warn > 30:
                    logger.warning("WebSocket marked as disconnected, cannot send command")
                    self._last_notconn_warn = now
                return False
            
            # Check WebSocket state more carefully
            try:
                # websocket-client uses sock to check connection
                if hasattr(self.ws, 'sock') and self.ws.sock:
                    # Socket exists, try to send
                    pass
                else:
                    now = time.time()
                    if not hasattr(self, '_last_notconn_warn') or now - self._last_notconn_warn > 30:
                        logger.warning("WebSocket socket not available, cannot send command")
                        self._last_notconn_warn = now
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
        Uses threading.Event for efficient wait (no busy-loop polling).
        """
        if wait_for_response:
            req_id = str(uuid.uuid4())
            command['reqID'] = req_id
            
            event = threading.Event()
            with self._pending_lock:
                self._pending_responses[req_id] = None
                # Store event for this request so _on_message can signal it
                if not hasattr(self, '_pending_events'):
                    self._pending_events: Dict[str, threading.Event] = {}
                self._pending_events[req_id] = event
            
            if not self._send_command(command):
                with self._pending_lock:
                    self._pending_responses.pop(req_id, None)
                    if hasattr(self, '_pending_events'):
                        self._pending_events.pop(req_id, None)
                return None
            
            # Wait for response using Event (efficient, no GIL contention)
            event.wait(timeout=timeout)
            
            with self._pending_lock:
                if hasattr(self, '_pending_events'):
                    self._pending_events.pop(req_id, None)
                response = self._pending_responses.pop(req_id, None)
            
            if response is not None:
                return response
            
            # Throttle timeout warnings — accumulate and report summary every 60s
            # Previously logged each getTicks timeout (up to 16/min), flooding the log
            now = time.time()
            if not hasattr(self, '_timeout_counter'):
                self._timeout_counter = 0
                self._last_timeout_warn = 0.0
            self._timeout_counter += 1
            if now - self._last_timeout_warn > 60:
                logger.warning(f"Command timeout: {command.get('cmd')} ({self._timeout_counter} timeouts in last 60s)")
                self._timeout_counter = 0
                self._last_timeout_warn = now
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
        
    def _perform_post_auth_startup(self):
        """Execute post-authentication startup sequence in a separate thread"""
        try:
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
                self.streamer_id = streamer_id
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
            
            # Subscribe to transactions (changes=True for event-driven)
            if not self._send_command({
                "cmd": "subscribe",
                "accountKey": self.account_key,
                "sub": "transactions",
                "changes": True
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

            # Start L1 staleness watchdog (auto-resubscribe if data stops)
            self._start_l1_watchdog()
                
        except Exception as e:
            logger.error(f"❌ Error in post-auth startup: {e}", exc_info=True)
    
    def _start_l1_watchdog(self):
        """
        Start a background watchdog thread that monitors L1 data freshness.
        
        If no L1Update is received for >90 seconds during market hours,
        triggers automatic resubscription to all preferred symbols.
        
        This catches the case where:
        - WebSocket ping/pong keeps the connection alive
        - But Hammer's data streamer silently stops sending L1Updates
        - Or subscriptions were lost during a server-side reset
        """
        if self._l1_watchdog_running:
            logger.debug("[L1_WATCHDOG] Already running — skipping duplicate start")
            return
        
        self._l1_watchdog_running = True
        self._last_l1_update_time = time.time()  # Initialize with current time
        
        def watchdog_loop():
            logger.info("[L1_WATCHDOG] 🐕 Started — monitoring L1 data freshness (threshold: 90s)")
            
            while self._l1_watchdog_running and self._should_reconnect:
                try:
                    time.sleep(30)  # Check every 30 seconds
                    
                    if not self.connected or not self.authenticated:
                        continue  # Skip check when disconnected (reconnect logic handles this)
                    
                    # Only check during US market hours (9:30-16:00 ET = 14:30-21:00 UTC)
                    from datetime import datetime, timezone, timedelta
                    now_utc = datetime.now(timezone.utc)
                    et_offset = timedelta(hours=-4)  # EDT (adjust if needed)
                    now_et = now_utc + et_offset
                    market_open = now_et.replace(hour=9, minute=25, second=0)
                    market_close = now_et.replace(hour=16, minute=5, second=0)
                    
                    if not (market_open <= now_et <= market_close):
                        continue  # Outside market hours — no L1 expected
                    
                    # Check staleness
                    now = time.time()
                    age = now - self._last_l1_update_time
                    
                    if age > self._l1_stale_threshold:
                        # L1 data is stale — check cooldown
                        time_since_last_resub = now - self._last_resubscribe_time
                        
                        if time_since_last_resub < self._l1_resubscribe_cooldown:
                            logger.debug(
                                f"[L1_WATCHDOG] L1 stale ({age:.0f}s) but cooldown active "
                                f"({time_since_last_resub:.0f}s < {self._l1_resubscribe_cooldown}s)"
                            )
                            continue
                        
                        logger.warning(
                            f"[L1_WATCHDOG] ⚠️ L1 data STALE for {age:.0f}s! "
                            f"Last L1Update was {age:.0f}s ago. Triggering resubscription..."
                        )
                        
                        self._last_resubscribe_time = now
                        self._resubscribe_all_preferred()
                    else:
                        # Periodic health log (every ~5 min)
                        if hasattr(self, '_l1_msg_count') and self._l1_msg_count % 10000 == 0:
                            logger.info(
                                f"[L1_WATCHDOG] ✅ L1 healthy — last update {age:.1f}s ago, "
                                f"total L1 msgs: {self._l1_msg_count}"
                            )
                            
                except Exception as e:
                    logger.error(f"[L1_WATCHDOG] Error in watchdog loop: {e}")
            
            self._l1_watchdog_running = False
            logger.info("[L1_WATCHDOG] 🛑 Watchdog stopped")
        
        watchdog_thread = threading.Thread(target=watchdog_loop, daemon=True)
        watchdog_thread.name = "L1_Staleness_Watchdog"
        watchdog_thread.start()
    
    def _resubscribe_all_preferred(self):
        """
        Re-subscribe to all preferred symbols via HammerFeed.
        Called by the L1 watchdog when data staleness is detected.
        """
        try:
            from app.live.hammer_feed import get_hammer_feed
            from app.market_data.static_data_store import get_static_store
            from app.api.market_data_routes import ETF_TICKERS
            
            hammer_feed = get_hammer_feed()
            if not hammer_feed:
                logger.error("[L1_WATCHDOG] ❌ HammerFeed not available for resubscription")
                return
            
            static_store = get_static_store()
            if not static_store or not static_store.is_loaded():
                logger.error("[L1_WATCHDOG] ❌ Static store not loaded for resubscription")
                return
            
            # Get all symbols
            all_symbols = static_store.get_all_symbols()
            preferred_symbols = [s for s in all_symbols if s not in ETF_TICKERS]
            
            if not preferred_symbols:
                logger.warning("[L1_WATCHDOG] No preferred symbols found")
                return
            
            logger.info(
                f"[L1_WATCHDOG] 🔄 Re-subscribing to {len(preferred_symbols)} preferred stocks "
                f"+ {len(ETF_TICKERS)} ETFs..."
            )
            
            # First, re-subscribe ETFs
            for etf in ETF_TICKERS:
                hammer_feed.subscribe_symbol(etf, include_l2=False)
            
            # Then batch-subscribe preferred stocks
            subscribed = hammer_feed.subscribe_symbols_batch(
                preferred_symbols,
                include_l2=False,
                batch_size=50
            )
            
            logger.info(
                f"[L1_WATCHDOG] ✅ Resubscription complete: "
                f"{subscribed}/{len(preferred_symbols)} preferred + {len(ETF_TICKERS)} ETFs"
            )
            
        except Exception as e:
            logger.error(f"[L1_WATCHDOG] ❌ Resubscription failed: {e}", exc_info=True)
    
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
                "sym": hammer_symbol
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
    
    def get_ticks(self, symbol: str, lastFew: int = 50, tradesOnly: bool = False, regHoursOnly: bool = True, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """
        Get historical tick data for a symbol (getTicks command).
        
        Args:
            symbol: Symbol in Hammer format (e.g., "AAPL" or "CIM-B")
            lastFew: Number of last ticks to retrieve
            tradesOnly: If True, only return trades (filter out bid/ask changes)
            regHoursOnly: If True, only return regular trading hours data
            timeout: Command timeout in seconds (default: 10.0)
            
        Returns:
            Response dict with 'data' field containing list of ticks, or None on error
        """
        if not self.is_connected():
            # Throttled — this gets called thousands of times during disconnect
            return None
        
        try:
            # Convert symbol to Hammer format if needed
            hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
            
            # Build getTicks command (Hammer Pro API format)
            command = {
                "cmd": "getTicks",
                "sym": hammer_symbol,
                "lastFew": lastFew,
                "tradesOnly": tradesOnly,
                "regHoursOnly": regHoursOnly
            }
            
            logger.debug(f"\ud83d\udd0d getTicks command: {hammer_symbol}, lastFew={lastFew}, tradesOnly={tradesOnly}")
            
            # Send command and wait for response
            response = self.send_command_and_wait(command, wait_for_response=True, timeout=timeout)
            
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
            
        # Ensure streamer is ready
        if not self.streamer_ready:
            logger.info(f"⏳ Waiting for streamer {self.streamer_id} to be ready...")
            if not self._streamer_ready_event.wait(timeout=timeout):
                logger.warning(f"⚠️ Streamer {self.streamer_id} not ready after {timeout}s")
                # Proceed anyway, might work
        
        try:
            hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
            command = {
                "cmd": "getQuotes",
                "streamerID": self.streamer_id,
                "sym": hammer_symbol
            }
            
            response = self.send_command_and_wait(command, timeout=timeout)
            if response and response.get('success') == 'OK':
                return response.get('result')
            
            # Fallback: Maybe subscribe L2 with changes=False gives a snapshot?
            # But getQuotes is the standard way for snapshots.
            logger.debug(f"getQuotes failed for {symbol}: {response}")
            return None
        except Exception as e:
            logger.error(f"Error getting L2 snapshot for {symbol}: {e}")
            return None

    def add_observer(self, callback: Callable[[Dict[str, Any]], None]):
        """Add an observer callback for incoming messages"""
        with self._observers_lock:
            if callback not in self._observers:
                self._observers.append(callback)
                logger.debug(f"Observer added: {callback}")

    def remove_observer(self, callback: Callable[[Dict[str, Any]], None]):
        """Remove an observer callback"""
        with self._observers_lock:
            if callback in self._observers:
                self._observers.remove(callback)
                logger.debug(f"Observer removed: {callback}")

    def get_transactions(self, account_key: Optional[str] = None, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        Get transactions from Hammer Pro (getTransactions).
        Useful for recovering fills on startup in HAMMER_PRO mode.
        """
        if not self.is_connected():
            return None
        
        target_account = account_key if account_key else self.account_key
        
        command = {
            "cmd": "getTransactions",
            "accountKey": target_account,
            "changesOnly": False # Get ALL transactions for recovery
        }
        
        # Hammer responses for this are usually updates, but we can wait for acknowledgement 
        # OR we wait for the transactionsUpdate that will follow.
        # Actually Hammer docs say: "initiate the update by sending getTransactions... response will be transactionsUpdate"
        
        # If we wait for response to THIS command, we get success:OK.
        # But the actual data comes as an update.
        # So this method should probably just Trigger the request.
        # The Observer (QeBenchDataLogger) will catch the resulting 'transactionsUpdate'.
        return self.send_command_and_wait(command, timeout=timeout)

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

    def subscribe_symbols_batch(self, symbols: list, include_l2: bool = False, batch_size: int = 50) -> int:
        """
        Subscribe to a batch of symbols (L1) using correct Hammer API format.
        
        Args:
            symbols: List of symbols (display format, e.g. "CIM PRB")
            include_l2: If True, also subscribe to Level 2 (NOT IMPLEMENTED)
            batch_size: Number of symbols to process in one command 
                        (Hammer accepts comma-separated list or array)
            
        Returns:
            Number of successfully queued subscriptions (approx)
        """
        if not self.is_connected():
            return 0
            
        count = 0
        total = len(symbols)
        
        # Helper to process chunks
        def chunker(seq, size):
            return (seq[pos:pos + size] for pos in range(0, len(seq), size))

        for chunk in chunker(symbols, batch_size):
            hammer_symbols = []
            for symbol in chunk:
                # Convert to Hammer format (e.g. "CIM PRB" -> "CIM-B")
                hammer_symbols.append(SymbolMapper.to_hammer_symbol(symbol))
            
            if not hammer_symbols:
                continue

            # Hammer API: 
            # { "cmd": "subscribe", "sub": "L1", "streamerID": "...", "sym": ["...", "..."] }
            cmd = {
                "cmd": "subscribe",
                "sub": "L1",  # Explicitly request L1 feed
                "streamerID": self.streamer_id,
                "sym": hammer_symbols
                # accountKey is usually NOT needed for market data subscription, 
                # streamerID is the key.
            }
            
            if self._send_command(cmd):
                count += len(hammer_symbols)
            
            # Small sleep between batches to remain polite
            time.sleep(0.05)
            
        logger.info(f"✅ Queued L1 subscriptions for {count}/{total} symbols using streamer {self.streamer_id}")
        return count 


# ═══════════════════════════════════════════════════════════════════════════════
# Global Singleton Instance Management
# ═══════════════════════════════════════════════════════════════════════════════

_global_hammer_client: Optional[HammerClient] = None


def get_hammer_client() -> Optional[HammerClient]:
    """
    Get global singleton HammerClient instance.
    
    Returns:
        HammerClient instance if available, None otherwise
    """
    return _global_hammer_client


def set_hammer_client(client: HammerClient) -> None:
    """
    Set global singleton HammerClient instance.
    
    Args:
        client: HammerClient instance to set as global singleton
    """
    global _global_hammer_client
    _global_hammer_client = client
    logger.info(f"[HammerClient] Global singleton instance set")

