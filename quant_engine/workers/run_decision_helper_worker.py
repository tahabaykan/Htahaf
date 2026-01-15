"""
Entry point for Decision Helper Worker

Run this script to start the Decision Helper worker process.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.workers.decision_helper_worker import main

if __name__ == "__main__":
    main()


