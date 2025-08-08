import asyncio
import websockets
import json
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime

class HammerProClient:
    """
    Hammer Pro WebSocket API Client
    Integrates with FINAL BB scoring system and provides watchlist management
    """
    
    def __init__(self, host="127.0.0.1", port=8080, password=None):
        self.ws_url = f"ws://{host}:{port}"
        self.password = password
        self.websocket = None
        self.connected = False
        self.message_handlers: Dict[str, Callable] = {}
        self.logger = logging.getLogger(__name__)
        
        # Portfolio and watchlist management
        self.portfolios = {}
        self.watchlists = {}
        self.market_data = {}
        
    async def connect(self):
        """Connect to Hammer Pro WebSocket API"""
        try:
            self.websocket = await websockets.connect(self.ws_url)
            self.connected = True
            
            # Authenticate with password
            if self.password:
                auth_msg = {
                    "cmd": "connect",
                    "pwd": self.password,
                    "reqID": "auth_001"
                }
                await self.send_message(auth_msg)
            
            # Start listening for messages
            asyncio.create_task(self._listen())
            self.logger.info("Connected to Hammer Pro API")
            
        except Exception as e:
            self.logger.error(f"Failed to connect to Hammer Pro: {e}")
            self.connected = False
            
    async def _listen(self):
        """Listen for incoming messages from Hammer Pro"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self._handle_message(data)
        except Exception as e:
            self.logger.error(f"Error in message listener: {e}")
            self.connected = False
            
    async def _handle_message(self, data: Dict):
        """Handle incoming messages from Hammer Pro"""
        cmd = data.get("cmd", "")
        
        if cmd in self.message_handlers:
            await self.message_handlers[cmd](data)
        else:
            self.logger.debug(f"Unhandled message: {cmd}")
            
    async def send_message(self, message: Dict):
        """Send message to Hammer Pro"""
        if self.connected and self.websocket:
            await self.websocket.send(json.dumps(message))
            
    def register_handler(self, cmd: str, handler: Callable):
        """Register message handler for specific command"""
        self.message_handlers[cmd] = handler
        
    # Portfolio Management
    async def get_portfolios(self) -> List[Dict]:
        """Get all portfolios from Hammer Pro"""
        msg = {
            "cmd": "enumPorts",
            "reqID": "get_ports_001"
        }
        await self.send_message(msg)
        return self.portfolios
        
    async def create_watchlist(self, name: str, symbols: List[str]) -> str:
        """Create a new watchlist with symbols"""
        msg = {
            "cmd": "addToPort",
            "new": True,
            "name": name,
            "sym": symbols,
            "reqID": "create_watchlist_001"
        }
        await self.send_message(msg)
        return f"Watchlist '{name}' created with {len(symbols)} symbols"
        
    async def update_watchlist(self, port_id: str, symbols: List[str]):
        """Update existing watchlist with new symbols"""
        msg = {
            "cmd": "addToPort",
            "portID": port_id,
            "sym": symbols,
            "reqID": "update_watchlist_001"
        }
        await self.send_message(msg)
        
    # Market Data Management
    async def subscribe_market_data(self, symbols: List[str], streamer_id: str = "AMTD"):
        """Subscribe to real-time market data for symbols"""
        # Start data streamer first
        start_msg = {
            "cmd": "startDataStreamer",
            "streamerID": streamer_id,
            "reqID": "start_streamer_001"
        }
        await self.send_message(start_msg)
        
        # Subscribe to L1 data
        subscribe_msg = {
            "cmd": "subscribe",
            "streamerID": streamer_id,
            "sub": "L1",
            "sym": symbols,
            "reqID": "subscribe_l1_001"
        }
        await self.send_message(subscribe_msg)
        
    async def get_symbol_snapshot(self, symbol: str) -> Dict:
        """Get current snapshot for a symbol"""
        msg = {
            "cmd": "getSymbolSnapshot",
            "sym": symbol,
            "reqID": f"snapshot_{symbol}_001"
        }
        await self.send_message(msg)
        return self.market_data.get(symbol, {})
        
    # Trading Account Management
    async def get_trading_accounts(self) -> List[Dict]:
        """Get available trading accounts"""
        msg = {
            "cmd": "enumTradingAccounts",
            "reqID": "get_accounts_001"
        }
        await self.send_message(msg)
        return []
        
    async def start_trading_account(self, account_key: str):
        """Start trading account for order execution"""
        msg = {
            "cmd": "startTradingAccount",
            "accountKey": account_key,
            "reqID": "start_account_001"
        }
        await self.send_message(msg)
        
    # Order Management
    async def place_order(self, account_key: str, symbol: str, quantity: int, 
                         action: str, order_type: str, limit_price: float = None):
        """Place a new order through Hammer Pro"""
        order = {
            "ConditionalType": "None",
            "Legs": [{
                "Symbol": symbol,
                "Quantity": quantity,
                "Action": action,
                "OrderType": order_type,
                "LimitPrice": limit_price if limit_price else 0,
                "TIF": "Day"
            }]
        }
        
        msg = {
            "cmd": "tradeCommandNew",
            "accountKey": account_key,
            "order": order,
            "reqID": f"order_{symbol}_{datetime.now().timestamp()}"
        }
        await self.send_message(msg)
        
    async def close(self):
        """Close connection to Hammer Pro"""
        if self.websocket:
            await self.websocket.close()
        self.connected = False
        self.logger.info("Disconnected from Hammer Pro API") 