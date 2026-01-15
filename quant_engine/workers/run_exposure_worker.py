#!/usr/bin/env python3
"""
Exposure Worker Entry Point

Run: python workers/run_exposure_worker.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.event_driven.workers.exposure_worker import main

if __name__ == "__main__":
    main()



