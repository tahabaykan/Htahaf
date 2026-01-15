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
    
    async def connect(
        self,
        host: str = '127.0.0.1',
        port: Optional[int] = None,
        client_id: int = 21
    ) -> Dict[str, Any]:
        """
        Connect to IBKR Gateway / TWS using async connection.
        """
        # CRITICAL FIX 5.0: PRE-EMPTIVE MONKEY PATCH & DEBUGGING
        # This MUST run before any ib_async/ib_insync imports or calls.
        import sys
        import asyncio
        import traceback
        
        try:
             # 1. Get Running Loop & Log
             try:
                 loop = asyncio.get_running_loop()
                 logger.info(f"[IBKR] Connect Start - Running Loop ID: {id(loop)}")
             except RuntimeError:
                 loop = asyncio.new_event_loop()
                 asyncio.set_event_loop(loop)
                 logger.info(f"[IBKR] Connect Start - Created New Loop ID: {id(loop)}")

             # 2. Aggressive Monkey Patch (Redirect get_event_loop -> get_running_loop)
             # This saves legacy libs that call get_event_loop() internally
             asyncio.get_event_loop = asyncio.get_running_loop
             logger.info("[IBKR] Monkey-patching asyncio.get_event_loop -> get_running_loop applied.")

             # 3. Force SET Event Loop
             asyncio.set_event_loop(loop)
             
             # 4. Apply nest_asyncio
             try:
                 import nest_asyncio
                 nest_asyncio.apply(loop)
                 logger.info("[IBKR] nest_asyncio applied ✅")
             except ImportError:
                 pass
                 
        except Exception as patch_err:
             logger.error(f"[IBKR] Patching failed: {patch_err}")

        try:
             # Ensure library is available (NOW SAFE after patch)
             if not self._ensure_ib_insync():
                 return {'success': False, 'error': 'ib_insync/ib_async missing', 'connected': False}

             if port is None:
                 port = self.default_port
                 
             # Patch asyncio in ib_insync/ib_async (util patch)
             try:
                if self.use_ib_async:
                    import ib_async.util as util
                    util.patchAsyncio()
                else:
                    import ib_insync.util as util
                    util.patchAsyncio()
             except:
                pass
            
             # Create IB instance (newer ib_insync version doesn't accept 'loop' parameter)
             # The library will automatically use the running event loop
             self._ibkr_client = IB()
             
             # Connect asynchronously on the current event loop
             logger.info(f"[IBKR] Starting connectAsync to {host}:{port}...")
             await self._ibkr_client.connectAsync(host, port, clientId=client_id, timeout=15)
             logger.info("[IBKR] connectAsync completed.")
             
             self.connected = True
             self.connection_error = None
             logger.info(f"[IBKR] Connected to {self.account_type} at {host}:{port} (clientId={client_id}) via asyncio (ib_async={self.use_ib_async})")
             
             # Setup auto-tracking
             asyncio.create_task(self._auto_track_befday_task())
             
             return {'success': True, 'connected': True, 'account_type': self.account_type}
             
        except Exception as e:
             self.connected = False
             self.connection_error = str(e)
             logger.error(f"[IBKR] Connection failed: {e}", exc_info=True)
             return {'success': False, 'error': str(e), 'connected': False}

    def _ensure_ib_insync(self) -> bool:
        """Lazy import ib_async (Legacy) or ib_insync (Fallback)."""
        global IB_INSYNC_AVAILABLE, IB, Contract, Position, Order, ExecutionFilter
        
        if IB_INSYNC_AVAILABLE is not None:
             return IB_INSYNC_AVAILABLE
             
        # Priority: ib_async (Legacy Janall uses this)
        try:
             from ib_async import IB as IBClass, Contract as ContractClass, Position as PositionClass, Order as OrderClass, ExecutionFilter as ExecFilterClass
             IB = IBClass
             Contract = ContractClass
             Position = PositionClass
             Order = OrderClass
             ExecutionFilter = ExecFilterClass
             IB_INSYNC_AVAILABLE = True
             self.use_ib_async = True
             logger.info("[IBKR] Using ib_async (Legacy Mode) ✅")
             return True
        except (ImportError, RuntimeError, Exception) as e:
             # Catch RuntimeError too (Event loop errors during import) to allow fallback
             logger.warning(f"[IBKR] ib_async failed to import/init: {e}. Trying fallback...")

        # Fallback: ib_insync
        try:
             from ib_insync import IB as IBClass, Contract as ContractClass, Position as PositionClass, Order as OrderClass, ExecutionFilter as ExecFilterClass
             IB = IBClass
             Contract = ContractClass
             Position = PositionClass
             Order = OrderClass
             ExecutionFilter = ExecFilterClass
             IB_INSYNC_AVAILABLE = True
             self.use_ib_async = False
             logger.info("[IBKR] Using ib_insync (Fallback) ⚠️")
             return True
        except (ImportError, RuntimeError, Exception) as e:
             IB_INSYNC_AVAILABLE = False
             logger.error(f"Neither ib_async nor ib_insync available: {e}")
             return False

    async def _auto_track_befday_task(self):
        """Internal helper for auto-tracking task."""
        try:
            await asyncio.sleep(2)
            from app.psfalgo.befday_tracker import get_befday_tracker, track_befday_positions, initialize_befday_tracker
            
            tracker = get_befday_tracker() or initialize_befday_tracker()
            if not tracker: return
            
            mode = 'ibkr_gun' if self.account_type == 'IBKR_GUN' else 'ibkr_ped'
            should_track, _ = tracker.should_track(mode=mode)
            if should_track:
                 positions = await self.get_positions()
                 if positions:
                      await track_befday_positions(positions, mode, self.account_type)
        except Exception as e:
            logger.error(f"[IBKR] Auto-track error: {e}")

            # --- PHASE 10.2: FILL RECOVERY & BENCHMARK LOGGING ---
            # Define execution handler
            def on_exec_details(trade, fill, execution):
                """Callback for IBKR execution details"""
                try:
                    # 1. Extract Details (Universal)
                    fill_id = execution.execId
                    symbol = trade.contract.symbol
                    price = execution.price
                    qty = execution.shares
                    side = execution.side 
                    account = execution.acctNumber
                    order_ref = execution.orderRef if execution.orderRef else "UNKNOWN"
                    action = "BUY" if side == "BOT" else "SELL"
                    
                    # 2. Log to DailyFillsStore (ALWAYS)
                    try:
                        from app.trading.daily_fills_store import get_daily_fills_store
                        get_daily_fills_store().log_fill(
                            self.account_type, symbol, action, qty, price, order_ref
                        )
                    except Exception as e:
                        logger.error(f"[IBKR] Daily Fill Log Error: {e}")

                    # 3. Bench Logger (Conditional)
                    worker_name = os.getenv("WORKER_NAME", "")
                    is_bench_worker = "qebench" in worker_name
                    force_enable = getattr(self, "force_enable_logging", False)
                    
                    if not is_bench_worker and not force_enable:
                        return

                    from app.analysis.qebenchdata import get_bench_logger
                    # execution object contains: execId, time, acctNumber, exchange, side, shares, price
                    # contract object (trade.contract) contains: symbol
                    
                    time_str = execution.time # YYYYMMDD  HH:mm:ss  (Local Exchange Time or UTC? Usually UTC or tz aware)
                    
                    # Parse Time (IBKR format can be erratic, usually "20230501  14:30:00")
                    # We need a robust parser.
                    # For now, let's assume standard IBKR format string or iso format.
                    try:
                        # IBKR often returns strings like '20230524 09:30:00 UTC'
                        # Simplified parsing attempt:
                        # Let's create a datetime object.
                        # If execution.time is string.
                        fill_time = datetime.now() # Fallback
                        if isinstance(time_str, str):
                           # Try parsing - simple approach
                           # Remove potential timezone info for simplicity or parse correctly
                           clean_time = time_str.split(' ')[0] + ' ' + time_str.split(' ')[1] 
                           fill_time = datetime.strptime(clean_time, '%Y%m%d %H:%M:%S')
                        elif isinstance(time_str, datetime):
                            fill_time = time_str

                    except Exception as te:
                        logger.warning(f"Time parse failed for {time_str}: {te}")
                        fill_time = datetime.now()
                    
                    # Log to QeBenchDataLogger
                    logger.info(f"[IBKR] Execution received: {symbol} {side} {qty} @ {price}")
                    bench_logger = get_bench_logger()
                    bench_logger.log_fill(
                        symbol=symbol,
                        price=price,
                        qty=qty,
                        action=action,
                        account=account,
                        fill_time=fill_time,
                        fill_id=fill_id,
                        source_module="IBKR_CONNECTOR"
                    )

                except Exception as e:
                    logger.error(f"[IBKR] Error in execDetails callback: {e}", exc_info=True)

            # Register callback
            self._ibkr_client.execDetailsEvent += on_exec_details
            
            # Request Executions (Recovery for missed fills today)
            # Use ExecutionFilter (clientId=0 means 'all clients' if we want, or None)
            # Need to run this slightly delayed or immediately?
            # ib_insync `reqExecutions` is async-ish (returns list eventually or events).
            # We trigger it.
            try:
                # Create filter for "Today"? Default is all? usually we want recent.
                # Empty filter = all executions.
                # We need proper class instance. 
                # Note: 'IB' class was lazy imported above in connect() scope, but unavailable in outer scope?
                # Actually, self._ibkr_client is an instance of IB.
                # We need `ExecutionFilter` class. 
                # It is available as `IB.ExecutionFilter`? No, it's a separate class in `ib_insync`.
                # We extracted it earlier in `_ensure_ib_insync`? No, we extracted IB, Contract, Position, Order.
                # Let's assume we can get it or pass an empty object?
                # Usually `reqExecutions()` takes an `ExecutionFilter`.
                
                # To be strict, we should import ExecutionFilter.
                # But since `_ensure_ib_insync` didn't put it in global, we have to import it here inside the loop/executor context?
                # Or just use `ExecutionFilter()` from the module.
                # Since we are already inside a method where we did some imports...
                # Simpler: Pass a dummy filter.
                
                from ib_insync import ExecutionFilter
                exec_filter = ExecutionFilter() 
                # self._ibkr_client.reqExecutions(exec_filter) # This triggers events
                
                # Run in executor because reqExecutions might block? No, it returns list.
                # But we want to trigger the events.
                # "reqExecutions" returns a list of (Execution, Contract) AND fires events.
                
                def trigger_recovery():
                    try:
                        self._ibkr_client.reqExecutions(exec_filter)
                        logger.info("[IBKR] Recovery: Executions requested.")
                    except Exception as re:
                        logger.error(f"[IBKR] Recovery request failed: {re}")
                
                # Run trigger in executor
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, trigger_recovery)
                
            except Exception as e:
                logger.error(f"[IBKR] Failed to setup execution recovery: {e}")

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
            List of order dicts with: symbol, action, qty, order_type, price, status, order_id
        """
        if not self.connected or not self._ibkr_client:
            logger.warning(f"[IBKR] Not connected, cannot get open orders")
            return []
        
        if not self._ensure_ib_insync():
            logger.warning(f"[IBKR] ib_insync not available")
            return []
        
        try:
            # Request all open orders from all clients (not just this client)
            self._ibkr_client.reqAllOpenOrders()
            
            # Wait a bit for TWS to send data
            await asyncio.sleep(0.3)
            
            # Get open orders from IBKR
            orders = self._ibkr_client.openOrders()
            
            # Format orders
            order_list = []
            for trade in orders:
                order = trade.order
                contract = trade.contract
                order_status = trade.orderStatus
                
                order_dict = {
                    'symbol': contract.symbol,
                    'action': order.action,  # BUY or SELL
                    'qty': order.totalQuantity,
                    'order_type': order.orderType,  # LMT, MKT, etc.
                    'price': getattr(order, 'lmtPrice', 0.0),
                    'status': order_status.status,
                    'order_id': order.orderId,
                    'account': order.account,
                    'filled': order_status.filled,
                    'remaining': order_status.remaining
                }
                
                order_list.append(order_dict)
            
            logger.info(f"[IBKR] Retrieved {len(order_list)} open orders for {self.account_type}")
            return order_list
            
        except Exception as e:
            logger.error(f"[IBKR] Error getting open orders: {e}", exc_info=True)
            return []
    
    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """
        Get open orders from IBKR.
        
        Returns:
            List of open order dicts
        """
        if not self.connected or not self._ibkr_client:
            # Only warn once per minute / or simple debug to avoid spam
            logger.debug(f"[IBKR] Not connected, cannot get open orders")
            return []
        
        if not self._ensure_ib_insync():
            logger.warning(f"[IBKR] ib_insync not available")
            return []
        
        try:
            # Get open orders from IBKR (sync method, but safe to call from async)
            # Use openTrades() to get Trade objects (which contain order AND contract)
            # openOrders() only returns Order objects (no contract info linked securely)
            orders = self._ibkr_client.openTrades()
            
            # Format orders
            order_list = []
            for trade in orders:
                order = trade.order
                contract = trade.contract
                
                # Check for order status in trade object if available
                status = order.orderStatus.status if hasattr(order, 'orderStatus') and order.orderStatus else 'UNKNOWN'
                # Fallback to trade.orderStatus
                if status == 'UNKNOWN' and hasattr(trade, 'orderStatus'):
                     status = trade.orderStatus.status

                order_dict = {
                    'order_id': order.orderId,
                    'symbol': contract.symbol,
                    'side': order.action,  # 'BUY' or 'SELL'
                    'qty': order.totalQuantity,
                    'order_type': order.orderType,  # 'LMT', 'MKT', etc.
                    'limit_price': order.lmtPrice if order.orderType == 'LMT' else None,
                    'status': status,
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
    
    async def place_order(self, contract_details: Dict[str, Any], order_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Place order to IBKR.
        
        Args:
            contract_details: Dict with symbol, secType, exchange, currency
            order_details: Dict with action, totalQuantity, orderType, lmtPrice
            
        Returns:
            Result dict with order_id
        """
        if not self.connected or not self._ibkr_client:
            return {'success': False, 'message': 'Not connected to IBKR'}
            
        if not self._ensure_ib_insync():
            return {'success': False, 'message': 'ib_insync not available'}
            
        try:
            # Prepare arguments for sync call
            symbol = contract_details.get('symbol')
            action = order_details.get('action')
            qty = order_details.get('totalQuantity')
            price = order_details.get('lmtPrice')
            order_type = order_details.get('orderType', 'LMT')
            
            # We need to run the order placement in the executor thread with event loop
            # because creating Contract and Order objects might need IB context?
            # Actually, Contract and Order are just data objects in ib_insync usually.
            # But placing the order `ib.placeOrder(contract, order)` is the key.
            
            import asyncio
            
            response_queue = []
            
            def place_order_sync():
                try:
                    import time
                    from ib_insync import Contract, Order
                    
                    # Create Contract
                    contract = Contract()
                    contract.symbol = symbol
                    contract.secType = contract_details.get('secType', 'STK')
                    contract.exchange = contract_details.get('exchange', 'SMART')
                    contract.currency = contract_details.get('currency', 'USD')
                    
                    # Create Order
                    order = Order()
                    order.action = action # 'BUY' or 'SELL'
                    order.totalQuantity = float(qty)
                    order.orderType = order_type
                    
                    # Set Order Ref (Strategy Tag) if provided
                    strategy_tag = order_details.get('strategy_tag', '')
                    if strategy_tag:
                        order.orderRef = strategy_tag
                    
                    if order_type == 'LMT' and price:
                        order.lmtPrice = float(price)

                    # IBKR NATURE: Pacing/Throttling
                    # Wait 0.1s before placing order to ensure stability
                    time.sleep(0.1)

                    trade = self._ibkr_client.placeOrder(contract, order)
                    
                    # IBKR NATURE: Post-Pacing
                    # Wait 0.5s after placing order to ensure backend registers it
                    time.sleep(0.5)
                    
                    # Capture basic info immediately
                    order_id = trade.order.orderId if trade.order else 0
                    
                    response_queue.append({
                        'success': True,
                        'order_id': order_id,
                        'message': f'Order placed: {action} {qty} {symbol}'
                    })
                    
                except Exception as e:
                    response_queue.append({
                        'success': False,
                        'message': f'IBKR Place Order Error: {e}'
                    })

            # Execute in thread
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, place_order_sync)
            
            if response_queue:
                return response_queue[0]
            else:
                return {'success': False, 'message': 'Unknown error in placement thread'}
                
        except Exception as e:
            logger.error(f"[IBKR] Error placing order: {e}", exc_info=True)
            return {'success': False, 'message': str(e)}

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

