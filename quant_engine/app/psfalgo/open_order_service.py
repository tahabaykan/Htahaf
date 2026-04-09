"""
Open Order Service
Abstracts the retrieval of open orders from different brokers (IBKR vs Hammer).
"""

from typing import List, Dict, Any, Optional
from app.core.logger import logger
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
        """Fetch orders from IBKR via isolated helper. Must NOT be called from the event loop thread (deadlock)."""
        import asyncio
        from app.psfalgo.ibkr_connector import get_open_orders_isolated_sync
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                # Called from event loop thread: get_open_orders_isolated_sync would deadlock (loop waits for executor, executor waits for loop).
                logger.warning(
                    "[OpenOrderService] get_open_orders called from event loop thread; returning [] to avoid deadlock. "
                    "Caller should use run_in_executor for the code path that needs open orders."
                )
                return []
            return get_open_orders_isolated_sync(account_id)
        except Exception as e:
            logger.warning(f"[OpenOrderService] get_open_orders_isolated_sync failed: {e}")
            return []

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
        """Run async code from sync context. When already in a running loop, run coro in a thread to avoid 'coroutine was never awaited'."""
        import asyncio
        import concurrent.futures

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # Run coro in a dedicated thread with its own loop so we don't drop the coroutine.
            # IBKRConnector.get_open_orders() uses _run_on_ib_thread and can run in any loop.
            def _run_in_thread():
                th_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(th_loop)
                try:
                    return th_loop.run_until_complete(coro)
                except Exception as e:
                    logger.warning(f"[OpenOrderService] Thread-run async failed: {e}")
                    return []
                finally:
                    th_loop.close()
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(_run_in_thread)
                    return fut.result(timeout=5)
            except concurrent.futures.TimeoutError:
                logger.warning("[OpenOrderService] get_open_orders timed out (20s)")
                return []
            except Exception as e:
                logger.warning(f"[OpenOrderService] Failed to run async in thread: {e}")
                return []
        else:
            return loop.run_until_complete(coro)

# Global instance
_open_order_service = OpenOrderService()

def get_open_order_service() -> OpenOrderService:
    return _open_order_service
