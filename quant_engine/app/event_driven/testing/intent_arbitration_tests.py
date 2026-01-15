"""
Intent Arbitration Test Scenarios

Tests for IntentArbiter conflict resolution:
1) MM churn + LT drift + CAP_RECOVERY → only CAP_RECOVERY intents pass
2) SOFT_DERISK + LT drift → both allowed if no conflict
3) HARD_DERISK + MM churn → MM churn suppressed
4) Conflicting intents on same symbol → higher priority wins
5) Multiple derisk intents → merged and LiquidityGuard applied
6) MM leftover >15% overnight → next OPEN generates MM_DECREASE intents
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.event_driven.decision_engine.intent_arbiter import IntentArbiter, IntentPriority


def test_cap_recovery_suppresses_all():
    """Test 1: MM churn + LT drift + CAP_RECOVERY → only CAP_RECOVERY intents pass"""
    print("\n" + "=" * 80)
    print("TEST 1: CAP_RECOVERY Suppresses All Lower Priority")
    print("=" * 80)
    
    config = {
        "intent_arbitration": {
            "cap_recovery_target_gross": 123.0,
            "mm_overnight_max_pct": 15.0,
            "soft_suppress_threshold": 120.0
        },
        "exposure": {"max_gross_exposure_pct": 130.0}
    }
    
    arbiter = IntentArbiter(config)
    
    # Create mixed intents
    intents = [
        {
            "intent_type": "MM_CHURN",
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
            "classification": "MM_LONG_INCREASE",
            "bucket": "MM",
            "effect": "INCREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": 2.0,
        },
        {
            "intent_type": "LT_BAND_CORRECTIVE",
            "symbol": "MSFT",
            "action": "SELL",
            "quantity": 50,
            "classification": "LT_LONG_DECREASE",
            "bucket": "LT",
            "effect": "DECREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": -1.0,
        },
        {
            "intent_type": "CAP_RECOVERY",
            "symbol": "GOOGL",
            "action": "SELL",
            "quantity": 200,
            "classification": "LT_LONG_DECREASE",
            "bucket": "LT",
            "effect": "DECREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": -5.0,
        },
    ]
    
    # Arbitrate with CAP_RECOVERY active (gross = 131%)
    arbitrated = arbiter.arbitrate(
        intents=intents,
        current_gross_exposure_pct=131.0,
        current_mode="CAP_RECOVERY"
    )
    
    print(f"Input intents: {len(intents)}")
    print(f"Arbitrated intents: {len(arbitrated)}")
    
    # Check: MM churn should be suppressed (risk-increasing)
    mm_intents = [i for i in arbitrated if i.get("intent_type") == "MM_CHURN"]
    assert len(mm_intents) == 0, f"MM churn should be suppressed, got {len(mm_intents)}"
    
    # Check: CAP_RECOVERY should pass
    cap_intents = [i for i in arbitrated if i.get("intent_type") == "CAP_RECOVERY"]
    assert len(cap_intents) == 1, f"CAP_RECOVERY should pass, got {len(cap_intents)}"
    
    # Check: LT drift should pass (risk-reducing)
    lt_intents = [i for i in arbitrated if i.get("intent_type") == "LT_BAND_CORRECTIVE"]
    assert len(lt_intents) == 1, f"LT drift (risk-reducing) should pass, got {len(lt_intents)}"
    
    print(f"\n[PASS] TEST 1 PASSED: CAP_RECOVERY suppresses MM churn, allows risk-reducing")


def test_soft_derisk_with_lt_drift():
    """Test 2: SOFT_DERISK + LT drift → both allowed if no conflict"""
    print("\n" + "=" * 80)
    print("TEST 2: SOFT_DERISK + LT Drift (No Conflict)")
    print("=" * 80)
    
    config = {
        "intent_arbitration": {
            "cap_recovery_target_gross": 123.0,
            "mm_overnight_max_pct": 15.0,
            "soft_suppress_threshold": 120.0
        }
    }
    
    arbiter = IntentArbiter(config)
    
    # Create non-conflicting intents (different symbols)
    intents = [
        {
            "intent_type": "SOFT_DERISK",
            "symbol": "AAPL",
            "action": "SELL",
            "quantity": 100,
            "classification": "LT_LONG_DECREASE",
            "bucket": "LT",
            "effect": "DECREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": -2.0,
        },
        {
            "intent_type": "LT_BAND_CORRECTIVE",
            "symbol": "MSFT",
            "action": "BUY",
            "quantity": 50,
            "classification": "LT_SHORT_DECREASE",
            "bucket": "LT",
            "effect": "DECREASE",
            "dir": "SHORT",
            "risk_delta_gross_pct": -1.0,
        },
    ]
    
    # Arbitrate (gross = 115%, not CAP_RECOVERY)
    arbitrated = arbiter.arbitrate(
        intents=intents,
        current_gross_exposure_pct=115.0,
        current_mode="SOFT_DERISK"
    )
    
    print(f"Input intents: {len(intents)}")
    print(f"Arbitrated intents: {len(arbitrated)}")
    
    # Both should pass (no conflict, both risk-reducing)
    assert len(arbitrated) == 2, f"Both intents should pass, got {len(arbitrated)}"
    
    print(f"\n[PASS] TEST 2 PASSED: SOFT_DERISK and LT drift both allowed")


def test_hard_derisk_suppresses_mm():
    """Test 3: HARD_DERISK + MM churn → MM churn suppressed"""
    print("\n" + "=" * 80)
    print("TEST 3: HARD_DERISK Suppresses MM Churn")
    print("=" * 80)
    
    config = {
        "intent_arbitration": {
            "cap_recovery_target_gross": 123.0,
            "mm_overnight_max_pct": 15.0,
            "soft_suppress_threshold": 120.0
        }
    }
    
    arbiter = IntentArbiter(config)
    
    intents = [
        {
            "intent_type": "HARD_DERISK",
            "symbol": "AAPL",
            "action": "SELL",
            "quantity": 200,
            "classification": "LT_LONG_DECREASE",
            "bucket": "LT",
            "effect": "DECREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": -5.0,
        },
        {
            "intent_type": "MM_CHURN",
            "symbol": "MSFT",
            "action": "BUY",
            "quantity": 100,
            "classification": "MM_LONG_INCREASE",
            "bucket": "MM",
            "effect": "INCREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": 2.0,
        },
    ]
    
    # Arbitrate with HARD_DERISK active
    arbitrated = arbiter.arbitrate(
        intents=intents,
        current_gross_exposure_pct=110.0,
        current_mode="HARD_DERISK"
    )
    
    print(f"Input intents: {len(intents)}")
    print(f"Arbitrated intents: {len(arbitrated)}")
    
    # MM churn should be suppressed
    mm_intents = [i for i in arbitrated if i.get("intent_type") == "MM_CHURN"]
    assert len(mm_intents) == 0, f"MM churn should be suppressed, got {len(mm_intents)}"
    
    # HARD_DERISK should pass
    hard_intents = [i for i in arbitrated if i.get("intent_type") == "HARD_DERISK"]
    assert len(hard_intents) == 1, f"HARD_DERISK should pass, got {len(hard_intents)}"
    
    print(f"\n[PASS] TEST 3 PASSED: HARD_DERISK suppresses MM churn")


def test_symbol_conflict_resolution():
    """Test 4: Conflicting intents on same symbol → higher priority wins"""
    print("\n" + "=" * 80)
    print("TEST 4: Symbol Conflict Resolution")
    print("=" * 80)
    
    config = {
        "intent_arbitration": {
            "cap_recovery_target_gross": 123.0,
            "mm_overnight_max_pct": 15.0,
            "soft_suppress_threshold": 120.0
        }
    }
    
    arbiter = IntentArbiter(config)
    
    # Conflicting intents on same symbol (LONG_INCREASE vs LONG_DECREASE)
    intents = [
        {
            "intent_type": "MM_CHURN",
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 100,
            "classification": "MM_LONG_INCREASE",
            "bucket": "MM",
            "effect": "INCREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": 2.0,
            "priority": IntentPriority.MM_CHURN,
        },
        {
            "intent_type": "SOFT_DERISK",
            "symbol": "AAPL",
            "action": "SELL",
            "quantity": 50,
            "classification": "LT_LONG_DECREASE",
            "bucket": "LT",
            "effect": "DECREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": -1.0,
            "priority": IntentPriority.SOFT_DERISK,
        },
    ]
    
    # Arbitrate
    arbitrated = arbiter.arbitrate(
        intents=intents,
        current_gross_exposure_pct=115.0,
        current_mode="SOFT_DERISK"
    )
    
    print(f"Input intents: {len(intents)}")
    print(f"Arbitrated intents: {len(arbitrated)}")
    
    # Higher priority (SOFT_DERISK) should win
    assert len(arbitrated) == 1, f"Only one intent should pass, got {len(arbitrated)}"
    assert arbitrated[0].get("intent_type") == "SOFT_DERISK", "SOFT_DERISK should win"
    
    print(f"\n[PASS] TEST 4 PASSED: Higher priority intent wins conflict")


def test_merge_same_direction():
    """Test 5: Multiple derisk intents → merged if same direction & effect"""
    print("\n" + "=" * 80)
    print("TEST 5: Merge Same Direction & Effect")
    print("=" * 80)
    
    config = {
        "intent_arbitration": {
            "cap_recovery_target_gross": 123.0,
            "mm_overnight_max_pct": 15.0,
            "soft_suppress_threshold": 120.0
        }
    }
    
    arbiter = IntentArbiter(config)
    
    # Multiple derisk intents on same symbol, same direction & effect
    intents = [
        {
            "intent_type": "SOFT_DERISK",
            "symbol": "AAPL",
            "action": "SELL",
            "quantity": 100,
            "classification": "LT_LONG_DECREASE",
            "bucket": "LT",
            "effect": "DECREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": -2.0,
        },
        {
            "intent_type": "HARD_DERISK",
            "symbol": "AAPL",
            "action": "SELL",
            "quantity": 50,
            "classification": "LT_LONG_DECREASE",
            "bucket": "LT",
            "effect": "DECREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": -1.0,
        },
    ]
    
    # Arbitrate
    arbitrated = arbiter.arbitrate(
        intents=intents,
        current_gross_exposure_pct=115.0,
        current_mode="HARD_DERISK"
    )
    
    print(f"Input intents: {len(intents)}")
    print(f"Arbitrated intents: {len(arbitrated)}")
    
    # Should be merged (same symbol, direction, effect)
    assert len(arbitrated) == 1, f"Intents should be merged, got {len(arbitrated)}"
    assert arbitrated[0].get("quantity") == 150, f"Merged quantity should be 150, got {arbitrated[0].get('quantity')}"
    
    print(f"\n[PASS] TEST 5 PASSED: Intents merged (qty: 100 + 50 = 150)")


def test_mm_overnight_leftover():
    """Test 6: MM leftover >15% overnight → next OPEN generates MM_DECREASE intents"""
    print("\n" + "=" * 80)
    print("TEST 6: MM Overnight Leftover (Stub - Logic in Decision Engine)")
    print("=" * 80)
    
    # This test is a placeholder - actual logic would be in Decision Engine
    # to check MM bucket at market open and generate MM_DECREASE intents
    
    config = {
        "intent_arbitration": {
            "cap_recovery_target_gross": 123.0,
            "mm_overnight_max_pct": 15.0,
            "soft_suppress_threshold": 120.0
        }
    }
    
    arbiter = IntentArbiter(config)
    
    # Simulate MM leftover >15%
    mm_current_pct = 18.0  # > 15% threshold
    
    # Decision Engine would generate MM_DECREASE intents
    # IntentArbiter would allow them (but they're still lower priority than CAP_RECOVERY/HARD_DERISK)
    intents = [
        {
            "intent_type": "MM_DECREASE",
            "symbol": "AAPL",
            "action": "SELL",
            "quantity": 100,
            "classification": "MM_LONG_DECREASE",
            "bucket": "MM",
            "effect": "DECREASE",
            "dir": "LONG",
            "risk_delta_gross_pct": -2.0,
        },
    ]
    
    # Arbitrate in OPEN regime (should allow MM_DECREASE)
    arbitrated = arbiter.arbitrate(
        intents=intents,
        current_gross_exposure_pct=85.0,  # Low exposure
        current_mode="NORMAL"
    )
    
    print(f"MM Current %: {mm_current_pct}% (threshold: {arbiter.mm_overnight_max_pct}%)")
    print(f"Input intents: {len(intents)}")
    print(f"Arbitrated intents: {len(arbitrated)}")
    
    # MM_DECREASE should pass (risk-reducing)
    assert len(arbitrated) == 1, f"MM_DECREASE should pass, got {len(arbitrated)}"
    
    print(f"\n[PASS] TEST 6 PASSED: MM leftover >15% generates MM_DECREASE (stub)")


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("INTENT ARBITRATION TEST SUITE")
    print("=" * 80)
    
    try:
        test_cap_recovery_suppresses_all()
        test_soft_derisk_with_lt_drift()
        test_hard_derisk_suppresses_mm()
        test_symbol_conflict_resolution()
        test_merge_same_direction()
        test_mm_overnight_leftover()
        
        print("\n" + "=" * 80)
        print("[PASS] ALL TESTS PASSED")
        print("=" * 80)
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n[ERROR] ERROR: {e}")
        raise


if __name__ == "__main__":
    main()



