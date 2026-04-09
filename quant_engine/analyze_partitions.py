
import sys
import os
sys.path.insert(0, os.getcwd())

from app.market_data.static_data_store import initialize_static_store
from app.market_data.grouping import get_all_group_keys
from app.core.logger import logger

# Disable file logging to avoid clutter
logger.remove()
logger.add(sys.stdout, level="INFO")

def analyze():
    print("Initializing Static Store...")
    # Initialize store (will auto-find CSV)
    store = initialize_static_store()
    
    if not store.is_loaded():
        # Try explicit path if auto-find fails (fallback)
        print("Auto-find failed, trying explicit path...")
        store.load_csv(r"c:\StockTracker\janalldata.csv")
    
    if not store.is_loaded():
        print("Failed to load static store.")
        return

    print("Resolving Groups...")
    groups = get_all_group_keys(store)
    
    print("\n--- GROUP DISTRIBUTION ---")
    
    # Sort by group name
    sorted_groups = sorted(groups.items(), key=lambda x: x[0])
    
    total_symbols = 0
    group_counts = []
    
    for group, symbols in sorted_groups:
        count = len(symbols)
        total_symbols += count
        group_counts.append((group, count))
        print(f"{group:<30} : {count}")
    
    print(f"\nTotal Symbols: {total_symbols}")
    
    with open("partition_proposal.txt", "w") as f:
        f.write("--- GROUP DISTRIBUTION ---\n")
        for group, count in sorted_groups:
            f.write(f"{group:<30} : {count}\n")
        
        f.write(f"\nTotal Symbols: {total_symbols}\n")
        
        f.write("\n--- 4-WAY PARTITION PROPOSAL ---\n")
        for i in range(4):
            f.write(f"Terminal {i+1} ({terminal_counts[i]}): {terminals[i]}\n")
            
        f.write("\n--- 8-WAY PARTITION PROPOSAL ---\n")
        # 8-way split
        terminals8 = [[] for _ in range(8)]
        terminal_counts8 = [0] * 8
        
        for group, count in sorted_by_size:
            min_idx = terminal_counts8.index(min(terminal_counts8))
            terminals8[min_idx].append(group)
            terminal_counts8[min_idx] += count
            
        for i in range(8):
            f.write(f"Terminal {i+1} ({terminal_counts8[i]}): {terminals8[i]}\n")
            
    print("Proposal written to partition_proposal.txt")

if __name__ == "__main__":
    analyze()
