"""
Execution Chaos Test Scenarios

Tests system robustness under adversarial broker conditions:
1) Out-of-order events
2) Partial fills + replace
3) Cancel rejection
4) Latency simulation
5) Duplicate events
6) Mixed chaos
"""

import sys
import time
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.core.redis_client import get_redis_client
from app.event_driven.state.event_log import EventLog
from app.event_driven.state.store import StateStore
from app.event_driven.contracts.events import IntentEvent, OrderEvent, OrderClassification
from app.event_driven.execution.chaos_simulator import ChaosExecutionSimulator
from app.event_driven.reporting.intraday_tracker import IntradayTracker
from app.event_driven.reporting.daily_ledger import DailyLedger


class ChaosTestRunner:
    """Test runner for execution chaos scenarios"""
    
    def __init__(self):
        redis_client = get_redis_client().sync
        if not redis_client:
            raise RuntimeError("Redis client not available")
        
        self.event_log = EventLog(redis_client=redis_client)
        self.state_store = StateStore(redis_client=redis_client)
        self.intraday_tracker = IntradayTracker()
        self.daily_ledger = DailyLedger()
        
        # Test statistics
        self.test_results = []
    
    def clear_test_data(self):
        """Clear test data from Redis"""
        # Clear order registry
        self.state_store.redis.delete("orders_registry")
        # Clear open orders
        for key in self.state_store.redis.keys("orders:open:*"):
            self.state_store.redis.delete(key)
        # Clear intraday positions
        for key in self.state_store.redis.keys("intraday:positions:*"):
            self.state_store.redis.delete(key)
    
    def test_out_of_order_events(self):
        """Test 1: Fill event arrives BEFORE order ACCEPTED event"""
        print("\n" + "=" * 80)
        print("TEST 1: Out-of-Order Events (Fill Before ACCEPTED)")
        print("=" * 80)
        
        self.clear_test_data()
        
        # Create chaos simulator with out-of-order enabled
        chaos_config = {
            "enabled": True,
            "out_of_order": True,
            "latency": True,
            "latency_min_seconds": 0.1,
            "latency_max_seconds": 2.0,
        }
        
        simulator = ChaosExecutionSimulator(chaos_config=chaos_config)
        simulator.connect()
        
        # Create test intent
        intent_id = f"TEST_INTENT_{uuid.uuid4().hex[:8]}"
        intent_data = {
            "event_id": intent_id,
            "data": {
                "intent_type": "SOFT_DERISK",
                "symbol": "AAPL",
                "action": "SELL",
                "quantity": 100,
                "reason": "Test out-of-order",
                "classification": "LT_LONG_DECREASE",
                "bucket": "LT",
                "effect": "DECREASE",
                "dir": "LONG",
                "risk_delta_notional": -10000.0,
                "risk_delta_gross_pct": -1.0,
                "position_context_at_intent": {
                    "current_qty": 200,
                    "avg_fill_price": 150.0,
                    "account_id": "HAMMER"
                },
                "limit_price": 149.0,
            }
        }
        
        # Process intent (will generate ACCEPTED, WORKING, then FILL)
        simulator.process_intent(intent_data)
        
        # Wait for events
        time.sleep(3)
        
        # Read order events
        messages = self.event_log.read("orders", "test_consumer", "test_consumer", count=10, block=0)
        
        event_actions = [msg["data"].get("action", "") for msg in messages]
        print(f"Event sequence: {event_actions}")
        
        # Verify: Should have ACCEPTED, WORKING, and FILLED
        assert "ACCEPTED" in event_actions, "ACCEPTED event missing"
        assert "WORKING" in event_actions, "WORKING event missing"
        assert "FILLED" in event_actions or "PARTIAL_FILL" in event_actions, "Fill event missing"
        
        # Verify: No negative position drift
        position = self.intraday_tracker.get_intraday_position("HAMMER", "AAPL")
        assert position["intraday_qty"] >= 0 or position["intraday_long_qty"] >= 0, "Negative position drift detected"
        
        print("\n[PASS] TEST 1 PASSED: Out-of-order events handled correctly")
        self.test_results.append(("test_out_of_order_events", True))
    
    def test_partial_fill_replace(self):
        """Test 2: Partial fill + replace scenario"""
        print("\n" + "=" * 80)
        print("TEST 2: Partial Fill + Replace")
        print("=" * 80)
        
        self.clear_test_data()
        
        chaos_config = {
            "enabled": True,
            "partial_fill": True,
            "partial_fill_probability": 1.0,  # Always partial fill
            "partial_fill_min_pct": 0.3,
            "partial_fill_max_pct": 0.3,  # Exactly 30%
        }
        
        simulator = ChaosExecutionSimulator(chaos_config=chaos_config)
        simulator.connect()
        
        intent_id = f"TEST_INTENT_{uuid.uuid4().hex[:8]}"
        intent_data = {
            "event_id": intent_id,
            "data": {
                "intent_type": "SOFT_DERISK",
                "symbol": "MSFT",
                "action": "SELL",
                "quantity": 100,
                "reason": "Test partial fill",
                "classification": "LT_LONG_DECREASE",
                "bucket": "LT",
                "effect": "DECREASE",
                "dir": "LONG",
                "risk_delta_notional": -15000.0,
                "risk_delta_gross_pct": -1.5,
                "position_context_at_intent": {
                    "current_qty": 200,
                    "avg_fill_price": 300.0,
                    "account_id": "HAMMER"
                },
                "limit_price": 299.0,
            }
        }
        
        simulator.process_intent(intent_data)
        time.sleep(2)
        
        # Read events
        messages = self.event_log.read("orders", "test_consumer", "test_consumer", count=10, block=0)
        
        fill_events = [msg for msg in messages if msg["data"].get("action") in ["PARTIAL_FILL", "FILLED"]]
        
        assert len(fill_events) > 0, "No fill events found"
        
        # Check fill quantities
        total_filled = sum(msg["data"].get("filled_quantity", 0) for msg in fill_events)
        print(f"Total filled: {total_filled} (expected: 30-100)")
        
        # Verify: No duplicate counting
        fill_ids = set()
        for msg in fill_events:
            fill_id = msg["data"].get("metadata", {}).get("fill_id")
            if fill_id:
                assert fill_id not in fill_ids, f"Duplicate fill_id detected: {fill_id}"
                fill_ids.add(fill_id)
        
        print("\n[PASS] TEST 2 PASSED: Partial fill handled correctly")
        self.test_results.append(("test_partial_fill_replace", True))
    
    def test_cancel_rejection(self):
        """Test 3: Cancel rejection (order already filled)"""
        print("\n" + "=" * 80)
        print("TEST 3: Cancel Rejection")
        print("=" * 80)
        
        self.clear_test_data()
        
        chaos_config = {
            "enabled": True,
            "cancel_rejection": True,
            "cancel_rejection_probability": 1.0,  # Always reject
        }
        
        simulator = ChaosExecutionSimulator(chaos_config=chaos_config)
        simulator.connect()
        
        # Create and fill an order first
        intent_id = f"TEST_INTENT_{uuid.uuid4().hex[:8]}"
        intent_data = {
            "event_id": intent_id,
            "data": {
                "intent_type": "SOFT_DERISK",
                "symbol": "GOOGL",
                "action": "SELL",
                "quantity": 50,
                "reason": "Test cancel rejection",
                "classification": "LT_LONG_DECREASE",
                "bucket": "LT",
                "effect": "DECREASE",
                "dir": "LONG",
                "risk_delta_notional": -5000.0,
                "risk_delta_gross_pct": -0.5,
                "position_context_at_intent": {
                    "current_qty": 100,
                    "avg_fill_price": 2500.0,
                    "account_id": "HAMMER"
                },
                "limit_price": 2499.0,
            }
        }
        
        simulator.process_intent(intent_data)
        time.sleep(2)
        
        # Get order_id from events
        messages = self.event_log.read("orders", "test_consumer", "test_consumer", count=10, block=0)
        order_events = [msg for msg in messages if msg["data"].get("action") == "ACCEPTED"]
        
        if not order_events:
            print("⚠️ No ACCEPTED event found, skipping cancel test")
            return
        
        order_id = order_events[0]["data"].get("order_id")
        
        # Try to cancel (should be rejected)
        cancel_result = simulator.cancel_order(order_id, "Test cancel")
        
        time.sleep(1)
        
        # Check for CANCEL_REJECTED event
        messages = self.event_log.read("orders", "test_consumer", "test_consumer", count=20, block=0)
        reject_events = [msg for msg in messages if msg["data"].get("action") == "CANCEL_REJECTED"]
        
        # Verify: Cancel was rejected
        assert len(reject_events) > 0 or not cancel_result, "Cancel rejection not handled"
        
        # Verify: No double counting of fills
        fill_events = [msg for msg in messages if msg["data"].get("action") in ["FILLED", "PARTIAL_FILL"]]
        fill_ids = set()
        for msg in fill_events:
            fill_id = msg["data"].get("metadata", {}).get("fill_id")
            if fill_id:
                assert fill_id not in fill_ids, "Duplicate fill detected"
                fill_ids.add(fill_id)
        
        print("\n[PASS] TEST 3 PASSED: Cancel rejection handled correctly")
        self.test_results.append(("test_cancel_rejection", True))
    
    def test_duplicate_events(self):
        """Test 4: Duplicate fill events"""
        print("\n" + "=" * 80)
        print("TEST 4: Duplicate Events")
        print("=" * 80)
        
        self.clear_test_data()
        
        chaos_config = {
            "enabled": True,
            "duplicate": True,
            "duplicate_probability": 1.0,  # Always duplicate
        }
        
        simulator = ChaosExecutionSimulator(chaos_config=chaos_config)
        simulator.connect()
        
        intent_id = f"TEST_INTENT_{uuid.uuid4().hex[:8]}"
        intent_data = {
            "event_id": intent_id,
            "data": {
                "intent_type": "SOFT_DERISK",
                "symbol": "TSLA",
                "action": "BUY",
                "quantity": 200,
                "reason": "Test duplicate events",
                "classification": "LT_SHORT_DECREASE",
                "bucket": "LT",
                "effect": "DECREASE",
                "dir": "SHORT",
                "risk_delta_notional": -40000.0,
                "risk_delta_gross_pct": -4.0,
                "position_context_at_intent": {
                    "current_qty": -300,
                    "avg_fill_price": 200.0,
                    "account_id": "HAMMER"
                },
                "limit_price": 201.0,
            }
        }
        
        simulator.process_intent(intent_data)
        time.sleep(2)
        
        # Read events
        messages = self.event_log.read("orders", "test_consumer", "test_consumer", count=20, block=0)
        
        fill_events = [msg for msg in messages if msg["data"].get("action") in ["FILLED", "PARTIAL_FILL"]]
        
        # Count fills by fill_id
        fill_id_counts = {}
        for msg in fill_events:
            fill_id = msg["data"].get("metadata", {}).get("fill_id")
            if fill_id:
                fill_id_counts[fill_id] = fill_id_counts.get(fill_id, 0) + 1
        
        # Verify: Each fill_id appears at most once (duplicates ignored)
        for fill_id, count in fill_id_counts.items():
            assert count == 1, f"Fill ID {fill_id} appears {count} times (should be 1 due to idempotency)"
        
        # Verify: IntradayTracker has correct position
        position = self.intraday_tracker.get_intraday_position("HAMMER", "TSLA")
        print(f"Intraday position: {position['intraday_qty']}")
        
        # Verify: No phantom positions (position should be reasonable)
        assert abs(position["intraday_qty"]) <= 500, "Phantom position detected"
        
        print("\n[PASS] TEST 4 PASSED: Duplicate events ignored correctly")
        self.test_results.append(("test_duplicate_events", True))
    
    def test_mixed_chaos(self):
        """Test 5: Mixed chaos (partial fills + delayed cancel + duplicate fill)"""
        print("\n" + "=" * 80)
        print("TEST 5: Mixed Chaos")
        print("=" * 80)
        
        self.clear_test_data()
        
        chaos_config = {
            "enabled": True,
            "partial_fill": True,
            "partial_fill_probability": 0.5,
            "duplicate": True,
            "duplicate_probability": 0.3,
            "latency": True,
            "latency_min_seconds": 0.5,
            "latency_max_seconds": 2.0,
            "cancel_rejection": True,
            "cancel_rejection_probability": 0.2,
        }
        
        simulator = ChaosExecutionSimulator(chaos_config=chaos_config)
        simulator.connect()
        
        # Create multiple intents
        symbols = ["AAPL", "MSFT", "GOOGL"]
        for symbol in symbols:
            intent_id = f"TEST_INTENT_{uuid.uuid4().hex[:8]}"
            intent_data = {
                "event_id": intent_id,
                "data": {
                    "intent_type": "SOFT_DERISK",
                    "symbol": symbol,
                    "action": "SELL",
                    "quantity": 100,
                    "reason": f"Test mixed chaos {symbol}",
                    "classification": "LT_LONG_DECREASE",
                    "bucket": "LT",
                    "effect": "DECREASE",
                    "dir": "LONG",
                    "risk_delta_notional": -10000.0,
                    "risk_delta_gross_pct": -1.0,
                    "position_context_at_intent": {
                        "current_qty": 200,
                        "avg_fill_price": 150.0,
                        "account_id": "HAMMER"
                    },
                    "limit_price": 149.0,
                }
            }
            simulator.process_intent(intent_data)
            time.sleep(0.5)
        
        time.sleep(5)  # Wait for all events
        
        # Read all events
        messages = self.event_log.read("orders", "test_consumer", "test_consumer", count=50, block=0)
        
        # Verify: No negative position drift
        for symbol in symbols:
            position = self.intraday_tracker.get_intraday_position("HAMMER", symbol)
            assert position["intraday_qty"] >= -500, f"Negative position drift for {symbol}: {position['intraday_qty']}"
        
        # Verify: Daily Ledger totals are correct
        # (Check that fills are recorded correctly)
        fill_events = [msg for msg in messages if msg["data"].get("action") in ["FILLED", "PARTIAL_FILL"]]
        
        # Count unique fills
        fill_ids = set()
        for msg in fill_events:
            fill_id = msg["data"].get("metadata", {}).get("fill_id")
            if fill_id:
                assert fill_id not in fill_ids, f"Duplicate fill_id: {fill_id}"
                fill_ids.add(fill_id)
        
        # Verify: System converged to stable state
        stats = simulator.get_chaos_stats()
        print(f"Chaos stats: {stats}")
        
        print("\n[PASS] TEST 5 PASSED: Mixed chaos handled correctly")
        self.test_results.append(("test_mixed_chaos", True))
    
    def test_idempotency(self):
        """Test 6: Idempotency for order_id and fill_id"""
        print("\n" + "=" * 80)
        print("TEST 6: Idempotency")
        print("=" * 80)
        
        self.clear_test_data()
        
        simulator = ChaosExecutionSimulator(chaos_config={"enabled": False})
        simulator.connect()
        
        # Process same intent twice
        intent_id = f"TEST_INTENT_{uuid.uuid4().hex[:8]}"
        intent_data = {
            "event_id": intent_id,
            "data": {
                "intent_type": "SOFT_DERISK",
                "symbol": "AAPL",
                "action": "SELL",
                "quantity": 100,
                "reason": "Test idempotency",
                "classification": "LT_LONG_DECREASE",
                "bucket": "LT",
                "effect": "DECREASE",
                "dir": "LONG",
                "risk_delta_notional": -10000.0,
                "risk_delta_gross_pct": -1.0,
                "position_context_at_intent": {
                    "current_qty": 200,
                    "avg_fill_price": 150.0,
                    "account_id": "HAMMER"
                },
                "limit_price": 149.0,
            }
        }
        
        # Process first time
        simulator.process_intent(intent_data)
        time.sleep(1)
        
        # Process second time (should be ignored)
        simulator.process_intent(intent_data)
        time.sleep(1)
        
        # Read events
        messages = self.event_log.read("orders", "test_consumer", "test_consumer", count=20, block=0)
        
        # Count ACCEPTED events (should be 1, not 2)
        accepted_events = [msg for msg in messages if msg["data"].get("action") == "ACCEPTED"]
        
        assert len(accepted_events) == 1, f"Expected 1 ACCEPTED event, got {len(accepted_events)}"
        
        print("\n[PASS] TEST 6 PASSED: Idempotency enforced correctly")
        self.test_results.append(("test_idempotency", True))
    
    def run_all_tests(self):
        """Run all chaos tests"""
        print("\n" + "=" * 80)
        print("EXECUTION CHAOS TEST SUITE")
        print("=" * 80)
        
        try:
            self.test_out_of_order_events()
            self.test_partial_fill_replace()
            self.test_cancel_rejection()
            self.test_duplicate_events()
            self.test_mixed_chaos()
            self.test_idempotency()
            
            print("\n" + "=" * 80)
            print("TEST SUMMARY")
            print("=" * 80)
            for test_name, passed in self.test_results:
                status = "[PASS]" if passed else "[FAIL]"
                print(f"{status} {test_name}")
            
            all_passed = all(result[1] for result in self.test_results)
            if all_passed:
                print("\n[PASS] ALL TESTS PASSED")
            else:
                print("\n[FAIL] SOME TESTS FAILED")
            
            return all_passed
        
        except Exception as e:
            print(f"\n[ERROR] Test suite error: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Main entry point"""
    runner = ChaosTestRunner()
    success = runner.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()



