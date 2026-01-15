
import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

@dataclass
class MarketData:
    symbol: str
    bid: float
    ask: float
    last: float
    bid_size: int
    ask_size: int
    volume: int
    timestamp: float

@dataclass
class TradeSignal:
    symbol: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    order_type: str  # 'LIMIT', 'MARKET'
    price: float
    reason: str
    edge: float  # Expected profit per share

class QuantBrain:
    def __init__(self):
        self.logger = logging.getLogger('quant_brain')
        self.logger.setLevel(logging.INFO)
        
        # Strategy Parameters
        self.min_spread_threshold = 0.05  # Minimum 5 cents to bother
        self.min_edge_threshold = 0.02    # Minimum 2 cents expected profit
        
        # Risk Parameters
        self.max_position_size = 5000     # Max dollars per trade
        
        # State
        self.fair_value_cache: Dict[str, float] = {}

    def calculate_fair_value(self, market_data: MarketData) -> float:
        """
        Calculates Fair Value based on Microstructure.
        
        In a perfect world, FairValue = (Bid + Ask) / 2.
        In reality, we use Volume Weighted Mid Price (VWMP) to detect pressure.
        
        Formula:
        Adj = (BidSize * Ask + AskSize * Bid) / (BidSize + AskSize)
        """
        # Safety checks
        if market_data.bid <= 0 or market_data.ask <= 0:
            return market_data.last if market_data.last > 0 else 0.0
            
        total_size = market_data.bid_size + market_data.ask_size
        
        if total_size == 0:
            return (market_data.bid + market_data.ask) / 2.0
            
        # Volume Weighted Mid Price (Micro-Price)
        # Note: If BidSize is huge, it pushes price UP towards Ask.
        vwmp = (market_data.bid * market_data.ask_size + market_data.ask * market_data.bid_size) / total_size
        
        return round(vwmp, 4)

    def get_market_maker_signal(self, market_data: MarketData) -> Optional[TradeSignal]:
        """
        Evaluates if we should provide liquidity (Market Making strategy).
        Target: Stocks with WIDE spreads.
        """
        # 1. Validation
        if market_data.bid <= 0 or market_data.ask <= 0:
            return None
            
        current_spread = market_data.ask - market_data.bid
        
        # 2. Filter: Is spread wide enough to be worth the risk?
        if current_spread < self.min_spread_threshold:
            return None
            
        # 3. Calculate Fair Value
        fair_val = self.calculate_fair_value(market_data)
        
        # 4. Strategy Logic:
        # We want to buy at Bid + epsilon (to be first in line)
        # We want to sell at Ask - epsilon
        
        # Check Skew: Where is FV relative to Mid?
        mid_point = (market_data.bid + market_data.ask) / 2
        
        # Ideal Buy Price: Just above current Bid (to capture spread)
        # But allow some margin of safety below Fair Value
        ideal_buy = market_data.bid + 0.01
        
        # Ideal Sell Price: Just below current Ask
        ideal_sell = market_data.ask - 0.01
        
        # Edge Calculation (Safety margin)
        # Buying at ideal_buy, assuming we exit at Fair Value
        buy_edge = fair_val - ideal_buy
        
        # Selling at ideal_sell, assuming we exit at Fair Value
        sell_edge = ideal_sell - fair_val
        
        # Decision
        # Prioritize the side with better edge
        if buy_edge > self.min_edge_threshold and buy_edge > sell_edge:
            return TradeSignal(
                symbol=market_data.symbol,
                action='BUY',
                order_type='LIMIT',
                price=ideal_buy,
                reason=f'Spread Capture (Spread: {current_spread:.2f}, Edge: {buy_edge:.2f})',
                edge=buy_edge
            )
            
        elif sell_edge > self.min_edge_threshold:
            return TradeSignal(
                symbol=market_data.symbol,
                action='SELL', # Short or Close Long
                order_type='LIMIT',
                price=ideal_sell,
                reason=f'Spread Capture (Spread: {current_spread:.2f}, Edge: {sell_edge:.2f})',
                edge=sell_edge
            )
            
        return None

    def analyze_liquidity_shock(self, market_data: MarketData, previous_data: MarketData) -> Optional[TradeSignal]:
        """
        Detects sudden large trades that dislocate price (Mean Reversion).
        """
        # To be implemented: requires history tracking
        return None
