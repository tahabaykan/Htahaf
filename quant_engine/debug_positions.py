import asyncio
import os
import sys
from pathlib import Path

# Setup Path
sys.path.append(os.getcwd())

from app.psfalgo.position_snapshot_api import initialize_position_snapshot_api, get_position_snapshot_api
from app.psfalgo.ibkr_connector import initialize_ibkr_connectors

async def main():
    print("--- DEBUG POSITIONS START ---")
    
    # Init dependencies
    initialize_ibkr_connectors() # Mock or Real?
    initialize_position_snapshot_api()
    
    api = get_position_snapshot_api()
    account_id = "IBKR_PED"
    
    # Check CSV existence
    csv_path = Path("befibped.csv")
    print(f"Checking {csv_path.absolute()}: Exists={csv_path.exists()}")
    if csv_path.exists():
        with open(csv_path, 'r') as f:
            print(f"CSV Content Preview:\n{f.read(200)}...")
    
    # Verify Befday Map Loading directly
    print(f"\n--- Testing _load_befday_map('{account_id}') ---")
    bef_map = api._load_befday_map(account_id)
    print(f"Loaded Map Size: {len(bef_map)}")
    if bef_map:
        first_key = list(bef_map.keys())[0]
        print(f"Sample Entry [{first_key}]: {bef_map[first_key]}")
        
    # Check for specific symbol if known
    sym_to_check = "HOVNP"
    if sym_to_check in bef_map:
        print(f"FOUND {sym_to_check}: {bef_map[sym_to_check]}")
    else:
        print(f"MISSING {sym_to_check} in map!")

    # Fetch Snapshot
    print(f"\nFetching snapshot for {account_id}...")
    try:
        snapshots = await api.get_position_snapshot(account_id=account_id)
        print(f"Fetched {len(snapshots)} positions.")
        
        for pos in snapshots[:10]: # Print first 10
            print(f"Sym: {pos.symbol}, Qty: {pos.qty}, Befday: {pos.befday_qty}, Origin: {pos.origin_type}, Strategy: {pos.strategy_type}")
            
    except Exception as e:
        print(f"Error: {e}")

    print("--- DEBUG POSITIONS END ---")

if __name__ == "__main__":
    asyncio.run(main())
