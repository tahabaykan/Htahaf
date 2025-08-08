import tkinter as tk
from tkinter import ttk
import tkinter.font as tkFont
import pandas as pd
from ib_insync import IB, Stock, LimitOrder
import logging
from Ntahaf.ib_api.conid_manager import load_conids
import threading
import time

# Logging ayarları
logger = logging.getLogger('MaltoplaWindow')
logger.setLevel(logging.INFO)

# Konsola log yazdırmak için handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def polygonize_ticker(symbol):
    symbol = str(symbol).strip()
    if ' PR' in symbol:
        base, pr = symbol.split(' PR', 1)
        return f"{base}p{pr.strip().upper()}"
    return symbol

def create_stock_contract(symbol):
    return Stock(symbol.strip(), 'SMART', 'USD')

symbol_to_conid = load_conids()

def create_ibkr_contract(symbol, conid=None):
    if conid:
        return Stock(symbol, 'SMART', 'USD', conId=conid)
    else:
        return Stock(symbol, 'SMART', 'USD')

def load_mastermind_data():
    data = {}
    for csv_path in ["Ntahaf/mastermind_histport.csv", "Ntahaf/mastermind_extltport.csv"]:
        try:
            df = pd.read_csv(csv_path)
            for _, row in df.iterrows():
                ticker = str(row.get("PREF IBKR", "")).strip()
                if not ticker:
                    continue
                if ticker not in data:
                    data[ticker] = {}
                for col in row.index:
                    if col != "PREF IBKR":
                        data[ticker][col] = row[col]
        except Exception as e:
            print(f"CSV okunamadı: {csv_path} - {e}")
    return data

def load_smi_data():
    """SMI rate verilerini yükle"""
    smi_data = {}
    try:
        df = pd.read_csv('Smiall.csv')
        for _, row in df.iterrows():
            ticker = str(row.get("PREF IBKR", "")).strip()
            smi_rate = row.get("SMI", 0)
            if ticker:
                smi_data[ticker] = smi_rate
        print(f"SMI data yüklendi: {len(smi_data)} hisse")
    except Exception as e:
        print(f"SMI CSV okunamadı: Smiall.csv - {e}")
    return smi_data

