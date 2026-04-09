"""
Market Making (MM) Analysis Engine
==================================

Strategic Agent for Preferred Stock Market Making.
Analyzes 22+ DOS Groups using high-fidelity Truth Tick data.

Analysis Components:
1. Truth Tick Filter: STRICT Round Lots (100, 200, 500) only.
2. OFI (Order Flow Imbalance): Directional imbalance of round lots.
3. Liquidity Pockets: Volume clustering.
4. Persistence Risk: Time-between-trades analysis for MM->PM transition.
5. Score-Based Aggressiveness: Final_BB_skor integration.

Output:
Strategic parameters for MM execution (Optimal Spread, Max Size, Danger Signals).
"""

import math
import statistics
import time
import os
from typing import Dict, Any, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime

from app.core.logger import logger
from app.live.hammer_client import HammerClient
from app.market_data.static_data_store import get_static_store
from app.core.fast_score_calculator import get_fast_score_calculator
from app.market_data.grouping import get_all_group_keys, resolve_group_key

class MMAnalysisEngine:
    """
    Market Making Analysis Engine.
    
    Generates strategic parameters for MM execution bots.
    Does NOT place orders.
    """
    
    # Constants
    MIN_SPREAD_GOAL = 0.05
    MM_EXIT_BUFFER = 0.07  # Buy P, Sell P + 0.07
    
    # User-defined thresholds
    ROUND_LOT_SIZE = 100
    DANGER_VOLATILITY_MULTIPLIER = 1.5
    MM_HOLD_LIMIT_SECONDS = 3 * 60 * 60  # 3 Hours
    
    def __init__(self, hammer_client: Optional[HammerClient] = None):
        if hammer_client:
            self.hammer = hammer_client
        else:
            from app.config.settings import settings
            self.hammer = HammerClient(
                host=settings.HAMMER_HOST,
                port=settings.HAMMER_PORT,
                password=settings.HAMMER_PASSWORD,
                account_key=settings.HAMMER_ACCOUNT_KEY
            )
        
        # Initialize Static Data Store
        from app.market_data.static_data_store import get_static_store, initialize_static_store
        self.static_store = get_static_store()
        if not self.static_store:
            self.static_store = initialize_static_store()
        
        self.score_calc = get_fast_score_calculator()
        
        # Ensure static store loaded
        if self.static_store and not self.static_store.is_loaded():
            self.static_store.load_csv()
            
    def analyze_all_groups(self, lookback: int = 3000, group_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Analyze all 22+ groups/subgroups.
        
        Returns list of analysis results (one dict per symbol).
        """
        if not self.hammer.is_connected():
            logger.info("Reconnecting existing Hammer client for Historical Data...")
            if not self.hammer.connect():
                logger.error("Failed to connect to Hammer")
                return []
        
        all_results = []
        
        # Get all groups
        groups = get_all_group_keys(self.static_store)
        total_symbols = sum(len(syms) for syms in groups.values())
        logger.info(f"Starting MM Analysis for {len(groups)} groups ({total_symbols} symbols)")
        
        # Prepare output dir for partial saves
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "reports")
        os.makedirs(output_dir, exist_ok=True)
        partial_file = os.path.join(output_dir, f"MM_Strategy_Partial_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")
        
        processed = 0
        for group_name, symbols in groups.items():
            if group_filter and group_name != group_filter:
                continue
                
            for symbol in symbols:
                try:
                    result = self.analyze_symbol(symbol, group_name, lookback)
                    if result:
                        all_results.append(result)
                        
                        # Save partial every 10 results
                        if len(all_results) % 10 == 0:
                             import pandas as pd
                             pd.DataFrame(all_results).to_csv(partial_file, index=False)
                    
                    processed += 1
                    if processed % 10 == 0:
                        logger.info(f"Processed {processed}/{total_symbols} symbols... (Found {len(all_results)} valid)")
                        
                    # Rate limiting to prevent Hammer overload
                    time.sleep(0.1)
                        
                except Exception as e:
                    logger.error(f"Error analyzing {symbol}: {e}", exc_info=True)
        
        # Final save of partial
        if all_results:
             import pandas as pd
             pd.DataFrame(all_results).to_csv(partial_file, index=False)
             
        return all_results

    def _get_cache_path(self, symbol: str) -> str:
        return os.path.join(os.getcwd(), "data", "cache", f"ticks_{symbol}.json")
        
    def _load_ticks_from_cache(self, symbol: str) -> Optional[List[Dict]]:
        path = self._get_cache_path(symbol)
        if os.path.exists(path):
            try:
                # Check age (e.g., 4 hours)
                mtime = os.path.getmtime(path)
                if time.time() - mtime < 14400: # 4 hours
                    with open(path, 'r') as f:
                        return json.load(f)
            except:
                pass
        return None
        
    def _save_ticks_to_cache(self, symbol: str, ticks: List[Dict]):
        try:
            cache_dir = os.path.join(os.getcwd(), "data", "cache")
            os.makedirs(cache_dir, exist_ok=True)
            path = self._get_cache_path(symbol)
            with open(path, 'w') as f:
                json.dump(ticks, f)
        except:
            pass

    def analyze_symbol(self, symbol: str, group: str, lookback: int = 3000) -> Optional[Dict[str, Any]]:
        """
        1. Fetch Ticks (Hammer) - With Cache Support
        2. Filter (Round Lots)
        3. Analyze (Persistence, OFI, Clustering)
        4. Return Metrics
        """
        
        # Try Cache First if not in market hours or just to save time
        # For now, always try cache first for speed in dev loop
        raw_ticks = self._load_ticks_from_cache(symbol)
        
        if not raw_ticks:
            # Fallback Loop for Reliability
            lookback_steps = [lookback, 130] 
            timeout_per_step = 3.0 
            
            for step_lookback in lookback_steps:
                try:
                    # Rate Limit
                    time.sleep(0.1) 
                    
                    # Fetch
                    ticks_resp = self.hammer.get_ticks(symbol, lastFew=step_lookback, tradesOnly=True, timeout=timeout_per_step)
                    raw_ticks = ticks_resp.get('data', []) if ticks_resp else []
                    
                    if raw_ticks and len(raw_ticks) > 0:
                        # Save to cache
                        self._save_ticks_to_cache(symbol, raw_ticks)
                        break # Success
                        
                    time.sleep(0.1) 
                    
                except Exception as e:
                    logger.debug(f"MMEngine: Error fetching {symbol} (LB={step_lookback}): {e}")
                    continue

        if not raw_ticks:
            # logger.warning(f"Failed to get ticks for {symbol} after all attempts") # Original line, now handled by new logger.debug
            return None

        # 2. Filter: Round Lots Only (Strict)
        # AND Filter: Last 3 Days Only
        
        # Calculate 3 days ago timestamp (ms)
        three_days_ago_sec = time.time() - (3 * 24 * 60 * 60)
        
        valid_ticks = []
        
        for t in raw_ticks:
            # Map keys (Hammer returns brief keys: s=size, t=time, p=price)
            size = t.get('s', 0) if 's' in t else t.get('size', 0)
            price = t.get('p', 0.0) if 'p' in t else t.get('price', 0.0)
            ts_raw = t.get('t', 0) if 't' in t else t.get('time', 0)
            
            # Enrich dict for easier usage later
            t['size'] = size
            t['price'] = price
            t['time'] = ts_raw
            
            # Check Round Lot
            if not self._is_round_lot(size):
                continue
                
            # Parse Timestamp
            ts = 0.0
            try:
                if isinstance(ts_raw, str):
                    # Handle ISO format: 2026-01-08T20:47:37.030
                    # fromisoformat requires consistent format, if fails try other ways
                    ts = datetime.fromisoformat(ts_raw).timestamp()
                else:
                    ts = float(ts_raw)
                    # Auto-detect ms vs sec
                    if ts > 30000000000:
                        ts = ts / 1000.0
            except:
                continue
            
            # Store normalized timestamp (seconds)
            t['ts_norm'] = ts
            
            # Filter: recent 3 days
            if ts < three_days_ago_sec:
                continue
                
            valid_ticks.append(t)
        
        round_lot_ticks = valid_ticks
        
        if len(round_lot_ticks) < 1:
            # logger.debug(f"{symbol}: Insufficient round lot data")
            return None
            
        # Sort Ticks by Time for Analysis
        round_lot_ticks.sort(key=lambda x: x.get('ts_norm', 0))

        # --- EXECUTION STRATEGIST LOGIC ---

        # 1. Gather Market Context from Latest Tick
        latest_tick = round_lot_ticks[-1]
        last_price = latest_tick.get('price', 0)
        
        # Hammer ticks usually have 'b' (bid) and 'a' (ask) if quote data was attached
        bid = latest_tick.get('b', 0.0) or last_price
        ask = latest_tick.get('a', 0.0) or last_price
        spread = ask - bid if (ask > 0 and bid > 0) else 0.01

        # Calculate Statistics
        avg_inter_arrival, max_inter_arrival = self._calc_time_stats(round_lot_ticks)
        persistence_risk_score = self._calc_persistence_risk(avg_inter_arrival)
        ofi_score = self._calc_ofi(round_lot_ticks)
        
        # 2. Determine Execution Mode (Predator vs Shadow vs Vulture vs Zombie)
        # Shadow: Tight spread (<0.15) AND Liquid (Interval < 600s or ADV high)
        # Predator: Low Liquidity AND Slow
        # Vulture: Very Slow (Ghost) but Wide Spread
        # Zombie: Very Slow (Ghost) and Tight Spread
        
        # 2. Determine Execution Mode (Predator vs Shadow vs Vulture vs Zombie)
        
        # Simplified ADV check if available
        adv = float(self.static_store.get_static_data(symbol).get('AVG_ADV', 0) or 0)
        
        execution_mode = "NORMAL"
        profit_target = "0.10"
        strategy_desc = "Balanced approach."
        max_size = 500 # Default increased to 500
        
        # Classify
        if spread <= 0.15 and (avg_inter_arrival < 600 or adv > 30000):
            execution_mode = "SHADOW"
            profit_target = "0.06" # Min profit optimization
            max_size = 1000 # Scale up for Shadow
            strategy_desc = "Front-run inside spread, fast churn."
        elif avg_inter_arrival > 10800: # > 3 Hours (Ghost Territory)
            if spread > 0.50:
                execution_mode = "VULTURE" # Opportunity
                profit_target = "0.40+"
                max_size = 200 # Cap Vulture at 200
                strategy_desc = "Deep Stalking. Very Illiquid but Juicy Spread."
            else:
                execution_mode = "ZOMBIE" # Danger
                profit_target = "N/A"
                max_size = 0
                strategy_desc = "AVOID. Dead money risk."
        elif spread >= 0.40 or avg_inter_arrival > 3600:
            execution_mode = "PREDATOR"
            profit_target = "0.20-0.25"
            max_size = 500
            strategy_desc = "Sit and wait for fat tail. Do not front-run for cents."

        # 3. Tactical Overrides
        
        # A. Adverse Selection (Shadow Only) - 5 TICK RULE
        # Logic: If last 5 ticks cluster around Bid or are decreasing, it's dumping.
        tactical_override = "NONE"
        if execution_mode == "SHADOW" and len(round_lot_ticks) >= 5:
            last_5 = round_lot_ticks[-5:]
            prices = [t.get('price', 0) for t in last_5]
            # Check for consistent pressure on Bid side (dumping)
            # If price is consistently <= mean of prices (flat or down) relative to spread
            # Simple heuristic: strictly non-increasing check over 5 ticks
            is_dumping = all(prices[i] >= prices[i+1] for i in range(len(prices)-1))
            
            # Alternative: Check distance to Bid. If we had Bid history it would be precise.
            # Using price action: If 5 ticks are effectively 'hitting' the same low level.
            # Let's stick to Non-Increasing Price sequence for dumping detection.
            if is_dumping:
                 tactical_override = "ADVERSE_SELECTION_PROTECT (5-Tick Rule)"
                 strategy_desc += " | ⚠️ 5-TICK DUMP DETECTED (Pull Bids)"

        # B. Mid-Point Snatch (Shadow Only)
        if execution_mode == "SHADOW" and spread > 0.20:
             if tactical_override == "NONE":
                 tactical_override = "MID_POINT_ICEBERG"
                 strategy_desc += " | 🧊 ICEBERG MID-POINT"

        # 4. Gem Logic Integration (Short-Sell & Asymmetry)
        davg = 0.0
        gem_size_adj = "NEUTRAL"
        initial_action = "BUY_BID" # Default
        group_vol_alert = False
        
        try:
            import json
            from app.core.redis_client import get_redis_client
            redis_client = get_redis_client().sync
            
            gem_key = f"gem:inspect:{symbol}"
            gem_json = redis_client.get(gem_key)
            if gem_json:
                gem_data = json.loads(gem_json)
                current_data = gem_data.get('current', {})
                davg = current_data.get('davg') or 0.0
                grp_avg_chg = current_data.get('group_avg_change') or 0.0
                
                # Asymmetric Sizing & Directional Logic
                # EXPENSIVE: Davg > 0.12 (Tighter threshold)
                if davg > 0.12:
                    if ofi_score < 0:
                        # Expensive + Selling Pressure = SHORT SETUP
                        gem_size_adj = "SHORT_FOCUS"
                        initial_action = "SHORT_ASK_FIRST"
                        strategy_desc += " | 📉 SHORT-SELL OVERLAY (Davg>0.12 + OFI-)"
                    else:
                        gem_size_adj = "ASYM_SELL_HEAVY (Bid 100 / Ask Max)"
                
                # CHEAP: Davg < -0.13 (Tighter threshold)
                elif davg < -0.13:
                    if ofi_score > 0:
                         # Cheap + Buying Pressure = LONG SETUP
                         gem_size_adj = "LONG_FOCUS"
                         initial_action = "LONG_BID_FIRST"
                         strategy_desc += " | 📈 LONG-BUY OVERLAY (Davg<-0.13 + OFI+)"
                    else:
                         gem_size_adj = "ASYM_BUY_HEAVY (Bid Max / Ask 100)"
                
                if abs(grp_avg_chg) > 0.05:
                    group_vol_alert = True
        except Exception:
            pass

        # 5. Final Assembly
        optimal_spread = 0.05
        if execution_mode in ["PREDATOR", "VULTURE"]:
            optimal_spread = 0.20
        
        if group_vol_alert:
             optimal_spread *= 1.5
             strategy_desc += " | GROUP VOL ALERT"

        # Trend Status (Simplified for Summary)
        # ... kept existing logic or simplified ...
        trend_status = "RANGE" 
        # (re-using previous calculation if not overwritten, but for clarity:)
        if len(round_lot_ticks) >= 5:
             # fast re-check
             last_5_p = [t.get('price', 0) for t in round_lot_ticks[-5:]]
             if all(last_5_p[i] < last_5_p[i+1] for i in range(4)): trend_status = "UP_LADDER"
             elif all(last_5_p[i] > last_5_p[i+1] for i in range(4)): trend_status = "DOWN_LADDER"

        # PM Transition
        pm_transition_plan = "NORMAL"
        if persistence_risk_score > 0.7:
            pm_transition_plan = "STRICT_3H_EXIT"

        return {
            "Symbol": symbol,
            "Group": group,
            "Round_Lots_Count": len(round_lot_ticks),
            "Execution_Mode": execution_mode,
            "Initial_Action": initial_action, # NEW
            "Profit_Target": profit_target,
            "Max_Size": max_size,
            "Tactical_Override": tactical_override,
            "Strategy_Desc": strategy_desc,
            "Trend_Status": trend_status,
            "Gem_Davg": round(davg, 3),
            "Size_Adjustment": gem_size_adj,
            "Group_Vol_Alert": group_vol_alert,
            "Avg_Inter_Arrival_Sec": round(avg_inter_arrival, 0),
            "Persistence_Risk_Score": round(persistence_risk_score, 2),
            "OFI_Score": round(ofi_score, 2),
            "Optimal_Spread": round(optimal_spread, 2),
            "PM_Transition_Plan": pm_transition_plan,
            "ADV": adv
        }

    def _is_round_lot(self, size: float) -> bool:
        """Strict Round Lot: Multiples of 100"""
        return size >= 100 and size % 100 == 0

    def _calc_time_stats(self, ticks: List[Dict]) -> Tuple[float, float]:
        """Calculate average and max time between trades in seconds"""
        if len(ticks) < 2:
            return 0.0, 0.0
            
        # Ticks are already sorted by 'ts_norm' in analyze_symbol
        
        gaps = []
        for i in range(1, len(ticks)):
            t1 = ticks[i-1].get('ts_norm', 0)
            t2 = ticks[i].get('ts_norm', 0)
            
            gap = t2 - t1
            if gap > 0:
                gaps.append(gap)
                
        if not gaps:
            return 0.0, 0.0
            
        avg_gap = statistics.mean(gaps)
        max_gap = max(gaps)
        return avg_gap, max_gap

    def _calc_persistence_risk(self, avg_inter_arrival: float) -> float:
        """
        Calculate risk of holding a position > 3 hours.
        Return 0.0 (Low Risk) to 1.0 (High Risk).
        """
        # If trades happen every 5 mins (300s) -> Low Risk
        # If trades happen every 2 hours (7200s) -> High Risk
        
        # Sigmoid-ish mapping
        # 30 mins (1800s) -> 0.5
        # 3 hours (10800s) -> 1.0
        
        risk = avg_inter_arrival / 3600.0 # Risk per hour of gap
        return min(risk, 1.0)

    def _calc_ofi(self, ticks: List[Dict]) -> float:
        """
        Calculate Order Flow Imbalance (-1.0 to +1.0).
        Based on tick direction logic (Price change or Aggressor side).
        
        Since we have filtered Trade data, we infer direction from Price Change 
        relative to previous trade (Tick Test).
        """
        buy_vol = 0
        sell_vol = 0
        
        # Ticks are already sorted
        
        for i in range(1, len(ticks)):
            prev = ticks[i-1]
            curr = ticks[i]
            
            p1 = prev.get('price', 0)
            p2 = curr.get('price', 0)
            size = curr.get('size', 0)
            
            if p2 > p1:
                buy_vol += size
            elif p2 < p1:
                sell_vol += size
            else:
                pass
                
        total = buy_vol + sell_vol
        if total == 0:
            return 0.0
            
        return (buy_vol - sell_vol) / total
