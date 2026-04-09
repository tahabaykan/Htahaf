"""
ADDNEWPOS v1 Validation / Replay Harness

Tests ADDNEWPOS v1 decision engine against expected behavior.
Validates that decisions match expected outcomes, including exposure eligibility.

Purpose:
- Validate ADDNEWPOS v1 produces correct BUY/ADD decisions
- Validate exposure eligibility checks
- Validate symbol filtering
- Identify differences and report them clearly
- Human-readable output for analysis
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from app.core.logger import logger
from app.psfalgo.decision_models import (
    DecisionRequest,
    DecisionResponse,
    Decision,
    PositionSnapshot,
    SymbolMetrics,
    ExposureSnapshot
)
from app.psfalgo.addnewpos_engine import addnewpos_decision_engine, initialize_addnewpos_engine
from app.psfalgo.decision_cooldown import initialize_decision_cooldown_manager
from app.psfalgo.confidence_calculator import initialize_confidence_calculator


@dataclass
class ValidationTestCase:
    """
    Validation test case.
    """
    name: str
    description: str
    input_request: DecisionRequest
    expected_outcome: Dict[str, Any]  # Expected decisions/filtered
    janall_behavior: str  # What Janall would do
    category: str  # "BUY", "ADD", "FILTERED", "EXPOSURE_INELIGIBLE", etc.
    cooldown_setup: Optional[Dict[str, datetime]] = None  # For test isolation


@dataclass
class ValidationResult:
    """
    Validation result for a test case.
    """
    test_case: ValidationTestCase
    actual_response: DecisionResponse
    passed: bool
    differences: List[str]
    details: Dict[str, Any]
    diff_categories: Dict[str, List[str]]  # LOGIC_MISMATCH, INTENTIONAL_DIFF, FORMAT_DIFF, TEST_SETUP_ERROR


class AddnewposValidationHarness:
    """
    ADDNEWPOS Validation Harness.
    
    Tests ADDNEWPOS v1 against expected behavior.
    """
    
    def __init__(self):
        """Initialize validation harness"""
        self.test_cases: List[ValidationTestCase] = []
        self.results: List[ValidationResult] = []
        
        # Initialize engines
        initialize_addnewpos_engine()
        initialize_decision_cooldown_manager(cooldown_minutes=5.0)
        initialize_confidence_calculator()
    
    def _reset_test_state(self):
        """
        Reset test state between test cases.
        Clears cooldown manager and any global state.
        """
        from app.psfalgo.decision_cooldown import get_decision_cooldown_manager
        cooldown_manager = get_decision_cooldown_manager()
        if cooldown_manager:
            cooldown_manager.clear_all_cooldowns()
            logger.debug("Test state reset: All cooldowns cleared")
    
    def add_test_case(self, test_case: ValidationTestCase):
        """Add a test case"""
        self.test_cases.append(test_case)
    
    async def run_test_case(self, test_case: ValidationTestCase) -> ValidationResult:
        """
        Run a single test case.
        
        Args:
            test_case: Test case to run
            
        Returns:
            ValidationResult
        """
        logger.info(f"Running test case: {test_case.name}")
        
        # Reset test state before each test (isolation)
        self._reset_test_state()
        
        # Setup test-specific state (e.g., cooldown)
        if test_case.cooldown_setup:
            from app.psfalgo.decision_cooldown import get_decision_cooldown_manager
            cooldown_manager = get_decision_cooldown_manager()
            if cooldown_manager:
                for symbol, cooldown_ts in test_case.cooldown_setup.items():
                    cooldown_manager.set_decision_ts(symbol, cooldown_ts)
        
        # Run ADDNEWPOS engine
        actual_response = await addnewpos_decision_engine(test_case.input_request)
        
        # Compare with expected outcome
        passed, differences, details, diff_categories = self._compare_results(
            test_case,
            actual_response
        )
        
        result = ValidationResult(
            test_case=test_case,
            actual_response=actual_response,
            passed=passed,
            differences=differences,
            details=details,
            diff_categories=diff_categories
        )
        
        self.results.append(result)
        return result
    
    def _compare_results(
        self,
        test_case: ValidationTestCase,
        actual_response: DecisionResponse
    ) -> Tuple[bool, List[str], Dict[str, Any], Dict[str, List[str]]]:
        """
        Compare actual response with expected outcome using semantic matching.
        
        Returns:
            (passed, differences, details, diff_categories)
        """
        differences = []
        diff_categories = {
            'LOGIC_MISMATCH': [],
            'INTENTIONAL_DIFF': [],
            'FORMAT_DIFF': [],
            'TEST_SETUP_ERROR': []
        }
        details = {}
        
        expected = test_case.expected_outcome
        
        # Check eligibility first (ADDNEWPOS specific)
        expected_eligible = expected.get('eligible', True)
        # Check if response has decisions or was filtered due to eligibility
        actual_eligible = len(actual_response.decisions) > 0 or len(actual_response.filtered_out) > 0
        
        if expected_eligible != actual_eligible:
            diff_msg = f"Eligibility mismatch: Expected {expected_eligible}, Got {actual_eligible}"
            differences.append(diff_msg)
            diff_categories['LOGIC_MISMATCH'].append(diff_msg)
        
        # Check total decisions count
        expected_decisions_count = expected.get('decisions_count', 0)
        actual_decisions_count = len(actual_response.decisions)
        
        if actual_decisions_count != expected_decisions_count:
            diff_msg = f"Decision count mismatch: Expected {expected_decisions_count}, Got {actual_decisions_count}"
            differences.append(diff_msg)
            diff_categories['LOGIC_MISMATCH'].append(diff_msg)
        
        # Check total filtered count
        expected_filtered_count = expected.get('filtered_count', 0)
        actual_filtered_count = len(actual_response.filtered_out)
        
        if actual_filtered_count != expected_filtered_count:
            diff_msg = f"Filtered count mismatch: Expected {expected_filtered_count}, Got {actual_filtered_count}"
            differences.append(diff_msg)
            diff_categories['LOGIC_MISMATCH'].append(diff_msg)
        
        # Check specific symbols
        expected_symbols = expected.get('symbols', {})
        
        for symbol, expected_symbol_data in expected_symbols.items():
            # Find actual decision or filtered
            actual_decision = None
            for d in actual_response.decisions:
                if d.symbol == symbol:
                    actual_decision = d
                    break
            
            if not actual_decision:
                for d in actual_response.filtered_out:
                    if d.symbol == symbol:
                        actual_decision = d
                        break
            
            # Compare
            expected_action = expected_symbol_data.get('action')  # "BUY", "ADD", or "FILTERED"
            expected_reason = expected_symbol_data.get('reason', '')
            expected_filter_reasons = expected_symbol_data.get('filter_reasons', [])
            
            if not actual_decision:
                diff_msg = f"{symbol}: Expected {expected_action}, but no decision found"
                differences.append(diff_msg)
                diff_categories['LOGIC_MISMATCH'].append(diff_msg)
                continue
            
            # Check action (semantic: exact match required)
            if actual_decision.action != expected_action:
                diff_msg = f"{symbol}: Action mismatch - Expected {expected_action}, Got {actual_decision.action}"
                differences.append(diff_msg)
                diff_categories['LOGIC_MISMATCH'].append(diff_msg)
            
            # Check reason (for BUY/ADD decisions) - SEMANTIC MATCHING
            if expected_action in ["BUY", "ADD"] and expected_reason:
                if not self._semantic_match_reason(expected_reason, actual_decision.reason):
                    diff_msg = f"{symbol}: Reason mismatch - Expected contains '{expected_reason}', Got '{actual_decision.reason}'"
                    differences.append(diff_msg)
                    diff_categories['FORMAT_DIFF'].append(diff_msg)
            
            # Check filter_reasons (for FILTERED decisions) - SEMANTIC MATCHING
            if expected_action == "FILTERED" and expected_filter_reasons:
                for expected_filter_reason in expected_filter_reasons:
                    if not self._semantic_match_filter_reason(expected_filter_reason, actual_decision.filter_reasons):
                        diff_msg = f"{symbol}: Filter reason mismatch - Expected '{expected_filter_reason}', Got {actual_decision.filter_reasons}"
                        differences.append(diff_msg)
                        diff_categories['FORMAT_DIFF'].append(diff_msg)
        
        passed = len(differences) == 0
        
        details = {
            'expected_eligible': expected_eligible,
            'actual_eligible': actual_eligible,
            'expected_decisions': expected_decisions_count,
            'actual_decisions': actual_decisions_count,
            'expected_filtered': expected_filtered_count,
            'actual_filtered': actual_filtered_count,
            'symbol_comparisons': len(expected_symbols)
        }
        
        return passed, differences, details, diff_categories
    
    def _semantic_match_reason(self, expected: str, actual: str) -> bool:
        """
        Semantic matching for reason strings.
        Uses contains/category-based matching instead of exact string match.
        """
        if not expected or not actual:
            return expected == actual
        
        expected_lower = expected.lower()
        actual_lower = actual.lower()
        
        # Check if expected keywords are present in actual
        keywords = ['bid buy', 'ucuzluk', 'fbtot', 'spread']
        for keyword in keywords:
            if keyword in expected_lower:
                if keyword in actual_lower:
                    return True
        
        # Fallback: contains check
        return expected_lower in actual_lower
    
    def _semantic_match_filter_reason(self, expected: str, actual_reasons: List[str]) -> bool:
        """
        Semantic matching for filter_reasons.
        Uses category-based matching.
        """
        if not expected:
            return True
        
        expected_lower = expected.lower()
        actual_reasons_str = ' | '.join(actual_reasons).lower()
        
        # Category-based matching
        categories = {
            'cooldown': ['cooldown', 'active'],
            'metrics not available': ['metrics not available', 'missing metrics'],
            'bid buy ucuzluk': ['bid buy', 'ucuzluk'],
            'fbtot': ['fbtot'],
            'spread': ['spread'],
            'avg_adv': ['avg_adv', 'avg adv'],
            'exposure': ['exposure', 'threshold', 'not eligible'],
            'max lot': ['max_lot', 'max lot', 'existing position']
        }
        
        # Check if expected category matches any actual reason
        for category, keywords in categories.items():
            if category in expected_lower:
                for keyword in keywords:
                    if keyword in actual_reasons_str:
                        return True
        
        # Fallback: contains check
        return expected_lower in actual_reasons_str
    
    async def run_all_tests(self) -> List[ValidationResult]:
        """Run all test cases with proper isolation"""
        logger.info(f"Running {len(self.test_cases)} test cases...")
        
        # Reset state before running all tests
        self._reset_test_state()
        
        for test_case in self.test_cases:
            await self.run_test_case(test_case)
        
        return self.results
    
    def generate_report(self) -> str:
        """
        Generate human-readable validation report.
        
        Returns:
            Report string
        """
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("ADDNEWPOS v1 VALIDATION REPORT")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # Summary
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.passed)
        failed_tests = total_tests - passed_tests
        
        report_lines.append(f"Total Tests: {total_tests}")
        report_lines.append(f"Passed: {passed_tests}")
        report_lines.append(f"Failed: {failed_tests}")
        report_lines.append("")
        
        # Detailed results
        for i, result in enumerate(self.results, 1):
            test_case = result.test_case
            status = "[PASS]" if result.passed else "[FAIL]"
            
            report_lines.append("-" * 80)
            report_lines.append(f"Test {i}: {test_case.name} - {status}")
            report_lines.append(f"Category: {test_case.category}")
            report_lines.append(f"Description: {test_case.description}")
            report_lines.append(f"Janall Behavior: {test_case.janall_behavior}")
            report_lines.append("")
            
            # Actual results
            report_lines.append("Actual Results:")
            report_lines.append(f"  Decisions: {len(result.actual_response.decisions)}")
            report_lines.append(f"  Filtered: {len(result.actual_response.filtered_out)}")
            
            # Decisions
            if result.actual_response.decisions:
                report_lines.append("")
                report_lines.append("  BUY/ADD Decisions:")
                for decision in result.actual_response.decisions:
                    report_lines.append(f"    {decision.symbol}:")
                    report_lines.append(f"      Action: {decision.action}")
                    report_lines.append(f"      Lot: {decision.calculated_lot}")
                    report_lines.append(f"      Reason: {decision.reason}")
                    report_lines.append(f"      Confidence: {decision.confidence:.2f}")
                    report_lines.append(f"      Step: {decision.step_number}")
            
            # Filtered
            if result.actual_response.filtered_out:
                report_lines.append("")
                report_lines.append("  FILTERED Symbols:")
                for decision in result.actual_response.filtered_out:
                    report_lines.append(f"    {decision.symbol}:")
                    report_lines.append(f"      Step: {decision.step_number}")
                    report_lines.append(f"      Reasons: {', '.join(decision.filter_reasons)}")
            
            # Differences with categories
            if result.differences:
                report_lines.append("")
                report_lines.append("  Differences:")
                for diff in result.differences:
                    report_lines.append(f"    [X] {diff}")
                
                # Show diff categories
                if result.diff_categories:
                    report_lines.append("")
                    report_lines.append("  Difference Categories:")
                    for category, diffs in result.diff_categories.items():
                        if diffs:
                            report_lines.append(f"    {category}: {len(diffs)} difference(s)")
                            for d in diffs[:3]:  # Show first 3
                                report_lines.append(f"      - {d}")
                            if len(diffs) > 3:
                                report_lines.append(f"      ... and {len(diffs) - 3} more")
            
            # Step summary
            if result.actual_response.step_summary:
                report_lines.append("")
                report_lines.append("  Step Summary:")
                for step_num, step_data in result.actual_response.step_summary.items():
                    report_lines.append(f"    Step {step_num} ({step_data.get('name', 'N/A')}):")
                    report_lines.append(f"      Total: {step_data.get('total_symbols', 0)}")
                    if 'eligible_symbols' in step_data:
                        report_lines.append(f"      Eligible: {step_data.get('eligible_symbols', 0)}")
                    if 'decisions' in step_data:
                        report_lines.append(f"      Decisions: {step_data.get('decisions', 0)}")
                    report_lines.append(f"      Filtered: {step_data.get('filtered_out', 0)}")
            
            report_lines.append("")
        
        report_lines.append("=" * 80)
        report_lines.append("END OF REPORT")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    def save_report(self, output_path: Path):
        """Save validation report to file"""
        report = self.generate_report()
        output_path.write_text(report, encoding='utf-8')
        logger.info(f"Validation report saved to {output_path}")


# ============================================================================
# TEST FIXTURES
# ============================================================================

def create_test_fixture_1() -> ValidationTestCase:
    """
    Test Case 1: Exposure Ineligible
    
    Scenario:
    - Exposure ratio: 0.85 (85%) >= threshold 0.8 (80%)
    - Mode: OFANSIF ✅
    
    Expected: Not eligible, no decisions
    """
    available_symbols = ["MS PRK", "BAC PRM", "WFC PRY"]
    
    metrics = {
        "MS PRK": SymbolMetrics(
            symbol="MS PRK",
            bid_buy_ucuzluk=0.08,
            fbtot=1.15,
            spread=0.03,
            avg_adv=6000.0,
            bid=27.28,
            ask=27.32,
            last=27.30,
            timestamp=datetime.now()
        ),
        "BAC PRM": SymbolMetrics(
            symbol="BAC PRM",
            bid_buy_ucuzluk=0.07,
            fbtot=1.12,
            spread=0.04,
            avg_adv=3000.0,
            bid=25.18,
            ask=25.22,
            last=25.20,
            timestamp=datetime.now()
        ),
        "WFC PRY": SymbolMetrics(
            symbol="WFC PRY",
            bid_buy_ucuzluk=0.09,
            fbtot=1.18,
            spread=0.02,
            avg_adv=5000.0,
            bid=24.48,
            ask=24.52,
            last=24.50,
            timestamp=datetime.now()
        )
    }
    
    exposure = ExposureSnapshot(
        pot_total=54000.0,  # 85% of pot_max (exceeds 80% threshold)
        pot_max=63636.0,
        long_lots=600.0,
        short_lots=0.0,
        net_exposure=600.0,
        timestamp=datetime.now()
    )
    
    request = DecisionRequest(
        positions=[],
        metrics=metrics,
        exposure=exposure,
        available_symbols=available_symbols,
        cycle_count=1,
        snapshot_ts=datetime.now()
    )
    
    return ValidationTestCase(
        name="Test Case 1: Exposure Ineligible",
        description="Exposure ratio >= threshold - should not run",
        input_request=request,
        expected_outcome={
            'eligible': False,
            'decisions_count': 0,
            'filtered_count': 0,
            'symbols': {}
        },
        janall_behavior="Not eligible (exposure ratio >= 80%)",
        category="EXPOSURE_INELIGIBLE"
    )


def create_test_fixture_2() -> ValidationTestCase:
    """
    Test Case 2: Exposure Eligible - Perfect BUY
    
    Scenario:
    - Exposure ratio: 0.5 (50%) < threshold 0.8 (80%) ✅
    - Mode: OFANSIF ✅
    - Symbol: MS PRK
    - Bid Buy Ucuzluk: 0.08 (> 0.06) ✅
    - Fbtot: 1.15 (> 1.10) ✅
    - Spread: 0.03 (< 0.05) ✅
    - AVG_ADV: 6000 (> 1000) ✅
    - No existing position ✅
    - No cooldown ✅
    
    Expected: BUY (200 lot)
    """
    available_symbols = ["MS PRK"]
    
    metrics = {
        "MS PRK": SymbolMetrics(
            symbol="MS PRK",
            bid_buy_ucuzluk=0.08,
            fbtot=1.15,
            spread=0.03,
            avg_adv=6000.0,
            bid=27.28,
            ask=27.32,
            last=27.30,
            timestamp=datetime.now()
        )
    }
    
    exposure = ExposureSnapshot(
        pot_total=30000.0,  # 47% of pot_max (< 80% threshold)
        pot_max=63636.0,
        long_lots=400.0,
        short_lots=0.0,
        net_exposure=400.0,
        timestamp=datetime.now()
    )
    
    request = DecisionRequest(
        positions=[],  # No existing positions
        metrics=metrics,
        exposure=exposure,
        available_symbols=available_symbols,
        cycle_count=1,
        snapshot_ts=datetime.now()
    )
    
    return ValidationTestCase(
        name="Test Case 2: Exposure Eligible - Perfect BUY",
        description="Symbol passes all filters - should BUY (200 lot)",
        input_request=request,
        expected_outcome={
            'eligible': True,
            'decisions_count': 1,
            'filtered_count': 0,
            'symbols': {
                'MS PRK': {
                    'action': 'BUY',
                    'reason': 'Bid Buy Ucuzluk',
                    'calculated_lot': 200
                }
            }
        },
        janall_behavior="BUY (200 lot, BID_BUY)",
        category="BUY"
    )


def create_test_fixture_3() -> ValidationTestCase:
    """
    Test Case 3: Exposure Eligible - ADD (Existing Position)
    
    Scenario:
    - Exposure eligible ✅
    - Symbol: BAC PRM
    - Existing position: 100 lots
    - Max lot per symbol: 200
    - Remaining capacity: 100 lots
    - All filters pass ✅
    
    Expected: ADD (100 lot - remaining capacity)
    """
    available_symbols = ["BAC PRM"]
    
    metrics = {
        "BAC PRM": SymbolMetrics(
            symbol="BAC PRM",
            bid_buy_ucuzluk=0.07,
            fbtot=1.12,
            spread=0.04,
            avg_adv=3000.0,
            bid=25.18,
            ask=25.22,
            last=25.20,
            timestamp=datetime.now()
        )
    }
    
    positions = [
        PositionSnapshot(
            symbol="BAC PRM",
            qty=100.0,  # Existing position
            avg_price=25.00,
            current_price=25.20,
            unrealized_pnl=20.0,
            group="heldff",
            cgrup=None,
            timestamp=datetime.now()
        )
    ]
    
    exposure = ExposureSnapshot(
        pot_total=30000.0,  # 47% of pot_max
        pot_max=63636.0,
        long_lots=100.0,
        short_lots=0.0,
        net_exposure=100.0,
        timestamp=datetime.now()
    )
    
    request = DecisionRequest(
        positions=positions,
        metrics=metrics,
        exposure=exposure,
        available_symbols=available_symbols,
        cycle_count=1,
        snapshot_ts=datetime.now()
    )
    
    return ValidationTestCase(
        name="Test Case 3: Exposure Eligible - ADD (Existing Position)",
        description="Symbol with existing position - should ADD (remaining capacity)",
        input_request=request,
        expected_outcome={
            'eligible': True,
            'decisions_count': 1,
            'filtered_count': 0,
            'symbols': {
                'BAC PRM': {
                    'action': 'ADD',
                    'reason': 'Bid Buy Ucuzluk',
                    'calculated_lot': 100  # Remaining capacity (200 - 100)
                }
            }
        },
        janall_behavior="ADD (100 lot, BID_BUY)",
        category="ADD"
    )


def create_test_fixture_4() -> ValidationTestCase:
    """
    Test Case 4: Symbol Filtered - Bid Buy Ucuzluk Too Low
    
    Scenario:
    - Exposure eligible ✅
    - Symbol: WFC PRY
    - Bid Buy Ucuzluk: 0.04 (< 0.06) ❌
    - Other filters pass ✅
    
    Expected: FILTERED (Bid Buy Ucuzluk <= 0.06)
    """
    available_symbols = ["WFC PRY"]
    
    metrics = {
        "WFC PRY": SymbolMetrics(
            symbol="WFC PRY",
            bid_buy_ucuzluk=0.04,  # < 0.06 ❌
            fbtot=1.18,
            spread=0.02,
            avg_adv=5000.0,
            bid=24.48,
            ask=24.52,
            last=24.50,
            timestamp=datetime.now()
        )
    }
    
    exposure = ExposureSnapshot(
        pot_total=30000.0,
        pot_max=63636.0,
        long_lots=400.0,
        short_lots=0.0,
        net_exposure=400.0,
        timestamp=datetime.now()
    )
    
    request = DecisionRequest(
        positions=[],
        metrics=metrics,
        exposure=exposure,
        available_symbols=available_symbols,
        cycle_count=1,
        snapshot_ts=datetime.now()
    )
    
    return ValidationTestCase(
        name="Test Case 4: Symbol Filtered - Bid Buy Ucuzluk Too Low",
        description="Bid Buy Ucuzluk < threshold - should be filtered",
        input_request=request,
        expected_outcome={
            'eligible': True,
            'decisions_count': 0,
            'filtered_count': 1,
            'symbols': {
                'WFC PRY': {
                    'action': 'FILTERED',
                    'filter_reasons': ['Bid Buy Ucuzluk']
                }
            }
        },
        janall_behavior="FILTERED (Bid Buy Ucuzluk <= 0.06)",
        category="FILTERED"
    )


# ============================================================================
# MAIN VALIDATION RUNNER
# ============================================================================

async def run_validation():
    """
    Run all validation test cases.
    
    Usage:
        python -m quant_engine.tests.test_addnewpos_validation
    """
    harness = AddnewposValidationHarness()
    
    # Add all test cases
    harness.add_test_case(create_test_fixture_1())
    harness.add_test_case(create_test_fixture_2())
    harness.add_test_case(create_test_fixture_3())
    harness.add_test_case(create_test_fixture_4())
    
    # Run all tests
    logger.info("Starting ADDNEWPOS v1 validation...")
    results = await harness.run_all_tests()
    
    # Generate report
    report = harness.generate_report()
    print(report)
    
    # Save report
    output_path = Path(__file__).parent / 'addnewpos_validation_report.txt'
    harness.save_report(output_path)
    
    # Summary
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    
    logger.info(f"Validation complete: {passed}/{total} tests passed")
    
    if passed < total:
        logger.warning(f"{total - passed} tests failed - check report for details")
        return False
    else:
        logger.info("All tests passed! ✅")
        return True


if __name__ == "__main__":
    print("=" * 80)
    print("ADDNEWPOS v1 VALIDATION - Starting...")
    print("=" * 80)
    print()
    
    try:
        success = asyncio.run(run_validation())
        
        if success:
            print("\n" + "=" * 80)
            print("[OK] VALIDATION COMPLETE - All tests passed!")
            print("=" * 80)
        else:
            print("\n" + "=" * 80)
            print("[FAIL] VALIDATION COMPLETE - Some tests failed. Check report for details.")
            print("=" * 80)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()




