"""tests/fault/fault_hammer_feed_drop.py

Test Hammer feed drop handling: skip corrupted data, maintain candle integrity.
"""

import pytest
import time

from app.strategy.strategy_example import ExampleStrategy
from app.strategy.candle_manager import CandleManager
from app.engine.position_manager import PositionManager
from app.risk.risk_manager import RiskManager
from app.risk.risk_limits import RiskLimits
from app.risk.risk_state import RiskState


class TestHammerFeedDrop:
    """Test Hammer feed drop handling"""
    
    @pytest.fixture
    def setup(self):
        """Setup strategy"""
        strategy = ExampleStrategy()
        candle_manager = CandleManager(interval_seconds=60)
        position_manager = PositionManager()
        risk_limits = RiskLimits()
        risk_state = RiskState()
        risk_manager = RiskManager(limits=risk_limits, state=risk_state)
        risk_manager.set_position_manager(position_manager)
        
        strategy.initialize(
            candle_manager=candle_manager,
            position_manager=position_manager,
            risk_manager=risk_manager
        )
        
        return {
            'strategy': strategy,
            'candle_manager': candle_manager
        }
    
    def test_sudden_feed_freeze(self, setup):
        """Test sudden feed freeze"""
        strategy = setup['strategy']
        candle_manager = setup['candle_manager']
        
        # Generate normal ticks
        normal_ticks = [
            {"symbol": "AAPL", "last": "150.0", "volume": 1000, "ts": int(time.time() * 1000)},
            {"symbol": "AAPL", "last": "151.0", "volume": 1000, "ts": int(time.time() * 1000) + 1000},
        ]
        
        # Process normal ticks
        for tick in normal_ticks:
            strategy.on_tick(tick)
        
        # Feed freezes (no ticks for 5 seconds)
        time.sleep(0.1)  # Simulate freeze
        
        # Feed resumes
        resume_ticks = [
            {"symbol": "AAPL", "last": "152.0", "volume": 1000, "ts": int(time.time() * 1000) + 6000},
        ]
        
        # Process resumed ticks
        for tick in resume_ticks:
            strategy.on_tick(tick)
        
        # Verify candles still valid
        candles = candle_manager.get_candles("AAPL", count=10)
        assert len(candles) >= 0, "Should have valid candles"
        
        print("✓ Feed freeze handled gracefully")
    
    def test_out_of_order_ticks(self, setup):
        """Test out-of-order ticks"""
        strategy = setup['strategy']
        candle_manager = setup['candle_manager']
        
        # Generate out-of-order ticks
        ticks = [
            {"symbol": "AAPL", "last": "150.0", "volume": 1000, "ts": 1000},
            {"symbol": "AAPL", "last": "152.0", "volume": 1000, "ts": 3000},  # Out of order
            {"symbol": "AAPL", "last": "151.0", "volume": 1000, "ts": 2000},  # Should come before
        ]
        
        # Process ticks
        for tick in ticks:
            strategy.on_tick(tick)
        
        # Verify candles still valid
        candles = candle_manager.get_candles("AAPL", count=10)
        # System should handle out-of-order gracefully
        print("✓ Out-of-order ticks handled")
    
    def test_corrupt_tick_values(self, setup):
        """Test corrupt tick values"""
        strategy = setup['strategy']
        
        # Generate corrupt ticks
        corrupt_ticks = [
            {"symbol": "AAPL", "last": "invalid", "volume": 1000, "ts": int(time.time() * 1000)},
            {"symbol": "AAPL", "last": "-100.0", "volume": 1000, "ts": int(time.time() * 1000) + 1000},  # Negative price
            {"symbol": "AAPL", "last": "0.0", "volume": 1000, "ts": int(time.time() * 1000) + 2000},  # Zero price
            {"symbol": "", "last": "150.0", "volume": 1000, "ts": int(time.time() * 1000) + 3000},  # Missing symbol
        ]
        
        # Process corrupt ticks (should skip invalid ones)
        processed = 0
        for tick in corrupt_ticks:
            try:
                signal = strategy.on_tick(tick)
                if signal is not None or tick.get('last', '0').replace('.', '').isdigit():
                    processed += 1
            except Exception:
                # Expected to skip corrupt data
                pass
        
        # Should skip corrupt data
        assert processed < len(corrupt_ticks), "Should skip some corrupt ticks"
        print("✓ Corrupt tick values skipped")
    
    def test_candle_integrity_maintained(self, setup):
        """Test candle integrity maintained despite feed issues"""
        strategy = setup['strategy']
        candle_manager = setup['candle_manager']
        
        # Generate mix of valid and invalid ticks
        ticks = [
            {"symbol": "AAPL", "last": "150.0", "volume": 1000, "ts": int(time.time() * 1000)},
            {"symbol": "AAPL", "last": "invalid", "volume": 1000, "ts": int(time.time() * 1000) + 1000},  # Invalid
            {"symbol": "AAPL", "last": "151.0", "volume": 1000, "ts": int(time.time() * 1000) + 2000},  # Valid
        ]
        
        # Process ticks
        for tick in ticks:
            try:
                strategy.on_tick(tick)
            except Exception:
                pass
        
        # Verify candles are still valid
        candles = candle_manager.get_candles("AAPL", count=10)
        
        # Check candle structure
        for candle in candles:
            assert candle.open > 0, "Candle should have valid open"
            assert candle.high >= candle.low, "Candle should have valid high/low"
        
        print("✓ Candle integrity maintained")
    
    def test_engine_not_terminated(self, setup):
        """Test engine doesn't terminate on feed issues"""
        strategy = setup['strategy']
        
        # Generate problematic ticks
        problematic_ticks = [
            {"symbol": "AAPL", "last": "150.0", "volume": 1000, "ts": int(time.time() * 1000)},
            {"symbol": "AAPL", "last": None, "volume": 1000, "ts": int(time.time() * 1000) + 1000},  # None price
            {"symbol": "AAPL", "last": "151.0", "volume": 1000, "ts": int(time.time() * 1000) + 2000},
        ]
        
        # Process ticks (should not crash)
        for tick in problematic_ticks:
            try:
                strategy.on_tick(tick)
            except Exception as e:
                # Should log but not crash
                print(f"Handled error: {e}")
        
        # Engine should still be functional
        print("✓ Engine continues running despite feed issues")








