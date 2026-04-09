"""
LT Trim Engine - Executive Phase 11 Refactor
============================================

Role: "Executive Execution Engine"
-   Consumes SIGNALs from Karbotu (Veto/Bias).
-   Consumes MULTIPLIERs from Reducemore (Sizing Intensity).
-   Consumes RUNTIME CONTROLS (Force Trim, Enable/Disable).
-   Executes the "Ladder" and "Spread Gating" logic.

Input:
    Signals, Multipliers, Rules, Controls, Market Data
Output:
    Intents (Standardized)
"""

import math
import time
import sys
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.decision_models import Intent # Phase 11 Intent Model

class LTTrimEngine:
    """
    LT Trim Engine (Phase 11 Executive)
    Now reads thresholds from GeneralLogicStore (qegenerallogic.csv)
    """
    
    # Default Spread Tables (fallback if GeneralLogicStore not available)
    # Format: (SpreadLimit, ScoreLimit)
    # Logic: If Spread >= SpreadLimit, we accept Score >= ScoreLimit.
    DEFAULT_LONG_SPREAD_THRESHOLDS = [
        (0.06, 0.08),   # Normal Spread -> Need 0.08
        (0.10, 0.05),   # Wide Spread -> Need 0.05
        (0.15, 0.02),   # Very Wide -> Need 0.02
        (0.25, 0.00),   # Huge Spread -> Accept 0.00 (Neutral)
        (0.45, -0.02),  # Massive Spread -> Tolerate slight negative
        (10.0, -0.08)   # Extreme -> Tolerate -0.08 max (User Request)
    ]
    DEFAULT_SHORT_SPREAD_THRESHOLDS = [
        (0.06, -0.08),
        (0.10, -0.05),
        (0.15, -0.02),
        (0.25, 0.00),
        (0.45, 0.02),
        (10.0, 0.08)
    ]
    DEFAULT_LADDER_TARGETS = [0.10, 0.20, 0.40]

    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        # Track daily stats
        self.symbol_stats: Dict[str, Dict[str, Any]] = {}
        self.max_daily_trim_pct = 80.0
        self._last_stats_date: Optional[str] = None  # Track which day stats belong to
        
        # Load thresholds from GeneralLogicStore
        self._load_thresholds()
    
    def _load_thresholds(self):
        """Load thresholds from GeneralLogicStore (qegenerallogic.csv)"""
        try:
            from app.core.general_logic_store import get_general_logic_store
            store = get_general_logic_store()
            
            # Load LONG thresholds
            long_data = store.get("lt_trim.long_spread_thresholds")
            if long_data and isinstance(long_data, list):
                self.LONG_SPREAD_THRESHOLDS = [(float(row[0]), float(row[1])) for row in long_data]
            else:
                self.LONG_SPREAD_THRESHOLDS = self.DEFAULT_LONG_SPREAD_THRESHOLDS
            
            # Load SHORT thresholds
            short_data = store.get("lt_trim.short_spread_thresholds")
            if short_data and isinstance(short_data, list):
                self.SHORT_SPREAD_THRESHOLDS = [(float(row[0]), float(row[1])) for row in short_data]
            else:
                self.SHORT_SPREAD_THRESHOLDS = self.DEFAULT_SHORT_SPREAD_THRESHOLDS
            
            # Load ladder targets
            ladder_data = store.get("lt_trim.ladder_targets")
            if ladder_data and isinstance(ladder_data, list):
                self.LADDER_TARGETS = [float(x) for x in ladder_data]
            else:
                self.LADDER_TARGETS = self.DEFAULT_LADDER_TARGETS
            
            # Load max daily trim percentage
            max_trim = store.get("lt_trim.max_daily_trim_pct")
            if max_trim is not None:
                self.max_daily_trim_pct = float(max_trim)
            
            logger.debug(f"[LT_TRIM] Loaded thresholds from GeneralLogicStore")
        except Exception as e:
            logger.warning(f"[LT_TRIM] Could not load from GeneralLogicStore, using defaults: {e}")
            self.LONG_SPREAD_THRESHOLDS = self.DEFAULT_LONG_SPREAD_THRESHOLDS
            self.SHORT_SPREAD_THRESHOLDS = self.DEFAULT_SHORT_SPREAD_THRESHOLDS
            self.LADDER_TARGETS = self.DEFAULT_LADDER_TARGETS

    async def run(
        self,
        request, # DecisionRequest
        karbotu_signals: Dict[str, Any],
        reducemore_multipliers: Dict[str, Any],
        rules: Dict[str, Any],
        controls: Any, # RuntimeControls object
        account_id: str = "UNKNOWN"
    ) -> Tuple[List[Intent], Dict[str, Any]]:
        """
        Main Execution Cycle.
        """
        import sys
        # print("I AM HERE - LT TRIM ENGINE RUNNING (START)", flush=True)
        intents = []
        

        # Diagnostic tracking
        diagnostic = {
            'analyzed_count': 0,
            'generated_count': 0,
            'skipped_count': 0,
            'details': []
        }

        # 1. Global Enable Check
        if not controls.lt_trim_enabled:
            diagnostic['global_status'] = 'DISABLED'
            logger.warning(f"[LT_TRIM] ⚠️ Engine DISABLED: lt_trim_enabled={controls.lt_trim_enabled}")
            return [], diagnostic
        
        logger.info(f"[LT_TRIM] ✅ Engine ENABLED: Processing {len(request.positions)} positions")

        for position in request.positions:
            symbol = position.symbol
            qty = position.qty
            
            diagnostic['analyzed_count'] += 1
            
            if abs(qty) < 1: 
                diagnostic['details'].append({'symbol': symbol, 'status': 'SKIP_DUST', 'qty': qty})
                continue # Ignore dust
            
            # Taxonomy Check
            if getattr(position, 'strategy_type', 'LT') != 'LT':
                diagnostic['details'].append({'symbol': symbol, 'status': 'SKIP_STRATEGY', 'type': getattr(position, 'strategy_type', 'N/A')})
                continue
            
            # Origin Type Filter: Sadece OV (Overnight) position'ları işle
            origin_type = getattr(position, 'origin_type', 'INT')
            if origin_type != 'OV':
                logger.info(
                    f"[LT_TRIM] ⏭️ {symbol}: SKIP origin_type={origin_type} (need OV) "
                    f"| qty={qty} tag={getattr(position, 'tag', '?')}"
                )
                diagnostic['details'].append({'symbol': symbol, 'status': 'SKIP_ORIGIN', 'origin': origin_type, 'reason': 'INT positions handled by REV orders'})
                continue
            
            # MM Position Filter
            pos_tag = getattr(position, 'tag', '') or ''
            if 'MM' in pos_tag.upper():
                logger.info(f"[LT_TRIM] ⏭️ {symbol}: SKIP MM position (tag={pos_tag}) | qty={qty}")
                diagnostic['details'].append({'symbol': symbol, 'status': 'SKIP_MM_POSITION', 'tag': pos_tag})
                continue
            
            is_long = qty > 0
            if is_long and not controls.lt_trim_long_enabled: 
                logger.info(f"[LT_TRIM] ⏭️ {symbol}: SKIP LONG side disabled | qty={qty}")
                diagnostic['details'].append({'symbol': symbol, 'status': 'SKIP_SIDE_DISABLED', 'side': 'LONG'})
                continue
            if not is_long and not controls.lt_trim_short_enabled: 
                logger.info(f"[LT_TRIM] ⏭️ {symbol}: SKIP SHORT side disabled | qty={qty}")
                diagnostic['details'].append({'symbol': symbol, 'status': 'SKIP_SIDE_DISABLED', 'side': 'SHORT'})
                continue

            # Retrieve Metrics
            metric = request.metrics.get(symbol)
            if not metric:
                logger.info(f"[LT_TRIM] ⏭️ {symbol}: SKIP no metrics data | qty={qty} origin={origin_type}")
                diagnostic['details'].append({'symbol': symbol, 'status': 'SKIP_NO_METRICS'})
                continue
            
            l1 = request.l1_data.get(symbol) if isinstance(request.l1_data, dict) else request.l1_data     
            if not l1: l1 = metric 

            # Intensity Scaling
            intensity = controls.lt_trim_intensity 
            rm_mult = reducemore_multipliers.get(symbol)
            if rm_mult and controls.allow_reducemore_scale:
                intensity *= rm_mult.value

            symbol_intents, reasons, debug_info = self._evaluate_trim(
                position, metric, l1, intensity, rules
            )
            
            status = 'NO_ACTION'
            if symbol_intents:
                status = 'INTENT_GENERATED'
                diagnostic['generated_count'] += len(symbol_intents)
                intents.extend(symbol_intents)
                for _si in symbol_intents:
                    logger.info(
                        f"[LT_TRIM] ✅ {symbol}: {'SELL' if is_long else 'BUY'} {_si.qty} lot "
                        f"| fbtot={metric.fbtot} sfstot={metric.sfstot} gort={metric.gort} "
                        f"ucuz={metric.bid_buy_ucuzluk} pah={metric.ask_sell_pahalilik} "
                        f"bid={metric.bid} ask={metric.ask} last={metric.last} "
                        f"son5={metric.son5_tick} v1h={metric.volav_1h} v4h={metric.volav_4h} "
                        f"score={debug_info.get('score')} spread={debug_info.get('spread')}"
                    )
            else:
                # Log why no action was taken
                score_val = debug_info.get('score')
                spread_val = debug_info.get('spread', 0)
                befday_val = debug_info.get('befday', 0)
                reason_str = ','.join(reasons) if reasons else 'UNKNOWN'
                logger.info(
                    f"[LT_TRIM] ⏭️ {symbol}: NO_ACTION — {reason_str} "
                    f"| qty={qty} befday={befday_val} score={score_val} spread={spread_val:.2f} "
                    f"| bid={metric.bid} ask={metric.ask}"
                )
            
            # Rich detail for diagnostic
            detail = {
                'symbol': symbol,
                'status': status,
                'qty': qty,
                'score': debug_info.get('score'),
                'intensity': intensity,
                'reasons': reasons,
                'debug_info': debug_info
            }
            diagnostic['details'].append(detail)
            
        return intents, diagnostic

    def _evaluate_trim(self, position, metric, l1, intensity, rules):
        """Evaluate single symbol trim logic using 4-Stage Befday Model."""
        intents = []
        symbol = position.symbol
        
        # USE ACTUAL BROKER QTY (not potential_qty!)
        # DECREASE engines must only trim REAL positions, not pending unfilled orders.
        # potential_qty includes open orders (INC+DEC) which inflates the position
        # and causes false trim orders on positions that don't actually exist.
        qty = position.qty
        
        is_long = qty > 0
        abs_qty = abs(qty)
        
        # Befday Qty from Position (Enriched in Snapshot)
        # OV position'lar için befday_qty kullan (INT position'lar zaten filtrelendi)
        befday_qty = getattr(position, 'befday_qty', 0.0)
        abs_befday = abs(befday_qty)
        if abs_befday < 1: 
             # OV position ama befday 0 ise current qty'yi kullan (fallback)
             sys.stderr.write(f"[DEBUG LT_TRIM] Warn: {symbol} OV but befday 0? Using current qty as befday: {abs_qty}\n")
             abs_befday = abs_qty
             
        # Score & Spread
        from app.core.data_fabric import get_data_fabric
        data_fabric = get_data_fabric()
        
        score = None
        if data_fabric:
            fast_snapshot = data_fabric.get_fast_snapshot(symbol)
            if fast_snapshot and fast_snapshot.get('_has_derived'):
                if is_long:
                    score = fast_snapshot.get('ask_sell_pahalilik') or fast_snapshot.get('Ask_sell_pahalilik_skoru')
                else:
                    score = fast_snapshot.get('bid_buy_ucuzluk') or fast_snapshot.get('Bid_buy_ucuzluk_skoru')
        
        if score is None:
            score = metric.ask_sell_pahalilik if is_long else metric.bid_buy_ucuzluk
        
        debug_info = {'score': score, 'spread': 0.0, 'befday': abs_befday}
        
        if score is None:
            return [], ['SCORE_NULL'], debug_info

        # --- SAFETY FLOOR (User Request) ---
        # "Score -0.08 centten yukarı olmak zorunda"
        # 🔧 FIX: Safety floor kontrolünü stage trigger logic'e entegre ettik
        # Burada skip etmiyoruz, çünkü spread gating zaten score kontrolü yapıyor
        # SAFE_FLOOR = -0.08
        # if is_long and score < SAFE_FLOOR:
        #     return [], [f"SCORE_TOO_LOW({score:.2f}<{SAFE_FLOOR})"], debug_info


        # L1 Data
        def _safe_get(obj, key, default=0):
            if obj is None: return default
            if hasattr(obj, 'get'): return obj.get(key, default)
            return getattr(obj, key, default)

        bid = metric.bid if metric.bid is not None else _safe_get(l1, 'bid', 0)
        ask = metric.ask if metric.ask is not None else _safe_get(l1, 'ask', 0)
        bid, ask = (bid or 0), (ask or 0)
        if bid <= 0 or ask <= 0:
            return [], [f"BAD_L1_DATA(bid={bid},ask={ask})"], debug_info
        spread = ask - bid
        debug_info['spread'] = spread
        
        # --- LOGIC BRANCHING ---
        # Branch A: Small Position (< 400)
        # Branch B: Standard Position (>= 400)
        
        needed_sell_qty = 0
        flags_triggered = 0
        triggered_reasons = []
        
        if abs_befday < 400:
            # Special Small Pos Logic
            # Stage 1 (Spread) -> Skipped
            # Stage 2 (Score 0.10) -> Sell 200
            # Stage 3 (Score 0.20) -> Sell Rest (Close)
            
            # Check Stage 2
            limit2 = 0.10
            stage2_met = (is_long and score >= limit2) or (not is_long and score <= -limit2)
            
            # Check Stage 3
            limit3 = 0.20
            stage3_met = (is_long and score >= limit3) or (not is_long and score <= -limit3)
            
            target_sell_total = 0
            
            if stage3_met:
                target_sell_total = abs_befday # Sell All
                triggered_reasons.append(f"SMALL_STAGE3_CLOSE({limit3})")
            elif stage2_met:
                target_sell_total = 200
                triggered_reasons.append(f"SMALL_STAGE2_200({limit2})")
            else:
                # No stages met → do NOT trim (same guard as standard branch)
                return [], ["SMALL_NO_STAGES_MET"], debug_info
            
            # Cap at actual max (abs_befday)
            target_sell_total = min(target_sell_total, abs_befday)
            
            # Calculate needed
            # Target Qty = Abs Befday - Target Sell
            target_qty_abs = abs_befday - target_sell_total
            needed_sell_qty = abs_qty - target_qty_abs
            
            # For small logic, min 200 doesn't strictly apply if we are closing (sell rest).
            # If Stage 2 (200) triggered, we sell 200.
            
        else:
            # Standard 4-Stage Logic
            
            # Stage 1: Spread Gating ("Loose Trim")
            # 🔧 FIX: Spread gating'e safety floor kontrolü eklendi
            thresholds = self.LONG_SPREAD_THRESHOLDS if is_long else self.SHORT_SPREAD_THRESHOLDS
            stage1_met = False
            SAFE_FLOOR = -0.08
            for (spr_limit, score_limit) in thresholds:
                spread_ok = (spread >= spr_limit)
                # Safety floor kontrolü: score en az -0.08 olmalı (LONG için)
                score_meets_floor = (score >= SAFE_FLOOR) if is_long else (score <= abs(SAFE_FLOOR))
                score_ok = (score >= score_limit) if is_long else (score <= score_limit)
                if spread_ok and score_ok and score_meets_floor:
                    stage1_met = True
                    triggered_reasons.append(f"STAGE1_SPREAD(S={spread:.2f})")
                    break
            if stage1_met: flags_triggered += 1
            
            # Stage 2: Ladder 1 (Score 0.10)
            limit2 = 0.10
            if (is_long and score >= limit2) or (not is_long and score <= -limit2):
                flags_triggered += 1
                triggered_reasons.append(f"STAGE2_SCORE({limit2})")

            # Stage 3: Ladder 2 (Score 0.20)
            limit3 = 0.20
            if (is_long and score >= limit3) or (not is_long and score <= -limit3):
                flags_triggered += 1
                triggered_reasons.append(f"STAGE3_SCORE({limit3})")

            # Stage 4: Ladder 3 (Score 0.40)
            limit4 = 0.40
            if (is_long and score >= limit4) or (not is_long and score <= -limit4):
                flags_triggered += 1
                triggered_reasons.append(f"STAGE4_SCORE({limit4})")
                
            if flags_triggered == 0:
                return [], [f"NO_STAGES_MET(score={score:.3f},spread={spread:.3f})"], debug_info
            
            # Calculate Target
            step_size_pct = 20.0 * intensity
            total_sell_pct = flags_triggered * step_size_pct
            total_sell_pct = min(total_sell_pct, self.max_daily_trim_pct)
            
            target_retention_pct = 100.0 - total_sell_pct
            target_qty_abs = abs_befday * (target_retention_pct / 100.0)
            
            needed_sell_qty = abs_qty - target_qty_abs

        # Common Execution Logic
        sys.stderr.write(f"[DEBUG LT_TRIM] {symbol} NeedsSell={needed_sell_qty} (Reasons={','.join(triggered_reasons)})\n")

        final_trim_qty = 0
        
        if needed_sell_qty > 0:
            # Check rounding/min rule (Standard Rule)
            if needed_sell_qty < 200:
                # Force min 200
                final_trim_qty = 200
            else:
                final_trim_qty = int(round(needed_sell_qty / 100.0) * 100)
                if final_trim_qty < 200: final_trim_qty = 200
            
            # 🛡️ OVER-COVER PROTECTION: DECREASE emri ASLA pozisyondan büyük olamaz!
            # Pozisyon min lot'tan küçükse → emir VERİLMEZ, pozisyon olduğu gibi bırakılır.
            if final_trim_qty > abs_qty:
                if abs_qty < 70:
                    triggered_reasons.append(f"POS_TOO_SMALL(pos={abs_qty}<70,need={final_trim_qty})")
                    return intents, triggered_reasons, debug_info  # Return empty
                else:
                    # Pozisyon 70+ ama hesaplanan lot büyük → pozisyon kadarına cap et
                    final_trim_qty = int(abs_qty)
            
            if final_trim_qty > 0:
                price = self._calculate_hidden_price(bid, ask, is_long)
                reason_code = f"LT_STAGE_{flags_triggered if abs_befday >= 400 else 'SMALL'}"
                intents.append(self._create_intent(symbol, final_trim_qty, price, reason_code, is_long))
        
        return intents, triggered_reasons, debug_info

    def _create_intent(self, symbol, qty, price, reason, is_long):
        return Intent(
            symbol=symbol,
            action='SELL' if is_long else 'BUY', # Actually Cover? standardized to BUY/SELL for IBKR
            qty=qty, # Intent qty usually absolute? Or signed? Provider expects signed? 
            # Intent model said qty: int. Usually absolute.
            intent_category='LT_TRIM_MICRO',
            engine_name='LT_TRIM',  # CRITICAL FIX: Set engine name for UI tab routing
            priority=30, # High Priority (> Karbotu 20)
            reason=reason,
            metadata={'price': price, 'hidden': True}
        )

    def _calculate_hidden_price(self, bid, ask, is_long):
        spread = ask - bid
        if is_long: return round(ask - (spread * 0.15), 2)
        return round(bid + (spread * 0.15), 2)

    def _get_stats(self, symbol, qty):
        # Legacy stats for reporting, less critical for logic now driven by Befday
        today = datetime.now().strftime('%Y-%m-%d')
        if self._last_stats_date != today:
            self.symbol_stats.clear()
            self._last_stats_date = today
        if symbol not in self.symbol_stats:
            self.symbol_stats[symbol] = {'trimmed_today_pct': 0.0, 'max_observed_qty': abs(qty)}
        return self.symbol_stats[symbol]

    def _update_stats(self, symbol, qty, max_qty):
        pass # Stats now implicitly handled by Befday comparison

    def reset_stats(self):
        self.symbol_stats.clear()
        self._last_stats_date = None
        
# Global Instance
_lt_trim_engine = LTTrimEngine()
def get_lt_trim_engine(): return _lt_trim_engine

