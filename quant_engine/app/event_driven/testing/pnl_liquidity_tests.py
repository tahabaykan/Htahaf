"""
Test Scenarios for PnL Calculation and LiquidityGuard

A) PnL Test Scenario:
- befday_qty=2000 at prev_close=15.00
- today buy 1000 at 15.20
- today sell 1000 at 15.30
Expected: intraday realized pnl = +0.10 * 1000 = +100

B) LiquidityGuard Test Scenarios:
- LT order not capped at 2000
- MM order capped at 2000
- min lot enforced
- residual handling near close
"""

import time
from datetime import date
from app.event_driven.reporting.intraday_tracker import IntradayTracker
from app.event_driven.execution.liquidity_guard import LiquidityGuard
from app.core.logger import logger


def test_pnl_calculation():
    """Test A: Intraday PnL calculation"""
    print("\n" + "=" * 80)
    print("TEST A: Intraday PnL Calculation")
    print("=" * 80)
    
    tracker = IntradayTracker()
    account_id = "HAMMER"
    # Use unique symbol with timestamp and random component to avoid Redis conflicts
    import random
    symbol = f"TEST_PNL_{int(time.time())}_{random.randint(1000, 9999)}"
    test_date = date.today()
    
    # Clear any existing test data for this symbol (clean start)
    # Access Redis directly to delete test key
    from app.core.redis_client import get_redis_client
    redis_client = get_redis_client().sync
    if redis_client:
        key = tracker.get_tracker_key(account_id, symbol, test_date)
        redis_client.delete(key)
        # Also clear any old TEST symbols from previous runs (cleanup)
        pattern = f"{tracker.tracker_key_prefix}:{test_date.isoformat()}:{account_id}:TEST_PNL_*"
        for old_key in redis_client.keys(pattern):
            redis_client.delete(old_key)
    
    # Scenario: befday_qty=2000 at prev_close=15.00
    # today buy 1000 at 15.20
    # today sell 1000 at 15.30
    # Expected: intraday realized pnl = +0.10 * 1000 = +100
    
    # Buy 1000 at 15.20 (opens long position)
    realized_pnl_1, pos_1 = tracker.update_intraday_position(
        account_id=account_id,
        symbol=symbol,
        fill_qty=1000,
        fill_price=15.20,
        action="BUY",
        target_date=test_date
    )
    
    print(f"After BUY 1000 @ 15.20:")
    print(f"  Realized PnL: ${realized_pnl_1:.2f}")
    print(f"  Intraday Long Qty: {pos_1['intraday_long_qty']}")
    print(f"  Intraday Long Avg Price: ${pos_1['intraday_long_avg_price']:.2f}")
    assert realized_pnl_1 == 0.0, "No PnL on opening position"
    assert pos_1['intraday_long_qty'] == 1000, "Long position opened"
    assert pos_1['intraday_long_avg_price'] == 15.20, "Avg price correct"
    
    # Sell 1000 at 15.30 (closes long position)
    realized_pnl_2, pos_2 = tracker.update_intraday_position(
        account_id=account_id,
        symbol=symbol,
        fill_qty=1000,
        fill_price=15.30,
        action="SELL",
        target_date=test_date
    )
    
    print(f"\nAfter SELL 1000 @ 15.30:")
    print(f"  Realized PnL: ${realized_pnl_2:.2f}")
    print(f"  Cumulative Realized PnL: ${pos_2['realized_pnl']:.2f}")
    print(f"  Intraday Long Qty: {pos_2['intraday_long_qty']}")
    
    expected_pnl = (15.30 - 15.20) * 1000  # +100
    assert abs(realized_pnl_2 - expected_pnl) < 0.01, f"Expected ${expected_pnl:.2f}, got ${realized_pnl_2:.2f}"
    assert abs(pos_2['realized_pnl'] - expected_pnl) < 0.01, f"Expected cumulative ${expected_pnl:.2f}"
    assert pos_2['intraday_long_qty'] == 0, "Long position closed"
    
    print(f"\n[PASS] TEST A PASSED: Intraday PnL = ${pos_2['realized_pnl']:.2f} (expected ${expected_pnl:.2f})")


def test_liquidity_guard_lt():
    """Test B1: LT order not capped at 2000"""
    print("\n" + "=" * 80)
    print("TEST B1: LT Order Not Capped at 2000")
    print("=" * 80)
    
    guard = LiquidityGuard()
    
    # LT order with large quantity
    avg_adv = 10000000  # 10M shares/day
    base_max = guard.calculate_base_max(avg_adv)  # Should be 10000
    
    desired_qty = 5000
    clamped_qty, info = guard.clamp_quantity(
        desired_qty=desired_qty,
        symbol="AAPL",
        classification="LT_LONG_INCREASE",
        avg_adv=avg_adv,
        bucket="LT",
        minutes_to_close=None,
        intent_type=None
    )
    
    print(f"Desired Qty: {desired_qty}")
    print(f"Base Max: {base_max}")
    print(f"Clamped Qty: {clamped_qty}")
    print(f"Reason: {info.get('reason', 'N/A')}")
    
    # LT should not be capped at 2000 (only at base_max)
    assert clamped_qty == desired_qty, f"LT order should not be capped, got {clamped_qty}"
    print("\n[PASS] TEST B1 PASSED: LT order not capped at 2000")


