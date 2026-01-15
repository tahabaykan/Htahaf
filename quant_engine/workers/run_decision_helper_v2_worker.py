"""
Run DecisionHelperV2 Worker

Entry point script to run the DecisionHelperV2 worker in a separate process.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.workers.decision_helper_v2_worker import main

if __name__ == "__main__":
    main()
