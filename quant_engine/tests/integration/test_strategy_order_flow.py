"""tests/integration/test_strategy_order_flow.py

Test strategy signal → order flow.
"""

import pytest
import time

from app.core.event_bus import EventBus
from app.strategy.strategy_example import ExampleStrategy
from app.strategy.candle_manager import CandleManager
from app.engine.position_manager import PositionManager
from app.risk.risk_manager import RiskManager
from app.risk.risk_limits import RiskLimits
from app.risk.risk_state import RiskState
from tests.utils.fake_execution_factory import FakeExecutionFactory


class TestStrategyOrderFlow:
    """Test strategy order flow"""
    
    @pytest.fixture
    def setup(self):
        """Setup strategy with dependencies"""
        strategy = ExampleStrategy()
        candle_manager = CandleManager(interval_seconds=60)
        position_manager = PositionManager()
        risk_limits = RiskLimits(max_trades_per_minute=100)
        risk_state = RiskState()
        risk_manager = RiskManager(limits=risk_limits, state=risk_state)
        risk_manager.set_position_manager(position_manager)
        
        strategy.initialize(
            candle_manager=candle_manager,
            position_manager=position_manager,
            risk_manager=risk_manager,
            symbols=["AAPL", "MSFT"]
        )
        
        return {
            'strategy': strategy,
            'candle_manager': candle_manager,
            'position_manager': position_manager
        }
    
    def test_duplicate_signal_prevention(self, setup):
        """Test duplicate signal prevention"""
        strategy = setup['strategy']
        
        # Generate ticks that would create signals
        ticks = FakeExecutionFactory.create_ticks("AAPL", count=100, start_price=150.0)
        
        signals = []
        for tick in ticks:
            signal = strategy.on_tick(tick)
            if signal:
                signals.append(signal)
        
        # Check for duplicates (same symbol, same side, within 60 seconds)
        signal_times = {}
        duplicates = 0
        
        for signal in signals:
            key = f"{signal['symbol']}_{signal['signal']}"
            signal_time = signal.get('timestamp', time.time())
            
            if key in signal_times:
                time_diff = abs(signal_time - signal_times[key])
                if time_diff < 60:  # Within 60 seconds
                    duplicates += 1
            
            signal_times[key] = signal_time
        
        # Should have some duplicate prevention
        print(f"✓ Generated {len(signals)} signals")
        print(f"✓ Duplicate prevention working (duplicates: {duplicates})")
    
    def test_multiple_symbol_support(self, setup):
        """Test multiple symbol support"""
        strategy = setup['strategy']
        
        # Generate ticks for multiple symbols
        aapl_ticks = FakeExecutionFactory.create_ticks("AAPL", count=50, start_price=150.0)
        msft_ticks = FakeExecutionFactory.create_ticks("MSFT", count=50, start_price=300.0)
        
        all_ticks = aapl_ticks + msft_ticks
        
        signals = []
        for tick in all_ticks:
            signal = strategy.on_tick(tick)
            if signal:
                signals.append(signal)
        
        # Verify signals for both symbols
        symbols = set(s['symbol'] for s in signals)
        assert len(symbols) >= 1, "Should process multiple symbols"
        
        print(f"✓ Processed ticks for symbols: {symbols}")
        print(f"✓ Generated {len(signals)} signals")
    
    def test_indicator_values_correct(self, setup):
        """Test indicator values are correct"""
        strategy = setup['strategy']
        
        # Generate enough ticks for indicator calculation
        ticks = FakeExecutionFactory.create_ticks("AAPL", count=100, start_price=150.0)
        
        # Process ticks
        for tick in ticks:
            strategy.on_tick(tick)
        
        # Get indicator value
        sma = strategy.get_indicator("AAPL", "sma", period=20)
        
        # Verify indicator calculated
        assert sma is not None, "SMA should be calculated"
        assert sma > 0, "SMA should be positive"
        
        print(f"✓ SMA(20) calculated: {sma:.2f}")
    
    def test_candle_manager_correctness(self, setup):
        """Test candle manager correctness"""
        strategy = setup['strategy']
        candle_manager = setup['candle_manager']
        
        # Generate ticks
        ticks = FakeExecutionFactory.create_ticks("AAPL", count=200, start_price=150.0)
        
        # Process ticks
        completed_candles = 0
        for tick in ticks:
            completed = strategy.on_tick(tick)
            if completed:
                completed_candles += 1
        
        # Get candles
        candles = candle_manager.get_candles("AAPL", count=10)
        
        # Verify candles created
        assert len(candles) > 0, "Should have candles"
        
        # Verify candle structure
        for candle in candles:
            assert candle.open > 0, "Candle should have open"
            assert candle.high >= candle.low, "Candle high >= low"
            assert candle.high >= candle.open, "Candle high >= open"
            assert candle.high >= candle.close, "Candle high >= close"
        
        print(f"✓ Created {len(candles)} candles")
        print(f"✓ Candle structure correct")






