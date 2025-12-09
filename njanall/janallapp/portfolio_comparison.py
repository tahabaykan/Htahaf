"""
Portfolio Comparison - Mevcut pozisyonları ideal portföy dağılımıyla karşılaştırma

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
import numpy as np

class PortfolioComparisonWindow:
    def __init__(self, parent):
        self.parent = parent
        
        # Ana pencere
        self.win = tk.Toplevel(parent)
        self.win.title("Portfolio Comparison - Mevcut vs İdeal Dağılım")
        self.win.geometry("1400x800")
        self.win.transient(parent)
        self.win.grab_set()
        
        # Veri saklama
        self.ideal_portfolio = {}
        self.current_positions = []
        self.current_group_distribution = {}
        
        # UI oluştur
        self.setup_ui()
        
        # Verileri yükle
        self.load_data()
    
    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        # Üst panel - Butonlar
        top_frame = ttk.Frame(self.win)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        self.btn_refresh = ttk.Button(top_frame, text="Yenile", 
                                     command=self.load_data, width=10)
        self.btn_refresh.pack(side='left', padx=2)
        
        self.btn_export = ttk.Button(top_frame, text="Excel'e Aktar", 
                                   command=self.export_to_excel, width=12)
        self.btn_export.pack(side='left', padx=2)
        
        # Bilgi etiketi
        self.lbl_info = ttk.Label(top_frame, text="Veriler yükleniyor...")
        self.lbl_info.pack(side='right', padx=5)
        
        # Sekme kontrolü
        self.setup_tabs()
    
    def setup_tabs(self):
        """Sekmeleri oluştur"""
        # Notebook (sekme kontrolü)
        self.notebook = ttk.Notebook(self.win)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Long sekmesi
        self.long_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.long_frame, text="📈 Long Pozisyonlar")
        
        # Short sekmesi
        self.short_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.short_frame, text="📉 Short Pozisyonlar")
        
        # Long sekmesi için tablo
        self.setup_long_table()
        
        # Short sekmesi için tablo
        self.setup_short_table()
        
        # Exposure bilgisi paneli
        self.setup_exposure_panel()
    
    def setup_long_table(self):
        """Long pozisyonlar tablosunu oluştur"""
        # Tablo frame
        table_frame = ttk.Frame(self.long_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Kolonlar
        columns = [
            'Grup', 'İdeal Lot', 'İdeal %', 'Mevcut Lot', 'Mevcut %', 
            'Lot Farkı', '% Farkı', 'Durum'
        ]
        
        # Treeview oluştur
        self.long_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=20)
        
        # Kolon başlıkları ve genişlikleri
        column_widths = {
            'Grup': 150,
            'İdeal Lot': 80,
            'İdeal %': 70,
            'Mevcut Lot': 80,
            'Mevcut %': 70,
            'Lot Farkı': 80,
            '% Farkı': 70,
            'Durum': 100
        }
        
        for col in columns:
            self.long_tree.heading(col, text=col)
            self.long_tree.column(col, width=column_widths.get(col, 100), anchor='center')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.long_tree.yview)
        self.long_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack
        self.long_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Sıralama bağla
        for col in columns:
            self.long_tree.heading(col, command=lambda c=col: self.sort_by_column(c, 'long'))
    
    def setup_short_table(self):
        """Short pozisyonlar tablosunu oluştur"""
        # Tablo frame
        table_frame = ttk.Frame(self.short_frame)
        table_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Kolonlar
        columns = [
            'Grup', 'İdeal Lot', 'İdeal %', 'Mevcut Lot', 'Mevcut %', 
            'Lot Farkı', '% Farkı', 'Durum'
        ]
        
        # Treeview oluştur
        self.short_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=20)
        
        # Kolon başlıkları ve genişlikleri
        column_widths = {
            'Grup': 150,
            'İdeal Lot': 80,
            'İdeal %': 70,
            'Mevcut Lot': 80,
            'Mevcut %': 70,
            'Lot Farkı': 80,
            '% Farkı': 70,
            'Durum': 100
        }
        
        for col in columns:
            self.short_tree.heading(col, text=col)
            self.short_tree.column(col, width=column_widths.get(col, 100), anchor='center')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.short_tree.yview)
        self.short_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack
        self.short_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Sıralama bağla
        for col in columns:
            self.short_tree.heading(col, command=lambda c=col: self.sort_by_column(c, 'short'))
    
    def setup_exposure_panel(self):
        """Exposure bilgisi panelini oluştur"""
        # Exposure paneli - alt kısımda
        exposure_frame = ttk.LabelFrame(self.win, text="📊 Exposure Karşılaştırması")
        exposure_frame.pack(fill='x', padx=5, pady=5)
        
        # Long exposure bilgisi
        long_frame = ttk.Frame(exposure_frame)
        long_frame.pack(fill='x', padx=5, pady=2)
        
        ttk.Label(long_frame, text="📈 Long Exposure:", font=('Arial', 10, 'bold')).pack(side='left')
        self.lbl_long_ideal = ttk.Label(long_frame, text="İdeal: $0", foreground='blue')
        self.lbl_long_ideal.pack(side='left', padx=10)
        self.lbl_long_current = ttk.Label(long_frame, text="Mevcut: $0", foreground='green')
        self.lbl_long_current.pack(side='left', padx=10)
        self.lbl_long_diff = ttk.Label(long_frame, text="Fark: $0", foreground='red')
        self.lbl_long_diff.pack(side='left', padx=10)
        
        # Short exposure bilgisi
        short_frame = ttk.Frame(exposure_frame)
        short_frame.pack(fill='x', padx=5, pady=2)
        
        ttk.Label(short_frame, text="📉 Short Exposure:", font=('Arial', 10, 'bold')).pack(side='left')
        self.lbl_short_ideal = ttk.Label(short_frame, text="İdeal: $0", foreground='blue')
        self.lbl_short_ideal.pack(side='left', padx=10)
        self.lbl_short_current = ttk.Label(short_frame, text="Mevcut: $0", foreground='green')
        self.lbl_short_current.pack(side='left', padx=10)
        self.lbl_short_diff = ttk.Label(short_frame, text="Fark: $0", foreground='red')
        self.lbl_short_diff.pack(side='left', padx=10)
        
        # Toplam exposure bilgisi
        total_frame = ttk.Frame(exposure_frame)
        total_frame.pack(fill='x', padx=5, pady=2)
        
        ttk.Label(total_frame, text="💰 Toplam Exposure:", font=('Arial', 10, 'bold')).pack(side='left')
        self.lbl_total_ideal = ttk.Label(total_frame, text="İdeal: $0", foreground='blue')
        self.lbl_total_ideal.pack(side='left', padx=10)
        self.lbl_total_current = ttk.Label(total_frame, text="Mevcut: $0", foreground='green')
        self.lbl_total_current.pack(side='left', padx=10)
        self.lbl_total_diff = ttk.Label(total_frame, text="Fark: $0", foreground='red')
        self.lbl_total_diff.pack(side='left', padx=10)
    
    def load_data(self):
        """Verileri yükle"""
        try:
            self.lbl_info.config(text="Veriler yükleniyor...")
            self.win.update()
            
            # İdeal portföyü yükle
            self.load_ideal_portfolio()
            
            # Mevcut pozisyonları yükle
            self.load_current_positions()
            
            # Grup dağılımını hesapla
            self.calculate_group_distribution()
            
            # Tabloları güncelle
            self.update_tables()
            
            # Exposure bilgilerini güncelle
            self.update_exposure_info()
            
            self.lbl_info.config(text=f"✅ Veriler yüklendi - {self.current_mode} modu")
            
        except Exception as e:
            messagebox.showerror("Hata", f"Veriler yüklenirken hata oluştu:\n{e}")
            self.lbl_info.config(text="❌ Hata oluştu")
    
    def load_ideal_portfolio(self):
        """İdeal portföy dağılımını exposureadjuster.csv'den yükle"""
        try:
            # CSV dosya yolu
            current_dir = os.path.dirname(os.path.abspath(__file__))  # janallapp dizini
            project_root = os.path.dirname(os.path.dirname(current_dir))  # StockTracker dizini
            csv_path = os.path.join(project_root, 'exposureadjuster.csv')
            
            if not os.path.exists(csv_path):
                raise FileNotFoundError(f"exposureadjuster.csv dosyası bulunamadı!\nAranan yol: {os.path.abspath(csv_path)}")
            
            df = pd.read_csv(csv_path)
            
            # Genel ayarları al
            total_exposure = 1000000  # Default
            avg_pref_price = 25.0     # Default
            long_ratio = 85.0         # Default
            short_ratio = 15.0        # Default
            
            for _, row in df.iterrows():
                setting = str(row['Setting']).strip()
                value = str(row['Value']).strip()
                
                if setting == 'Total Exposure':
                    try:
                        exposure_str = value.replace('$', '').replace(',', '')
                        total_exposure = float(exposure_str)
                    except:
                        pass
                elif setting == 'Avg Pref Price':
                    try:
                        price_str = value.replace('$', '').replace(',', '')
                        avg_pref_price = float(price_str)
                    except:
                        pass
                elif setting == 'Long Ratio':
                    try:
                        ratio_str = value.replace('%', '')
                        long_ratio = float(ratio_str)
                    except:
                        pass
                elif setting == 'Short Ratio':
                    try:
                        ratio_str = value.replace('%', '')
                        short_ratio = float(ratio_str)
                    except:
                        pass
            
            # Toplam lot hesapla
            total_lots = int(total_exposure / avg_pref_price)
            long_lots = int(total_lots * long_ratio / 100)
            short_lots = int(total_lots * short_ratio / 100)
            
            print(f"[PORTFOLIO COMPARISON] 📊 İdeal portföy ayarları:")
            print(f"   💰 Total Exposure: ${total_exposure:,.0f}")
            print(f"   💵 Avg Pref Price: ${avg_pref_price:.2f}")
            print(f"   📈 Long Ratio: {long_ratio}%")
            print(f"   📉 Short Ratio: {short_ratio}%")
            print(f"   📊 Total Lots: {total_lots:,}")
            print(f"   📈 Long Lots: {long_lots:,}")
            print(f"   📉 Short Lots: {short_lots:,}")
            
            # Grup dağılımlarını al
            self.ideal_portfolio = {
                'total_exposure': total_exposure,
                'avg_pref_price': avg_pref_price,
                'long_ratio': long_ratio,
                'short_ratio': short_ratio,
                'total_lots': total_lots,
                'long_lots': long_lots,
                'short_lots': short_lots,
                'long_groups': {},
                'short_groups': {}
            }
            
            # Long Groups bölümünü bul
            long_groups_section = False
            short_groups_section = False
            
            for _, row in df.iterrows():
                setting = str(row['Setting']).strip()
                
                if setting == 'Long Groups':
                    long_groups_section = True
                    short_groups_section = False
                    continue
                elif setting == 'Short Groups':
                    long_groups_section = False
                    short_groups_section = True
                    continue
                elif setting == '':
                    continue
                
                if long_groups_section and setting != 'Percentage':
                    try:
                        percentage_str = str(row['Value']).replace('%', '')
                        percentage = float(percentage_str)
                        ideal_lots = int(long_lots * percentage / 100)
                        self.ideal_portfolio['long_groups'][setting] = {
                            'percentage': percentage,
                            'lots': ideal_lots
                        }
                    except:
                        pass
                
                elif short_groups_section and setting != 'Percentage':
                    try:
                        percentage_str = str(row['Value']).replace('%', '')
                        percentage = float(percentage_str)
                        ideal_lots = int(short_lots * percentage / 100)
                        self.ideal_portfolio['short_groups'][setting] = {
                            'percentage': percentage,
                            'lots': ideal_lots
                        }
                    except:
                        pass
            
            print(f"[PORTFOLIO COMPARISON] ✅ İdeal portföy yüklendi:")
            print(f"   📈 Long Groups: {len(self.ideal_portfolio['long_groups'])} grup")
            print(f"   📉 Short Groups: {len(self.ideal_portfolio['short_groups'])} grup")
            
        except Exception as e:
            print(f"[PORTFOLIO COMPARISON] ❌ İdeal portföy yüklenirken hata: {e}")
            raise
    
    def load_current_positions(self):
        """Mevcut pozisyonları aktif moddan yükle"""
        try:
            # Mode manager'ı kontrol et
            if hasattr(self.parent, 'mode_manager'):
                if self.parent.mode_manager.is_hampro_mode():
                    print("[PORTFOLIO COMPARISON] 🔄 HAMPRO modunda pozisyonlar çekiliyor...")
                    self.current_positions = self.parent.hammer.get_positions_direct()
                    self.current_mode = "HAMPRO"
                elif self.parent.mode_manager.is_ibkr_mode():
                    print("[PORTFOLIO COMPARISON] 🔄 IBKR modunda pozisyonlar çekiliyor...")
                    self.current_positions = self.parent.ibkr.get_positions_direct()
                    self.current_mode = "IBKR"
                else:
                    print("[PORTFOLIO COMPARISON] ⚠️ Mod belirlenemedi, HAMPRO kullanılıyor...")
                    self.current_positions = self.parent.hammer.get_positions_direct()
                    self.current_mode = "HAMPRO"
            else:
                print("[PORTFOLIO COMPARISON] ⚠️ Mode manager bulunamadı, HAMPRO kullanılıyor...")
                self.current_positions = self.parent.hammer.get_positions_direct()
                self.current_mode = "HAMPRO"
            
            print(f"[PORTFOLIO COMPARISON] ✅ {len(self.current_positions)} pozisyon yüklendi ({self.current_mode} modu)")
            
            # Pozisyonları detaylı debug et
            print(f"[PORTFOLIO COMPARISON] 🔍 Tüm pozisyonlar:")
            for i, pos in enumerate(self.current_positions):
                symbol = pos.get('symbol', 'N/A')
                qty = pos.get('qty', 0)
                print(f"[PORTFOLIO COMPARISON] 🔍 Pos {i+1}: '{symbol}' = {qty}")
            
            # Pozisyonları filtrele (0 olanları çıkar)
            filtered_positions = [pos for pos in self.current_positions if pos.get('qty', 0) != 0]
            print(f"[PORTFOLIO COMPARISON] 📊 Filtrelenmiş pozisyonlar: {len(filtered_positions)}")
            
            for i, pos in enumerate(filtered_positions):
                symbol = pos.get('symbol', 'N/A')
                qty = pos.get('qty', 0)
                print(f"[PORTFOLIO COMPARISON] 📊 Filtrelenmiş Pos {i+1}: '{symbol}' = {qty}")
            
        except Exception as e:
            print(f"[PORTFOLIO COMPARISON] ❌ Mevcut pozisyonlar yüklenirken hata: {e}")
            raise
    
    def calculate_group_distribution(self):
        """Mevcut pozisyonları gruplara göre dağıt"""
        try:
            # Grup dosyalarını yükle
            self.load_group_files()
            
            # Mevcut pozisyonları gruplara göre dağıt
            self.current_group_distribution = {
                'long_groups': {},
                'short_groups': {}
            }
            
            total_long_lots = 0
            total_short_lots = 0
            matched_positions = 0
            unmatched_positions = 0
            
            print(f"[PORTFOLIO COMPARISON] 🔄 {len(self.current_positions)} pozisyon gruplara dağıtılıyor...")
            
            for pos in self.current_positions:
                symbol = pos.get('symbol', '')
                qty = pos.get('qty', 0)
                
                if qty == 0:
                    print(f"[PORTFOLIO COMPARISON] ⚠️ {symbol}: qty=0, atlanıyor")
                    continue
                
                print(f"[PORTFOLIO COMPARISON] 🔍 {symbol}: {qty} lot işleniyor...")
                
                # Hisse grubunu bul
                group = self.find_stock_group(symbol)
                
                if group:
                    matched_positions += 1
                    if qty > 0:  # Long pozisyon
                        if group not in self.current_group_distribution['long_groups']:
                            self.current_group_distribution['long_groups'][group] = 0
                        self.current_group_distribution['long_groups'][group] += qty
                        total_long_lots += qty
                        print(f"[PORTFOLIO COMPARISON] ✅ {symbol}: +{qty} lot -> {group} (Long)")
                    else:  # Short pozisyon
                        if group not in self.current_group_distribution['short_groups']:
                            self.current_group_distribution['short_groups'][group] = 0
                        self.current_group_distribution['short_groups'][group] += abs(qty)
                        total_short_lots += abs(qty)
                        print(f"[PORTFOLIO COMPARISON] ✅ {symbol}: {abs(qty)} lot -> {group} (Short)")
                else:
                    unmatched_positions += 1
                    print(f"[PORTFOLIO COMPARISON] ❌ {symbol}: Grup bulunamadı!")
            
            print(f"[PORTFOLIO COMPARISON] 📊 Mevcut grup dağılımı:")
            print(f"   📈 Toplam Long Lots: {total_long_lots:,}")
            print(f"   📉 Toplam Short Lots: {total_short_lots:,}")
            print(f"   📈 Long Groups: {len(self.current_group_distribution['long_groups'])} grup")
            print(f"   📉 Short Groups: {len(self.current_group_distribution['short_groups'])} grup")
            print(f"   ✅ Eşleşen pozisyonlar: {matched_positions}")
            print(f"   ❌ Eşleşmeyen pozisyonlar: {unmatched_positions}")
            
            # Long grupları detaylı göster
            if self.current_group_distribution['long_groups']:
                print(f"[PORTFOLIO COMPARISON] 📈 Long Groups detayı:")
                for group, lots in self.current_group_distribution['long_groups'].items():
                    print(f"   📈 {group}: {lots:,} lot")
            
            # Short grupları detaylı göster
            if self.current_group_distribution['short_groups']:
                print(f"[PORTFOLIO COMPARISON] 📉 Short Groups detayı:")
                for group, lots in self.current_group_distribution['short_groups'].items():
                    print(f"   📉 {group}: {lots:,} lot")
            
        except Exception as e:
            print(f"[PORTFOLIO COMPARISON] ❌ Grup dağılımı hesaplanırken hata: {e}")
            raise
    
    def load_group_files(self):
        """Grup dosyalarını yükle - Take Profit Panel mantığıyla"""
        try:
            # Grup dosyaları mapping - Take Profit Panel'daki gibi
            self.group_files = {
                'heldcilizyeniyedi': 'ssfinekheldcilizyeniyedi.csv',
                'heldcommonsuz': 'ssfinekheldcommonsuz.csv', 
                'helddeznff': 'ssfinekhelddeznff.csv',
                'heldff': 'ssfinekheldff.csv',
                'heldflr': 'ssfinekheldflr.csv',
                'heldgarabetaltiyedi': 'ssfinekheldgarabetaltiyedi.csv',
                'heldkuponlu': 'ssfinekheldkuponlu.csv',
                'heldkuponlukreciliz': 'ssfinekheldkuponlukreciliz.csv',
                'heldkuponlukreorta': 'ssfinekheldkuponlukreorta.csv',
                'heldnff': 'ssfinekheldnff.csv',
                'heldotelremorta': 'ssfinekheldotelremorta.csv',
                'heldsolidbig': 'ssfinekheldsolidbig.csv',
                'heldtitrekhc': 'ssfinekheldtitrekhc.csv',
                'highmatur': 'ssfinekhighmatur.csv',
                'notbesmaturlu': 'ssfineknotbesmaturlu.csv',
                'notcefilliquid': 'ssfineknotcefilliquid.csv',
                'nottitrekhc': 'ssfineknotcefilliquid.csv',
                'rumoreddanger': 'ssfinekrumoreddanger.csv',
                'salakilliquid': 'ssfineksalakilliquid.csv',
                'shitremhc': 'ssfinekshitremhc.csv'
            }
            
            # Her grup dosyasını yükle
            self.group_stocks = {}
            for group_name, filename in self.group_files.items():
                # Dosya yolunu kontrol et - mevcut dizinde ara
                if os.path.exists(filename):
                    file_path = filename
                else:
                    # janall klasöründe ara
                    current_dir = os.path.dirname(os.path.abspath(__file__))  # janallapp dizini
                    project_root = os.path.dirname(os.path.dirname(current_dir))  # StockTracker dizini
                    janall_dir = os.path.join(project_root, 'janall')
                    file_path = os.path.join(janall_dir, filename)
                
                print(f"[PORTFOLIO COMPARISON] 🔍 Kontrol ediliyor: {file_path}")
                
                if os.path.exists(file_path):
                    try:
                        df = pd.read_csv(file_path)
                        print(f"[PORTFOLIO COMPARISON] 📊 {filename} yüklendi: {len(df)} satır")
                        print(f"[PORTFOLIO COMPARISON] 📋 Kolonlar: {list(df.columns)}")
                        
                        # PREF IBKR kolonunu kullan - Take Profit Panel'daki gibi
                        stocks = []
                        if 'PREF IBKR' in df.columns:
                            stocks = df['PREF IBKR'].dropna().astype(str).tolist()
                        elif 'Symbol' in df.columns:
                            stocks = df['Symbol'].dropna().astype(str).tolist()
                        elif 'SYMBOL' in df.columns:
                            stocks = df['SYMBOL'].dropna().astype(str).tolist()
                        elif 'symbol' in df.columns:
                            stocks = df['symbol'].dropna().astype(str).tolist()
                        else:
                            print(f"[PORTFOLIO COMPARISON] ⚠️ {filename} Symbol kolonu bulunamadı")
                        
                        self.group_stocks[group_name] = stocks
                        print(f"[PORTFOLIO COMPARISON] ✅ {group_name}: {len(stocks)} hisse")
                        
                        # İlk birkaç hisseyi göster
                        if stocks:
                            print(f"[PORTFOLIO COMPARISON] 🔍 {group_name} örnek hisseler: {stocks[:3]}")
                        
                    except Exception as e:
                        print(f"[PORTFOLIO COMPARISON] ❌ {filename} yüklenemedi: {e}")
                        self.group_stocks[group_name] = []
                else:
                    print(f"[PORTFOLIO COMPARISON] ⚠️ {filename} bulunamadı: {file_path}")
                    self.group_stocks[group_name] = []
            
            print(f"[PORTFOLIO COMPARISON] ✅ {len(self.group_stocks)} grup dosyası yüklendi")
            
            # Toplam hisse sayısını hesapla
            total_stocks = sum(len(stocks) for stocks in self.group_stocks.values())
            print(f"[PORTFOLIO COMPARISON] 📊 Toplam {total_stocks} hisse yüklendi")
            
        except Exception as e:
            print(f"[PORTFOLIO COMPARISON] ❌ Grup dosyaları yüklenirken hata: {e}")
            raise
    
    def find_stock_group(self, symbol):
        """Hisse senedinin hangi grupta olduğunu bul - Take Profit Panel mantığıyla"""
        try:
            # Symbol'ü normalize et
            normalized_symbol = symbol.strip().upper()
            print(f"[PORTFOLIO COMPARISON] 🔍 '{symbol}' -> '{normalized_symbol}' aranıyor...")
            
            # Her grupta ara - Take Profit Panel'daki gibi
            for group_name, stocks in self.group_stocks.items():
                for stock in stocks:
                    if stock and isinstance(stock, str):
                        stock_normalized = stock.strip().upper()
                        if stock_normalized == normalized_symbol:
                            print(f"[PORTFOLIO COMPARISON] ✅ '{symbol}' -> {group_name} grubunda bulundu")
                            return group_name
            
            # Bulunamadı
            print(f"[PORTFOLIO COMPARISON] ⚠️ '{symbol}' hiçbir grupta bulunamadı")
            return None
            
        except Exception as e:
            print(f"[PORTFOLIO COMPARISON] ❌ {symbol} grubu bulunurken hata: {e}")
            return None
    
    def update_tables(self):
        """Long ve Short tablolarını güncelle"""
        try:
            # Long tablosunu temizle ve güncelle
            for item in self.long_tree.get_children():
                self.long_tree.delete(item)
            
            # Short tablosunu temizle ve güncelle
            for item in self.short_tree.get_children():
                self.short_tree.delete(item)
            
            # Long grupları için satırlar ekle
            for group_name, ideal_data in self.ideal_portfolio['long_groups'].items():
                ideal_lots = ideal_data['lots']
                ideal_percentage = ideal_data['percentage']
                
                current_lots = self.current_group_distribution['long_groups'].get(group_name, 0)
                current_percentage = 0
                if sum(self.current_group_distribution['long_groups'].values()) > 0:
                    current_percentage = (current_lots / sum(self.current_group_distribution['long_groups'].values())) * 100
                
                lot_diff = current_lots - ideal_lots
                percentage_diff = current_percentage - ideal_percentage
                
                # Durum belirle
                if abs(percentage_diff) <= 1:
                    status = "✅ İyi"
                elif abs(percentage_diff) <= 3:
                    status = "⚠️ Orta"
                else:
                    status = "❌ Kötü"
                
                # Long tablosuna satır ekle
                self.long_tree.insert('', 'end', values=[
                    group_name,
                    f"{ideal_lots:,}",
                    f"{ideal_percentage:.1f}%",
                    f"{current_lots:,}",
                    f"{current_percentage:.1f}%",
                    f"{lot_diff:+,}",
                    f"{percentage_diff:+.1f}%",
                    status
                ])
            
            # Short grupları için satırlar ekle
            for group_name, ideal_data in self.ideal_portfolio['short_groups'].items():
                ideal_lots = ideal_data['lots']
                ideal_percentage = ideal_data['percentage']
                
                current_lots = self.current_group_distribution['short_groups'].get(group_name, 0)
                current_percentage = 0
                if sum(self.current_group_distribution['short_groups'].values()) > 0:
                    current_percentage = (current_lots / sum(self.current_group_distribution['short_groups'].values())) * 100
                
                lot_diff = current_lots - ideal_lots
                percentage_diff = current_percentage - ideal_percentage
                
                # Durum belirle
                if abs(percentage_diff) <= 1:
                    status = "✅ İyi"
                elif abs(percentage_diff) <= 3:
                    status = "⚠️ Orta"
                else:
                    status = "❌ Kötü"
                
                # Short tablosuna satır ekle
                self.short_tree.insert('', 'end', values=[
                    group_name,
                    f"{ideal_lots:,}",
                    f"{ideal_percentage:.1f}%",
                    f"{current_lots:,}",
                    f"{current_percentage:.1f}%",
                    f"{lot_diff:+,}",
                    f"{percentage_diff:+.1f}%",
                    status
                ])
            
            print(f"[PORTFOLIO COMPARISON] ✅ Tablolar güncellendi")
            
        except Exception as e:
            print(f"[PORTFOLIO COMPARISON] ❌ Tablolar güncellenirken hata: {e}")
            raise
    
    def update_exposure_info(self):
        """Exposure bilgilerini güncelle"""
        try:
            # İdeal exposure hesapla
            avg_price = self.ideal_portfolio['avg_pref_price']
            
            # İdeal long exposure
            ideal_long_lots = self.ideal_portfolio['long_lots']
            ideal_long_exposure = ideal_long_lots * avg_price
            
            # İdeal short exposure
            ideal_short_lots = self.ideal_portfolio['short_lots']
            ideal_short_exposure = ideal_short_lots * avg_price
            
            # İdeal toplam exposure
            ideal_total_exposure = ideal_long_exposure + ideal_short_exposure
            
            # Mevcut exposure hesapla
            current_long_lots = sum(self.current_group_distribution['long_groups'].values())
            current_long_exposure = current_long_lots * avg_price
            
            current_short_lots = sum(self.current_group_distribution['short_groups'].values())
            current_short_exposure = current_short_lots * avg_price
            
            current_total_exposure = current_long_exposure + current_short_exposure
            
            # Farkları hesapla
            long_diff = current_long_exposure - ideal_long_exposure
            short_diff = current_short_exposure - ideal_short_exposure
            total_diff = current_total_exposure - ideal_total_exposure
            
            # Long exposure bilgilerini güncelle
            self.lbl_long_ideal.config(text=f"İdeal: ${ideal_long_exposure:,.0f}")
            self.lbl_long_current.config(text=f"Mevcut: ${current_long_exposure:,.0f}")
            self.lbl_long_diff.config(text=f"Fark: ${long_diff:+,.0f}")
            
            # Short exposure bilgilerini güncelle
            self.lbl_short_ideal.config(text=f"İdeal: ${ideal_short_exposure:,.0f}")
            self.lbl_short_current.config(text=f"Mevcut: ${current_short_exposure:,.0f}")
            self.lbl_short_diff.config(text=f"Fark: ${short_diff:+,.0f}")
            
            # Toplam exposure bilgilerini güncelle
            self.lbl_total_ideal.config(text=f"İdeal: ${ideal_total_exposure:,.0f}")
            self.lbl_total_current.config(text=f"Mevcut: ${current_total_exposure:,.0f}")
            self.lbl_total_diff.config(text=f"Fark: ${total_diff:+,.0f}")
            
            print(f"[PORTFOLIO COMPARISON] 📊 Exposure bilgileri güncellendi:")
            print(f"   📈 Long: İdeal ${ideal_long_exposure:,.0f}, Mevcut ${current_long_exposure:,.0f}, Fark ${long_diff:+,.0f}")
            print(f"   📉 Short: İdeal ${ideal_short_exposure:,.0f}, Mevcut ${current_short_exposure:,.0f}, Fark ${short_diff:+,.0f}")
            print(f"   💰 Toplam: İdeal ${ideal_total_exposure:,.0f}, Mevcut ${current_total_exposure:,.0f}, Fark ${total_diff:+,.0f}")
            
        except Exception as e:
            print(f"[PORTFOLIO COMPARISON] ❌ Exposure bilgileri güncellenirken hata: {e}")
            raise
    
    def sort_by_column(self, col, table_type='long'):
        """Kolonu sırala"""
        try:
            # Hangi tabloyu kullanacağımızı belirle
            tree = self.long_tree if table_type == 'long' else self.short_tree
            
            # Mevcut sıralama durumunu kontrol et
            if hasattr(self, f'sort_column_{table_type}') and getattr(self, f'sort_column_{table_type}') == col:
                setattr(self, f'sort_reverse_{table_type}', not getattr(self, f'sort_reverse_{table_type}'))
            else:
                setattr(self, f'sort_column_{table_type}', col)
                setattr(self, f'sort_reverse_{table_type}', False)
            
            # Verileri al ve sırala
            data = []
            for item in tree.get_children():
                values = tree.item(item)['values']
                data.append(values)
            
            # Kolon indeksini bul
            columns = ['Grup', 'İdeal Lot', 'İdeal %', 'Mevcut Lot', 'Mevcut %', 'Lot Farkı', '% Farkı', 'Durum']
            col_index = columns.index(col)
            
            # Sırala
            reverse = getattr(self, f'sort_reverse_{table_type}')
            data.sort(key=lambda x: self._sort_key(x[col_index], col_index), reverse=reverse)
            
            # Tabloyu yeniden doldur
            for item in tree.get_children():
                tree.delete(item)
            
            for row in data:
                tree.insert('', 'end', values=row)
            
            print(f"[PORTFOLIO COMPARISON] 📊 {table_type} tablosu {col} kolonuna göre sıralandı (reverse={reverse})")
            
        except Exception as e:
            print(f"[PORTFOLIO COMPARISON] ❌ Sıralama hatası: {e}")
    
    def _sort_key(self, value, col_index):
        """Sıralama anahtarı"""
        try:
            if col_index in [1, 3, 5]:  # Lot sayıları
                return int(value.replace(',', '').replace('+', '').replace('-', ''))
            elif col_index in [2, 4, 6]:  # Yüzdeler
                return float(value.replace('%', '').replace('+', '').replace('-', ''))
            else:
                return str(value)
        except:
            return str(value)
    
    def export_to_excel(self):
        """Sonuçları Excel'e aktar"""
        try:
            from tkinter import filedialog
            
            # Dosya seç
            filename = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                title="Portfolio Comparison'ı Excel'e Aktar"
            )
            
            if not filename:
                return
            
            # Verileri hazırla
            columns = ['Grup', 'İdeal Lot', 'İdeal %', 'Mevcut Lot', 'Mevcut %', 'Lot Farkı', '% Farkı', 'Durum']
            
            # Long verileri
            long_data = []
            for item in self.long_tree.get_children():
                values = self.long_tree.item(item)['values']
                long_data.append(['Long'] + values)  # Tip bilgisi ekle
            
            # Short verileri
            short_data = []
            for item in self.short_tree.get_children():
                values = self.short_tree.item(item)['values']
                short_data.append(['Short'] + values)  # Tip bilgisi ekle
            
            # Tüm verileri birleştir
            all_data = long_data + short_data
            all_columns = ['Tip'] + columns
            
            # DataFrame oluştur
            df = pd.DataFrame(all_data, columns=all_columns)
            
            # Excel'e yaz
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Portfolio Comparison', index=False)
                
                # Exposure bilgilerini ayrı sheet'e ekle
                exposure_data = {
                    'Metrik': ['Long Exposure', 'Short Exposure', 'Toplam Exposure'],
                    'İdeal': [
                        self.lbl_long_ideal.cget('text').replace('İdeal: ', ''),
                        self.lbl_short_ideal.cget('text').replace('İdeal: ', ''),
                        self.lbl_total_ideal.cget('text').replace('İdeal: ', '')
                    ],
                    'Mevcut': [
                        self.lbl_long_current.cget('text').replace('Mevcut: ', ''),
                        self.lbl_short_current.cget('text').replace('Mevcut: ', ''),
                        self.lbl_total_current.cget('text').replace('Mevcut: ', '')
                    ],
                    'Fark': [
                        self.lbl_long_diff.cget('text').replace('Fark: ', ''),
                        self.lbl_short_diff.cget('text').replace('Fark: ', ''),
                        self.lbl_total_diff.cget('text').replace('Fark: ', '')
                    ]
                }
                
                exposure_df = pd.DataFrame(exposure_data)
                exposure_df.to_excel(writer, sheet_name='Exposure Summary', index=False)
            
            messagebox.showinfo("Başarılı", f"Portfolio Comparison başarıyla Excel'e aktarıldı:\n{filename}")
            
        except Exception as e:
            messagebox.showerror("Hata", f"Excel'e aktarılırken hata oluştu:\n{e}")
