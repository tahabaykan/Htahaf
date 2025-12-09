"""
Port Adjuster - Portföy ayarlama penceresi

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janall/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Örnek:
✅ DOĞRU: "exposureadjuster.csv" (StockTracker dizininde)
❌ YANLIŞ: "janall/exposureadjuster.csv"
=================================
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import os
import math

class PortAdjusterWindow:
    def __init__(self, parent):
        self.parent = parent
        
        # Ana pencere - Daha geniş
        self.win = tk.Toplevel(parent)
        self.win.title("Port Adjuster - Portföy Ayarları")
        self.win.geometry("1400x800")  # 1000x700'den 1400x800'e çıkarıldı
        self.win.transient(parent)
        # grab_set() kaldırıldı - minimize edilebilir olması için
        
        # Başlık frame - minimize butonu ile
        title_frame = ttk.Frame(self.win)
        title_frame.pack(fill='x', padx=5, pady=5)
        
        title_label = ttk.Label(title_frame, text="Port Adjuster - Portföy Ayarları", 
                                font=("Arial", 12, "bold"))
        title_label.pack(side='left')
        
        # Pencere kontrol butonları (sağ üst)
        window_controls = ttk.Frame(title_frame)
        window_controls.pack(side='right')
        
        # Alta Al (Minimize) butonu
        minimize_btn = ttk.Button(window_controls, text="🗕 Alta Al", width=10,
                                  command=lambda: self.win.iconify())
        minimize_btn.pack(side='left', padx=2)
        
        # 3. Step penceresinin ana pencereye erişebilmesi için referansları ekle
        # FinalThgLotDistributor, parent üzerinden 'main_window' arıyor
        self.main_window = parent
        try:
            # Toplevel objesine de aynı referansı ekle
            self.win.main_window = parent
        except Exception:
            pass
        
        # Varsayılan değerler - exposureadjuster.csv'deki değerlerle aynı
        self.total_exposure = 1000000  # 1M USD
        self.avg_pref_price = 25.0     # 25 USD
        self.long_ratio = 85.0         # %85 (CSV'deki değer)
        self.short_ratio = 15.0        # %15 (CSV'deki değer)
        
        # Lot hakları
        self.long_lot_rights = 34000   # 34K Long
        self.short_lot_rights = 6000   # 6K Short
        
        # Tüm kümeler ve varsayılan yüzdeleri - exposureadjuster.csv'deki değerlerle aynı
        self.long_groups = {
            'heldcilizyeniyedi': 0.0,    # %0.0
            'heldcommonsuz': 0.0,        # %0.0
            'helddeznff': 10.0,          # %10.0
            'heldff': 35.0,              # %35.0 (CSV'deki değer)
            'heldflr': 0.0,              # %0.0
            'heldgarabetaltiyedi': 0.0,  # %0.0
            'heldkuponlu': 15.0,         # %15.0 (CSV'deki değer)
            'heldkuponlukreciliz': 0.0,  # %0.0
            'heldkuponlukreorta': 0.0,   # %0.0
            'heldnff': 5.0,              # %5.0 (CSV'deki değer)
            'heldotelremorta': 3.0,      # %3.0 (CSV'deki değer)
            'heldsolidbig': 5.0,         # %5.0 (CSV'deki değer)
            'heldtitrekhc': 8.0,         # %8.0 (CSV'deki değer)
            'highmatur': 15.0,           # %15.0 (CSV'deki değer)
            'notbesmaturlu': 0.0,        # %0.0
            'notcefilliquid': 0.0,       # %0.0
            'nottitrekhc': 4.0,          # %4.0 (CSV'deki değer)
            'rumoreddanger': 0.0,        # %0.0
            'salakilliquid': 0.0,        # %0.0
            'shitremhc': 0.0             # %0.0
        }
        
        self.short_groups = {
            'heldcilizyeniyedi': 0,    # %0
            'heldcommonsuz': 0,        # %0
            'helddeznff': 30,          # %30
            'heldff': 0,               # %0
            'heldflr': 0,              # %0
            'heldgarabetaltiyedi': 0,  # %0
            'heldkuponlu': 50,         # %50
            'heldkuponlukreciliz': 20, # %20
            'heldkuponlukreorta': 0,   # %0
            'heldnff': 0,              # %0
            'heldotelremorta': 0,      # %0
            'heldsolidbig': 0,         # %0
            'heldtitrekhc': 0,         # %0
            'highmatur': 0,            # %0
            'notbesmaturlu': 0,        # %0
            'notcefilliquid': 0,       # %0
            'nottitrekhc': 0,          # %0
            'rumoreddanger': 0,        # %0
            'salakilliquid': 0,        # %0
            'shitremhc': 0             # %0
        }
        
        self.setup_ui()
        self.calculate_lots()
        
        # Stock Data Manager referansı
        self.stock_data_manager = None
    
    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        # Başlık
        title_label = ttk.Label(self.win, text="Port Adjuster - Portföy Ayarları", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=5)
        
        # Ana butonlar - Başlığın altında
        button_frame = ttk.Frame(self.win)
        button_frame.pack(pady=5)
        
        # Hesapla butonu
        hesapla_btn = ttk.Button(button_frame, text="Hesapla", command=self.calculate_lots)
        hesapla_btn.pack(side='left', padx=5)
        
        # Uygula butonu
        uygula_btn = ttk.Button(button_frame, text="Uygula", command=self.calculate_lots)
        uygula_btn.pack(side='left', padx=5)
        
        # CSV'den Yükle butonu
        yukle_btn = ttk.Button(button_frame, text="CSV'den Yükle", command=self.load_settings_from_csv)
        yukle_btn.pack(side='left', padx=5)
        
        # Hisse Veri Çek butonu
        veri_cek_btn = ttk.Button(button_frame, text="Hisse Veri Çek", command=self.fetch_stock_data)
        veri_cek_btn.pack(side='left', padx=5)
        
        # Kaydet butonu
        kaydet_btn = ttk.Button(button_frame, text="exposureadjuster.csv'ye Kaydet", command=self.save_settings)
        kaydet_btn.pack(side='left', padx=5)
        

        
        # 3. Step - Final FB & SFS Lot Dağıtıcı butonu
        final_thg_btn = ttk.Button(button_frame, text="3. Step - Final FB & SFS", 
                                   command=self.show_final_thg_distributor, 
                                   style='Accent.TButton')
        final_thg_btn.pack(side='left', padx=5)
        
        # Kapat butonu
        kapat_btn = ttk.Button(button_frame, text="Kapat", command=self.win.destroy)
        kapat_btn.pack(side='left', padx=5)
        
        print("[PORT ADJUSTER] ✅ Ana butonlar oluşturuldu")
        
        # Hisse arama frame'i
        search_frame = ttk.Frame(self.win)
        search_frame.pack(fill='x', padx=10, pady=5)
        
        # Hisse arama etiketi
        ttk.Label(search_frame, text="Hisse Sembolü:").pack(side='left', padx=5)
        
        # Hisse arama girişi
        self.symbol_entry = ttk.Entry(search_frame, width=15)
        self.symbol_entry.pack(side='left', padx=5)
        self.symbol_entry.insert(0, "CFG PRE")  # Örnek hisse
        
        # Arama butonu
        search_btn = ttk.Button(search_frame, text="Ara", command=self.search_stock)
        search_btn.pack(side='left', padx=5)
        
        # Sonuç etiketi
        self.result_label = ttk.Label(search_frame, text="", font=("Arial", 10))
        self.result_label.pack(side='left', padx=20)
        
        # 1. Step Frame - Daha kompakt
        step1_frame = ttk.LabelFrame(self.win, text="1. Step - Genel Ayarlar", padding=5)
        step1_frame.pack(fill='x', padx=10, pady=2)
        
        # İlk satır - Total Exposure ve Avg Pref Price yan yana
        first_row = ttk.Frame(step1_frame)
        first_row.pack(fill='x', pady=2)
        
        # Total Exposure
        ttk.Label(first_row, text="Total Exposure (USD):", width=18).pack(side='left')
        self.exposure_entry = ttk.Entry(first_row, width=12)
        self.exposure_entry.pack(side='left', padx=5)
        self.exposure_entry.insert(0, f"{self.total_exposure:,}")
        
        # Avg Pref Price
        ttk.Label(first_row, text="Avg Pref Price (USD):", width=18).pack(side='left', padx=(20,0))
        self.price_entry = ttk.Entry(first_row, width=12)
        self.price_entry.pack(side='left', padx=5)
        self.price_entry.insert(0, str(self.avg_pref_price))
        
        # İkinci satır - Total Lot
        second_row = ttk.Frame(step1_frame)
        second_row.pack(fill='x', pady=2)
        ttk.Label(second_row, text="Total Lot:", width=18).pack(side='left')
        self.total_lot_label = ttk.Label(second_row, text="40,000", font=("Arial", 10, "bold"))
        self.total_lot_label.pack(side='left', padx=5)
        
        # Üçüncü satır - Long/Short Ratio yan yana
        third_row = ttk.Frame(step1_frame)
        third_row.pack(fill='x', pady=2)
        ttk.Label(third_row, text="Long Ratio (%):", width=18).pack(side='left')
        self.long_ratio_entry = ttk.Entry(third_row, width=8)
        self.long_ratio_entry.pack(side='left', padx=5)
        
        ttk.Label(third_row, text="Short Ratio (%):", width=18).pack(side='left', padx=(20,0))
        self.short_ratio_entry = ttk.Entry(third_row, width=8)
        self.short_ratio_entry.pack(side='left', padx=5)
        
        # Dördüncü satır - Long/Short Lot yan yana
        fourth_row = ttk.Frame(step1_frame)
        fourth_row.pack(fill='x', pady=2)
        ttk.Label(fourth_row, text="Long Lot:", width=18).pack(side='left')
        self.long_lot_label = ttk.Label(fourth_row, text="26,000", font=("Arial", 10, "bold"))
        self.long_lot_label.pack(side='left', padx=5)
        
        ttk.Label(fourth_row, text="Short Lot:", width=18).pack(side='left', padx=(20,0))
        self.short_lot_label = ttk.Label(fourth_row, text="14,000", font=("Arial", 10, "bold"))
        self.short_lot_label.pack(side='left', padx=5)
        
        # Değerleri güncelle
        self.long_ratio_entry.insert(0, str(self.long_ratio))
        self.short_ratio_entry.insert(0, str(self.short_ratio))
        
        # 2. Step Frame
        step2_frame = ttk.LabelFrame(self.win, text="2. Step - Kümelerde Dağıtım", padding=10)
        step2_frame.pack(fill='both', expand=True, padx=10, pady=2)
        
        # Notebook (tab) oluştur
        notebook = ttk.Notebook(step2_frame)
        notebook.pack(fill='both', expand=True)
        
        # Long Groups Tab
        long_tab = ttk.Frame(notebook)
        notebook.add(long_tab, text="Long Groups")
        self.setup_long_groups_tab(long_tab)
        
        # Short Groups Tab
        short_tab = ttk.Frame(notebook)
        notebook.add(short_tab, text="Short Groups")
        self.setup_short_groups_tab(short_tab)
    
    def setup_long_groups_tab(self, parent):
        """Long groups tab'ını oluştur"""
        # Başlık ve butonlar yan yana
        title_frame = ttk.Frame(parent)
        title_frame.pack(fill='x', pady=5)
        
        ttk.Label(title_frame, text="Long Kümelerde Lot Dağıtımı", 
                 font=("Arial", 12, "bold")).pack(side='left')
        
        # Sıfırla butonu
        sifirla_btn = ttk.Button(title_frame, text="Sıfırla", command=self.reset_long_groups)
        sifirla_btn.pack(side='right', padx=5)
        
        # Toplam oran bilgisi (kırmızı/mavi)
        self.long_total_ratio_label = ttk.Label(parent, text="", font=("Arial", 10, "bold"))
        self.long_total_ratio_label.pack(pady=2)
        
        # Ana container frame - Çok daha yukarıda
        main_container = ttk.Frame(parent)
        main_container.pack(fill='both', expand=True, padx=5, pady=0)  # pady=2'den pady=0'a düşürüldü
        
        # Sol taraf - Tablo
        table_frame = ttk.Frame(main_container)
        table_frame.pack(side='left', fill='both', expand=True)
        
        # Tablo - Çok daha kısa height
        cols = ['group', 'lot_amount', 'total_value']
        headers = ['Küme', 'Lot Miktarı', 'Toplam Değer (USD)']
        
        self.long_tree = ttk.Treeview(table_frame, columns=cols, show='headings', height=4)  # height=6'dan height=4'e düşürüldü
        
        for c, h in zip(cols, headers):
            self.long_tree.heading(c, text=h)
            if c == 'group':
                self.long_tree.column(c, width=150, anchor='center')
            elif c == 'lot_amount':
                self.long_tree.column(c, width=120, anchor='center')
            else:
                self.long_tree.column(c, width=150, anchor='center')
        
        # Scrollbar
        long_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.long_tree.yview)
        self.long_tree.configure(yscrollcommand=long_scrollbar.set)
        
        self.long_tree.pack(side='left', fill='both', expand=True)
        long_scrollbar.pack(side='right', fill='y')
        
        # Sağ taraf - Yüzde giriş alanları (daha yukarıda)
        percentage_frame = ttk.Frame(main_container)
        percentage_frame.pack(side='right', fill='y', padx=(15, 0))
        
        # Yüzde başlığı
        ttk.Label(percentage_frame, text="Yüzde (%)", font=("Arial", 10, "bold")).pack(pady=(0, 3))  # pady=(0, 5)'ten pady=(0, 3)'e düşürüldü
        
        # Yüzde giriş alanları için container
        self.long_percentage_container = ttk.Frame(percentage_frame)
        self.long_percentage_container.pack(fill='y')
        
        # Bilgi etiketi - Daha yukarıda
        info_label = ttk.Label(parent, text="Yüzdeyi değiştirmek için sağdaki kutucuklara yazın", 
                              font=("Arial", 9, "italic"))
        info_label.pack(pady=1)  # pady=2'den pady=1'e düşürüldü
    
    def setup_short_groups_tab(self, parent):
        """Short groups tab'ını oluştur"""
        # Başlık ve butonlar yan yana
        title_frame = ttk.Frame(parent)
        title_frame.pack(fill='x', pady=5)
        
        ttk.Label(title_frame, text="Short Kümelerde Lot Dağıtımı", 
                 font=("Arial", 12, "bold")).pack(side='left')
        
        # Sıfırla butonu
        sifirla_btn = ttk.Button(title_frame, text="Sıfırla", command=self.reset_short_groups)
        sifirla_btn.pack(side='right', padx=5)
        
        # Toplam oran bilgisi (kırmızı/mavi)
        self.short_total_ratio_label = ttk.Label(parent, text="", font=("Arial", 10, "bold"))
        self.short_total_ratio_label.pack(pady=2)
        
        # Ana container frame - Çok daha yukarıda
        main_container = ttk.Frame(parent)
        main_container.pack(fill='both', expand=True, padx=5, pady=0)  # pady=2'den pady=0'a düşürüldü
        
        # Sol taraf - Tablo
        table_frame = ttk.Frame(main_container)
        table_frame.pack(side='left', fill='both', expand=True)
        
        # Tablo - Çok daha kısa height
        cols = ['group', 'lot_amount', 'total_value']
        headers = ['Küme', 'Lot Miktarı', 'Toplam Değer (USD)']
        
        self.short_tree = ttk.Treeview(table_frame, columns=cols, show='headings', height=4)  # height=6'dan height=4'e düşürüldü
        
        for c, h in zip(cols, headers):
            self.short_tree.heading(c, text=h)
            if c == 'group':
                self.short_tree.column(c, width=150, anchor='center')
            elif c == 'lot_amount':
                self.short_tree.column(c, width=120, anchor='center')
            else:
                self.short_tree.column(c, width=150, anchor='center')
        
        # Scrollbar
        short_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.short_tree.yview)
        self.short_tree.configure(yscrollcommand=short_scrollbar.set)
        
        self.short_tree.pack(side='left', fill='both', expand=True)
        short_scrollbar.pack(side='right', fill='y')
        
        # Sağ taraf - Yüzde giriş alanları (daha yukarıda)
        percentage_frame = ttk.Frame(main_container)
        percentage_frame.pack(side='right', fill='y', padx=(15, 0))
        
        # Yüzde başlığı
        ttk.Label(percentage_frame, text="Yüzde (%)", font=("Arial", 10, "bold")).pack(pady=(0, 3))  # pady=(0, 5)'ten pady=(0, 3)'e düşürüldü
        
        # Yüzde giriş alanları için container
        self.short_percentage_container = ttk.Frame(percentage_frame)
        self.short_percentage_container.pack(fill='y')
        
        # Bilgi etiketi - Daha yukarıda
        info_label = ttk.Label(parent, text="Yüzdeyi değiştirmek için sağdaki kutucuklara yazın", 
                              font=("Arial", 9, "italic"))
        info_label.pack(pady=1)  # pady=2'den pady=1'e düşürüldü
    
    def calculate_lots(self):
        """Lot hesaplamalarını yap"""
        try:
            # Değerleri al
            self.total_exposure = float(self.exposure_entry.get().replace(',', ''))
            self.avg_pref_price = float(self.price_entry.get())
            self.long_ratio = float(self.long_ratio_entry.get())
            self.short_ratio = float(self.short_ratio_entry.get())
            
            # Total lot hesapla
            total_lot = self.total_exposure / self.avg_pref_price
            
            # Long/Short lot hesapla
            long_lot = total_lot * (self.long_ratio / 100)
            short_lot = total_lot * (self.short_ratio / 100)
            
            # Labels güncelle
            self.total_lot_label.config(text=f"{total_lot:,.0f}")
            self.long_lot_label.config(text=f"{long_lot:,.0f}")
            self.short_lot_label.config(text=f"{short_lot:,.0f}")
            
            # Tabloları güncelle
            self.update_long_groups_table(long_lot)
            self.update_short_groups_table(short_lot)
            
            print(f"[PORT ADJUSTER] ✅ Hesaplama tamamlandı:")
            print(f"  Total Exposure: ${self.total_exposure:,.0f}")
            print(f"  Avg Price: ${self.avg_pref_price:.2f}")
            print(f"  Total Lot: {total_lot:,.0f}")
            print(f"  Long Lot: {long_lot:,.0f} ({self.long_ratio}%)")
            print(f"  Short Lot: {short_lot:,.0f} ({self.short_ratio}%)")
            
        except Exception as e:
            print(f"[PORT ADJUSTER] ❌ Hesaplama hatası: {e}")
            messagebox.showerror("Hata", f"Hesaplama hatası: {e}")
    
    def update_long_groups_table(self, total_long_lot):
        """Long groups tablosunu güncelle"""
        # Tabloyu temizle
        for item in self.long_tree.get_children():
            self.long_tree.delete(item)
        
        # Yüzde giriş alanlarını temizle
        for widget in self.long_percentage_container.winfo_children():
            widget.destroy()
        
        # Verileri ekle
        for group, percentage in self.long_groups.items():
            lot_amount = total_long_lot * (percentage / 100)
            total_value = lot_amount * self.avg_pref_price
            
            self.long_tree.insert('', 'end', values=[
                group,
                f"{lot_amount:,.0f}",
                f"${total_value:,.0f}"
            ])
            
            # Yüzde giriş alanı oluştur - küme ismi ile birlikte
            entry_frame = ttk.Frame(self.long_percentage_container)
            entry_frame.pack(fill='x', pady=0)  # pady=1'den pady=0'a düşürüldü
            
            # Küme ismi etiketi - SOL TARAFTA
            group_label = ttk.Label(entry_frame, text=f"{group}:", width=25, anchor='w')
            group_label.pack(side='left')
            
            # Yüzde giriş alanı - SAĞ TARAFTA
            percentage_entry = ttk.Entry(entry_frame, width=8)
            percentage_entry.pack(side='right', padx=(5, 0))
            percentage_entry.insert(0, str(percentage))
            
            # Entry'yi bind et - sadece kutucuktan çıkınca güncelle
            percentage_entry.bind('<FocusOut>', lambda e, g=group, entry=percentage_entry: self.update_percentage(g, entry.get(), 'long'))
        
        # Toplam oran bilgisini güncelle
        total_percentage = sum(self.long_groups.values())
        if total_percentage > 100:
            # Kırmızı uyarı - fazla lot
            excess_lot = total_long_lot * ((total_percentage - 100) / 100)
            self.long_total_ratio_label.config(
                text=f"⚠️ Toplam oran %{total_percentage:.1f} - {excess_lot:,.0f} lot fazlanız var!",
                foreground="red"
            )
        elif total_percentage < 100:
            # Mavi bilgi - eksik lot
            missing_lot = total_long_lot * ((100 - total_percentage) / 100)
            self.long_total_ratio_label.config(
                text=f"ℹ️ Toplam oran %{total_percentage:.1f} - {missing_lot:,.0f} lot daha eklenebilir",
                foreground="blue"
            )
        else:
            # Yeşil - tam %100
            self.long_total_ratio_label.config(
                text=f"✅ Toplam oran %{total_percentage:.1f} - Mükemmel!",
                foreground="green"
            )
    
    def update_short_groups_table(self, total_short_lot):
        """Short groups tablosunu güncelle"""
        # Tabloyu temizle
        for item in self.short_tree.get_children():
            self.short_tree.delete(item)
        
        # Yüzde giriş alanlarını temizle
        for widget in self.short_percentage_container.winfo_children():
            widget.destroy()
        
        # Verileri ekle
        for group, percentage in self.short_groups.items():
            lot_amount = total_short_lot * (percentage / 100)
            total_value = lot_amount * self.avg_pref_price
            
            self.short_tree.insert('', 'end', values=[
                group,
                f"{lot_amount:,.0f}",
                f"${total_value:,.0f}"
            ])
            
            # Yüzde giriş alanı oluştur - küme ismi ile birlikte
            entry_frame = ttk.Frame(self.short_percentage_container)
            entry_frame.pack(fill='x', pady=0)  # pady=1'den pady=0'a düşürüldü
            
            # Küme ismi etiketi - SOL TARAFTA
            group_label = ttk.Label(entry_frame, text=f"{group}:", width=25, anchor='w')
            group_label.pack(side='left')
            
            # Yüzde giriş alanı - SAĞ TARAFTA
            percentage_entry = ttk.Entry(entry_frame, width=8)
            percentage_entry.pack(side='right', padx=(5, 0))
            percentage_entry.insert(0, str(percentage))
            
            # Entry'yi bind et - sadece kutucuktan çıkınca güncelle
            percentage_entry.bind('<FocusOut>', lambda e, g=group, entry=percentage_entry: self.update_percentage(g, entry.get(), 'short'))
        
        # Toplam oran bilgisini güncelle
        total_percentage = sum(self.short_groups.values())
        if total_percentage > 100:
            # Kırmızı uyarı - fazla lot
            excess_lot = total_short_lot * ((total_percentage - 100) / 100)
            self.short_total_ratio_label.config(
                text=f"⚠️ Toplam oran %{total_percentage:.1f} - {excess_lot:,.0f} lot fazlanız var!",
                foreground="red"
            )
        elif total_percentage < 100:
            # Mavi bilgi - eksik lot
            missing_lot = total_short_lot * ((100 - total_percentage) / 100)
            self.short_total_ratio_label.config(
                text=f"ℹ️ Toplam oran %{total_percentage:.1f} - {missing_lot:,.0f} lot daha eklenebilir",
                foreground="blue"
            )
        else:
            # Yeşil - tam %100
            self.short_total_ratio_label.config(
                text=f"✅ Toplam oran %{total_percentage:.1f} - Mükemmel!",
                foreground="green"
            )
    
    def update_percentage(self, group, value, group_type):
        """Yüzde değerini güncelle ve otomatik hesapla"""
        try:
            percentage = float(value)
            if group_type == 'long':
                self.long_groups[group] = percentage
            else:
                self.short_groups[group] = percentage
            
            # Hesaplamayı yeniden yap
            self.calculate_lots()
            
        except ValueError:
            # Geçersiz değer girildiğinde hata verme
            pass
    
    def reset_long_groups(self):
        """Long gruplarını sıfırla"""
        for group in self.long_groups:
            self.long_groups[group] = 0
        self.calculate_lots()
        self.update_long_groups_table(self.total_exposure / self.avg_pref_price * (self.long_ratio / 100))
        messagebox.showinfo("Sıfırlama Tamamlandı", "Long grupları sıfırlandı.")
    
    def reset_short_groups(self):
        """Short gruplarını sıfırla"""
        for group in self.short_groups:
            self.short_groups[group] = 0
        self.calculate_lots()
        self.update_short_groups_table(self.total_exposure / self.avg_pref_price * (self.short_ratio / 100))
        messagebox.showinfo("Sıfırlama Tamamlandı", "Short grupları sıfırlandı.")
    
    def load_settings_from_csv(self):
        """CSV'den ayarları yükle"""
        try:
            # Ana dizindeki exposureadjuster.csv'yi kullan (StockTracker dizini)
            # Absolute path kullanarak working directory sorununu çöz
            current_dir = os.path.dirname(os.path.abspath(__file__))  # janallapp dizini
            project_root = os.path.dirname(os.path.dirname(current_dir))  # StockTracker dizini
            csv_filename = os.path.join(project_root, 'exposureadjuster.csv')
            if not os.path.exists(csv_filename):
                print(f"[PORT ADJUSTER] ⚠️ {csv_filename} bulunamadı, varsayılan ayarlar kullanılıyor")
                return
            
            # Bölüm takibi için değişkenler
            long_groups_section = False
            short_groups_section = False
            
            import csv
            with open(csv_filename, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    setting = row.get('Setting', '').strip()
                    value = row.get('Value', '').strip()
                    
                    if setting == 'Total Exposure':
                        try:
                            exposure_str = value.replace('$', '').replace(',', '')
                            self.total_exposure = float(exposure_str)
                            if hasattr(self, 'exposure_entry'):
                                self.exposure_entry.delete(0, tk.END)
                                self.exposure_entry.insert(0, f"{self.total_exposure:,.0f}")
                        except:
                            pass
                    
                    elif setting == 'Avg Pref Price':
                        try:
                            price_str = value.replace('$', '').replace(',', '')
                            self.avg_pref_price = float(price_str)
                            if hasattr(self, 'price_entry'):
                                self.price_entry.delete(0, tk.END)
                                self.price_entry.insert(0, str(self.avg_pref_price))
                        except:
                            pass
                    
                    elif setting == 'Long Ratio':
                        try:
                            ratio_str = value.replace('%', '')
                            self.long_ratio = float(ratio_str)
                            if hasattr(self, 'long_ratio_entry'):
                                self.long_ratio_entry.delete(0, tk.END)
                                self.long_ratio_entry.insert(0, str(self.long_ratio))
                        except:
                            pass
                    
                    elif setting == 'Short Ratio':
                        try:
                            ratio_str = value.replace('%', '')
                            self.short_ratio = float(ratio_str)
                            if hasattr(self, 'short_ratio_entry'):
                                self.short_ratio_entry.delete(0, tk.END)
                                self.short_ratio_entry.insert(0, str(self.short_ratio))
                        except:
                            pass
                    
                    elif setting == 'Long Groups':
                        # Long groups bölümü başladı
                        long_groups_section = True
                        short_groups_section = False
                        continue
                    
                    elif setting == 'Short Groups':
                        # Short groups bölümü başladı
                        long_groups_section = False
                        short_groups_section = True
                        continue
                    
                    elif setting and '%' in value:
                        # Küme yüzdesi
                        try:
                            group = setting
                            percentage = float(value.replace('%', ''))
                            
                            # Hangi bölümde olduğumuzu kontrol et
                            if long_groups_section and group in self.long_groups:
                                self.long_groups[group] = percentage
                                print(f"[PORT ADJUSTER] 📊 Long {group}: {percentage}%")
                            elif short_groups_section and group in self.short_groups:
                                self.short_groups[group] = percentage
                                print(f"[PORT ADJUSTER] 📊 Short {group}: {percentage}%")
                        except Exception as e:
                            print(f"[PORT ADJUSTER] ⚠️ {group} yüzdesi yüklenirken hata: {e}")
            
            print(f"[PORT ADJUSTER] ✅ Ayarlar {csv_filename} dosyasından yüklendi")
            
            # UI'da grup yüzdelerini güncelle
            self.update_group_percentages_ui()
            
            # Hesaplamaları yap
            self.calculate_lots()
            
        except Exception as e:
            print(f"[PORT ADJUSTER] ❌ CSV yükleme hatası: {e}")
    
    def set_stock_data_manager(self, manager):
        """Stock Data Manager referansını ayarla"""
        self.stock_data_manager = manager
        print("[PORT ADJUSTER] ✅ Stock Data Manager referansı ayarlandı")
    
    def fetch_stock_data(self):
        """Stock Data Manager'dan hisse verilerini çek"""
        try:
            if not self.stock_data_manager:
                self.result_label.config(text="❌ Stock Data Manager bağlantısı yok!")
                return
            
            # Tüm hisseleri listele
            all_stocks = self.stock_data_manager.get_all_stocks()
            if all_stocks:
                self.result_label.config(text=f"✅ {len(all_stocks)} hisse bulundu")
                print(f"[PORT ADJUSTER] 📋 Toplam {len(all_stocks)} hisse:")
                for i, stock in enumerate(all_stocks[:10]):  # İlk 10'unu göster
                    print(f"  {i+1}. {stock}")
                if len(all_stocks) > 10:
                    print(f"  ... ve {len(all_stocks) - 10} tane daha")
            else:
                self.result_label.config(text="❌ Hiç hisse bulunamadı")
                
        except Exception as e:
            self.result_label.config(text=f"❌ Hata: {e}")
            print(f"[PORT ADJUSTER] ❌ Hisse veri çekme hatası: {e}")
    
    def search_stock(self):
        """Belirli bir hisse için veri ara"""
        try:
            if not self.stock_data_manager:
                self.result_label.config(text="❌ Stock Data Manager bağlantısı yok!")
                return
            
            symbol = self.symbol_entry.get().strip().upper()
            if not symbol:
                self.result_label.config(text="❌ Hisse sembolü girin!")
                return
            
            # Hisse verilerini al
            stock_data = self.stock_data_manager.get_stock_data(symbol)
            if not stock_data:
                self.result_label.config(text=f"❌ {symbol} bulunamadı!")
                return
            
            # Fiyat verilerini al
            price_data = self.stock_data_manager.get_stock_price_data(symbol)
            
            # Skor verilerini al
            score_data = self.stock_data_manager.get_stock_scores(symbol)
            
            # Sonuçları göster
            result_text = f"✅ {symbol} bulundu!\n"
            
            if price_data:
                result_text += f"💰 Fiyat: Bid={price_data.get('bid', 'N/A')}, Ask={price_data.get('ask', 'N/A')}, Last={price_data.get('last', 'N/A')}, Prev={price_data.get('prev_close', 'N/A')}\n"
            
            if score_data:
                result_text += f"📊 Skorlar: FB={score_data.get('Final_FB_skor', 'N/A')}, SFS={score_data.get('Final_SFS_skor', 'N/A')}, BB={score_data.get('Final_BB_skor', 'N/A')}\n"
            
            # Diğer önemli verileri göster
            important_cols = ['CMON', 'CGRUP', 'FINAL_THG', 'AVG_ADV', 'SMI', 'SHORT_FINAL']
            for col in important_cols:
                if col in stock_data:
                    result_text += f"📋 {col}: {stock_data[col]}\n"
            
            self.result_label.config(text=result_text)
            print(f"[PORT ADJUSTER] 🔍 {symbol} arama sonucu:")
            print(f"  Fiyat verileri: {price_data}")
            print(f"  Skor verileri: {score_data}")
            
        except Exception as e:
            self.result_label.config(text=f"❌ Hata: {e}")
            print(f"[PORT ADJUSTER] ❌ Hisse arama hatası: {e}")
    
    def save_settings(self):
        """Ayarları kaydet"""
        try:
            # CSV olarak kaydet
            import csv
            import os
            
            # Ana dizindeki CSV dosyasına kaydet (StockTracker dizini)
            # Absolute path kullanarak working directory sorununu çöz
            current_dir = os.path.dirname(os.path.abspath(__file__))  # janallapp dizini
            project_root = os.path.dirname(os.path.dirname(current_dir))  # StockTracker dizini
            csv_filename = os.path.join(project_root, 'exposureadjuster.csv')
            with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Setting', 'Value'])
                writer.writerow(['Total Exposure', f"${self.total_exposure:,.0f}"])
                writer.writerow(['Avg Pref Price', f"${self.avg_pref_price:.2f}"])
                writer.writerow(['Long Ratio', f"{self.long_ratio}%"])
                writer.writerow(['Short Ratio', f"{self.short_ratio}%"])
                writer.writerow([])
                writer.writerow(['Long Groups', 'Percentage'])
                for group, percentage in self.long_groups.items():
                    writer.writerow([group, f"{percentage}%"])
                writer.writerow([])
                writer.writerow(['Short Groups', 'Percentage'])
                for group, percentage in self.short_groups.items():
                    writer.writerow([group, f"{percentage}%"])
            
            print(f"[PORT ADJUSTER] ✅ Ayarlar kaydedildi: {csv_filename}")
            messagebox.showinfo("Başarılı", f"Port ayarları {csv_filename} dosyasına kaydedildi!")
            
        except Exception as e:
            print(f"[PORT ADJUSTER] ❌ Kaydetme hatası: {e}")
            messagebox.showerror("Hata", f"Kaydetme hatası: {e}")
    

    def update_group_percentages_ui(self):
        """Grup yüzdelerini UI'da güncelle"""
        try:
            # Long groups için yüzde giriş alanlarını güncelle
            for group, percentage in self.long_groups.items():
                if hasattr(self, 'long_percentage_entries') and group in self.long_percentage_entries:
                    entry = self.long_percentage_entries[group]
                    entry.delete(0, tk.END)
                    entry.insert(0, str(percentage))
            
            # Short groups için yüzde giriş alanlarını güncelle
            for group, percentage in self.short_groups.items():
                if hasattr(self, 'short_percentage_entries') and group in self.short_percentage_entries:
                    entry = self.short_percentage_entries[group]
                    entry.delete(0, tk.END)
                    entry.insert(0, str(percentage))
            
            print("[PORT ADJUSTER] ✅ Grup yüzdeleri UI'da güncellendi")
            
        except Exception as e:
            print(f"[PORT ADJUSTER] ❌ UI güncelleme hatası: {e}")
    
    def show_final_thg_distributor(self):
        """FINAL THG Lot Dağıtıcı penceresini aç"""
        try:
            from .final_thg_lot_distributor import FinalThgLotDistributor
            # PORT ADJUSTER OBJESİNİ (self) geç, window'u (self.win) değil!
            final_thg = FinalThgLotDistributor(self)
            # FinalThgLotDistributor referansını sakla (ADDNEWPOS için)
            self.final_thg_distributor = final_thg
            print("[PORT ADJUSTER] ✅ FINAL THG Lot Dağıtıcı açıldı - Port Adjuster referansı geçildi")
            return final_thg
        except SyntaxError as e:
            error_msg = f"3. Step dosyasında syntax hatası var (Satır {e.lineno}): {e.msg}"
            print(f"[PORT ADJUSTER] ❌ Syntax Error: {error_msg}")
            messagebox.showerror("Syntax Hatası", 
                f"3. Step penceresinde syntax hatası bulundu!\n\n"
                f"Satır {e.lineno}: {e.msg}\n\n"
                f"Lütfen final_thg_lot_distributor.py dosyasındaki\n"
                f"indentation (girinti) hatalarını düzeltin.")
        except Exception as e:
            print(f"[PORT ADJUSTER] ❌ FINAL THG Lot Dağıtıcı açılamadı: {e}")
            messagebox.showerror("Hata", f"FINAL THG Lot Dağıtıcı açılamadı: {e}")
    
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
                # En yüksek FINAL_THG'ya sahip olanları seç
                selected = group.nlargest(max_allowed, 'FINAL_THG')
            else:  # SHORT
                # En düşük SHORT_FINAL'a sahip olanları seç
                selected = group.nsmallest(max_allowed, 'SHORT_FINAL')
            
            limited_stocks.append(selected)
        
        if limited_stocks:
            return pd.concat(limited_stocks, ignore_index=True)
        else:
            return pd.DataFrame()
    
    def select_stocks_by_rules(self, file_name, df):
        """
        ntumcsvport.py'deki mantıkla hisseleri seçer
        """
        try:
            # Dosya için özel kuralları al
            file_basename = os.path.basename(file_name)
            if file_basename in self.file_rules:
                rules = self.file_rules[file_basename]
            else:
                # Varsayılan kural
                rules = {
                    'long_percent': 25, 'long_multiplier': 1.5,
                    'short_percent': 25, 'short_multiplier': 0.7,
                    'max_short': 3
                }
            
            print(f"   📋 Kurallar: LONG {rules['long_percent']}% + {rules['long_multiplier']}x, SHORT {rules['short_percent']}% + {rules['short_multiplier']}x")
            
            # Final_FB_skor ve Final_SFS_skor kolonlarını ekleme (eksikse)
            if 'Final_FB_skor' not in df.columns:
                df['Final_FB_skor'] = df.get('FINAL_THG', 0)  # Fallback
            if 'Final_SFS_skor' not in df.columns:
                df['Final_SFS_skor'] = df.get('SHORT_FINAL', 0)  # Fallback
            
            # Ortalama değerleri hesapla - Artık Final_FB_skor ve Final_SFS_skor kullanıyoruz!
            avg_final_fb = df['Final_FB_skor'].mean()
            avg_final_sfs = df['Final_SFS_skor'].mean()
            
            print(f"   📈 Ortalama Final_FB_skor: {avg_final_fb:.4f}")
            print(f"   📉 Ortalama Final_SFS_skor: {avg_final_sfs:.4f}")
            
            # LONG hisseleri seç - Final_FB_skor kullanıyoruz (yüksek olması iyi)
            long_candidates = df[df['Final_FB_skor'] >= (avg_final_fb * rules['long_multiplier'])].copy()
            long_candidates = long_candidates.sort_values('Final_FB_skor', ascending=False)
            
            # Top %X'i hesapla (yukarı yuvarlama)
            top_count = math.ceil(len(df) * rules['long_percent'] / 100)
            top_stocks = df.nlargest(top_count, 'Final_FB_skor')
            
            # İki kriterin kesişimini al
            long_candidates_set = set(long_candidates['PREF IBKR'])
            top_set = set(top_stocks['PREF IBKR'])
            long_intersection = long_candidates_set.intersection(top_set)
            
            # Kesişimdeki hisseleri al
            long_stocks = df[df['PREF IBKR'].isin(long_intersection)].copy()
            
            # Şirket sınırını uygula
            long_stocks_limited = self.limit_by_company(long_stocks, 'LONG', df)
            
            print(f"   🟢 LONG kriterleri:")
            print(f"      - {rules['long_multiplier']}x ortalama kriteri: {len(long_candidates)} hisse")
            print(f"      - Top {rules['long_percent']}% kriteri: {len(top_stocks)} hisse")
            print(f"      - Kesişim: {len(long_stocks)} hisse")
            print(f"      - Şirket sınırı uygulandıktan sonra: {len(long_stocks_limited)} hisse")
            
            # SHORT hisseleri seç - Final_SFS_skor kullanıyoruz (düşük olması iyi)
            short_candidates = df[df['Final_SFS_skor'] <= (avg_final_sfs * rules['short_multiplier'])].copy()
            short_candidates = short_candidates.sort_values('Final_SFS_skor', ascending=True)
            
            # Bottom %X'i hesapla (yukarı yuvarlama)
            bottom_count = math.ceil(len(df) * rules['short_percent'] / 100)
            bottom_stocks = df.nsmallest(bottom_count, 'Final_SFS_skor')
            
            # İki kriterin kesişimini al
            short_candidates_set = set(short_candidates['PREF IBKR'])
            bottom_set = set(bottom_stocks['PREF IBKR'])
            short_intersection = short_candidates_set.intersection(bottom_set)
            
            # Kesişimdeki hisseleri al
            short_stocks = df[df['PREF IBKR'].isin(short_intersection)].copy()
            
            # SHORT sınırını uygula
            if len(short_stocks) > rules['max_short']:
                print(f"   ⚠️ SHORT sınırı uygulanıyor: {len(short_stocks)} → {rules['max_short']}")
                short_stocks = short_stocks.nsmallest(rules['max_short'], 'Final_SFS_skor')
            
            # Şirket sınırını uygula
            short_stocks_limited = self.limit_by_company(short_stocks, 'SHORT', df)
            
            print(f"   🔴 SHORT kriterleri:")
            print(f"      - {rules['short_multiplier']}x ortalama kriteri: {len(short_candidates)} hisse")
            print(f"      - Bottom {rules['short_percent']}% kriteri: {len(bottom_stocks)} hisse")
            print(f"      - Kesişim: {len(short_intersection)} hisse")
            print(f"      - SHORT sınırı uygulandıktan sonra: {len(short_stocks)} hisse")
            print(f"      - Şirket sınırı uygulandıktan sonra: {len(short_stocks_limited)} hisse")
            
            return long_stocks_limited, short_stocks_limited
            
        except Exception as e:
            print(f"   ❌ Hisse seçim hatası: {e}")
            return pd.DataFrame(), pd.DataFrame()
    
    def apply_tumcsv_rules(self):
        """
        TUMCSV kurallarını uygula - Her kümeyi ntumcsvport.py mantığıyla işle
        """
        try:
            print("🚀 TUMCSV AYARLAMASI BAŞLIYOR...")
            print("=" * 80)
            
            # Tüm ssfinek dosyalarını bul
            ssfinek_files = []
            for group in self.long_groups.keys():
                if self.long_groups[group] > 0:  # Sadece pozitif yüzdesi olan gruplar
                    file_name = f"ssfinek{group}.csv"
                    if os.path.exists(file_name):
                        ssfinek_files.append((group, file_name))
                    else:
                        print(f"⚠️ {file_name} bulunamadı, {group} grubu atlanıyor")
            
            print(f"📁 İşlenecek dosyalar: {len(ssfinek_files)} adet")
            
            all_long_stocks = []
            all_short_stocks = []
            
            for group, file_name in ssfinek_files:
                print(f"\n📊 İşleniyor: {group} ({file_name})")
                
                try:
                    # Dosyayı oku
                    df = pd.read_csv(file_name)
                    print(f"   ✅ Dosya okundu: {len(df)} satır")
                    
                    if len(df) == 0:
                        print(f"   ⚠️ Dosya boş, atlanıyor")
                        continue
                    
                    # Gerekli kolonları kontrol et
                    required_columns = ['PREF IBKR', 'FINAL_THG', 'SHORT_FINAL', 'CMON']
                    missing_columns = [col for col in required_columns if col not in df.columns]
                    
                    if missing_columns:
                        print(f"   ❌ Eksik kolonlar: {missing_columns}")
                        continue
                    
                    # Final_FB_skor ve Final_SFS_skor kolonlarını STOCK DATA MANAGER'dan al!
                    print(f"   🔄 Final_FB_skor ve Final_SFS_skor kolonları STOCK DATA MANAGER'dan alınıyor...")
                    
                    # Her hisse için skorları Stock Data Manager'dan al
                    for idx, row in df.iterrows():
                        try:
                            symbol = row.get('PREF IBKR', 'N/A')
                            
                            # ✅ CSV'den FINAL_THG ve SHORT_FINAL değerlerini al (fallback)
                            final_thg = float(row.get('FINAL_THG', 0)) if row.get('FINAL_THG', 0) != 'N/A' else 0
                            short_final = float(row.get('SHORT_FINAL', 0)) if row.get('SHORT_FINAL', 0) != 'N/A' else 0
                            
                            # ✅ STOCK DATA MANAGER'dan Final_FB_skor ve Final_SFS_skor verilerini al
                            final_fb_skor = final_thg  # Varsayılan olarak CSV değeri
                            final_sfs_skor = short_final  # Varsayılan olarak CSV değeri
                            
                            # Top Ten Bid Buy mantığıyla ana sayfadaki DataFrame'den çek
                            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                                try:
                                    parent_df = self.parent.df
                                    # PREF IBKR kolonunda symbol'ü ara
                                    symbol_row = parent_df[parent_df['PREF IBKR'] == symbol]
                                    
                                    if not symbol_row.empty:
                                        # Önce DataFrame'den Final_FB_skor kolonunu kontrol et
                                        if 'Final_FB_skor' in parent_df.columns:
                                            fb_value = symbol_row['Final_FB_skor'].iloc[0]
                                            if pd.notna(fb_value) and fb_value != 'N/A':
                                                final_fb_skor = float(fb_value)
                                                print(f"      ✅ {symbol}: Ana sayfadan Final_FB_skor={final_fb_skor:.2f}")
                                        
                                        # Final_SFS_skor için de aynı mantık
                                        if 'Final_SFS_skor' in parent_df.columns:
                                            sfs_value = symbol_row['Final_SFS_skor'].iloc[0]
                                            if pd.notna(sfs_value) and sfs_value != 'N/A':
                                                final_sfs_skor = float(sfs_value)
                                                print(f"      ✅ {symbol}: Ana sayfadan Final_SFS_skor={final_sfs_skor:.2f}")
                                        
                                        # DataFrame'de yoksa hesapla - Top Ten Bid Buy mantığıyla
                                        if (final_fb_skor == final_thg or final_sfs_skor == short_final) and hasattr(self.parent, 'calculate_scores') and hasattr(self.parent, 'hammer'):
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
                                                scores = self.parent.calculate_scores(symbol, symbol_row.iloc[0], bid_raw, ask_raw, last_raw, prev_close, benchmark_chg)
                                                
                                                if scores:
                                                    if 'Final_FB_skor' in scores:
                                                        final_fb_skor = float(scores['Final_FB_skor'])
                                                        print(f"      ✅ {symbol}: Hesaplanan Final_FB_skor={final_fb_skor:.2f}")
                                                    
                                                    if 'Final_SFS_skor' in scores:
                                                        final_sfs_skor = float(scores['Final_SFS_skor'])
                                                        print(f"      ✅ {symbol}: Hesaplanan Final_SFS_skor={final_sfs_skor:.2f}")
                                            else:
                                                print(f"      ⚠️ {symbol}: Market data alınamadı, CSV değerleri kullanılıyor")
                                                
                                except Exception as e:
                                    print(f"      ⚠️ {symbol}: Ana sayfadan veri alınamadı: {e}")
                                    print(f"        CSV değerleri kullanılıyor: Final_FB_skor={final_thg:.2f}, Final_SFS_skor={short_final:.2f}")
                            else:
                                print(f"      ⚠️ {symbol}: Ana sayfa DataFrame'i yok, CSV değerleri kullanılıyor")
                            
                            # DataFrame'e ekle
                            df.at[idx, 'Final_FB_skor'] = round(final_fb_skor, 2)
                            df.at[idx, 'Final_SFS_skor'] = round(final_sfs_skor, 2)
                            
                        except Exception as e:
                            print(f"      ⚠️ {row.get('PREF IBKR', 'N/A')} skor alınamadı: {e}")
                            df.at[idx, 'Final_FB_skor'] = 0
                            df.at[idx, 'Final_SFS_skor'] = 0
                    
                    print(f"   ✅ Final_FB_skor ve Final_SFS_skor kolonları eklendi!")
                    
                    # ntumcsvport.py mantığıyla hisseleri seç
                    long_stocks, short_stocks = self.select_stocks_by_rules(file_name, df)
                    
                    # Seçilen hisseleri listeye ekle
                    for _, row in long_stocks.iterrows():
                        stock_info = {
                            'GRUP': group,
                            'DOSYA': file_name,
                            'PREF_IBKR': row['PREF IBKR'],
                            'Final_FB_skor': row.get('Final_FB_skor', row.get('FINAL_THG', 0)),
                            'Final_SFS_skor': row.get('Final_SFS_skor', row.get('SHORT_FINAL', 0)),
                            'FINAL_THG': row.get('FINAL_THG', 0),
                            'SHORT_FINAL': row.get('SHORT_FINAL', 0),
                            'SMI': row.get('SMI', 'N/A'),
                            'CGRUP': row.get('CGRUP', 'N/A'),
                            'CMON': row.get('CMON', 'N/A'),
                            'TİP': 'LONG',
                            'GRUP_YUZDESI': self.long_groups[group]
                        }
                        all_long_stocks.append(stock_info)
                    
                    for _, row in short_stocks.iterrows():
                        stock_info = {
                            'GRUP': group,
                            'DOSYA': file_name,
                            'PREF_IBKR': row['PREF IBKR'],
                            'Final_FB_skor': row.get('Final_FB_skor', row.get('FINAL_THG', 0)),
                            'Final_SFS_skor': row.get('Final_SFS_skor', row.get('SHORT_FINAL', 0)),
                            'FINAL_THG': row.get('FINAL_THG', 0),
                            'SHORT_FINAL': row.get('SHORT_FINAL', 0),
                            'SMI': row.get('SMI', 'N/A'),
                            'CGRUP': row.get('CGRUP', 'N/A'),
                            'CMON': row.get('CMON', 'N/A'),
                            'TİP': 'SHORT',
                            'GRUP_YUZDESI': self.short_groups.get(group, 0)
                        }
                        all_short_stocks.append(stock_info)
                    
                    print(f"   🟢 {group}: {len(long_stocks)} LONG, {len(short_stocks)} SHORT hisse seçildi")
                    
                except Exception as e:
                    print(f"   ❌ {group} işlenirken hata: {e}")
                    continue
            
            # Sonuçları göster
            if all_long_stocks or all_short_stocks:
                print(f"\n📊 TUMCSV AYARLAMASI TAMAMLANDI!")
                print(f"   🟢 Toplam LONG: {len(all_long_stocks)} hisse")
                print(f"   🔴 Toplam SHORT: {len(all_short_stocks)} hisse")
                
                # Sonuçları CSV'ye kaydet
                if all_long_stocks:
                    long_df = pd.DataFrame(all_long_stocks)
                    long_df.to_csv('port_adjuster_long_stocks.csv', index=False)
                    print(f"   💾 LONG hisseler: port_adjuster_long_stocks.csv")
                
                if all_short_stocks:
                    short_df = pd.DataFrame(all_short_stocks)
                    short_df.to_csv('port_adjuster_short_stocks.csv', index=False)
                    print(f"   💾 SHORT hisseler: port_adjuster_short_stocks.csv")
                
                messagebox.showinfo("Başarılı", f"TUMCSV ayarlaması tamamlandı!\nLONG: {len(all_long_stocks)} hisse\nSHORT: {len(all_short_stocks)} hisse")
                
            else:
                print(f"\n❌ Hiç hisse seçilemedi!")
                messagebox.showwarning("Uyarı", "Hiç hisse seçilemedi!")
                
        except Exception as e:
            print(f"❌ TUMCSV ayarlaması hatası: {e}")
            messagebox.showerror("Hata", f"TUMCSV ayarlaması hatası: {e}")
