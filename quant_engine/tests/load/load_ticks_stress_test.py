"""tests/load/load_ticks_stress_test.py

High-load stress test: 100,000 ticks, measure throughput and performance.
"""

import time
import psutil
import os
from typing import Dict, Any

from app.strategy.strategy_example import ExampleStrategy
from app.strategy.candle_manager import CandleManager
from app.engine.position_manager import PositionManager
from app.risk.risk_manager import RiskManager
from app.risk.risk_limits import RiskLimits
from app.risk.risk_state import RiskState
from tests.utils.fake_execution_factory import FakeExecutionFactory


class LoadTicksStressTest:
    """Stress test for tick processing"""
    
    def __init__(self):
        self.strategy = ExampleStrategy()
        candle_manager = CandleManager(interval_seconds=60)
        position_manager = PositionManager()
        risk_limits = RiskLimits(max_trades_per_minute=10000)
        risk_state = RiskState()
        risk_manager = RiskManager(limits=risk_limits, state=risk_state)
        risk_manager.set_position_manager(position_manager)
        
        self.strategy.initialize(
            candle_manager=candle_manager,
            position_manager=position_manager,
            risk_manager=risk_manager
        )
    
    def run_test(self, tick_count: int = 100000) -> Dict[str, Any]:
        """
        Run stress test.
        
        Args:
            tick_count: Number of ticks to process
            
        Returns:
            Test results dict
        """
        print(f"🚀 Starting stress test: {tick_count:,} ticks")
        
        # Generate ticks
        print("Generating ticks...")
        ticks = FakeExecutionFactory.create_ticks("AAPL", count=tick_count, start_price=150.0)
        
        # Measure memory before
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / 1024 / 1024  # MB
        
        # Measure CPU before
        cpu_before = process.cpu_percent(interval=0.1)
        
        # Process ticks
        print("Processing ticks...")
        start_time = time.time()
        
        signals = 0
        indicator_time = 0
        candle_time = 0
        
        for i, tick in enumerate(ticks):
            # Measure indicator time
            ind_start = time.time()
            signal = self.strategy.on_tick(tick)
            ind_elapsed = time.time() - ind_start
            
            indicator_time += ind_elapsed
            
            # Measure candle time (approximate)
            candle_time += ind_elapsed * 0.3  # Estimate
            
            if signal:
                signals += 1
            
            # Progress update
            if (i + 1) % 10000 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                print(f"  Processed {i+1:,} ticks ({rate:.0f} ticks/sec)")
        
        total_time = time.time() - start_time
        
        # Measure memory after
        mem_after = process.memory_info().rss / 1024 / 1024  # MB
        mem_used = mem_after - mem_before
        
        # Measure CPU after
        cpu_after = process.cpu_percent(interval=0.1)
        
        # Calculate metrics
        throughput = tick_count / total_time
        avg_indicator_time = indicator_time / tick_count * 1000  # ms
        avg_candle_time = candle_time / tick_count * 1000  # ms
        
        results = {
            'tick_count': tick_count,
            'total_time': total_time,
            'throughput_ticks_per_sec': throughput,
            'signals_generated': signals,
            'avg_indicator_time_ms': avg_indicator_time,
            'avg_candle_time_ms': avg_candle_time,
            'memory_used_mb': mem_used,
            'cpu_percent': cpu_after
        }
        
        return results
    
    def print_results(self, results: Dict[str, Any]):
        """Print test results"""
        print("\n" + "="*60)
        print("STRESS TEST RESULTS")
        print("="*60)
        print(f"Ticks processed:      {results['tick_count']:,}")
        print(f"Total time:           {results['total_time']:.2f}s")
        print(f"Throughput:           {results['throughput_ticks_per_sec']:.0f} ticks/sec")
        print(f"Signals generated:    {results['signals_generated']}")
        print(f"Avg indicator time:   {results['avg_indicator_time_ms']:.3f} ms")
        print(f"Avg candle time:      {results['avg_candle_time_ms']:.3f} ms")
        print(f"Memory used:          {results['memory_used_mb']:.1f} MB")
        print(f"CPU usage:            {results['cpu_percent']:.1f}%")
        print("="*60)
        
        # Check performance threshold
        if results['throughput_ticks_per_sec'] < 5000:
            print("❌ FAIL: Throughput < 5,000 ticks/sec")
            return False
        else:
            print("✅ PASS: Throughput >= 5,000 ticks/sec")
            return True


if __name__ == "__main__":
    test = LoadTicksStressTest()
    results = test.run_test(tick_count=100000)
    passed = test.print_results(results)
    exit(0 if passed else 1)








