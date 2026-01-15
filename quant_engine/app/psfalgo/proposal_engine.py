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

from datetime import datetime
from typing import Dict, Any, Optional, List

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
        
        # Calculate spread
        spread = None
        spread_percent = None
        if bid and ask and bid > 0 and ask > 0:
            spread = ask - bid
            mid_price = (bid + ask) / 2
            if mid_price > 0:
                spread_percent = (spread / mid_price) * 100
        
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
            price_hint=decision.price_hint
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
                            'bid': symbol_metrics.bid,
                            'ask': symbol_metrics.ask,
                            'last': symbol_metrics.last,
                            'spread': symbol_metrics.spread,
                            'spread_percent': symbol_metrics.spread_percent
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

