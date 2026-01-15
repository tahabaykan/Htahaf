"""
Static Data Store
Loads and stores static daily metrics from janalldata.csv
Keyed by PREF_IBKR (primary key)
"""

import pandas as pd
import os
from pathlib import Path
from typing import Dict, Optional, Any


class StaticDataStore:
    """
    Stores static daily metrics loaded from CSV.
    Data is loaded once per day and keyed by PREF_IBKR.
    """
    
    # Required static fields
    REQUIRED_FIELDS = [
        'PREF IBKR',  # Primary key (note: space in column name)
        'prev_close',
        'CMON',
        'CGRUP',
        'FINAL_THG',
        'SHORT_FINAL',
        'AVG_ADV',
        'SMI',
        'SMA63 chg',  # Note: space in column name
        'SMA246 chg'  # Note: space in column name
    ]
    
    def __init__(self, csv_path: Optional[str] = None):
        """
        Initialize StaticDataStore.
        
        Args:
            csv_path: Path to janalldata.csv. If None, will search for it.
        """
        self.data: Dict[str, Dict[str, Any]] = {}  # {PREF_IBKR: {field: value}}
        self.csv_path = csv_path
        self.loaded = False
        
    def _find_csv_file(self) -> Optional[Path]:
        """Find janalldata.csv file"""
        possible_paths = [
            Path(r"C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janall") / 'janalldata.csv',
            Path(os.getcwd()) / 'janall' / 'janalldata.csv',
            Path(os.getcwd()) / 'janalldata.csv',
            Path(os.getcwd()).parent / 'janall' / 'janalldata.csv',
            Path(__file__).parent.parent / 'janallapp' / 'janalldata.csv',
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        return None
    
    def load_csv(self, csv_path: Optional[str] = None) -> bool:
        """
        Load static data from CSV file.
        
        Args:
            csv_path: Path to CSV file. If None, will search for janalldata.csv
            
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            if csv_path:
                filepath = Path(csv_path)
            elif self.csv_path:
                filepath = Path(self.csv_path)
            else:
                filepath = self._find_csv_file()
            
            if not filepath or not filepath.exists():
                print(f"[StaticDataStore] ❌ CSV file not found")
                return False
            
            print(f"[StaticDataStore] 📊 Loading: {filepath}")
            
            # Try different encodings
            try:
                df = pd.read_csv(filepath, encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(filepath, encoding='latin-1')
            
            # Check required columns
            missing_cols = [col for col in self.REQUIRED_FIELDS if col not in df.columns]
            if missing_cols:
                print(f"[StaticDataStore] ⚠️ Missing columns: {missing_cols}")
                # Continue anyway, but log warning
            
            # Clear existing data
            self.data = {}
            
            # Load data keyed by PREF_IBKR
            pref_ibkr_col = 'PREF IBKR'
            if pref_ibkr_col not in df.columns:
                print(f"[StaticDataStore] ❌ Primary key column '{pref_ibkr_col}' not found")
                return False
            
            for _, row in df.iterrows():
                pref_ibkr = str(row[pref_ibkr_col]).strip()
                if not pref_ibkr or pref_ibkr == 'nan':
                    continue
                
                # Extract required fields
                static_data = {}
                for field in self.REQUIRED_FIELDS:
                    if field in df.columns:
                        value = row[field]
                        # Convert to appropriate type
                        if pd.isna(value):
                            static_data[field] = None
                        elif field in ['prev_close', 'CMON', 'FINAL_THG', 'SHORT_FINAL', 
                                      'AVG_ADV', 'SMI', 'SMA63 chg', 'SMA246 chg']:
                            try:
                                static_data[field] = float(value)
                            except (ValueError, TypeError):
                                static_data[field] = None
                        else:
                            static_data[field] = str(value) if value else None
                    else:
                        static_data[field] = None
                
                self.data[pref_ibkr] = static_data
            
            self.loaded = True
            print(f"[StaticDataStore] ✅ Loaded {len(self.data)} symbols")
            return True
            
        except Exception as e:
            print(f"[StaticDataStore] ❌ Load error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_static_data(self, pref_ibkr: str) -> Optional[Dict[str, Any]]:
        """
        Get static data for a symbol.
        
        Args:
            pref_ibkr: PREF_IBKR symbol (primary key)
            
        Returns:
            Dictionary of static fields, or None if not found
        """
        return self.data.get(pref_ibkr)
    
    def get_all_symbols(self) -> list:
        """Get list of all PREF_IBKR symbols"""
        return list(self.data.keys())
    
    def is_loaded(self) -> bool:
        """Check if data has been loaded"""
        return self.loaded
    
    def get_field(self, pref_ibkr: str, field: str) -> Optional[Any]:
        """
        Get a specific field for a symbol.
        
        Args:
            pref_ibkr: PREF_IBKR symbol
            field: Field name
            
        Returns:
            Field value or None
        """
        symbol_data = self.get_static_data(pref_ibkr)
        if symbol_data:
            return symbol_data.get(field)
        return None








