#!/usr/bin/env python3
"""
Ledger Consumer Entry Point

Consumes order events and updates daily ledger.

Run: python workers/run_ledger_consumer.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.event_driven.reporting.daily_ledger import LedgerConsumer

def main():
    """Main entry point"""
    consumer = LedgerConsumer()
    
    import signal
    def signal_handler(sig, frame):
        from app.core.logger import logger
        logger.info(f"🛑 [{consumer.worker_name}] Received SIGINT, shutting down...")
        consumer.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    consumer.run()


if __name__ == "__main__":
    main()



