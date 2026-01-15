"""
app/analysis/ofi_engine.py

Order Flow Imbalance (OFI) Engine
Calculates the buy/sell pressure based on the changes in the L1 Order Book (Best Bid/Ask Price & Size).

Formula:
  e_n = I(P_n^b >= P_{n-1}^b) * q_n^b - I(P_n^b <= P_{n-1}^b) * q_{n-1}^b
        - I(P_n^a <= P_{n-1}^a) * q_n^a + I(P_n^a >= P_{n-1}^a) * q_{n-1}^a

Simplified Logic:
  - Bid Higher -> Add Bid Size (+)
  - Bid Lower -> Remove Prev Bid Size (-)
  - Bid Same -> Add (Bid Size - Prev Bid Size) (+ or -)
  
  - Ask Lower -> Add Ask Size (as Selling Pressure -> -)
  - Ask Higher -> Remove Prev Ask Size (Less Selling -> +)
  - Ask Same -> Add (Prev Ask Size - Ask Size) (+ or -)

  OFI = Delta_Bid_Flow - Delta_Ask_Flow

Storage:
  Redis Key: `ofi:score:{symbol}` (Float)
"""

import time
import json
from typing import Dict, Optional
from app.core.redis_client import get_redis_client
from app.core.logger import logger

class OFIEngine:
    _instance = None
    
    # Cache to store previous state: {symbol: {'bid': price, 'bid_size': size, 'ask': price, 'ask_size': size, 'ts': timestamp}}
    _state_cache: Dict[str, Dict] = {}

    def __init__(self):
        self.redis = get_redis_client().sync
        
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def process_tick(self, symbol: str, bid: float, bid_size: int, ask: float, ask_size: int, timestamp: float) -> float:
        """
        Calculate OFI for a single tick update.
        Returns the instantaneous OFI contribution of this tick.
        Updates the running OFI score in Redis.
        """
        prev = self._state_cache.get(symbol)
        
        # Initialize state if first tick
        if prev is None:
            self._state_cache[symbol] = {
                'bid': bid, 'bid_size': bid_size,
                'ask': ask, 'ask_size': ask_size,
                'ts': timestamp
            }
            return 0.0

        # DATA CLEANING: Skip if bad data (0 prices)
        if bid <= 0 or ask <= 0:
            return 0.0

        prev_bid = prev['bid']
        prev_bid_size = prev['bid_size']
        prev_ask = prev['ask']
        prev_ask_size = prev['ask_size']

        # --- CALCULATE BID FLOW (Buying Pressure) ---
        bid_flow = 0.0
        if bid > prev_bid:
            # Price moved up -> New buying interest at higher price
            bid_flow = bid_size
        elif bid < prev_bid:
            # Price moved down -> Buyers retreated
            bid_flow = -prev_bid_size
        else:
             # Price same -> Change in size
            bid_flow = bid_size - prev_bid_size

        # --- CALCULATE ASK FLOW (Selling Pressure) ---
        # Note: Ask Flow is usually subtracted from Total Flow
        # If Ask moves down (Sellers aggressive), AskFlow should be POSITIVE (representing selling pressure)
        # We will subtract AskFlow from BidFlow later.
        
        ask_flow = 0.0
        if ask < prev_ask:
            # Price moved down -> Sellers aggressive
            ask_flow = ask_size
        elif ask > prev_ask:
            # Price moved up -> Sellers retreated
            ask_flow = -prev_ask_size
        else:
            # Price same -> Change in size
            ask_flow = ask_size - prev_ask_size

        # Net Order Flow Imbalance
        # Positive = Buying Pressure
        # Negative = Selling Pressure
        ofi_contribution = bid_flow - ask_flow

        # --- UPDATE REDIS ---
        # We can store:
        # 1. Instantaneous OFI (very volatile)
        # 2. Cumulative OFI (Trend)
        # 3. Moving Average OFI (e.g. 1-min)
        
        # User requested "Score". Let's use a decay factor or simple accumulation reset daily.
        # For now, let's keep a simplistic Cumulative Day OFI.
        # But for 'current' state, maybe a rolling window is better?
        # Let's start with CUMULATIVE OFI for the day.
        
        # Update Cache
        self._state_cache[symbol] = {
            'bid': bid, 'bid_size': bid_size,
            'ask': ask, 'ask_size': ask_size,
            'ts': timestamp
        }
        
        # Increment Redis
        try:
            self.redis.incrbyfloat(f"ofi:score:{symbol}", ofi_contribution)
        except Exception as e:
            logger.error(f"Error updating OFI redis: {e}")
            
        return ofi_contribution

def get_ofi_engine():
    return OFIEngine.get_instance()
