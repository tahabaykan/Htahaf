"""
Hammer Pro API Client - NEWHAM
Hammer Pro GUI'sine bağlanarak market data ve trading işlemleri yapar.

Kullanım:
    python NEWHAM.py

Hammer Pro'da API'yi etkinleştirmeyi unutmayın:
    Settings > API > Enable Streaming API
"""

import websocket
import json
import logging
import time
import threading
from datetime import datetime
from typing import Optional, Dict, List, Any, Callable

class HammerProClient:
    """
    Hammer Pro WebSocket API Client
    
    Hammer Pro'nun WebSocket API'sine bağlanarak:
    - Market data (L1, L2) alabilir
    - Trading işlemleri yapabilir
    - Portfolios yönetebilir
    - Alerts oluşturabilir
    - Historical data çekebilir
    """
    
    def __init__(self, host='127.0.0.1', port=16400, password=None):
        """
        Hammer Pro Client başlat
        
        Args:
            host: Hammer Pro API host (default: 127.0.0.1)
            port: Hammer Pro API port (Hammer Pro Settings'ten alınır, default: 16400)
            password: Hammer Pro login şifresi
        """
        self.host = host
        self.port = port
        self.password = password
        self.url = f"ws://{host}:{port}"
        
        # WebSocket bağlantısı
        self.ws = None
        self.connected = False
        self.authenticated = False
        
        # Veri saklama
        self.market_data = {}  # L1 verileri: {symbol: {bid, ask, last, ...}}
        self.l2_data = {}      # L2 verileri: {symbol: {bids: [], asks: []}}
        self.positions = []    # Trading pozisyonları
        self.balances = {}     # Hesap bakiyeleri
        self.transactions = [] # İşlemler/emirler
        
        # Streamer ve account durumları
        self.data_streamers = {}  # {streamerID: {name, isSet, state}}
        self.trading_accounts = {} # {accountKey: {state, ...}}
        
        # Callback'ler
        self.on_l1_update: Optional[Callable] = None
        self.on_l2_update: Optional[Callable] = None
        self.on_position_update: Optional[Callable] = None
        self.on_fill: Optional[Callable] = None
        self.on_alert: Optional[Callable] = None
        
        # Senkron yanıt beklemek için
        self._pending_responses = {}
        self._pending_lock = threading.Lock()
        self._req_id_counter = 0
        
        # Logging
        self.logger = logging.getLogger('HammerProClient')
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(handler)
        
    def connect(self) -> bool:
        """
        Hammer Pro'ya bağlan ve authenticate ol
        
        Returns:
            bool: Bağlantı başarılı ise True
        """
        if not self.password:
            self.logger.error("❌ API şifresi ayarlanmamış!")
            return False
        
        try:
            self.logger.info(f"🔗 Hammer Pro'ya bağlanılıyor: {self.url}")
            
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
            
            if not self.connected:
                self.logger.error("❌ WebSocket bağlantısı zaman aşımına uğradı")
                return False
            
            # Authentication için bekle
            start_time = time.time()
            while not self.authenticated and time.time() - start_time < timeout:
                time.sleep(0.1)
            
            if not self.authenticated:
                self.logger.error("❌ Authentication zaman aşımına uğradı")
                return False
            
            self.logger.info("✅ Hammer Pro bağlantısı başarılı!")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Bağlantı hatası: {e}")
            return False
    
    def _on_open(self, ws):
        """WebSocket açıldığında çağrılır"""
        self.connected = True
        self.logger.info("🔗 WebSocket bağlantısı açıldı")
        
        # Authentication gönder
        auth_cmd = {
            "cmd": "connect",
            "pwd": self.password
        }
        self._send_command(auth_cmd)
    
    def _on_message(self, ws, message):
        """Gelen WebSocket mesajlarını işle"""
        try:
            # CONNECTED mesajını atla
            if message.strip() == "CONNECTED":
                return
            
            # JSON parse et
            data = json.loads(message)
            cmd = data.get("cmd", "")
            success = data.get("success", "")
            result = data.get("result", {})
            req_id = data.get("reqID")
            
            # Bekleyen yanıtları kaydet
            if req_id:
                with self._pending_lock:
                    self._pending_responses[req_id] = data
            
            # Komut tipine göre işle
            if cmd == "connect":
                if success == "OK":
                    self.authenticated = True
                    self.logger.info("✅ Authentication başarılı")
                    # Bağlantı sonrası otomatik işlemler
                    self._after_connect()
                else:
                    self.logger.error(f"❌ Authentication hatası: {result}")
            
            elif cmd == "closing":
                self.logger.warning("⚠️ Hammer Pro kapanıyor...")
                self.connected = False
                self.authenticated = False
            
            elif cmd == "L1Update":
                self._handle_l1_update(result)
            
            elif cmd == "L2Update":
                self._handle_l2_update(result)
            
            elif cmd == "positionsUpdate":
                self._handle_positions_update(result)
            
            elif cmd == "balancesUpdate":
                self._handle_balances_update(result)
            
            elif cmd == "transactionsUpdate":
                self._handle_transactions_update(result)
            
            elif cmd == "alertTriggerUpdate":
                self._handle_alert_trigger(result)
            
            elif cmd == "newsUpdate":
                self._handle_news_update(result)
            
            elif cmd == "dataStreamerStateUpdate":
                self._handle_streamer_state_update(result)
            
            elif cmd == "tradingAccountStateUpdate":
                self._handle_account_state_update(result)
            
        except json.JSONDecodeError as e:
            self.logger.error(f"❌ JSON parse hatası: {e}")
        except Exception as e:
            self.logger.error(f"❌ Mesaj işleme hatası: {e}")
    
    def _after_connect(self):
        """Bağlantı sonrası otomatik işlemler"""
        # Data streamer'ları listele
        self.enum_data_streamers()
        # Trading account'ları listele
        self.enum_trading_accounts()
    
    def _handle_l1_update(self, result: Dict):
        """L1 market data güncellemesini işle"""
        try:
            symbol = result.get("sym")
            if not symbol:
                return
            
            # Market data'yı sakla
            self.market_data[symbol] = {
                "sym": symbol,
                "bid": float(result.get("bid", 0)),
                "ask": float(result.get("ask", 0)),
                "last": float(result.get("price", result.get("last", 0))),
                "size": float(result.get("size", 0)),
                "volume": float(result.get("volume", 0)),
                "timestamp": result.get("timeStamp", datetime.now().isoformat())
            }
            
            # Callback çağır
            if self.on_l1_update:
                try:
                    self.on_l1_update(self.market_data[symbol])
                except Exception as e:
                    self.logger.error(f"❌ L1 callback hatası: {e}")
                    
        except Exception as e:
            self.logger.error(f"❌ L1 update işleme hatası: {e}")
    
    def _handle_l2_update(self, result: Dict):
        """L2 (depth) market data güncellemesini işle"""
        try:
            symbol = result.get("sym")
            if not symbol:
                return
            
            # L2 verisini sakla
            if symbol not in self.l2_data:
                self.l2_data[symbol] = {"bids": [], "asks": []}
            
            # Bids güncelle
            if "bids" in result:
                for bid in result["bids"]:
                    act = bid.get("act")  # a=add, d=delete, m=modify
                    mmid = bid.get("MMID")
                    price = float(bid.get("price", 0))
                    size = float(bid.get("size", 0))
                    
                    if act == "a" or act == "m":
                        # Ekle veya güncelle
                        existing = next((b for b in self.l2_data[symbol]["bids"] 
                                       if b.get("MMID") == mmid and abs(b.get("price", 0) - price) < 0.001), None)
                        if existing:
                            existing["price"] = price
                            existing["size"] = size
                        else:
                            self.l2_data[symbol]["bids"].append({
                                "MMID": mmid,
                                "price": price,
                                "size": size
                            })
                    elif act == "d":
                        # Sil
                        self.l2_data[symbol]["bids"] = [
                            b for b in self.l2_data[symbol]["bids"]
                            if not (b.get("MMID") == mmid and abs(b.get("price", 0) - price) < 0.001)
                        ]
                
                # Fiyata göre sırala (büyükten küçüğe)
                self.l2_data[symbol]["bids"].sort(key=lambda x: x["price"], reverse=True)
            
            # Asks güncelle
            if "asks" in result:
                for ask in result["asks"]:
                    act = ask.get("act")
                    mmid = ask.get("MMID")
                    price = float(ask.get("price", 0))
                    size = float(ask.get("size", 0))
                    
                    if act == "a" or act == "m":
                        existing = next((a for a in self.l2_data[symbol]["asks"]
                                       if a.get("MMID") == mmid and abs(a.get("price", 0) - price) < 0.001), None)
                        if existing:
                            existing["price"] = price
                            existing["size"] = size
                        else:
                            self.l2_data[symbol]["asks"].append({
                                "MMID": mmid,
                                "price": price,
                                "size": size
                            })
                    elif act == "d":
                        self.l2_data[symbol]["asks"] = [
                            a for a in self.l2_data[symbol]["asks"]
                            if not (a.get("MMID") == mmid and abs(a.get("price", 0) - price) < 0.001)
                        ]
                
                # Fiyata göre sırala (küçükten büyüğe)
                self.l2_data[symbol]["asks"].sort(key=lambda x: x["price"])
            
            # Callback çağır
            if self.on_l2_update:
                try:
                    self.on_l2_update(self.l2_data[symbol])
                except Exception as e:
                    self.logger.error(f"❌ L2 callback hatası: {e}")
                    
        except Exception as e:
            self.logger.error(f"❌ L2 update işleme hatası: {e}")
    
    def _handle_positions_update(self, result: Any):
        """Pozisyon güncellemelerini işle"""
        try:
            if isinstance(result, list):
                self.positions = result
            elif isinstance(result, dict) and "positions" in result:
                self.positions = result["positions"]
            
            # Callback çağır
            if self.on_position_update:
                try:
                    self.on_position_update(self.positions)
                except Exception as e:
                    self.logger.error(f"❌ Position callback hatası: {e}")
                    
        except Exception as e:
            self.logger.error(f"❌ Position update işleme hatası: {e}")
    
    def _handle_balances_update(self, result: Dict):
        """Bakiye güncellemelerini işle"""
        try:
            account_key = result.get("accountKey")
            if account_key:
                self.balances[account_key] = result
        except Exception as e:
            self.logger.error(f"❌ Balance update işleme hatası: {e}")
    
    def _handle_transactions_update(self, result: Dict):
        """İşlem güncellemelerini işle (emirler, fill'ler)"""
        try:
            transactions = result.get("transactions", [])
            for tx in transactions:
                # Yeni fill'leri yakala
                if tx.get("StatusID") == "Filled" and tx.get("New", False):
                    if self.on_fill:
                        try:
                            self.on_fill(tx)
                        except Exception as e:
                            self.logger.error(f"❌ Fill callback hatası: {e}")
        except Exception as e:
            self.logger.error(f"❌ Transaction update işleme hatası: {e}")
    
    def _handle_alert_trigger(self, result: Dict):
        """Alert tetiklendiğinde çağrılır"""
        try:
            if self.on_alert:
                self.on_alert(result)
        except Exception as e:
            self.logger.error(f"❌ Alert callback hatası: {e}")
    
    def _handle_news_update(self, result: Dict):
        """News güncellemesini işle"""
        self.logger.info(f"📰 News: {result.get('title', 'N/A')}")
    
    def _handle_streamer_state_update(self, result: Dict):
        """Data streamer durum güncellemesini işle"""
        streamer_id = result.get("streamerID")
        state = result.get("state")
        if streamer_id:
            if streamer_id not in self.data_streamers:
                self.data_streamers[streamer_id] = {}
            self.data_streamers[streamer_id]["state"] = state
    
    def _handle_account_state_update(self, result: Dict):
        """Trading account durum güncellemesini işle"""
        account_key = result.get("accountKey")
        state = result.get("state")
        if account_key:
            if account_key not in self.trading_accounts:
                self.trading_accounts[account_key] = {}
            self.trading_accounts[account_key]["state"] = state
    
    def _on_error(self, ws, error):
        """WebSocket hatalarını işle"""
        self.logger.error(f"❌ WebSocket hatası: {error}")
        self.connected = False
        self.authenticated = False
    
    def _on_close(self, ws, close_status_code, close_msg):
        """WebSocket kapanışını işle"""
        self.logger.info(f"🔌 WebSocket kapandı: {close_status_code} - {close_msg}")
        self.connected = False
        self.authenticated = False
    
    def _send_command(self, command: Dict) -> bool:
        """WebSocket'e komut gönder"""
        try:
            if not self.ws or not self.connected:
                self.logger.error("❌ WebSocket bağlı değil")
                return False
            
            # reqID ekle (yoksa)
            if "reqID" not in command:
                self._req_id_counter += 1
                command["reqID"] = f"req_{self._req_id_counter}_{int(time.time())}"
            
            message = json.dumps(command)
            self.ws.send(message)
            return True
        except Exception as e:
            self.logger.error(f"❌ Komut gönderme hatası: {e}")
            return False
    
    def _send_and_wait(self, command: Dict, timeout: float = 5.0) -> Optional[Dict]:
        """Komut gönder ve yanıtı bekle (blocking)"""
        req_id = command.get("reqID") or f"req_{self._req_id_counter + 1}_{int(time.time())}"
        command["reqID"] = req_id
        
        with self._pending_lock:
            self._pending_responses[req_id] = None
        
        if not self._send_command(command):
            return None
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._pending_lock:
                if req_id in self._pending_responses and self._pending_responses[req_id] is not None:
                    return self._pending_responses.pop(req_id)
            time.sleep(0.05)
        
        # Timeout
        with self._pending_lock:
            self._pending_responses.pop(req_id, None)
        
        self.logger.warning(f"⚠️ Komut yanıtı zaman aşımı: {command.get('cmd')}")
        return None
    
    # ============ DATA STREAMERS ============
    
    def enum_data_streamers(self) -> List[Dict]:
        """Mevcut data streamer'ları listele"""
        resp = self._send_and_wait({"cmd": "enumDataStreamers"})
        if resp and resp.get("success") == "OK":
            streamers = resp.get("result", [])
            self.logger.info(f"✅ {len(streamers)} data streamer bulundu")
            for s in streamers:
                self.data_streamers[s.get("streamerID")] = s
            return streamers
        return []
    
    def start_data_streamer(self, streamer_id: str, refresh: Optional[int] = None) -> bool:
        """Data streamer'ı başlat"""
        cmd = {"cmd": "startDataStreamer", "streamerID": streamer_id}
        if refresh:
            cmd["refresh"] = refresh
        
        resp = self._send_and_wait(cmd)
        if resp and resp.get("success") == "OK":
            self.logger.info(f"✅ Streamer başlatıldı: {streamer_id}")
            return True
        return False
    
    def stop_data_streamer(self, streamer_id: str) -> bool:
        """Data streamer'ı durdur"""
        resp = self._send_and_wait({"cmd": "stopDataStreamer", "streamerID": streamer_id})
        if resp and resp.get("success") == "OK":
            self.logger.info(f"✅ Streamer durduruldu: {streamer_id}")
            return True
        return False
    
    def subscribe(self, streamer_id: str, sub_type: str, symbols: List[str], 
                  transient: bool = False, changes: bool = True, max_rows: Optional[int] = None) -> bool:
        """
        Market data'ya subscribe ol
        
        Args:
            streamer_id: Streamer ID
            sub_type: "L1" veya "L2"
            symbols: Sembol listesi
            transient: L1 için - veriyi database'e kaydetme
            changes: L2 için - sadece değişiklikleri gönder
            max_rows: L2 için - maksimum satır sayısı
        """
        cmd = {
            "cmd": "subscribe",
            "streamerID": streamer_id,
            "sub": sub_type,
            "sym": symbols
        }
        
        if sub_type == "L1":
            cmd["transient"] = transient
        elif sub_type == "L2":
            cmd["changes"] = changes
            if max_rows:
                cmd["maxRows"] = max_rows
        
        resp = self._send_and_wait(cmd)
        if resp and resp.get("success") == "OK":
            subbed = resp.get("result", {}).get("subbed", [])
            self.logger.info(f"✅ {len(subbed)} sembole subscribe olundu: {sub_type}")
            return True
        return False
    
    def unsubscribe(self, streamer_id: str, sub_type: str, symbols: List[str]) -> bool:
        """Market data'dan unsubscribe ol"""
        cmd = {
            "cmd": "unsubscribe",
            "streamerID": streamer_id,
            "sub": sub_type,
            "sym": symbols if symbols != ["*"] else "*"
        }
        
        resp = self._send_and_wait(cmd)
        if resp and resp.get("success") == "OK":
            self.logger.info(f"✅ Unsubscribe başarılı: {sub_type}")
            return True
        return False
    
    def get_subscriptions(self, streamer_id: str, sub_type: str) -> List[str]:
        """Subscribe olunan sembolleri listele"""
        resp = self._send_and_wait({
            "cmd": "getSubscriptions",
            "streamerID": streamer_id,
            "sub": sub_type
        })
        if resp and resp.get("success") == "OK":
            return resp.get("result", {}).get("subbed", [])
        return []
    
    # ============ TRADING ============
    
    def enum_trading_accounts(self) -> List[Dict]:
        """Trading account'ları listele"""
        resp = self._send_and_wait({"cmd": "enumTradingAccounts"})
        if resp and resp.get("success") == "OK":
            accounts = resp.get("result", {}).get("accounts", [])
            self.logger.info(f"✅ {len(accounts)} trading account bulundu")
            return accounts
        return []
    
    def start_trading_account(self, account_key: str) -> bool:
        """Trading account'ı başlat"""
        resp = self._send_and_wait({
            "cmd": "startTradingAccount",
            "accountKey": account_key
        })
        if resp and resp.get("success") == "OK":
            self.logger.info(f"✅ Trading account başlatıldı: {account_key}")
            return True
        return False
    
    def stop_trading_account(self, account_key: str) -> bool:
        """Trading account'ı durdur"""
        resp = self._send_and_wait({
            "cmd": "stopTradingAccount",
            "accountKey": account_key
        })
        if resp and resp.get("success") == "OK":
            self.logger.info(f"✅ Trading account durduruldu: {account_key}")
            return True
        return False
    
    def place_order(self, account_key: str, symbol: str, action: str, quantity: float,
                   order_type: str = "Limit", limit_price: Optional[float] = None,
                   stop_price: Optional[float] = None, tif: str = "Day",
                   routing: str = "", sp_instructions: str = "") -> bool:
        """
        Emir gönder
        
        Args:
            account_key: Trading account key
            symbol: Sembol
            action: "Buy", "Sell", "Short", "Cover"
            quantity: Miktar
            order_type: "Market", "Limit", "StopMarket", "StopLimit"
            limit_price: Limit fiyatı
            stop_price: Stop fiyatı
            tif: Time in Force ("Day", "GTC", vb.)
            routing: Routing seçeneği
            sp_instructions: Özel talimatlar
        """
        leg = {
            "Symbol": symbol,
            "Action": action,
            "Quantity": quantity,
            "OrderType": order_type,
            "TIF": tif
        }
        
        if order_type in ["Limit", "StopLimit"] and limit_price:
            leg["LimitPrice"] = limit_price
        
        if order_type in ["StopMarket", "StopLimit"] and stop_price:
            leg["StopPrice"] = stop_price
        
        if routing:
            leg["Routing"] = routing
        
        if sp_instructions:
            leg["SpInstructions"] = sp_instructions
        
        cmd = {
            "cmd": "tradeCommandNew",
            "accountKey": account_key,
            "order": {
                "Legs": [leg]
            }
        }
        
        resp = self._send_and_wait(cmd, timeout=10.0)
        if resp and resp.get("success") == "OK":
            self.logger.info(f"✅ Emir gönderildi: {symbol} {action} {quantity}")
            return True
        else:
            self.logger.error(f"❌ Emir hatası: {resp.get('result') if resp else 'Yanıt yok'}")
            return False
    
    def cancel_order(self, account_key: str, order_id: str) -> bool:
        """Emri iptal et"""
        resp = self._send_and_wait({
            "cmd": "tradeCommandCancel",
            "accountKey": account_key,
            "orderID": order_id
        })
        if resp and resp.get("success") == "OK":
            self.logger.info(f"✅ Emir iptal edildi: {order_id}")
            return True
        return False
    
    def modify_order(self, account_key: str, order_id: str, **kwargs) -> bool:
        """Emri değiştir"""
        leg = {}
        if "limit_price" in kwargs:
            leg["LimitPrice"] = kwargs["limit_price"]
        if "quantity" in kwargs:
            leg["Quantity"] = kwargs["quantity"]
        
        cmd = {
            "cmd": "tradeCommandModify",
            "accountKey": account_key,
            "order": {
                "OrderID": order_id,
                "Legs": [leg]
            }
        }
        
        resp = self._send_and_wait(cmd)
        if resp and resp.get("success") == "OK":
            self.logger.info(f"✅ Emir değiştirildi: {order_id}")
            return True
        return False
    
    def get_positions(self, account_key: str, force_refresh: bool = False) -> List[Dict]:
        """Pozisyonları getir"""
        resp = self._send_and_wait({
            "cmd": "getPositions",
            "accountKey": account_key,
            "forceRefresh": force_refresh
        })
        if resp and resp.get("success") == "OK":
            result = resp.get("result", {})
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "positions" in result:
                return result["positions"]
        return []
    
    def get_balances(self, account_key: str) -> Dict:
        """Bakiyeleri getir"""
        resp = self._send_and_wait({
            "cmd": "getBalances",
            "accountKey": account_key
        })
        if resp and resp.get("success") == "OK":
            return resp.get("result", {})
        return {}
    
    def get_transactions(self, account_key: str, force_refresh: bool = False,
                        changes_only: bool = False) -> List[Dict]:
        """İşlemleri getir"""
        resp = self._send_and_wait({
            "cmd": "getTransactions",
            "accountKey": account_key,
            "forceRefresh": force_refresh,
            "changesOnly": changes_only
        })
        if resp and resp.get("success") == "OK":
            result = resp.get("result", {})
            if isinstance(result, dict) and "transactions" in result:
                return result["transactions"]
        return []
    
    # ============ PORTFOLIOS ============
    
    def enum_ports(self) -> List[Dict]:
        """Portfolio'ları listele"""
        resp = self._send_and_wait({"cmd": "enumPorts"})
        if resp and resp.get("success") == "OK":
            return resp.get("result", {}).get("ports", [])
        return []
    
    def enum_port_symbols(self, port_id: str, detailed: bool = False) -> List:
        """Portfolio'daki sembolleri listele"""
        resp = self._send_and_wait({
            "cmd": "enumPortSymbols",
            "portID": port_id,
            "detailed": detailed
        })
        if resp and resp.get("success") == "OK":
            return resp.get("result", [])
        return []
    
    def add_to_port(self, port_id: str, symbols: List[str], new: bool = False,
                    name: Optional[str] = None) -> bool:
        """Portfolio'ya sembol ekle"""
        cmd = {
            "cmd": "addToPort",
            "portID": port_id,
            "new": new,
            "sym": symbols
        }
        if new and name:
            cmd["name"] = name
        
        resp = self._send_and_wait(cmd)
        if resp and resp.get("success") == "OK":
            self.logger.info(f"✅ Portfolio güncellendi: {port_id}")
            return True
        return False
    
    # ============ ALERTS ============
    
    def subscribe_alerts(self) -> bool:
        """Alert'lere subscribe ol"""
        resp = self._send_and_wait({
            "cmd": "subscribe",
            "sub": "alerts"
        })
        if resp and resp.get("success") == "OK":
            self.logger.info("✅ Alert'lere subscribe olundu")
            return True
        return False
    
    def enum_alerts(self, alert_type: Optional[str] = None) -> List[Dict]:
        """Alert'leri listele"""
        cmd = {"cmd": "enumAlerts"}
        if alert_type:
            cmd["alertType"] = alert_type
        
        resp = self._send_and_wait(cmd)
        if resp and resp.get("success") == "OK":
            return resp.get("result", {}).get("alerts", [])
        return []
    
    def add_alert(self, symbol: str, alert_type: str, main_price: float,
                   alert_desc: Optional[str] = None) -> Optional[str]:
        """Alert ekle"""
        # Sembol formatını düzelt (PR formatı için)
        formatted_symbol = symbol
        if " PR" in symbol:
            parts = symbol.split(" PR")
            if len(parts) == 2:
                formatted_symbol = f"{parts[0]}-{parts[1]}"
        
        alert = {
            "AlertCategory": "SingleSymbol",
            "AlertType": alert_type,
            "AlertFlags": "BasedOnLAST",
            "Enabled": True,
            "internalSymbols": formatted_symbol,
            "MainPrice": main_price,
            "MainValue": main_price,
            "NotifyFlags": "PopupWindow, HighlightRow",
            "NotifyColorValue": "#90EE90"
        }
        
        if alert_desc:
            alert["Desc"] = alert_desc
        
        resp = self._send_and_wait({
            "cmd": "addAlert",
            "alert": alert
        })
        if resp and resp.get("success") == "OK":
            alert_id = resp.get("result", {}).get("alertID")
            self.logger.info(f"✅ Alert eklendi: {symbol} ({alert_type}) - ID: {alert_id}")
            return alert_id
        return None
    
    # ============ HISTORICAL DATA ============
    
    def get_candles(self, symbol: str, candle_size: str, start_date: Optional[str] = None,
                    end_date: Optional[str] = None, reg_hours_only: bool = False) -> List[Dict]:
        """OHLC candle verilerini getir"""
        cmd = {
            "cmd": "getCandles",
            "sym": symbol,
            "candleSize": candle_size,
            "regHoursOnly": reg_hours_only
        }
        if start_date:
            cmd["startDate"] = start_date
        if end_date:
            cmd["endDate"] = end_date
        
        resp = self._send_and_wait(cmd, timeout=30.0)
        if resp and resp.get("success") == "OK":
            return resp.get("result", {}).get("data", [])
        return []
    
    def get_ticks(self, symbol: str, start_date: Optional[str] = None,
                  end_date: Optional[str] = None, trades_only: bool = True,
                  reg_hours_only: bool = True, last_few: Optional[int] = None) -> List[Dict]:
        """Tick verilerini getir"""
        cmd = {
            "cmd": "getTicks",
            "sym": symbol,
            "tradesOnly": trades_only,
            "regHoursOnly": reg_hours_only
        }
        if start_date:
            cmd["startDate"] = start_date
        if end_date:
            cmd["endDate"] = end_date
        if last_few:
            cmd["lastFew"] = last_few
        
        resp = self._send_and_wait(cmd, timeout=30.0)
        if resp and resp.get("success") == "OK":
            return resp.get("result", {}).get("data", [])
        return []
    
    def get_symbol_snapshot(self, symbol: str) -> Optional[Dict]:
        """Sembol snapshot verilerini getir"""
        resp = self._send_and_wait({
            "cmd": "getSymbolSnapshot",
            "sym": symbol
        })
        if resp and resp.get("success") == "OK":
            return resp.get("result", {})
        return None
    
    def disconnect(self):
        """Bağlantıyı kapat"""
        if self.ws:
            try:
                self.ws.close()
                self.ws = None
                self.connected = False
                self.authenticated = False
                self.logger.info("🔌 Bağlantı kapatıldı")
            except Exception as e:
                self.logger.error(f"❌ Bağlantı kapatma hatası: {e}")


