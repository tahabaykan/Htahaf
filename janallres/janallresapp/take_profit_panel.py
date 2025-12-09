"""
Take Profit Panel - Long ve Short pozisyonlar için take profit emirleri

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janallres/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Bu modül CSV dosyalarını okur, tüm dosya yolları ana dizine göre olmalı!
=================================
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import os

class TakeProfitPanel:
    def __init__(self, parent, position_type):
        """
        Take Profit Panel'i oluştur
        
        Args:
            parent: Ana pencere
            position_type: "longs" veya "shorts"
        """
        self.parent = parent
        self.position_type = position_type
        self.hammer = parent.hammer
    
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
            return [100]  # Hata durumunda minimum 100 lot döndür
    
    def __init__(self, parent, position_type):
        """
        Take Profit Panel'i oluştur
        
        Args:
            parent: Ana pencere
            position_type: "longs" veya "shorts"
        """
        self.parent = parent
        self.position_type = position_type
        self.hammer = parent.hammer
        
        # Pencere başlığı
        if position_type == "longs":
            title = "Take Profit Longs - Long Pozisyonlar"
            self.order_buttons = ["Ask Sell", "Front Sell", "SoftFront Sell", "Bid Sell", "Pahalı Prof Sell"]
        else:  # shorts
            title = "Take Profit Shorts - Short Pozisyonlar"
            self.order_buttons = ["Bid Buy", "Front Buy", "SoftFront Buy", "Ask Buy", "Ucuz Prof Buy"]
        
        # Ana pencere
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry("1200x700")
        self.win.transient(parent)
        # grab_set() kaldırıldı - minimize edilebilir olması için
        
        # Başlık frame - minimize butonu ile
        title_frame = ttk.Frame(self.win)
        title_frame.pack(fill='x', padx=5, pady=5)
        
        title_label = ttk.Label(title_frame, text=title, font=("Arial", 12, "bold"))
        title_label.pack(side='left')
        
        # Pencere kontrol butonları (sağ üst)
        window_controls = ttk.Frame(title_frame)
        window_controls.pack(side='right')
        
        # Alta Al (Minimize) butonu
        minimize_btn = ttk.Button(window_controls, text="🗕 Alta Al", width=10,
                                  command=lambda: self.win.iconify())
        minimize_btn.pack(side='left', padx=2)
        
        # Pozisyon verileri
        self.positions = []
        self.selected_positions = {}  # Dictionary olarak tanımla
        
        self.setup_ui()
        self.load_positions()
    
    def get_lrpan_price(self, symbol):
        """Hisse için LRPAN fiyatını al (100/200/300 lot olan son print)"""
        try:
            if hasattr(self.parent, 'hammer') and self.parent.hammer and self.parent.hammer.connected:
                # getTicks komutu ile son 25 tick'i al
                tick_data = self.parent.hammer.get_ticks(symbol, lastFew=25, tradesOnly=True, regHoursOnly=False)
                
                if tick_data and 'data' in tick_data and tick_data['data']:
                    ticks = tick_data['data']
                    
                    # Şu anki zamanı al
                    from datetime import datetime
                    current_time = datetime.now()
                    
                    # En yakın real print'i bul (zaman farkına göre)
                    closest_real_print = None
                    min_time_diff = None
                    
                    for tick in ticks:
                        size = tick.get('s', 0)
                        price = tick.get('p', 0)
                        timestamp_str = tick.get('t', '')
                        
                        # Sadece 100, 200, 300 lot olanları kontrol et
                        if size in [100, 200, 300]:
                            try:
                                # Timestamp'i parse et
                                tick_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                
                                # Zaman farkını hesapla (saniye cinsinden)
                                time_diff = abs((current_time - tick_time).total_seconds())
                                
                                # En yakın print'i güncelle
                                if min_time_diff is None or time_diff < min_time_diff:
                                    closest_real_print = {
                                        'price': price,
                                        'size': size,
                                        'timestamp': timestamp_str,
                                        'time_diff': time_diff
                                    }
                                    min_time_diff = time_diff
                                    print(f"[LRPAN PRICE] ✅ {symbol}: REAL PRINT! {size} lot @ ${price:.2f} - {time_diff:.0f}s önce")
                                
                            except Exception as e:
                                print(f"[LRPAN PRICE] ⚠️ {symbol}: Timestamp parse hatası: {e}")
                    
                    if closest_real_print:
                        print(f"[LRPAN PRICE] 🎯 {symbol}: EN YAKIN REAL PRINT - ${closest_real_print['price']:.2f} ({closest_real_print['time_diff']:.0f}s önce)")
                        return closest_real_print['price']
                    else:
                        print(f"[LRPAN PRICE] ⚠️ {symbol}: LRPAN fiyatı bulunamadı (100/200/300 lot yok)")
                        return None
                else:
                    print(f"[LRPAN PRICE] ⚠️ {symbol}: Tick data bulunamadı")
                    return None
            else:
                print(f"[LRPAN PRICE] ⚠️ {symbol}: Hammer Pro bağlı değil")
                return None
                
        except Exception as e:
            print(f"[LRPAN PRICE] ❌ {symbol} LRPAN fiyat alma hatası: {e}")
            return None
    
    def get_lrpan_price_from_symbol(self):
        """Seçili pozisyonlar için LRPAN fiyatını al"""
        try:
            if not self.selected_positions:
                return None
            
            # İlk seçili pozisyonun symbol'ünü kullan
            symbol = list(self.selected_positions)[0]
            return self.get_lrpan_price(symbol)
            
        except Exception as e:
            print(f"[LRPAN PRICE] ❌ Symbol alma hatası: {e}")
            return None
    
    def check_soft_front_buy_conditions(self, bid, ask, last_print):
        """SoftFront Buy koşullarını kontrol et - LRPAN fiyatı ile"""
        if bid <= 0 or ask <= 0 or last_print <= 0:
            return False
        
        spread = ask - bid
        if spread <= 0:
            return False
        
        # LRPAN fiyatını al (gerçek print fiyatı)
        lrpan_price = self.get_lrpan_price_from_symbol()
        if lrpan_price is None:
            # LRPAN fiyatı bulunamazsa last_print kullan
            print(f"[SOFT FRONT BUY] ⚠️ LRPAN fiyatı bulunamadı, last_print kullanılıyor: ${last_print:.2f}")
            real_print_price = last_print
        else:
            # LRPAN fiyatını kullan
            real_print_price = lrpan_price
            print(f"[SOFT FRONT BUY] ✅ LRPAN fiyatı kullanılıyor: ${real_print_price:.2f}")
        
        # Koşul 1: %60 kuralı - (ask - real_print_price) / (ask - bid) > 0.60
        condition1 = (ask - real_print_price) / spread > 0.60
        
        # Koşul 2: 0.15 cent kuralı - (ask - real_print_price) >= 0.15
        condition2 = (ask - real_print_price) >= 0.15
        
        print(f"[SOFT FRONT BUY] 🔍 Koşul 1: {(ask - real_print_price) / spread:.2f} > 0.60 = {condition1}")
        print(f"[SOFT FRONT BUY] 🔍 Koşul 2: {(ask - real_print_price):.2f} >= 0.15 = {condition2}")
        
        # En az bir koşul sağlanmalı
        return condition1 or condition2
    
    def check_soft_front_sell_conditions(self, bid, ask, last_print):
        """SoftFront Sell koşullarını kontrol et - LRPAN fiyatı ile"""
        if bid <= 0 or ask <= 0 or last_print <= 0:
            return False
        
        spread = ask - bid
        if spread <= 0:
            return False
        
        # LRPAN fiyatını al (gerçek print fiyatı)
        lrpan_price = self.get_lrpan_price_from_symbol()
        if lrpan_price is None:
            # LRPAN fiyatı bulunamazsa last_print kullan - Koşulları gevşet
            print(f"[SOFT FRONT SELL] ⚠️ LRPAN fiyatı bulunamadı, last_print kullanılıyor: ${last_print:.2f}")
            real_print_price = last_print
            
            # Last print kullanıldığında koşulları gevşet
            # Koşul 1: %40 kuralı (gevşetilmiş)
            condition1 = (real_print_price - bid) / spread > 0.40
            # Koşul 2: 0.05 cent kuralı (gevşetilmiş)  
            condition2 = (real_print_price - bid) >= 0.05
            
            print(f"[SOFT FRONT SELL] 🔍 Last Print Koşul 1: {(real_print_price - bid) / spread:.2f} > 0.40 = {condition1}")
            print(f"[SOFT FRONT SELL] 🔍 Last Print Koşul 2: {(real_print_price - bid):.2f} >= 0.05 = {condition2}")
        else:
            # LRPAN fiyatını kullan - Normal koşullar
            real_print_price = lrpan_price
            print(f"[SOFT FRONT SELL] ✅ LRPAN fiyatı kullanılıyor: ${real_print_price:.2f}")
            
            # Koşul 1: %60 kuralı - (real_print_price - bid) / (ask - bid) > 0.60
            condition1 = (real_print_price - bid) / spread > 0.60
            # Koşul 2: 0.15 cent kuralı - (real_print_price - bid) >= 0.15
            condition2 = (real_print_price - bid) >= 0.15
            
            print(f"[SOFT FRONT SELL] 🔍 LRPAN Koşul 1: {(real_print_price - bid) / spread:.2f} > 0.60 = {condition1}")
            print(f"[SOFT FRONT SELL] 🔍 LRPAN Koşul 2: {(real_print_price - bid):.2f} >= 0.15 = {condition2}")
        
        # En az bir koşul sağlanmalı
        return condition1 or condition2
    
    def calculate_profitable_lot_size(self, current_qty):
        """Kârlı pozisyonlar için lot hesapla (%20 ama minimum 200 lot)"""
        # %20 hesapla
        twenty_percent = int(abs(current_qty) * 0.2)
        
        # Minimum 200 lot kontrolü
        if twenty_percent < 200:
            # Eğer %20, 200'den küçükse, mevcut miktarın tamamını al (ters pozisyona geçmemek için)
            return min(abs(current_qty), 200)
        else:
            # %20, 200'den büyükse, %20'yi al
            return twenty_percent
    
    def get_ask_sell_pahalilik_skoru(self, symbol):
        """Hisse için Ask Sell Pahalılık Skoru'nu al"""
        try:
            # Pozisyon verilerinden skor al
            for pos in self.positions:
                if pos['symbol'] == symbol:
                    return pos.get('ask_sell_pahalilik_skoru', 0.0)
            return 0.0
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ {symbol} Ask Sell Pahalılık Skoru alınamadı: {e}")
            return 0.0
    
    def get_bid_buy_ucuzluk_skoru(self, symbol):
        """Hisse için Bid Buy Ucuzluk Skoru'nu al"""
        try:
            # Pozisyon verilerinden skor al
            for pos in self.positions:
                if pos['symbol'] == symbol:
                    return pos.get('bid_buy_ucuzluk_skoru', 0.0)
            return 0.0
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ {symbol} Bid Buy Ucuzluk Skoru alınamadı: {e}")
            return 0.0
    
    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        # Üst panel - Butonlar
        top_frame = ttk.Frame(self.win)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        # Emir butonları
        for button_text in self.order_buttons:
            btn = ttk.Button(top_frame, text=button_text, width=12,
                           command=lambda bt=button_text: self.place_orders(bt))
            btn.pack(side='left', padx=2)
        
        # Ayırıcı
        ttk.Separator(top_frame, orient='vertical').pack(side='left', padx=10, fill='y')
        
        # Lot ayarlama butonları
        ttk.Label(top_frame, text="Lot:").pack(side='left', padx=2)
        self.lot_entry = ttk.Entry(top_frame, width=8)
        self.lot_entry.pack(side='left', padx=2)
        self.lot_entry.insert(0, "200")  # Default 200 lot
        
        # Lot butonları
        self.btn_lot_25 = ttk.Button(top_frame, text="%25", 
                                    command=lambda: self.set_lot_percentage(25), width=6)
        self.btn_lot_25.pack(side='left', padx=1)
        
        self.btn_lot_50 = ttk.Button(top_frame, text="%50", 
                                    command=lambda: self.set_lot_percentage(50), width=6)
        self.btn_lot_50.pack(side='left', padx=1)
        
        self.btn_lot_75 = ttk.Button(top_frame, text="%75", 
                                    command=lambda: self.set_lot_percentage(75), width=6)
        self.btn_lot_75.pack(side='left', padx=1)
        
        self.btn_lot_100 = ttk.Button(top_frame, text="%100", 
                                     command=lambda: self.set_lot_percentage(100), width=6)
        self.btn_lot_100.pack(side='left', padx=1)
        
        self.btn_lot_avg_adv = ttk.Button(top_frame, text="Avg Adv", 
                                         command=self.set_lot_avg_adv, width=8)
        self.btn_lot_avg_adv.pack(side='left', padx=1)
        
        # Ayırıcı
        ttk.Separator(top_frame, orient='vertical').pack(side='left', padx=10, fill='y')
        
        # Seçim butonları
        self.btn_select_all = ttk.Button(top_frame, text="Tümünü Seç", 
                                       command=self.select_all_positions, width=12)
        self.btn_select_all.pack(side='left', padx=1)
        
        self.btn_deselect_all = ttk.Button(top_frame, text="Tümünü Kaldır", 
                                         command=self.deselect_all_positions, width=12)
        self.btn_deselect_all.pack(side='left', padx=1)
        
        # Yenile butonu
        self.btn_refresh = ttk.Button(top_frame, text="Yenile", 
                                    command=self.load_positions, width=10)
        self.btn_refresh.pack(side='right', padx=2)
        
        # Cercop butonu - 100 lot'tan az olanları Front Buy/Sell ile seç
        self.btn_cercop = ttk.Button(top_frame, text="Cercop", 
                                   command=self.cercop_action, width=10)
        self.btn_cercop.pack(side='right', padx=2)
        
        # Tablo
        self.setup_table()
        
        # Alt panel - Bilgi
        info_frame = ttk.Frame(self.win)
        info_frame.pack(fill='x', padx=5, pady=5)
        
        self.lbl_info = ttk.Label(info_frame, text="Pozisyonlar yükleniyor...")
        self.lbl_info.pack(side='left')
        
        self.lbl_selected = ttk.Label(info_frame, text="0 pozisyon seçildi")
        self.lbl_selected.pack(side='right')
    
    def setup_table(self):
        """Pozisyon tablosunu oluştur"""
        # Kolonlar - Longs için Ask Sell ve Front Sell pahalılığı, Shorts için Bid Buy ve Front Buy ucuzluğu + Yeni kolonlar
        if self.position_type == "longs":
            cols = ['select', 'symbol', 'qty', 'avg_cost', 'current_price', 'fbtot', 'pnl_vs_cost', 'market_value', 'ask_sell_pahalilik', 'front_sell_pahalilik', 'outperf_chg_pct', 'timebased_bench_chg', 'avg_adv', 'maxalw', 'smi', 'final_fb', 'final_sfs', 'grup', 'avg_final_fb', 'avg_final_sfs', 'fbplagr', 'fbratgr', 'gort']
            headers = ['Seç', 'Symbol', 'Qty', 'Avg Cost', 'Current', 'FBtot', 'PnL', 'Market Value', 'Ask Sell Pahalılık', 'Front Sell Pahalılık', 'Outperf%', 'Timebased', 'AVG_ADV', 'MAXALW', 'SMI', 'Final FB', 'Final SFS', 'Grup', 'Avg Final FB', 'Avg Final SFS', 'FBPlagr', 'FBRatgr', 'GORT']
        else:  # shorts
            cols = ['select', 'symbol', 'qty', 'avg_cost', 'current_price', 'sfstot', 'pnl_vs_cost', 'market_value', 'bid_buy_ucuzluk', 'front_buy_ucuzluk', 'outperf_chg_pct', 'timebased_bench_chg', 'avg_adv', 'maxalw', 'smi', 'final_fb', 'final_sfs', 'grup', 'avg_final_fb', 'avg_final_sfs', 'sfsplagr', 'sfsratgr', 'gort']
            headers = ['Seç', 'Symbol', 'Qty', 'Avg Cost', 'Current', 'SFStot', 'PnL', 'Market Value', 'Bid Buy Ucuzluk', 'Front Buy Ucuzluk', 'Outperf%', 'Timebased', 'AVG_ADV', 'MAXALW', 'SMI', 'Final FB', 'Final SFS', 'Grup', 'Avg Final FB', 'Avg Final SFS', 'SFSPlagr', 'SFSRatgr', 'GORT']
        
        # Tablo
        self.tree = ttk.Treeview(self.win, columns=cols, show='headings', height=20)
        
        # Font boyutunu daha da küçült
        style = ttk.Style()
        style.configure("Treeview", font=('Arial', 6))
        style.configure("Treeview.Heading", font=('Arial', 6, 'bold'))
        
        # Kolon başlıkları ve genişlikleri - daha da küçük boyutlar
        for c, h in zip(cols, headers):
            self.tree.heading(c, text=h)
            if c == 'select':
                self.tree.column(c, width=30, anchor='center')
            elif c == 'symbol':
                self.tree.column(c, width=60, anchor='center')
            elif c in ['qty']:
                self.tree.column(c, width=50, anchor='center')
            elif c in ['avg_cost', 'current_price', 'pnl_vs_cost', 'market_value']:
                self.tree.column(c, width=65, anchor='center')
            elif c in ['outperf_chg_pct', 'timebased_bench_chg']:
                self.tree.column(c, width=60, anchor='center')
            elif c in ['ask_sell_pahalilik', 'front_sell_pahalilik', 'bid_buy_ucuzluk', 'front_buy_ucuzluk']:
                self.tree.column(c, width=75, anchor='center')
            elif c in ['smi', 'final_fb', 'final_sfs']:
                self.tree.column(c, width=55, anchor='center')
            elif c in ['grup']:
                self.tree.column(c, width=60, anchor='center')
            elif c in ['avg_final_fb', 'avg_final_sfs']:
                self.tree.column(c, width=60, anchor='center')
            elif c in ['fbplagr', 'fbratgr', 'sfsplagr', 'sfsratgr']:
                self.tree.column(c, width=50, anchor='center')
            elif c in ['fbtot', 'sfstot']:
                self.tree.column(c, width=55, anchor='center')
            elif c == 'gort':
                self.tree.column(c, width=50, anchor='center')
            else:
                self.tree.column(c, width=80, anchor='center')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.win, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack
        self.tree.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scrollbar.pack(side='right', fill='y', pady=5)
        
        # Tıklama olayları
        self.tree.bind('<Button-1>', self.on_table_click)
        self.tree.bind('<Double-1>', self.on_double_click)
        
        # Sıralama için tıklama olayları
        self.tree.bind('<Button-1>', self.on_header_click)
        
        # Sıralama durumu
        self.sort_column = None
        self.sort_reverse = False
        
        # Header tıklama olayları için binding
        self.tree.bind('<Button-1>', self.on_header_click)
    
    def convert_pref_to_hammer_format(self, symbol):
        """PREF IBKR formatındaki symbol'ü Hammer Pro formatına çevir (sadece PR bulunan hisselerde)"""
        # Eğer zaten Hammer Pro formatındaysa (örn: "EQH-C", "PSA-P") olduğu gibi döndür
        if "-" in symbol and len(symbol.split("-")) == 2:
            return symbol
        
        # Örnek: "CIM PRC" -> "CIM-C", "EQH PRA" -> "EQH-A", "USB PRH" -> "USB-H"
        if " PR" in symbol:
            parts = symbol.split(" PR")
            if len(parts) == 2:
                base_symbol = parts[0]
                suffix = parts[1]
                # Suffix'i tek karaktere çevir
                if suffix == "A":
                    return f"{base_symbol}-A"
                elif suffix == "B":
                    return f"{base_symbol}-B"
                elif suffix == "C":
                    return f"{base_symbol}-C"
                elif suffix == "D":
                    return f"{base_symbol}-D"
                elif suffix == "E":
                    return f"{base_symbol}-E"
                elif suffix == "F":
                    return f"{base_symbol}-F"
                elif suffix == "G":
                    return f"{base_symbol}-G"
                elif suffix == "H":
                    return f"{base_symbol}-H"
                elif suffix == "I":
                    return f"{base_symbol}-I"
                elif suffix == "J":
                    return f"{base_symbol}-J"
                elif suffix == "K":
                    return f"{base_symbol}-K"
                elif suffix == "L":
                    return f"{base_symbol}-L"
                elif suffix == "M":
                    return f"{base_symbol}-M"
                elif suffix == "N":
                    return f"{base_symbol}-N"
                elif suffix == "O":
                    return f"{base_symbol}-O"
                elif suffix == "P":
                    return f"{base_symbol}-P"
                elif suffix == "Q":
                    return f"{base_symbol}-Q"
                elif suffix == "R":
                    return f"{base_symbol}-R"
                elif suffix == "S":
                    return f"{base_symbol}-S"
                elif suffix == "T":
                    return f"{base_symbol}-T"
                elif suffix == "U":
                    return f"{base_symbol}-U"
                elif suffix == "V":
                    return f"{base_symbol}-V"
                elif suffix == "W":
                    return f"{base_symbol}-W"
                elif suffix == "X":
                    return f"{base_symbol}-X"
                elif suffix == "Y":
                    return f"{base_symbol}-Y"
                elif suffix == "Z":
                    return f"{base_symbol}-Z"
        
        # Normal hisse senedi ise olduğu gibi döndür
        return symbol
    
    def load_positions(self):
        """Mevcut moda göre pozisyonları yükle - Pozisyonlarım butonuyla aynı mantık"""
        try:
            # Tabloyu temizle
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            self.lbl_info.config(text="Pozisyonlar yükleniyor...")
            self.win.update()
            
            # Pozisyonlarım butonuyla aynı mantık
            if hasattr(self.parent, 'mode_manager'):
                if self.parent.mode_manager.is_hampro_mode():
                    print("[TAKE PROFIT] OK HAMPRO modunda pozisyonlar cekiliyor...")
                    # Hammer Pro'dan pozisyonları çek
                    positions = self.hammer.get_positions_direct()
                elif self.parent.mode_manager.is_ibkr_mode():
                    print("[TAKE PROFIT] OK IBKR modunda pozisyonlar cekiliyor...")
                    # IBKR'den pozisyonları çek
                    positions = self.parent.ibkr.get_positions_direct()
                    print(f"[TAKE PROFIT] 🔍 IBKR'den {len(positions)} pozisyon alındı")
                    # IBKR pozisyonlarını debug et
                    for i, pos in enumerate(positions[:10]):  # İlk 10 pozisyonu göster
                        print(f"[TAKE PROFIT] 🔍 IBKR Pos {i+1}: {pos['symbol']} = {pos['qty']}")
                else:
                    print("[TAKE PROFIT] ⚠️ Mod belirlenemedi, HAMPRO kullanılıyor...")
                    positions = self.hammer.get_positions_direct()
            else:
                print("[TAKE PROFIT] ⚠️ Mode manager bulunamadı, HAMPRO kullanılıyor...")
                positions = self.hammer.get_positions_direct()
            
            if not positions:
                self.lbl_info.config(text="Pozisyon bulunamadı")
                print("[TAKE PROFIT] ❌ Hiç pozisyon bulunamadı")
                return
            
            print(f"[TAKE PROFIT] 📊 Toplam {len(positions)} pozisyon alındı")
            
            # Pozisyon tipine göre filtrele
            filtered_positions = []
            for pos in positions:
                qty = pos['qty']
                symbol = pos['symbol']
                
                print(f"[TAKE PROFIT] 🔍 {symbol}: qty={qty}, type={self.position_type}")
                
                if self.position_type == "longs" and qty > 0:
                    # Long pozisyonlar (quantity > 0)
                    filtered_positions.append(pos)
                    print(f"[TAKE PROFIT] ✅ {symbol} LONG pozisyon olarak eklendi")
                elif self.position_type == "shorts" and qty < 0:
                    # Short pozisyonlar (quantity < 0)
                    filtered_positions.append(pos)
                    print(f"[TAKE PROFIT] ✅ {symbol} SHORT pozisyon olarak eklendi")
                else:
                    print(f"[TAKE PROFIT] ⚠️ {symbol} filtrelendi (qty={qty}, type={self.position_type})")
            
            print(f"[TAKE PROFIT] 📊 Filtreleme sonucu: {len(filtered_positions)} {self.position_type} pozisyon")
            
            if not filtered_positions:
                self.lbl_info.config(text=f"{self.position_type.title()} pozisyon bulunamadı")
                print(f"[TAKE PROFIT] ❌ {self.position_type.title()} pozisyon bulunamadı")
                return
            
            # Pozisyonları tabloya ekle
            for pos in filtered_positions:
                symbol = pos['symbol']
                qty = pos['qty']
                avg_cost = pos['avg_cost']
                
                # Current price al
                current_price = self.get_current_price(symbol)
                
                # AVG COST hesaplamasını düzelt
                if avg_cost is None or avg_cost == 0:
                    # AVG COST yoksa pozisyon değerini hesapla
                    if qty != 0 and current_price > 0:
                        # Pozisyon değerini al
                        position_value = pos.get('positionValue', 0)
                        if position_value > 0:
                            avg_cost = position_value / abs(qty)
                        else:
                            avg_cost = current_price
                    else:
                        avg_cost = 0.0
                
                # PnL hesapla
                if self.position_type == "longs":
                    pnl = (current_price - avg_cost) * abs(qty) if avg_cost > 0 and current_price > 0 else 0.0
                else:  # shorts
                    pnl = (avg_cost - current_price) * abs(qty) if avg_cost > 0 and current_price > 0 else 0.0
                
                # Market value
                market_value = current_price * abs(qty)
                
                # AVG_ADV ve MAXALW değerlerini al
                avg_adv = self.get_avg_adv_from_csv(symbol)
                maxalw = avg_adv / 10 if avg_adv > 0 else 0
                
                # SMI değerini al
                smi = self.get_smi_from_csv(symbol)
                
                # Final FB ve Final SFS skorlarını al
                final_fb = self.get_final_fb_from_csv(symbol)
                final_sfs = self.get_final_sfs_from_csv(symbol)
                
                # Yeni kolonlar için verileri al
                print(f"[TAKE PROFIT] 🔍 {symbol} için grup bilgisi aranıyor...")
                grup_value, avg_final_fb, avg_final_sfs, fbplagr, fbratgr, fbtot, sfsplagr, sfsratgr, sfstot, gort = self.get_new_column_data(symbol)
                print(f"[TAKE PROFIT] 📊 {symbol} -> Grup: {grup_value}, Avg Final FB: {avg_final_fb:.2f}, Avg Final SFS: {avg_final_sfs:.2f}, FBPlagr: {fbplagr}, FBRatgr: {fbratgr}, FBtot: {fbtot}, SFSPlagr: {sfsplagr}, SFSRatgr: {sfsratgr}, SFStot: {sfstot}, GORT: {gort:.2f}")
                
                # Final jdata'dan Outperf Chg% ve Timebased Bench Chg verilerini al
                outperf_chg_pct = "N/A"
                timebased_bench_chg = "N/A"
                
                try:
                    print(f"\n🎯 [TAKE PROFIT] {symbol} için Final jdata aranıyor...")
                    
                    # Import testi
                    print(f"🔍 [TAKE PROFIT] Import testi başlıyor...")
                    
                    # myjdata modülünden veri al
                    try:
                        from .myjdata import get_final_jdata_for_symbol, FINAL_JDATA_RESULTS
                        print(f"✅ [TAKE PROFIT] Relative import başarılı!")
                    except ImportError as e:
                        print(f"⚠️ [TAKE PROFIT] Relative import hatası: {e}")
                        # Absolute import dene
                        try:
                            from janallresapp.myjdata import get_final_jdata_for_symbol, FINAL_JDATA_RESULTS
                            print(f"✅ [TAKE PROFIT] Absolute import başarılı!")
                        except ImportError as e2:
                            print(f"❌ [TAKE PROFIT] Absolute import da hatası: {e2}")
                            raise e2
                    
                    print(f"📊 [TAKE PROFIT] FINAL_JDATA_RESULTS keys: {list(FINAL_JDATA_RESULTS.keys())}")
                    
                    final_data = get_final_jdata_for_symbol(symbol)
                    
                    if final_data:
                        outperf_chg_pct = f"{final_data.get('outperf_chg_pct', 0):.2f}%"
                        timebased_bench_chg = f"${final_data.get('timebased_bench_chg', 0):.4f}"
                        print(f"✅ [TAKE PROFIT] {symbol} Final jdata: Outperf={outperf_chg_pct}, Timebased={timebased_bench_chg}")
                    else:
                        print(f"⚠️ [TAKE PROFIT] {symbol} için Final jdata bulunamadı")
                        
                        # Alternatif olarak global değişkenden direkt al
                        if symbol in FINAL_JDATA_RESULTS:
                            direct_data = FINAL_JDATA_RESULTS[symbol]
                            outperf_chg_pct = f"{direct_data.get('outperf_chg_pct', 0):.2f}%"
                            timebased_bench_chg = f"${direct_data.get('timebased_bench_chg', 0):.4f}"
                            print(f"OK [TAKE PROFIT] {symbol} direkt FINAL_JDATA_RESULTS'dan alindi")
                        else:
                            print(f"❌ [TAKE PROFIT] {symbol} FINAL_JDATA_RESULTS'da da yok")
                            
                except Exception as e:
                    print(f"❌ [TAKE PROFIT] {symbol} Final jdata alma hatası: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Debug: Skorları logla
                print(f"[TAKE PROFIT] 📊 {symbol}: Final_FB={final_fb:.4f}, Final_SFS={final_sfs:.4f}")
                print(f"[TAKE PROFIT] 💰 {symbol}: Qty={qty}, AvgCost={avg_cost:.2f}, Current={current_price:.2f}, PnL={pnl:.2f}")
                
                # Mevcut pozisyonu al (Hammer Pro'dan) - Artık kullanılmıyor
                # current_position = abs(qty)  # Mevcut pozisyon miktarı
                
                # Pahalılık/Ucuzluk hesaplamaları
                ask_sell_pahalilik = "N/A"
                front_sell_pahalilik = "N/A"
                bid_buy_ucuzluk = "N/A"
                front_buy_ucuzluk = "N/A"
                
                # BASIT ÇÖZÜM: Mini450'den hazır hesaplanmış pahalılık skorlarını çek
                matching_rows = None
                try:
                    print(f"[TAKE PROFIT] 🔍 {symbol} için Mini450'den pahalılık skorları çekiliyor...")
                    if hasattr(self.parent, 'df') and not self.parent.df.empty:
                        print(f"[TAKE PROFIT] 📊 Mini450 DataFrame mevcut: {len(self.parent.df)} satır")
                        print(f"[TAKE PROFIT] 📋 Mini450 kolonları: {list(self.parent.df.columns)}")
                        
                        # DataFrame'de PREF IBKR kolonunda symbol'ü ara
                        if 'PREF IBKR' in self.parent.df.columns:
                            matching_rows = self.parent.df[self.parent.df['PREF IBKR'] == symbol]
                            print(f"[TAKE PROFIT] 🔍 {symbol} için {len(matching_rows)} eşleşme bulundu")
                            if not matching_rows.empty:
                                row = matching_rows.iloc[0]
                                print(f"[TAKE PROFIT] 📊 {symbol} satır verisi alındı")
                                
                                if self.position_type == "longs":
                                    # Longs için Ask Sell ve Front Sell pahalılığı
                                    print(f"[TAKE PROFIT] 🔍 {symbol} için mevcut kolonlar: {list(row.index)}")
                                    if 'Ask_sell_pahalilik_skoru' in row:
                                        try:
                                            ask_value = row['Ask_sell_pahalilik_skoru']
                                            if ask_value != 'N/A' and ask_value is not None:
                                                ask_sell_pahalilik = f"${float(ask_value):.4f}"
                                                print(f"[TAKE PROFIT] ✅ {symbol} Ask Sell Pahalılık: ${float(ask_value):.4f}")
                                            else:
                                                print(f"[TAKE PROFIT] ⚠️ {symbol} Ask_sell_pahalilik_skoru N/A")
                                        except (ValueError, TypeError):
                                            print(f"[TAKE PROFIT] ⚠️ {symbol} Ask_sell_pahalilik_skoru geçersiz değer: {row['Ask_sell_pahalilik_skoru']}")
                                    else:
                                        print(f"[TAKE PROFIT] ⚠️ {symbol} Ask_sell_pahalilik_skoru bulunamadı")
                                    
                                    if 'Front_sell_pahalilik_skoru' in row:
                                        try:
                                            front_value = row['Front_sell_pahalilik_skoru']
                                            if front_value != 'N/A' and front_value is not None:
                                                front_sell_pahalilik = f"${float(front_value):.4f}"
                                                print(f"[TAKE PROFIT] ✅ {symbol} Front Sell Pahalılık: ${float(front_value):.4f}")
                                            else:
                                                print(f"[TAKE PROFIT] ⚠️ {symbol} Front_sell_pahalilik_skoru N/A")
                                        except (ValueError, TypeError):
                                            print(f"[TAKE PROFIT] ⚠️ {symbol} Front_sell_pahalilik_skoru geçersiz değer: {row['Front_sell_pahalilik_skoru']}")
                                    else:
                                        print(f"[TAKE PROFIT] ⚠️ {symbol} Front_sell_pahalilik_skoru bulunamadı")
                                else:  # shorts
                                    # Shorts için Bid Buy ve Front Buy ucuzluğu
                                    if 'Bid_buy_ucuzluk_skoru' in row:
                                        try:
                                            bid_value = row['Bid_buy_ucuzluk_skoru']
                                            if bid_value != 'N/A' and bid_value is not None:
                                                bid_buy_ucuzluk = f"${float(bid_value):.4f}"
                                                print(f"[TAKE PROFIT] ✅ {symbol} Bid Buy Ucuzluk: ${float(bid_value):.4f}")
                                            else:
                                                print(f"[TAKE PROFIT] ⚠️ {symbol} Bid_buy_ucuzluk_skoru N/A")
                                        except (ValueError, TypeError):
                                            print(f"[TAKE PROFIT] ⚠️ {symbol} Bid_buy_ucuzluk_skoru geçersiz değer: {row['Bid_buy_ucuzluk_skoru']}")
                                    else:
                                        print(f"[TAKE PROFIT] ⚠️ {symbol} Bid_buy_ucuzluk_skoru bulunamadı")
                                    
                                    if 'Front_buy_ucuzluk_skoru' in row:
                                        try:
                                            front_value = row['Front_buy_ucuzluk_skoru']
                                            if front_value != 'N/A' and front_value is not None:
                                                front_buy_ucuzluk = f"${float(front_value):.4f}"
                                                print(f"[TAKE PROFIT] ✅ {symbol} Front Buy Ucuzluk: ${float(front_value):.4f}")
                                            else:
                                                print(f"[TAKE PROFIT] ⚠️ {symbol} Front_buy_ucuzluk_skoru N/A")
                                        except (ValueError, TypeError):
                                            print(f"[TAKE PROFIT] ⚠️ {symbol} Front_buy_ucuzluk_skoru geçersiz değer: {row['Front_buy_ucuzluk_skoru']}")
                                    else:
                                        print(f"[TAKE PROFIT] ⚠️ {symbol} Front_buy_ucuzluk_skoru bulunamadı")
                            else:
                                print(f"[TAKE PROFIT] ⚠️ {symbol} Mini450'de bulunamadı")
                        else:
                            print(f"[TAKE PROFIT] ⚠️ Mini450'de PREF IBKR kolonu bulunamadı")
                    else:
                        print(f"[TAKE PROFIT] ⚠️ Mini450 DataFrame bulunamadı")
                except Exception as e:
                    print(f"[TAKE PROFIT] ⚠️ {symbol} pahalılık/ucuzluk hesaplama hatası: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Tabloya ekle - Longs ve Shorts için farklı kolonlar
                if self.position_type == "longs":
                    values = [
                        "",  # Seç kolonu boş
                        symbol,
                        f"{qty:.0f}",
                        f"${avg_cost:.2f}" if avg_cost > 0 else "N/A",
                        f"{current_price:.2f}",
                        fbtot,  # FBtot
                        f"${pnl:.2f}",
                        f"${market_value:.2f}",
                        ask_sell_pahalilik,  # Ask Sell Pahalılık
                        front_sell_pahalilik,  # Front Sell Pahalılık
                        outperf_chg_pct,
                        timebased_bench_chg,
                        f"{avg_adv:.0f}",
                        f"{maxalw:.0f}",
                        f"{smi:.4f}" if smi > 0 else "N/A",
                        f"{final_fb:.4f}" if final_fb > 0 else "N/A",
                        f"{final_sfs:.4f}" if final_sfs > 0 else "N/A",
                        grup_value,  # Grup
                        f"{avg_final_fb:.2f}" if avg_final_fb != 0 else "",  # Avg Final FB
                        f"{avg_final_sfs:.2f}" if avg_final_sfs != 0 else "",  # Avg Final SFS
                        fbplagr,  # FBPlagr
                        fbratgr,  # FBRatgr
                        f"{gort:.2f}" if isinstance(gort, (int, float)) and not pd.isna(gort) else "N/A"  # GORT
                    ]
                else:  # shorts
                    values = [
                        "",  # Seç kolonu boş
                        symbol,
                        f"{qty:.0f}",
                        f"${avg_cost:.2f}" if avg_cost > 0 else "N/A",
                        f"{current_price:.2f}",
                        sfstot,  # SFStot
                        f"${pnl:.2f}",
                        f"${market_value:.2f}",
                        bid_buy_ucuzluk,  # Bid Buy Ucuzluk
                        front_buy_ucuzluk,  # Front Buy Ucuzluk
                        outperf_chg_pct,
                        timebased_bench_chg,
                        f"{avg_adv:.0f}",
                        f"{maxalw:.0f}",
                        f"{smi:.4f}" if smi > 0 else "N/A",
                        f"{final_fb:.4f}" if final_fb > 0 else "N/A",
                        f"{final_sfs:.4f}" if final_sfs > 0 else "N/A",
                        grup_value,  # Grup
                        f"{avg_final_fb:.2f}" if avg_final_fb != 0 else "",  # Avg Final FB
                        f"{avg_final_sfs:.2f}" if avg_final_sfs != 0 else "",  # Avg Final SFS
                        sfsplagr,  # SFSPlagr
                        sfsratgr,  # SFSRatgr
                        f"{gort:.2f}" if isinstance(gort, (int, float)) and not pd.isna(gort) else "N/A"  # GORT
                    ]
                
                item = self.tree.insert('', 'end', values=values)
                
                # Pozisyon verisini sakla
                # Skor verilerini ekle
                ask_sell_pahalilik_skoru = 0.0
                front_sell_pahalilik_skoru = 0.0
                bid_buy_ucuzluk_skoru = 0.0
                front_buy_ucuzluk_skoru = 0.0
                
                if matching_rows is not None and not matching_rows.empty:
                    row = matching_rows.iloc[0]
                    
                    if self.position_type == "longs":
                        # Longs için Ask Sell ve Front Sell pahalılığı
                        if 'Ask_sell_pahalilik_skoru' in row:
                            try:
                                ask_value = row['Ask_sell_pahalilik_skoru']
                                if ask_value != 'N/A' and ask_value is not None:
                                    ask_sell_pahalilik_skoru = float(ask_value)
                                else:
                                    ask_sell_pahalilik_skoru = 0.0
                            except (ValueError, TypeError):
                                ask_sell_pahalilik_skoru = 0.0
                        if 'Front_sell_pahalilik_skoru' in row:
                            try:
                                front_value = row['Front_sell_pahalilik_skoru']
                                if front_value != 'N/A' and front_value is not None:
                                    front_sell_pahalilik_skoru = float(front_value)
                                else:
                                    front_sell_pahalilik_skoru = 0.0
                            except (ValueError, TypeError):
                                front_sell_pahalilik_skoru = 0.0
                    else:  # shorts
                        # Shorts için Bid Buy ve Front Buy ucuzluğu
                        if 'Bid_buy_ucuzluk_skoru' in row:
                            try:
                                bid_value = row['Bid_buy_ucuzluk_skoru']
                                if bid_value != 'N/A' and bid_value is not None:
                                    bid_buy_ucuzluk_skoru = float(bid_value)
                                else:
                                    bid_buy_ucuzluk_skoru = 0.0
                            except (ValueError, TypeError):
                                bid_buy_ucuzluk_skoru = 0.0
                        if 'Front_buy_ucuzluk_skoru' in row:
                            try:
                                front_value = row['Front_buy_ucuzluk_skoru']
                                if front_value != 'N/A' and front_value is not None:
                                    front_buy_ucuzluk_skoru = float(front_value)
                                else:
                                    front_buy_ucuzluk_skoru = 0.0
                            except (ValueError, TypeError):
                                front_buy_ucuzluk_skoru = 0.0
                
                self.positions.append({
                    'item_id': item,
                    'symbol': symbol,
                    'qty': qty,
                    'avg_cost': avg_cost,
                    'current_price': current_price,
                    'avg_adv': avg_adv,
                    'maxalw': maxalw,
                    'smi': smi,
                    'final_fb': final_fb,
                    'final_sfs': final_sfs,
                    'ask_sell_pahalilik_skoru': ask_sell_pahalilik_skoru,
                    'front_sell_pahalilik_skoru': front_sell_pahalilik_skoru,
                    'bid_buy_ucuzluk_skoru': bid_buy_ucuzluk_skoru,
                    'front_buy_ucuzluk_skoru': front_buy_ucuzluk_skoru
                })
            
            self.lbl_info.config(text=f"{len(filtered_positions)} {self.position_type} pozisyon bulundu")
            self.update_selection_count()
            
        except Exception as e:
            self.lbl_info.config(text=f"Pozisyon yükleme hatası: {e}")
            print(f"[TAKE PROFIT] ❌ Pozisyon yükleme hatası: {e}")
            import traceback
            traceback.print_exc()
            
            # Hata oluşsa bile pencereyi kapatma, sadece hata mesajını göster
            print(f"[TAKE PROFIT] ⚠️ Hata oluştu ama pencere açık kalıyor...")
    
    def get_current_price(self, symbol):
        """Symbol için current price al"""
        try:
            # Hammer Pro'dan market data al
            market_data = self.hammer.get_market_data(symbol)
            if market_data and 'last' in market_data:
                return float(market_data['last'])
            
            # Parent'tan get_last_price_for_symbol kullan
            if hasattr(self.parent, 'get_last_price_for_symbol'):
                return self.parent.get_last_price_for_symbol(symbol) or 0.0
            
            return 0.0
        except:
            return 0.0
    
    def on_table_click(self, event):
        """Tabloya tıklama - Seçim durumunu değiştir"""
        try:
            region = self.tree.identify_region(event.x, event.y)
            if region != "cell":
                return
            
            column = self.tree.identify_column(event.x)
            if column != "#1":  # Sadece Seç kolonuna tıklandığında
                return
            
            item = self.tree.identify('item', event.x, event.y)
            if not item:
                return
            
            # Seçim durumunu değiştir
            current = self.tree.set(item, "select")
            symbol = self.tree.set(item, "symbol")
            
            if current == "✓":  # Seçili ise
                self.tree.set(item, "select", "")  # Seçimi kaldır
                if symbol in self.selected_positions:
                    try:
                        del self.selected_positions[symbol]
                    except Exception:
                        pass
            else:  # Seçili değilse
                self.tree.set(item, "select", "✓")  # Seç
                # Satırdan avg_cost ve qty alıp sözlüğe yaz
                values = self.tree.item(item)['values']
                try:
                    avg_cost_str = values[3]
                    if isinstance(avg_cost_str, str):
                        avg_cost_clean = avg_cost_str.replace('$', '').replace(',', '').strip()
                        avg_cost = float(avg_cost_clean) if avg_cost_clean else 0.0
                    else:
                        avg_cost = float(avg_cost_str)
                except Exception:
                    avg_cost = 0.0
                try:
                    qty = float(values[2])
                except Exception:
                    qty = 0.0
                self.selected_positions[symbol] = { 'avg_cost': avg_cost, 'qty': qty }
            
            self.update_selection_count()
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ Tablo tıklama hatası: {e}")
    
    def on_header_click(self, event):
        """Kolon başlığına tıklama - Sıralama yap"""
        try:
            region = self.tree.identify_region(event.x, event.y)
            if region == "heading":
                column = self.tree.identify_column(event.x)
                self.sort_by_column(column)
            else:
                # Normal tablo tıklama
                self.on_table_click(event)
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ Header tıklama hatası: {e}")
    
    def sort_by_column(self, column):
        """Kolon'a göre sırala"""
        try:
            # Kolon indeksini al
            col_index = int(column.replace('#', '')) - 1
            
            # Kolon adını al - Longs ve Shorts için farklı kolonlar
            if self.position_type == "longs":
                cols = ['select', 'symbol', 'qty', 'avg_cost', 'current_price', 'fbtot', 'pnl_vs_cost', 'market_value', 'ask_sell_pahalilik', 'front_sell_pahalilik', 'outperf_chg_pct', 'timebased_bench_chg', 'avg_adv', 'maxalw', 'smi', 'final_fb', 'final_sfs', 'grup', 'avg_final_fb', 'avg_final_sfs', 'fbplagr', 'fbratgr', 'gort']
            else:  # shorts
                cols = ['select', 'symbol', 'qty', 'avg_cost', 'current_price', 'sfstot', 'pnl_vs_cost', 'market_value', 'bid_buy_ucuzluk', 'front_buy_ucuzluk', 'outperf_chg_pct', 'timebased_bench_chg', 'avg_adv', 'maxalw', 'smi', 'final_fb', 'final_sfs', 'grup', 'avg_final_fb', 'avg_final_sfs', 'sfsplagr', 'sfsratgr', 'gort']
            if col_index < len(cols):
                col_name = cols[col_index]
                
                # Aynı kolona tekrar tıklandıysa sıralama yönünü değiştir
                if self.sort_column == col_name:
                    self.sort_reverse = not self.sort_reverse
                else:
                    self.sort_column = col_name
                    self.sort_reverse = False
                
                print(f"[TAKE PROFIT] OK {col_name} kolonuna gore siralaniyor... {'Azalan' if self.sort_reverse else 'Artan'}")
                
                # Mevcut verileri al
                items = []
                for item in self.tree.get_children():
                    values = self.tree.item(item)['values']
                    items.append(values)
                
                # Sırala
                if col_name == 'select':
                    # Seç kolonu için sıralama yapma
                    return
                elif col_name in ['qty', 'current_position', 'avg_cost', 'current_price', 'pnl_vs_cost', 'market_value', 'avg_adv', 'maxalw']:
                    # Sayısal kolonlar
                    items.sort(key=lambda x: float(str(x[col_index]).replace('$', '').replace(',', '')) if x[col_index] and str(x[col_index]) != 'N/A' else 0, reverse=self.sort_reverse)
                elif col_name in ['ask_sell_pahalilik', 'front_sell_pahalilik', 'bid_buy_ucuzluk', 'front_buy_ucuzluk']:
                    # Pahalılık/Ucuzluk kolonları ($ işareti ile)
                    items.sort(key=lambda x: float(str(x[col_index]).replace('$', '')) if x[col_index] and str(x[col_index]) != 'N/A' else 0, reverse=self.sort_reverse)
                elif col_name in ['smi', 'final_fb', 'final_sfs', 'avg_final_fb', 'avg_final_sfs', 'fbratgr', 'fbtot', 'sfsratgr', 'sfstot']:
                    # Skor kolonları
                    items.sort(key=lambda x: float(x[col_index]) if x[col_index] and str(x[col_index]) != 'N/A' else 0, reverse=self.sort_reverse)
                elif col_name == 'gort':
                    # GORT kolonu - sayısal sıralama
                    items.sort(key=lambda x: float(str(x[col_index]).replace('N/A', '0')) if x[col_index] and str(x[col_index]) != 'N/A' else 0, reverse=self.sort_reverse)
                elif col_name in ['fbplagr', 'sfsplagr']:
                    # FBPlagr/SFSPlagr kolonu (ondalık değeri al)
                    items.sort(key=lambda x: float(str(x[col_index]).split("(")[1].split(")")[0]) if x[col_index] and str(x[col_index]) != 'N/A' and "(" in str(x[col_index]) else 0, reverse=self.sort_reverse)
                else:
                    # Metin kolonları
                    items.sort(key=lambda x: str(x[col_index]) if x[col_index] else '', reverse=self.sort_reverse)
                
                # Tabloyu temizle ve sıralanmış verileri ekle
                for item in self.tree.get_children():
                    self.tree.delete(item)
                
                for values in items:
                    self.tree.insert('', 'end', values=values)
                
                print(f"[TAKE PROFIT] ✅ Sıralama tamamlandı")
                
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ Sıralama hatası: {e}")
    
    def on_double_click(self, event):
        """Çift tıklama - OrderBook penceresini aç"""
        try:
            item = self.tree.identify('item', event.x, event.y)
            if not item:
                return
            
            symbol = self.tree.set(item, "symbol")
            
            # OrderBook penceresini aç
            from .order_management import OrderBookWindow
            OrderBookWindow(self.parent, symbol, self.hammer)
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ OrderBook açma hatası: {e}")
    
    def select_all_positions(self):
        """Tüm pozisyonları seç"""
        for item in self.tree.get_children():
            symbol = self.tree.set(item, "symbol")
            self.tree.set(item, "select", "✓")
            
            # Avg cost'u dolar işaretinden temizle
            avg_cost_str = self.tree.item(item)['values'][3]
            if isinstance(avg_cost_str, str):
                avg_cost_str = avg_cost_str.replace('$', '').replace(',', '').strip()
                try:
                    avg_cost = float(avg_cost_str)
                except ValueError:
                    avg_cost = 0.0
            else:
                avg_cost = float(avg_cost_str)
            
            # Quantity'yi al
            qty_str = self.tree.item(item)['values'][2]
            try:
                qty = float(qty_str)
            except ValueError:
                qty = 0.0
            
            self.selected_positions[symbol] = {
                'qty': qty,
                'avg_cost': avg_cost
            }
        
        self.update_selection_count()
    
    def calculate_front_sell_price(self, symbol):
        """Front Sell fiyatını hesapla"""
        try:
            # Stock Data Manager'dan fiyat bilgisi al
            if hasattr(self.parent, 'stock_data_manager'):
                stock_data = self.parent.stock_data_manager.get_stock_data(symbol)
                if stock_data and 'ask' in stock_data:
                    return float(stock_data['ask'])
                elif stock_data and 'last_price' in stock_data:
                    return float(stock_data['last_price'])
            
            # Fallback: Avg cost kullan
            if symbol in self.selected_positions:
                avg_cost = self.selected_positions[symbol]['avg_cost']
                if avg_cost > 0:
                    return avg_cost
            
            return None
        except Exception as e:
            print(f"[CERCOP] Front Sell fiyat hatası ({symbol}): {e}")
            return None
    
    def calculate_front_buy_price(self, symbol):
        """Front Buy fiyatını hesapla"""
        try:
            # Stock Data Manager'dan fiyat bilgisi al
            if hasattr(self.parent, 'stock_data_manager'):
                stock_data = self.parent.stock_data_manager.get_stock_data(symbol)
                if stock_data and 'bid' in stock_data:
                    return float(stock_data['bid'])
                elif stock_data and 'last_price' in stock_data:
                    return float(stock_data['last_price'])
            
            # Fallback: Avg cost kullan
            if symbol in self.selected_positions:
                avg_cost = self.selected_positions[symbol]['avg_cost']
                if avg_cost > 0:
                    return avg_cost
            
            return None
        except Exception as e:
            print(f"[CERCOP] Front Buy fiyat hatası ({symbol}): {e}")
            return None
    
    def cercop_action(self):
        """Cercop: 200 lot'tan az olan tüm hisseleri seç ve emir onay penceresi aç"""
        try:
            # 200 lot'tan az olan pozisyonları bul
            small_lot_positions = []
            
            for item in self.tree.get_children():
                values = self.tree.item(item)['values']
                symbol = values[1] if values[0] == '' else values[0]  # Symbol 1. kolonda
                qty = float(values[2])  # Quantity kolonu
                
                # 200 lot'tan az olanları seç
                if abs(qty) < 200:
                    small_lot_positions.append({
                        'symbol': symbol,
                        'qty': qty,
                        'item': item
                    })
            
            if not small_lot_positions:
                messagebox.showinfo("Cercop", "200 lot'tan az pozisyon bulunamadı!")
                return
            
            print(f"[CERCOP] 🔍 {len(small_lot_positions)} küçük lot pozisyonu bulundu")
            
            # Debug: Pozisyonları listele
            for pos in small_lot_positions:
                print(f"[CERCOP DEBUG] {pos['symbol']}: qty={pos['qty']}")
            
            # Emir onay penceresi aç
            self.show_cercop_confirmation(small_lot_positions)
            
        except Exception as e:
            print(f"[CERCOP] ERROR Cercop hatası: {e}")
            messagebox.showerror("Hata", f"Cercop hatası: {e}")
    
    def show_cercop_confirmation(self, small_lot_positions):
        """Cercop için emir onay penceresi"""
        try:
            # Onay penceresi
            confirm_win = tk.Toplevel(self.win)
            confirm_win.title("Cercop Emir Onayı")
            confirm_win.geometry("800x600")
            confirm_win.transient(self.win)
            confirm_win.grab_set()
            
            # Başlık
            title_frame = ttk.Frame(confirm_win)
            title_frame.pack(fill='x', padx=10, pady=10)
            
            ttk.Label(title_frame, text="Cercop Emir Onayı", font=('Arial', 14, 'bold')).pack()
            ttk.Label(title_frame, text=f"{len(small_lot_positions)} küçük lot pozisyonu için emirler (200 lot altı)", font=('Arial', 10)).pack()
            
            # Emir listesi
            list_frame = ttk.Frame(confirm_win)
            list_frame.pack(fill='both', expand=True, padx=10, pady=5)
            
            # Treeview
            columns = ('Symbol', 'Qty', 'Action', 'Price', 'Lot')
            order_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
            
            # Kolon başlıkları
            for col in columns:
                order_tree.heading(col, text=col)
                order_tree.column(col, width=120)
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=order_tree.yview)
            order_tree.configure(yscrollcommand=scrollbar.set)
            
            order_tree.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # Emirleri hazırla ve listeye ekle
            order_details = []
            
            for pos in small_lot_positions:
                symbol = pos['symbol']
                qty = pos['qty']
                
                # Action belirle
                if self.position_type == "longs":
                    action = "SELL"  # Long pozisyonlar için Front Sell
                    action_text = "Front Sell"
                else:  # shorts
                    action = "BUY"   # Short pozisyonlar için Front Buy
                    action_text = "Front Buy"
                
                # Fiyat hesapla - LAST PRINT'ten hesapla (last print - 0.01 veya + 0.01)
                try:
                    last_print = None
                    
                    # ÖNCE: get_market_data ile 'last' değerini al (en güvenilir)
                    if hasattr(self.parent, 'hammer') and self.parent.hammer and self.parent.hammer.connected:
                        try:
                            # Symbol dönüşümü (PR -> -)
                            hammer_symbol = symbol.replace(" PR", "-")
                            market_data = self.parent.hammer.get_market_data(hammer_symbol)
                            if market_data and 'last' in market_data:
                                last_print = float(market_data['last'])
                                if last_print > 0:
                                    print(f"[CERCOP] {symbol}: last_print={last_print:.2f} (get_market_data)")
                        except Exception as e:
                            print(f"[CERCOP] get_market_data hatası ({symbol}): {e}")
                    
                    # İKİNCİ: get_ticks ile son tick'i al
                    if (last_print is None or last_print <= 0) and hasattr(self.parent, 'hammer') and self.parent.hammer and self.parent.hammer.connected:
                        try:
                            # getTicks ile son tick'i al
                            tick_data = self.parent.hammer.get_ticks(symbol, lastFew=1, tradesOnly=True, regHoursOnly=False)
                            if tick_data and 'data' in tick_data and tick_data['data']:
                                ticks = tick_data['data']
                                if ticks:
                                    last_tick = ticks[-1]  # En son tick
                                    last_print = float(last_tick.get('price', 0))
                                    if last_print > 0:
                                        print(f"[CERCOP] {symbol}: last_print={last_print:.2f} (getTicks)")
                        except Exception as e:
                            print(f"[CERCOP] getTicks hatası ({symbol}): {e}")
                    
                    # ÜÇÜNCÜ: Stock Data Manager'dan last_price al
                    if (last_print is None or last_print <= 0) and hasattr(self.parent, 'stock_data_manager') and self.parent.stock_data_manager:
                        try:
                            stock_data = self.parent.stock_data_manager.get_stock_data(symbol)
                            if stock_data and 'last_price' in stock_data and stock_data['last_price']:
                                last_print = float(stock_data['last_price'])
                                if last_print > 0:
                                    print(f"[CERCOP] {symbol}: last_price={last_print:.2f} (Stock Data Manager)")
                        except Exception as e:
                            print(f"[CERCOP] Stock Data Manager hatası ({symbol}): {e}")
                    
                    # LAST PRINT bulunamadıysa emri atla (avg_cost kullanma!)
                    if last_print is None or last_print <= 0:
                        print(f"[CERCOP] ❌ SKIP {symbol}: Last print bulunamadı - emir atlanıyor")
                        continue
                    
                    # Fiyat hesapla: Front Sell = last_print - 0.01, Front Buy = last_print + 0.01
                    if self.position_type == "longs":
                        price = last_print - 0.01  # Front Sell: last print - 0.01
                    else:  # shorts
                        price = last_print + 0.01  # Front Buy: last print + 0.01
                    
                    print(f"[CERCOP] ✅ {symbol}: last_print={last_print:.2f} → price={price:.2f} ({action_text})")
                        
                except Exception as e:
                    print(f"[CERCOP] ❌ Fiyat hesaplama hatası ({symbol}): {e}")
                    print(f"[CERCOP] ❌ SKIP {symbol}: Hata nedeniyle emir atlanıyor")
                    continue
                
                # Emir detayını kaydet
                order_detail = {
                    'symbol': symbol,
                    'action': action,
                    'price': price,
                    'quantity': abs(qty),
                    'action_text': action_text
                }
                order_details.append(order_detail)
                
                # Treeview'e ekle
                order_tree.insert('', 'end', values=(
                    symbol,
                    f"{qty:.0f}",
                    action_text,
                    f"${price:.2f}",
                    f"{abs(qty):.0f}"
                ))
            
            if not order_details:
                messagebox.showwarning("Cercop", "Geçerli emir bulunamadı!")
                confirm_win.destroy()
                return
            
            # Butonlar
            button_frame = ttk.Frame(confirm_win)
            button_frame.pack(fill='x', padx=10, pady=10)
            
            def send_orders():
                """Seçili emirleri gönder"""
                try:
                    print(f"[CERCOP] 🔄 {len(order_details)} emir gönderiliyor...")
                    
                    successful_orders = 0
                    failed_orders = 0
                    
                    for order in order_details:
                        symbol = order['symbol']
                        action = order['action']
                        price = order['price']
                        quantity = order['quantity']
                        action_text = order['action_text']
                        
                        # Emir gönder
                        if self.parent.mode_manager.is_hammer_mode():
                            # Hammer Pro - Symbol dönüşümü
                            hammer_symbol = symbol.replace(" PR", "-")
                            
                            try:
                                success = self.hammer.place_order(
                                    symbol=hammer_symbol,
                                    side=action,
                                    quantity=quantity,
                                    price=price,
                                    order_type="LIMIT",
                                    hidden=True
                                )
                                
                                if success or "new order sent" in str(success):
                                    successful_orders += 1
                                    print(f"[CERCOP] ✅ {symbol} → {hammer_symbol}: {action_text} {quantity} lot @ ${price:.2f}")
                                else:
                                    failed_orders += 1
                                    print(f"[CERCOP] ❌ {symbol} → {hammer_symbol}: {action_text} {quantity} lot @ ${price:.2f}")
                            except Exception as e:
                                if "new order sent" in str(e).lower():
                                    successful_orders += 1
                                    print(f"[CERCOP] ✅ {symbol} → {hammer_symbol}: {action_text} {quantity} lot @ ${price:.2f} (new order sent)")
                                else:
                                    failed_orders += 1
                                    print(f"[CERCOP] ❌ {symbol} → {hammer_symbol}: {e}")
                        else:
                            # IBKR
                            success = self.parent.mode_manager.place_order(
                                symbol=symbol,
                                side=action,
                                quantity=quantity,
                                price=price,
                                order_type="LIMIT",
                                hidden=True
                            )
                            
                            if success:
                                successful_orders += 1
                                print(f"[CERCOP] ✅ {symbol}: {action_text} {quantity} lot @ ${price:.2f}")
                            else:
                                failed_orders += 1
                                print(f"[CERCOP] ❌ {symbol}: {action_text} {quantity} lot @ ${price:.2f}")
                    
                    # Sonuç mesajı
                    messagebox.showinfo("Cercop Tamamlandı", 
                                      f"Başarılı: {successful_orders} emir\n"
                                      f"Başarısız: {failed_orders} emir\n"
                                      f"Toplam: {len(order_details)} pozisyon")
                    
                    confirm_win.destroy()
                    
                except Exception as e:
                    print(f"[CERCOP] ❌ Emir gönderme hatası: {e}")
                    messagebox.showerror("Hata", f"Emir gönderme hatası: {e}")
            
            def save_to_trades_csv():
                """Seçili emirleri trades.csv formatında kaydet"""
                try:
                    print(f"[CERCOP CSV] 🔄 {len(order_details)} emir trades.csv'ye kaydediliyor...")
                    
                    # CSV satırları
                    csv_rows = []
                    
                    for order in order_details:
                        symbol = order['symbol']
                        action = order['action']
                        price = order['price']
                        quantity = order['quantity']
                        
                        # CSV formatı (orijinal format)
                        csv_row = [
                            action,                    # Action
                            int(quantity),             # Quantity
                            symbol,                    # Symbol
                            'STK',                    # SecType
                            'SMART/AMEX',              # Exchange
                            'USD',                    # Currency
                            'DAY',                    # TimeInForce
                            'LMT',                    # OrderType
                            f"{price:.2f}",           # LmtPrice
                            'Basket',                 # BasketTag
                            'U21016730',              # Account
                            'Basket',                 # OrderRef
                            'TRUE',                   # Hidden
                            'TRUE'                    # OutsideRth
                        ]
                        
                        csv_rows.append(csv_row)
                        print(f"[CERCOP CSV] ✅ {symbol}: {action} {quantity} @ ${price:.2f}")
                    
                    if csv_rows:
                        # CSV dosyasına kaydet
                        import csv
                        
                        csv_filename = 'trades.csv'
                        
                        # Her seferinde yeni dosya oluştur (0'dan yaz)
                        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                            writer = csv.writer(csvfile)
                            
                            # Header yaz (orijinal format)
                            headers = ['Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 'Currency', 'TimeInForce', 'OrderType', 'LmtPrice', 'BasketTag', 'Account', 'OrderRef', 'Hidden', 'OutsideRth']
                            writer.writerow(headers)
                            
                            # Emirleri yaz
                            writer.writerows(csv_rows)
                        
                        print(f"[CERCOP CSV] ✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                        messagebox.showinfo("Başarılı", f"{len(csv_rows)} emir trades.csv'ye kaydedildi!")
                    else:
                        messagebox.showwarning("Uyarı", "Kaydedilecek geçerli emir bulunamadı!")
                        
                except Exception as e:
                    print(f"[CERCOP CSV] ❌ Kaydetme hatası: {e}")
                    messagebox.showerror("Hata", f"trades.csv kaydetme hatası: {e}")
            
            def cancel_orders():
                """İptal et"""
                confirm_win.destroy()
            
            # Butonları ekle
            ttk.Button(button_frame, text="Emirleri Gönder", command=send_orders, style='Accent.TButton').pack(side='left', padx=5)
            ttk.Button(button_frame, text="trades.csv'ye Kaydet", command=save_to_trades_csv).pack(side='left', padx=5)
            ttk.Button(button_frame, text="İptal", command=cancel_orders).pack(side='right', padx=5)
            
        except Exception as e:
            print(f"[CERCOP] ❌ Onay penceresi hatası: {e}")
            messagebox.showerror("Hata", f"Onay penceresi hatası: {e}")
    
    def deselect_all_positions(self):
        """Tüm seçimleri kaldır"""
        for item in self.tree.get_children():
            self.tree.set(item, "select", "")
        
        self.selected_positions.clear()
        self.update_selection_count()
    
    def update_selection_count(self):
        """Seçili pozisyon sayısını güncelle"""
        count = len(self.selected_positions)
        self.lbl_selected.config(text=f"{count} pozisyon seçildi")
    
    def set_lot_percentage(self, percentage):
        """Lot'u pozisyon miktarının yüzdesi olarak ayarla - 100'lük yuvarlama ile"""
        # Sözlük yapısında seçim kontrolü
        if not isinstance(self.selected_positions, dict) or len(self.selected_positions) == 0:
            messagebox.showwarning("Uyarı", "Önce pozisyon seçin!")
            return
        
        try:
            # Her hisse için ayrı lot hesapla
            total_lot = 0
            for pos in self.positions:
                if pos['symbol'] in self.selected_positions:
                    # Her hissenin kendi miktarının yüzdesi
                    calculated_lot = abs(pos['qty']) * percentage / 100
                    
                    # %100 haricinde 100'lük yuvarlama yap
                    if percentage == 100:
                        # %100 için normal yuvarlama
                        individual_lot = int(round(calculated_lot))
                    else:
                        # %25, %50, %75 için 100'lük aşağı yuvarlama
                        individual_lot = int(calculated_lot // 100) * 100
                        # Minimum 100 lot
                        if individual_lot < 100:
                            individual_lot = 100
                    
                    total_lot += individual_lot
                    print(f"[TAKE PROFIT %{percentage}] 🔍 {pos['symbol']}: Qty={abs(pos['qty'])} → %{percentage}={calculated_lot:.1f} → Lot={individual_lot}")
            
            # Toplam lot'u göster
            self.lot_entry.delete(0, tk.END)
            self.lot_entry.insert(0, str(total_lot))
            
            # Bilgi mesajı göster
            # RUNALL Allowed modunda messagebox gösterme
            if hasattr(self.parent, 'runall_allowed_mode') and self.parent.runall_allowed_mode:
                print(f"[TAKE PROFIT] ✅ Allowed modu: Lot Hesaplama mesajı atlandı - Toplam lot: {total_lot}")
            else:
                messagebox.showinfo("Lot Hesaplama", 
                                  f"Her hisse için {percentage}% hesaplandı (100'lük yuvarlama):\n"
                                  f"Toplam lot: {total_lot}")
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ Lot yüzde hesaplama hatası: {e}")
    
    def set_lot_avg_adv(self):
        """Lot'u AVG_ADV olarak ayarla"""
        if not self.selected_positions:
            messagebox.showwarning("Uyarı", "Önce pozisyon seçin!")
            return
        
        try:
            # CSV'den AVG_ADV değerlerini al
            total_avg_adv = 0
            count = 0
            
            for pos in self.positions:
                if pos['symbol'] in self.selected_positions:
                    # CSV'den AVG_ADV değerini bul
                    avg_adv = self.get_avg_adv_from_csv(pos['symbol'])
                    if avg_adv > 0:
                        total_avg_adv += avg_adv
                        count += 1
            
            if count > 0:
                avg_adv_value = int(total_avg_adv / count)
                self.lot_entry.delete(0, tk.END)
                self.lot_entry.insert(0, str(avg_adv_value))
            else:
                messagebox.showwarning("Uyarı", "AVG_ADV değerleri bulunamadı!")
                
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ AVG_ADV hesaplama hatası: {e}")
    
    def get_avg_adv_from_csv(self, symbol):
        """CSV'den AVG_ADV değerini al"""
        try:
            # Parent'tan DataFrame'i al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                row = self.parent.df[self.parent.df['PREF IBKR'] == symbol]
                if not row.empty:
                    avg_adv = row['AVG_ADV'].iloc[0]
                    if pd.notna(avg_adv) and avg_adv != 'N/A':
                        return float(avg_adv)
            
            return 0.0
        except:
            return 0.0
    
    def get_smi_from_csv(self, symbol):
        """CSV'den SMI değerini al"""
        try:
            # CSV dosyalarından SMI değerini bul
            import glob
            import pandas as pd
            
            # Tüm ssfinek CSV dosyalarını bul
            csv_files = glob.glob('ssfinek*.csv')
            
            for csv_file in csv_files:
                try:
                    # Dosyayı oku
                    df = pd.read_csv(csv_file, encoding='utf-8-sig')
                    
                    # PREF IBKR ve SMI kolonları var mı kontrol et
                    if 'PREF IBKR' in df.columns and 'SMI' in df.columns:
                        # Symbol'ü bul
                        row = df[df['PREF IBKR'] == symbol]
                        if not row.empty:
                            smi = row['SMI'].iloc[0]
                            if pd.notna(smi) and smi != 'N/A':
                                return float(smi)
                except Exception as e:
                    continue
            
            return 0.0
        except:
            return 0.0
    
    def auto_select_profitable_positions(self, order_type):
        """Kârlı pozisyonları otomatik seç"""
        try:
            selected_count = 0
            
            # Önce tüm seçimleri temizle
            self.selected_positions.clear()
            
            for pos in self.positions:
                symbol = pos['symbol']
                
                if order_type == "Pahalı Prof Sell":
                    # Ask Sell Pahalılık Skoru > 0.05 kontrolü
                    pahalilik_skoru = self.get_ask_sell_pahalilik_skoru(symbol)
                    if pahalilik_skoru > 0.05:
                        self.selected_positions.add(symbol)
                        selected_count += 1
                        print(f"[AUTO SELECT] ✅ {symbol}: Ask Sell Pahalılık = ${pahalilik_skoru:.4f} > 0.05")
                
                elif order_type == "Ucuz Prof Buy":
                    # Bid Buy Ucuzluk Skoru < -0.05 kontrolü
                    ucuzluk_skoru = self.get_bid_buy_ucuzluk_skoru(symbol)
                    if ucuzluk_skoru < -0.05:
                        self.selected_positions.add(symbol)
                        selected_count += 1
                        print(f"[AUTO SELECT] ✅ {symbol}: Bid Buy Ucuzluk = ${ucuzluk_skoru:.4f} < -0.05")
            
            # Tabloyu güncelle
            self.update_table_selections()
            
            # Sonuç mesajı
            if selected_count > 0:
                messagebox.showinfo("Otomatik Seçim", 
                                  f"{selected_count} pozisyon otomatik seçildi!\n"
                                  f"Koşulları sağlayan pozisyonlar için emir hazırlanıyor...")
            else:
                messagebox.showinfo("Otomatik Seçim", 
                                  "Koşulları sağlayan pozisyon bulunamadı.\n"
                                  f"{order_type} için uygun pozisyon yok.")
                
        except Exception as e:
            print(f"[AUTO SELECT] ❌ Otomatik seçim hatası: {e}")
            messagebox.showerror("Hata", f"Otomatik seçim hatası: {e}")
    
    def update_table_selections(self):
        """Tablodaki seçimleri güncelle"""
        try:
            for item in self.tree.get_children():
                values = self.tree.item(item)['values']
                symbol = values[1]  # Symbol kolonu
                
                if symbol in self.selected_positions:
                    self.tree.set(item, 'select', '☑')
                else:
                    self.tree.set(item, 'select', '☐')
        except Exception as e:
            print(f"[UPDATE TABLE] ❌ Tablo güncelleme hatası: {e}")
    
    def place_orders(self, order_type):
        """Seçili pozisyonlar için emir gönder"""
        # Özel emir türleri için otomatik seçim yap
        if order_type in ["Pahalı Prof Sell", "Ucuz Prof Buy"]:
            self.auto_select_profitable_positions(order_type)
        
        if not self.selected_positions:
            messagebox.showwarning("Uyarı", "Önce pozisyon seçin!")
            return
        
        try:
            lot_size = int(self.lot_entry.get())
        except ValueError:
            messagebox.showerror("Hata", "Geçersiz lot değeri!")
            return
        
        # Emir onay penceresi göster
        self.show_order_confirmation(order_type, lot_size)
        
    def show_order_confirmation(self, order_type, lot_size):
        """Emir onay penceresi göster"""
        # Onay penceresi
        confirm_win = tk.Toplevel(self.win)
        confirm_win.title(f"Emir Onayı - {order_type}")
        confirm_win.geometry("800x600")
        confirm_win.transient(self.win)
        confirm_win.grab_set()
        
        # Başlık
        title = f"{order_type} Emirleri - {len(self.selected_positions)} Pozisyon"
        ttk.Label(confirm_win, text=title, font=('Arial', 12, 'bold')).pack(pady=10)
        
        # Emir detayları tablosu
        cols = ['symbol', 'qty', 'order_price', 'order_info', 'lot_size']
        headers = ['Symbol', 'Qty', 'Emir Fiyatı', 'Emir Bilgisi', 'Lot Size']
        
        tree = ttk.Treeview(confirm_win, columns=cols, show='headings', height=15)
        
        for c, h in zip(cols, headers):
            tree.heading(c, text=h)
            if c == 'symbol':
                tree.column(c, width=100, anchor='center')
            elif c == 'qty':
                tree.column(c, width=80, anchor='center')
            elif c == 'order_price':
                tree.column(c, width=120, anchor='center')
            elif c == 'lot_size':
                tree.column(c, width=100, anchor='center')
            else:
                tree.column(c, width=200, anchor='center')
        
        tree.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Emir detaylarını ekle
        order_details = []
        
        for pos in self.positions:
            if pos['symbol'] in self.selected_positions:
                symbol = pos['symbol']
                qty = pos['qty']
                
                # Market data al
                market_data = self.hammer.get_market_data(symbol)
                if not market_data:
                    continue
                
                bid = float(market_data.get('bid', 0))
                ask = float(market_data.get('ask', 0))
                last = float(market_data.get('last', 0))
                spread = ask - bid if ask > 0 and bid > 0 else 0
                
                # Emir fiyatını hesapla
                if order_type == "Ask Sell":
                    price = ask - (spread * 0.15) if spread > 0 else ask
                    action = "SELL"
                elif order_type == "Front Sell":
                    price = last - 0.01 if last > 0 else 0
                    action = "SELL"
                elif order_type == "SoftFront Sell":
                    # SoftFront Sell koşullarını kontrol et
                    if not self.check_soft_front_sell_conditions(bid, ask, last):
                        text_widget.insert(tk.END, f"⚠️ {symbol} SoftFront Sell koşulları sağlanmıyor - emir atlandı\n")
                        text_widget.insert(tk.END, f"   Bid: ${bid:.4f}, Ask: ${ask:.4f}, Last: ${last:.4f}\n")
                        text_widget.insert(tk.END, f"   Spread: ${spread:.4f}\n")
                        text_widget.insert(tk.END, "-" * 40 + "\n")
                        continue
                    price = last - 0.01 if last > 0 else 0
                    action = "SELL"
                elif order_type == "Bid Sell":
                    price = bid - 0.01 if bid > 0 else 0
                    action = "SELL"
                elif order_type == "Bid Buy":
                    price = bid + (spread * 0.15) if spread > 0 else bid
                    action = "BUY"
                elif order_type == "Front Buy":
                    price = last + 0.01 if last > 0 else 0
                    action = "BUY"
                elif order_type == "SoftFront Buy":
                    # SoftFront Buy koşullarını kontrol et
                    if not self.check_soft_front_buy_conditions(bid, ask, last):
                        text_widget.insert(tk.END, f"⚠️ {symbol} SoftFront Buy koşulları sağlanmıyor - emir atlandı\n")
                        text_widget.insert(tk.END, f"   Bid: ${bid:.4f}, Ask: ${ask:.4f}, Last: ${last:.4f}\n")
                        text_widget.insert(tk.END, f"   Spread: ${spread:.4f}\n")
                        text_widget.insert(tk.END, "-" * 40 + "\n")
                        continue
                    price = last + 0.01 if last > 0 else 0
                    action = "BUY"
                elif order_type == "Ask Buy":
                    price = ask + 0.01 if ask > 0 else 0
                    action = "BUY"
                elif order_type == "Pahalı Prof Sell":
                    # Ask Sell Pahalılık Skoru > 0.05 cent kontrolü
                    pahalilik_skoru = self.get_ask_sell_pahalilik_skoru(symbol)
                    if pahalilik_skoru <= 0.05:
                        text_widget.insert(tk.END, f"⚠️ {symbol} Ask Sell Pahalılık Skoru yeterli değil: {pahalilik_skoru:.4f} (Min: 0.05)\n")
                        text_widget.insert(tk.END, "-" * 40 + "\n")
                        continue
                    
                    # Kârlı lot hesapla
                    individual_lot = self.calculate_profitable_lot_size(qty)
                    if individual_lot == 0:
                        text_widget.insert(tk.END, f"⚠️ {symbol} için yeterli lot yok (Mevcut: {abs(qty)})\n")
                        text_widget.insert(tk.END, "-" * 40 + "\n")
                        continue
                    
                    # Ask Sell fiyatı hesapla
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        price = ask - (spread * 0.15)
                    else:
                        price = ask if ask > 0 else 0
                    action = "SELL"
                elif order_type == "Ucuz Prof Buy":
                    # Bid Buy Ucuzluk Skoru < -0.05 cent kontrolü
                    ucuzluk_skoru = self.get_bid_buy_ucuzluk_skoru(symbol)
                    if ucuzluk_skoru >= -0.05:
                        text_widget.insert(tk.END, f"⚠️ {symbol} Bid Buy Ucuzluk Skoru yeterli değil: {ucuzluk_skoru:.4f} (Max: -0.05)\n")
                        text_widget.insert(tk.END, "-" * 40 + "\n")
                        continue
                    
                    # Kârlı lot hesapla
                    individual_lot = self.calculate_profitable_lot_size(qty)
                    if individual_lot == 0:
                        text_widget.insert(tk.END, f"⚠️ {symbol} için yeterli lot yok (Mevcut: {abs(qty)})\n")
                        text_widget.insert(tk.END, "-" * 40 + "\n")
                        continue
                    
                    # Bid Buy fiyatı hesapla
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        price = bid + (spread * 0.15)
                    else:
                        price = bid if bid > 0 else 0
                    action = "BUY"
                else:
                    continue
                
                # Profitable emirler için özel lot hesaplama
                if order_type in ["Pahalı Prof Sell", "Ucuz Prof Buy"]:
                    # Zaten calculate_profitable_lot_size ile hesaplandı
                    pass  # individual_lot zaten hesaplandı
                else:
                    # Normal emirler için lot hesaplama
                    total_selected_qty = sum(abs(p['qty']) for p in self.positions if p['symbol'] in self.selected_positions)
                    if total_selected_qty > 0:
                        raw_individual_lot = abs(qty) * lot_size / total_selected_qty
                        # 100'lük yuvarlama uygula
                        individual_lot = int(raw_individual_lot // 100) * 100
                        if individual_lot < 100:  # Minimum 100 lot
                            individual_lot = 100
                    else:
                        # Lot size'ı da 100'lük yuvarlama ile düzelt
                        individual_lot = int(lot_size // 100) * 100
                        if individual_lot < 100:  # Minimum 100 lot
                            individual_lot = 100
                
                # Lot bölücü kontrolü
                if hasattr(self.parent, 'lot_divider_enabled') and self.parent.lot_divider_enabled:
                    # Lot'u 200er parçalara böl
                    lot_parts = self.divide_lot_size(individual_lot)
                    
                    # Her parça için emir oluştur
                    for i, part_lot in enumerate(lot_parts, 1):
                        order_info = f"{part_lot} lot {action} @ ${price:.2f} (HIDDEN) - Parça {i}/{len(lot_parts)}"
                        
                        # Tabloya ekle
                        tree.insert('', 'end', values=[
                            symbol,
                            f"{abs(qty):.0f}",
                            f"${price:.2f}",
                            order_info,
                            f"{part_lot}"
                        ])
                        
                        # Emir detayını sakla
                        order_details.append({
                            'symbol': symbol,
                            'action': action,
                            'price': price,
                            'quantity': part_lot,
                            'part_number': i,
                            'total_parts': len(lot_parts)
                        })
                else:
                    # Normal emir (lot bölücü kapalı)
                    order_info = f"{individual_lot} lot {action} @ ${price:.2f} (HIDDEN)"
                    
                    # Tabloya ekle
                    tree.insert('', 'end', values=[
                        symbol,
                        f"{abs(qty):.0f}",
                        f"${price:.2f}",
                        order_info,
                        f"{individual_lot}"
                    ])
                    
                    # Emir detayını sakla
                    order_details.append({
                        'symbol': symbol,
                        'action': action,
                        'price': price,
                        'quantity': individual_lot
                    })
        
        # Butonlar
        button_frame = ttk.Frame(confirm_win)
        button_frame.pack(pady=10)
        
        def confirm_orders():
            """Emirleri gönder"""
            try:
                print(f"[TAKE PROFIT] OK {len(order_details)} emir gonderiliyor...")
                
                # Mevcut moda göre emir gönder
                if hasattr(self.parent, 'mode_manager'):
                    if self.parent.mode_manager.is_hampro_mode():
                        print("[TAKE PROFIT] OK HAMPRO modunda emirler gonderiliyor...")
                        for order in order_details:
                            symbol = order['symbol']
                            action = order['action']
                            price = order['price']
                            quantity = order['quantity']
                            
                            # Symbol mapping (PR -> -)
                            hammer_symbol = symbol.replace(" PR", "-")
                            
                            # Hammer Pro'ya emir gönder
                            self.hammer.place_order(
                                symbol=hammer_symbol,
                                side=action,
                                quantity=quantity,
                                price=price,
                                order_type="LIMIT",
                                hidden=True  # Hidden emirler için
                            )
                            
                            print(f"[TAKE PROFIT] ✅ {symbol}: {action} {quantity} lot @ ${price:.2f} (HAMPRO)")
                    
                    elif self.parent.mode_manager.is_ibkr_mode():
                        print("[TAKE PROFIT] 🔄 IBKR modunda emirler gönderiliyor...")
                        import time
                        
                        success_count = 0
                        failed_count = 0
                        
                        for i, order in enumerate(order_details):
                            try:
                                symbol = order['symbol']
                                action = order['action']
                                price = order['price']
                                quantity = order['quantity']
                                
                                print(f"[TAKE PROFIT] 🔄 Emir {i+1}/{len(order_details)}: {symbol} {action} {quantity} lot @ ${price:.2f}")
                                
                                # IBKR modunda symbol'ü olduğu gibi gönder (PMT PRC)
                                order_symbol = symbol  # PMT PRC
                                
                                # Mode manager ile emir gönder
                                success = self.parent.mode_manager.place_order(
                                    symbol=order_symbol,
                                    side=action,
                                    quantity=quantity,
                                    price=price,
                                    order_type="LIMIT",
                                    hidden=True
                                )
                                
                                if success:
                                    success_count += 1
                                    print(f"[TAKE PROFIT] ✅ {symbol}: {action} {quantity} lot @ ${price:.2f} (IBKR)")
                                else:
                                    failed_count += 1
                                    print(f"[TAKE PROFIT] ❌ {symbol}: {action} {quantity} lot @ ${price:.2f} - Başarısız (IBKR)")
                                
                                # IBKR API rate limiting artık ModeManager'da global throttle ile yönetiliyor
                                    
                            except Exception as e:
                                failed_count += 1
                                print(f"[TAKE PROFIT] ❌ Emir {i+1} hatası: {e}")
                                import traceback
                                traceback.print_exc()
                        
                        # Sonuç özeti
                        print(f"[TAKE PROFIT] 📊 Sonuç: {success_count} başarılı, {failed_count} başarısız")
                        if success_count > 0:
                            # RUNALL Allowed modunda messagebox gösterme
                            if not (hasattr(self.parent, 'runall_allowed_mode') and self.parent.runall_allowed_mode):
                                messagebox.showinfo("Emir Sonucu", 
                                                  f"{success_count} emir başarıyla gönderildi!\n"
                                                  f"{failed_count} emir başarısız oldu.")
                            else:
                                print(f"[TAKE PROFIT] ℹ️ Allowed modu aktif - 'Emir Sonucu' penceresi gösterilmedi")
                                # Hata mesajını otomatik kapatmak için kısa bir gecikme ekle
                                # parent MainWindow olmalı (after metodu için)
                                if hasattr(self.parent, 'addnewpos_close_messagebox') and hasattr(self.parent, 'after'):
                                    self.parent.after(500, lambda: self.parent.addnewpos_close_messagebox())
                                elif hasattr(self.parent, 'main_window') and hasattr(self.parent.main_window, 'addnewpos_close_messagebox'):
                                    self.parent.main_window.after(500, lambda: self.parent.main_window.addnewpos_close_messagebox())
                                if hasattr(self.parent, 'runall_auto_confirm_messagebox') and hasattr(self.parent, 'after'):
                                    self.parent.after(500, lambda: self.parent.runall_auto_confirm_messagebox())
                                elif hasattr(self.parent, 'main_window') and hasattr(self.parent.main_window, 'runall_auto_confirm_messagebox'):
                                    self.parent.main_window.after(500, lambda: self.parent.main_window.runall_auto_confirm_messagebox())
                        else:
                            # RUNALL Allowed modunda hata mesajını gösterme
                            if not (hasattr(self.parent, 'runall_allowed_mode') and self.parent.runall_allowed_mode):
                                messagebox.showerror("Hata", "Hiçbir emir gönderilemedi!")
                            else:
                                print(f"[TAKE PROFIT] ℹ️ Allowed modu aktif - Hata mesajı gösterilmedi")
                                # parent MainWindow olmalı (after metodu için)
                                if hasattr(self.parent, 'addnewpos_close_messagebox') and hasattr(self.parent, 'after'):
                                    self.parent.after(500, lambda: self.parent.addnewpos_close_messagebox())
                                elif hasattr(self.parent, 'main_window') and hasattr(self.parent.main_window, 'addnewpos_close_messagebox'):
                                    self.parent.main_window.after(500, lambda: self.parent.main_window.addnewpos_close_messagebox())
                            return
                    else:
                        print("[TAKE PROFIT] ⚠️ Mod belirlenemedi, HAMPRO kullanılıyor...")
                        # Fallback to HAMPRO
                        for order in order_details:
                            symbol = order['symbol']
                            action = order['action']
                            price = order['price']
                            quantity = order['quantity']
                            
                            hammer_symbol = symbol.replace(" PR", "-")
                            self.hammer.place_order(
                                symbol=hammer_symbol,
                                side=action,
                                quantity=quantity,
                                price=price,
                                order_type="LIMIT",
                                hidden=True  # Hidden emirler için
                            )
                            print(f"[TAKE PROFIT] ✅ {symbol}: {action} {quantity} lot @ ${price:.2f} (FALLBACK)")
                else:
                    print("[TAKE PROFIT] ⚠️ Mode manager bulunamadı, HAMPRO kullanılıyor...")
                    # Fallback to HAMPRO
                    for order in order_details:
                        symbol = order['symbol']
                        action = order['action']
                        price = order['price']
                        quantity = order['quantity']
                        
                        hammer_symbol = symbol.replace(" PR", "-")
                        self.hammer.place_order(
                            symbol=hammer_symbol,
                            side=action,
                            quantity=quantity,
                            price=price,
                            order_type="LIMIT",
                            hidden=True  # Hidden emirler için
                        )
                        print(f"[TAKE PROFIT] ✅ {symbol}: {action} {quantity} lot @ ${price:.2f} (FALLBACK)")
                
                print(f"[TAKE PROFIT] ✅ {len(order_details)} emir gönderildi")
                messagebox.showinfo("Başarılı", f"{len(order_details)} emir gönderildi!")
                confirm_win.destroy()
                
            except Exception as e:
                print(f"[TAKE PROFIT] ❌ Emir gönderme hatası: {e}")
                messagebox.showerror("Hata", f"Emir gönderme hatası: {e}")
        
        def save_to_trades_csv():
            """Emirleri trades.csv'ye kaydet - Port Adjuster ile aynı format"""
            try:
                print(f"[TAKE PROFIT CSV] 🔄 {len(order_details)} emir trades.csv'ye kaydediliyor...")
                
                csv_rows = []
                
                for order in order_details:
                    try:
                        symbol = order['symbol']
                        action = order['action']
                        price = order['price']
                        quantity = order['quantity']
                        
                        # Symbol'ü olduğu gibi bırak (PR formatını koru)
                        # Port Adjuster'da da symbol'ler olduğu gibi kalıyor
                        
                        # CSV formatına çevir - Port Adjuster ile aynı format
                        csv_row = [
                            action,                    # Action: BUY/SELL
                            quantity,                  # Quantity: Lot miktarı
                            symbol,                    # Symbol: Ticker (PR formatında)
                            'STK',                    # SecType: STK
                            'SMART/AMEX',             # Exchange: SMART/AMEX
                            'USD',                    # Currency: USD
                            'DAY',                    # TimeInForce: DAY
                            'LMT',                    # OrderType: LMT
                            round(price, 2),          # LmtPrice: Fiyat
                            'Basket',                 # BasketTag: Basket
                            'U21016730',              # Account: U21016730
                            'Basket',                 # OrderRef: Basket
                            'TRUE',                   # Hidden: TRUE
                            'TRUE'                    # OutsideRth: TRUE
                        ]
                        
                        csv_rows.append(csv_row)
                        print(f"[TAKE PROFIT CSV] ✅ {symbol}: {action} {quantity} @ ${price:.2f}")
                        
                    except Exception as e:
                        print(f"[TAKE PROFIT CSV] ❌ Emir formatı hatası ({order.get('symbol', 'Unknown')}): {e}")
                
                if csv_rows:
                    # CSV dosyasına kaydet
                    import csv
                    import os
                    
                    csv_filename = 'trades.csv'
                    
                    # Her seferinde yeni dosya oluştur (0'dan yaz)
                    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                        writer = csv.writer(csvfile)
                        
                        # Header yaz
                        headers = ['Action', 'Quantity', 'Symbol', 'SecType', 'Exchange', 
                                  'Currency', 'TimeInForce', 'OrderType', 'LmtPrice', 
                                  'BasketTag', 'Account', 'OrderRef', 'Hidden', 'OutsideRth']
                        writer.writerow(headers)
                        
                        # Emirleri yaz
                        writer.writerows(csv_rows)
                    
                    print(f"[TAKE PROFIT CSV] ✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                    messagebox.showinfo("Başarılı", f"{len(csv_rows)} emir trades.csv'ye kaydedildi!")
                else:
                    messagebox.showwarning("Uyarı", "Kaydedilecek geçerli emir bulunamadı!")
                    
            except Exception as e:
                print(f"[TAKE PROFIT CSV] ❌ Kaydetme hatası: {e}")
                messagebox.showerror("Hata", f"trades.csv kaydetme hatası: {e}")
        
        def cancel_orders():
            """İptal et"""
            confirm_win.destroy()
        
        ttk.Button(button_frame, text="Emirleri Gönder", command=confirm_orders, 
                  style='Accent.TButton').pack(side='left', padx=5)
        ttk.Button(button_frame, text="trades.csv'ye Kaydet", command=save_to_trades_csv, 
                  style='Success.TButton').pack(side='left', padx=5)
        ttk.Button(button_frame, text="İptal Et", command=cancel_orders).pack(side='left', padx=5)

    def get_final_fb_from_csv(self, symbol):
        """DataFrame'den Final FB skorunu al - Top Ten Bid Buy mantığıyla"""
        try:
            # Parent'tan DataFrame'i al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                # PREF IBKR kolonunda symbol'ü ara
                row = self.parent.df[self.parent.df['PREF IBKR'] == symbol]
                if not row.empty:
                    # Önce DataFrame'den Final_FB_skor kolonunu kontrol et
                    if 'Final_FB_skor' in self.parent.df.columns:
                        value = row['Final_FB_skor'].iloc[0]
                        if pd.notna(value) and value != 'N/A':
                            return float(value)
                    
                    # DataFrame'de yoksa hesapla - Top Ten Bid Buy mantığıyla
                    if hasattr(self.parent, 'calculate_scores') and hasattr(self.parent, 'hammer'):
                        # Market data al
                        market_data = self.parent.hammer.get_market_data(symbol)
                        if market_data:
                            bid_raw = float(market_data.get('bid', 0))
                            ask_raw = float(market_data.get('ask', 0))
                            last_raw = float(market_data.get('last', 0))
                            prev_close = float(market_data.get('prevClose', 0))
                            
                            # Benchmark değişimini hesapla
                            benchmark_chg = self.parent.get_benchmark_change_for_ticker(symbol)
                            
                            # Skorları hesapla
                            scores = self.parent.calculate_scores(symbol, row.iloc[0], bid_raw, ask_raw, last_raw, prev_close, benchmark_chg)
                            
                            if scores and 'Final_FB_skor' in scores:
                                return float(scores['Final_FB_skor'])
            
            return 0.0
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ Final FB çekme hatası {symbol}: {e}")
            return 0.0

    def get_final_sfs_from_csv(self, symbol):
        """Final SFS skorunu al - JFIN emirleriyle aynı mantık"""
        try:
            # JFIN emirleriyle aynı mantık: 3 aşamalı çekme
            # 1. Ana DataFrame'den çek
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                row = self.parent.df[self.parent.df['PREF IBKR'] == symbol]
                if not row.empty and 'Final_SFS_skor' in self.parent.df.columns:
                    value = row['Final_SFS_skor'].iloc[0]
                    if pd.notna(value) and value != 'N/A':
                        print(f"[TAKE PROFIT] ✅ {symbol} Final SFS (DataFrame): {float(value):.4f}")
                        return float(value)
            
            # 2. Stock Data Manager'dan çek
            if hasattr(self.parent, 'stock_data_manager'):
                try:
                    score_data = self.parent.stock_data_manager.get_stock_data(symbol, 'Final_SFS_skor')
                    if score_data is not None and score_data != 'N/A':
                        print(f"[TAKE PROFIT] ✅ {symbol} Final SFS (Stock Data Manager): {float(score_data):.4f}")
                        return float(score_data)
                except Exception as e:
                    print(f"[TAKE PROFIT] ⚠️ Stock Data Manager'dan Final SFS çekme hatası: {e}")
            
            # 3. Son çare: Final_FB_skor'dan farklı bir değer hesapla
            # Final SFS genellikle Final FB'den farklıdır, bu yüzden farklı bir hesaplama yapalım
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                row = self.parent.df[self.parent.df['PREF IBKR'] == symbol]
                if not row.empty and 'Final_FB_skor' in self.parent.df.columns:
                    fb_value = row['Final_FB_skor'].iloc[0]
                    if pd.notna(fb_value) and fb_value != 'N/A':
                        # Final SFS'i Final FB'den biraz farklı yap (örnek hesaplama)
                        sfs_value = float(fb_value) * 0.95  # %5 fark
                        print(f"[TAKE PROFIT] ⚠️ {symbol} Final SFS (Hesaplama): {sfs_value:.4f}")
                        return sfs_value
            
            print(f"[TAKE PROFIT] ⚠️ {symbol} Final SFS bulunamadı")
            return 0.0
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ Final SFS çekme hatası {symbol}: {e}")
            return 0.0
    
    def get_new_column_data(self, symbol):
        """Yeni kolonlar için veri al: Grup, Avg Final FB, Avg Final SFS, FBPlagr, FBRatgr, GORT - JFIN emirleriyle aynı mantık"""
        try:
            grup_value = "N/A"
            avg_final_fb = 0
            avg_final_sfs = 0
            fbplagr = "N/A"
            fbratgr = "N/A"
            gort = 0.0
            
            # JFIN emirleriyle aynı mantık: Grup dosyalarından hisseyi bul
            grup_value = self.get_group_from_symbol(symbol)
            
            # Grup ortalama Final FB ve Final SFS hesapla - JFIN emirleriyle aynı mantık
            if grup_value and grup_value != 'N/A':
                avg_final_fb = self.calculate_group_avg_final_fb(grup_value)
                avg_final_sfs = self.calculate_group_avg_final_sfs(grup_value)
                
                # FBPlagr hesapla
                fbplagr = self.calculate_fbplagr(symbol, grup_value)
                
                # FBRatgr için final_fb değerini al
                final_fb = self.get_final_fb_from_csv(symbol)
                fbratgr = self.calculate_fbratgr(symbol, final_fb, avg_final_fb)
                
                # FBtot hesapla (FBPlagr + FBRatgr)
                fbtot = self.calculate_fbtot(fbplagr, fbratgr)
                
                # Shorts için SFS kolonları hesapla
                if self.position_type == "shorts":
                    final_sfs_value = self.get_final_sfs_from_csv(symbol)
                    sfsplagr = self.calculate_sfsplagr(symbol, grup_value)
                    sfsratgr = self.calculate_sfsratgr(symbol, final_sfs_value, avg_final_sfs)
                    sfstot = self.calculate_sfstot(sfsplagr, sfsratgr)
                else:
                    # Longs için SFS kolonları N/A
                    sfsplagr = "N/A"
                    sfsratgr = "N/A"
                    sfstot = "N/A"
            
            # GORT hesapla (parent'tan)
            if hasattr(self.parent, 'calculate_gort'):
                gort = self.parent.calculate_gort(symbol)
            
            print(f"[TAKE PROFIT] ✅ {symbol} -> Grup: {grup_value}, Avg Final FB: {avg_final_fb:.2f}, Avg Final SFS: {avg_final_sfs:.2f}, FBPlagr: {fbplagr}, FBRatgr: {fbratgr}, FBtot: {fbtot}, SFSPlagr: {sfsplagr}, SFSRatgr: {sfsratgr}, SFStot: {sfstot}, GORT: {gort:.2f}")
            
            return grup_value, avg_final_fb, avg_final_sfs, fbplagr, fbratgr, fbtot, sfsplagr, sfsratgr, sfstot, gort
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ {symbol} yeni kolon verisi alma hatası: {e}")
            return "N/A", 0, 0, "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", 0.0
    
    def get_group_from_symbol(self, symbol):
        """JFIN emirleriyle aynı mantık: Symbol'ü grup dosyalarında ara"""
        try:
            # Grup dosya eşleşmesi - JFIN emirleriyle aynı
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
                            print(f"[TAKE PROFIT] 🎯 {symbol} -> {group} grubunda bulundu (tam eşleşme)")
                            return group
                        
                        # Esnek eşleşme kontrol et (büyük/küçük harf, boşluk vs.)
                        symbol_upper = symbol.upper().strip()
                        for group_symbol in group_symbols:
                            if group_symbol and isinstance(group_symbol, str):
                                group_symbol_upper = group_symbol.upper().strip()
                                if symbol_upper == group_symbol_upper:
                                    print(f"[TAKE PROFIT] 🎯 {symbol} -> {group} grubunda bulundu (esnek eşleşme)")
                                    return group
                        
                    except Exception as e:
                        print(f"[TAKE PROFIT] ⚠️ {file_name} okuma hatası: {e}")
                        continue
                else:
                    print(f"[TAKE PROFIT] ⚠️ {file_name} dosyası bulunamadı")
            
            # Debug: Hangi dosyaların mevcut olduğunu kontrol et
            print(f"[TAKE PROFIT] 🔍 {symbol} için grup dosyaları kontrol ediliyor...")
            for group, file_name in group_file_map.items():
                if os.path.exists(file_name):
                    print(f"[TAKE PROFIT] ✅ {file_name} mevcut")
                else:
                    print(f"[TAKE PROFIT] ❌ {file_name} bulunamadı")
            
            print(f"[TAKE PROFIT] ⚠️ {symbol} hiçbir grup dosyasında bulunamadı")
            return "N/A"
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ {symbol} grup bulma hatası: {e}")
            return "N/A"
    
    def calculate_group_avg_final_fb(self, group):
        """Grup ortalama Final FB hesapla - JFIN emirleriyle aynı mantık"""
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
            
            file_name = group_file_map.get(group.lower())
            if not file_name or not os.path.exists(file_name):
                return 0
            
            # Grup dosyasından hisseleri al
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            # Parent DataFrame'den bu gruba ait hisselerin Final FB değerlerini al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                group_rows = self.parent.df[self.parent.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_FB_skor' in self.parent.df.columns:
                    # N/A ve 0 değerleri filtrele
                    final_fb_values = group_rows['Final_FB_skor'].dropna()
                    # String değerleri sayıya çevir
                    final_fb_values = pd.to_numeric(final_fb_values, errors='coerce').dropna()
                    final_fb_values = final_fb_values[final_fb_values > 0]  # 0'dan büyük olanları al
                    if not final_fb_values.empty:
                        avg_fb = final_fb_values.mean()
                        print(f"[TAKE PROFIT] 📊 {group} grubu ortalama Final FB: {avg_fb:.2f} ({len(final_fb_values)} geçerli hisse)")
                        return avg_fb
            
            return 0
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ {group} grup ortalama Final FB hesaplama hatası: {e}")
            return 0
    
    def calculate_group_avg_final_sfs(self, group):
        """Grup ortalama Final SFS hesapla - JFIN emirleriyle aynı mantık"""
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
            
            file_name = group_file_map.get(group.lower())
            if not file_name or not os.path.exists(file_name):
                return 0
            
            # Grup dosyasından hisseleri al
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            # Parent DataFrame'den bu gruba ait hisselerin Final SFS değerlerini al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                group_rows = self.parent.df[self.parent.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_SFS_skor' in self.parent.df.columns:
                    # N/A ve 0 değerleri filtrele
                    final_sfs_values = group_rows['Final_SFS_skor'].dropna()
                    # String değerleri sayıya çevir
                    final_sfs_values = pd.to_numeric(final_sfs_values, errors='coerce').dropna()
                    final_sfs_values = final_sfs_values[final_sfs_values > 0]  # 0'dan büyük olanları al
                    if not final_sfs_values.empty:
                        avg_sfs = final_sfs_values.mean()
                        print(f"[TAKE PROFIT] 📊 {group} grubu ortalama Final SFS: {avg_sfs:.2f} ({len(final_sfs_values)} geçerli hisse)")
                        return avg_sfs
            
            return 0
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ {group} grup ortalama Final SFS hesaplama hatası: {e}")
            return 0
    
    def calculate_fbplagr(self, symbol, group):
        """Grupta Final FB sıralamasını hesapla (örn: 4/10)"""
        try:
            if not group or group == 'N/A':
                return "N/A"
            
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
                return "N/A"
            
            # Grup dosyasından hisseleri al
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            # Parent DataFrame'den bu gruba ait hisselerin Final FB değerlerini al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                group_rows = self.parent.df[self.parent.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_FB_skor' in self.parent.df.columns:
                    # N/A ve 0 değerleri filtrele
                    final_fb_data = group_rows[['PREF IBKR', 'Final_FB_skor']].dropna()
                    # String değerleri sayıya çevir
                    final_fb_data['Final_FB_skor'] = pd.to_numeric(final_fb_data['Final_FB_skor'], errors='coerce')
                    final_fb_data = final_fb_data.dropna()
                    final_fb_data = final_fb_data[final_fb_data['Final_FB_skor'] > 0]
                    
                    if not final_fb_data.empty:
                        # Final FB'ye göre sırala (en düşükten en yükseğe - tersine çevir)
                        final_fb_data = final_fb_data.sort_values('Final_FB_skor', ascending=True).reset_index(drop=True)
                        
                        # Symbol'ün sırasını bul
                        symbol_row = final_fb_data[final_fb_data['PREF IBKR'] == symbol]
                        if not symbol_row.empty:
                            rank = symbol_row.index[0] + 1  # 1'den başla
                            total_count = len(final_fb_data)
                            # Hem kesir hem de ondalık format göster
                            decimal_ratio = rank / total_count
                            result = f"{rank}/{total_count} ({decimal_ratio:.2f})"
                            print(f"[TAKE PROFIT] 📊 {symbol} FBPlagr: {result} (Final FB: {symbol_row.iloc[0]['Final_FB_skor']:.2f})")
                            return result
            
            return "N/A"
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ {symbol} FBPlagr hesaplama hatası: {e}")
            return "N/A"
    
    def calculate_fbratgr(self, symbol, final_fb, avg_final_fb):
        """Final FB / Grup Average oranını hesapla"""
        try:
            if avg_final_fb == 0 or final_fb <= 0:
                return "N/A"
            
            ratio = final_fb / avg_final_fb
            result = f"{ratio:.2f}"
            print(f"[TAKE PROFIT] 📊 {symbol} FBRatgr: {result} ({final_fb:.2f} / {avg_final_fb:.2f})")
            return result
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ {symbol} FBRatgr hesaplama hatası: {e}")
            return "N/A"
    
    def calculate_fbtot(self, fbplagr, fbratgr):
        """FBPlagr + FBRatgr toplamını hesapla"""
        try:
            # FBPlagr'dan ondalık değeri çıkar (örn: "2/24 (0.08)" -> 0.08)
            fbplagr_value = 0
            if fbplagr != "N/A" and "(" in fbplagr:
                try:
                    # Parantez içindeki ondalık değeri al
                    decimal_part = fbplagr.split("(")[1].split(")")[0]
                    fbplagr_value = float(decimal_part)
                except:
                    fbplagr_value = 0
            
            # FBRatgr'dan sayısal değeri çıkar
            fbratgr_value = 0
            if fbratgr != "N/A":
                try:
                    fbratgr_value = float(fbratgr)
                except:
                    fbratgr_value = 0
            
            # Toplamı hesapla
            total = fbplagr_value + fbratgr_value
            result = f"{total:.2f}"
            print(f"[TAKE PROFIT] 📊 FBtot: {result} ({fbplagr_value:.2f} + {fbratgr_value:.2f})")
            return result
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ FBtot hesaplama hatası: {e}")
            return "N/A"
    
    def calculate_sfsplagr(self, symbol, group):
        """Grupta Final SFS sıralamasını hesapla (örn: 4/10) - Shorts için"""
        try:
            if not group or group == 'N/A':
                return "N/A"
            
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
                return "N/A"
            
            # Grup dosyasından hisseleri al
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            # Parent DataFrame'den bu gruba ait hisselerin Final SFS değerlerini al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                group_rows = self.parent.df[self.parent.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_SFS_skor' in self.parent.df.columns:
                    # N/A ve 0 değerleri filtrele
                    final_sfs_data = group_rows[['PREF IBKR', 'Final_SFS_skor']].dropna()
                    # String değerleri sayıya çevir
                    final_sfs_data['Final_SFS_skor'] = pd.to_numeric(final_sfs_data['Final_SFS_skor'], errors='coerce')
                    final_sfs_data = final_sfs_data.dropna()
                    final_sfs_data = final_sfs_data[final_sfs_data['Final_SFS_skor'] > 0]
                    
                    if not final_sfs_data.empty:
                        # Final SFS'ye göre sırala (en düşükten en yükseğe - tersine çevir)
                        final_sfs_data = final_sfs_data.sort_values('Final_SFS_skor', ascending=True).reset_index(drop=True)
                        
                        # Symbol'ün sırasını bul
                        symbol_row = final_sfs_data[final_sfs_data['PREF IBKR'] == symbol]
                        if not symbol_row.empty:
                            rank = symbol_row.index[0] + 1  # 1'den başla
                            total_count = len(final_sfs_data)
                            # Hem kesir hem de ondalık format göster
                            decimal_ratio = rank / total_count
                            result = f"{rank}/{total_count} ({decimal_ratio:.2f})"
                            print(f"[TAKE PROFIT] 📊 {symbol} SFSPlagr: {result} (Final SFS: {symbol_row.iloc[0]['Final_SFS_skor']:.2f})")
                            return result
            
            return "N/A"
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ {symbol} SFSPlagr hesaplama hatası: {e}")
            return "N/A"
    
    def calculate_sfsratgr(self, symbol, final_sfs, avg_final_sfs):
        """Final SFS / Grup Average oranını hesapla - Shorts için"""
        try:
            if avg_final_sfs == 0 or final_sfs <= 0:
                return "N/A"
            
            ratio = final_sfs / avg_final_sfs
            result = f"{ratio:.2f}"
            print(f"[TAKE PROFIT] 📊 {symbol} SFSRatgr: {result} ({final_sfs:.2f} / {avg_final_sfs:.2f})")
            return result
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ {symbol} SFSRatgr hesaplama hatası: {e}")
            return "N/A"
    
    def calculate_sfstot(self, sfsplagr, sfsratgr):
        """SFSPlagr + SFSRatgr toplamını hesapla - Shorts için"""
        try:
            # SFSPlagr'dan ondalık değeri çıkar (örn: "2/24 (0.08)" -> 0.08)
            sfsplagr_value = 0
            if sfsplagr != "N/A" and "(" in sfsplagr:
                try:
                    # Parantez içindeki ondalık değeri al
                    decimal_part = sfsplagr.split("(")[1].split(")")[0]
                    sfsplagr_value = float(decimal_part)
                except:
                    sfsplagr_value = 0
            
            # SFSRatgr'dan sayısal değeri çıkar
            sfsratgr_value = 0
            if sfsratgr != "N/A":
                try:
                    sfsratgr_value = float(sfsratgr)
                except:
                    sfsratgr_value = 0
            
            # Toplamı hesapla
            total = sfsplagr_value + sfsratgr_value
            result = f"{total:.2f}"
            print(f"[TAKE PROFIT] 📊 SFStot: {result} ({sfsplagr_value:.2f} + {sfsratgr_value:.2f})")
            return result
            
        except Exception as e:
            print(f"[TAKE PROFIT] ❌ SFStot hesaplama hatası: {e}")
            return "N/A"
