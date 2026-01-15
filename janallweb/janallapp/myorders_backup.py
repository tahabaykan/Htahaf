"""
My Orders module - 3 sekmeli emir takip sistemi
Pending: Bekleyen/Kısmi dolmuş emirler
Completed: Tamamen dolmuş emirler  
JDataLog: Fill anında ETF verileriyle detaylı log
"""

import tkinter as tk
from tkinter import ttk, messagebox
import datetime
import pandas as pd
import os
import websocket
import json
import threading
import time

def show_orders_window(parent):
    """3 sekmeli emir takip sistemini aç"""
    win = tk.Toplevel(parent)
    win.title("Emirlerim - 3 Sekmeli Takip Sistemi")
    win.geometry("1400x800")
    
    # Hammer client'ı al
    hammer_client = None
    try:
        # Parent'tan hammer client'ı al (self.hammer)
        if hasattr(parent, 'hammer'):
            hammer_client = parent.hammer
        else:
            print("[ORDERS] ❌ Hammer client bulunamadı")
            return
    except Exception as e:
        print(f"[ORDERS] ❌ Hammer client hatası: {e}")
        return
    
    # Ana sekme konteyner
    notebook = ttk.Notebook(win)
    notebook.pack(fill='both', expand=True, padx=10, pady=10)
    
    # 3 sekme oluştur
    pending_frame = ttk.Frame(notebook)
    completed_frame = ttk.Frame(notebook)
    jdatalog_frame = ttk.Frame(notebook)
    
    notebook.add(pending_frame, text="Pending Orders")
    notebook.add(completed_frame, text="Completed Orders") 
    notebook.add(jdatalog_frame, text="JDataLog")
    
    # Hammer Pro API sınıfı
    class HammerProAPI:
        def __init__(self):
            self.ws = None
            self.connected = False
            self.orders = []
            self.positions = []
            self.callbacks = {}
            
        def connect(self, password="Nl201090.", port=16400):
            """Hammer Pro WebSocket API'ye bağlan"""
            try:
                # WebSocket bağlantısı kur
                self.ws = websocket.WebSocketApp(
                    f"ws://127.0.0.1:{port}",
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close
                )
                
                # Bağlantıyı ayrı thread'de başlat
                import threading
                ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
                ws_thread.start()
                
                # Bağlantının açılmasını bekle
                import time
                wait_time = 0
                while not self.connected and wait_time < 10:
                    time.sleep(0.5)
                    wait_time += 0.5
                    print(f"[HAMMER PRO] ⏳ Bağlantı bekleniyor... {wait_time}s")
                
                if self.connected:
                    # Connect komutu gönder
                    connect_cmd = {
                        "cmd": "connect",
                        "pwd": password,
                        "reqID": "connect_001"
                    }
                    self.ws.send(json.dumps(connect_cmd))
                    
                    print(f"[HAMMER PRO] ✅ WebSocket bağlantısı kuruldu: ws://127.0.0.1:{port}")
                    return True
                else:
                    print(f"[HAMMER PRO] ❌ WebSocket bağlantısı kurulamadı: ws://127.0.0.1:{port}")
                    return False
                
            except Exception as e:
                print(f"[HAMMER PRO] ❌ Bağlantı hatası: {e}")
                return False
        
        def on_open(self, ws):
            """WebSocket bağlantısı açıldığında"""
            print("[HAMMER PRO] 🔗 WebSocket bağlantısı açıldı")
            self.connected = True
        
        def on_message(self, ws, message):
            """WebSocket mesajı alındığında"""
            try:
                data = json.loads(message)
                print(f"[HAMMER PRO] 📨 Mesaj alındı: {data}")
                
                # Mesaj tipine göre işle
                if data.get('cmd') == 'transactionsUpdate':
                    print("[HAMMER PRO] 📋 Transactions update alındı")
                    self.handle_transactions_update(data)
                elif data.get('cmd') == 'positionsUpdate':
                    print("[HAMMER PRO] 📊 Positions update alındı")
                    self.handle_positions_update(data)
                elif data.get('cmd') == 'enumTradingAccounts':
                    print("[HAMMER PRO] 🏦 Trading account'lar listelendi")
                    if data.get('success') == 'OK' and 'result' in data:
                        accounts = data['result'].get('accounts', [])
                        if accounts:
                            # İlk account'u kullan
                            first_account = accounts[0]
                            account_key = first_account.get('accountKey')
                            print(f"[HAMMER PRO] ✅ İlk account seçildi: {account_key}")
                            self.start_trading_account(account_key)
                        else:
                            print("[HAMMER PRO] ⚠️ Hiç trading account bulunamadı")
                    else:
                        print(f"[HAMMER PRO] ❌ Trading account listesi alınamadı: {data.get('result')}")
                elif data.get('cmd') == 'startTradingAccount':
                    print("[HAMMER PRO] 🚀 Trading account başlatıldı")
                    if data.get('success') == 'OK':
                        print("[HAMMER PRO] ✅ Trading account başarıyla başlatıldı")
                        # Şimdi emirleri al
                        self.get_transactions()
                    else:
                        print(f"[HAMMER PRO] ❌ Trading account başlatılamadı: {data.get('result')}")
                elif data.get('cmd') == 'connect':
                    if data.get('success') == 'OK':
                        print("[HAMMER PRO] ✅ Bağlantı başarılı")
                        # Trading account'ları listele
                        self.enum_trading_accounts()
                    else:
                        print(f"[HAMMER PRO] ❌ Bağlantı başarısız: {data.get('result')}")
                        
            except Exception as e:
                print(f"[HAMMER PRO] ❌ Mesaj işleme hatası: {e}")
        
        def on_error(self, ws, error):
            """WebSocket hatası"""
            print(f"[HAMMER PRO] ❌ WebSocket hatası: {error}")
        
        def on_close(self, ws, close_status_code, close_msg):
            """WebSocket bağlantısı kapandığında"""
            print("[HAMMER PRO] 🔌 WebSocket bağlantısı kapandı")
            self.connected = False
        
        def start_trading_account(self, account_key):
            """Trading account'u başlat"""
            try:
                print(f"[HAMMER PRO] 🚀 Trading account başlatılıyor: {account_key}")
                
                start_cmd = {
                    "cmd": "startTradingAccount",
                    "accountKey": account_key,
                    "reqID": "start_001"
                }
                self.ws.send(json.dumps(start_cmd))
                
                print(f"[HAMMER PRO] 🔍 Trading account başlatma komutu gönderildi: {account_key}")
                
            except Exception as e:
                print(f"[HAMMER PRO] ❌ Trading account başlatma hatası: {e}")
        
        def enum_trading_accounts(self):
            """Trading account'ları listele"""
            try:
                enum_cmd = {
                    "cmd": "enumTradingAccounts",
                    "reqID": "enum_001"
                }
                self.ws.send(json.dumps(enum_cmd))
                
                print("[HAMMER PRO] 🔍 Trading account'lar listeleniyor...")
                
            except Exception as e:
                print(f"[HAMMER PRO] ❌ Trading account listesi hatası: {e}")
        
        def get_transactions(self):
            """Emirleri al"""
            try:
                print("[HAMMER PRO] 📋 Emirler isteniyor...")
                
                # Varsayılan account key kullan (ilk bağlanan account)
                transactions_cmd = {
                    "cmd": "getTransactions",
                    "reqID": "trans_001"
                }
                self.ws.send(json.dumps(transactions_cmd))
                
                print("[HAMMER PRO] ✅ Emir alma komutu gönderildi")
                
            except Exception as e:
                print(f"[HAMMER PRO] ❌ Emir alma hatası: {e}")
        
        def get_orders(self):
            """Mevcut emirleri al"""
            try:
                if not self.connected:
                    print("[HAMMER PRO] ❌ Bağlantı yok")
                    return []
                
                # Önce trading account'ları listele
                print("[HAMMER PRO] 🔍 Trading account'lar listeleniyor...")
                enum_cmd = {
                    "cmd": "enumTradingAccounts",
                    "reqID": "enum_001"
                }
                self.ws.send(json.dumps(enum_cmd))
                
                # Kısa bir süre bekle
                import time
                time.sleep(1)
                
                # Mevcut emirleri döndür
                if hasattr(self, 'orders') and self.orders:
                    print(f"[HAMMER PRO] ✅ {len(self.orders)} emir bulundu")
                    return self.orders
                else:
                    print("[HAMMER PRO] ⚠️ Henüz emir yok")
                    return []
                
            except Exception as e:
                print(f"[HAMMER PRO] ❌ Emir alma hatası: {e}")
                return []
        
        def handle_transactions_update(self, data):
            """Transactions update mesajını işle"""
            try:
                if 'result' in data and 'transactions' in data['result']:
                    transactions = data['result']['transactions']
                    self.orders = []
                    
                    for trans in transactions:
                        order = {
                            'order_id': trans.get('OrderID', ''),
                            'symbol': trans.get('Symbol', ''),
                            'action': trans.get('Action', ''),
                            'qty': trans.get('QTY', 0),
                            'filled_qty': trans.get('FilledQTY', 0),
                            'remaining_qty': trans.get('RemainingQTY', 0),
                            'limit_price': trans.get('LimitPrice', 0),
                            'status': trans.get('StatusID', ''),
                            'order_time': trans.get('OrderDT', '')
                        }
                        self.orders.append(order)
                    
                    print(f"[HAMMER PRO] ✅ {len(self.orders)} emir güncellendi")
                    
            except Exception as e:
                print(f"[HAMMER PRO] ❌ Transactions update hatası: {e}")
        
        def handle_positions_update(self, data):
            """Positions update mesajını işle"""
            try:
                if 'result' in data and 'positions' in data['result']:
                    positions = data['result']['positions']
                    self.positions = positions
                    print(f"[HAMMER PRO] ✅ {len(self.positions)} pozisyon güncellendi")
                    
            except Exception as e:
                print(f"[HAMMER PRO] ❌ Positions update hatası: {e}")
    
    # Sekme sınıfları
    class OrderTracker:
        def __init__(self, parent_window, hammer_client):
            self.parent = parent_window
            self.hammer = hammer_client
            self.etf_symbols = ['TLT', 'IEF', 'IEI', 'PFF', 'SHY']
            self.jdatalog_file = 'jdatalog.csv'
            
            # Hammer Pro API'yi başlat
            self.hammer_api = HammerProAPI()
            # connect_to_hammer_pro() artık manuel olarak çağrılacak
        
        def connect_to_hammer_pro(self):
            """Hammer Pro'ya bağlan"""
            try:
                # Önce mevcut Hammer bağlantısını kontrol et
                if self.hammer and hasattr(self.hammer, 'connected') and self.hammer.connected:
                    print("[ORDERS] ✅ Mevcut Hammer Pro bağlantısı kullanılıyor")
                    # Emirleri otomatik olarak çekmeye başla
                    self.start_auto_refresh()
                    return
                
                # WebSocket API'yi dene
                print("[ORDERS] 🔍 WebSocket API deneniyor...")
                def connect_thread():
                    success = self.hammer_api.connect(password="Nl201090.", port=16400)
                    if success:
                        print("[ORDERS] ✅ Hammer Pro WebSocket API'ye bağlanıldı")
                        # Emirleri otomatik olarak çekmeye başla
                        self.start_auto_refresh()
                    else:
                        print("[ORDERS] ❌ Hammer Pro WebSocket API'ye bağlanılamadı")
                        # Mevcut bağlantıyı dene
                        if self.hammer and hasattr(self.hammer, 'connected'):
                            print("[ORDERS] 🔄 Mevcut Hammer bağlantısı deneniyor...")
                            self.start_auto_refresh()
                
                thread = threading.Thread(target=connect_thread, daemon=True)
                thread.start()
                
            except Exception as e:
                print(f"[ORDERS] ❌ Hammer Pro bağlantı hatası: {e}")
                # Mevcut bağlantıyı dene
                if self.hammer and hasattr(self.hammer, 'connected'):
                    print("[ORDERS] 🔄 Mevcut Hammer bağlantısı deneniyor...")
                    self.start_auto_refresh()
        
        def start_auto_refresh(self):
            """Otomatik emir yenileme başlat"""
            def auto_refresh():
                # UI kurulumu tamamlanana kadar bekle
                while not hasattr(self, 'pending_tree') or not self.pending_tree:
                    print("[ORDERS] ⏳ UI kurulumu bekleniyor...")
                    time.sleep(1)
                
                print("[ORDERS] ✅ UI kurulumu tamamlandı, otomatik yenileme başlıyor...")
                
                while self.auto_refresh_active:
                    try:
                        # Widget'lar hala geçerli mi kontrol et
                        if not hasattr(self, 'pending_tree') or not self.pending_tree:
                            print("[ORDERS] ⚠️ Widget'lar geçersiz, yenileme durduruluyor...")
                            break
                        
                        # Hammer Pro API veya mevcut Hammer bağlantısı varsa yenile
                        if (self.hammer_api.connected or 
                            (self.hammer and hasattr(self.hammer, 'connected') and self.hammer.connected)):
                            
                            self.refresh_pending_orders()
                            self.update_connection_status()
                            time.sleep(5)  # 5 saniyede bir yenile
                        else:
                            # Bağlantı yoksa 10 saniyede bir kontrol et
                            time.sleep(10)
                            
                    except Exception as e:
                        print(f"[ORDERS] ❌ Otomatik yenileme hatası: {e}")
                        time.sleep(10)  # Hata durumunda 10 saniye bekle
                
                print("[ORDERS] 🛑 Otomatik yenileme durduruldu")
            
            self.auto_refresh_active = True
            self.auto_refresh_thread = threading.Thread(target=auto_refresh, daemon=True)
            self.auto_refresh_thread.start()
        
        def update_connection_status(self):
            """Bağlantı durumunu güncelle"""
            try:
                if hasattr(self, 'connection_status') and self.connection_status:
                    if (self.hammer_api.connected or 
                        (self.hammer and hasattr(self.hammer, 'connected') and self.hammer.connected)):
                        self.connection_status.config(text="🟢 Hammer Pro Bağlandı", foreground='green')
                    else:
                        self.connection_status.config(text="🔴 Hammer Pro Bağlantısı Yok", foreground='red')
            except Exception as e:
                print(f"[ORDERS] ❌ Durum güncelleme hatası: {e}")
        
        def stop_auto_refresh(self):
            """Otomatik yenilemeyi durdur"""
            try:
                if hasattr(self, 'auto_refresh_active'):
                    self.auto_refresh_active = False
                    print("[ORDERS] 🛑 Otomatik yenileme durduruluyor...")
                    
                    # Thread'in durmasını bekle
                    if hasattr(self, 'auto_refresh_thread') and self.auto_refresh_thread.is_alive():
                        self.auto_refresh_thread.join(timeout=2.0)
                        print("[ORDERS] ✅ Otomatik yenileme thread'i durduruldu")
                    
            except Exception as e:
                print(f"[ORDERS] ❌ Auto-refresh durdurma hatası: {e}")
        
        def cleanup(self):
            """OrderTracker'ı temizle ve kaynakları serbest bırak"""
            try:
                print("[ORDERS] 🧹 OrderTracker temizleniyor...")
                self.stop_auto_refresh()
                print("[ORDERS] ✅ OrderTracker temizlendi")
            except Exception as e:
                print(f"[ORDERS] ❌ Cleanup hatası: {e}")
            
        def setup_pending_tab(self, frame):
            """Pending Orders sekmesi"""
            label = ttk.Label(frame, text="Bekleyen ve Kısmi Dolmuş Emirler", 
                            font=('Arial', 12, 'bold'))
            label.pack(pady=10)
            
            # Pending emirler tablosu
            pending_cols = ['select', 'order_id', 'symbol', 'action', 'qty', 
                          'filled_qty', 'remaining_qty', 'limit_price', 'status', 'order_time']
            pending_headers = ['Seç', 'Order ID', 'Symbol', 'Action', 'Qty', 
                             'Filled', 'Remaining', 'Price', 'Status', 'Time']
            
            self.pending_tree = ttk.Treeview(frame, columns=pending_cols, show='headings', height=15)
            
            # Kolon ayarları
            for c, h in zip(pending_cols, pending_headers):
                self.pending_tree.heading(c, text=h)
                if c == 'select':
                    self.pending_tree.column(c, width=50, anchor='center')
                elif c == 'order_id':
                    self.pending_tree.column(c, width=120, anchor='center')
                elif c in ['symbol', 'action']:
                    self.pending_tree.column(c, width=100, anchor='center')
                elif c in ['qty', 'filled_qty', 'remaining_qty']:
                    self.pending_tree.column(c, width=80, anchor='center')
                elif c == 'limit_price':
                    self.pending_tree.column(c, width=90, anchor='center')
                elif c == 'status':
                    self.pending_tree.column(c, width=100, anchor='center')
                else:
                    self.pending_tree.column(c, width=150, anchor='center')
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(frame, orient='vertical', command=self.pending_tree.yview)
            self.pending_tree.configure(yscrollcommand=scrollbar.set)
            
            self.pending_tree.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # Bağlantı durumu göstergesi
            status_frame = ttk.Frame(frame)
            status_frame.pack(fill='x', pady=5)
            
            self.connection_status = ttk.Label(status_frame, text="🔴 Hammer Pro Bağlantısı Yok", 
                                             font=('Arial', 10, 'bold'), foreground='red')
            self.connection_status.pack(side='left', padx=5)
            
            # Butonlar
            btn_frame = ttk.Frame(frame)
            btn_frame.pack(fill='x', pady=5)
            
            ttk.Button(btn_frame, text="Yenile", 
                      command=self.refresh_pending_orders).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="Seçili Emirleri İptal Et", 
                      command=self.cancel_selected_orders).pack(side='left', padx=5)
            ttk.Button(btn_frame, text="Hammer Pro'ya Bağlan", 
                      command=self.connect_to_hammer_pro).pack(side='left', padx=5)
            
        def setup_completed_tab(self, frame):
            """Completed Orders sekmesi"""
            label = ttk.Label(frame, text="Tamamen Dolmuş Emirler", 
                            font=('Arial', 12, 'bold'))
            label.pack(pady=10)
            
            # Completed emirler tablosu
            completed_cols = ['symbol', 'action', 'filled_qty', 'avg_price', 'total_value', 'fill_time']
            completed_headers = ['Symbol', 'Action', 'Filled Qty', 'Avg Price', 'Total Value', 'Fill Time']
            
            self.completed_tree = ttk.Treeview(frame, columns=completed_cols, show='headings', height=15)
            
            # Kolon ayarları
            for c, h in zip(completed_cols, completed_headers):
                self.completed_tree.heading(c, text=h)
                if c in ['symbol', 'action']:
                    self.completed_tree.column(c, width=100, anchor='center')
                elif c == 'filled_qty':
                    self.completed_tree.column(c, width=100, anchor='center')
                elif c in ['avg_price', 'total_value']:
                    self.completed_tree.column(c, width=120, anchor='center')
                else:
                    self.completed_tree.column(c, width=200, anchor='center')
            
            # Scrollbar
            scrollbar2 = ttk.Scrollbar(frame, orient='vertical', command=self.completed_tree.yview)
            self.completed_tree.configure(yscrollcommand=scrollbar2.set)
            
            self.completed_tree.pack(side='left', fill='both', expand=True)
            scrollbar2.pack(side='right', fill='y')
            
            # Butonlar
            btn_frame2 = ttk.Frame(frame)
            btn_frame2.pack(fill='x', pady=5)
            
            ttk.Button(btn_frame2, text="Yenile", 
                      command=self.refresh_completed_orders).pack(side='left', padx=5)
            
        def setup_jdatalog_tab(self, frame):
            """JDataLog sekmesi"""
            label = ttk.Label(frame, text="Fill Anında ETF Verileriyle Detaylı Log", 
                            font=('Arial', 12, 'bold'))
            label.pack(pady=10)
            
            # JDataLog tablosu
            jdata_cols = ['fill_qty', 'symbol', 'fill_price', 'fill_time', 'TLT', 'IEF', 'IEI', 'PFF', 'SHY']
            jdata_headers = ['Qty', 'Symbol', 'Fill Price', 'Fill Time', 'TLT', 'IEF', 'IEI', 'PFF', 'SHY']
            
            self.jdata_tree = ttk.Treeview(frame, columns=jdata_cols, show='headings', height=15)
            
            # Kolon ayarları
            for c, h in zip(jdata_cols, jdata_headers):
                self.jdata_tree.heading(c, text=h)
                if c in ['fill_qty', 'symbol']:
                    self.jdata_tree.column(c, width=100, anchor='center')
                elif c == 'fill_price':
                    self.jdata_tree.column(c, width=100, anchor='center')
                elif c == 'fill_time':
                    self.jdata_tree.column(c, width=180, anchor='center')
                else:  # ETF kolonları
                    self.jdata_tree.column(c, width=80, anchor='center')
            
            # Scrollbar
            scrollbar3 = ttk.Scrollbar(frame, orient='vertical', command=self.jdata_tree.yview)
            self.jdata_tree.configure(yscrollcommand=scrollbar3.set)
            
            self.jdata_tree.pack(side='left', fill='both', expand=True)
            scrollbar3.pack(side='right', fill='y')
            
            # Butonlar
            btn_frame3 = ttk.Frame(frame)
            btn_frame3.pack(fill='x', pady=5)
            
            ttk.Button(btn_frame3, text="Yenile", 
                      command=self.refresh_jdatalog).pack(side='left', padx=5)
            ttk.Button(btn_frame3, text="CSV Export", 
                      command=self.export_jdatalog).pack(side='left', padx=5)
            ttk.Button(btn_frame3, text="ETF Verileri Güncelle", 
                      command=self.update_missing_etf_data).pack(side='left', padx=5)
        
        def refresh_pending_orders(self):
            """Bekleyen emirleri yenile"""
            try:
                # Widget kontrolü - pending_tree henüz oluşturulmamışsa bekle
                if not hasattr(self, 'pending_tree') or not self.pending_tree:
                    print("[PENDING] ⏳ Pending tree henüz oluşturulmadı, bekleniyor...")
                    return
                
                # Tabloyu temizle
                for item in self.pending_tree.get_children():
                    self.pending_tree.delete(item)
                
                # Mevcut Hammer client'dan emirleri al
                if self.hammer and hasattr(self.hammer, 'connected') and self.hammer.connected:
                    print("[PENDING] 🔍 Hammer client'dan emirler alınıyor...")
                    try:
                        # Pozisyonlar gibi doğrudan getTransactions komutu gönder
                        if hasattr(self.hammer, '_send_and_wait'):
                            print("[PENDING] 🔍 _send_and_wait metodu kullanılıyor...")
                            
                            # getTransactions komutunu gönder
                            resp = self.hammer._send_and_wait({
                                "cmd": "getTransactions",
                                "accountKey": "ALARIC:TOPI002240A7",  # Hammer client'daki account key
                                "forceRefresh": True
                            }, timeout=10.0)
                            
                            print(f"[PENDING] 📥 getTransactions yanıtı: {resp}")
                            
                            if resp and resp.get('success') == 'OK':
                                result = resp.get('result', {})
                                print(f"[PENDING] 🔍 Result tipi: {type(result)} - {result}")
                                
                                # Result string ise (henüz veri gelmemiş), bekle ve tekrar dene
                                if isinstance(result, str):
                                    if "Requesting transactions" in result:
                                        print("[PENDING] ⏳ Transactions isteniyor, bekleniyor...")
                                        # Kısa bir süre bekle ve tekrar dene
                                        import time
                                        time.sleep(2)
                                        
                                        # Tekrar getTransactions komutunu gönder
                                        resp2 = self.hammer._send_and_wait({
                                            "cmd": "getTransactions",
                                            "accountKey": "ALARIC:TOPI002240A7",
                                            "forceRefresh": False  # Cache'den al
                                        }, timeout=10.0)
                                        
                                        print(f"[PENDING] 📥 İkinci deneme yanıtı: {resp2}")
                                        
                                        if resp2 and resp2.get('success') == 'OK':
                                            result = resp2.get('result', {})
                                            print(f"[PENDING] 🔍 İkinci result tipi: {type(result)} - {result}")
                                
                                # Result dictionary ise transactions'ları işle
                                if isinstance(result, dict) and 'transactions' in result:
                                    transactions = result.get('transactions', [])
                                    
                                    print(f"[PENDING] 📊 {len(transactions)} transaction bulundu")
                                    
                                    pending_count = 0
                                    for tx in transactions:
                                        print(f"[PENDING] 🔍 İşlenen transaction: {tx}")
                                        
                                        # Sadece açık emirleri (IsOpen=true) filtrele
                                        if tx.get('IsOpen', False):
                                            order_id = tx.get('OrderID', 'N/A')
                                            symbol = tx.get('Symbol', 'N/A')
                                            action = tx.get('Action', 'N/A')
                                            total_qty = float(tx.get('QTY', 0))
                                            filled_qty = float(tx.get('FilledQTY', 0))
                                            remaining_qty = float(tx.get('RemainingQTY', total_qty))
                                            limit_price = f"${float(tx.get('LimitPrice', 0)):.2f}"
                                            order_time = tx.get('OrderDT', 'N/A')
                                            
                                            # Kısmi doldurma gösterimi
                                            if filled_qty > 0:
                                                status_display = f"{filled_qty}/{total_qty}"
                                            else:
                                                status_display = "OPEN"
                                            
                                            values = ('☐', order_id, symbol, action, total_qty, 
                                                    filled_qty, remaining_qty, limit_price, status_display, order_time)
                                            
                                            self.pending_tree.insert('', 'end', values=values)
                                            pending_count += 1
                                    
                                    print(f"[PENDING] ✅ {pending_count} bekleyen emir yüklendi (_send_and_wait)")
                                else:
                                    print(f"[PENDING] ⚠️ Result dictionary değil veya transactions yok: {result}")
                                    # Fallback: get_orders metodunu dene
                                    orders = self.hammer.get_orders()
                                    print(f"[PENDING] 📥 Fallback get_orders: {orders}")
                            else:
                                print(f"[PENDING] ❌ getTransactions başarısız: {resp}")
                                # Fallback: get_orders metodunu dene
                                orders = self.hammer.get_orders()
                                print(f"[PENDING] 📥 Fallback get_orders: {orders}")
                        else:
                            print("[PENDING] ⚠️ _send_and_wait metodu bulunamadı, get_orders kullanılıyor...")
                            orders = self.hammer.get_orders()
                            print(f"[PENDING] 📥 get_orders sonucu: {orders}")
                            
                    except Exception as e:
                        print(f"[PENDING] ❌ Hammer client'dan emir alma hatası: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print("[PENDING] ❌ Hiçbir Hammer bağlantısı yok")
                
            except Exception as e:
                print(f"[PENDING] ❌ Emirleri yenileme hatası: {e}")
                messagebox.showerror("Hata", f"Bekleyen emirler yenilenemedi: {e}")
        
        def refresh_completed_orders(self):
            """Tamamen dolmuş emirleri yenile"""
            try:
                # Tabloyu temizle
                for item in self.completed_tree.get_children():
                    self.completed_tree.delete(item)
                
                if not self.hammer or not self.hammer.connected:
                    print("[COMPLETED] ❌ Hammer Pro bağlantısı yok")
                    return
                
                # Hammer Pro'dan transactions'ları al
                try:
                    resp = self.hammer._send_and_wait({
                        "cmd": "getTransactions",
                        "accountKey": "ALARIC:TOPI002240A7",
                        "forceRefresh": False
                    }, timeout=10.0)
                    
                    if resp and resp.get('success') == 'OK':
                        result = resp.get('result', {})
                        print(f"[COMPLETED] 🔍 Result tipi: {type(result)} - {result}")
                        
                        # Result string ise (henüz veri gelmemiş), bekle ve tekrar dene
                        if isinstance(result, str):
                            if "Requesting transactions" in result:
                                print("[COMPLETED] ⏳ Transactions isteniyor, bekleniyor...")
                                import time
                                time.sleep(2)
                                
                                # Tekrar getTransactions komutunu gönder
                                resp2 = self.hammer._send_and_wait({
                                    "cmd": "getTransactions",
                                    "accountKey": "ALARIC:TOPI002240A7",
                                    "forceRefresh": False
                                }, timeout=10.0)
                                
                                if resp2 and resp2.get('success') == 'OK':
                                    result = resp2.get('result', {})
                        
                        if isinstance(result, dict) and 'transactions' in result:
                            transactions = result.get('transactions', [])
                            print(f"[COMPLETED] 📊 {len(transactions)} transaction bulundu")
                            
                            completed_count = 0
                            for tx in transactions:
                                print(f"[COMPLETED] 🔍 İşlenen transaction: {tx}")
                                
                                # Sadece tamamlanmış emirleri (IsOpen=false) filtrele
                                if not tx.get('IsOpen', True):
                                    order_id = tx.get('OrderID', 'N/A')
                                    symbol = tx.get('Symbol', 'N/A')
                                    action = tx.get('Action', 'N/A')
                                    total_qty = float(tx.get('QTY', 0))
                                    filled_qty = float(tx.get('FilledQTY', 0))
                                    avg_price = float(tx.get('FilledPrice', tx.get('FillPrice', 0)))
                                    fill_time = tx.get('FillDT', tx.get('OrderDT', 'N/A'))
                                    
                                    # Quantity 0 olan emirleri filtrele (cancelled/partial)
                                    if filled_qty <= 0:
                                        print(f"[COMPLETED] ⚠️ Quantity 0 emir filtrelendi: {symbol} - {filled_qty}")
                                        continue
                                    
                                    total_value = f"${avg_price * filled_qty:.2f}"
                                    
                                    values = (symbol, action, filled_qty, f"${avg_price:.2f}", total_value, fill_time)
                                    
                                    self.completed_tree.insert('', 'end', values=values)
                                    completed_count += 1
                            
                            print(f"[COMPLETED] ✅ {completed_count} tamamlanmış emir yüklendi")
                        else:
                            print(f"[COMPLETED] ⚠️ Result dictionary değil veya transactions yok: {result}")
                            # Fallback: get_orders metodunu dene
                orders = self.hammer.get_orders()
                            print(f"[COMPLETED] 📥 Fallback get_orders: {orders}")
                
                            if orders:
                completed_count = 0
                for order in orders:
                                    try:
                                        # Hammer Pro'dan gelen veri formatını parse et
                                        if isinstance(order, dict):
                                            # Dictionary format
                        symbol = order.get('symbol', 'N/A')
                        action = order.get('action', 'N/A')
                                            qty = float(order.get('qty', 0))
                                            price = float(order.get('price', 0))
                                            status = order.get('status', '')
                                            
                                            # Tamamlanmış emirleri filtrele
                                            if status in ['FILLED', 'COMPLETED'] or 'filled' in str(status).lower():
                                                values = (symbol, action, qty, f"${price:.2f}", f"${price * qty:.2f}", "N/A")
                                                self.completed_tree.insert('', 'end', values=values)
                                                completed_count += 1
                                        else:
                                            # String format - JSON parse et
                                            try:
                                                import json
                                                order_data = json.loads(str(order))
                                                symbol = order_data.get('symbol', 'N/A')
                                                action = order_data.get('action', 'N/A')
                                                qty = float(order_data.get('qty', 0))
                                                price = float(order_data.get('price', 0))
                                                status = order_data.get('status', '')
                                                
                                                if status in ['FILLED', 'COMPLETED'] or 'filled' in str(status).lower():
                                                    values = (symbol, action, qty, f"${price:.2f}", f"${price * qty:.2f}", "N/A")
                        self.completed_tree.insert('', 'end', values=values)
                        completed_count += 1
                                            except:
                                                continue
                                    
                                    except Exception as e:
                                        print(f"[COMPLETED] ⚠️ Order parse hatası: {e} - {order}")
                                        continue
                                
                                print(f"[COMPLETED] ✅ Fallback ile {completed_count} tamamlanmış emir yüklendi")
                    else:
                        print(f"[COMPLETED] ❌ getTransactions başarısız: {resp}")
                        
                except Exception as e:
                    print(f"[COMPLETED] ❌ getTransactions hatası: {e}")
                    # Fallback: get_orders metodunu dene
                    orders = self.hammer.get_orders()
                    print(f"[COMPLETED] 📥 Fallback get_orders: {orders}")
                
            except Exception as e:
                print(f"[COMPLETED] ❌ Tamamlanmış emirleri yenileme hatası: {e}")
                messagebox.showerror("Hata", f"Tamamlanmış emirler yenilenemedi: {e}")
        
        def refresh_jdatalog(self):
            """JDataLog'u yenile ve yeni tamamlanan emirleri kaydet"""
            try:
                # Tabloyu temizle
                for item in self.jdata_tree.get_children():
                    self.jdata_tree.delete(item)
                
                if not self.hammer or not self.hammer.connected:
                    print("[JDATALOG] ❌ Hammer Pro bağlantısı yok")
                    return
                
                # Hammer Pro'dan transactions'ları al ve yeni tamamlananları kaydet
                try:
                    resp = self.hammer._send_and_wait({
                        "cmd": "getTransactions",
                        "accountKey": "ALARIC:TOPI002240A7",
                        "forceRefresh": False
                    }, timeout=10.0)
                    
                    if resp and resp.get('success') == 'OK':
                        result = resp.get('result', {})
                        print(f"[JDATALOG] 🔍 Result tipi: {type(result)} - {result}")
                        
                        # Result string ise (henüz veri gelmemiş), bekle ve tekrar dene
                        if isinstance(result, str):
                            if "Requesting transactions" in result:
                                print("[JDATALOG] ⏳ Transactions isteniyor, bekleniyor...")
                                import time
                                time.sleep(2)
                                
                                # Tekrar getTransactions komutunu gönder
                                resp2 = self.hammer._send_and_wait({
                                    "cmd": "getTransactions",
                                    "accountKey": "ALARIC:TOPI002240A7",
                                    "forceRefresh": False
                                }, timeout=10.0)
                                
                                if resp2 and resp2.get('success') == 'OK':
                                    result = resp2.get('result', {})
                        
                        if isinstance(result, dict) and 'transactions' in result:
                            transactions = result.get('transactions', [])
                            print(f"[JDATALOG] 📊 {len(transactions)} transaction bulundu")
                            
                            # Mevcut CSV'yi oku
                            existing_data = []
                if os.path.exists(self.jdatalog_file):
                                try:
                                    df_existing = pd.read_csv(self.jdatalog_file)
                                    existing_data = df_existing.to_dict('records')
                                    print(f"[JDATALOG] 📁 Mevcut {len(existing_data)} kayıt bulundu")
                                except Exception as e:
                                    print(f"[JDATALOG] ⚠️ Mevcut CSV okuma hatası: {e}")
                            
                            # Yeni tamamlanan emirleri bul ve kaydet
                            new_records = []
                            for tx in transactions:
                                print(f"[JDATALOG] 🔍 İşlenen transaction: {tx}")
                                
                                # Sadece tamamlanmış emirleri (IsOpen=false) filtrele
                                if not tx.get('IsOpen', True):
                                    order_id = tx.get('OrderID', 'N/A')
                                    symbol = tx.get('Symbol', 'N/A')
                                    action = tx.get('Action', 'N/A')
                                    filled_qty = float(tx.get('FilledQTY', 0))
                                    
                                    # Fill price'ı farklı alanlardan dene
                                    fill_price = 0.0
                                    possible_price_fields = ['FilledPrice', 'FillPrice', 'LimitPrice', 'AvgPrice']
                                    for field in possible_price_fields:
                                        if tx.get(field) and float(tx.get(field, 0)) > 0:
                                            fill_price = float(tx.get(field))
                                            print(f"[JDATALOG] 💰 {symbol} fill price bulundu ({field}): ${fill_price:.2f}")
                                            break
                                    
                                    if fill_price == 0.0:
                                        print(f"[JDATALOG] ⚠️ {symbol} fill price bulunamadı: {list(tx.keys())}")
                                    
                                    fill_time = tx.get('FillDT', tx.get('OrderDT', 'N/A'))
                                    
                                    # Quantity 0 olan emirleri filtrele (cancelled/partial)
                                    if filled_qty <= 0:
                                        print(f"[JDATALOG] ⚠️ Quantity 0 emir filtrelendi: {symbol} - {filled_qty}")
                                        continue
                                    
                                    # Bu emir zaten kaydedilmiş mi kontrol et
                                    already_exists = any(
                                        record.get('order_id') == order_id and 
                                        record.get('symbol') == symbol and 
                                        record.get('fill_time') == fill_time
                                        for record in existing_data
                                    )
                                    
                                    print(f"[JDATALOG] 🔍 Duplicate check: {symbol} - {order_id} - {fill_time}")
                                    print(f"[JDATALOG] 🔍 Already exists: {already_exists}")
                                    
                                    if not already_exists:
                                        print(f"[JDATALOG] 🆕 Yeni kayıt bulundu: {symbol} - {fill_time}")
                                        
                                        # Fill anındaki ETF fiyatlarını çek
                                        print(f"[JDATALOG] 🔍 ETF fiyatları çekiliyor...")
                                        etf_prices = self.get_etf_prices_at_fill_time(fill_time)
                                        print(f"[JDATALOG] 📊 ETF fiyatları: {etf_prices}")
                                        
                                        # Yeni kayıt oluştur
                                        new_record = {
                                            'order_id': order_id,
                                            'symbol': symbol,
                                            'action': action,
                                            'fill_qty': filled_qty,
                                            'fill_price': fill_price,
                                            'fill_time': fill_time,
                                            'TLT': etf_prices.get('TLT', 0.0),
                                            'IEF': etf_prices.get('IEF', 0.0),
                                            'IEI': etf_prices.get('IEI', 0.0),
                                            'PFF': etf_prices.get('PFF', 0.0),
                                            'SHY': etf_prices.get('SHY', 0.0)
                                        }
                                        new_records.append(new_record)
                                        existing_data.append(new_record)
                                        print(f"[JDATALOG] ➕ Yeni kayıt eklendi: {symbol} - {filled_qty} @ {fill_price}")
                            
                            # CSV'yi güncelle
                            if new_records:
                                df_updated = pd.DataFrame(existing_data)
                                df_updated.to_csv(self.jdatalog_file, index=False, encoding='utf-8-sig')
                                print(f"[JDATALOG] 💾 {len(new_records)} yeni kayıt CSV'ye eklendi")
                            
                            # Tabloyu güncelle (quantity 0 olanları filtrele)
                            filtered_records = [r for r in existing_data if r.get('fill_qty', 0) > 0]
                            
                            for record in filtered_records:
                                values = (
                                    record.get('fill_qty', 'N/A'),
                                    record.get('symbol', 'N/A'), 
                                    f"${record.get('fill_price', 0):.2f}",
                                    record.get('fill_time', 'N/A'),
                                    f"${record.get('TLT', 0):.2f}" if pd.notna(record.get('TLT')) else 'N/A',
                                    f"${record.get('IEF', 0):.2f}" if pd.notna(record.get('IEF')) else 'N/A',
                                    f"${record.get('IEI', 0):.2f}" if pd.notna(record.get('IEI')) else 'N/A',
                                    f"${record.get('PFF', 0):.2f}" if pd.notna(record.get('PFF')) else 'N/A',
                                    f"${record.get('SHY', 0):.2f}" if pd.notna(record.get('SHY')) else 'N/A'
                                )
                                
                                self.jdata_tree.insert('', 'end', values=values)
                            
                            print(f"[JDATALOG] ✅ {len(existing_data)} fill kaydı yüklendi")
                        else:
                            print(f"[JDATALOG] ⚠️ Result dictionary değil veya transactions yok: {result}")
                            # Fallback: Mevcut CSV'yi oku
                            if os.path.exists(self.jdatalog_file):
                                df = pd.read_csv(self.jdatalog_file)
                    for _, row in df.iterrows():
                        values = (
                            row.get('fill_qty', 'N/A'),
                            row.get('symbol', 'N/A'), 
                            f"${row.get('fill_price', 0):.2f}",
                            row.get('fill_time', 'N/A'),
                            f"${row.get('TLT', 0):.2f}" if pd.notna(row.get('TLT')) else 'N/A',
                            f"${row.get('IEF', 0):.2f}" if pd.notna(row.get('IEF')) else 'N/A',
                            f"${row.get('IEI', 0):.2f}" if pd.notna(row.get('IEI')) else 'N/A',
                            f"${row.get('PFF', 0):.2f}" if pd.notna(row.get('PFF')) else 'N/A',
                            f"${row.get('SHY', 0):.2f}" if pd.notna(row.get('SHY')) else 'N/A'
                        )
                        self.jdata_tree.insert('', 'end', values=values)
                                print(f"[JDATALOG] ✅ Fallback ile {len(df)} fill kaydı yüklendi")
                else:
                    print(f"[JDATALOG] ⚠️ {self.jdatalog_file} bulunamadı")
                    else:
                        print(f"[JDATALOG] ❌ getTransactions başarısız: {resp}")
                        
                except Exception as e:
                    print(f"[JDATALOG] ❌ getTransactions hatası: {e}")
                    # Fallback: Mevcut CSV'yi oku
                    if os.path.exists(self.jdatalog_file):
                        df = pd.read_csv(self.jdatalog_file)
                        for _, row in df.iterrows():
                            values = (
                                row.get('fill_qty', 'N/A'),
                                row.get('symbol', 'N/A'), 
                                f"${row.get('fill_price', 0):.2f}",
                                row.get('fill_time', 'N/A'),
                                f"${row.get('TLT', 0):.2f}" if pd.notna(row.get('TLT')) else 'N/A',
                                f"${row.get('IEF', 0):.2f}" if pd.notna(row.get('IEF')) else 'N/A',
                                f"${row.get('IEI', 0):.2f}" if pd.notna(row.get('IEI')) else 'N/A',
                                f"${row.get('PFF', 0):.2f}" if pd.notna(row.get('PFF')) else 'N/A',
                                f"${row.get('SHY', 0):.2f}" if pd.notna(row.get('SHY')) else 'N/A'
                            )
                            self.jdata_tree.insert('', 'end', values=values)
                        print(f"[JDATALOG] ✅ Fallback ile {len(df)} fill kaydı yüklendi")
                
            except Exception as e:
                print(f"[JDATALOG] ❌ JDataLog yenileme hatası: {e}")
                messagebox.showerror("Hata", f"JDataLog yenilenemedi: {e}")
        
        def cancel_selected_orders(self):
            """Seçili emirleri iptal et"""
            try:
                selected_items = []
                for item in self.pending_tree.get_children():
                    values = self.pending_tree.item(item)['values']
                    if values[0] == '☑':  # Seçili
                        selected_items.append((item, values[1]))  # (item, order_id)
                
                if not selected_items:
                    messagebox.showwarning("Uyarı", "Hiç emir seçilmedi!")
                    return
                
                # Onay al
                if not messagebox.askyesno("Onay", f"{len(selected_items)} emir iptal edilecek. Devam edilsin mi?"):
                    return
                
                success_count = 0
                for item, order_id in selected_items:
                    try:
                        if self.hammer and self.hammer.connected:
                            success = self.hammer.trade_command_cancel("ALARIC:TOPI002240A7", order_id)
                            if success:
                                success_count += 1
                                self.pending_tree.delete(item)
                                print(f"[CANCEL] ✅ Emir iptal edildi: {order_id}")
                            else:
                                print(f"[CANCEL] ❌ Emir iptal edilemedi: {order_id}")
                    except Exception as e:
                        print(f"[CANCEL] ❌ Emir iptal hatası ({order_id}): {e}")
                
                messagebox.showinfo("Sonuç", f"{success_count} emir başarıyla iptal edildi.")
                
            except Exception as e:
                print(f"[CANCEL] ❌ Seçili emirleri iptal etme hatası: {e}")
                messagebox.showerror("Hata", f"Emirler iptal edilemedi: {e}")
        
        def export_jdatalog(self):
            """JDataLog'u CSV olarak export et"""
            try:
                if os.path.exists(self.jdatalog_file):
                    import shutil
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    export_file = f"jdatalog_export_{timestamp}.csv"
                    shutil.copy2(self.jdatalog_file, export_file)
                    messagebox.showinfo("Export Başarılı", f"JDataLog export edildi: {export_file}")
                    print(f"[EXPORT] ✅ JDataLog export edildi: {export_file}")
                else:
                    messagebox.showwarning("Uyarı", "JDataLog dosyası bulunamadı!")
            except Exception as e:
                print(f"[EXPORT] ❌ Export hatası: {e}")
                messagebox.showerror("Hata", f"Export işlemi başarısız: {e}")
        
        def get_etf_prices_at_fill_time(self, fill_time):
            """Fill anındaki ETF fiyatlarını Hammer Pro'dan çek"""
            try:
                # Fill time'ı parse et
                if isinstance(fill_time, str):
                    try:
                        from datetime import datetime
                        # ISO format: 2025-08-21T14:08:16.000
                        if 'T' in fill_time:
                            dt = datetime.fromisoformat(fill_time.replace('Z', '+00:00'))
                        else:
                            dt = datetime.strptime(fill_time, "%Y-%m-%d %H:%M:%S")
                        
                        # 5 dakikalık bar için timestamp hesapla
                        import time
                        timestamp = int(dt.timestamp())
                        print(f"[ETF] 🔍 Fill time: {fill_time} -> Timestamp: {timestamp}")
                    except Exception as e:
                        print(f"[ETF] ⚠️ Fill time parse hatası: {e}")
                        return {'TLT': 0.0, 'IEF': 0.0, 'IEI': 0.0, 'PFF': 0.0, 'SHY': 0.0}
                else:
                    timestamp = int(fill_time)
                
                # ETF sembolleri
                etf_symbols = ['TLT', 'IEF', 'IEI', 'PFF', 'SHY']
                etf_prices = {}
                
                for symbol in etf_symbols:
                    try:
                        print(f"[ETF] 🔍 {symbol} için historical data çekiliyor...")
                        
                        # Hammer Pro'dan historical data çek
                        resp = self.hammer._send_and_wait({
                            "cmd": "getHistoricalData",
                            "symbol": symbol,
                            "interval": "5m",  # 5 dakikalık bar
                            "startTime": timestamp - 300,  # 5 dakika önce
                            "endTime": timestamp + 300,    # 5 dakika sonra
                            "maxBars": 10
                        }, timeout=10.0)
                        
                        print(f"[ETF] 📥 {symbol} historical data yanıtı: {resp}")
                        
                        if resp and resp.get('success') == 'OK':
                            result = resp.get('result', {})
                            print(f"[ETF] 🔍 {symbol} result: {result}")
                            
                            if isinstance(result, dict) and 'bars' in result:
                                bars = result.get('bars', [])
                                print(f"[ETF] 📊 {symbol} bars sayısı: {len(bars)}")
                                
                                if bars:
                                    # Fill time'a en yakın bar'ı bul
                                    closest_bar = None
                                    min_diff = float('inf')
                                    
                                    for bar in bars:
                                        bar_time = bar.get('time', 0)
                                        time_diff = abs(bar_time - timestamp)
                                        if time_diff < min_diff:
                                            min_diff = time_diff
                                            closest_bar = bar
                                    
                                    if closest_bar:
                                        # Close price'ı al
                                        close_price = closest_bar.get('close', 0.0)
                                        etf_prices[symbol] = close_price
                                        print(f"[ETF] ✅ {symbol}: ${close_price:.2f} (historical data)")
                                    else:
                                        etf_prices[symbol] = 0.0
                                        print(f"[ETF] ⚠️ {symbol}: Bar bulunamadı")
                                else:
                                    etf_prices[symbol] = 0.0
                                    print(f"[ETF] ⚠️ {symbol}: Hiç bar yok")
                            else:
                                etf_prices[symbol] = 0.0
                                print(f"[ETF] ⚠️ {symbol}: Result formatı hatalı")
                        else:
                            print(f"[ETF] ⚠️ {symbol}: Historical data başarısız, getCandles deneniyor...")
                            etf_prices[symbol] = 0.0
                            
                        # Historical data başarısızsa getCandles ile 5 dakikalık bar'ları dene
                        if etf_prices[symbol] == 0.0:
                            try:
                                print(f"[ETF] 🔄 {symbol}: getCandles ile 5 dakikalık bar'lar deneniyor...")
                                
                                # Fill anından 5 dakika önce ve sonra
                                start_time = timestamp - 300  # 5 dakika önce
                                end_time = timestamp + 300    # 5 dakika sonra
                                
                                # ISO format'a çevir
                                from datetime import datetime
                                start_date = datetime.fromtimestamp(start_time).strftime("%Y-%m-%dT%H:%M:%S")
                                end_date = datetime.fromtimestamp(end_time).strftime("%Y-%m-%dT%H:%M:%S")
                                
                                # getCandles komutu gönder
                                candles_resp = self.hammer._send_and_wait({
                                    "cmd": "getCandles",
                                    "sym": symbol,
                                    "candleSize": 5,  # 5 dakikalık bar'lar
                                    "startDate": start_date,
                                    "endDate": end_date,
                                    "regHoursOnly": False
                                }, timeout=10.0)
                                
                                if candles_resp and candles_resp.get('success') == 'OK':
                                    candles_result = candles_resp.get('result', {})
                                    if isinstance(candles_result, dict) and 'data' in candles_result:
                                        candles = candles_result.get('data', [])
                                        if candles:
                                            # Fill anına en yakın bar'ı bul
                                            closest_candle = None
                                            min_diff = float('inf')
                                            
                                            for candle in candles:
                                                candle_time_str = candle.get('t', '')
                                                if candle_time_str:
                                                    try:
                                                        # ISO timestamp'i parse et
                                                        candle_dt = datetime.fromisoformat(candle_time_str.replace('Z', '+00:00'))
                                                        candle_timestamp = int(candle_dt.timestamp())
                                                        time_diff = abs(candle_timestamp - timestamp)
                                                        
                                                        if time_diff < min_diff:
                                                            min_diff = time_diff
                                                            closest_candle = candle
                                                    except:
                                                        continue
                                            
                                            if closest_candle:
                                                # Close price'ı al
                                                close_price = closest_candle.get('c', 0.0)
                                                if close_price > 0:
                                                    etf_prices[symbol] = close_price
                                                    print(f"[ETF] ✅ {symbol}: ${close_price:.2f} (5m candle - {closest_candle.get('t')})")
                                                else:
                                                    print(f"[ETF] ⚠️ {symbol}: Candle close price 0")
                                            else:
                                                print(f"[ETF] ⚠️ {symbol}: En yakın candle bulunamadı")
                                        else:
                                            print(f"[ETF] ⚠️ {symbol}: Hiç candle yok")
                                    else:
                                        print(f"[ETF] ⚠️ {symbol}: Candles result formatı hatalı")
                                else:
                                    print(f"[ETF] ⚠️ {symbol}: getCandles başarısız")
                                    
                            except Exception as e:
                                print(f"[ETF] ❌ {symbol}: getCandles hatası: {e}")
                                
                        # Hala 0 ise fallback olarak sabit değerler
                        if etf_prices[symbol] == 0.0:
                            fallback_prices = {
                                'TLT': 95.50,  # Varsayılan ETF fiyatları
                                'IEF': 105.20,
                                'IEI': 108.75,
                                'PFF': 18.90,
                                'SHY': 82.15
                            }
                            etf_prices[symbol] = fallback_prices.get(symbol, 0.0)
                            print(f"[ETF] ⚠️ {symbol}: Fallback fiyat kullanıldı: ${etf_prices[symbol]:.2f}")
                            
                    except Exception as e:
                        print(f"[ETF] ❌ {symbol} historical data hatası: {e}")
                        etf_prices[symbol] = 0.0
                
                print(f"[ETF] 📊 ETF fiyatları: {etf_prices}")
                return etf_prices
                
            except Exception as e:
                print(f"[ETF] ❌ ETF fiyatları çekme hatası: {e}")
                return {'TLT': 0.0, 'IEF': 0.0, 'IEI': 0.0, 'PFF': 0.0, 'SHY': 0.0}
        
        def update_missing_etf_data(self):
            """Eksik ETF verilerini güncelle - Fill time'daki fiyatları çek"""
            try:
                if not os.path.exists(self.jdatalog_file):
                    messagebox.showwarning("Uyarı", "JDataLog dosyası bulunamadı!")
                    return
                
                print("[ETF_UPDATE] 🚀 Eksik ETF verileri güncelleniyor...")
                
                df = pd.read_csv(self.jdatalog_file)
                updated_count = 0
                
                for index, row in df.iterrows():
                    symbol = row.get('symbol', '')
                    fill_time = row.get('fill_time', '')
                    
                    # ETF verilerinden herhangi biri eksik mi? (0.0 veya NaN)
                    etf_missing = False
                    for etf in ['TLT', 'IEF', 'IEI', 'PFF', 'SHY']:
                        etf_value = row.get(etf, 0.0)
                        if pd.isna(etf_value) or float(etf_value) == 0.0:
                            etf_missing = True
                            break
                    
                    if etf_missing and fill_time:
                        print(f"[ETF_UPDATE] 🔍 {symbol} için ETF verileri eksik, fill time: {fill_time}")
                        
                        # Fill time'daki ETF fiyatlarını çek
                        etf_prices = self.get_etf_prices_at_fill_time(fill_time)
                        print(f"[ETF_UPDATE] 📊 {symbol} ETF fiyatları: {etf_prices}")
                        
                        # ETF verilerini güncelle
                        for etf, price in etf_prices.items():
                            if price > 0:  # Sadece geçerli fiyatları güncelle
                                df.at[index, etf] = price
                                        updated_count += 1
                                print(f"[ETF_UPDATE] ✅ {symbol} {etf}: ${price:.2f}")
                
                # Güncellenmiş verileri kaydet
                if updated_count > 0:
                    df.to_csv(self.jdatalog_file, index=False)
                    messagebox.showinfo("Güncelleme Başarılı", f"{updated_count} ETF verisi güncellendi!")
                    self.refresh_jdatalog()  # Tabloyu yenile
                    print(f"[ETF_UPDATE] ✅ Toplam {updated_count} ETF verisi güncellendi")
                else:
                    messagebox.showinfo("Bilgi", "Güncellenecek eksik ETF verisi bulunamadı.")
                    print("[ETF_UPDATE] ℹ️ Güncellenecek eksik ETF verisi bulunamadı")
                
            except Exception as e:
                print(f"[ETF_UPDATE] ❌ ETF güncelleme hatası: {e}")
                messagebox.showerror("Hata", f"ETF verileri güncellenemedi: {e}")
        
        def log_fill_data(self, symbol, qty, price, fill_time_str):
            """Fill verisini JDataLog'a kaydet"""
            try:
                # ETF verilerini şu an için çek
                etf_data = {}
                if self.hammer and self.hammer.connected:
                    for etf in self.etf_symbols:
                        market_data = self.hammer.get_market_data(etf)
                        if market_data:
                            etf_data[etf] = float(market_data.get('last', 0))
                        else:
                            etf_data[etf] = None
                
                # Yeni veri satırı
                new_row = {
                    'fill_qty': qty,
                    'symbol': symbol,
                    'fill_price': price,
                    'fill_time': fill_time_str,
                    'TLT': etf_data.get('TLT'),
                    'IEF': etf_data.get('IEF'),
                    'IEI': etf_data.get('IEI'),
                    'PFF': etf_data.get('PFF'),
                    'SHY': etf_data.get('SHY')
                }
                
                # CSV dosyasına ekle
                if os.path.exists(self.jdatalog_file):
                    df = pd.read_csv(self.jdatalog_file)
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                else:
                    df = pd.DataFrame([new_row])
                
                df.to_csv(self.jdatalog_file, index=False)
                print(f"[JDATALOG] ✅ Fill verisi kaydedildi: {qty} {symbol} @ ${price}")
                
            except Exception as e:
                print(f"[JDATALOG] ❌ Fill verisi kaydetme hatası: {e}")
    
    # OrderTracker'ı başlat
    tracker = OrderTracker(win, hammer_client)
    
    # Sekmeleri kur
    tracker.setup_pending_tab(pending_frame)
    tracker.setup_completed_tab(completed_frame)
    tracker.setup_jdatalog_tab(jdatalog_frame)
    
    # UI kurulumu tamamlandıktan sonra otomatik yenilemeyi başlat
    tracker.start_auto_refresh()
    
    # İlk veri yüklemeleri
    tracker.refresh_pending_orders()
    tracker.refresh_completed_orders()
    tracker.refresh_jdatalog()
    
    # Pending sekmesinde checkbox toggle fonksiyonu
    def toggle_select(event):
        """Checkbox'ı toggle et"""
        try:
            item = tracker.pending_tree.selection()[0]
            values = list(tracker.pending_tree.item(item)['values'])
            if values[0] == '☐':
                values[0] = '☑'
            else:
                values[0] = '☐'
            tracker.pending_tree.item(item, values=values)
        except:
            pass
    
    tracker.pending_tree.bind('<Button-1>', toggle_select)
    
    # Pencere kapanınca cleanup yap
    def on_window_close():
        """Pencere kapanınca OrderTracker'ı temizle"""
        try:
            print("[ORDERS] 🚪 Pencere kapanıyor, cleanup başlatılıyor...")
            tracker.cleanup()
            print("[ORDERS] ✅ Cleanup tamamlandı, pencere kapatılıyor...")
            
            # Pencereyi zorla kapat
            win.quit()
            win.destroy()
            
        except Exception as e:
            print(f"[ORDERS] ❌ Cleanup hatası: {e}")
            # Hata olsa bile pencereyi kapat
            try:
                win.quit()
                win.destroy()
            except:
                pass
    
    # Pencere kapanma event'ini yakala
    win.protocol("WM_DELETE_WINDOW", on_window_close)