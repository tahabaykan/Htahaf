"""
Order Management modülü - Emir gönderme ve yönetimi
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd

class OrderManager:
    def __init__(self, main_window):
        self.main_window = main_window
        self.hammer = main_window.hammer
        
    def place_order_for_selected(self, order_type):
        """Seçili tickerlar için emir gönder"""
        selected_tickers = self.get_selected_tickers()
        if not selected_tickers:
            print("❌ Seçili ticker yok!")
            return
        
        try:
            lot_size = int(self.main_window.lot_entry.get())
        except ValueError:
            print("❌ Geçersiz lot değeri!")
            return
        
        print(f"📤 {len(selected_tickers)} ticker için {order_type} emri hazırlanıyor...")
        
        # Emir onay penceresi göster
        self.show_order_confirmation(selected_tickers, order_type, lot_size)
    
    def show_order_confirmation(self, tickers, order_type, lot_size):
        """Emir onay penceresi göster"""
        # Onay penceresi oluştur
        confirm_window = tk.Toplevel(self.main_window)
        confirm_window.title("Emir Onayı")
        confirm_window.geometry("500x400")
        confirm_window.transient(self.main_window)
        confirm_window.grab_set()
        
        # Başlık
        title_label = ttk.Label(confirm_window, text="Gönderilecek Emirler", font=("Arial", 12, "bold"))
        title_label.pack(pady=10)
        
        # Emir detayları frame
        details_frame = ttk.Frame(confirm_window)
        details_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Scrollable text widget
        text_widget = tk.Text(details_frame, height=15, width=60)
        scrollbar = ttk.Scrollbar(details_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Emir detaylarını hazırla
        order_details = []
        total_cost = 0
        
        for ticker in tickers:
            try:
                # Market data'dan değerleri al
                market_data = self.hammer.get_market_data(ticker)
                if not market_data:
                    text_widget.insert(tk.END, f"⚠️ {ticker} için market data bulunamadı\n")
                    continue
                
                bid = float(market_data.get('bid', 0))
                ask = float(market_data.get('ask', 0))
                last = float(market_data.get('last', 0))
                spread = ask - bid
                
                # Emir fiyatını hesapla
                if order_type == 'bid_buy':
                    price = bid + (spread * 0.15)
                    action = 'BUY'
                elif order_type == 'front_buy':
                    price = last + 0.01
                    action = 'BUY'
                elif order_type == 'ask_buy':
                    price = ask + 0.01
                    action = 'BUY'
                elif order_type == 'ask_sell':
                    price = ask - (spread * 0.15)
                    action = 'SELL'
                elif order_type == 'front_sell':
                    price = last - 0.01
                    action = 'SELL'
                elif order_type == 'bid_sell':
                    price = bid - 0.01
                    action = 'SELL'
                else:
                    text_widget.insert(tk.END, f"❌ Bilinmeyen emir tipi: {order_type}\n")
                    continue
                
                # Emir detayını kaydet
                order_details.append({
                    'ticker': ticker,
                    'action': action,
                    'price': price,
                    'lot_size': lot_size,
                    'total': price * lot_size
                })
                
                # Detayları text widget'a ekle
                text_widget.insert(tk.END, f"📋 {ticker}\n")
                text_widget.insert(tk.END, f"   İşlem: {action}\n")
                text_widget.insert(tk.END, f"   Fiyat: ${price:.4f}\n")
                text_widget.insert(tk.END, f"   Lot: {lot_size}\n")
                text_widget.insert(tk.END, f"   Toplam: ${price * lot_size:.2f}\n")
                text_widget.insert(tk.END, f"   Tip: {order_type}\n")
                text_widget.insert(tk.END, "-" * 40 + "\n")
                
                total_cost += price * lot_size
                
            except Exception as e:
                text_widget.insert(tk.END, f"❌ {ticker} için hata: {e}\n")
        
        # Toplam bilgisi
        text_widget.insert(tk.END, f"\n💰 TOPLAM MALİYET: ${total_cost:.2f}\n")
        text_widget.insert(tk.END, f"📊 TOPLAM EMİR SAYISI: {len(order_details)}\n")
        
        # Butonlar frame
        button_frame = ttk.Frame(confirm_window)
        button_frame.pack(pady=10)
        
        # Onayla butonu
        def confirm_orders():
            print(f"📤 {len(order_details)} emir gönderiliyor...")
            
            for order in order_details:
                try:
                    # Gerçek emir gönderimi
                    success = self.hammer.place_order(
                        order['ticker'], 
                        order['action'], 
                        order['lot_size'], 
                        order['price'], 
                        hidden=True
                    )
                    
                    if success:
                        print(f"✅ {order['ticker']} {order['action']} {order['lot_size']} lot @ ${order['price']:.4f} - BAŞARILI")
                    else:
                        print(f"❌ {order['ticker']} emri gönderilemedi")
                        
                except Exception as e:
                    print(f"❌ {order['ticker']} için emir gönderilirken hata: {e}")
            
            confirm_window.destroy()
            print("🎯 Tüm emirler işlendi!")
        
        # İptal butonu
        def cancel_orders():
            print("❌ Emirler iptal edildi")
            confirm_window.destroy()
        
        confirm_btn = ttk.Button(button_frame, text="✅ Emirleri Gönder", command=confirm_orders, style="Accent.TButton")
        confirm_btn.pack(side='left', padx=5)
        
        cancel_btn = ttk.Button(button_frame, text="❌ İptal", command=cancel_orders)
        cancel_btn.pack(side='left', padx=5)
    
    def get_selected_tickers(self):
        """Seçili tickerları döndür"""
        selected = []
        for item in self.main_window.table.get_children():
            if self.main_window.table.set(item, 'Seç') == '✓':
                ticker = self.main_window.table.set(item, 'PREF IBKR')
                selected.append(ticker)
        return selected
    
    def select_all_tickers(self):
        """Tüm tickerları seç"""
        for item in self.main_window.table.get_children():
            self.main_window.table.set(item, 'Seç', '✓')
    
    def deselect_all_tickers(self):
        """Tüm ticker seçimlerini kaldır"""
        for item in self.main_window.table.get_children():
            self.main_window.table.set(item, 'Seç', '')
    
    def set_lot_percentage(self, percentage):
        """Mevcut pozisyonun yüzdesi kadar lot ayarla"""
        selected_tickers = self.get_selected_tickers()
        if not selected_tickers:
            print("❌ Seçili ticker yok!")
            return
        
        # Pozisyonları al (şimdilik dummy data)
        positions = {}  # Gerçek pozisyon verisi buraya gelecek
        
        for ticker in selected_tickers:
            position_size = positions.get(ticker, 0)
            if position_size > 0:
                lot_size = int(position_size * percentage / 100)
                self.main_window.lot_entry.delete(0, tk.END)
                self.main_window.lot_entry.insert(0, str(lot_size))
                print(f"✅ {ticker} için %{percentage} lot: {lot_size}")
            else:
                print(f"⚠️ {ticker} için pozisyon bulunamadı")
    
    def set_lot_avg_adv(self):
        """Seçili hissenin AVG_ADV/40 değerini lot olarak ayarla"""
        selected_tickers = self.get_selected_tickers()
        if not selected_tickers:
            print("❌ Seçili ticker yok!")
            return
        
        # İlk seçili ticker için AVG_ADV değerini al
        ticker = selected_tickers[0]
        for item in self.main_window.table.get_children():
            if self.main_window.table.set(item, 'PREF IBKR') == ticker:
                avg_adv = self.main_window.table.set(item, 'AVG_ADV')
                try:
                    avg_adv_value = float(avg_adv)
                    lot_size = int(avg_adv_value / 40)
                    self.main_window.lot_entry.delete(0, tk.END)
                    self.main_window.lot_entry.insert(0, str(lot_size))
                    print(f"✅ {ticker} için Avg Adv lot: {lot_size} (AVG_ADV: {avg_adv_value})")
                except ValueError:
                    print(f"❌ {ticker} için AVG_ADV değeri geçersiz: {avg_adv}")
                break
    
    def on_checkbox_click(self, event):
        """Checkbox tıklama olayını işle"""
        region = self.main_window.table.identify_region(event.x, event.y)
        if region == "cell":
            column = self.main_window.table.identify_column(event.x)
            if column == "#1":  # Seç kolonu
                item = self.main_window.table.identify_row(event.y)
                if item:
                    current = self.main_window.table.set(item, "Seç")
                    self.main_window.table.set(item, "Seç", "✓" if current != "✓" else "")
    
    def select_ticker(self, symbol):
        """Belirli bir ticker'ı seç/seçimi kaldır"""
        try:
            # Tablodaki tüm satırları kontrol et
            for item in self.main_window.table.get_children():
                values = self.main_window.table.item(item)['values']
                if values and len(values) > 1 and values[1] == symbol:  # PREF IBKR kolonu
                    current = self.main_window.table.set(item, "Seç")
                    new_value = "✓" if current != "✓" else ""
                    self.main_window.table.set(item, "Seç", new_value)
                    print(f"✅ {symbol} {'seçildi' if new_value == '✓' else 'seçimi kaldırıldı'}")
                    break
        except Exception as e:
            print(f"❌ {symbol} seçimi hatası: {e}")


