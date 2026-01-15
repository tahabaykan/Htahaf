#!/usr/bin/env python3
"""
PnL & LiquidityGuard Test Runner

Runs test scenarios for:
- Intraday PnL calculation (using intraday_avg_fill_price only)
- LiquidityGuard sizing constraints

Usage:
    python workers/run_pnl_liquidity_tests.py
"""

import os
import sys
from pathlib import Path

# Add quant_engine directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.event_driven.testing.pnl_liquidity_tests import main

if __name__ == "__main__":
    main()



