"""
Greatest MM Worker Runner
=========================

Terminal 9: Start Greatest MM Quant Worker

Usage:
    python workers/run_greatest_mm_worker.py
"""

import sys
import os

# ═══════════════════════════════════════════════════════════════════════
# FIX: Force UTF-8 encoding on Windows to prevent UnicodeEncodeError
# Windows CP1254 (Turkish) encoding cannot handle emoji characters
# (🎯, 🚀, ✅, 📊, etc.) used in logger messages throughout the worker.
# This MUST be done BEFORE any print/logger calls.
# ═══════════════════════════════════════════════════════════════════════
if sys.platform == 'win32':
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, Exception):
        # Python < 3.7 or already redirected — wrap with io.TextIOWrapper
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.workers.greatest_mm_worker import main

if __name__ == "__main__":
    print("🎯 Starting Greatest MM Quant Worker (Terminal 9)...")
    print("Press Ctrl+C to stop")
    print()
    main()
