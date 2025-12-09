#!/usr/bin/env python3
"""
CSV'den Prev Close Değerleri Alma Modülü

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ njanall DİZİNİNE YAPILMALI!!
njanall dizininde çalışması için path_helper kullanılmalı!

Bu modül CSV dosyasından Prev Close değerlerini okur:
✅ DOĞRU: get_csv_path("janalldata.csv") (njanall dizininde)
❌ YANLIŞ: "janalldata.csv" (StockTracker dizininde)
=================================
"""

import pandas as pd
import os
from .path_helper import get_csv_path

class CSVPrevCloseManager:
    """CSV dosyasından Prev Close değerlerini yöneten sınıf"""
    
    def __init__(self, csv_file_path=None):
        """CSV dosyasını yükle"""
        if csv_file_path is None:
            csv_file_path = get_csv_path("janalldata.csv")
        self.csv_file_path = csv_file_path
        self.csv_data = None
        self.load_csv_data()
    
    def load_csv_data(self):
        """CSV dosyasını yükle"""
        try:
            if os.path.exists(self.csv_file_path):
                self.csv_data = pd.read_csv(self.csv_file_path)
                print(f"✅ CSV dosyası yüklendi: {len(self.csv_data)} satır")
            else:
                print(f"❌ CSV dosyası bulunamadı: {self.csv_file_path}")
                self.csv_data = pd.DataFrame()
        except Exception as e:
            print(f"❌ CSV yükleme hatası: {e}")
            self.csv_data = pd.DataFrame()
    
    def get_prev_close(self, symbol):
        """Sembol için Prev Close değerini al"""
        if self.csv_data is None or self.csv_data.empty:
            return 0
        
        try:
            # PREF IBKR sütununda sembolü ara
            symbol_row = self.csv_data[self.csv_data['PREF IBKR'] == symbol]
            
            if not symbol_row.empty:
                # Last Price sütunundan değeri al
                last_price = symbol_row.iloc[0]['Last Price']
                if pd.notna(last_price) and last_price > 0:
                    return float(last_price)
            
            return 0
            
        except Exception as e:
            print(f"❌ Prev Close alma hatası ({symbol}): {e}")
            return 0
    
    def get_all_symbols(self):
        """CSV'deki tüm sembolleri al"""
        if self.csv_data is None or self.csv_data.empty:
            return []
        
        try:
            symbols = self.csv_data['PREF IBKR'].dropna().tolist()
            return symbols
        except Exception as e:
            print(f"❌ Sembol listesi alma hatası: {e}")
            return []
    
    def get_symbols_with_prev_close(self):
        """Prev Close değeri olan sembolleri al"""
        if self.csv_data is None or self.csv_data.empty:
            return {}
        
        try:
            result = {}
            for _, row in self.csv_data.iterrows():
                symbol = row['PREF IBKR']
                last_price = row['Last Price']
                
                if pd.notna(symbol) and pd.notna(last_price) and last_price > 0:
                    result[symbol] = float(last_price)
            
            return result
            
        except Exception as e:
            print(f"❌ Prev Close listesi alma hatası: {e}")
            return {}

# Test fonksiyonu
def test_csv_prev_close():
    """CSV Prev Close testi"""
    print("=== CSV Prev Close Testi ===")
    
    manager = CSVPrevCloseManager()
    
    # Test sembolleri
    test_symbols = ["AHL PRE", "SPY", "AAPL", "ATH PRD"]
    
    for symbol in test_symbols:
        prev_close = manager.get_prev_close(symbol)
        print(f"📊 {symbol}: Prev Close = {prev_close}")
    
    # Tüm sembolleri listele
    all_symbols = manager.get_all_symbols()
    print(f"📋 Toplam {len(all_symbols)} sembol bulundu")
    
    # Prev Close'lu sembolleri listele
    prev_close_symbols = manager.get_symbols_with_prev_close()
    print(f"📊 {len(prev_close_symbols)} sembolde Prev Close değeri var")

if __name__ == "__main__":
    test_csv_prev_close()
