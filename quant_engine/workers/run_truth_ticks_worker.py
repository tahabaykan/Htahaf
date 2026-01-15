"""
Run Truth Ticks Worker

Entry point script to run the Truth Ticks worker in a separate process.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.workers.truth_ticks_worker import main

if __name__ == "__main__":
    main()


