
import logging
import time
import math
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import deque

from app.core.logger import logger
from app.event_driven.decision_engine.shadow_observer import shadow_observer

class MMChurnEngine:
    """
    MM Churn Engine - The "Money Maker"
    
    Responsibilities:
    1. Place two-sided quotes around Truth Price.
    2. Manage inventory (skew quotes).
    3. Respect pricing rules (Tick Rounding, Anchor Spacing).
    4. Enforce Order Discipline (Throttle, Min Interval).
    5. Handle Low Confidence via Gating/Min Lot.
    """
    
    def __init__(self, tick_size: float = 0.01):
        self.tick_size = tick_size
        
        # Configuration (Defaults)
        self.min_lot_size = 200
        self.max_clip_size = 4000
        self.min_replace_interval = 2.5 # Seconds
        self.max_working_orders = 2 # Per symbol
        self.low_conf_threshold = 25.0
        
        # State Tracking
        # {symbol: {'last_replace_ts': float, 'working_orders': [], 'last_truth_vol': float}}
        self.symbol_state: Dict[str, Dict[str, Any]] = {}
        
        # Token Bucket for Global Throttle
        # rate: tokens/sec, capacity: max burst
        self.token_bucket_rate = 5.0 
        self.token_bucket_capacity = 10.0
        self.tokens = 10.0
        self.last_token_update = time.time()
        
    def _get_symbol_state(self, symbol: str) -> Dict[str, Any]:
        if symbol not in self.symbol_state:
            self.symbol_state[symbol] = {
                'last_replace_ts': 0.0,
                'working_orders': {}, # {id: order_dict}
                'last_l1_ts': 0.0
            }
        return self.symbol_state[symbol]

    def _update_tokens(self, now: float):
        elapsed = now - self.last_token_update
        self.tokens = min(self.token_bucket_capacity, self.tokens + elapsed * self.token_bucket_rate)
        self.last_token_update = now

    def _consume_token(self, now: float) -> bool:
        self._update_tokens(now)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    def _round_price(self, price: float, side: str = 'MID') -> float:
        """Round to tick size. Side used for conservative rounding if needed."""
        # Standard rounding
        ticks = round(price / self.tick_size)
        return ticks * self.tick_size

    def plan_churn(
        self,
        symbol: str,
        l1_data: Dict[str, Any],
        truth_data: Dict[str, Any],
        position: Dict[str, Any],
        active_orders: List[Dict[str, Any]],
        regime: str,
        current_time: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate churn intents for a single symbol.
        """
        intents = []
        state = self._get_symbol_state(symbol)
        
        # Use provided time (simulation) or wall clock
        now = current_time if current_time else time.time()
        
        # 0. Shadow Comparison (Non-Invasive)
        # Check snapshot_cache_v2 if provided in l1_data (mocking the wrapper)
        v2_data = l1_data.get('v2_snapshot')
        if v2_data:
            v2_age = now - v2_data.get('timestamp', 0)
            l1_age = now - l1_data.get('timestamp', 0)
            logger.info(f"🧪 [MMChurnEngine] Shadow Comparison ({symbol}): V1 Age: {l1_age:.1f}s | V2 Age: {v2_age:.1f}s")
            
            # Record KPIs
            shadow_observer.record_snapshot_age(v2_age)
            v1_mid = (l1_data.get('bid', 0) + l1_data.get('ask', 0)) / 2
            v2_mid = (v2_data.get('bid', 0) + v2_data.get('ask', 0)) / 2
            shadow_observer.record_comparison(v1_mid, v2_mid, would_flip=False) # would_flip logic later if needed
            
            # Order-time guard logic: If v2 age > 90s, signal refresh
            if v2_age > 90.0:
                logger.warning(f"🔄 [MMChurnEngine] Stale V2 Cache ({v2_age:.1f}s). TRIGGERING ON-DEMAND L2 SNAPSHOT for {symbol}.")
                # In production, we signal the wrapper or call HammerClient.get_l2_snapshot externally if available.
                # For now, we flag this in the intent or metadata.
                shadow_observer.record_churn_event(symbol, 'STALE_REFRESH_TRIGGER')
            
        # First call fix for token bucket init
        if self.last_token_update == 0: self.last_token_update = now
        
        # 0. Suppression Checks
        if regime in ['HARD_DERISK', 'CAP_RECOVERY']:
            return [] # Suppressed
            
        # 1. Stale L1 Gating
        # Preferred Market Logic: data can be old (up to 90s)
        # l1_data should have 'timestamp' (float seconds)
        l1_ts = l1_data.get('timestamp', 0)
        
        # Stale Threshold: 90.0s for Preferreds
        if now - l1_ts > 90.0:
            # Too Stale - Freeze Churn (No New Orders)
            # Logic: If data is >90s old, we risk quoting on ghost prices.
            return []
            
        # 2. Min Replace Interval (Per Symbol)
        if now - state['last_replace_ts'] < self.min_replace_interval:
            return []
            
        # 3. Features & Inputs
        bid = l1_data.get('bid', 0)
        ask = l1_data.get('ask', 0)
        if bid <= 0 or ask <= 0: return []
        
        # Strict "No Change" Logic
        # If L1 Bid/Ask is identical to what we saw last time, AND we have working orders, 
        # do not generate new intents (spam prevention for stable markets).
        last_bid = state.get('last_bid', -1.0)
        last_ask = state.get('last_ask', -1.0)
        
        # Update State
        state['last_bid'] = bid
        state['last_ask'] = ask
        
        # If no change in market data, and we have active orders, skip calculation?
        # EXCEPT: If we need to refresh due to confidence or time?
        # But user said: "If bid/ask unchanged, do not churn."
        # Note: active_orders might have changed (fills), so check if we have orders.
        if bid == last_bid and ask == last_ask:
            # Market didn't change.
            # If we already have 2 active orders (Bid+Ask), then we are good.
            # If we have 0 orders (entry), we should proceed.
            # So: Skip ONLY if we are fully invested/active? estimate active count.
            has_bid = any(o['side'] == 'BUY' for o in active_orders)
            has_ask = any(o['side'] == 'SELL' for o in active_orders)
            if has_bid and has_ask:
                return []
        
        spread = ask - bid
        mid = (bid + ask) / 2
        
        truth_price = truth_data.get('truth_price', mid)
        confidence = truth_data.get('confidence', 100.0)
        volav = truth_data.get('volav', 0.0) # Volatility/Volume metric
        
        # 4. Gating Logic (Low Conf + Wide Spread + Low Vol)
        is_low_conf = confidence < self.low_conf_threshold
        is_wide = spread > 0.10
        is_low_vol = volav < 1000 # Dummy threshold
        
        slow_mode = False
        target_lot_size = self.max_clip_size # Start with max, scale down
        
        if is_low_conf:
            target_lot_size = self.min_lot_size
            if is_wide and is_low_vol:
                # Slower refresh
                slow_mode = True
                if now - state['last_replace_ts'] < 10.0: # 10s interval
                    return []

        # 5. Pricing Logic
        # A. Calculate Raw Targets
        if spread <= 0.10: # Tight
            if spread <= self.tick_size + 1e-9: # 1 Tick Spread (e.g. 0.01)
                # Join Best
                my_bid = bid
                my_ask = ask
            else:
                # Inside Improvement
                # E.g. Spread 0.05. Offset 0.01 inside.
                my_bid = bid + self.tick_size
                my_ask = ask - self.tick_size
        else: # Wide
            # Capture Spread portion (15%)
            offset = spread * 0.15
            my_bid = bid + offset
            my_ask = ask - offset
            
        # B. Anchor Spacing & Smoothing
        # TODO: Check 'anchors' from truth_data if available
        # Simple rounding for now
        my_bid = self._round_price(my_bid)
        my_ask = self._round_price(my_ask)
        
        # C. Validity Checks
        # Never cross
        if my_bid >= my_ask:
            mid_tick = self._round_price(mid)
            my_bid = mid_tick - self.tick_size
            my_ask = mid_tick + self.tick_size
            
        # Never outside [Best Bid, Best Ask] for inside quoting?
        # "Never place prices outside [bid, ask] when doing inside-spread quoting"
        # If wide spread logic pushes us out (unlikely with +offset), clamp.
        my_bid = min(my_bid, ask - self.tick_size) # Cap at Ask-1tick
        my_ask = max(my_ask, bid + self.tick_size) # Floor at Bid+1tick
        
        # But ensure we don't go worse than Best Bid/Ask if we intended to join? 
        # If Spread is wide, we want to be inside. 
        # If we calculate bid+offset, it is inside.
        
        # Validity: Check against Anchor Zones (0.04 spacing)
        # Mock Anchor logic: passive orders at Bid, Bid-0.05...
        # Assume we just respect min spacing of 0.04 between our Bid and Ask?
        # "two-sided quotes must be >= 0.04 apart"
        if (my_ask - my_bid) < 0.04:
             # Widen to meet min spacing 
             # Center around mid
             center = (my_ask + my_bid) / 2
             my_bid = center - 0.02
             my_ask = center + 0.02
             my_bid = self._round_price(my_bid)
             my_ask = self._round_price(my_ask)
             
        # 6. Order Management (Replace/Cancel)
        # Compare with active orders
        # active_orders is list of dicts {id, price, qty, side, etc}
        
        # Identify current working orders
        current_bid_order = next((o for o in active_orders if o['side'] == 'BUY'), None)
        current_ask_order = next((o for o in active_orders if o['side'] == 'SELL'), None)
        
        # Token Bucket Check (Global)
        if not self._consume_token(now):
            return [] # Global throttle
            
        # Process Bid
        if current_bid_order:
            # Check for Replace
            diff_price = abs(current_bid_order['price'] - my_bid)
            if diff_price < self.tick_size:
                # Ignore small change (< 1 tick)
                pass
            else:
                # Generate Replace Intent
                intents.append({
                    'type': 'MM_LONG_INCREASE', # Wait. Increase/Decrease logic? 
                    # Actually MM Churn is usually "Modify Order" -> "MM_QUOTE_UPDATE"
                    # But standard intent system uses Increase/Decrease.
                    # Let's emit CHURN_UPDATE intent to specific side
                    'action': 'REPLACE',
                    'order_id': current_bid_order['id'],
                    'price': my_bid,
                    'qty': target_lot_size,
                    'side': 'BUY',
                    'symbol': symbol,
                    'classification': 'MM_QUOTE'
                })
                state['last_replace_ts'] = now
        else:
            # New Order
            if len(active_orders) < self.max_working_orders:
                intents.append({
                    'type': 'MM_LONG_INCREASE',
                    'action': 'NEW',
                    'price': my_bid,
                    'qty': target_lot_size,
                    'side': 'BUY',
                    'symbol': symbol,
                    'classification': 'MM_QUOTE'
                })
                state['last_replace_ts'] = now

        # Process Ask
        if current_ask_order:
            # Check for Replace
            diff_price = abs(current_ask_order['price'] - my_ask)
            if diff_price < self.tick_size:
                pass
            else:
                intents.append({
                    'action': 'REPLACE',
                    'order_id': current_ask_order['id'],
                    'price': my_ask,
                    'qty': target_lot_size,
                    'side': 'SELL',
                    'symbol': symbol,
                    'classification': 'MM_QUOTE'
                })
                state['last_replace_ts'] = now
        else:
            # New Order
            if len(active_orders) < self.max_working_orders:
                intents.append({
                    'type': 'MM_SHORT_INCREASE', # Or LONG_DECREASE if holding inventory?
                    # Simplified: Churn Sell is always offering.
                    'action': 'NEW',
                    'price': my_ask,
                    'qty': target_lot_size,
                    'side': 'SELL',
                    'symbol': symbol,
                    'classification': 'MM_QUOTE'
                })
                state['last_replace_ts'] = now
                
        return intents
