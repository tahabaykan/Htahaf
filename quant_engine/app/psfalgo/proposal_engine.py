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
        logger.info("ProposalEngine initialized")
    
    def map_decision_to_proposal(
        self,
        decision: Decision,
        cycle_id: int,
        decision_source: str,
        decision_timestamp: datetime,
        market_context: Optional[Dict[str, Any]] = None
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
            return None
        
        # DEDUPLICATION CHECK
        # Create a unique key for this proposal content
        try:
            dedupe_key = f"{decision.symbol}_{decision.action}_{decision.calculated_lot}_{decision.price_hint}"
            now = datetime.now()
            
            # Check if recently proposed (e.g. within last 30 seconds)
            if dedupe_key in self.proposal_dedupe_cache:
                last_ts = self.proposal_dedupe_cache[dedupe_key]
                if (now - last_ts).total_seconds() < 30:  # 30 second suppression
                    # logger.debug(f"[PROPOSAL] Suppressing duplicate proposal {dedupe_key}")
                    return None
            
            # Update cache
            self.proposal_dedupe_cache[dedupe_key] = now
            
            # Cleanup cache occasionally (simple way: if too big)
            if len(self.proposal_dedupe_cache) > 1000:
                self.proposal_dedupe_cache.clear()
                
        except Exception:
            pass  # Don't fail on dedupe error
        
        # Map action to side
        side = None
        if decision.action in ["SELL", "REDUCE"]:
            side = "SELL"
        elif decision.action in ["BUY", "ADD"]:
            side = decision.action  # "BUY" or "ADD"
        else:
            logger.warning(f"[PROPOSAL] Unknown action: {decision.action}")
            return None
        
        # Get quantity
        qty = decision.calculated_lot
        if qty is None or qty <= 0:
            logger.warning(f"[PROPOSAL] Invalid quantity for {decision.symbol}: {qty}")
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
                    
                    # Fill in missing bid/ask/last from snapshot
                    if bid is None:
                        bid = snapshot.get('bid')
                    if ask is None:
                        ask = snapshot.get('ask')
                    if last is None:
                        last = snapshot.get('last')
        except Exception as e:
            logger.debug(f"[PROPOSAL] Could not get extended market context: {e}")
        
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
            bid is not None and
            ask is not None and
            last is not None and
            spread_percent is not None
        )
        if not market_context_complete:
            warnings.append("MARKET_CONTEXT_INCOMPLETE")
        
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
        
        # Determine Book and Order Subtype
        from app.psfalgo.proposal_models import PositionBook, OrderSubtype
        
        # Default Book
        book = PositionBook.LT.value
        if decision_source in ["GREATEST_MM", "SIDEHIT_PRESS", "AURA_MM"]:
            book = PositionBook.MM.value
            
        # Determine Subtype
        order_subtype = OrderSubtype.UNKNOWN.value
        
        if decision_source == "ADDNEWPOS":
            # ADDNEWPOS implies entering/increasing
            if side == "BUY":
                order_subtype = OrderSubtype.LT_LONG_INCREASE.value
            elif side == "SELL": # Short Entry
                order_subtype = OrderSubtype.LT_SHORT_INCREASE.value
                
        elif decision_source in ["KARBOTU", "REDUCEMORE", "LT_TRIM"]:
            # These are REDUCTION/EXIT engines
            if side == "SELL": # Selling Long
                order_subtype = OrderSubtype.LT_LONG_DECREASE.value
            elif side == "BUY": # Covering Short
                order_subtype = OrderSubtype.LT_SHORT_DECREASE.value
                
        # MM Logic (Future placeholder)
        elif book == PositionBook.MM.value:
            if "INCREASE" in str(decision.reason).upper(): # Heuristic
                order_subtype = OrderSubtype.MM_LONG_INCREASE.value if side=="BUY" else OrderSubtype.MM_SHORT_INCREASE.value
            else:
                order_subtype = OrderSubtype.MM_LONG_DECREASE.value if side=="SELL" else OrderSubtype.MM_SHORT_DECREASE.value

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
            # Tags
            book=book,
            order_subtype=order_subtype,
            # Decision context
            engine=decision_source,
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
            potential_qty=decision.potential_qty
        )
        
        # Add warnings if any
        if warnings:
            # Store warnings in proposal (can be added to to_dict/to_human_readable)
            proposal.warnings = warnings
            logger.warning(
                f"[PROPOSAL] Proposal {decision.symbol} has warnings: {', '.join(warnings)}"
            )
        
        logger.debug(
            f"[PROPOSAL] Generated proposal: {decision.symbol} {side} {qty} @ {proposed_price} "
            f"(engine={decision_source}, cycle={cycle_id})"
        )
        
        return proposal
    
    async def process_decision_response(
        self,
        response: DecisionResponse,
        cycle_id: int,
        decision_source: str,
        decision_timestamp: datetime
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
                market_context=market_context
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

