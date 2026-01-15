#!/usr/bin/env python3
"""
Execution Service Entry Point

Run: python workers/run_execution_service.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.event_driven.execution.service import main

if __name__ == "__main__":
    main()



