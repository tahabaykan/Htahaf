import unittest
import sys
import os
from pathlib import Path
from collections import deque

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.market_data.truth_ticks_engine import TruthTicksEngine

class TestTruthTicksWeighted(unittest.TestCase):
    def setUp(self):
        # Initialize engine
        self.engine = TruthTicksEngine()
        
        # Override config manually for testing to ensure deterministic behavior
        self.engine.config = {
             'print_realism': {
                 'weights': {'lot_100_200': 1.0, 'round_large': 0.4, 'irregular': 0.2},
                 'min_lot_ignore': 20
             },
             'slippage': {
                 'adv_thresholds': [
                     {'adv': 100000, 'bad_slip': 0.03},
                     {'adv': 40000, 'bad_slip': 0.05}
                 ],
                 'adv_default_bad_slip': 0.12,
                 'spread_floor_multiplier': 0.25
             }
        }
        self.engine.MIN_SIZE = 20

    def test_calculate_print_weight(self):
        """Test the new 3-tier weighting logic"""
        # 100/200 -> 1.0
        self.assertAlmostEqual(self.engine.calculate_print_weight(100), 1.0)
        self.assertAlmostEqual(self.engine.calculate_print_weight(200), 1.0)
        
        # 300, 400, 1000 -> 0.4 (Round large)
        self.assertAlmostEqual(self.engine.calculate_print_weight(300), 0.4)
        self.assertAlmostEqual(self.engine.calculate_print_weight(500), 0.4)
        self.assertAlmostEqual(self.engine.calculate_print_weight(1000), 0.4)
        
        # Irregular -> 0.2
        self.assertAlmostEqual(self.engine.calculate_print_weight(150), 0.2)
        self.assertAlmostEqual(self.engine.calculate_print_weight(21), 0.2)
        self.assertAlmostEqual(self.engine.calculate_print_weight(350), 0.2) # Not round
        
        # Check logic for 300
        self.assertAlmostEqual(self.engine.calculate_print_weight(300), 0.4)

    def test_is_truth_tick(self):
        """Test that venue filtering is removed and only size matters"""
        # Venue logic removed, only size matters (>= MIN_SIZE)
        self.assertTrue(self.engine.is_truth_tick({'size': 20, 'exch': 'NYSE'}))
        self.assertTrue(self.engine.is_truth_tick({'size': 20, 'exch': 'FNRA'}))
        self.assertFalse(self.engine.is_truth_tick({'size': 19, 'exch': 'NYSE'}))
        # FNRA 100/200 rule was specific before, now just size
        self.assertTrue(self.engine.is_truth_tick({'size': 100, 'exch': 'FNRA'}))

    def test_calculate_bad_slip(self):
        """Test dynamic bad slippage threshold calculation"""
        # High ADV (>= 100000) -> 0.03
        self.assertAlmostEqual(self.engine.calculate_bad_slip(150000, spread=0.01), 0.03)
        
        # Medium ADV (>= 40000) -> 0.05
        self.assertAlmostEqual(self.engine.calculate_bad_slip(50000, spread=0.01), 0.05)
        
        # Low ADV (< 40000, fallback to default) -> 0.12
        self.assertAlmostEqual(self.engine.calculate_bad_slip(1000, spread=0.01), 0.12)
        
        # Spread Floor Logic
        # bad_slip base = 0.03, spread = 0.20 -> floor = 0.20 * 0.25 = 0.05. Result 0.05 (max)
        self.assertAlmostEqual(self.engine.calculate_bad_slip(150000, spread=0.20), 0.05)
        
        # bad_slip base = 0.03, spread = 0.04 -> floor = 0.01. Result 0.03
        self.assertAlmostEqual(self.engine.calculate_bad_slip(150000, spread=0.04), 0.03)

    def test_compute_metrics_weighted_volume(self):
        """Test that Truth Volume and VWAP use realism weights"""
        import time
        now = time.time()
        
        # Setup ticks (recent timestamps)
        ticks = [
            {'ts': now - 100, 'price': 10.0, 'size': 100, 'exch': 'NYSE'}, # W=1.0, Vol=100
            {'ts': now - 50,  'price': 10.1, 'size': 300, 'exch': 'NYSE'}, # W=0.4, Vol=120
            {'ts': now - 10,  'price': 10.2, 'size': 50 , 'exch': 'NYSE'}, # W=0.2, Vol=10
        ]
        # Total Weighted Vol = 100 + 120 + 10 = 230
        # Weighted Value = (10.0*100) + (10.1*120) + (10.2*10) = 1000 + 1212 + 102 = 2314
        # VWAP = 2314 / 230 = 10.060869...
        
        self.engine.tick_store['TEST'] = deque(ticks)
        
        metrics = self.engine.compute_metrics('TEST', avg_adv=10000)
        
        self.assertIsNotNone(metrics)
        # compute_metrics returns 'truth_volume_100'
        self.assertIn('truth_volume_100', metrics)
        self.assertAlmostEqual(metrics['truth_volume_100'], 230.0)
        self.assertAlmostEqual(metrics['truth_vwap_100'], 2314/230)

if __name__ == '__main__':
    unittest.main()
