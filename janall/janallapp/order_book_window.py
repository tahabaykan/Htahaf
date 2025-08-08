"""
OrderBook pencere modülü.
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta

class OrderBookWindow(tk.Toplevel):
    def __init__(self, parent, symbol, hammer_client):
        super().__init__(parent)
        
        self.symbol = symbol
        self.hammer = hammer_client
        
        # Pencere ayarları
        self.title(f"OrderBook - {symbol}")
        self.geometry("800x600")
        
        # L2 verisi için subscribe ol
        self.hammer.subscribe_symbol(symbol, include_l2=True)
        print(f"[ORDERBOOK] 📊 {symbol} için L2 verisi istendi")
        
        # Grid ağırlıkları
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1)
        
        self.setup_ui()
        self.start_updates()
        
    def setup_ui(self):
        # Üst başlık
        header = ttk.Label(self, text=f"{self.symbol} OrderBook", font=('Arial', 14, 'bold'))
        header.grid(row=0, column=0, columnspan=3, pady=10)
        
        # Bid Tablosu
        bid_frame = ttk.LabelFrame(self, text="Bid (7)")
        bid_frame.grid(row=1, column=0, padx=5, pady=5, sticky='nsew')
        
        self.bid_table = ttk.Treeview(bid_frame, columns=('Price', 'Size', 'Venue'), show='headings', height=7)
        for col in ('Price', 'Size', 'Venue'):
            self.bid_table.heading(col, text=col)
            self.bid_table.column(col, width=80)
        self.bid_table.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Ask Tablosu
        ask_frame = ttk.LabelFrame(self, text="Ask (7)")
        ask_frame.grid(row=1, column=1, padx=5, pady=5, sticky='nsew')
        
        self.ask_table = ttk.Treeview(ask_frame, columns=('Price', 'Size', 'Venue'), show='headings', height=7)
        for col in ('Price', 'Size', 'Venue'):
            self.ask_table.heading(col, text=col)
            self.ask_table.column(col, width=80)
        self.ask_table.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Last Prints Tablosu
        prints_frame = ttk.LabelFrame(self, text="Last Prints (10)")
        prints_frame.grid(row=1, column=2, padx=5, pady=5, sticky='nsew')
        
        self.prints_table = ttk.Treeview(prints_frame, 
            columns=('Time', 'Price', 'Size', 'Venue'), 
            show='headings',
            height=10)
        for col, width in [('Time', 60), ('Price', 80), ('Size', 80), ('Venue', 60)]:
            self.prints_table.heading(col, text=col)
            self.prints_table.column(col, width=width)
        self.prints_table.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Alt bilgi çubuğu
        self.status_label = ttk.Label(self, text="Veri bekleniyor...")
        self.status_label.grid(row=2, column=0, columnspan=3, pady=5)
        
    def update_orderbook(self):
        """OrderBook verilerini güncelle"""
        try:
            # L2 verilerini al
            l2_data = self.hammer.l2_data.get(self.symbol, {})
            if not l2_data:
                return
                
            # Bid tablosunu güncelle
            for item in self.bid_table.get_children():
                self.bid_table.delete(item)
            for bid in l2_data.get('bids', [])[:7]:  # İlk 7 bid
                self.bid_table.insert('', 'end', values=(
                    f"{bid['price']:.2f}",
                    f"{bid['size']:.1f}",
                    bid['venue']
                ))
                
            # Ask tablosunu güncelle
            for item in self.ask_table.get_children():
                self.ask_table.delete(item)
            for ask in l2_data.get('asks', [])[:7]:  # İlk 7 ask
                self.ask_table.insert('', 'end', values=(
                    f"{ask['price']:.2f}",
                    f"{ask['size']:.1f}",
                    ask['venue']
                ))
                
            # Last prints tablosunu güncelle
            prints = l2_data.get('last_prints', [])  # Son 10 print zaten sınırlı
            for item in self.prints_table.get_children():
                self.prints_table.delete(item)
            for print_data in prints:
                self.prints_table.insert('', 0, values=(  # Başa ekle (en yeni üstte)
                    print_data['time'],
                    f"{print_data['price']:.2f}",
                    f"{print_data['size']:.1f}",
                    print_data['venue']
                ))
                
            # Durum çubuğunu güncelle
            timestamp = l2_data.get('timestamp', '')
            if timestamp:
                try:
                    # ISO format'tan datetime'a çevir
                    dt = datetime.fromisoformat(timestamp)
                    # Türkiye saati için 3 saat ekle
                    dt = dt + timedelta(hours=3)
                    # Formatla
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-4]
                    self.status_label.config(text=f"Son güncelleme: {formatted_time}")
                except:
                    self.status_label.config(text=f"Son güncelleme: {timestamp}")
            
        except Exception as e:
            self.status_label.config(text=f"Hata: {str(e)}")
            
    def start_updates(self):
        """Periyodik güncellemeyi başlat"""
        self.update_orderbook()
        self.after(1000, self.start_updates)  # Her 1 saniyede bir güncelle