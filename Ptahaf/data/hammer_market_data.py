import logging
import time
from datetime import datetime
from Megapp import MegaHammerClient

class HammerMarketDataManager:
    def __init__(self):
        self.client = None
        self.connected = False
        self.streamer_started = False
        self.active_symbols = set()
        
        logging.basicConfig(level=logging.WARNING)  # Debug ve INFO mesajlarını kapat
        self.logger = logging.getLogger(__name__)
        
    def connect(self):
        """Hammer Pro'ya bağlan"""
        try:
            print("[HAMMER] 🔗 Hammer Pro'ya bağlanılıyor...")
            
            self.client = MegaHammerClient(
                host='127.0.0.1',
                port=16400,
                password='Nl201090.'
            )
            
            if self.client.connect():
                self.connected = True
                print("[HAMMER] ✅ Hammer Pro bağlantısı başarılı")
                self.logger.info("Connected to Hammer Pro")
                
                # Streamer'ı başlat
                self._start_streamer()
                return True
            else:
                print("[HAMMER] ❌ Hammer Pro bağlantısı başarısız")
                self.connected = False
                return False
                
        except Exception as e:
            self.connected = False
            print(f"[HAMMER] ❌ Hammer Pro bağlantı hatası: {e}")
            self.logger.error(f"Failed to connect to Hammer Pro: {str(e)}")
            return False
            
    def _start_streamer(self):
        """Market data streamer'ı başlat"""
        if not self.connected:
            return False
            
        try:
            # Mevcut streamer'ları listele
            enum_cmd = {
                "cmd": "enumDataStreamers",
                "reqID": self.client._get_next_req_id()
            }
            
            if not self.client._send_command(enum_cmd):
                self.logger.error("Failed to enumerate streamers")
                return False
                
            time.sleep(1)
            
            # Streamer'ı başlat
            start_cmd = {
                "cmd": "startDataStreamer",
                "streamerID": "GSMQUOTES"
            }
            
            if not self.client._send_command(start_cmd):
                self.logger.error("Failed to start streamer")
                return False
                
            time.sleep(2)  # Streamer'ın başlamasını bekle
            self.streamer_started = True
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting streamer: {e}")
            return False
            
    def subscribe_symbols(self, symbols):
        """Sembollere subscribe ol"""
        if not self.connected or not self.streamer_started:
            return False
            
        try:
            # Yeni sembolleri subscribe et
            new_symbols = [s for s in symbols if s not in self.active_symbols]
            if new_symbols:
                cmd = {
                    "cmd": "subscribe",
                    "sub": "L1",
                    "streamerID": "GSMQUOTES",
                    "sym": new_symbols
                }
                
                if not self.client._send_command(cmd):
                    self.logger.error(f"Failed to subscribe to symbols: {new_symbols}")
                    return False
                    
                self.active_symbols.update(new_symbols)
                self.logger.info(f"Subscribed to {len(new_symbols)} new symbols")
                
            return True
            
        except Exception as e:
            self.logger.error(f"Error subscribing to symbols: {e}")
            return False
            
    def unsubscribe_symbols(self, symbols=None):
        """Sembollerden unsubscribe ol"""
        if not self.connected:
            return False
            
        try:
            if symbols is None:
                # Tüm sembollerden unsubscribe ol
                if self.active_symbols:
                    cmd = {
                        "cmd": "unsubscribe",
                        "sub": "L1",
                        "streamerID": "GSMQUOTES",
                        "sym": "*"
                    }
                    
                    if not self.client._send_command(cmd):
                        self.logger.error("Failed to unsubscribe from all symbols")
                        return False
                        
                    self.active_symbols.clear()
                    self.logger.info("Unsubscribed from all symbols")
            else:
                # Belirli sembollerden unsubscribe ol
                symbols_to_remove = [s for s in symbols if s in self.active_symbols]
                if symbols_to_remove:
                    cmd = {
                        "cmd": "unsubscribe",
                        "sub": "L1",
                        "streamerID": "GSMQUOTES",
                        "sym": symbols_to_remove
                    }
                    
                    if not self.client._send_command(cmd):
                        self.logger.error(f"Failed to unsubscribe from symbols: {symbols_to_remove}")
                        return False
                        
                    self.active_symbols.difference_update(symbols_to_remove)
                    self.logger.info(f"Unsubscribed from {len(symbols_to_remove)} symbols")
                    
            return True
            
        except Exception as e:
            self.logger.error(f"Error unsubscribing from symbols: {e}")
            return False
            
    def get_market_data(self, symbol):
        """Sembol için market data al"""
        if not self.connected:
            return None
            
        try:
            cmd = {
                "cmd": "getSymbolSnapshot",
                "sym": symbol
            }
            
            if not self.client._send_command(cmd):
                self.logger.error(f"Failed to get snapshot for {symbol}")
                return None
                
            # Response will come through the websocket
            time.sleep(0.1)  # Give time for the response
            
            return self.client.market_data.get(symbol)
            
        except Exception as e:
            self.logger.error(f"Error getting market data for {symbol}: {e}")
            return None
            
    def get_etf_data(self, symbols=None):
        """ETF verilerini al"""
        if symbols is None:
            symbols = ['PFF', 'TLT', 'SPY', 'IWM', 'KRE']
            
        etf_data = {}
        for symbol in symbols:
            data = self.get_market_data(symbol)
            if data:
                etf_data[symbol] = {
                    'last': data.get('last', 'N/A'),
                    'bid': data.get('bid', 'N/A'),
                    'ask': data.get('ask', 'N/A'),
                    'volume': data.get('volume', 'N/A'),
                    'prev_close': data.get('prevClose', 'N/A'),
                    'change': data.get('change', 'N/A')
                }
                
                # Change percentage hesapla
                if (data.get('last') not in ['N/A', None] and 
                    data.get('prevClose') not in ['N/A', None]):
                    change_pct = 100 * (float(data['last']) - float(data['prevClose'])) / float(data['prevClose'])
                    etf_data[symbol]['change_pct'] = round(change_pct, 2)
                else:
                    etf_data[symbol]['change_pct'] = 'N/A'
                    
        return etf_data
        
    def disconnect(self):
        """Hammer Pro bağlantısını kapat"""
        if not self.connected:
            return
            
        try:
            # Tüm sembollerden unsubscribe ol
            self.unsubscribe_symbols()
            
            # Streamer'ı durdur
            if self.streamer_started:
                stop_cmd = {
                    "cmd": "stopDataStreamer",
                    "streamerID": "GSMQUOTES"
                }
                self.client._send_command(stop_cmd)
                self.streamer_started = False
                
            # Bağlantıyı kapat
            self.client.disconnect()
            self.connected = False
            self.logger.info("Disconnected from Hammer Pro")
            
        except Exception as e:
            self.logger.error(f"Error during disconnect: {str(e)}")
            
    def handle_market_data_update(self, update_data):
        """Market data güncellemelerini işle"""
        try:
            symbol = update_data.get('sym')
            if symbol:
                self.client.market_data[symbol] = update_data
                
        except Exception as e:
            self.logger.error(f"Error handling market data update: {e}")
            
    def get_positions(self):
        """Pozisyonları al"""
        if not self.connected:
            return []
            
        try:
            # Hammer Pro'dan pozisyonları al
            cmd = {
                "cmd": "getPortSnapshot",
                "portID": "current"  # Aktif portfolio
            }
            
            if not self.client._send_command(cmd):
                self.logger.error("Failed to get positions")
                return []
                
            # Response will come through websocket
            time.sleep(0.1)
            
            # Format positions
            positions = []
            for symbol, data in self.client.market_data.items():
                if data.get('qty', 0) != 0:  # Sadece pozisyonu olanları al
                    positions.append({
                        'symbol': symbol,
                        'quantity': data.get('qty', 0),
                        'avgCost': data.get('avgCost', 0)
                    })
                    
            return positions
            
        except Exception as e:
            self.logger.error(f"Error getting positions: {e}")
            return []