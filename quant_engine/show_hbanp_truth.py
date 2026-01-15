
from app.market_data.truth_ticks_engine import TruthTicksEngine
import datetime

# Dummy data for HBANP
# Includes:
# - Valid Non-FNRA (NYSE, size 15+)
# - Invalid Non-FNRA (NYSE, size < 15)
# - Valid FNRA (100, 200)
# - Invalid FNRA (98, 300, 500)

raw_ticks = [
    {"ts": "2025-10-23T10:00:01", "price": 25.20, "size": 100, "exch": "FNRA", "desc": "Valid FNRA 100"},
    {"ts": "2025-10-23T10:00:02", "price": 25.21, "size": 200, "exch": "FNRA", "desc": "Valid FNRA 200"},
    {"ts": "2025-10-23T10:00:03", "price": 25.22, "size": 300, "exch": "FNRA", "desc": "INVALID FNRA 300"},
    {"ts": "2025-10-23T10:00:04", "price": 25.23, "size": 98, "exch": "FNRA", "desc": "INVALID FNRA 98"},
    {"ts": "2025-10-23T10:00:05", "price": 25.24, "size": 14, "exch": "NYSE", "desc": "INVALID NYSE 14"},
    {"ts": "2025-10-23T10:00:06", "price": 25.25, "size": 15, "exch": "NYSE", "desc": "Valid NYSE 15"},
    {"ts": "2025-10-23T10:00:07", "price": 25.26, "size": 18, "exch": "ARCA", "desc": "Valid ARCA 18"},
    {"ts": "2025-10-23T10:00:08", "price": 25.27, "size": 500, "exch": "FNRA", "desc": "INVALID FNRA 500"},
    {"ts": "2025-10-23T10:00:09", "price": 25.28, "size": 100, "exch": "FNRA", "desc": "Valid FNRA 100"},
    {"ts": "2025-10-23T10:00:10", "price": 25.29, "size": 25, "exch": "EDGX", "desc": "Valid EDGX 25"},
     # Add more valid ones to fill list
] + [
    {"ts": f"2025-10-23T11:00:{i:02d}", "price": 25.30 + i*0.01, "size": 100, "exch": "FNRA", "desc": f"Filler FNRA 100 #{i}"} 
    for i in range(35)
]

def run_demo():
    print(f"--- HBANP TRUTH TICK DEMO ---")
    print(f"Total Raw Ticks: {len(raw_ticks)}")
    print(f"Rules:\n1. All: Size >= 15\n2. FNRA: Only 100 or 200\n3. Non-FNRA: Any >= 15\n")
    
    engine = TruthTicksEngine()
    
    # Process ticks
    accepted_ticks = []
    rejected_log = []
    
    for tick in raw_ticks:
        # Normalize mock tick (engine expects ts as float usually, but filter handles inputs)
        # We'll rely on our manual is_truth_tick check for demo
        is_truth = engine.is_truth_tick(tick)
        if is_truth:
            accepted_ticks.append(tick)
        else:
            rejected_log.append(f"REJECTED: {tick['desc']} ({tick['size']} @ {tick['exch']})")
            
    print(f"\n--- REJECTED LOG (Sample) ---")
    for log in rejected_log[:10]:
        print(log)
        
    print(f"\n--- LAST 40 TRUTH TICKS (ACCEPTED) ---")
    # Show last 40
    to_show = accepted_ticks[-40:]
    for i, tick in enumerate(to_show):
        print(f"{i+1:02d}. [ACCEPTED] {tick['ts']} | {tick['exch']:<5} | Size: {tick['size']:<4} | {tick['desc']}")

if __name__ == "__main__":
    run_demo()
