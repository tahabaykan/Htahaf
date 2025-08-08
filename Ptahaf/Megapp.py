import websocket
import json
import logging
import time
import threading
from datetime import datetime
from collections import defaultdict

class MegaHammerClient:
    def __init__(self, host='127.0.0.1', port=16400, password=''):
        # WebSocket bağlantı bilgileri
        self.url = f"ws://{host}:{port}"
        self.password = password
        
        # Logging ayarları
        self.logger = logging.getLogger('mega_hammer')
        self.logger.setLevel(logging.WARNING)  # Debug ve INFO mesajlarını kapat
        handler = logging.FileHandler('mega_hammer.log')
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)
        
        # Veri containerleri
        self.market_data = {}          # Sembol bazlı market data
        self.orderbooks = {}           # Sembol bazlı orderbook
        self.last_prints = {}          # Sembol bazlı son işlemler
        self.watchlists = {}           # Hammer Pro'daki watchlistler
        self.positions = {}            # Açık pozisyonlar
        self.orders = {}               # Açık orderlar
        
        # Bağlantı durumu
        self.ws = None
        self.connected = False
        self.authenticated = False
        self.req_id_counter = 0
        
        # Callback'ler
        self.on_market_data = None     # Market data güncellemesi
        self.on_orderbook = None       # Orderbook güncellemesi
        self.on_trade = None           # Yeni işlem
        self.on_position = None        # Pozisyon değişimi
        self.on_order = None           # Order durumu değişimi
        
    def _get_next_req_id(self):
        """Unique request ID üret"""
        self.req_id_counter += 1
        return str(self.req_id_counter)
        
    def _send_command(self, command, req_id=None):
        """WebSocket'e komut gönder"""
        if req_id:
            command["reqID"] = req_id
        try:
            self.ws.send(json.dumps(command))
            return True
        except Exception as e:
            self.logger.error(f"Error sending command: {e}")
            return False
            
    def _on_message(self, ws, message):
        """Gelen WebSocket mesajlarını işle"""
        try:
            # CONNECTED mesajını işle
            if message.strip() == "CONNECTED":
                self.logger.info("WebSocket CONNECTED")
                return
                
            # JSON mesajını parse et
            data = json.loads(message)
            cmd = data.get("cmd", "")
            success = data.get("success", "")
            result = data.get("result", {})
            
            # Mesaj tipine göre işle
            if cmd == "connect":
                if success == "OK":
                    self.authenticated = True
                    self.logger.info("Authenticated with Hammer Pro")
                    
                    # Önce mevcut streamerleri listele
                    self._send_command({
                        "cmd": "enumDataStreamers",
                        "reqID": self._get_next_req_id()
                    })
                    
            elif cmd == "enumDataStreamers":
                if success == "OK":
                    streamers = result
                    self.logger.info(f"Available streamers: {streamers}")
                    
                    # Data streamer'ı başlat
                    self._send_command({
                        "cmd": "startDataStreamer",
                        "streamerID": "ALARICQ"
                    })
                    
                    # Watchlistleri al
                    self._send_command({
                        "cmd": "enumPorts",
                        "reqID": self._get_next_req_id()
                    })
                    
            elif cmd == "startDataStreamer":
                if success == "OK":
                    self.logger.info("Data streamer started")
                    
            elif cmd == "enumPorts":
                if success == "OK":
                    ports = result.get("ports", [])
                    self.logger.info(f"Got portfolios: {[p['name'] for p in ports]}")
                    
                    # Her port için sembolleri al
                    for port in ports:
                        self._send_command({
                            "cmd": "enumPortSymbols",
                            "portID": port["portID"],
                            "reqID": self._get_next_req_id()
                        })
                        
            elif cmd == "enumPortSymbols":
                if success == "OK":
                    port_id = data.get("reqID")  # Port ID'yi request ID'den alıyoruz
                    symbols = result
                    
                    if isinstance(symbols, list):  # Basit sembol listesi
                        self.watchlists[port_id] = {
                            "symbols": symbols
                        }
                        # Sembollere subscribe ol
                        for symbol in symbols:
                            self.subscribe_symbol(symbol)
                    else:  # Detaylı sembol bilgisi
                        symbols_list = [item["sym"] for item in symbols]
                        self.watchlists[port_id] = {
                            "symbols": symbols_list
                        }
                        # Sembollere subscribe ol
                        for symbol in symbols_list:
                            self.subscribe_symbol(symbol)
                            
            elif cmd == "L1Update":
                # L1 market data update
                self._handle_market_data(result)
            elif cmd == "L2Update":
                # L2 (depth) update
                self._handle_depth_update(result)
            elif cmd == "positionUpdate":
                self._handle_position_update(result)
                
            elif cmd == "orderUpdate":
                self._handle_order_update(result)
                
        except json.JSONDecodeError:
            pass
        except Exception as e:
            self.logger.error(f"Error handling message: {e}")
            
    def _handle_market_data(self, data):
        """Market data güncellemelerini işle"""
        try:
            symbol = data.get("sym")
            if not symbol:
                return
                
            # Market data'yı parse et
            market_data = {
                "price": float(data.get("price", 0)) if data.get("price") else 0,
                "bid": float(data.get("bid", 0)) if data.get("bid") else 0,
                "ask": float(data.get("ask", 0)) if data.get("ask") else 0,
                "last": float(data.get("price", 0)) if data.get("price") else 0,  # price = last
                "size": float(data.get("size", 0)) if data.get("size") else 0,
                "volume": float(data.get("volume", 0)) if data.get("volume") else 0,
                "timestamp": data.get("timeStamp", datetime.now().isoformat()),
                "is_live": True
            }
            
            # Veriyi güncelle
            if symbol not in self.market_data:
                self.market_data[symbol] = {}
            
            # Sadece gelen değerleri güncelle
            self.market_data[symbol].update(market_data)
            
            # Callback'i çağır
            if self.on_market_data:
                self.on_market_data(symbol, self.market_data[symbol])
                
            # Eğer size > 0 ise bu bir trade'dir
            if market_data["size"] > 0:
                trade = {
                    "price": market_data["price"],
                    "size": market_data["size"],
                    "timestamp": market_data["timestamp"],
                    "MMID": data.get("MMID", ""),
                    "type": "trade"
                }
                
                # Trade listesini güncelle
                if symbol not in self.last_prints:
                    self.last_prints[symbol] = []
                
                self.last_prints[symbol].insert(0, trade)
                self.last_prints[symbol] = self.last_prints[symbol][:10]
                
                # Trade callback'ini çağır
                if self.on_trade:
                    self.on_trade(symbol, trade)
                
        except Exception as e:
            self.logger.error(f"Error handling market data: {e}")
            
    def _handle_depth_update(self, data):
        """Orderbook güncellemelerini işle"""
        try:
            symbol = data.get("sym")
            if not symbol:
                return
                
            # Orderbook verilerini al
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            # Yeni orderbook oluştur veya mevcut olanı al
            if symbol not in self.orderbooks:
                self.orderbooks[symbol] = {"bids": [], "asks": [], "timestamp": ""}
            
            current_book = self.orderbooks[symbol]
            
            # Her bir bid/ask için action'a göre işlem yap
            for bid in bids:
                act = bid.get("act")
                if act == "a":  # add
                    current_book["bids"].append(bid)
                elif act == "d":  # delete
                    current_book["bids"] = [b for b in current_book["bids"] 
                                          if not (b["MMID"] == bid["MMID"] and b["price"] == bid["price"])]
                elif act == "m":  # modify
                    for b in current_book["bids"]:
                        if b["MMID"] == bid["MMID"] and b["price"] == bid["price"]:
                            b.update(bid)
            
            for ask in asks:
                act = ask.get("act")
                if act == "a":  # add
                    current_book["asks"].append(ask)
                elif act == "d":  # delete
                    current_book["asks"] = [a for a in current_book["asks"] 
                                          if not (a["MMID"] == ask["MMID"] and a["price"] == ask["price"])]
                elif act == "m":  # modify
                    for a in current_book["asks"]:
                        if a["MMID"] == ask["MMID"] and a["price"] == ask["price"]:
                            a.update(ask)
            
            # Fiyata göre sırala
            current_book["bids"].sort(key=lambda x: float(x["price"]), reverse=True)  # En yüksek fiyat başta
            current_book["asks"].sort(key=lambda x: float(x["price"]))  # En düşük fiyat başta
            
            # Timestamp güncelle
            current_book["timestamp"] = datetime.now().isoformat()
            
            # Callback'i çağır
            if self.on_orderbook:
                self.on_orderbook(symbol, current_book)
                
        except Exception as e:
            self.logger.error(f"Error handling depth update: {e}")
            
    def _handle_trade_update(self, data):
        """Son işlem güncellemelerini işle"""
        try:
            symbol = data.get("sym")
            if not symbol:
                return
                
            # Trade verilerini parse et
            trade = {
                "price": float(data.get("price", 0)) if data.get("price") else 0,
                "size": float(data.get("size", 0)) if data.get("size") else 0,
                "timestamp": data.get("timeStamp", datetime.now().isoformat()),
                "MMID": data.get("MMID", ""),  # Market maker ID
                "type": data.get("type", "")  # Trade tipi
            }
            
            # Sembol için trade listesi oluştur
            if symbol not in self.last_prints:
                self.last_prints[symbol] = []
                
            # Yeni trade'i ekle ve son 10 trade'i tut
            self.last_prints[symbol].insert(0, trade)
            self.last_prints[symbol] = self.last_prints[symbol][:10]
            
            # Callback'i çağır
            if self.on_trade:
                self.on_trade(symbol, trade)
                
        except Exception as e:
            self.logger.error(f"Error handling trade update: {e}")
            
    def _handle_position_update(self, data):
        """Pozisyon güncellemelerini işle"""
        try:
            positions = data.get("positions", [])
            
            # Pozisyonları güncelle
            for pos in positions:
                symbol = pos.get("symbol")
                if symbol:
                    self.positions[symbol] = pos
                    
            # Callback'i çağır
            if self.on_position:
                self.on_position(self.positions)
                
        except Exception as e:
            self.logger.error(f"Error handling position update: {e}")
            
    def _handle_order_update(self, data):
        """Order güncellemelerini işle"""
        try:
            orders = data.get("orders", [])
            
            # Orderları güncelle
            for order in orders:
                order_id = order.get("orderId")
                if order_id:
                    self.orders[order_id] = order
                    
            # Callback'i çağır
            if self.on_order:
                self.on_order(self.orders)
                
        except Exception as e:
            self.logger.error(f"Error handling order update: {e}")
            
    def _on_error(self, ws, error):
        """WebSocket hatalarını işle"""
        self.logger.error(f"WebSocket error: {error}")
        self.connected = False
        self.authenticated = False
        
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket kapanışını işle"""
        self.logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.connected = False
        self.authenticated = False
        
    def _on_open(self, ws):
        """WebSocket açılışını işle"""
        self.connected = True
        self.logger.info("WebSocket opened")
        
        # Authentication gönder
        auth_cmd = {
            "cmd": "connect",
            "pwd": self.password
        }
        self._send_command(auth_cmd)
        
    def connect(self):
        """Hammer Pro'ya bağlan"""
        try:
            self.ws = websocket.WebSocketApp(
                self.url,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open
            )
            
            # WebSocket'i ayrı thread'de başlat
            self.ws_thread = threading.Thread(target=self.ws.run_forever)
            self.ws_thread.daemon = True
            self.ws_thread.start()
            
            # Bağlantı için bekle
            timeout = 10
            start_time = time.time()
            while not self.connected and time.time() - start_time < timeout:
                time.sleep(0.1)
                
            return self.connected
            
        except Exception as e:
            self.logger.error(f"Error connecting: {e}")
            return False
            
    def disconnect(self):
        """Hammer Pro'dan bağlantıyı kes"""
        if self.ws:
            self.ws.close()
            
    def subscribe_symbol(self, symbol):
        """Bir sembole subscribe ol"""
        if not self.connected or not self.authenticated:
            self.logger.error("Not connected/authenticated")
            return False
            
        # Sembolü formatla
        if " PR" in symbol:
            base, suffix = symbol.split(" PR")
            formatted_symbol = f"{base}-{suffix}"
        else:
            formatted_symbol = symbol
            
        # L1 market data subscription
        self._send_command({
            "cmd": "subscribe",
            "sub": "L1",
            "streamerID": "ALARICQ",
            "sym": [formatted_symbol],
            "transient": False  # Datayı database'e kaydet
        })

        # L2 (depth) subscription
        self._send_command({
            "cmd": "subscribe",
            "sub": "L2",
            "streamerID": "ALARICQ",
            "sym": [formatted_symbol],
            "changes": False,  # Her update'te tüm book'u gönder
            "maxRows": 10  # En fazla 10 seviye
        })

        # Trade prints subscription - L1 ile birlikte geliyor
        # Hammer Pro API'sinde trade verisi L1 subscription içinde geliyor
        # Ayrı bir "trades" subscription'a gerek yok
        # L1Update mesajlarında size > 0 ise bu bir trade'dir
        
        return True
        
    def get_market_data(self, symbol):
        """Bir sembol için market data al"""
        return self.market_data.get(symbol, {})
        
    def get_orderbook(self, symbol):
        """Bir sembol için orderbook al"""
        return self.orderbooks.get(symbol, {"bids": [], "asks": []})
        
    def get_last_prints(self, symbol):
        """Bir sembol için son işlemleri al"""
        return self.last_prints.get(symbol, [])
        
    def get_positions(self):
        """Tüm pozisyonları al"""
        return self.positions
        
    def get_orders(self):
        """Tüm orderları al"""
        return self.orders
        
    def get_watchlists(self):
        """Tüm watchlistleri al"""
        return self.watchlists
        
    def create_watchlist(self, name, symbols, data=None):
        """Yeni bir watchlist oluştur
        
        Args:
            name (str): Watchlist adı
            symbols (list): Sembol listesi
            data (dict): Her sembol için ek veri (opsiyonel)
        """
        if not self.connected or not self.authenticated:
            self.logger.error("Not connected/authenticated")
            return False
            
        # Watchlist oluştur
        cmd = {
            "cmd": "addToPort",
            "new": True,
            "name": name,
            "items": []
        }
        
        # Sembolleri ekle
        for symbol in symbols:
            item = {
                "sym": symbol
            }
            if data and symbol in data:
                item.update(data[symbol])
            cmd["items"].append(item)
            
        return self._send_command(cmd)
        
    def place_order(self, symbol, side, quantity, order_type="Market", limit_price=None):
        """Yeni order gönder"""
        if not self.connected or not self.authenticated:
            self.logger.error("Not connected/authenticated")
            return False
            
        order = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "type": order_type
        }
        
        if limit_price:
            order["limitPrice"] = limit_price
            
        cmd = {
            "cmd": "placeOrder",
            "order": order
        }
        
        return self._send_command(cmd)
        
    def cancel_order(self, order_id):
        """Order iptal et"""
        if not self.connected or not self.authenticated:
            self.logger.error("Not connected/authenticated")
            return False
            
        cmd = {
            "cmd": "cancelOrder",
            "orderId": order_id
        }
        
        return self._send_command(cmd)

