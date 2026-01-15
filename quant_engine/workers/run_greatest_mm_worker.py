"""
Greatest MM Worker Runner
=========================

Terminal 9: Start Greatest MM Quant Worker

Usage:
    python workers/run_greatest_mm_worker.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.workers.greatest_mm_worker import main

if __name__ == "__main__":
    print("🎯 Starting Greatest MM Quant Worker (Terminal 9)...")
    print("Press Ctrl+C to stop")
    print()
    main()
