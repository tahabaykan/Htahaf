"""
Ana pencere modülü.

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janallres/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Örnek:
✅ DOĞRU: "janalldata.csv" (StockTracker dizininde)
❌ YANLIŞ: "janallresres/janalldata.csv"
=================================
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import numpy as np
import time
import os
import threading
from datetime import datetime, date
from .etf_panel import ETFPanel
from .order_management import OrderManager, OrderBookWindow
from .bdata_storage import BDataStorage
from .stock_data_manager import StockDataManager
from .exception_manager import ExceptionListManager
from .exception_window import ExceptionListWindow

# Grup isimleri çeviri sözlüğü
GROUP_NAME_MAPPING = {
    'heldcilizyeniyedi': 'N-7coup',
    'heldcommonsuz': 'WO-issuer',
    'helddeznff': 'Dis-NFF',
    'heldff': 'Fix-Float',
    'heldflr': 'Directly Float',
    'heldgarabetaltiyedi': 'W-6coup',
    'heldkuponlu': 'Coupon based',
    'heldkuponlukreciliz': 'KRE W-Coupon',
    'heldkuponlukreorta': 'KRE M-Coupon',
    'heldnff': 'ad-NFF',
    'heldotelremorta': 'REM-Hot',
    'heldsolidbig': 'Stable-CP',
    'heldtitrekhc': 'W- High Coup',
    'highmatur': 'High Coup Maturity',
    'notbesmaturlu': 'NL Maturity',
    'notcefilliquid': 'IL-CEF issuer',
    'nottitrekhc': 'Not held - High Coup',
    'rumoreddanger': 'Once Rumored',
    'salakilliquid': 'Very illiquid',
    'shitremhc': 'W-REM High Coup'
}

def get_display_name(group_name):
    """Grup ismini görüntüleme ismine çevir"""
    return GROUP_NAME_MAPPING.get(group_name, group_name)


class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("janallres")
        
        # Performans optimizasyonu flag'leri
        self.is_mini450_active = False
        self.background_data_cache = {}
        self.background_update_thread = None
        self.background_update_running = False
        
        # Hammer Pro client
        from .hammer_client import HammerClient
        self.hammer = HammerClient(
            host='127.0.0.1',  # localhost
            port=16400,        # varsayılan port
            password='Nl201090.',  # API şifresi
            main_window=self  # Main window referansı
        )
        
        # IBKR TWS/Gateway client (ib_insync)
        from .ibkr_client import IBKRClient
        self.ibkr = IBKRClient(
            host='127.0.0.1',  # localhost
            port=4001,         # IBKR Gateway port (4001=live, 4002=paper)
            client_id=1,       # Client ID
            main_window=self   # Main window referansı
        )
        
        # IBKR Native client (TWS API)
        from .ibkr_native_client import IBKRNativeClient
        self.ibkr_native = IBKRNativeClient(
            host='127.0.0.1',  # localhost
            port=4001,         # IBKR Gateway port (4001=live, 4002=paper)
            client_id=2,       # Farklı Client ID (native için)
            main_window=self   # Main window referansı
        )
        
        # Mode Manager
        from .mode_manager import ModeManager
        self.mode_manager = ModeManager(
            hammer_client=self.hammer,
            ibkr_client=self.ibkr,
            ibkr_native_client=self.ibkr_native,
            main_window=self  # Controller kontrolü için
        )
        
        # Mod sistemi
        self.current_mode = "HAMPRO"  # HAMPRO veya IBKR
        self.hampro_mode = True
        self.ibkr_gun_mode = False
        self.ibkr_ped_mode = False
        
        # Order Manager
        self.order_manager = OrderManager(self)
        
        # Günlük befham.csv kontrolü
        self.befham_checked_today = False
        self.check_daily_befham()
        # Günlük befibgun.csv ve befibped.csv kontrolü (IBKR için)
        self.befibgun_checked_today = False
        self.befibped_checked_today = False
        
        # BDATA Storage
        self.bdata_storage = BDataStorage()
        
        # Stock Data Manager - Ana sayfa verilerini yönetmek için
        self.stock_data_manager = StockDataManager()
        
        # Exception List Manager - Trade edilmemesi gereken hisseleri yönetir
        self.exception_manager = ExceptionListManager("exception_list.csv")
        
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
            'DEFAULT': {'PFF': 1.1, 'TLT': -0.08, 'IEF': 0.0, 'IEI': 0.0},  # PFF*1.1 - TLT*0.08
            'C400': {'PFF': 0.36, 'TLT': 0.36, 'IEF': 0.08, 'IEI': 0.0},
            'C425': {'PFF': 0.368, 'TLT': 0.34, 'IEF': 0.092, 'IEI': 0.0},
            'C450': {'PFF': 0.38, 'TLT': 0.32, 'IEF': 0.10, 'IEI': 0.0},
            'C475': {'PFF': 0.40, 'TLT': 0.30, 'IEF': 0.12, 'IEI': 0.0},
            'C500': {'PFF': 0.32, 'TLT': 0.40, 'IEF': 0.08, 'IEI': 0.0},
            'C525': {'PFF': 0.42, 'TLT': 0.28, 'IEF': 0.14, 'IEI': 0.0},
            'C550': {'PFF': 0.408, 'TLT': 0.2, 'IEF': 0.152, 'IEI': 0.04},
            'C575': {'PFF': 0.44, 'TLT': 0.24, 'IEF': 0.16, 'IEI': 0.0},
            'C600': {'PFF': 0.432, 'TLT': 0.12, 'IEF': 0.168, 'IEI': 0.08},
            'C625': {'PFF': 0.448, 'TLT': 0.08, 'IEF': 0.172, 'IEI': 0.1}
        }
        
        # Önceki ETF fiyatları (değişim hesaplama için)
        self.prev_etf_prices = {}
        
        # Stabil benchmark hesaplama için
        self.stable_etf_changes = {}  # Son güncellenmiş sabit değerler
        self.etf_changes = {}  # ETF değişimleri (stable'dan kopyalanır)
        self.last_benchmark_update = 0  # Son güncelleme zamanı
        self.benchmark_update_interval = 5.0  # 5 saniyede bir güncelle
        
        # Cache sistemi - hesaplama boşluklarını önle
        self.last_valid_scores = {}  # Her ticker için son geçerli skorlar
        
        # Başlangıçta boş DataFrame
        self.df = pd.DataFrame()
        
        # Ana CSV dosyasını otomatik yükle
        self.load_main_csv_on_startup()
        self.tickers = []
        
        # Sayfalama ayarları
        self.items_per_page = 15
        self.current_page = 0
        self.total_pages = (len(self.tickers) + self.items_per_page - 1) // self.items_per_page
        
        # Sıralama ayarları
        self.sort_column = None
        self.sort_ascending = True
        
        self.setup_ui()
        
        # Başlangıçta exposure bilgisini güncelle
        self.after(1000, self.update_exposure_display)  # 1 saniye sonra güncelle
    
    def load_main_csv_on_startup(self):
        """Uygulama başlarken ana CSV dosyasını otomatik yükle"""
        try:
            csv_file = 'janalldata.csv'
            if os.path.exists(csv_file):
                print(f"[STARTUP] INFO Ana CSV dosyasi yukleniyor: {csv_file}")
                self.show_file_data(csv_file, is_main=True)
                print(f"[STARTUP] ✅ Ana CSV dosyası yüklendi: {len(self.df)} hisse")
            else:
                print(f"[STARTUP] ⚠️ Ana CSV dosyası bulunamadı: {csv_file}")
                print(f"[STARTUP] 💡 Benchmark hesaplamaları için CSV dosyası gerekli!")
        except Exception as e:
            print(f"[STARTUP] ERROR Ana CSV yukleme hatasi: {e}")
        
    def setup_ui(self):
        # Üst panel - Bağlantı butonları
        top_frame = ttk.Frame(self)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        self.btn_connect = ttk.Button(top_frame, text="Connect to Hammer Pro", command=self.connect_hammer)
        self.btn_connect.pack(side='left', padx=2)
        
        self.btn_live = ttk.Button(top_frame, text="Start Live Data", command=self.toggle_live_data)
        self.btn_live.pack(side='left', padx=2)
        
        # Exposure bilgisi gösterimi - Lot Bölücü yanına taşınacak
        
        # Port Adjuster butonu
        self.btn_port_adjuster = ttk.Button(top_frame, text="Port Adjuster", width=14,
                                           command=self.show_port_adjuster)
        self.btn_port_adjuster.pack(side='left', padx=4)
        
        # Pozisyonlarım butonu
        from .mypositions import show_positions_window
        self.btn_mypos = ttk.Button(top_frame, text="My Positions", width=14,
                                    command=lambda: self.show_positions())
        self.btn_mypos.pack(side='left', padx=4)
        
        # Take Profit Longs butonu
        self.btn_take_profit_longs = ttk.Button(top_frame, text="Take Profit Longs", width=16,
                                               command=self.show_take_profit_longs)
        self.btn_take_profit_longs.pack(side='left', padx=4)
        
        # Take Profit Shorts butonu
        self.btn_take_profit_shorts = ttk.Button(top_frame, text="Take Profit Shorts", width=16,
                                                command=self.show_take_profit_shorts)
        self.btn_take_profit_shorts.pack(side='left', padx=4)
        
        # L-spread butonu
        self.btn_lspread = ttk.Button(top_frame, text="L-spread", width=12,
                                        command=self.show_lspread)
        self.btn_lspread.pack(side='left', padx=4)
        
        # Emirlerim butonu
        self.btn_my_orders = ttk.Button(top_frame, text="My Orders", width=12,
                                       command=self.show_my_orders)
        self.btn_my_orders.pack(side='left', padx=4)
        
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
        
        # Soft Front butonları
        self.btn_soft_front_buy = ttk.Button(order_frame, text="SoftFront Buy", 
                                           command=lambda: self.order_manager.place_order_for_selected('soft_front_buy'), width=12)
        self.btn_soft_front_buy.pack(side='left', padx=1)
        
        self.btn_soft_front_sell = ttk.Button(order_frame, text="SoftFront Sell", 
                                            command=lambda: self.order_manager.place_order_for_selected('soft_front_sell'), width=12)
        self.btn_soft_front_sell.pack(side='left', padx=1)
        
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
        
        self.btn_lot_75 = ttk.Button(lot_frame, text="%75", 
                                    command=lambda: self.order_manager.set_lot_percentage(75), width=6)
        self.btn_lot_75.pack(side='left', padx=1)
        
        self.btn_lot_100 = ttk.Button(lot_frame, text="%100", 
                                     command=lambda: self.order_manager.set_lot_percentage(100), width=6)
        self.btn_lot_100.pack(side='left', padx=1)
        
        self.btn_lot_avg_adv = ttk.Button(lot_frame, text="Avg Adv", 
                                         command=self.order_manager.set_lot_avg_adv, width=8)
        self.btn_lot_avg_adv.pack(side='left', padx=1)
        
        # Seçim butonları
        selection_frame = ttk.Frame(self)
        selection_frame.pack(fill='x', padx=5, pady=2)
        
        self.btn_select_all = ttk.Button(selection_frame, text="Select All", 
                                       command=self.order_manager.select_all_tickers, width=12)
        self.btn_select_all.pack(side='left', padx=1)
        
        self.btn_deselect_all = ttk.Button(selection_frame, text="Deselect All", 
                                         command=self.order_manager.deselect_all_tickers, width=12)
        self.btn_deselect_all.pack(side='left', padx=1)
        
        # Mod butonları - Tümünü Seç ve Tümünü Kaldır butonlarının yanına taşındı
        self.btn_hampro_mode = ttk.Button(selection_frame, text="H-1 Mod", width=12,
                                         command=lambda: self.set_mode("HAMPRO"))
        self.btn_hampro_mode.pack(side='left', padx=2)
        
        self.btn_ibkr_gun_mode = ttk.Button(selection_frame, text="I-1 Mod", width=14,
                                           command=lambda: self.set_mode("IBKR_GUN"))
        self.btn_ibkr_gun_mode.pack(side='left', padx=2)
        
        self.btn_ibkr_ped_mode = ttk.Button(selection_frame, text="I-2 Mod", width=14,
                                           command=lambda: self.set_mode("IBKR_PED"))
        self.btn_ibkr_ped_mode.pack(side='left', padx=2)
        
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
            'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor', 'Final_SAS_skor', 'Final_SFS_skor', 'Final_SBS_skor',
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
        
        # Mod butonlarını ayarla
        self.setup_mode_buttons()
        
        # CSV dosya butonları
        files_frame = ttk.Frame(self)
        files_frame.pack(fill='x', padx=5, pady=5)
        
        # Ana veri butonu
        main_frame = ttk.Frame(files_frame)
        main_frame.pack(fill='x', pady=2)
        
        btn_main = ttk.Button(main_frame, text="janallresDATA", 
                            command=lambda: self.show_file_data('janalldata.csv', is_main=True))
        btn_main.pack(side='left', padx=2)
        
        # Allincdata butonu - Tüm hisseleri mini görünümde göster
        btn_mini450 = ttk.Button(main_frame, text="Allincdata", 
                                command=self.show_mini450_view, 
                                style='Accent.TButton')
        btn_mini450.pack(side='left', padx=5)
        
        # Passive mgmt butonu - Pozisyon yönetimi robotu
        btn_psfalgo = ttk.Button(main_frame, text="Passive mgmt", 
                                command=self.start_psfalgo_robot, 
                                style='Accent.TButton')
        btn_psfalgo.pack(side='left', padx=5)
        
        # Compare It butonu - Portföy karşılaştırması
        self.btn_compare_it = ttk.Button(main_frame, text="📊 Compare It", 
                                        command=self.show_portfolio_comparison,
                                        style='Accent.TButton')
        self.btn_compare_it.pack(side='left', padx=5)
        
        # Lot Bölücü butonu - Emirleri 200er lotlar halinde böl
        self.lot_divider_enabled = False
        self.btn_lot_divider = ttk.Button(main_frame, text="📦 Lot Divider: OFF", 
                                        command=self.toggle_lot_divider, 
                                        style='Accent.TButton')
        self.btn_lot_divider.pack(side='left', padx=5)
        
        # Exposure bilgisi gösterimi - Lot Bölücü yanında
        self.exposure_label = ttk.Label(main_frame, text="H-1 Mod active - Long: 0.00 | Short: 0.00 | Total: 0.00", 
                                       font=('Arial', 9, 'bold'), foreground='blue')
        self.exposure_label.pack(side='left', padx=10)
        
        # Ayırıcı çizgi
        separator = ttk.Separator(files_frame, orient='horizontal')
        separator.pack(fill='x', pady=5)
        
        # CSV dosya isimleri - janek_ssfinek dosyalarını kullan (prev_close kolonu var)
        csv_files = [
            'janek_ssfinekheldcilizyeniyedi.csv',
            'janek_ssfinekheldcommonsuz.csv',
            'janek_ssfinekhelddeznff.csv',
            'janek_ssfinekheldff.csv',
            'janek_ssfinekheldflr.csv',
            'janek_ssfinekheldgarabetaltiyedi.csv',
            'janek_ssfinekheldkuponlu.csv',
            'janek_ssfinekheldkuponlukreciliz.csv',
            'janek_ssfinekheldkuponlukreorta.csv',
            'janek_ssfinekheldnff.csv',
            'janek_ssfinekheldotelremorta.csv',
            'janek_ssfinekheldsolidbig.csv',
            'janek_ssfinekheldtitrekhc.csv',
            'janek_ssfinekhighmatur.csv',
            'janek_ssfineknotbesmaturlu.csv',
            'janek_ssfineknotcefilliquid.csv',
            'janek_ssfineknottitrekhc.csv',
            'janek_ssfinekrumoreddanger.csv',
            'janek_ssfineksalakilliquid.csv',
            'janek_ssfinekshitremhc.csv'
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
            
            # Dosya adını kısalt ve görüntüleme ismine çevir
            short_name = file.replace('janek_ssfinek', '').replace('.csv', '')
            display_name = get_display_name(short_name)
            btn = ttk.Button(current_frame, text=display_name, command=lambda f=file: self.show_file_data(f))
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
                    # ETF Panel'deki aynı veri kaynağını kullan!
                    if etf in self.etf_panel.etf_data:
                        etf_data = self.etf_panel.etf_data[etf]
                        last_price = etf_data.get('last', 0)
                        
                        # ETF Panel'deki CSV'den prev_close al (aynı kaynak!)
                        csv_prev_close = self.etf_panel.get_etf_prev_close(etf)
                        
                        if last_price > 0 and csv_prev_close > 0:
                            # ETF Panel'deki aynı hesaplama yöntemi!
                            change_dollars = round(last_price - csv_prev_close, 4)
                            self.stable_etf_changes[etf] = change_dollars
                        else:
                            self.stable_etf_changes[etf] = 0
                    else:
                        # ETF Panel'de yoksa CSV'den al
                        csv_prev_close = self.etf_panel.get_etf_prev_close(etf)
                        if csv_prev_close > 0:
                            # Market data'dan last price al
                            market_data = self.hammer.get_market_data(etf)
                            if market_data:
                                last_price = market_data.get('last', 0)
                                if last_price > 0:
                                    change_dollars = round(last_price - csv_prev_close, 4)
                                    self.stable_etf_changes[etf] = change_dollars
                                else:
                                    self.stable_etf_changes[etf] = 0
                            else:
                                self.stable_etf_changes[etf] = 0
                        else:
                            self.stable_etf_changes[etf] = 0
            
            # Son güncelleme zamanını kaydet
            self.last_benchmark_update = current_time
            
            # self.etf_changes'i stable değerlerle güncelle
            self.etf_changes = self.stable_etf_changes.copy()
                
        except Exception as e:
            pass
    
    def get_benchmark_type_for_ticker(self, ticker):
        """Ticker için benchmark tipini belirle (CGRUP'a göre)"""
        try:
            # DataFrame'i kontrol et
            if self.df.empty:
                return 'DEFAULT'
            
            # Ticker'ı DataFrame'de ara
            ticker_row = self.df[self.df['PREF IBKR'] == ticker]
            
            if ticker_row.empty:
                return 'DEFAULT'
            
            # CGRUP kolonundan değeri al
            cgrup_str = ticker_row.iloc[0]['CGRUP']
            
            if pd.isna(cgrup_str) or cgrup_str == '':
                return 'DEFAULT'
            
            # CGRUP değerini benchmark key'e çevir
            # CGRUP değerleri zaten 'c525' formatında geliyor, direkt kullan
            if str(cgrup_str).lower().startswith('c'):
                benchmark_key = str(cgrup_str).upper()  # 'c525' -> 'C525'
            else:
                # Eski format: sayısal değer (5.25 -> C525)
                benchmark_key = f"C{int(float(cgrup_str) * 100)}"
            
            if benchmark_key in self.benchmark_formulas:
                return benchmark_key
            else:
                return 'DEFAULT'
                
        except Exception as e:
            return 'DEFAULT'
    
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
            return 0.0
    
    def connect_hammer(self):
        """Hammer Pro'ya bağlan/bağlantıyı kes"""
        if not self.hammer.connected:
            print("\n[HAMMER] OK Hammer Pro'ya baglaniliyor...")
            print(f"[HAMMER] OK Host: {self.hammer.host}")
            print(f"[HAMMER] OK Port: {self.hammer.port}")
            
            if self.hammer.connect():
                self.btn_connect.config(text="Disconnect")
                print("[HAMMER] OK Baglanti basarili!")
                
                # Bağlantı kurulduktan sonra befham.csv günlük kontrol (00:00-16:30)
                if not self.befham_checked_today:
                    self.check_daily_befham()
            else:
                print("[HAMMER] ERROR Baglanti basarisiz!")
                print("[HAMMER] INFO Kontrol edilecekler:")
                print("   1. Hammer Pro çalışıyor mu?")
                print("   2. Port numarası doğru mu?")
                print("   3. API şifresi doğru mu?")
        else:
            print("\n[HAMMER] OK Baglanti kesiliyor...")
            self.hammer.disconnect()
            self.btn_connect.config(text="Connect to Hammer Pro")
            print("[HAMMER] OK Baglanti kesildi.")
            
    def toggle_live_data(self):
        """Live data akışını başlat/durdur"""
        if not hasattr(self, 'live_data_running'):
            self.live_data_running = False
            
        if not self.live_data_running:
            # Önce janalldata.csv'yi yükle ve tüm sembollere subscribe ol
            self.show_file_data('janalldata.csv', is_main=True)
            
            # ETF'ler için sadece snapshot (L1 subscription yok)
            print("\n[ETF] OK ETF'ler icin snapshot sistemi baslatiliyor...")
            self.etf_panel.subscribe_etfs()  # Sadece snapshot çeker artık
            
            self.live_data_running = True
            self.btn_live.config(text="Stop Live Data")
            
            # ETF verilerini güncelleme döngüsünü başlat
            self.update_etf_data()
            
            # Ana tabloyu güncelleme döngüsünü başlat
            self.update_live_data()
        else:
            self.live_data_running = False
            self.btn_live.config(text="Start Live Data")
            
            # Artık snapshot sistemi yok, L1 streaming kullanıyoruz
    
    def load_prev_close_from_csv(self):
        """CSV dosyalarından prev_close değerlerini yükle"""
        try:
            # CSV dosyalarından prev_close değerleri yükleniyor...
            
            # janek_ss*.csv dosyalarını bul
            csv_files = []
            for file in os.listdir('.'):
                if file.startswith('janek_ss') and file.endswith('.csv'):
                    csv_files.append(file)
            
            # Bulunan dosyalar: {csv_files}
            
            # Cache'i temizle
            if hasattr(self, 'prev_close_cache'):
                delattr(self, 'prev_close_cache')
            self.prev_close_cache = {}
            
            # Her dosyayı oku ve prev_close değerlerini al
            for csv_file in csv_files:
                try:
                    df_csv = pd.read_csv(csv_file, encoding='utf-8-sig')
                    
                    # PREF IBKR ve prev_close kolonlarını kontrol et
                    if 'PREF IBKR' in df_csv.columns and 'prev_close' in df_csv.columns:
                        # {csv_file} okundu: {len(df_csv)} satır
                        
                        # prev_close değerlerini cache'le
                        for idx, row in df_csv.iterrows():
                            ticker = row['PREF IBKR']
                            prev_close = row['prev_close']
                            
                            # NaN kontrolü
                            if pd.notna(prev_close) and prev_close > 0:
                                self.prev_close_cache[ticker] = float(prev_close)
                                # {ticker}: prev_close={prev_close}
                            else:
                                # {ticker}: prev_close={prev_close} (geçersiz)
                                pass
                    
                    else:
                        # {csv_file}: PREF IBKR veya prev_close kolonu bulunamadı
                        pass
                
                except Exception as e:
                    continue
            
        except Exception as e:
            pass
            
    def update_scores_with_market_data(self):
        """Market data ile skorları güncelle - CSV'den prev_close oku"""
        try:
            # ETF verileri otomatik güncelleniyor (5s interval)
            
            # CSV'lerden prev_close değerlerini yükle
            self.load_prev_close_from_csv()
            
            # Sadece görünür ticker'lar için işle (performans için)
            visible_tickers = self.get_visible_tickers()
            
            # PREFERRED STOCK'LAR İÇİN SADECE L1 STREAMING KULLANILACAK!
            # SNAPSHOT İSTEKLERİ TAMAMEN KALDIRILDI!
            
            for idx, row in self.df.iterrows():
                ticker = row['PREF IBKR']
                
                # Sadece görünür ticker'lar için skorları hesapla
                if ticker not in visible_tickers:
                    continue
                    
                # Tüm hisseler için işle (ETF'ler ayrı panelde)
                # Sadece ETF'leri hariç tut
                etf_list = ["SPY", "TLT", "IEF", "IEI", "PFF", "KRE", "IWM", "SHY", "PGF"]
                if ticker in etf_list:
                    continue
                    
                market_data = self.hammer.get_market_data(ticker)
                
                # Market data'dan değerleri al (sadece streaming'den)
                bid = market_data.get('bid', 0)
                ask = market_data.get('ask', 0)
                last_price = market_data.get('last', 0)
                
                # DataFrame'den prev_close değerini al
                df_prev_close = row.get('prev_close', 0)
                # print(f"[DEBUG] {ticker}: DataFrame'den df_prev_close={df_prev_close}")  # Debug mesajı kaldırıldı
                
                if df_prev_close != 'N/A' and df_prev_close > 0:
                    prev_close = float(df_prev_close)
                    # print(f"[DEBUG] {ticker}: DataFrame'den prev_close kullanılıyor: {prev_close}")  # Debug mesajı kaldırıldı
                else:
                    # Cache'den al (fallback)
                    prev_close = self.get_prev_close_for_symbol(ticker)
                    # print(f"[DEBUG] {ticker}: Cache'den prev_close alındı: {prev_close}")  # Debug mesajı kaldırıldı
                
                # DataFrame'e prev_close kolonunu ekle (zaten var ama güncelle)
                self.df.at[idx, 'prev_close'] = prev_close
                
                # Debug: Streaming veri durumunu kontrol et
                if bid == 0 and ask == 0:
                    # print(f"[SKOR] ⚠️ {ticker} için streaming veri yok (bid={bid}, ask={ask})")
                    continue
                    
                # Benchmark değişimini hesapla
                benchmark_chg = self.get_benchmark_change_for_ticker(ticker)
                benchmark_type = self.get_benchmark_type_for_ticker(ticker)
                
                # Skorları hesapla
                scores = self.calculate_scores(ticker, row, bid, ask, last_price, prev_close, benchmark_chg)
                
                # DataFrame'i güncelle
                for col, value in scores.items():
                    try:
                        # Kolonu ekle (yoksa)
                        if col not in self.df.columns:
                            self.df[col] = 'N/A'
                        self.df.at[idx, col] = value
                        # Debug: İlk 3 ticker için DataFrame'e yazılan değerleri göster
                        # Debug mesajı kapatıldı - performans için
                        # if idx < 3 and col in ['Final_BB_skor', 'Final_SAS_skor']:
                        #     print(f"[DATAFRAME] {ticker}: {col} = {value}")
                    except Exception as e:
                        print(f"[DATAFRAME ERROR] {ticker} - {col}: {e}")
                
                # Benchmark değerlerini güncelle
                self.df.at[idx, 'Benchmark_Type'] = benchmark_type
                self.df.at[idx, 'Benchmark_Chg'] = benchmark_chg
                    
        except Exception as e:
            # Debug mesajı kapatıldı - performans için
            pass
            # print(f"[HATA] Skor güncelleme hatası: {e}")
    
    def calculate_scores_for_all_stocks(self):
        """Tüm hisseler için skorları hesapla"""
        try:
            if not hasattr(self, 'df') or self.df is None:
                # print("[SKOR] ⚠️ DataFrame bulunamadı")
                return
            
            # print("[SKOR] 🔄 Tüm hisseler için skorlar hesaplanıyor...")
            
            for index, row in self.df.iterrows():
                ticker = row['PREF IBKR']
                
                # Market data al (cache'den öncelik ver)
                if self.is_mini450_active:
                    market_data = self.get_cached_market_data(ticker)
                else:
                    market_data = self.hammer.get_market_data(ticker) if hasattr(self, 'hammer') and self.hammer else None
                
                if market_data:
                    bid = float(market_data.get('bid', 0))
                    ask = float(market_data.get('ask', 0))
                    last_price = float(market_data.get('last', 0))
                else:
                    bid = ask = last_price = 0
                
                # Prev close al
                prev_close = self.get_prev_close_for_symbol(ticker)
                
                # Benchmark change al
                benchmark_chg = self.get_benchmark_change_for_ticker(ticker)
                
                # Skorları hesapla
                self.calculate_scores(ticker, row, bid, ask, last_price, prev_close, benchmark_chg)
            
            # print("[SKOR] ✅ Tüm skorlar hesaplandı")
            
        except Exception as e:
            # print(f"[SKOR] ❌ Skor hesaplama hatası: {e}")
            pass
    
    # calculate_scores_for_stock FONKSİYONU KALDIRILDI - YANLIŞ FORMÜLLER VARDI!
    # Artık calculate_scores FONKSİYONU KULLANILIYOR - DOĞRU FORMÜLLER!
    
    def calculate_scores(self, ticker, row, bid, ask, last_price, prev_close, benchmark_chg=0):
        """Ntahaf formüllerine göre skorları hesapla - 800 katsayısı ile final skorlama - Parametre olarak gelen prev_close kullan"""
        try:
            # Parametre olarak gelen prev_close değerini kullan (daha güvenilir!)
            if prev_close <= 0:
                # Fallback: DataFrame'den al
                df_prev_close = row.get('prev_close', 0)
                if df_prev_close != 'N/A' and df_prev_close > 0:
                    prev_close = float(df_prev_close)
                    # Debug mesajı kapatıldı - performans için
                    # print(f"[SKOR] ⚠️ {ticker}: DataFrame'den fallback prev_close={prev_close}")
                else:
                    # Debug mesajı kapatıldı - performans için
                    # print(f"[SKOR] ❌ {ticker}: prev_close bulunamadı! DataFrame={df_prev_close}, Parametre={prev_close}")
                    return None
            
            # Spread hesapla
            spread = float(ask) - float(bid) if ask != 'N/A' and bid != 'N/A' and ask > 0 and bid > 0 else 0
            
            # Passive fiyatlar hesapla (Ntahaf formülleri)
            pf_bid_buy = float(bid) + (spread * 0.15) if bid > 0 else 0
            pf_front_buy = float(last_price) + 0.01 if last_price > 0 else 0
            pf_ask_buy = float(ask) + 0.01 if ask > 0 else 0
            pf_ask_sell = float(ask) - (spread * 0.15) if ask > 0 else 0
            pf_front_sell = float(last_price) - 0.01 if last_price > 0 else 0
            pf_bid_sell = float(bid) - 0.01 if bid > 0 else 0
            
            # Değişimler hesapla (Ntahaf formülleri) - DataFrame'den prev_close kullan
            pf_bid_buy_chg = pf_bid_buy - prev_close if prev_close > 0 else 0
            pf_front_buy_chg = pf_front_buy - prev_close if prev_close > 0 else 0
            pf_ask_buy_chg = pf_ask_buy - prev_close if prev_close > 0 else 0
            pf_ask_sell_chg = pf_ask_sell - prev_close if prev_close > 0 else 0
            pf_front_sell_chg = pf_front_sell - prev_close if prev_close > 0 else 0
            pf_bid_sell_chg = pf_bid_sell - prev_close if prev_close > 0 else 0
            
            # Ucuzluk/Pahalilik skorları (Ntahaf formülleri)
            bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
            front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
            ask_buy_ucuzluk = pf_ask_buy_chg - benchmark_chg
            ask_sell_pahali = pf_ask_sell_chg - benchmark_chg
            front_sell_pahali = pf_front_sell_chg - benchmark_chg
            bid_sell_pahali = pf_bid_sell_chg - benchmark_chg
            
            # Final skorlar (FINAL_THG varsa kullan, yoksa 0)
            final_thg_raw = row.get('FINAL_THG', 0)
            final_thg = float(final_thg_raw) if final_thg_raw != 'N/A' else 0
            
            # Debug: İlk 3 ticker için detaylı bilgi
            if ticker in ['AHL PRE', 'AHL PRD', 'ATH PRD']:
                # print(f"[SKOR DEBUG] {ticker}:")
                # print(f"  prev_close={prev_close}, benchmark_chg={benchmark_chg}")
                # print(f"  pf_bid_buy={pf_bid_buy:.4f}, pf_bid_buy_chg={pf_bid_buy_chg:.4f}")
                # print(f"  bid_buy_ucuzluk={bid_buy_ucuzluk:.4f}")
                # print(f"  FINAL_THG raw={final_thg_raw}, final_thg={final_thg:.2f}")
                # print(f"  final_bb hesaplama: {final_thg:.2f} - 800 * {bid_buy_ucuzluk:.4f} = {final_thg - 800 * bid_buy_ucuzluk:.2f} (800 katsayısı)")
                # print(f"  [800 KATSAYISI] Final skorlama sistemi güncellendi!")
                pass
            
            def final_skor(final_thg, skor):
                """Final skor hesaplama - 800 katsayısı ile"""
                return final_thg - 800 * skor
            
            final_bb = final_skor(final_thg, bid_buy_ucuzluk)
            final_fb = final_skor(final_thg, front_buy_ucuzluk)
            final_ab = final_skor(final_thg, ask_buy_ucuzluk)
            final_as = final_skor(final_thg, ask_sell_pahali)
            final_fs = final_skor(final_thg, front_sell_pahali)
            final_bs = final_skor(final_thg, bid_sell_pahali)
            
            # Yeni Final SAS, Final SFS, Final SBS skorları (SHORT_FINAL kullanarak - çıkarma formülü)
            short_final = float(row.get('SHORT_FINAL', 0)) if row.get('SHORT_FINAL') != 'N/A' else 0
            final_sas = short_final - 800 * ask_sell_pahali if short_final > 0 else 0
            final_sfs = short_final - 800 * front_sell_pahali if short_final > 0 else 0
            final_sbs = short_final - 800 * bid_sell_pahali if short_final > 0 else 0
            
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
                'Final_SAS_skor': round(final_sas, 2),
                'Final_SFS_skor': round(final_sfs, 2),
                'Final_SBS_skor': round(final_sbs, 2),
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
                    'Final_SAS_skor': 0,
                    'Final_SFS_skor': 0,
                    'Final_SBS_skor': 0,
                    'Spread': 0
                }

    def update_live_data(self):
        if not self.live_data_running:
            return
            
        # GUI güncellemesini daha az sıklıkta yap (Allincdata'da)
        if hasattr(self, 'is_mini450_active') and self.is_mini450_active:
            # Allincdata modunda GUI güncellemesini yavaşlat
            self.update_table()
            self.update_scores_with_market_data() # Skorları güncelle
            self.after(3000, self.update_live_data)  # Allincdata'da 3 saniyede bir
        else:
            # Normal modda hızlı güncelleme
            self.update_table()
            self.update_scores_with_market_data() # Skorları güncelle
            self.after(1000, self.update_live_data)  # Normal modda 1 saniyede bir
        
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
            if column in ['FINAL_THG', 'AVG_ADV', 'SMI', 'SHORT_FINAL', 'SMA63 chg', 'SMA246 chg', 'SMA 246 CHG', 'GORT', 'Bid', 'Ask', 'Last', 'Volume']:
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
                    
                    # CSV'den belirli kolonları ekle (SMA63 chg ve SMA246 chg kolonları eklendi)
                    available_columns = [col for col in ['PREF IBKR', 'prev_close', 'CMON', 'CGRUP', 'FINAL_THG', 'AVG_ADV', 'SMI', 'SMA63 chg', 'SMA246 chg', 'SMA 246 CHG', 'SHORT_FINAL'] if col in self.df.columns]
                    
                    # prev_close kolonu kontrolü (janek_ssfinek dosyalarında mevcut olmalı)
                    # Debug mesajları kapatıldı - performans için
                    # if 'prev_close' not in self.df.columns:
                    #     print(f"[UPDATE_TABLE] ⚠️ prev_close kolonu bulunamadı")
                    # else:
                    #     print(f"[UPDATE_TABLE] ✅ prev_close kolonu bulundu")
                    for col in available_columns:
                        value = row_data.get(col, 'N/A')
                        if isinstance(value, (int, float)) and not np.isnan(value):
                            if col in ['SMI']:
                                value = f"{value:.4f}"
                            elif col in ['prev_close']:
                                value = f"{value:.2f}"
                            else:
                                value = f"{value:.2f}"
                        row_values.append(value)
                    
                    # Skor kolonlarını ekle (kendi hesapladığımız)
                    score_columns = [
                        'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
                        'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru',
                        'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor', 'Final_SAS_skor', 'Final_SFS_skor', 'Final_SBS_skor',
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
                    
                    # GORT kolonunu ekle (cache'lenmiş hesaplama)
                    # Önce DataFrame'den kontrol et (daha önce hesaplanmış olabilir)
                    gort_value = None
                    if ticker in self.df['PREF IBKR'].values:
                        ticker_idx = self.df[self.df['PREF IBKR'] == ticker].index[0]
                        if 'GORT' in self.df.columns:
                            existing_gort = self.df.at[ticker_idx, 'GORT']
                            if pd.notna(existing_gort) and existing_gort != 0:
                                gort_value = existing_gort
                    
                    # DataFrame'de yoksa hesapla (cache mekanizması içinde)
                    if gort_value is None:
                        gort_value = self.calculate_gort(ticker)
                        # DataFrame'e de kaydet (sıralama için)
                        if ticker in self.df['PREF IBKR'].values:
                            ticker_idx = self.df[self.df['PREF IBKR'] == ticker].index[0]
                            self.df.at[ticker_idx, 'GORT'] = gort_value if isinstance(gort_value, (int, float)) and not np.isnan(gort_value) else np.nan
                    
                    if isinstance(gort_value, (int, float)) and not np.isnan(gort_value):
                        gort_value = f"{gort_value:.2f}"
                    else:
                        gort_value = 'N/A'
                    row_values.append(gort_value)
                    
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
            
            # Stock Data Manager'ı güncelle - Ana tablo verilerini kaydet
            if not self.df.empty:
                self.stock_data_manager.update_stock_data_from_main_table(self.df, self.columns)
        
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
                            
                            # PREFERRED STOCK'LAR İÇİN SNAPSHOT TAMAMEN KALDIRILDI!
                            # Sadece streaming veri kullanılacak
                            if " PR" in ticker:
                                # print(f"[SKOR] 🚫 SNAPSHOT KALDIRILDI: {ticker} - Sadece streaming kullanılacak!")
                                pass
                            
                            # Benchmark tipini ve değişimini hesapla
                            benchmark_type = self.get_benchmark_type_for_ticker(ticker)
                            benchmark_chg = self.get_benchmark_change_for_ticker(ticker)
                            
                            # Benchmark bilgilerini tabloya yaz
                            if 'Benchmark_Type' in self.columns:
                                self.table.set(item, 'Benchmark_Type', benchmark_type)
                            if 'Benchmark_Chg' in self.columns:
                                self.table.set(item, 'Benchmark_Chg', f"{benchmark_chg:.4f}")
                            
                            # SKORLARI TEKRAR HESAPLAMA KALDIRILDI! DataFrame'de zaten doğru değerler var
                            # from .update_janalldata_with_scores import calculate_scores
                            # scores = calculate_scores(row_data, bid_raw, ask_raw, last_raw, prev_close, benchmark_chg)
                            
                            # TÜM SKORLARI DataFrame'den al (zaten doğru hesaplanmış)
                            all_scores = {
                                'Bid_buy_ucuzluk_skoru': row_data.get('Bid_buy_ucuzluk_skoru', 'N/A'),
                                'Front_buy_ucuzluk_skoru': row_data.get('Front_buy_ucuzluk_skoru', 'N/A'),
                                'Ask_buy_ucuzluk_skoru': row_data.get('Ask_buy_ucuzluk_skoru', 'N/A'),
                                'Ask_sell_pahalilik_skoru': row_data.get('Ask_sell_pahalilik_skoru', 'N/A'),
                                'Front_sell_pahalilik_skoru': row_data.get('Front_sell_pahalilik_skoru', 'N/A'),
                                'Bid_sell_pahalilik_skoru': row_data.get('Bid_sell_pahalilik_skoru', 'N/A'),
                                'Final_BB_skor': row_data.get('Final_BB_skor', 'N/A'),
                                'Final_FB_skor': row_data.get('Final_FB_skor', 'N/A'),
                                'Final_AB_skor': row_data.get('Final_AB_skor', 'N/A'),
                                'Final_AS_skor': row_data.get('Final_AS_skor', 'N/A'),
                                'Final_FS_skor': row_data.get('Final_FS_skor', 'N/A'),
                                'Final_BS_skor': row_data.get('Final_BS_skor', 'N/A'),
                                'Final_SAS_skor': row_data.get('Final_SAS_skor', 'N/A'),
                                'Final_SFS_skor': row_data.get('Final_SFS_skor', 'N/A'),
                                'Final_SBS_skor': row_data.get('Final_SBS_skor', 'N/A'),
                                'Spread': row_data.get('Spread', 'N/A')
                            }
                            
                            # Debug: DataFrame'den alınan değerleri göster
                            if ticker in ['AHL PRE', 'AHL PRD', 'ATH PRD']:
                                # print(f"[DATAFRAME_READ] {ticker}: Final_BB_skor={all_scores['Final_BB_skor']}, Final_SAS_skor={all_scores['Final_SAS_skor']}")
                                pass
                            
                            # TÜM SKORLARI tabloya yaz (DataFrame'den alınan değerler)
                            for score_name, score_value in all_scores.items():
                                if score_name in self.columns:
                                    if isinstance(score_value, (int, float)) and not np.isnan(score_value):
                                        self.table.set(item, score_name, f"{score_value:.2f}")
                                    else:
                                        self.table.set(item, score_name, 'N/A')
                            

                    
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
            
            # CSV'den sadece belirli kolonları al - SMA63 chg ve SMA246 chg kolonları eklendi
            csv_columns_to_show = ['PREF IBKR', 'prev_close', 'CMON', 'CGRUP', 'FINAL_THG', 'AVG_ADV', 'SMI', 'SMA63 chg', 'SMA246 chg', 'SMA 246 CHG', 'SHORT_FINAL']
            
            # Sadece mevcut kolonları al (yoksa hata vermesin)
            available_columns = [col for col in csv_columns_to_show if col in df.columns]
            
            # prev_close kolonu kontrolü (janek_ssfinek dosyalarında mevcut olmalı)
            # Debug mesajları kapatıldı - performans için
            # if 'prev_close' not in df.columns:
            #     print(f"[CSV] ⚠️ prev_close kolonu bulunamadı: {filename}")
            # else:
            #     print(f"[CSV] OK prev_close kolonu bulundu: {filename}")
            
            # Skor kolonları (kendi hesapladığımız)
            score_columns = [
                'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
                'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru',
                'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor', 'Final_SAS_skor', 'Final_SFS_skor', 'Final_SBS_skor',
                'Spread'
            ]
            
            # Benchmark kolonları (kendi hesapladığımız)
            benchmark_columns = ['Benchmark_Type', 'Benchmark_Chg']
            
            # GORT kolonu (hesaplanacak)
            gort_columns = ['GORT']
            
            # Live kolonları (Hammer Pro'dan)
            live_columns = ['Bid', 'Ask', 'Last', 'Volume']
            
            # Toplam kolon sırası
            self.columns = ['Seç'] + available_columns + score_columns + benchmark_columns + gort_columns + live_columns
            
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
                elif col in ['prev_close']:
                    self.table.column(col, width=25, anchor='center')  # prev_close için orta genişlik
                elif col in ['CMON', 'CGRUP']:
                    self.table.column(col, width=15, anchor='center')  # En dar
                elif col in ['SMI', 'SMA63 chg', 'SMA246 chg', 'SMA 246 CHG', 'SHORT_FINAL', 'GORT']:
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
            
            # TÜM PENCERELERDE SKORLARI HESAPLA! (Ana pencere ve grup pencereleri)
            # Debug mesajı kapatıldı - performans için
            # print(f"[CSV] 🔄 {filename}: Skorlar hesaplanıyor...")
            
            # Önce skorları hesapla
            self.calculate_scores_for_all_stocks()
            
            # Şimdi DataFrame'e skor kolonlarını ekle
            # Debug mesajı kapatıldı - performans için
            # print(f"[CSV] 🔄 {filename}: DataFrame'e skor kolonları ekleniyor...")
            
            # Skor kolonları
            score_columns = [
                'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
                'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru',
                'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor', 'Final_SAS_skor', 'Final_SFS_skor', 'Final_SBS_skor',
                'Spread'
            ]
            
            # Her hisse için skorları hesapla ve DataFrame'e ekle
            for index, row in self.df.iterrows():
                ticker = row['PREF IBKR']
                
                # Hammer'dan live verileri al
                market_data = self.hammer.get_market_data(ticker) if hasattr(self, 'hammer') and self.hammer else None
                if market_data:
                    bid_raw = float(market_data.get('bid', 0))
                    ask_raw = float(market_data.get('ask', 0))
                    last_raw = float(market_data.get('last', 0))
                    prev_close = float(market_data.get('prevClose', 0))
                    
                    # Benchmark değişimini hesapla
                    benchmark_chg = self.get_benchmark_change_for_ticker(ticker)
                    
                    # Skorları hesapla - DOĞRU FONKSİYONU KULLAN!
                    scores = self.calculate_scores(ticker, row, bid_raw, ask_raw, last_raw, prev_close, benchmark_chg)
                    
                    # DataFrame'e skorları yaz
                    if scores:
                        for score_name, score_value in scores.items():
                            if score_name in score_columns:
                                self.df.at[index, score_name] = score_value
                
                # GORT değerini hesapla ve DataFrame'e ekle
                gort_value = self.calculate_gort(ticker)
                self.df.at[index, 'GORT'] = gort_value if isinstance(gort_value, (int, float)) and not np.isnan(gort_value) else np.nan
            
            # Debug mesajı kapatıldı - performans için
            # print(f"[CSV] ✅ {filename}: Skorlar hesaplandı ve DataFrame'e eklendi")
                    
            # Sıralama sıfırla
            self.sort_column = None
            self.sort_ascending = True
            
            # _last_visible_tickers'ı sıfırla (yeni dosya yüklendiğinde tablo yeniden çizilsin)
            if hasattr(self, '_last_visible_tickers'):
                delattr(self, '_last_visible_tickers')
                
            self.update_table()
            
            # Başlığı güncelle
            if is_main:
                self.title("janallres - Tüm Veriler")
            else:
                # Dosya adından grup ismini çıkar
                if 'janek_ssfinek' in filename:
                    short_name = filename.replace('janek_ssfinek', '').replace('.csv', '')
                else:
                    short_name = filename.replace('ssfinek', '').replace('.csv', '')
                display_name = get_display_name(short_name)
                self.title(f"janallres - {display_name}")
                
            # Debug mesajları kapatıldı - performans için
            # print(f"[CSV] ✅ {filename} yüklendi")
            # print(f"[CSV] ℹ️ {len(df)} satır")
            # print(f"[CSV] 📋 Mevcut Kolonlar: {', '.join(available_columns)}")
            # print(f"[CSV] 📋 Toplam Kolon Sayısı: {len(self.columns)}")
            
            # Stock Data Manager'ı CSV verileri ile güncelle
            self.stock_data_manager.update_stock_data_from_csv(filename, df)
            
        except Exception as e:
                print(f"[CSV] ERROR Dosya okuma hatasi ({filename}): {e}")
    
    def get_prev_close_for_symbol(self, symbol: str) -> float:
        """Symbol için prev close değerini döndür - cache'den oku"""
        try:
            # Cache'den kontrol et
            if hasattr(self, 'prev_close_cache') and symbol in self.prev_close_cache:
                value = float(self.prev_close_cache[symbol])
                # print(f"[PREV CLOSE] ✓ {symbol}: cache'den prev_close={value}")  # Debug mesajı kaldırıldı
                return value
            
            # ETF Panel'den al
            if hasattr(self, 'etf_panel') and self.etf_panel:
                if symbol in self.etf_panel.etf_prev_close_data:
                    value = float(self.etf_panel.etf_prev_close_data[symbol])
                    # print(f"[PREV CLOSE] ✓ {symbol}: ETF panel'den prev_close={value}")  # Debug mesajı kaldırıldı
                    return value
            
            # print(f"[PREV CLOSE] ❌ {symbol}: prev_close cache'de bulunamadı")  # Debug mesajı kaldırıldı
            # if hasattr(self, 'prev_close_cache'):
            #     print(f"[PREV CLOSE] 📋 Cache'deki ticker'lar: {list(self.prev_close_cache.keys())[:10]}...")  # Debug mesajı kaldırıldı
            # else:
            #     print(f"[PREV CLOSE] 📋 Cache boş!")  # Debug mesajı kaldırıldı
            return 0.0
            
        except Exception as e:
            # print(f"[PREV CLOSE] ❌ {symbol} genel hata: {e}")  # Debug mesajı kaldırıldı
            return 0.0
    
    def get_last_price_for_symbol(self, symbol: str) -> float:
        """Symbol için son fiyatı döndür - PREF IBKR formatını Hammer Pro formatına çevirerek"""
        try:
            # PREF IBKR formatını Hammer Pro formatına çevir
            from .myjdata import get_hammer_symbol_from_pref_ibkr
            hammer_symbol = get_hammer_symbol_from_pref_ibkr(symbol)
            
            # Hammer Pro'dan market data al
            if hasattr(self, 'hammer') and self.hammer:
                market_data = self.hammer.get_market_data(hammer_symbol)
                if market_data and 'last' in market_data:
                    last_price = float(market_data['last'])
                    return last_price
        
            # ETF Panel'den al
            if hasattr(self, 'etf_panel') and self.etf_panel:
                if symbol in self.etf_panel.etf_data:
                    last_price = float(self.etf_panel.etf_data[symbol].get('last', 0))
                    return last_price
        
            return 0.0
        except Exception as e:
            print(f"[MAIN] ❌ {symbol} fiyat alma hatası: {e}")
            return 0.0
    
    def get_final_thg_for_symbol(self, symbol: str) -> float:
        """Symbol için FINAL_THG değerini döndür - janek_ss dosyalarından oku"""
        try:
            # Önce cache'den kontrol et
            if hasattr(self, 'final_thg_data') and symbol in self.final_thg_data:
                return float(self.final_thg_data[symbol])
            
            # janek_ss dosyalarından oku
            import glob
            import pandas as pd
            
            # Tüm janek_ss dosyalarını bul (ana dizinde)
            janek_files = glob.glob('janek_ss*.csv')
            
            for janek_file in janek_files:
                try:
                    # Dosyayı oku
                    df = pd.read_csv(janek_file, encoding='utf-8-sig')
                    
                    # PREF IBKR ve FINAL_THG kolonları var mı kontrol et
                    if 'PREF IBKR' in df.columns and 'FINAL_THG' in df.columns:
                        # Symbol'ü bul
                        row = df[df['PREF IBKR'] == symbol]
                        if not row.empty:
                            final_thg = row['FINAL_THG'].iloc[0]
                            if pd.notna(final_thg):
                                # Cache'e kaydet
                                if not hasattr(self, 'final_thg_data'):
                                    self.final_thg_data = {}
                                self.final_thg_data[symbol] = float(final_thg)
                                print(f"[FINAL_THG] ✓ {symbol}: {final_thg} ({janek_file})")
                                return float(final_thg)
                except Exception as e:
                    print(f"[FINAL_THG] ⚠️ {janek_file} okuma hatası: {e}")
                    continue
            
            print(f"[FINAL_THG] ❌ {symbol}: FINAL_THG bulunamadı")
            return 0.0
            
        except Exception as e:
            print(f"[FINAL_THG] ❌ {symbol} genel hata: {e}")
            return 0.0
    
    def show_order_confirmation(self, title, symbols, scores, order_type, group):
        """Emir onay penceresi - Detaylı bilgilerle"""
        import tkinter as tk
        from tkinter import ttk
        
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("1200x600")
        win.transient(self)  # Modal pencere yap
        win.grab_set()  # Modal pencere yap
        
        # Başlık
        ttk.Label(win, text=f"{title}\n{len(symbols)} stocks selected", 
                 font=('Arial', 12, 'bold')).pack(pady=10)
        
        # Tablo - Detaylı bilgiler (checkbox'lı)
        cols = ['select', 'symbol', 'order_info', 'bid', 'ask', 'spread', 'last', 'score', 'avg_adv', 'maxalw']
        if order_type == "ask_sell":
            headers = ['Seç', 'Symbol', 'Emir Bilgisi', 'Bid', 'Ask', 'Spread', 'Last', 'Final SAS Skor', 'AVG_ADV', 'MAXALW']
        else:
            headers = ['Seç', 'Symbol', 'Emir Bilgisi', 'Bid', 'Ask', 'Spread', 'Last', 'Final BB Skor', 'AVG_ADV', 'MAXALW']
        tree = ttk.Treeview(win, columns=cols, show='headings', height=15)
        
        for c, h in zip(cols, headers):
            tree.heading(c, text=h)
            if c == 'select':
                tree.column(c, width=50, anchor='center')
            elif c == 'symbol':
                tree.column(c, width=100, anchor='center')
            elif c == 'order_info':
                tree.column(c, width=200, anchor='center')
            elif c in ['avg_adv', 'maxalw']:
                tree.column(c, width=80, anchor='center')
            else:
                tree.column(c, width=120, anchor='center')
        
        tree.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Verileri ekle - Detaylı bilgilerle (checkbox'lı)
        # Lot hesaplaması: MAXALW/4 bazında, 200-800 arasında sınırlı
        def calculate_lot_size(maxalw):
            """MAXALW/4 bazında lot hesapla, 200-800 arasında sınırla"""
            if maxalw <= 0:
                return 200  # Default minimum
            
            # MAXALW/4 hesapla
            calculated_lot = maxalw / 4
            
            # 100'lüğe yuvarla
            rounded_lot = round(calculated_lot / 100) * 100
            
            # 200-800 arasında sınırla
            if rounded_lot < 200:
                return 200
            elif rounded_lot > 800:
                return 800
            else:
                return rounded_lot
        
        # Seçili hisseleri takip etmek için
        selected_symbols = []
        symbol_lots = {}  # Her hisse için lot bilgisini sakla
        
        for symbol, score in zip(symbols, scores):
            # Market data al
            market_data = self.hammer.get_market_data(symbol) if hasattr(self, 'hammer') and self.hammer else None
            
            if market_data:
                bid = float(market_data.get('bid', 0))
                ask = float(market_data.get('ask', 0))
                last = float(market_data.get('last', 0))
                spread = ask - bid if ask > 0 and bid > 0 else 0
            else:
                bid = ask = last = spread = 0
            
            # Emir fiyatını hesapla
            if order_type == "bid_buy":
                order_price = bid + spread * 0.15
                order_direction = "BUY"
            else:  # ask_sell
                order_price = ask - spread * 0.15
                order_direction = "SELL"
            
            # AVG_ADV ve MAXALW değerlerini al
            avg_adv = self.get_avg_adv_from_csv(symbol)
            maxalw = avg_adv / 10 if avg_adv > 0 else 0
            
            # Her hisse için MAXALW/4 bazında lot hesapla
            individual_lot = calculate_lot_size(maxalw)
            
            # Debug: Lot hesaplama detayları
            print(f"[LOT CALC] {symbol}: MAXALW={maxalw:.0f}, MAXALW/4={maxalw/4:.0f}, Rounded={individual_lot}")
            
            # Lot bilgisini sakla
            symbol_lots[symbol] = individual_lot
            
            # Emir bilgisi
            order_info = f"{individual_lot} lot {order_direction} @ ${order_price:.2f} (HIDDEN)"
            
            # Varsayılan olarak seçili (✓)
            item = tree.insert('', 'end', values=[
                "✓",  # Seçili
                symbol,
                order_info,
                f"${bid:.2f}" if bid > 0 else "N/A",
                f"${ask:.2f}" if ask > 0 else "N/A",
                f"${spread:.2f}" if spread > 0 else "N/A",
                f"${last:.2f}" if last > 0 else "N/A",
                f"{score:.2f}",
                f"{avg_adv:.0f}",
                f"{maxalw:.0f}"
            ])
            
            # Varsayılan olarak seçili
            selected_symbols.append(symbol)
        
        # Checkbox tıklama fonksiyonu
        def toggle_selection(event):
            region = tree.identify_region(event.x, event.y)
            if region == "cell":
                column = tree.identify_column(event.x)
                if column == "#1":  # Seç kolonu
                    item = tree.identify_row(event.y)
                    if item:
                        values = list(tree.item(item)['values'])
                        if values[0] == "✓":  # Seçili ise
                            values[0] = "☐"  # Seçimi kaldır
                            if values[1] in selected_symbols:
                                selected_symbols.remove(values[1])
                        else:  # Seçili değilse
                            values[0] = "✓"  # Seç
                            if values[1] not in selected_symbols:
                                selected_symbols.append(values[1])
                        tree.item(item, values=values)
        
        # Tablo tıklama olayını bağla
        tree.bind('<Button-1>', toggle_selection)
        
        # Butonlar
        button_frame = ttk.Frame(win)
        button_frame.pack(pady=10)
        
        def save_to_trades_csv():
            """Seçili emirleri trades.csv formatında kaydet"""
            try:
                if not selected_symbols:
                    messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
                    return
                
                print(f"[CSV SAVE] 🔄 {len(selected_symbols)} seçili emir trades.csv'ye kaydediliyor...")
                
                # CSV satırları
                csv_rows = []
                
                for symbol in selected_symbols:
                    # Market data al
                    market_data = self.hammer.get_market_data(symbol) if hasattr(self, 'hammer') and self.hammer else None
                    
                    if market_data:
                        bid = float(market_data.get('bid', 0))
                        ask = float(market_data.get('ask', 0))
                        spread = ask - bid if ask > 0 and bid > 0 else 0
                    else:
                        bid = ask = spread = 0
                    
                    # Emir fiyatını hesapla
                    if order_type == "bid_buy":
                        order_price = bid + spread * 0.15
                        action = "BUY"
                    else:  # ask_sell
                        order_price = ask - spread * 0.15
                        action = "SELL"
                    
                    # Lot miktarını al
                    individual_lot = symbol_lots.get(symbol, 200)
                    
                    # Lot Bölücü aktifse lotları böl
                    if self.lot_divider_enabled:
                        lot_parts = self.divide_lot_size(individual_lot)
                        print(f"[CSV SAVE] 🔄 {symbol}: {individual_lot} lot -> {lot_parts} parçalara bölündü")
                        
                        # Her parça için ayrı CSV satırı oluştur
                        for i, lot_part in enumerate(lot_parts):
                            csv_row = [
                                action,                           # Action: BUY/SELL
                                lot_part,                         # Quantity: Lot miktarı
                                symbol,                           # Symbol: Ticker
                                'STK',                           # SecType: STK
                                'SMART/AMEX',                    # Exchange: SMART/AMEX
                                'USD',                           # Currency: USD
                                'DAY',                           # TimeInForce: DAY
                                'LMT',                           # OrderType: LMT
                                round(order_price, 2),           # LmtPrice: Fiyat
                                'Basket',                        # BasketTag: Basket
                                'U21016730',                     # Account: U21016730
                                'Basket',                        # OrderRef: Basket
                                'TRUE',                          # Hidden: TRUE
                                'TRUE'                           # OutsideRth: TRUE
                            ]
                            csv_rows.append(csv_row)
                    else:
                        # Lot Bölücü kapalıysa normal şekilde tek satır
                        csv_row = [
                            action,                           # Action: BUY/SELL
                            individual_lot,                   # Quantity: Lot miktarı
                            symbol,                           # Symbol: Ticker
                            'STK',                           # SecType: STK
                            'SMART/AMEX',                    # Exchange: SMART/AMEX
                            'USD',                           # Currency: USD
                            'DAY',                           # TimeInForce: DAY
                            'LMT',                           # OrderType: LMT
                            round(order_price, 2),           # LmtPrice: Fiyat
                            'Basket',                        # BasketTag: Basket
                            'U21016730',                     # Account: U21016730
                            'Basket',                        # OrderRef: Basket
                            'TRUE',                          # Hidden: TRUE
                            'TRUE'                           # OutsideRth: TRUE
                        ]
                        csv_rows.append(csv_row)
                    
                    print(f"[CSV SAVE] 📝 {symbol}: {action} {individual_lot} lot @ ${order_price:.2f}")
                
                # CSV dosyasına kaydet (her seferinde yeni dosya)
                import csv
                import os
                
                csv_filename = 'trades.csv'
                
                # Her seferinde yeni dosya oluştur (0'dan yaz)
                with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    
                    # Header yaz
                    csv_headers = ['Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 'Currency', 
                                  'TimeInForce', 'OrderType', 'LmtPrice', 'BasketTag', 'Account', 
                                  'OrderRef', 'Hidden', 'OutsideRth']
                    writer.writerow(csv_headers)
                    
                    # Emirleri yaz
                    writer.writerows(csv_rows)
                
                print(f"[CSV SAVE] ✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                messagebox.showinfo("Başarılı", f"{len(csv_rows)} emir trades.csv'ye kaydedildi!")
                
            except Exception as e:
                print(f"[CSV SAVE] ❌ CSV kaydetme hatası: {e}")
                messagebox.showerror("Hata", f"CSV kaydetme hatası: {e}")
        
        def confirm_order():
            """Seçili emirleri gönder"""
            try:
                if not selected_symbols:
                    print(f"[ORDER] ⚠️ {group}: Hiç hisse seçilmedi!")
                    win.destroy()
                    return
                
                print(f"[ORDER] 🔄 {group}: {len(selected_symbols)} seçili hisse için emirler gönderiliyor...")
                
                for symbol in selected_symbols:
                    # Symbol mapping (PR -> -)
                    hammer_symbol = symbol.replace(" PR", "-")
                    
                    # Market data al
                    market_data = self.hammer.get_market_data(symbol)
                    
                    if order_type == "bid_buy":
                        # Bid buy: bid + spread*0.15
                        if market_data and 'bid' in market_data and 'ask' in market_data:
                            bid = float(market_data['bid'])
                            ask = float(market_data['ask'])
                            spread = ask - bid
                            price = bid + spread * 0.15
                        else:
                            print(f"[ORDER] ⚠️ {symbol}: Bid/Ask fiyatı bulunamadı")
                            continue
                    else:  # ask_sell
                        # Ask sell: ask - spread*0.15
                        if market_data and 'ask' in market_data and 'bid' in market_data:
                            ask = float(market_data['ask'])
                            bid = float(market_data['bid'])
                            spread = ask - bid
                            price = ask - spread * 0.15
                        else:
                            print(f"[ORDER] ⚠️ {symbol}: Ask/Bid fiyatı bulunamadı")
                            continue
                    
                    # Her hisse için hesaplanan lot'u kullan
                    individual_lot = symbol_lots.get(symbol, 200)  # Default 200
                    
                    # Emir gönder (mevcut moda göre)
                    if hasattr(self, 'mode_manager'):
                        success = self.mode_manager.place_order(
                            symbol=hammer_symbol,
                            side="BUY" if order_type == "bid_buy" else "SELL",
                            quantity=individual_lot,
                            price=price,
                            order_type="LIMIT",
                            hidden=True
                        )
                        
                        if success:
                            print(f"[ORDER] ✅ {symbol}: {order_type} emri gönderildi - {individual_lot} lot @ ${price:.2f}")
                        else:
                            print(f"[ORDER] ❌ {symbol}: {order_type} emri gönderilemedi")
                    else:
                        # Fallback to direct hammer
                        self.hammer.place_order(
                            symbol=hammer_symbol,
                            side="BUY" if order_type == "bid_buy" else "SELL",
                            quantity=individual_lot,
                            price=price,
                            order_type="LIMIT"
                        )
                    
                    print(f"[ORDER] ✅ {symbol}: {order_type} emri gönderildi - {individual_lot} lot @ ${price:.2f} (MAXALW/4: {individual_lot})")
                
                print(f"[ORDER] ✅ {group} grubu için {len(selected_symbols)} emir gönderildi")
                win.destroy()
                
            except Exception as e:
                print(f"[ORDER] ❌ Emir gönderme hatası: {e}")
                win.destroy()
        
        def cancel_order():
            """İptal et"""
            print(f"[ORDER] ❌ {group} grubu için emirler iptal edildi")
            win.destroy()
        
        ttk.Button(button_frame, text="Send Selected Orders", command=confirm_order, 
                  style='Accent.TButton').pack(side='left', padx=5)
        ttk.Button(button_frame, text="Save to trades.csv", command=save_to_trades_csv, 
                  style='Accent.TButton').pack(side='left', padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_order).pack(side='left', padx=5)
        
        # Pencere referansını döndür
        return win
    
    def show_positions(self):
        """Mevcut moda göre pozisyonlarım penceresini aç"""
        if self.mode_manager.is_hampro_mode():
            from .mypositions import show_positions_window
            show_positions_window(self, self.get_last_price_for_symbol)
        elif self.mode_manager.is_ibkr_mode():
            from .ibkr_positions import show_ibkr_positions_window
            show_ibkr_positions_window(self, self.get_last_price_for_symbol)
    
    def set_mode(self, mode):
        """Modu değiştir ve GUI'yi güncelle"""
        if self.mode_manager.set_mode(mode):
            self.current_mode = mode
            self.hampro_mode = (mode == "HAMPRO")
            self.ibkr_gun_mode = (mode == "IBKR_GUN")
            self.ibkr_ped_mode = (mode == "IBKR_PED")
            
            # Buton görünümlerini güncelle
            if mode == "HAMPRO":
                self.btn_hampro_mode.configure(style="Accent.TButton")
                self.btn_ibkr_gun_mode.configure(style="TButton")
                self.btn_ibkr_ped_mode.configure(style="TButton")
            elif mode == "IBKR_GUN":
                self.btn_hampro_mode.configure(style="TButton")
                self.btn_ibkr_gun_mode.configure(style="Accent.TButton")
                self.btn_ibkr_ped_mode.configure(style="TButton")
            elif mode == "IBKR_PED":
                self.btn_hampro_mode.configure(style="TButton")
                self.btn_ibkr_gun_mode.configure(style="TButton")
                self.btn_ibkr_ped_mode.configure(style="Accent.TButton")
            
            print(f"[MAIN] 🔄 Mod değiştirildi: {mode}")
            
            # Exposure bilgisini güncelle
            self.update_exposure_display()
            
            # Bağlantı durumlarını kontrol et
            status = self.mode_manager.get_connection_status()
            print(f"[MAIN] 📊 Bağlantı durumları: {status}")
            
            # IBKR moduna geçildiyse bağlantıyı kontrol et
            if mode in ["IBKR_GUN", "IBKR_PED"]:
                # Native IBKR client'i öncelikle bağla
                if not self.ibkr_native.is_connected():
                    print("[MAIN] ⚠️ IBKR Native Gateway'e bağlanılıyor...")
                    if self.ibkr_native.connect_to_ibkr():
                        print("[MAIN] ✅ IBKR Native Gateway bağlantısı başarılı")
                    else:
                        print("[MAIN] ❌ IBKR Native Gateway bağlantısı başarısız")
                else:
                    print("[MAIN] ✅ IBKR Native Gateway zaten bağlı")
                
                # ib_insync client'i de bağla (yedek olarak)
                if not self.ibkr.is_connected():
                    print("[MAIN] ⚠️ IBKR ib_insync Gateway'e bağlanılıyor...")
                    if self.ibkr.connect_to_ibkr():
                        print("[MAIN] ✅ IBKR ib_insync Gateway bağlantısı başarılı")
                    else:
                        print("[MAIN] ❌ IBKR ib_insync Gateway bağlantısı başarısız")
                else:
                    print("[MAIN] ✅ IBKR ib_insync Gateway zaten bağlı")

                # IBKR moduna geçişte befibgun.csv veya befibped.csv günlük kontrol (00:00-16:30)
                if mode == "IBKR_GUN":
                    if not self.befibgun_checked_today:
                        self.check_daily_befib()
                elif mode == "IBKR_PED":
                    if not self.befibped_checked_today:
                        self.check_daily_befib()
    
    def show_take_profit_longs(self):
        """Take Profit Longs penceresini aç - Sadece long pozisyonlar (quantity > 0)"""
        from .take_profit_panel import TakeProfitPanel
        TakeProfitPanel(self, "longs")
    
    def show_take_profit_shorts(self):
        """Take Profit Shorts penceresini aç - Sadece short pozisyonlar (quantity < 0)"""
        from .take_profit_panel import TakeProfitPanel
        TakeProfitPanel(self, "shorts")
    
    def show_lspread(self):
        """L-spread penceresini aç - Spread >= 0.20 olan hisseler"""
        from .lspread_panel import LSpreadPanel
        LSpreadPanel(self)
    
    def show_port_adjuster(self):
        """Port Adjuster penceresini aç"""
        from .port_adjuster import PortAdjusterWindow
        port_window = PortAdjusterWindow(self)
        
        # Stock Data Manager referansını geç
        port_window.set_stock_data_manager(self.stock_data_manager)
        
        # Port Adjuster window referansını döndür (ADDNEWPOS için)
        return port_window
    
    def show_portfolio_comparison(self):
        """Portfolio Comparison penceresini aç"""
        from .portfolio_comparison import PortfolioComparisonWindow
        PortfolioComparisonWindow(self)
    
    def show_my_orders(self):
        """Emirlerim penceresini aç - Mod-aware"""
        # Mevcut moda göre emirleri göster
        if hasattr(self, 'mode_manager'):
            if self.mode_manager.is_hampro_mode():
                print("[MAIN] 🔄 HAMPRO modunda emirler gösteriliyor...")
                # Hammer Pro'dan emirleri göster
                from .myorders import show_orders_window
                show_orders_window(self)
            elif self.mode_manager.is_ibkr_mode():
                print("[MAIN] 🔄 IBKR modunda emirler gösteriliyor...")
                # IBKR'den emirleri göster
                from .ibkr_orders import show_ibkr_orders_window
                show_ibkr_orders_window(self)
            else:
                print("[MAIN] ⚠️ Mod belirlenemedi, HAMPRO kullanılıyor...")
                from .myorders import show_orders_window
                show_orders_window(self)
        else:
            print("[MAIN] ⚠️ Mode manager bulunamadı, HAMPRO kullanılıyor...")
            from .myorders import show_orders_window
            show_orders_window(self)
    
    def reset_trades_csv(self):
        """trades.csv dosyasını sıfırla - yeni işlem başlıyor"""
        try:
            import os
            
            csv_filename = 'trades.csv'
            
            # Dosya varsa sıfırla
            if os.path.exists(csv_filename):
                # Mevcut dosyayı yedekle
                import time
                backup_filename = f'trades_backup_{int(time.time())}.csv'
                os.rename(csv_filename, backup_filename)
                print(f"[CSV RESET] 💾 Mevcut trades.csv yedeklendi: {backup_filename}")
            
            # Yeni boş dosya oluştur (sadece başlıklarla)
            import csv
            csv_headers = ['Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 'Currency', 
                          'TimeInForce', 'OrderType', 'LmtPrice', 'BasketTag', 'Account', 
                          'OrderRef', 'Hidden', 'OutsideRth']
            
            with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(csv_headers)
            
            print(f"[CSV RESET] ✅ trades.csv sıfırlandı, yeni işlem başlıyor")
            
        except Exception as e:
            print(f"[CSV RESET] ❌ CSV sıfırlama hatası: {e}")
    
    def show_mini450_view(self):
        """
        JANALLDATA'daki tüm 450 hisseyi tek sayfada mini görünümde göster.
        Bu sayede tüm hisseler için aynı anda live data request atılabilir.
        """
        try:
            print("🔍 ALLINCDATA GÖRÜNÜMÜ AÇILIYOR...")
            print("=" * 60)
            
            # Allincdata aktif flag'ini set et (performans optimizasyonu için)
            self.is_mini450_active = True
            
            # Arka plan data güncelleme thread'ini başlat
            self.start_background_data_update()
            
            # Hammer Pro bağlantısını kontrol et
            if not hasattr(self, 'hammer') or not self.hammer.connected:
                messagebox.showwarning("Uyarı", "Önce Hammer Pro'ya bağlanın!")
                return
                
            # Live data'nın çalıştığından emin ol
            if not hasattr(self, 'live_data_running') or not self.live_data_running:
                messagebox.showwarning("Uyarı", "Önce Live Data'yı başlatın!")
                return
            
            # JANALLDATA dosyasını yükle
            if not os.path.exists('janalldata.csv'):
                messagebox.showerror("Hata", "janalldata.csv dosyası bulunamadı!")
                return
            
            # Mevcut durumu kaydet
            self.original_items_per_page = self.items_per_page
            self.original_current_page = self.current_page
            
            # CSV'yi yükle
            df = pd.read_csv('janalldata.csv')
            print(f"📊 janallresDATA yüklendi: {len(df)} hisse")
            
            # Tüm hisseleri tek sayfada göstermek için items_per_page'i artır
            self.items_per_page = len(df)  # Tüm hisseleri tek sayfada göster
            self.current_page = 0
            
            # Normal show_file_data mantığını kullan ama mini görünüm için optimize et
            self.show_file_data('janalldata.csv', is_main=True)
            
            # Tablo satır yüksekliğini küçült (mini görünüm)
            self.table.configure(height=25)  # Daha fazla satır göster
            
            # Font boyutunu küçült
            style = ttk.Style()
            style.configure("Mini.Treeview", font=('Arial', 8))  # Küçük font
            style.configure("Mini.Treeview.Heading", font=('Arial', 8, 'bold'))
            self.table.configure(style="Mini.Treeview")
            
            # Kolon genişliklerini küçült
            for col in self.columns:
                if col == 'PREF IBKR':
                    self.table.column(col, width=80)  # Sembol kolonu
                elif col in ['Bid', 'Ask', 'Last']:
                    self.table.column(col, width=50)  # Fiyat kolonları
                elif col == 'SMA63 chg':
                    self.table.column(col, width=45)  # SMA63 chg kolonu
                elif col in ['SMA246 chg', 'SMA 246 CHG']:
                    self.table.column(col, width=50)  # SMA246 chg kolonu
                elif col == 'GORT':
                    self.table.column(col, width=50)  # GORT kolonu
                elif col in ['Final_FB_skor', 'Final_SFS_skor', 'Final_BB_skor']:
                    self.table.column(col, width=60)  # Skor kolonları  
                else:
                    self.table.column(col, width=40)  # Diğer kolonlar
            
            print(f"🔍 Allincdata görünümü aktif: {len(df)} hisse tek sayfada")
            print(f"📡 Tüm hisseler için live data request'leri atılıyor...")
            
            # Başlığı güncelle
            self.title("janallres - Allincdata Görünümü (Tüm Hisseler)")
            
            # Normal buton ekle (çıkış için)
            self.add_normal_view_button()
            
            messagebox.showinfo("Allincdata Aktif", 
                              f"✅ Allincdata görünümü aktif!\n\n"
                              f"📊 {len(df)} hisse tek sayfada gösteriliyor\n"
                              f"📡 Tüm hisseler için live data alınıyor\n"
                              f"🔍 Artık tüm skorlar hesaplanacak!\n\n"
                              f"Normal görünüme dönmek için 'Normal Görünüm' butonuna basın.")
            
        except Exception as e:
            print(f"❌ Allincdata görünümü hatası: {e}")
            messagebox.showerror("Hata", f"Allincdata görünümü hatası: {e}")
            
            # Hata durumunda orijinal duruma dön
            self.restore_normal_view()
    
    def add_normal_view_button(self):
        """Normal görünüme dönmek için buton ekle"""
        if not hasattr(self, 'normal_view_button'):
            # Buton frame'i bul veya oluştur
            if hasattr(self, 'files_frame'):
                files_frame = self.children[list(self.children.keys())[2]]  # files_frame'i bul
                for child in files_frame.winfo_children():
                    if isinstance(child, ttk.Frame):
                        main_frame = child
                        break
                
                # Normal görünüm butonu ekle
                self.normal_view_button = ttk.Button(main_frame, text="🔙 Normal View", 
                                                   command=self.restore_normal_view)
                self.normal_view_button.pack(side='left', padx=5)
    
    def restore_normal_view(self):
        """Normal görünüme geri dön"""
        try:
            # Allincdata flag'ini sıfırla (performans optimizasyonu)
            self.is_mini450_active = False
            
            # Arka plan thread'ini durdur
            self.stop_background_data_update()
            
            # Orijinal değerleri geri yükle
            if hasattr(self, 'original_items_per_page'):
                self.items_per_page = self.original_items_per_page
                self.current_page = self.original_current_page
                
                # Sayfa sayısını yeniden hesapla
                if hasattr(self, 'tickers'):
                    self.total_pages = max(1, (len(self.tickers) + self.items_per_page - 1) // self.items_per_page)
                
                # Tabloyu normale döndür
                self.table.configure(height=15)  # Normal yükseklik
                
                # Font'u normale döndür
                style = ttk.Style()
                style.configure("Treeview", font=('Arial', 9))
                style.configure("Treeview.Heading", font=('Arial', 9, 'bold'))
                self.table.configure(style="Treeview")
                
                # Kolon genişliklerini normale döndür
                for col in self.columns:
                    if col == 'Seç':
                        self.table.column(col, width=30, anchor='center')
                    elif col == 'PREF IBKR':
                        self.table.column(col, width=100, anchor='center')
                    elif col in ['Bid', 'Ask', 'Last', 'Volume']:
                        self.table.column(col, width=70, anchor='center')
                    elif col in ['Final_FB_skor', 'Final_SFS_skor', 'Final_BB_skor', 'Final_AB_skor', 'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor']:
                        self.table.column(col, width=80, anchor='center')
                    elif col == 'SMA63 chg':
                        self.table.column(col, width=60, anchor='center')  # SMA63 chg kolonu
                    elif col in ['SMA246 chg', 'SMA 246 CHG']:
                        self.table.column(col, width=60, anchor='center')  # SMA246 chg kolonu
                    elif col == 'GORT':
                        self.table.column(col, width=60, anchor='center')  # GORT kolonu
                    else:
                        self.table.column(col, width=60, anchor='center')
                
                # Tabloyu güncelle
                self.update_table()
                
                # Normal görünüm butonunu kaldır
                if hasattr(self, 'normal_view_button'):
                    self.normal_view_button.destroy()
                    delattr(self, 'normal_view_button')
                
                # Başlığı güncelle
                self.title("janallres - Normal Görünüm")
                
                print("🔙 Normal görünüme dönüldü")
                
        except Exception as e:
            print(f"❌ Normal görünüme dönüş hatası: {e}")
    
    def start_background_data_update(self):
        """Arka plan data güncelleme thread'ini başlat"""
        if not self.background_update_running:
            self.background_update_running = True
            self.background_update_thread = threading.Thread(
                target=self.background_data_worker, 
                daemon=True
            )
            self.background_update_thread.start()
            print("🔧 Arka plan data güncelleme thread'i başlatıldı")
    
    def stop_background_data_update(self):
        """Arka plan data güncelleme thread'ini durdur"""
        self.background_update_running = False
        if self.background_update_thread:
            print("🔧 Arka plan data güncelleme thread'i durduruluyor...")
    
    def background_data_worker(self):
        """Arka plan thread - data cache güncelleme"""
        while self.background_update_running:
            try:
                if self.is_mini450_active and hasattr(self, 'df') and not self.df.empty:
                    # Allincdata aktifken arka planda data cache'i güncelle
                    for _, row in self.df.iterrows():
                        if not self.background_update_running:
                            break
                            
                        ticker = row.get('PREF IBKR', '')
                        if ticker and hasattr(self, 'hammer') and self.hammer.connected:
                            try:
                                # Market data al ve cache'e koy
                                market_data = self.hammer.get_market_data(ticker)
                                if market_data:
                                    self.background_data_cache[ticker] = {
                                        'market_data': market_data,
                                        'timestamp': time.time()
                                    }
                                
                                # CPU yükünü azaltmak için kısa bekle
                                time.sleep(0.1)
                                
                            except Exception as e:
                                # Sessizce devam et
                                pass
                
                # Arka plan güncellemesi: 5 saniyede bir
                time.sleep(5)
                
            except Exception as e:
                print(f"[BACKGROUND] ❌ Arka plan hatası: {e}")
                time.sleep(5)
        
        print("🔧 Arka plan data güncelleme thread'i durdu")
    
    def get_cached_market_data(self, ticker):
        """Cache'den market data al (3 saniyeden eski değilse)"""
        if ticker in self.background_data_cache:
            cache_entry = self.background_data_cache[ticker]
            age = time.time() - cache_entry['timestamp']
            if age < 3:  # 3 saniyeden yeni ise
                return cache_entry['market_data']
        
        # Cache'de yoksa veya eskiyse normal yoldan al
        if hasattr(self, 'hammer') and self.hammer.connected:
            return self.hammer.get_market_data(ticker)
        return None

    def scan_all_pages_for_scores(self):
        """
        Tüm grup dosyalarının tüm sayfalarını tarayarak skorları hesapla.
        Bu sayede TUMCSV ayarlaması yapılırken gerçek skorlar kullanılabilir.
        Thread kullanarak UI'ı donmadan çalışır.
        """
        try:
            # Thread'de çalıştır
            import threading
            def scan_thread():
                try:
                    print("🚀 TÜM SAYFALAR TARANACAK - SKORLAR HESAPLANACAK!")
                    print("=" * 80)
                    
                    # Hammer Pro bağlantısını kontrol et
                    if not hasattr(self, 'hammer') or not self.hammer.connected:
                        self.after(0, lambda: messagebox.showwarning("Uyarı", "Önce Hammer Pro'ya bağlanın!"))
                        return
                        
                    # Live data'nın çalıştığından emin ol
                    if not hasattr(self, 'live_data_running') or not self.live_data_running:
                        self.after(0, lambda: messagebox.showwarning("Uyarı", "Önce Live Data'yı başlatın!"))
                        return
                    
                    # CSV dosya listesi (grup butonlarındaki dosyalar)
                    csv_files = [
                        'janek_ssfinekheldcilizyeniyedi.csv',
                        'janek_ssfinekheldcommonsuz.csv', 
                        'janek_ssfinekhelddeznff.csv',
                        'janek_ssfinekheldff.csv',
                        'janek_ssfinekheldflr.csv',
                        'janek_ssfinekheldgarabetaltiyedi.csv',
                        'janek_ssfinekheldkuponlu.csv',
                        'janek_ssfinekheldkuponlukreciliz.csv',
                        'janek_ssfinekheldkuponlukreorta.csv',
                        'janek_ssfinekheldnff.csv',
                        'janek_ssfinekheldotelremorta.csv',
                        'janek_ssfinekheldsolidbig.csv',
                        'janek_ssfinekheldtitrekhc.csv',
                        'janek_ssfinekhighmatur.csv',
                        'janek_ssfineknotbesmaturlu.csv',
                        'janek_ssfineknotcefilliquid.csv',
                        'janek_ssfineknottitrekhc.csv',
                        'janek_ssfinekrumoreddanger.csv',
                        'janek_ssfineksalakilliquid.csv',
                        'janek_ssfinekshitremhc.csv'
                    ]
                    
                    progress_msg = f"Toplam {len(csv_files)} grup dosyası taranacak..."
                    print(f"📋 {progress_msg}")
                    
                    # Mevcut durumu kaydet
                    original_df = self.df.copy() if hasattr(self, 'df') else None
                    original_page = self.current_page
                    original_tickers = self.tickers.copy() if hasattr(self, 'tickers') else []
                    
                    total_stocks_scanned = 0
                    total_scores_calculated = 0
                    
                    # Her grup dosyasını tara
                    for file_idx, file_name in enumerate(csv_files):
                        if not os.path.exists(file_name):
                            print(f"⚠️ {file_name} bulunamadı, atlanıyor")
                            continue
                            
                        print(f"\n📊 [{file_idx+1}/{len(csv_files)}] İşleniyor: {file_name}")
                        
                        try:
                            # Dosyayı geçici olarak yükle (görünür hale getirmeden)
                            temp_df = pd.read_csv(file_name)
                            print(f"   ✅ Dosya okundu: {len(temp_df)} hisse")
                            
                            if len(temp_df) == 0:
                                print(f"   ⚠️ Dosya boş, atlanıyor")
                                continue
                            
                            # Geçici olarak bu dosyayı ana dosya yap (skorları hesaplayabilmek için)
                            self.df = temp_df
                            self.tickers = temp_df['PREF IBKR'].tolist()
                            
                            # Sayfa sayısını hesapla 
                            self.total_pages = max(1, (len(self.tickers) + self.items_per_page - 1) // self.items_per_page)
                            
                            print(f"   📄 Toplam {self.total_pages} sayfa taranacak")
                            
                            # Tüm sayfaları tara
                            for page in range(self.total_pages):
                                self.current_page = page
                                visible_tickers = self.get_visible_tickers()
                                
                                print(f"   📄 Sayfa {page+1}/{self.total_pages}: {len(visible_tickers)} hisse")
                                
                                # Bu sayfadaki her hisse için skorları hesapla
                                for ticker in visible_tickers:
                                    total_stocks_scanned += 1
                                    
                                    try:
                                        # CSV'den bu hissenin verilerini al
                                        row_data = temp_df[temp_df['PREF IBKR'] == ticker]
                                        if row_data.empty:
                                            continue
                                            
                                        row = row_data.iloc[0]
                                        
                                        # Market data al (live)
                                        market_data = self.hammer.get_market_data(ticker)
                                        if market_data:
                                            bid_raw = float(market_data.get('bid', 0))
                                            ask_raw = float(market_data.get('ask', 0))
                                            last_raw = float(market_data.get('last', 0))
                                            prev_close = float(market_data.get('prevClose', 0))
                                            
                                            # Benchmark değişimini hesapla
                                            benchmark_chg = self.get_benchmark_change_for_ticker(ticker)
                                            
                                            # Skorları hesapla
                                            scores = self.calculate_scores(ticker, row, bid_raw, ask_raw, last_raw, prev_close, benchmark_chg)
                                            
                                            if scores:
                                                total_scores_calculated += 1
                                                
                                                # DataFrame'e skorları kaydet
                                                idx = temp_df[temp_df['PREF IBKR'] == ticker].index[0]
                                                for score_name, score_value in scores.items():
                                                    temp_df.at[idx, score_name] = score_value
                                                
                                                # İlk 3 hisse için debug bilgisi
                                                if total_scores_calculated <= 3:
                                                    final_fb = scores.get('Final_FB_skor', 'N/A')
                                                    final_sfs = scores.get('Final_SFS_skor', 'N/A')
                                                    print(f"      ✅ {ticker}: Final_FB_skor={final_fb:.2f}, Final_SFS_skor={final_sfs:.2f}")
                                            
                                        else:
                                            print(f"      ⚠️ {ticker}: Market data alınamadı")
                                            
                                    except Exception as e:
                                        print(f"      ❌ {ticker} için skor hesaplama hatası: {e}")
                                        continue
                                
                                # Her 5 sayfada bir ilerleme bilgisi
                                if (page + 1) % 5 == 0:
                                    print(f"   🔄 İlerleme: {page+1}/{self.total_pages} sayfa tamamlandı")
                            
                            # Bu dosyanın güncellenmiş halini kaydet (skorlarla birlikte)
                            temp_df.to_csv(file_name, index=False)
                            print(f"   💾 {file_name} skorlarla güncellendi")
                            
                        except Exception as e:
                            print(f"   ❌ {file_name} işlenirken hata: {e}")
                            continue
                    
                    # Orijinal durumu geri yükle
                    if original_df is not None:
                        self.df = original_df
                        self.tickers = original_tickers
                        self.current_page = original_page
                        self.total_pages = max(1, (len(self.tickers) + self.items_per_page - 1) // self.items_per_page)
                        self.after(0, self.update_table)
                    
                    # Sonuç mesajı
                    result_msg = f"✅ Tarama tamamlandı!\n\nToplam {total_stocks_scanned} hisse taranı\n{total_scores_calculated} skor hesaplandı"
                    print(f"\n{result_msg}")
                    self.after(0, lambda: messagebox.showinfo("Başarılı", result_msg))
                    
                except Exception as e:
                    error_msg = f"Tarama sırasında hata: {e}"
                    print(f"❌ {error_msg}")
                    self.after(0, lambda: messagebox.showerror("Hata", error_msg))
            
            # Thread'i başlat
            thread = threading.Thread(target=scan_thread, daemon=True)
            thread.start()
            
        except Exception as e:
            print(f"❌ Tarama başlatma hatası: {e}")
            messagebox.showerror("Hata", f"Tarama başlatılamadı: {e}")

    def get_avg_adv_from_csv(self, symbol):
        """CSV'den AVG_ADV değerini al"""
        try:
            # CSV dosyalarından AVG_ADV değerini bul
            import glob
            import pandas as pd
            
            # Tüm ssfinek CSV dosyalarını bul
            csv_files = glob.glob('ssfinek*.csv')
            
            for csv_file in csv_files:
                try:
                    # Dosyayı oku
                    df = pd.read_csv(csv_file, encoding='utf-8-sig')
                    
                    # PREF IBKR ve AVG_ADV kolonları var mı kontrol et
                    if 'PREF IBKR' in df.columns and 'AVG_ADV' in df.columns:
                        # Symbol'ü bul
                        row = df[df['PREF IBKR'] == symbol]
                        if not row.empty:
                            avg_adv = row['AVG_ADV'].iloc[0]
                            if pd.notna(avg_adv) and avg_adv != 'N/A':
                                return float(avg_adv)
                except Exception as e:
                    continue
            
            return 0.0
        except:
            return 0.0
    
    def show_stock_data_status(self):
        """Stock Data Manager durumunu göster"""
        try:
            if not hasattr(self, 'stock_data_manager') or not self.stock_data_manager:
                messagebox.showinfo("Durum", "Stock Data Manager henüz başlatılmamış!")
                return
            
            # Durum özetini al
            summary = self.stock_data_manager.get_data_summary()
            
            if summary:
                status_text = f"""Stock Data Manager Durumu:

📊 Toplam Hisse: {summary.get('total_stocks', 0)}
✅ Geçerli Veri: {summary.get('valid_stocks', 0)}
⏰ Süresi Dolmuş: {summary.get('expired_stocks', 0)}
📁 CSV Dosyaları: {', '.join(summary.get('csv_files', []))}
🕐 Son Güncelleme: {time.strftime('%H:%M:%S', time.localtime(summary.get('last_update', 0)))}

💡 Örnek Kullanım:
• Port Adjuster'da "Hisse Veri Çek" butonuna tıklayın
• Hisse sembolü girin (örn: CFG PRE) ve "Ara" butonuna tıklayın
• Final_FB_skor, Final_SFS_skor gibi verileri görebilirsiniz"""
                
                messagebox.showinfo("Stock Data Manager Durumu", status_text)
            else:
                messagebox.showinfo("Durum", "Durum bilgisi alınamadı!")
                
        except Exception as e:
            messagebox.showerror("Hata", f"Durum gösterilirken hata: {e}")
            print(f"[STOCK_DATA_STATUS] ❌ Hata: {e}")
    
    # SNAPSHOT FONKSİYONLARI KALDIRILDI - Artık sadece L1 streaming kullanıyoruz!
    
    def check_daily_befham(self):
        """Günlük befham.csv kontrolü - Sadece 00:00-16:30 arası, günde 1 kez"""
        try:
            # Zaman penceresi: 00:00 - 16:30 (Yerel saat)
            now = datetime.now()
            window_end = now.replace(hour=16, minute=30, second=0, microsecond=0)

            # 16:30 - 23:59 arasında asla çalıştırma
            if now >= window_end:
                return

            # Mevcut befham.csv dosyasını kontrol et
            befpos_file = "befham.csv"
            
            # Eğer bugün için befpos dosyası varsa, tekrar çalıştırma
            if os.path.exists(befpos_file):
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(befpos_file))
                    if mtime.date() == now.date():
                        print(f"[BEFHAM] OK bugun icin mevcut: {befpos_file}")
                        self.befham_checked_today = True
                        return
                except Exception:
                    pass
            
            # Hammer Pro bağlantısı kontrolü
            if not self.hammer or not getattr(self.hammer, 'connected', False):
                print(f"[BEFHAM] WARN Hammer Pro baglantisi yok, befham.csv calistirilamadi")
                return
            
            print(f"[BEFHAM] OK befham.csv calistiriliyor...")
            
            # befham.csv çalıştır
            self.run_befpos_csv()
            self.befham_checked_today = True
            
        except Exception as e:
            print(f"[BEFHAM] ERROR Gunluk kontrol hatasi: {e}")
    
    def run_befpos_csv(self):
        """befham.csv dosyasını çalıştır ve pozisyonları kaydet"""
        try:
            # Hammer Pro'dan pozisyonları al
            positions = self.hammer.get_positions_direct()
            if not positions:
                print("[BEFHAM] WARN Pozisyon verisi alinmadi")
                return
            
            # Pozisyon verilerini DataFrame'e çevir
            position_data = []
            for pos in positions:
                symbol = pos.get('symbol', '')
                qty = pos.get('qty', None)
                if qty is None:
                    qty = pos.get('quantity', 0)
                avg_price = pos.get('avg_cost', None)
                if avg_price is None:
                    avg_price = pos.get('average_price', 0.0)
                market_value = pos.get('market_value', None)
                if market_value is None:
                    try:
                        market_value = float(qty) * float(avg_price)
                    except Exception:
                        market_value = 0.0
                unreal = pos.get('unrealized_pnl', 0.0)
                realized = pos.get('realized_pnl', 0.0)
                position_data.append({
                    'Symbol': symbol,
                    'Quantity': qty,
                    'AveragePrice': avg_price,
                    'MarketValue': market_value,
                    'UnrealizedPnL': unreal,
                    'RealizedPnL': realized,
                    'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            
            # DataFrame oluştur
            df = pd.DataFrame(position_data)
            
            # Dosya adı
            filename = "befham.csv"
            
            # CSV'ye kaydet
            df.to_csv(filename, index=False)
            print(f"[BEFHAM] OK Pozisyonlar kaydedildi: {filename} ({len(position_data)} pozisyon)")
            
        except Exception as e:
            print(f"[BEFHAM] ERROR befham.csv calistirma hatasi: {e}")

    def check_daily_befib(self):
        """Günlük befibgun.csv veya befibped.csv kontrolü - Sadece 00:00-16:30 arası, günde 1 kez"""
        try:
            now = datetime.now()
            window_end = now.replace(hour=16, minute=30, second=0, microsecond=0)
            if now >= window_end:
                return
            
            # Aktif modu kontrol et
            active_account = self.mode_manager.get_active_account()
            if active_account == "IBKR_GUN":
                befib_file = "befibgun.csv"
            elif active_account == "IBKR_PED":
                befib_file = "befibped.csv"
            else:
                return  # IBKR modu değilse çalıştırma
            
            if os.path.exists(befib_file):
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(befib_file))
                    if mtime.date() == now.date():
                        print(f"[BEFIB] OK bugun icin mevcut: {befib_file}")
                        # Mod bazlı flag'i güncelle
                        if active_account == "IBKR_GUN":
                            self.befibgun_checked_today = True
                        elif active_account == "IBKR_PED":
                            self.befibped_checked_today = True
                        return
                except Exception:
                    pass
            # IBKR bağlantısı kontrolü (native veya ib_insync)
            ib_connected = False
            try:
                ib_connected = self.ibkr_native.is_connected() or self.ibkr.is_connected()
            except Exception:
                ib_connected = False
            if not ib_connected:
                print(f"[BEFIB] WARN IBKR baglantisi yok, {befib_file} calistirilamadi")
                return
            print(f"[BEFIB] OK {befib_file} calistiriliyor...")
            self.run_befib_csv()
            # Mod bazlı flag'i güncelle
            if active_account == "IBKR_GUN":
                self.befibgun_checked_today = True
            elif active_account == "IBKR_PED":
                self.befibped_checked_today = True
        except Exception as e:
            print(f"[BEFIB] ERROR Gunluk kontrol hatasi: {e}")

    def run_befib_csv(self):
        """befibgun.csv veya befibped.csv dosyasını çalıştır ve IBKR pozisyonlarını kaydet"""
        try:
            # Aktif modu kontrol et
            active_account = self.mode_manager.get_active_account()
            if active_account == "IBKR_GUN":
                filename = "befibgun.csv"
            elif active_account == "IBKR_PED":
                filename = "befibped.csv"
            else:
                print(f"[BEFIB] WARN Aktif mod IBKR değil: {active_account}")
                return
            
            # IBKR'den pozisyonları al (öncelik: native)
            positions = []
            try:
                if self.ibkr_native.is_connected():
                    positions = self.ibkr_native.get_positions()
            except Exception:
                positions = []
            if not positions:
                try:
                    if self.ibkr.is_connected():
                        positions = self.ibkr.get_positions()
                except Exception:
                    positions = []
            if not positions:
                print(f"[BEFIB] WARN Pozisyon verisi alinmadi")
                return
            position_data = []
            for pos in positions:
                symbol = pos.get('symbol', '')
                qty = pos.get('qty', None)
                if qty is None:
                    qty = pos.get('quantity', 0)
                avg_cost = pos.get('avg_cost', None)
                if avg_cost is None:
                    avg_cost = pos.get('average_price', 0.0)
                market_price = pos.get('market_price', None)
                market_value = pos.get('market_value', None)
                if market_value is None:
                    try:
                        price = market_price if market_price not in (None, 0) else avg_cost
                        market_value = float(qty) * float(price)
                    except Exception:
                        market_value = 0.0
                unreal = pos.get('unrealized_pnl', pos.get('unrealizedPnL', 0.0))
                realized = pos.get('realized_pnl', pos.get('realizedPnL', 0.0))
                position_data.append({
                    'Symbol': symbol,
                    'Quantity': qty,
                    'AveragePrice': avg_cost,
                    'MarketValue': market_value,
                    'UnrealizedPnL': unreal,
                    'RealizedPnL': realized,
                    'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
            df = pd.DataFrame(position_data)
            df.to_csv(filename, index=False)
            print(f"[BEFIB] OK Pozisyonlar kaydedildi: {filename} ({len(position_data)} pozisyon)")
        except Exception as e:
            print(f"[BEFIB] ERROR befib csv calistirma hatasi: {e}")
    
    def start_psfalgo_robot(self):
        """Psfalgo robotunu başlat"""
        try:
            print("[PSFALGO] 🤖 Robot başlatılıyor...")
            
            # Eğer pencere zaten açıksa, önce kapat
            if hasattr(self, 'psfalgo_window') and self.psfalgo_window:
                try:
                    if self.psfalgo_window.winfo_exists():
                        self.psfalgo_window.destroy()
                except:
                    pass
            
            # Robot penceresi oluştur
            self.psfalgo_window = tk.Toplevel(self)
            self.psfalgo_window.title("Passive mgmt Robot - Pozisyon Yönetimi")
            self.psfalgo_window.geometry("1000x700")
            self.psfalgo_window.transient(self)
            
            # Minimize butonu ekle (başlık çubuğuna)
            self.psfalgo_window.attributes('-toolwindow', False)  # Minimize butonunu göster
            
            # Pencere kapatıldığında temizlik yap
            def on_closing():
                self.psfalgo_running = False
                self.psfalgo_window.destroy()
                self.psfalgo_window = None
            
            self.psfalgo_window.protocol("WM_DELETE_WINDOW", on_closing)
            
            # Robot durumu
            self.psfalgo_running = False
            self.psfalgo_positions = {}  # Pozisyon takibi
            self.psfalgo_trades = {}     # Trade takibi (3 saatlik kontrol için)
            self.controller_enabled = False  # Controller modu (ON/OFF)
            self.excluded_tickers = set()  # Excluded ticker'lar (RUNALL ve diğer fonksiyonlar için)
            self.runall_allowed_mode = False  # RUNALL Allowed modu (otomatik onay)
            self.runall_loop_running = False  # RUNALL döngüsü çalışıyor mu
            self.runall_loop_count = 0  # RUNALL döngü sayacı
            
            # Excluded ticker'ları CSV'den yükle
            self.load_excluded_tickers_from_csv()
            
            # Emir cache'i (60 saniyede bir güncellenecek)
            import time
            self.orders_cache = []
            self.orders_cache_time = time.time() - 61  # İlk çağrıda hemen güncellensin
            self.orders_cache_interval = 60  # 60 saniye
            
            # Pozisyonlar için cache
            self.positions_cache = {}  # {account: positions_list}
            self.positions_cache_time = {}  # {account: timestamp}
            
            # GORT hesaplamaları için cache (grup dosyaları ve ortalamalar)
            self.gort_cache = {}  # {symbol: gort_value}
            self.group_avg_cache = {}  # {(group, cgrup, 'sma63' or 'sma246'): avg_value}
            self.group_file_cache = {}  # {group: DataFrame} - Grup dosyalarını cache'le
            self.gort_cache_time = time.time() - 61  # İlk çağrıda hemen güncellensin
            self.gort_cache_interval = 300  # 5 dakika (300 saniye) - Grup dosyaları nadiren değişir
            
            self.setup_psfalgo_ui()
            
            # İlk cache güncellemesini yap (asenkron olarak)
            self.psfalgo_window.after(1000, self.get_cached_orders)  # 1 saniye sonra ilk güncelleme
            
        except Exception as e:
            print(f"[PSFALGO] ❌ Robot başlatma hatası: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Hata", f"Psfalgo robot başlatılamadı: {e}")
    
    def setup_psfalgo_ui(self):
        """Psfalgo robot UI'ını oluştur"""
        # Başlık ve kontrol butonları frame
        title_frame = ttk.Frame(self.psfalgo_window)
        title_frame.pack(fill='x', padx=10, pady=5)
        
        # Başlık
        title_label = ttk.Label(title_frame, text="Passive mgmt Robot - Position Management", 
                               font=("Arial", 14, "bold"))
        title_label.pack(side='left')
        
        # Pencere kontrol butonları (sağ üst)
        window_controls = ttk.Frame(title_frame)
        window_controls.pack(side='right')
        
        # Alta Al (Minimize) butonu
        minimize_btn = ttk.Button(window_controls, text="🗕 Alta Al", width=10,
                                  command=lambda: self.psfalgo_window.iconify())
        minimize_btn.pack(side='left', padx=2)
        
        # Exposure ayarları çerçevesi
        exposure_frame = ttk.LabelFrame(self.psfalgo_window, text="💰 Exposure Settings", padding=10)
        exposure_frame.pack(fill='x', padx=10, pady=5)
        
        # Exposure limit input
        ttk.Label(exposure_frame, text="Exposure Limit ($):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.exposure_limit_var = tk.StringVar(value="1200000")  # Default 1.2M
        ttk.Entry(exposure_frame, textvariable=self.exposure_limit_var, width=15).grid(row=0, column=1, padx=5, pady=5, sticky='w')
        
        # Ortalama hisse fiyatı
        ttk.Label(exposure_frame, text="Average Stock Price ($):").grid(row=0, column=2, padx=5, pady=5, sticky='w')
        self.avg_price_var = tk.StringVar(value="22")  # Default 22
        ttk.Entry(exposure_frame, textvariable=self.avg_price_var, width=10).grid(row=0, column=3, padx=5, pady=5, sticky='w')
        
        # Pot Expo Limit input (yeni)
        ttk.Label(exposure_frame, text="Pot Expo Limit ($):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.pot_expo_limit_var = tk.StringVar(value="1400000")  # Default 1.4M
        ttk.Entry(exposure_frame, textvariable=self.pot_expo_limit_var, width=15).grid(row=1, column=1, padx=5, pady=5, sticky='w')
        
        # Hesaplanan max lot
        self.max_lot_label = ttk.Label(exposure_frame, text="Max Lot: 54,545", font=("Arial", 10, "bold"), foreground='green')
        self.max_lot_label.grid(row=2, column=0, columnspan=4, padx=5, pady=5, sticky='w')
        
        # Pot Max Lot (yeni)
        self.pot_max_lot_label = ttk.Label(exposure_frame, text="Pot Max Lot: 63,636", font=("Arial", 10, "bold"), foreground='purple')
        self.pot_max_lot_label.grid(row=3, column=0, columnspan=4, padx=5, pady=5, sticky='w')
        
        # Defansif/Ofansif eşik bilgisi
        self.threshold_label = ttk.Label(exposure_frame, text="Defensive Threshold: 52,545 lot | Offensive Turn: 50,909 lot", 
                                        font=("Arial", 9), foreground='blue')
        self.threshold_label.grid(row=4, column=0, columnspan=4, padx=5, pady=5, sticky='w')
        
        # Mevcut lot bilgisi
        self.current_lot_label = ttk.Label(exposure_frame, text="Mevcut Lot: 0 | Mode: -", 
                                          font=("Arial", 10, "bold"), foreground='red')
        self.current_lot_label.grid(row=5, column=0, columnspan=4, padx=5, pady=5, sticky='w')
        
        # Değişiklikleri hesapla
        def calculate_exposure():
            try:
                exposure_limit = float(self.exposure_limit_var.get())
                pot_expo_limit = float(self.pot_expo_limit_var.get())
                avg_price = float(self.avg_price_var.get())
                
                max_lot = int(exposure_limit / avg_price)
                pot_max_lot = int(pot_expo_limit / avg_price)
                defensive_threshold = int(max_lot * 0.955)  # %95.5
                offensive_threshold = int(max_lot * 0.927)  # %92.7
                
                self.max_lot_label.config(text=f"Max Lot: {max_lot:,}")
                self.pot_max_lot_label.config(text=f"Pot Max Lot: {pot_max_lot:,}")
                self.threshold_label.config(text=f"Defensive Threshold: {defensive_threshold:,} lot | Offensive Turn: {offensive_threshold:,} lot")
            except ValueError:
                pass
        
        self.exposure_limit_var.trace('w', lambda *args: calculate_exposure())
        self.pot_expo_limit_var.trace('w', lambda *args: calculate_exposure())
        self.avg_price_var.trace('w', lambda *args: calculate_exposure())
        calculate_exposure()
        
        # Kontrol butonları
        control_frame = ttk.Frame(self.psfalgo_window)
        control_frame.pack(fill='x', padx=10, pady=5)
        
        self.start_btn = ttk.Button(control_frame, text="Start Robot", 
                                   command=self.start_psfalgo_monitoring)
        self.start_btn.pack(side='left', padx=5)
        
        self.stop_btn = ttk.Button(control_frame, text="Stop Robot", 
                                  command=self.stop_psfalgo_monitoring, state='disabled')
        self.stop_btn.pack(side='left', padx=5)
        
        # RUNALL butonu
        self.runall_btn = ttk.Button(control_frame, text="▶️ RUNALL", 
                                     command=self.run_all_sequence, 
                                     style='Accent.TButton')
        self.runall_btn.pack(side='left', padx=5)
        
        # RUNALL DURDUR butonu (başlangıçta gizli)
        self.runall_stop_btn = ttk.Button(control_frame, text="⏹️ RUNALL DURDUR", 
                                          command=self.stop_runall_loop, 
                                          style='Danger.TButton',
                                          state='disabled')
        self.runall_stop_btn.pack(side='left', padx=5)
        
        # Allowed checkbox - RUNALL modunda otomatik onay için
        self.runall_allowed_var = tk.BooleanVar(value=False)
        self.runall_allowed_checkbox = ttk.Checkbutton(control_frame, 
                                                       text="✅ Allowed (Otomatik Onay)", 
                                                       variable=self.runall_allowed_var)
        self.runall_allowed_checkbox.pack(side='left', padx=5)
        
        # Lot Bölücü checkbox - RUNALL modunda otomatik Lot Bölücü açma için
        self.runall_lot_divider_var = tk.BooleanVar(value=False)
        self.runall_lot_divider_checkbox = ttk.Checkbutton(control_frame, 
                                                           text="📦 Lot Divider (Auto Open)", 
                                                           variable=self.runall_lot_divider_var)
        self.runall_lot_divider_checkbox.pack(side='left', padx=5)
        
        # Controller butonu (ON/OFF toggle)
        self.controller_btn = ttk.Button(control_frame, text="🎛️ Controller: OFF", 
                                         command=self.toggle_controller, 
                                         style='Accent.TButton')
        self.controller_btn.pack(side='left', padx=5)
        
        # KARBOTU butonu
        self.karbotu_btn = ttk.Button(control_frame, text="🎯 KARBOTU", 
                                     command=self.start_karbotu_automation, 
                                     style='Accent.TButton')
        self.karbotu_btn.pack(side='left', padx=5)
        
        # REDUCEMORE butonu
        self.reducemore_btn = ttk.Button(control_frame, text="📉 REDUCEMORE", 
                                         command=self.start_reducemore_automation, 
                                         style='Accent.TButton')
        self.reducemore_btn.pack(side='left', padx=5)
        
        # Excluder butonu
        self.excluder_btn = ttk.Button(control_frame, text="🚫 Excluder", 
                                       command=self.show_excluder_dialog, 
                                       style='Accent.TButton')
        self.excluder_btn.pack(side='left', padx=5)
        
        # ADDNEWPOS butonu
        self.addnewpos_btn = ttk.Button(control_frame, text="➕ ADDNEWPOS", 
                                        command=self.start_addnewpos_automation, 
                                        style='Accent.TButton')
        self.addnewpos_btn.pack(side='left', padx=5)
        
        # Excluded ticker'ları sakla
        self.excluded_tickers = set()  # Set olarak sakla (hızlı arama için)
        
        # Durum etiketi
        self.status_label = ttk.Label(control_frame, text="Status: Stopped", 
                                     font=("Arial", 10))
        self.status_label.pack(side='right', padx=5)
        
        # Pozisyon tablosu
        table_frame = ttk.Frame(self.psfalgo_window)
        table_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Tablo kolonları
        columns = ('Symbol', 'Current Qty', 'Potential Qty', 'Befday Qty', 'Todays Qty Chg', 'Max Change', 'MAXALW', '3H Change', 'Open Orders', 'Max Add Long', 'Max Add Short', 'Status')
        self.psfalgo_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.psfalgo_tree.heading(col, text=col)
            self.psfalgo_tree.column(col, width=120)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.psfalgo_tree.yview)
        self.psfalgo_tree.configure(yscrollcommand=scrollbar.set)
        
        self.psfalgo_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Log alanı
        log_frame = ttk.LabelFrame(self.psfalgo_window, text="Robot Logs")
        log_frame.pack(fill='x', padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, height=8, width=100)
        log_scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side='left', fill='both', expand=True)
        log_scrollbar.pack(side='right', fill='y')
        
        # İlk pozisyon verilerini yükle
        self.load_psfalgo_positions()
        
        # İlk exposure kontrolünü yap (robot başlamadan önce bile göster)
        try:
            exposure_info = self.check_exposure_limits()
            if exposure_info.get('mode') == 'ERROR':
                self.current_lot_label.config(text="Waiting for connection...", foreground='orange')
        except Exception as e:
            self.log_message(f"⚠️ İlk exposure kontrolü yapılamadı: {e}")
    
    def load_psfalgo_positions(self):
        """Psfalgo için pozisyon verilerini yükle - Aktif moda göre"""
        try:
            # Aktif modu kontrol et
            if hasattr(self, 'mode_manager'):
                active_account = self.mode_manager.get_active_account()
            else:
                if self.hampro_mode:
                    active_account = "HAMPRO"
                elif self.ibkr_gun_mode:
                    active_account = "IBKR_GUN"
                elif self.ibkr_ped_mode:
                    active_account = "IBKR_PED"
                else:
                    active_account = "HAMPRO"
            
            self.log_message(f"🔄 Aktif mod: {active_account} - Pozisyonlar çekiliyor...")
            
            # Aktif hesaptan pozisyonları al
            positions = []
            if active_account in ["IBKR_GUN", "IBKR_PED"]:
                # IBKR mod - IBKR pozisyonlarını al (GUN veya PED)
                if hasattr(self.mode_manager, 'ibkr_native_client') and self.mode_manager.ibkr_native_client.is_connected():
                    positions = self.mode_manager.ibkr_native_client.get_positions()
                    self.log_message(f"✅ IBKR Native'dan {len(positions)} pozisyon alındı ({active_account})")
                elif hasattr(self.mode_manager, 'ibkr_client') and self.mode_manager.ibkr_client.is_connected():
                    positions = self.mode_manager.ibkr_client.get_positions()
                    self.log_message(f"✅ IBKR Client'dan {len(positions)} pozisyon alındı ({active_account})")
                else:
                    self.log_message(f"❌ IBKR bağlantısı yok! ({active_account}) Lütfen önce bağlanın.")
                    return
            else:  # HAMPRO
                # HAMPRO mod - Hammer Pro pozisyonlarını al
                if self.hammer and self.hammer.connected:
                    positions = self.hammer.get_positions_direct()
                    self.log_message(f"✅ HAMPRO'dan {len(positions)} pozisyon alındı")
                    # Debug: Pozisyon yapısını logla
                    if positions:
                        self.log_message(f"🔍 İlk pozisyon örneği: {positions[0]}")
                    else:
                        self.log_message("⚠️ HAMPRO'dan pozisyon döndü ama liste boş!")
                else:
                    self.log_message("❌ HAMPRO bağlantısı yok! Lütfen önce bağlanın.")
                    return
            
            if not positions:
                self.log_message("⚠️ Pozisyon bulunamadı!")
                return
            
            # Pozisyonları DataFrame'e çevir
            position_data = []
            for pos in positions:
                symbol = pos.get('symbol', '') or pos.get('Symbol', '') or pos.get('ticker', '') or pos.get('Ticker', '')
                qty = pos.get('qty', None) or pos.get('quantity', None) or pos.get('Quantity', None) or pos.get('qty', None)
                
                # Debug log
                if not symbol:
                    self.log_message(f"⚠️ Pozisyon'da symbol bulunamadı: {pos}")
                    continue
                
                if qty is None:
                    self.log_message(f"⚠️ {symbol}: qty None, 0 olarak ayarlandı")
                    qty = 0
                
                try:
                    qty_float = float(qty)
                    if qty_float != 0:  # Sadece 0 olmayan pozisyonları ekle
                        position_data.append({
                            'Symbol': symbol,
                            'Quantity': qty_float
                        })
                        self.log_message(f"✅ {symbol}: {qty_float:.0f} lot eklendi")
                except (ValueError, TypeError) as e:
                    self.log_message(f"⚠️ {symbol}: qty parse edilemedi: {qty} - {e}")
                    continue
            
            if not position_data:
                self.log_message("⚠️ Pozisyon verisi parse edilemedi veya tüm pozisyonlar 0!")
                self.log_message(f"🔍 Toplam {len(positions)} pozisyon geldi ama parse edilemedi")
                return
            
            df = pd.DataFrame(position_data)
            
            # Tabloyu temizle
            for item in self.psfalgo_tree.get_children():
                self.psfalgo_tree.delete(item)
            
            # Pozisyonları tabloya ekle
            for _, row in df.iterrows():
                symbol = row['Symbol']
                quantity = row['Quantity']
                
                # Gün başı pozisyonu al (befib/befham'dan)
                befday_qty = self.load_bef_position(symbol)
                
                # Bugünkü değişim hesapla
                todays_qty_chg = quantity - befday_qty
                
                # MAXALW değerini al (AVG_ADV/10)
                maxalw = self.get_maxalw_for_symbol(symbol)
                max_change = int(maxalw * 3 / 4) if maxalw > 0 else 0  # MAXALW*3/4 olarak güncellendi
                
                # Short pozisyonları eksi ile göster
                display_quantity = f"{quantity:.0f}" if quantity >= 0 else f"{quantity:.0f}"
                
                # Açık emirleri kontrol et
                open_orders_count = self.get_open_orders_count(symbol)
                
                # Emir analizi yap
                order_analysis = self.analyze_order_impact(symbol, quantity)
                
                self.psfalgo_tree.insert('', 'end', values=[
                    symbol,
                    display_quantity,
                    f"{order_analysis['potential_position']:.0f}",  # Potansiyel pozisyon
                    f"{befday_qty:.0f}",  # Befday Qty
                    f"{todays_qty_chg:+.0f}",  # Todays Qty Chg (artı/eksi ile)
                    f"{max_change}",  # Max Change (MAXALW*3/4)
                    f"{maxalw:.0f}",  # MAXALW
                    "0",  # 3 saatlik değişim
                    f"{open_orders_count}",  # Açık emir sayısı
                    f"{order_analysis['max_additional_long']:.0f}",  # Max ek long
                    f"{order_analysis['max_additional_short']:.0f}",  # Max ek short
                    "Hazır"
                ])
                
                # Pozisyon verilerini sakla
                self.psfalgo_positions[symbol] = {
                    'quantity': quantity,
                    'befday_qty': befday_qty,
                    'todays_qty_chg': todays_qty_chg,
                    'maxalw': maxalw,
                    'max_change': max_change,
                    'three_hour_change': 0,
                    'last_trade_time': None
                }
            
            self.log_message(f"✅ {len(df)} pozisyon yüklendi")
            
        except Exception as e:
            self.log_message(f"❌ Pozisyon yükleme hatası: {e}")
    
    def get_maxalw_for_symbol(self, symbol):
        """Hisse için MAXALW değerini al (AVG_ADV/10)"""
        try:
            # AVG_ADV değerini al
            avg_adv = self.get_avg_adv_from_csv(symbol)
            
            # MAXALW = AVG_ADV / 10
            maxalw = avg_adv / 10 if avg_adv > 0 else 0
            
            return maxalw
        except Exception as e:
            print(f"[PSFALGO] ❌ {symbol} MAXALW hesaplama hatası: {e}")
            return 0
    
    def load_bef_position(self, symbol):
        """befib veya befham dosyasından gün başı pozisyonu oku"""
        try:
            import pandas as pd
            import os
            
            # Aktif moda göre dosya seç
            if hasattr(self, 'mode_manager'):
                active_account = self.mode_manager.get_active_account()
            else:
                if self.hampro_mode:
                    active_account = "HAMPRO"
                elif self.ibkr_gun_mode:
                    active_account = "IBKR_GUN"
                elif self.ibkr_ped_mode:
                    active_account = "IBKR_PED"
                else:
                    active_account = "HAMPRO"
            
            if active_account == "IBKR_GUN":
                bef_file = "befibgun.csv"
            elif active_account == "IBKR_PED":
                bef_file = "befibped.csv"
            else:  # HAMPRO
                bef_file = "befham.csv"
            
            # Dosya var mı kontrol et
            if not os.path.exists(bef_file):
                print(f"[CONTROLLER] ⚠️ {bef_file} dosyası bulunamadı")
                return 0
            
            # CSV'yi oku
            df = pd.read_csv(bef_file)
            
            # Symbol kolonunu bul (Symbol veya PREF IBKR olabilir)
            symbol_col = None
            if 'Symbol' in df.columns:
                symbol_col = 'Symbol'
            elif 'PREF IBKR' in df.columns:
                symbol_col = 'PREF IBKR'
            
            if symbol_col is None:
                print(f"[CONTROLLER] ⚠️ {bef_file} dosyasında Symbol kolonu bulunamadı")
                return 0
            
            # Quantity kolonunu bul
            qty_col = None
            if 'Quantity' in df.columns:
                qty_col = 'Quantity'
            elif 'qty' in df.columns:
                qty_col = 'qty'
            
            if qty_col is None:
                print(f"[CONTROLLER] ⚠️ {bef_file} dosyasında Quantity kolonu bulunamadı")
                return 0
            
            # Symbol'ü bul
            row = df[df[symbol_col] == symbol]
            if row.empty:
                # Pozisyon yok (0 olarak döndür)
                return 0
            
            # Quantity değerini al
            qty = row[qty_col].iloc[0]
            return float(qty) if pd.notna(qty) else 0
            
        except Exception as e:
            print(f"[CONTROLLER] ❌ {symbol} BEF pozisyon okuma hatası: {e}")
            return 0
    
    def get_open_orders_sum(self, symbol, use_cache=False):
        """Açık emirlerin toplam miktarını hesapla (potansiyel fill)"""
        try:
            # Cache kullanılıyorsa cache'den al, değilse direkt çek
            if use_cache and hasattr(self, 'orders_cache'):
                orders = self.get_cached_orders()
            else:
                # Aktif hesaptan açık emirleri al
                if hasattr(self, 'mode_manager'):
                    active_account = self.mode_manager.get_active_account()
                else:
                    active_account = "HAMPRO" if self.hampro_mode else "IBKR"
                
                orders = []
                if active_account == "IBKR":
                    if hasattr(self.mode_manager, 'ibkr_native_client') and self.mode_manager.ibkr_native_client.is_connected():
                        orders = self.mode_manager.ibkr_native_client.get_open_orders()
                    elif hasattr(self.mode_manager, 'ibkr_client') and self.mode_manager.ibkr_client.is_connected():
                        orders = self.mode_manager.ibkr_client.get_orders_direct()
                else:  # HAMPRO
                    if self.hammer and self.hammer.connected:
                        orders = self.hammer.get_open_orders()
            
            # Symbol'e göre filtrele ve topla
            total_qty = 0
            for order in orders:
                order_symbol = order.get('symbol', '') or order.get('Symbol', '')
                
                # Symbol eşleştirmesi (tam eşleşme veya preferred stock formatı)
                is_match = False
                if order_symbol == symbol:
                    is_match = True
                elif '-' in order_symbol:
                    # Preferred stock formatı: "SYMBOL-A" -> "SYMBOL PRA"
                    base, suffix = order_symbol.split('-', 1)
                    if base == symbol.replace(' PR', '').split()[0]:
                        is_match = True
                elif ' PR' in symbol and order_symbol == symbol.replace(' PR', ''):
                    # Symbol "ABC PRC" ama order "ABC" formatında
                    is_match = True
                
                if is_match:
                    # Remaining quantity kullan (filled değil, kalan miktar)
                    remaining = order.get('remaining', None) or order.get('Remaining', None)
                    qty = order.get('quantity', 0) or order.get('qty', 0) or order.get('Quantity', 0) or 0
                    
                    # Eğer remaining varsa onu kullan (daha doğru)
                    if remaining is not None and remaining > 0:
                        qty = float(remaining)
                    else:
                        qty = float(qty)
                    
                    side = order.get('side', '').upper() or order.get('Side', '').upper() or order.get('action', '').upper() or order.get('Action', '').upper()
                    
                    # Status kontrolü - sadece açık emirleri say
                    status = order.get('status', '').upper() or order.get('Status', '').upper()
                    if status in ['CANCELLED', 'FILLED', 'REJECTED', 'API CANCELLED']:
                        continue  # Bu emirler artık açık değil
                    
                    if side == 'BUY':
                        total_qty += qty
                    elif side == 'SELL':
                        total_qty -= qty
            
            return total_qty
            
        except Exception as e:
            print(f"[CONTROLLER] ❌ {symbol} açık emir toplama hatası: {e}")
            return 0
    
    def check_position_direction_change(self, current_qty, order_side, order_qty, gün_başı_pozisyon=None, open_orders_qty=0):
        """
        Pozisyon türü değişimini kontrol et - Gün başı pozisyon bazında (açık emirler dahil)
        
        Args:
            current_qty: Mevcut pozisyon
            order_side: BUY/SELL
            order_qty: İstenen emir miktarı
            gün_başı_pozisyon: Gün başı pozisyon (befib/befham'dan)
            open_orders_qty: Açık emirler toplamı (potansiyel fill)
        
        Returns: (allowed, adjusted_qty, needs_rounding, reason)
        """
        try:
            # Gün başı pozisyon türü (eğer verilmişse)
            if gün_başı_pozisyon is not None:
                if gün_başı_pozisyon > 0:
                    gün_başı_type = 'LONG'
                elif gün_başı_pozisyon < 0:
                    gün_başı_type = 'SHORT'
                else:
                    gün_başı_type = 'ZERO'
            else:
                gün_başı_type = None
            
            # Mevcut potansiyel pozisyon (açık emirler dahil)
            current_potential = current_qty + open_orders_qty
            
            # Mevcut pozisyon türü
            if current_potential > 0:
                current_type = 'LONG'
            elif current_potential < 0:
                current_type = 'SHORT'
            else:
                current_type = 'ZERO'
            
            # Yeni emir eklendikten sonra potansiyel pozisyon
            if order_side.upper() == 'BUY':
                potential_qty = current_potential + order_qty
            else:  # SELL
                potential_qty = current_potential - order_qty
            
            # Potansiyel pozisyon türü
            if potential_qty > 0:
                potential_type = 'LONG'
            elif potential_qty < 0:
                potential_type = 'SHORT'
            else:
                potential_type = 'ZERO'
            
            # GÜN BAŞI POZİSYON BAZINDA KONTROL (Öncelikli)
            if gün_başı_type is not None:
                if gün_başı_type == 'LONG' and potential_type == 'SHORT':
                    # Gün başı long pozisyon → potansiyel short olmamalı
                    # Emir miktarını mevcut potansiyel pozisyona indir (tam 0'a getir)
                    # current_potential pozitif olmalı ki 0'a getirebilsin
                    if current_potential > 0:
                        adjusted_qty = current_potential  # Tam lot (örn: 247)
                        return False, adjusted_qty, False, f"Gün başı long pozisyon ({gün_başı_pozisyon:.0f}) short'a geçemez - emir {current_potential:.0f} lot'a indirildi (0'a getirmek için)"
                    else:
                        # Zaten short'a geçmiş, emir gönderilemez
                        return False, 0, False, f"Gün başı long pozisyon ({gün_başı_pozisyon:.0f}) zaten short'a geçmiş - emir engellendi"
                
                elif gün_başı_type == 'SHORT' and potential_type == 'LONG':
                    # Gün başı short pozisyon → potansiyel long olmamalı
                    # Emir miktarını mevcut potansiyel pozisyona indir (tam 0'a getir)
                    if current_potential < 0:
                        adjusted_qty = abs(current_potential)  # Tam lot
                        return False, adjusted_qty, False, f"Gün başı short pozisyon ({gün_başı_pozisyon:.0f}) long'a geçemez - emir {abs(current_potential):.0f} lot'a indirildi (0'a getirmek için)"
                    else:
                        # Zaten long'a geçmiş, emir gönderilemez
                        return False, 0, False, f"Gün başı short pozisyon ({gün_başı_pozisyon:.0f}) zaten long'a geçmiş - emir engellendi"
            
            # Mevcut pozisyon bazında kontrol (backup - gün başı bilgisi yoksa)
            if current_type == 'LONG' and potential_type == 'SHORT':
                # Long'dan short'a geçiş engellenmeli
                if current_potential > 0:
                    adjusted_qty = current_potential  # Tam lot (0'a getirmek için)
                    return False, adjusted_qty, False, "Long pozisyon short'a geçemez - emir 0'a getirmek için ayarlandı"
                else:
                    return False, 0, False, "Long pozisyon zaten short'a geçmiş - emir engellendi"
            
            elif current_type == 'SHORT' and potential_type == 'LONG':
                # Short'dan long'a geçiş engellenmeli
                if current_potential < 0:
                    adjusted_qty = abs(current_potential)  # Tam lot (0'a getirmek için)
                    return False, adjusted_qty, False, "Short pozisyon long'a geçemez - emir 0'a getirmek için ayarlandı"
                else:
                    return False, 0, False, "Short pozisyon zaten long'a geçmiş - emir engellendi"
            
            else:
                # Geçiş yok veya 0'dan geçiş (izinli)
                return True, order_qty, True, "Pozisyon türü korunuyor - normal yuvarlama yapılabilir"
                
        except Exception as e:
            print(f"[CONTROLLER] ❌ Pozisyon türü kontrol hatası: {e}")
            return True, order_qty, True, f"Hata: {e}"
    
    def check_maxalw_limits(self, symbol, current_qty, open_orders_qty, new_order_qty, order_side, gün_başı_pozisyon, maxalw):
        """
        MAXALW limitleri kontrolü
        
        Returns: (allowed_qty, reason)
        """
        try:
            # Mevcut potansiyel pozisyon (açık emirler dahil)
            current_potential = current_qty + open_orders_qty
            
            # Yeni emir eklendikten sonra potansiyel pozisyon (BUY/SELL yönüne göre)
            if order_side.upper() == 'BUY':
                potential_position = current_potential + new_order_qty
            else:  # SELL
                potential_position = current_potential - new_order_qty
            
            # Limit 1: Toplam pozisyon MAXALW'yi geçmemeli (abs ile) - emir miktarı ayarlanır
            abs_potential = abs(potential_position)
            current_abs = abs(current_potential)
            
            if abs_potential > maxalw:
                # Limit aşılıyor, ne kadar eklenebilir?
                if current_abs >= maxalw:
                    limit_1_allowed = 0
                    limit_1_reason = f"Toplam pozisyon limiti: Zaten MAXALW'ye ulaştı ({current_abs:.0f} >= {maxalw:.0f}), emir engellendi"
                else:
                    # Kalan kapasite (yönü dikkate alarak)
                    limit_1_allowed = maxalw - current_abs
                    if limit_1_allowed < new_order_qty:
                        limit_1_reason = f"Toplam pozisyon limiti: Emir {new_order_qty} → {limit_1_allowed:.0f} lot'a düşürüldü (MAXALW: {maxalw:.0f}, mevcut: {current_abs:.0f})"
                    else:
                        limit_1_reason = f"Toplam pozisyon limiti OK"
            else:
                # Limit içinde, tam emir miktarı kabul edilebilir (ama diğer limitlere de bakılacak)
                limit_1_allowed = maxalw - current_abs
                if limit_1_allowed > new_order_qty:
                    limit_1_allowed = new_order_qty
                limit_1_reason = f"Toplam pozisyon limiti OK"
            
            # Limit 2: Günlük değişim MAXALW*3/4'ü geçmemeli (abs ile) - emir miktarı ayarlanır
            maxalw_daily_limit = maxalw * 3 / 4
            
            # Mevcut günlük değişim (açık emirler dahil)
            current_daily_change = abs(current_potential - gün_başı_pozisyon)
            
            # Yeni emir eklendikten sonra günlük değişim
            potential_daily_change = abs(potential_position - gün_başı_pozisyon)
            
            if potential_daily_change > maxalw_daily_limit:
                # Limit aşılıyor, ne kadar eklenebilir?
                if current_daily_change >= maxalw_daily_limit:
                    limit_2_allowed = 0
                    limit_2_reason = f"Günlük değişim limiti: Zaten limit dolu ({current_daily_change:.0f} >= {maxalw_daily_limit:.0f}), emir engellendi"
                else:
                    # Kalan günlük değişim hakkı
                    # Emir miktarı öyle ayarlanmalı ki potansiyel değişim limiti aşmasın
                    limit_2_allowed = maxalw_daily_limit - current_daily_change
                    if limit_2_allowed < new_order_qty:
                        limit_2_reason = f"Günlük değişim limiti: Emir {new_order_qty} → {limit_2_allowed:.0f} lot'a düşürüldü (Limit: {maxalw_daily_limit:.0f}, mevcut değişim: {current_daily_change:.0f})"
                    else:
                        limit_2_reason = f"Günlük değişim limiti OK"
            else:
                # Limit içinde, kalan kapasite hesapla
                limit_2_allowed = maxalw_daily_limit - current_daily_change
                if limit_2_allowed > new_order_qty:
                    limit_2_allowed = new_order_qty
                limit_2_reason = f"Günlük değişim limiti OK"
            
            # Limit 3: Ters yönde gün başı pozisyonunu aşmamalı (emir miktarı ayarlanır)
            # Gün başı pozisyonun mutlak değeri
            abs_befday = abs(gün_başı_pozisyon)
            
            # Günlük değişim (işaretli)
            current_daily_change_signed = current_potential - gün_başı_pozisyon
            potential_daily_change_signed = potential_position - gün_başı_pozisyon
            
            # Ters yönde geçiş var mı kontrol et
            if gün_başı_pozisyon > 0 and potential_position < 0:
                # Gün başı long → potansiyel short (ters yön)
                # Emir miktarını ayarla: pozisyonu 0'a getir ama ters yöne geçirme
                # current_potential pozitif olmalı (hala long)
                # Emir miktarı: pozisyonu 0'a getirmek için gereken miktar
                if current_potential > 0:
                    # Pozisyonu 0'a getirmek için gereken miktar
                    limit_3_allowed = current_potential
                    limit_3_reason = f"Ters yön limiti: Emir {new_order_qty} → {limit_3_allowed:.0f} lot'a düşürüldü (pozisyon 0'a getirmek için, gün başı: {abs_befday:.0f})"
                else:
                    # Zaten short'a geçmiş, emir gönderilemez
                    limit_3_allowed = 0
                    limit_3_reason = f"Ters yön limiti: Zaten short'a geçilmiş, emir engellendi (gün başı: {abs_befday:.0f})"
            elif gün_başı_pozisyon < 0 and potential_position > 0:
                # Gün başı short → potansiyel long (ters yön)
                # Emir miktarını ayarla: pozisyonu 0'a getir ama ters yöne geçirme
                # current_potential negatif olmalı (hala short)
                # Emir miktarı: pozisyonu 0'a getirmek için gereken miktar
                if current_potential < 0:
                    # Pozisyonu 0'a getirmek için gereken miktar (abs ile)
                    limit_3_allowed = abs(current_potential)
                    limit_3_reason = f"Ters yön limiti: Emir {new_order_qty} → {limit_3_allowed:.0f} lot'a düşürüldü (pozisyon 0'a getirmek için, gün başı: {abs_befday:.0f})"
                else:
                    # Zaten long'a geçmiş, emir gönderilemez
                    limit_3_allowed = 0
                    limit_3_reason = f"Ters yön limiti: Zaten long'a geçilmiş, emir engellendi (gün başı: {abs_befday:.0f})"
            else:
                # Ters yönde geçiş yok, bu limit geçerli değil
                limit_3_allowed = new_order_qty  # Sınırsız (diğer limitler kontrol edilecek)
                limit_3_reason = f"Ters yön kontrolü gerekmiyor"
            
            # Üç limitten küçük olanı seç
            allowed_qty = min(limit_1_allowed, limit_2_allowed, limit_3_allowed, new_order_qty)
            allowed_qty = max(0, allowed_qty)  # Negatif olamaz
            
            if allowed_qty == 0:
                reason = f"MAXALW limiti: {limit_1_reason} | {limit_2_reason} | {limit_3_reason}"
            elif allowed_qty != new_order_qty:
                reason = f"MAXALW limiti: {limit_1_reason} | {limit_2_reason} | {limit_3_reason} → Emir {new_order_qty} → {allowed_qty} lot'a düşürüldü"
            else:
                reason = f"MAXALW limiti OK: Limit1={limit_1_allowed:.0f}, Limit2={limit_2_allowed:.0f}, Limit3={limit_3_allowed:.0f}"
            
            return allowed_qty, reason
            
        except Exception as e:
            print(f"[CONTROLLER] ❌ MAXALW limit kontrol hatası: {e}")
            import traceback
            traceback.print_exc()
            return 0, f"Hata: {e}"
    
    def check_pot_total_limit(self, symbol, order_side, order_qty):
        """
        Pot Toplam limit kontrolü - Sadece pozisyon arttırma emirleri için
        
        Returns: (adjusted_qty, reason)
        """
        try:
            # Pot Toplam hesapla
            pot_info = self.calculate_potential_total()
            current_pot_total = pot_info.get('pot_total', 0)
            
            # Pot Max Lot hesapla
            pot_expo_limit = float(self.pot_expo_limit_var.get())
            avg_price = float(self.avg_price_var.get())
            pot_max_lot = int(pot_expo_limit / avg_price)
            
            # Bu emir pozisyon arttırma mı? (Emir pozisyon arttırma ise kontrol et)
            # Eğer Pot Toplam + Emir > Pot Max Lot ise, emri düşür
            new_pot_total = current_pot_total + order_qty
            if new_pot_total > pot_max_lot:
                adjusted_qty = max(0, pot_max_lot - current_pot_total)
                reason = f"Pot Toplam limiti: {current_pot_total:,} + {order_qty:,} = {new_pot_total:,} > {pot_max_lot:,} → Emir {order_qty:,} → {adjusted_qty:,} lot'a düşürüldü"
                return adjusted_qty, reason
            
            return order_qty, "Pot Toplam limiti OK"
            
        except Exception as e:
            print(f"[CONTROLLER] ❌ Pot Toplam limit kontrol hatası: {e}")
            import traceback
            traceback.print_exc()
            return order_qty, f"Hata: {e}"
    
    def controller_check_order(self, symbol, order_side, requested_qty):
        """
        Controller ON iken emir kontrolü
        
        Returns: (allowed, adjusted_qty, reason)
        """
        try:
            # Controller kapalıysa kontrol yapma
            if not hasattr(self, 'controller_enabled') or not self.controller_enabled:
                return True, requested_qty, "Controller kapalı"
            
            # Aktif hesaptan mevcut pozisyonu al
            if hasattr(self, 'mode_manager'):
                active_account = self.mode_manager.get_active_account()
            else:
                if self.hampro_mode:
                    active_account = "HAMPRO"
                elif self.ibkr_gun_mode:
                    active_account = "IBKR_GUN"
                elif self.ibkr_ped_mode:
                    active_account = "IBKR_PED"
                else:
                    active_account = "HAMPRO"
            
            # Mevcut pozisyonu bul (cache'lenmiş pozisyonlardan)
            current_qty = 0
            positions = self.get_cached_positions(active_account)
            
            # Symbol'e göre pozisyonu bul
            for pos in positions:
                pos_symbol = pos.get('symbol') or pos.get('Symbol', '')
                if pos_symbol == symbol:
                    current_qty = pos.get('quantity', 0) or pos.get('qty', 0) or 0
                    break
            
            # Açık emirler toplamı (cache'lenmiş emirlerden)
            open_orders_qty = self.get_open_orders_sum(symbol, use_cache=True)
            
            # Gün başı pozisyon
            gün_başı_pozisyon = self.load_bef_position(symbol)
            
            # MAXALW değeri
            maxalw = self.get_maxalw_for_symbol(symbol)
            if maxalw <= 0:
                print(f"[CONTROLLER] ⚠️ {symbol} için MAXALW değeri bulunamadı")
                return True, requested_qty, "MAXALW değeri bulunamadı - kontrol atlandı"
            
            # 1. POZISYON TÜRÜ KONTROLÜ (Gün başı pozisyon bazında, açık emirler dahil)
            pos_allowed, pos_adjusted_qty, needs_rounding, pos_reason = self.check_position_direction_change(
                current_qty, order_side, requested_qty, gün_başı_pozisyon, open_orders_qty
            )
            
            # 2. MAXALW LİMİTLERİ KONTROLÜ
            maxalw_allowed_qty, maxalw_reason = self.check_maxalw_limits(
                symbol, current_qty, open_orders_qty, pos_adjusted_qty, order_side, gün_başı_pozisyon, maxalw
            )
            
            # 3. POT TOPLAM LİMİT KONTROLÜ (sadece pozisyon arttırma emirleri için)
            # Emir pozisyon arttırma mı kontrol et
            is_position_increase = False
            if order_side == 'BUY' and current_qty >= 0:
                # Long pozisyon var veya 0, BUY emri arttırma
                is_position_increase = True
            elif order_side == 'SELL' and current_qty < 0:
                # Short pozisyon var, SELL emri arttırma (short artar)
                is_position_increase = True
            
            pot_allowed_qty = maxalw_allowed_qty
            pot_reason = ""
            if is_position_increase:
                pot_allowed_qty, pot_reason = self.check_pot_total_limit(symbol, order_side, maxalw_allowed_qty)
            
            # 4. FİNAL EMİR MİKTARI
            final_qty = min(pos_adjusted_qty, maxalw_allowed_qty, pot_allowed_qty)
            final_qty = max(0, final_qty)  # Negatif olamaz
            
            # 4. YUVARLAMA KARARI
            if needs_rounding and final_qty == requested_qty:
                # Normal durum: Yuvarlama yapılabilir (KARBOTU/REDUCEMORE kuralları)
                # Burada yuvarlama fonksiyonu çağrılabilir (opsiyonel)
                final_qty = int(final_qty)  # Şimdilik tam sayı
            else:
                # Geçiş durumu: Yuvarlama YOK, tam lot
                final_qty = int(final_qty)  # Tam lot (örn: 330)
            
            # Sonuç
            if final_qty == 0:
                reason_parts = [pos_reason, maxalw_reason]
                if pot_reason:
                    reason_parts.append(pot_reason)
                return False, 0, f"Emir engellendi: {' | '.join(reason_parts)}"
            elif final_qty != requested_qty:
                reason_parts = [pos_reason, maxalw_reason]
                if pot_reason:
                    reason_parts.append(pot_reason)
                return True, final_qty, f"Emir ayarlandı: {requested_qty} → {final_qty} | {' | '.join(reason_parts)}"
            else:
                reason_parts = [pos_reason, maxalw_reason]
                if pot_reason:
                    reason_parts.append(pot_reason)
                return True, final_qty, f"Emir onaylandı: {' | '.join(reason_parts)}"
                
        except Exception as e:
            print(f"[CONTROLLER] ❌ Emir kontrol hatası ({symbol}): {e}")
            import traceback
            traceback.print_exc()
            return True, requested_qty, f"Hata: {e}"
    
    def start_psfalgo_monitoring(self):
        """Psfalgo robotunu başlat"""
        self.psfalgo_running = True
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_label.config(text="Status: Running")
        
        self.log_message("OK Psfalgo robot baslatildi")
        
        # Otomatik: Take Profit Longs akışını başlat
        try:
            self.auto_take_profit_longs_selection()
        except Exception as e:
            self.log_message(f"ERROR TP Longs otomasyonu: {e}")
        
        # Robot döngüsünü başlat
        self.psfalgo_monitoring_loop()
    
    def stop_psfalgo_monitoring(self):
        """Psfalgo robotunu durdur"""
        self.psfalgo_running = False
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_label.config(text="Status: Stopped")
        
        self.log_message("⏹️ Psfalgo robot durduruldu")
    
    def psfalgo_monitoring_loop(self):
        """Psfalgo robot ana döngüsü - Exposure kontrolü ile"""
        if not self.psfalgo_running:
            return
        
        # Pencere hala var mı kontrol et
        if not hasattr(self, 'psfalgo_window') or not self.psfalgo_window:
            return
        
        try:
            # Exposure kontrolü yap
            exposure_info = self.check_exposure_limits()
            current_mode = exposure_info.get('mode', 'UNKNOWN')
            can_add_positions = exposure_info.get('can_add_positions', False)
            
            # Pozisyonları güncelle (emirler cache'den alınacak)
            self.update_psfalgo_positions()
            
            # Pot Toplam kontrolü (Controller ON ise ve 60 saniyede bir)
            if hasattr(self, 'controller_enabled') and self.controller_enabled:
                pot_info = self.calculate_potential_total()
                pot_total = pot_info.get('pot_total', 0)
                pot_max_lot = int(float(self.pot_expo_limit_var.get()) / float(self.avg_price_var.get()))
                
                # ADDNEWPOS butonu durumu
                if current_mode == "OFANSIF" and pot_total < pot_max_lot:
                    if hasattr(self, 'addnewpos_btn'):
                        self.addnewpos_btn.config(state='normal')
                else:
                    if hasattr(self, 'addnewpos_btn'):
                        self.addnewpos_btn.config(state='disabled')
            
            # Mod kontrolü
            if current_mode == "DEFANSIVE":
                self.log_message(f"🛡️ DEFANSIVE MOD: Sadece KARBOTU işlemleri yapılabilir (pozisyon artırma yasak)")
            elif current_mode == "OFANSIF":
                self.log_message(f"⚡ OFANSIF MOD: Hem KARBOTU hem ADDPOS işlemleri yapılabilir")
            else:
                self.log_message(f"🔶 GEÇIŞ MOD: Dikkatli ilerle")
            
            # 60 saniye sonra tekrar çalıştır (Controller ON ise daha sık kontrol)
            # Ama pozisyon güncellemesi cache'den alınacak, bu yüzden daha sık çalışabilir
            interval = 60000 if (hasattr(self, 'controller_enabled') and self.controller_enabled) else 300000
            self.psfalgo_window.after(interval, self.psfalgo_monitoring_loop)
            
        except Exception as e:
            self.log_message(f"❌ Robot döngü hatası: {e}")
            # Hata olsa bile devam et
            if hasattr(self, 'psfalgo_window') and self.psfalgo_window:
                self.psfalgo_window.after(300000, self.psfalgo_monitoring_loop)

    def auto_take_profit_longs_selection(self):
        """Take Profit Longs penceresini aç, filtrele ve Ask Sell onay penceresini hazırla"""
        try:
            from .take_profit_panel import TakeProfitPanel
            panel = TakeProfitPanel(self, "longs")

            def do_select_and_open():
                try:
                    # Table hazır mı? değilse tekrar dene
                    if len(panel.tree.get_children()) == 0 or not hasattr(panel, 'positions') or not panel.positions:
                        panel.win.after(400, do_select_and_open)
                        return
                    # Seçimleri temizle
                    try:
                        panel.deselect_all_positions()
                    except Exception:
                        pass

                    selected_any = False
                    for item in panel.tree.get_children():
                        try:
                            symbol = panel.tree.set(item, 'symbol')
                            qty_str = panel.tree.set(item, 'qty')
                            fbtot_str = panel.tree.set(item, 'fbtot')

                            # Miktar
                            try:
                                qty = float(qty_str)
                            except Exception:
                                qty = 0.0

                            # FBtot (N/A veya boş ise atla)
                            # Fbtot: N/A/boş/0.00 olanları atla
                            try:
                                fbtot_val = float(fbtot_str)
                                if fbtot_val == 0.0:
                                    continue
                            except Exception:
                                continue

                            if qty >= 100 and fbtot_val < 1.60:
                                panel.tree.set(item, 'select', '✓')
                                # Satır değerlerinden avg_cost ve qty'yi alıp sözlüğe yaz
                                values = panel.tree.item(item)['values']
                                try:
                                    avg_cost_str = values[3]
                                    if isinstance(avg_cost_str, str):
                                        avg_cost_clean = avg_cost_str.replace('$', '').replace(',', '').strip()
                                        avg_cost = float(avg_cost_clean) if avg_cost_clean else 0.0
                                    else:
                                        avg_cost = float(avg_cost_str)
                                except Exception:
                                    avg_cost = 0.0
                                panel.selected_positions[symbol] = { 'avg_cost': avg_cost, 'qty': qty }
                                selected_any = True
                        except Exception:
                            continue

                    panel.update_selection_count()

                    if not selected_any:
                        self.log_message("INFO TP Longs: Kriterlere uyan pozisyon bulunamadı (qty>=100, fbtot<1.60)")
                        return

                    # %50 lot ayarla ve Ask Sell onay penceresini aç
                    panel.set_lot_percentage(50)
                    panel.place_orders("Ask Sell")
                except Exception as e:
                    self.log_message(f"ERROR TP Longs secim/ackis: {e}")

            # Panel oluştuktan sonra kısa gecikmeyle çalıştır (UI hazır olsun)
            panel.win.after(600, do_select_and_open)
        except Exception as e:
            self.log_message(f"ERROR TP Longs otomasyon init: {e}")
    
    def check_exposure_limits(self):
        """Exposure limitlerini kontrol et ve modu belirle - AKTİF HESAP bazlı"""
        try:
            # Exposure parametrelerini al
            exposure_limit = float(self.exposure_limit_var.get())
            avg_price = float(self.avg_price_var.get())
            
            # Max lot hesapla
            max_lot = int(exposure_limit / avg_price)
            defensive_threshold = int(max_lot * 0.955)  # %95.5
            offensive_threshold = int(max_lot * 0.927)  # %92.7
            
            # Aktif mod bilgisi
            if hasattr(self, 'mode_manager'):
                active_account = self.mode_manager.get_active_account()
            else:
                if self.hampro_mode:
                    active_account = "HAMPRO"
                elif self.ibkr_gun_mode:
                    active_account = "IBKR_GUN"
                elif self.ibkr_ped_mode:
                    active_account = "IBKR_PED"
                else:
                    active_account = "HAMPRO"
            
            self.log_message(f"📊 Exposure kontrolü başlatıldı - Aktif hesap: {active_account}")
            
            # Aktif hesaptan pozisyonları al
            positions = []
            if active_account == "HAMPRO":
                # HAMPRO mod kontrolü
                if not self.hammer or not self.hammer.connected:
                    self.log_message("⚠️ HAMPRO bağlantısı yok!")
                    self.current_lot_label.config(text="No HAMPRO connection!", foreground='red')
                    return {'mode': 'ERROR', 'can_add_positions': False}
                
                positions = self.hammer.get_positions_direct()
                self.log_message(f"✅ HAMPRO'dan {len(positions)} pozisyon alındı")
                
            elif active_account in ["IBKR_GUN", "IBKR_PED"]:
                # IBKR mod kontrolü (GUN veya PED)
                if hasattr(self.mode_manager, 'ibkr_native_client') and self.mode_manager.ibkr_native_client.is_connected():
                    positions = self.mode_manager.ibkr_native_client.get_positions()
                    self.log_message(f"✅ IBKR Native'dan {len(positions)} pozisyon alındı ({active_account})")
                elif hasattr(self.mode_manager, 'ibkr_client') and self.mode_manager.ibkr_client.is_connected():
                    positions = self.mode_manager.ibkr_client.get_positions()
                    self.log_message(f"✅ IBKR Client'dan {len(positions)} pozisyon alındı ({active_account})")
                else:
                    self.log_message(f"⚠️ IBKR bağlantısı yok! ({active_account})")
                    self.current_lot_label.config(text=f"No IBKR connection! ({active_account})", foreground='red')
                    return {'mode': 'ERROR', 'can_add_positions': False}
            else:
                self.log_message(f"⚠️ Bilinmeyen mod: {active_account}")
                return {'mode': 'ERROR', 'can_add_positions': False}
            
            # Toplam lot hesapla (long pozisyonlar + abs(short pozisyonlar))
            total_lots = 0
            long_lots = 0
            short_lots = 0
            
            # Debug: İlk 3 pozisyonun yapısını göster
            if len(positions) > 0:
                self.log_message(f"🔍 İlk pozisyon örneği: {positions[0]}")
            
            for pos in positions:
                # Önce quantity dene, yoksa qty kullan
                qty_value = pos.get('quantity') or pos.get('qty') or pos.get('Quantity')
                if qty_value is None:
                    self.log_message(f"⚠️ Pozisyon'da qty bulunamadı: {pos}")
                    continue
                
                try:
                    qty = int(float(qty_value))
                except (ValueError, TypeError):
                    self.log_message(f"⚠️ qty parse edilemedi: {qty_value} - {pos}")
                    continue
                
                if qty > 0:
                    long_lots += qty
                elif qty < 0:
                    short_lots += abs(qty)
                
                total_lots += abs(qty)
            
            # Modu belirle
            if total_lots > defensive_threshold:
                mode = "DEFANSIVE"  # Sadece KARBOTU
                mode_color = 'red'
            elif total_lots < offensive_threshold:
                mode = "OFANSIF"  # Hem KARBOTU hem ADDPOS
                mode_color = 'green'
            else:
                mode = "GEÇIŞ"  # Geçiş modu
                mode_color = 'orange'
            
            # Pot Toplam hesapla (Controller ON ise)
            pot_total = 0
            if hasattr(self, 'controller_enabled') and self.controller_enabled:
                pot_info = self.calculate_potential_total()
                pot_total = pot_info.get('pot_total', total_lots)
                self.log_message(f"📊 Pot Toplam: {pot_total:,} lot (Mevcut: {total_lots:,}, Arttırma: {pot_info.get('pot_increase', 0):,}, Azaltma: {pot_info.get('pot_decrease', 0):,})")
            
            # UI güncelle
            if pot_total > 0:
                self.current_lot_label.config(
                    text=f"Hesap: {active_account} | Long: {long_lots:,} | Short: {short_lots:,} | Toplam: {total_lots:,} | Pot Toplam: {pot_total:,} | Mode: {mode}", 
                    foreground=mode_color
                )
            else:
                self.current_lot_label.config(
                    text=f"Hesap: {active_account} | Long: {long_lots:,} | Short: {short_lots:,} | Toplam: {total_lots:,} | Mode: {mode}", 
                    foreground=mode_color
                )
            
            # Detaylı log
            self.log_message(f"💰 Exposure: {total_lots:,} / {max_lot:,} lot ({total_lots/max_lot*100:.1f}%) | Mode: {mode}")
            self.log_message(f"📈 Long: {long_lots:,} lot | Short: {short_lots:,} lot | Toplam: {total_lots:,} lot")
            self.log_message(f"🎯 Eşikler: Defansif={defensive_threshold:,} lot (%95.5) | Ofansif dönüş={offensive_threshold:,} lot (%92.7)")
            
            # Pot Max Lot hesapla
            pot_expo_limit = float(self.pot_expo_limit_var.get())
            pot_max_lot = int(pot_expo_limit / avg_price)
            
            return {
                'mode': mode,
                'total_lots': total_lots,
                'long_lots': long_lots,
                'short_lots': short_lots,
                'max_lot': max_lot,
                'pot_max_lot': pot_max_lot,
                'pot_total': pot_total,
                'defensive_threshold': defensive_threshold,
                'offensive_threshold': offensive_threshold,
                'can_add_positions': (mode == "OFANSIF" or mode == "GEÇIŞ"),
                'active_account': active_account
            }
            
        except Exception as e:
            self.log_message(f"❌ Exposure kontrol hatası: {e}")
            import traceback
            self.log_message(f"❌ Traceback: {traceback.format_exc()}")
            return {'mode': 'ERROR', 'can_add_positions': False}
    
    def update_psfalgo_positions(self):
        """Psfalgo pozisyonlarını güncelle - Aktif mod için"""
        try:
            # Aktif modu kontrol et
            if hasattr(self, 'mode_manager'):
                active_account = self.mode_manager.get_active_account()
            else:
                if self.hampro_mode:
                    active_account = "HAMPRO"
                elif self.ibkr_gun_mode:
                    active_account = "IBKR_GUN"
                elif self.ibkr_ped_mode:
                    active_account = "IBKR_PED"
                else:
                    active_account = "HAMPRO"
            
            # Aktif moda göre pozisyonları al
            if active_account in ["IBKR_GUN", "IBKR_PED"]:
                # IBKR pozisyonlarını al (GUN veya PED)
                if hasattr(self.mode_manager, 'ibkr_native_client') and self.mode_manager.ibkr_native_client.is_connected():
                    current_positions = self.mode_manager.ibkr_native_client.get_positions()
                elif hasattr(self.mode_manager, 'ibkr_client') and self.mode_manager.ibkr_client.is_connected():
                    current_positions = self.mode_manager.ibkr_client.get_positions()
                else:
                    current_positions = []
            else:  # HAMPRO
                # HAMPRO pozisyonlarını al
                if self.hammer and self.hammer.connected:
                    current_positions = self.hammer.get_positions_direct()
                    self.log_message(f"🔄 update_psfalgo_positions: {len(current_positions)} pozisyon alındı")
                    if current_positions:
                        self.log_message(f"🔍 update_psfalgo_positions: İlk pozisyon örneği: {current_positions[0]}")
                else:
                    current_positions = []
                    self.log_message("❌ update_psfalgo_positions: HAMPRO bağlantısı yok!")
            
            if not current_positions:
                self.log_message("⚠️ update_psfalgo_positions: Pozisyon bulunamadı!")
                return
            
            # Pozisyonları güncelle
            for pos in current_positions:
                symbol = pos.get('symbol', '') or pos.get('Symbol', '')
                current_qty = pos.get('quantity', None) or pos.get('qty', None) or pos.get('Quantity', 0)
                if current_qty is None:
                    current_qty = 0
                
                if symbol in self.psfalgo_positions:
                    old_qty = self.psfalgo_positions[symbol]['quantity']
                    change = current_qty - old_qty
                    
                    # Eğer değişim varsa, kontrolleri yap
                    if change != 0:
                        # Pozisyon değişim türünü belirle
                        change_type, change_amount = self.determine_position_change_type(symbol, old_qty, current_qty)
                        
                        # MAXALW limitini kontrol et
                        maxalw_ok, maxalw_msg = self.check_maxalw_limit(symbol, change_type, change_amount)
                        
                        # 3 saatlik limiti kontrol et
                        three_hour_ok, three_hour_msg = self.check_three_hour_limit(symbol, change_amount)
                        
                        # Log mesajları
                        self.log_message(f"📊 {symbol}: {change_type} ({change_amount:+.0f})")
                        self.log_message(f"   MAXALW: {maxalw_msg}")
                        self.log_message(f"   3H: {three_hour_msg}")
                        
                        # Eğer limitler aşıldıysa uyarı ver
                        if not maxalw_ok or not three_hour_ok:
                            self.log_message(f"⚠️ {symbol} LİMİT AŞILDI!")
                    
                    # Pozisyon değişimini kaydet
                    self.psfalgo_positions[symbol]['quantity'] = current_qty
                    self.psfalgo_positions[symbol]['three_hour_change'] += change
                    
                    # Tabloyu güncelle
                    self.update_psfalgo_table_row(symbol, current_qty, change)
                    
                    # Açık emirleri kontrol et ve logla
                    open_orders_count = self.get_open_orders_count(symbol)
                    if open_orders_count > 0:
                        self.log_message(f"📋 {symbol}: {open_orders_count} açık emir mevcut")
                    
                    # Emir analizi yap ve logla
                    order_analysis = self.analyze_order_impact(symbol, current_qty)
                    if order_analysis['long_increase_orders'] > 0 or order_analysis['long_decrease_orders'] > 0 or order_analysis['short_increase_orders'] > 0 or order_analysis['short_decrease_orders'] > 0:
                        self.log_message(f"📊 {symbol} Emir Analizi:")
                        self.log_message(f"   Long Artırma: {order_analysis['long_increase_orders']}")
                        self.log_message(f"   Long Azaltma: {order_analysis['long_decrease_orders']}")
                        self.log_message(f"   Short Artırma: {order_analysis['short_increase_orders']}")
                        self.log_message(f"   Short Azaltma: {order_analysis['short_decrease_orders']}")
                        self.log_message(f"   Potansiyel Pozisyon: {order_analysis['potential_position']}")
                        self.log_message(f"   Max Ek Long: {order_analysis['max_additional_long']}")
                        self.log_message(f"   Max Ek Short: {order_analysis['max_additional_short']}")
                        
                        # MAXALW kontrolü
                        maxalw = self.get_maxalw_for_symbol(symbol)
                        if abs(order_analysis['potential_position']) > maxalw:
                            self.log_message(f"⚠️ {symbol} MAXALW AŞILDI! Potansiyel: {abs(order_analysis['potential_position'])} > {maxalw}")
                    
        except Exception as e:
            self.log_message(f"❌ Pozisyon güncelleme hatası: {e}")
    
    def update_psfalgo_table_row(self, symbol, quantity, change):
        """Psfalgo tablosundaki satırı güncelle"""
        try:
            for item in self.psfalgo_tree.get_children():
                values = self.psfalgo_tree.item(item)['values']
                if values[0] == symbol:
                    # Satırı güncelle
                    new_values = list(values)
                    
                    # Gün başı pozisyonu al
                    befday_qty = self.psfalgo_positions[symbol].get('befday_qty', 0)
                    if befday_qty == 0:
                        befday_qty = self.load_bef_position(symbol)
                        self.psfalgo_positions[symbol]['befday_qty'] = befday_qty
                    
                    # Bugünkü değişim hesapla
                    todays_qty_chg = quantity - befday_qty
                    self.psfalgo_positions[symbol]['todays_qty_chg'] = todays_qty_chg
                    
                    # Short pozisyonları eksi ile göster
                    if quantity < 0:
                        new_values[1] = f"{quantity:.0f}"  # Current Qty
                    else:
                        new_values[1] = f"{quantity:.0f}"
                    
                    # Emir analizi yap
                    order_analysis = self.analyze_order_impact(symbol, quantity)
                    new_values[2] = f"{order_analysis['potential_position']:.0f}"  # Potansiyel pozisyon
                    new_values[3] = f"{befday_qty:.0f}"  # Befday Qty
                    new_values[4] = f"{todays_qty_chg:+.0f}"  # Todays Qty Chg
                    
                    # Max Change güncelle (MAXALW*3/4)
                    maxalw = self.psfalgo_positions[symbol]['maxalw']
                    max_change = int(maxalw * 3 / 4) if maxalw > 0 else 0
                    new_values[5] = f"{max_change}"  # Max Change
                    new_values[6] = f"{maxalw:.0f}"  # MAXALW
                    
                    new_values[7] = f"{self.psfalgo_positions[symbol]['three_hour_change']:.0f}"  # 3H Change
                    
                    # Açık emirleri güncelle
                    open_orders_count = self.get_open_orders_count(symbol)
                    new_values[8] = f"{open_orders_count}"  # Open Orders
                    
                    new_values[9] = f"{order_analysis['max_additional_long']:.0f}"  # Max ek long
                    new_values[10] = f"{order_analysis['max_additional_short']:.0f}"  # Max ek short
                    
                    # Durum kontrolü
                    max_change = self.psfalgo_positions[symbol]['max_change']
                    three_hour_change = abs(self.psfalgo_positions[symbol]['three_hour_change'])
                    
                    # Potansiyel pozisyon MAXALW kontrolü
                    maxalw = self.psfalgo_positions[symbol]['maxalw']
                    potential_position = order_analysis['potential_position']
                    
                    # Gün başı pozisyon türü kontrolü
                    befday_qty = self.psfalgo_positions[symbol].get('befday_qty', 0)
                    position_type_violation = False
                    if befday_qty > 0 and potential_position < 0:
                        position_type_violation = True
                    elif befday_qty < 0 and potential_position > 0:
                        position_type_violation = True
                    
                    if position_type_violation:
                        new_values[11] = "⚠️ Pozisyon Türü İhlali"
                    elif abs(potential_position) > maxalw:
                        new_values[11] = "⚠️ MAXALW Aşıldı"
                    elif three_hour_change > max_change:
                        new_values[11] = "⚠️ 3H Limit Aşıldı"
                    else:
                        new_values[11] = "✅ Normal"
                    
                    self.psfalgo_tree.item(item, values=new_values)
                    break
                    
        except Exception as e:
            self.log_message(f"❌ Tablo güncelleme hatası: {e}")
    
    def get_cached_orders(self):
        """Cache'lenmiş emirleri al veya güncelle (60 saniyede bir)"""
        try:
            import time
            current_time = time.time()
            
            # Cache süresi dolmuş mu kontrol et (60 saniye)
            if current_time - self.orders_cache_time > self.orders_cache_interval:
                # Cache'i güncelle
                if hasattr(self, 'mode_manager'):
                    self.orders_cache = self.mode_manager.get_orders()
                    self.orders_cache_time = current_time
                    print(f"[PSFALGO] 🔄 Emir cache güncellendi ({len(self.orders_cache)} emir)")
                else:
                    self.orders_cache = []
            
            return self.orders_cache
        except Exception as e:
            print(f"[PSFALGO] ❌ Emir cache hatası: {e}")
            return []
    
    def get_cached_positions(self, active_account=None):
        """Cache'lenmiş pozisyonları döndür (60 saniye cache)"""
        try:
            import time
            current_time = time.time()
            
            # Aktif hesabı belirle
            if active_account is None:
                if hasattr(self, 'mode_manager'):
                    active_account = self.mode_manager.get_active_account()
                else:
                    if self.hampro_mode:
                        active_account = "HAMPRO"
                    elif self.ibkr_gun_mode:
                        active_account = "IBKR_GUN"
                    elif self.ibkr_ped_mode:
                        active_account = "IBKR_PED"
                    else:
                        active_account = "HAMPRO"
            
            # Cache key'i aktif hesaba göre
            cache_key = active_account
            
            # Cache yoksa veya süresi dolmuşsa yenile
            if cache_key not in getattr(self, 'positions_cache', {}) or \
               cache_key not in getattr(self, 'positions_cache_time', {}) or \
               (current_time - self.positions_cache_time.get(cache_key, 0)) > self.orders_cache_interval:  # Aynı interval (60 saniye)
                
                # Cache dict'leri oluştur
                if not hasattr(self, 'positions_cache'):
                    self.positions_cache = {}
                if not hasattr(self, 'positions_cache_time'):
                    self.positions_cache_time = {}
                
                # Cache'i güncelle
                self.positions_cache[cache_key] = []
                self.positions_cache_time[cache_key] = current_time
                
                # Aktif moda göre pozisyonları çek
                if active_account in ["IBKR_GUN", "IBKR_PED"]:
                    if hasattr(self.mode_manager, 'ibkr_native_client') and self.mode_manager.ibkr_native_client.is_connected():
                        self.positions_cache[cache_key] = self.mode_manager.ibkr_native_client.get_positions()
                    elif hasattr(self.mode_manager, 'ibkr_client') and self.mode_manager.ibkr_client.is_connected():
                        self.positions_cache[cache_key] = self.mode_manager.ibkr_client.get_positions()
                else:  # HAMPRO
                    if self.hammer and self.hammer.connected:
                        self.positions_cache[cache_key] = self.hammer.get_positions_direct()
            
            return self.positions_cache.get(cache_key, [])
        except Exception as e:
            print(f"[PSFALGO] ❌ Pozisyon cache hatası: {e}")
            return []
    
    def get_open_orders_count(self, symbol):
        """Belirli bir sembol için açık emir sayısını döndür"""
        try:
            # Cache'lenmiş emirleri al
            orders = self.get_cached_orders()
            if not orders:
                return 0
            
            # Symbol için açık emirleri say
            count = 0
            for order in orders:
                order_symbol = order.get('symbol', '')
                # Symbol eşleştirmesi (display symbol ile)
                if order_symbol == symbol:
                    count += 1
                # Alternatif eşleştirme (base symbol ile)
                elif '-' in order_symbol:
                    base_symbol = order_symbol.split('-')[0]
                    if base_symbol == symbol.replace(' PR', ''):
                        count += 1
            
            return count
            
        except Exception as e:
            self.log_message(f"❌ Açık emir kontrol hatası ({symbol}): {e}")
            return 0
    
    def calculate_potential_total(self):
        """
        Pot Toplam hesapla: Mevcut pozisyon + Açık emirler (arttırma - azaltma)
        
        Returns:
            dict: {
                'current_total': int,      # Mevcut toplam lot (ABS)
                'pot_total': int,          # Potansiyel toplam lot (ABS)
                'pot_increase': int,       # Potansiyel arttırma emirleri toplamı
                'pot_decrease': int,       # Potansiyel azaltma emirleri toplamı
                'by_symbol': dict          # Her hisse için detay
            }
        """
        try:
            # Aktif modu kontrol et
            if hasattr(self, 'mode_manager'):
                active_account = self.mode_manager.get_active_account()
            else:
                if self.hampro_mode:
                    active_account = "HAMPRO"
                elif self.ibkr_gun_mode:
                    active_account = "IBKR_GUN"
                elif self.ibkr_ped_mode:
                    active_account = "IBKR_PED"
                else:
                    active_account = "HAMPRO"
            
            # Mevcut pozisyonları al
            positions = []
            if active_account == "HAMPRO":
                if self.hammer and self.hammer.connected:
                    positions = self.hammer.get_positions_direct()
            elif active_account in ["IBKR_GUN", "IBKR_PED"]:
                if hasattr(self.mode_manager, 'ibkr_native_client') and self.mode_manager.ibkr_native_client.is_connected():
                    positions = self.mode_manager.ibkr_native_client.get_positions()
                elif hasattr(self.mode_manager, 'ibkr_client') and self.mode_manager.ibkr_client.is_connected():
                    positions = self.mode_manager.ibkr_client.get_positions()
            
            # Açık emirleri al (cache'den)
            orders = self.get_cached_orders()
            
            # Gün başı pozisyonları yükle (tüm semboller için)
            bef_positions = {}
            for pos in positions:
                symbol = pos.get('symbol', '') or pos.get('Symbol', '')
                if symbol:
                    bef_positions[symbol] = self.load_bef_position(symbol)
            
            # Her hisse için analiz
            current_total = 0
            pot_total = 0
            pot_increase_total = 0
            pot_decrease_total = 0
            by_symbol = {}
            
            # Tüm sembolleri topla (pozisyonlar + emirler)
            all_symbols = set()
            for pos in positions:
                symbol = pos.get('symbol', '') or pos.get('Symbol', '')
                if symbol:
                    all_symbols.add(symbol)
            for order in orders:
                symbol = order.get('symbol', '') or order.get('Symbol', '')
                if symbol:
                    all_symbols.add(symbol)
            
            for symbol in all_symbols:
                # Mevcut pozisyon
                current_pos = 0
                for pos in positions:
                    pos_symbol = pos.get('symbol', '') or pos.get('Symbol', '')
                    if pos_symbol == symbol:
                        qty = pos.get('quantity') or pos.get('qty') or pos.get('Quantity', 0)
                        current_pos = float(qty) if qty else 0
                        break
                
                # Gün başı pozisyon
                bef_pos = bef_positions.get(symbol, 0)
                
                # Açık emirleri analiz et
                pot_increase = 0  # Pozisyon arttırma emirleri
                pot_decrease = 0  # Pozisyon azaltma emirleri
                
                for order in orders:
                    order_symbol = order.get('symbol', '') or order.get('Symbol', '')
                    if order_symbol != symbol:
                        continue
                    
                    # Status kontrolü
                    status = order.get('status', '').upper() or order.get('Status', '').upper()
                    if status in ['CANCELLED', 'FILLED', 'REJECTED', 'API CANCELLED']:
                        continue
                    
                    # Remaining quantity
                    remaining = order.get('remaining', None) or order.get('Remaining', None)
                    if remaining is not None and remaining > 0:
                        order_qty = abs(float(remaining))
                    else:
                        order_qty = abs(float(order.get('qty', 0) or order.get('quantity', 0) or 0))
                    
                    if order_qty == 0:
                        continue
                    
                    # Emir türü
                    order_action = order.get('action', '').upper() or order.get('Action', '').upper() or order.get('side', '').upper() or order.get('Side', '').upper()
                    
                    # Pozisyon arttırma/azaltma analizi
                    if current_pos >= 0:  # Long pozisyon var veya 0
                        if order_action in ['BUY', 'LONG']:
                            # Long artırma
                            pot_increase += order_qty
                        elif order_action in ['SELL', 'SHORT']:
                            # Long azaltma
                            pot_decrease += order_qty
                    else:  # Short pozisyon var
                        if order_action in ['SELL', 'SHORT']:
                            # Short artırma
                            pot_increase += order_qty
                        elif order_action in ['BUY', 'LONG']:
                            # Short azaltma
                            pot_decrease += order_qty
                
                # Potansiyel pozisyon hesapla
                if current_pos >= 0:
                    pot_pos = current_pos + pot_increase - pot_decrease
                else:
                    pot_pos = current_pos - pot_increase + pot_decrease
                
                # Toplamlara ekle (ABS)
                current_total += abs(current_pos)
                pot_total += abs(pot_pos)
                pot_increase_total += pot_increase
                pot_decrease_total += pot_decrease
                
                # Detay kaydet
                by_symbol[symbol] = {
                    'current': current_pos,
                    'bef': bef_pos,
                    'pot_increase': pot_increase,
                    'pot_decrease': pot_decrease,
                    'pot': pot_pos
                }
            
            return {
                'current_total': int(current_total),
                'pot_total': int(pot_total),
                'pot_increase': int(pot_increase_total),
                'pot_decrease': int(pot_decrease_total),
                'by_symbol': by_symbol
            }
            
        except Exception as e:
            print(f"[POT TOTAL] ❌ Hesaplama hatası: {e}")
            import traceback
            traceback.print_exc()
            return {
                'current_total': 0,
                'pot_total': 0,
                'pot_increase': 0,
                'pot_decrease': 0,
                'by_symbol': {}
            }
    
    def analyze_order_impact(self, symbol, current_position):
        """
        Belirli bir sembol için emirlerin pozisyon üzerindeki etkisini analiz eder
        
        Args:
            symbol: Hisse sembolü
            current_position: Mevcut pozisyon (pozitif=long, negatif=short)
            
        Returns:
            dict: {
                'long_increase_orders': int,  # Long artırma emirleri toplamı
                'long_decrease_orders': int,  # Long azaltma emirleri toplamı
                'short_increase_orders': int, # Short artırma emirleri toplamı
                'short_decrease_orders': int, # Short azaltma emirleri toplamı
                'potential_position': int,    # Potansiyel pozisyon
                'max_additional_long': int,   # Maksimum ek long emir
                'max_additional_short': int   # Maksimum ek short emir
            }
        """
        try:
            # Cache'lenmiş emirleri al (60 saniyede bir güncellenir)
            orders = self.get_cached_orders()
            if not orders:
                return {
                    'long_increase_orders': 0,
                    'long_decrease_orders': 0,
                    'short_increase_orders': 0,
                    'short_decrease_orders': 0,
                    'potential_position': current_position,
                    'max_additional_long': 0,
                    'max_additional_short': 0
                }
            
            # Emir analizi
            long_increase = 0  # Long artırma emirleri
            long_decrease = 0  # Long azaltma emirleri
            short_increase = 0 # Short artırma emirleri
            short_decrease = 0 # Short azaltma emirleri
            
            for order in orders:
                order_symbol = order.get('symbol', '') or order.get('Symbol', '')
                order_action = order.get('action', '').upper() or order.get('Action', '').upper() or order.get('side', '').upper() or order.get('Side', '').upper()
                
                # Remaining quantity kullan (daha doğru)
                remaining = order.get('remaining', None) or order.get('Remaining', None)
                if remaining is not None and remaining > 0:
                    order_qty = abs(float(remaining))
                else:
                    order_qty = abs(float(order.get('qty', 0) or order.get('quantity', 0) or order.get('Quantity', 0) or 0))
                
                # Status kontrolü - sadece açık emirleri say
                status = order.get('status', '').upper() or order.get('Status', '').upper()
                if status in ['CANCELLED', 'FILLED', 'REJECTED', 'API CANCELLED']:
                    continue  # Bu emirler artık açık değil
                
                # Symbol eşleştirmesi
                is_match = False
                if order_symbol == symbol:
                    is_match = True
                elif '-' in order_symbol:
                    base_symbol = order_symbol.split('-')[0]
                    if base_symbol == symbol.replace(' PR', ''):
                        is_match = True
                
                if is_match and order_qty > 0:
                    if order_action in ['BUY', 'LONG']:
                        if current_position >= 0:
                            # Long pozisyon var veya yok, BUY emri long artırır
                            long_increase += order_qty
                        else:
                            # Short pozisyon var, BUY emri short azaltır
                            short_decrease += order_qty
                    elif order_action in ['SELL', 'SHORT']:
                        if current_position > 0:
                            # Long pozisyon var, SELL emri long azaltır
                            long_decrease += order_qty
                        else:
                            # Long pozisyon yok, SELL emri short artırır
                            short_increase += order_qty
            
            # Potansiyel pozisyon hesapla
            potential_position = current_position + long_increase - long_decrease - short_increase + short_decrease
            
            # MAXALW değerini al
            maxalw = self.get_maxalw_for_symbol(symbol)
            
            # Maksimum ek emir hesapla
            max_additional_long = 0
            max_additional_short = 0
            
            if current_position >= 0:
                # Long pozisyon var veya yok
                current_long = max(0, current_position)
                max_additional_long = max(0, maxalw - current_long - long_increase + long_decrease)
                max_additional_short = max(0, maxalw - short_increase + short_decrease)
            else:
                # Short pozisyon var
                current_short = abs(current_position)
                max_additional_short = max(0, maxalw - current_short - short_increase + short_decrease)
                max_additional_long = max(0, maxalw - long_increase + long_decrease)
            
            return {
                'long_increase_orders': long_increase,
                'long_decrease_orders': long_decrease,
                'short_increase_orders': short_increase,
                'short_decrease_orders': short_decrease,
                'potential_position': potential_position,
                'max_additional_long': max_additional_long,
                'max_additional_short': max_additional_short
            }
            
        except Exception as e:
            self.log_message(f"❌ Emir analiz hatası ({symbol}): {e}")
            return {
                'long_increase_orders': 0,
                'long_decrease_orders': 0,
                'short_increase_orders': 0,
                'short_decrease_orders': 0,
                'potential_position': current_position,
                'max_additional_long': 0,
                'max_additional_short': 0
            }
    
    def log_message(self, message):
        """Psfalgo log mesajı ekle"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {message}\n"
            self.log_text.insert(tk.END, log_entry)
            self.log_text.see(tk.END)
        except Exception:
            pass
    
    def run_all_sequence(self):
        """RUNALL butonu: Lot bölücü aç → Controller ON → KARBOTU başlat → ADDNEWPOS → 1 dk bekle → Emirleri iptal et → Tekrar başla (sürekli döngü)"""
        try:
            # RUNALL Allowed modunu kontrol et
            if hasattr(self, 'runall_allowed_var'):
                self.runall_allowed_mode = self.runall_allowed_var.get()
            else:
                self.runall_allowed_mode = False
            
            # RUNALL döngüsü durumu kontrolü (toggle)
            if not hasattr(self, 'runall_loop_running'):
                self.runall_loop_running = False
                self.runall_loop_count = 0
            
            # Eğer döngü çalışıyorsa durdur
            if self.runall_loop_running:
                self.stop_runall_loop()
                return
            
            # Döngüyü başlat
            self.runall_loop_running = True
            
            # Tıklanmış butonları ve kapatılmış pencereleri temizle (yeni döngü başladığında)
            if hasattr(self, '_clicked_buttons'):
                self._clicked_buttons.clear()
            if hasattr(self, '_closed_windows'):
                self._closed_windows.clear()
            
            print("[RUNALL] ▶️ RUNALL sırası başlatılıyor...")
            self.log_message("▶️ RUNALL sırası başlatılıyor...")
            
            # Buton metnini güncelle
            if hasattr(self, 'runall_btn'):
                self.runall_btn.config(text="▶️ RUNALL", state='disabled')
            if hasattr(self, 'runall_stop_btn'):
                self.runall_stop_btn.config(state='normal')
            
            # Döngü sayacını artır
            self.runall_loop_count += 1
            print(f"[RUNALL] 🔄 Döngü #{self.runall_loop_count} başlatılıyor...")
            self.log_message(f"🔄 Döngü #{self.runall_loop_count} başlatılıyor...")
            
            # Adım 1: Lot bölücü kontrolü (checkbox'tan kontrol edilecek)
            if hasattr(self, 'runall_lot_divider_var'):
                lot_divider_enabled = self.runall_lot_divider_var.get()
                if lot_divider_enabled and not self.lot_divider_enabled:
                    self.lot_divider_enabled = True
                    self.btn_lot_divider.config(text="📦 Lot Divider: ON")
                    self.btn_lot_divider.config(style='Success.TButton')
                    print("[RUNALL] ✅ Adım 1: Lot Bölücü açıldı (checkbox aktif)")
                    self.log_message("✅ Adım 1: Lot Bölücü açıldı (checkbox aktif)")
                elif not lot_divider_enabled:
                    print("[RUNALL] ℹ️ Adım 1: Lot Bölücü checkbox işaretli değil, açılmayacak")
                    self.log_message("ℹ️ Adım 1: Lot Bölücü checkbox işaretli değil")
                else:
                    print("[RUNALL] ℹ️ Adım 1: Lot Bölücü zaten açık")
                    self.log_message("ℹ️ Adım 1: Lot Bölücü zaten açık")
            else:
                print("[RUNALL] ℹ️ Adım 1: Lot Bölücü checkbox bulunamadı, açılmayacak")
                self.log_message("ℹ️ Adım 1: Lot Bölücü checkbox bulunamadı")
            
            # Adım 2: Controller'ı ON yap (aktif moda göre doğru CSV kullanılacak)
            if not self.controller_enabled:
                self.controller_enabled = True
                self.controller_btn.config(text="🎛️ Controller: ON")
                self.controller_btn.config(style='Success.TButton')
                
                # Aktif modu logla
                active_account = self.mode_manager.get_active_account()
                if active_account == "IBKR_GUN":
                    csv_file = "befibgun.csv"
                elif active_account == "IBKR_PED":
                    csv_file = "befibped.csv"
                elif active_account == "HAMPRO":
                    csv_file = "befham.csv"
                else:
                    csv_file = "bilinmeyen"
                
                print(f"[RUNALL] ✅ Adım 2: Controller ON yapıldı (CSV: {csv_file})")
                self.log_message(f"✅ Adım 2: Controller ON yapıldı (CSV: {csv_file})")
            else:
                print("[RUNALL] ℹ️ Adım 2: Controller zaten ON")
                self.log_message("ℹ️ Adım 2: Controller zaten ON")
            
            # Adım 3: Pot Toplam kontrolü ve ADDNEWPOS butonu durumu
            exposure_info = self.check_exposure_limits()
            pot_total = exposure_info.get('pot_total', 0)
            pot_max_lot = exposure_info.get('pot_max_lot', 63636)
            total_lots = exposure_info.get('total_lots', 0)
            max_lot = exposure_info.get('max_lot', 54545)
            mode = exposure_info.get('mode', 'UNKNOWN')
            
            # Pot Toplam kontrolü
            if pot_total > 0 and pot_total >= pot_max_lot:
                print(f"[RUNALL] ⚠️ Pot Toplam limiti aşıldı: {pot_total:,} / {pot_max_lot:,}")
                self.log_message(f"⚠️ Pot Toplam limiti aşıldı: {pot_total:,} / {pot_max_lot:,}")
                # ADDNEWPOS butonunu pasif yap
                if hasattr(self, 'addnewpos_btn'):
                    self.addnewpos_btn.config(state='disabled')
            else:
                # ADDNEWPOS butonu durumu
                if mode == "OFANSIF" and pot_total < pot_max_lot:
                    if hasattr(self, 'addnewpos_btn'):
                        self.addnewpos_btn.config(state='normal')
                        print(f"[RUNALL] ✅ ADDNEWPOS aktif: Pot Toplam {pot_total:,} < Pot Max {pot_max_lot:,}")
                        self.log_message(f"✅ ADDNEWPOS aktif: Pot Toplam {pot_total:,} < Pot Max {pot_max_lot:,}")
                else:
                    if hasattr(self, 'addnewpos_btn'):
                        self.addnewpos_btn.config(state='disabled')
            
            # Adım 4: KARBOTU'yu başlat
            print("[RUNALL] ✅ Adım 4: KARBOTU başlatılıyor...")
            self.log_message("✅ Adım 4: KARBOTU başlatılıyor...")
            
            # KARBOTU bitince otomatik ADDNEWPOS tetikleme için callback ekle
            self.runall_waiting_for_karbotu = True
            self.runall_addnewpos_triggered = False  # ADDNEWPOS'un sadece bir kez tetiklenmesini sağla
            self.start_karbotu_automation()
            
            # KARBOTU bitince kontrol et (her 5 saniyede bir kontrol) - SADECE BACKUP olarak
            # Asıl tetikleme karbotu_proceed_to_next_step ve karbotu_step_13'ten gelecek
            # self.after(5000, self.runall_check_karbotu_and_addnewpos)  # YORUM SATIRI - Çift tetiklemeyi önlemek için
            
            print("[RUNALL] ✅ RUNALL sırası başlatıldı (KARBOTU çalışıyor, bitince ADDNEWPOS kontrol edilecek)")
            self.log_message("✅ RUNALL sırası başlatıldı (KARBOTU çalışıyor, bitince ADDNEWPOS kontrol edilecek)")
            
            # Allowed modunda otomatik onay başlat
            if self.runall_allowed_mode:
                print("[RUNALL] ✅ Allowed modu aktif - Otomatik onay sistemi çalışıyor")
                self.log_message("✅ Allowed modu aktif - Otomatik onay sistemi çalışıyor")
                self.start_runall_auto_confirm_loop()
            
        except Exception as e:
            print(f"[RUNALL] ❌ RUNALL hatası: {e}")
            self.log_message(f"❌ RUNALL hatası: {e}")
            if not self.runall_allowed_mode:
                messagebox.showerror("Hata", f"RUNALL başlatılamadı: {e}")
    
    def load_excluded_tickers_from_csv(self):
        """excluder_psfalgo.csv dosyasından excluded ticker'ları yükle"""
        try:
            import pandas as pd
            import os
            
            csv_file = "excluder_psfalgo.csv"
            
            if not hasattr(self, 'excluded_tickers'):
                self.excluded_tickers = set()
            
            if os.path.exists(csv_file):
                df = pd.read_csv(csv_file)
                
                # Symbol veya Ticker kolonunu bul
                symbol_col = None
                if 'Symbol' in df.columns:
                    symbol_col = 'Symbol'
                elif 'Ticker' in df.columns:
                    symbol_col = 'Ticker'
                elif len(df.columns) > 0:
                    symbol_col = df.columns[0]  # İlk kolonu kullan
                
                if symbol_col:
                    tickers = df[symbol_col].dropna().astype(str).str.strip().str.upper()
                    self.excluded_tickers = set(tickers.tolist())
                    print(f"[EXCLUDER] ✅ {len(self.excluded_tickers)} ticker CSV'den yüklendi")
                else:
                    print(f"[EXCLUDER] ⚠️ CSV dosyasında uygun kolon bulunamadı")
            else:
                print(f"[EXCLUDER] ℹ️ CSV dosyası bulunamadı, boş liste başlatılıyor")
                self.excluded_tickers = set()
                
        except Exception as e:
            print(f"[EXCLUDER] ❌ CSV yükleme hatası: {e}")
            if not hasattr(self, 'excluded_tickers'):
                self.excluded_tickers = set()
    
    def save_excluded_tickers_to_csv(self):
        """Excluded ticker'ları excluder_psfalgo.csv dosyasına kaydet"""
        try:
            import pandas as pd
            
            csv_file = "excluder_psfalgo.csv"
            
            if not hasattr(self, 'excluded_tickers') or not self.excluded_tickers:
                # Boş liste ise CSV'yi sil veya boş DataFrame kaydet
                df = pd.DataFrame(columns=['Symbol'])
                df.to_csv(csv_file, index=False)
                print(f"[EXCLUDER] ✅ CSV dosyası temizlendi")
            else:
                # Ticker'ları DataFrame'e çevir
                tickers_list = sorted(list(self.excluded_tickers))
                df = pd.DataFrame({'Symbol': tickers_list})
                df.to_csv(csv_file, index=False)
                print(f"[EXCLUDER] ✅ {len(tickers_list)} ticker CSV'ye kaydedildi: {csv_file}")
                
        except Exception as e:
            print(f"[EXCLUDER] ❌ CSV kaydetme hatası: {e}")
            raise
    
    def show_excluder_dialog(self):
        """Excluder dialog'unu göster - Ticker'ları exclude etmek için"""
        try:
            from tkinter import messagebox
            
            # CSV'den yükle
            self.load_excluded_tickers_from_csv()
            
            # Dialog penceresi oluştur
            dialog = tk.Toplevel(self.psfalgo_window)
            dialog.title("🚫 Excluder - Ticker Exclude Listesi")
            dialog.geometry("600x500")
            dialog.transient(self.psfalgo_window)
            dialog.grab_set()
            
            # Ana frame
            main_frame = ttk.Frame(dialog)
            main_frame.pack(fill='both', expand=True, padx=10, pady=10)
            
            # Açıklama
            info_label = ttk.Label(main_frame, 
                                  text="Manage tickers to exclude",
                                  font=("Arial", 10, "bold"))
            info_label.pack(pady=5)
            
            # Liste kutusu ve scrollbar
            list_frame = ttk.Frame(main_frame)
            list_frame.pack(fill='both', expand=True, pady=10)
            
            scrollbar = ttk.Scrollbar(list_frame)
            scrollbar.pack(side='right', fill='y')
            
            listbox = tk.Listbox(list_frame, height=12, yscrollcommand=scrollbar.set, selectmode=tk.EXTENDED)
            listbox.pack(side='left', fill='both', expand=True)
            scrollbar.config(command=listbox.yview)
            
            # Mevcut ticker'ları listbox'a yükle
            if hasattr(self, 'excluded_tickers') and self.excluded_tickers:
                for ticker in sorted(self.excluded_tickers):
                    listbox.insert(tk.END, ticker)
            
            # Ekleme alanı
            add_frame = ttk.Frame(main_frame)
            add_frame.pack(fill='x', pady=5)
            
            ttk.Label(add_frame, text="Add New Ticker (comma separated):", font=("Arial", 9)).pack(anchor='w')
            
            entry_frame = ttk.Frame(add_frame)
            entry_frame.pack(fill='x', pady=5)
            
            entry_widget = ttk.Entry(entry_frame, width=50)
            entry_widget.pack(side='left', fill='x', expand=True, padx=(0, 5))
            
            def add_tickers():
                """Yeni ticker'lar ekle"""
                try:
                    text_content = entry_widget.get().strip()
                    if not text_content:
                        return
                    
                    # Virgülle ayır ve temizle
                    new_tickers = [t.strip().upper() for t in text_content.split(',') if t.strip()]
                    
                    if not hasattr(self, 'excluded_tickers'):
                        self.excluded_tickers = set()
                    
                    added_count = 0
                    for ticker in new_tickers:
                        if ticker and ticker not in self.excluded_tickers:
                            self.excluded_tickers.add(ticker)
                            listbox.insert(tk.END, ticker)
                            added_count += 1
                    
                    if added_count > 0:
                        # Listbox'ı sırala
                        items = list(listbox.get(0, tk.END))
                        listbox.delete(0, tk.END)
                        for item in sorted(items):
                            listbox.insert(tk.END, item)
                        
                        entry_widget.delete(0, tk.END)
                        self.log_message(f"✅ {added_count} ticker eklendi")
                    else:
                        messagebox.showinfo("Bilgi", "Ticker'lar zaten listede veya geçersiz")
                        
                except Exception as e:
                    messagebox.showerror("Hata", f"Ticker eklenemedi: {e}")
            
            add_btn = ttk.Button(entry_frame, text="➕ Ekle", command=add_tickers)
            add_btn.pack(side='left')
            
            # Butonlar
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill='x', pady=10)
            
            def delete_selected():
                """Seçili ticker'ları sil"""
                try:
                    selected_indices = listbox.curselection()
                    if not selected_indices:
                        messagebox.showinfo("Bilgi", "Lütfen silmek için ticker seçin")
                        return
                    
                    # Seçili ticker'ları al
                    selected_tickers = [listbox.get(i) for i in selected_indices]
                    
                    # Set'ten sil
                    for ticker in selected_tickers:
                        if ticker in self.excluded_tickers:
                            self.excluded_tickers.remove(ticker)
                    
                    # Listbox'tan sil (ters sırada sil ki index kaymasın)
                    for i in reversed(selected_indices):
                        listbox.delete(i)
                    
                    self.log_message(f"✅ {len(selected_tickers)} ticker silindi")
                    messagebox.showinfo("Başarılı", f"{len(selected_tickers)} ticker silindi")
                    
                except Exception as e:
                    messagebox.showerror("Hata", f"Ticker silinemedi: {e}")
            
            def select_all():
                """Tüm ticker'ları seç"""
                listbox.selection_set(0, tk.END)
            
            def clear_all():
                """Tüm ticker'ları sil"""
                if not hasattr(self, 'excluded_tickers') or not self.excluded_tickers:
                    messagebox.showinfo("Bilgi", "Liste zaten boş")
                    return
                
                if messagebox.askyesno("Onay", "Tüm ticker'ları silmek istediğinize emin misiniz?"):
                    self.excluded_tickers = set()
                    listbox.delete(0, tk.END)
                    self.log_message("✅ Tüm ticker'lar silindi")
                    messagebox.showinfo("Başarılı", "Tüm ticker'lar silindi")
            
            def save_and_close():
                """Kaydet ve kapat"""
                try:
                    self.save_excluded_tickers_to_csv()
                    self.log_message(f"✅ {len(self.excluded_tickers)} ticker CSV'ye kaydedildi")
                    messagebox.showinfo("Başarılı", f"{len(self.excluded_tickers)} ticker kaydedildi")
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("Hata", f"Kaydetme hatası: {e}")
            
            def cancel_dialog():
                """Dialog'u iptal et"""
                dialog.destroy()
            
            # Butonlar
            ttk.Button(button_frame, text="🗑️ Delete Selected", command=delete_selected).pack(side='left', padx=2)
            ttk.Button(button_frame, text="📋 Select All", command=select_all).pack(side='left', padx=2)
            ttk.Button(button_frame, text="🗑️ Delete All", command=clear_all).pack(side='left', padx=2)
            ttk.Button(button_frame, text="💾 Save and Close", command=save_and_close).pack(side='left', padx=2)
            ttk.Button(button_frame, text="❌ Cancel", command=cancel_dialog).pack(side='left', padx=2)
            
            # Enter tuşu ile ekle
            entry_widget.bind('<Return>', lambda e: add_tickers())
            
            # Focus'u entry widget'a ver
            entry_widget.focus_set()
            
        except Exception as e:
            print(f"[EXCLUDER] ❌ Dialog hatası: {e}")
            import traceback
            traceback.print_exc()
            from tkinter import messagebox
            messagebox.showerror("Hata", f"Excluder dialog'u açılamadı: {e}")
    
    def is_ticker_excluded(self, symbol):
        """Ticker exclude edilmiş mi kontrol et"""
        if not hasattr(self, 'excluded_tickers'):
            return False
        return symbol.upper() in self.excluded_tickers
    
    def start_addnewpos_automation(self, from_runall=False):
        """
        ADDNEWPOS otomasyonu: Port Adjuster → CSV Yükle → Final FB&SFS → Grup Ağırlıkları → TUMCSV → BB Long Filtre → JFIN %50 BB → Exclude Kontrol → Emir Gönder
        
        Args:
            from_runall: True ise RUNALL'dan çağrıldı (exposure kontrolü yapılacak), False ise manuel çağrıldı (direkt başlatılacak)
        """
        try:
            print("[ADDNEWPOS] ▶️ ADDNEWPOS otomasyonu başlatılıyor...")
            self.log_message("▶️ ADDNEWPOS otomasyonu başlatılıyor...")
            
            # RUNALL'dan çağrılmadıysa (manuel çağrıldıysa) exposure kontrolü yapma, direkt başlat
            if not from_runall:
                print("[ADDNEWPOS] ℹ️ Manuel olarak başlatıldı, exposure kontrolü yapılmıyor")
                self.log_message("ℹ️ Manuel olarak başlatıldı, exposure kontrolü yapılmıyor")
            
            # Excluded ticker'ları yükle
            self.load_excluded_tickers_from_csv()
            
            # Adım 1: Port Adjuster penceresini aç
            self.log_message("📋 Adım 1: Port Adjuster penceresi açılıyor...")
            port_adjuster_window = self.show_port_adjuster()
            
            # Port Adjuster referansını sakla
            self.addnewpos_port_adjuster = port_adjuster_window
            
            # Port Adjuster penceresinin açılmasını bekle
            self.after(1000, lambda: self.addnewpos_step_2_csv_yukle(port_adjuster_window))
            
        except Exception as e:
            print(f"[ADDNEWPOS] ❌ Otomasyon başlatma hatası: {e}")
            self.log_message(f"❌ ADDNEWPOS başlatma hatası: {e}")
            import traceback
            traceback.print_exc()
            from tkinter import messagebox
            messagebox.showerror("Hata", f"ADDNEWPOS başlatılamadı: {e}")
    
    def addnewpos_step_2_csv_yukle(self, port_adjuster_window):
        """Adım 2: CSV'den Yükle butonuna tıkla"""
        try:
            self.log_message("📋 Adım 2: CSV'den Yükle butonuna tıklanıyor...")
            
            # Port Adjuster window kontrolü
            if port_adjuster_window is None:
                print("[ADDNEWPOS] ❌ Port Adjuster window None")
                self.log_message("❌ Adım 2: Port Adjuster penceresi bulunamadı")
                return
            
            # Port Adjuster penceresindeki CSV'den Yükle butonunu bul ve tıkla
            if hasattr(port_adjuster_window, 'load_settings_from_csv'):
                port_adjuster_window.load_settings_from_csv()
                print("[ADDNEWPOS] ✅ CSV'den Yükle tamamlandı")
                self.log_message("✅ Adım 2: CSV'den Yükle tamamlandı")
                
                # Messagebox'ı otomatik kapat (eğer açıldıysa) ve sonraki adıma geç
                self.after(500, lambda: self.addnewpos_close_messagebox())
                
                # Popup'ları kapat ve pencere kapanmasını bekle
                def proceed_to_step_3():
                    # Popup'ları tekrar kontrol et
                    self.addnewpos_close_messagebox()
                    # Sonraki adıma geç
                    self.addnewpos_step_3_final_fb_sfs(port_adjuster_window)
                
                # Kısa bir bekleme sonrası devam et
                self.after(1500, proceed_to_step_3)
            else:
                print(f"[ADDNEWPOS] ❌ Port Adjuster'da load_settings_from_csv bulunamadı. Mevcut attributeler: {dir(port_adjuster_window)}")
                self.log_message("❌ Adım 2: CSV'den Yükle butonu bulunamadı")
        except Exception as e:
            print(f"[ADDNEWPOS] ❌ Adım 2 hatası: {e}")
            self.log_message(f"❌ Adım 2 hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def wait_for_window_close(self, window, callback, max_wait=5000, check_interval=200):
        """
        Pencere kapanana kadar bekle, sonra callback'i çağır
        
        Args:
            window: Kontrol edilecek pencere (Toplevel veya widget)
            callback: Pencere kapandıktan sonra çağrılacak fonksiyon
            max_wait: Maksimum bekleme süresi (ms)
            check_interval: Kontrol aralığı (ms)
        """
        if window is None:
            # Pencere yoksa direkt callback'i çağır
            callback()
            return
        
        start_time = time.time() * 1000  # ms cinsinden
        
        def check_window():
            current_time = time.time() * 1000
            elapsed = current_time - start_time
            
            # Maksimum bekleme süresi aşıldıysa devam et
            if elapsed >= max_wait:
                print(f"[WAIT] ⏱️ Maksimum bekleme süresi aşıldı ({max_wait}ms), devam ediliyor...")
                callback()
                return
            
            # Pencere hala açık mı kontrol et
            try:
                if hasattr(window, 'winfo_exists'):
                    if not window.winfo_exists():
                        print(f"[WAIT] ✅ Pencere kapatıldı, devam ediliyor...")
                        callback()
                        return
                elif hasattr(window, 'win'):
                    if not window.win.winfo_exists():
                        print(f"[WAIT] ✅ Pencere kapatıldı, devam ediliyor...")
                        callback()
                        return
            except:
                # Pencere zaten kapanmış olabilir
                print(f"[WAIT] ✅ Pencere kapatıldı (exception), devam ediliyor...")
                callback()
                return
            
            # Popup'ları kontrol et ve kapat
            self.runall_auto_confirm_messagebox()
            
            # Tekrar kontrol et
            self.after(check_interval, check_window)
        
        # İlk kontrolü başlat
        self.after(check_interval, check_window)
    
    def addnewpos_close_messagebox(self):
        """Açık messagebox'ları otomatik kapat - Daha agresif versiyon"""
        try:
            # Önce runall_auto_confirm_messagebox'ı çağır (daha güçlü)
            if hasattr(self, 'runall_allowed_mode') and self.runall_allowed_mode:
                self.runall_auto_confirm_messagebox()
            
            # Tüm açık Toplevel pencerelerini kontrol et (recursive)
            def find_and_close_all_messageboxes(parent):
                try:
                    for widget in parent.winfo_children():
                        if isinstance(widget, tk.Toplevel):
                            try:
                                title = widget.title().lower()
                                # Messagebox pencerelerini tespit et (daha geniş keyword listesi)
                                if any(keyword in title for keyword in [
                                    'başarılı', 'success', 'tamamlandı', 'completed', 'tamam', 'ok', 
                                    'uyarı', 'warning', 'hata', 'error', 'info', 'information',
                                    'bilgi', 'mesaj', 'message', 'onay', 'confirm', 'lot hesaplama',
                                    'cercop', 'otomatik seçim', 'emir sonucu', 'emir özeti'
                                ]) or title == '':
                                    # "OK" veya "Tamam" butonunu bul ve tıkla (daha agresif)
                                    def find_ok_button(parent_widget, depth=0):
                                        if depth > 15:
                                            return False
                                        try:
                                            for child in parent_widget.winfo_children():
                                                if isinstance(child, (tk.Button, ttk.Button)):
                                                    try:
                                                        text = str(child.cget('text')).lower().strip()
                                                        if any(keyword in text for keyword in [
                                                            'ok', 'tamam', 'okay', 'kabul', 'accept', 
                                                            'onayla', 'confirm', 'evet', 'yes'
                                                        ]):
                                                            # İptal butonlarını atla
                                                            if any(cancel in text for cancel in ['iptal', 'cancel', 'reddet', 'no', 'hayır']):
                                                                continue
                                                            child.invoke()
                                                            print(f"[ADDNEWPOS] ✅ Messagebox kapatıldı: '{text}' ({widget.title()})")
                                                            # Kısa bir bekleme ekle
                                                            self.after(100, lambda: None)
                                                            return True
                                                    except:
                                                        pass
                                                # Recursive olarak devam et
                                                if find_ok_button(child, depth + 1):
                                                    return True
                                        except:
                                            pass
                                        return False
                                    
                                    if find_ok_button(widget):
                                        # Pencereyi de kapat (eğer hala açıksa)
                                        try:
                                            if widget.winfo_exists():
                                                widget.destroy()
                                        except:
                                            pass
                            except:
                                pass
                        # Recursive olarak devam et
                        find_and_close_all_messageboxes(widget)
                except:
                    pass
            
            # Ana pencereden başla
            find_and_close_all_messageboxes(self)
            
            # Port Adjuster ve FinalThgLotDistributor pencerelerini de kontrol et
            if hasattr(self, 'addnewpos_port_adjuster') and self.addnewpos_port_adjuster:
                if hasattr(self.addnewpos_port_adjuster, 'win'):
                    find_and_close_all_messageboxes(self.addnewpos_port_adjuster.win)
            
            if hasattr(self, 'addnewpos_final_thg') and self.addnewpos_final_thg:
                if hasattr(self.addnewpos_final_thg, 'win'):
                    find_and_close_all_messageboxes(self.addnewpos_final_thg.win)
            
            # Psfalgo penceresini de kontrol et
            if hasattr(self, 'psfalgo_window') and self.psfalgo_window:
                try:
                    find_and_close_all_messageboxes(self.psfalgo_window)
                except:
                    pass
                    
        except Exception as e:
            print(f"[ADDNEWPOS] ⚠️ Messagebox kapatma hatası: {e}")
    
    def addnewpos_step_3_final_fb_sfs(self, port_adjuster_window):
        """Adım 3: 3. Step - Final FB & SFS butonuna tıkla"""
        try:
            self.log_message("📋 Adım 3: Final FB & SFS penceresi açılıyor...")
            
            # Port Adjuster penceresinin hala açık olduğunu kontrol et
            if not port_adjuster_window or not hasattr(port_adjuster_window, 'win'):
                print("[ADDNEWPOS] ❌ Port Adjuster penceresi geçersiz")
                self.log_message("❌ Adım 3: Port Adjuster penceresi geçersiz")
                return
            
            try:
                port_adjuster_window.win.winfo_exists()
            except tk.TclError:
                print("[ADDNEWPOS] ❌ Port Adjuster penceresi kapatılmış")
                self.log_message("❌ Adım 3: Port Adjuster penceresi kapatılmış")
                return
            
            # Port Adjuster'daki Final FB & SFS butonuna tıkla
            if hasattr(port_adjuster_window, 'show_final_thg_distributor'):
                try:
                    final_thg_distributor = port_adjuster_window.show_final_thg_distributor()
                    print("[ADDNEWPOS] ✅ Final FB & SFS penceresi açıldı")
                    self.log_message("✅ Adım 3: Final FB & SFS penceresi açıldı")
                    
                    # FinalThgLotDistributor referansını sakla
                    if final_thg_distributor:
                        self.addnewpos_final_thg = final_thg_distributor
                        # Final THG penceresinin başarıyla açıldığını kontrol et
                        if hasattr(final_thg_distributor, 'win'):
                            try:
                                final_thg_distributor.win.winfo_exists()
                                print("[ADDNEWPOS] ✅ Final THG penceresi doğrulandı")
                            except tk.TclError:
                                print("[ADDNEWPOS] ⚠️ Final THG penceresi geçersiz")
                                return
                    elif hasattr(port_adjuster_window, 'final_thg_distributor'):
                        self.addnewpos_final_thg = port_adjuster_window.final_thg_distributor
                    else:
                        print("[ADDNEWPOS] ⚠️ FinalThgLotDistributor referansı alınamadı")
                        self.addnewpos_port_adjuster = port_adjuster_window
                    
                    # Popup'ları kapat ve sonraki adıma geç
                    def proceed_to_step_4():
                        # Popup'ları kontrol et ve kapat
                        self.addnewpos_close_messagebox()
                        
                        # Port Adjuster penceresini minimize et (kapatma, çünkü Final THG'nin parent'ı)
                        # Final THG penceresi Port Adjuster'ın child'ı olduğu için kapatmıyoruz
                        if port_adjuster_window and hasattr(port_adjuster_window, 'win'):
                            try:
                                if port_adjuster_window.win.winfo_exists():
                                    print("[ADDNEWPOS] 📦 Port Adjuster penceresi minimize ediliyor (Final THG açık)...")
                                    self.log_message("📦 Port Adjuster penceresi minimize ediliyor...")
                                    port_adjuster_window.win.iconify()  # Minimize et, kapatma
                            except:
                                pass
                        
                        # Sonraki adıma geç
                        self.addnewpos_step_4_grup_agirliklari()
                    
                    self.after(1000, proceed_to_step_4)
                except tk.TclError as e:
                    print(f"[ADDNEWPOS] ❌ Final THG penceresi açılırken hata: {e}")
                    self.log_message(f"❌ Adım 3: Final THG penceresi açılamadı: {e}")
                    # Hata mesajını Allowed modunda otomatik kapat
                    if hasattr(self, 'runall_allowed_mode') and self.runall_allowed_mode:
                        self.after(500, lambda: self.addnewpos_close_messagebox())
            else:
                print("[ADDNEWPOS] ❌ Port Adjuster'da show_final_thg_distributor bulunamadı")
                self.log_message("❌ Adım 3: Final FB & SFS butonu bulunamadı")
        except Exception as e:
            print(f"[ADDNEWPOS] ❌ Adım 3 hatası: {e}")
            self.log_message(f"❌ Adım 3 hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def addnewpos_step_4_grup_agirliklari(self):
        """Adım 4: Grup Ağırlıklarını Yükle butonuna tıkla"""
        try:
            self.log_message("📋 Adım 4: Grup Ağırlıklarını Yükle...")
            
            # FinalThgLotDistributor referansını al
            final_thg = None
            if hasattr(self, 'addnewpos_final_thg') and self.addnewpos_final_thg:
                final_thg = self.addnewpos_final_thg
            elif hasattr(self, 'addnewpos_port_adjuster') and hasattr(self.addnewpos_port_adjuster, 'final_thg_distributor'):
                final_thg = self.addnewpos_port_adjuster.final_thg_distributor
                self.addnewpos_final_thg = final_thg
            
            if final_thg and hasattr(final_thg, 'load_group_weights'):
                final_thg.load_group_weights()
                print("[ADDNEWPOS] ✅ Grup Ağırlıklarını Yükle tamamlandı")
                self.log_message("✅ Adım 4: Grup Ağırlıklarını Yükle tamamlandı")
                
                # Messagebox'ı otomatik kapat ve popup'ları kontrol et
                def proceed_to_step_5():
                    # Popup'ları tekrar kontrol et ve kapat
                    self.addnewpos_close_messagebox()
                    # Sonraki adıma geç
                    self.addnewpos_step_5_tumcsv()
                
                self.after(500, lambda: self.addnewpos_close_messagebox())
                self.after(1500, proceed_to_step_5)
            else:
                print("[ADDNEWPOS] ❌ FinalThgLotDistributor veya load_group_weights bulunamadı")
                self.log_message("❌ Adım 4: Grup Ağırlıklarını Yükle butonu bulunamadı")
        except Exception as e:
            print(f"[ADDNEWPOS] ❌ Adım 4 hatası: {e}")
            self.log_message(f"❌ Adım 4 hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def addnewpos_step_5_tumcsv(self):
        """Adım 5: TUMCSV Ayarlaması Yap butonuna tıkla"""
        try:
            self.log_message("📋 Adım 5: TUMCSV Ayarlaması Yap...")
            
            # FinalThgLotDistributor referansını al
            final_thg = None
            if hasattr(self, 'addnewpos_final_thg') and self.addnewpos_final_thg:
                final_thg = self.addnewpos_final_thg
            elif hasattr(self, 'addnewpos_port_adjuster') and hasattr(self.addnewpos_port_adjuster, 'final_thg_distributor'):
                final_thg = self.addnewpos_port_adjuster.final_thg_distributor
                self.addnewpos_final_thg = final_thg
            
            if final_thg and hasattr(final_thg, 'apply_tumcsv_rules'):
                final_thg.apply_tumcsv_rules()
                print("[ADDNEWPOS] ✅ TUMCSV Ayarlaması tamamlandı")
                self.log_message("✅ Adım 5: TUMCSV Ayarlaması tamamlandı")
                
                # Messagebox'ı otomatik kapat (TUMCSV işlemi uzun sürebilir)
                def proceed_to_step_6():
                    # Popup'ları tekrar kontrol et ve kapat
                    self.addnewpos_close_messagebox()
                    # Sonraki adıma geç
                    self.addnewpos_step_6_bb_filter()
                
                self.after(2000, lambda: self.addnewpos_close_messagebox())
                self.after(3500, proceed_to_step_6)
            else:
                print("[ADDNEWPOS] ❌ FinalThgLotDistributor veya apply_tumcsv_rules bulunamadı")
                self.log_message("❌ Adım 5: TUMCSV Ayarlaması butonu bulunamadı")
        except Exception as e:
            print(f"[ADDNEWPOS] ❌ Adım 5 hatası: {e}")
            self.log_message(f"❌ Adım 5 hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def addnewpos_step_6_bb_filter(self):
        """Adım 6: BBlong sekmesinde SMA63CHG filtresini -1.6'dan küçük olacak şekilde ayarla ve Uygula"""
        try:
            self.log_message("📋 Adım 6: BB Long sekmesinde SMA63CHG filtresi uygulanıyor...")
            
            # FinalThgLotDistributor referansını al
            final_thg = None
            if hasattr(self, 'addnewpos_final_thg') and self.addnewpos_final_thg:
                final_thg = self.addnewpos_final_thg
            elif hasattr(self, 'addnewpos_port_adjuster') and hasattr(self.addnewpos_port_adjuster, 'final_thg_distributor'):
                final_thg = self.addnewpos_port_adjuster.final_thg_distributor
                self.addnewpos_final_thg = final_thg
            
            if final_thg:
                # Pencere referansının geçerli olup olmadığını kontrol et
                win_valid = False
                if hasattr(final_thg, 'win'):
                    try:
                        # Pencere hala var mı kontrol et
                        if final_thg.win.winfo_exists():
                            win_valid = True
                    except:
                        win_valid = False
                
                if not win_valid:
                    print("[ADDNEWPOS] ⚠️ Final FB & SFS penceresi geçersiz, yeniden açılıyor...")
                    self.log_message("⚠️ Final FB & SFS penceresi geçersiz, yeniden açılıyor...")
                    # Port Adjuster'dan yeniden aç
                    if hasattr(self, 'addnewpos_port_adjuster') and self.addnewpos_port_adjuster:
                        if hasattr(self.addnewpos_port_adjuster, 'show_final_thg_distributor'):
                            final_thg = self.addnewpos_port_adjuster.show_final_thg_distributor()
                            self.addnewpos_final_thg = final_thg
                            # Pencere açılmasını bekle
                            self.after(2000, lambda: self.addnewpos_step_6_bb_filter())
                            return
                    else:
                        print("[ADDNEWPOS] ❌ Port Adjuster referansı bulunamadı")
                        self.log_message("❌ Adım 6: Port Adjuster referansı bulunamadı")
                        return
                
                # BB Long sekmesine geç (notebook'u kontrol et)
                notebook_found = False
                if hasattr(final_thg, 'win') and final_thg.win.winfo_exists():
                    try:
                        # Notebook'u bul ve BB Long sekmesine geç
                        for widget in final_thg.win.winfo_children():
                            if isinstance(widget, ttk.Notebook):
                                # BB Long sekmesine geç (index 0)
                                widget.select(0)
                                print("[ADDNEWPOS] ✅ BB Long sekmesine geçildi")
                                notebook_found = True
                                break
                    except Exception as e:
                        print(f"[ADDNEWPOS] ⚠️ Notebook bulma hatası: {e}")
                
                # SMA63CHG filtresini ayarla
                if hasattr(final_thg, 'bb_sma_filter_var'):
                    try:
                        final_thg.bb_sma_filter_var.set("-1.6")
                        # Below seçili olmalı
                        if hasattr(final_thg, 'bb_filter_type'):
                            final_thg.bb_filter_type.set("below")
                        
                        # Filtreyi uygula
                        if hasattr(final_thg, 'apply_bb_filter'):
                            final_thg.apply_bb_filter()
                            print("[ADDNEWPOS] ✅ SMA63CHG filtresi uygulandı (-1.6'dan küçük)")
                            self.log_message("✅ Adım 6: SMA63CHG filtresi uygulandı (-1.6'dan küçük)")
                            
                            # Popup'ları kapat ve sonraki adıma geç
                            def proceed_to_step_7():
                                # Popup'ları kontrol et ve kapat
                                self.addnewpos_close_messagebox()
                                # Sonraki adıma geç
                                self.addnewpos_step_7_jfin_50_bb()
                            
                            self.after(500, lambda: self.addnewpos_close_messagebox())
                            self.after(1500, proceed_to_step_7)
                        else:
                            print("[ADDNEWPOS] ❌ apply_bb_filter bulunamadı")
                            self.log_message("❌ Adım 6: Filtre uygulama fonksiyonu bulunamadı")
                    except Exception as e:
                        print(f"[ADDNEWPOS] ❌ Filtre ayarlama hatası: {e}")
                        self.log_message(f"❌ Adım 6: Filtre ayarlama hatası: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print("[ADDNEWPOS] ❌ bb_sma_filter_var bulunamadı")
                    self.log_message("❌ Adım 6: SMA63CHG filtre alanı bulunamadı")
            else:
                print("[ADDNEWPOS] ❌ FinalThgLotDistributor referansı bulunamadı")
                self.log_message("❌ Adım 6: Final FB & SFS penceresi bulunamadı")
        except Exception as e:
            print(f"[ADDNEWPOS] ❌ Adım 6 hatası: {e}")
            self.log_message(f"❌ Adım 6 hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def addnewpos_step_7_jfin_50_bb(self):
        """Adım 7: JFIN %50 BB butonuna tıkla"""
        try:
            self.log_message("📋 Adım 7: JFIN %50 BB butonuna tıklanıyor...")
            
            # FinalThgLotDistributor referansını al
            final_thg = None
            if hasattr(self, 'addnewpos_final_thg') and self.addnewpos_final_thg:
                final_thg = self.addnewpos_final_thg
            elif hasattr(self, 'addnewpos_port_adjuster') and hasattr(self.addnewpos_port_adjuster, 'final_thg_distributor'):
                final_thg = self.addnewpos_port_adjuster.final_thg_distributor
                self.addnewpos_final_thg = final_thg
            
            if final_thg and hasattr(final_thg, 'show_jfin_orders'):
                # JFIN %50 BB emirlerini göster (excluded ticker kontrolü yapılacak)
                final_thg.show_jfin_orders('BB', 50)
                print("[ADDNEWPOS] ✅ JFIN %50 BB penceresi açıldı")
                self.log_message("✅ Adım 7: JFIN %50 BB penceresi açıldı")
                
                # Popup'ları kapat ve excluded ticker kontrolü yap
                def proceed_to_step_8():
                    # Popup'ları kontrol et ve kapat
                    self.addnewpos_close_messagebox()
                    # Excluded ticker kontrolü yap
                    self.addnewpos_step_8_exclude_check()
                    # Sonra emirleri otomatik gönder
                    self.after(2000, lambda: self.addnewpos_step_9_auto_send_orders())
                
                # JFIN onay penceresinin açılmasını bekle
                self.after(2000, proceed_to_step_8)
            else:
                print("[ADDNEWPOS] ❌ FinalThgLotDistributor veya show_jfin_orders bulunamadı")
                self.log_message("❌ Adım 7: JFIN %50 BB butonu bulunamadı")
        except Exception as e:
            print(f"[ADDNEWPOS] ❌ Adım 7 hatası: {e}")
            self.log_message(f"❌ Adım 7 hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def addnewpos_step_8_exclude_check(self):
        """Adım 8: Excluded ticker kontrolü ve onay penceresinde excluded ticker'ları çıkar"""
        try:
            self.log_message("📋 Adım 8: Excluded ticker kontrolü yapılıyor...")
            
            # FinalThgLotDistributor referansını al
            final_thg = None
            if hasattr(self, 'addnewpos_final_thg') and self.addnewpos_final_thg:
                final_thg = self.addnewpos_final_thg
            elif hasattr(self, 'addnewpos_port_adjuster') and hasattr(self.addnewpos_port_adjuster, 'final_thg_distributor'):
                final_thg = self.addnewpos_port_adjuster.final_thg_distributor
                self.addnewpos_final_thg = final_thg
            
            # FinalThgLotDistributor'daki JFIN onay penceresini bul
            if final_thg and hasattr(final_thg, 'win'):
                # Tüm açık pencereleri kontrol et
                for child in final_thg.win.winfo_children():
                    if isinstance(child, tk.Toplevel):
                        # JFIN onay penceresi bulundu
                        self.addnewpos_exclude_from_jfin_window(child)
                        return
                
                # Eğer doğrudan win'in altında değilse, tüm toplevel'leri kontrol et
                all_windows = []
                def find_toplevels(parent):
                    for widget in parent.winfo_children():
                        if isinstance(widget, tk.Toplevel):
                            all_windows.append(widget)
                        find_toplevels(widget)
                
                find_toplevels(final_thg.win)
                
                # JFIN onay penceresini bul (başlığında "JFIN" geçen)
                for win in all_windows:
                    try:
                        if "JFIN" in win.title():
                            self.addnewpos_exclude_from_jfin_window(win)
                            return
                    except:
                        continue
                
                # Eğer hala bulunamadıysa, tüm açık Toplevel pencerelerini kontrol et
                self.addnewpos_find_jfin_window_recursive(final_thg.win)
        except Exception as e:
            print(f"[ADDNEWPOS] ❌ Adım 8 hatası: {e}")
            self.log_message(f"❌ Adım 8 hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def addnewpos_exclude_from_jfin_window(self, jfin_window):
        """JFIN onay penceresinde excluded ticker'ları işaretleme kaldır ve toplam lot bildirimi göster"""
        try:
            from tkinter import messagebox
            
            # Excluded ticker'ları yükle
            self.load_excluded_tickers_from_csv()
            
            excluded_tickers_exist = hasattr(self, 'excluded_tickers') and self.excluded_tickers
            if not excluded_tickers_exist:
                print("[ADDNEWPOS] ℹ️ Excluded ticker yok, tüm emirler gönderilecek")
                self.log_message("ℹ️ Excluded ticker yok, tüm emirler gönderilecek")
            
            # JFIN penceresindeki treeview'ı bul
            order_tree = None
            for widget in jfin_window.winfo_children():
                if isinstance(widget, ttk.Treeview):
                    order_tree = widget
                    break
                # Frame içinde de olabilir
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Treeview):
                        order_tree = child
                        break
                    for grandchild in child.winfo_children():
                        if isinstance(grandchild, ttk.Treeview):
                            order_tree = grandchild
                            break
            
            if not order_tree:
                print("[ADDNEWPOS] ⚠️ JFIN onay penceresinde treeview bulunamadı")
                self.log_message("⚠️ JFIN onay penceresinde treeview bulunamadı")
                return
            
            # Excluded ticker'ları işaretleme kaldır ve toplam lot hesapla
            excluded_count = 0
            excluded_lot_total = 0
            remaining_lot_total = 0
            total_orders = 0
            remaining_orders = 0
            
            # Emir türünü belirle (Long mu Short mu?)
            order_type = "pozisyon arttırma"  # Varsayılan
            try:
                window_title = jfin_window.title()
                if "BB" in window_title or "FB" in window_title or "SoftFB" in window_title:
                    order_type = "pozisyon arttırma"  # Long
                elif "SAS" in window_title or "SFS" in window_title or "SoftFS" in window_title:
                    order_type = "pozisyon azaltma"  # Short
            except:
                pass
            
            for item in order_tree.get_children():
                values = list(order_tree.item(item)['values'])
                if len(values) >= 10:  # En az 10 kolon olmalı (Hesaplanan Lot kolonu için)
                    symbol = values[2]  # Sembol kolonu
                    # Hesaplanan Lot kolonu (index 9)
                    try:
                        calculated_lot_str = str(values[9]).replace(',', '').strip()
                        calculated_lot = int(float(calculated_lot_str)) if calculated_lot_str and calculated_lot_str != 'N/A' else 0
                    except (ValueError, TypeError, IndexError):
                        calculated_lot = 0
                    
                    total_orders += 1
                    
                    # Seçili emirlerin lot toplamını hesapla (excluded olmayanlar için)
                    if values[0] == '☑':  # Seçili ise
                        if excluded_tickers_exist and self.is_ticker_excluded(symbol):
                            # Excluded ticker - checkbox'ı kaldır (☐ yap)
                            values[0] = '☐'
                            order_tree.item(item, values=values, tags=('unselected',))
                            excluded_count += 1
                            excluded_lot_total += calculated_lot
                            print(f"[ADDNEWPOS] 🚫 {symbol} excluded - işaretleme kaldırıldı ({calculated_lot:,} lot)")
                        else:
                            # Seçili emir (excluded değil)
                            remaining_lot_total += calculated_lot
                            remaining_orders += 1
            
            # Bildirim mesajı oluştur
            if excluded_count > 0:
                self.log_message(f"✅ {excluded_count} excluded ticker işaretlemesi kaldırıldı ({excluded_lot_total:,} lot)")
                print(f"[ADDNEWPOS] ✅ {excluded_count} excluded ticker işaretlemesi kaldırıldı ({excluded_lot_total:,} lot)")
            
            # Toplam lot bildirimi göster
            if remaining_lot_total > 0:
                message = f"📊 {remaining_lot_total:,} lot {order_type} emri onay penceresine açıldı"
                if excluded_count > 0:
                    message += f"\n🚫 {excluded_count} ticker excluded ({excluded_lot_total:,} lot çıkarıldı)"
                message += f"\n✅ {remaining_orders} emir gönderilecek"
                
                print(f"[ADDNEWPOS] {message}")
                self.log_message(message)
                
                # Bildirim penceresi göster (Allowed modunda gösterme)
                if not (hasattr(self, 'runall_allowed_mode') and self.runall_allowed_mode):
                    messagebox.showinfo("ADDNEWPOS - Emir Özeti", message)
                else:
                    print(f"[ADDNEWPOS] ℹ️ Allowed modu aktif - Bildirim penceresi gösterilmedi")
            else:
                warning_msg = "⚠️ Hiç emir kalmadı! Tüm emirler excluded edilmiş olabilir."
                print(f"[ADDNEWPOS] {warning_msg}")
                self.log_message(warning_msg)
                messagebox.showwarning("Uyarı", warning_msg)
            
        except Exception as e:
            print(f"[ADDNEWPOS] ❌ Exclude kontrol hatası: {e}")
            self.log_message(f"❌ Exclude kontrol hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def addnewpos_find_jfin_window_recursive(self, parent):
        """Recursive olarak JFIN penceresini bul"""
        try:
            for widget in parent.winfo_children():
                if isinstance(widget, tk.Toplevel):
                    try:
                        if "JFIN" in widget.title():
                            self.addnewpos_exclude_from_jfin_window(widget)
                            # JFIN penceresini sakla (emir gönderme için)
                            self.addnewpos_jfin_window = widget
                            return
                    except:
                        pass
                # Recursive olarak devam et
                self.addnewpos_find_jfin_window_recursive(widget)
        except:
            pass
    
    def addnewpos_step_9_auto_send_orders(self):
        """Adım 9: JFIN onay penceresinde Emirleri Gönder butonuna otomatik tıkla"""
        try:
            self.log_message("📋 Adım 9: Emirleri Gönder butonuna otomatik tıklanıyor...")
            
            # JFIN penceresini bul
            jfin_window = None
            if hasattr(self, 'addnewpos_jfin_window'):
                jfin_window = self.addnewpos_jfin_window
            else:
                # FinalThgLotDistributor'dan JFIN penceresini bul
                final_thg = None
                if hasattr(self, 'addnewpos_final_thg') and self.addnewpos_final_thg:
                    final_thg = self.addnewpos_final_thg
                elif hasattr(self, 'addnewpos_port_adjuster') and hasattr(self.addnewpos_port_adjuster, 'final_thg_distributor'):
                    final_thg = self.addnewpos_port_adjuster.final_thg_distributor
                
                if final_thg and hasattr(final_thg, 'win'):
                    # Tüm açık pencereleri kontrol et
                    all_windows = []
                    def find_toplevels(parent):
                        for widget in parent.winfo_children():
                            if isinstance(widget, tk.Toplevel):
                                all_windows.append(widget)
                            find_toplevels(widget)
                    
                    find_toplevels(final_thg.win)
                    
                    # JFIN onay penceresini bul
                    for win in all_windows:
                        try:
                            if "JFIN" in win.title():
                                jfin_window = win
                                self.addnewpos_jfin_window = win
                                break
                        except:
                            continue
            
            if jfin_window:
                # "Emirleri Gönder" butonunu bul ve tıkla
                send_button = None
                
                def find_send_button(parent):
                    nonlocal send_button
                    if send_button:
                        return
                    try:
                        for widget in parent.winfo_children():
                            try:
                                # Button kontrolü
                                if isinstance(widget, (tk.Button, ttk.Button)):
                                    try:
                                        text = str(widget.cget('text')).lower()
                                        # "Emirleri Gönder" butonunu bul
                                        if 'gönder' in text or 'send' in text or ('emir' in text and 'gönder' in text):
                                            send_button = widget
                                            print(f"[ADDNEWPOS] ✅ Buton bulundu: '{widget.cget('text')}'")
                                            return
                                    except Exception as e:
                                        pass
                                
                                # Recursive olarak devam et
                                find_send_button(widget)
                            except Exception as e:
                                # Widget erişilemez olabilir, devam et
                                pass
                    except Exception as e:
                        pass
                
                find_send_button(jfin_window)
                
                if send_button:
                    print("[ADDNEWPOS] ✅ Emirleri Gönder butonu bulundu, tıklanıyor...")
                    self.log_message("✅ Adım 9: Emirleri Gönder butonuna tıklanıyor...")
                    try:
                        send_button.invoke()
                        print("[ADDNEWPOS] ✅ Emirleri Gönder butonuna tıklandı")
                        self.log_message("✅ Adım 9: Emirleri Gönder butonuna tıklandı")
                    except Exception as e:
                        print(f"[ADDNEWPOS] ⚠️ Buton tıklama hatası: {e}")
                        self.log_message(f"⚠️ Adım 9: Buton tıklama hatası: {e}")
                else:
                    # Hala bulunamadıysa tekrar dene (max 5 kez)
                    if not hasattr(self, 'addnewpos_send_retry_count'):
                        self.addnewpos_send_retry_count = 0
                    
                    self.addnewpos_send_retry_count += 1
                    if self.addnewpos_send_retry_count < 5:
                        print(f"[ADDNEWPOS] ⚠️ Emirleri Gönder butonu bulunamadı, tekrar denenecek... ({self.addnewpos_send_retry_count}/5)")
                        self.log_message(f"⚠️ Adım 9: Emirleri Gönder butonu bulunamadı, tekrar denenecek... ({self.addnewpos_send_retry_count}/5)")
                        # 2 saniye sonra tekrar dene
                        self.after(2000, lambda: self.addnewpos_step_9_auto_send_orders())
                    else:
                        print("[ADDNEWPOS] ❌ Emirleri Gönder butonu 5 denemede bulunamadı, manuel gönderilmesi gerekiyor")
                        self.log_message("❌ Adım 9: Emirleri Gönder butonu bulunamadı, lütfen manuel gönderin")
                        self.addnewpos_send_retry_count = 0  # Reset
            else:
                print("[ADDNEWPOS] ⚠️ JFIN onay penceresi bulunamadı")
                self.log_message("⚠️ Adım 9: JFIN onay penceresi bulunamadı")
        except Exception as e:
            print(f"[ADDNEWPOS] ❌ Adım 9 hatası: {e}")
            self.log_message(f"❌ Adım 9 hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def toggle_controller(self):
        """Controller ON/OFF toggle"""
        try:
            self.controller_enabled = not self.controller_enabled
            
            if self.controller_enabled:
                self.controller_btn.config(text="🎛️ Controller: ON")
                self.controller_btn.config(style='Success.TButton')
                print("[CONTROLLER] ✅ Controller: ON")
                self.log_message("✅ Controller: ON - Pozisyon kontrolü aktif")
            else:
                self.controller_btn.config(text="🎛️ Controller: OFF")
                self.controller_btn.config(style='Accent.TButton')
                print("[CONTROLLER] ❌ Controller: OFF")
                self.log_message("❌ Controller: OFF - Pozisyon kontrolü kapalı")
                
        except Exception as e:
            print(f"[CONTROLLER] ❌ Toggle hatası: {e}")
            self.log_message(f"❌ Controller toggle hatası: {e}")
    
    def start_karbotu_automation(self):
        """KARBOTU otomasyonunu başlat"""
        try:
            print("[KARBOTU] 🎯 KARBOTU otomasyonu başlatılıyor...")
            self.log_message("🎯 KARBOTU otomasyonu başlatılıyor...")
            
            # KARBOTU adımlarını başlat
            self.karbotu_current_step = 1
            self.karbotu_total_steps = 13
            self.karbotu_running = True
            
            # İlk adım: Take Profit Longs penceresini aç
            self.karbotu_step_1_open_take_profit_longs()
            
        except Exception as e:
            print(f"[KARBOTU] ❌ Otomasyon başlatma hatası: {e}")
            self.log_message(f"❌ KARBOTU başlatma hatası: {e}")
            messagebox.showerror("Hata", f"KARBOTU başlatılamadı: {e}")
    
    def karbotu_step_1_open_take_profit_longs(self):
        """Adım 1: Take Profit Longs penceresini aç"""
        try:
            print("[KARBOTU] 📋 Adım 1: Take Profit Longs penceresi açılıyor...")
            self.log_message("📋 Adım 1: Take Profit Longs penceresi açılıyor...")
            
            # Take Profit Longs penceresini aç
            from .take_profit_panel import TakeProfitPanel
            self.take_profit_longs_panel = TakeProfitPanel(self, "longs")
            
            # Adım 2'ye geç
            self.karbotu_current_step = 2
            self.karbotu_step_2_fbtot_lt_110()
            
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 1 hatası: {e}")
            self.log_message(f"❌ Adım 1 hatası: {e}")
    
    def karbotu_step_2_fbtot_lt_110(self):
        """Adım 2: Fbtot < 1.10 ve Ask Sell pahalılık > -0.10"""
        try:
            print("[KARBOTU] 📋 Adım 2: Fbtot < 1.10 kontrolü...")
            self.log_message("📋 Adım 2: Fbtot < 1.10 ve Ask Sell pahalılık > -0.10")
            
            # Lot yüzdesi: %50
            lot_percentage = 50
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel.tree.get_children():
                values = self.take_profit_longs_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]  # Fbtot kolonu
                ask_sell_pahalilik_str = values[8]  # Ask Sell Pahalılık kolonu
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            # $ işaretini kaldır ve float'a çevir
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot < 1.10 ve Ask Sell pahalılık > -0.10
                    if fbtot < 1.10 and ask_sell_pahalilik > -0.10:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 2: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 2: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_longs_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, Fbtot={pos['fbtot']:.2f}, Ask Sell Pahalılık=${pos['ask_sell_pahalilik']:.4f}")
                
                # Pozisyonları seç ve %50 lot ile Ask Sell onay penceresi aç
                self.karbotu_select_positions_and_confirm(filtered_positions, "Ask Sell", 50, "Adım 2")
            else:
                print("[KARBOTU] ⚠️ Adım 2: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 2: Koşula uygun pozisyon bulunamadı")
                # Adım 3'e geç
                self.karbotu_current_step = 3
                self.karbotu_step_3_fbtot_111_145_low()
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 2 hatası: {e}")
            self.log_message(f"❌ Adım 2 hatası: {e}")
    
    def karbotu_step_3_fbtot_111_145_low(self):
        """Adım 3: Fbtot 1.11-1.45 ve Ask Sell pahalılık -0.05 ile +0.04 arası"""
        try:
            print("[KARBOTU] 📋 Adım 3: Fbtot 1.11-1.45 kontrolü...")
            self.log_message("📋 Adım 3: Fbtot 1.11-1.45 ve Ask Sell pahalılık -0.05 ile +0.04 arası")
            
            # Lot yüzdesi: %25
            lot_percentage = 25
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel.tree.get_children():
                values = self.take_profit_longs_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]
                ask_sell_pahalilik_str = values[8]
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot 1.11-1.45 ve Ask Sell pahalılık -0.05 ile +0.04 arası
                    if 1.11 <= fbtot <= 1.45 and -0.05 <= ask_sell_pahalilik <= 0.04:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 3: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 3: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_longs_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, Fbtot={pos['fbtot']:.2f}, Ask Sell Pahalılık=${pos['ask_sell_pahalilik']:.4f}")
                
                # Pozisyonları seç ve %25 lot ile Ask Sell onay penceresi aç
                self.karbotu_select_positions_and_confirm(filtered_positions, "Ask Sell", 25, "Adım 3")
            else:
                print("[KARBOTU] ⚠️ Adım 3: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 3: Koşula uygun pozisyon bulunamadı")
                # Adım 4'e geç
                self.karbotu_current_step = 4
                self.karbotu_step_4_fbtot_111_145_high()
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 3 hatası: {e}")
            self.log_message(f"❌ Adım 3 hatası: {e}")
    
    def karbotu_step_4_fbtot_111_145_high(self):
        """Adım 4: Fbtot 1.11-1.45 ve Ask Sell pahalılık > +0.05"""
        try:
            print("[KARBOTU] 📋 Adım 4: Fbtot 1.11-1.45 yüksek kontrolü...")
            self.log_message("📋 Adım 4: Fbtot 1.11-1.45 ve Ask Sell pahalılık > +0.05")
            
            # Lot yüzdesi: %50
            lot_percentage = 50
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel.tree.get_children():
                values = self.take_profit_longs_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]
                ask_sell_pahalilik_str = values[8]
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot 1.11-1.45 ve Ask Sell pahalılık > +0.05
                    if 1.11 <= fbtot <= 1.45 and ask_sell_pahalilik > 0.05:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 4: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 4: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_longs_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, Fbtot={pos['fbtot']:.2f}, Ask Sell Pahalılık=${pos['ask_sell_pahalilik']:.4f}")
                
                # Pozisyonları seç ve %50 lot ile Ask Sell onay penceresi aç
                self.karbotu_select_positions_and_confirm(filtered_positions, "Ask Sell", 50, "Adım 4")
            else:
                print("[KARBOTU] ⚠️ Adım 4: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 4: Koşula uygun pozisyon bulunamadı")
                # Adım 5'e geç
                self.karbotu_current_step = 5
                self.karbotu_step_5_fbtot_146_185_low()
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 4 hatası: {e}")
            self.log_message(f"❌ Adım 4 hatası: {e}")
    
    def karbotu_step_5_fbtot_146_185_low(self):
        """Adım 5: Fbtot 1.46-1.85 ve Ask Sell pahalılık +0.05 ile +0.10 arası"""
        try:
            print("[KARBOTU] 📋 Adım 5: Fbtot 1.46-1.85 kontrolü...")
            self.log_message("📋 Adım 5: Fbtot 1.46-1.85 ve Ask Sell pahalılık +0.05 ile +0.10 arası")
            
            # Lot yüzdesi: %25
            lot_percentage = 25
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel.tree.get_children():
                values = self.take_profit_longs_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]
                ask_sell_pahalilik_str = values[8]
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot 1.46-1.85 ve Ask Sell pahalılık +0.05 ile +0.10 arası
                    if 1.46 <= fbtot <= 1.85 and 0.05 <= ask_sell_pahalilik <= 0.10:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 5: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 5: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_longs_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, Fbtot={pos['fbtot']:.2f}, Ask Sell Pahalılık=${pos['ask_sell_pahalilik']:.4f}")
                
                # Pozisyonları seç ve %25 lot ile Ask Sell onay penceresi aç
                self.karbotu_select_positions_and_confirm(filtered_positions, "Ask Sell", 25, "Adım 5")
            else:
                print("[KARBOTU] ⚠️ Adım 5: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 5: Koşula uygun pozisyon bulunamadı")
                # Adım 6'ya geç
                self.karbotu_current_step = 6
                self.karbotu_step_6_fbtot_146_185_high()
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 5 hatası: {e}")
            self.log_message(f"❌ Adım 5 hatası: {e}")
    
    def karbotu_step_6_fbtot_146_185_high(self):
        """Adım 6: Fbtot 1.46-1.85 ve Ask Sell pahalılık > +0.10"""
        try:
            print("[KARBOTU] 📋 Adım 6: Fbtot 1.46-1.85 yüksek kontrolü...")
            self.log_message("📋 Adım 6: Fbtot 1.46-1.85 ve Ask Sell pahalılık > +0.10")
            
            # Lot yüzdesi: %50
            lot_percentage = 50
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel.tree.get_children():
                values = self.take_profit_longs_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]
                ask_sell_pahalilik_str = values[8]
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot 1.46-1.85 ve Ask Sell pahalılık > +0.10
                    if 1.46 <= fbtot <= 1.85 and ask_sell_pahalilik > 0.10:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 6: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 6: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_longs_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, Fbtot={pos['fbtot']:.2f}, Ask Sell Pahalılık=${pos['ask_sell_pahalilik']:.4f}")
                
                # Pozisyonları seç ve %50 lot ile Ask Sell onay penceresi aç
                self.karbotu_select_positions_and_confirm(filtered_positions, "Ask Sell", 50, "Adım 6")
            else:
                print("[KARBOTU] ⚠️ Adım 6: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 6: Koşula uygun pozisyon bulunamadı")
                # Adım 7'ye geç
                self.karbotu_current_step = 7
                self.karbotu_step_7_fbtot_186_210()
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 6 hatası: {e}")
            self.log_message(f"❌ Adım 6 hatası: {e}")
    
    def karbotu_step_7_fbtot_186_210(self):
        """Adım 7: Fbtot 1.86-2.10 ve Ask Sell pahalılık > +0.20"""
        try:
            print("[KARBOTU] 📋 Adım 7: Fbtot 1.86-2.10 kontrolü...")
            self.log_message("📋 Adım 7: Fbtot 1.86-2.10 ve Ask Sell pahalılık > +0.20")
            
            # Lot yüzdesi: %25
            lot_percentage = 25
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel.tree.get_children():
                values = self.take_profit_longs_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]
                ask_sell_pahalilik_str = values[8]
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot 1.86-2.10 ve Ask Sell pahalılık > +0.20
                    if 1.86 <= fbtot <= 2.10 and ask_sell_pahalilik > 0.20:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 7: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 7: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_longs_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, Fbtot={pos['fbtot']:.2f}, Ask Sell Pahalılık=${pos['ask_sell_pahalilik']:.4f}")
                
                # Pozisyonları seç ve %25 lot ile Ask Sell onay penceresi aç
                self.karbotu_select_positions_and_confirm(filtered_positions, "Ask Sell", 25, "Adım 7")
            else:
                print("[KARBOTU] ⚠️ Adım 7: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 7: Koşula uygun pozisyon bulunamadı")
                # Adım 8'e geç - Take Profit Shorts aç
                self.karbotu_current_step = 8
                self.karbotu_step_8_open_take_profit_shorts()
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 7 hatası: {e}")
            self.log_message(f"❌ Adım 7 hatası: {e}")
    
    def karbotu_step_8_open_take_profit_shorts(self):
        """Adım 8: Take Profit Longs kapat ve Take Profit Shorts aç"""
        try:
            print("[KARBOTU] 📋 Adım 8: Take Profit Shorts penceresi açılıyor...")
            self.log_message("📋 Adım 8: Take Profit Shorts penceresi açılıyor...")
            
            # Take Profit Longs penceresini kapat
            if hasattr(self, 'take_profit_longs_panel') and self.take_profit_longs_panel:
                self.take_profit_longs_panel.win.destroy()
            
            # Take Profit Shorts penceresini aç
            from .take_profit_panel import TakeProfitPanel
            self.take_profit_shorts_panel = TakeProfitPanel(self, "shorts")
            
            # Adım 9'a geç
            self.karbotu_current_step = 9
            self.karbotu_step_9_sfstot_170_high()
            
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 8 hatası: {e}")
            self.log_message(f"❌ Adım 8 hatası: {e}")
    
    def karbotu_step_9_sfstot_170_high(self):
        """Adım 9: SFStot > 1.70 ve Bid Buy ucuzluk < +0.10"""
        try:
            print("[KARBOTU] 📋 Adım 9: SFStot > 1.70 kontrolü...")
            self.log_message("📋 Adım 9: SFStot > 1.70 ve Bid Buy ucuzluk < +0.10")
            
            # Lot yüzdesi: %50
            lot_percentage = 50
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_shorts_panel.tree.get_children():
                values = self.take_profit_shorts_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                sfstot_str = values[5]  # SFStot kolonu
                bid_buy_ucuzluk_str = values[8]  # Bid Buy Ucuzluk kolonu
                
                try:
                    # SFStot'u güvenli şekilde parse et
                    sfstot = 0
                    if sfstot_str != 'N/A' and sfstot_str:
                        try:
                            sfstot = float(sfstot_str)
                        except (ValueError, TypeError):
                            sfstot = 0
                    
                    # SFStot 0.0 veya N/A ise skip et
                    if sfstot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Bid Buy ucuzluk skorunu güvenli şekilde parse et
                    bid_buy_ucuzluk = 0
                    if bid_buy_ucuzluk_str != 'N/A' and bid_buy_ucuzluk_str:
                        try:
                            clean_str = str(bid_buy_ucuzluk_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                bid_buy_ucuzluk = float(clean_str)
                        except (ValueError, TypeError):
                            bid_buy_ucuzluk = 0
                    
                    # Koşul: SFStot > 1.70 ve Bid Buy ucuzluk < +0.10
                    if sfstot > 1.70 and bid_buy_ucuzluk < 0.10:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'sfstot': sfstot,
                            'bid_buy_ucuzluk': bid_buy_ucuzluk
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 9: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 9: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_shorts_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, SFStot={pos['sfstot']:.2f}, Bid Buy Ucuzluk=${pos['bid_buy_ucuzluk']:.4f}")
                
                # Pozisyonları seç ve %50 lot ile Bid Buy onay penceresi aç
                self.karbotu_select_shorts_positions_and_confirm(filtered_positions, "Bid Buy", 50, "Adım 9")
            else:
                print("[KARBOTU] ⚠️ Adım 9: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 9: Koşula uygun pozisyon bulunamadı")
                # Adım 10'a geç
                self.karbotu_current_step = 10
                self.karbotu_step_10_sfstot_140_169_low()
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 9 hatası: {e}")
            self.log_message(f"❌ Adım 9 hatası: {e}")
    
    def karbotu_step_10_sfstot_140_169_low(self):
        """Adım 10: SFStot 1.40-1.69 ve Bid Buy ucuzluk +0.05 ile -0.04 arası"""
        try:
            print("[KARBOTU] 📋 Adım 10: SFStot 1.40-1.69 kontrolü...")
            self.log_message("📋 Adım 10: SFStot 1.40-1.69 ve Bid Buy ucuzluk +0.05 ile -0.04 arası")
            
            # Lot yüzdesi: %25
            lot_percentage = 25
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_shorts_panel.tree.get_children():
                values = self.take_profit_shorts_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                sfstot_str = values[5]
                bid_buy_ucuzluk_str = values[8]
                
                try:
                    # SFStot'u güvenli şekilde parse et
                    sfstot = 0
                    if sfstot_str != 'N/A' and sfstot_str:
                        try:
                            sfstot = float(sfstot_str)
                        except (ValueError, TypeError):
                            sfstot = 0
                    
                    # SFStot 0.0 veya N/A ise skip et
                    if sfstot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Bid Buy ucuzluk skorunu güvenli şekilde parse et
                    bid_buy_ucuzluk = 0
                    if bid_buy_ucuzluk_str != 'N/A' and bid_buy_ucuzluk_str:
                        try:
                            clean_str = str(bid_buy_ucuzluk_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                bid_buy_ucuzluk = float(clean_str)
                        except (ValueError, TypeError):
                            bid_buy_ucuzluk = 0
                    
                    # Koşul: SFStot 1.40-1.69 ve Bid Buy ucuzluk +0.05 ile -0.04 arası
                    if 1.40 <= sfstot <= 1.69 and -0.04 <= bid_buy_ucuzluk <= 0.05:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'sfstot': sfstot,
                            'bid_buy_ucuzluk': bid_buy_ucuzluk
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 10: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 10: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_shorts_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, SFStot={pos['sfstot']:.2f}, Bid Buy Ucuzluk=${pos['bid_buy_ucuzluk']:.4f}")
                
                # Pozisyonları seç ve %25 lot ile Bid Buy onay penceresi aç
                self.karbotu_select_shorts_positions_and_confirm(filtered_positions, "Bid Buy", 25, "Adım 10")
            else:
                print("[KARBOTU] ⚠️ Adım 10: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 10: Koşula uygun pozisyon bulunamadı")
                # Adım 11'e geç
                self.karbotu_current_step = 11
                self.karbotu_step_11_sfstot_140_169_high()
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 10 hatası: {e}")
            self.log_message(f"❌ Adım 10 hatası: {e}")
    
    def karbotu_select_shorts_positions_and_confirm(self, positions, order_type, lot_percentage, step_name):
        """Shorts pozisyonları seç ve onay penceresi aç"""
        try:
            # Pozisyonları seç
            for pos in positions:
                self.take_profit_shorts_panel.tree.set(pos['item'], "select", "✓")
                
                # Avg cost'u güvenli şekilde parse et
                avg_cost_str = self.take_profit_shorts_panel.tree.item(pos['item'])['values'][3]
                avg_cost = 0
                if avg_cost_str and avg_cost_str != 'N/A':
                    try:
                        clean_str = str(avg_cost_str).replace('$', '').replace(',', '').strip()
                        if clean_str and clean_str != 'nan':
                            avg_cost = float(clean_str)
                    except (ValueError, TypeError):
                        avg_cost = 0
                
                self.take_profit_shorts_panel.selected_positions[pos['symbol']] = {
                    'qty': float(self.take_profit_shorts_panel.tree.item(pos['item'])['values'][2]),
                    'avg_cost': avg_cost
                }
            
            # Lot yüzdesini ayarla
            if lot_percentage == 25:
                self.take_profit_shorts_panel.set_lot_percentage(25)
            elif lot_percentage == 50:
                self.take_profit_shorts_panel.set_lot_percentage(50)
            
            # Onay penceresini aç
            self.karbotu_show_shorts_confirmation_window(positions, order_type, lot_percentage, step_name)
            
        except Exception as e:
            print(f"[KARBOTU] ❌ Shorts pozisyon seçimi hatası: {e}")
            self.log_message(f"❌ Shorts pozisyon seçimi hatası: {e}")
    
    def karbotu_send_shorts_orders_direct(self, positions, order_type, lot_percentage, step_name):
        """KARBOTU Shorts emirlerini direkt gönder (Allowed modunda onay penceresi olmadan)"""
        try:
            print(f"[KARBOTU SHORTS] 🔄 {step_name} emirleri direkt gönderiliyor (Allowed modu)...")
            self.log_message(f"🔄 {step_name} emirleri direkt gönderiliyor (Allowed modu)...")
            
            # Pozisyon verilerini hazırla
            order_data = {}
            
            for pos in positions:
                item_values = self.take_profit_shorts_panel.tree.item(pos['item'])['values']
                symbol = pos['symbol']
                qty = float(item_values[2])  # Negatif gelebilir
                abs_qty = abs(qty)
                
                # Lot hesapla
                calculated_lot = abs_qty * (lot_percentage / 100)
                
                # Lot yuvarlama
                if lot_percentage == 100:
                    lot_qty = int(calculated_lot)
                elif calculated_lot > 0:
                    if calculated_lot <= 0:
                        lot_qty = 0
                    elif calculated_lot <= 100:
                        lot_qty = 100
                    elif calculated_lot <= 200:
                        lot_qty = 200
                    elif calculated_lot <= 300:
                        lot_qty = 300
                    elif calculated_lot <= 400:
                        lot_qty = 400
                    elif calculated_lot <= 500:
                        lot_qty = 500
                    else:
                        lot_qty = int((calculated_lot + 99) // 100) * 100
                else:
                    lot_qty = 0
                
                # MAXALW*3/4 limit kontrolü
                maxalw = self.get_maxalw_for_symbol(symbol)
                max_change_limit = maxalw * 3 / 4 if maxalw > 0 else 0
                
                # Gün başı pozisyon
                befday_qty = self.load_bef_position(symbol)
                
                # Mevcut pozisyon ve açık emirler
                current_qty = qty
                open_orders_qty = self.get_open_orders_sum(symbol, use_cache=True)
                current_potential = current_qty + open_orders_qty
                
                # Günlük değişim (mutlak değer)
                current_daily_change = abs(current_potential - befday_qty)
                
                # Yeni emir sonrası potansiyel değişim (Bid Buy = short pozisyonu azaltır)
                new_potential = current_potential + lot_qty  # Short pozisyonu azaltır (daha az negatif)
                potential_daily_change = abs(new_potential - befday_qty)
                
                # MAXALW*3/4 limitini aşacaksa emir gönderme
                if potential_daily_change > max_change_limit:
                    print(f"[KARBOTU SHORTS] ⚠️ {symbol}: MAXALW*3/4 limiti aşılacak ({potential_daily_change:.0f} > {max_change_limit:.0f}), emir atlandı")
                    self.log_message(f"⚠️ {symbol}: MAXALW*3/4 limiti aşılacak, emir atlandı")
                    continue
                
                # Emir fiyatını hesapla
                market_data = None
                if hasattr(self, 'hammer') and self.hammer:
                    market_data = self.hammer.get_market_data(symbol)
                
                if not market_data:
                    print(f"[KARBOTU SHORTS] ❌ {symbol} market_data bulunamadı, atlandı")
                    continue
                
                bid = float(market_data.get('bid', 0))
                ask = float(market_data.get('ask', 0))
                last = float(market_data.get('last', 0))
                
                emir_fiyat = 0
                if order_type == "Bid Buy":
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = bid + (spread * 0.15)
                    else:
                        continue
                elif order_type == "Ask Sell":
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = ask - (spread * 0.15)
                    else:
                        continue
                
                if emir_fiyat > 0 and lot_qty != 0:
                    order_data[symbol] = {'price': emir_fiyat, 'lot': lot_qty}
            
            # Emirleri gönder
            success_count = 0
            for symbol in order_data:
                data = order_data[symbol]
                emir_fiyat = data['price']
                lot_qty = data['lot']
                
                if abs(lot_qty) < 200:
                    continue
                
                # Controller kontrolü (MAXALW limitleri dahil)
                if hasattr(self, 'controller_enabled') and self.controller_enabled:
                    order_side = "BUY"  # Short pozisyonu kapatmak için BUY
                    allowed, adjusted_qty, reason = self.controller_check_order(symbol, order_side, abs(lot_qty))
                    
                    if not allowed or adjusted_qty == 0:
                        print(f"[KARBOTU SHORTS] ⚠️ {symbol}: Controller engelledi - {reason}")
                        self.log_message(f"⚠️ {symbol}: Controller engelledi - {reason}")
                        continue
                    
                    lot_qty = adjusted_qty
                
                # Emir gönder
                if self.mode_manager.is_hammer_mode():
                    hammer_symbol = symbol.replace(" PR", "-")
                    try:
                        success = self.hammer.place_order(
                            symbol=hammer_symbol,
                            side="BUY",
                            quantity=lot_qty,
                            price=emir_fiyat,
                            order_type="LIMIT",
                            hidden=True
                        )
                        if success or "new order sent" in str(success):
                            success_count += 1
                            print(f"[KARBOTU SHORTS] ✅ {symbol}: Bid Buy {lot_qty} lot @ ${emir_fiyat:.2f}")
                    except Exception as e:
                        if "new order sent" in str(e).lower():
                            success_count += 1
                        else:
                            print(f"[KARBOTU SHORTS] ❌ {symbol}: {e}")
                else:
                    success = self.mode_manager.place_order(
                        symbol=symbol,
                        side="BUY",
                        quantity=lot_qty,
                        price=emir_fiyat,
                        order_type="LIMIT",
                        hidden=True
                    )
                    if success:
                        success_count += 1
                        print(f"[KARBOTU SHORTS] ✅ {symbol}: Bid Buy {lot_qty} lot @ ${emir_fiyat:.2f}")
            
            print(f"[KARBOTU SHORTS] ✅ {step_name} tamamlandı: {success_count} emir gönderildi")
            self.log_message(f"✅ {step_name} tamamlandı: {success_count} emir gönderildi")
            
            # Sonraki adıma geç (kısa bir bekleme ile - adımlar sıralı ilerlesin)
            self.after(1000, self.karbotu_proceed_to_next_step)
            
        except Exception as e:
            print(f"[KARBOTU SHORTS] ❌ Direkt emir gönderme hatası: {e}")
            self.log_message(f"❌ Direkt emir gönderme hatası: {e}")
            import traceback
            traceback.print_exc()
            # Hata olsa bile sonraki adıma geç (kısa bir bekleme ile)
            self.after(1000, self.karbotu_proceed_to_next_step)
    
    def karbotu_show_shorts_confirmation_window(self, positions, order_type, lot_percentage, step_name):
        """KARBOTU Shorts onay penceresi göster"""
        try:
            # RUNALL Allowed modunda otomatik onay kontrolü
            if hasattr(self, 'runall_allowed_mode') and self.runall_allowed_mode:
                print(f"[KARBOTU SHORTS] ✅ Allowed modu aktif - Onay penceresi atlanıyor, emirler direkt gönderiliyor")
                self.log_message(f"✅ Allowed modu: {step_name} (Shorts) - Emirler otomatik gönderiliyor")
                # Emirleri direkt gönder (onay penceresi açmadan)
                self.karbotu_send_shorts_orders_direct(positions, order_type, lot_percentage, step_name)
                return
            
            # Onay penceresi
            confirm_win = tk.Toplevel(self.psfalgo_window)
            confirm_win.title(f"KARBOTU - {step_name}")
            confirm_win.geometry("600x400")
            confirm_win.transient(self.psfalgo_window)
            # grab_set() kaldırıldı - minimize edilebilir olması için
            
            # Başlık frame - minimize butonu ile
            title_frame = ttk.Frame(confirm_win)
            title_frame.pack(fill='x', padx=10, pady=10)
            
            # Sol taraf - başlık bilgileri
            title_left = ttk.Frame(title_frame)
            title_left.pack(side='left', fill='x', expand=True)
            
            ttk.Label(title_left, text=f"KARBOTU - {step_name}", font=('Arial', 14, 'bold')).pack(anchor='w')
            ttk.Label(title_left, text=f"{order_type} - %{lot_percentage} Lot", font=('Arial', 12)).pack(anchor='w')
            ttk.Label(title_left, text=f"{len(positions)} pozisyon seçildi", font=('Arial', 10)).pack(anchor='w')
            
            # Sağ taraf - minimize butonu
            window_controls = ttk.Frame(title_frame)
            window_controls.pack(side='right')
            
            # Alta Al (Minimize) butonu
            minimize_btn = ttk.Button(window_controls, text="🗕 Alta Al", width=10,
                                      command=lambda: confirm_win.iconify())
            minimize_btn.pack(side='left', padx=2)
            
            # Pozisyon listesi
            list_frame = ttk.Frame(confirm_win)
            list_frame.pack(fill='both', expand=True, padx=10, pady=5)
            
            # Treeview
            columns = ('Symbol', 'Qty', 'Lot', 'SFStot', 'Bid Buy Ucuzluk', 'Emir Fiyat')
            pos_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)
            
            # Kolon genişlikleri
            col_widths = {'Symbol': 80, 'Qty': 60, 'Lot': 60, 'SFStot': 60, 'Bid Buy Ucuzluk': 100, 'Emir Fiyat': 80}
            for col in columns:
                pos_tree.heading(col, text=col)
                pos_tree.column(col, width=col_widths[col])
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=pos_tree.yview)
            pos_tree.configure(yscrollcommand=scrollbar.set)
            
            pos_tree.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # ✅ FİYAT VE LOT DEPOSU - pencereye özel
            order_data = {}  # {symbol: {'price': emir_fiyat, 'lot': lot_qty}}
            
            # Pozisyonları ekle
            for pos in positions:
                # Pozisyon verilerini al
                item_values = self.take_profit_shorts_panel.tree.item(pos['item'])['values']
                qty = float(item_values[2])  # Negatif gelebilir (-276 gibi)
                
                # Short pozisyonlar için ABS değer ile hesapla
                abs_qty = abs(qty)  # -276 -> 276
                calculated_lot = abs_qty * (lot_percentage / 100)  # 276 * 0.75 = 207
                
                # %100 lot için yuvarlama YAPILMAZ - tam lot miktarı kullanılır
                if lot_percentage == 100:
                    lot_qty = int(calculated_lot)  # 276 (pozitif)
                # Lot yuvarlama (%50 ve %25 için) - pozitif değer ile yuvarlama yap
                elif calculated_lot > 0:
                    # Pozitif sayılar için normal yuvarlama
                    if calculated_lot <= 0:
                        lot_qty = 0
                    elif calculated_lot <= 100:
                        lot_qty = 100
                    elif calculated_lot <= 200:
                        lot_qty = 200
                    elif calculated_lot <= 300:
                        lot_qty = 300
                    elif calculated_lot <= 400:
                        lot_qty = 400
                    elif calculated_lot <= 500:
                        lot_qty = 500
                    elif calculated_lot <= 600:
                        lot_qty = 600
                    elif calculated_lot <= 700:
                        lot_qty = 700
                    elif calculated_lot <= 800:
                        lot_qty = 800
                    elif calculated_lot <= 900:
                        lot_qty = 900
                    elif calculated_lot <= 1000:
                        lot_qty = 1000
                    else:
                        lot_qty = int((calculated_lot + 99) // 100) * 100
                else:
                    lot_qty = 0
                
                # Lot her zaman pozitif olmalı (BUY emri için short pozisyonu kapatmak için)
                # qty negatif olsa bile (short pozisyon), lot pozitif hesaplanır
                
                # Emir fiyatını hesapla (emir tipine göre)
                symbol = pos['symbol']
                emir_fiyat = 0
                
                # JFIN ile BIREBIR aynı mantık - Longs ile BIREBIR AYNI
                print(f"[KARBOTU SHORTS] 🔍 {symbol} JFIN mantığı ile fiyat hesaplanıyor...")
                
                # JFIN'in calculate_order_price metodunu kopyala - AYNI MANTIK
                market_data = None
                
                if hasattr(self, 'hammer') and self.hammer:
                    market_data = self.hammer.get_market_data(symbol)
                    if not market_data:
                        emir_fiyat = 0
                        print(f"[KARBOTU SHORTS] ❌ {symbol} market_data boş - JFIN gibi N/A döndürülüyor")
                        continue
                else:
                    emir_fiyat = 0
                    print(f"[KARBOTU SHORTS] ❌ {symbol} Hammer yok - JFIN gibi N/A döndürülüyor")
                    continue
                
                bid = float(market_data.get('bid', 0))
                ask = float(market_data.get('ask', 0))
                last = float(market_data.get('last', 0))
                
                print(f"[KARBOTU SHORTS DEBUG] 📊 {symbol} JFIN market_data: bid=${bid:.2f}, ask=${ask:.2f}, last=${last:.2f}")
                
                # JFIN'in tam mantığını kopyala
                if order_type == "Bid Buy":
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = bid + (spread * 0.15)
                        print(f"[KARBOTU SHORTS] ✅ {symbol} Bid Buy (JFIN): bid=${bid:.2f} + spread*0.15=${spread*0.15:.2f} = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU SHORTS] ❌ {symbol} Bid Buy: bid/ask değerleri geçersiz")
                elif order_type == "Ask Sell":
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = ask - (spread * 0.15)
                        print(f"[KARBOTU SHORTS] ✅ {symbol} Ask Sell (JFIN): ask=${ask:.2f} - spread*0.15=${spread*0.15:.2f} = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU SHORTS] ❌ {symbol} Ask Sell: bid/ask değerleri geçersiz")
                else:
                    # Bilinmeyen emir tipi için Bid Buy formülü kullan (shorts için)
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = bid + (spread * 0.15)
                        print(f"[KARBOTU SHORTS] ✅ {symbol} {order_type} (JFIN default): bid=${bid:.2f} + spread*0.15=${spread*0.15:.2f} = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU SHORTS] ❌ {symbol} {order_type}: bid/ask değerleri geçersiz")
                
                pos_tree.insert('', 'end', values=(
                    pos['symbol'],
                    f"{qty:.0f}",
                    f"{lot_qty:.0f}",
                    f"{pos['sfstot']:.2f}",
                    f"${pos['bid_buy_ucuzluk']:.4f}",
                    f"${emir_fiyat:.2f}"
                ))
                
                # ✅ FİYAT VE LOT DEPOSAYA KAYDET
                if emir_fiyat > 0 and lot_qty != 0:
                    order_data[symbol] = {'price': emir_fiyat, 'lot': lot_qty}
                    print(f"[KARBOTU SHORTS] ✅ {symbol} depoya kaydedildi: fiyat=${emir_fiyat:.2f}, lot={lot_qty}")
                else:
                    print(f"[KARBOTU SHORTS] ⚠️ {symbol} geçersiz: fiyat=${emir_fiyat:.2f}, lot={lot_qty}")
            
            # Butonlar
            button_frame = ttk.Frame(confirm_win)
            button_frame.pack(fill='x', padx=10, pady=10)
            
            def on_confirm():
                """Onay verildi - Emirleri gönder - DEPODAN FİYATLARI KULLAN"""
                try:
                    print(f"[KARBOTU] 🔄 {step_name} emirleri gönderiliyor...")
                    self.log_message(f"🔄 {step_name} emirleri gönderiliyor...")
                    
                    # ✅ DEPODAN FİYATLARI KULLAN - Market data çekme YOK
                    for symbol in order_data:
                        data = order_data[symbol]
                        emir_fiyat = data['price']
                        lot_qty = data['lot']
                        
                        # ✅ Minimum 200 lot kontrolü - 200'den azsa skip et
                        if abs(lot_qty) < 200:
                            print(f"[KARBOTU] ⚠️ {symbol}: lot={lot_qty} < 200, atlandı")
                            continue
                        
                        print(f"[KARBOTU] 📤 {symbol}: fiyat=${emir_fiyat:.2f}, lot={lot_qty}")
                        
                        # Emir gönder
                        if self.mode_manager.is_hammer_mode():
                            # Hammer Pro - Symbol dönüşümü
                            hammer_symbol = symbol.replace(" PR", "-")
                            
                            try:
                                success = self.hammer.place_order(
                                    symbol=hammer_symbol,
                                    side="BUY",
                                    quantity=lot_qty,
                                    price=emir_fiyat,
                                    order_type="LIMIT",
                                    hidden=True
                                )
                                
                                if success or "new order sent" in str(success):
                                    print(f"[KARBOTU] ✅ {symbol} → {hammer_symbol}: BUY {lot_qty} lot @ ${emir_fiyat:.2f}")
                                else:
                                    print(f"[KARBOTU] ❌ {symbol} → {hammer_symbol}: BUY {lot_qty} lot @ ${emir_fiyat:.2f}")
                            except Exception as e:
                                if "new order sent" in str(e).lower():
                                    print(f"[KARBOTU] ✅ {symbol} → {hammer_symbol}: BUY {lot_qty} lot @ ${emir_fiyat:.2f} (new order sent)")
                                else:
                                    print(f"[KARBOTU] ❌ {symbol} → {hammer_symbol}: {e}")
                        else:
                            # IBKR
                            success = self.mode_manager.place_order(
                                symbol=symbol,
                                side="BUY",
                                quantity=lot_qty,
                                price=emir_fiyat,
                                order_type="LIMIT",
                                hidden=True
                            )
                            
                            if success:
                                print(f"[KARBOTU] ✅ {symbol}: BUY {lot_qty} lot @ ${emir_fiyat:.2f}")
                            else:
                                print(f"[KARBOTU] ❌ {symbol}: BUY {lot_qty} lot @ ${emir_fiyat:.2f}")
                    
                    print(f"[KARBOTU] ✅ {step_name} emirleri gönderildi")
                    self.log_message(f"✅ {step_name} emirleri gönderildi")
                    
                    # Popup'ları kapat
                    self.addnewpos_close_messagebox()
                    if hasattr(self, 'runall_allowed_mode') and self.runall_allowed_mode:
                        self.runall_auto_confirm_messagebox()
                    
                except Exception as e:
                    print(f"[KARBOTU] ❌ Emir gönderme hatası: {e}")
                    self.log_message(f"❌ Emir gönderme hatası: {e}")
                
                confirm_win.destroy()
                # Sonraki adıma geç (kısa bir bekleme ile - adımlar sıralı ilerlesin)
                self.after(1000, self.karbotu_proceed_to_next_step)
            
            def on_cancel():
                """İptal edildi"""
                print(f"[KARBOTU] ❌ {step_name} iptal edildi")
                self.log_message(f"❌ {step_name} iptal edildi")
                confirm_win.destroy()
                # Sonraki adıma geç (kısa bir bekleme ile - adımlar sıralı ilerlesin)
                self.after(1000, self.karbotu_proceed_to_next_step)
            
            def save_to_trades_csv():
                """Seçili emirleri trades.csv formatında kaydet - PENCERE'DEKİ FİYATLAR kullan"""
                try:
                    print(f"[KARBOTU CSV SHORTS] 🔄 trades.csv'ye kaydediliyor...")
                    self.log_message(f"🔄 trades.csv'ye kaydediliyor...")
                    
                    # CSV satırları
                    csv_rows = []
                    
                    # PENCERE'DEKİ tablodan verileri al (zaten hesaplanmış fiyatlar var)
                    for item in pos_tree.get_children():
                        values = pos_tree.item(item)['values']
                        symbol = values[0]
                        qty = float(values[1])
                        lot_qty = float(values[2])
                        
                        # Emir fiyatını PENCERE'DEKİ DEĞERDEN al (zaten hesaplanmış)
                        emir_fiyat_str = values[5]  # "Emir Fiyat" kolonu
                        try:
                            # $ işaretini ve format karakterlerini temizle
                            emir_fiyat = float(str(emir_fiyat_str).replace('$', '').replace(',', '').strip())
                            print(f"[KARBOTU CSV SHORTS] ✅ {symbol}: Emir fiyatı pencereden alındı: ${emir_fiyat:.2f}")
                        except (ValueError, TypeError, IndexError):
                            print(f"[KARBOTU CSV SHORTS] ❌ {symbol}: Emir fiyatı okunamadı: {emir_fiyat_str}")
                            emir_fiyat = 0
                            continue
                        
                        # Lot ve fiyat ZATEN PENCREDEN ALINDI - market data çekmeye GEREK YOK!
                        # Minimum lot kontrolü
                        if abs(lot_qty) < 200:
                            continue
                        
                        # CSV'ye kaydet (fiyat ve lot zaten hazır)
                        if emir_fiyat > 0:
                            # CSV formatı (orijinal format)
                            csv_row = [
                                'BUY',                     # Action
                                int(lot_qty),             # Quantity
                                symbol,                    # Symbol
                                'STK',                    # SecType
                                'SMART/AMEX',              # Exchange
                                'USD',                    # Currency
                                'DAY',                    # TimeInForce
                                'LMT',                    # OrderType
                                f"{emir_fiyat:.2f}",      # LmtPrice
                                'Basket',                 # BasketTag
                                'U21016730',              # Account
                                'Basket',                 # OrderRef
                                'TRUE',                   # Hidden
                                'TRUE'                    # OutsideRth
                            ]
                            
                            csv_rows.append(csv_row)
                            print(f"[KARBOTU CSV] ✅ {symbol}: BUY {lot_qty} @ ${emir_fiyat:.2f}")
                    
                    if csv_rows:
                        # CSV dosyasına kaydet
                        import csv
                        
                        csv_filename = 'trades.csv'
                        
                        # Dosyayı sıfırdan yaz (write mode)
                        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                            writer = csv.writer(csvfile)
                            
                            # Başlık satırı (orijinal format)
                            writer.writerow(['Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 'Currency', 'TimeInForce', 'OrderType', 'LmtPrice', 'BasketTag', 'Account', 'OrderRef', 'Hidden', 'OutsideRth'])
                            
                            # Emir satırları
                            writer.writerows(csv_rows)
                        
                        print(f"[KARBOTU CSV] ✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                        self.log_message(f"✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                        messagebox.showinfo("Başarılı", f"{len(csv_rows)} emir trades.csv'ye kaydedildi!")
                    else:
                        messagebox.showwarning("Uyarı", "Kaydedilecek geçerli emir bulunamadı!")
                        
                except Exception as e:
                    print(f"[KARBOTU CSV] ❌ Kaydetme hatası: {e}")
                    self.log_message(f"❌ Kaydetme hatası: {e}")
                    messagebox.showerror("Hata", f"trades.csv kaydetme hatası: {e}")
            
            ttk.Button(button_frame, text="Send Orders", command=on_confirm, style='Accent.TButton').pack(side='left', padx=5)
            ttk.Button(button_frame, text="Save to trades.csv", command=save_to_trades_csv).pack(side='left', padx=5)
            ttk.Button(button_frame, text="İptal Et", command=on_cancel).pack(side='right', padx=5)
            
        except Exception as e:
            print(f"[KARBOTU] ❌ Shorts onay penceresi hatası: {e}")
            self.log_message(f"❌ Shorts onay penceresi hatası: {e}")
    
    def karbotu_step_11_sfstot_140_169_high(self):
        """Adım 11: SFStot 1.40-1.69 ve Bid Buy ucuzluk < -0.05"""
        try:
            print("[KARBOTU] 📋 Adım 11: SFStot 1.40-1.69 yüksek kontrolü...")
            self.log_message("📋 Adım 11: SFStot 1.40-1.69 ve Bid Buy ucuzluk < -0.05")
            
            # Lot yüzdesi: %50
            lot_percentage = 50
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_shorts_panel.tree.get_children():
                values = self.take_profit_shorts_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                sfstot_str = values[5]
                bid_buy_ucuzluk_str = values[8]
                
                try:
                    # SFStot'u güvenli şekilde parse et
                    sfstot = 0
                    if sfstot_str != 'N/A' and sfstot_str:
                        try:
                            sfstot = float(sfstot_str)
                        except (ValueError, TypeError):
                            sfstot = 0
                    
                    # SFStot 0.0 veya N/A ise skip et
                    if sfstot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Bid Buy ucuzluk skorunu güvenli şekilde parse et
                    bid_buy_ucuzluk = 0
                    if bid_buy_ucuzluk_str != 'N/A' and bid_buy_ucuzluk_str:
                        try:
                            clean_str = str(bid_buy_ucuzluk_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                bid_buy_ucuzluk = float(clean_str)
                        except (ValueError, TypeError):
                            bid_buy_ucuzluk = 0
                    
                    # Koşul: SFStot 1.40-1.69 ve Bid Buy ucuzluk < -0.05
                    if 1.40 <= sfstot <= 1.69 and bid_buy_ucuzluk < -0.05:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'sfstot': sfstot,
                            'bid_buy_ucuzluk': bid_buy_ucuzluk
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 11: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 11: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_shorts_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, SFStot={pos['sfstot']:.2f}, Bid Buy Ucuzluk=${pos['bid_buy_ucuzluk']:.4f}")
                
                # Pozisyonları seç ve %50 lot ile Bid Buy onay penceresi aç
                self.karbotu_select_shorts_positions_and_confirm(filtered_positions, "Bid Buy", 50, "Adım 11")
            else:
                print("[KARBOTU] ⚠️ Adım 11: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 11: Koşula uygun pozisyon bulunamadı")
                # Adım 12'ye geç
                self.karbotu_current_step = 12
                self.karbotu_step_12_sfstot_110_139_low()
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 11 hatası: {e}")
            self.log_message(f"❌ Adım 11 hatası: {e}")
    
    def karbotu_step_12_sfstot_110_139_low(self):
        """Adım 12: SFStot 1.10-1.39 ve Bid Buy ucuzluk +0.05 ile -0.04 arası"""
        try:
            print("[KARBOTU] 📋 Adım 12: SFStot 1.10-1.39 kontrolü...")
            self.log_message("📋 Adım 12: SFStot 1.10-1.39 ve Bid Buy ucuzluk +0.05 ile -0.04 arası")
            
            # Lot yüzdesi: %25
            lot_percentage = 25
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_shorts_panel.tree.get_children():
                values = self.take_profit_shorts_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                sfstot_str = values[5]
                bid_buy_ucuzluk_str = values[8]
                
                try:
                    # SFStot'u güvenli şekilde parse et
                    sfstot = 0
                    if sfstot_str != 'N/A' and sfstot_str:
                        try:
                            sfstot = float(sfstot_str)
                        except (ValueError, TypeError):
                            sfstot = 0
                    
                    # SFStot 0.0 veya N/A ise skip et
                    if sfstot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Bid Buy ucuzluk skorunu güvenli şekilde parse et
                    bid_buy_ucuzluk = 0
                    if bid_buy_ucuzluk_str != 'N/A' and bid_buy_ucuzluk_str:
                        try:
                            clean_str = str(bid_buy_ucuzluk_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                bid_buy_ucuzluk = float(clean_str)
                        except (ValueError, TypeError):
                            bid_buy_ucuzluk = 0
                    
                    # Koşul: SFStot 1.10-1.39 ve Bid Buy ucuzluk +0.05 ile -0.04 arası
                    if 1.10 <= sfstot <= 1.39 and -0.04 <= bid_buy_ucuzluk <= 0.05:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'sfstot': sfstot,
                            'bid_buy_ucuzluk': bid_buy_ucuzluk
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 12: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 12: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_shorts_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, SFStot={pos['sfstot']:.2f}, Bid Buy Ucuzluk=${pos['bid_buy_ucuzluk']:.4f}")
                
                # Pozisyonları seç ve %25 lot ile Bid Buy onay penceresi aç
                self.karbotu_select_shorts_positions_and_confirm(filtered_positions, "Bid Buy", 25, "Adım 12")
            else:
                print("[KARBOTU] ⚠️ Adım 12: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 12: Koşula uygun pozisyon bulunamadı")
                # Adım 13'e geç
                self.karbotu_current_step = 13
                self.karbotu_step_13_sfstot_110_139_high()
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 12 hatası: {e}")
            self.log_message(f"❌ Adım 12 hatası: {e}")
    
    def karbotu_step_13_sfstot_110_139_high(self):
        """Adım 13: SFStot 1.10-1.39 ve Bid Buy ucuzluk < -0.05"""
        try:
            print("[KARBOTU] 📋 Adım 13: SFStot 1.10-1.39 yüksek kontrolü...")
            self.log_message("📋 Adım 13: SFStot 1.10-1.39 ve Bid Buy ucuzluk < -0.05")
            
            # Lot yüzdesi: %50
            lot_percentage = 50
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_shorts_panel.tree.get_children():
                values = self.take_profit_shorts_panel.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                sfstot_str = values[5]
                bid_buy_ucuzluk_str = values[8]
                
                try:
                    # SFStot'u güvenli şekilde parse et
                    sfstot = 0
                    if sfstot_str != 'N/A' and sfstot_str:
                        try:
                            sfstot = float(sfstot_str)
                        except (ValueError, TypeError):
                            sfstot = 0
                    
                    # SFStot 0.0 veya N/A ise skip et
                    if sfstot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Bid Buy ucuzluk skorunu güvenli şekilde parse et
                    bid_buy_ucuzluk = 0
                    if bid_buy_ucuzluk_str != 'N/A' and bid_buy_ucuzluk_str:
                        try:
                            clean_str = str(bid_buy_ucuzluk_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                bid_buy_ucuzluk = float(clean_str)
                        except (ValueError, TypeError):
                            bid_buy_ucuzluk = 0
                    
                    # Koşul: SFStot 1.10-1.39 ve Bid Buy ucuzluk < -0.05
                    if 1.10 <= sfstot <= 1.39 and bid_buy_ucuzluk < -0.05:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'sfstot': sfstot,
                            'bid_buy_ucuzluk': bid_buy_ucuzluk
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[KARBOTU] ✅ Adım 13: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 13: {len(filtered_positions)} pozisyon bulundu")
                
                # Debug: Bulunan pozisyonları listele
                for pos in filtered_positions:
                    # Lot hesaplama debug'u
                    item_values = self.take_profit_shorts_panel.tree.item(pos['item'])['values']
                    qty = float(item_values[2])
                    calculated_lot = qty * (lot_percentage / 100)
                    
                    # Lot yuvarlama mantığı (debug için - negatif sayılar için)
                    if calculated_lot >= 0:
                        # Pozitif sayılar için normal yuvarlama
                        if calculated_lot <= 0:
                            lot_qty = 0
                        elif calculated_lot <= 100:
                            lot_qty = 100
                        elif calculated_lot <= 200:
                            lot_qty = 200
                        elif calculated_lot <= 300:
                            lot_qty = 300
                        elif calculated_lot <= 400:
                            lot_qty = 400
                        elif calculated_lot <= 500:
                            lot_qty = 500
                        elif calculated_lot <= 600:
                            lot_qty = 600
                        elif calculated_lot <= 700:
                            lot_qty = 700
                        elif calculated_lot <= 800:
                            lot_qty = 800
                        elif calculated_lot <= 900:
                            lot_qty = 900
                        elif calculated_lot <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((calculated_lot + 99) // 100) * 100
                    else:
                        # Negatif sayılar için aşağı yuvarlama (daha negatif)
                        abs_calculated = abs(calculated_lot)
                        if abs_calculated <= 100:
                            lot_qty = 100
                        elif abs_calculated <= 200:
                            lot_qty = 200
                        elif abs_calculated <= 300:
                            lot_qty = 300
                        elif abs_calculated <= 400:
                            lot_qty = -400
                        elif abs_calculated <= 500:
                            lot_qty = -500
                        elif abs_calculated <= 600:
                            lot_qty = -600
                        elif abs_calculated <= 700:
                            lot_qty = -700
                        elif abs_calculated <= 800:
                            lot_qty = -800
                        elif abs_calculated <= 900:
                            lot_qty = -900
                        elif abs_calculated <= 1000:
                            lot_qty = 1000
                        else:
                            lot_qty = int((abs_calculated + 99) // 100) * 100
                    
                    print(f"[KARBOTU DEBUG] ✅ {pos['symbol']}: Qty={qty:.0f} → %{lot_percentage}={calculated_lot:.1f} → {lot_qty} lot, SFStot={pos['sfstot']:.2f}, Bid Buy Ucuzluk=${pos['bid_buy_ucuzluk']:.4f}")
                
                # Pozisyonları seç ve %50 lot ile Bid Buy onay penceresi aç
                self.karbotu_select_shorts_positions_and_confirm(filtered_positions, "Bid Buy", 50, "Adım 13")
            else:
                print("[KARBOTU] ⚠️ Adım 13: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 13: Koşula uygun pozisyon bulunamadı")
                # Tüm adımlar tamamlandı
                print("[KARBOTU] 🎯 Tüm adımlar tamamlandı!")
                self.log_message("🎯 KARBOTU otomasyonu tamamlandı!")
                self.karbotu_running = False
                
                # RUNALL'dan çağrıldıysa ADDNEWPOS kontrolü yap (SADECE BİR KEZ)
                if hasattr(self, 'runall_waiting_for_karbotu') and self.runall_waiting_for_karbotu:
                    if not hasattr(self, 'runall_addnewpos_triggered') or not self.runall_addnewpos_triggered:
                        self.runall_waiting_for_karbotu = False
                        self.runall_addnewpos_triggered = True  # İşaretle ki tekrar tetiklenmesin
                        self.after(2000, self.runall_check_karbotu_and_addnewpos)  # 2 saniye sonra kontrol et
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Adım 13 hatası: {e}")
            self.log_message(f"❌ Adım 13 hatası: {e}")
            # Hata olsa bile otomasyonu sonlandır
            self.karbotu_running = False
    
    # ==================== REDUCEMORE OTOMASYONU ====================
    
    def start_reducemore_automation(self):
        """REDUCEMORE otomasyonunu başlat"""
        try:
            print("[REDUCEMORE] 📉 REDUCEMORE otomasyonu başlatılıyor...")
            self.log_message("📉 REDUCEMORE otomasyonu başlatılıyor...")
            
            # REDUCEMORE adımlarını başlat
            self.reducemore_current_step = 1
            self.reducemore_total_steps = 13
            self.reducemore_running = True
            
            # İlk adım: Take Profit Longs penceresini aç
            self.reduce_more_step_1_open_take_profit_longs()
            
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Otomasyon başlatma hatası: {e}")
            self.log_message(f"❌ REDUCEMORE başlatma hatası: {e}")
            messagebox.showerror("Hata", f"REDUCEMORE başlatılamadı: {e}")
    
    def reduce_more_step_1_open_take_profit_longs(self):
        """Adım 1: Take Profit Longs penceresini aç"""
        try:
            print("[REDUCEMORE] 📋 Adım 1: Take Profit Longs penceresi açılıyor...")
            self.log_message("📋 Adım 1: Take Profit Longs penceresi açılıyor...")
            
            # Take Profit Longs penceresini aç
            from .take_profit_panel import TakeProfitPanel
            self.take_profit_longs_panel_reducemore = TakeProfitPanel(self, "longs")
            
            # Adım 2'ye geç
            self.reducemore_current_step = 2
            self.reduce_more_step_2_fbtot_lt_110()
            
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 1 hatası: {e}")
            self.log_message(f"❌ Adım 1 hatası: {e}")
    
    def reduce_more_step_2_fbtot_lt_110(self):
        """Adım 2: Fbtot < 1.10 ve Ask Sell pahalılık > -0.20"""
        try:
            print("[REDUCEMORE] 📋 Adım 2: Fbtot < 1.10 kontrolü...")
            self.log_message("📋 Adım 2: Fbtot < 1.10 ve Ask Sell pahalılık > -0.20")
            
            # Lot yüzdesi: %100
            lot_percentage = 100
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel_reducemore.tree.get_children():
                values = self.take_profit_longs_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]  # Fbtot kolonu
                ask_sell_pahalilik_str = values[8]  # Ask Sell Pahalılık kolonu
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            # $ işaretini kaldır ve float'a çevir
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot < 1.10 ve Ask Sell pahalılık > -0.20
                    if fbtot < 1.10 and ask_sell_pahalilik > -0.20:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 2: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 2: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %100 lot ile Ask Sell onay penceresi aç
                self.reduce_more_select_positions_and_confirm(filtered_positions, "Ask Sell", 100, "Adım 2")
            else:
                print("[REDUCEMORE] ⚠️ Adım 2: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 2: Koşula uygun pozisyon bulunamadı")
                # Adım 3'e geç
                self.reducemore_current_step = 3
                self.reduce_more_step_3_fbtot_111_145_low()
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 2 hatası: {e}")
            self.log_message(f"❌ Adım 2 hatası: {e}")
    
    def reduce_more_step_3_fbtot_111_145_low(self):
        """Adım 3: Fbtot 1.11-1.45 ve Ask Sell pahalılık -0.08 ile +0.01 arası"""
        try:
            print("[REDUCEMORE] 📋 Adım 3: Fbtot 1.11-1.45 kontrolü...")
            self.log_message("📋 Adım 3: Fbtot 1.11-1.45 ve Ask Sell pahalılık -0.08 ile +0.01 arası")
            
            # Lot yüzdesi: %75
            lot_percentage = 75
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel_reducemore.tree.get_children():
                values = self.take_profit_longs_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]
                ask_sell_pahalilik_str = values[8]
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot 1.11-1.45 ve Ask Sell pahalılık -0.08 ile +0.01 arası
                    if 1.11 <= fbtot <= 1.45 and -0.08 <= ask_sell_pahalilik <= 0.01:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 3: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 3: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %75 lot ile Ask Sell onay penceresi aç
                self.reduce_more_select_positions_and_confirm(filtered_positions, "Ask Sell", 75, "Adım 3")
            else:
                print("[REDUCEMORE] ⚠️ Adım 3: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 3: Koşula uygun pozisyon bulunamadı")
                # Adım 4'e geç
                self.reducemore_current_step = 4
                self.reduce_more_step_4_fbtot_111_145_high()
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 3 hatası: {e}")
            self.log_message(f"❌ Adım 3 hatası: {e}")
    
    def reduce_more_step_4_fbtot_111_145_high(self):
        """Adım 4: Fbtot 1.11-1.45 ve Ask Sell pahalılık > +0.01"""
        try:
            print("[REDUCEMORE] 📋 Adım 4: Fbtot 1.11-1.45 yüksek kontrolü...")
            self.log_message("📋 Adım 4: Fbtot 1.11-1.45 ve Ask Sell pahalılık > +0.01")
            
            # Lot yüzdesi: %100
            lot_percentage = 100
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel_reducemore.tree.get_children():
                values = self.take_profit_longs_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]
                ask_sell_pahalilik_str = values[8]
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot 1.11-1.45 ve Ask Sell pahalılık > +0.01
                    if 1.11 <= fbtot <= 1.45 and ask_sell_pahalilik > 0.01:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 4: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 4: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %100 lot ile Ask Sell onay penceresi aç
                self.reduce_more_select_positions_and_confirm(filtered_positions, "Ask Sell", 100, "Adım 4")
            else:
                print("[REDUCEMORE] ⚠️ Adım 4: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 4: Koşula uygun pozisyon bulunamadı")
                # Adım 5'e geç
                self.reducemore_current_step = 5
                self.reduce_more_step_5_fbtot_146_185_low()
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 4 hatası: {e}")
            self.log_message(f"❌ Adım 4 hatası: {e}")
    
    def reduce_more_step_5_fbtot_146_185_low(self):
        """Adım 5: Fbtot 1.46-1.85 ve Ask Sell pahalılık +0.01 ile +0.07 arası"""
        try:
            print("[REDUCEMORE] 📋 Adım 5: Fbtot 1.46-1.85 kontrolü...")
            self.log_message("📋 Adım 5: Fbtot 1.46-1.85 ve Ask Sell pahalılık +0.01 ile +0.07 arası")
            
            # Lot yüzdesi: %50
            lot_percentage = 50
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel_reducemore.tree.get_children():
                values = self.take_profit_longs_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]
                ask_sell_pahalilik_str = values[8]
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot 1.46-1.85 ve Ask Sell pahalılık +0.01 ile +0.07 arası
                    if 1.46 <= fbtot <= 1.85 and 0.01 <= ask_sell_pahalilik <= 0.07:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 5: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 5: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %50 lot ile Ask Sell onay penceresi aç
                self.reduce_more_select_positions_and_confirm(filtered_positions, "Ask Sell", 50, "Adım 5")
            else:
                print("[REDUCEMORE] ⚠️ Adım 5: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 5: Koşula uygun pozisyon bulunamadı")
                # Adım 6'ya geç
                self.reducemore_current_step = 6
                self.reduce_more_step_6_fbtot_146_185_high()
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 5 hatası: {e}")
            self.log_message(f"❌ Adım 5 hatası: {e}")
    
    def reduce_more_step_6_fbtot_146_185_high(self):
        """Adım 6: Fbtot 1.46-1.85 ve Ask Sell pahalılık > +0.07"""
        try:
            print("[REDUCEMORE] 📋 Adım 6: Fbtot 1.46-1.85 yüksek kontrolü...")
            self.log_message("📋 Adım 6: Fbtot 1.46-1.85 ve Ask Sell pahalılık > +0.07")
            
            # Lot yüzdesi: %75
            lot_percentage = 75
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel_reducemore.tree.get_children():
                values = self.take_profit_longs_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]
                ask_sell_pahalilik_str = values[8]
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot 1.46-1.85 ve Ask Sell pahalılık > +0.07
                    if 1.46 <= fbtot <= 1.85 and ask_sell_pahalilik > 0.07:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 6: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 6: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %75 lot ile Ask Sell onay penceresi aç
                self.reduce_more_select_positions_and_confirm(filtered_positions, "Ask Sell", 75, "Adım 6")
            else:
                print("[REDUCEMORE] ⚠️ Adım 6: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 6: Koşula uygun pozisyon bulunamadı")
                # Adım 7'ye geç
                self.reducemore_current_step = 7
                self.reduce_more_step_7_fbtot_186_210()
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 6 hatası: {e}")
            self.log_message(f"❌ Adım 6 hatası: {e}")
    
    def reduce_more_step_7_fbtot_186_210(self):
        """Adım 7: Fbtot 1.86-2.10 ve Ask Sell pahalılık > +0.18"""
        try:
            print("[REDUCEMORE] 📋 Adım 7: Fbtot 1.86-2.10 kontrolü...")
            self.log_message("📋 Adım 7: Fbtot 1.86-2.10 ve Ask Sell pahalılık > +0.18")
            
            # Lot yüzdesi: %50
            lot_percentage = 50
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_longs_panel_reducemore.tree.get_children():
                values = self.take_profit_longs_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                fbtot_str = values[5]
                ask_sell_pahalilik_str = values[8]
                
                try:
                    # Fbtot'u güvenli şekilde parse et
                    fbtot = 0
                    if fbtot_str != 'N/A' and fbtot_str:
                        try:
                            fbtot = float(fbtot_str)
                        except (ValueError, TypeError):
                            fbtot = 0
                    
                    # Fbtot 0.0 veya N/A ise skip et
                    if fbtot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Ask Sell pahalılık skorunu güvenli şekilde parse et
                    ask_sell_pahalilik = 0
                    if ask_sell_pahalilik_str != 'N/A' and ask_sell_pahalilik_str:
                        try:
                            clean_str = str(ask_sell_pahalilik_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                ask_sell_pahalilik = float(clean_str)
                        except (ValueError, TypeError):
                            ask_sell_pahalilik = 0
                    
                    # Koşul: Fbtot 1.86-2.10 ve Ask Sell pahalılık > +0.18
                    if 1.86 <= fbtot <= 2.10 and ask_sell_pahalilik > 0.18:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'fbtot': fbtot,
                            'ask_sell_pahalilik': ask_sell_pahalilik
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 7: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 7: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %50 lot ile Ask Sell onay penceresi aç
                self.reduce_more_select_positions_and_confirm(filtered_positions, "Ask Sell", 50, "Adım 7")
            else:
                print("[REDUCEMORE] ⚠️ Adım 7: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 7: Koşula uygun pozisyon bulunamadı")
                # Adım 8'e geç - Take Profit Shorts aç
                self.reducemore_current_step = 8
                self.reduce_more_step_8_open_take_profit_shorts()
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 7 hatası: {e}")
            self.log_message(f"❌ Adım 7 hatası: {e}")
    
    def reduce_more_step_8_open_take_profit_shorts(self):
        """Adım 8: Take Profit Longs kapat ve Take Profit Shorts aç"""
        try:
            print("[REDUCEMORE] 📋 Adım 8: Take Profit Shorts penceresi açılıyor...")
            self.log_message("📋 Adım 8: Take Profit Shorts penceresi açılıyor...")
            
            # Take Profit Longs penceresini kapat
            if hasattr(self, 'take_profit_longs_panel_reducemore') and self.take_profit_longs_panel_reducemore:
                self.take_profit_longs_panel_reducemore.win.destroy()
            
            # Take Profit Shorts penceresini aç
            from .take_profit_panel import TakeProfitPanel
            self.take_profit_shorts_panel_reducemore = TakeProfitPanel(self, "shorts")
            
            # Adım 9'a geç
            self.reducemore_current_step = 9
            self.reduce_more_step_9_sfstot_170_high()
            
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 8 hatası: {e}")
            self.log_message(f"❌ Adım 8 hatası: {e}")
    
    def reduce_more_step_9_sfstot_170_high(self):
        """Adım 9: SFStot > 1.70 ve Bid Buy ucuzluk < +0.14"""
        try:
            print("[REDUCEMORE] 📋 Adım 9: SFStot > 1.70 kontrolü...")
            self.log_message("📋 Adım 9: SFStot > 1.70 ve Bid Buy ucuzluk < +0.14")
            
            # Lot yüzdesi: %100
            lot_percentage = 100
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_shorts_panel_reducemore.tree.get_children():
                values = self.take_profit_shorts_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                sfstot_str = values[5]  # SFStot kolonu
                bid_buy_ucuzluk_str = values[8]  # Bid Buy Ucuzluk kolonu
                
                try:
                    # SFStot'u güvenli şekilde parse et
                    sfstot = 0
                    if sfstot_str != 'N/A' and sfstot_str:
                        try:
                            sfstot = float(sfstot_str)
                        except (ValueError, TypeError):
                            sfstot = 0
                    
                    # SFStot 0.0 veya N/A ise skip et
                    if sfstot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Bid Buy ucuzluk skorunu güvenli şekilde parse et
                    bid_buy_ucuzluk = 0
                    if bid_buy_ucuzluk_str != 'N/A' and bid_buy_ucuzluk_str:
                        try:
                            clean_str = str(bid_buy_ucuzluk_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                bid_buy_ucuzluk = float(clean_str)
                        except (ValueError, TypeError):
                            bid_buy_ucuzluk = 0
                    
                    # Koşul: SFStot > 1.70 ve Bid Buy ucuzluk < +0.14
                    if sfstot > 1.70 and bid_buy_ucuzluk < 0.14:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'sfstot': sfstot,
                            'bid_buy_ucuzluk': bid_buy_ucuzluk
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 9: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 9: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %100 lot ile Bid Buy onay penceresi aç
                self.reduce_more_select_shorts_positions_and_confirm(filtered_positions, "Bid Buy", 100, "Adım 9")
            else:
                print("[REDUCEMORE] ⚠️ Adım 9: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 9: Koşula uygun pozisyon bulunamadı")
                # Adım 10'a geç
                self.reducemore_current_step = 10
                self.reduce_more_step_10_sfstot_140_169_low()
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 9 hatası: {e}")
            self.log_message(f"❌ Adım 9 hatası: {e}")
    
    def reduce_more_step_10_sfstot_140_169_low(self):
        """Adım 10: SFStot 1.40-1.69 ve Bid Buy ucuzluk -0.04 ile +0.05 arası"""
        try:
            print("[REDUCEMORE] 📋 Adım 10: SFStot 1.40-1.69 kontrolü...")
            self.log_message("📋 Adım 10: SFStot 1.40-1.69 ve Bid Buy ucuzluk -0.04 ile +0.05 arası")
            
            # Lot yüzdesi: %50
            lot_percentage = 50
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_shorts_panel_reducemore.tree.get_children():
                values = self.take_profit_shorts_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                sfstot_str = values[5]
                bid_buy_ucuzluk_str = values[8]
                
                try:
                    # SFStot'u güvenli şekilde parse et
                    sfstot = 0
                    if sfstot_str != 'N/A' and sfstot_str:
                        try:
                            sfstot = float(sfstot_str)
                        except (ValueError, TypeError):
                            sfstot = 0
                    
                    # SFStot 0.0 veya N/A ise skip et
                    if sfstot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Bid Buy ucuzluk skorunu güvenli şekilde parse et
                    bid_buy_ucuzluk = 0
                    if bid_buy_ucuzluk_str != 'N/A' and bid_buy_ucuzluk_str:
                        try:
                            clean_str = str(bid_buy_ucuzluk_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                bid_buy_ucuzluk = float(clean_str)
                        except (ValueError, TypeError):
                            bid_buy_ucuzluk = 0
                    
                    # Koşul: SFStot 1.40-1.69 ve Bid Buy ucuzluk -0.04 ile +0.05 arası
                    if 1.40 <= sfstot <= 1.69 and -0.04 <= bid_buy_ucuzluk <= 0.05:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'sfstot': sfstot,
                            'bid_buy_ucuzluk': bid_buy_ucuzluk
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 10: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 10: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %50 lot ile Bid Buy onay penceresi aç
                self.reduce_more_select_shorts_positions_and_confirm(filtered_positions, "Bid Buy", 50, "Adım 10")
            else:
                print("[REDUCEMORE] ⚠️ Adım 10: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 10: Koşula uygun pozisyon bulunamadı")
                # Adım 11'e geç
                self.reducemore_current_step = 11
                self.reduce_more_step_11_sfstot_140_169_high()
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 10 hatası: {e}")
            self.log_message(f"❌ Adım 10 hatası: {e}")
    
    def reduce_more_step_11_sfstot_140_169_high(self):
        """Adım 11: SFStot 1.40-1.69 ve Bid Buy ucuzluk < -0.05"""
        try:
            print("[REDUCEMORE] 📋 Adım 11: SFStot 1.40-1.69 yüksek kontrolü...")
            self.log_message("📋 Adım 11: SFStot 1.40-1.69 ve Bid Buy ucuzluk < -0.05")
            
            # Lot yüzdesi: %75
            lot_percentage = 75
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_shorts_panel_reducemore.tree.get_children():
                values = self.take_profit_shorts_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                sfstot_str = values[5]
                bid_buy_ucuzluk_str = values[8]
                
                try:
                    # SFStot'u güvenli şekilde parse et
                    sfstot = 0
                    if sfstot_str != 'N/A' and sfstot_str:
                        try:
                            sfstot = float(sfstot_str)
                        except (ValueError, TypeError):
                            sfstot = 0
                    
                    # SFStot 0.0 veya N/A ise skip et
                    if sfstot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Bid Buy ucuzluk skorunu güvenli şekilde parse et
                    bid_buy_ucuzluk = 0
                    if bid_buy_ucuzluk_str != 'N/A' and bid_buy_ucuzluk_str:
                        try:
                            clean_str = str(bid_buy_ucuzluk_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                bid_buy_ucuzluk = float(clean_str)
                        except (ValueError, TypeError):
                            bid_buy_ucuzluk = 0
                    
                    # Koşul: SFStot 1.40-1.69 ve Bid Buy ucuzluk < -0.05
                    if 1.40 <= sfstot <= 1.69 and bid_buy_ucuzluk < -0.05:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'sfstot': sfstot,
                            'bid_buy_ucuzluk': bid_buy_ucuzluk
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 11: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 11: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %75 lot ile Bid Buy onay penceresi aç
                self.reduce_more_select_shorts_positions_and_confirm(filtered_positions, "Bid Buy", 75, "Adım 11")
            else:
                print("[REDUCEMORE] ⚠️ Adım 11: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 11: Koşula uygun pozisyon bulunamadı")
                # Adım 12'ye geç
                self.reducemore_current_step = 12
                self.reduce_more_step_12_sfstot_110_139_low()
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 11 hatası: {e}")
            self.log_message(f"❌ Adım 11 hatası: {e}")
    
    def reduce_more_step_12_sfstot_110_139_low(self):
        """Adım 12: SFStot 1.10-1.39 ve Bid Buy ucuzluk -0.04 ile +0.05 arası"""
        try:
            print("[REDUCEMORE] 📋 Adım 12: SFStot 1.10-1.39 kontrolü...")
            self.log_message("📋 Adım 12: SFStot 1.10-1.39 ve Bid Buy ucuzluk -0.04 ile +0.05 arası")
            
            # Lot yüzdesi: %50
            lot_percentage = 50
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_shorts_panel_reducemore.tree.get_children():
                values = self.take_profit_shorts_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                sfstot_str = values[5]
                bid_buy_ucuzluk_str = values[8]
                
                try:
                    # SFStot'u güvenli şekilde parse et
                    sfstot = 0
                    if sfstot_str != 'N/A' and sfstot_str:
                        try:
                            sfstot = float(sfstot_str)
                        except (ValueError, TypeError):
                            sfstot = 0
                    
                    # SFStot 0.0 veya N/A ise skip et
                    if sfstot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Bid Buy ucuzluk skorunu güvenli şekilde parse et
                    bid_buy_ucuzluk = 0
                    if bid_buy_ucuzluk_str != 'N/A' and bid_buy_ucuzluk_str:
                        try:
                            clean_str = str(bid_buy_ucuzluk_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                bid_buy_ucuzluk = float(clean_str)
                        except (ValueError, TypeError):
                            bid_buy_ucuzluk = 0
                    
                    # Koşul: SFStot 1.10-1.39 ve Bid Buy ucuzluk -0.04 ile +0.05 arası
                    if 1.10 <= sfstot <= 1.39 and -0.04 <= bid_buy_ucuzluk <= 0.05:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'sfstot': sfstot,
                            'bid_buy_ucuzluk': bid_buy_ucuzluk
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 12: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 12: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %50 lot ile Bid Buy onay penceresi aç
                self.reduce_more_select_shorts_positions_and_confirm(filtered_positions, "Bid Buy", 50, "Adım 12")
            else:
                print("[REDUCEMORE] ⚠️ Adım 12: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 12: Koşula uygun pozisyon bulunamadı")
                # Adım 13'e geç
                self.reducemore_current_step = 13
                self.reduce_more_step_13_sfstot_110_139_high()
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 12 hatası: {e}")
            self.log_message(f"❌ Adım 12 hatası: {e}")
    
    def reduce_more_step_13_sfstot_110_139_high(self):
        """Adım 13: SFStot 1.10-1.39 ve Bid Buy ucuzluk < -0.05"""
        try:
            print("[REDUCEMORE] 📋 Adım 13: SFStot 1.10-1.39 yüksek kontrolü...")
            self.log_message("📋 Adım 13: SFStot 1.10-1.39 ve Bid Buy ucuzluk < -0.05")
            
            # Lot yüzdesi: %75
            lot_percentage = 75
            
            # Pozisyonları filtrele
            filtered_positions = []
            for item in self.take_profit_shorts_panel_reducemore.tree.get_children():
                values = self.take_profit_shorts_panel_reducemore.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]
                sfstot_str = values[5]
                bid_buy_ucuzluk_str = values[8]
                
                try:
                    # SFStot'u güvenli şekilde parse et
                    sfstot = 0
                    if sfstot_str != 'N/A' and sfstot_str:
                        try:
                            sfstot = float(sfstot_str)
                        except (ValueError, TypeError):
                            sfstot = 0
                    
                    # SFStot 0.0 veya N/A ise skip et
                    if sfstot <= 0:
                        continue
                    
                    # 100 lot altı pozisyonları göz ardı et
                    qty = float(values[2])  # Quantity kolonu
                    if abs(qty) < 100:
                        continue
                    
                    # Bid Buy ucuzluk skorunu güvenli şekilde parse et
                    bid_buy_ucuzluk = 0
                    if bid_buy_ucuzluk_str != 'N/A' and bid_buy_ucuzluk_str:
                        try:
                            clean_str = str(bid_buy_ucuzluk_str).replace('$', '').replace(',', '').strip()
                            if clean_str and clean_str != 'nan':
                                bid_buy_ucuzluk = float(clean_str)
                        except (ValueError, TypeError):
                            bid_buy_ucuzluk = 0
                    
                    # Koşul: SFStot 1.10-1.39 ve Bid Buy ucuzluk < -0.05
                    if 1.10 <= sfstot <= 1.39 and bid_buy_ucuzluk < -0.05:
                        filtered_positions.append({
                            'symbol': symbol,
                            'item': item,
                            'sfstot': sfstot,
                            'bid_buy_ucuzluk': bid_buy_ucuzluk
                        })
                        
                except (ValueError, TypeError):
                    continue
            
            if filtered_positions:
                print(f"[REDUCEMORE] ✅ Adım 13: {len(filtered_positions)} pozisyon bulundu")
                self.log_message(f"✅ Adım 13: {len(filtered_positions)} pozisyon bulundu")
                
                # Pozisyonları seç ve %75 lot ile Bid Buy onay penceresi aç
                self.reduce_more_select_shorts_positions_and_confirm(filtered_positions, "Bid Buy", 75, "Adım 13")
            else:
                print("[REDUCEMORE] ⚠️ Adım 13: Koşula uygun pozisyon bulunamadı")
                self.log_message("⚠️ Adım 13: Koşula uygun pozisyon bulunamadı")
                # Tüm adımlar tamamlandı
                print("[REDUCEMORE] 🎯 Tüm adımlar tamamlandı!")
                self.log_message("🎯 REDUCEMORE otomasyonu tamamlandı!")
                self.reducemore_running = False
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Adım 13 hatası: {e}")
            self.log_message(f"❌ Adım 13 hatası: {e}")
            # Hata olsa bile otomasyonu sonlandır
            self.reducemore_running = False
    
    def reduce_more_select_positions_and_confirm(self, positions, order_type, lot_percentage, step_name):
        """REDUCEMORE: Pozisyonları seç ve onay penceresi aç"""
        try:
            # Pozisyonları seç
            for pos in positions:
                self.take_profit_longs_panel_reducemore.tree.set(pos['item'], "select", "✓")
                
                # Avg cost'u güvenli şekilde parse et
                avg_cost_str = self.take_profit_longs_panel_reducemore.tree.item(pos['item'])['values'][3]
                avg_cost = 0
                if avg_cost_str and avg_cost_str != 'N/A':
                    try:
                        clean_str = str(avg_cost_str).replace('$', '').replace(',', '').strip()
                        if clean_str and clean_str != 'nan':
                            avg_cost = float(clean_str)
                    except (ValueError, TypeError):
                        avg_cost = 0
                
                self.take_profit_longs_panel_reducemore.selected_positions[pos['symbol']] = {
                    'qty': float(self.take_profit_longs_panel_reducemore.tree.item(pos['item'])['values'][2]),
                    'avg_cost': avg_cost
                }
            
            # Lot yüzdesini ayarla
            if lot_percentage == 25:
                self.take_profit_longs_panel_reducemore.set_lot_percentage(25)
            elif lot_percentage == 50:
                self.take_profit_longs_panel_reducemore.set_lot_percentage(50)
            elif lot_percentage == 75:
                self.take_profit_longs_panel_reducemore.set_lot_percentage(75)
            elif lot_percentage == 100:
                self.take_profit_longs_panel_reducemore.set_lot_percentage(100)
            
            # Onay penceresini aç
            print(f"[REDUCEMORE DEBUG] 🔄 Onay penceresi açılıyor: {step_name}")
            self.reduce_more_show_confirmation_window(positions, order_type, lot_percentage, step_name)
            
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Pozisyon seçimi hatası: {e}")
            self.log_message(f"❌ REDUCEMORE pozisyon seçimi hatası: {e}")
    
    def reduce_more_show_confirmation_window(self, positions, order_type, lot_percentage, step_name):
        """REDUCEMORE onay penceresi göster - KARBOTU ile birebir aynı mantık"""
        # Bu fonksiyon KARBOTU'nun karbotu_show_confirmation_window ile birebir aynı
        # Sadece panel adları (take_profit_longs_panel_reducemore) ve log mesajları değişir
        # Kod çok uzun olduğu için karbotu_show_confirmation_window'u kullanıyoruz
        # Ancak panel adını değiştirmemiz gerekiyor
        try:
            print(f"[REDUCEMORE DEBUG] 🔄 Onay penceresi fonksiyonu başladı: {step_name}")
            # Onay penceresi
            confirm_win = tk.Toplevel(self.psfalgo_window)
            confirm_win.title(f"REDUCEMORE - {step_name}")
            confirm_win.geometry("600x400")
            confirm_win.transient(self.psfalgo_window)
            # grab_set() kaldırıldı - minimize edilebilir olması için
            
            # Başlık frame - minimize butonu ile
            title_frame = ttk.Frame(confirm_win)
            title_frame.pack(fill='x', padx=10, pady=10)
            
            # Sol taraf - başlık bilgileri
            title_left = ttk.Frame(title_frame)
            title_left.pack(side='left', fill='x', expand=True)
            
            ttk.Label(title_left, text=f"REDUCEMORE - {step_name}", font=('Arial', 14, 'bold')).pack(anchor='w')
            ttk.Label(title_left, text=f"{order_type} - %{lot_percentage} Lot", font=('Arial', 12)).pack(anchor='w')
            ttk.Label(title_left, text=f"{len(positions)} pozisyon seçildi", font=('Arial', 10)).pack(anchor='w')
            
            # Sağ taraf - minimize butonu
            window_controls = ttk.Frame(title_frame)
            window_controls.pack(side='right')
            
            # Alta Al (Minimize) butonu
            minimize_btn = ttk.Button(window_controls, text="🗕 Alta Al", width=10,
                                      command=lambda: confirm_win.iconify())
            minimize_btn.pack(side='left', padx=2)
            
            # Pozisyon listesi
            list_frame = ttk.Frame(confirm_win)
            list_frame.pack(fill='both', expand=True, padx=10, pady=5)
            
            # Treeview
            columns = ('Symbol', 'Qty', 'Lot', 'Fbtot', 'Ask Sell Pahalılık', 'Emir Fiyat')
            pos_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)
            
            # Kolon genişlikleri
            col_widths = {'Symbol': 80, 'Qty': 60, 'Lot': 60, 'Fbtot': 60, 'Ask Sell Pahalılık': 100, 'Emir Fiyat': 80}
            for col in columns:
                pos_tree.heading(col, text=col)
                pos_tree.column(col, width=col_widths[col])
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=pos_tree.yview)
            pos_tree.configure(yscrollcommand=scrollbar.set)
            
            pos_tree.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # ✅ FİYAT VE LOT DEPOSU - pencereye özel
            order_data = {}  # {symbol: {'price': emir_fiyat, 'lot': lot_qty}}
            
            # Pozisyonları ekle
            for pos in positions:
                # Pozisyon verilerini al
                item_values = self.take_profit_longs_panel_reducemore.tree.item(pos['item'])['values']
                symbol = pos['symbol']
                qty = float(item_values[2])  # Quantity
                
                # Lot hesapla (%50, %75 veya %100)
                calculated_lot = qty * (lot_percentage / 100)
                
                # %100 lot için yuvarlama YAPILMAZ - tam lot miktarı kullanılır
                if lot_percentage == 100:
                    lot_qty = int(calculated_lot)
                # Lot yuvarlama mantığı (%50 ve %75 için)
                elif calculated_lot >= 0:
                    if calculated_lot <= 0:
                        lot_qty = 0
                    elif calculated_lot <= 100:
                        lot_qty = 100
                    elif calculated_lot <= 200:
                        lot_qty = 200
                    elif calculated_lot <= 300:
                        lot_qty = 300
                    elif calculated_lot <= 400:
                        lot_qty = 400
                    elif calculated_lot <= 500:
                        lot_qty = 500
                    elif calculated_lot <= 600:
                        lot_qty = 600
                    elif calculated_lot <= 700:
                        lot_qty = 700
                    elif calculated_lot <= 800:
                        lot_qty = 800
                    elif calculated_lot <= 900:
                        lot_qty = 900
                    elif calculated_lot <= 1000:
                        lot_qty = 1000
                    else:
                        lot_qty = int((calculated_lot + 99) // 100) * 100
                else:
                    abs_calculated = abs(calculated_lot)
                    if abs_calculated <= 100:
                        lot_qty = 100
                    elif abs_calculated <= 200:
                        lot_qty = 200
                    elif abs_calculated <= 300:
                        lot_qty = 300
                    elif abs_calculated <= 400:
                        lot_qty = -400
                    elif abs_calculated <= 500:
                        lot_qty = -500
                    elif abs_calculated <= 600:
                        lot_qty = -600
                    elif abs_calculated <= 700:
                        lot_qty = -700
                    elif abs_calculated <= 800:
                        lot_qty = -800
                    elif abs_calculated <= 900:
                        lot_qty = -900
                    elif abs_calculated <= 1000:
                        lot_qty = 1000
                    else:
                        lot_qty = int((abs_calculated + 99) // 100) * 100
                
                # Emir fiyatını hesapla (JFIN mantığı - KARBOTU ile aynı)
                emir_fiyat = 0
                market_data = None
                
                if hasattr(self, 'hammer') and self.hammer:
                    market_data = self.hammer.get_market_data(symbol)
                    if not market_data:
                        emir_fiyat = 0
                        continue
                else:
                    emir_fiyat = 0
                    continue
                
                bid = float(market_data.get('bid', 0))
                ask = float(market_data.get('ask', 0))
                
                if order_type == "Ask Sell":
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = ask - (spread * 0.15)
                    else:
                        emir_fiyat = 0
                        continue
                else:
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = ask - (spread * 0.15)
                    else:
                        emir_fiyat = 0
                        continue
                
                pos_tree.insert('', 'end', values=(
                    pos['symbol'],
                    f"{qty:.0f}",
                    f"{lot_qty:.0f}",
                    f"{pos['fbtot']:.2f}",
                    f"${pos['ask_sell_pahalilik']:.4f}",
                    f"${emir_fiyat:.2f}"
                ))
                
                if emir_fiyat > 0 and lot_qty != 0:
                    order_data[symbol] = {'price': emir_fiyat, 'lot': lot_qty}
            
            # Butonlar
            button_frame = ttk.Frame(confirm_win)
            button_frame.pack(fill='x', padx=10, pady=10)
            
            def on_confirm():
                try:
                    print(f"[REDUCEMORE] 🔄 {step_name} emirleri gönderiliyor...")
                    self.log_message(f"🔄 {step_name} emirleri gönderiliyor...")
                    
                    for symbol in order_data:
                        data = order_data[symbol]
                        emir_fiyat = data['price']
                        lot_qty = data['lot']
                        
                        if abs(lot_qty) < 200:
                            continue
                        
                        if self.mode_manager.is_hammer_mode():
                            hammer_symbol = symbol.replace(" PR", "-")
                            try:
                                success = self.hammer.place_order(
                                    symbol=hammer_symbol,
                                    side="SELL",
                                    quantity=lot_qty,
                                    price=emir_fiyat,
                                    order_type="LIMIT",
                                    hidden=True
                                )
                            except Exception as e:
                                pass
                        else:
                            success = self.mode_manager.place_order(
                                symbol=symbol,
                                side="SELL",
                                quantity=lot_qty,
                                price=emir_fiyat,
                                order_type="LIMIT",
                                hidden=True
                            )
                    
                    print(f"[REDUCEMORE] ✅ {step_name} emirleri gönderildi")
                    self.log_message(f"✅ {step_name} emirleri gönderildi")
                    
                except Exception as e:
                    print(f"[REDUCEMORE] ❌ Emir gönderme hatası: {e}")
                    self.log_message(f"❌ Emir gönderme hatası: {e}")
                
                confirm_win.destroy()
                self.reduce_more_proceed_to_next_step()
            
            def on_cancel():
                print(f"[REDUCEMORE] ❌ {step_name} iptal edildi")
                self.log_message(f"❌ {step_name} iptal edildi")
                confirm_win.destroy()
                self.reduce_more_proceed_to_next_step()
            
            def save_to_trades_csv():
                """Seçili emirleri trades.csv formatında kaydet"""
                try:
                    print(f"[REDUCEMORE CSV] 🔄 {len(positions)} emir trades.csv'ye kaydediliyor...")
                    self.log_message(f"🔄 {len(positions)} emir trades.csv'ye kaydediliyor...")
                    
                    # CSV satırları
                    csv_rows = []
                    
                    # PENCERE'DEKİ tablodan verileri al (zaten hesaplanmış fiyatlar var)
                    for item in pos_tree.get_children():
                        values = pos_tree.item(item)['values']
                        symbol = values[0]
                        qty = float(values[1])
                        lot_qty = float(values[2])
                        
                        # Emir fiyatını PENCERE'DEKİ DEĞERDEN al (zaten hesaplanmış)
                        emir_fiyat_str = values[5]  # "Emir Fiyat" kolonu
                        try:
                            # $ işaretini ve format karakterlerini temizle
                            emir_fiyat = float(str(emir_fiyat_str).replace('$', '').replace(',', '').strip())
                            print(f"[REDUCEMORE CSV] ✅ {symbol}: Emir fiyatı pencereden alındı: ${emir_fiyat:.2f}")
                        except (ValueError, TypeError, IndexError):
                            print(f"[REDUCEMORE CSV] ❌ {symbol}: Emir fiyatı okunamadı: {emir_fiyat_str}")
                            emir_fiyat = 0
                            continue
                        
                        # Lot ve fiyat ZATEN PENCREDEN ALINDI - market data çekmeye GEREK YOK!
                        # Minimum lot kontrolü
                        if abs(lot_qty) < 200:
                            continue
                        
                        # CSV'ye kaydet (fiyat ve lot zaten hazır)
                        if emir_fiyat > 0:
                            # CSV formatı (orijinal format)
                            csv_row = [
                                'SELL',                    # Action
                                int(lot_qty),             # Quantity
                                symbol,                    # Symbol
                                'STK',                    # SecType
                                'SMART/AMEX',              # Exchange
                                'USD',                    # Currency
                                'DAY',                    # TimeInForce
                                'LMT',                    # OrderType
                                f"{emir_fiyat:.2f}",      # LmtPrice
                                'Basket',                 # BasketTag
                                'U21016730',              # Account
                                'Basket',                 # OrderRef
                                'TRUE',                   # Hidden
                                'TRUE'                    # OutsideRth
                            ]
                            
                            csv_rows.append(csv_row)
                            print(f"[REDUCEMORE CSV] ✅ {symbol}: SELL {lot_qty} @ ${emir_fiyat:.2f}")
                    
                    if csv_rows:
                        # CSV dosyasına kaydet
                        import csv
                        
                        csv_filename = 'trades.csv'
                        
                        # Dosyayı sıfırdan yaz (write mode)
                        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                            writer = csv.writer(csvfile)
                            
                            # Başlık satırı (orijinal format)
                            writer.writerow(['Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 'Currency', 'TimeInForce', 'OrderType', 'LmtPrice', 'BasketTag', 'Account', 'OrderRef', 'Hidden', 'OutsideRth'])
                            
                            # Emir satırları
                            writer.writerows(csv_rows)
                        
                        print(f"[REDUCEMORE CSV] ✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                        self.log_message(f"✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                        messagebox.showinfo("Başarılı", f"{len(csv_rows)} emir trades.csv'ye kaydedildi!")
                    else:
                        messagebox.showwarning("Uyarı", "Kaydedilecek geçerli emir bulunamadı!")
                        
                except Exception as e:
                    print(f"[REDUCEMORE CSV] ❌ Kaydetme hatası: {e}")
                    self.log_message(f"❌ Kaydetme hatası: {e}")
                    messagebox.showerror("Hata", f"trades.csv kaydetme hatası: {e}")
            
            ttk.Button(button_frame, text="Send Orders", command=on_confirm, style='Accent.TButton').pack(side='left', padx=5)
            ttk.Button(button_frame, text="Save to trades.csv", command=save_to_trades_csv).pack(side='left', padx=5)
            ttk.Button(button_frame, text="İptal Et", command=on_cancel).pack(side='right', padx=5)
            
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Onay penceresi hatası: {e}")
            self.log_message(f"❌ Onay penceresi hatası: {e}")
    
    def reduce_more_select_shorts_positions_and_confirm(self, positions, order_type, lot_percentage, step_name):
        """REDUCEMORE: Shorts pozisyonları seç ve onay penceresi aç"""
        try:
            for pos in positions:
                self.take_profit_shorts_panel_reducemore.tree.set(pos['item'], "select", "✓")
                
                avg_cost_str = self.take_profit_shorts_panel_reducemore.tree.item(pos['item'])['values'][3]
                avg_cost = 0
                if avg_cost_str and avg_cost_str != 'N/A':
                    try:
                        clean_str = str(avg_cost_str).replace('$', '').replace(',', '').strip()
                        if clean_str and clean_str != 'nan':
                            avg_cost = float(clean_str)
                    except (ValueError, TypeError):
                        avg_cost = 0
                
                self.take_profit_shorts_panel_reducemore.selected_positions[pos['symbol']] = {
                    'qty': float(self.take_profit_shorts_panel_reducemore.tree.item(pos['item'])['values'][2]),
                    'avg_cost': avg_cost
                }
            
            # Lot yüzdesini ayarla
            if lot_percentage == 25:
                self.take_profit_shorts_panel_reducemore.set_lot_percentage(25)
            elif lot_percentage == 50:
                self.take_profit_shorts_panel_reducemore.set_lot_percentage(50)
            elif lot_percentage == 75:
                self.take_profit_shorts_panel_reducemore.set_lot_percentage(75)
            elif lot_percentage == 100:
                self.take_profit_shorts_panel_reducemore.set_lot_percentage(100)
            
            self.reduce_more_show_shorts_confirmation_window(positions, order_type, lot_percentage, step_name)
            
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Shorts pozisyon seçimi hatası: {e}")
            self.log_message(f"❌ REDUCEMORE Shorts pozisyon seçimi hatası: {e}")
    
    def reduce_more_show_shorts_confirmation_window(self, positions, order_type, lot_percentage, step_name):
        """REDUCEMORE Shorts onay penceresi göster - KARBOTU ile birebir aynı mantık"""
        try:
            confirm_win = tk.Toplevel(self.psfalgo_window)
            confirm_win.title(f"REDUCEMORE - {step_name}")
            confirm_win.geometry("600x400")
            confirm_win.transient(self.psfalgo_window)
            confirm_win.grab_set()
            
            title_frame = ttk.Frame(confirm_win)
            title_frame.pack(fill='x', padx=10, pady=10)
            
            ttk.Label(title_frame, text=f"REDUCEMORE - {step_name}", font=('Arial', 14, 'bold')).pack()
            ttk.Label(title_frame, text=f"{order_type} - %{lot_percentage} Lot", font=('Arial', 12)).pack()
            ttk.Label(title_frame, text=f"{len(positions)} pozisyon seçildi", font=('Arial', 10)).pack()
            
            list_frame = ttk.Frame(confirm_win)
            list_frame.pack(fill='both', expand=True, padx=10, pady=5)
            
            columns = ('Symbol', 'Qty', 'Lot', 'SFStot', 'Bid Buy Ucuzluk', 'Emir Fiyat')
            pos_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)
            
            col_widths = {'Symbol': 80, 'Qty': 60, 'Lot': 60, 'SFStot': 60, 'Bid Buy Ucuzluk': 100, 'Emir Fiyat': 80}
            for col in columns:
                pos_tree.heading(col, text=col)
                pos_tree.column(col, width=col_widths[col])
            
            scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=pos_tree.yview)
            pos_tree.configure(yscrollcommand=scrollbar.set)
            
            pos_tree.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            order_data = {}
            
            for pos in positions:
                item_values = self.take_profit_shorts_panel_reducemore.tree.item(pos['item'])['values']
                qty = float(item_values[2])  # Negatif gelebilir (-276 gibi)
                
                # Short pozisyonlar için ABS değer ile hesapla
                abs_qty = abs(qty)  # -276 -> 276
                calculated_lot = abs_qty * (lot_percentage / 100)  # 276 * 0.75 = 207
                
                # %100 lot için yuvarlama YAPILMAZ - tam lot miktarı kullanılır
                if lot_percentage == 100:
                    lot_qty = int(calculated_lot)  # 276 (pozitif)
                # Lot yuvarlama (%50 ve %75 için) - pozitif değer ile yuvarlama yap
                elif calculated_lot > 0:
                    if calculated_lot <= 0:
                        lot_qty = 0
                    elif calculated_lot <= 100:
                        lot_qty = 100
                    elif calculated_lot <= 200:
                        lot_qty = 200
                    elif calculated_lot <= 300:
                        lot_qty = 300
                    elif calculated_lot <= 400:
                        lot_qty = 400
                    elif calculated_lot <= 500:
                        lot_qty = 500
                    elif calculated_lot <= 600:
                        lot_qty = 600
                    elif calculated_lot <= 700:
                        lot_qty = 700
                    elif calculated_lot <= 800:
                        lot_qty = 800
                    elif calculated_lot <= 900:
                        lot_qty = 900
                    elif calculated_lot <= 1000:
                        lot_qty = 1000
                    else:
                        lot_qty = int((calculated_lot + 99) // 100) * 100
                else:
                    lot_qty = 0
                
                # Lot her zaman pozitif olmalı (BUY emri için short pozisyonu kapatmak için)
                # qty negatif olsa bile (short pozisyon), lot pozitif hesaplanır
                
                symbol = pos['symbol']
                emir_fiyat = 0
                market_data = None
                
                if hasattr(self, 'hammer') and self.hammer:
                    market_data = self.hammer.get_market_data(symbol)
                    if not market_data:
                        continue
                else:
                    continue
                
                bid = float(market_data.get('bid', 0))
                ask = float(market_data.get('ask', 0))
                
                if order_type == "Bid Buy":
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = bid + (spread * 0.15)
                    else:
                        continue
                else:
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = bid + (spread * 0.15)
                    else:
                        continue
                
                pos_tree.insert('', 'end', values=(
                    pos['symbol'],
                    f"{qty:.0f}",
                    f"{lot_qty:.0f}",
                    f"{pos['sfstot']:.2f}",
                    f"${pos['bid_buy_ucuzluk']:.4f}",
                    f"${emir_fiyat:.2f}"
                ))
                
                if emir_fiyat > 0 and lot_qty != 0:
                    order_data[symbol] = {'price': emir_fiyat, 'lot': lot_qty}
            
            button_frame = ttk.Frame(confirm_win)
            button_frame.pack(fill='x', padx=10, pady=10)
            
            def on_confirm():
                try:
                    print(f"[REDUCEMORE] 🔄 {step_name} emirleri gönderiliyor...")
                    self.log_message(f"🔄 {step_name} emirleri gönderiliyor...")
                    
                    for symbol in order_data:
                        data = order_data[symbol]
                        emir_fiyat = data['price']
                        lot_qty = data['lot']
                        
                        if abs(lot_qty) < 200:
                            continue
                        
                        if self.mode_manager.is_hammer_mode():
                            hammer_symbol = symbol.replace(" PR", "-")
                            try:
                                success = self.hammer.place_order(
                                    symbol=hammer_symbol,
                                    side="BUY",
                                    quantity=lot_qty,
                                    price=emir_fiyat,
                                    order_type="LIMIT",
                                    hidden=True
                                )
                            except Exception as e:
                                pass
                        else:
                            success = self.mode_manager.place_order(
                                symbol=symbol,
                                side="BUY",
                                quantity=lot_qty,
                                price=emir_fiyat,
                                order_type="LIMIT",
                                hidden=True
                            )
                    
                    print(f"[REDUCEMORE] ✅ {step_name} emirleri gönderildi")
                    self.log_message(f"✅ {step_name} emirleri gönderildi")
                    
                except Exception as e:
                    print(f"[REDUCEMORE] ❌ Emir gönderme hatası: {e}")
                    self.log_message(f"❌ Emir gönderme hatası: {e}")
                
                confirm_win.destroy()
                self.reduce_more_proceed_to_next_step()
            
            def on_cancel():
                print(f"[REDUCEMORE] ❌ {step_name} iptal edildi")
                self.log_message(f"❌ {step_name} iptal edildi")
                confirm_win.destroy()
                self.reduce_more_proceed_to_next_step()
            
            def save_to_trades_csv():
                """Seçili emirleri trades.csv formatında kaydet - SHORTS için BUY"""
                try:
                    print(f"[REDUCEMORE CSV SHORTS] 🔄 {len(positions)} emir trades.csv'ye kaydediliyor...")
                    self.log_message(f"🔄 {len(positions)} emir trades.csv'ye kaydediliyor...")
                    
                    # CSV satırları
                    csv_rows = []
                    
                    # PENCERE'DEKİ tablodan verileri al (zaten hesaplanmış fiyatlar var)
                    for item in pos_tree.get_children():
                        values = pos_tree.item(item)['values']
                        symbol = values[0]
                        qty = float(values[1])
                        lot_qty = float(values[2])
                        
                        # Emir fiyatını PENCERE'DEKİ DEĞERDEN al (zaten hesaplanmış)
                        emir_fiyat_str = values[5]  # "Emir Fiyat" kolonu
                        try:
                            # $ işaretini ve format karakterlerini temizle
                            emir_fiyat = float(str(emir_fiyat_str).replace('$', '').replace(',', '').strip())
                            print(f"[REDUCEMORE CSV SHORTS] ✅ {symbol}: Emir fiyatı pencereden alındı: ${emir_fiyat:.2f}")
                        except (ValueError, TypeError, IndexError):
                            print(f"[REDUCEMORE CSV SHORTS] ❌ {symbol}: Emir fiyatı okunamadı: {emir_fiyat_str}")
                            emir_fiyat = 0
                            continue
                        
                        # Lot ve fiyat ZATEN PENCREDEN ALINDI - market data çekmeye GEREK YOK!
                        # Minimum lot kontrolü
                        if abs(lot_qty) < 200:
                            continue
                        
                        # CSV'ye kaydet (fiyat ve lot zaten hazır) - SHORTS için BUY
                        if emir_fiyat > 0:
                            # CSV formatı (orijinal format) - Short pozisyon için BUY
                            csv_row = [
                                'BUY',                     # Action (short pozisyonu kapatmak için BUY)
                                int(lot_qty),             # Quantity
                                symbol,                    # Symbol
                                'STK',                    # SecType
                                'SMART/AMEX',              # Exchange
                                'USD',                    # Currency
                                'DAY',                    # TimeInForce
                                'LMT',                    # OrderType
                                f"{emir_fiyat:.2f}",      # LmtPrice
                                'Basket',                 # BasketTag
                                'U21016730',              # Account
                                'Basket',                 # OrderRef
                                'TRUE',                   # Hidden
                                'TRUE'                    # OutsideRth
                            ]
                            
                            csv_rows.append(csv_row)
                            print(f"[REDUCEMORE CSV SHORTS] ✅ {symbol}: BUY {lot_qty} @ ${emir_fiyat:.2f}")
                    
                    if csv_rows:
                        # CSV dosyasına kaydet
                        import csv
                        
                        csv_filename = 'trades.csv'
                        
                        # Dosyayı sıfırdan yaz (write mode)
                        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                            writer = csv.writer(csvfile)
                            
                            # Başlık satırı (orijinal format)
                            writer.writerow(['Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 'Currency', 'TimeInForce', 'OrderType', 'LmtPrice', 'BasketTag', 'Account', 'OrderRef', 'Hidden', 'OutsideRth'])
                            
                            # Emir satırları
                            writer.writerows(csv_rows)
                        
                        print(f"[REDUCEMORE CSV SHORTS] ✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                        self.log_message(f"✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                        messagebox.showinfo("Başarılı", f"{len(csv_rows)} emir trades.csv'ye kaydedildi!")
                    else:
                        messagebox.showwarning("Uyarı", "Kaydedilecek geçerli emir bulunamadı!")
                        
                except Exception as e:
                    print(f"[REDUCEMORE CSV SHORTS] ❌ Kaydetme hatası: {e}")
                    self.log_message(f"❌ Kaydetme hatası: {e}")
                    messagebox.showerror("Hata", f"trades.csv kaydetme hatası: {e}")
            
            ttk.Button(button_frame, text="Send Orders", command=on_confirm, style='Accent.TButton').pack(side='left', padx=5)
            ttk.Button(button_frame, text="Save to trades.csv", command=save_to_trades_csv).pack(side='left', padx=5)
            ttk.Button(button_frame, text="İptal Et", command=on_cancel).pack(side='right', padx=5)
            
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Shorts onay penceresi hatası: {e}")
            self.log_message(f"❌ Shorts onay penceresi hatası: {e}")
    
    def reduce_more_proceed_to_next_step(self):
        """REDUCEMORE: Sonraki adıma geç"""
        try:
            if self.reducemore_current_step >= self.reducemore_total_steps:
                print("[REDUCEMORE] 🎯 Tüm adımlar tamamlandı!")
                self.log_message("🎯 REDUCEMORE otomasyonu tamamlandı!")
                self.reducemore_running = False
                return
            
            next_step = self.reducemore_current_step + 1
            
            step_methods = {
                2: self.reduce_more_step_2_fbtot_lt_110,
                3: self.reduce_more_step_3_fbtot_111_145_low,
                4: self.reduce_more_step_4_fbtot_111_145_high,
                5: self.reduce_more_step_5_fbtot_146_185_low,
                6: self.reduce_more_step_6_fbtot_146_185_high,
                7: self.reduce_more_step_7_fbtot_186_210,
                8: self.reduce_more_step_8_open_take_profit_shorts,
                9: self.reduce_more_step_9_sfstot_170_high,
                10: self.reduce_more_step_10_sfstot_140_169_low,
                11: self.reduce_more_step_11_sfstot_140_169_high,
                12: self.reduce_more_step_12_sfstot_110_139_low,
                13: self.reduce_more_step_13_sfstot_110_139_high
            }
            
            if next_step in step_methods:
                self.reducemore_current_step = next_step
                step_methods[next_step]()
            else:
                print(f"[REDUCEMORE] ⚠️ Adım {next_step} henüz implement edilmedi")
                self.log_message(f"⚠️ Adım {next_step} henüz implement edilmedi")
                
        except Exception as e:
            print(f"[REDUCEMORE] ❌ Sonraki adım hatası: {e}")
            self.log_message(f"❌ Sonraki adım hatası: {e}")
    
    def karbotu_select_positions_and_confirm(self, positions, order_type, lot_percentage, step_name):
        """Pozisyonları seç ve onay penceresi aç"""
        try:
            # Pozisyonları seç
            for pos in positions:
                self.take_profit_longs_panel.tree.set(pos['item'], "select", "✓")
                
                # Avg cost'u güvenli şekilde parse et
                avg_cost_str = self.take_profit_longs_panel.tree.item(pos['item'])['values'][3]
                avg_cost = 0
                if avg_cost_str and avg_cost_str != 'N/A':
                    try:
                        clean_str = str(avg_cost_str).replace('$', '').replace(',', '').strip()
                        if clean_str and clean_str != 'nan':
                            avg_cost = float(clean_str)
                    except (ValueError, TypeError):
                        avg_cost = 0
                
                self.take_profit_longs_panel.selected_positions[pos['symbol']] = {
                    'qty': float(self.take_profit_longs_panel.tree.item(pos['item'])['values'][2]),
                    'avg_cost': avg_cost
                }
            
            # Lot yüzdesini ayarla
            if lot_percentage == 25:
                self.take_profit_longs_panel.set_lot_percentage(25)
            elif lot_percentage == 50:
                self.take_profit_longs_panel.set_lot_percentage(50)
            
            # Onay penceresini aç
            print(f"[KARBOTU DEBUG] 🔄 Onay penceresi açılıyor: {step_name}")
            self.karbotu_show_confirmation_window(positions, order_type, lot_percentage, step_name)
            
        except Exception as e:
            print(f"[KARBOTU] ❌ Pozisyon seçimi hatası: {e}")
            self.log_message(f"❌ Pozisyon seçimi hatası: {e}")
    
    def karbotu_send_orders_direct(self, positions, order_type, lot_percentage, step_name):
        """KARBOTU emirlerini direkt gönder (Allowed modunda onay penceresi olmadan)"""
        try:
            print(f"[KARBOTU] 🔄 {step_name} emirleri direkt gönderiliyor (Allowed modu)...")
            self.log_message(f"🔄 {step_name} emirleri direkt gönderiliyor (Allowed modu)...")
            
            # Pozisyon verilerini hazırla
            order_data = {}
            
            for pos in positions:
                item_values = self.take_profit_longs_panel.tree.item(pos['item'])['values']
                symbol = pos['symbol']
                qty = float(item_values[2])
                
                # Lot hesapla
                calculated_lot = qty * (lot_percentage / 100)
                
                # Lot yuvarlama
                if calculated_lot >= 0:
                    if calculated_lot <= 0:
                        lot_qty = 0
                    elif calculated_lot <= 100:
                        lot_qty = 100
                    elif calculated_lot <= 200:
                        lot_qty = 200
                    elif calculated_lot <= 300:
                        lot_qty = 300
                    elif calculated_lot <= 400:
                        lot_qty = 400
                    elif calculated_lot <= 500:
                        lot_qty = 500
                    else:
                        lot_qty = int((calculated_lot + 99) // 100) * 100
                else:
                    abs_calculated = abs(calculated_lot)
                    if abs_calculated <= 100:
                        lot_qty = 100
                    elif abs_calculated <= 200:
                        lot_qty = 200
                    elif abs_calculated <= 300:
                        lot_qty = 300
                    else:
                        lot_qty = int((abs_calculated + 99) // 100) * 100
                
                # MAXALW*3/4 limit kontrolü
                maxalw = self.get_maxalw_for_symbol(symbol)
                max_change_limit = maxalw * 3 / 4 if maxalw > 0 else 0
                
                # Gün başı pozisyon
                befday_qty = self.load_bef_position(symbol)
                
                # Mevcut pozisyon ve açık emirler
                current_qty = qty
                open_orders_qty = self.get_open_orders_sum(symbol, use_cache=True)
                current_potential = current_qty + open_orders_qty
                
                # Günlük değişim (mutlak değer)
                current_daily_change = abs(current_potential - befday_qty)
                
                # Yeni emir sonrası potansiyel değişim
                if order_type == "Ask Sell":
                    new_potential = current_potential - lot_qty
                else:
                    new_potential = current_potential + lot_qty
                
                potential_daily_change = abs(new_potential - befday_qty)
                
                # MAXALW*3/4 limitini aşacaksa emir gönderme
                if potential_daily_change > max_change_limit:
                    print(f"[KARBOTU] ⚠️ {symbol}: MAXALW*3/4 limiti aşılacak ({potential_daily_change:.0f} > {max_change_limit:.0f}), emir atlandı")
                    self.log_message(f"⚠️ {symbol}: MAXALW*3/4 limiti aşılacak, emir atlandı")
                    continue
                
                # Emir fiyatını hesapla
                market_data = None
                if hasattr(self, 'hammer') and self.hammer:
                    market_data = self.hammer.get_market_data(symbol)
                
                if not market_data:
                    print(f"[KARBOTU] ❌ {symbol} market_data bulunamadı, atlandı")
                    continue
                
                bid = float(market_data.get('bid', 0))
                ask = float(market_data.get('ask', 0))
                last = float(market_data.get('last', 0))
                
                emir_fiyat = 0
                if order_type == "Ask Sell":
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = ask - (spread * 0.15)
                    else:
                        continue
                elif order_type == "Bid Buy":
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = bid + (spread * 0.15)
                    else:
                        continue
                elif order_type == "Front Sell":
                    if last > 0:
                        emir_fiyat = last - 0.01
                    else:
                        continue
                elif order_type == "Front Buy":
                    if last > 0:
                        emir_fiyat = last + 0.01
                    else:
                        continue
                
                if emir_fiyat > 0 and lot_qty != 0:
                    order_data[symbol] = {'price': emir_fiyat, 'lot': lot_qty}
            
            # Emirleri gönder
            success_count = 0
            for symbol in order_data:
                data = order_data[symbol]
                emir_fiyat = data['price']
                lot_qty = data['lot']
                
                if abs(lot_qty) < 200:
                    continue
                
                # Controller kontrolü (MAXALW limitleri dahil)
                if hasattr(self, 'controller_enabled') and self.controller_enabled:
                    order_side = "SELL" if order_type in ["Ask Sell", "Front Sell"] else "BUY"
                    allowed, adjusted_qty, reason = self.controller_check_order(symbol, order_side, abs(lot_qty))
                    
                    if not allowed or adjusted_qty == 0:
                        print(f"[KARBOTU] ⚠️ {symbol}: Controller engelledi - {reason}")
                        self.log_message(f"⚠️ {symbol}: Controller engelledi - {reason}")
                        continue
                    
                    lot_qty = adjusted_qty if order_side == "SELL" else adjusted_qty
                
                # Emir gönder
                if self.mode_manager.is_hammer_mode():
                    hammer_symbol = symbol.replace(" PR", "-")
                    try:
                        success = self.hammer.place_order(
                            symbol=hammer_symbol,
                            side="SELL" if order_type in ["Ask Sell", "Front Sell"] else "BUY",
                            quantity=lot_qty,
                            price=emir_fiyat,
                            order_type="LIMIT",
                            hidden=True
                        )
                        if success or "new order sent" in str(success):
                            success_count += 1
                            print(f"[KARBOTU] ✅ {symbol}: {order_type} {lot_qty} lot @ ${emir_fiyat:.2f}")
                    except Exception as e:
                        if "new order sent" in str(e).lower():
                            success_count += 1
                        else:
                            print(f"[KARBOTU] ❌ {symbol}: {e}")
                else:
                    success = self.mode_manager.place_order(
                        symbol=symbol,
                        side="SELL" if order_type in ["Ask Sell", "Front Sell"] else "BUY",
                        quantity=lot_qty,
                        price=emir_fiyat,
                        order_type="LIMIT",
                        hidden=True
                    )
                    if success:
                        success_count += 1
                        print(f"[KARBOTU] ✅ {symbol}: {order_type} {lot_qty} lot @ ${emir_fiyat:.2f}")
            
            print(f"[KARBOTU] ✅ {step_name} tamamlandı: {success_count} emir gönderildi")
            self.log_message(f"✅ {step_name} tamamlandı: {success_count} emir gönderildi")
            
            # Sonraki adıma geç (kısa bir bekleme ile - adımlar sıralı ilerlesin)
            self.after(1000, self.karbotu_proceed_to_next_step)
            
        except Exception as e:
            print(f"[KARBOTU] ❌ Direkt emir gönderme hatası: {e}")
            self.log_message(f"❌ Direkt emir gönderme hatası: {e}")
            import traceback
            traceback.print_exc()
            # Hata olsa bile sonraki adıma geç (kısa bir bekleme ile)
            self.after(1000, self.karbotu_proceed_to_next_step)
    
    def karbotu_show_confirmation_window(self, positions, order_type, lot_percentage, step_name):
        """KARBOTU onay penceresi göster"""
        try:
            print(f"[KARBOTU DEBUG] 🔄 Onay penceresi fonksiyonu başladı: {step_name}")
            
            # RUNALL Allowed modunda otomatik onay kontrolü
            if hasattr(self, 'runall_allowed_mode') and self.runall_allowed_mode:
                print(f"[KARBOTU] ✅ Allowed modu aktif - Onay penceresi atlanıyor, emirler direkt gönderiliyor")
                self.log_message(f"✅ Allowed modu: {step_name} - Emirler otomatik gönderiliyor")
                # Emirleri direkt gönder (onay penceresi açmadan)
                self.karbotu_send_orders_direct(positions, order_type, lot_percentage, step_name)
                return
            
            # Onay penceresi
            confirm_win = tk.Toplevel(self.psfalgo_window)
            confirm_win.title(f"KARBOTU - {step_name}")
            confirm_win.geometry("600x400")
            confirm_win.transient(self.psfalgo_window)
            # grab_set() kaldırıldı - minimize edilebilir olması için
            
            # Başlık frame - minimize butonu ile
            title_frame = ttk.Frame(confirm_win)
            title_frame.pack(fill='x', padx=10, pady=10)
            
            # Sol taraf - başlık bilgileri
            title_left = ttk.Frame(title_frame)
            title_left.pack(side='left', fill='x', expand=True)
            
            ttk.Label(title_left, text=f"KARBOTU - {step_name}", font=('Arial', 14, 'bold')).pack(anchor='w')
            ttk.Label(title_left, text=f"{order_type} - %{lot_percentage} Lot", font=('Arial', 12)).pack(anchor='w')
            ttk.Label(title_left, text=f"{len(positions)} pozisyon seçildi", font=('Arial', 10)).pack(anchor='w')
            
            # Sağ taraf - minimize butonu
            window_controls = ttk.Frame(title_frame)
            window_controls.pack(side='right')
            
            # Alta Al (Minimize) butonu
            minimize_btn = ttk.Button(window_controls, text="🗕 Alta Al", width=10,
                                      command=lambda: confirm_win.iconify())
            minimize_btn.pack(side='left', padx=2)
            
            # Pozisyon listesi
            list_frame = ttk.Frame(confirm_win)
            list_frame.pack(fill='both', expand=True, padx=10, pady=5)
            
            # Treeview
            columns = ('Symbol', 'Qty', 'Lot', 'Fbtot', 'Ask Sell Pahalılık', 'Emir Fiyat')
            pos_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)
            
            # Kolon genişlikleri
            col_widths = {'Symbol': 80, 'Qty': 60, 'Lot': 60, 'Fbtot': 60, 'Ask Sell Pahalılık': 100, 'Emir Fiyat': 80}
            for col in columns:
                pos_tree.heading(col, text=col)
                pos_tree.column(col, width=col_widths[col])
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=pos_tree.yview)
            pos_tree.configure(yscrollcommand=scrollbar.set)
            
            pos_tree.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # ✅ FİYAT VE LOT DEPOSU - pencereye özel
            order_data = {}  # {symbol: {'price': emir_fiyat, 'lot': lot_qty}}
            
            # Pozisyonları ekle
            for pos in positions:
                # Pozisyon verilerini al
                item_values = self.take_profit_longs_panel.tree.item(pos['item'])['values']
                symbol = pos['symbol']
                qty = float(item_values[2])  # Quantity
                
                # Lot hesapla (%50 veya %25)
                calculated_lot = qty * (lot_percentage / 100)
                
                # Lot yuvarlama mantığı (negatif sayılar için)
                if calculated_lot >= 0:
                    # Pozitif sayılar için normal yuvarlama
                    if calculated_lot <= 0:
                        lot_qty = 0
                    elif calculated_lot <= 100:
                        lot_qty = 100
                    elif calculated_lot <= 200:
                        lot_qty = 200
                    elif calculated_lot <= 300:
                        lot_qty = 300
                    elif calculated_lot <= 400:
                        lot_qty = 400
                    elif calculated_lot <= 500:
                        lot_qty = 500
                    elif calculated_lot <= 600:
                        lot_qty = 600
                    elif calculated_lot <= 700:
                        lot_qty = 700
                    elif calculated_lot <= 800:
                        lot_qty = 800
                    elif calculated_lot <= 900:
                        lot_qty = 900
                    elif calculated_lot <= 1000:
                        lot_qty = 1000
                    else:
                        lot_qty = int((calculated_lot + 99) // 100) * 100
                else:
                    # Negatif sayılar için aşağı yuvarlama (daha negatif)
                    abs_calculated = abs(calculated_lot)
                    if abs_calculated <= 100:
                        lot_qty = 100
                    elif abs_calculated <= 200:
                        lot_qty = 200
                    elif abs_calculated <= 300:
                        lot_qty = 300
                    elif abs_calculated <= 400:
                        lot_qty = -400
                    elif abs_calculated <= 500:
                        lot_qty = -500
                    elif abs_calculated <= 600:
                        lot_qty = -600
                    elif abs_calculated <= 700:
                        lot_qty = -700
                    elif abs_calculated <= 800:
                        lot_qty = -800
                    elif abs_calculated <= 900:
                        lot_qty = -900
                    elif abs_calculated <= 1000:
                        lot_qty = 1000
                    else:
                        lot_qty = int((abs_calculated + 99) // 100) * 100
                
                # Emir fiyatını hesapla (emir tipine göre)
                symbol = pos['symbol']
                emir_fiyat = 0
                
                # JFIN ile BIREBIR aynı mantık - calculate_order_price metodunu kopyala
                print(f"[KARBOTU DEBUG] 🔍 {symbol} JFIN mantığı ile fiyat hesaplanıyor...")
                
                # JFIN'in calculate_order_price metodunu kopyala - AYNI MANTIK
                # Ana sayfadan market data al (JFIN ile TAMAMEN AYNI)
                market_data = None
                
                if hasattr(self, 'hammer') and self.hammer:
                    market_data = self.hammer.get_market_data(symbol)
                    if not market_data:
                        emir_fiyat = 0
                        print(f"[KARBOTU] ❌ {symbol} market_data boş - JFIN gibi N/A döndürülüyor")
                        continue
                else:
                    emir_fiyat = 0
                    print(f"[KARBOTU] ❌ {symbol} Hammer yok - JFIN gibi N/A döndürülüyor")
                    continue
                
                bid = float(market_data.get('bid', 0))
                ask = float(market_data.get('ask', 0))
                last = float(market_data.get('last', 0))
                
                print(f"[KARBOTU DEBUG] 📊 {symbol} JFIN market_data: bid=${bid:.2f}, ask=${ask:.2f}, last=${last:.2f}")
                
                # JFIN'in tam mantığını kopyala
                if order_type == "Bid Buy":
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = bid + (spread * 0.15)
                        print(f"[KARBOTU] ✅ {symbol} Bid Buy (JFIN): bid=${bid:.2f} + spread*0.15=${spread*0.15:.2f} = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU] ❌ {symbol} Bid Buy: bid/ask değerleri geçersiz")
                elif order_type == "Ask Sell":
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = ask - (spread * 0.15)
                        print(f"[KARBOTU] ✅ {symbol} Ask Sell (JFIN): ask=${ask:.2f} - spread*0.15=${spread*0.15:.2f} = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU] ❌ {symbol} Ask Sell: bid/ask değerleri geçersiz")
                elif order_type == "Front Buy":
                    if last > 0:
                        emir_fiyat = last + 0.01
                        print(f"[KARBOTU] ✅ {symbol} Front Buy (JFIN): last=${last:.2f} + 0.01 = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU] ❌ {symbol} Front Buy: last değeri geçersiz")
                elif order_type == "Front Sell":
                    if last > 0:
                        emir_fiyat = last - 0.01
                        print(f"[KARBOTU] ✅ {symbol} Front Sell (JFIN): last=${last:.2f} - 0.01 = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU] ❌ {symbol} Front Sell: last değeri geçersiz")
                elif order_type == "SoftFront Buy":
                    if last > 0:
                        emir_fiyat = last + 0.01
                        print(f"[KARBOTU] ✅ {symbol} SoftFront Buy (JFIN): last=${last:.2f} + 0.01 = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU] ❌ {symbol} SoftFront Buy: last değeri geçersiz")
                elif order_type == "SoftFront Sell":
                    if last > 0:
                        emir_fiyat = last - 0.01
                        print(f"[KARBOTU] ✅ {symbol} SoftFront Sell (JFIN): last=${last:.2f} - 0.01 = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU] ❌ {symbol} SoftFront Sell: last değeri geçersiz")
                elif order_type == "Bid Sell":
                    if bid > 0:
                        emir_fiyat = bid - 0.01
                        print(f"[KARBOTU] ✅ {symbol} Bid Sell (JFIN): bid=${bid:.2f} - 0.01 = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU] ❌ {symbol} Bid Sell: bid değeri geçersiz")
                elif order_type == "Ask Buy":
                    if ask > 0:
                        emir_fiyat = ask + 0.01
                        print(f"[KARBOTU] ✅ {symbol} Ask Buy (JFIN): ask=${ask:.2f} + 0.01 = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU] ❌ {symbol} Ask Buy: ask değeri geçersiz")
                else:
                    # Bilinmeyen emir tipi için Ask Sell formülü kullan
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        emir_fiyat = ask - (spread * 0.15)
                        print(f"[KARBOTU] ✅ {symbol} {order_type} (JFIN default): ask=${ask:.2f} - spread*0.15=${spread*0.15:.2f} = ${emir_fiyat:.2f}")
                    else:
                        emir_fiyat = 0
                        print(f"[KARBOTU] ❌ {symbol} {order_type}: bid/ask değerleri geçersiz")
                
                pos_tree.insert('', 'end', values=(
                    pos['symbol'],
                    f"{qty:.0f}",
                    f"{lot_qty:.0f}",
                    f"{pos['fbtot']:.2f}",
                    f"${pos['ask_sell_pahalilik']:.4f}",
                    f"${emir_fiyat:.2f}"
                ))
                
                # ✅ FİYAT VE LOT DEPOSAYA KAYDET
                if emir_fiyat > 0 and lot_qty != 0:
                    order_data[symbol] = {'price': emir_fiyat, 'lot': lot_qty}
                    print(f"[KARBOTU] ✅ {symbol} depoya kaydedildi: fiyat=${emir_fiyat:.2f}, lot={lot_qty}")
                else:
                    print(f"[KARBOTU] ⚠️ {symbol} geçersiz: fiyat=${emir_fiyat:.2f}, lot={lot_qty}")
            
            # Butonlar
            button_frame = ttk.Frame(confirm_win)
            button_frame.pack(fill='x', padx=10, pady=10)
            
            def on_confirm():
                """Onay verildi - Emirleri gönder - DEPODAN FİYATLARI KULLAN"""
                try:
                    print(f"[KARBOTU] 🔄 {step_name} emirleri gönderiliyor...")
                    self.log_message(f"🔄 {step_name} emirleri gönderiliyor...")
                    
                    # ✅ DEPODAN FİYATLARI KULLAN - Market data çekme YOK
                    for symbol in order_data:
                        data = order_data[symbol]
                        emir_fiyat = data['price']
                        lot_qty = data['lot']
                        
                        # ✅ Minimum 200 lot kontrolü - 200'den azsa skip et
                        if abs(lot_qty) < 200:
                            print(f"[KARBOTU] ⚠️ {symbol}: lot={lot_qty} < 200, atlandı")
                            continue
                        
                        print(f"[KARBOTU] 📤 {symbol}: fiyat=${emir_fiyat:.2f}, lot={lot_qty}")
                        
                        # Emir gönder
                        if self.mode_manager.is_hammer_mode():
                            # Hammer Pro - Symbol dönüşümü
                            hammer_symbol = symbol.replace(" PR", "-")
                            
                            try:
                                success = self.hammer.place_order(
                                    symbol=hammer_symbol,
                                    side="SELL",
                                    quantity=lot_qty,
                                    price=emir_fiyat,
                                    order_type="LIMIT",
                                    hidden=True
                                )
                                
                                if success or "new order sent" in str(success):
                                    print(f"[KARBOTU] ✅ {symbol} → {hammer_symbol}: SELL {lot_qty} lot @ ${emir_fiyat:.2f}")
                                else:
                                    print(f"[KARBOTU] ❌ {symbol} → {hammer_symbol}: SELL {lot_qty} lot @ ${emir_fiyat:.2f}")
                            except Exception as e:
                                if "new order sent" in str(e).lower():
                                    print(f"[KARBOTU] ✅ {symbol} → {hammer_symbol}: SELL {lot_qty} lot @ ${emir_fiyat:.2f} (new order sent)")
                                else:
                                    print(f"[KARBOTU] ❌ {symbol} → {hammer_symbol}: {e}")
                        else:
                            # IBKR
                            success = self.mode_manager.place_order(
                                symbol=symbol,
                                side="SELL",
                                quantity=lot_qty,
                                price=emir_fiyat,
                                order_type="LIMIT",
                                hidden=True
                            )
                            
                            if success:
                                print(f"[KARBOTU] ✅ {symbol}: SELL {lot_qty} lot @ ${emir_fiyat:.2f}")
                            else:
                                print(f"[KARBOTU] ❌ {symbol}: SELL {lot_qty} lot @ ${emir_fiyat:.2f}")
                    
                    print(f"[KARBOTU] ✅ {step_name} emirleri gönderildi")
                    self.log_message(f"✅ {step_name} emirleri gönderildi")
                    
                    # Popup'ları kapat
                    self.addnewpos_close_messagebox()
                    if hasattr(self, 'runall_allowed_mode') and self.runall_allowed_mode:
                        self.runall_auto_confirm_messagebox()
                    
                except Exception as e:
                    print(f"[KARBOTU] ❌ Emir gönderme hatası: {e}")
                    self.log_message(f"❌ Emir gönderme hatası: {e}")
                
                confirm_win.destroy()
                # Sonraki adıma geç (kısa bir bekleme ile - adımlar sıralı ilerlesin)
                self.after(1000, self.karbotu_proceed_to_next_step)
            
            def on_cancel():
                """İptal edildi"""
                print(f"[KARBOTU] ❌ {step_name} iptal edildi")
                self.log_message(f"❌ {step_name} iptal edildi")
                confirm_win.destroy()
                # Sonraki adıma geç (kısa bir bekleme ile - adımlar sıralı ilerlesin)
                self.after(1000, self.karbotu_proceed_to_next_step)
            
            def save_to_trades_csv():
                """Seçili emirleri trades.csv formatında kaydet"""
                try:
                    print(f"[KARBOTU CSV] 🔄 {len(positions)} emir trades.csv'ye kaydediliyor...")
                    self.log_message(f"🔄 {len(positions)} emir trades.csv'ye kaydediliyor...")
                    
                    # CSV satırları
                    csv_rows = []
                    
                    # PENCERE'DEKİ tablodan verileri al (zaten hesaplanmış fiyatlar var)
                    for item in pos_tree.get_children():
                        values = pos_tree.item(item)['values']
                        symbol = values[0]
                        qty = float(values[1])
                        lot_qty = float(values[2])
                        
                        # Emir fiyatını PENCERE'DEKİ DEĞERDEN al (zaten hesaplanmış)
                        emir_fiyat_str = values[5]  # "Emir Fiyat" kolonu
                        try:
                            # $ işaretini ve format karakterlerini temizle
                            emir_fiyat = float(str(emir_fiyat_str).replace('$', '').replace(',', '').strip())
                            print(f"[KARBOTU CSV] ✅ {symbol}: Emir fiyatı pencereden alındı: ${emir_fiyat:.2f}")
                        except (ValueError, TypeError, IndexError):
                            print(f"[KARBOTU CSV] ❌ {symbol}: Emir fiyatı okunamadı: {emir_fiyat_str}")
                            emir_fiyat = 0
                            continue
                        
                        # Lot ve fiyat ZATEN PENCREDEN ALINDI - market data çekmeye GEREK YOK!
                        # Minimum lot kontrolü
                        if abs(lot_qty) < 200:
                            continue
                        
                        # CSV'ye kaydet (fiyat ve lot zaten hazır)
                        if emir_fiyat > 0:
                            # CSV formatı (orijinal format)
                            csv_row = [
                                'SELL',                    # Action
                                int(lot_qty),             # Quantity
                                symbol,                    # Symbol
                                'STK',                    # SecType
                                'SMART/AMEX',              # Exchange
                                'USD',                    # Currency
                                'DAY',                    # TimeInForce
                                'LMT',                    # OrderType
                                f"{emir_fiyat:.2f}",      # LmtPrice
                                'Basket',                 # BasketTag
                                'U21016730',              # Account
                                'Basket',                 # OrderRef
                                'TRUE',                   # Hidden
                                'TRUE'                    # OutsideRth
                            ]
                            
                            csv_rows.append(csv_row)
                            print(f"[KARBOTU CSV] ✅ {symbol}: SELL {lot_qty} @ ${emir_fiyat:.2f}")
                    
                    if csv_rows:
                        # CSV dosyasına kaydet
                        import csv
                        
                        csv_filename = 'trades.csv'
                        
                        # Dosyayı sıfırdan yaz (write mode)
                        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                            writer = csv.writer(csvfile)
                            
                            # Başlık satırı (orijinal format)
                            writer.writerow(['Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 'Currency', 'TimeInForce', 'OrderType', 'LmtPrice', 'BasketTag', 'Account', 'OrderRef', 'Hidden', 'OutsideRth'])
                            
                            # Emir satırları
                            writer.writerows(csv_rows)
                        
                        print(f"[KARBOTU CSV] ✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                        self.log_message(f"✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                        messagebox.showinfo("Başarılı", f"{len(csv_rows)} emir trades.csv'ye kaydedildi!")
                    else:
                        messagebox.showwarning("Uyarı", "Kaydedilecek geçerli emir bulunamadı!")
                        
                except Exception as e:
                    print(f"[KARBOTU CSV] ❌ Kaydetme hatası: {e}")
                    self.log_message(f"❌ Kaydetme hatası: {e}")
                    messagebox.showerror("Hata", f"trades.csv kaydetme hatası: {e}")
            
            ttk.Button(button_frame, text="Send Orders", command=on_confirm, style='Accent.TButton').pack(side='left', padx=5)
            ttk.Button(button_frame, text="Save to trades.csv", command=save_to_trades_csv).pack(side='left', padx=5)
            ttk.Button(button_frame, text="İptal Et", command=on_cancel).pack(side='right', padx=5)
            
        except Exception as e:
            print(f"[KARBOTU] ❌ Onay penceresi hatası: {e}")
            self.log_message(f"❌ Onay penceresi hatası: {e}")
    
    def karbotu_proceed_to_next_step(self):
        """Sonraki adıma geç"""
        try:
            if self.karbotu_current_step >= self.karbotu_total_steps:
                self.log_message("🎯 KARBOTU otomasyonu tamamlandı!")
                self.karbotu_running = False
                
                # Tüm Take Profit pencerelerini kapat
                def close_karbotu_windows():
                    try:
                        # Take Profit Shorts penceresini kapat
                        if hasattr(self, 'take_profit_shorts_panel') and self.take_profit_shorts_panel:
                            try:
                                if hasattr(self.take_profit_shorts_panel, 'win') and self.take_profit_shorts_panel.win.winfo_exists():
                                    self.take_profit_shorts_panel.win.destroy()
                            except:
                                pass
                        
                        # Take Profit Longs penceresini kapat
                        if hasattr(self, 'take_profit_longs_panel') and self.take_profit_longs_panel:
                            try:
                                if hasattr(self.take_profit_longs_panel, 'win') and self.take_profit_longs_panel.win.winfo_exists():
                                    self.take_profit_longs_panel.win.destroy()
                            except:
                                pass
                        
                        # KARBOTU onay pencerelerini kapat
                        for widget in self.winfo_children():
                            try:
                                if isinstance(widget, tk.Toplevel):
                                    title = widget.title()
                                    if 'KARBOTU' in title or 'Emir Onayı' in title:
                                        widget.destroy()
                            except:
                                pass
                    except:
                        pass
                
                # Pencereleri hemen kapat
                close_karbotu_windows()
                
                # RUNALL'dan çağrıldıysa ADDNEWPOS kontrolü yap (SADECE BİR KEZ)
                if hasattr(self, 'runall_waiting_for_karbotu') and self.runall_waiting_for_karbotu:
                    if not hasattr(self, 'runall_addnewpos_triggered') or not self.runall_addnewpos_triggered:
                        self.runall_waiting_for_karbotu = False
                        self.runall_addnewpos_triggered = True  # İşaretle ki tekrar tetiklenmesin
                        self.after(2000, self.runall_check_karbotu_and_addnewpos)  # 2 saniye sonra kontrol et
                
                return
            
            # Sonraki adımı çağır
            next_step = self.karbotu_current_step + 1
            
            # Adım fonksiyonlarını mapping
            step_methods = {
                2: self.karbotu_step_2_fbtot_lt_110,
                3: self.karbotu_step_3_fbtot_111_145_low,
                4: self.karbotu_step_4_fbtot_111_145_high,
                5: self.karbotu_step_5_fbtot_146_185_low,
                6: self.karbotu_step_6_fbtot_146_185_high,
                7: self.karbotu_step_7_fbtot_186_210,
                8: self.karbotu_step_8_open_take_profit_shorts,
                9: self.karbotu_step_9_sfstot_170_high,
                10: self.karbotu_step_10_sfstot_140_169_low,
                11: self.karbotu_step_11_sfstot_140_169_high,
                12: self.karbotu_step_12_sfstot_110_139_low,
                13: self.karbotu_step_13_sfstot_110_139_high
            }
            
            if next_step in step_methods:
                self.karbotu_current_step = next_step
                step_methods[next_step]()
            else:
                print(f"[KARBOTU] ⚠️ Adım {next_step} henüz implement edilmedi")
                self.log_message(f"⚠️ Adım {next_step} henüz implement edilmedi")
                
        except Exception as e:
            print(f"[KARBOTU] ❌ Sonraki adım hatası: {e}")
            self.log_message(f"❌ Sonraki adım hatası: {e}")
    
    def runall_check_karbotu_and_addnewpos(self):
        """KARBOTU bitince exposure kontrolü yap ve ADDNEWPOS tetikle (SADECE BİR KEZ)"""
        try:
            # Eğer zaten tetiklendiyse tekrar çalıştırma
            if hasattr(self, 'runall_addnewpos_triggered') and self.runall_addnewpos_triggered:
                # Ama henüz start_addnewpos_automation çağrılmadıysa devam et
                if hasattr(self, 'runall_addnewpos_started') and self.runall_addnewpos_started:
                    print("[RUNALL] ⚠️ ADDNEWPOS zaten başlatıldı, tekrar tetiklenmeyecek")
                    return
            
            # KARBOTU hala çalışıyorsa tekrar kontrol et
            if hasattr(self, 'karbotu_running') and self.karbotu_running:
                self.after(5000, self.runall_check_karbotu_and_addnewpos)
                return
            
            print("[RUNALL] 🔍 KARBOTU tamamlandı, exposure kontrolü yapılıyor...")
            self.log_message("🔍 KARBOTU tamamlandı, exposure kontrolü yapılıyor...")
            
            # Exposure kontrolü yap
            exposure_info = self.check_exposure_limits()
            pot_total = exposure_info.get('pot_total', 0)
            pot_max_lot = exposure_info.get('pot_max_lot', 63636)
            total_lots = exposure_info.get('total_lots', 0)
            max_lot = exposure_info.get('max_lot', 54545)
            mode = exposure_info.get('mode', 'UNKNOWN')
            
            # Pot Toplam kontrolü - Limit dolduracak emirler var mı?
            if mode == "OFANSIF" and pot_total < pot_max_lot:
                # Eğer zaten başlatıldıysa tekrar başlatma
                if hasattr(self, 'runall_addnewpos_started') and self.runall_addnewpos_started:
                    print("[RUNALL] ⚠️ ADDNEWPOS zaten başlatıldı, tekrar tetiklenmeyecek")
                    self.log_message("⚠️ ADDNEWPOS zaten başlatıldı, tekrar tetiklenmeyecek")
                    return
                
                available_lot = pot_max_lot - pot_total
                print(f"[RUNALL] ✅ ADDNEWPOS tetikleniyor: Pot Toplam {pot_total:,} < Pot Max {pot_max_lot:,} (Açılabilir: {available_lot:,} lot)")
                self.log_message(f"✅ ADDNEWPOS tetikleniyor: Pot Toplam {pot_total:,} < Pot Max {pot_max_lot:,} (Açılabilir: {available_lot:,} lot)")
                
                # ADDNEWPOS'un başlatıldığını işaretle
                self.runall_addnewpos_started = True
                
                # ADDNEWPOS'u otomatik başlat (RUNALL'dan çağrıldığını belirt)
                # ADDNEWPOS bitince callback ekle
                self.runall_addnewpos_callback_set = True
                self.after(2000, lambda: self.start_addnewpos_automation(from_runall=True))
            else:
                print(f"[RUNALL] ℹ️ ADDNEWPOS gerekmiyor: Mode={mode}, Pot Toplam={pot_total:,}, Pot Max={pot_max_lot:,}")
                self.log_message(f"ℹ️ ADDNEWPOS gerekmiyor: Mode={mode}, Pot Toplam={pot_total:,}, Pot Max={pot_max_lot:,}")
                
                # ADDNEWPOS gerekmiyorsa direkt emirleri iptal et ve tekrar başla
                if hasattr(self, 'runall_loop_running') and self.runall_loop_running:
                    print("[RUNALL] 🔄 ADDNEWPOS gerekmiyor, emirleri iptal edip yeni döngüye geçiliyor...")
                    self.log_message("🔄 ADDNEWPOS gerekmiyor, emirleri iptal edip yeni döngüye geçiliyor...")
                    self.after(2000, lambda: self.runall_cancel_orders_and_restart())
            
            print("[RUNALL] ✅ RUNALL sırası tamamlandı!")
            self.log_message("✅ RUNALL sırası tamamlandı!")
            
            # Not: ADDNEWPOS emirleri gönderildikten sonra callback final_thg_lot_distributor.py'de tetiklenecek
            
        except Exception as e:
            print(f"[RUNALL] ❌ KARBOTU sonrası kontrol hatası: {e}")
            self.log_message(f"❌ KARBOTU sonrası kontrol hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def runall_cancel_orders_and_restart(self):
        """RUNALL döngüsü: Tüm emirleri iptal et ve tekrar başla"""
        try:
            print("[RUNALL] 🗑️ Tüm emirleri iptal ediliyor...")
            self.log_message("🗑️ Tüm emirleri iptal ediliyor...")
            
            # Aktif modu kontrol et
            if hasattr(self, 'mode_manager'):
                active_account = self.mode_manager.get_active_account()
            else:
                if self.hampro_mode:
                    active_account = "HAMPRO"
                elif self.ibkr_gun_mode:
                    active_account = "IBKR_GUN"
                elif self.ibkr_ped_mode:
                    active_account = "IBKR_PED"
                else:
                    active_account = "HAMPRO"
            
            # IBKR modunda: Doğrudan tüm emirleri iptal et (pencere açmadan)
            if active_account in ["IBKR_GUN", "IBKR_PED"]:
                try:
                    print("[RUNALL] 🗑️ IBKR emirleri doğrudan iptal ediliyor...")
                    self.log_message("🗑️ IBKR emirleri doğrudan iptal ediliyor...")
                    
                    # IBKR client'ı al
                    ibkr_client = None
                    if hasattr(self.mode_manager, 'ibkr_native_client') and self.mode_manager.ibkr_native_client.is_connected():
                        ibkr_client = self.mode_manager.ibkr_native_client
                    elif hasattr(self.mode_manager, 'ibkr_client') and self.mode_manager.ibkr_client.is_connected():
                        ibkr_client = self.mode_manager.ibkr_client
                    
                    if ibkr_client and ibkr_client.is_connected():
                        # Açık emirleri al
                        if hasattr(ibkr_client, 'get_open_orders'):
                            open_orders = ibkr_client.get_open_orders()
                        else:
                            open_orders = ibkr_client.get_orders_direct() if hasattr(ibkr_client, 'get_orders_direct') else []
                        
                        if open_orders:
                            print(f"[RUNALL] 📊 {len(open_orders)} açık emir bulundu, iptal ediliyor...")
                            cancel_count = 0
                            for order in open_orders:
                                try:
                                    order_id = order.get('order_id') or order.get('orderId')
                                    if order_id:
                                        if hasattr(ibkr_client, 'cancelOrder'):
                                            ibkr_client.cancelOrder(int(order_id))
                                        elif hasattr(ibkr_client, 'cancel_order'):
                                            ibkr_client.cancel_order(order_id)
                                        cancel_count += 1
                                        print(f"[RUNALL] 📤 İptal isteği gönderildi: {order_id}")
                                except Exception as e:
                                    print(f"[RUNALL] ⚠️ Emir iptal hatası: {e}")
                            
                            print(f"[RUNALL] ✅ {cancel_count} emir iptal isteği gönderildi")
                            # 2 saniye sonra tekrar başla
                            self.after(2000, lambda: self.runall_close_orders_window_and_restart(None))
                        else:
                            print("[RUNALL] ℹ️ İptal edilecek emir bulunamadı")
                            # Direkt tekrar başla
                            self.after(1000, lambda: self.runall_close_orders_window_and_restart(None))
                    else:
                        print("[RUNALL] ❌ IBKR bağlantısı yok")
                        # Hata olsa bile devam et
                        self.after(2000, lambda: self.runall_close_orders_window_and_restart(None))
                    
                except Exception as e:
                    print(f"[RUNALL] ❌ IBKR emir iptal hatası: {e}")
                    self.log_message(f"❌ IBKR emir iptal hatası: {e}")
                    # Hata olsa bile devam et
                    self.after(2000, lambda: self.runall_close_orders_window_and_restart(None))
            
            # HAMPRO modunda: Doğrudan tüm emirleri iptal et (pencere açmadan)
            else:  # HAMPRO
                try:
                    print("[RUNALL] 🗑️ HAMPRO emirleri doğrudan iptal ediliyor...")
                    self.log_message("🗑️ HAMPRO emirleri doğrudan iptal ediliyor...")
                    
                    if self.hammer and self.hammer.connected:
                        # Açık emirleri al
                        open_orders = self.hammer.get_orders_direct() if hasattr(self.hammer, 'get_orders_direct') else []
                        
                        if open_orders:
                            print(f"[RUNALL] 📊 {len(open_orders)} açık emir bulundu, iptal ediliyor...")
                            cancel_count = 0
                            for order in open_orders:
                                try:
                                    order_id = order.get('order_id') or order.get('orderId')
                                    if order_id:
                                        if hasattr(self.hammer, 'trade_command_cancel'):
                                            self.hammer.trade_command_cancel("ALARIC:TOPI002240A7", order_id)
                                        cancel_count += 1
                                        print(f"[RUNALL] 📤 İptal isteği gönderildi: {order_id}")
                                except Exception as e:
                                    print(f"[RUNALL] ⚠️ Emir iptal hatası: {e}")
                            
                            print(f"[RUNALL] ✅ {cancel_count} emir iptal isteği gönderildi")
                            # 2 saniye sonra tekrar başla
                            self.after(2000, lambda: self.runall_close_orders_window_and_restart(None))
                        else:
                            print("[RUNALL] ℹ️ İptal edilecek emir bulunamadı")
                            # Direkt tekrar başla
                            self.after(1000, lambda: self.runall_close_orders_window_and_restart(None))
                    else:
                        print("[RUNALL] ❌ HAMPRO bağlantısı yok")
                        # Hata olsa bile devam et
                        self.after(2000, lambda: self.runall_close_orders_window_and_restart(None))
                    
                except Exception as e:
                    print(f"[RUNALL] ❌ HAMPRO emir iptal hatası: {e}")
                    self.log_message(f"❌ HAMPRO emir iptal hatası: {e}")
                    # Hata olsa bile devam et
                    self.after(2000, lambda: self.runall_close_orders_window_and_restart(None))
            
        except Exception as e:
            print(f"[RUNALL] ❌ Emir iptal ve restart hatası: {e}")
            self.log_message(f"❌ Emir iptal ve restart hatası: {e}")
            import traceback
            traceback.print_exc()
            # Hata olsa bile devam et
            self.after(2000, lambda: self.runall_close_orders_window_and_restart(None))
    
    def start_runall_auto_confirm_loop(self):
        """RUNALL Allowed modunda otomatik onay döngüsünü başlat"""
        if not self.runall_allowed_mode or not self.runall_loop_running:
            return
        
        # Tıklanmış butonları ve kapatılmış pencereleri takip et (tekrar tıklamayı önlemek için)
        if not hasattr(self, '_clicked_buttons'):
            self._clicked_buttons = set()
        if not hasattr(self, '_closed_windows'):
            self._closed_windows = set()
        
        # Her 200ms'de bir onay mesajlarını kontrol et (daha sık kontrol)
        self.runall_auto_confirm_messagebox()
        self.after(200, self.start_runall_auto_confirm_loop)
    
    def runall_auto_confirm_messagebox(self):
        """Onay mesajlarını otomatik olarak kabul et (Evet/Yes butonuna tıkla)"""
        if not self.runall_allowed_mode:
            return
        
        # Tıklanmış butonları ve kapatılmış pencereleri takip et (tekrar tıklamayı önlemek için)
        if not hasattr(self, '_clicked_buttons'):
            self._clicked_buttons = set()
        if not hasattr(self, '_closed_windows'):
            self._closed_windows = set()
        
        try:
            # Tüm Toplevel pencereleri bul (daha agresif yöntem)
            all_toplevels = []
            
            # Ana pencereden başla
            try:
                for widget in self.winfo_children():
                    if isinstance(widget, tk.Toplevel):
                        all_toplevels.append(widget)
            except:
                pass
            
            # Psfalgo penceresinden
            if hasattr(self, 'psfalgo_window') and self.psfalgo_window:
                try:
                    if self.psfalgo_window.winfo_exists():
                        for widget in self.psfalgo_window.winfo_children():
                            if isinstance(widget, tk.Toplevel):
                                all_toplevels.append(widget)
                except:
                    pass
            
            # Take Profit pencerelerinden
            if hasattr(self, 'take_profit_longs_panel') and hasattr(self.take_profit_longs_panel, 'win'):
                try:
                    if self.take_profit_longs_panel.win.winfo_exists():
                        for widget in self.take_profit_longs_panel.win.winfo_children():
                            if isinstance(widget, tk.Toplevel):
                                all_toplevels.append(widget)
                except:
                    pass
            
            if hasattr(self, 'take_profit_shorts_panel') and hasattr(self.take_profit_shorts_panel, 'win'):
                try:
                    if self.take_profit_shorts_panel.win.winfo_exists():
                        for widget in self.take_profit_shorts_panel.win.winfo_children():
                            if isinstance(widget, tk.Toplevel):
                                all_toplevels.append(widget)
                except:
                    pass
            
            # Tüm açık Toplevel pencereleri bul (recursive)
            def find_all_toplevels(parent, found_list, depth=0):
                if depth > 5:  # Recursion limit
                    return
                try:
                    for widget in parent.winfo_children():
                        if isinstance(widget, tk.Toplevel):
                            if widget not in found_list:
                                found_list.append(widget)
                            find_all_toplevels(widget, found_list, depth + 1)
                        else:
                            find_all_toplevels(widget, found_list, depth + 1)
                except:
                    pass
            
            find_all_toplevels(self, all_toplevels)
            
            # Tüm butonları recursive olarak bul (fonksiyon tanımı)
            def find_all_buttons_recursive(widget, buttons_list, depth=0):
                if depth > 15:  # Recursion limit
                    return
                try:
                    for child in widget.winfo_children():
                        try:
                            if isinstance(child, (tk.Button, ttk.Button)):
                                buttons_list.append(child)
                            find_all_buttons_recursive(child, buttons_list, depth + 1)
                        except:
                            pass
                except:
                    pass
            
            # Her Toplevel penceresinde buton ara
            for toplevel in all_toplevels:
                try:
                    # Pencere hala var mı kontrol et
                    if not toplevel.winfo_exists():
                        continue
                    
                    title = toplevel.title().lower()
                    
                    # "Emir Sonucu" ve "Başarılı" (TUMCSV) pencerelerini özel olarak kontrol et
                    if 'emir sonucu' in title or ('başarılı' in title):
                        # Bu pencere zaten kapatıldı mı kontrol et
                        window_id = id(toplevel)
                        if window_id in self._closed_windows:
                            continue  # Zaten kapatıldı, atla
                        
                        # TUMCSV popup'ı kontrol et
                        is_tumcsv_popup = False
                        try:
                            # Pencere içeriğini kontrol et
                            for widget in toplevel.winfo_children():
                                try:
                                    widget_text = str(widget).lower()
                                    if 'tumcsv' in widget_text or 'ayarlaması' in widget_text:
                                        is_tumcsv_popup = True
                                        break
                                    # Label'ları kontrol et
                                    if isinstance(widget, (tk.Label, ttk.Label)):
                                        label_text = widget.cget('text').lower() if hasattr(widget, 'cget') else ''
                                        if 'tumcsv' in label_text or 'ayarlaması' in label_text:
                                            is_tumcsv_popup = True
                                            break
                                except:
                                    pass
                        except:
                            pass
                        
                        print(f"[RUNALL] 🔍 Popup penceresi bulundu: {toplevel.title()} (TUMCSV: {is_tumcsv_popup})")
                        buttons = []
                        find_all_buttons_recursive(toplevel, buttons)
                        # "Tamam" butonunu bul ve tıkla
                        for btn in buttons:
                            try:
                                if not btn.winfo_exists():
                                    continue
                                
                                # Bu buton zaten tıklandı mı kontrol et
                                button_id = id(btn)
                                if button_id in self._clicked_buttons:
                                    continue  # Zaten tıklandı, atla
                                
                                text = str(btn.cget('text')).lower().strip()
                                if 'tamam' in text or 'ok' in text:
                                    print(f"[RUNALL] ✅ Popup penceresindeki '{text}' butonu bulundu, tıklanıyor... ({toplevel.title()})")
                                    # Butonu işaretle (tekrar tıklanmasın)
                                    self._clicked_buttons.add(button_id)
                                    btn.invoke()
                                    # Pencereyi de kapat ve işaretle
                                    try:
                                        if toplevel.winfo_exists():
                                            toplevel.destroy()
                                            self._closed_windows.add(window_id)
                                    except:
                                        pass
                                    break
                            except:
                                pass
                        continue  # Bu pencereyi işledik, diğerlerine geç
                    
                    buttons = []
                    find_all_buttons_recursive(toplevel, buttons)
                    
                    # Her butonu kontrol et
                    for btn in buttons:
                        try:
                            if not btn.winfo_exists():
                                continue
                            
                            text = str(btn.cget('text')).lower().strip()
                            
                            # Onay butonları için genişletilmiş keyword listesi
                            confirm_keywords = [
                                'ok', 'tamam', 'yes', 'evet', 'kabul', 'accept', 'onayla', 'confirm',
                                'gönder', 'send', 'emirleri gönder', 'okay', 'devam', 'continue',
                                'ilerle', 'proceed', 'başlat', 'start', 'çalıştır', 'run'
                            ]
                            
                            if any(keyword in text for keyword in confirm_keywords):
                                # İptal/Reddet butonlarını atla
                                if any(cancel_keyword in text for cancel_keyword in ['iptal', 'cancel', 'reddet', 'no', 'hayır', 'kapat', 'close']):
                                    continue
                                
                                # Bu buton zaten tıklandı mı kontrol et
                                button_id = id(btn)
                                if button_id in self._clicked_buttons:
                                    continue  # Zaten tıklandı, atla
                                
                                # Bu pencere zaten kapatıldı mı kontrol et
                                window_id = id(toplevel)
                                if window_id in self._closed_windows:
                                    continue  # Pencere zaten kapatıldı, atla
                                
                                print(f"[RUNALL] ✅ Onay butonu bulundu: '{text}' (Pencere: '{title}'), tıklanıyor...")
                                self.log_message(f"✅ Otomatik onay: '{text}' ({title})")
                                
                                # Butonu işaretle (tekrar tıklanmasın)
                                self._clicked_buttons.add(button_id)
                                
                                # Butonu tıkla
                                try:
                                    btn.invoke()
                                    # invoke sonrası kısa bir bekleme ekle
                                    self.after(100, lambda: None)
                                    
                                    # Pencere kapatıldıysa işaretle
                                    try:
                                        if not toplevel.winfo_exists():
                                            self._closed_windows.add(window_id)
                                    except:
                                        pass
                                except:
                                    # invoke çalışmazsa event_generate dene
                                    try:
                                        btn.event_generate('<Button-1>')
                                        self.after(100, lambda: None)
                                        
                                        # Pencere kapatıldıysa işaretle
                                        try:
                                            if not toplevel.winfo_exists():
                                                self._closed_windows.add(window_id)
                                        except:
                                            pass
                                    except:
                                        pass
                                
                                # Bir buton bulundu ve tıklandı, diğerlerini kontrol etmeye devam et
                                break
                        except Exception as e:
                            continue
                            
                except Exception as e:
                    continue
            
            # Ek olarak: Tkinter'ın messagebox'larını bulmak için özel bir yöntem
            # Messagebox'lar genellikle boş başlıklı Toplevel pencereler olarak oluşturulur
            try:
                # Tüm widget'ları tarayarak messagebox benzeri pencereleri bul
                def find_messagebox_windows(parent, found_list, depth=0):
                    if depth > 10:
                        return
                    try:
                        for widget in parent.winfo_children():
                            if isinstance(widget, tk.Toplevel):
                                try:
                                    title = widget.title()
                                    # Boş başlık veya bilgi mesajı içeren pencereler
                                    if title == '' or any(keyword in title.lower() for keyword in ['bilgi', 'info', 'onay', 'confirm', 'uyarı', 'warning']):
                                        if widget not in found_list:
                                            found_list.append(widget)
                                except:
                                    pass
                            find_messagebox_windows(widget, found_list, depth + 1)
                    except:
                        pass
                
                messagebox_windows = []
                find_messagebox_windows(self, messagebox_windows)
                
                # Messagebox pencerelerindeki butonları bul
                for mb_window in messagebox_windows:
                    try:
                        if not mb_window.winfo_exists():
                            continue
                        
                        # Tüm butonları bul
                        mb_buttons = []
                        find_all_buttons_recursive(mb_window, mb_buttons)
                        
                        for btn in mb_buttons:
                            try:
                                # Bu buton zaten tıklandı mı kontrol et
                                button_id = id(btn)
                                if button_id in self._clicked_buttons:
                                    continue  # Zaten tıklandı, atla
                                
                                text = str(btn.cget('text')).lower().strip()
                                if any(keyword in text for keyword in ['ok', 'tamam', 'yes', 'evet', 'kabul', 'accept']):
                                    if not any(cancel_keyword in text for cancel_keyword in ['iptal', 'cancel', 'reddet', 'no', 'hayır']):
                                        print(f"[RUNALL] ✅ Messagebox butonu bulundu: '{text}', tıklanıyor...")
                                        self.log_message(f"✅ Otomatik onay (messagebox): '{text}'")
                                        
                                        # Butonu işaretle (tekrar tıklanmasın)
                                        self._clicked_buttons.add(button_id)
                                        
                                        try:
                                            btn.invoke()
                                            self.after(100, lambda: None)
                                            
                                            # Pencere kapatıldıysa işaretle
                                            try:
                                                if not mb_window.winfo_exists():
                                                    self._closed_windows.add(id(mb_window))
                                            except:
                                                pass
                                        except:
                                            try:
                                                btn.event_generate('<Button-1>')
                                                self.after(100, lambda: None)
                                                
                                                # Pencere kapatıldıysa işaretle
                                                try:
                                                    if not mb_window.winfo_exists():
                                                        self._closed_windows.add(id(mb_window))
                                                except:
                                                    pass
                                            except:
                                                pass
                                        break
                            except:
                                continue
                    except:
                        continue
            except:
                pass
            
        except Exception as e:
            print(f"[RUNALL] ⚠️ Onay mesajı bulma hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def stop_runall_loop(self):
        """RUNALL döngüsünü durdur"""
        try:
            print("[RUNALL] ⏹️ RUNALL döngüsü durduruluyor...")
            self.log_message("⏹️ RUNALL döngüsü durduruluyor...")
            self.runall_loop_running = False
            
            # Buton metnini güncelle
            if hasattr(self, 'runall_btn'):
                self.runall_btn.config(text="▶️ RUNALL", state='normal')
                self.runall_btn.config(style='Accent.TButton')
            if hasattr(self, 'runall_stop_btn'):
                self.runall_stop_btn.config(state='disabled')
            
            print("[RUNALL] ✅ RUNALL döngüsü durduruldu")
            self.log_message("✅ RUNALL döngüsü durduruldu")
            
        except Exception as e:
            print(f"[RUNALL] ❌ Durdurma hatası: {e}")
            self.log_message(f"❌ Durdurma hatası: {e}")
    
    def runall_close_orders_window_and_restart(self, orders_window):
        """Emirlerim penceresini kapat ve RUNALL döngüsünü tekrar başlat"""
        try:
            # Döngü durdurulmuşsa devam etme
            if not hasattr(self, 'runall_loop_running') or not self.runall_loop_running:
                print("[RUNALL] ⏹️ Döngü durdurulmuş, tekrar başlatılmayacak")
                self.log_message("⏹️ Döngü durdurulmuş, tekrar başlatılmayacak")
                return
            
            # Pencereyi kapat
            if orders_window:
                try:
                    orders_window.destroy()
                except:
                    pass
            
            print("[RUNALL] ✅ Emirler iptal edildi, yeni döngü başlatılıyor...")
            self.log_message("✅ Emirler iptal edildi, yeni döngü başlatılıyor...")
            
            # Flag'leri resetle - YENİ DÖNGÜ İÇİN HAZIRLA
            self.runall_addnewpos_triggered = False
            self.runall_addnewpos_started = False
            self.runall_waiting_for_karbotu = False
            self.runall_addnewpos_callback_set = False
            
            # KARBOTU flag'lerini de resetle
            if hasattr(self, 'karbotu_running'):
                self.karbotu_running = False
            
            # Controller'ın açık olduğundan emin ol
            if not self.controller_enabled:
                self.controller_enabled = True
                if hasattr(self, 'controller_btn'):
                    self.controller_btn.config(text="🎛️ Controller: ON")
                    self.controller_btn.config(style='Success.TButton')
            
            # Exposure kontrolü yap
            exposure_info = self.check_exposure_limits()
            self.log_message(f"📊 Exposure kontrolü: {exposure_info.get('mode', 'UNKNOWN')} mod")
            
            # İptal işlemi tamamlandıktan sonra hemen yeni döngüye başla (kısa bir gecikme ile)
            def restart_loop():
                if hasattr(self, 'runall_loop_running') and self.runall_loop_running:
                    print("[RUNALL] 🔄 Yeni döngü başlatılıyor (KARBOTU ile)...")
                    self.log_message("🔄 Yeni döngü başlatılıyor (KARBOTU ile)...")
                    # run_all_sequence'ı çağır (KARBOTU ile başlayacak)
                    self.run_all_sequence()
                else:
                    print("[RUNALL] ⏹️ Döngü durdurulmuş, tekrar başlatılmayacak")
                    self.log_message("⏹️ Döngü durdurulmuş, tekrar başlatılmayacak")
            
            # İptal işlemi tamamlandıktan sonra kısa bir gecikme ile yeni döngüye başla
            if hasattr(self, 'runall_loop_running') and self.runall_loop_running:
                self.after(2000, restart_loop)  # 2 saniye sonra yeni döngüye başla
            else:
                print("[RUNALL] ⏹️ Döngü durdurulmuş, tekrar başlatılmayacak")
                self.log_message("⏹️ Döngü durdurulmuş, tekrar başlatılmayacak")
            
        except Exception as e:
            print(f"[RUNALL] ❌ Restart hatası: {e}")
            self.log_message(f"❌ Restart hatası: {e}")
            import traceback
            traceback.print_exc()
            # Hata olsa bile tekrar dene (döngü hala çalışıyorsa)
            if hasattr(self, 'runall_loop_running') and self.runall_loop_running:
                self.after(2000, self.run_all_sequence)
    
    def toggle_lot_divider(self):
        """Lot bölücü modunu aç/kapat"""
        self.lot_divider_enabled = not self.lot_divider_enabled
        
        if self.lot_divider_enabled:
            self.btn_lot_divider.config(text="📦 Lot Divider: ON")
            self.btn_lot_divider.config(style='Success.TButton')
            print("✅ Lot Bölücü: AÇIK - Emirler 200er lotlar halinde bölünecek")
        else:
            self.btn_lot_divider.config(text="📦 Lot Divider: OFF")
            self.btn_lot_divider.config(style='Accent.TButton')
            print("❌ Lot Bölücü: KAPALI - Emirler normal gönderilecek")
    
    def divide_lot_size(self, total_lot):
        """
        Lot miktarını akıllıca böl - YENİ MANTIK:
        - 0-399 lot: Direkt o kadar gönder (130 lot varsa 130, 250 lot varsa 250)
        - 400+ lot: 200'ün katları + kalan (kalan 200-399 arası olmalı)
          Örnek: 500 lot = 200 + 300 (200+200+100 değil!)
          Örnek: 600 lot = 200 + 200 + 200
          Örnek: 700 lot = 200 + 200 + 300
          Örnek: 800 lot = 200 + 200 + 200 + 200
          Örnek: 900 lot = 200 + 200 + 200 + 300
        """
        try:
            if total_lot <= 0:
                return []
            
            # 0-399 lot arası: Direkt gönder
            if total_lot <= 399:
                return [total_lot]
            
            # 400+ lot: 200'ün katları + kalan (kalan 200-399 arası olmalı)
            lot_parts = []
            remaining = total_lot
            
            # 200'ün katlarını çıkar (kalan 200-399 arası kalacak şekilde)
            while remaining >= 400:
                lot_parts.append(200)
                remaining -= 200
            
            # Kalan miktarı ekle (200-399 arası veya 0)
            if remaining > 0:
                lot_parts.append(remaining)
            
            return lot_parts
            
        except Exception as e:
            print(f"❌ Lot bölme hatası: {e}")
            return [total_lot]  # Hata durumunda orijinal miktarı döndür
    
    def determine_position_change_type(self, symbol, current_qty, new_qty):
        """Pozisyon değişim türünü belirle"""
        try:
            # Mevcut pozisyon türü
            if current_qty > 0:
                current_type = "LONG"
            elif current_qty < 0:
                current_type = "SHORT"
            else:
                current_type = "FLAT"
            
            # Yeni pozisyon türü
            if new_qty > 0:
                new_type = "LONG"
            elif new_qty < 0:
                new_type = "SHORT"
            else:
                new_type = "FLAT"
            
            # Değişim miktarı
            change = new_qty - current_qty
            
            # Pozisyon değişim türünü belirle
            if current_type == "LONG" and new_qty > current_qty:
                return "LONG_ARTTIRMA", change
            elif current_type == "LONG" and new_qty < current_qty:
                return "LONG_AZALTMA", change
            elif current_type == "SHORT" and new_qty < current_qty:
                return "SHORT_ARTTIRMA", change
            elif current_type == "SHORT" and new_qty > current_qty:
                return "SHORT_AZALTMA", change
            elif current_type == "FLAT" and new_qty > 0:
                return "LONG_ARTTIRMA", change
            elif current_type == "FLAT" and new_qty < 0:
                return "SHORT_ARTTIRMA", change
            else:
                return "UNKNOWN", change
                
        except Exception as e:
            self.log_message(f"❌ Pozisyon türü belirleme hatası ({symbol}): {e}")
            return "ERROR", 0
    
    def check_maxalw_limit(self, symbol, change_type, change_amount):
        """MAXALW limitini kontrol et (1/4 kuralı)"""
        try:
            # MAXALW değerini al
            maxalw = self.get_maxalw_for_symbol(symbol)
            if maxalw <= 0:
                return True, "MAXALW değeri bulunamadı"
            
            # Maksimum değişim limiti (MAXALW/4)
            max_change_limit = maxalw / 4
            
            # Mutlak değişim miktarını kontrol et
            abs_change = abs(change_amount)
            
            if abs_change > max_change_limit:
                return False, f"MAXALW limiti aşıldı: {abs_change:.0f} > {max_change_limit:.0f}"
            else:
                return True, f"MAXALW limiti OK: {abs_change:.0f} <= {max_change_limit:.0f}"
                
        except Exception as e:
            self.log_message(f"❌ MAXALW kontrol hatası ({symbol}): {e}")
            return False, f"Hata: {e}"
    
    def check_three_hour_limit(self, symbol, change_amount):
        """3 saatlik süre limitini kontrol et"""
        try:
            current_time = datetime.now()
            
            # Bu hisse için son trade zamanını kontrol et
            if symbol in self.psfalgo_positions:
                last_trade_time = self.psfalgo_positions[symbol].get('last_trade_time')
                
                if last_trade_time:
                    # 3 saat geçmiş mi kontrol et
                    time_diff = current_time - last_trade_time
                    if time_diff.total_seconds() < 3 * 3600:  # 3 saat = 10800 saniye
                        # 3 saat içinde, toplam değişimi kontrol et
                        three_hour_change = self.psfalgo_positions[symbol].get('three_hour_change', 0)
                        new_total_change = three_hour_change + change_amount
                        
                        # MAXALW/4 limitini kontrol et
                        maxalw = self.get_maxalw_for_symbol(symbol)
                        max_change_limit = maxalw / 4
                        
                        if abs(new_total_change) > max_change_limit:
                            return False, f"3 saatlik limit aşıldı: {abs(new_total_change):.0f} > {max_change_limit:.0f}"
                        else:
                            return True, f"3 saatlik limit OK: {abs(new_total_change):.0f} <= {max_change_limit:.0f}"
                    else:
                        # 3 saat geçmiş, sıfırla
                        self.psfalgo_positions[symbol]['three_hour_change'] = 0
                        self.psfalgo_positions[symbol]['last_trade_time'] = current_time
                        return True, "3 saatlik süre sıfırlandı"
                else:
                    # İlk trade
                    self.psfalgo_positions[symbol]['last_trade_time'] = current_time
                    return True, "İlk trade"
            else:
                return True, "Pozisyon bulunamadı"
                
        except Exception as e:
            self.log_message(f"❌ 3 saatlik limit kontrol hatası ({symbol}): {e}")
            return False, f"Hata: {e}"
    
    def setup_mode_buttons(self):
        """Mod butonlarının başlangıç görünümünü ayarla"""
        try:
            # HAMPRO modu varsayılan olarak aktif
            self.btn_hampro_mode.configure(style="Accent.TButton")
            self.btn_ibkr_gun_mode.configure(style="TButton")
            self.btn_ibkr_ped_mode.configure(style="TButton")
            
            # Mode manager callback'lerini ayarla
            self.mode_manager.on_mode_changed = self.on_mode_changed
            self.mode_manager.on_positions_changed = self.on_positions_changed
            self.mode_manager.on_orders_changed = self.on_orders_changed
            
            print("[MAIN] OK Mod butonlari ayarlandi")
        except Exception as e:
            print(f"[MAIN] ERROR Mod butonlari ayarlama hatasi: {e}")
    
    def on_mode_changed(self, mode):
        """Mod değiştiğinde çağrılır"""
        print(f"[MAIN] 🔄 Mod değişti: {mode}")
    
    def on_positions_changed(self, positions):
        """Pozisyonlar değiştiğinde çağrılır"""
        print(f"[MAIN] 📊 Pozisyonlar güncellendi: {len(positions)} pozisyon")
        # Exposure bilgisini güncelle
        self.update_exposure_display()
    
    def on_orders_changed(self, orders):
        """Emirler değiştiğinde çağrılır"""
        print(f"[MAIN] 📋 Emirler güncellendi: {len(orders)} emir")
    
    def open_exception_list(self):
        """Exception listesi penceresini açar."""
        try:
            ExceptionListWindow(self, self.exception_manager)
        except Exception as e:
            messagebox.showerror("Hata", f"Exception listesi penceresi açılamadı: {e}")
    
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
    
    def update_exposure_display(self):
        """Aktif mod için exposure bilgisini hesapla ve göster"""
        try:
            print(f"[EXPOSURE] OK Exposure guncelleniyor... Aktif mod: {self.current_mode}")
            
            if self.current_mode == "HAMPRO":
                long_exposure, short_exposure = self.calculate_hammer_exposure()
                mode_text = "H-1 Mod active"
            elif self.current_mode == "IBKR_GUN":
                long_exposure, short_exposure = self.calculate_ibkr_exposure()
                mode_text = "I-1 Mod active"
            elif self.current_mode == "IBKR_PED":
                long_exposure, short_exposure = self.calculate_ibkr_exposure()
                mode_text = "I-2 Mod active"
            else:
                long_exposure, short_exposure = 0.0, 0.0
                mode_text = "Mode unknown"
            
            # Total exposure hesapla
            total_exposure = long_exposure + short_exposure
            
            # Exposure bilgisini güncelle - Kısa format
            exposure_text = f"{mode_text} - Long: {long_exposure:,.0f} | Short: {short_exposure:,.0f} | Total: {total_exposure:,.0f}"
            self.exposure_label.configure(text=exposure_text)
            
            print(f"[EXPOSURE] OK {exposure_text}")
            
        except Exception as e:
            print(f"[EXPOSURE] ERROR Exposure hesaplama hatasi: {e}")
            import traceback
            traceback.print_exc()
            self.exposure_label.configure(text="Exposure hesaplanamadı")
    
    def calculate_hammer_exposure(self):
        """HAMMER PRO pozisyonlarından exposure hesapla"""
        try:
            if not self.hammer.connected:
                return 0.0, 0.0
            
            positions = self.hammer.get_positions_direct()  # Direct pozisyonları al
            long_exposure = 0.0
            short_exposure = 0.0
            
            print(f"[EXPOSURE] 🔍 HAMMER pozisyonları kontrol ediliyor: {len(positions)} pozisyon")
            
            for position in positions:
                symbol = position.get('symbol', '')
                quantity = float(position.get('qty', 0))  # HAMMER'da 'qty' kullanılıyor
                
                # Pozisyonlardan gelen price bilgisini kullan
                price_for_exposure = position.get('price_for_exposure')
                last_price = position.get('last_price')
                prev_close = position.get('prev_close')
                avg_cost = position.get('avg_cost', 0)
                
                print(f"[EXPOSURE] 📊 {symbol}: Qty={quantity}, AvgCost={avg_cost}, LastPrice={last_price}, PrevClose={prev_close}, PriceForExposure={price_for_exposure}")
                
                # Price bilgisini belirle - Öncelik sırası:
                # 1. Pozisyonlardan gelen price_for_exposure
                # 2. Pozisyonlardan gelen last_price
                # 3. Pozisyonlardan gelen prev_close
                # 4. Avg cost (fallback)
                
                price = None
                
                if price_for_exposure and price_for_exposure > 0:
                    price = float(price_for_exposure)
                    print(f"[EXPOSURE] 📊 {symbol}: Pozisyon price_for_exposure={price}")
                elif last_price and last_price > 0:
                    price = float(last_price)
                    print(f"[EXPOSURE] 📊 {symbol}: Pozisyon last_price={price}")
                elif prev_close and prev_close > 0:
                    price = float(prev_close)
                    print(f"[EXPOSURE] 📊 {symbol}: Pozisyon prev_close={price}")
                else:
                    # Fallback: Avg cost kullan
                    if avg_cost and avg_cost > 0:
                        price = float(avg_cost)
                        print(f"[EXPOSURE] 📊 {symbol}: Avg cost={price}")
                    else:
                        print(f"[EXPOSURE] ⚠️ {symbol}: Price bulunamadı, exposure hesaplanamadı")
                        continue
                
                if price and price > 0:
                    exposure = quantity * price
                    
                    if quantity > 0:  # Long pozisyon
                        long_exposure += exposure
                        print(f"[EXPOSURE] 📈 {symbol}: Long exposure += {exposure:.2f}")
                    elif quantity < 0:  # Short pozisyon
                        short_exposure += abs(exposure)  # Short exposure pozitif göster
                        print(f"[EXPOSURE] 📉 {symbol}: Short exposure += {abs(exposure):.2f}")
                else:
                    print(f"[EXPOSURE] ⚠️ {symbol}: Price bulunamadı, exposure hesaplanamadı")
            
            print(f"[EXPOSURE] 📊 HAMMER Toplam - Long: {long_exposure:.2f}, Short: {short_exposure:.2f}")
            return long_exposure, short_exposure
            
        except Exception as e:
            print(f"[EXPOSURE] ❌ HAMMER exposure hesaplama hatası: {e}")
            import traceback
            traceback.print_exc()
            return 0.0, 0.0
    
    def calculate_ibkr_exposure(self):
        """IBKR pozisyonlarından exposure hesapla"""
        try:
            # Önce native client'i dene (averageCost bilgisi için)
            if self.ibkr_native.is_connected():
                positions = self.ibkr_native.get_positions()
            elif self.ibkr.is_connected():
                positions = self.ibkr.get_positions()
            else:
                print("[EXPOSURE] ❌ IBKR bağlantısı yok")
                return 0.0, 0.0
            
            long_exposure = 0.0
            short_exposure = 0.0
            
            print(f"[EXPOSURE] 🔍 IBKR pozisyonları kontrol ediliyor: {len(positions)} pozisyon")
            
            for position in positions:
                symbol = position.get('symbol', '')
                quantity = float(position.get('qty', 0))  # IBKR'da da 'qty' kullanılıyor
                
                # IBKR pozisyonlarından price bilgisini al
                market_price = position.get('market_price', 0)
                avg_cost = position.get('avg_cost', 0)
                
                print(f"[EXPOSURE] 📊 {symbol}: Qty={quantity}, MarketPrice={market_price}, AvgCost={avg_cost}")
                
                # Price bilgisini belirle - Öncelik sırası:
                # 1. Market price (gerçek zamanlı fiyat)
                # 2. Avg cost (fallback)
                
                price = None
                
                if market_price and market_price > 0:
                    price = float(market_price)
                    print(f"[EXPOSURE] 📊 {symbol}: Market price={price}")
                elif avg_cost and avg_cost > 0:
                    price = float(avg_cost)
                    print(f"[EXPOSURE] 📊 {symbol}: Avg cost={price}")
                else:
                    print(f"[EXPOSURE] ⚠️ {symbol}: Price bulunamadı, exposure hesaplanamadı")
                    continue
                
                if price and price > 0:
                    exposure = quantity * price
                    
                    if quantity > 0:  # Long pozisyon
                        long_exposure += exposure
                        print(f"[EXPOSURE] 📈 {symbol}: Long exposure += {exposure:.2f}")
                    elif quantity < 0:  # Short pozisyon
                        short_exposure += abs(exposure)  # Short exposure pozitif göster
                        print(f"[EXPOSURE] 📉 {symbol}: Short exposure += {abs(exposure):.2f}")
                else:
                    print(f"[EXPOSURE] ⚠️ {symbol}: Price bulunamadı, exposure hesaplanamadı")
            
            print(f"[EXPOSURE] 📊 IBKR Toplam - Long: {long_exposure:.2f}, Short: {short_exposure:.2f}")
            return long_exposure, short_exposure
            
        except Exception as e:
            print(f"[EXPOSURE] ❌ IBKR exposure hesaplama hatası: {e}")
            import traceback
            traceback.print_exc()
            return 0.0, 0.0
    
    def get_group_from_symbol(self, symbol):
        """Symbol'ün hangi gruba ait olduğunu bul - Take Profit Panel mantığıyla"""
        try:
            # Grup dosya eşleşmesi
            group_file_map = {
                'heldff': 'ssfinekheldff.csv',
                'helddeznff': 'ssfinekhelddeznff.csv', 
                'heldkuponlu': 'ssfinekheldkuponlu.csv',
                'heldnff': 'ssfinekheldnff.csv',
                'heldflr': 'ssfinekheldflr.csv',
                'heldgarabetaltiyedi': 'ssfinekheldgarabetaltiyedi.csv',
                'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
                'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
                'heldotelremorta': 'ssfinekheldotelremorta.csv',
                'heldsolidbig': 'ssfinekheldsolidbig.csv',
                'heldtitrekhc': 'ssfinekheldtitrekhc.csv',
                'highmatur': 'ssfinekhighmatur.csv',
                'notcefilliquid': 'ssfineknotcefilliquid.csv',
                'notbesmaturlu': 'ssfineknotbesmaturlu.csv',
                'nottitrekhc': 'ssfineknottitrekhc.csv',
                'salakilliquid': 'ssfineksalakilliquid.csv',
                'shitremhc': 'ssfinekshitremhc.csv'
            }
            
            # Her grup dosyasını kontrol et
            for group, file_name in group_file_map.items():
                if os.path.exists(file_name):
                    try:
                        df = pd.read_csv(file_name)
                        group_symbols = df['PREF IBKR'].tolist()
                        
                        # Tam eşleşme kontrol et
                        if symbol in group_symbols:
                            return group
                        
                        # Esnek eşleşme kontrol et (büyük/küçük harf, boşluk vs.)
                        symbol_upper = symbol.upper().strip()
                        for group_symbol in group_symbols:
                            if group_symbol and isinstance(group_symbol, str):
                                group_symbol_upper = group_symbol.upper().strip()
                                if symbol_upper == group_symbol_upper:
                                    return group
                    except Exception as e:
                        continue
            
            return "N/A"
            
        except Exception as e:
            # Debug mesajı kapatıldı - performans için
            # print(f"[GORT] ❌ {symbol} grup bulma hatası: {e}")
            return "N/A"
    
    def get_cgrup_from_symbol(self, symbol):
        """Symbol'ün CGRUP değerini bul (kuponlu gruplar için)"""
        try:
            if self.df.empty:
                return None
            
            row = self.df[self.df['PREF IBKR'] == symbol]
            if not row.empty and 'CGRUP' in self.df.columns:
                cgrup = row['CGRUP'].iloc[0]
                if pd.notna(cgrup) and cgrup != '' and cgrup != 'N/A':
                    return str(cgrup).strip()
            
            return None
            
        except Exception as e:
            # Debug mesajı kapatıldı - performans için
            # print(f"[GORT] ❌ {symbol} CGRUP bulma hatası: {e}")
            return None
    
    def calculate_group_avg_sma63chg(self, symbol, group, cgrup=None):
        """Grup ortalama SMA 63 CHG hesapla"""
        try:
            # Kuponlu gruplar için CGRUP'a göre gruplama
            kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
            
            if group.lower() in kuponlu_groups and cgrup:
                # CGRUP'a göre gruplama
                if self.df.empty:
                    return 0.01
                
                # Aynı CGRUP'a sahip hisseleri bul
                cgrup_rows = self.df[(self.df['CGRUP'] == cgrup) & (self.df['PREF IBKR'] != symbol)]
                
                # SMA 63 CHG için farklı kolon isimlerini dene
                sma63_col_names = ['SMA63 chg', 'SMA63CHG', 'SMA63_CHG', 'SMA 63 CHG']
                for col_name in sma63_col_names:
                    if col_name in self.df.columns:
                        sma63_values = cgrup_rows[col_name].dropna()
                        sma63_values = pd.to_numeric(sma63_values, errors='coerce').dropna()
                        if not sma63_values.empty:
                            avg = sma63_values.mean()
                            # Sadece ilk birkaç için log
                            if not hasattr(self, '_gort_group_avg_log_count'):
                                self._gort_group_avg_log_count = 0
                            if self._gort_group_avg_log_count < 3:
                                # Debug mesajı kapatıldı - performans için
                                # print(f"[GORT] 📊 {symbol} ({group}, CGRUP={cgrup}): SMA63 grup ortalaması = {avg:.2f} ({len(sma63_values)} hisse)")
                                self._gort_group_avg_log_count += 1
                            return avg if avg != 0 else 0.01
                
                return 0.01
            
            # Normal gruplar için grup dosyasından
            group_file_map = {
                'heldff': 'ssfinekheldff.csv',
                'helddeznff': 'ssfinekhelddeznff.csv', 
                'heldkuponlu': 'ssfinekheldkuponlu.csv',
                'heldnff': 'ssfinekheldnff.csv',
                'heldflr': 'ssfinekheldflr.csv',
                'heldgarabetaltiyedi': 'ssfinekheldgarabetaltiyedi.csv',
                'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
                'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
                'heldotelremorta': 'ssfinekheldotelremorta.csv',
                'heldsolidbig': 'ssfinekheldsolidbig.csv',
                'heldtitrekhc': 'ssfinekheldtitrekhc.csv',
                'highmatur': 'ssfinekhighmatur.csv',
                'notcefilliquid': 'ssfineknotcefilliquid.csv',
                'notbesmaturlu': 'ssfineknotbesmaturlu.csv',
                'nottitrekhc': 'ssfineknottitrekhc.csv',
                'salakilliquid': 'ssfineksalakilliquid.csv',
                'shitremhc': 'ssfinekshitremhc.csv'
            }
            
            file_name = group_file_map.get(group.lower())
            if not file_name or not os.path.exists(file_name):
                return 0.01
            
            # Grup dosyasından hisseleri al
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            # Parent DataFrame'den bu gruba ait hisselerin SMA 63 CHG değerlerini al
            if not self.df.empty:
                group_rows = self.df[self.df['PREF IBKR'].isin(group_symbols)]
                
                # SMA 63 CHG için farklı kolon isimlerini dene
                sma63_col_names = ['SMA63 chg', 'SMA63CHG', 'SMA63_CHG', 'SMA 63 CHG']
                for col_name in sma63_col_names:
                    if col_name in self.df.columns:
                        sma63_values = group_rows[col_name].dropna()
                        sma63_values = pd.to_numeric(sma63_values, errors='coerce').dropna()
                        if not sma63_values.empty:
                            avg = sma63_values.mean()
                            # Sadece ilk birkaç için log
                            if not hasattr(self, '_gort_group_avg_log_count'):
                                self._gort_group_avg_log_count = 0
                            if self._gort_group_avg_log_count < 3:
                                # Debug mesajı kapatıldı - performans için
                                # print(f"[GORT] 📊 {symbol} ({group}): SMA63 grup ortalaması = {avg:.2f} ({len(sma63_values)} hisse)")
                                self._gort_group_avg_log_count += 1
                            return avg if avg != 0 else 0.01
            
            return 0.01
            
        except Exception as e:
            # Debug mesajı kapatıldı - performans için
            # print(f"[GORT] ❌ {symbol} grup ortalama SMA 63 CHG hesaplama hatası: {e}")
            return 0.01
    
    def calculate_group_avg_sma246chg(self, symbol, group, cgrup=None):
        """Grup ortalama SMA 246 CHG hesapla"""
        try:
            # Kuponlu gruplar için CGRUP'a göre gruplama
            kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
            
            if group.lower() in kuponlu_groups and cgrup:
                # CGRUP'a göre gruplama
                if self.df.empty:
                    return 0.01
                
                # Aynı CGRUP'a sahip hisseleri bul
                cgrup_rows = self.df[(self.df['CGRUP'] == cgrup) & (self.df['PREF IBKR'] != symbol)]
                
                # SMA 246 CHG için farklı kolon isimlerini dene - "SMA246 chg" formatını öncelikli yap
                sma246_col_names = ['SMA246 chg', 'SMA 246 CHG', 'SMA246CHG', 'SMA246_CHG', 'SMA 246 chg']
                for col_name in sma246_col_names:
                    if col_name in self.df.columns:
                        sma246_values = cgrup_rows[col_name].dropna()
                        sma246_values = pd.to_numeric(sma246_values, errors='coerce').dropna()
                        if not sma246_values.empty:
                            avg = sma246_values.mean()
                            # Sadece ilk birkaç için log
                            if not hasattr(self, '_gort_group_avg_log_count'):
                                self._gort_group_avg_log_count = 0
                            if self._gort_group_avg_log_count < 3:
                                # Debug mesajı kapatıldı - performans için
                                # print(f"[GORT] 📊 {symbol} ({group}, CGRUP={cgrup}): SMA246 grup ortalaması = {avg:.2f} ({len(sma246_values)} hisse)")
                                self._gort_group_avg_log_count += 1
                            return avg if avg != 0 else 0.01
                
                return 0.01
            
            # Normal gruplar için grup dosyasından
            group_file_map = {
                'heldff': 'ssfinekheldff.csv',
                'helddeznff': 'ssfinekhelddeznff.csv', 
                'heldkuponlu': 'ssfinekheldkuponlu.csv',
                'heldnff': 'ssfinekheldnff.csv',
                'heldflr': 'ssfinekheldflr.csv',
                'heldgarabetaltiyedi': 'ssfinekheldgarabetaltiyedi.csv',
                'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
                'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
                'heldotelremorta': 'ssfinekheldotelremorta.csv',
                'heldsolidbig': 'ssfinekheldsolidbig.csv',
                'heldtitrekhc': 'ssfinekheldtitrekhc.csv',
                'highmatur': 'ssfinekhighmatur.csv',
                'notcefilliquid': 'ssfineknotcefilliquid.csv',
                'notbesmaturlu': 'ssfineknotbesmaturlu.csv',
                'nottitrekhc': 'ssfineknottitrekhc.csv',
                'salakilliquid': 'ssfineksalakilliquid.csv',
                'shitremhc': 'ssfinekshitremhc.csv'
            }
            
            file_name = group_file_map.get(group.lower())
            if not file_name or not os.path.exists(file_name):
                return 0.01
            
            # Grup dosyasından hisseleri al
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            # Parent DataFrame'den bu gruba ait hisselerin SMA 246 CHG değerlerini al
            if not self.df.empty:
                group_rows = self.df[self.df['PREF IBKR'].isin(group_symbols)]
                
                # SMA 246 CHG için farklı kolon isimlerini dene - "SMA246 chg" formatını öncelikli yap
                sma246_col_names = ['SMA246 chg', 'SMA 246 CHG', 'SMA246CHG', 'SMA246_CHG', 'SMA 246 chg']
                for col_name in sma246_col_names:
                    if col_name in self.df.columns:
                        sma246_values = group_rows[col_name].dropna()
                        sma246_values = pd.to_numeric(sma246_values, errors='coerce').dropna()
                        if not sma246_values.empty:
                            avg = sma246_values.mean()
                            # Sadece ilk birkaç için log
                            if not hasattr(self, '_gort_group_avg_log_count'):
                                self._gort_group_avg_log_count = 0
                            if self._gort_group_avg_log_count < 3:
                                # Debug mesajı kapatıldı - performans için
                                # print(f"[GORT] 📊 {symbol} ({group}): SMA246 grup ortalaması = {avg:.2f} ({len(sma246_values)} hisse)")
                                self._gort_group_avg_log_count += 1
                            return avg if avg != 0 else 0.01
            
            return 0.01
            
        except Exception as e:
            # Debug mesajı kapatıldı - performans için
            # print(f"[GORT] ❌ {symbol} grup ortalama SMA 246 CHG hesaplama hatası: {e}")
            return 0.01
    
    def calculate_gort_from_group_file(self, symbol):
        """GORT değerini grup dosyasından direkt çek - Grup pencerelerindeki mantıkla aynı (CACHE'LENMİŞ)"""
        try:
            import time
            current_time = time.time()
            
            # Cache kontrolü - GORT değeri cache'de var mı?
            if hasattr(self, 'gort_cache') and symbol in self.gort_cache:
                # Cache süresi dolmuş mu kontrol et
                if hasattr(self, 'gort_cache_time') and (current_time - self.gort_cache_time) < self.gort_cache_interval:
                    return self.gort_cache[symbol]
            
            # Grup bilgisini al
            group = self.get_group_from_symbol(symbol)
            if group == "N/A":
                return 0.0
            
            # Grup dosya eşleşmesi
            group_file_map = {
                'heldff': 'ssfinekheldff.csv',
                'helddeznff': 'ssfinekhelddeznff.csv', 
                'heldkuponlu': 'ssfinekheldkuponlu.csv',
                'heldnff': 'ssfinekheldnff.csv',
                'heldflr': 'ssfinekheldflr.csv',
                'heldgarabetaltiyedi': 'ssfinekheldgarabetaltiyedi.csv',
                'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
                'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
                'heldotelremorta': 'ssfinekheldotelremorta.csv',
                'heldsolidbig': 'ssfinekheldsolidbig.csv',
                'heldtitrekhc': 'ssfinekheldtitrekhc.csv',
                'highmatur': 'ssfinekhighmatur.csv',
                'notcefilliquid': 'ssfineknotcefilliquid.csv',
                'notbesmaturlu': 'ssfineknotbesmaturlu.csv',
                'nottitrekhc': 'ssfineknottitrekhc.csv',
                'salakilliquid': 'ssfineksalakilliquid.csv',
                'shitremhc': 'ssfinekshitremhc.csv'
            }
            
            file_name = group_file_map.get(group.lower())
            if not file_name or not os.path.exists(file_name):
                return 0.0
            
            # Grup dosyasını cache'den al veya oku
            if hasattr(self, 'group_file_cache') and group.lower() in self.group_file_cache:
                group_df = self.group_file_cache[group.lower()]
            else:
                # Cache'de yok, oku ve cache'le
                group_df = pd.read_csv(file_name)
                if not hasattr(self, 'group_file_cache'):
                    self.group_file_cache = {}
                self.group_file_cache[group.lower()] = group_df
            
            # Symbol'ü bul
            symbol_row = group_df[group_df['PREF IBKR'] == symbol]
            if symbol_row.empty:
                return 0.0
            
            # SMA 63 CHG ve SMA 246 CHG değerlerini al
            sma63chg = None
            sma246chg = None
            
            # SMA 63 CHG için farklı isimleri dene
            sma63_col_names = ['SMA63 chg', 'SMA63CHG', 'SMA63_chg', 'SMA 63 CHG']
            for col_name in sma63_col_names:
                if col_name in group_df.columns:
                    sma63chg_val = symbol_row[col_name].iloc[0]
                    if pd.notna(sma63chg_val):
                        sma63chg = pd.to_numeric(sma63chg_val, errors='coerce')
                        if not pd.isna(sma63chg):
                            break
            
            # SMA 246 CHG için farklı isimleri dene - "SMA246 chg" formatını öncelikli yap
            sma246_col_names = ['SMA246 chg', 'SMA 246 CHG', 'SMA246CHG', 'SMA246_CHG', 'SMA 246 chg']
            for col_name in sma246_col_names:
                if col_name in group_df.columns:
                    sma246chg_val = symbol_row[col_name].iloc[0]
                    if pd.notna(sma246chg_val):
                        sma246chg = pd.to_numeric(sma246chg_val, errors='coerce')
                        if not pd.isna(sma246chg):
                            break
            
            if sma63chg is None or sma246chg is None:
                return 0.0
            
            # CGRUP bilgisini al (kuponlu gruplar için)
            cgrup = None
            if 'CGRUP' in group_df.columns:
                cgrup_val = symbol_row['CGRUP'].iloc[0]
                if pd.notna(cgrup_val) and cgrup_val != '' and cgrup_val != 'N/A':
                    cgrup = str(cgrup_val).strip()
            
            # Grup ortalamalarını hesapla - Cache'den al veya hesapla
            kuponlu_groups = ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']
            
            # Cache key oluştur
            cache_key_sma63 = (group.lower(), cgrup if (group.lower() in kuponlu_groups and cgrup) else None, 'sma63')
            cache_key_sma246 = (group.lower(), cgrup if (group.lower() in kuponlu_groups and cgrup) else None, 'sma246')
            
            # SMA 63 CHG ortalama - Cache'den al
            if hasattr(self, 'group_avg_cache') and cache_key_sma63 in self.group_avg_cache:
                group_avg_sma63 = self.group_avg_cache[cache_key_sma63]
            else:
                # Cache'de yok, hesapla
                if group.lower() in kuponlu_groups and cgrup:
                    # CGRUP'a göre gruplama
                    cgrup_rows = group_df[(group_df['CGRUP'] == cgrup) & (group_df['PREF IBKR'] != symbol)]
                    
                    # SMA 63 CHG ortalama
                    for col_name in sma63_col_names:
                        if col_name in group_df.columns:
                            sma63_values = cgrup_rows[col_name].dropna()
                            sma63_values = pd.to_numeric(sma63_values, errors='coerce').dropna()
                            if not sma63_values.empty:
                                group_avg_sma63 = sma63_values.mean()
                                if group_avg_sma63 == 0:
                                    group_avg_sma63 = 0.01
                                break
                    else:
                        group_avg_sma63 = 0.01
                else:
                    # Normal gruplar için - Grup dosyasındaki tüm hisselerin ortalaması
                    for col_name in sma63_col_names:
                        if col_name in group_df.columns:
                            sma63_values = group_df[col_name].dropna()
                            sma63_values = pd.to_numeric(sma63_values, errors='coerce').dropna()
                            if not sma63_values.empty:
                                group_avg_sma63 = sma63_values.mean()
                                if group_avg_sma63 == 0:
                                    group_avg_sma63 = 0.01
                                break
                    else:
                        group_avg_sma63 = 0.01
                
                # Cache'le
                if not hasattr(self, 'group_avg_cache'):
                    self.group_avg_cache = {}
                self.group_avg_cache[cache_key_sma63] = group_avg_sma63
            
            # SMA 246 CHG ortalama - Cache'den al
            if hasattr(self, 'group_avg_cache') and cache_key_sma246 in self.group_avg_cache:
                group_avg_sma246 = self.group_avg_cache[cache_key_sma246]
            else:
                # Cache'de yok, hesapla
                if group.lower() in kuponlu_groups and cgrup:
                    # CGRUP'a göre gruplama
                    cgrup_rows = group_df[(group_df['CGRUP'] == cgrup) & (group_df['PREF IBKR'] != symbol)]
                    
                    # SMA 246 CHG ortalama
                    for col_name in sma246_col_names:
                        if col_name in group_df.columns:
                            sma246_values = cgrup_rows[col_name].dropna()
                            sma246_values = pd.to_numeric(sma246_values, errors='coerce').dropna()
                            if not sma246_values.empty:
                                group_avg_sma246 = sma246_values.mean()
                                if group_avg_sma246 == 0:
                                    group_avg_sma246 = 0.01
                                break
                    else:
                        group_avg_sma246 = 0.01
                else:
                    # Normal gruplar için - Grup dosyasındaki tüm hisselerin ortalaması
                    for col_name in sma246_col_names:
                        if col_name in group_df.columns:
                            sma246_values = group_df[col_name].dropna()
                            sma246_values = pd.to_numeric(sma246_values, errors='coerce').dropna()
                            if not sma246_values.empty:
                                group_avg_sma246 = sma246_values.mean()
                                if group_avg_sma246 == 0:
                                    group_avg_sma246 = 0.01
                                break
                    else:
                        group_avg_sma246 = 0.01
                
                # Cache'le
                if not hasattr(self, 'group_avg_cache'):
                    self.group_avg_cache = {}
                self.group_avg_cache[cache_key_sma246] = group_avg_sma246
            
            # GORT hesapla (SMA63: %25, SMA246: %75 ağırlık)
            gort = (0.25 * (sma63chg - group_avg_sma63)) + (0.75 * (sma246chg - group_avg_sma246))
            
            # GORT'u cache'le
            if not hasattr(self, 'gort_cache'):
                self.gort_cache = {}
            if not hasattr(self, 'gort_cache_time'):
                self.gort_cache_time = current_time
            self.gort_cache[symbol] = gort
            self.gort_cache_time = current_time  # Cache zamanını güncelle
            
            return gort
            
        except Exception as e:
            # Debug mesajı kapatıldı - performans için
            # print(f"[GORT] ❌ {symbol} grup dosyasından GORT hesaplama hatası: {e}")
            return 0.0
    
    def calculate_gort(self, symbol):
        """GORT değerini hesapla - Önce grup dosyasından çek, yoksa normal hesapla"""
        try:
            # Önce grup dosyasından çek (grup pencerelerindeki mantıkla aynı)
            gort = self.calculate_gort_from_group_file(symbol)
            if gort != 0.0:
                return gort
            
            # Fallback: Normal hesaplama (eski mantık)
            if self.df.empty:
                return 0.0
            
            # Symbol'ün satırını bul
            row = self.df[self.df['PREF IBKR'] == symbol]
            if row.empty:
                return 0.0
            
            # SMA 63 CHG ve SMA 246 CHG değerlerini al
            sma63chg = None
            sma246chg = None
            
            # SMA 63 CHG için farklı isimleri dene
            sma63_col_names = ['SMA63 chg', 'SMA63CHG', 'SMA63_chg', 'SMA 63 CHG']
            for col_name in sma63_col_names:
                if col_name in self.df.columns:
                    sma63chg_val = row[col_name].iloc[0]
                    if pd.notna(sma63chg_val):
                        sma63chg = pd.to_numeric(sma63chg_val, errors='coerce')
                        if not pd.isna(sma63chg):
                            break
            
            # SMA 246 CHG için farklı isimleri dene
            sma246_col_names = ['SMA246 chg', 'SMA 246 CHG', 'SMA246CHG', 'SMA246_CHG', 'SMA 246 chg']
            for col_name in sma246_col_names:
                if col_name in self.df.columns:
                    sma246chg_val = row[col_name].iloc[0]
                    if pd.notna(sma246chg_val):
                        sma246chg = pd.to_numeric(sma246chg_val, errors='coerce')
                        if not pd.isna(sma246chg):
                            break
            
            if sma63chg is None or sma246chg is None:
                return 0.0
            
            # Grup bilgisini al
            group = self.get_group_from_symbol(symbol)
            cgrup = self.get_cgrup_from_symbol(symbol)
            
            if group == "N/A":
                return 0.0
            
            # Grup ortalamalarını hesapla
            group_avg_sma63 = self.calculate_group_avg_sma63chg(symbol, group, cgrup)
            group_avg_sma246 = self.calculate_group_avg_sma246chg(symbol, group, cgrup)
            
            # GORT hesapla (SMA63: %25, SMA246: %75 ağırlık)
            gort = (0.25 * (sma63chg - group_avg_sma63)) + (0.75 * (sma246chg - group_avg_sma246))
            
            return gort
            
        except Exception as e:
            # Debug mesajı kapatıldı - performans için
            # print(f"[GORT] ❌ {symbol} GORT hesaplama hatası: {e}")
            return 0.0
    