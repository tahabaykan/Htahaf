"""
FINAL THG Tabanlı Lot Dağıtıcı
JANALLRES uygulamasında Port Adjuster'a entegre edilecek

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janallres/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Örnek:
✅ DOĞRU: "ssfinekheldff.csv" (StockTracker dizininde)
❌ YANLIŞ: "janallresres/ssfinekheldff.csv"
=================================
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import numpy as np
import os
import glob
import math

class FinalThgLotDistributor:
    def __init__(self, parent):
        self.parent = parent
        
        # ✅ ANA SAYFA REFERANSI EKLENDİ!
        # main_window'a erişim için parent'ı takip et
        self.main_window = None
        if hasattr(parent, 'main_window'):
            self.main_window = parent.main_window
        elif hasattr(parent, 'master') and hasattr(parent.master, 'main_window'):
            self.main_window = parent.master.main_window
        elif hasattr(parent, 'winfo_toplevel'):
            # Toplevel'den main_window'u bul
            toplevel = parent.winfo_toplevel()
            if hasattr(toplevel, 'main_window'):
                self.main_window = toplevel.main_window
    
        print(f"[3. STEP] 🔍 Ana sayfa referansı aranıyor...")
        if self.main_window:
            print(f"[3. STEP] ✅ Ana sayfa referansı bulundu: {type(self.main_window).__name__}")
            if hasattr(self.main_window, 'hammer'):
                print(f"[3. STEP] ✅ Hammer Pro referansı bulundu")
            else:
                print(f"[3. STEP] ⚠️ Hammer Pro referansı bulunamadı")
        else:
            print(f"[3. STEP] ❌ Ana sayfa referansı bulunamadı!")
        
        # Ana pencere - parent Port Adjuster ise onun window'unu kullan
        if hasattr(parent, 'win'):
            # Port Adjuster objesi geçilmiş
            self.port_adjuster = parent  # ✅ Port Adjuster objesini sakla!
            parent_window = parent.win
            print(f"[3. STEP] ✅ Port Adjuster objesi geçildi ve saklandı")
        else:
            # Doğrudan window geçilmiş
            self.port_adjuster = None  # Port Adjuster yok
            parent_window = parent
            print(f"[3. STEP] ⚠️ Doğrudan window geçildi, Port Adjuster yok")
        
        self.win = tk.Toplevel(parent_window)
        self.win.title("Final FB & SFS Lot Dağıtıcı - 3. Step")
        self.win.geometry("1600x900")
        self.win.transient(parent_window)
        # grab_set() kaldırıldı - minimize edilebilir olması için
        
        # Grup dosyaları
        self.group_files = {
            'HELDFF': 'ssfinekheldff.csv',
            'DEZNFF': 'ssfinekhelddeznff.csv', 
            'HELDKUPONLU': 'ssfinekheldkuponlu.csv',
            'HELDNFF': 'ssfinekheldnff.csv',
            'HELDFLR': 'ssfinekheldflr.csv',
            'HELDGARABETALTIYEDI': 'ssfinekheldgarabetaltiyedi.csv',
            'HELDKUPONLUKRECILIZ': 'ssfinekheldkuponlukreciliz.csv',
            'HELDKUPONLUKREORTA': 'ssfinekheldkuponlukreorta.csv',
            'HELDOTELREMORTA': 'ssfinekheldotelremorta.csv',
            'HELDSOLIDBIG': 'ssfinekheldsolidbig.csv',
            'HELDTITREKHC': 'ssfinekheldtitrekhc.csv',
            'HIGHMATUR': 'ssfinekhighmatur.csv',
            'NOTBESMATURLU': 'ssfineknotbesmaturlu.csv',
            'NOTCEFILLIQUID': 'ssfineknotcefilliquid.csv',
            'NOTTITREKHC': 'ssfineknotcefilliquid.csv',
            'RUMOREDDANGER': 'ssfinekrumoreddanger.csv',
            'SALAKILLIQUID': 'ssfineksalakilliquid.csv',
            'SHITREMHC': 'ssfinekshitremhc.csv'
        }
        
        # Grup ağırlıkları (Port Adjuster'dan gelecek)
        self.group_weights = {}
        
        # Toplam lot hakkı
        self.total_lot_rights = 0
        
        # Exposure Adjuster değerleri
        self.total_exposure = 1000000  # 1M USD
        self.avg_price = 25.0  # 25 USD
        
        # Long/Short lot hakları - exposureadjuster.csv'den yükle
        self.load_lot_rights_from_csv()
        
        print(f"🔍 BAŞLANGIÇ LOT HAKLARI:")
        print(f"   📊 Long: {self.long_lot_rights:,}")
        print(f"   📊 Short: {self.short_lot_rights:,}")
        
        # UI'daki toplam lot hakkını setup_ui'dan sonra güncelleyeceğiz
        
        # Alpha değeri
        self.alpha = 3
        
        # NTUMCSVPORT kurallarını ekle
        self.file_rules = self.get_file_specific_rules()
        
        # Stock Data Manager referansı
        self.stock_data_manager = None
        if self.main_window and hasattr(self.main_window, 'stock_data_manager'):
            self.stock_data_manager = self.main_window.stock_data_manager
            print(f"[3. STEP] ✅ Stock Data Manager referansı alındı")
        else:
            print(f"[3. STEP] ⚠️ Stock Data Manager referansı bulunamadı")
        
        self.setup_ui()
        
        # UI oluştuktan sonra CSV'den yüklenen lot haklarını göster
        self.total_lot_label.config(text=f"Long: {self.long_lot_rights:,} | Short: {self.short_lot_rights:,}")
    
    def check_soft_front_buy_conditions(self, bid, ask, last_print, symbol=None):
        """SoftFront Buy koşullarını kontrol et - LRPAN fiyatı ile"""
        if bid <= 0 or ask <= 0 or last_print <= 0:
            return False
        
        spread = ask - bid
        if spread <= 0:
            return False
        
        # LRPAN fiyatını al (gerçek print fiyatı)
        lrpan_price = None
        if symbol:
            lrpan_price = self.get_lrpan_price(symbol)
        
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
    
    def check_soft_front_sell_conditions(self, bid, ask, last_print, symbol=None):
        """SoftFront Sell koşullarını kontrol et - LRPAN fiyatı ile"""
        if bid <= 0 or ask <= 0 or last_print <= 0:
            return False
        
        spread = ask - bid
        if spread <= 0:
            return False
        
        # LRPAN fiyatını al (gerçek print fiyatı)
        lrpan_price = None
        if symbol:
            lrpan_price = self.get_lrpan_price(symbol)
        
        if lrpan_price is None:
            # LRPAN fiyatı bulunamazsa last_print kullan
            print(f"[SOFT FRONT SELL] ⚠️ LRPAN fiyatı bulunamadı, last_print kullanılıyor: ${last_print:.2f}")
            real_print_price = last_print
        else:
            # LRPAN fiyatını kullan
            real_print_price = lrpan_price
            print(f"[SOFT FRONT SELL] ✅ LRPAN fiyatı kullanılıyor: ${real_print_price:.2f}")
        
        # Koşul 1: %60 kuralı - (real_print_price - bid) / (ask - bid) > 0.60
        condition1 = (real_print_price - bid) / spread > 0.60
        
        # Koşul 2: 0.15 cent kuralı - (real_print_price - bid) >= 0.15
        condition2 = (real_print_price - bid) >= 0.15
        
        print(f"[SOFT FRONT SELL] 🔍 Koşul 1: {(real_print_price - bid) / spread:.2f} > 0.60 = {condition1}")
        print(f"[SOFT FRONT SELL] 🔍 Koşul 2: {(real_print_price - bid):.2f} >= 0.15 = {condition2}")
        
        # En az bir koşul sağlanmalı
        return condition1 or condition2
    
    def convert_symbol_to_hammer_format(self, symbol):
        """PREF IBKR formatındaki symbol'ü Hammer Pro formatına çevir"""
        # Eğer zaten Hammer Pro formatındaysa (örn: "EQH-C", "PSA-P") olduğu gibi döndür
        if "-" in symbol and len(symbol.split("-")) == 2:
            return symbol
        
        # Örnek: "EQH PRA" -> "EQH-A", "USB PRH" -> "USB-H"
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
        
        # Sekme başlıklarını da hemen güncelle
        self.bb_long_lot_info.config(text=f"BB Long ({self.long_lot_rights:,} lot/sekme) - Hazır")
        self.fb_long_lot_info.config(text=f"FB Long ({self.long_lot_rights:,} lot/sekme) - Hazır")
        self.sas_short_lot_info.config(text=f"SAS Short ({self.short_lot_rights:,} lot/sekme) - Hazır")
        self.sfs_short_lot_info.config(text=f"SFS Short ({self.short_lot_rights:,} lot/sekme) - Hazır")
        
        print(f"✅ UI'da lot hakları güncellendi: Long: {self.long_lot_rights:,} | Short: {self.short_lot_rights:,}")
        print(f"✅ Sekme başlıkları güncellendi!")
    
    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        # Başlık frame - minimize butonu ile
        title_frame = ttk.Frame(self.win)
        title_frame.pack(fill='x', padx=5, pady=5)
        
        # Başlık
        title_label = ttk.Label(title_frame, text="Final FB & SFS Tabanlı Lot Dağıtıcı - 3. Step", 
                               font=("Arial", 14, "bold"))
        title_label.pack(side='left')
        
        # Pencere kontrol butonları (sağ üst)
        window_controls = ttk.Frame(title_frame)
        window_controls.pack(side='right')
        
        # Alta Al (Minimize) butonu
        minimize_btn = ttk.Button(window_controls, text="🗕 Alta Al", width=10,
                                  command=lambda: self.win.iconify())
        minimize_btn.pack(side='left', padx=2)
        
        # Üst butonlar
        button_frame = ttk.Frame(self.win)
        button_frame.pack(pady=5)
        
        # Grup ağırlıklarını yükle butonu
        load_weights_btn = ttk.Button(button_frame, text="Grup Ağırlıklarını Yükle", 
                                     command=self.load_group_weights)
        load_weights_btn.pack(side='left', padx=5)
        
        # TUMCSV Ayarlaması Yap butonu
        tumcsv_btn = ttk.Button(button_frame, text="TUMCSV Ayarlaması Yap", 
                                command=self.apply_tumcsv_rules, 
                                style='Accent.TButton')
        tumcsv_btn.pack(side='left', padx=5)
        
        # Lot dağılımını hesapla butonu
        calculate_btn = ttk.Button(button_frame, text="Lot Dağılımını Hesapla", 
                                  command=self.calculate_lot_distribution)
        calculate_btn.pack(side='left', padx=5)
        
        # Sonuçları kaydet butonu
        save_btn = ttk.Button(button_frame, text="Sonuçları Kaydet", 
                             command=self.save_results)
        save_btn.pack(side='left', padx=5)
        
        # Kapat butonu
        close_btn = ttk.Button(button_frame, text="Kapat", command=self.win.destroy)
        close_btn.pack(side='left', padx=5)
        
        # Ana frame
        main_frame = ttk.Frame(self.win)
        main_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Sol taraf - Grup ağırlıkları
        left_frame = ttk.LabelFrame(main_frame, text="Grup Ağırlıkları ve Lot Hakları", padding=10)
        left_frame.pack(side='left', fill='y', padx=(0, 5))
        
        # Sağ panel - Sonuçlar
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side='right', fill='both', expand=True, padx=(10, 0))
        
        # Sonuçlar başlığı
        results_label = ttk.Label(right_frame, text="Final FB & SFS Lot Dağılımı Sonuçları", 
                                 font=("Arial", 12, "bold"))
        results_label.pack(pady=5)
        
        # Tab kontrolü - 4 sekme: BB Long, FB Long, SAS Short, SFS Short
        notebook = ttk.Notebook(right_frame)
        notebook.pack(fill='both', expand=True)
        
        # 1. BB Long tab (Final_BB_skor kullanarak Long seçimi)
        bb_long_frame = ttk.Frame(notebook)
        notebook.add(bb_long_frame, text="BB Long")
        
        # BB Long lot durumu etiketi
        self.bb_long_lot_info = tk.Label(bb_long_frame, text="BB Long - Lot durumu hesaplanıyor...",
                                        font=('Arial', 10, 'bold'), bg='lightblue', pady=5)
        self.bb_long_lot_info.pack(fill='x', padx=5, pady=5)

        # BB Long SMA63 chg filtresi
        bb_filter_frame = ttk.Frame(bb_long_frame)
        bb_filter_frame.pack(fill='x', padx=5, pady=2)

        ttk.Label(bb_filter_frame, text="SMA63 chg Filtresi:", font=("Arial", 9, "bold")).pack(side='left')
        self.bb_sma_filter_var = tk.StringVar()
        self.bb_sma_filter_entry = ttk.Entry(bb_filter_frame, textvariable=self.bb_sma_filter_var, width=8)
        self.bb_sma_filter_entry.pack(side='left', padx=2)

        self.bb_filter_type = tk.StringVar(value="below")
        ttk.Radiobutton(bb_filter_frame, text="Below", variable=self.bb_filter_type, value="below",
                        command=self.apply_bb_filter).pack(side='left', padx=2)
        ttk.Radiobutton(bb_filter_frame, text="Above", variable=self.bb_filter_type, value="above",
                        command=self.apply_bb_filter).pack(side='left', padx=2)

        ttk.Button(bb_filter_frame, text="Uygula", command=self.apply_bb_filter).pack(side='left', padx=5)
        ttk.Button(bb_filter_frame, text="Filtreleri Kaldır", command=self.clear_all_filters).pack(side='left', padx=5)
        
        # BB Long FBtot filtresi
        bb_fbtot_filter_frame = ttk.Frame(bb_long_frame)
        bb_fbtot_filter_frame.pack(fill='x', padx=5, pady=2)

        ttk.Label(bb_fbtot_filter_frame, text="FBtot Filtresi:", font=("Arial", 9, "bold")).pack(side='left')
        self.bb_fbtot_filter_var = tk.StringVar()
        self.bb_fbtot_filter_entry = ttk.Entry(bb_fbtot_filter_frame, textvariable=self.bb_fbtot_filter_var, width=8)
        self.bb_fbtot_filter_entry.pack(side='left', padx=2)

        self.bb_fbtot_filter_type = tk.StringVar(value="below")
        ttk.Radiobutton(bb_fbtot_filter_frame, text="Below", variable=self.bb_fbtot_filter_type, value="below",
                        command=self.apply_bb_filter).pack(side='left', padx=2)
        ttk.Radiobutton(bb_fbtot_filter_frame, text="Above", variable=self.bb_fbtot_filter_type, value="above",
                        command=self.apply_bb_filter).pack(side='left', padx=2)
        
        # JFIN BB butonları
        jfin_bb_frame = ttk.Frame(bb_long_frame)
        jfin_bb_frame.pack(fill='x', padx=5, pady=2)
        
        ttk.Label(jfin_bb_frame, text="JFIN BB Emirleri:", font=("Arial", 9, "bold")).pack(side='left')
        
        ttk.Button(jfin_bb_frame, text="JFIN %25 BB", 
                  command=lambda: self.show_jfin_orders('BB', 25)).pack(side='left', padx=2)
        ttk.Button(jfin_bb_frame, text="JFIN %50 BB", 
                  command=lambda: self.show_jfin_orders('BB', 50)).pack(side='left', padx=2)
        ttk.Button(jfin_bb_frame, text="JFIN %75 BB", 
                  command=lambda: self.show_jfin_orders('BB', 75)).pack(side='left', padx=2)
        ttk.Button(jfin_bb_frame, text="JFIN %100 BB", 
                  command=lambda: self.show_jfin_orders('BB', 100)).pack(side='left', padx=2)
        
        # SoftFront Buy butonları
        ttk.Button(jfin_bb_frame, text="JFIN %25 SoftFB", 
                  command=lambda: self.show_jfin_orders('SoftFB', 25)).pack(side='left', padx=2)
        ttk.Button(jfin_bb_frame, text="JFIN %50 SoftFB", 
                  command=lambda: self.show_jfin_orders('SoftFB', 50)).pack(side='left', padx=2)
        ttk.Button(jfin_bb_frame, text="JFIN %75 SoftFB", 
                  command=lambda: self.show_jfin_orders('SoftFB', 75)).pack(side='left', padx=2)
        ttk.Button(jfin_bb_frame, text="JFIN %100 SoftFB", 
                  command=lambda: self.show_jfin_orders('SoftFB', 100)).pack(side='left', padx=2)
        
        bb_long_columns = ('Grup', 'Sembol', 'Final_BB_skor', 'Final_SFS_skor', 'FBtot', 'SMI', 'SMA63 chg', 'GORT', 'MAXALW', 'Mevcut Pozisyon', 'Hesaplanan Lot', 'Eklenebilir Lot')
        self.bb_long_tree = ttk.Treeview(bb_long_frame, columns=bb_long_columns, show='headings', height=15)
        
        # BB Long kolon başlıkları
        for col in bb_long_columns:
            self.bb_long_tree.heading(col, text=col)
            if col in ['Grup', 'Sembol']:
                self.bb_long_tree.column(col, width=120 if col == 'Grup' else 100)
            elif 'skor' in col:
                self.bb_long_tree.column(col, width=120)
            elif col == 'GORT':
                self.bb_long_tree.column(col, width=80)
            else:
                self.bb_long_tree.column(col, width=80)
        
        bb_long_scrollbar = ttk.Scrollbar(bb_long_frame, orient='vertical', command=self.bb_long_tree.yview)
        self.bb_long_tree.configure(yscrollcommand=bb_long_scrollbar.set)
        self.bb_long_tree.pack(side='left', fill='both', expand=True)
        bb_long_scrollbar.pack(side='right', fill='y')
        
        # 2. FB Long tab (Final_FB_skor kullanarak Long seçimi)
        fb_long_frame = ttk.Frame(notebook)
        notebook.add(fb_long_frame, text="FB Long")
        
        # FB Long lot durumu etiketi
        self.fb_long_lot_info = tk.Label(fb_long_frame, text="FB Long - Lot durumu hesaplanıyor...",
                                        font=('Arial', 10, 'bold'), bg='lightgreen', pady=5)
        self.fb_long_lot_info.pack(fill='x', padx=5, pady=5)

        # FB Long SMA63 chg filtresi
        fb_filter_frame = ttk.Frame(fb_long_frame)
        fb_filter_frame.pack(fill='x', padx=5, pady=2)

        ttk.Label(fb_filter_frame, text="SMA63 chg Filtresi:", font=("Arial", 9, "bold")).pack(side='left')
        self.fb_sma_filter_var = tk.StringVar()
        self.fb_sma_filter_entry = ttk.Entry(fb_filter_frame, textvariable=self.fb_sma_filter_var, width=8)
        self.fb_sma_filter_entry.pack(side='left', padx=2)

        self.fb_filter_type = tk.StringVar(value="below")
        ttk.Radiobutton(fb_filter_frame, text="Below", variable=self.fb_filter_type, value="below",
                        command=self.apply_fb_filter).pack(side='left', padx=2)
        ttk.Radiobutton(fb_filter_frame, text="Above", variable=self.fb_filter_type, value="above",
                        command=self.apply_fb_filter).pack(side='left', padx=2)

        ttk.Button(fb_filter_frame, text="Uygula", command=self.apply_fb_filter).pack(side='left', padx=5)
        ttk.Button(fb_filter_frame, text="Filtreleri Kaldır", command=self.clear_all_filters).pack(side='left', padx=5)
        
        # FB Long FBtot filtresi
        fb_fbtot_filter_frame = ttk.Frame(fb_long_frame)
        fb_fbtot_filter_frame.pack(fill='x', padx=5, pady=2)

        ttk.Label(fb_fbtot_filter_frame, text="FBtot Filtresi:", font=("Arial", 9, "bold")).pack(side='left')
        self.fb_fbtot_filter_var = tk.StringVar()
        self.fb_fbtot_filter_entry = ttk.Entry(fb_fbtot_filter_frame, textvariable=self.fb_fbtot_filter_var, width=8)
        self.fb_fbtot_filter_entry.pack(side='left', padx=2)

        self.fb_fbtot_filter_type = tk.StringVar(value="below")
        ttk.Radiobutton(fb_fbtot_filter_frame, text="Below", variable=self.fb_fbtot_filter_type, value="below",
                        command=self.apply_fb_filter).pack(side='left', padx=2)
        ttk.Radiobutton(fb_fbtot_filter_frame, text="Above", variable=self.fb_fbtot_filter_type, value="above",
                        command=self.apply_fb_filter).pack(side='left', padx=2)
        
        # JFIN FB butonları
        jfin_fb_frame = ttk.Frame(fb_long_frame)
        jfin_fb_frame.pack(fill='x', padx=5, pady=2)
        
        ttk.Label(jfin_fb_frame, text="JFIN FB Emirleri:", font=("Arial", 9, "bold")).pack(side='left')
        
        ttk.Button(jfin_fb_frame, text="JFIN %25 FB", 
                  command=lambda: self.show_jfin_orders('FB', 25)).pack(side='left', padx=2)
        ttk.Button(jfin_fb_frame, text="JFIN %50 FB", 
                  command=lambda: self.show_jfin_orders('FB', 50)).pack(side='left', padx=2)
        ttk.Button(jfin_fb_frame, text="JFIN %75 FB", 
                  command=lambda: self.show_jfin_orders('FB', 75)).pack(side='left', padx=2)
        ttk.Button(jfin_fb_frame, text="JFIN %100 FB", 
                  command=lambda: self.show_jfin_orders('FB', 100)).pack(side='left', padx=2)
        
        # SoftFront Buy butonları
        ttk.Button(jfin_fb_frame, text="JFIN %25 SoftFB", 
                  command=lambda: self.show_jfin_orders('SoftFB', 25)).pack(side='left', padx=2)
        ttk.Button(jfin_fb_frame, text="JFIN %50 SoftFB", 
                  command=lambda: self.show_jfin_orders('SoftFB', 50)).pack(side='left', padx=2)
        ttk.Button(jfin_fb_frame, text="JFIN %75 SoftFB", 
                  command=lambda: self.show_jfin_orders('SoftFB', 75)).pack(side='left', padx=2)
        ttk.Button(jfin_fb_frame, text="JFIN %100 SoftFB", 
                  command=lambda: self.show_jfin_orders('SoftFB', 100)).pack(side='left', padx=2)
        
        fb_long_columns = ('Grup', 'Sembol', 'Final_FB_skor', 'Final_SFS_skor', 'FBtot', 'SMI', 'SMA63 chg', 'GORT', 'MAXALW', 'Mevcut Pozisyon', 'Hesaplanan Lot', 'Eklenebilir Lot')
        self.fb_long_tree = ttk.Treeview(fb_long_frame, columns=fb_long_columns, show='headings', height=15)
        
        # FB Long kolon başlıkları
        for col in fb_long_columns:
            self.fb_long_tree.heading(col, text=col)
            if col in ['Grup', 'Sembol']:
                self.fb_long_tree.column(col, width=120 if col == 'Grup' else 100)
            elif 'skor' in col:
                self.fb_long_tree.column(col, width=120)
            elif col == 'GORT':
                self.fb_long_tree.column(col, width=80)
            else:
                self.fb_long_tree.column(col, width=80)
        
        fb_long_scrollbar = ttk.Scrollbar(fb_long_frame, orient='vertical', command=self.fb_long_tree.yview)
        self.fb_long_tree.configure(yscrollcommand=fb_long_scrollbar.set)
        self.fb_long_tree.pack(side='left', fill='both', expand=True)
        fb_long_scrollbar.pack(side='right', fill='y')
        
        # 3. SAS Short tab (Final_SAS_skor kullanarak Short seçimi)
        sas_short_frame = ttk.Frame(notebook)
        notebook.add(sas_short_frame, text="SAS Short")
        
        # SAS Short lot durumu etiketi
        self.sas_short_lot_info = tk.Label(sas_short_frame, text="SAS Short - Lot durumu hesaplanıyor...",
                                          font=('Arial', 10, 'bold'), bg='lightyellow', pady=5)
        self.sas_short_lot_info.pack(fill='x', padx=5, pady=5)

        # SAS Short SMA63 chg filtresi
        sas_filter_frame = ttk.Frame(sas_short_frame)
        sas_filter_frame.pack(fill='x', padx=5, pady=2)

        ttk.Label(sas_filter_frame, text="SMA63 chg Filtresi:", font=("Arial", 9, "bold")).pack(side='left')
        self.sas_sma_filter_var = tk.StringVar()
        self.sas_sma_filter_entry = ttk.Entry(sas_filter_frame, textvariable=self.sas_sma_filter_var, width=8)
        self.sas_sma_filter_entry.pack(side='left', padx=2)

        self.sas_filter_type = tk.StringVar(value="below")
        ttk.Radiobutton(sas_filter_frame, text="Below", variable=self.sas_filter_type, value="below",
                        command=self.apply_sas_filter).pack(side='left', padx=2)
        ttk.Radiobutton(sas_filter_frame, text="Above", variable=self.sas_filter_type, value="above",
                        command=self.apply_sas_filter).pack(side='left', padx=2)

        ttk.Button(sas_filter_frame, text="Uygula", command=self.apply_sas_filter).pack(side='left', padx=5)
        ttk.Button(sas_filter_frame, text="Filtreleri Kaldır", command=self.clear_all_filters).pack(side='left', padx=5)
        
        # SAS Short SFStot filtresi
        sas_sfstot_filter_frame = ttk.Frame(sas_short_frame)
        sas_sfstot_filter_frame.pack(fill='x', padx=5, pady=2)

        ttk.Label(sas_sfstot_filter_frame, text="SFStot Filtresi:", font=("Arial", 9, "bold")).pack(side='left')
        self.sas_sfstot_filter_var = tk.StringVar()
        self.sas_sfstot_filter_entry = ttk.Entry(sas_sfstot_filter_frame, textvariable=self.sas_sfstot_filter_var, width=8)
        self.sas_sfstot_filter_entry.pack(side='left', padx=2)

        self.sas_sfstot_filter_type = tk.StringVar(value="below")
        ttk.Radiobutton(sas_sfstot_filter_frame, text="Below", variable=self.sas_sfstot_filter_type, value="below",
                        command=self.apply_sas_filter).pack(side='left', padx=2)
        ttk.Radiobutton(sas_sfstot_filter_frame, text="Above", variable=self.sas_sfstot_filter_type, value="above",
                        command=self.apply_sas_filter).pack(side='left', padx=2)
        
        # JFIN SAS butonları
        jfin_sas_frame = ttk.Frame(sas_short_frame)
        jfin_sas_frame.pack(fill='x', padx=5, pady=2)
        
        ttk.Label(jfin_sas_frame, text="JFIN SAS Emirleri:", font=("Arial", 9, "bold")).pack(side='left')
        
        ttk.Button(jfin_sas_frame, text="JFIN %25 SAS", 
                  command=lambda: self.show_jfin_orders('SAS', 25)).pack(side='left', padx=2)
        ttk.Button(jfin_sas_frame, text="JFIN %50 SAS", 
                  command=lambda: self.show_jfin_orders('SAS', 50)).pack(side='left', padx=2)
        ttk.Button(jfin_sas_frame, text="JFIN %75 SAS", 
                  command=lambda: self.show_jfin_orders('SAS', 75)).pack(side='left', padx=2)
        ttk.Button(jfin_sas_frame, text="JFIN %100 SAS", 
                  command=lambda: self.show_jfin_orders('SAS', 100)).pack(side='left', padx=2)
        
        # SoftFront Sell butonları
        ttk.Button(jfin_sas_frame, text="JFIN %25 SoftFS", 
                  command=lambda: self.show_jfin_orders('SoftFS', 25)).pack(side='left', padx=2)
        ttk.Button(jfin_sas_frame, text="JFIN %50 SoftFS", 
                  command=lambda: self.show_jfin_orders('SoftFS', 50)).pack(side='left', padx=2)
        ttk.Button(jfin_sas_frame, text="JFIN %75 SoftFS", 
                  command=lambda: self.show_jfin_orders('SoftFS', 75)).pack(side='left', padx=2)
        ttk.Button(jfin_sas_frame, text="JFIN %100 SoftFS", 
                  command=lambda: self.show_jfin_orders('SoftFS', 100)).pack(side='left', padx=2)
        
        sas_short_columns = ('Grup', 'Sembol', 'Final_SAS_skor', 'Final_FB_skor', 'SFStot', 'SMI', 'SMA63 chg', 'GORT', 'MAXALW', 'Mevcut Pozisyon', 'Hesaplanan Lot', 'Eklenebilir Lot')
        self.sas_short_tree = ttk.Treeview(sas_short_frame, columns=sas_short_columns, show='headings', height=15)
        
        # SAS Short kolon başlıkları
        for col in sas_short_columns:
            self.sas_short_tree.heading(col, text=col)
            if col in ['Grup', 'Sembol']:
                self.sas_short_tree.column(col, width=120 if col == 'Grup' else 100)
            elif 'skor' in col:
                self.sas_short_tree.column(col, width=120)
            elif col == 'GORT':
                self.sas_short_tree.column(col, width=80)
            else:
                self.sas_short_tree.column(col, width=80)
        
        sas_short_scrollbar = ttk.Scrollbar(sas_short_frame, orient='vertical', command=self.sas_short_tree.yview)
        self.sas_short_tree.configure(yscrollcommand=sas_short_scrollbar.set)
        self.sas_short_tree.pack(side='left', fill='both', expand=True)
        sas_short_scrollbar.pack(side='right', fill='y')
        
        # 4. SFS Short tab (Final_SFS_skor kullanarak Short seçimi)
        sfs_short_frame = ttk.Frame(notebook)
        notebook.add(sfs_short_frame, text="SFS Short")
        
        # SFS Short lot durumu etiketi
        self.sfs_short_lot_info = tk.Label(sfs_short_frame, text="SFS Short - Lot durumu hesaplanıyor...",
                                          font=('Arial', 10, 'bold'), bg='lightcoral', pady=5)
        self.sfs_short_lot_info.pack(fill='x', padx=5, pady=5)

        # SFS Short SMA63 chg filtresi
        sfs_filter_frame = ttk.Frame(sfs_short_frame)
        sfs_filter_frame.pack(fill='x', padx=5, pady=2)

        ttk.Label(sfs_filter_frame, text="SMA63 chg Filtresi:", font=("Arial", 9, "bold")).pack(side='left')
        self.sfs_sma_filter_var = tk.StringVar()
        self.sfs_sma_filter_entry = ttk.Entry(sfs_filter_frame, textvariable=self.sfs_sma_filter_var, width=8)
        self.sfs_sma_filter_entry.pack(side='left', padx=2)

        self.sfs_filter_type = tk.StringVar(value="below")
        ttk.Radiobutton(sfs_filter_frame, text="Below", variable=self.sfs_filter_type, value="below",
                        command=self.apply_sfs_filter).pack(side='left', padx=2)
        ttk.Radiobutton(sfs_filter_frame, text="Above", variable=self.sfs_filter_type, value="above",
                        command=self.apply_sfs_filter).pack(side='left', padx=2)

        ttk.Button(sfs_filter_frame, text="Uygula", command=self.apply_sfs_filter).pack(side='left', padx=5)
        ttk.Button(sfs_filter_frame, text="Filtreleri Kaldır", command=self.clear_all_filters).pack(side='left', padx=5)
        
        # SFS Short SFStot filtresi
        sfs_sfstot_filter_frame = ttk.Frame(sfs_short_frame)
        sfs_sfstot_filter_frame.pack(fill='x', padx=5, pady=2)

        ttk.Label(sfs_sfstot_filter_frame, text="SFStot Filtresi:", font=("Arial", 9, "bold")).pack(side='left')
        self.sfs_sfstot_filter_var = tk.StringVar()
        self.sfs_sfstot_filter_entry = ttk.Entry(sfs_sfstot_filter_frame, textvariable=self.sfs_sfstot_filter_var, width=8)
        self.sfs_sfstot_filter_entry.pack(side='left', padx=2)

        self.sfs_sfstot_filter_type = tk.StringVar(value="below")
        ttk.Radiobutton(sfs_sfstot_filter_frame, text="Below", variable=self.sfs_sfstot_filter_type, value="below",
                        command=self.apply_sfs_filter).pack(side='left', padx=2)
        ttk.Radiobutton(sfs_sfstot_filter_frame, text="Above", variable=self.sfs_sfstot_filter_type, value="above",
                        command=self.apply_sfs_filter).pack(side='left', padx=2)
        
        # JFIN SFS butonları
        jfin_sfs_frame = ttk.Frame(sfs_short_frame)
        jfin_sfs_frame.pack(fill='x', padx=5, pady=2)
        
        ttk.Label(jfin_sfs_frame, text="JFIN SFS Emirleri:", font=("Arial", 9, "bold")).pack(side='left')
        
        ttk.Button(jfin_sfs_frame, text="JFIN %25 SFS", 
                  command=lambda: self.show_jfin_orders('SFS', 25)).pack(side='left', padx=2)
        ttk.Button(jfin_sfs_frame, text="JFIN %50 SFS", 
                  command=lambda: self.show_jfin_orders('SFS', 50)).pack(side='left', padx=2)
        ttk.Button(jfin_sfs_frame, text="JFIN %75 SFS", 
                  command=lambda: self.show_jfin_orders('SFS', 75)).pack(side='left', padx=2)
        ttk.Button(jfin_sfs_frame, text="JFIN %100 SFS", 
                  command=lambda: self.show_jfin_orders('SFS', 100)).pack(side='left', padx=2)
        
        # SoftFront Sell butonları
        ttk.Button(jfin_sfs_frame, text="JFIN %25 SoftFS", 
                  command=lambda: self.show_jfin_orders('SoftFS', 25)).pack(side='left', padx=2)
        ttk.Button(jfin_sfs_frame, text="JFIN %50 SoftFS", 
                  command=lambda: self.show_jfin_orders('SoftFS', 50)).pack(side='left', padx=2)
        ttk.Button(jfin_sfs_frame, text="JFIN %75 SoftFS", 
                  command=lambda: self.show_jfin_orders('SoftFS', 75)).pack(side='left', padx=2)
        ttk.Button(jfin_sfs_frame, text="JFIN %100 SoftFS", 
                  command=lambda: self.show_jfin_orders('SoftFS', 100)).pack(side='left', padx=2)
        
        sfs_short_columns = ('Grup', 'Sembol', 'Final_SFS_skor', 'Final_FB_skor', 'SFStot', 'SMI', 'SMA63 chg', 'GORT', 'MAXALW', 'Mevcut Pozisyon', 'Hesaplanan Lot', 'Eklenebilir Lot')
        self.sfs_short_tree = ttk.Treeview(sfs_short_frame, columns=sfs_short_columns, show='headings', height=15)
        
        # SFS Short kolon başlıkları
        for col in sfs_short_columns:
            self.sfs_short_tree.heading(col, text=col)
            if col in ['Grup', 'Sembol']:
                self.sfs_short_tree.column(col, width=120 if col == 'Grup' else 100)
            elif 'skor' in col:
                self.sfs_short_tree.column(col, width=120)
            elif col == 'GORT':
                self.sfs_short_tree.column(col, width=80)
            else:
                self.sfs_short_tree.column(col, width=80)
        
        sfs_short_scrollbar = ttk.Scrollbar(sfs_short_frame, orient='vertical', command=self.sfs_short_tree.yview)
        self.sfs_short_tree.configure(yscrollcommand=sfs_short_scrollbar.set)
        self.sfs_short_tree.pack(side='left', fill='both', expand=True)
        sfs_short_scrollbar.pack(side='right', fill='y')
        
        # Geriye uyumluluk için eski referansları tut
        self.long_tree = self.fb_long_tree  # FB Long'u default long olarak tut
        self.short_tree = self.sfs_short_tree  # SFS Short'u default short olarak tut
        
        # Grup ağırlıkları tablosu
        self.weights_tree = ttk.Treeview(left_frame, columns=('Group', 'Weight', 'LotRights'),
                                        show='headings', height=15)
        self.weights_tree.heading('Group', text='Grup')
        self.weights_tree.heading('Weight', text='Ağırlık (%)')
        self.weights_tree.heading('LotRights', text='Lot Hakları')
        self.weights_tree.column('Group', width=150)
        self.weights_tree.column('Weight', width=80)
        self.weights_tree.column('LotRights', width=100)
        self.weights_tree.pack(fill='both', expand=True)

        # Filtrelenmiş veriler için değişkenler (başlangıçta boş)
        self.bb_filtered_data = []
        self.fb_filtered_data = []
        self.sas_filtered_data = []
        self.sfs_filtered_data = []
        
        # Toplam lot hakkı
        total_frame = ttk.Frame(left_frame)
        total_frame.pack(fill='x', pady=5)
        ttk.Label(total_frame, text="Toplam Lot Hakkı:").pack(side='left')
        self.total_lot_label = ttk.Label(total_frame, text="0", font=("Arial", 10, "bold"))
        self.total_lot_label.pack(side='left', padx=5)
        
        # Alpha ayarı
        alpha_frame = ttk.Frame(left_frame)
        alpha_frame.pack(fill='x', pady=5)
        ttk.Label(alpha_frame, text="Alpha Değeri:").pack(side='left')
        self.alpha_var = tk.StringVar(value="3")
        alpha_combo = ttk.Combobox(alpha_frame, textvariable=self.alpha_var, 
                                  values=["2", "3", "4", "5"], width=5)
        alpha_combo.pack(side='left', padx=5)
        alpha_combo.bind('<<ComboboxSelected>>', self.on_alpha_change)
        
        # Sağ taraf - Lot dağılımı sonuçları
        right_frame = ttk.LabelFrame(main_frame, text="FINAL THG Lot Dağılımı Sonuçları", padding=10)
        right_frame.pack(side='right', fill='both', expand=True)
        
        # Sonuçlar tablosu
        self.results_tree = ttk.Treeview(right_frame, 
                                        columns=('Group', 'Symbol', 'FINAL_THG', 'SMI', 'MAXALW', 'CalculatedLots', 'FinalLots', 'CurrentLots', 'AvailableLots', 'Status'),
                                        show='headings', height=20)
        
        # Sıralanabilir başlıklar
        self.results_tree.heading('Group', text='Grup ↕', command=lambda: self.sort_treeview('Group', 0))
        self.results_tree.heading('Symbol', text='Sembol ↕', command=lambda: self.sort_treeview('Symbol', 1))
        self.results_tree.heading('FINAL_THG', text='FINAL THG ↕', command=lambda: self.sort_treeview('FINAL_THG', 2))
        self.results_tree.heading('SMI', text='SMI ↕', command=lambda: self.sort_treeview('SMI', 3))
        self.results_tree.heading('MAXALW', text='MAXALW ↕', command=lambda: self.sort_treeview('MAXALW', 4))
        self.results_tree.heading('CalculatedLots', text='Hesaplanan Lot ↕', command=lambda: self.sort_treeview('CalculatedLots', 5))
        self.results_tree.heading('FinalLots', text='Final Lot ↕', command=lambda: self.sort_treeview('FinalLots', 6))
        self.results_tree.heading('CurrentLots', text='Mevcut Lot ↕', command=lambda: self.sort_treeview('CurrentLots', 7))
        self.results_tree.heading('AvailableLots', text='Alınabilir Lot ↕', command=lambda: self.sort_treeview('AvailableLots', 8))
        self.results_tree.heading('Status', text='Durum ↕', command=lambda: self.sort_treeview('Status', 9))
        
        # Sıralama durumunu takip et
        self.sort_reverse = False
        self.last_sort_column = None
        
        self.results_tree.column('Group', width=120)
        self.results_tree.column('Symbol', width=100)
        self.results_tree.column('FINAL_THG', width=100)
        self.results_tree.column('SMI', width=80)
        self.results_tree.column('MAXALW', width=80)
        self.results_tree.column('CalculatedLots', width=120)
        self.results_tree.column('FinalLots', width=100)
        self.results_tree.column('CurrentLots', width=100)
        self.results_tree.column('AvailableLots', width=100)
        self.results_tree.column('Status', width=100)
        
        self.results_tree.pack(fill='both', expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=self.results_tree.yview)
        scrollbar.pack(side='right', fill='y')
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        # Özet bilgiler
        summary_frame = ttk.LabelFrame(self.win, text="Özet Bilgiler", padding=10)
        summary_frame.pack(fill='x', padx=10, pady=5)
        
        self.summary_label = ttk.Label(summary_frame, text="Grup ağırlıklarını yükleyin ve lot dağılımını hesaplayın.")
        self.summary_label.pack()
    
    def setup_long_tab(self):
        """Long sekmesini oluştur"""
        # Sonuçlar tablosu
        cols = ['Group', 'Symbol', 'Final_FB_skor', 'Final_SFS_skor', 'FINAL_THG', 'SHORT_FINAL', 'SMI', 'MAXALW', 'CalculatedLots', 'FinalLots', 'CurrentLots', 'AvailableLots', 'Status']
        headers = ['Grup', 'Sembol', 'Final_FB_skor', 'Final_SFS_skor', 'FINAL_THG', 'SHORT_FINAL', 'SMI', 'MAXALW', 'Hesaplanan Lot', 'Final Lot', 'Mevcut Lot', 'Alınabilir Lot', 'Durum']
        
        self.long_tree = ttk.Treeview(self.long_tab, columns=cols, show='headings', height=20)
        
        for c, h in zip(cols, headers):
            self.long_tree.heading(c, text=h, command=lambda col=c: self.sort_treeview(col, cols.index(col), 'long'))
            if c == 'Group':
                self.long_tree.column(c, width=120, anchor='center')
            elif c == 'Symbol':
                self.long_tree.column(c, width=100, anchor='center')
            elif c == 'Final_FB_skor':
                self.long_tree.column(c, width=120, anchor='center')
            elif c == 'Final_SFS_skor':
                self.long_tree.column(c, width=120, anchor='center')
            elif c == 'FINAL_THG':
                self.long_tree.column(c, width=100, anchor='center')
            elif c == 'SHORT_FINAL':
                self.long_tree.column(c, width=100, anchor='center')
            elif c == 'SMI':
                self.long_tree.column(c, width=80, anchor='center')
            elif c == 'MAXALW':
                self.long_tree.column(c, width=80, anchor='center')
            elif c == 'CalculatedLots':
                self.long_tree.column(c, width=120, anchor='center')
            elif c == 'FinalLots':
                self.long_tree.column(c, width=100, anchor='center')
            elif c == 'CurrentLots':
                self.long_tree.column(c, width=100, anchor='center')
            elif c == 'AvailableLots':
                self.long_tree.column(c, width=120, anchor='center')
            else:
                self.long_tree.column(c, width=100, anchor='center')
        
        self.long_tree.pack(side='left', fill='both', expand=True)
        
        # Scrollbar
        long_scrollbar = ttk.Scrollbar(self.long_tab, orient="vertical", command=self.long_tree.yview)
        self.long_tree.configure(yscrollcommand=long_scrollbar.set)
        long_scrollbar.pack(side='right', fill='y')
        
        # Sıralama için değişkenler
        self.long_sort_column = None
        self.long_sort_reverse = False
    
    def setup_short_tab(self):
        """Short sekmesini oluştur"""
        # Sonuçlar tablosu
        cols = ['Group', 'Symbol', 'Final_FB_skor', 'Final_SFS_skor', 'SHORT_FINAL', 'FINAL_THG', 'SMI', 'MAXALW', 'CalculatedLots', 'FinalLots', 'CurrentLots', 'AvailableLots', 'Status']
        headers = ['Grup', 'Sembol', 'Final_FB_skor', 'Final_SFS_skor', 'SHORT_FINAL', 'FINAL_THG', 'SMI', 'MAXALW', 'Hesaplanan Lot', 'Final Lot', 'Mevcut Lot', 'Alınabilir Lot', 'Durum']
        
        self.short_tree = ttk.Treeview(self.short_tab, columns=cols, show='headings', height=20)
        
        for c, h in zip(cols, headers):
            self.short_tree.heading(c, text=h, command=lambda col=c: self.sort_treeview(col, cols.index(col), 'short'))
            if c == 'Group':
                self.short_tree.column(c, width=120, anchor='center')
            elif c == 'Symbol':
                self.short_tree.column(c, width=100, anchor='center')
            elif c == 'Final_FB_skor':
                self.short_tree.column(c, width=120, anchor='center')
            elif c == 'Final_SFS_skor':
                self.short_tree.column(c, width=120, anchor='center')
            elif c == 'SHORT_FINAL':
                self.short_tree.column(c, width=100, anchor='center')
            elif c == 'FINAL_THG':
                self.short_tree.column(c, width=100, anchor='center')
            elif c == 'SMI':
                self.short_tree.column(c, width=80, anchor='center')
            elif c == 'MAXALW':
                self.short_tree.column(c, width=100, anchor='center')
            elif c == 'CalculatedLots':
                self.short_tree.column(c, width=120, anchor='center')
            elif c == 'FinalLots':
                self.short_tree.column(c, width=100, anchor='center')
            elif c == 'CurrentLots':
                self.short_tree.column(c, width=100, anchor='center')
            elif c == 'AvailableLots':
                self.short_tree.column(c, width=120, anchor='center')
            else:
                self.short_tree.column(c, width=100, anchor='center')
        
        self.short_tree.pack(side='left', fill='both', expand=True)
        
        # Scrollbar
        short_scrollbar = ttk.Scrollbar(self.short_tab, orient="vertical", command=self.short_tree.yview)
        self.short_tree.configure(yscrollcommand=short_scrollbar.set)
        short_scrollbar.pack(side='right', fill='y')
        
        # Sıralama için değişkenler
        self.short_sort_column = None
        self.short_sort_reverse = False
    
    def on_alpha_change(self, event=None):
        """Alpha değeri değiştiğinde"""
        try:
            self.alpha = int(self.alpha_var.get())
            print(f"[FINAL THG] Alpha değeri {self.alpha} olarak ayarlandı")
        except:
            self.alpha = 3
    
    def get_current_position_lots(self, symbol):
        """Mevcut moda göre pozisyon lotunu al (IBKR MOD veya HAMMER MOD)"""
        try:
            # Mode manager'ı kontrol et
            if hasattr(self.parent, 'mode_manager') and self.parent.mode_manager:
                mode_manager = self.parent.mode_manager
                
                if mode_manager.is_ibkr_mode():
                    # IBKR MOD açık - IBKR pozisyonlarını kullan
                    print(f"[FINAL THG] 🔄 IBKR MOD aktif - {symbol} pozisyonu IBKR'den alınıyor...")
                    if hasattr(self.parent, 'ibkr') and self.parent.ibkr:
                        positions = self.parent.ibkr.get_positions_direct()
                        if positions:
                            for pos in positions:
                                if pos.get('symbol') == symbol:
                                    qty = pos.get('qty', 0)
                                    print(f"[FINAL THG] ✅ IBKR {symbol} pozisyon bulundu: {qty}")
                                    return abs(qty)  # Mutlak değer döndür
                            print(f"[FINAL THG] ⚠️ IBKR'de {symbol} pozisyon bulunamadı")
                        else:
                            print(f"[FINAL THG] ⚠️ IBKR'den pozisyon alınamadı")
                    else:
                        print(f"[FINAL THG] ❌ IBKR client bulunamadı")
                
                elif mode_manager.is_hampro_mode():
                    # HAMMER MOD açık - Hammer Pro pozisyonlarını kullan
                    print(f"[FINAL THG] 🔄 HAMMER MOD aktif - {symbol} pozisyonu Hammer Pro'dan alınıyor...")
                    if hasattr(self.parent, 'hammer') and self.parent.hammer:
                        positions = self.parent.hammer.get_positions_direct()
                        if positions:
                            for pos in positions:
                                if pos.get('symbol') == symbol:
                                    qty = pos.get('qty', 0)
                                    print(f"[FINAL THG] ✅ Hammer Pro {symbol} pozisyon bulundu: {qty}")
                                    return abs(qty)  # Mutlak değer döndür
                            print(f"[FINAL THG] ⚠️ Hammer Pro'da {symbol} pozisyon bulunamadı")
                        else:
                            print(f"[FINAL THG] ⚠️ Hammer Pro'dan pozisyon alınamadı")
                    else:
                        print(f"[FINAL THG] ❌ Hammer Pro client bulunamadı")
                else:
                    print(f"[FINAL THG] ⚠️ Mod belirlenemedi, Hammer Pro kullanılıyor...")
                    # Fallback: Hammer Pro kullan
                    if hasattr(self.parent, 'hammer') and self.parent.hammer:
                        positions = self.parent.hammer.get_positions_direct()
                        if positions:
                            for pos in positions:
                                if pos.get('symbol') == symbol:
                                    qty = pos.get('qty', 0)
                                    return abs(qty)
            else:
                print(f"[FINAL THG] ⚠️ Mode manager bulunamadı, Hammer Pro kullanılıyor...")
                # Fallback: Hammer Pro kullan
                if hasattr(self.parent, 'hammer') and self.parent.hammer:
                    positions = self.parent.hammer.get_positions_direct()
                    if positions:
                        for pos in positions:
                            if pos.get('symbol') == symbol:
                                qty = pos.get('qty', 0)
                                return abs(qty)
            
            return 0  # Pozisyon bulunamadı veya hata
        except Exception as e:
            print(f"[FINAL THG] Pozisyon lotu alınırken hata: {e}")
            return 0
    
    def sort_treeview(self, col, col_index):
        """Treeview'ı belirtilen kolona göre sırala"""
        try:
            # Aynı kolona tekrar tıklandıysa sıralama yönünü değiştir
            if self.last_sort_column == col:
                self.sort_reverse = not self.sort_reverse
            else:
                self.sort_reverse = False
                self.last_sort_column = col
            
            # Mevcut verileri al
            data = []
            for item in self.results_tree.get_children():
                values = self.results_tree.item(item)['values']
                data.append(values)
            
            if not data:
                return
            
            # Sıralama yönünü belirle
            reverse = self.sort_reverse
            
            # Kolon tipine göre sırala
            if col in ['FINAL_THG', 'SMI', 'MAXALW', 'CalculatedLots', 'FinalLots', 'CurrentLots', 'AvailableLots']:
                # Sayısal sıralama
                try:
                    data.sort(key=lambda x: float(str(x[col_index]).replace(',', '')) if str(x[col_index]).replace(',', '').replace('.', '').replace('-', '').isdigit() else 0, reverse=reverse)
                except:
                    data.sort(key=lambda x: str(x[col_index]), reverse=reverse)
            else:
                # Metin sıralama
                data.sort(key=lambda x: str(x[col_index]), reverse=reverse)
            
            # Sıralama yönünü göster
            arrow = " ↓" if reverse else " ↑"
            self.results_tree.heading(col, text=f"{col}{arrow}")
            
            # Verileri yeniden ekle
            for item in self.results_tree.get_children():
                self.results_tree.delete(item)
            
            for row in data:
                self.results_tree.insert('', 'end', values=row)
                
            print(f"[FINAL THG] {col} kolonuna göre sıralandı (reverse={reverse})")
            
        except Exception as e:
            print(f"[FINAL THG] Sıralama hatası: {e}")
    
    def load_group_weights(self):
        """Port Adjuster'dan grup ağırlıklarını yükle"""
        try:
            # 🚨 KRİTİK: Port Adjuster'la aynı CSV yolunu kullan!
            # Port Adjuster'da kullanılan yol: StockTracker dizinindeki exposureadjuster.csv
            current_dir = os.path.dirname(os.path.abspath(__file__))  # janallresapp dizini
            project_root = os.path.dirname(os.path.dirname(current_dir))  # StockTracker dizini
            csv_path = os.path.join(project_root, 'exposureadjuster.csv')
            print(f"🔍 CSV dosyası aranıyor: {os.path.abspath(csv_path)}")
            
            if not os.path.exists(csv_path):
                messagebox.showerror("Hata", f"exposureadjuster.csv dosyası bulunamadı!\nAranan yol: {os.path.abspath(csv_path)}\nÖnce Port Adjuster'da ayarları kaydedin.")
                return
            else:
                print(f"✅ CSV dosyası bulundu: {os.path.abspath(csv_path)}")
            
            df = pd.read_csv(csv_path)
            print(f"📊 CSV okundu: {len(df)} satır")
            print(f"📋 CSV kolonları: {list(df.columns)}")
            print(f"🔍 İlk 5 satır:")
            print(df.head().to_string())
            
            # 🚨 DEBUG: CSV dosya yolunu ve içeriğini detaylı kontrol et
            print(f"\n🔍 DEBUG: CSV dosya detayları:")
            print(f"   📁 Dosya yolu: {os.path.abspath(csv_path)}")
            print(f"   📊 Toplam satır: {len(df)}")
            print(f"   📋 Kolonlar: {list(df.columns)}")
            
            # CSV'de "Short Groups" bölümünü bul ve göster
            short_groups_found = False
            for idx, row in df.iterrows():
                setting = str(row['Setting']).strip()
                if setting == 'Short Groups':
                    short_groups_found = True
                    print(f"   📋 'Short Groups' bölümü {idx}. satırda bulundu")
                    break
            
            if not short_groups_found:
                print(f"   ❌ 'Short Groups' bölümü bulunamadı!")
            else:
                print(f"   ✅ 'Short Groups' bölümü bulundu")
                
                # Short Groups bölümünden sonraki 5 satırı göster
                print(f"   📊 Short Groups bölümünden sonraki 5 satır:")
                for i in range(idx + 1, min(idx + 6, len(df))):
                    row = df.iloc[i]
                    setting = str(row['Setting']).strip()
                    value = str(row['Value']).strip()
                    print(f"      {i}: {setting} = {value}")
                
                # 🚨 DEBUG: CSV'deki tüm satırları kontrol et
                print(f"\n🔍 DEBUG: CSV'deki tüm satırlar:")
                for i, row in df.iterrows():
                    setting = str(row['Setting']).strip()
                    value = str(row['Value']).strip()
                    if 'held' in setting.lower() or 'high' in setting.lower() or 'not' in setting.lower() or 'rumor' in setting.lower() or 'salak' in setting.lower() or 'shit' in setting.lower():
                        print(f"   {i:2d}: {setting} = {value}")
            
            # Grup ağırlıklarını al - Long ve Short Groups'ları ayrı ayrı al
            self.long_group_weights = {}
            self.short_group_weights = {}
            long_total_weight = 0
            short_total_weight = 0
            
            # CSV'deki grup ağırlıklarını doğru şekilde bul
            current_section = None
            
            for _, row in df.iterrows():
                setting = str(row['Setting']).strip()
                value = str(row['Value']).strip()
                
                # Bölüm başlıklarını kontrol et
                if setting == 'Long Groups':
                    current_section = 'long'
                    print(f"📋 Long Groups bölümü bulundu")
                    continue
                elif setting == 'Short Groups':
                    current_section = 'short'
                    print(f"📋 Short Groups bölümü bulundu")
                    continue
                elif setting == 'Percentage':
                    # Bu satırı atla, sadece başlık
                    print(f"📋 {current_section.upper()} bölümü için Percentage başlığı bulundu")
                    continue
                
                # Grup ağırlıklarını işle - sadece current_section set edilmişse
                if current_section == 'long' and '%' in value:
                    try:
                        group = setting
                        weight = float(value.replace('%', ''))
                        self.long_group_weights[group] = weight
                        long_total_weight += weight
                        print(f"   📊 LONG: {group} = {weight}%")
                    except Exception as e:
                        print(f"   ❌ LONG {setting} ağırlık hatası: {e}")
                        continue
                elif current_section == 'short' and '%' in value:
                    try:
                        group = setting
                        weight = float(value.replace('%', ''))
                        self.short_group_weights[group] = weight
                        short_total_weight += weight
                        print(f"   📊 SHORT: {group} = {weight}%")
                    except Exception as e:
                        print(f"   ❌ SHORT {setting} ağırlık hatası: {e}")
                        continue
            
            # Toplam lot hakkını Port Adjuster'dan al
            # Total Exposure ve Avg Pref Price'dan hesapla
            total_exposure = 1000000  # Varsayılan
            avg_pref_price = 25.0     # Varsayılan
            long_ratio = 85.0         # Varsayılan
            short_ratio = 15.0        # Varsayılan
            
            for _, row in df.iterrows():
                setting = row['Setting']
                value = row['Value']
                
                if setting == 'Total Exposure':
                    try:
                        exposure_str = str(value).replace('$', '').replace(',', '')
                        total_exposure = float(exposure_str)
                    except:
                        pass
                elif setting == 'Avg Pref Price':
                    try:
                        price_str = str(value).replace('$', '').replace(',', '')
                        avg_pref_price = float(price_str)
                    except:
                        pass
            
            # Exposure değerlerini güncelle
            self.total_exposure = total_exposure
            self.avg_price = avg_pref_price
            
            # Long/Short lot haklarını hesapla - CSV'deki toplam ağırlıklardan
            total_lots = int(total_exposure / avg_pref_price)
            calculated_long_rights = int(total_lots * (long_total_weight / 100))
            calculated_short_rights = int(total_lots * (short_total_weight / 100))
            
            print(f"📊 CSV'den hesaplanan lot hakları:")
            print(f"   📈 Long toplam ağırlık: {long_total_weight}% → {calculated_long_rights:,} lot")
            print(f"   📉 Short toplam ağırlık: {short_total_weight}% → {calculated_short_rights:,} lot")
            
            # 🚨 KRİTİK: SADECE CSV'den hesaplanan lot haklarını kullan!
            # Port Adjuster'dan eski, yanlış değerleri alma!
            self.long_lot_rights = calculated_long_rights
            self.short_lot_rights = calculated_short_rights
            print(f"📊 CSV'den hesaplanan lot hakları kullanıldı: Long={self.long_lot_rights:,}, Short={self.short_lot_rights:,}")
            
            # Port Adjuster'da da bu değerleri güncelle (widget kontrolü ile)
            if hasattr(self, 'port_adjuster') and self.port_adjuster:
                try:
                    # Port Adjuster penceresinin hala açık olup olmadığını kontrol et
                    if hasattr(self.port_adjuster, 'win'):
                        try:
                            self.port_adjuster.win.winfo_exists()
                        except tk.TclError:
                            print("⚠️ Port Adjuster penceresi kapatılmış, güncelleme atlandı")
                            # Port Adjuster referansını temizle
                            self.port_adjuster = None
                            return
                    
                    if hasattr(self.port_adjuster, 'long_lot_rights'):
                        self.port_adjuster.long_lot_rights = self.long_lot_rights
                    if hasattr(self.port_adjuster, 'short_lot_rights'):
                        self.port_adjuster.short_lot_rights = self.short_lot_rights
                    print(f"✅ Port Adjuster lot hakları CSV'den güncellendi: Long={self.long_lot_rights:,}, Short={self.short_lot_rights:,}")
                except Exception as e:
                    print(f"⚠️ Port Adjuster güncellenirken hata: {e}")
            
            print(f"✅ Exposure değerleri yüklendi:")
            print(f"   Toplam Exposure: ${total_exposure:,.0f}")
            print(f"   Ortalama Fiyat: ${avg_pref_price:.2f}")
            print(f"   Toplam Lot Hakkı: {total_lots:,}")
            print(f"   Long Lot Hakkı: {self.long_lot_rights:,} (CSV'den: {long_total_weight}%)")
            print(f"   Short Lot Hakkı: {self.short_lot_rights:,} (CSV'den: {short_total_weight}%)")
            
            # Debug: Yüklenen grup ağırlıklarını göster
            print(f"\n🔍 YÜKLENEN GRUP AĞIRLIKLARI:")
            print(f"   📊 LONG Gruplar ({len(self.long_group_weights)} adet):")
            for group, weight in self.long_group_weights.items():
                print(f"      {group}: {weight}%")
            
            print(f"   📊 SHORT Gruplar ({len(self.short_group_weights)} adet):")
            for group, weight in self.short_group_weights.items():
                print(f"      {group}: {weight}%")
            
            print(f"\n📈 TOPLAM AĞIRLIKLAR:")
            print(f"   LONG: {long_total_weight}%")
            print(f"   SHORT: {short_total_weight}%")
            
            # 🚨 KRİTİK: Port Adjuster'ı tamamen sıfırla ve CSV'den yüklenen değerlerle güncelle!
            if hasattr(self, 'port_adjuster') and self.port_adjuster:
                try:
                    # Port Adjuster penceresinin hala açık olup olmadığını kontrol et
                    if hasattr(self.port_adjuster, 'win'):
                        try:
                            self.port_adjuster.win.winfo_exists()
                        except tk.TclError:
                            print("⚠️ Port Adjuster penceresi kapatılmış, güncelleme atlandı")
                            # Port Adjuster referansını temizle
                            self.port_adjuster = None
                            return
                    
                    # Port Adjuster'da grup ağırlıklarını TAMAMEN SIFIRLA
                    if hasattr(self.port_adjuster, 'long_groups'):
                        self.port_adjuster.long_groups = {}  # Önce sıfırla
                        self.port_adjuster.long_groups = self.long_group_weights.copy()  # Sonra CSV'den yükle
                        print(f"✅ Port Adjuster LONG grupları SIFIRLANDI ve güncellendi: {len(self.port_adjuster.long_groups)} grup")
                    
                    if hasattr(self.port_adjuster, 'short_groups'):
                        self.port_adjuster.short_groups = {}  # Önce sıfırla
                        self.port_adjuster.short_groups = self.short_group_weights.copy()  # Sonra CSV'den yükle
                        print(f"✅ Port Adjuster SHORT grupları SIFIRLANDI ve güncellendi: {len(self.port_adjuster.short_groups)} grup")
                    
                    # Port Adjuster'da lot haklarını da güncelle
                    if hasattr(self.port_adjuster, 'long_lot_rights'):
                        self.port_adjuster.long_lot_rights = self.long_lot_rights
                    if hasattr(self.port_adjuster, 'short_lot_rights'):
                        self.port_adjuster.short_lot_rights = self.short_lot_rights
                        
                    print(f"✅ Port Adjuster lot hakları güncellendi: Long={self.long_lot_rights:,}, Short={self.short_lot_rights:,}")
                    
                    # 🚨 DEBUG: Port Adjuster'daki değerleri kontrol et
                    print(f"\n🔍 DEBUG: Port Adjuster'daki güncel değerler:")
                    if hasattr(self.port_adjuster, 'short_groups'):
                        short_items = list(self.port_adjuster.short_groups.items())[:5]
                        print(f"   📊 İlk 5 SHORT grup (Port Adjuster):")
                        for group, weight in short_items:
                            print(f"      {group}: {weight}%")
                    
                except Exception as e:
                    print(f"⚠️ Port Adjuster güncellenirken hata: {e}")
            else:
                print(f"⚠️ Port Adjuster bulunamadı, grup ağırlıkları güncellenemedi")
            
            # 🚨 DEBUG: Grup ağırlıklarını kontrol et
            print(f"\n🔍 DEBUG: Grup ağırlıkları kontrol ediliyor...")
            print(f"   📊 self.long_group_weights: {len(self.long_group_weights)} grup")
            print(f"   📊 self.short_group_weights: {len(self.short_group_weights)} grup")
            
            # İlk 5 SHORT grubu göster
            short_items = list(self.short_group_weights.items())[:5]
            print(f"   📊 İlk 5 SHORT grup:")
            for group, weight in short_items:
                print(f"      {group}: {weight}%")
            
            # Tabloyu güncelle (widget'ın varlığını kontrol et)
            try:
                if hasattr(self, 'weights_tree') and self.weights_tree:
                    # Widget'ın hala geçerli olup olmadığını kontrol et
                    try:
                        self.weights_tree.winfo_exists()
                        self.update_weights_table()
                    except tk.TclError:
                        print("⚠️ weights_tree widget'ı geçersiz, tablo güncellenemedi")
                else:
                    print("⚠️ weights_tree widget'ı bulunamadı, tablo güncellenemedi")
            except Exception as e:
                print(f"⚠️ Tablo güncellenirken hata: {e}")
            
            # Stock Data Manager'dan Final_FB_skor ve Final_SFS_skor verilerini çek
            if self.stock_data_manager:
                print(f"[3. STEP] 🔄 Stock Data Manager'dan skor verileri çekiliyor...")
                try:
                    # Final_FB_skor verilerini al
                    fb_scores = self.stock_data_manager.get_stock_column_data('Final_FB_skor')
                    print(f"[3. STEP] ✅ Final_FB_skor verileri alındı: {len(fb_scores)} hisse")
                    
                    # Final_SFS_skor verilerini al
                    sfs_scores = self.stock_data_manager.get_stock_column_data('Final_SFS_skor')
                    print(f"[3. STEP] ✅ Final_SFS_skor verileri alındı: {len(sfs_scores)} hisse")
                    
                    # Verileri sakla
                    self.fb_scores_data = fb_scores
                    self.sfs_scores_data = sfs_scores
                    
                except Exception as e:
                    print(f"[3. STEP] ❌ Skor verileri çekilirken hata: {e}")
                    self.fb_scores_data = {}
                    self.sfs_scores_data = {}
            else:
                print(f"[3. STEP] ⚠️ Stock Data Manager yok, skor verileri çekilemedi")
                self.fb_scores_data = {}
                self.sfs_scores_data = {}
            
            # Lot haklarını tekrar CSV'den yükle (güncel değerler için)
            self.load_lot_rights_from_csv()
            
            # UI'daki toplam lot hakkını güncelle (widget kontrolü ile)
            if hasattr(self, 'total_lot_label') and self.total_lot_label:
                try:
                    self.total_lot_label.winfo_exists()
                    self.total_lot_label.config(text=f"Long: {self.long_lot_rights:,} | Short: {self.short_lot_rights:,}")
                except tk.TclError:
                    print("⚠️ total_lot_label widget'ı geçersiz")
            
            # Sağ üstteki sekme başlıklarını da güncelle (widget kontrolü ile)
            if hasattr(self, 'bb_long_lot_info') and self.bb_long_lot_info:
                try:
                    self.bb_long_lot_info.winfo_exists()
                    self.bb_long_lot_info.config(text=f"BB Long ({self.long_lot_rights:,} lot/sekme) - Lot durumu hesaplanıyor...")
                except tk.TclError:
                    print("⚠️ bb_long_lot_info widget'ı geçersiz")
            
            if hasattr(self, 'fb_long_lot_info') and self.fb_long_lot_info:
                try:
                    self.fb_long_lot_info.winfo_exists()
                    self.fb_long_lot_info.config(text=f"FB Long ({self.long_lot_rights:,} lot/sekme) - Lot durumu hesaplanıyor...")
                except tk.TclError:
                    print("⚠️ fb_long_lot_info widget'ı geçersiz")
            
            if hasattr(self, 'sas_short_lot_info') and self.sas_short_lot_info:
                try:
                    self.sas_short_lot_info.winfo_exists()
                    self.sas_short_lot_info.config(text=f"SAS Short ({self.short_lot_rights:,} lot/sekme) - Lot durumu hesaplanıyor...")
                except tk.TclError:
                    print("⚠️ sas_short_lot_info widget'ı geçersiz")
            
            if hasattr(self, 'sfs_short_lot_info') and self.sfs_short_lot_info:
                try:
                    self.sfs_short_lot_info.winfo_exists()
                    self.sfs_short_lot_info.config(text=f"SFS Short ({self.short_lot_rights:,} lot/sekme) - Lot durumu hesaplanıyor...")
                except tk.TclError:
                    print("⚠️ sfs_short_lot_info widget'ı geçersiz")
            
            print(f"✅ Sekme başlıkları güncellendi: Long={self.long_lot_rights:,}, Short={self.short_lot_rights:,}")
            
            # Güncel lot haklarıyla popup göster (Allowed modunda gösterme)
            if not (hasattr(self.main_window, 'runall_allowed_mode') and self.main_window.runall_allowed_mode):
                messagebox.showinfo("Başarılı", f"Grup ağırlıkları yüklendi!\nLong ağırlık: {long_total_weight}%\nShort ağırlık: {short_total_weight}%\nLong lot hakkı: {self.long_lot_rights:,}\nShort lot hakkı: {self.short_lot_rights:,}")
            else:
                print(f"[ADDNEWPOS] ℹ️ Allowed modu aktif - Bildirim penceresi gösterilmedi")
            
        except Exception as e:
            error_msg = f"Grup ağırlıkları yüklenirken hata: {e}"
            print(f"[ADDNEWPOS] ❌ {error_msg}")
            # Allowed modunda hata mesajını göster ama otomatik kapatılacak
            if not (hasattr(self.main_window, 'runall_allowed_mode') and self.main_window.runall_allowed_mode):
                messagebox.showerror("Hata", error_msg)
            else:
                print(f"[ADDNEWPOS] ℹ️ Allowed modu aktif - Hata mesajı gösterilmedi, otomatik kapatılacak")
                # Hata mesajını otomatik kapatmak için kısa bir gecikme ekle
                self.main_window.after(500, lambda: self.main_window.addnewpos_close_messagebox())
    
    def update_weights_table(self):
        """Ağırlıklar tablosunu güncelle"""
        try:
            # Widget'ın varlığını kontrol et
            if not hasattr(self, 'weights_tree') or not self.weights_tree:
                print("⚠️ weights_tree widget'ı bulunamadı")
                return
            
            # Widget'ın hala geçerli olup olmadığını kontrol et
            try:
                self.weights_tree.winfo_exists()
            except tk.TclError:
                print("⚠️ weights_tree widget'ı geçersiz")
                return
            
            # Önce CSV'den güncel lot haklarını yükle
            self.load_lot_rights_from_csv()
            
            # Mevcut verileri temizle
            for item in self.weights_tree.get_children():
                self.weights_tree.delete(item)
            
            # Long grupları ekle
            long_total = 0
            for group, weight in self.long_group_weights.items():
                lot_rights = int((weight / 100) * self.long_lot_rights)
                long_total += lot_rights
                
                self.weights_tree.insert('', 'end', values=(f"LONG: {group}", f"{weight}%", f"{lot_rights:,}"))
            
            # Short grupları ekle
            short_total = 0
            for group, weight in self.short_group_weights.items():
                lot_rights = int((weight / 100) * self.short_lot_rights)
                short_total += lot_rights
                
                self.weights_tree.insert('', 'end', values=(f"SHORT: {group}", f"{weight}%", f"{lot_rights:,}"))
            
            # Toplam lot hakkını güncelle - CSV'den güncel değerleri kullan
            if hasattr(self, 'total_lot_label') and self.total_lot_label:
                try:
                    self.total_lot_label.config(text=f"Long: {self.long_lot_rights:,} | Short: {self.short_lot_rights:,}")
                except tk.TclError:
                    print("⚠️ total_lot_label widget'ı geçersiz")
        except Exception as e:
            print(f"⚠️ update_weights_table hatası: {e}")
            import traceback
            traceback.print_exc()
    
    def calculate_lot_distribution(self):
        """FINAL THG tabanlı lot dağılımını hesapla"""
        if not self.group_weights:
            messagebox.showerror("Hata", "Önce grup ağırlıklarını yükleyin!")
            return
        
        try:
            # Sonuçlar tablosunu temizle
            for item in self.results_tree.get_children():
                self.results_tree.delete(item)
            
            all_results = []
            
            # Her grup için lot dağılımını hesapla
            for group, weight in self.group_weights.items():
                if weight <= 0:
                    continue
                
                # Grup dosyasını bul
                # Mevcut çalışma dizininde ara
                file_pattern = f"ssfinek{group.lower()}.csv"
                
                if not os.path.exists(file_pattern):
                    print(f"[FINAL THG] {group} için CSV dosyası bulunamadı: {os.path.abspath(file_pattern)}")
                    continue
                
                csv_file = file_pattern
                print(f"[FINAL THG] {group} grubu analiz ediliyor: {csv_file}")
                
                # CSV'yi oku
                df = pd.read_csv(csv_file, encoding='utf-8-sig')
                
                # Gerekli kolonları kontrol et
                required_columns = ['FINAL_THG', 'PREF IBKR']
                if not all(col in df.columns for col in required_columns):
                    print(f"[FINAL THG] {group} için gerekli kolonlar bulunamadı: {required_columns}")
                    continue
                
                # SMI ve AVG_ADV kolonlarını kontrol et
                has_smi = 'SMI' in df.columns
                has_avg_adv = 'AVG_ADV' in df.columns
                
                # MAXALW değerini AVG_ADV/10 olarak hesapla
                if has_avg_adv:
                    df['MAXALW'] = df['AVG_ADV'] / 10
                    has_maxalw = True
                else:
                    has_maxalw = False
                
                # FINAL THG değerlerini al
                final_thg_data = df[['FINAL_THG', 'PREF IBKR']].dropna()
                
                if len(final_thg_data) == 0:
                    print(f"[FINAL THG] {group} için FINAL THG verisi bulunamadı")
                    continue
                
                # TOP 5 hisseyi bul
                top_5_indices = final_thg_data['FINAL_THG'].nlargest(5).index
                top_5_data = final_thg_data.loc[top_5_indices]
                
                # Bu grup için lot hakkını hesapla
                group_lot_rights = int((weight / 100) * self.total_lot_rights)
                
                # FINAL THG tabanlı lot dağılımını hesapla
                final_thg_values = top_5_data['FINAL_THG'].values
                lot_distribution = self.calculate_group_lot_distribution(final_thg_values, group_lot_rights)
                
                # Sonuçları ekle
                for i, (idx, row) in enumerate(top_5_data.iterrows()):
                    symbol = row['PREF IBKR']
                    final_thg = row['FINAL_THG']
                    calculated_lots = lot_distribution[i]
                    
                    # SMI ve MAXALW değerlerini al
                    try:
                        smi_value = df.loc[idx, 'SMI'] if has_smi else 'N/A'
                    except:
                        smi_value = 'N/A'
                    
                    try:
                        maxalw_value = df.loc[idx, 'MAXALW'] if has_maxalw else 'N/A'
                    except:
                        maxalw_value = 'N/A'
                    
                    # MAXALW limitini kontrol et (MAXALW = AVG_ADV/10, limit = MAXALW*2)
                    final_lots = calculated_lots
                    status = "✓"
                    
                    if has_maxalw and maxalw_value != 'N/A' and maxalw_value != '':
                        try:
                            maxalw_limit = float(maxalw_value) * 2  # MAXALW'nin 2 katı = AVG_ADV/5
                            if calculated_lots > maxalw_limit:
                                final_lots = int(maxalw_limit)
                                status = f"MAXALW limit ({maxalw_limit:.0f})"
                        except:
                            pass
                    
                    # Mevcut pozisyon lotunu al
                    current_lots = self.get_current_position_lots(symbol)
                    
                    # Alınabilir lot hesapla (Final Lot - Mevcut Lot)
                    available_lots = max(0, final_lots - current_lots)
                    
                    # Tabloya ekle
                    self.results_tree.insert('', 'end', values=(
                        group, symbol, f"{final_thg:.2f}", 
                        smi_value, maxalw_value,
                        f"{calculated_lots:,}", f"{final_lots:,}", 
                        f"{current_lots:,}", f"{available_lots:,}", status
                    ))
                    
                    all_results.append({
                        'group': group,
                        'symbol': symbol,
                        'final_thg': final_thg,
                        'smi': smi_value,
                        'maxalw': maxalw_value,
                        'calculated_lots': calculated_lots,
                        'final_lots': final_lots,
                        'current_lots': current_lots,
                        'available_lots': available_lots,
                        'status': status
                    })
            
            # Özet bilgileri güncelle
            total_calculated = sum(r['calculated_lots'] for r in all_results)
            total_final = sum(r['final_lots'] for r in all_results)
            total_current = sum(r['current_lots'] for r in all_results)
            total_available = sum(r['available_lots'] for r in all_results)
            efficiency = (total_final / total_calculated * 100) if total_calculated > 0 else 0
            
            summary_text = f"Toplam Hesaplanan Lot: {total_calculated:,}\n"
            summary_text += f"Toplam Final Lot: {total_final:,}\n"
            summary_text += f"Toplam Mevcut Lot: {total_current:,}\n"
            summary_text += f"Toplam Alınabilir Lot: {total_available:,}\n"
            summary_text += f"Verimlilik: {efficiency:.1f}%\n"
            summary_text += f"Kullanılmayan Lot: {total_calculated - total_final:,}"
            
            self.summary_label.config(text=summary_text)
            
            messagebox.showinfo("Başarılı", f"Lot dağılımı hesaplandı!\n{len(all_results)} hisse analiz edildi.")
            
        except Exception as e:
            messagebox.showerror("Hata", f"Lot dağılımı hesaplanırken hata: {e}")
            print(f"[FINAL THG] Hata: {e}")
    
    def calculate_group_lot_distribution(self, final_thg_values, total_lot, min_lot_thresh=100):
        """Bir grup için FINAL THG tabanlı lot dağılımını hesapla"""
        final_thg_arr = np.array(final_thg_values, dtype=np.float64)
        max_score = final_thg_arr.max()
        
        # Oranları hesapla ve farkları güçlendir
        relative_scores = (final_thg_arr / max_score) ** self.alpha
        
        # Lotları ölçekle
        raw_lot_alloc = relative_scores / relative_scores.sum() * total_lot
        
        # Minimum eşik altındakileri sıfırla
        raw_lot_alloc[raw_lot_alloc < min_lot_thresh] = 0
        
        # Lotları 100'lük sayılara yuvarla
        lot_alloc = np.round(raw_lot_alloc / 100) * 100
        lot_alloc = lot_alloc.astype(int)
        
        # Eğer toplam lot farkı varsa, en yüksek skorlu hisseye ekle
        if lot_alloc.sum() != total_lot:
            difference = total_lot - lot_alloc.sum()
            if difference > 0:
                max_idx = np.argmax(relative_scores)
                lot_alloc[max_idx] += difference
        
        return lot_alloc
    
    def calculate_score_based_lot_distribution_by_group(self, stocks_list, score_type, is_short=False):
        """Grup bazlı lot dağılımını hesapla - Her grup kendi lot hakkı içinde"""
        try:
            if not stocks_list:
                return {}
            
            # Port Adjuster'dan grup ağırlıklarını al
            if not hasattr(self.parent, 'long_groups') or not hasattr(self.parent, 'short_groups'):
                print(f"   ⚠️ Port Adjuster grup ağırlıkları bulunamadı, varsayılan dağılım yapılıyor")
                return self.calculate_score_based_lot_distribution_simple(stocks_list, score_type, 10000, is_short)
            
            # Grup bazında hisseleri ayır
            groups = {}
            for stock in stocks_list:
                group = stock.get('GRUP', 'unknown')
                if group not in groups:
                    groups[group] = []
                groups[group].append(stock)
            
            print(f"   🎯 {score_type} grup bazlı lot dağılımı (Alpha: {self.alpha}):")
            
            all_lots = {}
            total_distributed = 0
            
            for group, group_stocks in groups.items():
                # Grup ağırlığını al
                if is_short:
                    group_weight = self.parent.short_groups.get(group, 0)
                    total_rights = self.parent.short_lot_rights if hasattr(self.parent, 'short_lot_rights') else 12000
                else:
                    group_weight = self.parent.long_groups.get(group, 0)
                    total_rights = self.parent.long_lot_rights if hasattr(self.parent, 'long_lot_rights') else 28000
                
                # Bu grubun lot hakkını hesapla
                if group_weight > 0:
                    group_lot_rights = int((group_weight / 100) * total_rights)
                else:
                    group_lot_rights = 0
                
                print(f"      📊 {group}: {group_weight}% × {total_rights:,} = {group_lot_rights:,} lot")
                
                if group_lot_rights <= 0:
                    # Lot hakkı yoksa 0 ver
                    for stock in group_stocks:
                        all_lots[stock.get('PREF IBKR', 'N/A')] = 0
                    continue
                
                # Bu grup için lot dağılımı yap
                group_lots = self.calculate_score_based_lot_distribution_simple(
                    group_stocks, score_type, group_lot_rights, is_short
                )
                
                # Sonuçları birleştir
                all_lots.update(group_lots)
                total_distributed += sum(group_lots.values())
            
            print(f"   ✅ {score_type} toplam dağıtılan: {total_distributed:,} lot")
            
            return all_lots
            
        except Exception as e:
            print(f"   ❌ {score_type} grup bazlı lot dağılım hatası: {e}")
            return {stock.get('PREF IBKR', 'N/A'): 100 for stock in stocks_list}
    
    def calculate_score_based_lot_distribution_simple(self, stocks_list, score_type, total_lot, is_short=False, min_lot_thresh=100):
        """Basit skor bazlı lot dağılımı (tek grup için) - TAMAMEN LOT HAKKINI DOLDURACAK"""
        try:
            if not stocks_list:
                return {}
            
            print(f"         🎯 Grup içi dağılım: {len(stocks_list)} hisse için {total_lot:,} lot")
            
            # Skorları topla
            scores = []
            symbols = []
            
            for stock in stocks_list:
                symbol = stock.get('PREF IBKR', 'N/A')
                score = self.get_score_for_symbol(symbol, score_type, stock)
                
                try:
                    score_float = float(score) if score != 'N/A' else 0
                    scores.append(score_float)
                    symbols.append(symbol)
                except:
                    scores.append(0)
                    symbols.append(symbol)
            
            if not scores or all(s == 0 for s in scores):
                # Eşit dağıt - TAMAMEN DOLDUR
                equal_lot = (total_lot // len(symbols)) // 100 * 100  # 100'lük yuvarla
                remainder = total_lot - (equal_lot * len(symbols))
                result = {symbol: equal_lot for symbol in symbols}
                # Kalanı ilk hisseye ekle
                if remainder > 0 and symbols:
                    result[symbols[0]] += remainder
                return result
            
            scores_arr = np.array(scores, dtype=np.float64)
            
            # SHORT için tersine çevir (düşük skor = yüksek lot)
            if is_short:
                min_score = scores_arr.min()
                max_score = scores_arr.max()
                if max_score > min_score:
                    scores_arr = max_score - scores_arr + min_score
                    print(f"         🔄 SHORT: Skorlar tersine çevrildi (düşük skor = yüksek lot)")
                else:
                    scores_arr = np.ones_like(scores_arr)
            
            # Normalize et ve alfa uygula
            max_score_normalized = scores_arr.max()
            if max_score_normalized > 0:
                relative_scores = (scores_arr / max_score_normalized) ** self.alpha
                print(f"         📈 Alpha({self.alpha}) uygulandı - En yüksek oran: {relative_scores.max():.3f}")
            else:
                relative_scores = np.ones_like(scores_arr)
            
            # Lotları ölçekle - TAMAMEN DOLDUR
            if relative_scores.sum() > 0:
                raw_lot_alloc = relative_scores / relative_scores.sum() * total_lot
            else:
                raw_lot_alloc = np.ones_like(relative_scores) * (total_lot / len(relative_scores))
            
            # MINIMUM EŞİK KONTROLÜNÜ DEVRE DIŞI BIRAK - TAMAMEN DOLDUR!
            # Minimum eşik kontrolü yapma, tüm lotları dağıt
            print(f"         🔧 Minimum eşik ({min_lot_thresh}) atlanıyor - tam dağılım için")
            
            # Lotları 100'lük sayılara yuvarla
            lot_alloc = np.round(raw_lot_alloc / 100) * 100
            lot_alloc = lot_alloc.astype(int)
            
            # MUTLAKA TOPLAM LOT HAKKINI DOLDUR - AKILLI DAĞILIM
            current_total = lot_alloc.sum()
            difference = total_lot - current_total
            
            if difference != 0:
                print(f"         🔧 Lot farkı düzeltiliyor: {difference:,} lot")
                
                # Farkı orantılı olarak dağıt
                if current_total > 0:
                    # Mevcut dağılıma göre orantılı artış/azalış
                    adjustment_ratio = total_lot / current_total
                    lot_alloc = lot_alloc * adjustment_ratio
                    lot_alloc = np.round(lot_alloc / 100) * 100  # 100'lük yuvarla
                    lot_alloc = lot_alloc.astype(int)
                    
                    # Hala fark varsa, en yüksek skorluya ekle/çıkar
                    final_difference = total_lot - lot_alloc.sum()
                    if final_difference != 0:
                        max_idx = np.argmax(relative_scores)
                        lot_alloc[max_idx] += final_difference
                        print(f"         🎯 Son düzeltme: {final_difference:,} lot en yüksek skorluya eklendi")
                else:
                    # Hiç lot dağıtılmamışsa eşit dağıt
                    equal_lot = (total_lot // len(lot_alloc)) // 100 * 100
                    lot_alloc = np.full_like(lot_alloc, equal_lot)
                    remainder = total_lot - lot_alloc.sum()
                    if remainder > 0:
                        lot_alloc[0] += remainder
            
            # Sonuçları dictionary olarak döndür
            result = {}
            for i, symbol in enumerate(symbols):
                result[symbol] = max(int(lot_alloc[i]), 0)
            
            # MAXALW KISITI UYGULA
            print(f"         🔒 MAXALW kısıtları uygulanıyor...")
            original_total = sum(result.values())
            adjusted_result = {}
            total_reduced = 0
            
            for symbol in symbols:
                original_lot = result[symbol]
                
                # MAXALW değerini al
                maxalw = 'N/A'
                for stock in stocks_list:
                    if stock.get('PREF IBKR', 'N/A') == symbol:
                        maxalw = self.calculate_maxalw(symbol, stock)
                        break
                
                if maxalw != 'N/A' and isinstance(maxalw, (int, float)) and maxalw > 0:
                    max_allowed_lot = int(maxalw * 2)
                    
                    if original_lot > max_allowed_lot:
                        # MAXALW kısıtı devreye giriyor
                        reduced_lot = max_allowed_lot
                        reduction = original_lot - reduced_lot
                        total_reduced += reduction
                        print(f"         📉 {symbol}: {original_lot:,} → {reduced_lot:,} lot (MAXALW={maxalw:.0f} kısıtı)")
                        
                        # AKILLI 600 MINIMUM: Sadece orijinal lot 600+ idi ve MAXALW 600'ün altına düşürdüyse
                        if original_lot >= 600 and reduced_lot < 600:
                            reduced_lot = 600
                            print(f"         📈 {symbol}: MAXALW kısıtı 600'ün altına düşürdü → 600'e yükseltildi")
                        elif original_lot < 600:
                            # Orijinal zaten 600'ün altındaydı, orijinal değere geri çıkar
                            reduced_lot = original_lot
                            print(f"         🔄 {symbol}: Orijinal lot {original_lot:,} idi, geri yükseltildi")
                        
                        adjusted_result[symbol] = reduced_lot
                    else:
                        # MAXALW kısıtı geçmiyor, orijinal değeri koru
                        adjusted_result[symbol] = original_lot
                else:
                    # MAXALW bulunamadı, orijinal değeri koru
                    adjusted_result[symbol] = original_lot
            
            # Final kontrol ve debug
            final_total = sum(adjusted_result.values())
            if total_reduced > 0:
                print(f"         🔒 MAXALW kısıtları: {total_reduced:,} lot azaltıldı")
            print(f"         ✅ MAXALW kısıtlı dağıtım: {final_total:,} lot (Orijinal: {original_total:,})")
            
            if final_total != total_lot:
                difference = final_total - total_lot
                if difference > 0:
                    print(f"         📈 Fazla lot: +{difference:,} (MAXALW kısıtları ve 600 minimum nedeniyle)")
                else:
                    print(f"         📉 Eksik lot: {difference:,}")
            
            return adjusted_result
            
        except Exception as e:
            print(f"   ❌ Basit lot dağılım hatası: {e}")
            # Hata durumunda eşit dağıt ama toplamı koru
            equal_lot = (total_lot // len(stocks_list)) if stocks_list else 100
            return {stock.get('PREF IBKR', 'N/A'): equal_lot for stock in stocks_list}
    
    def calculate_independent_score_based_lot_distribution(self, stocks_list, score_type, direction):
        """Her sekme için bağımsız grup bazlı lot dağılımı - CSV'den dinamik lot hakları"""
        try:
            if not stocks_list:
                return {}
            
            # Her sekme için tam lot hakkı (güncel değerleri kullan)
            if direction == 'LONG':
                total_sekme_lots = getattr(self, 'long_lot_rights', 28000)  # CSV'den güncel Long lot
            else:  # SHORT
                total_sekme_lots = getattr(self, 'short_lot_rights', 12000)   # CSV'den güncel Short lot
            
            # Port Adjuster'dan grup ağırlıklarını al
            port_adjuster = None
            
            # Port Adjuster'ı bul - birkaç yolu dene
            if hasattr(self, 'parent') and self.parent:
                if hasattr(self.parent, 'long_groups'):
                    port_adjuster = self.parent
                    print(f"   ✅ Port Adjuster bulundu: self.parent ({type(self.parent).__name__})")
                elif hasattr(self.parent, 'parent') and hasattr(self.parent.parent, 'long_groups'):
                    port_adjuster = self.parent.parent
                    print(f"   ✅ Port Adjuster bulundu: self.parent.parent ({type(self.parent.parent).__name__})")
            
            # Hala bulamadıysak main_window üzerinden dene
            if not port_adjuster and hasattr(self, 'main_window') and self.main_window:
                if hasattr(self.main_window, 'port_adjuster') and hasattr(self.main_window.port_adjuster, 'long_groups'):
                    port_adjuster = self.main_window.port_adjuster
                    print(f"   ✅ Port Adjuster bulundu: main_window.port_adjuster")
            
            if not port_adjuster:
                print(f"   ❌ Port Adjuster grup ağırlıkları bulunamadı - varsayılan eşit dağılım")
                return self.calculate_score_based_lot_distribution_simple(stocks_list, score_type, total_sekme_lots, direction=='SHORT')
            
            # Grup bazında hisseleri ayır
            groups = {}
            for stock in stocks_list:
                group = stock.get('GRUP', 'unknown')
                if group not in groups:
                    groups[group] = []
                groups[group].append(stock)
            
            print(f"   🎯 {score_type} - {direction} sekmesi ({total_sekme_lots:,} lot):")
            print(f"      📋 CSV'den gelen gruplar: {list(groups.keys())}")
            
            # Port Adjuster gruplarını da göster
            if direction == 'SHORT':
                pa_groups = list(port_adjuster.short_groups.keys())
                print(f"      📋 Port Adjuster SHORT grupları: {pa_groups}")
                print(f"      📊 Port Adjuster SHORT ağırlıkları: {port_adjuster.short_groups}")
            else:
                pa_groups = list(port_adjuster.long_groups.keys())
                print(f"      📋 Port Adjuster LONG grupları: {pa_groups}")
                print(f"      📊 Port Adjuster LONG ağırlıkları: {port_adjuster.long_groups}")
            
            # CSV grupları ile Port Adjuster grupları karşılaştırması
            missing_groups = []
            for csv_group in groups.keys():
                if direction == 'SHORT':
                    if csv_group not in port_adjuster.short_groups:
                        missing_groups.append(csv_group)
                else:
                    if csv_group not in port_adjuster.long_groups:
                        missing_groups.append(csv_group)
            
            if missing_groups:
                print(f"      ⚠️ CSV'de var ama Port Adjuster'da OLMAYAN gruplar: {missing_groups}")
            
            all_lots = {}
            total_distributed = 0
            
            for group, group_stocks in groups.items():
                # Grup ağırlığını al - DEBUG için tüm mevcut grupları göster
                if direction == 'SHORT':
                    group_weight = port_adjuster.short_groups.get(group, 0)
                    available_groups = list(port_adjuster.short_groups.keys())
                else:
                    group_weight = port_adjuster.long_groups.get(group, 0)
                    available_groups = list(port_adjuster.long_groups.keys())
                
                # DEBUG: Grup eşleşme kontrolü
                if group_weight == 0:
                    print(f"      ⚠️  GRUP EŞLEŞMEDI: '{group}' bulunamadı!")
                    print(f"         📋 Mevcut gruplar: {available_groups[:5]}...")
                    
                    # Benzer grup ismi ara
                    for available_group in available_groups:
                        if group.lower() in available_group.lower() or available_group.lower() in group.lower():
                            if direction == 'SHORT':
                                group_weight = port_adjuster.short_groups.get(available_group, 0)
                            else:
                                group_weight = port_adjuster.long_groups.get(available_group, 0)
                            print(f"         🔍 Benzer grup bulundu: '{group}' → '{available_group}' ({group_weight}%)")
                            break
                
                # Bu grubun bu sekmede alabileceği lot hakkını hesapla
                if group_weight > 0:
                    group_lot_rights = int((group_weight / 100) * total_sekme_lots)
                else:
                    group_lot_rights = 0
                
                print(f"      📊 {group}: {group_weight}% × {total_sekme_lots:,} = {group_lot_rights:,} lot ({len(group_stocks)} hisse)")
                
                if group_lot_rights <= 0:
                    # Lot hakkı yoksa 0 ver
                    print(f"         ❌ {group}: Lot hakkı 0 - {len(group_stocks)} hisseye 0 lot verildi")
                    for stock in group_stocks:
                        all_lots[stock.get('PREF IBKR', 'N/A')] = 0
                    continue
                
                # Bu grup için lot dağılımı yap
                group_lots = self.calculate_score_based_lot_distribution_simple(
                    group_stocks, score_type, group_lot_rights, direction=='SHORT'
                )
                
                # Grup içi en iyi hisseleri göster
                if group_lots:
                    group_total_distributed = sum(group_lots.values())
                    sorted_group_lots = sorted(group_lots.items(), key=lambda x: x[1], reverse=True)
                    top_stocks = sorted_group_lots[:3]  # İlk 3'ü göster
                    print(f"         🏆 En yüksek lotlar: {', '.join([f'{s}({l:,})' for s, l in top_stocks])}")
                    
                    # MAXALW kısıtları sonrası grup toplamını göster
                    if group_total_distributed > group_lot_rights:
                        print(f"         📊 Grup toplamı: {group_total_distributed:,} lot (Hedef: {group_lot_rights:,}) - MAXALW/600 minimum nedeniyle fazla")
                    elif group_total_distributed == group_lot_rights:
                        print(f"         📊 Grup toplamı: {group_total_distributed:,}/{group_lot_rights:,} lot ✅ (100.0%)")
                    else:
                        print(f"         📊 Grup toplamı: {group_total_distributed:,}/{group_lot_rights:,} lot ({group_total_distributed/group_lot_rights*100:.1f}%)")
                    
                    # KRITIK KONTROL: Grup ağırlığı 0 ama lot alıyorsa HATA!
                    if group_weight == 0 and group_total_distributed > 0:
                        print(f"         🚨 HATA: {group} %0 ağırlık ama {group_total_distributed:,} lot aldı!")
                else:
                    print(f"         ❌ {group}: Lot dağılımı başarısız!")
                
                # Sonuçları birleştir
                all_lots.update(group_lots)
                total_distributed += sum(group_lots.values())
            
            print(f"   ✅ {score_type} ({direction}) toplam: {total_distributed:,} lot")
            print(f"   📈 Hedef: {total_sekme_lots:,} lot - Fark: {total_sekme_lots - total_distributed:,} lot\n")
            
            return all_lots
            
        except Exception as e:
            print(f"   ❌ {score_type} bağımsız lot dağılım hatası: {e}")
            return {stock.get('PREF IBKR', 'N/A'): 100 for stock in stocks_list}
    
    def save_results(self):
        """Sonuçları CSV dosyasına kaydet"""
        try:
            # Long verilerini al
            long_data = []
            for item in self.long_tree.get_children():
                values = self.long_tree.item(item)['values']
                long_data.append({
                    'Grup': values[0],
                    'Sembol': values[1],
                    'FINAL_THG': values[2],
                    'SHORT_FINAL': values[3],
                    'SMI': values[4],
                    'MAXALW': values[5],
                    'Hesaplanan_Lot': values[6],
                    'Final_Lot': values[7],
                    'Mevcut_Lot': values[8],
                    'Alinabilir_Lot': values[9],
                    'Durum': values[10]
                })
            
            # Short verilerini al
            short_data = []
            for item in self.short_tree.get_children():
                values = self.short_tree.item(item)['values']
                short_data.append({
                    'Grup': values[0],
                    'Sembol': values[1],
                    'SHORT_FINAL': values[2],
                    'FINAL_THG': values[3],
                    'SMI': values[4],
                    'MAXALW': values[5],
                    'Hesaplanan_Lot': values[6],
                    'Final_Lot': values[7],
                    'Mevcut_Lot': values[8],
                    'Alinabilir_Lot': values[9],
                    'Durum': values[10]
                })
            
            # Long CSV'ye kaydet
            if long_data:
                long_df = pd.DataFrame(long_data)
                long_filename = 'final_thg_long_distribution.csv'
                long_df.to_csv(long_filename, index=False, encoding='utf-8-sig')
                print(f"[FINAL THG] Long sonuçlar {long_filename} dosyasına kaydedildi")
            
            # Short CSV'ye kaydet
            if short_data:
                short_df = pd.DataFrame(short_data)
                short_filename = 'final_thg_short_distribution.csv'
                short_df.to_csv(short_filename, index=False, encoding='utf-8-sig')
                print(f"[FINAL THG] Short sonuçlar {short_filename} dosyasına kaydedildi")
            
            if long_data or short_data:
                messagebox.showinfo("Başarılı", f"Sonuçlar kaydedildi!\nLong: {len(long_data)} hisse\nShort: {len(short_data)} hisse")
            else:
                messagebox.showwarning("Uyarı", "Kaydedilecek veri bulunamadı!")
            
        except Exception as e:
            messagebox.showerror("Hata", f"Sonuçlar kaydedilirken hata: {e}")
    
    def get_file_specific_rules(self):
        """
        Her dosya için özel kuralları döndürür (ntumcsvport.py'den alındı)
        """
        rules = {
            'ssfinekheldsolidbig.csv': {
                'long_percent': 25, 'long_multiplier': 1.5,
                'short_percent': 20, 'short_multiplier': 0.6,
                'max_short': 2
            },
            'ssfinekheldbesmaturlu.csv': {
                'long_percent': 15, 'long_multiplier': 1.5,
                'short_percent': 10, 'short_multiplier': 0.3,
                'max_short': 2
            },
            'ssfinekheldtitrekhc.csv': {
                'long_percent': 15, 'long_multiplier': 1.5,
                'short_percent': 10, 'short_multiplier': 0.3,
                'max_short': 2
            },
            'ssfinekheldkuponlukreorta.csv': {
                'long_percent': 20, 'long_multiplier': 1.45,
                'short_percent': 30, 'short_multiplier': 0.7,
                'max_short': 3
            },
            'ssfinekheldflr.csv': {
                'long_percent': 30, 'long_multiplier': 1.4,
                'short_percent': 20, 'short_multiplier': 0.6,
                'max_short': 2
            },
            'ssfinekheldkuponlukreciliz.csv': {
                'long_percent': 20, 'long_multiplier': 1.5,
                'short_percent': 30, 'short_multiplier': 0.7,
                'max_short': 3
            },
            'ssfinekheldcommonsuz.csv': {
                'long_percent': 10, 'long_multiplier': 1.6,
                'short_percent': 25, 'short_multiplier': 0.5,
                'max_short': 3
            },
            'ssfineknotbesmaturlu.csv': {
                'long_percent': 10, 'long_multiplier': 1.6,
                'short_percent': 10, 'short_multiplier': 0.3,
                'max_short': 2
            },
            'ssfinekrumoreddanger.csv': {
                'long_percent': 5, 'long_multiplier': 1.75,
                'short_percent': 10, 'short_multiplier': 0.3,
                'max_short': 2
            },
            'ssfinekheldgarabetaltiyedi.csv': {
                'long_percent': 30, 'long_multiplier': 1.45,
                'short_percent': 20, 'short_multiplier': 0.6,
                'max_short': 3
            },
            'ssfinekheldnff.csv': {
                'long_percent': 25, 'long_multiplier': 1.45,
                'short_percent': 20, 'short_multiplier': 0.5,
                'max_short': 2
            },
            'ssfinekheldotelremorta.csv': {
                'long_percent': 15, 'long_multiplier': 1.55,
                'short_percent': 20, 'short_multiplier': 0.5,
                'max_short': 3
            },
            'ssfineksalakilliquid.csv': {
                'long_percent': 10, 'long_multiplier': 1.55,
                'short_percent': 15, 'short_multiplier': 0.4,
                'max_short': 2
            },
            'ssfinekheldff.csv': {
                'long_percent': 30, 'long_multiplier': 1.4,
                'short_percent': 20, 'short_multiplier': 0.5,
                'max_short': 2
            },
            'ssfinekhighmatur.csv': {
                'long_percent': 35, 'long_multiplier': 1.35,
                'short_percent': 7, 'short_multiplier': 0.25,
                'max_short': 2
            },
            'ssfineknotcefilliquid.csv': {
                'long_percent': 15, 'long_multiplier': 1.5,
                'short_percent': 15, 'short_multiplier': 0.5,
                'max_short': 2
            },
            'ssfinekhelddeznff.csv': {
                'long_percent': 25, 'long_multiplier': 1.4,
                'short_percent': 30, 'short_multiplier': 0.7,
                'max_short': 2
            },
            'ssfinekheldkuponlu.csv': {
                'long_percent': 35, 'long_multiplier': 1.3,
                'short_percent': 40, 'short_multiplier': 0.80,
                'max_short': 999  # Sınırsız
            }
        }
        return rules
    
    def limit_by_company(self, stocks_df, direction='LONG', original_df=None):
        """
        Aynı şirketten (CMON) gelen hisseleri sınırlar (ntumcsvport.py'den alındı)
        """
        if len(stocks_df) == 0:
            return stocks_df
        
        # Orijinal dosyadaki tüm hisseleri kullan
        if original_df is not None:
            full_df = original_df
        else:
            full_df = stocks_df
        
        # CMON'a göre grupla (filtrelenmiş hisseler)
        company_groups = stocks_df.groupby('CMON')
        limited_stocks = []
        
        for company, group in company_groups:
            # Orijinal dosyadaki bu şirketin toplam hisse sayısını bul
            company_total_count = len(full_df[full_df['CMON'] == company])
            # 1.6'ya böl ve normal yuvarla (0.5+ yukarı, 0.4- aşağı)
            # Minimum 1 hisse seçilebilir
            max_allowed = max(1, round(company_total_count / 1.6))
            
            print(f"      📊 {company}: {company_total_count} hisse → maksimum {max_allowed} seçilebilir")
            
            if direction == 'LONG':
                # Live skor kolonu varsa onu kullan, yoksa Final_FB_skor kullan
                live_cols = [col for col in group.columns if col.endswith('_live')]
                if live_cols:
                    live_col = live_cols[0]
                    selected = group.nlargest(max_allowed, live_col)
                    print(f"        ✅ {company}: En yüksek {live_col} ile {len(selected)} hisse seçildi")
                else:
                    selected = group.nlargest(max_allowed, 'Final_FB_skor')
                    print(f"        ⚠️ {company}: Fallback - Final_FB_skor ile {len(selected)} hisse seçildi")
            else:  # SHORT
                # Live skor kolonu varsa onu kullan, yoksa Final_SFS_skor kullan
                live_cols = [col for col in group.columns if col.endswith('_live')]
                if live_cols:
                    live_col = live_cols[0]
                    selected = group.nsmallest(max_allowed, live_col)
                    print(f"        ✅ {company}: En düşük {live_col} ile {len(selected)} hisse seçildi")
                else:
                    selected = group.nsmallest(max_allowed, 'Final_SFS_skor')
                    print(f"        ⚠️ {company}: Fallback - Final_SFS_skor ile {len(selected)} hisse seçildi")
            
            limited_stocks.append(selected)
        
        if limited_stocks:
            return pd.concat(limited_stocks, ignore_index=True)
        else:
            return pd.DataFrame()
    
    def select_stocks_by_score_type_with_mini450_snapshot(self, file_name, df, score_type, direction='LONG'):
        """
        Mini450'den anlık skor snapshot alarak ntumcsvport.py mantığıyla hisse seçer
        score_type: 'Final_BB_skor', 'Final_FB_skor', 'Final_SAS_skor', 'Final_SFS_skor'
        direction: 'LONG' (yüksek iyi) veya 'SHORT' (düşük iyi)
        """
        try:
            print(f"   🔍 Mini450'den {score_type} snapshot alınıyor...")
            
            # Dosya için özel kuralları al
            file_basename = os.path.basename(file_name)
            if file_basename in self.file_rules:
                rules = self.file_rules[file_basename]
            else:
                rules = {
                    'long_percent': 25, 'long_multiplier': 1.5,
                    'short_percent': 25, 'short_multiplier': 0.7,
                    'max_short': 3
                }
            
            # Mini450'den anlık skorları çek ve DataFrame'e ekle
            enhanced_df = df.copy()
            snapshot_scores = []
            
            for idx, row in df.iterrows():
                symbol = row.get('PREF IBKR', 'N/A')
                
                # Mini450'den anlık skor al
                live_score = self.get_score_for_symbol(symbol, score_type, row)
                enhanced_df.at[idx, f'{score_type}_live'] = live_score
                
                if isinstance(live_score, (int, float)):
                    snapshot_scores.append(live_score)
                    # Sadece ilk 3 hisseyi göster (spam'i önlemek için)
                    if len(snapshot_scores) <= 3:
                        print(f"      📊 {symbol}: {score_type}={live_score:.4f}")
                elif len(snapshot_scores) <= 3:
                    print(f"      ❌ {symbol}: {score_type} değeri geçersiz: {live_score}")
            
            if len(snapshot_scores) == 0:
                print(f"   ❌ Mini450'den {score_type} için geçerli değer bulunamadı!")
                return pd.DataFrame()
            
            # Geçerli skorları filtrele
            live_column = f'{score_type}_live'
            valid_df = enhanced_df[pd.notna(enhanced_df[live_column]) & (enhanced_df[live_column] != 'N/A')].copy()
            valid_df[live_column] = pd.to_numeric(valid_df[live_column], errors='coerce')
            valid_df = valid_df[pd.notna(valid_df[live_column])]
            
            if len(valid_df) == 0:
                print(f"   ❌ {score_type} için geçerli snapshot değer bulunamadı!")
                return pd.DataFrame()
            
            # ntumcsvport.py mantığını uygula
            if direction == 'LONG':
                # LONG için yüksek skorlar iyi (ntumcsvport.py mantığı)
                avg_score = valid_df[live_column].mean()
                print(f"   📈 Mini450 Ortalama {score_type}: {avg_score:.4f}")
                print(f"   📋 LONG Kurallar: {rules['long_percent']}% + {rules['long_multiplier']}x")
                
                # 1. Kriter: Ortalama × çarpan'dan büyük olanlar
                long_candidates = valid_df[valid_df[live_column] >= (avg_score * rules['long_multiplier'])].copy()
                long_candidates = long_candidates.sort_values(live_column, ascending=False)
                
                # 2. Kriter: Top %X
                top_count = math.ceil(len(valid_df) * rules['long_percent'] / 100)
                top_stocks = valid_df.nlargest(top_count, live_column)
                
                # İki kriterin kesişimi
                candidates_set = set(long_candidates['PREF IBKR'])
                top_set = set(top_stocks['PREF IBKR'])
                intersection = candidates_set.intersection(top_set)
                
                # Kesişimdeki hisseleri al
                selected_stocks = valid_df[valid_df['PREF IBKR'].isin(intersection)].copy()
                
                print(f"   🎯 LONG - {rules['long_multiplier']}x ortalama kriteri: {len(long_candidates)} hisse")
                print(f"   🎯 LONG - Top {rules['long_percent']}% kriteri: {len(top_stocks)} hisse")
                print(f"   ✅ LONG - Kesişim: {len(selected_stocks)} hisse")
                
                # Şirket sınırını uygula (ntumcsvport.py mantığı)
                selected_stocks_limited = self.limit_by_company(selected_stocks, 'LONG', valid_df)
                print(f"   📊 LONG - Şirket sınırı sonrası: {len(selected_stocks_limited)} hisse")
                
                # DEBUG: Seçilen hisselerin skorlarını göster
                if len(selected_stocks_limited) > 0:
                    print(f"   🎯 SEÇILEN LONG HİSSELERİN {score_type} SKORLARI:")
                    selected_with_scores = selected_stocks_limited.copy()
                    selected_with_scores = selected_with_scores.sort_values(live_column, ascending=False)
                    for i, (_, row) in enumerate(selected_with_scores.head(5).iterrows()):
                        symbol = row['PREF IBKR']
                        score_val = row[live_column]
                        print(f"      {i+1}. {symbol}: {score_val:.4f}")
                
                return selected_stocks_limited
                
            else:  # SHORT
                # SHORT için düşük skorlar iyi (ntumcsvport.py mantığı)
                avg_score = valid_df[live_column].mean()
                print(f"   📉 Mini450 Ortalama {score_type}: {avg_score:.4f}")
                print(f"   📋 SHORT Kurallar: {rules['short_percent']}% + {rules['short_multiplier']}x (Max: {rules['max_short']})")
                
                # 1. Kriter: Ortalama × çarpan'dan küçük olanlar
                short_candidates = valid_df[valid_df[live_column] <= (avg_score * rules['short_multiplier'])].copy()
                short_candidates = short_candidates.sort_values(live_column, ascending=True)
                
                # 2. Kriter: Bottom %X
                bottom_count = math.ceil(len(valid_df) * rules['short_percent'] / 100)
                bottom_stocks = valid_df.nsmallest(bottom_count, live_column)
                
                # İki kriterin kesişimi
                candidates_set = set(short_candidates['PREF IBKR'])
                bottom_set = set(bottom_stocks['PREF IBKR'])
                intersection = candidates_set.intersection(bottom_set)
                
                # Kesişimdeki hisseleri al
                selected_stocks = valid_df[valid_df['PREF IBKR'].isin(intersection)].copy()
                
                # SHORT sınırını uygula
                if len(selected_stocks) > rules['max_short']:
                    print(f"   ⚠️ SHORT sınırı uygulanıyor: {len(selected_stocks)} → {rules['max_short']}")
                    selected_stocks = selected_stocks.nsmallest(rules['max_short'], live_column)
                
                print(f"   🎯 SHORT - {rules['short_multiplier']}x ortalama kriteri: {len(short_candidates)} hisse")
                print(f"   🎯 SHORT - Bottom {rules['short_percent']}% kriteri: {len(bottom_stocks)} hisse")
                print(f"   ✅ SHORT - Kesişim: {len(selected_stocks)} hisse")
                
                # Şirket sınırını uygula (ntumcsvport.py mantığı)
                selected_stocks_limited = self.limit_by_company(selected_stocks, 'SHORT', valid_df)
                print(f"   📊 SHORT - Şirket sınırı sonrası: {len(selected_stocks_limited)} hisse")
                
                # DEBUG: Seçilen hisselerin skorlarını göster
                if len(selected_stocks_limited) > 0:
                    print(f"   🎯 SEÇILEN SHORT HİSSELERİN {score_type} SKORLARI:")
                    selected_with_scores = selected_stocks_limited.copy()
                    selected_with_scores = selected_with_scores.sort_values(live_column, ascending=True)
                    for i, (_, row) in enumerate(selected_with_scores.head(5).iterrows()):
                        symbol = row['PREF IBKR']
                        score_val = row[live_column]
                        print(f"      {i+1}. {symbol}: {score_val:.4f}")
                
                return selected_stocks_limited
            
        except Exception as e:
            print(f"   ❌ {direction} Mini450 snapshot seçim hatası ({score_type}): {e}")
            return pd.DataFrame()

    def select_stocks_by_score_type(self, file_name, df, score_type, direction='LONG'):
        """
        Mini450 snapshot ile seçim yap
        """
        return self.select_stocks_by_score_type_with_mini450_snapshot(file_name, df, score_type, direction)

    def select_stocks_by_rules(self, file_name, df):
        """
        Geriye uyumluluk için - FB Long mantığını kullanır
        """
        return self.select_stocks_by_score_type(file_name, df, 'Final_FB_skor', 'LONG')
    
    def apply_tumcsv_rules(self):
        """
        YENİ SİSTEM: Mini450'den grup bazlı hisse seçimi
        Her gruptan %10 hisse seç, lot dağılımını alfa katsayısı ile yap
        """
        try:
            print("🚀 YENİ TUMCSV AYARLAMASI BAŞLIYOR...")
            print("=" * 80)
            print("📊 Mini450 bazlı grup seçim sistemi")
            print("📈 Her gruptan %10 hisse seçilecek (en yüksek FINAL BB skorlu)")
            
            # Önce CSV'den güncel lot haklarını yükle
            self.load_lot_rights_from_csv()
            
            # Sekme başlıklarını güncel lot haklarıyla güncelle
            self.bb_long_lot_info.config(text=f"BB Long ({self.long_lot_rights:,} lot/sekme) - İşleniyor...")
            self.fb_long_lot_info.config(text=f"FB Long ({self.long_lot_rights:,} lot/sekme) - İşleniyor...")
            self.sas_short_lot_info.config(text=f"SAS Short ({self.short_lot_rights:,} lot/sekme) - İşleniyor...")
            self.sfs_short_lot_info.config(text=f"SFS Short ({self.short_lot_rights:,} lot/sekme) - İşleniyor...")
            print(f"✅ TUMCSV işlemi öncesi sekme başlıkları güncellendi: Long={self.long_lot_rights:,}, Short={self.short_lot_rights:,}")
            
            # Mini450 verilerini al
            if not hasattr(self.main_window, 'df') or self.main_window.df is None:
                messagebox.showerror("Hata", "Önce Mini450 görünümünü açın!")
                return
            
            print(f"📊 Mini450 verisi: {len(self.main_window.df)} hisse")
            
            # Port Adjuster grup ağırlıklarını al - Önce yükle
            if not hasattr(self, 'long_group_weights') or not hasattr(self, 'short_group_weights') or not self.long_group_weights or not self.short_group_weights:
                print("🔄 Grup ağırlıkları yüklenmemiş, şimdi yükleniyor...")
                self.load_group_weights()
            
            long_group_weights = self.long_group_weights
            short_group_weights = self.short_group_weights
            
            print(f"📊 CSV'den yüklenen grup ağırlıkları:")
            print(f"   📈 LONG: {len(long_group_weights)} grup")
            print(f"   📉 SHORT: {len(short_group_weights)} grup")
            
            # Port Adjuster'dan güncel lot haklarını al
            if hasattr(self.port_adjuster, 'long_lot_rights') and hasattr(self.port_adjuster, 'short_lot_rights'):
                total_long_rights = self.port_adjuster.long_lot_rights
                total_short_rights = self.port_adjuster.short_lot_rights
                print(f"📊 Port Adjuster'dan güncel lot hakları: Long={total_long_rights:,}, Short={total_short_rights:,}")
            else:
                # CSV'den varsayılan değerler (70%/30%)
                total_long_rights = 28000
                total_short_rights = 12000
                print(f"⚠️ Port Adjuster lot hakları bulunamadı, varsayılan kullanılıyor: Long={total_long_rights:,}, Short={total_short_rights:,}")
            
            print(f"🔍 Long grup ağırlıkları: {long_group_weights}")
            print(f"🔍 Short grup ağırlıkları: {short_group_weights}")
            
            # Güncel lot haklarını sınıf değişkeni olarak sakla
            self.total_long_rights = total_long_rights
            self.total_short_rights = total_short_rights
            
            # Debug: Saklanan değerleri kontrol et
            print(f"🔒 Sınıf değişkenlerine kaydedildi:")
            print(f"   📊 self.total_long_rights = {self.total_long_rights:,}")
            print(f"   📊 self.total_short_rights = {self.total_short_rights:,}")
            
            all_long_stocks = []
            all_short_stocks = []
            
            # LONG grupları için işlem (sadece LONG hakkı olanlar)
            print("\n🟢 LONG GRUPLAR İŞLENİYOR...")
            long_groups_only = {k: v for k, v in long_group_weights.items() if v > 0}
            print(f"🔍 LONG hakkı olan gruplar: {long_groups_only}")
            
            for group in long_groups_only:
                long_weight = long_group_weights.get(group, 0)
                print(f"\n📊 İşleniyor: {group} (SADECE LONG: {long_weight}%)")
                
                # Mini450'den bu gruba ait hisseleri bul
                group_stocks = self.get_group_stocks_from_mini450(group)
                
                if len(group_stocks) == 0:
                    print(f"   ⚠️ {group} grubunda hisse bulunamadı")
                    continue
                
                print(f"   📊 Toplam {len(group_stocks)} hisse bulundu")
                
                # Her skor türü için %10 hisse seç (minimum 2)
                selected_count = max(2, round(len(group_stocks) * 0.1))  # En az 2 hisse
                print(f"   🎯 %10 kural: {len(group_stocks)} hisse → {selected_count} hisse seçilecek (minimum 2)")
                
                # SADECE LONG skorları için seçim yap
                bb_stocks = self.select_top_stocks_by_score(group_stocks, 'Final_BB_skor', selected_count, 'LONG')
                fb_stocks = self.select_top_stocks_by_score(group_stocks, 'Final_FB_skor', selected_count, 'LONG')
                
                print(f"   📊 LONG Seçilen hisseler:")
                print(f"      🔵 BB Long: {len(bb_stocks)} hisse")
                print(f"      🟢 FB Long: {len(fb_stocks)} hisse")
                
                # LONG hisseleri listeye ekle
                for stock in bb_stocks:
                    stock['GRUP'] = group
                    stock['SKOR_TURU'] = 'BB_LONG'
                    all_long_stocks.append(stock)
                
                for stock in fb_stocks:
                    stock['GRUP'] = group
                    stock['SKOR_TURU'] = 'FB_LONG'
                    all_long_stocks.append(stock)
            
            # SHORT grupları için işlem (sadece SHORT hakkı olanlar)
            print("\n🔴 SHORT GRUPLAR İŞLENİYOR...")
            short_groups_only = {k: v for k, v in short_group_weights.items() if v > 0}
            print(f"🔍 SHORT hakkı olan gruplar: {short_groups_only}")
            
            for group in short_groups_only:
                short_weight = short_group_weights.get(group, 0)
                print(f"\n📊 İşleniyor: {group} (SADECE SHORT: {short_weight}%)")
                
                # Mini450'den bu grupa ait hisseleri bul
                group_stocks = self.get_group_stocks_from_mini450(group)
                
                if len(group_stocks) == 0:
                    print(f"   ⚠️ {group} grubunda hisse bulunamadı")
                    continue
                
                print(f"   📊 Toplam {len(group_stocks)} hisse bulundu")
                
                # Her skor türü için %10 hisse seç (minimum 2)
                selected_count = max(2, round(len(group_stocks) * 0.1))  # En az 2 hisse
                print(f"   🎯 %10 kural: {len(group_stocks)} hisse → {selected_count} hisse seçilecek (minimum 2)")
                
                # SADECE SHORT skorları için seçim yap
                sas_stocks = self.select_top_stocks_by_score(group_stocks, 'Final_SAS_skor', selected_count, 'SHORT')
                sfs_stocks = self.select_top_stocks_by_score(group_stocks, 'Final_SFS_skor', selected_count, 'SHORT')
                
                print(f"   📊 SHORT Seçilen hisseler:")
                print(f"      🟠 SAS Short: {len(sas_stocks)} hisse")
                print(f"      🔴 SFS Short: {len(sfs_stocks)} hisse")
                
                # SHORT hisseleri listeye ekle
                for stock in sas_stocks:
                    stock['GRUP'] = group
                    stock['SKOR_TURU'] = 'SAS_SHORT'
                    all_short_stocks.append(stock)
                
                for stock in sfs_stocks:
                    stock['GRUP'] = group
                    stock['SKOR_TURU'] = 'SFS_SHORT'
                    all_short_stocks.append(stock)
            
            # Sonuçları göster
            if all_long_stocks or all_short_stocks:
                print(f"\n📊 TUMCSV AYARLAMASI TAMAMLANDI!")
                print(f"   🟢 Toplam LONG: {len(all_long_stocks)} hisse")
                print(f"   🔴 Toplam SHORT: {len(all_short_stocks)} hisse")
                
                # Sonuçları tablolarda göster - 4 ayrı sekme için
                self.display_tumcsv_results_by_score_type(all_long_stocks, all_short_stocks)
                
                # Sonuçları CSV'ye kaydet
                if all_long_stocks:
                    long_df = pd.DataFrame(all_long_stocks)
                    long_df.to_csv('final_fb_sfs_tumcsv_long_stocks.csv', index=False)
                    print(f"   📁 LONG hisseler kaydedildi: final_fb_sfs_tumcsv_long_stocks.csv")
                
                if all_short_stocks:
                    short_df = pd.DataFrame(all_short_stocks)
                    short_df.to_csv('final_fb_sfs_tumcsv_short_stocks.csv', index=False)
                    print(f"   📁 SHORT hisseler kaydedildi: final_fb_sfs_tumcsv_short_stocks.csv")
                
                # Başarılı mesajı göster (Allowed modunda gösterme)
                if not (hasattr(self.main_window, 'runall_allowed_mode') and self.main_window.runall_allowed_mode):
                    messagebox.showinfo("Başarılı", f"TUMCSV ayarlaması tamamlandı!\nLONG: {len(all_long_stocks)} hisse\nSHORT: {len(all_short_stocks)} hisse")
                else:
                    print(f"[TUMCSV] ℹ️ Allowed modu aktif - 'TUMCSV ayarlaması tamamlandı' penceresi gösterilmedi")
                    # Popup'ı otomatik kapatmak için kısa bir gecikme ekle
                    if self.main_window:
                        self.main_window.after(500, lambda: self.main_window.addnewpos_close_messagebox())
                        self.main_window.after(500, lambda: self.main_window.runall_auto_confirm_messagebox())
                
            else:
                print(f"❌ Hiç hisse seçilemedi!")
                # RUNALL Allowed modunda uyarı mesajını gösterme
                if not (hasattr(self.main_window, 'runall_allowed_mode') and self.main_window.runall_allowed_mode):
                    messagebox.showwarning("Uyarı", "Hiç hisse seçilemedi!")
                else:
                    print(f"[TUMCSV] ℹ️ Allowed modu aktif - Uyarı mesajı gösterilmedi")
                    if self.main_window:
                        self.main_window.after(500, lambda: self.main_window.addnewpos_close_messagebox())
                
        except Exception as e:
            print(f"❌ TUMCSV ayarlaması hatası: {e}")
            # RUNALL Allowed modunda hata mesajını gösterme
            if not (hasattr(self.main_window, 'runall_allowed_mode') and self.main_window.runall_allowed_mode):
                messagebox.showerror("Hata", f"TUMCSV ayarlaması hatası: {e}")
            else:
                print(f"[TUMCSV] ℹ️ Allowed modu aktif - Hata mesajı gösterilmedi")
                if self.main_window:
                    self.main_window.after(500, lambda: self.main_window.addnewpos_close_messagebox())
    
    def get_current_position(self, symbol):
        """Hisse için mevcut pozisyonu al"""
        try:
            if hasattr(self.parent, 'main_window') and hasattr(self.parent.main_window, 'current_positions'):
                positions = self.parent.main_window.current_positions
                for pos in positions:
                    if pos.get('symbol', '').upper() == symbol.upper():
                        return pos.get('quantity', 0)
            return 0
        except Exception as e:
            print(f"[JFIN] ❌ {symbol} mevcut pozisyon alma hatası: {e}")
            return 0

    def calculate_addable_lot_jfin(self, maxalw, current_position, calculated_lot=0):
        """Eklenebilir lot hesapla - Long için (JFIN için)"""
        try:
            maxalw_num = float(maxalw) if maxalw != 'N/A' else 0
            current_num = float(current_position) if current_position != 'N/A' else 0
            
            # Long için: MAXALW - Mevcut Pozisyon (en fazla bu kadar eklenebilir!)
            addable = maxalw_num - current_num
            
            # print(f"[JFIN] 📊 Long eklenebilir lot: MAXALW={maxalw_num}, Mevcut={current_num}, Eklenebilir={addable}")
            return max(0, addable)  # Negatif olamaz
        except Exception as e:
            print(f"[JFIN] ❌ Long eklenebilir lot hesaplama hatası: {e}")
            return 0

    def calculate_addable_lot_short_jfin(self, maxalw, current_position, calculated_lot=0):
        """Eklenebilir lot hesapla - Short için (mutlak değerler) (JFIN için)"""
        try:
            maxalw_num = float(maxalw) if maxalw != 'N/A' else 0
            current_num = abs(float(current_position)) if current_position != 'N/A' else 0  # Short için mutlak değer
            
            # Short için: MAXALW - |Mevcut Pozisyon| (en fazla bu kadar eklenebilir!)
            addable = maxalw_num - current_num
            
            # print(f"[JFIN] 📊 Short eklenebilir lot: MAXALW={maxalw_num}, |Mevcut|={current_num}, Eklenebilir={addable}")
            return max(0, addable)  # Negatif olamaz
        except Exception as e:
            print(f"[JFIN] ❌ Short eklenebilir lot hesaplama hatası: {e}")
            return 0

    def calculate_group_avg_final_fb(self, group):
        """Grup ortalama Final FB hesapla - Take Profit Panel mantığıyla"""
        try:
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
            
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            if hasattr(self.parent, 'main_window') and hasattr(self.parent.main_window, 'df') and not self.parent.main_window.df.empty:
                group_rows = self.parent.main_window.df[self.parent.main_window.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_FB_skor' in self.parent.main_window.df.columns:
                    final_fb_values = group_rows['Final_FB_skor'].dropna()
                    final_fb_values = pd.to_numeric(final_fb_values, errors='coerce').dropna()
                    final_fb_values = final_fb_values[final_fb_values > 0]
                    if not final_fb_values.empty:
                        avg_fb = final_fb_values.mean()
                        print(f"[JFIN] 📊 {group} grubu ortalama Final FB: {avg_fb:.2f} ({len(final_fb_values)} geçerli hisse)")
                        return avg_fb
            
            return 0
            
        except Exception as e:
            print(f"[JFIN] ❌ {group} grup ortalama Final FB hesaplama hatası: {e}")
            return 0

    def calculate_group_avg_final_sfs(self, group):
        """Grup ortalama Final SFS hesapla - Take Profit Panel mantığıyla"""
        try:
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
            
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            if hasattr(self.parent, 'main_window') and hasattr(self.parent.main_window, 'df') and not self.parent.main_window.df.empty:
                group_rows = self.parent.main_window.df[self.parent.main_window.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_SFS_skor' in self.parent.main_window.df.columns:
                    final_sfs_values = group_rows['Final_SFS_skor'].dropna()
                    final_sfs_values = pd.to_numeric(final_sfs_values, errors='coerce').dropna()
                    final_sfs_values = final_sfs_values[final_sfs_values > 0]
                    if not final_sfs_values.empty:
                        avg_sfs = final_sfs_values.mean()
                        print(f"[JFIN] 📊 {group} grubu ortalama Final SFS: {avg_sfs:.2f} ({len(final_sfs_values)} geçerli hisse)")
                        return avg_sfs
            
            return 0
            
        except Exception as e:
            print(f"[JFIN] ❌ {group} grup ortalama Final SFS hesaplama hatası: {e}")
            return 0

    def calculate_fbplagr(self, symbol, group):
        """FBPlagr hesapla - Take Profit Panel mantığıyla"""
        try:
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
            
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            if hasattr(self.parent, 'main_window') and hasattr(self.parent.main_window, 'df') and not self.parent.main_window.df.empty:
                group_rows = self.parent.main_window.df[self.parent.main_window.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_FB_skor' in self.parent.main_window.df.columns:
                    final_fb_values = group_rows['Final_FB_skor'].dropna()
                    final_fb_values = pd.to_numeric(final_fb_values, errors='coerce').dropna()
                    final_fb_values = final_fb_values[final_fb_values > 0]
                    
                    if symbol in group_rows['PREF IBKR'].values:
                        symbol_row = group_rows[group_rows['PREF IBKR'] == symbol]
                        if not symbol_row.empty:
                            symbol_fb = pd.to_numeric(symbol_row['Final_FB_skor'].iloc[0], errors='coerce')
                            if not pd.isna(symbol_fb) and symbol_fb > 0:
                                # Bu sembolün grup içindeki sıralamasını hesapla
                                rank = (final_fb_values >= symbol_fb).sum()
                                total_count = len(final_fb_values)
                                plagr = rank / total_count if total_count > 0 else 0
                                return f"{plagr:.4f}"
            
            return "N/A"
            
        except Exception as e:
            print(f"[JFIN] ❌ {symbol} FBPlagr hesaplama hatası: {e}")
            return "N/A"

    def calculate_sfsplagr(self, symbol, group):
        """SFSPlagr hesapla - Take Profit Panel mantığıyla"""
        try:
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
            
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            if hasattr(self.parent, 'main_window') and hasattr(self.parent.main_window, 'df') and not self.parent.main_window.df.empty:
                group_rows = self.parent.main_window.df[self.parent.main_window.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_SFS_skor' in self.parent.main_window.df.columns:
                    final_sfs_values = group_rows['Final_SFS_skor'].dropna()
                    final_sfs_values = pd.to_numeric(final_sfs_values, errors='coerce').dropna()
                    final_sfs_values = final_sfs_values[final_sfs_values > 0]
                    
                    if symbol in group_rows['PREF IBKR'].values:
                        symbol_row = group_rows[group_rows['PREF IBKR'] == symbol]
                        if not symbol_row.empty:
                            symbol_sfs = pd.to_numeric(symbol_row['Final_SFS_skor'].iloc[0], errors='coerce')
                            if not pd.isna(symbol_sfs) and symbol_sfs > 0:
                                # Bu sembolün grup içindeki sıralamasını hesapla
                                rank = (final_sfs_values >= symbol_sfs).sum()
                                total_count = len(final_sfs_values)
                                plagr = rank / total_count if total_count > 0 else 0
                                return f"{plagr:.4f}"
            
            return "N/A"
            
        except Exception as e:
            print(f"[JFIN] ❌ {symbol} SFSPlagr hesaplama hatası: {e}")
            return "N/A"

    def get_final_fb_from_csv(self, symbol):
        """CSV'den Final FB skorunu al"""
        try:
            if hasattr(self.parent, 'main_window') and hasattr(self.parent.main_window, 'df') and not self.parent.main_window.df.empty:
                symbol_row = self.parent.main_window.df[self.parent.main_window.df['PREF IBKR'] == symbol]
                if not symbol_row.empty and 'Final_FB_skor' in self.parent.main_window.df.columns:
                    return pd.to_numeric(symbol_row['Final_FB_skor'].iloc[0], errors='coerce')
            return 0
        except Exception as e:
            print(f"[JFIN] ❌ {symbol} Final FB alma hatası: {e}")
            return 0

    def get_final_sfs_from_csv(self, symbol):
        """CSV'den Final SFS skorunu al"""
        try:
            if hasattr(self.parent, 'main_window') and hasattr(self.parent.main_window, 'df') and not self.parent.main_window.df.empty:
                symbol_row = self.parent.main_window.df[self.parent.main_window.df['PREF IBKR'] == symbol]
                if not symbol_row.empty and 'Final_SFS_skor' in self.parent.main_window.df.columns:
                    return pd.to_numeric(symbol_row['Final_SFS_skor'].iloc[0], errors='coerce')
            return 0
        except Exception as e:
            print(f"[JFIN] ❌ {symbol} Final SFS alma hatası: {e}")
            return 0

    def calculate_fbratgr(self, symbol, final_fb, avg_final_fb):
        """FBRatgr hesapla"""
        try:
            if avg_final_fb > 0 and final_fb > 0:
                ratgr = final_fb / avg_final_fb
                return f"{ratgr:.4f}"
            return "N/A"
        except Exception as e:
            print(f"[JFIN] ❌ {symbol} FBRatgr hesaplama hatası: {e}")
            return "N/A"

    def calculate_sfsratgr(self, symbol, final_sfs, avg_final_sfs):
        """SFSRatgr hesapla"""
        try:
            if avg_final_sfs > 0 and final_sfs > 0:
                ratgr = final_sfs / avg_final_sfs
                return f"{ratgr:.4f}"
            return "N/A"
        except Exception as e:
            print(f"[JFIN] ❌ {symbol} SFSRatgr hesaplama hatası: {e}")
            return "N/A"

    def calculate_fbtot(self, fbplagr, fbratgr):
        """FBtot hesapla - Take Profit Panel mantığıyla (TOPLAMA)"""
        try:
            if fbplagr != "N/A" and fbratgr != "N/A":
                plagr_num = float(fbplagr)
                ratgr_num = float(fbratgr)
                fbtot = plagr_num + ratgr_num  # TOPLAMA, çarpma değil!
                return f"{fbtot:.4f}"
            return "N/A"
        except Exception as e:
            print(f"[JFIN] ❌ FBtot hesaplama hatası: {e}")
            return "N/A"

    def calculate_sfstot(self, sfsplagr, sfsratgr):
        """SFStot hesapla - Take Profit Panel mantığıyla (TOPLAMA)"""
        try:
            if sfsplagr != "N/A" and sfsratgr != "N/A":
                plagr_num = float(sfsplagr)
                ratgr_num = float(sfsratgr)
                sfstot = plagr_num + ratgr_num  # TOPLAMA, çarpma değil!
                return f"{sfstot:.4f}"
            return "N/A"
        except Exception as e:
            print(f"[JFIN] ❌ SFStot hesaplama hatası: {e}")
            return "N/A"

    def calculate_fbtot_for_symbol(self, symbol, group):
        """Hisse için FBtot değerini hesapla - Take Profit Panel mantığıyla"""
        try:
            grup_value = group
            avg_final_fb = 0
            fbplagr = "N/A"
            fbratgr = "N/A"
            
            if grup_value and grup_value != 'N/A':
                avg_final_fb = self.calculate_group_avg_final_fb(grup_value)
                
                fbplagr = self.calculate_fbplagr(symbol, grup_value)
                
                final_fb = self.get_final_fb_from_csv(symbol)
                fbratgr = self.calculate_fbratgr(symbol, final_fb, avg_final_fb)
                
                fbtot = self.calculate_fbtot(fbplagr, fbratgr)
                
                print(f"[JFIN] ✅ {symbol} -> Grup: {grup_value}, Avg Final FB: {avg_final_fb:.2f}, FBPlagr: {fbplagr}, FBRatgr: {fbratgr}, FBtot: {fbtot}")
                return fbtot
            
            return "N/A"
            
        except Exception as e:
            print(f"[JFIN] ❌ {symbol} FBtot hesaplama hatası: {e}")
            return "N/A"

    def calculate_sfstot_for_symbol(self, symbol, group):
        """Hisse için SFStot değerini hesapla - Take Profit Panel mantığıyla"""
        try:
            grup_value = group
            avg_final_sfs = 0
            sfsplagr = "N/A"
            sfsratgr = "N/A"
            
            if grup_value and grup_value != 'N/A':
                avg_final_sfs = self.calculate_group_avg_final_sfs(grup_value)
                
                sfsplagr = self.calculate_sfsplagr(symbol, grup_value)
                
                final_sfs = self.get_final_sfs_from_csv(symbol)
                sfsratgr = self.calculate_sfsratgr(symbol, final_sfs, avg_final_sfs)
                
                sfstot = self.calculate_sfstot(sfsplagr, sfsratgr)
                
                print(f"[JFIN] ✅ {symbol} -> Grup: {grup_value}, Avg Final SFS: {avg_final_sfs:.2f}, SFSPlagr: {sfsplagr}, SFSRatgr: {sfsratgr}, SFStot: {sfstot}")
                return sfstot
            
            return "N/A"
            
        except Exception as e:
            print(f"[JFIN] ❌ {symbol} SFStot hesaplama hatası: {e}")
            return "N/A"
    
    def show_jfin_orders(self, order_type, percentage):
        """JFIN emirleri için onay penceresi göster"""
        try:
            print(f"\n[JFIN] 🔄 {order_type} %{percentage} emirleri hazırlanıyor...")
            
            # ADDNEWPOS kontrolü: Maksimum açılabilecek lot hesapla
            max_addable_lot = None
            if hasattr(self.main_window, 'addnewpos_final_thg') and self.main_window.addnewpos_final_thg == self:
                # Pot Toplam ve Pot Max Lot hesapla
                exposure_info = self.main_window.check_exposure_limits()
                pot_total = exposure_info.get('pot_total', 0)
                pot_max_lot = exposure_info.get('pot_max_lot', 63636)
                
                if pot_total > 0:
                    max_addable_lot = pot_max_lot - pot_total
                    print(f"[ADDNEWPOS] 📊 Maksimum açılabilecek lot: {max_addable_lot:,} (Pot Max: {pot_max_lot:,} - Pot Toplam: {pot_total:,})")
                    self.main_window.log_message(f"📊 ADDNEWPOS: Maksimum açılabilecek lot: {max_addable_lot:,}")
            
            # Sekme türüne göre doğru tree'yi al
            tree_map = {
                'BB': self.bb_long_tree,
                'FB': self.fb_long_tree, 
                'SAS': self.sas_short_tree,
                'SFS': self.sfs_short_tree,
                'SoftFB': self.fb_long_tree,  # SoftFront Buy FB sekmesini kullanır
                'SoftFS': self.sfs_short_tree  # SoftFront Sell SFS sekmesini kullanır
            }
            
            if order_type not in tree_map:
                messagebox.showerror("Hata", f"Geçersiz emir türü: {order_type}")
                return
            
            tree = tree_map[order_type]
            
            # Tree'deki GÖRÜNÜR hisseleri oku (filtrelenmiş olanlar)
            orders = []
            visible_items = []

            # Filtreleme mantığını düzelt
            if order_type == 'BB':
                if hasattr(self, 'bb_filtered_data') and self.bb_filtered_data:
                    visible_items = self.bb_filtered_data
                else:
                    visible_items = tree.get_children()
            elif order_type == 'FB':
                if hasattr(self, 'fb_filtered_data') and self.fb_filtered_data:
                    visible_items = self.fb_filtered_data
                else:
                    visible_items = tree.get_children()
            elif order_type == 'SAS':
                if hasattr(self, 'sas_filtered_data') and self.sas_filtered_data:
                    visible_items = self.sas_filtered_data
                else:
                    visible_items = tree.get_children()
            elif order_type == 'SFS':
                if hasattr(self, 'sfs_filtered_data') and self.sfs_filtered_data:
                    visible_items = self.sfs_filtered_data
                else:
                    visible_items = tree.get_children()
            elif order_type == 'SoftFB':
                if hasattr(self, 'fb_filtered_data') and self.fb_filtered_data:
                    visible_items = self.fb_filtered_data
                else:
                    visible_items = tree.get_children()
            elif order_type == 'SoftFS':
                if hasattr(self, 'sfs_filtered_data') and self.sfs_filtered_data:
                    visible_items = self.sfs_filtered_data
                else:
                    visible_items = tree.get_children()
            else:
                visible_items = tree.get_children()

            print(f"[JFIN] 🔍 {order_type} için {len(visible_items)} görünür hisse bulundu")
            
            for item in visible_items:
                values = tree.item(item)['values']
                print(f"[JFIN] 🔍 Hisse: {values[1] if len(values) > 1 else 'Unknown'}, Kolon sayısı: {len(values)}")
                if len(values) >= 11:  # En az 11 kolon olmalı (Mevcut Pozisyon eklendi)
                    try:
                        grup = values[0]
                        symbol = values[1]

                        # Final score güvenli dönüştürme
                        try:
                            final_score = float(values[2]) if values[2] not in ['N/A', '', None] else 0
                        except (ValueError, TypeError):
                            final_score = 0

                        # SMI değerini al (index 5)
                        try:
                            smi = values[5] if values[5] not in ['N/A', '', None] else 'N/A'
                        except (IndexError, ValueError, TypeError):
                            smi = 'N/A'
                        
                        # SMA63 chg değerini al (index 6)
                        try:
                            sma63_chg = values[6] if values[6] not in ['N/A', '', None] else 'N/A'
                        except (IndexError, ValueError, TypeError):
                            sma63_chg = 'N/A'
                        
                        # MAXALW değerini al (index 8) - GORT eklendikten sonra index kaydı
                        try:
                            maxalw_str = values[8] if len(values) > 8 and values[8] not in ['N/A', '', None] else '0'
                            if isinstance(maxalw_str, str):
                                maxalw = float(maxalw_str.replace(',', '')) if maxalw_str.replace(',', '').replace('.', '').replace('-', '').isdigit() else 0
                            else:
                                maxalw = float(maxalw_str) if maxalw_str else 0
                        except (IndexError, ValueError, TypeError):
                            maxalw = 0
                        
                        # Mevcut Pozisyon değerini al (index 9) - GORT eklendikten sonra index kaydı
                        try:
                            current_pos_str = values[9] if len(values) > 9 and values[9] not in ['N/A', '', None] else '0'
                            if isinstance(current_pos_str, str):
                                current_position = float(current_pos_str.replace(',', '')) if current_pos_str.replace(',', '').replace('.', '').replace('-', '').isdigit() else 0
                            else:
                                current_position = float(current_pos_str) if current_pos_str else 0
                        except (IndexError, ValueError, TypeError):
                            current_position = 0
                        
                        # Hesaplanan Lot değerini al (index 10) - GORT eklendikten sonra index kaydı
                        try:
                            calculated_lot_str = values[10] if len(values) > 10 and values[10] not in ['N/A', '', None] else '0'
                            if isinstance(calculated_lot_str, str):
                                calculated_lot = float(calculated_lot_str.replace(',', '')) if calculated_lot_str.replace(',', '').replace('.', '').replace('-', '').isdigit() else 0
                            else:
                                calculated_lot = float(calculated_lot_str) if calculated_lot_str else 0
                        except (IndexError, ValueError, TypeError):
                            calculated_lot = 0
                        
                        # Eklenebilir lot hesapla
                        eklenebilir_lot = self.calculate_addable_lot_jfin(maxalw, current_position, calculated_lot)
                        
                        # Eğer eklenebilir lot 200'den azsa, bu pozisyonu atla
                        if eklenebilir_lot < 200:
                            print(f"[JFIN] ⚠️ {symbol} atlandı - Eklenebilir lot: {eklenebilir_lot} (MAXALW: {maxalw}, Mevcut: {current_position})")
                            continue
                        
                        print(f"[JFIN] ✅ {symbol} eklendi - Eklenebilir lot: {eklenebilir_lot}")
                        
                        # Yüzdesel lot hesapla: İlk ekrandaki hesaplanan lot'un yüzdesi
                        yuzdelik_lot = calculated_lot * (percentage / 100)
                        
                        # Ama eklenebilir lot'tan fazla olamaz!
                        final_lot = min(yuzdelik_lot, eklenebilir_lot)
                        
                        print(f"[JFIN] 📊 {symbol}: Hesaplanan={calculated_lot}, %{percentage}={yuzdelik_lot}, Eklenebilir={eklenebilir_lot}, Final={final_lot}")
                        
                        # %100 haricinde 100'lük yuvarlama yap
                        if percentage == 100:
                            # %100 için normal yuvarlama
                            final_lot = int(round(final_lot))
                        else:
                            # %25, %50, %75 için 100'lük aşağı yuvarlama
                            final_lot = int(final_lot // 100) * 100
                            # Minimum 100 lot
                            if final_lot < 100:
                                final_lot = 100
                        
                        # En az 100 lot olsun
                        if final_lot >= 100:
                            orders.append({
                                'group': grup,
                                'symbol': symbol,
                                'score': final_score,
                                'smi': smi,
                                'sma63_chg': sma63_chg,
                                'eklenebilir_lot': eklenebilir_lot,
                                'calculated_lot': final_lot,  # Final lot kullan
                                'order_type': order_type,
                                'current_position': current_position
                            })
                            print(f"   ✅ {symbol}: {calculated_lot} → %{percentage} = {yuzdelik_lot} → MAX({yuzdelik_lot}, {eklenebilir_lot}) = {final_lot} lot")
                        else:
                            print(f"   ❌ {symbol}: {final_lot} lot < 100, atlandı")
                            
                    except Exception as e:
                        print(f"   ❌ {symbol if 'symbol' in locals() else 'Unknown'} işleme hatası: {e}")
                        continue
            
            if not orders:
                messagebox.showwarning("Uyarı", f"JFIN {order_type} %{percentage} için uygun hisse bulunamadı!")
                return
            
            # ADDNEWPOS kontrolü: Lotları maksimum açılabilecek lota göre güncelle
            if max_addable_lot is not None and max_addable_lot > 0:
                # Mevcut toplam lot hesapla
                current_total_lot = sum(order.get('calculated_lot', 0) for order in orders)
                
                if current_total_lot != max_addable_lot:
                    # Lotları orantılı olarak güncelle (weighted)
                    # Eğer current_total_lot < max_addable_lot ise artır, > ise azalt
                    ratio = max_addable_lot / current_total_lot
                    print(f"[ADDNEWPOS] 🔄 Exposure limitine göre lot güncelleme: {current_total_lot:,} → {max_addable_lot:,} (Oran: {ratio:.3f})")
                    
                    for order in orders:
                        original_lot = order.get('calculated_lot', 0)
                        updated_lot = int(original_lot * ratio)
                        # 100'ün katlarına yuvarla
                        updated_lot = (updated_lot // 100) * 100
                        # Minimum 200 lot kontrolü (ADDNEWPOS için)
                        if updated_lot < 200:
                            updated_lot = 200  # Minimum 200 lot
                        order['calculated_lot'] = updated_lot
                        print(f"   {order['symbol']}: {original_lot:,} → {updated_lot:,} lot")
                    
                    final_total = sum(o.get('calculated_lot', 0) for o in orders)
                    self.main_window.log_message(f"🔄 ADDNEWPOS: Exposure limitine göre lotlar güncellendi: {current_total_lot:,} → {final_total:,} lot (Hedef: {max_addable_lot:,})")
            
            # Minimum 200 lot kontrolü - 200 lot'tan küçük emirleri filtrele
            orders_before_filter = len(orders)
            orders = [order for order in orders if order.get('calculated_lot', 0) >= 200]
            orders_after_filter = len(orders)
            
            if orders_before_filter != orders_after_filter:
                filtered_count = orders_before_filter - orders_after_filter
                print(f"[ADDNEWPOS] ⚠️ {filtered_count} emir 200 lot'tan küçük olduğu için filtrelendi")
                self.main_window.log_message(f"⚠️ {filtered_count} emir 200 lot'tan küçük olduğu için filtrelendi")
            
            print(f"[JFIN] ✅ {len(orders)} adet {order_type} emri hazırlandı")
            
            # Emir onay penceresini aç
            self.show_jfin_order_confirmation(order_type, percentage, orders)
            
        except Exception as e:
            print(f"[JFIN] ❌ {order_type} %{percentage} hazırlama hatası: {e}")
            messagebox.showerror("Hata", f"JFIN emirleri hazırlanırken hata: {e}")
    
    def calculate_order_price(self, symbol, order_type):
        """Emir türüne göre fiyat hesapla"""
        try:
            # Ana sayfadan market data al
            if hasattr(self.main_window, 'hammer') and self.main_window.hammer:
                market_data = self.main_window.hammer.get_market_data(symbol)
                if not market_data:
                    return "N/A"
                
                bid = float(market_data.get('bid', 0))
                ask = float(market_data.get('ask', 0))
                last = float(market_data.get('last', 0))
                
                if order_type == 'BB':  # Bid Buy
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        price = bid + (spread * 0.15)
                        return f"${price:.2f}"
                elif order_type == 'FB':  # Front Buy
                    if last > 0:
                        price = last + 0.01
                        return f"${price:.2f}"
                elif order_type == 'SoftFB':  # SoftFront Buy
                    if last > 0:
                        # SoftFront Buy koşullarını kontrol et
                        if not self.check_soft_front_buy_conditions(bid, ask, last, symbol):
                            return "KOŞUL YOK"
                        
                        # LRPAN fiyatını al (gerçek print fiyatı)
                        lrpan_price = self.get_lrpan_price(symbol)
                        if lrpan_price is not None:
                            price = lrpan_price + 0.01
                            print(f"[SOFT FRONT BUY] ✅ {symbol}: LRPAN fiyatı kullanılıyor - ${lrpan_price:.2f} + $0.01 = ${price:.2f}")
                        else:
                            price = last + 0.01
                            print(f"[SOFT FRONT BUY] ⚠️ {symbol}: LRPAN fiyatı bulunamadı, last kullanılıyor - ${last:.2f} + $0.01 = ${price:.2f}")
                        return f"${price:.2f}"
                elif order_type == 'SAS':  # Ask Sell
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        price = ask - (spread * 0.15)
                        return f"${price:.2f}"
                elif order_type == 'SFS':  # Front Sell
                    if last > 0:
                        price = last - 0.01
                        return f"${price:.2f}"
                elif order_type == 'SoftFS':  # SoftFront Sell
                    if last > 0:
                        # SoftFront Sell koşullarını kontrol et
                        if not self.check_soft_front_sell_conditions(bid, ask, last, symbol):
                            return "KOŞUL YOK"
                        
                        # LRPAN fiyatını al (gerçek print fiyatı)
                        lrpan_price = self.get_lrpan_price(symbol)
                        if lrpan_price is not None:
                            price = lrpan_price - 0.01
                            print(f"[SOFT FRONT SELL] ✅ {symbol}: LRPAN fiyatı kullanılıyor - ${lrpan_price:.2f} - $0.01 = ${price:.2f}")
                        else:
                            price = last - 0.01
                            print(f"[SOFT FRONT SELL] ⚠️ {symbol}: LRPAN fiyatı bulunamadı, last kullanılıyor - ${last:.2f} - $0.01 = ${price:.2f}")
                        return f"${price:.2f}"
            
            return "N/A"
            
        except Exception as e:
            print(f"[JFIN] ❌ {symbol} fiyat hesaplama hatası: {e}")
            return "N/A"
    
    def get_lrpan_price(self, symbol):
        """Hisse için LRPAN fiyatını al (100/200/300 lot olan son print)"""
        try:
            if self.main_window and hasattr(self.main_window, 'hammer') and self.main_window.hammer and self.main_window.hammer.connected:
                # getTicks komutu ile son 10 tick'i al
                tick_data = self.main_window.hammer.get_ticks(symbol, lastFew=10)
                
                if tick_data and 'data' in tick_data and tick_data['data']:
                    ticks = tick_data['data']
                    
                    # Sondan başlayarak 100, 200, 300 lot olanları ara
                    for i in range(len(ticks) - 1, -1, -1):
                        tick = ticks[i]
                        size = tick.get('s', 0)
                        price = tick.get('p', 0)
                        
                        # Sadece 100, 200, 300 lot olanları kontrol et
                        if size in [100, 200, 300]:
                            print(f"[LRPAN PRICE] ✅ {symbol}: LRPAN fiyatı bulundu - {size} lot @ ${price:.2f}")
                            return price
                    
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
    
    def show_jfin_order_confirmation(self, order_type, percentage, orders):
        """JFIN emir onay penceresi"""
        try:
            import tkinter as tk
            from tkinter import ttk
            
            # RUNALL Allowed modunu kontrol et
            runall_allowed_mode = False
            if hasattr(self.main_window, 'runall_allowed_mode'):
                runall_allowed_mode = self.main_window.runall_allowed_mode
            
            # Emir türü açıklamaları
            order_descriptions = {
                'BB': 'Bid Buy (bid + spread*0.15 e hidden buy)',
                'FB': 'Front Buy (last + 0.01 e hidden buy)', 
                'SoftFB': 'SoftFront Buy (last + 0.01 e hidden buy - koşullu)',
                'SAS': 'Ask Sell (ask - spread*0.15 e hidden sell)',
                'SFS': 'Front Sell (last - 0.01 e hidden sell)',
                'SoftFS': 'SoftFront Sell (last - 0.01 e hidden sell - koşullu)'
            }
            
            win = tk.Toplevel(self.win)
            win.title(f"JFIN {order_type} %{percentage} - Emir Onayı")
            win.geometry("1400x700")
            win.transient(self.win)
            # grab_set() kaldırıldı - minimize edilebilir olması için
            
            # JFIN penceresini main_window'a bildir (ADDNEWPOS için)
            if hasattr(self.main_window, 'addnewpos_jfin_window'):
                self.main_window.addnewpos_jfin_window = win
            
            # Başlık frame - minimize butonu ile
            title_frame = ttk.Frame(win)
            title_frame.pack(fill='x', padx=10, pady=5)
            
            # Sol taraf - başlık bilgileri
            title_left = ttk.Frame(title_frame)
            title_left.pack(side='left', fill='x', expand=True)
            
            title_text = f"JFIN {order_type} %{percentage} Emirleri"
            description = order_descriptions.get(order_type, '')
            
            ttk.Label(title_left, text=title_text, font=('Arial', 14, 'bold')).pack(anchor='w')
            ttk.Label(title_left, text=description, font=('Arial', 10)).pack(anchor='w')
            ttk.Label(title_left, text=f"Toplam {len(orders)} emir", font=('Arial', 10, 'bold')).pack(anchor='w')
            
            # Sağ taraf - minimize butonu
            window_controls = ttk.Frame(title_frame)
            window_controls.pack(side='right')
            
            # Alta Al (Minimize) butonu
            minimize_btn = ttk.Button(window_controls, text="🗕 Alta Al", width=10,
                                      command=lambda: win.iconify())
            minimize_btn.pack(side='left', padx=2)
            
            # Toplu seçim butonları
            button_frame = ttk.Frame(win)
            button_frame.pack(fill='x', padx=10, pady=5)
            
            ttk.Button(button_frame, text="Tümünü Seç", 
                      command=lambda: self.select_all_orders(order_tree, True)).pack(side='left', padx=5)
            ttk.Button(button_frame, text="Tümünü Kaldır", 
                      command=lambda: self.select_all_orders(order_tree, False)).pack(side='left', padx=5)
            
            # Emirler tablosu - SMA63 chg kolonu eklendi + Mevcut Lot kolonu
            columns = ('Seç', 'Grup', 'Sembol', 'Skor', 'SMI', 'SMA63 chg', 'Emir Fiyatı', 'Mevcut Lot', 'Eklenebilir Lot', 'Hesaplanan Lot', 'Emir Türü')
            order_tree = ttk.Treeview(win, columns=columns, show='headings', height=20)
            
            # Kolon başlıkları
            for col in columns:
                order_tree.heading(col, text=col)
                if col == 'Seç':
                    order_tree.column(col, width=60)
                elif col in ['Grup', 'Sembol']:
                    order_tree.column(col, width=100)
                elif col == 'SMI':
                    order_tree.column(col, width=70)
                elif col == 'SMA63 chg':
                    order_tree.column(col, width=75)
                elif col == 'Emir Türü':
                    order_tree.column(col, width=80)
                elif col == 'Emir Fiyatı':
                    order_tree.column(col, width=90)
                elif col == 'Mevcut Lot':
                    order_tree.column(col, width=100)
                else:
                    order_tree.column(col, width=120)
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(win, orient='vertical', command=order_tree.yview)
            order_tree.configure(yscrollcommand=scrollbar.set)
            
            order_tree.pack(side='left', fill='both', expand=True, padx=(10, 0), pady=5)
            scrollbar.pack(side='right', fill='y', padx=(0, 10), pady=5)
            
            # Emirleri doldur
            for i, order in enumerate(orders):
                # Score değerini güvenli formatlama
                try:
                    score_text = f"{float(order['score']):.2f}" if order['score'] and order['score'] != 'N/A' else 'N/A'
                except (ValueError, TypeError):
                    score_text = 'N/A'
                
                # Emir fiyatını hesapla
                order_price = self.calculate_order_price(order['symbol'], order['order_type'])
                
                # Eklenebilir lot güvenli formatlama
                try:
                    eklenebilir_text = f"{float(order['eklenebilir_lot']):,.0f}"
                except (ValueError, TypeError):
                    eklenebilir_text = str(order['eklenebilir_lot'])
                
                # Hesaplanan lot güvenli formatlama
                try:
                    calculated_text = f"{int(order['calculated_lot']):,}"
                except (ValueError, TypeError):
                    calculated_text = str(order['calculated_lot'])
                
                # Mevcut lot güvenli formatlama
                try:
                    current_lot_text = f"{float(order.get('current_position', 0)):,.0f}"
                except (ValueError, TypeError):
                    current_lot_text = '0'
                
                values = (
                    '☑',  # Seçili (checkbox style)
                    order['group'],
                    order['symbol'], 
                    score_text,
                    order.get('smi', 'N/A'),  # SMI kolonu
                    order.get('sma63_chg', 'N/A'),  # SMA63 chg kolonu
                    order_price,
                    current_lot_text,  # Mevcut Lot kolonu
                    eklenebilir_text,
                    calculated_text,
                    order['order_type']
                )
                order_tree.insert('', 'end', values=values, tags=('selected',))
            
            # Tek tıklama olayı - seçim toggle
            def toggle_selection(event):
                # Tıklanan konumu belirle
                region = order_tree.identify_region(event.x, event.y)
                if region == "cell":
                    # Tıklanan satırı al
                    item = order_tree.identify_row(event.y)
                    if item:
                        current_values = list(order_tree.item(item)['values'])
                        # Checkbox toggle
                        if current_values[0] == '☑':  # Seçili ise
                            current_values[0] = '☐'  # Seçimi kaldır
                            order_tree.item(item, values=current_values, tags=('unselected',))
                        else:  # Seçili değil ise
                            current_values[0] = '☑'  # Seç
                            order_tree.item(item, values=current_values, tags=('selected',))
            
            # Tek tık ile seçim
            order_tree.bind('<Button-1>', toggle_selection)
            
            # Alt butonlar
            bottom_frame = ttk.Frame(win)
            bottom_frame.pack(fill='x', padx=10, pady=5)
            
            def send_orders():
                """Seçili emirleri gönder - Excluded ticker kontrolü ile"""
                selected_orders = []
                excluded_count = 0
                
                for item in order_tree.get_children():
                    values = order_tree.item(item)['values']
                    if values[0] == '☑':  # Seçili ise (checkbox dolu)
                        symbol = values[2]
                        
                        # Excluded ticker kontrolü
                        if hasattr(self.main_window, 'is_ticker_excluded') and self.main_window.is_ticker_excluded(symbol):
                            excluded_count += 1
                            print(f"[JFIN] 🚫 {symbol} excluded - emir gönderilmeyecek")
                            continue
                        
                        selected_orders.append({
                            'symbol': symbol,
                            'price': values[6],  # Emir fiyatı (SMA63 chg eklendi, 5->6)
                            'lot': int(str(values[9]).replace(',', '')),  # Hesaplanan lot (SMA63 chg eklendi, 7->8, 8->9)
                            'order_type': values[10]  # Emir türü (SMA63 chg eklendi, 8->9, 9->10)
                        })
                
                if excluded_count > 0:
                    print(f"[JFIN] 🚫 {excluded_count} excluded ticker emir listesinden çıkarıldı")
                
                if selected_orders:
                    # Gerçek emir gönderme (Hammer Pro API)
                    success_count = 0
                    error_count = 0
                    
                    for order in selected_orders:
                        try:
                            symbol = order['symbol']
                            lot = order['lot']
                            order_type = order['order_type']
                            price_str = str(order['price']).replace('$', '').strip()  # $ işaretini kaldır
                            
                            # N/A kontrolü
                            if price_str in ['N/A', 'KOŞUL YOK', '', 'None', 'nan']:
                                print(f"[JFIN] ⚠️ {symbol}: Fiyat N/A ({price_str}), emir atlanıyor")
                                error_count += 1
                                continue
                            
                            try:
                                price = float(price_str)
                                if price <= 0:
                                    print(f"[JFIN] ⚠️ {symbol}: Geçersiz fiyat ({price}), emir atlanıyor")
                                    error_count += 1
                                    continue
                            except (ValueError, TypeError):
                                print(f"[JFIN] ⚠️ {symbol}: Fiyat parse edilemedi: {price_str}, emir atlanıyor")
                                error_count += 1
                                continue
                            
                            # Emir türüne göre side belirle
                            if order_type in ['BB', 'FB', 'SoftFB']:  # Buy emirleri
                                side = 'BUY'
                            else:  # SAS, SFS, SoftFS - Sell emirleri
                                side = 'SELL'
                            
                            # Lot bölücü kontrolü
                            if hasattr(self.main_window, 'lot_divider_enabled') and self.main_window.lot_divider_enabled:
                                # Lot'u 200er parçalara böl
                                lot_parts = self.divide_lot_size(lot)
                                print(f"[JFIN] 📦 Lot Bölücü: AÇIK - {lot} lot → {lot_parts}")
                                
                                # Her parça için emir gönder
                                for i, part_lot in enumerate(lot_parts, 1):
                                    if hasattr(self.main_window, 'mode_manager'):
                                        success = self.main_window.mode_manager.place_order(
                                            symbol=symbol,
                                            side=side,
                                            quantity=part_lot,
                                            price=price,
                                            order_type="LIMIT",
                                            hidden=True
                                        )
                                        
                                        if success:
                                            success_count += 1
                                            print(f"[JFIN] ✅ {symbol}: {part_lot} lot {order_type} @ ${price:.2f} - Parça {i}/{len(lot_parts)} - Başarılı")
                                        else:
                                            error_count += 1
                                            print(f"[JFIN] ❌ {symbol}: {part_lot} lot {order_type} @ ${price:.2f} - Parça {i}/{len(lot_parts)} - Başarısız")
                                    else:
                                        error_count += 1
                                        print(f"[JFIN] ❌ Mode manager bulunamadı!")
                            else:
                                # Normal emir (lot bölücü kapalı)
                                # Mode manager kullan (IBKR veya HAMPRO)
                                if hasattr(self.main_window, 'mode_manager'):
                                    success = self.main_window.mode_manager.place_order(
                                        symbol=symbol,
                                        side=side,
                                        quantity=lot,
                                        price=price,
                                        order_type="LIMIT",
                                        hidden=True
                                    )
                                    
                                    if success:
                                        success_count += 1
                                        print(f"[JFIN] ✅ {symbol}: {lot} lot {order_type} @ ${price:.2f} - Başarılı")
                                    else:
                                        error_count += 1
                                        print(f"[JFIN] ❌ {symbol}: {lot} lot {order_type} @ ${price:.2f} - Başarısız")
                                else:
                                    error_count += 1
                                    print(f"[JFIN] ❌ Mode manager bulunamadı!")
                        
                        except Exception as e:
                            error_count += 1
                            print(f"[JFIN] ❌ Emir gönderme hatası ({order['symbol']}): {e}")
                    
                    # Sonuç mesajı
                    if success_count > 0:
                        # RUNALL Allowed modunda messagebox gösterme
                        if not (hasattr(self.main_window, 'runall_allowed_mode') and self.main_window.runall_allowed_mode):
                            messagebox.showinfo("Başarılı", 
                                              f"✅ {success_count} emir başarılı\n❌ {error_count} emir başarısız")
                        
                        # RUNALL döngüsünde ise 1 dakika bekleyip emirleri iptal et ve tekrar başla
                        if hasattr(self.main_window, 'runall_loop_running') and self.main_window.runall_loop_running:
                            self.main_window.log_message("✅ ADDNEWPOS emirleri gönderildi, 1 dakika sonra emirler iptal edilecek")
                            
                            # ADDNEWPOS pencerelerini hemen kapat
                            def close_addnewpos_windows():
                                try:
                                    # JFIN penceresini kapat
                                    if hasattr(self.main_window, 'addnewpos_jfin_window'):
                                        try:
                                            if self.main_window.addnewpos_jfin_window.winfo_exists():
                                                self.main_window.addnewpos_jfin_window.destroy()
                                        except:
                                            pass
                                    
                                    # Final THG penceresini kapat
                                    if hasattr(self.main_window, 'addnewpos_final_thg') and self.main_window.addnewpos_final_thg:
                                        try:
                                            if hasattr(self.main_window.addnewpos_final_thg, 'win') and self.main_window.addnewpos_final_thg.win.winfo_exists():
                                                self.main_window.addnewpos_final_thg.win.destroy()
                                        except:
                                            pass
                                    
                                    # Port Adjuster penceresini kapat
                                    if hasattr(self.main_window, 'addnewpos_port_adjuster') and self.main_window.addnewpos_port_adjuster:
                                        try:
                                            if hasattr(self.main_window.addnewpos_port_adjuster, 'win') and self.main_window.addnewpos_port_adjuster.win.winfo_exists():
                                                self.main_window.addnewpos_port_adjuster.win.destroy()
                                        except:
                                            pass
                                except:
                                    pass
                            
                            # Pencere kapatmayı hemen yap
                            close_addnewpos_windows()
                            
                            # 1 dakika sonra emirleri iptal et ve tekrar başla
                            def schedule_cancel_and_restart():
                                if hasattr(self.main_window, 'runall_loop_running') and self.main_window.runall_loop_running:
                                    self.main_window.log_message("⏰ 1 dakika geçti, emirler iptal ediliyor...")
                                    self.main_window.runall_cancel_orders_and_restart()
                            
                            self.main_window.after(60000, schedule_cancel_and_restart)
                            self.main_window.runall_addnewpos_callback_set = False
                            
                            # JFIN penceresini kapat
                            try:
                                if win.winfo_exists():
                                    win.destroy()
                            except:
                                pass
                        else:
                            # RUNALL döngüsü çalışmıyorsa pencereyi kapat
                            try:
                                if win.winfo_exists():
                                    win.destroy()
                            except:
                                pass
                    else:
                        # RUNALL Allowed modunda messagebox gösterme
                        if not (hasattr(self.main_window, 'runall_allowed_mode') and self.main_window.runall_allowed_mode):
                            messagebox.showerror("Hata", f"Hiç emir gönderilemedi! ({error_count} hata)")
                        
                        # Hiç emir gönderilemediyse pencereyi kapat
                        try:
                            if win.winfo_exists():
                                win.destroy()
                        except:
                            pass
                else:
                    messagebox.showwarning("Uyarı", "Hiç emir seçilmedi!")
            
            def cancel_orders():
                win.destroy()
                
            def save_to_trades_csv():
                """Seçili emirleri trades.csv formatında kaydet"""
                try:
                    selected_orders = []
                    for item in order_tree.get_children():
                        values = order_tree.item(item)['values']
                        if values[0] == '☑':  # Seçili ise (checkbox dolu)
                            selected_orders.append({
                                'symbol': values[2],
                                'price': values[6],  # Emir fiyatı (SMA63 chg eklendi, 5->6)
                                'lot': int(str(values[9]).replace(',', '')),  # Hesaplanan lot (SMA63 chg eklendi, 7->8, 8->9)
                                'order_type': values[10]  # Emir türü (SMA63 chg eklendi, 8->9, 9->10)
                            })
                    
                    if not selected_orders:
                        messagebox.showwarning("Uyarı", "Hiç emir seçilmedi!")
                        return
                    
                    print(f"[TRADES CSV] 🔄 {len(selected_orders)} seçili emir trades.csv'ye kaydediliyor...")
                    
                    # CSV satırları oluştur
                    csv_rows = []
                    
                    for order in selected_orders:
                        try:
                            symbol = order['symbol']
                            lot = order['lot']
                            order_type = order['order_type']
                            price_str = order['price'].replace('$', '')  # $ işaretini kaldır
                            price = float(price_str)
                            
                            # Emir türüne göre action belirle
                            if order_type in ['BB', 'FB']:  # Buy emirleri
                                action = 'BUY'
                            else:  # SAS, SFS - Sell emirleri
                                action = 'SELL'
                            
                            # Lot Bölücü aktifse lotları böl
                            if self.main_window and hasattr(self.main_window, 'lot_divider_enabled') and self.main_window.lot_divider_enabled:
                                lot_parts = self.divide_lot_size(lot)
                                print(f"[TRADES CSV] 🔄 {symbol}: {lot} lot -> {lot_parts} parçalara bölündü")
                                
                                # Her parça için ayrı CSV satırı oluştur
                                for i, lot_part in enumerate(lot_parts):
                                    csv_row = [
                                        action,                           # Action: BUY/SELL
                                        lot_part,                         # Quantity: Lot miktarı
                                        symbol,                          # Symbol: Ticker
                                        'STK',                          # SecType: STK
                                        'SMART/AMEX',                   # Exchange: SMART/AMEX
                                        'USD',                          # Currency: USD
                                        'DAY',                          # TimeInForce: DAY
                                        'LMT',                          # OrderType: LMT
                                        round(price, 2),                # LmtPrice: Fiyat
                                        'Basket',                       # BasketTag: Basket
                                        'U21016730',                    # Account: U21016730
                                        'Basket',                       # OrderRef: Basket
                                        'TRUE',                         # Hidden: TRUE
                                        'TRUE'                          # OutsideRth: TRUE
                                    ]
                                    csv_rows.append(csv_row)
                            else:
                                # Lot Bölücü kapalıysa normal şekilde tek satır
                                csv_row = [
                                    action,                           # Action: BUY/SELL
                                    lot,                             # Quantity: Lot miktarı
                                    symbol,                          # Symbol: Ticker
                                    'STK',                          # SecType: STK
                                    'SMART/AMEX',                   # Exchange: SMART/AMEX
                                    'USD',                          # Currency: USD
                                    'DAY',                          # TimeInForce: DAY
                                    'LMT',                          # OrderType: LMT
                                    round(price, 2),                # LmtPrice: Fiyat
                                    'Basket',                       # BasketTag: Basket
                                    'U21016730',                    # Account: U21016730
                                    'Basket',                       # OrderRef: Basket
                                    'TRUE',                         # Hidden: TRUE
                                    'TRUE'                          # OutsideRth: TRUE
                                ]
                                csv_rows.append(csv_row)
                            print(f"[TRADES CSV] 📝 {symbol}: {action} {lot} lot @ ${price:.2f}")
                            
                        except Exception as e:
                            print(f"[TRADES CSV] ❌ Emir formatı hatası ({order['symbol']}): {e}")
                    
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
                        
                        print(f"[TRADES CSV] ✅ {len(csv_rows)} emir trades.csv'ye kaydedildi")
                        messagebox.showinfo("Başarılı", f"{len(csv_rows)} emir trades.csv'ye kaydedildi!")
                    else:
                        messagebox.showwarning("Uyarı", "Kaydedilecek geçerli emir bulunamadı!")
                        
                except Exception as e:
                    print(f"[PREF CSV] ❌ Kaydetme hatası: {e}")
                    messagebox.showerror("Hata", f"Pref.csv kaydetme hatası: {e}")
            
            ttk.Button(bottom_frame, text="Emirleri Gönder", command=send_orders, 
                      style='Accent.TButton').pack(side='left', padx=5)
            ttk.Button(bottom_frame, text="trades.csv'ye Kaydet", command=save_to_trades_csv, 
                      style='Success.TButton').pack(side='left', padx=5)
            ttk.Button(bottom_frame, text="İptal Et", command=cancel_orders).pack(side='left', padx=5)
            
            # RUNALL Allowed modunda otomatik gönder
            if runall_allowed_mode:
                # Tümünü seç ve gönder
                if self.main_window:
                    self.main_window.after(2000, lambda: self.auto_send_jfin_orders(win, order_tree, send_orders))
                else:
                    print("[JFIN] ⚠️ main_window bulunamadı, otomatik gönderim yapılamadı")
            
        except Exception as e:
            print(f"[JFIN] ❌ Onay penceresi hatası: {e}")
            messagebox.showerror("Hata", f"Emir onay penceresi hatası: {e}")
    
    def auto_send_jfin_orders(self, win, order_tree, send_orders_func):
        """Allowed modunda JFIN emirlerini otomatik gönder"""
        try:
            # Tümünü seç
            for item in order_tree.get_children():
                current_values = list(order_tree.item(item)['values'])
                current_values[0] = '☑'  # Seçili yap
                order_tree.item(item, values=current_values, tags=('selected',))
            
            print("[JFIN] ✅ Tüm emirler seçildi (Allowed modu)")
            
            # MAXALW*3/4 limit kontrolü ile emirleri filtrele
            filtered_orders = []
            for item in order_tree.get_children():
                values = order_tree.item(item)['values']
                if values[0] == '☑':
                    symbol = values[2]
                    
                    # MAXALW*3/4 limit kontrolü
                    if hasattr(self.main_window, 'get_maxalw_for_symbol'):
                        maxalw = self.main_window.get_maxalw_for_symbol(symbol)
                        max_change_limit = maxalw * 3 / 4 if maxalw > 0 else 0
                        
                        # Gün başı pozisyon
                        if hasattr(self.main_window, 'load_bef_position'):
                            befday_qty = self.main_window.load_bef_position(symbol)
                        else:
                            befday_qty = 0
                        
                        # Mevcut pozisyon ve açık emirler
                        if hasattr(self.main_window, 'get_open_orders_sum'):
                            open_orders_qty = self.main_window.get_open_orders_sum(symbol, use_cache=True)
                        else:
                            open_orders_qty = 0
                        
                        # Mevcut pozisyonu bul
                        current_qty = 0
                        if hasattr(self.main_window, 'get_cached_positions'):
                            positions = self.main_window.get_cached_positions(
                                self.main_window.mode_manager.get_active_account() if hasattr(self.main_window, 'mode_manager') else "HAMPRO"
                            )
                            for pos in positions:
                                if pos.get('symbol') == symbol:
                                    current_qty = pos.get('quantity', 0) or pos.get('qty', 0) or 0
                                    break
                        
                        current_potential = current_qty + open_orders_qty
                        
                        # Emir lot miktarı
                        try:
                            lot = int(str(values[9]).replace(',', ''))
                        except:
                            lot = 0
                        
                        # Emir türüne göre potansiyel pozisyon
                        order_type = values[10]
                        if order_type in ['BB', 'FB', 'SoftFB']:  # Buy
                            new_potential = current_potential + lot
                        else:  # Sell
                            new_potential = current_potential - lot
                        
                        # Günlük değişim (mutlak değer)
                        potential_daily_change = abs(new_potential - befday_qty)
                        
                        # MAXALW*3/4 limitini aşacaksa emir gönderme
                        if potential_daily_change > max_change_limit:
                            print(f"[JFIN] ⚠️ {symbol}: MAXALW*3/4 limiti aşılacak ({potential_daily_change:.0f} > {max_change_limit:.0f}), emir seçimi kaldırıldı")
                            current_values = list(values)
                            current_values[0] = '☐'  # Seçimi kaldır
                            order_tree.item(item, values=current_values, tags=('unselected',))
                            continue
                    
                    filtered_orders.append(item)
            
            if filtered_orders:
                print(f"[JFIN] ✅ {len(filtered_orders)} emir MAXALW*3/4 kontrolünden geçti, gönderiliyor...")
                # Emirleri gönder
                send_orders_func()
            else:
                print("[JFIN] ⚠️ MAXALW*3/4 kontrolünden geçen emir bulunamadı")
                win.destroy()
                
        except Exception as e:
            print(f"[JFIN] ❌ Otomatik gönderme hatası: {e}")
            import traceback
            traceback.print_exc()
            # Hata olsa bile pencereyi kapat
            try:
                win.destroy()
            except:
                pass
    
    def select_all_orders(self, tree, select_all=True):
        """Tüm emirleri seç/seçimi kaldır"""
        try:
            for item in tree.get_children():
                current_values = list(tree.item(item)['values'])
                if select_all:
                    current_values[0] = '☑'  # Checkbox dolu
                    tree.item(item, values=current_values, tags=('selected',))
                else:
                    current_values[0] = '☐'  # Checkbox boş
                    tree.item(item, values=current_values, tags=('unselected',))
        except Exception as e:
            print(f"[JFIN] ❌ Toplu seçim hatası: {e}")
    
    def load_lot_rights_from_csv(self):
        """exposureadjuster.csv'den lot haklarını direkt yükle"""
        try:
            import pandas as pd
            import os
            
            # Ana dizindeki exposureadjuster.csv'yi oku
            csv_path = os.path.join('..', 'exposureadjuster.csv')
            
            if not os.path.exists(csv_path):
                print(f"⚠️ exposureadjuster.csv bulunamadı, varsayılan değerler kullanılıyor")
                self.long_lot_rights = 28000
                self.short_lot_rights = 12000
                return
            
            df = pd.read_csv(csv_path)
            
            # Değerleri çek
            total_exposure = 1000000  # Varsayılan
            avg_price = 25.0  # Varsayılan
            long_ratio = 70.0  # Varsayılan
            short_ratio = 30.0  # Varsayılan
            
            for _, row in df.iterrows():
                setting = row['Setting']
                value = str(row['Value']).replace('$', '').replace(',', '').replace('%', '')
                
                try:
                    if setting == 'Total Exposure':
                        total_exposure = float(value)
                    elif setting == 'Avg Pref Price':
                        avg_price = float(value)
                    elif setting == 'Long Ratio':
                        long_ratio = float(value)
                    elif setting == 'Short Ratio':
                        short_ratio = float(value)
                except ValueError:
                    continue
            
            # Lot haklarını hesapla
            total_lots = int(total_exposure / avg_price)
            self.long_lot_rights = int(total_lots * (long_ratio / 100))
            self.short_lot_rights = int(total_lots * (short_ratio / 100))
            
            print(f"📊 CSV'den lot hakları yüklendi:")
            print(f"   💰 Total Exposure: ${total_exposure:,.0f}")
            print(f"   💲 Avg Price: ${avg_price:.2f}")
            print(f"   📈 Long Ratio: {long_ratio}% → {self.long_lot_rights:,} lot")
            print(f"   📉 Short Ratio: {short_ratio}% → {self.short_lot_rights:,} lot")
            
        except Exception as e:
            print(f"❌ CSV lot hakları yükleme hatası: {e}")
            # Hata durumunda varsayılan değerler
            self.long_lot_rights = 28000
            self.short_lot_rights = 12000
    
    def get_score_for_symbol(self, symbol, score_type, stock_data):
        """Sembol için belirtilen skor türünü al - Mini450'deki ana DataFrame'den eşleştir"""
        try:
            # Önce ana sayfadaki DataFrame'den (mini450'den) çek
            if self.main_window and hasattr(self.main_window, 'df') and not self.main_window.df.empty:
                try:
                    # PREF IBKR kolonunda symbol'ü ara
                    symbol_row = self.main_window.df[self.main_window.df['PREF IBKR'] == symbol]
                    if not symbol_row.empty:
                        if score_type in self.main_window.df.columns:
                            score_value = symbol_row[score_type].iloc[0]
                            if pd.notna(score_value) and score_value != 'N/A':
                                # print(f"      ✅ {symbol}: Mini450'den {score_type}={float(score_value):.4f}")
                                return float(score_value)
                        # else:
                        #     print(f"      ⚠️ {symbol}: Mini450'de {score_type} kolonu bulunamadı")
                    # else:
                    #     print(f"      ⚠️ {symbol}: Mini450'de PREF IBKR eşleşmesi bulunamadı")
                        
                except Exception as e:
                    print(f"      ❌ {symbol}: Mini450'den veri çekme hatası: {e}")
            
            # Ana DataFrame'den alamadıysa Stock Data Manager'dan dene
            if self.stock_data_manager:
                try:
                    score_data = self.stock_data_manager.get_stock_data(symbol, score_type)
                    if score_data is not None:
                        print(f"      ✅ {symbol}: Stock Data Manager'dan {score_type}={float(score_data):.4f}")
                        return float(score_data)
                except Exception:
                    pass
            
            # Son çare olarak CSV'den al
            csv_value = stock_data.get(score_type, 'N/A')
            if csv_value != 'N/A':
                print(f"      ⚠️ {symbol}: CSV'den {score_type}={csv_value}")
            return csv_value
            
        except Exception as e:
            print(f"      ❌ {symbol}: Skor alma hatası: {e}")
            return 'N/A'
    
    def calculate_maxalw(self, symbol, stock_data):
        """MAXALW = AVG_ADV / 10 hesapla"""
        try:
            # 1. Önce main_window.df'den AVG_ADV al
            if hasattr(self, 'main_window') and self.main_window and hasattr(self.main_window, 'df'):
                if not self.main_window.df.empty:
                    matching_rows = self.main_window.df[self.main_window.df['PREF IBKR'] == symbol]
                    if not matching_rows.empty and 'AVG_ADV' in matching_rows.columns:
                        avg_adv = matching_rows['AVG_ADV'].iloc[0]
                        if pd.notna(avg_adv) and avg_adv != 'N/A':
                            try:
                                return float(avg_adv) / 10
                            except:
                                pass
            
            # 2. CSV stock_data'dan al
            if isinstance(stock_data, dict):
                avg_adv = stock_data.get('AVG_ADV', 'N/A')
                if avg_adv != 'N/A':
                    try:
                        return float(avg_adv) / 10
                    except:
                        pass
            
            return 'N/A'
            
        except Exception as e:
            return 'N/A'
    
    def get_group_stocks_from_mini450(self, group):
        """
        Mini450'den belirli bir gruba ait hisseleri döndürür
        """
        try:
            # Grup dosya eşleşmesini bul
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
                'notexextlc': 'ssfineknotexextlc.csv'
            }
            
            file_name = group_file_map.get(group.lower())
            if not file_name:
                print(f"   ⚠️ {group} için dosya eşleşmesi bulunamadı")
                return []
            
            # CSV'den grup hisselerini al
            if not os.path.exists(file_name):
                print(f"   ⚠️ {file_name} dosyası bulunamadı")
                return []
                
            df = pd.read_csv(file_name)
            group_symbols = set(df['PREF IBKR'].tolist())
            
            # Mini450'den bu gruba ait hisseleri filtrele
            mini450_df = self.main_window.df
            group_stocks = []
            
            for _, row in mini450_df.iterrows():
                symbol = row.get('PREF IBKR', '')
                if symbol in group_symbols:
                    stock_dict = row.to_dict()
                    group_stocks.append(stock_dict)
            
            print(f"   📊 {group}: {len(group_symbols)} CSV hisse → {len(group_stocks)} Mini450'de bulundu")
            return group_stocks
            
        except Exception as e:
            print(f"   ❌ {group} grup hisselerini alma hatası: {e}")
            return []
    
    def select_top_stocks_by_score(self, stocks, score_column, count, direction):
        """
        Belirli skoruna göre en iyi hisseleri seçer + Şirket kısıtı uygular
        """
        try:
            if len(stocks) == 0:
                return []
            
            # DataFrame'e çevir
            df = pd.DataFrame(stocks)
            
            # Skor kolonunu kontrol et
            if score_column not in df.columns:
                print(f"   ⚠️ {score_column} kolonu bulunamadı")
                return []
            
            # Numeric olmayan değerleri temizle
            df[score_column] = pd.to_numeric(df[score_column], errors='coerce')
            df = df.dropna(subset=[score_column])
            
            if len(df) == 0:
                print(f"   ⚠️ {score_column} için geçerli değer bulunamadı")
                return []
            
            # İlk önce skor bazlı sıralama yap
            if direction == 'LONG':
                # En yüksek skorlular önce
                df_sorted = df.sort_values(score_column, ascending=False)
            else:  # SHORT
                # En düşük skorlular önce
                df_sorted = df.sort_values(score_column, ascending=True)
            
            # Şirket kısıtı uygula
            print(f"   🏢 Şirket kısıtı uygulanıyor...")
            selected_stocks = []
            company_counts = {}  # Her şirketin kaç hisse seçildiğini takip et
            
            for _, row in df_sorted.iterrows():
                if len(selected_stocks) >= count:
                    break  # Hedef sayıya ulaştık
                
                company = row.get('CMON', 'N/A')
                
                # Bu şirketin toplam hisse sayısını bul (grup içinde)
                if company not in company_counts:
                    company_total = len(df[df['CMON'] == company])
                    # Şirket kısıtı: Her şirketten maksimum 3 hisse
                    max_per_company = min(3, company_total)  # En fazla 3, ama toplam sayıdan fazla olamaz
                    company_counts[company] = {'selected': 0, 'max': max_per_company, 'total': company_total}
                    print(f"      🏢 {company}: {company_total} hisse → maksimum {max_per_company} seçilebilir (max 3 kısıtı)")
                
                # Bu şirketten daha fazla hisse seçebilir miyiz?
                if company_counts[company]['selected'] < company_counts[company]['max']:
                    selected_stocks.append(row.to_dict())
                    company_counts[company]['selected'] += 1
                    symbol = row.get('PREF IBKR', 'N/A')
                    score = row.get(score_column, 'N/A')
                    print(f"      ✅ {symbol} ({company}): Skor={score:.2f}, Şirket: {company_counts[company]['selected']}/{company_counts[company]['max']}")
                else:
                    symbol = row.get('PREF IBKR', 'N/A')
                    print(f"      ❌ {symbol} ({company}): Şirket kısıtı! Zaten {company_counts[company]['max']} hisse seçildi")
            
            print(f"   🎯 {score_column}: {len(selected_stocks)} hisse seçildi (şirket kısıtı ile)")
            
            # Şirket bazlı özet
            for company, info in company_counts.items():
                if info['selected'] > 0:
                    print(f"      📊 {company}: {info['selected']}/{info['max']} hisse seçildi")
            
            return selected_stocks
            
        except Exception as e:
            print(f"   ❌ {score_column} seçim hatası: {e}")
            return []
    
    def calculate_remaining_lot_rights(self, stocks_list, calculated_lots, direction):
        """
        Her grup için kalan lot haklarını hesaplar
        """
        try:
            group_used_lots = {}  # Her grubun kullandığı lot sayısı
            
            # Kullanılan lotları grupla
            for stock in stocks_list:
                group = stock.get('GRUP', 'N/A')
                symbol = stock.get('PREF IBKR', 'N/A')
                used_lot = calculated_lots.get(symbol, 0)
                
                if group not in group_used_lots:
                    group_used_lots[group] = 0
                group_used_lots[group] += used_lot
            
            # Port Adjuster'dan grup haklarını al
            if direction == 'LONG':
                # Güncel long lot hakkını al
                if hasattr(self, 'total_long_rights'):
                    total_rights = self.total_long_rights  # Her Long sekme için
                else:
                    total_rights = 28000  # CSV'den varsayılan
                group_weights = self.long_group_weights
            else:  # SHORT
                # Güncel short lot hakkını al  
                if hasattr(self, 'total_short_rights'):
                    total_rights = self.total_short_rights   # Her Short sekme için
                else:
                    total_rights = 12000   # CSV'den varsayılan
                group_weights = self.short_group_weights
            
            remaining_info = []
            
            for group, weight in group_weights.items():
                if weight > 0:  # Sadece hakkı olan gruplar
                    group_total_right = int(total_rights * weight / 100)
                    used_lot = group_used_lots.get(group, 0)
                    remaining = group_total_right - used_lot
                    
                    if remaining != 0:  # Sadece kalan lot varsa göster
                        remaining_info.append(f"{group}: {remaining:,} lot")
            
            return " | ".join(remaining_info) if remaining_info else "Tüm haklar kullanıldı"
            
        except Exception as e:
            return f"Hesaplama hatası: {e}"
    
    def update_lot_info_labels(self, bb_lots, fb_lots, sas_lots, sfs_lots, 
                               bb_stocks, fb_stocks, sas_stocks, sfs_stocks):
        """
        Tüm sekmelerin lot durumu etiketlerini günceller
        """
        try:
            # Güncel lot haklarını al
            long_rights = getattr(self, 'total_long_rights', 28000)  # CSV'den güncel varsayılan
            short_rights = getattr(self, 'total_short_rights', 12000)  # CSV'den güncel varsayılan
            
            # BB Long lot durumu
            bb_remaining = self.calculate_remaining_lot_rights(bb_stocks, bb_lots, 'LONG')
            self.bb_long_lot_info.config(text=f"BB Long ({long_rights:,} lot/sekme) - Kalan: {bb_remaining}")
            
            # FB Long lot durumu  
            fb_remaining = self.calculate_remaining_lot_rights(fb_stocks, fb_lots, 'LONG')
            self.fb_long_lot_info.config(text=f"FB Long ({long_rights:,} lot/sekme) - Kalan: {fb_remaining}")
            
            # SAS Short lot durumu
            sas_remaining = self.calculate_remaining_lot_rights(sas_stocks, sas_lots, 'SHORT')
            self.sas_short_lot_info.config(text=f"SAS Short ({short_rights:,} lot/sekme) - Kalan: {sas_remaining}")
            
            # SFS Short lot durumu
            sfs_remaining = self.calculate_remaining_lot_rights(sfs_stocks, sfs_lots, 'SHORT')
            self.sfs_short_lot_info.config(text=f"SFS Short ({short_rights:,} lot/sekme) - Kalan: {sfs_remaining}")
            
        except Exception as e:
            print(f"❌ Lot durumu güncelleme hatası: {e}")
    
    def get_current_position(self, symbol):
        """
        Belirli bir sembol için mevcut pozisyonu döndürür (Mode manager'a göre)
        Pozitif = Long, Negatif = Short, 0 = Yok
        """
        try:
            print(f"   🔍 {symbol} pozisyon araştırılıyor...")
            
            # Mode manager'ı kontrol et
            if hasattr(self.main_window, 'mode_manager') and self.main_window.mode_manager:
                mode_manager = self.main_window.mode_manager
                
                if mode_manager.is_ibkr_mode():
                    # IBKR MOD açık - IBKR pozisyonlarını kullan
                    print(f"   🔄 IBKR MOD aktif - {symbol} pozisyonu IBKR'den alınıyor...")
                    if hasattr(self.main_window, 'ibkr') and self.main_window.ibkr:
                        ibkr_client = self.main_window.ibkr
                        print(f"   📡 IBKR bağlantısı: {hasattr(ibkr_client, 'is_connected') and ibkr_client.is_connected()}")
                        
                        # Pozisyonları al
                        positions = ibkr_client.get_positions_direct()
                        print(f"   📊 IBKR'den {len(positions) if positions else 0} pozisyon alındı")
                        
                        if positions:
                            # Symbol ile eşleştir
                            for pos in positions:
                                pos_symbol = pos.get('symbol', '')
                                pos_qty = pos.get('qty', 0)
                                
                                if pos_symbol == symbol:
                                    print(f"   ✅ IBKR {symbol} bulundu: {pos_qty} lot")
                                    try:
                                        result = float(pos_qty) if pos_qty is not None else 0
                                        print(f"   🎯 IBKR {symbol} pozisyon: {result}")
                                        return result
                                    except Exception as convert_error:
                                        print(f"   ❌ IBKR {symbol} quantity dönüştürme hatası: {convert_error}")
                                        return 0
                            
                            print(f"   ⚠️ IBKR'de {symbol} pozisyonlarda bulunamadı")
                        else:
                            print(f"   ⚠️ IBKR'den pozisyon alınamadı")
                    else:
                        print(f"   ❌ IBKR bağlantısı bulunamadı!")
                
                elif mode_manager.is_hampro_mode():
                    # HAMMER MOD açık - Hammer Pro pozisyonlarını kullan
                    print(f"   🔄 HAMMER MOD aktif - {symbol} pozisyonu Hammer Pro'dan alınıyor...")
                    if hasattr(self.main_window, 'hammer') and self.main_window.hammer:
                        hammer_client = self.main_window.hammer
                        print(f"   📡 Hammer Pro bağlantısı: {hasattr(hammer_client, 'connected') and hammer_client.connected}")
                        
                        # Pozisyonları al
                        positions = hammer_client.get_positions_direct()
                        print(f"   📊 Hammer Pro'dan {len(positions) if positions else 0} pozisyon alındı")
                        
                        if positions:
                            # Symbol ile eşleştir
                            for pos in positions:
                                pos_symbol = pos.get('symbol', '')
                                pos_qty = pos.get('qty', 0)
                                
                                if pos_symbol == symbol:
                                    print(f"   ✅ Hammer Pro {symbol} bulundu: {pos_qty} lot")
                                    try:
                                        result = float(pos_qty) if pos_qty is not None else 0
                                        print(f"   🎯 Hammer Pro {symbol} pozisyon: {result}")
                                        return result
                                    except Exception as convert_error:
                                        print(f"   ❌ Hammer Pro {symbol} quantity dönüştürme hatası: {convert_error}")
                                        return 0
                            
                            print(f"   ⚠️ Hammer Pro'da {symbol} pozisyonlarda bulunamadı")
                        else:
                            print(f"   ⚠️ Hammer Pro'dan pozisyon alınamadı")
                    else:
                        print(f"   ❌ Hammer Pro bağlantısı bulunamadı!")
                else:
                    print(f"   ⚠️ Mod belirlenemedi, Hammer Pro kullanılıyor...")
                    # Fallback: Hammer Pro kullan
                    if hasattr(self.main_window, 'hammer') and self.main_window.hammer:
                        hammer_client = self.main_window.hammer
                        positions = hammer_client.get_positions_direct()
                        if positions:
                            for pos in positions:
                                pos_symbol = pos.get('symbol', '')
                                pos_qty = pos.get('qty', 0)
                                if pos_symbol == symbol:
                                    try:
                                        result = float(pos_qty) if pos_qty is not None else 0
                                        return result
                                    except Exception:
                                        return 0
            else:
                print(f"   ⚠️ Mode manager bulunamadı, Hammer Pro kullanılıyor...")
                # Fallback: Hammer Pro kullan
                if hasattr(self.main_window, 'hammer') and self.main_window.hammer:
                    hammer_client = self.main_window.hammer
                    positions = hammer_client.get_positions_direct()
                    if positions:
                        for pos in positions:
                            pos_symbol = pos.get('symbol', '')
                            pos_qty = pos.get('qty', 0)
                            if pos_symbol == symbol:
                                try:
                                    result = float(pos_qty) if pos_qty is not None else 0
                                    return result
                                except Exception:
                                    return 0
            
            print(f"   🔄 {symbol} pozisyon: 0 (varsayılan)")
            return 0  # Pozisyon bulunamadı
            
        except Exception as e:
            print(f"   ❌ {symbol} pozisyon alma hatası: {e}")
            return 0
    
    def calculate_addable_lot(self, symbol, allocated_lot, is_short=False):
        """
        Eklenebilir lot miktarını hesaplar (100'lük yuvarlamayla)
        """
        try:
            current_position = self.get_current_position(symbol)
            
            if is_short:
                # Short için: mevcut short pozisyon + yeni short lot
                # Mevcut -1000, yeni 1500 → eklenebilir 500
                current_short = abs(current_position) if current_position < 0 else 0
                addable = max(0, allocated_lot - current_short)
            else:
                # Long için: yeni long lot - mevcut long pozisyon  
                # Mevcut +1000, yeni 4400 → eklenebilir 3400
                current_long = current_position if current_position > 0 else 0
                addable = max(0, allocated_lot - current_long)
            
            # 100'lük yuvarla
            addable_rounded = round(addable / 100) * 100
            
            return int(addable_rounded)
            
        except Exception as e:
            print(f"   ⚠️ {symbol} eklenebilir lot hesaplama hatası: {e}")
            return 0
    
    def display_tumcsv_results_by_score_type(self, all_long_stocks, all_short_stocks):
        """4 farklı sekme için hisseleri skor türüne göre ayır ve göster - HER SEKME KENDI SKORUNA GÖRE"""
        try:
            # Tüm tabloları temizle
            for item in self.bb_long_tree.get_children():
                self.bb_long_tree.delete(item)
            for item in self.fb_long_tree.get_children():
                self.fb_long_tree.delete(item)
            for item in self.sas_short_tree.get_children():
                self.sas_short_tree.delete(item)
            for item in self.sfs_short_tree.get_children():
                self.sfs_short_tree.delete(item)
            
            # Tüm hisseleri birleştir
            all_stocks = all_long_stocks + all_short_stocks
            
            print(f"   🎯 4 sekmeye skor türüne göre hisseler dağıtılıyor...")
            
            # Skor türüne göre hisseleri ayır - HER HİSSE SADECE BİR SEKMEDE!
            bb_long_stocks_list = []
            fb_long_stocks_list = []
            sas_short_stocks_list = []
            sfs_short_stocks_list = []
            
            # HER SEKME BAĞIMSIZ - Sekmeler arası kesişim OLABİLİR
            # Sadece aynı sekme içinde duplicate olmamalı
            
            for stock in all_stocks:
                symbol = stock.get('PREF IBKR', 'N/A')
                skor_turu = stock.get('SKOR_TURU', '')
                
                if skor_turu == 'BB_LONG':
                    bb_long_stocks_list.append(stock)
                elif skor_turu == 'FB_LONG':
                    fb_long_stocks_list.append(stock)
                elif skor_turu == 'SAS_SHORT':
                    sas_short_stocks_list.append(stock)
                elif skor_turu == 'SFS_SHORT':
                    sfs_short_stocks_list.append(stock)
            
            print(f"   📊 Skor türüne göre dağılım:")
            print(f"      🔵 BB Long: {len(bb_long_stocks_list)} hisse")
            print(f"      🟢 FB Long: {len(fb_long_stocks_list)} hisse")
            print(f"      🟠 SAS Short: {len(sas_short_stocks_list)} hisse")
            print(f"      🔴 SFS Short: {len(sfs_short_stocks_list)} hisse")
            
            # Her skor türü için BAĞIMSIZ GRUP BAZLI lot dağılımını hesapla
            # Güncel lot haklarını al
            long_rights = getattr(self, 'total_long_rights', 28000)  # CSV'den güncel varsayılan
            short_rights = getattr(self, 'total_short_rights', 12000)  # CSV'den güncel varsayılan
            
            print(f"\n   🎯 BAĞIMSIZ GRUP BAZLI Lot dağılımları hesaplanıyor (Alpha: {self.alpha})...")
            print(f"   📊 Her sekme bağımsız lot hakkı:")
            print(f"      🔵 BB Long: {long_rights:,} lot (bağımsız)")
            print(f"      🟢 FB Long: {long_rights:,} lot (bağımsız)")
            print(f"      🟠 SAS Short: {short_rights:,} lot (bağımsız)")
            print(f"      🔴 SFS Short: {short_rights:,} lot (bağımsız)")
            print(f"      📈 Toplam: {long_rights*2:,} Long + {short_rights*2:,} Short = {(long_rights*2)+(short_rights*2):,} lot\n")
            
            bb_lots = self.calculate_independent_score_based_lot_distribution(bb_long_stocks_list, 'Final_BB_skor', 'LONG')
            fb_lots = self.calculate_independent_score_based_lot_distribution(fb_long_stocks_list, 'Final_FB_skor', 'LONG')
            sas_lots = self.calculate_independent_score_based_lot_distribution(sas_short_stocks_list, 'Final_SAS_skor', 'SHORT')
            sfs_lots = self.calculate_independent_score_based_lot_distribution(sfs_short_stocks_list, 'Final_SFS_skor', 'SHORT')
            
            # Lot durumu etiketlerini güncelle
            self.update_lot_info_labels(bb_lots, fb_lots, sas_lots, sfs_lots,
                                       bb_long_stocks_list, fb_long_stocks_list, 
                                       sas_short_stocks_list, sfs_short_stocks_list)
            
            # BB Long sekmesini doldur (sadece BB_LONG skor türündeki hisseler)
            bb_seen_symbols = set()  # Bu sekme için duplicate kontrol
            for stock in bb_long_stocks_list:
                try:
                    symbol = stock.get('PREF IBKR', 'N/A')
                    group = stock.get('GRUP', 'N/A')
                    
                    # Bu sekmede duplicate kontrolü
                    if symbol in bb_seen_symbols:
                        continue
                    bb_seen_symbols.add(symbol)
                    
                    final_bb_skor = self.get_score_for_symbol(symbol, 'Final_BB_skor', stock)
                    final_sfs_skor = self.get_score_for_symbol(symbol, 'Final_SFS_skor', stock)
                    fbtot = self.calculate_fbtot_for_symbol(symbol, group)
                    smi = stock.get('SMI', 'N/A')
                    sma63_chg = stock.get('SMA63 chg', 'N/A')
                    
                    # MAXALW = AVG_ADV / 10 hesapla
                    maxalw = self.calculate_maxalw(symbol, stock)
                    
                    # Mevcut pozisyonu al
                    current_position = self.get_current_position(symbol)
                    
                    # Hesaplanan lot dağılımını al
                    calculated_lots = bb_lots.get(symbol, 0)
                    
                    # Eklenebilir lot hesapla
                    addable_lot = self.calculate_addable_lot_jfin(maxalw, current_position, calculated_lots)
                    
                    # GORT hesapla
                    gort = 0.0
                    if hasattr(self.main_window, 'calculate_gort'):
                        gort = self.main_window.calculate_gort(symbol)
                    gort_str = f"{gort:.2f}" if isinstance(gort, (int, float)) and not pd.isna(gort) else "N/A"
                    
                    bb_long_values = (group, symbol, final_bb_skor, final_sfs_skor, fbtot, smi, sma63_chg, gort_str, maxalw, current_position, calculated_lots, addable_lot)
                    self.bb_long_tree.insert('', 'end', values=bb_long_values)
                    
                except Exception as e:
                    print(f"   ❌ BB Long {stock.get('PREF IBKR', 'N/A')} gösterim hatası: {e}")
            
            # FB Long sekmesini doldur (sadece FB_LONG skor türündeki hisseler)
            fb_seen_symbols = set()  # Bu sekme için duplicate kontrol
            for stock in fb_long_stocks_list:
                try:
                    symbol = stock.get('PREF IBKR', 'N/A')
                    group = stock.get('GRUP', 'N/A')
                    
                    # Bu sekmede duplicate kontrolü
                    if symbol in fb_seen_symbols:
                        continue
                    fb_seen_symbols.add(symbol)
                    
                    final_fb_skor = self.get_score_for_symbol(symbol, 'Final_FB_skor', stock)
                    final_sfs_skor = self.get_score_for_symbol(symbol, 'Final_SFS_skor', stock)
                    fbtot = self.calculate_fbtot_for_symbol(symbol, group)
                    smi = stock.get('SMI', 'N/A')
                    sma63_chg = stock.get('SMA63 chg', 'N/A')
                    
                    # MAXALW = AVG_ADV / 10 hesapla
                    maxalw = self.calculate_maxalw(symbol, stock)
                    
                    # Mevcut pozisyonu al
                    current_position = self.get_current_position(symbol)
                    
                    # Hesaplanan lot dağılımını al
                    calculated_lots = fb_lots.get(symbol, 0)
                    
                    # Eklenebilir lot hesapla
                    addable_lot = self.calculate_addable_lot_jfin(maxalw, current_position, calculated_lots)
                    
                    # GORT hesapla
                    gort = 0.0
                    if hasattr(self.main_window, 'calculate_gort'):
                        gort = self.main_window.calculate_gort(symbol)
                    gort_str = f"{gort:.2f}" if isinstance(gort, (int, float)) and not pd.isna(gort) else "N/A"
                    
                    fb_long_values = (group, symbol, final_fb_skor, final_sfs_skor, fbtot, smi, sma63_chg, gort_str, maxalw, current_position, calculated_lots, addable_lot)
                    self.fb_long_tree.insert('', 'end', values=fb_long_values)
                    
                except Exception as e:
                    print(f"   ❌ FB Long {stock.get('PREF IBKR', 'N/A')} gösterim hatası: {e}")
            
            # SAS Short sekmesini doldur (sadece SAS_SHORT skor türündeki hisseler)
            sas_seen_symbols = set()  # Bu sekme için duplicate kontrol
            for stock in sas_short_stocks_list:
                try:
                    symbol = stock.get('PREF IBKR', 'N/A')
                    group = stock.get('GRUP', 'N/A')
                    
                    # Bu sekmede duplicate kontrolü
                    if symbol in sas_seen_symbols:
                        continue
                    sas_seen_symbols.add(symbol)
                    
                    final_sas_skor = self.get_score_for_symbol(symbol, 'Final_SAS_skor', stock)
                    final_fb_skor = self.get_score_for_symbol(symbol, 'Final_FB_skor', stock)
                    sfstot = self.calculate_sfstot_for_symbol(symbol, group)
                    smi = stock.get('SMI', 'N/A')
                    sma63_chg = stock.get('SMA63 chg', 'N/A')
                    
                    # MAXALW = AVG_ADV / 10 hesapla
                    maxalw = self.calculate_maxalw(symbol, stock)
                    
                    # Mevcut pozisyonu al
                    current_position = self.get_current_position(symbol)
                    
                    # Hesaplanan lot dağılımını al
                    calculated_lots = sas_lots.get(symbol, 0)
                    
                    # Eklenebilir lot hesapla (Short için)
                    addable_lot = self.calculate_addable_lot_short_jfin(maxalw, current_position, calculated_lots)
                    
                    # GORT hesapla
                    gort = 0.0
                    if hasattr(self.main_window, 'calculate_gort'):
                        gort = self.main_window.calculate_gort(symbol)
                    gort_str = f"{gort:.2f}" if isinstance(gort, (int, float)) and not pd.isna(gort) else "N/A"
                    
                    sas_short_values = (group, symbol, final_sas_skor, final_fb_skor, sfstot, smi, sma63_chg, gort_str, maxalw, abs(current_position), calculated_lots, addable_lot)
                    self.sas_short_tree.insert('', 'end', values=sas_short_values)
                    
                except Exception as e:
                    print(f"   ❌ SAS Short {stock.get('PREF IBKR', 'N/A')} gösterim hatası: {e}")
            
            # SFS Short sekmesini doldur (sadece SFS_SHORT skor türündeki hisseler)
            sfs_seen_symbols = set()  # Bu sekme için duplicate kontrol
            for stock in sfs_short_stocks_list:
                try:
                    symbol = stock.get('PREF IBKR', 'N/A')
                    group = stock.get('GRUP', 'N/A')
                    
                    # Bu sekmede duplicate kontrolü
                    if symbol in sfs_seen_symbols:
                        continue
                    sfs_seen_symbols.add(symbol)
                    
                    final_sfs_skor = self.get_score_for_symbol(symbol, 'Final_SFS_skor', stock)
                    final_fb_skor = self.get_score_for_symbol(symbol, 'Final_FB_skor', stock)
                    sfstot = self.calculate_sfstot_for_symbol(symbol, group)
                    smi = stock.get('SMI', 'N/A')
                    sma63_chg = stock.get('SMA63 chg', 'N/A')
                    
                    # MAXALW = AVG_ADV / 10 hesapla
                    maxalw = self.calculate_maxalw(symbol, stock)
                    
                    # Mevcut pozisyonu al
                    current_position = self.get_current_position(symbol)
                    
                    # Hesaplanan lot dağılımını al
                    calculated_lots = sfs_lots.get(symbol, 0)
                    
                    # Eklenebilir lot hesapla (Short için)
                    addable_lot = self.calculate_addable_lot_short_jfin(maxalw, current_position, calculated_lots)
                    
                    # GORT hesapla
                    gort = 0.0
                    if hasattr(self.main_window, 'calculate_gort'):
                        gort = self.main_window.calculate_gort(symbol)
                    gort_str = f"{gort:.2f}" if isinstance(gort, (int, float)) and not pd.isna(gort) else "N/A"
                    
                    sfs_short_values = (group, symbol, final_sfs_skor, final_fb_skor, sfstot, smi, sma63_chg, gort_str, maxalw, abs(current_position), calculated_lots, addable_lot)
                    self.sfs_short_tree.insert('', 'end', values=sfs_short_values)
                    
                except Exception as e:
                    print(f"   ❌ SFS Short {stock.get('PREF IBKR', 'N/A')} gösterim hatası: {e}")
            
            print(f"   ✅ 4 sekme skor türüne göre güncellendi:")
            print(f"   🔵 BB Long: {len(bb_long_stocks_list)} hisse (Final_BB_skor'a göre seçilmiş)")
            print(f"   🟢 FB Long: {len(fb_long_stocks_list)} hisse (Final_FB_skor'a göre seçilmiş)")
            print(f"   🟠 SAS Short: {len(sas_short_stocks_list)} hisse (Final_SAS_skor'a göre seçilmiş)")
            print(f"   🔴 SFS Short: {len(sfs_short_stocks_list)} hisse (Final_SFS_skor'a göre seçilmiş)")

            # Filtrelenmiş verileri sakla (başlangıç için tüm veriler filtrelenmiş kabul edilsin)
            # Her sekme için tree'deki item ID'lerini sakla
            self.bb_filtered_data = [item for item in self.bb_long_tree.get_children()]
            self.fb_filtered_data = [item for item in self.fb_long_tree.get_children()]
            self.sas_filtered_data = [item for item in self.sas_short_tree.get_children()]
            self.sfs_filtered_data = [item for item in self.sfs_short_tree.get_children()]

            # Başlangıçta filtreleme UI'larını güncelle (boş filtre)
            try:
                self.apply_bb_filter()
                self.apply_fb_filter()
                self.apply_sas_filter()
                self.apply_sfs_filter()
            except:
                pass  # Başlangıçta hata olursa devam et

        except Exception as e:
            print(f"❌ 4 sekme sonuç gösterim hatası: {e}")

    def get_exempted_groups(self):
        """Filtrelemeye dahil olmayan gruplar"""
        return ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']

    def should_apply_fbtot_filter(self, group, fbtot_value, filter_value, filter_type):
        """FBtot filtresi uygulanıp uygulanmayacağını belirler"""
        try:
            # Filtre değeri boş ise filtreleme yapma
            if not filter_value or filter_value.strip() == '':
                return True

            # Belirtilen gruplar için filtreleme yapma
            exempted_groups = self.get_exempted_groups()
            if group.lower() in exempted_groups:
                print(f"[FBtot FILTER] ✅ {group} exempted, filtreleme yapılmıyor")
                return True

            # FBtot değeri geçerli değilse, filtrelemeye dahil etme
            if fbtot_value == 'N/A' or fbtot_value == '' or fbtot_value is None:
                print(f"[FBtot FILTER] ❌ FBtot değeri geçersiz: {fbtot_value}")
                return False

            filter_num = float(filter_value)
            fbtot_num = float(fbtot_value)

            if filter_type == 'above':
                result = fbtot_num >= filter_num
                print(f"[FBtot FILTER] 🔍 {group}: FBtot={fbtot_num} >= {filter_num} = {result}")
                return result
            else:  # below
                result = fbtot_num <= filter_num
                print(f"[FBtot FILTER] 🔍 {group}: FBtot={fbtot_num} <= {filter_num} = {result}")
                return result

        except (ValueError, TypeError) as e:
            # Hata durumunda, filtrelemeye dahil etme
            print(f"[FBtot FILTER] ❌ Hata: {e}")
            return False

    def should_apply_sfstot_filter(self, group, sfstot_value, filter_value, filter_type):
        """SFStot filtresi uygulanıp uygulanmayacağını belirler"""
        try:
            # Filtre değeri boş ise filtreleme yapma
            if not filter_value or filter_value.strip() == '':
                return True

            # Belirtilen gruplar için filtreleme yapma
            exempted_groups = self.get_exempted_groups()
            if group.lower() in exempted_groups:
                print(f"[SFStot FILTER] ✅ {group} exempted, filtreleme yapılmıyor")
                return True

            # SFStot değeri geçerli değilse, filtrelemeye dahil etme
            if sfstot_value == 'N/A' or sfstot_value == '' or sfstot_value is None:
                print(f"[SFStot FILTER] ❌ SFStot değeri geçersiz: {sfstot_value}")
                return False

            filter_num = float(filter_value)
            sfstot_num = float(sfstot_value)

            if filter_type == 'above':
                result = sfstot_num >= filter_num
                print(f"[SFStot FILTER] 🔍 {group}: SFStot={sfstot_num} >= {filter_num} = {result}")
                return result
            else:  # below
                result = sfstot_num <= filter_num
                print(f"[SFStot FILTER] 🔍 {group}: SFStot={sfstot_num} <= {filter_num} = {result}")
                return result

        except (ValueError, TypeError) as e:
            # Hata durumunda, filtrelemeye dahil etme
            print(f"[SFStot FILTER] ❌ Hata: {e}")
            return False

    def should_apply_sma_filter(self, group, sma_value, filter_value, filter_type):
        """SMA63 chg filtresi uygulanıp uygulanmayacağını belirler"""
        try:
            # Filtre değeri boş ise filtreleme yapma
            if not filter_value or filter_value.strip() == '':
                return True

            # Belirtilen gruplar için filtreleme yapma
            exempted_groups = self.get_exempted_groups()
            if group.lower() in exempted_groups:
                print(f"[SMA FILTER] ✅ {group} exempted, filtreleme yapılmıyor")
                return True

            # SMA değeri geçerli değilse, filtrelemeye dahil etme
            if sma_value == 'N/A' or sma_value == '' or sma_value is None:
                print(f"[SMA FILTER] ❌ SMA değeri geçersiz: {sma_value}")
                return False

            filter_num = float(filter_value)
            sma_num = float(sma_value)

            if filter_type == 'above':
                result = sma_num >= filter_num
                print(f"[SMA FILTER] 🔍 {group}: SMA={sma_num} >= {filter_num} = {result}")
                return result
            else:  # below
                result = sma_num <= filter_num
                print(f"[SMA FILTER] 🔍 {group}: SMA={sma_num} <= {filter_num} = {result}")
                return result

        except (ValueError, TypeError) as e:
            # Hata durumunda, filtrelemeye dahil etme
            print(f"[SMA FILTER] ❌ Hata: {e}")
            return False

    def apply_bb_filter(self):
        """BB Long sekmesi için SMA63 chg filtresi uygular"""
        try:
            filter_value = self.bb_sma_filter_var.get().strip()
            filter_type = self.bb_filter_type.get()

            # Tüm satırları al (hem görünür hem gizli)
            all_items = []
            for item in self.bb_long_tree.get_children():
                all_items.append(item)
            # Detach edilmiş itemleri de dahil et
            try:
                # Treeview'da tüm itemleri bulmak için parent'tan başlayarak recursive arama yap
                def get_all_tree_items(tree, parent=''):
                    items = []
                    for item in tree.get_children(parent):
                        items.append(item)
                        items.extend(get_all_tree_items(tree, item))
                    return items

                all_items = get_all_tree_items(self.bb_long_tree)
            except:
                # Hata durumunda sadece görünür itemleri kullan
                all_items = list(self.bb_long_tree.get_children())

            # Filtrelenmiş verileri sakla
            self.bb_filtered_data = []
            
            # FBtot filtre değerlerini önceden al
            fbtot_filter_value = self.bb_fbtot_filter_var.get().strip()
            fbtot_filter_type = self.bb_fbtot_filter_type.get()
            
            print(f"[BB FILTER] 🔍 Toplam {len(all_items)} hisse kontrol ediliyor...")
            print(f"[BB FILTER] 🔍 SMA Filtre: {filter_type} {filter_value}")
            print(f"[BB FILTER] 🔍 FBtot Filtre: {fbtot_filter_type} {fbtot_filter_value}")

            for item in all_items:
                try:
                    values = self.bb_long_tree.item(item)['values']
                    print(f"[BB FILTER] 🔍 Item: {item}, Kolon sayısı: {len(values)}")
                    
                    if len(values) >= 7:  # En az 7 kolon olmalı (SMA63 chg index 6)
                        group = values[0]
                        symbol = values[1]
                        sma_value = values[6]  # SMA63 chg kolonu
                        fbtot_value = values[4]  # FBtot kolonu
                        
                        sma_pass = self.should_apply_sma_filter(group, sma_value, filter_value, filter_type)
                        fbtot_pass = self.should_apply_fbtot_filter(group, fbtot_value, fbtot_filter_value, fbtot_filter_type)

                        print(f"[BB FILTER] 🔍 {symbol}: SMA={sma_value} (pass={sma_pass}), FBtot={fbtot_value} (pass={fbtot_pass})")

                        if sma_pass and fbtot_pass:
                            self.bb_filtered_data.append(item)
                            print(f"[BB FILTER] ✅ {symbol} eklendi")
                            # Item'i görünür yap
                            try:
                                self.bb_long_tree.reattach(item, '', 'end')
                            except:
                                pass  # Zaten görünür
                        else:
                            # Item'i gizle
                            try:
                                self.bb_long_tree.detach(item)
                            except:
                                pass  # Zaten gizli
                    else:
                        print(f"[BB FILTER] ❌ Kolon sayısı yetersiz: {len(values)} < 7")
                except:
                    continue

            # Filtreleme bilgisini göster
            if filter_value and filter_value.strip():
                filter_text = f"{filter_type} {filter_value}"
            else:
                filter_text = "Kapalı"

            print(f"🔵 BB Long filtresi uygulandı: {filter_text} (Gösterilen: {len(self.bb_filtered_data)})")

        except Exception as e:
            print(f"❌ BB Long filtre hatası: {e}")

    def apply_fb_filter(self):
        """FB Long sekmesi için SMA63 chg filtresi uygular"""
        try:
            filter_value = self.fb_sma_filter_var.get().strip()
            filter_type = self.fb_filter_type.get()

            # Tüm satırları al (hem görünür hem gizli)
            all_items = []
            for item in self.fb_long_tree.get_children():
                all_items.append(item)
            try:
                def get_all_tree_items(tree, parent=''):
                    items = []
                    for item in tree.get_children(parent):
                        items.append(item)
                        items.extend(get_all_tree_items(tree, item))
                    return items
                all_items = get_all_tree_items(self.fb_long_tree)
            except:
                all_items = list(self.fb_long_tree.get_children())

            # Filtrelenmiş verileri sakla
            self.fb_filtered_data = []
            
            # FBtot filtre değerlerini önceden al
            fbtot_filter_value = self.fb_fbtot_filter_var.get().strip()
            fbtot_filter_type = self.fb_fbtot_filter_type.get()
            
            print(f"[FB FILTER] 🔍 Toplam {len(all_items)} hisse kontrol ediliyor...")
            print(f"[FB FILTER] 🔍 SMA Filtre: {filter_type} {filter_value}")
            print(f"[FB FILTER] 🔍 FBtot Filtre: {fbtot_filter_type} {fbtot_filter_value}")

            for item in all_items:
                try:
                    values = self.fb_long_tree.item(item)['values']
                    print(f"[FB FILTER] 🔍 Item: {item}, Kolon sayısı: {len(values)}")
                    
                    if len(values) >= 7:  # En az 7 kolon olmalı (SMA63 chg index 6)
                        group = values[0]
                        symbol = values[1]
                        sma_value = values[6]  # SMA63 chg kolonu
                        fbtot_value = values[4]  # FBtot kolonu
                        
                        sma_pass = self.should_apply_sma_filter(group, sma_value, filter_value, filter_type)
                        fbtot_pass = self.should_apply_fbtot_filter(group, fbtot_value, fbtot_filter_value, fbtot_filter_type)

                        print(f"[FB FILTER] 🔍 {symbol}: SMA={sma_value} (pass={sma_pass}), FBtot={fbtot_value} (pass={fbtot_pass})")

                        if sma_pass and fbtot_pass:
                            self.fb_filtered_data.append(item)
                            print(f"[FB FILTER] ✅ {symbol} eklendi")
                            # Item'i görünür yap
                            try:
                                self.fb_long_tree.reattach(item, '', 'end')
                            except:
                                pass  # Zaten görünür
                        else:
                            # Item'i gizle
                            try:
                                self.fb_long_tree.detach(item)
                            except:
                                pass  # Zaten gizli
                    else:
                        print(f"[FB FILTER] ❌ Kolon sayısı yetersiz: {len(values)} < 7")
                except:
                    continue

            # Filtreleme bilgisini göster
            if filter_value and filter_value.strip():
                filter_text = f"{filter_type} {filter_value}"
            else:
                filter_text = "Kapalı"

            print(f"🟢 FB Long filtresi uygulandı: {filter_text} (Gösterilen: {len(self.fb_filtered_data)})")

        except Exception as e:
            print(f"❌ FB Long filtre hatası: {e}")

    def apply_sas_filter(self):
        """SAS Short sekmesi için SMA63 chg filtresi uygular"""
        try:
            filter_value = self.sas_sma_filter_var.get().strip()
            filter_type = self.sas_filter_type.get()

            # Tüm satırları al (hem görünür hem gizli)
            all_items = []
            for item in self.sas_short_tree.get_children():
                all_items.append(item)
            try:
                def get_all_tree_items(tree, parent=''):
                    items = []
                    for item in tree.get_children(parent):
                        items.append(item)
                        items.extend(get_all_tree_items(tree, item))
                    return items
                all_items = get_all_tree_items(self.sas_short_tree)
            except:
                all_items = list(self.sas_short_tree.get_children())

            # Filtrelenmiş verileri sakla
            self.sas_filtered_data = []
            
            # SFStot filtre değerlerini önceden al
            sfstot_filter_value = self.sas_sfstot_filter_var.get().strip()
            sfstot_filter_type = self.sas_sfstot_filter_type.get()
            
            print(f"[SAS FILTER] 🔍 Toplam {len(all_items)} hisse kontrol ediliyor...")
            print(f"[SAS FILTER] 🔍 SMA Filtre: {filter_type} {filter_value}")
            print(f"[SAS FILTER] 🔍 SFStot Filtre: {sfstot_filter_type} {sfstot_filter_value}")

            for item in all_items:
                try:
                    values = self.sas_short_tree.item(item)['values']
                    print(f"[SAS FILTER] 🔍 Item: {item}, Kolon sayısı: {len(values)}")
                    
                    if len(values) >= 7:  # En az 7 kolon olmalı (SMA63 chg index 6)
                        group = values[0]
                        symbol = values[1]
                        sma_value = values[6]  # SMA63 chg kolonu
                        sfstot_value = values[4]  # SFStot kolonu
                        
                        sma_pass = self.should_apply_sma_filter(group, sma_value, filter_value, filter_type)
                        sfstot_pass = self.should_apply_sfstot_filter(group, sfstot_value, sfstot_filter_value, sfstot_filter_type)

                        print(f"[SAS FILTER] 🔍 {symbol}: SMA={sma_value} (pass={sma_pass}), SFStot={sfstot_value} (pass={sfstot_pass})")

                        if sma_pass and sfstot_pass:
                            self.sas_filtered_data.append(item)
                            print(f"[SAS FILTER] ✅ {symbol} eklendi")
                            # Item'i görünür yap
                            try:
                                self.sas_short_tree.reattach(item, '', 'end')
                            except:
                                pass  # Zaten görünür
                        else:
                            # Item'i gizle
                            try:
                                self.sas_short_tree.detach(item)
                            except:
                                pass  # Zaten gizli
                    else:
                        print(f"[SAS FILTER] ❌ Kolon sayısı yetersiz: {len(values)} < 7")
                except:
                    continue

            # Filtreleme bilgisini göster
            if filter_value and filter_value.strip():
                filter_text = f"{filter_type} {filter_value}"
            else:
                filter_text = "Kapalı"

            print(f"🟠 SAS Short filtresi uygulandı: {filter_text} (Gösterilen: {len(self.sas_filtered_data)})")

        except Exception as e:
            print(f"❌ SAS Short filtre hatası: {e}")

    def apply_sfs_filter(self):
        """SFS Short sekmesi için SMA63 chg filtresi uygular"""
        try:
            filter_value = self.sfs_sma_filter_var.get().strip()
            filter_type = self.sfs_filter_type.get()

            # Tüm satırları al (hem görünür hem gizli)
            all_items = []
            for item in self.sfs_short_tree.get_children():
                all_items.append(item)
            try:
                def get_all_tree_items(tree, parent=''):
                    items = []
                    for item in tree.get_children(parent):
                        items.append(item)
                        items.extend(get_all_tree_items(tree, item))
                    return items
                all_items = get_all_tree_items(self.sfs_short_tree)
            except:
                all_items = list(self.sfs_short_tree.get_children())

            # Filtrelenmiş verileri sakla
            self.sfs_filtered_data = []
            
            # SFStot filtre değerlerini önceden al
            sfstot_filter_value = self.sfs_sfstot_filter_var.get().strip()
            sfstot_filter_type = self.sfs_sfstot_filter_type.get()
            
            print(f"[SFS FILTER] 🔍 Toplam {len(all_items)} hisse kontrol ediliyor...")
            print(f"[SFS FILTER] 🔍 SMA Filtre: {filter_type} {filter_value}")
            print(f"[SFS FILTER] 🔍 SFStot Filtre: {sfstot_filter_type} {sfstot_filter_value}")

            for item in all_items:
                try:
                    values = self.sfs_short_tree.item(item)['values']
                    print(f"[SFS FILTER] 🔍 Item: {item}, Kolon sayısı: {len(values)}")
                    
                    if len(values) >= 7:  # En az 7 kolon olmalı (SMA63 chg index 6)
                        group = values[0]
                        symbol = values[1]
                        sma_value = values[6]  # SMA63 chg kolonu
                        sfstot_value = values[4]  # SFStot kolonu
                        
                        sma_pass = self.should_apply_sma_filter(group, sma_value, filter_value, filter_type)
                        sfstot_pass = self.should_apply_sfstot_filter(group, sfstot_value, sfstot_filter_value, sfstot_filter_type)

                        print(f"[SFS FILTER] 🔍 {symbol}: SMA={sma_value} (pass={sma_pass}), SFStot={sfstot_value} (pass={sfstot_pass})")

                        if sma_pass and sfstot_pass:
                            self.sfs_filtered_data.append(item)
                            print(f"[SFS FILTER] ✅ {symbol} eklendi")
                            # Item'i görünür yap
                            try:
                                self.sfs_short_tree.reattach(item, '', 'end')
                            except:
                                pass  # Zaten görünür
                        else:
                            # Item'i gizle
                            try:
                                self.sfs_short_tree.detach(item)
                            except:
                                pass  # Zaten gizli
                    else:
                        print(f"[SFS FILTER] ❌ Kolon sayısı yetersiz: {len(values)} < 7")
                except:
                    continue

            # Filtreleme bilgisini göster
            if filter_value and filter_value.strip():
                filter_text = f"{filter_type} {filter_value}"
            else:
                filter_text = "Kapalı"

            print(f"🔴 SFS Short filtresi uygulandı: {filter_text} (Gösterilen: {len(self.sfs_filtered_data)})")

        except Exception as e:
            print(f"❌ SFS Short filtre hatası: {e}")

    def clear_all_filters(self):
        """Tüm sekmelerdeki filtreleri kaldırır ve sayfayı ilk açıldığındaki hale döndürür"""
        try:
            print("🔄 Tüm filtreler kaldırılıyor...")

            # 1. Filtre alanlarını temizle
            self.bb_sma_filter_var.set('')
            self.fb_sma_filter_var.set('')
            self.sas_sma_filter_var.set('')
            self.sfs_sma_filter_var.set('')

            # 2. Filtre türlerini varsayılan değerlere döndür
            self.bb_filter_type.set('below')
            self.fb_filter_type.set('below')
            self.sas_filter_type.set('below')
            self.sfs_filter_type.set('below')

            # 3. Tüm treeview'lardaki gizli satırları görünür hale getir
            # Önce tüm itemlerin değerlerini sakla, sonra treeview'ı temizleyip yeniden doldur
            def restore_all_items(tree):
                """Treeview'daki tüm itemleri görünür hale getirir"""
                # Tüm itemlerin değerlerini al (hem görünür hem gizli)
                all_values = []

                def collect_all_items(parent=''):
                    items = []
                    for item in tree.get_children(parent):
                        try:
                            values = tree.item(item)['values']
                            items.append(values)
                        except:
                            pass
                        items.extend(collect_all_items(item))
                    return items

                # Tüm itemleri topla
                all_values = collect_all_items()

                # Treeview'ı temizle
                for item in tree.get_children():
                    tree.delete(item)

                # Tüm itemleri yeniden ekle (artık hepsi görünür olacak)
                for values in all_values:
                    tree.insert('', 'end', values=values)

                return all_values

            # Tüm treeview'lar için
            bb_values = restore_all_items(self.bb_long_tree)
            fb_values = restore_all_items(self.fb_long_tree)
            sas_values = restore_all_items(self.sas_short_tree)
            sfs_values = restore_all_items(self.sfs_short_tree)

            # 4. Filtrelenmiş veri listelerini sıfırla
            self.bb_filtered_data = list(self.bb_long_tree.get_children())
            self.fb_filtered_data = list(self.fb_long_tree.get_children())
            self.sas_filtered_data = list(self.sas_short_tree.get_children())
            self.sfs_filtered_data = list(self.sfs_short_tree.get_children())

            print("✅ Tüm filtreler kaldırıldı! Sayfa ilk açıldığındaki haline döndürüldü.")
            print(f"   📊 BB Long: {len(bb_values)} hisse geri yüklendi")
            print(f"   📊 FB Long: {len(fb_values)} hisse geri yüklendi")
            print(f"   📊 SAS Short: {len(sas_values)} hisse geri yüklendi")
            print(f"   📊 SFS Short: {len(sfs_values)} hisse geri yüklendi")

        except Exception as e:
            print(f"❌ Filtreleri kaldırma hatası: {e}")
            import traceback
            print(f"❌ Hata detayı: {traceback.format_exc()}")
    
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
