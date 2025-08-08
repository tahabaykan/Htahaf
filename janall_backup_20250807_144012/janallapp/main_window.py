"""
Ana pencere modülü.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import numpy as np
import time
import os
from .etf_panel import ETFPanel
from .order_management import OrderManager, OrderBookWindow
from .bdata_storage import BDataStorage

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JanAll")
        
        # Hammer Pro client
        from .hammer_client import HammerClient
        self.hammer = HammerClient(
            host='127.0.0.1',  # localhost
            port=16400,        # varsayılan port
            password='Nl201090.'  # API şifresi
        )
        
        # Order Manager
        self.order_manager = OrderManager(self)
        
        # BDATA Storage
        self.bdata_storage = BDataStorage()
        
        # ETF verilerini takip etmek için
        self.etf_data = {}
        
        # Benchmark hesaplama için gerekli veriler
        self.pff_last = None
        self.tlt_last = None
        self.spy_last = None
        self.ief_last = None
        self.iei_last = None
        
        # Benchmark formülleri (kupon oranlarına göre) - %20 AZALTILMIŞ KATSAYILAR
        self.benchmark_formulas = {
            'DEFAULT': {'PFF': 1.04, 'TLT': -0.08, 'IEF': 0.0, 'IEI': 0.0},   # CGRUP yoksa: PFF*1.04-TLT*0.08 (%20 azaltılmış)
            'C400': {'PFF': 0.36, 'TLT': 0.36, 'IEF': 0.08, 'IEI': 0.0},      # %4 (%20 azaltılmış)
            'C425': {'PFF': 0.368, 'TLT': 0.34, 'IEF': 0.092, 'IEI': 0.0},    # %4.25 (%20 azaltılmış)
            'C450': {'PFF': 0.376, 'TLT': 0.32, 'IEF': 0.104, 'IEI': 0.0},    # %4.5 (%20 azaltılmış)
            'C475': {'PFF': 0.384, 'TLT': 0.3, 'IEF': 0.116, 'IEI': 0.0},     # %4.75 (%20 azaltılmış)
            'C500': {'PFF': 0.392, 'TLT': 0.28, 'IEF': 0.128, 'IEI': 0.0},    # %5 (%20 azaltılmış)
            'C525': {'PFF': 0.4, 'TLT': 0.24, 'IEF': 0.14, 'IEI': 0.02},      # %5.25 (%20 azaltılmış)
            'C550': {'PFF': 0.408, 'TLT': 0.2, 'IEF': 0.152, 'IEI': 0.04},    # %5.5 (%20 azaltılmış)
            'C575': {'PFF': 0.416, 'TLT': 0.16, 'IEF': 0.164, 'IEI': 0.06},   # %5.75 (%20 azaltılmış)
            'C600': {'PFF': 0.432, 'TLT': 0.12, 'IEF': 0.168, 'IEI': 0.08},   # %6 (%20 azaltılmış)
            'C625': {'PFF': 0.448, 'TLT': 0.08, 'IEF': 0.172, 'IEI': 0.1},    # %6.25 (%20 azaltılmış)
            'C650': {'PFF': 0.464, 'TLT': 0.04, 'IEF': 0.156, 'IEI': 0.14},   # %6.5 (%20 azaltılmış)
            'C675': {'PFF': 0.48, 'TLT': 0.0, 'IEF': 0.14, 'IEI': 0.18},      # %6.75 (%20 azaltılmış)
            'C700': {'PFF': 0.512, 'TLT': 0.0, 'IEF': 0.12, 'IEI': 0.168},    # %7 (%20 azaltılmış)
            'C725': {'PFF': 0.544, 'TLT': 0.0, 'IEF': 0.1, 'IEI': 0.156},     # %7.25 (%20 azaltılmış)
            'C750': {'PFF': 0.576, 'TLT': 0.0, 'IEF': 0.0, 'IEI': 0.224},     # %7.5 (%20 azaltılmış)
            'C775': {'PFF': 0.608, 'TLT': 0.0, 'IEF': 0.0, 'IEI': 0.192},     # %7.75 (%20 azaltılmış)
            'C800': {'PFF': 0.64, 'TLT': 0.0, 'IEF': 0.0, 'IEI': 0.16}        # %8 (%20 azaltılmış)
        }
        
        # Önceki ETF fiyatları (değişim hesaplama için)
        self.prev_etf_prices = {}
        
        # Stabil benchmark hesaplama için
        self.stable_etf_changes = {}  # Son güncellenmiş sabit değerler
        self.last_benchmark_update = 0  # Son güncelleme zamanı
        self.benchmark_update_interval = 5.0  # 5 saniyede bir güncelle
        
        # Cache sistemi - hesaplama boşluklarını önle
        self.last_valid_scores = {}  # Her ticker için son geçerli skorlar
        
        # Başlangıçta boş DataFrame
        self.df = pd.DataFrame()
        self.tickers = []
        
        # Sayfalama ayarları
        self.items_per_page = 15
        self.current_page = 0
        self.total_pages = (len(self.tickers) + self.items_per_page - 1) // self.items_per_page
        
        # Sıralama ayarları
        self.sort_column = None
        self.sort_ascending = True
        
        self.setup_ui()
        
    def setup_ui(self):
        # Üst panel - Bağlantı butonları
        top_frame = ttk.Frame(self)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        self.btn_connect = ttk.Button(top_frame, text="Hammer Pro'ya Bağlan", command=self.connect_hammer)
        self.btn_connect.pack(side='left', padx=2)
        
        self.btn_live = ttk.Button(top_frame, text="Live Data Başlat", command=self.toggle_live_data)
        self.btn_live.pack(side='left', padx=2)
        
        # BDATA butonları
        bdata_frame = ttk.Frame(top_frame)
        bdata_frame.pack(side='right', padx=2)
        
        self.btn_bdata_export = ttk.Button(bdata_frame, text="BDATA Export", command=self.export_bdata, width=12)
        self.btn_bdata_export.pack(side='left', padx=1)
        
        self.btn_befday_export = ttk.Button(bdata_frame, text="BEFDAY Export", command=self.export_befday, width=12)
        self.btn_befday_export.pack(side='left', padx=1)
        
        self.btn_bdata_clear = ttk.Button(bdata_frame, text="BDATA Clear", command=self.clear_bdata, width=12)
        self.btn_bdata_clear.pack(side='left', padx=1)
        
        # Order Management Butonları
        order_frame = ttk.Frame(self)
        order_frame.pack(fill='x', padx=5, pady=2)
        
        # Order butonları
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
        
        self.btn_bid_sell = ttk.Button(order_frame, text="Bid Sell", 
                                      command=lambda: self.order_manager.place_order_for_selected('bid_sell'), width=10)
        self.btn_bid_sell.pack(side='left', padx=1)
        
        # Lot seçim frame
        lot_frame = ttk.Frame(self)
        lot_frame.pack(fill='x', padx=5, pady=2)
        
        # Manuel lot girişi
        ttk.Label(lot_frame, text="Lot:").pack(side='left', padx=2)
        self.lot_entry = ttk.Entry(lot_frame, width=8)
        self.lot_entry.pack(side='left', padx=2)
        self.lot_entry.insert(0, "200")  # Default 200 lot
        
        # Lot butonları
        self.btn_lot_25 = ttk.Button(lot_frame, text="%25", 
                                    command=lambda: self.order_manager.set_lot_percentage(25), width=6)
        self.btn_lot_25.pack(side='left', padx=1)
        
        self.btn_lot_50 = ttk.Button(lot_frame, text="%50", 
                                    command=lambda: self.order_manager.set_lot_percentage(50), width=6)
        self.btn_lot_50.pack(side='left', padx=1)
        
        self.btn_lot_100 = ttk.Button(lot_frame, text="%100", 
                                     command=lambda: self.order_manager.set_lot_percentage(100), width=6)
        self.btn_lot_100.pack(side='left', padx=1)
        
        self.btn_lot_avg_adv = ttk.Button(lot_frame, text="Avg Adv", 
                                         command=self.order_manager.set_lot_avg_adv, width=8)
        self.btn_lot_avg_adv.pack(side='left', padx=1)
        
        # Seçim butonları
        selection_frame = ttk.Frame(self)
        selection_frame.pack(fill='x', padx=5, pady=2)
        
        self.btn_select_all = ttk.Button(selection_frame, text="Tümünü Seç", 
                                       command=self.order_manager.select_all_tickers, width=12)
        self.btn_select_all.pack(side='left', padx=1)
        
        self.btn_deselect_all = ttk.Button(selection_frame, text="Tümünü Kaldır", 
                                         command=self.order_manager.deselect_all_tickers, width=12)
        self.btn_deselect_all.pack(side='left', padx=1)
        
        # Tablo - CSV'den gelen tüm kolonları kullan
        # Başlangıçta boş, CSV yüklendiğinde güncellenecek
        self.columns = ['Seç']  # Seç kolonu her zaman ilk
        
        # Style ayarla - küçük font
        style = ttk.Style()
        style.configure("Treeview", font=('Arial', 6))
        style.configure("Treeview.Heading", font=('Arial', 6, 'bold'))
        
        self.table = ttk.Treeview(self, columns=self.columns, show='headings', height=15)
        
        # Çift tıklama olayını bağla
        self.table.bind('<Double-1>', self.on_double_click)
        
        # Checkbox tıklama olayını bağla - sadece Seç kolonu için
        self.table.bind('<ButtonRelease-1>', self.on_table_click)
        
        # Kolon başlıkları ve genişlikleri  
        score_columns = [
            'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
            'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru',
            'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor',
            'Spread'
        ]
        benchmark_columns = ['Benchmark_Type', 'Benchmark_Chg']
        
        for col in self.columns:
            # Sıralama fonksiyonunu bağla
            self.table.heading(col, 
                text=col,
                command=lambda c=col: self.sort_by_column(c))
                
            if col in ['PREF IBKR']:
                self.table.column(col, width=35, anchor='w')  # Sol hizalı - çok dar
            elif col in ['CMON', 'CGRUP']:
                self.table.column(col, width=15, anchor='center')  # En dar
            elif col in ['SMI', 'SHORT_FINAL']:
                self.table.column(col, width=20, anchor='center')  # Dar
            elif col in ['FINAL_THG', 'AVG_ADV']:
                self.table.column(col, width=25, anchor='center')  # Orta
            elif col in score_columns:
                self.table.column(col, width=30, anchor='center')  # Skor kolonları - çok dar
            elif col in benchmark_columns:
                self.table.column(col, width=20, anchor='center') # Benchmark kolonları - orta
            else:
                self.table.column(col, width=20, anchor='center')  # Normal - çok dar
                
        self.table.pack(fill='both', expand=True, padx=5, pady=5)
        
        # CSV dosya butonları
        files_frame = ttk.Frame(self)
        files_frame.pack(fill='x', padx=5, pady=5)
        
        # Ana veri butonu
        main_frame = ttk.Frame(files_frame)
        main_frame.pack(fill='x', pady=2)
        
        btn_main = ttk.Button(main_frame, text="JANALLDATA", 
                            command=lambda: self.show_file_data('janalldata.csv', is_main=True))
        btn_main.pack(side='left', padx=2)
        
        # Ayırıcı çizgi
        separator = ttk.Separator(files_frame, orient='horizontal')
        separator.pack(fill='x', pady=5)
        
        # CSV dosya isimleri
        csv_files = [
            'ssfinekheldcilizyeniyedi.csv',
            'ssfinekheldcommonsuz.csv',
            'ssfinekhelddeznff.csv',
            'ssfinekheldff.csv',
            'ssfinekheldflr.csv',
            'ssfinekheldgarabetaltiyedi.csv',
            'ssfinekheldkuponlu.csv',
            'ssfinekheldkuponlukreciliz.csv',
            'ssfinekheldkuponlukreorta.csv',
            'ssfinekheldnff.csv',
            'ssfinekheldotelremorta.csv',
            'ssfinekheldsolidbig.csv',
            'ssfinekheldtitrekhc.csv',
            'ssfinekhighmatur.csv',
            'ssfineknotbesmaturlu.csv',
            'ssfineknotcefilliquid.csv',
            'ssfineknottitrekhc.csv',
            'ssfinekrumoreddanger.csv',
            'ssfineksalakilliquid.csv',
            'ssfinekshitremhc.csv'
        ]
        
        # Her satırda 10 buton olacak şekilde düzenle
        buttons_per_row = 10
        current_frame = ttk.Frame(files_frame)
        current_frame.pack(fill='x', pady=2)
        
        for i, file in enumerate(csv_files):
            # Her 10 butonda bir yeni satır başlat
            if i > 0 and i % buttons_per_row == 0:
                current_frame = ttk.Frame(files_frame)
                current_frame.pack(fill='x', pady=2)
            
            # Dosya adını kısalt
            short_name = file.replace('ssfinek', '').replace('.csv', '')
            btn = ttk.Button(current_frame, text=short_name, command=lambda f=file: self.show_file_data(f))
            btn.pack(side='left', padx=2)
        
        # ETF Paneli
        self.etf_panel = ETFPanel(self, self.hammer)
        self.etf_panel.pack(fill='x', padx=5, pady=5)
        
        # Ayırıcı çizgi
        separator = ttk.Separator(self, orient='horizontal')
        separator.pack(fill='x', pady=5)
        
        # Sayfalama kontrolleri
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill='x', padx=5, pady=5)
        
        self.btn_prev = ttk.Button(nav_frame, text="<", command=self.prev_page)
        self.btn_prev.pack(side='left', padx=2)
        
        self.lbl_page = ttk.Label(nav_frame, text=f"Sayfa {self.current_page + 1} / {self.total_pages}")
        self.lbl_page.pack(side='left', padx=10)
        
        self.btn_next = ttk.Button(nav_frame, text=">", command=self.next_page)
        self.btn_next.pack(side='left', padx=2)
        
        # İlk sayfayı göster
        self.update_table()
        
    def export_bdata(self):
        """BDATA ve BEFDAY CSV'lerini oluştur"""
        try:
            self.bdata_storage.export_to_csv()
            messagebox.showinfo("Başarılı", "BDATA ve BEFDAY CSV'leri oluşturuldu!")
        except Exception as e:
            messagebox.showerror("Hata", f"BDATA export hatası: {e}")
    
    def export_befday(self):
        """Sadece BEFDAY CSV'sini oluştur"""
        try:
            summary = self.bdata_storage.get_position_summary_with_snapshot()
            self.bdata_storage.create_befday_csv(summary)
            messagebox.showinfo("Başarılı", "BEFDAY CSV'si oluşturuldu!")
        except Exception as e:
            messagebox.showerror("Hata", f"BEFDAY export hatası: {e}")
    
    def clear_bdata(self):
        """BDATA verilerini temizle"""
        if messagebox.askyesno("Onay", "Tüm BDATA verilerini temizlemek istediğinizden emin misiniz?"):
            try:
                self.bdata_storage.clear_all_data()
                messagebox.showinfo("Başarılı", "BDATA verileri temizlendi!")
            except Exception as e:
                messagebox.showerror("Hata", f"BDATA temizleme hatası: {e}")
    
    def add_manual_fill(self, ticker, direction, price, size):
        """Manuel fill ekle"""
        try:
            self.bdata_storage.add_manual_fill(ticker, direction, price, size)
            print(f"[MANUAL FILL] {ticker} {direction} {size}@{price} eklendi")
        except Exception as e:
            print(f"[MANUAL FILL] Hata: {e}")
    
    def update_etf_data_for_benchmark(self):
        """STABİL ETF benchmark hesaplama - 5 saniyede bir güncelle"""
        try:
            import time
            current_time = time.time()
            
            # 5 saniyede bir güncelle (sürekli değil!)
            if current_time - self.last_benchmark_update < self.benchmark_update_interval:
                return  # Henüz zamanı gelmedi
            
            # Benchmark ETF'ler
            benchmark_etfs = ['SPY', 'TLT', 'IEF', 'IEI', 'PFF', 'KRE', 'IWM']
            
            # ETF Panel'deki cache'lenmiş verileri kullan (daha stabil)
            if hasattr(self, 'etf_panel') and self.etf_panel:
                for etf in benchmark_etfs:
                    if etf in self.etf_panel.etf_data:
                        etf_data = self.etf_panel.etf_data[etf]
                        last_price = etf_data.get('last', 0)
                        prev_close = etf_data.get('prev_close', 0)
                        
                        if last_price > 0 and prev_close > 0:
                            # 2 decimal'e yuvarla (stabil hesaplama için)
                            change_dollars = round(last_price - prev_close, 4)
                            self.stable_etf_changes[etf] = change_dollars
                        elif etf not in self.stable_etf_changes:
                            # İlk defa eksikse 0 yap
                            self.stable_etf_changes[etf] = 0
                    elif etf not in self.stable_etf_changes:
                        # Cache'de yoksa market data'dan al
                        market_data = self.hammer.get_market_data(etf)
                        if market_data:
                            last_price = market_data.get('last', 0)
                            prev_close = market_data.get('prevClose', 0)
                            if last_price > 0 and prev_close > 0:
                                change_dollars = round(last_price - prev_close, 4)
                                self.stable_etf_changes[etf] = change_dollars
                            else:
                                self.stable_etf_changes[etf] = 0
                        else:
                            self.stable_etf_changes[etf] = 0
            
            # Son güncelleme zamanını kaydet
            self.last_benchmark_update = current_time
            
            # self.etf_changes'i stable değerlerle güncelle
            self.etf_changes = self.stable_etf_changes.copy()
                
        except Exception as e:
            print(f"[BENCHMARK] ETF veri güncelleme hatası: {e}")
    
    def get_benchmark_type_for_ticker(self, ticker):
        """Ticker için benchmark tipini belirle (CGRUP'a göre)"""
        try:
            # DataFrame'den ticker'ın CGRUP bilgisini al
            ticker_row = self.df[self.df['PREF IBKR'] == ticker]
            if not ticker_row.empty:
                cgrup = ticker_row['CGRUP'].iloc[0]
                if pd.isna(cgrup) or cgrup == 'N/A' or cgrup == '':
                    return 'DEFAULT'  # CGRUP yoksa varsayılan formül
                
                # CGRUP'u benchmark tipine çevir
                cgrup_str = str(cgrup).strip().lower()
                benchmark_key = cgrup_str.upper()
                if benchmark_key in self.benchmark_formulas:
                    return benchmark_key
                else:
                    return 'DEFAULT'  # Bilinmeyen CGRUP için varsayılan
            else:
                return 'DEFAULT'  # Veri yoksa varsayılan
                
        except Exception as e:
            print(f"[BENCHMARK] {ticker} benchmark tipi belirleme hatası: {e}")
            return 'DEFAULT'  # Hata durumunda varsayılan
    
    def get_benchmark_change_for_ticker(self, ticker):
        """STABİL Ticker benchmark değişimini hesapla - 2 decimal yuvarlamalı"""
        try:
            # Önce stable ETF verilerini güncelle (5s interval ile)
            self.update_etf_data_for_benchmark()
            
            if not hasattr(self, 'etf_changes') or not self.etf_changes:
                return 0.0
            
            # Ticker'ın benchmark tipini al
            benchmark_type = self.get_benchmark_type_for_ticker(ticker)
            formula = self.benchmark_formulas.get(benchmark_type, self.benchmark_formulas['DEFAULT'])
            
            # STABİL benchmark değişimini hesapla (2 decimal yuvarlama)
            benchmark_change = 0.0
            for etf, coefficient in formula.items():
                if etf in self.etf_changes and coefficient != 0:
                    etf_change = round(self.etf_changes[etf], 4)  # ETF change'i yuvarla
                    coefficient_rounded = round(coefficient, 2)    # Katsayıyı yuvarla
                    contribution = etf_change * coefficient_rounded
                    benchmark_change += contribution
            
            # 4 decimal'e yuvarla (stabil sonuç için)
            return round(benchmark_change, 4)
            
        except Exception as e:
            print(f"[BENCHMARK] {ticker} benchmark değişim hesaplama hatası: {e}")
            return 0.0
    
    def connect_hammer(self):
        """Hammer Pro'ya bağlan/bağlantıyı kes"""
        if not self.hammer.connected:
            print("\n[HAMMER] 🔌 Hammer Pro'ya bağlanılıyor...")
            print(f"[HAMMER] 📍 Host: {self.hammer.host}")
            print(f"[HAMMER] 🔢 Port: {self.hammer.port}")
            
            if self.hammer.connect():
                self.btn_connect.config(text="Bağlantıyı Kes")
                print("[HAMMER] ✅ Bağlantı başarılı!")
            else:
                print("[HAMMER] ❌ Bağlantı başarısız!")
                print("[HAMMER] 💡 Kontrol edilecekler:")
                print("   1. Hammer Pro çalışıyor mu?")
                print("   2. Port numarası doğru mu?")
                print("   3. API şifresi doğru mu?")
        else:
            print("\n[HAMMER] 🔌 Bağlantı kesiliyor...")
            self.hammer.disconnect()
            self.btn_connect.config(text="Hammer Pro'ya Bağlan")
            print("[HAMMER] ✅ Bağlantı kesildi.")
            
    def toggle_live_data(self):
        """Live data akışını başlat/durdur"""
        if not hasattr(self, 'live_data_running'):
            self.live_data_running = False
            
        if not self.live_data_running:
            # Önce janalldata.csv'yi yükle ve tüm sembollere subscribe ol
            self.show_file_data('janalldata.csv', is_main=True)
            
            # ETF'ler için streaming subscribe
            print("\n[ETF] 🔄 ETF'ler için streaming başlatılıyor...")
            self.etf_panel.subscribe_etfs()  # Sadece streaming subscribe
            
            self.live_data_running = True
            self.btn_live.config(text="Live Data Durdur")
            
            # ETF verilerini güncelleme döngüsünü başlat
            self.update_etf_data()
            
            # Ana tabloyu güncelleme döngüsünü başlat
            self.update_live_data()
        else:
            self.live_data_running = False
            self.btn_live.config(text="Live Data Başlat")
            
    def update_scores_with_market_data(self):
        """Market data ile skorları güncelle"""
        try:
            # ETF verileri otomatik güncelleniyor (5s interval)
            
            # Sadece görünür ticker'lar için işle (performans için)
            visible_tickers = self.get_visible_tickers()
            
            # SNAPSHOT İSTEKLERİ KALDIRILDI - Sadece L1 streaming kullanıyoruz!
            
            for idx, row in self.df.iterrows():
                ticker = row['PREF IBKR']
                
                # Sadece görünür ticker'lar için skorları hesapla
                if ticker not in visible_tickers:
                    continue
                    
                market_data = self.hammer.get_market_data(ticker)
                
                # Market data'dan değerleri al
                bid = market_data.get('bid', 0)
                ask = market_data.get('ask', 0)
                last_price = market_data.get('last', 0)
                prev_close = market_data.get('prevClose', 0)
                
                # Debug: Market data durumunu kontrol et (snapshot kaldırıldı)
                if prev_close == 0:
                    print(f"[SKOR] {ticker} için prevClose=0 (L1 streaming'den gelecek)")
                
                # Benchmark değişimini hesapla
                benchmark_chg = self.get_benchmark_change_for_ticker(ticker)
                benchmark_type = self.get_benchmark_type_for_ticker(ticker)
                
                # Skorları hesapla
                scores = self.calculate_scores(ticker, row, bid, ask, last_price, prev_close, benchmark_chg)
                
                # DataFrame'i güncelle
                for col, value in scores.items():
                    self.df.at[idx, col] = value
                
                # Benchmark değerlerini güncelle
                self.df.at[idx, 'Benchmark_Type'] = benchmark_type
                self.df.at[idx, 'Benchmark_Chg'] = benchmark_chg
                
                # Debug: Skor bilgilerini göster (sadece birkaç tane)
                if idx < 3:  # İlk 3 ticker için debug
                    print(f"[SKOR] {ticker}: bid={bid}, ask={ask}, last={last_price}, prevClose={prev_close}")
                    print(f"[SKOR] {ticker}: benchmark={benchmark_type}, chg={benchmark_chg:.2f}")
                    
        except Exception as e:
            print(f"[HATA] Skor güncelleme hatası: {e}")
    
    def calculate_scores(self, ticker, row, bid, ask, last_price, prev_close, benchmark_chg=0):
        """Ntahaf formüllerine göre skorları hesapla"""
        try:
            # Spread hesapla
            spread = float(ask) - float(bid) if ask != 'N/A' and bid != 'N/A' and ask > 0 and bid > 0 else 0
            
            # Passive fiyatlar hesapla (Ntahaf formülleri)
            pf_bid_buy = float(bid) + (spread * 0.15) if bid > 0 else 0
            pf_front_buy = float(last_price) + 0.01 if last_price > 0 else 0
            pf_ask_buy = float(ask) + 0.01 if ask > 0 else 0
            pf_ask_sell = float(ask) - (spread * 0.15) if ask > 0 else 0
            pf_front_sell = float(last_price) - 0.01 if last_price > 0 else 0
            pf_bid_sell = float(bid) - 0.01 if bid > 0 else 0
            
            # Değişimler hesapla (Ntahaf formülleri)
            pf_bid_buy_chg = pf_bid_buy - float(prev_close) if prev_close > 0 else 0
            pf_front_buy_chg = pf_front_buy - float(prev_close) if prev_close > 0 else 0
            pf_ask_buy_chg = pf_ask_buy - float(prev_close) if prev_close > 0 else 0
            pf_ask_sell_chg = pf_ask_sell - float(prev_close) if prev_close > 0 else 0
            pf_front_sell_chg = pf_front_sell - float(prev_close) if prev_close > 0 else 0
            pf_bid_sell_chg = pf_bid_sell - float(prev_close) if prev_close > 0 else 0
            
            # Ucuzluk/Pahalilik skorları (Ntahaf formülleri)
            bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
            front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
            ask_buy_ucuzluk = pf_ask_buy_chg - benchmark_chg
            ask_sell_pahali = pf_ask_sell_chg - benchmark_chg
            front_sell_pahali = pf_front_sell_chg - benchmark_chg
            bid_sell_pahali = pf_bid_sell_chg - benchmark_chg
            
            # Final skorlar (FINAL_THG varsa kullan, yoksa 0)
            final_thg = float(row.get('FINAL_THG', 0)) if row.get('FINAL_THG') != 'N/A' else 0
            
            def final_skor(final_thg, skor):
                return final_thg - 400 * skor
            
            final_bb = final_skor(final_thg, bid_buy_ucuzluk)
            final_fb = final_skor(final_thg, front_buy_ucuzluk)
            final_ab = final_skor(final_thg, ask_buy_ucuzluk)
            final_as = final_skor(final_thg, ask_sell_pahali)
            final_fs = final_skor(final_thg, front_sell_pahali)
            final_bs = final_skor(final_thg, bid_sell_pahali)
            
            # Başarılı hesaplanan skorları cache'e kaydet
            calculated_scores = {
                'Bid_buy_ucuzluk_skoru': round(bid_buy_ucuzluk, 2),
                'Front_buy_ucuzluk_skoru': round(front_buy_ucuzluk, 2),
                'Ask_buy_ucuzluk_skoru': round(ask_buy_ucuzluk, 2),
                'Ask_sell_pahalilik_skoru': round(ask_sell_pahali, 2),
                'Front_sell_pahalilik_skoru': round(front_sell_pahali, 2),
                'Bid_sell_pahalilik_skoru': round(bid_sell_pahali, 2),
                'Final_BB_skor': round(final_bb, 2),
                'Final_FB_skor': round(final_fb, 2),
                'Final_AB_skor': round(final_ab, 2),
                'Final_AS_skor': round(final_as, 2),
                'Final_FS_skor': round(final_fs, 2),
                'Final_BS_skor': round(final_bs, 2),
                'Spread': round(spread, 4)
            }
            
            # Cache'e kaydet
            if not hasattr(self, 'last_valid_scores'):
                self.last_valid_scores = {}
            self.last_valid_scores[ticker] = calculated_scores
            
            return calculated_scores
        except Exception as e:
            # Cache'den son geçerli değerleri al (varsa)
            if hasattr(self, 'last_valid_scores') and ticker in self.last_valid_scores:
                cached_scores = self.last_valid_scores[ticker]
                print(f"[CACHE] {ticker} için cached skorlar kullanılıyor")
                return cached_scores
            else:
                print(f"[HATA] Skor hesaplama hatası: {e}")
                return {
                    'Bid_buy_ucuzluk_skoru': 0,
                    'Front_buy_ucuzluk_skoru': 0,
                    'Ask_buy_ucuzluk_skoru': 0,
                    'Ask_sell_pahalilik_skoru': 0,
                    'Front_sell_pahalilik_skoru': 0,
                    'Bid_sell_pahalilik_skoru': 0,
                    'Final_BB_skor': 0,
                    'Final_FB_skor': 0,
                    'Final_AB_skor': 0,
                    'Final_AS_skor': 0,
                    'Final_FS_skor': 0,
                    'Final_BS_skor': 0,
                    'Spread': 0
                }

    def update_live_data(self):
        if not self.live_data_running:
            return
            
        self.update_table()
        self.update_scores_with_market_data() # Skorları güncelle
        self.after(1000, self.update_live_data)  # Her 1 saniyede bir güncelle
        
    def update_etf_data(self):
        """ETF verilerini güncelle"""
        if not self.live_data_running:
            return
            
        try:
            # Her ETF için market verilerini al ve paneli güncelle
            for symbol in self.etf_panel.etf_list:
                market_data = self.hammer.get_market_data(symbol)
                self.etf_panel.update_etf_data(symbol, market_data)
                
            # ETF display'ini güncelle (ana tabloyu etkilemeden)
            self.etf_panel.update_etf_display()
                
        except Exception as e:
            print(f"[HATA] ETF güncelleme hatası: {e}")
            
        # Her 2 saniyede bir güncelle (ana tablodan bağımsız)
        self.after(2000, self.update_etf_data)
        
    def get_visible_tickers(self):
        start_idx = self.current_page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.tickers))
        return self.tickers[start_idx:end_idx]
        
    def sort_by_column(self, column):
        """Seçilen kolona göre sırala"""
        if self.sort_column == column:
            # Aynı kolona tekrar tıklandı, sıralama yönünü değiştir
            self.sort_ascending = not self.sort_ascending
        else:
            # Yeni kolon seçildi, artan sıralama ile başla
            self.sort_column = column
            self.sort_ascending = True
            
        # DataFrame'i sırala
        try:
            # Sayısal kolonlar için nan'ları sona at
            if column in ['FINAL_THG', 'AVG_ADV', 'SMI', 'SHORT_FINAL', 'Bid', 'Ask', 'Last', 'Volume']:
                # Önce string 'N/A' değerlerini NaN'a çevir
                self.df[column] = pd.to_numeric(self.df[column], errors='coerce')
                
            # Sırala
            self.df = self.df.sort_values(
                by=column,
                ascending=self.sort_ascending,
                na_position='last'
            )
            
            # Sıralanmış ticker listesini güncelle
            self.tickers = self.df['PREF IBKR'].tolist()
            
            # Başlığı güncelle
            direction = "↑" if self.sort_ascending else "↓"
            for col in self.table["columns"]:
                if col == column:
                    self.table.heading(col, text=f"{col} {direction}")
                else:
                    self.table.heading(col, text=col)
                    
            # Tabloyu güncelle
            self.current_page = 0  # İlk sayfaya dön
            self.update_table()
            
        except Exception as e:
            print(f"[HATA] Sıralama hatası ({column}): {e}")
        
    def update_table(self):
        # Mevcut seçimleri kaydet
        selected_items = {}
        for item in self.table.get_children():
            ticker = self.table.set(item, 'PREF IBKR')
            is_selected = self.table.set(item, 'Seç') == '✓'
            if is_selected:
                selected_items[ticker] = True
        
        # Görünür ticker'ları al
        visible_tickers = self.get_visible_tickers()
        
        # Tabloyu temizle ve yeniden oluştur (sadece ilk kez veya sayfa değiştiğinde)
        if not hasattr(self, '_last_visible_tickers') or self._last_visible_tickers != visible_tickers:
            # Tabloyu temizle
            for item in self.table.get_children():
                self.table.delete(item)
            
            # Yeni görünür preferred stock'lara REAL-TIME L1 subscribe ol (sadece preferred stock'lar)
            if hasattr(self, 'live_data_running') and self.live_data_running:
                print(f"\n[PREF] 🔄 {len(visible_tickers)} preferred stock için REAL-TIME L1 streaming...")
                
                # Preferred stock'ları kaydet
                self.preferred_tickers = [ticker for ticker in visible_tickers 
                                        if " PR" in ticker or " PRA" in ticker or " PRC" in ticker]
                
                for ticker in self.preferred_tickers:
                    self.hammer.subscribe_symbol(ticker)  # Artık bu L1 streaming yapacak (real-time)
                    print(f"[PREF] ✅ {ticker} L1 streaming başlatıldı")
                
                # 2s snapshot sistemi IPTAL - artık real-time L1 streaming kullanıyoruz!
            
            # Her ticker için satır ekle
            for ticker in visible_tickers:
                try:
                    # CSV'den statik verileri al
                    row_data = self.df[self.df['PREF IBKR'] == ticker].iloc[0]
                    
                    # Statik değerleri formatla
                    final_thg = row_data.get('FINAL_THG', 'N/A')
                    if isinstance(final_thg, (int, float)) and not np.isnan(final_thg):
                        final_thg = f"{final_thg:.2f}"
                        
                    avg_adv = row_data.get('AVG_ADV', 'N/A')
                    if isinstance(avg_adv, (int, float)) and not np.isnan(avg_adv):
                        avg_adv = f"{avg_adv:.2f}"
                        
                    smi = row_data.get('SMI', 'N/A')
                    if isinstance(smi, (int, float)) and not np.isnan(smi):
                        smi = f"{smi:.4f}"
                        
                    short_final = row_data.get('SHORT_FINAL', 'N/A')
                    if isinstance(short_final, (int, float)) and not np.isnan(short_final):
                        short_final = f"{short_final:.2f}"
                    
                    # Skor değerlerini al
                    bid_buy_ucuzluk = row_data.get('Bid_buy_ucuzluk_skoru', 'N/A')
                    front_buy_ucuzluk = row_data.get('Front_buy_ucuzluk_skoru', 'N/A')
                    ask_buy_ucuzluk = row_data.get('Ask_buy_ucuzluk_skoru', 'N/A')
                    ask_sell_pahali = row_data.get('Ask_sell_pahalilik_skoru', 'N/A')
                    front_sell_pahali = row_data.get('Front_sell_pahalilik_skoru', 'N/A')
                    bid_sell_pahali = row_data.get('Bid_sell_pahalilik_skoru', 'N/A')
                    final_bb = row_data.get('Final_BB_skor', 'N/A')
                    final_fb = row_data.get('Final_FB_skor', 'N/A')
                    final_ab = row_data.get('Final_AB_skor', 'N/A')
                    final_as = row_data.get('Final_AS_skor', 'N/A')
                    final_fs = row_data.get('Final_FS_skor', 'N/A')
                    final_bs = row_data.get('Final_BS_skor', 'N/A')
                    spread = row_data.get('Spread', 'N/A')
                    
                    # Benchmark değerlerini al
                    benchmark_type = row_data.get('Benchmark_Type', 'N/A')
                    benchmark_chg = row_data.get('Benchmark_Chg', 'N/A')
                    
                    # Skor değerlerini formatla
                    def format_score(value):
                        if isinstance(value, (int, float)) and not np.isnan(value):
                            return f"{value:.2f}"
                        return 'N/A'
                    
                    # Seçim durumunu kontrol et
                    selection_status = "✓" if ticker in selected_items else ""
                    
                    # CSV'den mevcut kolonları al (show_file_data'dan available_columns kullan)
                    # Bu satırları kaldırdık çünkü available_columns zaten show_file_data'da tanımlanmış
                    
                    # Seç kolonu ile başla
                    row_values = [selection_status]
                    
                    # CSV'den belirli kolonları ekle (available_columns'ı class seviyesinde tutmamız gerekiyor)
                    available_columns = [col for col in ['PREF IBKR', 'CMON', 'CGRUP', 'FINAL_THG', 'AVG_ADV', 'SMI', 'SHORT_FINAL'] if col in self.df.columns]
                    for col in available_columns:
                        value = row_data.get(col, 'N/A')
                        if isinstance(value, (int, float)) and not np.isnan(value):
                            if col in ['SMI']:
                                value = f"{value:.4f}"
                            else:
                                value = f"{value:.2f}"
                        row_values.append(value)
                    
                    # Skor kolonlarını ekle (kendi hesapladığımız)
                    score_columns = [
                        'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
                        'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru',
                        'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor',
                        'Spread'
                    ]
                    
                    for col in score_columns:
                        value = row_data.get(col, 'N/A')
                        if isinstance(value, (int, float)) and not np.isnan(value):
                            value = f"{value:.2f}"
                        row_values.append(value)
                    
                    # Benchmark kolonlarını ekle (kendi hesapladığımız)
                    benchmark_type = row_data.get('Benchmark_Type', 'N/A')
                    benchmark_chg = row_data.get('Benchmark_Chg', 'N/A')
                    if isinstance(benchmark_chg, (int, float)) and not np.isnan(benchmark_chg):
                        benchmark_chg = f"{benchmark_chg:.2f}"
                    row_values.extend([benchmark_type, benchmark_chg])
                    
                    # Live kolonları ekle (başlangıçta N/A)
                    row_values.extend(['N/A', 'N/A', 'N/A', 'N/A'])  # Bid, Ask, Last, Volume
                except Exception as e:
                    print(f"[HATA] {ticker} için veri hatası: {e}")
                    selection_status = "✓" if ticker in selected_items else ""
                    # Dinamik olarak kolon sayısını hesapla
                    total_columns = len(self.columns) - 1  # 'Seç' kolonunu çıkar
                    row_values = [selection_status] + [ticker] + ['N/A'] * (total_columns - 1)
                
                # Satırı ekle
                self.table.insert('', 'end', values=row_values)
            
            # Görünür ticker'ları kaydet
            self._last_visible_tickers = visible_tickers
        
        # Sadece live data kolonlarını güncelle (seçimleri koruyarak)
        for item in self.table.get_children():
            ticker = self.table.set(item, 'PREF IBKR')
            if ticker in visible_tickers:
                try:
                    # Hammer Pro'dan live verileri al
                    market_data = self.hammer.get_market_data(ticker)
                    if not market_data:
                        continue
                        
                    bid_raw = market_data.get('bid', 0)
                    ask_raw = market_data.get('ask', 0)
                    last_raw = market_data.get('last', 0)
                    volume_raw = market_data.get('volume', 0)
                    is_live = market_data.get('is_live', False)
                    

                    
                    # Format değerleri (0 ise N/A)
                    bid = f"{bid_raw:.2f}" if bid_raw > 0 else "N/A"
                    ask = f"{ask_raw:.2f}" if ask_raw > 0 else "N/A"
                    last = f"{last_raw:.2f}" if last_raw > 0 else "N/A"
                    volume = f"{int(volume_raw):,}" if volume_raw > 0 else "N/A"
                    
                    # Live kolonları güncelle
                    self.table.set(item, 'Bid', bid)
                    self.table.set(item, 'Ask', ask)
                    self.table.set(item, 'Last', last)
                    self.table.set(item, 'Volume', volume)
                    
                    # SKORLARI GERÇEK VERİLERLE HESAPLA!
                    if bid_raw > 0 and ask_raw > 0 and last_raw > 0:
                        # CSV'den row verisini al
                        csv_row = self.df[self.df['PREF IBKR'] == ticker]
                        if not csv_row.empty:
                            row_data = csv_row.iloc[0]
                            prev_close = market_data.get('prevClose', 0)
                            
                            # PrevClose güncel değilse snapshot ile güncelle
                            if prev_close == 0 or abs(last_raw - prev_close) > (last_raw * 0.1):  # %10'dan fazla fark varsa
                                self.hammer.get_symbol_snapshot(ticker)
                                # Snapshot'tan güncel prev_close al
                                updated_data = self.hammer.get_market_data(ticker)
                                if updated_data:
                                    prev_close = updated_data.get('prevClose', prev_close)
                            
                            # Benchmark tipini ve değişimini hesapla
                            benchmark_type = self.get_benchmark_type_for_ticker(ticker)
                            benchmark_chg = self.get_benchmark_change_for_ticker(ticker)
                            
                            # Benchmark bilgilerini tabloya yaz
                            if 'Benchmark_Type' in self.columns:
                                self.table.set(item, 'Benchmark_Type', benchmark_type)
                            if 'Benchmark_Chg' in self.columns:
                                self.table.set(item, 'Benchmark_Chg', f"{benchmark_chg:.4f}")
                            
                            # Skorları hesapla
                            from .update_janalldata_with_scores import calculate_scores
                            scores = calculate_scores(row_data, bid_raw, ask_raw, last_raw, prev_close, benchmark_chg)
                            
                            # Skorları tabloya yaz
                            for score_name, score_value in scores.items():
                                if score_name in self.columns:
                                    col_index = self.columns.index(score_name)
                                    if col_index < len(self.table['columns']):
                                        self.table.set(item, score_name, f"{score_value:.2f}")
                            

                    
                    # Live data satırlarını yeşil yap
                    if is_live:
                        self.table.item(item, tags=('live_data',))
                    else:
                        self.table.item(item, tags=())
                        
                except Exception as e:
                    print(f"[HATA] {ticker} için live data güncelleme hatası: {e}")
        
        # Live data satırlarını yeşil yap
        self.table.tag_configure('live_data', background='lightgreen')
        
        # Sayfa bilgisini güncelle
        self.lbl_page.config(text=f"Sayfa {self.current_page + 1} / {self.total_pages}")
        
    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_table()
            
    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_table()
            
    def on_double_click(self, event):
        """Tabloda çift tıklanan satır için OrderBook penceresini aç"""
        try:
            # Tıklanan konumu kontrol et
            item_id = self.table.identify('item', event.x, event.y)
            if not item_id:  # Tablo dışına tıklandı
                return
                
            # Tıklanan satırı seç
            self.table.selection_set(item_id)
            
            # Seçili satırı al
            selection = self.table.selection()
            if not selection:  # Seçili satır yoksa
                return
                
            item = selection[0]
            # Seçilen satırın verilerini al
            values = self.table.item(item)['values']
            if not values:
                return
                
            # İlk kolon PREF IBKR
            symbol = values[1]  # Seç kolonu sonrası PREF IBKR
            
            # OrderBook penceresini aç (order butonları ile)
            OrderBookWindow(self, symbol, self.hammer)
            
        except Exception as e:
            print(f"[HATA] OrderBook açılırken hata: {e}")
        
    def on_table_click(self, event):
        """Tabloya tıklanan satırın seçim durumunu değiştir"""
        try:
            # Tıklanan konumu kontrol et
            region = self.table.identify_region(event.x, event.y)
            if region != "cell":
                return
                
            # Tıklanan kolonu kontrol et
            column = self.table.identify_column(event.x)
            if column != "#1":  # Sadece Seç kolonuna tıklandığında işlem yap
                return
                
            # Tıklanan satırı bul
            item_id = self.table.identify('item', event.x, event.y)
            if not item_id:  # Tablo dışına tıklandı
                return
                
            # Seçim durumunu değiştir
            current = self.table.set(item_id, "Seç")
            new_value = "✓" if current != "✓" else ""
            self.table.set(item_id, "Seç", new_value)
            
            # Debug için yazdır
            ticker = self.table.set(item_id, "PREF IBKR")
            print(f"✅ {ticker} {'seçildi' if new_value == '✓' else 'seçimi kaldırıldı'}")
            
        except Exception as e:
            print(f"[HATA] Tabloya tıklanan satır seçimi hatası: {e}")
        
    def show_file_data(self, filename, is_main=False):
        """Seçilen CSV dosyasındaki verileri göster"""
        try:
            # CSV'yi oku
            df = pd.read_csv(filename)
            
            # CSV'den sadece belirli kolonları al
            csv_columns_to_show = ['PREF IBKR', 'CMON', 'CGRUP', 'FINAL_THG', 'AVG_ADV', 'SMI', 'SHORT_FINAL']
            
            # Sadece mevcut kolonları al (yoksa hata vermesin)
            available_columns = [col for col in csv_columns_to_show if col in df.columns]
            
            # Skor kolonları (kendi hesapladığımız)
            score_columns = [
                'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
                'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru',
                'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor',
                'Spread'
            ]
            
            # Benchmark kolonları (kendi hesapladığımız)
            benchmark_columns = ['Benchmark_Type', 'Benchmark_Chg']
            
            # Live kolonları (Hammer Pro'dan)
            live_columns = ['Bid', 'Ask', 'Last', 'Volume']
            
            # Toplam kolon sırası
            self.columns = ['Seç'] + available_columns + score_columns + benchmark_columns + live_columns
            
            # Tabloyu yeniden oluştur
            self.table.destroy()
            self.table = ttk.Treeview(self, columns=self.columns, show='headings', height=15)
            
            # Çift tıklama olayını bağla
            self.table.bind('<Double-1>', self.on_double_click)
            
            # Checkbox tıklama olayını bağla - sadece Seç kolonu için
            self.table.bind('<ButtonRelease-1>', self.on_table_click)
            
            # Kolon başlıkları ve genişlikleri
            for col in self.columns:
                # Sıralama fonksiyonunu bağla
                self.table.heading(col, 
                    text=col,
                    command=lambda c=col: self.sort_by_column(c))
                    
                if col in ['PREF IBKR']:
                    self.table.column(col, width=35, anchor='w')  # Sol hizalı - çok dar
                elif col in ['CMON', 'CGRUP']:
                    self.table.column(col, width=15, anchor='center')  # En dar
                elif col in ['SMI', 'SHORT_FINAL']:
                    self.table.column(col, width=20, anchor='center')  # Dar
                elif col in ['FINAL_THG', 'AVG_ADV']:
                    self.table.column(col, width=25, anchor='center')  # Orta
                elif 'skor' in col.lower() or 'final' in col.lower():
                    self.table.column(col, width=30, anchor='center')  # Skor kolonları - çok dar
                elif 'benchmark' in col.lower():
                    self.table.column(col, width=20, anchor='center') # Benchmark kolonları - orta
                else:
                    self.table.column(col, width=20, anchor='center')  # Normal - çok dar
                    
            self.table.pack(fill='both', expand=True, padx=5, pady=5)
            
            # Tabloyu temizle
            for item in self.table.get_children():
                self.table.delete(item)
                
            # Ticker'ları al
            self.tickers = df['PREF IBKR'].tolist()
            
            # Sayfalama ayarlarını güncelle
            self.current_page = 0
            self.total_pages = (len(self.tickers) + self.items_per_page - 1) // self.items_per_page
            
            # Yeni verileri göster
            self.df = df
            
            # Live data için tüm sembollere subscribe ol
            if is_main:
                print("\n[HAMMER] 🔄 Tüm sembollere subscribe olunuyor...")
                for ticker in self.tickers:
                    self.hammer.subscribe_symbol(ticker)
                    
            # Sıralama sıfırla
            self.sort_column = None
            self.sort_ascending = True
            
            # _last_visible_tickers'ı sıfırla (yeni dosya yüklendiğinde tablo yeniden çizilsin)
            if hasattr(self, '_last_visible_tickers'):
                delattr(self, '_last_visible_tickers')
                
            self.update_table()
            
            # Başlığı güncelle
            if is_main:
                self.title("JanAll - Tüm Veriler")
            else:
                short_name = filename.replace('ssfinek', '').replace('.csv', '')
                self.title(f"JanAll - {short_name}")
                
            print(f"[CSV] ✅ {filename} yüklendi")
            print(f"[CSV] ℹ️ {len(df)} satır")
            print(f"[CSV] 📋 Mevcut Kolonlar: {', '.join(available_columns)}")
            print(f"[CSV] 📋 Toplam Kolon Sayısı: {len(self.columns)}")
            
        except Exception as e:
            print(f"[CSV] ❌ Dosya okuma hatası ({filename}): {e}")
    
    # SNAPSHOT FONKSİYONLARI KALDIRILDI - Artık sadece L1 streaming kullanıyoruz!