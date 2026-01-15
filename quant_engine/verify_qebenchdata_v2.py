
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import json
import threading
from datetime import datetime

# Add path to allow imports
sys.path.append(r"c:\StockTracker\quant_engine")

# ----------------------------------------------------------------------
# MOCK SETUP BEFORE IMPORTS
# ----------------------------------------------------------------------
# We need to mock 'redis' and 'websocket' behavior to prevent real connections/threads

# Create a mock for app.core.redis_client
mock_redis_module = MagicMock()
mock_redis_instance = MagicMock()
mock_redis_module.redis_client = mock_redis_instance

# Setup PubSub mock to yield one message then stop, PREVENTING INFINITE LOOPS
mock_pubsub = MagicMock()
# listen() returns an iterator. We yield one item then stop.
mock_pubsub.listen.return_value = iter([
    {'type': 'message', 'data': json.dumps({'mode': 'HAMMER_PRO'})}
])
mock_redis_instance.pubsub.return_value = mock_pubsub

# Inject into sys.modules
sys.modules['app.core.redis_client'] = mock_redis_module

# Also mock HammerClient to prevent any accidental usage
mock_hammer_module = MagicMock()
sys.modules['app.live.hammer_client'] = mock_hammer_module

# Now we can import the module under test
try:
    from app.analysis import qebenchdata
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    sys.exit(1)

# ----------------------------------------------------------------------
# TEST CLASS
# ----------------------------------------------------------------------
class TestQeBenchDataLogger(unittest.TestCase):

    def setUp(self):
        # Reset Singleton for each test
        qebenchdata._logger_instance = None
        if hasattr(qebenchdata.QeBenchDataLogger, '_instance'):
             qebenchdata.QeBenchDataLogger._instance = None
             
        # Mock StaticDataStore
        self.mock_store_patcher = patch('app.market_data.static_data_store.get_static_store')
        self.mock_store = self.mock_store_patcher.start()
        self.mock_store_instance = MagicMock()
        self.mock_store.return_value = self.mock_store_instance
        self.mock_store_instance.is_loaded.return_value = True

        # Ensure Redis mock is clean
        mock_redis_instance.reset_mock()

    def tearDown(self):
        self.mock_store_patcher.stop()

    def test_initialization_and_listener(self):
        print(">> Testing Initialization & Listener...")
        logger = qebenchdata.get_bench_logger()
        # Should have subscribed
        mock_redis_instance.pubsub.assert_called_once()
        mock_pubsub.subscribe.assert_called_with("sys:account_change")
        print("   ✅ Redis subscription verified")

    def test_log_fill_realtime(self):
        print(">> Testing Realtime Fill Logging...")
        logger = qebenchdata.get_bench_logger()
        
        # Setup Peers for logic
        # Mock _get_peers_for_symbol via StaticDataStore
        # We'll mock the internal helper method to avoid complexity
        logger._get_peers_for_symbol = MagicMock(return_value=['PEER_A', 'PEER_B'])
        
        # Mock Redis get for prices
        def mock_redis_get(key):
            if 'PEER_A' in key: return json.dumps({'last': 100.0})
            if 'PEER_B' in key: return json.dumps({'last': 106.0}) # Avg 103
            return None
        mock_redis_instance.get.side_effect = mock_redis_get
        
        # Log Fill
        fill_time = datetime.now()
        logger.log_fill(
            symbol="TARGET", price=105.0, qty=10, action="BUY", 
            account="IBKR_1", fill_time=fill_time, fill_id="TEST_FILL_1"
        )
        
        # Verify Publish
        # Expected Benchmark: (100+106)/2 = 103.0
        mock_redis_instance.publish.assert_not_called() # Code uses set(), not publish() by default for now?
        # Checked code: it uses redis_client.set(key, json) and commented out publish
        # Verify SET
        mock_redis_instance.set.assert_called()
        args = mock_redis_instance.set.call_args[0]
        self.assertIn("bench:last_fill:TARGET", args[0])
        payload = json.loads(args[1])
        self.assertEqual(payload['bench_price'], 103.0)
        self.assertEqual(payload['bench_source'], "REALTIME")
        print(f"   ✅ Realtime Benchmark Calculated: {payload['bench_price']}")

    def test_log_fill_recovery(self):
        print(">> Testing Recovery Fill Logging...")
        logger = qebenchdata.get_bench_logger()
        
        # Force "recovery" via time
        old_time = datetime(2020, 1, 1, 12, 0, 0)
        
        # Mock _recover_benchmark_via_hammer
        logger._recover_benchmark_via_hammer = MagicMock(return_value=55.5)
        
        logger.log_fill(
            symbol="TARGET", price=50.0, qty=10, action="SELL", 
            account="HAMMER", fill_time=old_time, fill_id="TEST_FILL_REC"
        )
        
        # Verify it called recovery
        logger._recover_benchmark_via_hammer.assert_called_with("TARGET", old_time)
        
        # Verify Redis Set
        args = mock_redis_instance.set.call_args[0]
        payload = json.loads(args[1])
        self.assertEqual(payload['bench_price'], 55.5)
        self.assertEqual(payload['bench_source'], "RECOVERED:HAMMER_TICKS")
        print(f"   ✅ Recovery Benchmark Used: {payload['bench_price']}")

# ----------------------------------------------------------------------
# MAIN EXECUTION
# ----------------------------------------------------------------------
if __name__ == '__main__':
    print("Starting Verification Tests...")
    # Run tests with buffer=False to see output immediately
    # exit=False ensures script doesn't kill shell even if fails
    runner = unittest.TextTestRunner(verbosity=2, buffer=False)
    result = runner.run(unittest.makeSuite(TestQeBenchDataLogger))
    
    if result.wasSuccessful():
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("\n❌ TESTS FAILED")
        sys.exit(1)
