"""
Position Redis Worker
=====================

CRITICAL: Periodically updates positions AND open orders to Redis for ALL accounts.

This worker ensures that every engine (MinMax, DailyLimit, REV, etc.) always reads
FRESH position data from Redis — regardless of which account is currently "active".

Key design rules:
- Positions and orders for BOTH HAMPRO and IBKR_PED are refreshed every cycle.
- BEFDAY values are READ-ONLY (captured once per day at startup, never modified here).
- Only current qty and potential_qty change throughout the day.
- Open orders are used to calculate potential_qty = qty + net_open_orders.

Redis Keys Updated:
    psfalgo:positions:{account_id}     → positions with qty, potential_qty, befday_qty
    psfalgo:open_orders:{account_id}   → open orders list
"""
import asyncio
import json
import time
from loguru import logger
from typing import Optional, Dict, List, Any


# All accounts to keep fresh
ALL_ACCOUNTS = ["HAMPRO", "IBKR_PED"]


class PositionRedisWorker:
    """
    Worker that periodically writes positions AND orders for ALL accounts to Redis.
    
    This is the SINGLE SOURCE OF TRUTH for terminals and engines:
    - Backend writes positions/orders to Redis every 30s
    - Terminals, MinMax, REV, etc. read from Redis (no HTTP/broker calls needed)
    - BEFDAY is NEVER modified (sacred, captured once at day start)
    """
    
    def __init__(self):
        self.running = False
        self.update_interval = 30  # seconds
        self._refresh_count = 0
        self._error_count = 0
    
    async def run(self):
        """Main worker loop — refreshes ALL accounts."""
        logger.info(
            f"[PositionRedisWorker] Starting... "
            f"(updates every {self.update_interval}s, accounts={ALL_ACCOUNTS})"
        )
        self.running = True
        
        # Wait a bit for services to initialize
        await asyncio.sleep(15)
        
        while self.running:
            try:
                for account_id in ALL_ACCOUNTS:
                    if not self.running:
                        break
                    try:
                        await self._refresh_account(account_id)
                    except Exception as e:
                        self._error_count += 1
                        logger.warning(f"[PositionRedisWorker] {account_id} refresh error: {e}")

                self._refresh_count += 1
                if self._refresh_count % 20 == 0:
                    logger.info(
                        f"[PositionRedisWorker] 📊 cycle #{self._refresh_count} "
                        f"(errors: {self._error_count})"
                    )

            except Exception as e:
                logger.error(f"[PositionRedisWorker] Loop error: {e}", exc_info=True)
            
            await asyncio.sleep(self.update_interval)

    async def _refresh_account(self, account_id: str):
        """Refresh positions + orders for a single account."""
        t0 = time.time()

        # 1. Refresh positions
        pos_count = await self._refresh_positions(account_id)

        # 2. Refresh open orders
        order_count = await self._refresh_open_orders(account_id)

        # 3. Update potential_qty using fresh order data
        if order_count > 0:
            self._update_potential_qty(account_id)

        elapsed = time.time() - t0
        # Log at INFO every 10th cycle, DEBUG otherwise
        log_fn = logger.info if self._refresh_count % 10 == 0 else logger.debug
        log_fn(
            f"[PositionRedisWorker] {account_id}: "
            f"{pos_count} positions, {order_count} orders "
            f"({elapsed:.1f}s)"
        )

    # ═══════════════════════════════════════════════════════════════
    # Position Refresh
    # ═══════════════════════════════════════════════════════════════

    async def _refresh_positions(self, account_id: str) -> int:
        """Fetch live positions and write to Redis.
        
        MERGE strategy: If fill_tag_handler has written a fresher qty update
        (within the last 30s), we KEEP the fill_tag_handler value (it's more accurate
        because it reacted to a fill event immediately).
        
        BEFDAY is NEVER overwritten — only read from psfalgo:befday:positions:{account_id}.
        """
        from app.core.redis_client import get_redis_client
        redis = get_redis_client()
        if not redis:
            return 0

        pos_key = f"psfalgo:positions:{account_id}"

        # ── Fetch live positions from broker ──
        live_positions: Dict[str, Dict] = {}

        if "HAMPRO" in account_id.upper():
            live_positions = self._fetch_hampro_positions()
        elif "IBKR" in account_id.upper():
            live_positions = await self._fetch_ibkr_positions(account_id)

        if not live_positions:
            # No positions from broker — don't wipe existing Redis data
            # (fill_tag_handler may have updated it more recently)
            return 0

        # ── MERGE with existing Redis data ──
        # fill_tag_handler writes to Redis on every fill event (immediate).
        # If fill_tag_handler wrote FRESHER qty within last 30s, we must
        # preserve that qty (broker may not have synced the fill yet).
        try:
            raw = redis.get(pos_key)
            if raw:
                data_str = raw if isinstance(raw, str) else raw.decode('utf-8')
                existing = json.loads(data_str)
                if isinstance(existing, dict):
                    meta = existing.get('_meta', {})
                    existing_updated_at = meta.get('updated_at', 0)
                    existing_source = meta.get('source', '')
                    
                    # If fill_tag_handler updated within last 30s, its qty values
                    # are MORE ACCURATE than broker data (broker sync is delayed)
                    fill_tag_is_fresher = (
                        existing_source != 'position_redis_worker' and
                        (time.time() - existing_updated_at) < 30
                    )

                    for sym, info in existing.items():
                        if sym == '_meta':
                            continue
                        if not isinstance(info, dict):
                            continue
                        
                        if sym not in live_positions:
                            # Symbol in existing but not in live broker data:
                            # keep it (broker may not have synced yet but fill happened)
                            live_positions[sym] = info
                        elif fill_tag_is_fresher:
                            # Symbol exists in both — but fill_tag_handler data is fresher
                            # Preserve fill_tag_handler's qty (it reacted to a fill event)
                            existing_qty = float(info.get('qty', 0))
                            broker_qty = float(live_positions[sym].get('qty', 0))
                            if abs(existing_qty - broker_qty) > 0.01:
                                live_positions[sym]['qty'] = existing_qty
                                live_positions[sym]['potential_qty'] = float(info.get('potential_qty', existing_qty))
                                logger.debug(
                                    f"[PositionRedisWorker] MERGE: {sym} keeping fill_tag qty "
                                    f"{existing_qty:.0f} over broker qty {broker_qty:.0f} "
                                    f"(fill_tag_handler updated {time.time() - existing_updated_at:.0f}s ago)"
                                )
        except Exception as e:
            logger.debug(f"[PositionRedisWorker] Merge read error: {e}")

        # ── Enrich with BEFDAY data (READ-ONLY, never modify befday itself) ──
        try:
            befday_key = f"psfalgo:befday:positions:{account_id}"
            befday_raw = redis.get(befday_key)
            if befday_raw:
                befday_str = befday_raw if isinstance(befday_raw, str) else befday_raw.decode('utf-8')
                befday_data = json.loads(befday_str)
                befday_map = {}
                if isinstance(befday_data, list):
                    for entry in befday_data:
                        sym = entry.get('symbol', '')
                        bef_qty = float(entry.get('qty', entry.get('quantity', 0)))
                        if sym:
                            befday_map[sym] = bef_qty
                elif isinstance(befday_data, dict):
                    for sym, info in befday_data.items():
                        if sym == '_meta':
                            continue
                        if isinstance(info, dict):
                            befday_map[sym] = float(info.get('qty', info.get('quantity', 0)))
                        else:
                            befday_map[sym] = float(info or 0)

                # Apply befday_qty to positions (BEFDAY is sacred, only READ here)
                for sym, bef_qty in befday_map.items():
                    if sym in live_positions and isinstance(live_positions[sym], dict):
                        live_positions[sym]['befday_qty'] = bef_qty
                    elif sym not in live_positions:
                        # Symbol in befday but no live position → might have been closed today
                        # Include so MinMax can see befday_qty even when current=0
                        live_positions[sym] = {
                            'symbol': sym,
                            'qty': 0.0,
                            'potential_qty': 0.0,
                            'befday_qty': bef_qty,
                            'avg_price': 0.0,
                            'current_price': 0.0,
                        }
        except Exception as e:
            logger.debug(f"[PositionRedisWorker] Befday enrichment error: {e}")

        # ── Write to Redis ──
        live_positions['_meta'] = {
            'updated_at': time.time(),
            'source': 'position_redis_worker',
            'account_id': account_id,
        }
        redis.set(pos_key, json.dumps(live_positions), ex=3600)  # 1-hour TTL (must survive brief outages)

        return len([k for k in live_positions if k != '_meta'])

    def _fetch_hampro_positions(self) -> Dict[str, Dict]:
        """Fetch HAMPRO positions from Hammer positions service (sync).
        
        CRITICAL: Uses get_hammer_positions_service() — the SAME service that
        the UI and position_snapshot_api use. This ensures Redis always has
        the same position data that the frontend displays.
        """
        result = {}
        try:
            from app.api.trading_routes import get_hammer_positions_service
            svc = get_hammer_positions_service()
            if not svc:
                logger.warning("[PositionRedisWorker] HAMPRO: No HammerPositionsService available")
                return result

            positions = svc.get_positions(force_refresh=False)
            if not positions:
                logger.debug("[PositionRedisWorker] HAMPRO: get_positions returned empty")
                return result

            for pos in positions:
                if isinstance(pos, dict):
                    # HammerPositionsService._normalize_position returns:
                    # symbol, side, quantity, avg_price, current_price, unrealized_pnl, market_value
                    sym = pos.get('symbol', '')
                    qty = float(pos.get('quantity', pos.get('qty', 0)))
                    avg_price = float(pos.get('avg_price', pos.get('avgPrice', 0)))
                    current_price_raw = pos.get('current_price')
                else:
                    sym = getattr(pos, 'symbol', '')
                    qty = float(getattr(pos, 'quantity', getattr(pos, 'qty', 0)))
                    avg_price = float(getattr(pos, 'avg_price', getattr(pos, 'avgPrice', 0)))
                    current_price_raw = getattr(pos, 'current_price', None)

                if sym and abs(qty) > 0.001:
                    # Prefer live L1 price, fallback to position's current_price, then avg_price
                    current_price = self._get_live_price(sym) or (float(current_price_raw) if current_price_raw else None) or avg_price
                    result[sym] = {
                        'symbol': sym,
                        'qty': qty,
                        'potential_qty': qty,
                        'befday_qty': 0.0,  # Will be enriched from befday data below
                        'avg_price': avg_price,
                        'current_price': current_price,
                        'unrealized_pnl': (current_price - avg_price) * qty if avg_price > 0 else 0,
                    }
            
            if result:
                logger.debug(f"[PositionRedisWorker] HAMPRO: fetched {len(result)} positions from Hammer")
        except Exception as e:
            logger.warning(f"[PositionRedisWorker] HAMPRO fetch error: {e}")
        return result

    async def _fetch_ibkr_positions(self, account_id: str) -> Dict[str, Dict]:
        """Fetch IBKR positions via isolated sync wrapper.
        
        CRITICAL: connector.get_positions() is ASYNC — calling it in run_in_executor
        creates a coroutine that is never awaited, causing RuntimeWarning.
        We must use get_positions_isolated_sync() which properly runs on the IB loop thread.
        """
        result = {}
        try:
            from app.psfalgo.ibkr_connector import get_ibkr_connector, get_positions_isolated_sync
            connector = get_ibkr_connector(account_type=account_id, create_if_missing=False)
            if not connector or not connector.is_connected():
                return result

            loop = asyncio.get_running_loop()
            positions = await loop.run_in_executor(
                None, lambda: get_positions_isolated_sync(account_id)
            )
            if not positions:
                return result

            for pos in positions:
                if isinstance(pos, dict):
                    sym = pos.get('symbol', '')
                    qty = float(pos.get('position', pos.get('qty', 0)))
                    avg_price = float(pos.get('avgCost', pos.get('avg_price', 0)))
                else:
                    sym = getattr(pos, 'symbol', '')
                    qty = float(getattr(pos, 'position', getattr(pos, 'qty', 0)))
                    avg_price = float(getattr(pos, 'avgCost', getattr(pos, 'avg_price', 0)))

                sym = sym.strip() if sym else ''
                if sym and abs(qty) > 0.001:
                    current_price = self._get_live_price(sym) or avg_price
                    result[sym] = {
                        'symbol': sym,
                        'qty': qty,
                        'potential_qty': qty,
                        'befday_qty': 0.0,
                        'avg_price': avg_price,
                        'current_price': current_price,
                        'unrealized_pnl': (current_price - avg_price) * qty if avg_price > 0 else 0,
                    }
        except Exception as e:
            logger.warning(f"[PositionRedisWorker] IBKR fetch error for {account_id}: {e}")
        return result

    # ═══════════════════════════════════════════════════════════════
    # Open Orders Refresh
    # ═══════════════════════════════════════════════════════════════

    async def _refresh_open_orders(self, account_id: str) -> int:
        """Fetch open orders and write to Redis."""
        from app.core.redis_client import get_redis_client
        redis = get_redis_client()
        if not redis:
            return 0

        orders_key = f"psfalgo:open_orders:{account_id}"
        orders: List[Dict] = []

        if "HAMPRO" in account_id.upper():
            orders = self._fetch_hampro_orders()
        elif "IBKR" in account_id.upper():
            orders = await self._fetch_ibkr_orders(account_id)

        # Write (even empty = "no open orders" signal)
        order_data = {
            'orders': orders,
            'count': len(orders),
            'updated_at': time.time(),
            'account_id': account_id,
        }
        redis.set(orders_key, json.dumps(order_data), ex=3600)  # 1-hour TTL
        return len(orders)

    def _fetch_hampro_orders(self) -> List[Dict]:
        """Fetch HAMPRO open orders via Hammer orders service."""
        try:
            from app.trading.hammer_orders_service import get_hammer_orders_service
            svc = get_hammer_orders_service()
            if not svc:
                return []

            raw_orders = svc.get_orders()
            if not raw_orders:
                return []

            orders = []
            for o in raw_orders:
                if isinstance(o, dict):
                    orders.append({
                        'symbol': o.get('symbol', ''),
                        'action': o.get('action', 'BUY').upper(),
                        'totalQuantity': float(o.get('totalQuantity', o.get('qty', 0))),
                        'price': float(o.get('price', o.get('lmtPrice', 0))),
                        'orderId': o.get('orderId', o.get('OrderID', '')),
                        'status': o.get('status', o.get('StatusID', '')),
                        'account': 'HAMPRO',
                    })
            return orders
        except Exception as e:
            logger.warning(f"[PositionRedisWorker] HAMPRO orders error: {e}")
            return []

    async def _fetch_ibkr_orders(self, account_id: str) -> List[Dict]:
        """Fetch IBKR open orders.
        
        Uses get_open_orders_isolated_sync which runs on the IB event loop
        thread synchronously — avoids the async/await mismatch that caused
        'coroutine was never awaited' RuntimeWarning.
        """
        try:
            from app.psfalgo.ibkr_connector import get_open_orders_isolated_sync
            
            loop = asyncio.get_running_loop()
            raw_orders = await loop.run_in_executor(
                None, lambda: get_open_orders_isolated_sync(account_id)
            )
            if not raw_orders:
                return []

            orders = []
            for o in raw_orders:
                if isinstance(o, dict):
                    orders.append({
                        'symbol': o.get('symbol', '').strip(),
                        'action': o.get('action', 'BUY').upper(),
                        'totalQuantity': float(o.get('totalQuantity', o.get('qty', 0))),
                        'price': float(o.get('lmtPrice', o.get('price', 0))),
                        'orderId': o.get('orderId', o.get('order_id', '')),
                        'status': o.get('status', 'Submitted'),
                        'account': account_id,
                    })
            return orders
        except Exception as e:
            logger.warning(f"[PositionRedisWorker] IBKR orders error for {account_id}: {e}")
            return []

    # ═══════════════════════════════════════════════════════════════
    # Potential Qty Update
    # ═══════════════════════════════════════════════════════════════

    def _update_potential_qty(self, account_id: str):
        """Update potential_qty in Redis: potential_qty = qty + net_open_orders."""
        # ═══════════════════════════════════════════════════════════════
        # CANCEL GRACE PERIOD GUARD: After reqGlobalCancel or Hammer
        # cancel_all, open orders in Redis may be stale (still showing
        # cancelled orders). During the grace period, skip potential_qty
        # updates to avoid overwriting the correct potential_qty = qty
        # with stale cancelled order data.
        # ═══════════════════════════════════════════════════════════════
        try:
            from app.psfalgo.exposure_calculator import _is_cancel_grace_period_active
            if _is_cancel_grace_period_active():
                logger.debug(f"[PositionRedisWorker] ⏳ Cancel grace period active — skipping potential_qty update for {account_id}")
                return
        except Exception:
            pass
        
        from app.core.redis_client import get_redis_client
        redis = get_redis_client()
        if not redis:
            return

        try:
            # Read positions
            pos_key = f"psfalgo:positions:{account_id}"
            raw = redis.get(pos_key)
            if not raw:
                return
            data_str = raw if isinstance(raw, str) else raw.decode('utf-8')
            positions = json.loads(data_str)
            if not isinstance(positions, dict):
                return

            # Read orders
            orders_key = f"psfalgo:open_orders:{account_id}"
            raw_orders = redis.get(orders_key)
            if not raw_orders:
                return
            orders_str = raw_orders if isinstance(raw_orders, str) else raw_orders.decode('utf-8')
            orders_data = json.loads(orders_str)
            orders = orders_data.get('orders', []) if isinstance(orders_data, dict) else []

            # Calculate net open qty per symbol
            open_qty_map: Dict[str, float] = {}
            for order in orders:
                sym = order.get('symbol', '')
                qty = float(order.get('totalQuantity', 0))
                action = order.get('action', 'BUY').upper()
                if action in ('SELL', 'SSHORT'):
                    qty = -qty
                if sym:
                    open_qty_map[sym] = open_qty_map.get(sym, 0.0) + qty

            # Update potential_qty
            changed = False
            for sym, net_open in open_qty_map.items():
                if sym in positions and isinstance(positions[sym], dict):
                    current_qty = float(positions[sym].get('qty', 0))
                    new_potential = current_qty + net_open
                    old_potential = float(positions[sym].get('potential_qty', 0))
                    if abs(old_potential - new_potential) > 0.01:
                        positions[sym]['potential_qty'] = new_potential
                        changed = True

            if changed:
                positions['_meta'] = positions.get('_meta', {})
                positions['_meta']['potential_updated_at'] = time.time()
                redis.set(pos_key, json.dumps(positions), ex=3600)  # 1-hour TTL
        except Exception as e:
            logger.warning(f"[PositionRedisWorker] potential_qty error for {account_id}: {e}")

    # ═══════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════

    def _get_live_price(self, symbol: str) -> Optional[float]:
        """Get current price from DataFabric."""
        try:
            from app.core.data_fabric import get_data_fabric
            fabric = get_data_fabric()
            if fabric:
                snap = fabric.get_fast_snapshot(symbol)
                if snap:
                    return snap.get('last') or snap.get('bid') or snap.get('ask')
        except Exception:
            pass
        return None


# Global instance
_position_redis_worker: Optional[PositionRedisWorker] = None


def get_position_redis_worker() -> Optional[PositionRedisWorker]:
    """Get global PositionRedisWorker instance"""
    return _position_redis_worker


def start_position_redis_worker():
    """Start the position Redis worker"""
    global _position_redis_worker
    
    if _position_redis_worker and _position_redis_worker.running:
        logger.warning("[PositionRedisWorker] Already running")
        return
    
    _position_redis_worker = PositionRedisWorker()
    
    # Start in background
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_position_redis_worker.run())
        logger.info("[PositionRedisWorker] ✅ Started (ALL accounts, 30s interval)")
    except RuntimeError:
        asyncio.create_task(_position_redis_worker.run())
        logger.info("[PositionRedisWorker] ✅ Started via asyncio.create_task")
    except Exception as e:
        logger.error(f"[PositionRedisWorker] Failed to start: {e}")