def test_liquidity_guard_mm():
    """Test B2: MM order capped at 2000"""
    print("\n" + "=" * 80)
    print("TEST B2: MM Order Capped at 2000")
    print("=" * 80)
    
    guard = LiquidityGuard()
    
    avg_adv = 10000000  # 10M shares/day
    base_max = guard.calculate_base_max(avg_adv)  # Should be 10000
    mm_max = guard.get_bucket_max("MM")  # Should be 2000
    
    desired_qty = 5000
    clamped_qty, info = guard.clamp_quantity(
        desired_qty=desired_qty,
        symbol="AAPL",
        classification="MM_LONG_INCREASE",
        avg_adv=avg_adv,
        bucket="MM",
        minutes_to_close=None,
        intent_type=None
    )
    
    print(f"Desired Qty: {desired_qty}")
    print(f"Base Max: {base_max}")
    print(f"MM Max Cap: {mm_max}")
    print(f"Clamped Qty: {clamped_qty}")
    print(f"Reason: {info.get('reason', 'N/A')}")
    
    # MM should be capped at 2000 (min of base_max and mm_max)
    expected = min(base_max, mm_max)
    assert clamped_qty == expected, f"MM order should be capped at {expected}, got {clamped_qty}"
    print(f"\n[PASS] TEST B2 PASSED: MM order capped at {expected}")


def test_liquidity_guard_min_lot():
    """Test B3: Min lot enforced"""
    print("\n" + "=" * 80)
    print("TEST B3: Min Lot Enforced")
    print("=" * 80)
    
    guard = LiquidityGuard()
    
    avg_adv = 1000000  # 1M shares/day
    min_lot = guard.min_lot  # 200
    
    # Try order below min_lot (not near close)
    desired_qty = 100
    clamped_qty, info = guard.clamp_quantity(
        desired_qty=desired_qty,
        symbol="AAPL",
        classification="LT_LONG_INCREASE",
        avg_adv=avg_adv,
        bucket="LT",
        minutes_to_close=60,  # Not near close
        intent_type=None
    )
    
    print(f"Desired Qty: {desired_qty} (< min_lot={min_lot})")
    print(f"Clamped Qty: {clamped_qty}")
    print(f"Deferred: {info.get('deferred', False)}")
    print(f"Reason: {info.get('reason', 'N/A')}")
    
    # Should be deferred (0)
    assert clamped_qty == 0, f"Order below min_lot should be deferred, got {clamped_qty}"
    assert info.get('deferred', False), "Should be marked as deferred"
    print("\n[PASS] TEST B3 PASSED: Min lot enforced (order deferred)")


def test_liquidity_guard_residual_near_close():
    """Test B4: Residual handling near close"""
    print("\n" + "=" * 80)
    print("TEST B4: Residual Handling Near Close")
    print("=" * 80)
    
    guard = LiquidityGuard()
    
    avg_adv = 1000000
    min_lot = guard.min_lot  # 200
    
    # Try residual order near close
    desired_qty = 100  # < min_lot
    clamped_qty, info = guard.clamp_quantity(
        desired_qty=desired_qty,
        symbol="AAPL",
        classification="LT_LONG_DECREASE",
        avg_adv=avg_adv,
        bucket="LT",
        minutes_to_close=1,  # Near close (< 2 minutes)
        intent_type="HARD_DERISK"
    )
    
    print(f"Desired Qty: {desired_qty} (< min_lot={min_lot})")
    print(f"Minutes to Close: 1")
    print(f"Intent Type: HARD_DERISK")
    print(f"Clamped Qty: {clamped_qty}")
    print(f"Reason: {info.get('reason', 'N/A')}")
    
    # Should be allowed near close during HARD_DERISK
    assert clamped_qty == desired_qty, f"Residual should be allowed near close, got {clamped_qty}"
    print("\n[PASS] TEST B4 PASSED: Residual allowed near close during HARD_DERISK")


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("PNL & LIQUIDITYGUARD TEST SUITE")
    print("=" * 80)
    
    try:
        test_pnl_calculation()
        test_liquidity_guard_lt()
        test_liquidity_guard_mm()
        test_liquidity_guard_min_lot()
        test_liquidity_guard_residual_near_close()
        
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