# ============ ÖRNEK KULLANIM ============

def main():
    """Örnek kullanım"""
    # Hammer Pro ayarları
    PORT = 16400  # Hammer Pro Settings'ten alın
    PASSWORD = "your_password_here"  # Hammer Pro login şifresi
    
    # Client oluştur
    client = HammerProClient(port=PORT, password=PASSWORD)
    
    # Callback'ler tanımla
    def on_l1_update(data):
        print(f"📊 L1 Update: {data['sym']} - Bid: {data['bid']}, Ask: {data['ask']}, Last: {data['last']}")
    
    def on_fill(tx):
        print(f"✅ Fill: {tx.get('Symbol')} - {tx.get('Action')} {tx.get('FilledQTY')} @ {tx.get('FilledPrice')}")
    
    client.on_l1_update = on_l1_update
    client.on_fill = on_fill
    
    # Bağlan
    if not client.connect():
        print("❌ Bağlantı başarısız!")
        return
    
    try:
        # Data streamer'ları listele
        streamers = client.enum_data_streamers()
        if streamers:
            streamer_id = streamers[0].get("streamerID")
            print(f"📡 Streamer seçildi: {streamer_id}")
            
            # Streamer'ı başlat
            client.start_data_streamer(streamer_id)
            time.sleep(2)  # Streamer'ın başlaması için bekle
            
            # Örnek sembollere subscribe ol
            symbols = ["AAPL", "MSFT", "TSLA"]
            client.subscribe(streamer_id, "L1", symbols)
            
            print("✅ Market data dinleniyor... (10 saniye)")
            time.sleep(10)
        
        # Trading account örneği
        accounts = client.enum_trading_accounts()
        if accounts:
            account_key = accounts[0].get("accountKey")
            print(f"💼 Account seçildi: {account_key}")
            
            # Account'ı başlat
            client.start_trading_account(account_key)
            time.sleep(2)
            
            # Pozisyonları getir
            positions = client.get_positions(account_key)
            print(f"📋 Pozisyonlar: {len(positions)} adet")
            
            # Örnek emir (YORUM SATIRI - gerçek emir göndermez)
            # client.place_order(
            #     account_key=account_key,
            #     symbol="AAPL",
            #     action="Buy",
            #     quantity=1,
            #     order_type="Limit",
            #     limit_price=150.0
            # )
        
    except KeyboardInterrupt:
        print("\n⚠️ Kullanıcı tarafından durduruldu")
    finally:
        client.disconnect()
        print("👋 Bağlantı kapatıldı")


if __name__ == "__main__":
    main()









