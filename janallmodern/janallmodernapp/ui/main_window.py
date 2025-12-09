"""
Main Window - Modernized UI Component

This is the main application window with modern UI/UX.
Business logic is separated into controller classes.

!!! IMPORTANT FILE PATH WARNING !!!
===================================
ALL CSV READING AND WRITING OPERATIONS MUST BE DONE TO StockTracker DIRECTORY!!
NOT TO StockTracker/janall/ DIRECTORY!!
TO PREVENT CONFUSION, THIS RULE MUST BE STRICTLY FOLLOWED!

Example:
✅ CORRECT: "janalldata.csv" (in StockTracker directory)
❌ WRONG: "janall/janalldata.csv"
===================================
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import os
from typing import Optional, Dict, List, Any

# Import modern theme (optional)
try:
    from .theme import ModernTheme
except ImportError:
    ModernTheme = None

# Import UI components
from .etf_panel import ETFPanel


class MainWindow(tk.Tk):
    """
    Main application window with modern UI.
    
    This class handles UI setup and delegates business logic to controllers.
    """
    
    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        
        # Configure window
        self.title("JanAllModern")
        self.geometry("1400x900")
        
        # Apply modern theme (optional - can work without it)
        try:
            from .theme import ModernTheme
            self.theme = ModernTheme()
            self.style = self.theme.configure_styles()
        except ImportError:
            # Fallback if theme not available
            self.theme = None
            self.style = None
        
        # Initialize controllers (to be implemented)
        # self.main_controller = MainController(self)
        # self.table_controller = TableController(self)
        # self.order_controller = OrderController(self)
        # self.benchmark_controller = BenchmarkController(self)
        
        # Initialize services
        from ..services.hammer_client import HammerClient
        self.hammer = HammerClient(
            host='127.0.0.1',
            port=16400,
            password='Nl201090.',
            main_window=self
        )
        
        # IBKR clients (optional - can be None if not needed)
        self.ibkr = None
        self.ibkr_native = None
        try:
            from ..services.ibkr_client import IBKRClient
            self.ibkr = IBKRClient(
                host='127.0.0.1',
                port=4001,
                client_id=1,
                main_window=self
            )
        except ImportError:
            print("[INFO] IBKR client not available")
        
        try:
            from ..services.ibkr_native_client import IBKRNativeClient
            self.ibkr_native = IBKRNativeClient(
                host='127.0.0.1',
                port=4001,
                client_id=2,
                main_window=self
            )
        except ImportError:
            print("[INFO] IBKR Native client not available")
        
        # Initialize mode manager
        from ..core.mode_manager import ModeManager
        self.mode_manager = ModeManager(
            hammer_client=self.hammer,
            ibkr_client=self.ibkr,
            ibkr_native_client=self.ibkr_native,
            main_window=self
        )
        
        # Initialize managers
        from ..core.order_management import OrderManager
        from ..core.bdata_storage import BDataStorage
        from ..core.stock_data_manager import StockDataManager
        from ..core.exception_manager import ExceptionListManager
        
        self.order_manager = OrderManager(self)
        self.bdata_storage = BDataStorage()
        self.stock_data_manager = StockDataManager()
        self.exception_manager = ExceptionListManager("exception_list.csv")
        
        # Live data flag
        self.live_data_running = False
        
        # ETF panel (will be created in setup_ui)
        self.etf_panel = None
        
        # Data storage
        self.df = pd.DataFrame()
        self.tickers = []
        
        # Pagination
        self.items_per_page = 15
        self.current_page = 0
        self.total_pages = 0
        
        # Sorting
        self.sort_column = None
        self.sort_ascending = True
        
        # Setup UI
        self.setup_ui()
        
        # Load main CSV on startup
        self.load_main_csv_on_startup()
    
    def setup_ui(self):
        """
        Setup the modern UI layout.
        
        This method creates all UI components with modern styling.
        """
        # Top frame - Connection and main buttons
        top_frame = ttk.Frame(self)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        # Connection buttons
        connection_frame = ttk.Frame(top_frame)
        connection_frame.pack(side='left', padx=2)
        
        self.btn_connect = ttk.Button(
            connection_frame,
            text="Hammer Pro'ya Bağlan",
            command=self.connect_hammer
        )
        self.btn_connect.pack(side='left', padx=2)
        
        self.btn_live = ttk.Button(
            connection_frame,
            text="Live Data Başlat",
            command=self.toggle_live_data
        )
        self.btn_live.pack(side='left', padx=2)
        
        self.btn_prev_close = ttk.Button(
            connection_frame,
            text="Prev Close Çek",
            command=self.fetch_all_prev_close
        )
        self.btn_prev_close.pack(side='left', padx=2)
        
        # Right side buttons
        right_frame = ttk.Frame(top_frame)
        right_frame.pack(side='right', padx=2)
        
        # BDATA buttons
        bdata_frame = ttk.Frame(right_frame)
        bdata_frame.pack(side='left', padx=1)
        
        self.btn_bdata_export = ttk.Button(
            bdata_frame,
            text="BDATA Export",
            command=self.export_bdata,
            width=12
        )
        self.btn_bdata_export.pack(side='left', padx=1)
        
        self.btn_befday_export = ttk.Button(
            bdata_frame,
            text="BEFDAY Export",
            command=self.export_befday,
            width=12
        )
        self.btn_befday_export.pack(side='left', padx=1)
        
        self.btn_bdata_clear = ttk.Button(
            bdata_frame,
            text="BDATA Clear",
            command=self.clear_bdata,
            width=12
        )
        self.btn_bdata_clear.pack(side='left', padx=1)
        
        # Exception List button
        self.btn_exception_list = ttk.Button(
            bdata_frame,
            text="Exception List",
            command=self.open_exception_list,
            width=12
        )
        self.btn_exception_list.pack(side='left', padx=1)
        
        # ETF Panel
        etf_frame = ttk.LabelFrame(self, text="ETF Panel")
        etf_frame.pack(fill='x', padx=5, pady=2)
        self.etf_panel = ETFPanel(etf_frame, self.hammer)
        self.etf_panel.pack(fill='x', padx=5, pady=5)
        
        # Order buttons frame
        order_frame = ttk.Frame(self)
        order_frame.pack(fill='x', padx=5, pady=2)
        
        # Order buttons
        self.btn_bid_buy = ttk.Button(order_frame, text="Bid Buy", 
                                     command=lambda: self.order_manager.place_order_for_selected('bid_buy'), width=10)
        self.btn_bid_buy.pack(side='left', padx=1)
        
        self.btn_front_buy = ttk.Button(order_frame, text="Front Buy", 
                                       command=lambda: self.order_manager.place_order_for_selected('front_buy'), width=10)
        self.btn_front_buy.pack(side='left', padx=1)
        
        self.btn_ask_buy = ttk.Button(order_frame, text="Ask Buy", 
                                     command=lambda: self.order_manager.place_order_for_selected('ask_buy'), width=10)
        self.btn_ask_buy.pack(side='left', padx=1)
        
        self.btn_ask_sell = ttk.Button(order_frame, text="Ask Sell", 
                                      command=lambda: self.order_manager.place_order_for_selected('ask_sell'), width=10)
        self.btn_ask_sell.pack(side='left', padx=1)
        
        self.btn_front_sell = ttk.Button(order_frame, text="Front Sell", 
                                        command=lambda: self.order_manager.place_order_for_selected('front_sell'), width=10)
        self.btn_front_sell.pack(side='left', padx=1)
        
        self.btn_soft_front_buy = ttk.Button(order_frame, text="SoftFront Buy", 
                                           command=lambda: self.order_manager.place_order_for_selected('soft_front_buy'), width=12)
        self.btn_soft_front_buy.pack(side='left', padx=1)
        
        self.btn_soft_front_sell = ttk.Button(order_frame, text="SoftFront Sell", 
                                            command=lambda: self.order_manager.place_order_for_selected('soft_front_sell'), width=12)
        self.btn_soft_front_sell.pack(side='left', padx=1)
        
        self.btn_bid_sell = ttk.Button(order_frame, text="Bid Sell", 
                                      command=lambda: self.order_manager.place_order_for_selected('bid_sell'), width=10)
        self.btn_bid_sell.pack(side='left', padx=1)
        
        # Lot entry
        lot_frame = ttk.Frame(self)
        lot_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(lot_frame, text="Lot:").pack(side='left', padx=2)
        self.lot_entry = ttk.Entry(lot_frame, width=8)
        self.lot_entry.pack(side='left', padx=2)
        self.lot_entry.insert(0, "200")
        
        # Main table
        table_frame = ttk.Frame(self)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Table columns (will be populated from CSV)
        self.columns = ['Select']
        
        # Create table with modern styling
        self.table = ttk.Treeview(
            table_frame,
            columns=self.columns,
            show='headings',
            height=15,
            style='Modern.Treeview'
        )
        
        # Configure columns
        for col in self.columns:
            self.table.heading(col, text=col)
            self.table.column(col, width=100, anchor='center')
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(table_frame, orient='vertical', 
                                   command=self.table.yview)
        h_scrollbar = ttk.Scrollbar(table_frame, orient='horizontal', 
                                   command=self.table.xview)
        self.table.configure(yscrollcommand=v_scrollbar.set,
                            xscrollcommand=h_scrollbar.set)
        
        # Pack scrollbars and table
        self.table.pack(side='left', fill='both', expand=True)
        v_scrollbar.pack(side='right', fill='y')
        h_scrollbar.pack(side='bottom', fill='x')
        
        # Pagination controls
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill='x', padx=5, pady=2)
        
        self.btn_prev = ttk.Button(
            nav_frame,
            text="< Previous",
            command=self.prev_page
        )
        self.btn_prev.pack(side='left', padx=2)
        
        self.lbl_page = ttk.Label(
            nav_frame,
            text="Page 1 / 1"
        )
        self.lbl_page.pack(side='left', padx=5)
        
        self.btn_next = ttk.Button(
            nav_frame,
            text="Next >",
            command=self.next_page
        )
        self.btn_next.pack(side='left', padx=2)
    
    def load_main_csv_on_startup(self):
        """Load main CSV file on application startup."""
        try:
            csv_file = 'janalldata.csv'
            if os.path.exists(csv_file):
                print(f"[STARTUP] Loading main CSV file: {csv_file}")
                self.show_file_data(csv_file, is_main=True)
                print(f"[STARTUP] ✅ Main CSV file loaded: {len(self.df)} stocks")
            else:
                print(f"[STARTUP] ⚠️ Main CSV file not found: {csv_file}")
        except Exception as e:
            print(f"[STARTUP] ERROR Loading main CSV: {e}")
    
    def show_file_data(self, filename: str, is_main: bool = False):
        """
        Show data from a CSV file in the table.
        
        Args:
            filename: CSV file name
            is_main: Whether this is the main data file
        """
        try:
            if not os.path.exists(filename):
                print(f"[CSV] ERROR Dosya bulunamadı: {filename}")
                return
            
            # CSV'yi oku
            df = pd.read_csv(filename)
            
            if df.empty:
                print(f"[CSV] WARNING Dosya boş: {filename}")
                return
            
            # CSV'den sadece belirli kolonları al
            csv_columns_to_show = ['PREF IBKR', 'prev_close', 'CMON', 'CGRUP', 'FINAL_THG', 'AVG_ADV', 'SMI', 'SMA63 chg', 'SMA246 chg', 'SMA 246 CHG', 'SHORT_FINAL']
            
            # Sadece mevcut kolonları al (yoksa hata vermesin)
            available_columns = [col for col in csv_columns_to_show if col in df.columns]
            
            # Skor kolonları (kendi hesapladığımız)
            score_columns = [
                'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
                'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru',
                'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor', 'Final_SAS_skor', 'Final_SFS_skor', 'Final_SBS_skor',
                'Spread'
            ]
            
            # Benchmark kolonları
            benchmark_columns = ['Benchmark_Type', 'Benchmark_Chg']
            
            # GORT kolonu
            gort_columns = ['GORT']
            
            # Live kolonları (Hammer Pro'dan)
            live_columns = ['Bid', 'Ask', 'Last', 'Volume']
            
            # Toplam kolon sırası
            self.columns = ['Select'] + available_columns + score_columns + benchmark_columns + gort_columns + live_columns
            
            # Tabloyu yeniden oluştur
            if hasattr(self, 'table'):
                self.table.destroy()
            
            # Table frame'i bul
            table_frame = None
            for widget in self.winfo_children():
                if isinstance(widget, ttk.Frame):
                    for child in widget.winfo_children():
                        if isinstance(child, ttk.Treeview):
                            table_frame = widget
                            break
                    if table_frame:
                        break
            
            if not table_frame:
                # Table frame bulunamadı, yeni oluştur
                table_frame = ttk.Frame(self)
                table_frame.pack(fill='both', expand=True, padx=5, pady=5)
            
            # Yeni tablo oluştur
            self.table = ttk.Treeview(table_frame, columns=self.columns, show='headings', height=15)
            
            # Kolon başlıkları ve genişlikleri
            for col in self.columns:
                self.table.heading(col, text=col)
                if col == 'Select':
                    self.table.column(col, width=50, anchor='center')
                elif col == 'PREF IBKR':
                    self.table.column(col, width=100, anchor='w')
                else:
                    self.table.column(col, width=80, anchor='center')
            
            # Scrollbars
            v_scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
            h_scrollbar = ttk.Scrollbar(table_frame, orient='horizontal', command=self.table.xview)
            self.table.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
            
            # Pack
            self.table.pack(side='left', fill='both', expand=True)
            v_scrollbar.pack(side='right', fill='y')
            h_scrollbar.pack(side='bottom', fill='x')
            
            # Ticker'ları al
            if 'PREF IBKR' in df.columns:
                self.tickers = df['PREF IBKR'].dropna().tolist()
            else:
                self.tickers = []
            
            # Sayfalama ayarlarını güncelle
            self.current_page = 0
            self.total_pages = max(1, (len(self.tickers) + self.items_per_page - 1) // self.items_per_page)
            
            # Yeni verileri göster
            self.df = df
            
            # Live data için tüm sembollere subscribe ol
            if is_main and self.hammer.connected:
                print(f"\n[HAMMER] 🔄 {len(self.tickers)} sembole subscribe olunuyor...")
                for ticker in self.tickers:
                    if ticker:
                        self.hammer.subscribe_symbol(ticker)
            
            # Tabloyu güncelle
            self.update_table()
            
            # Başlığı güncelle
            if is_main:
                self.title("JanAllModern - Tüm Veriler")
            else:
                short_name = os.path.basename(filename).replace('.csv', '')
                self.title(f"JanAllModern - {short_name}")
            
            print(f"[CSV] ✅ {filename} yüklendi: {len(df)} satır")
            
        except Exception as e:
            print(f"[CSV] ERROR Dosya okuma hatası ({filename}): {e}")
            import traceback
            traceback.print_exc()
    
    def connect_hammer(self):
        """Hammer Pro'ya bağlan/bağlantıyı kes"""
        if not self.hammer.connected:
            print("\n[HAMMER] OK Hammer Pro'ya baglaniliyor...")
            print(f"[HAMMER] OK Host: {self.hammer.host}")
            print(f"[HAMMER] OK Port: {self.hammer.port}")
            
            if self.hammer.connect():
                self.btn_connect.config(text="Bağlantıyı Kes")
                print("[HAMMER] OK Baglanti basarili!")
            else:
                print("[HAMMER] ERROR Baglanti basarisiz!")
                print("[HAMMER] INFO Kontrol edilecekler:")
                print("   1. Hammer Pro çalışıyor mu?")
                print("   2. Port numarası doğru mu?")
                print("   3. API şifresi doğru mu?")
        else:
            print("\n[HAMMER] OK Baglanti kesiliyor...")
            self.hammer.disconnect()
            self.btn_connect.config(text="Hammer Pro'ya Bağlan")
            print("[HAMMER] OK Baglanti kesildi.")
    
    def toggle_live_data(self):
        """Live data akışını başlat/durdur"""
        if not self.live_data_running:
            # Önce janalldata.csv'yi yükle ve tüm sembollere subscribe ol
            self.show_file_data('janalldata.csv', is_main=True)
            
            # ETF panel varsa subscribe et
            if self.etf_panel:
                print("\n[ETF] OK ETF'ler icin L1 streaming baslatiliyor...")
                self.etf_panel.subscribe_etfs()
            
            self.live_data_running = True
            self.btn_live.config(text="Live Data Durdur")
            
            # ETF verilerini güncelleme döngüsünü başlat
            if self.etf_panel:
                self.update_etf_data()
            
            # Ana tabloyu güncelleme döngüsünü başlat
            self.update_live_data()
        else:
            self.live_data_running = False
            self.btn_live.config(text="Live Data Başlat")
    
    def update_etf_data(self):
        """ETF verilerini güncelle"""
        if not self.live_data_running or not self.etf_panel:
            return
        
        try:
            # ETF panel'den market data al ve güncelle
            for etf in getattr(self.etf_panel, 'etf_list', []):
                market_data = self.hammer.get_market_data(etf)
                if market_data:
                    self.etf_panel.update_etf_data(etf, market_data)
            
            # Display'i güncelle
            self.etf_panel.update_etf_display()
            
            # 1 saniye sonra tekrar güncelle
            self.after(1000, self.update_etf_data)
        except Exception as e:
            print(f"[ETF] ERROR ETF güncelleme hatası: {e}")
            if self.live_data_running:
                self.after(1000, self.update_etf_data)
    
    def update_live_data(self):
        """Ana tablo verilerini güncelle"""
        if not self.live_data_running:
            return
        
        try:
            # Tablodaki tüm sembollere subscribe ol ve verileri güncelle
            if hasattr(self, 'table') and self.df is not None and not self.df.empty:
                # Her satır için market data al
                for item in self.table.get_children():
                    ticker = self.table.set(item, 'PREF IBKR')
                    if ticker:
                        market_data = self.hammer.get_market_data(ticker)
                        if market_data:
                            # Verileri güncelle (bu kısım daha sonra geliştirilecek)
                            pass
            
            # 1 saniye sonra tekrar güncelle
            self.after(1000, self.update_live_data)
        except Exception as e:
            print(f"[LIVE DATA] ERROR Güncelleme hatası: {e}")
            if self.live_data_running:
                self.after(1000, self.update_live_data)
    
    def export_bdata(self):
        """BDATA export"""
        try:
            self.bdata_storage.export_to_csv()
            messagebox.showinfo("Başarılı", "BDATA CSV'leri oluşturuldu!")
        except Exception as e:
            messagebox.showerror("Hata", f"BDATA export hatası: {e}")
    
    def export_befday(self):
        """BEFDAY export"""
        try:
            summary = self.bdata_storage.get_position_summary_with_snapshot()
            self.bdata_storage.create_befday_csv(summary)
            messagebox.showinfo("Başarılı", "BEFDAY CSV oluşturuldu!")
        except Exception as e:
            messagebox.showerror("Hata", f"BEFDAY export hatası: {e}")
    
    def clear_bdata(self):
        """BDATA temizle"""
        if messagebox.askyesno("Onay", "Tüm BDATA verilerini temizlemek istediğinizden emin misiniz?"):
            self.bdata_storage.clear_all_data()
            messagebox.showinfo("Başarılı", "BDATA verileri temizlendi!")
    
    def open_exception_list(self):
        """Exception list penceresini aç"""
        from ..ui.exception_window import ExceptionListWindow
        ExceptionListWindow(self, self.exception_manager)
    
    def fetch_all_prev_close(self):
        """Prev close çek - KALDIRILDI"""
        print("[PREV CLOSE] 🚫 PREV CLOSE ÇEKME İŞLEMİ TAMAMEN KALDIRILDI!")
        print("[PREV CLOSE] 🚫 Streaming veri kullanılacak, prev close çekilmeyecek!")
        messagebox.showinfo("Bilgi", "Prev Close çekme işlemi kaldırıldı. Streaming veri kullanılıyor.")
    
    def check_exception_tickers(self, ticker_list):
        """
        Verilen ticker listesinde exception olanları kontrol eder.
        
        Args:
            ticker_list: Kontrol edilecek ticker listesi
            
        Returns:
            tuple: (allowed_tickers, exception_tickers, message)
        """
        allowed_tickers, exception_tickers = self.exception_manager.filter_exception_tickers(ticker_list)
        
        if exception_tickers:
            message = f"Exception listesinde bulunan hisseler: {', '.join(exception_tickers)}"
        else:
            message = "Tüm hisseler trade edilebilir."
        
        return allowed_tickers, exception_tickers, message
    
    def get_last_price_for_symbol(self, symbol):
        """Symbol için son fiyatı al"""
        try:
            market_data = self.hammer.get_market_data(symbol)
            if market_data:
                return float(market_data.get('last', 0))
            return 0.0
        except Exception as e:
            print(f"[PRICE] ERROR {symbol} fiyat alma hatası: {e}")
            return 0.0
    
    def prev_page(self):
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_table()
    
    def next_page(self):
        """Go to next page."""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_table()
    
    def update_table(self):
        """Update the table with current page data."""
        if not hasattr(self, 'df') or self.df is None or self.df.empty:
            return
        
        # Tabloyu temizle
        for item in self.table.get_children():
            self.table.delete(item)
        
        # Sayfa bilgisini güncelle
        if hasattr(self, 'lbl_page'):
            self.lbl_page.config(
                text=f"Page {self.current_page + 1} / {self.total_pages}"
            )
        
        # Mevcut sayfadaki verileri göster
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.df))
        
        for idx in range(start_idx, end_idx):
            row = self.df.iloc[idx]
            values = []
            
            # Her kolon için değer al
            for col in self.columns:
                if col == 'Select':
                    values.append('☐')  # Checkbox placeholder
                elif col in self.df.columns:
                    val = row[col]
                    if pd.isna(val):
                        values.append('')
                    else:
                        values.append(str(val))
                else:
                    values.append('')
            
            # Satırı ekle
            self.table.insert('', 'end', values=values)

