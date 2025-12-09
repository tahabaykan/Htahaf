"""
L-spread Panel - Spread >= 0.20 olan hisseleri gösterir
BBtot ve SAStot kolonları ile birlikte mini450 verilerini listeler
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import os

class LSpreadPanel:
    def __init__(self, parent):
        self.parent = parent
        
        # Pencere oluştur
        self.win = tk.Toplevel(parent)
        self.win.title("L-spread - Spread >= 0.20")
        self.win.geometry("1400x800")
        self.win.configure(bg='white')
        
        # Veri depolama
        self.data = None
        self.filtered_data = None

        self.selected_items = set()
        self.lot_settings = {}  # Symbol -> lot miktarı mapping
        self.update_timer = None  # Otomatik güncelleme timer'ı
        
        # UI oluştur
        self.setup_ui()
        
        # Veriyi yükle
        self.load_data()
        
        # Otomatik güncelleme başlat
        self.start_auto_update()
        
        # Pencereyi göster
        self.win.focus()
        
        # Pencere kapatıldığında cleanup yap
        self.win.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def setup_ui(self):
        """UI bileşenlerini oluştur"""
        # Başlık
        title_label = ttk.Label(self.win, text="L-spread - Spread >= 0.20 Cent", 
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=5)
        
        # Üst panel - Butonlar
        top_frame = ttk.Frame(self.win)
        top_frame.pack(fill='x', padx=5, pady=5)
        
        # Yenile butonu
        self.btn_refresh = ttk.Button(top_frame, text="Yenile", width=10,
                                     command=self.refresh_data)
        self.btn_refresh.pack(side='left', padx=2)
        
        # Filtreleme bilgisi
        self.filter_info = ttk.Label(top_frame, text="Filtreleme: Spread >= 0.20")
        self.filter_info.pack(side='left', padx=10)
        
        # Buton frame'i oluştur (tablo öncesi)
        self.setup_buttons()
        
        # Ana frame
        self.main_frame = ttk.Frame(self.win)
        self.main_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Tablo oluştur
        self.setup_table()
    
    def setup_table(self):
        """Tablo oluştur"""
        # Kolonlar - seçim kutucuğu ve ucuzluk skorları ekle
        cols = ['select', 'PREF_IBKR', 'prev_close', 'FINAL_THG', 'BBtot', 'SAStot', 
                'Last', 'bid', 'ask', 'spread', 'bid_buy_ucuzluk', 'ask_sell_ucuzluk', 
                'SMI', 'MAXALW', 'Lot', 'SMA63_chg']
        headers = ['✓', 'PREF IBKR', 'Prev Close', 'FINAL THG', 'BBtot', 'SAStot', 
                   'Last', 'Bid', 'Ask', 'Spread', 'Bid Buy Ucuzluk', 'Ask Sell Ucuzluk',
                   'SMI', 'MAXALW', 'Lot', 'SMA63 Chg']
        
        # Treeview oluştur
        self.tree = ttk.Treeview(self.main_frame, columns=cols, show='headings', height=25)
        
        # Kolon başlıkları ve sıralama özelliği
        for col, header in zip(cols, headers):
            if col == 'select':
                self.tree.heading(col, text=header, command=lambda: self.toggle_all_selection())
            else:
                self.tree.heading(col, text=header, command=lambda c=col: self.sort_column(c))
        
        # Kolon genişlikleri (küçük font için optimize edilmiş)
        self.tree.column('select', width=30, anchor='center')
        self.tree.column('PREF_IBKR', width=80, anchor='center')
        self.tree.column('prev_close', width=70, anchor='center')
        self.tree.column('FINAL_THG', width=70, anchor='center')
        self.tree.column('BBtot', width=60, anchor='center')
        self.tree.column('SAStot', width=60, anchor='center')
        self.tree.column('Last', width=60, anchor='center')
        self.tree.column('bid', width=60, anchor='center')
        self.tree.column('ask', width=60, anchor='center')
        self.tree.column('spread', width=60, anchor='center')
        self.tree.column('bid_buy_ucuzluk', width=80, anchor='center')
        self.tree.column('ask_sell_ucuzluk', width=80, anchor='center')
        self.tree.column('SMI', width=50, anchor='center')
        self.tree.column('MAXALW', width=60, anchor='center')
        self.tree.column('Lot', width=60, anchor='center')
        self.tree.column('SMA63_chg', width=70, anchor='center')
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.main_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # TAKE PROFIT PANEL'DEN KOPYA: Çalışan seçim sistemi
        self.tree.bind('<Button-1>', self.on_table_click)
        
        # Seçim durumu
        self.selected_items = set()
        
        # Lot yönetimi
        self.lot_settings = {}  # symbol -> lot_size
        
        # Sıralama durumu
        self.sort_column_name = None
        self.sort_reverse = False
    
    def setup_buttons(self):
        """Butonları oluştur"""
        # Buton frame'i
        button_frame = ttk.Frame(self.win)
        button_frame.pack(fill='x', padx=5, pady=5)
        
        # Sol taraf - Lot butonları
        lot_frame = ttk.LabelFrame(button_frame, text="Lot Ayarları")
        lot_frame.pack(side='left', padx=5)
        
        # MAXALW/4 Lot butonu
        self.btn_maxalw_lot = ttk.Button(lot_frame, text="MAXALW/4", command=self.set_maxalw_lot)
        self.btn_maxalw_lot.pack(side='left', padx=2)
        
        # Yüzdesel lot butonları
        self.btn_lot_25 = ttk.Button(lot_frame, text="%25", command=lambda: self.set_lot_percentage(25))
        self.btn_lot_25.pack(side='left', padx=2)
        
        self.btn_lot_50 = ttk.Button(lot_frame, text="%50", command=lambda: self.set_lot_percentage(50))
        self.btn_lot_50.pack(side='left', padx=2)
        
        self.btn_lot_75 = ttk.Button(lot_frame, text="%75", command=lambda: self.set_lot_percentage(75))
        self.btn_lot_75.pack(side='left', padx=2)
        
        self.btn_lot_100 = ttk.Button(lot_frame, text="%100", command=lambda: self.set_lot_percentage(100))
        self.btn_lot_100.pack(side='left', padx=2)
        
        # Sabit lot butonları
        self.btn_lot_200 = ttk.Button(lot_frame, text="200", command=self.test_200_lot)
        self.btn_lot_200.pack(side='left', padx=2)
        
        self.btn_lot_500 = ttk.Button(lot_frame, text="500", command=self.test_500_lot)
        self.btn_lot_500.pack(side='left', padx=2)
        
        self.btn_lot_1000 = ttk.Button(lot_frame, text="1000", command=self.test_1000_lot)
        self.btn_lot_1000.pack(side='left', padx=2)
        
        # Orta taraf - Seçim butonları
        select_frame = ttk.LabelFrame(button_frame, text="Seçim")
        select_frame.pack(side='left', padx=5)
        
        self.btn_select_all = ttk.Button(select_frame, text="Tümünü Seç", command=self.debug_select_all_stocks)
        self.btn_select_all.pack(side='left', padx=2)
        
        # Venue test butonu
        self.btn_venue_test = ttk.Button(select_frame, text="Venue Test", command=self.test_venue_extraction)
        self.btn_venue_test.pack(side='left', padx=2)
        
        self.btn_deselect_all = ttk.Button(select_frame, text="Tümünü Kaldır", command=self.deselect_all_stocks)
        self.btn_deselect_all.pack(side='left', padx=2)
        
        # Sağ taraf - İşlem butonları
        action_frame = ttk.LabelFrame(button_frame, text="İşlemler")
        action_frame.pack(side='right', padx=5)
        
        self.btn_bid_buy = ttk.Button(action_frame, text="Bid Buy", command=self.bid_buy)
        self.btn_bid_buy.pack(side='left', padx=2)
        
        self.btn_ask_sell = ttk.Button(action_frame, text="Ask Sell", command=self.ask_sell)
        self.btn_ask_sell.pack(side='left', padx=2)
        
        # LRPAN butonu
        self.btn_lrpan = ttk.Button(action_frame, text="LRPAN", command=self.analyze_last_real_prints)
        self.btn_lrpan.pack(side='left', padx=2)
    
    def sort_column(self, col):
        """Kolonu sırala"""
        try:
            # Aynı kolona tekrar tıklanırsa ters çevir
            if self.sort_column_name == col:
                self.sort_reverse = not self.sort_reverse
            else:
                self.sort_column_name = col
                self.sort_reverse = False
            
            # Veriyi sırala
            if self.filtered_data is not None and not self.filtered_data.empty:
                # Sayısal kolonlar için özel işlem
                if col in ['prev_close', 'FINAL_THG', 'spread', 'SMI', 'MAXALW', 'SMA63_chg']:
                    # Sayısal değerlere dönüştür
                    self.filtered_data[col] = pd.to_numeric(self.filtered_data[col], errors='coerce')
                    sorted_data = self.filtered_data.sort_values(col, ascending=not self.sort_reverse, na_position='last')
                else:
                    sorted_data = self.filtered_data.sort_values(col, ascending=not self.sort_reverse, na_position='last')
                
                self.filtered_data = sorted_data
                self.update_table()
                
                print(f"[L-SPREAD] ✅ {col} kolonu sıralandı ({'Azalan' if self.sort_reverse else 'Artan'})")
        except Exception as e:
            print(f"[L-SPREAD] ❌ Sıralama hatası: {e}")
    
    def set_maxalw_lot(self):
        """MAXALW lot ayarla - Düzgün yuvarlama ile"""
        try:
            if not self.selected_items:
                messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
                return
            
            print(f"[L-SPREAD] 🔄 {len(self.selected_items)} hisse için MAXALW lot hesaplanıyor...")
            print(f"[L-SPREAD DEBUG] 🔍 selected_items: {self.selected_items}")
            
            # Seçili hisseler için MAXALW lot hesapla
            for symbol in self.selected_items:
                # Hisse verilerini al
                row_data = self.filtered_data[self.filtered_data['PREF IBKR'] == symbol]
                if not row_data.empty:
                    row = row_data.iloc[0]
                    maxalw = row.get('MAXALW', 0)
                    
                    # MAXALW değerinin 1/4'ünü al ve 100'e yuvarla
                    if maxalw > 0:
                        # MAXALW'nin 1/4'ünü al
                        quarter_maxalw = maxalw / 4
                        # 100'e yuvarla
                        lot = round(quarter_maxalw / 100) * 100
                        if lot < 100:  # Minimum 100 lot
                            lot = 100
                        print(f"[L-SPREAD MAXALW] 🔍 {symbol}: MAXALW={maxalw:.1f} → 1/4={quarter_maxalw:.1f} → Lot={lot}")
                    else:
                        lot = 100  # Varsayılan 100 lot
                        print(f"[L-SPREAD MAXALW] ⚠️ {symbol}: MAXALW=0 → Lot=100 (varsayılan)")
                    
                    # Lot ayarını kaydet
                    self.lot_settings[symbol] = lot
                    print(f"[L-SPREAD] ✅ {symbol}: MAXALW={maxalw:.0f} → Lot={lot}")
                    print(f"[L-SPREAD DEBUG] 📝 lot_settings güncellendi: {self.lot_settings}")
                else:
                    print(f"[L-SPREAD] ⚠️ {symbol}: Veri bulunamadı")
            
            messagebox.showinfo("Başarılı", f"{len(self.selected_items)} hisse için MAXALW lot ayarlandı!")
            
            # Tabloyu güncelle
            self.update_table()
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ MAXALW lot ayarlama hatası: {e}")
            messagebox.showerror("Hata", f"MAXALW lot ayarlama hatası: {e}")
    
    def set_fixed_lot(self, lot):
        """Sabit lot ayarla"""
        try:
            print(f"[L-SPREAD DEBUG] 🚀 set_fixed_lot çağrıldı: lot={lot}")
            print(f"[L-SPREAD DEBUG] 🔍 selected_items boyutu: {len(self.selected_items)}")
            print(f"[L-SPREAD DEBUG] 🔍 selected_items içeriği: {self.selected_items}")
            
            if not self.selected_items:
                print(f"[L-SPREAD DEBUG] ⚠️ selected_items boş!")
                messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
                return
            
            print(f"[L-SPREAD] 🔄 {len(self.selected_items)} hisse için sabit lot: {lot}")
            print(f"[L-SPREAD DEBUG] 🔍 selected_items: {self.selected_items}")
            
            # Seçili hisseler için sabit lot ayarla
            for symbol in self.selected_items:
                # Lot ayarını kaydet
                self.lot_settings[symbol] = lot
                print(f"[L-SPREAD] ✅ {symbol}: Sabit lot = {lot}")
                print(f"[L-SPREAD DEBUG] 📝 lot_settings güncellendi: {self.lot_settings}")
            
            messagebox.showinfo("Başarılı", f"{len(self.selected_items)} hisse için sabit lot: {lot}")
            
            # Tabloyu güncelle
            self.update_table()
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Sabit lot ayarlama hatası: {e}")
            messagebox.showerror("Hata", f"Sabit lot ayarlama hatası: {e}")
    
    def debug_set_fixed_lot(self, lot):
        """Debug wrapper for set_fixed_lot"""
        print(f"[L-SPREAD DEBUG] 🔘 Lot butonu tıklandı: {lot}")
        print(f"[L-SPREAD DEBUG] 🔍 Mevcut selected_items: {self.selected_items}")
        print(f"[L-SPREAD DEBUG] 🔍 Mevcut lot_settings: {self.lot_settings}")
        
        # set_fixed_lot'u çağır
        self.set_fixed_lot(lot)
    
    def test_200_lot(self):
        """Test 200 lot butonu"""
        print(f"[L-SPREAD TEST] 🔘 200 LOT BUTONU TIKLANDI!")
        print(f"[L-SPREAD TEST] 🔍 selected_items: {self.selected_items}")
        print(f"[L-SPREAD TEST] 🔍 lot_settings: {self.lot_settings}")
        
        if not self.selected_items:
            print(f"[L-SPREAD TEST] ⚠️ HİÇ HİSSE SEÇİLMEMİŞ!")
            messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
            return
        
        # Manuel lot ayarla
        for symbol in self.selected_items:
            self.lot_settings[symbol] = 200
            print(f"[L-SPREAD TEST] ✅ {symbol} → 200 lot ayarlandı")
        
        print(f"[L-SPREAD TEST] 📝 Güncel lot_settings: {self.lot_settings}")
        messagebox.showinfo("Başarılı", f"{len(self.selected_items)} hisse için 200 lot ayarlandı!")
        self.update_table()
    
    def test_500_lot(self):
        """Test 500 lot butonu"""
        print(f"[L-SPREAD TEST] 🔘 500 LOT BUTONU TIKLANDI!")
        print(f"[L-SPREAD TEST] 🔍 selected_items: {self.selected_items}")
        print(f"[L-SPREAD TEST] 🔍 lot_settings: {self.lot_settings}")
        
        if not self.selected_items:
            print(f"[L-SPREAD TEST] ⚠️ HİÇ HİSSE SEÇİLMEMİŞ!")
            messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
            return
        
        # Manuel lot ayarla
        for symbol in self.selected_items:
            self.lot_settings[symbol] = 500
            print(f"[L-SPREAD TEST] ✅ {symbol} → 500 lot ayarlandı")
        
        print(f"[L-SPREAD TEST] 📝 Güncel lot_settings: {self.lot_settings}")
        messagebox.showinfo("Başarılı", f"{len(self.selected_items)} hisse için 500 lot ayarlandı!")
        self.update_table()
    
    def test_1000_lot(self):
        """Test 1000 lot butonu"""
        print(f"[L-SPREAD TEST] 🔘 1000 LOT BUTONU TIKLANDI!")
        print(f"[L-SPREAD TEST] 🔍 selected_items: {self.selected_items}")
        print(f"[L-SPREAD TEST] 🔍 lot_settings: {self.lot_settings}")
        
        if not self.selected_items:
            print(f"[L-SPREAD TEST] ⚠️ HİÇ HİSSE SEÇİLMEMİŞ!")
            messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
            return
        
        # Manuel lot ayarla
        for symbol in self.selected_items:
            self.lot_settings[symbol] = 1000
            print(f"[L-SPREAD TEST] ✅ {symbol} → 1000 lot ayarlandı")
        
        print(f"[L-SPREAD TEST] 📝 Güncel lot_settings: {self.lot_settings}")
        messagebox.showinfo("Başarılı", f"{len(self.selected_items)} hisse için 1000 lot ayarlandı!")
        self.update_table()
    
    def debug_select_all_stocks(self):
        """Debug wrapper for select_all_stocks"""
        print(f"[L-SPREAD DEBUG] 🔘 Tümünü Seç butonu tıklandı")
        print(f"[L-SPREAD DEBUG] 🔍 Mevcut selected_items: {self.selected_items}")
        
        # select_all_stocks'u çağır
        self.select_all_stocks()
    
    def select_all(self):
        """Tüm hisseleri seç"""
        try:
            for item in self.tree.get_children():
                self.tree.selection_add(item)
            print("[L-SPREAD] ✅ Tüm hisseler seçildi")
        except Exception as e:
            print(f"[L-SPREAD] ❌ Tümünü seçme hatası: {e}")
    
    def deselect_all(self):
        """Tüm seçimleri kaldır"""
        try:
            self.tree.selection_remove(self.tree.selection())
            print("[L-SPREAD] ✅ Tüm seçimler kaldırıldı")
        except Exception as e:
            print(f"[L-SPREAD] ❌ Seçimleri kaldırma hatası: {e}")
    
    def bid_buy(self):
        """Bid Buy işlemi"""
        try:
            # Seçili hisseleri kontrol et
            if not self.selected_items:
                messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi! Lütfen önce hisseleri seçin.")
                return
            
            # Onay penceresi göster
            self.show_order_confirmation("Bid Buy", "bid_buy")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Bid Buy hatası: {e}")
            messagebox.showerror("Hata", f"Bid Buy hatası: {e}")
    
    def ask_sell(self):
        """Ask Sell işlemi"""
        try:
            # Seçili hisseleri kontrol et
            if not self.selected_items:
                messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi! Lütfen önce hisseleri seçin.")
                return
            
            # Onay penceresi göster
            self.show_order_confirmation("Ask Sell", "ask_sell")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Ask Sell hatası: {e}")
            messagebox.showerror("Hata", f"Ask Sell hatası: {e}")
    
    def load_data(self):
        """mini450 verilerini live dataframe'den yükle"""
        try:
            # DEBUG: Sistem durumunu kontrol et
            print(f"\n[L-SPREAD DEBUG] 🔍 Sistem durumu kontrol ediliyor...")
            print(f"[L-SPREAD DEBUG] 📡 Parent hammer var mı: {hasattr(self.parent, 'hammer')}")
            
            if hasattr(self.parent, 'hammer'):
                print(f"[L-SPREAD DEBUG] 🔗 Hammer Pro bağlı mı: {self.parent.hammer.connected}")
                print(f"[L-SPREAD DEBUG] 🔐 Hammer Pro authenticated mı: {self.parent.hammer.authenticated}")
                print(f"[L-SPREAD DEBUG] 📊 Market data cache boyutu: {len(self.parent.hammer.market_data)}")
                
                # Live data durumunu kontrol et
                if hasattr(self.parent, 'live_data_running'):
                    print(f"[L-SPREAD DEBUG] 🔴 Live data çalışıyor mu: {self.parent.live_data_running}")
                else:
                    print(f"[L-SPREAD DEBUG] ⚠️ Live data durumu bilinmiyor")
                    
                # Preferred tickers durumunu kontrol et
                if hasattr(self.parent, 'preferred_tickers'):
                    print(f"[L-SPREAD DEBUG] 📋 Preferred tickers: {len(self.parent.preferred_tickers)} adet")
                else:
                    print(f"[L-SPREAD DEBUG] ⚠️ Preferred tickers bulunamadı")
            else:
                print(f"[L-SPREAD DEBUG] ❌ Hammer Pro client bulunamadı!")
            
            # Parent'tan live DataFrame'i al (Take Profit paneli gibi)
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                self.data = self.parent.df.copy()
                print(f"[L-SPREAD] ✅ Live DataFrame yüklendi: {len(self.data)} satır")
                print(f"[L-SPREAD] 📊 Mevcut kolonlar: {list(self.data.columns)}")
                
                # Bid ve Ask kolonlarını kontrol et
                bid_cols = [col for col in self.data.columns if 'bid' in col.lower()]
                ask_cols = [col for col in self.data.columns if 'ask' in col.lower()]
                print(f"[L-SPREAD] 🔍 Bid kolonları: {bid_cols}")
                print(f"[L-SPREAD] 🔍 Ask kolonları: {ask_cols}")
                
                # İlk satırın Bid ve Ask değerlerini kontrol et
                if not self.data.empty:
                    first_row = self.data.iloc[0]
                    print(f"[L-SPREAD] 🔍 İlk satır Bid değeri: {first_row.get('Bid', 'KOLON YOK')}")
                    print(f"[L-SPREAD] 🔍 İlk satır Ask değeri: {first_row.get('Ask', 'KOLON YOK')}")
                    
                    # Alternatif kolonları kontrol et
                    print(f"[L-SPREAD] 🔍 İlk satır Bid_buy_ucuzluk_skoru: {first_row.get('Bid_buy_ucuzluk_skoru', 'KOLON YOK')}")
                    print(f"[L-SPREAD] 🔍 İlk satır Ask_buy_ucuzluk_skoru: {first_row.get('Ask_buy_ucuzluk_skoru', 'KOLON YOK')}")
                    
                    # Gerçek fiyat kolonlarını ara
                    price_cols = [col for col in self.data.columns if any(word in col.lower() for word in ['price', 'fiyat', 'last', 'close'])]
                    print(f"[L-SPREAD] 🔍 Fiyat kolonları: {price_cols}")
                    
                    # İlk satırın tüm değerlerini göster (debug için)
                    print(f"[L-SPREAD] 🔍 İlk satır tüm değerler:")
                    for col in self.data.columns:
                        if 'bid' in col.lower() or 'ask' in col.lower() or 'price' in col.lower():
                            print(f"    {col}: {first_row.get(col, 'N/A')}")
                    
                    # İlk 3 satırın Bid/Ask değerlerini göster
                    print(f"[L-SPREAD] 🔍 İlk 3 satır Bid/Ask değerleri:")
                    for i in range(min(3, len(self.data))):
                        row = self.data.iloc[i]
                        symbol = row.get('PREF IBKR', 'N/A')
                        bid_val = row.get('Bid', 'N/A')
                        ask_val = row.get('Ask', 'N/A')
                        print(f"    {symbol}: Bid={bid_val}, Ask={ask_val}")
                
                # Veriyi filtrele ve göster
                self.filter_and_display_data()
            else:
                messagebox.showerror("Hata", "Live DataFrame bulunamadı. Mini450 aktif mi?")
                print(f"[L-SPREAD] ❌ Parent DataFrame bulunamadı")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Veri yükleme hatası: {e}")
            messagebox.showerror("Hata", f"Veri yükleme hatası: {e}")
    
    def filter_and_display_data(self):
        """Spread >= 0.20 olan hisseleri filtrele ve göster"""
        try:
            if self.data is None or self.data.empty:
                return
            
            # Spread kolonu zaten hesaplanmış, kontrol et ve sayısal yap
            if 'Spread' in self.data.columns:
                print(f"[L-SPREAD] ✅ Spread kolonu mevcut")
                # Spread kolonunu sayısal yap (string ise)
                self.data['Spread'] = pd.to_numeric(self.data['Spread'], errors='coerce').fillna(0)
            else:
                print(f"[L-SPREAD] ⚠️ Spread kolonu bulunamadı")
                self.data['Spread'] = 0
            
            # MAXALW hesapla (AVG_ADV/10)
            if 'AVG_ADV' in self.data.columns:
                self.data['MAXALW'] = self.data['AVG_ADV'] / 10
            else:
                self.data['MAXALW'] = 0
            
            # Spread >= 0.20 olan hisseleri filtrele
            self.filtered_data = self.data[self.data['Spread'] >= 0.20].copy()
            
            print(f"[L-SPREAD] 📊 Filtrelenmiş veri: {len(self.filtered_data)} hisse (spread >= 0.20)")
            
            # BBtot ve SAStot hesapla
            self.calculate_bbtot_sastot()
            
            # Tabloyu güncelle
            self.update_table()
            
            # Filtreleme bilgisini güncelle
            self.filter_info.config(text=f"Filtreleme: Spread >= 0.20 ({len(self.filtered_data)} hisse)")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Filtreleme hatası: {e}")
            messagebox.showerror("Hata", f"Filtreleme hatası: {e}")
    
    def calculate_bbtot_sastot(self):
        """BBtot ve SAStot değerlerini hesapla"""
        try:
            if self.filtered_data is None or self.filtered_data.empty:
                return
            
            # BBtot hesapla (Final BB kullanarak)
            self.filtered_data['BBtot'] = self.filtered_data.apply(
                lambda row: self.calculate_bbtot_for_symbol(row['PREF IBKR']), axis=1
            )
            
            # SAStot hesapla (Final SAS kullanarak)
            self.filtered_data['SAStot'] = self.filtered_data.apply(
                lambda row: self.calculate_sastot_for_symbol(row['PREF IBKR']), axis=1
            )
            
            print(f"[L-SPREAD] ✅ BBtot ve SAStot hesaplandı")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ BBtot/SAStot hesaplama hatası: {e}")
    
    def calculate_bbtot_for_symbol(self, symbol):
        """Belirli bir hisse için BBtot hesapla"""
        try:
            # Final BB değerini al (bid buy için)
            final_bb = self.get_final_bb_from_dataframe(symbol)
            if final_bb == 0:
                return "N/A"
            
            # Grup bilgisini al
            group = self.get_group_from_dataframe(symbol)
            if not group or group == 'N/A':
                return "N/A"
            
            # Grup ortalama Final BB hesapla
            avg_final_bb = self.calculate_group_avg_final_bb(group)
            if avg_final_bb == 0:
                return "N/A"
            
            # BBPlagr hesapla (grup içi sıralama)
            bbplagr = self.calculate_bbplagr(symbol, group)
            
            # BBRatgr hesapla (Final BB / Grup Average)
            bbratgr = self.calculate_bbratgr(symbol, final_bb, avg_final_bb)
            
            # BBtot = BBPlagr + BBRatgr
            bbplagr_value = self.extract_decimal_from_bbplagr(bbplagr)
            bbratgr_value = self.extract_decimal_from_bbratgr(bbratgr)
            
            total = bbplagr_value + bbratgr_value
            return f"{total:.2f}"
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ {symbol} BBtot hesaplama hatası: {e}")
            return "N/A"
    
    def calculate_sastot_for_symbol(self, symbol):
        """Belirli bir hisse için SAStot hesapla"""
        try:
            # Final SAS değerini al (short ask sell için)
            final_sas = self.get_final_sas_from_dataframe(symbol)
            if final_sas == 0:
                return "N/A"
            
            # Grup bilgisini al
            group = self.get_group_from_dataframe(symbol)
            if not group or group == 'N/A':
                return "N/A"
            
            # Grup ortalama Final SAS hesapla
            avg_final_sas = self.calculate_group_avg_final_sas(group)
            if avg_final_sas == 0:
                return "N/A"
            
            # SASPlagr hesapla (grup içi sıralama)
            sasplagr = self.calculate_sasplagr(symbol, group)
            
            # SASRatgr hesapla (Final SAS / Grup Average)
            sasratgr = self.calculate_sasratgr(symbol, final_sas, avg_final_sas)
            
            # SAStot = SASPlagr + SASRatgr
            sasplagr_value = self.extract_decimal_from_sasplagr(sasplagr)
            sasratgr_value = self.extract_decimal_from_sasratgr(sasratgr)
            
            total = sasplagr_value + sasratgr_value
            return f"{total:.2f}"
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ {symbol} SAStot hesaplama hatası: {e}")
            return "N/A"
    
    def get_final_bb_from_dataframe(self, symbol):
        """Live DataFrame'den Final BB değerini al"""
        try:
            # Parent'tan live DataFrame'i al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                row = self.parent.df[self.parent.df['PREF IBKR'] == symbol]
                if not row.empty:
                    # Final_BB_skor kolonunu kontrol et
                    if 'Final_BB_skor' in self.parent.df.columns:
                        value = row['Final_BB_skor'].iloc[0]
                        if pd.notna(value) and value != 'N/A':
                            return float(value)
            return 0
        except Exception as e:
            print(f"[L-SPREAD] ❌ {symbol} Final BB alma hatası: {e}")
            return 0
    
    def get_final_sas_from_dataframe(self, symbol):
        """Live DataFrame'den Final SAS değerini al"""
        try:
            # Parent'tan live DataFrame'i al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                row = self.parent.df[self.parent.df['PREF IBKR'] == symbol]
                if not row.empty:
                    # Final_SAS_skor kolonunu kontrol et
                    if 'Final_SAS_skor' in self.parent.df.columns:
                        value = row['Final_SAS_skor'].iloc[0]
                        if pd.notna(value) and value != 'N/A':
                            return float(value)
            return 0
        except Exception as e:
            print(f"[L-SPREAD] ❌ {symbol} Final SAS alma hatası: {e}")
            return 0
    
    def get_group_from_dataframe(self, symbol):
        """Live DataFrame'den grup bilgisini al - Take Profit mantığıyla"""
        try:
            # Grup dosya eşleşmesi - Take Profit ile aynı
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
                            print(f"[L-SPREAD] 🎯 {symbol} -> {group} grubunda bulundu (tam eşleşme)")
                            return group
                        
                        # Esnek eşleşme kontrol et (büyük/küçük harf, boşluk vs.)
                        symbol_upper = symbol.upper().strip()
                        for group_symbol in group_symbols:
                            if group_symbol and isinstance(group_symbol, str):
                                group_symbol_upper = group_symbol.upper().strip()
                                if symbol_upper == group_symbol_upper:
                                    print(f"[L-SPREAD] 🎯 {symbol} -> {group} grubunda bulundu (esnek eşleşme)")
                                    return group
                        
                    except Exception as e:
                        print(f"[L-SPREAD] ⚠️ {file_name} okuma hatası: {e}")
                        continue
                else:
                    print(f"[L-SPREAD] ⚠️ {file_name} dosyası bulunamadı")
            
            print(f"[L-SPREAD] ⚠️ {symbol} hiçbir grup dosyasında bulunamadı")
            return "N/A"
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ {symbol} grup bulma hatası: {e}")
            return "N/A"
    
    def calculate_group_avg_final_bb(self, group):
        """Grup için ortalama Final BB hesapla - Take Profit mantığıyla"""
        try:
            # Grup dosya eşleşmesi - Take Profit ile aynı
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
            
            # Parent DataFrame'den bu gruba ait hisselerin Final BB değerlerini al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                group_rows = self.parent.df[self.parent.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_BB_skor' in self.parent.df.columns:
                    # N/A ve 0 değerleri filtrele - Take Profit mantığıyla
                    final_bb_values = group_rows['Final_BB_skor'].dropna()
                    # String değerleri sayıya çevir
                    final_bb_values = pd.to_numeric(final_bb_values, errors='coerce').dropna()
                    final_bb_values = final_bb_values[final_bb_values > 0]  # 0'dan büyük olanları al
                    if not final_bb_values.empty:
                        avg_fb = final_bb_values.mean()
                        print(f"[L-SPREAD] 📊 {group} grubu ortalama Final BB: {avg_fb:.2f} ({len(final_bb_values)} geçerli hisse)")
                        return avg_fb
            
            return 0
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ {group} grup ortalama Final BB hesaplama hatası: {e}")
            return 0
    
    def calculate_group_avg_final_sas(self, group):
        """Grup için ortalama Final SAS hesapla - Take Profit mantığıyla"""
        try:
            # Grup dosya eşleşmesi - Take Profit ile aynı
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
            
            # Parent DataFrame'den bu gruba ait hisselerin Final SAS değerlerini al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                group_rows = self.parent.df[self.parent.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_SAS_skor' in self.parent.df.columns:
                    # N/A ve 0 değerleri filtrele - Take Profit mantığıyla
                    final_sas_values = group_rows['Final_SAS_skor'].dropna()
                    # String değerleri sayıya çevir
                    final_sas_values = pd.to_numeric(final_sas_values, errors='coerce').dropna()
                    final_sas_values = final_sas_values[final_sas_values > 0]  # 0'dan büyük olanları al
                    if not final_sas_values.empty:
                        avg_sas = final_sas_values.mean()
                        print(f"[L-SPREAD] 📊 {group} grubu ortalama Final SAS: {avg_sas:.2f} ({len(final_sas_values)} geçerli hisse)")
                        return avg_sas
            
            return 0
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ {group} grup ortalama Final SAS hesaplama hatası: {e}")
            return 0
    
    def calculate_bbplagr(self, symbol, group):
        """BBPlagr hesapla (grup içi Final BB sıralaması) - Take Profit mantığıyla"""
        try:
            if not group or group == 'N/A':
                return "N/A"
            
            # Grup dosya eşleşmesi - Take Profit ile aynı
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
            
            # Parent DataFrame'den bu gruba ait hisselerin Final BB değerlerini al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                group_rows = self.parent.df[self.parent.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_BB_skor' in self.parent.df.columns:
                    # N/A ve 0 değerleri filtrele - Take Profit mantığıyla
                    final_bb_data = group_rows[['PREF IBKR', 'Final_BB_skor']].dropna()
                    # String değerleri sayıya çevir
                    final_bb_data['Final_BB_skor'] = pd.to_numeric(final_bb_data['Final_BB_skor'], errors='coerce')
                    final_bb_data = final_bb_data.dropna()
                    final_bb_data = final_bb_data[final_bb_data['Final_BB_skor'] > 0]
                    
                    if not final_bb_data.empty:
                        # Final BB'ye göre sırala (en düşükten en yükseğe - tersine çevir)
                        final_bb_data = final_bb_data.sort_values('Final_BB_skor', ascending=True).reset_index(drop=True)
                        
                        # Symbol'ün sırasını bul
                        symbol_row = final_bb_data[final_bb_data['PREF IBKR'] == symbol]
                        if not symbol_row.empty:
                            rank = symbol_row.index[0] + 1  # 1'den başla
                            total_count = len(final_bb_data)
                            # Hem kesir hem de ondalık format göster
                            decimal_ratio = rank / total_count
                            result = f"{rank}/{total_count} ({decimal_ratio:.2f})"
                            print(f"[L-SPREAD] 📊 {symbol} BBPlagr: {result} (Final BB: {symbol_row.iloc[0]['Final_BB_skor']:.2f})")
                            return result
            
            return "N/A"
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ {symbol} BBPlagr hesaplama hatası: {e}")
            return "N/A"
    
    def calculate_sasplagr(self, symbol, group):
        """SASPlagr hesapla (grup içi Final SAS sıralaması) - Take Profit mantığıyla"""
        try:
            if not group or group == 'N/A':
                return "N/A"
            
            # Grup dosya eşleşmesi - Take Profit ile aynı
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
            
            # Parent DataFrame'den bu gruba ait hisselerin Final SAS değerlerini al
            if hasattr(self.parent, 'df') and not self.parent.df.empty:
                group_rows = self.parent.df[self.parent.df['PREF IBKR'].isin(group_symbols)]
                if not group_rows.empty and 'Final_SAS_skor' in self.parent.df.columns:
                    # N/A ve 0 değerleri filtrele - Take Profit mantığıyla
                    final_sas_data = group_rows[['PREF IBKR', 'Final_SAS_skor']].dropna()
                    # String değerleri sayıya çevir
                    final_sas_data['Final_SAS_skor'] = pd.to_numeric(final_sas_data['Final_SAS_skor'], errors='coerce')
                    final_sas_data = final_sas_data.dropna()
                    final_sas_data = final_sas_data[final_sas_data['Final_SAS_skor'] > 0]
                    
                    if not final_sas_data.empty:
                        # Final SAS'a göre sırala (en düşükten en yükseğe - tersine çevir)
                        final_sas_data = final_sas_data.sort_values('Final_SAS_skor', ascending=True).reset_index(drop=True)
                        
                        # Symbol'ün sırasını bul
                        symbol_row = final_sas_data[final_sas_data['PREF IBKR'] == symbol]
                        if not symbol_row.empty:
                            rank = symbol_row.index[0] + 1  # 1'den başla
                            total_count = len(final_sas_data)
                            # Hem kesir hem de ondalık format göster
                            decimal_ratio = rank / total_count
                            result = f"{rank}/{total_count} ({decimal_ratio:.2f})"
                            print(f"[L-SPREAD] 📊 {symbol} SASPlagr: {result} (Final SAS: {symbol_row.iloc[0]['Final_SAS_skor']:.2f})")
                            return result
            
            return "N/A"
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ {symbol} SASPlagr hesaplama hatası: {e}")
            return "N/A"
    
    def calculate_bbratgr(self, symbol, final_bb, avg_final_bb):
        """BBRatgr hesapla (Final BB / Grup Average)"""
        try:
            if avg_final_bb == 0 or final_bb <= 0:
                return "N/A"
            
            ratio = final_bb / avg_final_bb
            return f"{ratio:.2f}"
        except Exception as e:
            print(f"[L-SPREAD] ❌ {symbol} BBRatgr hesaplama hatası: {e}")
            return "N/A"
    
    def calculate_sasratgr(self, symbol, final_sas, avg_final_sas):
        """SASRatgr hesapla (Final SAS / Grup Average)"""
        try:
            if avg_final_sas == 0 or final_sas <= 0:
                return "N/A"
            
            ratio = final_sas / avg_final_sas
            return f"{ratio:.2f}"
        except Exception as e:
            print(f"[L-SPREAD] ❌ {symbol} SASRatgr hesaplama hatası: {e}")
            return "N/A"
    
    def extract_decimal_from_bbplagr(self, bbplagr):
        """BBPlagr'dan ondalık değeri çıkar"""
        try:
            if bbplagr != "N/A" and "(" in bbplagr:
                decimal_part = bbplagr.split("(")[1].split(")")[0]
                return float(decimal_part)
            return 0
        except:
            return 0
    
    def extract_decimal_from_bbratgr(self, bbratgr):
        """BBRatgr'dan sayısal değeri çıkar"""
        try:
            if bbratgr != "N/A":
                return float(bbratgr)
            return 0
        except:
            return 0
    
    def extract_decimal_from_sasplagr(self, sasplagr):
        """SASPlagr'dan ondalık değeri çıkar"""
        try:
            if sasplagr != "N/A" and "(" in sasplagr:
                decimal_part = sasplagr.split("(")[1].split(")")[0]
                return float(decimal_part)
            return 0
        except:
            return 0
    
    def extract_decimal_from_sasratgr(self, sasratgr):
        """SASRatgr'dan sayısal değeri çıkar"""
        try:
            if sasratgr != "N/A":
                return float(sasratgr)
            return 0
        except:
            return 0
    
    def update_table(self):
        """Tabloyu güncelle"""
        try:
            # Mevcut verileri temizle
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            if self.filtered_data is None or self.filtered_data.empty:
                return
            
            # Verileri tabloya ekle - seçim kutucuğu ile
            for _, row in self.filtered_data.iterrows():
                symbol = row.get('PREF IBKR', 'N/A')
                is_selected = symbol in self.selected_items
                
                # LIVE MARKET DATA ÇEK - Mini450 ile aynı yöntem
                bid_display = "N/A"
                ask_display = "N/A"
                last_display = "N/A"
                
                if hasattr(self.parent, 'hammer') and self.parent.hammer and self.parent.hammer.connected:
                    market_data = self.parent.hammer.get_market_data(symbol)
                    if market_data:
                        bid_raw = market_data.get('bid', 0)
                        ask_raw = market_data.get('ask', 0)
                        last_raw = market_data.get('last', 0)
                        
                        bid_display = f"${bid_raw:.2f}" if bid_raw > 0 else "N/A"
                        ask_display = f"${ask_raw:.2f}" if ask_raw > 0 else "N/A"
                        last_display = f"${last_raw:.2f}" if last_raw > 0 else "N/A"
                        
                        # print(f"[L-SPREAD LIVE] ✅ {symbol}: Bid={bid_display}, Ask={ask_display}, Last={last_display}")
                    else:
                        # print(f"[L-SPREAD LIVE] ⚠️ {symbol}: Market data bulunamadı")
                        pass
                else:
                    # print(f"[L-SPREAD LIVE] ⚠️ {symbol}: Hammer Pro bağlı değil")
                    pass
                
                # Lot değerini al
                lot_value = self.lot_settings.get(symbol, row.get('MAXALW', 0))
                lot_display = f"{lot_value:.0f}" if lot_value > 0 else "N/A"
                
                values = [
                    "☑" if is_selected else "☐",  # Seçim kutucuğu
                    symbol,
                    f"${row.get('prev_close', 0):.2f}" if row.get('prev_close', 0) > 0 else "N/A",
                    f"${row.get('FINAL_THG', 0):.2f}" if row.get('FINAL_THG', 0) > 0 else "N/A",
                    row.get('BBtot', 'N/A'),
                    row.get('SAStot', 'N/A'),
                    last_display,  # Live Last Price
                    bid_display,   # Live Bid
                    ask_display,   # Live Ask
                    f"${row.get('Spread', 0):.2f}" if row.get('Spread', 0) > 0 else "N/A",
                    f"{row.get('Bid_buy_ucuzluk_skoru', 0):.2f}" if row.get('Bid_buy_ucuzluk_skoru', 0) != 0 else "N/A",  # Bid Buy Ucuzluk
                    f"{row.get('Ask_sell_pahalilik_skoru', 0):.2f}" if row.get('Ask_sell_pahalilik_skoru', 0) != 0 else "N/A",  # Ask Sell Ucuzluk
                    f"{row.get('SMI', 0):.2f}" if row.get('SMI', 0) > 0 else "N/A",
                    f"{row.get('MAXALW', 0):.2f}" if row.get('MAXALW', 0) > 0 else "N/A",
                    lot_display,  # Lot değeri
                    f"{row.get('SMA63 chg', 0):.2f}%" if row.get('SMA63 chg', 0) != 0 else "N/A"
                ]
                
                item = self.tree.insert('', 'end', values=values)
                # Symbol'ü item'a tag olarak ekle
                self.tree.set(item, 'PREF_IBKR', symbol)
            
            print(f"[L-SPREAD] ✅ Tablo güncellendi: {len(self.filtered_data)} satır")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Tablo güncelleme hatası: {e}")
    
    def start_auto_update(self):
        """Otomatik güncelleme başlat - Mini450 ile aynı mantık"""
        try:
            print("[L-SPREAD] 🔄 Otomatik güncelleme başlatılıyor...")
            self.update_timer = self.win.after(2000, self.auto_update_loop)  # 2 saniyede bir güncelle
        except Exception as e:
            print(f"[L-SPREAD] ❌ Otomatik güncelleme başlatma hatası: {e}")
    
    def auto_update_loop(self):
        """Otomatik güncelleme döngüsü"""
        try:
            # Sadece pencere açıksa güncelle
            if self.win.winfo_exists():
                # Live market data ile tabloyu güncelle
                self.update_table()
                
                # Sonraki güncellemeyi planla
                self.update_timer = self.win.after(2000, self.auto_update_loop)
            else:
                print("[L-SPREAD] 🔌 Pencere kapatıldı, otomatik güncelleme durduruluyor...")
        except Exception as e:
            print(f"[L-SPREAD] ❌ Otomatik güncelleme hatası: {e}")
    
    def stop_auto_update(self):
        """Otomatik güncellemeyi durdur"""
        try:
            if self.update_timer:
                self.win.after_cancel(self.update_timer)
                self.update_timer = None
                print("[L-SPREAD] ⏹️ Otomatik güncelleme durduruldu")
        except Exception as e:
            print(f"[L-SPREAD] ❌ Otomatik güncelleme durdurma hatası: {e}")
    
    def on_closing(self):
        """Pencere kapatılırken cleanup yap"""
        try:
            print("[L-SPREAD] 🔌 Pencere kapatılıyor, cleanup yapılıyor...")
            self.stop_auto_update()
            self.win.destroy()
        except Exception as e:
            print(f"[L-SPREAD] ❌ Pencere kapatma hatası: {e}")
            self.win.destroy()
    
    def refresh_data(self):
        """Veriyi yenile"""
        self.load_data()
    
    def toggle_all_selection(self):
        """Tümünü seç/seçimi kaldır"""
        if len(self.selected_items) == len(self.filtered_data):
            # Tümünü kaldır
            self.selected_items.clear()
        else:
            # Tümünü seç
            for _, row in self.filtered_data.iterrows():
                symbol = row.get('PREF IBKR', 'N/A')
                if symbol != 'N/A':
                    self.selected_items.add(symbol)
        
        # Tabloyu yenile
        self.update_table()
        print(f"[L-SPREAD] ✅ Seçim durumu: {len(self.selected_items)} hisse seçili")
    
    # ESKİ METODLAR KALDIRILDI - TAKE PROFIT PANEL'DEN KOPYA KULLANILIYOR
    
    def on_table_click(self, event):
        """TAKE PROFIT PANEL'DEN KOPYA: Tabloya tıklama - Seçim durumunu değiştir"""
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
            symbol = self.tree.set(item, "PREF_IBKR")
            
            print(f"[L-SPREAD DEBUG] 🖱️ Table click: symbol={symbol}, current={current}")
            
            if current == "☑":  # Seçili ise
                self.tree.set(item, "select", "☐")  # Seçimi kaldır
                if symbol in self.selected_items:
                    self.selected_items.remove(symbol)
                print(f"[L-SPREAD] ✅ {symbol} seçimi kaldırıldı")
            else:  # Seçili değilse
                self.tree.set(item, "select", "☑")  # Seç
                self.selected_items.add(symbol)
                print(f"[L-SPREAD] ✅ {symbol} seçildi")
            
            print(f"[L-SPREAD DEBUG] 📝 Güncel selected_items: {self.selected_items}")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Table click hatası: {e}")
    
    def analyze_last_real_prints(self):
        """LRPAN - Last Real Print Analyzer"""
        try:
            print(f"[LRPAN] 🔍 Last Real Print analizi başlatılıyor...")
            
            if not self.selected_items:
                messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
                return
            
            # LRPAN sonuçları penceresi
            lrpan_win = tk.Toplevel(self.win)
            lrpan_win.title("LRPAN - Last Real Print Analyzer")
            lrpan_win.geometry("800x600")
            lrpan_win.transient(self.win)
            lrpan_win.grab_set()
            
            # LRPAN sonuçları tablosu
            columns = ('Symbol', 'Shares', 'Venue', 'Price', 'Status')
            lrpan_tree = ttk.Treeview(lrpan_win, columns=columns, show='headings', height=20)
            
            # Kolon başlıkları
            for col in columns:
                lrpan_tree.heading(col, text=col)
                if col == 'Symbol':
                    lrpan_tree.column(col, width=120, anchor='center')
                elif col == 'Shares':
                    lrpan_tree.column(col, width=80, anchor='center')
                elif col == 'Venue':
                    lrpan_tree.column(col, width=100, anchor='center')
                elif col == 'Price':
                    lrpan_tree.column(col, width=100, anchor='center')
                elif col == 'Status':
                    lrpan_tree.column(col, width=120, anchor='center')
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(lrpan_win, orient='vertical', command=lrpan_tree.yview)
            lrpan_tree.configure(yscrollcommand=scrollbar.set)
            
            lrpan_tree.pack(side='left', fill='both', expand=True, padx=10, pady=10)
            scrollbar.pack(side='right', fill='y', pady=10)
            
            # Her seçili hisse için LRPAN analizi
            for symbol in self.selected_items:
                print(f"[LRPAN] 🔍 {symbol} analiz ediliyor...")
                
                # Hammer Pro'dan tick data al (venue bilgisi için) - İyileştirilmiş
                if hasattr(self.parent, 'hammer') and self.parent.hammer and self.parent.hammer.connected:
                    # Support takımının komutunu kullan - Son 25 tick'i al
                    print(f"[LRPAN] 🔍 {symbol}: Support takımının komutu ile tick data deneniyor...")
                    
                    # Support takımının TAM komutu ile test et (lastFew yok!)
                    print(f"[LRPAN] 🔍 {symbol}: Support takımının TAM komutu ile test ediliyor...")
                    tick_data = self.parent.hammer.get_ticks(symbol, lastFew=25, tradesOnly=False, regHoursOnly=True)
                    
                    if tick_data and 'data' in tick_data and tick_data['data']:
                        # Son 25 tick'i al ve şu anki zamana en yakın real print'i bul
                        all_ticks = tick_data['data']
                        last_25_ticks = all_ticks[-25:] if len(all_ticks) >= 25 else all_ticks
                        
                        print(f"[LRPAN] 🔍 {symbol}: Son {len(last_25_ticks)} tick kontrol ediliyor...")
                        
                        # Şu anki zamanı al
                        from datetime import datetime
                        current_time = datetime.now()
                        print(f"[LRPAN] 🕐 Şu anki zaman: {current_time.strftime('%H:%M:%S')}")
                        
                        # En yakın real print'i bul (zaman farkına göre)
                        closest_real_print = None
                        min_time_diff = None
                        
                        for i, tick in enumerate(last_25_ticks):
                            price = tick.get('p', 0)
                            size = tick.get('s', 0)
                            timestamp_str = tick.get('t', '')
                            
                            # Geliştirilmiş venue extraction
                            venue = self.parent.hammer.extract_venue_from_tick(tick, symbol)
                            
                            # Debug: Her tick'in detaylı bilgilerini göster
                            print(f"[LRPAN] 📊 {symbol} Tick {i+1} (Zaman: {timestamp_str}):")
                            print(f"[LRPAN] 📊   Price: {price}, Size: {size}, Venue: {venue}")
                            
                            # Tüm tick field'larını göster
                            print(f"[LRPAN] 📊   Tüm field'lar: {dict(tick)}")
                            
                            # Venue field'larını tek tek kontrol et
                            venue_fields = ['e', 'ex', 'exchange', 'venue', 'mkt', 'market', 'src', 'source', 'inst', 'instrument', 'dest', 'destination', 'route', 'routing']
                            venue_debug = {}
                            for field in venue_fields:
                                venue_debug[field] = tick.get(field, 'None')
                            print(f"[LRPAN] 📊   Venue field'ları: {venue_debug}")
                            
                            # Sadece 100, 200, 300 lot olanları kontrol et
                            if size in [100, 200, 300]:
                                try:
                                    # Timestamp'i parse et
                                    tick_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                    
                                    # Zaman farkını hesapla (saniye cinsinden)
                                    time_diff = abs((current_time - tick_time).total_seconds())
                                    
                                    print(f"[LRPAN] ✅ {symbol}: REAL PRINT! {size} shares @ ${price} ({venue})")
                                    print(f"[LRPAN] 🕐 Zaman farkı: {time_diff:.0f} saniye önce")
                                    
                                    # En yakın print'i güncelle
                                    if min_time_diff is None or time_diff < min_time_diff:
                                        closest_real_print = {
                                            'price': price,
                                            'size': size,
                                            'venue': venue,
                                            'timestamp': timestamp_str,
                                            'time_diff': time_diff
                                        }
                                        min_time_diff = time_diff
                                        print(f"[LRPAN] 🎯 {symbol}: YENİ EN YAKIN PRINT!")
                                    
                                except Exception as e:
                                    print(f"[LRPAN] ⚠️ {symbol}: Timestamp parse hatası: {e}")
                            else:
                                print(f"[LRPAN] ⚠️ {symbol} Tick {i+1}: {size} shares - IGNORE (100/200/300 değil)")
                        
                        # En yakın real print'i göster
                        if closest_real_print:
                            print(f"[LRPAN] 🎯 {symbol}: EN YAKIN REAL PRINT BULUNDU!")
                            print(f"[LRPAN] 🎯   Zaman: {closest_real_print['timestamp']}")
                            print(f"[LRPAN] 🎯   Fiyat: ${closest_real_print['price']}")
                            print(f"[LRPAN] 🎯   Lot: {closest_real_print['size']}")
                            print(f"[LRPAN] 🎯   Venue: {closest_real_print['venue']}")
                            print(f"[LRPAN] 🎯   Zaman farkı: {closest_real_print['time_diff']:.0f} saniye önce")
                        
                        if closest_real_print:
                            # Gerçek print bulundu
                            status = "✅ REAL"
                            tag = 'real'
                            values = [
                                symbol,
                                f"{closest_real_print['size']:.0f}",
                                closest_real_print['venue'],
                                f"${closest_real_print['price']:.2f}",
                                status
                            ]
                        else:
                            # Hiç gerçek print bulunamadı
                            status = "❌ NO REAL PRINT"
                            tag = 'no_real'
                            values = [
                                symbol,
                                "N/A",
                                "N/A",
                                "N/A",
                                status
                            ]
                            print(f"[LRPAN] ⚠️ {symbol}: Hiç gerçek print bulunamadı")
                        
                        lrpan_tree.insert('', 'end', values=values, tags=(tag,))
                    else:
                        # Tick data bulunamadı
                        values = [symbol, "N/A", "N/A", "N/A", "❌ NO TICK DATA"]
                        lrpan_tree.insert('', 'end', values=values, tags=('no_data',))
                        print(f"[LRPAN] ⚠️ {symbol}: Tick data bulunamadı")
                else:
                    # Hammer Pro bağlı değil
                    values = [symbol, "N/A", "N/A", "N/A", "❌ NO CONNECTION"]
                    lrpan_tree.insert('', 'end', values=values, tags=('no_connection',))
                    print(f"[LRPAN] ⚠️ {symbol}: Hammer Pro bağlı değil")
            
            # Tag renkleri
            lrpan_tree.tag_configure('real', background='lightgreen')
            lrpan_tree.tag_configure('fake', background='lightcoral')
            lrpan_tree.tag_configure('no_real', background='lightyellow')
            lrpan_tree.tag_configure('no_data', background='lightyellow')
            lrpan_tree.tag_configure('no_connection', background='lightgray')
            
            print(f"[LRPAN] ✅ Analiz tamamlandı: {len(self.selected_items)} hisse")
            
        except Exception as e:
            print(f"[LRPAN] ❌ Analiz hatası: {e}")
            messagebox.showerror("Hata", f"LRPAN analiz hatası: {e}")
    
    def test_venue_extraction(self):
        """Venue extraction'ı test et"""
        try:
            print(f"[LRPAN TEST] 🔍 Venue extraction testi başlatılıyor...")
            
            test_symbols = ['AAPL', 'MSFT', 'TSLA', 'BOH PRB', 'PSEC PRA']
            
            for symbol in test_symbols:
                print(f"[LRPAN TEST] 🔍 {symbol} test ediliyor...")
                
                # Venue tahmin testi
                guessed_venue = self.parent.hammer.guess_venue_from_symbol(symbol)
                print(f"[LRPAN TEST] 📊 {symbol} -> Tahmin edilen venue: {guessed_venue}")
                
                # getTicks testi
                if hasattr(self.parent, 'hammer') and self.parent.hammer and self.parent.hammer.connected:
                    tick_data = self.parent.hammer.get_ticks(symbol, lastFew=1)
                    if tick_data and tick_data.get('data'):
                        tick = tick_data['data'][0]
                        extracted_venue = self.parent.hammer.extract_venue_from_tick(tick, symbol)
                        print(f"[LRPAN TEST] 📊 {symbol} -> Çıkarılan venue: {extracted_venue}")
                        print(f"[LRPAN TEST] 📊 {symbol} -> Tick field'ları: {list(tick.keys())}")
                
                print(f"[LRPAN TEST] ---")
            
            print(f"[LRPAN TEST] ✅ Test tamamlandı!")
            
        except Exception as e:
            print(f"[LRPAN TEST] ❌ Test hatası: {e}")
    
    def analyze_print_authenticity(self, shares, venue):
        """Print'in gerçek olup olmadığını analiz et - Sadece 100, 200, 300 lot"""
        try:
            # Sadece 100, 200, 300 lot olanları real print kabul et
            if shares in [100, 200, 300]:
                return True
            else:
                return False
                    
        except Exception as e:
            print(f"[LRPAN] ❌ Print analiz hatası: {e}")
            return False
    
    def sort_column(self, col):
        """Kolon sıralama fonksiyonu"""
        try:
            # Mevcut sıralama durumunu kontrol et
            if self.sort_column_name == col:
                self.sort_reverse = not self.sort_reverse
            else:
                self.sort_reverse = False
                self.sort_column_name = col
            
            # Veriyi sırala
            if self.filtered_data is not None and not self.filtered_data.empty:
                if col == 'select':
                    return  # Seçim kolonu sıralanmaz
                
                # Kolon adını DataFrame kolonuna çevir
                df_col = self.get_dataframe_column_name(col)
                
                if df_col in self.filtered_data.columns:
                    # Sayısal kolonlar için özel işlem
                    if col in ['prev_close', 'FINAL_THG', 'Last', 'bid', 'ask', 'spread', 
                              'bid_buy_ucuzluk', 'ask_sell_ucuzluk', 'SMI', 'MAXALW', 'SMA63_chg']:
                        # Sayısal değerlere çevir
                        self.filtered_data[df_col] = pd.to_numeric(self.filtered_data[df_col], errors='coerce')
                        self.filtered_data = self.filtered_data.sort_values(df_col, ascending=not self.sort_reverse, na_position='last')
                    else:
                        # Metin kolonları için
                        self.filtered_data = self.filtered_data.sort_values(df_col, ascending=not self.sort_reverse, na_position='last')
                    
                    # Tabloyu yenile
                    self.update_table()
                    print(f"[L-SPREAD] ✅ {col} kolonu sıralandı: {'Azalan' if self.sort_reverse else 'Artan'}")
                else:
                    print(f"[L-SPREAD] ❌ {col} kolonu bulunamadı")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Sıralama hatası: {e}")
    
    def get_dataframe_column_name(self, col):
        """Kolon adını DataFrame kolonuna çevir"""
        column_mapping = {
            'PREF_IBKR': 'PREF IBKR',
            'prev_close': 'prev_close',
            'FINAL_THG': 'FINAL_THG',
            'Last': 'Last Price',
            'bid': 'Bid_buy_ucuzluk_skoru',
            'ask': 'Ask_buy_ucuzluk_skoru',
            'spread': 'Spread',
            'bid_buy_ucuzluk': 'Bid_buy_ucuzluk_skoru',
            'ask_sell_ucuzluk': 'Ask_sell_pahalilik_skoru',
            'SMI': 'SMI',
            'MAXALW': 'MAXALW',
            'SMA63_chg': 'SMA63 chg'
        }
        return column_mapping.get(col, col)
    
    def execute_bid_buy(self):
        """Bid Buy emirleri gönder"""
        try:
            if not self.selected_items:
                messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
                return
            
            # Onay penceresi göster
            self.show_order_confirmation("Bid Buy", "bid_buy")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Bid Buy hatası: {e}")
            messagebox.showerror("Hata", f"Bid Buy hatası: {e}")
    
    def execute_ask_sell(self):
        """Ask Sell emirleri gönder"""
        try:
            if not self.selected_items:
                messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
                return
            
            # Onay penceresi göster
            self.show_order_confirmation("Ask Sell", "ask_sell")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Ask Sell hatası: {e}")
            messagebox.showerror("Hata", f"Ask Sell hatası: {e}")
    
    def show_order_confirmation(self, title, order_type):
        """Emir onay penceresi göster - Take Profit Longs ve JFIN formatında"""
        try:
            # Onay penceresi
            win = tk.Toplevel(self.win)
            win.title(f"{title} Emirleri - {len(self.selected_items)} Pozisyon")
            win.geometry("900x500")
            win.transient(self.win)
            win.grab_set()
            
            # Emirler tablosu - Take Profit Longs ve JFIN formatında
            columns = ('Symbol', 'Qty', 'Emir Fiyatı', 'Emir Bilgisi', 'Lot Size')
            order_tree = ttk.Treeview(win, columns=columns, show='headings', height=15)
            
            # Kolon başlıkları
            for col in columns:
                order_tree.heading(col, text=col)
                if col == 'Symbol':
                    order_tree.column(col, width=100, anchor='center')
                elif col == 'Qty':
                    order_tree.column(col, width=80, anchor='center')
                elif col == 'Emir Fiyatı':
                    order_tree.column(col, width=100, anchor='center')
                elif col == 'Emir Bilgisi':
                    order_tree.column(col, width=300, anchor='center')
                elif col == 'Lot Size':
                    order_tree.column(col, width=80, anchor='center')
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(win, orient='vertical', command=order_tree.yview)
            order_tree.configure(yscrollcommand=scrollbar.set)
            
            order_tree.pack(side='left', fill='both', expand=True, padx=10, pady=10)
            scrollbar.pack(side='right', fill='y', pady=10)
            
            # Emir detaylarını hesapla
            selected_symbols = list(self.selected_items)
            
            for symbol in selected_symbols:
                # Hisse verilerini al
                row_data = self.filtered_data[self.filtered_data['PREF IBKR'] == symbol]
                if not row_data.empty:
                    row = row_data.iloc[0]
                    
                    # Qty (miktar) - Lot ayarı varsa onu kullan, yoksa MAXALW/4 hesapla
                    if symbol in self.lot_settings:
                        # Lot ayarı varsa onu kullan
                        raw_qty = self.lot_settings[symbol]
                        print(f"[L-SPREAD ORDER] ✅ {symbol}: Lot ayarı kullanılıyor: {raw_qty}")
                    else:
                        # Lot ayarı yoksa MAXALW/4 hesapla
                        maxalw = row.get('MAXALW', 0)
                        if maxalw > 0:
                            # MAXALW'nin 1/4'ünü al
                            raw_qty = maxalw / 4
                            print(f"[L-SPREAD ORDER] 🔄 {symbol}: MAXALW/4 hesaplanıyor: MAXALW={maxalw:.1f} → {raw_qty:.1f}")
                        else:
                            raw_qty = 100  # Varsayılan 100 lot
                            print(f"[L-SPREAD ORDER] ⚠️ {symbol}: MAXALW=0 → Varsayılan 100 lot")
                    
                    # Lot değerini 100'lük yuvarlama ile düzelt
                    if raw_qty > 0:
                        # 100'lük yuvarlama uygula
                        qty = int(raw_qty // 100) * 100
                        if qty < 100:  # Minimum 100 lot
                            qty = 100
                    else:
                        qty = 100  # Varsayılan 100 lot
                    
                    # DEBUG: Lot ayarlarını kontrol et
                    print(f"[L-SPREAD ORDER] 🔍 {symbol}: lot_settings={self.lot_settings.get(symbol, 'YOK')}, MAXALW={row.get('MAXALW', 0)}, Raw qty={raw_qty}, Final qty={qty}")
                    
                    # Gerçek Bid/Ask fiyatlarını al - Hammer Pro'dan live veri çek
                    # Symbol conversion'ı Hammer Pro client'ın kendi get_market_data metoduna bırak
                    # Çünkü o zaten PREF IBKR formatını doğru şekilde handle ediyor
                    
                    # Hammer Pro'dan live market data çek (mini450 ile aynı yöntem)
                    if hasattr(self.parent, 'hammer') and self.parent.hammer:
                        market_data = self.parent.hammer.get_market_data(symbol)
                        if market_data and market_data.get('bid', 0) > 0 and market_data.get('ask', 0) > 0:
                            bid_price = market_data.get('bid', 0)
                            ask_price = market_data.get('ask', 0)
                            print(f"[L-SPREAD] ✅ {symbol}: Live Bid=${bid_price:.2f}, Ask=${ask_price:.2f}")
                        else:
                            # Fallback: DataFrame'den çek
                            bid_price = float(str(row.get('Bid', 0)).replace('$', '').replace(',', '')) if str(row.get('Bid', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                            ask_price = float(str(row.get('Ask', 0)).replace('$', '').replace(',', '')) if str(row.get('Ask', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                            print(f"[L-SPREAD] ⚠️ {symbol}: Fallback Bid=${bid_price:.2f}, Ask=${ask_price:.2f}")
                    else:
                        # Fallback: DataFrame'den çek
                        bid_price = float(str(row.get('Bid', 0)).replace('$', '').replace(',', '')) if str(row.get('Bid', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                        ask_price = float(str(row.get('Ask', 0)).replace('$', '').replace(',', '')) if str(row.get('Ask', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                        print(f"[L-SPREAD] ⚠️ {symbol}: No Hammer, Fallback Bid=${bid_price:.2f}, Ask=${ask_price:.2f}")
                    
                    spread = float(str(row.get('Spread', 0)).replace('$', '').replace(',', '')) if str(row.get('Spread', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                    
                    # Emir fiyatını hesapla
                    if order_type == "bid_buy":
                        order_price = bid_price + (spread * 0.15)
                        order_info = f"{qty:.0f} lot BUY @ ${order_price:.2f} (HIDDEN)"
                    else:  # ask_sell
                        order_price = ask_price - (spread * 0.15)
                        order_info = f"{qty:.0f} lot SELL @ ${order_price:.2f} (HIDDEN)"
                    
                    values = [
                        symbol,
                        f"{qty:.0f}",
                        f"${order_price:.2f}",
                        order_info,
                        f"{qty:.0f}"
                    ]
                    
                    order_tree.insert('', 'end', values=values)
            
            # Butonlar
            button_frame = ttk.Frame(win)
            button_frame.pack(pady=10)
            
            # Ana butonlar
            ttk.Button(button_frame, text="Emirleri Gönder", 
                      command=lambda: self.send_orders(order_tree, order_type)).pack(side='left', padx=5)
            ttk.Button(button_frame, text="trades.csv'ye Kaydet", 
                      command=lambda: self.save_to_trades_csv(order_tree, order_type)).pack(side='left', padx=5)
            ttk.Button(button_frame, text="İptal Et", 
                      command=win.destroy).pack(side='left', padx=5)
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Onay penceresi hatası: {e}")
            messagebox.showerror("Hata", f"Onay penceresi hatası: {e}")
    
    def send_orders(self, order_tree, order_type):
        """Emirleri gönder"""
        try:
            print(f"[L-SPREAD] 🔄 {len(self.selected_items)} emir gönderiliyor...")
            
            success_count = 0
            error_count = 0
            
            for symbol in self.selected_items:
                # Hisse verilerini al
                row_data = self.filtered_data[self.filtered_data['PREF IBKR'] == symbol]
                if not row_data.empty:
                    row = row_data.iloc[0]
                    
                    # Emir detaylarını hesapla
                    if symbol in self.lot_settings:
                        # Lot ayarı varsa onu kullan
                        raw_qty = self.lot_settings[symbol]
                        print(f"[L-SPREAD SEND] ✅ {symbol}: Lot ayarı kullanılıyor: {raw_qty}")
                    else:
                        # Lot ayarı yoksa MAXALW/4 hesapla
                        maxalw = row.get('MAXALW', 0)
                        if maxalw > 0:
                            # MAXALW'nin 1/4'ünü al
                            raw_qty = maxalw / 4
                            print(f"[L-SPREAD SEND] 🔄 {symbol}: MAXALW/4 hesaplanıyor: MAXALW={maxalw:.1f} → {raw_qty:.1f}")
                        else:
                            raw_qty = 100  # Varsayılan 100 lot
                            print(f"[L-SPREAD SEND] ⚠️ {symbol}: MAXALW=0 → Varsayılan 100 lot")
                    
                    # Lot değerini 100'lük yuvarlama ile düzelt
                    if raw_qty > 0:
                        # 100'lük yuvarlama uygula
                        qty = int(raw_qty // 100) * 100
                        if qty < 100:  # Minimum 100 lot
                            qty = 100
                    else:
                        qty = 100  # Varsayılan 100 lot
                    
                    # Gerçek Bid/Ask fiyatlarını al - Hammer Pro'dan live veri çek
                    # Symbol conversion'ı Hammer Pro client'ın kendi get_market_data metoduna bırak
                    # Çünkü o zaten PREF IBKR formatını doğru şekilde handle ediyor
                    
                    # Hammer Pro'dan live market data çek (mini450 ile aynı yöntem)
                    if hasattr(self.parent, 'hammer') and self.parent.hammer:
                        market_data = self.parent.hammer.get_market_data(symbol)
                        if market_data and market_data.get('bid', 0) > 0 and market_data.get('ask', 0) > 0:
                            bid_price = market_data.get('bid', 0)
                            ask_price = market_data.get('ask', 0)
                            print(f"[L-SPREAD] ✅ {symbol}: Live Bid=${bid_price:.2f}, Ask=${ask_price:.2f}")
                        else:
                            # Fallback: DataFrame'den çek
                            bid_price = float(str(row.get('Bid', 0)).replace('$', '').replace(',', '')) if str(row.get('Bid', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                            ask_price = float(str(row.get('Ask', 0)).replace('$', '').replace(',', '')) if str(row.get('Ask', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                            print(f"[L-SPREAD] ⚠️ {symbol}: Fallback Bid=${bid_price:.2f}, Ask=${ask_price:.2f}")
                    else:
                        # Fallback: DataFrame'den çek
                        bid_price = float(str(row.get('Bid', 0)).replace('$', '').replace(',', '')) if str(row.get('Bid', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                        ask_price = float(str(row.get('Ask', 0)).replace('$', '').replace(',', '')) if str(row.get('Ask', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                        print(f"[L-SPREAD] ⚠️ {symbol}: No Hammer, Fallback Bid=${bid_price:.2f}, Ask=${ask_price:.2f}")
                    
                    spread = float(str(row.get('Spread', 0)).replace('$', '').replace(',', '')) if str(row.get('Spread', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                    
                    if order_type == "bid_buy":
                        order_price = bid_price + (spread * 0.15)
                        action = "BUY"
                    else:  # ask_sell
                        order_price = ask_price - (spread * 0.15)
                        action = "SELL"
                    
                    # Symbol mapping (PR -> -)
                    hammer_symbol = symbol.replace(" PR", "-")
                    
                    # Mevcut moda göre emir gönder
                    if hasattr(self.parent, 'mode_manager'):
                        success = self.parent.mode_manager.place_order(
                            symbol=hammer_symbol,
                            side=action,
                            quantity=qty,
                            price=order_price,
                            order_type="LIMIT",
                            hidden=True  # Hidden emir
                        )
                        
                        if success:
                            success_count += 1
                            print(f"[L-SPREAD] ✅ {symbol}: {action} {qty:.0f} lot @ ${order_price:.2f}")
                        else:
                            error_count += 1
                            print(f"[L-SPREAD] ❌ {symbol}: {action} {qty:.0f} lot @ ${order_price:.2f} - Başarısız")
                    elif hasattr(self.parent, 'hammer') and self.parent.hammer:
                        # Fallback to direct hammer
                        success = self.parent.hammer.place_order(
                            symbol=hammer_symbol,
                            side=action,
                            quantity=qty,
                            price=order_price,
                            order_type="LIMIT",
                            hidden=True  # Hidden emir
                        )
                        
                        if success:
                            success_count += 1
                            print(f"[L-SPREAD] ✅ {symbol}: {action} {qty:.0f} lot @ ${order_price:.2f}")
                        else:
                            error_count += 1
                            print(f"[L-SPREAD] ❌ {symbol}: {action} {qty:.0f} lot @ ${order_price:.2f} - Başarısız")
                    else:
                        error_count += 1
                        print(f"[L-SPREAD] ❌ Bağlantı yok!")
            
            # Sonuç mesajı
            result_msg = f"Emirler Gönderildi!\n\nBaşarılı: {success_count}\nBaşarısız: {error_count}"
            messagebox.showinfo("Sonuç", result_msg)
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Emir gönderme hatası: {e}")
            messagebox.showerror("Hata", f"Emir gönderme hatası: {e}")
    
    def save_to_trades_csv(self, order_tree, order_type):
        """Emirleri trades.csv'ye kaydet"""
        try:
            # trades.csv dosyasına kaydet
            import csv
            from datetime import datetime
            
            filename = "trades.csv"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(filename, 'a', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                
                # Başlık satırı (dosya boşsa)
                if file.tell() == 0:
                    writer.writerow(['Timestamp', 'Symbol', 'Action', 'Quantity', 'Price', 'Order Info'])
                
                # Emirleri yaz
                for symbol in self.selected_items:
                    # Hisse verilerini al
                    row_data = self.filtered_data[self.filtered_data['PREF IBKR'] == symbol]
                    if not row_data.empty:
                        row = row_data.iloc[0]
                        
                        # Emir detaylarını hesapla
                        if symbol in self.lot_settings:
                            # Lot ayarı varsa onu kullan
                            raw_qty = self.lot_settings[symbol]
                            print(f"[L-SPREAD CSV] ✅ {symbol}: Lot ayarı kullanılıyor: {raw_qty}")
                        else:
                            # Lot ayarı yoksa MAXALW/4 hesapla
                            maxalw = row.get('MAXALW', 0)
                            if maxalw > 0:
                                # MAXALW'nin 1/4'ünü al
                                raw_qty = maxalw / 4
                                print(f"[L-SPREAD CSV] 🔄 {symbol}: MAXALW/4 hesaplanıyor: MAXALW={maxalw:.1f} → {raw_qty:.1f}")
                            else:
                                raw_qty = 100  # Varsayılan 100 lot
                                print(f"[L-SPREAD CSV] ⚠️ {symbol}: MAXALW=0 → Varsayılan 100 lot")
                        
                        # Lot değerini 100'lük yuvarlama ile düzelt
                        if raw_qty > 0:
                            # 100'lük yuvarlama uygula
                            qty = int(raw_qty // 100) * 100
                            if qty < 100:  # Minimum 100 lot
                                qty = 100
                        else:
                            qty = 100  # Varsayılan 100 lot
                        
                        # Gerçek Bid/Ask fiyatlarını al - Hammer Pro'dan live veri çek
                        # Symbol conversion'ı Hammer Pro client'ın kendi get_market_data metoduna bırak
                        # Çünkü o zaten PREF IBKR formatını doğru şekilde handle ediyor
                        
                        # DEBUG: Hammer Pro durumunu kontrol et
                        print(f"[L-SPREAD DEBUG] 🔍 {symbol} için market data çekiliyor...")
                        print(f"[L-SPREAD DEBUG] 📡 Parent hammer var mı: {hasattr(self.parent, 'hammer')}")
                        
                        if hasattr(self.parent, 'hammer'):
                            print(f"[L-SPREAD DEBUG] 🔗 Hammer Pro bağlı mı: {self.parent.hammer.connected}")
                            print(f"[L-SPREAD DEBUG] 🔐 Hammer Pro authenticated mı: {self.parent.hammer.authenticated}")
                            print(f"[L-SPREAD DEBUG] 📊 Market data cache boyutu: {len(self.parent.hammer.market_data)}")
                            
                            # Live data durumunu kontrol et
                            if hasattr(self.parent, 'live_data_running'):
                                print(f"[L-SPREAD DEBUG] 🔴 Live data çalışıyor mu: {self.parent.live_data_running}")
                            else:
                                print(f"[L-SPREAD DEBUG] ⚠️ Live data durumu bilinmiyor")
                        
                        # Hammer Pro'dan live market data çek (mini450 ile aynı yöntem)
                        if hasattr(self.parent, 'hammer') and self.parent.hammer:
                            market_data = self.parent.hammer.get_market_data(symbol)
                            print(f"[L-SPREAD DEBUG] 📈 {symbol} market data: {market_data}")
                            
                            if market_data and market_data.get('bid', 0) > 0 and market_data.get('ask', 0) > 0:
                                bid_price = market_data.get('bid', 0)
                                ask_price = market_data.get('ask', 0)
                                print(f"[L-SPREAD] ✅ {symbol}: Live Bid=${bid_price:.2f}, Ask=${ask_price:.2f}")
                            else:
                                # Fallback: DataFrame'den çek
                                bid_price = float(str(row.get('Bid', 0)).replace('$', '').replace(',', '')) if str(row.get('Bid', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                                ask_price = float(str(row.get('Ask', 0)).replace('$', '').replace(',', '')) if str(row.get('Ask', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                                print(f"[L-SPREAD] ⚠️ {symbol}: Fallback Bid=${bid_price:.2f}, Ask=${ask_price:.2f}")
                        else:
                            # Fallback: DataFrame'den çek
                            bid_price = float(str(row.get('Bid', 0)).replace('$', '').replace(',', '')) if str(row.get('Bid', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                            ask_price = float(str(row.get('Ask', 0)).replace('$', '').replace(',', '')) if str(row.get('Ask', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                            print(f"[L-SPREAD] ⚠️ {symbol}: No Hammer, Fallback Bid=${bid_price:.2f}, Ask=${ask_price:.2f}")
                        
                        spread = float(str(row.get('Spread', 0)).replace('$', '').replace(',', '')) if str(row.get('Spread', 0)).replace('$', '').replace(',', '') != 'N/A' else 0
                        
                        if order_type == "bid_buy":
                            order_price = bid_price + (spread * 0.15)
                            action = "BUY"
                            order_info = f"{qty:.0f} lot BUY @ ${order_price:.2f} (HIDDEN)"
                        else:  # ask_sell
                            order_price = ask_price - (spread * 0.15)
                            action = "SELL"
                            order_info = f"{qty:.0f} lot SELL @ ${order_price:.2f} (HIDDEN)"
                        
                        writer.writerow([timestamp, symbol, action, f"{qty:.0f}", f"${order_price:.2f}", order_info])
            
            messagebox.showinfo("Başarılı", f"Emirler {filename} dosyasına kaydedildi!")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ CSV kaydetme hatası: {e}")
            messagebox.showerror("Hata", f"CSV kaydetme hatası: {e}")
    
    def select_all_orders(self, order_tree, select_all):
        """Tüm emirleri seç/seçimi kaldır"""
        try:
            for item in order_tree.get_children():
                values = list(order_tree.item(item, 'values'))
                if select_all:
                    values[0] = "☑"  # Seç
                else:
                    values[0] = "☐"  # Kaldır
                order_tree.item(item, values=values)
        except Exception as e:
            print(f"[L-SPREAD] ❌ Toplu seçim hatası: {e}")
    
    def get_symbol_data_from_filtered(self, symbol):
        """Filtrelenmiş veriden symbol verilerini al"""
        try:
            if self.filtered_data is not None and not self.filtered_data.empty:
                symbol_row = self.filtered_data[self.filtered_data['PREF IBKR'] == symbol]
                if not symbol_row.empty:
                    return symbol_row.iloc[0].to_dict()
            return None
        except Exception as e:
            print(f"[L-SPREAD] ❌ Symbol data alma hatası: {e}")
            return None
    
    def calculate_lot_for_symbol(self, symbol):
        """Symbol için lot hesapla"""
        try:
            # Seçili hisselerden MAXALW değerini bul
            if self.filtered_data is not None and not self.filtered_data.empty:
                symbol_row = self.filtered_data[self.filtered_data['PREF IBKR'] == symbol]
                if not symbol_row.empty:
                    maxalw = symbol_row['MAXALW'].iloc[0]
                    if pd.notna(maxalw) and maxalw > 0:
                        # MAXALW'nin 1/4'ü, yüzlere yuvarla
                        lot = round(maxalw / 4 / 100) * 100
                        return max(lot, 100)  # Minimum 100 lot
            return 200  # Default lot
        except Exception as e:
            print(f"[L-SPREAD] ❌ Lot hesaplama hatası: {e}")
            return 200
    
    def get_market_data_for_symbol(self, symbol):
        """Symbol için market data al"""
        try:
            if hasattr(self.parent, 'hammer') and self.parent.hammer:
                return self.parent.hammer.get_market_data(symbol)
            return None
        except Exception as e:
            print(f"[L-SPREAD] ❌ Market data alma hatası: {e}")
            return None
    
    def set_maxalw_lot(self):
        """MAXALW lot ayarla"""
        try:
            if not self.selected_items:
                messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
                return
            
            # Seçili hisseler için MAXALW lot hesapla
            for symbol in self.selected_items:
                lot = self.calculate_lot_for_symbol(symbol)
                print(f"[L-SPREAD] ✅ {symbol}: MAXALW lot = {lot}")
            
            messagebox.showinfo("Başarılı", f"{len(self.selected_items)} hisse için MAXALW lot ayarlandı!")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ MAXALW lot hatası: {e}")
            messagebox.showerror("Hata", f"MAXALW lot hatası: {e}")
    
    def set_fixed_lot(self, lot_size):
        """Sabit lot ayarla"""
        try:
            if not self.selected_items:
                messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
                return
            
            print(f"[L-SPREAD] ✅ {len(self.selected_items)} hisse için sabit lot: {lot_size}")
            messagebox.showinfo("Başarılı", f"{len(self.selected_items)} hisse için sabit lot {lot_size} ayarlandı!")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Sabit lot hatası: {e}")
            messagebox.showerror("Hata", f"Sabit lot hatası: {e}")
    
    def select_all_stocks(self):
        """Tüm hisseleri seç"""
        try:
            if self.filtered_data is not None and not self.filtered_data.empty:
                for _, row in self.filtered_data.iterrows():
                    symbol = row.get('PREF IBKR', 'N/A')
                    if symbol != 'N/A':
                        self.selected_items.add(symbol)
                
                self.update_table()
                print(f"[L-SPREAD] ✅ Tüm hisseler seçildi: {len(self.selected_items)} hisse")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Tümünü seç hatası: {e}")
    
    def deselect_all_stocks(self):
        """Tüm seçimleri kaldır"""
        try:
            self.selected_items.clear()
            self.update_table()
            print(f"[L-SPREAD] ✅ Tüm seçimler kaldırıldı")
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ Seçimleri kaldırma hatası: {e}")
    
    def set_lot_percentage(self, percentage):
        """Yüzdesel lot ayarla - 100'lük yuvarlama ile"""
        try:
            if not self.selected_items:
                messagebox.showwarning("Uyarı", "Hiç hisse seçilmedi!")
                return
            
            print(f"[L-SPREAD] 🔄 {len(self.selected_items)} hisse için %{percentage} lot hesaplanıyor...")
            
            # Seçili hisseler için yüzdesel lot hesapla
            for symbol in self.selected_items:
                # Hisse verilerini al
                row_data = self.filtered_data[self.filtered_data['PREF IBKR'] == symbol]
                if not row_data.empty:
                    row = row_data.iloc[0]
                    maxalw = row.get('MAXALW', 0)
                    
                    if maxalw > 0:
                        # MAXALW'nin yüzdesini al
                        calculated_lot = maxalw * percentage / 100
                        
                        # %100 haricinde 100'lük yuvarlama yap
                        if percentage == 100:
                            # %100 için normal yuvarlama
                            lot = round(calculated_lot)
                        else:
                            # %25, %50, %75 için 100'lük aşağı yuvarlama
                            lot = int(calculated_lot // 100) * 100
                        
                        # Minimum 100 lot
                        if lot < 100:
                            lot = 100
                        
                        print(f"[L-SPREAD %{percentage}] 🔍 {symbol}: MAXALW={maxalw:.1f} → %{percentage}={calculated_lot:.1f} → Lot={lot}")
                    else:
                        lot = 100  # Varsayılan 100 lot
                        print(f"[L-SPREAD %{percentage}] ⚠️ {symbol}: MAXALW=0 → Lot=100 (varsayılan)")
                    
                    # Lot ayarını kaydet
                    self.lot_settings[symbol] = lot
                    print(f"[L-SPREAD] ✅ {symbol}: %{percentage} lot = {lot}")
                else:
                    print(f"[L-SPREAD] ⚠️ {symbol}: Veri bulunamadı")
            
            messagebox.showinfo("Başarılı", f"{len(self.selected_items)} hisse için %{percentage} lot ayarlandı!")
            
            # Tabloyu güncelle
            self.update_table()
            
        except Exception as e:
            print(f"[L-SPREAD] ❌ %{percentage} lot ayarlama hatası: {e}")
            messagebox.showerror("Hata", f"%{percentage} lot ayarlama hatası: {e}")
