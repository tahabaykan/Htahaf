"""
FINAL THG Tabanlı Lot Dağıtıcı
JANALL uygulamasında Port Adjuster'a entegre edilecek
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
        
        # Ana pencere
        self.win = tk.Toplevel(parent)
        self.win.title("Final FB & SFS Lot Dağıtıcı - 3. Step")
        self.win.geometry("1600x900")
        self.win.transient(parent)
        self.win.grab_set()
        
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
        
        # Long/Short lot hakları
        self.long_lot_rights = 34000  # 34K Long
        self.short_lot_rights = 6000   # 6K Short
        
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
    
    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        # Başlık
        title_label = ttk.Label(self.win, text="Final FB & SFS Tabanlı Lot Dağıtıcı - 3. Step", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=5)
        
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
        
        bb_long_columns = ('Grup', 'Sembol', 'Final_BB_skor', 'Final_SFS_skor', 'SMI', 'MAXALW', 'Hesaplanan Lot')
        self.bb_long_tree = ttk.Treeview(bb_long_frame, columns=bb_long_columns, show='headings', height=15)
        
        # BB Long kolon başlıkları
        for col in bb_long_columns:
            self.bb_long_tree.heading(col, text=col)
            if col in ['Grup', 'Sembol']:
                self.bb_long_tree.column(col, width=120 if col == 'Grup' else 100)
            elif 'skor' in col:
                self.bb_long_tree.column(col, width=120)
            else:
                self.bb_long_tree.column(col, width=80)
        
        bb_long_scrollbar = ttk.Scrollbar(bb_long_frame, orient='vertical', command=self.bb_long_tree.yview)
        self.bb_long_tree.configure(yscrollcommand=bb_long_scrollbar.set)
        self.bb_long_tree.pack(side='left', fill='both', expand=True)
        bb_long_scrollbar.pack(side='right', fill='y')
        
        # 2. FB Long tab (Final_FB_skor kullanarak Long seçimi)
        fb_long_frame = ttk.Frame(notebook)
        notebook.add(fb_long_frame, text="FB Long")
        
        fb_long_columns = ('Grup', 'Sembol', 'Final_FB_skor', 'Final_SFS_skor', 'SMI', 'MAXALW', 'Hesaplanan Lot')
        self.fb_long_tree = ttk.Treeview(fb_long_frame, columns=fb_long_columns, show='headings', height=15)
        
        # FB Long kolon başlıkları
        for col in fb_long_columns:
            self.fb_long_tree.heading(col, text=col)
            if col in ['Grup', 'Sembol']:
                self.fb_long_tree.column(col, width=120 if col == 'Grup' else 100)
            elif 'skor' in col:
                self.fb_long_tree.column(col, width=120)
            else:
                self.fb_long_tree.column(col, width=80)
        
        fb_long_scrollbar = ttk.Scrollbar(fb_long_frame, orient='vertical', command=self.fb_long_tree.yview)
        self.fb_long_tree.configure(yscrollcommand=fb_long_scrollbar.set)
        self.fb_long_tree.pack(side='left', fill='both', expand=True)
        fb_long_scrollbar.pack(side='right', fill='y')
        
        # 3. SAS Short tab (Final_SAS_skor kullanarak Short seçimi)
        sas_short_frame = ttk.Frame(notebook)
        notebook.add(sas_short_frame, text="SAS Short")
        
        sas_short_columns = ('Grup', 'Sembol', 'Final_SAS_skor', 'Final_FB_skor', 'SMI', 'MAXALW', 'Hesaplanan Lot')
        self.sas_short_tree = ttk.Treeview(sas_short_frame, columns=sas_short_columns, show='headings', height=15)
        
        # SAS Short kolon başlıkları
        for col in sas_short_columns:
            self.sas_short_tree.heading(col, text=col)
            if col in ['Grup', 'Sembol']:
                self.sas_short_tree.column(col, width=120 if col == 'Grup' else 100)
            elif 'skor' in col:
                self.sas_short_tree.column(col, width=120)
            else:
                self.sas_short_tree.column(col, width=80)
        
        sas_short_scrollbar = ttk.Scrollbar(sas_short_frame, orient='vertical', command=self.sas_short_tree.yview)
        self.sas_short_tree.configure(yscrollcommand=sas_short_scrollbar.set)
        self.sas_short_tree.pack(side='left', fill='both', expand=True)
        sas_short_scrollbar.pack(side='right', fill='y')
        
        # 4. SFS Short tab (Final_SFS_skor kullanarak Short seçimi)
        sfs_short_frame = ttk.Frame(notebook)
        notebook.add(sfs_short_frame, text="SFS Short")
        
        sfs_short_columns = ('Grup', 'Sembol', 'Final_SFS_skor', 'Final_FB_skor', 'SMI', 'MAXALW', 'Hesaplanan Lot')
        self.sfs_short_tree = ttk.Treeview(sfs_short_frame, columns=sfs_short_columns, show='headings', height=15)
        
        # SFS Short kolon başlıkları
        for col in sfs_short_columns:
            self.sfs_short_tree.heading(col, text=col)
            if col in ['Grup', 'Sembol']:
                self.sfs_short_tree.column(col, width=120 if col == 'Grup' else 100)
            elif 'skor' in col:
                self.sfs_short_tree.column(col, width=120)
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
        """Hammer hesabından mevcut pozisyon lotunu al"""
        try:
            # Parent'tan hammer client'ı al
            if hasattr(self.parent, 'hammer') and self.parent.hammer:
                hammer_client = self.parent.hammer
                
                # Pozisyonları al
                positions = hammer_client.get_positions_direct()
                if positions:
                    # Symbol'e göre pozisyon ara
                    for pos in positions:
                        if pos.get('symbol') == symbol:
                            qty = pos.get('qty', 0)
                            # Pozitif qty = long pozisyon, negatif qty = short pozisyon
                            return abs(qty)  # Mutlak değer döndür
            
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
            # exposureadjuster.csv dosyasından ağırlıkları oku
            # Mevcut çalışma dizininde ara (en basit çözüm)
            csv_path = 'exposureadjuster.csv'
            if not os.path.exists(csv_path):
                messagebox.showerror("Hata", f"exposureadjuster.csv dosyası bulunamadı!\nAranan yol: {os.path.abspath(csv_path)}\nÖnce Port Adjuster'da ayarları kaydedin.")
                return
            
            df = pd.read_csv(csv_path)
            
            # Grup ağırlıklarını al - Long ve Short Groups'ları ayrı ayrı al
            self.long_group_weights = {}
            self.short_group_weights = {}
            long_total_weight = 0
            short_total_weight = 0
            
            # Long Groups bölümünü bul
            long_groups_section = False
            short_groups_section = False
            
            for _, row in df.iterrows():
                setting = row['Setting']
                value = row['Value']
                
                if setting == 'Long Groups':
                    long_groups_section = True
                    short_groups_section = False
                    continue
                elif setting == 'Short Groups':
                    long_groups_section = False
                    short_groups_section = True
                    continue
                elif long_groups_section and '%' in str(value):
                    try:
                        group = setting
                        weight = float(str(value).replace('%', ''))
                        self.long_group_weights[group] = weight
                        long_total_weight += weight
                    except:
                        continue
                elif short_groups_section and '%' in str(value):
                    try:
                        group = setting
                        weight = float(str(value).replace('%', ''))
                        self.short_group_weights[group] = weight
                        short_total_weight += weight
                    except:
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
            
            # Long/Short lot haklarını hesapla
            total_lots = int(total_exposure / avg_pref_price)
            self.long_lot_rights = int(total_lots * (long_ratio / 100))
            self.short_lot_rights = int(total_lots * (short_ratio / 100))
            
            print(f"✅ Exposure değerleri yüklendi:")
            print(f"   Toplam Exposure: ${total_exposure:,.0f}")
            print(f"   Ortalama Fiyat: ${avg_pref_price:.2f}")
            print(f"   Toplam Lot Hakkı: {total_lots:,}")
            print(f"   Long Lot Hakkı: {self.long_lot_rights:,} ({long_ratio}%)")
            print(f"   Short Lot Hakkı: {self.short_lot_rights:,} ({short_ratio}%)")
            
            # Tabloyu güncelle
            self.update_weights_table()
            
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
            
            messagebox.showinfo("Başarılı", f"Grup ağırlıkları yüklendi!\nLong ağırlık: {long_total_weight}%\nShort ağırlık: {short_total_weight}%\nLong lot hakkı: {self.long_lot_rights:,}\nShort lot hakkı: {self.short_lot_rights:,}")
            
        except Exception as e:
            messagebox.showerror("Hata", f"Grup ağırlıkları yüklenirken hata: {e}")
    
    def update_weights_table(self):
        """Ağırlıklar tablosunu güncelle"""
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
        
        # Toplam lot hakkını güncelle
        total_lot = long_total + short_total
        self.total_lot_label.config(text=f"Long: {long_total:,} | Short: {short_total:,}")
    
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
                    print(f"      📊 {symbol}: {score_type}={live_score:.4f}")
            
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
        TUMCSV kurallarını uygula - Her kümeyi ntumcsvport.py mantığıyla işle
        """
        try:
            print("🚀 TUMCSV AYARLAMASI BAŞLIYOR...")
            print("=" * 80)
            
            # Tüm ssfinek dosyalarını bul (Long ve Short grupları birleştir)
            ssfinek_files = []
            all_groups = list(self.long_group_weights.keys()) + list(self.short_group_weights.keys())
            
            print(f"🔍 Aranan gruplar: {all_groups}")
            print(f"🔍 Long grup ağırlıkları: {self.long_group_weights}")
            print(f"🔍 Short grup ağırlıkları: {self.short_group_weights}")
            
            for group in all_groups:
                # Long veya Short'tan hangisinde varsa o yüzdeyi al
                long_weight = self.long_group_weights.get(group, 0)
                short_weight = self.short_group_weights.get(group, 0)
                total_weight = long_weight + short_weight
                
                print(f"🔍 {group}: Long={long_weight}%, Short={short_weight}%, Toplam={total_weight}%")
                
                if total_weight > 0:  # Sadece pozitif yüzdesi olan gruplar
                    file_name = f"ssfinek{group.lower()}.csv"
                    print(f"🔍 {group} için dosya aranıyor: {file_name}")
                    
                    if os.path.exists(file_name):
                        ssfinek_files.append((group, file_name))
                        print(f"✅ {file_name} bulundu")
                    else:
                        print(f"⚠️ {file_name} bulunamadı, {group} grubu atlanıyor")
                else:
                    print(f"⚠️ {group}: Ağırlık 0%, atlanıyor")
            
            print(f"📁 İşlenecek dosyalar: {len(ssfinek_files)} adet")
            if len(ssfinek_files) == 0:
                print(f"❌ Hiç dosya bulunamadı! Çalışma dizini: {os.getcwd()}")
                print(f"❌ Mevcut dosyalar: {[f for f in os.listdir('.') if f.startswith('ssfinek')]}")
                return
            
            all_long_stocks = []
            all_short_stocks = []
            
            for group, file_name in ssfinek_files:
                print(f"\n📊 İşleniyor: {group} ({file_name})")
                
                try:
                    # Dosyayı oku
                    df = pd.read_csv(file_name)
                    print(f"   ✅ Dosya okundu: {len(df)} satır")
                    
                    # DEBUG: Mevcut kolonları göster
                    print(f"   🔍 Mevcut kolonlar: {list(df.columns)}")
                    
                    if len(df) == 0:
                        print(f"   ⚠️ Dosya boş, atlanıyor")
                        continue
                    
                    # Gerekli kolonları kontrol et
                    required_columns = ['PREF IBKR', 'FINAL_THG', 'SHORT_FINAL', 'CMON']
                    missing_columns = [col for col in required_columns if col not in df.columns]
                    
                    if missing_columns:
                        print(f"   ❌ Eksik kolonlar: {missing_columns}")
                        print(f"   💡 Bu kolonlar için önce uygulamada skorları hesaplamanız gerekiyor!")
                        print(f"   💡 Herhangi bir grup butonuna tıklayıp 'Skorları Hesapla' yapın")
                        continue
                    
                    # Final_FB_skor ve Final_SFS_skor kolonlarını STOCK DATA MANAGER'dan al!
                    print(f"   🔄 Final_FB_skor ve Final_SFS_skor kolonları STOCK DATA MANAGER'dan alınıyor...")
                    print(f"   🚀 Her PREF IBKR için Stock Data Manager'dan direkt veriler çekiliyor!")
                    print(f"   📊 Ana sayfada hesaplanan skorlar kullanılıyor!")
                    
                    # YENİ SİSTEM: Mini450 Snapshot ile 4 farklı skor türü için seçim yap
                    print(f"   🔍 Mini450 Snapshot Sistemi ile {group} grubu işleniyor...")
                    
                    # 4 farklı skor türü için seçim yap
                    bb_long_stocks = self.select_stocks_by_score_type(file_name, df, 'Final_BB_skor', 'LONG')
                    fb_long_stocks = self.select_stocks_by_score_type(file_name, df, 'Final_FB_skor', 'LONG')
                    sas_short_stocks = self.select_stocks_by_score_type(file_name, df, 'Final_SAS_skor', 'SHORT')
                    sfs_short_stocks = self.select_stocks_by_score_type(file_name, df, 'Final_SFS_skor', 'SHORT')
                    
                    print(f"   📊 {group} Skor türlerine göre seçilen hisseler:")
                    print(f"      🔵 BB Long: {len(bb_long_stocks)} hisse")
                    print(f"      🟢 FB Long: {len(fb_long_stocks)} hisse") 
                    print(f"      🟠 SAS Short: {len(sas_short_stocks)} hisse")
                    print(f"      🔴 SFS Short: {len(sfs_short_stocks)} hisse")
                    
                    # Grupları birleştir (FB Long ve SFS Short varsayılan olarak)
                    group_long_stocks = fb_long_stocks  # FB Long varsayılan
                    group_short_stocks = sfs_short_stocks  # SFS Short varsayılan
                    
                    all_long_stocks.extend(group_long_stocks.to_dict('records') if len(group_long_stocks) > 0 else [])
                    all_short_stocks.extend(group_short_stocks.to_dict('records') if len(group_short_stocks) > 0 else [])
                    
                    print(f"   🟢 {group}: {len(group_long_stocks)} LONG, {len(group_short_stocks)} SHORT hisse seçildi")
                    
                    # YENİ SİSTEM TAMAMLANDI - Mini450 Snapshot ile seçim yapıldı
                    
                except Exception as e:
                    print(f"   ❌ {group} işlenirken hata: {e}")
                    continue
            
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
                
                # Başarılı mesajı göster
                messagebox.showinfo("Başarılı", f"TUMCSV ayarlaması tamamlandı!\nLONG: {len(all_long_stocks)} hisse\nSHORT: {len(all_short_stocks)} hisse")
                
            else:
                print(f"❌ Hiç hisse seçilemedi!")
                messagebox.showwarning("Uyarı", "Hiç hisse seçilemedi!")
                
        except Exception as e:
            print(f"❌ TUMCSV ayarlaması hatası: {e}")
            messagebox.showerror("Hata", f"TUMCSV ayarlaması hatası: {e}")
    
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
                                print(f"      ✅ {symbol}: Mini450'den {score_type}={float(score_value):.4f}")
                                return float(score_value)
                        else:
                            print(f"      ⚠️ {symbol}: Mini450'de {score_type} kolonu bulunamadı")
                    else:
                        print(f"      ⚠️ {symbol}: Mini450'de PREF IBKR eşleşmesi bulunamadı")
                        
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
    
    def display_tumcsv_results_by_score_type(self, all_long_stocks, all_short_stocks):
        """4 farklı sekme için hisseleri skor türüne göre ayır ve göster"""
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
            
            print(f"   🎯 4 sekmeye {len(all_stocks)} hisse dağıtılıyor...")
            
            for stock in all_stocks:
                try:
                    symbol = stock.get('PREF IBKR', 'N/A')
                    group = stock.get('CGRUP', 'N/A')
                    
                    # 4 farklı skor türünü al
                    final_bb_skor = self.get_score_for_symbol(symbol, 'Final_BB_skor', stock)
                    final_fb_skor = self.get_score_for_symbol(symbol, 'Final_FB_skor', stock) 
                    final_sas_skor = self.get_score_for_symbol(symbol, 'Final_SAS_skor', stock)
                    final_sfs_skor = self.get_score_for_symbol(symbol, 'Final_SFS_skor', stock)
                    
                    # SMI ve MAXALW değerlerini al
                    smi = stock.get('SMI', 'N/A')
                    maxalw = stock.get('MAXALW', 'N/A')
                    
                    # Hesaplanan lot (şimdilik 100 varsayılan)
                    calculated_lots = 100
                    
                    # Her sekmede gösterilecek veriler
                    bb_long_values = (group, symbol, final_bb_skor, final_sfs_skor, smi, maxalw, calculated_lots)
                    fb_long_values = (group, symbol, final_fb_skor, final_sfs_skor, smi, maxalw, calculated_lots) 
                    sas_short_values = (group, symbol, final_sas_skor, final_fb_skor, smi, maxalw, calculated_lots)
                    sfs_short_values = (group, symbol, final_sfs_skor, final_fb_skor, smi, maxalw, calculated_lots)
                    
                    # Her sekmede göster
                    self.bb_long_tree.insert('', 'end', values=bb_long_values)
                    self.fb_long_tree.insert('', 'end', values=fb_long_values)
                    self.sas_short_tree.insert('', 'end', values=sas_short_values)
                    self.sfs_short_tree.insert('', 'end', values=sfs_short_values)
                    
                except Exception as e:
                    print(f"   ❌ {stock.get('PREF IBKR', 'N/A')} gösterim hatası: {e}")
            
            print(f"   ✅ 4 sekme güncellendi:")
            print(f"   🔵 BB Long: {len(all_stocks)} hisse")
            print(f"   🟢 FB Long: {len(all_stocks)} hisse")
            print(f"   🟠 SAS Short: {len(all_stocks)} hisse")
            print(f"   🔴 SFS Short: {len(all_stocks)} hisse")
            
        except Exception as e:
            print(f"❌ 4 sekme sonuç gösterim hatası: {e}")
                                                final_fb_skor = float(fb_value)
                                                print(f"      ✅ {symbol}: Ana sayfadan Final_FB_skor={final_fb_skor:.2f}")
                                        
                                        # Final_SFS_skor için de aynı mantık
                                        if 'Final_SFS_skor' in parent_df.columns:
                                            sfs_value = symbol_row['Final_SFS_skor'].iloc[0]
                                            if pd.notna(sfs_value) and sfs_value != 'N/A':
                                                final_sfs_skor = float(sfs_value)
                                                print(f"      ✅ {symbol}: Ana sayfadan Final_SFS_skor={final_sfs_skor:.2f}")
                                        
                                        # DataFrame'de yoksa hesapla - Top Ten Bid Buy mantığıyla
                                        if (final_fb_skor == final_thg or final_sfs_skor == short_final) and hasattr(self.parent.main_window, 'calculate_scores') and hasattr(self.parent.main_window, 'hammer'):
                                            # Market data al
                                            market_data = self.parent.main_window.hammer.get_market_data(symbol)
                                            if market_data:
                                                bid_raw = float(market_data.get('bid', 0))
                                                ask_raw = float(market_data.get('ask', 0))
                                                last_raw = float(market_data.get('last', 0))
                                                prev_close = float(market_data.get('prevClose', 0))
                                                
                                                # Benchmark değişimini hesapla
                                                benchmark_chg = self.parent.main_window.get_benchmark_change_for_ticker(symbol)
                                                
                                                # Skorları hesapla
                                                scores = self.parent.main_window.calculate_scores(symbol, symbol_row.iloc[0], bid_raw, ask_raw, last_raw, prev_close, benchmark_chg)
                                                
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
                                print(f"      ⚠️ {symbol}: Stock Data Manager yok, CSV değerleri kullanılıyor")
                                print(f"        CSV değerleri: Final_FB_skor={final_thg:.2f}, Final_SFS_skor={short_final:.2f}")
                            
                            # DataFrame'e ekle
                            df.at[idx, 'Final_FB_skor'] = round(final_fb_skor, 2)
                            df.at[idx, 'Final_SFS_skor'] = round(final_sfs_skor, 2)
                            
                        except Exception as e:
                            print(f"      ⚠️ {row.get('PREF IBKR', 'N/A')} skor alınamadı: {e}")
                            df.at[idx, 'Final_FB_skor'] = 0
                            df.at[idx, 'Final_SFS_skor'] = 0
                    
                    print(f"   ✅ Final_FB_skor ve Final_SFS_skor kolonları STOCK DATA MANAGER'dan alındı!")
                    print(f"   🚀 Ana sayfada hesaplanan skorlar kullanıldı!")
                    print(f"   📊 CSV'den FINAL_THG ve SHORT_FINAL değerleri fallback olarak kullanıldı!")
                    
                    # DEBUG: Alınan skorları göster
                    print(f"   🔍 Stock Data Manager'dan alınan skorları göster:")
                    sample_rows = df.head(3)
                    for _, row in sample_rows.iterrows():
                        print(f"      {row.get('PREF IBKR', 'N/A')}: Final_FB_skor={row.get('Final_FB_skor', 'N/A')}, Final_SFS_skor={row.get('Final_SFS_skor', 'N/A')}")
                    
                    # 4 farklı skor türüne göre hisseleri seç
                    bb_long_stocks = self.select_stocks_by_score_type(file_name, df, 'Final_BB_skor', 'LONG')
                    fb_long_stocks = self.select_stocks_by_score_type(file_name, df, 'Final_FB_skor', 'LONG')
                    sas_short_stocks = self.select_stocks_by_score_type(file_name, df, 'Final_SAS_skor', 'SHORT')
                    sfs_short_stocks = self.select_stocks_by_score_type(file_name, df, 'Final_SFS_skor', 'SHORT')
                    
                    print(f"   📊 Skor türlerine göre seçilen hisseler:")
                    print(f"      🔵 BB Long: {len(bb_long_stocks)} hisse")
                    print(f"      🟢 FB Long: {len(fb_long_stocks)} hisse")
                    print(f"      🟠 SAS Short: {len(sas_short_stocks)} hisse")
                    print(f"      🔴 SFS Short: {len(sfs_short_stocks)} hisse")
                    
                    # Geriye uyumluluk için FB Long ve SFS Short'u kullan
                    long_stocks = fb_long_stocks
                    short_stocks = sfs_short_stocks
                    
                    # Seçilen hisseleri listeye ekle
                    for _, row in long_stocks.iterrows():
                        stock_info = {
                            'GRUP': group,
                            'DOSYA': file_name,
                            'PREF_IBKR': row['PREF IBKR'],
                            'Final_FB_skor': row['Final_FB_skor'],
                            'Final_SFS_skor': row['Final_SFS_skor'],
                            'SMI': row.get('SMI', 'N/A'),
                            'CGRUP': row.get('CGRUP', 'N/A'),
                            'CMON': row.get('CMON', 'N/A'),
                            'AVG_ADV': row.get('AVG_ADV', 0),
                            'TİP': 'LONG',
                            'GRUP_YUZDESI': self.long_group_weights.get(group, 0)
                        }
                        all_long_stocks.append(stock_info)
                    
                    for _, row in short_stocks.iterrows():
                        stock_info = {
                            'GRUP': group,
                            'DOSYA': file_name,
                            'PREF_IBKR': row['PREF IBKR'],
                            'Final_FB_skor': row['Final_FB_skor'],
                            'Final_SFS_skor': row['Final_SFS_skor'],
                            'SMI': row.get('SMI', 'N/A'),
                            'CGRUP': row.get('CGRUP', 'N/A'),
                            'CMON': row.get('CMON', 'N/A'),
                            'AVG_ADV': row.get('AVG_ADV', 0),
                            'TİP': 'SHORT',
                            'GRUP_YUZDESI': self.short_group_weights.get(group, 0)
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
                
                # Sonuçları tablolarda göster - 4 ayrı sekme için
                self.display_tumcsv_results_by_score_type(all_long_stocks, all_short_stocks)
                
                # Sonuçları CSV'ye kaydet
                if all_long_stocks:
                    long_df = pd.DataFrame(all_long_stocks)
                    long_df.to_csv('final_fb_sfs_tumcsv_long_stocks.csv', index=False)
                    print(f"   💾 LONG hisseler: final_fb_sfs_tumcsv_long_stocks.csv")
                
                if all_short_stocks:
                    short_df = pd.DataFrame(all_short_stocks)
                    short_df.to_csv('final_fb_sfs_tumcsv_short_stocks.csv', index=False)
                    print(f"   💾 SHORT hisseler: final_fb_sfs_tumcsv_short_stocks.csv")
                
                messagebox.showinfo("Başarılı", f"TUMCSV ayarlaması tamamlandı!\nLONG: {len(all_long_stocks)} hisse\nSHORT: {len(all_short_stocks)} hisse")
                
            else:
                print(f"\n❌ Hiç hisse seçilemedi!")
                messagebox.showwarning("Uyarı", "Hiç hisse seçilemedi!")
                
        except Exception as e:
            print(f"❌ TUMCSV ayarlaması hatası: {e}")
            messagebox.showerror("Hata", f"TUMCSV ayarlaması hatası: {e}")
    
    def get_score_for_symbol(self, symbol, score_type, stock_data):
        """Sembol için belirtilen skor türünü al - Mini450'deki ana DataFrame'den eşleştir"""
        try:
            # Önce ana sayfadaki DataFrame'den (mini450'den) çek
            if self.main_window and hasattr(self.main_window, 'df') and not self.main_window.df.empty:
                try:
                    # PREF IBKR kolonunda symbol'ü ara
                    symbol_row = self.main_window.df[self.main_window.df['PREF IBKR'] == symbol]
                    
                    if not symbol_row.empty:
                        # İlgili skor kolonunu kontrol et
                        if score_type in self.main_window.df.columns:
                            score_value = symbol_row[score_type].iloc[0]
                            if pd.notna(score_value) and score_value != 'N/A':
                                print(f"      ✅ {symbol}: Mini450'den {score_type}={float(score_value):.4f}")
                                return float(score_value)
                            else:
                                print(f"      ⚠️ {symbol}: Mini450'de {score_type} kolonu boş/N/A")
                        else:
                            print(f"      ⚠️ {symbol}: Mini450'de {score_type} kolonu bulunamadı")
                    else:
                        print(f"      ⚠️ {symbol}: Mini450'de PREF IBKR eşleşmesi bulunamadı")
                        
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
    
    def display_tumcsv_results_by_score_type(self, all_long_stocks, all_short_stocks):
        """4 farklı sekme için hisseleri skor türüne göre ayır ve göster"""
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
            
            # Her hisse için 4 farklı skor türünü hesapla ve ilgili sekmelere ekle
            all_stocks = all_long_stocks + all_short_stocks
            
            for stock in all_stocks:
                symbol = stock['PREF_IBKR']
                group = stock['GRUP']
                
                # Tüm skor türlerini al
                bb_score = self.get_score_for_symbol(symbol, 'Final_BB_skor', stock)
                fb_score = self.get_score_for_symbol(symbol, 'Final_FB_skor', stock)
                sas_score = self.get_score_for_symbol(symbol, 'Final_SAS_skor', stock)
                sfs_score = self.get_score_for_symbol(symbol, 'Final_SFS_skor', stock)
                
                # MAXALW hesapla
                avg_adv = stock.get('AVG_ADV', 0)
                if avg_adv > 0:
                    maxalw = round(avg_adv / 10, 0)
                else:
                    maxalw = 'N/A'
                
                # Lot bilgileri (şimdilik basit)
                calculated_lots = 100  # Örnek değer
                
                # Skorları formatla
                bb_display = f"{bb_score:.4f}" if isinstance(bb_score, (int, float)) else bb_score
                fb_display = f"{fb_score:.4f}" if isinstance(fb_score, (int, float)) else fb_score
                sas_display = f"{sas_score:.4f}" if isinstance(sas_score, (int, float)) else sas_score
                sfs_display = f"{sfs_score:.4f}" if isinstance(sfs_score, (int, float)) else sfs_score
                maxalw_display = f"{maxalw:.0f}" if isinstance(maxalw, (int, float)) else maxalw
                
                # Her sekmeye ekle (farklı ana skorlarla)
                # BB Long - Final_BB_skor ana kolon
                self.bb_long_tree.insert('', 'end', values=(
                    group, symbol, bb_display, sfs_display,
                    stock.get('SMI', 'N/A'), maxalw_display, f"{calculated_lots:,}"
                ))
                
                # FB Long - Final_FB_skor ana kolon
                self.fb_long_tree.insert('', 'end', values=(
                    group, symbol, fb_display, sfs_display,
                    stock.get('SMI', 'N/A'), maxalw_display, f"{calculated_lots:,}"
                ))
                
                # SAS Short - Final_SAS_skor ana kolon
                self.sas_short_tree.insert('', 'end', values=(
                    group, symbol, sas_display, fb_display,
                    stock.get('SMI', 'N/A'), maxalw_display, f"{calculated_lots:,}"
                ))
                
                # SFS Short - Final_SFS_skor ana kolon
                self.sfs_short_tree.insert('', 'end', values=(
                    group, symbol, sfs_display, fb_display,
                    stock.get('SMI', 'N/A'), maxalw_display, f"{calculated_lots:,}"
                ))
            
            print(f"✅ 4 sekme için sonuçlar gösterildi:")
            print(f"   🔵 BB Long: {len(all_stocks)} hisse")
            print(f"   🟢 FB Long: {len(all_stocks)} hisse")
            print(f"   🟠 SAS Short: {len(all_stocks)} hisse")
            print(f"   🔴 SFS Short: {len(all_stocks)} hisse")
            
        except Exception as e:
            print(f"❌ 4 sekme sonuç gösterim hatası: {e}")

    def display_tumcsv_results(self, long_stocks, short_stocks):
        """TUMCSV sonuçlarını 4 ayrı sekmede göster"""
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
            
            # Long hisseleri ekle - ntumcsvport.py mantığı ile lot dağılımı
            if long_stocks:
                # Duplicate kontrolü - her hisseyi sadece bir kez ekle
                seen_symbols = set()
                unique_long_stocks = []
                
                for stock in long_stocks:
                    symbol = stock['PREF_IBKR']
                    if symbol not in seen_symbols:
                        seen_symbols.add(symbol)
                        unique_long_stocks.append(stock)
                    else:
                        print(f"      ⚠️ Duplicate hisse atlandı: {symbol}")
                
                print(f"      🟢 Duplicate kontrolü: {len(long_stocks)} → {len(unique_long_stocks)} unique hisse")
                
                long_lots = self.calculate_group_lot_distribution_for_tumcsv(unique_long_stocks, 'LONG')
                
                for stock in unique_long_stocks:
                    group = stock['GRUP']
                    symbol = stock['PREF_IBKR']
                    
                    # Stock Data Manager'dan Final_FB_skor ve Final_SFS_skor verilerini al
                    final_fb_skor = 'N/A'
                    final_sfs_skor = 'N/A'
                    
                    if self.stock_data_manager:
                        try:
                            # Final_FB_skor verisini al
                            fb_data = self.stock_data_manager.get_stock_data(symbol, 'Final_FB_skor')
                            if fb_data is not None:
                                final_fb_skor = float(fb_data)
                            
                            # Final_SFS_skor verisini al
                            sfs_data = self.stock_data_manager.get_stock_data(symbol, 'Final_SFS_skor')
                            if sfs_data is not None:
                                final_sfs_skor = float(sfs_data)
                                
                        except Exception as e:
                            print(f"[3. STEP] ⚠️ {symbol} için skor verisi alınamadı: {e}")
                    
                    # Eğer Stock Data Manager'dan veri alınamadıysa CSV'den al
                    if final_fb_skor == 'N/A':
                        final_fb_skor = stock.get('Final_FB_skor', 'N/A')
                    if final_sfs_skor == 'N/A':
                        final_sfs_skor = stock.get('Final_SFS_skor', 'N/A')
                    
                    # Bu hisse için hesaplanan lot
                    calculated_lots = long_lots.get(symbol, 0)
                    final_lots = calculated_lots
                    available_lots = final_lots
                    
                    # MAXALW hesapla (AVG_ADV / 10)
                    avg_adv = stock.get('AVG_ADV', 0)
                    if avg_adv > 0:
                        maxalw = round(avg_adv / 10, 0)
                    else:
                        maxalw = 'N/A'
                    
                    # Durum belirle
                    if calculated_lots == 0:
                        status = "Lot hakkı yok"
                    elif isinstance(maxalw, (int, float)) and calculated_lots > maxalw * 2:
                        status = "MAXALW limiti aşıldı"
                        final_lots = int(maxalw * 2)
                        available_lots = final_lots
                    else:
                        status = "Aktif"
                    
                    # Final_FB_skor ve Final_SFS_skor değerlerini formatla
                    fb_display = f"{final_fb_skor:.4f}" if isinstance(final_fb_skor, (int, float)) else final_fb_skor
                    sfs_display = f"{final_sfs_skor:.4f}" if isinstance(final_sfs_skor, (int, float)) else final_sfs_skor
                    
                    # Tüm skor türlerini al
                    final_bb_skor = self.get_score_for_symbol(symbol, 'Final_BB_skor', stock)
                    final_fb_skor = self.get_score_for_symbol(symbol, 'Final_FB_skor', stock)
                    final_sfs_skor = self.get_score_for_symbol(symbol, 'Final_SFS_skor', stock)
                    
                    # Skorları formatla
                    bb_display = f"{final_bb_skor:.4f}" if isinstance(final_bb_skor, (int, float)) else final_bb_skor
                    fb_display = f"{final_fb_skor:.4f}" if isinstance(final_fb_skor, (int, float)) else final_fb_skor
                    sfs_display = f"{final_sfs_skor:.4f}" if isinstance(final_sfs_skor, (int, float)) else final_sfs_skor
                    
                    # BB Long sekmesine ekle (Final_BB_skor kullanarak seçilmiş)
                    self.bb_long_tree.insert('', 'end', values=(
                        group, symbol, bb_display, sfs_display,
                        stock.get('SMI', 'N/A'),
                        f"{maxalw:.0f}" if isinstance(maxalw, (int, float)) else maxalw,
                        f"{calculated_lots:,}"
                    ))
                    
                    # FB Long sekmesine ekle (Final_FB_skor kullanarak seçilmiş)
                    self.fb_long_tree.insert('', 'end', values=(
                        group, symbol, fb_display, sfs_display,
                        stock.get('SMI', 'N/A'),
                        f"{maxalw:.0f}" if isinstance(maxalw, (int, float)) else maxalw,
                        f"{calculated_lots:,}"
                    ))
            
            # Short hisseleri ekle - ntumcsvport.py mantığı ile lot dağılımı
            if short_stocks:
                # Duplicate kontrolü - her hisseyi sadece bir kez ekle
                seen_symbols = set()
                unique_short_stocks = []
                
                for stock in short_stocks:
                    symbol = stock['PREF_IBKR']
                    if symbol not in seen_symbols:
                        seen_symbols.add(symbol)
                        unique_short_stocks.append(stock)
                    else:
                        print(f"      ⚠️ Duplicate hisse atlandı: {symbol}")
                
                print(f"      🔴 Duplicate kontrolü: {len(short_stocks)} → {len(unique_short_stocks)} unique hisse")
                
                short_lots = self.calculate_group_lot_distribution_for_tumcsv(unique_short_stocks, 'SHORT')
                
                for stock in unique_short_stocks:
                    group = stock['GRUP']
                    symbol = stock['PREF_IBKR']
                    
                    # Stock Data Manager'dan Final_FB_skor ve Final_SFS_skor verilerini al
                    final_fb_skor = 'N/A'
                    final_sfs_skor = 'N/A'
                    
                    if self.stock_data_manager:
                        try:
                            # Final_FB_skor verisini al
                            fb_data = self.stock_data_manager.get_stock_data(symbol, 'Final_FB_skor')
                            if fb_data is not None:
                                final_fb_skor = float(fb_data)
                            
                            # Final_SFS_skor verisini al
                            sfs_data = self.stock_data_manager.get_stock_data(symbol, 'Final_SFS_skor')
                            if sfs_data is not None:
                                final_sfs_skor = float(sfs_data)
                                
                        except Exception as e:
                            print(f"[3. STEP] ⚠️ {symbol} için skor verisi alınamadı: {e}")
                    
                    # Eğer Stock Data Manager'dan veri alınamadıysa CSV'den al
                    if final_fb_skor == 'N/A':
                        final_fb_skor = stock.get('Final_FB_skor', 'N/A')
                    if final_sfs_skor == 'N/A':
                        final_sfs_skor = stock.get('Final_SFS_skor', 'N/A')
                    
                    # Bu hisse için hesaplanan lot
                    calculated_lots = short_lots.get(symbol, 0)
                    final_lots = calculated_lots
                    available_lots = final_lots
                    
                    # MAXALW hesapla (AVG_ADV / 10)
                    avg_adv = stock.get('AVG_ADV', 0)
                    if avg_adv > 0:
                        maxalw = round(avg_adv / 10, 0)
                    else:
                        maxalw = 'N/A'
                    
                    # Durum belirle
                    if calculated_lots == 0:
                        status = "Lot hakkı yok"
                    elif isinstance(maxalw, (int, float)) and calculated_lots > maxalw * 2:
                        status = "MAXALW limiti aşıldı"
                        final_lots = int(maxalw * 2)
                        available_lots = final_lots
                    else:
                        status = "Aktif"
                    
                    # Tüm skor türlerini al
                    final_bb_skor = self.get_score_for_symbol(symbol, 'Final_BB_skor', stock)
                    final_fb_skor = self.get_score_for_symbol(symbol, 'Final_FB_skor', stock)
                    final_sas_skor = self.get_score_for_symbol(symbol, 'Final_SAS_skor', stock)
                    final_sfs_skor = self.get_score_for_symbol(symbol, 'Final_SFS_skor', stock)
                    
                    # Skorları formatla
                    bb_display = f"{final_bb_skor:.4f}" if isinstance(final_bb_skor, (int, float)) else final_bb_skor
                    fb_display = f"{final_fb_skor:.4f}" if isinstance(final_fb_skor, (int, float)) else final_fb_skor
                    sas_display = f"{final_sas_skor:.4f}" if isinstance(final_sas_skor, (int, float)) else final_sas_skor
                    sfs_display = f"{final_sfs_skor:.4f}" if isinstance(final_sfs_skor, (int, float)) else final_sfs_skor
                    
                    # SAS Short sekmesine ekle (Final_SAS_skor kullanarak seçilmiş)
                    self.sas_short_tree.insert('', 'end', values=(
                        group, symbol, sas_display, fb_display,
                        stock.get('SMI', 'N/A'),
                        f"{maxalw:.0f}" if isinstance(maxalw, (int, float)) else maxalw,
                        f"{calculated_lots:,}"
                    ))
                    
                    # SFS Short sekmesine ekle (Final_SFS_skor kullanarak seçilmiş)
                    self.sfs_short_tree.insert('', 'end', values=(
                        group, symbol, sfs_display, fb_display,
                        stock.get('SMI', 'N/A'),
                        f"{maxalw:.0f}" if isinstance(maxalw, (int, float)) else maxalw,
                        f"{calculated_lots:,}"
                    ))
            
            print(f"✅ TUMCSV sonuçları tablolarda gösterildi:")
            print(f"   🟢 LONG: {len(long_stocks)} hisse")
            print(f"   🔴 SHORT: {len(short_stocks)} hisse")
            
        except Exception as e:
            print(f"❌ TUMCSV sonuçları gösterilirken hata: {e}")
    
    def calculate_group_lot_distribution_for_tumcsv(self, stocks, direction):
        """TUMCSV mantığı ile lot dağılımı hesapla"""
        try:
            if not stocks:
                return {}
            
            # Grup bazında lot haklarını al
            group_lots = {}
            for stock in stocks:
                group = stock['GRUP']
                if group not in group_lots:
                    # Long veya Short grubundan lot hakkını al
                    if direction == 'LONG':
                        group_weight = self.long_group_weights.get(group, 0)
                        total_lot_rights = self.long_lot_rights
                    else:  # SHORT
                        group_weight = self.short_group_weights.get(group, 0)
                        total_lot_rights = self.short_lot_rights
                    
                    # Lot hakkını hesapla
                    if group_weight > 0 and total_lot_rights > 0:
                        lot_rights = int((group_weight / 100) * total_lot_rights)
                        group_lots[group] = lot_rights
                        print(f"   📊 {group}: {group_weight}% × {total_lot_rights:,} = {lot_rights:,} lot")
                    else:
                        group_lots[group] = 0
                        print(f"   ⚠️ {group}: Lot hakkı yok (weight: {group_weight}%, total: {total_lot_rights:,})")
            
            # Her grup için lot dağılımı yap
            result_lots = {}
            
            for group, total_lot_rights in group_lots.items():
                if total_lot_rights <= 0:
                    continue
                
                # Bu gruptaki hisseleri al
                group_stocks = [s for s in stocks if s['GRUP'] == group]
                
                if not group_stocks:
                    continue
                
                # Final_FB_skor veya Final_SFS_skor'a göre sırala
                if direction == 'LONG':
                    group_stocks.sort(key=lambda x: x.get('Final_FB_skor', 0), reverse=True)
                    score_key = 'Final_FB_skor'
                    print(f"      🟢 {group}: Final_FB_skor'a göre sıralama")
                else:  # SHORT
                    group_stocks.sort(key=lambda x: x.get('Final_SFS_skor', 0), reverse=False)  # En düşük en iyi
                    score_key = 'Final_SFS_skor'
                    print(f"      🔴 {group}: Final_SFS_skor'a göre sıralama (en düşük en iyi)")
                
                # Alpha tabanlı lot dağılımı
                alpha = float(self.alpha_var.get())
                min_lot_thresh = 100
                
                # Skorları normalize et
                scores = [stock.get(score_key, 0) for stock in group_stocks]
                if not scores or max(scores) == 0:
                    continue
                
                max_score = max(scores)
                normalized_scores = [(score / max_score) ** alpha for score in scores]
                
                # Toplam normalize skor
                total_normalized = sum(normalized_scores)
                
                if total_normalized == 0:
                    continue
                
                # Lot dağılımı
                for i, stock in enumerate(group_stocks):
                    symbol = stock['PREF_IBKR']
                    
                    # Bu hisse için lot hesapla
                    if total_normalized > 0:
                        lot_ratio = normalized_scores[i] / total_normalized
                        calculated_lots = int(total_lot_rights * lot_ratio)
                        
                        # Minimum lot kontrolü
                        if calculated_lots < min_lot_thresh:
                            calculated_lots = 0
                        
                        # 100'e yuvarla
                        calculated_lots = round(calculated_lots / 100) * 100
                        
                        result_lots[symbol] = calculated_lots
                    else:
                        result_lots[symbol] = 0
            
            print(f"✅ {direction} lot dağılımı hesaplandı:")
            for symbol, lots in result_lots.items():
                if lots > 0:
                    print(f"   {symbol}: {lots:,} lot")
            
            return result_lots
            
        except Exception as e:
            print(f"❌ Lot dağılımı hesaplanırken hata: {e}")
            return {}
    
    def calculate_final_fb_with_csv_and_live(self, final_thg, bid, ask, last_price):
        """
        CSV'den gelen FINAL_THG + Hammer Pro'dan gelen live bid/ask verilerle Final_FB_skor hesapla
        Ana sayfadaki hesaplama mantığını kullanır
        """
        try:
            # CSV'den gelen FINAL_THG değerini kullan
            print(f"          📊 CSV'den FINAL_THG: {final_thg:.2f}")
            
            # Hammer Pro'dan gelen live verileri kullan
            bid = float(bid) if bid > 0 else 0
            ask = float(ask) if ask > 0 else 0
            last_price = float(last_price) if last_price > 0 else 0
            
            # Spread hesapla
            spread = ask - bid if ask > 0 and bid > 0 else 0
            
            # Passive fiyatlar hesapla (ana sayfadaki formüllerle)
            pf_bid_buy = bid + (spread * 0.15) if bid > 0 else 0
            pf_front_buy = last_price + 0.01 if last_price > 0 else 0
            pf_ask_buy = ask + 0.01 if ask > 0 else 0
            
            # prev_close için varsayılan değer (ana sayfadaki mantıkla)
            prev_close = last_price  # Basit yaklaşım
            
            # Değişimler hesapla
            pf_bid_buy_chg = pf_bid_buy - prev_close if prev_close > 0 else 0
            pf_front_buy_chg = pf_front_buy - prev_close if prev_close > 0 else 0
            pf_ask_buy_chg = pf_ask_buy - prev_close if prev_close > 0 else 0
            
            # Benchmark değişimi için varsayılan değer (ana sayfadaki mantıkla)
            benchmark_chg = 0.0  # Basit yaklaşım
            
            # Ucuzluk skorları
            bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
            front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
            ask_buy_ucuzluk = pf_ask_buy_chg - benchmark_chg
            
            # Ana sayfadaki formülle Final_FB_skor hesapla
            # Final_FB_skor = FINAL_THG - 800 * front_buy_ucuzluk
            final_fb_skor = final_thg - 800 * front_buy_ucuzluk
            
            print(f"          🔄 Final_FB_skor hesaplama:")
            print(f"            Spread: {spread:.4f}")
            print(f"            Pf_front_buy: {pf_front_buy:.4f}")
            print(f"            Front_buy_ucuzluk: {front_buy_ucuzluk:.4f}")
            print(f"            Formül: {final_thg:.2f} - 800 × {front_buy_ucuzluk:.4f} = {final_fb_skor:.2f}")
            
            return final_fb_skor
            
        except Exception as e:
            print(f"          ❌ Final_FB_skor hesaplanamadı: {e}")
            return final_thg  # Hata durumunda CSV değerini döndür
    
    def calculate_final_sfs_with_csv_and_live(self, short_final, bid, ask, last_price):
        """
        CSV'den gelen SHORT_FINAL + Hammer Pro'dan gelen live bid/ask verilerle Final_SFS_skor hesapla
        Ana sayfadaki hesaplama mantığını kullanır
        """
        try:
            # CSV'den gelen SHORT_FINAL değerini kullan
            print(f"          📊 CSV'den SHORT_FINAL: {short_final:.2f}")
            
            # Hammer Pro'dan gelen live verileri kullan
            bid = float(bid) if bid > 0 else 0
            ask = float(ask) if ask > 0 else 0
            last_price = float(last_price) if last_price > 0 else 0
            
            # Spread hesapla
            spread = ask - bid if ask > 0 and bid > 0 else 0
            
            # Passive fiyatlar hesapla (ana sayfadaki formüllerle)
            pf_ask_sell = ask - (spread * 0.15) if ask > 0 else 0
            pf_front_sell = last_price - 0.01 if last_price > 0 else 0
            pf_bid_sell = bid - 0.01 if bid > 0 else 0
            
            # prev_close için varsayılan değer (ana sayfadaki mantıkla)
            prev_close = last_price  # Basit yaklaşım
            
            # Değişimler hesapla
            pf_ask_sell_chg = pf_ask_sell - prev_close if prev_close > 0 else 0
            pf_front_sell_chg = pf_front_sell - prev_close if prev_close > 0 else 0
            pf_bid_sell_chg = pf_bid_sell - prev_close if prev_close > 0 else 0
            
            # Benchmark değişimi için varsayılan değer (ana sayfadaki mantıkla)
            benchmark_chg = 0.0  # Basit yaklaşım
            
            # Pahalılık skorları
            ask_sell_pahalilik = pf_ask_sell_chg - benchmark_chg
            front_sell_pahalilik = pf_front_sell_chg - benchmark_chg
            bid_sell_pahalilik = pf_bid_sell_chg - benchmark_chg
            
            # Ana sayfadaki formülle Final_SFS_skor hesapla
            # Final_SFS_skor = SHORT_FINAL - 800 * front_sell_pahalilik
            final_sfs_skor = short_final - 800 * front_sell_pahalilik
            
            print(f"          🔄 Final_SFS_skor hesaplama:")
            print(f"            Spread: {spread:.4f}")
            print(f"            Pf_front_sell: {pf_front_sell:.4f}")
            print(f"            Front_sell_pahalilik: {front_sell_pahalilik:.4f}")
            print(f"            Formül: {short_final:.2f} - 800 × {front_sell_pahalilik:.4f} = {final_sfs_skor:.2f}")
            
            return final_sfs_skor
            
        except Exception as e:
            print(f"          ❌ Final_SFS_skor hesaplanamadı: {e}")
            return short_final  # Hata durumunda CSV değerini döndür
