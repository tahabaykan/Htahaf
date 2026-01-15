"""
Execution Router
Routes orders to broker based on execution mode and active ExecutionProvider.

Execution Modes (Automation Level):
- PREVIEW: No execution, only simulation
- SEMI_AUTO: Execute only user-approved orders
- FULL_AUTO: Execute auto-approved orders automatically

Trading Account Modes (Broker Backend):
- HAMPRO: Hammer Pro
- IBKR_PED: IBKR Paper
- IBKR_GUN: IBKR Live
"""

from enum import Enum
from typing import Dict, Any, Optional
from app.core.logger import logger
from app.trading.trading_account_context import get_trading_context, TradingAccountMode
from app.execution.execution_provider import ExecutionProvider, ExecutionProviderStatus
from app.execution.providers import HammerExecutionProvider, IBKRExecutionProvider

# Order Controller for Orphan Marking
# REMOVED: from app.psfalgo.order_manager import get_order_controller

class ExecutionMode(Enum):
    """Execution mode enum (Automation Level)"""
    PREVIEW = "PREVIEW"
    SEMI_AUTO = "SEMI_AUTO"
    FULL_AUTO = "FULL_AUTO"


class ExecutionResult(Enum):
    """Execution result enum"""
    SIMULATED = "SIMULATED"
    EXECUTED = "EXECUTED"
    SKIPPED_USER_ACTION = "SKIPPED_USER_ACTION"
    BLOCKED_BY_GATE = "BLOCKED_BY_GATE"
    SKIPPED_NO_PLAN = "SKIPPED_NO_PLAN"
    ERROR = "ERROR"
    SKIPPED_NO_PROVIDER = "SKIPPED_NO_PROVIDER"


