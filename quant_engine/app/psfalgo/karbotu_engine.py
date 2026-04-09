"""
KARBOTU Decision Engine - Phase 11 Refactor
===========================================

Role: "Macro Decision & Signal Engine"
-   Generates SIGNALS (Eligibility, Bias, Quality) for LT TRIM execution.
-   Generates INTENTS (Macro reduction suggestions) if needed.
-   Does NOT execute trades directly (delegates execution details to LT Trim).

Dual Output Mode:
    1.  Signals: Used by LT Trim engine for Veto/Bias.
    2.  Intents: Optional direct macro decisions (e.g. "Hard Reduce List").
"""

import asyncio
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.core.logger import logger
from app.psfalgo.decision_models import (
    PositionSnapshot,
    SymbolMetrics,
    Decision, # Legacy model, mapped to Intent
    DecisionRequest
)
from app.psfalgo.intent_models import Intent, IntentAction
from app.psfalgo.decision_models import AnalysisSignal as KarbotuSignal
from dataclasses import dataclass



@dataclass
class KarbotuOutput:
    """Output payload from Karbotu Engine."""
    signals: Dict[str, KarbotuSignal] = field(default_factory=dict)
    intents: List[Intent] = field(default_factory=list)
    execution_time_ms: float = 0.0

class KarbotuEngine:
    """
    KARBOTU Decision Engine (Phase 11)
    
    Now purely analytical + macro intent generator.
    Standard execution logic (steps 2-13) determines SIGNALS for LT Trim.
    """
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.last_diagnostic = None  # Store last cycle diagnostic for API access
        # Fallback rules can be loaded here if config_manager not provided
     
    async def run(
        self, 
        request: DecisionRequest, 
        rules: Dict[str, Any]
    ) -> KarbotuOutput:
        """
        Main entry point.
        Args:
            request: Market data & positions
            rules: Effective strategy rules for this account
        """
        start_time = datetime.now()
        output = KarbotuOutput()
        
        logger.info(f"[KARBOTU] 🚀 Engine starting: {len(request.positions)} positions, {len(request.metrics)} metrics")
        
        # Diagnostic tracking
        diagnostic = {
            'total_positions': len(request.positions),
            'longs_count': 0,
            'shorts_count': 0,
            'positions_analyzed': 0,
            'eligible_count': 0,
            'triggered_count': 0,
            'blocked_by_gort': 0,
            'blocked_by_too_cheap': 0,
            'blocked_by_too_expensive': 0,
            'no_metrics': 0,
            'intent_generated': 0,
            'blocking_details': []
        }
        
        try:
            # Import data completeness check
            from app.psfalgo.decision_models import is_data_complete, get_missing_metrics
            
            # Separate positions (EXCLUDE MM positions - those are for MM engine)
            longs = []
            shorts = []
            for p in request.positions:
                pos_tag = getattr(p, 'tag', '') or ''
                if 'MM' in pos_tag.upper():
                    logger.debug(f"[KARBOTU] Skipping MM position: {p.symbol} (tag={pos_tag})")
                    continue
                # Use POTENTIAL QTY (Net of Pending)
                qty = getattr(p, 'potential_qty', p.qty)
                if qty is None: qty = p.qty
                
                if 'MM' in pos_tag.upper():
                    logger.debug(f"[KARBOTU] Skipping MM position: {p.symbol} (tag={pos_tag})")
                    continue
                
                # Check potential qty side
                if qty > 0:
                    longs.append(p)
                elif qty < 0:
                    shorts.append(p)
            
            diagnostic['longs_count'] = len(longs)
            diagnostic['shorts_count'] = len(shorts)
            not_found_list = []
            valid_longs = []
            valid_shorts = []
            
            for pos in longs:
                metric = request.metrics.get(pos.symbol)
                if not is_data_complete(metric, side='LONG'):
                    missing = get_missing_metrics(metric, side='LONG')
                    not_found_list.append({
                        'symbol': pos.symbol,
                        'side': 'LONG',
                        'qty': pos.qty,
                        'missing_metrics': missing,
                        'reason': f"DATA_INCOMPLETE: {', '.join(missing)}"
                    })
                    diagnostic['no_metrics'] += 1
                    logger.debug(f"[KARBOTU] ⚠️ {pos.symbol} EXCLUDED - DATA_INCOMPLETE: {missing}")
                else:
                    valid_longs.append(pos)
            
            for pos in shorts:
                metric = request.metrics.get(pos.symbol)
                if not is_data_complete(metric, side='SHORT'):
                    missing = get_missing_metrics(metric, side='SHORT')
                    not_found_list.append({
                        'symbol': pos.symbol,
                        'side': 'SHORT',
                        'qty': pos.qty,
                        'missing_metrics': missing,
                        'reason': f"DATA_INCOMPLETE: {', '.join(missing)}"
                    })
                    diagnostic['no_metrics'] += 1
                    logger.debug(f"[KARBOTU] ⚠️ {pos.symbol} EXCLUDED - DATA_INCOMPLETE: {missing}")
                else:
                    valid_shorts.append(pos)
            
            # Store NOT FOUND list to Redis for UI tab
            if not_found_list:
                try:
                    from app.core.redis_client import get_redis_client
                    redis_client = get_redis_client()
                    if redis_client and redis_client.sync:
                        import json
                        redis_client.sync.setex(
                            'psfalgo:not_found:karbotu',
                            300,  # 5 min TTL
                            json.dumps(not_found_list)
                        )
                        logger.info(f"[KARBOTU] 📋 Stored {len(not_found_list)} NOT FOUND stocks to Redis")
                except Exception as redis_err:
                    logger.warning(f"[KARBOTU] Could not store NOT FOUND to Redis: {redis_err}")
            
            # Use filtered lists for analysis
            longs = valid_longs
            shorts = valid_shorts
            
            # --- PROCESS LONGS ---
            for pos in longs:
                diagnostic['positions_analyzed'] += 1
                metric = request.metrics.get(pos.symbol)
                
                signal, intent, detail_info = self._analyze_long(pos, metric, rules)
                output.signals[pos.symbol] = signal
                
                # DEBUG: Log each position's analysis result
                logger.debug(
                    f"[KARBOTU_DEBUG] LONG {pos.symbol}: "
                    f"bias={signal.bias:.2f}, eligible={signal.eligibility}, "
                    f"intent={intent is not None}, reasons={signal.reason_codes}"
                )
                
                # Track results with FULL details
                status = 'NO_INTENT'
                if signal.eligibility:
                    diagnostic['eligible_count'] += 1
                if signal.bias > 0.5:
                    diagnostic['triggered_count'] += 1
                    status = 'TRIGGERED'
                    logger.debug(
                        f"[KARBOTU_DEBUG] LONG {pos.symbol} TRIGGERED "
                        f"(bias {signal.bias:.2f} > 0.5)"
                    )
                if intent:
                    output.intents.append(intent)
                    diagnostic['intent_generated'] += 1
                    status = 'INTENT_GENERATED'
                    logger.info(
                        f"[KARBOTU_DEBUG] ✅ LONG {pos.symbol} INTENT GENERATED: "
                        f"{intent.action} {intent.qty}"
                    )
                else:
                    if signal.bias > 0.5:
                        # TRIGGERED but NO INTENT - this is the BUG!
                        logger.warning(
                            f"[KARBOTU_DEBUG] ⚠️ LONG {pos.symbol} TRIGGERED BUT NO INTENT! "
                            f"bias={signal.bias:.2f}, eligible={signal.eligibility}, "
                            f"reasons={signal.reason_codes}"
                        )
                
                # Store comprehensive detail for Report
                diagnostic['blocking_details'].append({
                    'symbol': pos.symbol,
                    'side': 'LONG',
                    'status': status,
                    'qty': pos.qty,
                    'sell_qty': intent.qty if intent else 0,
                    'step_triggered': detail_info.get('step'),
                    'gort': metric.gort if metric else None,
                    'fbtot': metric.fbtot if metric else None,
                    'ask_sell_pahalilik': metric.ask_sell_pahalilik if metric else None,
                    'reasons': signal.reason_codes,
                    'sweep_triggered': detail_info.get('sweep', False),
                    'calculation': detail_info.get('calc_detail', ''),
                    'filters_passed': detail_info.get('filters', {})
                })
                
                # Track blocking reasons
                if 'GORT_TOO_LOW' in signal.reason_codes:
                    diagnostic['blocked_by_gort'] += 1
                if 'TOO_CHEAP_TO_SELL' in signal.reason_codes:
                    diagnostic['blocked_by_too_cheap'] += 1
                if not metric:
                    diagnostic['no_metrics'] += 1

            # --- PROCESS SHORTS ---
            for pos in shorts:
                diagnostic['positions_analyzed'] += 1
                metric = request.metrics.get(pos.symbol)
                
                signal, intent, detail_info = self._analyze_short(pos, metric, rules)
                output.signals[pos.symbol] = signal
                
                # Same detailed tracking as longs
                status = 'NO_INTENT'
                if signal.eligibility:
                    diagnostic['eligible_count'] += 1
                if signal.bias > 0.5:
                    diagnostic['triggered_count'] += 1
                    status = 'TRIGGERED'
                if intent:
                    output.intents.append(intent)
                    diagnostic['intent_generated'] += 1
                    status = 'INTENT_GENERATED'
                
                # Store comprehensive detail
                diagnostic['blocking_details'].append({
                    'symbol': pos.symbol,
                    'side': 'SHORT',
                    'status': status,
                    'qty': pos.qty,
                    'cover_qty': intent.qty if intent else 0,
                    'step_triggered': detail_info.get('step'),
                    'gort': metric.gort if metric else None,
                    'sfstot': metric.sfstot if metric else None,
                    'bid_buy_ucuzluk': metric.bid_buy_ucuzluk if metric else None,
                    'reasons': signal.reason_codes,
                    'sweep_triggered': detail_info.get('sweep', False),
                    'calculation': detail_info.get('calc_detail', ''),
                    'filters_passed': detail_info.get('filters', {})
                })
                
                if 'GORT_TOO_HIGH' in signal.reason_codes:
                    diagnostic['blocked_by_gort'] += 1
                if 'TOO_EXPENSIVE_TO_COVER' in signal.reason_codes:
                    diagnostic['blocked_by_too_expensive'] += 1
                if not metric:
                    diagnostic['no_metrics'] += 1

            output.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log comprehensive diagnostic summary
            logger.info("=" * 80)
            logger.info("[KARBOTU DIAGNOSTIC] Cycle Summary:")
            logger.info(f"  Positions: {diagnostic['total_positions']} (Longs: {diagnostic['longs_count']}, Shorts: {diagnostic['shorts_count']})")
            logger.info(f"  Eligible: {diagnostic['eligible_count']}/{diagnostic['positions_analyzed']}")
            logger.info(f"  Triggered: {diagnostic['triggered_count']}/{diagnostic['positions_analyzed']}")
            logger.info(f"  Intents Generated: {diagnostic['intent_generated']}")
            logger.info(f"  Blocked - GORT: {diagnostic['blocked_by_gort']}, Too Cheap: {diagnostic['blocked_by_too_cheap']}, Too Expensive: {diagnostic['blocked_by_too_expensive']}, No Metrics: {diagnostic['no_metrics']}")
            
            if diagnostic['blocking_details']:
                logger.info("  Top Blocking Details:")
                for detail in diagnostic['blocking_details'][:5]:  # Show top 5
                    # New structure: status, reasons (list), not 'reason'
                    reason_str = ', '.join(detail.get('reasons', [])) if detail.get('reasons') else 'UNKNOWN'
                    if 'GORT_TOO_LOW' in reason_str or 'GORT_TOO_HIGH' in reason_str:
                        logger.info(f"    - {detail['symbol']} ({detail['side']}): {reason_str} (gort={detail.get('gort')})")
                    elif 'TOO_CHEAP' in reason_str or 'TOO_EXPENSIVE' in reason_str:
                        metric_name = 'ask_sell_pahalilik' if 'ask_sell_pahalilik' in detail else 'bid_buy_ucuzluk'
                        logger.info(f"    - {detail['symbol']} ({detail['side']}): {reason_str} ({metric_name}={detail.get(metric_name)})")
                    else:
                        # Intent generated - show details
                        logger.info(f"    - {detail['symbol']} ({detail['side']}): {detail['status']} qty={detail.get('sell_qty', detail.get('cover_qty', 0))}")
            
            if diagnostic['intent_generated'] == 0:
                logger.warning(f"[KARBOTU] ⚠️ NO INTENTS GENERATED - analyzed={diagnostic['positions_analyzed']}, eligible={diagnostic['eligible_count']}, triggered={diagnostic['triggered_count']}, blocked_by_gort={diagnostic['blocked_by_gort']}, no_metrics={diagnostic['no_metrics']}")
            else:
                logger.info(f"[KARBOTU] ✅ Generated {diagnostic['intent_generated']} intents (analyzed={diagnostic['positions_analyzed']}, eligible={diagnostic['eligible_count']}, triggered={diagnostic['triggered_count']})")
            logger.info("=" * 80)
            
            # Store diagnostic for API access
            output.diagnostic = diagnostic
            self.last_diagnostic = diagnostic
            
            return output

        except Exception as e:
            logger.error(f"[KARBOTU] Error in run: {e}", exc_info=True)
            return output

    def _analyze_long(self, pos: PositionSnapshot, metric: SymbolMetrics, rules: Dict) -> Tuple[KarbotuSignal, Optional[Intent], Dict[str, Any]]:
        """Analyze a LONG position."""
        detail_info = {'step': None, 'sweep': False, 'filters': {}, 'calc_detail': ''}
        
        if not metric:
             return KarbotuSignal(pos.symbol, False, 0.0, "UNKNOWN", ["No Metrics"]), None, detail_info
        
        symbol = pos.symbol
        reasons = []
        eligible = False
        bias = 0.0 # Neutral
        bucket = "OK"
        
        # 1. GORT Filter (Veto)
        gort_conf = rules.get('karbotu', {}).get('gort_filter_longs', {})
        if gort_conf.get('enabled', True):
            filters = gort_conf.get('filters', {})
            # Gort must be > threshold
            if metric.gort is not None and metric.gort <= filters.get('gort_gt', -1.0):
                reasons.append("GORT_TOO_LOW")
                bucket = "BAD"
            # Ask Sell Pahalilik must be > threshold (not too cheap)
            elif metric.ask_sell_pahalilik is not None and metric.ask_sell_pahalilik <= filters.get('ask_sell_pahalilik_gt', -0.05):
                reasons.append("TOO_CHEAP_TO_SELL")
                bucket = "BAD"
            else:
                eligible = True # Passes basic checks
                bucket = "GOOD_LONG"
        else:
            eligible = True # Filter disabled

        # 2. Step Logic (Determines Intensity/Bias)
        # We iterate steps to find if any 'sell' condition is met. 
        # If met, it increases sell pressure (Bias).
        
        # Simplified loop for steps 2-7
        triggered_step = None
        for step_num in range(2, 8):
            step_key = f'step_{step_num}'
            step_conf = rules.get('karbotu', {}).get(step_key, {})
            if not step_conf.get('enabled', False) or step_conf.get('side') != 'LONGS':
                continue
                
            # Check filters
            # Note: Logic reused from original _check_step_filters ideally
            if self._passes_step_filters(step_conf.get('filters', {}), metric, is_shorts=False):
                triggered_step = step_num
                bias = 1.0 # Strong Selling Bias
                reasons.append(f"TRIGGER_STEP_{step_num}")
                detail_info['filters'] = step_conf.get('filters', {})
                break
        
        detail_info['step'] = triggered_step
        
        signal = KarbotuSignal(
            symbol=symbol, 
            eligibility=(eligible and (triggered_step is not None)), # Only eligible if triggered? Or Gort passed?
            # CORRECTION: LT Trim usually governs the trigger. Karbotu just provides the "OK".
            # If GORT passed, it is "Eligible for consideration".
            # But if a Step passed, it is "Recommended to Sell".
            # Let's say: Eligible = GORT Passed. Bias = 1.0 if Step Triggered.
            bias=bias, 
            quality_bucket=bucket, 
            reason_codes=reasons
        )
        
        # Intent Generation (CRITICAL FIX)
        intent = None
        if bias > 0.5 and triggered_step is not None:
            # KARBOTU triggered - create SELL intent
            # USE POTENTIAL QTY for Sizing
            pot_qty = getattr(pos, 'potential_qty', pos.qty) or pos.qty
            
            # Current Logic: Sell 10% of potential position, Min 200 lots
            raw_qty = max(125, int(pot_qty * 0.1))
            
            # SWEEP LOGIC: If remaining qty < 200, sell nearly all
            remaining = pot_qty - raw_qty
            
            final_qty = raw_qty
            if remaining < 200 and remaining > 0:
                final_qty = pot_qty  # Sweep all potential
                detail_info['sweep'] = True
                detail_info['calc_detail'] = f"SWEEP: {pot_qty} - {raw_qty} = {remaining} < 200 → Sell ALL"
                logger.info(f"[KARBOTU] 🧹 SWEEP Triggered for {symbol}: Remainder {remaining} < 200 -> Selling ALL {final_qty}")
            else:
                detail_info['calc_detail'] = f"10% of {pot_qty} = {raw_qty}, remain={remaining}"
            
            # CAP LOGIC: Ensure we don't flip position (Sell > Held Potential)
            if final_qty > pot_qty:
                 final_qty = pot_qty

            # Safe formatting for None values
            gort_str = f"{metric.gort:.2f}" if metric.gort is not None else "N/A"
            pahalilik_str = f"{metric.ask_sell_pahalilik:.2f}" if metric.ask_sell_pahalilik is not None else "N/A"
            fbtot_str = f"{metric.fbtot:.2f}" if metric.fbtot is not None else "N/A"
            
            # Generate unique ID
            intent_id = f"KARBOTU_LONG_{symbol}_{int(datetime.now().timestamp() * 1000)}"
            
            intent = Intent(
                id=intent_id,
                symbol=symbol,
                action=IntentAction.SELL,
                qty=final_qty,
                reason_code=f"KARBOTU_STEP_{triggered_step}",
                reason_text=f'KARBOTU Step {triggered_step} profit-taking (GORT={gort_str}, Fbtot={fbtot_str}, Pahalilik={pahalilik_str})',
                trigger_rule=f"Step {triggered_step} LONG filter",
                engine_name="KARBOTU",
                metric_values={
                    "gort": metric.gort,
                    "ask_sell_pahalilik": metric.ask_sell_pahalilik,
                    "bias": bias,
                    "fbtot": metric.fbtot,
                    "sma63_chg": metric.sma63_chg
                },
                priority=20,  # Macro Priority
                intent_category="KARBOTU_MACRO"
            )
            logger.debug(
                f"[KARBOTU] ✅ Created SELL intent for {symbol}: "
                f"{final_qty} lots (Pos: {pos.qty}), Step={triggered_step}"
            )
        
        return signal, intent, detail_info

    def _analyze_short(self, pos: PositionSnapshot, metric: SymbolMetrics, rules: Dict) -> Tuple[KarbotuSignal, Optional[Intent], Dict[str, Any]]:
        """Analyze a SHORT position."""
        detail_info = {'step': None, 'sweep': False, 'filters': {}, 'calc_detail': ''}
        
        if not metric:
             return KarbotuSignal(pos.symbol, False, 0.0, "UNKNOWN", ["No Metrics"]), None, detail_info

        symbol = pos.symbol
        reasons = []
        eligible = False
        bias = 0.0
        bucket = "OK"

        # 1. GORT Filter
        gort_conf = rules.get('karbotu', {}).get('gort_filter_shorts', {})
        if gort_conf.get('enabled', True):
            filters = gort_conf.get('filters', {})
            if metric.gort is not None and metric.gort >= filters.get('gort_lt', 1.0):
                reasons.append("GORT_TOO_HIGH")
                bucket = "BAD"
            elif metric.bid_buy_ucuzluk is not None and metric.bid_buy_ucuzluk >= filters.get('bid_buy_ucuzluk_lt', 0.05):
                reasons.append("TOO_EXPENSIVE_TO_COVER")
                bucket = "BAD"
            else:
                eligible = True
                bucket = "GOOD_SHORT"
        else:
            eligible = True

        # 2. Step Logic (9-13)
        triggered_step = None
        for step_num in range(9, 14):
            step_key = f'step_{step_num}'
            step_conf = rules.get('karbotu', {}).get(step_key, {})
            if not step_conf.get('enabled', False) or step_conf.get('side') != 'SHORTS':
                continue
            
            if self._passes_step_filters(step_conf.get('filters', {}), metric, is_shorts=True):
                triggered_step = step_num
                bias = 1.0 # Strong Buying (Covering) Bias? 
                # Note: Bias convention: +1 = Sell/Short, -1 = Buy/Cover? 
                # Plan said: "bias: float (-1.0 to 1.0, where >0 is Sell/Short pressure)"
                # Wait, usually positive bias = Bullish? No, context is "Karbotu Decision".
                # If Karbotu is "Reduce Position", then:
                # For Longs: Reduce = Sell (>0 pressure?)
                # For Shorts: Reduce = Cover (Buy) (<0 pressure?)
                # Let's standardize: Bias = "Desire to Reduce". 
                # If 1.0 -> Strongly want to reduce (Sell Long or Cover Short).
                bias = 1.0 
                reasons.append(f"TRIGGER_STEP_{step_num}")
                detail_info['filters'] = step_conf.get('filters', {})
                break
        
        detail_info['step'] = triggered_step

        signal = KarbotuSignal(
            symbol=symbol,
            eligibility=eligible, # Gort passed
            bias=bias,            # Step triggered
            quality_bucket=bucket,
            reason_codes=reasons
        )
        
        # Intent Generation (CRITICAL FIX)
        intent = None
        if bias > 0.5 and triggered_step is not None:
            # KARBOTU triggered - create BUY (COVER) intent
            # Current Logic: Cover 10% of position (profit-taking), Min 200 lots
            # USE POTENTIAL QTY for Sizing
            pot_qty = getattr(pos, 'potential_qty', pos.qty) or pos.qty
            abs_qty = abs(pot_qty)
            
            raw_qty = max(125, int(abs_qty * 0.1))  # Min 125 lots for decrease

            # SWEEP LOGIC: If remaining (short) qty < 200, cover all
            remaining = abs_qty - raw_qty
            final_qty = raw_qty
            if remaining < 200 and remaining > 0:
                final_qty = abs_qty # Cover all
                detail_info['sweep'] = True
                detail_info['calc_detail'] = f"SWEEP: {abs_qty} - {raw_qty} = {remaining} < 200 → Cover ALL"
                logger.info(f"[KARBOTU] 🧹 SWEEP Triggered for {symbol}: Remainder {remaining} < 200 -> Covering ALL {final_qty}")
            else:
                detail_info['calc_detail'] = f"10% of {abs_qty} = {raw_qty}, remain={remaining}"
            
            # CAP LOGIC: Ensure we don't flip position
            if final_qty > abs_qty:
                final_qty = abs_qty
            
            # Safe formatting for None values
            gort_str = f"{metric.gort:.2f}" if metric.gort is not None else "N/A"
            ucuzluk_str = f"{metric.bid_buy_ucuzluk:.2f}" if metric.bid_buy_ucuzluk is not None else "N/A"
            sfstot_str = f"{metric.sfstot:.2f}" if metric.sfstot is not None else "N/A"
            
            # Generate unique ID
            intent_id = f"KARBOTU_SHORT_{symbol}_{int(datetime.now().timestamp() * 1000)}"
            
            intent = Intent(
                id=intent_id,
                symbol=symbol,
                action=IntentAction.BUY,
                qty=final_qty,
                reason_code=f"KARBOTU_STEP_{triggered_step}",
                reason_text=f'KARBOTU Step {triggered_step} profit-taking (GORT={gort_str}, Sfstot={sfstot_str}, Ucuzluk={ucuzluk_str})',
                trigger_rule=f"Step {triggered_step} SHORT filter",
                engine_name="KARBOTU",
                metric_values={
                    "gort": metric.gort,
                    "bid_buy_ucuzluk": metric.bid_buy_ucuzluk,
                    "bias": bias,
                    "sfstot": metric.sfstot,
                    "sma63_chg": metric.sma63_chg
                },
                priority=20,  # Macro Priority
                intent_category="KARBOTU_MACRO"
            )
            logger.debug(
                f"[KARBOTU] ✅ Created BUY (COVER) intent for {symbol}: "
                f"{final_qty} lots (Pos: {pos.qty}), Step={triggered_step}"
            )
        
        return signal, intent, detail_info

    def _passes_step_filters(self, filters, metric, is_shorts):
        """Helper to check filters (simplified rewrite of original logic)."""
        if is_shorts:
            # SFStot & BidBuy
            v_sfstot = metric.sfstot if metric.sfstot is not None else 0
            v_bb = metric.bid_buy_ucuzluk if metric.bid_buy_ucuzluk is not None else 0
            
            if 'sfstot_gt' in filters and not (v_sfstot > filters['sfstot_gt']): return False
            if 'sfstot_gte' in filters and not (v_sfstot >= filters['sfstot_gte']): return False
            if 'sfstot_lte' in filters and not (v_sfstot <= filters['sfstot_lte']): return False
            if 'bid_buy_ucuzluk_lt' in filters and not (v_bb < filters['bid_buy_ucuzluk_lt']): return False
            if 'bid_buy_ucuzluk_gte' in filters and not (v_bb >= filters['bid_buy_ucuzluk_gte']): return False
            if 'bid_buy_ucuzluk_lte' in filters and not (v_bb <= filters['bid_buy_ucuzluk_lte']): return False
            return True
        else:
            # FBtot & AskSell
            v_fbtot = metric.fbtot if metric.fbtot is not None else 0
            v_as = metric.ask_sell_pahalilik if metric.ask_sell_pahalilik is not None else 0
            
            if 'fbtot_lt' in filters and not (v_fbtot < filters['fbtot_lt']): return False
            if 'fbtot_gte' in filters and not (v_fbtot >= filters['fbtot_gte']): return False
            if 'fbtot_lte' in filters and not (v_fbtot <= filters['fbtot_lte']): return False
            if 'ask_sell_pahalilik_gt' in filters and not (v_as > filters['ask_sell_pahalilik_gt']): return False
            if 'ask_sell_pahalilik_gte' in filters and not (v_as >= filters['ask_sell_pahalilik_gte']): return False
            if 'ask_sell_pahalilik_lte' in filters and not (v_as <= filters['ask_sell_pahalilik_lte']): return False
            return True

# Global Instance
_karbotu_engine = KarbotuEngine()
def get_karbotu_engine(): return _karbotu_engine
