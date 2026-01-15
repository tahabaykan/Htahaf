
import sys
import os
import json

# Add path
sys.path.append(os.getcwd())

from app.analysis import gem_logic

def test_logic():
    print("Testing Gem Logic...")
    
    # 1. Reduction Ratio
    # C=5000, Max=10000. Ratio = 0.5. RR = 1 - 0.25 = 0.75.
    rr = gem_logic.calculate_reduction_ratio(5000, 10000)
    print(f"RR(5000, 10000) = {rr} (Expected 0.75)")
    assert rr == 0.75
    
    # C=10000 (Max), Max=10000. Ratio = 1.0. RR = 0.0.
    rr_max = gem_logic.calculate_reduction_ratio(10000, 10000)
    print(f"RR(10000, 10000) = {rr_max} (Expected 0.0)")
    assert rr_max == 0.0
    
    # 2. 400 Rule
    # C=300 (<400). Should close all.
    qty, reason = gem_logic.calculate_target_details(300, 0.5)
    print(f"Target(300) = {qty}, {reason}")
    assert qty == 300
    
    # 3. Rounding
    # C=5000. RR=0.5 -> Raw Sell 2500 -> Round 2500.
    qty, reason = gem_logic.calculate_target_details(5000, 0.5)
    print(f"Target(5000, RR=0.5) = {qty}")
    assert qty == 2500
    
    # C=5000. RR=0.103 (Raw 515). Round -> 500.
    qty, reason = gem_logic.calculate_target_details(5000, 0.103)
    print(f"Target(5000, RR=0.103) = {qty}")
    assert qty == 500
    
    print("✅ Logic Verified.")

def test_worker_load():
    print("\nTesting Worker Universe Load...")
    try:
        from workers.market_context_worker import MarketContextWorker
        worker = MarketContextWorker()
        worker.load_universe()
        print(f"✅ Universe Loaded: {len(worker.universe)} symbols.")
    except Exception as e:
        print(f"❌ Worker Error: {e}")

if __name__ == "__main__":
    test_logic()
    test_worker_load()
