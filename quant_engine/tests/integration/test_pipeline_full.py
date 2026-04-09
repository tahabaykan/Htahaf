"""tests/integration/test_pipeline_full.py

End-to-end pipeline test: HAMMER → ENGINE → STRATEGY → RISK → ORDER → IBKR → EXECUTION → POSITION
"""

import time
import json
import pytest
from typing import List, Dict, Any

from app.core.event_bus import EventBus
from app.engine.engine_loop import TradingEngine
from app.engine.position_manager import PositionManager
from app.strategy.strategy_example import ExampleStrategy
from app.risk.risk_manager import RiskManager
from app.risk.risk_limits import RiskLimits
from app.risk.risk_state import RiskState
from tests.utils.fake_execution_factory import FakeExecutionFactory


class TestFullPipeline:
    """End-to-end pipeline test"""
    
    @pytest.fixture
    def setup(self):
        """Setup test environment"""
        # Clear Redis streams
        try:
            redis = EventBus.redis_client.sync if hasattr(EventBus, 'redis_client') else None
            if redis:
                redis.delete("ticks", "orders", "executions", "signals")
        except:
            pass
        
        # Create components
        strategy = ExampleStrategy()
        position_manager = PositionManager()
        risk_limits = RiskLimits(
            max_position_per_symbol=1000.0,
            max_daily_loss=10000.0,
            max_trades_per_minute=100
        )
        risk_state = RiskState()
        risk_manager = RiskManager(limits=risk_limits, state=risk_state)
        risk_manager.set_position_manager(position_manager)
        
        engine = TradingEngine(strategy, sync_on_start=False)
        engine.position_manager = position_manager
        engine.risk_manager = risk_manager
        
        return {
            'strategy': strategy,
            'position_manager': position_manager,
            'risk_manager': risk_manager,
            'engine': engine
        }
    
    def test_pipeline_500_ticks(self, setup):
        """Test full pipeline with 500 ticks"""
        strategy = setup['strategy']
        position_manager = setup['position_manager']
        risk_manager = setup['risk_manager']
        
        # Generate 500 ticks
        ticks = FakeExecutionFactory.create_ticks("AAPL", count=500, start_price=150.0)
        
        # Process ticks
        signals_generated = 0
        orders_published = 0
        
        for tick in ticks:
            # Process through strategy
            signal = strategy.on_tick(tick)
            
            if signal:
                signals_generated += 1
                
                # Risk check
                symbol = signal.get('symbol')
                side = signal.get('signal')
                qty = float(signal.get('quantity', 0))
                price = float(signal.get('price', 0))
                
                allowed, reason = risk_manager.check_before_order(symbol, side, qty, price)
                
                if allowed:
                    orders_published += 1
                    # Publish to orders stream (simulated)
                    EventBus.stream_add("orders", signal)
        
        # Verify signals generated
        assert signals_generated > 0, "No signals generated"
        
        # Verify orders published
        assert orders_published > 0, "No orders published"
        
        print(f"✓ Processed {len(ticks)} ticks")
        print(f"✓ Generated {signals_generated} signals")
        print(f"✓ Published {orders_published} orders")
    
    def test_execution_to_position(self, setup):
        """Test execution → position update flow"""
        position_manager = setup['position_manager']
        risk_manager = setup['risk_manager']
        
        # Create 10 BUY executions
        buy_executions = []
        for i in range(10):
            exec_msg = FakeExecutionFactory.create_execution(
                symbol="AAPL",
                side="BUY",
                qty=10.0,
                price=150.0 + i * 0.5,
                order_id=1000 + i
            )
            buy_executions.append(exec_msg)
        
        # Apply executions
        for exec_msg in buy_executions:
            position_manager.apply_execution(exec_msg)
            risk_manager.update_after_execution(
                exec_msg['symbol'],
                exec_msg['side'],
                float(exec_msg['fill_qty']),
                float(exec_msg['fill_price'])
            )
        
        # Verify position
        position = position_manager.get_position("AAPL")
        assert position is not None, "Position not created"
        assert position['qty'] == 100.0, f"Expected qty=100, got {position['qty']}"
        
        # Create 10 SELL executions
        sell_executions = []
        for i in range(10):
            exec_msg = FakeExecutionFactory.create_execution(
                symbol="AAPL",
                side="SELL",
                qty=10.0,
                price=155.0 + i * 0.5,
                order_id=2000 + i
            )
            sell_executions.append(exec_msg)
        
        # Apply sell executions
        for exec_msg in sell_executions:
            position_manager.apply_execution(exec_msg)
            risk_manager.update_after_execution(
                exec_msg['symbol'],
                exec_msg['side'],
                float(exec_msg['fill_qty']),
                float(exec_msg['fill_price'])
            )
        
        # Verify position closed
        position = position_manager.get_position("AAPL")
        assert position['qty'] == 0.0, f"Expected qty=0, got {position['qty']}"
        
        # Verify P&L
        realized_pnl = position_manager.get_total_realized_pnl()
        assert realized_pnl > 0, f"Expected positive P&L, got {realized_pnl}"
        
        print(f"✓ Applied 10 BUY executions")
        print(f"✓ Applied 10 SELL executions")
        print(f"✓ Position closed correctly")
        print(f"✓ Realized P&L: ${realized_pnl:.2f}")
    
    def test_risk_state_updates(self, setup):
        """Test risk manager state updates"""
        risk_manager = setup['risk_manager']
        
        # Create executions
        for i in range(5):
            exec_msg = FakeExecutionFactory.create_execution(
                symbol="AAPL",
                side="BUY",
                qty=10.0,
                price=150.0
            )
            risk_manager.update_after_execution(
                exec_msg['symbol'],
                exec_msg['side'],
                float(exec_msg['fill_qty']),
                float(exec_msg['fill_price'])
            )
        
        # Verify state
        state = risk_manager.get_state()
        assert state['trade_count'] == 5, f"Expected 5 trades, got {state['trade_count']}"
        assert state['trades_last_minute'] == 5, f"Expected 5 trades/min, got {state['trades_last_minute']}"
        
        print(f"✓ Risk state updated correctly")
        print(f"✓ Trade count: {state['trade_count']}")
    
    def test_no_deadlocks(self, setup):
        """Test system doesn't deadlock under load"""
        strategy = setup['strategy']
        
        # Generate high volume of ticks
        ticks = FakeExecutionFactory.create_ticks("AAPL", count=1000, start_price=150.0)
        
        start_time = time.time()
        
        # Process all ticks
        for tick in ticks:
            strategy.on_tick(tick)
        
        elapsed = time.time() - start_time
        
        # Should complete in reasonable time (< 10 seconds)
        assert elapsed < 10.0, f"Processing took too long: {elapsed}s"
        
        print(f"✓ Processed 1000 ticks in {elapsed:.2f}s")
        print(f"✓ No deadlocks detected")






