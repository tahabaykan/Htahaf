"""
app/analysis/genobs_service.py

Genobs Service
Aggregates data from various subsystems to provide a consolidated view for 'Genobs' (General Observation) Module.

Data Sources:
  - Redis: market_context (Latest Price, Bid, Ask)
  - Redis: truth_ticks:inspect (Truth Tick, Temporal Volav)
  - Redis: janall:metrics (Fbtot, Sfstot, SMI)
  - Redis: ofi:score (Order Flow Imbalance)
  - Static: Universe Data (Group, ADV)
"""

import json
import time
from typing import List, Dict, Any, Optional
from app.core.redis_client import get_redis_client
from app.core.logger import logger
from app.market_data.static_data_store import get_static_store

class GenobsService:
    def __init__(self):
        self.redis = get_redis_client().sync
        self.static_store = get_static_store()
        
    def get_genobs_data(self) -> List[Dict[str, Any]]:
        """
        Fetch and aggregate all data for Genobs table.
        """
        # Ensure static store is loaded
        if not self.static_store or not self.static_store.is_loaded():
            from app.market_data.static_data_store import initialize_static_store
            initialize_static_store()
            self.static_store = get_static_store()
            
        # Try to fetch universe from Redis first (populated by MarketContextWorker)
        universe_dict = {}
        universe_json = self.redis.get("market_context:universe")
        
        if universe_json:
            universe_dict = json.loads(universe_json)
        else:
            # Fallback to static store direct access
            if self.static_store and self.static_store.is_loaded():
                universe_dict = self.static_store.data
                
        if not universe_dict:
            return []
        
        results = []
        
        # We can use pipeline to fetch data in bulk for performance
        # But for 450 symbols, iteratively might be slow.
        # Let's simple-loop first, optimize with pipeline if needed.
        
        # Optimization: Fetch massive keys in batches if needed.
        # For now, simplistic approach.
        
        for symbol, info in universe_dict.items():
            try:
                # 1. Static Data
                group = info.get('group', 'N/A')
                cgrup = info.get('cgrup', 'N/A')
                
                # Default to 0 if not found, to avoid 50000 dummy
                adv = 0
                static_data = self.static_store.get_static_data(symbol)
                if static_data:
                    adv = static_data.get('AVG_ADV', 0)
                
                if adv == 0 or adv == 50000:
                   # Try one more time from info if static failed, but avoid 50000 if possible
                   # Actually info['ADV'] is likely 50000 from worker.
                   # Let's trust static store's AVG_ADV as primary.
                   pass
                
                # 2. Market Context (Live Data)
                # 2. Market Context (Live Data)
                # 💀 LIFELESS MODE INTEGRATION
                # If DataFabric is in Lifeless Mode, we MUST use it to see the "Shuffled" prices.
                # Genobs normally reads raw Redis 'market_context', which is NOT updated by the shuffle (shuffle is RAM-only).
                
                valid_ctx = None
                is_lifeless = False
                
                try:
                    from app.core.data_fabric import get_data_fabric
                    fabric = get_data_fabric()
                    if fabric and fabric.is_lifeless_mode():
                        is_lifeless = True
                        snap = fabric.get_fast_snapshot(symbol)
                        if snap:
                            valid_ctx = {
                                'bid': snap.get('bid', 0),
                                'ask': snap.get('ask', 0),
                                'last': snap.get('last', 0),
                                'vol': snap.get('volume', 0),
                                'ts': snap.get('timestamp', 0),
                                'prev_close': snap.get('prev_close', 0)
                            }
                except Exception as e:
                    # logger.warning(f"Genobs Lifeless check failed: {e}")
                    pass

                if not is_lifeless:
                    # NORMAL MODE: Read from Redis history (market_context:{symbol}:5m)
                    # WEEKEND MODE: Search for the last VALID data (bid>0, ask>0) in the last 100 entries
                    
                    # Fetch top 50 entries (usually enough to cover a weekend of idle logging or find Friday)
                    ctx_list = self.redis.lrange(f"market_context:{symbol}:5m", 0, 99)
                    
                    for ctx_json in ctx_list:
                        try:
                            c = json.loads(ctx_json)
                            if c.get('bid', 0) > 0 and c.get('ask', 0) > 0:
                                valid_ctx = c
                                break
                        except:
                            continue
                    
                    # If no valid data found, fallback to latest (even if 0)
                    if not valid_ctx and ctx_list:
                        try:
                            valid_ctx = json.loads(ctx_list[0])
                        except:
                            pass

                bid = 0.0
                ask = 0.0
                last = 0.0
                vol = 0
                prev_close = info.get('prev_close', 0)
                ts = 0
                
                if valid_ctx:
                    bid = valid_ctx.get('bid', 0)
                    ask = valid_ctx.get('ask', 0)
                    last = valid_ctx.get('last', 0)
                    vol = valid_ctx.get('vol', 0)
                    ts = valid_ctx.get('ts', 0)
                    
                    if prev_close == 0:
                        prev_close = valid_ctx.get('prev_close', 0)

                # 3. Truth Ticks & Volav
                # truth_ticks:inspect:{symbol}
                truth_json = self.redis.get(f"truth_ticks:inspect:{symbol}")
                
                truth_price = None
                truth_ts = None
                volav_1h = None
                
                if truth_json:
                    t_data = json.loads(truth_json)
                    if t_data.get('success') and t_data.get('data'):
                        d = t_data['data']
                        # Truth Price logic (simplified or from inspect)
                        # The inspect data usually has 'current_truth' or similar?
                        # GemEngine calculates it from path_dataset.
                        # BUT `temporal_analysis` inside data has hist_volav.
                        
                        temp = d.get('temporal_analysis', {})
                        if '1h' in temp:
                            volav_1h = temp['1h'].get('hist_volav')
                            
                        # Last Truth Tick
                        # We can find it from path_dataset or if inspect has summary.
                        # Let's grab the last valid truth from GemEngine logic or similar.
                        # For speed, let's assume 'last_truth_price' is stored or take the last from path_dataset
                        # Actually GemEngine iterates path_dataset.
                        # Let's see if we can find a simpler key. 
                        # TruthTicksEngine might populate `truth_ticks:last:{symbol}`? (Check later)
                        # For now, let's assume Volav is the main thing we need here.
                        # If Truth Price is needed, we look at path_dataset[-1] if exists
                        
                        path_dataset = d.get('path_dataset', [])
                        valid_ticks = [t for t in path_dataset if t.get('size', 0) in [100, 200]]
                        if valid_ticks:
                            last_tick = valid_ticks[-1] 
                            truth_price = last_tick.get('price')
                            truth_ts = last_tick.get('timestamp')


                # 4. Janall Metrics
                # janall:metrics:{symbol}
                metrics_json = self.redis.get(f"janall:metrics:{symbol}")
                fbtot = None
                sfstot = None
                final_thg = None
                smi = None # Not standard Janall but requested? Maybe GemEngine logic?
                
                if metrics_json:
                    m = json.loads(metrics_json)
                    fbtot = m.get('fbtot')
                    sfstot = m.get('sfstot')
                    final_thg = m.get('final_thg')
                    smi = m.get('smi')
                    short_final = m.get('short_final')
                    
                # 5. OFI Score
                ofi_score = 0.0
                ofi_val = self.redis.get(f"ofi:score:{symbol}")
                if ofi_val:
                    ofi_score = float(ofi_val)
                    
                # 6. Gem Metrics (Davg)
                davg = None
                gem_inspect_json = self.redis.get(f"gem:inspect:{symbol}")
                if gem_inspect_json:
                    g = json.loads(gem_inspect_json)
                    cur = g.get('current', {})
                    davg = cur.get('davg')
                
                # --- CALCULATIONS ---
                daily_chg = 0.0
                if prev_close > 0 and last > 0:
                    daily_chg = (last - prev_close)
                
                spread = 0.0
                if bid > 0 and ask > 0:
                    spread = ask - bid
                    
                spread_factor = spread * 0.15
                
                ask_sell = 0.0
                bid_buy = 0.0
                
                if ask > 0:
                    ask_sell = ask - spread_factor
                if bid > 0:
                    bid_buy = bid + spread_factor
                    
                # Scores - Explicit Calculations
                # Ask sell price - 1h Volav
                score_ask_volav = None
                if ask_sell > 0 and volav_1h:
                    score_ask_volav = ask_sell - volav_1h

                # Bid buy - 1h Volav
                score_bid_volav = None
                if bid_buy > 0 and volav_1h:
                    score_bid_volav = bid_buy - volav_1h
                    
                # Ask sell - Last truth tick
                score_ask_truth = None
                if ask_sell > 0 and truth_price:
                    score_ask_truth = ask_sell - truth_price
                    
                # Bid buy - Last truth tick
                score_bid_truth = None
                if bid_buy > 0 and truth_price:
                    score_bid_truth = bid_buy - truth_price

                # Truth - Vol (Difference)
                truth_minus_vol = None
                if truth_price and volav_1h:
                    truth_minus_vol = truth_price - volav_1h

                # Legacy "Best" Scores (using fallback logic if preferred, or just mapping)
                # For compatibility we can keep ask_sell_score as the "Volav" one if available, else Truth
                ask_sell_score = score_ask_volav if score_ask_volav is not None else score_ask_truth
                bid_buy_score = score_bid_volav if score_bid_volav is not None else score_bid_truth
                        
                # Assemble Object
                row = {
                    'symbol': symbol,
                    'group': group,
                    'last': last,
                    'bid': bid,
                    'ask': ask,
                    'daily_chg': round(daily_chg, 2),
                    'spread': round(spread, 2),
                    'davg': round(davg, 2) if davg is not None else None,
                    'volav_1h': round(volav_1h, 2) if volav_1h else None,
                    'truth_price': round(truth_price, 2) if truth_price else None,
                    'truth_ts': truth_ts,
                    'truth_minus_vol': round(truth_minus_vol, 4) if truth_minus_vol is not None else None,
                    'ofi': round(ofi_score, 2),
                    'fbtot': round(fbtot, 2) if fbtot is not None else None,
                    'sfstot': round(sfstot, 2) if sfstot is not None else None,
                    'final_thg': round(final_thg, 2) if final_thg is not None else None,
                    'short_final': round(short_final, 2) if short_final is not None else None,
                    'smi': round(smi, 2) if smi is not None else None,
                    'ask_sell': round(ask_sell, 2) if ask_sell else None,
                    'bid_buy': round(bid_buy, 2) if bid_buy else None,
                    'score_ask_volav': round(score_ask_volav, 4) if score_ask_volav is not None else None,
                    'score_bid_volav': round(score_bid_volav, 4) if score_bid_volav is not None else None,
                    'score_ask_truth': round(score_ask_truth, 4) if score_ask_truth is not None else None,
                    'score_bid_truth': round(score_bid_truth, 4) if score_bid_truth is not None else None,
                    'ask_sell_score': round(ask_sell_score, 4) if ask_sell_score is not None else None,
                    'bid_buy_score': round(bid_buy_score, 4) if bid_buy_score is not None else None,
                    'avg_adv': adv 
                }
                
                results.append(row)
            except Exception as e:
                logger.error(f"Genobs error for {symbol}: {e}")
                continue
                
        return results

genobs_service = GenobsService()
def get_genobs_service():
    return genobs_service