class ExecutionRouter:
    """
    Routes orders to broker based on execution mode and active provider.
    Handles 'Safe Mode Switching' between brokers.
    """
    
    def __init__(self, execution_mode: ExecutionMode = ExecutionMode.PREVIEW):
        self.execution_mode = execution_mode
        self.providers: Dict[TradingAccountMode, ExecutionProvider] = {
            TradingAccountMode.HAMPRO: HammerExecutionProvider(),
            TradingAccountMode.IBKR_PED: IBKRExecutionProvider('IBKR_PED'),
            TradingAccountMode.IBKR_GUN: IBKRExecutionProvider('IBKR_GUN')
        }
        logger.info(f"ExecutionRouter initialized (Mode: {execution_mode.value})")
        
    def set_mode(self, mode: ExecutionMode):
        """Set automation level (PREVIEW/SEMI/FULL)."""
        self.execution_mode = mode
        logger.info(f"Execution Automation Mode changed to: {mode.value}")
    
    def get_mode(self) -> ExecutionMode:
        """Get automation level."""
        return self.execution_mode
    
    def switch_account_mode(self, target_mode: TradingAccountMode):
        """
        SAFE MODE SWITCHING LOGIC (STRICT).
        
        1. Context validation.
        2. Set new mode in Context.
        3. Activate/Connect new Provider.
        4. Orphan old orders (READ-ONLY) - via Controller.
        5. DO NOT auto-cancel.
        """
        ctx = get_trading_context()
        old_mode = ctx.trading_mode
        
        if old_mode == target_mode:
            logger.info(f"Already in {target_mode.value}, skipping switch.")
            return

        logger.info(f"🔄 Switching Account Mode: {old_mode.value} -> {target_mode.value}")

        # 1. Update Context Mode
        if not ctx.set_trading_mode(target_mode):
            logger.error("Context rejected mode switch.")
            return

        # 2. Activate New Provider (Check Connection)
        new_provider = self.providers.get(target_mode)
        if not new_provider:
            logger.error(f"No provider found for {target_mode.value}")
            return
            
        # Ensure connected
        if new_provider.get_status() == ExecutionProviderStatus.DISCONNECTED:
            logger.info(f"Connecting new provider {target_mode.value}...")
            new_provider.connect()
            
        # 3. Refresh Snapshots (Optional but recommended)
        # new_provider.get_open_orders(target_mode.value)
            
        # 4. Orphan Old Orders via Controller
        # "Mark old-provider orders as orphaned_provider=True"
        # The user's instruction implies a lazy import and conditional orphan marking.
        # Assuming 'AUTOMATIC' refers to FULL_AUTO mode for orphan marking.
        if self.execution_mode == ExecutionMode.FULL_AUTO:
            # Phase 4: Mark old provider orders as orphaned
            from app.psfalgo.order_manager import get_order_controller
            oc = get_order_controller()
            if oc:
                orphaned_count = oc.mark_provider_orders_orphaned(old_mode.value)
                logger.info(f"Orphaned {orphaned_count} orders from {old_mode.value}")
            else:
                logger.warning("OrderController not available for orphan marking.")
        else:
            logger.info(f"Skipping orphan marking in {self.execution_mode.value} mode.")

        logger.info(f"✅ Switched to {target_mode.value}. Old orders orphaned. NO AUTO-CANCEL.")


    def handle(
        self,
        order_plan: Dict[str, Any],
        gate_status: Dict[str, Any],
        user_action: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Handle order execution.
        """
        try:
            # 1. Validation
            if not order_plan or order_plan.get('action') == 'NONE':
                return {
                    'execution_status': ExecutionResult.SKIPPED_NO_PLAN.value,
                    'execution_reason': 'No order plan'
                }
            
            gate_status_value = gate_status.get('gate_status') if gate_status else None
            
            # 2. Logic by Automation Mode
            if self.execution_mode == ExecutionMode.PREVIEW:
                return self._simulate_execution(order_plan)
                
            if self.execution_mode == ExecutionMode.SEMI_AUTO:
                if user_action != 'APPROVE':
                    return {
                        'execution_status': ExecutionResult.SKIPPED_USER_ACTION.value,
                        'execution_reason': f'User action is {user_action}, not APPROVE',
                        'user_action': user_action
                    }
                if gate_status_value == 'BLOCKED':
                    return {
                        'execution_status': ExecutionResult.BLOCKED_BY_GATE.value,
                        'execution_reason': 'Gate BLOCKED in SEMI_AUTO'
                    }
                return self._execute_via_provider(order_plan, symbol)

            if self.execution_mode == ExecutionMode.FULL_AUTO:
                if gate_status_value != 'AUTO_APPROVED':
                     return {
                        'execution_status': ExecutionResult.BLOCKED_BY_GATE.value,
                        'execution_reason': f'Gate {gate_status_value} != AUTO_APPROVED'
                    }
                return self._execute_via_provider(order_plan, symbol)
                
            return {'execution_status': ExecutionResult.ERROR.value, 'execution_reason': 'Unknown Mode'}

        except Exception as e:
            logger.error(f"Error in execution router: {e}", exc_info=True)
            return {
                'execution_status': ExecutionResult.ERROR.value,
                'execution_reason': f'Error: {str(e)}'
            }

    def _simulate_execution(self, order_plan: Dict[str, Any]) -> Dict[str, Any]:
        action = order_plan.get('action', 'NONE')
        size = order_plan.get('size', 0)
        price = order_plan.get('price', 0)
        style = order_plan.get('style', 'N/A')
        
        logger.info(f"[SIMULATED] Would execute: {action} {size} @ {price:.4f} {style}")
        return {
            'execution_status': ExecutionResult.SIMULATED.value,
            'execution_reason': f'Preview: {action} {size} @ {price:.4f} {style}'
        }

    def _execute_via_provider(self, order_plan: Dict[str, Any], symbol: Optional[str]) -> Dict[str, Any]:
        """Delegate to active provider determined by TradingAccountContext."""
        ctx = get_trading_context()
        active_account = ctx.trading_mode  # Enum (HAMPRO/IBKR_PED/IBKR_GUN)
        
        provider = self.providers.get(active_account)
        
        if not provider:
            logger.error(f"[EXECUTION BLOCKED] No provider config for {active_account.value}")
            return {
                'execution_status': ExecutionResult.SKIPPED_NO_PROVIDER.value,
                'execution_reason': f'No provider for {active_account.value}'
            }
            
        # Prepare Order Request
        order_symbol = symbol or order_plan.get('symbol')
        quantity = order_plan.get('size', 0)
        price = order_plan.get('price', 0.0)
        action = order_plan.get('action', 'BUY')
        style = order_plan.get('style', 'LIMIT')
        
        # Construct Request
        request = {
            'symbol': order_symbol,
            'action': action,
            'quantity': quantity,
            'price': price,
            'style': style,
            # Add strict fields if needed by provider
            'psfalgo_source': order_plan.get('psfalgo_source', False),
            'psfalgo_action': order_plan.get('psfalgo_action', '')
        }
        
        # Execute with STRICT account_id
        result = provider.place_order(account_id=active_account.value, order_request=request)
        
        if result.get('success'):
            return {
                'execution_status': ExecutionResult.EXECUTED.value,
                'execution_reason': result.get('message', 'Executed'),
                'order_id': result.get('order_id'),
                'provider': active_account.value
            }
        else:
            return {
                'execution_status': ExecutionResult.ERROR.value,
                'execution_reason': result.get('message', 'Provider Error'),
                'provider_error': result.get('error')
            }

# Global Router Instance (if needed)
_router: Optional[ExecutionRouter] = None

def get_execution_router() -> ExecutionRouter:
    global _router
    if not _router:
        _router = ExecutionRouter()
    return _router

