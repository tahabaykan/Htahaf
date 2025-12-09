"""
Veri validation ve doğrulama fonksiyonları
"""

import re
from typing import Any, Dict, List, Optional
import pandas as pd

class ValidationError(Exception):
    """Validation hatası"""
    pass

def validate_symbol(symbol: str) -> bool:
    """
    Sembol formatını doğrula
    
    Args:
        symbol: Hisse sembolü (örn: "VNO PRN", "VNO-N", "SPY")
        
    Returns:
        True if valid
        
    Raises:
        ValidationError: Geçersiz sembol formatı
    """
    if not symbol or not isinstance(symbol, str):
        raise ValidationError("Sembol boş olamaz")
    
    symbol = symbol.strip()
    
    if len(symbol) < 1 or len(symbol) > 20:
        raise ValidationError(f"Sembol uzunluğu geçersiz: {len(symbol)}")
    
    # Preferred stock format kontrolü
    if ' PR' in symbol:
        # Format: "VNO PRN" -> "VNO PRN"
        parts = symbol.split(' PR')
        if len(parts) != 2:
            raise ValidationError(f"Geçersiz preferred stock formatı: {symbol}")
        base, suffix = parts
        if not base or not suffix or len(suffix) != 1:
            raise ValidationError(f"Geçersiz preferred stock formatı: {symbol}")
    
    elif '-' in symbol:
        # Format: "VNO-N" -> "VNO-N"
        parts = symbol.split('-')
        if len(parts) != 2:
            raise ValidationError(f"Geçersiz sembol formatı: {symbol}")
        base, suffix = parts
        if not base or not suffix or len(suffix) != 1:
            raise ValidationError(f"Geçersiz sembol formatı: {symbol}")
    
    # Genel karakter kontrolü (sadece harf, rakam, boşluk, tire, nokta)
    if not re.match(r'^[A-Z0-9\s\-\.]+$', symbol.upper()):
        raise ValidationError(f"Geçersiz karakterler içeren sembol: {symbol}")
    
    return True

def validate_price(price: Any, min_price: float = 0.01, max_price: float = 10000.0) -> bool:
    """
    Fiyat değerini doğrula
    
    Args:
        price: Fiyat değeri
        min_price: Minimum geçerli fiyat
        max_price: Maksimum geçerli fiyat
        
    Returns:
        True if valid
        
    Raises:
        ValidationError: Geçersiz fiyat değeri
    """
    try:
        price_float = float(price)
    except (ValueError, TypeError):
        raise ValidationError(f"Fiyat sayısal değil: {price}")
    
    if pd.isna(price_float):
        raise ValidationError("Fiyat NaN değeri")
    
    if price_float <= 0:
        raise ValidationError(f"Fiyat pozitif olmalı: {price_float}")
    
    if price_float < min_price:
        raise ValidationError(f"Fiyat minimum değerin altında: {price_float} < {min_price}")
    
    if price_float > max_price:
        raise ValidationError(f"Fiyat maksimum değerin üstünde: {price_float} > {max_price}")
    
    return True

def validate_lot(lot: Any, min_lot: int = 1, max_lot: int = 100000) -> bool:
    """
    Lot miktarını doğrula
    
    Args:
        lot: Lot miktarı
        min_lot: Minimum geçerli lot
        max_lot: Maksimum geçerli lot
        
    Returns:
        True if valid
        
    Raises:
        ValidationError: Geçersiz lot miktarı
    """
    try:
        lot_int = int(lot)
    except (ValueError, TypeError):
        raise ValidationError(f"Lot sayısal değil: {lot}")
    
    if pd.isna(lot_int):
        raise ValidationError("Lot NaN değeri")
    
    if lot_int < min_lot:
        raise ValidationError(f"Lot minimum değerin altında: {lot_int} < {min_lot}")
    
    if lot_int > max_lot:
        raise ValidationError(f"Lot maksimum değerin üstünde: {lot_int} > {max_lot}")
    
    return True

def validate_csv_data(df: pd.DataFrame, required_columns: List[str] = None, 
                     symbol_column: str = 'PREF IBKR') -> Dict[str, Any]:
    """
    CSV verilerini doğrula
    
    Args:
        df: DataFrame
        required_columns: Zorunlu kolonlar listesi
        symbol_column: Sembol kolonu adı
        
    Returns:
        Validation sonuçları dictionary'si
        
    Raises:
        ValidationError: Geçersiz veri
    """
    results = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'row_count': len(df),
        'column_count': len(df.columns)
    }
    
    # DataFrame boş mu kontrol et
    if df.empty:
        results['warnings'].append("DataFrame boş")
        return results
    
    # Zorunlu kolonlar kontrolü
    if required_columns:
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            results['errors'].append(f"Eksik kolonlar: {missing_columns}")
            results['valid'] = False
    
    # Sembol kolonu kontrolü
    if symbol_column in df.columns:
        # Duplicate semboller kontrolü
        duplicates = df[symbol_column].duplicated()
        if duplicates.any():
            duplicate_symbols = df[duplicates][symbol_column].unique()
            results['warnings'].append(f"Tekrar eden semboller: {duplicate_symbols[:10]}")
        
        # Sembol formatı kontrolü (ilk 10 satır)
        invalid_symbols = []
        for idx, symbol in df[symbol_column].head(10).items():
            try:
                validate_symbol(str(symbol))
            except ValidationError as e:
                invalid_symbols.append(f"Satır {idx}: {e}")
        
        if invalid_symbols:
            results['warnings'].extend(invalid_symbols[:5])  # İlk 5 hatayı göster
    
    # Fiyat kolonları kontrolü (varsa)
    price_columns = ['Bid', 'Ask', 'Last', 'prev_close']
    for col in price_columns:
        if col in df.columns:
            invalid_prices = []
            for idx, price in df[col].head(10).items():
                try:
                    validate_price(price)
                except ValidationError:
                    invalid_prices.append(f"Satır {idx}, Kolon {col}")
            
            if invalid_prices:
                results['warnings'].extend(invalid_prices[:3])  # İlk 3 hatayı göster
    
    return results


