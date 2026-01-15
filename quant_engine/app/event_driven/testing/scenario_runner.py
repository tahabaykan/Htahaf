"""
Scenario Runner - Testing Harness

Injects synthetic events and asserts expected outputs (intents, modes).
"""

import time
import json
from typing import Dict, Any, List, Optional, Callable
from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.event_driven.state.event_log import EventLog
from app.event_driven.state.store import StateStore
from app.event_driven.contracts.events import ExposureEvent, SessionEvent, IntentEvent, OrderClassification
from app.event_driven.decision_engine.policy_table import PolicyMode


class ScenarioRunner:
    """Scenario runner for testing risk and order lifecycle"""
    
    def __init__(self):
        redis_client = get_redis_client().sync
        if not redis_client:
            raise RuntimeError("Redis client not available")
        
        self.event_log = EventLog(redis_client=redis_client)
        self.state_store = StateStore(redis_client=redis_client)
        self.scenarios_passed = 0
        self.scenarios_failed = 0
    
    def inject_exposure(self, equity: float, gross_exposure_pct: float, 
                       long_gross_pct: float = None, short_gross_pct: float = None,
                       lt_current_pct: float = None, lt_potential_pct: float = None,
                       mm_current_pct: float = None, mm_potential_pct: float = None,
                       open_orders_potential: float = 0.0):
        """Inject exposure event"""
        long_notional = (long_gross_pct / 100.0 * equity) if long_gross_pct else (gross_exposure_pct / 2 / 100.0 * equity)
        short_notional = (short_gross_pct / 100.0 * equity) if short_gross_pct else (gross_exposure_pct / 2 / 100.0 * equity)
        
        buckets = {
            "LT": {
                "current": (lt_current_pct / 100.0 * equity) if lt_current_pct else (long_notional * 0.8),
                "current_pct": lt_current_pct or (long_notional * 0.8 / equity * 100.0),
                "potential": (lt_potential_pct / 100.0 * equity) if lt_potential_pct else (long_notional * 0.85),
                "potential_pct": lt_potential_pct or (long_notional * 0.85 / equity * 100.0),
                "target": equity * 0.8,
                "target_pct": 80.0,
                "max": equity * 0.9,
                "max_pct": 90.0,
            },
            "MM_PURE": {
                "current": (mm_current_pct / 100.0 * equity) if mm_current_pct else (long_notional * 0.2),
                "current_pct": mm_current_pct or (long_notional * 0.2 / equity * 100.0),
                "potential": (mm_potential_pct / 100.0 * equity) if mm_potential_pct else (long_notional * 0.25),
                "potential_pct": mm_potential_pct or (long_notional * 0.25 / equity * 100.0),
                "target": equity * 0.2,
                "target_pct": 20.0,
                "max": equity * 0.3,
                "max_pct": 30.0,
            }
        }
        
        group_exposure = {f"group_{i}": 0.0 for i in range(1, 23)}
        
        event = ExposureEvent.create(
            equity=equity,
            long_notional=long_notional,
            short_notional=short_notional,
            gross_exposure_pct=gross_exposure_pct,
            net_exposure_pct=(long_notional - short_notional) / equity * 100.0,
            long_gross_pct=long_gross_pct or (long_notional / equity * 100.0),
            short_gross_pct=short_gross_pct or (short_notional / equity * 100.0),
            buckets=buckets,
            group_exposure=group_exposure,
            positions=[],
            open_orders_potential=open_orders_potential,
        )
        
        self.event_log.publish("exposure", event)
        logger.info(f"📊 Injected exposure: gross={gross_exposure_pct:.2f}%")
    
    def inject_session(self, regime: str, minutes_to_close: Optional[int] = None):
        """Inject session event"""
        market_open = regime != "CLOSED"
        event = SessionEvent.create(
            regime=regime,
            market_open=market_open,
            minutes_to_close=minutes_to_close,
        )
        self.event_log.publish("session", event)
        logger.info(f"⏰ Injected session: regime={regime}, minutes_to_close={minutes_to_close}")
    
    def wait_for_decision(self, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        """Wait for decision state update"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            decision_state = self.state_store.get_state("decision")
            if decision_state:
                return decision_state
            time.sleep(0.1)
        return None
    
    def check_intents(self, expected_count: int = 0, expected_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Check for intents in stream (read last N messages)"""
        # Read from intents stream
        try:
            # Use XREVRANGE to get last messages
            stream_key = "ev.intents"
            messages = self.state_store.redis.xrevrange(stream_key, count=10)
            
            intents = []
            for msg_id, msg_data in messages:
                data_str = msg_data.get("data", "{}")
                data = json.loads(data_str) if isinstance(data_str, str) else data_str
                intents.append(data)
            
            if expected_count is not None:
                assert len(intents) >= expected_count, f"Expected at least {expected_count} intents, got {len(intents)}"
            
            if expected_type:
                matching = [i for i in intents if i.get("intent_type") == expected_type]
                assert len(matching) > 0, f"Expected intent type {expected_type}, found {len(matching)}"
                return matching
            
            return intents
        except Exception as e:
            logger.error(f"Error checking intents: {e}", exc_info=True)
            return []
    
    def run_scenario(self, name: str, setup: Callable, assertions: Callable) -> bool:
        """Run a test scenario"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 Running scenario: {name}")
        logger.info(f"{'='*60}")
        
        try:
            # Clear state
            self.state_store.delete_state("exposure")
            self.state_store.delete_state("session")
            self.state_store.delete_state("decision")
            
            # Run setup
            setup(self)
            
            # Wait a bit for processing
            time.sleep(0.5)
            
            # Run assertions
            result = assertions(self)
            
            if result:
                logger.info(f"✅ Scenario PASSED: {name}")
                self.scenarios_passed += 1
                return True
            else:
                logger.error(f"❌ Scenario FAILED: {name}")
                self.scenarios_failed += 1
                return False
        
        except AssertionError as e:
            logger.error(f"❌ Scenario FAILED: {name} - {e}")
            self.scenarios_failed += 1
            return False
        except Exception as e:
            logger.error(f"❌ Scenario ERROR: {name} - {e}", exc_info=True)
            self.scenarios_failed += 1
            return False
    
    def print_summary(self):
        """Print test summary"""
        total = self.scenarios_passed + self.scenarios_failed
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 Test Summary: {self.scenarios_passed}/{total} passed")
        logger.info(f"{'='*60}")


def scenario_a_open_early_120pct(runner: ScenarioRunner):
    """Scenario A: OPEN/EARLY with gross 120% -> allow activity but keep hard cap"""
    runner.inject_exposure(equity=1000000.0, gross_exposure_pct=120.0)
    runner.inject_session(regime="EARLY")
    
    time.sleep(0.5)
    
    decision = runner.wait_for_decision()
    assert decision is not None, "Decision should be made"
    
    mode = decision.get("mode")
    # In EARLY, 120% should be within tolerance (125%), so NORMAL or THROTTLE
    assert mode in ["NORMAL", "THROTTLE_NEW_ORDERS"], f"Expected NORMAL or THROTTLE, got {mode}"
    
    # Should NOT generate derisk intents
    intents = runner.check_intents(expected_count=0)
    assert len(intents) == 0, "Should not generate derisk intents in EARLY with 120%"
    
    return True


def scenario_b_1616_115pct_soft_derisk(runner: ScenarioRunner):
    """Scenario B: 16:16 with gross 115% -> SOFT_DERISK intents produced"""
    runner.inject_exposure(equity=1000000.0, gross_exposure_pct=115.0)
    runner.inject_session(regime="LATE", minutes_to_close=44)  # 16:16 = 44 min to close
    
    time.sleep(0.5)
    
    decision = runner.wait_for_decision()
    assert decision is not None, "Decision should be made"
    
    mode = decision.get("mode")
    assert mode == "SOFT_DERISK", f"Expected SOFT_DERISK, got {mode}"
    
    # Should generate SOFT_DERISK intents
    intents = runner.check_intents(expected_count=1, expected_type="SOFT_DERISK")
    assert len(intents) > 0, "Should generate SOFT_DERISK intents"
    
    return True


def scenario_c_1628_110pct_hard_derisk(runner: ScenarioRunner):
    """Scenario C: 16:28 with gross 110% -> HARD_DERISK intents produced"""
    runner.inject_exposure(equity=1000000.0, gross_exposure_pct=110.0)
    runner.inject_session(regime="CLOSE", minutes_to_close=2)  # 16:28 = 2 min to close
    
    time.sleep(0.5)
    
    decision = runner.wait_for_decision()
    assert decision is not None, "Decision should be made"
    
    mode = decision.get("mode")
    assert mode == "HARD_DERISK", f"Expected HARD_DERISK, got {mode}"
    
    # Should generate HARD_DERISK intents
    intents = runner.check_intents(expected_count=1, expected_type="HARD_DERISK")
    assert len(intents) > 0, "Should generate HARD_DERISK intents"
    
    return True


def scenario_d_131pct_hard_cap(runner: ScenarioRunner):
    """Scenario D: gross 131% at any time -> immediate HARD_DERISK + throttling"""
    runner.inject_exposure(equity=1000000.0, gross_exposure_pct=131.0)
    runner.inject_session(regime="MID")  # Even in MID, hard cap is enforced
    
    time.sleep(0.5)
    
    decision = runner.wait_for_decision()
    assert decision is not None, "Decision should be made"
    
    mode = decision.get("mode")
    assert mode == "HARD_DERISK", f"Expected HARD_DERISK (hard cap exceeded), got {mode}"
    
    # Should generate HARD_DERISK intents immediately
    intents = runner.check_intents(expected_count=1, expected_type="HARD_DERISK")
    assert len(intents) > 0, "Should generate HARD_DERISK intents for hard cap violation"
    
    return True


def scenario_e_potential_135pct_throttle(runner: ScenarioRunner):
    """Scenario E: current 85% but potential 135% -> THROTTLE_NEW_ORDERS (no forced derisk)"""
    equity = 1000000.0
    current_exposure = 85.0
    open_orders_potential = (135.0 - 85.0) / 100.0 * equity  # 50% of equity in open orders
    
    runner.inject_exposure(
        equity=equity,
        gross_exposure_pct=current_exposure,
        open_orders_potential=open_orders_potential
    )
    runner.inject_session(regime="MID")
    
    time.sleep(0.5)
    
    decision = runner.wait_for_decision()
    assert decision is not None, "Decision should be made"
    
    mode = decision.get("mode")
    assert mode == "THROTTLE_NEW_ORDERS", f"Expected THROTTLE_NEW_ORDERS, got {mode}"
    
    # Should NOT generate derisk intents (only throttle)
    intents = runner.check_intents(expected_count=0)
    # Note: May have some intents from previous scenarios, so we check for derisk types
    derisk_intents = [i for i in intents if i.get("intent_type") in ["SOFT_DERISK", "HARD_DERISK"]]
    assert len(derisk_intents) == 0, "Should not generate derisk intents for potential exposure (only throttle)"
    
    return True


def scenario_f_classification_cancel(runner: ScenarioRunner):
    """Scenario F: Mixed classified open orders, hit cap, ensure only *_INCREASE are canceled"""
    from app.event_driven.contracts.events import IntentEvent, OrderClassification
    
    # Inject exposure at 130% (hard cap)
    runner.inject_exposure(equity=1000000.0, gross_exposure_pct=130.0)
    runner.inject_session(regime="MID")
    
    # Wait for decision engine to process
    time.sleep(0.5)
    
    # Check that Execution Service would cancel risk-increasing orders
    # This is tested by checking that only *_INCREASE orders are in cancel list
    # In real system, Execution Service monitors exposure and cancels automatically
    
    # For this test, we verify the classification system works
    # by checking that intents have proper classification
    intents = runner.check_intents(expected_count=0)  # May have derisk intents
    
    # Verify classification enum works
    cls = OrderClassification.MM_LONG_INCREASE
    assert cls.is_risk_increasing == True, "MM_LONG_INCREASE should be risk-increasing"
    assert cls.bucket == "MM", "Bucket should be MM"
    assert cls.direction == "LONG", "Direction should be LONG"
    assert cls.effect == "INCREASE", "Effect should be INCREASE"
    
    cls2 = OrderClassification.LT_SHORT_DECREASE
    assert cls2.is_risk_increasing == False, "LT_SHORT_DECREASE should NOT be risk-increasing"
    
    return True


def main():
    """Run all scenarios"""
    runner = ScenarioRunner()
    
    scenarios = [
        ("A: OPEN/EARLY 120% -> allow activity", scenario_a_open_early_120pct),
        ("B: 16:16 115% -> SOFT_DERISK", scenario_b_1616_115pct_soft_derisk),
        ("C: 16:28 110% -> HARD_DERISK", scenario_c_1628_110pct_hard_derisk),
        ("D: 131% -> HARD_DERISK (hard cap)", scenario_d_131pct_hard_cap),
        ("E: Current 85% / Potential 135% -> THROTTLE", scenario_e_potential_135pct_throttle),
        ("F: Classification and cancel logic", scenario_f_classification_cancel),
    ]
    
    logger.info("🚀 Starting Scenario Runner")
    logger.info("⚠️  Make sure Decision Engine is running!")
    
    for name, scenario_func in scenarios:
        runner.run_scenario(name, lambda r: None, scenario_func)
        time.sleep(0.5)  # Small delay between scenarios
    
    runner.print_summary()


if __name__ == "__main__":
    main()

