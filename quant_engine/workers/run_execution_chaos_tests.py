#!/usr/bin/env python3
"""
Execution Chaos Test Runner

Runs adversarial testing scenarios for Execution Service.

Usage:
    python workers/run_execution_chaos_tests.py
"""

import os
import sys
from pathlib import Path

# Add quant_engine directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.event_driven.testing.execution_chaos_tests import main

if __name__ == "__main__":
    main()