class OrderBookWindow:
    def __init__(self, parent, symbol, hammer_client):
        self.parent = parent
        self.symbol = symbol
        self.hammer = hammer_client
        
        # Pencere oluştur
        self.window = tk.Toplevel(parent)
        self.window.title(f"OrderBook - {symbol}")
        self.window.geometry("800x600")
        
        # Order Management butonları ekle
        self.setup_order_buttons()
        
        # OrderBook tablosu
        self.setup_orderbook_table()
        
        # L2 data subscribe
        self.hammer.subscribe_symbol(symbol, include_l2=True)
        
        # Güncelleme döngüsü
        self.update_orderbook()
    
    def setup_order_buttons(self):
        """OrderBook penceresine order butonları ekle"""
        order_frame = ttk.Frame(self.window)
        order_frame.pack(fill='x', padx=5, pady=2)
        
        # Order butonları
        self.btn_bid_buy = ttk.Button(order_frame, text="Bid Buy", 
                                     command=lambda: self.place_order('bid_buy'), width=10)
        self.btn_bid_buy.pack(side='left', padx=1)
        
        self.btn_front_buy = ttk.Button(order_frame, text="Front Buy", 
                                       command=lambda: self.place_order('front_buy'), width=10)
        self.btn_front_buy.pack(side='left', padx=1)
        
        self.btn_ask_buy = ttk.Button(order_frame, text="Ask Buy", 
                                     command=lambda: self.place_order('ask_buy'), width=10)
        self.btn_ask_buy.pack(side='left', padx=1)
        
        self.btn_ask_sell = ttk.Button(order_frame, text="Ask Sell", 
                                      command=lambda: self.place_order('ask_sell'), width=10)
        self.btn_ask_sell.pack(side='left', padx=1)
        
        self.btn_front_sell = ttk.Button(order_frame, text="Front Sell", 
                                        command=lambda: self.place_order('front_sell'), width=10)
        self.btn_front_sell.pack(side='left', padx=1)
        
        self.btn_bid_sell = ttk.Button(order_frame, text="Bid Sell", 
                                      command=lambda: self.place_order('bid_sell'), width=10)
        self.btn_bid_sell.pack(side='left', padx=1)
        
        # Lot girişi
        ttk.Label(order_frame, text="Lot:").pack(side='left', padx=2)
        self.lot_entry = ttk.Entry(order_frame, width=8)
        self.lot_entry.pack(side='left', padx=2)
        self.lot_entry.insert(0, "200")
    
    def setup_orderbook_table(self):
        """OrderBook tablosunu oluştur"""
        # Ana frame
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Bids frame
        bids_frame = ttk.LabelFrame(main_frame, text="Bids")
        bids_frame.pack(side='left', fill='both', expand=True, padx=2)
        
        # Bids tablosu
        bids_columns = ('Price', 'Size', 'Venue')
        self.bids_tree = ttk.Treeview(bids_frame, columns=bids_columns, show='headings', height=10)
        for col in bids_columns:
            self.bids_tree.heading(col, text=col)
            self.bids_tree.column(col, width=100)
        self.bids_tree.pack(fill='both', expand=True)
        
        # Asks frame
        asks_frame = ttk.LabelFrame(main_frame, text="Asks")
        asks_frame.pack(side='right', fill='both', expand=True, padx=2)
        
        # Asks tablosu
        asks_columns = ('Price', 'Size', 'Venue')
        self.asks_tree = ttk.Treeview(asks_frame, columns=asks_columns, show='headings', height=10)
        for col in asks_columns:
            self.asks_tree.heading(col, text=col)
            self.asks_tree.column(col, width=100)
        self.asks_tree.pack(fill='both', expand=True)
        
        # Last prints frame
        prints_frame = ttk.LabelFrame(self.window, text="Last Prints")
        prints_frame.pack(fill='x', padx=5, pady=5)
        
        # Last prints tablosu
        prints_columns = ('Time', 'Price', 'Size', 'Venue')
        self.prints_tree = ttk.Treeview(prints_frame, columns=prints_columns, show='headings', height=5)
        for col in prints_columns:
            self.prints_tree.heading(col, text=col)
            self.prints_tree.column(col, width=150)
        self.prints_tree.pack(fill='x')
    
    def update_orderbook(self):
        """OrderBook verilerini güncelle"""
        try:
            # L2 data'yı al
            l2_data = self.hammer.get_l2_data(self.symbol)
            if l2_data:
                # Bids'i güncelle
                for item in self.bids_tree.get_children():
                    self.bids_tree.delete(item)
                
                for bid in l2_data.get('bids', [])[:7]:  # İlk 7 bid
                    self.bids_tree.insert('', 'end', values=(
                        f"{bid.get('price', 0):.4f}",
                        bid.get('size', 0),
                        bid.get('venue', 'N/A')
                    ))
                
                # Asks'i güncelle
                for item in self.asks_tree.get_children():
                    self.asks_tree.delete(item)
                
                for ask in l2_data.get('asks', [])[:7]:  # İlk 7 ask
                    self.asks_tree.insert('', 'end', values=(
                        f"{ask.get('price', 0):.4f}",
                        ask.get('size', 0),
                        ask.get('venue', 'N/A')
                    ))
                
                # Last prints'i güncelle
                for item in self.prints_tree.get_children():
                    self.prints_tree.delete(item)
                
                prints = l2_data.get('last_prints', [])[-10:]
                # Eğer prints sayısı az ise son tickleri çekmeyi tetikle
                if len(prints) < 10 and hasattr(self.hammer, '_send_command'):
                    try:
                        # Son birkaç tick'i iste (L1 üzerinden backfilled pseudo olabilir)
                        self.hammer._send_command({
                            'cmd': 'getTicks',
                            'sym': self.symbol.replace(' PR', '-'),
                            'lastFew': 10
                        })
                    except Exception:
                        pass
                for print_data in prints:  # Son 10 print
                    self.prints_tree.insert('', 0, values=(
                        print_data.get('time', 'N/A'),
                        f"{print_data.get('price', 0):.4f}",
                        print_data.get('size', 0),
                        print_data.get('venue', 'N/A')
                    ))
        
        except Exception as e:
            print(f"OrderBook güncelleme hatası: {e}")
        
        # Her 1 saniyede bir güncelle
        self.window.after(1000, self.update_orderbook)
    
    def place_order(self, order_type):
        """OrderBook penceresinden emir gönder"""
        try:
            lot_size = int(self.lot_entry.get())
        except ValueError:
            print("❌ Geçersiz lot değeri!")
            return
        
        try:
            # Market data'dan değerleri al
            market_data = self.hammer.get_market_data(self.symbol)
            if not market_data:
                print(f"⚠️ {self.symbol} için market data bulunamadı")
                return
            
            bid = float(market_data.get('bid', 0))
            ask = float(market_data.get('ask', 0))
            last = float(market_data.get('last', 0))
            spread = ask - bid
            
            # Emir fiyatını hesapla
            if order_type == 'bid_buy':
                price = bid + (spread * 0.15)
                action = 'BUY'
            elif order_type == 'front_buy':
                price = last + 0.01
                action = 'BUY'
            elif order_type == 'ask_buy':
                price = ask + 0.01
                action = 'BUY'
            elif order_type == 'ask_sell':
                price = ask - (spread * 0.15)
                action = 'SELL'
            elif order_type == 'front_sell':
                price = last - 0.01
                action = 'SELL'
            elif order_type == 'bid_sell':
                price = bid - 0.01
                action = 'SELL'
            else:
                print(f"❌ Bilinmeyen emir tipi: {order_type}")
                return
            
            # Emir gönder (şimdilik sadece log)
            print(f"📤 {self.symbol} {action} {lot_size} lot @ {price:.4f} ({order_type})")
            
            # Gerçek emir gönderimi buraya gelecek
            # self.hammer.place_order(self.symbol, action, lot_size, price, hidden=True)
            
        except Exception as e:
            print(f"❌ {self.symbol} için emir gönderilirken hata: {e}") 