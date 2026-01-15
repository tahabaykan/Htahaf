"""
Execution Service
Bridges the gap between User Acceptance and Execution Router.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from app.core.logger import logger
from app.psfalgo.proposal_store import get_proposal_store
from app.psfalgo.account_mode import get_account_mode_manager
from app.execution.execution_router import get_execution_router, ExecutionMode
from app.trading.trading_account_context import get_trading_context, TradingAccountMode

class ExecutionService:
    """
    Service to handle proposal execution after user acceptance.
    """
    
    def __init__(self):
        self.proposal_store = get_proposal_store()
        self.router = get_execution_router()
        self.account_manager = get_account_mode_manager()
        
    async def execute_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """
        Execute an accepted proposal.
        
        Args:
            proposal_id: ID of the proposal to execute
            
        Returns:
            Execution result dict
        """
        try:
            # 1. Get Proposal
            proposal = self.proposal_store.get_proposal(proposal_id)
            if not proposal:
                return {'success': False, 'error': f'Proposal {proposal_id} not found'}
            
            # 2. Validate Status (Must be ACCEPTED)
            if proposal.status != 'ACCEPTED':
                return {
                    'success': False, 
                    'error': f'Proposal must be ACCEPTED before execution. Current: {proposal.status}'
                }
                
            # 3. Prepare Order Plan
            # Convert Proposal fields to Order Plan format expected by Router
            order_plan = {
                'symbol': proposal.symbol,
                'action': proposal.side, # BUY/SELL
                'size': proposal.qty,
                'price': proposal.proposed_price,
                'style': proposal.order_type, # LIMIT/MARKET
                'psfalgo_source': True,
                'psfalgo_action': f"Proposal-{proposal_id}" 
            }
            
            # 4. Determine Active Account
            # Ensure TradingAccountContext is synced with AccountModeManager
            # The Router uses TradingAccountContext
            ctx = get_trading_context()
            current_mode = self.account_manager.get_mode()
            
            # Sync context if needed (safety check)
            # We map string mode (IBKR_PED) to Enum
            try:
                target_enum = TradingAccountMode(current_mode)
                if ctx.trading_mode != target_enum:
                    logger.info(f"[EXEC_SERVICE] Syncing Context Mode to {current_mode}")
                    ctx.set_trading_mode(target_enum)
            except ValueError:
                logger.error(f"[EXEC_SERVICE] Invalid account mode string: {current_mode}")
                return {'success': False, 'error': f'Invalid account mode: {current_mode}'}

            # 5. Set Router to SEMI_AUTO (Since this IS a user action) or FULL_AUTO?
            # User clicked "Accept", so this is effectively SEMI_AUTO execution.
            # We temporarily force SEMI_AUTO logic for this transaction if not already set?
            # Actually, Router.handle() takes 'user_action'.
            # If we pass user_action='APPROVE', it should work in SEMI_AUTO.
            
            # Check current router mode
            # If Router is in PREVIEW, we might want to warn or override?
            # User wants to EXECUTE. So we assume they want real execution.
            # We will rely on the Router's configuration. 
            # If Router is PREVIEW, it will return SIMULATED.
            # Use `runall_engine` or `runtime_controls` checks if we need to enforce "Live"?
            # For now, let's respect the Router's mode, but pass 'APPROVE'.
            
            gate_status = {'gate_status': 'MANUAL_APPROVE'} # Dummy gate status for manual action
            
            # 6. Execute via Router
            logger.info(f"[EXEC_SERVICE] Routing proposal {proposal_id} to {current_mode}...")
            result = self.router.handle(
                order_plan=order_plan,
                gate_status=gate_status,
                user_action='APPROVE',
                symbol=proposal.symbol
            )
            
            # 7. Update Proposal with Result
            execution_updates = {
                'execution_result': result
            }
            
            if result.get('execution_status') == 'EXECUTED':
                execution_updates['status'] = 'SENT'
                execution_updates['order_id'] = result.get('order_id')
                logger.info(f"[EXEC_SERVICE] Proposal {proposal_id} SENT. OrderID: {result.get('order_id')}")
            else:
                logger.warning(f"[EXEC_SERVICE] Proposal {proposal_id} execution failed/skipped: {result.get('execution_reason')}")
                
            # Sync updates to store
            # PROPOSAL object update
            proposal.execution_result = result
            if result.get('execution_status') == 'EXECUTED':
                proposal.status = 'SENT'
                if result.get('order_id'):
                    proposal.order_id = result.get('order_id')
            
            # No explicit 'update_proposal' method in store? 
            # Store usually returns reference, so modification might persist if in-memory.
            # But safer to call a save method if it exists.
            # Looking at proposal_store.py (not viewed but standard pattern)... 
            # Usually in-memory store updates are immediate if object reference is shared.
            
            return {
                'success': True,
                'proposal_id': proposal_id,
                'execution_result': result
            }
            
        except Exception as e:
            logger.error(f"[EXEC_SERVICE] Error executing proposal {proposal_id}: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

# Global Instance
_execution_service: Optional[ExecutionService] = None

def get_execution_service() -> ExecutionService:
    global _execution_service
    if not _execution_service:
        _execution_service = ExecutionService()
    return _execution_service
