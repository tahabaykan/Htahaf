import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import pandas as pd
import time
import logging
from datetime import datetime

# Import our modules
try:
    from data.market_data import MarketDataManager
    from config import Config
    from gui.connection_dialog import ConnectionDialog
except ImportError:
    from .data.market_data import MarketDataManager
    from .config import Config
    from .gui.connection_dialog import ConnectionDialog

class LongShortPanel(ttk.Frame):
    def __init__(self, parent, market_data):
        super().__init__(parent)
        self.market_data = market_data
        self.lbl_long = tk.Label(self, text="", fg="green", font=("Arial", 12, "bold"))
        self.lbl_short = tk.Label(self, text="", fg="red", font=("Arial", 12, "bold"))
        self.lbl_long.pack(side="left", padx=10)
        self.lbl_short.pack(side="left", padx=10)
        self.update_panel()

    def update_panel(self):
        positions = self.market_data.get_positions()
        long_qty = sum(pos.get('quantity', 0) for pos in positions if pos.get('quantity', 0) > 0)
        short_qty = sum(-pos.get('quantity', 0) for pos in positions if pos.get('quantity', 0) < 0)
        long_exp = sum(pos.get('quantity', 0) * pos.get('avgCost', 0) for pos in positions if pos.get('quantity', 0) > 0)
        short_exp = sum(-pos.get('quantity', 0) * pos.get('avgCost', 0) for pos in positions if pos.get('quantity', 0) < 0)
        self.lbl_long.config(text=f"Long: {long_qty:,} ({long_exp/1000:.1f}K USD)")
        self.lbl_short.config(text=f"Short: {short_qty:,} ({short_exp/1000:.1f}K USD)")
        self.after(2000, self.update_panel)

