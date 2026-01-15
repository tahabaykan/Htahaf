
"""
Verification Script for Multi-Broker Architecture
Tests:
1. Safe Mode Switching (HAMPRO -> IBKR_PED)
2. Orphan Logic (Old orders marked ORPHANED)
3. Position Ledger Split (LT/MM buckets)
"""

import sys
import os
import unittest
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.logger import logger
from app.trading.trading_account_context import get_trading_context, TradingAccountMode
from app.execution.execution_router import ExecutionRouter, ExecutionMode
from app.psfalgo.order_manager import initialize_order_controller, get_order_controller, TrackedOrder, OrderStatus
from app.engine.position_manager import PositionManager
from app.execution.providers import HammerExecutionProvider, IBKRExecutionProvider

# Configure Logger to stdout
logging.basicConfig(level=logging.INFO)

class TestMultiBroker(unittest.TestCase):
    
    def setUp(self):
        # Initialize components
        self.controller = initialize_order_controller({'enabled': True})
        self.context = get_trading_context()
        self.router = ExecutionRouter(ExecutionMode.SEMI_AUTO)
        self.position_mgr = PositionManager()
        
        # Reset Context
        self.context.set_trading_mode(TradingAccountMode.HAMPRO)
        self.context.set_hammer_connected(True)
        self.context.set_ibkr_paper_connected(True) # Mock connection
        
    def test_safe_mode_switching(self):
        print("\n=== TEST: Safe Mode Switching ===")
        
        # 1. Create a "HAMPRO" order
        order1 = TrackedOrder(
            order_id="HAM_101",
            symbol="TEST_SYM",
            action="BUY",
            order_type="BID_BUY",
            lot_qty=100,
            price=10.50,
            provider="HAMPRO",
            book="LT"
        )
        self.controller.track_order(order1)
        print(f"Created Active Order: {order1.order_id} (Provider: {order1.provider})")
        
        # Verify it's active
        self.assertTrue(order1.is_active)
        self.assertEqual(order1.provider, "HAMPRO")
        
        # 2. Switch Mode to IBKR_PED
        print(f"Switching Mode to {TradingAccountMode.IBKR_PED}...")
        self.router.switch_account_mode(TradingAccountMode.IBKR_PED)
        
        # 3. Verify Switch
        self.assertEqual(self.context.trading_mode, TradingAccountMode.IBKR_PED)
        self.assertIsInstance(self.context.execution_provider, IBKRExecutionProvider)
        print("Mode Switched Successfully.")
        
        # 4. Verify Orphan Logic
        # Order1 should be ORPHANED (status=ORPHANED, orphaned_provider=True)
        # Note: TrackedOrder object is same, so we check reference
        self.assertEqual(order1.status, OrderStatus.ORPHANED)
        self.assertTrue(order1.orphaned_provider)
        self.assertFalse(order1.is_active) # Should be false now
        print(f"Verified Orphan: {order1.order_id} Status={order1.status} Orphaned={order1.orphaned_provider}")
        
    def test_position_ledger_split(self):
        print("\n=== TEST: Position Ledger Split (LT/MM) ===")
        
        symbol = "TEST_POS"
        
        # 1. Apply LT Fill
        print("Applying LT Fill: +100 @ $10.00")
        self.position_mgr.apply_execution({
            "symbol": symbol,
            "qty": 100,
            "price": 10.00,
            "side": "BUY",
            "book": "LT"
        })
        
        pos = self.position_mgr.get_position(symbol)
        self.assertEqual(pos['lt_qty'], 100)
        self.assertEqual(pos['mm_qty'], 0)
        self.assertEqual(pos['qty'], 100)
        print(f"Pos State (LT Fill): {pos}")
        
        # 2. Apply MM Fill
        print("Applying MM Fill: +50 @ $11.00")
        self.position_mgr.apply_execution({
            "symbol": symbol,
            "qty": 50,
            "price": 11.00,
            "side": "BUY",
            "book": "MM"
        })
        
        pos = self.position_mgr.get_position(symbol)
        self.assertEqual(pos['lt_qty'], 100)
        self.assertEqual(pos['mm_qty'], 50)
        self.assertEqual(pos['qty'], 150) # Net 150
        
        # Verify Avg Price (Weighted)
        # (100*10 + 50*11) / 150 = (1000 + 550) / 150 = 1550 / 150 = 10.333
        expected_avg = 1550 / 150
        self.assertAlmostEqual(pos['avg_price'], expected_avg, places=2)
        print(f"Pos State (MM Fill): {pos}")
        
        # 3. Reduce MM Only
        print("Applying MM Sell: -50 @ $12.00")
        self.position_mgr.apply_execution({
            "symbol": symbol,
            "qty": 50,
            "price": 12.00,
            "side": "SELL",
            "book": "MM"
        })
        
        pos = self.position_mgr.get_position(symbol)
        self.assertEqual(pos['lt_qty'], 100) # Unchanged
        self.assertEqual(pos['mm_qty'], 0)   # Back to 0
        self.assertEqual(pos['qty'], 100)
        print(f"Pos State (MM Reduce): {pos}")

if __name__ == '__main__':
    unittest.main()
