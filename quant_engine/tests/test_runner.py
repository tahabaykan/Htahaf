"""tests/test_runner.py

Unified test runner for all test suites.
"""

import sys
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional


class TestRunner:
    """Unified test runner"""
    
    def __init__(self):
        self.test_dir = Path(__file__).parent
        self.results: List[Dict[str, Any]] = []
    
    def run_unit_tests(self) -> bool:
        """Run unit tests"""
        print("\n" + "="*60)
        print("RUNNING UNIT TESTS")
        print("="*60)
        
        unit_dir = self.test_dir / "unit"
        return self._run_pytest(unit_dir, "unit")
    
    def run_integration_tests(self) -> bool:
        """Run integration tests"""
        print("\n" + "="*60)
        print("RUNNING INTEGRATION TESTS")
        print("="*60)
        
        integration_dir = self.test_dir / "integration"
        return self._run_pytest(integration_dir, "integration")
    
    def run_load_tests(self) -> bool:
        """Run load/stress tests"""
        print("\n" + "="*60)
        print("RUNNING LOAD/STRESS TESTS")
        print("="*60)
        
        load_dir = self.test_dir / "load"
        return self._run_pytest(load_dir, "load")
    
    def run_fault_tests(self) -> bool:
        """Run fault tolerance tests"""
        print("\n" + "="*60)
        print("RUNNING FAULT TOLERANCE TESTS")
        print("="*60)
        
        fault_dir = self.test_dir / "fault"
        return self._run_pytest(fault_dir, "fault")
    
    def _run_pytest(self, test_dir: Path, suite_name: str) -> bool:
        """Run pytest on test directory"""
        if not test_dir.exists():
            print(f"⚠ Test directory not found: {test_dir}")
            return False
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_dir), "-v"],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            elapsed = time.time() - start_time
            
            # Parse results
            passed = result.returncode == 0
            output = result.stdout + result.stderr
            
            # Count tests
            test_count = output.count("PASSED") + output.count("FAILED")
            
            self.results.append({
                'suite': suite_name,
                'passed': passed,
                'elapsed': elapsed,
                'test_count': test_count,
                'output': output
            })
            
            print(output)
            print(f"\n✓ {suite_name} tests completed in {elapsed:.2f}s")
            
            return passed
        
        except subprocess.TimeoutExpired:
            print(f"❌ {suite_name} tests timed out")
            return False
        except Exception as e:
            print(f"❌ Error running {suite_name} tests: {e}")
            return False
    
    def run_all_tests(self) -> bool:
        """Run all test suites"""
        print("\n" + "="*60)
        print("RUNNING ALL TESTS")
        print("="*60)
        
        all_passed = True
        
        # Run test suites
        all_passed &= self.run_unit_tests()
        all_passed &= self.run_integration_tests()
        all_passed &= self.run_load_tests()
        all_passed &= self.run_fault_tests()
        
        return all_passed
    
    def print_summary(self):
        """Print test summary table"""
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"{'Suite':<20} {'Status':<10} {'Tests':<10} {'Time':<10}")
        print("-"*60)
        
        total_tests = 0
        total_time = 0
        
        for result in self.results:
            status = "✅ PASS" if result['passed'] else "❌ FAIL"
            tests = result.get('test_count', 0)
            elapsed = result.get('elapsed', 0)
            
            print(f"{result['suite']:<20} {status:<10} {tests:<10} {elapsed:.2f}s")
            
            total_tests += tests
            total_time += elapsed
        
        print("-"*60)
        print(f"{'TOTAL':<20} {'':<10} {total_tests:<10} {total_time:.2f}s")
        print("="*60)
        
        # Overall status
        all_passed = all(r['passed'] for r in self.results)
        if all_passed:
            print("\n✅ ALL TESTS PASSED")
        else:
            print("\n❌ SOME TESTS FAILED")
        
        return all_passed


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test runner for quant_engine")
    parser.add_argument(
        '--all',
        action='store_true',
        help='Run all test suites'
    )
    parser.add_argument(
        '--unit',
        action='store_true',
        help='Run unit tests'
    )
    parser.add_argument(
        '--integration',
        action='store_true',
        help='Run integration tests'
    )
    parser.add_argument(
        '--load',
        action='store_true',
        help='Run load/stress tests'
    )
    parser.add_argument(
        '--fault',
        action='store_true',
        help='Run fault tolerance tests'
    )
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    if args.all or (not args.unit and not args.integration and not args.load and not args.fault):
        # Run all if no specific suite specified
        all_passed = runner.run_all_tests()
    else:
        all_passed = True
        
        if args.unit:
            all_passed &= runner.run_unit_tests()
        
        if args.integration:
            all_passed &= runner.run_integration_tests()
        
        if args.load:
            all_passed &= runner.run_load_tests()
        
        if args.fault:
            all_passed &= runner.run_fault_tests()
    
    # Print summary
    runner.print_summary()
    
    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()






