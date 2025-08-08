"""
ETF panel modülü.
"""

import tkinter as tk
from tkinter import ttk
import pandas as pd
import numpy as np
import time

class ETFPanel(ttk.Frame):
    def __init__(self, parent, hammer_client):
        super().__init__(parent)
        self.hammer = hammer_client
        self.etf_data = {}  # ETF verilerini saklamak için
        self.prev_prices = {}  # Önceki fiyatları saklamak için
        self.etf_prev_close_data = {}  # ETF'ler için prev_close verileri
        # Artık snapshot sistemi yok - L1 streaming kullanıyoruz
        
        # ETF'leri CSV'den yükle
        self.load_etfs_from_csv()
        
        # ETF prev_close verilerini yükle
        self.load_etf_prev_close_data()
        
        self.setup_ui()
        
        # ETF'ler için L1 streaming başlat
        self.subscribe_etfs()
        
    def load_etf_prev_close_data(self):
        """ETF'ler için prev_close verilerini janeketfs.csv'den yükle"""
        try:
            import os
            if os.path.exists('janeketfs.csv'):
                import pandas as pd
                etf_df = pd.read_csv('janeketfs.csv')
                for _, row in etf_df.iterrows():
                    symbol = row['Symbol']
                    prev_close = row['prev_close']
                    if prev_close > 0:
                        self.etf_prev_close_data[symbol] = prev_close
                print(f"[ETF] ✅ ETF prev_close verileri yüklendi: {len(self.etf_prev_close_data)} ETF")
            else:
                print("[ETF] ⚠️ janeketfs.csv dosyası bulunamadı")
        except Exception as e:
            print(f"[ETF] ❌ ETF prev_close verileri yüklenirken hata: {e}")
    
    def get_etf_prev_close(self, symbol):
        """Bir ETF için prev_close değerini al"""
        return self.etf_prev_close_data.get(symbol, 0)
        
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
        
        # ETF tablosu
        columns = ['Symbol', 'Last', 'Change', 'Change %', 'Prev Close']
        self.etf_table = ttk.Treeview(self, columns=columns, show='headings', height=8)
        
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
        """ETF'ler için L1 streaming subscribe ol"""
        # L1 streaming kullan (Last + Change için)
        for etf in self.etf_list:
            self.hammer.subscribe_symbol(etf)
            
    def safe_float(self, value, fallback=0):
        """Güvenli float çevirme - bozuk veri gelirse fallback kullan"""
        try:
            if value is None or value == '' or value == 'N/A':
                return fallback
            # String'se float'a çevir
            if isinstance(value, str):
                # Bilimsel notasyon (E) varsa parse et
                return float(value)
            return float(value)
        except (ValueError, TypeError):
            return fallback
    
    def update_etf_data(self, symbol, market_data):
        """ETF verilerini güncelle - FALLBACK mekanizması ile"""
        try:
            # Eski veriyi koru (fallback için)
            old_data = self.etf_data.get(symbol, {})
            old_last = old_data.get('last', 0)
            old_prev_close = old_data.get('prev_close', 0)
            
            # Market data'dan güvenli şekilde al
            last_raw = market_data.get('last', 0)
            prev_close_raw = market_data.get('prevClose', 0)
            
            # Güvenli float çevirme - bozuksa eski değeri koru
            last = self.safe_float(last_raw, old_last)
            prev_close = self.safe_float(prev_close_raw, old_prev_close)
            
            # Eğer yeni değer 0 ya da bozuksa eski değeri koru
            if last <= 0 and old_last > 0:
                last = old_last
            if prev_close <= 0 and old_prev_close > 0:
                prev_close = old_prev_close
            
            # PrevClose yoksa snapshot ile al (ETF'ler için kritik!)
            if prev_close <= 0 and last > 0:
                # ETF snapshot mesajı kaldırıldı
                self.hammer.get_symbol_snapshot(symbol)
                # Snapshot'tan güncel prev_close al
                updated_data = self.hammer.get_market_data(symbol)
                if updated_data:
                    updated_prev_close = self.safe_float(updated_data.get('prevClose', 0), 0)
                    if updated_prev_close > 0:
                        prev_close = updated_prev_close
            
            # Change hesapla
            change_dollars = 0
            if last > 0 and prev_close > 0:
                change_dollars = last - prev_close
            elif market_data.get('change') is not None:
                change_dollars = self.safe_float(market_data.get('change', 0), 0)
                
            # Change percentage hesapla
            change_pct = 0
            if prev_close > 0 and change_dollars != 0:
                change_pct = (change_dollars / prev_close) * 100
                
            # Veriyi sakla (sadece geçerli değerleri)
            if last > 0:  # Last price geçerliyse kaydet
                self.etf_data[symbol] = {
                    'last': last,
                    'prev_close': prev_close,
                    'change_dollars': change_dollars,
                    'change_pct': change_pct,
                    'is_live': market_data.get('is_live', False)
                }
            
        except Exception as e:
            print(f"[ETF] ❌ {symbol} veri güncelleme hatası: {e} - Eski veri korunuyor")
            
    def update_etf_display(self):
        """ETF tablosunu güncelle (prevClose kullanarak)"""
        # Tabloyu temizle
        for item in self.etf_table.get_children():
            self.etf_table.delete(item)
            
        # Her ETF için satır ekle
        for etf in self.etf_list:
            try:
                # Önce kendi cache'imizden kontrol et (güncel/güvenli veri)
                if etf in self.etf_data:
                    etf_data = self.etf_data[etf]
                    last = etf_data.get('last', 0)
                    is_live = etf_data.get('is_live', False)
                else:
                    # Cache'de yoksa market data'dan al (ilk defa)
                    market_data = self.hammer.get_market_data(etf)
                    if market_data:
                        last = self.safe_float(market_data.get('last', 0), 0)
                        is_live = market_data.get('is_live', False)
                    else:
                        # Hiç veri yok - skip
                        continue
                
                # Prev Close değerini CSV'den al
                csv_prev_close = self.get_etf_prev_close(etf)
                
                # Change hesaplama - CSV'den alınan prev_close ile
                change_dollar = 0
                change_pct = 0
                if last > 0 and csv_prev_close > 0:
                    change_dollar = last - csv_prev_close
                    change_pct = (change_dollar / csv_prev_close) * 100
                
                # Artık L1 streaming kullanıyoruz, snapshot yok
                    
                # GÜVENLİ FORMATLAMA - BİR DEĞER BOZUKSA "N/A" YERİNE SON DEĞERİ KORU
                try:
                    last_str = f"${last:.2f}" if last > 0 else "N/A"
                except:
                    last_str = "N/A"
                
                try:
                    # Change'i dolar bazında göster - 0 değilse göster
                    if abs(change_dollar) > 0.0001:
                        change_str = f"{change_dollar:+.4f}"
                    else:
                        change_str = "0.0000"  # "N/A" değil 0 göster
                except:
                    change_str = "0.0000"
                    
                try:
                    # Yüzde değişimi - 0 değilse göster
                    if abs(change_pct) > 0.001:
                        change_pct_str = f"{change_pct:+.2f}%"
                    else:
                        change_pct_str = "0.00%"  # "N/A" değil 0% göster
                except:
                    change_pct_str = "0.00%"
                
                # Renk belirle
                tags = ()
                if is_live:
                    tags += ('live_data',)
                    
                if change_dollar > 0:
                    tags += ('positive',)
                elif change_dollar < 0:
                    tags += ('negative',)
                
                # Prev Close değerini CSV'den al
                csv_prev_close = self.get_etf_prev_close(etf)
                if csv_prev_close > 0:
                    prev_close_str = f"${csv_prev_close:.2f}"
                else:
                    prev_close_str = "N/A"
                
                # Satırı ekle
                row_values = [etf, last_str, change_str, change_pct_str, prev_close_str]
                self.etf_table.insert('', 'end', values=row_values, tags=tags)
                
                # Debug çıktıları kaldırıldı
                
            except Exception as e:
                print(f"[ETF] ❌ {etf} display hatası: {e}")
                row_values = [etf, "N/A", "N/A", "N/A", "N/A"]
                self.etf_table.insert('', 'end', values=row_values)
                
        # Renkleri ayarla
        self.etf_table.tag_configure('live_data', background='lightgreen')
        self.etf_table.tag_configure('positive', foreground='darkgreen', font=('Arial', 8, 'bold'))
        self.etf_table.tag_configure('negative', foreground='darkred', font=('Arial', 8, 'bold'))
    
    # SNAPSHOT FONKSİYONLARI KALDIRILDI - Artık L1 streaming kullanıyoruz!