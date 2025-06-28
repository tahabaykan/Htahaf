import tkinter as tk
from tkinter import ttk
import pandas as pd
import threading
import time
from hammerib.gui.etf_panel import ETFPanel
from hammerib.ib_api.manager import ETF_SYMBOLS
from ib_insync import LimitOrder, Stock  # GEREKLİ İMPORT
from tkinter import messagebox  # messagebox fix
import tkinter.font as tkFont

CHECKED = '\u2611'  # ☑
UNCHECKED = '\u2610'  # ☐

def clean_symbol(symbol):
    return str(symbol).strip().replace('.', '').replace('/', '')

class MaltoplaWindow(tk.Toplevel):
    def __init__(self, parent, ibkr_manager, csv_path, benchmark_type):
        super().__init__(parent)
        self.title(f"{csv_path} Maltopla Analiz")
        self.ibkr = ibkr_manager
        self.csv_path = csv_path
        self.benchmark_type = benchmark_type  # 'T' or 'C'
        self.ticker_info = self.load_tickers_info()  # symbol -> dict with csv data
        self.tickers = list(self.ticker_info.keys())
        self.items_per_page = 20
        self.page = 0
        self.max_page = max(0, (len(self.tickers) - 1) // self.items_per_page)
        self.ticker_cache = {}  # symbol -> data dict
        self.ticker_handlers = {}  # symbol -> handler ref
        self.checked_tickers = set()
        self.etf_panel = ETFPanel(self, ETF_SYMBOLS, compact=True)
        self.etf_panel.pack(fill='x', padx=2, pady=2)
        self.after(1000, self.update_etf_panel)
        # Yeni kolonlar
        self.COLUMNS = [
            'Seç', 'Ticker', 'Last print', 'Previous close', 'Bid', 'Ask', 'Spread', 'Pref type', 'Benchmark type', 'Benchmark chg',
            'CMON', 'Group', 'AVG_ADV', 'Final_Shares', 'FINAL_THG',
            # Long/cover için
            'PF Bid buy', 'PF bid buy chg', '🟩 Bid buy Ucuzluk Skoru',
            'PF front buy', 'PF front buy chg', '🟩 Front buy ucuzluk skoru',
            'PF ask buy', 'PF ask buy chg', '🟩 Ask buy ucuzluk skoru',
            # Short/cover için
            'PF Ask sell', 'PF Ask sell chg', '🔺 Ask sell pahalilik skoru',
            'PF front sell', 'PF front sell chg', '🔺 Front sell pahalilik skoru',
            'PF bid sell', 'PF bid sell chg', '🔺 Bid sell pahalilik skoru'
        ]
        font_small = tkFont.Font(family="Arial", size=8)
        font_bold = tkFont.Font(family="Arial", size=8, weight="bold")
        style = ttk.Style()
        style.configure("Treeview.Heading", font=("Arial", 8))
        self.table = ttk.Treeview(self, columns=self.COLUMNS, show='headings', height=20)
        for col in self.COLUMNS:
            # Tüm ucuzluk ve pahalılık skoru kolonları için genişlik artır
            if 'Ucuzluk Skoru' in col or 'pahalilik skoru' in col:
                self.table.heading(col, text=col)
                self.table.column(col, width=80, anchor='center')
            else:
                self.table.heading(col, text=col)
                self.table.column(col, width=35 if col != 'Seç' else 25, anchor='center')
        self.table.tag_configure('small', font=font_small)
        self.table.tag_configure('bold', font=font_bold)
        self.table.tag_configure('green', foreground='#008000', font=font_bold)
        self.table.tag_configure('red', foreground='#B22222', font=font_bold)
        self.table.pack(fill='both', expand=True)
        self.table.bind('<Button-1>', self.on_table_click)
        # Açıklama satırları (ucuzluk skorları 🟩, pahalılık skorları 🔺)
        desc_long = (['']*15 + ['Long pozisyon açmak / arttırmak için, veya Short pozisyon kapatmak/azaltmak için'] + ['']*8)
        desc_short = (['']*24 + ['Short pozisyon açmak / arttırmak için, veya Long pozisyon kapatmak/azaltmak için'] + ['']*8)
        self.table.insert('', 'end', iid='desc_long', values=desc_long, tags=('small',))
        self.table.insert('', 'end', iid='desc_short', values=desc_short, tags=('small',))
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
        self.sort_col = None
        self.sort_reverse = False
        self.sorted_symbols = self.tickers[:]
        def get_sort_key(row, col_idx):
            val = row[col_idx]
            try:
                if isinstance(val, str) and val.startswith('🟩 '):
                    val = val[2:]
                elif isinstance(val, str) and val.startswith('🔺 '):
                    val = val[2:]
                if val in ('N/A', '', None) or (isinstance(val, float) and (val != val)):
                    return float('inf')
                return float(val)
            except Exception:
                return float('inf')
        def row_for_symbol(sym):
            d = self.ticker_cache.get(sym, {})
            bid = d.get('bid', 'N/A')
            ask = d.get('ask', 'N/A')
            last = d.get('last', 'N/A')
            prev_close = d.get('prev_close', 'N/A')
            checked = CHECKED if sym in self.checked_tickers else UNCHECKED
            pref_type = self.ticker_info.get(sym, {}).get('Pref type', '')
            benchmark_type = self.benchmark_type
            cmon = self.ticker_info.get(sym, {}).get('CMON', '')
            group = self.ticker_info.get(sym, {}).get('Group', '')
            avg_adv = self.ticker_info.get(sym, {}).get('AVG_ADV', '')
            final_shares = self.ticker_info.get(sym, {}).get('Final_Shares', '')
            final_thg = self.ticker_info.get(sym, {}).get('FINAL_THG', '')
            # ... hesaplamalar ...
            # (Kısa tutmak için orijinal insert_or_update_row fonksiyonundaki hesaplamaları buraya ekleyin)
            # ...
            # Sonuç olarak bir row listesi döndürmeli
            return [checked, sym, last, prev_close, bid, ask, 'N/A', pref_type, benchmark_type, 'N/A', cmon, group, avg_adv, final_shares, final_thg, 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        def populate_table_from_cache_sorted():
            self.table.delete(*self.table.get_children())
            # Açıklama satırlarını tekrar ekle
            self.table.insert('', 'end', iid='desc_long', values=(['']*15 + ['Long pozisyon açmak / arttırmak için, veya Short pozisyon kapatmak/azaltmak için'] + ['']*8), tags=('small',))
            self.table.insert('', 'end', iid='desc_short', values=(['']*24 + ['Short pozisyon açmak / arttırmak için, veya Long pozisyon kapatmak/azaltmak için'] + ['']*8), tags=('small',))
            symbols = self.sorted_symbols[:]
            # Sayfalama
            start = self.page * self.items_per_page
            end = min(start + self.items_per_page, len(symbols))
            for symbol in symbols[start:end]:
                self.insert_or_update_row(symbol)
            self.lbl_page.config(text=f'Page {self.page+1} / {max(1, (len(self.tickers)-1)//self.items_per_page+1)}')
        def on_heading_click(col):
            if self.sort_col == col:
                self.sort_reverse = not self.sort_reverse
            else:
                self.sort_col = col
                self.sort_reverse = False
            idx = self.COLUMNS.index(self.sort_col)
            # Tüm tickerlar için sıralama
            rows = []
            for sym in self.tickers:
                row = self.table.item(sym)['values'] if self.table.exists(sym) else None
                if not row:
                    # Eğer satır yoksa, cache'den oluştur
                    row = row_for_symbol(sym)
                rows.append(row)
            rows.sort(key=lambda r: (get_sort_key(r, idx) is None, get_sort_key(r, idx)), reverse=self.sort_reverse)
            self.sorted_symbols = [r[1] for r in rows]
            self.page = 0
            populate_table_from_cache_sorted()
        for col in self.COLUMNS:
            self.table.heading(col, text=col, command=lambda c=col: on_heading_click(c))
        # populate_table_from_cache_sorted fonksiyonunu kullan
        self.populate_table_from_cache = populate_table_from_cache_sorted
        self.populate_table_from_cache()

    def load_tickers_info(self):
        info = {}
        try:
            df = pd.read_csv(self.csv_path)
            cols = [c.strip() for c in df.columns]
            df.columns = cols
            for _, row in df.iterrows():
                symbol = row['PREF IBKR'] if 'PREF IBKR' in row and pd.notna(row['PREF IBKR']) else row.iloc[0]
                if pd.isna(symbol):
                    continue
                symbol = clean_symbol(symbol)
                info[symbol] = {
                    'CMON': row['CMON'] if 'CMON' in row else '',
                    'Group': row['Group'] if 'Group' in row else '',
                    'AVG_ADV': row['AVG_ADV'] if 'AVG_ADV' in row else '',
                    'Final_Shares': row['Final_Shares'] if 'Final_Shares' in row else '',
                    'FINAL_THG': row['FINAL_THG'] if 'FINAL_THG' in row else '',
                    'Pref type': row['Pref type'] if 'Pref type' in row else '',
                }
        except Exception:
            pass
        return info

    def get_visible_tickers(self):
        start = self.page * self.items_per_page
        end = min(start + self.items_per_page, len(self.tickers))
        return self.tickers[start:end]

    def subscribe_visible(self):
        visible = [clean_symbol(s) for s in self.get_visible_tickers()]
        print(f"[MaltoplaWindow] subscribe_visible (page {self.page}): {visible}")
        self.ibkr.clear_subscriptions()
        for symbol in list(self.ticker_handlers.keys()):
            if symbol not in visible:
                handler = self.ticker_handlers.pop(symbol, None)
                ticker_obj = self.ibkr.tickers.get(symbol, {}).get('ticker')
                if ticker_obj and handler:
                    try:
                        print(f"[MaltoplaWindow] handler removed: {symbol}")
                        ticker_obj.updateEvent -= handler
                    except Exception:
                        pass
        self.ibkr.subscribe_tickers(visible)
        for symbol in visible:
            ticker_obj = self.ibkr.tickers.get(symbol, {}).get('ticker')
            if ticker_obj and symbol not in self.ticker_handlers:
                def make_handler(sym):
                    def handler(ticker):
                        print(f"[MaltoplaWindow] on_ticker_update: {sym} {ticker}")
                        self.on_ticker_update(sym, ticker)
                    return handler
                handler = make_handler(symbol)
                print(f"[MaltoplaWindow] handler added: {symbol}")
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
        # Açıklama satırlarını tekrar ekle
        self.table.insert('', 'end', iid='desc_long', values=(['']*15 + ['Long pozisyon açmak / arttırmak için, veya Short pozisyon kapatmak/azaltmak için'] + ['']*8), tags=('small',))
        self.table.insert('', 'end', iid='desc_short', values=(['']*24 + ['Short pozisyon açmak / arttırmak için, veya Long pozisyon kapatmak/azaltmak için'] + ['']*8), tags=('small',))
        # Sayfalama
        start = self.page * self.items_per_page
        end = min(start + self.items_per_page, len(self.tickers))
        for symbol in self.tickers[start:end]:
            self.insert_or_update_row(symbol)
        self.lbl_page.config(text=f'Page {self.page+1} / {max(1, (len(self.tickers)-1)//self.items_per_page+1)}')

    def insert_or_update_row(self, symbol):
        # Sadece IBKRManager'daki last_data (cache) verisini kullan
        d = self.ibkr.last_data.get(symbol) or {}
        bid = d.get('bid', 'N/A')
        ask = d.get('ask', 'N/A')
        last = d.get('last', 'N/A')
        prev_close = d.get('prev_close', 'N/A')
        checked = CHECKED if symbol in self.checked_tickers else UNCHECKED
        pref_type = self.ticker_info.get(symbol, {}).get('Pref type', '')
        benchmark_type = self.benchmark_type
        cmon = self.ticker_info.get(symbol, {}).get('CMON', '')
        group = self.ticker_info.get(symbol, {}).get('Group', '')
        avg_adv = self.ticker_info.get(symbol, {}).get('AVG_ADV', '')
        final_shares = self.ticker_info.get(symbol, {}).get('Final_Shares', '')
        final_thg = self.ticker_info.get(symbol, {}).get('FINAL_THG', '')
        # Benchmark chg
        if bid != 'N/A' and ask != 'N/A' and prev_close != 'N/A' and last != 'N/A':
            try:
                bid = float(bid)
                ask = float(ask)
                last = float(last)
                prev_close = float(prev_close)
                spread = ask - bid
                if self.benchmark_type == 'T':
                    etf_data = self.ibkr.get_etf_data()
                    pff_chg = etf_data.get('PFF', {}).get('change', 0) or 0
                    tlt_chg = etf_data.get('TLT', {}).get('change', 0) or 0
                    benchmark_chg = round(pff_chg * 0.7 + tlt_chg * 0.1, 3)
                else:
                    etf_data = self.ibkr.get_etf_data()
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
        # Skor kolonlarını belirgin sembolle göster
        def green(val):
            return f'🟩 {val}' if val != 'N/A' else val
        def red(val):
            return f'🔺 {val}' if val != 'N/A' else val
        values = (
            checked, symbol, last, prev_close, bid, ask, spread, pref_type, benchmark_type, benchmark_chg,
            cmon, group, avg_adv, final_shares, final_thg,
            pf_bid_buy, pf_bid_buy_chg, green(bid_buy_ucuzluk),
            pf_front_buy, pf_front_buy_chg, green(front_buy_ucuzluk),
            pf_ask_buy, pf_ask_buy_chg, green(ask_buy_ucuzluk),
            pf_ask_sell, pf_ask_sell_chg, red(ask_sell_pahali),
            pf_front_sell, pf_front_sell_chg, red(front_sell_pahali),
            pf_bid_sell, pf_bid_sell_chg, red(bid_sell_pahali)
        )
        tags = ['small']
        if any(val != 'N/A' for val in [bid_buy_ucuzluk, front_buy_ucuzluk, ask_buy_ucuzluk]):
            tags.append('green')
        if any(val != 'N/A' for val in [ask_sell_pahali, front_sell_pahali, bid_sell_pahali]):
            tags.append('red')
        if self.table.exists(symbol):
            self.table.item(symbol, values=values, tags=tuple(tags))
        else:
            self.table.insert('', 'end', iid=symbol, values=values, tags=tuple(tags))

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
        selected = self.get_selected_tickers()
        if not selected:
            messagebox.showinfo('Uyarı', 'Lütfen en az bir hisse seçin.')
            return
        sent_orders = 0
        errors = []
        for symbol in selected:
            d = self.ticker_cache.get(symbol, {})
            bid = d.get('bid')
            ask = d.get('ask')
            if bid is None or ask is None or bid == 'N/A' or ask == 'N/A':
                errors.append(f"{symbol}: Fiyat verisi yok.")
                continue
            try:
                bid = float(bid)
                ask = float(ask)
                price = round(bid + (ask - bid) * 0.15, 2)
                contract = Stock(symbol, 'SMART', 'USD')
                order = LimitOrder('BUY', 200, price)
                order.hidden = True
                self.ibkr.ib.placeOrder(contract, order)
                sent_orders += 1
            except Exception as e:
                errors.append(f"{symbol}: {e}")
        msg = f"{sent_orders} adet hidden buy emri gönderildi."
        if errors:
            msg += "\nHatalar:\n" + "\n".join(errors)
        messagebox.showinfo('Emir Sonucu', msg)

    def on_spr_hidden_ask(self):
        selected = self.get_selected_tickers()
        if not selected:
            messagebox.showinfo('Uyarı', 'Lütfen en az bir hisse seçin.')
            return
        sent_orders = 0
        errors = []
        for symbol in selected:
            d = self.ticker_cache.get(symbol, {})
            bid = d.get('bid')
            ask = d.get('ask')
            if bid is None or ask is None or bid == 'N/A' or ask == 'N/A':
                errors.append(f"{symbol}: Fiyat verisi yok.")
                continue
            try:
                bid = float(bid)
                ask = float(ask)
                price = round(ask - (ask - bid) * 0.15, 2)
                contract = Stock(symbol, 'SMART', 'USD')
                order = LimitOrder('SELL', 200, price)
                order.hidden = True
                self.ibkr.ib.placeOrder(contract, order)
                sent_orders += 1
            except Exception as e:
                errors.append(f"{symbol}: {e}")
        msg = f"{sent_orders} adet hidden sell emri gönderildi."
        if errors:
            msg += "\nHatalar:\n" + "\n".join(errors)
        messagebox.showinfo('Emir Sonucu', msg)

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

    def sort_by_column(self, col):
        if self.sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = col
            self.sort_reverse = False
        self.populate_table_from_cache()

    # update_ticker_cache_polling fonksiyonunu ve self.after(1500, ...) çağrılarını kaldır
    # Artık sadece event handler ile güncelleme olacak 