# Örnek kullanım
def main():
    # Logging ayarları
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Client oluştur
    client = MegaHammerClient(
        host='127.0.0.1',
        port=16400,
        password='YOUR_PASSWORD'  # Hammer Pro API şifrenizi buraya girin
    )
    
    # Market data callback
    def on_market_data(symbol, data):
        print(f"\nMarket Data - {symbol}:")
        print(f"Price: {data['price']}")
        print(f"Bid: {data['bid']}")
        print(f"Ask: {data['ask']}")
        print(f"Last: {data['last']}")
        
    # Orderbook callback
    def on_orderbook(symbol, data):
        print(f"\nOrderbook - {symbol}:")
        print("Bids:", data['bids'][:3])  # İlk 3 bid
        print("Asks:", data['asks'][:3])  # İlk 3 ask
        
    # Trade callback
    def on_trade(symbol, trade):
        print(f"\nTrade - {symbol}:")
        print(f"{trade['size']} @ {trade['price']}")
        
    # Position callback
    def on_position(positions):
        print("\nPositions:")
        for sym, pos in positions.items():
            print(f"{sym}: {pos['size']} @ {pos['avgPrice']}")
            
    # Order callback
    def on_order(orders):
        print("\nOrders:")
        for order_id, order in orders.items():
            print(f"{order_id}: {order['symbol']} {order['side']} {order['quantity']}")
            
    # Callback'leri ayarla
    client.on_market_data = on_market_data
    client.on_orderbook = on_orderbook
    client.on_trade = on_trade
    client.on_position = on_position
    client.on_order = on_order
    
    # Bağlan
    print("Connecting to Hammer Pro...")
    if not client.connect():
        print("Failed to connect!")
        return
        
    try:
        # Ana döngü
        while True:
            # Watchlistleri kontrol et
            watchlists = client.get_watchlists()
            for name, watchlist in watchlists.items():
                print(f"\nWatchlist: {name}")
                for symbol in watchlist.get('symbols', []):
                    # Market data al
                    data = client.get_market_data(symbol)
                    if data:
                        print(f"{symbol}: Last={data.get('last', 'N/A')} Bid={data.get('bid', 'N/A')} Ask={data.get('ask', 'N/A')}")
                        
                    # Son işlemleri al
                    trades = client.get_last_prints(symbol)
                    if trades:
                        print(f"Last trade: {trades[0]['size']} @ {trades[0]['price']}")
                        
            # 5 saniye bekle
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        client.disconnect()
        
if __name__ == "__main__":
    main()