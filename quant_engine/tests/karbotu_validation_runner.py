"""
KARBOTU Validation Runner - Standalone Script

Run validation tests and generate report.

Usage:
    python -m quant_engine.tests.karbotu_validation_runner
    python quant_engine/tests/karbotu_validation_runner.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from quant_engine.tests.test_karbotu_validation import (
    run_validation,
    KarbotuValidationHarness,
    create_test_fixture_1,
    create_test_fixture_2,
    create_test_fixture_3,
    create_test_fixture_4,
    create_test_fixture_5,
    create_test_fixture_6,
    create_test_fixture_7,
    create_test_fixture_8
)


async def main():
    """Main entry point"""
    print("=" * 80)
    print("KARBOTU v1 VALIDATION RUNNER")
    print("=" * 80)
    print()
    
    success = await run_validation()
    
    if success:
        print("\n[OK] All validation tests passed!")
        return 0
    else:
        print("\n[FAIL] Some validation tests failed. Check report for details.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

