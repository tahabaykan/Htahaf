import logging
import time
from datetime import datetime, timedelta
from .hammer_market_data import HammerMarketDataManager

class MarketDataManager:
    def __init__(self, connect_on_init=False):
        self.hammer = HammerMarketDataManager()
        self.connected = False
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        if connect_on_init:
            self.connect()
            
    def connect(self):
        """Connect to Hammer Pro."""
        try:
            self.hammer.connect()
            self.connected = self.hammer.connected
            return self.connected
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            self.connected = False
            return False
            
    def disconnect(self):
        """Disconnect from Hammer Pro."""
        if self.connected:
            try:
                self.hammer.disconnect()
            finally:
                self.connected = False
                
    def subscribe_symbols(self, symbols):
        """Subscribe to market data for symbols."""
        if not self.connected:
            return False
        return self.hammer.subscribe_symbols(symbols)
        
    def unsubscribe_symbols(self, symbols=None):
        """Unsubscribe from market data."""
        if not self.connected:
            return False
        return self.hammer.unsubscribe_symbols(symbols)
        
    def get_market_data(self, symbol):
        """Get market data for a symbol."""
        if not self.connected:
            return None
        return self.hammer.get_market_data(symbol)
        
    def get_etf_data(self, symbols=None):
        """Get ETF market data."""
        if not self.connected:
            return {}
        return self.hammer.get_etf_data(symbols)
        
    def get_positions(self):
        """Get current positions."""
        if not self.connected:
            return []
            
        try:
            # Hammer Pro'dan pozisyonları al
            cmd = {
                "cmd": "getPositions",
                "reqID": self.hammer.client._get_next_req_id()
            }
            
            if not self.hammer.client._send_command(cmd):
                self.logger.error("Failed to get positions")
                return []
                
            # Response will come through websocket
            time.sleep(0.1)
            
            # Format positions
            positions = []
            for pos in self.hammer.client.positions.values():
                positions.append({
                    'symbol': pos.get('symbol'),
                    'quantity': pos.get('quantity', 0),
                    'avgCost': pos.get('avgCost', 0)
                })
                
            return positions
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []
            
    def get_recent_fills(self, minutes=60):
        """Get recent fills."""
        if not self.connected:
            return []
            
        try:
            # Hammer Pro'dan fill'leri al
            cmd = {
                "cmd": "getTransactions",
                "reqID": self.hammer.client._get_next_req_id(),
                "changesOnly": True
            }
            
            if not self.hammer.client._send_command(cmd):
                self.logger.error("Failed to get transactions")
                return []
                
            # Response will come through websocket
            time.sleep(0.1)
            
            # Son X dakikadaki fill'leri filtrele
            cutoff_time = datetime.now() - timedelta(minutes=minutes)
            recent_fills = []
            
            for fill in self.hammer.client.transactions.values():
                if not fill.get('FilledDT'):
                    continue
                    
                try:
                    fill_time = datetime.fromisoformat(fill['FilledDT'].replace('Z', '+00:00'))
                except:
                    continue
                    
                if fill_time >= cutoff_time:
                    recent_fills.append({
                        'symbol': fill.get('Symbol'),
                        'side': fill.get('Action'),
                        'price': fill.get('FilledPrice'),
                        'quantity': fill.get('FilledQTY'),
                        'time': fill_time,
                        'fill_id': fill.get('OrderID')
                    })
                    
            return recent_fills
            
        except Exception as e:
            self.logger.error(f"Error getting recent fills: {e}")
            return []
            
    def get_historical_fills(self, start_time, end_time):
        """Get historical fills."""
        if not self.connected:
            return []
            
        try:
            # Hammer Pro'dan fill'leri al
            cmd = {
                "cmd": "getTransactions",
                "reqID": self.hammer.client._get_next_req_id(),
                "changesOnly": False
            }
            
            if not self.hammer.client._send_command(cmd):
                self.logger.error("Failed to get transactions")
                return []
                
            # Response will come through websocket
            time.sleep(0.1)
            
            # Zaman aralığındaki fill'leri filtrele
            historical_fills = []
            
            for fill in self.hammer.client.transactions.values():
                if not fill.get('FilledDT'):
                    continue
                    
                try:
                    fill_time = datetime.fromisoformat(fill['FilledDT'].replace('Z', '+00:00'))
                except:
                    continue
                    
                if start_time <= fill_time <= end_time:
                    historical_fills.append({
                        'symbol': fill.get('Symbol'),
                        'side': fill.get('Action'),
                        'price': fill.get('FilledPrice'),
                        'quantity': fill.get('FilledQTY'),
                        'time': fill_time
                    })
                    
            return historical_fills
            
        except Exception as e:
            self.logger.error(f"Error getting historical fills: {e}")
            return []