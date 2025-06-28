import tkinter as tk
from tkinter import ttk
import threading
import pandas as pd
from hammerib.ib_api.manager import IBKRManager, ETF_SYMBOLS
import time
from hammerib.gui.etf_panel import ETFPanel
from hammerib.gui.opt_buttons import create_opt_buttons
from hammerib.gui.benchmark_panel import BenchmarkPanel
from hammerib.gui.maltopla_window import MaltoplaWindow
from hammerib.gui.pos_orders_buttons import create_pos_orders_buttons
from hammerib.gui.top_movers_buttons import create_top_movers_buttons

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stock Tracker Modular")
        self.ibkr = IBKRManager()
        self.historical_tickers = pd.read_csv('historical_data.csv')['PREF IBKR'].dropna().tolist()
        self.extended_tickers = pd.read_csv('extlthistorical.csv')['PREF IBKR'].dropna().tolist()
        self.items_per_page = 20
        self.historical_page = 0
        self.extended_page = 0
        self.active_tab = 0  # 0: historical, 1: extended
        self.etf_panel = ETFPanel(self, ETF_SYMBOLS, compact=True)
        self.etf_panel.pack(fill='x', padx=5, pady=2)
        self.loop_running = False
        self.loop_job = None
        self.setup_ui()
        # Create BenchmarkPanel instances after setup_ui() so that historical_frame and extended_frame exist
        self.historical_benchmark = BenchmarkPanel(self.historical_frame)
        self.historical_benchmark.pack(fill='x', padx=5, pady=5)
        self.extended_benchmark = BenchmarkPanel(self.extended_frame)
        self.extended_benchmark.pack(fill='x', padx=5, pady=5)
        self.data_thread = None
        self.after(1000, self.update_etf_panel)

    def setup_ui(self):
        top = ttk.Frame(self)
        top.pack(fill='x')
        self.btn_connect = ttk.Button(top, text="IBKR'ye Bağlan", command=self.connect_ibkr)
        self.btn_connect.pack(side='left', padx=5)
        self.btn_loop = ttk.Button(top, text='Döngü Başlat', command=self.toggle_loop)
        self.btn_loop.pack(side='left', padx=5)
        create_opt_buttons(top, self)
        create_pos_orders_buttons(top, self)
        create_top_movers_buttons(top, self)
        self.status_label = ttk.Label(top, text="Durum: Bekleniyor")
        self.status_label.pack(side='left', padx=10)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True)
        # Historical tab
        self.historical_frame = ttk.Frame(self.notebook)
        self.historical_table = self.create_table(self.historical_frame)
        self.historical_nav = self.create_nav(self.historical_frame, self.prev_historical, self.next_historical)
        self.notebook.add(self.historical_frame, text="T-prefs")
        # Extended tab
        self.extended_frame = ttk.Frame(self.notebook)
        self.extended_table = self.create_table(self.extended_frame)
        self.extended_nav = self.create_nav(self.extended_frame, self.prev_extended, self.next_extended)
        self.notebook.add(self.extended_frame, text="C-prefs")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        self.update_tables()

    def create_table(self, parent):
        columns = ('Ticker', 'Bid', 'Ask', 'Last', 'Volume')
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
        self.ibkr.connect()
        self.status_label.config(text="Durum: IBKR'ye bağlı")
        self.subscribe_visible()
        if not self.data_thread:
            self.data_thread = threading.Thread(target=self.update_data_loop, daemon=True)
            self.data_thread.start()

    def subscribe_visible(self):
        if not self.ibkr.connected:
            return
        if self.active_tab == 0:
            tickers = self.get_visible_tickers(self.historical_tickers, self.historical_page)
        else:
            tickers = self.get_visible_tickers(self.extended_tickers, self.extended_page)
        self.ibkr.clear_subscriptions()
        self.ibkr.subscribe_tickers(tickers)

    def get_visible_tickers(self, ticker_list, page):
        start = page * self.items_per_page
        end = min(start + self.items_per_page, len(ticker_list))
        return ticker_list[start:end]

    def update_tables(self):
        # Historical
        self.update_table(self.historical_table, self.historical_tickers, self.historical_page)
        self.historical_nav['lbl'].config(text=f"Page {self.historical_page + 1}")
        # Extended
        self.update_table(self.extended_table, self.extended_tickers, self.extended_page)
        self.extended_nav['lbl'].config(text=f"Page {self.extended_page + 1}")

    def update_table(self, table, ticker_list, page):
        for item in table.get_children():
            table.delete(item)
        for ticker in self.get_visible_tickers(ticker_list, page):
            table.insert('', 'end', values=(ticker, 'N/A', 'N/A', 'N/A', 'N/A'))

    def update_data_loop(self):
        while True:
            if self.active_tab == 0:
                tickers = self.get_visible_tickers(self.historical_tickers, self.historical_page)
                table = self.historical_table
                benchmark_panel = self.historical_benchmark
            else:
                tickers = self.get_visible_tickers(self.extended_tickers, self.extended_page)
                table = self.extended_table
                benchmark_panel = self.extended_benchmark
            data = self.ibkr.get_market_data(tickers)
            for item in table.get_children():
                try:
                    ticker = table.item(item)['values'][0]
                    d = data.get(ticker)
                    if d:
                        table.item(item, values=(ticker, d['bid'], d['ask'], d['last'], d['volume']))
                except tk.TclError:
                    # Item not found, skip
                    pass
            benchmark_data = self.ibkr.calculate_benchmarks()
            benchmark_panel.update(benchmark_data)
            time.sleep(1)

    def prev_historical(self):
        if self.historical_page > 0:
            self.historical_page -= 1
            self.update_tables()
            if self.active_tab == 0:
                self.subscribe_visible()

    def next_historical(self):
        max_page = (len(self.historical_tickers) - 1) // self.items_per_page
        if self.historical_page < max_page:
            self.historical_page += 1
            self.update_tables()
            if self.active_tab == 0:
                self.subscribe_visible()

    def prev_extended(self):
        if self.extended_page > 0:
            self.extended_page -= 1
            self.update_tables()
            if self.active_tab == 1:
                self.subscribe_visible()

    def next_extended(self):
        max_page = (len(self.extended_tickers) - 1) // self.items_per_page
        if self.extended_page < max_page:
            self.extended_page += 1
            self.update_tables()
            if self.active_tab == 1:
                self.subscribe_visible()

    def on_tab_changed(self, event):
        self.active_tab = self.notebook.index(self.notebook.select())
        self.subscribe_visible()

    def update_etf_panel(self):
        etf_data = self.ibkr.get_etf_data()
        self.etf_panel.update(etf_data)
        self.after(1000, self.update_etf_panel)

    def run(self):
        self.mainloop()

    def close(self):
        if self.ibkr:
            self.ibkr.disconnect()
        self.destroy()

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
        MaltoplaWindow(self, self.ibkr, 'optimized_50_stocks_portfolio.csv', 'T')

    def open_extlt35_maltopla_window(self):
        MaltoplaWindow(self, self.ibkr, 'optimized_35_extlt.csv', 'C')

    def open_positions_window(self):
        win = tk.Toplevel(self)
        win.title('Pozisyonlarım')
        ttk.Label(win, text='Pozisyonlarım (WebSocket API ile entegre edilecek)').pack(padx=20, pady=20)

    def open_orders_window(self):
        win = tk.Toplevel(self)
        win.title('Emirlerim')
        ttk.Label(win, text='Emirlerim (WebSocket API ile entegre edilecek)').pack(padx=20, pady=20)

    def open_t_top_losers_window(self):
        self.open_top_movers_window('T', 'losers')

    def open_t_top_gainers_window(self):
        self.open_top_movers_window('T', 'gainers')

    def open_c_top_losers_window(self):
        self.open_top_movers_window('C', 'losers')

    def open_c_top_gainers_window(self):
        self.open_top_movers_window('C', 'gainers')

    def open_top_movers_window(self, pref_type, direction):
        win = tk.Toplevel(self)
        win.title(f"{pref_type}-{'çok düşenler' if direction=='losers' else 'çok yükselenler'}")
        ttk.Label(win, text=f"{pref_type}-{'çok düşenler' if direction=='losers' else 'çok yükselenler'} (İçerik eklenecek)").pack(padx=20, pady=20)

    def toggle_loop(self):
        if self.loop_running:
            self.loop_running = False
            self.btn_loop.config(text='Döngü Başlat')
            if self.loop_job:
                self.after_cancel(self.loop_job)
                self.loop_job = None
        else:
            self.loop_running = True
            self.btn_loop.config(text='Döngüyü Durdur')
            self.loop_state = {'tab': 0, 'page': 0, 'phase': 'T'}
            self.notebook.select(0)
            self.historical_page = 0
            self.extended_page = 0
            self.update_tables()
            self.subscribe_visible()
            self.loop_job = self.after(100, self.loop_step)

    def loop_step(self):
        if not self.loop_running:
            return
        # Determine current phase and page
        if self.loop_state['phase'] == 'T':
            max_page = (len(self.historical_tickers) - 1) // self.items_per_page
            if self.historical_page < max_page:
                self.historical_page += 1
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(5000, self.loop_step)
            else:
                self.loop_state['phase'] = 'C'
                self.notebook.select(1)
                self.extended_page = 0
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(5000, self.loop_step)
        elif self.loop_state['phase'] == 'C':
            max_page = (len(self.extended_tickers) - 1) // self.items_per_page
            if self.extended_page < max_page:
                self.extended_page += 1
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(5000, self.loop_step)
            else:
                self.loop_state['phase'] = 'T'
                self.notebook.select(0)
                self.historical_page = 0
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(5000, self.loop_step) 