import sys
import os
from pathlib import Path

# Setup Path
sys.path.append(os.getcwd())

# Mock logger to avoid import issues or detailed logging setup
import logging
logging.basicConfig(level=logging.INFO)

from app.psfalgo.position_snapshot_api import PositionSnapshotAPI

def main():
    print("--- BEFDAY READ TEST ---")
    print(f"CWD: {os.getcwd()}")
    
    # Instantiate API (mock params)
    # We can pass None for dependencies as we only test _load_befday_map which is mostly independent
    # (It imports pandas inside)
    api = PositionSnapshotAPI(
        position_manager=None, # Mock
        static_store=None, # Mock
        market_data_cache=None # Mock
    )
    
    account_id = "IBKR_PED"
    csv_filename = "befibped.csv"
    
    # Check physical file
    p = Path(csv_filename)
    print(f"File {p.absolute()} exists? {p.exists()}")
    if p.exists():
        print(f"File size: {p.stat().st_size} bytes")
    
    # Call method
    try:
        bef_map = api._load_befday_map(account_id)
        print(f"Result Map Size: {len(bef_map)}")
        if bef_map:
            print("First 5 entries:")
            count = 0
            for k, v in bef_map.items():
                print(f"  {k}: {v}")
                count += 1
                if count >= 5: break
                
            if "HOVNP" in bef_map:
                print(f"HOVNP Found: {bef_map['HOVNP']}")
            else:
                print("HOVNP NOT in map")
        else:
            print("Map is EMPTY (Failed to load or Parse)")
            
    except Exception as e:
        print(f"Error calling _load_befday_map: {e}")

if __name__ == "__main__":
    main()
