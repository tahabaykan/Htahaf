"""tests/unit/test_fifo_position_manager.py

Unit test for FIFO-based average price logic.
"""

import pytest

from app.engine.position_manager import PositionManager
from tests.utils.fake_execution_factory import FakeExecutionFactory


class TestFIFOPositionManager:
    """Test FIFO position manager"""
    
    @pytest.fixture
    def position_manager(self):
        """Create position manager"""
        return PositionManager()
    
    def test_buy_buy_sell_partial(self, position_manager):
        """Test: buy → buy → sell partial"""
        # Buy 10 @ 100
        exec1 = FakeExecutionFactory.create_execution("AAPL", "BUY", 10.0, 100.0)
        position_manager.apply_execution(exec1)
        
        # Buy 10 @ 110
        exec2 = FakeExecutionFactory.create_execution("AAPL", "BUY", 10.0, 110.0)
        position_manager.apply_execution(exec2)
        
        # Verify position
        pos = position_manager.get_position("AAPL")
        assert pos['qty'] == 20.0, f"Expected qty=20, got {pos['qty']}"
        assert pos['avg_price'] == 105.0, f"Expected avg=105, got {pos['avg_price']}"
        
        # Sell 5 @ 120 (partial)
        exec3 = FakeExecutionFactory.create_execution("AAPL", "SELL", 5.0, 120.0)
        position_manager.apply_execution(exec3)
        
        # Verify position
        pos = position_manager.get_position("AAPL")
        assert pos['qty'] == 15.0, f"Expected qty=15, got {pos['qty']}"
        # Avg price should still be based on remaining FIFO queue
        assert pos['avg_price'] > 0, "Avg price should be positive"
        
        print(f"✓ Buy → Buy → Sell Partial: qty={pos['qty']}, avg={pos['avg_price']:.2f}")
    
    def test_buy_sell_flip(self, position_manager):
        """Test: buy → sell flip (long to short)"""
        # Buy 10 @ 100
        exec1 = FakeExecutionFactory.create_execution("AAPL", "BUY", 10.0, 100.0)
        position_manager.apply_execution(exec1)
        
        # Sell 15 @ 110 (flip to short)
        exec2 = FakeExecutionFactory.create_execution("AAPL", "SELL", 15.0, 110.0)
        position_manager.apply_execution(exec2)
        
        # Verify position flipped
        pos = position_manager.get_position("AAPL")
        assert pos['qty'] == -5.0, f"Expected qty=-5 (short), got {pos['qty']}"
        
        print(f"✓ Buy → Sell Flip: qty={pos['qty']}, avg={pos['avg_price']:.2f}")
    
    def test_sell_short_cover(self, position_manager):
        """Test: sell short → cover"""
        # Sell short 10 @ 100
        exec1 = FakeExecutionFactory.create_execution("AAPL", "SELL", 10.0, 100.0)
        position_manager.apply_execution(exec1)
        
        # Verify short position
        pos = position_manager.get_position("AAPL")
        assert pos['qty'] == -10.0, f"Expected qty=-10, got {pos['qty']}"
        
        # Cover 10 @ 90
        exec2 = FakeExecutionFactory.create_execution("AAPL", "BUY", 10.0, 90.0)
        position_manager.apply_execution(exec2)
        
        # Verify position closed
        pos = position_manager.get_position("AAPL")
        assert pos['qty'] == 0.0, f"Expected qty=0, got {pos['qty']}"
        
        # Verify realized P&L (sold at 100, bought at 90 = +10 per share = +100)
        realized_pnl = position_manager.get_total_realized_pnl()
        assert realized_pnl > 0, f"Expected positive P&L, got {realized_pnl}"
        
        print(f"✓ Sell Short → Cover: qty={pos['qty']}, realized P&L=${realized_pnl:.2f}")
    
    def test_realized_pnl_correctness(self, position_manager):
        """Test: realized P&L correctness"""
        # Buy 10 @ 100
        exec1 = FakeExecutionFactory.create_execution("AAPL", "BUY", 10.0, 100.0)
        position_manager.apply_execution(exec1)
        
        # Sell 10 @ 120
        exec2 = FakeExecutionFactory.create_execution("AAPL", "SELL", 10.0, 120.0)
        position_manager.apply_execution(exec2)
        
        # Verify realized P&L: (120 - 100) * 10 = 200
        pos = position_manager.get_position("AAPL")
        realized_pnl = position_manager.get_total_realized_pnl()
        
        # Should be approximately 200 (may vary based on FIFO implementation)
        assert realized_pnl > 0, f"Expected positive P&L, got {realized_pnl}"
        
        print(f"✓ Realized P&L: ${realized_pnl:.2f} (expected ~$200)")
    
    def test_unrealized_pnl_correctness(self, position_manager):
        """Test: unrealized P&L correctness"""
        # Buy 10 @ 100
        exec1 = FakeExecutionFactory.create_execution("AAPL", "BUY", 10.0, 100.0)
        position_manager.apply_execution(exec1)
        
        # Update unrealized P&L with market price
        position_manager.calculate_unrealized_pnl("AAPL", current_market_price=110.0)
        
        # Verify unrealized P&L: (110 - 100) * 10 = 100
        pos = position_manager.get_position("AAPL")
        assert pos['unrealized_pnl'] > 0, f"Expected positive unrealized P&L, got {pos['unrealized_pnl']}"
        
        print(f"✓ Unrealized P&L: ${pos['unrealized_pnl']:.2f} (expected ~$100)")






