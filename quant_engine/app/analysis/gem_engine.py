"""
Gem Proposal Engine
Orchestrates the generation of "Gem" trading proposals.
Reads from Market Context (Redis), applies Gem Logic, and stores proposals.

MULTI-TIMEFRAME DIVERGENCE:
- Calculates group changes for 1H, 4H, 1D, 2D timeframes
- Shows each symbol's divergence from group average for each timeframe
- All values in CENTS (not percentages)

TIMEFRAMES (Trading Time):
- 1H = 12 entries (5min * 12 = 60min)
- 4H = 48 entries (5min * 48 = 4 hours)
- 1D = 78 entries (6.5 hours * 12)
- 2D = 156 entries (2 days)
"""

import json
import time
from typing import List, Dict, Any, Optional, Tuple
from app.core.redis_client import get_redis_client
from app.core.logger import logger
from app.analysis import gem_logic
from app.analysis.befday_guard import get_befday_guard
from app.market_data.janall_metrics_engine import get_janall_metrics_engine, initialize_janall_metrics_engine

class GemProposalEngine:
    # Valid truth tick sizes - DELEGATING TO TRUTH TICKS ENGINE
    # TRUTH_SIZES removed to prevent duplication.
    # Uses get_truth_ticks_engine().is_truth_tick() logic.
    
    # Timeframe definitions: (name, num_5min_entries)
    TIMEFRAMES = {
        '1h': 12,    # 12 * 5min = 1 hour
        '4h': 48,    # 48 * 5min = 4 hours
        '1d': 78,    # ~6.5 trading hours
        '2d': 156,   # ~2 trading days
    }
    
    def __init__(self):
        self.redis = get_redis_client().sync
        self.befday_guard = get_befday_guard()
        # Initialize Janall Metrics Engine to access Fbtot/Sfstot
        self.janall_metrics_engine = initialize_janall_metrics_engine()
        
    def get_historical_price(self, symbol: str, entries_back: int) -> Optional[float]:
        """
        Get historical price from market_context list.
        entries_back: how many 5-min entries back to look
        
        Returns the 'last' price from that entry, or None if not available.
        """
        try:
            key = f"market_context:{symbol}:5m"
            entry_json = self.redis.lindex(key, entries_back)
            if entry_json:
                entry = json.loads(entry_json)
                return entry.get('last', 0)
            return None
        except Exception:
            return None

    def get_truth_price_from_ticks(self, symbol: str) -> Optional[Tuple[float, int, str, float, dict]]:
        """
        Wrapper for _get_truth_price_raw that applies Simulation Offset in Lifeless Mode.
        """
        result = self._get_truth_price_raw(symbol)
        
        # 💀 SIMULATION CHECK
        try:
            from app.core.data_fabric import get_data_fabric
            fabric = get_data_fabric()
            if fabric and fabric.is_lifeless_mode() and result:
                offset = fabric.get_simulation_offset(symbol)
                if offset != 0.0:
                    price, size, source, ts, ta = result
                    return (price + offset, size, source, ts, ta)
        except Exception:
            pass
            
        return result

    def _get_truth_price_raw(self, symbol: str) -> Optional[Tuple[float, int, str, float, dict]]:
        """
        Get the "Current Truth Price".
        STRICT: Must be the LAST 100/200 lot print from 'path_dataset'.
        Returns (price, size, source, timestamp, temporal_analysis)
        
        Data sources (in priority order):
        1. truth_ticks:inspect:{symbol} — Rich analysis data (1h TTL, from worker)
        2. tt:ticks:{symbol} — Raw tick array (12-day TTL, from TruthTicksEngine)
        3. security_context:{symbol} — Legacy fallback
        """
        try:
            # ═══════════════════════════════════════════════════════════════
            # SOURCE 1: truth_ticks:inspect (rich data from worker, 1h TTL)
            # ═══════════════════════════════════════════════════════════════
            inspect_key = f"truth_ticks:inspect:{symbol}"
            inspect_json = self.redis.get(inspect_key)
            
            if inspect_json:
                inspect_data = json.loads(inspect_json)
                if inspect_data.get('success') and inspect_data.get('data'):
                    data = inspect_data['data']
                    
                    # Extract temporal analysis if available
                    temporal_analysis = data.get('temporal_analysis', {})

                    # 1. Use 'path_dataset' which contains raw ticks from truth_ticks_100
                    # This is the most reliable source for individual ticks
                    path_dataset = data.get('path_dataset', [])
                    
                    latest_valid_price = None
                    max_ts = 0
                    found_size = 0
                    
                    # Iterate ALL ticks in dataset
                    for tick in path_dataset:
                        sz = int(tick.get('size', 0))
                        ts = tick.get('timestamp', 0)
                        price = tick.get('price', 0)
                        
                        # Use Central Truth Engine for validation
                        # Lazy import to avoid circular dependency
                        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
                        truth_engine = get_truth_ticks_engine()
                        
                        if truth_engine.is_truth_tick(tick):
                            if ts > max_ts:
                                max_ts = ts
                                latest_valid_price = price
                                found_size = sz
                    
                    if latest_valid_price:
                        return (latest_valid_price, found_size, "truth_ticks:path_dataset", max_ts, temporal_analysis)
                        
                    # 2. Fallback: Check 'trades_history' if available (sometimes different dataset)
                    trades = data.get('trades_history', [])
                    if trades:
                        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
                        truth_engine = get_truth_ticks_engine()

                        for t in trades:
                            sz = int(t.get('size', 0))
                            ts = t.get('timestamp', 0)
                            price = t.get('price', 0)
                            # Convert to format expected by is_truth_tick if needed, mainly 'exch'
                            if truth_engine.is_truth_tick(t):
                                if ts > max_ts:
                                    max_ts = ts
                                    latest_valid_price = price
                                    found_size = sz
                                    
                        if latest_valid_price:
                             return (latest_valid_price, found_size, "truth_ticks:raw_history", max_ts, temporal_analysis)

                    # 3. Fallback: Top Truth Events
                    top_events = data.get('top_truth_events_200', [])
                    for t in top_events:
                        sz = int(t.get('size', 0))
                        ts = t.get('timestamp', 0) # 'ts' in top_events
                        price = t.get('price', 0)
                        # Top events are already filtered by Truth Engine ideally, but verify
                        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
                        truth_engine = get_truth_ticks_engine()
                        
                        if truth_engine.is_truth_tick(t):
                             if ts > max_ts:  # Find LATEST among top events
                                max_ts = ts
                                latest_valid_price = price
                                found_size = sz
                                
                    if latest_valid_price:
                        return (latest_valid_price, found_size, "truth_ticks:top_events", max_ts, temporal_analysis)

            # ═══════════════════════════════════════════════════════════════
            # SOURCE 2: tt:ticks:{symbol} — Raw tick array (12-day TTL)
            # Used when truth_ticks:inspect is expired/empty (worker not running)
            # ═══════════════════════════════════════════════════════════════
            tt_key = f"tt:ticks:{symbol}"
            tt_json = self.redis.get(tt_key)
            
            if tt_json:
                ticks = json.loads(tt_json)
                if ticks and isinstance(ticks, list):
                    from app.market_data.truth_ticks_engine import get_truth_ticks_engine
                    truth_engine = get_truth_ticks_engine()
                    
                    latest_valid_price = None
                    max_ts = 0
                    found_size = 0
                    
                    for tick in ticks:
                        # tt:ticks format: {ts, price, size, exch}
                        if truth_engine.is_truth_tick(tick):
                            ts = tick.get('ts', 0)
                            if ts > max_ts:
                                max_ts = ts
                                latest_valid_price = float(tick.get('price', 0))
                                found_size = int(tick.get('size', 0))
                    
                    if latest_valid_price and latest_valid_price > 0:
                        return (latest_valid_price, found_size, "tt:ticks:last_truth", max_ts, {})

            # Fallback: Security Context (Legacy)
            sc_key = f"security_context:{symbol}"
            sc_json = self.redis.get(sc_key)
            if sc_json:
                sc_data = json.loads(sc_json)
                truth_data = sc_data.get('truth', {})
                dominant_price = truth_data.get('dominant_price')
                if dominant_price and dominant_price > 0:
                    # Use extracted temporal_analysis if we have it, else empty
                    ta_to_use = temporal_analysis if 'temporal_analysis' in locals() else {}
                    return (dominant_price, 200, "security_context:grpan", 0, ta_to_use)
            
            return None
            
        except Exception as e:
            logger.debug(f"GemEngine: Error getting truth price for {symbol}: {e}")
            return None
        finally:
            # 💀 SIMULATION: Apply Truth Offset if Lifeless Mode
            try:
                from app.core.data_fabric import get_data_fabric
                fabric = get_data_fabric()
                if fabric and fabric.is_lifeless_mode():
                    offset = fabric.get_simulation_offset(symbol)
                    if offset != 0.0:
                        # Wait, we need to modify the return value. 
                        # 'finally' executes but doesn't change 'return' unless we return explicitly here.
                        # This structure is tricky in Python.
                        # Better to modify the return points or wrap the logic.
                        pass 
            except:
                pass
        
    def generate_proposals(self) -> List[Dict[str, Any]]:
        """
        Generates proposals with multi-timeframe divergence calculations.
        """
        proposals = []
        
        # 1. Fetch Universe from Redis
        universe_json = self.redis.get("market_context:universe")
        if not universe_json:
            logger.warning("GemEngine: Universe not found in Redis.")
            return []
            
        universe = json.loads(universe_json)
        
        # 2. First pass: Collect current prices and historical prices for each timeframe
        symbol_data = {}
        group_current_changes = {}  # {group: [current_cent_changes]}
        group_tf_changes = {tf: {} for tf in self.TIMEFRAMES}  # {tf: {group: [changes]}}
        group_prev_closes = {}
        
        for symbol, info in universe.items():
            group = info.get('group', 'unknown')
            
            # Get current market context
            last_ctx_json = self.redis.lindex(f"market_context:{symbol}:5m", 0)
            if not last_ctx_json:
                # logger.warning(f"Skipping {symbol}: No market context in Redis")
                continue
                
            last_ctx = json.loads(last_ctx_json)
            quote_price = last_ctx.get('last') or 0
            prev_close = last_ctx.get('prev_close') or 0
            vol = last_ctx.get('vol') or 0
            bid = last_ctx.get('bid') or 0
            ask = last_ctx.get('ask') or 0
            
            # 💀 SIMULATION: Override L1 with Shuffled Data (DataFabric)
            # This ensures Gem Analysis sees the simulated prices and offsets.
            try:
                from app.core.data_fabric import get_data_fabric
                fabric = get_data_fabric()
                if fabric and fabric.is_lifeless_mode():
                    snap = fabric.get_fast_snapshot(symbol)
                    if snap:
                        quote_price = snap.get('last') or quote_price
                        bid = snap.get('bid') or bid
                        ask = snap.get('ask') or ask
                        # Update prev_close if available in snapshot
                        if snap.get('prev_close'):
                            prev_close = float(snap.get('prev_close'))
            except Exception:
                pass
            
            # PrevClose is usually static, but if it came from Redis context, it might be old.
                    # DataFabric has correct static prev_close.
                    # BUT strictly speaking, 'last - prev_close' logic uses prev_close.
                    # If we shuffle 'last', we change change. Correct.

            
            # Try to get truth price
            truth_result = self.get_truth_price_from_ticks(symbol)
            
            temporal_data = {}
            
            if truth_result:
                effective_price, truth_size, truth_source, truth_ts, temporal_data = truth_result
                has_truth = True
            else:
                effective_price = quote_price
                truth_size = 0
                truth_source = None
                truth_ts = None
                has_truth = False
            
            if effective_price <= 0:
                # logger.warning(f"Skipping {symbol}: Effective price is 0 (Quote: {quote_price})")
                continue
            
            if prev_close <= 0:
                prev_close = effective_price
            
            # Current change from prev_close (in cents)
            current_change = effective_price - prev_close
            
            # Calculate changes for each timeframe using PRE-CALCULATED TEMPORAL DATA
            tf_changes = {}
            tf_prices = {}
            
            for tf_name in self.TIMEFRAMES:
                # Get data from temporal_analysis passed from TruthTicksEngine
                # temporal_data keys are '1h', '4h', etc.
                tf_info = temporal_data.get(tf_name, {})
                change = tf_info.get('change')
                hist_price = tf_info.get('hist_volav')
                
                # If we have valid change data from engine, use it
                if change is not None and hist_price is not None:
                    tf_changes[tf_name] = change
                    tf_prices[tf_name] = hist_price
                else:
                    # Fallback (if needed, or leave None)
                    tf_changes[tf_name] = None
                    tf_prices[tf_name] = None
            
            # Store calculated data for group aggregation
            group_current_changes[group] = group_current_changes.get(group, []) + [current_change]
            
            if group not in group_prev_closes:
                group_prev_closes[group] = []
            group_prev_closes[group].append(prev_close)
            
            # Anomaly Detection
            if '1h' in tf_changes and tf_changes['1h'] is not None:
                chg1h = tf_changes['1h']
                if chg1h < -2.0:
                    print(f"ANOMALY {symbol} 1H Chg: {chg1h} (Price={effective_price} Hist={tf_prices['1h']})")

            for tf, change_val in tf_changes.items():
                if change_val is not None:
                    if group not in group_tf_changes[tf]:
                        group_tf_changes[tf][group] = []
                    group_tf_changes[tf][group].append(change_val)
        
            # Store symbol data
            symbol_data[symbol] = {
                'group': group,
                'effective_price': effective_price,
                'quote_price': quote_price,
                'prev_close': prev_close,
                'current_change': current_change,
                'tf_changes': tf_changes,
                'tf_prices': tf_prices,
                'vol': vol,
                'bid': bid,
                'ask': ask,
                'has_truth': has_truth,
                'truth_size': truth_size,
                'truth_source': truth_source,
                'info': info,
                'truth_ts': truth_ts
            }
        
        # 3. Calculate group averages
        group_avg_current = {}
        for group, changes in group_current_changes.items():
            group_avg_current[group] = sum(changes) / len(changes) if changes else 0.0
        
        group_avg_prev = {}
        for group, closes in group_prev_closes.items():
            group_avg_prev[group] = sum(closes) / len(closes) if closes else 0.0
        
        # Calculate group averages for each timeframe
        group_avg_tf = {tf: {} for tf in self.TIMEFRAMES}
        for tf_name in self.TIMEFRAMES:
            for group, changes in group_tf_changes[tf_name].items():
                group_avg_tf[tf_name][group] = sum(changes) / len(changes) if changes else 0.0
        
        # 4. Generate proposals with multi-timeframe divergence
        for symbol, data in symbol_data.items():
            group = data['group']
            grp_avg = group_avg_current.get(group, 0.0)
            grp_avg_pc = group_avg_prev.get(group, 0.0)
            
            current_change = data['current_change']
            effective_price = data['effective_price']
            prev_close = data['prev_close']
            vol = data['vol']
            bid = data['bid']
            ask = data['ask']
            has_truth = data['has_truth']
            truth_size = data['truth_size']
            tf_changes = data['tf_changes']
            info = data['info']
            truth_ts = data.get('truth_ts')
            
            # Current divergence (Div Now)
            divergence = current_change - grp_avg
            abs_div = abs(divergence)
            
            # Calculate divergence for each timeframe
            tf_divs = {}
            inspector_tf_data = {}
            
            # Davg Calculation with Weights
            # Weights: Current (0.15), 1h (0.30), 4h (0.20), 1d (0.20), 2d (0.15)
            weights = {
                'current': 0.15,
                '1h': 0.30,
                '4h': 0.20,
                '1d': 0.20,
                '2d': 0.15
            }

            weighted_sum = 0.0
            total_weight = 0.0
            
            # 1. Current Divergence contribution
            weighted_sum += divergence * weights['current']
            total_weight += weights['current']

            for tf_name in self.TIMEFRAMES:
                sym_tf_chg = tf_changes.get(tf_name)
                grp_tf_avg = group_avg_tf[tf_name].get(group, 0.0)
                
                div_val = None
                if sym_tf_chg is not None:
                    div_val = sym_tf_chg - grp_tf_avg
                    
                    # Add to weighted calculation
                    w = weights.get(tf_name, 0.0)
                    if w > 0:
                        weighted_sum += div_val * w
                        total_weight += w
                
                tf_divs[tf_name] = div_val
                
                # Prepare inspector data
                inspector_tf_data[tf_name] = {
                    'hist_price': data['tf_prices'].get(tf_name),
                    'change_cents': sym_tf_chg,
                    'group_avg_change': grp_tf_avg,
                    'divergence': div_val
                }
            
            # Compute Weighted Davg
            davg = None
            if total_weight > 0:
                davg = weighted_sum / total_weight
                
            # Fetch Fbtot / Sfstot from Redis (populated by MarketContextWorker)
            fbtot = None
            sfstot = None
            try:
                metrics_json = self.redis.get(f"janall:metrics:{symbol}")
                if metrics_json:
                    metrics = json.loads(metrics_json)
                    fbtot = metrics.get('fbtot')
                    sfstot = metrics.get('sfstot')
            except Exception:
                pass

            # Debug Davg/Fbtot for specific problematic symbol


            # SAVE INSPECTOR DATA TO REDIS
            inspector_data = {
                'symbol': symbol,
                'group': group,
                'timestamp': time.time(),
                'current': {
                    'price': effective_price,
                    'is_truth': has_truth,
                    'source': data['truth_source'] if has_truth else 'quote',
                    'size': truth_size,
                    'ts': truth_ts,
                    'prev_close': prev_close,
                    'change': current_change,
                    'group_avg_change': grp_avg,
                    'divergence': divergence,
                    'davg': davg,
                    'fbtot': fbtot,
                    'sfstot': sfstot
                },
                'timeframes': inspector_tf_data
            }
            self.redis.setex(f"gem:inspect:{symbol}", 3600, json.dumps(inspector_data))
                
            # Spread
            def _safe_f(v): return float(v) if v is not None else 0.0
            s_bid = _safe_f(bid)
            s_ask = _safe_f(ask)
            spread = s_ask - s_bid if s_ask > 0 and s_bid > 0 else 0
            
            # Action logic
            if abs_div > 0.08:
                action = "SELL" if divergence > 0 else "BUY"
            elif abs_div > 0.05:
                action = "WATCH"
            else:
                action = "HOLD"
            
            # Check fake print
            avg_adv = info.get('ADV', 50000)
            is_fake = gem_logic.is_fake_print(vol, avg_adv)
            
            # Build reason (simplified)
            reason = f"Sym: {current_change:+.2f} | Grp: {grp_avg:+.2f}"
            if not has_truth:
                reason += " (q)"
            
            proposal = {
                'symbol': symbol,
                'group': group,
                'price': round(effective_price, 2),
                'prev_close': round(prev_close, 2),
                'grp_avg_prev': round(grp_avg_pc, 2),
                'rr': round(divergence, 2),
                'divergence': round(divergence, 4),
                'davg': round(davg, 2) if davg is not None else None,
                'fbtot': round(fbtot, 2) if fbtot is not None else None,
                'sfstot': round(sfstot, 2) if sfstot is not None else None,
                # Multi-timeframe divergences
                'div_1h': round(tf_divs.get('1h'), 2) if tf_divs.get('1h') is not None else None,
                'div_4h': round(tf_divs.get('4h'), 2) if tf_divs.get('4h') is not None else None,
                'div_1d': round(tf_divs.get('1d'), 2) if tf_divs.get('1d') is not None else None,
                'div_2d': round(tf_divs.get('2d'), 2) if tf_divs.get('2d') is not None else None,
                'spread_eff': "WIDE" if spread > 0.20 else "NORMAL",
                'action': action,
                'qty': 0,
                'reason': reason,
                'is_fake_print': is_fake,
                'has_truth_tick': has_truth,
                'truth_size': truth_size
            }
            proposals.append(proposal)
        
        # Sort by absolute divergence
        proposals.sort(key=lambda x: abs(x.get('divergence', 0)), reverse=True)
        
        logger.info(f"GemEngine: Generated {len(proposals)} proposals with multi-TF divergence.")

        # Store in Redis
        if proposals:
            self.redis.set("gem:proposals", json.dumps(proposals))
        else:
            self.redis.set("gem:proposals", json.dumps([]))
            
        return proposals

# Global Instance
gem_engine = GemProposalEngine()
