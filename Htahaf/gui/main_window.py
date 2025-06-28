import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import pandas as pd
from Htahaf.ib_api.manager import PolygonMarketData
import time
from hammerib.gui.etf_panel import ETFPanel
from hammerib.gui.opt_buttons import create_opt_buttons
from hammerib.gui.benchmark_panel import BenchmarkPanel
from Htahaf.gui.maltopla_window import MaltoplaWindow
from hammerib.gui.pos_orders_buttons import create_pos_orders_buttons
from hammerib.gui.top_movers_buttons import create_top_movers_buttons
from hammerib.gui.orderable_table import OrderableTableFrame
from tb_modules.tb_data_management import sort_and_paginate_rows
import re
from hammerib.ib_api.manager import ETF_SYMBOLS
from Htahaf.gui.general_window import GeneralWindow
from Htahaf.utils.order_management import OrderManager
from ib_insync import LimitOrder
import os
import csv
from Htahaf.utils.bdata_storage import BDataStorage
from Htahaf.gui.orderbook_window import OrderBookWindow
from datetime import datetime
from Htahaf.utils.benchmark_calculator import BenchmarkCalculator
from Htahaf.psfalgo1_core import PsfAlgo1
from Htahaf.psfalgo2 import PsfAlgo2

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
        long_qty = sum(pos['quantity'] for pos in positions if pos['quantity'] > 0)
        short_qty = sum(-pos['quantity'] for pos in positions if pos['quantity'] < 0)
        long_exp = sum(pos['quantity'] * pos['avgCost'] for pos in positions if pos['quantity'] > 0)
        short_exp = sum(-pos['quantity'] * pos['avgCost'] for pos in positions if pos['quantity'] < 0)
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
        ib = getattr(self.market_data, 'ib', None)
        if ib and ib.isConnected():
            account_info = ib.accountSummary()
            sma_limit = next((item.value for item in account_info if item.tag == 'SMA'), 'N/A')
            sma_remaining = next((item.value for item in account_info if item.tag == 'SMA_Remaining'), 'N/A')
            self.lbl_sma.config(text=f"SMA Limit: {sma_limit}, Remaining: {sma_remaining}")
        else:
            self.lbl_sma.config(text="IBKR bağlantısı yok.")
        self.after(2000, self.update_panel)

def polygonize_ticker(symbol):
    symbol = str(symbol).strip()
    if ' PR' in symbol:
        base, pr = symbol.split(' PR', 1)
        return f"{base}p{pr.strip().upper()}"
    return symbol

