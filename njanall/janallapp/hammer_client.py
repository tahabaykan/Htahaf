"""
Hammer Pro API client modülü.

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janall/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Bu modül WebSocket bağlantısı yapar, CSV işlemleri yapmaz
ama diğer modüllerle entegre çalışırken bu kurala dikkat edilmeli!
=================================
"""

import websocket
import json
import logging
import time
import threading
from datetime import datetime

class HammerClient:
    def __init__(self, host='127.0.0.1', port=16400, password=None, main_window=None):
        self.host = host
        self.port = port
        self.password = password
        self.main_window = main_window  # Main window referansı
        self.url = None  # Bağlantı sırasında oluşturulacak
        self.ws = None
        self.connected = False
        self.authenticated = False
        self.market_data = {}
        self.l2_data = {}  # L2 verilerini saklamak için
        self.positions = []  # Hesap pozisyonları (ham liste)
        self.positions_map = {}  # display_symbol -> qty
        self.account_key = "ALARIC:TOPI002240A7"
        # UI entegrasyonu için callback'ler
        self.on_positions = None  # callable(list)
        self.on_fill = None       # callable(dict)
        self.benchmark_provider = None  # callable(symbol)->float
        
        # Logging ayarları
        self.logger = logging.getLogger('hammer_client')
        self.logger.setLevel(logging.WARNING)  # Debug mesajlarını kapat

        # Senkron yanıt beklemek için (getTicks/getCandles/getTransactions vb.)
        self._pending_responses = {}
        self._pending_lock = threading.Lock()
        # Harici kurallar için opsiyonel sağlayıcılar
        self.benchmark_key_provider = None  # callable(symbol)->str
        
        # Price provider
        self.get_last_price_for_symbol = None  # callable(symbol)->float
        
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
            req_id = data.get("reqID")

            # Eğer belirli bir isteğe yanıt ise bekleyenlere bırak
            if req_id:
                with self._pending_lock:
                    self._pending_responses[req_id] = data
            
            # Debug: Sadece önemli mesajları göster
            # if cmd not in ["L1Update", "L2Update"]:
            #     print(f"[HAMMER] 📥 Mesaj: {cmd}")
            
            # Mesaj tipine göre işle
            if cmd == "connect":
                if success == "OK":
                    self.authenticated = True
                    print("[HAMMER] ✅ Hammer Pro bağlantısı başarılı")
                    
                    # Bağlantı başarılı, streamer'ları başlat
                    # Tek streamer: ALARICQ (hem L1 hem L2)
                    start_cmd = {
                        "cmd": "startDataStreamer",
                        "streamerID": "ALARICQ"
                    }
                    self._send_command(start_cmd)
                    # Trading account'ı başlat ve pozisyon/işlem akışına bağlan
                    self._send_command({"cmd": "startTradingAccount", "accountKey": self.account_key})
                    # Tüm işlemleri almak için subscribe
                    self._send_command({"cmd": "subscribe", "accountKey": self.account_key, "sub": "transactions", "changes": False})
                    # Pozisyonlar için subscribe (tam liste)
                    self._send_command({"cmd": "subscribe", "accountKey": self.account_key, "sub": "positions", "changes": False})
                    # Başlangıç pozisyonlarını iste
                    self._send_command({"cmd": "getPositions", "accountKey": self.account_key})
                    
            elif cmd == "startDataStreamer":
                if success == "OK":
                    # Sessiz
                    pass
                    
            elif cmd == "startTradingAccount":
                if success == "OK":
                    # Sessiz
                    pass
                else:
                    print(f"[HAMMER] ❌ Trading account hatası: {result}")
                    
            elif cmd == "tradeCommandNew":
                if success == "OK":
                    print("[HAMMER] ✅ Emir başarıyla gönderildi!")
                else:
                    print(f"[HAMMER] ❌ Emir hatası: {result}")
                    
            elif cmd == "tradeCommandUpdate":
                # Sessiz: yalnızca hata olursa gösterilebilir
                pass
            elif cmd == "transactionsUpdate":
                # İşlem güncellemeleri - yeni fill'leri yakala
                try:
                    tx = result if isinstance(result, dict) else {}
                    account_key = tx.get('accountKey', '')
                    # Initial snapshot (set) tüm işlemleri New:true getirir; sadece change olduğunda kaydet
                    if tx.get('setOrChange') != 'change':
                        return
                    for tr in tx.get('transactions', []):
                        try:
                            status = tr.get('StatusID')
                            is_new = tr.get('New', False)
                            symbol = tr.get('Symbol')
                            filled_qty = float(tr.get('FilledQTY', 0))
                            filled_price = float(tr.get('FilledPrice', tr.get('LimitPrice', 0)))
                            filled_dt = tr.get('FilledDT', tr.get('LastTransactionDT'))
                            action = tr.get('Action', '').lower()
                            if status == 'Filled' and is_new and symbol and filled_qty > 0:
                                # PREF mapping geri çevir
                                display_symbol = symbol
                                if '-' in symbol:
                                    base, suffix = symbol.split('-')
                                    display_symbol = f"{base} PR{suffix}"
                                # jdata.csv'ye kaydet
                                try:
                                    from .myjdata import append_fill
                                    append_fill(
                                        symbol=display_symbol,
                                        side=action,
                                        qty=filled_qty,
                                        price=filled_price,
                                        fill_time=filled_dt,
                                        get_last=self.get_last_price_for_symbol,
                                        main_window=self.main_window
                                    )
                                except Exception as e:
                                    print(f"[HAMMER] ❌ Fill kaydetme hatası: {e}")
                                
                                # Benchmark değerini sağlayıcıdan al (opsiyonel)
                                bench = 0.0
                                try:
                                    if callable(self.benchmark_provider):
                                        bench = float(self.benchmark_provider(display_symbol))
                                except Exception:
                                    bench = 0.0
                                fill_payload = {
                                    'symbol': display_symbol,
                                    'direction': 'long' if action == 'buy' else 'short',
                                    'price': filled_price,
                                    'qty': filled_qty,
                                    'time': filled_dt,
                                    'benchmark_at_fill': bench
                                }
                                if callable(self.on_fill):
                                    self.on_fill(fill_payload)
                        except Exception:
                            continue
                except Exception:
                    pass
            elif cmd == "getPositions":
                try:
                    # Pozisyonları sakla ve callback'e bildir
                    # Bazı brokerlar result altında { positions: [...] } döndürebilir
                    if isinstance(result, dict) and 'positions' in result:
                        pos = result.get('positions', [])
                    else:
                        pos = result if isinstance(result, list) else []
                    self.positions = pos if isinstance(pos, list) else []
                    # Map oluştur
                    self.positions_map = {}
                    for p in self.positions:
                        try:
                            sym = p.get('Symbol') or p.get('sym')
                            qty = self._extract_position_qty(p)
                            if not sym:
                                continue
                            # display symbol
                            disp = sym
                            if '-' in sym:
                                base, suffix = sym.split('-')
                                disp = f"{base} PR{suffix}"
                            self.positions_map[disp] = qty
                        except Exception:
                            continue
                    if callable(self.on_positions):
                        self.on_positions(self.positions)
                except Exception:
                    pass

            elif cmd == "getTicks":
                # getTicks yanıtını işle - zaten _pending_responses'a kaydedildi
                print(f"[HAMMER CLIENT] 📊 getTicks yanıtı alındı: {success}")
                if success == "OK" and isinstance(result, dict):
                    data_count = len(result.get('data', []))
                    print(f"[HAMMER CLIENT] 📊 getTicks data count: {data_count}")
                else:
                    print(f"[HAMMER CLIENT] ❌ getTicks hatası: {result}")
                    
            elif cmd == "positionsUpdate":
                try:
                    pos = result if isinstance(result, list) else result.get('positions', []) if isinstance(result, dict) else []
                    if isinstance(pos, list):
                        self.positions = pos
                        # Map güncelle
                        self.positions_map = {}
                        for p in pos:
                            try:
                                sym = p.get('Symbol') or p.get('sym')
                                qty = self._extract_position_qty(p)
                                if not sym:
                                    continue
                                disp = sym
                                if '-' in sym:
                                    base, suffix = sym.split('-')
                                    disp = f"{base} PR{suffix}"
                                self.positions_map[disp] = qty
                            except Exception:
                                continue
                        if callable(self.on_positions):
                            self.on_positions(self.positions)
                except Exception:
                    pass
                    
            elif cmd == "L1Update":
                # L1 market data update
                symbol = result.get('sym')
                
                # Debug raw bid/ask values - sadece hata durumlarında göster
                raw_bid = result.get('bid')
                raw_ask = result.get('ask')
                raw_last = result.get('last')
                
                # Sadece geçersiz veri durumunda göster
                if raw_bid == 0 and raw_ask == 0:
                    pass
                
                # L1 fiyatlarını işle
                self._handle_market_data(result)

                # Last prints'leri L1Update'tan üret (size>0 olanlar trade kabul edilir)
                try:
                    trade_size = result.get('size')
                    if trade_size and float(trade_size) > 0:
                        # Sembolü display formatına çevir (AHL-F -> AHL PRF)
                        etf_list = ["SHY", "IEF", "TLT", "IWM", "KRE", "SPY", "PFF", "PGF"]
                        display_symbol = symbol
                        if symbol in etf_list:
                            display_symbol = symbol
                        elif "-" in symbol:
                            base, suffix = symbol.split("-")
                            display_symbol = f"{base} PR{suffix}"
                        
                        # Mevcut l2 kaydını al/oluştur
                        l2_entry = self.l2_data.get(display_symbol, {
                            "bids": [],
                            "asks": [],
                            "last_prints": [],
                            "timestamp": datetime.now().isoformat()
                        })
                        trade_price = result.get('price', result.get('last', 0))
                        trade_time = result.get('timeStamp', datetime.now().strftime("%H:%M:%S"))
                        # Heuristic: venue'yu mevcut L2 defterinden eşleşen fiyat ile bulmaya çalış
                        venue_guess = 'N/A'
                        try:
                            price_f = float(trade_price) if trade_price is not None else 0.0
                            # Önce asks içinde ara (trade ask'tan gerçekleşmiş olabilir)
                            for ask in l2_entry.get('asks', []):
                                if abs(float(ask.get('price', 0)) - price_f) < 1e-6:
                                    venue_guess = ask.get('venue', ask.get('MMID', 'N/A'))
                                    break
                            # Bulunamadıysa bids içinde ara
                            if venue_guess == 'N/A':
                                for bid in l2_entry.get('bids', []):
                                    if abs(float(bid.get('price', 0)) - price_f) < 1e-6:
                                        venue_guess = bid.get('venue', bid.get('MMID', 'N/A'))
                                        break
                        except Exception:
                            pass
                        l2_entry.setdefault('last_prints', [])
                        l2_entry['last_prints'].append({
                            "time": trade_time,
                            "price": float(trade_price) if trade_price is not None else 0.0,
                            "size": float(trade_size),
                            # Sadece en son trade için venue tahmini; eski kayıtlar 'N/A' kalabilir
                            "venue": venue_guess
                        })
                        # Sadece son 10
                        l2_entry['last_prints'] = l2_entry['last_prints'][-10:]
                        self.l2_data[display_symbol] = l2_entry
                except Exception:
                    pass
                
            elif cmd == "getSymbolSnapshot":
                # SNAPSHOT TAMAMEN KALDIRILDI - SADECE L1 STREAMING KULLANILIYOR!
                print(f"[HAMMER] 🚫 Snapshot mesajı kaldırıldı - Sadece L1 streaming kullanılıyor!")
                    
            elif cmd == "getQuotes":
                # Bazı kurulumlarda desteklenmiyor; L2 için subscribe/L2Update kullanılacak
                if success != "OK":
                    # Sessizce geç
                    return
                # getQuotes başarılı ise yine de işle (uyumlu kurulumlar için)
                try:
                    result = result if isinstance(result, dict) else json.loads(result)
                    self._handle_l2_data(result)
                except Exception:
                    pass
                    
            elif cmd == "L2Update":
                try:
                    # L2Update içeriği result altında gelir
                    l2_data = result if isinstance(result, dict) else {}
                    if not l2_data:
                        return
                    # Veriyi işle
                    self._handle_l2_data(l2_data)
                except Exception as e:
                    # print(f"[HATA] L2Update verisi işlenirken hata: {e}")
                    pass

            elif cmd == "getTicks":
                try:
                    # Son N tick (trade) verilerini last_prints'e yerleştir
                    res = result if isinstance(result, dict) else {}
                    symbol = res.get('sym', '')
                    if not symbol:
                        return
                    # Sembolü display formatına çevir
                    display_symbol = symbol
                    if "-" in symbol:
                        base, suffix = symbol.split("-")
                        display_symbol = f"{base} PR{suffix}"
                    
                    prints_list = []
                    for item in res.get('data', [])[-10:]:
                        try:
                            ts = item.get('t') or item.get('timeStamp')
                            price = float(item.get('p', 0)) if item.get('p') is not None else 0.0
                            size = float(item.get('s', 0)) if item.get('s') is not None else 0.0
                            if size > 0:
                                prints_list.append({
                                    'time': ts,
                                    'price': price,
                                    'size': size,
                                    'venue': 'N/A'
                                })
                        except Exception:
                            continue
                    if prints_list:
                        entry = self.l2_data.get(display_symbol, {
                            'bids': [],
                            'asks': [],
                            'last_prints': [],
                            'timestamp': datetime.now().isoformat()
                        })
                        # Append and keep last 10
                        entry['last_prints'] = (entry.get('last_prints', []) + prints_list)[-10:]
                        self.l2_data[display_symbol] = entry
                except Exception as e:
                    # print(f"[HATA] getTicks verisi işlenirken hata: {e}")
                    pass
                
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
                
            # Sembolü geri çevir (örn: AHL-F -> AHL PRF, VNO-N -> VNO PRN)
            display_symbol = symbol
            if symbol in etf_list:
                # ETF'ler için değişiklik yok
                display_symbol = symbol
            elif "-" in symbol:
                # Hammer'dan gelen "-" formatını geri çevir
                base, suffix = symbol.split("-")
                display_symbol = f"{base} PR{suffix}"
            else:
                # Diğer hisseler (SOJE, AAPL, vb.) olduğu gibi kullan
                display_symbol = symbol
                
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
                
            # Sembolü geri çevir (örn: AHL-F -> AHL PRF, VNO-N -> VNO PRN)
            display_symbol = symbol
            if "-" in symbol:
                # Hammer'dan gelen "-" formatını geri çevir
                base, suffix = symbol.split("-")
                display_symbol = f"{base} PR{suffix}"
            else:
                # Diğer hisseler (SOJE, AAPL, vb.) olduğu gibi kullan
                display_symbol = symbol
                    
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
                        # print(f"[HATA] Bid verisi parse edilemedi: {bid_data} - {e}")
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
                        # print(f"[HATA] Ask verisi parse edilemedi: {ask_data} - {e}")
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
                        # print(f"[HATA] Print verisi parse edilemedi: {print_data} - {e}")
                        continue
                
                # Yeni printleri ekle ve son 10'u tut
                if prints:
                    l2_data["last_prints"] = (prints + l2_data["last_prints"])[:10]
            
            # Timestamp güncelle
            l2_data["timestamp"] = datetime.now().isoformat()
            
            # Debug
                    # print(f"[HAMMER] 📊 L2 Data güncellendi: {display_symbol}")
        # print(f"  - Bids: {len(l2_data['bids'])} adet")
        # print(f"  - Asks: {len(l2_data['asks'])} adet")
        # print(f"  - Last Prints: {len(l2_data['last_prints'])} adet")
            
            # Veriyi sakla
            self.l2_data[display_symbol] = l2_data
            
        except Exception as e:
            # print(f"[HATA] L2 verisi işlenirken hata: {e}")
            pass
            
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
        
    def _send_and_wait(self, command, timeout: float = 8.0):
        """Komutu gönder ve aynı reqID'li yanıtı bekle (blocking)."""
        try:
            req_id = command.get('reqID') or str(time.time())
            command['reqID'] = req_id
            with self._pending_lock:
                self._pending_responses.pop(req_id, None)
            self.ws.send(json.dumps(command))
            start = time.time()
            while time.time() - start < timeout:
                with self._pending_lock:
                    if req_id in self._pending_responses:
                        return self._pending_responses.pop(req_id)
                time.sleep(0.05)
        except Exception:
            return None
        return None

    def _extract_position_qty(self, pos: dict) -> float:
        """Hammer Pro API dokümantasyonuna göre pozisyon qty'sini çıkar."""
        try:
            # Hammer Pro API dokümantasyonuna göre yaygın alanlar
            # TD Ameritrade örneği: "QTY": 1.0
            for key in ("QTY", "Quantity", "Qty", "qty", "Position", "position"):
                val = pos.get(key)
                if val is not None and val != "":
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        continue
            
            # Long/Short pozisyonlar için
            long_qty = pos.get('LongQty') or pos.get('longQty') or pos.get('LongQuantity')
            short_qty = pos.get('ShortQty') or pos.get('shortQty') or pos.get('ShortQuantity')
            
            if long_qty is not None:
                try:
                    return float(long_qty)
                except (ValueError, TypeError):
                    pass
                    
            if short_qty is not None:
                try:
                    return -float(short_qty)
                except (ValueError, TypeError):
                    pass
            
            # Net pozisyon için
            net_qty = pos.get('NetQty') or pos.get('netQty') or pos.get('NetQuantity')
            if net_qty is not None:
                try:
                    return float(net_qty)
                except (ValueError, TypeError):
                    pass
            
            # Diğer olası alanlar
            for key, val in pos.items():
                if val is None or val == "":
                    continue
                key_lower = str(key).lower()
                if any(sub in key_lower for sub in ['qty', 'quantity', 'shares', 'position']):
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        continue
                        
        except Exception as e:
            # print(f"[HAMMER] Qty extract error: {e}")
            pass
            
        return 0.0

    def _extract_position_avg_cost(self, pos: dict) -> float:
        """Hammer Pro API dokümantasyonuna göre ortalama maliyeti çıkar."""
        try:
            # Yaygın alan adları
            for key in ('Paid', 'paid', 'AvgPrice', 'avg', 'averagePrice', 'AvgCost', 'AverageCost', 'Basis', 'BasisPrice'):
                val = pos.get(key)
                if val is not None and val != "":
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        continue
                        
        except Exception:
            pass
            
        return 0.0

    # Dışarıya pozisyonları doğrudan döndüren yardımcı
    def get_positions_direct(self):
        """Hammer Pro'dan pozisyonları doğrudan çek (blocking) ve normalize et."""
        try:
            # print(f"[HAMMER] 🔍 Pozisyonlar getiriliyor... Account: {self.account_key}")
            
            # Önce mevcut positions_map'i kontrol et
            if hasattr(self, 'positions_map') and self.positions_map:
                # print(f"[HAMMER] 📋 Mevcut positions_map'ten {len(self.positions_map)} pozisyon bulundu")
                out = []
                for display, qty in self.positions_map.items():
                    # Avg cost'u positions'dan bul
                    avg_cost = 0.0
                    for pos in getattr(self, 'positions', []):
                        sym = pos.get('Symbol') or pos.get('sym')
                        if sym and '-' in sym:
                            base, suffix = sym.split('-')
                            pos_display = f"{base} PR{suffix}"
                            if pos_display == display:
                                avg_cost = self._extract_position_avg_cost(pos)
                                break
                    
                    out.append({
                        'symbol': display,
                        'qty': float(qty),
                        'avg_cost': avg_cost
                    })
                return out
            
            # Eğer positions_map yoksa, getPositions komutunu dene
            resp = self._send_and_wait({
                "cmd": "getPositions",
                "accountKey": self.account_key,
                "forceRefresh": True
            }, timeout=10.0)
            
            if not resp or resp.get('success') != 'OK':
                # print(f"[HAMMER] ❌ getPositions başarısız: {resp}")
                return []
                
            # print(f"[HAMMER] ✅ getPositions yanıtı alındı")
            
            res = resp.get('result')
            if isinstance(res, dict) and 'positions' in res:
                items = res.get('positions', [])
            else:
                items = res if isinstance(res, list) else []
                
            # print(f"[HAMMER] 📊 {len(items)} pozisyon bulundu")
            
            out = []
            for i, p in enumerate(items):
                try:
                    # print(f"[HAMMER] 🔍 Pozisyon {i+1}: {p}")
                    
                    sym = p.get('Symbol') or p.get('sym')
                    if not sym:
                        # print(f"[HAMMER] ⚠️ Sembol bulunamadı: {p}")
                        continue
                        
                    display = sym
                    if '-' in sym:
                        b, s = sym.split('-')
                        display = f"{b} PR{s}"
                        
                    qty = self._extract_position_qty(p)
                    avg_cost = self._extract_position_avg_cost(p)
                    
                    # print(f"[HAMMER] 📋 {display}: Qty={qty}, AvgCost={avg_cost}")
                    
                    # Last price veya prev close bilgisini al
                    last_price = p.get('LastPrice') or p.get('lastPrice') or p.get('last_price')
                    prev_close = p.get('PrevClose') or p.get('prevClose') or p.get('prev_close')
                    
                    # Last price yoksa prev close kullan
                    price_for_exposure = last_price if last_price else prev_close
                    
                    out.append({
                        'symbol': display,
                        'qty': float(qty),
                        'avg_cost': avg_cost,
                        'last_price': last_price,
                        'prev_close': prev_close,
                        'price_for_exposure': price_for_exposure,
                        'raw_data': p  # Debug için ham veri
                    })
                except Exception as e:
                    print(f"[HAMMER] ❌ Pozisyon parse hatası: {e}")
                    continue
                    
            return out
            
        except Exception as e:
            print(f"[HAMMER] ❌ get_positions_direct hatası: {e}")
            return []
        
    def _send_command(self, command):
        """WebSocket'e komut gönder"""
        try:
            self.ws.send(json.dumps(command))
            return True
        except Exception as e:
            self.logger.error(f"Error sending command: {e}")
            return False
            
    def get_symbol_snapshot(self, symbol):
        """Bir sembol için snapshot verilerini al - TAMAMEN KALDIRILDI!"""
        # SNAPSHOT TAMAMEN KALDIRILDI - SADECE L1 STREAMING KULLANILIYOR!
        print(f"[HAMMER] 🚫 Snapshot kaldırıldı: {symbol} - Sadece L1 streaming kullanılıyor!")
        return False

    def subscribe_symbol(self, symbol, include_l2=False):
        """Bir sembole subscribe ol - ETF'ler için L1 streaming, preferred stocks için L1+L2"""
        if not self.connected or not self.authenticated:
            return False
            
        # ETF listesi - bunlar için L1 streaming kullanılacak
        etf_list = ["SPY", "TLT", "IEF", "IEI", "PFF", "KRE", "IWM", "SHY", "PGF"]
        
        # Sembolü formatla
        formatted_symbol = symbol
        if symbol in etf_list:
            # ETF'ler için format değişikliği yok
            formatted_symbol = symbol
            
            # ETF'ler için L1 streaming kullan
            l1_cmd = {
                "cmd": "subscribe",
                "sub": "L1",
                "streamerID": "ALARICQ",
                "sym": [formatted_symbol],
                "transient": False  # Veriyi database'e kaydet
            }
            return self._send_command(l1_cmd)
            
        elif " PR" in symbol:
            # Preferred stocks: "CIM PRB" -> "CIM-B", "ACR PRC" -> "ACR-C", "EQH PRA" -> "EQH-A"
            # PR bulunan hisselerde dönüşüm yap
            parts = symbol.split(" PR")
            if len(parts) == 2:
                base_symbol = parts[0]
                suffix = parts[1]
                formatted_symbol = f"{base_symbol}-{suffix}"
            
            # Sessiz
            
            # Preferred stocks için L1 streaming
            l1_cmd = {
                "cmd": "subscribe",
                "sub": "L1",
                "streamerID": "ALARICQ",
                "sym": [formatted_symbol],
                "transient": False  # Veriyi database'e kaydet
            }
            self._send_command(l1_cmd)

            # OrderBook için L2 gerekiyorsa ek olarak L2'ye de abone ol
            if include_l2:
                l2_cmd = {
                    "cmd": "subscribe",
                    "sub": "L2",
                    "streamerID": "ALARICQ",
                    "sym": [formatted_symbol],
                    "changes": False,
                    "maxRows": 7
                }
                self._send_command(l2_cmd)

            return True
        else:
            # Diğer tüm hisseler (SOJE, AAPL, vb.) olduğu gibi kullan
            formatted_symbol = symbol
            
            # Sessiz
            
            # TÜM HİSSELER İÇİN L1 SUBSCRIBE!
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
                # L2 verisi için aynı streamerID: ALARICQ
                l2_cmd = {
                    "cmd": "subscribe",
                    "sub": "L2",
                    "streamerID": "ALARICQ",
                    "sym": [formatted_symbol],
                    "changes": False,  # Her seferinde tüm veriyi al
                    "maxRows": 7
                }
                self._send_command(l2_cmd)
                time.sleep(0.2)
                
            return True
        
    def get_market_data(self, symbol):
        """Bir sembol için market data al"""
        # Symbol mapping yap - subscribe_symbol ile aynı mantık
        formatted_symbol = symbol
        if " PR" in symbol:
            # PR bulunan hisselerde dönüşüm yap (örn: "CIM PRB" -> "CIM-B")
            parts = symbol.split(" PR")
            if len(parts) == 2:
                base_symbol = parts[0]
                suffix = parts[1]
                formatted_symbol = f"{base_symbol}-{suffix}"
        
        # Önce formatted symbol ile ara
        if formatted_symbol in self.market_data:
            return self.market_data.get(formatted_symbol, {})
        
        # Bulamazsa orijinal symbol ile ara
        return self.market_data.get(symbol, {})
    
    def guess_venue_from_symbol(self, symbol):
        """Symbol'den venue tahmin et"""
        try:
            symbol_upper = symbol.upper()
            
            # Yaygın venue mapping'leri
            venue_mapping = {
                # NASDAQ
                'NASDAQ': ['NASDAQ', 'NDAQ', 'NDX'],
                # NYSE
                'NYSE': ['NYSE', 'NYX'],
                # AMEX
                'AMEX': ['AMEX', 'AMX'],
                # OTC
                'OTC': ['OTC', 'OTCBB', 'PINK'],
                # BATS
                'BATS': ['BATS', 'BZX', 'BYX'],
                # IEX
                'IEX': ['IEX'],
                # ARCA
                'ARCA': ['ARCA', 'ARCAEX']
            }
            
            # Symbol'de venue ipucu ara
            for venue, keywords in venue_mapping.items():
                for keyword in keywords:
                    if keyword in symbol_upper:
                        return venue
            
            # Symbol uzunluğuna göre tahmin
            if len(symbol) <= 4:
                return 'NASDAQ'  # Kısa symbol'ler genelde NASDAQ
            elif len(symbol) > 4:
                return 'NYSE'    # Uzun symbol'ler genelde NYSE
            
            return 'UNKNOWN'
            
        except Exception as e:
            print(f"[HAMMER CLIENT] ❌ Venue tahmin hatası: {e}")
            return 'UNKNOWN'
    
    def extract_venue_from_tick(self, tick, symbol=None):
        """Tick'ten venue bilgisini çıkar - Geliştirilmiş mapping"""
        try:
            # Venue field'larını öncelik sırasına göre dene
            venue_fields = [
                'e',            # Exchange (Support takımının örneğinde bu var!)
                'ex',           # Exchange
                'exchange',     # Exchange (full name)
                'venue',        # Venue
                'mkt',          # Market
                'market',       # Market (full name)
                'src',          # Source
                'source',       # Source (full name)
                'inst',         # Instrument
                'instrument',   # Instrument (full name)
                'dest',         # Destination
                'destination',  # Destination (full name)
                'route',        # Route
                'routing'       # Routing
            ]
            
            for field in venue_fields:
                value = tick.get(field)
                if value and str(value).strip() and str(value).upper() != 'NONE':
                    return str(value).strip()
            
            # Eğer tick'te venue bilgisi yoksa ve symbol verilmişse, symbol'den tahmin et
            if symbol:
                guessed_venue = self.guess_venue_from_symbol(symbol)
                if guessed_venue != 'UNKNOWN':
                    print(f"[HAMMER CLIENT] 🔍 Venue tahmin edildi: {symbol} -> {guessed_venue}")
                    return guessed_venue
            
            return 'UNKNOWN'
            
        except Exception as e:
            print(f"[HAMMER CLIENT] ❌ Venue extraction hatası: {e}")
            return 'UNKNOWN'
    
    def enum_data_streamers(self):
        """Mevcut data streamer'ları listele"""
        try:
            command = {
                "cmd": "enumDataStreamers",
                "reqID": f"streamers_{int(time.time())}"  # reqID ekle
            }
            
            print(f"[HAMMER CLIENT] 🔍 enumDataStreamers komutu gönderiliyor...")
            
            response = self.send_command_and_wait(command)
            
            if response and response.get('success') == 'OK':
                streamers = response.get('result', [])
                print(f"[HAMMER CLIENT] ✅ Data streamer'lar bulundu: {len(streamers)} adet")
                print(f"[HAMMER CLIENT] 🔍 Streamer response detayı: {response}")
                for i, streamer in enumerate(streamers):
                    print(f"[HAMMER CLIENT] 📋 Streamer {i+1}: {streamer} (type: {type(streamer).__name__})")
                return streamers
            else:
                print(f"[HAMMER CLIENT] ❌ enumDataStreamers hatası: {response}")
                return []
                
        except Exception as e:
            print(f"[HAMMER CLIENT] ❌ enumDataStreamers exception: {e}")
            return []
    
    def get_ticks_with_venue(self, symbol, lastFew=25, tradesOnly=True, regHoursOnly=True):
        """Venue bilgisi ile tick data al - backfillFirst ile"""
        try:
            # Symbol mapping yap
            formatted_symbol = symbol
            if " PR" in symbol:
                parts = symbol.split(" PR")
                if len(parts) == 2:
                    base_symbol = parts[0]
                    suffix = parts[1]
                    formatted_symbol = f"{base_symbol}-{suffix}"
            
            # Önce streamer'ları al
            streamers = self.enum_data_streamers()
            if not streamers:
                print(f"[HAMMER CLIENT] ⚠️ Streamer bulunamadı, normal getTicks kullanılıyor")
                return self.get_ticks(symbol, lastFew, tradesOnly, regHoursOnly)
            
            # İlk streamer'ı kullan
            streamer_id = streamers[0] if isinstance(streamers, list) else streamers
            print(f"[HAMMER CLIENT] 🔍 Kullanılan streamer: {streamer_id}")
            
            # backfillFirst ile getTicks komutu gönder - Dokümantasyondaki gibi
            command = {
                "cmd": "getTicks",
                "reqID": f"venue_{int(time.time())}",  # reqID ekle
                "sym": formatted_symbol,
                "lastFew": lastFew,
                "tradesOnly": False,  # tradesOnly: false (venue bilgisi için)
                "regHoursOnly": regHoursOnly,
                "backfillFirst": streamer_id,
                "type": "tick",  # Tick data için
                "backfillType": "incremental"
            }
            
            print(f"[HAMMER CLIENT] 🔍 getTicks with venue komutu gönderiliyor: {formatted_symbol}")
            print(f"[HAMMER CLIENT] 📋 Venue parametreleri: backfillFirst={streamer_id}, type=tick")
            
            # Komutu gönder ve yanıtı bekle
            response = self.send_command_and_wait(command)
            
            if response and response.get('success') == 'OK':
                result = response.get('result', {})
                tick_count = len(result.get('data', []))
                print(f"[HAMMER CLIENT] ✅ getTicks with venue başarılı: {formatted_symbol} - {tick_count} tick alındı")
                
                # Debug: Venue tick'lerinin detaylı analizi
                if result.get('data') and len(result['data']) > 0:
                    print(f"[HAMMER CLIENT] 🔍 Venue getTicks - Toplam {len(result['data'])} tick alındı")
                    
                    # İlk 3 tick'in detaylı analizi
                    for i, tick in enumerate(result['data'][:3]):
                        print(f"[HAMMER CLIENT] 🔍 Venue Tick {i+1} - Tüm field'lar:")
                        for key, value in tick.items():
                            print(f"[HAMMER CLIENT] 🔍   {key}: {value} (type: {type(value).__name__})")
                        print(f"[HAMMER CLIENT] 🔍   ---")
                    
                    # Venue field'larını özel olarak kontrol et
                    print(f"[HAMMER CLIENT] 🔍 Venue field analizi (backfillFirst):")
                    venue_fields = ['e', 'ex', 'exchange', 'venue', 'mkt', 'market', 'src', 'source', 'inst', 'instrument', 'dest', 'destination', 'route', 'routing']
                    for field in venue_fields:
                        values = []
                        for tick in result['data'][:5]:  # İlk 5 tick'i kontrol et
                            value = tick.get(field)
                            if value is not None:
                                values.append(str(value))
                        if values:
                            print(f"[HAMMER CLIENT] 🔍   {field}: {values}")
                        else:
                            print(f"[HAMMER CLIENT] 🔍   {field}: YOK")
                
                return result
            else:
                print(f"[HAMMER CLIENT] ❌ getTicks with venue hatası: {response}")
                return None
                
        except Exception as e:
            print(f"[HAMMER CLIENT] ❌ getTicks with venue exception: {e}")
            return None
    
    def get_ticks(self, symbol, lastFew=25, tradesOnly=True, regHoursOnly=True):
        """Bir sembol için tick data al (venue bilgisi için) - İyileştirilmiş versiyon"""
        try:
            # Symbol mapping yap
            formatted_symbol = symbol
            if " PR" in symbol:
                parts = symbol.split(" PR")
                if len(parts) == 2:
                    base_symbol = parts[0]
                    suffix = parts[1]
                    formatted_symbol = f"{base_symbol}-{suffix}"
            
            # getTicks komutu gönder - Support takımının TAM komutu (lastFew yok!)
            command = {
                "cmd": "getTicks",
                "reqID": "1234",  # Support takımının kullandığı reqID
                "sym": formatted_symbol,
                "tradesOnly": False,  # tradesOnly: false (venue bilgisi için)
                "regHoursOnly": True   # Support takımının kullandığı regHoursOnly: true
            }
            
            print(f"[HAMMER CLIENT] 🔍 getTicks komutu gönderiliyor: {formatted_symbol}")
            print(f"[HAMMER CLIENT] 📋 Parametreler: reqID={command['reqID']}, tradesOnly=False, regHoursOnly=True (Support takımının TAM komutu)")
            
            # Komutu gönder ve yanıtı bekle
            response = self.send_command_and_wait(command)
            
            if response and response.get('success') == 'OK':
                result = response.get('result', {})
                tick_count = len(result.get('data', []))
                print(f"[HAMMER CLIENT] ✅ getTicks başarılı: {formatted_symbol} - {tick_count} tick alındı")
                
                # Debug: Tüm tick'lerin detaylı field'larını göster
                if result.get('data') and len(result['data']) > 0:
                    print(f"[HAMMER CLIENT] 🔍 Toplam {len(result['data'])} tick alındı")
                    
                    # İlk 3 tick'in detaylı analizi
                    for i, tick in enumerate(result['data'][:3]):
                        print(f"[HAMMER CLIENT] 🔍 Tick {i+1} - Tüm field'lar:")
                        for key, value in tick.items():
                            print(f"[HAMMER CLIENT] 🔍   {key}: {value} (type: {type(value).__name__})")
                        print(f"[HAMMER CLIENT] 🔍   ---")
                    
                    # Venue field'larını özel olarak kontrol et
                    print(f"[HAMMER CLIENT] 🔍 Venue field analizi:")
                    venue_fields = ['e', 'ex', 'exchange', 'venue', 'mkt', 'market', 'src', 'source', 'inst', 'instrument', 'dest', 'destination', 'route', 'routing']
                    for field in venue_fields:
                        values = []
                        for tick in result['data'][:5]:  # İlk 5 tick'i kontrol et
                            value = tick.get(field)
                            if value is not None:
                                values.append(str(value))
                        if values:
                            print(f"[HAMMER CLIENT] 🔍   {field}: {values}")
                        else:
                            print(f"[HAMMER CLIENT] 🔍   {field}: YOK")
                
                return result
            else:
                print(f"[HAMMER CLIENT] ❌ getTicks hatası: {response}")
                return None
                
        except Exception as e:
            print(f"[HAMMER CLIENT] ❌ getTicks exception: {e}")
            return None
    
    def send_command(self, command):
        """Hammer Pro API'ye komut gönder"""
        try:
            import json
            
            # JSON formatında komutu gönder
            command_json = json.dumps(command)
            print(f"[HAMMER CLIENT] 📤 Komut gönderiliyor: {command_json}")
            
            # WebSocket'e gönder
            if self.ws and self.ws.sock:
                self.ws.send(command_json)
                print(f"[HAMMER CLIENT] ✅ Komut gönderildi: {command['cmd']}")
            else:
                print(f"[HAMMER CLIENT] ❌ WebSocket bağlı değil")
                
        except Exception as e:
            print(f"[HAMMER CLIENT] ❌ send_command exception: {e}")
    
    def send_command_and_wait(self, command, timeout=5):
        """Komut gönder ve yanıtı bekle"""
        try:
            import time
            import uuid
            
            # Unique request ID ekle
            req_id = str(uuid.uuid4())
            command['reqID'] = req_id
            
            # Pending response'u kaydet
            with self._pending_lock:
                self._pending_responses[req_id] = None
            
            # Komutu gönder
            self.send_command(command)
            
            # Yanıtı bekle
            start_time = time.time()
            while time.time() - start_time < timeout:
                with self._pending_lock:
                    if req_id in self._pending_responses and self._pending_responses[req_id] is not None:
                        response = self._pending_responses[req_id]
                        del self._pending_responses[req_id]
                        print(f"[HAMMER CLIENT] ✅ Yanıt alındı: {response.get('cmd')}")
                        return response
                time.sleep(0.1)
            
            # Timeout - pending response'u temizle
            with self._pending_lock:
                if req_id in self._pending_responses:
                    del self._pending_responses[req_id]
            
            print(f"[HAMMER CLIENT] ⚠️ getTicks timeout: {command['sym']}")
            return None
            
        except Exception as e:
            print(f"[HAMMER CLIENT] ❌ send_command_and_wait exception: {e}")
            return None
        
    def get_l2_data(self, symbol):
        """Bir sembol için L2 verilerini döndür (subscribe sonrası cache'den)."""
        try:
            return self.l2_data.get(symbol, {})
        except Exception:
            return {}
        
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
    
    def place_order(self, symbol, side, quantity, price, order_type="LIMIT", hidden=True, account_key="ALARIC:TOPI002240A7"):
        """Hammer Pro'ya emir gönder"""
        if not self.connected or not self.authenticated:
            print("[HAMMER] ❌ Bağlantı yok, emir gönderilemez!")
            return False
        
        try:
            # Symbol mapping yap
            formatted_symbol = symbol
            if " PR" in symbol:
                formatted_symbol = symbol.replace(" PR", "-")
            
            # First start trading account if not already started
            if not hasattr(self, 'trading_account_started'):
                start_account_cmd = {
                    "cmd": "startTradingAccount",
                    "accountKey": account_key
                }
                # Sessiz
                self._send_command(start_account_cmd)
                self.trading_account_started = True
                time.sleep(0.5)  # Wait for account to start
            
            # Emir mesajını oluştur - Doğru format
            order_message = {
                "cmd": "tradeCommandNew",
                "accountKey": account_key,
                "order": {
                    "Legs": [{
                        "Symbol": formatted_symbol,
                        "Action": side.capitalize(),
                        "Quantity": quantity,
                        "OrderType": order_type.capitalize(),
                        "LimitPrice": price,
                        "SpInstructions": "Hidden"  # Tüm emirler default olarak hidden
                    }]
                }
            }
            
            # Emri gönder
            self._send_command(order_message)
            # Emir gönderildi (sessiz)
            return True
            
        except Exception as e:
            print(f"[HAMMER] ❌ Emir gönderme hatası: {e}")
            return False

    # --- Geriye dönük fill tespiti ve jdata.csv tohumlama ---
    def backfill_recent_fills(self, account_key: str, minutes_ago: int = 120, on_fill_callback=None):
        """İnternet kesintisi sırasında kaçan fill'leri yakalamak için, son N dakikadaki
        transactions listesini çekip yeni fill'leri jdata.csv'ye işaretlemek.
        Not: Hammer Pro transactionsUpdate'ta değişenleri verir; burada doğrudan getTransactions kullanırız.
        """
        try:
            # Tüm işlemleri getir (changesOnly=false)
            resp = self._send_and_wait({
                "cmd": "getTransactions",
                "accountKey": account_key,
                "changesOnly": False
            }, timeout=10.0)
            if not resp or resp.get('success') != 'OK':
                return 0
            result = resp.get('result', {})
            txs = result.get('transactions', []) if isinstance(result, dict) else []
            cutoff_ts = time.time() - minutes_ago * 60
            added = 0
            for tr in txs:
                try:
                    if tr.get('StatusID') != 'Filled':
                        continue
                    filled_dt = tr.get('FilledDT') or tr.get('LastTransactionDT')
                    # ISO time to epoch
                    filled_epoch = cutoff_ts
                    try:
                        from datetime import datetime
                        filled_epoch = datetime.fromisoformat(str(filled_dt).replace('Z','')).timestamp()
                    except Exception:
                        pass
                    if filled_epoch < cutoff_ts:
                        # eski ama yine de işleyebiliriz
                        pass
                    symbol = tr.get('Symbol')
                    display_symbol = symbol
                    if symbol and '-' in symbol:
                        base, suffix = symbol.split('-')
                        display_symbol = f"{base} PR{suffix}"
                    qty = float(tr.get('FilledQTY', 0) or tr.get('QTY', 0) or 0)
                    price = float(tr.get('FilledPrice', tr.get('LimitPrice', 0)) or 0)
                    side = tr.get('Action', 'Buy').lower()
                    # Kullanıcı sağlayıcısı ile benchmark key belirle
                    bench_key = 'DEFAULT'
                    try:
                        if callable(self.benchmark_key_provider):
                            bench_key = self.benchmark_key_provider(display_symbol) or 'DEFAULT'
                    except Exception:
                        bench_key = 'DEFAULT'
                    # Dışarıya bildir ki jdata.csv'ye yazsın
                    payload = {
                        'symbol': display_symbol,
                        'direction': 'long' if side == 'buy' else 'short',
                        'qty': qty,
                        'price': price,
                        'time': str(filled_dt),
                        'benchmark_key': bench_key
                    }
                    if callable(on_fill_callback):
                        on_fill_callback(payload)
                        added += 1
                except Exception:
                    continue
            return added
        except Exception:
            return 0

    # --- Emir yönetimi metodları ---
    def get_trading_accounts(self):
        """Mevcut trading account'ları getir"""
        try:
            # Varsayılan account key'i kullan
            return [{'accountKey': self.account_key}]
        except Exception as e:
            print(f"[HAMMER] ❌ get_trading_accounts hatası: {e}")
            return []
    
    def enum_trading_accounts(self):
        """Hammer Pro'dan trading account'ları listele"""
        try:
            print(f"[HAMMER] 🔄 Trading accounts listeleniyor...")
            
            # enumTradingAccounts komutunu gönder
            resp = self._send_and_wait({
                "cmd": "enumTradingAccounts"
            })
            
            if resp and resp.get('success') == 'OK':
                return resp.get('result', {})
            else:
                print(f"[HAMMER] ❌ Trading accounts listeleme hatası: {resp.get('result', 'Bilinmeyen hata')}")
                return {}
        except Exception as e:
            print(f"[HAMMER] ❌ enum_trading_accounts hatası: {e}")
            return {}
    
    def start_trading_account(self, account_key):
        """Trading account'ı başlat"""
        try:
            print(f"[HAMMER] 🔄 Trading account başlatılıyor... Account: {account_key}")
            
            # startTradingAccount komutunu gönder
            resp = self._send_and_wait({
                "cmd": "startTradingAccount",
                "accountKey": account_key
            })
            
            if resp and resp.get('success') == 'OK':
                print(f"[HAMMER] ✅ Trading account başlatıldı: {account_key}")
                return True
            else:
                print(f"[HAMMER] ❌ Trading account başlatma hatası: {resp.get('result', 'Bilinmeyen hata')}")
                return False
        except Exception as e:
            print(f"[HAMMER] ❌ start_trading_account hatası: {e}")
            return False
    
    def get_transactions(self, account_key, forceRefresh=False, changesOnly=False):
        """Hesaptan işlemleri/emirleri getir"""
        try:
            print(f"[HAMMER] 🔄 İşlemler getiriliyor... Account: {account_key}")
            
            # getTransactions komutunu gönder
            resp = self._send_and_wait({
                "cmd": "getTransactions",
                "accountKey": account_key,
                "forceRefresh": forceRefresh,
                "changesOnly": changesOnly
            })
            
            if resp and resp.get('success') == 'OK':
                return resp.get('result', {})
            else:
                print(f"[HAMMER] ❌ İşlem getirme hatası: {resp.get('result', 'Bilinmeyen hata')}")
                return {}
        except Exception as e:
            print(f"[HAMMER] ❌ get_transactions hatası: {e}")
            return {}
    
    def get_orders(self):
        """Hammer Pro'dan emirleri al (getTransactions kullanarak)"""
        try:
            if not self.connected or not self.authenticated:
                print("[HAMMER] ❌ Bağlantı yok, emirler alınamaz!")
                return []
            
            # getTransactions komutu ile tüm işlemleri al
            resp = self._send_and_wait({
                "cmd": "getTransactions",
                "accountKey": "ALARIC:TOPI002240A7",  # Varsayılan hesap
                "forceRefresh": True  # En güncel verileri al
            })
            
            if resp and resp.get('success') == 'OK':
                result = resp.get('result', {})
                transactions = result.get('transactions', [])
                
                # Sadece açık emirleri (IsOpen=true) filtrele
                orders = []
                for tx in transactions:
                    if tx.get('IsOpen', False):  # Sadece açık emirler
                        order = {
                            'order_id': tx.get('OrderID', 'N/A'),
                            'symbol': tx.get('Symbol', 'N/A'),
                            'action': tx.get('Action', 'N/A'),
                            'qty': tx.get('QTY', 0),
                            'filled_qty': tx.get('FilledQTY', 0),
                            'remaining_qty': tx.get('RemainingQTY', tx.get('QTY', 0)),
                            'order_type': tx.get('OrderType', 'N/A'),
                            'limit_price': tx.get('LimitPrice', 0),
                            'stop_price': tx.get('StopPrice', 0),
                            'status': tx.get('StatusID', 'N/A'),
                            'order_time': tx.get('OrderDT', 'N/A'),
                            'avg_price': tx.get('FilledPrice', 0),
                            'fill_time': tx.get('FilledDT', 'N/A')
                        }
                        orders.append(order)
                
                print(f"[HAMMER] ✅ {len(orders)} emir alındı")
                return orders
            else:
                print(f"[HAMMER] ❌ Emirleri alma hatası: {resp.get('result', 'Bilinmeyen hata')}")
                return []
                
        except Exception as e:
            print(f"[HAMMER] ❌ get_orders hatası: {e}")
            return []
    
    def trade_command_cancel(self, account_key, order_id):
        """Emri iptal et"""
        try:
            print(f"[HAMMER] 🔄 Emir iptal ediliyor... Order ID: {order_id}")
            
            # tradeCommandCancel komutunu gönder
            resp = self._send_and_wait({
                "cmd": "tradeCommandCancel",
                "accountKey": account_key,
                "orderID": order_id
            })
            
            if resp and resp.get('success') == 'OK':
                print(f"[HAMMER] ✅ Emir iptal edildi: {order_id}")
                return True
            else:
                print(f"[HAMMER] ❌ Emir iptal hatası ({order_id}): {resp.get('result', 'Bilinmeyen hata')}")
                return False
        except Exception as e:
            print(f"[HAMMER] ❌ trade_command_cancel hatası ({order_id}): {e}")
            return False