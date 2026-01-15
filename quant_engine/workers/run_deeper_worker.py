"""
Standalone script to run the deeper analysis worker.

Usage:
    python workers/run_deeper_worker.py
    
    Or with environment variables:
    WORKER_NAME=worker1 python workers/run_deeper_worker.py
"""

import os
import sys

# Add quant_engine to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.workers.deeper_analysis_worker import main

if __name__ == "__main__":
    main()


