
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

# ═══ DOUBLE-LAUNCH PROTECTION ═══
# Backend (main.py) manages TT workers automatically.
# If backend is running, this script should NOT be used.
def _check_backend_managing():
    """Check if backend is already managing TT workers."""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=2)
        managed_by = r.get("tt_cluster:managed_by")
        if managed_by:
            managed_by = managed_by.decode('utf-8') if isinstance(managed_by, bytes) else managed_by
            if managed_by == "backend":
                alive = r.get("tt_cluster:alive_count")
                alive_str = alive.decode('utf-8') if alive else "?"
                print("=" * 60)
                print("⚠️  UYARI: Backend TT worker'ları otomatik yönetiyor!")
                print(f"   Aktif worker sayısı: {alive_str}")
                print("   Bu scripti çalıştırmanız ÇİFT TT worker oluşturur!")
                print("   Bu bilgisayarı AŞIRI yavaşlatır!")
                print("=" * 60)
                print()
                confirm = input("Yine de devam etmek istiyor musunuz? (evet yazın): ").strip().lower()
                if confirm != "evet":
                    print("İptal edildi. Backend TT worker'ları zaten çalışıyor.")
                    sys.exit(0)
                else:
                    print("⚠️  DİKKAT: Çift TT worker moduna geçiliyor!")
                    # Clear backend management flag since user is taking over
                    r.delete("tt_cluster:managed_by")
    except Exception:
        pass  # Redis not available, allow launch

_check_backend_managing()

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
            # Try multiple fallback paths
            fallback_paths = [
                r"c:\StockTracker\janalldata.csv",
                r"c:\StockTracker\janall\janalldata.csv",
                r"c:\StockTracker\janall\janallapp\janalldata.csv",
                r"c:\StockTracker\njanall\janalldata.csv",
                r"c:\StockTracker\newjanall\janalldata.csv",
            ]
            for fp in fallback_paths:
                if os.path.exists(fp):
                    print(f"   Found CSV at: {fp}")
                    store.load_csv(fp)
                    break
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
        time.sleep(5) # Stagger start — Hammer Pro needs time between auth requests
        
    print(f"\n✅ All {len(processes)} workers launched.")
    print("   Close the individual worker windows to stop them.")
    print("   Or close this window to exit launcher (workers will keep running).")

def main():
    global CLUSTER_SIZE
    import argparse
    parser = argparse.ArgumentParser(description="Truth Ticks Cluster Launcher")
    parser.add_argument("--single", action="store_true", 
                       help="Launch a single worker for ALL symbols (simpler, more reliable)")
    parser.add_argument("--size", type=int, default=CLUSTER_SIZE,
                       help=f"Number of workers (default: {CLUSTER_SIZE})")
    args = parser.parse_args()
    
    if args.single:
        print("🚀 SINGLE WORKER MODE: Launching one worker for ALL symbols")
        print("   No config needed - worker auto-loads ALL symbols from static store.")
        print()
        
        cmd = [sys.executable, WORKER_SCRIPT, "--name", "truth_ticks_all"]
        
        if os.name == 'nt':
            p = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            p = subprocess.Popen(cmd)
        
        print(f"✅ Single worker launched (PID: {p.pid})")
        print("   Close the worker window to stop it.")
    else:
        CLUSTER_SIZE = args.size
        config_files = setup_configs()
        if config_files:
            print(f"\n⚠️  IMPORTANT: ALL {len(config_files)} workers MUST be running for full coverage!")
            print(f"   If only Worker 1 starts, 334 symbols will have NO truth tick data.")
            print(f"   Consider using --single for simpler operation.\n")
            launch_workers(config_files)
        else:
            print("❌ Launch aborted due to configuration errors.")
            input("Press Enter to exit...")

if __name__ == "__main__":
    main()
