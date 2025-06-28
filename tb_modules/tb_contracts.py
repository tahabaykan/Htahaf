"""
Interactive Brokers contract related utilities for StockTracker
"""
from ib_insync import Stock

def create_preferred_stock_contract(ticker_symbol):
    """
    Tercihli hisse senedi kontratı oluşturur
    
    Args:
        ticker_symbol (str): Tercihli hisse senedi sembolü (örn. "PFF-B")
        
    Returns:
        Stock: Interactive Brokers Stock nesnesi
    """
    # Basit doğrulama
    if not ticker_symbol or not isinstance(ticker_symbol, str):
        raise ValueError("Invalid ticker symbol")
    
    # Boşlukları kaldır ve büyük harfe çevir
    ticker_symbol = ticker_symbol.strip().upper()
    
    # Kontrat oluştur
    # Amerikan tercihli hisseleri
    contract = Stock(symbol=ticker_symbol, exchange='SMART', currency='USD')
    
    return contract

def create_common_stock_contract(ticker_symbol):
    """
    Adi hisse senedi kontratı oluşturur
    
    Args:
        ticker_symbol (str): Adi hisse senedi sembolü (örn. "AAPL")
        
    Returns:
        Stock: Interactive Brokers Stock nesnesi
    """
    # Basit doğrulama
    if not ticker_symbol or not isinstance(ticker_symbol, str):
        raise ValueError("Invalid ticker symbol")
    
    # Boşlukları kaldır ve büyük harfe çevir
    ticker_symbol = ticker_symbol.strip().upper()
    
    # Kontrat oluştur
    contract = Stock(symbol=ticker_symbol, exchange='SMART', currency='USD')
    
    return contract 