"""
KARBOTU Engine V2 - JanallApp Compatible

FBTOT-based step filtering for LONGS (Steps 2-7)
SFSTOT-based step filtering for SHORTS (Steps 8-13)

Execution order: Always after LT_TRIM, before ADDNEWPOS
"""
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.decision_models import (
    PositionSnapshot,
    SymbolMetrics,
    DecisionRequest
)
from app.psfalgo.karbotu_config import get_karbotu_config, KarbotuStepFilter


@dataclass
class KarbotuDecision:
    """KARBOTU decision output"""
    symbol: str
    action: str  # SELL (LONG) or BUY (SHORT cover)
    qty: int
    step: int
    reason: str
    tag: str  # LT_LONG_DECREASE or LT_SHORT_DECREASE
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KarbotuOutput:
    """KARBOTU engine output"""
    decisions: List[KarbotuDecision] = field(default_factory=list)
    diagnostic: Dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0


class KarbotuEngineV2:
    """
    KARBOTU Engine V2 - JanallApp Compatible
    
    Key Changes from V1:
    - Uses FBTOT (not GORT!) for LONG filtering
    - Uses SFSTOT for SHORT filtering  
    - Step-based filtering (2-7 for LONGS, 8-13 for SHORTS)
    - Configurable filters: GORT, FBTOT/SFSTOT, SMA63Chg, pahalilik
    - Lot percentage per step (10-50%)
    """
    
    def __init__(self):
        self.config = get_karbotu_config()
        logger.info("[KARBOTU_V2] Initialized with JanallApp-compatible filtering")
    
    async def run(self, request: DecisionRequest, controls=None, account_id: str = None) -> KarbotuOutput:
        """
        Main execution - process all positions through step filters
        
        Args:
            request: DecisionRequest with positions and metrics
            controls: RuntimeControls with heavy_long_dec/heavy_short_dec flags
            account_id: Account ID for MinMax validation
        
        Returns decisions for positions that pass filters
        """
        start_time = datetime.now()
        output = KarbotuOutput()
        
        # Extract HEAVY mode flags
        heavy_long = getattr(controls, 'heavy_long_dec', False) if controls else False
        heavy_short = getattr(controls, 'heavy_short_dec', False) if controls else False
        
        diagnostic = {
            'total_positions': len(request.positions),
            'longs_count': 0,
            'shorts_count': 0,
            'long_decisions': 0,
            'short_decisions': 0,
            'long_steps_triggered': {},
            'short_steps_triggered': {},
            'filtered_out': 0,
            'heavy_long_mode': heavy_long,
            'heavy_short_mode': heavy_short
        }
        
        try:
            # Separate LONGS and SHORTS
            longs = [p for p in request.positions if p.qty > 0]
            shorts = [p for p in request.positions if p.qty < 0]
            
            diagnostic['longs_count'] = len(longs)
            diagnostic['shorts_count'] = len(shorts)
            
            # Process LONGS (Steps 2-7)
            for pos in longs:
                decision = await self._process_long_position(pos, request.metrics, heavy_long, account_id, controls)
                if decision:
                    output.decisions.append(decision)
                    diagnostic['long_decisions'] += 1
                    step_key = f"step_{decision.step}"
                    diagnostic['long_steps_triggered'][step_key] = diagnostic['long_steps_triggered'].get(step_key, 0) + 1
                else:
                    diagnostic['filtered_out'] += 1
            
            # Process SHORTS (Steps 8-13)
            for pos in shorts:
                decision = await self._process_short_position(pos, request.metrics, heavy_short, account_id, controls)
                if decision:
                    output.decisions.append(decision)
                    diagnostic['short_decisions'] += 1
                    step_key = f"step_{decision.step}"
                    diagnostic['short_steps_triggered'][step_key] = diagnostic['short_steps_triggered'].get(step_key, 0) + 1
                else:
                    diagnostic['filtered_out'] += 1
            
            output.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log summary
            logger.info("=" * 80)
            logger.info("[KARBOTU_V2 DIAGNOSTIC] Cycle Summary:")
            logger.info(f"  Positions: {diagnostic['total_positions']} (Longs: {diagnostic['longs_count']}, Shorts: {diagnostic['shorts_count']})")
            logger.info(f"  Decisions: {len(output.decisions)} (Longs: {diagnostic['long_decisions']}, Shorts: {diagnostic['short_decisions']})")
            logger.info(f"  Filtered Out: {diagnostic['filtered_out']}")
            
            if diagnostic['long_steps_triggered']:
                logger.info(f"  LONG Steps Triggered: {diagnostic['long_steps_triggered']}")
            if diagnostic['short_steps_triggered']:
                logger.info(f"  SHORT Steps Triggered: {diagnostic['short_steps_triggered']}")
            
            logger.info("=" * 80)
            
            output.diagnostic = diagnostic
            return output
        
        except Exception as e:
            logger.error(f"[KARBOTU_V2] Error in run: {e}", exc_info=True)
            output.diagnostic = diagnostic
            return output
    
    async def _process_long_position(
        self, 
        pos: PositionSnapshot, 
        metrics: Dict[str, SymbolMetrics],
        heavy_mode: bool = False,
        account_id: str = None,
        controls = None
    ) -> Optional[KarbotuDecision]:
        """
        Process LONG position through Steps 2-7
        
        Args:
            heavy_mode: If True, bypass FBTOT/GORT filters - only use pahalilik score
            account_id: Account ID for MinMax validation
            controls: RuntimeControls with heavy_lot_pct, heavy_long_threshold
        
        Returns first triggered decision (or None)
        """
        metric = metrics.get(pos.symbol)
        if not metric:
            logger.debug(f"[KARBOTU_V2] No metrics for {pos.symbol}, skipping")
            return None
        
        # HEAVY MODE: Bypass all filters, only check pahalilik score
        # CRITICAL: Uses potential_qty (current + open orders) to account for LT_TRIM decisions
        if heavy_mode:
            pahalilik = getattr(metric, 'ask_sell_pahalilik', None)
            if pahalilik is None:
                return None
            
            # Get configurable thresholds from controls (or use defaults)
            HEAVY_THRESHOLD = getattr(controls, 'heavy_long_threshold', 0.02) if controls else 0.02
            HEAVY_LOT_PCT = getattr(controls, 'heavy_lot_pct', 30) if controls else 30
            
            if pahalilik >= HEAVY_THRESHOLD:
                # USE ACTUAL BROKER QTY (not potential_qty!)
                # DECREASE engines must only trim REAL positions.
                effective_qty = pos.qty
                if effective_qty <= 0:
                    logger.debug(f"[KARBOTU_V2] {pos.symbol} HEAVYLONGDEC: potential_qty={effective_qty} <= 0, skipping")
                    return None
                
                lot_qty = self._calculate_lot_qty(effective_qty, HEAVY_LOT_PCT)
                
                # 🛡️ OVER-COVER PROTECTION: DECREASE emri ASLA pozisyondan büyük olamaz!
                # Bu kural pozisyon flip'ini (SHORT→LONG veya LONG→SHORT) kesinlikle önler.
                lot_qty = min(lot_qty, int(effective_qty))
                
                # 400-LOT RULE: If final potential would be < 400, close position to 0
                # MUST come BEFORE min-lot check!
                final_potential = effective_qty - lot_qty
                if 0 < final_potential < 400:
                    lot_qty = int(effective_qty)  # Close entire position
                    logger.info(
                        f"[KARBOTU_V2] {pos.symbol} 400-LOT RULE: "
                        f"would leave {final_potential:.0f} → closing to 0 (lot={lot_qty})"
                    )
                
                if lot_qty < 70:
                    logger.info(
                        f"[KARBOTU_V2] {pos.symbol} HEAVYLONGDEC: qty={lot_qty} < 70 min lot, "
                        f"position too small to decrease — SKIPPING (pos={effective_qty})"
                    )
                    return None
                
                # MinMax Validation - Ensure we don't exceed todays_min_qty
                if account_id and lot_qty > 0:
                    from app.psfalgo.minmax_area_service import get_minmax_area_service, get_max_sell_qty
                    minmax_svc = get_minmax_area_service()
                    minmax_row = minmax_svc.get_row(account_id, pos.symbol)
                    if minmax_row:
                        max_sell = get_max_sell_qty(minmax_row, pos.qty)
                        if lot_qty > max_sell:
                            if max_sell < 100:
                                logger.info(f"[KARBOTU_V2] {pos.symbol} HEAVYLONGDEC: MinMax cap={max_sell} < 100, skipping")
                                return None
                            lot_qty = max_sell
                            logger.info(f"[KARBOTU_V2] {pos.symbol} HEAVYLONGDEC: Capped to MinMax limit {lot_qty}")
                
                decision = KarbotuDecision(
                    symbol=pos.symbol,
                    action='SELL',
                    qty=lot_qty,
                    step=0,  # Step 0 = HEAVY mode
                    reason=f'HEAVYLONGDEC: ASK_SELL={pahalilik:.4f} >= {HEAVY_THRESHOLD}',
                    tag='HEAVYLONGDEC',
                    metadata={
                        'step': 0,
                        'heavy_mode': True,
                        'ask_sell_pahalilik': pahalilik,
                        'lot_pct': HEAVY_LOT_PCT,
                        'original_qty': pos.qty,
                        'effective_qty': effective_qty  # Qty after LT_TRIM considered
                    }
                )
                
                logger.info(
                    f"[KARBOTU_V2] {pos.symbol} HEAVYLONGDEC: "
                    f"SELL {lot_qty} lots ({HEAVY_LOT_PCT}% of {effective_qty}), pahalilik={pahalilik:.4f} "
                    f"| fbtot={metric.fbtot} sfstot={metric.sfstot} gort={metric.gort} "
                    f"ucuz={metric.bid_buy_ucuzluk} bid={metric.bid} ask={metric.ask} last={metric.last} "
                    f"son5={metric.son5_tick} v1h={metric.volav_1h} v4h={metric.volav_4h}"
                )
                
                return decision
            
            return None  # Pahalilik too low
        
        # NORMAL MODE: Use step filters
        # Get enabled LONG filters
        long_filters = self.config.get_enabled_filters('LONGS')
        
        # Try each step in order (2-7)
        for step_filter in sorted(long_filters, key=lambda x: x.step):
            if self._passes_long_filters(metric, step_filter):
                # USE ACTUAL BROKER QTY (not potential_qty!)
                # DECREASE engines must only trim REAL positions.
                effective_qty = pos.qty
                if effective_qty <= 0:
                    logger.debug(
                        f"[KARBOTU_V2] {pos.symbol} Step {step_filter.step}: "
                        f"potential_qty={effective_qty} <= 0, skipping (LT_TRIM consumed all)"
                    )
                    continue
                
                # Calculate lot qty
                lot_qty = self._calculate_lot_qty(effective_qty, step_filter.lot_percentage)
                
                # 🛡️ OVER-COVER PROTECTION: DECREASE emri ASLA pozisyondan büyük olamaz!
                lot_qty = min(lot_qty, int(effective_qty))
                
                # 400-LOT RULE: If remaining position < 400, close entire position
                # MUST come BEFORE min-lot check! (same logic as SHORT side)
                final_remaining = effective_qty - lot_qty
                if 0 < final_remaining < 400:
                    lot_qty = int(effective_qty)
                    logger.info(
                        f"[KARBOTU_V2] {pos.symbol} Step {step_filter.step} 400-LOT RULE: "
                        f"would leave {final_remaining:.0f} → closing to 0 (lot={lot_qty})"
                    )
                
                if lot_qty < 70:
                    logger.info(
                        f"[KARBOTU_V2] {pos.symbol} Step {step_filter.step}: qty={lot_qty} < 70 min lot, "
                        f"position too small to decrease — SKIPPING (pos={effective_qty})"
                    )
                    continue  # Try next step
                
                # MinMax Validation (same as HEAVY mode)
                if account_id and lot_qty > 0:
                    from app.psfalgo.minmax_area_service import get_minmax_area_service, get_max_sell_qty
                    minmax_svc = get_minmax_area_service()
                    minmax_row = minmax_svc.get_row(account_id, pos.symbol)
                    if minmax_row:
                        max_sell = get_max_sell_qty(minmax_row, pos.qty)
                        if lot_qty > max_sell:
                            if max_sell < 125:
                                logger.info(f"[KARBOTU_V2] {pos.symbol} Step {step_filter.step}: MinMax cap={max_sell} < 125, skipping")
                                continue  # Try next step
                            lot_qty = max_sell
                            logger.info(f"[KARBOTU_V2] {pos.symbol} Step {step_filter.step}: Capped to MinMax limit {lot_qty}")
                
                # Look up POS TAG from Redis for v4 tag
                _pos_tag = 'MM'
                try:
                    from app.psfalgo.position_tag_store import get_position_tag_store
                    _store = get_position_tag_store()
                    if _store:
                        _pos_tag = _store.get_tag(pos.symbol, account_id)
                except Exception:
                    pass
                
                decision = KarbotuDecision(
                    symbol=pos.symbol,
                    action='SELL',
                    qty=lot_qty,
                    step=step_filter.step,
                    reason=f'KARBOTU Step {step_filter.step}: FBTOT={metric.fbtot:.2f}, ASK_SELL={metric.ask_sell_pahalilik:.4f}',
                    tag=f'{_pos_tag}_KB_LONG_DEC',
                    metadata={
                        'step': step_filter.step,
                        'fbtot': metric.fbtot,
                        'gort': metric.gort,
                        'sma63chg': getattr(metric, 'sma63chg', None),
                        'ask_sell_pahalilik': metric.ask_sell_pahalilik,
                        'lot_pct': step_filter.lot_percentage,
                        'original_qty': pos.qty,
                        'effective_qty': effective_qty  # Qty after LT_TRIM considered
                    }
                )
                
                logger.info(
                    f"[KARBOTU_V2] {pos.symbol} LONG Step {step_filter.step}: "
                    f"SELL {lot_qty} lots ({step_filter.lot_percentage}% of {effective_qty}) "
                    f"| fbtot={metric.fbtot} sfstot={metric.sfstot} gort={metric.gort} "
                    f"ucuz={metric.bid_buy_ucuzluk} pah={metric.ask_sell_pahalilik} "
                    f"bid={metric.bid} ask={metric.ask} last={metric.last} "
                    f"son5={metric.son5_tick} v1h={metric.volav_1h} v4h={metric.volav_4h}"
                )
                
                return decision  # Return first triggered step
        
        # No step filter passed — log why
        _fbtot = metric.fbtot if metric.fbtot is not None else 0.0
        _pah = metric.ask_sell_pahalilik if metric.ask_sell_pahalilik is not None else 0.0
        _gort = metric.gort if metric.gort is not None else 0.0
        logger.info(
            f"[KARBOTU_V2] ⏭️ {pos.symbol} LONG: No step triggered "
            f"| fbtot={_fbtot:.3f} pah={_pah:.4f} "
            f"gort={_gort:.2f} bid={metric.bid} ask={metric.ask} "
            f"| Steps checked: {[sf.step for sf in long_filters]}"
        )
        return None
    
    async def _process_short_position(
        self,
        pos: PositionSnapshot,
        metrics: Dict[str, SymbolMetrics],
        heavy_mode: bool = False,
        account_id: str = None,
        controls = None
    ) -> Optional[KarbotuDecision]:
        """
        Process SHORT position through Steps 8-13
        
        Args:
            heavy_mode: If True, bypass SFSTOT/GORT filters - only use ucuzluk score
            account_id: Account ID for MinMax validation
            controls: RuntimeControls with heavy_lot_pct, heavy_short_threshold
        
        Returns first triggered decision (or None)
        """
        metric = metrics.get(pos.symbol)
        if not metric:
            logger.debug(f"[KARBOTU_V2] No metrics for {pos.symbol}, skipping")
            return None
        
        # HEAVY MODE: Bypass all filters, only check ucuzluk score
        # CRITICAL: Uses potential_qty (current + open orders) to account for LT_TRIM decisions
        if heavy_mode:
            ucuzluk = getattr(metric, 'bid_buy_ucuzluk', None)
            if ucuzluk is None:
                return None
            
            # Get configurable thresholds from controls (or use defaults)
            HEAVY_THRESHOLD = getattr(controls, 'heavy_short_threshold', -0.02) if controls else -0.02
            HEAVY_LOT_PCT = getattr(controls, 'heavy_lot_pct', 30) if controls else 30
            
            if ucuzluk <= HEAVY_THRESHOLD:
                # USE ACTUAL BROKER QTY (not potential_qty!)
                # DECREASE engines must only trim REAL positions.
                effective_qty = abs(pos.qty)
                if effective_qty <= 0:
                    logger.debug(f"[KARBOTU_V2] {pos.symbol} HEAVYSHORTDEC: potential_qty=0, skipping")
                    return None
                
                lot_qty = self._calculate_lot_qty(effective_qty, HEAVY_LOT_PCT)
                
                # 🛡️ OVER-COVER PROTECTION: DECREASE emri ASLA pozisyondan büyük olamaz!
                lot_qty = min(lot_qty, int(effective_qty))
                
                # 400-LOT RULE: If final potential would be < 400, close position to 0
                # MUST come BEFORE min-lot check!
                final_potential = effective_qty - lot_qty
                if 0 < final_potential < 400:
                    lot_qty = int(effective_qty)  # Close entire position
                    logger.info(
                        f"[KARBOTU_V2] {pos.symbol} 400-LOT RULE: "
                        f"would leave {final_potential:.0f} → closing to 0 (lot={lot_qty})"
                    )
                
                if lot_qty < 70:
                    logger.info(
                        f"[KARBOTU_V2] {pos.symbol} HEAVYSHORTDEC: qty={lot_qty} < 70 min lot, "
                        f"position too small to decrease — SKIPPING (pos={effective_qty})"
                    )
                    return None
                
                # MinMax Validation - Ensure we don't exceed todays_max_qty (for shorts, BUY covers = toward max)
                if account_id and lot_qty > 0:
                    from app.psfalgo.minmax_area_service import get_minmax_area_service, get_max_buy_qty
                    minmax_svc = get_minmax_area_service()
                    minmax_row = minmax_svc.get_row(account_id, pos.symbol)
                    if minmax_row:
                        max_buy = get_max_buy_qty(minmax_row, pos.qty)
                        if lot_qty > max_buy:
                            if max_buy < 100:
                                logger.info(f"[KARBOTU_V2] {pos.symbol} HEAVYSHORTDEC: MinMax cap={max_buy} < 100, skipping")
                                return None
                            lot_qty = max_buy
                            logger.info(f"[KARBOTU_V2] {pos.symbol} HEAVYSHORTDEC: Capped to MinMax limit {lot_qty}")
                
                decision = KarbotuDecision(
                    symbol=pos.symbol,
                    action='BUY',  # Cover short
                    qty=lot_qty,
                    step=0,  # Step 0 = HEAVY mode
                    reason=f'HEAVYSHORTDEC: BID_BUY={ucuzluk:.4f} <= {HEAVY_THRESHOLD}',
                    tag='HEAVYSHORTDEC',
                    metadata={
                        'step': 0,
                        'heavy_mode': True,
                        'bid_buy_ucuzluk': ucuzluk,
                        'lot_pct': HEAVY_LOT_PCT,
                        'original_qty': pos.qty,
                        'effective_qty': effective_qty  # Qty after LT_TRIM considered
                    }
                )
                
                logger.info(
                    f"[KARBOTU_V2] {pos.symbol} HEAVYSHORTDEC: "
                    f"BUY {lot_qty} lots ({HEAVY_LOT_PCT}% of {effective_qty}), ucuzluk={ucuzluk:.4f} "
                    f"| fbtot={metric.fbtot} sfstot={metric.sfstot} gort={metric.gort} "
                    f"pah={metric.ask_sell_pahalilik} bid={metric.bid} ask={metric.ask} last={metric.last} "
                    f"son5={metric.son5_tick} v1h={metric.volav_1h} v4h={metric.volav_4h}"
                )
                
                return decision
            
            return None  # Ucuzluk not low enough
        
        # NORMAL MODE: Use step filters
        # Get enabled SHORT filters
        short_filters = self.config.get_enabled_filters('SHORTS')
        
        # Try each step in order (9-14)
        for step_filter in sorted(short_filters, key=lambda x: x.step):
            if self._passes_short_filters(metric, step_filter):
                # USE ACTUAL BROKER QTY (not potential_qty!)
                # DECREASE engines must only trim REAL positions.
                effective_qty = abs(pos.qty)
                if effective_qty <= 0:
                    logger.debug(
                        f"[KARBOTU_V2] {pos.symbol} Step {step_filter.step}: "
                        f"potential_qty=0, skipping (LT_TRIM consumed all)"
                    )
                    continue
                
                # Calculate lot qty (use abs for shorts)
                lot_qty = self._calculate_lot_qty(effective_qty, step_filter.lot_percentage)
                
                # 🛡️ OVER-COVER PROTECTION: DECREASE emri ASLA pozisyondan büyük olamaz!
                lot_qty = min(lot_qty, int(effective_qty))
                
                # 400-LOT RULE: If remaining position < 400, close entire position
                # MUST come BEFORE min-lot check! Otherwise small positions get stuck:
                # e.g. 284 lots → calculate 100 (50% rounded) → 100<125 SKIP → never reaches 400-rule
                # Correct: 284→100 → remaining=184<400 → close all 284 → 284>125 OK!
                final_remaining = effective_qty - lot_qty
                if 0 < final_remaining < 400:
                    lot_qty = int(effective_qty)
                    logger.info(
                        f"[KARBOTU_V2] {pos.symbol} Step {step_filter.step} 400-LOT RULE: "
                        f"would leave {final_remaining:.0f} → closing to 0 (lot={lot_qty})"
                    )
                
                if lot_qty < 70:
                    logger.info(
                        f"[KARBOTU_V2] {pos.symbol} Step {step_filter.step}: qty={lot_qty} < 70 min lot, "
                        f"position too small to decrease — SKIPPING (pos={effective_qty})"
                    )
                    continue  # Try next step
                
                # MinMax Validation (same as HEAVY mode)
                if account_id and lot_qty > 0:
                    from app.psfalgo.minmax_area_service import get_minmax_area_service, get_max_buy_qty
                    minmax_svc = get_minmax_area_service()
                    minmax_row = minmax_svc.get_row(account_id, pos.symbol)
                    if minmax_row:
                        max_buy = get_max_buy_qty(minmax_row, abs(pos.qty))
                        if lot_qty > max_buy:
                            if max_buy < 125:
                                logger.info(f"[KARBOTU_V2] {pos.symbol} Step {step_filter.step}: MinMax cap={max_buy} < 125, skipping")
                                continue  # Try next step
                            lot_qty = max_buy
                            logger.info(f"[KARBOTU_V2] {pos.symbol} Step {step_filter.step}: Capped to MinMax limit {lot_qty}")
                
                # Look up POS TAG from Redis for v4 tag
                _pos_tag = 'MM'
                try:
                    from app.psfalgo.position_tag_store import get_position_tag_store
                    _store = get_position_tag_store()
                    if _store:
                        _pos_tag = _store.get_tag(pos.symbol, account_id)
                except Exception:
                    pass
                
                decision = KarbotuDecision(
                    symbol=pos.symbol,
                    action='BUY',  # Cover short
                    qty=lot_qty,
                    step=step_filter.step,
                    reason=f'KARBOTU Step {step_filter.step}: SFSTOT={metric.sfstot:.2f}, BID_BUY={metric.bid_buy_ucuzluk:.4f}',
                    tag=f'{_pos_tag}_KB_SHORT_DEC',
                    metadata={
                        'step': step_filter.step,
                        'sfstot': metric.sfstot,
                        'gort': metric.gort,
                        'sma63chg': getattr(metric, 'sma63chg', None),
                        'bid_buy_ucuzluk': metric.bid_buy_ucuzluk,
                        'lot_pct': step_filter.lot_percentage,
                        'original_qty': pos.qty,
                        'effective_qty': effective_qty  # Qty after LT_TRIM considered
                    }
                )
                
                logger.info(
                    f"[KARBOTU_V2] {pos.symbol} SHORT Step {step_filter.step}: "
                    f"BUY {lot_qty} lots ({step_filter.lot_percentage}% of {effective_qty}) "
                    f"| fbtot={metric.fbtot} sfstot={metric.sfstot} gort={metric.gort} "
                    f"ucuz={metric.bid_buy_ucuzluk} pah={metric.ask_sell_pahalilik} "
                    f"bid={metric.bid} ask={metric.ask} last={metric.last} "
                    f"son5={metric.son5_tick} v1h={metric.volav_1h} v4h={metric.volav_4h}"
                )
                
                return decision
        
        # No step filter passed — log why
        _sfstot = metric.sfstot if metric.sfstot is not None else 0.0
        _ucuz = metric.bid_buy_ucuzluk if metric.bid_buy_ucuzluk is not None else 0.0
        _gort = metric.gort if metric.gort is not None else 0.0
        logger.info(
            f"[KARBOTU_V2] ⏭️ {pos.symbol} SHORT: No step triggered "
            f"| sfstot={_sfstot:.3f} ucuz={_ucuz:.4f} "
            f"gort={_gort:.2f} bid={metric.bid} ask={metric.ask} "
            f"| Steps checked: {[sf.step for sf in short_filters]}"
        )
        return None
    
    def _passes_long_filters(self, metric: SymbolMetrics, step_filter: KarbotuStepFilter) -> bool:
        """
        Check if metric passes all filters for LONG position
        
        Filters checked:
        1. FBTOT range
        2. GORT range (optional, -999 = skip)
        3. SMA63Chg range (optional, -999 = skip)
        4. ask_sell_pahalilik range
        """
        # Check FBTOT
        if not hasattr(metric, 'fbtot') or metric.fbtot is None:
            return False
        
        if not (step_filter.fbtot_min <= metric.fbtot <= step_filter.fbtot_max):
            return False
        
        # Check GORT (optional)
        if step_filter.gort_min != -999:
            if not hasattr(metric, 'gort') or metric.gort is None:
                return False
            if not (step_filter.gort_min <= metric.gort <= step_filter.gort_max):
                return False
        
        # Check SMA63Chg (optional)
        if step_filter.sma63chg_min != -999:
            if not hasattr(metric, 'sma63chg') or metric.sma63chg is None:
                return False
            if not (step_filter.sma63chg_min <= metric.sma63chg <= step_filter.sma63chg_max):
                return False
        
        # Check ask_sell_pahalilik
        if not hasattr(metric, 'ask_sell_pahalilik') or metric.ask_sell_pahalilik is None:
            return False
        
        if not (step_filter.pahalilik_min <= metric.ask_sell_pahalilik <= step_filter.pahalilik_max):
            return False
        
        return True
    
    def _passes_short_filters(self, metric: SymbolMetrics, step_filter: KarbotuStepFilter) -> bool:
        """
        Check if metric passes all filters for SHORT position
        
        Filters checked:
        1. SFSTOT range (stored in fbt_min/max columns)
        2. GORT range (optional)
        3. SMA63Chg range (optional)
        4. bid_buy_ucuzluk range (stored in pahalilik_min/max)
        """
        # Check SFSTOT
        if not hasattr(metric, 'sfstot') or metric.sfstot is None:
            return False
        
        if not (step_filter.fbtot_min <= metric.sfstot <= step_filter.fbtot_max):
            return False
        
        # Check GORT (optional)
        if step_filter.gort_min != -999:
            if not hasattr(metric, 'gort') or metric.gort is None:
                return False
            if not (step_filter.gort_min <= metric.gort <= step_filter.gort_max):
                return False
        
        # Check SMA63Chg (optional)
        if step_filter.sma63chg_min != -999:
            if not hasattr(metric, 'sma63chg') or metric.sma63chg is None:
                return False
            if not (step_filter.sma63chg_min <= metric.sma63chg <= step_filter.sma63chg_max):
                return False
        
        # Check bid_buy_ucuzluk
        if not hasattr(metric, 'bid_buy_ucuzluk') or metric.bid_buy_ucuzluk is None:
            return False
        
        if not (step_filter.pahalilik_min <= metric.bid_buy_ucuzluk <= step_filter.pahalilik_max):
            return False
        
        return True
    
    def _calculate_lot_qty(self, qty: float, percentage: int) -> int:
        """
        Calculate lot quantity with 100-LOT ROUNDING (DOWN)
        
        Args:
            qty: Position quantity (or potential_qty)
            percentage: Lot percentage (10-50%)
        
        Returns:
            Rounded lot quantity (minimum 125 as raw calculation)
            
        IMPORTANT: Callers MUST enforce OVER-COVER PROTECTION:
            lot_qty = min(lot_qty, abs(position))
            if lot_qty < 125: SKIP the order (don't place it)
            
        Examples:
            528 -> 500 (round DOWN to nearest 100)
            266 -> 200 (round DOWN)
            1000 * 30% = 300 -> 300
            150 * 50% = 75 -> 125 (minimum raw output)
            28 * 50% = 14 -> 125 (minimum raw) -> caller caps to 28 -> caller skips (28 < 125)
        """
        calculated = qty * (percentage / 100.0)
        
        # Round DOWN to nearest 100 (528 -> 500, not 600)
        # Min lot for decrease orders is 70 (not 125/200)
        if calculated < 70:
            return 70  # Minimum 70 lot for decrease
        else:
            return int(calculated // 100) * 100


# Global instance
_karbotu_engine_v2 = None

def get_karbotu_engine_v2() -> KarbotuEngineV2:
    """Get global KARBOTU V2 engine instance"""
    global _karbotu_engine_v2
    if _karbotu_engine_v2 is None:
        _karbotu_engine_v2 = KarbotuEngineV2()
    return _karbotu_engine_v2
