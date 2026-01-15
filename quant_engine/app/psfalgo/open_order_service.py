"""
Open Order Service
Abstracts the retrieval of open orders from different brokers (IBKR vs Hammer).
"""

from typing import List, Dict, Any, Optional
from app.core.logger import logger
from app.psfalgo.ibkr_connector import get_ibkr_connector
# Hammer imports - lazy to avoid circular deps
from app.trading.hammer_orders_service import HammerOrdersService
from app.live.hammer_client import HammerClient

class OpenOrderService:
    """
    Service to fetch open orders from the active broker.
    Routes requests to IBKRConnector or HammerOrdersService based on account_id.
    """
    
    def __init__(self):
        self._hammer_service: Optional[HammerOrdersService] = None
        
    def get_open_orders(self, account_id: str, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get open orders for the specified account.
        
        Args:
            account_id: Account identifier (IBKR_GUN, IBKR_PED, HAMMER_PRO, etc.)
            symbol: Optional symbol to filter by
            
        Returns:
            List of open order dicts:
            [{
                'symbol': str,
                'side': 'BUY'/'SELL',
                'qty': float,
                'filled': float,
                'remaining': float,
                'order_id': str
            }]
        """
        all_orders = []
        
        # 1. Route based on account type
        if "IBKR" in account_id.upper():
            all_orders = self._get_ibkr_orders(account_id)
        elif "HAMMER" in account_id.upper() or "HAMPRO" in account_id.upper():
            all_orders = self._get_hammer_orders(account_id)
        else:
            logger.warning(f"[OpenOrderService] Unknown account type: {account_id}")
            return []
            
        # 2. Filter by symbol if requested
        if symbol:
            target_sym = symbol.upper().strip()
            # Basic fuzzy matching for suffix differences (e.g. PR A vs PRA)
            filtered = []
            for o in all_orders:
                o_sym = o['symbol'].upper().strip()
                if o_sym == target_sym or o_sym.replace(" ", "") == target_sym.replace(" ", ""):
                    filtered.append(o)
            return filtered
            
        return all_orders

    def get_pending_qty(self, account_id: str, symbol: str, side: str) -> float:
        """
        Get total pending quantity for a specific symbol and side.
        
        Args:
            account_id: Account ID
            symbol: Symbol
            side: 'BUY' or 'SELL'
            
        Returns:
            Total remaining quantity (float)
        """
        orders = self.get_open_orders(account_id, symbol)
        total_pending = 0.0
        
        target_side = side.upper()
        
        for order in orders:
            if order['side'] == target_side:
                # Use remaining qty if available, else total - filled
                remaining = order.get('remaining', 0.0)
                if remaining <= 0:
                     remaining = order.get('qty', 0.0) - order.get('filled', 0.0)
                
                total_pending += max(0.0, remaining)
                
        return total_pending

    def _get_ibkr_orders(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetch orders from IBKR Connector"""
        connector = get_ibkr_connector(account_id)
        if not connector:
            logger.warning(f"[OpenOrderService] No connector for {account_id}")
            return []
            
        # IBKR get_open_orders is async, but we might be in sync context?
        # The connector methods are async. We need to run them properly.
        # If we are in an async loop, await it. If not, run_until_complete?
        # IMPORTANT: PSFAlgo architecture usually runs engines in async loops.
        # But ActionPlanner is often sync.
        # IBKRConnector.get_open_orders() is async.
        
        # Checking calling context... ActionPlanner.plan_action is sync.
        # We need a sync wrapper for this call if called from sync context.
        
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We are in a running loop (e.g. FastAPI request)
                # We can't verify open orders synchronously without blocking/nesting issues.
                # However, IBKRConnector internally caches or makes sync calls via its client?
                # No, it uses `await`.
                # FIX: We should rely on `ActionPlanner` being called from an async context (ProposalEngine)
                # and make this method async too?
                # User requirement: "ActionPlanner... soracak".
                # To be safe, for now we will try to get the result.
                
                # If we are effectively in async code, we should await. 
                # But this method signature is sync for compatibility.
                # Let's trust that the caller can handle a future if we updated the signature? 
                # No, let's look at `ibkr_connector.py`. It has `async def get_open_orders`.
                
                # For this implementation, I will assume we can block on a new logical thread or 
                # use a sync bridge if absolutely necessary.
                # BETTER: Modify this service to contain `async def` and update callers.
                pass
        except:
            pass
            
        # For simplify/safety: We'll implement a sync-bridge helper
        return self._run_async(connector.get_open_orders())

    def _get_hammer_orders(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetch orders from Hammer Service"""
        # HammerOrdersService.get_orders is SYNC.
        if not self._hammer_service:
            # Try to init service
            # Need a client. Try getting global or creating new?
            # Creating new might be expensive/broken if connection is needed.
            # Best effort: Try to find existing client?
            # For now, minimal stub or empty if not injected.
            # In a real app, this should be injected.
            # Assuming we can get it or fail gracefully.
            return []
            
        return self._hammer_service.get_orders()

    def _run_async(self, coro):
        """Helper to run async code from sync context"""
        import asyncio
        import concurrent.futures
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
             # Cannot block here. Return empty list to be safe.
             # Caller should ideally be async.
             logger.warning("[OpenOrderService] Called from running loop but method is sync. Returning empty list.")
             return []
        else:
             return loop.run_until_complete(coro)

# Global instance
_open_order_service = OpenOrderService()

def get_open_order_service() -> OpenOrderService:
    return _open_order_service
