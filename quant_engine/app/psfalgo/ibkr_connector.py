"""
IBKR Gateway Connector - Phase 10.1 (Real Connection)

Connects to IBKR Gateway / TWS for positions, orders, and account summary.
Execution yok, order gönderimi yok. SADECE positions / open orders / account summary.

Key Principles:
- Normal connection (not READ-ONLY, but no execution)
- Account selector (GUN / PED)
- Market data ALWAYS from HAMMER
- Execution ASLA yapılmayacak
- Live account (not paper)
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio

from app.core.logger import logger

# ib_insync import (lazy import - only when actually needed)
# PHASE 10.1: Do NOT import ib_insync at module level - it requires event loop
# Import will happen lazily in connect() method
IB_INSYNC_AVAILABLE = None  # Will be set lazily
IB = None
Contract = None
Position = None
Order = None


class IBKRConnector:
    """
    IBKR Gateway Connector (READ-ONLY).
    
    Responsibilities:
    - Connect to IBKR Gateway / TWS
    - Get positions (READ-ONLY)
    - Get open orders (READ-ONLY)
    - Get account summary (READ-ONLY)
    - Account selector (GUN / PED)
    
    Does NOT:
    - Submit orders
    - Modify positions
    - Execute trades
    - Provide market data (always from HAMMER)
    """
    
    def __init__(self, account_type: str = "IBKR_GUN"):
        """
        Initialize IBKR Connector.
        
        Args:
            account_type: Account type (IBKR_GUN or IBKR_PED)
        """
        self.account_type = account_type
        self.connected = False
        self.connection_error: Optional[str] = None
        
        # IBKR Gateway / TWS connection (type will be IB after lazy import)
        self._ibkr_client: Optional[Any] = None
        
        # PHASE 10.1: Same port for both GUN and PED (like Janall)
        # Default: 4001 (Gateway) or 7497 (TWS)
        # Account distinction is done via account field, not port
        self.default_port = 4001  # Gateway default
        self.tws_port = 7497  # TWS default
        
        logger.info(f"IBKRConnector initialized (account_type={account_type}, port: {self.default_port}/{self.tws_port})")
    
    def _ensure_ib_insync(self) -> bool:
        """
        Lazy import of ib_insync - sync import (like Janall).
        Janall uses ib_async with module-level import, we use ib_insync with lazy import.
        CRITICAL: ib_insync requires event loop at import time.
        Solution: Import in a thread with its own event loop.
        Returns True if available, False otherwise.
        """
        global IB_INSYNC_AVAILABLE, IB, Contract, Position, Order
        
        if IB_INSYNC_AVAILABLE is not None:
            return IB_INSYNC_AVAILABLE
        
        try:
            # CRITICAL: ib_insync import requires event loop
            # Import in a separate thread with its own event loop
            import asyncio
            import threading
            from queue import Queue
            
            result_queue = Queue()
            error_queue = Queue()
            
            def import_in_thread():
                """Import ib_insync in a thread with its own event loop"""
                try:
                    # Create new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    # Now import ib_insync (event loop exists)
                    from ib_insync import IB as IBClass, Contract as ContractClass, Position as PositionClass, Order as OrderClass
                    
                    # Put result in queue
                    result_queue.put({
                        'IB': IBClass,
                        'Contract': ContractClass,
                        'Position': PositionClass,
                        'Order': OrderClass
                    })
                    
                    # Close event loop
                    loop.close()
                except Exception as e:
                    error_queue.put(e)
            
            # Start import thread
            import_thread = threading.Thread(target=import_in_thread, daemon=True)
            import_thread.start()
            import_thread.join(timeout=5.0)  # Wait max 5 seconds
            
            if not error_queue.empty():
                error = error_queue.get()
                raise error
            
            if not result_queue.empty():
                result = result_queue.get()
                IB = result['IB']
                Contract = result['Contract']
                Position = result['Position']
                Order = result['Order']
                IB_INSYNC_AVAILABLE = True
                logger.info("[IBKR] ib_insync imported successfully (lazy import in thread)")
                return True
            else:
                raise RuntimeError("ib_insync import timeout (thread did not complete)")
                
        except ImportError as e:
            IB_INSYNC_AVAILABLE = False
            logger.error(f"ib_insync import failed (not installed): {e}. Install with: pip install ib-insync")
            return False
        except RuntimeError as e:
            IB_INSYNC_AVAILABLE = False
            logger.error(f"ib_insync import failed (event loop issue): {e}")
            return False
        except Exception as e:
            IB_INSYNC_AVAILABLE = False
            logger.error(f"ib_insync import failed (unknown error): {e}", exc_info=True)
            return False
    
    async def connect(
        self,
        host: str = '127.0.0.1',
        port: Optional[int] = None,
        client_id: int = 1
    ) -> Dict[str, Any]:
        """
        Connect to IBKR Gateway / TWS.
        
        PHASE 10.1: Same port for both GUN and PED (like Janall).
        Account distinction is done via account field filtering.
        
        Args:
            host: IBKR Gateway / TWS host (default: 127.0.0.1)
            port: Port number (default: 4001 for Gateway, 7497 for TWS)
            client_id: Client ID (default: 1)
        
        Returns:
            Connection result
        """
        # Lazy import ib_insync (sync import, like Janall)
        if not self._ensure_ib_insync():
            error_msg = "ib_insync not available. Install with: pip install ib-insync"
            self.connected = False
            self.connection_error = error_msg
            logger.error(f"[IBKR] {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'account_type': self.account_type,
                'connected': False
            }
        
        try:
            # Use default port if not provided
            if port is None:
                port = self.default_port
            
            # Create IB client (now IB is available from lazy import)
            self._ibkr_client = IB()
            
            # PHASE 10.1: Use sync connect() method (like Janall does with ib_async)
            # Janall uses: self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=15)
            # CRITICAL: ib_insync.connect() needs event loop in the thread where it runs
            # So we create event loop in executor thread before calling connect()
            import asyncio
            import threading
            
            def connect_with_event_loop():
                """Connect in executor thread with its own event loop"""
                # Create event loop for this thread (executor thread)
                try:
                    # Try to get existing loop
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # No loop exists, create one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                # Now call sync connect() - it will use the event loop we just created
                self._ibkr_client.connect(host, port, clientId=client_id, timeout=15)
            
            # Run in executor to avoid blocking async context
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, connect_with_event_loop)
            
            self.connected = True
            self.connection_error = None
            
            logger.info(f"[IBKR] Connected to {self.account_type} at {host}:{port} (clientId={client_id})")
            
            # Auto-track BEFDAY positions (günde 1 kere, ilk bağlantıda)
            async def auto_track_befday_ibkr():
                """Auto-track BEFDAY positions when IBKR connects (once per day)"""
                try:
                    await asyncio.sleep(2)  # Wait for IBKR to stabilize
                    
                    from app.psfalgo.befday_tracker import get_befday_tracker, track_befday_positions
                    
                    tracker = get_befday_tracker()
                    if not tracker:
                        logger.warning("[BEFDAY] Tracker not initialized, skipping auto-track")
                        return
                    
                    # Determine mode based on account_type
                    mode = 'ibkr_gun' if self.account_type == 'IBKR_GUN' else 'ibkr_ped'
                    
                    # Check if should track
                    should_track, reason = tracker.should_track(mode=mode)
                    if not should_track:
                        logger.info(f"[BEFDAY] Skipping auto-track for {self.account_type}: {reason}")
                        return
                    
                    # Get positions from IBKR
                    positions = await self.get_positions()
                    if positions:
                        success = await track_befday_positions(
                            positions=positions,
                            mode=mode,
                            account=self.account_type
                        )
                        if success:
                            logger.info(f"[BEFDAY] ✅ Auto-tracked {len(positions)} {self.account_type} positions (befibgun.csv or befibped.csv)")
                        else:
                            logger.warning(f"[BEFDAY] Auto-track failed for {self.account_type}")
                    else:
                        logger.info(f"[BEFDAY] No positions to track for {self.account_type}")
                except Exception as e:
                    logger.error(f"[BEFDAY] Error in auto-track for {self.account_type}: {e}", exc_info=True)
            
            # Schedule auto-track after a delay
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(auto_track_befday_ibkr())
            except RuntimeError:
                # No event loop, create one
                asyncio.run(auto_track_befday_ibkr())
            
            return {
                'success': True,
                'account_type': self.account_type,
                'host': host,
                'port': port,
                'client_id': client_id,
                'connected': True
            }
        except Exception as e:
            self.connected = False
            self.connection_error = str(e)
            
            logger.error(f"[IBKR] Connection failed to {self.account_type}: {e}", exc_info=True)
            
            return {
                'success': False,
                'error': str(e),
                'account_type': self.account_type,
                'host': host,
                'port': port,
                'connected': False
            }
    
    async def disconnect(self):
        """Disconnect from IBKR Gateway / TWS"""
        try:
            if self._ibkr_client and self.connected:
                # Use sync disconnect() method (like Janall does with ib_async)
                # CRITICAL: ib_insync.disconnect() needs event loop in the thread where it runs
                def disconnect_with_event_loop():
                    """Disconnect in executor thread with its own event loop"""
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    self._ibkr_client.disconnect()
                
                # Run in executor to avoid blocking async context
                import asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, disconnect_with_event_loop)
            
            self.connected = False
            self.connection_error = None
            self._ibkr_client = None
            
            logger.info(f"[IBKR] Disconnected from {self.account_type}")
        except Exception as e:
            logger.error(f"[IBKR] Disconnect error: {e}", exc_info=True)
            self.connected = False
            self._ibkr_client = None
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get positions from IBKR.
        
        Returns:
            List of position dicts with: symbol, qty, avg_price, account
        """
        if not self.connected or not self._ibkr_client:
            logger.warning(f"[IBKR] Not connected, cannot get positions")
            return []
        
        if not self._ensure_ib_insync():
            logger.warning(f"[IBKR] ib_insync not available")
            return []
        
        try:
            # Get positions from IBKR (sync method, but called from async context)
            # ib_insync.positions() is sync but safe to call from async
            positions: List[Position] = self._ibkr_client.positions()
            
            # Filter by account type
            account_positions = []
            for pos in positions:
                # Check if position belongs to this account
                # Account field format: "DU123456" or similar
                # We match by checking if account starts with expected prefix
                # For now, we'll accept all positions and let the caller filter
                # Or we can check pos.account if it matches expected pattern
                
                # Get contract details
                contract = pos.contract
                symbol = contract.symbol
                
                # Calculate average price
                # ib_insync Position.avgCost is ALREADY per-share average cost (not total)
                # updatePortfolio callback shows: averageCost=19.535 (per-share)
                # So we use avgCost directly, NOT divided by position
                avg_cost = getattr(pos, 'averageCost', None)
                if avg_cost is None:
                    avg_cost = getattr(pos, 'avgCost', 0)
                
                # avgCost is already per-share, use it directly
                avg_price = float(avg_cost) if avg_cost else 0.0
                
                position_dict = {
                    'symbol': symbol,
                    'qty': pos.position,  # Positive = Long, Negative = Short
                    'avg_price': avg_price,
                    'account': pos.account,
                    'contract': {
                        'symbol': contract.symbol,
                        'secType': contract.secType,
                        'currency': contract.currency,
                        'exchange': contract.exchange
                    }
                }
                
                account_positions.append(position_dict)
            
            logger.debug(f"[IBKR] Retrieved {len(account_positions)} positions for {self.account_type}")
            return account_positions
            
        except Exception as e:
            logger.error(f"[IBKR] Error getting positions: {e}", exc_info=True)
            return []
    
    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get open orders from IBKR.
        
        Returns:
            List of open order dicts
        """
        if not self.connected or not self._ibkr_client:
            logger.warning(f"[IBKR] Not connected, cannot get open orders")
            return []
        
        if not self._ensure_ib_insync():
            logger.warning(f"[IBKR] ib_insync not available")
            return []
        
        try:
            # Get open orders from IBKR (sync method, but safe to call from async)
            orders = self._ibkr_client.openOrders()
            
            # Format orders
            order_list = []
            for trade in orders:
                order = trade.order
                contract = trade.contract
                
                order_dict = {
                    'order_id': order.orderId,
                    'symbol': contract.symbol,
                    'side': order.action,  # 'BUY' or 'SELL'
                    'qty': order.totalQuantity,
                    'order_type': order.orderType,  # 'LMT', 'MKT', etc.
                    'limit_price': order.lmtPrice if order.orderType == 'LMT' else None,
                    'status': order.orderStatus.status,
                    'filled': order.filledQuantity,
                    'remaining': order.totalQuantity - order.filledQuantity,
                    'account': order.account if hasattr(order, 'account') else None
                }
                
                order_list.append(order_dict)
            
            logger.debug(f"[IBKR] Retrieved {len(order_list)} open orders for {self.account_type}")
            return order_list
            
        except Exception as e:
            logger.error(f"[IBKR] Error getting open orders: {e}", exc_info=True)
            return []
    
    async def get_account_summary(self) -> Dict[str, Any]:
        """
        Get account summary from IBKR (READ-ONLY).
        
        Returns:
            Account summary dict
        """
        if not self.connected:
            logger.warning(f"[IBKR] Not connected, cannot get account summary")
            return {}
        
        try:
            # Get account summary from IBKR (sync method, but safe to call from async)
            account_values = self._ibkr_client.accountValues()
            
            # Format account summary
            summary = {
                'account': self.account_type,
                'connected': True
            }
            
            # Extract key values
            for av in account_values:
                tag = av.tag
                value = av.value
                currency = av.currency
                
                # Key fields
                if tag == 'NetLiquidation':
                    summary['net_liquidation'] = float(value) if value else 0.0
                elif tag == 'BuyingPower':
                    summary['buying_power'] = float(value) if value else 0.0
                elif tag == 'TotalCashValue':
                    summary['total_cash'] = float(value) if value else 0.0
                elif tag == 'GrossPositionValue':
                    summary['gross_position_value'] = float(value) if value else 0.0
                elif tag == 'AvailableFunds':
                    summary['available_funds'] = float(value) if value else 0.0
            
            logger.debug(f"[IBKR] Retrieved account summary for {self.account_type}")
            return summary
        except Exception as e:
            logger.error(f"[IBKR] Error getting account summary: {e}", exc_info=True)
            return {
                'account': self.account_type,
                'connected': False,
                'error': str(e)
            }
    
    def is_connected(self) -> bool:
        """Check if connected to IBKR"""
        return self.connected


# Global instances (one per account type)
_ibkr_gun_connector: Optional[IBKRConnector] = None
_ibkr_ped_connector: Optional[IBKRConnector] = None


def get_ibkr_connector(account_type: str = "IBKR_GUN") -> Optional[IBKRConnector]:
    """
    Get IBKR connector for account type.
    
    Args:
        account_type: IBKR_GUN or IBKR_PED
        
    Returns:
        IBKRConnector instance
    """
    global _ibkr_gun_connector, _ibkr_ped_connector
    
    if account_type == "IBKR_GUN":
        if _ibkr_gun_connector is None:
            _ibkr_gun_connector = IBKRConnector(account_type="IBKR_GUN")
        return _ibkr_gun_connector
    elif account_type == "IBKR_PED":
        if _ibkr_ped_connector is None:
            _ibkr_ped_connector = IBKRConnector(account_type="IBKR_PED")
        return _ibkr_ped_connector
    else:
        logger.warning(f"Invalid IBKR account type: {account_type}")
        return None


def initialize_ibkr_connectors():
    """Initialize IBKR connectors (both GUN and PED)"""
    global _ibkr_gun_connector, _ibkr_ped_connector
    
    _ibkr_gun_connector = IBKRConnector(account_type="IBKR_GUN")
    _ibkr_ped_connector = IBKRConnector(account_type="IBKR_PED")
    
    logger.info("IBKR connectors initialized (GUN and PED)")

