import pandas as pd
import os
from pathlib import Path
import glob
from .static_data_store import StaticDataStore

class CSVService:
    def __init__(self, base_dir=None):
        # Olası yollar
        possible_paths = [
            Path(r"C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janall"),  # Kullanıcının tam yolu
            Path(os.getcwd()) / 'janall',
            Path(os.getcwd()).parent / 'janall',
            Path(os.getcwd()),  # Belki direkt buradadır
        ]
        
        self.janall_dir = None
        for path in possible_paths:
            if path.exists() and (path / 'janallapp').exists():
                self.janall_dir = path
                break
            # Alternatif: janallapp olmasa bile çok sayıda csv varsa kabul et
            if path.exists():
                csv_count = len(list(path.glob('*.csv')))
                if csv_count > 50:
                    self.janall_dir = path
                    break
        
        if not self.janall_dir:
            # Fallback
            self.janall_dir = Path(r"C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janall")
            
        print(f"[CSVService] JanAll dizini: {self.janall_dir}")
        self.current_df = None
        
        # Initialize StaticDataStore
        self.static_store = StaticDataStore()

    def set_current_dataframe(self, df):
        self.current_df = df

    def get_current_dataframe(self):
        return self.current_df

    def _find_file(self, filename):
        if not self.janall_dir:
            return None
        
        # Dosya adını temizle (klasör adı varsa kaldır)
        clean_filename = os.path.basename(filename)
        
        # Direkt dene
        filepath = self.janall_dir / clean_filename
        if filepath.exists():
            return filepath
            
        # Alt klasörlerde ara (gerekirse)
        return None

    def load_csv(self, filename):
        try:
            filepath = self._find_file(filename)
            if not filepath:
                print(f"[CSVService] ❌ Dosya bulunamadı: {filename} (Dizin: {self.janall_dir})")
                return None
                
            print(f"[CSVService] 📊 Yükleniyor: {filepath}")
            # Encoding denemeleri
            try:
                df = pd.read_csv(filepath, encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(filepath, encoding='latin-1')
                
            print(f"[CSVService] ✅ Yüklendi: {len(df)} satır")
            self.current_df = df
            
            # Also load into StaticDataStore if this is janalldata.csv
            if filename == 'janalldata.csv' or 'janalldata' in filename.lower():
                print(f"[CSVService] 📦 Loading into StaticDataStore...")
                self.static_store.load_csv(str(filepath))
            
            return df
        except Exception as e:
            print(f"[CSVService] ❌ Yükleme hatası: {e}")
            return None
    
    def get_static_data(self, pref_ibkr: str):
        """
        Get static data for a symbol from StaticDataStore.
        
        Args:
            pref_ibkr: PREF_IBKR symbol
            
        Returns:
            Dictionary of static fields or None
        """
        return self.static_store.get_static_data(pref_ibkr)
    
    def get_static_store(self):
        """Get the StaticDataStore instance"""
        return self.static_store

    def list_csv_files(self):
        try:
            if not self.janall_dir:
                return []
            
            # Tüm CSV'leri bul
            all_csvs = list(self.janall_dir.glob("*.csv"))
            
            # Sadece janek_ssfinek ile başlayanları filtrele (daha hızlı UI için)
            filtered_files = [f.name for f in all_csvs if f.name.startswith("janek_ssfinek")]
            
            if not filtered_files:
                # Hiç yoksa hepsini döndür (fallback)
                return sorted([f.name for f in all_csvs])
                
            return sorted(filtered_files)
        except Exception as e:
            print(f"[CSVService] Listeleme hatası: {e}")
            return []