def unpolygonize_ticker(symbol):
    m = re.match(r'^([A-Z]+)p([a-z]+)$', symbol)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    return symbol

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stock Tracker Modular")
        self.open_windows = []
        self.market_data = PolygonMarketData()
        # ETF WebSocket başlat ve spike callback bağla
        self.market_data.start_etf_stream(on_spike=self.on_etf_spike)
        # Hisse listelerini yeni CSV dosyalarından oku ve mapping oluştur
        self.historical_df = pd.read_csv('mastermind_histport.csv')
        self.extended_df = pd.read_csv('mastermind_extltport.csv')
        self.ticker_map = {}
        self.historical_tickers = []
        seen_hist = set()
        for _, row in self.historical_df.iterrows():
            orig = str(row['PREF IBKR']).strip()
            if orig not in seen_hist:
                poly = polygonize_ticker(orig)
                self.ticker_map[orig] = poly
                self.ticker_map[poly] = orig
                self.historical_tickers.append(orig)
                seen_hist.add(orig)
        self.extended_tickers = []
        seen_ext = set()
        for _, row in self.extended_df.iterrows():
            orig = str(row['PREF IBKR']).strip()
            if orig not in seen_ext:
                poly = polygonize_ticker(orig)
                self.ticker_map[orig] = poly
                self.ticker_map[poly] = orig
                self.extended_tickers.append(orig)
                seen_ext.add(orig)
        self.items_per_page = 17
        self.historical_page = 0
        self.extended_page = 0
        self.active_tab = 0  # 0: historical, 1: extended
        self.etf_panel = ETFPanel(self, ETF_SYMBOLS, compact=True)
        self.etf_panel.pack(fill='x', padx=5, pady=2)
        self.long_short_panel = LongShortPanel(self, self.market_data)
        self.long_short_panel.pack(fill='x', padx=5, pady=5)
        self.sma_panel = SMAPanel(self, self.market_data)
        self.sma_panel.pack(fill='x', padx=5, pady=5)
        self.loop_running = False
        self.loop_job = None
        self.exdiv_data = {}
        self.auto_data_running = False
        self.auto_data_job = None
        self.setup_ui()
        self.historical_benchmark = BenchmarkPanel(self.historical_frame)
        self.historical_benchmark.pack(fill='x', padx=5, pady=5)
        self.extended_benchmark = BenchmarkPanel(self.extended_frame)
        self.extended_benchmark.pack(fill='x', padx=5, pady=5)
        self.data_thread = None
        self.after(1000, self.update_tables)
        
        # --- T-pref benchmark katsayıları ---
        self.tpref_bench_coeffs = {
            'c400': (0.40, 0.20),
            'c425': (0.44, 0.19),
            'c450': (0.48, 0.18),
            'c475': (0.51, 0.16),
            'c500': (0.55, 0.15),
            'c525': (0.59, 0.14),
            'c550': (0.62, 0.12),
            'c575': (0.66, 0.11),
            'c600': (0.70, 0.10),
            'c625': (0.73, 0.09),
            'c650': (0.76, 0.08),
            'c675': (0.79, 0.07),
            'c700': (0.82, 0.06),
            'c725': (0.85, 0.05),
            'c750': (0.88, 0.04),
        }
        # Map T-pref ticker to CGRUP (benchmark group)
        self.tpref_cgrup_map = {}
        for _, row in self.historical_df.iterrows():
            ticker = str(row['PREF IBKR']).strip()
            cgrup = str(row['CGRUP']).strip().lower()
            self.tpref_cgrup_map[ticker] = cgrup
            
        # --- BDATA'yı mevcut IBKR pozisyonlarıyla başlat ---
        self.c_type_extra_tickers = set()
        for fname in ['ffextlt.csv', 'flrextlt.csv', 'maturextlt.csv', 'nffextlt.csv', 'duzextlt.csv']:
            try:
                df = pd.read_csv(fname)
                for _, row in df.iterrows():
                    ticker = str(row['PREF IBKR']).strip()
                    self.c_type_extra_tickers.add(ticker)
            except Exception:
                pass
        # --- C-pref CSV mapping ve data cache ---
        self.C_CSV_FILES = [
            "nffextlt.csv",
            "ffextlt.csv",
            "flrextlt.csv",
            "maturextlt.csv",
            "duzextlt.csv"
        ]
        self.c_ticker_to_csv = {}
        self.c_csv_data = {}
        for fname in self.C_CSV_FILES:
            try:
                df = pd.read_csv(fname)
                self.c_csv_data[fname] = df.set_index('PREF IBKR')
                for ticker in df['PREF IBKR']:
                    self.c_ticker_to_csv[ticker.strip()] = fname
            except Exception as e:
                print(f"{fname} okunamadı: {e}")

        # --- PsfAlgo Exclude Listesi ---
        self.psfalgo_exclude = self.load_psfalgo_exclude()

        # ✅ PSFAlgo1 ve PSFAlgo2 instance'larını oluştur
        self.psf_algo1 = PsfAlgo1(self.market_data, exclude_list=self.psfalgo_exclude)
        self.psf_algo2 = PsfAlgo2(self.market_data, exclude_list=self.psfalgo_exclude)
        
        # ✅ Ana pencere referanslarını ayarla
        self.psf_algo1.set_main_window(self)
        self.psf_algo2.set_main_window(self)
        
        # ✅ Birbirlerine referans ver (otomatik devir için)
        self.psf_algo1.set_psfalgo2(self.psf_algo2)
        self.psf_algo2.set_psfalgo1(self.psf_algo1)
        
        # ✅ Backward compatibility için
        self.psf_algo = self.psf_algo1  # Eski kodların çalışması için

    def setup_ui(self):
        # Birinci satır: ana işlev butonları
        top1 = ttk.Frame(self)
        top1.pack(fill='x')
        self.btn_connect_ibkr = ttk.Button(top1, text="IBKR'ye Bağlan", command=self.connect_ibkr, width=14)
        self.btn_connect_ibkr.pack(side='left', padx=2)
        self.btn_live_data = ttk.Button(top1, text="Canlı Veri Başlat", command=self.toggle_live_data, width=14)
        self.btn_live_data.pack(side='left', padx=2)
        self.btn_update_data = ttk.Button(top1, text="Veri Güncelle", command=self.update_data_once, width=14)
        self.btn_update_data.pack(side='left', padx=2)
        self.btn_etf_update = ttk.Button(top1, text="ETF Veri Güncelle", command=self.update_etf_data_once, width=14)
        self.btn_etf_update.pack(side='left', padx=2)
        self.btn_opt50 = ttk.Button(top1, text="Opt50", command=self.open_opt50_window, width=14)
        self.btn_opt50.pack(side='left', padx=2)
        self.btn_extlt35 = ttk.Button(top1, text="Extlt35", command=self.open_extlt35_window, width=14)
        self.btn_extlt35.pack(side='left', padx=2)
        self.btn_opt50_maltopla = ttk.Button(top1, text="Opt50 maltopla", command=self.open_opt50_maltopla_window, width=14)
        self.btn_opt50_maltopla.pack(side='left', padx=2)
        self.btn_extlt35_maltopla = ttk.Button(top1, text="Extlt35 maltopla", command=self.open_extlt35_maltopla_window, width=14)
        self.btn_extlt35_maltopla.pack(side='left', padx=2)
        self.btn_exdiv = ttk.Button(top1, text="Paste Ex-Div List", command=self.paste_exdiv_list, width=16)
        self.btn_exdiv.pack(side='left', padx=2)
        self.btn_auto_data = ttk.Button(top1, text="AutoDataOFF", command=self.toggle_auto_data, width=14)
        self.btn_auto_data.pack(side='left', padx=2)
        self.btn_psf_algo1 = ttk.Button(top1, text="PsfAlgo1 OFF", command=self.activate_psf_algo1, width=14)
        self.btn_psf_algo1.pack(side='left', padx=2)
        self.btn_psf_algo2 = ttk.Button(top1, text="PsfAlgo2 OFF", command=self.activate_psf_algo2, width=14)
        self.btn_psf_algo2.pack(side='left', padx=2)
        self.btn_psfalgo_exclude = ttk.Button(top1, text="Exclude fr Psfalgo", command=self.open_psfalgo_exclude_window, width=18)
        self.btn_psfalgo_exclude.pack(side='left', padx=2)
        self.btn_psf_reasoning = ttk.Button(top1, text="Psf Reasoning", command=self.open_psf_reasoning_window, width=16)
        self.btn_psf_reasoning.pack(side='left', padx=2)
        self.btn_befday = ttk.Button(top1, text="BEFDAY", command=self.befday_snapshot, width=10)
        self.btn_befday.pack(side='left', padx=2)
        
        # ✅ PSFAlgo test butonları
        self.btn_psf_test = ttk.Button(top1, text="PSF Test", command=self.test_psf_reverse, width=10)
        self.btn_psf_test.pack(side='left', padx=2)
        self.btn_psf_debug = ttk.Button(top1, text="PSF Debug", command=self.debug_psf_fills, width=10)
        self.btn_psf_debug.pack(side='left', padx=2)
        
        self.btn_bdata = ttk.Button(self, text="BDATA", command=self.open_bdata_window, width=10)
        self.btn_bdata.pack(side='top', padx=2, pady=2)
        self.bdata_path = os.path.join(os.path.dirname(__file__), '../data/bdata.csv')
        self.bdata = self.load_bdata()
        # İkinci satır: diğer butonlar
        top2 = ttk.Frame(self)
        top2.pack(fill='x', pady=(2, 0))
        self.btn_positions = ttk.Button(top2, text="Pozisyonlarım", command=self.open_positions_window, width=14)
        self.btn_positions.pack(side='left', padx=2)
        self.btn_orders = ttk.Button(top2, text="Emirlerim", command=self.open_orders_window, width=14)
        self.btn_orders.pack(side='left', padx=2)
        self.btn_t_top_losers_maltopla = ttk.Button(top2, text="T-top losers", command=self.open_t_top_losers_maltopla, width=14)
        self.btn_t_top_losers_maltopla.pack(side='left', padx=2)
        self.btn_t_top_gainers_maltopla = ttk.Button(top2, text="T-top gainers", command=self.open_t_top_gainers_maltopla, width=14)
        self.btn_t_top_gainers_maltopla.pack(side='left', padx=2)
        self.btn_long_take_profit = ttk.Button(top2, text='Long take profit', command=self.open_long_take_profit_window, width=14)
        self.btn_long_take_profit.pack(side='left', padx=2)
        self.btn_short_take_profit = ttk.Button(top2, text='Short take profit', command=self.open_short_take_profit_window, width=14)
        self.btn_short_take_profit.pack(side='left', padx=2)
        self.status_label = ttk.Label(top2, text="Durum: Bekleniyor")
        self.status_label.pack(side='left', padx=10)
        # Üçüncü satır: kategori butonları
        cat_frame = ttk.Frame(self)
        cat_frame.pack(fill='x', pady=(2, 0))
        self.btn_maturex_top_losers = ttk.Button(cat_frame, text="Maturex-çok düşenler", command=self.open_maturex_top_losers_window, width=18)
        self.btn_maturex_top_losers.pack(side='left', padx=2)
        self.btn_nffex_top_losers = ttk.Button(cat_frame, text="NFFex-çok düşenler", command=self.open_nffex_top_losers_window, width=16)
        self.btn_nffex_top_losers.pack(side='left', padx=2)
        self.btn_ffex_top_losers = ttk.Button(cat_frame, text="FFex-çok düşenler", command=self.open_ffex_top_losers_window, width=14)
        self.btn_ffex_top_losers.pack(side='left', padx=2)
        self.btn_flrex_top_losers = ttk.Button(cat_frame, text="FLRex-çok düşenler", command=self.open_flrex_top_losers_window, width=16)
        self.btn_flrex_top_losers.pack(side='left', padx=2)
        self.btn_duzex_top_losers = ttk.Button(cat_frame, text="Duzex-çok düşenler", command=self.open_duzex_top_losers_window, width=16)
        self.btn_duzex_top_losers.pack(side='left', padx=2)
        self.btn_maturex_top_gainers = ttk.Button(cat_frame, text="Maturex-çok yükselenler", command=self.open_maturex_top_gainers_window, width=18)
        self.btn_maturex_top_gainers.pack(side='left', padx=2)
        self.btn_nffex_top_gainers = ttk.Button(cat_frame, text="NFFex-çok yükselenler", command=self.open_nffex_top_gainers_window, width=16)
        self.btn_nffex_top_gainers.pack(side='left', padx=2)
        self.btn_ffex_top_gainers = ttk.Button(cat_frame, text="FFex-çok yükselenler", command=self.open_ffex_top_gainers_window, width=14)
        self.btn_ffex_top_gainers.pack(side='left', padx=2)
        self.btn_flrex_top_gainers = ttk.Button(cat_frame, text="FLRex-çok yükselenler", command=self.open_flrex_top_gainers_window, width=16)
        self.btn_flrex_top_gainers.pack(side='left', padx=2)
        self.btn_duzex_top_gainers = ttk.Button(cat_frame, text="Duzex-çok yükselenler", command=self.open_duzex_top_gainers_window, width=16)
        self.btn_duzex_top_gainers.pack(side='left', padx=2)
        # Notebook ve frame'ler aşağıda
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True)
        self.historical_frame = ttk.Frame(self.notebook)
        self.historical_table = self.create_table(self.historical_frame)
        self.historical_nav = self.create_nav(self.historical_frame, self.prev_historical, self.next_historical)
        self.notebook.add(self.historical_frame, text="T-prefs")
        self.extended_frame = ttk.Frame(self.notebook)
        self.extended_table = self.create_table(self.extended_frame)
        self.extended_nav = self.create_nav(self.extended_frame, self.prev_extended, self.next_extended)
        self.notebook.add(self.extended_frame, text="C-prefs")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def create_table(self, parent):
        columns = ('Ticker', 'Bid', 'Ask', 'Last', 'Previous close', 'Volume', 'Pref type', 'Benchmark chg', 'CMON', 'Group', 'AVG_ADV', 'FINAL_THG')
        table = ttk.Treeview(parent, columns=columns, show='headings', height=20)
        for col in columns:
            table.heading(col, text=col)
            table.column(col, width=100, anchor='center')
        table.pack(fill='both', expand=True)
        return table

    def create_nav(self, parent, prev_cmd, next_cmd):
        nav = ttk.Frame(parent)
        nav.pack(fill='x')
        btn_prev = ttk.Button(nav, text="<", command=prev_cmd)
        btn_prev.pack(side='left', padx=5)
        lbl = ttk.Label(nav, text="Page 1")
        lbl.pack(side='left', padx=5)
        btn_next = ttk.Button(nav, text=">", command=next_cmd)
        btn_next.pack(side='left', padx=5)
        return {'frame': nav, 'btn_prev': btn_prev, 'btn_next': btn_next, 'lbl': lbl}

    def connect_ibkr(self):
        """IBKR TWS/Gateway'e bağlan"""
        if self.market_data.connect_ibkr():
            self.status_label.config(text="Durum: IBKR'ye bağlı")
            self.btn_connect_ibkr.config(text="IBKR'den Ayrıl", command=self.disconnect_ibkr)
            
            # ✅ PSFAlgo varsa market data'ya bağla
            if hasattr(self, 'psf_algo') and self.psf_algo is not None:
                self.market_data.set_psf_algo(self.psf_algo)
                print("[MAIN] PSFAlgo, IBKR fill event'lerine bağlandı")
            
            # Pozisyonları ve emirleri güncelle
            self.init_bdata_from_ibkr()  # <-- IBKR bağlantısından sonra BDATA başlat
            self.update_tables()
        else:
            self.status_label.config(text="Durum: IBKR bağlantı hatası")

    def disconnect_ibkr(self):
        """IBKR bağlantısını kapat"""
        self.market_data.disconnect_ibkr()
        self.status_label.config(text="Durum: IBKR bağlantısı kesildi")
        self.btn_connect_ibkr.config(text="IBKR'ye Bağlan", command=self.connect_ibkr)

    def toggle_live_data(self):
        if not getattr(self, 'live_data_running', False):
            # Aktif tabdaki tickerları al
            if self.active_tab == 0:
                orig_tickers = self.get_visible_tickers(self.historical_tickers, self.historical_page)
            else:
                orig_tickers = self.get_visible_tickers(self.extended_tickers, self.extended_page)
            poly_tickers = [self.ticker_map[orig] for orig in orig_tickers]
            self.market_data.start_live_stream(poly_tickers, self.on_live_update)
            self.btn_live_data.config(text="Canlı Veriyi Durdur")
            self.live_data_running = True
            self.status_label.config(text="Durum: Canlı veri açık")
        else:
            self.market_data.stop_live_stream()
            self.btn_live_data.config(text="Canlı Veri Başlat")
            self.live_data_running = False
            self.status_label.config(text="Durum: Canlı veri kapalı")

    def update_data_once(self):
        # Tüm T-pref ve C-pref tickerlarını topla
        all_tickers = self.historical_tickers + self.extended_tickers
        poly_tickers = [polygonize_ticker(orig) for orig in all_tickers]
        self.market_data.fetch_rest_data(poly_tickers)
        self.update_tables()
        self.status_label.config(text="Durum: Tüm hisseler güncellendi (REST API)")

    def subscribe_visible(self):
        if self.active_tab == 0:
            orig_tickers = self.get_visible_tickers(self.historical_tickers, self.historical_page)
        else:
            orig_tickers = self.get_visible_tickers(self.extended_tickers, self.extended_page)
        poly_tickers = [self.ticker_map[orig] for orig in orig_tickers]
        if getattr(self, 'live_mode', False):
            self.market_data.start_live_stream(poly_tickers, self.on_live_update)
        else:
            self.market_data.fetch_rest_data(poly_tickers)

    def get_visible_tickers(self, ticker_list, page):
        start = page * self.items_per_page
        end = min(start + self.items_per_page, len(ticker_list))
        return ticker_list[start:end]

    def on_live_update(self, symbol, data):
        # Canlı veri geldiğinde tabloyu güncelle
        self.update_tables()

    def update_tables(self):
        # Historical
        self.update_table(self.historical_table, self.historical_tickers, self.historical_page)
        self.historical_nav['lbl'].config(text=f"Page {self.historical_page + 1}")
        # Extended
        self.update_table(self.extended_table, self.extended_tickers, self.extended_page)
        self.extended_nav['lbl'].config(text=f"Page {self.extended_page + 1}")
        # BenchmarkPanel'leri güncelle
        benchmarks = self.get_benchmarks()
        self.historical_benchmark.update(benchmarks)
        self.extended_benchmark.update(benchmarks)

    def update_table(self, table, ticker_list, page):
        for item in table.get_children():
            table.delete(item)
        orig_tickers = self.get_visible_tickers(ticker_list, page)
        poly_tickers = [self.ticker_map[orig] for orig in orig_tickers]
        data = self.market_data.get_market_data(poly_tickers)
        for orig, poly in zip(orig_tickers, poly_tickers):
            d = data.get(poly, {})
            last = d.get('last','N/A')
            prev_close = d.get('prev_close','N/A')
            try:
                last_f = float(last)
                prev_close_f = float(prev_close)
                adj_prev_close = prev_close_f
                div = self.exdiv_data.get(orig, 0)
                if div:
                    adj_prev_close = prev_close_f - div
                daily_change = last_f - adj_prev_close
                daily_change = round(daily_change, 4)
            except Exception:
                daily_change = 'N/A'
            table.insert('', 'end', values=(orig, d.get('bid','N/A'), d.get('ask','N/A'), d.get('last','N/A'), adj_prev_close if 'adj_prev_close' in locals() else d.get('prev_close','N/A'), d.get('volume','N/A'), 'N/A', 'N/A', daily_change, 'N/A', 'N/A', 'N/A'))

    def update_data_loop(self):
        while True:
            self.subscribe_visible()
            time.sleep(2)

    def prev_historical(self):
        if self.historical_page > 0:
            self.historical_page -= 1
            self.update_tables()

    def next_historical(self):
        max_page = (len(self.historical_tickers) - 1) // self.items_per_page
        if self.historical_page < max_page:
            self.historical_page += 1
            self.update_tables()

    def prev_extended(self):
        if self.extended_page > 0:
            self.extended_page -= 1
            self.update_tables()

    def next_extended(self):
        max_page = (len(self.extended_tickers) - 1) // self.items_per_page
        if self.extended_page < max_page:
            self.extended_page += 1
            self.update_tables()

    def on_tab_changed(self, event):
        self.active_tab = self.notebook.index(self.notebook.select())
        self.subscribe_visible()

    def update_etf_panel(self):
        # ETF panelini canlı WebSocket verisiyle güncelle
        etf_data = {}
        
        # ETF'ler için previous close bilgisini al
        etf_symbols = ["PFF", "TLT", "SPY", "IWM", "KRE"]
        
        for sym in etf_symbols:
            # IBKR'den ETF verisini al
            if hasattr(self.market_data, 'ib') and self.market_data.ib and self.market_data.ib.isConnected():
                try:
                    from ib_insync import Stock
                    contract = Stock(sym, 'SMART', 'USD')
                    self.market_data.ib.qualifyContracts(contract)
                    ticker_data = self.market_data.ib.ticker(contract)
                    
                    if ticker_data and ticker_data.last:
                        last = ticker_data.last
                        prev_close = ticker_data.close  # Previous close fiyatı
                        
                        if last != 'N/A' and prev_close is not None and prev_close > 0:
                            # Previous close'a göre change hesapla
                            change = round(last - prev_close, 3)
                            change_pct = round(100 * (last - prev_close) / prev_close, 2)
                        else:
                            change = 'N/A'
                            change_pct = 'N/A'
                        
                        etf_data[sym] = {'last': last, 'change': change, 'change_pct': change_pct}
                    else:
                        etf_data[sym] = {'last': 'N/A', 'change': 'N/A', 'change_pct': 'N/A'}
                        
                except Exception as e:
                    print(f"[ETF UPDATE] ❌ {sym} ETF data hatası: {e}")
                    etf_data[sym] = {'last': 'N/A', 'change': 'N/A', 'change_pct': 'N/A'}
            else:
                # Fallback: WebSocket fiyatlarını kullan (eğer varsa)
                prices = getattr(self.market_data, 'etf_prices', {}).get(sym, [])
                last = prices[-1][1] if prices else 'N/A'
                etf_data[sym] = {'last': last, 'change': 'N/A', 'change_pct': 'N/A'}
        
        # ETF panelini güncelle
        if hasattr(self, 'etf_panel'):
            self.etf_panel.update(etf_data)
        
        # 1 saniye sonra tekrar güncelle
        self.after(1000, self.update_etf_panel)

    def update_etf_data_once(self):
        # ETF'leri IBKR'den güncelle (previous close ile)
        print("[ETF UPDATE] 📊 ETF'ler IBKR'den güncelleniyor...")
        
        if hasattr(self.market_data, 'get_etf_data'):
            etf_data = self.market_data.get_etf_data()
            
            # ETF panelini güncelle
            if hasattr(self, 'etf_panel') and etf_data:
                self.etf_panel.update(etf_data)
                print(f"[ETF UPDATE] ✅ {len(etf_data)} ETF güncellendi")
                
                # Debug: ETF change değerlerini logla
                for symbol, data in etf_data.items():
                    last = data.get('last', 'N/A')
                    prev_close = data.get('prev_close', 'N/A')
                    change = data.get('change', 'N/A')
                    change_pct = data.get('change_pct', 'N/A')
                    print(f"[ETF UPDATE] {symbol}: Last={last}, PrevClose={prev_close}, Change={change} ({change_pct}%)")
            else:
                print("[ETF UPDATE] ❌ ETF data alınamadı")
        
        self.status_label.config(text="Durum: ETF'ler güncellendi (Previous Close ile)")
        
        # Normal ETF panel güncellemesini de çağır
        self.update_etf_panel()

    def open_extlt35_window(self):
        self.open_csv_window('optimized_35_extlt.csv', 'Extlt35')

    def open_opt50_window(self):
        self.open_csv_window('optimized_50_stocks_portfolio.csv', 'Opt50')

    def open_csv_window(self, csv_path, title):
        try:
            df = pd.read_csv(csv_path)
            # Kolon isimlerini normalize et
            cols = [c.strip() for c in df.columns]
            df.columns = cols
            # Gerekli kolonları çek
            show_cols = ['PREF IBKR', 'Final_Shares', 'FINAL_THG', 'AVG_ADV']
            # Alternatif kolon isimleri için fallback
            for alt in ['Final Shares', 'Final_Shares']:
                if alt in df.columns:
                    df['Final_Shares'] = df[alt]
            for alt in ['FINAL THG', 'FINAL_THG']:
                if alt in df.columns:
                    df['FINAL_THG'] = df[alt]
            for alt in ['AVG ADV', 'AVG_ADV']:
                if alt in df.columns:
                    df['AVG_ADV'] = df[alt]
            df = df[[c for c in show_cols if c in df.columns]]
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror(title, f"CSV okunamadı: {e}")
            return
        win = tk.Toplevel(self)
        win.title(title)
        table = ttk.Treeview(win, columns=list(df.columns), show='headings')
        for col in df.columns:
            table.heading(col, text=col)
            table.column(col, width=120, anchor='center')
        for _, row in df.iterrows():
            table.insert('', 'end', values=[row.get(col, '') for col in df.columns])
        table.pack(fill='both', expand=True)
        # Scrollbar ekle
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

    def open_opt50_maltopla_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('optimized_50_stocks_portfolio.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "Opt50 Maltopla", "optimized_50_stocks_portfolio.csv", market_data_dict, etf_data, benchmark_type='T', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        # self.maltopla_windows.append(win)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_extlt35_maltopla_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('optimized_35_extlt.csv')
        seen_ibkr = set()
        seen_poly = set()
        unique_rows = []
        for _, row in df.iterrows():
            ticker = str(row['PREF IBKR']).strip()
            poly = polygonize_ticker(ticker)
            if ticker not in seen_ibkr and poly not in seen_poly:
                seen_ibkr.add(ticker)
                seen_poly.add(poly)
                unique_rows.append(row)
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for row in unique_rows]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "Extlt35 Maltopla", "optimized_35_extlt.csv", market_data_dict, etf_data, benchmark_type='C', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data, c_ticker_to_csv=self.c_ticker_to_csv, c_csv_data=self.c_csv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_positions_window(self):
        win = tk.Toplevel(self)
        win.title('Pozisyonlarım')
        win.geometry("600x400")
        
        # Create positions table
        columns = ('Symbol', 'Quantity', 'Avg Cost', 'Market Value', 'Unrealized PnL')
        table = ttk.Treeview(win, columns=columns, show='headings')
        
        # Set column headings
        for col in columns:
            table.heading(col, text=col)
            table.column(col, width=100, anchor='center')
            
        table.pack(fill='both', expand=True, padx=5, pady=5)
        
        def update_table():
            # Clear existing items
            for item in table.get_children():
                table.delete(item)
            # Get positions from IBKR
            if hasattr(self.market_data, 'ib') and self.market_data.ib.isConnected():
                positions = self.market_data.ib.positions()
                # Update table
                for position in positions:
                    contract = position.contract
                    table.insert('', 'end', values=(
                        contract.symbol,
                        position.position,
                        position.avgCost,
                        '',  # marketValue yok
                        ''   # unrealizedPNL yok
                    ))
            # Schedule next update
            win.after(5000, update_table)
            
        # Start updates
        update_table()

    def open_orders_window(self):
        orders_window = tk.Toplevel(self)
        orders_window.title("Emirlerim")
        orders_window.geometry("1100x600")

        # Create notebook for tabs
        notebook = ttk.Notebook(orders_window)
        notebook.pack(fill='both', expand=True, padx=5, pady=5)

        # Pending Orders tab (IBKR)
        pending_frame = ttk.Frame(notebook)
        notebook.add(pending_frame, text="Bekleyen")
        
        # Add button frame for pending orders
        pending_btn_frame = ttk.Frame(pending_frame)
        pending_btn_frame.pack(fill='x', pady=2)
        
        # Add select all/deselect all buttons
        ttk.Button(pending_btn_frame, text="Tümünü Seç", command=lambda: self._select_all_orders(self.pending_tree)).pack(side='left', padx=2)
        ttk.Button(pending_btn_frame, text="Tümünü Bırak", command=lambda: self._deselect_all_orders(self.pending_tree)).pack(side='left', padx=2)
        
        # Add cancel and modify buttons
        ttk.Button(pending_btn_frame, text="Seçili Emirleri İptal Et", command=lambda: self._cancel_selected_orders(self.pending_tree)).pack(side='left', padx=2)
        ttk.Button(pending_btn_frame, text="Seçili Emri Düzenle", command=lambda: self._modify_selected_order(self.pending_tree)).pack(side='left', padx=2)
        
        # Add Orderbook button
        ttk.Button(pending_btn_frame, text="Orderbook", command=lambda: self._open_orderbook_for_selected(self.pending_tree)).pack(side='left', padx=2)
        
        pending_columns = ('select', 'symbol', 'action', 'quantity', 'price', 'status', 'orderId', 'Type', 'Emir info', 'N or Rev')
        self.pending_tree = ttk.Treeview(pending_frame, columns=pending_columns, show='headings')
        for col in pending_columns:
            self.pending_tree.heading(col, text=col)
            self.pending_tree.column(col, width=100)
        self.pending_tree.pack(fill='both', expand=True)
        
        # Bind click event for checkboxes
        self.pending_tree.bind('<ButtonRelease-1>', lambda e: self._toggle_checkbox(self.pending_tree, e))

        # Filled Orders tab (IBKR)
        filled_frame = ttk.Frame(notebook)
        notebook.add(filled_frame, text="Fillendi")
        
        # Add button frame for filled orders
        filled_btn_frame = ttk.Frame(filled_frame)
        filled_btn_frame.pack(fill='x', pady=2)
        
        # Add select all/deselect all buttons
        ttk.Button(filled_btn_frame, text="Tümünü Seç", command=lambda: self._select_all_orders(self.filled_tree)).pack(side='left', padx=2)
        ttk.Button(filled_btn_frame, text="Tümünü Bırak", command=lambda: self._deselect_all_orders(self.filled_tree)).pack(side='left', padx=2)
        
        # Add Orderbook button
        ttk.Button(filled_btn_frame, text="Orderbook", command=lambda: self._open_orderbook_for_selected(self.filled_tree)).pack(side='left', padx=2)
        
        filled_columns = ('select', 'symbol', 'action', 'quantity', 'price', 'status', 'orderId', 'fillTime', 'Type', 'Emir info', 'N or Rev')
        self.filled_tree = ttk.Treeview(filled_frame, columns=filled_columns, show='headings')
        for col in filled_columns:
            self.filled_tree.heading(col, text=col)
            self.filled_tree.column(col, width=100)
        self.filled_tree.pack(fill='both', expand=True)
        
        # Bind click event for checkboxes
        self.filled_tree.bind('<ButtonRelease-1>', lambda e: self._toggle_checkbox(self.filled_tree, e))

        # Reverse Orders tab (OrderManager)
        reverse_frame = ttk.Frame(notebook)
        notebook.add(reverse_frame, text="Reverse Orders")
        
        # Add button frame for reverse orders
        reverse_btn_frame = ttk.Frame(reverse_frame)
        reverse_btn_frame.pack(fill='x', pady=2)
        
        # Add select all/deselect all buttons
        ttk.Button(reverse_btn_frame, text="Tümünü Seç", command=lambda: self._select_all_orders(self.reverse_tree)).pack(side='left', padx=2)
        ttk.Button(reverse_btn_frame, text="Tümünü Bırak", command=lambda: self._deselect_all_orders(self.reverse_tree)).pack(side='left', padx=2)
        
        # Add Orderbook button
        ttk.Button(reverse_btn_frame, text="Orderbook", command=lambda: self._open_orderbook_for_selected(self.reverse_tree)).pack(side='left', padx=2)
        
        columns_reverse = ("select", "Ticker", "Direction", "Price", "Size", "Hidden", "OrderType", "Parent Fill Time", "Parent Fill Price")
        self.reverse_tree = ttk.Treeview(reverse_frame, columns=columns_reverse, show='headings')
        for col in columns_reverse:
            self.reverse_tree.heading(col, text=col)
            self.reverse_tree.column(col, width=120, anchor='center')
        self.reverse_tree.pack(fill='both', expand=True)
        
        # Bind click event for checkboxes
        self.reverse_tree.bind('<ButtonRelease-1>', lambda e: self._toggle_checkbox(self.reverse_tree, e))

        refresh_btn = ttk.Button(orders_window, text="Yenile", command=lambda: self.update_orders(pending_frame, filled_frame))
        refresh_btn.pack(pady=5)
        self.update_orders(pending_frame, filled_frame)

    def _toggle_checkbox(self, tree, event):
        """Toggle checkbox when clicked"""
        # Get the clicked region
        region = tree.identify_region(event.x, event.y)
        if region == "cell":
            # Get the clicked column
            column = tree.identify_column(event.x)
            if column == "#1":  # First column (select)
                # Get the clicked item
                item = tree.identify_row(event.y)
                if item:
                    # Toggle the checkbox
                    current = tree.set(item, "select")
                    tree.set(item, "select", "✓" if current != "✓" else "")
                    # Update the tree
                    tree.update()

    def _select_all_orders(self, tree):
        """Select all orders in the given tree"""
        for item in tree.get_children():
            tree.set(item, 'select', '✓')
            tree.update()

    def _deselect_all_orders(self, tree):
        """Deselect all orders in the given tree"""
        for item in tree.get_children():
            tree.set(item, 'select', '')
            tree.update()

    def _find_order_by_id(self, order_id):
        ib = getattr(self.market_data, 'ib', None)
        if not ib or not ib.isConnected():
            return None, None
        # Önce openOrders'dan bak
        for o in ib.openOrders():
            if getattr(o, 'orderId', None) == order_id:
                contract = getattr(o, 'contract', None)
                return o, contract
        # trades içinden bak
        for t in ib.trades():
            if getattr(t.order, 'orderId', None) == order_id:
                return t.order, getattr(t, 'contract', None)
        return None, None

    def _cancel_selected_orders(self, tree):
        """Cancel selected orders"""
        selected_orders = []
        for item in tree.get_children():
            if tree.set(item, 'select') == '✓':
                order_id = tree.set(item, 'orderId')
                if order_id:
                    selected_orders.append(order_id)
        
        if not selected_orders:
            messagebox.showinfo("Uyarı", "Lütfen iptal edilecek emirleri seçin.")
            return
            
        if messagebox.askyesno("Onay", f"{len(selected_orders)} adet emir iptal edilecek. Onaylıyor musunuz?"):
            for order_id in selected_orders:
                try:
                    if hasattr(self.market_data, 'ib') and self.market_data.ib.isConnected():
                        order_obj, _ = self._find_order_by_id(int(order_id))
                        if order_obj:
                            self.market_data.ib.cancelOrder(order_obj)
                        else:
                            messagebox.showerror("Hata", f"OrderId {order_id} için Order objesi bulunamadı.")
                except Exception as e:
                    messagebox.showerror("Hata", f"Emir iptal edilirken hata oluştu: {e}")
            self.update_orders(None, None)  # Tabloları yenile

    def _modify_selected_order(self, tree):
        """Modify selected order"""
        selected_orders = []
        for item in tree.get_children():
            if tree.set(item, 'select') == '✓':
                order_id = tree.set(item, 'orderId')
                if order_id:
                    selected_orders.append((order_id, item))
        
        if not selected_orders:
            messagebox.showinfo("Uyarı", "Lütfen düzenlenecek emri seçin.")
            return
            
        if len(selected_orders) > 1:
            messagebox.showinfo("Uyarı", "Lütfen sadece bir emir seçin.")
            return
            
        order_id, item = selected_orders[0]
        
        # Emir düzenleme penceresi
        modify_win = tk.Toplevel(self)
        modify_win.title("Emir Düzenle")
        modify_win.geometry("300x200")
        
        # Mevcut değerleri al
        try:
            current_price = float(tree.set(item, 'price'))
        except Exception:
            current_price = 0.0
        try:
            current_quantity = int(float(tree.set(item, 'quantity')))
        except Exception:
            current_quantity = 0
        
        # Yeni değerler için entry'ler
        ttk.Label(modify_win, text="Yeni Fiyat:").pack(pady=5)
        price_entry = ttk.Entry(modify_win)
        price_entry.insert(0, str(current_price))
        price_entry.pack(pady=5)
        
        ttk.Label(modify_win, text="Yeni Miktar:").pack(pady=5)
        quantity_entry = ttk.Entry(modify_win)
        quantity_entry.insert(0, str(current_quantity))
        quantity_entry.pack(pady=5)
        
        def apply_modification():
            try:
                new_price = float(price_entry.get())
                new_quantity = int(float(quantity_entry.get()))
                if hasattr(self.market_data, 'ib') and self.market_data.ib.isConnected():
                    order_obj, contract = self._find_order_by_id(int(order_id))
                    # Eğer contract yoksa, Treeview'dan sembol ile yeni contract oluştur
                    if not contract:
                        symbol = tree.set(item, 'symbol')
                        if not symbol:
                            messagebox.showerror("Hata", "Sembol bulunamadı, emir modify edilemez.")
                            return
                        from ib_insync import Stock
                        contract = Stock(symbol, 'SMART', 'USD')
                    if order_obj and contract:
                        self.market_data.ib.cancelOrder(order_obj)
                        # Yeni order oluştur (aynı sembol, action, type ile)
                        action = getattr(order_obj, 'action', 'BUY')
                        orderType = getattr(order_obj, 'orderType', 'LMT')
                        from ib_insync import LimitOrder
                        if orderType == 'LMT':
                            new_order = LimitOrder(action, new_quantity, new_price)
                            new_order.hidden = True  # Emir gizli olarak gönderilecek
                        else:
                            messagebox.showerror("Hata", f"Sadece LMT tipli emirler destekleniyor.")
                            return
                        self.market_data.ib.placeOrder(contract, new_order)
                        messagebox.showinfo("Başarılı", "Emir başarıyla güncellendi (eski iptal, yeni gönderildi).")
                        modify_win.destroy()
                        self.update_orders(None, None)
                    else:
                        messagebox.showerror("Hata", f"OrderId {order_id} için Order veya Contract objesi bulunamadı. Bu emir modify edilemez.")
            except Exception as e:
                messagebox.showerror("Hata", f"Emir düzenlenirken hata oluştu: {e}")
        
        ttk.Button(modify_win, text="Uygula", command=apply_modification).pack(pady=10)

    def update_orders(self, pending_frame, filled_frame):
        # DEBUG: IBKR API'dan veri geliyor mu?
        ib = getattr(self.market_data, 'ib', None)
        if not ib or not ib.isConnected():
            print('[DEBUG] IBKR bağlantısı yok veya kopuk.')
            return
        print('[DEBUG] openOrders:', ib.openOrders())
        print('[DEBUG] orders:', ib.orders() if hasattr(ib, 'orders') else 'Yok')
        print('[DEBUG] trades:', ib.trades())
        print('[DEBUG] positions:', ib.positions())
        # Treeview'ları temizle
        for item in self.pending_tree.get_children():
            self.pending_tree.delete(item)
        for item in self.filled_tree.get_children():
            self.filled_tree.delete(item)

        # --- Bekleyen Emirler (openOrders) ---
        open_orders = ib.openOrders()
        orders_with_contracts = ib.orders() if hasattr(ib, 'orders') else []
        orderid_to_symbol = {}
        for o in orders_with_contracts:
            try:
                orderid_to_symbol[o.orderId] = o.contract.symbol
            except Exception:
                pass
        # Pozisyonları al
        positions = {}
        try:
            for p in ib.positions():
                positions[p.contract.symbol] = p.position
        except Exception:
            pass
        # Reverse orderId seti
        reverse_order_ids = set()
        if hasattr(self, 'order_manager'):
            for ro in self.order_manager.get_reverse_orders():
                if 'orderId' in ro:
                    reverse_order_ids.add(ro['orderId'])
        # trades üzerinden orderId->symbol eşlemesi
        trades = ib.trades()
        trade_orderid_to_symbol = {}
        for trade in trades:
            try:
                trade_orderid_to_symbol[trade.order.orderId] = trade.contract.symbol
            except Exception:
                pass
        for o in open_orders:
            orderId = getattr(o, 'orderId', None)
            # symbol bulma
            symbol = orderid_to_symbol.get(orderId, '')
            if not symbol:
                symbol = trade_orderid_to_symbol.get(orderId, '')
            action = getattr(o, 'action', '')
            quantity = getattr(o, 'totalQuantity', '')
            price = getattr(o, 'lmtPrice', '')
            status = getattr(o, 'status', '')
            orderType = getattr(o, 'orderType', '')
            # Emir info
            pos = positions.get(symbol, 0)
            emir_info = ''
            if action == 'BUY':
                if pos < 0:
                    emir_info = 'Short azaltma'
                else:
                    emir_info = 'Long arttirma'
            elif action == 'SELL':
                if pos > 0:
                    emir_info = 'Long azaltma'
                else:
                    emir_info = 'Short arttirma'
            nor_rev = 'Nor'
            if orderId in reverse_order_ids:
                nor_rev = 'Rev'
            self.pending_tree.insert('', 'end', values=(
                '', symbol, action, quantity, price, status, orderId, orderType, emir_info, nor_rev
            ))

        # --- Fillendi Emirler (IBKR trades doğrudan, minimum debug amaçlı) ---
        for trade in trades:
            contract = trade.contract
            order = trade.order
            status = trade.orderStatus
            fills = trade.fills
            if not fills:
                continue
            symbol = getattr(contract, 'symbol', '')
            orderId = getattr(order, 'orderId', '')
            orderType = getattr(order, 'orderType', '')
            # Pozisyonu bulmak için fill öncesi pozisyonu tahmin etmek gerekir, burada sadece fill anındaki pozisyonu kullanıyoruz
            pos = positions.get(symbol, 0)
            for fill in fills:
                fill_time = fill.time.strftime('%Y-%m-%d %H:%M:%S') if hasattr(fill, 'time') else ''
                fill_size = fill.execution.shares
                fill_price = fill.execution.price
                action = order.action
                # Emir info
                emir_info = ''
                if action == 'BUY':
                    if pos < 0:
                        emir_info = 'Short azaltma'
                    else:
                        emir_info = 'Long arttirma'
                elif action == 'SELL':
                    if pos > 0:
                        emir_info = 'Long azaltma'
                    else:
                        emir_info = 'Short arttirma'
                nor_rev = 'Nor'
                if hasattr(self, 'order_manager'):
                    for ro in self.order_manager.get_reverse_orders():
                        if ro.get('orderId', None) == orderId:
                            nor_rev = 'Rev'
                            break
                self.filled_tree.insert('', 'end', values=(
                    '', symbol, action, fill_size, fill_price, status.status, orderId, fill_time, orderType, emir_info, nor_rev
                ))

        # --- Reverse Orders (OrderManager) ---
        if hasattr(self, 'order_manager'):
            reverse_orders = self.order_manager.get_reverse_orders()
            reverse_tree = None
            for child in filled_frame.master.winfo_children():
                if isinstance(child, ttk.Notebook):
                    for i in range(child.index('end')):
                        tab = child.nametowidget(child.tabs()[i])
                        if 'Reverse' in child.tab(i, 'text'):
                            reverse_tree = tab.winfo_children()[0]
            if reverse_tree:
                for item in reverse_tree.get_children():
                    reverse_tree.delete(item)
                for ro in reverse_orders:
                    reverse_tree.insert('', 'end', values=(
                        ro['ticker'],
                        ro['direction'],
                        ro['price'],
                        ro['size'],
                        ro.get('hidden', False),
                        ro.get('order_type', 'TP'),
                        ro.get('parent_fill_time', ''),
                        ro.get('parent_fill_price', '')
                    ))

    def _open_orderbook_for_selected(self, tree):
        """Open orderbook window for the selected order's symbol"""
        selected_items = []
        for item in tree.get_children():
            if tree.set(item, 'select') == '✓':
                selected_items.append(item)
        
        if not selected_items:
            messagebox.showinfo("Uyarı", "Lütfen bir emir seçin.")
            return
            
        if len(selected_items) > 1:
            messagebox.showinfo("Uyarı", "Lütfen sadece bir emir seçin.")
            return
            
        item = selected_items[0]
        symbol = tree.set(item, 'symbol')
        if not symbol:
            messagebox.showinfo("Uyarı", "Seçili emirde sembol bilgisi bulunamadı.")
            return
            
        # Orderbook penceresini aç
        OrderBookWindow(self, symbol, self.market_data.ib)

    def open_top_movers_window(self, pref_type, direction):
        import tkinter.font as tkFont
        import pandas as pd
        import time
        win = tk.Toplevel(self)
        win.title(f"{pref_type}-{'çok düşenler' if direction=='losers' else 'çok yükselenler'}")
        etf_panel = ETFPanel(win, compact=True)
        etf_panel.pack(fill='x', padx=2, pady=2)
        COLUMNS = [
            'Seç', 'Ticker', 'Last print', 'Previous close', 'Bid', 'Ask', 'Spread', 'Pref type', 'Benchmark type', 'Benchmark chg',
            'CMON', 'Group', 'AVG_ADV', 'Final_Shares', 'FINAL_THG',
            'PF Bid buy', 'PF bid buy chg', '🟩 Bid buy Ucuzluk Skoru',
            'PF front buy', 'PF front buy chg', '🟩 Front buy ucuzluk skoru',
            'PF ask buy', 'PF ask buy chg', '🟩 Ask buy ucuzluk skoru',
            'PF Ask sell', 'PF Ask sell chg', '🔺 Ask sell pahalilik skoru',
            'PF front sell', 'PF front sell chg', '🔺 Front sell pahalilik skoru',
            'PF bid sell', 'PF bid sell chg', '🔺 Bid sell pahalilik skoru'
        ]
        font_small = tkFont.Font(family="Arial", size=8)
        font_bold = tkFont.Font(family="Arial", size=8, weight="bold")
        style = ttk.Style()
        style.configure("Treeview.Heading", font=("Arial", 8))
        table = ttk.Treeview(win, columns=COLUMNS, show='headings', height=20)
        for i, col in enumerate(COLUMNS):
            if 'Ucuzluk Skoru' in col or 'pahalilik skoru' in col:
                table.heading(col, text=col)
                table.column(col, width=80, anchor='center')
            else:
                table.heading(col, text=col)
                table.column(col, width=30 if col != 'Seç' else 25, anchor='center')
        table.tag_configure('small', font=font_small)
        table.tag_configure('bold', font=font_bold)
        table.tag_configure('green', foreground='#008000', font=font_bold)
        table.tag_configure('red', foreground='#B22222', font=font_bold)
        table.pack(fill='both', expand=True)
        csv_path = 'mastermind_histport.csv' if pref_type == 'T' else 'mastermind_extltport.csv'
        try:
            df = pd.read_csv(csv_path)
            cols = [c.strip() for c in df.columns]
            df.columns = cols
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("CSV Hatası", f"CSV okunamadı: {e}")
            return
        ticker_info = {}
        ticker_map = {}
        for _, row in df.iterrows():
            symbol = row['PREF IBKR'] if 'PREF IBKR' in row and pd.notna(row['PREF IBKR']) else row.iloc[0]
            if pd.isna(symbol):
                continue
            symbol = str(symbol).strip()
            poly = polygonize_ticker(symbol)
            ticker_map[symbol] = poly
            ticker_map[poly] = symbol
            ticker_info[symbol] = {
                'CMON': row['CMON'] if 'CMON' in row else '',
                'Group': row['Group'] if 'Group' in row else '',
                'AVG_ADV': row['AVG_ADV'] if 'AVG_ADV' in row else '',
                'Final_Shares': row['Final_Shares'] if 'Final_Shares' in row else '',
                'FINAL_THG': row['FINAL_THG'] if 'FINAL_THG' in row else '',
                'Pref type': row['Pref type'] if 'Pref type' in row else '',
            }
        tickers = list(ticker_info.keys())
        items_per_page = 17
        page = [0]
        checked = set()
        sort_col = [None]
        sort_reverse = [False]
        desc_long = (['']*15 + ['Long pozisyon açmak / arttırmak için, veya Short pozisyon kapatmak/azaltmak için'] + ['']*2 + ['🟩'] + ['']*2 + ['🟩'] + ['']*2 + ['🟩'] + ['']*8)
        desc_short = (['']*24 + ['Short pozisyon açmak / arttırmak için, veya Long pozisyon kapatmak/azaltmak için'] + ['']*2 + ['🔺'] + ['']*2 + ['🔺'] + ['']*2 + ['🔺'])
        table.insert('', 'end', iid='desc_long', values=desc_long, tags=('small',))
        table.insert('', 'end', iid='desc_short', values=desc_short, tags=('small',))
        def row_for_symbol(symbol):
            poly = ticker_map[symbol]
            d = self.market_data.get_market_data([poly]).get(poly, {})
            bid = d.get('bid', 'N/A')
            ask = d.get('ask', 'N/A')
            last = d.get('last', 'N/A')
            prev_close = d.get('prev_close', 'N/A')
            checked_box = '\u2611' if symbol in checked else '\u2610'
            pref_type_val = ticker_info.get(symbol, {}).get('Pref type', '')
            benchmark_type = pref_type
            cmon = ticker_info.get(symbol, {}).get('CMON', '')
            group = ticker_info.get(symbol, {}).get('Group', '')
            avg_adv = ticker_info.get(symbol, {}).get('AVG_ADV', '')
            final_shares = ticker_info.get(symbol, {}).get('Final_Shares', '')
            final_thg = ticker_info.get(symbol, {}).get('FINAL_THG', '')
            # Spread ve skor hesapları maltopla ile aynı şekilde yapılacak
            if bid != 'N/A' and ask != 'N/A' and prev_close != 'N/A' and last != 'N/A':
                try:
                    bid = float(bid)
                    ask = float(ask)
                    last = float(last)
                    prev_close = float(prev_close)
                    adj_prev_close = prev_close
                    div = self.exdiv_data.get(symbol, 0)
                    if div:
                        adj_prev_close = prev_close - div
                    daily_change = last - adj_prev_close
                    spread = ask - bid
                    etf_data = self.market_data.get_etf_data()
                    if pref_type == 'T':
                        pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                        tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                        benchmark_chg = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
                    else:
                        pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                        tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                        benchmark_chg = round(pff_chg * 1.3 - tlt_chg * 0.1, 3)
                    pf_bid_buy = round(bid + spread * 0.15, 3)
                    pf_bid_buy_chg = round(pf_bid_buy - adj_prev_close, 3)
                    bid_buy_ucuzluk = round(pf_bid_buy_chg - benchmark_chg, 3)
                    pf_front_buy = round(last + 0.01, 3)
                    pf_front_buy_chg = round(pf_front_buy - adj_prev_close, 3)
                    front_buy_ucuzluk = round(pf_front_buy_chg - benchmark_chg, 3)
                    pf_ask_buy = round(ask + 0.01, 3)
                    pf_ask_buy_chg = round(pf_ask_buy - adj_prev_close, 3)
                    ask_buy_ucuzluk = round(pf_ask_buy_chg - benchmark_chg, 3)
                    pf_ask_sell = round(ask - spread * 0.15, 3)
                    pf_ask_sell_chg = round(pf_ask_sell - adj_prev_close, 3)
                    ask_sell_pahali = round(pf_ask_sell_chg - benchmark_chg, 3)
                    pf_front_sell = round(last - 0.01, 3)
                    pf_front_sell_chg = round(pf_front_sell - adj_prev_close, 3)
                    front_sell_pahali = round(pf_front_sell_chg - benchmark_chg, 3)
                    pf_bid_sell = round(bid - 0.01, 3)
                    pf_bid_sell_chg = round(pf_bid_sell - adj_prev_close, 3)
                    bid_sell_pahali = round(pf_bid_sell_chg - benchmark_chg, 3)
                except Exception:
                    spread = pf_bid_buy = pf_bid_buy_chg = bid_buy_ucuzluk = pf_front_buy = pf_front_buy_chg = front_buy_ucuzluk = pf_ask_buy = pf_ask_buy_chg = ask_buy_ucuzluk = pf_ask_sell = pf_ask_sell_chg = ask_sell_pahali = pf_front_sell = pf_front_sell_chg = front_sell_pahali = pf_bid_sell = pf_bid_sell_chg = bid_sell_pahali = benchmark_chg = daily_change = 'N/A'
            else:
                spread = pf_bid_buy = pf_bid_buy_chg = bid_buy_ucuzluk = pf_front_buy = pf_front_buy_chg = front_buy_ucuzluk = pf_ask_buy = pf_ask_buy_chg = ask_buy_ucuzluk = pf_ask_sell = pf_ask_sell_chg = ask_sell_pahali = pf_front_sell = pf_front_sell_chg = front_sell_pahali = pf_bid_sell = pf_bid_sell_chg = bid_sell_pahali = benchmark_chg = daily_change = 'N/A'
            row = [checked_box, symbol, last, adj_prev_close if 'adj_prev_close' in locals() else prev_close, bid, ask, spread, pref_type_val, benchmark_type, benchmark_chg,
                   cmon, group, avg_adv, final_shares, final_thg,
                   pf_bid_buy, pf_bid_buy_chg, f'🟩 {bid_buy_ucuzluk}' if bid_buy_ucuzluk != 'N/A' else bid_buy_ucuzluk,
                   pf_front_buy, pf_front_buy_chg, f'🟩 {front_buy_ucuzluk}' if front_buy_ucuzluk != 'N/A' else front_buy_ucuzluk,
                   pf_ask_buy, pf_ask_buy_chg, f'🟩 {ask_buy_ucuzluk}' if ask_buy_ucuzluk != 'N/A' else ask_buy_ucuzluk,
                   pf_ask_sell, pf_ask_sell_chg, f'🔺 {ask_sell_pahali}' if ask_sell_pahali != 'N/A' else ask_sell_pahali,
                   pf_front_sell, pf_front_sell_chg, f'🔺 {front_sell_pahali}' if front_sell_pahali != 'N/A' else front_sell_pahali,
                   pf_bid_sell, pf_bid_sell_chg, f'🔺 {bid_sell_pahali}' if bid_sell_pahali != 'N/A' else bid_sell_pahali]
            return row
        def get_sort_key(val):
            try:
                if val is None or str(val).strip() in ('N/A', 'nan', ''):
                    return float('inf')
                return float(str(val).replace(',', ''))
            except Exception:
                return float('inf')
        def populate():
            window_data = {symbol: self.market_data.get_market_data([ticker_map[symbol]]).get(ticker_map[symbol], {}) for symbol in tickers}
            all_rows = []
            for symbol in tickers:
                row = row_for_symbol(symbol)
                all_rows.append(row)
            idx = COLUMNS.index(sort_col[0]) if sort_col[0] is not None else None
            if idx is not None:
                all_rows.sort(
                    key=lambda x: get_sort_key(x[idx]),
                    reverse=sort_reverse[0]
                )
            start = page[0] * items_per_page
            end = start + items_per_page
            page_rows = all_rows[start:end]
            table.delete(*[i for i in table.get_children() if i not in ('desc_long','desc_short')])
            for row in page_rows:
                table.insert('', 'end', iid=row[1], values=row)
            total_pages = (len(all_rows) + items_per_page - 1) // items_per_page
            nav_lbl.config(text=f'Page {page[0]+1} / {total_pages}')
        def on_heading_click(col):
            if sort_col[0] == col:
                sort_reverse[0] = not sort_reverse[0]
            else:
                sort_col[0] = col
                sort_reverse[0] = False
            page[0] = 0
            populate()
        for col in COLUMNS:
            table.heading(col, text=col, command=lambda c=col: on_heading_click(c))
        sel_frame = ttk.Frame(win)
        sel_frame.pack(fill='x', pady=2)
        ttk.Button(sel_frame, text='Tümünü Seç', command=lambda: (checked.clear(), checked.update(tickers[page[0]*items_per_page:page[0]*items_per_page+items_per_page]), populate())).pack(side='left', padx=2)
        ttk.Button(sel_frame, text='Tümünü Kaldır', command=lambda: (checked.clear(), populate())).pack(side='left', padx=2)
        action_frame = ttk.Frame(win)
        action_frame.pack(fill='x', pady=4)
        ttk.Button(action_frame, text='Seçili Tickerlara Hidden Order', command=lambda: None).pack(side='left', padx=2)
        nav = ttk.Frame(win)
        nav.pack(fill='x')
        btn_prev = ttk.Button(nav, text='<', command=lambda: (page.__setitem__(0, max(0, page[0]-1)), populate()))
        btn_prev.pack(side='left', padx=5)
        nav_lbl = ttk.Label(nav, text='Page 1')
        nav_lbl.pack(side='left', padx=5)
        btn_next = ttk.Button(nav, text='>', command=lambda: (page.__setitem__(0, min(page[0]+1, (len(tickers)-1)//items_per_page)), populate()))
        btn_next.pack(side='left', padx=5)
        def update_etf_panel():
            etf_panel.update(self.market_data.get_etf_data())
            win.after(1000, update_etf_panel)
        update_etf_panel()
        populate()

    def open_opt50_general_window(self):
        import pandas as pd
        COLUMNS = [
            'Seç', 'Ticker', 'Last price', 'Previous close', 'Bid', 'Ask', 'Volume', 'Spread',
            'Benchmark type', 'Benchmark chg',
            'CMON', 'Group', 'AVG_ADV', 'Final_Shares', 'FINAL_THG',
            'PF Bid buy', 'PF bid buy chg', 'Bid buy Ucuzluk Skoru',
            'PF front buy', 'PF front buy chg', 'Front buy ucuzluk skoru',
            'PF ask buy', 'PF ask buy chg', 'Ask buy ucuzluk skoru',
            'PF Ask sell', 'PF Ask sell chg', 'Ask sell pahalilik skoru',
            'PF front sell', 'PF front sell chg', 'Front sell pahalilik skoru',
            'PF bid sell', 'PF bid sell chg', 'Bid sell pahalilik skoru'
        ]
        LONG_HEADER = "Long pozisyon açmak / arttırmak için, veya Short pozisyon kapatmak/azaltmak için"
        SHORT_HEADER = "Short pozisyon açmak / arttırmak için, veya Long pozisyon kapatmak/azaltmak için"
        # CSV oku
        df = pd.read_csv('optimized_50_stocks_portfolio.csv')
        # Güncel market verisi
        market_data_dict = self.market_data.get_market_data([self.ticker_map.get(str(row['PREF IBKR']).strip(), str(row['PREF IBKR']).strip()) for _, row in df.iterrows()])
        etf_data = self.market_data.get_etf_data()
        rows = []
        pff_chg = etf_data.get('PFF', {}).get('change', 0)
        tlt_chg = etf_data.get('TLT', {}).get('change', 0)
        for _, row in df.iterrows():
            ticker = str(row['PREF IBKR']).strip()
            poly = self.ticker_map.get(ticker, ticker)
            md = market_data_dict.get(poly, {})
            last = md.get('last', 'N/A')
            prev_close = md.get('prev_close', 'N/A')
            bid = md.get('bid', 'N/A')
            ask = md.get('ask', 'N/A')
            volume = md.get('volume', 'N/A')
            try:
                spread = float(ask) - float(bid)
            except:
                spread = 'N/A'
            if ticker in self.historical_tickers:
                cgrup = self.tpref_cgrup_map.get(ticker, '')
                benchmark_type = f'T-{cgrup}' if cgrup else 'T'
                benchmark_chg = self.get_tpref_benchmark(ticker, pff_chg, tlt_chg)
            elif ticker in self.extended_tickers or ticker in self.c_type_extra_tickers:
                benchmark_type = 'C'
                try:
                    benchmark_chg = etf_data['PFF']['change'] * 1.3 - etf_data['TLT']['change'] * 0.1
                except:
                    benchmark_chg = 'N/A'
            else:
                benchmark_type = ''
                benchmark_chg = 'N/A'
            cmon = row.get('CMON', '')
            group = row.get('Group', '')
            avg_adv = row.get('AVG_ADV', '')
            final_shares = row.get('Final_Shares', '')
            final_thg = row.get('FINAL_THG', '')
            # PF ve skor hesapları
            def safe_float(x):
                try: return float(x)
                except: return None
            bid_f = safe_float(bid)
            ask_f = safe_float(ask)
            last_f = safe_float(last)
            prev_close_f = safe_float(prev_close)
            spread_f = safe_float(spread)
            bench_f = safe_float(benchmark_chg)
            # Long/cover
            pf_bid_buy = bid_f + spread_f * 0.15 if bid_f is not None and spread_f is not None else 'N/A'
            pf_bid_buy_chg = round(pf_bid_buy - prev_close_f, 3)
            bid_buy_ucuzluk = round(pf_bid_buy_chg - bench_f if pf_bid_buy_chg != 'N/A' and bench_f is not None else 'N/A', 3)
            pf_front_buy = last_f + 0.01 if last_f is not None else 'N/A'
            pf_front_buy_chg = round(pf_front_buy - prev_close_f, 3)
            front_buy_ucuzluk = round(pf_front_buy_chg - bench_f if pf_front_buy_chg != 'N/A' and bench_f is not None else 'N/A', 3)
            pf_ask_buy = ask_f + 0.01 if ask_f is not None else 'N/A'
            pf_ask_buy_chg = round(pf_ask_buy - prev_close_f, 3)
            ask_buy_ucuzluk = round(pf_ask_buy_chg - bench_f if pf_ask_buy_chg != 'N/A' and bench_f is not None else 'N/A', 3)
            # Short/cover
            pf_ask_sell = ask_f - spread_f * 0.15 if ask_f is not None and spread_f is not None else 'N/A'
            pf_ask_sell_chg = round(pf_ask_sell - prev_close_f, 3)
            ask_sell_pahali = round(pf_ask_sell_chg - bench_f if pf_ask_sell_chg != 'N/A' and bench_f is not None else 'N/A', 3)
            pf_front_sell = last_f - 0.01 if last_f is not None else 'N/A'
            pf_front_sell_chg = round(pf_front_sell - prev_close_f, 3)
            front_sell_pahali = round(pf_front_sell_chg - bench_f if pf_front_sell_chg != 'N/A' and bench_f is not None else 'N/A', 3)
            pf_bid_sell = bid_f - 0.01 if bid_f is not None else 'N/A'
            pf_bid_sell_chg = round(pf_bid_sell - prev_close_f, 3)
            bid_sell_pahali = round(pf_bid_sell_chg - bench_f if pf_bid_sell_chg != 'N/A' and bench_f is not None else 'N/A', 3)
            row_tuple = [
                '', ticker, last, prev_close, bid, ask, volume, spread,
                benchmark_type, benchmark_chg,
                cmon, group, avg_adv, final_shares, final_thg,
                pf_bid_buy, pf_bid_buy_chg, bid_buy_ucuzluk,
                pf_front_buy, pf_front_buy_chg, front_buy_ucuzluk,
                pf_ask_buy, pf_ask_buy_chg, ask_buy_ucuzluk,
                pf_ask_sell, pf_ask_sell_chg, ask_sell_pahali,
                pf_front_sell, pf_front_sell_chg, front_sell_pahali,
                pf_bid_sell, pf_bid_sell_chg, bid_sell_pahali
            ]
            rows.append(row_tuple)
        win = GeneralWindow(self, "Opt50 Maltopla", COLUMNS, LONG_HEADER, SHORT_HEADER)
        for row in rows:
            win.table.insert('', 'end', values=row) 

    def open_t_top_losers_maltopla(self, on_close_callback=None):
        """T-top losers maltopla penceresini aç"""
        print("[MAIN] T-top losers maltopla penceresi açılıyor")
        
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        
        # ✅ PISDoNGU durumuna göre başlık belirle
        base_title = "T-top Losers - Maltopla"
        
        # PSFAlgo1 kontrolü (yeni 8 adımlı sistem)
        if hasattr(self, 'psf_algo1') and self.psf_algo1 and self.psf_algo1.is_active:
            chain_title = self.psf_algo1.get_chain_state_title()
            if chain_title:
                title = f"{chain_title} | {base_title}"
            else:
                title = base_title
        # PSFAlgo2 kontrolü (eski 6 adımlı sistem)
        elif hasattr(self, 'psf_algo2') and self.psf_algo2 and self.psf_algo2.is_active:
            chain_title = self.psf_algo2.get_chain_state_title()
            if chain_title:
                title = f"{chain_title} | {base_title}"
            else:
                title = base_title
        # Eski PSFAlgo kontrolü (backward compatibility)
        elif hasattr(self, 'psf_algo') and self.psf_algo and self.psf_algo.is_active:
            chain_title = self.psf_algo.get_chain_state_title()
            if chain_title:
                title = f"{chain_title} | {base_title}"
            else:
                title = base_title
        else:
            title = base_title
        
        # ✅ mastermind_histport.csv'den ticker listesi al (benchmark hesaplama için)
        df = pd.read_csv('mastermind_histport.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        
        # ✅ Market data al
        market_data_dict = self.market_data.get_market_data(tickers)
        
        # ✅ ETF data'yı market_data'dan al
        etf_data = self.market_data.get_etf_data()
        
        # ✅ mastermind_histport.csv kullan (benchmark hesaplama düzgün çalışsın diye)
        win = MaltoplaWindow(self, title, 'mastermind_histport.csv', market_data_dict, etf_data, 'T', self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: (win.destroy(), on_close_callback() if on_close_callback else None))

    def open_t_top_gainers_maltopla(self, on_close_callback=None):
        """T-top gainers maltopla penceresini aç"""
        print("[MAIN] T-top gainers maltopla penceresi açılıyor")
        
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        
        # ✅ PISDoNGU durumuna göre başlık belirle
        base_title = "T-top Gainers - Maltopla"
        
        # PSFAlgo1 kontrolü (yeni 8 adımlı sistem)
        if hasattr(self, 'psf_algo1') and self.psf_algo1 and self.psf_algo1.is_active:
            chain_title = self.psf_algo1.get_chain_state_title()
            if chain_title:
                title = f"{chain_title} | {base_title}"
            else:
                title = base_title
        # PSFAlgo2 kontrolü (eski 6 adımlı sistem)
        elif hasattr(self, 'psf_algo2') and self.psf_algo2 and self.psf_algo2.is_active:
            chain_title = self.psf_algo2.get_chain_state_title()
            if chain_title:
                title = f"{chain_title} | {base_title}"
            else:
                title = base_title
        # Eski PSFAlgo kontrolü (backward compatibility)
        elif hasattr(self, 'psf_algo') and self.psf_algo and self.psf_algo.is_active:
            chain_title = self.psf_algo.get_chain_state_title()
            if chain_title:
                title = f"{chain_title} | {base_title}"
            else:
                title = base_title
        else:
            title = base_title
        
        # ✅ mastermind_histport.csv'den ticker listesi al (benchmark hesaplama için)
        df = pd.read_csv('mastermind_histport.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        
        # ✅ Market data al
        market_data_dict = self.market_data.get_market_data(tickers)
        
        # ✅ ETF data'yı market_data'dan al
        etf_data = self.market_data.get_etf_data()
        
        # ✅ mastermind_histport.csv kullan (benchmark hesaplama düzgün çalışsın diye)
        win = MaltoplaWindow(self, title, 'mastermind_histport.csv', market_data_dict, etf_data, 'T', self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: (win.destroy(), on_close_callback() if on_close_callback else None))

    def open_short_take_profit_window(self, on_close_callback=None):
        """Short take profit penceresi aç"""
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        import pandas as pd
        
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        
        # Short pozisyonları al
        positions = [pos for pos in self.market_data.get_positions() if pos['quantity'] < 0]
        tickers = [pos['symbol'] for pos in positions]
        
        # Güncel skorları oku
        try:
            final_df = pd.read_csv('mastermind_histport.csv')
        except Exception:
            final_df = pd.DataFrame()
            
        final_thg_map = dict(zip(final_df['PREF IBKR'], final_df['FINAL_THG'])) if not final_df.empty else {}
        avg_adv_map = dict(zip(final_df['PREF IBKR'], final_df['AVG_ADV'])) if not final_df.empty else {}
        
        df = pd.DataFrame({
            'PREF IBKR': tickers,
            'Quantity': [pos['quantity'] for pos in positions],  # Negatif değerler olacak
            'FINAL_THG': [final_thg_map.get(t, '') for t in tickers],
            'AVG_ADV': [avg_adv_map.get(t, '') for t in tickers],
        })
        
        # Convert tickers to Polygon format
        poly_tickers = [polygonize_ticker(t) for t in tickers]
        market_data_dict = self.market_data.get_market_data(poly_tickers)
        etf_data = self.market_data.get_etf_data()
        
        win = MaltoplaWindow(self, "Short take profit", df, market_data_dict, etf_data, 
                           benchmark_type='T', ibkr_client=self.market_data.ib, 
                           exdiv_data=self.exdiv_data, c_ticker_to_csv=self.c_ticker_to_csv, 
                           c_csv_data=self.c_csv_data)
        
        if on_close_callback:
            win.protocol("WM_DELETE_WINDOW", lambda: (self.close_maltopla_window(win), on_close_callback()))
        else:
            win.protocol("WM_DELETE_WINDOW", lambda: self.close_maltopla_window(win))

    def load_exdiv_list(self):
        file_path = filedialog.askopenfilename(title="Select Ex-Div List File", filetypes=[("Text/CSV Files", "*.txt *.csv")])
        if not file_path:
            return
        try:
            # Try reading as CSV, fallback to manual parsing
            try:
                df = pd.read_csv(file_path, header=None)
                tickers = df.iloc[:, 0].astype(str).str.strip()
                dividends = df.iloc[:, 3]
            except Exception:
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                tickers, dividends = [], []
                for line in lines:
                    parts = line.strip().split('\t') if '\t' in line else line.strip().split()
                    if len(parts) >= 4:
                        tickers.append(parts[0])
                        dividends.append(parts[3])
            self.exdiv_data = {t: d for t, d in zip(tickers, dividends)}
            self.show_exdiv_popup()
        except Exception as e:
            messagebox.showerror("Ex-Div List Error", f"Failed to load ex-div list: {e}")

    def show_exdiv_popup(self):
        win = tk.Toplevel(self)
        win.title("Today's Ex-Div List")
        table = ttk.Treeview(win, columns=("Ticker", "Dividend"), show='headings')
        table.heading("Ticker", text="Ticker")
        table.heading("Dividend", text="Dividend (cent)")
        table.column("Ticker", width=100, anchor='center')
        table.column("Dividend", width=100, anchor='center')
        for ticker, div in self.exdiv_data.items():
            table.insert('', 'end', values=(ticker, div))
        table.pack(fill='both', expand=True, padx=10, pady=10)

    def paste_exdiv_list(self):
        import re
        from datetime import datetime
        import os
        import pandas as pd
        
        win = tk.Toplevel(self)
        win.title("Paste Ex-Div List")
        win.geometry("700x540")
        label = ttk.Label(win, text="Paste MarketChameleon Ex-Div List Below:")
        label.pack(pady=5)
        text = tk.Text(win, wrap='word', font=("Consolas", 10))
        text.pack(fill='both', expand=True, padx=10, pady=5)
        result_table = None
        
        def exdiv_to_internal(ticker):
            if '-' in ticker:
                base, suf = ticker.split('-', 1)
                return f"{base} PR{suf.upper()}"
            return ticker
            
        def save_to_csv():
            try:
                if not hasattr(self, 'exdiv_data') or not self.exdiv_data:
                    messagebox.showwarning("Warning", "No data to save. Please parse the data first.")
                    return
                    
                # Create exdivkayit directory if it doesn't exist
                exdiv_dir = os.path.join('Htahaf', 'exdivkayit')
                if not os.path.exists(exdiv_dir):
                    os.makedirs(exdiv_dir)
                
                # Generate filename with current date (e.g., p140625.csv)
                current_date = datetime.now().strftime('%d%m%y')
                filename = f"p{current_date}.csv"
                filepath = os.path.join(exdiv_dir, filename)
                
                # Save data to CSV
                df = pd.DataFrame(list(self.exdiv_data.items()), columns=['Ticker', 'Dividend'])
                df.to_csv(filepath, index=False)
                messagebox.showinfo("Success", f"Data saved to {filename}")
                
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save data: {str(e)}")
        
        def load_todays_data():
            try:
                # Try to load today's data
                current_date = datetime.now().strftime('%d%m%y')
                filename = f"p{current_date}.csv"
                filepath = os.path.join('Htahaf', 'exdivkayit', filename)
                
                if os.path.exists(filepath):
                    df = pd.read_csv(filepath)
                    self.exdiv_data = dict(zip(df['Ticker'], df['Dividend']))
                    self.update_tables()
                    messagebox.showinfo("Success", f"Loaded today's data from {filename}")
                else:
                    messagebox.showinfo("Info", "No data file found for today.")
                    
            except Exception as e:
                messagebox.showerror("Load Error", f"Failed to load data: {str(e)}")
        
        def parse():
            nonlocal result_table
            try:
                if result_table:
                    result_table.destroy()
                lines = text.get("1.0", tk.END).splitlines()
                exdivs = []
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    # Atla: boş satır veya başlık
                    if not line or line.startswith('Symbol') or line.startswith('Name'):
                        i += 1
                        continue
                    m = re.match(r'^([A-Z0-9\-]+)Add', line)
                    ticker = m.group(1) if m else None
                    if ticker and i+1 < len(lines):
                        data_line = lines[i+1]
                        div_amt = None
                        # Yüzde işaretinden sonra miktar bulmaya çalış
                        percent_indices = [m.start() for m in re.finditer('%', data_line)]
                        for percent_idx in percent_indices:
                            after_percent = data_line[percent_idx+1:]
                            after_percent = after_percent.lstrip()
                            if not after_percent:
                                continue
                            if after_percent[0].isalpha():
                                continue
                            match = re.match(r'([0-9]+(\.[0-9]+)?)', after_percent)
                            if match:
                                val = float(match.group(1))
                                if 0 < val < 100:
                                    div_amt = val
                                    break
                        if div_amt is None:
                            floats = []
                            for p in re.split(r'\s|\t', data_line):
                                try:
                                    f = float(p)
                                    floats.append(f)
                                except:
                                    continue
                            for f in floats:
                                if 0 < f < 100:
                                    div_amt = f
                                    break
                        if div_amt:
                            exdivs.append((ticker, div_amt))
                        i += 2
                    else:
                        i += 1
                self.exdiv_data = {exdiv_to_internal(t): d for t, d in exdivs}
                if not exdivs:
                    messagebox.showinfo("No Data", f"No ex-dividend entries found.")
                    return
                result_table = ttk.Treeview(win, columns=("Ticker", "Dividend"), show='headings')
                result_table.heading("Ticker", text="Ticker")
                result_table.heading("Dividend", text="Dividend (cent)")
                result_table.column("Ticker", width=100, anchor='center')
                result_table.column("Dividend", width=120, anchor='center')
                for ticker, div in exdivs:
                    result_table.insert('', 'end', values=(ticker, div))
                result_table.pack(fill='x', padx=10, pady=10)
            except Exception as e:
                messagebox.showerror("Parse Error", f"Hata oluştu: {e}")
                
        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=5)
        btn_parse = ttk.Button(btn_frame, text="Parse", command=parse)
        btn_parse.pack(side='left', padx=5)
        btn_apply = ttk.Button(btn_frame, text="Uygula", command=self.update_tables)
        btn_apply.pack(side='left', padx=5)
        btn_save = ttk.Button(btn_frame, text="CSV'ye Kaydet", command=save_to_csv)
        btn_save.pack(side='left', padx=5)
        
        # Try to load today's data when window opens
        load_todays_data()

    def toggle_auto_data(self):
        if not self.auto_data_running:
            self.auto_data_running = True
            self.btn_auto_data.config(text="AutoDataON")
            self.auto_data_counter = 0
            self.run_auto_data()
        else:
            self.auto_data_running = False
            self.btn_auto_data.config(text="AutoDataOFF")
            if hasattr(self, 'auto_data_job_etf') and self.auto_data_job_etf:
                self.after_cancel(self.auto_data_job_etf)
                self.auto_data_job_etf = None

    def run_auto_data(self):
        if not self.auto_data_running:
            return
        import threading
        def run_data():
            self.update_data_once()
        threading.Thread(target=run_data, daemon=True).start()
        self.auto_data_job = self.after(45000, self.run_auto_data)

    def on_etf_spike(self, symbol, pct_chg):
        # Ana thread'de update_data_once çağır
        self.after(0, self.update_data_once)

    def close_maltopla_window(self, win):
        # if win in self.maltopla_windows:
        #     self.maltopla_windows.remove(win)
        win.destroy()

    def start_psf_algo_chain(self):
        # 1. T-top losers
        def after_t_top_losers():
            # 2. T-top gainers
            def after_t_top_gainers():
                # 3. Long take profit (ve Front sell)
                def after_long_take_profit():
                    # 4. Short take profit (ve Front buy)
                    def after_short_take_profit():
                        # 5. PsfAlgo OFF
                        self.btn_psf_algo.config(text="PsfAlgo OFF", style='TButton')
                        self.psf_algo = None
                    self.open_short_take_profit_window(on_close_callback=after_short_take_profit)
                self.open_long_take_profit_window(on_close_callback=after_long_take_profit)
            self.open_t_top_gainers_maltopla(on_close_callback=after_t_top_gainers)
        self.open_t_top_losers_maltopla(on_close_callback=after_t_top_losers)

    def activate_psf_algo(self):
        """PSFAlgo'yu aktif/pasif hale getir"""
        # PSFAlgo instance'ı yoksa oluştur
        if not hasattr(self, 'psf_algo') or self.psf_algo is None:
            # ✅ Order manager'ı da geç
            if not hasattr(self, 'order_manager'):
                from Htahaf.utils.order_management import OrderManager
                self.order_manager = OrderManager()
            
            self.psf_algo = PsfAlgo(self.market_data, exclude_list=self.psfalgo_exclude, order_manager=self.order_manager)
            
            # ✅ Ana pencere referansını ayarla
            self.psf_algo.set_main_window(self)
            
            # ✅ IBKR bağlıysa fill event'lere bağla
            if self.market_data.ib_connected:
                self.market_data.set_psf_algo(self.psf_algo)
                print("[MAIN] PSFAlgo oluşturuldu ve IBKR fill event'lerine bağlandı")
        
        # PSFAlgo durumunu toggle et
        if self.psf_algo.is_active:
            # Şu anda aktif -> pasif yap
            self.psf_algo.deactivate()
            self.btn_psf_algo.config(text="PsfAlgo OFF")
            self.btn_psf_algo.config(style='TButton')
            print("[GUI] 🔴 PSFAlgo KAPALI")
        else:
            # Şu anda pasif -> aktif yap ve chain'i başlat
            self.psf_algo.activate()
            self.btn_psf_algo.config(text="PsfAlgo ON")
            self.btn_psf_algo.config(style='Accent.TButton')
            print("[GUI] 🟢 PSFAlgo AÇIK - Chain başlatılıyor")

    def activate_psf_algo1(self):
        """PSFAlgo1'i aktif/pasif et (İLK 8 ADIM)"""
        # PSFAlgo1 durumunu toggle et
        if self.psf_algo1.is_active:
            # Şu anda aktif -> pasif yap
            self.psf_algo1.deactivate()
            self.btn_psf_algo1.config(text="PsfAlgo1 OFF")
            self.btn_psf_algo1.config(style='TButton')
            print("[GUI] 🔴 PSFAlgo1 KAPALI")
        else:
            # Şu anda pasif -> aktif yap ve chain'i başlat
            # ✅ IBKR bağlıysa fill event'lere bağla
            if self.market_data.ib_connected:
                self.market_data.set_psf_algo(self.psf_algo1)
                print("[MAIN] PSFAlgo1, IBKR fill event'lerine bağlandı")
            
            self.psf_algo1.activate()
            self.btn_psf_algo1.config(text="PsfAlgo1 ON")
            self.btn_psf_algo1.config(style='Accent.TButton')
            print("[GUI] 🟢 PSFAlgo1 AÇIK - YENİ 8 ADIMLI SİSTEM başlatılıyor")

    def activate_psf_algo2(self):
        """PSFAlgo2'yi aktif/pasif et (ESKİ 6 ADIM)"""
        # PSFAlgo2 durumunu toggle et
        if self.psf_algo2.is_active:
            # Şu anda aktif -> pasif yap
            self.psf_algo2.deactivate()
            self.btn_psf_algo2.config(text="PsfAlgo2 OFF")
            self.btn_psf_algo2.config(style='TButton')
            print("[GUI] 🔴 PSFAlgo2 KAPALI")
        else:
            # Şu anda pasif -> aktif yap ve chain'i başlat
            # ✅ IBKR bağlıysa fill event'lere bağla
            if self.market_data.ib_connected:
                self.market_data.set_psf_algo(self.psf_algo2)
                print("[MAIN] PSFAlgo2, IBKR fill event'lerine bağlandı")
            
            self.psf_algo2.activate()
            self.btn_psf_algo2.config(text="PsfAlgo2 ON")
            self.btn_psf_algo2.config(style='Accent.TButton')
            print("[GUI] 🟢 PSFAlgo2 AÇIK - ESKİ 6 ADIMLI SİSTEM başlatılıyor")

    def run_long_take_profit(self):
        """Long pozisyonlar için take profit işlemleri"""
        try:
            # Mevcut long pozisyonları al
            positions = [pos for pos in self.market_data.get_positions() if pos['quantity'] > 0]
            if not positions:
                return
                
            # Her pozisyon için ask sell pahalilik skorunu ve spread'i kontrol et
            for pos in positions:
                ticker = pos['symbol']
                quantity = pos['quantity']
                
                try:
                    # Skorları oku
                    final_df = pd.read_csv('mastermind_histport.csv')
                    score = final_df[final_df['PREF IBKR'] == ticker]['Ask sell pahalilik skoru'].iloc[0]
                    
                    # Market data'dan fiyatları al
                    market_data = self.market_data.get_market_data([ticker])
                    if ticker in market_data:
                        data = market_data[ticker]
                        bid = float(data.get('bid', 0))
                        ask = float(data.get('ask', 0))
                        spread = ask - bid
                        
                        # Koşulları kontrol et:
                        # 1. Ask sell pahalilik skoru > 0.05
                        # 2. Spread > 0.04
                        if score > 0.05 and spread > 0.04:
                            # %20'lik kısmı hesapla
                            target_size = int(quantity * 0.2)
                            
                            # Lot sınırlamalarını uygula
                            if target_size < 200:
                                target_size = min(200, quantity)  # En az 200 veya mevcut miktar
                            elif target_size > 800:
                                target_size = 800  # En fazla 800
                            
                            # Hidden sell emri gönder
                            hidden_price = ask - (spread * 0.15)
                            if hasattr(self.market_data, 'place_order'):
                                success = self.market_data.place_order(
                                    ticker, 'SELL', target_size, 
                                    price=hidden_price, 
                                    order_type='LIMIT'
                                )
                                if success:
                                    print(f"Long take profit emri gönderildi: {ticker} {target_size} lot @ {hidden_price}")
                                    print(f"Skor: {score}, Spread: {spread}")
                except Exception as e:
                    print(f"Error processing {ticker}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error in run_long_take_profit: {e}")

    def run_short_take_profit(self):
        """Short pozisyonlar için take profit işlemleri"""
        try:
            # Mevcut short pozisyonları al
            positions = [pos for pos in self.market_data.get_positions() if pos['quantity'] < 0]
            if not positions:
                return
                
            # Her pozisyon için bid buy ucuzluk skorunu ve spread'i kontrol et
            for pos in positions:
                ticker = pos['symbol']
                quantity = abs(pos['quantity'])  # Mutlak değer
                
                try:
                    # Skorları oku
                    final_df = pd.read_csv('mastermind_histport.csv')
                    score = final_df[final_df['PREF IBKR'] == ticker]['Bid buy Ucuzluk skoru'].iloc[0]
                    
                    # Market data'dan fiyatları al
                    market_data = self.market_data.get_market_data([ticker])
                    if ticker in market_data:
                        data = market_data[ticker]
                        bid = float(data.get('bid', 0))
                        ask = float(data.get('ask', 0))
                        spread = ask - bid
                        
                        # Koşulları kontrol et:
                        # 1. Bid buy ucuzluk skoru < -0.05
                        # 2. Spread > 0.04
                        if score < -0.05 and spread > 0.04:
                            # %20'lik kısmı hesapla
                            target_size = int(quantity * 0.2)
                            
                            # Lot sınırlamalarını uygula
                            if target_size < 200:
                                target_size = min(200, quantity)  # En az 200 veya mevcut miktar
                            elif target_size > 800:
                                target_size = 800  # En fazla 800
                            
                            # Hidden buy emri gönder
                            hidden_price = bid + (spread * 0.15)
                            if hasattr(self.market_data, 'place_order'):
                                success = self.market_data.place_order(
                                    ticker, 'BUY', target_size, 
                                    price=hidden_price, 
                                    order_type='LIMIT'
                                )
                                if success:
                                    print(f"Short take profit emri gönderildi: {ticker} {target_size} lot @ {hidden_price}")
                                    print(f"Skor: {score}, Spread: {spread}")
                except Exception as e:
                    print(f"Error processing {ticker}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error in run_short_take_profit: {e}")

    def open_maturex_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('maturextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "Maturex", "maturextlt.csv", market_data_dict, etf_data, benchmark_type='Mat', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_nffex_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('nffextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "NFFex", "nffextlt.csv", market_data_dict, etf_data, benchmark_type='NFF', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_ffex_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('ffextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "FFex", "ffextlt.csv", market_data_dict, etf_data, benchmark_type='FF', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_flrex_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('flrextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "FLRex", "flrextlt.csv", market_data_dict, etf_data, benchmark_type='FLR', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_duzex_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('duzextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "Duzex", "duzextlt.csv", market_data_dict, etf_data, benchmark_type='Duz', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_maturex_maltopla_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('maturextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "Maturex Maltopla", "maturextlt.csv", market_data_dict, etf_data, benchmark_type='Mat', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_nffex_maltopla_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('nffextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "NFFex Maltopla", "nffextlt.csv", market_data_dict, etf_data, benchmark_type='NFF', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_ffex_maltopla_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('ffextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "FFex Maltopla", "ffextlt.csv", market_data_dict, etf_data, benchmark_type='FF', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_flrex_maltopla_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('flrextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "FLRex Maltopla", "flrextlt.csv", market_data_dict, etf_data, benchmark_type='FLR', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_duzex_maltopla_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('duzextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "Duzex Maltopla", "duzextlt.csv", market_data_dict, etf_data, benchmark_type='Duz', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_maturex_top_losers_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('maturextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "Maturex-top losers", "maturextlt.csv", market_data_dict, etf_data, benchmark_type='Mat', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_maturex_top_gainers_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('maturextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "Maturex-top gainers", "maturextlt.csv", market_data_dict, etf_data, benchmark_type='Mat', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_nffex_top_losers_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('nffextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "NFFex-top losers", "nffextlt.csv", market_data_dict, etf_data, benchmark_type='NFF', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_nffex_top_gainers_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('nffextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "NFFex-top gainers", "nffextlt.csv", market_data_dict, etf_data, benchmark_type='NFF', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_ffex_top_losers_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('ffextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "FFex-top losers", "ffextlt.csv", market_data_dict, etf_data, benchmark_type='FF', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_ffex_top_gainers_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('ffextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "FFex-top gainers", "ffextlt.csv", market_data_dict, etf_data, benchmark_type='FF', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_flrex_top_losers_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('flrextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "FLRex-top losers", "flrextlt.csv", market_data_dict, etf_data, benchmark_type='FLR', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_flrex_top_gainers_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('flrextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "FLRex-top gainers", "flrextlt.csv", market_data_dict, etf_data, benchmark_type='FLR', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_duzex_top_losers_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('duzextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "Duzex-top losers", "duzextlt.csv", market_data_dict, etf_data, benchmark_type='Duz', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def open_duzex_top_gainers_window(self):
        import pandas as pd
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        df = pd.read_csv('duzextlt.csv')
        tickers = [polygonize_ticker(str(row['PREF IBKR']).strip()) for _, row in df.iterrows()]
        market_data_dict = self.market_data.get_market_data(tickers)
        etf_data = self.market_data.get_etf_data()
        win = MaltoplaWindow(self, "Duzex-top gainers", "duzextlt.csv", market_data_dict, etf_data, benchmark_type='Duz', ibkr_client=self.market_data.ib, exdiv_data=self.exdiv_data)
        win.protocol("WM_DELETE_WINDOW", lambda w=win: self.close_maltopla_window(w))

    def load_bdata(self):
        path = os.path.abspath(self.bdata_path)
        if os.path.exists(path):
            try:
                return pd.read_csv(path).to_dict('records')
            except Exception:
                return []
        return []

    def save_bdata(self):
        path = os.path.abspath(self.bdata_path)
        df = pd.DataFrame(self.bdata)
        df.to_csv(path, index=False)

    def update_bdata_with_fill(self, fill):
        # fill: OrderFill objesi
        ticker = fill.ticker
        size = fill.fill_size
        price = fill.fill_price
        bench = fill.benchmark_at_fill
        direction = fill.direction
        # BDATA'da var mı?
        found = None
        for row in self.bdata:
            if row['Ticker'] == ticker:
                found = row
                break
        # Pozisyon artırıcı/azaltıcı mantık
        is_increase = False
        if direction == 'long':
            is_increase = True
        elif direction == 'short':
            is_increase = True
        if found:
            if is_increase:
                total_size = found['Total Size'] + size
                found['Avg Cost'] = (found['Avg Cost'] * found['Total Size'] + price * size) / total_size
                found['Avg Benchmark'] = (found['Avg Benchmark'] * found['Total Size'] + bench * size) / total_size
                found['Total Size'] = total_size
                found['Fills'] = found['Fills'] + f", {price:.2f}/{size}/{bench:.2f}"
            else:
                found['Total Size'] -= size
                found['Fills'] = found['Fills'] + f", -{price:.2f}/{size}/{bench:.2f}"
                if found['Total Size'] <= 0:
                    self.bdata.remove(found)
            # Bench Type güncelle
            if ticker in self.historical_tickers:
                cgrup = self.tpref_cgrup_map.get(ticker, '')
                found['Bench Type'] = f'T-{cgrup}' if cgrup else 'T'
            elif ticker in self.extended_tickers or ticker in self.c_type_extra_tickers:
                found['Bench Type'] = 'C'
            else:
                found['Bench Type'] = ''
            # Güncel fiyat ve benchmarkı güncelle
            poly = polygonize_ticker(ticker)
            md = self.market_data.get_market_data([poly]).get(poly, {})
            etf_data = self.market_data.get_etf_data()
            pff_last = etf_data.get('PFF', {}).get('last', None)
            tlt_last = etf_data.get('TLT', {}).get('last', None)
            try:
                found['Current Price'] = float(md.get('last', found['Avg Cost']))
            except Exception:
                found['Current Price'] = found['Avg Cost']
            if found['Bench Type'].startswith('T-') or found['Bench Type'] == 'T':
                found['Current Benchmark'] = self.get_tpref_benchmark(ticker, pff_last, tlt_last)
            elif found['Bench Type'] == 'C':
                try:
                    found['Current Benchmark'] = float(pff_last) * 1.3 - float(tlt_last) * 0.1 if pff_last is not None and tlt_last is not None else None
                except Exception:
                    found['Current Benchmark'] = None
            else:
                found['Current Benchmark'] = None
        else:
            if is_increase:
                # Bench Type belirle
                if ticker in self.historical_tickers:
                    cgrup = self.tpref_cgrup_map.get(ticker, '')
                    bench_type = f'T-{cgrup}' if cgrup else 'T'
                elif ticker in self.extended_tickers or ticker in getattr(self, 'c_type_extra_tickers', set()):
                    bench_type = 'C'
                else:
                    bench_type = ''
                # Güncel fiyat ve benchmarkı belirle
                poly = polygonize_ticker(ticker)
                md = self.market_data.get_market_data([poly]).get(poly, {})
                etf_data = self.market_data.get_etf_data()
                pff_last = etf_data.get('PFF', {}).get('last', None)
                tlt_last = etf_data.get('TLT', {}).get('last', None)
                try:
                    current_price = float(md.get('last', price))
                except Exception:
                    current_price = price
                if bench_type.startswith('T-') or bench_type == 'T':
                    current_bench = self.get_tpref_benchmark(ticker, pff_last, tlt_last)
                elif bench_type == 'C':
                    try:
                        current_bench = float(pff_last) * 1.3 - float(tlt_last) * 0.1 if pff_last is not None and tlt_last is not None else None
                    except Exception:
                        current_bench = None
                else:
                    current_bench = None
                self.bdata.append({
                    'Ticker': ticker,
                    'Total Size': size,
                    'Avg Cost': price,
                    'Avg Benchmark': bench,
                    'Bench Type': bench_type,
                    'Current Price': current_price,
                    'Current Benchmark': current_bench,
                    'Fills': f"{price:.2f}/{size}/{bench:.2f}"
                })
        self.save_bdata()

    def update_bdata_with_reduce(self, ticker, reduce_size):
        # Pozisyon azaltınca (ör: satış fill'i geldiğinde)
        for row in self.bdata:
            if row['Ticker'] == ticker:
                row['Total Size'] -= reduce_size
                if row['Total Size'] <= 0:
                    self.bdata.remove(row)
                break
        self.save_bdata()

    def open_bdata_window(self):
        """BDATA penceresi - PSFAlgo'dan bağımsız"""
        try:
            from Htahaf.utils.bdata_storage import BDataStorage
            from Htahaf.utils.benchmark_calculator import BenchmarkCalculator
        except ImportError:
            messagebox.showerror("Hata", "BDATA modülü bulunamadı!")
            return
            
        window = tk.Toplevel(self)
        window.title("🎯 BDATA - Pozisyon Analizi")
        window.geometry("1400x700")
        
        # Ana frame
        main_frame = ttk.Frame(window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Üst bilgi paneli
        info_frame = ttk.LabelFrame(main_frame, text="📊 Snapshot Sistemi", padding=10)
        info_frame.pack(fill='x', pady=(0, 10))
        
        info_text = """🎯 Snapshot Sistemi: Bugünkü fiyatları milat kabul ederek avg outperformance hesaplar.
• İlk kez kullanıyorsanız '📸 Bugün Snapshot Oluştur' butonuna basın.
• Tüm pozisyonları bugüne sıfırlamak için '🔄 Snapshot'ları Sıfırla' butonunu kullanın.
• Manuel fill eklemek için alt kısımdaki formu kullanabilirsiniz."""
        
        info_label = ttk.Label(info_frame, text=info_text, font=('Arial', 9))
        info_label.pack(anchor='w')
        
        # Buton paneli
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(0, 10))
        
        def create_snapshots():
            try:
                bdata = BDataStorage()
                bdata.create_snapshot_for_current_positions()
                messagebox.showinfo("Başarılı", "Mevcut pozisyonlar için snapshot oluşturuldu!")
                refresh_table()
            except Exception as e:
                messagebox.showerror("Hata", f"Snapshot oluşturma hatası: {e}")
        
        def reset_snapshots():
            try:
                bdata = BDataStorage()
                bdata.reset_all_snapshots_to_today()
                messagebox.showinfo("Başarılı", "Tüm snapshot'lar bugüne sıfırlandı!")
                refresh_table()
            except Exception as e:
                messagebox.showerror("Hata", f"Snapshot sıfırlama hatası: {e}")
        
        def export_csv():
            try:
                bdata = BDataStorage()
                success = bdata.update_csv()
                if success:
                    messagebox.showinfo("Başarılı", "BDATA CSV'ye kaydedildi!")
                else:
                    messagebox.showwarning("Uyarı", "Kaydedilecek pozisyon bulunamadı!")
            except Exception as e:
                messagebox.showerror("Hata", f"CSV kaydetme hatası: {e}")
        
        def load_from_ibkr():
            """IBKR'den mevcut pozisyonları yükle ve milat oluştur"""
            try:
                if not hasattr(self, 'market_data') or not self.market_data:
                    messagebox.showerror("Hata", "IBKR bağlantısı yok! Önce IBKR'a bağlanın.")
                    return
                
                if not hasattr(self.market_data, 'ib') or not self.market_data.ib or not self.market_data.ib.isConnected():
                    messagebox.showerror("Hata", "IBKR bağlantısı kapalı! Önce bağlantı kurun.")
                    return
                
                # Kullanıcı onayı al
                result = messagebox.askyesno(
                    "IBKR Pozisyon Yükleme", 
                    "Bu işlem mevcut BDATA'yı temizleyip IBKR'den pozisyonları yükleyecek.\n"
                    "Avg outperformance değerleri 0'a eşitlenecek (milat).\n\n"
                    "Devam etmek istiyor musunuz?"
                )
                
                if not result:
                    return
                
                # Benchmark calculator oluştur
                benchmark_calc = BenchmarkCalculator(self)
                
                # BDATA'ya yükle
                bdata = BDataStorage()
                success = bdata.load_ibkr_positions(self.market_data, benchmark_calc)
                
                if success:
                    messagebox.showinfo("Başarılı", 
                        "IBKR pozisyonları başarıyla BDATA'ya yüklendi!\n"
                        "Avg outperformance değerleri 0'a eşitlendi.")
                    refresh_table()
                else:
                    messagebox.showerror("Hata", "Pozisyon yükleme başarısız!")
                    
            except Exception as e:
                messagebox.showerror("Hata", f"IBKR yükleme hatası: {e}")
                import traceback
                traceback.print_exc()
        
        def update_fills_from_ibkr():
            """IBKR'den yeni fill'leri çek ve BDATA'yı güncelle"""
            try:
                if not hasattr(self, 'market_data') or not self.market_data:
                    messagebox.showerror("Hata", "IBKR bağlantısı yok!")
                    return
                
                if not hasattr(self.market_data, 'ib') or not self.market_data.ib or not self.market_data.ib.isConnected():
                    messagebox.showerror("Hata", "IBKR bağlantısı kapalı!")
                    return
                
                # Benchmark calculator oluştur
                benchmark_calc = BenchmarkCalculator(self)
                
                # Fill'leri güncelle (otomatik offline detection dahil)
                bdata = BDataStorage()
                success = bdata.update_with_ibkr_fills(self.market_data, benchmark_calc, hours_back=24)
                
                if success:
                    messagebox.showinfo("Başarılı", "IBKR fill'leri başarıyla güncellendi!")
                    refresh_table()
                else:
                    messagebox.showwarning("Bilgi", "Yeni fill bulunamadı veya güncelleme başarısız!")
                    
            except Exception as e:
                messagebox.showerror("Hata", f"Fill güncelleme hatası: {e}")
        
        def enable_auto_monitoring():
            """Otomatik fill monitoring'i etkinleştir"""
            try:
                if not hasattr(self, 'market_data') or not self.market_data:
                    messagebox.showerror("Hata", "IBKR bağlantısı yok!")
                    return
                
                if not hasattr(self.market_data, 'ib') or not self.market_data.ib or not self.market_data.ib.isConnected():
                    messagebox.showerror("Hata", "IBKR bağlantısı kapalı!")
                    return
                
                # Benchmark calculator oluştur
                benchmark_calc = BenchmarkCalculator(self)
                
                # Auto monitoring'i etkinleştir
                bdata = BDataStorage()
                bdata.enable_auto_fill_monitoring(self.market_data, benchmark_calc)
                
                messagebox.showinfo("Başarılı", 
                    "Otomatik fill monitoring etkinleştirildi!\n"
                    "Artık yeni fill'ler otomatik olarak BDATA'ya eklenecek.")
                    
            except Exception as e:
                messagebox.showerror("Hata", f"Auto monitoring hatası: {e}")
        
        def check_offline_fills():
            """Program açılışında offline fill'leri kontrol et"""
            try:
                if not hasattr(self, 'market_data') or not self.market_data:
                    messagebox.showinfo("Bilgi", "IBKR bağlantısı yok, offline fill kontrolü atlandı.")
                    return
                
                if not hasattr(self.market_data, 'ib') or not self.market_data.ib or not self.market_data.ib.isConnected():
                    messagebox.showinfo("Bilgi", "IBKR bağlantısı kapalı, offline fill kontrolü atlandı.")
                    return
                
                # Benchmark calculator oluştur
                benchmark_calc = BenchmarkCalculator(self)
                
                # Offline fill detection
                bdata = BDataStorage()
                success = bdata.detect_and_process_offline_fills(self.market_data, benchmark_calc)
                
                if success:
                    print("[BDATA GUI] ✅ Offline fill kontrolü tamamlandı")
                    refresh_table()
                else:
                    print("[BDATA GUI] ⚠️ Offline fill kontrolünde sorun")
                    
            except Exception as e:
                print(f"[BDATA GUI] ❌ Offline fill kontrol hatası: {e}")
        
        # Butonlar
        ttk.Button(button_frame, text="🔗 IBKR'den Pozisyon Yükle", 
                  command=load_from_ibkr).pack(side='left', padx=(0, 10))
        ttk.Button(button_frame, text="🔄 IBKR Fill'leri Güncelle", 
                  command=update_fills_from_ibkr).pack(side='left', padx=(0, 10))
        ttk.Button(button_frame, text="⚡ Otomatik Monitoring", 
                  command=enable_auto_monitoring).pack(side='left', padx=(0, 10))
        ttk.Button(button_frame, text="🔍 Offline Fill Kontrol", 
                  command=check_offline_fills).pack(side='left', padx=(0, 10))
        ttk.Button(button_frame, text="📸 Bugün Snapshot Oluştur", 
                  command=create_snapshots).pack(side='left', padx=(0, 10))
        ttk.Button(button_frame, text="🔄 Snapshot'ları Sıfırla", 
                  command=reset_snapshots).pack(side='left', padx=(0, 10))
        ttk.Button(button_frame, text="💾 BDATA'yı CSV'ye Kaydet", 
                  command=export_csv).pack(side='right')
        
        # Ana tablo frame'i
        table_frame = ttk.LabelFrame(main_frame, text="📊 Pozisyon Tablosu", padding=10)
        table_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        # Treeview oluştur
        columns = ('Ticker', 'Poly', 'Total Size', 'Avg Cost', 'Bench Type', 'Avg Benchmark', 
                  'Current Price', 'Current Benchmark', 'Avg Outperf', 'Fills')
        tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=15)
        
        # Sütun başlıklarını ayarla
        for col in columns:
            tree.heading(col, text=col)
            if col in ['Avg Cost', 'Current Price', 'Avg Benchmark', 'Current Benchmark', 'Avg Outperf']:
                tree.column(col, width=100, anchor='e')
            elif col in ['Total Size']:
                tree.column(col, width=80, anchor='e')
            else:
                tree.column(col, width=120)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Grid layout
        tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        # Tablo sıralama fonksiyonu
        def treeview_sort_column(tv, col, reverse):
            try:
                l = [(tv.set(k, col), k) for k in tv.get_children('')]
                
                def safe_float(x):
                    try:
                        return float(x)
                    except:
                        return 0.0
                
                if col in ['Total Size', 'Avg Cost', 'Current Price', 'Avg Benchmark', 'Current Benchmark', 'Avg Outperf']:
                    l.sort(key=lambda x: safe_float(x[0]), reverse=reverse)
                else:
                    l.sort(reverse=reverse)
                
                for index, (val, k) in enumerate(l):
                    tv.move(k, '', index)
                
                tv.heading(col, command=lambda: treeview_sort_column(tv, col, not reverse))
            except Exception as e:
                print(f"Sıralama hatası: {e}")
        
        # Sütun başlıklarına tıklama eventi
        for col in columns:
            tree.heading(col, command=lambda _col=col: treeview_sort_column(tree, _col, False))
        
        def refresh_table():
            """Tabloyu güncelle"""
            try:
                # Mevcut verileri temizle
                for item in tree.get_children():
                    tree.delete(item)
                
                # BDATA'dan verileri al
                bdata = BDataStorage()
                summary = bdata.get_position_summary_with_snapshot()
                
                if not summary:
                    # Veri yoksa bilgilendirme satırı ekle
                    tree.insert('', 'end', values=('Veri bulunamadı', '', '', '', '', '', '', '', '', ''))
                    return
                
                # Market data için tüm ticker'ları topla
                all_tickers = [ticker for (ticker, direction) in summary.keys()]
                poly_tickers = [polygonize_ticker(t) for t in all_tickers]
                
                # Market data ve ETF data al
                try:
                    market_data_dict = self.market_data.get_market_data(poly_tickers)
                    etf_data = self.market_data.get_etf_data()
                    pff_last = etf_data.get('PFF', {}).get('last', None)
                    tlt_last = etf_data.get('TLT', {}).get('last', None)
                except Exception as e:
                    print(f"[BDATA REFRESH] Market data alma hatası: {e}")
                    market_data_dict = {}
                    pff_last = None
                    tlt_last = None
                
                # Her pozisyon için satır ekle
                for (ticker, direction), data in summary.items():
                    # Gerçek market data'dan current price al (Long Take Profit'teki gibi)
                    poly_ticker = polygonize_ticker(ticker)
                    md = market_data_dict.get(poly_ticker, {})
                    
                    try:
                        current_price = float(md.get('last', 0))
                        # Last price = 0 veya N/A ise fallback kullan
                        if current_price <= 0:
                            # EXDIV uygulaması için previous close kontrol et
                            prev_close = md.get('prev_close', 0)
                            if prev_close and prev_close > 0:
                                current_price = float(prev_close)
                            else:
                                current_price = data['avg_cost']  # Son çare olarak avg_cost
                                print(f"[BDATA] {ticker}: Market data bulunamadı, avg_cost kullanılıyor")
                    except:
                        current_price = data['avg_cost']
                        print(f"[BDATA] {ticker}: Current price parse hatası, avg_cost kullanılıyor")
                    
                    # Benchmark tipi ve current benchmark hesapla (maltopla pencerelerindeki gibi)
                    if ticker in self.historical_tickers:
                        cgrup = self.tpref_cgrup_map.get(ticker, '')
                        bench_type = f'T-{cgrup}' if cgrup else 'T'
                        current_benchmark = self.get_tpref_benchmark(ticker, pff_last, tlt_last)
                    elif ticker in self.extended_tickers or ticker in getattr(self, 'c_type_extra_tickers', set()):
                        bench_type = 'C'
                        try:
                            current_benchmark = float(pff_last) * 1.3 - float(tlt_last) * 0.1 if pff_last is not None and tlt_last is not None else None
                        except:
                            current_benchmark = None
                    else:
                        bench_type = ''
                        current_benchmark = None
                    
                    # Avg benchmark'ı milat için hesapla (avg_outperformance = 0 olacak şekilde)
                    # avg_outperformance = (current_price - avg_cost) - (current_benchmark - avg_benchmark) = 0
                    # avg_benchmark = current_benchmark - (current_price - avg_cost)
                    if current_benchmark is not None:
                        calculated_avg_benchmark = current_benchmark - (current_price - data['avg_cost'])
                        
                        # Eğer BDATA'da avg_benchmark değeri varsa onu kullan, yoksa hesaplananı kullan
                        if 'avg_benchmark' in data and data['avg_benchmark'] is not None:
                            avg_benchmark_display = data['avg_benchmark']
                        else:
                            avg_benchmark_display = calculated_avg_benchmark
                            print(f"[BDATA] {ticker}: Avg benchmark hesaplandı: {calculated_avg_benchmark:.4f}")
                        
                        # Avg outperformance hesapla
                        avg_outperf = bdata.calculate_avg_outperformance(
                            ticker, current_price, current_benchmark
                        )
                    else:
                        avg_benchmark_display = data.get('avg_benchmark', 0.0)
                        avg_outperf = 0.0
                        print(f"[BDATA] {ticker}: Current benchmark hesaplanamadı")
                    
                    # Fills string
                    fills_str = f"{len(data['fills'])} fills"
                    
                    # Satırı ekle
                    tree.insert('', 'end', values=(
                        ticker,
                        poly_ticker,
                        data['total_size'],
                        f"{data['avg_cost']:.4f}",
                        bench_type,
                        f"{avg_benchmark_display:.4f}",
                        f"{current_price:.4f}",
                        f"{current_benchmark:.4f}" if current_benchmark is not None else "N/A",
                        f"{avg_outperf:.4f}",
                        fills_str
                    ))
                    
            except Exception as e:
                print(f"Tablo güncelleme hatası: {e}")
                import traceback
                traceback.print_exc()
        
        # Manuel fill ekleme paneli
        fill_frame = ttk.LabelFrame(main_frame, text="➕ Manuel Fill Ekleme", padding=10)
        fill_frame.pack(fill='x', pady=(10, 0))
        
        # Fill form elemanları
        form_frame = ttk.Frame(fill_frame)
        form_frame.pack(fill='x')
        
        ttk.Label(form_frame, text="Ticker:").grid(row=0, column=0, padx=(0, 5), sticky='w')
        ticker_entry = ttk.Entry(form_frame, width=10)
        ticker_entry.grid(row=0, column=1, padx=(0, 15))
        
        ttk.Label(form_frame, text="Direction:").grid(row=0, column=2, padx=(0, 5), sticky='w')
        direction_combo = ttk.Combobox(form_frame, values=['long', 'short'], width=8, state='readonly')
        direction_combo.grid(row=0, column=3, padx=(0, 15))
        direction_combo.set('long')
        
        ttk.Label(form_frame, text="Fiyat:").grid(row=0, column=4, padx=(0, 5), sticky='w')
        price_entry = ttk.Entry(form_frame, width=10)
        price_entry.grid(row=0, column=5, padx=(0, 15))
        
        ttk.Label(form_frame, text="Size:").grid(row=0, column=6, padx=(0, 5), sticky='w')
        size_entry = ttk.Entry(form_frame, width=10)
        size_entry.grid(row=0, column=7, padx=(0, 15))
        
        def add_manual_fill():
            try:
                ticker = ticker_entry.get().strip().upper()
                direction = direction_combo.get()
                price = float(price_entry.get())
                size = int(size_entry.get())
                
                if not ticker or not direction or price <= 0 or size <= 0:
                    messagebox.showerror("Hata", "Tüm alanları doğru doldurun!")
                    return
                
                bdata = BDataStorage()
                success = bdata.add_manual_fill(ticker, direction, price, size)
                
                if success:
                    messagebox.showinfo("Başarılı", f"{ticker} {direction} {size}@{price:.4f} fill eklendi!")
                    # Form temizle
                    ticker_entry.delete(0, 'end')
                    price_entry.delete(0, 'end')
                    size_entry.delete(0, 'end')
                    # Tabloyu güncelle
                    refresh_table()
                
            except ValueError:
                messagebox.showerror("Hata", "Fiyat ve Size numerik değer olmalı!")
            except Exception as e:
                messagebox.showerror("Hata", f"Fill ekleme hatası: {e}")
        
        ttk.Button(form_frame, text="➕ Fill Ekle", command=add_manual_fill).grid(row=0, column=8, padx=(15, 0))
        
        # İlk tabloyu yükle
        refresh_table()
        
        # Pencere boyutunu ayarla
        window.minsize(1200, 600)

    def init_bdata_from_ibkr(self):
        print("[DEBUG] init_bdata_from_ibkr başı")
        # --- FILL GEÇMİŞİ VARSA ONU KULLAN ---
        try:
            bdata_storage = BDataStorage()
            fill_summary = bdata_storage.get_open_position_summary()
        except Exception as e:
            print(f"[DEBUG] BDataStorage yüklenemedi: {e}")
            fill_summary = {}
        if fill_summary:
            print("[DEBUG] Fill geçmişinden başlatılıyor.")
            self.bdata = []
            etf_data = self.market_data.get_etf_data()
            pff_last = etf_data.get('PFF', {}).get('last', None)
            tlt_last = etf_data.get('TLT', {}).get('last', None)
            for (ticker, direction), val in fill_summary.items():
                size = val['total_size']
                if size == 0:
                    continue
                avg_cost = val['avg_cost']
                avg_bench = val['avg_benchmark']
                fills = val['fills']
                poly = polygonize_ticker(ticker)
                md = self.market_data.get_market_data([poly]).get(poly, {})
                try:
                    current_price = float(md.get('last', avg_cost))
                except Exception:
                    current_price = avg_cost
                # Bench Type ve current benchmark
                if ticker in self.historical_tickers:
                    cgrup = self.tpref_cgrup_map.get(ticker, '')
                    bench_type = f'T-{cgrup}' if cgrup else 'T'
                    current_bench = self.get_tpref_benchmark(ticker, pff_last, tlt_last)
                elif ticker in self.extended_tickers or ticker in getattr(self, 'c_type_extra_tickers', set()):
                    bench_type = 'C'
                    try:
                        current_bench = float(pff_last) * 1.3 - float(tlt_last) * 0.1 if pff_last is not None and tlt_last is not None else None
                    except Exception:
                        current_bench = None
                else:
                    bench_type = ''
                    current_bench = None
                self.bdata.append({
                    'Ticker': ticker,
                    'Poly': poly,
                    'Total Size': size,
                    'Avg Cost': avg_cost,
                    'Avg Benchmark': avg_bench,
                    'Bench Type': bench_type,
                    'Current Price': current_price,
                    'Current Benchmark': current_bench,
                    'Fills': ', '.join([f"{f['fill_price']:.2f}/{f['fill_size']}/{f['benchmark_at_fill']:.2f}" for f in fills])
                })
            print("[DEBUG] init_bdata_from_ibkr sonu (fill geçmişi), BDATA:", self.bdata)
            self.save_bdata()
            return
        # --- FILL GEÇMİŞİ YOKSA IBKR POZİSYONLARI İLE DEVAM ET ---
        try:
            positions = self.market_data.get_positions()
            print("[DEBUG] IBKR'den gelen pozisyonlar:", positions)
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("IBKR Pozisyon Hatası", f"IBKR pozisyonları alınamadı: {e}")
            self.bdata = []
            return
        if not positions:
            import tkinter.messagebox as mb
            mb.showinfo("Pozisyon Yok", "IBKR'de açık pozisyon bulunamadı.")
            self.bdata = []
            return
        tickers = [pos['symbol'] for pos in positions if pos['quantity'] != 0]
        poly_tickers = [polygonize_ticker(t) for t in tickers]
        market_data_dict = self.market_data.get_market_data(poly_tickers)
        etf_data = self.market_data.get_etf_data()
        pff_last = etf_data.get('PFF', {}).get('last', None)
        tlt_last = etf_data.get('TLT', {}).get('last', None)
        self.bdata = []
        for pos in positions:
            symbol = pos['symbol']
            size = pos['quantity']
            avg_cost = pos['avgCost']
            if size == 0:
                continue
            poly = polygonize_ticker(symbol)
            md = market_data_dict.get(poly, {})
            try:
                current_price = float(md.get('last', avg_cost))
            except Exception:
                current_price = avg_cost
            # Benchmark tipi ve güncel benchmark değeri
            if symbol in self.historical_tickers:
                cgrup = self.tpref_cgrup_map.get(symbol, '')
                bench_type = f'T-{cgrup}' if cgrup else 'T'
                current_bench = self.get_tpref_benchmark(symbol, pff_last, tlt_last)
            elif symbol in self.extended_tickers or symbol in getattr(self, 'c_type_extra_tickers', set()):
                bench_type = 'C'
                try:
                    current_bench = float(pff_last) * 1.3 - float(tlt_last) * 0.1 if pff_last is not None and tlt_last is not None else None
                except Exception:
                    current_bench = None
            else:
                bench_type = ''
                current_bench = None
            # Avg Benchmark: avg_cost - current_price + current_bench
            if current_bench is not None:
                avg_benchmark = avg_cost - current_price + current_bench
            else:
                avg_benchmark = ''
            self.bdata.append({
                'Ticker': symbol,
                'Poly': poly,
                'Total Size': size,
                'Avg Cost': avg_cost,
                'Avg Benchmark': avg_benchmark,
                'Bench Type': bench_type,
                'Fills': f"{avg_cost:.2f}/{size}/{avg_benchmark if avg_benchmark != '' else ''}"
            })
        print("[DEBUG] init_bdata_from_ibkr sonu, BDATA:", self.bdata)
        self.save_bdata()

    def get_tpref_benchmark(self, ticker, pff_last, tlt_last):
        cgrup = self.tpref_cgrup_map.get(ticker, None)
        if cgrup and cgrup in self.tpref_bench_coeffs:
            pff_coef, tlt_coef = self.tpref_bench_coeffs[cgrup]
            return round(pff_last * pff_coef + tlt_last * tlt_coef, 4)
        return None

    def get_benchmarks(self):
        # Returns a dict of benchmarks for all tickers
        etf_data = self.market_data.get_etf_data()
        pff_last = etf_data.get('PFF', {}).get('last', None)
        tlt_last = etf_data.get('TLT', {}).get('last', None)
        benchmarks = {}
        # T-pref: per ticker
        for ticker in self.historical_tickers:
            bench = self.get_tpref_benchmark(ticker, pff_last, tlt_last)
            if bench is not None:
                benchmarks[f'T-{ticker}'] = bench
        # C-pref: eski sistem (örnek, C-Benchmark)
        c_bench = self.market_data.get_benchmarks().get('C-Benchmark', None)
        for ticker in self.extended_tickers:
            if c_bench is not None:
                benchmarks[f'C-{ticker}'] = c_bench
        return benchmarks

    def export_bdata_to_csv(self):
        import csv
        with open('bdata.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Ticker", "Poly", "Total Size", "Avg Cost", "Bench Type", "Avg Benchmark",
                "Current Price", "Current Benchmark", "Avg Outperf", "Fills (Fiyat/Size/Bench)"
            ])
            for row in self.bdata:
                writer.writerow([
                    row.get('Ticker', ''),
                    row.get('Poly', ''),
                    row.get('Total Size', ''),
                    row.get('Avg Cost', ''),
                    row.get('Bench Type', ''),
                    row.get('Avg Benchmark', ''),
                    row.get('Current Price', ''),
                    row.get('Current Benchmark', ''),
                    row.get('Avg Outperf', ''),
                    row.get('Fills', '')
                ])

    def load_psfalgo_exclude(self):
        path = "excpsfalgo.csv"
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                return set(df['Symbol'].astype(str).str.strip().str.upper())
            except Exception:
                return set()
        return set()

    def save_psfalgo_exclude(self):
        path = "excpsfalgo.csv"
        df = pd.DataFrame({'Symbol': list(self.psfalgo_exclude)})
        df.to_csv(path, index=False)

    def open_psfalgo_exclude_window(self):
        win = tk.Toplevel(self)
        win.title("Exclude fr Psfalgo")
        win.geometry("400x400")
        table = ttk.Treeview(win, columns=("Symbol",), show='headings')
        table.heading("Symbol", text="Symbol")
        table.pack(fill='both', expand=True)
        def refresh_table():
            for i in table.get_children():
                table.delete(i)
            for sym in sorted(self.psfalgo_exclude):
                table.insert('', 'end', values=(sym,))
        refresh_table()
        entry = ttk.Entry(win)
        entry.pack(pady=5)
        def add_symbol():
            sym = entry.get().strip().upper()
            if sym and sym not in self.psfalgo_exclude:
                self.psfalgo_exclude.add(sym)
                refresh_table()
        ttk.Button(win, text="Ekle", command=add_symbol).pack()
        def remove_selected():
            for item in table.selection():
                sym = table.item(item, 'values')[0]
                self.psfalgo_exclude.discard(sym)
            refresh_table()
        ttk.Button(win, text="Seçiliyi Sil", command=remove_selected).pack(pady=5)
        def save_and_close():
            self.save_psfalgo_exclude()
            win.destroy()
        ttk.Button(win, text="Kaydet ve Kapat", command=save_and_close).pack(pady=10)

    def open_psf_reasoning_window(self):
        win = tk.Toplevel(self)
        win.title("PSF Reasoning Log")
        win.geometry("800x600")

        # Log dosyası yolu
        log_file = os.path.join('logs', 'psf_reasoning.log')

        # Text widget ve scrollbar
        text_frame = ttk.Frame(win)
        text_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        text_widget = tk.Text(text_frame, wrap='word')
        scrollbar = ttk.Scrollbar(text_frame, orient='vertical', command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side='right', fill='y')
        text_widget.pack(side='left', fill='both', expand=True)

        def load_log():
            try:
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        text_widget.delete('1.0', tk.END)
                        text_widget.insert('1.0', content)
                        text_widget.see('end')  # En son satıra scroll
                else:
                    text_widget.delete('1.0', tk.END)
                    text_widget.insert('1.0', "Log dosyası henüz oluşturulmamış.")
            except Exception as e:
                text_widget.delete('1.0', tk.END)
                text_widget.insert('1.0', f"Log dosyası okunamadı: {str(e)}")

        def auto_refresh():
            load_log()
            win.after(5000, auto_refresh)  # 5 saniyede bir güncelle

        # İlk yükleme
        load_log()
        
        # Otomatik yenileme başlat
        auto_refresh()

        # Pencere kapatıldığında otomatik yenilemeyi durdur
        def on_close():
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)
        win.after(5000, auto_refresh)

    def run_long_front_run(self):
        """Long pozisyonlar için front run işlemleri"""
        try:
            # Mevcut long pozisyonları al
            positions = [pos for pos in self.market_data.get_positions() if pos['quantity'] > 0]
            if not positions:
                return
                
            # Her pozisyon için front sell pahalilik skorunu al
            position_scores = []
            for pos in positions:
                ticker = pos['symbol']
                quantity = pos['quantity']
                
                try:
                    # Skorları oku
                    final_df = pd.read_csv('mastermind_histport.csv')
                    score = final_df[final_df['PREF IBKR'] == ticker]['Front sell pahalilik skoru'].iloc[0]
                    
                    # Front sell pahalilik skoru > 0.10 kontrolü
                    if score > 0.10:
                        position_scores.append((ticker, quantity, score))
                except Exception as e:
                    print(f"Error getting score for {ticker}: {e}")
                    continue
            
            # Skorlara göre sırala (en yüksekten en düşüğe)
            position_scores.sort(key=lambda x: x[2], reverse=True)
            
            # En yüksek skorlu 3 hisse için işlem yap
            for ticker, quantity, score in position_scores[:3]:
                try:
                    # Market data'dan last price'ı al
                    market_data = self.market_data.get_market_data([ticker])
                    if ticker in market_data:
                        data = market_data[ticker]
                        last_price = float(data.get('last', 0))
                        
                        # %20'lik kısmı hesapla
                        target_size = int(quantity * 0.2)
                        
                        # Lot sınırlamalarını uygula
                        if target_size < 200:
                            target_size = min(200, quantity)  # En az 200 veya mevcut miktar
                        elif target_size > 800:
                            target_size = 800  # En fazla 800
                        
                        # Hidden sell emri gönder (last - 0.01)
                        hidden_price = last_price - 0.01
                        if hasattr(self.market_data, 'place_order'):
                            success = self.market_data.place_order(
                                ticker, 'SELL', target_size, 
                                price=hidden_price, 
                                order_type='LIMIT'
                            )
                            if success:
                                print(f"Long front run emri gönderildi: {ticker} {target_size} lot @ {hidden_price}")
                                print(f"Front sell skoru: {score}")
                except Exception as e:
                    print(f"Error sending order for {ticker}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error in run_long_front_run: {e}")

    def run_short_front_run(self):
        """Short pozisyonlar için front run işlemleri"""
        try:
            # Mevcut short pozisyonları al
            positions = [pos for pos in self.market_data.get_positions() if pos['quantity'] < 0]
            if not positions:
                return
                
            # Her pozisyon için front buy ucuzluk skorunu al
            position_scores = []
            for pos in positions:
                ticker = pos['symbol']
                quantity = abs(pos['quantity'])  # Mutlak değer
                
                try:
                    # Skorları oku
                    final_df = pd.read_csv('mastermind_histport.csv')
                    score = final_df[final_df['PREF IBKR'] == ticker]['Front buy ucuzluk skoru'].iloc[0]
                    
                    # Front buy ucuzluk skoru < -0.10 kontrolü
                    if score < -0.10:
                        position_scores.append((ticker, quantity, score))
                except Exception as e:
                    print(f"Error getting score for {ticker}: {e}")
                    continue
            
            # Skorlara göre sırala (en düşükten en yükseğe)
            position_scores.sort(key=lambda x: x[2])
            
            # En düşük skorlu 3 hisse için işlem yap
            for ticker, quantity, score in position_scores[:3]:
                try:
                    # Market data'dan last price'ı al
                    market_data = self.market_data.get_market_data([ticker])
                    if ticker in market_data:
                        data = market_data[ticker]
                        last_price = float(data.get('last', 0))
                        
                        # %20'lik kısmı hesapla
                        target_size = int(quantity * 0.2)
                        
                        # Lot sınırlamalarını uygula
                        if target_size < 200:
                            target_size = min(200, quantity)  # En az 200 veya mevcut miktar
                        elif target_size > 800:
                            target_size = 800  # En fazla 800
                        
                        # Hidden buy emri gönder (last + 0.01)
                        hidden_price = last_price + 0.01
                        if hasattr(self.market_data, 'place_order'):
                            success = self.market_data.place_order(
                                ticker, 'BUY', target_size, 
                                price=hidden_price, 
                                order_type='LIMIT'
                            )
                            if success:
                                print(f"Short front run emri gönderildi: {ticker} {target_size} lot @ {hidden_price}")
                                print(f"Front buy skoru: {score}")
                except Exception as e:
                    print(f"Error sending order for {ticker}: {e}")
                    continue
                    
        except Exception as e:
            print(f"Error in run_short_front_run: {e}")

    def befday_snapshot(self):
        """Piyasa açılışı öncesi pozisyonların snapshot'ını CSV'ye kaydet"""
        try:
            # IBKR bağlantısı kontrolü
            if not self.market_data.ib_connected:
                messagebox.showerror("Hata", "IBKR bağlantısı gerekli! Önce IBKR'ye bağlanın.")
                return
            
            # Mevcut pozisyonları IBKR'den çek
            positions = self.market_data.get_positions()
            
            if not positions:
                messagebox.showinfo("Bilgi", "Herhangi bir pozisyon bulunamadı.")
                return
            
            # CSV başlıkları - pozisyonlarım penceresindeki gibi
            headers = ['Symbol', 'Quantity', 'AvgCost', 'Market Price', 'Market Value', 'Unrealized PnL', 'Account']
            
            # CSV verileri
            csv_data = []
            
            # Market data'yı çek
            symbols = [pos['symbol'] for pos in positions]
            market_data = self.market_data.get_market_data(symbols)
            
            for pos in positions:
                symbol = pos['symbol']
                quantity = pos['quantity']
                avg_cost = pos['avgCost']
                account = pos['account']
                
                # Market price'ı al
                data = market_data.get(symbol, {})
                market_price = data.get('last', 'N/A')
                
                # Market value hesapla
                if market_price != 'N/A' and isinstance(market_price, (int, float)):
                    market_value = quantity * float(market_price)
                    unrealized_pnl = (float(market_price) - avg_cost) * quantity
                else:
                    market_value = 'N/A'
                    unrealized_pnl = 'N/A'
                
                csv_data.append([
                    symbol,
                    quantity,
                    avg_cost,
                    market_price,
                    market_value,
                    unrealized_pnl,
                    account
                ])
            
            # CSV dosyasına kaydet
            csv_filename = 'befday.csv'
            with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                writer.writerows(csv_data)
            
            # Bilgilendirme mesajı
            total_positions = len(positions)
            long_positions = len([p for p in positions if p['quantity'] > 0])
            short_positions = len([p for p in positions if p['quantity'] < 0])
            
            message = f"""BEFDAY Snapshot Kaydedildi!

Dosya: {csv_filename}
Toplam Pozisyon: {total_positions}
Long Pozisyon: {long_positions}
Short Pozisyon: {short_positions}

Tarih/Saat: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
            
            messagebox.showinfo("BEFDAY Snapshot", message)
            print(f"[BEFDAY] Snapshot kaydedildi: {csv_filename}")
            print(f"[BEFDAY] {total_positions} pozisyon kaydedildi")
            
        except Exception as e:
            error_msg = f"BEFDAY snapshot kaydetme hatası: {str(e)}"
            messagebox.showerror("Hata", error_msg)
            print(f"[BEFDAY ERROR] {error_msg}")

    def test_psf_reverse(self):
        """PSFAlgo reverse order sistemini test et"""
        if not hasattr(self, 'psf_algo') or self.psf_algo is None:
            messagebox.showwarning("Uyarı", "PSFAlgo henüz başlatılmamış. Önce 'PsfAlgo OFF' butonuna tıklayın.")
            return
        
        # Test parametreleri
        ticker = "JAGX"
        side = "long"
        fill_price = 2.89 
        fill_size = 200
        
        print(f"[GUI TEST] 🧪 PSFAlgo reverse order test başlatılıyor...")
        print(f"[GUI TEST] Test parametreleri: {ticker} {side} {fill_size} lot @ {fill_price}")
        
        # Test'i çalıştır
        success = self.psf_algo.test_reverse_order_system(ticker, side, fill_price, fill_size)
        
        if success:
            messagebox.showinfo("Test Sonucu", f"✅ PSFAlgo reverse order test başarılı!\n\nTest parametreleri:\n{ticker} {side} {fill_size} lot @ {fill_price}\n\nKonsolu kontrol edin.")
        else:
            messagebox.showwarning("Test Sonucu", f"❌ PSFAlgo reverse order test başarısız.\n\nPSFAlgo aktif değil. Önce 'PsfAlgo OFF' butonuna tıklayarak aktifleştirin.")

    def debug_psf_fills(self):
        """PSFAlgo günlük fill durumunu debug et"""
        if not hasattr(self, 'psf_algo') or self.psf_algo is None:
            messagebox.showwarning("Uyarı", "PSFAlgo henüz başlatılmamış. Önce 'PsfAlgo OFF' butonuna tıklayın.")
            return
        
        print(f"[GUI DEBUG] 🔍 PSFAlgo günlük fill debug başlatılıyor...")
        
        # Debug'i çalıştır
        self.psf_algo.debug_daily_fills()
        
        # Konsol mesajı
        messagebox.showinfo("Debug Sonucu", "🔍 PSFAlgo günlük fill durumu konsola yazdırıldı.\n\nDetaylar için konsolu kontrol edin.")

    def open_long_take_profit_window(self, on_close_callback=None):
        """Long take profit penceresi aç"""
        from Htahaf.gui.maltopla_window import MaltoplaWindow
        import pandas as pd
        
        def polygonize_ticker(symbol):
            symbol = str(symbol).strip()
            if ' PR' in symbol:
                base, pr = symbol.split(' PR', 1)
                return f"{base}p{pr.strip().upper()}"
            return symbol
        
        # Long pozisyonları al
        positions = [pos for pos in self.market_data.get_positions() if pos['quantity'] > 0]
        tickers = [pos['symbol'] for pos in positions]
        
        # Güncel skorları oku
        try:
            final_df = pd.read_csv('mastermind_histport.csv')
        except Exception:
            final_df = pd.DataFrame()
            
        final_thg_map = dict(zip(final_df['PREF IBKR'], final_df['FINAL_THG'])) if not final_df.empty else {}
        avg_adv_map = dict(zip(final_df['PREF IBKR'], final_df['AVG_ADV'])) if not final_df.empty else {}
        
        df = pd.DataFrame({
            'PREF IBKR': tickers,
            'Quantity': [pos['quantity'] for pos in positions],
            'FINAL_THG': [final_thg_map.get(t, '') for t in tickers],
            'AVG_ADV': [avg_adv_map.get(t, '') for t in tickers],
        })
        
        # Convert tickers to Polygon format
        poly_tickers = [polygonize_ticker(t) for t in tickers]
        market_data_dict = self.market_data.get_market_data(poly_tickers)
        etf_data = self.market_data.get_etf_data()
        
        win = MaltoplaWindow(self, "Long take profit", df, market_data_dict, etf_data, 
                           benchmark_type='T', ibkr_client=self.market_data.ib, 
                           exdiv_data=self.exdiv_data, c_ticker_to_csv=self.c_ticker_to_csv, 
                           c_csv_data=self.c_csv_data)
        
        if on_close_callback:
            win.protocol("WM_DELETE_WINDOW", lambda: (self.close_maltopla_window(win), on_close_callback()))
        else:
            win.protocol("WM_DELETE_WINDOW", lambda: self.close_maltopla_window(win))
