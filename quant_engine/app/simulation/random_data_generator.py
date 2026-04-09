"""
Random Data Generator - Generate random market data for LIFELESS mode

Features:
- Realistic bid/ask spreads
- Price continuity (random walk)
- Random positions for testing
- Volume simulation
"""
import random
from typing import Dict, List, Optional
from dataclasses import dataclass

from loguru import logger


@dataclass
class RandomL1Data:
    """Random L1 market data"""
    symbol: str
    bid: float
    ask: float
    mid: float
    bid_size: int
    ask_size: int
    last_trade: float
    volume: int


class RandomDataGenerator:
    """
    Generates random market data for LIFELESS mode.
    
    Features:
    - Price continuity (random walk)
    - Realistic spreads (0.1-0.5%)
    - Volume simulation
    - Position generation for testing
    
    Usage:
        generator = RandomDataGenerator(seed=42)
        l1_data = generator.generate_l1_data('SOJD')
        positions = generator.generate_positions(num_positions=50)
    """
    
    def __init__(self, seed: Optional[int] = None):
        if seed:
            random.seed(seed)
        
        # Price cache for continuity
        self.prices: Dict[str, float] = {}
        
        # Common stock symbols for testing
        self.test_symbols = [
            'SOJD', 'SOKM', 'EUHOL', 'NUGYO', 'PGSUS', 
            'THYAO', 'KARS', 'TOASO', 'ASELS', 'AKSEN'
        ]
        
        logger.info("[RandomDataGenerator] Initialized")
    
    def generate_l1_data(self, symbol: str) -> RandomL1Data:
        """
        Generate random L1 data for a symbol.
        
        Uses random walk to maintain price continuity.
        """
        # Get or initialize base price
        if symbol not in self.prices:
            # Initial random price
            self.prices[symbol] = random.uniform(10.0, 50.0)
        
        # Random walk (±5% max movement)
        change = random.uniform(-0.05, 0.05)
        self.prices[symbol] *= (1 + change)
        
        # Keep price in reasonable range
        self.prices[symbol] = max(5.0, min(100.0, self.prices[symbol]))
        
        mid_price = self.prices[symbol]
        
        # Random spread (0.1-0.5%)
        spread_pct = random.uniform(0.001, 0.005)
        spread = mid_price * spread_pct
        
        bid = mid_price - spread / 2
        ask = mid_price + spread / 2
        
        return RandomL1Data(
            symbol=symbol,
            bid=round(bid, 2),
            ask=round(ask, 2),
            mid=round(mid_price, 2),
            bid_size=random.randint(100, 10000),
            ask_size=random.randint(100, 10000),
            last_trade=round(mid_price, 2),
            volume=random.randint(10000, 1000000)
        )
    
    def generate_positions(self, num_positions: int = 50) -> List[Dict]:
        """
        Generate random positions for testing.
        
        Returns list of position dicts with:
        - symbol
        - qty (positive=LONG, negative=SHORT)
        - avg_cost
        - befday_qty
        - befday_avg_cost
        """
        # Use mix of real symbols and generated ones
        symbols = self.test_symbols[:min(num_positions, len(self.test_symbols))]
        
        # Add generated symbols if needed
        if num_positions > len(symbols):
            for i in range(len(symbols), num_positions):
                symbols.append(f"SIM{i:03d}")
        
        positions = []
        
        for symbol in symbols:
            # Random position size
            size_type = random.choice(['small', 'medium', 'large'])
            
            if size_type == 'small':
                qty = random.randint(200, 500)
            elif size_type == 'medium':
                qty = random.randint(500, 1500)
            else:  # large
                qty = random.randint(1500, 5000)
            
            # 70% LONG, 30% SHORT
            if random.random() < 0.7:
                qty = abs(qty)
            else:
                qty = -abs(qty)
            
            # Random avg cost
            avg_cost = random.uniform(10.0, 50.0)
            
            # BEFDAY qty (slight difference from current)
            befday_diff = random.randint(-200, 200)
            befday_qty = qty + befday_diff
            
            # BEFDAY avg cost (±5% from current)
            befday_avg_cost = avg_cost * random.uniform(0.95, 1.05)
            
            positions.append({
                'symbol': symbol,
                'qty': qty,
                'avg_cost': round(avg_cost, 2),
                'befday_qty': befday_qty,
                'befday_avg_cost': round(befday_avg_cost, 2),
                'current_value': round(abs(qty) * avg_cost, 2)
            })
        
        logger.info(f"[RandomDataGenerator] Generated {len(positions)} positions")
        
        return positions
    
    def generate_metrics(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Generate random Janall metrics for symbols.
        
        Returns dict of symbol -> metrics
        """
        metrics = {}
        
        for symbol in symbols:
            metrics[symbol] = {
                'fbtot': random.uniform(-2.0, 2.0),
                'sfstot': random.uniform(-2.0, 2.0),
                'gort': random.uniform(-5.0, 5.0),
                'sma63chg': random.uniform(-0.10, 0.10),
                'ask_sell_pahalilik': random.uniform(-0.20, 0.20),
                'bid_buy_ucuzluk': random.uniform(-0.20, 0.20),
                'final_thg': random.uniform(0.0, 10.0)
            }
        
        return metrics
    
    def reset_prices(self):
        """Reset price cache (for new simulation)"""
        self.prices.clear()
        logger.info("[RandomDataGenerator] Price cache reset")


# Global instance
_random_data_generator: Optional[RandomDataGenerator] = None


def get_random_data_generator() -> RandomDataGenerator:
    """Get global random data generator"""
    global _random_data_generator
    if _random_data_generator is None:
        _random_data_generator = RandomDataGenerator()
    return _random_data_generator
