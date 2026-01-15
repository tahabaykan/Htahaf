
import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime
import json
import time

# Add path to allow imports
sys.path.append(r"c:\StockTracker\quant_engine")

class TestQeBenchDataLogger(unittest.TestCase):

    def setUp(self):
        # Mock Redis
        self.mock_redis_patcher = patch('app.core.redis_client.redis_client')
        self.mock_redis = self.mock_redis_patcher.start()
        
        # Mock StaticDataStore
        self.mock_store_patcher = patch('app.market_data.static_data_store.get_static_store')
        self.mock_store = self.mock_store_patcher.start()
        self.mock_store_instance = MagicMock()
        self.mock_store.return_value = self.mock_store_instance
        self.mock_store_instance.is_loaded.return_value = True
        
        # Mock dependencies in modules
        sys.modules['app.core.redis_client'] = MagicMock()
        sys.modules['app.core.redis_client'].redis_client = self.mock_redis
        
        # Import the module under test
        from app.analysis import qebenchdata
        self.qebenchdata = qebenchdata
        
        # Reset Singleton
        qebenchdata._bench_logger = None

    def tearDown(self):
        self.mock_redis_patcher.stop()
        self.mock_store_patcher.stop()

    def test_log_fill_realtime(self):
        """Test logging a fill with realtime benchmark calculation"""
        logger = self.qebenchdata.GetQeBenchDataLogger()
        
        # Setup Peers
        # Symbol: TEST_A, Group: G1. Peers: TEST_B, TEST_C
        self.mock_store_instance.get_static_data.side_effect = lambda s: {'GROUP': 'G1', 'CGRUP': None} if s in ['TEST_A', 'TEST_B', 'TEST_C'] else None
        self.mock_store_instance.get_all_symbols.return_value = ['TEST_A', 'TEST_B', 'TEST_C']
        
        # Mock Redis prices for peers (market_context:{symbol}:5m)
        # TEST_B: 100, TEST_C: 102
        # Average should be (100 + 102 + 101(self?)) / 3 or just peers?
        # Logic includes self if in list.
        # Let's say we have 3 stocks in group.
        
        def mock_get(key):
            if 'TEST_B' in key: return json.dumps({'last': 100.0, 'last_price': 100.0})
            if 'TEST_C' in key: return json.dumps({'last': 102.0, 'last_price': 102.0})
            if 'TEST_A' in key: return json.dumps({'last': 101.0, 'last_price': 101.0})
            return None
        self.mock_redis.get.side_effect = mock_get
        
        # Call log_fill
        fill_time = datetime.now()
        logger.log_fill(
            symbol="TEST_A",
            price=101.5,
            qty=100,
            action="BUY",
            account="IBKR_GUN",
            source_module="TEST",
            fill_time=fill_time,
            fill_id="FILL_001"
        )
        
        # Verify Redis Publish
        expected_bench = (100.0 + 102.0 + 101.0) / 3 # 101.0
        self.mock_redis.publish.assert_called_once()
        args = self.mock_redis.publish.call_args[0]
        self.assertEqual(args[0], "bench:last_fill:TEST_A")
        payload = json.loads(args[1])
        self.assertEqual(payload['symbol'], 'TEST_A')
        self.assertAlmostEqual(payload['group_avg_price'], 101.0)
        
        # Verify CSV content
        date_str = fill_time.strftime('%Y%m%d')
        filename = f"c:\\StockTracker\\quant_engine\\reports\\qebenchdata_{date_str}.csv"
        self.assertTrue(os.path.exists(filename))
        
        df = pd.read_csv(filename)
        # Filter for our fill ID
        row = df[df['fill_id'] == 'FILL_001'].iloc[0]
        self.assertEqual(row['symbol'], 'TEST_A')
        self.assertAlmostEqual(row['group_benchmark_price'], 101.0)
        
        print(f"✅ Realtime Fill logged successfully. Bench: {row['group_benchmark_price']}")

    @patch('app.live.hammer_client.HammerClient')
    def test_log_fill_recovery(self, MockHammer):
        """Test logging a historical fill with Hammer recovery"""
        logger = self.qebenchdata.GetQeBenchDataLogger()
        
        # Setup Peers (Same G1)
        self.mock_store_instance.get_static_data.side_effect = lambda s: {'GROUP': 'G1'}
        self.mock_store_instance.get_all_symbols.return_value = ['TEST_A', 'TEST_B']
        
        # Mock Hammer Client response for get_ticks
        mock_client = MockHammer.return_value
        mock_client.connect.return_value = True
        
        # Mock Ticks: 
        # Target Time: 12:00:00
        # Tick 1 (12:00:01) - too new
        # Tick 2 (11:59:59) - GOOD (Price 50)
        target_time = datetime(2025, 5, 20, 12, 0, 0)
        
        def mock_get_ticks(symbol, **kwargs):
            return {
                'data': [
                    {'t': '2025-05-20T12:00:05', 'p': 55.0},
                    {'t': '2025-05-20T11:59:55', 'p': 50.0}, # Matches TEST_A and TEST_B
                ]
            }
        mock_client.get_ticks.side_effect = mock_get_ticks
        
        # Call log_fill with OLD time
        logger.log_fill(
            symbol="TEST_A",
            price=52.0,
            qty=100,
            action="BUY",
            account="HAMMER_PRO",
            source_module="RECOVERY",
            fill_time=target_time,
            fill_id="FILL_REC_001"
        )
        
        # Verify Hammer Called
        self.assertTrue(mock_client.connect.called)
        # Should call for TEST_A and TEST_B
        self.assertEqual(mock_client.get_ticks.call_count, 2)
        
        # Benchmark = (50.0 + 50.0) / 2 = 50.0
        # Verify CSV
        date_str = target_time.strftime('%Y%m%d') # Note: CSV uses Current Date for file, or fill date? Code uses `datetime.now()` for filename.
        # The file will be named with TODAY's date, but row has fill time.
        filename = f"c:\\StockTracker\\quant_engine\\reports\\qebenchdata_{datetime.now().strftime('%Y%m%d')}.csv"
        
        df = pd.read_csv(filename)
        row = df[df['fill_id'] == 'FILL_REC_001'].iloc[0]
        self.assertEqual(row['active_mode'], 'HAMMER_PRO') # Since we didn't change mode, it defaults or we passed it
        # Actually logic uses `current_active_mode` from context, but we passed `account` string.
        # The benchmark should be 50.0
        self.assertAlmostEqual(row['group_benchmark_price'], 50.0)
        self.assertEqual(row['recovery_method'], 'HAMMER_TICKS')
        
        print(f"✅ Recovered Fill logged successfully. Bench: {row['group_benchmark_price']}")

    def test_account_mismatch_warning(self):
        """Test that account mismatch logs a warning"""
        logger = self.qebenchdata.GetQeBenchDataLogger()
        logger.current_active_mode = "HAMMER_PRO"
        
        with self.assertLogs(level='WARNING') as cm:
            logger.log_fill(
                symbol="TEST_A",
                price=100,
                qty=10,
                action="BUY",
                account="DU12345", # IBKR Account
                source_module="TEST",
                fill_time=datetime.now(),
                fill_id="FILL_WARN"
            )
            self.assertTrue(any("Account Mismatch" in o for o in cm.output))
            print("✅ Account Mismatch warning verify passed.")

if __name__ == '__main__':
    unittest.main()
