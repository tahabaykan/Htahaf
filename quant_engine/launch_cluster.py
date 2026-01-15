
"""
Truth Ticks Cluster Launcher
===========================

Launches 6 TruthTicksWorker terminals with dynamic load balancing.

Partitioning Strategy:
- Worker 1: ALL 'heldkuponlu' family groups (heldkuponlu, heldkuponlu:c400, etc.)
            This isolates the most critical group (approx 160-200 stocks).
- Worker 2-6: Remaining stocks (approx 240) split evenly (approx 48 per worker).

Features:
- Dynamically reads janalldata.csv via StaticStore.
- Resolves groups using Grouping logic.
- Creates individual JSON config files for each worker.
- Spawns subprocesses in new console windows (on Windows).
"""

import os
import sys
import json
import time
import subprocess
import math
from pathlib import Path
from typing import List, Dict

# Add parent dir to path
sys.path.insert(0, os.getcwd())

from app.market_data.static_data_store import initialize_static_store
from app.market_data.grouping import get_all_group_keys
from app.core.logger import logger

# Configuration
CLUSTER_SIZE = 6
WORKER_SCRIPT = "app/workers/truth_ticks_worker.py"
CONFIG_DIR = Path("config/cluster_configs")

def setup_configs():
    """
    Partition symbols and generate config files.
    """
    print("🚀 Initializing Cluster Configuration...")
    
    # Initialize store
    try:
        store = initialize_static_store()
        if not store.is_loaded():
            # Try explict path
            store.load_csv(r"c:\StockTracker\janalldata.csv")
    except Exception as e:
        print(f"❌ Failed to load static store: {e}")
        return None

    if not store.is_loaded():
        print("❌ Static store not loaded. Cannot partition.")
        return None

    # Get all groups
    groups = get_all_group_keys(store)
    
    # Partition logic
    heldkuponlu_symbols = []
    other_symbols = []
    
    for group, symbols in groups.items():
        if "heldkuponlu" in group:
            heldkuponlu_symbols.extend(symbols)
        else:
            other_symbols.extend(symbols)
            
    # Dedup
    heldkuponlu_symbols = sorted(list(set(heldkuponlu_symbols)))
    other_symbols = sorted(list(set(other_symbols)))
    
    total_symbols = len(heldkuponlu_symbols) + len(other_symbols)
    print(f"📊 found {total_symbols} total symbols")
    print(f"   - heldkuponlu family: {len(heldkuponlu_symbols)}")
    print(f"   - others: {len(other_symbols)}")
    
    # Worker assignments
    worker_configs = {}
    
    # Worker 1: heldkuponlu
    worker_configs[1] = heldkuponlu_symbols
    
    # Worker 2-6: Split others evenly
    other_workers_count = CLUSTER_SIZE - 1
    chunk_size = math.ceil(len(other_symbols) / other_workers_count)
    
    for i in range(other_workers_count):
        worker_id = i + 2
        start_idx = i * chunk_size
        end_idx = min((i + 1) * chunk_size, len(other_symbols))
        
        chunk = other_symbols[start_idx:end_idx]
        worker_configs[worker_id] = chunk
        
    # Ensure config dir exists
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Write config files
    created_files = []
    for worker_id, symbols in worker_configs.items():
        config_path = CONFIG_DIR / f"worker_{worker_id}.json"
        config_data = {
            "worker_id": worker_id,
            "count": len(symbols),
            "symbols": symbols
        }
        
        with open(config_path, "w") as f:
            json.dump(config_data, f, indent=2)
        
        created_files.append(config_path)
        print(f"✅ Config generated for Worker {worker_id}: {len(symbols)} symbols")
        
    return created_files

def launch_workers(config_files: List[Path]):
    """
    Launch worker subprocesses.
    """
    processes = []
    
    print("\n🚀 Launching Workers...")
    
    for config_file in config_files:
        worker_id = config_file.stem
        
        # Command to run
        # Use simple python command
        cmd = [sys.executable, WORKER_SCRIPT, "--name", worker_id, "--config", str(config_file)]
        
        print(f"   Starting {worker_id}...")
        
        # Launch in new console window
        if os.name == 'nt':
            # Windows: CREATE_NEW_CONSOLE
            p = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            # Linux/Mac (not main target but valid): nohup or just background
            p = subprocess.Popen(cmd)
            
        processes.append(p)
        time.sleep(1) # Stagger start slightly
        
    print(f"\n✅ All {len(processes)} workers launched.")
    print("   Close the individual worker windows to stop them.")
    print("   Or close this window to exit launcher (workers will keep running).")

def main():
    config_files = setup_configs()
    if config_files:
        launch_workers(config_files)
    else:
        print("❌ Launch aborted due to configuration errors.")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
