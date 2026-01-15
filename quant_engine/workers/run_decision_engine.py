#!/usr/bin/env python3
"""
Decision Engine Entry Point

Run: python workers/run_decision_engine.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.event_driven.decision_engine.engine import main

if __name__ == "__main__":
    main()



