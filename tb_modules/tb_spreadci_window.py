#!/usr/bin/env python
"""
SpreadciDataWindow implementation for StockTracker
"""
import math
import time
import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import threading
from collections import defaultdict
from ib_insync import Stock

class SpreadciDataWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Spreadci Data Monitor")
        self.geometry("1200x600")
        
        # IBKR bağlantısı ve referanslar
        self.parent = parent
        self.ib = parent.ib  # Ana penceredeki IBKR bağlantısını kullan
        self.is_connected = parent.is_connected
        
        # Veri yönetimi
        self.ticker_contracts = {}  # Aktif abonelikler
        self.latest_data = defaultdict(dict)
        self.all_symbols = []  # Tüm semboller
        self.current_page = 0  # Mevcut sayfa
        self.symbols_per_page = 20  # Sayfa başına sembol sayısı
        self.running = True
        
        # UI oluştur
        self.setup_ui()
        
        # Verileri yükle
        self.load_data()
        
        # Abonelikleri başlat
        if self.is_connected:
            self.subscribe_page_tickers()
        
        # Kapanış işleyici ekle
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Event loop'u başlat
        threading.Thread(target=self.run_event_loop, daemon=True).start()
        
    def setup_ui(self):
        # Ana frame
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Treeview
        self.tree = ttk.Treeview(self.main_frame)
        self.tree['columns'] = ('Symbol', 'Bid', 'Ask', 'Last', 'Volume', 'Spread', 'DIV AMOUNT')
        
        # Sütunları yapılandır
        self.tree.column('#0', width=0, stretch=tk.NO)
        self.tree.column('Symbol', anchor=tk.W, width=100)
        self.tree.column('Bid', anchor=tk.E, width=100)
        self.tree.column('Ask', anchor=tk.E, width=100)
        self.tree.column('Last', anchor=tk.E, width=100)
        self.tree.column('Volume', anchor=tk.E, width=100)
        self.tree.column('Spread', anchor=tk.E, width=100)
        self.tree.column('DIV AMOUNT', anchor=tk.E, width=100)
        
        # Başlıkları yapılandır
        self.tree.heading('Symbol', text='Symbol')
        self.tree.heading('Bid', text='Bid')
        self.tree.heading('Ask', text='Ask')
        self.tree.heading('Last', text='Last')
        self.tree.heading('Volume', text='Volume')
        self.tree.heading('Spread', text='Spread')
        self.tree.heading('DIV AMOUNT', text='DIV AMOUNT')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.main_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Yerleştirme
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Sayfalama kontrolleri
        self.nav_frame = ttk.Frame(self)
        self.nav_frame.pack(fill=tk.X, pady=5)
        
        self.prev_button = ttk.Button(self.nav_frame, text="Önceki Sayfa", command=self.prev_page)
        self.prev_button.pack(side=tk.LEFT, padx=5)
        
        self.next_button = ttk.Button(self.nav_frame, text="Sonraki Sayfa", command=self.next_page)
        self.next_button.pack(side=tk.LEFT, padx=5)
        
        self.page_label = ttk.Label(self.nav_frame, text="Sayfa: 1")
        self.page_label.pack(side=tk.LEFT, padx=20)
        
        # Yenile butonu
        self.refresh_button = ttk.Button(self.nav_frame, text="Yenile", command=self.refresh_data)
        self.refresh_button.pack(side=tk.RIGHT, padx=5)
        
        # Son güncelleme zamanı
        self.last_update_label = ttk.Label(self.nav_frame, text="Son güncelleme: -")
        self.last_update_label.pack(side=tk.RIGHT, padx=20)
    
    def load_data(self):
        """CSV'den verileri yükle"""
        try:
            # Spreadci verilerini ana uygulamadan al veya CSV'den oku
            self.all_symbols = []
            
            try:
                # Ana uygulamadan verileri al
                spreadci_data = self.parent.get_spreadci_data()
                if spreadci_data:
                    self.all_symbols = list(spreadci_data.keys())
            except:
                # CSV'den yüklemeyi dene
                try:
                    df = pd.read_csv('spreadci.csv')
                    if 'PREF IBKR' in df.columns:
                        self.all_symbols = df[df['PREF IBKR'].notna()]['PREF IBKR'].tolist()
                except:
                    # Örnek veri oluştur
                    self.all_symbols = ["NLY-F", "NLY-G", "NLY-I", "AGNC-G", "DX-C", "RC-E", "TWO-A", "TWO-B", "TWO-C"]
            
            # İlk sayfayı yükle
            self.current_page = 0
            self.load_page()
            
        except Exception as e:
            messagebox.showerror("Hata", f"Veri yüklenirken hata oluştu: {str(e)}")
    
    def load_page(self):
        """Belirli bir sayfayı yükle"""
        try:
            # Önce abonelikleri temizle
            self.clear_subscriptions()
            
            # Treeview'ı temizle
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            # Sayfa için sembolleri al
            start_idx = self.current_page * self.symbols_per_page
            end_idx = start_idx + self.symbols_per_page
            
            # Listenin sınırlarını kontrol et
            if start_idx >= len(self.all_symbols):
                start_idx = 0
                self.current_page = 0
                end_idx = min(self.symbols_per_page, len(self.all_symbols))
            
            page_symbols = self.all_symbols[start_idx:end_idx]
            
            # Her sembol için treeview'a satır ekle
            for symbol in page_symbols:
                self.tree.insert('', tk.END, text="", values=(
                    symbol, '0.00', '0.00', '0.00', '0', '0.00', '0.00'
                ))
            
            # Sayfa bilgisini güncelle
            total_pages = max(1, math.ceil(len(self.all_symbols) / self.symbols_per_page))
            self.page_label.config(text=f"Sayfa: {self.current_page + 1}/{total_pages}")
            
            # Butonları güncelle
            self.prev_button.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
            self.next_button.config(state=tk.NORMAL if self.current_page < total_pages - 1 else tk.DISABLED)
            
            # Sembollere abone ol
            self.subscribe_page_tickers()
            
        except Exception as e:
            print(f"Spreadci load_page error: {e}")
    
    def subscribe_page_tickers(self):
        """Mevcut sayfadaki tickerlara abone ol"""
        if not self.is_connected:
            return
            
        try:
            # Sayfa için sembolleri al
            start_idx = self.current_page * self.symbols_per_page
            end_idx = start_idx + self.symbols_per_page
            page_symbols = self.all_symbols[start_idx:end_idx]
            
            # Ana penceredeki fonksiyonu kullanarak abone ol
            self.parent.subscribe_spreadci_tickers(page_symbols)
        except Exception as e:
            print(f"Subscribe page tickers error: {e}")
    
    def clear_subscriptions(self):
        """Spreadci aboneliklerini temizle"""
        try:
            if self.is_connected:
                # Ana penceredeki fonksiyonu kullanarak abonelikleri temizle
                self.parent.clear_spreadci_subscriptions()
        except Exception as e:
            print(f"Clear subscriptions error: {e}")
    
    def prev_page(self):
        """Önceki sayfaya git"""
        if self.current_page > 0:
            self.current_page -= 1
            self.load_page()
    
    def next_page(self):
        """Sonraki sayfaya git"""
        total_pages = math.ceil(len(self.all_symbols) / self.symbols_per_page)
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.load_page()
    
    def refresh_data(self):
        """Spreadci verilerini yenile"""
        self.load_page()
        self.last_update_label.config(text=f"Son güncelleme: {datetime.datetime.now().strftime('%H:%M:%S')}")
    
    def run_event_loop(self):
        """Arka plan işleyici için event loop"""
        while self.running:
            try:
                if self.is_connected:
                    self.update_ui()
                time.sleep(1)
            except Exception as e:
                print(f"Spreadci event loop error: {e}")
    
    def update_ui(self):
        """UI'ı güncelle"""
        try:
            # Piyasa verilerini al
            market_data = self.parent.market_data_cache
            
            # Treeview öğelerini al
            for item in self.tree.get_children():
                symbol = self.tree.item(item, 'values')[0]
                
                # Markwt data'dan veriyi al
                ticker_data = market_data.get(symbol)
                
                if ticker_data:
                    bid = getattr(ticker_data, 'bid', 0.0)
                    ask = getattr(ticker_data, 'ask', 0.0)
                    last = getattr(ticker_data, 'last', 0.0)
                    volume = getattr(ticker_data, 'volume', 0)
                    
                    # Spread hesapla
                    spread = 0.0
                    if bid and ask and bid > 0:
                        spread = (ask - bid) / bid * 100
                    
                    # Treeview'ı güncelle
                    self.tree.item(item, values=(
                        symbol, 
                        f"{bid:.2f}" if bid else "0.00", 
                        f"{ask:.2f}" if ask else "0.00", 
                        f"{last:.2f}" if last else "0.00", 
                        volume, 
                        f"{spread:.2f}%" if spread else "0.00%",
                        "0.00"  # Temettü verisi şu an için sabit
                    ))
            
            # Son güncelleme zamanını göster
            now = datetime.datetime.now().strftime("%H:%M:%S")
            self.last_update_label.config(text=f"Son güncelleme: {now}")
            
        except Exception as e:
            print(f"Update UI error: {e}")
    
    def on_closing(self):
        """Pencere kapatılırken çağrılır"""
        try:
            # Event loop'u durdur
            self.running = False
            
            # Abonelikleri temizle
            self.clear_subscriptions()
            
            # Pencereyi kapat
            self.destroy()
        except Exception as e:
            print(f"Window closing error: {e}") 