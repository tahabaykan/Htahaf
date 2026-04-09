"""
Position Snapshot API - Production-Grade

Provides async position snapshot API for PSFALGO decision engines.
Aggregates data from position manager, market data, and static data.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from app.core.logger import logger

# In-memory cache for position snapshot to avoid repeated IBKR/Redis hits when multiple endpoints poll (e.g. exposure, janall, positions).
# TTL seconds; concurrent requests within TTL share one snapshot.
_POSITION_SNAPSHOT_CACHE: Dict[str, Tuple[float, List[Any]]] = {}
_POSITION_SNAPSHOT_CACHE_TTL = 5

# BEFDAY exposure cache: /api/trading/exposure calls get_befday_exposure_snapshot every time (103 symbols + calculate_exposure).
_BEFDAY_EXPOSURE_CACHE: Dict[str, Tuple[float, Any]] = {}
_BEFDAY_EXPOSURE_CACHE_TTL = 10
from app.psfalgo.decision_models import PositionSnapshot, PositionPriceStatus, PositionTag
from app.market_data.grouping import resolve_primary_group, resolve_secondary_group
from app.market_data.static_data_store import StaticDataStore

@dataclass
class PositionSnapshotAPI:
    """
    Position Snapshot API - async, production-grade.
    
    Responsibilities:
    - Get position snapshots from position manager
    - Enrich with market data (current price, P&L)
    - Enrich with static data (group, cgrup)
    - Calculate holding time metrics
    - Format for decision engines
    """
    
    def __init__(
        self,
        position_manager=None,
        static_store: Optional[StaticDataStore] = None,
        market_data_cache: Optional[Dict[str, Dict[str, Any]]] = None
    ):
        """
        Initialize Position Snapshot API.
        
        Args:
            position_manager: PositionManager instance
            static_store: StaticDataStore instance
            market_data_cache: Market data cache {symbol: market_data}
        """
        self.position_manager = position_manager
        self.static_store = static_store
        self.market_data_cache = market_data_cache or {}
    
    async def get_position_snapshot(
        self,
        account_id: str = "HAMPRO",
        symbols: Optional[List[str]] = None,
        include_zero_positions: bool = False
    ) -> List[PositionSnapshot]:
        """
        Get position snapshot for symbols within STRICT ACCOUNT SCOPE.
        
        Args:
            account_id: Account ID (HAMPRO, IBKR_PED, IBKR_GUN). REQUIRED.
            symbols: List of symbols to get snapshots for. If None, gets all positions.
            include_zero_positions: Include positions with qty=0 (default: False)
            
        Returns:
            List of PositionSnapshot objects for the specified account.
        """
        try:
            # In-memory cache: avoid repeated IBKR/Redis when exposure, janall, positions poll within a few seconds
            cache_key = f"{account_id}:{include_zero_positions}" if symbols is None else None
            if cache_key:
                now = time.time()
                if cache_key in _POSITION_SNAPSHOT_CACHE:
                    expiry_ts, cached = _POSITION_SNAPSHOT_CACHE[cache_key]
                    if now < expiry_ts and cached:
                        logger.debug(f"[POSITION_SNAPSHOT] Cache hit for {account_id} ({len(cached)} positions)")
                        return list(cached)
            logger.info(f"[POSITION_SNAPSHOT] Fetching for Account: {account_id}")
            snapshots = []
            open_qty_map: Dict[str, float] = {}
            # Load Befday Map for Taxonomy
            befday_map = self._load_befday_map(account_id)
            logger.info(f"[POSITION_SNAPSHOT] Loaded {len(befday_map)} entries from Befday for {account_id}")

            # CASE A: IBKR Account
            if account_id in ["IBKR_PED", "IBKR_GUN"]:
                from app.psfalgo.ibkr_connector import get_ibkr_connector, get_active_ibkr_account, set_active_ibkr_account

                # CRITICAL FIX: First try Redis (fast, no timeout)
                # If Redis has data, use it. Only fetch from IBKR if Redis is empty or stale.
                try:
                    from app.core.redis_client import get_redis_client
                    import json
                    redis = get_redis_client()
                    if redis:
                        positions_key = f"psfalgo:positions:{account_id}"
                        raw_positions = redis.get(positions_key)
                        if raw_positions:
                            positions_dict = json.loads(raw_positions.decode() if isinstance(raw_positions, bytes) else raw_positions)
                            if positions_dict:
                                # ═══════════════════════════════════════════════════════════
                                # CRITICAL STALENESS CHECK: Detect phantom/stale positions
                                # If ALL positions have qty=0, Redis has only befday phantoms
                                # (no real IBKR data). Must fall through to IBKR fetch.
                                # Also check if data is too old (>5 min) and IBKR is connected.
                                # ═══════════════════════════════════════════════════════════
                                meta = positions_dict.get('_meta', {})
                                redis_updated_at = meta.get('updated_at', 0)
                                redis_age_seconds = time.time() - redis_updated_at if redis_updated_at else 999999
                                
                                # Check if all qty values are zero (phantom positions from befday)
                                non_meta_items = {k: v for k, v in positions_dict.items() if k != '_meta'}
                                all_qty_zero = all(
                                    float(v.get('qty', 0)) == 0
                                    for v in non_meta_items.values()
                                    if isinstance(v, dict)
                                ) if non_meta_items else True
                                
                                # Check if IBKR connector is available and connected
                                connector_for_check = get_ibkr_connector(account_type=account_id, create_if_missing=False)
                                ibkr_is_connected = connector_for_check and connector_for_check.is_connected()
                                
                                # Decide whether to bypass fast path
                                bypass_fast_path = False
                                
                                if all_qty_zero and ibkr_is_connected:
                                    logger.warning(
                                        f"[POSITION_SNAPSHOT] ⚠️ Redis fast path BYPASSED for {account_id}: "
                                        f"ALL {len(non_meta_items)} positions have qty=0 (phantom/stale from befday). "
                                        f"Falling through to IBKR fetch for real positions."
                                    )
                                    # Delete stale Redis key so next time we don't hit it again
                                    try:
                                        redis.delete(positions_key)
                                        logger.info(f"[POSITION_SNAPSHOT] 🗑️ Deleted stale Redis key {positions_key}")
                                    except Exception:
                                        pass
                                    bypass_fast_path = True
                                    
                                elif all_qty_zero and not ibkr_is_connected:
                                    logger.error(
                                        f"[POSITION_SNAPSHOT] ❌ IBKR NOT CONNECTED for {account_id} "
                                        f"and Redis has {len(non_meta_items)} phantom positions (all qty=0). "
                                        f"Exposure will show $0 until IBKR Gateway is connected. "
                                        f"Check IBKR Gateway/TWS is running on port 4001."
                                    )
                                    # DON'T fake data with befday_qty - show honest 0
                                    # Bypass fast path so it falls to IBKR fetch (which will also fail = empty)
                                    bypass_fast_path = True
                                    
                                elif redis_age_seconds > 300 and ibkr_is_connected:
                                    logger.warning(
                                        f"[POSITION_SNAPSHOT] ⚠️ Redis data is {redis_age_seconds:.0f}s old "
                                        f"and IBKR is connected for {account_id}. "
                                        f"Bypassing fast path for fresh IBKR fetch."
                                    )
                                    bypass_fast_path = True
                                
                                # Only proceed with fast path if we didn't decide to bypass
                                if not bypass_fast_path:
                                    # Convert dict to PositionSnapshot objects
                                    snapshots_from_redis = []
                                    befday_updated = False
                                    for sym, pos_data in positions_dict.items():
                                        if sym and sym != '_meta':
                                            # CRITICAL FIX: Use befday_map as authoritative source
                                            # DO NOT trust embedded befday_qty — it may be stale!
                                            if befday_map and sym in befday_map:
                                                correct_befday = float(befday_map[sym].get('quantity', 0))
                                            elif not befday_map:
                                                # befday_map is EMPTY → no captures today yet
                                                # Use CURRENT qty as BEFDAY to prevent phantom REV orders
                                                correct_befday = float(pos_data.get('qty', 0))
                                            else:
                                                correct_befday = 0.0  # Not in befday = new position today
                                            
                                            # Update the dict so Redis gets corrected too
                                            old_befday = pos_data.get('befday_qty', 0)
                                            if abs(float(old_befday or 0) - correct_befday) > 0.001:
                                                pos_data['befday_qty'] = correct_befday
                                                befday_updated = True
                                            
                                            # Derive taxonomy from befday_qty
                                            # OV = Overnight (was in BEFDAY), INT = Intraday (new today)
                                            _origin = pos_data.get('origin_type', 'OV' if abs(correct_befday) > 0.001 else 'INT')
                                            _strategy = pos_data.get('strategy_type', 'LT')
                                            _qty_val = pos_data.get('qty', 0)
                                            _side = 'Long' if _qty_val >= 0 else 'Short'
                                            _taxonomy = pos_data.get('full_taxonomy', f"{_strategy} {_origin} {_side}")
                                            
                                            snapshots_from_redis.append(PositionSnapshot(
                                                symbol=sym,
                                                qty=_qty_val,
                                                avg_price=pos_data.get('avg_price', 0.0),
                                                current_price=pos_data.get('current_price', 0.0),
                                                unrealized_pnl=pos_data.get('unrealized_pnl', 0.0),
                                                # CRITICAL: potential_qty defaults to qty (not stale Redis value)
                                                # Open orders correction at lines below will adjust this
                                                potential_qty=pos_data.get('potential_qty', None) or _qty_val,
                                                befday_qty=correct_befday,
                                                group=pos_data.get('group', None),
                                                cgrup=pos_data.get('cgrup', None),
                                                account_type=account_id,
                                                origin_type=_origin,
                                                strategy_type=_strategy,
                                                full_taxonomy=_taxonomy,
                                                # CRITICAL: display_qty must be set so frontend shows CURRENT correctly
                                                # Without this, display_qty=None → frontend renders null as 0
                                                display_qty=_qty_val,
                                                display_bucket=pos_data.get('display_bucket', 'LT'),
                                                view_mode=pos_data.get('view_mode', 'SINGLE_BUCKET'),
                                            ))
                                    
                                    if befday_updated:
                                        logger.info(f"[POSITION_SNAPSHOT] Updated stale befday_qty values from befday_map ({len(befday_map)} entries)")
                                    
                                    # CRITICAL: In fast path also load open orders from Redis so newly placed orders (and potential_qty) are correct
                                    #
                                    # ═══════════════════════════════════════════════════════════
                                    # CANCEL GRACE PERIOD GUARD: After reqGlobalCancel or
                                    # Hammer cancel_all, Redis open orders may still show stale
                                    # cancelled orders for up to ~5s. During the cancel grace
                                    # period (15s), we SKIP open order adjustments so that
                                    # potential_qty = qty (no phantom open orders).
                                    # This prevents engines from seeing wrong effective_qty
                                    # and calculating incorrect lot sizes.
                                    # ═══════════════════════════════════════════════════════════
                                    _cancel_grace_active = False
                                    try:
                                        from app.psfalgo.exposure_calculator import _is_cancel_grace_period_active
                                        _cancel_grace_active = _is_cancel_grace_period_active()
                                    except Exception:
                                        pass
                                    
                                    try:
                                        orders_key = f"psfalgo:open_orders:{account_id}"
                                        raw_orders = redis.get(orders_key)
                                        if _cancel_grace_active:
                                            # Grace period: treat all open orders as cancelled
                                            # potential_qty stays = qty (already set above)
                                            logger.info(
                                                f"[POSITION_SNAPSHOT] ⏳ Cancel grace period active — "
                                                f"skipping open orders for potential_qty (potential=qty)"
                                            )
                                        elif raw_orders:
                                            parsed_orders = json.loads(raw_orders.decode() if isinstance(raw_orders, bytes) else raw_orders)
                                            # Handle wrapped format vs legacy list
                                            if isinstance(parsed_orders, dict) and 'orders' in parsed_orders:
                                                open_orders = parsed_orders['orders']
                                            elif isinstance(parsed_orders, list):
                                                open_orders = parsed_orders
                                            else:
                                                open_orders = []
                                            if isinstance(open_orders, list) and open_orders:
                                                open_qty_map = {}
                                                for order in open_orders:
                                                    raw_sym = order.get('symbol')
                                                    sym_n = self.normalize_ibkr_symbol(raw_sym)
                                                    qty_o = order.get('totalQuantity', order.get('qty', 0))
                                                    action = order.get('action', 'BUY')
                                                    if action == 'SELL':
                                                        qty_o = -qty_o
                                                    if sym_n:
                                                        open_qty_map[sym_n] = open_qty_map.get(sym_n, 0.0) + qty_o
                                                from dataclasses import replace
                                                for i, sn in enumerate(snapshots_from_redis):
                                                    net_open = open_qty_map.get(sn.symbol, 0.0)
                                                    new_potential = sn.qty + net_open
                                                    if abs((sn.potential_qty or 0) - new_potential) > 0.001:
                                                        snapshots_from_redis[i] = replace(sn, potential_qty=new_potential)
                                                logger.debug(f"[POSITION_SNAPSHOT] Fast path: applied {len(open_orders)} open orders to potential_qty")
                                    except Exception as oe:
                                        logger.debug(f"[POSITION_SNAPSHOT] Fast path open orders read: {oe}")
                                    
                                    # CRITICAL: Enrich with live L1 prices from market data cache
                                    # Redis may store stale/zero prices; always refresh from L1 feed
                                    from dataclasses import replace as dc_replace
                                    enriched_count = 0
                                    for i, sn in enumerate(snapshots_from_redis):
                                        live_price = self._get_current_price(sn.symbol)
                                        if live_price and live_price > 0:
                                            updates = {"current_price": live_price}
                                            # Recalc unrealized P&L if avg_price available
                                            if sn.avg_price and sn.avg_price > 0:
                                                updates["unrealized_pnl"] = (live_price - sn.avg_price) * sn.qty
                                            snapshots_from_redis[i] = dc_replace(sn, **updates)
                                            enriched_count += 1
                                    if enriched_count > 0:
                                        logger.debug(f"[POSITION_SNAPSHOT] Fast path: enriched {enriched_count}/{len(snapshots_from_redis)} positions with L1 prices")
                                    
                                    logger.info(f"[POSITION_SNAPSHOT] ✅ Using {len(snapshots_from_redis)} positions from Redis (fast path, no IBKR timeout)")
                                    # Write CORRECTED positions_dict back to Redis (with updated befday_qty)
                                    positions_dict['_meta'] = {'updated_at': time.time()}
                                    redis.set(positions_key, json.dumps(positions_dict), ex=3600)  # 1 hour TTL
                                    if cache_key:
                                        _POSITION_SNAPSHOT_CACHE[cache_key] = (time.time() + _POSITION_SNAPSHOT_CACHE_TTL, snapshots_from_redis)
                                    return snapshots_from_redis
                except Exception as redis_err:
                    logger.warning(f"[POSITION_SNAPSHOT] Redis read failed: {redis_err}", exc_info=True)
                
                # Fallback: Fetch from IBKR (Redis empty, stale/phantom data, or bypassed)
                connector = get_ibkr_connector(account_type=account_id, create_if_missing=False)
                if not connector or not connector.is_connected():
                    # CRITICAL FIX: Return in-memory cache instead of empty list
                    # This prevents "Loading..." in UI when IBKR Gateway is down
                    if cache_key and cache_key in _POSITION_SNAPSHOT_CACHE:
                        expiry_ts, cached = _POSITION_SNAPSHOT_CACHE[cache_key]
                        if cached:
                            logger.warning(f"[POSITION_SNAPSHOT] IBKR not connected for {account_id} — returning {len(cached)} cached positions (stale)")
                            return list(cached)
                    logger.warning(f"[POSITION_SNAPSHOT] No connector for {account_id}, no Redis, no cache - returning empty")
                    return []
                
                # CRITICAL FIX: If connector is connected but active_account is None, set it!
                active_account = get_active_ibkr_account()
                if connector.is_connected() and active_account != account_id:
                    if active_account is None:
                        logger.warning(f"[POSITION_SNAPSHOT] Connector is connected but active_account is None! Setting active account to {account_id}")
                        set_active_ibkr_account(account_id)
                        active_account = get_active_ibkr_account()
                        logger.info(f"[POSITION_SNAPSHOT] Active account after fix: {active_account}")
                    else:
                        logger.warning(f"[POSITION_SNAPSHOT] Skipping IBKR fetch: {account_id} is not active (active={active_account})")
                        return []
                
                # CRITICAL: Only fetch from IBKR if this is the ACTIVE account
                if active_account != account_id:
                    logger.warning(f"[POSITION_SNAPSHOT] Skipping IBKR fetch: {account_id} is not active (active={active_account})")
                    return []
                
                # CRITICAL: Use isolated sync for positions to avoid "Event loop is closed" in request context
                # Open orders fetched separately via _get_ibkr_open_orders_isolated (also isolated)
                ibkr_positions = []
                if connector and connector.is_connected():
                    try:
                        from app.psfalgo.ibkr_connector import get_positions_isolated_sync
                        loop = asyncio.get_running_loop()
                        ibkr_positions = await asyncio.wait_for(
                            loop.run_in_executor(None, lambda: get_positions_isolated_sync(account_id)),
                            timeout=12.0
                        )
                        if not isinstance(ibkr_positions, list):
                            ibkr_positions = []
                    except asyncio.TimeoutError:
                        logger.warning(f"[POSITION_SNAPSHOT] IBKR positions timeout (12s) - Gateway slow")
                        ibkr_positions = []
                    except Exception as e:
                        logger.warning(f"[POSITION_SNAPSHOT] IBKR positions error: {e}")
                        ibkr_positions = []
                    
                    # CRITICAL: Try to read open orders from Redis first (fast, no timeout)
                    # Only fetch from IBKR if Redis is empty (lazy loading)
                    try:
                        from app.core.redis_client import get_redis_client
                        import json
                        redis = get_redis_client()
                        if redis:
                            orders_key = f"psfalgo:open_orders:{account_id}"
                            raw_orders = redis.get(orders_key)
                            if raw_orders:
                                parsed_orders = json.loads(raw_orders.decode() if isinstance(raw_orders, bytes) else raw_orders)
                                # Handle wrapped format vs legacy list
                                if isinstance(parsed_orders, dict) and 'orders' in parsed_orders:
                                    open_orders = parsed_orders['orders']
                                elif isinstance(parsed_orders, list):
                                    open_orders = parsed_orders
                                else:
                                    open_orders = []
                                # Process open orders from Redis
                                if isinstance(open_orders, list):
                                    for order in open_orders:
                                        raw_sym = order.get('symbol')
                                        sym = self.normalize_ibkr_symbol(raw_sym)
                                        qty = order.get('totalQuantity', order.get('qty', 0))
                                        action = order.get('action', 'BUY')
                                        if action == 'SELL':
                                            qty = -qty
                                        if sym:
                                            open_qty_map[sym] = open_qty_map.get(sym, 0.0) + qty
                                logger.debug(f"[POSITION_SNAPSHOT] ✅ Read {len(open_orders) if isinstance(open_orders, list) else 0} open orders from Redis (fast)")
                            else:
                                # Redis empty - fetch from IBKR (but with timeout protection)
                                try:
                                    open_orders = await asyncio.wait_for(
                                        self._get_ibkr_open_orders_isolated(account_id),
                                        timeout=5.0  # Short timeout
                                    )
                                    if isinstance(open_orders, list):
                                        # Process and write to Redis
                                        for order in open_orders:
                                            raw_sym = order.get('symbol')
                                            sym = self.normalize_ibkr_symbol(raw_sym)
                                            qty = order.get('totalQuantity', order.get('qty', 0))
                                            action = order.get('action', 'BUY')
                                            if action == 'SELL':
                                                qty = -qty
                                            if sym:
                                                open_qty_map[sym] = open_qty_map.get(sym, 0.0) + qty
                                        # Write to Redis for next time (10 min TTL — orders are volatile)
                                        orders_payload = {'orders': open_orders, '_meta': {'updated_at': time.time()}}
                                        redis.set(orders_key, json.dumps(orders_payload), ex=600)  # 10 min TTL
                                        logger.info(f"[POSITION_SNAPSHOT] ✅ Fetched and wrote {len(open_orders)} open orders to Redis")
                                except asyncio.TimeoutError:
                                    logger.debug(f"[POSITION_SNAPSHOT] Open orders timeout (5s) - using empty (will retry later)")
                                    open_orders = []
                                except Exception as oe:
                                    logger.debug(f"[POSITION_SNAPSHOT] Open orders fetch error: {oe}")
                                    open_orders = []
                    except Exception as oe:
                        logger.debug(f"[POSITION_SNAPSHOT] Open orders Redis read/write failed: {oe}")

                logger.info(f"[POSITION_SNAPSHOT] {account_id}: fetched {len(ibkr_positions)} positions")
                logger.debug(f"[POTENTIAL_DEBUG] Open Orders Map: {open_qty_map}")
                
                # Combine Broker Positions with Befday Symbols (Union)
                # This ensures we return snapshots for everything in our plan, even if flat in Broker
                
                # Map broker positions by symbol for easy lookup
                broker_pos_map = {p.get('symbol'): p for p in ibkr_positions}
                
                # Create Union of symbols
                all_symbols = set(broker_pos_map.keys()) | set(befday_map.keys())
                # If specific symbols requested: include them so we return at least phantom snapshots (e.g. fill for AAPL when account has no AAPL)
                if symbols:
                    requested_set = set(symbols)
                    all_symbols = (all_symbols & requested_set) | requested_set

                # CRITICAL: If befday_map is empty (no Redis, no CSV for today),
                # then CURRENT = BEFDAY (user hasn't captured yet, or broker wasn't ready).
                # Without this guard, ALL positions get befday_qty=0, causing RevRecovery
                # to see every position as "Health Broken" and issue phantom REV orders.
                # (Same guard already exists for HAMPRO at line ~399)
                befday_is_empty = len(befday_map) == 0
                if befday_is_empty:
                    logger.warning(f"[POSITION_SNAPSHOT] ⚡ IBKR befday_map is EMPTY for {account_id} → using CURRENT as BEFDAY (no captures today yet)")

                logger.info(f"[POSITION_SNAPSHOT] processing {len(all_symbols)} total symbols (Union of Broker & Befday)")

                for sym in all_symbols:
                    # Get Broker Data or Default (Phantom Position)
                    pos_data = broker_pos_map.get(sym)
                    if not pos_data:
                        # Phantom Position (Exists in Plan, Flat in Broker)
                        pos_data = {
                            'symbol': sym,
                            'qty': 0.0,
                            'avg_price': 0.0,
                            'account': account_id
                        }
                    
                    net_open = open_qty_map.get(sym, 0.0)
                    
                    # Resolve Befday Qty (Try raw symbol and normalized)
                    if befday_is_empty:
                        # No BEFDAY data exists → CURRENT = BEFDAY (prevent phantom REV orders)
                        current_qty = float(pos_data.get('qty', 0))
                        bef_qty = current_qty
                        bef_data = {'quantity': current_qty, 'strategy': 'LT', 'origin': 'OV', 'side': 'Long' if current_qty >= 0 else 'Short'}
                    else:
                        bef_data = befday_map.get(sym, {})
                        bef_qty = bef_data.get('quantity', 0.0)
                    
                    if sym == 'HOVNP' or sym == 'WRB PRF':
                         logger.debug(f"[BEFDAY_DEBUG] Checking {sym}: Found={bool(bef_data)}, Qty={bef_qty}, MapSize={len(befday_map)}")
                    
                    snapshot = await self._enrich_position(pos_data, sym, account_id, net_open_qty=net_open, befday_qty=bef_qty, befday_data=bef_data)
                    if snapshot:
                        # If include_zero_positions is False, we typically skip 0 qty.
                        # BUT for RevnBookCheck, we need them if they have Befday data!
                        # So we modify the check: Skip ONLY if qty=0 AND befday_qty=0
                        
                        is_flat = abs(snapshot.qty) < 0.01
                        has_befday = abs(snapshot.befday_qty) > 0.01
                        
                        if not include_zero_positions:
                             # strict filtering: if flat and NO befday -> skip
                             # if flat but HAS befday -> KEEP (it's a target)
                             if is_flat and not has_befday:
                                  continue
                        
                        snapshots.append(snapshot)
            
            # CASE B: Hammer Account (HAMPRO)
            elif account_id in ["HAMPRO", "HAMMER_PRO"]:
                # Fetch Open Orders via HammerOrdersService
                try:
                    from app.api.trading_routes import get_hammer_orders_service
                    orders_service = get_hammer_orders_service()
                    if orders_service:
                         # Use list_orders or get_orders depending on API
                         all_orders = orders_service.get_orders(force_refresh=False)
                         for order in all_orders:
                             if order.get('status') in ['OPEN', 'PENDING', 'PARTIAL']:
                                 sym = order.get('symbol')
                                 qty = order.get('quantity', 0) - order.get('filled_quantity', 0)
                                 side = order.get('side', 'BUY')
                                 if side == 'SELL':
                                     qty = -qty
                                 if sym:
                                     open_qty_map[sym] = open_qty_map.get(sym, 0.0) + qty
                except Exception as oe:
                    logger.warning(f"Error fetching Hammer open orders: {oe}")

                if self.position_manager:
                    hammer_positions = self._get_positions_from_manager(symbols)
                    logger.info(f"[POSITION_SNAPSHOT] HAMPRO: fetched {len(hammer_positions)} positions")
                    
                    # CRITICAL: Write Hammer open orders to Redis for terminals
                    try:
                        from app.core.redis_client import get_redis_client
                        import json
                        redis = get_redis_client()
                        if redis:
                            # Get all open orders from Hammer
                            from app.api.trading_routes import get_hammer_orders_service
                            orders_service = get_hammer_orders_service()
                            if orders_service:
                                all_orders = orders_service.get_orders(force_refresh=False)
                                open_orders_list = [o for o in all_orders if o.get('status') in ['OPEN', 'PENDING', 'PARTIAL']]
                                orders_key = f"psfalgo:open_orders:{account_id}"
                                orders_payload = {'orders': open_orders_list, '_meta': {'updated_at': time.time()}}
                                redis.set(orders_key, json.dumps(orders_payload), ex=600)  # 10 min TTL (orders are volatile)
                                logger.info(f"[POSITION_SNAPSHOT] ✅ Wrote {len(open_orders_list)} Hammer open orders to Redis {orders_key}")
                    except Exception as oe:
                        logger.warning(f"[POSITION_SNAPSHOT] Redis write Hammer open orders failed: {oe}")
                    
                    # CRITICAL: If befday_map is empty (no CSV, no Redis), 
                    # then CURRENT = BEFDAY (user hasn't traded today, first click)
                    befday_is_empty = len(befday_map) == 0
                    if befday_is_empty:
                        logger.info("[POSITION_SNAPSHOT] ⚡ befday_map is EMPTY → using CURRENT as BEFDAY (no trades today)")
                    
                    for pos_data in hammer_positions:
                         sym = pos_data.get('symbol')
                         net_open = open_qty_map.get(sym, 0.0)
                         # Resolve Befday Qty
                         if befday_is_empty:
                             # No BEFDAY data exists → CURRENT = BEFDAY
                             current_qty = float(pos_data.get('qty', 0))
                             bef_qty = current_qty
                             # Determine strategy from Internal Ledger (not hardcode LT)
                             _bef_strategy = 'LT'
                             try:
                                 from app.psfalgo.internal_ledger_store import get_internal_ledger_store
                                 _ledger = get_internal_ledger_store()
                                 if _ledger and sym and _ledger.has_symbol(account_id, sym):
                                     _lt = _ledger.get_lt_quantity(account_id, sym)
                                     _mm = current_qty - _lt
                                     if abs(_mm) > abs(_lt) and abs(_mm) > 0.01:
                                         _bef_strategy = 'MM'
                             except Exception:
                                 pass
                             bef_data = {'quantity': current_qty, 'strategy': _bef_strategy, 'origin': 'OV', 'side': 'Long' if current_qty >= 0 else 'Short'}
                         else:
                             bef_data = befday_map.get(sym, {})
                             bef_qty = bef_data.get('quantity', 0.0)
                         
                         snapshot = await self._enrich_position(pos_data, sym, account_id, net_open_qty=net_open, befday_qty=bef_qty, befday_data=bef_data)
                         if snapshot:
                             if not include_zero_positions and abs(snapshot.qty) < 0.01:
                                 continue
                             snapshots.append(snapshot)
            
            else:
                logger.error(f"[POSITION_SNAPSHOT] Unknown account_id: {account_id}")
                return []
            
            # CRITICAL: Write positions to Redis so RevnBookCheck / recovery can read (key: psfalgo:positions:{account_id})
            # This is the SINGLE SOURCE OF TRUTH for terminals
            try:
                from app.core.redis_client import get_redis_client
                import json
                redis = get_redis_client()
                if redis and snapshots:
                    positions_dict = {
                        getattr(s, "symbol", ""): {
                            "symbol": getattr(s, "symbol", ""),
                            "qty": getattr(s, "qty", 0),
                            "potential_qty": getattr(s, "potential_qty", 0),
                            "befday_qty": getattr(s, "befday_qty", 0),
                            "avg_price": getattr(s, "avg_price", 0.0),
                            "current_price": getattr(s, "current_price", 0.0),
                            "unrealized_pnl": getattr(s, "unrealized_pnl", 0.0),
                            "group": getattr(s, "group", None),
                            "cgrup": getattr(s, "cgrup", None),
                            "strategy_type": getattr(s, "strategy_type", "LT"),  # LT or MM
                            "origin_type": getattr(s, "origin_type", "OV"),
                            "full_taxonomy": getattr(s, "full_taxonomy", ""),
                            "display_qty": getattr(s, "display_qty", None) or getattr(s, "qty", 0),
                            "display_bucket": getattr(s, "display_bucket", "LT"),
                            "view_mode": getattr(s, "view_mode", "SINGLE_BUCKET"),
                        }
                        for s in snapshots
                        if getattr(s, "symbol", "")
                    }
                    positions_dict['_meta'] = {'updated_at': time.time()}
                    key = f"psfalgo:positions:{account_id}"
                    redis.set(key, json.dumps(positions_dict), ex=3600)  # 1 hour TTL
                    logger.info(f"[POSITION_SNAPSHOT] ✅ Wrote {len(positions_dict)} positions to Redis {key} (BEFDAY/CURRENT/POTENTIAL)")
                    
                    # NOTE: BEFDAY is ONLY written by the user button click (befday_routes.py / psfalgo_routes.py).
                    # This periodic snapshot refresh must NEVER write to psfalgo:befday:positions:*
                    # because befday_qty here may be stale/0 and would corrupt the real BEFDAY data.
            except Exception as re:
                logger.warning(f"[POSITION_SNAPSHOT] Redis write positions failed: {re}")
            if cache_key and snapshots:
                _POSITION_SNAPSHOT_CACHE[cache_key] = (time.time() + _POSITION_SNAPSHOT_CACHE_TTL, snapshots)
            logger.debug(f"[POSITION_SNAPSHOT] Returned {len(snapshots)} positions for {account_id}")
            return snapshots
            
        except Exception as e:
            logger.error(f"Error getting position snapshot: {e}", exc_info=True)
            return []

    async def _get_ibkr_open_orders_isolated(self, account_id: str) -> List[Dict[str, Any]]:
        """Fetch IBKR open orders via shared isolated helper to avoid 'event loop is already running' when called from FastAPI."""
        try:
            from app.psfalgo.ibkr_connector import get_open_orders_isolated_sync
            loop = asyncio.get_running_loop()
            # Use executor with increased timeout handling
            return await loop.run_in_executor(None, lambda: get_open_orders_isolated_sync(account_id))
        except Exception as e:
            logger.warning(f"[POSITION_SNAPSHOT] IBKR open orders executor error: {e} (type={type(e).__name__})")
            return []
    
    def _get_positions_from_manager(self, symbols: Optional[List[str]]) -> List[Dict[str, Any]]:
        """
        Get positions from Hammer Position Manager.
        """
        # Adapter for HammerPositionsService (get_positions method)
        if hasattr(self.position_manager, 'get_positions'):
            try:
                raw_positions = self.position_manager.get_positions(force_refresh=False)
                
                positions = []
                for pos in raw_positions:
                    symbol = pos.get('symbol')
                    # Filter by symbols if provided
                    if symbols and symbol not in symbols:
                        continue
                    
                    positions.append({
                        'symbol': symbol,
                        'qty': pos.get('quantity', 0.0),
                        'avg_price': pos.get('avg_price', 0.0),
                        'realized_pnl': 0.0,
                        'unrealized_pnl': pos.get('unrealized_pnl', 0.0),
                        'last_update_time': datetime.now().timestamp()
                    })
                return positions
            except Exception as e:
                logger.error(f"Error getting positions from service: {e}")
                return []

        # Adapter for Legacy Position Manager (dict access)
        if hasattr(self.position_manager, 'positions'):
            positions = []
            for symbol, pos_data in self.position_manager.positions.items():
                if symbols and symbol not in symbols:
                    continue
                
                position_dict = {
                    'symbol': symbol,
                    'qty': pos_data.get('qty', 0.0),
                    'avg_price': pos_data.get('avg_price', 0.0),
                    'realized_pnl': pos_data.get('realized_pnl', 0.0),
                    'unrealized_pnl': pos_data.get('unrealized_pnl', 0.0),
                    'last_update_time': pos_data.get('last_update_time', 0.0)
                }
                positions.append(position_dict)
            return positions
        
        return []

    async def _get_ibkr_positions(
        self, 
        symbols: Optional[List[str]],
        target_account_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get positions from specific IBKR account.
        """
        try:
            from app.psfalgo.ibkr_connector import get_ibkr_connector
            
            # Strict mode: Only check one target account provided by caller
            if not target_account_type:
                 return []

            connector = get_ibkr_connector(account_type=target_account_type)
            
            if connector and connector.is_connected():
                positions = await connector.get_positions()
                result_positions = []
                
                for pos in positions:
                    symbol = pos.get('symbol')
                    if symbols and symbol not in symbols:
                        continue
                    
                    result_positions.append(pos)
                return result_positions
            else:
                return []
            
        except Exception as e:
            logger.error(f"Error getting IBKR positions: {e}", exc_info=True)
            return []
    
    async def _enrich_position(
        self,
        pos_data: Dict[str, Any],
        symbol: str,
        account_id: str,
        net_open_qty: float = 0.0,
        befday_qty: float = 0.0,
        befday_data: Optional[Dict[str, Any]] = None
    ) -> Optional[PositionSnapshot]:
        """
        Enrich position data with market data (Price Status Handling).
        """
        try:
            qty = pos_data.get('qty', 0.0)
            avg_price = pos_data.get('avg_price', 0.0)
            last_update_time = pos_data.get('last_update_time', 0.0)
            
            # Taxonomy Determination (Phase 9)
            if befday_data and befday_data.get('full_taxonomy'):
                strategy_type = befday_data.get('strategy', 'LT')
                origin_type = befday_data.get('origin', 'OV')
                full_taxonomy = befday_data.get('full_taxonomy')
            else:
                strategy_type, origin_type, full_taxonomy = self._determine_taxonomy(qty, befday_qty, symbol=symbol, account_id=account_id)
            
            # Symbol Normalization
            normalized_symbol = self.normalize_ibkr_symbol(symbol)
            
            # Get current market price (ALWAYS from HAMMER using NORMALIZED symbol)
            current_price = self._get_current_price(normalized_symbol)
            
            # Fallback to original symbol logic
            if current_price is None:
                current_price = self._get_current_price(symbol)
            
            # PRICE STATUS LOGIC
            price_status = PositionPriceStatus.OK
            
            if current_price is None or current_price <= 0:
                # Missing price behavior: MARK as NO_PRICE but return snapshot (qty visible)
                current_price = 0.0
                price_status = PositionPriceStatus.NO_PRICE
            
            # Calculate unrealized P&L
            unrealized_pnl = (current_price - avg_price) * qty if avg_price > 0 else 0.0
            
            # Get group/cgrup from static data
            group, cgrup = self._get_group_info(symbol)
            
            # Calculate holding time metrics
            position_open_ts, holding_minutes = self._calculate_holding_time(last_update_time)
            
            # PHASE 8: LT/MM Split & Netting Logic
            # -------------------------------------------------------------
            from app.psfalgo.internal_ledger_store import get_internal_ledger_store, initialize_internal_ledger_store
            ledger = get_internal_ledger_store()
            if not ledger:
                initialize_internal_ledger_store()
                ledger = get_internal_ledger_store()
            
            # Determine Base LT from Befday (Default Assumption)
            # Strategy Type determined in Phase 9 above
            bef_lt_base = 0.0
            if strategy_type == "LT":
                 bef_lt_base = befday_qty
            
            lt_qty_raw = 0.0
            if ledger:
                 if ledger.has_symbol(account_id, symbol):
                      lt_qty_raw = ledger.get_lt_quantity(account_id, symbol)
                 else:
                      lt_qty_raw = bef_lt_base
            else:
                 lt_qty_raw = bef_lt_base
            
            mm_qty_raw = qty - lt_qty_raw
            
            # Determine Display Bucket & View Mode
            display_qty = qty
            display_bucket = "MM" # Default assumption
            view_mode = "SINGLE_BUCKET"
            
            # Logic implementation of Phase 8.2 Rules
            is_lt_zero = abs(lt_qty_raw) < 0.0001
            is_mm_zero = abs(mm_qty_raw) < 0.0001
            
            if is_lt_zero and is_mm_zero:
                display_bucket = "FLAT"
            elif is_lt_zero:
                display_bucket = "MM"
                view_mode = "SINGLE_BUCKET"
            elif is_mm_zero:
                display_bucket = "LT"
                view_mode = "SINGLE_BUCKET"
            else:
                # Both exist - check direction
                same_sign = (lt_qty_raw > 0 and mm_qty_raw > 0) or (lt_qty_raw < 0 and mm_qty_raw < 0)
                
                if same_sign:
                    # SAME Sign -> SPLIT (MIXED)
                    display_bucket = "MIXED"
                    view_mode = "SPLIT_SAME_DIR"
                else:
                    # OPPOSITE Sign -> NET (Dominant Bucket)
                    view_mode = "NETTED_OPPOSITE"
                    # Determine dominant bucket by absolute size
                    if abs(lt_qty_raw) >= abs(mm_qty_raw):
                        display_bucket = "LT"
                    else:
                        display_bucket = "MM"

            # Get Previous Close for Intraday PnL
            prev_close = self._get_prev_close(normalized_symbol)
            if prev_close <= 0:
                 prev_close = self._get_prev_close(symbol)
                 
            # Intraday Calculations
            intraday_pnl = 0.0
            intraday_cost = 0.0
            
            if current_price and current_price > 0 and prev_close and prev_close > 0:
                # User heuristic: "Last - PrevClose * Qty" (Simple View)
                intraday_cost = prev_close 
                intraday_pnl = (current_price - prev_close) * qty
            
            # PRICE STATUS LOGIC
            price_status = "OK" 
            
            if current_price is None or current_price <= 0:
                price_status = "NO_PRICE"
            
            # Phase 10: Position Tags (OV/INT Breakdown)
            # -------------------------------------------------------------
            position_tags = self._calculate_position_tags(
                account_id=account_id,
                symbol=symbol,
                befday_qty=befday_qty,
                current_qty=qty,
                befday_data=befday_data
            )
            
            # Determine Dominant Tag for Display (User Requirement: "Cogunluk etkisi")
            # Scan position_tags for largest absolute qty
            dominant_tag = None
            max_tag_qty = -1.0
            
            for tag, t_qty in position_tags.items():
                 if t_qty > max_tag_qty:
                      max_tag_qty = t_qty
                      dominant_tag = tag
            
            # If we found a dominant tag, update taxonomy fields
            if dominant_tag:
                 # format: "BOOK_SIDE_ORIGIN" (e.g. "LT_LONG_OV")
                 parts = dominant_tag.split('_')
                 if len(parts) >= 3:
                      # Update Strategy and Origin based on Dominant
                      strategy_type = parts[0] # LT or MM
                      origin_type = parts[2]   # OV or INT
                      side_str = "Long" if "LONG" in parts[1] else "Short"
                      
                      # Full Taxonomy for Main Display (e.g. "LT OV Long")
                      full_taxonomy = f"{strategy_type} {origin_type} {side_str}"
            
            # Create PositionSnapshot
            snapshot = PositionSnapshot(
                symbol=symbol,
                qty=qty,
                avg_price=avg_price,
                current_price=current_price or 0.0,
                unrealized_pnl=unrealized_pnl,
                group=group,
                cgrup=cgrup,
                account_type=account_id,
                position_open_ts=last_update_time,
                holding_minutes=0.0, 
                price_status=price_status,
                
                # Phase 8 Fields
                lt_qty_raw=lt_qty_raw,
                mm_qty_raw=mm_qty_raw,
                display_qty=qty, 
                display_bucket="MM", 
                view_mode="SINGLE_BUCKET",
                
                # Phase 9: 8-Type Taxonomy (Strict Classification)
                strategy_type=strategy_type,
                origin_type=origin_type,
                full_taxonomy=full_taxonomy,
                befday_qty=befday_qty,
                
                # Phase 10: Position Tags
                position_tags=position_tags,
                
                # Intraday P&L
                prev_close=prev_close,
                intraday_cost=intraday_cost,
                intraday_pnl=intraday_pnl,
                
                potential_qty=qty + net_open_qty,
                timestamp=datetime.now()
            )
            
            # ── Inject TSS/RTS from TruthShiftEngine ──
            try:
                from app.terminals.truth_shift_engine import get_truth_shift_engine
                ts_engine = get_truth_shift_engine()
                ts_data = ts_engine.get_symbol_tss(symbol)
                if ts_data:
                    windows = ts_data.get('windows', {})
                    w5 = windows.get('TSS_5M', {})
                    w15 = windows.get('TSS_15M', {})
                    w1h = windows.get('TSS_1H', {})
                    snapshot.tss_5m = w5.get('score') if w5.get('valid') else None
                    snapshot.tss_15m = w15.get('score') if w15.get('valid') else None
                    snapshot.tss_1h = w1h.get('score') if w1h.get('valid') else None
                    rts = ts_data.get('rts', {})
                    snapshot.rts_15m = rts.get('TSS_15M')
                    snapshot.truth_shift_group = ts_data.get('group')
            except Exception:
                pass  # TSS not available yet — non-critical
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Error enriching position {symbol}: {e}", exc_info=True)
            return None

    def _load_befday_map(self, account_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Load Befday Map (Redis First, CSV Fallback).
        Returns map: Symbol -> {
            'quantity': float,
            'full_taxonomy': str,
            'strategy': str,
            'origin': str,
            'side': str
        }
        """
        result = {}
        
        # 1. Try Redis (Priority) — account-scoped key for 3-account isolation
        # ═══════════════════════════════════════════════════════════════
        # CRITICAL: Also validate companion date key to ensure data is from TODAY.
        # Stale Redis data (from yesterday) must NOT be used as today's BEFDAY.
        # ═══════════════════════════════════════════════════════════════
        try:
            from app.core.redis_client import get_redis_client
            from datetime import datetime as _dt_check
            redis = get_redis_client()
            if redis:
                key = f"psfalgo:befday:positions:{account_id}"
                date_key = f"psfalgo:befday:date:{account_id}"
                data = redis.get(key)
                if data:
                    # Validate date key matches TODAY
                    stored_date = redis.get(date_key)
                    stored_date_str = stored_date.decode() if isinstance(stored_date, bytes) else stored_date if stored_date else None
                    today_str = _dt_check.now().strftime("%Y%m%d")
                    
                    if stored_date_str != today_str:
                        # STALE DATA — delete and fall through to CSV/empty
                        redis.delete(key)
                        redis.delete(date_key)
                        logger.warning(f"[_load_befday_map] 🗑️ Redis BEFDAY STALE for {account_id}: "
                                       f"stored_date={stored_date_str}, today={today_str} — deleted, falling through")
                    else:
                        import json
                        befday_list = json.loads(data)
                        logger.info(f"[_load_befday_map] ✅ Loaded {len(befday_list)} entries from Redis (date={stored_date_str})")
                        
                        for item in befday_list:
                            sym = str(item.get('symbol')).strip()
                            qty = float(item.get('qty', 0))
                            side = str(item.get('side', '')).strip().lower()
                            full_tax = str(item.get('full_taxonomy', '')).upper()
                            # BEFDAY: short must always be negative. Stale Redis may have positive short qty.
                            if qty > 0 and (side == 'short' or 'SHORT' in full_tax):
                                qty = -qty
                            avg_cost = item.get('avg_cost')
                            if avg_cost is not None:
                                try:
                                    avg_cost = float(avg_cost)
                                except (TypeError, ValueError):
                                    avg_cost = None
                            result[sym] = {
                                'quantity': qty,
                                'full_taxonomy': item.get('full_taxonomy', ''),
                                'strategy': item.get('strategy', 'LT'),
                                'origin': item.get('origin', 'OV'),
                                'side': item.get('side', ''),
                                'avg_cost': avg_cost
                            }
                        return result
        except Exception as re:
            logger.warning(f"[_load_befday_map] Redis load failed: {re}. Falling back to CSV.")

        # 2. Fallback to CSV
        import pandas as pd
        from pathlib import Path
        import os
        from datetime import datetime as _dt_csv, date as _date_csv
        
        # Determine filename
        filename = "befday.csv"
        # Map account to filename logic (align with befday_tracker)
        acc_up = account_id.upper()
        if acc_up == "IBKR_PED": 
             filename = "befibped.csv"
        elif acc_up == "IBKR_GUN":
             filename = "befibgun.csv"
        elif acc_up == "HAMPRO":
             filename = "befham.csv"
             
        # FIXED: Always try C:/StockTracker FIRST (this is where befday_routes saves canonical CSV)
        # CRITICAL: Also check modification date — stale CSV from yesterday must NOT be used
        csv_path = Path("C:/StockTracker") / filename
        if csv_path.exists():
            file_date = _dt_csv.fromtimestamp(os.path.getmtime(csv_path)).date()
            if file_date != _date_csv.today():
                logger.warning(f"[_load_befday_map] ⚠️ Canonical CSV {csv_path} is STALE (modified {file_date}, today {_date_csv.today()}) — skipping")
                csv_path = Path("__nonexistent__")  # Force fallback
        if not csv_path.exists():
            # Fallback 2: Try befday directory for canonical name
            befday_dir = Path("C:/StockTracker/quant_engine/befday")
            alt_path = befday_dir / filename
            found_valid = False
            if alt_path.exists():
                alt_date = _dt_csv.fromtimestamp(os.path.getmtime(alt_path)).date()
                if alt_date == _date_csv.today():
                    csv_path = alt_path
                    found_valid = True
                else:
                    logger.warning(f"[_load_befday_map] ⚠️ Befday dir CSV {alt_path} is STALE (modified {alt_date}) — skipping")
            
            if not found_valid:
                # Fallback 3: TODAY's DATED CSV in befday directory (e.g., befibped_20260219.csv)
                # ═══════════════════════════════════════════════════════════════
                # CRITICAL: Only accept TODAY's dated CSV, NEVER older dates!
                # If no today CSV exists → return empty → befday_is_empty → CURRENT=BEFDAY
                # ═══════════════════════════════════════════════════════════════
                try:
                    from datetime import datetime as dt
                    today_str = dt.now().strftime("%Y%m%d")
                    prefix = filename.replace('.csv', '')  # e.g., "befibped"
                    
                    today_dated = befday_dir / f"{prefix}_{today_str}.csv"
                    if today_dated.exists():
                        csv_path = today_dated
                        logger.info(f"[_load_befday_map] Using today's dated CSV: {csv_path}")
                    else:
                        logger.info(f"[_load_befday_map] No today CSV ({prefix}_{today_str}.csv) found — BEFDAY will be empty (CURRENT=BEFDAY)")
                        return {}
                except Exception:
                    return {}

        if not csv_path.exists():
            logger.warning(f"[_load_befday_map] Befday file not found: {csv_path}")
            return {}
            
        try:
            df = pd.read_csv(csv_path)
            
            # Check required columns
            if 'Symbol' not in df.columns or 'Quantity' not in df.columns:
                logger.error(f"[_load_befday_map] Invalid columns in {filename}: {df.columns}")
                return {}
            
            # Detect format: new format has Strategy/Full_Taxonomy, old format does not
            is_new_format = 'Strategy' in df.columns or 'Full_Taxonomy' in df.columns
            logger.debug(f"[_load_befday_map] CSV format: {'NEW' if is_new_format else 'LEGACY'} ({filename})")
                
            for _, row in df.iterrows():
                try:
                    sym = str(row['Symbol']).strip() # Strip whitespace!
                    qty = float(row['Quantity'])
                    
                    # Determine side from quantity FIRST (sign matters)
                    # Negative qty = Short, Positive qty = Long
                    inferred_side = "Long" if qty >= 0 else "Short"
                    
                    # BEFDAY: short pozisyonlar negatif olmalı. Eski CSV'de Quantity pozitif + Side=Short ise negatif yap
                    side_col = str(row.get('Side', '')).strip().lower()
                    pos_type = str(row.get('Position_Type', '')).strip().upper()
                    if qty > 0 and (side_col == 'short' or pos_type == 'SHORT'):
                        qty = -qty
                        inferred_side = "Short"
                    
                    # Extract taxonomy info if available (new format)
                    if is_new_format:
                        full_tax = str(row.get('Full_Taxonomy', ''))
                        strategy = str(row.get('Strategy', 'LT'))
                        origin = str(row.get('Origin', 'OV'))
                        side = str(row.get('Side', inferred_side))
                    else:
                        # Legacy format: derive from quantity sign
                        strategy = 'LT'
                        origin = 'OV'
                        side = inferred_side
                        full_tax = f"LT OV {inferred_side}"
                    
                    # Get avg_cost from multiple possible column names
                    avg_cost = None
                    # Priority 1: Avg_Cost (new format)
                    if 'Avg_Cost' in df.columns:
                        try:
                            avg_cost = float(row['Avg_Cost']) if pd.notna(row.get('Avg_Cost')) else None
                        except (TypeError, ValueError):
                            pass
                    # Priority 2: AveragePrice (legacy format like befham.csv)
                    if avg_cost is None and 'AveragePrice' in df.columns:
                        try:
                            avg_cost = float(row['AveragePrice']) if pd.notna(row.get('AveragePrice')) else None
                        except (TypeError, ValueError):
                            pass
                    # Priority 3: Calculate from MarketValue
                    if avg_cost is None and 'Market_Value' in df.columns and qty != 0:
                        try:
                            mv = float(row['Market_Value'])
                            avg_cost = mv / abs(qty) if qty else None
                        except (TypeError, ValueError):
                            pass
                    # Priority 4: MarketValue from legacy format
                    if avg_cost is None and 'MarketValue' in df.columns and qty != 0:
                        try:
                            mv = float(row['MarketValue'])
                            avg_cost = mv / abs(qty) if qty else None
                        except (TypeError, ValueError):
                            pass
                    
                    result[sym] = {
                        'quantity': qty,
                        'full_taxonomy': full_tax,
                        'strategy': strategy,
                        'origin': origin,
                        'side': side,
                        'avg_cost': avg_cost
                    }
                except Exception as row_error:
                    logger.warning(f"[_load_befday_map] Error parsing row in {filename}: {row_error}")
                    continue

            # Cache CSV data to Redis ONLY if key does NOT already exist.
            # BEFDAY is sacred — written once per day (user button click), never overwritten.
            if result:
                try:
                    import json
                    from app.core.redis_client import get_redis_client
                    redis = get_redis_client()
                    if redis:
                        key = f"psfalgo:befday:positions:{account_id}"
                        existing = redis.get(key)
                        if not existing:
                            befday_list = [
                                {
                                    "symbol": sym,
                                    "qty": info["quantity"],
                                    "full_taxonomy": info.get("full_taxonomy", ""),
                                    "strategy": info.get("strategy", "LT"),
                                    "origin": info.get("origin", "OV"),
                                    "side": info.get("side", ""),
                                    "avg_cost": info.get("avg_cost"),
                                }
                                for sym, info in result.items()
                            ]
                            redis.set(key, json.dumps(befday_list), ex=86400)
                            # Also write companion date key for staleness check
                            from datetime import datetime as _dt
                            date_key = f"psfalgo:befday:date:{account_id}"
                            redis.set(date_key, _dt.now().strftime("%Y%m%d"), ex=86400)
                            logger.info(f"[_load_befday_map] Cached {len(befday_list)} CSV BEFDAY entries to Redis {key} + date key (first write)")
                        else:
                            logger.debug(f"[_load_befday_map] Redis BEFDAY key {key} already exists, not overwriting from CSV")
                except Exception as re:
                    logger.warning(f"[_load_befday_map] Redis write after CSV load failed: {re}")

            return result
        except Exception as e:
            logger.warning(f"Failed to load {filename}: {e}")
            return {}

    def get_befday_exposure_snapshot(self, account_id: str):
        """
        Compute ExposureSnapshot from BEFDAY positions for the account.
        Uses avg_cost from BEFDAY when available, else current price (last/bid/ask).
        Returns None if no befday data or calculator not available.
        Cached 10s to avoid recalc on every /api/trading/exposure poll.
        """
        now = time.time()
        if account_id in _BEFDAY_EXPOSURE_CACHE:
            expiry_ts, cached = _BEFDAY_EXPOSURE_CACHE[account_id]
            if now < expiry_ts and cached is not None:
                return cached
        from app.psfalgo.decision_models import PositionSnapshot as PosSnap
        from app.psfalgo.exposure_calculator import get_exposure_calculator
        befday_map = self._load_befday_map(account_id)
        if not befday_map:
            return None
        calculator = get_exposure_calculator()
        if not calculator:
            return None
        positions = []
        for sym, info in befday_map.items():
            qty = float(info.get("quantity", 0))
            if abs(qty) < 0.001:
                continue
            price = info.get("avg_cost")
            if price is None or float(price) <= 0:
                price = self._get_current_price(sym)
            if price is None or float(price) <= 0:
                price = 100.0
            price = float(price)
            positions.append(
                PosSnap(symbol=sym, qty=qty, avg_price=price, current_price=price, unrealized_pnl=0.0)
            )
        if not positions:
            return None
        result = calculator.calculate_exposure(positions)
        _BEFDAY_EXPOSURE_CACHE[account_id] = (time.time() + _BEFDAY_EXPOSURE_CACHE_TTL, result)
        return result

    def _determine_taxonomy(self, qty: float, befday_qty: float, symbol: str = "", account_id: str = "") -> tuple[str, str, str]:
        """
        Determine Strategy, Origin, and Full Taxonomy string.
        Logic:
        - Origin: If in Befday (befday_qty != 0) -> OV (Overnight). Else INT (Intraday).
        - Strategy: Check Internal Ledger for LT/MM split. Default LT if no ledger data.
        - Side: Long/Short based on Qty sign.
        """
        # Origin
        origin_type = "OV" if abs(befday_qty) > 0.001 else "INT"
        
        # Strategy: Check Internal Ledger for actual LT/MM split
        strategy_type = "LT"  # default
        if symbol and account_id:
            try:
                from app.psfalgo.internal_ledger_store import get_internal_ledger_store
                ledger = get_internal_ledger_store()
                if ledger and ledger.has_symbol(account_id, symbol):
                    lt_qty = ledger.get_lt_quantity(account_id, symbol)
                    mm_qty = qty - lt_qty
                    # Dominant bucket by absolute size
                    if abs(mm_qty) > abs(lt_qty) and abs(mm_qty) > 0.01:
                        strategy_type = "MM"
            except Exception:
                pass
        
        # Side
        side = "Long" if qty >= 0 else "Short"
        if abs(qty) < 0.01 and abs(befday_qty) > 0.01:
             # Closed position check side of befday
             side = "Long" if befday_qty >= 0 else "Short"
        
        full_taxonomy = f"{strategy_type} {origin_type} {side}"
        return strategy_type, origin_type, full_taxonomy
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current market price for symbol.
        
        Priority:
        1. last (from market_data_cache)
        2. bid (if long position)
        3. ask (if short position)
        4. price (fallback)
        
        Args:
            symbol: Symbol (PREF_IBKR)
            
        Returns:
            Current price or None
        """
        # Dynamic import to ensure we see the LATEST authentic global cache
        # (Avoids stale reference issues if init happened too early)
        from app.api.market_data_routes import market_data_cache
        
        market_data = market_data_cache.get(symbol, {})
        
        # Priority 1: last
        if 'last' in market_data and market_data['last']:
            return float(market_data['last'])
        
        # Priority 2: price (fallback)
        if 'price' in market_data and market_data['price']:
            return float(market_data['price'])
        
        # Priority 3: mid price (bid + ask) / 2
        bid = market_data.get('bid')
        ask = market_data.get('ask')
        if bid and ask and float(bid) > 0 and float(ask) > 0:
            return (float(bid) + float(ask)) / 2.0
        
        # Priority 4: bid or ask (whichever available)
        if bid and float(bid) > 0:
            return float(bid)
        if ask and float(ask) > 0:
            return float(ask)
            
        # Debugging: Why did it fail?
        # Only log if cache seems populated but this symbol is missing/empty
        if len(market_data_cache) > 0:
            if not market_data:
                 logger.debug(f"[PRICE_LOOKUP_FAIL] Symbol '{symbol}' not found in cache (Size: {len(market_data_cache)})")
            else:
                 logger.debug(f"[PRICE_LOOKUP_FAIL] Symbol '{symbol}' found but no valid price keys. Data: {market_data}")

        # Fallback: Try Redis (L1 Stream)
        # This is critical for standalone workers (like RevnBookCheck) that don't share memory with Backend
        try:
            from app.core.redis_client import get_redis_client
            import json
            redis = get_redis_client()
            if redis:
                key = f"market:l1:{symbol}"
                data = redis.get(key)
                if data:
                    l1_data = json.loads(data)
                    # Support 'last', 'bid', 'ask' in that order
                    if 'last' in l1_data and l1_data['last'] > 0:
                        return float(l1_data['last'])
                    if 'bid' in l1_data and l1_data['bid'] > 0:
                        return float(l1_data['bid'])
                    # If we found data but no price, that's still a "found" but empty.
                    logger.debug(f"[PRICE_FROM_REDIS] Found {symbol} in Redis but valid price missing: {l1_data}")
        except Exception as re:
             logger.debug(f"[PRICE_FROM_REDIS] Error reading Redis for {symbol}: {re}")
        
        return None
    
    def _get_group_info(self, symbol: str) -> tuple[Optional[str], Optional[str]]:
        """
        Get group and cgrup for symbol from static data.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            
        Returns:
            Tuple of (group, cgrup)
        """
        if not self.static_store:
            return None, None
        
        static_data = self.static_store.get_static_data(symbol)
        if not static_data:
            return None, None
        
        # Get primary group
        group = resolve_primary_group(static_data, symbol)
        
        # Get secondary group (CGRUP) if applicable
        cgrup = None
        if group in ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']:
            cgrup = resolve_secondary_group(static_data, group)
        
        return group, cgrup
    
    def _calculate_holding_time(self, last_update_time: float) -> tuple[Optional[datetime], float]:
        """
        Calculate holding time metrics.
        
        Args:
            last_update_time: Unix timestamp of last position update
            
        Returns:
            Tuple of (position_open_ts, holding_minutes)
        """
        if not last_update_time or last_update_time <= 0:
            return None, 0.0
        
        try:
            # Convert to datetime
            position_open_ts = datetime.fromtimestamp(last_update_time)
            
            # Calculate holding minutes
            now = datetime.now()
            holding_delta = now - position_open_ts
            holding_minutes = holding_delta.total_seconds() / 60.0
            
            return position_open_ts, holding_minutes
            
        except Exception as e:
            logger.debug(f"Error calculating holding time: {e}")
            return None, 0.0

    @staticmethod
    def normalize_ibkr_symbol(symbol: str) -> str:
        """
        Normalize IBKR symbol to match internal FAST/Janall naming convention.
        
        Strict Logic (User Instruction):
        - Replace '-' with ' PR'
        
        Examples:
        - MITT-A -> MITT PRA
        - ACR-D  -> ACR PRD
        - CIM-C  -> CIM PRC
        - PRS    -> PRS (no change)
        
        Args:
            symbol: Original IBKR symbol
            
        Returns:
            Normalized symbol
        """
        if not symbol:
            return ""
        
        # Strict replacement rule: "-" -> " PR"
        return symbol.replace('-', ' PR').strip()
        
    def _calculate_position_tags(
        self,
        account_id: str,
        symbol: str,
        befday_qty: float,
        current_qty: float,
        befday_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, float]:
        """
        Calculate 8-Type Position Tags (OV/INT Split).
        
        Logic (User Defined):
        - OV: Based on Befday Quantity + Befday Strategy (LT/MM).
        - INT: Logic requires LT/MM Split of Intraday moves.
             We use InternalLedgerStore (which tracks Total LT) to derive this.
             Total LT = Ledger.get_lt_quantity()
             Total MM = Current - Total LT
             
        - LT_INT = Total LT - LT_OV (adjusted for closure)
        - MM_INT = Total MM - MM_OV (adjusted for closure)
        
        Returns:
            Dict[tag, qty] e.g. {'LT_LONG_OV': 1000.0, 'LT_LONG_INT': 400.0}
        """
        tags: Dict[str, float] = {}
        
        # 0. Get Befday Strategy (Default to LT if not specified)
        bef_strategy = "LT"
        if befday_data:
             st = befday_data.get('strategy', 'LT')
             if str(st).strip() != "": bef_strategy = str(st).strip().upper()
        
        # 1. Fetch Total LT from Internal Ledger
        from app.psfalgo.internal_ledger_store import get_internal_ledger_store, initialize_internal_ledger_store
        store = get_internal_ledger_store()
        if not store:
             initialize_internal_ledger_store()
             store = get_internal_ledger_store()
             
        total_lt = 0.0
        
        # Determine Base LT from Befday (Default Assumption)
        bef_lt_base = 0.0
        if bef_strategy == "LT":
             bef_lt_base = befday_qty
        
        # Check Ledger Overrides
        if store:
             if store.has_symbol(account_id, symbol):
                  # Ledger has explicit state (even if 0) -> Use it
                  total_lt = store.get_lt_quantity(account_id, symbol)
             else:
                  # Ledger has NO state -> Default to Befday Base
                  total_lt = bef_lt_base
        else:
             # No store -> Default to Befday Base
             total_lt = bef_lt_base
             
        # 2. Calculate Total MM
        total_mm = current_qty - total_lt
        
        # 3. Determine Breakdown (OV vs INT) using DailyFillsStore
        # ------------------------------------------------------------------
        # Logic:
        # Use INT components from Daily Fills Log (Actual Filled Orders).
        # Calculate OV as residual (Total - INT).
        
        lt_int_qty = 0.0
        mm_int_qty = 0.0
        
        try:
             from app.trading.daily_fills_store import get_daily_fills_store
             daily_store = get_daily_fills_store()
             breakdown = daily_store.get_intraday_breakdown(account_id, symbol)
             lt_int_qty = breakdown.get('LT', 0.0)
             mm_int_qty = breakdown.get('MM', 0.0)
        except Exception as e:
             # Fallback (Safety)
             pass
             
        # 4. Calculate OV (Residual)
        lt_ov_qty = total_lt - lt_int_qty
        mm_ov_qty = total_mm - mm_int_qty
        
        # 5. Map to Tags
        tags: Dict[PositionTag, float] = {}
        
        def add_tag(qty, book, origin):
             if abs(qty) > 0.001:
                  side = "LONG" if qty > 0 else "SHORT"
                  
                  # Correct Enum Mapping
                  # book=LT, origin=OV -> LT_LONG_OV
                  tag = None
                  if book == "LT":
                       if origin == "OV":
                            tag = PositionTag.LT_LONG_OV if qty > 0 else PositionTag.LT_SHORT_OV
                       else:
                            tag = PositionTag.LT_LONG_INT if qty > 0 else PositionTag.LT_SHORT_INT
                  else:
                       if origin == "OV":
                            tag = PositionTag.MM_LONG_OV if qty > 0 else PositionTag.MM_SHORT_OV
                       else:
                            tag = PositionTag.MM_LONG_INT if qty > 0 else PositionTag.MM_SHORT_INT
                            
                  if tag:
                       tags[tag] = abs(qty)
                  
        add_tag(lt_ov_qty, "LT", "OV")
        add_tag(lt_int_qty, "LT", "INT")
        add_tag(mm_ov_qty, "MM", "OV")
        add_tag(mm_int_qty, "MM", "INT")
            
        return tags

    def _get_prev_close(self, symbol: str) -> float:
        """
        Get Previous Close price for the symbol.
        Source: StaticDataStore (janalldata.csv) or Redis fallback.
        """
        try:
            # 1. Try Static Data Store (Primary Source for Daily Prev Close)
            if self.static_store:
                # Try with normalized symbol (e.g. "MITT PRA")
                static_data = self.static_store.get_static_data(symbol)
                if static_data and static_data.get('prev_close'):
                     val = float(static_data['prev_close'])
                     if val > 0: return val
                     
                # Try with raw symbol just in case (e.g. "MITT-A")
                if "-" in symbol:
                     raw_static = self.static_store.get_static_data(symbol)
                     if raw_static and raw_static.get('prev_close'):
                         val = float(raw_static['prev_close'])
                         if val > 0: return val

            # 2. Redis Fallback (TODO: Implement when Market Data Engine populates it consistently)
            # if self.redis_client:
            #    ...
            
            return 0.0
            
        except Exception:
            return 0.0


# Global instance
_position_snapshot_api: Optional[PositionSnapshotAPI] = None


def get_position_snapshot_api() -> Optional[PositionSnapshotAPI]:
    """Get global PositionSnapshotAPI instance"""
    return _position_snapshot_api


def initialize_position_snapshot_api(
    position_manager=None,
    static_store: Optional[StaticDataStore] = None,
    market_data_cache: Optional[Dict[str, Dict[str, Any]]] = None
):
    """Initialize global PositionSnapshotAPI instance"""
    global _position_snapshot_api
    _position_snapshot_api = PositionSnapshotAPI(
        position_manager=position_manager,
        static_store=static_store,
        market_data_cache=market_data_cache
    )
    logger.info("PositionSnapshotAPI initialized")

