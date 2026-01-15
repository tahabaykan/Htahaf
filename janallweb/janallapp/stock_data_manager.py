"""
Stock Data Manager - Hisse verilerini yöneten ve erişim sağlayan sınıf

!!! ÖNEMLİ DOSYA YOLU UYARISI !!!
=================================
BÜTÜN CSV OKUMA VE CSV KAYDETME İŞLEMLERİ StockTracker DİZİNİNE YAPILMALI!!
StockTracker/janall/ dizinine YAPILMAMALI!!!
KARIŞASAYI ÖNLEMEK İÇİN BU KURALA MUTLAKA UYULACAK!

Bu modül CSV verilerini yönetir, tüm dosya yolları ana dizine göre olmalı!
=================================
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, List
import time

class StockDataManager:
    """
    Ana sayfada görünen her hisse için tüm verileri yöneten ve erişim sağlayan sınıf.
    Her hisse sembolü için bid, ask, last, prev_close ve diğer tüm kolon verilerini saklar.
    """
    
    def __init__(self):
        # Her hisse sembolü için tüm verileri saklayan ana dictionary
        self.stock_data: Dict[str, Dict[str, Any]] = {}
        
        # Son güncelleme zamanları
        self.last_update_times: Dict[str, float] = {}
        
        # Veri geçerlilik süresi (saniye)
        self.data_validity_duration = 30.0  # 30 saniye
        
        # Ana sayfa tablosundan gelen veriler
        self.main_table_data: pd.DataFrame = pd.DataFrame()
        
        # CSV dosyalarından gelen ek veriler
        self.csv_data: Dict[str, pd.DataFrame] = {}
        
        print("[STOCK_DATA_MANAGER] OK Stock Data Manager baslatildi")
    
    def update_stock_data_from_main_table(self, table_data: pd.DataFrame, columns: List[str]):
        """
        Ana sayfa tablosundan gelen verileri günceller
        
        Args:
            table_data: Ana tablodaki veriler (DataFrame)
            columns: Tablo kolonları
        """
        try:
            if table_data.empty:
                print("[STOCK_DATA_MANAGER] ⚠️ Ana tablo verisi boş")
                return
            
            # Debug mesajı kapatıldı - performans için
            # print(f"[STOCK_DATA_MANAGER] 🔄 Ana tablo verileri güncelleniyor... {len(table_data)} hisse")
            
            # Her hisse için verileri güncelle
            for _, row in table_data.iterrows():
                symbol = row.get('PREF IBKR', '')
                if not symbol or pd.isna(symbol):
                    continue
                
                # Bu hisse için veri dictionary'si oluştur
                if symbol not in self.stock_data:
                    self.stock_data[symbol] = {}
                
                # Tüm kolon verilerini sakla
                for col in columns:
                    if col in row and not pd.isna(row[col]):
                        self.stock_data[symbol][col] = row[col]
                
                # Özel kolonları ayrı ayrı sakla (kolay erişim için)
                special_columns = {
                    'bid': 'Bid',
                    'ask': 'Ask', 
                    'last': 'Last',
                    'prev_close': 'prev_close',
                    'volume': 'Volume',
                    'symbol': 'PREF IBKR',
                    'cmon': 'CMON',
                    'cgrup': 'CGRUP',
                    'final_thg': 'FINAL_THG',
                    'avg_adv': 'AVG_ADV',
                    'smi': 'SMI',
                    'short_final': 'SHORT_FINAL'
                }
                
                for key, col_name in special_columns.items():
                    if col_name in row and not pd.isna(row[col_name]):
                        self.stock_data[symbol][key] = row[col_name]
                
                # Skor kolonlarını sakla
                score_columns = [
                    'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor', 
                    'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor',
                    'Final_SAS_skor', 'Final_SFS_skor', 'Final_SBS_skor',
                    'Bid_buy_ucuzluk_skoru', 'Front_buy_ucuzluk_skoru', 'Ask_buy_ucuzluk_skoru',
                    'Ask_sell_pahalilik_skoru', 'Front_sell_pahalilik_skoru', 'Bid_sell_pahalilik_skoru',
                    'Spread'
                ]
                
                for score_col in score_columns:
                    if score_col in row and not pd.isna(row[score_col]):
                        self.stock_data[symbol][score_col] = row[score_col]
                
                # Benchmark verilerini sakla
                benchmark_columns = ['Benchmark_Type', 'Benchmark_Chg']
                for bench_col in benchmark_columns:
                    if bench_col in row and not pd.isna(row[bench_col]):
                        self.stock_data[symbol][bench_col] = row[bench_col]
                
                # Güncelleme zamanını kaydet
                self.last_update_times[symbol] = time.time()
            
            # Ana tablo verilerini sakla
            self.main_table_data = table_data.copy()
            
            # Debug mesajı kapatıldı - performans için
            # print(f"[STOCK_DATA_MANAGER] ✅ {len(self.stock_data)} hisse için veriler güncellendi")
            
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ Ana tablo verileri güncellenirken hata: {e}")
    
    def update_stock_data_from_csv(self, csv_name: str, csv_data: pd.DataFrame):
        """
        CSV dosyasından gelen verileri günceller
        
        Args:
            csv_name: CSV dosya adı
            csv_data: CSV verileri
        """
        try:
            if csv_data.empty:
                print(f"[STOCK_DATA_MANAGER] ⚠️ {csv_name} CSV verisi boş")
                return
            
            # Debug mesajı kapatıldı - performans için
            # print(f"[STOCK_DATA_MANAGER] 🔄 {csv_name} CSV verileri güncelleniyor... {len(csv_data)} hisse")
            
            # CSV verilerini sakla
            self.csv_data[csv_name] = csv_data.copy()
            
            # Her hisse için CSV verilerini ekle
            for _, row in csv_data.iterrows():
                symbol = row.get('PREF IBKR', '')
                if not symbol or pd.isna(symbol):
                    continue
                
                # Bu hisse için veri dictionary'si oluştur
                if symbol not in self.stock_data:
                    self.stock_data[symbol] = {}
                
                # CSV'deki tüm kolonları sakla
                for col in csv_data.columns:
                    if col in row and not pd.isna(row[col]):
                        self.stock_data[symbol][col] = row[col]
                
                # Güncelleme zamanını kaydet
                self.last_update_times[symbol] = time.time()
            
            # Debug mesajı kapatıldı - performans için
            # print(f"[STOCK_DATA_MANAGER] ✅ {csv_name} CSV verileri güncellendi")
            
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ {csv_name} CSV verileri güncellenirken hata: {e}")
    
    def get_stock_data(self, symbol: str, column: str = None) -> Any:
        """
        Belirli bir hisse için veri döndürür
        
        Args:
            symbol: Hisse sembolü
            column: İstenen kolon (None ise tüm veriler)
            
        Returns:
            İstenen veri veya tüm veriler
        """
        try:
            if symbol not in self.stock_data:
                print(f"[STOCK_DATA_MANAGER] ⚠️ {symbol} için veri bulunamadı")
                return None
            
            # Veri geçerliliğini kontrol et
            if self._is_data_expired(symbol):
                print(f"[STOCK_DATA_MANAGER] ⚠️ {symbol} için veri süresi dolmuş")
                return None
            
            if column:
                # Belirli bir kolon için veri döndür
                return self.stock_data[symbol].get(column, None)
            else:
                # Tüm verileri döndür
                return self.stock_data[symbol].copy()
                
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ {symbol} veri alınırken hata: {e}")
            return None
    
    def get_stock_column_data(self, column: str) -> Dict[str, Any]:
        """
        Belirli bir kolon için tüm hisselerin verilerini döndürür
        
        Args:
            column: İstenen kolon adı
            
        Returns:
            {symbol: value} formatında dictionary
        """
        try:
            result = {}
            current_time = time.time()
            
            for symbol, data in self.stock_data.items():
                # Veri geçerliliğini kontrol et
                if self._is_data_expired(symbol):
                    continue
                
                if column in data:
                    result[symbol] = data[column]
            
            print(f"[STOCK_DATA_MANAGER] ✅ {column} kolonu için {len(result)} hisse verisi döndürüldü")
            return result
            
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ {column} kolonu verileri alınırken hata: {e}")
            return {}
    
    def get_stock_price_data(self, symbol: str) -> Dict[str, float]:
        """
        Hisse için fiyat verilerini döndürür
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Fiyat verileri dictionary'si
        """
        try:
            if symbol not in self.stock_data:
                return {}
            
            price_data = {}
            price_columns = {
                'bid': 'Bid',
                'ask': 'Ask',
                'last': 'Last', 
                'prev_close': 'prev_close'
            }
            
            for key, col_name in price_columns.items():
                if col_name in self.stock_data[symbol]:
                    value = self.stock_data[symbol][col_name]
                    if isinstance(value, (int, float)) and not pd.isna(value):
                        price_data[key] = float(value)
                    elif isinstance(value, str) and value != 'N/A':
                        try:
                            price_data[key] = float(value)
                        except:
                            pass
            
            return price_data
            
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ {symbol} fiyat verileri alınırken hata: {e}")
            return {}
    
    def get_stock_scores(self, symbol: str) -> Dict[str, float]:
        """
        Hisse için skor verilerini döndürür
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            Skor verileri dictionary'si
        """
        try:
            if symbol not in self.stock_data:
                return {}
            
            score_data = {}
            score_columns = [
                'Final_BB_skor', 'Final_FB_skor', 'Final_AB_skor',
                'Final_AS_skor', 'Final_FS_skor', 'Final_BS_skor',
                'Final_SAS_skor', 'Final_SFS_skor', 'Final_SBS_skor'
            ]
            
            for score_col in score_columns:
                if score_col in self.stock_data[symbol]:
                    value = self.stock_data[symbol][score_col]
                    if isinstance(value, (int, float)) and not pd.isna(value):
                        score_data[score_col] = float(value)
                    elif isinstance(value, str) and value != 'N/A':
                        try:
                            score_data[score_col] = float(value)
                        except:
                            pass
            
            return score_data
            
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ {symbol} skor verileri alınırken hata: {e}")
            return {}
    
    def get_all_stocks(self) -> List[str]:
        """
        Tüm hisse sembollerini döndürür
        
        Returns:
            Hisse sembolleri listesi
        """
        return list(self.stock_data.keys())
    
    def get_stocks_with_column(self, column: str, value=None) -> List[str]:
        """
        Belirli bir kolonda belirli değere sahip hisseleri döndürür
        
        Args:
            column: Kolon adı
            value: Aranan değer (None ise sadece kolonu olan hisseler)
            
        Returns:
            Hisse sembolleri listesi
        """
        try:
            result = []
            current_time = time.time()
            
            for symbol, data in self.stock_data.items():
                # Veri geçerliliğini kontrol et
                if self._is_data_expired(symbol):
                    continue
                
                if column in data:
                    if value is None:
                        result.append(symbol)
                    elif data[column] == value:
                        result.append(symbol)
            
            return result
            
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ {column} kolonu için hisse arama hatası: {e}")
            return []
    
    def search_stocks(self, search_term: str) -> List[str]:
        """
        Arama terimi ile hisse arama
        
        Args:
            search_term: Arama terimi
            
        Returns:
            Eşleşen hisse sembolleri listesi
        """
        try:
            search_term = search_term.upper()
            result = []
            
            for symbol in self.stock_data.keys():
                if search_term in symbol.upper():
                    result.append(symbol)
            
            return result
            
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ Hisse arama hatası: {e}")
            return []
    
    def get_data_summary(self) -> Dict[str, Any]:
        """
        Veri yönetici durumu özeti
        
        Returns:
            Durum özeti
        """
        try:
            current_time = time.time()
            valid_stocks = 0
            expired_stocks = 0
            
            for symbol in self.stock_data.keys():
                if self._is_data_expired(symbol):
                    expired_stocks += 1
                else:
                    valid_stocks += 1
            
            return {
                'total_stocks': len(self.stock_data),
                'valid_stocks': valid_stocks,
                'expired_stocks': expired_stocks,
                'csv_files': list(self.csv_data.keys()),
                'last_update': max(self.last_update_times.values()) if self.last_update_times else 0
            }
            
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ Özet alınırken hata: {e}")
            return {}
    
    def clear_expired_data(self):
        """Süresi dolmuş verileri temizler"""
        try:
            current_time = time.time()
            expired_symbols = []
            
            for symbol, last_update in self.last_update_times.items():
                if self._is_data_expired(symbol):
                    expired_symbols.append(symbol)
            
            for symbol in expired_symbols:
                del self.stock_data[symbol]
                del self.last_update_times[symbol]
            
            if expired_symbols:
                print(f"[STOCK_DATA_MANAGER] 🗑️ {len(expired_symbols)} süresi dolmuş hisse verisi temizlendi")
                
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ Süresi dolmuş veriler temizlenirken hata: {e}")
    
    def _is_data_expired(self, symbol: str) -> bool:
        """
        Veri süresinin dolup dolmadığını kontrol eder
        
        Args:
            symbol: Hisse sembolü
            
        Returns:
            True if expired, False otherwise
        """
        if symbol not in self.last_update_times:
            return True
        
        current_time = time.time()
        last_update = self.last_update_times[symbol]
        
        return (current_time - last_update) > self.data_validity_duration
    
    def export_to_csv(self, filename: str = None):
        """
        Tüm verileri CSV olarak export eder
        
        Args:
            filename: Export dosya adı
        """
        try:
            if not filename:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"stock_data_export_{timestamp}.csv"
            
            # Veri listesi oluştur
            export_data = []
            for symbol, data in self.stock_data.items():
                row = {'Symbol': symbol}
                row.update(data)
                export_data.append(row)
            
            # DataFrame oluştur ve export et
            df = pd.DataFrame(export_data)
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            
            print(f"[STOCK_DATA_MANAGER] ✅ Veriler {filename} dosyasına export edildi")
            
        except Exception as e:
            print(f"[STOCK_DATA_MANAGER] ❌ CSV export hatası: {e}")



