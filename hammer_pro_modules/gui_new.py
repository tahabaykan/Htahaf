"""
Hammer Pro GUI Module - Market Data Integration
Ana kullanıcı arayüzü - Gerçek zamanlı market data ile
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import asyncio
import threading
import logging
from typing import Optional
from connection import HammerProConnection
from watchlist_manager import HammerProWatchlistManager
from layout_manager import HammerProLayoutManager
from market_data_manager import HammerProMarketDataManager
from csv_handler import HammerProCSVHandler
from config import HammerProConfig

class HammerProGUI:
    """Hammer Pro Ana GUI Sınıfı - Market Data Integration"""
    
    def __init__(self):
        """GUI'yi başlat"""
        self.setup_logging()
        self.setup_components()
        self.setup_gui()
        
    def setup_logging(self):
        """Logging ayarları"""
        log_config = HammerProConfig.LOG_SETTINGS
        logging.basicConfig(
            level=getattr(logging, log_config["level"]),
            format=log_config["format"],
            handlers=[
                logging.FileHandler(log_config["file"]),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_components(self):
        """Bileşenleri başlat"""
        # Bağlantı
        self.connection = HammerProConnection()
        
        # Watchlist manager
        self.watchlist_manager = HammerProWatchlistManager(self.connection)
        
        # Layout manager
        self.layout_manager = HammerProLayoutManager(self.connection)
        
        # Market data manager
        self.market_data_manager = HammerProMarketDataManager(self.connection)
        
        # CSV handler
        self.csv_handler = HammerProCSVHandler()
        
        # Durum değişkenleri
        self.connected = False
        self.csv_loaded = False
        
    def setup_gui(self):
        """GUI'yi kur"""
        self.root = tk.Tk()
        self.root.title("Hammer Pro FINAL BB Integration")
        self.root.geometry("1200x800")
        
        # Ana frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill='both', expand=True)
        
        # Başlık
        ttk.Label(main_frame, text="Hammer Pro FINAL BB Integration", 
                 font=("Arial", 16, "bold")).pack(pady=(0, 20))
        
        # Notebook (tabbed interface)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill='both', expand=True)
        
        # Tabları oluştur
        self.setup_connection_tab()
        self.setup_csv_tab()
        self.setup_market_data_tab()
        self.setup_watchlist_tab()
        self.setup_layout_tab()
        self.setup_status_tab()
        
    def setup_connection_tab(self):
        """Bağlantı tab'ı"""
        conn_frame = ttk.Frame(self.notebook)
        self.notebook.add(conn_frame, text="Bağlantı")
        
        # Bağlantı ayarları
        settings_frame = ttk.LabelFrame(conn_frame, text="Hammer Pro Bağlantı Ayarları")
        settings_frame.pack(fill='x', padx=10, pady=10)
        
        # Host
        ttk.Label(settings_frame, text="Host:").grid(row=0, column=0, padx=5, pady=5)
        self.host_var = tk.StringVar(value=HammerProConfig.DEFAULT_HOST)
        ttk.Entry(settings_frame, textvariable=self.host_var).grid(row=0, column=1, padx=5, pady=5)
        
        # Port
        ttk.Label(settings_frame, text="Port:").grid(row=1, column=0, padx=5, pady=5)
        self.port_var = tk.StringVar(value=str(HammerProConfig.DEFAULT_PORT))
        ttk.Entry(settings_frame, textvariable=self.port_var).grid(row=1, column=1, padx=5, pady=5)
        
        # Şifre
        ttk.Label(settings_frame, text="Şifre:").grid(row=2, column=0, padx=5, pady=5)
        self.password_var = tk.StringVar()
        ttk.Entry(settings_frame, textvariable=self.password_var, show="*").grid(row=2, column=1, padx=5, pady=5)
        
        # Bağlantı butonları
        btn_frame = ttk.Frame(conn_frame)
        btn_frame.pack(pady=10)
        
        self.connect_btn = ttk.Button(btn_frame, text="Bağlan", command=self.connect_to_hammer)
        self.connect_btn.pack(side='left', padx=5)
        
        self.disconnect_btn = ttk.Button(btn_frame, text="Bağlantıyı Kes", command=self.disconnect_from_hammer, state='disabled')
        self.disconnect_btn.pack(side='left', padx=5)
        
        # Durum
        self.conn_status_label = ttk.Label(conn_frame, text="Durum: Bağlantı Yok", foreground="red")
        self.conn_status_label.pack(pady=10)
        
    def setup_csv_tab(self):
        """CSV tab'ı"""
        csv_frame = ttk.Frame(self.notebook)
        self.notebook.add(csv_frame, text="CSV Dosyası")
        
        # CSV seçimi
        csv_select_frame = ttk.LabelFrame(csv_frame, text="CSV Dosya Seçimi")
        csv_select_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Label(csv_select_frame, text="CSV Dosyası:").pack(anchor='w', padx=5, pady=2)
        
        file_frame = ttk.Frame(csv_select_frame)
        file_frame.pack(fill='x', padx=5, pady=2)
        
        self.csv_path_var = tk.StringVar(value=HammerProConfig.CSV_SETTINGS["default_file"])
        ttk.Entry(file_frame, textvariable=self.csv_path_var, width=60).pack(side='left', fill='x', expand=True)
        ttk.Button(file_frame, text="Dosya Seç", command=self.select_csv_file).pack(side='right', padx=5)
        
        ttk.Button(csv_select_frame, text="CSV'yi Yükle", command=self.load_csv_data).pack(pady=5)
        
        # CSV bilgileri
        info_frame = ttk.LabelFrame(csv_frame, text="CSV Bilgileri")
        info_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Treeview için CSV bilgileri
        self.csv_info_tree = ttk.Treeview(info_frame, columns=('Property', 'Value'), show='headings', height=10)
        self.csv_info_tree.heading('Property', text='Özellik')
        self.csv_info_tree.heading('Value', text='Değer')
        self.csv_info_tree.column('Property', width=200)
        self.csv_info_tree.column('Value', width=300)
        self.csv_info_tree.pack(fill='both', expand=True, padx=5, pady=5)
        
    def setup_market_data_tab(self):
        """Market Data tab'ı"""
        market_frame = ttk.Frame(self.notebook)
        self.notebook.add(market_frame, text="Market Data")
        
        # Market data işlemleri
        market_ops_frame = ttk.LabelFrame(market_frame, text="Market Data İşlemleri")
        market_ops_frame.pack(fill='x', padx=10, pady=10)
        
        # Butonlar
        btn_frame = ttk.Frame(market_ops_frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Market Data Güncelle", command=self.update_market_data).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="FINAL BB Skorları Hesapla", command=self.calculate_final_bb_scores).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Gerçek Zamanlı Abone Ol", command=self.subscribe_realtime).pack(side='left', padx=5)
        
        # Market data sonuçları
        result_frame = ttk.LabelFrame(market_frame, text="Market Data Sonuçları")
        result_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Treeview için market data sonuçları
        self.market_result_tree = ttk.Treeview(result_frame, 
            columns=('Symbol', 'Bid', 'Ask', 'Last', 'Volume', 'FINAL_THG', 'FINAL_BB'), 
            show='headings', height=15)
        self.market_result_tree.heading('Symbol', text='Sembol')
        self.market_result_tree.heading('Bid', text='Bid')
        self.market_result_tree.heading('Ask', text='Ask')
        self.market_result_tree.heading('Last', text='Last')
        self.market_result_tree.heading('Volume', text='Volume')
        self.market_result_tree.heading('FINAL_THG', text='FINAL_THG')
        self.market_result_tree.heading('FINAL_BB', text='FINAL_BB')
        self.market_result_tree.column('Symbol', width=100)
        self.market_result_tree.column('Bid', width=80)
        self.market_result_tree.column('Ask', width=80)
        self.market_result_tree.column('Last', width=80)
        self.market_result_tree.column('Volume', width=100)
        self.market_result_tree.column('FINAL_THG', width=100)
        self.market_result_tree.column('FINAL_BB', width=100)
        self.market_result_tree.pack(fill='both', expand=True, padx=5, pady=5)
        
    def setup_watchlist_tab(self):
        """Watchlist tab'ı"""
        watchlist_frame = ttk.Frame(self.notebook)
        self.notebook.add(watchlist_frame, text="Watchlist")
        
        # Watchlist oluşturma
        create_frame = ttk.LabelFrame(watchlist_frame, text="Watchlist Oluşturma")
        create_frame.pack(fill='x', padx=10, pady=10)
        
        # Watchlist adı
        ttk.Label(create_frame, text="Watchlist Adı:").pack(anchor='w', padx=5, pady=2)
        self.watchlist_name_var = tk.StringVar(value="SSFI_HELD_KUPONLU")
        ttk.Entry(create_frame, textvariable=self.watchlist_name_var, width=40).pack(anchor='w', padx=5, pady=2)
        
        # Watchlist türü
        ttk.Label(create_frame, text="Watchlist Türü:").pack(anchor='w', padx=5, pady=2)
        self.watchlist_type_var = tk.StringVar(value="all")
        type_frame = ttk.Frame(create_frame)
        type_frame.pack(anchor='w', padx=5, pady=2)
        
        ttk.Radiobutton(type_frame, text="Tüm Semboller", 
                       variable=self.watchlist_type_var, value="all").pack(side='left', padx=5)
        ttk.Radiobutton(type_frame, text="En Yüksek FINAL_BB", 
                       variable=self.watchlist_type_var, value="top_final_bb").pack(side='left', padx=5)
        ttk.Radiobutton(type_frame, text="En Düşük FINAL_BB", 
                       variable=self.watchlist_type_var, value="bottom_final_bb").pack(side='left', padx=5)
        
        # Maksimum sembol sayısı
        ttk.Label(create_frame, text="Maksimum Sembol Sayısı:").pack(anchor='w', padx=5, pady=2)
        self.max_symbols_var = tk.StringVar(value="50")
        ttk.Entry(create_frame, textvariable=self.max_symbols_var, width=10).pack(anchor='w', padx=5, pady=2)
        
        # Oluştur butonu
        ttk.Button(create_frame, text="Watchlist Oluştur", command=self.create_watchlist).pack(pady=10)
        
        # Sonuçlar
        result_frame = ttk.LabelFrame(watchlist_frame, text="Sonuçlar")
        result_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Treeview için sonuçlar
        self.result_tree = ttk.Treeview(result_frame, columns=('Symbol', 'FINAL_THG', 'FINAL_BB', 'Company', 'Status'), show='headings', height=15)
        self.result_tree.heading('Symbol', text='Sembol')
        self.result_tree.heading('FINAL_THG', text='FINAL_THG')
        self.result_tree.heading('FINAL_BB', text='FINAL_BB')
        self.result_tree.heading('Company', text='Şirket')
        self.result_tree.heading('Status', text='Durum')
        self.result_tree.column('Symbol', width=100)
        self.result_tree.column('FINAL_THG', width=100)
        self.result_tree.column('FINAL_BB', width=100)
        self.result_tree.column('Company', width=150)
        self.result_tree.column('Status', width=100)
        self.result_tree.pack(fill='both', expand=True, padx=5, pady=5)
        
    def setup_layout_tab(self):
        """Layout tab'ı"""
        layout_frame = ttk.Frame(self.notebook)
        self.notebook.add(layout_frame, text="Layout")
        
        # Layout oluşturma
        create_frame = ttk.LabelFrame(layout_frame, text="Layout Oluşturma")
        create_frame.pack(fill='x', padx=10, pady=10)
        
        # Layout adı
        ttk.Label(create_frame, text="Layout Adı:").pack(anchor='w', padx=5, pady=2)
        self.layout_name_var = tk.StringVar(value="SSFI_HELD_KUPONLU_LAYOUT")
        ttk.Entry(create_frame, textvariable=self.layout_name_var, width=40).pack(anchor='w', padx=5, pady=2)
        
        # Layout türü
        ttk.Label(create_frame, text="Layout Türü:").pack(anchor='w', padx=5, pady=2)
        self.layout_type_var = tk.StringVar(value="top_final_bb")
        type_frame = ttk.Frame(create_frame)
        type_frame.pack(anchor='w', padx=5, pady=2)
        
        ttk.Radiobutton(type_frame, text="En Yüksek FINAL_BB (20 sembol)", 
                       variable=self.layout_type_var, value="top_final_bb").pack(side='left', padx=5)
        ttk.Radiobutton(type_frame, text="En Düşük FINAL_BB (20 sembol)", 
                       variable=self.layout_type_var, value="bottom_final_bb").pack(side='left', padx=5)
        ttk.Radiobutton(type_frame, text="Tüm Semboller (20 sembol)", 
                       variable=self.layout_type_var, value="all").pack(side='left', padx=5)
        
        # Layout butonları
        btn_frame = ttk.Frame(create_frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Layout Oluştur", command=self.create_layout).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Layout Yükle", command=self.load_layout).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Layout Kaydet", command=self.save_layout).pack(side='left', padx=5)
        
        # Layout sonuçları
        result_frame = ttk.LabelFrame(layout_frame, text="Layout Sonuçları")
        result_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Treeview için layout sonuçları
        self.layout_result_tree = ttk.Treeview(result_frame, columns=('Symbol', 'FINAL_THG', 'FINAL_BB', 'Company', 'Status'), show='headings', height=15)
        self.layout_result_tree.heading('Symbol', text='Sembol')
        self.layout_result_tree.heading('FINAL_THG', text='FINAL_THG')
        self.layout_result_tree.heading('FINAL_BB', text='FINAL_BB')
        self.layout_result_tree.heading('Company', text='Şirket')
        self.layout_result_tree.heading('Status', text='Durum')
        self.layout_result_tree.column('Symbol', width=100)
        self.layout_result_tree.column('FINAL_THG', width=100)
        self.layout_result_tree.column('FINAL_BB', width=100)
        self.layout_result_tree.column('Company', width=150)
        self.layout_result_tree.column('Status', width=100)
        self.layout_result_tree.pack(fill='both', expand=True, padx=5, pady=5)
        
    def setup_status_tab(self):
        """Durum tab'ı"""
        status_frame = ttk.Frame(self.notebook)
        self.notebook.add(status_frame, text="Durum")
        
        # Log görüntüleme
        log_frame = ttk.LabelFrame(status_frame, text="Log Mesajları")
        log_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Text widget için log
        self.log_text = tk.Text(log_frame, height=20, width=80)
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Scrollbar
        log_scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        log_scrollbar.pack(side='right', fill='y')
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        # Log handler ekle
        self.setup_log_handler()
        
    def setup_log_handler(self):
        """Log handler'ı GUI'ye bağla"""
        class TextHandler(logging.Handler):
            def __init__(self, text_widget):
                logging.Handler.__init__(self)
                self.text_widget = text_widget
                
            def emit(self, record):
                msg = self.format(record)
                self.text_widget.insert(tk.END, msg + '\n')
                self.text_widget.see(tk.END)
                
        handler = TextHandler(self.log_text)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(handler)
        
    def select_csv_file(self):
        """CSV dosyası seç"""
        filename = filedialog.askopenfilename(
            title="CSV Dosyası Seç",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            self.csv_path_var.set(filename)
            
    def load_csv_data(self):
        """CSV verilerini yükle"""
        try:
            csv_path = self.csv_path_var.get()
            success = self.csv_handler.load_csv(csv_path)
            
            if success:
                self.csv_loaded = True
                messagebox.showinfo("Başarılı", "CSV dosyası yüklendi!")
                self.update_csv_info()
            else:
                messagebox.showerror("Hata", "CSV dosyası yüklenemedi!")
                
        except Exception as e:
            messagebox.showerror("Hata", f"CSV yükleme hatası: {e}")
            
    def update_csv_info(self):
        """CSV bilgilerini güncelle"""
        # Treeview'i temizle
        for item in self.csv_info_tree.get_children():
            self.csv_info_tree.delete(item)
            
        # CSV bilgilerini al
        info = self.csv_handler.get_csv_info()
        if info:
            for key, value in info.items():
                if key == "final_thg_stats":
                    for stat_key, stat_value in value.items():
                        self.csv_info_tree.insert('', 'end', values=(f"FINAL_THG {stat_key}", f"{stat_value:.2f}"))
                else:
                    self.csv_info_tree.insert('', 'end', values=(key, value))
                    
    def update_market_data(self):
        """Market data güncelle"""
        if not self.connected:
            messagebox.showerror("Hata", "Hammer Pro'ya bağlı değilsiniz!")
            return
            
        if not self.csv_loaded:
            messagebox.showerror("Hata", "CSV dosyası yüklenmemiş!")
            return
            
        def update_thread():
            async def update():
                try:
                    # CSV'den sembolleri al
                    symbols = self.csv_handler.get_symbols_by_type("all", 50)
                    
                    # Market data güncelle
                    success = await self.market_data_manager.update_market_data_for_symbols(symbols)
                    
                    if success:
                        self.root.after(0, lambda: messagebox.showinfo("Başarılı", "Market data güncellendi!"))
                        self.root.after(0, lambda: self.update_market_data_tree())
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Hata", "Market data güncellenemedi!"))
                        
                except Exception as e:
                    self.logger.error(f"Market data güncelleme hatası: {e}")
                    self.root.after(0, lambda: messagebox.showerror("Hata", f"Market data güncelleme hatası: {e}"))
                    
            asyncio.run(update())
            
        threading.Thread(target=update_thread, daemon=True).start()
        
    def calculate_final_bb_scores(self):
        """FINAL BB skorları hesapla"""
        if not self.connected:
            messagebox.showerror("Hata", "Hammer Pro'ya bağlı değilsiniz!")
            return
            
        if not self.csv_loaded:
            messagebox.showerror("Hata", "CSV dosyası yüklenmemiş!")
            return
            
        def calculate_thread():
            async def calculate():
                try:
                    # FINAL BB skorları hesapla
                    scores = self.market_data_manager.calculate_final_bb_scores_batch(self.csv_handler.csv_data)
                    
                    if scores:
                        self.root.after(0, lambda: messagebox.showinfo("Başarılı", f"{len(scores)} FINAL BB skor hesaplandı!"))
                        self.root.after(0, lambda: self.update_market_data_tree())
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Hata", "FINAL BB skor hesaplanamadı!"))
                        
                except Exception as e:
                    self.logger.error(f"FINAL BB skor hesaplama hatası: {e}")
                    self.root.after(0, lambda: messagebox.showerror("Hata", f"FINAL BB skor hesaplama hatası: {e}"))
                    
            asyncio.run(calculate())
            
        threading.Thread(target=calculate_thread, daemon=True).start()
        
    def subscribe_realtime(self):
        """Gerçek zamanlı abone ol"""
        if not self.connected:
            messagebox.showerror("Hata", "Hammer Pro'ya bağlı değilsiniz!")
            return
            
        if not self.csv_loaded:
            messagebox.showerror("Hata", "CSV dosyası yüklenmemiş!")
            return
            
        def subscribe_thread():
            async def subscribe():
                try:
                    # CSV'den sembolleri al
                    symbols = self.csv_handler.get_symbols_by_type("all", 50)
                    
                    # Gerçek zamanlı abone ol
                    success = await self.market_data_manager.subscribe_to_symbols(symbols)
                    
                    if success:
                        self.root.after(0, lambda: messagebox.showinfo("Başarılı", "Gerçek zamanlı abone olundu!"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Hata", "Gerçek zamanlı abone olunamadı!"))
                        
                except Exception as e:
                    self.logger.error(f"Abone olma hatası: {e}")
                    self.root.after(0, lambda: messagebox.showerror("Hata", f"Abone olma hatası: {e}"))
                    
            asyncio.run(subscribe())
            
        threading.Thread(target=subscribe_thread, daemon=True).start()
        
    def update_market_data_tree(self):
        """Market data treeview'ini güncelle"""
        # Treeview'i temizle
        for item in self.market_result_tree.get_children():
            self.market_result_tree.delete(item)
            
        # Market data bilgilerini ekle
        for symbol, market_info in self.market_data_manager.symbol_data.items():
            final_thg = 0
            if self.csv_handler.csv_data is not None:
                symbol_data = self.csv_handler.get_symbol_data(symbol)
                if symbol_data:
                    final_thg = symbol_data.get('final_thg', 0)
            
            final_bb = self.market_data_manager.final_bb_scores.get(symbol, final_thg)
            
            self.market_result_tree.insert('', 'end', values=(
                symbol,
                f"{market_info.get('bid', 0):.2f}",
                f"{market_info.get('ask', 0):.2f}",
                f"{market_info.get('last', 0):.2f}",
                f"{market_info.get('volume', 0):,.0f}",
                f"{final_thg:.2f}",
                f"{final_bb:.2f}"
            ))
            
    def connect_to_hammer(self):
        """Hammer Pro'ya bağlan"""
        def connect_thread():
            async def connect():
                try:
                    # Bağlantı ayarlarını güncelle
                    self.connection.host = self.host_var.get()
                    self.connection.port = int(self.port_var.get())
                    self.connection.password = self.password_var.get()
                    
                    # Bağlan
                    success = await self.connection.connect()
                    
                    if success:
                        self.connected = True
                        self.root.after(0, self.update_connection_status, True)
                    else:
                        self.root.after(0, self.update_connection_status, False)
                        
                except Exception as e:
                    self.logger.error(f"Bağlantı hatası: {e}")
                    self.root.after(0, self.update_connection_status, False)
                    
            asyncio.run(connect())
            
        threading.Thread(target=connect_thread, daemon=True).start()
        
    def update_connection_status(self, connected: bool):
        """Bağlantı durumunu güncelle"""
        self.connected = connected
        
        if connected:
            self.conn_status_label.config(text="Durum: Bağlandı", foreground="green")
            self.connect_btn.config(state='disabled')
            self.disconnect_btn.config(state='normal')
        else:
            self.conn_status_label.config(text="Durum: Bağlantı Yok", foreground="red")
            self.connect_btn.config(state='normal')
            self.disconnect_btn.config(state='disabled')
            
    def disconnect_from_hammer(self):
        """Hammer Pro'dan bağlantıyı kes"""
        def disconnect_thread():
            async def disconnect():
                try:
                    await self.connection.disconnect()
                    self.root.after(0, self.update_connection_status, False)
                except Exception as e:
                    self.logger.error(f"Bağlantı kesme hatası: {e}")
                    
            asyncio.run(disconnect())
            
        threading.Thread(target=disconnect_thread, daemon=True).start()
        
    def create_watchlist(self):
        """Watchlist oluştur"""
        if not self.connected:
            messagebox.showerror("Hata", "Hammer Pro'ya bağlı değilsiniz!")
            return
            
        if not self.csv_loaded:
            messagebox.showerror("Hata", "CSV dosyası yüklenmemiş!")
            return
            
        def create_thread():
            async def create():
                try:
                    watchlist_name = self.watchlist_name_var.get()
                    watchlist_type = self.watchlist_type_var.get()
                    max_symbols = int(self.max_symbols_var.get())
                    
                    # Sembolleri al
                    symbols = self.csv_handler.get_symbols_by_type(watchlist_type, max_symbols)
                    
                    if not symbols:
                        self.root.after(0, lambda: messagebox.showerror("Hata", "Filtrelenmiş sembol bulunamadı!"))
                        return
                    
                    # Watchlist oluştur
                    success, created_symbols = await self.watchlist_manager.create_watchlist_from_csv(
                        self.csv_handler.csv_data, watchlist_name, watchlist_type, max_symbols
                    )
                    
                    if success:
                        self.root.after(0, lambda: messagebox.showinfo("Başarılı", f"Watchlist '{watchlist_name}' oluşturuldu!"))
                        self.root.after(0, lambda: self.update_result_tree(created_symbols))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Hata", "Watchlist oluşturulamadı!"))
                        
                except Exception as e:
                    self.logger.error(f"Watchlist oluşturma hatası: {e}")
                    self.root.after(0, lambda: messagebox.showerror("Hata", f"Watchlist oluşturma hatası: {e}"))
                    
            asyncio.run(create())
            
        threading.Thread(target=create_thread, daemon=True).start()
        
    def create_layout(self):
        """Layout oluştur"""
        if not self.connected:
            messagebox.showerror("Hata", "Hammer Pro'ya bağlı değilsiniz!")
            return
            
        if not self.csv_loaded:
            messagebox.showerror("Hata", "CSV dosyası yüklenmemiş!")
            return
            
        def create_thread():
            async def create():
                try:
                    layout_name = self.layout_name_var.get()
                    layout_type = self.layout_type_var.get()
                    
                    # Layout oluştur
                    success, created_symbols = await self.layout_manager.create_layout_from_csv(
                        self.csv_handler.csv_data, layout_name, layout_type, 20
                    )
                    
                    if success:
                        self.root.after(0, lambda: messagebox.showinfo("Başarılı", f"Layout '{layout_name}' oluşturuldu!"))
                        self.root.after(0, lambda: self.update_layout_result_tree(created_symbols))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Hata", "Layout oluşturulamadı!"))
                        
                except Exception as e:
                    self.logger.error(f"Layout oluşturma hatası: {e}")
                    self.root.after(0, lambda: messagebox.showerror("Hata", f"Layout oluşturma hatası: {e}"))
                    
            asyncio.run(create())
            
        threading.Thread(target=create_thread, daemon=True).start()
        
    def load_layout(self):
        """Layout yükle"""
        if not self.connected:
            messagebox.showerror("Hata", "Hammer Pro'ya bağlı değilsiniz!")
            return
            
        def load_thread():
            async def load():
                try:
                    layout_name = self.layout_name_var.get()
                    success = await self.layout_manager.load_layout(layout_name)
                    
                    if success:
                        self.root.after(0, lambda: messagebox.showinfo("Başarılı", f"Layout '{layout_name}' yüklendi!"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Hata", "Layout yüklenemedi!"))
                        
                except Exception as e:
                    self.logger.error(f"Layout yükleme hatası: {e}")
                    self.root.after(0, lambda: messagebox.showerror("Hata", f"Layout yükleme hatası: {e}"))
                    
            asyncio.run(load())
            
        threading.Thread(target=load_thread, daemon=True).start()
        
    def save_layout(self):
        """Layout kaydet"""
        if not self.connected:
            messagebox.showerror("Hata", "Hammer Pro'ya bağlı değilsiniz!")
            return
            
        def save_thread():
            async def save():
                try:
                    layout_name = self.layout_name_var.get()
                    success = await self.layout_manager.save_layout(layout_name)
                    
                    if success:
                        self.root.after(0, lambda: messagebox.showinfo("Başarılı", f"Layout '{layout_name}' kaydedildi!"))
                    else:
                        self.root.after(0, lambda: messagebox.showerror("Hata", "Layout kaydedilemedi!"))
                        
                except Exception as e:
                    self.logger.error(f"Layout kaydetme hatası: {e}")
                    self.root.after(0, lambda: messagebox.showerror("Hata", f"Layout kaydetme hatası: {e}"))
                    
            asyncio.run(save())
            
        threading.Thread(target=save_thread, daemon=True).start()
        
    def update_layout_result_tree(self, symbols: list):
        """Layout sonuç treeview'ini güncelle"""
        # Treeview'i temizle
        for item in self.layout_result_tree.get_children():
            self.layout_result_tree.delete(item)
            
        # Yeni sembolleri ekle
        for symbol in symbols:
            symbol_data = self.csv_handler.get_symbol_data(symbol)
            if symbol_data:
                final_bb = self.market_data_manager.final_bb_scores.get(symbol, symbol_data['final_thg'])
                self.layout_result_tree.insert('', 'end', values=(
                    symbol_data['symbol'],
                    f"{symbol_data['final_thg']:.2f}",
                    f"{final_bb:.2f}",
                    symbol_data['company'],
                    'Layout\'a Eklendi'
                ))
        
    def update_result_tree(self, symbols: list):
        """Sonuç treeview'ini güncelle"""
        # Treeview'i temizle
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
            
        # Yeni sembolleri ekle
        for symbol in symbols:
            symbol_data = self.csv_handler.get_symbol_data(symbol)
            if symbol_data:
                final_bb = self.market_data_manager.final_bb_scores.get(symbol, symbol_data['final_thg'])
                self.result_tree.insert('', 'end', values=(
                    symbol_data['symbol'],
                    f"{symbol_data['final_thg']:.2f}",
                    f"{final_bb:.2f}",
                    symbol_data['company'],
                    'Watchlist\'e Eklendi'
                ))
                
    def run(self):
        """GUI'yi çalıştır"""
        self.root.mainloop()
        
    def close(self):
        """GUI'yi kapat"""
        if self.connected:
            asyncio.run(self.connection.disconnect())
        self.root.destroy() 