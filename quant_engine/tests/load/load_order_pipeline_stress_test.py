"""tests/load/load_order_pipeline_stress_test.py

Stress test for order pipeline: 10,000 signals → orders → executions.
"""

import time
from typing import Dict, Any

from app.core.event_bus import EventBus
from app.order.order_publisher import OrderPublisher
from app.engine.execution_handler import ExecutionHandler
from app.engine.position_manager import PositionManager
from app.risk.risk_manager import RiskManager
from app.risk.risk_limits import RiskLimits
from app.risk.risk_state import RiskState
from tests.utils.fake_execution_factory import FakeExecutionFactory


class LoadOrderPipelineStressTest:
    """Stress test for order pipeline"""
    
    def __init__(self):
        self.position_manager = PositionManager()
        risk_limits = RiskLimits(max_trades_per_minute=20000)
        risk_state = RiskState()
        self.risk_manager = RiskManager(limits=risk_limits, state=risk_state)
        self.risk_manager.set_position_manager(self.position_manager)
        
        self.execution_handler = ExecutionHandler(self.position_manager, risk_manager=self.risk_manager)
    
    def run_test(self, signal_count: int = 10000) -> Dict[str, Any]:
        """
        Run stress test.
        
        Args:
            signal_count: Number of signals to process
            
        Returns:
            Test results dict
        """
        print(f"🚀 Starting order pipeline stress test: {signal_count:,} signals")
        
        # Generate signals
        print("Generating signals...")
        signals = []
        for i in range(signal_count):
            signal = FakeExecutionFactory.create_signal(
                symbol="AAPL",
                signal="BUY" if i % 2 == 0 else "SELL",
                price=150.0 + (i % 10) * 0.5,
                quantity=10.0
            )
            signals.append(signal)
        
        # Measure order publishing
        print("Publishing orders...")
        order_start = time.time()
        
        orders_published = 0
        for signal in signals:
            try:
                OrderPublisher.publish(
                    signal['symbol'],
                    signal['signal'],
                    signal['quantity'],
                    signal.get('order_type', 'MKT')
                )
                orders_published += 1
            except Exception as e:
                print(f"Error publishing order: {e}")
        
        order_time = time.time() - order_start
        
        # Generate executions
        print("Generating executions...")
        executions = []
        for i, signal in enumerate(signals[:signal_count]):
            exec_msg = FakeExecutionFactory.create_execution(
                symbol=signal['symbol'],
                side=signal['signal'],
                qty=signal['quantity'],
                price=signal['price'],
                order_id=1000 + i
            )
            executions.append(exec_msg)
        
        # Measure execution processing
        print("Processing executions...")
        exec_start = time.time()
        
        for exec_msg in executions:
            self.execution_handler._process_execution(exec_msg)
        
        exec_time = time.time() - exec_start
        
        # Calculate metrics
        order_throughput = orders_published / order_time
        exec_throughput = len(executions) / exec_time
        avg_order_latency = (order_time / orders_published) * 1000  # ms
        avg_exec_latency = (exec_time / len(executions)) * 1000  # ms
        
        results = {
            'signal_count': signal_count,
            'orders_published': orders_published,
            'executions_processed': len(executions),
            'order_time': order_time,
            'exec_time': exec_time,
            'order_throughput_per_sec': order_throughput,
            'exec_throughput_per_sec': exec_throughput,
            'avg_order_latency_ms': avg_order_latency,
            'avg_exec_latency_ms': avg_exec_latency
        }
        
        return results
    
    def print_results(self, results: Dict[str, Any]):
        """Print test results"""
        print("\n" + "="*60)
        print("ORDER PIPELINE STRESS TEST RESULTS")
        print("="*60)
        print(f"Signals:              {results['signal_count']:,}")
        print(f"Orders published:     {results['orders_published']:,}")
        print(f"Executions processed:  {results['executions_processed']:,}")
        print(f"Order time:           {results['order_time']:.2f}s")
        print(f"Exec time:            {results['exec_time']:.2f}s")
        print(f"Order throughput:     {results['order_throughput_per_sec']:.0f} orders/sec")
        print(f"Exec throughput:      {results['exec_throughput_per_sec']:.0f} execs/sec")
        print(f"Avg order latency:    {results['avg_order_latency_ms']:.3f} ms")
        print(f"Avg exec latency:     {results['avg_exec_latency_ms']:.3f} ms")
        print("="*60)
        
        # Check performance
        passed = True
        if results['order_throughput_per_sec'] < 1000:
            print("❌ FAIL: Order throughput < 1,000 orders/sec")
            passed = False
        else:
            print("✅ PASS: Order throughput >= 1,000 orders/sec")
        
        if results['exec_throughput_per_sec'] < 1000:
            print("❌ FAIL: Execution throughput < 1,000 execs/sec")
            passed = False
        else:
            print("✅ PASS: Execution throughput >= 1,000 execs/sec")
        
        return passed


if __name__ == "__main__":
    test = LoadOrderPipelineStressTest()
    results = test.run_test(signal_count=10000)
    passed = test.print_results(results)
    exit(0 if passed else 1)








