#!/usr/bin/env python3
"""
BefDay Snapshot Worker

Creates daily baseline snapshot for an account.
Ensures once-per-day behavior (idempotent).

Usage:
    python workers/run_befday_snapshot.py [account_id]

Account IDs: HAMMER, IBKR_GUN, IBKR_PED
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.event_driven.baseline.befday_snapshot import BefDaySnapshot
from app.core.logger import logger
from datetime import date


def main():
    """Main entry point"""
    # Get account ID from command line or default to HAMMER
    account_id = sys.argv[1] if len(sys.argv) > 1 else "HAMMER"
    
    valid_accounts = [BefDaySnapshot.ACCOUNT_HAMMER, 
                     BefDaySnapshot.ACCOUNT_IBKR_GUN,
                     BefDaySnapshot.ACCOUNT_IBKR_PED]
    
    if account_id not in valid_accounts:
        logger.error(f"❌ Invalid account_id: {account_id}")
        logger.info(f"Valid accounts: {', '.join(valid_accounts)}")
        sys.exit(1)
    
    snapshot = BefDaySnapshot()
    snapshot_date = date.today()
    
    # Check if snapshot already exists
    if snapshot.has_snapshot_today(account_id, snapshot_date):
        logger.info(
            f"⏭️ Snapshot already exists for {account_id} on {snapshot_date}. "
            f"Use --force to recreate."
        )
        existing = snapshot.load_snapshot(account_id, snapshot_date)
        if existing:
            logger.info(f"📊 Existing snapshot: {existing.get('total_symbols', 0)} symbols")
        return
    
    # Create snapshot
    try:
        snapshot_data = snapshot.create_snapshot(account_id, snapshot_date, force=False)
        logger.info(
            f"✅ BefDay snapshot created for {account_id}: "
            f"{snapshot_data.get('total_symbols', 0)} symbols"
        )
    except Exception as e:
        logger.error(f"❌ Error creating snapshot: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()



