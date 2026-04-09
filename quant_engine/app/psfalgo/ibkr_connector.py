"""
IBKR Gateway Connector - Phase 10.1 (Real Connection)

Connects to IBKR Gateway for positions, orders, and account summary.
Execution yok, order gönderimi yok. SADECE positions / open orders / account summary.

Key Principles:
- IBKR Gateway only (TWS kullanılmıyor). Port 4001.
- Default Port: 4001 (Live)
- Account selector (GUN / PED)
- Market data ALWAYS from HAMMER
- Execution ASLA yapılmayacak
- Port 4001 (GUN and PED)
"""
import asyncio

# NOTE: Do NOT patch asyncio at module level - it causes event loop conflicts
# All event loop setup must happen inside the worker thread

from typing import Optional, Dict, Any, List
from datetime import datetime
import time
import queue
import threading
from concurrent.futures import Future
import os
import sys

from app.core.logger import logger

# ib_insync import (lazy import - only when actually needed)
# PHASE 10.1: Do NOT import ib_insync at module level - it requires event loop
# Import will happen lazily in connect() method
IB_INSYNC_AVAILABLE = None  # Will be set lazily
IB = None
Contract = None
Position = None
Order = None
ExecutionFilter = None


class IBKRConnector:
    """
    IBKR Gateway Connector (READ-ONLY).
    
    Responsibilities:
    - Connect to IBKR Gateway
    - Get positions (READ-ONLY)
    - Get open orders (READ-ONLY)
    - Get account summary (READ-ONLY)
    - Account selector (GUN / PED)
    
    Does NOT:
    - Submit orders (except via place_order which acts as bridge)
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
        
        # IBKR Gateway connection (type will be IB after lazy import)
        self._ibkr_client: Optional[Any] = None
        # Loop where IBKR connection lives (usually a dedicated thread loop)
        self._ib_loop: Optional[asyncio.AbstractEventLoop] = None
        # Client ID used when connecting. Required for cancel: only same client can cancel its orders.
        self._client_id: Optional[int] = None
        # Thread that runs the IB event loop (run_forever). Set by connect_isolated_sync.
        self._ib_thread: Optional[threading.Thread] = None

        # IBKR Gateway Port (Default: 4001) – Live ONLY, same for GUN/PED. Never 4002.
        self.gateway_port = 4001
        
        logger.info(f"IBKRConnector initialized (account_type={account_type}, port: {self.gateway_port})")

    async def _run_on_ib_thread(self, func: Any, timeout: float = 5) -> Any:
        """
        Run sync IB API call safely on the IB loop/thread via executor or directly if sync.
        """
        if not self._ibkr_client:
            logger.warning(f"[IBKR] _run_on_ib_thread: connector not ready")
            return None
        
        if not self.connected:
            logger.warning(f"[IBKR] _run_on_ib_thread: not connected")
            return None

        try:
            loop = asyncio.get_running_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, func),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.debug(f"[IBKR] _run_on_ib_thread timeout ({timeout}s)")
            return None
        except Exception as e:
            logger.warning(f"[IBKR] _run_on_ib_thread error: {e}")
            return None

    def run_sync_on_ib_loop(self, func: Any, timeout: float = 15) -> Any:
        """
        Run a sync function on the IB thread's event loop (same session as connect).
        """
        if not self._ib_loop or not self.connected or not self._ibkr_client:
            logger.warning("[IBKR] run_sync_on_ib_loop: no IB loop or not connected")
            return None
        
        fut: Future[Any] = Future()

        def _run_in_loop() -> None:
            try:
                result = func()
                fut.set_result(result)
            except Exception as e:
                fut.set_exception(e)

        self._ib_loop.call_soon_threadsafe(_run_in_loop)
        try:
            return fut.result(timeout=timeout)
        except Exception as e:
            logger.warning(f"[IBKR] run_sync_on_ib_loop: {e}")
            return None

    def _get_open_orders_sync(self) -> List[Dict[str, Any]]:
        """Get open orders using openTrades() - the recommended ib_insync method.
        
        NOTE: reqOpenOrders() is deprecated and unreliable per ib_insync docs.
        openTrades() provides real-time accurate data for orders placed in this session.
        """
        if not self._ibkr_client: return []
        try:
            # Use openTrades() instead of reqOpenOrders() - per ib_insync documentation:
            # - reqOpenOrders() can return stale/inaccurate data
            # - openTrades() is fast, accurate, and real-time updated
            trades = self._ibkr_client.openTrades()
            return [_format_trade_to_order_dict(t, self.account_type) for t in (trades or [])]
        except Exception as e:
            logger.warning(f"[IBKR] _get_open_orders_sync error: {e}")
            return []

    def _get_open_orders_all_sync(self) -> List[Dict[str, Any]]:
        if not self._ibkr_client: return []
        try:
            trades = self._ibkr_client.reqAllOpenOrders()
            return [_format_trade_to_order_dict(t, self.account_type) for t in (trades or [])]
        except Exception: return []

    def _cancel_orders_sync(self, order_ids: List[int]) -> List[str]:
        if not self._ibkr_client: return []
        client = getattr(self._ibkr_client, "client", None)
        if not client: return []
        cancelled: List[str] = []
        for oid in order_ids:
            try:
                client.cancelOrder(int(oid))
                cancelled.append(str(oid))
                time.sleep(0.02)
            except Exception as e:
                msg = str(e).lower()
                if "10147" in msg or "not found" in msg:
                    cancelled.append(str(oid))
        return cancelled

    def _global_cancel_sync(self) -> bool:
        if not self._ibkr_client: return False
        try:
            self._ibkr_client.reqGlobalCancel()
            return True
        except Exception: return False

    def _get_filled_orders_sync(self) -> List[Dict[str, Any]]:
        if not self._ibkr_client: return []
        if not self._ibkr_client.isConnected(): return []
        try:
            fills = self._ibkr_client.reqExecutions(None)
        except Exception:
            return []
        
        from datetime import date
        today = date.today()
        order_list = []
        for fill in (fills or []):
            if not fill: continue
            execution = getattr(fill, "execution", None)
            if not execution: continue
            if getattr(execution, "time", None) and getattr(execution.time, "date", None):
                if execution.time.date() != today: continue
            
            side = "BUY" if getattr(execution, "side", "") == "BOT" else "SELL"
            shares = float(getattr(execution, "shares", 0) or 0)
            order_list.append({
                "order_id": getattr(execution, "orderId", 0),
                "symbol": fill.contract.symbol if fill.contract else "",
                "action": side,
                "qty": shares,
                "price": getattr(execution, "price", 0),
                "status": "Filled",
                "source": "IBKR",
                "account": getattr(execution, "acctNumber", self.account_type),
                "timestamp": execution.time.timestamp() if getattr(execution, "time", None) else time.time(),
            })
        return order_list

    async def connect(
        self,
        host: str = '127.0.0.1',
        port: Optional[int] = None,
        client_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Connect to IBKR Gateway using ib_insync.
        Must be called from a loop where IBKR operations will reside.
        """
        try:
            if client_id is None:
                client_id = 12 if self.account_type == "IBKR_PED" else 11

            hosts_to_try = [host]
            if host in ['127.0.0.1', 'localhost']:
                 hosts_to_try = ['127.0.0.1', 'localhost']

            if port is not None:
                ports_to_try = [int(port)]
            else:
                ports_to_try = [4001, 7497, 7496, 4002]

            logger.info(f"[IBKR] Attempting connection via hosts={hosts_to_try} ports={ports_to_try} (clientId={client_id})")

            ok, import_err = self._ensure_ib_insync()
            if not ok:
                 return {'success': False, 'error': f"ib_insync not available: {import_err}", 'connected': False}

            # Get connection loop - prefer pre-set loop from connect_isolated_sync
            if self._ib_loop:
                loop = self._ib_loop
            else:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    # No running loop - create new one
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            
            # Disconnect if needed
            if self._ibkr_client:
                try: self._ibkr_client.disconnect()
                except: pass
                self._ibkr_client = None
            self.connected = False

            # Create IB instance FRESH for this connection attempt
            ib = IB()
            
            # Explicitly force loops on everything possible to prevent mismatch and force proper binding
            if hasattr(ib, 'loop'): ib.loop = loop
            if hasattr(ib, '_loop'): ib._loop = loop
            
            if hasattr(ib, 'client'):
                 if hasattr(ib.client, 'loop'): ib.client.loop = loop
                 if hasattr(ib.client, '_loop'): ib.client._loop = loop
                 if hasattr(ib.client, 'setLoop'): ib.client.setLoop(loop)
            
            if hasattr(ib, 'wrapper'):
                 if hasattr(ib.wrapper, 'loop'): ib.wrapper.loop = loop
                 if hasattr(ib.wrapper, '_loop'): ib.wrapper._loop = loop
            
            connected = False
            last_error = None
            
            for p in ports_to_try:
                if connected: break
                for h in hosts_to_try:
                    if connected: break
                    try:
                        logger.info(f"[IBKR] Connecting to {h}:{p}...")
                        if ib.isConnected(): 
                            ib.disconnect()
                        
                        await ib.connectAsync(h, p, clientId=int(client_id), timeout=10)
                        
                        ib.reqMarketDataType(1) # Live
                        
                        self._ibkr_client = ib
                        self._ib_loop = loop
                        self._client_id = int(client_id)
                        self.connected = True
                        self.connection_error = None
                        self.gateway_port = p
                        
                        logger.info(f"[IBKR] ✅ Connected to {self.account_type} at {h}:{p} (clientId={client_id})")
                        await self._register_fill_recovery()
                        asyncio.create_task(self._auto_track_befday_task())
                        
                        connected = True
                        return {'success': True, 'connected': True, 'account_type': self.account_type, 'host': h, 'port': p}
                        
                    except Exception as e:
                        last_error = str(e)
                        logger.warning(f"[IBKR] Failed to connect to {h}:{p}: {e}")
                        try: ib.disconnect()
                        except: pass
            
            error_msg = f"All connection attempts failed. Last error: {last_error}"
            logger.error(f"[IBKR] {error_msg}")
            self.connected = False
            self.connection_error = error_msg
            return {'success': False, 'error': error_msg, 'connected': False}

        except Exception as e:
            self.connected = False
            self.connection_error = str(e)
            logger.error(f"[IBKR] Critical connection error: {e}", exc_info=True)
            return {'success': False, 'error': str(e), 'connected': False}

    def _ensure_ib_insync(self) -> tuple[bool, str]:
        """Lazy import ib_insync with Python 3.14 compatibility fixes."""
        global IB_INSYNC_AVAILABLE, IB, Contract, Position, Order, ExecutionFilter
        
        if IB_INSYNC_AVAILABLE is not None:
            return (IB_INSYNC_AVAILABLE, "")

        try:
            if sys.platform == 'win32':
                try: asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                except: pass

            try:
                import nest_asyncio
                nest_asyncio.apply()
            except ImportError: pass

            # Fix get_event_loop to prioritize running loop (CRITICAL)
            if not hasattr(asyncio, "_qe_orig_get_event_loop"):
                asyncio._qe_orig_get_event_loop = asyncio.get_event_loop # type: ignore

                def _qe_compat_get_event_loop():
                    try:
                        return asyncio.get_running_loop()
                    except RuntimeError:
                        pass
                    # Fallback
                    try: return asyncio._qe_orig_get_event_loop() # type: ignore
                    except: return asyncio.new_event_loop()

                asyncio.get_event_loop = _qe_compat_get_event_loop # type: ignore

            # Fix asyncio.timeout for ib_insync usage outside tasks
            if not hasattr(asyncio, "_qe_orig_timeout"):
                asyncio._qe_orig_timeout = asyncio.timeout # type: ignore
                class _QeCompatTimeout:
                    def __init__(self, *args, **kwargs):
                        self._args = args; self._kwargs = kwargs; self._inner = None
                    async def __aenter__(self):
                        try:
                            self._inner = asyncio._qe_orig_timeout(*self._args, **self._kwargs) # type: ignore
                            return await self._inner.__aenter__()
                        except RuntimeError as e:
                            if "inside a task" in str(e): return None
                            raise
                    async def __aexit__(self, exc_type, exc, tb):
                        if self._inner is not None: return await self._inner.__aexit__(exc_type, exc, tb)
                        return False
                asyncio.timeout = lambda *a, **k: _QeCompatTimeout(*a, **k) # type: ignore

            from ib_insync import (
                IB as IBClass, Contract as ContractClass, Position as PositionClass,
                Order as OrderClass, ExecutionFilter as ExecFilterClass
            )
            IB = IBClass; Contract = ContractClass; Position = PositionClass
            Order = OrderClass; ExecutionFilter = ExecFilterClass
            IB_INSYNC_AVAILABLE = True
            logger.info("[IBKR] ib_insync (nibkrtry-style) loaded ✅")
            return (True, "")
        except Exception as e:
            IB_INSYNC_AVAILABLE = False
            return (False, str(e))

    async def _register_fill_recovery(self) -> None:
        if not self._ibkr_client: return
        def on_exec_details(trade, fill):
            try:
                execution = fill.execution
                symbol = trade.contract.symbol
                action = "BUY" if execution.side == "BOT" else "SELL"
                fill_id = str(execution.execId) if hasattr(execution, 'execId') else None
                # Extract fill time from IBKR execution (format: "20260303 15:30:45")
                fill_time_str = str(execution.time) if hasattr(execution, 'time') and execution.time else None
                try:
                    from app.trading.daily_fills_store import get_daily_fills_store
                    store = get_daily_fills_store()
                    # CRITICAL: Fetch bid/ask from shared market_data_cache NOW
                    # L1 data comes from Hammer and is shared across all accounts
                    _fill_bid, _fill_ask = None, None
                    try:
                        from app.api.market_data_routes import get_market_data
                        from app.live.symbol_mapper import SymbolMapper
                        # Try display format first (market_data_cache key format)
                        for _sym_variant in [symbol, SymbolMapper.to_display_symbol(symbol), SymbolMapper.to_hammer_symbol(symbol)]:
                            _md = get_market_data(_sym_variant)
                            if _md and _md.get('bid') and _md.get('ask') and float(_md['bid']) > 0 and float(_md['ask']) > 0:
                                _fill_bid = float(_md['bid'])
                                _fill_ask = float(_md['ask'])
                                break
                    except Exception:
                        pass
                    store.log_fill(self.account_type, symbol, action, execution.shares, execution.price, execution.orderRef or "UNKNOWN", fill_id=fill_id, fill_time=fill_time_str, bid=_fill_bid, ask=_fill_ask)
                except Exception as fill_err:
                    logger.error(f"[IBKR_FILL] ❌ CRITICAL: Failed to log fill {symbol} {action} {execution.shares}@{execution.price} to CSV: {fill_err}")
                # Redis publish (with bench_chg)
                try:
                    from app.core.event_bus import EventBus
                    from app.trading.daily_fills_store import get_daily_fills_store
                    bench_chg, bench_source = get_daily_fills_store()._fetch_benchmark_for_symbol(symbol)
                    ledger_data = {
                        "event": "FILL", "symbol": symbol, "qty": str(execution.shares),
                        "price": str(execution.price), "action": action, "account_id": self.account_type,
                        "order_id": str(execution.orderId) if hasattr(execution, 'orderId') else "",
                        "fill_id": fill_id or "",
                        "tag": str(execution.orderRef) if hasattr(execution, 'orderRef') else "",
                        "timestamp": datetime.now().isoformat()
                    }
                    if bench_chg is not None:
                        ledger_data["bench_chg"] = str(round(bench_chg, 4))
                        ledger_data["bench_source"] = bench_source or ""
                    EventBus.xadd("psfalgo:execution:ledger", ledger_data)
                    # Log metrics snapshot at fill time
                    try:
                        from app.api.market_data_routes import get_janall_metrics_engine as _gj
                        _jeng = _gj()
                        if _jeng and hasattr(_jeng, 'symbol_metrics_cache'):
                            _jd = _jeng.symbol_metrics_cache.get(symbol, {})
                            if _jd:
                                logger.info(
                                    f"[IBKR_FILL] 📊 {symbol} {action} {execution.shares}@{execution.price} "
                                    f"tag={execution.orderRef} | METRICS: "
                                    f"fbtot={_jd.get('fbtot')} sfstot={_jd.get('sfstot')} gort={_jd.get('gort')} "
                                    f"ucuz={_jd.get('bid_buy_ucuzluk')} pah={_jd.get('ask_sell_pahalilik')} "
                                    f"bid={_jd.get('_breakdown',{}).get('inputs',{}).get('bid')} "
                                    f"ask={_jd.get('_breakdown',{}).get('inputs',{}).get('ask')} "
                                    f"last={_jd.get('_breakdown',{}).get('inputs',{}).get('last')}"
                                )
                    except Exception:
                        pass  # Best effort
                except Exception as redis_err:
                    logger.warning(f"[IBKR_FILL] Redis publish failed for {symbol}: {redis_err}")
                
                # ── Update PositionTagStore (Dual Tag v4, per-account) ──
                try:
                    from app.psfalgo.fill_tag_handler import handle_fill_for_tagging
                    order_ref = str(execution.orderRef) if hasattr(execution, 'orderRef') and execution.orderRef else "UNKNOWN"
                    handle_fill_for_tagging(
                        symbol=symbol,
                        fill_qty=execution.shares,
                        action=action,
                        source=order_ref,
                        tag=order_ref,
                        account_id=self.account_type
                    )
                except Exception as tag_err:
                    logger.debug(f"[IBKR_FILL] PositionTag update error for {symbol}: {tag_err}")

                # ── Update OrderLifecycleTracker (fill price available) ──
                try:
                    from app.monitoring.order_lifecycle_tracker import get_order_lifecycle_tracker
                    tracker = get_order_lifecycle_tracker()
                    order_ref = str(execution.orderRef) if hasattr(execution, 'orderRef') and execution.orderRef else ""
                    tracker.on_fill(
                        symbol=symbol,
                        action=action,
                        fill_price=execution.price,
                        tag=order_ref,
                        account_id=self.account_type,
                        fill_qty=int(execution.shares),
                    )
                except Exception as tracker_err:
                    logger.debug(f"[IBKR_FILL] OrderLifecycleTracker error for {symbol}: {tracker_err}")
            except Exception as outer_err:
                logger.error(f"[IBKR_FILL] ❌ on_exec_details handler failed: {outer_err}", exc_info=True)
        self._ibkr_client.execDetailsEvent += on_exec_details
        try:
            # ExecutionFilter may be None if lazy import hasn't completed yet
            # ib_insync's reqExecutions accepts None as filter (returns all executions)
            exec_filter = ExecutionFilter() if ExecutionFilter is not None else None
            self._ibkr_client.reqExecutions(exec_filter)
        except Exception as req_err:
            logger.warning(f"[IBKR_FILL] reqExecutions failed: {req_err}")

    async def _auto_track_befday_task(self):
        """
        Smart BEFDAY auto-capture on IBKR connection.
        
        Rules:
        - ONLY captures if today's BEFDAY has NOT been captured yet (first boot of the day).
        - Mid-day reconnects are safe: has_captured_today() returns True after first capture.
        - BEFDAY is still SACRED — exactly 1 capture per account per day.
        - This replaces the old "button click only" approach which caused stale BEFDAY data
          every morning because nobody clicked the button before trading started.
        - RETRY: If 0 positions returned (IBKR not settled), retry up to 3 times with
          increasing delays (5s, 10s, 15s) before giving up.
        """
        try:
            await asyncio.sleep(5)  # Wait 5s for IBKR positions to settle after connect
            
            # Map account_type to befday account name
            account_map = {"IBKR_PED": "ibped", "IBKR_GUN": "ibgun", "HAMPRO": "ham"}
            bef_account = account_map.get(self.account_type)
            if not bef_account:
                logger.warning(f"[IBKR] BEFDAY auto-track: unknown account_type {self.account_type}")
                return
            
            # Check if already captured today — if yes, skip (sacred rule)
            try:
                from app.api.befday_routes import has_captured_today
                if has_captured_today(bef_account):
                    logger.info(f"[IBKR] BEFDAY already captured today for {bef_account} — skipping auto-capture")
                    return
            except Exception as check_err:
                logger.warning(f"[IBKR] BEFDAY capture check failed: {check_err}")
                return
            
            # First connection of the day — auto-capture BEFDAY
            logger.info(f"[IBKR] 🔥 First connection of the day for {self.account_type} — auto-capturing BEFDAY...")
            
            # Clear stale Redis BEFDAY key from yesterday
            try:
                from app.core.redis_client import get_redis_client
                redis = get_redis_client()
                if redis:
                    stale_key = f"psfalgo:befday:positions:{self.account_type}"
                    stale_date_key = f"psfalgo:befday:date:{self.account_type}"
                    redis.delete(stale_key)
                    redis.delete(stale_date_key)
                    logger.info(f"[IBKR] Cleared stale Redis BEFDAY keys: {stale_key}, {stale_date_key}")
            except Exception as redis_err:
                logger.warning(f"[IBKR] Redis stale key cleanup failed: {redis_err}")
            
            # RETRY LOOP: IBKR may need time to settle position data
            max_retries = 6
            retry_delays = [5, 10, 15, 20, 30, 45]  # seconds between retries — extended to give IBKR time
            
            for attempt in range(max_retries):
                try:
                    from app.api.befday_routes import capture_befday, has_captured_today as _hct
                    
                    # Re-check before each attempt (maybe the frontend captured it meanwhile)
                    if _hct(bef_account):
                        logger.info(f"[IBKR] BEFDAY captured by another path for {bef_account} — stopping retry")
                        return
                    
                    result = await capture_befday(bef_account, force=False)
                    if result and result.get("success"):
                        pos_count = result.get("position_count", 0)
                        if pos_count > 0:
                            logger.info(f"[IBKR] ✅ BEFDAY auto-captured for {bef_account}: {pos_count} positions (attempt {attempt + 1})")
                            return  # SUCCESS — done
                        else:
                            logger.warning(f"[IBKR] BEFDAY auto-capture returned 0 positions on attempt {attempt + 1}/{max_retries}")
                    else:
                        error_msg = result.get("error", "unknown") if result else "no result"
                        logger.warning(f"[IBKR] BEFDAY auto-capture returned non-success on attempt {attempt + 1}/{max_retries}: {error_msg}")
                    
                    # Wait before retry (unless last attempt)
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        logger.info(f"[IBKR] BEFDAY retry in {delay}s for {bef_account}...")
                        await asyncio.sleep(delay)
                        
                except Exception as cap_err:
                    logger.error(f"[IBKR] BEFDAY auto-capture failed on attempt {attempt + 1}: {cap_err}", exc_info=True)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delays[attempt])
            
            logger.error(f"[IBKR] ❌ BEFDAY auto-capture FAILED after {max_retries} attempts for {bef_account}. "
                         f"Manual capture will be triggered on next UI click.")
                
        except Exception as e:
            logger.error(f"[IBKR] _auto_track_befday_task error: {e}", exc_info=True)

    async def disconnect(self):
        try:
            if self._ibkr_client:
                try: self._ibkr_client.disconnect()
                except: pass
            self.connected = False
            self._ibkr_client = None
            logger.info(f"[IBKR] Disconnected {self.account_type}")
        except Exception as e: logger.error(f"[IBKR] Disconnect error: {e}")

    async def get_positions(self) -> List[Dict[str, Any]]:
        # Sync wrapper around _run_on_ib_thread etc similar to original...
        if not self.connected or not self._ibkr_client: return []
        if not self._ensure_ib_insync()[0]: return []
        try:
            # Note: lambda works because _run_on_ib_thread uses executor
            positions_list = await self._run_on_ib_thread(lambda: self._ibkr_client.positions(), timeout=8)
            if positions_list is None: return []
            account_positions = []
            for pos in positions_list:
                account_positions.append({
                    'symbol': pos.contract.symbol,
                    'qty': pos.position,
                    'avg_price': float(getattr(pos, 'averageCost', 0) or 0),
                    'account': pos.account,
                    'contract': {'symbol': pos.contract.symbol, 'secType': pos.contract.secType, 'currency': pos.contract.currency}
                })
            return account_positions
        except Exception as e:
            logger.error(f"[IBKR] get_positions error: {e}")
            return []

    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get open orders using openTrades() - the recommended ib_insync method.
        
        NOTE: reqOpenOrders() is deprecated and unreliable per ib_insync docs.
        openTrades() provides real-time accurate data for orders placed in this session.
        """
        if not self.connected or not self._ibkr_client: return []
        if not self._ensure_ib_insync()[0]: return []
        try:
            # Use openTrades() instead of reqOpenOrders() - much faster and more accurate
            trades = await self._run_on_ib_thread(lambda: self._ibkr_client.openTrades(), timeout=5)
            if trades is None: return []
            return [_format_trade_to_order_dict(t, self.account_type) for t in trades]
        except Exception as e:
            logger.error(f"[IBKR] get_open_orders error: {e}")
            return []

    async def get_filled_orders(self) -> List[Dict[str, Any]]:
        if not self.connected or not self._ibkr_client: return []
        try:
            fills = await self._run_on_ib_thread(lambda: self._ibkr_client.reqExecutions(), timeout=15)
            if fills is None: return []
            from datetime import date
            today = date.today()
            order_list = []
            for fill in fills:
                if fill.execution.time.date() != today: continue
                order_list.append({
                    'order_id': fill.execution.orderId,
                    'symbol': fill.contract.symbol,
                    'action': "BUY" if fill.execution.side == "BOT" else "SELL",
                    'qty': float(fill.execution.shares),
                    'price': fill.execution.price,
                    'status': 'Filled',
                    'source': 'IBKR',
                    'timestamp': fill.execution.time.timestamp()
                })
            return order_list
        except: return []

    async def cancel_orders(self, order_ids: List[int]) -> List[str]:
        if not self.connected or not self._ibkr_client: return []
        def _do_cancel():
            cancelled = []
            client = getattr(self._ibkr_client, "client", None)
            if not client: return []
            for oid in order_ids:
                try:
                    client.cancelOrder(int(oid))
                    cancelled.append(str(oid))
                except: pass
            return cancelled
        out = await self._run_on_ib_thread(_do_cancel, timeout=8)
        return out if isinstance(out, list) else []

    async def get_account_summary(self) -> Dict[str, Any]:
        if not self.connected: return {}
        try:
            ave = await self._run_on_ib_thread(lambda: self._ibkr_client.accountValues(), timeout=8)
            if ave is None: return {'account': self.account_type, 'connected': False}
            summary = {'account': self.account_type, 'connected': True}
            for av in ave:
                if av.tag == 'NetLiquidation': summary['net_liquidation'] = float(av.value)
                elif av.tag == 'BuyingPower': summary['buying_power'] = float(av.value)
                elif av.tag == 'TotalCashValue': summary['total_cash'] = float(av.value)
            return summary
        except: return {}

    async def place_order(self, contract_details: Dict[str, Any], order_details: Dict[str, Any]) -> Dict[str, Any]:
        if not self.connected or not self._ibkr_client: return {'success': False, 'message': 'Not connected'}
        if not self._ensure_ib_insync()[0]: return {'success': False, 'message': 'ib_insync missing'}
        try:
            symbol = contract_details.get('symbol')
            action = order_details.get('action')
            qty = order_details.get('totalQuantity')
            price = order_details.get('lmtPrice')
            # DUPLICATE CHECK - Using Redis cache (instant) instead of slow 12s timeout IBKR API call
            # This provides duplicate protection without the performance penalty
            # NOTE: Uses STRING-based JSON list format to match xnl_engine.py (not HASH)
            try:
                from app.core.redis_client import get_redis_client
                import json
                r = get_redis_client()
                if r:
                    orders_key = f"psfalgo:open_orders:{self.account_type}"
                    raw = r.get(orders_key)
                    if raw:
                        s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                        cached_list = json.loads(s) if isinstance(s, str) else []
                        # Handle wrapped format
                        if isinstance(cached_list, dict) and 'orders' in cached_list:
                            cached_list = cached_list['orders']
                        if isinstance(cached_list, list):
                            our_tag = (order_details.get('strategy_tag') or '').upper()
                            for o in cached_list:
                                cached_tag = (o.get('tag') or o.get('strategy_tag') or '').upper()
                                if (o.get('symbol') == symbol and 
                                    o.get('action') == action and 
                                    abs(float(o.get('price', 0)) - float(price or 0)) < 0.01 and
                                    cached_tag == our_tag):
                                    logger.warning(f"[IBKR] Duplicate order detected (cache): {symbol} {action} @ {price} tag={our_tag}")
                                    return {'success': False, 'message': f"Duplicate order: {symbol}", 'duplicate': True}
            except Exception as cache_err:
                logger.debug(f"[IBKR] Duplicate cache check skipped: {cache_err}")

            contract = Contract()
            contract.symbol = symbol
            contract.secType = 'STK'
            contract.exchange = contract_details.get('exchange') or order_details.get('exchange') or 'SMART'
            contract.currency = 'USD'
            
            order = Order()
            order.action = action; order.totalQuantity = float(qty)
            order.orderType = 'LMT'; order.lmtPrice = float(price)
            order.hidden = True; order.displaySize = 0
            if order_details.get('strategy_tag'): order.orderRef = order_details['strategy_tag']

            trade = await self._run_on_ib_thread(lambda: self._ibkr_client.placeOrder(contract, order), timeout=5)

            if trade:
                order_id = trade.order.orderId
                logger.info(f"[IBKR] Placed {action} {qty} {symbol} @ {price} (ID: {order_id})")
                
                # Push to Redis so UI can see the order (STRING-based JSON list format)
                try:
                    from app.core.redis_client import get_redis_client
                    import json
                    import time
                    r = get_redis_client()
                    if r:
                        orders_key = f"psfalgo:open_orders:{self.account_type}"
                        order_data = {
                            'order_id': str(order_id),
                            'symbol': symbol,
                            'action': action,
                            'quantity': float(qty),
                            'price': float(price),
                            'order_type': 'LMT',
                            'status': 'Submitted',
                            'tag': order_details.get('strategy_tag', ''),
                            'timestamp': time.time(),
                            'source': 'IBKR'
                        }
                        # Use STRING-based JSON list (matches xnl_engine.py format)
                        raw = r.get(orders_key)
                        existing_list = []
                        parsed = []
                        if raw:
                            s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                            try:
                                parsed = json.loads(s) if isinstance(s, str) else []
                            except: parsed = []
                        # Handle wrapped format
                        if isinstance(parsed, dict) and 'orders' in parsed:
                            existing_list = parsed['orders'] if isinstance(parsed['orders'], list) else []
                        elif isinstance(parsed, list):
                            existing_list = parsed
                        else:
                            existing_list = []
                        if not isinstance(existing_list, list):
                            existing_list = []
                        # Add new order (avoid duplicates by order_id)
                        existing_list = [o for o in existing_list if str(o.get('order_id')) != str(order_id)]
                        existing_list.append(order_data)
                        payload = {'orders': existing_list, '_meta': {'updated_at': time.time()}}
                        r.set(orders_key, json.dumps(payload), ex=600)
                        logger.debug(f"[IBKR] Pushed order {order_id} to Redis {orders_key} ({len(existing_list)} orders)")
                except Exception as redis_err:
                    logger.warning(f"[IBKR] Redis push failed: {redis_err}")
                
                return {'success': True, 'order_id': order_id, 'message': f"Order placed (ID: {order_id})"}
            else:
                 return {'success': False, 'message': 'Place order failed (No Trade object)'}

        except Exception as e:
            logger.error(f"[IBKR] place_order error: {e}", exc_info=True)
            return {'success': False, 'message': str(e)}

    def is_connected(self) -> bool: return self.connected


# Global instances
_ibkr_gun_connector: Optional[IBKRConnector] = None
_ibkr_ped_connector: Optional[IBKRConnector] = None
_active_ibkr_account: Optional[str] = None
_REDIS_ACTIVE_ACCOUNT_KEY = "psfalgo:ibkr:active_account"

def get_active_ibkr_account() -> Optional[str]:
    try:
        from app.core.redis_client import get_redis_client
        r = get_redis_client()
        if r and getattr(r, 'sync', None):
            active = r.sync.get(_REDIS_ACTIVE_ACCOUNT_KEY)
            if active:
                val = active.decode('utf-8') if isinstance(active, bytes) else active
                global _active_ibkr_account; _active_ibkr_account = val
                return val
    except: pass
    return _active_ibkr_account

def set_active_ibkr_account(account_type: Optional[str]) -> None:
    global _active_ibkr_account; _active_ibkr_account = account_type
    try:
        from app.core.redis_client import get_redis_client
        r = get_redis_client()
        if r and getattr(r, 'sync', None):
            if account_type: r.sync.set(_REDIS_ACTIVE_ACCOUNT_KEY, account_type)
            else: r.sync.delete(_REDIS_ACTIVE_ACCOUNT_KEY)
    except: pass

def _clear_redis_open_orders_for_account(account_type: str) -> None:
    try:
        from app.core.redis_client import get_redis_client
        r = get_redis_client()
        if r: r.delete(f"psfalgo:open_orders:{account_type}")
    except: pass

def get_ibkr_connector(account_type: str = "IBKR_GUN", create_if_missing: bool = True) -> Optional[IBKRConnector]:
    global _ibkr_gun_connector, _ibkr_ped_connector
    if account_type == "IBKR_GUN":
        if _ibkr_gun_connector is None:
            if not create_if_missing: return None
            _ibkr_gun_connector = IBKRConnector(account_type="IBKR_GUN")
        return _ibkr_gun_connector
    elif account_type == "IBKR_PED":
        if _ibkr_ped_connector is None:
            if not create_if_missing: return None
            _ibkr_ped_connector = IBKRConnector(account_type="IBKR_PED")
        return _ibkr_ped_connector
    return None

def get_ibkr_order_client_id(account_type: str) -> Optional[int]:
    conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
    return getattr(conn, "_client_id", None) if conn and conn.connected else None

def disconnect_other_ibkr_account(keep_active: str) -> None:
    global _ibkr_gun_connector, _ibkr_ped_connector
    if keep_active == "IBKR_GUN":
        if _ibkr_ped_connector and _ibkr_ped_connector.connected:
            try: _ibkr_ped_connector._ibkr_client.disconnect()
            except: pass
            _ibkr_ped_connector.connected = False; _ibkr_ped_connector._ibkr_client = None
    elif keep_active == "IBKR_PED":
        if _ibkr_gun_connector and _ibkr_gun_connector.connected:
             try: _ibkr_gun_connector._ibkr_client.disconnect()
             except: pass
             _ibkr_gun_connector.connected = False; _ibkr_gun_connector._ibkr_client = None

# Helpers for standalone/sync usage via worker thread if needed
def _format_trade_to_order_dict(trade: Any, account_type: str) -> Dict[str, Any]:
    order = trade.order
    status = trade.orderStatus.status if trade.orderStatus else 'UNKNOWN'
    return {
        'order_id': order.orderId, 'symbol': trade.contract.symbol, 'action': order.action,
        'qty': order.totalQuantity, 'price': order.lmtPrice or order.price, 'status': status,
        'account': getattr(order, 'account', account_type), 'source': 'IBKR',
        'strategy_tag': getattr(order, 'orderRef', '')
    }

def get_positions_isolated_sync(account_type: str) -> List[Dict[str, Any]]:
    """Get IBKR positions using isolated sync call on IB thread."""
    conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
    if not conn or not conn.connected:
        logger.warning(f"[get_positions_isolated_sync] No connected IBKR connector for {account_type}")
        return []
    
    def _get_positions_sync():
        if not conn._ibkr_client:
            return []
        try:
            positions_list = conn._ibkr_client.positions()
            if positions_list is None:
                return []
            account_positions = []
            for pos in positions_list:
                account_positions.append({
                    'symbol': pos.contract.symbol,
                    'qty': pos.position,
                    'avg_price': float(getattr(pos, 'averageCost', 0) or 0),
                    'account': pos.account,
                    'contract': {'symbol': pos.contract.symbol, 'secType': pos.contract.secType, 'currency': pos.contract.currency}
                })
            return account_positions
        except Exception as e:
            logger.error(f"[get_positions_isolated_sync] Error: {e}")
            return []
    
    return conn.run_sync_on_ib_loop(_get_positions_sync, timeout=15) or []

def get_open_orders_isolated_sync(account_type: str) -> List[Dict[str, Any]]:
    """Get open orders using openTrades() - fast since it uses local ib_insync cache."""
    conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
    if not conn or not conn.connected: return []
    # Timeout reduced to 3s since openTrades() uses local cache (no API round-trip)
    return conn.run_sync_on_ib_loop(conn._get_open_orders_sync, timeout=3) or []

def get_open_orders_all_isolated_sync(account_type: str) -> List[Dict[str, Any]]:
    conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
    if not conn or not conn.connected: return []
    return conn.run_sync_on_ib_loop(conn._get_open_orders_all_sync, timeout=18) or []

def get_filled_orders_isolated_sync(account_type: str) -> List[Dict[str, Any]]:
    conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
    if not conn or not conn.connected: return []
    return conn.run_sync_on_ib_loop(conn._get_filled_orders_sync, timeout=5) or []

def cancel_orders_isolated_sync(account_type: str, order_ids: List[int]) -> List[str]:
    conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
    if not conn or not conn.connected: return []
    return conn.run_sync_on_ib_loop(lambda: conn._cancel_orders_sync(order_ids), timeout=20) or []

def global_cancel_isolated_sync(account_type: str) -> bool:
    conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
    if not conn or not conn.connected: return False
    return conn.run_sync_on_ib_loop(conn._global_cancel_sync, timeout=10) is True

def place_order_isolated_sync(
    account_type: str,
    contract_details: Dict[str, Any],
    order_details: Dict[str, Any]
) -> Dict[str, Any]:
    """Place order via IBKR using isolated sync call on IB thread.
    
    Same pattern as other isolated_sync functions — runs on the IB event loop
    thread to avoid asyncio conflicts with FastAPI's event loop.
    """
    # ═══════════════════════════════════════════════════════════════
    # MARKET HOURS GUARD — Block ALL orders outside regular hours
    # After-hours fills are catastrophic due to wide spreads.
    # WRB-F 2026-03-11: SELL @$18.15 when TT ~$20 (after-hours)
    # ═══════════════════════════════════════════════════════════════
    try:
        from app.trading.hammer_execution_service import _is_us_market_open
        if not _is_us_market_open():
            symbol = contract_details.get('symbol', '?')
            action = order_details.get('action', '?')
            qty = order_details.get('totalQuantity', 0)
            price = order_details.get('lmtPrice', 0)
            tag = order_details.get('strategy_tag', '')
            logger.warning(
                f"🚫 [MARKET_CLOSED] IBKR Order BLOCKED — market is closed! "
                f"{symbol} {action} {qty} @ ${float(price):.4f} (Tag: {tag})"
            )
            return {'success': False, 'message': 'Market is closed — order blocked'}
    except Exception as mh_err:
        logger.warning(f"[MARKET_HOURS] Check failed (allowing order): {mh_err}")
    
    # ═══════════════════════════════════════════════════════════════
    # ORDER GUARD — EXCLUDED LIST CHECK (LAST BARRIER)
    # This catches ANY excluded symbol regardless of which engine
    # generated the order. qe_excluded.csv is the single source of truth.
    # ═══════════════════════════════════════════════════════════════
    try:
        from app.trading.order_guard import is_order_allowed
        _guard_symbol = contract_details.get('symbol', '?')
        _guard_action = order_details.get('action', '?')
        _guard_qty = order_details.get('totalQuantity', 0)
        _guard_tag = order_details.get('strategy_tag', '')
        allowed, guard_reason = is_order_allowed(
            symbol=_guard_symbol, side=_guard_action, quantity=_guard_qty,
            tag=_guard_tag, account_id=account_type
        )
        if not allowed:
            logger.error(
                f"🚫 [ORDER_GUARD] IBKR BLOCKED: {_guard_symbol} {_guard_action} {_guard_qty} "
                f"(Tag: {_guard_tag}, Account: {account_type}) — {guard_reason}"
            )
            return {'success': False, 'message': f'ORDER_GUARD BLOCKED: {guard_reason}'}
    except Exception as guard_err:
        logger.warning(f"[ORDER_GUARD] Guard check failed (allowing order): {guard_err}")
    
    conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
    if not conn or not conn.connected:
        return {'success': False, 'message': f'IBKR connector not connected for {account_type}'}
    
    if not conn._ibkr_client:
        return {'success': False, 'message': 'No IBKR client available'}
    
    def _place_order_sync():
        try:
            _ensure = conn._ensure_ib_insync()
            if not _ensure[0]:
                return {'success': False, 'message': 'ib_insync not available'}
            
            symbol = contract_details.get('symbol')
            action = order_details.get('action')
            qty = order_details.get('totalQuantity')
            price = order_details.get('lmtPrice')
            
            # Duplicate check via Redis
            try:
                from app.core.redis_client import get_redis_client
                import json
                r = get_redis_client()
                if r:
                    orders_key = f"psfalgo:open_orders:{account_type}"
                    raw = r.get(orders_key)
                    if raw:
                        s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                        cached_list = json.loads(s) if isinstance(s, str) else []
                        # Handle wrapped format
                        if isinstance(cached_list, dict) and 'orders' in cached_list:
                            cached_list = cached_list['orders']
                        if isinstance(cached_list, list):
                            our_tag = (order_details.get('strategy_tag') or '').upper()
                            for o in cached_list:
                                cached_tag = (o.get('tag') or o.get('strategy_tag') or '').upper()
                                if (o.get('symbol') == symbol and
                                    o.get('action') == action and
                                    abs(float(o.get('price', 0)) - float(price or 0)) < 0.01 and
                                    cached_tag == our_tag):
                                    logger.warning(f"[IBKR] Duplicate order detected (cache): {symbol} {action} @ {price} tag={our_tag}")
                                    return {'success': False, 'message': f"Duplicate order: {symbol}", 'duplicate': True}
            except Exception as cache_err:
                logger.debug(f"[IBKR] Duplicate cache check skipped: {cache_err}")
            
            contract = Contract()
            contract.symbol = symbol
            contract.secType = 'STK'
            contract.exchange = contract_details.get('exchange') or order_details.get('exchange') or 'SMART'
            contract.currency = 'USD'
            
            order = Order()
            order.action = action
            order.totalQuantity = float(qty)
            order.orderType = 'LMT'
            order.lmtPrice = float(price)
            order.hidden = True
            order.displaySize = 0
            if order_details.get('strategy_tag'):
                order.orderRef = order_details['strategy_tag']
            
            trade = conn._ibkr_client.placeOrder(contract, order)
            
            if trade:
                order_id = trade.order.orderId
                logger.info(f"[IBKR] ✅ Placed {action} {qty} {symbol} @ {price} (ID: {order_id})")
                
                # ── OrderLifecycleTracker: record order sent ──
                try:
                    from app.monitoring.order_lifecycle_tracker import get_order_lifecycle_tracker
                    get_order_lifecycle_tracker().on_order_sent(
                        symbol=symbol, action=action, price=float(price),
                        lot=int(float(qty)), tag=order_details.get('strategy_tag', ''),
                        account_id=account_type,
                        order_id=str(order_id),
                    )
                except Exception:
                    pass
                
                # Push to Redis
                try:
                    import json, time
                    from app.core.redis_client import get_redis_client
                    r = get_redis_client()
                    if r:
                        orders_key = f"psfalgo:open_orders:{account_type}"
                        order_data = {
                            'order_id': str(order_id),
                            'symbol': symbol,
                            'action': action,
                            'quantity': float(qty),
                            'price': float(price),
                            'order_type': 'LMT',
                            'status': 'Submitted',
                            'tag': order_details.get('strategy_tag', ''),
                            'timestamp': time.time(),
                            'source': 'IBKR'
                        }
                        raw = r.get(orders_key)
                        existing_list = []
                        parsed = []
                        if raw:
                            s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                            try:
                                parsed = json.loads(s) if isinstance(s, str) else []
                            except: parsed = []
                        # Handle wrapped format
                        if isinstance(parsed, dict) and 'orders' in parsed:
                            existing_list = parsed['orders'] if isinstance(parsed['orders'], list) else []
                        elif isinstance(parsed, list):
                            existing_list = parsed
                        else:
                            existing_list = []
                        if not isinstance(existing_list, list):
                            existing_list = []
                        existing_list = [o for o in existing_list if str(o.get('order_id')) != str(order_id)]
                        existing_list.append(order_data)
                        payload = {'orders': existing_list, '_meta': {'updated_at': time.time()}}
                        r.set(orders_key, json.dumps(payload), ex=600)
                except Exception as redis_err:
                    logger.warning(f"[IBKR] Redis push failed: {redis_err}")
                
                return {'success': True, 'order_id': order_id, 'message': f"Order placed (ID: {order_id})"}
            else:
                return {'success': False, 'message': 'Place order failed (No Trade object)'}
                
        except Exception as e:
            logger.error(f"[place_order_isolated_sync] Error: {e}", exc_info=True)
            return {'success': False, 'message': str(e)}
    
    return conn.run_sync_on_ib_loop(_place_order_sync, timeout=10) or {'success': False, 'message': 'Timeout'}

def modify_order_isolated_sync(
    account_type: str,
    order_id: int,
    new_price: float,
    new_qty: Optional[float] = None
) -> Dict[str, Any]:
    """
    ATOMIC order modify for IBKR using ib_insync's native modify mechanism.
    
    In IBKR/TWS, calling placeOrder() with an existing orderId automatically
    modifies the order — no cancel needed, same order ID preserved.
    
    This finds the existing Trade object from openTrades(), updates only
    the price (and optionally qty), then re-submits via placeOrder().
    
    Args:
        account_type: 'IBKR_PED' or 'IBKR_GUN'
        order_id: The existing order's ID  
        new_price: New limit price
        new_qty: Optional new quantity (if None, keeps existing qty)
        
    Returns:
        {'success': True/False, 'message': '...'}
    """
    conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
    if not conn or not conn.connected:
        return {'success': False, 'message': f'IBKR connector not connected for {account_type}'}
    
    if not conn._ibkr_client:
        return {'success': False, 'message': 'No IBKR client available'}
    
    # LIFELESS MODE GUARD
    try:
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        if fabric and fabric.is_lifeless_mode():
            logger.info(f"🛡️ [SIMULATION - LIFELESS MODE] Would modify IBKR order {order_id} → ${new_price:.4f}")
            return {'success': True, 'message': '[SIMULATION] Order Modified'}
    except Exception:
        pass
    
    def _modify_order_sync():
        try:
            _ensure = conn._ensure_ib_insync()
            if not _ensure[0]:
                return {'success': False, 'message': 'ib_insync not available'}
            
            # Step 1: Find existing Trade by order_id from openTrades()
            trades = conn._ibkr_client.openTrades()
            target_trade = None
            for trade in trades:
                if trade.order.orderId == order_id:
                    target_trade = trade
                    break
            
            if not target_trade:
                logger.warning(f"[IBKR MODIFY] Order {order_id} not found in openTrades()")
                return {'success': False, 'message': f'Order {order_id} not found in open trades'}
            
            # Step 2: Modify the order's price (and optionally qty)
            old_price = target_trade.order.lmtPrice
            target_trade.order.lmtPrice = float(new_price)
            if new_qty is not None:
                target_trade.order.totalQuantity = float(new_qty)
            
            # Step 3: Re-submit via placeOrder — IBKR treats this as MODIFY (same orderId)
            modified_trade = conn._ibkr_client.placeOrder(
                target_trade.contract, 
                target_trade.order
            )
            
            if modified_trade:
                symbol = target_trade.contract.symbol
                logger.info(
                    f"[IBKR MODIFY] ✅ ATOMIC modify {symbol} order {order_id}: "
                    f"${old_price:.4f} → ${new_price:.4f} (same ID, no cancel gap)"
                )
                
                # Update Redis cache with new price
                try:
                    import json, time
                    from app.core.redis_client import get_redis_client
                    r = get_redis_client()
                    if r:
                        orders_key = f"psfalgo:open_orders:{account_type}"
                        raw = r.get(orders_key)
                        if raw:
                            s = raw.decode('utf-8') if isinstance(raw, bytes) else raw
                            cached_list = json.loads(s) if isinstance(s, str) else []
                            # Handle wrapped format
                            if isinstance(cached_list, dict) and 'orders' in cached_list:
                                inner_list = cached_list['orders']
                            elif isinstance(cached_list, list):
                                inner_list = cached_list
                            else:
                                inner_list = []
                            if isinstance(inner_list, list):
                                for o in inner_list:
                                    if str(o.get('order_id')) == str(order_id):
                                        o['price'] = float(new_price)
                                        o['timestamp'] = time.time()
                                        if new_qty is not None:
                                            o['quantity'] = float(new_qty)
                                        break
                                payload = {'orders': inner_list, '_meta': {'updated_at': time.time()}}
                                r.set(orders_key, json.dumps(payload), ex=600)
                except Exception as redis_err:
                    logger.warning(f"[IBKR MODIFY] Redis cache update failed: {redis_err}")
                
                return {
                    'success': True, 
                    'order_id': order_id,
                    'message': f'Order modified: ${old_price:.4f} → ${new_price:.4f}'
                }
            else:
                return {'success': False, 'message': 'placeOrder returned None'}
                
        except Exception as e:
            logger.error(f"[modify_order_isolated_sync] Error: {e}", exc_info=True)
            return {'success': False, 'message': str(e)}
    
    return conn.run_sync_on_ib_loop(_modify_order_sync, timeout=10) or {'success': False, 'message': 'Timeout'}


def initialize_ibkr_connectors():
    global _ibkr_gun_connector, _ibkr_ped_connector
    _ibkr_gun_connector = IBKRConnector(account_type="IBKR_GUN")
    _ibkr_ped_connector = IBKRConnector(account_type="IBKR_PED")
    logger.info("IBKR connectors initialized")

def connect_isolated_sync(
    account_type: str,
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    client_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Connect IBKR connector properly isolated in a worker thread.
    Use SelectorEventLoop to ensure compatibility with ib_insync on Windows.
    """
    # Check if already connected
    conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
    if conn and conn.is_connected():
        logger.info(f"[IBKR] Already connected {account_type}")
        set_active_ibkr_account(account_type)
        return {'success': True, 'connected': True, 'already_connected': True}

    # PHASE 11: Do NOT disconnect other account - support dual connections
    # Both IBKR_PED and IBKR_GUN can be connected simultaneously
    
    result_q: queue.Queue = queue.Queue()

    def _worker():
        loop = None
        try:
            # Step 1: Create a completely fresh event loop for this thread
            if sys.platform == 'win32':
                 loop = asyncio.SelectorEventLoop()
            else:
                 loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                import nest_asyncio
                nest_asyncio.apply(loop)
            except: pass
            
            # Step 2: AGGRESSIVE patching - must happen BEFORE importing ib_insync components
            # Patch at module level to ensure all subsequent imports use our loop
            original_get_running_loop = asyncio.get_running_loop
            original_get_event_loop = asyncio.get_event_loop
            
            def patched_get_running_loop():
                try:
                    return original_get_running_loop()
                except RuntimeError:
                    return loop
            
            def patched_get_event_loop():
                return loop
            
            asyncio.get_running_loop = patched_get_running_loop
            asyncio.get_event_loop = patched_get_event_loop
            
            # Step 3: Now import and create IB instance AFTER patches are in place
            conn = get_ibkr_connector(account_type=account_type)
            if not conn:
                result_q.put({"success": False, "error": "No connector"})
                return

            conn._ib_thread = threading.current_thread()
            conn._ib_loop = loop

            # Step 4: Do the connection directly here instead of calling conn.connect()
            # This ensures all IB operations happen with our loop
            async def _do_direct_connect():
                nonlocal conn
                try:
                    # CRITICAL: Import ib_insync FRESH inside this thread after loop is set
                    # This ensures all internal asyncio references use our loop
                    try:
                        # Clear any cached modules to force fresh import
                        import sys
                        mods_to_remove = [k for k in sys.modules.keys() if 'ib_insync' in k or 'ibapi' in k]
                        for mod in mods_to_remove:
                            del sys.modules[mod]
                        
                        from ib_insync import IB as LocalIB
                        logger.info("[IBKR_ISOLATED] Fresh ib_insync import successful")
                    except ImportError as e:
                        return {'success': False, 'error': f"ib_insync import failed: {e}"}
                    
                    # Create IB instance FRESH in this thread with this loop
                    ib = LocalIB()
                    
                    # Force all possible loop references to our loop
                    if hasattr(ib, 'loop'): ib.loop = loop
                    if hasattr(ib, '_loop'): ib._loop = loop
                    if hasattr(ib, 'client'):
                        if hasattr(ib.client, 'loop'): ib.client.loop = loop
                        if hasattr(ib.client, '_loop'): ib.client._loop = loop
                        if hasattr(ib.client, 'setLoop'): ib.client.setLoop(loop)
                    if hasattr(ib, 'wrapper'):
                        if hasattr(ib.wrapper, 'loop'): ib.wrapper.loop = loop
                        if hasattr(ib.wrapper, '_loop'): ib.wrapper._loop = loop
                    
                    # Determine client ID
                    cid = client_id
                    if cid is None:
                        cid = 12 if account_type == "IBKR_PED" else 11
                    
                    # Try connection
                    hosts_to_try = [host] if host not in ['127.0.0.1', 'localhost'] else ['127.0.0.1', 'localhost']
                    ports_to_try = [int(port)] if port else [4001, 7497, 7496, 4002]
                    
                    logger.info(f"[IBKR_ISOLATED] Attempting connection: hosts={hosts_to_try}, ports={ports_to_try}, clientId={cid}")
                    
                    connected = False
                    last_error = None
                    
                    for p in ports_to_try:
                        if connected: break
                        for h in hosts_to_try:
                            if connected: break
                            try:
                                logger.info(f"[IBKR_ISOLATED] Trying {h}:{p}...")
                                await ib.connectAsync(h, p, clientId=int(cid), timeout=10)
                                ib.reqMarketDataType(1)  # Live data
                                
                                # Store on connector
                                conn._ibkr_client = ib
                                conn._ib_loop = loop
                                conn._client_id = int(cid)
                                conn.connected = True
                                conn.connection_error = None
                                conn.gateway_port = p
                                
                                logger.info(f"[IBKR_ISOLATED] ✅ Connected to {account_type} at {h}:{p}")
                                
                                # Register fill recovery and start befday tracking
                                try:
                                    await conn._register_fill_recovery()
                                    asyncio.create_task(conn._auto_track_befday_task())
                                except Exception as e:
                                    logger.warning(f"[IBKR_ISOLATED] Post-connect setup warning: {e}")
                                
                                connected = True
                                return {'success': True, 'connected': True, 'account_type': account_type, 'host': h, 'port': p}
                                
                            except Exception as e:
                                last_error = str(e)
                                logger.warning(f"[IBKR_ISOLATED] Failed {h}:{p}: {e}")
                                try: ib.disconnect()
                                except: pass
                    
                    if not connected:
                        error_msg = f"All connection attempts failed. Last error: {last_error}"
                        conn.connected = False
                        conn.connection_error = error_msg
                        return {'success': False, 'error': error_msg}
                    
                except Exception as e:
                    logger.error(f"[IBKR_ISOLATED] Connection error: {e}", exc_info=True)
                    return {'success': False, 'error': str(e)}

            try:
                out = loop.run_until_complete(_do_direct_connect())
                if out and out.get('success'):
                    set_active_ibkr_account(account_type)
                    _clear_redis_open_orders_for_account(account_type)
                    # Sync TradingAccountContext connection flag
                    try:
                        from app.trading.trading_account_context import get_trading_context
                        ctx = get_trading_context()
                        if ctx:
                            if account_type == "IBKR_PED":
                                ctx.set_ibkr_ped_connected(True)
                            elif account_type == "IBKR_GUN":
                                ctx.set_ibkr_live_connected(True)
                            logger.info(f"[IBKR] ✅ TradingAccountContext synced: {account_type} connected=True")
                    except Exception as ctx_err:
                        logger.debug(f"[IBKR] TradingAccountContext sync warning: {ctx_err}")
                result_q.put(out)
            except Exception as e:
                 # Check if actually connected despite error
                if conn.is_connected():
                     set_active_ibkr_account(account_type)
                     result_q.put({'success': True, 'connected': True})
                else:
                     result_q.put({"success": False, "error": str(e)})

            loop.run_forever()
            
        except Exception as e:
            logger.error(f"[IBKR] Worker died: {e}")
            if result_q.empty(): result_q.put({"success": False, "error": str(e)})

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    
    try:
        res = result_q.get(timeout=17)
        return res
    except queue.Empty:
        conn = get_ibkr_connector(account_type=account_type, create_if_missing=False)
        if conn and conn.is_connected():
             set_active_ibkr_account(account_type)
             return {'success': True, 'connected': True, 'timeout_but_connected': True}
        return {'success': False, 'error': 'Timeout'}
