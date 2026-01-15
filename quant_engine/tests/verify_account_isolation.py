
import asyncio
import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.logger import logger
from app.psfalgo.decision_models import PositionSnapshot
from app.psfalgo.position_snapshot_api import PositionSnapshotAPI

import logging

# Configure logger
logger.remove()
def custom_sink(message):
    sys.stdout.write(str(message))
    sys.stdout.flush()
logger.add(custom_sink, level="DEBUG", format="{message}")

async def run_strict_isolation_test():
    print("\n[TEST] Starting Account Isolation Verification...")
    
    # Mock dependencies
    mock_position_manager = MagicMock()
    mock_position_manager.get_positions.return_value = [
        {'symbol': 'HMR1', 'quantity': 100, 'avg_price': 10, 'account_type': 'HAMMER_PRO'}
    ]
    
    api = PositionSnapshotAPI(position_manager=mock_position_manager)
    
    # Mock IBKR positions
    async def mock_ibkr_positions(symbols, target_account_type=None):
        print(f"[MOCK] Fetching IBKR for target: {target_account_type}")
        if target_account_type == "IBKR_GUN":
            return [{'symbol': 'GUN1', 'qty': 50, 'avg_price': 20, 'account_type': 'IBKR_GUN'}]
        elif target_account_type == "IBKR_PED":
            return [{'symbol': 'PED1', 'qty': 30, 'avg_price': 30, 'account_type': 'IBKR_PED'}]
        return []

    # Mock enrich
    async def mock_enrich(pos_data, symbol):
        return PositionSnapshot(
            symbol=symbol, qty=pos_data.get('qty') or pos_data.get('quantity'), 
            avg_price=pos_data.get('avg_price'), current_price=10.0, unrealized_pnl=0,
            account_type=pos_data.get('account_type')
        )

    api._get_ibkr_positions = mock_ibkr_positions
    api._enrich_position = mock_enrich
    
    # Test Case 1: Active Mode = HAMMER
    print("\n--- TEST CASE 1: HAMMER Active ---")
    with patch('app.psfalgo.account_mode.get_account_mode_manager') as mock_get_manager:
        mock_manager = MagicMock()
        mock_manager.is_ibkr.return_value = False
        mock_manager.get_account_type.return_value = "HAMMER_PRO"
        mock_get_manager.return_value = mock_manager
        
        snapshots = await api.get_position_snapshot()
        print(f"Result count: {len(snapshots)}")
        for s in snapshots:
            print(f"  - {s.symbol} ({s.account_type})")

    # Test Case 2: Active Mode = IBKR_GUN
    print("\n--- TEST CASE 2: IBKR_GUN Active ---")
    with patch('app.psfalgo.account_mode.get_account_mode_manager') as mock_get_manager:
        mock_manager = MagicMock()
        mock_manager.is_ibkr.return_value = True
        mock_manager.get_account_type.return_value = "IBKR_GUN"
        mock_get_manager.return_value = mock_manager
        
        snapshots = await api.get_position_snapshot()
        print(f"Result count: {len(snapshots)}")
        for s in snapshots:
            print(f"  - {s.symbol} ({s.account_type})")
            
    # Test Case 3: Active Mode = IBKR_PED
    print("\n--- TEST CASE 3: IBKR_PED Active ---")
    with patch('app.psfalgo.account_mode.get_account_mode_manager') as mock_get_manager:
        mock_manager = MagicMock()
        mock_manager.is_ibkr.return_value = True
        mock_manager.get_account_type.return_value = "IBKR_PED"
        mock_get_manager.return_value = mock_manager
        
        snapshots = await api.get_position_snapshot()
        print(f"Result count: {len(snapshots)}")
        for s in snapshots:
            print(f"  - {s.symbol} ({s.account_type})")

if __name__ == "__main__":
    asyncio.run(run_strict_isolation_test())
