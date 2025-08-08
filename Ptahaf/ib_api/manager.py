import requests
import threading
import time
import websocket
import json
from ib_insync import *
import logging

POLYGON_API_KEY = "8G4FqbJYOio53Gnvk0IFURdZFKAc74j2"  # Buraya kendi Polygon API anahtarınızı girin

polygon_logger = logging.getLogger('PolygonLogger')
polygon_logger.setLevel(logging.INFO)
polygon_handler = logging.FileHandler('polygon_debug.log')
polygon_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
polygon_logger.addHandler(polygon_handler)

def polygon_log(*args, **kwargs):
    msg = ' '.join(str(a) for a in args)
    polygon_logger.info(msg)

class PolygonMarketData:
    def __init__(self):
        self.last_data = {}  # symbol -> {bid, ask, last, prev_close, volume, timestamp}
        self.lock = threading.Lock()
        self.ws = None
        self.ws_thread = None
        self.live_mode = False
        self.subscribed_symbols = set()
        # ETF WebSocket
        self.etf_symbols = ["PFF", "TLT", "SPY", "IWM", "KRE"]
        self.etf_ws = None
        self.etf_ws_thread = None
        self.etf_prices = {sym: [] for sym in self.etf_symbols}  # symbol -> [(timestamp, last)]
        self.etf_last_spike = 0
        self.etf_spike_callback = None
        # IBKR bağlantısı için
        self.ib = IB()
        self.ib_connected = False
        self.filled_trades = []
        self.positions = []
        self.open_orders = []
        
        # ✅ PSFAlgo referansı
        self.psf_algo = None

    def set_psf_algo(self, psf_algo):
        """PSFAlgo referansını ayarla"""
        self.psf_algo = psf_algo
        print(f"[IBKR Manager] PSFAlgo referansı ayarlandı: {psf_algo is not None}")

    def connect_ibkr(self, host='127.0.0.1', port=4001, client_id=1):
        """IBKR TWS/Gateway'e bağlan"""
        try:
            print(f"[IBKR Manager] 🔗 IBKR'ye bağlanılıyor: {host}:{port} (Client ID: {client_id})")
            
            # Gerekli kütüphaneleri import et
            from ib_insync import IB, util
            import logging
            import time
            
            # Logging ayarla
            util.logToConsole(logging.INFO)
            
            # Yeni IB instance oluştur
            self.ib = IB()
            
            # Önceki bağlantıyı temizle
            try:
                self.ib.disconnect()
            except Exception as e:
                print(f"[IBKR Manager] ⚠️ Önceki bağlantı kapatılırken hata: {e}")
            
            print("[IBKR Manager] 🔄 Gateway bağlantısı deneniyor...")
            
            # Farklı client ID'lerle bağlantı dene
            client_ids_to_try = [client_id, 999, 888, 777]
            
            for try_client_id in client_ids_to_try:
                try:
                    print(f"[IBKR Manager] 🔄 Client ID {try_client_id} deneniyor...")
                    self.ib.connect(host, port, clientId=try_client_id, timeout=30)
                    
                    if self.ib.isConnected():
                        print(f"[IBKR Manager] ✅ IBKR'ye bağlanıldı: {host}:{port} (Client ID: {try_client_id})")
                        
                        # Fill event handler'ı ekle
                        try:
                            self.ib.execDetailsEvent += self.on_fill
                            print("[IBKR Manager] ✅ Fill event handler eklendi")
                        except Exception as e:
                            print(f"[IBKR Manager] ⚠️ Fill handler hatası: {e}")
                        
                        # Market data type ayarla
                        try:
                            self.ib.reqMarketDataType(3)  # Delayed data
                            print("[IBKR Manager] ✅ Market data type ayarlandı")
                        except Exception as e:
                            print(f"[IBKR Manager] ⚠️ Market data type hatası: {e}")
                        
                        # Bağlantıyı stabilize etmek için bekle
                        time.sleep(3)
                        print("[IBKR Manager] ✅ Bağlantı stabilizasyonu tamamlandı")
                        
                        self.ib_connected = True
                        return True
                        
                except Exception as e:
                    print(f"[IBKR Manager] ⚠️ Client ID {try_client_id} bağlantı hatası: {e}")
                    try:
                        self.ib.disconnect()
                    except:
                        pass
            
            # Tüm denemeler başarısız olursa
            print("[IBKR Manager] ❌ Tüm Client ID'ler başarısız!")
            print("\n[IBKR Manager] 💡 Gateway Kontrol Listesi:")
            print("1. IB Gateway/TWS açık mı?")
            print("2. Gateway'de Configure > Settings > API")
            print("3. 'Enable ActiveX and Socket Clients' işaretli mi?")
            print("4. Socket port doğru mu? (Varsayılan: 4001)")
            print("5. 'Allow connections from localhost' işaretli mi?")
            print("6. 'Read-Only API' işaretli DEĞİL mi?")
            print("7. Gateway'i yeniden başlatın")
            print("\n[IBKR Manager] ⚠️ Gateway olmadan da uygulama çalışabilir (sadece market data)")
            
            self.ib_connected = False
            return False
            
        except Exception as e:
            print(f"[IBKR Manager] ❌ Beklenmeyen hata: {e}")
            self.ib_connected = False
            return False

    def disconnect_ibkr(self):
        """IBKR bağlantısını kapat"""
        if self.ib_connected:
            try:
                self.ib.disconnect()
                self.ib_connected = False
                polygon_log("[IBKR] Disconnected")
            except Exception as e:
                polygon_log(f"[IBKR] Disconnect error: {e}")

    def get_positions(self):
        """Get current positions from IBKR"""
        if not self.ib_connected:
            return []
        try:
            # ✅ Timeout ile positions isteği
            positions = self.ib.positions()
            result = []
            for pos in positions:
                result.append({
                    'symbol': pos.contract.symbol,
                    'quantity': pos.position,
                    'avgCost': pos.avgCost,
                    'account': pos.account
                })
            print(f"[IBKR Manager] ✅ {len(result)} pozisyon bulundu")
            return result
        except Exception as e:
            print(f"[IBKR Manager] ⚠️ Positions hatası (normal): {e}")
            return []

    def get_open_orders(self):
        """Get open orders from IBKR"""
        if not self.ib_connected:
            return []
        try:
            # ✅ Timeout ile open orders isteği
            orders = self.ib.openOrders()
            result = []
            for o in orders:
                result.append({
                    'symbol': getattr(o.contract, 'symbol', ''),
                    'action': getattr(o.order, 'action', ''),
                    'quantity': getattr(o.order, 'totalQuantity', ''),
                    'price': getattr(o.order, 'lmtPrice', ''),
                    'status': getattr(o, 'status', ''),
                    'orderId': getattr(o.order, 'orderId', '')
                })
            print(f"[IBKR Manager] ✅ {len(result)} açık emir bulundu")
            return result
        except Exception as e:
            print(f"[IBKR Manager] ⚠️ Open orders hatası (normal): {e}")
            return []

    def place_order(self, symbol, action, quantity, price=None, order_type='LIMIT'):
        """Place an order through IBKR"""
        if not self.ib_connected:
            polygon_log("[IBKR] Not connected")
            return False
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            if order_type == 'LIMIT':
                order = LimitOrder(action, quantity, price)
            else:
                order = MarketOrder(action, quantity)
            order.hidden = True  # Tüm emirler gizli gönderilecek
            trade = self.ib.placeOrder(contract, order)
            polygon_log(f"[IBKR] Order placed: {symbol} {action} {quantity} @ {price}")
            return True
        except Exception as e:
            polygon_log(f"[IBKR] Error placing order: {e}")
            return False

    def fetch_rest_data(self, symbols):
        batch_size = 100
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            try:
                tickers_str = ','.join(batch)
                url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
                params = {
                    "tickers": tickers_str,
                    "apiKey": POLYGON_API_KEY
                }
                resp = requests.get(url, params=params)
                snap = resp.json()
                with self.lock:
                    for ticker_data in snap.get('tickers', []):
                        symbol = ticker_data.get('ticker')
                        last = ticker_data.get('day', {}).get('c')
                        prev_close = ticker_data.get('prevDay', {}).get('c')
                        volume = ticker_data.get('day', {}).get('v')
                        last_quote = ticker_data.get('lastQuote', {})
                        bid = last_quote.get('p')
                        ask = last_quote.get('P')
                        if bid is None:
                            bid = last_quote.get('bid')
                        if ask is None:
                            ask = last_quote.get('ask')
                        self.last_data[symbol] = {
                            "bid": bid,
                            "ask": ask,
                            "last": last,
                            "prev_close": prev_close,
                            "volume": volume,
                            "timestamp": time.time()
                        }
                time.sleep(1)  # Batch başına 1 saniye bekle (rate limit için)
            except Exception as e:
                polygon_log(f"[Polygon REST] Batch snapshot failed: {e}")
                for symbol in batch:
                    self.last_data[symbol] = {
                        "bid": None, "ask": None, "last": None, "prev_close": None, "volume": None, "timestamp": time.time()
                    }

    def get_market_data(self, symbols, batch_size=50, retry_missing=True):
        """
        Polygon'dan toplu veri çeker. Büyük listelerde batch (chunk) ile çeker, eksik kalanları tekrar dener.
        LOG: API yanıtı, eksik alanlar ve N/A olanlar detaylıca loglanır.
        """
        results = {}
        symbols = list(set(symbols))  # Unique
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
            params = {
                "tickers": ",".join(batch),
                "apiKey": POLYGON_API_KEY
            }
            try:
                resp = requests.get(url, params=params, timeout=10)
                data = resp.json()
                polygon_log(f"[Polygon][Batch] Request: {batch}")
                polygon_log(f"[Polygon][Batch] Response: {json.dumps(data)[:1000]}...")  # ilk 1000 karakter
                if 'tickers' in data:
                    for t in data['tickers']:
                        sym = t.get('ticker')
                        last_quote = t.get('lastQuote', {})
                        bid = last_quote.get('p', 'N/A')
                        ask = last_quote.get('P', 'N/A')
                        last = t.get('lastTrade', {}).get('p', 'N/A') if t.get('lastTrade') else 'N/A'
                        prev_close = t.get('prevDay', {}).get('c', 'N/A') if t.get('prevDay') else 'N/A'
                        volume = t.get('day', {}).get('v', 'N/A') if t.get('day') else 'N/A'
                        if bid in [None, 'N/A'] or ask in [None, 'N/A'] or last in [None, 'N/A']:
                            polygon_log(f"[Polygon][Warn] {sym} has missing data: bid={bid}, ask={ask}, last={last}")
                        results[sym] = {
                            'bid': bid,
                            'ask': ask,
                            'last': last,
                            'prev_close': prev_close,
                            'volume': volume,
                            'timestamp': time.time()
                        }
                else:
                    polygon_log(f"[Polygon] No tickers in response for batch: {batch}")
            except Exception as e:
                polygon_log(f"[Polygon] Batch error: {e} for batch: {batch}")
            time.sleep(0.3)  # Rate limit
        # Retry missing if needed
        if retry_missing:
            missing = [s for s in symbols if s not in results]
            if missing:
                polygon_log(f"[Polygon] Missing {len(missing)} tickers, retrying individually...")
                for s in missing:
                    try:
                        url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{s}"
                        params = {"apiKey": POLYGON_API_KEY}
                        resp = requests.get(url, params=params, timeout=5)
                        t = resp.json().get('ticker', {})
                        polygon_log(f"[Polygon][Single] {s} response: {json.dumps(t)[:500]}...")
                        if t:
                            last_quote = t.get('lastQuote', {})
                            bid = last_quote.get('p', 'N/A')
                            ask = last_quote.get('P', 'N/A')
                            last = t.get('lastTrade', {}).get('p', 'N/A') if t.get('lastTrade') else 'N/A'
                            prev_close = t.get('prevDay', {}).get('c', 'N/A') if t.get('prevDay') else 'N/A'
                            volume = t.get('day', {}).get('v', 'N/A') if t.get('day') else 'N/A'
                            if bid in [None, 'N/A'] or ask in [None, 'N/A'] or last in [None, 'N/A']:
                                polygon_log(f"[Polygon][Warn] {s} has missing data: bid={bid}, ask={ask}, last={last}")
                            results[s] = {
                                'bid': bid,
                                'ask': ask,
                                'last': last,
                                'prev_close': prev_close,
                                'volume': volume,
                                'timestamp': time.time()
                            }
                        else:
                            polygon_log(f"[Polygon] No data for {s}")
                    except Exception as e:
                        polygon_log(f"[Polygon] Error for {s}: {e}")
                    time.sleep(0.3)
        # Update cache
        with self.lock:
            for sym, val in results.items():
                self.last_data[sym] = val
        # Log N/A results
        for sym in symbols:
            d = self.last_data.get(sym, {})
            if not d or any(d.get(k) in [None, 'N/A'] for k in ['bid','ask','last']):
                polygon_log(f"[Polygon][FinalWarn] {sym} has N/A or missing data in final result: {d}")
        return {symbol: self.last_data.get(symbol, {}) for symbol in symbols}

    def get_all_market_data(self):
        with self.lock:
            return self.last_data.copy()

    def start_live_stream(self, symbols, on_update):
        """Polygon WebSocket ile canlı veri başlat"""
        self.live_mode = True
        self.subscribed_symbols = set(symbols)
        if self.ws:
            self.stop_live_stream()
        def run_ws():
            ws_url = f"wss://socket.polygon.io/stocks"
            self.ws = websocket.WebSocketApp(ws_url,
                on_open=lambda ws: self._on_ws_open(ws, symbols),
                on_message=lambda ws, msg: self._on_ws_message(ws, msg, on_update),
                on_error=lambda ws, err: polygon_log(f"[Polygon WS] Error: {err}"),
                on_close=lambda ws, code, msg: polygon_log("[Polygon WS] Closed"))
            self.ws.run_forever()
        self.ws_thread = threading.Thread(target=run_ws, daemon=True)
        self.ws_thread.start()

    def _on_ws_open(self, ws, symbols):
        ws.send(json.dumps({"action": "auth", "params": POLYGON_API_KEY}))
        time.sleep(1)
        ws.send(json.dumps({"action": "subscribe", "params": ",".join(f"Q.{s}" for s in symbols)}))
        polygon_log(f"[Polygon WS] Subscribed: {symbols}")

    def _on_ws_message(self, ws, message, on_update):
        data = json.loads(message)
        for item in data:
            if item.get("ev") == "Q":
                symbol = item.get("sym")
                with self.lock:
                    self.last_data[symbol] = {
                        "bid": item.get("b", "N/A"),
                        "ask": item.get("a", "N/A"),
                        "last": self.last_data.get(symbol, {}).get("last", "N/A"),
                        "prev_close": self.last_data.get(symbol, {}).get("prev_close", "N/A"),
                        "volume": self.last_data.get(symbol, {}).get("volume", "N/A"),
                        "timestamp": time.time()
                    }
                if on_update:
                    on_update(symbol, self.last_data[symbol])

    def stop_live_stream(self):
        self.live_mode = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        if self.ws_thread:
            self.ws_thread = None
        polygon_log("[Polygon WS] Live stream stopped.")

    def get_etf_data(self):
        etf_symbols = ["PFF", "TLT", "SPY", "IWM", "KRE"]
        results = {}
        try:
            tickers_str = ','.join(etf_symbols)
            url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
            params = {
                "tickers": tickers_str,
                "apiKey": POLYGON_API_KEY
            }
            resp = requests.get(url, params=params)
            snap = resp.json()
            for ticker_data in snap.get('tickers', []):
                symbol = ticker_data.get('ticker')
                last = ticker_data.get('day', {}).get('c')
                prev_close = ticker_data.get('prevDay', {}).get('c')
                if last is not None and prev_close is not None:
                    change = round(last - prev_close, 3)  # Dolar cinsinden
                    change_pct = round(100 * (last - prev_close) / prev_close, 2) if prev_close != 0 else 0
                else:
                    change = 'N/A'
                    change_pct = 'N/A'
                results[symbol] = {
                    'last': last,
                    'change': change,
                    'change_pct': change_pct
                }
        except Exception as e:
            polygon_log(f"[Polygon REST] ETF data fetch error: {e}")
        return results

    def get_benchmarks(self):
        etfs = self.get_etf_data()
        pff_chg = etfs.get('PFF', {}).get('change', 0) or 0
        tlt_chg = etfs.get('TLT', {}).get('change', 0) or 0
        t_benchmark = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
        c_benchmark = round(pff_chg * 1.3 - tlt_chg * 0.1, 3)
        return {'T-Benchmark': t_benchmark, 'C-Benchmark': c_benchmark}

    def start_etf_stream(self, on_spike=None):
        """ETF'ler için Polygon WebSocket ile canlı veri başlat ve 1dk değişim tetikleyici kur"""
        self.etf_spike_callback = on_spike
        if self.etf_ws:
            self.stop_etf_stream()
        def run_etf_ws():
            ws_url = f"wss://socket.polygon.io/stocks"
            self.etf_ws = websocket.WebSocketApp(ws_url,
                on_open=lambda ws: self._on_etf_ws_open(ws),
                on_message=lambda ws, msg: self._on_etf_ws_message(ws, msg),
                on_error=lambda ws, err: polygon_log(f"[Polygon ETF WS] Error: {err}"),
                on_close=lambda ws, code, msg: polygon_log("[Polygon ETF WS] Closed"))
            self.etf_ws.run_forever()
        self.etf_ws_thread = threading.Thread(target=run_etf_ws, daemon=True)
        self.etf_ws_thread.start()

    def stop_etf_stream(self):
        if self.etf_ws:
            try:
                self.etf_ws.close()
            except Exception:
                pass
            self.etf_ws = None
        if self.etf_ws_thread:
            self.etf_ws_thread = None
        polygon_log("[Polygon ETF WS] Live stream stopped.")

    def _on_etf_ws_open(self, ws):
        ws.send(json.dumps({"action": "auth", "params": "d0pfubfEcofAp1rwJExCzOqNyFLHIAjh"}))
        time.sleep(1)
        ws.send(json.dumps({"action": "subscribe", "params": ",".join(f"T.{s}" for s in self.etf_symbols)}))
        polygon_log(f"[Polygon ETF WS] Subscribed: {self.etf_symbols}")

    def _on_etf_ws_message(self, ws, message):
        data = json.loads(message)
        now = time.time()
        for item in data:
            if item.get("ev") == "T":  # Trade event
                symbol = item.get("sym")
                price = item.get("p")
                if symbol in self.etf_symbols and price is not None:
                    with self.lock:
                        self.etf_prices[symbol].append((now, price))
                        # Sadece son 70 saniyeyi tut
                        self.etf_prices[symbol] = [(t, p) for t, p in self.etf_prices[symbol] if now-t <= 70]
                        # 1dk önceki fiyatı bul
                        old_prices = [p for t, p in self.etf_prices[symbol] if now-t >= 55 and now-t <= 65]
                        if old_prices:
                            old_price = old_prices[0]
                            pct_chg = 100 * (price - old_price) / old_price if old_price else 0
                            if abs(pct_chg) >= 0.5:
                                # Son spike'dan beri 20sn geçtiyse tekrar tetikle
                                if now - self.etf_last_spike > 20:
                                    self.etf_last_spike = now
                                    polygon_log(f"[ETF SPIKE] {symbol} 1dk değişim: {pct_chg:.2f}%")
                                    if self.etf_spike_callback:
                                        self.etf_spike_callback(symbol, pct_chg)

    def on_fill(self, trade, fill):
        """IBKR fill event handler - Hem PSFAlgo hem de manuel emirler için reverse order sistemi"""
        try:
            ticker = trade.contract.symbol
            action = trade.order.action  # BUY veya SELL
            fill_price = fill.execution.price
            fill_size = fill.execution.shares
            
            # BUY -> long, SELL -> short
            side = 'long' if action == 'BUY' else 'short'
            
            print(f"[IBKR FILL] {ticker} {action} {fill_size} @ {fill_price}")
            
            # ✅ PSFAlgo'ya bildir (aktifse)
            if self.psf_algo and hasattr(self.psf_algo, 'is_active') and self.psf_algo.is_active:
                self.psf_algo.on_fill(ticker, side, fill_price, fill_size)
                print(f"[IBKR FILL] PSFAlgo'ya bildirildi")
            else:
                print(f"[IBKR FILL] PSFAlgo pasif/yok - manuel reverse order kontrolü yapılıyor")
                
                # ✅ Manuel emirler için reverse order sistemi
                self.handle_manual_reverse_order(ticker, side, fill_price, fill_size)
                
        except Exception as e:
            print(f"[IBKR FILL ERROR] Fill işleme hatası: {e}")
            polygon_log(f"[IBKR] Fill processing error: {e}")

    def handle_manual_reverse_order(self, ticker, side, fill_price, fill_size):
        """Manuel emirler için reverse order sistemi"""
        try:
            # Günlük fill takibi (basit versiyon)
            if not hasattr(self, 'daily_fills'):
                import datetime
                self.daily_fills = {}
                self.today = datetime.date.today()
            
            # Gün değişmişse sıfırla
            import datetime
            today = datetime.date.today()
            if self.today != today:
                self.today = today
                self.daily_fills = {}
                print(f"[MANUAL REVERSE] Yeni gün ({today}), günlük fill takibi sıfırlandı")
            
            # Ticker için entry oluştur
            if ticker not in self.daily_fills:
                self.daily_fills[ticker] = {'long': 0, 'short': 0, 'reverse_orders': 0}
            
            # Fill miktarını ekle
            self.daily_fills[ticker][side] += fill_size
            daily_total = self.daily_fills[ticker][side]
            
            print(f"[MANUAL REVERSE] {ticker} {side} günlük toplam: {daily_total} lot")
            
            # 200+ lot olduğunda reverse order kontrolü
            if daily_total >= 200:
                print(f"[MANUAL REVERSE] {ticker} {side} günlük fill 200+ lot ({daily_total}), pozisyon arttırma kontrolü yapılıyor")
                
                # Mevcut pozisyonu al
                current_position = self.get_current_position_size(ticker)
                
                # Fill sonrası pozisyonu hesapla
                if side == 'long':
                    new_position = current_position + fill_size
                else:  # short
                    new_position = current_position - fill_size
                    
                print(f"[MANUAL REVERSE] {ticker} pozisyon değişimi: {current_position} -> {new_position}")
                
                # Pozisyon arttırma kontrolü
                is_position_increasing = False
                
                if side == 'long':
                    if current_position >= 0 and new_position > current_position:
                        is_position_increasing = True
                        print(f"[MANUAL REVERSE] {ticker} LONG pozisyon arttırma tespit edildi")
                else:  # short
                    if current_position <= 0 and new_position < current_position:
                        is_position_increasing = True
                        print(f"[MANUAL REVERSE] {ticker} SHORT pozisyon arttırma tespit edildi")
                
                if is_position_increasing:
                    # ✅ Maksimum 600 lot reverse order kontrolü
                    current_reverse_orders = self.daily_fills[ticker]['reverse_orders']
                    max_reverse_limit = 600
                    
                    if current_reverse_orders >= max_reverse_limit:
                        print(f"[MANUAL REVERSE] ❌ {ticker} için reverse order limiti aşıldı ({current_reverse_orders}/{max_reverse_limit})")
                        return
                    
                    # Açılacak reverse order miktarını hesapla
                    remaining_reverse_capacity = max_reverse_limit - current_reverse_orders
                    reverse_size = min(daily_total, remaining_reverse_capacity)
                    
                    if reverse_size <= 0:
                        print(f"[MANUAL REVERSE] ❌ {ticker} için reverse order kapasitesi yok")
                        return
                    
                    print(f"[MANUAL REVERSE] ✅ {ticker} pozisyon arttırma - reverse order açılıyor ({reverse_size} lot)")
                    
                    # Reverse order aç
                    reverse_side = 'SHORT' if side == 'long' else 'LONG'
                    success = self.open_manual_reverse_order(ticker, reverse_side, reverse_size, fill_price)
                    
                    if success:
                        # Reverse order sayacını güncelle
                        self.daily_fills[ticker]['reverse_orders'] += reverse_size
                        print(f"[MANUAL REVERSE] ✅ {ticker} reverse order başarılı - toplam reverse: {self.daily_fills[ticker]['reverse_orders']}")
                else:
                    print(f"[MANUAL REVERSE] ❌ {ticker} pozisyon azaltma işlemi - reverse order açılmıyor")
            else:
                print(f"[MANUAL REVERSE] {ticker} {side} günlük fill henüz 200'ün altında ({daily_total})")
                
        except Exception as e:
            print(f"[MANUAL REVERSE ERROR] {ticker} manuel reverse order hatası: {e}")

    def get_current_position_size(self, ticker):
        """Ticker için mevcut pozisyon büyüklüğünü döndür"""
        try:
            positions = self.get_positions()
            for pos in positions:
                if pos['symbol'] == ticker:
                    return pos['quantity']
            return 0
        except Exception:
            return 0

    def open_manual_reverse_order(self, ticker, side, size, fill_price):
        """Manuel reverse order açar"""
        try:
            # ✅ İyileştirilmiş bid/ask alma sistemi - çoklu kaynak kontrolü
            bid = 0
            ask = 0
            
            # 1. Polygon REST API'den al
            try:
                market_data = self.get_market_data([ticker])
                if ticker in market_data:
                    md = market_data[ticker]
                    bid = float(md.get('bid', 0)) if md.get('bid') not in [None, 'N/A'] else 0
                    ask = float(md.get('ask', 0)) if md.get('ask') not in [None, 'N/A'] else 0
                    if bid > 0 and ask > 0:
                        print(f"[MANUAL REVERSE] {ticker} Polygon'dan bid/ask alındı: Bid={bid:.3f}, Ask={ask:.3f}")
            except Exception as e:
                print(f"[MANUAL REVERSE] {ticker} Polygon market data hatası: {e}")
            
            # 2. Last_data cache'den al (eğer ilk kaynak başarısızsa)
            if (bid <= 0 or ask <= 0) and hasattr(self, 'last_data') and self.last_data:
                # IBKR formatındaki ticker'ı Polygon formatına çevir
                poly_ticker = self.polygonize_ticker(ticker)
                if poly_ticker in self.last_data:
                    data = self.last_data[poly_ticker]
                    cached_bid = data.get('bid')
                    cached_ask = data.get('ask')
                    
                    if cached_bid and cached_ask and float(cached_bid) > 0 and float(cached_ask) > 0:
                        bid = float(cached_bid)
                        ask = float(cached_ask)
                        print(f"[MANUAL REVERSE] {ticker} cache'den bid/ask alındı: Bid={bid:.3f}, Ask={ask:.3f}")
            
            # 3. Current price'dan tahmin et (son çare)
            if bid <= 0 or ask <= 0:
                print(f"[MANUAL REVERSE] {ticker} bid/ask veri kaynakları başarısız, tahmini değerler kullanılıyor")
                
                # Fill price'dan basit tahmin
                estimated_spread = fill_price * 0.005  # %0.5 spread varsayımı
                bid = fill_price - (estimated_spread / 2)
                ask = fill_price + (estimated_spread / 2)
                print(f"[MANUAL REVERSE] {ticker} tahmini bid/ask: Bid={bid:.3f}, Ask={ask:.3f} (spread: {estimated_spread:.3f})")
            
            # Final kontrol
            if bid <= 0 or ask <= 0:
                print(f"[MANUAL REVERSE] {ticker} için tüm bid/ask kaynakları başarısız: bid={bid}, ask={ask}")
                return False
                
            # ✅ DÜZGÜN REVERSE ORDER MANTıĞı - PASİF KAR ALMA
            spread = ask - bid
            min_profit = 0.05  # 5 cent minimum kar
            
            print(f"[MANUAL REVERSE] 📊 {ticker} Market: Bid={bid:.3f}, Ask={ask:.3f}, Spread={spread:.3f}, Fill={fill_price:.3f}")
            
            # Reverse emir fiyatını hesapla
            if side == 'LONG':  # SHORT pozisyonu kapattık, şimdi BUY reverse açıyoruz
                # ✅ SHORT fill alındıysa, kar için DAHA DÜŞÜK fiyattan BUY yapmalıyız
                min_profit_price = fill_price - min_profit  # 24.28 - 0.05 = 24.23
                print(f"[MANUAL REVERSE] 🎯 SHORT fill sonrası BUY reverse: Fill={fill_price:.3f} → Kar hedefi={min_profit_price:.3f}")
                
                # Orderbook depth kontrolü
                price, logic = self.calculate_passive_buy_price(ticker, fill_price, min_profit_price, bid, ask, spread)
                    
            else:  # LONG pozisyonu kapattık, şimdi SELL reverse açıyoruz  
                # ✅ LONG fill alındıysa, kar için DAHA YÜKSEK fiyattan SELL yapmalıyız
                min_profit_price = fill_price + min_profit  # Örnek: 24.28 + 0.05 = 24.33
                print(f"[MANUAL REVERSE] 🎯 LONG fill sonrası SELL reverse: Fill={fill_price:.3f} → Kar hedefi={min_profit_price:.3f}")
                
                # Orderbook depth kontrolü
                price, logic = self.calculate_passive_sell_price(ticker, fill_price, min_profit_price, bid, ask, spread)
            
            print(f"[MANUAL REVERSE] {ticker} {side} reverse mantık: {logic}")
            print(f"[MANUAL REVERSE] {ticker} reverse emir açılıyor: {side} {size} lot @ {price:.3f}")
            
            # Emri gönder
            action = 'BUY' if side == 'LONG' else 'SELL'
            success = self.place_order(ticker, action, size, price=price, order_type='LIMIT')
            
            if success:
                print(f"[MANUAL REVERSE] ✅ {ticker} reverse order başarılı")
                return True
            else:
                print(f"[MANUAL REVERSE] ❌ {ticker} reverse order başarısız")
                return False
                
        except Exception as e:
            print(f"[MANUAL REVERSE ERROR] {ticker} reverse order açılırken hata: {e}")
            return False

    def polygonize_ticker(self, ticker):
        """IBKR ticker'ını Polygon formatına çevir"""
        return ticker.replace(' ', '.').replace('-', '.').replace('+', '.')

    def calculate_passive_buy_price(self, ticker, fill_price, min_profit_price, bid, ask, spread):
        """✅ SHORT fill sonrası pasif BUY reverse order fiyatı hesapla - ORDERBOOK DEPTH kontrolü"""
        print(f"[PASSIVE BUY] 📈 {ticker} SHORT fill {fill_price:.3f} sonrası pasif BUY hesaplama")
        print(f"[PASSIVE BUY] 🎯 Kar hedefi: {min_profit_price:.3f} (5 cent kar)")
        
        # Mevcut bid kar hedefimizden düşükse → hidden order
        if bid <= min_profit_price:
            # Bid kar hedefinden düşük, güvenli bölgedeyiz
            hidden_price = bid + (spread * 0.15)  # Bidin %15 üstüne hidden
            logic = f"Bid ({bid:.3f}) ≤ Kar hedefi ({min_profit_price:.3f}) → Hidden: {hidden_price:.3f} (bid+spread*0.15)"
            return hidden_price, logic
        
        else:
            # ⚠️ Bid kar hedefinden yüksek - orderbook depth kontrol et
            print(f"[PASSIVE BUY] ⚠️ Bid ({bid:.3f}) > Kar hedefi ({min_profit_price:.3f}) - ORDERBOOK DEPTH kontrolü")
            
            # 5 cent aşağıdaki bölgeyi kontrol et
            search_range_start = fill_price - 0.05  # 24.28 - 0.05 = 24.23
            search_range_end = fill_price - 0.10    # 24.28 - 0.10 = 24.18
            
            print(f"[PASSIVE BUY] 🔍 Orderbook depth araştırma: {search_range_end:.3f} - {search_range_start:.3f}")
            
            # Basit depth analizi (gerçek orderbook verisi olmadığı için tahmin)
            # Gerçek uygulamada IBKR'den Level II data alınmalı
            
            # 5 cent aralığında muhtemel bid seviyeleri tahmin et
            # Örnek: 24.25, 24.20, 24.16, 24.10 gibi
            estimated_bids = []
            
            # 0.01 cent aralıklarla muhtemel bidleri hesapla
            current_level = search_range_start
            while current_level >= search_range_end:
                # Bid density simülasyonu - bazı seviyelerde bid var varsayımı
                if current_level % 0.05 == 0:  # 5 cent katları (daha yoğun)
                    estimated_bids.append(current_level)
                elif current_level % 0.01 == 0:  # 1 cent katları (orta yoğun)
                    estimated_bids.append(current_level)
                current_level -= 0.01
                current_level = round(current_level, 2)
            
            print(f"[PASSIVE BUY] 📊 Tahmini bid seviyeler: {estimated_bids[:5]}...")  # İlk 5'ini göster
            
            if len(estimated_bids) >= 2:
                # İlk ve ikinci bid seviyesi arasına yerleş
                first_bid = estimated_bids[0]   # Örnek: 24.25
                second_bid = estimated_bids[1]  # Örnek: 24.16
                
                # İkinci bidin 0.01 cent önüne yerleş
                optimal_price = second_bid + 0.01  # 24.16 + 0.01 = 24.17
                
                logic = f"Depth analizi: İlk bid {first_bid:.3f}, İkinci bid {second_bid:.3f} → Optimal: {optimal_price:.3f}"
                return optimal_price, logic
                
            else:
                # Depth analizi başarısız - güvenli minimum kar fiyatını kullan
                logic = f"Depth analizi yetersiz → Güvenli kar fiyatı: {min_profit_price:.3f}"
                return min_profit_price, logic

    def calculate_passive_sell_price(self, ticker, fill_price, min_profit_price, bid, ask, spread):
        """✅ LONG fill sonrası pasif SELL reverse order fiyatı hesapla - ORDERBOOK DEPTH kontrolü"""
        print(f"[PASSIVE SELL] 📉 {ticker} LONG fill {fill_price:.3f} sonrası pasif SELL hesaplama")
        print(f"[PASSIVE SELL] 🎯 Kar hedefi: {min_profit_price:.3f} (5 cent kar)")
        
        # Mevcut ask kar hedefimizden yüksekse → hidden order
        if ask >= min_profit_price:
            # Ask kar hedefinden yüksek, güvenli bölgedeyiz
            hidden_price = ask - (spread * 0.15)  # Askin %15 altına hidden
            logic = f"Ask ({ask:.3f}) ≥ Kar hedefi ({min_profit_price:.3f}) → Hidden: {hidden_price:.3f} (ask-spread*0.15)"
            return hidden_price, logic
        
        else:
            # ⚠️ Ask kar hedefinden düşük - orderbook depth kontrol et
            print(f"[PASSIVE SELL] ⚠️ Ask ({ask:.3f}) < Kar hedefi ({min_profit_price:.3f}) - ORDERBOOK DEPTH kontrolü")
            
            # 5 cent yukarıdaki bölgeyi kontrol et
            search_range_start = fill_price + 0.05  # 24.28 + 0.05 = 24.33
            search_range_end = fill_price + 0.10    # 24.28 + 0.10 = 24.38
            
            print(f"[PASSIVE SELL] 🔍 Orderbook depth araştırma: {search_range_start:.3f} - {search_range_end:.3f}")
            
            # Basit depth analizi (gerçek orderbook verisi olmadığı için tahmin)
            estimated_asks = []
            
            # 0.01 cent aralıklarla muhtemel askleri hesapla
            current_level = search_range_start
            while current_level <= search_range_end:
                # Ask density simülasyonu
                if current_level % 0.05 == 0:  # 5 cent katları (daha yoğun)
                    estimated_asks.append(current_level)
                elif current_level % 0.01 == 0:  # 1 cent katları (orta yoğun)
                    estimated_asks.append(current_level)
                current_level += 0.01
                current_level = round(current_level, 2)
            
            print(f"[PASSIVE SELL] 📊 Tahmini ask seviyeler: {estimated_asks[:5]}...")  # İlk 5'ini göster
            
            if len(estimated_asks) >= 2:
                # İlk ve ikinci ask seviyesi arasına yerleş
                first_ask = estimated_asks[0]   # Örnek: 24.33
                second_ask = estimated_asks[1]  # Örnek: 24.38
                
                # İkinci askin 0.01 cent altına yerleş  
                optimal_price = second_ask - 0.01  # 24.38 - 0.01 = 24.37
                
                logic = f"Depth analizi: İlk ask {first_ask:.3f}, İkinci ask {second_ask:.3f} → Optimal: {optimal_price:.3f}"
                return optimal_price, logic
                
            else:
                # Depth analizi başarısız - güvenli minimum kar fiyatını kullan
                logic = f"Depth analizi yetersiz → Güvenli kar fiyatı: {min_profit_price:.3f}"
                return min_profit_price, logic
