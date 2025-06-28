import tkinter as tk
from tkinter import ttk
import pandas as pd
import threading
import time
from hammerib.gui.etf_panel import ETFPanel
from hammerib.ib_api.manager import ETF_SYMBOLS

CHECKED = '\u2611'  # ☑
UNCHECKED = '\u2610'  # ☐

class MaltoplaWindow(tk.Toplevel):
    def __init__(self, parent, ibkr_manager, csv_path, benchmark_type):
        super().__init__(parent)
        self.title(f"{csv_path} Maltopla Analiz")
        self.ibkr = ibkr_manager
        self.csv_path = csv_path
        self.benchmark_type = benchmark_type  # 'T' or 'C'
        self.tickers = self.load_tickers()
        self.items_per_page = 20
        self.page = 0
        self.max_page = max(0, (len(self.tickers) - 1) // self.items_per_page)
        self.ticker_cache = {}  # symbol -> data dict
        self.ticker_handlers = {}  # symbol -> handler ref
        self.checked_tickers = set()
        self.etf_panel = ETFPanel(self, ETF_SYMBOLS, compact=True)
        self.etf_panel.pack(fill='x', padx=2, pady=2)
        self.after(1000, self.update_etf_panel)
        self.table = ttk.Treeview(self, columns=(
            'Seç', 'Ticker', 'Bid', 'Ask', 'Prev Close', 'Bid+spr*0.15', 'Benchmark', 'Avantaj'), show='headings', height=20)
        for col in ('Seç', 'Ticker', 'Bid', 'Ask', 'Prev Close', 'Bid+spr*0.15', 'Benchmark', 'Avantaj'):
            self.table.heading(col, text=col)
            self.table.column(col, width=90 if col=='Seç' else 110, anchor='center')
        self.table.pack(fill='both', expand=True)
        self.table.bind('<Button-1>', self.on_table_click)
        # Selection buttons
        sel_frame = ttk.Frame(self)
        sel_frame.pack(fill='x', pady=2)
        btn_select_all = ttk.Button(sel_frame, text='Tümünü Seç', command=self.select_all)
        btn_select_all.pack(side='left', padx=2)
        btn_deselect_all = ttk.Button(sel_frame, text='Tümünü Kaldır', command=self.deselect_all)
        btn_deselect_all.pack(side='left', padx=2)
        # Navigation
        nav = ttk.Frame(self)
        nav.pack(fill='x')
        self.btn_prev = ttk.Button(nav, text='<', command=self.prev_page)
        self.btn_prev.pack(side='left', padx=5)
        self.lbl_page = ttk.Label(nav, text=f'Page {self.page+1}')
        self.lbl_page.pack(side='left', padx=5)
        self.btn_next = ttk.Button(nav, text='>', command=self.next_page)
        self.btn_next.pack(side='left', padx=5)
        # Action buttons
        action_frame = ttk.Frame(self)
        action_frame.pack(fill='x', pady=4)
        btn_spr_hidden_bid = ttk.Button(action_frame, text='spr hidden bid', command=self.on_spr_hidden_bid)
        btn_spr_hidden_bid.pack(side='left', padx=2)
        btn_spr_hidden_ask = ttk.Button(action_frame, text='spr hidden ask', command=self.on_spr_hidden_ask)
        btn_spr_hidden_ask.pack(side='left', padx=2)
        btn_adj_hidden_bid = ttk.Button(action_frame, text='adj hidden bid', command=self.on_adj_hidden_bid)
        btn_adj_hidden_bid.pack(side='left', padx=2)
        btn_adj_hidden_ask = ttk.Button(action_frame, text='adj hidden ask', command=self.on_adj_hidden_ask)
        btn_adj_hidden_ask.pack(side='left', padx=2)
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self._running = True
        self.subscribe_visible()
        self.populate_table_from_cache()

    def load_tickers(self):
        try:
            df = pd.read_csv(self.csv_path)
            if 'PREF IBKR' in df.columns:
                return df['PREF IBKR'].dropna().tolist()
            else:
                return df.iloc[:,0].dropna().tolist()
        except Exception:
            return []

    def get_visible_tickers(self):
        start = self.page * self.items_per_page
        end = min(start + self.items_per_page, len(self.tickers))
        return self.tickers[start:end]

    def subscribe_visible(self):
        # Unsubscribe old
        for symbol in list(self.ticker_handlers.keys()):
            if symbol not in self.get_visible_tickers():
                handler = self.ticker_handlers.pop(symbol, None)
                ticker_obj = self.ibkr.tickers.get(symbol, {}).get('ticker')
                if ticker_obj and handler:
                    try:
                        ticker_obj.updateEvent -= handler
                    except Exception:
                        pass
        # Subscribe new
        self.ibkr.subscribe_tickers(self.get_visible_tickers())
        for symbol in self.get_visible_tickers():
            ticker_obj = self.ibkr.tickers.get(symbol, {}).get('ticker')
            if ticker_obj and symbol not in self.ticker_handlers:
                def make_handler(sym):
                    def handler(ticker):
                        self.on_ticker_update(sym, ticker)
                    return handler
                handler = make_handler(symbol)
                ticker_obj.updateEvent += handler
                self.ticker_handlers[symbol] = handler
        self.populate_table_from_cache()

    def on_ticker_update(self, symbol, ticker):
        # Update cache
        prev_close = self.ibkr.prev_closes.get(symbol)
        self.ticker_cache[symbol] = {
            'bid': ticker.bid,
            'ask': ticker.ask,
            'last': ticker.last,
            'prev_close': prev_close,
            'timestamp': time.time()
        }
        self.update_row(symbol)

    def populate_table_from_cache(self):
        self.table.delete(*self.table.get_children())
        for symbol in self.get_visible_tickers():
            self.insert_or_update_row(symbol)

    def insert_or_update_row(self, symbol):
        d = self.ticker_cache.get(symbol, {})
        bid = d.get('bid', 'N/A')
        ask = d.get('ask', 'N/A')
        prev_close = d.get('prev_close', 'N/A')
        checked = CHECKED if symbol in self.checked_tickers else UNCHECKED
        if bid is not None and ask is not None and prev_close is not None and bid != 'N/A' and ask != 'N/A' and prev_close != 'N/A':
            try:
                bid = float(bid)
                ask = float(ask)
                prev_close = float(prev_close)
                bid_spr = round(bid + (ask - bid) * 0.15, 3)
                if self.benchmark_type == 'T':
                    benchmark = self.ibkr.calculate_benchmarks().get('T-Benchmark', 0)
                else:
                    benchmark = self.ibkr.calculate_benchmarks().get('C-Benchmark', 0)
                avantaj = round(bid_spr - prev_close - (benchmark if benchmark != 'N/A' else 0), 3)
            except Exception:
                bid_spr = 'N/A'
                avantaj = 'N/A'
        else:
            bid_spr = 'N/A'
            avantaj = 'N/A'
            benchmark = self.ibkr.calculate_benchmarks().get('T-Benchmark' if self.benchmark_type == 'T' else 'C-Benchmark', 'N/A')
        values = (checked, symbol, bid, ask, prev_close, bid_spr, benchmark, avantaj)
        if self.table.exists(symbol):
            self.table.item(symbol, values=values)
        else:
            self.table.insert('', 'end', iid=symbol, values=values)

    def update_row(self, symbol):
        self.insert_or_update_row(symbol)

    def on_table_click(self, event):
        region = self.table.identify('region', event.x, event.y)
        if region != 'cell':
            return
        col = self.table.identify_column(event.x)
        if col != '#1':  # Only first column (checkbox)
            return
        row = self.table.identify_row(event.y)
        if not row:
            return
        symbol = self.table.item(row, 'values')[1]
        if symbol in self.checked_tickers:
            self.checked_tickers.remove(symbol)
        else:
            self.checked_tickers.add(symbol)
        self.update_row(symbol)

    def prev_page(self):
        if self.page > 0:
            self.page -= 1
            self.lbl_page.config(text=f'Page {self.page+1}')
            self.subscribe_visible()

    def next_page(self):
        if self.page < self.max_page:
            self.page += 1
            self.lbl_page.config(text=f'Page {self.page+1}')
            self.subscribe_visible()

    def select_all(self):
        for symbol in self.get_visible_tickers():
            self.checked_tickers.add(symbol)
            self.update_row(symbol)

    def deselect_all(self):
        for symbol in self.get_visible_tickers():
            if symbol in self.checked_tickers:
                self.checked_tickers.remove(symbol)
            self.update_row(symbol)

    def get_selected_tickers(self):
        return list(self.checked_tickers)

    def on_spr_hidden_bid(self):
        print('spr hidden bid:', self.get_selected_tickers())
    def on_spr_hidden_ask(self):
        print('spr hidden ask:', self.get_selected_tickers())
    def on_adj_hidden_bid(self):
        print('adj hidden bid:', self.get_selected_tickers())
    def on_adj_hidden_ask(self):
        print('adj hidden ask:', self.get_selected_tickers())

    def on_close(self):
        self._running = False
        # Unsubscribe all event handlers
        for symbol, handler in self.ticker_handlers.items():
            ticker_obj = self.ibkr.tickers.get(symbol, {}).get('ticker')
            if ticker_obj and handler:
                try:
                    ticker_obj.updateEvent -= handler
                except Exception:
                    pass
        self.ticker_handlers.clear()
        if self.ibkr and hasattr(self.ibkr, 'clear_subscriptions'):
            self.ibkr.clear_subscriptions()
        self.destroy()

    def update_etf_panel(self):
        etf_data = self.ibkr.get_etf_data()
        self.etf_panel.update(etf_data)
        self.after(1000, self.update_etf_panel) 