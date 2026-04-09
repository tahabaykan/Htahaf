"""
Proposal Engine - Human-in-the-Loop Order Proposals

Maps DecisionResponse → OrderProposal (BEFORE ExecutionIntent).
Generates human-readable order proposals for manual evaluation.

Key Principles:
- ExecutionIntent'tan ÖNCE
- Broker'dan TAMAMEN bağımsız
- Human-readable
- Decision logic'e dokunmaz
- Execution layer'a dokunmaz
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import hashlib

from app.core.logger import logger
from app.psfalgo.decision_models import DecisionResponse, Decision
from app.psfalgo.proposal_models import OrderProposal, ProposalStatus
from app.psfalgo.metrics_snapshot_api import get_metrics_snapshot_api


class ProposalEngine:
    """
    Proposal Engine - generates OrderProposal from DecisionResponse.
    
    Responsibilities:
    - Map Decision → OrderProposal
    - Enrich with market context (bid/ask/last/spread)
    - Generate human-readable proposals
    
    Does NOT:
    - Modify decision engines
    - Create ExecutionIntent
    - Call broker adapter
    """
    
    def __init__(self):
        """Initialize Proposal Engine"""
        self.proposal_dedupe_cache = {}  # key -> timestamp
        logger.info("[PROPOSAL_ENGINE] Initialized (dedupe cache cleared)")
    
    def map_decision_to_proposal(
        self,
        decision: Decision,
        cycle_id: int,
        decision_source: str,
        decision_timestamp: datetime,
        market_context: Optional[Dict[str, Any]] = None,
        account_id: Optional[str] = None
    ) -> Optional[OrderProposal]:
        """
        Map a Decision to OrderProposal.
        
        Args:
            decision: Decision object from decision engine
            cycle_id: RUNALL cycle count
            decision_source: "KARBOTU", "REDUCEMORE", or "ADDNEWPOS"
            decision_timestamp: Timestamp of decision
            market_context: Optional market data (bid/ask/last/spread)
            
        Returns:
            OrderProposal or None if decision is FILTERED
        """
        # Skip filtered decisions
        if decision.action == "FILTERED" or decision.filtered_out:
            logger.debug(f"[PROPOSAL] Skipping filtered decision for {decision.symbol}")
            return None
        
        # DEDUPLICATION CHECK
        # Create a unique key for this proposal content
        try:
            # IDENTICAL CHECK: Include price (rounded to 2 decimals) for true duplicate detection
            price_rounded = round(decision.price_hint or 0, 2) if decision.price_hint else 0
            dedupe_key = f"{decision.symbol}_{decision.action}_{decision.calculated_lot}_{price_rounded}"
            now = datetime.now()
            
            # Check if recently proposed (within last 5 seconds to prevent spam)
            if dedupe_key in self.proposal_dedupe_cache:
                last_ts = self.proposal_dedupe_cache[dedupe_key]
                if (now - last_ts).total_seconds() < 5:  # 5 second suppression (reduced from 30s)
                    logger.debug(f"[PROPOSAL] Suppressing duplicate proposal {dedupe_key} (last seen {(now - last_ts).total_seconds():.1f}s ago)")
                    return None
            
            # Update cache
            self.proposal_dedupe_cache[dedupe_key] = now
            
            # Cleanup cache occasionally (simple way: if too big)
            if len(self.proposal_dedupe_cache) > 1000:
                self.proposal_dedupe_cache.clear()
                
        except Exception as de:
            logger.warning(f"[PROPOSAL] Dedupe error for {decision.symbol}: {de}")
        
        # Map action to side
        # ADDNEWPOS uses SHORT/ADD_SHORT for short entries → map to SELL
        side = None
        if decision.action in ["SELL", "REDUCE", "SHORT", "ADD_SHORT"]:
            side = "SELL"
        elif decision.action in ["BUY", "ADD"]:
            side = decision.action  # "BUY" or "ADD"
        else:
            logger.warning(f"[PROPOSAL] Unknown action for {decision.symbol}: {decision.action}")
            return None
        
        # Get quantity
        qty = decision.calculated_lot
        if qty is None or qty <= 0:
            logger.warning(f"[PROPOSAL] Invalid quantity for {decision.symbol}: {qty} (action={decision.action})")
            return None
        
        # Map order_type from decision
        order_type = "LIMIT"  # Default to LIMIT
        if decision.order_type:
            order_type_str = decision.order_type.upper()
            if "MARKET" in order_type_str:
                order_type = "MARKET"
            elif "LIMIT" in order_type_str:
                order_type = "LIMIT"
        
        # Get price hint (for LIMIT orders)
        proposed_price = decision.price_hint
        
        # Get market context (if provided)
        bid = market_context.get('bid') if market_context else None
        ask = market_context.get('ask') if market_context else None
        last = market_context.get('last') if market_context else None
        
        # Get extended market context from data_fabric
        prev_close = None
        daily_chg = None
        
        # Initialize scores from market_context (Priority 1: Live Computed via MetricComputeEngine)
        bench_chg = market_context.get('benchmark_chg') if market_context else None
        pahalilik_score = market_context.get('as_pahali') if market_context else None
        ucuzluk_score = market_context.get('bb_ucuz') if market_context else None
        
        try:
            from app.core.data_fabric import get_data_fabric
            data_fabric = get_data_fabric()
            if data_fabric:
                snapshot = data_fabric.get_fast_snapshot(decision.symbol)
                if snapshot:
                    prev_close = snapshot.get('prev_close')
                    last_price = snapshot.get('last') or last
                    
                    # Get daily change (in cents, from data_fabric - pre-calculated)
                    daily_chg = snapshot.get('daily_chg')
                    # Fallback: calculate as percentage if not available in cents
                    if daily_chg is None and prev_close and prev_close > 0 and last_price:
                        daily_chg = last_price - prev_close  # Cents
                    
                    # Get benchmark change fallback
                    if bench_chg is None:
                        bench_chg = snapshot.get('bench_chg') or snapshot.get('benchmark_chg')
                    
                    # Get scores fallback (recalculated relative to group benchmark)
                    if pahalilik_score is None:
                        pahalilik_score = snapshot.get('ask_sell_pahalilik') or snapshot.get('Ask_sell_pahalilik_skoru')
                    if ucuzluk_score is None:
                        ucuzluk_score = snapshot.get('bid_buy_ucuzluk') or snapshot.get('Bid_buy_ucuzluk_skoru')
                    
                    # Fill in missing bid/ask/last from snapshot (CRITICAL FALLBACK)
                    if bid is None or bid <= 0:
                        bid = snapshot.get('bid')
                    if ask is None or ask <= 0:
                        ask = snapshot.get('ask')
                    if last is None or last <= 0:
                        last = snapshot.get('last')
        except Exception as e:
            logger.debug(f"[PROPOSAL] Could not get extended market context: {e}")
        
        # Fallback from decision (runall enriches symbol_metrics -> decision.bench_chg / ask_sell_pahalilik for Ask ph / B: in UI)
        if bench_chg is None:
            bench_chg = getattr(decision, 'bench_chg', None)
        if pahalilik_score is None:
            pahalilik_score = getattr(decision, 'ask_sell_pahalilik', None)
        
        # Calculate spread
        spread = None
        spread_percent = None
        if bid and ask and bid > 0 and ask > 0:
            spread = ask - bid
            mid_price = (bid + ask) / 2
            if mid_price > 0:
                spread_percent = (spread / mid_price) * 100
        
        # Calculate Limit Price (User Formula: Bid+Spread*0.15 / Ask-Spread*0.15)
        # Only if price_hint was not provided by decision
        if proposed_price is None and bid is not None and ask is not None and spread is not None:
            SPREAD_FACTOR = 0.15
            if side == 'BUY':
                proposed_price = bid + (spread * SPREAD_FACTOR)
                # Round to 2 decimals
                proposed_price = round(proposed_price, 2)
            elif side == 'SELL':
                proposed_price = ask - (spread * SPREAD_FACTOR)
                proposed_price = round(proposed_price, 2)
        
        # Recalculate Scores based on PROPOSED PRICE (User Request - "Ask Fill" logic)
        # Formula: (ProposedPrice - PrevClose) - BenchmarkChg
        if proposed_price is not None and prev_close is not None and bench_chg is not None:
            try:
                # 1. Calc absolute change from prev close
                proposed_chg = proposed_price - prev_close
                
                # 2. Subtract benchmark change (Alpha)
                # Note: bench_chg is usually small (e.g. 0.05), matching price scale in Janall logic
                dynamic_score = proposed_chg - bench_chg
                
                # 3. Assign to appropriate score
                if side == 'SELL':
                    # Selling: Higher is better (Expensive)
                    pahalilik_score = dynamic_score
                elif side == 'BUY':
                    # Buying: Lower (more negative) is better (Cheap)
                    # Use same formula to be consistent with scanner
                    ucuzluk_score = dynamic_score
            except Exception as e:
                logger.debug(f"[PROPOSAL] Error calc dynamic scores: {e}")
        
        # PHASE 8: Proposal enrichment validation
        warnings = []
        
        # Check market context completeness
        market_context_complete = (
            bid is not None and bid > 0 and
            ask is not None and ask > 0 and
            last is not None and last > 0 and
            spread_percent is not None
        )
        if not market_context_complete:
            warnings.append("MARKET_CONTEXT_INCOMPLETE")
            logger.warning(
                f"[PROPOSAL] Warning for {decision.symbol}: Incomplete Market Context (No Live Data). "
                f"Bid={bid}, Ask={ask}, Last={last}, Spread%={spread_percent}. "
                f"Proposal will be marked invalid in UI if prices are 0."
            )
            # CRITICAL: We still return the proposal but it might have 0 prices if fallbacks failed.
            # However, if bid/ask are 0, proposed_price will be None.
            if proposed_price is None or proposed_price <= 0:
                 logger.error(f"[PROPOSAL] ❌ REJECTED {decision.symbol}: Could not determine proposed price (Bid={bid}, Ask={ask})")
                 return None
        
        # Check decision context completeness
        decision_context_complete = (
            decision.reason and
            len(decision.reason) > 0 and
            decision.metrics_used and
            len(decision.metrics_used) > 0
        )
        if not decision_context_complete:
            warnings.append("DECISION_CONTEXT_INCOMPLETE")
        
        # Build decision thresholds dict to explain WHY this proposal was made
        decision_thresholds = {}
        if decision.metrics_used:
            decision_thresholds = {
                'score_used': pahalilik_score if side == 'SELL' else ucuzluk_score,
                'score_threshold': decision.metrics_used.get('score_threshold'),
                'spread_pct': spread_percent,
                'ladder_step': decision.metrics_used.get('ladder_step'),
                'intensity': decision.metrics_used.get('intensity'),
            }
        
        # ═══════════════════════════════════════════════════════════════
        # DUAL TAG SYSTEM v4
        # ═══════════════════════════════════════════════════════════════
        # POS TAG: MM or LT (from portfolio position)
        # ENGINE TAG: MM, PA, AN, KB, TRIM (from which engine generated)
        # Combined: {POS}_{ENGINE}_{DIRECTION}_{ACTION}
        # ═══════════════════════════════════════════════════════════════
        from app.psfalgo.proposal_models import PositionBook, EngineTag, OrderSubtype
        
        engine_name = decision.engine_name if decision.engine_name else decision_source
        
        # ── ENGINE TAG (which engine generated this order) ──
        engine_tag = "MM"  # Default
        if engine_name in ["GREATEST_MM", "SIDEHIT_PRESS", "AURA_MM"]:
            engine_tag = "MM"
        elif engine_name in ["PATADD", "PATADD_ENGINE"]:
            engine_tag = "PA"
        elif engine_name in ["ADDNEWPOS", "ADDNEWPOS_ENGINE"]:
            engine_tag = "AN"
        elif engine_name in ["KARBOTU", "KARBOTU_V2"]:
            engine_tag = "KB"
        elif engine_name in ["LT_TRIM", "REDUCEMORE"]:
            engine_tag = "TRIM"
        
        # ── POS TAG (what type of position is this in portfolio) ──
        # For INC engines (PA, AN, MM): if no existing position, assign based on engine
        # For DEC engines (KB, TRIM): look up existing position's POS TAG
        pos_tag = "MM"  # Default (migration: all existing = MM)
        current_pos_tag = self._lookup_pos_tag(decision.symbol, account_id)
        current_qty = getattr(decision, 'current_qty', None) or 0
        
        # ═══════════════════════════════════════════════════════════════
        # RULE 1: MM ENGINE BLOCKED ON LT POSITIONS
        # ═══════════════════════════════════════════════════════════════
        # LT pos tag'lı bir hissede MM engine increase yapamaz.
        # KB ve TRIM decrease yapar, MM karışmaz.
        # ═══════════════════════════════════════════════════════════════
        if engine_tag == "MM" and current_pos_tag == "LT" and current_qty != 0:
            logger.warning(
                f"[PROPOSAL] ❌ BLOCKED: {decision.symbol} | MM engine cannot operate "
                f"on LT position (current_qty={current_qty}). KB/TRIM handles LT decrease."
            )
            return None
        
        # ═══════════════════════════════════════════════════════════════
        # RULE 2 & 3: PA/AN vs MM POSITION — DOMINANCE RULES
        # ═══════════════════════════════════════════════════════════════
        if engine_tag in ("PA", "AN") and current_pos_tag == "MM" and current_qty != 0:
            # Determine if PA/AN wants same or opposite direction
            is_long_pos = current_qty > 0
            pa_wants_long = (side == "BUY")
            same_direction = (is_long_pos == pa_wants_long)
            
            if same_direction:
                # ── RULE 2: Same direction → LT baskın, POS TAG = LT ──
                # MM tag'li long +500 var, PA BUY istiyor → POS TAG MM→LT
                pos_tag = "LT"
                logger.info(
                    f"[PROPOSAL] 🏷️ {decision.symbol}: PA/AN same dir → "
                    f"POS TAG MM→LT (qty={current_qty}, engine={engine_tag})"
                )
                # Also update PositionTagStore immediately
                try:
                    from app.psfalgo.position_tag_store import get_position_tag_store
                    store = get_position_tag_store()
                    if store:
                        store.set_tag(decision.symbol, "LT", account_id)
                except Exception:
                    pass
            else:
                # ── RULE 3: Opposite direction → MM tasfiye (0'lama) ──
                # MM tag'li long +500 var, PA SHORT istiyor →
                # MM mağlup → pozisyon 0'lanmalı → tasfiye emri
                # Tasfiye: long ise SELL @ ask-spread*0.15, short ise BUY @ bid+spread*0.15
                logger.warning(
                    f"[PROPOSAL] ⚠️ {decision.symbol}: PA/AN opposite dir! "
                    f"MM position must be liquidated first. "
                    f"current_qty={current_qty}, PA wants {'LONG' if pa_wants_long else 'SHORT'}"
                )
                
                # Generate LIQUIDATION order instead of PA/AN order
                liq_qty = abs(current_qty)
                if is_long_pos:
                    liq_side = "SELL"
                    # ask - spread*0.15 pricing
                    if ask and spread:
                        liq_price = round(ask - (spread * 0.15), 2)
                    else:
                        liq_price = proposed_price  # fallback
                    liq_direction = "LONG_DEC"
                else:
                    liq_side = "BUY"
                    # bid + spread*0.15 pricing
                    if bid and spread:
                        liq_price = round(bid + (spread * 0.15), 2)
                    else:
                        liq_price = proposed_price  # fallback
                    liq_direction = "SHORT_DEC"
                
                # Tasfiye tag: MM_MM_*_DEC (MM DECREASE = en agresif frontlama hakkı)
                pos_tag = "MM"
                engine_tag = "MM"
                order_subtype = f"OZEL_MM_MM_{liq_direction}"
                book = "MM"
                side = liq_side
                qty = liq_qty
                proposed_price = liq_price
                
                logger.info(
                    f"[PROPOSAL] 🔄 {decision.symbol}: OZEL Liquidation order generated: "
                    f"{liq_side} {liq_qty} @ ${liq_price:.2f} | Tag: {order_subtype} "
                    f"(MM_DECREASE = max frontlama sacrifice: $0.60, 50%)"
                )
                
                # Build direction_action and skip to proposal creation
                direction_action = liq_direction
                order_subtype = f"OZEL_{pos_tag}_{engine_tag}_{direction_action}"
                book = pos_tag
                
                # Skip normal tag assignment below
                # (falls through to proposal creation with overridden values)
                # Create proposal with liquidation params
                proposal = OrderProposal(
                    symbol=decision.symbol,
                    side=side,
                    qty=qty,
                    order_type="LIMIT",
                    proposed_price=proposed_price,
                    bid=bid,
                    ask=ask,
                    last=last,
                    spread=spread,
                    spread_percent=spread_percent,
                    prev_close=prev_close,
                    daily_chg=daily_chg,
                    bench_chg=bench_chg,
                    pahalilik_score=pahalilik_score,
                    ucuzluk_score=ucuzluk_score,
                    decision_thresholds=decision_thresholds,
                    book=book,
                    order_subtype=order_subtype,
                    pos_tag=pos_tag,
                    engine_tag=engine_tag,
                    engine=engine_name,
                    reason=f"LT_DOMINANCE_LIQUIDATION: {engine_tag} wants opposite dir, MM pos must close",
                    confidence=1.0,
                    metrics_used=decision.metrics_used or {},
                    cycle_id=cycle_id,
                    decision_ts=decision_timestamp,
                    proposal_ts=datetime.now(),
                    status=ProposalStatus.PROPOSED.value,
                    step_number=decision.step_number,
                    lot_percentage=100.0,
                    price_hint=proposed_price,
                    current_qty=current_qty,
                    potential_qty=0,
                    account_id=account_id
                )
                
                logger.info(
                    f"[PROPOSAL] Generated LIQUIDATION: {decision.symbol} {side} {qty} @ {proposed_price} "
                    f"| Tag: {order_subtype} | POS=MM ENGINE=MM (LT dominance liquidation)"
                )
                return proposal
        
        # ── Normal POS TAG assignment ──
        if engine_tag in ("PA", "AN"):
            pos_tag = "LT"
        elif engine_tag == "MM":
            pos_tag = "MM"
        elif engine_tag in ("KB", "TRIM"):
            pos_tag = current_pos_tag  # Inherit from existing position
        
        # ── DIRECTION + ACTION ──
        if side == "BUY":
            if engine_tag in ("PA", "AN", "MM"):
                direction_action = "LONG_INC"
            else:  # KB, TRIM → buying covers short
                direction_action = "SHORT_DEC"
        else:  # SELL
            if engine_tag in ("PA", "AN", "MM"):
                direction_action = "SHORT_INC"
            else:  # KB, TRIM → selling trims long
                direction_action = "LONG_DEC"
        
        # ── FULL TAG ──
        order_subtype = f"{pos_tag}_{engine_tag}_{direction_action}"
        book = pos_tag  # book = pos_tag for backwards compat
        
        # Create proposal
        proposal = OrderProposal(
            symbol=decision.symbol,
            side=side,
            qty=qty,
            order_type=order_type,
            proposed_price=proposed_price,
            bid=bid,
            ask=ask,
            last=last,
            spread=spread,
            spread_percent=spread_percent,
            # Extended market context
            prev_close=prev_close,
            daily_chg=daily_chg,
            bench_chg=bench_chg,
            pahalilik_score=pahalilik_score,
            ucuzluk_score=ucuzluk_score,
            decision_thresholds=decision_thresholds,
            # Dual Tag System v4
            book=book,
            order_subtype=order_subtype,
            pos_tag=pos_tag,
            engine_tag=engine_tag,
            # Decision context
            engine=engine_name,
            reason=decision.reason,
            confidence=decision.confidence or 0.0,
            metrics_used=decision.metrics_used or {},
            cycle_id=cycle_id,
            decision_ts=decision_timestamp,
            proposal_ts=datetime.now(),
            status=ProposalStatus.PROPOSED.value,
            step_number=decision.step_number,
            lot_percentage=decision.lot_percentage,
            price_hint=decision.price_hint,
            # Position Context (Phase 11 UI)
            current_qty=decision.current_qty,
            potential_qty=decision.potential_qty,
            # Account tagging (CRITICAL for per-account filtering)
            account_id=account_id
        )
        
        # Add warnings if any
        if warnings:
            # Store warnings in proposal (can be added to to_dict/to_human_readable)
            proposal.warnings = warnings
            # DECISION_CONTEXT_INCOMPLETE is informational (some engines don't populate reason/metrics)
            serious_warnings = [w for w in warnings if w != "DECISION_CONTEXT_INCOMPLETE"]
            if serious_warnings:
                logger.warning(
                    f"[PROPOSAL] Proposal {decision.symbol} has warnings: {', '.join(warnings)}"
                )
            else:
                logger.debug(
                    f"[PROPOSAL] Proposal {decision.symbol} minor: {', '.join(warnings)}"
                )
        
        logger.info(
            f"[PROPOSAL] Generated: {decision.symbol} {side} {qty} @ {proposed_price} "
            f"| Tag: {order_subtype} | POS={pos_tag} ENGINE={engine_tag} "
            f"(engine={engine_name}, cycle={cycle_id})"
        )
        
        return proposal
    
    def _lookup_pos_tag(self, symbol: str, account_id: str = None) -> str:
        """
        Look up POS TAG for a symbol from PositionTagStore (per-account).
        
        Returns 'MM' or 'LT'. Defaults to 'MM' (migration default).
        """
        try:
            from app.psfalgo.position_tag_store import get_position_tag_store
            store = get_position_tag_store()
            if store:
                return store.get_tag(symbol, account_id)
        except Exception as e:
            logger.debug(f"[PROPOSAL] POS TAG lookup error for {symbol}: {e}")
        
        return "MM"  # Migration default
    
    async def process_decision_response(
        self,
        response: DecisionResponse,
        cycle_id: int,
        decision_source: str,
        decision_timestamp: datetime,
        account_id: Optional[str] = None
    ) -> List[OrderProposal]:
        """
        Process DecisionResponse and create OrderProposals.
        
        Args:
            response: DecisionResponse from decision engine
            cycle_id: RUNALL cycle count
            decision_source: "KARBOTU", "REDUCEMORE", or "ADDNEWPOS"
            decision_timestamp: Timestamp of decision
            
        Returns:
            List of OrderProposals
        """
        proposals: List[OrderProposal] = []
        
        # Get metrics snapshot API for market context
        metrics_api = get_metrics_snapshot_api()
        
        # Map each decision to proposal
        for decision in response.decisions:
            # Get market context for this symbol
            market_context = None
            if metrics_api:
                try:
                    metrics = await metrics_api.get_metrics_snapshot(
                        symbols=[decision.symbol],
                        snapshot_ts=decision_timestamp
                    )
                    symbol_metrics = metrics.get(decision.symbol)
                    if symbol_metrics:
                        market_context = {
                            'bid': getattr(symbol_metrics, 'bid', None),
                            'ask': getattr(symbol_metrics, 'ask', None),
                            'last': getattr(symbol_metrics, 'last', None),
                            'spread': getattr(symbol_metrics, 'spread', None),
                            'spread_percent': getattr(symbol_metrics, 'spread_percent', None),
                            # FIX Phase 11.2: Use safe getattr for ALL SymbolMetrics fields
                            'bb_ucuz': getattr(symbol_metrics, 'bid_buy_ucuzluk', getattr(symbol_metrics, 'bb_ucuz', 0.0)),
                            'as_pahali': getattr(symbol_metrics, 'ask_sell_pahalilik', getattr(symbol_metrics, 'as_pahali', 0.0)),
                            'benchmark_chg': getattr(symbol_metrics, 'benchmark_chg', getattr(symbol_metrics, 'bench_chg', 0.0))
                        }
                except Exception as e:
                    logger.warning(f"[PROPOSAL] Error getting market context for {decision.symbol}: {e}")
            
            proposal = self.map_decision_to_proposal(
                decision=decision,
                cycle_id=cycle_id,
                decision_source=decision_source,
                decision_timestamp=decision_timestamp,
                market_context=market_context,
                account_id=account_id
            )
            
            if proposal:
                proposals.append(proposal)
        
        logger.info(
            f"[PROPOSAL] Generated {len(proposals)} proposals from {len(response.decisions)} decisions "
            f"(source={decision_source}, cycle={cycle_id})"
        )
        
        return proposals


# Global instance
_proposal_engine: Optional[ProposalEngine] = None


def get_proposal_engine() -> Optional[ProposalEngine]:
    """Get global ProposalEngine instance"""
    return _proposal_engine


def initialize_proposal_engine():
    """Initialize global ProposalEngine instance"""
    global _proposal_engine
    _proposal_engine = ProposalEngine()
    logger.info("ProposalEngine initialized")

