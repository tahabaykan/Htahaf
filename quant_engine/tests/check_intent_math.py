
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import pytest
from app.psfalgo.intent_math import compute_intents, calculate_rounded_lot

def test_compute_intents_defaults():
    config = {
        'hard_threshold_pct': 130.0,
        'soft_ratio_num': 12,
        'soft_ratio_den': 13,
        'Amax': 100.0,
        'Asoft': 20.0,
        'pn': 1.25,
        'q': 2.14,
        'ps': 1.50
    }
    
    # S should be 120.0
    
    # Case 1: E=50 (NORMAL)
    # Expected: High AddIntent
    add, red, regime = compute_intents(50.0, config)
    assert regime == "NORMAL"
    assert add > 80.0 # From prompt "Add ~85"
    assert red == 100.0 - add

    # Case 2: E=95 (NORMAL)
    # Expected: Moderate AddIntent
    add, red, regime = compute_intents(95.0, config)
    assert regime == "NORMAL"
    assert 40.0 < add < 60.0 # From prompt "Add ~45"

    # Case 3: E=120 (At Boundary / Soft)
    # If S=120, E=120. x=1. Add = Asoft = 20.0
    add, red, regime = compute_intents(120.0, config)
    # Note: float precision might make it slightly Soft or Normal depending on exact S calc
    # But result should be close to Asoft (20.0).
    assert abs(add - 20.0) < 0.1 

    # Case 4: E=125 (SOFT)
    add, red, regime = compute_intents(125.0, config)
    assert regime == "SOFT"
    assert add < 20.0
    assert add > 0.0

    # Case 5: E=130 (HARD)
    add, red, regime = compute_intents(130.0, config)
    assert regime == "HARD"
    assert add == 0.0
    assert red == 100.0

def test_calculate_rounded_lot():
    policy = {'rounding': {'no_trade_below_raw': 100, 'min_trade_lot': 200}}
    
    # < 100 -> 0
    assert calculate_rounded_lot(78, policy) == 0
    assert calculate_rounded_lot(99, policy) == 0
    
    # 100..199 -> 200
    assert calculate_rounded_lot(100, policy) == 200
    assert calculate_rounded_lot(123, policy) == 200
    assert calculate_rounded_lot(199, policy) == 200
    
    # >= 200 -> Nearest 100
    assert calculate_rounded_lot(200, policy) == 200
    assert calculate_rounded_lot(249, policy) == 200
    assert calculate_rounded_lot(251, policy) == 300
    assert calculate_rounded_lot(338, policy) == 300
    assert calculate_rounded_lot(492, policy) == 500

if __name__ == "__main__":
    test_compute_intents_defaults()
    test_calculate_rounded_lot()
    print("ALL TESTS PASSED")
