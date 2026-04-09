
import sys
import os

# Add project root to path
sys.path.append(r'c:\StockTracker\quant_engine')

from app.market_data.static_data_store import StaticDataStore
from app.core.logger import logger

def test_sma_loading():
    print("Initializing StaticDataStore...")
    store = StaticDataStore()
    
    print("Loading janalldata.csv...")
    success = store.load_csv()
    
    if not success:
        print("Failed to load CSV.")
        return

    # Check a few symbols
    symbols = list(store.data.keys())[:5]
    print(f"Top 5 symbols: {symbols}")
    
    for symbol in symbols:
        data = store.get_static_data(symbol)
        sma63 = data.get('SMA63 chg')
        sma246 = data.get('SMA246 chg')
        sma63_raw = data.get('SMA63 chg_raw')
        sma246_raw = data.get('SMA246 chg_raw')
        
        print(f"[{symbol}] SMA63: {sma63} (raw: {sma63_raw}), SMA246: {sma246} (raw: {sma246_raw})")
        
        if sma63 is None and sma63_raw is not None:
             print(f"ERROR: {symbol} has raw but mapped is None")

if __name__ == "__main__":
    test_sma_loading()
