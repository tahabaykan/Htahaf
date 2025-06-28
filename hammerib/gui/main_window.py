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
from hammerib.gui.orderable_table import OrderableTableFrame
from tb_modules.tb_data_management import sort_and_paginate_rows

class LongShortPanel(ttk.Frame):
    def __init__(self, parent, ibkr_manager):
        super().__init__(parent)
        self.ibkr = ibkr_manager
        self.lbl_long = tk.Label(self, text="", fg="green", font=("Arial", 12, "bold"))
        self.lbl_short = tk.Label(self, text="", fg="red", font=("Arial", 12, "bold"))
        self.lbl_long.pack(side="left", padx=10)
        self.lbl_short.pack(side="left", padx=10)
        self.update_panel()

    def update_panel(self):
        positions = self.ibkr.get_positions()
        long_qty = sum(pos['quantity'] for pos in positions if pos['quantity'] > 0)
        short_qty = sum(-pos['quantity'] for pos in positions if pos['quantity'] < 0)
        long_exp = sum(pos['quantity'] * pos['avgCost'] for pos in positions if pos['quantity'] > 0)
        short_exp = sum(-pos['quantity'] * pos['avgCost'] for pos in positions if pos['quantity'] < 0)
        self.lbl_long.config(text=f"Long: {long_qty:,} ({long_exp/1000:.1f}K USD)")
        self.lbl_short.config(text=f"Short: {short_qty:,} ({short_exp/1000:.1f}K USD)")
        self.after(2000, self.update_panel)

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stock Tracker Modular")
        self.ibkr = IBKRManager()
        # Hisse listelerini yeni CSV dosyalarından oku ve ek alanları al
        self.historical_df = pd.read_csv('mastermind_histport.csv')
        self.extended_df = pd.read_csv('mastermind_extltport.csv')
        self.historical_tickers = self.historical_df['PREF IBKR'].dropna().drop_duplicates().tolist()
        self.extended_tickers = self.extended_df['PREF IBKR'].dropna().drop_duplicates().tolist()
        self.items_per_page = 17
        self.historical_page = 0
        self.extended_page = 0
        self.active_tab = 0  # 0: historical, 1: extended
        self.etf_panel = ETFPanel(self, ETF_SYMBOLS, compact=True)
        self.etf_panel.pack(fill='x', padx=5, pady=2)
        self.long_short_panel = LongShortPanel(self, self.ibkr)
        self.long_short_panel.pack(fill='x', padx=5, pady=5)
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
        self.btn_take_profit_longs = ttk.Button(top, text='Take Profit Longs', command=self.open_take_profit_longs_window)
        self.btn_take_profit_longs.pack(side='left', padx=2)
        self.btn_take_profit_shorts = ttk.Button(top, text='Take Profit Shorts', command=self.open_take_profit_shorts_window)
        self.btn_take_profit_shorts.pack(side='left', padx=2)
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
            table.insert('', 'end', values=(ticker, 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A'))

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
                        table.item(item, values=(ticker, d.get('bid','N/A'), d.get('ask','N/A'), d.get('last','N/A'), d.get('prev_close','N/A'), d.get('volume','N/A'), 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A'))
                except tk.TclError:
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
        columns = ('Symbol', 'Quantity', 'Avg Cost', 'Account', 'Benchmark Rel.')
        table = ttk.Treeview(win, columns=columns, show='headings')
        for col in columns:
            table.heading(col, text=col)
            table.column(col, width=100, anchor='center')
        table.pack(fill='both', expand=True)
        def update_table():
            for item in table.get_children():
                table.delete(item)
            positions = self.ibkr.get_positions()
            for pos in positions:
                rel = self.ibkr.get_benchmark_change_since_fill(pos['symbol'])
                rel_str = f"{rel:.3f}" if rel is not None else '-'
                table.insert('', 'end', values=(pos['symbol'], pos['quantity'], pos['avgCost'], pos['account'], rel_str))
            win.after(5000, update_table)
        update_table()

    def open_orders_window(self):
        win = tk.Toplevel(self)
        win.title('Emirlerim')
        notebook = ttk.Notebook(win)
        notebook.pack(fill='both', expand=True)
        # Bekleyen sekmesi
        frame_pending = ttk.Frame(notebook)
        columns_pending = ('Symbol', 'Action', 'Quantity', 'Price', 'Status', 'OrderId')
        table_pending = ttk.Treeview(frame_pending, columns=columns_pending, show='headings')
        for col in columns_pending:
            table_pending.heading(col, text=col)
            table_pending.column(col, width=100, anchor='center')
        table_pending.pack(fill='both', expand=True)
        def update_pending():
            for item in table_pending.get_children():
                table_pending.delete(item)
            orders = self.ibkr.get_open_orders()
            for o in orders:
                table_pending.insert('', 'end', values=(o['symbol'], o['action'], o['quantity'], o['price'], o['status'], o['orderId']))
            frame_pending.after(3000, update_pending)
        update_pending()
        notebook.add(frame_pending, text='Bekleyen')
        # Fillendi sekmesi
        frame_filled = ttk.Frame(notebook)
        columns_filled = (
            'Symbol', 'Fill Price', 'Fill Qty', 'Fill Time', 'Inc/Dec',
            'At Fill Benchmark', 'Cur Benchmark',
            'Best Bid/Ask', 'Last-0.01/+0.01',
            'Quickp Check', 'Frontfill Try'
        )
        table_filled = ttk.Treeview(frame_filled, columns=columns_filled, show='headings')
        for col in columns_filled:
            table_filled.heading(col, text=col)
            table_filled.column(col, width=120 if col.startswith('Cur') or col.startswith('At') else 100, anchor='center')
        table_filled.pack(fill='both', expand=True)
        btn_frame = ttk.Frame(frame_filled)
        btn_frame.pack(fill='x', pady=4)
        btn_quickp = ttk.Button(btn_frame, text='Quickp Check', command=lambda: update_filled(calc_mode='quickp'))
        btn_quickp.pack(side='left', padx=2)
        btn_frontfill = ttk.Button(btn_frame, text='Frontfill Try', command=lambda: update_filled(calc_mode='frontfill'))
        btn_frontfill.pack(side='left', padx=2)
        self._filled_cache = getattr(self, '_filled_cache', {})
        def get_filled_orders():
            fills = self.ibkr.filled_trades
            symbol_qty = {}
            filled_rows = []
            for f in fills:
                symbol = f['symbol']
                qty = f['qty']
                price = f['price']
                time_str = f['time']
                prev_qty = symbol_qty.get(symbol, 0)
                new_qty = prev_qty + qty
                inc_dec = 'Inc' if abs(new_qty) > abs(prev_qty) else 'Dec'
                symbol_qty[symbol] = new_qty
                filled_rows.append({
                    'symbol': symbol,
                    'fill_price': price,
                    'fill_qty': qty,
                    'fill_time': time_str,
                    'inc_dec': inc_dec,
                    'prev_qty': prev_qty,
                    'new_qty': new_qty,
                    'fill_obj': f
                })
            return filled_rows
        def get_benchmark_type(symbol):
            t_set = set(self.historical_tickers)
            c_set = set(self.extended_tickers)
            if symbol in t_set:
                return 'T'
            elif symbol in c_set:
                return 'C'
            else:
                return 'T'  # default fallback
        def calc_benchmark(pff, tlt, btype):
            if btype == 'T':
                return pff * 0.7 + tlt * 0.1
            else:
                return pff * 1.3 - tlt * 0.1
        def calc_outperf(row, mode, bid, ask, last, fill_benchmark, current_benchmark, side):
            fill_price = row['fill_price']
            # Çıkış fiyatı seçimi
            if mode == 'quickp':
                exit_price = bid if side == 'long' else ask
            elif mode == 'frontfill':
                if last is None:
                    return '-'
                exit_price = (last - 0.01) if side == 'long' else (last + 0.01)
            else:
                return '-'
            if exit_price is None:
                return '-'
            # Outperformance hesabı
            if side == 'long':
                outperf = (exit_price - fill_price) - (current_benchmark - fill_benchmark)
            else:
                outperf = (fill_price - exit_price) - (current_benchmark - fill_benchmark)
            return f"{outperf:.3f}"
        def update_filled(calc_mode='quickp'):
            for item in table_filled.get_children():
                table_filled.delete(item)
            filled_rows = get_filled_orders()
            for row in filled_rows:
                f = row['fill_obj']
                symbol = row['symbol']
                fill_benchmark = f['fill_benchmark']
                fill_price = row['fill_price']
                fill_qty = row['fill_qty']
                side = 'long' if fill_qty > 0 else 'short'
                ticker = self.ibkr.tickers.get(symbol, {}).get('ticker')
                bid = ticker.bid if ticker else None
                ask = ticker.ask if ticker else None
                last = ticker.last if ticker else None
                etf_data = self.ibkr.get_etf_data()
                pff = etf_data.get('PFF', {}).get('last', None)
                tlt = etf_data.get('TLT', {}).get('last', None)
                btype = get_benchmark_type(symbol)
                if pff is None or tlt is None or fill_benchmark is None:
                    cur_benchmark = '-'
                    cur_benchmark_val = None
                else:
                    cur_benchmark_val = calc_benchmark(pff, tlt, btype)
                    diff = cur_benchmark_val - fill_benchmark
                    cur_benchmark = f"{cur_benchmark_val:.2f} ({'+' if diff>=0 else ''}{diff:.2f})"
                at_fill_benchmark = f"{fill_benchmark:.2f}" if fill_benchmark is not None else '-'
                # Best Bid/Ask ve Last-0.01/+0.01
                if side == 'long':
                    best = bid if bid is not None else '-'
                    front = f"{last-0.01:.2f}" if last is not None else '-'
                else:
                    best = ask if ask is not None else '-'
                    front = f"{last+0.01:.2f}" if last is not None else '-'
                # Outperformance hesapları
                if row['inc_dec'] == 'Inc' and cur_benchmark_val is not None and fill_benchmark is not None:
                    quickp = calc_outperf(row, 'quickp', bid, ask, last, fill_benchmark, cur_benchmark_val, side)
                    frontfill = calc_outperf(row, 'frontfill', bid, ask, last, fill_benchmark, cur_benchmark_val, side)
                else:
                    quickp = '-'
                    frontfill = '-'
                vals = (
                    symbol, fill_price, fill_qty, row['fill_time'], row['inc_dec'],
                    at_fill_benchmark, cur_benchmark, best, front, quickp, frontfill
                )
                iid = f"{symbol}_{row['fill_time']}"
                table_filled.insert('', 'end', iid=iid, values=vals, tags=(row['inc_dec'],))
            table_filled.tag_configure('Inc', foreground='green')
            table_filled.tag_configure('Dec', foreground='red')
            frame_filled.after(3000, update_filled)
        update_filled()
        notebook.add(frame_filled, text='Fillendi')

    def open_t_top_losers_window(self):
        self.open_top_movers_window('T', 'losers')

    def open_t_top_gainers_window(self):
        self.open_top_movers_window('T', 'gainers')

    def open_c_top_losers_window(self):
        self.open_top_movers_window('C', 'losers')

    def open_c_top_gainers_window(self):
        self.open_top_movers_window('C', 'gainers')

    def open_top_movers_window(self, pref_type, direction):
        import tkinter.font as tkFont
        import pandas as pd
        import time
        win = tk.Toplevel(self)
        win.title(f"{pref_type}-{'çok düşenler' if direction=='losers' else 'çok yükselenler'}")
        etf_panel = ETFPanel(win, ETF_SYMBOLS, compact=True)
        etf_panel.pack(fill='x', padx=2, pady=2)
        # --- Use same columns as maltopla ---
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
        # --- Load CSV ---
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
        for _, row in df.iterrows():
            symbol = row['PREF IBKR'] if 'PREF IBKR' in row and pd.notna(row['PREF IBKR']) else row.iloc[0]
            if pd.isna(symbol):
                continue
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
        # Açıklama satırları (ucuzluk/pahalılık skorları)
        desc_long = (['']*15 + ['Long pozisyon açmak / arttırmak için, veya Short pozisyon kapatmak/azaltmak için'] + ['']*2 + ['🟩'] + ['']*2 + ['🟩'] + ['']*2 + ['🟩'] + ['']*8)
        desc_short = (['']*24 + ['Short pozisyon açmak / arttırmak için, veya Long pozisyon kapatmak/azaltmak için'] + ['']*2 + ['🔺'] + ['']*2 + ['🔺'] + ['']*2 + ['🔺'])
        table.insert('', 'end', iid='desc_long', values=desc_long, tags=('small',))
        table.insert('', 'end', iid='desc_short', values=desc_short, tags=('small',))
        def row_for_symbol(symbol):
            d = self.ibkr.last_data.get(symbol) or {}
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
                    spread = ask - bid
                    etf_data = self.ibkr.get_etf_data()
                    if pref_type == 'T':
                        pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                        tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                        benchmark_chg = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
                    else:
                        pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                        tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                        benchmark_chg = round(pff_chg * 1.3 - tlt_chg * 0.1, 3)
                    # --- Long/cover ---
                    pf_bid_buy = round(bid + spread * 0.15, 3)
                    pf_bid_buy_chg = round(pf_bid_buy - prev_close, 3)
                    bid_buy_ucuzluk = round(pf_bid_buy_chg - benchmark_chg, 3)
                    pf_front_buy = round(last + 0.01, 3)
                    pf_front_buy_chg = round(pf_front_buy - prev_close, 3)
                    front_buy_ucuzluk = round(pf_front_buy_chg - benchmark_chg, 3)
                    pf_ask_buy = round(ask + 0.01, 3)
                    pf_ask_buy_chg = round(pf_ask_buy - prev_close, 3)
                    ask_buy_ucuzluk = round(pf_ask_buy_chg - benchmark_chg, 3)
                    # --- Short/cover ---
                    pf_ask_sell = round(ask - spread * 0.15, 3)
                    pf_ask_sell_chg = round(pf_ask_sell - prev_close, 3)
                    ask_sell_pahali = round(pf_ask_sell_chg - benchmark_chg, 3)
                    pf_front_sell = round(last - 0.01, 3)
                    pf_front_sell_chg = round(pf_front_sell - prev_close, 3)
                    front_sell_pahali = round(pf_front_sell_chg - benchmark_chg, 3)
                    pf_bid_sell = round(bid - 0.01, 3)
                    pf_bid_sell_chg = round(pf_bid_sell - prev_close, 3)
                    bid_sell_pahali = round(pf_bid_sell_chg - benchmark_chg, 3)
                except Exception:
                    spread = pf_bid_buy = pf_bid_buy_chg = bid_buy_ucuzluk = pf_front_buy = pf_front_buy_chg = front_buy_ucuzluk = pf_ask_buy = pf_ask_buy_chg = ask_buy_ucuzluk = pf_ask_sell = pf_ask_sell_chg = ask_sell_pahali = pf_front_sell = pf_front_sell_chg = front_sell_pahali = pf_bid_sell = pf_bid_sell_chg = bid_sell_pahali = benchmark_chg = 'N/A'
            else:
                spread = pf_bid_buy = pf_bid_buy_chg = bid_buy_ucuzluk = pf_front_buy = pf_front_buy_chg = front_buy_ucuzluk = pf_ask_buy = pf_ask_buy_chg = ask_buy_ucuzluk = pf_ask_sell = pf_ask_sell_chg = ask_sell_pahali = pf_front_sell = pf_front_sell_chg = front_sell_pahali = pf_bid_sell = pf_bid_sell_chg = bid_sell_pahali = benchmark_chg = 'N/A'
            row = [checked_box, symbol, last, prev_close, bid, ask, spread, pref_type_val, benchmark_type, benchmark_chg,
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
            # Sadece bu pencereye ait tickerlar için cache'deki verileri al
            window_data = {symbol: self.ibkr.last_data.get(symbol, {}) for symbol in tickers}
            
            # Sıralama için tüm tickerları ve verilerini hazırla
            all_rows = []
            for symbol in tickers:
                row = row_for_symbol(symbol)
                all_rows.append(row)
            
            # Sıralama yap
            idx = COLUMNS.index(sort_col[0]) if sort_col[0] is not None else None
            if idx is not None:
                all_rows.sort(
                    key=lambda x: get_sort_key(x[idx]),
                    reverse=sort_reverse[0]
                )
            
            # Sayfalama uygula
            start = page[0] * items_per_page
            end = start + items_per_page
            page_rows = all_rows[start:end]
            
            # Tabloyu güncelle
            table.delete(*[i for i in table.get_children() if i not in ('desc_long','desc_short')])
            for row in page_rows:
                table.insert('', 'end', iid=row[1], values=row)
            
            # Sayfa bilgisini güncelle
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
        ttk.Button(action_frame, text='Seçili Tickerlara Hidden Order', command=lambda: None).pack(side='left', padx=2)  # TODO: order fonksiyonu
        nav = ttk.Frame(win)
        nav.pack(fill='x')
        btn_prev = ttk.Button(nav, text='<', command=lambda: (page.__setitem__(0, max(0, page[0]-1)), populate()))
        btn_prev.pack(side='left', padx=5)
        nav_lbl = ttk.Label(nav, text='Page 1')
        nav_lbl.pack(side='left', padx=5)
        btn_next = ttk.Button(nav, text='>', command=lambda: (page.__setitem__(0, min(page[0]+1, (len(tickers)-1)//items_per_page)), populate()))
        btn_next.pack(side='left', padx=5)
        def update_etf_panel():
            etf_panel.update(self.ibkr.get_etf_data())
            win.after(1000, update_etf_panel)
        update_etf_panel()
        populate()

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
                self.loop_job = self.after(3000, self.loop_step)
            else:
                self.loop_state['phase'] = 'C'
                self.notebook.select(1)
                self.extended_page = 0
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(3000, self.loop_step)
        elif self.loop_state['phase'] == 'C':
            max_page = (len(self.extended_tickers) - 1) // self.items_per_page
            if self.extended_page < max_page:
                self.extended_page += 1
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(3000, self.loop_step)
            else:
                self.loop_state['phase'] = 'T'
                self.notebook.select(0)
                self.historical_page = 0
                self.update_tables()
                self.subscribe_visible()
                self.loop_job = self.after(3000, self.loop_step)

    def open_take_profit_longs_window(self):
        import tkinter.font as tkFont
        import pandas as pd
        win = tk.Toplevel(self)
        win.title('Take Profit Longs')
        etf_panel = ETFPanel(win, ETF_SYMBOLS, compact=True)
        etf_panel.pack(fill='x', padx=2, pady=2)
        def load_csv_info(path):
            df = pd.read_csv(path)
            info = {}
            for _, row in df.iterrows():
                symbol = str(row['PREF IBKR']).strip()
                if symbol and symbol not in info:
                    info[symbol] = row.to_dict()
            return info
        t_info = load_csv_info('mastermind_histport.csv')
        c_info = load_csv_info('mastermind_extltport.csv')
        COLUMNS = [
            'Seç', 'Ticker', 'Qty', 'Last print', 'Previous close', 'Bid', 'Ask', 'Spread', 'Pref type', 'Benchmark type', 'Benchmark chg',
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
        checked = set()
        items_per_page = 17
        page = [0]
        sort_col = [None]
        sort_reverse = [False]
        def calculate_row(pos, t_info, c_info):
            symbol = pos['symbol']
            qty = pos['quantity']
            d = self.ibkr.last_data.get(symbol) or {}
            bid = d.get('bid', 'N/A')
            ask = d.get('ask', 'N/A')
            last = d.get('last', 'N/A')
            prev_close = d.get('prev_close', 'N/A')
            t_set = set(t_info.keys())
            c_set = set(c_info.keys())
            etf_data = self.ibkr.get_etf_data()
            if symbol in t_set:
                pref = 'T'
                info = t_info.get(symbol, {})
                benchmark_type = 'T'
                pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                benchmark_chg = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
            elif symbol in c_set:
                pref = 'C'
                info = c_info.get(symbol, {})
                benchmark_type = 'C'
                pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                benchmark_chg = round(pff_chg * 1.3 - tlt_chg * 0.1, 3)
            else:
                pref = '-'
                info = {}
                benchmark_type = '-'
                benchmark_chg = 0
            try:
                bid = float(bid)
                ask = float(ask)
                last = float(last)
                prev_close = float(prev_close)
                spread = ask - bid
                pf_bid_buy = round(bid + spread * 0.15, 3)
                pf_bid_buy_chg = round(pf_bid_buy - prev_close, 3)
                bid_buy_ucuzluk = round(pf_bid_buy_chg - benchmark_chg, 3)
                pf_front_buy = round(last + 0.01, 3)
                pf_front_buy_chg = round(pf_front_buy - prev_close, 3)
                front_buy_ucuzluk = round(pf_front_buy_chg - benchmark_chg, 3)
                pf_ask_buy = round(ask + 0.01, 3)
                pf_ask_buy_chg = round(pf_ask_buy - prev_close, 3)
                ask_buy_ucuzluk = round(pf_ask_buy_chg - benchmark_chg, 3)
                pf_ask_sell = round(ask - spread * 0.15, 3)
                pf_ask_sell_chg = round(pf_ask_sell - prev_close, 3)
                ask_sell_pahali = round(pf_ask_sell_chg - benchmark_chg, 3)
                pf_front_sell = round(last - 0.01, 3)
                pf_front_sell_chg = round(pf_front_sell - prev_close, 3)
                front_sell_pahali = round(pf_front_sell_chg - benchmark_chg, 3)
                pf_bid_sell = round(bid - 0.01, 3)
                pf_bid_sell_chg = round(pf_bid_sell - prev_close, 3)
                bid_sell_pahali = round(pf_bid_sell_chg - benchmark_chg, 3)
            except Exception:
                spread = pf_bid_buy = pf_bid_buy_chg = bid_buy_ucuzluk = pf_front_buy = pf_front_buy_chg = front_buy_ucuzluk = pf_ask_buy = pf_ask_buy_chg = ask_buy_ucuzluk = pf_ask_sell = pf_ask_sell_chg = ask_sell_pahali = pf_front_sell = pf_front_sell_chg = front_sell_pahali = pf_bid_sell = pf_bid_sell_chg = bid_sell_pahali = benchmark_chg = 'N/A'
            def green(val):
                return f'🟩 {val}' if val != 'N/A' else val
            def red(val):
                return f'🔺 {val}' if val != 'N/A' else val
            return [
                '\u2611' if symbol in checked else '\u2610', symbol, qty, last, prev_close, bid, ask, spread, info.get('Pref type', ''), benchmark_type, benchmark_chg,
                info.get('CMON', ''), info.get('Group', ''), info.get('AVG_ADV', ''), info.get('Final_Shares', ''), info.get('FINAL_THG', ''),
                pf_bid_buy, pf_bid_buy_chg, green(bid_buy_ucuzluk),
                pf_front_buy, pf_front_buy_chg, green(front_buy_ucuzluk),
                pf_ask_buy, pf_ask_buy_chg, green(ask_buy_ucuzluk),
                pf_ask_sell, pf_ask_sell_chg, red(ask_sell_pahali),
                pf_front_sell, pf_front_sell_chg, red(front_sell_pahali),
                pf_bid_sell, pf_bid_sell_chg, red(bid_sell_pahali)
            ]
        def get_all_positions():
            return [pos for pos in self.ibkr.get_positions() if pos['quantity'] > 0]
        def get_sort_key(val):
            try:
                if val is None or str(val).strip() in ('N/A', 'nan', ''):
                    return float('inf')
                return float(str(val).replace(',', ''))
            except Exception:
                return float('inf')
        def row_for_pos(pos):
            return calculate_row(pos, t_info, c_info)
        def populate():
            # Sadece long pozisyonlar için cache'deki verileri al
            positions = get_all_positions()
            position_symbols = {pos['symbol'] for pos in positions}
            window_data = {symbol: self.ibkr.last_data.get(symbol, {}) for symbol in position_symbols}
            
            # Sıralama için tüm pozisyonları ve verilerini hazırla
            all_rows = []
            for pos in positions:
                row = row_for_pos(pos)
                all_rows.append(row)
            
            # Sıralama yap
            idx = COLUMNS.index(sort_col[0]) if sort_col[0] is not None else None
            if idx is not None:
                all_rows.sort(
                    key=lambda x: get_sort_key(x[idx]),
                    reverse=sort_reverse[0]
                )
            
            # Sayfalama uygula
            start = page[0] * items_per_page
            end = start + items_per_page
            page_rows = all_rows[start:end]
            
            # Tabloyu güncelle
            table.delete(*table.get_children())
            for row in page_rows:
                table.insert('', 'end', iid=row[1], values=row)
            
            # Sayfa bilgisini güncelle
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
        ttk.Button(sel_frame, text='Tümünü Seç', command=lambda: (checked.clear(), checked.update([row[1] for row in sort_and_paginate_rows(positions, row_for_pos, sort_col_idx=COLUMNS.index(sort_col[0]) if sort_col[0] else None, sort_reverse=sort_reverse[0], page=page[0], items_per_page=items_per_page, get_sort_key_fn=get_sort_key)[0]]), populate())).pack(side='left', padx=2)
        ttk.Button(sel_frame, text='Tümünü Kaldır', command=lambda: (checked.clear(), populate())).pack(side='left', padx=2)
        action_frame = ttk.Frame(win)
        action_frame.pack(fill='x', pady=4)
        ttk.Button(action_frame, text='Seçili Pozisyonlara Hidden Buy', command=lambda: send_orders()).pack(side='left', padx=2)
        nav = ttk.Frame(win)
        nav.pack(fill='x')
        btn_prev = ttk.Button(nav, text='<', command=lambda: (page.__setitem__(0, max(0, page[0]-1)), populate()))
        btn_prev.pack(side='left', padx=5)
        nav_lbl = ttk.Label(nav, text='Page 1')
        nav_lbl.pack(side='left', padx=5)
        btn_next = ttk.Button(nav, text='>', command=lambda: (page.__setitem__(0, page[0]+1), populate()))
        btn_next.pack(side='left', padx=5)
        def send_orders():
            from ib_insync import LimitOrder, Stock
            from tkinter import messagebox
            sent = 0
            errors = []
            for symbol in checked:
                d = self.ibkr.tickers.get(symbol, {}).get('ticker')
                bid = d.bid if d else None
                ask = d.ask if d else None
                if bid is None or ask is None:
                    errors.append(f"{symbol}: Fiyat verisi yok.")
                    continue
                spread = ask - bid
                price = round(bid + spread * 0.15, 2)
                contract = Stock(symbol, 'SMART', 'USD')
                order = LimitOrder('BUY', 200, price)
                order.hidden = True
                try:
                    self.ibkr.ib.placeOrder(contract, order)
                    sent += 1
                except Exception as e:
                    errors.append(f"{symbol}: {e}")
            msg = f"{sent} adet hidden buy emri gönderildi."
            if errors:
                msg += "\nHatalar:\n" + "\n".join(errors)
            messagebox.showinfo('Emir Sonucu', msg)
        populate()

    def open_take_profit_shorts_window(self):
        import tkinter.font as tkFont
        import pandas as pd
        win = tk.Toplevel(self)
        win.title('Take Profit Shorts')
        etf_panel = ETFPanel(win, ETF_SYMBOLS, compact=True)
        etf_panel.pack(fill='x', padx=2, pady=2)
        def load_csv_info(path):
            df = pd.read_csv(path)
            info = {}
            for _, row in df.iterrows():
                symbol = str(row['PREF IBKR']).strip()
                if symbol and symbol not in info:
                    info[symbol] = row.to_dict()
            return info
        t_info = load_csv_info('mastermind_histport.csv')
        c_info = load_csv_info('mastermind_extltport.csv')
        COLUMNS = [
            'Seç', 'Ticker', 'Qty', 'Last print', 'Previous close', 'Bid', 'Ask', 'Spread', 'Pref type', 'Benchmark type', 'Benchmark chg',
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
        checked = set()
        items_per_page = 17
        page = [0]
        sort_col = [None]
        sort_reverse = [False]
        def calculate_row(pos, t_info, c_info):
            symbol = pos['symbol']
            qty = pos['quantity']
            d = self.ibkr.last_data.get(symbol) or {}
            bid = d.get('bid', 'N/A')
            ask = d.get('ask', 'N/A')
            last = d.get('last', 'N/A')
            prev_close = d.get('prev_close', 'N/A')
            t_set = set(t_info.keys())
            c_set = set(c_info.keys())
            etf_data = self.ibkr.get_etf_data()
            if symbol in t_set:
                pref = 'T'
                info = t_info.get(symbol, {})
                benchmark_type = 'T'
                pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                benchmark_chg = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
            elif symbol in c_set:
                pref = 'C'
                info = c_info.get(symbol, {})
                benchmark_type = 'C'
                pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                benchmark_chg = round(pff_chg * 1.3 - tlt_chg * 0.1, 3)
            else:
                pref = '-'
                info = {}
                benchmark_type = '-'
                benchmark_chg = 0
            try:
                bid = float(bid)
                ask = float(ask)
                last = float(last)
                prev_close = float(prev_close)
                spread = ask - bid
                pf_bid_buy = round(bid + spread * 0.15, 3)
                pf_bid_buy_chg = round(pf_bid_buy - prev_close, 3)
                bid_buy_ucuzluk = round(pf_bid_buy_chg - benchmark_chg, 3)
                pf_front_buy = round(last + 0.01, 3)
                pf_front_buy_chg = round(pf_front_buy - prev_close, 3)
                front_buy_ucuzluk = round(pf_front_buy_chg - benchmark_chg, 3)
                pf_ask_buy = round(ask + 0.01, 3)
                pf_ask_buy_chg = round(pf_ask_buy - prev_close, 3)
                ask_buy_ucuzluk = round(pf_ask_buy_chg - benchmark_chg, 3)
                pf_ask_sell = round(ask - spread * 0.15, 3)
                pf_ask_sell_chg = round(pf_ask_sell - prev_close, 3)
                ask_sell_pahali = round(pf_ask_sell_chg - benchmark_chg, 3)
                pf_front_sell = round(last - 0.01, 3)
                pf_front_sell_chg = round(pf_front_sell - prev_close, 3)
                front_sell_pahali = round(pf_front_sell_chg - benchmark_chg, 3)
                pf_bid_sell = round(bid - 0.01, 3)
                pf_bid_sell_chg = round(pf_bid_sell - prev_close, 3)
                bid_sell_pahali = round(pf_bid_sell_chg - benchmark_chg, 3)
            except Exception:
                spread = pf_bid_buy = pf_bid_buy_chg = bid_buy_ucuzluk = pf_front_buy = pf_front_buy_chg = front_buy_ucuzluk = pf_ask_buy = pf_ask_buy_chg = ask_buy_ucuzluk = pf_ask_sell = pf_ask_sell_chg = ask_sell_pahali = pf_front_sell = pf_front_sell_chg = front_sell_pahali = pf_bid_sell = pf_bid_sell_chg = bid_sell_pahali = benchmark_chg = 'N/A'
            def green(val):
                return f'🟩 {val}' if val != 'N/A' else val
            def red(val):
                return f'🔺 {val}' if val != 'N/A' else val
            return [
                '\u2611' if symbol in checked else '\u2610', symbol, qty, last, prev_close, bid, ask, spread, info.get('Pref type', ''), benchmark_type, benchmark_chg,
                info.get('CMON', ''), info.get('Group', ''), info.get('AVG_ADV', ''), info.get('Final_Shares', ''), info.get('FINAL_THG', ''),
                pf_bid_buy, pf_bid_buy_chg, green(bid_buy_ucuzluk),
                pf_front_buy, pf_front_buy_chg, green(front_buy_ucuzluk),
                pf_ask_buy, pf_ask_buy_chg, green(ask_buy_ucuzluk),
                pf_ask_sell, pf_ask_sell_chg, red(ask_sell_pahali),
                pf_front_sell, pf_front_sell_chg, red(front_sell_pahali),
                pf_bid_sell, pf_bid_sell_chg, red(bid_sell_pahali)
            ]
        def get_all_positions():
            return [pos for pos in self.ibkr.get_positions() if pos['quantity'] < 0]
        def get_sort_key(val):
            try:
                if val is None or str(val).strip() in ('N/A', 'nan', ''):
                    return float('inf')
                return float(str(val).replace(',', ''))
            except Exception:
                return float('inf')
        def row_for_pos(pos):
            return calculate_row(pos, t_info, c_info)
        def populate():
            # Sadece short pozisyonlar için cache'deki verileri al
            positions = get_all_positions()
            position_symbols = {pos['symbol'] for pos in positions}
            window_data = {symbol: self.ibkr.last_data.get(symbol, {}) for symbol in position_symbols}
            
            # Sıralama için tüm pozisyonları ve verilerini hazırla
            all_rows = []
            for pos in positions:
                row = row_for_pos(pos)
                all_rows.append(row)
            
            # Sıralama yap
            idx = COLUMNS.index(sort_col[0]) if sort_col[0] is not None else None
            if idx is not None:
                all_rows.sort(
                    key=lambda x: get_sort_key(x[idx]),
                    reverse=sort_reverse[0]
                )
            
            # Sayfalama uygula
            start = page[0] * items_per_page
            end = start + items_per_page
            page_rows = all_rows[start:end]
            
            # Tabloyu güncelle
            table.delete(*table.get_children())
            for row in page_rows:
                table.insert('', 'end', iid=row[1], values=row)
            
            # Sayfa bilgisini güncelle
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
        ttk.Button(sel_frame, text='Tümünü Seç', command=lambda: (checked.clear(), checked.update([row[1] for row in sort_and_paginate_rows(positions, row_for_pos, sort_col_idx=COLUMNS.index(sort_col[0]) if sort_col[0] else None, sort_reverse=sort_reverse[0], page=page[0], items_per_page=items_per_page, get_sort_key_fn=get_sort_key)[0]]), populate())).pack(side='left', padx=2)
        ttk.Button(sel_frame, text='Tümünü Kaldır', command=lambda: (checked.clear(), populate())).pack(side='left', padx=2)
        action_frame = ttk.Frame(win)
        action_frame.pack(fill='x', pady=4)
        ttk.Button(action_frame, text='Seçili Pozisyonlara Hidden Sell', command=lambda: send_orders()).pack(side='left', padx=2)
        nav = ttk.Frame(win)
        nav.pack(fill='x')
        btn_prev = ttk.Button(nav, text='<', command=lambda: (page.__setitem__(0, max(0, page[0]-1)), populate()))
        btn_prev.pack(side='left', padx=5)
        nav_lbl = ttk.Label(nav, text='Page 1')
        nav_lbl.pack(side='left', padx=5)
        btn_next = ttk.Button(nav, text='>', command=lambda: (page.__setitem__(0, page[0]+1), populate()))
        btn_next.pack(side='left', padx=5)
        def send_orders():
            from ib_insync import LimitOrder, Stock
            from tkinter import messagebox
            sent = 0
            errors = []
            for symbol in checked:
                d = self.ibkr.tickers.get(symbol, {}).get('ticker')
                bid = d.bid if d else None
                ask = d.ask if d else None
                if bid is None or ask is None:
                    errors.append(f"{symbol}: Fiyat verisi yok.")
                    continue
                spread = ask - bid
                price = round(ask - spread * 0.15, 2)
                contract = Stock(symbol, 'SMART', 'USD')
                order = LimitOrder('SELL', 200, price)
                order.hidden = True
                try:
                    self.ibkr.ib.placeOrder(contract, order)
                    sent += 1
                except Exception as e:
                    errors.append(f"{symbol}: {e}")
            msg = f"{sent} adet hidden sell emri gönderildi."
            if errors:
                msg += "\nHatalar:\n" + "\n".join(errors)
            messagebox.showinfo('Emir Sonucu', msg)
        populate() 