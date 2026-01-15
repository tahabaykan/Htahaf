"""
Static Data Store
Loads and stores static daily metrics from janalldata.csv
Keyed by PREF_IBKR (primary key)

NOTE: prev_close is loaded from CSV (janalldata.csv or janek_ssfinek*.csv files).
If not available in CSV, falls back to live Hammer market data.
"""

import pandas as pd
import os
from pathlib import Path
from typing import Dict, Optional, Any

from app.core.logger import logger
from app.market_data.grouping import resolve_primary_group


class StaticDataStore:
    """
    Stores static daily metrics loaded from CSV.
    Data is loaded once per day and keyed by PREF_IBKR.
    
    NOTE: prev_close is loaded from CSV (janalldata.csv has prev_close column).
    If not available in CSV, falls back to live Hammer market data.
    """
    
    # Required static fields
    REQUIRED_FIELDS = [
        'PREF IBKR',  # Primary key (note: space in column name)
        'CMON',
        'CGRUP',
        'GROUP',  # PRIMARY GROUP (file_group) - added for two-tier grouping
        'FINAL_THG',
        'SHORT_FINAL',
        'AVG_ADV',
        'SMI',
        'SMA63 chg',  # Note: space in column name
        'SMA246 chg'  # Note: space in column name
    ]
    
    # Optional fields (loaded if present in CSV)
    OPTIONAL_FIELDS = [
        'prev_close'  # Previous close price (from CSV, fallback to Hammer if not available)
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
            Path(__file__).parent.parent.parent / 'janall' / 'janalldata.csv',
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
                logger.error(f"CSV file not found: {csv_path or 'janalldata.csv'}")
                return False
            
            logger.info(f"Loading static data from: {filepath}")
            
            # Try different encodings
            try:
                df = pd.read_csv(filepath, encoding='utf-8')
            except UnicodeDecodeError:
                df = pd.read_csv(filepath, encoding='latin-1')
            
            # Check required columns
            missing_cols = [col for col in self.REQUIRED_FIELDS if col not in df.columns]
            if missing_cols:
                logger.warning(f"Missing columns: {missing_cols}")
                # Continue anyway, but log warning
            
            # Clear existing data
            self.data = {}
            
            # Load data keyed by PREF_IBKR
            pref_ibkr_col = 'PREF IBKR'
            if pref_ibkr_col not in df.columns:
                logger.error(f"Primary key column '{pref_ibkr_col}' not found")
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
                        elif field in ['FINAL_THG', 'SHORT_FINAL', 
                                      'AVG_ADV', 'SMI', 'SMA63 chg', 'SMA246 chg']:
                            # Numeric fields: convert to float
                            try:
                                static_data[field] = float(value)
                            except (ValueError, TypeError):
                                static_data[field] = None
                        else:
                            # String fields (CMON, CGRUP, etc.): keep as string
                            static_data[field] = str(value) if value else None
                    else:
                        static_data[field] = None
                
                # Extract optional fields (e.g., prev_close from CSV)
                for field in self.OPTIONAL_FIELDS:
                    if field in df.columns:
                        value = row[field]
                        if pd.isna(value):
                            static_data[field] = None
                        elif field == 'prev_close':
                            # prev_close is numeric
                            try:
                                prev_close_val = float(value)
                                if prev_close_val > 0:
                                    static_data[field] = prev_close_val
                                else:
                                    static_data[field] = None
                            except (ValueError, TypeError):
                                static_data[field] = None
                        else:
                            static_data[field] = value
                    else:
                        static_data[field] = None
                
                # Resolve GROUP if not in CSV (using grouping logic - Janall mantığı)
                if 'GROUP' not in static_data or not static_data.get('GROUP'):
                    primary_group = resolve_primary_group(static_data, pref_ibkr)
                    if primary_group:
                        static_data['GROUP'] = primary_group
                
                self.data[pref_ibkr] = static_data
            
            self.loaded = True
            logger.info(f"Loaded {len(self.data)} symbols from static data")
            return True
            
        except Exception as e:
            logger.error(f"Error loading static data: {e}", exc_info=True)
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


# Global instance
_static_store: Optional[StaticDataStore] = None


def get_static_store() -> Optional[StaticDataStore]:
    """Get global StaticDataStore instance"""
    global _static_store
    if _static_store is None:
        # Try to get from market_data_routes
        try:
            from app.api.market_data_routes import static_store as routes_store
            if routes_store:
                _static_store = routes_store
        except Exception:
            pass
    return _static_store


def initialize_static_store(csv_path: Optional[str] = None) -> StaticDataStore:
    """Initialize global StaticDataStore instance"""
    global _static_store
    # If already initialized in market_data_routes, use that instance
    try:
        from app.api.market_data_routes import static_store as routes_store
        if routes_store:
            _static_store = routes_store
            logger.info("StaticDataStore global instance synced from market_data_routes")
            return _static_store
    except Exception:
        pass
    # Otherwise create new instance
    _static_store = StaticDataStore(csv_path=csv_path)
    logger.info("StaticDataStore global instance initialized")
    return _static_store