class SMAPanel(ttk.Frame):
    def __init__(self, parent, market_data):
        super().__init__(parent)
        self.market_data = market_data
        self.lbl_sma = tk.Label(self, text="", font=("Arial", 12, "bold"))
        self.lbl_sma.pack(side="left", padx=10)
        self.update_panel()

    def update_panel(self):
        # Calculate SMA values from market data
        all_data = self.market_data.get_all_market_data()
        if all_data:
            prices = [data.get('price', 0) for data in all_data.values() if data.get('price', 0) > 0]
            if prices:
                sma = sum(prices) / len(prices)
                self.lbl_sma.config(text=f"SMA: {sma:.2f}")
        self.after(5000, self.update_panel)

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Initialize configuration
        self.config = Config()
        
        # Initialize market data manager
        self.market_data = MarketDataManager()
        
        # Window setup
        self.title("Hammer Pro Stock Tracker")
        
        # Load window size from config
        gui_config = self.config.get_gui_config()
        width = gui_config.get('window_width', 1400)
        height = gui_config.get('window_height', 800)
        self.geometry(f"{width}x{height}")
        
        # Data variables
        self.current_page = 0
        self.items_per_page = gui_config.get('items_per_page', 50)
        self.current_data_type = 'historical'
        self.live_data_enabled = False
        self.auto_data_enabled = False
        
        # Setup UI
        self.setup_ui()
        
        # Start data update thread
        self.start_data_thread()
    
    def setup_ui(self):
        """Setup the main UI"""
        # Main frame
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Top control panel
        self.setup_control_panel(main_frame)
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True, pady=(10, 0))
        
        # Create tabs
        self.create_historical_tab()
        self.create_extended_tab()
        self.create_mastermind_tab()
        self.create_befday_tab()
        
        # Status bar
        self.setup_status_bar(main_frame)
    
    def setup_control_panel(self, parent):
        """Setup the control panel"""
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill="x", pady=(0, 10))
        
        # Connection controls
        conn_frame = ttk.LabelFrame(control_frame, text="Hammer Pro Connection")
        conn_frame.pack(side="left", padx=(0, 10))
        
        self.btn_settings = ttk.Button(conn_frame, text="Ayarlar", command=self.show_connection_settings)
        self.btn_settings.pack(side="left", padx=5)
        
        self.btn_connect = ttk.Button(conn_frame, text="Bağlan", command=self.connect_hammer_pro)
        self.btn_connect.pack(side="left", padx=5)
        
        self.btn_disconnect = ttk.Button(conn_frame, text="Bağlantıyı Kes", command=self.disconnect_hammer_pro)
        self.btn_disconnect.pack(side="left", padx=5)
        
        # Data controls
        data_frame = ttk.LabelFrame(control_frame, text="Data Controls")
        data_frame.pack(side="left", padx=(0, 10))
        
        self.btn_live_data = ttk.Button(data_frame, text="Toggle Live Data", command=self.toggle_live_data)
        self.btn_live_data.pack(side="left", padx=5)
        
        self.btn_update_once = ttk.Button(data_frame, text="Update Once", command=self.update_data_once)
        self.btn_update_once.pack(side="left", padx=5)
        
        # Status indicators
        status_frame = ttk.LabelFrame(control_frame, text="Status")
        status_frame.pack(side="right")
        
        self.lbl_connection = tk.Label(status_frame, text="Bağlantı Yok", fg="red", font=("Arial", 10, "bold"))
        self.lbl_connection.pack(side="left", padx=5)
        
        self.lbl_live_data = tk.Label(status_frame, text="Canlı: KAPALI", fg="red", font=("Arial", 10, "bold"))
        self.lbl_live_data.pack(side="left", padx=5)
    
    def setup_status_bar(self, parent):
        """Setup the status bar"""
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill="x", pady=(10, 0))
        
        # Long/Short panel
        self.long_short_panel = LongShortPanel(status_frame, self.market_data)
        self.long_short_panel.pack(side="left")
        
        # SMA panel
        self.sma_panel = SMAPanel(status_frame, self.market_data)
        self.sma_panel.pack(side="left")
        
        # Page info
        self.lbl_page_info = tk.Label(status_frame, text="", font=("Arial", 10))
        self.lbl_page_info.pack(side="right")
    
    def create_historical_tab(self):
        """Create the historical data tab"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Historical")
        
        # Table
        self.historical_table = self.create_table(frame)
        
        # Navigation
        nav_frame = ttk.Frame(frame)
        nav_frame.pack(fill="x", pady=(10, 0))
        
        self.create_nav(nav_frame, self.prev_historical, self.next_historical)
    
    def create_extended_tab(self):
        """Create the extended data tab"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Extended")
        
        # Table
        self.extended_table = self.create_table(frame)
        
        # Navigation
        nav_frame = ttk.Frame(frame)
        nav_frame.pack(fill="x", pady=(10, 0))
        
        self.create_nav(nav_frame, self.prev_extended, self.next_extended)
    
    def create_mastermind_tab(self):
        """Create the mastermind data tab"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Mastermind")
        
        # Table
        self.mastermind_table = self.create_table(frame)
        
        # Navigation
        nav_frame = ttk.Frame(frame)
        nav_frame.pack(fill="x", pady=(10, 0))
        
        self.create_nav(nav_frame, self.prev_mastermind, self.next_mastermind)
    
    def create_befday_tab(self):
        """Create the befday data tab"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Befday")
        
        # Table
        self.befday_table = self.create_table(frame)
        
        # Navigation
        nav_frame = ttk.Frame(frame)
        nav_frame.pack(fill="x", pady=(10, 0))
        
        self.create_nav(nav_frame, self.prev_befday, self.next_befday)
    
    def create_table(self, parent):
        """Create a data table"""
        # Create Treeview
        columns = ('Symbol', 'Price', 'Bid', 'Ask', 'Size', 'Volume', 'Change', 'Change%')
        tree = ttk.Treeview(parent, columns=columns, show='headings', height=20)
        
        # Configure columns
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=100)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        return tree
    
    def create_nav(self, parent, prev_cmd, next_cmd):
        """Create navigation buttons"""
        btn_prev = ttk.Button(parent, text="Previous", command=prev_cmd)
        btn_prev.pack(side="left", padx=5)
        
        btn_next = ttk.Button(parent, text="Next", command=next_cmd)
        btn_next.pack(side="left", padx=5)
    
    def show_connection_settings(self):
        """Show connection settings dialog"""
        dialog = ConnectionDialog(self, self.config, self.on_connection_settings_connect)
        self.wait_window(dialog)
    
    def on_connection_settings_connect(self, host, port, password, streamer_id):
        """Handle connection from settings dialog"""
        try:
            # Update market data manager with new settings
            if self.market_data.connect(host, port, password):
                self.lbl_connection.config(text="Bağlandı", fg="green")
                self.logger.info("Connected to Hammer Pro")
                
                # Start data streamer with configured ID
                self.market_data.start_data_streamer(streamer_id)
                
                # Update UI
                self.update_tables()
            else:
                messagebox.showerror("Bağlantı Hatası", "Hammer Pro'ya bağlanılamadı")
        except Exception as e:
            messagebox.showerror("Bağlantı Hatası", f"Hammer Pro'ya bağlanırken hata: {e}")
    
    def connect_hammer_pro(self):
        """Connect to Hammer Pro using saved settings"""
        try:
            hammer_config = self.config.get_hammer_pro_config()
            host = hammer_config.get('host', '127.0.0.1')
            port = hammer_config.get('port', 8080)
            password = hammer_config.get('password', '')
            streamer_id = hammer_config.get('streamer_id', 'AMTD')
            
            if self.market_data.connect(host, port, password):
                self.lbl_connection.config(text="Bağlandı", fg="green")
                self.logger.info("Connected to Hammer Pro")
                
                # Start data streamer
                self.market_data.start_data_streamer(streamer_id)
                
                # Update UI
                self.update_tables()
            else:
                messagebox.showerror("Bağlantı Hatası", "Hammer Pro'ya bağlanılamadı. Ayarları kontrol edin.")
        except Exception as e:
            messagebox.showerror("Bağlantı Hatası", f"Hammer Pro'ya bağlanırken hata: {e}")
    
    def disconnect_hammer_pro(self):
        """Disconnect from Hammer Pro"""
        try:
            self.market_data.disconnect()
            self.lbl_connection.config(text="Bağlantı Yok", fg="red")
            self.logger.info("Disconnected from Hammer Pro")
        except Exception as e:
            self.logger.error(f"Error disconnecting: {e}")
    
    def toggle_live_data(self):
        """Toggle live data updates"""
        self.live_data_enabled = not self.live_data_enabled
        
        if self.live_data_enabled:
            self.lbl_live_data.config(text="Canlı: AÇIK", fg="green")
            self.logger.info("Live data enabled")
        else:
            self.lbl_live_data.config(text="Canlı: KAPALI", fg="red")
            self.logger.info("Live data disabled")
    
    def update_data_once(self):
        """Update data once"""
        self.update_tables()
    
    def update_tables(self):
        """Update all tables with current data"""
        # Update based on current tab
        current_tab = self.notebook.select()
        tab_id = self.notebook.index(current_tab)
        
        if tab_id == 0:  # Historical
            self.update_historical_table()
        elif tab_id == 1:  # Extended
            self.update_extended_table()
        elif tab_id == 2:  # Mastermind
            self.update_mastermind_table()
        elif tab_id == 3:  # Befday
            self.update_befday_table()
    
    def update_historical_table(self):
        """Update historical table"""
        tickers = self.market_data.get_historical_tickers(
            self.current_page * self.items_per_page,
            (self.current_page + 1) * self.items_per_page
        )
        self.update_table(self.historical_table, tickers)
        self.update_page_info('historical')
    
    def update_extended_table(self):
        """Update extended table"""
        tickers = self.market_data.get_extended_tickers(
            self.current_page * self.items_per_page,
            (self.current_page + 1) * self.items_per_page
        )
        self.update_table(self.extended_table, tickers)
        self.update_page_info('extended')
    
    def update_mastermind_table(self):
        """Update mastermind table"""
        tickers = self.market_data.get_mastermind_tickers(
            self.current_page * self.items_per_page,
            (self.current_page + 1) * self.items_per_page
        )
        self.update_table(self.mastermind_table, tickers)
        self.update_page_info('mastermind')
    
    def update_befday_table(self):
        """Update befday table"""
        tickers = self.market_data.get_befday_tickers(
            self.current_page * self.items_per_page,
            (self.current_page + 1) * self.items_per_page
        )
        self.update_table(self.befday_table, tickers)
        self.update_page_info('befday')
    
    def update_table(self, table, tickers):
        """Update a table with ticker data"""
        # Clear existing items
        for item in table.get_children():
            table.delete(item)
        
        # Subscribe to market data for these tickers
        if self.market_data.is_connected():
            self.market_data.subscribe_page_tickers(tickers)
        
        # Add data to table
        for ticker in tickers:
            if ticker:
                market_data = self.market_data.get_market_data(ticker)
                
                price = market_data.get('price', 0)
                bid = market_data.get('bid', 0)
                ask = market_data.get('ask', 0)
                size = market_data.get('size', 0)
                volume = market_data.get('volume', 0)
                timestamp = market_data.get('timestamp', '')
                
                # Calculate change (placeholder)
                change = 0
                change_pct = 0
                
                # Color coding based on data availability
                if price > 0:
                    # Live data available
                    price_color = "green"
                    status = "LIVE"
                else:
                    # No live data
                    price_color = "gray"
                    status = "CSV"
                
                item = table.insert('', 'end', values=(
                    ticker,
                    f"{price:.2f}" if price else "N/A",
                    f"{bid:.2f}" if bid else "N/A",
                    f"{ask:.2f}" if ask else "N/A",
                    f"{size:,.0f}" if size else "N/A",
                    f"{volume:,.0f}" if volume else "N/A",
                    f"{change:+.2f}" if change else "N/A",
                    f"{change_pct:+.2f}%" if change_pct else "N/A"
                ))
                
                # Color the row based on data status
                if price > 0:
                    table.set(item, 'Symbol', f"{ticker} ({status})")
                    table.item(item, tags=('live',))
                else:
                    table.item(item, tags=('csv',))
        
        # Configure row colors
        table.tag_configure('live', background='lightgreen')
        table.tag_configure('csv', background='lightgray')
    
    def update_page_info(self, data_type):
        """Update page information"""
        max_pages = self.market_data.get_max_pages(data_type, self.items_per_page)
        self.lbl_page_info.config(text=f"Page {self.current_page + 1} of {max_pages + 1}")
    
    def prev_historical(self):
        """Go to previous page in historical tab"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_historical_table()
    
    def next_historical(self):
        """Go to next page in historical tab"""
        max_pages = self.market_data.get_max_pages('historical', self.items_per_page)
        if self.current_page < max_pages:
            self.current_page += 1
            self.update_historical_table()
    
    def prev_extended(self):
        """Go to previous page in extended tab"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_extended_table()
    
    def next_extended(self):
        """Go to next page in extended tab"""
        max_pages = self.market_data.get_max_pages('extended', self.items_per_page)
        if self.current_page < max_pages:
            self.current_page += 1
            self.update_extended_table()
    
    def prev_mastermind(self):
        """Go to previous page in mastermind tab"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_mastermind_table()
    
    def next_mastermind(self):
        """Go to next page in mastermind tab"""
        max_pages = self.market_data.get_max_pages('mastermind', self.items_per_page)
        if self.current_page < max_pages:
            self.current_page += 1
            self.update_mastermind_table()
    
    def prev_befday(self):
        """Go to previous page in befday tab"""
        if self.current_page > 0:
            self.current_page -= 1
            self.update_befday_table()
    
    def next_befday(self):
        """Go to next page in befday tab"""
        max_pages = self.market_data.get_max_pages('befday', self.items_per_page)
        if self.current_page < max_pages:
            self.current_page += 1
            self.update_befday_table()
    
    def start_data_thread(self):
        """Start the data update thread"""
        def update_loop():
            while True:
                if self.live_data_enabled and self.market_data.is_connected():
                    # Update tables in main thread
                    self.after(0, self.update_tables)
                time.sleep(2)  # Update every 2 seconds
        
        thread = threading.Thread(target=update_loop, daemon=True)
        thread.start()
    
    def on_closing(self):
        """Handle window closing"""
        if self.market_data.is_connected():
            self.market_data.disconnect()
        self.destroy() 