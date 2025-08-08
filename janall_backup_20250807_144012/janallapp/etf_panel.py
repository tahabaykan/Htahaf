"""
ETF panel modülü.
"""

import tkinter as tk
from tkinter import ttk
import pandas as pd
import numpy as np

class ETFPanel(ttk.Frame):
    def __init__(self, parent, hammer_client):
        super().__init__(parent)
        self.hammer = hammer_client
        self.etf_data = {}  # ETF verilerini saklamak için
        
        # ETF'leri CSV'den yükle
        self.load_etfs_from_csv()
        
        self.setup_ui()
        
        # Başlangıçta otomatik snapshot çekme - KALDIRILDI!
        # self.after(1000, self.initial_etf_update)
        
    def initial_etf_update(self):
        """Başlangıçta ETF'leri güncelle - SADECE MANUEL ÇAĞRILDIĞINDA"""
        try:
            print("[ETF] 🚀 Başlangıç ETF güncellemesi...")
            
            # ETF'lere subscribe ol
            self.subscribe_etfs()
            
            # 3 saniye bekle
            self.after(3000, self.update_etf_display)
            
        except Exception as e:
            print(f"[ETF] ❌ Başlangıç güncelleme hatası: {e}")
            
    def load_etfs_from_csv(self):
        """ETF'leri CSV'den yükle"""
        try:
            df = pd.read_csv('etfs.csv')
            self.etf_list = df['PREF IBKR'].tolist()
            self.etf_df = df
            print(f"[ETF] ✅ {len(self.etf_list)} ETF yüklendi: {self.etf_list}")
        except Exception as e:
            print(f"[ETF] ❌ ETF CSV yükleme hatası: {e}")
            # Fallback: Sabit liste
            self.etf_list = ["SHY", "IEF", "TLT", "IWM", "KRE", "SPY", "PFF", "PGF", "IEI"]
            self.etf_df = pd.DataFrame({'PREF IBKR': self.etf_list})
        
    def setup_ui(self):
        """ETF panel UI'ını oluştur"""
        # Başlık
        title_label = ttk.Label(self, text="ETF Panel", font=('Arial', 10, 'bold'))
        title_label.pack(pady=2)
        
        # ETF tablosu (küçültülmüş)
        columns = ['Symbol', 'Last', 'Change', 'Change %']
        self.etf_table = ttk.Treeview(self, columns=columns, show='headings', height=4)
        
        # Kolon başlıkları ve genişlikleri
        for col in columns:
            self.etf_table.heading(col, text=col)
            if col == 'Symbol':
                self.etf_table.column(col, width=80, anchor='w')
            else:
                self.etf_table.column(col, width=100, anchor='center')
                
        self.etf_table.pack(fill='x', padx=5, pady=5)
        
        # İlk ETF'leri ekle
        self.update_etf_display()
        
    def subscribe_etfs(self):
        """ETF'lere subscribe ol - SADECE STREAMING"""
        print(f"[ETF] 🔄 {len(self.etf_list)} ETF'ye subscribe olunuyor...")
        
        # Sadece subscribe ol - SNAPSHOT YOK!
        for etf in self.etf_list:
            self.hammer.subscribe_symbol(etf)
            print(f"[ETF] ✅ {etf} subscribe edildi")
            
        print(f"[ETF] ✅ {len(self.etf_list)} ETF subscribe edildi")
        
    def update_etf_data(self, symbol, market_data):
        """ETF verilerini güncelle - STREAMING'den gelen veriler"""
        try:
            # Market data'dan değerleri al
            last = market_data.get('last', 0)
            prev_close = market_data.get('prevClose', 0)
            api_change = market_data.get('change', None)  # API'dan gelen change
            
            # Change hesapla - ÖNCE API'dan gelen change'i kullan
            change = 0
            change_pct = 0
            
            if api_change is not None:
                # API'dan gelen change değerini kullan
                change = api_change
                if prev_close > 0:
                    change_pct = (change / prev_close) * 100
            elif last > 0 and prev_close > 0:
                # Manuel hesapla
                change = last - prev_close
                change_pct = (change / prev_close) * 100
                
            # Veriyi sakla
            self.etf_data[symbol] = {
                'last': last,
                'prev_close': prev_close,
                'change': change,
                'change_pct': change_pct,
                'is_live': market_data.get('is_live', False)
            }
            
            # Debug
            print(f"[ETF] 📊 {symbol}: Last={last:.2f}, PrevClose={prev_close:.2f}, API_Change={api_change}, Final_Change={change:.2f}, Change%={change_pct:.2f}%")
            
        except Exception as e:
            print(f"[ETF] ❌ {symbol} veri güncelleme hatası: {e}")
            
    def update_etf_display(self):
        """ETF tablosunu güncelle - STREAMING'den gelen veriler"""
        print("[ETF] 🔄 update_etf_display() çağrıldı")
        
        # Tabloyu temizle
        for item in self.etf_table.get_children():
            self.etf_table.delete(item)
            
        # Her ETF için satır ekle
        for etf in self.etf_list:
            try:
                print(f"[ETF] 📊 {etf} için market data alınıyor...")
                
                # Market data'dan verileri al
                market_data = self.hammer.get_market_data(etf)
                
                if not market_data:
                    print(f"[ETF] ❌ {etf} için market data yok!")
                    row_values = [etf, "N/A", "N/A", "N/A"]
                    self.etf_table.insert('', 'end', values=row_values)
                    continue
                
                print(f"[ETF] ✅ {etf} market data: {market_data}")
                
                last = market_data.get('last', 0)
                prev_close = market_data.get('prevClose', 0)
                api_change = market_data.get('change', None)  # API'dan gelen change
                is_live = market_data.get('is_live', False)
                
                print(f"[ETF] 📊 {etf}: Last={last}, PrevClose={prev_close}, API_Change={api_change}")
                
                # Change hesapla - ÖNCE API'dan gelen change'i kullan
                change = 0
                change_pct = 0
                
                if api_change is not None:
                    print(f"[ETF] ✅ {etf} API'dan gelen change kullanılıyor: {api_change}")
                    # API'dan gelen change değerini kullan
                    change = api_change
                    if prev_close > 0:
                        change_pct = (change / prev_close) * 100
                elif last > 0 and prev_close > 0:
                    print(f"[ETF] ✅ {etf} manuel hesaplama yapılıyor")
                    # Manuel hesapla
                    change = last - prev_close
                    change_pct = (change / prev_close) * 100
                else:
                    print(f"[ETF] ❌ {etf} hesaplama yapılamıyor!")
                    if last == 0:
                        print(f"  - Last = 0")
                    if prev_close == 0:
                        print(f"  - PrevClose = 0")
                    if api_change is None:
                        print(f"  - API Change = None")
                    
                # Formatla - DOLAR bazında göster
                last_str = f"${last:.2f}" if last > 0 else "N/A"
                change_str = f"{change:+.2f}" if change != 0 else "N/A"
                change_pct_str = f"{change_pct:+.2f}%" if change_pct != 0 else "N/A"
                
                print(f"[ETF] 📋 {etf}: Last={last:.2f}, PrevClose={prev_close:.2f}, API_Change={api_change}, Final_Change={change:.2f}, Change%={change_pct:.2f}%")
                print(f"[ETF] 📋 {etf}: Last_Str='{last_str}', Change_Str='{change_str}', Change%_Str='{change_pct_str}'")
                
                # Renk belirle
                tags = ('live_data',)
                if change > 0:
                    tags += ('positive',)
                elif change < 0:
                    tags += ('negative',)
                
                # Satırı ekle
                row_values = [etf, last_str, change_str, change_pct_str]
                self.etf_table.insert('', 'end', values=row_values, tags=tags)
                
                print(f"[ETF] ✅ {etf} satırı eklendi: {row_values}")
                
            except Exception as e:
                print(f"[ETF] ❌ {etf} display hatası: {e}")
                row_values = [etf, "N/A", "N/A", "N/A"]
                self.etf_table.insert('', 'end', values=row_values)
                
        # Renkleri ayarla
        self.etf_table.tag_configure('live_data', background='lightgreen')
        self.etf_table.tag_configure('positive', foreground='green')
        self.etf_table.tag_configure('negative', foreground='red')
        
        print("[ETF] ✅ ETF tablosu güncellendi")