"""
Strategy Orchestrator

Coordinates all strategy engines and aggregates their proposals.

Responsibilities:
- Load MarketSnapshot and PositionSnapshot
- Run enabled strategies sequentially
- Aggregate all OrderProposals
- Send to ProposalStore

Does NOT:
- Execute orders
- Modify decision engines
- Call broker APIs
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.proposal_models import OrderProposal
from app.psfalgo.market_snapshot_models import MarketSnapshot
from app.psfalgo.decision_models import PositionSnapshot
from app.strategies.strategy_context import StrategyContext

# Import strategies
from app.strategies.take_profit_longs import generate_proposals as take_profit_longs_generate
from app.strategies.take_profit_shorts import generate_proposals as take_profit_shorts_generate
from app.strategies.addnewpos_core import generate_proposals as addnewpos_core_generate
from app.strategies.addnewpos_fast import generate_proposals as addnewpos_fast_generate, ENABLED as ADDNEWPOS_FAST_ENABLED


class StrategyOrchestrator:
    """
    Strategy Orchestrator - coordinates all strategy engines.
    
    Each strategy is independent and unaware of others.
    Orchestrator aggregates proposals and sends to ProposalStore.
    """
    
    def __init__(self, context: StrategyContext):
        """
        Initialize Strategy Orchestrator.
        
        Args:
            context: StrategyContext (GRPAN, RWVAP, Port Adjuster, etc.)
        """
        self.context = context
        self.enabled_strategies = {
            'TAKE_PROFIT_LONG': True,
            'TAKE_PROFIT_SHORT': True,
            'ADDNEWPOS_CORE': True,
            'ADDNEWPOS_FAST': ADDNEWPOS_FAST_ENABLED  # Feature flag
        }
        logger.info(f"[STRATEGY_ORCHESTRATOR] Initialized with strategies: {self.enabled_strategies}")
    
    def set_strategy_enabled(self, strategy_name: str, enabled: bool):
        """
        Enable/disable a strategy.
        
        Args:
            strategy_name: Strategy name ('TAKE_PROFIT_LONG', 'TAKE_PROFIT_SHORT', 'ADDNEWPOS_CORE', 'ADDNEWPOS_FAST')
            enabled: True to enable, False to disable
        """
        if strategy_name in self.enabled_strategies:
            self.enabled_strategies[strategy_name] = enabled
            logger.info(f"[STRATEGY_ORCHESTRATOR] Strategy {strategy_name} {'enabled' if enabled else 'disabled'}")
        else:
            logger.warning(f"[STRATEGY_ORCHESTRATOR] Unknown strategy: {strategy_name}")
    
    def generate_all_proposals(
        self,
        market_snapshots: Dict[str, MarketSnapshot],
        position_snapshots: Dict[str, PositionSnapshot],
        cycle_id: int = 0
    ) -> List[OrderProposal]:
        """
        Generate proposals from all enabled strategies.
        
        Args:
            market_snapshots: Dict mapping symbol -> MarketSnapshot
            position_snapshots: Dict mapping symbol -> PositionSnapshot
            cycle_id: Cycle ID for tracking
            
        Returns:
            List of all OrderProposals from enabled strategies
        """
        all_proposals = []
        
        # Strategy 1: Take Profit Longs
        if self.enabled_strategies.get('TAKE_PROFIT_LONG', False):
            try:
                proposals = take_profit_longs_generate(market_snapshots, position_snapshots, self.context)
                for proposal in proposals:
                    proposal.cycle_id = cycle_id
                    proposal.decision_ts = datetime.now()
                all_proposals.extend(proposals)
                logger.debug(f"[STRATEGY_ORCHESTRATOR] TAKE_PROFIT_LONG generated {len(proposals)} proposals")
            except Exception as e:
                logger.error(f"[STRATEGY_ORCHESTRATOR] Error in TAKE_PROFIT_LONG: {e}", exc_info=True)
        
        # Strategy 2: Take Profit Shorts
        if self.enabled_strategies.get('TAKE_PROFIT_SHORT', False):
            try:
                proposals = take_profit_shorts_generate(market_snapshots, position_snapshots, self.context)
                for proposal in proposals:
                    proposal.cycle_id = cycle_id
                    proposal.decision_ts = datetime.now()
                all_proposals.extend(proposals)
                logger.debug(f"[STRATEGY_ORCHESTRATOR] TAKE_PROFIT_SHORT generated {len(proposals)} proposals")
            except Exception as e:
                logger.error(f"[STRATEGY_ORCHESTRATOR] Error in TAKE_PROFIT_SHORT: {e}", exc_info=True)
        
        # Strategy 3: ADDNEWPOS Core
        if self.enabled_strategies.get('ADDNEWPOS_CORE', False):
            try:
                proposals = addnewpos_core_generate(market_snapshots, position_snapshots, self.context)
                for proposal in proposals:
                    proposal.cycle_id = cycle_id
                    proposal.decision_ts = datetime.now()
                all_proposals.extend(proposals)
                logger.debug(f"[STRATEGY_ORCHESTRATOR] ADDNEWPOS_CORE generated {len(proposals)} proposals")
            except Exception as e:
                logger.error(f"[STRATEGY_ORCHESTRATOR] Error in ADDNEWPOS_CORE: {e}", exc_info=True)
        
        # Strategy 4: ADDNEWPOS Fast
        if self.enabled_strategies.get('ADDNEWPOS_FAST', False):
            try:
                proposals = addnewpos_fast_generate(market_snapshots, position_snapshots, self.context)
                for proposal in proposals:
                    proposal.cycle_id = cycle_id
                    proposal.decision_ts = datetime.now()
                all_proposals.extend(proposals)
                logger.debug(f"[STRATEGY_ORCHESTRATOR] ADDNEWPOS_FAST generated {len(proposals)} proposals")
            except Exception as e:
                logger.error(f"[STRATEGY_ORCHESTRATOR] Error in ADDNEWPOS_FAST: {e}", exc_info=True)
        
        logger.info(f"[STRATEGY_ORCHESTRATOR] Generated {len(all_proposals)} total proposals from {sum(1 for v in self.enabled_strategies.values() if v)} enabled strategies")
        
        return all_proposals
    
    def get_strategy_status(self) -> Dict[str, Any]:
        """
        Get status of all strategies (enabled/disabled).
        
        Returns:
            Dict mapping strategy name -> enabled status
        """
        return self.enabled_strategies.copy()


# Global instance
_strategy_orchestrator: Optional[StrategyOrchestrator] = None


def get_strategy_orchestrator() -> Optional[StrategyOrchestrator]:
    """Get global StrategyOrchestrator instance"""
    return _strategy_orchestrator


def initialize_strategy_orchestrator(
    grpan_engine=None,
    rwvap_engine=None,
    static_store=None,
    port_adjuster_store=None
) -> StrategyOrchestrator:
    """
    Initialize global StrategyOrchestrator instance.
    
    Args:
        grpan_engine: GRPANEngine instance
        rwvap_engine: RWVAPEngine instance
        static_store: StaticDataStore instance
        port_adjuster_store: PortAdjusterStore instance
        
    Returns:
        StrategyOrchestrator instance
    """
    global _strategy_orchestrator
    
    context = StrategyContext(
        grpan_engine=grpan_engine,
        rwvap_engine=rwvap_engine,
        static_store=static_store,
        port_adjuster_store=port_adjuster_store
    )
    
    _strategy_orchestrator = StrategyOrchestrator(context)
    logger.info("[STRATEGY_ORCHESTRATOR] Global instance initialized")
    
    return _strategy_orchestrator





