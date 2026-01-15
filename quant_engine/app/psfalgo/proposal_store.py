"""
Proposal Store - Stores and manages OrderProposals

Stores proposals for human review and tracking.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import deque

from app.core.logger import logger
from app.psfalgo.proposal_models import OrderProposal, ProposalStatus


class ProposalStore:
    """
    Proposal Store - stores OrderProposals for human review.
    
    Responsibilities:
    - Store proposals
    - Track proposal lifecycle
    - Provide query interface
    
    Does NOT:
    - Execute proposals
    - Modify proposals (except status updates)
    """
    
    def __init__(self, max_proposals: int = 1000):
        """
        Initialize Proposal Store.
        
        Args:
            max_proposals: Maximum number of proposals to keep (default: 1000)
        """
        self.max_proposals = max_proposals
        
        # Store: {proposal_id: OrderProposal}
        # proposal_id = f"{cycle_id}_{symbol}_{side}_{proposal_ts.timestamp()}"
        self._proposals: Dict[str, OrderProposal] = {}
        
        # Recent proposals (for quick access)
        self._recent_proposals: deque = deque(maxlen=max_proposals)
        
        logger.info(f"ProposalStore initialized (max_proposals={max_proposals})")
    
    def add_proposal(self, proposal: OrderProposal) -> str:
        """
        Add proposal to store.
        
        Args:
            proposal: OrderProposal to add
            
        Returns:
            Proposal ID
        """
        proposal_id = self._generate_proposal_id(proposal)
        
        self._proposals[proposal_id] = proposal
        self._recent_proposals.append(proposal_id)
        
        # Log proposal
        logger.info(f"[PROPOSAL_STORE] Added proposal: {proposal_id}")
        logger.info(f"\n{proposal.to_human_readable()}")
        
        # Cleanup old proposals if needed
        if len(self._proposals) > self.max_proposals:
            self._cleanup_old_proposals()
        
        return proposal_id
    
    def _generate_proposal_id(self, proposal: OrderProposal) -> str:
        """Generate unique proposal ID"""
        return f"{proposal.cycle_id}_{proposal.symbol}_{proposal.side}_{proposal.proposal_ts.timestamp()}"
    
    def get_proposal_id(self, proposal: OrderProposal) -> str:
        """Get proposal ID for a proposal (public method)"""
        return self._generate_proposal_id(proposal)
    
    def get_proposal(self, proposal_id: str) -> Optional[OrderProposal]:
        """Get proposal by ID"""
        return self._proposals.get(proposal_id)
    
    def get_all_proposals(
        self,
        status: Optional[str] = None,
        engine: Optional[str] = None,
        cycle_id: Optional[int] = None,
        limit: int = 100
    ) -> List[OrderProposal]:
        """
        Get all proposals with optional filters.
        
        Args:
            status: Filter by status (PROPOSED, ACCEPTED, REJECTED, EXPIRED)
            engine: Filter by engine (KARBOTU, REDUCEMORE, ADDNEWPOS)
            cycle_id: Filter by cycle ID
            limit: Maximum number of proposals to return
            
        Returns:
            List of OrderProposals
        """
        proposals = list(self._proposals.values())
        
        # Apply filters
        if status:
            proposals = [p for p in proposals if p.status == status]
        if engine:
            proposals = [p for p in proposals if p.engine == engine]
        if cycle_id is not None:
            proposals = [p for p in proposals if p.cycle_id == cycle_id]
        
        # Sort by proposal_ts (newest first)
        proposals.sort(key=lambda p: p.proposal_ts, reverse=True)
        
        # Limit
        return proposals[:limit]
    
    def get_latest_proposals(self, limit: int = 10) -> List[OrderProposal]:
        """Get latest N proposals"""
        proposal_ids = list(self._recent_proposals)[-limit:]
        proposals = [self._proposals[pid] for pid in proposal_ids if pid in self._proposals]
        return proposals
    
    def get_pending_proposals(self) -> List[OrderProposal]:
        """Get all pending proposals (PROPOSED status)"""
        return self.get_all_proposals(status=ProposalStatus.PROPOSED.value, limit=1000)
    
    def update_proposal_status(
        self,
        proposal_id: str,
        status: str,
        human_action: Optional[str] = None
    ) -> bool:
        """
        Update proposal status (for human actions).
        
        Args:
            proposal_id: Proposal ID
            status: New status (ACCEPTED, REJECTED, EXPIRED)
            human_action: Human action ("ACCEPTED", "REJECTED")
            
        Returns:
            True if updated, False if not found
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            logger.warning(f"[PROPOSAL_STORE] Proposal not found: {proposal_id}")
            return False
        
        proposal.status = status
        proposal.human_action = human_action
        proposal.human_action_ts = datetime.now()
        
        logger.info(f"[PROPOSAL_STORE] Updated proposal {proposal_id}: status={status}, action={human_action}")
        return True
    
    def _cleanup_old_proposals(self):
        """Remove old proposals (keep only recent N)"""
        # Sort by proposal_ts (oldest first)
        sorted_proposals = sorted(
            self._proposals.items(),
            key=lambda x: x[1].proposal_ts
        )
        
        # Keep only last max_proposals
        to_remove = len(sorted_proposals) - self.max_proposals
        if to_remove > 0:
            for proposal_id, _ in sorted_proposals[:to_remove]:
                del self._proposals[proposal_id]
                logger.debug(f"[PROPOSAL_STORE] Removed old proposal: {proposal_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get proposal store statistics"""
        proposals = list(self._proposals.values())
        
        stats = {
            'total_proposals': len(proposals),
            'by_status': {},
            'by_engine': {},
            'by_side': {}
        }
        
        for proposal in proposals:
            # By status
            stats['by_status'][proposal.status] = stats['by_status'].get(proposal.status, 0) + 1
            
            # By engine
            stats['by_engine'][proposal.engine] = stats['by_engine'].get(proposal.engine, 0) + 1
            
            # By side
            stats['by_side'][proposal.side] = stats['by_side'].get(proposal.side, 0) + 1
        
        return stats


# Global instance
_proposal_store: Optional[ProposalStore] = None


def get_proposal_store() -> Optional[ProposalStore]:
    """Get global ProposalStore instance"""
    return _proposal_store


def initialize_proposal_store(max_proposals: int = 1000):
    """Initialize global ProposalStore instance"""
    global _proposal_store
    _proposal_store = ProposalStore(max_proposals=max_proposals)
    logger.info("ProposalStore initialized")

