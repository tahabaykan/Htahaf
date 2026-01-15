"""
Trader Mode - Human-First UI

Trader mode for human-first trading assistant.
Algoritma "ne yapacağını" söyler, trader son kararı verir.

Key Principles:
- HUMAN_ONLY mode: ACCEPT/REJECT sadece logging
- Execution ASLA tetiklenmez
- Proposal EXPIRED olabilir
- Decision logic'e dokunmaz
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum

from app.core.logger import logger
from app.psfalgo.proposal_store import get_proposal_store
from app.psfalgo.proposal_models import OrderProposal, ProposalStatus
from app.psfalgo.market_snapshot_store import get_market_snapshot_store


class TraderMode(Enum):
    """Trader mode"""
    HUMAN_ONLY = "HUMAN_ONLY"  # ACCEPT/REJECT sadece logging, execution yok
    PROPOSAL_ONLY = "PROPOSAL_ONLY"  # Sadece proposal üret, ACCEPT/REJECT yok


class TraderModeManager:
    """
    Trader Mode Manager - manages trader mode and proposal lifecycle.
    
    Responsibilities:
    - Manage trader mode (HUMAN_ONLY)
    - Handle ACCEPT/REJECT (logging only)
    - Proposal expiration
    - Daily summary generation
    
    Does NOT:
    - Execute orders
    - Modify decision engines
    - Change dry_run mode
    """
    
    def __init__(self, trader_mode: str = "HUMAN_ONLY"):
        """
        Initialize Trader Mode Manager.
        
        Args:
            trader_mode: "HUMAN_ONLY" or "PROPOSAL_ONLY"
        """
        self.trader_mode = TraderMode(trader_mode)
        self.proposal_expiry_minutes = 5  # Proposals expire after 5 minutes
        
        logger.info(f"TraderModeManager initialized (mode={self.trader_mode.value})")
    
    def accept_proposal(self, proposal_id: str, trader_note: Optional[str] = None) -> Dict[str, Any]:
        """
        Accept proposal (HUMAN_ONLY mode - logging only, no execution).
        
        Args:
            proposal_id: Proposal ID
            trader_note: Optional trader note
            
        Returns:
            Result dict
        """
        proposal_store = get_proposal_store()
        if not proposal_store:
            return {'success': False, 'error': 'ProposalStore not initialized'}
        
        proposal = proposal_store.get_proposal(proposal_id)
        if not proposal:
            return {'success': False, 'error': f'Proposal not found: {proposal_id}'}
        
        # Update status (logging only - no execution)
        proposal_store.update_proposal_status(
            proposal_id=proposal_id,
            status='ACCEPTED',
            human_action='ACCEPTED'
        )
        
        # Log acceptance
        logger.info(
            f"[TRADER] Proposal ACCEPTED: {proposal.symbol} {proposal.side} {proposal.qty} "
            f"@ {proposal.proposed_price} (note: {trader_note or 'none'})"
        )
        
        return {
            'success': True,
            'message': f'Proposal {proposal_id} accepted (logged, no execution)',
            'proposal': proposal.to_dict()
        }
    
    def reject_proposal(self, proposal_id: str, trader_note: Optional[str] = None) -> Dict[str, Any]:
        """
        Reject proposal (HUMAN_ONLY mode - logging only).
        
        Args:
            proposal_id: Proposal ID
            trader_note: Optional trader note (why rejected)
            
        Returns:
            Result dict
        """
        proposal_store = get_proposal_store()
        if not proposal_store:
            return {'success': False, 'error': 'ProposalStore not initialized'}
        
        proposal = proposal_store.get_proposal(proposal_id)
        if not proposal:
            return {'success': False, 'error': f'Proposal not found: {proposal_id}'}
        
        # Update status (logging only)
        proposal_store.update_proposal_status(
            proposal_id=proposal_id,
            status='REJECTED',
            human_action='REJECTED'
        )
        
        # Log rejection
        logger.info(
            f"[TRADER] Proposal REJECTED: {proposal.symbol} {proposal.side} {proposal.qty} "
            f"@ {proposal.proposed_price} (note: {trader_note or 'none'})"
        )
        
        return {
            'success': True,
            'message': f'Proposal {proposal_id} rejected (logged)',
            'proposal': proposal.to_dict()
        }
    
    def expire_old_proposals(self) -> int:
        """
        Expire old proposals (older than expiry time).
        
        Returns:
            Number of expired proposals
        """
        proposal_store = get_proposal_store()
        if not proposal_store:
            return 0
        
        # Get all PROPOSED proposals
        proposals = proposal_store.get_all_proposals(status='PROPOSED', limit=1000)
        
        expired_count = 0
        expiry_time = datetime.now() - timedelta(minutes=self.proposal_expiry_minutes)
        
        for proposal in proposals:
            if proposal.proposal_ts < expiry_time:
                # Get proposal ID from store
                proposal_id = proposal_store.get_proposal_id(proposal)
                proposal_store.update_proposal_status(
                    proposal_id=proposal_id,
                    status='EXPIRED',
                    human_action=None
                )
                expired_count += 1
        
        if expired_count > 0:
            logger.info(f"[TRADER] Expired {expired_count} old proposals")
        
        return expired_count
    
    def generate_daily_summary(self, session_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate daily trader summary.
        
        Args:
            session_date: Date (YYYY-MM-DD), if None uses today
            
        Returns:
            Daily summary report
        """
        if session_date is None:
            session_date = datetime.now().strftime('%Y-%m-%d')
        
        proposal_store = get_proposal_store()
        if not proposal_store:
            return {
                'success': False,
                'error': 'ProposalStore not initialized'
            }
        
        # Get all proposals from today
        all_proposals = proposal_store.get_all_proposals(limit=1000)
        today_proposals = [
            p for p in all_proposals
            if p.proposal_ts.strftime('%Y-%m-%d') == session_date
        ]
        
        # Count by engine
        by_engine = {}
        for prop in today_proposals:
            engine = prop.engine
            by_engine[engine] = by_engine.get(engine, 0) + 1
        
        # Count by status
        by_status = {}
        for prop in today_proposals:
            status = prop.status
            by_status[status] = by_status.get(status, 0) + 1
        
        # Top symbols (by proposal count)
        symbol_counts = {}
        for prop in today_proposals:
            symbol = prop.symbol
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        
        top_symbols = sorted(symbol_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Accepted/Rejected counts
        accepted_count = sum(1 for p in today_proposals if p.status == 'ACCEPTED')
        rejected_count = sum(1 for p in today_proposals if p.status == 'REJECTED')
        expired_count = sum(1 for p in today_proposals if p.status == 'EXPIRED')
        proposed_count = sum(1 for p in today_proposals if p.status == 'PROPOSED')
        
        summary = {
            'session_date': session_date,
            'total_proposals': len(today_proposals),
            'by_engine': by_engine,
            'by_status': by_status,
            'top_symbols': dict(top_symbols),
            'accepted_count': accepted_count,
            'rejected_count': rejected_count,
            'expired_count': expired_count,
            'proposed_count': proposed_count,
            'acceptance_rate': (
                accepted_count / len(today_proposals) * 100
                if len(today_proposals) > 0 else 0
            )
        }
        
        logger.info(f"[TRADER] Daily summary generated for {session_date}: {len(today_proposals)} proposals")
        
        return {
            'success': True,
            'summary': summary
        }


# Global instance
_trader_mode_manager: Optional[TraderModeManager] = None


def get_trader_mode_manager() -> Optional[TraderModeManager]:
    """Get global TraderModeManager instance"""
    return _trader_mode_manager


def initialize_trader_mode_manager(trader_mode: str = "HUMAN_ONLY"):
    """Initialize global TraderModeManager instance"""
    global _trader_mode_manager
    _trader_mode_manager = TraderModeManager(trader_mode=trader_mode)
    logger.info(f"TraderModeManager initialized (mode={trader_mode})")

