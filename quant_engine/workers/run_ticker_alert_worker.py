#!/usr/bin/env python3
"""
Run Ticker Alert Worker

Entry point for running the ticker alert worker in a separate process.
"""

import sys
import os

# Add quant_engine to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.workers.ticker_alert_worker import main

if __name__ == "__main__":
    main()