class MaltoplaWindow(tk.Toplevel):
    def __init__(self, parent, title, csv_path, market_data_dict, etf_data, benchmark_type='T', ibkr_client=None, exdiv_data=None, c_ticker_to_csv=None, c_csv_data=None):
        print(f"[DEBUG] MaltoplaWindow __init__ parent.psf_algo var mı? {hasattr(parent, 'psf_algo')}")
        super().__init__(parent)
        self.ib = ibkr_client  # Ana uygulamadan gelen mevcut bağlantıyı kullan
        self.exdiv_data = exdiv_data or {}
        self.c_ticker_to_csv = c_ticker_to_csv
        self.c_csv_data = c_csv_data
        self.title(title)
        self.parent = parent
        self.csv_path = csv_path
        self.market_data_dict = market_data_dict
        self.etf_data = etf_data
        self.benchmark_type = benchmark_type
        self.items_per_page = 20
        self.page = 0
        self.selected_tickers = set()  # Seçili ticker'lar (unique)
        self.sorted_col = None
        self.sort_reverse = False
        self.rows = []
        self.selected_lots = {}
        self.confirmation_window_open = False  # Onay penceresi kontrolü için
        COLUMNS = [
            'Seç', 'Ticker', 'Last price', 'Daily change', 'Benchmark change', 'FINAL_THG', 'Previous close',
            'Bid', 'Ask', 'Spread', 'Volume',
            'Bid buy Ucuzluk skoru', 'Final BB skor',
            'Front buy ucuzluk skoru', 'Final FB skor',
            'Ask buy ucuzluk skoru', 'Final AB skor',
            'Ask sell pahalilik skoru', 'Final AS skor',
            'Front sell pahalilik skoru', 'Final FS skor',
            'Bid sell pahalilik skoru', 'Final BS skor',
            'Benchmark type', 'Quantity', 'CMON', 'AVG_ADV', 'MAXALW Size', 'Final_Shares',
            'PF Bid buy', 'PF bid buy chg', 'PF front buy', 'PF front buy chg',
            'PF ask buy', 'PF ask buy chg', 'PF ask sell', 'PF ask sell chg',
            'PF front sell', 'PF front sell chg', 'PF bid sell', 'PF bid sell chg',
            'SMI rate', 'Mevcut Pozisyon'
        ]
        self.COLUMNS = COLUMNS
        LONG_HEADER = "Long pozisyon açmak / arttırmak için, veya Short pozisyon kapatmak/azaltmak için"
        SHORT_HEADER = "Short pozisyon açmak / arttırmak için, veya Long pozisyon kapatmak/azaltmak için"
        font_bold = tkFont.Font(family="Arial", size=6, weight="bold")
        font_normal = tkFont.Font(family="Arial", size=6)
        
        # Stil ayarları
        style = ttk.Style()
        style.configure("Treeview.Heading", font=("Arial", 6))
        
        # Özel başlık stilleri
        style.configure("Green.Treeview.Heading", foreground="dark green")
        style.configure("Yellow.Treeview.Heading", foreground="dark goldenrod")
        style.configure("Red.Treeview.Heading", foreground="dark red")
        
        # ✅ PSFAlgo aktif skor vurgulama stili
        style.configure("PSFActive.Treeview.Heading", background="lightblue", foreground="navy", font=("Arial", 7, "bold"))
        
        # ✅ PSFAlgo durumuna göre aktif skor kolonunu belirle
        active_score_column = None
        if hasattr(parent, 'psf_algo') and parent.psf_algo and parent.psf_algo.is_active:
            chain_state = getattr(parent.psf_algo, 'chain_state', None)
            if chain_state == 'T_LOSERS' or chain_state == 'T_LOSERS_FB':
                active_score_column = 'Final BB skor'  # BID BUY için
            elif chain_state == 'T_GAINERS' or chain_state == 'T_GAINERS_FS':
                active_score_column = 'Final AS skor'  # ASK SELL için (en düşük)
            elif chain_state == 'LONG_TP_AS':
                active_score_column = 'Final AS skor'  # Long TP Ask Sell
            elif chain_state == 'LONG_TP_FS':
                active_score_column = 'Final FS skor'  # Long TP Front Sell
            elif chain_state == 'SHORT_TP_BB':
                active_score_column = 'Final BB skor'  # Short TP Bid Buy
            elif chain_state == 'SHORT_TP_FB':
                active_score_column = 'Final FB skor'  # Short TP Front Buy
        
        self.table = ttk.Treeview(self, columns=COLUMNS, show='headings', height=20)
        
        # Kolon başlıklarını ayarla
        for col in COLUMNS:
            # ✅ PSFAlgo aktif skor kolonu vurgulaması
            if col == active_score_column:
                # PSFAlgo aktif skor kolonu - özel vurgulama
                self.table.heading(col, text=f"🎯 {col} 🎯", command=lambda c=col: self.sort_by_column(c))
                self.table.column(col, width=85, anchor='center')  # Biraz daha geniş
                print(f"[MALTOPLA] ✅ Aktif skor kolonu vurgulandı: {col}")
            else:
                # Başlık renklerini belirle (sadece satır/hücre için kullanılacak)
                if col in ['Bid buy Ucuzluk skoru', 'Ask sell pahalilik skoru']:
                    style_name = "Green.Treeview.Heading"
                elif col in ['Front buy ucuzluk skoru', 'Front sell pahalilik skoru']:
                    style_name = "Yellow.Treeview.Heading"
                elif col in ['Ask buy ucuzluk skoru', 'Bid sell pahalilik skoru']:
                    style_name = "Red.Treeview.Heading"
                else:
                    style_name = "Treeview.Heading"
                # Sadece text ve command parametrelerini kullan
                self.table.heading(col, text=col, command=lambda c=col: self.sort_by_column(c))
                
            # Kolon genişliği ayarı (aktif skor dışında)
            if col != active_score_column:
                if col in [
                    'Bid buy Ucuzluk skoru', 'Front buy ucuzluk skoru', 'Ask buy ucuzluk skoru',
                    'Ask sell pahalilik skoru', 'Front sell pahalilik skoru', 'Bid sell pahalilik skoru']:
                    self.table.column(col, width=70, anchor='center')
                elif col == 'Seç':
                    self.table.column(col, width=25, anchor='center')
                elif col == 'MAXALW Size':
                    self.table.column(col, width=80, anchor='center')  # MAXALW Size için özel genişlik
                # Final_Shares'ten sonraki kolonlar için genişliği yarıya indir
                elif COLUMNS.index(col) > COLUMNS.index('Final_Shares'):
                    self.table.column(col, width=25, anchor='center')
                else:
                    self.table.column(col, width=50, anchor='center')
        
        # Tag'leri yapılandır
        self.table.tag_configure('bold', font=font_bold)
        self.table.tag_configure('normal', font=font_normal)
        
        # Hücre renkleri için tag'ler
        self.table.tag_configure('green_cell', foreground='dark green')
        self.table.tag_configure('yellow_cell', foreground='dark goldenrod')
        self.table.tag_configure('red_cell', foreground='dark red')
        
        self.table.pack(fill='both', expand=True, side='top')
        # Navigation ve seçim butonları (tablonun hemen altına, scrollbar'ın üstüne)
        nav = ttk.Frame(self)
        nav.pack(fill='x', pady=2, side='top')
        btn_prev = ttk.Button(nav, text='< Önceki', width=8, command=self.prev_page)
        btn_prev.pack(side='left', padx=2)
        self.lbl_page = ttk.Label(nav, text='Page 1')
        self.lbl_page.pack(side='left', padx=2)
        btn_next = ttk.Button(nav, text='Sonraki >', width=8, command=self.next_page)
        btn_next.pack(side='left', padx=2)
        btn_select_all = ttk.Button(nav, text='Tümünü Seç', width=10, command=self.select_all)
        btn_select_all.pack(side='left', padx=2)
        btn_deselect_all = ttk.Button(nav, text='Tümünü Kaldır', width=12, command=self.deselect_all)
        btn_deselect_all.pack(side='left', padx=2)
        # Emir butonları ve lot entry
        order_frame = ttk.Frame(self)
        order_frame.pack(fill='x', pady=2, side='top')
        # Lot butonu ve entry
        def send_lot_orders():
            self.size_toggle.set('')  # Toggle'ı kapat
            self._send_orders_with_lot_only()
        lot_btn = ttk.Button(order_frame, text='Lot', width=6, command=send_lot_orders)
        lot_btn.pack(side='left', padx=2)
        # Avgadv lot butonu
        def set_avgadv_lots():
            updated = []
            for row in self.rows:
                ticker = row[1]
                if ticker not in self.selected_tickers:
                    continue
                try:
                    avg_adv = float(row[self.COLUMNS.index('AVG_ADV')])
                    lot = avg_adv / 40
                    if lot > 2000:
                        lot = lot / 2
                    lot = int(round((lot + 50) / 100) * 100)  # En yakın 100'e
                    if lot < 200:
                        lot = 200
                    self.selected_lots[ticker] = lot
                    updated.append(f"{ticker}: {lot}")
                except Exception:
                    continue
            if updated:
                from tkinter import messagebox
                messagebox.showinfo("Avgadv Lot Ayarlandı", "\n".join(updated))
            else:
                from tkinter import messagebox
                messagebox.showinfo("Avgadv Lot", "Seçili hisselerde geçerli AVG_ADV yok.")
        avgadv_btn = ttk.Button(order_frame, text='Avgadv lot', width=10, command=set_avgadv_lots)
        avgadv_btn.pack(side='left', padx=2)

        # --- Yüzde toggle butonları ---
        self.size_toggle = tk.StringVar(value='')  # '', '20', '50', '100'
        def set_toggle(val):
            self.size_toggle.set(val)
        pct20_btn = ttk.Button(order_frame, text='%20', width=5, command=lambda: set_toggle('20'))
        pct20_btn.pack(side='left', padx=1)
        pct50_btn = ttk.Button(order_frame, text='%50', width=5, command=lambda: set_toggle('50'))
        pct50_btn.pack(side='left', padx=1)
        pct100_btn = ttk.Button(order_frame, text='%100', width=5, command=lambda: set_toggle('100'))
        pct100_btn.pack(side='left', padx=1)
        # Toggle kapatma için tekrar tıklama
        def toggle_off(event, val):
            if self.size_toggle.get() == val:
                self.size_toggle.set('')
        pct20_btn.bind('<Button-1>', lambda e: toggle_off(e, '20') if self.size_toggle.get() == '20' else None)
        pct50_btn.bind('<Button-1>', lambda e: toggle_off(e, '50') if self.size_toggle.get() == '50' else None)
        pct100_btn.bind('<Button-1>', lambda e: toggle_off(e, '100') if self.size_toggle.get() == '100' else None)

        # Emir butonları
        ttk.Button(order_frame, text='Bid buy', width=8, command=self.send_bid_buy_orders).pack(side='left', padx=2)
        ttk.Button(order_frame, text='Front buy', width=8, command=self.send_front_buy_orders).pack(side='left', padx=2)
        ttk.Button(order_frame, text='Ask buy', width=8, command=self.send_ask_buy_orders).pack(side='left', padx=2)
        ttk.Button(order_frame, text='Ask sell', width=8, command=self.send_ask_sell_orders).pack(side='left', padx=2)
        ttk.Button(order_frame, text='Front sell', width=8, command=self.send_front_sell_orders).pack(side='left', padx=2)
        ttk.Button(order_frame, text='Bid sell', width=8, command=self.send_bid_sell_orders).pack(side='left', padx=2)
        # Orderbook butonu
        def open_orderbook():
            selected = list(self.selected_tickers)
            if not selected:
                from tkinter import messagebox
                messagebox.showinfo("Orderbook", "Lütfen bir hisse seçin.")
                return
            ticker = selected[0]
            # Orderbook penceresini aç (IBKR entegrasyonu ile)
            from Ntahaf.gui.orderbook_window import OrderBookWindow
            OrderBookWindow(self, ticker, self.ib)
        orderbook_btn = ttk.Button(order_frame, text='Orderbook', width=10, command=open_orderbook)
        orderbook_btn.pack(side='left', padx=2)
        # Scrollbar ekle (hem yatay hem dikey)
        xscroll = ttk.Scrollbar(self, orient='horizontal', command=self.table.xview)
        yscroll = ttk.Scrollbar(self, orient='vertical', command=self.table.yview)
        self.table.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        xscroll.pack(side='bottom', fill='x')
        yscroll.pack(side='right', fill='y')
        self.table.bind('<Button-1>', self.on_table_click)
        # Açıklama satırları
        self.table.insert('', 'end', iid='desc_long', values=(['']*2 + [LONG_HEADER] + ['']*(len(COLUMNS)-3)), tags=('bold',))
        self.table.insert('', 'end', iid='desc_short', values=(['']*11 + [SHORT_HEADER] + ['']*(len(COLUMNS)-12)), tags=('bold',))
        # CSV oku ve satırları hazırla
        if isinstance(csv_path, pd.DataFrame):
            df = csv_path.copy()
        else:
            df = pd.read_csv(csv_path)
        seen_ibkr = set()
        seen_poly = set()
        mastermind_data = load_mastermind_data()
        smi_data = load_smi_data()
        for _, row in df.iterrows():
            ticker = str(row['PREF IBKR']).strip()
            poly = polygonize_ticker(ticker)
            if ticker in seen_ibkr or poly in seen_poly:
                continue
            seen_ibkr.add(ticker)
            seen_poly.add(poly)
            md = market_data_dict.get(poly, {})
            mm_row = mastermind_data.get(ticker, {})
            smi_rate = smi_data.get(ticker, 0)
            # C-pref ise ilgili CSV'den veri çek
            def get_val(col):
                val = row.get(col, '')
                # SSFINEK CSV'lerinde zaten tüm veriler var, mastermind_data'ya ihtiyaç yok
                # Sadece CSV'den gelen veriyi kullan
                if val == '' or pd.isna(val):
                    return 'N/A'
                return val
            last = md.get('last', 'N/A')
            prev_close = md.get('prev_close', 'N/A')
            
            # ✅ EXDIV uygulaması - Daily change hesaplamasından ÖNCE yapılmalı
            try:
                prev_close_f = float(prev_close)
                div = self.exdiv_data.get(ticker, 0)
                if div and float(div) > 0:
                    # Temettü düzeltmesi: previous close'dan temettü miktarını çıkar
                    adjusted_prev_close = prev_close_f - float(div)
                    print(f"[EXDIV] {ticker}: Previous close {prev_close_f:.2f} → {adjusted_prev_close:.2f} (div: {div})")
                    prev_close_f = adjusted_prev_close
                    prev_close = adjusted_prev_close  # String olarak da güncelle
                else:
                    prev_close_f = float(prev_close)
            except Exception as e:
                print(f"[EXDIV] {ticker} ex-div uygulaması hatası: {e}")
                try:
                    prev_close_f = float(prev_close)
                except:
                    prev_close_f = None
            
            # ✅ Last price = 0 veya N/A ise previous close'u kullan
            try:
                last_f = float(last)
                if last_f <= 0:  # Last price 0 veya negatifse
                    print(f"[PRICE FIX] {ticker}: Last price {last} → Previous close {prev_close} kullanılıyor")
                    last = prev_close
                    last_f = prev_close_f if prev_close_f is not None else None
            except:
                # Last price parse edilemiyorsa da previous close'u dene
                if last in ['N/A', '', None, 0, '0']:
                    print(f"[PRICE FIX] {ticker}: Last price geçersiz ({last}) → Previous close {prev_close} kullanılıyor")
                    last = prev_close
                    last_f = prev_close_f if prev_close_f is not None else None
                else:
                    last_f = None
            bid = md.get('bid', 'N/A')
            ask = md.get('ask', 'N/A')
            volume = md.get('volume', 'N/A')
            final_thg = get_val('FINAL_THG')
            avg_adv = get_val('AVG_ADV')
            cmon = get_val('CMON')
            final_shares = get_val('Final_Shares')
            try:
                spread = float(ask) - float(bid)
            except:
                spread = 'N/A'
            if benchmark_type == 'T' and hasattr(parent, 'get_tpref_benchmark') and hasattr(parent, 'historical_tickers') and ticker in parent.historical_tickers:
                pff_chg = etf_data.get('PFF', {}).get('change', 0)
                tlt_chg = etf_data.get('TLT', {}).get('change', 0)
                benchmark_chg = parent.get_tpref_benchmark(ticker, pff_chg, tlt_chg)
                cgrup = getattr(parent, 'tpref_cgrup_map', {}).get(ticker, '')
                benchmark_type_str = f'T-{cgrup}' if cgrup else 'T'
            elif hasattr(parent, 'c_type_extra_tickers') and (ticker in getattr(parent, 'extended_tickers', set()) or ticker in parent.c_type_extra_tickers):
                try:
                    benchmark_chg = etf_data['PFF']['change'] * 1.3 - etf_data['TLT']['change'] * 0.1
                except:
                    benchmark_chg = 'N/A'
                benchmark_type_str = 'C'
            else:
                # ✅ Default benchmark değeri - 0 yerine None kullan
                benchmark_chg = 0  # 'N/A' yerine 0 kullan
                benchmark_type_str = ''
            def safe_float(x):
                try: return float(x)
                except: return None
            def fmt(x):
                try:
                    f = float(x)
                    return f"{f:.2f}"
                except:
                    return x
            bid_f = safe_float(bid)
            ask_f = safe_float(ask)
            spread_f = safe_float(spread)
            bench_f = safe_float(benchmark_chg)
            # ✅ prev_close_f zaten ex-div düzeltilmiş, yeniden safe_float ile çevirme
            # prev_close_f = safe_float(prev_close)  # Bu satır ex-div düzeltmesini etkisiz hale getiriyor
            daily_change = last_f - prev_close_f if last_f is not None and prev_close_f is not None else 'N/A'
            pf_bid_buy = bid_f + spread_f * 0.15 if bid_f is not None and spread_f is not None else 'N/A'
            pf_bid_buy_chg = pf_bid_buy - prev_close_f if pf_bid_buy != 'N/A' and prev_close_f is not None else 'N/A'
            bid_buy_ucuzluk = pf_bid_buy_chg - bench_f if pf_bid_buy_chg != 'N/A' and bench_f is not None else 'N/A'
            pf_front_buy = last_f + 0.01 if last_f is not None else 'N/A'
            pf_front_buy_chg = pf_front_buy - prev_close_f if pf_front_buy != 'N/A' and prev_close_f is not None else 'N/A'
            front_buy_ucuzluk = pf_front_buy_chg - bench_f if pf_front_buy_chg != 'N/A' and bench_f is not None else 'N/A'
            pf_ask_buy = ask_f + 0.01 if ask_f is not None else 'N/A'
            pf_ask_buy_chg = pf_ask_buy - prev_close_f if pf_ask_buy != 'N/A' and prev_close_f is not None else 'N/A'
            ask_buy_ucuzluk = pf_ask_buy_chg - bench_f if pf_ask_buy_chg != 'N/A' and bench_f is not None else 'N/A'
            pf_ask_sell = ask_f - spread_f * 0.15 if ask_f is not None and spread_f is not None else 'N/A'
            pf_ask_sell_chg = pf_ask_sell - prev_close_f if pf_ask_sell != 'N/A' and prev_close_f is not None else 'N/A'
            ask_sell_pahali = pf_ask_sell_chg - bench_f if pf_ask_sell_chg != 'N/A' and bench_f is not None else 'N/A'
            pf_front_sell = last_f - 0.01 if last_f is not None else 'N/A'
            pf_front_sell_chg = pf_front_sell - prev_close_f if pf_front_sell != 'N/A' and prev_close_f is not None else 'N/A'
            front_sell_pahali = pf_front_sell_chg - bench_f if pf_front_sell_chg != 'N/A' and bench_f is not None else 'N/A'
            pf_bid_sell = bid_f - 0.01 if bid_f is not None else 'N/A'
            pf_bid_sell_chg = pf_bid_sell - prev_close_f if pf_bid_sell != 'N/A' and prev_close_f is not None else 'N/A'
            bid_sell_pahali = pf_bid_sell_chg - bench_f if pf_bid_sell_chg != 'N/A' and bench_f is not None else 'N/A'
            # --- Final skorlar hesaplama ---
            def final_skor(final_thg, skor):
                try:
                    return float(final_thg) - 400 * float(skor)
                except:
                    return 'N/A'
            final_bb = final_skor(final_thg, bid_buy_ucuzluk)
            final_fb = final_skor(final_thg, front_buy_ucuzluk)
            final_ab = final_skor(final_thg, ask_buy_ucuzluk)
            final_as = final_skor(final_thg, ask_sell_pahali)
            final_fs = final_skor(final_thg, front_sell_pahali)
            final_bs = final_skor(final_thg, bid_sell_pahali)
            # ✅ Quantity değerini DataFrame'den al (Take Profit pencerelerinde)
            quantity_value = row.get('Quantity', self.get_current_position_size(ticker))
            
            # ✅ MAXALW Size hesapla (AVGADV/10)
            try:
                maxalw_size = int(float(avg_adv) / 10) if avg_adv and avg_adv != 'N/A' else 'N/A'
            except:
                maxalw_size = 'N/A'
            
            row_tuple = [
                '', ticker, fmt(last), fmt(daily_change), fmt(benchmark_chg), fmt(final_thg), fmt(prev_close),
                fmt(bid), fmt(ask), fmt(spread), fmt(volume),
                fmt(bid_buy_ucuzluk), fmt(final_bb),
                fmt(front_buy_ucuzluk), fmt(final_fb),
                fmt(ask_buy_ucuzluk), fmt(final_ab),
                fmt(ask_sell_pahali), fmt(final_as),
                fmt(front_sell_pahali), fmt(final_fs),
                fmt(bid_sell_pahali), fmt(final_bs),
                benchmark_type_str, fmt(quantity_value), fmt(cmon), fmt(avg_adv), fmt(maxalw_size), fmt(final_shares),
                fmt(pf_bid_buy), fmt(pf_bid_buy_chg), fmt(pf_front_buy), fmt(pf_front_buy_chg),
                fmt(pf_ask_buy), fmt(pf_ask_buy_chg), fmt(pf_ask_sell), fmt(pf_ask_sell_chg),
                fmt(pf_front_sell), fmt(pf_front_sell_chg), fmt(pf_bid_sell), fmt(pf_bid_sell_chg),
                fmt(smi_rate), fmt(self.get_current_position_size(ticker))
            ]
            self.rows.append(row_tuple)
        
        # ✅ PSFAlgo1 ve PSFAlgo2 entegrasyonu - aktif olanı tespit et (populate_table'dan ÖNCE)
        self.psf_algo = None
        print(f"[DEBUG] parent.psf_algo1 var mı? {hasattr(parent, 'psf_algo1')}")
        print(f"[DEBUG] parent.psf_algo1 aktif mi? {hasattr(parent, 'psf_algo1') and parent.psf_algo1 and parent.psf_algo1.is_active}")
        print(f"[DEBUG] parent.psf_algo2 var mı? {hasattr(parent, 'psf_algo2')}")
        print(f"[DEBUG] parent.psf_algo2 aktif mi? {hasattr(parent, 'psf_algo2') and parent.psf_algo2 and parent.psf_algo2.is_active}")
        print(f"[DEBUG] parent.psf_algo var mı? {hasattr(parent, 'psf_algo')}")
        
        if hasattr(parent, 'psf_algo1') and parent.psf_algo1 and parent.psf_algo1.is_active:
            self.psf_algo = parent.psf_algo1
            print("[MALTOPLA] PSFAlgo1 entegrasyonu aktif")
        elif hasattr(parent, 'psf_algo2') and parent.psf_algo2 and parent.psf_algo2.is_active:
            self.psf_algo = parent.psf_algo2
            print("[MALTOPLA] PSFAlgo2 entegrasyonu aktif")
        elif hasattr(parent, 'psf_algo') and parent.psf_algo:
            # Backward compatibility
            self.psf_algo = parent.psf_algo
            print("[MALTOPLA] Eski PSFAlgo entegrasyonu aktif (backward compatibility)")
        else:
            print("[MALTOPLA] PSFAlgo entegrasyonu yok")
        
        # ✅ Aktif PSFAlgo'ya pencere referansını ver
        if self.psf_algo:
            print(f"[MALTOPLA] {self.psf_algo.__class__.__name__} current_window ayarlanıyor")
            self.psf_algo.current_window = self
            # PSFAlgo'ya pencere açıldığını bildir
            if hasattr(self.psf_algo, 'on_window_opened'):
                self.psf_algo.on_window_opened(self)
                print(f"[MALTOPLA] {self.psf_algo.__class__.__name__}.on_window_opened çağrıldı")

        # ✅ En son populate_table çağır - PSFAlgo entegrasyonu tamamlandıktan sonra
        self.populate_table()

    def populate_table(self):
        print("[DEBUG] MaltoplaWindow.populate_table çağrıldı")
        print(f"[DEBUG] populate_table'da self.psf_algo var mı? {hasattr(self, 'psf_algo') and self.psf_algo is not None}")
        for item in self.table.get_children():
            if item not in ('desc_long', 'desc_short'):
                self.table.delete(item)
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        for i, row in enumerate(self.rows[start:end]):
            ticker = row[1]
            sel = '\u2611' if ticker in self.selected_tickers else '\u2610'
            row_disp = [sel] + list(row[1:])
            item_id = f'row_{self.page*self.items_per_page+i}'
            self.table.insert('', 'end', iid=item_id, values=row_disp)
            # Hücrelere renk uygula
            for col_idx, col_name in enumerate(self.COLUMNS):
                if col_name in ['Bid buy Ucuzluk skoru', 'Ask sell pahalilik skoru']:
                    self.table.set(item_id, col_idx, row_disp[col_idx])
                    self.table.item(item_id, tags=('green_cell',))
                elif col_name in ['Front buy ucuzluk skoru', 'Front sell pahalilik skoru']:
                    self.table.set(item_id, col_idx, row_disp[col_idx])
                    self.table.item(item_id, tags=('yellow_cell',))
                elif col_name in ['Ask buy ucuzluk skoru', 'Bid sell pahalilik skoru']:
                    self.table.set(item_id, col_idx, row_disp[col_idx])
                    self.table.item(item_id, tags=('red_cell',))
        total_pages = (len(self.rows) + self.items_per_page - 1) // self.items_per_page
        self.lbl_page.config(text=f'Page {self.page+1} / {total_pages}')

        # ✅ Veri yüklendiğinde aktif PSFAlgo'ya bildir
        import traceback
        if hasattr(self, 'psf_algo') and self.psf_algo is not None:
            print(f"[DEBUG] MaltoplaWindow {self.psf_algo.__class__.__name__}.on_data_ready çağrılıyor")
            try:
                self.psf_algo.on_data_ready(self)
                print(f"[DEBUG] MaltoplaWindow {self.psf_algo.__class__.__name__}.on_data_ready çağrısı başarılı")
            except Exception as e:
                print(f"[DEBUG] psf_algo.on_data_ready hata: {e}")
                traceback.print_exc()
        elif hasattr(self.parent, 'psf_algo') and self.parent.psf_algo is not None:
            print("[DEBUG] MaltoplaWindow psf_algo.on_data_ready çağrılıyor (parent üzerinden - backward compatibility)")
            try:
                self.parent.psf_algo.on_data_ready(self)
                print("[DEBUG] MaltoplaWindow psf_algo.on_data_ready çağrısı başarılı")
            except Exception as e:
                print(f"[DEBUG] psf_algo.on_data_ready hata: {e}")
                traceback.print_exc()

    def prev_page(self):
        total_pages = (len(self.rows) + self.items_per_page - 1) // self.items_per_page
        if self.page > 0:
            self.page -= 1
        else:
            self.page = total_pages - 1 if total_pages > 0 else 0
        self.populate_table()

    def next_page(self):
        total_pages = (len(self.rows) + self.items_per_page - 1) // self.items_per_page
        if self.page < total_pages - 1:
            self.page += 1
        else:
            self.page = 0
        self.populate_table()

    def select_all(self):
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        for i in range(start, min(end, len(self.rows))):
            ticker = self.rows[i][1]
            self.selected_tickers.add(ticker)
        self.populate_table()

    def deselect_all(self):
        self.selected_tickers.clear()
        self.populate_table()

    def on_table_click(self, event):
        region = self.table.identify('region', event.x, event.y)
        if region != 'cell':
            return
        col = self.table.identify_column(event.x)
        if col != '#1':  # Sadece Seç kolonu
            return
        row_id = self.table.identify_row(event.y)
        if not row_id or not row_id.startswith('row_'):
            return
        idx = int(row_id.split('_')[1])
        ticker = self.rows[idx][1]
        if ticker in self.selected_tickers:
            self.selected_tickers.remove(ticker)
        else:
            self.selected_tickers.add(ticker)
        self.populate_table()

    def sort_by_column(self, col):
        idx = self.COLUMNS.index(col)
        data_rows = [row for row in self.rows if row[1] != 'desc_long' and row[1] != 'desc_short']
        data_rows.sort(key=lambda x: (self._sort_key(x[idx]) is None, self._sort_key(x[idx])), reverse=self.sort_reverse)
        self.rows = data_rows
        self.populate_table()
        self.sort_reverse = not self.sort_reverse

    def _sort_key(self, val):
        try:
            if val is None or str(val).strip() in ("N/A", "nan", ""):
                return None
            return float(str(val).replace(",", ""))
        except Exception:
            return None

    # Emir gönderme fonksiyonları (placeholder, gerçek API ile entegre edilecek)
    def send_bid_buy_orders(self):
        self._send_orders('bid_buy')
    def send_front_buy_orders(self):
        self._send_orders('front_buy')
    def send_ask_buy_orders(self):
        self._send_orders('ask_buy')
    def send_ask_sell_orders(self):
        self._send_orders('ask_sell')
    def send_front_sell_orders(self):
        self._send_orders('front_sell')
    def send_bid_sell_orders(self):
        self._send_orders('bid_sell')
    def _send_orders(self, order_type):
        # Default lot değeri
        default_lot = 200  # lot_var olmadığı için sabit değer kullan
        
        # Sadece seçili ticker'lar için emir hazırla
        preview = []
        filtered_by_smi = []  # SMI rate nedeniyle filtrelenen hisseler
        adjusted_lots = []    # Lot ayarlaması yapılan hisseler
        
        for row in self.rows:
            ticker = row[1]
            if ticker not in self.selected_tickers:
                continue
                
            # Mevcut pozisyonu al
            current_position = self.get_current_position_size(ticker)
                
            price = None
            # Tablodan bid/ask almak yerine market_data_dict'ten al
            table_bid = self._safe_float(row[self.COLUMNS.index('Bid')])
            table_ask = self._safe_float(row[self.COLUMNS.index('Ask')])
            table_spread = self._safe_float(row[self.COLUMNS.index('Spread')])
            
            # Market data'dan gerçek fiyatları al
            poly_ticker = polygonize_ticker(ticker)
            if poly_ticker in self.market_data_dict:
                md = self.market_data_dict[poly_ticker]
                bid = self._safe_float(md.get('bid', 0))
                ask = self._safe_float(md.get('ask', 0))
                spread = ask - bid if bid and ask and bid > 0 and ask > 0 else table_spread
            else:
                # Market data yoksa tablo değerlerini kullan
                bid = table_bid
                ask = table_ask
                spread = table_spread
            
            benchmark_chg = row[self.COLUMNS.index('Benchmark change')] if 'Benchmark change' in self.COLUMNS else ''
            smi_rate = self.get_smi_rate(ticker)
            
            # Skor seçimi
            if order_type == 'bid_buy':
                ilgili_skor = row[self.COLUMNS.index('Bid buy Ucuzluk skoru')]
                price = bid
                if price is not None and spread is not None:
                    price = price + spread * 0.15
            elif order_type == 'front_buy':
                ilgili_skor = row[self.COLUMNS.index('Front buy ucuzluk skoru')]
                price = self._safe_float(row[self.COLUMNS.index('Last price')])
                if price is not None:
                    price = price + 0.01
                    
                    # ✅ FRONT BUY SPREAD KONTROLÜ
                    if hasattr(self, 'psf_algo') and self.psf_algo:
                        is_valid, message = self.psf_algo.validate_front_order_before_sending(ticker, 'front_buy', price)
                        if not is_valid:
                            print(f"[FRONT VALIDATION] ❌ {ticker} front buy spread kontrolü başarısız: {message}")
                            continue  # Bu hisseyi atla
                    elif hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1:
                        is_valid, message = self.parent.psf_algo1.validate_front_order_before_sending(ticker, 'front_buy', price)
                        if not is_valid:
                            print(f"[FRONT VALIDATION] ❌ {ticker} front buy spread kontrolü başarısız: {message}")
                            continue  # Bu hisseyi atla
                    elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2:
                        is_valid, message = self.parent.psf_algo2.validate_front_order_before_sending(ticker, 'front_buy', price)
                        if not is_valid:
                            print(f"[FRONT VALIDATION] ❌ {ticker} front buy spread kontrolü başarısız: {message}")
                            continue  # Bu hisseyi atla
            elif order_type == 'ask_buy':
                ilgili_skor = row[self.COLUMNS.index('Ask buy ucuzluk skoru')]
                price = ask
                if price is not None:
                    price = price + 0.01
            elif order_type == 'ask_sell':
                ilgili_skor = row[self.COLUMNS.index('Ask sell pahalilik skoru')]
                price = ask
                if price is not None and spread is not None:
                    price = price - spread * 0.15
            elif order_type == 'front_sell':
                ilgili_skor = row[self.COLUMNS.index('Front sell pahalilik skoru')]
                price = self._safe_float(row[self.COLUMNS.index('Last price')])
                if price is not None:
                    price = price - 0.01
                    
                    # ✅ FRONT SELL SPREAD KONTROLÜ
                    if hasattr(self, 'psf_algo') and self.psf_algo:
                        is_valid, message = self.psf_algo.validate_front_order_before_sending(ticker, 'front_sell', price)
                        if not is_valid:
                            print(f"[FRONT VALIDATION] ❌ {ticker} front sell spread kontrolü başarısız: {message}")
                            continue  # Bu hisseyi atla
                    elif hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1:
                        is_valid, message = self.parent.psf_algo1.validate_front_order_before_sending(ticker, 'front_sell', price)
                        if not is_valid:
                            print(f"[FRONT VALIDATION] ❌ {ticker} front sell spread kontrolü başarısız: {message}")
                            continue  # Bu hisseyi atla
                    elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2:
                        is_valid, message = self.parent.psf_algo2.validate_front_order_before_sending(ticker, 'front_sell', price)
                        if not is_valid:
                            print(f"[FRONT VALIDATION] ❌ {ticker} front sell spread kontrolü başarısız: {message}")
                            continue  # Bu hisseyi atla
            elif order_type == 'bid_sell':
                ilgili_skor = row[self.COLUMNS.index('Bid sell pahalilik skoru')]
                price = bid
                if price is not None:
                    price = price - 0.01
            else:
                ilgili_skor = ''
            
            # Lot hesaplama (toggle'a göre)
            lot = None
            toggle = self.size_toggle.get()
            if toggle in ['20', '50', '100']:
                try:
                    # Final_Shares kolonunu kontrol et
                    if 'Final_Shares' in self.COLUMNS:
                        final_shares_idx = self.COLUMNS.index('Final_Shares')
                        qty_raw = row[final_shares_idx]
                        print(f"[YÜZDE HESAP] {ticker}: Final_Shares raw değeri = '{qty_raw}' (tip: {type(qty_raw)})")
                        
                        # Değeri temizle ve float'a çevir
                        if qty_raw == '' or qty_raw is None or str(qty_raw).strip() == '':
                            # Final_Shares boşsa Quantity kolonunu dene
                            if 'Quantity' in self.COLUMNS:
                                qty_idx = self.COLUMNS.index('Quantity')
                                qty_raw = row[qty_idx]
                                print(f"[YÜZDE HESAP] {ticker}: Final_Shares boş, Quantity kullanılıyor = '{qty_raw}'")
                            else:
                                raise ValueError("Hem Final_Shares hem Quantity kolonu boş")
                        
                        qty = abs(float(str(qty_raw).replace(',', '').strip()))
                        pct = int(toggle)
                        lot = int(max(1, round(qty * pct / 100)))
                        
                        print(f"[YÜZDE HESAP] {ticker}: %{pct} hesaplaması → qty={qty}, hesaplanan_lot={lot}")
                    else:
                        print(f"[YÜZDE HESAP] HATA: Final_Shares kolonu bulunamadı! Mevcut kolonlar: {self.COLUMNS}")
                        raise ValueError("Final_Shares kolonu bulunamadı")
                        
                except (ValueError, IndexError, TypeError) as e:
                    print(f"[YÜZDE HESAP] HATA {ticker}: {e}")
                    # Hata durumunda varsayılan değere geri dön
                    lot = None
            
            # Eğer yüzdelik hesaplama başarısızsa veya toggle yoksa, manuel lot kullan
            if lot is None:
                lot = self.selected_lots.get(ticker, default_lot)
                if toggle:
                    print(f"[YÜZDE HESAP] {ticker}: Yüzde hesaplaması başarısız, varsayılan lot kullanılıyor: {lot}")
                else:
                    print(f"[LOT] {ticker}: Manuel lot kullanılıyor: {lot}")
            
            # Pozisyon kontrolü ve lot ayarlaması
            if order_type in ['ask_sell', 'front_sell', 'bid_sell']:
                # SELL emirleri için kontrol
                if current_position > 0:
                    # Long pozisyon var - pozisyon azaltma
                    if lot > current_position:
                        # Emir, mevcut pozisyondan fazla - otomatik ayarla
                        print(f"[POZISYON KONTROLÜ] {ticker}: {lot} lot sell emri, mevcut long pozisyon {current_position} → lot {current_position}'e ayarlandı")
                        adjusted_lots.append((ticker, lot, current_position, "Long pozisyon azaltma"))
                        lot = current_position
                elif current_position <= 0:
                    # Pozisyon yok veya short pozisyon var - short arttırma işlemi
                    # SMI kontrolü sadece bu durumda
                    smi_rate = self.get_smi_rate(ticker)
                    if smi_rate > 0.28:
                        print(f"[SMI FILTER] {ticker} short arttırma işlemi reddedildi - SMI rate: {smi_rate:.4f} > 0.28")
                        logger.info(f"SMI FILTER: {ticker} short arttırma reddedildi - SMI rate: {smi_rate:.4f}")
                        filtered_by_smi.append((ticker, smi_rate))
                        continue  # Bu hisseyi atla, diğer hisselere devam et
                    else:
                        print(f"[SMI FILTER] {ticker} short arttırma onaylandı - SMI rate: {smi_rate:.4f} <= 0.28")
            elif order_type in ['bid_buy', 'front_buy', 'ask_buy']:
                # BUY emirleri için kontrol
                if current_position < 0:
                    # Short pozisyon var - pozisyon azaltma
                    if lot > abs(current_position):
                        # Emir, mevcut pozisyondan fazla - otomatik ayarla
                        print(f"[POZISYON KONTROLÜ] {ticker}: {lot} lot buy emri, mevcut short pozisyon {current_position} → lot {abs(current_position)}'e ayarlandı")
                        adjusted_lots.append((ticker, lot, abs(current_position), "Short pozisyon azaltma"))
                        lot = abs(current_position)
                # Long arttırma işlemi - SMI kontrolü yok
                        
            if price is not None and lot is not None and lot > 0:
                preview.append((ticker, lot, price, order_type, bid, ask, spread, benchmark_chg, ilgili_skor, smi_rate))
        
        # SMI filtreleme bilgisi göster
        if filtered_by_smi:
            from tkinter import messagebox
            filtered_msg = "SMI rate > 0.28 nedeniyle filtrelenen hisseler (Short arttırma):\n"
            for ticker, smi in filtered_by_smi:
                filtered_msg += f"• {ticker}: SMI {smi:.4f}\n"
            messagebox.showinfo("SMI Filtresi", filtered_msg)
        
        # Lot ayarlaması bilgisi göster
        if adjusted_lots:
            from tkinter import messagebox
            adjusted_msg = "Mevcut pozisyona göre lot ayarlaması yapılan hisseler:\n"
            for ticker, original, adjusted, reason in adjusted_lots:
                adjusted_msg += f"• {ticker}: {original} → {adjusted} lot ({reason})\n"
            messagebox.showinfo("Lot Ayarlaması", adjusted_msg)
            
        # ✅ ŞİRKET LİMİTİ KONTROLÜ (YENİ!) - Emir onayı öncesi
        print(f"[MALTOPLA COMPANY FILTER] 🏢 Emir onayında şirket limiti kontrolü: {len(preview)} emir")
        
        # Preview listesini şirket kontrolü için uygun formata çevir
        preview_for_company_check = []
        for item in preview:
            ticker = item[0]
            score = item[8] if len(item) > 8 else 0  # ilgili_skor
            try:
                score = float(score) if score else 0
            except:
                score = 0
            preview_for_company_check.append((ticker, score))
        
        # Şirket limitlerini uygula
        if hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1:
            # PSFAlgo1 aktifse onun fonksiyonunu kullan
            filtered_tickers_with_scores = self.parent.psf_algo1.filter_by_company_limits(preview_for_company_check)
        elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2:
            # PSFAlgo2 aktifse onun fonksiyonunu kullan
            filtered_tickers_with_scores = self.parent.psf_algo2.filter_by_company_limits(preview_for_company_check)
        else:
            # Hiçbiri aktif değilse şirket kontrolü yapmadan devam et
            print(f"[MALTOPLA COMPANY FILTER] ⚠️ PSFAlgo aktif değil, şirket kontrolü atlanıyor")
            filtered_tickers_with_scores = preview_for_company_check
        
        # Filtrelenmiş ticker listesi
        filtered_tickers = [item[0] for item in filtered_tickers_with_scores]
        
        # Preview listesini filtrele
        original_preview_count = len(preview)
        preview = [item for item in preview if item[0] in filtered_tickers]
        
        print(f"[MALTOPLA COMPANY FILTER] 📊 Şirket limiti sonrası: {original_preview_count} → {len(preview)} emir")
        
        # Onay penceresi ve emir gönderme (mevcut _send_orders ile aynı yapıda)
        if not preview:
            from tkinter import messagebox
            messagebox.showinfo("Emir Gönder", "Şirket limiti kontrolü sonrası emir gönderilecek hisse bulunamadı.")
            return
            
        # Mevcut onay penceresi kontrolü
        if self.confirmation_window_open:
            from tkinter import messagebox
            messagebox.showwarning("Onay Penceresi", "Zaten bir onay penceresi açık. Önce mevcut pencereyi tamamlayın.")
            return
            
        self.confirmation_window_open = True
        
        # PSFAlgo onay bekleme durumunu ayarla
        if hasattr(self.parent, 'psf_algo') and self.parent.psf_algo and self.parent.psf_algo.is_active:
            self.parent.psf_algo.waiting_for_approval = True
            print("[PSFAlgo CHAIN] ⏸️ Onay bekleme durumu aktif (Lot butonu)")
        elif hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1 and self.parent.psf_algo1.is_active:
            self.parent.psf_algo1.waiting_for_approval = True
            print("[PSFAlgo1 CHAIN] ⏸️ Onay bekleme durumu aktif")
        elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2 and self.parent.psf_algo2.is_active:
            self.parent.psf_algo2.waiting_for_approval = True
            print("[PSFAlgo2 CHAIN] ⏸️ Onay bekleme durumu aktif")
        
        import tkinter as tk
        from tkinter import simpledialog
        confirm_win = tk.Toplevel(self)
        
        # PSFAlgo döngü adımı bilgisini al
        psf_step_info = ""
        
        # PSFAlgo1 kontrolü (yeni 8 adımlı sistem)
        if hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1 and self.parent.psf_algo1.is_active:
            chain_title = self.parent.psf_algo1.get_chain_state_title()
            if chain_title:
                psf_step_info = f" - {chain_title}"
        # PSFAlgo2 kontrolü (eski 6 adımlı sistem)
        elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2 and self.parent.psf_algo2.is_active:
            chain_title = self.parent.psf_algo2.get_chain_state_title()
            if chain_title:
                psf_step_info = f" - {chain_title}"
        # Eski PSFAlgo kontrolü (backward compatibility)
        elif hasattr(self.parent, 'psf_algo') and self.parent.psf_algo and self.parent.psf_algo.is_active:
            chain_title = self.parent.psf_algo.get_chain_state_title()
            if chain_title:
                psf_step_info = f" - {chain_title}"
        
        confirm_win.title(f"Emir Onayı (Lot){psf_step_info}")
        
        # Mesaj metni de döngü bilgisiyle güncelle
        message_text = "Aşağıdaki emirler gönderilecek. Onaylıyor musunuz?"
        if psf_step_info:
            message_text += f"\n{chain_title}"
            
        tk.Label(confirm_win, text=message_text, font=("Arial", 10, "bold")).pack(pady=5)
        
        # Scrollable frame oluştur
        canvas = tk.Canvas(confirm_win)
        scrollbar = tk.Scrollbar(confirm_win, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Headers
        headers = ["Ticker", "Lot", "Emir Fiyatı", "Yön", "Bid", "Ask", "Spread", "Benchmark %", "İlgili Skor", "SMI Rate"]
        for idx, h in enumerate(headers):
            tk.Label(scrollable_frame, text=h, width=12, anchor='w', font=("Arial", 9, "bold"), 
                    relief="ridge", borderwidth=1).grid(row=0, column=idx, sticky="ew", padx=1, pady=1)
        
        # Data rows
        for i, (ticker, lot, price, order_type, bid, ask, spread, benchmark_chg, ilgili_skor, smi_rate) in enumerate(preview):
            # Renk kodlaması: yeşil=buy, kırmızı=sell
            bg_color = "#E8F5E8" if order_type in ['bid_buy', 'front_buy', 'ask_buy'] else "#FFE8E8"
            
            # benchmark_chg'yi güvenli şekilde formatla
            benchmark_chg_f = self._safe_float(benchmark_chg)
            benchmark_display = f"{benchmark_chg_f:.2f}%" if benchmark_chg_f is not None else "N/A"
            
            tk.Label(scrollable_frame, text=str(ticker), width=12, anchor='w', bg=bg_color,
                    relief="ridge", borderwidth=1).grid(row=i+1, column=0, sticky="ew", padx=1, pady=1)
            tk.Label(scrollable_frame, text=str(lot), width=12, anchor='w', bg=bg_color,
                    relief="ridge", borderwidth=1).grid(row=i+1, column=1, sticky="ew", padx=1, pady=1)
            tk.Label(scrollable_frame, text=f"{price:.3f}", width=12, anchor='w', bg=bg_color, font=("Arial", 9, "bold"),
                    relief="ridge", borderwidth=1).grid(row=i+1, column=2, sticky="ew", padx=1, pady=1)
            tk.Label(scrollable_frame, text=order_type, width=12, anchor='w', bg=bg_color,
                    relief="ridge", borderwidth=1).grid(row=i+1, column=3, sticky="ew", padx=1, pady=1)
            tk.Label(scrollable_frame, text=f"{bid:.3f}" if bid is not None and bid > 0 else "N/A", width=12, anchor='w', bg=bg_color,
                    relief="ridge", borderwidth=1).grid(row=i+1, column=4, sticky="ew", padx=1, pady=1)
            tk.Label(scrollable_frame, text=f"{ask:.3f}" if ask is not None and ask > 0 else "N/A", width=12, anchor='w', bg=bg_color,
                    relief="ridge", borderwidth=1).grid(row=i+1, column=5, sticky="ew", padx=1, pady=1)
            tk.Label(scrollable_frame, text=f"{spread:.3f}" if spread is not None and spread > 0 else "N/A", width=12, anchor='w', bg=bg_color,
                    relief="ridge", borderwidth=1).grid(row=i+1, column=6, sticky="ew", padx=1, pady=1)
            tk.Label(scrollable_frame, text=benchmark_display, width=12, anchor='w', bg=bg_color,
                    relief="ridge", borderwidth=1).grid(row=i+1, column=7, sticky="ew", padx=1, pady=1)
            tk.Label(scrollable_frame, text=f"{ilgili_skor}" if ilgili_skor != '' else "N/A", width=12, anchor='w', bg=bg_color,
                    relief="ridge", borderwidth=1).grid(row=i+1, column=8, sticky="ew", padx=1, pady=1)
            tk.Label(scrollable_frame, text=f"{smi_rate:.4f}", width=12, anchor='w', bg=bg_color,
                    relief="ridge", borderwidth=1).grid(row=i+1, column=9, sticky="ew", padx=1, pady=1)
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True, padx=10, pady=5)
        scrollbar.pack(side="right", fill="y")
        
        def onayla():
            self.confirmation_window_open = False
            confirm_win.destroy()
            
            # PSFAlgo onay bekleme durumunu sıfırla
            if hasattr(self.parent, 'psf_algo') and self.parent.psf_algo and self.parent.psf_algo.is_active:
                self.parent.psf_algo.waiting_for_approval = False
                print("[PSFAlgo CHAIN] ✅ Onay alındı, onay bekleme durumu sıfırlandı")
            elif hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1 and self.parent.psf_algo1.is_active:
                self.parent.psf_algo1.waiting_for_approval = False
                print("[PSFAlgo1 CHAIN] ✅ Onay alındı, onay bekleme durumu sıfırlandı")
            elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2 and self.parent.psf_algo2.is_active:
                self.parent.psf_algo2.waiting_for_approval = False
                print("[PSFAlgo2 CHAIN] ✅ Onay alındı, onay bekleme durumu sıfırlandı")
            
            # Emirleri gönder - preview tuple'ından sadece ilk 4 elemanı al
            for ticker, lot, price, order_type, *_ in preview:
                self._send_hidden_order(ticker, price, lot, order_type)
            
            # PSFAlgo aktifse emir kontrolü yap ve chain'i devam ettir
            if hasattr(self.parent, 'psf_algo') and self.parent.psf_algo and self.parent.psf_algo.is_active:
                print("[PSFAlgo CHAIN] Emirler onaylandı, emir kontrolü yapılıyor...")
                # Emir kontrolünü arka planda çalıştır (UI'yi bloke etmemek için)
                import threading
                def run_order_control():
                    self.parent.psf_algo.advance_chain()
                threading.Thread(target=run_order_control).start()
            elif hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1 and self.parent.psf_algo1.is_active:
                print("[PSFAlgo1 CHAIN] Emirler onaylandı, sonraki adıma geçiliyor...")
                import threading
                def run_psfalgo1_advance():
                    # Aynı pencerede sonraki adım varsa continue_current_window_next_step kullan
                    if hasattr(self.parent.psf_algo1, 'continue_current_window_next_step') and \
                       self.parent.psf_algo1.chain_state in ['T_LOSERS_FB', 'T_GAINERS_FS', 'LONG_TP_FS', 'SHORT_TP_FB']:
                        self.parent.psf_algo1.continue_current_window_next_step()
                    else:
                        self.parent.psf_algo1.advance_chain()
                threading.Thread(target=run_psfalgo1_advance).start()
            elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2 and self.parent.psf_algo2.is_active:
                print("[PSFAlgo2 CHAIN] Emirler onaylandı, sonraki adıma geçiliyor...")
                import threading
                def run_psfalgo2_advance():
                    # PSFAlgo2'de LONG_TP_FRONT ve SHORT_TP_FRONT son adımlar, advance_chain çağır
                    self.parent.psf_algo2.advance_chain()
                threading.Thread(target=run_psfalgo2_advance).start()
        
        def iptal():
            self.confirmation_window_open = False
            confirm_win.destroy()
            
            # PSFAlgo onay bekleme durumunu sıfırla
            if hasattr(self.parent, 'psf_algo') and self.parent.psf_algo and self.parent.psf_algo.is_active:
                self.parent.psf_algo.waiting_for_approval = False
                print("[PSFAlgo CHAIN] ❌ İptal edildi (Lot butonu), onay bekleme durumu sıfırlandı")
            elif hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1 and self.parent.psf_algo1.is_active:
                self.parent.psf_algo1.waiting_for_approval = False
                print("[PSFAlgo1 CHAIN] ❌ İptal edildi, onay bekleme durumu sıfırlandı")
            elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2 and self.parent.psf_algo2.is_active:
                self.parent.psf_algo2.waiting_for_approval = False
                print("[PSFAlgo2 CHAIN] ❌ İptal edildi, onay bekleme durumu sıfırlandı")
            
            # PSFAlgo aktifse sonraki adıma geç
            if hasattr(self.parent, 'psf_algo') and self.parent.psf_algo and self.parent.psf_algo.is_active:
                print("[PSFAlgo CHAIN] Kullanıcı iptal etti (Lot butonu), sonraki adıma geçiliyor...")
                self.parent.after(0, self.parent.psf_algo.advance_chain)
            elif hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1 and self.parent.psf_algo1.is_active:
                print("[PSFAlgo1 CHAIN] Kullanıcı iptal etti, sonraki adıma geçiliyor...")
                # Aynı pencerede sonraki adım varsa continue_current_window_next_step kullan
                if hasattr(self.parent.psf_algo1, 'continue_current_window_next_step') and \
                   self.parent.psf_algo1.chain_state in ['T_LOSERS_FB', 'T_GAINERS_FS', 'LONG_TP_FS', 'SHORT_TP_FB']:
                    self.parent.after(0, self.parent.psf_algo1.continue_current_window_next_step)
                else:
                    self.parent.after(0, self.parent.psf_algo1.advance_chain)
            elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2 and self.parent.psf_algo2.is_active:
                print("[PSFAlgo2 CHAIN] Kullanıcı iptal etti, sonraki adıma geçiliyor...")
                # PSFAlgo2'de LONG_TP_FRONT ve SHORT_TP_FRONT son adımlar, advance_chain çağır
                self.parent.after(0, self.parent.psf_algo2.advance_chain)
        
        # Pencere kapanma olayını yakala (X butonu)
        def on_confirm_window_close():
            self.confirmation_window_open = False
            
            # PSFAlgo onay bekleme durumunu sıfırla
            if hasattr(self.parent, 'psf_algo') and self.parent.psf_algo and self.parent.psf_algo.is_active:
                self.parent.psf_algo.waiting_for_approval = False
                print("[PSFAlgo CHAIN] ❌ X butonu ile kapatıldı (Lot butonu), onay bekleme durumu sıfırlandı")
            elif hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1 and self.parent.psf_algo1.is_active:
                self.parent.psf_algo1.waiting_for_approval = False
                print("[PSFAlgo1 CHAIN] ❌ X butonu ile kapatıldı, onay bekleme durumu sıfırlandı")
            elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2 and self.parent.psf_algo2.is_active:
                self.parent.psf_algo2.waiting_for_approval = False
                print("[PSFAlgo2 CHAIN] ❌ X butonu ile kapatıldı, onay bekleme durumu sıfırlandı")
            
            # X butonu PSFAlgo'yu tamamen durdurur
            if hasattr(self.parent, 'psf_algo') and self.parent.psf_algo and self.parent.psf_algo.is_active:
                print("[PSFAlgo CHAIN] X butonu ile kapatıldı (Lot butonu), PSFAlgo durduruluyor...")
                self.parent.psf_algo.deactivate()
            elif hasattr(self.parent, 'psf_algo1') and self.parent.psf_algo1 and self.parent.psf_algo1.is_active:
                print("[PSFAlgo1 CHAIN] X butonu ile kapatıldı, PSFAlgo1 durduruluyor...")
                self.parent.psf_algo1.deactivate()
            elif hasattr(self.parent, 'psf_algo2') and self.parent.psf_algo2 and self.parent.psf_algo2.is_active:
                print("[PSFAlgo2 CHAIN] X butonu ile kapatıldı, PSFAlgo2 durduruluyor...")
                self.parent.psf_algo2.deactivate()
        
        confirm_win.protocol("WM_DELETE_WINDOW", on_confirm_window_close)
        
        btn_frame = tk.Frame(confirm_win)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Onayla", command=onayla, width=10, bg="#4CAF50", fg="white").pack(side='left', padx=10)
        tk.Button(btn_frame, text="İptal", command=iptal, width=10, bg="#F44336", fg="white").pack(side='left', padx=10)

    def _safe_float(self, x):
        try:
            return float(x)
        except:
            return None

    def _split_lot_to_chunks(self, total_lot, chunk_size=200):
        """Lot'u belirtilen boyutta parçalara böl"""
        total_lot = int(total_lot)
        chunks = []
        
        while total_lot > 0:
            if total_lot >= chunk_size:
                chunks.append(chunk_size)
                total_lot -= chunk_size
            else:
                chunks.append(total_lot)
                total_lot = 0
                
        return chunks

    def polygon_to_ibkr_ticker(self, ticker):
        # Polygon'dan gelen 'FpC' gibi ticker'ı IBKR'nin beklediği 'F PRC' formatına çevir
        # Bu örnek sadece FpC -> F PRC için, gerekirse daha genel bir dönüşüm eklenebilir
        if ticker.upper() == 'FPC':
            return 'F PRC'
        return ticker  # Diğerleri için olduğu gibi bırak
    def _send_hidden_order(self, ticker, price, lot, order_type):
        """IBKR hesabına gerçek emir gönderme - 200'lük lotlara bölerek"""
        try:
            if not self.ib or not self.ib.isConnected():
                logger.error("IBKR bağlantısı yok veya kapalı!")
                return

            # Mevcut pozisyonu kontrol et
            current_position = self.get_current_position_size(ticker)
            
            # Pozisyon kontrolü ve lot ayarlaması
            if order_type in ['ask_sell', 'front_sell', 'bid_sell']:
                # SELL emirleri için kontrol
                if current_position > 0:
                    # Long pozisyon var - pozisyon azaltma
                    if lot > current_position:
                        # Emir, mevcut pozisyondan fazla - otomatik ayarla
                        print(f"[POZISYON KONTROLÜ] {ticker}: {lot} lot sell emri, mevcut long pozisyon {current_position} → lot {current_position}'e ayarlandı")
                        lot = current_position
                elif current_position <= 0:
                    # Pozisyon yok veya short pozisyon var - short arttırma işlemi
                    # SMI kontrolü sadece bu durumda
                    smi_rate = self.get_smi_rate(ticker)
                    if smi_rate > 0.28:
                        print(f"[SMI FILTER] {ticker} short arttırma işlemi reddedildi - SMI rate: {smi_rate:.4f} > 0.28")
                        logger.info(f"SMI FILTER: {ticker} short arttırma reddedildi - SMI rate: {smi_rate:.4f}")
                        return  # Bu ticker için emir gönderme, fonksiyonu bitir
                    else:
                        print(f"[SMI FILTER] {ticker} short arttırma onaylandı - SMI rate: {smi_rate:.4f} <= 0.28")
            elif order_type in ['bid_buy', 'front_buy', 'ask_buy']:
                # BUY emirleri için kontrol
                if current_position < 0:
                    # Short pozisyon var - pozisyon azaltma
                    if lot > abs(current_position):
                        # Emir, mevcut pozisyondan fazla - otomatik ayarla
                        print(f"[POZISYON KONTROLÜ] {ticker}: {lot} lot buy emri, mevcut short pozisyon {current_position} → lot {abs(current_position)}'e ayarlandı")
                        lot = abs(current_position)
                # Long arttırma işlemi - SMI kontrolü yok

            # Lot sıfırsa emir gönderme
            if lot <= 0:
                print(f"[POZISYON KONTROLÜ] {ticker}: Lot sıfır veya negatif, emir gönderilmedi")
                return

            order_action = "BUY" if order_type in ['bid_buy', 'front_buy', 'ask_buy'] else "SELL"
            contract = Stock(ticker, 'SMART', 'USD')
            price = round(price, 2)
            
            # Lot'u 200'lük parçalara böl
            lot_chunks = self._split_lot_to_chunks(lot, 200)
            
            print(f"[LOT SPLIT] {ticker} toplam {lot} lot → {len(lot_chunks)} parçaya bölündü: {lot_chunks}")
            
            # Her parça için emir gönder
            successful_orders = 0
            for i, chunk_size in enumerate(lot_chunks):
                try:
                    order = LimitOrder(order_action, chunk_size, price)
                    order.tif = "DAY"
                    order.hidden = True

                    trade = self.ib.placeOrder(contract, order)
                    print(f"[EMIR {i+1}/{len(lot_chunks)}] {ticker} {order_action} {chunk_size} @ {price} gönderildi")

                    # Emir durumunu bekle (kısa süre)
                    max_wait = 5  # saniye
                    waited = 0
                    while trade.orderStatus.status in ("PendingSubmit", "PreSubmitted") and waited < max_wait:
                        time.sleep(0.5)
                        waited += 0.5
                        self.ib.sleep(0.1)

                    if trade.orderStatus.status == "Submitted":
                        print(f"[EMIR {i+1}/{len(lot_chunks)}] ✅ {ticker} {order_action} {chunk_size} @ {price} başarılı")
                        successful_orders += 1
                    else:
                        print(f"[EMIR {i+1}/{len(lot_chunks)}] ⚠️ {ticker} durum: {trade.orderStatus.status}")
                        successful_orders += 1  # Pending durumları da sayalım
                        
                    # Emirler arası kısa bekleme (rate limiting için)
                    if i < len(lot_chunks) - 1:
                        time.sleep(0.2)
                        
                except Exception as e:
                    print(f"[EMIR {i+1}/{len(lot_chunks)}] ❌ {ticker} parça emir hatası: {e}")
                    logger.error(f"Parça emir hatası {ticker} chunk {chunk_size}: {e}")
            
            print(f"[LOT SPLIT SONUÇ] {ticker}: {successful_orders}/{len(lot_chunks)} emir başarılı")
            
            if successful_orders > 0:
                print(f"[GENEL] ✅ {ticker} için {successful_orders} parça emir gönderildi")
            else:
                print(f"[GENEL] ❌ {ticker} için hiçbir emir gönderilemedi")

        except Exception as e:
            logger.error(f"Emir gönderme hatası: {e}")
            print(f"[GENEL] ❌ {ticker} genel emir hatası: {e}")

    def get_current_position_size(self, ticker):
        """Mevcut pozisyon büyüklüğünü döndür"""
        try:
            if hasattr(self.parent, 'market_data') and hasattr(self.parent.market_data, 'get_positions'):
                positions = self.parent.market_data.get_positions()
                for pos in positions:
                    if pos['symbol'] == ticker:
                        return pos['quantity']
            return 0
        except Exception:
            return 0

    def get_smi_rate(self, ticker):
        """Ticker için SMI rate değerini döndür"""
        try:
            # Mevcut satırlardan SMI rate'i bul
            for row in self.rows:
                if row[1] == ticker:  # ticker kolonu
                    smi_idx = self.COLUMNS.index('SMI rate')
                    smi_val = row[smi_idx]
                    return float(smi_val) if smi_val != 'N/A' else 0.0
            return 0.0
        except Exception:
            return 0.0

    def _send_orders_with_lot_only(self):
        # Default lot değeri
        default_lot = 200  # lot_var olmadığı için sabit değer kullan
        
        # Sadece seçili ticker'lar için emir hazırla
        preview = []
        for row in self.rows:
            ticker = row[1]
            if ticker not in self.selected_tickers:
                continue
            price = self._safe_float(row[self.COLUMNS.index('Bid')])
            spread = self._safe_float(row[self.COLUMNS.index('Spread')])
            if price is not None and spread is not None:
                price = price + spread * 0.15
            lot = default_lot
            if price is not None and lot is not None:
                preview.append((ticker, lot, price, 'bid_buy'))
                
        # Onay penceresi
        if not preview:
            from tkinter import messagebox
            messagebox.showinfo("Emir Gönder", "Seçili ve geçerli emir yok.")
            return
            
        import tkinter as tk
        confirm_win = tk.Toplevel(self)
        confirm_win.title("Emir Onayı (Lot)")
        
        tk.Label(confirm_win, text="Aşağıdaki emirler gönderilecek. Onaylıyor musunuz?", font=("Arial", 10, "bold")).pack(pady=5)
        
        frame = tk.Frame(confirm_win)
        frame.pack(padx=10, pady=5)
        
        tk.Label(frame, text="Ticker", width=10, anchor='w').grid(row=0, column=0)
        tk.Label(frame, text="Lot", width=8, anchor='w').grid(row=0, column=1)
        tk.Label(frame, text="Fiyat", width=12, anchor='w').grid(row=0, column=2)
        tk.Label(frame, text="Yön", width=12, anchor='w').grid(row=0, column=3)
        
        for i, (ticker, lot, price, order_type) in enumerate(preview):
            tk.Label(frame, text=str(ticker), width=10, anchor='w').grid(row=i+1, column=0)
            tk.Label(frame, text=str(lot), width=8, anchor='w').grid(row=i+1, column=1)
            tk.Label(frame, text=f"{price:.2f}", width=12, anchor='w').grid(row=i+1, column=2)
            tk.Label(frame, text=order_type, width=12, anchor='w').grid(row=i+1, column=3)
        
        def onayla():
            confirm_win.destroy()
            # Basit emir gönderme - PSFAlgo kontrolü yok
            for ticker, lot, price, order_type in preview:
                self._send_hidden_order(ticker, price, lot, order_type)
                
        def iptal():
            confirm_win.destroy()
        
        btn_frame = tk.Frame(confirm_win)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Onayla", command=onayla, width=10, bg="#4CAF50", fg="white").pack(side='left', padx=10)
        tk.Button(btn_frame, text="İptal", command=iptal, width=10, bg="#F44336", fg="white").pack(side='left', padx=10)

    def on_close(self):
        # ✅ Pencere kapatıldığında aktif PSFAlgo'yu temizle
        if hasattr(self, 'psf_algo') and self.psf_algo is not None:
            self.psf_algo.current_window = None
            print(f"[MALTOPLA] {self.psf_algo.__class__.__name__} current_window temizlendi")
        elif hasattr(self.parent, 'psf_algo') and self.parent.psf_algo is not None:
            # Backward compatibility
            self.parent.psf_algo.current_window = None
            print("[MALTOPLA] Eski PSFAlgo current_window temizlendi")
        
        self.destroy()

def get_contract_details(app, symbol):
    pass  # No longer needed with ib_insync

def send_ibkr_order(symbol, lot, price, action="BUY", hidden=True, client_id=1300, port=4001):
    pass  # No longer needed with ib_insync 
