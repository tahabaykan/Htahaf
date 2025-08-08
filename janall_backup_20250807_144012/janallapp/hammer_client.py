"""
Hammer Pro API client modülü.
"""

import websocket
import json
import logging
import time
import threading
from datetime import datetime

class HammerClient:
    def __init__(self, host='127.0.0.1', port=16400, password=None):
        self.host = host
        self.port = port
        self.password = password
        self.url = None  # Bağlantı sırasında oluşturulacak
        self.ws = None
        self.connected = False
        self.authenticated = False
        self.market_data = {}
        self.l2_data = {}  # L2 verilerini saklamak için
        
        # Logging ayarları
        self.logger = logging.getLogger('hammer_client')
        self.logger.setLevel(logging.WARNING)  # Debug mesajlarını kapat
        
    def connect(self):
        """Hammer Pro'ya bağlan"""
        if not self.password:
            print("[HAMMER] ❌ API şifresi ayarlanmamış!")
            return False

        try:
            self.url = f"ws://{self.host}:{self.port}"
            print(f"[HAMMER] 🔗 Bağlanılıyor: {self.url}")
            
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
            
    def _on_message(self, ws, message):
        """Gelen WebSocket mesajlarını işle"""
        try:
            # CONNECTED mesajını işle
            if message.strip() == "CONNECTED":
                return
                
            # JSON mesajını parse et
            data = json.loads(message)
            cmd = data.get("cmd", "")
            success = data.get("success", "")
            result = data.get("result", {})
            
            # Debug: Gelen mesajı göster
            print(f"[HAMMER] 📥 Mesaj: {cmd}")
            
            # Mesaj tipine göre işle
            if cmd == "connect":
                if success == "OK":
                    self.authenticated = True
                    print("[HAMMER] ✅ Hammer Pro bağlantısı başarılı")
                    
                    # Bağlantı başarılı, streamer'ları başlat
                    # L1 verisi için ALARICQ
                    l1_cmd = {
                        "cmd": "startDataStreamer",
                        "streamerID": "ALARICQ"
                    }
                    self._send_command(l1_cmd)
                    
                    # L2 verisi için GSMQUOTES
                    l2_cmd = {
                        "cmd": "startDataStreamer",
                        "streamerID": "GSMQUOTES"
                    }
                    self._send_command(l2_cmd)
                    
            elif cmd == "startDataStreamer":
                if success == "OK":
                    print("[HAMMER] ✅ Data streamer başlatıldı")
                    
            elif cmd == "L1Update":
                # L1 market data update
                symbol = result.get('sym')
                print(f"[HAMMER] 📊 L1 Update: {symbol}")
                
                # Debug raw bid/ask values
                raw_bid = result.get('bid')
                raw_ask = result.get('ask')
                raw_last = result.get('last')
                print(f"[HAMMER] 🔍 L1 Raw: bid={raw_bid}({type(raw_bid)}), ask={raw_ask}({type(raw_ask)}), last={raw_last}({type(raw_last)})")
                
                self._handle_market_data(result)
                
            elif cmd == "getSymbolSnapshot":
                if success == "OK":
                    print(f"[HAMMER] 📸 Snapshot: {result.get('sym')}")
                    self._handle_market_data(result)
                    
            elif cmd == "getQuotes":
                try:
                    if success != "OK":
                        print(f"[HATA] Quotes hatası: {result}")
                        return
                        
                    print(f"[HAMMER] 📚 Quotes alındı")
                    print(f"[HAMMER] 📦 Veri: {result}")
                    
                    # Veriyi işle
                    if isinstance(result, str):
                        result = json.loads(result)
                    
                    # L2 verisini dönüştür
                    l2_data = {
                        "sym": result.get("sym", ""),
                        "bids": [],
                        "asks": [],
                        "last_prints": []
                    }
                    
                    # Bid/Ask verilerini dönüştür
                    for bid in result.get("bids", []):
                        try:
                            if isinstance(bid, str):
                                parts = bid.split(",")
                                if len(parts) >= 3:
                                    l2_data["bids"].append({
                                        "price": float(parts[0]),
                                        "size": float(parts[1]),
                                        "venue": parts[2].strip()
                                    })
                            elif isinstance(bid, dict):
                                l2_data["bids"].append({
                                    "price": float(bid.get("price", 0)),
                                    "size": float(bid.get("size", 0)),
                                    "venue": bid.get("MMID", bid.get("venue", "N/A"))
                                })
                        except Exception as e:
                            print(f"[HATA] Bid verisi parse edilemedi: {bid} - {e}")
                            continue
                            
                    for ask in result.get("asks", []):
                        try:
                            if isinstance(ask, str):
                                parts = ask.split(",")
                                if len(parts) >= 3:
                                    l2_data["asks"].append({
                                        "price": float(parts[0]),
                                        "size": float(parts[1]),
                                        "venue": parts[2].strip()
                                    })
                            elif isinstance(ask, dict):
                                l2_data["asks"].append({
                                    "price": float(ask.get("price", 0)),
                                    "size": float(ask.get("size", 0)),
                                    "venue": ask.get("MMID", ask.get("venue", "N/A"))
                                })
                        except Exception as e:
                            print(f"[HATA] Ask verisi parse edilemedi: {ask} - {e}")
                            continue
                            
                    # Son işlemleri dönüştür
                    for trade in result.get("prints", []):  # trades yerine prints!
                        try:
                            if isinstance(trade, str):
                                parts = trade.split(",")
                                if len(parts) >= 4:
                                    l2_data["last_prints"].append({
                                        "time": parts[0],
                                        "price": float(parts[1]),
                                        "size": float(parts[2]),
                                        "venue": parts[3].strip()
                                    })
                            elif isinstance(trade, dict):
                                l2_data["last_prints"].append({
                                    "time": trade.get("timeStamp", trade.get("time", datetime.now().strftime("%H:%M:%S"))),
                                    "price": float(trade.get("price", 0)),
                                    "size": float(trade.get("size", 0)),
                                    "venue": trade.get("MMID", trade.get("venue", "N/A"))
                                })
                        except Exception as e:
                            print(f"[HATA] Print verisi parse edilemedi: {trade} - {e}")
                            continue
                    
                    # Debug: Parse edilen veriyi göster
                    print(f"[HAMMER] 📊 L2 Data:")
                    print(f"  Bids: {len(l2_data['bids'])} adet")
                    print(f"  Asks: {len(l2_data['asks'])} adet")
                    print(f"  Last Prints: {len(l2_data['last_prints'])} adet")
                    
                    self._handle_l2_data(l2_data)
                    
                except Exception as e:
                    print(f"[HATA] Quotes verisi işlenirken hata: {e}")
                    
            elif cmd == "L2Update":
                try:
                    # L2Update mesajı farklı formatta geliyor
                    if isinstance(data, dict):
                        l2_data = data
                    elif isinstance(data, str):
                        l2_data = json.loads(data)
                    else:
                        print(f"[HATA] Bilinmeyen L2Update formatı: {type(data)}")
                        return
                        
                    # Sembol bilgisini al
                    symbol = l2_data.get('sym', '')
                    if not symbol:
                        print(f"[HATA] L2Update verisinde sembol yok: {l2_data}")
                        return
                        
                    print(f"[HAMMER] 📊 L2Update: {symbol}")
                    
                    # Veriyi işle
                    self._handle_l2_data(l2_data)
                    
                except Exception as e:
                    print(f"[HATA] L2Update verisi işlenirken hata: {e}")
                
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
                
            # ETF listesi
            etf_list = ["SHY", "IEF", "TLT", "IWM", "KRE", "SPY", "PFF", "PGF"]
                
            # Sembolü geri çevir (örn: AHL-E -> AHL PRE)
            display_symbol = symbol
            if symbol in etf_list:
                # ETF'ler için değişiklik yok
                display_symbol = symbol
            elif "-" in symbol:
                base, suffix = symbol.split("-")
                if len(suffix) == 1:  # Tek harf suffix
                    display_symbol = f"{base} PR{suffix}"
                
            # Safe float conversion helper
            def safe_float(value, default=0):
                if value is None or value == "":
                    return default
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return default
            
            # Market data'yı parse et (string değerleri düzgün convert et)
            last_price = safe_float(data.get("last")) or safe_float(data.get("price"))
            bid_price = safe_float(data.get("bid"))
            ask_price = safe_float(data.get("ask"))
            
            market_data = {
                "price": last_price,
                "bid": bid_price,
                "ask": ask_price,
                "last": last_price,
                "size": safe_float(data.get("lastTradeSize")) or safe_float(data.get("size")),
                "volume": safe_float(data.get("volume")),
                "prevClose": safe_float(data.get("prevClose")) or safe_float(data.get("previClose")) or safe_float(data.get("close")),
                "timestamp": data.get("timestamp", data.get("timeStamp", datetime.now().isoformat())),
                "is_live": True,
                "change": safe_float(data.get("change"))
            }
            
            # Veriyi display_symbol ile sakla
            self.market_data[display_symbol] = market_data
            
        except Exception as e:
            self.logger.error(f"Error handling market data: {e}")
            
    def _handle_l2_data(self, data):
        """L2 verilerini işle"""
        try:
            symbol = data.get("sym")
            if not symbol:
                return
                
            # Sembolü geri çevir
            display_symbol = symbol
            if "-" in symbol:
                base, suffix = symbol.split("-")
                if len(suffix) == 1:
                    display_symbol = f"{base} PR{suffix}"
                    
            # Mevcut veriyi al veya yeni oluştur
            l2_data = self.l2_data.get(display_symbol, {
                "bids": [],
                "asks": [],
                "last_prints": [],
                "timestamp": datetime.now().isoformat()
            })
            
            # Bid ve Ask güncellemeleri
            if "bids" in data:
                bids = []
                for bid_data in data["bids"]:
                    try:
                        if isinstance(bid_data, dict):
                            # Dict formatı
                            bids.append({
                                "price": float(bid_data.get("price", 0)),
                                "size": float(bid_data.get("size", 0)),
                                "venue": bid_data.get("MMID", "N/A")
                            })
                        elif isinstance(bid_data, str):
                            # String formatı: "price,size,venue"
                            parts = bid_data.split(",")
                            if len(parts) >= 3:
                                bids.append({
                                    "price": float(parts[0]),
                                    "size": float(parts[1]),
                                    "venue": parts[2].strip()
                                })
                    except Exception as e:
                        print(f"[HATA] Bid verisi parse edilemedi: {bid_data} - {e}")
                        continue
                
                # Fiyata göre sırala (büyükten küçüğe)
                bids.sort(key=lambda x: float(x["price"]), reverse=True)
                l2_data["bids"] = bids[:7]  # İlk 7 bid
                
            if "asks" in data:
                asks = []
                for ask_data in data["asks"]:
                    try:
                        if isinstance(ask_data, dict):
                            # Dict formatı
                            asks.append({
                                "price": float(ask_data.get("price", 0)),
                                "size": float(ask_data.get("size", 0)),
                                "venue": ask_data.get("MMID", "N/A")
                            })
                        elif isinstance(ask_data, str):
                            # String formatı: "price,size,venue"
                            parts = ask_data.split(",")
                            if len(parts) >= 3:
                                asks.append({
                                    "price": float(parts[0]),
                                    "size": float(parts[1]),
                                    "venue": parts[2].strip()
                                })
                    except Exception as e:
                        print(f"[HATA] Ask verisi parse edilemedi: {ask_data} - {e}")
                        continue
                
                # Fiyata göre sırala (küçükten büyüğe)
                asks.sort(key=lambda x: float(x["price"]))
                l2_data["asks"] = asks[:7]  # İlk 7 ask
                
            # Last prints güncellemeleri
            if "prints" in data:
                prints = []
                for print_data in data["prints"]:
                    try:
                        if isinstance(print_data, dict):
                            # Dict formatı
                            prints.append({
                                "time": print_data.get("timeStamp", datetime.now().strftime("%H:%M:%S")),
                                "price": float(print_data.get("price", 0)),
                                "size": float(print_data.get("size", 0)),
                                "venue": print_data.get("MMID", "N/A")
                            })
                        elif isinstance(print_data, str):
                            # String formatı: "time,price,size,venue"
                            parts = print_data.split(",")
                            if len(parts) >= 4:
                                prints.append({
                                    "time": parts[0],
                                    "price": float(parts[1]),
                                    "size": float(parts[2]),
                                    "venue": parts[3].strip()
                                })
                    except Exception as e:
                        print(f"[HATA] Print verisi parse edilemedi: {print_data} - {e}")
                        continue
                
                # Yeni printleri ekle ve son 10'u tut
                if prints:
                    l2_data["last_prints"] = (prints + l2_data["last_prints"])[:10]
            
            # Timestamp güncelle
            l2_data["timestamp"] = datetime.now().isoformat()
            
            # Debug
            print(f"[HAMMER] 📊 L2 Data güncellendi: {display_symbol}")
            print(f"  - Bids: {len(l2_data['bids'])} adet")
            print(f"  - Asks: {len(l2_data['asks'])} adet")
            print(f"  - Last Prints: {len(l2_data['last_prints'])} adet")
            
            # Veriyi sakla
            self.l2_data[display_symbol] = l2_data
            
        except Exception as e:
            print(f"[HATA] L2 verisi işlenirken hata: {e}")
            
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
        print("[HAMMER] 🔗 WebSocket bağlantısı açıldı")
        
        # Authentication gönder
        auth_cmd = {
            "cmd": "connect",
            "pwd": self.password
        }
        self._send_command(auth_cmd)
        
    def _send_command(self, command):
        """WebSocket'e komut gönder"""
        try:
            self.ws.send(json.dumps(command))
            return True
        except Exception as e:
            self.logger.error(f"Error sending command: {e}")
            return False
            
    def get_symbol_snapshot(self, symbol):
        """Bir sembol için snapshot verilerini al (previous close dahil)"""
        if not self.connected or not self.authenticated:
            return False
            
        # ETF listesi
        etf_list = ["SPY", "TLT", "IEF", "IEI", "PFF", "KRE", "IWM"]
        
        # Sembolü formatla
        formatted_symbol = symbol
        if symbol in etf_list:
            # ETF'ler için format değişikliği yok
            formatted_symbol = symbol
        elif " PR" in symbol:
            # Basit kural: " PR" (boşluk + PR) varsa "-" ile değiştir
            # Örn: "AHL PRE" -> "AHL-E", "VNO PRN" -> "VNO-N", "TRTX PRC" -> "TRTX-C"
            formatted_symbol = symbol.replace(" PR", "-")
            
        print(f"[HAMMER] 📸 Snapshot Request: {symbol} -> {formatted_symbol}")
            
        # Snapshot isteği gönder
        snapshot_cmd = {
            "cmd": "getSymbolSnapshot",
            "sym": formatted_symbol,
            "reqID": str(time.time())
        }
        return self._send_command(snapshot_cmd)

    def subscribe_symbol(self, symbol, include_l2=False):
        """Bir sembole subscribe ol - ETF'ler için sadece snapshot, preferred stocks için L1+L2"""
        if not self.connected or not self.authenticated:
            return False
            
        # ETF listesi - bunlar için L1 streaming kullanılacak (sadece Last + Change için)
        etf_list = ["SPY", "TLT", "IEF", "IEI", "PFF", "KRE", "IWM"]
        
        # Sembolü formatla
        formatted_symbol = symbol
        if symbol in etf_list:
            # ETF'ler için format değişikliği yok
            formatted_symbol = symbol

            
            # ETF'ler için de L1 streaming kullan
            l1_cmd = {
                "cmd": "subscribe",
                "sub": "L1",
                "streamerID": "ALARICQ",
                "sym": [formatted_symbol],
                "transient": False  # Veriyi database'e kaydet
            }
            return self._send_command(l1_cmd)
            
        elif " PR" in symbol:
            # Preferred stocks: "AHL PRE" -> "AHL-E", "VNO PRN" -> "VNO-N", "TRTX PRC" -> "TRTX-C"
            # Basit kural: " PR" (boşluk + PR) varsa "-" ile değiştir
            formatted_symbol = symbol.replace(" PR", "-")
            
        # PREFERRED STOCKS İÇİN SADECE L1 SUBSCRIBE! (Snapshot tamamen kaldırıldı)
        l1_cmd = {
            "cmd": "subscribe",
            "sub": "L1",
            "streamerID": "ALARICQ",
            "sym": [formatted_symbol],
            "transient": False  # Veriyi database'e kaydet
        }
        self._send_command(l1_cmd)
        
        # L2 subscribe (OrderBook için)
        if include_l2:
            # L2 verisi için GSMQUOTES kullan
            l2_cmd = {
                "cmd": "subscribe",
                "sub": "L2",
                "streamerID": "GSMQUOTES",
                "sym": [formatted_symbol],
                "changes": False  # Her seferinde tüm veriyi al
            }
            self._send_command(l2_cmd)
            
            # Başlangıç L2 verisi için
            book_cmd = {
                "cmd": "getQuotes",
                "sym": formatted_symbol,
                "streamerID": "GSMQUOTES",
                "type": "L2",  # L2 verisi için
                "maxRows": 7,  # Her seviye için maksimum satır
                "reqID": str(time.time())
            }
            self._send_command(book_cmd)
            
            # Biraz bekle
            time.sleep(0.5)
            
        return True
        
    def get_market_data(self, symbol):
        """Bir sembol için market data al"""
        return self.market_data.get(symbol, {})
        
    def get_l2_data(self, symbol):
        """Bir sembol için L2 verilerini al"""
        try:
            # Sembolü formatla - basit kural: " PR" -> "-"
            formatted_symbol = symbol
            if " PR" in symbol:
                formatted_symbol = symbol.replace(" PR", "-")
                
            # L2 verisi iste
            cmd = {
                "cmd": "getQuotes",
                "sym": formatted_symbol,
                "streamerID": "GSMQUOTES",
                "type": "L2",  # L2 verisi için
                "maxRows": 7,  # Her seviye için maksimum satır
                "reqID": str(time.time())
            }
            self._send_command(cmd)
            
            # Veriyi bekle (0.5 saniye)
            time.sleep(0.5)
            
            # Veriyi al
            return self.l2_data.get(symbol, {})
            
        except Exception as e:
            self.logger.error(f"Error getting L2 data: {e}")
            return None
        
    def disconnect(self):
        """Hammer Pro bağlantısını kapat"""
        if self.ws:
            try:
                self.ws.close()
                self.ws = None
                self.connected = False
                self.authenticated = False
                self.market_data.clear()
                self.l2_data.clear()
            except Exception as e:
                self.logger.error(f"Error disconnecting: {e}")