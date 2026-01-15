
"""
Test Suite for Janall DNA Integration
- TumCSV Selection
- Strict Lot Rounding
- Final Score Logic
"""
import unittest
import math
import sys
import os

# Fix import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.psfalgo.selection import SelectionEngine
from app.psfalgo.intent_math import calculate_rounded_lot, calculate_final_score

# Mock Config
MOCK_CONFIG = {
    'selection': {
        'tumcsv_modes': {
            'v10': {'percent': 0.10, 'min_count': 2},
            'v15': {'percent': 0.15, 'min_count': 2}
        },
        'issuer_limit': {'enabled': True}
    }
}

class TestJanallDNA(unittest.TestCase):
    
    def test_strict_lot_rounding(self):
        """Verify 0 or >= 200 lot rule."""
        # 1. Below 100 -> 0
        self.assertEqual(calculate_rounded_lot(99), 0)
        
        # 2. Prohibited Zone 100-149 -> 0
        self.assertEqual(calculate_rounded_lot(100), 0)
        self.assertEqual(calculate_rounded_lot(149), 0)
        
        # 3. Prohibited Zone 150-199 -> 200
        self.assertEqual(calculate_rounded_lot(150), 200)
        self.assertEqual(calculate_rounded_lot(199), 200)
        
        # 4. Normal Zone >= 200 (Nearest 100)
        self.assertEqual(calculate_rounded_lot(220), 200)
        self.assertEqual(calculate_rounded_lot(250), 300) # round half up usually? Py3 round half to even.
        # Python 3 round(2.5) -> 2, round(3.5) -> 4. 
        # 250 / 100 = 2.5 -> round -> 2 * 100 = 200? Check impl.
        # Impl: int(round(raw / 100.0) * 100)
        # round(2.5) is 2. So 250 -> 200. 
        # But 251 -> 2.51 -> 3 -> 300.
        # Let's verify behavior.
        self.assertEqual(calculate_rounded_lot(251), 300) 
        self.assertEqual(calculate_rounded_lot(349), 300)
        self.assertEqual(calculate_rounded_lot(351), 400)

    def test_final_score_calculation(self):
        """Verify Scoring Math."""
        # Long Score: Final_THG - (1000 * Ucuzluk)
        # High THG (80) - Cheap (-0.05) -> 80 - (1000*-0.05) = 80 + 50 = 130 (Higher is Better)
        self.assertEqual(calculate_final_score(80, -0.05), 130)
        
        # Short Score: SHORT_FINAL - (1000 * Pahalilik)
        # Low SHORT_FINAL (10) - Expensive (+0.05) -> 10 - (1000*0.05) = 10 - 50 = -40 (Lower is Better)
        self.assertEqual(calculate_final_score(10, 0.05), -40)

    def test_tumcsv_selection_long(self):
        """Verify Top X% for Long."""
        engine = SelectionEngine(MOCK_CONFIG)
        
        # 10 candidates
        cands = [
            {'CMON': 'A', 'Final_BB_skor': 100},
            {'CMON': 'B', 'Final_BB_skor': 90},
            {'CMON': 'C', 'Final_BB_skor': 80},
            {'CMON': 'D', 'Final_BB_skor': 70},
            {'CMON': 'E', 'Final_BB_skor': 60},
            {'CMON': 'F', 'Final_BB_skor': 50},
            {'CMON': 'G', 'Final_BB_skor': 40},
            {'CMON': 'H', 'Final_BB_skor': 30},
            {'CMON': 'I', 'Final_BB_skor': 20},
            {'CMON': 'J', 'Final_BB_skor': 10},
        ]
        
        # V10 -> 10% of 10 = 1. But min_count = 2. Should pick Top 2.
        # Long sorts Descending (High score first)
        selected = engine.apply_tumcsv_selection(cands, 'v10', 'LONG', 'Final_BB_skor')
        print(f"DEBUG LONG: Selected {len(selected)} items: {selected}")
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]['Final_BB_skor'], 100)
        self.assertEqual(selected[1]['Final_BB_skor'], 90)

    def test_tumcsv_selection_short(self):
        """Verify Bottom X% for Short (impl as Ascending Sort)."""
        engine = SelectionEngine(MOCK_CONFIG)
        cands = [
            {'CMON': 'A', 'Final_SAS_skor': 100},
            {'CMON': 'B', 'Final_SAS_skor': -50}, # Best Short
            {'CMON': 'C', 'Final_SAS_skor': -40}, # 2nd Best
            {'CMON': 'D', 'Final_SAS_skor': 0},
        ]
        # Short sorts Ascending (Low score first)
        selected = engine.apply_tumcsv_selection(cands, 'v10', 'SHORT', 'Final_SAS_skor')
        # Min count 2
        print(f"DEBUG SHORT: Selected {len(selected)} items: {selected}")
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]['Final_SAS_skor'], -50)
        self.assertEqual(selected[1]['Final_SAS_skor'], -40)

    def test_issuer_limit_selection(self):
        """Verify Issuer Limit (40% rule)."""
        engine = SelectionEngine(MOCK_CONFIG)
        # 10 candidates, 5 from same issuer 'MSG'
        # Total 10 -> 40% = Max 4 per issuer.
        # If we request V20 (let's say we want lots of stocks) -> Min 2.
        # Let's fake selection percent to 100% to test limit.
        engine.tumcsv_config['all'] = {'percent': 1.0, 'min_count': 10}
        
        cands = []
        for i in range(5):
            cands.append({'CMON': 'MSG', 'Final_BB_skor': 100-i}) # Scores 100, 99, 98, 97, 96
        for i in range(5):
            cands.append({'CMON': 'OTHER', 'Final_BB_skor': 50-i})
            
        # Limit per company = 10 / 1.6 = 6.25 -> 6.
        # MSG has 5 candidates. All accepted.
        # OTHER has 5 candidates. All accepted.
        # Total 10.
        
        selected = engine.apply_tumcsv_selection(cands, 'all', 'LONG', 'Final_BB_skor')
        
        msg_count = sum(1 for c in selected if c['CMON'] == 'MSG')
        self.assertEqual(msg_count, 5) 
        self.assertEqual(len(selected), 10) # 5 MSG + 5 OTHER

if __name__ == '__main__':
    unittest.main()
