import tkinter as tk
from tkinter import ttk
import pandas as pd
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
                    
                    # Bağlantı başarılı, streamer'ı başlat
                    start_cmd = {
                        "cmd": "startDataStreamer",
                        "streamerID": "ALARICQ"
                    }
                    self._send_command(start_cmd)
                    
            elif cmd == "startDataStreamer":
                if success == "OK":
                    print("[HAMMER] ✅ Data streamer başlatıldı")
                    
            elif cmd == "L1Update":
                # L1 market data update
                print(f"[HAMMER] 📊 L1 Update: {result.get('sym')}")
                self._handle_market_data(result)
                
            elif cmd == "getSymbolSnapshot":
                if success == "OK":
                    print(f"[HAMMER] 📸 Snapshot: {result.get('sym')}")
                    self._handle_market_data(result)
                
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
                
            # Sembolü geri çevir (örn: AHL-E -> AHL PRE)
            display_symbol = symbol
            if "-" in symbol:
                base, suffix = symbol.split("-")
                if len(suffix) == 1:  # Tek harf suffix
                    display_symbol = f"{base} PR{suffix}"
                
            # Market data'yı parse et
            market_data = {
                "price": float(data.get("price", 0)) if data.get("price") else 0,
                "bid": float(data.get("bid", 0)) if data.get("bid") else 0,
                "ask": float(data.get("ask", 0)) if data.get("ask") else 0,
                "last": float(data.get("price", 0)) if data.get("price") else 0,
                "size": float(data.get("size", 0)) if data.get("size") else 0,
                "volume": float(data.get("volume", 0)) if data.get("volume") else 0,
                "timestamp": data.get("timeStamp", datetime.now().isoformat()),
                "is_live": True
            }
            
            # Veriyi display_symbol ile sakla
            self.market_data[display_symbol] = market_data
            
            # Debug: Gelen veriyi göster
            print(f"[HAMMER] 📊 {display_symbol}: Bid={bid}, Ask={ask}, Last={last}")
            
        except Exception as e:
            self.logger.error(f"Error handling market data: {e}")
            
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
            
    def subscribe_symbol(self, symbol):
        """Bir sembole subscribe ol"""
        if not self.connected or not self.authenticated:
            return False
            
        # Sembolü formatla
        formatted_symbol = symbol
        if " PR" in symbol:
            # Örn: "AHL PRE" -> "AHL-E"
            # Örn: "VNO PRL" -> "VNO-L"
            parts = symbol.split(" PR")
            if len(parts) == 2:
                base = parts[0]
                suffix = parts[1].strip()
                formatted_symbol = f"{base}-{suffix}"
        elif " PRA" in symbol:  # PSEC PRA gibi özel durumlar
            parts = symbol.split(" PRA")
            base = parts[0]
            formatted_symbol = f"{base}-A"
        elif " PRC" in symbol:  # TRTX PRC gibi özel durumlar
            parts = symbol.split(" PRC")
            base = parts[0]
            formatted_symbol = f"{base}-C"
            
        print(f"[HAMMER] 🔄 Subscribe: {symbol} -> {formatted_symbol}")
            
                    # Önce snapshot isteği gönder
            snapshot_cmd = {
                "cmd": "getSymbolSnapshot",
                "sym": formatted_symbol,
                "reqID": str(time.time())
            }
            self._send_command(snapshot_cmd)
            
            # Sonra subscribe
            subscribe_cmd = {
                "cmd": "subscribe",
                "sub": "L1",
                "streamerID": "ALARICQ",  # GSMQUOTES yerine ALARICQ kullan
                "sym": [formatted_symbol]
            }
            
            # Her iki komutu da gönder
            return self._send_command(subscribe_cmd)
        
    def get_market_data(self, symbol):
        """Bir sembol için market data al"""
        return self.market_data.get(symbol, {})

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("janallres")
        
        # Hammer Pro client
        self.hammer = HammerClient(
            host='127.0.0.1',  # localhost
            port=16400,        # varsayılan port
            password='Nl201090.'  # API şifresi
        )
        
        # CSV'den ticker'ları yükle
        self.df = pd.read_csv('janalldata.csv')
        self.tickers = self.df['PREF IBKR'].tolist()
        
        # Sayfalama ayarları
        self.items_per_page = 15
        self.current_page = 0
        self.total_pages = (len(self.tickers) + self.items_per_page - 1) // self.items_per_page
        
        self.setup_ui()
        
    def setup_ui(self):
        # Üst panel - Bağlantı butonları
        top_frame = ttk.Frame(self)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        self.btn_connect = ttk.Button(top_frame, text="Hammer Pro'ya Bağlan", command=self.connect_hammer)
        self.btn_connect.pack(side='left', padx=2)
        
        self.btn_live = ttk.Button(top_frame, text="Live Data Başlat", command=self.toggle_live_data)
        self.btn_live.pack(side='left', padx=2)
        
        # Tablo
        # Statik kolonlar (CSV'den)
        static_columns = ['PREF IBKR', 'CMON', 'FINAL_THG', 'AVG_ADV', 'SMI', 'SHORT_FINAL']
        # Live kolonlar (Hammer Pro'dan)
        live_columns = ['Bid', 'Ask', 'Last', 'Volume']
        
        columns = static_columns + live_columns
        self.table = ttk.Treeview(self, columns=columns, show='headings', height=15)
        
        # Kolon başlıkları ve genişlikleri
        for col in columns:
            self.table.heading(col, text=col)
            if col in ['PREF IBKR']:
                self.table.column(col, width=150, anchor='w')  # Sol hizalı, geniş
            elif col in ['CMON', 'SMI', 'SHORT_FINAL']:
                self.table.column(col, width=80, anchor='center')  # Dar
            else:
                self.table.column(col, width=100, anchor='center')  # Normal
                
        self.table.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Sayfalama kontrolleri
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill='x', padx=5, pady=5)
        
        self.btn_prev = ttk.Button(nav_frame, text="<", command=self.prev_page)
        self.btn_prev.pack(side='left', padx=2)
        
        self.lbl_page = ttk.Label(nav_frame, text=f"Sayfa {self.current_page + 1} / {self.total_pages}")
        self.lbl_page.pack(side='left', padx=10)
        
        self.btn_next = ttk.Button(nav_frame, text=">", command=self.next_page)
        self.btn_next.pack(side='left', padx=2)
        
        # İlk sayfayı göster
        self.update_table()
        
    def connect_hammer(self):
        """Hammer Pro'ya bağlan/bağlantıyı kes"""
        if not self.hammer.connected:
            print("\n[HAMMER] 🔌 Hammer Pro'ya bağlanılıyor...")
            print(f"[HAMMER] 📍 Host: {self.hammer.host}")
            print(f"[HAMMER] 🔢 Port: {self.hammer.port}")
            
            if self.hammer.connect():
                self.btn_connect.config(text="Bağlantıyı Kes")
                print("[HAMMER] ✅ Bağlantı başarılı!")
            else:
                print("[HAMMER] ❌ Bağlantı başarısız!")
                print("[HAMMER] 💡 Kontrol edilecekler:")
                print("   1. Hammer Pro çalışıyor mu?")
                print("   2. Port numarası doğru mu?")
                print("   3. API şifresi doğru mu?")
        else:
            print("\n[HAMMER] 🔌 Bağlantı kesiliyor...")
            self.hammer.disconnect()
            self.btn_connect.config(text="Hammer Pro'ya Bağlan")
            print("[HAMMER] ✅ Bağlantı kesildi.")
            
    def toggle_live_data(self):
        if not hasattr(self, 'live_data_running'):
            self.live_data_running = False
            
        if not self.live_data_running:
            # Görünür sembollere subscribe ol
            visible_tickers = self.get_visible_tickers()
            for ticker in visible_tickers:
                self.hammer.subscribe_symbol(ticker)
                
            self.live_data_running = True
            self.btn_live.config(text="Live Data Durdur")
            
            # Tabloyu güncelleme döngüsünü başlat
            self.update_live_data()
        else:
            self.live_data_running = False
            self.btn_live.config(text="Live Data Başlat")
            
    def update_live_data(self):
        if not self.live_data_running:
            return
            
        self.update_table()
        self.after(1000, self.update_live_data)  # Her 1 saniyede bir güncelle
        
    def get_visible_tickers(self):
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.tickers))
        return self.tickers[start_idx:end_idx]
        
    def update_table(self):
        # Tabloyu temizle
        for item in self.table.get_children():
            self.table.delete(item)
            
        # Görünür ticker'ları al
        visible_tickers = self.get_visible_tickers()
        
        # Her ticker için satır ekle
        for ticker in visible_tickers:
            # CSV'den statik verileri al
            row_data = self.df[self.df['PREF IBKR'] == ticker].iloc[0]
            
            # Hammer Pro'dan live verileri al
            market_data = self.hammer.get_market_data(ticker)
            bid = market_data.get('bid', 'N/A')
            ask = market_data.get('ask', 'N/A')
            last = market_data.get('last', 'N/A')
            volume = market_data.get('volume', 'N/A')
            is_live = market_data.get('is_live', False)
            
            # Tüm değerleri birleştir
            row_values = [
                ticker,  # PREF IBKR
                row_data.get('CMON', 'N/A'),
                row_data.get('FINAL_THG', 'N/A'),
                row_data.get('AVG_ADV', 'N/A'),
                row_data.get('SMI', 'N/A'),
                row_data.get('SHORT_FINAL', 'N/A'),
                bid,
                ask,
                last,
                volume
            ]
            
            # Satırı ekle
            tags = ('live_data',) if is_live else ()
            self.table.insert('', 'end', values=row_values, tags=tags)
            
        # Live data satırlarını yeşil yap
        self.table.tag_configure('live_data', background='lightgreen')
        
    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.lbl_page.config(text=f"Sayfa {self.current_page + 1} / {self.total_pages}")
            self.update_table()
            
    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.lbl_page.config(text=f"Sayfa {self.current_page + 1} / {self.total_pages}")
            self.update_table()

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()