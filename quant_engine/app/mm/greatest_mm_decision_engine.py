"""
Greatest MM Decision Engine
===========================

Wrapper engine for Greatest MM to be used within RUNALL cycle.
Generates MM LONG INCREASE and MM SHORT INCREASE decisions.
"""

import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import Counter

from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.mm.greatest_mm_engine import get_greatest_mm_engine
from app.psfalgo.decision_models import DecisionRequest, DecisionResponse, Decision, RejectReason
from app.psfalgo.intent_models import IntentAction
from app.psfalgo.free_exposure_engine import get_free_exposure_engine

# Priority for MM is lowest (after ADDNEWPOS)
MM_PRIORITY = 10
MM_MIN_SCORE = 30.0
MM_MAX_SCORE = 200.0

class GreatestMMDecisionEngine:
    """
    Greatest MM Decision Engine
    
    Integrates the 4-scenario MM logic into RUNALL orkestratörü.
    Filters scores: 30 <= score < 250.
    """
    
    def __init__(self):
        self.mm_engine = get_greatest_mm_engine()
        self.redis_client = None
        self._tt_engine = None  # Lazy init TruthTicksEngine for Volav
        logger.info("[GREATEST_MM_DECISION] Initialized")

    def _get_truth_ticks_engine(self):
        """Lazy-init TruthTicksEngine for Volav computation."""
        if self._tt_engine is None:
            try:
                from app.market_data.truth_ticks_engine import get_truth_ticks_engine
                self._tt_engine = get_truth_ticks_engine()
            except Exception:
                pass
        return self._tt_engine

    def _compute_volav1_for_symbol(
        self, symbol: str, ticks: list, avg_adv: float
    ) -> tuple:
        """
        Compute Volav1 price for a symbol from truth ticks.
        Returns (volav_price, volav_window) tuple.
        
        volav_window: '1h' if computed from 1h ticks, '4h' if fallback used,
                      None if no volav computed.
        """
        tt_engine = self._get_truth_ticks_engine()
        if not tt_engine or not ticks:
            return None, None

        try:
            # Filter to 1h window — MM Volav must be 1h consistent with GenObs
            now = time.time()
            ONE_HOUR = 3600
            ticks_1h = [
                t for t in ticks
                if (now - t.get('ts', 0)) <= ONE_HOUR
            ]
            volav_window = '1h'
            
            # Fallback: if no ticks in last 1h (illiquid stock), use last 4h
            if len(ticks_1h) < 3:
                FOUR_HOURS = 4 * 3600
                ticks_1h = [
                    t for t in ticks
                    if (now - t.get('ts', 0)) <= FOUR_HOURS
                ]
                volav_window = '4h'
            
            if not ticks_1h:
                return None, None
            
            volav_levels, _ = tt_engine.compute_volav_levels(
                truth_ticks=ticks_1h, top_n=4, avg_adv=avg_adv
            )
            if volav_levels:
                price = volav_levels[0].get('price')
                if price:
                    return price, volav_window
        except Exception as e:
            logger.debug(f"[GREATEST_MM_DECISION] Volav compute error for {symbol}: {e}")
        return None, None

    def _get_redis_client(self):
        if self.redis_client is None:
            client = get_redis_client()
            self.redis_client = client.sync if client else None
        return self.redis_client

    def _fetch_truth_ticks(self, symbols: List[str]) -> Dict[str, List[Dict]]:
        """Fetch truth ticks from Redis for specified symbols only (Optimized)."""
        all_ticks = {}
        redis = self._get_redis_client()
        if not redis or not symbols:
            return all_ticks
            
        try:
            # Targeted lookup of 'inspect' keys which contain the PRE-FILTERED path_dataset
            for symbol in symbols:
                key = f"truth_ticks:inspect:{symbol}"
                try:
                    result_json = redis.get(key)
                    if result_json:
                        if isinstance(result_json, bytes):
                            result_json = result_json.decode('utf-8')
                        result_data = json.loads(result_json)
                        # Extract the path_dataset which contains the latest 100 truth ticks
                        # Format is [{'timestamp': ts, 'price': p, 'size': s, 'venue': v, ...}]
                        path_data = result_data.get('data', {}).get('path_dataset', [])
                        if path_data:
                            # Normalize keys for internal use (venue -> exch if needed)
                            normalized_ticks = []
                            for t in path_data:
                                normalized_ticks.append({
                                    'ts': t.get('timestamp'),
                                    'price': t.get('price'),
                                    'size': t.get('size'),
                                    'exch': t.get('venue')
                                })
                            all_ticks[symbol] = normalized_ticks
                except:
                    continue
        except Exception as e:
            logger.warning(f"[GREATEST_MM_DECISION] Redis error fetching ticks: {e}")
            
        return all_ticks

    def _compute_son5_tick(self, ticks: List[Dict]) -> Optional[float]:
        """Compute Son5Tick (mode of last 5 truth ticks)"""
        if not ticks or not isinstance(ticks, list):
            return None
            
        # Ticks from 'path_dataset' are ALREADY truth filtered!
        # Just sort and take last 5.
        sorted_ticks = sorted(
            ticks,
            key=lambda t: t.get('ts', 0),
            reverse=True
        )
        
        last5 = sorted_ticks[:5]
        prices = [round(t.get('price', 0), 2) for t in last5 if t.get('price', 0) > 0]
        
        if prices:
            price_counts = Counter(prices)
            return price_counts.most_common(1)[0][0]
            
        return None

    def _get_new_print(self, ticks: List[Dict]) -> Optional[float]:
        """Get latest valid truth print"""
        if not ticks or not isinstance(ticks, list):
            return None
            
        # Latest tick in path_dataset is at the end or we can sort
        sorted_ticks = sorted(ticks, key=lambda t: t.get('ts', 0), reverse=True)
        if sorted_ticks and sorted_ticks[0].get('price', 0) > 0:
            return sorted_ticks[0]['price']
            
        return None

    async def run(self, request: DecisionRequest) -> List[Decision]:
        """
        Run MM analysis and return Decisions for actionable symbols.
        """
        decisions = []
        
        # 2. Identify symbols to check
        symbols_to_check = list(set(request.l1_data.keys()))
        if request.available_symbols:
            for s in request.available_symbols:
                if s not in symbols_to_check:
                    symbols_to_check.append(s)
            
        # 1. Fetch truth ticks for Son5 calculation (PASS SYMBOLS)
        all_symbol_ticks = self._fetch_truth_ticks(symbols_to_check)
        
        # FREE EXPOSURE: Get dynamic lot sizing engine
        free_exp_engine = get_free_exposure_engine()
        # Resolve account_id from trading context (cached in RUNALL pre-calculation)
        try:
            from app.trading.trading_account_context import get_trading_context
            _ctx = get_trading_context()
            _account_id = _ctx.trading_mode.value if _ctx else None
        except Exception:
            _account_id = None
        
        # Check if free exposure is BLOCKED — skip all INCREASE decisions
        _free_snapshot = free_exp_engine.get_cached_snapshot(_account_id) if _account_id else None
        if _free_snapshot and _free_snapshot.get('blocked'):
            logger.warning(
                f"[GREATEST_MM_DECISION] FREE EXPOSURE BLOCKED for {_account_id} — "
                f"all MM INCREASE skipped (free={_free_snapshot['effective_free_pct']:.1f}%)"
            )
            return decisions  # Return empty — no increase allowed
        
        for symbol in symbols_to_check:
            try:
                # ── EXCLUDED LIST CHECK ────────────────────────
                # Skip symbols in qe_excluded.csv — they must NEVER get orders
                try:
                    from app.trading.order_guard import is_excluded
                    if is_excluded(symbol):
                        continue
                except Exception:
                    pass
                
                # Get basic L1 and metrics
                l1 = request.l1_data.get(symbol)
                
                # Robust check for dict type. If someone passed a string (e.g. from Redis), fail gracefully.
                if not isinstance(l1, dict):
                    continue
                    
                if not l1.get('bid') or not l1.get('ask'):
                    continue
                    
                bid = l1['bid']
                ask = l1['ask']
                
                # 🎯 PHASE 11: MIN SPREAD RULE
                # MM strategy logic depends on spread-based volatility. 
                # If spread < 0.06 (user's rule), skip the symbol.
                if (ask - bid) < 0.06:
                     continue
                
                metric = request.metrics.get(symbol)
                bench_chg = getattr(metric, 'bench_chg', 0.0) if metric else 0.0
                if bench_chg is None:
                    bench_chg = 0.0
                    
                prev_close = getattr(metric, 'prev_close', bid) if metric else bid
                if prev_close is None:
                    prev_close = bid
                
                # Get Son5Tick and NewPrint
                ticks = all_symbol_ticks.get(symbol, [])
                son5_tick = self._compute_son5_tick(ticks)
                new_print = self._get_new_print(ticks)
                
                if not son5_tick:
                    son5_tick = l1.get('last', (bid + ask) / 2.0)
                
                son5_tick = max(bid, min(ask, son5_tick))
                
                # Volav computation for this symbol
                avg_adv = float(getattr(metric, 'avg_adv', 0) or 0) if metric else 0.0
                volav1, volav_window = self._compute_volav1_for_symbol(symbol, ticks, avg_adv)
                
                # 3. Analyze (5-scenario: 4 classic + VOLAV_ANCHOR)
                analysis = self.mm_engine.analyze_symbol(
                    symbol=symbol,
                    bid=bid,
                    ask=ask,
                    prev_close=prev_close,
                    benchmark_chg=bench_chg,
                    son5_tick=son5_tick,
                    new_print=new_print,
                    volav1=volav1
                )
                
                if not analysis or analysis.error:
                    continue
                
                # 4. Filter and build decisions
                
                # Check for Pending Orders via Potential Qty
                # If we have pending orders, avoid stacking MM orders on top of them
                # logic: if potential > qty -> Pending BUY
                # logic: if potential < qty -> Pending SELL
                
                # Find position
                pos = next((p for p in request.positions if p.symbol == symbol), None)
                has_pending_buy = False
                has_pending_sell = False
                
                if pos:
                    pot_qty = getattr(pos, 'potential_qty', pos.qty)
                    if pot_qty is None: pot_qty = pos.qty
                    
                    if pot_qty > pos.qty:
                        has_pending_buy = True
                    elif pot_qty < pos.qty:
                        has_pending_sell = True
                
                # Format common values safely
                son5_tick_str = f"{son5_tick:.2f}" if son5_tick is not None else "N/A"
                new_print_str = f"{new_print:.2f}" if new_print is not None else "N/A"
                volav1_str = f"{volav1:.2f}" if volav1 is not None else "N/A"
                volav_tag = f"Volav_{volav_window}" if volav_window else "NoVolav"
                
                # LONG Action
                if analysis.long_actionable and not has_pending_buy:
                    score = analysis.best_long_score
                    if score is not None and MM_MIN_SCORE <= score < MM_MAX_SCORE:
                        # FREE EXPOSURE: Dynamic lot sizing based on AVG_ADV and free capacity
                        mm_lot = free_exp_engine.get_mm_lot_sync(_account_id, symbol) if _account_id else 200
                        if mm_lot <= 0:
                            logger.debug(f"[GREATEST_MM_DECISION] {symbol} LONG skipped — free exposure BLOCKED")
                        else:
                            scenario_str = analysis.best_long_scenario.value if analysis.best_long_scenario else "UNKNOWN"
                            
                            decisions.append(Decision(
                                symbol=symbol,
                                action="BUY",
                                calculated_lot=mm_lot,
                                price_hint=analysis.best_long_entry,
                                reason=(
                                    f"Greatest MM LONG Score: {score:.1f} "
                                    f"Sc={scenario_str} "
                                    f"[Son5={son5_tick_str}, {volav_tag}={volav1_str}] "
                                    f"[Lot={mm_lot} FreeExp]"
                                ),
                                confidence=0.9,
                                priority=MM_PRIORITY,
                                engine_name="GREATEST_MM",
                                metrics_used={
                                    'mm_score': float(score),
                                    'volav1': float(volav1) if volav1 is not None else 0.0,
                                    'volav_window': volav_window or 'none',
                                    'scenario': scenario_str,
                                    'son5_tick': float(son5_tick) if son5_tick is not None else 0.0,
                                    'new_print': float(new_print) if new_print is not None else 0.0,
                                    'bid': float(bid),
                                    'ask': float(ask),
                                    'free_exp_lot': mm_lot,
                                    'free_exp_pct': _free_snapshot['effective_free_pct'] if _free_snapshot else 0.0,
                                }
                            ))
                
                # SHORT Action
                if analysis.short_actionable and not has_pending_sell:
                    score = analysis.best_short_score
                    if score is not None and MM_MIN_SCORE <= score < MM_MAX_SCORE:
                        # FREE EXPOSURE: Dynamic lot sizing based on AVG_ADV and free capacity
                        mm_lot = free_exp_engine.get_mm_lot_sync(_account_id, symbol) if _account_id else 200
                        if mm_lot <= 0:
                            logger.debug(f"[GREATEST_MM_DECISION] {symbol} SHORT skipped — free exposure BLOCKED")
                        else:
                            scenario_str = analysis.best_short_scenario.value if analysis.best_short_scenario else "UNKNOWN"
                            
                            decisions.append(Decision(
                                symbol=symbol,
                                action="SELL",
                                calculated_lot=mm_lot,
                                price_hint=analysis.best_short_entry,
                                reason=(
                                    f"Greatest MM SHORT Score: {score:.1f} "
                                    f"Sc={scenario_str} "
                                    f"[Son5={son5_tick_str}, {volav_tag}={volav1_str}] "
                                    f"[Lot={mm_lot} FreeExp]"
                                ),
                                confidence=0.9,
                                priority=MM_PRIORITY,
                                engine_name="GREATEST_MM",
                                metrics_used={
                                    'mm_score': float(score),
                                    'volav1': float(volav1) if volav1 is not None else 0.0,
                                    'volav_window': volav_window or 'none',
                                    'scenario': scenario_str,
                                    'son5_tick': float(son5_tick) if son5_tick is not None else 0.0,
                                    'new_print': float(new_print) if new_print is not None else 0.0,
                                    'bid': float(bid),
                                    'ask': float(ask),
                                    'free_exp_lot': mm_lot,
                                    'free_exp_pct': _free_snapshot['effective_free_pct'] if _free_snapshot else 0.0,
                                }
                            ))
                        
            except Exception as e:
                logger.error(f"[GREATEST_MM_DECISION] Error processing {symbol}: {e}")
                
        return decisions

# Global instance
_instance = None
def get_greatest_mm_decision_engine():
    global _instance
    if _instance is None:
        _instance = GreatestMMDecisionEngine()
    return _instance
