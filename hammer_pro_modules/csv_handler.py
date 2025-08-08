"""
Hammer Pro CSV Handler Module
CSV dosya yükleme ve işleme
"""

import pandas as pd
import logging
import os
from typing import Optional, Dict, Any, List
from config import HammerProConfig

class HammerProCSVHandler:
    """Hammer Pro CSV İşleyici"""
    
    def __init__(self):
        """CSV handler'ı başlat"""
        self.logger = logging.getLogger(__name__)
        self.csv_data: Optional[pd.DataFrame] = None
        
    def load_csv(self, file_path: str) -> bool:
        """CSV dosyasını yükle"""
        try:
            if not os.path.exists(file_path):
                self.logger.error(f"CSV dosyası bulunamadı: {file_path}")
                return False
            
            self.csv_data = pd.read_csv(file_path)
            
            # Gerekli sütunları kontrol et
            required_columns = [
                HammerProConfig.CSV_SETTINGS["symbol_column"],
                HammerProConfig.CSV_SETTINGS["final_thg_column"]
            ]
            
            missing_columns = [col for col in required_columns if col not in self.csv_data.columns]
            if missing_columns:
                self.logger.error(f"Eksik sütunlar: {missing_columns}")
                return False
            
            # Veri istatistikleri
            symbol_count = len(self.csv_data[HammerProConfig.CSV_SETTINGS["symbol_column"]].dropna().unique())
            self.logger.info(f"CSV yüklendi: {len(self.csv_data)} satır, {symbol_count} benzersiz sembol")
            
            return True
            
        except Exception as e:
            self.logger.error(f"CSV yükleme hatası: {e}")
            return False
    
    def get_csv_info(self) -> Optional[Dict[str, Any]]:
        """CSV dosya bilgilerini al"""
        if self.csv_data is None:
            return None
        
        try:
            symbol_column = HammerProConfig.CSV_SETTINGS["symbol_column"]
            final_thg_column = HammerProConfig.CSV_SETTINGS["final_thg_column"]
            
            info = {
                "total_rows": len(self.csv_data),
                "unique_symbols": len(self.csv_data[symbol_column].dropna().unique()),
                "columns": list(self.csv_data.columns),
                "final_thg_stats": {
                    "min": self.csv_data[final_thg_column].min(),
                    "max": self.csv_data[final_thg_column].max(),
                    "mean": self.csv_data[final_thg_column].mean(),
                    "median": self.csv_data[final_thg_column].median()
                }
            }
            
            return info
            
        except Exception as e:
            self.logger.error(f"CSV bilgisi alma hatası: {e}")
            return None
    
    def get_symbols_by_type(self, watchlist_type: str, max_symbols: int = 50) -> List[str]:
        """Watchlist türüne göre sembolleri al"""
        if self.csv_data is None:
            self.logger.error("CSV verisi yüklenmemiş")
            return []
        
        try:
            symbol_column = HammerProConfig.CSV_SETTINGS["symbol_column"]
            final_thg_column = HammerProConfig.CSV_SETTINGS["final_thg_column"]
            
            # Benzersiz sembolleri al
            symbols = self.csv_data[symbol_column].dropna().unique().tolist()
            
            if watchlist_type == "top_final_thg":
                # En yüksek FINAL_THG'ye göre sırala
                sorted_data = self.csv_data.sort_values(final_thg_column, ascending=False)
                symbols = sorted_data[symbol_column].dropna().unique().tolist()[:max_symbols]
                
            elif watchlist_type == "bottom_final_thg":
                # En düşük FINAL_THG'ye göre sırala
                sorted_data = self.csv_data.sort_values(final_thg_column, ascending=True)
                symbols = sorted_data[symbol_column].dropna().unique().tolist()[:max_symbols]
                
            elif watchlist_type == "custom_filter":
                # Özel filtreleme (gelecekte genişletilebilir)
                symbols = symbols[:max_symbols]
                
            else:
                # Tüm semboller (maksimum sayıya kadar)
                symbols = symbols[:max_symbols]
            
            self.logger.info(f"Filtrelenmiş {len(symbols)} sembol: {watchlist_type}")
            return symbols
            
        except Exception as e:
            self.logger.error(f"Sembol filtreleme hatası: {e}")
            return []
    
    def get_symbol_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Belirli bir sembolün verilerini al"""
        if self.csv_data is None:
            return None
        
        try:
            symbol_column = HammerProConfig.CSV_SETTINGS["symbol_column"]
            final_thg_column = HammerProConfig.CSV_SETTINGS["final_thg_column"]
            company_column = HammerProConfig.CSV_SETTINGS["company_column"]
            
            # Sembol verilerini bul
            symbol_data = self.csv_data[self.csv_data[symbol_column] == symbol]
            
            if symbol_data.empty:
                return None
            
            row = symbol_data.iloc[0]
            
            data = {
                "symbol": symbol,
                "final_thg": row.get(final_thg_column, 0),
                "company": row.get(company_column, "N/A")
            }
            
            # Diğer sütunları da ekle
            for col in self.csv_data.columns:
                if col not in [symbol_column, final_thg_column, company_column]:
                    data[col.lower()] = row.get(col, 0)
            
            return data
            
        except Exception as e:
            self.logger.error(f"Sembol verisi alma hatası: {e}")
            return None
    
    def get_top_symbols(self, n: int = 10, by_column: str = None) -> List[Dict[str, Any]]:
        """En iyi sembolleri al"""
        if self.csv_data is None:
            return []
        
        try:
            if by_column is None:
                by_column = HammerProConfig.CSV_SETTINGS["final_thg_column"]
            
            # Sütuna göre sırala
            sorted_data = self.csv_data.sort_values(by_column, ascending=False)
            
            top_symbols = []
            symbol_column = HammerProConfig.CSV_SETTINGS["symbol_column"]
            
            for _, row in sorted_data.head(n).iterrows():
                symbol = row[symbol_column]
                symbol_data = self.get_symbol_data(symbol)
                if symbol_data:
                    top_symbols.append(symbol_data)
            
            return top_symbols
            
        except Exception as e:
            self.logger.error(f"En iyi semboller alma hatası: {e}")
            return []
    
    def validate_csv_format(self) -> bool:
        """CSV formatını doğrula"""
        if self.csv_data is None:
            return False
        
        try:
            required_columns = [
                HammerProConfig.CSV_SETTINGS["symbol_column"],
                HammerProConfig.CSV_SETTINGS["final_thg_column"]
            ]
            
            # Gerekli sütunları kontrol et
            for col in required_columns:
                if col not in self.csv_data.columns:
                    self.logger.error(f"Gerekli sütun eksik: {col}")
                    return False
            
            # Veri kalitesini kontrol et
            symbol_column = HammerProConfig.CSV_SETTINGS["symbol_column"]
            if self.csv_data[symbol_column].isna().all():
                self.logger.error("Sembol sütunu boş")
                return False
            
            self.logger.info("CSV formatı geçerli")
            return True
            
        except Exception as e:
            self.logger.error(f"CSV format doğrulama hatası: {e}")
            return False 