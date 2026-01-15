import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())

from app.core.data_fabric import get_data_fabric
# from app.market_data.static_data_store import get_static_data_store
from app.core.fast_score_calculator import get_fast_score_calculator

def debug_efscp():
    symbol = "EFSCP"
    print(f"--- DEBUGGING {symbol} ---")
    
    # 1. Check DataFabric Paths
    fabric = get_data_fabric()
    print(f"DataFabric initialized: {fabric}")
    
    # 2. Check Static Data
    static = fabric.get_static(symbol)
    if not static:
        print("Static Data NOT FOUND in Fabric")
    else:
        print(f"Static Data Source: {static.get('_source', 'Unknown')}")
        print(f"Prev Close: {static.get('prev_close')}")
        print(f"Aug2022_Price: {static.get('Aug2022_Price')}")
    
    # 3. Check Live Data match
    live = fabric.get_live(symbol)
    print(f"Live Data: {live}")
    
    # 4. Check Benchmark
    calc = get_fast_score_calculator()
    scores = calc.compute_fast_scores(symbol)
    print(f"Calculated Scores: {scores}")
    
    # 5. Check File Paths explicitly
    onedrive_path = Path(r"C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janall\janalldata.csv")
    local_path = Path(r"c:\StockTracker\janalldata.csv")
    
    if onedrive_path.exists():
        print("OneDrive File EXISTS")
        # Read snippet
        with open(onedrive_path, 'r') as f:
            for line in f:
                if symbol in line:
                    print(f"OneDrive Line: {line.strip()[:100]}...")
                    break
    
    if local_path.exists():
        print("Local File EXISTS")
        with open(local_path, 'r') as f:
            for line in f:
                if symbol in line:
                    print(f"Local Line: {line.strip()[:100]}...")
                    break

if __name__ == "__main__":
    debug_efscp()
