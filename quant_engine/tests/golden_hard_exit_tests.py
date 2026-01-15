import unittest
import sys
import os
from typing import Dict, Any

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.event_driven.decision_engine.hard_exit_engine import HardExitEngine

class TestGoldenHardExitScenarios(unittest.TestCase):
    def setUp(self):
        self.engine = HardExitEngine()
        
    def _make_pos(self, sym, size, cost, bucket='MM'):
        return {'symbol': sym, 'size': size, 'avg_cost': cost, 'bucket': bucket, 'mark_price': cost} # dummy mark
        
    def _make_md(self, bid, ask, truth=None, adv=1000):
        t = truth if truth else (bid+ask)/2
        return {'bid': bid, 'ask': ask, 'truth_price': t, 'adv': adv}

    def test_golden_1_profit_priority(self):
        """
        Scenario 1: Profit Priority
        Winner (Profit) must rank above Loser (Loss), even if Loser is "closer" to execution.
        """
        positions = [
            self._make_pos('LOSER', 100, 110), # Cost 110. Price 100. Loss 1000. Dist 10.
            self._make_pos('WINNER', 100, 90), # Cost 90. Price 100. Profit 1000. Dist 10.
        ]
        # Make LOSER closer to test priority override?
        # Say LOSER Cost 102 (Dist 2), WINNER Cost 90 (Dist 10).
        positions[0]['avg_cost'] = 102 
        
        md = {
            'LOSER': self._make_md(100, 101), # Sell @ 100. loss 200.
            'WINNER': self._make_md(100, 101), # Sell @ 100. profit 1000.
        }
        
        ranked = self.engine.rank_positions(positions, md)
        self.assertEqual(ranked[0]['symbol'], 'WINNER', "Profit must outrank Loss/Closeness")

    def test_golden_2_loss_minimization(self):
        """
        Scenario 2: Loss Minimization
        Small Loss ranked above Big Loss.
        """
        positions = [
            self._make_pos('BIG_LOSS', 100, 110),   # Cost 110. Price 100. Loss 1000.
            self._make_pos('SMALL_LOSS', 100, 102), # Cost 102. Price 100. Loss 200.
        ]
        md = {
            'BIG_LOSS': self._make_md(100, 101),
            'SMALL_LOSS': self._make_md(100, 101),
        }
        
        ranked = self.engine.rank_positions(positions, md)
        self.assertEqual(ranked[0]['symbol'], 'SMALL_LOSS', "Smallest loss must be first")

    def test_golden_3_mm_priority(self):
        """
        Scenario 3: MM Priority
        Default behavior selects MM over LT (Cost similar).
        """
        positions = [
            self._make_pos('MM_POS', 1000, 10, 'MM'),
            self._make_pos('LT_POS', 1000, 10, 'LT'),
        ]
        # Costs same (Slip 1.0)
        md = {
            'MM_POS': self._make_md(9, 11, truth=10), # Slip 1
            'LT_POS': self._make_md(9, 11, truth=10), # Slip 1
        }
        
        intents = self.engine.plan_hard_derisk(5000, positions, md, md, 'LATE', 'NORMAL', {}, {})
        # Should pick MM
        self.assertEqual(intents[0]['symbol'], 'MM_POS')

    def test_golden_4_cost_override(self):
        """
        Scenario 4: Cost Override
        MM rejected for LT if Cost_MM > 1.8 * Cost_LT.
        """
        positions = [
            self._make_pos('MM_BAD', 1000, 10, 'MM'),
            self._make_pos('LT_GOOD', 1000, 10, 'LT'),
        ]
        # MM Slip = 2.0 (8 vs 10). Cost 2000.
        # LT Slip = 1.0 (9 vs 10). Cost 1000.
        # 2000 > 1.8 * 1000. Switch!
        md = {
            'MM_BAD': self._make_md(8, 12, truth=10),
            'LT_GOOD': self._make_md(9, 11, truth=10),
        }
        
        intents = self.engine.plan_hard_derisk(5000, positions, md, md, 'LATE', 'NORMAL', {}, {})
        self.assertEqual(intents[0]['symbol'], 'LT_GOOD', "Must switch to LT if MM cost is restrictive")

    def test_golden_5_liquidity_tiebreak(self):
        """
        Scenario 5: Liquidity
        Illiquid name selected over Liquid name (when PnL similar).
        """
        positions = [
            self._make_pos('LIQUID', 100, 100),
            self._make_pos('ILLIQUID', 100, 100),
        ]
        # Identical PnL (0), Dist, Spread.
        # Diff ADV.
        md = {
            'LIQUID': self._make_md(100, 101, adv=1000000),
            'ILLIQUID': self._make_md(100, 101, adv=1000),
        }
        
        ranked = self.engine.rank_positions(positions, md)
        self.assertEqual(ranked[0]['symbol'], 'ILLIQUID', "Illiquid (Low ADV) must be first")

    def test_golden_6_low_confidence_full_exit(self):
        """
        Scenario 6: Low Confidence
        Full exit generated (no capping).
        """
        positions = [
            self._make_pos('LOW_CONF', 500, 100, 'MM'),
        ]
        md = {
            'LOW_CONF': self._make_md(100, 101),
        }
        # Low confidence score provided
        conf = {'LOW_CONF': 10.0} 
        
        # Request full reduction (Notional > Position Value)
        # 500 shares * 100 = 50,000. Request 60,000.
        intents = self.engine.plan_hard_derisk(60000, positions, md, md, 'LATE', 'NORMAL', conf, {})
        
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]['qty'], 500, "Must fully flatten despite low confidence")

    def test_golden_7_spread_preference(self):
        """
        Scenario 7: Spread Preference
        Narrow spread selected before Wide spread (all else equal).
        """
        positions = [
            self._make_pos('IsWIDE', 100, 100),
            self._make_pos('IsNARROW', 100, 100),
        ]
        # Same PnL per share (0). Same Dist (0).
        # Diff Spread.
        md = {
            # Wide: 99 - 101 (Spread 2.0). Exec Sell @ 99. Cost 100 -> Loss 1.0/sh
            'IsWIDE':   {'bid': 99.0, 'ask': 101.0, 'truth_price': 100.0, 'adv': 1000000},
            # Narrow: 99.9 - 100.1 (Spread 0.2). Exec Sell @ 99.9. Cost 100 -> Loss 0.1/sh
            # WAIT. If PnL is different, Profit Priority kicks in.
            # We want SAME PnL to test Spread tie-breaker.
            # So Exec Price must be same.
            # Wide: Bid 100. Ask 102. (Spread 2.0). Exec 100. Cost 100. PnL 0.
            'IsWIDE':   {'bid': 100.0, 'ask': 102.0, 'truth_price': 101.0, 'adv': 1000000},
            # Narrow: Bid 100. Ask 100.1. (Spread 0.1). Exec 100. Cost 100. PnL 0.
            'IsNARROW': {'bid': 100.0, 'ask': 100.1, 'truth_price': 100.05, 'adv': 1000000},
        }
        
        ranked = self.engine.rank_positions(positions, md)
        self.assertEqual(ranked[0]['symbol'], 'IsNARROW', "Narrow spread must be selected first")

    def test_golden_8_illiquid_gift(self):
        """
        Scenario 8: Illiquid 'Gift'
        Illiquid selected before Liquid (Tie-breaker for 'Gift' exit).
        """
        positions = [
            self._make_pos('LIQUID', 100, 100),
            self._make_pos('ILLIQUID', 100, 100),
        ]
        # Identical parameters except ADV
        md = {
            'LIQUID':   {'bid': 100, 'ask': 100.1, 'truth_price': 100.05, 'adv': 1000000},
            'ILLIQUID': {'bid': 100, 'ask': 100.1, 'truth_price': 100.05, 'adv': 5000},
        }
        ranked = self.engine.rank_positions(positions, md)
        self.assertEqual(ranked[0]['symbol'], 'ILLIQUID', "Illiquid must be first (Gift logic)")

if __name__ == '__main__':
    unittest.main()
