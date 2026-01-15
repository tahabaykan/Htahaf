import unittest
import sys
import os
from pathlib import Path
from collections import deque

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.event_driven.decision_engine.hard_exit_engine import HardExitEngine

class TestHardExitEngine(unittest.TestCase):
    def setUp(self):
        self.engine = HardExitEngine()
        
    def test_ranking_profitability(self):
        """Verify: Profit > Smallest Loss"""
        positions = [
            {'symbol': 'LOSER_BIG', 'size': 100, 'avg_cost': 100, 'bucket': 'MM'},
            {'symbol': 'WINNER',    'size': 100, 'avg_cost': 90,  'bucket': 'MM'},
            {'symbol': 'LOSER_SMALL', 'size': 100, 'avg_cost': 100, 'bucket': 'MM'},
        ]
        # Market Data: Price = 95
        # WINNER: (95 - 90) * 100 = +500 Profit
        # LOSER_BIG: (95 - 100) * 100 = -500 Loss (Abs 500)
        # LOSER_SMALL: Let's make it small loss. Price = 99.
        
        market_data = {
            'WINNER': {'bid': 95, 'ask': 96, 'adv': 1000},
            'LOSER_BIG': {'bid': 95, 'ask': 96, 'adv': 1000}, # Loss 500
            'LOSER_SMALL': {'bid': 99, 'ask': 100, 'adv': 1000}, # Loss 100 (99-100)
        }
        
        ranked = self.engine.rank_positions(positions, market_data)
        
        symbols = [p['symbol'] for p in ranked]
        # Expected: WINNER (Profit), LOSER_SMALL (Small Loss), LOSER_BIG (Big Loss)
        self.assertEqual(symbols, ['WINNER', 'LOSER_SMALL', 'LOSER_BIG'])

    def test_ranking_exec_proximity(self):
        """Verify: Closer to Exec > Farther (Tie on Profit)"""
        positions = [
            {'symbol': 'FAR',  'size': 100, 'avg_cost': 110, 'bucket': 'MM'}, # Cost 110
            {'symbol': 'CLOSE', 'size': 100, 'avg_cost': 102, 'bucket': 'MM'}, # Cost 102
        ]
        # Both are Losers. Price = 100.
        # FAR: Loss 1000. Dist = 10.
        # CLOSE: Loss 200. Dist = 2.
        # Wait, Smallest Loss logic already handles this? 
        # Yes, Smallest Loss covers dist if size is same. 
        # Let's make Wins equal to test Dist.
        
        positions = [
            {'symbol': 'FAR_WIN', 'size': 100, 'avg_cost': 90, 'bucket': 'MM'}, # +1000
            {'symbol': 'CLOSE_WIN', 'size': 100, 'avg_cost': 90, 'bucket': 'MM'}, # +1000
        ]
        # Same Cost/Profit. Differentiate by Bid Price proximity? 
        # Exec Proximity = abs(Exec - AvgCost).
        # If AvgCost is same, and Profit is same, then Exec Price is same.
        # We need Different Cost but SAME PROFIT? Valid if size differs? 
        # No, Profit is absolute. 
        # Let's try: Same Profit, Different Dist? 
        # Pos A: Size 100, Cost 90, Bid 100. Profit 1000. Dist 10.
        # Pos B: Size 50,  Cost 80, Bid 100. Profit 1000. Dist 20.
        # Result: A should be first (Closer).
        
        positions = [
            {'symbol': 'NEAR', 'size': 100, 'avg_cost': 90, 'bucket': 'MM'},
            {'symbol': 'FAR',  'size': 50,  'avg_cost': 80, 'bucket': 'MM'},
        ]
        market_data = {
            'NEAR': {'bid': 100, 'ask': 101, 'adv': 1000},
            'FAR':  {'bid': 100, 'ask': 101, 'adv': 1000},
        }
        
        ranked = self.engine.rank_positions(positions, market_data)
        self.assertEqual(ranked[0]['symbol'], 'NEAR')

    def test_mm_lt_cost_switch(self):
        """Verify: Switch to LT if MM cost > 1.8 * LT cost"""
        # MM Position: High Slippage
        # LT Position: Low Slippage
        positions = [
            {'symbol': 'MM_BAD', 'size': 1000, 'bucket': 'MM', 'mark_price': 10},
            {'symbol': 'LT_GOOD', 'size': 1000, 'bucket': 'LT', 'mark_price': 10},
        ]
        
        # Slip: MM=2.0 (Cost 2000), LT=1.0 (Cost 1000). 2.0 > 1.8*1.0? Yes.
        market_data = {
            'MM_BAD': {'bid': 8, 'ask': 12, 'truth_price': 10, 'adv': 1000}, # Exec 8 (Long). Slip 2.
            'LT_GOOD': {'bid': 9, 'ask': 11, 'truth_price': 10, 'adv': 1000}, # Exec 9. Slip 1.
        }
        
        intents = self.engine.plan_reduction(positions, market_data, 5000) # Reduce 5000 USD (~500 shares)
        
        # Should pick LT because MM cost is 2x LT cost.
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]['symbol'], 'LT_GOOD')
        self.assertEqual(intents[0]['type'], 'LT_LONG_DECREASE')

    def test_mm_lt_no_switch(self):
        """Verify: Stay on MM if cost <= 1.8 * LT"""
        # Slip: MM=1.5, LT=1.0. 1.5 < 1.8. Stay MM.
        positions = [
            {'symbol': 'MM_OK', 'size': 1000, 'bucket': 'MM', 'mark_price': 10},
            {'symbol': 'LT_GOOD', 'size': 1000, 'bucket': 'LT', 'mark_price': 10},
        ]
        market_data = {
            'MM_OK': {'bid': 8.5, 'ask': 11.5, 'truth_price': 10, 'adv': 1000}, # Exec 8.5. Slip 1.5.
            'LT_GOOD': {'bid': 9, 'ask': 11, 'truth_price': 10, 'adv': 1000},    # Slip 1.
        }
        
        intents = self.engine.plan_reduction(positions, market_data, 5000)
        self.assertEqual(intents[0]['symbol'], 'MM_OK')

if __name__ == '__main__':
    unittest.main()
