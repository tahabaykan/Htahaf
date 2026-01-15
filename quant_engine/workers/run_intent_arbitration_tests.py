#!/usr/bin/env python3
"""
Intent Arbitration Test Runner

Runs test scenarios for IntentArbiter conflict resolution.

Usage:
    python workers/run_intent_arbitration_tests.py
"""

import os
import sys
from pathlib import Path

# Add quant_engine directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.event_driven.testing.intent_arbitration_tests import main

if __name__ == "__main__":
    main()



